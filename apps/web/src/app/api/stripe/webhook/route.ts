import { NextResponse } from "next/server";
import Stripe from "stripe";
import { applyRateLimit } from "@/lib/rate-limit";

// Stripe webhook handler must read the raw body
export const dynamic = "force-dynamic";

type PlanTier = "free" | "starter" | "pro" | "business";

/**
 * Stripe Invoice extension (#31):
 * - `parent.subscription_details.subscription` exists on Stripe API v2+
 *   invoice objects where the invoice parents a subscription. The
 *   official Stripe TS type does not yet expose this nested field.
 * - `subscription` is the legacy top-level field (Stripe API v1 /
 *   historical invoices) still occasionally present on retrieved objects.
 *
 * We extract a `subscriptionId` via a single narrow helper instead of
 * scattering `as any` casts across the file.
 */
type InvoiceWithSubscription = Stripe.Invoice & {
  parent?: {
    subscription_details?: {
      subscription?: string | null;
    } | null;
  } | null;
  subscription?: string | null;
};

function extractSubscriptionId(invoice: Stripe.Invoice): string | null {
  const inv = invoice as InvoiceWithSubscription;
  return inv.parent?.subscription_details?.subscription ?? inv.subscription ?? null;
}

function planTierFromPriceId(priceId: string): PlanTier | null {
  const starterPriceIds = (process.env.STRIPE_STARTER_PRICE_IDS || "").split(",").filter(Boolean);
  const proPriceIds = (process.env.STRIPE_PRO_PRICE_IDS || "").split(",").filter(Boolean);
  const businessPriceIds = (process.env.STRIPE_BUSINESS_PRICE_IDS || "").split(",").filter(Boolean);
  if (starterPriceIds.includes(priceId)) return "starter";
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
  const limited = await applyRateLimit(request, { limit: 60, windowMs: 60_000 });
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

  // P1-4 (PR #89 → review-loop 1): 2-state idempotency ledger.
  // Codex review (2026-04-30) の P1 指摘:
  //   "INSERT-before-side-effect では updateUserPlan() throw 時に event が
  //    永久 dedup → DB inconsistent。claim/processed の 2-state ledger に
  //    すべき"
  //
  // 動作:
  //   1) INSERT (event_id, status='processing') ON CONFLICT DO NOTHING
  //   2) INSERT 成功 (= 初到達) → 通常処理 → 成功時 UPDATE status='processed'
  //      side effect 失敗時は UPDATE status='failed' して Stripe の retry で
  //      reclaim させる (500 return)
  //   3) INSERT 衝突 (= 重複) → 既存 status check:
  //        processed  → 200 duplicate (即返却)
  //        processing → 503 (Stripe retry 駆動)。worker crash で永久 'processing'
  //                     残留時に 2xx を返すと Stripe が retry を停止し billing が
  //                     永久未適用になる (Codex P1, Devin BUG)。
  //        failed     → 再処理 (UPDATE status='processing' に戻して続行)
  let dedupeAdmin: Awaited<ReturnType<typeof getSupabaseAdmin>>;
  try {
    dedupeAdmin = await getSupabaseAdmin();
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    console.error("[stripe/webhook] Admin client init failed:", message);
    return NextResponse.json(
      { error: "Idempotency guard failure" },
      { status: 500 }
    );
  }

  const eventCustomerId =
    typeof (event.data.object as { customer?: unknown })?.customer === "string"
      ? ((event.data.object as { customer?: string }).customer ?? null)
      : null;

  let claimedNew = false;
  {
    const { error: insertError } = await dedupeAdmin
      .from("processed_stripe_events")
      .insert({
        event_id: event.id,
        event_type: event.type,
        customer_id: eventCustomerId,
        status: "processing",
      });

    if (!insertError) {
      claimedNew = true;
    } else {
      // 23505 = postgres unique_violation
      const code = (insertError as { code?: string }).code;
      if (code !== "23505") {
        console.error(
          "[stripe/webhook] processed_stripe_events insert failed:",
          insertError.message
        );
        return NextResponse.json(
          { error: "Idempotency ledger write failed" },
          { status: 500 }
        );
      }

      // Conflict path: inspect existing row and decide.
      const { data: existing, error: selectError } = await dedupeAdmin
        .from("processed_stripe_events")
        .select("status, updated_at")
        .eq("event_id", event.id)
        .maybeSingle();

      if (selectError || !existing) {
        console.error(
          "[stripe/webhook] failed to read existing event row:",
          selectError?.message
        );
        return NextResponse.json(
          { error: "Idempotency ledger read failed" },
          { status: 500 }
        );
      }

      if (existing.status === "processed") {
        return NextResponse.json({ received: true, duplicate: true });
      }
      if (existing.status === "processing") {
        // Stale-lock takeover (review-loop 3, CodeRabbit Major + Codex P1):
        // worker crash / serverless timeout で 'processing' 残留時、503 だけ
        // 返していると Stripe retry が無限に空回りして event は永久 stuck。
        // updated_at が STALE_PROCESSING_MS 以上経過していれば前 worker は
        // 死んだとみなし、現 worker が reclaim する (status='processing' のまま
        // updated_at だけ bump して所有権を奪う)。
        // 同条件 + .eq("status", "processing") + .lt("updated_at", cutoff) で
        // race 安全 (2 workers が同時に試みても 1 件しか update できない)。
        const STALE_PROCESSING_MS = 5 * 60_000; // 5 minutes
        const staleCutoff = new Date(
          Date.now() - STALE_PROCESSING_MS
        ).toISOString();
        const { data: reclaimedStale, error: reclaimStaleError } =
          await dedupeAdmin
            .from("processed_stripe_events")
            .update({ status: "processing", last_error: null })
            .eq("event_id", event.id)
            .eq("status", "processing")
            .lt("updated_at", staleCutoff)
            .select("event_id");
        if (reclaimStaleError) {
          console.error(
            "[stripe/webhook] stale 'processing' reclaim failed:",
            reclaimStaleError.message
          );
          return NextResponse.json(
            { error: "Idempotency ledger stale-reclaim failed" },
            { status: 500 }
          );
        }
        if (reclaimedStale && reclaimedStale.length > 0) {
          console.warn(
            `[stripe/webhook] reclaimed stale 'processing' event ${event.id} ` +
              `(>${STALE_PROCESSING_MS / 60_000}min old)`
          );
          claimedNew = true;
        } else {
          // Active worker is still within the freshness window — let Stripe
          // retry. 503 keeps Stripe retrying (2xx would stop retries; see
          // Codex P1 / Devin BUG fixed in review-loop 3 commit 3cae293).
          return NextResponse.json(
            { received: false, status: "in_progress" },
            { status: 503 }
          );
        }
      } else if (existing.status === "failed") {
        // status === 'failed' → re-claim by flipping back to 'processing'.
        // (review-loop 2, P1) .select() で affected row 数を確認し、
        // 同時 retry が 2件 'failed' を見て両方 reclaim を試みた race を防ぐ。
        // 1件だけが update できる (もう1件は 0 rows = 別 worker が先に reclaim 済)。
        //
        // (review-loop 5, CodeRabbit Major + Codex P1) この block を else if で
        // 囲むのが必須。'processing' branch の stale takeover が成功した場合に
        // ここに fall through すると、`.eq("status", "failed")` が 0 rows match
        // (実際は既に 'processing' になっている) → 503 return → 取得した claim を
        // 投げ捨てて side effect が永久未実行になる、という重大バグを防ぐ。
        const { data: reclaimed, error: reclaimError } = await dedupeAdmin
          .from("processed_stripe_events")
          .update({ status: "processing", last_error: null })
          .eq("event_id", event.id)
          .eq("status", "failed")
          .select("event_id");
        if (reclaimError) {
          console.error(
            "[stripe/webhook] failed to re-claim failed event:",
            reclaimError.message
          );
          return NextResponse.json(
            { error: "Idempotency ledger reclaim failed" },
            { status: 500 }
          );
        }
        if (!reclaimed || reclaimed.length === 0) {
          // Another worker reclaimed in the meantime — return non-2xx so Stripe
          // retries (same reasoning as the 'processing' branch above). The
          // other worker may also crash before flipping status, so we cannot
          // assume the event will be processed without further retries.
          return NextResponse.json(
            { received: false, status: "in_progress" },
            { status: 503 }
          );
        }
        claimedNew = true;
      } else {
        // Defensive: unknown status value should not happen given the CHECK
        // constraint on processed_stripe_events.status, but if a future
        // migration adds a new state we want explicit failure rather than
        // silent skip.
        console.error(
          `[stripe/webhook] unexpected processed_stripe_events.status=${existing.status} for event ${event.id}`
        );
        return NextResponse.json(
          { error: "Idempotency ledger unknown state" },
          { status: 500 }
        );
      }
    }
  }
  // claimedNew === true: we own this event; must mark processed/failed before return.

  try {
    switch (event.type) {
      // ── Checkout completed: new subscription starts ──────────────────────
      case "checkout.session.completed": {
        const session = event.data.object as Stripe.Checkout.Session;
        const userId = session.metadata?.user_id;
        const plan = session.metadata?.plan as PlanTier | undefined;

        if (userId && plan && (plan === "starter" || plan === "pro" || plan === "business")) {
          await updateUserPlan(userId, plan, "active");
          console.info(`[stripe/webhook] checkout.session.completed: user=${userId} plan=${plan}`);
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
        console.info(`[stripe/webhook] customer.subscription.updated: customer=${customerId} status=${status} plan=${resolvedPlan}`);
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
        console.info(`[stripe/webhook] customer.subscription.deleted: customer=${customerId} user=${userId}`);
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
          // NOTE (#31): replaced `as any` cast with InvoiceWithSubscription.
          const subscriptionId: string | null = extractSubscriptionId(invoice);

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
        // Extract subscription id from parent (Stripe API v2+) or legacy field.
        // NOTE (#31): replaced `as any` cast with InvoiceWithSubscription.
        const subscriptionId: string | null = extractSubscriptionId(invoice);
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
          console.info(`[stripe/webhook] invoice.payment_succeeded: customer=${customerId} plan=${resolvedPlan}`);
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
    // 2-state ledger: mark as 'failed' so Stripe's next retry can reclaim
    // and re-run side effects. (013 + 014)
    const { error: markFailedError } = await dedupeAdmin
      .from("processed_stripe_events")
      .update({ status: "failed", last_error: message })
      .eq("event_id", event.id);
    if (markFailedError) {
      console.error(
        "[stripe/webhook] failed to mark event failed:",
        markFailedError.message
      );
    }
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }

  // Success path: flip claim from 'processing' to 'processed'.
  // Must happen AFTER all side effects committed.
  if (claimedNew) {
    const { error: markError } = await dedupeAdmin
      .from("processed_stripe_events")
      .update({ status: "processed" })
      .eq("event_id", event.id);
    if (markError) {
      // Side effects already committed; we cannot 500 here (would force
      // Stripe to retry and double-apply). Log and continue.
      console.error(
        "[stripe/webhook] failed to mark event processed:",
        markError.message
      );
    }
  }

  return NextResponse.json({ received: true });
}
