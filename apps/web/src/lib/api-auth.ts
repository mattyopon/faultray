import { createClient } from "@/lib/supabase/server";
import { NextResponse } from "next/server";
import type { SupabaseClient, User } from "@supabase/supabase-js";
import type { PlanTier } from "@/lib/types";

type SsrSupabase = Awaited<ReturnType<typeof createClient>>;

type AuthSuccess = { user: User; supabase: SsrSupabase; error: null };
type AuthFailure = { user: null; supabase: null; error: NextResponse };

/**
 * Plan hierarchy: free < starter < pro < business.
 *
 * Must stay in sync with the DB CHECK constraint (migration 005 allows
 * 'starter') and the Stripe webhook's PlanTier. Omitting a tier here is a
 * security bug: `PLAN_ORDER[unknownPlan]` is undefined and
 * `undefined < n` is false, which would let that tier through every gate.
 */
export type Plan = PlanTier;

type PlanSuccess = { user: User; supabase: SsrSupabase; plan: Plan; error: null };
type PlanFailure = { user: null; supabase: null; plan: null; error: NextResponse };

// Re-export for downstream typing convenience.
export type { SupabaseClient };

const PLAN_ORDER: Record<Plan, number> = { free: 0, starter: 1, pro: 2, business: 3 };

/**
 * CSRF保護: リクエストの Origin ヘッダーを allowlist と比較する。
 *
 * Allowlist:
 *   - 必須: `NEXT_PUBLIC_SITE_URL` (production / 全環境)
 *   - 非本番のみ: `VERCEL_URL` (preview/staging deployment の ephemeral
 *     `*.vercel.app` ドメイン。server-only env で改竄不可)
 *
 * production (`VERCEL_ENV='production'`) では `NEXT_PUBLIC_SITE_URL` のみ
 * 厳格一致。VERCEL_ENV 未設定 (self-host) では NODE_ENV='production' で
 * fallback 判定 (checkout/route.ts と整合)。
 *
 * Stripe webhook および cron ルート (/api/stripe/webhook, /api/cron/) は
 * Origin ヘッダーがないため CSRF チェックをスキップする。
 *
 * @returns 403 Response if Origin is invalid, null if OK
 */
function checkCsrf(request: Request): NextResponse | null {
  const url = new URL(request.url);
  // stripe webhook と cron はサーバー間リクエストのため Origin なし — スキップ
  const skipPaths = ["/api/stripe/webhook", "/api/cron/"];
  if (skipPaths.some((p) => url.pathname.startsWith(p))) {
    return null;
  }

  const origin = request.headers.get("origin");
  // Origin ヘッダーなし (サーバー間・curl など) は通過させる
  if (!origin) return null;

  const allowed = new Set<string>();

  // Primary allowlist: NEXT_PUBLIC_SITE_URL (production canonical domain).
  const siteUrl = process.env.NEXT_PUBLIC_SITE_URL ?? "https://faultray.com";
  try {
    allowed.add(new URL(siteUrl).origin);
  } catch {
    // malformed env — fall through; if VERCEL_URL も無ければ後続で fail-open
  }

  // Non-production-only: VERCEL_URL (preview/staging deployment domain).
  // Production を VERCEL_ENV で判定するのは checkout/route.ts と同じ理由
  // (preview build も NODE_ENV='production' になるため NODE_ENV だけでは
  // 区別不能)。VERCEL_ENV 未設定 (Vercel 外 self-host) は NODE_ENV fallback。
  const vercelEnv = process.env.VERCEL_ENV;
  const isProduction = vercelEnv
    ? vercelEnv === "production"
    : process.env.NODE_ENV === "production";
  if (!isProduction && process.env.VERCEL_URL) {
    try {
      allowed.add(new URL(`https://${process.env.VERCEL_URL}`).origin);
    } catch {
      // ignore
    }
  }

  if (allowed.size === 0) {
    // 設定 mis でいかなる allowlist も組み立てられない → fail-open
    // (production で NEXT_PUBLIC_SITE_URL が malformed だと全 request 403 に
    //  なるのを避ける従来挙動を維持)
    return null;
  }

  if (!allowed.has(origin)) {
    return NextResponse.json(
      { error: "Forbidden: Origin mismatch" },
      { status: 403 }
    );
  }

  return null;
}

/**
 * API Route Handler で認証を要求するヘルパー。
 * CSRF保護（Originヘッダー検証）を内包する。
 *
 * 使い方:
 *   const { user, error } = await requireAuth(request);
 *   if (error) return error;
 *   // user は認証済み
 */
export async function requireAuth(request: Request): Promise<AuthSuccess | AuthFailure> {
  // CSRF チェック
  const csrfError = checkCsrf(request);
  if (csrfError) {
    return { user: null, supabase: null, error: csrfError };
  }

  let supabase: SsrSupabase;
  try {
    supabase = await createClient();
  } catch {
    return {
      user: null,
      supabase: null,
      error: NextResponse.json({ error: "Supabase not configured" }, { status: 503 }),
    };
  }

  const {
    data: { user },
    error: authError,
  } = await supabase.auth.getUser();

  if (authError || !user) {
    return {
      user: null,
      supabase: null,
      error: NextResponse.json({ error: "Unauthorized" }, { status: 401 }),
    };
  }

  return { user, supabase, error: null };
}

/**
 * 認証に加えてプランレベルを検証するヘルパー。
 *
 * profilesテーブルの plan カラムを参照し、requiredPlan 以上でなければ 403 を返す。
 *
 * 使い方:
 *   const { user, plan, error } = await requirePlan("pro");
 *   if (error) return error;
 *   // user は requiredPlan 以上のプランを持つ認証済みユーザー
 */
export async function requirePlan(
  requiredPlan: Plan,
  request: Request
): Promise<PlanSuccess | PlanFailure> {
  const authResult = await requireAuth(request);
  if (authResult.error) {
    return { user: null, supabase: null, plan: null, error: authResult.error };
  }
  const { user, supabase } = authResult;

  const { data: profile, error: profileError } = await supabase
    .from("profiles")
    .select("plan")
    .eq("id", user.id)
    .maybeSingle();

  if (profileError) {
    console.error("[requirePlan] Profile fetch error:", profileError.message);
    return {
      user: null,
      supabase: null,
      plan: null,
      error: NextResponse.json({ error: "Failed to verify plan" }, { status: 500 }),
    };
  }

  // Treat unknown/legacy plan strings as "free" instead of letting them
  // bypass the comparison below (undefined < n === false).
  const rawPlan = (profile?.plan as string | null) ?? "free";
  const userPlan: Plan = rawPlan in PLAN_ORDER ? (rawPlan as Plan) : "free";

  if (PLAN_ORDER[userPlan] < PLAN_ORDER[requiredPlan]) {
    return {
      user: null,
      supabase: null,
      plan: null,
      error: NextResponse.json(
        { error: `Plan upgrade required. This endpoint requires '${requiredPlan}' or higher.` },
        { status: 403 }
      ),
    };
  }

  return { user, supabase, plan: userPlan, error: null };
}
