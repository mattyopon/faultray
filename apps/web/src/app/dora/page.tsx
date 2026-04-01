"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useState, useEffect } from "react";
import {
  ShieldAlert,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  TrendingUp,
  TrendingDown,
  Minus,
  Download,
  ArrowRight,
  ChevronDown,
  ChevronRight,
  FileText,
  Rocket,
} from "lucide-react";
import { useLocale } from "@/lib/useLocale";
import { appDict } from "@/i18n/app-dict";

/* ============================================================
 * Types
 * ============================================================ */

interface DoraPillar {
  id: string;
  name: string;
  articles: string;
  score: number;
  status: "compliant" | "partial" | "non_compliant";
  compliant: number;
  total: number;
}

interface DoraControl {
  id: string;
  pillar: string;
  description: string;
  status: "compliant" | "partial" | "non_compliant";
  last_assessed: string;
  evidence: string | null;
}

interface DoraGap {
  control_id: string;
  severity: "critical" | "high" | "medium";
  description: string;
  remediation: string;
  deadline: string;
}

interface DoraMetric {
  value: number;
  unit: string;
  trend: "up" | "down" | "stable";
  benchmark: number;
  status: "good" | "warning" | "critical";
}

interface DoraMetrics {
  deployment_frequency: DoraMetric;
  lead_time: DoraMetric;
  change_failure_rate: DoraMetric;
  mttr: DoraMetric;
}

interface EvidencePackage {
  pillar: string;
  items: number;
  total_required: number;
  coverage: number;
}

interface DoraData {
  assessed_at: string;
  organization: string;
  overall_score: number;
  pillars: DoraPillar[];
  controls: DoraControl[];
  gaps: DoraGap[];
  dora_metrics: DoraMetrics;
  evidence_packages: EvidencePackage[];
}

/* ============================================================
 * Static demo fallback
 * ============================================================ */

