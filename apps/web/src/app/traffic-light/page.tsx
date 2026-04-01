"use client";

import { Card } from "@/components/ui/card";
import { useState, useEffect } from "react";
import {
  CircleDot,
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Info,
} from "lucide-react";
import { useLocale } from "@/lib/useLocale";

/* ============================================================
 * Types
 * ============================================================ */

type TrafficStatus = "green" | "yellow" | "red";

interface ServiceStatus {
  id: string;
  name: string;
  status: TrafficStatus;
  uptime: string;
  message: string;
  lastChecked: string;
}

/* ============================================================
 * Demo Data
 * ============================================================ */

const DEMO_SERVICES: ServiceStatus[] = [
  { id: "web",           name: "Website",               status: "green",  uptime: "99.99%", message: "Website is healthy. All pages load within 200ms.",                  lastChecked: "just now" },
  { id: "api",           name: "API",                   status: "green",  uptime: "99.98%", message: "API is healthy. Response times are normal.",                        lastChecked: "just now" },
  { id: "checkout",      name: "Checkout",              status: "green",  uptime: "99.97%", message: "Checkout is healthy. Payments processing normally.",                 lastChecked: "just now" },
  { id: "auth",          name: "Login / Auth",          status: "green",  uptime: "99.99%", message: "Authentication is healthy. Users can log in normally.",              lastChecked: "just now" },
  { id: "db",            name: "Database",              status: "yellow", uptime: "99.91%", message: "Database is slower than usual. Investigating high query load.",       lastChecked: "2 min ago" },
  { id: "search",        name: "Search",                status: "green",  uptime: "99.95%", message: "Search is healthy. Results returning within 150ms.",                 lastChecked: "just now" },
  { id: "notifications", name: "Notifications",         status: "red",    uptime: "97.2%",  message: "Notifications are down. Email and SMS may be delayed. Team is investigating.", lastChecked: "5 min ago" },
  { id: "reports",       name: "Reports & Analytics",   status: "green",  uptime: "99.89%", message: "Reports are healthy. Dashboard data is up to date.",                 lastChecked: "just now" },
];

/* ============================================================
 * Helpers
 * ============================================================ */

function statusColor(status: TrafficStatus): string {
  if (status === "green") return "#22c55e";
  if (status === "yellow") return "#eab308";
  return "#ef4444";
}

function statusGlow(status: TrafficStatus): string {
  if (status === "green") return "0 0 24px rgba(34,197,94,0.4), 0 0 8px rgba(34,197,94,0.6)";
  if (status === "yellow") return "0 0 24px rgba(234,179,8,0.4), 0 0 8px rgba(234,179,8,0.6)";
  return "0 0 24px rgba(239,68,68,0.4), 0 0 8px rgba(239,68,68,0.6)";
}

function StatusIcon({ status, size = 16 }: { status: TrafficStatus; size?: number }) {
  if (status === "green")  return <CheckCircle2 size={size} style={{ color: statusColor(status) }} />;
  if (status === "yellow") return <AlertTriangle size={size} style={{ color: statusColor(status) }} />;
  return <XCircle size={size} style={{ color: statusColor(status) }} />;
}

/* ============================================================
 * Main Page
 * ============================================================ */

