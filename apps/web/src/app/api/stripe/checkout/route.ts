import { NextResponse } from "next/server";
import Stripe from "stripe";
import { applyRateLimit } from "@/lib/rate-limit";
import { requireAuth } from "@/lib/api-auth";

export const dynamic = "force-dynamic";

type Plan = "pro" | "business";
type Interval = "month" | "year";

interface CheckoutBody {
  plan: Plan;
  interval?: Interval;
}

// Price in cents (USD)
const PRICES: Record<Plan, Record<Interval, number>> = {
  pro: {
    month: 29900,  // $299
    year: 286900,  // $2,869
  },
  business: {
    month: 99900,  // $999
    year: 959000,  // $9,590
  },
};

const PLAN_NAMES: Record<Plan, string> = {
  pro: "FaultRay Pro",
  business: "FaultRay Business",
};

const TRIAL_DAYS: Record<Plan, number | undefined> = {
  pro: 14,
  business: undefined,
};

export async function POST(request: Request) {
  const limited = await applyRateLimit(request, { limit: 10, windowMs: 60_000 });
  if (limited) return limited;

  // Auth + CSRF gate (P1-2). Was using bare auth.getUser() without CSRF check.
  const { user, error: authError } = await requireAuth(request);
  if (authError) return authError;
  const userId = user.id;

  const secretKey = process.env.STRIPE_SECRET_KEY;
  if (!secretKey || secretKey === "sk_test_placeholder") {
    return NextResponse.json(
      { error: "Stripe is not configured. Please set STRIPE_SECRET_KEY." },
      { status: 503 }
    );
  }

  let body: Partial<CheckoutBody>;
  try {
    body = (await request.json()) as Partial<CheckoutBody>;
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const { plan, interval = "month" } = body;

  if (!plan || !["pro", "business"].includes(plan)) {
    return NextResponse.json(
      { error: "Invalid plan. Must be 'pro' or 'business'." },
      { status: 400 }
    );
  }

  if (!["month", "year"].includes(interval)) {
    return NextResponse.json(
      { error: "Invalid interval. Must be 'month' or 'year'." },
      { status: 400 }
    );
  }

  // APIPERF-05: Stripe API呼び出しにタイムアウトを設定（デフォルト80sを30sに短縮）
  const stripe = new Stripe(secretKey, { timeout: 30000 });

  // P2-1 (review-loop 2 + 3): success_url / cancel_url は server-side allowlist のみ。
  // 本番では NEXT_PUBLIC_SITE_URL が**設定 AND parse 可能**であることを要求。
  // malformed の場合に VERCEL_URL fallback すると preview deployment URL に
  // pin されてしまうため、production は厳格に弾く。
  // 非本番のみ VERCEL_URL fallback (server-only env、改竄不可) を許容。
  // Origin: ANY case で request.headers.get('origin') は使わない (P2-1 の核心)。
  //
  // NODE_ENV ではなく VERCEL_ENV で本番判定する (Codex P2): preview / staging
  // deployment は Next.js build 時に NODE_ENV='production' になるため、
  // NODE_ENV だけで isProduction 判定すると preview でも production 厳格パスを
  // 通り、NEXT_PUBLIC_SITE_URL 未設定の preview/staging で 503 になる。
  // VERCEL_ENV は production / preview / development のいずれかで明示的に区別可能。
  // VERCEL_ENV 未設定 (Vercel 外で動かしている self-host 等) では、過去互換のため
  // NODE_ENV='production' を本番扱いする。
  const vercelEnv = process.env.VERCEL_ENV;
  const isProduction = vercelEnv
    ? vercelEnv === "production"
    : process.env.NODE_ENV === "production";
  const siteUrl = process.env.NEXT_PUBLIC_SITE_URL;
  const vercelUrl = process.env.VERCEL_URL;

  function tryOrigin(value: string | null | undefined): string | null {
    if (!value) return null;
    try {
      return new URL(value).origin;
    } catch {
      return null;
    }
  }

  let origin: string | null = null;
  if (isProduction) {
    // Production: require valid NEXT_PUBLIC_SITE_URL, no fallback.
    if (!siteUrl) {
      console.error("[stripe/checkout] NEXT_PUBLIC_SITE_URL must be set in production");
      return NextResponse.json(
        { error: "Server configuration error. Please contact support." },
        { status: 503 }
      );
    }
    origin = tryOrigin(siteUrl);
    if (!origin) {
      console.error("[stripe/checkout] NEXT_PUBLIC_SITE_URL is malformed in production:", siteUrl);
      return NextResponse.json(
        { error: "Server configuration error. Please contact support." },
        { status: 503 }
      );
    }
  } else {
    // Non-production: NEXT_PUBLIC_SITE_URL → VERCEL_URL fallback chain.
    origin =
      tryOrigin(siteUrl) ??
      tryOrigin(vercelUrl ? `https://${vercelUrl}` : null);
    if (!origin) {
      console.error(
        "[stripe/checkout] no valid origin in non-prod (NEXT_PUBLIC_SITE_URL/VERCEL_URL both missing or malformed)"
      );
      return NextResponse.json(
        { error: "Server configuration error. Please contact support." },
        { status: 503 }
      );
    }
  }

  const unitAmount = PRICES[plan][interval];
  const trialDays = TRIAL_DAYS[plan];

  // #15: 冪等性キーで二重サブスクリプション防止
  // 時間バケット付きでexpire後の再チェックアウト時のStripe 400エラーを回避
  const hourBucket = Math.floor(Date.now() / 3600000);
  const idempotencyKey = `checkout-${userId}-${plan}-${interval}-${hourBucket}`;

  // #79 PR #102 Codex P1-A: 既存 stripe_customer_id を再利用する。これを渡さないと
  // Stripe は repeat checkout のたびに新規 customer を作成 → webhook の bootstrap で
  // profiles.stripe_customer_id ≠ 新 customer になり customer_mismatch で plan 更新が
  // skip される (legitimate な resubscribe / upgrade flow が silent に壊れる)。
  //
  // (Codex review-loop 2 P1-B2): lookup 失敗を silent fall-through させると、課金は
  // 通って plan 更新だけ落ちる "burn-without-credit" を再現してしまう。lookup が
  // できない = customer reuse 判定ができない = checkout を進めるべきでない。503 で
  // retry させ、ユーザーに明示的に再試行を促す。
  const supaUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const supaServiceKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!supaUrl || !supaServiceKey) {
    console.error("[stripe/checkout] Supabase admin not configured — refusing checkout to avoid customer_mismatch drop");
    return NextResponse.json(
      { error: "Server configuration error. Please contact support." },
      { status: 503 }
    );
  }
  let existingCustomerId: string | null = null;
  try {
    const { createClient: createAdminClient } = await import("@supabase/supabase-js");
    const adminSb = createAdminClient(supaUrl, supaServiceKey);
    const { data: profile, error: lookupError } = await adminSb
      .from("profiles")
      .select("stripe_customer_id")
      .eq("id", userId)
      .maybeSingle();
    if (lookupError) {
      throw new Error(lookupError.message);
    }
    existingCustomerId = (profile?.stripe_customer_id as string | null) ?? null;
  } catch (lookupErr) {
    // 503 で retry させる: silent fall-through (= 新規 customer 作成 → webhook
    // bootstrap で customer_mismatch → 200 ack drop) を排除する。
    console.error(
      "[stripe/checkout] profile lookup failed — refusing checkout:",
      lookupErr instanceof Error ? lookupErr.message : "unknown error"
    );
    return NextResponse.json(
      { error: "Service temporarily unavailable. Please try again in a moment." },
      { status: 503 }
    );
  }

  try {
    const session = await stripe.checkout.sessions.create(
      {
        mode: "subscription",
        // #79: 既存 customer を再利用 (repeat checkout で customer_mismatch を防ぐ)
        ...(existingCustomerId ? { customer: existingCustomerId } : {}),
        // #21: Checkout URL共有リスク軽減 — セッションを30分で失効させる
        // Stripeのデフォルトは24時間。URLが共有・漏洩した場合のリスクを最小化する。
        expires_at: Math.floor(Date.now() / 1000) + 1800,
        line_items: [
          {
            price_data: {
              currency: "usd",
              product_data: {
                name: PLAN_NAMES[plan],
                description: `FaultRay ${plan === "pro" ? "Pro" : "Business"} Plan — billed ${interval === "month" ? "monthly" : "annually"}`,
              },
              recurring: {
                interval: interval === "month" ? "month" : "year",
              },
              unit_amount: unitAmount,
            },
            quantity: 1,
          },
        ],
        subscription_data:
          trialDays !== undefined
            ? { trial_period_days: trialDays, metadata: { plan, user_id: userId ?? "" } }
            : { metadata: { plan, user_id: userId ?? "" } },
        success_url: `${origin}/settings?payment=success`,
        cancel_url: `${origin}/pricing`,
        metadata: {
          plan,
          interval,
          user_id: userId ?? "",
        },
      },
      { idempotencyKey }
    );

    return NextResponse.json({ url: session.url });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    console.error("[stripe/checkout] Error:", message);
    // Do not expose internal error details to clients
    return NextResponse.json({ error: "Failed to create checkout session. Please try again." }, { status: 500 });
  }
}
