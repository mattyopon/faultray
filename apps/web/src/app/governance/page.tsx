"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useState, useEffect } from "react";
import {
  Scale,
  ChevronDown,
  ChevronRight,
  Download,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Bot,
  FileText,
  Eye,
} from "lucide-react";
import { useLocale } from "@/lib/useLocale";
import { appDict } from "@/i18n/app-dict";

/* ============================================================
 * Types
 * ============================================================ */

interface RadarScores {
  transparency: number;
  accountability: number;
  fairness: number;
  privacy: number;
  safety: number;
  security: number;
  human_oversight: number;
  data_governance: number;
  risk_management: number;
  stakeholder: number;
}

interface Framework {
  name: string;
  score: number;
  status: "compliant" | "partial" | "non_compliant";
  total_requirements: number;
  compliant: number;
  partial: number;
  non_compliant: number;
}

interface GovernanceGap {
  id: string;
  framework: string;
  requirement: string;
  priority: "critical" | "high" | "medium";
  status: "compliant" | "partial" | "non_compliant";
  action: string;
}

interface PolicyTemplate {
  id: string;
  name: string;
  description: string;
  status: "draft" | "not_started" | "published";
}

interface AiSystem {
  id: string;
  name: string;
  department: string;
  risk_level: "high" | "medium" | "low";
  status: "active" | "review" | "retired";
  shadow_ai: boolean;
}

interface GovernanceData {
  assessed_at: string;
  organization: string;
  maturity_level: number;
  overall_score: number;
  radar_scores: RadarScores;
  frameworks: { meti: Framework; iso42001: Framework; ai_act: Framework };
  gaps: GovernanceGap[];
  policy_templates: PolicyTemplate[];
  ai_systems: AiSystem[];
}

/* ============================================================
 * Static demo fallback
 * ============================================================ */

const DEMO: GovernanceData = {
  assessed_at: "2026-04-01T09:00:00Z",
  organization: "Demo Organization",
  maturity_level: 2,
  overall_score: 48,
  radar_scores: {
    transparency: 55, accountability: 60, fairness: 40, privacy: 70,
    safety: 45, security: 65, human_oversight: 35, data_governance: 60,
    risk_management: 50, stakeholder: 40,
  },
  frameworks: {
    meti: { name: "METI AI Guidelines v1.1", score: 52, status: "partial", total_requirements: 28, compliant: 6, partial: 12, non_compliant: 10 },
    iso42001: { name: "ISO/IEC 42001:2023", score: 44, status: "partial", total_requirements: 25, compliant: 4, partial: 9, non_compliant: 12 },
    ai_act: { name: "AI推進法 (Draft)", score: 47, status: "partial", total_requirements: 15, compliant: 2, partial: 9, non_compliant: 4 },
  },
  gaps: [
    { id: "G-001", framework: "meti", requirement: "Human oversight mechanisms for high-risk AI decisions", priority: "critical", status: "non_compliant", action: "Implement mandatory human review for AI decisions affecting >$10k" },
    { id: "G-002", framework: "iso42001", requirement: "AI risk assessment documentation for all deployed models", priority: "critical", status: "non_compliant", action: "Document risk assessments for 8 production AI systems" },
    { id: "G-003", framework: "ai_act", requirement: "Explainability mechanisms for automated decisions", priority: "high", status: "non_compliant", action: "Implement SHAP/LIME explanations for credit scoring model" },
    { id: "G-004", framework: "meti", requirement: "Bias testing and fairness metrics", priority: "high", status: "partial", action: "Extend bias testing to cover all protected attributes" },
    { id: "G-005", framework: "iso42001", requirement: "AI incident response procedures", priority: "high", status: "non_compliant", action: "Create AI-specific incident response runbook" },
    { id: "G-006", framework: "meti", requirement: "Third-party AI vendor assessment", priority: "medium", status: "partial", action: "Complete vendor assessments for 5 AI service providers" },
  ],
  policy_templates: [
    { id: "PT-001", name: "AI Usage Policy", description: "Acceptable use guidelines for AI tools across the organization", status: "draft" },
    { id: "PT-002", name: "AI Risk Management Policy", description: "Framework for identifying, assessing, and mitigating AI risks", status: "not_started" },
    { id: "PT-003", name: "AI Ethics Guidelines", description: "Ethical principles for AI development and deployment", status: "draft" },
    { id: "PT-004", name: "AI Data Management Policy", description: "Data governance requirements for AI training and inference", status: "not_started" },
    { id: "PT-005", name: "AI Incident Response Plan", description: "Procedures for detecting, reporting, and remediating AI incidents", status: "not_started" },
  ],
  ai_systems: [
    { id: "AI-001", name: "Credit Scoring Model", department: "Risk", risk_level: "high", status: "active", shadow_ai: false },
    { id: "AI-002", name: "Fraud Detection Engine", department: "Security", risk_level: "high", status: "active", shadow_ai: false },
    { id: "AI-003", name: "Customer Churn Predictor", department: "Marketing", risk_level: "medium", status: "active", shadow_ai: false },
    { id: "AI-004", name: "Document OCR Pipeline", department: "Operations", risk_level: "low", status: "active", shadow_ai: false },
    { id: "AI-005", name: "ChatGPT API Integration", department: "Engineering", risk_level: "medium", status: "active", shadow_ai: true },
    { id: "AI-006", name: "Automated Trading Bot", department: "Finance", risk_level: "high", status: "review", shadow_ai: false },
    { id: "AI-007", name: "HR Resume Screener", department: "HR", risk_level: "high", status: "active", shadow_ai: true },
    { id: "AI-008", name: "Sentiment Analysis API", department: "Support", risk_level: "low", status: "active", shadow_ai: false },
  ],
};

