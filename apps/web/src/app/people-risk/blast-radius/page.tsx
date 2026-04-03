"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useEffect, useState, Suspense } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
  Zap,
  AlertTriangle,
  Server,
  Users,
  ArrowRight,
  Shield,
  XCircle,
  ChevronDown,
} from "lucide-react";
import { fetchMembers } from "@/lib/people-risk/queries";
import type { MemberWithSystems } from "@/lib/people-risk/types";

function impactLevel(ms: MemberWithSystems["member_systems"][0]) {
  if (ms.is_sole_owner) return "high";
  if (ms.access_level === "owner" || ms.access_level === "admin")
    return "medium";
  return "low";
}

const impactLabels: Record<string, { label: string; color: string }> = {
  high: { label: "高", color: "text-red-400 bg-red-500/10" },
  medium: { label: "中", color: "text-yellow-400 bg-yellow-500/10" },
  low: { label: "低", color: "text-emerald-400 bg-emerald-500/10" },
};

function BlastRadiusContent() {
  const searchParams = useSearchParams();
  const preselectedMember = searchParams.get("member");

  const [members, setMembers] = useState<MemberWithSystems[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string>(
    preselectedMember ?? ""
  );

  useEffect(() => {
    fetchMembers()
      .then((data) => {
        setMembers(data);
        if (preselectedMember) {
          setSelectedId(preselectedMember);
        }
      })
      .finally(() => setLoading(false));
  }, [preselectedMember]);

  const selectedMember = members.find((m) => m.id === selectedId) ?? null;

  const affectedSystems = selectedMember
    ? selectedMember.member_systems
        .map((ms) => ({
          ...ms,
          impact: impactLevel(ms),
        }))
        .sort((a, b) => {
          const order: Record<string, number> = { high: 0, medium: 1, low: 2 };
          return (order[a.impact] ?? 3) - (order[b.impact] ?? 3);
        })
    : [];

  const highCount = affectedSystems.filter((s) => s.impact === "high").length;
  const mediumCount = affectedSystems.filter(
    (s) => s.impact === "medium"
  ).length;

  if (loading) {
    return (
      <div className="p-6 md:p-10 max-w-5xl mx-auto">
        <div className="animate-pulse space-y-4">
          <div className="h-8 w-64 bg-[#1e293b] rounded" />
          <div className="h-16 bg-[#1e293b] rounded-2xl" />
          <div className="h-48 bg-[#1e293b] rounded-2xl" />
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 md:p-10 max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white flex items-center gap-2">
          <Zap size={24} className="text-[#FFD700]" />
          ブラストレディウス・シミュレーター
        </h1>
        <p className="text-sm text-[#94a3b8] mt-1">
          「この人が退職したら何が壊れるか」をシミュレーションします
        </p>
      </div>

      {/* Member Selector */}
      <Card className="p-6">
        <label className="block text-xs text-[#64748b] uppercase tracking-wider mb-2">
          退職をシミュレーションするメンバーを選択
        </label>
        <div className="relative">
          <select
            value={selectedId}
            onChange={(e) => setSelectedId(e.target.value)}
            aria-label="メンバーを選択"
            className="w-full appearance-none bg-[#0f1424] border border-[#1e293b] rounded-lg px-4 py-3 text-white text-sm focus:border-[#FFD700]/50 focus:outline-none cursor-pointer"
          >
            <option value="">-- メンバーを選択 --</option>
            {members
              .filter((m) => m.status === "active")
              .map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name}（{m.department} / {m.role}）- 管理システム{" "}
                  {m.member_systems.length}件
                </option>
              ))}
          </select>
          <ChevronDown
            size={16}
            className="absolute right-4 top-1/2 -translate-y-1/2 text-[#64748b] pointer-events-none"
          />
        </div>
      </Card>

      {/* Results */}
      {selectedMember && (
        <>
          {/* Summary Banner */}
          <div
            className={`p-5 rounded-xl border ${
              highCount > 0
                ? "bg-red-500/5 border-red-500/20"
                : mediumCount > 0
                  ? "bg-yellow-500/5 border-yellow-500/20"
                  : "bg-emerald-500/5 border-emerald-500/20"
            }`}
          >
            <div className="flex items-start gap-3">
              {highCount > 0 ? (
                <XCircle size={20} className="text-red-400 shrink-0 mt-0.5" />
              ) : (
                <Shield
                  size={20}
                  className="text-emerald-400 shrink-0 mt-0.5"
                />
              )}
              <div>
                <p className="text-white font-semibold">
                  {selectedMember.name}が退職した場合の影響
                </p>
                <div className="flex flex-wrap gap-4 mt-2 text-xs">
                  <span className="text-[#94a3b8]">
                    影響システム:{" "}
                    <span className="text-white font-semibold">
                      {affectedSystems.length}件
                    </span>
                  </span>
                  {highCount > 0 && (
                    <span className="text-red-400 font-semibold">
                      影響度・高: {highCount}件
                    </span>
                  )}
                  {mediumCount > 0 && (
                    <span className="text-yellow-400 font-semibold">
                      影響度・中: {mediumCount}件
                    </span>
                  )}
                </div>
                {highCount > 0 && (
                  <p className="text-xs text-[#94a3b8] mt-2">
                    この人物は{highCount}
                    件のシステムで唯一の管理者です。退職により管理不能になる可能性があります。
                  </p>
                )}
              </div>
            </div>
          </div>

          {/* Affected Systems */}
          <Card className="p-6">
            <h2 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
              <AlertTriangle size={16} className="text-[#FFD700]" />
              影響を受けるシステム
            </h2>
            <div className="space-y-3">
              {affectedSystems.map((ms) => {
                const system = ms.systems;
                const impact = impactLabels[ms.impact];
                return (
                  <div
                    key={ms.id}
                    className={`flex items-center gap-4 p-4 rounded-lg border ${
                      ms.impact === "high"
                        ? "border-red-500/20 bg-red-500/[0.03]"
                        : ms.impact === "medium"
                          ? "border-yellow-500/20 bg-yellow-500/[0.03]"
                          : "border-[#1e293b]"
                    }`}
                  >
                    <div
                      className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${impact.color}`}
                    >
                      <Server size={16} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <p className="text-sm font-medium text-white">
                          {system.name}
                        </p>
                        <Badge variant="default" className="text-[10px]">
                          {system.type?.toUpperCase()}
                        </Badge>
                      </div>
                      <p className="text-xs text-[#64748b] mt-0.5">
                        権限: {ms.access_level}
                        {ms.is_sole_owner && " (唯一の管理者)"}
                        {ms.notes && ` - ${ms.notes}`}
                      </p>
                    </div>
                    <div className="shrink-0 text-right">
                      <span
                        className={`inline-block px-2 py-1 rounded text-xs font-semibold ${impact.color}`}
                      >
                        影響度: {impact.label}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </Card>

          {/* Recommendations */}
          {highCount > 0 && (
            <Card className="p-6">
              <h2 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
                <Shield size={16} className="text-emerald-400" />
                推奨アクション
              </h2>
              <div className="space-y-2">
                {affectedSystems
                  .filter((ms) => ms.impact === "high")
                  .map((ms) => (
                    <div
                      key={ms.id}
                      className="flex items-center gap-3 p-3 rounded-lg bg-[#1e293b]/30"
                    >
                      <ArrowRight
                        size={14}
                        className="text-[#FFD700] shrink-0"
                      />
                      <p className="text-xs text-[#94a3b8]">
                        <span className="text-white font-medium">
                          {ms.systems.name}
                        </span>
                        のバックアップ管理者を設定してください
                      </p>
                      <Link href="/people-risk/actions">
                        <Badge
                          variant="gold"
                          className="cursor-pointer shrink-0"
                        >
                          アクション作成
                        </Badge>
                      </Link>
                    </div>
                  ))}
              </div>
            </Card>
          )}
        </>
      )}

      {/* Empty state */}
      {!selectedMember && (
        <Card className="p-12 text-center">
          <Users size={32} className="mx-auto text-[#475569] mb-3" />
          <p className="text-[#64748b]">
            上のドロップダウンからメンバーを選択して、
            <br />
            退職時の影響をシミュレーションしてください
          </p>
        </Card>
      )}
    </div>
  );
}

export default function BlastRadiusPage() {
  return (
    <Suspense fallback={
      <div className="p-6 md:p-10 max-w-5xl mx-auto">
        <div className="animate-pulse space-y-4">
          <div className="h-8 w-64 bg-[#1e293b] rounded" />
          <div className="h-16 bg-[#1e293b] rounded-2xl" />
          <div className="h-48 bg-[#1e293b] rounded-2xl" />
        </div>
      </div>
    }>
      <BlastRadiusContent />
    </Suspense>
  );
}
