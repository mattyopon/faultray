import { NextResponse } from "next/server";
import { applyRateLimit } from "@/lib/rate-limit";

export const dynamic = "force-dynamic";

/**
 * POST /api/cron/trial-expiry
 *
 * Daily cron (see vercel.json crons).
 *
 * Calls PL/pgSQL function `public.downgrade_expired_trials()` which
 * atomically SELECT + UPDATE rows matching:
 *   - trial_ends_at IS NOT NULL AND trial_ends_at < now()
 *   - plan != 'free'
 *   - subscription_status NOT IN ('active','trialing','past_due')
 *     (past_due is Stripe dunning window — keep features during retries)
 *
 * Rationale for RPC (vs JS SELECT+filter+UPDATE):
 *   1) Avoid Supabase JS 1000-row select limit (revenue leak)
 *   2) Eliminate race between read and write (webhook could flip status)
 *
 * Protected by CRON_SECRET (Bearer) to prevent unauthorized invocation.
 */
export async function POST(request: Request) {
  const limited = applyRateLimit(request, { limit: 5, windowMs: 60_000 });
  if (limited) return limited;

  const cronSecret = process.env.CRON_SECRET;
  const authHeader = request.headers.get("authorization");

  if (!cronSecret || authHeader !== `Bearer ${cronSecret}`) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { createClient } = await import("@supabase/supabase-js");
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const serviceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY;

  if (!url || !serviceRoleKey) {
    return NextResponse.json(
      { error: "Supabase not configured" },
      { status: 503 }
    );
  }

  const supabase = createClient(url, serviceRoleKey);

  const { data, error } = await supabase.rpc("downgrade_expired_trials");

  if (error) {
    console.error("[cron/trial-expiry] RPC error:", error.message);
    return NextResponse.json({ error: "Downgrade failed" }, { status: 500 });
  }

  const rows = Array.isArray(data) ? data : [];
  const downgraded = rows.length;

  console.info(`[cron/trial-expiry] Downgraded ${downgraded} users`);

  return NextResponse.json({ downgraded });
}
