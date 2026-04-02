import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const { searchParams, origin } = new URL(request.url);
  const code = searchParams.get("code");
  const redirectTo = searchParams.get("redirectTo") || "/dashboard";

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
