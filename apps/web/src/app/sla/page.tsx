"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useState, useEffect } from "react";
import {
  FileCheck,
  CheckCircle2,
  AlertTriangle,
  TrendingDown,
  TrendingUp,
  Shield,
  Clock,
  Zap,
  Activity,
} from "lucide-react";
import { useLocale } from "@/lib/useLocale";
import { appDict } from "@/i18n/app-dict";

/* ============================================================
 * Types
 * ============================================================ */

interface SlaOverview {
  target: number;
  current: number;
  error_budget_total_minutes: number;
  error_budget_used_minutes: number;
  error_budget_remaining_pct: number;
  status: "healthy" | "warning" | "critical";
  trend: "stable" | "improving" | "degrading";
  projected_breach_date: string | null;
}

interface SloItem {
  name: string;
  target: number;
  current: number;
  unit: string;
  status: "compliant" | "warning" | "critical";
}

interface BudgetHistory {
  day: number;
  budget_used_pct: number;
}

interface ValidationResult {
  can_meet_sla: boolean;
  bottleneck_layer: string;
  availability_by_layer: {
    hardware: { nines: number; availability: number };
    software: { nines: number; availability: number };
    theoretical: { nines: number; availability: number };
  };
  limiting_factor: string;
  proof: string;
  recommendations: string[];
}

interface SlaContract {
  id: string;
  provider: string;
  target: number;
  penalty_terms: string;
  expiry: string;
  status: "active" | "expired" | "pending";
}

interface SlaData {
  assessed_at: string;
  sla_overview: SlaOverview;
  slo_breakdown: SloItem[];
  error_budget_history: BudgetHistory[];
  validation: ValidationResult;
  contracts: SlaContract[];
}

/* ============================================================
 * Static demo fallback
 * ============================================================ */

const DEMO: SlaData = {
  assessed_at: "2026-04-01T09:00:00Z",
  sla_overview: {
    target: 99.95,
    current: 99.97,
    error_budget_total_minutes: 262.8,
    error_budget_used_minutes: 104.5,
    error_budget_remaining_pct: 60.2,
    status: "healthy",
    trend: "stable",
    projected_breach_date: null,
  },
  slo_breakdown: [
    { name: "HTTP Success Rate", target: 99.9, current: 99.96, unit: "%", status: "compliant" },
    { name: "Latency P50", target: 100, current: 68, unit: "ms", status: "compliant" },
    { name: "Latency P95", target: 300, current: 245, unit: "ms", status: "compliant" },
    { name: "Latency P99", target: 1000, current: 892, unit: "ms", status: "warning" },
    { name: "Error Rate", target: 0.1, current: 0.04, unit: "%", status: "compliant" },
    { name: "Throughput", target: 500, current: 1240, unit: "req/s", status: "compliant" },
    { name: "DB Query Time P95", target: 50, current: 43, unit: "ms", status: "compliant" },
    { name: "Cache Hit Rate", target: 90, current: 94.5, unit: "%", status: "compliant" },
  ],
  error_budget_history: Array.from({ length: 30 }, (_, i) => ({
    day: i + 1,
    budget_used_pct: i < 19 ? Math.min(39.8, 2.1 + i * 2.0) : 39.8,
  })),
  validation: {
    can_meet_sla: true,
    bottleneck_layer: "Software (P99 latency approaching limit)",
    availability_by_layer: {
      hardware: { nines: 5.91, availability: 99.9999 },
      software: { nines: 4.0, availability: 99.99 },
      theoretical: { nines: 3.85, availability: 99.986 },
    },
    limiting_factor: "software",
    proof: "Current software layer availability (99.99%) exceeds SLA target (99.95%). P99 latency at 892ms is approaching 1000ms threshold — continued growth may cause SLO breach within 45 days.",
    recommendations: [
      "Optimize P99 latency: add DB query caching for slow endpoints",
      "Set up burn-rate alerts at 5% and 10% hourly budget consumption",
      "Review and reduce error budget usage from deploy events",
    ],
  },
  contracts: [
    { id: "C-001", provider: "AWS us-east-1", target: 99.99, penalty_terms: "10% credit per 0.01% below target", expiry: "2027-03-31", status: "active" },
    { id: "C-002", provider: "Cloudflare CDN", target: 99.9, penalty_terms: "Service credit up to 25% monthly fee", expiry: "2026-12-31", status: "active" },
    { id: "C-003", provider: "Stripe Payments API", target: 99.99, penalty_terms: "0.01% fee reduction per minute of downtime", expiry: "2027-06-30", status: "active" },
    { id: "C-004", provider: "Twilio SMS Gateway", target: 99.95, penalty_terms: "Pro-rata credit for downtime", expiry: "2026-09-30", status: "active" },
  ],
};