const DEMO: DoraData = {
  assessed_at: "2026-04-01T09:00:00Z",
  organization: "Demo Organization",
  overall_score: 72,
  pillars: [
    { id: "pillar1", name: "ICT Risk Management", articles: "Articles 5-16", score: 78, status: "partial", compliant: 6, total: 10 },
    { id: "pillar2", name: "Incident Management", articles: "Articles 17-23", score: 62, status: "partial", compliant: 4, total: 8 },
    { id: "pillar3", name: "Resilience Testing", articles: "Articles 24-27", score: 70, status: "partial", compliant: 5, total: 7 },
    { id: "pillar4", name: "Third-Party Risk", articles: "Articles 28-30", score: 55, status: "non_compliant", compliant: 3, total: 8 },
    { id: "pillar5", name: "Information Sharing", articles: "Article 45", score: 82, status: "compliant", compliant: 4, total: 5 },
  ],
  controls: [
    { id: "P1-01", pillar: "pillar1", description: "ICT Risk Management Policy", status: "compliant", last_assessed: "2026-03-15", evidence: "doc_001.pdf" },
    { id: "P1-02", pillar: "pillar1", description: "Asset Management & Classification", status: "compliant", last_assessed: "2026-03-15", evidence: "doc_002.pdf" },
    { id: "P1-03", pillar: "pillar1", description: "Risk Assessment Process", status: "partial", last_assessed: "2026-02-28", evidence: "doc_003.pdf" },
    { id: "P1-04", pillar: "pillar1", description: "Protection & Prevention Controls", status: "non_compliant", last_assessed: "2026-02-01", evidence: null },
    { id: "P2-01", pillar: "pillar2", description: "Incident Detection & Classification", status: "compliant", last_assessed: "2026-03-20", evidence: "doc_010.pdf" },
    { id: "P2-02", pillar: "pillar2", description: "Major Incident Reporting (4h SLA)", status: "non_compliant", last_assessed: "2026-03-01", evidence: null },
    { id: "P2-03", pillar: "pillar2", description: "Incident Response Procedures", status: "partial", last_assessed: "2026-03-10", evidence: "doc_012.pdf" },
    { id: "P2-04", pillar: "pillar2", description: "Root Cause Analysis Process", status: "compliant", last_assessed: "2026-03-20", evidence: "doc_013.pdf" },
    { id: "P3-01", pillar: "pillar3", description: "Periodic ICT Tool Testing", status: "compliant", last_assessed: "2026-03-25", evidence: "doc_020.pdf" },
    { id: "P3-02", pillar: "pillar3", description: "Threat-Led Penetration Testing (TLPT)", status: "non_compliant", last_assessed: "2026-01-15", evidence: null },
    { id: "P3-03", pillar: "pillar3", description: "Test Result Remediation Tracking", status: "compliant", last_assessed: "2026-03-25", evidence: "doc_022.pdf" },
    { id: "P4-01", pillar: "pillar4", description: "Third-Party Identification & Classification", status: "partial", last_assessed: "2026-02-20", evidence: "doc_030.pdf" },
    { id: "P4-02", pillar: "pillar4", description: "DORA Contract Clause Standardization", status: "non_compliant", last_assessed: "2026-01-31", evidence: null },
    { id: "P4-03", pillar: "pillar4", description: "Cloud Concentration Risk Assessment", status: "non_compliant", last_assessed: "2026-01-31", evidence: null },
    { id: "P4-04", pillar: "pillar4", description: "Critical Third-Party Oversight Framework", status: "partial", last_assessed: "2026-02-28", evidence: "doc_033.pdf" },
    { id: "P5-01", pillar: "pillar5", description: "Cyber Threat Intelligence Sharing", status: "compliant", last_assessed: "2026-03-28", evidence: "doc_040.pdf" },
    { id: "P5-02", pillar: "pillar5", description: "Incident Information Exchange", status: "compliant", last_assessed: "2026-03-28", evidence: "doc_041.pdf" },
    { id: "P5-03", pillar: "pillar5", description: "Cross-Industry Collaboration", status: "partial", last_assessed: "2026-03-10", evidence: "doc_042.pdf" },
  ],
  gaps: [
    { control_id: "P4-02", severity: "critical", description: "DORA-required contract clauses missing from 23 vendor agreements", remediation: "Update all vendor contracts with DORA-required provisions", deadline: "2026-06-30" },
    { control_id: "P2-02", severity: "critical", description: "Incident reporting pipeline not automated within 4-hour regulatory window", remediation: "Implement automated incident reporting with 4h SLA", deadline: "2026-05-31" },
    { control_id: "P4-03", severity: "high", description: "No concentration risk assessment for AWS/Azure cloud dependency", remediation: "Perform concentration risk assessment, document multi-cloud strategy", deadline: "2026-07-31" },
    { control_id: "P3-02", severity: "high", description: "No TLPT program established; required for systemic institutions", remediation: "Establish annual TLPT program with qualified external testers", deadline: "2026-09-30" },
    { control_id: "P1-04", severity: "high", description: "Insufficient network segmentation between critical systems", remediation: "Implement zero-trust network segmentation", deadline: "2026-06-30" },
  ],
  dora_metrics: {
    deployment_frequency: { value: 12.3, unit: "per week", trend: "up", benchmark: 15.0, status: "good" },
    lead_time: { value: 4.2, unit: "days", trend: "down", benchmark: 3.0, status: "warning" },
    change_failure_rate: { value: 8.5, unit: "%", trend: "down", benchmark: 5.0, status: "warning" },
    mttr: { value: 47, unit: "minutes", trend: "down", benchmark: 30, status: "good" },
  },
  evidence_packages: [
    { pillar: "pillar1", items: 6, total_required: 10, coverage: 60 },
    { pillar: "pillar2", items: 4, total_required: 8, coverage: 50 },
    { pillar: "pillar3", items: 4, total_required: 7, coverage: 57 },
    { pillar: "pillar4", items: 2, total_required: 8, coverage: 25 },
    { pillar: "pillar5", items: 4, total_required: 5, coverage: 80 },
  ],
};

/* ============================================================
 * Helpers
 * ============================================================ */

function scoreColor(score: number): string {
  if (score >= 80) return "#10b981";
  if (score >= 60) return "#f59e0b";
  return "#ef4444";
}

