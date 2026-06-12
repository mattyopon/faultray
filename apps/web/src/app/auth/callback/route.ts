import { NextResponse } from "next/server";

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

  // SEC-02 / #26: Validate redirectTo via explicit allow-list of internal
  // app routes. Previous regex `^\/(?:[...]*)$` accepted `//evil.com` and
  // similar path-normalization traps. While NextResponse.redirect(origin+path)
  // prevents true cross-origin open redirect, the user-visible URL could
  // still render as `https://faultray.com//evil.com` which is confusing.
  // An allow-list of top-level segments removes the attack surface entirely.
  const SAFE_REDIRECT_PREFIXES: ReadonlyArray<string> = [
    "/dashboard",
    "/settings",
    "/simulate",
    "/projects",
    "/reports",
    "/compliance",
    "/dora",
    "/pricing",
    "/billing",
    "/whatif",
  ];
  const rawRedirectTo = searchParams.get("redirectTo") || "/dashboard";
  const isSafeRedirect = (value: string): boolean => {
    // Must be a proper internal path (single leading slash, no protocol / authority marker)
    if (!value.startsWith("/") || value.startsWith("//") || value.startsWith("/\\")) {
      return false;
    }
    // Reject path-traversal segments that could normalize out of the
    // allow-listed prefix (e.g. `/dashboard/../admin` → `/admin`).
    if (value.includes("..") || value.includes("\\")) {
      return false;
    }
    // Must begin with one of our known top-level segments
    return SAFE_REDIRECT_PREFIXES.some(
      (p) => value === p || value.startsWith(`${p}/`) || value.startsWith(`${p}?`) || value.startsWith(`${p}#`)
    );
  };
  const redirectTo = isSafeRedirect(rawRedirectTo) ? rawRedirectTo : "/dashboard";

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
          });
          if (insertError) {
            console.error(
              "[auth/callback] Profile bootstrap failed:",
              insertError.message
            );
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
          isNewUser = true;
          const { error: trialError } = await supabase
            .from("profiles")
            .update({ plan: "business", trial_ends_at: trialEndIso() })
            .eq("id", userId)
            // Re-assert the precondition so a concurrent webhook/coupon write
            // between read and update can't be clobbered.
            .eq("plan", "free")
            .is("trial_ends_at", null)
            .is("stripe_customer_id", null);
          if (trialError) {
            // Trial is recoverable support-side — don't block a working
            // sign-in over the entitlement write.
            console.error(
              "[auth/callback] Trial provisioning failed:",
              trialError.message
            );
            isNewUser = false;
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
    } catch {
      // Supabase not configured
    }
  }

  return NextResponse.redirect(`${origin}/login?error=auth_failed`);
}
