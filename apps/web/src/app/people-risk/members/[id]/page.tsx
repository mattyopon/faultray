"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useEffect, useState, use } from "react";
import Link from "next/link";
import {
  User,
  ArrowLeft,
  Server,
  AlertTriangle,
  Shield,
  Key,
  Eye,
  Edit3,
  Crown,
} from "lucide-react";
import { fetchMemberById } from "@/lib/people-risk/queries";
import type { MemberWithSystems } from "@/lib/people-risk/types";

const accessIcons: Record<string, React.ComponentType<{ size?: number; className?: string }>> = {
  owner: Crown,
  admin: Key,
  editor: Edit3,
  viewer: Eye,
};

const accessLabels: Record<string, string> = {
  owner: "オーナー",
  admin: "管理者",
  editor: "編集者",
  viewer: "閲覧者",
};

const systemTypeLabels: Record<string, string> = {
  gas: "Google Apps Script",
  aws: "AWS",
  saas: "SaaS",
  database: "データベース",
  infra: "インフラ",
  process: "業務プロセス",
};

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

function statusBadge(status: string | null) {
  switch (status) {
    case "orphaned":
      return <Badge variant="red">孤立</Badge>;
    case "dormant":
      return <Badge variant="yellow">休眠</Badge>;
    default:
      return <Badge variant="green">稼働中</Badge>;
  }
}

