"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useEffect, useState } from "react";
import { api, type FmeaData } from "@/lib/api";
import { AlertOctagon, Loader2, CheckCircle2, XCircle } from "lucide-react";

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

function rpnLabel(rpn: number): string {
  if (rpn >= 200) return "Critical";
  if (rpn >= 120) return "High";
  if (rpn >= 60) return "Medium";
  return "Low";
}

export default function FmeaPage() {
  const [data, setData] = useState<FmeaData>(DEMO_DATA);
  const [loading, setLoading] = useState(true);
  const [sortBy, setSortBy] = useState<"rpn" | "severity" | "occurrence">("rpn");

  useEffect(() => {
    api
      .getFmea()
      .then((result) => setData(result))
      .catch(() => setData(DEMO_DATA))
      .finally(() => setLoading(false));
  }, []);

  const sorted = [...data.failure_modes].sort((a, b) => {
    if (sortBy === "rpn") return b.rpn - a.rpn;
    if (sortBy === "severity") return b.severity - a.severity;
    return b.occurrence - a.occurrence;
  });

  return (
    <div className="max-w-[1200px] mx-auto px-6 py-10">
      <div className="mb-10">
        <h1 className="text-2xl font-bold mb-1 flex items-center gap-3">
          <AlertOctagon size={24} className="text-[#FFD700]" />
          FMEA Analysis
        </h1>
        <p className="text-[#94a3b8] text-sm">
          Failure Mode and Effects Analysis with RPN scoring
        </p>
      </div>

      {loading ? (
        <Card className="flex items-center justify-center py-20">
          <Loader2 size={24} className="animate-spin text-[#FFD700]" />
        </Card>
      ) : (
        <>
          {/* Summary Stats */}
          <div className="grid md:grid-cols-4 gap-6 mb-8">
            <Card className="text-center">
              <p className="text-3xl font-extrabold font-mono">{data.total_failure_modes}</p>
              <p className="text-xs text-[#64748b] uppercase tracking-wider mt-1">Failure Modes</p>
            </Card>
            <Card className="text-center">
              <p className="text-3xl font-extrabold font-mono text-red-400">{data.rpn_distribution.critical}</p>
              <p className="text-xs text-[#64748b] uppercase tracking-wider mt-1">Critical RPN</p>
            </Card>
            <Card className="text-center">
              <p className="text-3xl font-extrabold font-mono text-[#f59e0b]">{data.rpn_distribution.high}</p>
              <p className="text-xs text-[#64748b] uppercase tracking-wider mt-1">High RPN</p>
            </Card>
            <Card className="text-center">
              <p className="text-3xl font-extrabold font-mono text-emerald-400">
                {data.failure_modes.filter((f) => f.status === "mitigated").length}
              </p>
              <p className="text-xs text-[#64748b] uppercase tracking-wider mt-1">Mitigated</p>
            </Card>
          </div>

          {/* Sort Controls */}
          <div className="flex items-center gap-2 mb-4">
            <span className="text-xs text-[#64748b] uppercase tracking-wider">Sort by:</span>
            {(["rpn", "severity", "occurrence"] as const).map((s) => (
              <button
                key={s}
                onClick={() => setSortBy(s)}
                className={`px-3 py-1 rounded-lg text-xs font-medium transition-all ${
                  sortBy === s
                    ? "bg-[#FFD700]/10 text-[#FFD700] border border-[#FFD700]/30"
                    : "text-[#94a3b8] border border-[#1e293b] hover:border-[#64748b]"
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
                  <tr className="border-b border-[#1e293b]">
                    <th className="text-left py-3 px-2 text-[#64748b] font-medium">ID</th>
                    <th className="text-left py-3 px-2 text-[#64748b] font-medium">Component</th>
                    <th className="text-left py-3 px-2 text-[#64748b] font-medium">Failure Mode</th>
                    <th className="text-center py-3 px-2 text-[#64748b] font-medium">S</th>
                    <th className="text-center py-3 px-2 text-[#64748b] font-medium">O</th>
                    <th className="text-center py-3 px-2 text-[#64748b] font-medium">D</th>
                    <th className="text-center py-3 px-2 text-[#64748b] font-medium">RPN</th>
                    <th className="text-center py-3 px-2 text-[#64748b] font-medium">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {sorted.map((fm) => (
                    <tr key={fm.id} className="border-b border-[#1e293b]/50 hover:bg-white/[0.02]">
                      <td className="py-3 px-2 font-mono text-[#64748b]">{fm.id}</td>
                      <td className="py-3 px-2 font-medium">{fm.component}</td>
                      <td className="py-3 px-2">
                        <p>{fm.failure_mode}</p>
                        <p className="text-xs text-[#64748b] mt-0.5">{fm.effect}</p>
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
                        <span className="text-xs" style={{ color: rpnColor(fm.rpn) }}>{rpnLabel(fm.rpn)}</span>
                      </td>
                      <td className="py-3 px-2 text-center">
                        {fm.status === "mitigated" ? (
                          <Badge variant="green">
                            <CheckCircle2 size={10} className="mr-1" />
                            Mitigated
                          </Badge>
                        ) : (
                          <Badge variant="red">
                            <XCircle size={10} className="mr-1" />
                            Open
                          </Badge>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="mt-4 pt-4 border-t border-[#1e293b]">
              <p className="text-xs text-[#64748b]">
                <strong>S</strong> = Severity (1-10) | <strong>O</strong> = Occurrence (1-10) | <strong>D</strong> = Detection difficulty (1-10) | <strong>RPN</strong> = S x O x D (Risk Priority Number)
              </p>
            </div>
          </Card>
        </>
      )}
    </div>
  );
}
