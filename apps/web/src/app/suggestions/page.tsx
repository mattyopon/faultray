"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Lightbulb,
  TrendingUp,
  ArrowUpRight,
  Shield,
  Database,
  GitBranch,
  Gauge,
  AlertTriangle,
  ClipboardCheck,
} from "lucide-react";
import Link from "next/link";
import { useLocale } from "@/lib/useLocale";
import { appDict } from "@/i18n/app-dict";

const suggestions = [
  {
    title: { en: "Add database read replica", ja: "データベースリードレプリカの追加" },
    description: { en: "Implement a read replica for your primary database to handle failover scenarios. This eliminates the single point of failure in your data layer.", ja: "プライマリデータベースにリードレプリカを実装し、フェイルオーバーシナリオに対応します。データ層の単一障害点を排除します。" },
    impact: "+0.5 nines",
    effort: { en: "Medium", ja: "中" },
    category: { en: "Redundancy", ja: "冗長性" },
    icon: Database,
    priority: "high",
  },
  {
    title: { en: "Implement circuit breaker pattern", ja: "サーキットブレーカーパターンの実装" },
    description: { en: "Add circuit breaker pattern to prevent cascading failures between services. When a downstream service fails, the circuit breaker stops further requests.", ja: "サービス間のカスケード障害を防止するサーキットブレーカーパターンを追加します。下流サービスの障害時にリクエストを遮断します。" },
    impact: "+0.3 nines",
    effort: { en: "Low", ja: "低" },
    category: { en: "Resilience", ja: "レジリエンス" },
    icon: Shield,
    priority: "high",
  },
  {
    title: { en: "Multi-region DNS failover", ja: "マルチリージョンDNSフェイルオーバー" },
    description: { en: "Configure DNS-based failover to automatically route traffic to a healthy region when the primary region experiences issues.", ja: "DNSベースのフェイルオーバーを構成し、プライマリリージョンに問題が発生した場合に自動的に正常なリージョンへトラフィックを切り替えます。" },
    impact: "+0.8 nines",
    effort: { en: "High", ja: "高" },
    category: { en: "Availability", ja: "可用性" },
    icon: TrendingUp,
    priority: "high",
  },
  {
    title: { en: "Cache cluster partitioning tolerance", ja: "キャッシュクラスタのパーティション耐性強化" },
    description: { en: "Implement graceful degradation when cache clusters experience network partitions. Fallback to direct database queries with rate limiting.", ja: "キャッシュクラスタでネットワーク分断が発生した場合のグレースフルデグレデーションを実装します。レート制限付きの直接データベースクエリにフォールバックします。" },
    impact: "+0.2 nines",
    effort: { en: "Medium", ja: "中" },
    category: { en: "Resilience", ja: "レジリエンス" },
    icon: GitBranch,
    priority: "medium",
  },
  {
    title: { en: "Health check endpoint optimization", ja: "ヘルスチェックエンドポイントの最適化" },
    description: { en: "Add deep health checks that verify database connectivity, cache availability, and external service reachability.", ja: "データベース接続性、キャッシュの可用性、外部サービスへの到達性を検証するディープヘルスチェックを追加します。" },
    impact: "+0.1 nines",
    effort: { en: "Low", ja: "低" },
    category: { en: "Monitoring", ja: "監視" },
    icon: Gauge,
    priority: "medium",
  },
  {
    title: { en: "Implement retry with exponential backoff", ja: "指数バックオフ付きリトライの実装" },
    description: { en: "Add retry logic with exponential backoff and jitter for all external service calls to handle transient failures gracefully.", ja: "すべての外部サービス呼び出しに対して、指数バックオフとジッター付きのリトライロジックを追加し、一時的な障害を適切に処理します。" },
    impact: "+0.15 nines",
    effort: { en: "Low", ja: "低" },
    category: { en: "Resilience", ja: "レジリエンス" },
    icon: AlertTriangle,
    priority: "low",
  },
];

