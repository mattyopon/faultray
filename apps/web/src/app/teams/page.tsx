"use client";

import { useState, useEffect, useCallback } from "react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Users,
  Plus,
  Mail,
  Building2,
  Loader2,
  CheckCircle2,
  Clock,
  AlertCircle,
  XCircle,
  Trash2,
} from "lucide-react";
import { useAuth } from "@/components/auth-provider";
import { useLocale } from "@/lib/useLocale";

// ── 型定義 ──────────────────────────────────────────────────────────────────

interface OrgMember {
  id: string;
  org_id: string;
  user_id: string | null;
  email: string;
  role: string;
  status: string;
  invited_at: string;
  joined_at: string | null;
}

interface Organization {
  id: string;
  name: string;
  plan: string;
  created_at: string;
}

interface Task {
  id: string;
  org_id: string;
  title: string;
  description: string;
  status: string;
  priority: string;
  assignee_id: string | null;
  created_by: string;
  due_date: string | null;
  source: string;
  source_id: string;
  created_at: string;
  updated_at: string;
}

// ── ユーティリティ ──────────────────────────────────────────────────────────

const PRIORITY_CONFIG: Record<
  string,
  { label: string; variant: "red" | "yellow" | "default" | "green" | "gold" }
> = {
  critical: { label: "Critical", variant: "red" },
  high: { label: "High", variant: "yellow" },
  medium: { label: "Medium", variant: "default" },
  low: { label: "Low", variant: "green" },
};

const STATUS_COLUMNS = [
  { key: "open", label: "Open", icon: Clock, color: "#94a3b8" },
  { key: "in_progress", label: "In Progress", icon: Loader2, color: "#3b82f6" },
  { key: "done", label: "Done", icon: CheckCircle2, color: "#10b981" },
  { key: "blocked", label: "Blocked", icon: XCircle, color: "#ef4444" },
] as const;

const ROLE_LABELS: Record<string, string> = {
  owner: "Owner",
  admin: "Admin",
  member: "Member",
  viewer: "Viewer",
};

function avatarText(email: string): string {
  return email.slice(0, 2).toUpperCase();
}

// ── サブコンポーネント ───────────────────────────────────────────────────────

function RoleBadge({ role }: { role: string }) {
  const variantMap: Record<string, "gold" | "yellow" | "default" | "green"> = {
    owner: "gold",
    admin: "yellow",
    member: "default",
    viewer: "green",
  };
  return (
    <Badge variant={variantMap[role] ?? "default"}>
      {ROLE_LABELS[role] ?? role}
    </Badge>
  );
}

function StatusBadge({ status }: { status: string }) {
  const variantMap: Record<string, "green" | "default" | "red" | "yellow" | "gold"> = {
    active: "green",
    pending: "yellow",
    removed: "red",
  };
  return (
    <Badge variant={variantMap[status] ?? "default"}>
      {status.charAt(0).toUpperCase() + status.slice(1)}
    </Badge>
  );
}

