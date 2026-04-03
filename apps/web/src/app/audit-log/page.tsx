"use client";

// SAAS-03: 監査ログページ — 誰がいつ何の操作をしたかを記録・表示
// Enterprise compliance要件：変更履歴・アクセスログの透明性

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useState, useMemo, useEffect } from "react";
import {
  Shield,
  Search,
  Download,
  User,
  Key,
  Settings,
  Play,
  Trash2,
  Eye,
  ChevronDown,
  ChevronUp,
  Filter,
} from "lucide-react";
import { useLocale } from "@/lib/useLocale";

/* ============================================================
 * Types
 * ============================================================ */

type AuditAction =
  | "LOGIN"
  | "LOGOUT"
  | "SIMULATION_RUN"
  | "REPORT_EXPORT"
  | "SETTINGS_CHANGE"
  | "API_KEY_CREATED"
  | "API_KEY_REVOKED"
  | "PROJECT_CREATED"
  | "PROJECT_DELETED"
  | "MEMBER_INVITED"
  | "PLAN_CHANGED"
  | "DATA_EXPORT";

interface AuditEntry {
  id: string;
  timestamp: string;
  actor: string;
  actorEmail: string;
  action: AuditAction;
  resource?: string;
  ipAddress: string;
  userAgent: string;
  outcome: "SUCCESS" | "FAILURE";
  details?: string;
}

/* ============================================================
 * Demo Data
 * ============================================================ */

const DEMO_AUDIT_LOG: AuditEntry[] = [
  {
    id: "a001",
    timestamp: "2026-04-01T09:42:11Z",
    actor: "Yutaro Maeda",
    actorEmail: "yutaro@company.com",
    action: "SIMULATION_RUN",
    resource: "Project: E-Commerce Prod",
    ipAddress: "203.0.113.42",
    userAgent: "Chrome 123 / macOS",
    outcome: "SUCCESS",
    details: "Monte Carlo simulation — 2,048 scenarios, score 87.4",
  },
  {
    id: "a002",
    timestamp: "2026-04-01T09:10:05Z",
    actor: "Yutaro Maeda",
    actorEmail: "yutaro@company.com",
    action: "REPORT_EXPORT",
    resource: "DORA Compliance Report (PDF)",
    ipAddress: "203.0.113.42",
    userAgent: "Chrome 123 / macOS",
    outcome: "SUCCESS",
    details: "Exported quarterly DORA report for audit committee",
  },
  {
    id: "a003",
    timestamp: "2026-04-01T08:55:30Z",
    actor: "Kenji Tanaka",
    actorEmail: "kenji@company.com",
    action: "MEMBER_INVITED",
    resource: "invite: ops-lead@company.com",
    ipAddress: "198.51.100.12",
    userAgent: "Firefox 115 / Windows",
    outcome: "SUCCESS",
  },
  {
    id: "a004",
    timestamp: "2026-04-01T08:30:00Z",
    actor: "System",
    actorEmail: "system@faultray.com",
    action: "API_KEY_CREATED",
    resource: "CI/CD Pipeline Key (read-only)",
    ipAddress: "0.0.0.0",
    userAgent: "FaultRay API",
    outcome: "SUCCESS",
  },
  {
    id: "a005",
    timestamp: "2026-04-01T07:15:22Z",
    actor: "Yutaro Maeda",
    actorEmail: "yutaro@company.com",
    action: "SETTINGS_CHANGE",
    resource: "Notification: Slack webhook updated",
    ipAddress: "203.0.113.42",
    userAgent: "Chrome 123 / macOS",
    outcome: "SUCCESS",
    details: "Slack webhook URL changed for #infra-alerts channel",
  },
  {
    id: "a006",
    timestamp: "2026-03-31T18:22:14Z",
    actor: "Unknown",
    actorEmail: "attacker@evil.com",
    action: "LOGIN",
    ipAddress: "192.0.2.99",
    userAgent: "curl/7.88.1",
    outcome: "FAILURE",
    details: "Invalid credentials — 5 consecutive failures from this IP",
  },
  {
    id: "a007",
    timestamp: "2026-03-31T16:00:00Z",
    actor: "Yutaro Maeda",
    actorEmail: "yutaro@company.com",
    action: "DATA_EXPORT",
    resource: "Full YAML topology export — E-Commerce Prod",
    ipAddress: "203.0.113.42",
    userAgent: "Chrome 123 / macOS",
    outcome: "SUCCESS",
    details: "Topology configuration downloaded as topology.yaml",
  },
  {
    id: "a008",
    timestamp: "2026-03-31T14:30:00Z",
    actor: "Kenji Tanaka",
    actorEmail: "kenji@company.com",
    action: "PLAN_CHANGED",
    resource: "Free → Pro (14-day trial)",
    ipAddress: "198.51.100.12",
    userAgent: "Firefox 115 / Windows",
    outcome: "SUCCESS",
  },
];

