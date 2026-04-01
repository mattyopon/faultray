"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useState } from "react";
import {
  GitBranch,
  AlertTriangle,
  Users,
  CheckCircle2,
  XCircle,
  ChevronRight,
  Info,
  ArrowRight,
} from "lucide-react";
import { useLocale } from "@/lib/useLocale";

/* ============================================================
 * Types
 * ============================================================ */

type ServiceStatus = "green" | "yellow" | "red";

interface Service {
  id: string;
  name: string;
  description: string;
  ownerCount: number;
  status: ServiceStatus;
  dependsOn: string[];
  dependents: string[];
  personalizationAlert: boolean;
}

/* ============================================================
 * Demo Data
 * ============================================================ */

const DEMO_SERVICES: Service[] = [
  {
    id: "web",
    name: "Web Frontend",
    description: "React SPA served via CDN",
    ownerCount: 6,
    status: "green",
    dependsOn: ["api"],
    dependents: [],
    personalizationAlert: false,
  },
  {
    id: "api",
    name: "API Gateway",
    description: "Main REST API — handles all client requests",
    ownerCount: 4,
    status: "green",
    dependsOn: ["db", "cache", "auth"],
    dependents: ["web", "mobile"],
    personalizationAlert: false,
  },
  {
    id: "db",
    name: "PostgreSQL DB",
    description: "Primary relational database (RDS)",
    ownerCount: 2,
    status: "yellow",
    dependsOn: [],
    dependents: ["api", "analytics"],
    personalizationAlert: true,
  },
  {
    id: "cache",
    name: "Redis Cache",
    description: "In-memory cache layer for sessions and hot data",
    ownerCount: 1,
    status: "green",
    dependsOn: [],
    dependents: ["api"],
    personalizationAlert: true,
  },
  {
    id: "auth",
    name: "Auth Service",
    description: "OAuth2 / JWT authentication microservice",
    ownerCount: 3,
    status: "green",
    dependsOn: ["db"],
    dependents: ["api", "mobile"],
    personalizationAlert: false,
  },
  {
    id: "mobile",
    name: "Mobile Backend",
    description: "BFF layer for iOS/Android clients",
    ownerCount: 3,
    status: "green",
    dependsOn: ["api", "auth"],
    dependents: [],
    personalizationAlert: false,
  },
  {
    id: "analytics",
    name: "Analytics Pipeline",
    description: "Event streaming and BI data export",
    ownerCount: 2,
    status: "green",
    dependsOn: ["db"],
    dependents: [],
    personalizationAlert: false,
  },
  {
    id: "notifications",
    name: "Notification Service",
    description: "Email/SMS/Push notification dispatcher",
    ownerCount: 1,
    status: "red",
    dependsOn: ["api"],
    dependents: [],
    personalizationAlert: true,
  },
];

/* ============================================================
 * Helpers
 * ============================================================ */

function statusColor(status: ServiceStatus): string {
  if (status === "green") return "#10b981";
  if (status === "yellow") return "#f59e0b";
  return "#ef4444";
}

function statusLabel(status: ServiceStatus): string {
  if (status === "green") return "Healthy";
  if (status === "yellow") return "Degraded";
  return "Down";
}

function statusVariant(status: ServiceStatus): "green" | "yellow" | "red" {
  return status;
}

function TrafficLight({ status }: { status: ServiceStatus }) {
  return (
    <div
      className="w-4 h-4 rounded-full shrink-0 shadow-lg"
      style={{
        backgroundColor: statusColor(status),
        boxShadow: `0 0 8px ${statusColor(status)}60`,
      }}
    />
  );
}

function computeBlastRadius(serviceId: string, services: Service[]): Service[] {
  // BFS: find all services that transitively depend on this service
  const visited = new Set<string>();
  const queue = [serviceId];
  const affected: Service[] = [];

  while (queue.length > 0) {
    const current = queue.shift()!;
    if (visited.has(current)) continue;
    visited.add(current);

    for (const svc of services) {
      if (svc.dependsOn.includes(current) && !visited.has(svc.id)) {
        affected.push(svc);
        queue.push(svc.id);
      }
    }
  }

  return affected;
}

/* ============================================================
 * Main Page
 * ============================================================ */

