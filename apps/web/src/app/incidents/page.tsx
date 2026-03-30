"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useEffect, useState } from "react";
import { api, type Incident, type IncidentsData } from "@/lib/api";
import { Activity, Loader2, ChevronDown, ChevronRight } from "lucide-react";
import { useLocale } from "@/lib/useLocale";
import { appDict } from "@/i18n/app-dict";

const DEMO_DATA: IncidentsData = {
  incidents: [
    {
      id: "INC-001", title: "Cascading Database Failure", severity: "critical",
      start_time: "2026-03-28T14:23:00Z", end_time: "2026-03-28T14:35:00Z",
      duration_minutes: 12, affected_components: ["db_primary", "api", "worker"],
      root_cause: "Primary database disk I/O saturation",
      timeline: [
        { time: "T+0:00", event: "Database disk I/O reaches 100%", component: "db_primary", type: "trigger" },
        { time: "T+0:30", event: "Query latency exceeds 5s", component: "db_primary", type: "degradation" },
        { time: "T+1:00", event: "Connection pool exhausted", component: "db_primary", type: "failure" },
        { time: "T+1:15", event: "API health check fails", component: "api", type: "cascade" },
        { time: "T+5:00", event: "Alert fired, on-call paged", component: "monitor", type: "detection" },
        { time: "T+8:00", event: "Manual failover initiated", component: "db_replica", type: "recovery" },
        { time: "T+12:00", event: "All services recovered", component: "all", type: "resolved" },
      ],
    },
    {
      id: "INC-002", title: "Cache Cluster Network Partition", severity: "high",
      start_time: "2026-03-27T09:15:00Z", end_time: "2026-03-27T09:28:00Z",
      duration_minutes: 13, affected_components: ["cache", "api"],
      root_cause: "Network partition between AZs",
      timeline: [
        { time: "T+0:00", event: "Network partition between AZ-1a and AZ-1b", component: "network", type: "trigger" },
        { time: "T+0:15", event: "Cache split-brain detected", component: "cache", type: "failure" },
        { time: "T+0:30", event: "Cache hit rate drops to 40%", component: "cache", type: "degradation" },
        { time: "T+5:00", event: "Network partition resolved", component: "network", type: "recovery" },
        { time: "T+13:00", event: "Cache hit rate returns to 95%", component: "cache", type: "resolved" },
      ],
    },
    {
      id: "INC-003", title: "DNS Resolution Failure", severity: "high",
      start_time: "2026-03-25T22:10:00Z", end_time: "2026-03-25T22:18:00Z",
      duration_minutes: 8, affected_components: ["dns", "cdn", "gateway"],
      root_cause: "DNS provider TTL expiry during maintenance",
      timeline: [
        { time: "T+0:00", event: "DNS provider begins maintenance", component: "dns", type: "trigger" },
        { time: "T+0:30", event: "DNS TTL expires", component: "dns", type: "failure" },
        { time: "T+3:00", event: "Secondary DNS takes over", component: "dns", type: "recovery" },
        { time: "T+8:00", event: "All traffic flowing normally", component: "all", type: "resolved" },
      ],
    },
  ],
  summary: { total_incidents: 3, critical: 1, high: 2, medium: 0, average_duration_minutes: 11, most_affected_component: "db_primary" },
};

const EVENT_COLORS: Record<string, string> = {
  trigger: "#ef4444",
  failure: "#ef4444",
  degradation: "#f59e0b",
  cascade: "#f97316",
  detection: "#3b82f6",
  recovery: "#10b981",
  resolved: "#10b981",
};

