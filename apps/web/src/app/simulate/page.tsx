"use client";

import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useState, useRef, useEffect } from "react";
import { api, type SimulationResult, type CloudSimulationResult, type Project, type CalculationEvidence, type CascadeSimulation, type SimulationLog } from "@/lib/api";
import { trackEvent } from "@/lib/analytics";
import {
  Zap,
  Server,
  Cloud,
  Database,
  Globe,
  Loader2,
  CheckCircle2,
  XCircle,
  ArrowRight,
  Upload,
  FileCode,
  ChevronDown,
  ChevronRight,
  Shield,
  Copy,
  Check,
  Terminal,
  Radio,
  RefreshCw,
  Download,
  AlertTriangle,
  Clock,
  Layers,
  Activity,
  ChevronUp,
  Mail,
  Star,
} from "lucide-react";
import Link from "next/link";
import { useLocale } from "@/lib/useLocale";
import { appDict } from "@/i18n/app-dict";
import { Info } from "lucide-react";
import { useSearchParams, useRouter } from "next/navigation";
import { Suspense } from "react";

const SAMPLES = [
  { id: "web-saas", name: "Web SaaS Platform", desc: "3-tier architecture with API gateway, auth, database, cache", icon: Globe, components: 8 },
  { id: "microservices", name: "Microservices", desc: "Event-driven microservices with message queues and service mesh", icon: Server, components: 12 },
  { id: "multi-region", name: "Multi-Region", desc: "Multi-region deployment with cross-region replication", icon: Cloud, components: 15 },
  { id: "data-pipeline", name: "Data Pipeline", desc: "ETL pipeline with streaming, batch processing, and data lake", icon: Database, components: 10 },
];

const YAML_PLACEHOLDER = `# Your infrastructure topology
components:
  - id: web-server
    name: "Web Server"
    type: app_server
    host: web01
    port: 443
    replicas: 3
    capacity:
      max_connections: 5000
    metrics:
      cpu_percent: 25
      memory_percent: 40

  - id: database
    name: "PostgreSQL"
    type: database
    host: db01
    port: 5432
    replicas: 2
    capacity:
      max_connections: 200
    metrics:
      cpu_percent: 35
      memory_percent: 55

  - id: cache
    name: "Redis Cache"
    type: cache
    host: cache01
    port: 6379
    replicas: 2
    capacity:
      max_connections: 10000
    metrics:
      memory_percent: 30

dependencies:
  - source: web-server
    target: database
    type: requires
    weight: 1.0
  - source: web-server
    target: cache
    type: optional
    weight: 0.7`;

function ScanPreview({ summary }: { summary: CloudSimulationResult["scan_summary"] }) {
  const locale = useLocale();
  return (
    <div className="p-4 rounded-xl bg-emerald-500/5 border border-emerald-500/20 mb-6">
      <div className="flex items-center gap-2 mb-3">
        <CheckCircle2 size={16} className="text-emerald-400" />
        <span className="text-sm font-semibold text-emerald-400">{locale === "ja" ? "インフラが検出されました" : "Infrastructure Discovered"}</span>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div>
          <p className="text-2xl font-bold font-mono text-white">{summary.components_found}</p>
          <p className="text-xs text-[#64748b]">{locale === "ja" ? "コンポーネント" : "Components"}</p>
        </div>
        <div>
          <p className="text-2xl font-bold font-mono text-white">{summary.dependencies_inferred}</p>
          <p className="text-xs text-[#64748b]">{locale === "ja" ? "依存関係" : "Dependencies"}</p>
        </div>
        {summary.region && (
          <div>
            <p className="text-sm font-mono text-white">{summary.region}</p>
            <p className="text-xs text-[#64748b]">{locale === "ja" ? "リージョン" : "Region"}</p>
          </div>
        )}
        {summary.scan_duration_seconds != null && (
          <div>
            <p className="text-sm font-mono text-white">{summary.scan_duration_seconds}s</p>
            <p className="text-xs text-[#64748b]">{locale === "ja" ? "スキャン時間" : "Scan Time"}</p>
          </div>
        )}
      </div>
      {summary.warnings && summary.warnings.length > 0 && (
        <div className="mt-3 pt-3 border-t border-emerald-500/10">
          <p className="text-xs text-[#94a3b8]">{locale === "ja" ? `スキャン中に${summary.warnings.length}件の警告が発生しました` : `${summary.warnings.length} warning(s) during scan`}</p>
        </div>
      )}
    </div>
  );
}

