"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useState } from "react";
import {
  Brain,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Activity,
  Zap,
  ArrowRight,
  TrendingUp,
  TrendingDown,
  Minus,
  Bot,
  ShieldAlert,
} from "lucide-react";
import { useLocale } from "@/lib/useLocale";

/* ============================================================
 * Types
 * ============================================================ */

type AiStatus = "healthy" | "degraded" | "down";
type FallbackStatus = "primary" | "fallback" | "degraded";
type PromptRisk = "high" | "medium" | "low";

interface AiSystem {
  id: string;
  name: string;
  model: string;
  status: AiStatus;
  hallucinationRate: number;
  latencyP99: number;
  requestsPerMin: number;
  businessFlows: string[];
  fallbackChain: { label: string; status: FallbackStatus }[];
}

interface PromptScore {
  id: string;
  name: string;
  risk: PromptRisk;
  reason: string;
  score: number;
}

interface HallucinationPoint {
  time: string;
  rate: number;
}

/* ============================================================
 * Demo Data
 * ============================================================ */

const HALLUCINATION_HISTORY: HallucinationPoint[] = [
  { time: "00:00", rate: 1.8 },
  { time: "02:00", rate: 2.1 },
  { time: "04:00", rate: 1.9 },
  { time: "06:00", rate: 2.0 },
  { time: "08:00", rate: 2.8 },
  { time: "10:00", rate: 3.4 },
  { time: "12:00", rate: 2.3 },
  { time: "14:00", rate: 2.1 },
  { time: "16:00", rate: 2.5 },
  { time: "18:00", rate: 2.3 },
  { time: "20:00", rate: 2.2 },
  { time: "22:00", rate: 2.0 },
];

const DEMO_AI_SYSTEMS: AiSystem[] = [
  {
    id: "rec-engine",
    name: "Recommendation Engine",
    model: "GPT-4o",
    status: "healthy",
    hallucinationRate: 1.8,
    latencyP99: 340,
    requestsPerMin: 1240,
    businessFlows: ["Product discovery", "Upsell suggestions", "Email personalization"],
    fallbackChain: [
      { label: "GPT-4o (primary)", status: "primary" },
      { label: "Claude 3.5 Sonnet", status: "primary" },
      { label: "Local model (gte-small)", status: "primary" },
    ],
  },
  {
    id: "support-bot",
    name: "Customer Support Bot",
    model: "Claude 3.5 Sonnet",
    status: "degraded",
    hallucinationRate: 4.2,
    latencyP99: 1820,
    requestsPerMin: 87,
    businessFlows: ["Ticket triage", "FAQ automation", "Escalation routing"],
    fallbackChain: [
      { label: "Claude 3.5 Sonnet (primary)", status: "degraded" },
      { label: "GPT-4o-mini", status: "fallback" },
      { label: "Rule-based fallback", status: "primary" },
    ],
  },
  {
    id: "doc-generator",
    name: "Document Generator",
    model: "GPT-4o-mini",
    status: "healthy",
    hallucinationRate: 0.9,
    latencyP99: 2100,
    requestsPerMin: 23,
    businessFlows: ["Contract drafting", "Report generation", "Code documentation"],
    fallbackChain: [
      { label: "GPT-4o-mini (primary)", status: "primary" },
      { label: "GPT-4o", status: "primary" },
    ],
  },
];

const DEMO_PROMPT_SCORES: PromptScore[] = [
  { id: "p1", name: "support-bot/triage-v3", risk: "high",   reason: "Contains PII in few-shot examples; lacks output format constraints", score: 72 },
  { id: "p2", name: "rec-engine/ranking-v7", risk: "medium", reason: "Temperature=1.0 increases randomness; add max_tokens guard", score: 84 },
  { id: "p3", name: "doc-gen/contract-v2",   risk: "low",    reason: "Well-structured with JSON schema enforcement and retry logic", score: 96 },
  { id: "p4", name: "support-bot/faq-v5",    risk: "medium", reason: "No hallucination detection post-processing; long context window", score: 78 },
];

/* ============================================================
 * Helpers
 * ============================================================ */

function statusVariant(status: string): "green" | "yellow" | "red" | "default" {
  if (status === "healthy" || status === "primary") return "green";
  if (status === "degraded" || status === "fallback") return "yellow";
  if (status === "down") return "red";
  return "default";
}

function riskVariant(risk: PromptRisk): "green" | "yellow" | "red" {
  if (risk === "low") return "green";
  if (risk === "medium") return "yellow";
  return "red";
}

function hallucinationColor(rate: number): string {
  if (rate < 2) return "#10b981";
  if (rate < 4) return "#f59e0b";
  return "#ef4444";
}

function fallbackColor(status: FallbackStatus): string {
  if (status === "primary") return "#10b981";
  if (status === "fallback") return "#f59e0b";
  return "#ef4444";
}

