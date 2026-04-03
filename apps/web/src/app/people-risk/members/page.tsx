"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Users,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Search,
  ChevronRight,
} from "lucide-react";
import { fetchMembers } from "@/lib/people-risk/queries";
import { useLocale } from "@/lib/useLocale";
import type { MemberWithSystems } from "@/lib/people-risk/types";

function riskBadge(level: string | null) {
  switch (level) {
    case "critical":
      return <Badge variant="red">危険</Badge>;
    case "warning":
      return <Badge variant="yellow">注意</Badge>;
    default:
      return <Badge variant="green">安全</Badge>;
  }
}

function memberRiskLevel(member: MemberWithSystems): "critical" | "warning" | "safe" {
  const levels = member.member_systems.map((ms) => ms.risk_level);
  if (levels.includes("critical")) return "critical";
  if (levels.includes("warning")) return "warning";
  return "safe";
}

export default function MembersPage() {
  const locale = useLocale();
  const [members, setMembers] = useState<MemberWithSystems[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [filterStatus, setFilterStatus] = useState<"all" | "active" | "left">("all");

  useEffect(() => {
    fetchMembers()
      .then(setMembers)
      .finally(() => setLoading(false));
  }, []);

  const filtered = members.filter((m) => {
    if (filterStatus !== "all" && m.status !== filterStatus) return false;
    if (search) {
      const q = search.toLowerCase();
      return (
        m.name.toLowerCase().includes(q) ||
        (m.department ?? "").toLowerCase().includes(q) ||
        (m.role ?? "").toLowerCase().includes(q)
      );
    }
    return true;
  });

  // Sort: critical first, then warning, then safe
  const sorted = [...filtered].sort((a, b) => {
    const order = { critical: 0, warning: 1, safe: 2 };
    return order[memberRiskLevel(a)] - order[memberRiskLevel(b)];
  });

  if (loading) {
    return (
      <div className="p-6 md:p-10 max-w-7xl mx-auto">
        <div className="animate-pulse space-y-4">
          <div className="h-8 w-48 bg-[#1e293b] rounded" />
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-20 bg-[#1e293b] rounded-2xl" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 md:p-10 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Users size={24} className="text-[#FFD700]" />
            {locale === "ja" ? "メンバー一覧" : "Members"}
          </h1>
          <p className="text-sm text-[#94a3b8] mt-1">
            {locale === "ja" ? `${members.length}名のメンバーとシステム管理状況` : `${members.length} members and their system ownership`}
          </p>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1 max-w-sm">
          <Search
            size={16}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-[#64748b]"
          />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={locale === "ja" ? "名前・部署・役職で検索..." : "Search by name, department, role..."}
            aria-label={locale === "ja" ? "名前・部署・役職で検索" : "Search by name, department, role"}
            className="w-full pl-10 pr-4 py-2 bg-[#111827] border border-[#1e293b] rounded-lg text-sm text-white placeholder-[#64748b] focus:border-[#FFD700]/50 focus:outline-none"
          />
        </div>
        <div className="flex gap-1">
          {(["all", "active", "left"] as const).map((s) => (
            <button
              key={s}
              onClick={() => setFilterStatus(s)}
              className={`px-3 py-2 text-xs rounded-lg border transition-colors ${
                filterStatus === s
                  ? "border-[#FFD700]/50 bg-[#FFD700]/10 text-[#FFD700]"
                  : "border-[#1e293b] text-[#94a3b8] hover:border-[#475569]"
              }`}
            >
              {s === "all" ? "全員" : s === "active" ? "在籍" : "退職済み"}
            </button>
          ))}
        </div>
      </div>

      {/* Member List */}
      <div className="space-y-3">
        {sorted.map((member) => {
          const risk = memberRiskLevel(member);
          const systemCount = member.member_systems.length;
          const criticalCount = member.member_systems.filter(
            (ms) => ms.risk_level === "critical"
          ).length;

          return (
            <Link
              key={member.id}
              href={`/people-risk/members/${member.id}`}
            >
              <Card className="p-4 hover:border-[#FFD700]/30 hover:bg-[#1a2035] transition-all cursor-pointer group mb-3">
                <div className="flex items-center gap-4">
                  {/* Avatar */}
                  <div
                    className={`w-10 h-10 rounded-full flex items-center justify-center text-sm font-bold shrink-0 ${
                      member.status === "left"
                        ? "bg-[#475569]/20 text-[#64748b]"
                        : risk === "critical"
                          ? "bg-red-500/10 text-red-400"
                          : risk === "warning"
                            ? "bg-yellow-500/10 text-yellow-400"
                            : "bg-emerald-500/10 text-emerald-400"
                    }`}
                  >
                    {member.name.slice(0, 1)}
                  </div>

                  {/* Info */}
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-semibold text-white group-hover:text-[#FFD700] transition-colors">
                        {member.name}
                      </p>
                      {member.status === "left" && (
                        <Badge variant="default">退職済み</Badge>
                      )}
                    </div>
                    <p className="text-xs text-[#64748b]">
                      {member.department} / {member.role}
                    </p>
                  </div>

                  {/* Stats */}
                  <div className="hidden sm:flex items-center gap-4 text-xs">
                    <div className="text-center">
                      <p className="text-[#64748b]">{locale === "ja" ? "管理システム" : "Systems"}</p>
                      <p className="text-white font-semibold">{systemCount}</p>
                    </div>
                    {criticalCount > 0 && (
                      <div className="text-center">
                        <p className="text-[#64748b]">危険</p>
                        <p className="text-red-400 font-semibold flex items-center gap-1">
                          <AlertTriangle size={12} />
                          {criticalCount}
                        </p>
                      </div>
                    )}
                  </div>

                  {/* Risk Badge */}
                  <div className="shrink-0">{riskBadge(risk)}</div>

                  <ChevronRight
                    size={16}
                    className="text-[#475569] group-hover:text-[#FFD700] transition-colors shrink-0"
                  />
                </div>
              </Card>
            </Link>
          );
        })}

        {sorted.length === 0 && (
          <Card className="p-8 text-center">
            <p className="text-[#64748b]">{locale === "ja" ? "該当するメンバーがいません" : "No members found."}</p>
          </Card>
        )}
      </div>
    </div>
  );
}
