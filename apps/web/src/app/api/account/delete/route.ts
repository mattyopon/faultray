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
    const { data: profile } = await admin
      .from("profiles")
      .select("stripe_customer_id")
      .eq("id", userId)
      .maybeSingle();
    const stripeCustomerId =
      (profile?.stripe_customer_id as string | null | undefined) ?? null;

    // 2. Atomic DB deletion via SECURITY DEFINER RPC (#29).
    //    Replaces a 7-step non-transactional sequence that could leave
    //    orphan rows on failure. The RPC wraps the whole cascade in a
    //    single PL/pgSQL transaction and returns per-table counts.
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

    // 3. Cancel Stripe subscriptions using the pre-read customer id.
    //    External call — deliberately outside the DB tx. Failure is
    //    logged but non-fatal (data cleanup has already succeeded;
    //    Stripe customer.subscription.deleted webhook will eventually
    //    reconcile).
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
        await Promise.all(
          toCancel.map((id) => stripe.subscriptions.cancel(id))
        );
        console.info(
          `[account/delete] Cancelled ${toCancel.length} Stripe subscription(s) for customer ${stripeCustomerId}`
        );
      } catch (stripeErr) {
        const msg = stripeErr instanceof Error ? stripeErr.message : "Unknown error";
        console.error("[account/delete] Stripe cancellation error (non-fatal):", msg);
      }
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