/* Mini SVG chart for hallucination rate history */
function HallucinationChart({ data, width = 200, height = 48 }: { data: HallucinationPoint[]; width?: number; height?: number }) {
  const maxRate = Math.max(...data.map((d) => d.rate), 5);
  const pts = data.map((d, i) => {
    const x = (i / (data.length - 1)) * width;
    const y = height - (d.rate / maxRate) * height;
    return `${x},${y}`;
  });
  const polyline = pts.join(" ");
  const area = `0,${height} ${polyline} ${width},${height}`;

  return (
    <svg width={width} height={height} className="overflow-visible">
      <polygon points={area} fill="rgba(239,68,68,0.08)" />
      <polyline points={polyline} fill="none" stroke="#ef4444" strokeWidth="1.5" strokeLinejoin="round" />
      {/* Threshold line at 3% */}
      <line x1={0} y1={height - (3 / maxRate) * height} x2={width} y2={height - (3 / maxRate) * height}
        stroke="#f59e0b" strokeWidth="1" strokeDasharray="4,3" />
    </svg>
  );
}

/* ============================================================
 * Main Page
 * ============================================================ */

export default function AiReliabilityPage() {
  const locale = useLocale();

  const [expandedSystem, setExpandedSystem] = useState<string | null>("rec-engine");

  const overallHallucinationRate = (
    DEMO_AI_SYSTEMS.reduce((s, ai) => s + ai.hallucinationRate, 0) / DEMO_AI_SYSTEMS.length
  ).toFixed(1);

  const healthyCount  = DEMO_AI_SYSTEMS.filter((ai) => ai.status === "healthy").length;
  const degradedCount = DEMO_AI_SYSTEMS.filter((ai) => ai.status === "degraded").length;
  const highRiskPrompts = DEMO_PROMPT_SCORES.filter((p) => p.risk === "high").length;

  return (
    <div className="max-w-[1200px] mx-auto px-6 py-10">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold mb-1 flex items-center gap-3">
          <Brain size={24} className="text-[#FFD700]" />
          AI Reliability Dashboard
        </h1>
        <p className="text-[#94a3b8] text-sm">
          Monitor LLM/AI system health, hallucination rates, and dependency risks (Layer 3)
        </p>
      </div>

      {/* Top Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        {[
          { label: "AI Systems", value: DEMO_AI_SYSTEMS.length, color: "#e2e8f0" },
          { label: "Healthy", value: healthyCount, color: "#10b981" },
          { label: "Degraded", value: degradedCount, color: "#f59e0b" },
          { label: "Avg Hallucination Rate", value: `${overallHallucinationRate}%`, color: hallucinationColor(parseFloat(overallHallucinationRate)) },
        ].map((stat) => (
          <Card key={stat.label} className="text-center">
            <p className="text-xs text-[#64748b] uppercase tracking-wider mb-1">{stat.label}</p>
            <p className="text-3xl font-extrabold font-mono" style={{ color: stat.color }}>{stat.value}</p>
          </Card>
        ))}
      </div>

      {/* Hallucination Rate Overview */}
      <Card className="mb-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-base font-bold flex items-center gap-2">
            <Activity size={16} className="text-[#FFD700]" />
            Hallucination Rate — Last 24h
          </h3>
          <div className="flex items-center gap-3 text-xs text-[#64748b]">
            <span className="flex items-center gap-1"><span className="w-3 h-0.5 bg-red-500 inline-block" />Actual rate</span>
            <span className="flex items-center gap-1"><span className="w-3 h-0.5 bg-yellow-500 inline-block border-dashed border" />3% threshold</span>
          </div>
        </div>
        <div className="flex items-end gap-6">
          <HallucinationChart data={HALLUCINATION_HISTORY} width={400} height={72} />
          <div className="space-y-2 pb-1">
            <div>
              <p className="text-xs text-[#64748b]">{locale === "ja" ? "現在のレート" : "Current rate"}</p>
              <p className="text-2xl font-extrabold font-mono" style={{ color: hallucinationColor(2.3) }}>2.3%</p>
            </div>
            <div>
              <p className="text-xs text-[#64748b]">{locale === "ja" ? "ピーク (10:00)" : "Peak (10:00)"}</p>
              <p className="text-lg font-bold font-mono text-yellow-400">3.4%</p>
            </div>
            <div className="flex items-center gap-1 text-xs text-emerald-400">
              <TrendingDown size={12} />
              <span>{locale === "ja" ? "↓ 0.5% 昨日比" : "↓ 0.5% vs yesterday"}</span>
            </div>
          </div>
        </div>
      </Card>

      {/* AI Systems */}
      <div className="space-y-4 mb-8">
        <h3 className="text-sm font-semibold text-[#94a3b8] uppercase tracking-wider">AI Systems</h3>
        {DEMO_AI_SYSTEMS.map((ai) => {
          const isExpanded = expandedSystem === ai.id;

          return (
            <Card key={ai.id}>
              <button
                className="w-full text-left"
                onClick={() => setExpandedSystem(isExpanded ? null : ai.id)}
              >
                <div className="flex items-center gap-4 flex-wrap">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1 flex-wrap">
                      <span className="text-base font-bold text-[#e2e8f0]">{ai.name}</span>
                      <Badge variant="default" className="font-mono text-xs">{ai.model}</Badge>
                      <Badge variant={statusVariant(ai.status)}>
                        {ai.status === "healthy" ? "Healthy" : ai.status === "degraded" ? "Degraded" : "Down"}
                      </Badge>
                    </div>
                    <div className="flex flex-wrap gap-4 text-xs text-[#64748b]">
                      <span>Hallucination: <strong style={{ color: hallucinationColor(ai.hallucinationRate) }}>{ai.hallucinationRate}%</strong></span>
                      <span>P99: <strong className="text-[#94a3b8]">{ai.latencyP99}ms</strong></span>
                      <span>RPM: <strong className="text-[#94a3b8]">{ai.requestsPerMin.toLocaleString()}</strong></span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 text-xs text-[#64748b]">
                    <Bot size={13} />
                    {ai.businessFlows.length} flows
                  </div>
                </div>
              </button>

              {isExpanded && (
                <div className="mt-4 pt-4 border-t border-[#1e293b] grid md:grid-cols-2 gap-4">
                  {/* Business Flows */}
                  <div>
                    <h5 className="text-xs font-semibold text-[#64748b] uppercase tracking-wider mb-2 flex items-center gap-1">
                      <Zap size={11} />
                      Business Flows Using This AI
                    </h5>
                    <div className="space-y-1.5">
                      {ai.businessFlows.map((flow) => (
                        <div key={flow} className="flex items-center gap-2 text-sm text-[#94a3b8]">
                          <ArrowRight size={11} className="text-[#FFD700] shrink-0" />
                          {flow}
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Fallback Chain */}
                  <div>
                    <h5 className="text-xs font-semibold text-[#64748b] uppercase tracking-wider mb-2 flex items-center gap-1">
                      <ShieldAlert size={11} />
                      Fallback Chain
                    </h5>
                    <div className="space-y-2">
                      {ai.fallbackChain.map((fb, i) => (
                        <div key={i} className="flex items-center gap-3">
                          <span className="text-xs text-[#475569] w-4 text-right">{i + 1}.</span>
                          <div
                            className="w-2 h-2 rounded-full shrink-0"
                            style={{ backgroundColor: fallbackColor(fb.status) }}
                          />
                          <span className="text-sm text-[#94a3b8] flex-1">{fb.label}</span>
                          <Badge variant={statusVariant(fb.status)} className="text-[10px]">
                            {fb.status}
                          </Badge>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </Card>
          );
        })}
      </div>

      {/* Prompt Risk Scoring */}
      <Card>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-base font-bold flex items-center gap-2">
            <ShieldAlert size={16} className="text-[#FFD700]" />
            Prompt Risk Scoring
          </h3>
          {highRiskPrompts > 0 && (
            <Badge variant="red">{highRiskPrompts} high-risk prompt{highRiskPrompts !== 1 ? "s" : ""}</Badge>
          )}
        </div>
        <div className="space-y-3">
          {DEMO_PROMPT_SCORES.map((p) => (
            <div
              key={p.id}
              className={`p-3 rounded-xl border flex items-center gap-4 ${
                p.risk === "high"
                  ? "bg-red-500/5 border-red-500/15"
                  : p.risk === "medium"
                    ? "bg-yellow-500/5 border-yellow-500/15"
                    : "bg-emerald-500/5 border-emerald-500/15"
              }`}
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-0.5 flex-wrap">
                  <span className="text-sm font-mono font-medium text-[#e2e8f0]">{p.name}</span>
                  <Badge variant={riskVariant(p.risk)}>{p.risk.toUpperCase()} RISK</Badge>
                </div>
                <p className="text-xs text-[#64748b] leading-relaxed">{p.reason}</p>
              </div>
              <div className="text-right shrink-0">
                <p
                  className="text-2xl font-extrabold font-mono"
                  style={{ color: p.score >= 90 ? "#10b981" : p.score >= 75 ? "#f59e0b" : "#ef4444" }}
                >
                  {p.score}
                </p>
                <p className="text-xs text-[#64748b]">safety score</p>
              </div>
            </div>
          ))}
        </div>

        <p className="text-xs text-[#475569] mt-4 border-t border-[#1e293b] pt-3">
          Prompt risk scores are computed by analyzing: PII exposure, output format constraints, temperature settings, context length, and post-processing guardrails.
        </p>
      </Card>
    </div>
  );
}