export default function DependenciesPage() {
  useLocale();

  const [selectedService, setSelectedService] = useState<string | null>(null);

  const selected = DEMO_SERVICES.find((s) => s.id === selectedService) ?? null;
  const blastRadius = selectedService ? computeBlastRadius(selectedService, DEMO_SERVICES) : [];
  const alertCount = DEMO_SERVICES.filter((s) => s.personalizationAlert).length;
  const downCount = DEMO_SERVICES.filter((s) => s.status === "red").length;

  return (
    <div className="max-w-[1200px] mx-auto px-6 py-10">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold mb-1 flex items-center gap-3">
          <GitBranch size={24} className="text-[#FFD700]" />
          Dependency Map
        </h1>
        <p className="text-[#94a3b8] text-sm">
          "If X stops, what breaks?" — Blast radius analysis for non-engineers (Layer 1)
        </p>
      </div>

      {/* Summary */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        {[
          { label: "Total Services", value: DEMO_SERVICES.length, color: "#e2e8f0" },
          { label: "Down / Critical", value: downCount, color: "#ef4444" },
          { label: "Personalization Alerts", value: alertCount, color: "#f59e0b" },
          { label: "Healthy", value: DEMO_SERVICES.filter((s) => s.status === "green").length, color: "#10b981" },
        ].map((stat) => (
          <Card key={stat.label} className="text-center">
            <p className="text-xs text-[#64748b] uppercase tracking-wider mb-1">{stat.label}</p>
            <p className="text-3xl font-extrabold font-mono" style={{ color: stat.color }}>{stat.value}</p>
          </Card>
        ))}
      </div>

      {/* Personalization Alert Banner */}
      {alertCount > 0 && (
        <div className="mb-6 p-4 rounded-xl border border-yellow-500/30 bg-yellow-500/5 flex items-start gap-3">
          <AlertTriangle size={18} className="text-yellow-400 shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-semibold text-yellow-300">
              Personalization Alert: {alertCount} services with ≤2 owners
            </p>
            <p className="text-xs text-[#94a3b8] mt-0.5">
              These services are a knowledge risk. If the owner leaves or is unavailable, the team may not be able to respond to incidents.
            </p>
          </div>
        </div>
      )}

      <div className="grid lg:grid-cols-5 gap-6">
        {/* Service Grid */}
        <div className="lg:col-span-3">
          <Card>
            <h3 className="text-sm font-semibold text-[#94a3b8] uppercase tracking-wider mb-4 flex items-center gap-2">
              <GitBranch size={14} />
              Services · Click to see blast radius
            </h3>
            <div className="grid sm:grid-cols-2 gap-3">
              {DEMO_SERVICES.map((svc) => {
                const isSelected = selectedService === svc.id;
                const isAffected = blastRadius.some((b) => b.id === svc.id);

                return (
                  <button
                    key={svc.id}
                    className={`text-left p-4 rounded-xl border transition-all ${
                      isSelected
                        ? "border-[#FFD700]/40 bg-[#FFD700]/5"
                        : isAffected
                          ? "border-red-500/30 bg-red-500/5"
                          : "border-[#1e293b] bg-white/[0.02] hover:bg-white/[0.04] hover:border-[#334155]"
                    }`}
                    onClick={() => setSelectedService(isSelected ? null : svc.id)}
                  >
                    <div className="flex items-start justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <TrafficLight status={svc.status} />
                        <span className="text-sm font-semibold text-[#e2e8f0]">{svc.name}</span>
                      </div>
                      {svc.personalizationAlert && (
                        <AlertTriangle size={14} className="text-yellow-400 shrink-0" />
                      )}
                    </div>

                    <p className="text-xs text-[#64748b] mb-3 leading-relaxed">{svc.description}</p>

                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-1.5 text-xs text-[#64748b]">
                        <Users size={12} />
                        <span>
                          {svc.ownerCount} {svc.ownerCount === 1 ? "owner" : "owners"}
                        </span>
                        {svc.personalizationAlert && (
                          <span className="text-yellow-400 font-medium">⚠ Risk</span>
                        )}
                      </div>
                      <Badge variant={statusVariant(svc.status)}>
                        {statusLabel(svc.status)}
                      </Badge>
                    </div>

                    {svc.dependsOn.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1">
                        <span className="text-[10px] text-[#475569]">depends on:</span>
                        {svc.dependsOn.map((dep) => (
                          <span key={dep} className="text-[10px] bg-white/5 px-1.5 rounded text-[#94a3b8]">{dep}</span>
                        ))}
                      </div>
                    )}
                  </button>
                );
              })}
            </div>
          </Card>
        </div>

        {/* Blast Radius Panel */}
        <div className="lg:col-span-2">
          <Card className="sticky top-24">
            <h3 className="text-sm font-semibold text-[#94a3b8] uppercase tracking-wider mb-4 flex items-center gap-2">
              <AlertTriangle size={14} />
              Blast Radius
            </h3>

            {!selected ? (
              <div className="text-center py-8">
                <GitBranch size={32} className="text-[#1e293b] mx-auto mb-3" />
                <p className="text-sm text-[#64748b]">Select a service to see<br />what breaks if it stops.</p>
              </div>
            ) : (
              <div>
                {/* Selected service */}
                <div className="p-3 rounded-xl border border-[#FFD700]/30 bg-[#FFD700]/5 mb-4">
                  <div className="flex items-center gap-2 mb-1">
                    <TrafficLight status={selected.status} />
                    <span className="text-sm font-bold text-[#FFD700]">{selected.name}</span>
                  </div>
                  <p className="text-xs text-[#94a3b8]">{selected.description}</p>
                </div>

                <div className="flex items-center gap-2 mb-3">
                  <ArrowRight size={14} className="text-red-400" />
                  <span className="text-xs text-[#94a3b8]">
                    If this stops, <strong className="text-red-400">{blastRadius.length}</strong> service{blastRadius.length !== 1 ? "s" : ""} will be affected:
                  </span>
                </div>

                {blastRadius.length === 0 ? (
                  <div className="flex items-center gap-2 p-3 rounded-lg bg-emerald-500/5 border border-emerald-500/15">
                    <CheckCircle2 size={14} className="text-emerald-400 shrink-0" />
                    <p className="text-xs text-[#94a3b8]">No downstream dependents. Safe to take offline.</p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {blastRadius.map((affected) => (
                      <div
                        key={affected.id}
                        className="flex items-center gap-3 p-3 rounded-lg bg-red-500/5 border border-red-500/15"
                      >
                        <XCircle size={14} className="text-red-400 shrink-0" />
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-[#e2e8f0]">{affected.name}</p>
                          <p className="text-xs text-[#64748b] truncate">{affected.description}</p>
                        </div>
                        <TrafficLight status={affected.status} />
                      </div>
                    ))}

                    <div className="mt-3 p-3 rounded-lg border border-[#1e293b] bg-white/[0.02]">
                      <p className="text-xs text-[#64748b] flex items-start gap-1">
                        <Info size={11} className="shrink-0 mt-0.5" />
                        Total users impacted by this outage: estimate{" "}
                        <strong className="text-[#94a3b8] ml-1">
                          {blastRadius.some((s) => s.id === "web" || s.id === "api") ? "100%" : "partial"}
                        </strong>
                      </p>
                    </div>
                  </div>
                )}

                {/* Owners */}
                <div className="mt-4 pt-4 border-t border-[#1e293b]">
                  <p className="text-xs text-[#64748b] mb-2 flex items-center gap-1">
                    <Users size={11} />
                    Service owners:
                  </p>
                  <div className="flex gap-2">
                    {Array.from({ length: selected.ownerCount }).map((_, i) => (
                      <div
                        key={i}
                        className="w-7 h-7 rounded-full bg-[#1e293b] border border-[#334155] flex items-center justify-center text-xs text-[#64748b]"
                      >
                        {String.fromCharCode(65 + i)}
                      </div>
                    ))}
                    {selected.personalizationAlert && (
                      <span className="flex items-center gap-1 text-xs text-yellow-400 ml-1">
                        <AlertTriangle size={11} />
                        High risk
                      </span>
                    )}
                  </div>
                </div>
              </div>
            )}
          </Card>

          {/* Legend */}
          <Card className="mt-4">
            <h4 className="text-xs font-semibold text-[#64748b] uppercase tracking-wider mb-3">Legend</h4>
            <div className="space-y-2">
              {(["green", "yellow", "red"] as ServiceStatus[]).map((status) => (
                <div key={status} className="flex items-center gap-3 text-xs text-[#94a3b8]">
                  <TrafficLight status={status} />
                  <span>{statusLabel(status)} — {status === "green" ? "operating normally" : status === "yellow" ? "degraded performance" : "service is down"}</span>
                </div>
              ))}
              <div className="flex items-center gap-3 text-xs text-[#94a3b8]">
                <AlertTriangle size={14} className="text-yellow-400" />
                <span>Personalization alert: ≤2 people know this service</span>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
