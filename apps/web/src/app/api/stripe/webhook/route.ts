import { NextResponse } from "next/server";
import Stripe from "stripe";
import { applyRateLimit } from "@/lib/rate-limit";

// Stripe webhook handler must read the raw body
export const dynamic = "force-dynamic";

type PlanTier = "free" | "pro" | "business";

function planTierFromPriceId(priceId: string): PlanTier | null {
  const proPriceIds = (process.env.STRIPE_PRO_PRICE_IDS || "").split(",").filter(Boolean);
  const businessPriceIds = (process.env.STRIPE_BUSINESS_PRICE_IDS || "").split(",").filter(Boolean);
  if (proPriceIds.includes(priceId)) return "pro";
  if (businessPriceIds.includes(priceId)) return "business";
  return null;
}

async function getSupabaseAdmin() {
  const { createClient } = await import("@supabase/supabase-js");
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const serviceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !serviceRoleKey) {
    throw new Error("Supabase service role key not configured");
  }
  return createClient(url, serviceRoleKey);
}

async function updateUserPlan(userId: string, plan: PlanTier, subscriptionStatus?: string): Promise<void> {
  const supabase = await getSupabaseAdmin();
  const updatePayload: Record<string, unknown> = { plan };
  if (subscriptionStatus !== undefined) {
    updatePayload.subscription_status = subscriptionStatus;
  }
  const { error } = await supabase
    .from("profiles")
    .update(updatePayload)
    .eq("id", userId);
  if (error) {
    throw new Error(`Failed to update profile: ${error.message}`);
  }
}

async function updateUserByCustomerId(
  customerId: string,
  plan: PlanTier,
  subscriptionStatus?: string
): Promise<void> {
  const supabase = await getSupabaseAdmin();
  const { data: profile, error: lookupError } = await supabase
    .from("profiles")
    .select("id")
    .eq("stripe_customer_id", customerId)
    .maybeSingle();
  if (lookupError || !profile) {
    console.warn(`[stripe/webhook] No profile found for customer ${customerId}`);
    return;
  }
  await updateUserPlan(profile.id as string, plan, subscriptionStatus);
}

