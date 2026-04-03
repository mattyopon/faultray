"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useState } from "react";
import { FileSearch, ChevronDown, ChevronRight, CheckCircle2, Circle, Clock } from "lucide-react";
import { useLocale } from "@/lib/useLocale";
import { appDict } from "@/i18n/app-dict";

const DEMO_POSTMORTEMS = [
  {
    id: "PM-2026-003",
    title: "Cascading Database Failure — March 28",
    date: "2026-03-28",
    severity: "critical",
    status: "resolved",
    timeToDetect: "5 min",
    timeToResolve: "12 min",
    rootCause: "Primary database disk I/O saturated due to unthrottled batch export job introduced in v2.4.1 release.",
    timeline: [
      { time: "14:23", event: "Batch export job started without I/O throttling" },
      { time: "14:26", event: "Disk I/O reaches 100%, query latency spikes to 8s" },
      { time: "14:28", event: "PagerDuty alert fires — on-call engineer paged" },
      { time: "14:31", event: "Batch job killed, failover to replica initiated" },
      { time: "14:35", event: "All services recovered, error rate < 0.1%" },
    ],
    lessonsLearned: [
      "Batch jobs must have explicit I/O rate limits before deployment",
      "Auto-failover should trigger at 80% I/O utilization, not 100%",
      "Release checklist must include database load testing for export features",
    ],
    actionItems: [
      { id: "AI-001", text: "Add I/O throttling to all batch jobs", owner: "Platform Team", dueDate: "2026-04-05", status: "complete" },
      { id: "AI-002", text: "Lower auto-failover threshold to 80% I/O", owner: "SRE", dueDate: "2026-04-03", status: "complete" },
      { id: "AI-003", text: "Add batch load test to release checklist", owner: "Engineering", dueDate: "2026-04-10", status: "inProgress" },
      { id: "AI-004", text: "Implement canary deployment for DB-heavy features", owner: "Platform Team", dueDate: "2026-04-20", status: "open" },
    ],
  },
  {
    id: "PM-2026-002",
    title: "Cache Cluster Network Partition — March 27",
    date: "2026-03-27",
    severity: "high",
    status: "resolved",
    timeToDetect: "3 min",
    timeToResolve: "13 min",
    rootCause: "AWS VPC security group misconfiguration blocked inter-AZ traffic on port 6379 during a routine infrastructure update.",
    timeline: [
      { time: "09:12", event: "Terraform apply runs, modifies security group rules" },
      { time: "09:15", event: "Cache split-brain detected, hit rate drops to 40%" },
      { time: "09:18", event: "Alert fires, on-call investigates" },
      { time: "09:22", event: "Security group rule restored" },
      { time: "09:28", event: "Cache hit rate returns to 95%" },
    ],
    lessonsLearned: [
      "Infrastructure changes must be reviewed for port-level impact on inter-service communication",
      "Cache hit rate should be a primary SLO metric with <2min detection",
      "Terraform plans need automated security group impact analysis",
    ],
    actionItems: [
      { id: "AI-005", text: "Add security group change review to Terraform CI", owner: "Platform Team", dueDate: "2026-04-01", status: "complete" },
      { id: "AI-006", text: "Add cache hit rate to primary dashboard", owner: "SRE", dueDate: "2026-04-02", status: "complete" },
      { id: "AI-007", text: "Document inter-service port dependencies", owner: "Engineering", dueDate: "2026-04-15", status: "inProgress" },
    ],
  },
  {
    id: "PM-2026-001",
    title: "DNS Resolution Failure — March 25",
    date: "2026-03-25",
    severity: "high",
    status: "resolved",
    timeToDetect: "2 min",
    timeToResolve: "8 min",
    rootCause: "DNS provider maintenance window caused TTL expiry for primary domain records. Secondary DNS failover was not configured.",
    timeline: [
      { time: "22:10", event: "DNS provider begins scheduled maintenance" },
      { time: "22:10", event: "TTL expires for primary domain records" },
      { time: "22:12", event: "Synthetic monitor alerts — external DNS failure" },
      { time: "22:14", event: "Secondary DNS activated manually" },
      { time: "22:18", event: "All traffic routing normally" },
    ],
    lessonsLearned: [
      "Secondary DNS provider should be active-active, not manual failover",
      "DNS maintenance windows from providers must be tracked and alerts prepared",
      "Lower production DNS TTL from 3600s to 300s for faster failover",
    ],
    actionItems: [
      { id: "AI-008", text: "Configure active-active secondary DNS", owner: "Infra Team", dueDate: "2026-04-07", status: "complete" },
      { id: "AI-009", text: "Lower production DNS TTL to 300s", owner: "Infra Team", dueDate: "2026-04-03", status: "complete" },
      { id: "AI-010", text: "Subscribe to all DNS provider maintenance alerts", owner: "SRE", dueDate: "2026-04-10", status: "open" },
    ],
  },
];