function statusVariant(status: string): "green" | "yellow" | "red" | "default" {
  if (status === "compliant" || status === "good") return "green";
  if (status === "partial" || status === "warning") return "yellow";
  if (status === "non_compliant" || status === "critical") return "red";
  return "default";
}

function TrendIcon({ trend }: { trend: string }) {
  if (trend === "up") return <TrendingUp size={14} className="text-emerald-400" />;
  if (trend === "down") return <TrendingDown size={14} className="text-red-400" />;
  return <Minus size={14} className="text-[#64748b]" />;
}

/* ============================================================
 * Main Page
 * ============================================================ */

export default function DoraPage() {
  try {
    return <DoraPageInner />;
  } catch (e) {
    return <div style={{color: "red", padding: 40}}>DORA Error: {String(e)}</div>;
  }
}

function DoraPageInner() {
  const locale = useLocale();
  const t = appDict.dora[locale] ?? appDict.dora.en;
  const [data, setData] = useState<DoraData>(DEMO);
  const [loading, setLoading] = useState(true);
  const [expandedPillar, setExpandedPillar] = useState<string | null>("pillar1");
  const [showAllControls, setShowAllControls] = useState(false);

  useEffect(() => {
    fetch("/api/governance?action=dora")
      .then((r) => r.json())
      .then((d) => { if (d && d.pillars) setData(d); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const totalControls = data.controls.length;
  const compliantCount = data.controls.filter((c) => c.status === "compliant").length;
  const partialCount = data.controls.filter((c) => c.status === "partial").length;
  const nonCompliantCount = data.controls.filter((c) => c.status === "non_compliant").length;

  const pillarControls = (pillarId: string) => data.controls.filter((c) => c.pillar === pillarId);
  const displayedControls = showAllControls ? data.controls : data.controls.slice(0, 8);

  const METRIC_LABELS: Record<string, string> = {
    deployment_frequency: t.deploymentFrequency,
    lead_time: t.leadTime,
    change_failure_rate: t.changeFailureRate,
    mttr: t.mttr,
  };

  return (
    <div className="max-w-[1200px] mx-auto px-6 py-10">
      {/* Header */}
      <div className="mb-10">
        <h1 className="text-2xl font-bold mb-1 flex items-center gap-3">
          <ShieldAlert size={24} className="text-[#FFD700]" />
          {t.title}
        </h1>
        <p className="text-[#94a3b8] text-sm">{t.subtitle}</p>
        {loading && <p className="text-xs text-[#64748b] mt-1">{t.loading}</p>}
      </div>

      {/* ── 1. Score Overview ── */}
      <div className="grid md:grid-cols-4 gap-6 mb-8">
        <Card className="text-center">
          <p className="text-xs text-[#64748b] uppercase tracking-wider mb-2">{t.overallScore}</p>
          <p className="text-5xl font-extrabold font-mono" style={{ color: scoreColor(data.overall_score) }}>
            {data.overall_score}%
          </p>
          <Badge variant={statusVariant(data.overall_score >= 80 ? "compliant" : data.overall_score >= 60 ? "partial" : "non_compliant")} className="mt-2">
            {data.overall_score >= 80 ? t.compliant : data.overall_score >= 60 ? t.partial : t.nonCompliant}
          </Badge>
        </Card>
        <Card className="text-center">
          <p className="text-xs text-[#64748b] uppercase tracking-wider mb-2">{t.compliantControls}</p>
          <p className="text-5xl font-extrabold font-mono text-emerald-400">{compliantCount}</p>
          <p className="text-xs text-[#64748b] mt-2">{t.ofTotal.replace("{n}", String(totalControls))}</p>
        </Card>
        <Card className="text-center">
          <p className="text-xs text-[#64748b] uppercase tracking-wider mb-2">{t.partialControls}</p>
          <p className="text-5xl font-extrabold font-mono text-yellow-400">{partialCount}</p>
          <p className="text-xs text-[#64748b] mt-2">{t.needsImprovement}</p>
        </Card>
        <Card className="text-center">
          <p className="text-xs text-[#64748b] uppercase tracking-wider mb-2">{t.nonCompliantControls}</p>
          <p className="text-5xl font-extrabold font-mono text-red-400">{nonCompliantCount}</p>
          <p className="text-xs text-[#64748b] mt-2">{t.requiresRemediation}</p>
        </Card>
      </div>

      {/* ── 2. Pillar Breakdown ── */}
      <Card className="mb-8">
        <h3 className="text-lg font-bold mb-6 flex items-center gap-2">
          <ShieldAlert size={18} className="text-[#FFD700]" />
          {t.pillarOverview}
        </h3>
        <div className="space-y-3">
          {data.pillars.map((pillar) => (
            <div key={pillar.id}>
              <button
                className="w-full text-left"
                onClick={() => setExpandedPillar(expandedPillar === pillar.id ? null : pillar.id)}
              >
                <div className="flex items-center gap-3 py-2">
                  {expandedPillar === pillar.id
                    ? <ChevronDown size={14} className="text-[#64748b] shrink-0" />
                    : <ChevronRight size={14} className="text-[#64748b] shrink-0" />}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-sm font-medium truncate">{pillar.name}</span>
                      <div className="flex items-center gap-3 shrink-0 ml-4">
                        <span className="text-xs text-[#64748b]">{pillar.articles}</span>
                        <Badge variant={statusVariant(pillar.status)}>
                          {pillar.status === "compliant" ? t.compliant : pillar.status === "partial" ? t.partial : t.nonCompliant}
                        </Badge>
                        <span className="text-sm font-bold font-mono min-w-[44px] text-right" style={{ color: scoreColor(pillar.score) }}>
                          {pillar.score}%
                        </span>
                      </div>
                    </div>
                    <div className="h-2 bg-white/5 rounded-full overflow-hidden">
                      <div
                        className="h-full rounded-full transition-all duration-700"
                        style={{ width: `${pillar.score}%`, backgroundColor: scoreColor(pillar.score) }}
                      />
                    </div>
                  </div>
                </div>
              </button>

              {expandedPillar === pillar.id && (
                <div className="ml-6 mt-2 mb-3 space-y-2">
                  {pillarControls(pillar.id).map((ctrl) => (
                    <div
                      key={ctrl.id}
                      className={`flex items-center gap-3 p-3 rounded-lg border text-sm ${
                        ctrl.status === "compliant"
                          ? "bg-emerald-500/5 border-emerald-500/10"
                          : ctrl.status === "partial"
                            ? "bg-yellow-500/5 border-yellow-500/10"
                            : "bg-red-500/5 border-red-500/10"
                      }`}
                    >
                      {ctrl.status === "compliant"
                        ? <CheckCircle2 size={14} className="text-emerald-400 shrink-0" />
                        : ctrl.status === "partial"
                          ? <AlertTriangle size={14} className="text-yellow-400 shrink-0" />
                          : <XCircle size={14} className="text-red-400 shrink-0" />}
                      <span className="font-mono text-xs text-[#64748b] shrink-0">{ctrl.id}</span>
                      <span className="flex-1 text-[#e2e8f0]">{ctrl.description}</span>
                      <span className="text-xs text-[#64748b] shrink-0">{ctrl.last_assessed}</span>
                      {ctrl.evidence
                        ? <Badge variant="default"><FileText size={10} className="mr-1" />{t.evidenceAvailable}</Badge>
                        : <Badge variant="red"><FileText size={10} className="mr-1" />{t.noEvidence}</Badge>}
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </Card>

      {/* ── 3. Control Assessment Table ── */}
      <Card className="mb-8">
        <h3 className="text-lg font-bold mb-4 flex items-center gap-2">
          <CheckCircle2 size={18} className="text-[#FFD700]" />
          {t.controlAssessment}
        </h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#1e293b]">
                <th className="text-left py-3 px-2 text-[#64748b] font-medium">{t.controlId}</th>
                <th className="text-left py-3 px-2 text-[#64748b] font-medium">{t.description}</th>
                <th className="text-left py-3 px-2 text-[#64748b] font-medium">{t.statusCol}</th>
                <th className="text-left py-3 px-2 text-[#64748b] font-medium">{t.lastAssessed}</th>
                <th className="text-left py-3 px-2 text-[#64748b] font-medium">{t.evidence}</th>
              </tr>
            </thead>
            <tbody>
              {displayedControls.map((ctrl) => (
                <tr key={ctrl.id} className="border-b border-[#1e293b]/50 hover:bg-white/[0.02]">
                  <td className="py-3 px-2 font-mono text-xs text-[#64748b]">{ctrl.id}</td>
                  <td className="py-3 px-2 text-[#e2e8f0]">{ctrl.description}</td>
                  <td className="py-3 px-2">
                    <Badge variant={statusVariant(ctrl.status)}>
                      {ctrl.status === "compliant" ? t.pass : ctrl.status === "partial" ? t.partial : t.fail}
                    </Badge>
                  </td>
                  <td className="py-3 px-2 text-xs text-[#64748b]">{ctrl.last_assessed}</td>
                  <td className="py-3 px-2">
                    {ctrl.evidence
                      ? <span className="text-xs text-emerald-400 flex items-center gap-1"><FileText size={10} />{ctrl.evidence}</span>
                      : <span className="text-xs text-red-400">—</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {data.controls.length > 8 && (
          <div className="mt-4 text-center">
            <Button variant="secondary" size="sm" onClick={() => setShowAllControls(!showAllControls)}>
              {showAllControls ? t.showLess : t.showAll.replace("{n}", String(data.controls.length))}
            </Button>
          </div>
        )}
      </Card>

      {/* ── 4. Gap Analysis ── */}
      <Card className="mb-8">
        <h3 className="text-lg font-bold mb-4 flex items-center gap-2">
          <AlertTriangle size={18} className="text-[#FFD700]" />
          {t.gapAnalysis}
        </h3>
        <p className="text-xs text-[#64748b] mb-4">{t.gapSubtitle}</p>
        <div className="space-y-3">
          {data.gaps.map((gap, i) => (
            <div
              key={gap.control_id}
              className={`p-4 rounded-xl border ${
                gap.severity === "critical"
                  ? "bg-red-500/5 border-red-500/20"
                  : gap.severity === "high"
                    ? "bg-yellow-500/5 border-yellow-500/20"
                    : "bg-blue-500/5 border-blue-500/20"
              }`}
            >
              <div className="flex items-start gap-3">
                <span className="text-sm font-bold text-[#FFD700] shrink-0 w-5">{i + 1}.</span>
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1 flex-wrap">
                    <span className="font-mono text-xs text-[#64748b]">{gap.control_id}</span>
                    <Badge variant={gap.severity === "critical" ? "red" : gap.severity === "high" ? "yellow" : "default"}>
                      {gap.severity.toUpperCase()}
                    </Badge>
                    <span className="text-xs text-[#64748b]">{t.deadline}: {gap.deadline}</span>
                  </div>
                  <p className="text-sm text-[#e2e8f0] mb-1">{gap.description}</p>
                  <p className="text-xs text-[#FFD700] flex items-center gap-1">
                    <ArrowRight size={10} />
                    {gap.remediation}
                  </p>
                </div>
              </div>
            </div>
          ))}
        </div>
      </Card>

      {/* ── 5. DORA 4 Key Metrics ── */}
      <Card className="mb-8">
        <h3 className="text-lg font-bold mb-6 flex items-center gap-2">
          <TrendingUp size={18} className="text-[#FFD700]" />
          {t.doraMetricsTitle}
        </h3>
        <div className="grid md:grid-cols-2 gap-6">
          {(Object.entries(data.dora_metrics) as [string, DoraMetric][]).map(([key, metric]) => (
            <div key={key} className="p-4 rounded-xl border border-[#1e293b] bg-white/[0.02]">
              <div className="flex items-center justify-between mb-3">
                <p className="text-sm font-medium text-[#94a3b8]">{METRIC_LABELS[key] ?? key}</p>
                <div className="flex items-center gap-2">
                  <TrendIcon trend={metric.trend} />
                  <Badge variant={statusVariant(metric.status)}>
                    {metric.status === "good" ? t.good : metric.status === "warning" ? t.warning : t.critical}
                  </Badge>
                </div>
              </div>
              <p className="text-3xl font-extrabold font-mono text-[#e2e8f0]">
                {metric.value}
                <span className="text-sm font-normal text-[#64748b] ml-1">{metric.unit}</span>
              </p>
              <div className="mt-2 flex items-center gap-2">
                <span className="text-xs text-[#64748b]">{t.benchmark}:</span>
                <span className="text-xs font-mono text-[#FFD700]">{metric.benchmark} {metric.unit}</span>
              </div>
              <div className="mt-3 h-1.5 bg-white/5 rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full"
                  style={{
                    width: `${Math.min(100, (metric.value / (metric.benchmark * 1.5)) * 100)}%`,
                    backgroundColor: scoreColor(metric.status === "good" ? 85 : metric.status === "warning" ? 65 : 30),
                  }}
                />
              </div>
            </div>
          ))}
        </div>
      </Card>

      {/* ── 6. IPO Readiness ── */}
      <Card className="mb-8 border-[#FFD700]/20 bg-gradient-to-br from-[#0a0e1a] to-[#FFD700]/[0.03]">
        <div className="flex items-start gap-4">
          <div className="w-12 h-12 rounded-xl bg-[#FFD700]/10 border border-[#FFD700]/20 flex items-center justify-center shrink-0">
            <Rocket size={22} className="text-[#FFD700]" />
          </div>
          <div className="flex-1">
            <h3 className="text-lg font-bold text-[#FFD700] mb-2">{t.ipoReadinessTitle ?? "IPO Readiness"}</h3>
            <p className="text-sm text-[#94a3b8] leading-relaxed mb-4">
              {t.ipoReadinessDesc ?? "Going public? FaultRay proves your infrastructure meets the audit requirements investors and regulators demand."}
            </p>
            <div className="grid sm:grid-cols-2 gap-2">
              {[
                t.ipoCheckDora ?? "DORA compliance for financial services",
                t.ipoCheckSoc2 ?? "SOC2 Type II evidence package",
                t.ipoCheckIso ?? "ISO27001 control mapping",
                t.ipoCheckSla ?? "Availability SLA mathematical proof",
                t.ipoCheckRunbooks ?? "Incident response runbooks",
                t.ipoCheckAudit ?? "Change management audit trail",
              ].map((item) => (
                <div key={item} className="flex items-center gap-2 text-sm text-[#e2e8f0]">
                  <CheckCircle2 size={14} className="text-emerald-400 shrink-0" />
                  {item}
                </div>
              ))}
            </div>
          </div>
        </div>
      </Card>

      {/* ── 7. Evidence Package ── */}
      <Card>
        <div className="flex items-center justify-between mb-6">
          <h3 className="text-lg font-bold flex items-center gap-2">
            <FileText size={18} className="text-[#FFD700]" />
            {t.evidencePackage}
          </h3>
          <Button size="sm" onClick={() => alert("Generating evidence package...")}>
            <Download size={14} />
            {t.generateEvidence}
          </Button>
        </div>
        <div className="space-y-4">
          {data.evidence_packages.map((pkg) => {
            const pillar = data.pillars.find((p) => p.id === pkg.pillar);
            return (
              <div key={pkg.pillar}>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm text-[#94a3b8]">{pillar?.name ?? pkg.pillar}</span>
                  <div className="flex items-center gap-3">
                    <span className="text-xs text-[#64748b]">{pkg.items}/{pkg.total_required} {t.evidenceItems}</span>
                    <span className="text-sm font-mono font-bold" style={{ color: scoreColor(pkg.coverage) }}>
                      {pkg.coverage}%
                    </span>
                  </div>
                </div>
                <div className="h-2 bg-white/5 rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all duration-700"
                    style={{ width: `${pkg.coverage}%`, backgroundColor: scoreColor(pkg.coverage) }}
                  />
                </div>
              </div>
            );
          })}
        </div>
        <p className="text-xs text-[#64748b] mt-4 border-t border-[#1e293b] pt-3">
          {t.evidenceNote}
        </p>
      </Card>
    </div>
  );
}
