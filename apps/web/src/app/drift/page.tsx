"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useState } from "react";
import { GitBranch, CheckCircle2, AlertTriangle, RefreshCw } from "lucide-react";
import { useLocale } from "@/lib/useLocale";
import { appDict } from "@/i18n/app-dict";

const DRIFT_EVENTS = [
  {
    id: "DRIFT-001",
    component: "k8s/api-deployment",
    changeType: "replica_count",
    before: "replicas: 3",
    after: "replicas: 5",
    detectedAt: "2026-04-01 07:42 UTC",
    status: "active",
    autoFix: "kubectl scale deployment api --replicas=3",
    description: "Replica count was manually scaled up and differs from desired state in Git.",
  },
  {
    id: "DRIFT-002",
    component: "k8s/redis-configmap",
    changeType: "config_modified",
    before: "maxmemory: 512mb",
    after: "maxmemory: 1gb",
    detectedAt: "2026-03-31 15:12 UTC",
    status: "active",
    autoFix: "kubectl apply -f config/redis-configmap.yaml",
    description: "Redis maxmemory was patched directly without going through GitOps pipeline.",
  },
  {
    id: "DRIFT-003",
    component: "k8s/monitoring",
    changeType: "new_service",
    before: "(not in desired state)",
    after: "svc/prometheus-debug: port 9090",
    detectedAt: "2026-03-30 11:05 UTC",
    status: "resolved",
    autoFix: "kubectl delete svc prometheus-debug",
    description: "Debug service was deployed manually and left running after troubleshooting session.",
  },
];

const DRIFT_HISTORY = [
  { date: "2026-04-01", count: 2, resolved: 0 },
  { date: "2026-03-31", count: 1, resolved: 1 },
  { date: "2026-03-30", count: 3, resolved: 3 },
  { date: "2026-03-29", count: 0, resolved: 0 },
  { date: "2026-03-28", count: 1, resolved: 1 },
  { date: "2026-03-27", count: 2, resolved: 2 },
  { date: "2026-03-26", count: 0, resolved: 0 },
];

