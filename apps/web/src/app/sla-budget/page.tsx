"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useEffect, useState } from "react";
import { Timer, Loader2, TrendingDown } from "lucide-react";
import { useLocale } from "@/lib/useLocale";
import { appDict } from "@/i18n/app-dict";

interface SlaBudgetEntry {
  id: string;
  component: string;
  tier: string;
  sla_target_percent: number;
  allowed_minutes_per_month: number;
  consumed_minutes: number;
  remaining_minutes: number;
  burn_rate_percent: number;
  status: "healthy" | "warning" | "critical" | "exhausted";
  incidents_this_month: number;
}

interface SlaBudgetData {
  period: string;
  days_elapsed: number;
  days_total: number;
  overall_status: "healthy" | "warning" | "critical";
  entries: SlaBudgetEntry[];
}

const DEMO_DATA: SlaBudgetData = {
  period: "2026-04",
  days_elapsed: 1,
  days_total: 30,
  overall_status: "warning",
  entries: [
    { id: "sla-001", component: "API Gateway", tier: "Tier 0 - Critical", sla_target_percent: 99.99, allowed_minutes_per_month: 4.3, consumed_minutes: 0.0, remaining_minutes: 4.3, burn_rate_percent: 0.0, status: "healthy", incidents_this_month: 0 },
    { id: "sla-002", component: "Auth Service", tier: "Tier 0 - Critical", sla_target_percent: 99.99, allowed_minutes_per_month: 4.3, consumed_minutes: 2.1, remaining_minutes: 2.2, burn_rate_percent: 48.8, status: "warning", incidents_this_month: 1 },
    { id: "sla-003", component: "PostgreSQL Primary", tier: "Tier 0 - Critical", sla_target_percent: 99.99, allowed_minutes_per_month: 4.3, consumed_minutes: 4.8, remaining_minutes: -0.5, burn_rate_percent: 111.6, status: "exhausted", incidents_this_month: 2 },
    { id: "sla-004", component: "Payment Service", tier: "Tier 1 - High", sla_target_percent: 99.95, allowed_minutes_per_month: 21.6, consumed_minutes: 1.5, remaining_minutes: 20.1, burn_rate_percent: 6.9, status: "healthy", incidents_this_month: 0 },
    { id: "sla-005", component: "Redis Cache", tier: "Tier 1 - High", sla_target_percent: 99.95, allowed_minutes_per_month: 21.6, consumed_minutes: 15.2, remaining_minutes: 6.4, burn_rate_percent: 70.4, status: "critical", incidents_this_month: 3 },
    { id: "sla-006", component: "CDN / Edge", tier: "Tier 1 - High", sla_target_percent: 99.95, allowed_minutes_per_month: 21.6, consumed_minutes: 0.8, remaining_minutes: 20.8, burn_rate_percent: 3.7, status: "healthy", incidents_this_month: 0 },
    { id: "sla-007", component: "Background Worker", tier: "Tier 2 - Standard", sla_target_percent: 99.9, allowed_minutes_per_month: 43.2, consumed_minutes: 12.0, remaining_minutes: 31.2, burn_rate_percent: 27.8, status: "healthy", incidents_this_month: 1 },
    { id: "sla-008", component: "Email Notifications", tier: "Tier 2 - Standard", sla_target_percent: 99.9, allowed_minutes_per_month: 43.2, consumed_minutes: 38.5, remaining_minutes: 4.7, burn_rate_percent: 89.1, status: "critical", incidents_this_month: 5 },
    { id: "sla-009", component: "Monitoring Stack", tier: "Tier 2 - Standard", sla_target_percent: 99.9, allowed_minutes_per_month: 43.2, consumed_minutes: 5.0, remaining_minutes: 38.2, burn_rate_percent: 11.6, status: "healthy", incidents_this_month: 1 },
    { id: "sla-010", component: "Analytics Service", tier: "Tier 3 - Best Effort", sla_target_percent: 99.5, allowed_minutes_per_month: 216.0, consumed_minutes: 45.0, remaining_minutes: 171.0, burn_rate_percent: 20.8, status: "healthy", incidents_this_month: 2 },
  ],
};

function statusColor(status: string): string {
  if (status === "exhausted") return "#ef4444";
  if (status === "critical") return "#ef4444";
  if (status === "warning") return "#f59e0b";
  return "#10b981";
}