export default function SuggestionsPage() {
  const locale = useLocale();
  const t = appDict.suggestions[locale] ?? appDict.suggestions.en;
  const priorityLabel = (p: string) => {
    if (locale !== "ja") return p;
    return p === "high" ? "高" : p === "medium" ? "中" : "低";
  };

  return (
    <div className="max-w-[1200px] mx-auto px-6 py-10">
      <div className="mb-10">
        <h1 className="text-2xl font-bold mb-1">{t.title}</h1>
        <p className="text-[#94a3b8] text-sm">{t.subtitle}</p>
      </div>

      {/* Summary */}
      <div className="grid md:grid-cols-3 gap-6 mb-10">
        <Card>
          <div className="flex items-center gap-3 mb-2">
            <div className="w-10 h-10 rounded-lg bg-emerald-500/10 flex items-center justify-center">
              <TrendingUp size={20} className="text-emerald-400" />
            </div>
            <p className="text-xs text-[#64748b] uppercase tracking-wider">{t.potentialImprovement}</p>
          </div>
          <p className="text-2xl font-bold font-mono text-emerald-400">+2.05 nines</p>
          <p className="text-xs text-[#64748b] mt-1">{t.ifAll}</p>
        </Card>
        <Card>
          <div className="flex items-center gap-3 mb-2">
            <div className="w-10 h-10 rounded-lg bg-red-500/10 flex items-center justify-center">
              <AlertTriangle size={20} className="text-red-400" />
            </div>
            <p className="text-xs text-[#64748b] uppercase tracking-wider">{t.highPriority}</p>
          </div>
          <p className="text-2xl font-bold font-mono">3</p>
          <p className="text-xs text-[#64748b] mt-1">{t.immediateAttention}</p>
        </Card>
        <Card>
          <div className="flex items-center gap-3 mb-2">
            <div className="w-10 h-10 rounded-lg bg-[#FFD700]/10 flex items-center justify-center">
              <Lightbulb size={20} className="text-[#FFD700]" />
            </div>
            <p className="text-xs text-[#64748b] uppercase tracking-wider">{t.totalSuggestions}</p>
          </div>
          <p className="text-2xl font-bold font-mono">6</p>
          <p className="text-xs text-[#64748b] mt-1">{t.acrossCategories}</p>
        </Card>
      </div>

      {/* Link to Remediation Plan */}
      <Link href="/remediation">
        <Card hover className="mb-10 cursor-pointer">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 rounded-xl bg-[#FFD700]/[0.06] border border-[#FFD700]/10 flex items-center justify-center shrink-0">
              <ClipboardCheck size={22} className="text-[#FFD700]" />
            </div>
            <div className="flex-1">
              <h3 className="font-bold mb-1">{(appDict.remediation[locale] ?? appDict.remediation.en).viewDetailedPlan}</h3>
              <p className="text-sm text-[#94a3b8]">{(appDict.remediation[locale] ?? appDict.remediation.en).subtitle}</p>
            </div>
            <ArrowUpRight size={20} className="text-[#FFD700] shrink-0" />
          </div>
        </Card>
      </Link>

      {/* Suggestions List */}
      <div className="space-y-4">
        {suggestions.map((s, i) => {
          const Icon = s.icon;
          return (
            <Card key={i} hover className="cursor-pointer">
              <div className="flex items-start gap-5">
                <div className="w-12 h-12 rounded-xl bg-[#FFD700]/[0.06] border border-[#FFD700]/10 flex items-center justify-center shrink-0">
                  <Icon size={22} className="text-[#FFD700]" />
                </div>
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <h3 className="font-bold">{(s.title as Record<string,string>)[locale] ?? s.title.en}</h3>
                    <Badge variant={s.priority === "high" ? "red" : s.priority === "medium" ? "yellow" : "default"}>
                      {priorityLabel(s.priority)}
                    </Badge>
                    <Badge variant="default">{(s.category as Record<string,string>)[locale] ?? s.category.en}</Badge>
                  </div>
                  <p className="text-sm text-[#94a3b8] leading-relaxed mb-3">{(s.description as Record<string,string>)[locale] ?? s.description.en}</p>
                  <div className="flex items-center gap-4">
                    <div className="flex items-center gap-1.5 text-emerald-400 text-sm font-semibold">
                      <ArrowUpRight size={14} />
                      {s.impact}
                    </div>
                    <span className="text-[#1e293b]">|</span>
                    <span className="text-xs text-[#64748b]">{t.effort}: {(s.effort as Record<string,string>)[locale] ?? s.effort.en}</span>
                  </div>
                </div>
              </div>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