/* ============================================================
 * Error Budget Burn-Down SVG
 * ============================================================ */

function ErrorBudgetChart({
  history,
  t,
}: {
  history: BudgetHistory[];
  t: Record<string, string>;
}) {
  const w = 600;
  const h = 200;
  const pad = { top: 20, right: 20, bottom: 40, left: 50 };
  const chartW = w - pad.left - pad.right;
  const chartH = h - pad.top - pad.bottom;
  const days = history.length;

  const toX = (day: number) => pad.left + ((day - 1) / (days - 1)) * chartW;
  const toY = (pct: number) => pad.top + chartH - (pct / 100) * chartH;

  const pathD = history
    .map((d, i) => `${i === 0 ? "M" : "L"}${toX(d.day).toFixed(1)},${toY(d.budget_used_pct).toFixed(1)}`)
    .join(" ");

  const areaD =
    pathD +
    ` L${toX(days).toFixed(1)},${(pad.top + chartH).toFixed(1)} L${pad.left},${(pad.top + chartH).toFixed(1)} Z`;

  const dangerY = toY(80);
  const warningY = toY(50);

  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full" aria-label={t.burndownChart}>
      <defs>
        <linearGradient id="budgetGrad" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="#FFD700" stopOpacity={0.3} />
          <stop offset="100%" stopColor="#FFD700" stopOpacity={0.02} />
        </linearGradient>
      </defs>

      {/* Danger zone */}
      <rect x={pad.left} y={dangerY} width={chartW} height={pad.top + chartH - dangerY} fill="#ef4444" fillOpacity={0.05} />

      {/* Warning zone */}
      <rect x={pad.left} y={warningY} width={chartW} height={dangerY - warningY} fill="#f59e0b" fillOpacity={0.05} />

      {/* Grid lines */}
      {[0, 25, 50, 75, 100].map((pct) => {
        const y = toY(pct);
        return (
          <g key={pct}>
            <line x1={pad.left} x2={w - pad.right} y1={y} y2={y} stroke="#1e293b" strokeWidth={1} />
            <text x={pad.left - 6} y={y + 4} textAnchor="end" fill="#64748b" fontSize={10} fontFamily="monospace">
              {pct}%
            </text>
          </g>
        );
      })}

      {/* X axis labels */}
      {[1, 7, 14, 21, 30].map((day) => (
        <text key={day} x={toX(day)} y={h - 8} textAnchor="middle" fill="#64748b" fontSize={10}>
          {t.day} {day}
        </text>
      ))}

      {/* Area fill */}
      <path d={areaD} fill="url(#budgetGrad)" />

      {/* Line */}
      <path d={pathD} fill="none" stroke="#FFD700" strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round" />

      {/* Current point */}
      {history.length > 0 && (
        <circle
          cx={toX(history[history.length - 1].day)}
          cy={toY(history[history.length - 1].budget_used_pct)}
          r={5}
          fill="#FFD700"
          stroke="#0a0e1a"
          strokeWidth={2}
        />
      )}

      {/* Threshold labels */}
      <text x={w - pad.right - 2} y={dangerY - 4} textAnchor="end" fill="#ef4444" fontSize={9}>80%</text>
      <text x={w - pad.right - 2} y={warningY - 4} textAnchor="end" fill="#f59e0b" fontSize={9}>50%</text>
    </svg>
  );
}

