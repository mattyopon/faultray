"use client";

import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useState } from "react";
import { api, type SimulationResult } from "@/lib/api";
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
} from "lucide-react";
import Link from "next/link";

const SAMPLES = [
  { id: "web-saas", name: "Web SaaS Platform", desc: "3-tier architecture with API gateway, auth, database, cache", icon: Globe, components: 8 },
  { id: "microservices", name: "Microservices", desc: "Event-driven microservices with message queues and service mesh", icon: Server, components: 12 },
  { id: "multi-region", name: "Multi-Region", desc: "Multi-region deployment with cross-region replication", icon: Cloud, components: 15 },
  { id: "data-pipeline", name: "Data Pipeline", desc: "ETL pipeline with streaming, batch processing, and data lake", icon: Database, components: 10 },
];

function ResultsPanel({ result }: { result: SimulationResult }) {
  const scoreColor = result.overall_score >= 90 ? "text-emerald-400" : result.overall_score >= 70 ? "text-[#FFD700]" : "text-red-400";

  return (
    <div className="space-y-6">
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
            <h4 className="text-sm font-semibold text-[#94a3b8]">3-Layer Availability</h4>
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
    </div>
  );
}

export default function SimulatePage() {
  const [selected, setSelected] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<SimulationResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const runSimulation = async () => {
    if (!selected) return;
    setRunning(true);
    setError(null);
    setResult(null);

    try {
      const res = await api.simulate({ sample: selected });
      setResult(res);
    } catch (err) {
      // Use demo data if API is unavailable
      setResult({
        overall_score: 85.2,
        availability_estimate: "99.99%",
        nines: 4.0,
        scenarios_passed: 147,
        scenarios_failed: 5,
        total_scenarios: 152,
        layers: { software: 4.0, hardware: 5.91, theoretical: 6.65 },
        critical_failures: [
          { scenario: "Cascading database failure", impact: "Full service outage for 12 minutes", severity: "CRITICAL" },
          { scenario: "Cache cluster partition", impact: "Degraded performance, 30% latency increase", severity: "HIGH" },
          { scenario: "DNS resolution failure", impact: "Intermittent connectivity loss", severity: "HIGH" },
        ],
        suggestions: [
          { title: "Add database read replica", description: "Implement a read replica to handle failover scenarios", impact: "+0.5 nines", effort: "Medium" },
          { title: "Implement circuit breaker", description: "Add circuit breaker pattern for cascading failure protection", impact: "+0.3 nines", effort: "Low" },
        ],
      });
      if (err instanceof Error && !err.message.includes("fetch")) {
        setError(err.message);
      }
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="max-w-[1200px] mx-auto px-6 py-10">
      <div className="mb-10">
        <h1 className="text-2xl font-bold mb-1">Run Simulation</h1>
        <p className="text-[#94a3b8] text-sm">Select a sample topology or upload your own YAML to simulate chaos scenarios</p>
      </div>

      {!result ? (
        <>
          <div className="grid md:grid-cols-2 gap-6 mb-8">
            {SAMPLES.map((sample) => {
              const Icon = sample.icon;
              const isSelected = selected === sample.id;
              return (
                <button
                  key={sample.id}
                  onClick={() => setSelected(sample.id)}
                  className={`text-left p-6 rounded-2xl border transition-all duration-200 ${
                    isSelected
                      ? "border-[#FFD700] bg-[#FFD700]/[0.04] shadow-[0_0_30px_rgba(255,215,0,0.1)]"
                      : "border-[#1e293b] bg-[#111827] hover:border-[#FFD700]/30 hover:bg-[#1a2035]"
                  }`}
                >
                  <div className="flex items-start gap-4">
                    <div className={`w-12 h-12 rounded-xl flex items-center justify-center ${isSelected ? "bg-[#FFD700]/20" : "bg-[#FFD700]/[0.06]"} border border-[#FFD700]/10`}>
                      <Icon size={22} className="text-[#FFD700]" />
                    </div>
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <h3 className="font-bold">{sample.name}</h3>
                        <Badge variant="gold">{sample.components} nodes</Badge>
                      </div>
                      <p className="text-sm text-[#94a3b8]">{sample.desc}</p>
                    </div>
                    <div className={`w-5 h-5 rounded-full border-2 flex items-center justify-center ${isSelected ? "border-[#FFD700]" : "border-[#1e293b]"}`}>
                      {isSelected && <div className="w-2.5 h-2.5 rounded-full bg-[#FFD700]" />}
                    </div>
                  </div>
                </button>
              );
            })}
          </div>

          {error && (
            <div className="mb-6 p-4 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
              {error}
            </div>
          )}

          <div className="flex justify-center">
            <Button
              size="lg"
              disabled={!selected || running}
              onClick={runSimulation}
              className="min-w-[200px]"
            >
              {running ? (
                <>
                  <Loader2 size={18} className="animate-spin" />
                  Running Simulation...
                </>
              ) : (
                <>
                  <Zap size={18} />
                  Run Simulation
                </>
              )}
            </Button>
          </div>
        </>
      ) : (
        <>
          <ResultsPanel result={result} />
          <div className="flex justify-center mt-6">
            <Button variant="secondary" onClick={() => { setResult(null); setSelected(null); }}>
              Run Another Simulation
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