export default function MemberDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const [member, setMember] = useState<MemberWithSystems | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchMemberById(id)
      .then(setMember)
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) {
    return (
      <div className="p-6 md:p-10 max-w-5xl mx-auto">
        <div className="animate-pulse space-y-4">
          <div className="h-6 w-32 bg-[#1e293b] rounded" />
          <div className="h-32 bg-[#1e293b] rounded-2xl" />
          <div className="h-48 bg-[#1e293b] rounded-2xl" />
        </div>
      </div>
    );
  }

  if (!member) {
    return (
      <div className="p-6 md:p-10 max-w-5xl mx-auto">
        <Link
          href="/people-risk/members"
          className="text-sm text-[#94a3b8] hover:text-white flex items-center gap-1 mb-4"
        >
          <ArrowLeft size={14} />
          メンバー一覧に戻る
        </Link>
        <Card className="p-8 text-center">
          <p className="text-[#64748b]">メンバーが見つかりません</p>
        </Card>
      </div>
    );
  }

  const criticalSystems = member.member_systems.filter(
    (ms) => ms.risk_level === "critical"
  );
  const soleOwnerSystems = member.member_systems.filter(
    (ms) => ms.is_sole_owner
  );

  return (
    <div className="p-6 md:p-10 max-w-5xl mx-auto space-y-6">
      {/* Breadcrumb */}
      <Link
        href="/people-risk/members"
        className="text-sm text-[#94a3b8] hover:text-white flex items-center gap-1"
      >
        <ArrowLeft size={14} />
        メンバー一覧に戻る
      </Link>

      {/* Profile Card */}
      <Card className="p-6">
        <div className="flex flex-col sm:flex-row items-start gap-4">
          <div
            className={`w-16 h-16 rounded-full flex items-center justify-center text-xl font-bold shrink-0 ${
              member.status === "left"
                ? "bg-[#475569]/20 text-[#64748b]"
                : "bg-[#FFD700]/10 text-[#FFD700]"
            }`}
          >
            {member.name.slice(0, 1)}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className="text-xl font-bold text-white">{member.name}</h1>
              {member.status === "left" && (
                <Badge variant="red">退職済み</Badge>
              )}
            </div>
            <p className="text-sm text-[#94a3b8] mt-1">
              {member.department} / {member.role}
            </p>
            <div className="flex flex-wrap gap-4 mt-3 text-xs">
              <div>
                <span className="text-[#64748b]">管理システム: </span>
                <span className="text-white font-semibold">
                  {member.member_systems.length}件
                </span>
              </div>
              <div>
                <span className="text-[#64748b]">唯一の管理者: </span>
                <span
                  className={`font-semibold ${soleOwnerSystems.length > 0 ? "text-red-400" : "text-emerald-400"}`}
                >
                  {soleOwnerSystems.length}件
                </span>
              </div>
              <div>
                <span className="text-[#64748b]">危険レベル: </span>
                <span
                  className={`font-semibold ${criticalSystems.length > 0 ? "text-red-400" : "text-emerald-400"}`}
                >
                  {criticalSystems.length}件
                </span>
              </div>
            </div>
          </div>
          <Link href={`/people-risk/blast-radius?member=${member.id}`}>
            <Button variant="danger" size="sm">
              退職シミュレーション
            </Button>
          </Link>
        </div>
      </Card>

      {/* Warning Banner */}
      {(criticalSystems.length > 0 || member.status === "left") && (
        <div
          className={`flex items-start gap-3 p-4 rounded-xl border ${
            member.status === "left"
              ? "bg-red-500/5 border-red-500/20"
              : "bg-yellow-500/5 border-yellow-500/20"
          }`}
        >
          <AlertTriangle
            size={18}
            className={
              member.status === "left" ? "text-red-400" : "text-yellow-400"
            }
          />
          <div>
            {member.status === "left" ? (
              <>
                <p className="text-sm font-semibold text-red-400">
                  退職済みメンバーのシステムが残存しています
                </p>
                <p className="text-xs text-[#94a3b8] mt-1">
                  このメンバーが管理していたシステムの引き継ぎを確認してください。
                  特に唯一のオーナーだったシステムは孤立状態になっている可能性があります。
                </p>
              </>
            ) : (
              <>
                <p className="text-sm font-semibold text-yellow-400">
                  このメンバーは{criticalSystems.length}
                  件のシステムで唯一の管理者です
                </p>
                <p className="text-xs text-[#94a3b8] mt-1">
                  退職した場合、これらのシステムが管理不能になるリスクがあります。
                  バックアップ管理者の設定を推奨します。
                </p>
              </>
            )}
          </div>
        </div>
      )}

      {/* Systems Table */}
      <Card className="p-6">
        <h2 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
          <Server size={16} className="text-[#FFD700]" />
          担当システム一覧
        </h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-[#64748b] border-b border-[#1e293b] text-xs">
                <th scope="col" className="text-left py-3 font-medium">システム名</th>
                <th scope="col" className="text-left py-3 font-medium">種別</th>
                <th scope="col" className="text-left py-3 font-medium">権限</th>
                <th scope="col" className="text-center py-3 font-medium">唯一の管理者</th>
                <th scope="col" className="text-left py-3 font-medium">ステータス</th>
                <th scope="col" className="text-left py-3 font-medium">リスク</th>
              </tr>
            </thead>
            <tbody>
              {member.member_systems.map((ms) => {
                const system = ms.systems;
                const AccessIcon = accessIcons[ms.access_level ?? "viewer"] ?? Eye;
                return (
                  <tr
                    key={ms.id}
                    className="border-b border-[#1e293b]/50 hover:bg-[#1a2035]/50"
                  >
                    <td className="py-3">
                      <div>
                        <p className="text-white font-medium">{system.name}</p>
                        {system.description && (
                          <p className="text-xs text-[#64748b] mt-0.5 line-clamp-1">
                            {system.description}
                          </p>
                        )}
                      </div>
                    </td>
                    <td className="py-3">
                      <Badge variant="default">
                        {systemTypeLabels[system.type ?? ""] ?? system.type}
                      </Badge>
                    </td>
                    <td className="py-3">
                      <span className="flex items-center gap-1 text-[#94a3b8]">
                        <AccessIcon size={14} />
                        {accessLabels[ms.access_level ?? ""] ?? ms.access_level}
                      </span>
                    </td>
                    <td className="py-3 text-center">
                      {ms.is_sole_owner ? (
                        <span className="text-red-400 font-semibold">Yes</span>
                      ) : (
                        <span className="text-[#64748b]">-</span>
                      )}
                    </td>
                    <td className="py-3">{statusBadge(system.status)}</td>
                    <td className="py-3">{riskBadge(ms.risk_level)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {member.member_systems.length === 0 && (
          <p className="text-sm text-[#64748b] text-center py-4">
            担当システムがありません
          </p>
        )}
      </Card>

      {/* Notes */}
      {member.member_systems.some((ms) => ms.notes) && (
        <Card className="p-6">
          <h2 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
            <Shield size={16} className="text-[#FFD700]" />
            備考・リスク詳細
          </h2>
          <div className="space-y-2">
            {member.member_systems
              .filter((ms) => ms.notes)
              .map((ms) => (
                <div
                  key={ms.id}
                  className={`p-3 rounded-lg text-xs ${
                    ms.risk_level === "critical"
                      ? "bg-red-500/5 border border-red-500/10"
                      : ms.risk_level === "warning"
                        ? "bg-yellow-500/5 border border-yellow-500/10"
                        : "bg-[#1e293b]/30 border border-[#1e293b]"
                  }`}
                >
                  <p className="text-[#94a3b8]">
                    <span className="text-white font-medium">
                      {ms.systems.name}:
                    </span>{" "}
                    {ms.notes}
                  </p>
                </div>
              ))}
          </div>
        </Card>
      )}
    </div>
  );
}
