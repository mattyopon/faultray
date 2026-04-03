"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useState } from "react";
import { api, type BenchmarkData } from "@/lib/api";
import { Trophy, Loader2 } from "lucide-react";
import { useLocale } from "@/lib/useLocale";
import { appDict } from "@/i18n/app-dict";

const INDUSTRIES = [
  { id: "fintech", name: "FinTech", emoji: "bank" },
  { id: "healthcare", name: "Healthcare", emoji: "hospital" },
  { id: "ecommerce", name: "E-Commerce", emoji: "cart" },
  { id: "saas", name: "SaaS", emoji: "cloud" },
];

const DEMO_DATA: BenchmarkData = {
  industry: "SaaS",
  industry_id: "saas",
  your_score: 85.2,
  industry_average: 80.0,
  industry_top_10: 94.0,
  industry_bottom_10: 58.0,
  percentile: 70,
  categories: [
    { name: "Availability", your_score: 88, industry_avg: 85, top_10: 99 },
    { name: "Redundancy", your_score: 82, industry_avg: 80, top_10: 95 },
    { name: "Failover Speed", your_score: 78, industry_avg: 75, top_10: 93 },
    { name: "Data Protection", your_score: 90, industry_avg: 82, top_10: 96 },
    { name: "Monitoring", your_score: 85, industry_avg: 78, top_10: 95 },
    { name: "Compliance", your_score: 72, industry_avg: 70, top_10: 92 },
  ],
  regulatory_requirements: ["SOC2", "ISO27001", "GDPR"],
  typical_sla: "99.9%",
};