function statusBadge(status: string): "red" | "yellow" | "green" | "default" {
  if (status === "exhausted" || status === "critical") return "red";
  if (status === "warning") return "yellow";
  return "green";
}

function burnRateBar(burnRate: number) {
  const color = burnRate > 100 ? "#ef4444" : burnRate > 70 ? "#f59e0b" : burnRate > 40 ? "#eab308" : "#10b981";
  const width = Math.min(burnRate, 100);
  return (
    <div className="flex items-center gap-2">
      <div className="w-20 h-2 bg-white/5 rounded-full overflow-hidden">
        <div className="h-full rounded-full transition-all" style={{ width: `${width}%`, backgroundColor: color }} />
      </div>
      <span className="font-mono text-xs font-bold" style={{ color }}>{burnRate.toFixed(1)}%</span>
    </div>
  );
}

export default function SlaBudgetPage() {
  const [data, setData] = useState<SlaBudgetData>(DEMO_DATA);
  const [loading, setLoading] = useState(true);
  const [sortBy, setSortBy] = useState<"burn_rate" | "remaining" | "tier">("burn_rate");
  const locale = useLocale();
  const t = appDict.slaBudget[locale] ?? appDict.slaBudget.en;

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/proxy?path=/api/v1/sla-budget", { signal: controller.signal })
      .then((r) => r.json())
      .then((d) => setData(d))
      .catch(() => setData(DEMO_DATA))
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, []);

  const tierOrder: Record<string, number> = { "Tier 0 - Critical": 0, "Tier 1 - High": 1, "Tier 2 - Standard": 2, "Tier 3 - Best Effort": 3 };
  const sorted = [...data.entries].sort((a, b) => {
    if (sortBy === "burn_rate") return b.burn_rate_percent - a.burn_rate_percent;
    if (sortBy === "remaining") return a.remaining_minutes - b.remaining_minutes;
    return (tierOrder[a.tier] ?? 9) - (tierOrder[b.tier] ?? 9);
  });

  const exhaustedCount = data.entries.filter((e) => e.status === "exhausted").length;
  const criticalCount = data.entries.filter((e) => e.status === "critical").length;
  const warningCount = data.entries.filter((e) => e.status === "warning").length;
  const progressPercent = Math.round((data.days_elapsed / data.days_total) * 100);

  return (
    <div className="max-w-6xl mx-auto px-6 py-10">
      <div className="mb-10">
        <h1 className="text-2xl font-bold mb-1 flex items-center gap-3">
          <Timer size={24} className="text-[#FFD700]" />
          {t.title}
        </h1>
        <p className="text-[#94a3b8] text-sm">{t.subtitle}</p>
      </div>

      {loading ? (
        <Card className="flex items-center justify-center py-20">
          <Loader2 size={24} className="animate-spin text-[#FFD700]" />
          <span className="ml-3 text-[#94a3b8]">{t.loading}</span>
        </Card>
      ) : (
        <>
          {/* Period Header */}
          <Card className="mb-6">
            <div className="flex items-center justify-between mb-3">
              <div>
                <p className="font-semibold">{t.period}: {data.period}</p>
                <p className="text-xs text-[#64748b] mt-0.5">{t.daysElapsed}: {data.days_elapsed} / {data.days_total}</p>
              </div>
              <Badge variant={data.overall_status === "healthy" ? "green" : data.overall_status === "warning" ? "yellow" : "red"}>
                {data.overall_status.toUpperCase()}
              </Badge>
            </div>
            <div className="w-full h-2 bg-white/5 rounded-full overflow-hidden">
              <div className="h-full rounded-full bg-[#FFD700]/50" style={{ width: `${progressPercent}%` }} />
            </div>
            <p className="text-xs text-[#64748b] mt-1">{progressPercent}% {locale === "ja" ? "経過" : "of month elapsed"}</p>
          </Card>

          {/* Summary */}
          <div className="grid md:grid-cols-4 gap-4 mb-8">
            <Card className="text-center">
              <p className="text-3xl font-extrabold font-mono text-[#94a3b8]">{data.entries.length}</p>
              <p className="text-xs text-[#64748b] uppercase tracking-wider mt-1">{t.totalComponents}</p>
            </Card>
            <Card className="text-center">
              <p className="text-3xl font-extrabold font-mono text-red-400">{exhaustedCount}</p>
              <p className="text-xs text-[#64748b] uppercase tracking-wider mt-1">{t.exhausted}</p>
            </Card>
            <Card className="text-center">
              <p className="text-3xl font-extrabold font-mono text-red-400">{criticalCount}</p>
              <p className="text-xs text-[#64748b] uppercase tracking-wider mt-1">{t.critical}</p>
            </Card>
            <Card className="text-center">
              <p className="text-3xl font-extrabold font-mono text-[#f59e0b]">{warningCount}</p>
              <p className="text-xs text-[#64748b] uppercase tracking-wider mt-1">{t.warning}</p>
            </Card>
          </div>

          {/* Sort */}
          <div className="flex items-center gap-2 mb-4">
            <span className="text-xs text-[#64748b] uppercase tracking-wider">{t.sortBy}</span>
            {(["burn_rate", "remaining", "tier"] as const).map((s) => (
              <button
                key={s}
                onClick={() => setSortBy(s)}
                className={`px-3 py-1 rounded-lg text-xs font-medium transition-all ${
                  sortBy === s
                    ? "bg-[#FFD700]/10 text-[#FFD700] border border-[#FFD700]/30"
                    : "text-[#94a3b8] border border-[#1e293b] hover:border-[#64748b]"
                }`}
              >
                {s.replace("_", " ").toUpperCase()}
              </button>
            ))}
          </div>

          {/* SLA Budget Table */}
          <Card>
            <div className="flex items-center gap-2 mb-4">
              <TrendingDown size={16} className="text-[#FFD700]" />
              <h3 className="text-sm font-semibold text-[#94a3b8] uppercase tracking-wider">{t.budgetTable}</h3>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[#1e293b]">
                    <th scope="col" className="text-left py-3 px-3 text-[#64748b] font-medium">{t.component}</th>
                    <th scope="col" className="text-left py-3 px-3 text-[#64748b] font-medium">{t.tier}</th>
                    <th scope="col" className="text-center py-3 px-3 text-[#64748b] font-medium">{t.target}</th>
                    <th scope="col" className="text-center py-3 px-3 text-[#64748b] font-medium">{t.allowed}</th>
                    <th scope="col" className="text-center py-3 px-3 text-[#64748b] font-medium">{t.consumed}</th>
                    <th scope="col" className="text-center py-3 px-3 text-[#64748b] font-medium">{t.remaining}</th>
                    <th scope="col" className="text-left py-3 px-3 text-[#64748b] font-medium">{t.burnRate}</th>
                    <th scope="col" className="text-center py-3 px-3 text-[#64748b] font-medium">{t.status}</th>
                  </tr>
                </thead>
                <tbody>
                  {sorted.map((entry) => (
                    <tr
                      key={entry.id}
                      className={`border-b border-[#1e293b]/50 hover:bg-white/[0.02] ${entry.status === "exhausted" ? "bg-red-500/5" : ""}`}
                    >
                      <td className="py-3 px-3">
                        <p className="font-medium">{entry.component}</p>
                        {entry.incidents_this_month > 0 && (
                          <p className="text-xs text-[#64748b]">{entry.incidents_this_month} {locale === "ja" ? "件" : "incidents"}</p>
                        )}
                      </td>
                      <td className="py-3 px-3 text-xs text-[#64748b]">{entry.tier}</td>
                      <td className="py-3 px-3 text-center font-mono text-xs text-[#94a3b8]">{entry.sla_target_percent}%</td>
                      <td className="py-3 px-3 text-center font-mono text-xs text-[#94a3b8]">{entry.allowed_minutes_per_month.toFixed(1)}m</td>
                      <td className="py-3 px-3 text-center font-mono text-xs" style={{ color: statusColor(entry.status) }}>
                        {entry.consumed_minutes.toFixed(1)}m
                      </td>
                      <td className="py-3 px-3 text-center font-mono text-xs font-bold" style={{ color: entry.remaining_minutes < 0 ? "#ef4444" : statusColor(entry.status) }}>
                        {entry.remaining_minutes.toFixed(1)}m
                      </td>
                      <td className="py-3 px-3">{burnRateBar(entry.burn_rate_percent)}</td>
                      <td className="py-3 px-3 text-center">
                        <Badge variant={statusBadge(entry.status)}>{entry.status.toUpperCase()}</Badge>
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
