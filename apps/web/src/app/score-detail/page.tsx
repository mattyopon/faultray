"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useEffect, useState } from "react";
import { api, type ScoreExplainData, type ScoreLayer } from "@/lib/api";
import { BarChart3, Loader2, TrendingDown, Briefcase, TrendingUp, AlertTriangle, Target } from "lucide-react";
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
      <p className="text-xs text-[var(--text-muted)]">
        {t.weightedContribution} {layer.weighted_score.toFixed(2)} {t.points}
      </p>

      {expanded && (
        <div className="mt-4 pt-4 border-t border-[var(--border-color)] space-y-2">
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
                <span className="text-sm text-[var(--text-secondary)]">{f.name}</span>
              </div>
              <span className="text-sm font-mono font-semibold" style={{ color: scoreColor(f.score) }}>
                {f.score}
              </span>
            </div>
          ))}
        </div>
      )}

      <p className="text-xs text-[var(--text-muted)] mt-2">{expanded ? t.clickCollapse : t.clickExpand}</p>
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
      .catch((err) => { console.error("[score-detail] API error, using demo data:", err); setData(DEMO_DATA); })
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="w-full px-6 py-10">
      <div className="mb-10">
        <h1 className="text-2xl font-bold mb-1 flex items-center gap-3">
          <BarChart3 size={24} className="text-[var(--gold)]" />
          {t.title}
        </h1>
        <p className="text-[var(--text-secondary)] text-sm">{t.subtitle}</p>
      </div>

      {loading ? (
        <Card className="flex items-center justify-center py-20">
          <Loader2 size={24} className="animate-spin text-[var(--gold)]" />
          <span className="ml-3 text-[var(--text-secondary)]">{t.loading}</span>
        </Card>
      ) : (
        <>
          <Card className="mb-6 text-center">
            <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider mb-2">{t.overallScore}</p>
            <p className="text-6xl font-extrabold font-mono" style={{ color: scoreColor(data.overall_score) }}>
              {data.overall_score.toFixed(1)}
            </p>
            <p className="text-sm text-[var(--text-secondary)] mt-2">{t.sumOfWeighted}</p>
          </Card>

          {/* DEMO-04: 経営者向けサマリー */}
          {(() => {
            const incidentCount = Math.round((100 - data.overall_score) / 10 * 3);
            const lossAmount = locale === "ja"
              ? `${(incidentCount * 150).toLocaleString()}万円`
              : `$${(incidentCount * 15000).toLocaleString()}`;
            const industryAvg = 75.0;
            const top3 = data.top_detractors.slice(0, 3);

            const factorLabel = (factor: string): string => {
              if (locale !== "ja") return factor;
              const map: Record<string, string> = {
                // Hardware
                "Server redundancy": "サーバー冗長構成",
                "Disk RAID configuration": "ディスクRAID構成",
                "Power supply redundancy": "電源の冗長化",
                "Network interface bonding": "ネットワークインターフェースの冗長化",
                // Software
                "Application replicas": "アプリケーションレプリカ数",
                "Health check coverage": "ヘルスチェックのカバー率不足",
                "Circuit breaker patterns": "サーキットブレーカーの未実装",
                "Graceful degradation": "グレースフルデグラデーション",
                "Auto-scaling policies": "オートスケーリングポリシー",
                // Theoretical
                "Markov chain steady state": "マルコフ連鎖定常状態",
                "MTBF/MTTR ratio": "MTBF/MTTR比率",
                "Reliability block diagram": "信頼性ブロック図",
                // Operational
                "Runbook coverage": "運用ランブックの整備不足",
                "On-call response time": "オンコール応答時間",
                "Deployment rollback capability": "デプロイロールバック能力",
                "Monitoring & alerting": "監視・アラート体制",
                "Incident post-mortem process": "インシデント振り返りプロセス",
                // External SLA
                "Cloud provider SLA": "クラウドプロバイダーSLA",
                "Third-party API reliability": "外部APIの信頼性不足",
                "DNS provider SLA": "DNSプロバイダーSLA",
                "CDN availability": "CDN可用性",
              };
              return map[factor] ?? factor;
            };

            return (
              <Card className="mb-6 p-6 border-[var(--gold)]/20 bg-gradient-to-br from-[#FFD700]/[0.03] to-transparent">
                <h2 className="text-lg font-bold mb-5 flex items-center gap-2">
                  <Briefcase size={20} className="text-[var(--gold)]" />
                  {locale === "ja" ? "経営者サマリー" : "Executive Summary"}
                </h2>

                <div className="grid grid-cols-2 gap-4 mb-6">
                  <div className="p-4 rounded-xl bg-red-500/5 border border-red-500/10">
                    <div className="flex items-center gap-2 mb-1">
                      <AlertTriangle size={14} className="text-red-400" />
                      <p className="text-xs text-[var(--text-muted)]">
                        {locale === "ja" ? "年間推定障害リスク回数" : "Est. Annual Incidents"}
                      </p>
                    </div>
                    <p className="text-2xl font-extrabold font-mono text-red-400">
                      {incidentCount}
                      <span className="text-sm font-normal text-[var(--text-secondary)] ml-1">
                        {locale === "ja" ? "回" : "times"}
                      </span>
                    </p>
                  </div>

                  <div className="p-4 rounded-xl bg-orange-500/5 border border-orange-500/10">
                    <div className="flex items-center gap-2 mb-1">
                      <TrendingDown size={14} className="text-orange-400" />
                      <p className="text-xs text-[var(--text-muted)]">
                        {locale === "ja" ? "推定年間損失額" : "Est. Annual Loss"}
                      </p>
                    </div>
                    <p className="text-2xl font-extrabold font-mono text-orange-400">{lossAmount}</p>
                  </div>

                  <div className="p-4 rounded-xl bg-white/[0.02] border border-white/5">
                    <div className="flex items-center gap-2 mb-1">
                      <Target size={14} className="text-[var(--text-muted)]" />
                      <p className="text-xs text-[var(--text-muted)]">
                        {locale === "ja" ? "同業他社平均スコア" : "Industry Avg Score"}
                      </p>
                    </div>
                    <p className="text-2xl font-extrabold font-mono text-[var(--text-secondary)]">{industryAvg.toFixed(1)}</p>
                  </div>

                  <div className="p-4 rounded-xl bg-white/[0.02] border border-white/5">
                    <div className="flex items-center gap-2 mb-1">
                      <TrendingUp size={14} className="text-[var(--gold)]" />
                      <p className="text-xs text-[var(--text-muted)]">
                        {locale === "ja" ? "あなたのスコア" : "Your Score"}
                      </p>
                    </div>
                    <p
                      className="text-2xl font-extrabold font-mono"
                      style={{ color: scoreColor(data.overall_score) }}
                    >
                      {data.overall_score.toFixed(1)}
                    </p>
                  </div>
                </div>

                <div>
                  <h3 className="text-sm font-semibold text-[var(--text-secondary)] mb-3">
                    {locale === "ja" ? "推奨アクション TOP3" : "Recommended Actions TOP3"}
                  </h3>
                  <div className="space-y-2">
                    {top3.map((d, i) => (
                      <div key={d.factor} className="flex items-center justify-between p-3 rounded-lg bg-white/[0.02] border border-white/5">
                        <div className="flex items-center gap-3">
                          <span className="w-5 h-5 rounded-full bg-[var(--gold)]/10 text-[var(--gold)] text-xs font-bold flex items-center justify-center">
                            {i + 1}
                          </span>
                          <span className="text-sm text-[#e2e8f0]">{factorLabel(d.factor)}</span>
                        </div>
                        <Badge variant="green">+{d.potential_gain.toFixed(1)} pt</Badge>
                      </div>
                    ))}
                  </div>
                </div>
              </Card>
            );
          })()}

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
                <p className="text-xs text-[var(--text-muted)] mb-4">{t.topDetractorsDesc}</p>
                <div className="space-y-3">
                  {data.top_detractors.map((d) => (
                    <div key={d.factor} className="p-3 rounded-xl bg-red-500/5 border border-red-500/10">
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-sm font-medium">{d.factor}</span>
                        <span className="text-sm font-mono text-red-400">{d.score}</span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-[var(--text-muted)]">{d.layer}</span>
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