export default function DriftPage() {
  const locale = useLocale();
  const t = appDict.drift[locale] ?? appDict.drift.en;
  const [remediating, setRemediating] = useState<string | null>(null);

  const activeDrifts = DRIFT_EVENTS.filter((d) => d.status === "active");
  const isDrifted = activeDrifts.length > 0;

  const handleRemediate = (id: string) => {
    setRemediating(id);
    setTimeout(() => setRemediating(null), 2000);
  };

  return (
    <div className="max-w-[1200px] mx-auto px-6 py-10">
      <div className="flex items-start justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold mb-1 flex items-center gap-3">
            <GitBranch size={24} className="text-[#FFD700]" />
            {t.title}
          </h1>
          <p className="text-[#94a3b8] text-sm">{t.subtitle}</p>
        </div>
        <Button size="sm" className="flex items-center gap-2 shrink-0">
          <RefreshCw size={14} />
          Scan Now
        </Button>
      </div>

      {/* Status banner */}
      <div className={`rounded-xl p-5 mb-8 flex items-center gap-4 border ${isDrifted ? "border-[#f59e0b]/30 bg-[#f59e0b]/5" : "border-[#10b981]/30 bg-[#10b981]/5"}`}>
        {isDrifted ? (
          <AlertTriangle size={28} className="text-[#f59e0b] shrink-0" />
        ) : (
          <CheckCircle2 size={28} className="text-[#10b981] shrink-0" />
        )}
        <div>
          <p className="font-bold text-lg">
            {t.scanStatus}: <span className={isDrifted ? "text-[#f59e0b]" : "text-[#10b981]"}>
              {isDrifted ? t.drifted : t.clean}
            </span>
          </p>
          <p className="text-sm text-[#94a3b8]">
            {isDrifted
              ? `${activeDrifts.length} active drift event(s) detected`
              : t.noActiveDrift}
            {" · "}{t.lastChecked}: 2026-04-01 08:00 UTC
          </p>
        </div>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        <Card className="text-center">
          <p className="text-3xl font-extrabold font-mono text-[#f59e0b]">{activeDrifts.length}</p>
          <p className="text-xs text-[#64748b] uppercase tracking-wider mt-1">{locale === "ja" ? "アクティブドリフト" : "Active Drift"}</p>
        </Card>
        <Card className="text-center">
          <p className="text-3xl font-extrabold font-mono text-[#10b981]">
            {DRIFT_EVENTS.filter((d) => d.status === "resolved").length}
          </p>
          <p className="text-xs text-[#64748b] uppercase tracking-wider mt-1">{locale === "ja" ? "解決済み" : "Resolved"}</p>
        </Card>
        <Card className="text-center">
          <p className="text-3xl font-extrabold font-mono">{DRIFT_EVENTS.length}</p>
          <p className="text-xs text-[#64748b] uppercase tracking-wider mt-1">{locale === "ja" ? "今週の合計" : "Total This Week"}</p>
        </Card>
        <Card className="text-center">
          <p className="text-3xl font-extrabold font-mono text-[#3b82f6]">
            {DRIFT_EVENTS.filter((d) => d.autoFix).length}
          </p>
          <p className="text-xs text-[#64748b] uppercase tracking-wider mt-1">{t.autoRemediation}</p>
        </Card>
      </div>

      {/* Active drift events */}
      <div className="mb-8">
        <p className="text-sm font-semibold text-[#FFD700] mb-4">{t.driftEvents}</p>
        <div className="space-y-4">
          {DRIFT_EVENTS.map((event) => (
            <Card key={event.id}>
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-2 flex-wrap">
                    <span className="font-mono text-xs text-[#64748b]">{event.id}</span>
                    <Badge variant={event.changeType === "new_service" ? "yellow" : "red"}>
                      {event.changeType.replace(/_/g, " ")}
                    </Badge>
                    <Badge variant={event.status === "active" ? "yellow" : "green"}>
                      {event.status}
                    </Badge>
                  </div>
                  <p className="font-mono text-sm font-semibold text-[#94a3b8] mb-2">{event.component}</p>
                  <p className="text-sm text-[#94a3b8] mb-3">{event.description}</p>

                  {/* Diff */}
                  <div className="grid md:grid-cols-2 gap-2 mb-3">
                    <div className="bg-[#0a0e1a] rounded-lg p-2">
                      <p className="text-xs text-[#64748b] uppercase mb-1">{t.before}</p>
                      <code className="text-xs text-[#94a3b8] font-mono">{event.before}</code>
                    </div>
                    <div className="bg-[#0a0e1a] rounded-lg p-2">
                      <p className="text-xs text-[#10b981] uppercase mb-1">{t.after}</p>
                      <code className="text-xs text-[#10b981] font-mono">{event.after}</code>
                    </div>
                  </div>

                  {/* Auto-remediation command */}
                  {event.autoFix && (
                    <div className="bg-[#0a0e1a] rounded-lg p-2">
                      <p className="text-xs text-[#64748b] uppercase mb-1">{t.autoRemediation}</p>
                      <code className="text-xs text-[#3b82f6] font-mono">{event.autoFix}</code>
                    </div>
                  )}

                  <p className="text-xs text-[#64748b] mt-2">{t.detectedAt}: {event.detectedAt}</p>
                </div>

                {event.status === "active" && (
                  <div className="flex flex-col gap-2 shrink-0">
                    <Button
                      size="sm"
                      onClick={() => handleRemediate(event.id)}
                      disabled={remediating === event.id}
                    >
                      {remediating === event.id ? "Applying..." : t.remediate}
                    </Button>
                    <button className="text-xs text-[#64748b] hover:text-white transition-colors px-3 py-1.5">
                      {t.ignore}
                    </button>
                  </div>
                )}
              </div>
            </Card>
          ))}
        </div>
      </div>

      {/* Drift history chart */}
      <Card>
        <p className="text-sm font-semibold text-[#FFD700] mb-4">{t.driftHistory}</p>
        <div className="flex items-end gap-3 h-24">
          {DRIFT_HISTORY.map((day) => (
            <div key={day.date} className="flex-1 flex flex-col items-center gap-1">
              <div className="w-full flex flex-col-reverse gap-0.5">
                {day.count > 0 && (
                  <div
                    className="w-full rounded-sm bg-[#f59e0b]/60"
                    style={{ height: `${day.count * 20}px` }}
                  />
                )}
                {day.resolved > 0 && (
                  <div
                    className="w-full rounded-sm bg-[#10b981]/60"
                    style={{ height: `${day.resolved * 20}px` }}
                  />
                )}
              </div>
              <p className="text-[10px] text-[#475569]">{day.date.slice(5)}</p>
            </div>
          ))}
        </div>
        <div className="flex gap-4 mt-2">
          <div className="flex items-center gap-1.5 text-xs text-[#64748b]">
            <div className="w-3 h-3 rounded-sm bg-[#f59e0b]/60" />Detected
          </div>
          <div className="flex items-center gap-1.5 text-xs text-[#64748b]">
            <div className="w-3 h-3 rounded-sm bg-[#10b981]/60" />Resolved
          </div>
        </div>
      </Card>
    </div>
  );
}
