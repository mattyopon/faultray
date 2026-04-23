import { NextResponse } from "next/server";
import { requireAuth } from "@/lib/api-auth";
import { applyRateLimit } from "@/lib/rate-limit";

export const dynamic = "force-dynamic";

const VALID_KEYS = [
  "simulationCompleted",
  "scoreDegradation",
  "weeklySummary",
  "monthlyReport",
  "criticalAlertImmediate",
] as const;

/**
 * GET /api/notification-preferences — Read notification settings for the current user.
 */
export async function GET(request: Request) {
  const limited = await applyRateLimit(request, { limit: 30, windowMs: 60_000 });
  if (limited) return limited;

  const { user, error } = await requireAuth(request);
  if (error) return error;

  const { createClient } = await import("@/lib/supabase/server");
  const supabase = await createClient();

  const { data, error: queryError } = await supabase
    .from("profiles")
    .select("notification_preferences")
    .eq("id", user.id)
    .maybeSingle();

  if (queryError) {
    console.error("[notification-preferences] Query error:", queryError.message);
    return NextResponse.json({ error: "Failed to fetch preferences" }, { status: 500 });
  }

  return NextResponse.json(data?.notification_preferences ?? {
    simulationCompleted: true,
    scoreDegradation: true,
    weeklySummary: false,
    monthlyReport: false,
    criticalAlertImmediate: true,
  });
}

/**
 * PATCH /api/notification-preferences — Update notification settings.
 * Body: { "simulationCompleted": false, "weeklySummary": true }
 */
export async function PATCH(request: Request) {
  const limited = await applyRateLimit(request, { limit: 10, windowMs: 60_000 });
  if (limited) return limited;

  const { user, error } = await requireAuth(request);
  if (error) return error;

  let body: Record<string, unknown>;
  try {
    body = (await request.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  // Validate keys
  for (const key of Object.keys(body)) {
    if (!VALID_KEYS.includes(key as (typeof VALID_KEYS)[number])) {
      return NextResponse.json({ error: `Invalid key: ${key}` }, { status: 400 });
    }
    if (typeof body[key] !== "boolean") {
      return NextResponse.json({ error: `${key} must be boolean` }, { status: 400 });
    }
  }

  const { createClient } = await import("@/lib/supabase/server");
  const supabase = await createClient();

  // Merge with existing preferences
  const { data: existing } = await supabase
    .from("profiles")
    .select("notification_preferences")
    .eq("id", user.id)
    .maybeSingle();

  const merged = { ...(existing?.notification_preferences ?? {}), ...body };

  const { error: updateError } = await supabase
    .from("profiles")
    .update({ notification_preferences: merged })
    .eq("id", user.id);

  if (updateError) {
    console.error("[notification-preferences] Update error:", updateError.message);
    return NextResponse.json({ error: "Failed to update preferences" }, { status: 500 });
  }

  return NextResponse.json(merged);
}