/* ============================================================
 * Helpers
 * ============================================================ */

function statusVariant(status: string): "green" | "yellow" | "red" | "default" {
  if (status === "compliant" || status === "active" || status === "healthy") return "green";
  if (status === "warning") return "yellow";
  if (status === "critical" || status === "expired") return "red";
  return "default";
}

function sloCompliance(slo: SloItem): boolean {
  // For latency/error-rate: current should be <= target
  // For throughput/hit-rate: current should be >= target
  if (slo.unit === "req/s" || slo.name.includes("Hit Rate")) {
    return slo.current >= slo.target;
  }
  return slo.current <= slo.target;
}

function SloIcon({ name }: { name: string }) {
  if (name.includes("Latency")) return <Clock size={14} className="text-[var(--text-muted)] shrink-0" />;
  if (name.includes("Error")) return <AlertTriangle size={14} className="text-[var(--text-muted)] shrink-0" />;
  if (name.includes("Throughput")) return <Zap size={14} className="text-[var(--text-muted)] shrink-0" />;
  return <Activity size={14} className="text-[var(--text-muted)] shrink-0" />;
}

/* ============================================================
 * Main Page
 * ============================================================ */

export default function SlaPage() {
  const locale = useLocale();
  const t = appDict.sla[locale] ?? appDict.sla.en;
  const [data, setData] = useState<SlaData>(DEMO);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/governance?action=sla", { signal: controller.signal })
      .then((r) => r.json())
      .then((d) => { if (d && d.sla_overview) setData(d); })
      .catch((err) => console.error("[sla] fetch error:", err))
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, []);

  const ov = data.sla_overview;
  const isMeetingSla = ov.current >= ov.target;
  const budgetUsedPct = 100 - ov.error_budget_remaining_pct;

  return (
    <div className="w-full px-6 py-10">
      {/* Header */}
      <div className="mb-10">
        <h1 className="text-2xl font-bold mb-1 flex items-center gap-3">
          <FileCheck size={24} className="text-[var(--gold)]" />
          {t.title}
        </h1>
        <p className="text-[var(--text-secondary)] text-sm">{t.subtitle}</p>
        {loading && <p className="text-xs text-[var(--text-muted)] mt-1">{t.loading}</p>}
      </div>

      {/* ── 1. SLA Overview ── */}
      <div className="grid md:grid-cols-4 gap-6 mb-8">
        <Card className="text-center">
          <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider mb-2">{t.slaTarget}</p>
          <p className="text-4xl font-extrabold font-mono text-[var(--gold)]">{ov.target}%</p>
          <p className="text-xs text-[var(--text-muted)] mt-2">{t.contractedSla}</p>
        </Card>
        <Card className="text-center">
          <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider mb-2">{t.currentAvailability}</p>
          <p
            className="text-4xl font-extrabold font-mono"
            style={{ color: isMeetingSla ? "#10b981" : "#ef4444" }}
          >
            {ov.current}%
          </p>
          <Badge variant={isMeetingSla ? "green" : "red"} className="mt-2">
            {isMeetingSla ? t.slaHealthy : t.slaAtRisk}
          </Badge>
        </Card>
        <Card className="text-center">
          <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider mb-2">{t.errorBudgetUsed}</p>
          <p
            className="text-4xl font-extrabold font-mono"
            style={{ color: budgetUsedPct > 80 ? "#ef4444" : budgetUsedPct > 50 ? "#f59e0b" : "#10b981" }}
          >
            {budgetUsedPct.toFixed(0)}%
          </p>
          <p className="text-xs text-[var(--text-muted)] mt-2">
            {ov.error_budget_used_minutes.toFixed(0)}m / {ov.error_budget_total_minutes.toFixed(0)}m
          </p>
        </Card>
        <Card className="text-center">
          <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider mb-2">{t.budgetRemaining}</p>
          <p className="text-4xl font-extrabold font-mono text-emerald-400">
            {ov.error_budget_remaining_pct.toFixed(0)}%
          </p>
          {ov.projected_breach_date
            ? <Badge variant="red" className="mt-2">{t.breachOn} {ov.projected_breach_date}</Badge>
            : <Badge variant="green" className="mt-2">{t.noBreachProjected}</Badge>}
        </Card>
      </div>

      {/* ── 2. SLO Breakdown ── */}
      <Card className="mb-8">
        <h3 className="text-lg font-bold mb-4 flex items-center gap-2">
          <Activity size={18} className="text-[var(--gold)]" />
          {t.sloBreakdown}
        </h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--border-color)]">
                <th scope="col" className="text-left py-3 px-2 text-[var(--text-muted)] font-medium">{t.metric}</th>
                <th scope="col" className="text-right py-3 px-2 text-[var(--text-muted)] font-medium">{t.target}</th>
                <th scope="col" className="text-right py-3 px-2 text-[var(--text-muted)] font-medium">{t.current}</th>
                <th scope="col" className="text-left py-3 px-2 text-[var(--text-muted)] font-medium">{t.compliance}</th>
                <th scope="col" className="text-left py-3 px-2 text-[var(--text-muted)] font-medium">{t.trend}</th>
              </tr>
            </thead>
            <tbody>
              {data.slo_breakdown.map((slo) => {
                const ok = sloCompliance(slo);
                const usePct = (slo.unit === "%" || slo.unit === "%") && !slo.name.includes("Error");
                const barValue = usePct
                  ? slo.current
                  : slo.unit === "req/s" || slo.name.includes("Hit")
                    ? (slo.current / (slo.target * 2)) * 100
                    : (slo.current / (slo.target * 1.2)) * 100;

                return (
                  <tr key={slo.name} className="border-b border-[var(--border-color)]/50 hover:bg-white/[0.02]">
                    <td className="py-3 px-2">
                      <div className="flex items-center gap-2">
                        <SloIcon name={slo.name} />
                        <span className="text-[#e2e8f0]">{slo.name}</span>
                      </div>
                    </td>
                    <td className="py-3 px-2 text-right font-mono text-[var(--text-muted)]">
                      {slo.target} {slo.unit}
                    </td>
                    <td
                      className="py-3 px-2 text-right font-mono font-bold"
                      style={{ color: ok ? "#10b981" : slo.status === "warning" ? "#f59e0b" : "#ef4444" }}
                    >
                      {slo.current} {slo.unit}
                    </td>
                    <td className="py-3 px-2">
                      <div className="flex items-center gap-2">
                        <div className="w-16 h-1.5 bg-white/5 rounded-full overflow-hidden">
                          <div
                            className="h-full rounded-full"
                            style={{
                              width: `${Math.min(100, barValue)}%`,
                              backgroundColor: ok ? "#10b981" : "#ef4444",
                            }}
                          />
                        </div>
                        <Badge variant={statusVariant(slo.status)}>
                          {ok ? t.pass : slo.status === "warning" ? t.warning : t.fail}
                        </Badge>
                      </div>
                    </td>
                    <td className="py-3 px-2">
                      {ok
                        ? <TrendingUp size={14} className="text-emerald-400" />
                        : <TrendingDown size={14} className="text-red-400" />}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>

      {/* ── 3. Error Budget Burn-Down ── */}
      <Card className="mb-8">
        <h3 className="text-lg font-bold mb-2 flex items-center gap-2">
          <TrendingDown size={18} className="text-[var(--gold)]" />
          {t.errorBudgetTitle}
        </h3>
        <p className="text-xs text-[var(--text-muted)] mb-4">
          {t.errorBudgetSubtitle.replace("{pct}", ov.error_budget_remaining_pct.toFixed(0))}
        </p>
        <ErrorBudgetChart history={data.error_budget_history} t={t} />
        <div className="flex items-center gap-6 mt-4 text-xs text-[var(--text-muted)]">
          <span className="flex items-center gap-1">
            <span className="w-3 h-1 rounded-full bg-[var(--gold)] inline-block" />
            {t.budgetConsumed}
          </span>
          <span className="flex items-center gap-1">
            <span className="w-3 h-1 rounded-full bg-yellow-500/50 inline-block" />
            {t.warningZone} (50%)
          </span>
          <span className="flex items-center gap-1">
            <span className="w-3 h-1 rounded-full bg-red-500/50 inline-block" />
            {t.dangerZone} (80%)
          </span>
        </div>
      </Card>

      {/* ── 4. SLA Validation ── */}
      <Card className="mb-8">
        <h3 className="text-lg font-bold mb-4 flex items-center gap-2">
          <Shield size={18} className="text-[var(--gold)]" />
          {t.validationTitle}
        </h3>
        <div className="flex items-center gap-3 mb-4 p-3 rounded-lg bg-emerald-500/5 border border-emerald-500/20">
          {data.validation.can_meet_sla
            ? <CheckCircle2 size={20} className="text-emerald-400 shrink-0" />
            : <AlertTriangle size={20} className="text-red-400 shrink-0" />}
          <p className="text-sm font-semibold">
            {data.validation.can_meet_sla ? t.canMeetSla : t.cannotMeetSla}
          </p>
          <Badge variant={data.validation.can_meet_sla ? "green" : "red"}>
            {data.validation.limiting_factor.toUpperCase()}
          </Badge>
        </div>

        {/* Layer availability breakdown */}
        <div className="grid md:grid-cols-3 gap-4 mb-4">
          {(Object.entries(data.validation.availability_by_layer) as [string, { nines: number; availability: number }][]).map(([layer, val]) => (
            <div key={layer} className="p-3 rounded-lg border border-[var(--border-color)] bg-white/[0.02] text-center">
              <p className="text-xs text-[var(--text-muted)] uppercase mb-1">{layer}</p>
              <p className="text-xl font-bold font-mono text-[#e2e8f0]">{val.nines.toFixed(2)}</p>
              <p className="text-xs text-[var(--text-muted)]">{t.nines}</p>
              <p className="text-xs font-mono text-emerald-400 mt-1">{val.availability.toFixed(4)}%</p>
            </div>
          ))}
        </div>

        <p className="text-xs text-[var(--text-secondary)] mb-4 p-3 bg-white/[0.02] rounded-lg border border-[var(--border-color)]">
          {data.validation.proof}
        </p>

        <div className="space-y-2">
          {data.validation.recommendations.map((rec, i) => (
            <div key={i} className="flex items-start gap-2 text-sm">
              <span className="text-[var(--gold)] font-bold shrink-0">{i + 1}.</span>
              <span className="text-[var(--text-secondary)]">{rec}</span>
            </div>
          ))}
        </div>
      </Card>

      {/* ── SLA-DESIGN-01: Incident Severity SLA Matrix ── */}
      <Card className="mb-6">
        <h3 className="text-lg font-bold mb-4 flex items-center gap-2">
          <Shield size={18} className="text-[var(--gold)]" />
          {locale === "ja" ? "障害レベル別SLA定義" : "Incident Severity SLA Matrix"}
        </h3>
        <p className="text-xs text-[var(--text-muted)] mb-4">
          {locale === "ja"
            ? "各障害レベルの定義・応答時間・復旧目標時間（RTO）・復旧目標時点（RPO）を定義します。"
            : "Response Time, RTO and RPO targets by incident severity level."}
        </p>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--border-color)]">
                {[
                  locale === "ja" ? "レベル" : "Level",
                  locale === "ja" ? "定義" : "Definition",
                  locale === "ja" ? "応答時間" : "Response Time",
                  "RTO",
                  "RPO",
                  locale === "ja" ? "例" : "Example",
                ].map((h) => (
                  <th key={h} scope="col" className="text-left py-3 px-3 text-[var(--text-muted)] font-medium whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {[
                {
                  level: "P1 — Critical",
                  color: "text-red-400",
                  def: locale === "ja" ? "全サービス停止・データ損失" : "Complete service outage or data loss",
                  response: "15 min",
                  rto: "1h",
                  rpo: "5 min",
                  example: locale === "ja" ? "本番DBダウン、全ユーザー影響" : "Production DB down, all users impacted",
                },
                {
                  level: "P2 — High",
                  color: "text-orange-400",
                  def: locale === "ja" ? "主要機能の重大な劣化" : "Major feature degraded, significant user impact",
                  response: "1h",
                  rto: "4h",
                  rpo: "1h",
                  example: locale === "ja" ? "決済不可、50%以上のユーザーに影響" : "Payments failing, >50% users affected",
                },
                {
                  level: "P3 — Medium",
                  color: "text-yellow-400",
                  def: locale === "ja" ? "一部機能の劣化・ワークアラウンドあり" : "Partial degradation with workaround available",
                  response: "4h",
                  rto: "24h",
                  rpo: "4h",
                  example: locale === "ja" ? "レポート生成が遅い、一部エラー" : "Reports slow, isolated errors",
                },
                {
                  level: "P4 — Low",
                  color: "text-blue-400",
                  def: locale === "ja" ? "軽微な問題・UI不具合" : "Minor issue, cosmetic bug, low impact",
                  response: "1 business day",
                  rto: "1 week",
                  rpo: "1 day",
                  example: locale === "ja" ? "UIの文字ずれ、ドキュメントの誤字" : "UI misalignment, docs typo",
                },
              ].map((row) => (
                <tr key={row.level} className="border-b border-[var(--border-color)]/50 hover:bg-white/[0.02]">
                  <td className={`py-3 px-3 font-semibold whitespace-nowrap text-xs ${row.color}`}>{row.level}</td>
                  <td className="py-3 px-3 text-xs text-[var(--text-secondary)] max-w-[180px]">{row.def}</td>
                  <td className="py-3 px-3 text-xs font-mono font-bold text-white whitespace-nowrap">{row.response}</td>
                  <td className="py-3 px-3 text-xs font-mono font-bold text-emerald-400 whitespace-nowrap">{row.rto}</td>
                  <td className="py-3 px-3 text-xs font-mono font-bold text-blue-400 whitespace-nowrap">{row.rpo}</td>
                  <td className="py-3 px-3 text-xs text-[var(--text-muted)] max-w-[180px]">{row.example}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {/* ── 5. Contract Summary ── */}
      <Card>
        <h3 className="text-lg font-bold mb-4 flex items-center gap-2">
          <FileCheck size={18} className="text-[var(--gold)]" />
          {t.contractSummary}
        </h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--border-color)]">
                <th scope="col" className="text-left py-3 px-2 text-[var(--text-muted)] font-medium">{t.provider}</th>
                <th scope="col" className="text-right py-3 px-2 text-[var(--text-muted)] font-medium">{t.slaTarget}</th>
                <th scope="col" className="text-left py-3 px-2 text-[var(--text-muted)] font-medium">{t.penaltyTerms}</th>
                <th scope="col" className="text-left py-3 px-2 text-[var(--text-muted)] font-medium">{t.expiry}</th>
                <th scope="col" className="text-left py-3 px-2 text-[var(--text-muted)] font-medium">{t.statusCol}</th>
              </tr>
            </thead>
            <tbody>
              {data.contracts.map((contract) => (
                <tr key={contract.id} className="border-b border-[var(--border-color)]/50 hover:bg-white/[0.02]">
                  <td className="py-3 px-2">
                    <div className="flex items-center gap-2">
                      <Shield size={12} className="text-[var(--text-muted)]" />
                      <span className="text-[#e2e8f0] font-medium">{contract.provider}</span>
                    </div>
                  </td>
                  <td className="py-3 px-2 text-right font-mono font-bold text-[var(--gold)]">
                    {contract.target}%
                  </td>
                  <td className="py-3 px-2 text-xs text-[var(--text-muted)] max-w-[200px]">
                    {contract.penalty_terms}
                  </td>
                  <td className="py-3 px-2 text-xs text-[var(--text-secondary)]">{contract.expiry}</td>
                  <td className="py-3 px-2">
                    <Badge variant={statusVariant(contract.status)}>
                      {contract.status.charAt(0).toUpperCase() + contract.status.slice(1)}
                    </Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
