import { NextResponse } from "next/server";
import Stripe from "stripe";
import { applyRateLimit } from "@/lib/rate-limit";
import type { PlanTier } from "@/lib/types";

// Stripe webhook handler must read the raw body
export const dynamic = "force-dynamic";

/**
 * Extract the customer id from an event object whose `customer` field may be
 * a string id, an expanded object, or null (one-off invoices). Returning
 * null lets handlers ack-without-action instead of looking up
 * `stripe_customer_id = "[object Object]"` / throwing and forcing Stripe to
 * retry an event that can never succeed.
 */
function customerIdFrom(obj: {
  customer?: string | { id: string } | null;
}): string | null {
  const c = obj.customer;
  if (typeof c === "string") return c;
  if (c && typeof c === "object" && typeof c.id === "string") return c.id;
  return null;
}

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

/**
 * #112: ``plan === null`` means "could not resolve a plan from Stripe — keep
 * whatever is currently in the profile". We must never substitute a paid tier
 * as a fallback because that silently rewrites the customer's entitlement.
 */
async function updateUserPlan(
  userId: string,
  plan: PlanTier | null,
  subscriptionStatus?: string
): Promise<void> {
  const supabase = await getSupabaseAdmin();
  const updatePayload: Record<string, unknown> = {};
  if (plan !== null) {
    updatePayload.plan = plan;
  }
  if (subscriptionStatus !== undefined) {
    updatePayload.subscription_status = subscriptionStatus;
  }
  if (Object.keys(updatePayload).length === 0) {
    // Nothing to write (no plan change, no status change).
    return;
  }
  const { error } = await supabase
    .from("profiles")
    .update(updatePayload)
    .eq("id", userId);
  if (error) {
    throw new Error(`Failed to update profile: ${error.message}`);
  }
}

// #79 P1: customer_id source-of-truth resolution.
// metadata.user_id は forge 可能 (Stripe Checkout 作成時に攻撃者が任意設定可能)
// なため、subscription / invoice 系の event では customerId → profiles の lookup
// を唯一の真実源とする。bootstrap (checkout.session.completed) のみ metadata を
// 使うが、cross-check で同じ userId に異なる customer が紐づくのを reject する。
async function resolveUserByCustomerId(
  customerId: string
): Promise<string | null> {
  const supabase = await getSupabaseAdmin();
  const { data, error } = await supabase
    .from("profiles")
    .select("id")
    .eq("stripe_customer_id", customerId)
    .maybeSingle();
  if (error) {
    throw new Error(`Customer lookup failed: ${error.message}`);
  }
  return (data?.id as string | undefined) ?? null;
}

async function updateUserByCustomerId(
  customerId: string,
  plan: PlanTier | null,
  subscriptionStatus?: string
): Promise<void> {
  const userId = await resolveUserByCustomerId(customerId);
  if (!userId) {
    // #81 (P2-3): silent warn + return は Stripe retry を停止させ event を永久消失
    // させるため throw に変更。`profiles.stripe_customer_id` が未 bootstrap の
    // ケースでは Stripe が retry → checkout.session.completed が先に処理されれば
    // 次回 retry で resolve できる。永久 unmapped なら最終的に Stripe の retry
    // 期限 (3日) で諦めるが、その間に operator が DB を確認して fix できる。
    throw new Error(
      `Customer not mapped to a profile (customer=${customerId}). ` +
        `bootstrap (checkout.session.completed) で stripe_customer_id が未 persist。`
    );
  }
  await updateUserPlan(userId, plan, subscriptionStatus);
}

// #79 P1: bootstrap path専用。`checkout.session.completed` で初めて customerId が
// profile に紐づく時に呼ぶ。
//   - profile が存在しない → profile_not_found (500 retry)
//   - profile.stripe_customer_id が既存で event の customerId と異なる → customer_mismatch
//     (attack indicator: 攻撃者が他人の userId を metadata.user_id に詰めた可能性)
//   - profile.stripe_customer_id が NULL → 新規 persist
//   - 一致 → no-op
type BootstrapResult =
  | { ok: true }
  | { ok: false; reason: "profile_not_found" | "customer_mismatch" };

