"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useEffect, useState } from "react";
import { api, type FmeaData } from "@/lib/api";
import { AlertOctagon, Loader2, CheckCircle2, XCircle } from "lucide-react";
import { useLocale } from "@/lib/useLocale";
import type { Locale } from "@/i18n/config";
import { appDict } from "@/i18n/app-dict";

const DEMO_DATA: FmeaData = {
  analysis_date: "2026-03-30",
  total_failure_modes: 10,
  critical_rpn_threshold: 200,
  high_rpn_count: 4,
  failure_modes: [
    { id: "FM-001", component: "PostgreSQL Primary", failure_mode: "Complete database crash", effect: "All write operations fail, data loss risk", severity: 9, occurrence: 3, detection: 8, rpn: 216, recommended_action: "Implement automated failover with < 30s switchover", status: "open" },
    { id: "FM-002", component: "Redis Cache", failure_mode: "Memory exhaustion", effect: "Cache eviction storm, database overload", severity: 7, occurrence: 5, detection: 6, rpn: 210, recommended_action: "Set memory limits, implement eviction policies", status: "open" },
    { id: "FM-003", component: "API Gateway", failure_mode: "Certificate expiry", effect: "All HTTPS connections rejected", severity: 10, occurrence: 2, detection: 9, rpn: 180, recommended_action: "Automate cert renewal", status: "mitigated" },
    { id: "FM-004", component: "API Server", failure_mode: "Thread pool exhaustion", effect: "Requests queued, timeouts", severity: 6, occurrence: 6, detection: 4, rpn: 144, recommended_action: "Implement connection limits and auto-scaling", status: "open" },
    { id: "FM-005", component: "DNS", failure_mode: "DNS resolution failure", effect: "Service unreachable", severity: 10, occurrence: 1, detection: 7, rpn: 70, recommended_action: "Multi-provider DNS", status: "mitigated" },
    { id: "FM-006", component: "CDN / Edge", failure_mode: "Origin pull failure", effect: "Stale content served", severity: 5, occurrence: 3, detection: 3, rpn: 45, recommended_action: "Configure fallback origins", status: "mitigated" },
    { id: "FM-007", component: "Auth Service", failure_mode: "Token validation failure", effect: "Users unable to authenticate", severity: 8, occurrence: 2, detection: 5, rpn: 80, recommended_action: "Implement token caching", status: "open" },
    { id: "FM-008", component: "Background Worker", failure_mode: "Job queue backlog", effect: "Delayed processing", severity: 4, occurrence: 5, detection: 3, rpn: 60, recommended_action: "Dead letter queue + monitoring", status: "open" },
  ],
  rpn_distribution: { critical: 2, high: 2, medium: 4, low: 0 },
};

function rpnColor(rpn: number): string {
  if (rpn >= 200) return "#ef4444";
  if (rpn >= 120) return "#f59e0b";
  if (rpn >= 60) return "#eab308";
  return "#10b981";
}

function rpnLabel(rpn: number, locale: Locale): string {
  const t = appDict.fmea[locale] ?? appDict.fmea.en;
  if (rpn >= 200) return t.critical;
  if (rpn >= 120) return t.high;
  if (rpn >= 60) return t.medium;
  return t.low;
}