/* ============================================================
 * Radar Chart (SVG)
 * ============================================================ */

function RadarChart({ scores }: { scores: RadarScores }) {
  const size = 260;
  const cx = size / 2;
  const cy = size / 2;
  const r = 100;
  const keys = Object.keys(scores) as (keyof RadarScores)[];
  const n = keys.length;

  const angleOf = (i: number) => (i * 2 * Math.PI) / n - Math.PI / 2;

  const point = (value: number, i: number) => {
    const angle = angleOf(i);
    const dist = (value / 100) * r;
    return {
      x: cx + dist * Math.cos(angle),
      y: cy + dist * Math.sin(angle),
    };
  };

  const axisPoint = (i: number) => {
    const angle = angleOf(i);
    return { x: cx + r * Math.cos(angle), y: cy + r * Math.sin(angle) };
  };

  const labelPoint = (i: number) => {
    const angle = angleOf(i);
    const dist = r + 22;
    return { x: cx + dist * Math.cos(angle), y: cy + dist * Math.sin(angle) };
  };

  const LABELS: Record<keyof RadarScores, string> = {
    transparency: "Transparency",
    accountability: "Accountability",
    fairness: "Fairness",
    privacy: "Privacy",
    safety: "Safety",
    security: "Security",
    human_oversight: "Human\nOversight",
    data_governance: "Data\nGov.",
    risk_management: "Risk\nMgmt",
    stakeholder: "Stakeholder",
  };

  // Polygon for scores
  const dataPoints = keys.map((k, i) => point(scores[k], i));
  const dataPath = dataPoints.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ") + " Z";

  // Grid rings
  const rings = [25, 50, 75, 100];

  return (
    <svg viewBox={`0 0 ${size} ${size}`} className="w-full max-w-[320px] mx-auto" aria-label="AI Governance Radar">
      {/* Grid rings */}
      {rings.map((pct) => {
        const ringPoints = keys.map((_, i) => point(pct, i));
        const ringPath = ringPoints.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ") + " Z";
        return <path key={pct} d={ringPath} fill="none" stroke="#1e293b" strokeWidth={1} />;
      })}

      {/* Axis lines */}
      {keys.map((_, i) => {
        const ap = axisPoint(i);
        return <line key={i} x1={cx} y1={cy} x2={ap.x.toFixed(1)} y2={ap.y.toFixed(1)} stroke="#1e293b" strokeWidth={1} />;
      })}

      {/* Data polygon */}
      <path d={dataPath} fill="#FFD700" fillOpacity={0.15} stroke="#FFD700" strokeWidth={2} />

      {/* Data points */}
      {dataPoints.map((p, i) => (
        <circle key={i} cx={p.x} cy={p.y} r={3} fill="#FFD700" />
      ))}

      {/* Labels */}
      {keys.map((k, i) => {
        const lp = labelPoint(i);
        const parts = LABELS[k].split("\n");
        return (
          <text key={k} x={lp.x.toFixed(1)} y={lp.y.toFixed(1)} textAnchor="middle" fill="#64748b" fontSize={8} fontFamily="system-ui">
            {parts.map((part, pi) => (
              <tspan key={pi} x={lp.x.toFixed(1)} dy={pi === 0 ? "-4" : "10"}>{part}</tspan>
            ))}
          </text>
        );
      })}
    </svg>
  );
}

