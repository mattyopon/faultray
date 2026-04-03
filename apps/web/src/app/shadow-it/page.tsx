"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useEffect, useState } from "react";
import { Ghost, Loader2, AlertTriangle, Clock, FileX } from "lucide-react";
import { useLocale } from "@/lib/useLocale";
import { appDict } from "@/i18n/app-dict";

interface ShadowComponent {
  id: string;
  name: string;
  type: string;
  risk_level: "critical" | "high" | "medium" | "low";
  reason: "orphaned" | "stale" | "undocumented";
  last_seen: string;
  owner: string | null;
  risk_score: number;
}

interface ShadowItData {
  scan_date: string;
  total_components: number;
  orphaned: number;
  stale: number;
  undocumented: number;
  overall_risk_score: number;
  components: ShadowComponent[];
}

const DEMO_DATA: ShadowItData = {
  scan_date: "2026-04-01",
  total_components: 18,
  orphaned: 4,
  stale: 6,
  undocumented: 8,
  overall_risk_score: 71,
  components: [
    { id: "si-001", name: "legacy-auth-proxy", type: "proxy", risk_level: "critical", reason: "orphaned", last_seen: "2025-11-03", owner: null, risk_score: 94 },
    { id: "si-002", name: "old-reporting-db", type: "database", risk_level: "critical", reason: "orphaned", last_seen: "2025-09-15", owner: null, risk_score: 91 },
    { id: "si-003", name: "test-payment-gateway", type: "external_api", risk_level: "high", reason: "stale", last_seen: "2026-01-10", owner: "dev-team-a", risk_score: 78 },
    { id: "si-004", name: "internal-analytics-v1", type: "app_server", risk_level: "high", reason: "undocumented", last_seen: "2026-02-20", owner: null, risk_score: 72 },
    { id: "si-005", name: "webhook-forwarder", type: "app_server", risk_level: "high", reason: "stale", last_seen: "2026-01-28", owner: "ops-team", risk_score: 68 },
    { id: "si-006", name: "debug-endpoint-prod", type: "api_endpoint", risk_level: "critical", reason: "undocumented", last_seen: "2026-03-01", owner: null, risk_score: 96 },
    { id: "si-007", name: "redis-cache-legacy", type: "cache", risk_level: "medium", reason: "stale", last_seen: "2026-02-05", owner: "infra-team", risk_score: 55 },
    { id: "si-008", name: "batch-job-runner-v2", type: "worker", risk_level: "medium", reason: "undocumented", last_seen: "2026-03-10", owner: "dev-team-b", risk_score: 48 },
    { id: "si-009", name: "smtp-relay-old", type: "mail_server", risk_level: "high", reason: "orphaned", last_seen: "2025-12-20", owner: null, risk_score: 75 },
    { id: "si-010", name: "cdn-origin-backup", type: "load_balancer", risk_level: "medium", reason: "undocumented", last_seen: "2026-02-28", owner: "infra-team", risk_score: 42 },
    { id: "si-011", name: "feature-flag-service", type: "app_server", risk_level: "low", reason: "undocumented", last_seen: "2026-03-25", owner: "dev-team-a", risk_score: 28 },
    { id: "si-012", name: "log-aggregator-v1", type: "monitoring", risk_level: "medium", reason: "stale", last_seen: "2026-01-15", owner: "ops-team", risk_score: 51 },
  ],
};

function riskColor(level: string): string {
  if (level === "critical") return "#ef4444";
  if (level === "high") return "#f59e0b";
  if (level === "medium") return "#eab308";
  return "#10b981";
}

function riskBadgeVariant(level: string): "red" | "yellow" | "green" | "default" {
  if (level === "critical") return "red";
  if (level === "high") return "yellow";
  if (level === "medium") return "default";
  return "green";
}

function reasonIcon(reason: string) {
  if (reason === "orphaned") return <Ghost size={12} className="inline mr-1" />;
  if (reason === "stale") return <Clock size={12} className="inline mr-1" />;
  return <FileX size={12} className="inline mr-1" />;
}