export default function TrafficLightPage() {
  useLocale();

  const [selected, setSelected] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState(new Date());
  const [countdown, setCountdown] = useState(30);

  // Auto-refresh countdown
  useEffect(() => {
    const interval = setInterval(() => {
      setCountdown((c) => {
        if (c <= 1) {
          setLastRefresh(new Date());
          return 30;
        }
        return c - 1;
      });
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  const greenCount  = DEMO_SERVICES.filter((s) => s.status === "green").length;
  const yellowCount = DEMO_SERVICES.filter((s) => s.status === "yellow").length;
  const redCount    = DEMO_SERVICES.filter((s) => s.status === "red").length;

  const overallStatus: TrafficStatus =
    redCount > 0 ? "red" : yellowCount > 0 ? "yellow" : "green";

  const overallMessage =
    redCount > 0
      ? `${redCount} issue${redCount > 1 ? "s" : ""} detected — some services are down`
      : yellowCount > 0
        ? `${yellowCount} service${yellowCount > 1 ? "s are" : " is"} degraded — monitoring closely`
        : "All systems operational";

  const selectedService = DEMO_SERVICES.find((s) => s.id === selected) ?? null;

  return (
    <div className="max-w-[1200px] mx-auto px-6 py-10">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold mb-1 flex items-center gap-3">
          <CircleDot size={24} className="text-[#FFD700]" />
          System Status
        </h1>
        <p className="text-[#94a3b8] text-sm">
          Simple status view for executives and non-technical stakeholders (Layer 1)
        </p>
      </div>

      {/* Overall Status Banner */}
      <div
        className={`mb-8 p-6 rounded-2xl border text-center transition-all ${
          overallStatus === "green"
            ? "border-green-500/30 bg-green-500/5"
            : overallStatus === "yellow"
              ? "border-yellow-500/30 bg-yellow-500/5"
              : "border-red-500/30 bg-red-500/5"
        }`}
      >
        <div
          className="w-16 h-16 rounded-full mx-auto mb-4 flex items-center justify-center"
          style={{
            backgroundColor: statusColor(overallStatus) + "20",
            boxShadow: statusGlow(overallStatus),
          }}
        >
          <StatusIcon status={overallStatus} size={32} />
        </div>
        <p
          className="text-xl font-bold mb-1"
          style={{ color: statusColor(overallStatus) }}
        >
          {overallMessage}
        </p>
        <p className="text-sm text-[#64748b]">
          {greenCount} healthy · {yellowCount > 0 ? `${yellowCount} degraded · ` : ""}{redCount > 0 ? `${redCount} down · ` : ""}Last updated {lastRefresh.toLocaleTimeString()}
        </p>
        <div className="mt-3 flex items-center justify-center gap-2 text-xs text-[#475569]">
          <RefreshCw size={11} />
          Auto-refresh in {countdown}s
        </div>
      </div>

      {/* Traffic Light Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4 mb-8">
        {DEMO_SERVICES.map((service) => {
          const isSelected = selected === service.id;

          return (
            <button
              key={service.id}
              className={`text-center p-5 rounded-2xl border transition-all hover:scale-105 active:scale-95 ${
                isSelected
                  ? "border-white/20 bg-white/5 scale-105"
                  : "border-[#1e293b] bg-white/[0.02] hover:border-[#334155]"
              }`}
              onClick={() => setSelected(isSelected ? null : service.id)}
            >
              {/* Big circle */}
              <div
                className="w-14 h-14 rounded-full mx-auto mb-3 flex items-center justify-center"
                style={{
                  backgroundColor: statusColor(service.status) + "25",
                  boxShadow: isSelected ? statusGlow(service.status) : `0 0 10px ${statusColor(service.status)}30`,
                  border: `2px solid ${statusColor(service.status)}50`,
                }}
              >
                <div
                  className="w-8 h-8 rounded-full"
                  style={{
                    backgroundColor: statusColor(service.status),
                    boxShadow: `0 0 8px ${statusColor(service.status)}80`,
                  }}
                />
              </div>

              <p className="text-sm font-semibold text-[#e2e8f0] truncate">{service.name}</p>
              <p
                className="text-xs mt-0.5 font-medium"
                style={{ color: statusColor(service.status) }}
              >
                {service.status === "green" ? "Healthy" : service.status === "yellow" ? "Degraded" : "Down"}
              </p>
              {service.status !== "red" && (
                <p className="text-[10px] text-[#475569] mt-0.5">{service.uptime} uptime</p>
              )}
            </button>
          );
        })}
      </div>

      {/* Detail Tooltip */}
      {selectedService && (
        <Card className={`mb-6 border-2 transition-all ${
          selectedService.status === "green"
            ? "border-green-500/30"
            : selectedService.status === "yellow"
              ? "border-yellow-500/30"
              : "border-red-500/30"
        }`}>
          <div className="flex items-start gap-4">
            <div
              className="w-12 h-12 rounded-full shrink-0 flex items-center justify-center"
              style={{
                backgroundColor: statusColor(selectedService.status) + "20",
                boxShadow: statusGlow(selectedService.status),
              }}
            >
              <StatusIcon status={selectedService.status} size={22} />
            </div>
            <div className="flex-1">
              <h3 className="text-lg font-bold text-[#e2e8f0] mb-1">{selectedService.name}</h3>
              <p className="text-sm text-[#94a3b8] leading-relaxed mb-3">{selectedService.message}</p>
              <div className="flex flex-wrap gap-4 text-xs text-[#64748b]">
                <span>Uptime: <strong className="text-[#94a3b8]">{selectedService.uptime}</strong></span>
                <span>Last checked: <strong className="text-[#94a3b8]">{selectedService.lastChecked}</strong></span>
              </div>
            </div>
            <button
              className="text-[#475569] hover:text-[#94a3b8] transition-colors p-1"
              onClick={() => setSelected(null)}
            >
              ×
            </button>
          </div>
        </Card>
      )}

      {/* Legend */}
      <Card className="bg-[#0a0e1a]/50">
        <h4 className="text-xs font-semibold text-[#475569] uppercase tracking-wider mb-3 flex items-center gap-2">
          <Info size={12} />
          How to read this dashboard
        </h4>
        <div className="grid sm:grid-cols-3 gap-4">
          {(["green", "yellow", "red"] as TrafficStatus[]).map((status) => (
            <div key={status} className="flex items-center gap-3">
              <div
                className="w-8 h-8 rounded-full shrink-0"
                style={{
                  backgroundColor: statusColor(status),
                  boxShadow: `0 0 8px ${statusColor(status)}50`,
                }}
              />
              <div>
                <p className="text-sm font-semibold" style={{ color: statusColor(status) }}>
                  {status === "green" ? "Green — Healthy" : status === "yellow" ? "Yellow — Degraded" : "Red — Down"}
                </p>
                <p className="text-xs text-[#64748b]">
                  {status === "green"
                    ? "Service is running normally"
                    : status === "yellow"
                      ? "Service is slower or partially available"
                      : "Service is unavailable, team is responding"}
                </p>
              </div>
            </div>
          ))}
        </div>
        <p className="text-xs text-[#475569] mt-4 border-t border-[#1e293b] pt-3">
          Click any service circle to see a plain-language explanation. This dashboard auto-refreshes every 30 seconds. For technical details, see the APM or Dashboard pages.
        </p>
      </Card>
    </div>
  );
}
