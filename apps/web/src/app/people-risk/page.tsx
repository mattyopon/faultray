"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useEffect, useState } from "react";
import Link from "next/link";
import {
  UserX,
  AlertTriangle,
  Shield,
  Users,
  Server,
  TrendingDown,
  ArrowRight,
  Activity,
  Zap,
  FileCode2,
  CheckCircle2,
  Lock,
  Eye,
  BarChart2,
} from "lucide-react";
import {
  fetchSummary,
  fetchSnapshots,
  fetchActions,
} from "@/lib/people-risk/queries";
import { useLocale } from "@/lib/useLocale";
import { useAuth } from "@/components/auth-provider";
import { appDict } from "@/i18n/app-dict";
import type {
  PeopleRiskSummary,
  RiskSnapshot,
  ActionWithSystem,
} from "@/lib/people-risk/types";

/* ── Mini sparkline (SVG) ─────────────────────────────────── */

function Sparkline({ data }: { data: number[] }) {
  if (data.length < 2) return null;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const w = 120;
  const h = 32;
  const points = data
    .map((v, i) => {
      const x = (i / (data.length - 1)) * w;
      const y = h - ((v - min) / range) * (h - 4) - 2;
      return `${x},${y}`;
    })
    .join(" ");

  return (
    <svg width={w} height={h} className="inline-block">
      <polyline
        points={points}
        fill="none"
        stroke="#FFD700"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/* ── Stat card ────────────────────────────────────────────── */

function StatCard({
  label,
  value,
  sub,
  icon: Icon,
  color,
}: {
  label: string;
  value: string | number;
  sub?: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  color: string;
}) {
  return (
    <Card className="p-6">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider mb-1">
            {label}
          </p>
          <p className="text-2xl font-bold text-white">{value}</p>
          {sub && <p className="text-xs text-[var(--text-secondary)] mt-1">{sub}</p>}
        </div>
        <div className={`p-2.5 rounded-lg ${color}`}>
          <Icon size={20} />
        </div>
      </div>
    </Card>
  );
}

/* ── Preview page (unauthenticated) ───────────────────────── */

function PeopleRiskPreview({ locale }: { locale: string }) {
  const isJa = locale === "ja";

  const features = [
    {
      icon: Users,
      title: isJa ? "メンバー × システム マップ" : "Member × System Map",
      desc: isJa
        ? "誰がどのシステムを管理しているかを一覧で可視化。属人化のホットスポットを即座に特定。"
        : "Visualize who manages which systems. Instantly spot personalization hotspots.",
    },
    {
      icon: Zap,
      title: isJa ? "ブラストレディウス・シミュレーター" : "Blast Radius Simulator",
      desc: isJa
        ? "「この人が退職したら何が壊れるか」をワンクリックでシミュレーション。リスクを数値化。"
        : "Simulate the impact of any member leaving with one click. Quantify your risk.",
    },
    {
      icon: BarChart2,
      title: isJa ? "週次リスクトレンド" : "Weekly Risk Trend",
      desc: isJa
        ? "リスクスコアの推移をグラフで確認。改善アクションの効果を時系列で追跡。"
        : "Track risk score trends over time. Measure the impact of your improvement actions.",
    },
    {
      icon: Shield,
      title: isJa ? "改善アクション管理" : "Improvement Action Tracking",
      desc: isJa
        ? "優先度付きの改善タスクを一元管理。バックアップ管理者の設定漏れをゼロに。"
        : "Manage prioritized improvement tasks in one place. Never miss a backup admin assignment.",
    },
  ];

  const stats = [
    { value: isJa ? "平均 2.4件" : "2.4 avg", label: isJa ? "リスク検出 / メンバー" : "risks detected / member" },
    { value: isJa ? "60%削減" : "60% less", label: isJa ? "属人化リスク (3ヶ月後)" : "personalization risk in 3mo" },
    { value: isJa ? "5分" : "5 min", label: isJa ? "セットアップ時間" : "setup time" },
  ];

  return (
    <div className="min-h-screen bg-[#0a0f1e] text-white">
      {/* Hero */}
      <div className="px-6 py-16 md:py-24 max-w-5xl mx-auto text-center">
        <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-[var(--gold)]/10 border border-[var(--gold)]/20 text-[var(--gold)] text-xs font-semibold mb-6">
          <Lock size={12} />
          {isJa ? "ログインが必要です" : "Login required"}
        </div>
        <h1 className="text-3xl md:text-4xl font-bold text-white mb-4">
          <span className="text-[var(--gold)]">People Risk</span>{" "}
          {isJa ? "— 属人化リスクを可視化する" : "— Visualize Personalization Risk"}
        </h1>
        <p className="text-[var(--text-secondary)] text-base md:text-lg max-w-2xl mx-auto mb-8">
          {isJa
            ? "誰が退職したら何が壊れるか、今すぐ把握しましょう。GAS棚卸しから退職シミュレーションまで、属人化リスクを一元管理。"
            : "Know exactly what breaks if someone leaves — today. From GAS inventory to departure simulation, manage all personalization risk in one place."}
        </p>
        <div className="flex flex-col sm:flex-row gap-3 justify-center">
          <Link href="/login">
            <Button size="lg" className="w-full sm:w-auto">
              {isJa ? "無料で始める" : "Get started free"}
            </Button>
          </Link>
          <Link href="/login">
            <Button variant="secondary" size="lg" className="w-full sm:w-auto">
              <Eye size={16} />
              {isJa ? "デモを見る" : "View demo"}
            </Button>
          </Link>
        </div>
      </div>

      {/* Stats bar */}
      <div className="border-y border-[var(--border-color)] py-8">
        <div className="max-w-3xl mx-auto grid grid-cols-3 gap-6 px-6 text-center">
          {stats.map((s) => (
            <div key={s.label}>
              <p className="text-2xl font-bold text-[var(--gold)]">{s.value}</p>
              <p className="text-xs text-[var(--text-muted)] mt-1">{s.label}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Feature cards */}
      <div className="px-6 py-16 max-w-5xl mx-auto">
        <h2 className="text-xl font-bold text-white text-center mb-10">
          {isJa ? "主な機能" : "Key Features"}
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {features.map((f) => {
            const Icon = f.icon;
            return (
              <Card key={f.title} className="p-6">
                <div className="flex items-start gap-4">
                  <div className="w-10 h-10 rounded-lg bg-[var(--gold)]/10 flex items-center justify-center shrink-0">
                    <Icon size={20} className="text-[var(--gold)]" />
                  </div>
                  <div>
                    <h3 className="text-sm font-semibold text-white mb-1">{f.title}</h3>
                    <p className="text-xs text-[var(--text-muted)] leading-relaxed">{f.desc}</p>
                  </div>
                </div>
              </Card>
            );
          })}
        </div>
      </div>

      {/* CTA */}
      <div className="px-6 pb-20 max-w-xl mx-auto text-center">
        <Card className="p-8 border-[var(--gold)]/20">
          <h3 className="text-lg font-bold text-white mb-2">
            {isJa ? "今すぐ属人化リスクを把握する" : "Start mapping your people risk now"}
          </h3>
          <p className="text-sm text-[var(--text-muted)] mb-6">
            {isJa
              ? "無料プランで最大5名・5システムまで登録可能。クレジットカード不要。"
              : "Free plan supports up to 5 members and 5 systems. No credit card required."}
          </p>
          <Link href="/login">
            <Button size="lg" className="w-full">
              {isJa ? "FaultRayに登録する" : "Sign up for FaultRay"}
            </Button>
          </Link>
        </Card>
      </div>
    </div>
  );
}

/* ── Page ─────────────────────────────────────────────────── */

export default function PeopleRiskDashboard() {
  const { user, loading: authLoading } = useAuth();
  const [summary, setSummary] = useState<PeopleRiskSummary | null>(null);
  const [snapshots, setSnapshots] = useState<RiskSnapshot[]>([]);
  const [actions, setActions] = useState<ActionWithSystem[]>([]);
  const [loading, setLoading] = useState(true);
  const locale = useLocale();
  const t = appDict.peopleRisk[locale] ?? appDict.peopleRisk.en;

  useEffect(() => {
    // 未ログイン時はデータフェッチをスキップ
    if (!user) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setLoading(false);
      return;
    }
    // FETCHPAT-04: Use Promise.allSettled so one failure doesn't block others
    Promise.allSettled([fetchSummary(), fetchSnapshots(), fetchActions()])
      .then(([sRes, snRes, aRes]) => {
        if (sRes.status === "fulfilled") setSummary(sRes.value);
        if (snRes.status === "fulfilled") setSnapshots(snRes.value);
        if (aRes.status === "fulfilled") setActions(aRes.value);
      })
      .finally(() => setLoading(false));
  }, [user]);

  // 認証状態を待機中
  if (authLoading) {
    return (
      <div className="p-6 md:p-10 max-w-7xl mx-auto">
        <div className="animate-pulse space-y-6">
          <div className="h-8 w-64 bg-[var(--border-color)] rounded" />
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="h-28 bg-[var(--border-color)] rounded-2xl" />
            ))}
          </div>
        </div>
      </div>
    );
  }

  // 未ログイン → サービス紹介ページを表示
  if (!user) {
    return <PeopleRiskPreview locale={locale} />;
  }

  if (loading) {
    return (
      <div className="p-6 md:p-10 max-w-7xl mx-auto">
        <div className="animate-pulse space-y-6">
          <div className="h-8 w-64 bg-[var(--border-color)] rounded" />
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="h-28 bg-[var(--border-color)] rounded-2xl" />
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (!summary) return null;

  const pendingActions = actions.filter((a) => a.status !== "done");
  const criticalActions = pendingActions.filter(
    (a) => a.priority === "critical"
  );

  return (
    <div className="p-6 md:p-10 max-w-7xl mx-auto space-y-8">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <UserX size={24} className="text-[var(--gold)]" />
            {t.title}
          </h1>
          <p className="text-sm text-[var(--text-secondary)] mt-1">
            {t.subtitle}
          </p>
        </div>
        <div className="flex gap-2">
          <Link href="/people-risk/blast-radius">
            <Button variant="secondary" size="sm">
              <Zap size={14} />
              {t.blastRadiusTitle}
            </Button>
          </Link>
          <Link href="/people-risk/members">
            <Button size="sm">
              <Users size={14} />
              {locale === "ja" ? "メンバー一覧" : "Members"}
            </Button>
          </Link>
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label={locale === "ja" ? "管理システム数" : t.totalPeople}
          value={summary.totalSystems}
          sub={locale === "ja" ? `${summary.activeMembers}名が管理中` : `${summary.activeMembers} active`}
          icon={Server}
          color="bg-blue-500/10 text-blue-400"
        />
        <StatCard
          label={t.singleDep}
          value={summary.singleOwnerSystems}
          sub={t.busFactor}
          icon={AlertTriangle}
          color="bg-red-500/10 text-red-400"
        />
        <StatCard
          label={t.avgRisk}
          value={summary.avgRiskScore}
          sub={locale === "ja" ? "10が最大リスク" : "max risk = 10"}
          icon={Activity}
          color="bg-yellow-500/10 text-yellow-400"
        />
        <StatCard
          label={locale === "ja" ? "退職済みメンバー" : "Left Members"}
          value={summary.leftMembers}
          sub={locale === "ja" ? `全${summary.totalMembers}名中` : `of ${summary.totalMembers} total`}
          icon={UserX}
          color="bg-purple-500/10 text-purple-400"
        />
      </div>

      {/* Risk Breakdown + Trend */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Risk Distribution */}
        <Card className="p-6">
          <h2 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
            <Shield size={16} className="text-[var(--gold)]" />
            {locale === "ja" ? "リスクレベル分布" : "Risk Level Distribution"}
          </h2>
          <div className="space-y-3">
            {[
              {
                label: locale === "ja" ? "危険（Critical）" : "Critical",
                count: summary.criticalCount,
                total: summary.criticalCount + summary.warningCount + summary.safeCount,
                color: "bg-red-500",
                textColor: "text-red-400",
              },
              {
                label: locale === "ja" ? "注意（Warning）" : "Warning",
                count: summary.warningCount,
                total: summary.criticalCount + summary.warningCount + summary.safeCount,
                color: "bg-yellow-500",
                textColor: "text-yellow-400",
              },
              {
                label: locale === "ja" ? "安全（Safe）" : "Safe",
                count: summary.safeCount,
                total: summary.criticalCount + summary.warningCount + summary.safeCount,
                color: "bg-emerald-500",
                textColor: "text-emerald-400",
              },
            ].map((item) => {
              const pct =
                item.total > 0
                  ? Math.round((item.count / item.total) * 100)
                  : 0;
              return (
                <div key={item.label}>
                  <div className="flex items-center justify-between text-xs mb-1">
                    <span className={item.textColor}>{item.label}</span>
                    <span className="text-[var(--text-secondary)]">
                      {item.count}件 ({pct}%)
                    </span>
                  </div>
                  <div className="h-2 bg-[var(--border-color)] rounded-full overflow-hidden">
                    <div
                      className={`h-full ${item.color} rounded-full transition-all duration-500`}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </Card>

        {/* Weekly Trend */}
        <Card className="p-6">
          <h2 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
            <TrendingDown size={16} className="text-emerald-400" />
            {t.trendTitle}
          </h2>
          {snapshots.length > 0 ? (
            <div className="space-y-4">
              <div className="flex items-center gap-4">
                <Sparkline
                  data={snapshots.map((s) => s.avg_risk_score ?? 0)}
                />
                <div className="text-xs text-[var(--text-secondary)]">
                  <p>
                    最新:{" "}
                    <span className="text-white font-semibold">
                      {snapshots[snapshots.length - 1]?.avg_risk_score}
                    </span>
                  </p>
                  <p>
                    {snapshots.length}週間で{" "}
                    <span className="text-emerald-400">
                      {(
                        (snapshots[0]?.avg_risk_score ?? 0) -
                        (snapshots[snapshots.length - 1]?.avg_risk_score ?? 0)
                      ).toFixed(1)}
                    </span>{" "}
                    改善
                  </p>
                </div>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-[var(--text-muted)] border-b border-[var(--border-color)]">
                      <th scope="col" className="text-left py-2 font-medium">週</th>
                      <th scope="col" className="text-right py-2 font-medium">リスクスコア</th>
                      <th scope="col" className="text-right py-2 font-medium">BF=1</th>
                      <th scope="col" className="text-right py-2 font-medium">システム数</th>
                    </tr>
                  </thead>
                  <tbody>
                    {snapshots
                      .slice(-5)
                      .reverse()
                      .map((s) => (
                        <tr
                          key={s.id}
                          className="border-b border-[var(--border-color)]/50"
                        >
                          <td className="py-2 text-[var(--text-secondary)]">
                            {s.week_start}
                          </td>
                          <td className="py-2 text-right text-white">
                            {s.avg_risk_score}
                          </td>
                          <td className="py-2 text-right text-yellow-400">
                            {s.bus_factor_1_count}
                          </td>
                          <td className="py-2 text-right text-[var(--text-secondary)]">
                            {s.total_systems}
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <p className="text-sm text-[var(--text-muted)]">データがありません</p>
          )}
        </Card>
      </div>

      {/* Quick Links + Actions */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Quick Navigation */}
        <Card className="p-6">
          <h2 className="text-sm font-semibold text-white mb-4">{locale === "ja" ? "クイックアクセス" : "Quick Access"}</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {[
              {
                href: "/people-risk/members",
                label: locale === "ja" ? "メンバー一覧" : "Members",
                desc: locale === "ja" ? `${summary.totalMembers}名の管理状況` : `${summary.totalMembers} members`,
                icon: Users,
              },
              {
                href: "/people-risk/systems",
                label: locale === "ja" ? "システム一覧" : "Systems",
                desc: locale === "ja" ? `GAS棚卸し含む ${summary.totalSystems}件` : `${summary.totalSystems} systems`,
                icon: Server,
              },
              {
                href: "/people-risk/blast-radius",
                label: locale === "ja" ? "退職シミュレーション" : "Blast Radius",
                desc: locale === "ja" ? "影響範囲を即座に確認" : "Simulate departure impact",
                icon: Zap,
              },
              {
                href: "/people-risk/actions",
                label: locale === "ja" ? "改善アクション" : t.actionsTitle,
                desc: locale === "ja" ? `${pendingActions.length}件が対応待ち` : `${pendingActions.length} pending`,
                icon: CheckCircle2,
              },
            ].map((link) => {
              const Icon = link.icon;
              return (
                <Link key={link.href} href={link.href}>
                  <div className="flex items-center gap-3 p-3 rounded-lg border border-[var(--border-color)] hover:border-[var(--gold)]/30 hover:bg-[var(--bg-card-hover)] transition-all group">
                    <Icon
                      size={18}
                      className="text-[var(--text-muted)] group-hover:text-[var(--gold)] transition-colors shrink-0"
                    />
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-white group-hover:text-[var(--gold)] transition-colors">
                        {link.label}
                      </p>
                      <p className="text-xs text-[var(--text-muted)]">{link.desc}</p>
                    </div>
                    <ArrowRight
                      size={14}
                      className="ml-auto text-[var(--text-muted)] group-hover:text-[var(--gold)] transition-colors shrink-0"
                    />
                  </div>
                </Link>
              );
            })}
          </div>
        </Card>

        {/* Critical Actions */}
        <Card className="p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-white flex items-center gap-2">
              <AlertTriangle size={16} className="text-red-400" />
              {locale === "ja" ? "緊急対応アクション" : "Critical Actions"}
            </h2>
            <Link href="/people-risk/actions">
              <Badge variant="gold" className="cursor-pointer">
                {locale === "ja" ? `全${pendingActions.length}件` : `${pendingActions.length} total`}
              </Badge>
            </Link>
          </div>
          <div className="space-y-2">
            {criticalActions.length === 0 ? (
              <p className="text-sm text-[var(--text-muted)]">
                {locale === "ja" ? "緊急対応が必要なアクションはありません" : "No critical actions pending."}
              </p>
            ) : (
              criticalActions.slice(0, 5).map((action) => (
                <div
                  key={action.id}
                  className="flex items-start gap-3 p-3 rounded-lg bg-red-500/5 border border-red-500/10"
                >
                  <FileCode2
                    size={16}
                    className="text-red-400 mt-0.5 shrink-0"
                  />
                  <div className="min-w-0">
                    <p className="text-sm text-white">{action.title}</p>
                    {action.systems && (
                      <p className="text-xs text-[var(--text-muted)] mt-0.5">
                        {locale === "ja" ? "対象:" : "System:"} {action.systems.name}
                      </p>
                    )}
                  </div>
                  <Badge variant="red" className="ml-auto shrink-0">
                    {action.status === "in_progress" ? (locale === "ja" ? "対応中" : "In Progress") : (locale === "ja" ? "未対応" : "Pending")}
                  </Badge>
                </div>
              ))
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}
