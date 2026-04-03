"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Server,
  Search,
  Users,
  AlertTriangle,
  FileCode2,
  Cloud,
  Database,
  Settings,
  Workflow,
} from "lucide-react";
import { fetchSystems } from "@/lib/people-risk/queries";
import type { SystemWithMembers } from "@/lib/people-risk/types";
import { useLocale } from "@/lib/useLocale";

const typeConfig: Record<
  string,
  {
    label: string;
    icon: React.ComponentType<{ size?: number; className?: string }>;
    color: string;
  }
> = {
  gas: { label: "GAS", icon: FileCode2, color: "text-green-400" },
  aws: { label: "AWS", icon: Cloud, color: "text-orange-400" },
  saas: { label: "SaaS", icon: Cloud, color: "text-blue-400" },
  database: { label: "DB", icon: Database, color: "text-purple-400" },
  infra: { label: "Infra", icon: Settings, color: "text-cyan-400" },
  process: { label: "Process", icon: Workflow, color: "text-pink-400" },
};

function StatusBadge({ status, locale }: { status: string | null; locale: string }) {
  switch (status) {
    case "orphaned":
      return <Badge variant="red">{locale === "ja" ? "孤立" : "Orphaned"}</Badge>;
    case "dormant":
      return <Badge variant="yellow">{locale === "ja" ? "休眠" : "Dormant"}</Badge>;
    default:
      return <Badge variant="green">{locale === "ja" ? "稼働中" : "Active"}</Badge>;
  }
}

function busFactor(system: SystemWithMembers): number {
  const owners = system.member_systems.filter(
    (ms) => ms.access_level === "owner" || ms.access_level === "admin"
  );
  return owners.length;
}