export default function BenchmarkPage() {
  const [selectedIndustry, setSelectedIndustry] = useState<string | null>(null);
  const [data, setData] = useState<BenchmarkData>(DEMO_DATA);
  const [loading, setLoading] = useState(false);
  const locale = useLocale();
  const t = appDict.benchmark[locale] ?? appDict.benchmark.en;

  const loadBenchmark = async (industry: string) => {
    setSelectedIndustry(industry);
    setLoading(true);
    try {
      const result = await api.getBenchmark(industry);
      setData(result);
    } catch {
      setData({ ...DEMO_DATA, industry_id: industry, industry: INDUSTRIES.find((i) => i.id === industry)?.name || industry });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="w-full px-6 py-10">
      <div className="mb-10">
        <h1 className="text-2xl font-bold mb-1 flex items-center gap-3">
          <Trophy size={24} className="text-[var(--gold)]" />
          {t.title}
        </h1>
        <p className="text-[var(--text-secondary)] text-sm">
          {t.subtitle}
        </p>
      </div>

      {/* Industry Selection */}
      <div className="grid md:grid-cols-4 gap-4 mb-8">
        {INDUSTRIES.map((ind) => (
          <button
            key={ind.id}
            onClick={() => loadBenchmark(ind.id)}
            className={`p-4 rounded-xl border text-center transition-all ${
              selectedIndustry === ind.id
                ? "border-[var(--gold)] bg-[var(--gold)]/[0.04]"
                : "border-[var(--border-color)] bg-[var(--bg-card)] hover:border-[var(--gold)]/30"
            }`}
          >
            <p className="font-bold text-lg">{ind.name}</p>
          </button>
        ))}
      </div>

      {loading ? (
        <Card className="flex items-center justify-center py-20">
          <Loader2 size={24} className="animate-spin text-[var(--gold)]" />
        </Card>
      ) : selectedIndustry ? (
        <div className="space-y-6">
          {/* Score Comparison */}
          <div className="grid md:grid-cols-4 gap-6">
            <Card className="text-center">
              <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider mb-2">{t.yourScore}</p>
              <p className="text-4xl font-extrabold font-mono text-[var(--gold)]">{data.your_score}</p>
            </Card>
            <Card className="text-center">
              <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider mb-2">{t.industryAvg}</p>
              <p className="text-4xl font-extrabold font-mono text-[var(--text-secondary)]">{data.industry_average}</p>
            </Card>
            <Card className="text-center">
              <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider mb-2">{t.top10}</p>
              <p className="text-4xl font-extrabold font-mono text-emerald-400">{data.industry_top_10}</p>
            </Card>
            <Card className="text-center">
              <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider mb-2">{t.percentile}</p>
              <p className="text-4xl font-extrabold font-mono text-blue-400">{data.percentile}th</p>
            </Card>
          </div>

          {/* Position Visualization */}
          <Card>
            <h3 className="text-lg font-bold mb-4">{data.industry}{t.yourPosition}</h3>
            <div className="relative h-16 bg-white/[0.03] rounded-xl border border-[var(--border-color)] overflow-hidden">
              {/* Range bar */}
              <div
                className="absolute top-0 bottom-0 bg-gradient-to-r from-red-500/20 via-yellow-500/20 to-emerald-500/20"
                style={{ left: `${(data.industry_bottom_10 / 100) * 100}%`, right: `${100 - (data.industry_top_10 / 100) * 100}%` }}
              />
              {/* Industry average marker */}
              <div
                className="absolute top-0 bottom-0 w-0.5 bg-[#64748b]"
                style={{ left: `${data.industry_average}%` }}
              />
              <div
                className="absolute top-1 text-xs text-[var(--text-muted)]"
                style={{ left: `${data.industry_average}%`, transform: "translateX(-50%)" }}
              >
                Avg
              </div>
              {/* Your position */}
              <div
                className="absolute top-1/2 -translate-y-1/2 w-4 h-4 rounded-full bg-[var(--gold)] border-2 border-[var(--gold)] shadow-[0_0_10px_rgba(255,215,0,0.5)]"
                style={{ left: `${data.your_score}%`, transform: "translateX(-50%) translateY(-50%)" }}
              />
              <div
                className="absolute bottom-1 text-xs font-bold text-[var(--gold)]"
                style={{ left: `${data.your_score}%`, transform: "translateX(-50%)" }}
              >
                You
              </div>
            </div>
            <div className="flex justify-between text-xs text-[var(--text-muted)] mt-2">
              <span>0</span>
              <span>Bottom 10%: {data.industry_bottom_10}</span>
              <span>Top 10%: {data.industry_top_10}</span>
              <span>100</span>
            </div>
          </Card>

          {/* Category Comparison */}
          <Card>
            <h3 className="text-lg font-bold mb-6">{t.categoryBreakdown}</h3>
            <div className="space-y-4">
              {data.categories.map((cat) => (
                <div key={cat.name} className="space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium">{cat.name}</span>
                    <div className="flex items-center gap-3 text-xs font-mono">
                      <span className="text-[var(--gold)]">{cat.your_score}</span>
                      <span className="text-[var(--text-muted)]">{cat.industry_avg}</span>
                      <span className="text-emerald-400">{cat.top_10}</span>
                    </div>
                  </div>
                  <div className="relative h-3 bg-white/5 rounded-full overflow-hidden">
                    {/* Industry avg */}
                    <div
                      className="absolute top-0 bottom-0 bg-[#64748b]/30 rounded-full"
                      style={{ width: `${cat.industry_avg}%` }}
                    />
                    {/* Your score */}
                    <div
                      className="absolute top-0 bottom-0 rounded-full"
                      style={{
                        width: `${cat.your_score}%`,
                        backgroundColor: cat.your_score >= cat.industry_avg ? "#10b981" : "#f59e0b",
                      }}
                    />
                    {/* Top 10 marker */}
                    <div
                      className="absolute top-0 bottom-0 w-0.5 bg-emerald-400"
                      style={{ left: `${cat.top_10}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
            <div className="flex items-center gap-6 mt-4 pt-4 border-t border-[var(--border-color)]">
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full bg-[var(--gold)]" />
                <span className="text-xs text-[var(--text-muted)]">{t.yourScoreLabel}</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full bg-[#64748b]/30" />
                <span className="text-xs text-[var(--text-muted)]">{t.industryAvgLabel}</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-3 h-1 bg-emerald-400" />
                <span className="text-xs text-[var(--text-muted)]">{t.top10Label}</span>
              </div>
            </div>
          </Card>

          {/* Regulatory Requirements */}
          <Card>
            <h3 className="text-lg font-bold mb-4">{t.regulatoryRequirements}</h3>
            <div className="flex flex-wrap gap-2 mb-3">
              {data.regulatory_requirements.map((req) => (
                <Badge key={req} variant="gold">{req}</Badge>
              ))}
            </div>
            <p className="text-sm text-[var(--text-secondary)]">
              {data.industry}{t.typicalSla}: <span className="font-mono font-bold text-[var(--gold)]">{data.typical_sla}</span>
            </p>
          </Card>
        </div>
      ) : (
        <Card className="flex flex-col items-center justify-center py-16">
          <Trophy size={40} className="text-[#1e293b] mb-4" />
          <p className="text-[var(--text-muted)] text-sm">
            {t.selectIndustry}
          </p>
        </Card>
      )}
    </div>
  );
}
