"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useEffect, useState } from "react";
import { api, type ScoreExplainData, type ScoreLayer } from "@/lib/api";
import { BarChart3, Loader2, TrendingDown } from "lucide-react";
import { useLocale } from "@/lib/useLocale";
import { appDict } from "@/i18n/app-dict";

const DEMO_DATA: ScoreExplainData = {
  overall_score: 85.2,
  layers: [
    { name: "Hardware", score: 92.5, weight: 0.20, weighted_score: 18.5, factors: [
      { name: "Server redundancy", score: 95, impact: "positive" },
      { name: "Disk RAID configuration", score: 90, impact: "positive" },
      { name: "Power supply redundancy", score: 88, impact: "neutral" },
      { name: "Network interface bonding", score: 97, impact: "positive" },
    ]},
    { name: "Software", score: 78.3, weight: 0.25, weighted_score: 19.6, factors: [
      { name: "Application replicas", score: 85, impact: "positive" },
      { name: "Health check coverage", score: 72, impact: "negative" },
      { name: "Circuit breaker patterns", score: 60, impact: "negative" },
      { name: "Graceful degradation", score: 80, impact: "neutral" },
      { name: "Auto-scaling policies", score: 94, impact: "positive" },
    ]},
    { name: "Theoretical", score: 95.0, weight: 0.15, weighted_score: 14.25, factors: [
      { name: "Markov chain steady state", score: 97, impact: "positive" },
      { name: "MTBF/MTTR ratio", score: 93, impact: "positive" },
      { name: "Reliability block diagram", score: 95, impact: "positive" },
    ]},
    { name: "Operational", score: 80.0, weight: 0.25, weighted_score: 20.0, factors: [
      { name: "Runbook coverage", score: 65, impact: "negative" },
      { name: "On-call response time", score: 82, impact: "neutral" },
      { name: "Deployment rollback capability", score: 90, impact: "positive" },
      { name: "Monitoring & alerting", score: 85, impact: "positive" },
      { name: "Incident post-mortem process", score: 78, impact: "neutral" },
    ]},
    { name: "External SLA", score: 85.6, weight: 0.15, weighted_score: 12.84, factors: [
      { name: "Cloud provider SLA", score: 99, impact: "positive" },
      { name: "Third-party API reliability", score: 72, impact: "negative" },
      { name: "DNS provider SLA", score: 99, impact: "positive" },
      { name: "CDN availability", score: 95, impact: "positive" },
    ]},
  ],
  top_detractors: [
    { factor: "Circuit breaker patterns", layer: "Software", score: 60, potential_gain: 3.2 },
    { factor: "Runbook coverage", layer: "Operational", score: 65, potential_gain: 2.8 },
    { factor: "Third-party API reliability", layer: "External SLA", score: 72, potential_gain: 1.5 },
    { factor: "Health check coverage", layer: "Software", score: 72, potential_gain: 1.2 },
  ],
};

function scoreColor(score: number): string {
  if (score >= 90) return "#10b981";
  if (score >= 70) return "#FFD700";
  return "#ef4444";
}

function LayerCard({ layer, t }: { layer: ScoreLayer; t: (typeof appDict.scoreDetail)[keyof typeof appDict.scoreDetail] }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <Card className="cursor-pointer" onClick={() => setExpanded(!expanded)}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-3">
          <h3 className="font-bold">{layer.name}</h3>
          <Badge variant="default">{(layer.weight * 100).toFixed(0)}% {t.weight}</Badge>
        </div>
        <span className="text-2xl font-extrabold font-mono" style={{ color: scoreColor(layer.score) }}>
          {layer.score.toFixed(1)}
        </span>
      </div>

      <div className="h-2 bg-white/5 rounded-full overflow-hidden mb-2">
        <div
          className="h-full rounded-full transition-all duration-700"
          style={{ width: `${layer.score}%`, backgroundColor: scoreColor(layer.score) }}
        />
      </div>
      <p className="text-xs text-[#64748b]">
        {t.weightedContribution} {layer.weighted_score.toFixed(2)} {t.points}
      </p>

      {expanded && (
        <div className="mt-4 pt-4 border-t border-[#1e293b] space-y-2">
          {layer.factors.map((f) => (
            <div key={f.name} className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div
                  className="w-2 h-2 rounded-full"
                  style={{
                    backgroundColor:
                      f.impact === "positive" ? "#10b981" : f.impact === "negative" ? "#ef4444" : "#64748b",
                  }}
                />
                <span className="text-sm text-[#94a3b8]">{f.name}</span>
              </div>
              <span className="text-sm font-mono font-semibold" style={{ color: scoreColor(f.score) }}>
                {f.score}
              </span>
            </div>
          ))}
        </div>
      )}

      <p className="text-xs text-[#64748b] mt-2">{expanded ? t.clickCollapse : t.clickExpand}</p>
    </Card>
  );
}

export default function ScoreDetailPage() {
  const [data, setData] = useState<ScoreExplainData>(DEMO_DATA);
  const [loading, setLoading] = useState(true);
  const locale = useLocale();
  const t = appDict.scoreDetail[locale] ?? appDict.scoreDetail.en;

  useEffect(() => {
    api
      .getScoreExplain()
      .then((result) => setData(result))
      .catch(() => setData(DEMO_DATA))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="max-w-[1200px] mx-auto px-6 py-10">
      <div className="mb-10">
        <h1 className="text-2xl font-bold mb-1 flex items-center gap-3">
          <BarChart3 size={24} className="text-[#FFD700]" />
          {t.title}
        </h1>
        <p className="text-[#94a3b8] text-sm">{t.subtitle}</p>
      </div>

      {loading ? (
        <Card className="flex items-center justify-center py-20">
          <Loader2 size={24} className="animate-spin text-[#FFD700]" />
          <span className="ml-3 text-[#94a3b8]">{t.loading}</span>
        </Card>
      ) : (
        <>
          <Card className="mb-6 text-center">
            <p className="text-xs text-[#64748b] uppercase tracking-wider mb-2">{t.overallScore}</p>
            <p className="text-6xl font-extrabold font-mono" style={{ color: scoreColor(data.overall_score) }}>
              {data.overall_score.toFixed(1)}
            </p>
            <p className="text-sm text-[#94a3b8] mt-2">{t.sumOfWeighted}</p>
          </Card>

          <div className="grid lg:grid-cols-[1fr_350px] gap-6">
            <div className="space-y-4">
              {data.layers.map((layer) => (
                <LayerCard key={layer.name} layer={layer} t={t} />
              ))}
            </div>

            <div>
              <Card>
                <h3 className="text-lg font-bold mb-4 flex items-center gap-2">
                  <TrendingDown size={18} className="text-red-400" />
                  {t.topDetractors}
                </h3>
                <p className="text-xs text-[#64748b] mb-4">{t.topDetractorsDesc}</p>
                <div className="space-y-3">
                  {data.top_detractors.map((d) => (
                    <div key={d.factor} className="p-3 rounded-xl bg-red-500/5 border border-red-500/10">
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-sm font-medium">{d.factor}</span>
                        <span className="text-sm font-mono text-red-400">{d.score}</span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-[#64748b]">{d.layer}</span>
                        <Badge variant="green">+{d.potential_gain.toFixed(1)} {t.pts}</Badge>
                      </div>
                    </div>
                  ))}
                </div>
              </Card>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
