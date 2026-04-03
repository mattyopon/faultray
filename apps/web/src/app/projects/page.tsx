"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import Link from "next/link";
import { useEffect, useState, useRef } from "react";
import { api, type Project } from "@/lib/api";
import { useLocale } from "@/lib/useLocale";
import { appDict } from "@/i18n/app-dict";
import {
  FolderKanban,
  Plus,
  Cloud,
  Server,
  GitBranch,
  FileCode,
  Clock,
  BarChart3,
  Zap,
  X,
} from "lucide-react";
import { useRouter } from "next/navigation";

function ScoreRing({ score, size = 64 }: { score: number; size?: number }) {
  const radius = 45;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (score / 100) * circumference;
  const color = score >= 90 ? "#10B981" : score >= 70 ? "#FFD700" : "#ef4444";

  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg viewBox="0 0 100 100" className="transform -rotate-90" style={{ width: size, height: size }} aria-hidden="true">
        <circle cx="50" cy="50" r={radius} stroke="#1e293b" strokeWidth="10" fill="none" />
        <circle
          cx="50" cy="50" r={radius}
          stroke={color} strokeWidth="10" fill="none"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          className="transition-all duration-700 ease-out"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-sm font-extrabold" style={{ color }}>{score.toFixed(0)}</span>
      </div>
    </div>
  );
}

function TopologyIcon({ type }: { type?: string }) {
  if (type === "aws_scan") return <Cloud size={14} className="text-[#FFD700]" />;
  if (type === "k8s_scan") return <Server size={14} className="text-blue-400" />;
  if (type === "terraform") return <GitBranch size={14} className="text-purple-400" />;
  return <FileCode size={14} className="text-[#64748b]" />;
}

function TopologyLabel({ type, t }: { type?: string; t: Record<string, string> }) {
  if (type === "aws_scan") return <>{t.awsScan}</>;
  if (type === "k8s_scan") return <>{t.k8sScan}</>;
  if (type === "terraform") return <>{t.terraform}</>;
  return <>{t.manual}</>;
}