// ---- Calculation Evidence Section ----
function CalculationEvidencePanel({ evidence, t }: { evidence: CalculationEvidence; t: Record<string, string> }) {
  const [open, setOpen] = useState(true);
  const [expandedLayer, setExpandedLayer] = useState<string | null>(null);

  const layerColors: Record<string, { bar: string; text: string; border: string; bg: string }> = {
    Software: { bar: "bg-emerald-400", text: "text-emerald-400", border: "border-emerald-500/20", bg: "bg-emerald-500/5" },
    Hardware: { bar: "bg-[#FFD700]", text: "text-[#FFD700]", border: "border-[#FFD700]/20", bg: "bg-[#FFD700]/5" },
    Theoretical: { bar: "bg-blue-400", text: "text-blue-400", border: "border-blue-500/20", bg: "bg-blue-500/5" },
    Operational: { bar: "bg-purple-400", text: "text-purple-400", border: "border-purple-500/20", bg: "bg-purple-500/5" },
    "External SLA": { bar: "bg-orange-400", text: "text-orange-400", border: "border-orange-500/20", bg: "bg-orange-500/5" },
    External: { bar: "bg-orange-400", text: "text-orange-400", border: "border-orange-500/20", bg: "bg-orange-500/5" },
  };

  const bottleneckLayerName = evidence.bottleneck.split(" ")[0];

  // Find the actual bottleneck layer (lowest nines)
  const sortedLayers = [...evidence.layers].sort((a, b) => a.nines - b.nines);
  const lowestLayer = sortedLayers[0];

  return (
    <Card className="border-[#1e293b]">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center justify-between w-full"
      >
        <div className="flex items-center gap-3">
          <Layers size={18} className="text-[#FFD700]" />
          <h3 className="text-base font-bold">Calculation Evidence</h3>
        </div>
        {open ? <ChevronUp size={16} className="text-[#64748b]" /> : <ChevronDown size={16} className="text-[#64748b]" />}
      </button>

      {open && (
        <div className="mt-5 space-y-3">
          {/* Layer explanation banner */}
          <div className="flex items-start gap-3 p-3 rounded-xl bg-blue-500/[0.05] border border-blue-500/20">
            <Info size={15} className="text-blue-400 mt-0.5 shrink-0" />
            <div className="min-w-0">
              <p className="text-xs text-[#94a3b8] leading-relaxed">{t.layerExplanation ?? "Each layer represents an independent availability ceiling. Your actual availability = min(all layers) = weakest link."}</p>
              <p className="text-xs text-blue-400 mt-1">{t.focusOnLowest ?? "Focus on improving the lowest-scoring layer first."}</p>
            </div>
          </div>

          {evidence.layers.map((layer) => {
            const colors = layerColors[layer.name] ?? { bar: "bg-[#94a3b8]", text: "text-[#94a3b8]", border: "border-[#1e293b]", bg: "bg-white/[0.02]" };
            const isBottleneck = lowestLayer?.name === layer.name;
            const isExpanded = expandedLayer === layer.name;

            return (
              <div key={layer.name} className={`rounded-xl border ${isBottleneck ? "border-red-500/40 bg-red-500/[0.03]" : colors.border + " " + colors.bg} overflow-hidden`}>
                <button
                  onClick={() => setExpandedLayer(isExpanded ? null : layer.name)}
                  className="w-full p-4 text-left"
                >
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className={`text-sm font-semibold ${colors.text}`}>{layer.name}</span>
                      {isBottleneck && (
                        <>
                          <span className="px-2 py-0.5 text-[0.6875rem] font-bold rounded-full bg-red-500/10 text-red-400">{t.bottleneckLabel ?? "BOTTLENECK"}</span>
                          <span className="text-[0.6875rem] text-red-400/80 flex items-center gap-1">← {t.weakestLink ?? "This limits your availability"}</span>
                        </>
                      )}
                    </div>
                    <div className="flex items-center gap-3">
                      <span className={`text-sm font-mono font-bold ${colors.text}`}>{layer.nines.toFixed(2)} nines</span>
                      <span className="text-xs text-[#64748b]">max {layer.max_possible.toFixed(2)}</span>
                      {isExpanded ? <ChevronUp size={14} className="text-[#64748b]" /> : <ChevronDown size={14} className="text-[#64748b]" />}
                    </div>
                  </div>
                  <div className="h-1.5 bg-white/5 rounded-full overflow-hidden">
                    <div className={`h-full rounded-full ${colors.bar}`} style={{ width: `${(layer.nines / 7) * 100}%` }} />
                  </div>
                </button>

                {isExpanded && (
                  <div className="px-4 pb-4 space-y-2 border-t border-white/[0.05] pt-3">
                    {layer.factors.map((factor, fi) => {
                      const isPositive = factor.effect.startsWith("+");
                      const isNegative = factor.effect.startsWith("-");
                      return (
                        <div key={fi} className="flex items-start justify-between gap-3 text-sm">
                          <span className="text-[#94a3b8] flex-1">{factor.name}</span>
                          <span className={`font-mono text-xs shrink-0 ${isPositive ? "text-emerald-400" : isNegative ? "text-red-400" : "text-[#64748b]"}`}>
                            {factor.effect}
                          </span>
                          <span className="text-xs text-[#64748b] max-w-[180px] text-right">{factor.detail}</span>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}

          <div className="p-3 rounded-xl bg-white/[0.02] border border-[#1e293b]">
            <p className="text-xs text-red-400 mb-2 font-medium">{evidence.bottleneck}</p>
            <code className="text-xs font-mono text-emerald-400">{evidence.formula}</code>
          </div>
        </div>
      )}
    </Card>
  );
}

// ---- Cascade Simulation Section ----
function CascadeSimulationsPanel({ cascades }: { cascades: CascadeSimulation[] }) {
  const [expandedId, setExpandedId] = useState<string | null>(cascades[0]?.id ?? null);

  const eventTypeStyle: Record<string, { dot: string; label: string }> = {
    trigger: { dot: "bg-red-500", label: "text-red-400" },
    degradation: { dot: "bg-orange-400", label: "text-orange-400" },
    failure: { dot: "bg-red-500", label: "text-red-400" },
    cascade: { dot: "bg-orange-400", label: "text-orange-300" },
    outage: { dot: "bg-red-600", label: "text-red-400" },
    recovery: { dot: "bg-emerald-400", label: "text-emerald-400" },
  };

  const severityStyle = (s: string) =>
    s === "CRITICAL" ? "bg-red-500/10 text-red-400 border-red-500/20" : "bg-orange-500/10 text-orange-400 border-orange-500/20";

  return (
    <Card className="border-[#1e293b]">
      <div className="flex items-center gap-3 mb-5">
        <Activity size={18} className="text-orange-400" />
        <h3 className="text-base font-bold">Cascade Failure Simulation</h3>
        <span className="text-xs text-[#64748b]">Top {cascades.length} scenarios</span>
      </div>

      <div className="space-y-3">
        {cascades.map((cs) => (
          <div key={cs.id} className="rounded-xl border border-[#1e293b] bg-[#111827] overflow-hidden">
            <button
              onClick={() => setExpandedId(expandedId === cs.id ? null : cs.id)}
              className="w-full p-4 text-left"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-2 flex-wrap">
                    <span className="text-xs font-mono text-[#64748b]">{cs.id}</span>
                    <span className={`px-2 py-0.5 text-[0.6875rem] font-bold rounded-full border ${severityStyle(cs.severity)}`}>{cs.severity}</span>
                  </div>
                  <p className="text-sm font-medium text-white">{cs.trigger}</p>
                </div>
                <div className="flex flex-col items-end gap-1 shrink-0">
                  <div className="flex items-center gap-1.5 text-xs text-red-400">
                    <AlertTriangle size={12} />
                    <span className="font-bold">{cs.blast_radius_percent}%</span>
                    <span className="text-[#64748b]">blast radius</span>
                  </div>
                  <div className="flex items-center gap-1.5 text-xs text-[#64748b]">
                    <Clock size={12} />
                    <span>{cs.estimated_recovery_minutes}m recovery</span>
                  </div>
                  <div className="text-xs text-[#64748b]">{cs.affected_components}/{cs.total_components} components</div>
                </div>
              </div>
              <div className="flex items-center justify-end mt-2">
                {expandedId === cs.id ? <ChevronUp size={14} className="text-[#64748b]" /> : <ChevronDown size={14} className="text-[#64748b]" />}
              </div>
            </button>

            {expandedId === cs.id && (
              <div className="px-4 pb-4 border-t border-[#1e293b] pt-4">
                <div className="relative">
                  {cs.timeline.map((event, i) => {
                    const style = eventTypeStyle[event.type] ?? { dot: "bg-[#64748b]", label: "text-[#94a3b8]" };
                    const isLast = i === cs.timeline.length - 1;
                    return (
                      <div key={i} className="flex gap-3 mb-3 last:mb-0">
                        <div className="flex flex-col items-center">
                          <div className={`w-2.5 h-2.5 rounded-full mt-1 shrink-0 ${style.dot}`} />
                          {!isLast && <div className="w-px flex-1 bg-[#1e293b] mt-1" />}
                        </div>
                        <div className="pb-1 min-w-0">
                          <div className="flex items-baseline gap-2 flex-wrap">
                            <span className="text-xs font-mono text-[#64748b] shrink-0">{event.time}</span>
                            <span className="text-sm text-white">{event.event}</span>
                          </div>
                          <div className="flex items-center gap-2 mt-0.5">
                            <span className={`text-xs font-mono ${style.label}`}>[{event.component}]</span>
                            <span className="text-[0.6875rem] text-[#64748b] capitalize">{event.type}</span>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </Card>
  );
}

// ---- Simulation Log Section ----
function SimulationLogPanel({ log }: { log: SimulationLog }) {
  const [open, setOpen] = useState(false);
  const [sortBy, setSortBy] = useState<"id" | "risk_score" | "result">("id");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");

  const toggleSort = (col: "id" | "risk_score" | "result") => {
    if (sortBy === col) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortBy(col);
      setSortDir(col === "risk_score" ? "desc" : "asc");
    }
  };

  const sorted = [...log.scenarios].sort((a, b) => {
    let diff = 0;
    if (sortBy === "id") diff = a.id - b.id;
    else if (sortBy === "risk_score") diff = a.risk_score - b.risk_score;
    else if (sortBy === "result") {
      const order = { CRITICAL: 0, WARNING: 1, PASSED: 2 };
      diff = (order[a.result] ?? 3) - (order[b.result] ?? 3);
    }
    return sortDir === "asc" ? diff : -diff;
  });

  const resultBadge = (r: "PASSED" | "WARNING" | "CRITICAL") => {
    if (r === "CRITICAL") return <span className="px-2 py-0.5 text-[0.6875rem] font-bold rounded-full bg-red-500/10 text-red-400">CRITICAL</span>;
    if (r === "WARNING") return <span className="px-2 py-0.5 text-[0.6875rem] font-bold rounded-full bg-orange-500/10 text-orange-400">WARNING</span>;
    return <span className="px-2 py-0.5 text-[0.6875rem] font-bold rounded-full bg-emerald-500/10 text-emerald-400">PASSED</span>;
  };

  const handleDownload = () => {
    const blob = new Blob([JSON.stringify(log, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "faultray-simulation-log.json";
    a.click();
    URL.revokeObjectURL(url);
  };

  const SortIcon = ({ col }: { col: string }) => {
    if (sortBy !== col) return <ChevronDown size={12} className="text-[#64748b] opacity-40" />;
    return sortDir === "asc"
      ? <ChevronUp size={12} className="text-[#FFD700]" />
      : <ChevronDown size={12} className="text-[#FFD700]" />;
  };

  return (
    <Card className="border-[#1e293b]">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center justify-between w-full"
      >
        <div className="flex items-center gap-3">
          <Activity size={18} className="text-blue-400" />
          <h3 className="text-base font-bold">Simulation Log</h3>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-[#64748b]">
            {log.total_scenarios} scenarios · {log.duration_ms}ms
          </span>
          {open ? <ChevronUp size={16} className="text-[#64748b]" /> : <ChevronDown size={16} className="text-[#64748b]" />}
        </div>
      </button>

      {/* Summary bar always visible */}
      <div className="mt-3 flex items-center gap-4 text-xs">
        <span className="text-emerald-400 font-semibold">{log.passed} passed</span>
        <span className="text-[#1e293b]">|</span>
        <span className="text-red-400 font-semibold">{log.critical} critical</span>
        <span className="text-[#1e293b]">|</span>
        <span className="text-orange-400 font-semibold">{log.warning} warning</span>
        <button
          onClick={handleDownload}
          className="ml-auto flex items-center gap-1.5 text-xs text-[#94a3b8] hover:text-white transition-colors"
        >
          <Download size={12} />
          Download Full Log (JSON)
        </button>
      </div>

      {open && (
        <div className="mt-4 overflow-x-auto rounded-xl border border-[#1e293b]">
          <table className="w-full min-w-[600px] border-collapse text-sm">
            <thead>
              <tr className="bg-[#0d1117]">
                <th scope="col" className="px-4 py-2.5 text-left text-xs font-semibold text-[#64748b]">
                  <button onClick={() => toggleSort("id")} className="flex items-center gap-1 hover:text-white transition-colors">
                    # <SortIcon col="id" />
                  </button>
                </th>
                <th scope="col" className="px-4 py-2.5 text-left text-xs font-semibold text-[#64748b]">Scenario Name</th>
                <th scope="col" className="px-4 py-2.5 text-left text-xs font-semibold text-[#64748b]">
                  <button onClick={() => toggleSort("result")} className="flex items-center gap-1 hover:text-white transition-colors">
                    Result <SortIcon col="result" />
                  </button>
                </th>
                <th scope="col" className="px-4 py-2.5 text-left text-xs font-semibold text-[#64748b]">
                  <button onClick={() => toggleSort("risk_score")} className="flex items-center gap-1 hover:text-white transition-colors">
                    Risk Score <SortIcon col="risk_score" />
                  </button>
                </th>
                <th scope="col" className="px-4 py-2.5 text-left text-xs font-semibold text-[#64748b]">Affected</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((s, i) => (
                <tr key={s.id} className={i < sorted.length - 1 ? "border-b border-[#1e293b]" : ""}>
                  <td className="px-4 py-2.5 font-mono text-xs text-[#64748b]">{s.id}</td>
                  <td className="px-4 py-2.5 text-[#94a3b8] max-w-[280px]">{s.name}</td>
                  <td className="px-4 py-2.5">{resultBadge(s.result)}</td>
                  <td className="px-4 py-2.5 font-mono text-sm">
                    <span className={s.risk_score >= 8 ? "text-red-400" : s.risk_score >= 5 ? "text-orange-400" : "text-emerald-400"}>
                      {s.risk_score.toFixed(1)}
                    </span>
                    <span className="text-[#64748b] text-xs">/10</span>
                  </td>
                  <td className="px-4 py-2.5">
                    {s.affected.length === 0 ? (
                      <span className="text-xs text-[#64748b]">none</span>
                    ) : (
                      <span className="text-xs text-[#94a3b8]">{s.affected.join(", ")}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {log.total_scenarios > log.scenarios.length && (
            <div className="px-4 py-2.5 bg-[#0d1117] border-t border-[#1e293b] text-xs text-[#64748b] text-center">
              Showing first {log.scenarios.length} of {log.total_scenarios} scenarios. Download full log for all results.
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

// DEMO-04: ビジネス言語でのサマリー生成
function businessSummary(score: number, availability: string, criticalCount: number): { headline: string; detail: string; action: string } {
  if (score >= 90) {
    return {
      headline: `Your infrastructure can achieve ${availability} availability`,
      detail: `${criticalCount === 0 ? "No critical vulnerabilities detected." : `${criticalCount} critical issue${criticalCount > 1 ? "s" : ""} found.`} Your system demonstrates excellent resilience across all failure scenarios.`,
      action: "Export this as a PDF report to share with stakeholders →",
    };
  }
  if (score >= 70) {
    return {
      headline: `Your infrastructure availability ceiling is ${availability}`,
      detail: `${criticalCount} critical vulnerabilit${criticalCount !== 1 ? "ies" : "y"} detected. Addressing these would move you from ${score.toFixed(0)}/100 to 90+ score.`,
      action: "Review the recommendations below to improve your SLA →",
    };
  }
  return {
    headline: `Resilience improvement needed — availability ceiling is ${availability}`,
    detail: `${criticalCount} critical issues are limiting your availability. Without fixes, your system risks extended outages that could cost thousands of dollars per hour.`,
    action: "Prioritize the CRITICAL findings below for immediate action →",
  };
}

/**
 * SALES-04: リードナーチャリング
 * After running a simulation, capture email for weekly reliability tips.
 * Stores opted-in state to localStorage to avoid repeated prompts.
 */
function NurtureEmailCapture() {
  const [email, setEmail] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [dismissed, setDismissed] = useState(false);

  // Check if user already opted in or dismissed
  useEffect(() => {
    try {
      const prefs = JSON.parse(localStorage.getItem("faultray_notifications") ?? "{}") as Record<string, unknown>;
      if (prefs.nurtureOptedIn === true || prefs.nurtureDismissed === true) {
        setDismissed(true);
      }
    } catch {
      // localStorage unavailable — skip
    }
  }, []);

  if (dismissed) return null;

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!email) return;
    // Store opt-in in localStorage (backend integration point for drip sequence)
    try {
      const raw = localStorage.getItem("faultray_notifications");
      const prefs = raw ? (JSON.parse(raw) as Record<string, unknown>) : {};
      prefs.nurtureOptedIn = true;
      prefs.nurtureEmail = email;
      prefs.nurtureTimestamp = new Date().toISOString();
      localStorage.setItem("faultray_notifications", JSON.stringify(prefs));
    } catch {
      // localStorage unavailable
    }
    setSubmitted(true);
  }

  function handleDismiss() {
    try {
      const raw = localStorage.getItem("faultray_notifications");
      const prefs = raw ? (JSON.parse(raw) as Record<string, unknown>) : {};
      prefs.nurtureDismissed = true;
      localStorage.setItem("faultray_notifications", JSON.stringify(prefs));
    } catch {
      // localStorage unavailable
    }
    setDismissed(true);
  }

  return (
    <div className="p-5 rounded-2xl border border-[#FFD700]/20 bg-gradient-to-br from-[#FFD700]/[0.04] to-transparent">
      {submitted ? (
        <div className="flex items-center gap-3">
          <Star size={20} className="text-[#FFD700] shrink-0" />
          <div>
            <p className="text-sm font-semibold text-[#e2e8f0]">You&apos;re in! Weekly reliability tips coming your way.</p>
            <p className="text-xs text-[#64748b] mt-0.5">Check your inbox — unsubscribe anytime.</p>
          </div>
        </div>
      ) : (
        <div>
          <div className="flex items-start justify-between mb-3">
            <div className="flex items-center gap-2">
              <Mail size={18} className="text-[#FFD700]" />
              <p className="text-sm font-semibold">Get Weekly Reliability Insights</p>
            </div>
            <button
              onClick={handleDismiss}
              className="text-[#475569] hover:text-white text-xs transition-colors"
              aria-label="Dismiss"
            >
              ✕
            </button>
          </div>
          <p className="text-xs text-[#94a3b8] mb-4">
            One email/week: reliability benchmarks, failure case studies, and new FaultRay features. No spam.
          </p>
          <form onSubmit={handleSubmit} className="flex gap-2">
            <input
              type="email"
              required
              value={email}
              onChange={(e) => { setEmail(e.target.value); }}
              placeholder="your@company.com"
              aria-label="Email address"
              className="flex-1 min-w-0 px-3 py-2 rounded-lg bg-[#0d1117] border border-[#1e293b] text-sm text-white placeholder-[#475569] focus:outline-none focus:border-[#FFD700]/50 transition-colors"
            />
            <button
              type="submit"
              className="px-4 py-2 rounded-lg bg-[#FFD700] text-[#0a0e1a] text-sm font-semibold hover:bg-[#ffe44d] transition-colors shrink-0"
            >
              Subscribe
            </button>
          </form>
        </div>
      )}
    </div>
  );
}

function ResultsPanel({ result, scanSummary, simulateT }: { result: SimulationResult; scanSummary?: CloudSimulationResult["scan_summary"]; simulateT: Record<string, string> }) {
  const scoreColor = result.overall_score >= 90 ? "text-emerald-400" : result.overall_score >= 70 ? "text-[#FFD700]" : "text-red-400";
  const summary = businessSummary(result.overall_score, result.availability_estimate, result.critical_failures.length);

  return (
    <div className="space-y-6">
      {scanSummary && <ScanPreview summary={scanSummary} />}

      {/* DEMO-04: ビジネス言語サマリーバナー */}
      <div className={`p-5 rounded-2xl border ${
        result.overall_score >= 90
          ? "border-emerald-500/20 bg-emerald-500/[0.05]"
          : result.overall_score >= 70
          ? "border-amber-500/20 bg-amber-500/[0.05]"
          : "border-red-500/20 bg-red-500/[0.05]"
      }`}>
        <p className={`text-lg font-bold mb-1 ${scoreColor}`}>{summary.headline}</p>
        <p className="text-sm text-[#94a3b8] mb-2">{summary.detail}</p>
        <p className="text-xs text-[#64748b]">{summary.action}</p>
      </div>

      {/* Core score card */}
      <Card className="border-emerald-500/20">
        <div className="flex items-center gap-4 mb-6">
          <CheckCircle2 size={24} className="text-emerald-400" />
          <h3 className="text-lg font-bold">Simulation Complete</h3>
        </div>

        <div className="grid md:grid-cols-4 gap-6 mb-6">
          <div className="text-center p-4 rounded-xl bg-white/[0.02] border border-[#1e293b]">
            <p className={`text-3xl font-extrabold font-mono ${scoreColor}`}>{result.overall_score.toFixed(1)}</p>
            <p className="text-xs text-[#64748b] uppercase tracking-wider mt-1">Score</p>
          </div>
          <div className="text-center p-4 rounded-xl bg-white/[0.02] border border-[#1e293b]">
            <p className="text-3xl font-extrabold font-mono text-emerald-400">{result.availability_estimate}</p>
            <p className="text-xs text-[#64748b] uppercase tracking-wider mt-1">Availability</p>
          </div>
          <div className="text-center p-4 rounded-xl bg-white/[0.02] border border-[#1e293b]">
            <p className="text-3xl font-extrabold font-mono text-emerald-400">{result.scenarios_passed}</p>
            <p className="text-xs text-[#64748b] uppercase tracking-wider mt-1">Passed</p>
          </div>
          <div className="text-center p-4 rounded-xl bg-white/[0.02] border border-[#1e293b]">
            <p className="text-3xl font-extrabold font-mono text-red-400">{result.scenarios_failed}</p>
            <p className="text-xs text-[#64748b] uppercase tracking-wider mt-1">Failed</p>
          </div>
        </div>

        {result.layers && (
          <div className="space-y-3 mb-6">
            <h4 className="text-sm font-semibold text-[#94a3b8]">N-Layer Availability</h4>
            {[
              { label: "Software", value: result.layers.software, color: "bg-emerald-400" },
              { label: "Hardware", value: result.layers.hardware, color: "bg-[#FFD700]" },
              { label: "Theoretical", value: result.layers.theoretical, color: "bg-blue-400" },
            ].map((l) => (
              <div key={l.label} className="grid grid-cols-[80px_1fr_60px] items-center gap-3">
                <span className="text-xs text-[#64748b]">{l.label}</span>
                <div className="h-2 bg-white/5 rounded-full overflow-hidden">
                  <div className={`h-full rounded-full ${l.color}`} style={{ width: `${(l.value / 7) * 100}%` }} />
                </div>
                <span className="text-xs font-mono text-right">{l.value.toFixed(2)}</span>
              </div>
            ))}
          </div>
        )}

        {result.critical_failures.length > 0 && (
          <div className="mb-6">
            <h4 className="text-sm font-semibold text-red-400 mb-3">Critical Failures</h4>
            <div className="space-y-2">
              {result.critical_failures.map((f, i) => (
                <div key={i} className="flex items-start gap-3 p-3 rounded-lg bg-red-500/5 border border-red-500/10">
                  <XCircle size={16} className="text-red-400 mt-0.5 shrink-0" />
                  <div>
                    <p className="text-sm font-medium">{f.scenario}</p>
                    <p className="text-xs text-[#94a3b8] mt-0.5">{f.impact}</p>
                  </div>
                  <Badge variant="red" className="ml-auto shrink-0">{f.severity}</Badge>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="flex gap-3">
          <Link href="/results"><Button variant="secondary" size="sm">View Full Results <ArrowRight size={14} /></Button></Link>
          <Link href="/suggestions"><Button variant="secondary" size="sm">View Suggestions <ArrowRight size={14} /></Button></Link>
        </div>
      </Card>

      {/* Calculation Evidence */}
      {result.calculation_evidence && (
        <CalculationEvidencePanel evidence={result.calculation_evidence} t={simulateT} />
      )}

      {/* Cascade Simulations */}
      {result.cascade_simulations && result.cascade_simulations.length > 0 && (
        <CascadeSimulationsPanel cascades={result.cascade_simulations} />
      )}

      {/* Simulation Log */}
      {result.simulation_log && (
        <SimulationLogPanel log={result.simulation_log} />
      )}

      {/* SALES-04: リードナーチャリング — Weekly Insights capture */}
      <NurtureEmailCapture />
    </div>
  );
}

type TopTab = "quickstart" | "cloud" | "agent";

// Mock connected agents data (would come from API in production)
interface ConnectedAgent {
  id: string;
  name: string;
  provider: string;
  region: string;
  lastScan: string;
  components: number;
  status: "connected" | "scanning" | "error";
}

const MOCK_AGENTS: ConnectedAgent[] = [];

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const locale = useLocale();

  const handleCopy = () => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <button
      onClick={handleCopy}
      className="p-1.5 rounded-md hover:bg-white/10 transition-colors text-[#64748b] hover:text-white"
      title={locale === "ja" ? "クリップボードにコピー" : "Copy to clipboard"}
      aria-label={locale === "ja" ? "クリップボードにコピー" : "Copy to clipboard"}
    >
      {copied ? <Check size={14} className="text-emerald-400" /> : <Copy size={14} />}
    </button>
  );
}

function CodeBlock({ code, language = "bash" }: { code: string; language?: string }) {
  return (
    <div className="relative group rounded-lg bg-[#0d1117] border border-[#1e293b] overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2 border-b border-[#1e293b]">
        <span className="text-xs text-[#64748b] font-mono">{language}</span>
        <CopyButton text={code} />
      </div>
      <pre className="px-4 py-3 text-sm font-mono text-[#e2e8f0] overflow-x-auto">
        <code>{code}</code>
      </pre>
    </div>
  );
}

const DEMO_RESULT: SimulationResult = {
  overall_score: 85.2,
  availability_estimate: "99.99%",
  nines: 4.0,
  scenarios_passed: 147,
  scenarios_failed: 5,
  total_scenarios: 152,
  layers: { software: 4.0, hardware: 5.91, theoretical: 6.65, operational: 5.20, external: 4.85 },
  critical_failures: [
    { scenario: "Cascading database failure", impact: "Full service outage for 12 minutes", severity: "CRITICAL" },
    { scenario: "Cache cluster partition", impact: "Degraded performance, 30% latency increase", severity: "HIGH" },
    { scenario: "DNS resolution failure", impact: "Intermittent connectivity loss", severity: "HIGH" },
  ],
  suggestions: [
    { title: "Add database read replica", description: "Implement a read replica to handle failover scenarios", impact: "+0.5 nines", effort: "Medium" },
    { title: "Implement circuit breaker", description: "Add circuit breaker pattern for cascading failure protection", impact: "+0.3 nines", effort: "Low" },
  ],
  calculation_evidence: {
    layers: [
      {
        name: "Software",
        nines: 4.0,
        max_possible: 4.21,
        factors: [
          { name: "Replica redundancy", effect: "+0.30 nines", detail: "2x replicas on app_server" },
          { name: "No automatic failover", effect: "-0.21 nines", detail: "database has no automatic failover" },
          { name: "Health check interval", effect: "-0.10 nines", detail: "60s interval is too slow" },
        ],
      },
      {
        name: "Hardware",
        nines: 5.91,
        max_possible: 6.06,
        factors: [
          { name: "Multi-zone deployment", effect: "+0.50 nines", detail: "Components spread across AZs" },
          { name: "Storage redundancy", effect: "+0.20 nines", detail: "Replicated storage detected" },
          { name: "Single region", effect: "-0.15 nines", detail: "No cross-region failover configured" },
        ],
      },
      {
        name: "Theoretical",
        nines: 6.65,
        max_possible: 6.70,
        factors: [
          { name: "Markov chain steady-state", effect: "+0.80 nines", detail: "MTBF/MTTR ratio is favorable" },
          { name: "Reliability block diagram", effect: "+0.30 nines", detail: "Parallel paths increase ceiling" },
          { name: "Correlated failure risk", effect: "-0.05 nines", detail: "Shared dependencies reduce independence" },
        ],
      },
      {
        name: "Operational",
        nines: 5.20,
        max_possible: 5.45,
        factors: [
          { name: "Change management process", effect: "+0.40 nines", detail: "Formal change windows enforced" },
          { name: "On-call coverage", effect: "+0.20 nines", detail: "24/7 on-call rotation active" },
          { name: "Manual deployment steps", effect: "-0.25 nines", detail: "Human error risk in deployment process" },
        ],
      },
      {
        name: "External SLA",
        nines: 4.85,
        max_possible: 5.00,
        factors: [
          { name: "Cloud provider SLA", effect: "+0.50 nines", detail: "AWS 99.99% SLA for managed services" },
          { name: "DNS provider SLA", effect: "+0.20 nines", detail: "Route53 99.99% SLA" },
          { name: "Third-party API dependency", effect: "-0.15 nines", detail: "Payment gateway SLA capped at 99.95%" },
        ],
      },
    ],
    bottleneck: "Software layer limits overall availability",
    formula: "Availability = min(SW, HW, TH, OPS, EXT) = min(4.0, 5.91, 6.65, 5.20, 4.85) = 4.0 nines",
  },
  cascade_simulations: [
    {
      id: "CS-001",
      trigger: "Primary database disk I/O saturation",
      severity: "CRITICAL",
      affected_components: 5,
      total_components: 9,
      blast_radius_percent: 56,
      estimated_recovery_minutes: 12,
      timeline: [
        { time: "T+0:00", event: "DB disk I/O reaches 100%", component: "db_primary", type: "trigger" },
        { time: "T+0:30", event: "Query latency exceeds 5s", component: "db_primary", type: "degradation" },
        { time: "T+1:00", event: "Connection pool exhausted (200/200)", component: "db_primary", type: "failure" },
        { time: "T+1:15", event: "API server health check fails", component: "api", type: "cascade" },
        { time: "T+1:30", event: "Background workers queue backlog", component: "worker", type: "cascade" },
        { time: "T+2:00", event: "Load balancer marks API unhealthy", component: "gateway", type: "cascade" },
        { time: "T+5:00", event: "Full service outage", component: "all", type: "outage" },
        { time: "T+12:00", event: "DB disk cleared, service restored", component: "all", type: "recovery" },
      ],
    },
    {
      id: "CS-002",
      trigger: "Cache cluster memory saturation",
      severity: "HIGH",
      affected_components: 3,
      total_components: 9,
      blast_radius_percent: 33,
      estimated_recovery_minutes: 8,
      timeline: [
        { time: "T+0:00", event: "Cache memory reaches 95%", component: "cache", type: "trigger" },
        { time: "T+0:20", event: "Cache eviction rate spikes", component: "cache", type: "degradation" },
        { time: "T+1:00", event: "API response times increase 3x", component: "api", type: "cascade" },
        { time: "T+2:30", event: "Increased DB load from cache misses", component: "db_primary", type: "cascade" },
        { time: "T+8:00", event: "Cache scaled and warmed up", component: "cache", type: "recovery" },
      ],
    },
    {
      id: "CS-003",
      trigger: "Network partition between availability zones",
      severity: "HIGH",
      affected_components: 4,
      total_components: 9,
      blast_radius_percent: 44,
      estimated_recovery_minutes: 5,
      timeline: [
        { time: "T+0:00", event: "AZ-B network unreachable", component: "gateway", type: "trigger" },
        { time: "T+0:15", event: "Replica nodes lose quorum", component: "db_replica", type: "degradation" },
        { time: "T+0:45", event: "Read traffic fails for 50% of requests", component: "api", type: "cascade" },
        { time: "T+1:00", event: "Auth service in AZ-B down", component: "auth", type: "cascade" },
        { time: "T+5:00", event: "Network restored, replicas re-sync", component: "all", type: "recovery" },
      ],
    },
  ],
  simulation_log: {
    total_scenarios: 152,
    passed: 147,
    critical: 3,
    warning: 7,
    duration_ms: 1230,
    scenarios: [
      { id: 1, name: "Single node: db_primary failure", result: "CRITICAL", risk_score: 8.5, affected: ["api", "worker", "gateway"] },
      { id: 2, name: "Single node: cache failure", result: "WARNING", risk_score: 5.2, affected: ["api"] },
      { id: 3, name: "Single node: gateway failure", result: "PASSED", risk_score: 1.0, affected: [] },
      { id: 4, name: "Cascading: db_primary → api → worker", result: "CRITICAL", risk_score: 9.1, affected: ["api", "worker", "gateway", "cdn"] },
      { id: 5, name: "Partition: AZ-B network loss", result: "WARNING", risk_score: 6.3, affected: ["db_replica", "auth"] },
      { id: 6, name: "Resource: cache memory exhaustion", result: "WARNING", risk_score: 5.8, affected: ["api", "db_primary"] },
      { id: 7, name: "Single node: cdn failure", result: "PASSED", risk_score: 0.5, affected: [] },
      { id: 8, name: "Cascading: auth → gateway", result: "CRITICAL", risk_score: 8.2, affected: ["gateway", "api"] },
      { id: 9, name: "Single node: worker failure", result: "WARNING", risk_score: 4.1, affected: ["worker"] },
      { id: 10, name: "Single node: auth failure", result: "WARNING", risk_score: 4.8, affected: ["api"] },
      { id: 11, name: "Single node: db_replica failure", result: "PASSED", risk_score: 2.0, affected: [] },
      { id: 12, name: "Resource: cpu saturation on api", result: "WARNING", risk_score: 5.5, affected: ["api", "worker"] },
      { id: 13, name: "Latency: db_primary response > 10s", result: "WARNING", risk_score: 6.0, affected: ["api", "worker"] },
      { id: 14, name: "Single node: api failure (1 replica)", result: "PASSED", risk_score: 1.5, affected: [] },
      { id: 15, name: "Single node: api failure (2 replicas)", result: "PASSED", risk_score: 0.8, affected: [] },
    ],
  },
};

export default function SimulatePage() {
  return (
    <Suspense fallback={<div className="max-w-[1200px] mx-auto px-6 py-10 text-[#64748b]">Loading… / 読み込み中…</div>}>
      <SimulatePageInner />
    </Suspense>
  );
}

function SimulatePageInner() {
  const locale = useLocale();
  const t = appDict.simulate[locale] ?? appDict.simulate.en;
  const tProjects = appDict.projects[locale] ?? appDict.projects.en;
  const searchParams = useSearchParams();
  const router = useRouter();
  const preselectedProjectId = searchParams?.get("project") ?? null;

  const [topTab, setTopTab] = useState<TopTab>("quickstart");
  const [selected, setSelected] = useState<string | null>(null);
  const [yamlText, setYamlText] = useState("");
  const [yamlError, setYamlError] = useState<string | null>(null); // FORM-02: リアルタイムバリデーション
  const [uploadedFileName, setUploadedFileName] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [runProgress, setRunProgress] = useState(0); // DEMO-03: progress display
  const [result, setResult] = useState<SimulationResult | null>(null);
  const [scanSummary, setScanSummary] = useState<CloudSimulationResult["scan_summary"] | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);
  const [saveWarning, setSaveWarning] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Project selector
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(preselectedProjectId);

  // Quick Start sub-sections
  const [showYamlEditor, setShowYamlEditor] = useState(false);

  // Agent Connect
  const [apiKey] = useState("fray_sk_" + "xxxxxxxxxxxxxxxxxxxxxxxxxxxx");
  const [connectedAgents] = useState<ConnectedAgent[]>(MOCK_AGENTS);

  // Load projects for selector
  useEffect(() => {
    api.getProjects().then((data) => setProjects(Array.isArray(data) ? data : [])).catch(() => {});
  }, []);

  // If a project is preselected and has topology_yaml, load it
  useEffect(() => {
    if (!selectedProjectId || !projects.length) return;
    const proj = projects.find((p) => p.id === selectedProjectId);
    if (proj?.topology_yaml) {
      setYamlText(proj.topology_yaml);
      setSelected(null);
    }
  }, [selectedProjectId, projects]);

  // DATA-02: YAML入力サニタイズ — サイズ・危険パターン検証
  const MAX_YAML_BYTES = 512 * 1024; // 512 KB limit

  function sanitizeYamlInput(raw: string): { ok: boolean; text: string; error?: string } {
    if (new TextEncoder().encode(raw).length > MAX_YAML_BYTES) {
      return { ok: false, text: "", error: "File too large (max 512 KB). Please reduce the topology size." };
    }
    // Strip null bytes and non-printable control characters (except tab/newline/CR)
    const cleaned = raw.replace(/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/g, "");
    // Warn on YAML anchors that could cause billion-laughs DoS — strip them
    if (/&\w+\s*\n/.test(cleaned) && (cleaned.match(/\*\w+/g)?.length ?? 0) > 100) {
      return { ok: false, text: "", error: "Detected excessive YAML anchor expansion. Please simplify the topology." };
    }
    return { ok: true, text: cleaned };
  }

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    // DATA-02: reject oversized files early
    if (file.size > MAX_YAML_BYTES) {
      setError("File too large (max 512 KB). Please reduce the topology size.");
      return;
    }
    setUploadedFileName(file.name);
    const reader = new FileReader();
    reader.onload = (ev) => {
      const text = ev.target?.result as string;
      const { ok, text: cleaned, error: sanitizeError } = sanitizeYamlInput(text);
      if (!ok) {
        setError(sanitizeError ?? "Invalid YAML input.");
        return;
      }
      setYamlText(cleaned);
    };
    reader.readAsText(file);
  };

  const canRun = (() => {
    if (selected) return true;
    if (yamlText.trim().length > 0) return true;
    return false;
  })();

  const runSimulation = async () => {
    if (!canRun) return;
    setRunning(true);
    setRunProgress(0);
    setError(null);
    setResult(null);
    setScanSummary(undefined);

    // DEMO-03: Fake progress bar — gives user visual feedback during simulation
    const progressSteps = [
      { pct: 15, delay: 200, label: locale === "ja" ? "トポロジーを解析中..." : "Parsing topology..." },
      { pct: 35, delay: 600, label: locale === "ja" ? "シナリオを生成中..." : "Generating scenarios..." },
      { pct: 60, delay: 1200, label: locale === "ja" ? "障害シミュレーション実行中..." : "Running fault simulations..." },
      { pct: 80, delay: 1800, label: locale === "ja" ? "N-Layer分析中..." : "Analyzing N-Layer model..." },
      { pct: 95, delay: 2400, label: locale === "ja" ? "レポートを生成中..." : "Generating report..." },
    ];
    const timers: ReturnType<typeof setTimeout>[] = [];
    progressSteps.forEach(({ pct, delay }) => {
      timers.push(setTimeout(() => setRunProgress(pct), delay));
    });

    try {
      let res;
      const simPayload: Record<string, string> = {};
      if (selectedProjectId) simPayload.project_id = selectedProjectId;

      if (selected && !yamlText.trim()) {
        res = await api.simulate({ sample: selected, ...simPayload });
      } else if (yamlText.trim()) {
        res = await api.simulate({ topology_yaml: yamlText, ...simPayload });
      }
      if (res) {
        setResult(res);
        // ANALYTICS-02: Track simulation completion as conversion event
        trackEvent("simulation_run", {
          score: res.overall_score,
          nines: res.nines,
          scenario: selected || "custom",
          critical_count: res.critical_failures?.length ?? 0,
        });
        // CONVERT-01: Aha Momentの計測 — 初回シミュレーション完了を特別にトラッキング
        const ahaKey = "faultray_aha_moment_reached";
        if (!localStorage.getItem(ahaKey)) {
          localStorage.setItem(ahaKey, new Date().toISOString());
          trackEvent("aha_moment", {
            score: res.overall_score,
            time_to_aha_ms: Date.now() - performance.timeOrigin,
            critical_count: res.critical_failures?.length ?? 0,
          });
        }
        // Save to localStorage for topology/dashboard to read
        localStorage.setItem("faultray_last_simulation", JSON.stringify({
          ...res,
          timestamp: new Date().toISOString(),
          source: selected || "custom",
        }));

        // Also persist to Supabase (best-effort)
        try {
          await api.saveRun({
            project_id: selectedProjectId || undefined,
            overall_score: res.overall_score,
            availability_estimate: res.availability_estimate,
            nines: res.nines,
            scenarios_passed: res.scenarios_passed,
            scenarios_failed: res.scenarios_failed,
            total_scenarios: res.total_scenarios,
            result_data: res as unknown as Record<string, unknown>,
          });
        } catch {
          // Non-critical: localStorage backup already saved — show soft warning
          setSaveWarning(
            locale === "ja"
              ? "クラウド保存に失敗しました。結果はローカルに保存されています。"
              : "Cloud save failed. Results are saved locally."
          );
          setTimeout(() => setSaveWarning(null), 5000);
        }

        // Send Slack notification if webhook URL is configured (best-effort)
        try {
          const rawIntegrations = localStorage.getItem("faultray_integrations");
          if (rawIntegrations) {
            const integrations = JSON.parse(rawIntegrations) as Record<string, string>;
            const webhookUrl = integrations.slackWebhook;
            if (webhookUrl && webhookUrl.startsWith("https://hooks.slack.com/")) {
              const criticalCount = res.critical_failures.length;
              const topRecommendation = res.suggestions[0]?.title;
              fetch("/api/notify/slack", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                  webhookUrl,
                  score: res.overall_score,
                  critical: criticalCount,
                  topRecommendation,
                  source: selected || "custom",
                }),
              }).catch(() => {
                // Non-critical: notification failure does not affect simulation
              });
            }
          }
        } catch {
          // Non-critical: notification failure does not affect simulation
        }

        // FLOW-06: Auto-redirect to results page after successful simulation
        setTimeout(() => {
          router.push("/results");
        }, 1500);
      }
    } catch (err) {
      // SIM-02 fix: never silently return demo data on fetch failure.
      // Always surface the error so the user knows results are not real.
      const rawMsg = err instanceof Error ? err.message : "Simulation request failed. Please try again.";
      // CVR-04: Free→Pro アップグレードトリガー — クォータ超過時に明示的なCTA表示
      const isQuotaError =
        rawMsg.toLowerCase().includes("quota") ||
        rawMsg.toLowerCase().includes("limit") ||
        rawMsg.toLowerCase().includes("5 simulations") ||
        rawMsg.toLowerCase().includes("upgrade");
      const message = isQuotaError
        ? (locale === "ja"
            ? `${rawMsg}\n\nProプランにアップグレードすると月100回のシミュレーションが利用できます。`
            : `${rawMsg}\n\nUpgrade to Pro for 100 simulations/month.`)
        : rawMsg;
      setError(message);
    } finally {
      timers.forEach(clearTimeout);
      setRunProgress(100);
      setRunning(false);
    }
  };

  const resetState = () => {
    setResult(null);
    setScanSummary(undefined);
    setSelected(null);
    setYamlText("");
    setUploadedFileName(null);
    setError(null);
  };

  return (
    <div className="max-w-[1200px] mx-auto px-6 py-10">
      <div className="mb-10">
        <h1 className="text-2xl font-bold mb-1">{t.title}</h1>
        <p className="text-[#94a3b8] text-sm">{t.subtitle}</p>
      </div>

      {!result ? (
        <>
          {/* Project Selector */}
          {projects.length > 0 && (
            <div className="mb-8 flex items-center gap-3">
              <label className="text-xs text-[#64748b] uppercase tracking-wider shrink-0">
                {tProjects.title}
              </label>
              <select
                value={selectedProjectId ?? ""}
                onChange={(e) => {
                  const val = e.target.value || null;
                  setSelectedProjectId(val);
                  if (!val) {
                    setYamlText("");
                    setSelected(null);
                  }
                }}
                aria-label={tProjects.title}
                className="px-3 py-2 bg-[#0d1117] border border-[#1e293b] rounded-lg text-sm text-white focus:outline-none focus:border-[#FFD700]/50 transition-colors max-w-xs"
              >
                <option value="">— No project —</option>
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
              {selectedProjectId && (
                <span className="text-xs text-[#64748b]">
                  Topology loaded from project
                </span>
              )}
            </div>
          )}

          {/* Top-level Tabs */}
          <div className="flex gap-1 mb-8 p-1 rounded-xl bg-[#0d1117] border border-[#1e293b] w-fit flex-wrap">
            <button
              onClick={() => setTopTab("quickstart")}
              className={`flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-medium transition-all ${
                topTab === "quickstart"
                  ? "bg-[#FFD700]/10 text-[#FFD700] shadow-sm"
                  : "text-[#94a3b8] hover:text-white"
              }`}
            >
              <Zap size={16} />
              Quick Start
            </button>
            <button
              onClick={() => setTopTab("cloud")}
              className={`flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-medium transition-all ${
                topTab === "cloud"
                  ? "bg-[#FFD700]/10 text-[#FFD700] shadow-sm"
                  : "text-[#94a3b8] hover:text-white"
              }`}
            >
              <Cloud size={16} />
              {locale === "ja" ? "クラウドインポート" : "Cloud Import"}
            </button>
            <button
              onClick={() => setTopTab("agent")}
              className={`flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-medium transition-all ${
                topTab === "agent"
                  ? "bg-[#FFD700]/10 text-[#FFD700] shadow-sm"
                  : "text-[#94a3b8] hover:text-white"
              }`}
            >
              <Terminal size={16} />
              Agent Connect
            </button>
          </div>

          {/* ===== QUICK START TAB ===== */}
          {topTab === "quickstart" && (
            <>
              {/* Try Demo 1-click */}
              <div className="mb-8 p-5 rounded-xl border border-[#FFD700]/20 bg-[#FFD700]/[0.04] flex items-center justify-between gap-4 flex-wrap">
                <div>
                  <p className="text-sm font-semibold text-white mb-0.5">{locale === "ja" ? "まずはデモを試してみましょう" : "Try the demo first"}</p>
                  <p className="text-xs text-[#94a3b8]">{locale === "ja" ? "Web SaaS テンプレートで即座にシミュレーションを体験できます" : "Experience an instant simulation with the Web SaaS template"}</p>
                </div>
                <Button
                  variant="primary"
                  size="sm"
                  disabled={running}
                  onClick={async () => {
                    setSelected("web-saas");
                    setYamlText("");
                    setUploadedFileName(null);
                    setError(null);
                    setResult(null);
                    setScanSummary(undefined);
                    setRunning(true);
                    try {
                      const simPayload: Record<string, string> = {};
                      if (selectedProjectId) simPayload.project_id = selectedProjectId;
                      const res = await api.simulate({ sample: "web-saas", ...simPayload });
                      setResult(res);
                      localStorage.setItem("faultray_last_simulation", JSON.stringify({
                        ...res,
                        timestamp: new Date().toISOString(),
                        source: "web-saas",
                      }));
                    } catch (err) {
                      // SIM-02 fix: surface error rather than silently returning demo data
                      const message =
                        err instanceof Error
                          ? err.message
                          : "Demo simulation failed. Please try again.";
                      setError(message);
                    } finally {
                      setRunning(false);
                    }
                  }}
                  className="shrink-0"
                >
                  {running ? (
                    <><Loader2 size={14} className="animate-spin" /> Running...</>
                  ) : (
                    <><Zap size={14} /> Try Demo (1-click)</>
                  )}
                </Button>
              </div>

              {/* Sample Selection */}
              <div className="mb-8">
                <h2 className="text-sm font-semibold text-[#94a3b8] uppercase tracking-wider mb-4">Choose a sample topology</h2>
                <div className="grid md:grid-cols-2 gap-4">
                  {SAMPLES.map((sample) => {
                    const Icon = sample.icon;
                    const isSelected = selected === sample.id;
                    return (
                      <button
                        key={sample.id}
                        onClick={() => { setSelected(sample.id); setYamlText(""); setUploadedFileName(null); }}
                        className={`text-left p-5 rounded-2xl border transition-all duration-200 ${
                          isSelected
                            ? "border-[#FFD700] bg-[#FFD700]/[0.04] shadow-[0_0_30px_rgba(255,215,0,0.1)]"
                            : "border-[#1e293b] bg-[#111827] hover:border-[#FFD700]/30 hover:bg-[#1a2035]"
                        }`}
                      >
                        <div className="flex items-start gap-4">
                          <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${isSelected ? "bg-[#FFD700]/20" : "bg-[#FFD700]/[0.06]"} border border-[#FFD700]/10`}>
                            <Icon size={20} className="text-[#FFD700]" />
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 mb-1">
                              <h3 className="font-bold text-sm">{sample.name}</h3>
                              <Badge variant="gold">{sample.components} nodes</Badge>
                            </div>
                            <p className="text-xs text-[#94a3b8]">{sample.desc}</p>
                          </div>
                          <div className={`w-5 h-5 rounded-full border-2 flex items-center justify-center shrink-0 ${isSelected ? "border-[#FFD700]" : "border-[#1e293b]"}`}>
                            {isSelected && <div className="w-2.5 h-2.5 rounded-full bg-[#FFD700]" />}
                          </div>
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Divider */}
              <div className="flex items-center gap-4 mb-8">
                <div className="h-px flex-1 bg-[#1e293b]" />
                <span className="text-xs text-[#64748b] font-medium">OR UPLOAD YOUR OWN</span>
                <div className="h-px flex-1 bg-[#1e293b]" />
              </div>

              {/* File Upload Area */}
              <div id="simulate-file-upload" className="mb-6">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".yaml,.yml,.json,.tfstate"
                  onChange={handleFileUpload}
                  aria-label={locale === "ja" ? "トポロジーファイルをアップロード" : "Upload topology file"}
                  className="hidden"
                />
                <button
                  onClick={() => { fileInputRef.current?.click(); }}
                  className="w-full p-10 rounded-2xl border-2 border-dashed border-[#1e293b] hover:border-[#FFD700]/30 transition-colors text-center"
                >
                  <Upload size={28} className="mx-auto mb-3 text-[#64748b]" />
                  <p className="text-sm font-medium mb-1">
                    {uploadedFileName ? (
                      <span className="text-[#FFD700]">{uploadedFileName}</span>
                    ) : (
                      "Drop your topology file here"
                    )}
                  </p>
                  <p className="text-xs text-[#64748b]">
                    Supports .yaml, .yml, .json, .tfstate
                  </p>
                </button>
                {uploadedFileName && yamlText && (
                  <div className="mt-3">
                    <pre className="p-4 bg-[#0d1117] border border-[#1e293b] rounded-xl text-xs font-mono text-[#94a3b8] max-h-[150px] overflow-auto">
                      {yamlText.slice(0, 1000)}{yamlText.length > 1000 ? "\n..." : ""}
                    </pre>
                  </div>
                )}
              </div>

              {/* YAML Editor Expander — JOURNEY-03: YAMLの学習曲線を下げる説明を追加 */}
              <div className="mb-8">
                <button
                  onClick={() => setShowYamlEditor(!showYamlEditor)}
                  className="flex items-center gap-2 text-sm text-[#94a3b8] hover:text-white transition-colors"
                >
                  {showYamlEditor ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                  <FileCode size={14} />
                  <span>
                    {locale === "ja"
                      ? "自分のインフラのYAMLを書く（上級者向け）"
                      : "Write your own YAML topology (advanced)"}
                  </span>
                </button>
                {showYamlEditor && (
                  <div className="mt-4">
                    {/* JOURNEY-03: Quick-start guide for YAML newcomers */}
                    <div className="mb-4 p-4 rounded-xl border border-blue-500/15 bg-blue-500/[0.05] text-xs text-[#94a3b8] space-y-1.5">
                      <p className="font-semibold text-blue-300">
                        {locale === "ja" ? "YAMLの書き方（3分で覚えられます）" : "YAML quick guide — learn in 3 minutes"}
                      </p>
                      <p>
                        {locale === "ja"
                          ? "1. コンポーネントを列挙（例: app_server, database, cache）"
                          : "1. List your components (e.g., app_server, database, cache)"}
                      </p>
                      <p>
                        {locale === "ja"
                          ? "2. 各コンポーネントに可用性（availability）と依存関係（requires）を指定"
                          : "2. Set availability (0–1) and dependencies (requires:) for each"}
                      </p>
                      <p>
                        {locale === "ja"
                          ? "3. まず「Load example」でサンプルを読み込んで修正するのが一番簡単です"
                          : "3. Easiest: click \"Load example\" below and edit to match your stack"}
                      </p>
                    </div>
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs font-medium text-[#94a3b8]">Infrastructure Topology (YAML)</span>
                      <div className="flex items-center gap-3">
                        {/* EXPORT-02: YAML構成データの再ダウンロード */}
                        {yamlText.trim() && (
                          <button
                            onClick={() => {
                              const blob = new Blob([yamlText], { type: "text/yaml" });
                              const url = URL.createObjectURL(blob);
                              const a = document.createElement("a");
                              a.href = url;
                              a.download = "faultray-topology.yaml";
                              a.click();
                              URL.revokeObjectURL(url);
                            }}
                            className="text-xs text-[#64748b] hover:text-white transition-colors"
                          >
                            {locale === "ja" ? "YAMLをダウンロード" : "Download YAML"}
                          </button>
                        )}
                        <button
                          onClick={() => { setYamlText(YAML_PLACEHOLDER); setSelected(null); setUploadedFileName(null); }}
                          className="text-xs text-[#FFD700] hover:text-[#ffe44d] transition-colors"
                        >
                          {locale === "ja" ? "サンプルを読み込む" : "Load example"}
                        </button>
                      </div>
                    </div>
                    <textarea
                      value={yamlText}
                      onChange={(e) => {
                        const val = e.target.value;
                        setYamlText(val);
                        setSelected(null);
                        setUploadedFileName(null);
                        // FORM-02 / ERRMSG-04: リアルタイムバリデーション（行番号付きエラー）
                        if (val.trim()) {
                          const lines = val.split("\n");
                          let err: string | null = null;
                          for (let i = 0; i < lines.length; i++) {
                            const line = lines[i];
                            // タブ文字はYAML非推奨
                            if (/^\t/.test(line)) {
                              err = locale === "ja"
                                ? `${i + 1}行目: タブ文字は使用できません。スペースを使用してください。`
                                : `Line ${i + 1}: Tab character found — use spaces instead.`;
                              break;
                            }
                            // ERRMSG-04: Detect duplicate colons that indicate malformed keys
                            if (/^(\s*\w[\w\s-]*):\s*:\s*/.test(line)) {
                              err = locale === "ja"
                                ? `${i + 1}行目: 不正な構文 — コロンが重複しています。`
                                : `Line ${i + 1}: Syntax error — duplicate colon detected.`;
                              break;
                            }
                          }
                          // componentsキーが存在するか簡易チェック
                          if (!err && !val.includes("components:")) {
                            err = locale === "ja"
                              ? "`components:` キーが見つかりません。少なくとも1つのコンポーネントを定義してください。"
                              : "Missing `components:` key — define at least one component.";
                          }
                          setYamlError(err);
                        } else {
                          setYamlError(null);
                        }
                      }}
                      placeholder={YAML_PLACEHOLDER}
                      // MOBILE-02: inputmode="none" prevents mobile keyboard on YAML editor
                      // On mobile, recommend using the sample topology selector instead
                      className={`w-full h-[350px] px-4 py-3 bg-[#0d1117] border rounded-xl text-sm font-mono text-[#e2e8f0] placeholder-[#3a4558] focus:outline-none resize-y transition-colors ${yamlError ? "border-red-500/50 focus:border-red-500" : "border-[#1e293b] focus:border-[#FFD700]/50"}`}
                      aria-label={locale === "ja" ? "YAMLトポロジー定義" : "YAML topology definition"}
                      spellCheck={false}
                      maxLength={100000}
                    />
                    {/* MOBILE-02: Mobile hint — recommend sample topology or file upload */}
                    <p className="text-xs text-[#475569] mt-1 md:hidden">
                      {locale === "ja"
                        ? "モバイルでのYAML編集は難しい場合があります。上のサンプルトポロジーを選択するか、PCで作成したYAMLファイルをアップロードすることをお勧めします。"
                        : "YAML editing on mobile can be challenging. Try selecting a sample topology above, or upload a YAML file you prepared on desktop."
                      }
                    </p>
                    {/* FORM-02: リアルタイムバリデーションエラー表示 */}
                    {yamlError && (
                      <p className="text-xs text-red-400 mt-1 flex items-center gap-1">
                        <span>&#9888;</span> {yamlError}
                      </p>
                    )}
                    <p className="text-xs text-[#64748b] mt-2">
                      {locale === "ja"
                        ? "コンポーネント種別: app_server, database, cache, load_balancer, queue / 依存関係: requires, optional, async"
                        : "Component types: app_server, database, cache, load_balancer, queue | Dependencies: requires, optional, async"}
                    </p>
                  </div>
                )}
              </div>

              {error && (
                <div role="alert" className="mb-6 p-4 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
                  {error}
                </div>
              )}
              {saveWarning && (
                <div className="mb-4 p-3 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-400 text-sm flex items-center gap-2">
                  <AlertTriangle size={14} className="shrink-0" />
                  {saveWarning}
                </div>
              )}

              <div className="flex flex-col items-center gap-4">
                <Button
                  size="lg"
                  disabled={!canRun || running}
                  onClick={runSimulation}
                  className="min-w-[200px]"
                >
                  {running ? (
                    <>
                      <Loader2 size={18} className="animate-spin" />
                      {locale === "ja" ? "2,000+シナリオ実行中..." : "Running 2,000+ Scenarios..."}
                    </>
                  ) : (
                    <>
                      <Zap size={18} />
                      {locale === "ja" ? "シミュレーション実行" : "Run Simulation"}
                    </>
                  )}
                </Button>
                {/* DEMO-03: プログレスバー — 実行中の待ち時間を視覚化 */}
                {running && (
                  <div className="w-full max-w-[400px]">
                    <div className="flex justify-between text-xs text-[#64748b] mb-1.5">
                      <span>{locale === "ja" ? "進行中..." : "Processing..."}</span>
                      <span>{runProgress}%</span>
                    </div>
                    <div className="h-2 bg-[#1e293b] rounded-full overflow-hidden">
                      <div
                        className="h-full bg-[#FFD700] rounded-full transition-all duration-500"
                        style={{ width: `${runProgress}%` }}
                      />
                    </div>
                    <p className="text-[11px] text-[#475569] text-center mt-2">
                      {locale === "ja"
                        ? "本番環境には一切アクセスしません。純粋なシミュレーションです。"
                        : "No production access. Pure simulation — your infra is untouched."}
                    </p>
                  </div>
                )}
              </div>
            </>
          )}

          {/* ===== CLOUD IMPORT TAB ===== FUNC-03 */}
          {topTab === "cloud" && (
            <div className="space-y-8">
              {/* Header */}
              <div className="flex items-start gap-4 p-5 rounded-2xl border border-blue-500/20 bg-blue-500/[0.04]">
                <Cloud size={20} className="text-blue-400 shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm font-semibold text-blue-300 mb-1">
                    {locale === "ja" ? "クラウド構成を自動取り込み" : "Auto-discover your cloud topology"}
                  </p>
                  <p className="text-xs text-[#94a3b8]">
                    {locale === "ja"
                      ? "読み取り専用の権限で AWS・GCP・Azure のリソースを自動検出し、シミュレーション可能なトポロジーに変換します。"
                      : "Connect with read-only credentials to auto-discover AWS, GCP, or Azure resources and convert them to a simulatable topology."}
                  </p>
                </div>
              </div>

              {/* Provider selection */}
              <div>
                <p className="text-xs font-semibold text-[#64748b] uppercase tracking-wide mb-4">
                  {locale === "ja" ? "クラウドプロバイダーを選択" : "Select cloud provider"}
                </p>
                <div className="grid sm:grid-cols-3 gap-4">
                  {(["aws", "gcp", "azure"] as const).map((provider) => {
                    const meta = {
                      aws:   { label: "Amazon Web Services", color: "text-amber-400",  bg: "bg-amber-400/10", border: "border-amber-400/20",  badge: "EC2, RDS, ELB, Lambda, S3" },
                      gcp:   { label: "Google Cloud",        color: "text-blue-400",   bg: "bg-blue-400/10",  border: "border-blue-400/20",   badge: "Compute, GKE, Cloud SQL, BigQuery" },
                      azure: { label: "Microsoft Azure",     color: "text-sky-400",    bg: "bg-sky-400/10",   border: "border-sky-400/20",    badge: "VMs, AKS, SQL, CosmosDB" },
                    }[provider];
                    return (
                      <div key={provider} className={`p-4 rounded-xl border ${meta.border} ${meta.bg} flex flex-col gap-3`}>
                        <div className="flex items-center gap-2">
                          <Server size={16} className={meta.color} />
                          <span className={`text-sm font-bold ${meta.color}`}>{meta.label}</span>
                        </div>
                        <p className="text-[11px] text-[#64748b]">{meta.badge}</p>
                        <div className="mt-auto">
                          <button
                            onClick={() => { setTopTab("agent"); }}
                            className={`w-full py-2 rounded-lg text-xs font-semibold border ${meta.border} ${meta.color} hover:opacity-80 transition-opacity`}
                          >
                            {locale === "ja" ? "セットアップ手順を見る" : "View setup steps →"}
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Terraform Import */}
              <div className="p-5 rounded-xl border border-[#1e293b] bg-[#0d1117]">
                <div className="flex items-center gap-2 mb-3">
                  <Database size={16} className="text-purple-400" />
                  <p className="text-sm font-semibold">{locale === "ja" ? "Terraform State インポート" : "Terraform State Import"}</p>
                  <Badge variant="default" className="text-[10px]">tfstate</Badge>
                </div>
                <p className="text-xs text-[#94a3b8] mb-4">
                  {locale === "ja"
                    ? "terraform.tfstate ファイルを貼り付けるか、アップロードするとトポロジーを自動生成します。"
                    : "Paste or upload your terraform.tfstate file to auto-generate a topology for simulation."}
                </p>
                <button
                  onClick={() => {
                    setTopTab("quickstart");
                    // Scroll to file upload area
                    setTimeout(() => {
                      const el = document.getElementById("simulate-file-upload");
                      if (el) el.scrollIntoView({ behavior: "smooth" });
                    }, 100);
                  }}
                  className="text-xs font-medium text-[#FFD700] hover:underline"
                >
                  {locale === "ja" ? "ファイルアップロードへ →" : "Go to file upload →"}
                </button>
              </div>

              {/* IAM policy snippet */}
              <div>
                <p className="text-xs font-semibold text-[#64748b] uppercase tracking-wide mb-3">
                  {locale === "ja" ? "最小権限 IAM ポリシー（AWS 例）" : "Minimum IAM policy (AWS example)"}
                </p>
                <CodeBlock language="json" code={`{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": [
      "ec2:Describe*",
      "rds:Describe*",
      "elasticloadbalancing:Describe*",
      "lambda:List*", "lambda:Get*",
      "s3:ListAllMyBuckets", "s3:GetBucketLocation",
      "cloudwatch:GetMetricStatistics",
      "ecs:List*", "ecs:Describe*",
      "eks:ListClusters", "eks:DescribeCluster"
    ],
    "Resource": "*"
  }]
}`} />
                <p className="text-xs text-[#64748b] mt-2">
                  <Shield size={11} className="inline mr-1 text-emerald-400" />
                  {locale === "ja"
                    ? "読み取り専用アクション（Describe*/List*/Get*）のみ。書き込み権限は不要です。"
                    : "Read-only actions only (Describe*/List*/Get*). No write permissions required."}
                </p>
              </div>

              {/* Terraform: export tfstate guide */}
              <div>
                <p className="text-xs font-semibold text-[#64748b] uppercase tracking-wide mb-3">
                  {locale === "ja" ? "tfstate のエクスポート方法" : "How to export tfstate"}
                </p>
                <CodeBlock language="bash" code={`# Export local state
terraform state pull > topology.tfstate

# Or export from Terraform Cloud
terraform login
terraform state pull > topology.tfstate`} />
              </div>
            </div>
          )}

          {/* ===== AGENT CONNECT TAB ===== */}
          {topTab === "agent" && (
            <div className="space-y-8">
              {/* Security Notice */}
              <div className="flex items-start gap-3 p-4 rounded-xl bg-emerald-500/5 border border-emerald-500/20">
                <Shield size={18} className="text-emerald-400 mt-0.5 shrink-0" />
                <div>
                  <p className="text-sm font-medium text-emerald-400">Your credentials stay in your VPC</p>
                  <p className="text-xs text-[#94a3b8] mt-1">
                    The FaultRay agent runs inside your infrastructure. Only topology data and simulation results
                    are sent to FaultRay SaaS. Cloud provider credentials never leave your environment.
                  </p>
                </div>
              </div>

              {/* Step 1: API Key */}
              <div>
                <div className="flex items-center gap-3 mb-4">
                  <div className="w-7 h-7 rounded-full bg-[#FFD700]/10 border border-[#FFD700]/30 flex items-center justify-center text-xs font-bold text-[#FFD700]">1</div>
                  <h3 className="text-sm font-semibold">Get your API key</h3>
                </div>
                <div className="ml-10">
                  <div className="flex items-center gap-3 p-3 rounded-lg bg-[#0d1117] border border-[#1e293b]">
                    <code className="flex-1 text-sm font-mono text-[#e2e8f0] truncate">{apiKey}</code>
                    <CopyButton text={apiKey} />
                  </div>
                  <p className="text-xs text-[#64748b] mt-2">
                    Generate a new key in <Link href="/settings" className="text-[#FFD700] hover:underline">Settings</Link>. Keep it secret.
                  </p>
                </div>
              </div>

              {/* Step 2: Install */}
              <div>
                <div className="flex items-center gap-3 mb-4">
                  <div className="w-7 h-7 rounded-full bg-[#FFD700]/10 border border-[#FFD700]/30 flex items-center justify-center text-xs font-bold text-[#FFD700]">2</div>
                  <h3 className="text-sm font-semibold">Install the agent</h3>
                </div>
                <div className="ml-10">
                  <CodeBlock code="pip install faultray" />
                </div>
              </div>

              {/* Step 3: Connect & Scan */}
              <div>
                <div className="flex items-center gap-3 mb-4">
                  <div className="w-7 h-7 rounded-full bg-[#FFD700]/10 border border-[#FFD700]/30 flex items-center justify-center text-xs font-bold text-[#FFD700]">3</div>
                  <h3 className="text-sm font-semibold">Connect and scan your infrastructure</h3>
                </div>
                <div className="ml-10 space-y-3">
                  <CodeBlock
                    code={`# Connect the agent to FaultRay SaaS
faultray agent connect --token YOUR_API_KEY --url https://faultray.com`}
                  />
                  <p className="text-xs text-[#94a3b8] mb-3">Then scan your infrastructure:</p>
                  <CodeBlock
                    code={`# Scan specific providers
faultray scan --provider aws --region ap-northeast-1
faultray scan --provider gcp --project my-project
faultray scan --provider azure --subscription xxx
faultray scan --provider kubernetes

# Or scan all providers at once
faultray scan --all`}
                  />
                </div>
              </div>

              {/* Step 4: Connected Agents */}
              <div>
                <div className="flex items-center gap-3 mb-4">
                  <div className="w-7 h-7 rounded-full bg-[#FFD700]/10 border border-[#FFD700]/30 flex items-center justify-center text-xs font-bold text-[#FFD700]">4</div>
                  <h3 className="text-sm font-semibold">Connected agents</h3>
                </div>
                <div className="ml-10">
                  {connectedAgents.length === 0 ? (
                    <div className="p-8 rounded-2xl border border-dashed border-[#1e293b] text-center">
                      <Radio size={24} className="mx-auto mb-3 text-[#64748b]" />
                      <p className="text-sm text-[#94a3b8] mb-1">No agents connected yet</p>
                      <p className="text-xs text-[#64748b]">
                        Run the commands above to connect your first agent. Results will appear here automatically.
                      </p>
                    </div>
                  ) : (
                    <div className="space-y-3">
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-xs text-[#64748b]">{connectedAgents.length} agent(s) connected</span>
                        <button className="flex items-center gap-1.5 text-xs text-[#94a3b8] hover:text-white transition-colors">
                          <RefreshCw size={12} />
                          Refresh
                        </button>
                      </div>
                      {connectedAgents.map((agent) => (
                        <Card key={agent.id} className="!p-4">
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-3">
                              <div className={`w-2.5 h-2.5 rounded-full ${
                                agent.status === "connected" ? "bg-emerald-400" :
                                agent.status === "scanning" ? "bg-[#FFD700] animate-pulse" :
                                "bg-red-400"
                              }`} />
                              <div>
                                <p className="text-sm font-medium">{agent.name}</p>
                                <p className="text-xs text-[#64748b]">{agent.provider} / {agent.region}</p>
                              </div>
                            </div>
                            <div className="text-right">
                              <p className="text-sm font-mono text-[#e2e8f0]">{agent.components} components</p>
                              <p className="text-xs text-[#64748b]">Last scan: {agent.lastScan}</p>
                            </div>
                          </div>
                        </Card>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
        </>
      ) : (
        <>
          <ResultsPanel result={result} scanSummary={scanSummary} simulateT={t} />
          <div className="flex justify-center mt-6">
            <Button variant="secondary" onClick={resetState}>
              Run Another Simulation
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