export default function FmeaPage() {
  const [data, setData] = useState<FmeaData>(DEMO_DATA);
  const [loading, setLoading] = useState(true);
  const [sortBy, setSortBy] = useState<"rpn" | "severity" | "occurrence">("rpn");
  const locale = useLocale();
  const t = appDict.fmea[locale] ?? appDict.fmea.en;

  useEffect(() => {
    api
      .getFmea()
      .then((result) => setData(result))
      .catch((err) => { console.error("[fmea] API error, using demo data:", err); setData(DEMO_DATA); })
      .finally(() => setLoading(false));
  }, []);

  const sorted = [...data.failure_modes].sort((a, b) => {
    if (sortBy === "rpn") return b.rpn - a.rpn;
    if (sortBy === "severity") return b.severity - a.severity;
    return b.occurrence - a.occurrence;
  });

  return (
    <div className="w-full px-6 py-10">
      <div className="mb-10">
        <h1 className="text-2xl font-bold mb-1 flex items-center gap-3">
          <AlertOctagon size={24} className="text-[var(--gold)]" />
          {t.title}
        </h1>
        <p className="text-[var(--text-secondary)] text-sm">
          {t.subtitle}
        </p>
      </div>

      {loading ? (
        <Card className="flex items-center justify-center py-20">
          <Loader2 size={24} className="animate-spin text-[var(--gold)]" />
        </Card>
      ) : (
        <>
          {/* Summary Stats */}
          <div className="grid md:grid-cols-4 gap-6 mb-8">
            <Card className="text-center">
              <p className="text-3xl font-extrabold font-mono">{data.total_failure_modes}</p>
              <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider mt-1">{t.failureModes}</p>
            </Card>
            <Card className="text-center">
              <p className="text-3xl font-extrabold font-mono text-red-400">{data.rpn_distribution.critical}</p>
              <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider mt-1">{t.criticalRpn}</p>
            </Card>
            <Card className="text-center">
              <p className="text-3xl font-extrabold font-mono text-[#f59e0b]">{data.rpn_distribution.high}</p>
              <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider mt-1">{t.highRpn}</p>
            </Card>
            <Card className="text-center">
              <p className="text-3xl font-extrabold font-mono text-emerald-400">
                {data.failure_modes.filter((f) => f.status === "mitigated").length}
              </p>
              <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider mt-1">{t.mitigated}</p>
            </Card>
          </div>

          {/* Sort Controls */}
          <div className="flex items-center gap-2 mb-4">
            <span className="text-xs text-[var(--text-muted)] uppercase tracking-wider">{t.sortBy}</span>
            {(["rpn", "severity", "occurrence"] as const).map((s) => (
              <button
                key={s}
                onClick={() => setSortBy(s)}
                className={`px-3 py-1 rounded-lg text-xs font-medium transition-all ${
                  sortBy === s
                    ? "bg-[var(--gold)]/10 text-[var(--gold)] border border-[var(--gold)]/30"
                    : "text-[var(--text-secondary)] border border-[var(--border-color)] hover:border-[#64748b]"
                }`}
              >
                {s.toUpperCase()}
              </button>
            ))}
          </div>

          {/* FMEA Table */}
          <Card>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[var(--border-color)]">
                    <th scope="col" className="text-left py-3 px-2 text-[var(--text-muted)] font-medium">{t.id}</th>
                    <th scope="col" className="text-left py-3 px-2 text-[var(--text-muted)] font-medium">{t.component}</th>
                    <th scope="col" className="text-left py-3 px-2 text-[var(--text-muted)] font-medium">{t.failureMode}</th>
                    <th scope="col" className="text-center py-3 px-2 text-[var(--text-muted)] font-medium">S</th>
                    <th scope="col" className="text-center py-3 px-2 text-[var(--text-muted)] font-medium">O</th>
                    <th scope="col" className="text-center py-3 px-2 text-[var(--text-muted)] font-medium">D</th>
                    <th scope="col" className="text-center py-3 px-2 text-[var(--text-muted)] font-medium">RPN</th>
                    <th scope="col" className="text-center py-3 px-2 text-[var(--text-muted)] font-medium">{t.status}</th>
                  </tr>
                </thead>
                <tbody>
                  {sorted.map((fm) => (
                    <tr key={fm.id} className="border-b border-[var(--border-color)]/50 hover:bg-white/[0.02]">
                      <td className="py-3 px-2 font-mono text-[var(--text-muted)]">{fm.id}</td>
                      <td className="py-3 px-2 font-medium">{fm.component}</td>
                      <td className="py-3 px-2">
                        <p>{fm.failure_mode}</p>
                        <p className="text-xs text-[var(--text-muted)] mt-0.5">{fm.effect}</p>
                      </td>
                      <td className="py-3 px-2 text-center font-mono font-bold" style={{ color: fm.severity >= 8 ? "#ef4444" : "#94a3b8" }}>
                        {fm.severity}
                      </td>
                      <td className="py-3 px-2 text-center font-mono font-bold" style={{ color: fm.occurrence >= 5 ? "#f59e0b" : "#94a3b8" }}>
                        {fm.occurrence}
                      </td>
                      <td className="py-3 px-2 text-center font-mono font-bold" style={{ color: fm.detection >= 7 ? "#ef4444" : "#94a3b8" }}>
                        {fm.detection}
                      </td>
                      <td className="py-3 px-2 text-center">
                        <span className="font-mono font-bold text-lg" style={{ color: rpnColor(fm.rpn) }}>
                          {fm.rpn}
                        </span>
                        <br />
                        <span className="text-xs" style={{ color: rpnColor(fm.rpn) }}>{rpnLabel(fm.rpn, locale)}</span>
                      </td>
                      <td className="py-3 px-2 text-center">
                        {fm.status === "mitigated" ? (
                          <Badge variant="green">
                            <CheckCircle2 size={10} className="mr-1" />
                            {t.mitigated}
                          </Badge>
                        ) : (
                          <Badge variant="red">
                            <XCircle size={10} className="mr-1" />
                            {t.open}
                          </Badge>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="mt-4 pt-4 border-t border-[var(--border-color)]">
              <p className="text-xs text-[var(--text-muted)]">
                {t.rpnExplain}
              </p>
            </div>
          </Card>
        </>
      )}
    </div>
  );
}