function TaskCard({
  task,
  members,
  onStatusChange,
  onDelete,
}: {
  task: Task;
  members: OrgMember[];
  onStatusChange: (id: string, status: string) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
}) {
  const locale = useLocale();
  const assignee = members.find((m) => m.id === task.assignee_id);
  const priorityCfg = PRIORITY_CONFIG[task.priority] ?? PRIORITY_CONFIG.medium;
  const [deleting, setDeleting] = useState(false);

  const handleDelete = async () => {
    setDeleting(true);
    await onDelete(task.id);
    setDeleting(false);
  };

  return (
    <div className="bg-[#0a0e1a] border border-[#1e293b] rounded-xl p-4 space-y-3 hover:border-[#334155] transition-colors">
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm font-semibold leading-tight flex-1">{task.title}</p>
        <button
          onClick={handleDelete}
          disabled={deleting}
          className="text-[#475569] hover:text-red-400 transition-colors shrink-0 disabled:opacity-50"
          aria-label={locale === "ja" ? "タスクを削除" : "Delete task"}
        >
          {deleting ? (
            <Loader2 size={14} className="animate-spin" />
          ) : (
            <Trash2 size={14} />
          )}
        </button>
      </div>

      {task.description && (
        <p className="text-xs text-[#64748b] leading-relaxed line-clamp-2">
          {task.description}
        </p>
      )}

      <div className="flex items-center justify-between">
        <Badge variant={priorityCfg.variant}>{priorityCfg.label}</Badge>
        {task.due_date && (
          <p className="text-xs text-[#475569]">
            {new Date(task.due_date).toLocaleDateString()}
          </p>
        )}
      </div>

      {assignee && (
        <div className="flex items-center gap-2">
          <div className="w-5 h-5 rounded-full bg-[#1e293b] flex items-center justify-center text-[10px] font-bold text-[#94a3b8] shrink-0">
            {avatarText(assignee.email)}
          </div>
          <p className="text-xs text-[#64748b] truncate">{assignee.email}</p>
        </div>
      )}

      {task.source && (
        <p className="text-[10px] text-[#475569] font-mono">
          src: {task.source}
          {task.source_id ? ` #${task.source_id.slice(0, 8)}` : ""}
        </p>
      )}

      {/* ステータス変更セレクト */}
      <select
        className="w-full bg-[#111827] border border-[#1e293b] text-xs text-[#94a3b8] rounded-lg px-2 py-1.5 focus:outline-none focus:border-[#FFD700]/40"
        value={task.status}
        onChange={(e) => onStatusChange(task.id, e.target.value)}
        aria-label={locale === "ja" ? "タスクのステータスを変更" : "Change task status"}
      >
        {STATUS_COLUMNS.map((s) => (
          <option key={s.key} value={s.key}>
            {s.label}
          </option>
        ))}
      </select>
    </div>
  );
}

// ── メインページ ─────────────────────────────────────────────────────────────