function NewProjectModal({
  open,
  onClose,
  onCreated,
  t,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (project: Project) => void;
  t: Record<string, string>;
}) {
  const locale = useLocale();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [saving, setSaving] = useState(false);
  const modalRef = useRef<HTMLDivElement>(null);

  // MODAL-05: Esc key closes NewProjectModal
  useEffect(() => {
    if (!open) return;
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKey);
    modalRef.current?.focus();
    return () => document.removeEventListener("keydown", handleKey);
  }, [open, onClose]);

  if (!open) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setSaving(true);
    try {
      const project = await api.createProject({ name: name.trim(), description: description.trim() });
      onCreated(project);
      setName("");
      setDescription("");
      onClose();
    } catch {
      // ignore — still add a local placeholder
      const fallback: Project = {
        id: `local-${Date.now()}`,
        name: name.trim(),
        description: description.trim(),
        topology_yaml: null,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        run_count: 0,
        last_score: null,
        last_run_at: null,
      };
      onCreated(fallback);
      setName("");
      setDescription("");
      onClose();
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div ref={modalRef} tabIndex={-1} role="dialog" aria-modal="true" aria-label={t.newProject} className="relative w-full max-w-md bg-[#111827] border border-[#1e293b] rounded-2xl p-6 shadow-2xl outline-none">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-lg font-bold">{t.newProject}</h2>
          <button onClick={onClose} className="text-[#64748b] hover:text-white transition-colors" aria-label={locale === "ja" ? "閉じる" : "Close"}>
            <X size={20} />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs text-[#64748b] uppercase tracking-wider mb-2">{t.name}</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Production AWS"
              aria-label={t.name}
              required
              className="w-full px-4 py-2.5 bg-[#0a0e1a] border border-[#1e293b] rounded-lg text-sm text-white placeholder-[#475569] focus:outline-none focus:border-[#FFD700]/50 transition-colors"
            />
          </div>
          <div>
            <label className="block text-xs text-[#64748b] uppercase tracking-wider mb-2">{t.description}</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Brief description of this project..."
              aria-label={t.description}
              rows={3}
              maxLength={500}
              className="w-full px-4 py-2.5 bg-[#0a0e1a] border border-[#1e293b] rounded-lg text-sm text-white placeholder-[#475569] focus:outline-none focus:border-[#FFD700]/50 transition-colors resize-none"
            />
          </div>
          <div className="flex gap-3 pt-2">
            <Button type="button" variant="ghost" onClick={onClose} className="flex-1">
              Cancel
            </Button>
            <Button type="submit" disabled={saving || !name.trim()} className="flex-1">
              {saving ? "Creating..." : t.newProject}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const locale = useLocale();
  const t = appDict.projects[locale] ?? appDict.projects.en;
  const router = useRouter();

  useEffect(() => {
    api
      .getProjects()
      .then((data) => setProjects(Array.isArray(data) ? data : []))
      .catch(() => setProjects([]))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="max-w-[1200px] mx-auto px-6 py-10">
      {/* Header */}
      <div className="flex items-center justify-between mb-10">
        <div>
          <h1 className="text-2xl font-bold mb-1 flex items-center gap-3">
            <FolderKanban size={24} className="text-[#FFD700]" />
            {t.title}
          </h1>
          <p className="text-[#94a3b8] text-sm">{t.subtitle}</p>
        </div>
        <Button onClick={() => setModalOpen(true)}>
          <Plus size={16} />
          {t.newProject}
        </Button>
      </div>

      {/* Project Grid */}
      {loading ? (
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-48 rounded-2xl bg-[#111827] border border-[#1e293b] animate-pulse" />
          ))}
        </div>
      ) : projects.length === 0 ? (
        <div className="text-center py-24">
          <FolderKanban size={48} className="text-[#1e293b] mx-auto mb-4" />
          <p className="text-white font-semibold mb-2">{t.noProjects}</p>
          <p className="text-[#64748b] text-sm mb-6">{t.createFirst}</p>
          <Button onClick={() => setModalOpen(true)}>
            <Plus size={16} />
            {t.newProject}
          </Button>
        </div>
      ) : (
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
          {projects.map((project) => (
            <Link key={project.id} href={`/projects/${project.id}`}>
              <Card className="group cursor-pointer hover:border-[#FFD700]/30 hover:bg-[#1a2035] transition-all duration-200 h-full">
                {/* Card Header */}
                <div className="flex items-start justify-between mb-4">
                  <div className="flex-1 min-w-0 pr-3">
                    <h3 className="font-bold text-white truncate group-hover:text-[#FFD700] transition-colors">
                      {project.name}
                    </h3>
                    <p className="text-xs text-[#64748b] mt-1 line-clamp-2">
                      {project.description || "—"}
                    </p>
                  </div>
                  {project.last_score != null ? (
                    <ScoreRing score={project.last_score} size={56} />
                  ) : (
                    <div className="w-14 h-14 rounded-full border-2 border-[#1e293b] flex items-center justify-center shrink-0">
                      <span className="text-[10px] text-[#475569]">N/A</span>
                    </div>
                  )}
                </div>

                {/* Meta */}
                <div className="space-y-2 text-xs text-[#64748b]">
                  <div className="flex items-center gap-2">
                    <TopologyIcon type={project.topology_type} />
                    <span><TopologyLabel type={project.topology_type} t={t} /></span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Clock size={12} />
                    <span>
                      {project.last_run_at
                        ? new Date(project.last_run_at).toLocaleDateString()
                        : "—"}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <BarChart3 size={12} />
                    <span>{project.run_count ?? 0} {t.runCount}</span>
                  </div>
                </div>

                {/* Footer */}
                <div className="flex items-center justify-between mt-4 pt-4 border-t border-[#1e293b]">
                  <Badge variant={project.status === "archived" ? "default" : "green"}>
                    {project.status === "archived" ? t.archived : t.active}
                  </Badge>
                  <button
                    onClick={(e) => {
                      e.preventDefault();
                      router.push(`/simulate?project=${project.id}`);
                    }}
                    className="flex items-center gap-1.5 text-xs text-[#FFD700] hover:underline"
                  >
                    <Zap size={12} />
                    {t.runSimulation}
                  </button>
                </div>
              </Card>
            </Link>
          ))}
        </div>
      )}

      <NewProjectModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onCreated={(p) => setProjects((prev) => [p, ...prev])}
        t={t}
      />
    </div>
  );
}
