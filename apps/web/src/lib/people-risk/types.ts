/* ============================================================
 * FaultRay People — Shared Types
 * ============================================================ */

export interface Company {
  id: string;
  name: string;
  created_at: string;
}

export interface Member {
  id: string;
  company_id: string;
  name: string;
  department: string | null;
  role: string | null;
  status: "active" | "left";
  created_at: string;
}

export interface System {
  id: string;
  company_id: string;
  name: string;
  type: "gas" | "aws" | "saas" | "database" | "infra" | "process" | null;
  description: string | null;
  status: "active" | "orphaned" | "dormant" | null;
  last_updated: string | null;
  created_at: string;
}

export interface MemberSystem {
  id: string;
  member_id: string;
  system_id: string;
  access_level: "owner" | "admin" | "editor" | "viewer" | null;
  is_sole_owner: boolean;
  risk_level: "critical" | "warning" | "safe" | null;
  notes: string | null;
}

export interface Action {
  id: string;
  company_id: string;
  system_id: string | null;
  title: string;
  description: string | null;
  priority: "critical" | "warning" | "info" | null;
  risk_reduction: number | null;
  status: "pending" | "in_progress" | "done";
  created_at: string;
}

export interface RiskSnapshot {
  id: string;
  company_id: string;
  week_start: string;
  avg_risk_score: number | null;
  bus_factor_1_count: number | null;
  total_systems: number | null;
  created_at: string;
}

/* ============================================================
 * Joined / Computed Types
 * ============================================================ */

export interface MemberWithSystems extends Member {
  member_systems: (MemberSystem & { systems: System })[];
}

export interface SystemWithMembers extends System {
  member_systems: (MemberSystem & { members: Member })[];
}

export interface ActionWithSystem extends Action {
  systems: System | null;
}

/* ============================================================
 * Dashboard summary
 * ============================================================ */

export interface PeopleRiskSummary {
  totalSystems: number;
  singleOwnerSystems: number;
  busFactor1Count: number;
  avgRiskScore: number;
  totalMembers: number;
  activeMembers: number;
  leftMembers: number;
  criticalCount: number;
  warningCount: number;
  safeCount: number;
}
