import { NextResponse } from "next/server";
import { requireAuth } from "@/lib/api-auth";
import { applyRateLimit } from "@/lib/rate-limit";
import { AUDIT_LOG_ACTION_SET } from "@/lib/audit-log-actions";

export const dynamic = "force-dynamic";

/**
 * Allowed action values for audit log writes (whitelist).
 * #111: the previous list was lowercase dotted names (e.g. "simulation.run")
 * which the DB CHECK constraint never accepted, so every POST returned 500.
 * The canonical UPPER_SNAKE vocabulary lives in src/lib/audit-log-actions.ts
 * and is mirrored by migration 019.
 */
const ALLOWED_ACTIONS = AUDIT_LOG_ACTION_SET;

/**
 * Allowed outcome values for audit log writes (whitelist).
 * Must mirror the DB CHECK constraint `audit_logs_outcome_check`
 * (migration 011: outcome IN ('SUCCESS','FAILURE')). An arbitrary
 * caller-supplied value would otherwise surface as an unhandled Postgres
 * error (500) for what is really a client (400) mistake.
 */
const ALLOWED_OUTCOMES = new Set(["SUCCESS", "FAILURE"]);

/**
 * GET /api/audit-log — List audit log entries for the user's team.
 * Query params: ?action=LOGIN&outcome=FAILURE&limit=50&offset=0
 */
export async function GET(request: Request) {
  const limited = await applyRateLimit(request, { limit: 30, windowMs: 60_000 });
  if (limited) return limited;

  const { user, error } = await requireAuth(request);
  if (error) return error;

  const { createClient } = await import("@/lib/supabase/server");
  const supabase = await createClient();

  // Resolve user's team. ``team_members`` has no ``status`` column today —
  // every row already represents an active membership (status was an org_members
  // concept we mis-copied). Filtering by it returns zero rows and breaks reads.
  const { data: membership, error: membershipError } = await supabase
    .from("team_members")
    .select("team_id")
    .eq("user_id", user.id)
    .limit(1)
    .maybeSingle();

  // A DB/RLS failure must not be conflated with "no membership" — that would
  // hide an outage behind an empty (but 200) audit log.
  if (membershipError) {
    console.error("[audit-log] Membership lookup error:", membershipError.message);
    return NextResponse.json({ error: "Failed to fetch audit logs" }, { status: 500 });
  }

  if (!membership) {
    return NextResponse.json({ entries: [], total: 0 });
  }

  const url = new URL(request.url);
  const action = url.searchParams.get("action");
  const outcome = url.searchParams.get("outcome");
  // Clamp pagination params — NaN or negative values would otherwise be
  // passed straight into .range() and break the query.
  const rawLimit = parseInt(url.searchParams.get("limit") || "50", 10);
  const rawOffset = parseInt(url.searchParams.get("offset") || "0", 10);
  const limit = Number.isFinite(rawLimit) ? Math.min(Math.max(rawLimit, 1), 100) : 50;
  const offset = Number.isFinite(rawOffset) ? Math.max(rawOffset, 0) : 0;

  let query = supabase
    .from("audit_logs")
    .select("*", { count: "exact" })
    .eq("team_id", membership.team_id)
    .order("created_at", { ascending: false })
    .range(offset, offset + limit - 1);

  if (action) query = query.eq("action", action);
  if (outcome) query = query.eq("outcome", outcome);

  const { data, count, error: queryError } = await query;

  if (queryError) {
    console.error("[audit-log] Query error:", queryError.message);
    return NextResponse.json({ error: "Failed to fetch audit logs" }, { status: 500 });
  }

  return NextResponse.json({ entries: data ?? [], total: count ?? 0 });
}

/**
 * POST /api/audit-log — Write an audit log entry.
 * Called internally by other API routes when actions occur.
 */
export async function POST(request: Request) {
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

  const { action, resource, outcome, details } = body;

  if (!action || typeof action !== "string") {
    return NextResponse.json({ error: "action is required" }, { status: 400 });
  }

  // #17: Whitelist validation — reject unknown action values
  if (!ALLOWED_ACTIONS.has(action)) {
    return NextResponse.json(
      {
        error: `Invalid action '${action}'. Allowed values: ${[...ALLOWED_ACTIONS].join(", ")}`,
      },
      { status: 400 }
    );
  }

  // Validate outcome against the same fixed vocabulary the DB CHECK enforces,
  // so a bad value is a 400 (client error) rather than an unhandled 500.
  if (
    outcome !== undefined &&
    outcome !== null &&
    (typeof outcome !== "string" || !ALLOWED_OUTCOMES.has(outcome))
  ) {
    return NextResponse.json(
      {
        error: `Invalid outcome '${String(outcome)}'. Allowed values: ${[...ALLOWED_OUTCOMES].join(", ")}`,
      },
      { status: 400 }
    );
  }

  const { createClient } = await import("@/lib/supabase/server");
  const supabase = await createClient();

  // Resolve team — see GET handler comment; team_members has no ``status``
  // column today, so we filter only by user_id.
  const { data: membership } = await supabase
    .from("team_members")
    .select("team_id")
    .eq("user_id", user.id)
    .limit(1)
    .maybeSingle();

  const ipAddress = request.headers.get("x-forwarded-for")?.split(",")[0]?.trim() || "unknown";
  const userAgent = request.headers.get("user-agent") || "unknown";

  const { error: insertError } = await supabase.from("audit_logs").insert({
    team_id: membership?.team_id ?? null,
    user_id: user.id,
    actor_email: user.email ?? "unknown",
    action,
    resource: resource ?? null,
    ip_address: ipAddress,
    user_agent: userAgent,
    outcome: outcome ?? "SUCCESS",
    details: details ?? null,
  });

  if (insertError) {
    console.error("[audit-log] Insert error:", insertError.message);
    return NextResponse.json({ error: "Failed to write audit log" }, { status: 500 });
  }

  return NextResponse.json({ ok: true }, { status: 201 });
}
