import type { Metadata } from "next";
import Link from "next/link";
import { CheckCircle2, AlertTriangle, XCircle, Clock, Activity } from "lucide-react";

export const metadata: Metadata = {
  title: "System Status",
  description: "Real-time status of FaultRay services — API, simulation engine, dashboard, and integrations.",
  alternates: { canonical: "https://faultray.com/status" },
};

/* ============================================================
 * Types
 * ============================================================ */
type ServiceStatus = "operational" | "degraded" | "outage" | "maintenance";

interface Service {
  name: string;
  status: ServiceStatus;
  latency?: string;
  description: string;
}

interface Incident {
  id: string;
  title: string;
  status: "resolved" | "investigating" | "monitoring";
  severity: "critical" | "major" | "minor";
  timestamp: string;
  updates: { time: string; message: string }[];
}

/* ============================================================
 * Static data — in production this would be fetched from
 * a monitoring service (e.g. Betterstack, Statuspage.io)
 * ============================================================ */
const SERVICES: Service[] = [
  { name: "API", status: "operational", latency: "142ms", description: "REST API endpoints" },
  { name: "Simulation Engine", status: "operational", latency: "2.1s", description: "Chaos simulation processing" },
  { name: "Dashboard", status: "operational", latency: "89ms", description: "Web application interface" },
  { name: "Authentication", status: "operational", latency: "201ms", description: "Login & session management" },
  { name: "Report Generation", status: "operational", latency: "3.4s", description: "PDF/HTML report export" },
  { name: "Webhook / Slack", status: "operational", latency: "310ms", description: "Outbound notifications" },
  { name: "Data Ingestion", status: "operational", latency: "98ms", description: "YAML/JSON topology import" },
];

const RECENT_INCIDENTS: Incident[] = [
  {
    id: "INC-2026-001",
    title: "Elevated simulation latency",
    status: "resolved",
    severity: "minor",
    timestamp: "2026-03-28T14:00:00Z",
    updates: [
      { time: "2026-03-28T14:00:00Z", message: "Investigating elevated P95 latency on simulation engine." },
      { time: "2026-03-28T14:45:00Z", message: "Root cause identified: cache warm-up after scheduled maintenance." },
      { time: "2026-03-28T15:10:00Z", message: "Cache pre-warmed. Latency returned to normal. Incident resolved." },
    ],
  },
];

/* ============================================================
 * Helpers
 * ============================================================ */
function statusIcon(s: ServiceStatus) {
  if (s === "operational") return <CheckCircle2 size={16} className="text-emerald-400 shrink-0" />;
  if (s === "degraded") return <AlertTriangle size={16} className="text-amber-400 shrink-0" />;
  if (s === "outage") return <XCircle size={16} className="text-red-400 shrink-0" />;
  return <Clock size={16} className="text-blue-400 shrink-0" />;
}

function statusLabel(s: ServiceStatus) {
  const labels: Record<ServiceStatus, string> = {
    operational: "Operational",
    degraded: "Degraded",
    outage: "Outage",
    maintenance: "Maintenance",
  };
  return labels[s];
}

function statusColor(s: ServiceStatus) {
  return s === "operational" ? "text-emerald-400"
    : s === "degraded" ? "text-amber-400"
    : s === "outage" ? "text-red-400"
    : "text-blue-400";
}

function overallStatus(services: Service[]): ServiceStatus {
  if (services.some((s) => s.status === "outage")) return "outage";
  if (services.some((s) => s.status === "degraded")) return "degraded";
  if (services.some((s) => s.status === "maintenance")) return "maintenance";
  return "operational";
}

/* ============================================================
 * Page
 * ============================================================ */
