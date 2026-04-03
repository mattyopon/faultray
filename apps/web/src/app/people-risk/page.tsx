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
} from "lucide-react";
import {
  fetchSummary,
  fetchSnapshots,
  fetchActions,
} from "@/lib/people-risk/queries";
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
          <p className="text-xs text-[#64748b] uppercase tracking-wider mb-1">
            {label}
          </p>
          <p className="text-2xl font-bold text-white">{value}</p>
          {sub && <p className="text-xs text-[#94a3b8] mt-1">{sub}</p>}
        </div>
        <div className={`p-2.5 rounded-lg ${color}`}>
          <Icon size={20} />
        </div>
      </div>
    </Card>
  );
}

/* ── Page ─────────────────────────────────────────────────── */

export default function PeopleRiskDashboard() {
  const [summary, setSummary] = useState<PeopleRiskSummary | null>(null);
  const [snapshots, setSnapshots] = useState<RiskSnapshot[]>([]);
  const [actions, setActions] = useState<ActionWithSystem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // FETCHPAT-04: Use Promise.allSettled so one failure doesn't block others
    Promise.allSettled([fetchSummary(), fetchSnapshots(), fetchActions()])
      .then(([sRes, snRes, aRes]) => {
        if (sRes.status === "fulfilled") setSummary(sRes.value);
        if (snRes.status === "fulfilled") setSnapshots(snRes.value);
        if (aRes.status === "fulfilled") setActions(aRes.value);
      })
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="p-6 md:p-10 max-w-7xl mx-auto">
        <div className="animate-pulse space-y-6">
          <div className="h-8 w-64 bg-[#1e293b] rounded" />
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="h-28 bg-[#1e293b] rounded-2xl" />
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
            <UserX size={24} className="text-[#FFD700]" />
            属人化リスクダッシュボード
          </h1>
          <p className="text-sm text-[#94a3b8] mt-1">
            誰に依存しているか、誰が退職したら何が壊れるかを可視化します
          </p>
        </div>
        <div className="flex gap-2">
          <Link href="/people-risk/blast-radius">
            <Button variant="secondary" size="sm">
              <Zap size={14} />
              退職シミュレーション
            </Button>
          </Link>
          <Link href="/people-risk/members">
            <Button size="sm">
              <Users size={14} />
              メンバー一覧
            </Button>
          </Link>
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="管理システム数"
          value={summary.totalSystems}
          sub={`${summary.activeMembers}名が管理中`}
          icon={Server}
          color="bg-blue-500/10 text-blue-400"
        />
        <StatCard
          label="単一担当者依存"
          value={summary.singleOwnerSystems}
          sub="Bus Factor = 1"
          icon={AlertTriangle}
          color="bg-red-500/10 text-red-400"
        />
        <StatCard
          label="平均リスクスコア"
          value={summary.avgRiskScore}
          sub="10が最大リスク"
          icon={Activity}
          color="bg-yellow-500/10 text-yellow-400"
        />
        <StatCard
          label="退職済みメンバー"
          value={summary.leftMembers}
          sub={`全${summary.totalMembers}名中`}
          icon={UserX}
          color="bg-purple-500/10 text-purple-400"
        />
      </div>

      {/* Risk Breakdown + Trend */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Risk Distribution */}
        <Card className="p-6">
          <h2 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
            <Shield size={16} className="text-[#FFD700]" />
            リスクレベル分布
          </h2>
          <div className="space-y-3">
            {[
              {
                label: "危険（Critical）",
                count: summary.criticalCount,
                total: summary.criticalCount + summary.warningCount + summary.safeCount,
                color: "bg-red-500",
                textColor: "text-red-400",
              },
              {
                label: "注意（Warning）",
                count: summary.warningCount,
                total: summary.criticalCount + summary.warningCount + summary.safeCount,
                color: "bg-yellow-500",
                textColor: "text-yellow-400",
              },
              {
                label: "安全（Safe）",
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
                    <span className="text-[#94a3b8]">
                      {item.count}件 ({pct}%)
                    </span>
                  </div>
                  <div className="h-2 bg-[#1e293b] rounded-full overflow-hidden">
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
            週次リスクトレンド
          </h2>
          {snapshots.length > 0 ? (
            <div className="space-y-4">
              <div className="flex items-center gap-4">
                <Sparkline
                  data={snapshots.map((s) => s.avg_risk_score ?? 0)}
                />
                <div className="text-xs text-[#94a3b8]">
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
                    <tr className="text-[#64748b] border-b border-[#1e293b]">
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
                          className="border-b border-[#1e293b]/50"
                        >
                          <td className="py-2 text-[#94a3b8]">
                            {s.week_start}
                          </td>
                          <td className="py-2 text-right text-white">
                            {s.avg_risk_score}
                          </td>
                          <td className="py-2 text-right text-yellow-400">
                            {s.bus_factor_1_count}
                          </td>
                          <td className="py-2 text-right text-[#94a3b8]">
                            {s.total_systems}
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <p className="text-sm text-[#64748b]">データがありません</p>
          )}
        </Card>
      </div>

      {/* Quick Links + Actions */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Quick Navigation */}
        <Card className="p-6">
          <h2 className="text-sm font-semibold text-white mb-4">クイックアクセス</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {[
              {
                href: "/people-risk/members",
                label: "メンバー一覧",
                desc: `${summary.totalMembers}名の管理状況`,
                icon: Users,
              },
              {
                href: "/people-risk/systems",
                label: "システム一覧",
                desc: `GAS棚卸し含む ${summary.totalSystems}件`,
                icon: Server,
              },
              {
                href: "/people-risk/blast-radius",
                label: "退職シミュレーション",
                desc: "影響範囲を即座に確認",
                icon: Zap,
              },
              {
                href: "/people-risk/actions",
                label: "改善アクション",
                desc: `${pendingActions.length}件が対応待ち`,
                icon: CheckCircle2,
              },
            ].map((link) => {
              const Icon = link.icon;
              return (
                <Link key={link.href} href={link.href}>
                  <div className="flex items-center gap-3 p-3 rounded-lg border border-[#1e293b] hover:border-[#FFD700]/30 hover:bg-[#1a2035] transition-all group">
                    <Icon
                      size={18}
                      className="text-[#64748b] group-hover:text-[#FFD700] transition-colors shrink-0"
                    />
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-white group-hover:text-[#FFD700] transition-colors">
                        {link.label}
                      </p>
                      <p className="text-xs text-[#64748b]">{link.desc}</p>
                    </div>
                    <ArrowRight
                      size={14}
                      className="ml-auto text-[#475569] group-hover:text-[#FFD700] transition-colors shrink-0"
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
              緊急対応アクション
            </h2>
            <Link href="/people-risk/actions">
              <Badge variant="gold" className="cursor-pointer">
                全{pendingActions.length}件
              </Badge>
            </Link>
          </div>
          <div className="space-y-2">
            {criticalActions.length === 0 ? (
              <p className="text-sm text-[#64748b]">
                緊急対応が必要なアクションはありません
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
                      <p className="text-xs text-[#64748b] mt-0.5">
                        対象: {action.systems.name}
                      </p>
                    )}
                  </div>
                  <Badge variant="red" className="ml-auto shrink-0">
                    {action.status === "in_progress" ? "対応中" : "未対応"}
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
