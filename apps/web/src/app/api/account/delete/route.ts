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
import Stripe from "stripe";

export const dynamic = "force-dynamic";

export async function DELETE(request: Request) {
  const limited = await applyRateLimit(request, { limit: 5, windowMs: 60_000 });
  if (limited) return limited;

  // Parse optional confirmation body
  let body: { confirm?: boolean } = {};
  try {
    body = (await request.json()) as { confirm?: boolean };
  } catch {
    // No body is fine; we rely on the auth check below
  }

  if (!body.confirm) {
    return NextResponse.json(
      { error: "Confirmation required. Send { \"confirm\": true } in the request body." },
      { status: 400 }
    );
  }

  // Authenticate via SSR Supabase client (reads session from cookies)
  const { createClient } = await import("@/lib/supabase/server");
  const supabase = await createClient();

  const {
    data: { user },
    error: userError,
  } = await supabase.auth.getUser();

  if (userError || !user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
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
        const subscriptions = await stripe.subscriptions.list({
          customer: stripeCustomerId,
        });
        await Promise.all(
          subscriptions.data.map((sub) => stripe.subscriptions.cancel(sub.id))
        );
        console.info(
          `[account/delete] Cancelled ${subscriptions.data.length} Stripe subscription(s) for customer ${stripeCustomerId}`
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
