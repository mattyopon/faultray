"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useState } from "react";
import { Clock, Zap, AlertTriangle, FlaskConical, Settings, Bell } from "lucide-react";
import { useLocale } from "@/lib/useLocale";
import { appDict } from "@/i18n/app-dict";

type EventType = "deployment" | "incident" | "simulation" | "config" | "alert";

const TIMELINE_EVENTS = [
  { id: "TL-001", type: "incident" as EventType, title: "Database Primary Crash", component: "db_primary", severity: "critical", timestamp: "2026-04-01 09:15 UTC", description: "Disk I/O saturation caused cascading database failure." },
  { id: "TL-002", type: "alert" as EventType, title: "High Memory Alert — api-pod-3", component: "api", severity: "high", timestamp: "2026-04-01 08:52 UTC", description: "Memory usage crossed 90% threshold. Auto-scaling triggered." },
  { id: "TL-003", type: "deployment" as EventType, title: "API v3.1.2 Released", component: "api", severity: "info", timestamp: "2026-04-01 07:00 UTC", description: "Canary deployment at 10% traffic, promoted to 100% after 30 min." },
  { id: "TL-004", type: "config" as EventType, title: "Redis maxmemory increased", component: "cache", severity: "medium", timestamp: "2026-03-31 15:10 UTC", description: "Config patched directly outside GitOps pipeline — drift event created." },
  { id: "TL-005", type: "simulation" as EventType, title: "FaultRay: AZ-1a Network Partition", component: "network", severity: "info", timestamp: "2026-03-31 14:00 UTC", description: "Scheduled chaos simulation. Result: 87/100. Improved from last run." },
  { id: "TL-006", type: "alert" as EventType, title: "SLA Breach Warning — latency P99", component: "api", severity: "high", timestamp: "2026-03-31 12:30 UTC", description: "P99 latency exceeded 500ms threshold for 5 consecutive minutes." },
  { id: "TL-007", type: "deployment" as EventType, title: "Worker Service v2.8.0", component: "worker", severity: "info", timestamp: "2026-03-31 10:00 UTC", description: "New batch export feature with I/O rate limiting." },
  { id: "TL-008", type: "incident" as EventType, title: "Cache Network Partition", component: "cache", severity: "high", timestamp: "2026-03-31 09:15 UTC", description: "VPC security group misconfiguration blocked inter-AZ Redis traffic." },
  { id: "TL-009", type: "config" as EventType, title: "Auto-scaling policy updated", component: "k8s", severity: "low", timestamp: "2026-03-30 16:00 UTC", description: "Scale-up threshold lowered from 80% to 70% CPU utilization." },
  { id: "TL-010", type: "simulation" as EventType, title: "FaultRay: DB Read Replica Failure", component: "db_replica", severity: "info", timestamp: "2026-03-30 14:00 UTC", description: "Scheduled chaos simulation. Result: 91/100. All SLOs met." },
  { id: "TL-011", type: "deployment" as EventType, title: "Frontend v5.2.1 — Hotfix", component: "frontend", severity: "medium", timestamp: "2026-03-30 11:30 UTC", description: "Emergency hotfix for authentication redirect loop on Safari." },
  { id: "TL-012", type: "alert" as EventType, title: "Disk usage > 85% on db-node-1", component: "db_primary", severity: "medium", timestamp: "2026-03-30 09:00 UTC", description: "Automated disk cleanup triggered. Freed 18GB." },
  { id: "TL-013", type: "incident" as EventType, title: "DNS Resolution Failure", component: "dns", severity: "high", timestamp: "2026-03-29 22:10 UTC", description: "DNS provider maintenance caused TTL expiry." },
  { id: "TL-014", type: "config" as EventType, title: "Firewall rules updated", component: "network", severity: "low", timestamp: "2026-03-29 16:45 UTC", description: "Allowed egress to new third-party payment provider IPs." },
  { id: "TL-015", type: "deployment" as EventType, title: "Auth Service v1.4.0", component: "auth", severity: "info", timestamp: "2026-03-28 09:00 UTC", description: "Added PKCE flow support and OAuth2.1 compliance." },
  { id: "TL-016", type: "simulation" as EventType, title: "FaultRay: Full Stack Chaos", component: "all", severity: "info", timestamp: "2026-03-27 14:00 UTC", description: "Weekly chaos simulation. Score: 79/100. 2 issues found." },
  { id: "TL-017", type: "alert" as EventType, title: "Certificate expiry in 30 days", component: "ssl", severity: "medium", timestamp: "2026-03-26 08:00 UTC", description: "TLS cert for api.yourdomain.com expires 2026-04-25." },
  { id: "TL-018", type: "deployment" as EventType, title: "Terraform infra update", component: "k8s", severity: "medium", timestamp: "2026-03-25 11:00 UTC", description: "Node group instance type upgraded from m5.large to m5.xlarge." },
];

const TYPE_ICONS: Record<EventType, typeof Zap> = {
  deployment: Zap,
  incident: AlertTriangle,
  simulation: FlaskConical,
  config: Settings,
  alert: Bell,
};

