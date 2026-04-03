"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useState } from "react";
import { FlaskRound, TrendingUp, TrendingDown, CheckCircle2, AlertTriangle } from "lucide-react";
import { useLocale } from "@/lib/useLocale";
import { appDict } from "@/i18n/app-dict";

const DEMO_CANARIES = [
  {
    id: "CANARY-001",
    service: "API Service",
    baselineVersion: "v3.1.2",
    canaryVersion: "v3.1.3-rc1",
    trafficSplit: 10,
    deployedAt: "2026-04-01 06:00 UTC",
    status: "healthy",
    autoRollback: true,
    rollbackThreshold: 5.0,
    baseline: {
      errorRate: 0.4,
      latencyP99: 185,
      requestsPerMin: 9000,
      successRate: 99.6,
    },
    canary: {
      errorRate: 0.6,
      latencyP99: 178,
      requestsPerMin: 1000,
      successRate: 99.4,
    },
  },
];

const CANARY_HISTORY = [
  { id: "CANARY-000", service: "Worker Service", version: "v2.8.0", decision: "promoted", date: "2026-03-31", trafficSplit: 20, finalErrorRate: 0.2 },
  { id: "CANARY-999", service: "Auth Service", version: "v1.4.0", decision: "promoted", date: "2026-03-28", trafficSplit: 10, finalErrorRate: 0.1 },
  { id: "CANARY-998", service: "API Service", version: "v3.1.1", decision: "rolled_back", date: "2026-03-24", trafficSplit: 5, finalErrorRate: 7.2 },
];

function MetricRow({ label, baseline, canary, unit = "", lowerIsBetter = false }: {
  label: string;
  baseline: number;
  canary: number;
  unit?: string;
  lowerIsBetter?: boolean;
}) {
  const diff = canary - baseline;
  const isBetter = lowerIsBetter ? diff < 0 : diff > 0;
  const isWorse = lowerIsBetter ? diff > 0 : diff < 0;
  const color = isBetter ? "#10b981" : isWorse ? "#ef4444" : "#94a3b8";
  const Icon = diff === 0 ? null : isBetter ? TrendingUp : TrendingDown;

  return (
    <div className="grid grid-cols-4 gap-2 bg-[#0a0e1a] rounded-lg px-3 py-2.5 items-center">
      <p className="text-xs text-[#64748b] col-span-1">{label}</p>
      <p className="text-sm font-mono font-bold text-center">{baseline}{unit}</p>
      <p className="text-sm font-mono font-bold text-center" style={{ color }}>{canary}{unit}</p>
      <div className="flex items-center justify-end gap-1" style={{ color }}>
        {Icon && <Icon size={12} />}
        <span className="text-xs font-mono">{diff > 0 ? "+" : ""}{diff.toFixed(1)}{unit}</span>
      </div>
    </div>
  );
}