const STATUS_BADGE: Record<string, "green" | "yellow" | "default"> = {
  complete: "green",
  inProgress: "yellow",
  open: "default",
};

function PostmortemCard({ pm, t }: { pm: typeof DEMO_POSTMORTEMS[0]; t: Record<string, string> }) {
  const [expanded, setExpanded] = useState(false);
  const complete = pm.actionItems.filter((a) => a.status === "complete").length;

  return (
    <Card>
      <button className="w-full text-left" onClick={() => setExpanded(!expanded)}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            {expanded ? <ChevronDown size={16} className="text-[#64748b]" /> : <ChevronRight size={16} className="text-[#64748b]" />}
            <div>
              <div className="flex items-center gap-2 mb-1">
                <span className="font-mono text-xs text-[#64748b]">{pm.id}</span>
                <Badge variant={pm.severity === "critical" ? "red" : "yellow"}>{pm.severity}</Badge>
                <Badge variant="green">{t.resolved}</Badge>
              </div>
              <p className="font-bold">{pm.title}</p>
            </div>
          </div>
          <div className="text-right shrink-0 ml-4">
            <p className="text-xs text-[#64748b]">{pm.date}</p>
            <p className="text-xs text-[#10b981] mt-1">
              {t.actionItems}: {complete}/{pm.actionItems.length}
            </p>
          </div>
        </div>
      </button>

      {expanded && (
        <div className="mt-6 pt-4 border-t border-[#1e293b] space-y-6">
          {/* Stats */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="bg-[#0a0e1a] rounded-lg p-3 text-center">
              <p className="text-lg font-bold font-mono text-[#FFD700]">{pm.timeToDetect}</p>
              <p className="text-xs text-[#64748b] mt-1">{t.detecting}</p>
            </div>
            <div className="bg-[#0a0e1a] rounded-lg p-3 text-center">
              <p className="text-lg font-bold font-mono text-[#FFD700]">{pm.timeToResolve}</p>
              <p className="text-xs text-[#64748b] mt-1">{t.resolving}</p>
            </div>
            <div className="bg-[#0a0e1a] rounded-lg p-3 text-center col-span-2">
              <p className="text-sm font-bold text-[#10b981]">{complete}/{pm.actionItems.length} completed</p>
              <p className="text-xs text-[#64748b] mt-1">{t.actionItems}</p>
            </div>
          </div>

          {/* Root cause */}
          <div>
            <p className="text-xs text-[#64748b] uppercase tracking-wider mb-2">{t.rootCause}</p>
            <p className="text-sm text-[#94a3b8] bg-[#0a0e1a] rounded-lg p-3">{pm.rootCause}</p>
          </div>

          {/* Timeline */}
          <div>
            <p className="text-xs text-[#64748b] uppercase tracking-wider mb-3">{t.timeline}</p>
            <div className="relative pl-6">
              <div className="absolute left-[9px] top-0 bottom-0 w-0.5 bg-[#1e293b]" />
              <div className="space-y-3">
                {pm.timeline.map((item, i) => (
                  <div key={i} className="relative flex items-start gap-3">
                    <div className="absolute left-[-15px] w-3 h-3 rounded-full border-2 border-[#FFD700] bg-[#111827]" />
                    <div>
                      <span className="text-xs font-mono text-[#FFD700]">{item.time}</span>
                      <p className="text-xs text-[#94a3b8] mt-0.5">{item.event}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Lessons learned */}
          <div>
            <p className="text-xs text-[#64748b] uppercase tracking-wider mb-2">{t.lessonsLearned}</p>
            <ul className="space-y-1.5">
              {pm.lessonsLearned.map((lesson, i) => (
                <li key={i} className="text-sm text-[#94a3b8] flex gap-2">
                  <span className="text-[#FFD700] shrink-0">•</span>
                  {lesson}
                </li>
              ))}
            </ul>
          </div>

          {/* Action items */}
          <div>
            <p className="text-xs text-[#64748b] uppercase tracking-wider mb-3">{t.actionItems}</p>
            <div className="space-y-2">
              {pm.actionItems.map((item) => (
                <div key={item.id} className="flex items-center justify-between bg-[#0a0e1a] rounded-lg p-3">
                  <div className="flex items-start gap-2">
                    {item.status === "complete" ? (
                      <CheckCircle2 size={16} className="text-[#10b981] shrink-0 mt-0.5" />
                    ) : item.status === "inProgress" ? (
                      <Clock size={16} className="text-[#f59e0b] shrink-0 mt-0.5" />
                    ) : (
                      <Circle size={16} className="text-[#475569] shrink-0 mt-0.5" />
                    )}
                    <div>
                      <p className="text-sm">{item.text}</p>
                      <p className="text-xs text-[#64748b] mt-0.5">{item.owner} · Due: {item.dueDate}</p>
                    </div>
                  </div>
                  <Badge variant={STATUS_BADGE[item.status] ?? "default"}>
                    {item.status === "complete" ? t.complete : item.status === "inProgress" ? t.inProgress : t.open}
                  </Badge>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </Card>
  );
}

export default function PostmortemsPage() {
  const locale = useLocale();
  const t = appDict.postmortems[locale] ?? appDict.postmortems.en;

  const totalActions = DEMO_POSTMORTEMS.flatMap((p) => p.actionItems);
  const completedActions = totalActions.filter((a) => a.status === "complete").length;

  return (
    <div className="max-w-[1200px] mx-auto px-6 py-10">
      <div className="flex items-start justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold mb-1 flex items-center gap-3">
            <FileSearch size={24} className="text-[#FFD700]" />
            {t.title}
          </h1>
          <p className="text-[#94a3b8] text-sm">{t.subtitle}</p>
        </div>
        <Button size="sm" className="shrink-0">{t.newPostmortem}</Button>
      </div>

      {/* DEMO-05: Sample data notice */}
      <div className="mb-6 px-4 py-2.5 rounded-lg border border-amber-500/20 bg-amber-500/[0.06] flex items-center gap-2 text-xs text-amber-400">
        <span className="shrink-0">📋</span>
        <span>{locale === "ja" ? "サンプルデータを表示中。実際の障害データはシミュレーション実行後に蓄積されます。" : "Showing sample data. Real incident data accumulates after running simulations."}</span>
      </div>

      {/* Summary */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        <Card className="text-center">
          <p className="text-3xl font-extrabold font-mono">{DEMO_POSTMORTEMS.length}</p>
          <p className="text-xs text-[#64748b] uppercase tracking-wider mt-1">Post-Mortems</p>
        </Card>
        <Card className="text-center">
          <p className="text-3xl font-extrabold font-mono text-red-400">
            {DEMO_POSTMORTEMS.filter((p) => p.severity === "critical").length}
          </p>
          <p className="text-xs text-[#64748b] uppercase tracking-wider mt-1">Critical</p>
        </Card>
        <Card className="text-center">
          <p className="text-3xl font-extrabold font-mono text-[#10b981]">{completedActions}</p>
          <p className="text-xs text-[#64748b] uppercase tracking-wider mt-1">Actions Done</p>
        </Card>
        <Card className="text-center">
          <p className="text-3xl font-extrabold font-mono text-[#FFD700]">
            {totalActions.length - completedActions}
          </p>
          <p className="text-xs text-[#64748b] uppercase tracking-wider mt-1">Remaining</p>
        </Card>
      </div>

      <div className="space-y-4">
        {DEMO_POSTMORTEMS.map((pm) => (
          <PostmortemCard key={pm.id} pm={pm} t={t} />
        ))}
      </div>
    </div>
  );
}
