"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type ProjectWithRuns } from "@/lib/api";
import { useLocale } from "@/lib/useLocale";
import { appDict } from "@/i18n/app-dict";
import {
  ArrowLeft,
  Zap,
  Network,
  Download,
  ChevronDown,
  ChevronRight,
  AlertTriangle,
  Lightbulb,
  Clock,
  BarChart3,
  FolderKanban,
  Loader2,
} from "lucide-react";
import { useParams, useRouter } from "next/navigation";

function ScoreRing({ score, size = 120 }: { score: number; size?: number }) {
  const locale = useLocale();
  const radius = 45;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (score / 100) * circumference;
  const color = score >= 90 ? "#10B981" : score >= 70 ? "#FFD700" : "#ef4444";

  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg viewBox="0 0 100 100" className="transform -rotate-90" style={{ width: size, height: size }} aria-hidden="true">
        <circle cx="50" cy="50" r={radius} stroke="#1e293b" strokeWidth="8" fill="none" />
        <circle
          cx="50" cy="50" r={radius}
          stroke={color} strokeWidth="8" fill="none"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          className="transition-all duration-1000 ease-out"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-2xl font-extrabold" style={{ color }}>{score.toFixed(1)}</span>
        <span className="text-[10px] text-[#64748b] uppercase tracking-wider">{locale === "ja" ? "スコア" : "Score"}</span>
      </div>
    </div>
  );
}

type Run = ProjectWithRuns["runs"][number];

