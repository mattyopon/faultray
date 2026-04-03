"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useState } from "react";
import {
  Swords,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Calendar,
  Users,
  Play,
  FileText,
  ChevronDown,
  ChevronRight,
  Clock,
  Shield,
  Zap,
} from "lucide-react";
import { useLocale } from "@/lib/useLocale";

/* ============================================================
 * Types
 * ============================================================ */

type GameDayStatus = "upcoming" | "in_progress" | "completed" | "cancelled";

interface Participant {
  name: string;
  role: "commander" | "observer" | "responder";
}

interface PreCheck {
  label: string;
  passed: boolean;
}

interface GameDay {
  id: string;
  title: string;
  scenario: string;
  description: string;
  scheduledAt: string;
  duration: string;
  status: GameDayStatus;
  participants: Participant[];
  preChecks: PreCheck[];
  objectives: string[];
  postReport?: {
    outcome: string;
    findings: string[];
    mttr: string;
    passed: boolean;
  };
}

/* ============================================================
 * Demo Data
 * ============================================================ */

const SCENARIOS = [
  "Database Failover",
  "Network Partition",
  "LLM Timeout / Hallucination Spike",
  "Cache Eviction Storm",
  "CPU Starvation",
  "Data Center Outage",
  "DDoS Attack Simulation",
  "Key Rotation (Zero-Downtime)",
  "Third-Party API Outage",
  "Runaway Query (Lock Contention)",
];

const DEMO_GAMEDAYS: GameDay[] = [
  {
    id: "gd-2026-04-10",
    title: "Q2 GameDay #1 — DB Failover",
    scenario: "Database Failover",
    description: "Simulate a sudden PostgreSQL primary failure. Validate automatic failover to replica, RTO measurement, and runbook execution under time pressure.",
    scheduledAt: "2026-04-10T10:00:00Z",
    duration: "3 hours",
    status: "upcoming",
    participants: [
      { name: "Alice Chen",   role: "commander" },
      { name: "Bob Tanaka",   role: "responder" },
      { name: "Carol Smith",  role: "responder" },
      { name: "David Lee",    role: "observer" },
      { name: "Emma Wilson",  role: "observer" },
    ],
    preChecks: [
      { label: "Staging environment is isolated from production", passed: true },
      { label: "All responders have been briefed on scenario scope", passed: true },
      { label: "Monitoring dashboards are accessible", passed: true },
      { label: "Rollback procedure documented and accessible", passed: true },
      { label: "On-call escalation path confirmed", passed: false },
      { label: "Customer communication template prepared", passed: true },
    ],
    objectives: [
      "Measure RTO: primary→replica failover in ≤90 seconds",
      "Validate that API retries handle connection errors gracefully",
      "Verify that no data loss occurs (RPO = 0)",
      "Confirm alerting fires within 30s of failure injection",
      "Practice the DB-failover runbook from start to finish",
    ],
  },
  {
    id: "gd-2026-03-15",
    title: "Q1 GameDay #3 — LLM Timeout",
    scenario: "LLM Timeout / Hallucination Spike",
    description: "Simulated OpenAI API timeout + 40% hallucination rate spike. Tested fallback to local model and circuit breaker activation.",
    scheduledAt: "2026-03-15T10:00:00Z",
    duration: "2.5 hours",
    status: "completed",
    participants: [
      { name: "Frank Müller",  role: "commander" },
      { name: "Grace Park",    role: "responder" },
      { name: "Henry Okafor",  role: "responder" },
      { name: "Iris Nakamura", role: "observer" },
    ],
    preChecks: [
      { label: "Staging environment isolated", passed: true },
      { label: "Responders briefed", passed: true },
      { label: "Monitoring accessible", passed: true },
      { label: "Rollback documented", passed: true },
      { label: "Escalation path confirmed", passed: true },
      { label: "Communication template prepared", passed: true },
    ],
    objectives: [
      "Activate circuit breaker within 10s of LLM timeout",
      "Fall back to local embedding model with no user-facing error",
      "Measure P99 latency degradation during fallback mode",
      "Verify hallucination rate monitoring alerts fire",
    ],
    postReport: {
      outcome: "Partial success. Circuit breaker activated in 8s (✓). Fallback model latency was 3.2× baseline (acceptable). Hallucination alert fired at 4% threshold (3% gap from target).",
      findings: [
        "Fallback model does not support streaming — UX regression under fallback",
        "Alert threshold for hallucination rate was too aggressive (40% false-positive rate)",
        "Runbook Step 4 was ambiguous; rewritten after GameDay",
      ],
      mttr: "14 minutes",
      passed: true,
    },
  },
];