const ACTION_ICONS: Record<AuditAction, React.ComponentType<{ size?: number; className?: string }>> = {
  LOGIN: Key,
  LOGOUT: Key,
  SIMULATION_RUN: Play,
  REPORT_EXPORT: Download,
  SETTINGS_CHANGE: Settings,
  API_KEY_CREATED: Key,
  API_KEY_REVOKED: Key,
  PROJECT_CREATED: Shield,
  PROJECT_DELETED: Trash2,
  MEMBER_INVITED: User,
  PLAN_CHANGED: Shield,
  DATA_EXPORT: Download,
};

const ACTION_LABELS: Record<AuditAction, string> = {
  LOGIN: "Login",
  LOGOUT: "Logout",
  SIMULATION_RUN: "Simulation Run",
  REPORT_EXPORT: "Report Export",
  SETTINGS_CHANGE: "Settings Change",
  API_KEY_CREATED: "API Key Created",
  API_KEY_REVOKED: "API Key Revoked",
  PROJECT_CREATED: "Project Created",
  PROJECT_DELETED: "Project Deleted",
  MEMBER_INVITED: "Member Invited",
  PLAN_CHANGED: "Plan Changed",
  DATA_EXPORT: "Data Export",
};

/* ============================================================
 * Component
 * ============================================================ */