const TYPE_COLORS: Record<EventType, string> = {
  deployment: "#10b981",
  incident: "#ef4444",
  simulation: "#FFD700",
  config: "#3b82f6",
  alert: "#f59e0b",
};

const SEV_BADGE: Record<string, "red" | "yellow" | "green" | "default"> = {
  critical: "red",
  high: "yellow",
  medium: "default",
  low: "default",
  info: "green",
};

export default function TimelinePage() {
  const locale = useLocale();
  const t = appDict.timeline[locale] ?? appDict.timeline.en;
  const [typeFilter, setTypeFilter] = useState<EventType | "all">("all");
  const [timeRange, setTimeRange] = useState<"24h" | "3d" | "7d">("7d");

  const filtered = TIMELINE_EVENTS.filter((ev) => {
    if (typeFilter !== "all" && ev.type !== typeFilter) return false;
    return true;
  });

  const filterButtons: { key: EventType | "all"; label: string }[] = [
    { key: "all", label: t.filterAll },
    { key: "deployment", label: t.filterDeployment },
    { key: "incident", label: t.filterIncident },
    { key: "simulation", label: t.filterSimulation },
    { key: "config", label: t.filterConfig },
    { key: "alert", label: t.filterAlert },
  ];

  return (
    <div className="w-full px-6 py-10">
      <div className="mb-8">
        <h1 className="text-2xl font-bold mb-1 flex items-center gap-3">
          <Clock size={24} className="text-[var(--gold)]" />
          {t.title}
        </h1>
        <p className="text-[var(--text-secondary)] text-sm">{t.subtitle}</p>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-6">
        <div className="flex flex-wrap gap-2">
          {filterButtons.map(({ key, label }) => (
            <button
              key={key}
              onClick={() => setTypeFilter(key)}
              className={`px-3 py-1.5 text-xs rounded-md border transition-colors ${
                typeFilter === key
                  ? "border-[var(--gold)]/50 bg-[var(--gold)]/10 text-[var(--gold)]"
                  : "border-[var(--border-color)] text-[var(--text-muted)] hover:text-white"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="ml-auto flex gap-2">
          {(["24h", "3d", "7d"] as const).map((range) => (
            <button
              key={range}
              onClick={() => setTimeRange(range)}
              className={`px-3 py-1.5 text-xs rounded-md border transition-colors ${
                timeRange === range
                  ? "border-[var(--gold)]/50 bg-[var(--gold)]/10 text-[var(--gold)]"
                  : "border-[var(--border-color)] text-[var(--text-muted)] hover:text-white"
              }`}
            >
              {range === "24h" ? t.last24h : range === "3d" ? t.last3d : t.last7d}
            </button>
          ))}
        </div>
      </div>

      {/* Summary counts */}
      <div className="flex flex-wrap gap-4 mb-6">
        {(["deployment", "incident", "simulation", "config", "alert"] as EventType[]).map((type) => {
          const count = TIMELINE_EVENTS.filter((e) => e.type === type).length;
          return (
            <div key={type} className="flex items-center gap-2 text-sm">
              <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: TYPE_COLORS[type] }} />
              <span className="text-[var(--text-muted)] capitalize">{type}</span>
              <span className="text-white font-mono font-bold">{count}</span>
            </div>
          );
        })}
      </div>

      {/* Timeline */}
      {filtered.length === 0 ? (
        <Card className="text-center py-12">
          <p className="text-[var(--text-muted)]">{t.noEvents}</p>
        </Card>
      ) : (
        <div className="relative pl-8">
          {/* Vertical line */}
          <div className="absolute left-[15px] top-0 bottom-0 w-0.5 bg-[var(--border-color)]" />

          <div className="space-y-4">
            {filtered.map((ev) => {
              const Icon = TYPE_ICONS[ev.type];
              const color = TYPE_COLORS[ev.type];
              return (
                <div key={ev.id} className="relative">
                  {/* Icon dot */}
                  <div
                    className="absolute left-[-23px] w-7 h-7 rounded-full flex items-center justify-center border-2 border-[#0a0e1a]"
                    style={{ backgroundColor: `${color}20`, borderColor: color }}
                  >
                    <Icon size={12} style={{ color }} />
                  </div>

                  <Card>
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1 flex-wrap">
                          <Badge variant={SEV_BADGE[ev.severity] ?? "default"}>{ev.severity}</Badge>
                          <Badge variant="default" className="capitalize" style={{ color }}>{ev.type}</Badge>
                          <Badge variant="default">{ev.component}</Badge>
                        </div>
                        <p className="font-semibold text-sm mb-1">{ev.title}</p>
                        <p className="text-xs text-[var(--text-secondary)]">{ev.description}</p>
                      </div>
                      <p className="text-xs text-[var(--text-muted)] shrink-0 font-mono whitespace-nowrap">{ev.timestamp}</p>
                    </div>
                  </Card>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