export default function TeamsPage() {
  const { user } = useAuth();
  const locale = useLocale();

  // 組織・メンバー
  const [org, setOrg] = useState<Organization | null>(null);
  const [members, setMembers] = useState<OrgMember[]>([]);
  const [orgLoading, setOrgLoading] = useState(true);
  const [orgError, setOrgError] = useState<string | null>(null);

  // 組織作成フォーム
  const [creatingOrg, setCreatingOrg] = useState(false);
  const [orgName, setOrgName] = useState("");
  const [orgCreateLoading, setOrgCreateLoading] = useState(false);

  // 招待フォーム
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("member");
  const [inviteLoading, setInviteLoading] = useState(false);
  const [inviteMsg, setInviteMsg] = useState<{ type: "success" | "error"; text: string } | null>(null);

  // タスク
  const [tasks, setTasks] = useState<Task[]>([]);
  const [tasksLoading, setTasksLoading] = useState(false);

  // タスク作成フォーム
  const [showTaskForm, setShowTaskForm] = useState(false);
  const [newTaskTitle, setNewTaskTitle] = useState("");
  const [newTaskDesc, setNewTaskDesc] = useState("");
  const [newTaskPriority, setNewTaskPriority] = useState("medium");
  const [newTaskAssignee, setNewTaskAssignee] = useState("");
  const [newTaskDue, setNewTaskDue] = useState("");
  const [taskCreateLoading, setTaskCreateLoading] = useState(false);

  // ── データ取得 ─────────────────────────────────────────────────────────────

  const fetchOrgAndMembers = useCallback(async () => {
    setOrgLoading(true);
    setOrgError(null);
    try {
      const res = await fetch("/api/org/members");
      if (!res.ok) {
        const err = (await res.json()) as { error?: string };
        setOrgError(err.error ?? (locale === "ja" ? "組織の読み込みに失敗しました" : "Failed to load organization"));
        return;
      }
      const data = (await res.json()) as { org: Organization | null; members: OrgMember[] };
      setOrg(data.org);
      setMembers(data.members ?? []);
    } catch {
      setOrgError(locale === "ja" ? "ネットワークエラー" : "Network error");
    } finally {
      setOrgLoading(false);
    }
  }, []);

  const fetchTasks = useCallback(async () => {
    setTasksLoading(true);
    try {
      const res = await fetch("/api/tasks");
      if (res.ok) {
        const data = (await res.json()) as { tasks: Task[] };
        setTasks(data.tasks ?? []);
      }
    } finally {
      setTasksLoading(false);
    }
  }, []);

  useEffect(() => {
    if (user) {
      void fetchOrgAndMembers();
      void fetchTasks();
    }
  }, [user, fetchOrgAndMembers, fetchTasks]);

  // ── 操作ハンドラ ───────────────────────────────────────────────────────────

  const handleCreateOrg = async () => {
    if (!orgName.trim()) return;
    setOrgCreateLoading(true);
    try {
      const res = await fetch("/api/org/create", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: orgName.trim() }),
      });
      if (res.ok) {
        setOrgName("");
        setCreatingOrg(false);
        await fetchOrgAndMembers();
      }
    } finally {
      setOrgCreateLoading(false);
    }
  };

  const handleInvite = async () => {
    if (!inviteEmail.trim() || !org) return;
    setInviteLoading(true);
    setInviteMsg(null);
    try {
      const res = await fetch("/api/org/invite", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ org_id: org.id, email: inviteEmail.trim(), role: inviteRole }),
      });
      const data = (await res.json()) as { error?: string };
      if (res.ok) {
        setInviteMsg({ type: "success", text: `Invitation sent to ${inviteEmail}` });
        setInviteEmail("");
        await fetchOrgAndMembers();
      } else {
        setInviteMsg({ type: "error", text: data.error ?? (locale === "ja" ? "招待に失敗しました" : "Failed to invite") });
      }
    } catch {
      setInviteMsg({ type: "error", text: locale === "ja" ? "ネットワークエラー" : "Network error" });
    } finally {
      setInviteLoading(false);
    }
  };

  const handleCreateTask = async () => {
    if (!newTaskTitle.trim()) return;
    setTaskCreateLoading(true);
    try {
      const body: Record<string, string> = {
        title: newTaskTitle.trim(),
        description: newTaskDesc,
        priority: newTaskPriority,
      };
      if (newTaskAssignee) body.assignee_id = newTaskAssignee;
      if (newTaskDue) body.due_date = newTaskDue;

      const res = await fetch("/api/tasks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (res.ok) {
        setNewTaskTitle("");
        setNewTaskDesc("");
        setNewTaskPriority("medium");
        setNewTaskAssignee("");
        setNewTaskDue("");
        setShowTaskForm(false);
        await fetchTasks();
      }
    } finally {
      setTaskCreateLoading(false);
    }
  };

  const handleStatusChange = async (taskId: string, status: string) => {
    const res = await fetch(`/api/tasks/${taskId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    });
    if (res.ok) {
      setTasks((prev) =>
        prev.map((t) => (t.id === taskId ? { ...t, status, updated_at: new Date().toISOString() } : t))
      );
    }
  };

  const handleDeleteTask = async (taskId: string) => {
    const res = await fetch(`/api/tasks/${taskId}`, { method: "DELETE" });
    if (res.ok) {
      setTasks((prev) => prev.filter((t) => t.id !== taskId));
    }
  };

  // ── ログイン前 ─────────────────────────────────────────────────────────────

  if (!user) {
    return (
      <div className="max-w-[1200px] mx-auto px-6 py-20 text-center">
        <Users size={40} className="text-[#FFD700] mx-auto mb-4" />
        <h1 className="text-2xl font-bold mb-2">{locale === "ja" ? "組織・タスク" : "Organization & Tasks"}</h1>
        <p className="text-[#64748b]">{locale === "ja" ? "組織とタスクを管理するにはサインインしてください。" : "Sign in to manage your organization and tasks."}</p>
      </div>
    );
  }

  // ── ロード中 ───────────────────────────────────────────────────────────────

  if (orgLoading) {
    return (
      <div className="max-w-[1200px] mx-auto px-6 py-20 flex items-center justify-center gap-3 text-[#64748b]">
        <Loader2 size={20} className="animate-spin" />
        <span>{locale === "ja" ? "組織を読み込み中..." : "Loading organization..."}</span>
      </div>
    );
  }

  // ── 組織未作成 ─────────────────────────────────────────────────────────────

  if (!org) {
    return (
      <div className="max-w-[1200px] mx-auto px-6 py-20">
        <div className="text-center mb-10">
          <Building2 size={40} className="text-[#FFD700] mx-auto mb-4" />
          <h1 className="text-2xl font-bold mb-2">Create Your Organization</h1>
          <p className="text-[#64748b]">Set up an organization to invite members and manage tasks.</p>
        </div>

        {orgError && (
          <div role="alert" className="mb-6 p-4 bg-red-500/10 border border-red-500/20 rounded-xl text-red-400 text-sm flex items-center gap-2">
            <AlertCircle size={16} />
            {orgError}
          </div>
        )}

        {creatingOrg ? (
          <Card className="max-w-md mx-auto">
            <p className="text-sm font-semibold text-[#FFD700] mb-4">New Organization</p>
            <input
              type="text"
              placeholder={locale === "ja" ? "組織名" : "Organization name"}
              aria-label={locale === "ja" ? "組織名" : "Organization name"}
              value={orgName}
              onChange={(e) => setOrgName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && void handleCreateOrg()}
              className="w-full bg-[#0a0e1a] border border-[#1e293b] rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:border-[#FFD700]/40 mb-4"
              autoFocus
            />
            <div className="flex gap-3">
              <Button
                onClick={() => void handleCreateOrg()}
                disabled={orgCreateLoading || !orgName.trim()}
                className="flex-1"
              >
                {orgCreateLoading ? <Loader2 size={16} className="animate-spin" /> : <Plus size={16} />}
                Create
              </Button>
              <Button
                variant="secondary"
                onClick={() => { setCreatingOrg(false); setOrgName(""); }}
              >
                Cancel
              </Button>
            </div>
          </Card>
        ) : (
          <div className="text-center">
            <Button onClick={() => setCreatingOrg(true)}>
              <Plus size={16} />
              Create Organization
            </Button>
          </div>
        )}
      </div>
    );
  }

  // ── メイン UI ──────────────────────────────────────────────────────────────

  const activeMembers = members.filter((m) => m.status === "active");

  return (
    <div className="max-w-[1200px] mx-auto px-6 py-10 space-y-8">

      {/* ヘッダー */}
      <div>
        <h1 className="text-2xl font-bold mb-1 flex items-center gap-3">
          <Building2 size={24} className="text-[#FFD700]" />
          {org.name}
        </h1>
        <div className="flex items-center gap-3 mt-1">
          <Badge variant={org.plan === "free" ? "default" : "gold"}>
            {org.plan.toUpperCase()}
          </Badge>
          <span className="text-[#475569] text-xs">
            {members.length} member{members.length !== 1 ? "s" : ""}
          </span>
        </div>
      </div>

      {/* ── メンバー管理 ─────────────────────────────────────────────────── */}
      <Card>
        <div className="flex items-center justify-between mb-6">
          <p className="text-sm font-semibold text-[#FFD700] flex items-center gap-2">
            <Users size={14} />
            Members
          </p>
        </div>

        {/* メンバー一覧 */}
        <div className="space-y-2 mb-6">
          {members.length === 0 && (
            <p className="text-sm text-[#475569] text-center py-4">No members yet.</p>
          )}
          {members.map((member) => {
            // FLOW-08: Determine if current user can change this member's role
            const currentMember = members.find((m) => m.user_id === user?.id);
            const canChangeRole = currentMember?.role === "owner" && member.user_id !== user?.id;
            return (
            <div
              key={member.id}
              className="flex items-center gap-4 bg-[#0a0e1a] rounded-xl px-4 py-3"
            >
              <div className="w-8 h-8 rounded-full bg-[#1e293b] flex items-center justify-center text-xs font-bold text-[#94a3b8] shrink-0">
                {avatarText(member.email)}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold truncate">{member.email}</p>
                <p className="text-xs text-[#64748b]">
                  {member.status === "active" && member.joined_at
                    ? `Joined ${new Date(member.joined_at).toLocaleDateString()}`
                    : `Invited ${new Date(member.invited_at).toLocaleDateString()}`}
                </p>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                {/* FLOW-08: Owner can change roles inline */}
                {canChangeRole ? (
                  <select
                    value={member.role}
                    onChange={async (e) => {
                      const newRole = e.target.value;
                      try {
                        await fetch(`/api/org/members/${member.id}`, {
                          method: "PATCH",
                          headers: { "Content-Type": "application/json" },
                          body: JSON.stringify({ role: newRole }),
                        });
                        setMembers((prev) =>
                          prev.map((m) => m.id === member.id ? { ...m, role: newRole } : m)
                        );
                      } catch {
                        // Non-critical — role badge stays as-is
                      }
                    }}
                    className="text-xs bg-[#1e293b] border border-[#334155] text-[#94a3b8] rounded-md px-2 py-1 focus:outline-none focus:border-[#FFD700]/50"
                    aria-label={locale === "ja" ? `${member.email} の役割を変更` : `Change role for ${member.email}`}
                  >
                    <option value="admin">Admin</option>
                    <option value="member">Member</option>
                    <option value="viewer">Viewer</option>
                  </select>
                ) : (
                  <RoleBadge role={member.role} />
                )}
                <StatusBadge status={member.status} />
              </div>
            </div>
            );
          })}
        </div>

        {/* 招待フォーム */}
        <div className="border-t border-[#1e293b] pt-6">
          <p className="text-xs text-[#64748b] uppercase tracking-wider mb-4 flex items-center gap-2">
            <Mail size={12} />
            Invite Member
          </p>
          <div className="flex flex-col sm:flex-row gap-3">
            <input
              type="email"
              placeholder="email@example.com"
              aria-label={locale === "ja" ? "招待するメールアドレス" : "Invite email address"}
              value={inviteEmail}
              onChange={(e) => setInviteEmail(e.target.value)}
              className="flex-1 bg-[#0a0e1a] border border-[#1e293b] rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:border-[#FFD700]/40"
            />
            <select
              value={inviteRole}
              onChange={(e) => setInviteRole(e.target.value)}
              aria-label={locale === "ja" ? "招待する役割" : "Invite role"}
              className="bg-[#0a0e1a] border border-[#1e293b] rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:border-[#FFD700]/40"
            >
              <option value="admin">Admin</option>
              <option value="member">Member</option>
              <option value="viewer">Viewer</option>
            </select>
            <Button
              onClick={() => void handleInvite()}
              disabled={inviteLoading || !inviteEmail.trim()}
              size="md"
            >
              {inviteLoading ? <Loader2 size={16} className="animate-spin" /> : <Plus size={16} />}
              Invite
            </Button>
          </div>
          {inviteMsg && (
            <div
              role="alert"
              className={`mt-3 p-3 rounded-lg text-sm flex items-center gap-2 ${
                inviteMsg.type === "success"
                  ? "bg-emerald-500/10 text-emerald-400"
                  : "bg-red-500/10 text-red-400"
              }`}
            >
              {inviteMsg.type === "success" ? (
                <CheckCircle2 size={14} />
              ) : (
                <AlertCircle size={14} />
              )}
              {inviteMsg.text}
            </div>
          )}
        </div>
      </Card>

      {/* ── タスクボード ──────────────────────────────────────────────────── */}
      <Card>
        <div className="flex items-center justify-between mb-6">
          <p className="text-sm font-semibold text-[#FFD700]">Task Board</p>
          <Button size="sm" onClick={() => setShowTaskForm((v) => !v)}>
            <Plus size={14} />
            New Task
          </Button>
        </div>

        {/* タスク作成フォーム */}
        {showTaskForm && (
          <div className="mb-6 bg-[#0a0e1a] border border-[#1e293b] rounded-xl p-5 space-y-4">
            <p className="text-sm font-semibold text-[#94a3b8]">Create Task</p>
            <input
              type="text"
              placeholder={locale === "ja" ? "タスクタイトル *" : "Task title *"}
              aria-label={locale === "ja" ? "タスクタイトル（必須）" : "Task title (required)"}
              value={newTaskTitle}
              onChange={(e) => setNewTaskTitle(e.target.value)}
              className="w-full bg-[#111827] border border-[#1e293b] rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:border-[#FFD700]/40"
              autoFocus
            />
            <textarea
              placeholder={locale === "ja" ? "説明（任意）" : "Description (optional)"}
              aria-label={locale === "ja" ? "説明（任意）" : "Description (optional)"}
              value={newTaskDesc}
              onChange={(e) => setNewTaskDesc(e.target.value)}
              rows={2}
              maxLength={300}
              className="w-full bg-[#111827] border border-[#1e293b] rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:border-[#FFD700]/40 resize-none"
            />
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              <select
                value={newTaskPriority}
                onChange={(e) => setNewTaskPriority(e.target.value)}
                aria-label={locale === "ja" ? "優先度" : "Priority"}
                className="bg-[#111827] border border-[#1e293b] rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-[#FFD700]/40"
              >
                <option value="critical">Critical</option>
                <option value="high">High</option>
                <option value="medium">Medium</option>
                <option value="low">Low</option>
              </select>
              <select
                value={newTaskAssignee}
                onChange={(e) => setNewTaskAssignee(e.target.value)}
                aria-label={locale === "ja" ? "担当者" : "Assignee"}
                className="bg-[#111827] border border-[#1e293b] rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-[#FFD700]/40"
              >
                <option value="">Unassigned</option>
                {activeMembers.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.email}
                  </option>
                ))}
              </select>
              <input
                type="date"
                value={newTaskDue}
                onChange={(e) => setNewTaskDue(e.target.value)}
                aria-label={locale === "ja" ? "期限日" : "Due date"}
                className="bg-[#111827] border border-[#1e293b] rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-[#FFD700]/40 col-span-2 sm:col-span-1"
              />
            </div>
            <div className="flex gap-3">
              <Button
                onClick={() => void handleCreateTask()}
                disabled={taskCreateLoading || !newTaskTitle.trim()}
                className="flex-1"
              >
                {taskCreateLoading ? <Loader2 size={16} className="animate-spin" /> : <Plus size={16} />}
                Create Task
              </Button>
              <Button
                variant="secondary"
                onClick={() => {
                  setShowTaskForm(false);
                  setNewTaskTitle("");
                  setNewTaskDesc("");
                }}
              >
                Cancel
              </Button>
            </div>
          </div>
        )}

        {/* Kanban ボード */}
        {tasksLoading ? (
          <div className="flex items-center justify-center py-12 gap-3 text-[#64748b]">
            <Loader2 size={18} className="animate-spin" />
            <span>{locale === "ja" ? "タスクを読み込み中..." : "Loading tasks..."}</span>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
            {STATUS_COLUMNS.map(({ key, label, icon: Icon, color }) => {
              const columnTasks = tasks.filter((t) => t.status === key);
              return (
                <div key={key} className="space-y-3">
                  <div className="flex items-center gap-2 px-1">
                    <Icon size={14} style={{ color }} />
                    <p className="text-xs font-semibold uppercase tracking-wider" style={{ color }}>
                      {label}
                    </p>
                    <span className="ml-auto text-xs font-mono text-[#475569]">
                      {columnTasks.length}
                    </span>
                  </div>
                  <div className="space-y-3 min-h-[120px]">
                    {columnTasks.length === 0 ? (
                      <div className="border border-dashed border-[#1e293b] rounded-xl h-20 flex items-center justify-center">
                        <p className="text-xs text-[#334155]">Empty</p>
                      </div>
                    ) : (
                      columnTasks.map((task) => (
                        <TaskCard
                          key={task.id}
                          task={task}
                          members={members}
                          onStatusChange={handleStatusChange}
                          onDelete={handleDeleteTask}
                        />
                      ))
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </Card>
    </div>
  );
}
