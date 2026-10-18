import { NextResponse } from "next/server";
import { isSafeInternalPath } from "@/lib/safe-redirect";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const { searchParams, origin } = new URL(request.url);
  const code = searchParams.get("code");

  // AUTHCB-02: Log error parameter from provider for debugging
  const providerError = searchParams.get("error");
  const providerErrorDesc = searchParams.get("error_description");
  if (providerError) {
    console.error("[auth/callback] OAuth provider error:", providerError, providerErrorDesc);
    const msg = providerError === "access_denied" ? "access_denied" : "auth_failed";
    return NextResponse.redirect(`${origin}/login?error=${msg}`);
  }

  // SEC/#26: validate redirectTo as a SAME-ORIGIN internal path, shared with the
  // login page (src/lib/safe-redirect). The redirect is built same-origin below
  // (`${origin}${redirectTo}`), so any internal path that passes is safe from
  // open-redirect. The previous narrow prefix allow-list silently dropped valid
  // deep links (e.g. /people-risk/actions) to /dashboard even though the login
  // page accepted them.
  const rawRedirectTo = searchParams.get("redirectTo") || "/dashboard";
  const redirectTo = isSafeInternalPath(rawRedirectTo) ? rawRedirectTo : "/dashboard";

  if (code) {
    try {
      const { createClient } = await import("@/lib/supabase/server");
      const supabase = await createClient();
      const { error, data } = await supabase.auth.exchangeCodeForSession(code);
      if (!error && data.user) {
        const userId = data.user.id;

        // #123: don't swallow lookup errors — a transient DB fault used to be
        // indistinguishable from "first-time user" and silently took the
        // wrong branch while still issuing a session.
        const { data: existingProfile, error: profileError } = await supabase
          .from("profiles")
          .select("id, plan, trial_ends_at, stripe_customer_id")
          .eq("id", userId)
          .maybeSingle();

        if (profileError) {
          console.error(
            "[auth/callback] Profile lookup failed:",
            profileError.message
          );
          // SEC (U29): exchangeCodeForSession already set session cookies. Don't
          // leave an authenticated-but-broken session reachable — sign out so
          // the error redirect can't be bypassed by navigating to a gated route.
          await supabase.auth.signOut();
          return NextResponse.redirect(`${origin}/login?error=profile_setup_failed`);
        }

        const { shouldProvisionTrial, trialEndIso } = await import(
          "@/lib/trial-provisioning"
        );

        let isNewUser = false;
        if (!existingProfile) {
          // Trigger missing/failed: create the profile + trial ourselves.
          // #123: a failed insert means the account has no usable profile —
          // fail loudly instead of redirecting into a broken session.
          isNewUser = true;
          const { error: insertError } = await supabase.from("profiles").insert({
            id: userId,
            plan: "business",
            trial_ends_at: trialEndIso(),
            // Mark as a non-paying trial so trial-expiry can downgrade it later
            // (a profile whose status stayed at the 'active' DEFAULT is never
            // downgraded — see migration 025).
            subscription_status: "trialing",
          });
          if (insertError) {
            console.error(
              "[auth/callback] Profile bootstrap failed:",
              insertError.message
            );
            // SEC (U29): fail closed — clear the just-issued session rather than
            // leaving an authenticated account with no usable profile.
            await supabase.auth.signOut();
            return NextResponse.redirect(
              `${origin}/login?error=profile_setup_failed`
            );
          }
        } else if (shouldProvisionTrial(existingProfile, data.user.created_at)) {
          // #114: the handle_new_user trigger pre-creates the profile, so the
          // !existingProfile branch never ran for normal sign-ups and nobody
          // got the promised 7-day Business trial. A profile still in its
          // trigger default state (free / no trial / no Stripe) belonging to
          // an auth user created minutes ago IS a fresh signup — provision it.
          // SEC/bug (#114 + migration 013): billing columns (plan/trial_ends_at/
          // subscription_status) are service-role-only since 013 revoked the
          // authenticated UPDATE grant, so this update with the *user* client was
          // column-grant DENIED — the promised 7-day Business trial silently
          // never applied. Provision through a narrowly-scoped SECURITY DEFINER
          // RPC (migration 025) that re-asserts the trigger-default precondition
          // server-side and stamps subscription_status='trialing'.
          const { data: provisioned, error: trialError } = await supabase.rpc(
            "provision_business_trial"
          );
          if (trialError) {
            // Trial is recoverable support-side — don't block a working
            // sign-in over the entitlement write.
            console.error(
              "[auth/callback] Trial provisioning failed:",
              trialError.message
            );
            isNewUser = false;
          } else {
            // Only treat as a fresh trial (welcome email) when the RPC actually
            // provisioned a row (precondition still held).
            isNewUser = provisioned === true;
          }
        }

        if (isNewUser) {
          // Welcome email for both new-user paths (previously unreachable for
          // trigger-created profiles, i.e. effectively never sent).
          try {
            const { sendEmail } = await import("@/lib/email");
            const { welcomeEmail } = await import("@/lib/email-templates");
            const userEmail = data.user.email;
            const userName =
              data.user.user_metadata?.full_name ??
              data.user.email?.split("@")[0] ??
              "there";
            if (userEmail) {
              const { subject, html } = welcomeEmail(userName);
              await sendEmail({ to: userEmail, subject, html });
            }
          } catch {
            // Non-critical — do not block sign-in on email failure
          }
        }

        return NextResponse.redirect(`${origin}${redirectTo}`);
      }
    } catch (err) {
      // Was a silent catch-all ("Supabase not configured"), which also swallowed
      // genuine runtime faults (DB/network/unexpected errors) with no trace,
      // making production incidents impossible to debug. Log before falling
      // through to the generic auth_failed redirect.
      console.error(
        "[auth/callback] Unexpected error during code exchange:",
        err instanceof Error ? err.message : err
      );
    }
  }

  return NextResponse.redirect(`${origin}/login?error=auth_failed`);
}
