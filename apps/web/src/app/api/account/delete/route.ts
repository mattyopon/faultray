/**
 * EXPORT-01: GDPR-compliant account deletion endpoint.
 *
 * Deletes or anonymizes all user data from Supabase then removes the
 * auth.users record so the user can no longer log in.
 *
 * Requires: authenticated session (via Supabase SSR cookie).
 */
import { NextResponse } from "next/server";
import { applyRateLimit } from "@/lib/rate-limit";

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
    // 1. Delete simulation runs owned by this user's teams
    //    (cascade via team deletion below, but be explicit for audit trail)
    const { data: userTeams } = await admin
      .from("team_members")
      .select("team_id")
      .eq("user_id", userId);

    if (userTeams && userTeams.length > 0) {
      const teamIds = userTeams.map((t: { team_id: string }) => t.team_id);

      // Delete simulation runs
      await admin.from("simulation_runs").delete().in("team_id", teamIds);

      // Delete usage records
      await admin.from("usage").delete().in("team_id", teamIds);

      // Delete billing events
      await admin.from("billing_events").delete().in("team_id", teamIds);

      // Delete projects
      await admin.from("projects").delete().in("team_id", teamIds);

      // Remove user from all teams
      await admin.from("team_members").delete().eq("user_id", userId);

      // Delete teams owned by this user
      await admin.from("teams").delete().eq("owner_id", userId);
    }

    // 2. Delete / anonymize the user profile
    await admin.from("profiles").delete().eq("id", userId);

    // 3. Delete the auth user (point-of-no-return)
    const { error: deleteAuthError } = await admin.auth.admin.deleteUser(userId);
    if (deleteAuthError) {
      // Log but do not expose internal error details
      console.error("[account/delete] Failed to delete auth user:", deleteAuthError.message);
      return NextResponse.json(
        { error: "Failed to complete account deletion. Please contact support." },
        { status: 500 }
      );
    }

    console.log(`[account/delete] Account deleted for user ${userId}`);
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