export default function ShadowItPage() {
  const [data, setData] = useState<ShadowItData>(DEMO_DATA);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<"all" | "critical" | "high" | "medium" | "low">("all");
  const locale = useLocale();
  const t = appDict.shadowIt[locale] ?? appDict.shadowIt.en;

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/proxy?path=/api/v1/shadow-it", { signal: controller.signal })
      .then((r) => r.json())
      .then((d) => setData(d))
      .catch((err) => { console.error("[shadow-it] API error, using demo data:", err); setData(DEMO_DATA); })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, []);

  const filtered = data.components.filter((c) =>
    filter === "all" ? true : c.risk_level === filter
  );

  return (
    <div className="w-full px-6 py-10">
      <div className="mb-10">
        <h1 className="text-2xl font-bold mb-1 flex items-center gap-3">
          <Ghost size={24} className="text-[var(--gold)]" />
          {t.title}
        </h1>
        <p className="text-[var(--text-secondary)] text-sm">{t.subtitle}</p>
      </div>

      {loading ? (
        <Card className="flex items-center justify-center py-20">
          <Loader2 size={24} className="animate-spin text-[var(--gold)]" />
          <span className="ml-3 text-[var(--text-secondary)]">{t.loading}</span>
        </Card>
      ) : (
        <>
          {/* Summary Stats */}
          <div className="grid md:grid-cols-5 gap-4 mb-8">
            <Card className="text-center">
              <p className="text-3xl font-extrabold font-mono" style={{ color: data.overall_risk_score >= 70 ? "#ef4444" : data.overall_risk_score >= 50 ? "#f59e0b" : "#10b981" }}>
                {data.overall_risk_score}
              </p>
              <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider mt-1">{t.riskScore}</p>
            </Card>
            <Card className="text-center">
              <p className="text-3xl font-extrabold font-mono text-[var(--text-secondary)]">{data.total_components}</p>
              <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider mt-1">{t.total}</p>
            </Card>
            <Card className="text-center">
              <p className="text-3xl font-extrabold font-mono text-red-400">{data.orphaned}</p>
              <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider mt-1">{t.orphaned}</p>
            </Card>
            <Card className="text-center">
              <p className="text-3xl font-extrabold font-mono text-[#f59e0b]">{data.stale}</p>
              <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider mt-1">{t.stale}</p>
            </Card>
            <Card className="text-center">
              <p className="text-3xl font-extrabold font-mono text-yellow-400">{data.undocumented}</p>
              <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider mt-1">{t.undocumented}</p>
            </Card>
          </div>

          {/* Filter */}
          <div className="flex items-center gap-2 mb-4">
            <span className="text-xs text-[var(--text-muted)] uppercase tracking-wider">{t.filterBy}</span>
            {(["all", "critical", "high", "medium", "low"] as const).map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={`px-3 py-1 rounded-lg text-xs font-medium transition-all ${
                  filter === f
                    ? "bg-[var(--gold)]/10 text-[var(--gold)] border border-[var(--gold)]/30"
                    : "text-[var(--text-secondary)] border border-[var(--border-color)] hover:border-[#64748b]"
                }`}
              >
                {f.toUpperCase()}
              </button>
            ))}
          </div>

          {/* Components Table */}
          <Card>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[var(--border-color)]">
                    <th scope="col" className="text-left py-3 px-3 text-[var(--text-muted)] font-medium">{t.component}</th>
                    <th scope="col" className="text-left py-3 px-3 text-[var(--text-muted)] font-medium">{t.type}</th>
                    <th scope="col" className="text-center py-3 px-3 text-[var(--text-muted)] font-medium">{t.reason}</th>
                    <th scope="col" className="text-left py-3 px-3 text-[var(--text-muted)] font-medium">{t.owner}</th>
                    <th scope="col" className="text-left py-3 px-3 text-[var(--text-muted)] font-medium">{t.lastSeen}</th>
                    <th scope="col" className="text-center py-3 px-3 text-[var(--text-muted)] font-medium">{t.riskScore}</th>
                    <th scope="col" className="text-center py-3 px-3 text-[var(--text-muted)] font-medium">{t.level}</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((comp) => (
                    <tr key={comp.id} className="border-b border-[var(--border-color)]/50 hover:bg-white/[0.02]">
                      <td className="py-3 px-3 font-medium">{comp.name}</td>
                      <td className="py-3 px-3 font-mono text-xs text-[var(--text-muted)]">{comp.type}</td>
                      <td className="py-3 px-3 text-center">
                        <span className="text-xs text-[var(--text-secondary)]">
                          {reasonIcon(comp.reason)}
                          {comp.reason}
                        </span>
                      </td>
                      <td className="py-3 px-3 text-sm text-[var(--text-secondary)]">
                        {comp.owner ?? <span className="text-red-400 flex items-center gap-1"><AlertTriangle size={12} />{t.noOwner}</span>}
                      </td>
                      <td className="py-3 px-3 font-mono text-xs text-[var(--text-muted)]">{comp.last_seen}</td>
                      <td className="py-3 px-3 text-center">
                        <span className="font-mono font-bold" style={{ color: riskColor(comp.risk_level) }}>
                          {comp.risk_score}
                        </span>
                      </td>
                      <td className="py-3 px-3 text-center">
                        <Badge variant={riskBadgeVariant(comp.risk_level)}>
                          {comp.risk_level.toUpperCase()}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}
    </div>
  );
}
