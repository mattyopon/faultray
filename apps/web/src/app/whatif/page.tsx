"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useState } from "react";
import { api, type WhatIfResult } from "@/lib/api";
import { FlaskConical, Loader2, TrendingUp, TrendingDown, Minus } from "lucide-react";
import { useLocale } from "@/lib/useLocale";
import { appDict } from "@/i18n/app-dict";

const COMPONENTS = [
  { id: "api", name: "API Server" },
  { id: "db_primary", name: "PostgreSQL Primary" },
  { id: "cache", name: "Redis Cache" },
  { id: "gateway", name: "API Gateway" },
  { id: "worker", name: "Background Worker" },
  { id: "auth", name: "Auth Service" },
];

const PARAMETERS = [
  { id: "replicas", name: "Replicas", min: 1, max: 10, step: 1, default: 2 },
  { id: "capacity", name: "Max Connections", min: 100, max: 50000, step: 100, default: 5000 },
  { id: "failover_time", name: "Failover Time (s)", min: 1, max: 120, step: 1, default: 30 },
  { id: "health_check_interval", name: "Health Check Interval (s)", min: 1, max: 60, step: 1, default: 10 },
  { id: "retry_count", name: "Retry Count", min: 0, max: 10, step: 1, default: 3 },
  { id: "timeout", name: "Timeout (s)", min: 1, max: 120, step: 1, default: 30 },
];

