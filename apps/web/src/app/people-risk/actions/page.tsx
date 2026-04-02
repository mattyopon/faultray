"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useEffect, useState, useCallback } from "react";
import {
  CheckCircle2,
  Clock,
  Loader2,
  AlertTriangle,
  Info,
  TrendingDown,
  ArrowRight,
} from "lucide-react";
import { fetchActions, updateActionStatus } from "@/lib/people-risk/queries";
import type { ActionWithSystem } from "@/lib/people-risk/types";

const priorityConfig: Record<
  string,
  {
    label: string;
    icon: React.ComponentType<{ size?: number; className?: string }>;
    badgeVariant: "red" | "yellow" | "default";
    bgClass: string;
  }
> = {
  critical: {
    label: "緊急",
    icon: AlertTriangle,
    badgeVariant: "red",
    bgClass: "border-red-500/20 bg-red-500/[0.03]",
  },
  warning: {
    label: "注意",
    icon: Clock,
    badgeVariant: "yellow",
    bgClass: "border-yellow-500/20 bg-yellow-500/[0.03]",
  },
  info: {
    label: "情報",
    icon: Info,
    badgeVariant: "default",
    bgClass: "border-[#1e293b]",
  },
};

const statusLabels: Record<string, string> = {
  pending: "未対応",
  in_progress: "対応中",
  done: "完了",
};

export default function ActionsPage() {
  const [actions, setActions] = useState<ActionWithSystem[]>([]);
  const [loading, setLoading] = useState(true);
  const [updating, setUpdating] = useState<string | null>(null);
  const [filterStatus, setFilterStatus] = useState<string>("all");

  useEffect(() => {
    fetchActions()
      .then(setActions)
      .finally(() => setLoading(false));
  }, []);

  const handleStatusChange = useCallback(
    async (id: string, newStatus: "pending" | "in_progress" | "done") => {
      setUpdating(id);
      try {
        await updateActionStatus(id, newStatus);
        setActions((prev) =>
          prev.map((a) => (a.id === id ? { ...a, status: newStatus } : a))
        );
      } catch (e) {
        console.error("Failed to update action status:", e);
      } finally {
        setUpdating(null);
      }
    },
    []
  );

  const filtered =
    filterStatus === "all"
      ? actions
      : actions.filter((a) => a.status === filterStatus);

  const pendingCount = actions.filter((a) => a.status === "pending").length;
  const inProgressCount = actions.filter(
    (a) => a.status === "in_progress"
  ).length;
  const doneCount = actions.filter((a) => a.status === "done").length;
  const totalReduction = actions
    .filter((a) => a.status === "done")
    .reduce((sum, a) => sum + (a.risk_reduction ?? 0), 0);

  if (loading) {
    return (
      <div className="p-6 md:p-10 max-w-5xl mx-auto">
        <div className="animate-pulse space-y-4">
          <div className="h-8 w-48 bg-[#1e293b] rounded" />
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-24 bg-[#1e293b] rounded-2xl" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 md:p-10 max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white flex items-center gap-2">
          <CheckCircle2 size={24} className="text-[#FFD700]" />
          改善アクション
        </h1>
        <p className="text-sm text-[#94a3b8] mt-1">
          属人化リスクを低減するための対応アクション一覧
        </p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Card className="p-4 text-center">
          <p className="text-2xl font-bold text-red-400">{pendingCount}</p>
          <p className="text-xs text-[#64748b]">未対応</p>
        </Card>
        <Card className="p-4 text-center">
          <p className="text-2xl font-bold text-yellow-400">{inProgressCount}</p>
          <p className="text-xs text-[#64748b]">対応中</p>
        </Card>
        <Card className="p-4 text-center">
          <p className="text-2xl font-bold text-emerald-400">{doneCount}</p>
          <p className="text-xs text-[#64748b]">完了</p>
        </Card>
        <Card className="p-4 text-center">
          <p className="text-2xl font-bold text-[#FFD700]">
            -{totalReduction}%
          </p>
          <p className="text-xs text-[#64748b]">リスク低減</p>
        </Card>
      </div>

      {/* Filters */}
      <div className="flex gap-1">
        {["all", "pending", "in_progress", "done"].map((s) => (
          <button
            key={s}
            onClick={() => setFilterStatus(s)}
            className={`px-3 py-2 text-xs rounded-lg border transition-colors ${
              filterStatus === s
                ? "border-[#FFD700]/50 bg-[#FFD700]/10 text-[#FFD700]"
                : "border-[#1e293b] text-[#94a3b8] hover:border-[#475569]"
            }`}
          >
            {s === "all" ? `全て (${actions.length})` : `${statusLabels[s]} (${actions.filter((a) => a.status === s).length})`}
          </button>
        ))}
      </div>

      {/* Action List */}
      <div className="space-y-3">
        {filtered.map((action) => {
          const pc = priorityConfig[action.priority ?? "info"] ?? priorityConfig.info;
          const PriorityIcon = pc.icon;
          const isUpdating = updating === action.id;

          return (
            <Card
              key={action.id}
              className={`p-5 border ${
                action.status === "done" ? "opacity-60" : pc.bgClass
              }`}
            >
              <div className="flex flex-col sm:flex-row sm:items-start gap-4">
                {/* Left */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <PriorityIcon size={16} className="shrink-0" />
                    <h3
                      className={`text-sm font-semibold ${
                        action.status === "done"
                          ? "text-[#64748b] line-through"
                          : "text-white"
                      }`}
                    >
                      {action.title}
                    </h3>
                    <Badge variant={pc.badgeVariant}>{pc.label}</Badge>
                  </div>
                  {action.description && (
                    <p className="text-xs text-[#94a3b8] mt-1.5">
                      {action.description}
                    </p>
                  )}
                  <div className="flex flex-wrap gap-3 mt-2 text-xs">
                    {action.systems && (
                      <span className="text-[#64748b]">
                        対象: <span className="text-[#94a3b8]">{action.systems.name}</span>
                      </span>
                    )}
                    {action.risk_reduction != null && (
                      <span className="text-[#64748b] flex items-center gap-1">
                        <TrendingDown size={12} className="text-emerald-400" />
                        リスク低減:{" "}
                        <span className="text-emerald-400 font-semibold">
                          {action.risk_reduction}%
                        </span>
                      </span>
                    )}
                  </div>
                </div>

                {/* Right: Action buttons */}
                <div className="flex items-center gap-2 shrink-0">
                  {action.status === "pending" && (
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() =>
                        handleStatusChange(action.id, "in_progress")
                      }
                      disabled={isUpdating}
                    >
                      {isUpdating ? (
                        <Loader2 size={14} className="animate-spin" />
                      ) : (
                        <ArrowRight size={14} />
                      )}
                      対応する
                    </Button>
                  )}
                  {action.status === "in_progress" && (
                    <Button
                      size="sm"
                      onClick={() => handleStatusChange(action.id, "done")}
                      disabled={isUpdating}
                    >
                      {isUpdating ? (
                        <Loader2 size={14} className="animate-spin" />
                      ) : (
                        <CheckCircle2 size={14} />
                      )}
                      完了
                    </Button>
                  )}
                  {action.status === "done" && (
                    <Badge variant="green">
                      <CheckCircle2 size={12} />
                      完了済み
                    </Badge>
                  )}
                </div>
              </div>
            </Card>
          );
        })}

        {filtered.length === 0 && (
          <Card className="p-8 text-center">
            <p className="text-[#64748b]">該当するアクションがありません</p>
          </Card>
        )}
      </div>
    </div>
  );
}