function RunRow({ run, t }: { run: Run; t: Record<string, string> }) {
  const [expanded, setExpanded] = useState(false);
  const locale = useLocale();
  const hasCritical = (run.critical_failures?.length ?? 0) > 0;
  const hasSuggestions = (run.suggestions?.length ?? 0) > 0;
  const scoreColor =
    run.overall_score >= 90
      ? "text-emerald-400"
      : run.overall_score >= 70
      ? "text-[#FFD700]"
      : "text-red-400";

  return (
    <>
      <tr
        className="border-b border-[#1e293b]/50 hover:bg-white/[0.02] cursor-pointer"
        onClick={() => setExpanded(!expanded)}
      >
        <td className="py-3 px-3 text-[#94a3b8] text-sm">
          {new Date(run.created_at).toLocaleDateString()}
        </td>
        <td className={`py-3 px-3 font-mono font-bold text-sm ${scoreColor}`}>
          {run.overall_score.toFixed(1)}
        </td>
        <td className="py-3 px-3 text-[#94a3b8] text-sm font-mono">
          {run.availability_estimate}
        </td>
        <td className="py-3 px-3 text-sm">
          <span className="text-emerald-400">{run.scenarios_passed}</span>
          <span className="text-[#475569]"> / </span>
          <span className="text-[#94a3b8]">{run.total_scenarios}</span>
        </td>
        <td className="py-3 px-3 text-right">
          <Badge variant={run.scenarios_failed === 0 ? "green" : "yellow"}>
            {run.scenarios_failed === 0 ? t.allPassed ?? "All Passed" : `${run.scenarios_failed} ${t.xFailed ?? "Failed"}`}
          </Badge>
        </td>
        <td className="py-3 px-3 text-right text-[#64748b]">
          {(hasCritical || hasSuggestions) ? (
            expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />
          ) : null}
        </td>
      </tr>
      {expanded && (hasCritical || hasSuggestions) && (
        <tr className="border-b border-[#1e293b]/30">
          <td colSpan={6} className="px-3 pb-4 pt-2">
            <div className="grid md:grid-cols-2 gap-4">
              {hasCritical && (
                <div className="p-4 rounded-xl bg-red-500/5 border border-red-500/20">
                  <div className="flex items-center gap-2 mb-3">
                    <AlertTriangle size={14} className="text-red-400" />
                    <span className="text-xs font-semibold text-red-400 uppercase tracking-wider">{locale === "ja" ? "重大な障害" : "Critical Failures"}</span>
                  </div>
                  <ul className="space-y-2">
                    {run.critical_failures!.map((f, i) => (
                      <li key={i} className="text-xs text-[#94a3b8]">
                        <span className="text-white font-medium">{f.scenario}</span>
                        {" — "}
                        {f.impact}
                        <Badge variant={f.severity === "HIGH" ? "red" : "yellow"} className="ml-2 text-[10px]">
                          {f.severity}
                        </Badge>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {hasSuggestions && (
                <div className="p-4 rounded-xl bg-[#FFD700]/5 border border-[#FFD700]/20">
                  <div className="flex items-center gap-2 mb-3">
                    <Lightbulb size={14} className="text-[#FFD700]" />
                    <span className="text-xs font-semibold text-[#FFD700] uppercase tracking-wider">{locale === "ja" ? "改善提案" : "Suggestions"}</span>
                  </div>
                  <ul className="space-y-2">
                    {run.suggestions!.map((s, i) => (
                      <li key={i} className="text-xs text-[#94a3b8]">
                        <span className="text-white font-medium">{s.title}</span>
                        {" — "}
                        {s.description}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

export default function ProjectDetailPage() {
  const params = useParams();
  const projectId = params?.id as string;
  const [project, setProject] = useState<ProjectWithRuns | null>(null);
  const [loading, setLoading] = useState(true);
  const locale = useLocale();
  const t = appDict.projects[locale] ?? appDict.projects.en;
  const router = useRouter();

  useEffect(() => {
    if (!projectId) return;
    api
      .getProject(projectId)
      .then((data) => setProject(data))
      .catch(() => setProject(null))
      .finally(() => setLoading(false));
  }, [projectId]);

  const handleExport = () => {
    if (!project) return;
    const blob = new Blob([JSON.stringify(project, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${project.name.replace(/\s+/g, "-").toLowerCase()}-export.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  if (loading) {
    return (
      <div className="max-w-[1200px] mx-auto px-6 py-10 flex items-center justify-center min-h-[60vh]">
        <Loader2 size={32} className="text-[#FFD700] animate-spin" />
      </div>
    );
  }

  if (!project) {
    return (
      <div className="max-w-[1200px] mx-auto px-6 py-10 text-center">
        <FolderKanban size={48} className="text-[#1e293b] mx-auto mb-4" />
        <p className="text-[#64748b] mb-4">{locale === "ja" ? "プロジェクトが見つかりません" : "Project not found"}</p>
        <Link href="/projects">
          <Button variant="ghost">
            <ArrowLeft size={16} /> {locale === "ja" ? "プロジェクト一覧に戻る" : "Back to Projects"}
          </Button>
        </Link>
      </div>
    );
  }

  const latestRun = project.runs?.[0];
  const latestScore = latestRun?.overall_score ?? project.last_score;

  return (
    <div className="max-w-[1200px] mx-auto px-6 py-10">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-sm text-[#64748b] mb-8">
        <Link href="/projects" className="hover:text-white transition-colors flex items-center gap-1.5">
          <ArrowLeft size={14} />
          {t.title}
        </Link>
        <span>/</span>
        <span className="text-white">{project.name}</span>
      </div>

      {/* Header */}
      <div className="flex items-start justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold mb-1">{project.name}</h1>
          <p className="text-[#94a3b8] text-sm max-w-xl">
            {project.description || "—"}
          </p>
          <div className="flex items-center gap-4 mt-3 text-xs text-[#64748b]">
            <span className="flex items-center gap-1.5">
              <Clock size={12} />
              Created {new Date(project.created_at).toLocaleDateString()}
            </span>
            <span className="flex items-center gap-1.5">
              <BarChart3 size={12} />
              {project.run_count ?? project.runs?.length ?? 0} {t.runCount}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={handleExport}>
            <Download size={14} />
            {t.export}
          </Button>
          <Link href="/topology">
            <Button variant="ghost" size="sm">
              <Network size={14} />
              {t.viewTopology}
            </Button>
          </Link>
          <Button
            size="sm"
            onClick={() => router.push(`/simulate?project=${project.id}`)}
          >
            <Zap size={14} />
            {t.runSimulation}
          </Button>
        </div>
      </div>

      {/* Latest Score Card */}
      {latestScore != null && (
        <Card className="mb-8">
          <div className="flex items-center gap-8">
            <ScoreRing score={latestScore} size={120} />
            <div className="flex-1">
              <p className="text-xs text-[#64748b] uppercase tracking-wider mb-2">{locale === "ja" ? "最新シミュレーション" : "Latest Simulation"}</p>
              {latestRun && (
                <div className="grid grid-cols-3 gap-6">
                  <div>
                    <p className="text-xl font-bold font-mono text-emerald-400">
                      {latestRun.availability_estimate}
                    </p>
                    <p className="text-xs text-[#64748b] mt-0.5">{t.availability}</p>
                  </div>
                  <div>
                    <p className="text-xl font-bold font-mono">
                      <span className="text-emerald-400">{latestRun.scenarios_passed}</span>
                      <span className="text-[#475569]"> / </span>
                      <span className="text-[#94a3b8]">{latestRun.total_scenarios}</span>
                    </p>
                    <p className="text-xs text-[#64748b] mt-0.5">{t.scenarios}</p>
                  </div>
                  <div>
                    <p className="text-sm text-[#94a3b8]">
                      {new Date(latestRun.created_at).toLocaleDateString()}
                    </p>
                    <p className="text-xs text-[#64748b] mt-0.5">{t.date}</p>
                  </div>
                </div>
              )}
            </div>
          </div>
        </Card>
      )}

      {/* Simulation History */}
      <Card>
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-lg font-bold flex items-center gap-2">
            <BarChart3 size={18} className="text-[#FFD700]" />
            {t.simulationHistory}
          </h2>
          <Badge variant="default">{project.runs?.length ?? 0} runs</Badge>
        </div>

        {!project.runs || project.runs.length === 0 ? (
          <div className="text-center py-12">
            <Zap size={32} className="text-[#1e293b] mx-auto mb-3" />
            <p className="text-[#64748b] text-sm mb-4">No simulations yet for this project.</p>
            <Button size="sm" onClick={() => router.push(`/simulate?project=${project.id}`)}>
              <Zap size={14} />
              {t.runSimulation}
            </Button>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[#1e293b]">
                  <th scope="col" className="text-left py-3 px-3 text-[#64748b] font-medium">{t.date}</th>
                  <th scope="col" className="text-left py-3 px-3 text-[#64748b] font-medium">{t.score}</th>
                  <th scope="col" className="text-left py-3 px-3 text-[#64748b] font-medium">{t.availability}</th>
                  <th scope="col" className="text-left py-3 px-3 text-[#64748b] font-medium">{t.scenarios}</th>
                  <th scope="col" className="text-right py-3 px-3 text-[#64748b] font-medium">Status</th>
                  <th scope="col" className="w-6" />
                </tr>
              </thead>
              <tbody>
                {project.runs.map((run) => (
                  <RunRow key={run.id} run={run} t={t} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