/* ============================================================
 * Helpers
 * ============================================================ */

function scoreColor(score: number): string {
  if (score >= 70) return "#10b981";
  if (score >= 50) return "#f59e0b";
  return "#ef4444";
}

function statusVariant(status: string): "green" | "yellow" | "red" | "default" {
  if (status === "compliant") return "green";
  if (status === "partial") return "yellow";
  if (status === "non_compliant") return "red";
  return "default";
}

function riskVariant(level: string): "green" | "yellow" | "red" | "default" {
  if (level === "low") return "green";
  if (level === "medium") return "yellow";
  if (level === "high") return "red";
  return "default";
}

/* ============================================================
 * Main Page
 * ============================================================ */

export default function GovernancePage() {
  const locale = useLocale();
  const t = appDict.governance[locale] ?? appDict.governance.en;
  const [data, setData] = useState<GovernanceData>(DEMO);
  const [loading, setLoading] = useState(true);
  const [expandedGap, setExpandedGap] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/governance?action=ai-governance")
      .then((r) => r.json())
      .then((d) => { if (d && d.frameworks) setData(d); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const shadowAiCount = data.ai_systems.filter((s) => s.shadow_ai).length;

  const downloadPolicy = (policy: PolicyTemplate) => {
    const content = `# ${policy.name}\n\n${policy.description}\n\n## Purpose\nThis policy establishes guidelines for ${policy.name.toLowerCase()} within the organization.\n\n## Scope\nThis policy applies to all employees, contractors, and third parties.\n\n## Generated by FaultRay AI Governance Module\nDate: ${new Date().toISOString().split("T")[0]}\n`;
    const blob = new Blob([content], { type: "text/markdown" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${policy.id}-${policy.name.replace(/\s+/g, "-").toLowerCase()}.md`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  const MATURITY_LABELS = ["", t.maturity1, t.maturity2, t.maturity3, t.maturity4, t.maturity5];

  return (
    <div className="max-w-[1200px] mx-auto px-6 py-10">
      {/* Header */}
      <div className="mb-10">
        <h1 className="text-2xl font-bold mb-1 flex items-center gap-3">
          <Scale size={24} className="text-[#FFD700]" />
          {t.title}
        </h1>
        <p className="text-[#94a3b8] text-sm">{t.subtitle}</p>
        {loading && <p className="text-xs text-[#64748b] mt-1">{t.loading}</p>}
      </div>

      {/* ── 1. Maturity Overview ── */}
      <div className="grid md:grid-cols-[1fr_auto] gap-6 mb-8">
        <Card>
          <h3 className="text-lg font-bold mb-6 flex items-center gap-2">
            <Scale size={18} className="text-[#FFD700]" />
            {t.maturityOverview}
          </h3>
          <div className="flex items-center gap-6 mb-6">
            <div className="text-center shrink-0">
              <p className="text-xs text-[#64748b] uppercase tracking-wider mb-1">{t.maturityLevel}</p>
              <p className="text-6xl font-extrabold font-mono text-[#FFD700]">{data.maturity_level}</p>
              <p className="text-xs text-[#94a3b8] mt-1">{t.of5}</p>
            </div>
            <div className="flex-1">
              <p className="text-sm font-semibold text-[#e2e8f0] mb-2">{MATURITY_LABELS[data.maturity_level]}</p>
              <div className="space-y-1">
                {[1, 2, 3, 4, 5].map((level) => (
                  <div key={level} className="flex items-center gap-2">
                    <div
                      className={`h-3 rounded-sm flex-1 transition-all ${
                        level <= data.maturity_level ? "bg-[#FFD700]" : "bg-white/5"
                      }`}
                    />
                    <span className={`text-xs w-20 shrink-0 ${level === data.maturity_level ? "text-[#FFD700] font-bold" : "text-[#475569]"}`}>
                      {t[`maturityLabel${level}` as keyof typeof t]}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
          <p className="text-xs text-[#64748b] border-t border-[#1e293b] pt-3">{t.maturityNote}</p>
        </Card>

        <Card className="flex items-center justify-center">
          <RadarChart scores={data.radar_scores} />
        </Card>
      </div>

      {/* ── 2. Multi-Framework Status ── */}
      <div className="grid md:grid-cols-3 gap-6 mb-8">
        {(Object.entries(data.frameworks) as [string, Framework][]).map(([key, fw]) => (
          <Card key={key}>
            <div className="flex items-center justify-between mb-4">
              <p className="text-sm font-semibold text-[#e2e8f0] leading-snug">{fw.name}</p>
              <Badge variant={statusVariant(fw.status)}>
                {fw.status === "compliant" ? t.compliant : fw.status === "partial" ? t.partial : t.nonCompliant}
              </Badge>
            </div>
            <p className="text-4xl font-extrabold font-mono mb-3" style={{ color: scoreColor(fw.score) }}>
              {fw.score}%
            </p>
            <div className="h-2 bg-white/5 rounded-full overflow-hidden mb-4">
              <div
                className="h-full rounded-full"
                style={{ width: `${fw.score}%`, backgroundColor: scoreColor(fw.score) }}
              />
            </div>
            <div className="space-y-1 text-xs">
              <div className="flex justify-between">
                <span className="text-[#64748b]">{t.totalRequirements}</span>
                <span className="text-[#e2e8f0] font-mono">{fw.total_requirements}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-emerald-400">{t.compliantLabel}</span>
                <span className="font-mono text-emerald-400">{fw.compliant}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-yellow-400">{t.partialLabel}</span>
                <span className="font-mono text-yellow-400">{fw.partial}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-red-400">{t.nonCompliantLabel}</span>
                <span className="font-mono text-red-400">{fw.non_compliant}</span>
              </div>
            </div>
          </Card>
        ))}
      </div>

      {/* ── 3. Gap Analysis ── */}
      <Card className="mb-8">
        <h3 className="text-lg font-bold mb-4 flex items-center gap-2">
          <AlertTriangle size={18} className="text-[#FFD700]" />
          {t.gapAnalysis}
        </h3>
        <div className="space-y-2">
          {data.gaps.map((gap) => (
            <div
              key={gap.id}
              className={`rounded-xl border transition-colors ${
                gap.status === "non_compliant" ? "border-red-500/20 bg-red-500/5" :
                gap.status === "partial" ? "border-yellow-500/20 bg-yellow-500/5" :
                "border-emerald-500/20 bg-emerald-500/5"
              }`}
            >
              <button
                className="w-full text-left p-4"
                onClick={() => setExpandedGap(expandedGap === gap.id ? null : gap.id)}
              >
                <div className="flex items-center gap-3">
                  {gap.status === "compliant"
                    ? <CheckCircle2 size={16} className="text-emerald-400 shrink-0" />
                    : gap.status === "partial"
                      ? <AlertTriangle size={16} className="text-yellow-400 shrink-0" />
                      : <XCircle size={16} className="text-red-400 shrink-0" />}
                  <div className="flex-1 text-left">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-medium text-[#e2e8f0]">{gap.requirement}</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <Badge variant={gap.priority === "critical" ? "red" : gap.priority === "high" ? "yellow" : "default"}>
                      {gap.priority.toUpperCase()}
                    </Badge>
                    <span className="text-xs text-[#64748b] font-mono">{gap.framework.toUpperCase()}</span>
                    {expandedGap === gap.id
                      ? <ChevronDown size={14} className="text-[#64748b]" />
                      : <ChevronRight size={14} className="text-[#64748b]" />}
                  </div>
                </div>
              </button>
              {expandedGap === gap.id && (
                <div className="px-4 pb-4 border-t border-white/5 pt-3">
                  <p className="text-xs text-[#FFD700] flex items-center gap-1">
                    <span className="text-[#64748b]">{t.improvementAction}:</span>
                    {gap.action}
                  </p>
                </div>
              )}
            </div>
          ))}
        </div>
      </Card>

      {/* ── 4. Policy Templates ── */}
      <Card className="mb-8">
        <h3 className="text-lg font-bold mb-4 flex items-center gap-2">
          <FileText size={18} className="text-[#FFD700]" />
          {t.policyTemplates}
        </h3>
        <div className="space-y-3">
          {data.policy_templates.map((policy) => (
            <div key={policy.id} className="flex items-center gap-4 p-3 rounded-lg border border-[#1e293b] bg-white/[0.02]">
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-sm font-medium text-[#e2e8f0]">{policy.name}</span>
                  <Badge variant={policy.status === "published" ? "green" : policy.status === "draft" ? "yellow" : "default"}>
                    {policy.status === "published" ? t.published : policy.status === "draft" ? t.draft : t.notStarted}
                  </Badge>
                </div>
                <p className="text-xs text-[#64748b]">{policy.description}</p>
              </div>
              <Button variant="secondary" size="sm" onClick={() => downloadPolicy(policy)}>
                <Download size={12} />
                {t.generate}
              </Button>
            </div>
          ))}
        </div>
      </Card>

      {/* ── 5. AI System Registry ── */}
      <Card>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-bold flex items-center gap-2">
            <Bot size={18} className="text-[#FFD700]" />
            {t.aiRegistry}
          </h3>
          {shadowAiCount > 0 && (
            <Badge variant="red">
              <Eye size={10} className="mr-1" />
              {t.shadowAiDetected.replace("{n}", String(shadowAiCount))}
            </Badge>
          )}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#1e293b]">
                <th className="text-left py-3 px-2 text-[#64748b] font-medium">{t.systemName}</th>
                <th className="text-left py-3 px-2 text-[#64748b] font-medium">{t.department}</th>
                <th className="text-left py-3 px-2 text-[#64748b] font-medium">{t.riskLevel}</th>
                <th className="text-left py-3 px-2 text-[#64748b] font-medium">{t.statusCol}</th>
                <th className="text-left py-3 px-2 text-[#64748b] font-medium">{t.shadowAi}</th>
              </tr>
            </thead>
            <tbody>
              {data.ai_systems.map((sys) => (
                <tr key={sys.id} className="border-b border-[#1e293b]/50 hover:bg-white/[0.02]">
                  <td className="py-3 px-2">
                    <div className="flex items-center gap-2">
                      <Bot size={14} className="text-[#64748b]" />
                      <span className="text-[#e2e8f0]">{sys.name}</span>
                    </div>
                  </td>
                  <td className="py-3 px-2 text-[#94a3b8]">{sys.department}</td>
                  <td className="py-3 px-2">
                    <Badge variant={riskVariant(sys.risk_level)}>
                      {sys.risk_level.toUpperCase()}
                    </Badge>
                  </td>
                  <td className="py-3 px-2">
                    <Badge variant={sys.status === "active" ? "green" : sys.status === "review" ? "yellow" : "default"}>
                      {sys.status.charAt(0).toUpperCase() + sys.status.slice(1)}
                    </Badge>
                  </td>
                  <td className="py-3 px-2">
                    {sys.shadow_ai
                      ? <Badge variant="red"><Eye size={10} className="mr-1" />{t.shadowAiYes}</Badge>
                      : <span className="text-xs text-[#475569]">—</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {shadowAiCount > 0 && (
          <p className="text-xs text-red-400 mt-3 border-t border-[#1e293b] pt-3">
            {t.shadowAiWarning.replace("{n}", String(shadowAiCount))}
          </p>
        )}
      </Card>
    </div>
  );
}
