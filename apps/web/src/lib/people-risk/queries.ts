import { createClient } from "@/lib/supabase/client";
import type {
  Member,
  System,
  MemberSystem,
  Action,
  RiskSnapshot,
  MemberWithSystems,
  SystemWithMembers,
  ActionWithSystem,
  PeopleRiskSummary,
} from "./types";

const DEMO_COMPANY_ID = "11111111-1111-1111-1111-111111111111";

function supabase() {
  return createClient();
}

/* ── Members ─────────────────────────────────────────────── */

export async function fetchMembers(): Promise<MemberWithSystems[]> {
  const { data, error } = await supabase()
    .from("members")
    .select("*, member_systems(*, systems(*))")
    .eq("company_id", DEMO_COMPANY_ID)
    .order("name");
  if (error) throw error;
  return (data ?? []) as unknown as MemberWithSystems[];
}

export async function fetchMemberById(
  id: string
): Promise<MemberWithSystems | null> {
  // SEC (U32): scope by company in code, not RLS alone. Without the
  // company_id predicate this is an IDOR — any member id from any tenant would
  // be readable if the RLS policy is ever weakened/drifted. maybeSingle() so a
  // cross-tenant id returns null (not a 500).
  const { data, error } = await supabase()
    .from("members")
    .select("*, member_systems(*, systems(*))")
    .eq("id", id)
    .eq("company_id", DEMO_COMPANY_ID)
    .maybeSingle();
  if (error) return null;
  return (data ?? null) as unknown as MemberWithSystems | null;
}

/* ── Systems ─────────────────────────────────────────────── */

export async function fetchSystems(): Promise<SystemWithMembers[]> {
  const { data, error } = await supabase()
    .from("systems")
    .select("*, member_systems(*, members(*))")
    .eq("company_id", DEMO_COMPANY_ID)
    .order("name");
  if (error) throw error;
  return (data ?? []) as unknown as SystemWithMembers[];
}

/* ── Actions ─────────────────────────────────────────────── */

export async function fetchActions(): Promise<ActionWithSystem[]> {
  const { data, error } = await supabase()
    .from("actions")
    .select("*, systems(*)")
    .eq("company_id", DEMO_COMPANY_ID)
    .order("created_at", { ascending: false });
  if (error) throw error;
  return (data ?? []) as unknown as ActionWithSystem[];
}

export async function updateActionStatus(
  id: string,
  status: Action["status"]
): Promise<void> {
  // SEC (U32): scope the mutation by company and verify a row was actually
  // updated. `.update().eq("id")` without a company predicate is a cross-tenant
  // write under weak RLS; without `.select()` a zero-row update returns no
  // error and the UI falsely shows success.
  const { data, error } = await supabase()
    .from("actions")
    .update({ status })
    .eq("id", id)
    .eq("company_id", DEMO_COMPANY_ID)
    .select("id");
  if (error) throw error;
  if (!data || data.length === 0) {
    throw new Error("Action not found or not in scope");
  }
}

/* ── Snapshots ───────────────────────────────────────────── */

export async function fetchSnapshots(): Promise<RiskSnapshot[]> {
  const { data, error } = await supabase()
    .from("risk_snapshots")
    .select("*")
    .eq("company_id", DEMO_COMPANY_ID)
    .order("week_start");
  if (error) throw error;
  return (data ?? []) as RiskSnapshot[];
}

/* ── Summary (computed) ──────────────────────────────────── */

export async function fetchSummary(): Promise<PeopleRiskSummary> {
  const [membersRes, systemsRes, msRes] = await Promise.all([
    supabase()
      .from("members")
      .select("id, status")
      .eq("company_id", DEMO_COMPANY_ID),
    supabase()
      .from("systems")
      .select("id")
      .eq("company_id", DEMO_COMPANY_ID),
    // SEC (U32): scope member_systems to the company too. Previously this read
    // EVERY visible member_systems row, so under permissive/drifted RLS the
    // summary aggregated (and leaked counts) across other tenants. Inner-join
    // to members and filter by company.
    supabase()
      .from("member_systems")
      .select("system_id, is_sole_owner, risk_level, members!inner(company_id)")
      .eq("members.company_id", DEMO_COMPANY_ID),
  ]);

  const members = (membersRes.data ?? []) as Pick<Member, "id" | "status">[];
  const systems = (systemsRes.data ?? []) as Pick<System, "id">[];
  const ms = (msRes.data ?? []) as unknown as Pick<
    MemberSystem,
    "system_id" | "is_sole_owner" | "risk_level"
  >[];

  const soleOwnerSystems = new Set(
    ms.filter((r) => r.is_sole_owner).map((r) => r.system_id)
  );

  const riskCounts = { critical: 0, warning: 0, safe: 0 };
  for (const r of ms) {
    if (r.risk_level === "critical") riskCounts.critical++;
    else if (r.risk_level === "warning") riskCounts.warning++;
    else riskCounts.safe++;
  }

  const totalRisk =
    riskCounts.critical * 10 + riskCounts.warning * 5 + riskCounts.safe * 1;
  const avgRisk = ms.length > 0 ? totalRisk / ms.length : 0;

  return {
    totalSystems: systems.length,
    singleOwnerSystems: soleOwnerSystems.size,
    busFactor1Count: soleOwnerSystems.size,
    avgRiskScore: Math.round(avgRisk * 10) / 10,
    totalMembers: members.length,
    activeMembers: members.filter((m) => m.status === "active").length,
    leftMembers: members.filter((m) => m.status === "left").length,
    criticalCount: riskCounts.critical,
    warningCount: riskCounts.warning,
    safeCount: riskCounts.safe,
  };
}
