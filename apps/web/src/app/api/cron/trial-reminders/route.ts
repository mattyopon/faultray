import { NextResponse } from "next/server";
import { sendEmail } from "@/lib/email";
import { trialReminderEmail } from "@/lib/email-templates";
import { applyRateLimit } from "@/lib/rate-limit";
import { verifyCronAuth } from "@/lib/cron-auth";

export const dynamic = "force-dynamic";

/**
 * POST /api/cron/trial-reminders
 * Called by Vercel Cron or external scheduler (daily).
 * Finds users whose trial ends in exactly 3 days and sends reminder emails.
 * Protected by CRON_SECRET + optional CRON_ALLOWED_IPS (#27).
 */
export async function POST(request: Request) {
  const limited = await applyRateLimit(request, { limit: 5, windowMs: 60_000 });
  if (limited) return limited;

  const unauthorized = verifyCronAuth(request);
  if (unauthorized) return unauthorized;

  const { createClient } = await import("@supabase/supabase-js");
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const serviceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY;

  if (!url || !serviceRoleKey) {
    return NextResponse.json({ error: "Supabase not configured" }, { status: 503 });
  }

  const supabase = createClient(url, serviceRoleKey);

  // Find users whose trial ends in 3 days (between 3d and 4d from now)
  const now = new Date();
  const threeDaysLater = new Date(now.getTime() + 3 * 24 * 60 * 60 * 1000);
  const fourDaysLater = new Date(now.getTime() + 4 * 24 * 60 * 60 * 1000);

  const { data: users, error: queryError } = await supabase
    .from("profiles")
    .select("id, email, full_name, trial_ends_at")
    .gte("trial_ends_at", threeDaysLater.toISOString())
    .lt("trial_ends_at", fourDaysLater.toISOString())
    .eq("plan", "free");

  if (queryError) {
    console.error("[cron/trial-reminders] Query error:", queryError.message);
    return NextResponse.json({ error: "Query failed" }, { status: 500 });
  }

  if (!users || users.length === 0) {
    return NextResponse.json({ sent: 0, message: "No users approaching trial expiry" });
  }

  let sent = 0;
  const errors: string[] = [];

  for (const user of users) {
    if (!user.email) continue;

    const trialEnd = new Date(user.trial_ends_at as string);
    const daysLeft = Math.ceil((trialEnd.getTime() - now.getTime()) / (24 * 60 * 60 * 1000));
    const name = (user.full_name as string) || "there";
    const { subject, html } = trialReminderEmail(name, daysLeft);

    const result = await sendEmail({ to: user.email as string, subject, html });
    if (result.success) {
      sent++;
    } else {
      errors.push(`${user.email}: ${result.error}`);
    }
  }

  console.info(`[cron/trial-reminders] Sent ${sent}/${users.length} emails`);

  return NextResponse.json({ sent, total: users.length, errors: errors.length > 0 ? errors : undefined });
}
