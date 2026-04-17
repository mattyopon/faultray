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
  const limited = applyRateLimit(request, { limit: 5, windowMs: 60_000 });
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
    // 1. Delete data for teams owned by this user only.
    //    Teams where the user is merely a member must NOT be deleted.
    const { data: ownedTeams } = await admin
      .from("teams")
      .select("id")
      .eq("owner_id", userId);

    if (ownedTeams && ownedTeams.length > 0) {
      const ownedTeamIds = ownedTeams.map((t: { id: string }) => t.id);

      // Delete simulation runs
      await admin.from("simulation_runs").delete().in("team_id", ownedTeamIds);

      // Delete usage records
      await admin.from("usage").delete().in("team_id", ownedTeamIds);

      // Delete billing events
      await admin.from("billing_events").delete().in("team_id", ownedTeamIds);

      // Delete projects
      await admin.from("projects").delete().in("team_id", ownedTeamIds);

      // Remove all members from owned teams before deleting the teams
      await admin.from("team_members").delete().in("team_id", ownedTeamIds);

      // Delete teams owned by this user
      await admin.from("teams").delete().eq("owner_id", userId);
    }

    // Remove this user's membership from teams they joined but do not own
    await admin.from("team_members").delete().eq("user_id", userId);

    // 2. Cancel Stripe subscriptions to prevent continued billing after account deletion
    const stripeSecretKey = process.env.STRIPE_SECRET_KEY;
    if (stripeSecretKey && stripeSecretKey !== "sk_test_placeholder") {
      try {
        const stripe = new Stripe(stripeSecretKey, { timeout: 30000 });

        // Fetch stripe_customer_id from profiles before deletion
        const { data: profile } = await admin
          .from("profiles")
          .select("stripe_customer_id")
          .eq("id", userId)
          .maybeSingle();

        const customerId = profile?.stripe_customer_id as string | null | undefined;
        if (customerId) {
          const subscriptions = await stripe.subscriptions.list({ customer: customerId });
          await Promise.all(
            subscriptions.data.map((sub) => stripe.subscriptions.cancel(sub.id))
          );
          console.info(
            `[account/delete] Cancelled ${subscriptions.data.length} Stripe subscription(s) for customer ${customerId}`
          );
        }
      } catch (stripeErr) {
        // Log but do not block account deletion — data cleanup takes priority
        const msg = stripeErr instanceof Error ? stripeErr.message : "Unknown error";
        console.error("[account/delete] Stripe cancellation error (non-fatal):", msg);
      }
    }

    // 3. Delete / anonymize the user profile
    await admin.from("profiles").delete().eq("id", userId);

    // 4. Delete the auth user (point-of-no-return)
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
