import { createClient } from "@/lib/supabase/server";
import { NextResponse } from "next/server";
import type { User } from "@supabase/supabase-js";

type AuthSuccess = { user: User; error: null };
type AuthFailure = { user: null; error: NextResponse };

/** Plan hierarchy: free < pro < business */
export type Plan = "free" | "pro" | "business";

type PlanSuccess = { user: User; plan: Plan; error: null };
type PlanFailure = { user: null; plan: null; error: NextResponse };

const PLAN_ORDER: Record<Plan, number> = { free: 0, pro: 1, business: 2 };

/**
 * CSRF保護: リクエストのOriginヘッダーをNEXT_PUBLIC_SITE_URLと比較する。
 *
 * Stripe webhookおよびcronルート（/api/stripe/webhook, /api/cron/）は
 * OriginヘッダーがないためCSRFチェックをスキップする。
 *
 * @returns 403 Response if Origin is invalid, null if OK
 */
function checkCsrf(request: Request): NextResponse | null {
  const url = new URL(request.url);
  // stripe webhook と cron はサーバー間リクエストのためOriginなし — スキップ
  const skipPaths = ["/api/stripe/webhook", "/api/cron/"];
  if (skipPaths.some((p) => url.pathname.startsWith(p))) {
    return null;
  }

  const origin = request.headers.get("origin");
  // Originヘッダーなし（サーバー間・curlなど）は通過させる
  if (!origin) return null;

  const siteUrl = process.env.NEXT_PUBLIC_SITE_URL ?? "https://faultray.com";
  let expectedOrigin: string;
  try {
    expectedOrigin = new URL(siteUrl).origin;
  } catch {
    // NEXT_PUBLIC_SITE_URL が不正な場合はスキップ（設定ミス時に全リクエストを弾かないよう）
    return null;
  }

  if (origin !== expectedOrigin) {
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
    return { user: null, error: csrfError };
  }

  let supabase: Awaited<ReturnType<typeof createClient>>;
  try {
    supabase = await createClient();
  } catch {
    return {
      user: null,
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
      error: NextResponse.json({ error: "Unauthorized" }, { status: 401 }),
    };
  }

  return { user, error: null };
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
    return { user: null, plan: null, error: authResult.error };
  }
  const { user } = authResult;

  let supabase: Awaited<ReturnType<typeof createClient>>;
  try {
    supabase = await createClient();
  } catch {
    return {
      user: null,
      plan: null,
      error: NextResponse.json({ error: "Supabase not configured" }, { status: 503 }),
    };
  }

  const { data: profile, error: profileError } = await supabase
    .from("profiles")
    .select("plan")
    .eq("id", user.id)
    .maybeSingle();

  if (profileError) {
    console.error("[requirePlan] Profile fetch error:", profileError.message);
    return {
      user: null,
      plan: null,
      error: NextResponse.json({ error: "Failed to verify plan" }, { status: 500 }),
    };
  }

  const userPlan: Plan = (profile?.plan as Plan | null) ?? "free";

  if (PLAN_ORDER[userPlan] < PLAN_ORDER[requiredPlan]) {
    return {
      user: null,
      plan: null,
      error: NextResponse.json(
        { error: `Plan upgrade required. This endpoint requires '${requiredPlan}' or higher.` },
        { status: 403 }
      ),
    };
  }

  return { user, plan: userPlan, error: null };
}