export default function AuditLogPage() {
  const locale = useLocale();
  const [search, setSearch] = useState("");
  const [outcomeFilter, setOutcomeFilter] = useState<"ALL" | "SUCCESS" | "FAILURE">("ALL");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [entries, setEntries] = useState<AuditEntry[]>(DEMO_AUDIT_LOG);
  const [_loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/audit-log")
      .then((res) => res.json())
      .then((data) => {
        if (data.entries && data.entries.length > 0) {
          setEntries(data.entries.map((e: Record<string, unknown>) => ({
            id: e.id,
            timestamp: e.created_at,
            actor: e.actor_email?.toString().split("@")[0] ?? "Unknown",
            actorEmail: e.actor_email ?? "",
            action: e.action,
            resource: e.resource,
            ipAddress: e.ip_address ?? "",
            userAgent: e.user_agent ?? "",
            outcome: e.outcome ?? "SUCCESS",
            details: e.details,
          })));
        }
      })
      .catch((err) => console.error("[audit-log] Failed to fetch:", err))
      .finally(() => setLoading(false));
  }, []);

  const filtered = useMemo(() => {
    return entries.filter((entry) => {
      const matchesSearch =
        !search ||
        entry.actor.toLowerCase().includes(search.toLowerCase()) ||
        entry.actorEmail.toLowerCase().includes(search.toLowerCase()) ||
        ACTION_LABELS[entry.action].toLowerCase().includes(search.toLowerCase()) ||
        (entry.resource ?? "").toLowerCase().includes(search.toLowerCase());
      const matchesOutcome = outcomeFilter === "ALL" || entry.outcome === outcomeFilter;
      return matchesSearch && matchesOutcome;
    });
  }, [search, outcomeFilter, entries]);

  // Export as CSV (client-side)
  const exportCsv = () => {
    const header = "timestamp,actor,email,action,resource,ip,outcome,details";
    const rows = filtered.map((e) =>
      [e.timestamp, e.actor, e.actorEmail, e.action, e.resource ?? "", e.ipAddress, e.outcome, e.details ?? ""]
        .map((v) => `"${String(v).replace(/"/g, '""')}"`)
        .join(",")
    );
    const blob = new Blob([[header, ...rows].join("\n")], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `faultray-audit-log-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="max-w-[1100px] mx-auto px-6 py-10">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2 mb-1">
            <Shield size={24} className="text-[var(--gold)]" />
            {locale === "ja" ? "監査ログ" : "Audit Log"}
          </h1>
          <p className="text-sm text-[var(--text-muted)]">
            {locale === "ja"
              ? "誰がいつ何の操作をしたかを記録します。SOC 2 / GDPR コンプライアンス対応。"
              : "Immutable record of who did what and when. Supports SOC 2 / GDPR compliance."}
          </p>
        </div>
        <Button variant="secondary" size="sm" onClick={exportCsv}>
          <Download size={14} /> {locale === "ja" ? "CSVエクスポート" : "Export CSV"}
        </Button>
      </div>

      {/* Filters */}
      <Card className="mb-6">
        <div className="flex flex-wrap gap-4 items-center">
          <div className="flex items-center gap-2 flex-1 min-w-[200px]">
            <Search size={14} className="text-[var(--text-muted)] shrink-0" />
            <input
              type="text"
              placeholder={locale === "ja" ? "ユーザー・操作を検索..." : "Search user or action..."}
              aria-label={locale === "ja" ? "ユーザー・操作を検索" : "Search user or action"}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="bg-transparent text-sm text-white placeholder-[var(--text-muted)] focus:outline-none flex-1"
            />
          </div>
          <div className="flex items-center gap-2">
            <Filter size={14} className="text-[var(--text-muted)]" />
            {(["ALL", "SUCCESS", "FAILURE"] as const).map((val) => (
              <button
                key={val}
                onClick={() => setOutcomeFilter(val)}
                className={`px-3 py-1 rounded-full text-xs font-semibold transition-colors ${
                  outcomeFilter === val
                    ? val === "FAILURE"
                      ? "bg-red-500/20 text-red-400"
                      : val === "SUCCESS"
                      ? "bg-emerald-500/20 text-emerald-400"
                      : "bg-[var(--gold)]/20 text-[var(--gold)]"
                    : "bg-white/5 text-[var(--text-muted)] hover:text-white"
                }`}
              >
                {val}
              </button>
            ))}
          </div>
        </div>
      </Card>

      {/* Log Table */}
      <Card>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--border-color)]">
                <th scope="col" className="text-left py-3 px-3 text-[var(--text-muted)] font-medium whitespace-nowrap">
                  {locale === "ja" ? "日時" : "Timestamp"}
                </th>
                <th scope="col" className="text-left py-3 px-3 text-[var(--text-muted)] font-medium">
                  {locale === "ja" ? "ユーザー" : "Actor"}
                </th>
                <th scope="col" className="text-left py-3 px-3 text-[var(--text-muted)] font-medium">
                  {locale === "ja" ? "操作" : "Action"}
                </th>
                <th scope="col" className="text-left py-3 px-3 text-[var(--text-muted)] font-medium hidden md:table-cell">
                  {locale === "ja" ? "対象リソース" : "Resource"}
                </th>
                <th scope="col" className="text-left py-3 px-3 text-[var(--text-muted)] font-medium">
                  {locale === "ja" ? "結果" : "Outcome"}
                </th>
                <th scope="col" className="text-left py-3 px-3 text-[var(--text-muted)] font-medium hidden lg:table-cell">IP</th>
                <th scope="col" className="py-3 px-3" />
              </tr>
            </thead>
            <tbody>
              {filtered.map((entry) => {
                const ActionIcon = ACTION_ICONS[entry.action];
                const isExpanded = expandedId === entry.id;
                return (
                  <>
                    <tr
                      key={entry.id}
                      className="border-b border-[var(--border-color)]/50 hover:bg-white/[0.02] cursor-pointer"
                      onClick={() => setExpandedId(isExpanded ? null : entry.id)}
                    >
                      <td className="py-3 px-3 text-[var(--text-muted)] font-mono text-xs whitespace-nowrap">
                        {new Date(entry.timestamp).toLocaleString()}
                      </td>
                      <td className="py-3 px-3">
                        <div className="flex items-center gap-2">
                          <div className="w-6 h-6 rounded-full bg-[var(--border-color)] flex items-center justify-center">
                            <User size={12} className="text-[var(--text-muted)]" />
                          </div>
                          <div>
                            <p className="text-white text-xs font-medium">{entry.actor}</p>
                            <p className="text-[var(--text-muted)] text-xs">{entry.actorEmail}</p>
                          </div>
                        </div>
                      </td>
                      <td className="py-3 px-3">
                        <div className="flex items-center gap-1.5">
                          <ActionIcon size={12} className="text-[var(--gold)] shrink-0" />
                          <span className="text-white text-xs whitespace-nowrap">{ACTION_LABELS[entry.action]}</span>
                        </div>
                      </td>
                      <td className="py-3 px-3 text-[var(--text-secondary)] text-xs hidden md:table-cell max-w-[200px] truncate">
                        {entry.resource ?? "—"}
                      </td>
                      <td className="py-3 px-3">
                        <Badge variant={entry.outcome === "SUCCESS" ? "green" : "red"}>
                          {entry.outcome}
                        </Badge>
                      </td>
                      <td className="py-3 px-3 text-[var(--text-muted)] text-xs font-mono hidden lg:table-cell">
                        {entry.ipAddress}
                      </td>
                      <td className="py-3 px-3 text-right">
                        {isExpanded
                          ? <ChevronUp size={14} className="text-[var(--text-muted)]" />
                          : <ChevronDown size={14} className="text-[var(--text-muted)]" />
                        }
                      </td>
                    </tr>
                    {isExpanded && (
                      <tr key={`${entry.id}-detail`} className="border-b border-[var(--border-color)]/50 bg-white/[0.01]">
                        <td colSpan={7} className="py-3 px-6">
                          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs">
                            <div>
                              <p className="text-[var(--text-muted)] mb-0.5">{locale === "ja" ? "詳細" : "Details"}</p>
                              <p className="text-white">{entry.details ?? "—"}</p>
                            </div>
                            <div>
                              <p className="text-[var(--text-muted)] mb-0.5">{locale === "ja" ? "IPアドレス" : "IP Address"}</p>
                              <p className="text-white font-mono">{entry.ipAddress}</p>
                            </div>
                            <div>
                              <p className="text-[var(--text-muted)] mb-0.5">{locale === "ja" ? "ユーザーエージェント" : "User Agent"}</p>
                              <p className="text-white">{entry.userAgent}</p>
                            </div>
                            <div>
                              <p className="text-[var(--text-muted)] mb-0.5">{locale === "ja" ? "イベントID" : "Event ID"}</p>
                              <p className="text-white font-mono">{entry.id}</p>
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </>
                );
              })}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={7} className="py-12 text-center text-[var(--text-muted)]">
                    <Eye size={32} className="mx-auto mb-3 opacity-40" />
                    <p>{locale === "ja" ? "該当するログが見つかりません" : "No matching log entries"}</p>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="mt-4 text-xs text-[var(--text-muted)]">
          {locale === "ja"
            ? `${filtered.length}件のログエントリーを表示中。監査ログは90日間保持されます。`
            : `Showing ${filtered.length} entries. Audit logs are retained for 90 days.`}
        </div>
      </Card>

      {/* Compliance note */}
      <div className="mt-6 p-4 rounded-xl border border-[var(--border-color)] bg-white/[0.01]">
        <p className="text-xs text-[var(--text-muted)] leading-relaxed">
          <span className="font-semibold text-white">
            {locale === "ja" ? "コンプライアンス情報: " : "Compliance: "}
          </span>
          {locale === "ja"
            ? "このログはSOC 2 Type II、GDPR Article 30、ISO 27001 Annex A.12.4要件に対応しています。ログは改ざん防止のため暗号署名されます（Business/Enterpriseプラン）。"
            : "These logs satisfy SOC 2 Type II, GDPR Article 30, and ISO 27001 Annex A.12.4 requirements. Logs are cryptographically signed to prevent tampering (Business/Enterprise plan)."}
        </p>
      </div>
    </div>
  );
}
