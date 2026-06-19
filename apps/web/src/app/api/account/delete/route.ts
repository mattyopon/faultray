/**
 * EXPORT-01: GDPR-compliant account deletion endpoint.
 *
 * Deletes or anonymizes all user data from Supabase then removes the
 * auth.users record so the user can no longer log in.
 * Also cancels any active Stripe subscriptions to prevent continued billing.
 *
 * Requires: authenticated session (via Supabase SSR cookie).
 */
import { NextResponse } from "next/server";
import { applyRateLimit } from "@/lib/rate-limit";
import { requireAuth } from "@/lib/api-auth";
import Stripe from "stripe";

export const dynamic = "force-dynamic";

export async function DELETE(request: Request) {
  const limited = await applyRateLimit(request, { limit: 5, windowMs: 60_000 });
  if (limited) return limited;

  // Auth + CSRF gate. CSRF protection is critical here: account deletion is
  // irreversible, so a CSRF-induced DELETE from another origin would be
  // catastrophic. requireAuth runs checkCsrf() before reading session.
  const { user, error: authError } = await requireAuth(request);
  if (authError) return authError;

  // Parse optional confirmation body
  let body: { confirm?: unknown } = {};
  try {
    body = (await request.json()) as { confirm?: unknown };
  } catch {
    // No body is fine; we already authenticated above
  }

  // SEC (U16): require the strict boolean `true`. `!body.confirm` accepted any
  // truthy value (e.g. {"confirm": 1} or {"confirm": "x"}) → type-confusion that
  // could trigger an irreversible delete with an unintended payload.
  if (body.confirm !== true) {
    return NextResponse.json(
      { error: "Confirmation required. Send { \"confirm\": true } in the request body." },
      { status: 400 }
    );
  }

  const userId = user.id;

  // Use service-role client for privileged operations
  const { createClient: createAdminClient } = await import("@supabase/supabase-js");
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const serviceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY;

  if (!supabaseUrl || !serviceRoleKey) {
    return NextResponse.json(
      { error: "Server configuration error. Please contact support." },
      { status: 503 }
    );
  }

  const admin = createAdminClient(supabaseUrl, serviceRoleKey);

  try {
    // 1. Pre-read stripe_customer_id BEFORE the atomic delete (#29).
    //    The RPC in step 2 will wipe the profile row, so we must capture
    //    external-system identifiers ahead of time.
    const { data: profile, error: profileError } = await admin
      .from("profiles")
      .select("stripe_customer_id")
      .eq("id", userId)
      .maybeSingle();
    // SEC/bug: a FAILED read (transient DB fault) must NOT be conflated with
    // "no Stripe customer". If we swallowed the error, stripeCustomerId would
    // default to null, the cancellation block below would be skipped, and we'd
    // proceed to irreversibly delete the account while an active subscription
    // keeps billing — the exact orphaned-billing failure this ordering exists to
    // prevent, just triggered by a profile-read fault instead of a Stripe fault.
    // maybeSingle() returns {data:null,error:null} for a genuine no-row result
    // (legitimately no profile → nothing to cancel), so only a real error aborts.
    if (profileError) {
      console.error(
        "[account/delete] Profile pre-read failed — aborting deletion to avoid orphaning billing:",
        profileError.message
      );
      return NextResponse.json(
        {
          error:
            "Could not verify your billing state right now. Your account was NOT deleted — please try again shortly.",
        },
        { status: 502 }
      );
    }
    const stripeCustomerId =
      (profile?.stripe_customer_id as string | null | undefined) ?? null;

    // 2. Cancel Stripe subscriptions BEFORE any irreversible deletion (U7/bug).
    //    Previously this ran AFTER the DB+auth delete and swallowed errors: if
    //    Stripe were unreachable the subscription would keep billing with no
    //    profile left to reconcile (and no cancellation event is emitted if we
    //    never cancel, so the webhook can't "eventually reconcile"). We now
    //    cancel first and ABORT the deletion on failure — the user retries once
    //    Stripe is reachable; meanwhile account + subscription stay consistent.
    const stripeSecretKey = process.env.STRIPE_SECRET_KEY;
    if (
      stripeCustomerId &&
      stripeSecretKey &&
      stripeSecretKey !== "sk_test_placeholder"
    ) {
      try {
        const stripe = new Stripe(stripeSecretKey, { timeout: 30000 });
        // SEC (U7): cancel ALL subscriptions across pages. `list()` returns
        // only the first page (default 10), so a customer with >10 subs would
        // keep billing. Paginate explicitly via has_more / starting_after, and
        // skip already-canceled ones.
        const toCancel: string[] = [];
        let startingAfter: string | undefined;
        for (;;) {
          const page = await stripe.subscriptions.list({
            customer: stripeCustomerId,
            status: "all",
            limit: 100,
            ...(startingAfter ? { starting_after: startingAfter } : {}),
          });
          const subs = page.data ?? [];
          for (const sub of subs) {
            if (sub.status !== "canceled") toCancel.push(sub.id);
          }
          if (!page.has_more || subs.length === 0) break;
          startingAfter = subs[subs.length - 1].id;
        }
        // Use allSettled so one transient failure doesn't abort the whole
        // batch and leave a partially-cancelled state. Treat an
        // already-canceled / resource_missing subscription as success (the
        // desired end state is "not active"); only a genuine failure on a
        // still-active subscription aborts the deletion.
        const results = await Promise.allSettled(
          toCancel.map((id) => stripe.subscriptions.cancel(id))
        );
        const genuineFailures = results.filter((r) => {
          if (r.status === "fulfilled") return false;
          const reason = r.reason as { code?: string } | undefined;
          // Stripe surfaces 'resource_missing' when the subscription no longer
          // exists; an already-canceled sub is also an acceptable end state.
          return reason?.code !== "resource_missing";
        });
        if (genuineFailures.length > 0) {
          const first = genuineFailures[0] as PromiseRejectedResult;
          const reason = first.reason;
          throw reason instanceof Error
            ? reason
            : new Error("Stripe subscription cancellation failed");
        }
        console.info(
          `[account/delete] Cancelled ${toCancel.length} Stripe subscription(s) for customer ${stripeCustomerId}`
        );
      } catch (stripeErr) {
        const msg = stripeErr instanceof Error ? stripeErr.message : "Unknown error";
        console.error("[account/delete] Stripe cancellation failed — aborting deletion:", msg);
        return NextResponse.json(
          {
            error:
              "Could not cancel your active subscription right now. Your account was NOT deleted — please try again shortly.",
          },
          { status: 502 }
        );
      }
    }

    // 3. Atomic DB deletion via SECURITY DEFINER RPC (#29). Runs only after any
    //    subscription has been cancelled, so a billing record can't outlive the
    //    account. The RPC wraps the whole cascade in a single PL/pgSQL tx.
    const { error: rpcError } = await admin.rpc("delete_user_account", {
      uid: userId,
    });
    if (rpcError) {
      console.error(
        "[account/delete] delete_user_account RPC failed:",
        rpcError.message
      );
      return NextResponse.json(
        { error: "Account deletion failed. Please contact support." },
        { status: 500 }
      );
    }

    // 4. Delete the auth user (point-of-no-return, external to DB tx)
    const { error: deleteAuthError } = await admin.auth.admin.deleteUser(userId);
    if (deleteAuthError) {
      // Log but do not expose internal error details
      console.error("[account/delete] Failed to delete auth user:", deleteAuthError.message);
      return NextResponse.json(
        { error: "Failed to complete account deletion. Please contact support." },
        { status: 500 }
      );
    }

    console.info(`[account/delete] Account deleted for user ${userId}`);
    return NextResponse.json({ deleted: true });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    console.error("[account/delete] Unexpected error:", message);
    return NextResponse.json(
      { error: "Account deletion failed. Please contact support." },
      { status: 500 }
    );
  }
}