function IncidentCard({ incident }: { incident: Incident }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <Card>
      <button
        className="w-full text-left"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            {expanded ? <ChevronDown size={16} className="text-[#64748b]" /> : <ChevronRight size={16} className="text-[#64748b]" />}
            <div>
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs text-[#64748b]">{incident.id}</span>
                <Badge variant={incident.severity === "critical" ? "red" : "yellow"}>
                  {incident.severity}
                </Badge>
              </div>
              <p className="font-bold mt-1">{incident.title}</p>
            </div>
          </div>
          <div className="text-right">
            <p className="font-mono text-sm">{incident.duration_minutes}min</p>
            <p className="text-xs text-[#64748b]">
              {new Date(incident.start_time).toLocaleDateString()}
            </p>
          </div>
        </div>
      </button>

      {expanded && (
        <div className="mt-6 pt-4 border-t border-[#1e293b]">
          <div className="mb-4">
            <p className="text-xs text-[#64748b] uppercase tracking-wider mb-1">Root Cause</p>
            <p className="text-sm">{incident.root_cause}</p>
          </div>
          <div className="mb-4">
            <p className="text-xs text-[#64748b] uppercase tracking-wider mb-1">Affected Components</p>
            <div className="flex gap-2">
              {incident.affected_components.map((c) => (
                <Badge key={c} variant="default">{c}</Badge>
              ))}
            </div>
          </div>

          {/* Timeline */}
          <div>
            <p className="text-xs text-[#64748b] uppercase tracking-wider mb-3">Timeline</p>
            <div className="relative pl-6">
              {/* Vertical line */}
              <div className="absolute left-[9px] top-0 bottom-0 w-0.5 bg-[#1e293b]" />
              <div className="space-y-3">
                {incident.timeline.map((event, i) => (
                  <div key={i} className="relative flex items-start gap-3">
                    <div
                      className="absolute left-[-15px] w-3 h-3 rounded-full border-2 bg-[#111827]"
                      style={{ borderColor: EVENT_COLORS[event.type] || "#64748b" }}
                    />
                    <div className="flex-1 pl-2">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-mono text-[#64748b]">{event.time}</span>
                        <Badge
                          variant={
                            event.type === "trigger" || event.type === "failure"
                              ? "red"
                              : event.type === "recovery" || event.type === "resolved"
                                ? "green"
                                : "yellow"
                          }
                        >
                          {event.type}
                        </Badge>
                      </div>
                      <p className="text-sm mt-1">{event.event}</p>
                      <p className="text-xs text-[#64748b]">{event.component}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </Card>
  );
}

export default function IncidentsPage() {
  const [data, setData] = useState<IncidentsData>(DEMO_DATA);
  const [loading, setLoading] = useState(true);
  const locale = useLocale();
  const t = locale === "ja" ? appDict.incidents.ja : appDict.incidents.en;

  useEffect(() => {
    api
      .getIncidents()
      .then((result) => setData(result))
      .catch(() => setData(DEMO_DATA))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="max-w-[1200px] mx-auto px-6 py-10">
      <div className="mb-10">
        <h1 className="text-2xl font-bold mb-1 flex items-center gap-3">
          <Activity size={24} className="text-[#FFD700]" />
          {t.title}
        </h1>
        <p className="text-[#94a3b8] text-sm">
          {t.subtitle}
        </p>
      </div>

      {loading ? (
        <Card className="flex items-center justify-center py-20">
          <Loader2 size={24} className="animate-spin text-[#FFD700]" />
        </Card>
      ) : (
        <>
          {/* Summary */}
          <div className="grid md:grid-cols-4 gap-6 mb-8">
            <Card className="text-center">
              <p className="text-3xl font-extrabold font-mono">{data.summary.total_incidents}</p>
              <p className="text-xs text-[#64748b] uppercase tracking-wider mt-1">{t.totalIncidents}</p>
            </Card>
            <Card className="text-center">
              <p className="text-3xl font-extrabold font-mono text-red-400">{data.summary.critical}</p>
              <p className="text-xs text-[#64748b] uppercase tracking-wider mt-1">{t.critical}</p>
            </Card>
            <Card className="text-center">
              <p className="text-3xl font-extrabold font-mono text-[#f59e0b]">{data.summary.high}</p>
              <p className="text-xs text-[#64748b] uppercase tracking-wider mt-1">{t.high}</p>
            </Card>
            <Card className="text-center">
              <p className="text-3xl font-extrabold font-mono">{data.summary.average_duration_minutes}m</p>
              <p className="text-xs text-[#64748b] uppercase tracking-wider mt-1">{t.avgDuration}</p>
            </Card>
          </div>

          {/* Incidents */}
          <div className="space-y-4">
            {data.incidents.map((incident) => (
              <IncidentCard key={incident.id} incident={incident} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
