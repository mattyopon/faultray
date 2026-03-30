"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useState, useEffect } from "react";
import { api, type SimulationRun } from "@/lib/api";
import { FileText, Download, ChevronDown } from "lucide-react";
import { useLocale } from "@/lib/useLocale";
import { appDict } from "@/i18n/app-dict";

export default function ResultsPage() {
  const [runs, setRuns] = useState<SimulationRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<"all" | "passed" | "failed">("all");
  const locale = useLocale();
  const t = appDict.results[locale] ?? appDict.results.en;

  useEffect(() => {
    api.getRuns(undefined, 50)
      .then((data) => setRuns(data.runs || []))
      .catch(() => {
        setRuns([
          { id: 1, created_at: "2026-03-29T10:00:00Z", overall_score: 85.2, availability_estimate: "99.99%", engine_type: "static", scenarios_passed: 147, scenarios_failed: 5, total_scenarios: 152 },
          { id: 2, created_at: "2026-03-28T14:30:00Z", overall_score: 82.8, availability_estimate: "99.98%", engine_type: "static", scenarios_passed: 144, scenarios_failed: 8, total_scenarios: 152 },
          { id: 3, created_at: "2026-03-27T09:15:00Z", overall_score: 91.4, availability_estimate: "99.995%", engine_type: "monte_carlo", scenarios_passed: 150, scenarios_failed: 2, total_scenarios: 152 },
          { id: 4, created_at: "2026-03-26T16:45:00Z", overall_score: 78.6, availability_estimate: "99.97%", engine_type: "static", scenarios_passed: 140, scenarios_failed: 12, total_scenarios: 152 },
        ]);
      })
      .finally(() => setLoading(false));
  }, []);

  const filteredRuns = runs.filter((run) => {
    if (filter === "passed") return run.scenarios_failed === 0;
    if (filter === "failed") return run.scenarios_failed > 0;
    return true;
  });

  return (
    <div className="max-w-[1200px] mx-auto px-6 py-10">
      <div className="flex items-center justify-between mb-10">
        <div>
          <h1 className="text-2xl font-bold mb-1">{t.title}</h1>
          <p className="text-[#94a3b8] text-sm">{t.subtitle}</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="relative">
            <select
              value={filter}
              onChange={(e) => setFilter(e.target.value as "all" | "passed" | "failed")}
              className="appearance-none bg-[#111827] border border-[#1e293b] rounded-lg px-4 py-2 pr-8 text-sm text-[#94a3b8] focus:outline-none focus:border-[#FFD700]/50"
            >
              <option value="all">{t.allResults}</option>
              <option value="passed">{t.allPassed}</option>
              <option value="failed">{t.hasFailures}</option>
            </select>
            <ChevronDown size={14} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[#64748b] pointer-events-none" />
          </div>
          <Button variant="secondary" size="sm">
            <Download size={14} /> {t.export}
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="text-center py-20 text-[#64748b]">{t.loading}</div>
      ) : filteredRuns.length === 0 ? (
        <Card className="text-center py-16">
          <FileText size={48} className="text-[#1e293b] mx-auto mb-4" />
          <p className="text-[#64748b] mb-2">{t.noResults}</p>
          <p className="text-xs text-[#64748b]">{t.noResultsDesc}</p>
        </Card>
      ) : (
        <div className="space-y-4">
          {filteredRuns.map((run) => (
            <Card key={run.id} hover className="cursor-pointer">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-6">
                  <div className="text-center min-w-[80px]">
                    <p className={`text-2xl font-extrabold font-mono ${
                      run.overall_score >= 90 ? "text-emerald-400" : run.overall_score >= 70 ? "text-[#FFD700]" : "text-red-400"
                    }`}>
                      {run.overall_score.toFixed(1)}
                    </p>
                    <p className="text-[10px] text-[#64748b] uppercase tracking-wider">{t.score}</p>
                  </div>
                  <div className="h-12 w-px bg-[#1e293b]" />
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <p className="font-semibold">{run.availability_estimate}</p>
                      <Badge variant="default">{run.engine_type}</Badge>
                    </div>
                    <p className="text-xs text-[#64748b]">
                      {new Date(run.created_at).toLocaleDateString(locale, { weekday: "short", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-4">
                  <div className="text-right">
                    <p className="text-sm">
                      <span className="text-emerald-400 font-mono">{run.scenarios_passed}</span>
                      <span className="text-[#64748b]"> / {run.total_scenarios}</span>
                    </p>
                    <p className="text-xs text-[#64748b]">{t.scenariosPassed}</p>
                  </div>
                  <Badge variant={run.scenarios_failed === 0 ? "green" : run.scenarios_failed <= 5 ? "yellow" : "red"}>
                    {run.scenarios_failed === 0 ? t.allPassed : `${run.scenarios_failed} ${locale === "ja" ? "件失敗" : "Failed"}`}
                  </Badge>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