export default function SystemsPage() {
  const locale = useLocale();
  const [systems, setSystems] = useState<SystemWithMembers[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [filterType, setFilterType] = useState<string>("all");
  const [filterStatus, setFilterStatus] = useState<string>("all");

  useEffect(() => {
    fetchSystems()
      .then(setSystems)
      .finally(() => setLoading(false));
  }, []);

  const filtered = systems.filter((s) => {
    if (filterType !== "all" && s.type !== filterType) return false;
    if (filterStatus !== "all" && s.status !== filterStatus) return false;
    if (search) {
      const q = search.toLowerCase();
      return (
        s.name.toLowerCase().includes(q) ||
        (s.description ?? "").toLowerCase().includes(q)
      );
    }
    return true;
  });

  // Sort: orphaned first, then by bus factor (ascending)
  const sorted = [...filtered].sort((a, b) => {
    const statusOrder: Record<string, number> = { orphaned: 0, dormant: 1, active: 2 };
    const sa = statusOrder[a.status ?? "active"] ?? 2;
    const sb = statusOrder[b.status ?? "active"] ?? 2;
    if (sa !== sb) return sa - sb;
    return busFactor(a) - busFactor(b);
  });

  const gasCount = systems.filter((s) => s.type === "gas").length;
  const orphanedCount = systems.filter((s) => s.status === "orphaned").length;

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
      <div>
        <h1 className="text-2xl font-bold text-white flex items-center gap-2">
          <Server size={24} className="text-[#FFD700]" />
          {locale === "ja" ? "システム一覧" : "Systems"}
        </h1>
        <p className="text-sm text-[#94a3b8] mt-1">
          {locale === "ja"
            ? `${systems.length}件のシステム（GAS: ${gasCount}件、孤立: ${orphanedCount}件）`
            : `${systems.length} systems (GAS: ${gasCount}, Orphaned: ${orphanedCount})`}
        </p>
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
            placeholder={locale === "ja" ? "システム名で検索..." : "Search by system name..."}
            aria-label={locale === "ja" ? "システム名で検索" : "Search by system name"}
            className="w-full pl-10 pr-4 py-2 bg-[#111827] border border-[#1e293b] rounded-lg text-sm text-white placeholder-[#64748b] focus:border-[#FFD700]/50 focus:outline-none"
          />
        </div>
        <div className="flex gap-1 flex-wrap">
          {["all", "gas", "aws", "saas", "database", "infra"].map((t) => (
            <button
              key={t}
              onClick={() => setFilterType(t)}
              className={`px-3 py-2 text-xs rounded-lg border transition-colors ${
                filterType === t
                  ? "border-[#FFD700]/50 bg-[#FFD700]/10 text-[#FFD700]"
                  : "border-[#1e293b] text-[#94a3b8] hover:border-[#475569]"
              }`}
            >
              {t === "all" ? (locale === "ja" ? "全て" : "All") : typeConfig[t]?.label ?? t}
            </button>
          ))}
        </div>
        <div className="flex gap-1">
          {["all", "active", "orphaned", "dormant"].map((s) => (
            <button
              key={s}
              onClick={() => setFilterStatus(s)}
              className={`px-3 py-2 text-xs rounded-lg border transition-colors ${
                filterStatus === s
                  ? "border-[#FFD700]/50 bg-[#FFD700]/10 text-[#FFD700]"
                  : "border-[#1e293b] text-[#94a3b8] hover:border-[#475569]"
              }`}
            >
              {s === "all"
                ? (locale === "ja" ? "全状態" : "All")
                : s === "active"
                  ? (locale === "ja" ? "稼働中" : "Active")
                  : s === "orphaned"
                    ? (locale === "ja" ? "孤立" : "Orphaned")
                    : (locale === "ja" ? "休眠" : "Dormant")}
            </button>
          ))}
        </div>
      </div>

      {/* Systems Table */}
      <Card className="p-0 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-[#64748b] border-b border-[#1e293b] text-xs bg-[#0f1424]">
                <th scope="col" className="text-left py-3 px-4 font-medium">{locale === "ja" ? "システム名" : "System"}</th>
                <th scope="col" className="text-left py-3 px-4 font-medium">{locale === "ja" ? "種別" : "Type"}</th>
                <th scope="col" className="text-left py-3 px-4 font-medium">{locale === "ja" ? "ステータス" : "Status"}</th>
                <th scope="col" className="text-center py-3 px-4 font-medium">
                  {locale === "ja" ? "担当者数" : "Members"}
                </th>
                <th scope="col" className="text-center py-3 px-4 font-medium">
                  Bus Factor
                </th>
                <th scope="col" className="text-left py-3 px-4 font-medium">
                  {locale === "ja" ? "オーナー" : "Owners"}
                </th>
                <th scope="col" className="text-left py-3 px-4 font-medium">{locale === "ja" ? "最終更新" : "Last Updated"}</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((system) => {
                const tc = typeConfig[system.type ?? ""] ?? {
                  label: system.type ?? "-",
                  icon: Server,
                  color: "text-[#94a3b8]",
                };
                const TypeIcon = tc.icon;
                const bf = busFactor(system);
                const owners = system.member_systems
                  .filter(
                    (ms) =>
                      ms.access_level === "owner" ||
                      ms.access_level === "admin"
                  )
                  .map((ms) => ms.members);
                return (
                  <tr
                    key={system.id}
                    className={`border-b border-[#1e293b]/50 hover:bg-[#1a2035]/50 ${
                      system.status === "orphaned"
                        ? "bg-red-500/[0.02]"
                        : ""
                    }`}
                  >
                    <td className="py-3 px-4">
                      <div>
                        <p className="text-white font-medium">{system.name}</p>
                        {system.description && (
                          <p className="text-xs text-[#64748b] mt-0.5 line-clamp-1">
                            {system.description}
                          </p>
                        )}
                      </div>
                    </td>
                    <td className="py-3 px-4">
                      <span
                        className={`flex items-center gap-1.5 text-xs ${tc.color}`}
                      >
                        <TypeIcon size={14} />
                        {tc.label}
                      </span>
                    </td>
                    <td className="py-3 px-4">
                      <StatusBadge status={system.status} locale={locale} />
                    </td>
                    <td className="py-3 px-4 text-center">
                      <span className="text-white">
                        {system.member_systems.length}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-center">
                      <span
                        className={`inline-flex items-center gap-1 font-semibold ${
                          bf <= 1
                            ? "text-red-400"
                            : bf === 2
                              ? "text-yellow-400"
                              : "text-emerald-400"
                        }`}
                      >
                        {bf <= 1 && <AlertTriangle size={12} />}
                        {bf}
                      </span>
                    </td>
                    <td className="py-3 px-4">
                      <div className="space-y-0.5">
                        {owners.slice(0, 2).map((m) => (
                          <Link
                            key={m.id}
                            href={`/people-risk/members/${m.id}`}
                            className="flex items-center gap-1 text-xs text-[#94a3b8] hover:text-[#FFD700] transition-colors"
                          >
                            <Users size={10} />
                            <span>{m.name}</span>
                            {m.status === "left" && (
                              <Badge variant="red" className="text-[10px] px-1.5 py-0">
                                {locale === "ja" ? "退職" : "Left"}
                              </Badge>
                            )}
                          </Link>
                        ))}
                        {owners.length > 2 && (
                          <span className="text-xs text-[#64748b]">
                            +{owners.length - 2}{locale === "ja" ? "名" : " more"}
                          </span>
                        )}
                        {owners.length === 0 && (
                          <span className="text-xs text-red-400">{locale === "ja" ? "なし" : "None"}</span>
                        )}
                      </div>
                    </td>
                    <td className="py-3 px-4 text-xs text-[#64748b]">
                      {system.last_updated
                        ? new Date(system.last_updated).toLocaleDateString(
                            locale === "ja" ? "ja-JP" : "en-US"
                          )
                        : "-"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {sorted.length === 0 && (
          <div className="p-8 text-center text-[#64748b]">
            {locale === "ja" ? "該当するシステムがありません" : "No systems found."}
          </div>
        )}
      </Card>
    </div>
  );
}
