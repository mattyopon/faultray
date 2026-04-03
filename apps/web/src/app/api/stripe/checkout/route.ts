import { NextResponse } from "next/server";
import Stripe from "stripe";

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

  // API-01: 認証必須 — ログインユーザーのみチェックアウト可能
  const { createClient } = await import("@/lib/supabase/server");
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  const userId = user.id;

  // APIPERF-05: Stripe API呼び出しにタイムアウトを設定（デフォルト80sを30sに短縮）
  const stripe = new Stripe(secretKey, { timeout: 30000 });

  const origin =
    request.headers.get("origin") ??
    process.env.NEXT_PUBLIC_SITE_URL ??
    "https://faultray.com";

  const unitAmount = PRICES[plan][interval];
  const trialDays = TRIAL_DAYS[plan];

  try {
    const session = await stripe.checkout.sessions.create({
      mode: "subscription",
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
    });

    return NextResponse.json({ url: session.url });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    console.error("[stripe/checkout] Error:", message);
    // Do not expose internal error details to clients
    return NextResponse.json({ error: "Failed to create checkout session. Please try again." }, { status: 500 });
  }
}