async function bootstrapUserCustomer(
  userId: string,
  customerId: string
): Promise<BootstrapResult> {
  const supabase = await getSupabaseAdmin();
  const { data: profile, error } = await supabase
    .from("profiles")
    .select("id, stripe_customer_id")
    .eq("id", userId)
    .maybeSingle();
  if (error) {
    throw new Error(`Bootstrap profile lookup failed: ${error.message}`);
  }
  if (!profile) {
    return { ok: false, reason: "profile_not_found" };
  }
  const existingCustomer = (profile.stripe_customer_id as string | null) ?? null;
  if (existingCustomer && existingCustomer !== customerId) {
    return { ok: false, reason: "customer_mismatch" };
  }
  if (existingCustomer === null) {
    const { error: updateError } = await supabase
      .from("profiles")
      .update({ stripe_customer_id: customerId })
      .eq("id", userId);
    if (updateError) {
      throw new Error(
        `Failed to persist stripe_customer_id: ${updateError.message}`
      );
    }
  }
  return { ok: true };
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
      // #79 P1: 唯一 metadata.user_id を信用する bootstrap path。bootstrapUserCustomer
      // で cross-check し、attack signature (customer_mismatch) は plan 変更を skip。
      case "checkout.session.completed": {
        const session = event.data.object as Stripe.Checkout.Session;
        const userId = session.metadata?.user_id;
        const plan = session.metadata?.plan as PlanTier | undefined;
        const customerId =
          typeof session.customer === "string" ? session.customer : null;

        if (!userId || !plan || !customerId) {
          console.warn(
            `[stripe/webhook] checkout.session.completed: missing fields ` +
              `(user_id=${userId ?? "null"} plan=${plan ?? "null"} customer=${customerId ?? "null"})`
          );
          break;
        }
        if (plan !== "starter" && plan !== "pro" && plan !== "business") {
          console.warn(
            `[stripe/webhook] checkout.session.completed: invalid plan=${plan} (user=${userId})`
          );
          break;
        }
        const bootstrap = await bootstrapUserCustomer(userId, customerId);
        if (!bootstrap.ok) {
          if (bootstrap.reason === "customer_mismatch") {
            // #79 attack signature: 既存 profile.stripe_customer_id と event の
            // customerId が違う = 攻撃者が他人の user_id を metadata に詰めた可能性。
            // 200 ack だけ返し、Stripe retry で同じ攻撃を増幅させない。
            console.error(
              `[stripe/webhook] checkout.session.completed: customer_mismatch ` +
                `(user_id=${userId} got_customer=${customerId}). Possible metadata forgery — refusing to mutate plan.`
            );
            break;
          }
          // profile_not_found: race (auth.users → profiles trigger 未走) か
          // metadata.user_id 偽装。500 で Stripe retry させる。
          throw new Error(
            `Bootstrap failed: ${bootstrap.reason} (user_id=${userId} customer=${customerId})`
          );
        }
        await updateUserPlan(userId, plan, "active");
        console.info(
          `[stripe/webhook] checkout.session.completed: user=${userId} customer=${customerId} plan=${plan}`
        );
        break;
      }

      // ── Subscription updated: plan change or renewal ─────────────────────
      // #79 P1: customer_id source-of-truth で resolve。metadata.user_id は信用しない。
      case "customer.subscription.updated": {
        const subscription = event.data.object as Stripe.Subscription;
        const customerId = customerIdFrom(subscription);
        if (!customerId) {
          console.warn(
            "[stripe/webhook] customer.subscription.updated: no customer id on event — ack without action"
          );
          break;
        }
        const status = subscription.status; // active | past_due | canceled | ...

        // Determine plan from first price item
        const priceId = subscription.items.data[0]?.price?.id;
        const plan = priceId ? planTierFromPriceId(priceId) : null;

        const resolvedPlan: PlanTier =
          (status === "active" || status === "trialing") && plan ? plan : "free";

        await updateUserByCustomerId(customerId, resolvedPlan, status);
        console.info(
          `[stripe/webhook] customer.subscription.updated: customer=${customerId} status=${status} plan=${resolvedPlan}`
        );
        break;
      }

      // ── Subscription deleted: cancel or non-renewal ───────────────────────
      // #79 P1: customer_id source-of-truth で resolve。metadata.user_id は信用しない。
      // (Codex review-loop 3 P2): /api/account/delete は profile を先に消してから
      // Stripe subscriptions を cancel する設計のため、その flow の deleted event は
      // profile が存在しない状態で到達する (= 通常 flow)。500 retry を 3 日間続ける
      // のは ops noise なので、**deleted event のみ** profile not mapped を 200 ack
      // で受容する。攻撃者目線では既に削除済 customer の deleted event を発火させても
      // 何も起こせないため、リスクなし。
      case "customer.subscription.deleted": {
        const subscription = event.data.object as Stripe.Subscription;
        const customerId = customerIdFrom(subscription);
        if (!customerId) {
          console.warn(
            "[stripe/webhook] customer.subscription.deleted: no customer id on event — ack without action"
          );
          break;
        }

        const userId = await resolveUserByCustomerId(customerId);
        if (!userId) {
          console.info(
            `[stripe/webhook] customer.subscription.deleted: customer=${customerId} ` +
              `not mapped — likely account/delete flow, ack-ing without mutation.`
          );
          break;
        }
        await updateUserPlan(userId, "free", "canceled");
        console.info(
          `[stripe/webhook] customer.subscription.deleted: customer=${customerId} user=${userId}`
        );
        break;
      }

      // ── Payment failed: notify and mark past_due ──────────────────────────
      case "invoice.payment_failed": {
        const invoice = event.data.object as Stripe.Invoice;
        const customerId = customerIdFrom(invoice);
        if (!customerId) {
          console.warn(
            "[stripe/webhook] invoice.payment_failed: no customer id on event — ack without action"
          );
          break;
        }
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

          // #112: never default to a paid tier here. When subscription /
          // priceId resolution fails, keep the existing plan (null) and only
          // flip status to past_due. Transient Stripe retrieve errors are
          // re-thrown so Stripe retries, instead of silently downgrading.
          let resolvedPlan: PlanTier | null = null;
          if (subscriptionId) {
            try {
              const subscription = await stripe.subscriptions.retrieve(subscriptionId);
              const priceId = subscription.items.data[0]?.price?.id;
              resolvedPlan = priceId ? planTierFromPriceId(priceId) : null;
              if (resolvedPlan === null) {
                console.warn(
                  `[stripe/webhook] payment_failed: unresolved plan for priceId=${priceId ?? "(missing)"}; preserving existing plan`
                );
              }
            } catch (err) {
              console.error("[stripe/webhook] Failed to retrieve subscription for payment_failed:", err);
              throw err;
            }
          }

          await updateUserByCustomerId(customerId, resolvedPlan, "past_due");
          // TODO: trigger email notification via RETAIN-01 email system when implemented
        }
        break;
      }

      // ── Payment succeeded: ensure status is active ───────────────────────
      // #79 P1: customer_id source-of-truth で resolve。metadata.user_id は信用しない。
      case "invoice.payment_succeeded": {
        const invoice = event.data.object as Stripe.Invoice;
        const customerId = customerIdFrom(invoice);
        if (!customerId) {
          console.warn(
            "[stripe/webhook] invoice.payment_succeeded: no customer id on event — ack without action"
          );
          break;
        }
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
          // #112: don't fall back to "pro" — that silently rewrites the
          // entitlement of starter/business customers whose price ID isn't in
          // our local mapping. Preserve the existing plan instead and only flip
          // status to "active". Operators can fix the mapping and replay.
          const resolvedPlan: PlanTier | null = plan;
          if (resolvedPlan === null) {
            console.warn(
              `[stripe/webhook] payment_succeeded: unresolved plan for priceId=${priceId ?? "(missing)"}; preserving existing plan`
            );
          }
          await updateUserByCustomerId(customerId, resolvedPlan, "active");
          console.info(
            `[stripe/webhook] invoice.payment_succeeded: customer=${customerId} plan=${resolvedPlan ?? "(preserved)"}`
          );
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