/* ============================================================
 * Helpers
 * ============================================================ */

function statusVariant(status: GameDayStatus): "green" | "yellow" | "red" | "default" {
  if (status === "completed") return "green";
  if (status === "upcoming" || status === "in_progress") return "yellow";
  if (status === "cancelled") return "red";
  return "default";
}

function statusLabel(status: GameDayStatus): string {
  if (status === "completed") return "Completed";
  if (status === "upcoming") return "Upcoming";
  if (status === "in_progress") return "In Progress";
  return "Cancelled";
}

function roleColor(role: Participant["role"]): string {
  if (role === "commander") return "#FFD700";
  if (role === "responder") return "#10b981";
  return "#64748b";
}

/* ============================================================
 * Main Page
 * ============================================================ */

export default function GameDayPage() {
  const locale = useLocale();

  const [selectedScenario, setSelectedScenario] = useState(SCENARIOS[0]);
  const [expandedGameDay, setExpandedGameDay] = useState<string | null>("gd-2026-04-10");
  const [showNewForm, setShowNewForm] = useState(false);

  const upcoming = DEMO_GAMEDAYS.filter((g) => g.status === "upcoming");
  const completed = DEMO_GAMEDAYS.filter((g) => g.status === "completed");

  return (
    <div className="w-full px-6 py-10">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold mb-1 flex items-center gap-3">
          <Swords size={24} className="text-[var(--gold)]" />
          GameDay Planner
        </h1>
        <p className="text-[var(--text-secondary)] text-sm">
          Plan and run chaos engineering exercises to build resilience muscle memory (Layer 2)
        </p>
      </div>

      {/* DEMO-05: Sample data notice */}
      <div className="mb-6 px-4 py-2.5 rounded-lg border border-amber-500/20 bg-amber-500/[0.06] flex items-center gap-2 text-xs text-amber-400">
        <span className="shrink-0">📋</span>
        <span>{locale === "ja" ? "サンプルデータを表示中。実際のゲームデー演習を計画すると実データが表示されます。" : "Showing sample data. Your actual GameDay exercises will appear here."}</span>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        {[
          { label: "Upcoming", value: upcoming.length, color: "#f59e0b" },
          { label: "Completed", value: completed.length, color: "#10b981" },
          { label: "Scenarios Library", value: SCENARIOS.length, color: "#e2e8f0" },
          { label: "Avg MTTR (last 3)", value: "18 min", color: "#3b82f6" },
        ].map((stat) => (
          <Card key={stat.label} className="text-center">
            <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider mb-1">{stat.label}</p>
            <p className="text-2xl font-extrabold font-mono" style={{ color: stat.color }}>{stat.value}</p>
          </Card>
        ))}
      </div>

      <div className="grid lg:grid-cols-3 gap-6">
        {/* Main GameDay List */}
        <div className="lg:col-span-2 space-y-4">
          {/* New GameDay Button */}
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-[var(--text-secondary)] uppercase tracking-wider">GameDay Schedule</h3>
            <Button size="sm" onClick={() => setShowNewForm(!showNewForm)}>
              <Play size={13} />
              Schedule GameDay
            </Button>
          </div>

          {/* New GameDay Quick Form */}
          {showNewForm && (
            <Card className="border-[var(--gold)]/20 bg-[var(--gold)]/[0.02]">
              <h4 className="text-sm font-semibold text-[var(--gold)] mb-4">New GameDay</h4>
              <div className="grid sm:grid-cols-2 gap-4">
                <div>
                  <label className="text-xs text-[var(--text-muted)] mb-1 block">Scenario</label>
                  <select
                    className="w-full bg-[var(--bg-tertiary)] border border-[var(--border-color)] rounded-lg px-3 py-2 text-sm text-[var(--text-secondary)] focus:outline-none focus:border-[var(--gold)]/30"
                    value={selectedScenario}
                    onChange={(e) => setSelectedScenario(e.target.value)}
                    aria-label={locale === "ja" ? "シナリオ選択" : "Select scenario"}
                  >
                    {SCENARIOS.map((s) => <option key={s} value={s}>{s}</option>)}
                  </select>
                </div>
                <div>
                  <label className="text-xs text-[var(--text-muted)] mb-1 block">Date</label>
                  <input
                    type="date"
                    defaultValue="2026-04-24"
                    className="w-full bg-[var(--bg-tertiary)] border border-[var(--border-color)] rounded-lg px-3 py-2 text-sm text-[var(--text-secondary)] focus:outline-none focus:border-[var(--gold)]/30"
                  />
                </div>
              </div>
              <div className="mt-3 flex gap-2">
                <Button size="sm">Create GameDay</Button>
                <Button variant="secondary" size="sm" onClick={() => setShowNewForm(false)}>Cancel</Button>
              </div>
            </Card>
          )}

          {/* GameDay Cards */}
          {DEMO_GAMEDAYS.map((gd) => {
            const isExpanded = expandedGameDay === gd.id;
            const preChecksPassed = gd.preChecks.filter((c) => c.passed).length;
            const isSafeToRun = preChecksPassed === gd.preChecks.length;

            return (
              <Card key={gd.id}>
                <button
                  className="w-full text-left"
                  onClick={() => setExpandedGameDay(isExpanded ? null : gd.id)}
                >
                  <div className="flex items-start gap-3">
                    {isExpanded
                      ? <ChevronDown size={16} className="text-[var(--text-muted)] shrink-0 mt-0.5" />
                      : <ChevronRight size={16} className="text-[var(--text-muted)] shrink-0 mt-0.5" />}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap mb-1">
                        <span className="text-base font-bold text-[#e2e8f0]">{gd.title}</span>
                        <Badge variant={statusVariant(gd.status)}>{statusLabel(gd.status)}</Badge>
                      </div>
                      <div className="flex items-center gap-4 text-xs text-[var(--text-muted)]">
                        <span className="flex items-center gap-1"><Calendar size={11} />{new Date(gd.scheduledAt).toLocaleDateString()}</span>
                        <span className="flex items-center gap-1"><Clock size={11} />{gd.duration}</span>
                        <span className="flex items-center gap-1"><Users size={11} />{gd.participants.length} participants</span>
                      </div>
                    </div>
                  </div>
                </button>

                {isExpanded && (
                  <div className="mt-4 space-y-4">
                    <p className="text-sm text-[var(--text-secondary)] leading-relaxed">{gd.description}</p>

                    {/* Pre-Check */}
                    <div>
                      <div className="flex items-center justify-between mb-2">
                        <h5 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider flex items-center gap-1">
                          <Shield size={12} />
                          Pre-Flight Safety Checks
                        </h5>
                        <span className={`text-xs font-bold ${isSafeToRun ? "text-emerald-400" : "text-yellow-400"}`}>
                          {preChecksPassed}/{gd.preChecks.length} passed
                          {isSafeToRun ? " ✓ Safe to run" : " — resolve before running"}
                        </span>
                      </div>
                      <div className="space-y-1.5">
                        {gd.preChecks.map((check, i) => (
                          <div key={i} className="flex items-center gap-2 text-sm">
                            {check.passed
                              ? <CheckCircle2 size={13} className="text-emerald-400 shrink-0" />
                              : <XCircle size={13} className="text-red-400 shrink-0" />}
                            <span className={check.passed ? "text-[var(--text-secondary)]" : "text-red-300"}>{check.label}</span>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Objectives */}
                    <div>
                      <h5 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-2 flex items-center gap-1">
                        <Zap size={12} />
                        Objectives
                      </h5>
                      <div className="space-y-1.5">
                        {gd.objectives.map((obj, i) => (
                          <div key={i} className="flex items-start gap-2 text-sm">
                            <span className="text-[var(--gold)] font-mono shrink-0">{i + 1}.</span>
                            <span className="text-[var(--text-secondary)]">{obj}</span>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Participants */}
                    <div>
                      <h5 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-2 flex items-center gap-1">
                        <Users size={12} />
                        Team
                      </h5>
                      <div className="flex flex-wrap gap-2">
                        {gd.participants.map((p) => (
                          <div key={p.name} className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-white/5 border border-[var(--border-color)]">
                            <span className="w-2 h-2 rounded-full" style={{ backgroundColor: roleColor(p.role) }} />
                            <span className="text-sm text-[#e2e8f0]">{p.name}</span>
                            <span className="text-xs capitalize" style={{ color: roleColor(p.role) }}>{p.role}</span>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Post-Report */}
                    {gd.postReport && (
                      <div className={`p-4 rounded-xl border ${gd.postReport.passed ? "border-emerald-500/20 bg-emerald-500/5" : "border-red-500/20 bg-red-500/5"}`}>
                        <h5 className="text-xs font-semibold uppercase tracking-wider mb-2 flex items-center gap-1 text-[var(--text-muted)]">
                          <FileText size={12} />
                          Post-GameDay Report
                          <span className="ml-1 text-xs font-medium">· MTTR: <strong className="text-[#e2e8f0]">{gd.postReport.mttr}</strong></span>
                        </h5>
                        <p className="text-sm text-[var(--text-secondary)] leading-relaxed mb-3">{gd.postReport.outcome}</p>
                        <div className="space-y-1.5">
                          {gd.postReport.findings.map((f, i) => (
                            <div key={i} className="flex items-start gap-2 text-sm">
                              <AlertTriangle size={12} className="text-yellow-400 shrink-0 mt-0.5" />
                              <span className="text-[var(--text-secondary)]">{f}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Actions */}
                    {gd.status === "upcoming" && (
                      <div className="flex gap-2">
                        <Button size="sm" disabled={!isSafeToRun}>
                          <Play size={13} />
                          {isSafeToRun ? "Start GameDay" : "Fix pre-checks first"}
                        </Button>
                        <Button variant="secondary" size="sm">
                          <FileText size={13} />
                          Edit Plan
                        </Button>
                      </div>
                    )}
                  </div>
                )}
              </Card>
            );
          })}
        </div>

        {/* Scenario Library Sidebar */}
        <div>
          <Card>
            <h3 className="text-sm font-semibold text-[var(--text-secondary)] uppercase tracking-wider mb-4 flex items-center gap-2">
              <Zap size={14} />
              Scenario Library
            </h3>
            <div className="space-y-1.5">
              {SCENARIOS.map((scenario) => (
                <button
                  key={scenario}
                  className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors ${
                    selectedScenario === scenario
                      ? "bg-[var(--gold)]/10 text-[var(--gold)] border border-[var(--gold)]/20"
                      : "text-[var(--text-secondary)] hover:bg-white/5 hover:text-white"
                  }`}
                  onClick={() => setSelectedScenario(scenario)}
                >
                  {scenario}
                </button>
              ))}
            </div>

            <div className="mt-4 pt-4 border-t border-[var(--border-color)]">
              <p className="text-xs text-[var(--text-muted)] leading-relaxed">
                <strong className="text-[var(--text-secondary)]">Best practice:</strong> Run a GameDay at least once per quarter. Focus on scenarios that have caused real incidents.
              </p>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
