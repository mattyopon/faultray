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

  // Validate redirectTo to prevent open redirect — only allow internal paths
  const rawRedirectTo = searchParams.get("redirectTo") || "/dashboard";
  const redirectTo =
    rawRedirectTo.startsWith("/") && !rawRedirectTo.startsWith("//")
      ? rawRedirectTo
      : "/dashboard";

  if (code) {
    try {
      const { createClient } = await import("@/lib/supabase/server");
      const supabase = await createClient();
      const { error, data } = await supabase.auth.exchangeCodeForSession(code);
      if (!error && data.user) {
        // Provision 7-day Business trial for brand-new users
        const userId = data.user.id;
        const { data: existingProfile } = await supabase
          .from("profiles")
          .select("id, plan, trial_ends_at")
          .eq("id", userId)
          .maybeSingle();

        if (!existingProfile) {
          // First-ever sign-in: create profile with trial
          const trialEnd = new Date(
            Date.now() + 7 * 24 * 60 * 60 * 1000
          ).toISOString();
          await supabase.from("profiles").insert({
            id: userId,
            plan: "business",
            trial_ends_at: trialEnd,
          });

          // Send welcome email to new users
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
        // Existing profiles: no changes (trial already handled)

        return NextResponse.redirect(`${origin}${redirectTo}`);
      }
    } catch {
      // Supabase not configured
    }
  }

  return NextResponse.redirect(`${origin}/login?error=auth_failed`);
}