export async function POST(request: Request) {
  // Defense-in-depth: generous limit to allow Stripe retries
  const limited = applyRateLimit(request, { limit: 60, windowMs: 60_000 });
  if (limited) return limited;

  const secretKey = process.env.STRIPE_SECRET_KEY;
  const webhookSecret = process.env.STRIPE_WEBHOOK_SECRET;

  if (
    !secretKey ||
    secretKey === "sk_test_placeholder" ||
    !webhookSecret ||
    webhookSecret === "whsec_placeholder"
  ) {
    return NextResponse.json(
      { error: "Stripe webhook not configured" },
      { status: 503 }
    );
  }

  const signature = request.headers.get("stripe-signature");
  if (!signature) {
    return NextResponse.json({ error: "Missing stripe-signature header" }, { status: 400 });
  }

  let rawBody: string;
  try {
    rawBody = await request.text();
  } catch {
    return NextResponse.json({ error: "Failed to read request body" }, { status: 400 });
  }

  // APIPERF-05: Stripe APIタイムアウト設定
  const stripe = new Stripe(secretKey, { timeout: 30000 });

  let event: Stripe.Event;
  try {
    event = stripe.webhooks.constructEvent(rawBody, signature, webhookSecret);
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    console.error("[stripe/webhook] Signature verification failed:", message);
    // Do not expose verification details to callers
    return NextResponse.json({ error: "Webhook signature verification failed" }, { status: 400 });
  }

  try {
    switch (event.type) {
      // ── Checkout completed: new subscription starts ──────────────────────
      case "checkout.session.completed": {
        const session = event.data.object as Stripe.Checkout.Session;
        const userId = session.metadata?.user_id;
        const plan = session.metadata?.plan as PlanTier | undefined;

        if (userId && plan && (plan === "pro" || plan === "business")) {
          await updateUserPlan(userId, plan, "active");
          console.log(`[stripe/webhook] checkout.session.completed: user=${userId} plan=${plan}`);
        }
        break;
      }

      // ── Subscription updated: plan change or renewal ─────────────────────
      case "customer.subscription.updated": {
        const subscription = event.data.object as Stripe.Subscription;
        const customerId = subscription.customer as string;
        const userId = subscription.metadata?.user_id;
        const status = subscription.status; // active | past_due | canceled | ...

        // Determine plan from first price item
        const priceId = subscription.items.data[0]?.price?.id;
        const plan = priceId ? planTierFromPriceId(priceId) : null;

        const resolvedPlan: PlanTier = (status === "active" || status === "trialing") && plan
          ? plan
          : "free";

        if (userId) {
          await updateUserPlan(userId, resolvedPlan, status);
        } else {
          await updateUserByCustomerId(customerId, resolvedPlan, status);
        }
        console.log(`[stripe/webhook] customer.subscription.updated: customer=${customerId} status=${status} plan=${resolvedPlan}`);
        break;
      }

      // ── Subscription deleted: cancel or non-renewal ───────────────────────
      case "customer.subscription.deleted": {
        const subscription = event.data.object as Stripe.Subscription;
        const customerId = subscription.customer as string;
        const userId = subscription.metadata?.user_id;

        if (userId) {
          await updateUserPlan(userId, "free", "canceled");
        } else {
          await updateUserByCustomerId(customerId, "free", "canceled");
        }
        console.log(`[stripe/webhook] customer.subscription.deleted: customer=${customerId} user=${userId}`);
        break;
      }

      // ── Payment failed: notify and mark past_due ──────────────────────────
      case "invoice.payment_failed": {
        const invoice = event.data.object as Stripe.Invoice;
        const customerId = invoice.customer as string;
        const attemptCount = invoice.attempt_count ?? 1;

        console.warn(
          `[stripe/webhook] invoice.payment_failed: customer=${customerId} attempt=${attemptCount}`
        );

        // After 3 failed attempts Stripe will cancel the subscription via
        // customer.subscription.deleted; here we mark past_due early so the
        // UI can surface a payment-update banner without immediately revoking access.
        if (attemptCount >= 2) {
          // planをpriceIdから解決する。subscriptionが取得できない場合は
          // 既存のplanを維持するためupdateUserByCustomerIdのplan引数は使わず、
          // subscription取得後に実際のpriceIdからplanを決定する。
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          const invoiceAny = invoice as any;
          const subscriptionId: string | null =
            invoiceAny.parent?.subscription_details?.subscription ??
            invoiceAny.subscription ??
            null;

          let resolvedPlan: PlanTier = "pro"; // fallback
          if (subscriptionId) {
            try {
              const subscription = await stripe.subscriptions.retrieve(subscriptionId);
              const priceId = subscription.items.data[0]?.price?.id;
              resolvedPlan = (priceId ? planTierFromPriceId(priceId) : null) ?? "pro";
            } catch (err) {
              console.error("[stripe/webhook] Failed to retrieve subscription for payment_failed:", err);
            }
          }

          await updateUserByCustomerId(customerId, resolvedPlan, "past_due");
          // TODO: trigger email notification via RETAIN-01 email system when implemented
        }
        break;
      }

      // ── Payment succeeded: ensure status is active ───────────────────────
      case "invoice.payment_succeeded": {
        const invoice = event.data.object as Stripe.Invoice;
        const customerId = invoice.customer as string;
        // Extract subscription id from parent (Stripe API v2+) or legacy field
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const invoiceAny = invoice as any;
        const subscriptionId: string | null =
          invoiceAny.parent?.subscription_details?.subscription ??
          invoiceAny.subscription ??
          null;
        // Only act on subscription invoices (not one-time charges)
        if (subscriptionId) {
          // Retrieve subscription to determine plan
          const subscription = await stripe.subscriptions.retrieve(
            subscriptionId
          );
          const priceId = subscription.items.data[0]?.price?.id;
          const plan = priceId ? planTierFromPriceId(priceId) : null;
          const resolvedPlan: PlanTier = plan ?? "pro";
          const userId = subscription.metadata?.user_id;
          if (userId) {
            await updateUserPlan(userId, resolvedPlan, "active");
          } else {
            await updateUserByCustomerId(customerId, resolvedPlan, "active");
          }
          console.log(`[stripe/webhook] invoice.payment_succeeded: customer=${customerId} plan=${resolvedPlan}`);
        }
        break;
      }

      default:
        // Unhandled event type — acknowledge receipt without action
        break;
    }
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    console.error(`[stripe/webhook] Error handling event ${event.type}:`, message);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }

  return NextResponse.json({ received: true });
}