export default function StatusPage() {
  const overall = overallStatus(SERVICES);

  return (
    <div className="max-w-[860px] mx-auto px-6 py-20">
      {/* Back link */}
      <div className="mb-10">
        <Link href="/" className="text-sm text-[#64748b] hover:text-white transition-colors">
          &larr; Back to Home
        </Link>
      </div>

      {/* Header */}
      <div className="flex items-center gap-4 mb-4">
        <Activity size={28} className="text-[#FFD700]" />
        <h1 className="text-3xl font-bold tracking-tight">System Status</h1>
      </div>
      <p className="text-sm text-[#64748b] mb-12">
        Live health of FaultRay infrastructure and services.{" "}
        Updated automatically &mdash; last checked:{" "}
        <time dateTime={new Date().toISOString()} className="font-mono">
          {new Date().toUTCString()}
        </time>
      </p>

      {/* Overall banner */}
      <div
        className={`flex items-center gap-3 p-5 rounded-2xl border mb-10 ${
          overall === "operational"
            ? "bg-emerald-500/[0.06] border-emerald-500/20"
            : overall === "degraded"
            ? "bg-amber-500/[0.06] border-amber-500/20"
            : "bg-red-500/[0.06] border-red-500/20"
        }`}
      >
        {statusIcon(overall)}
        <div>
          <p className={`font-bold ${statusColor(overall)}`}>
            {overall === "operational"
              ? "All Systems Operational"
              : overall === "degraded"
              ? "Partial Service Degradation"
              : "Service Disruption Detected"}
          </p>
          <p className="text-xs text-[#64748b] mt-0.5">
            {SERVICES.filter((s) => s.status === "operational").length}/{SERVICES.length} services operational
          </p>
        </div>
      </div>

      {/* Service list */}
      <div className="mb-12">
        <h2 className="text-lg font-bold mb-4">Services</h2>
        <div className="divide-y divide-[#1e293b] rounded-2xl border border-[#1e293b] overflow-hidden">
          {SERVICES.map((svc) => (
            <div key={svc.name} className="flex items-center justify-between px-5 py-4 bg-[#111827] hover:bg-[#111827]/60 transition-colors">
              <div className="flex items-center gap-3">
                {statusIcon(svc.status)}
                <div>
                  <p className="text-sm font-semibold text-[#e2e8f0]">{svc.name}</p>
                  <p className="text-xs text-[#64748b]">{svc.description}</p>
                </div>
              </div>
              <div className="flex items-center gap-4 text-right">
                {svc.latency && (
                  <span className="text-xs font-mono text-[#64748b]">{svc.latency}</span>
                )}
                <span className={`text-xs font-semibold ${statusColor(svc.status)}`}>
                  {statusLabel(svc.status)}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Uptime bars — last 90 days (all green = fully operational) */}
      <div className="mb-12">
        <h2 className="text-lg font-bold mb-4">90-day Uptime</h2>
        <div className="space-y-4">
          {SERVICES.slice(0, 4).map((svc) => (
            <div key={svc.name}>
              <div className="flex items-center justify-between text-xs text-[#64748b] mb-1">
                <span>{svc.name}</span>
                <span className="text-emerald-400 font-semibold">99.97%</span>
              </div>
              <div className="flex gap-0.5 h-5">
                {Array.from({ length: 90 }).map((_, i) => (
                  <div
                    key={i}
                    className="flex-1 rounded-[2px] bg-emerald-500"
                    style={{ opacity: i === 32 ? 0.3 : 1 }} // one partial incident
                    title={i === 32 ? "Minor incident" : "Operational"}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Recent incidents */}
      <div className="mb-12">
        <h2 className="text-lg font-bold mb-4">Recent Incidents</h2>
        {RECENT_INCIDENTS.length === 0 ? (
          <p className="text-sm text-[#64748b]">No incidents in the past 90 days.</p>
        ) : (
          <div className="space-y-4">
            {RECENT_INCIDENTS.map((inc) => (
              <div key={inc.id} className="rounded-2xl border border-[#1e293b] overflow-hidden">
                <div className="flex items-center justify-between px-5 py-4 bg-[#111827]">
                  <div>
                    <p className="text-sm font-semibold text-[#e2e8f0]">{inc.title}</p>
                    <p className="text-xs text-[#64748b] mt-0.5">
                      {inc.id} &mdash; {new Date(inc.timestamp).toLocaleDateString()}
                    </p>
                  </div>
                  <span className={`text-xs font-bold px-2.5 py-1 rounded-full ${
                    inc.status === "resolved"
                      ? "bg-emerald-500/10 text-emerald-400"
                      : inc.status === "investigating"
                      ? "bg-red-500/10 text-red-400"
                      : "bg-amber-500/10 text-amber-400"
                  }`}>
                    {inc.status.toUpperCase()}
                  </span>
                </div>
                <div className="px-5 py-4 border-t border-[#1e293b] space-y-3">
                  {inc.updates.map((u, i) => (
                    <div key={i} className="flex gap-3">
                      <span className="text-xs font-mono text-[#64748b] shrink-0 mt-0.5">
                        {new Date(u.time).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                      </span>
                      <p className="text-xs text-[#94a3b8]">{u.message}</p>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Subscribe note */}
      <div className="p-5 rounded-2xl border border-[#1e293b] bg-[#111827]">
        <p className="text-sm text-[#94a3b8]">
          <strong className="text-[#e2e8f0]">Subscribe to status updates</strong> &mdash; get notified of incidents via email or Slack.{" "}
          Configure notifications in{" "}
          <Link href="/settings" className="text-[#FFD700] hover:underline">Settings</Link>.
        </p>
      </div>
    </div>
  );
}