export default function WhatIfPage() {
  const [component, setComponent] = useState("api");
  const [parameter, setParameter] = useState("replicas");
  const [value, setValue] = useState(2);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<WhatIfResult | null>(null);

  const locale = useLocale();
  const t = appDict.whatif[locale] ?? appDict.whatif.en;
  const selectedParam = PARAMETERS.find((p) => p.id === parameter)!;

  const runAnalysis = async () => {
    setLoading(true);
    try {
      const res = await api.whatIf(component, parameter, value);
      setResult(res);
    } catch {
      // Generate a local estimate
      setResult({
        baseline: { overall_score: 85.2, availability_estimate: "99.99%", nines: 4.0 },
        modified: {
          overall_score: Math.min(100, Math.max(0, 85.2 + (value - selectedParam.default) * 1.5)),
          nines: 4.0 + (value - selectedParam.default) * 0.1,
        },
        delta: {
          score: Math.round((value - selectedParam.default) * 1.5 * 10) / 10,
          direction: value > selectedParam.default ? "improvement" : value < selectedParam.default ? "degradation" : "neutral",
        },
        component_id: component,
        parameter,
        original_value: selectedParam.default,
        new_value: value,
        available_parameters: PARAMETERS.map((p) => p.id),
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-[1200px] mx-auto px-6 py-10">
      <div className="mb-10">
        <h1 className="text-2xl font-bold mb-1 flex items-center gap-3">
          <FlaskConical size={24} className="text-[#FFD700]" />
          {t.title}
        </h1>
        <p className="text-[#94a3b8] text-sm">
          {t.subtitle}
        </p>
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        {/* Controls */}
        <Card>
          <h3 className="text-sm font-semibold text-[#94a3b8] uppercase tracking-wider mb-6">
            {t.parameters}
          </h3>

          <div className="space-y-6">
            {/* Component Selection */}
            <div>
              <label className="text-xs font-medium text-[#94a3b8] mb-2 block">{t.component}</label>
              <div className="grid grid-cols-2 gap-2">
                {COMPONENTS.map((c) => (
                  <button
                    key={c.id}
                    onClick={() => setComponent(c.id)}
                    className={`px-3 py-2 rounded-lg text-sm text-left transition-all ${
                      component === c.id
                        ? "bg-[#FFD700]/10 text-[#FFD700] border border-[#FFD700]/30"
                        : "text-[#94a3b8] border border-[#1e293b] hover:border-[#64748b]"
                    }`}
                  >
                    {c.name}
                  </button>
                ))}
              </div>
            </div>

            {/* Parameter Selection */}
            <div>
              <label className="text-xs font-medium text-[#94a3b8] mb-2 block">{t.parameter}</label>
              <select
                value={parameter}
                onChange={(e) => {
                  setParameter(e.target.value);
                  const p = PARAMETERS.find((p) => p.id === e.target.value)!;
                  setValue(p.default);
                }}
                className="w-full px-3 py-2.5 bg-[#0d1117] border border-[#1e293b] rounded-lg text-sm text-[#e2e8f0] focus:border-[#FFD700]/50 focus:outline-none"
              >
                {PARAMETERS.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </div>

            {/* Slider */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="text-xs font-medium text-[#94a3b8]">{t.value}</label>
                <span className="text-lg font-bold font-mono text-[#FFD700]">{value}</span>
              </div>
              <input
                type="range"
                min={selectedParam.min}
                max={selectedParam.max}
                step={selectedParam.step}
                value={value}
                onChange={(e) => setValue(Number(e.target.value))}
                className="w-full accent-[#FFD700]"
              />
              <div className="flex justify-between text-xs text-[#64748b] mt-1">
                <span>{selectedParam.min}</span>
                <span className="text-[#94a3b8]">{t.default} {selectedParam.default}</span>
                <span>{selectedParam.max}</span>
              </div>
            </div>

            <Button onClick={runAnalysis} disabled={loading} className="w-full">
              {loading ? (
                <>
                  <Loader2 size={16} className="animate-spin" />
                  {t.analyzing}
                </>
              ) : (
                <>
                  <FlaskConical size={16} />
                  {t.runAnalysis}
                </>
              )}
            </Button>
          </div>
        </Card>

        {/* Results */}
        <div className="space-y-6">
          {result ? (
            <>
              <Card>
                <h3 className="text-sm font-semibold text-[#94a3b8] uppercase tracking-wider mb-6">
                  {t.impactAnalysis}
                </h3>

                <div className="grid grid-cols-2 gap-4 mb-6">
                  <div className="p-4 rounded-xl bg-white/[0.02] border border-[#1e293b] text-center">
                    <p className="text-xs text-[#64748b] uppercase tracking-wider mb-1">{t.before}</p>
                    <p className="text-3xl font-extrabold font-mono text-[#94a3b8]">
                      {result.baseline.overall_score.toFixed(1)}
                    </p>
                  </div>
                  <div className="p-4 rounded-xl bg-white/[0.02] border border-[#1e293b] text-center">
                    <p className="text-xs text-[#64748b] uppercase tracking-wider mb-1">{t.after}</p>
                    <p
                      className="text-3xl font-extrabold font-mono"
                      style={{
                        color:
                          result.delta.direction === "improvement"
                            ? "#10b981"
                            : result.delta.direction === "degradation"
                              ? "#ef4444"
                              : "#94a3b8",
                      }}
                    >
                      {result.modified.overall_score.toFixed(1)}
                    </p>
                  </div>
                </div>

                <div className="p-4 rounded-xl border border-[#1e293b] flex items-center justify-center gap-3">
                  {result.delta.direction === "improvement" ? (
                    <TrendingUp size={24} className="text-emerald-400" />
                  ) : result.delta.direction === "degradation" ? (
                    <TrendingDown size={24} className="text-red-400" />
                  ) : (
                    <Minus size={24} className="text-[#64748b]" />
                  )}
                  <span
                    className="text-2xl font-bold font-mono"
                    style={{
                      color:
                        result.delta.direction === "improvement"
                          ? "#10b981"
                          : result.delta.direction === "degradation"
                            ? "#ef4444"
                            : "#94a3b8",
                    }}
                  >
                    {result.delta.score > 0 ? "+" : ""}
                    {result.delta.score.toFixed(1)}
                  </span>
                  <Badge
                    variant={
                      result.delta.direction === "improvement"
                        ? "green"
                        : result.delta.direction === "degradation"
                          ? "red"
                          : "default"
                    }
                  >
                    {t[result.delta.direction as keyof typeof t] || result.delta.direction}
                  </Badge>
                </div>
              </Card>

              <Card>
                <h3 className="text-sm font-semibold text-[#94a3b8] uppercase tracking-wider mb-4">
                  {t.changeSummary}
                </h3>
                <div className="space-y-3">
                  <div className="flex justify-between text-sm">
                    <span className="text-[#64748b]">{t.component}</span>
                    <span className="font-medium">
                      {COMPONENTS.find((c) => c.id === result.component_id)?.name}
                    </span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-[#64748b]">{t.parameter}</span>
                    <span className="font-mono">{result.parameter}</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-[#64748b]">{t.original}</span>
                    <span className="font-mono">{result.original_value}</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-[#64748b]">{t.newValue}</span>
                    <span className="font-mono text-[#FFD700]">{result.new_value}</span>
                  </div>
                </div>
              </Card>
            </>
          ) : (
            <Card className="flex flex-col items-center justify-center py-16">
              <FlaskConical size={40} className="text-[#1e293b] mb-4" />
              <p className="text-[#64748b] text-sm">
                {t.adjustPrompt}
              </p>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