export default function CanaryPage() {
  const locale = useLocale();
  const t = appDict.canary[locale] ?? appDict.canary.en;
  const [action, setAction] = useState<{ id: string; type: "promote" | "rollback" } | null>(null);

  const handleAction = (id: string, type: "promote" | "rollback") => {
    setAction({ id, type });
    setTimeout(() => setAction(null), 2000);
  };

  return (
    <div className="max-w-[1200px] mx-auto px-6 py-10">
      <div className="mb-8">
        <h1 className="text-2xl font-bold mb-1 flex items-center gap-3">
          <FlaskRound size={24} className="text-[#FFD700]" />
          {t.title}
        </h1>
        <p className="text-[#94a3b8] text-sm">{t.subtitle}</p>
      </div>

      {/* Active canaries */}
      <div className="mb-8">
        <p className="text-sm font-semibold text-[#FFD700] mb-4">{t.activeDeployments}</p>

        {DEMO_CANARIES.length === 0 ? (
          <Card className="text-center py-12">
            <p className="text-[#64748b]">{t.noActive}</p>
          </Card>
        ) : (
          <div className="space-y-6">
            {DEMO_CANARIES.map((canary) => (
              <Card key={canary.id}>
                {/* Header */}
                <div className="flex items-start justify-between gap-4 mb-6">
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <Badge variant={canary.status === "healthy" ? "green" : "yellow"}>
                        {canary.status === "healthy" ? t.healthy : t.warning}
                      </Badge>
                      <Badge variant="default">{canary.service}</Badge>
                    </div>
                    <p className="text-xs text-[#64748b] mt-1">
                      {t.deployedAt}: {canary.deployedAt}
                    </p>
                  </div>
                  <div className="flex gap-2 shrink-0">
                    <Button
                      size="sm"
                      onClick={() => handleAction(canary.id, "promote")}
                      disabled={action?.id === canary.id}
                      className="bg-[#10b981] text-black hover:bg-[#059669]"
                    >
                      {action?.id === canary.id && action.type === "promote" ? "Promoting..." : t.promote}
                    </Button>
                    <button
                      onClick={() => handleAction(canary.id, "rollback")}
                      disabled={action?.id === canary.id}
                      className="px-3 py-1.5 text-sm rounded-md border border-red-500/30 text-red-400 hover:bg-red-500/10 transition-colors"
                    >
                      {action?.id === canary.id && action.type === "rollback" ? "Rolling back..." : t.rollback}
                    </button>
                  </div>
                </div>

                {/* Version comparison */}
                <div className="grid md:grid-cols-2 gap-4 mb-6">
                  <div className="bg-[#0a0e1a] rounded-lg p-3">
                    <p className="text-xs text-[#64748b] mb-1">{t.baseline} {t.version}</p>
                    <p className="font-mono font-bold text-[#94a3b8]">{canary.baselineVersion}</p>
                  </div>
                  <div className="bg-[#FFD700]/5 border border-[#FFD700]/20 rounded-lg p-3">
                    <p className="text-xs text-[#64748b] mb-1">{t.canaryLabel} {t.version}</p>
                    <p className="font-mono font-bold text-[#FFD700]">{canary.canaryVersion}</p>
                  </div>
                </div>

                {/* Traffic split visualization */}
                <div className="mb-6">
                  <p className="text-xs text-[#64748b] uppercase tracking-wider mb-2">{t.trafficSplit}</p>
                  <div className="flex h-6 rounded-lg overflow-hidden">
                    <div
                      className="bg-[#1e293b] flex items-center justify-center text-xs text-[#94a3b8]"
                      style={{ width: `${100 - canary.trafficSplit}%` }}
                    >
                      {100 - canary.trafficSplit}% {t.baseline}
                    </div>
                    <div
                      className="bg-[#FFD700] flex items-center justify-center text-xs text-black font-bold"
                      style={{ width: `${canary.trafficSplit}%` }}
                    >
                      {canary.trafficSplit}%
                    </div>
                  </div>
                </div>

                {/* Metrics comparison */}
                <div className="mb-4">
                  <div className="grid grid-cols-4 gap-2 mb-2 px-3">
                    <p className="text-xs text-[#64748b]">{locale === "ja" ? "メトリクス" : "Metric"}</p>
                    <p className="text-xs text-[#64748b] text-center">{t.baseline}</p>
                    <p className="text-xs text-[#FFD700] text-center">{t.canaryLabel}</p>
                    <p className="text-xs text-[#64748b] text-right">{locale === "ja" ? "差分" : "Delta"}</p>
                  </div>
                  <div className="space-y-1.5">
                    <MetricRow label={t.errorRate} baseline={canary.baseline.errorRate} canary={canary.canary.errorRate} unit="%" lowerIsBetter />
                    <MetricRow label={t.latencyP99} baseline={canary.baseline.latencyP99} canary={canary.canary.latencyP99} unit="ms" lowerIsBetter />
                    <MetricRow label={locale === "ja" ? "成功率" : "Success Rate"} baseline={canary.baseline.successRate} canary={canary.canary.successRate} unit="%" />
                    <MetricRow label={locale === "ja" ? "リクエスト/分" : "Req/min"} baseline={canary.baseline.requestsPerMin} canary={canary.canary.requestsPerMin} />
                  </div>
                </div>

                {/* Auto-rollback config */}
                <div className="flex items-center justify-between bg-[#0a0e1a] rounded-lg px-3 py-2 mt-4">
                  <div className="flex items-center gap-2">
                    {canary.status === "healthy" ? (
                      <CheckCircle2 size={14} className="text-[#10b981]" />
                    ) : (
                      <AlertTriangle size={14} className="text-[#f59e0b]" />
                    )}
                    <p className="text-xs text-[#64748b]">{t.autoRollback}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant={canary.autoRollback ? "green" : "default"}>
                      {canary.autoRollback ? t.enabled : t.disabled}
                    </Badge>
                    <span className="text-xs text-[#64748b]">{t.rollbackThreshold}: <span className="text-white font-mono">{canary.rollbackThreshold}%</span></span>
                  </div>
                </div>
              </Card>
            ))}
          </div>
        )}
      </div>

      {/* History */}
      <Card>
        <p className="text-sm font-semibold text-[#FFD700] mb-4">{locale === "ja" ? "カナリア履歴" : "Canary History"}</p>
        <div className="space-y-2">
          {CANARY_HISTORY.map((h) => (
            <div key={h.id} className="flex items-center justify-between bg-[#0a0e1a] rounded-lg px-3 py-2.5">
              <div className="flex items-center gap-3">
                <Badge variant={h.decision === "promoted" ? "green" : "red"}>
                  {h.decision === "promoted" ? t.promote : t.rollback}
                </Badge>
                <div>
                  <p className="text-sm font-semibold">{h.service} {h.version}</p>
                  <p className="text-xs text-[#64748b]">{h.date} · {h.trafficSplit}% traffic · {h.finalErrorRate}% error rate</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
