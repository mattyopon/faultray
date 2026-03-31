"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useState, useEffect, useCallback, useMemo, memo } from "react";
import {
  Activity,
  Cpu,
  HardDrive,
  Wifi,
  AlertTriangle,
  Server,
  RefreshCw,
  Download,
  Radio,
  ChevronDown,
  ChevronUp,
  CheckCircle,
  ArrowUpRight,
  ArrowDownRight,
  Minus,
  Network,
} from "lucide-react";
import { useLocale } from "@/lib/useLocale";
import { appDict } from "@/i18n/app-dict";
import { api, type ApmAgent, type ApmMetricPoint, type ApmAlert } from "@/lib/api";

/* ============================================================
 * Constants
 * ============================================================ */

const AGENT_COLORS = [
  "#10b981", // emerald
  "#3b82f6", // blue
  "#f59e0b", // amber
  "#ef4444", // red
  "#8b5cf6", // violet
  "#ec4899", // pink
  "#14b8a6", // teal
  "#f97316", // orange
];

type TimeRange = "5m" | "15m" | "1h" | "6h" | "24h" | "7d" | "30d";

const TIME_RANGES: TimeRange[] = ["5m", "15m", "1h", "6h", "24h", "7d", "30d"];

/* ============================================================
 * Mock Data — Realistic with per-agent time series
 * ============================================================ */

// Generate a sinusoidal + noise time series
function makeTimeSeries(
  baseVal: number,
  amplitude: number,
  periodFactor: number,
  count: number,
  startEpoch: number,
  intervalSec: number,
  drift = 0,
): ApmMetricPoint[] {
  return Array.from({ length: count }, (_, i) => {
    const phase = (i / count) * Math.PI * 2 * periodFactor;
    const noise = (Math.random() - 0.5) * amplitude * 0.4;
    const driftVal = drift * (i / count);
    const raw = baseVal + Math.sin(phase) * amplitude * 0.6 + noise + driftVal;
    return {
      metric_name: "cpu_percent",
      value: Math.max(0, Math.min(100, raw)),
      sample_count: Math.floor(Math.random() * 10) + 1,
      bucket_epoch: startEpoch + i * intervalSec,
    };
  });
}

function getPointsForRange(range: TimeRange): { count: number; intervalSec: number } {
  switch (range) {
    case "5m":  return { count: 60,  intervalSec: 5 };
    case "15m": return { count: 60,  intervalSec: 15 };
    case "1h":  return { count: 60,  intervalSec: 60 };
    case "6h":  return { count: 72,  intervalSec: 300 };
    case "24h": return { count: 288, intervalSec: 300 };
    case "7d":  return { count: 168, intervalSec: 3600 };
    case "30d": return { count: 180, intervalSec: 14400 };
  }
}

interface AgentTimeSeries {
  cpu: ApmMetricPoint[];
  mem: ApmMetricPoint[];
  netSent: ApmMetricPoint[];
  netRecv: ApmMetricPoint[];
  load1: ApmMetricPoint[];
  load5: ApmMetricPoint[];
  load15: ApmMetricPoint[];
}

function generateAllMockSeries(range: TimeRange): Record<string, AgentTimeSeries> {
  const { count, intervalSec } = getPointsForRange(range);
  const startEpoch = Math.floor(Date.now() / 1000) - count * intervalSec;

  const agents = {
    "agent-001": {
      cpu:     makeTimeSeries(35,  25, 2,   count, startEpoch, intervalSec),
      mem:     makeTimeSeries(62,  15, 1.5, count, startEpoch, intervalSec),
      netSent: makeTimeSeries(450, 300, 3,  count, startEpoch, intervalSec),
      netRecv: makeTimeSeries(820, 400, 2.5, count, startEpoch, intervalSec),
      load1:   makeTimeSeries(1.2, 0.8, 2,  count, startEpoch, intervalSec),
      load5:   makeTimeSeries(1.1, 0.5, 1.5, count, startEpoch, intervalSec),
      load15:  makeTimeSeries(1.0, 0.3, 1,  count, startEpoch, intervalSec),
    },
    "agent-002": {
      cpu:     makeTimeSeries(72,  20, 3,   count, startEpoch, intervalSec),
      mem:     makeTimeSeries(78,  10, 1,   count, startEpoch, intervalSec, 7), // memory leak pattern
      netSent: makeTimeSeries(1200, 600, 4, count, startEpoch, intervalSec),
      netRecv: makeTimeSeries(3400, 1200, 3, count, startEpoch, intervalSec),
      load1:   makeTimeSeries(3.5, 1.5, 3,  count, startEpoch, intervalSec),
      load5:   makeTimeSeries(3.2, 0.8, 2,  count, startEpoch, intervalSec),
      load15:  makeTimeSeries(3.0, 0.4, 1,  count, startEpoch, intervalSec),
    },
    "agent-003": {
      cpu:     makeTimeSeries(88,  10, 2,   count, startEpoch, intervalSec),
      mem:     makeTimeSeries(78,  8,  1.5, count, startEpoch, intervalSec),
      netSent: makeTimeSeries(200, 100, 2,  count, startEpoch, intervalSec),
      netRecv: makeTimeSeries(310, 120, 1.5, count, startEpoch, intervalSec),
      load1:   makeTimeSeries(4.8, 1.2, 2,  count, startEpoch, intervalSec),
      load5:   makeTimeSeries(4.5, 0.6, 1.5, count, startEpoch, intervalSec),
      load15:  makeTimeSeries(4.2, 0.3, 1,  count, startEpoch, intervalSec),
    },
    "agent-004": {
      cpu:     makeTimeSeries(0,   0,   1,   count, startEpoch, intervalSec),
      mem:     makeTimeSeries(0,   0,   1,   count, startEpoch, intervalSec),
      netSent: makeTimeSeries(0,   0,   1,   count, startEpoch, intervalSec),
      netRecv: makeTimeSeries(0,   0,   1,   count, startEpoch, intervalSec),
      load1:   makeTimeSeries(0,   0,   1,   count, startEpoch, intervalSec),
      load5:   makeTimeSeries(0,   0,   1,   count, startEpoch, intervalSec),
      load15:  makeTimeSeries(0,   0,   1,   count, startEpoch, intervalSec),
    },
  };

  return agents;
}

const MOCK_AGENTS: ApmAgent[] = [
  {
    agent_id: "agent-001",
    hostname: "web-server-01",
    ip_address: "10.0.1.10",
    status: "running",
    os_info: "Ubuntu 22.04",
    last_seen: new Date(Date.now() - 15000).toISOString(),
    cpu_percent: 34.2,
    memory_percent: 61.8,
    disk_percent: 45.0,
  },
  {
    agent_id: "agent-002",
    hostname: "api-server-02",
    ip_address: "10.0.1.11",
    status: "running",
    os_info: "Ubuntu 22.04",
    last_seen: new Date(Date.now() - 30000).toISOString(),
    cpu_percent: 72.5,
    memory_percent: 85.3,
    disk_percent: 62.1,
  },
  {
    agent_id: "agent-003",
    hostname: "db-server-01",
    ip_address: "10.0.1.20",
    status: "degraded",
    os_info: "Debian 12",
    last_seen: new Date(Date.now() - 120000).toISOString(),
    cpu_percent: 91.3,
    memory_percent: 78.2,
    disk_percent: 88.7,
  },
  {
    agent_id: "agent-004",
    hostname: "cache-server-01",
    ip_address: "10.0.1.30",
    status: "offline",
    os_info: "CentOS 8",
    last_seen: new Date(Date.now() - 900000).toISOString(),
    cpu_percent: undefined,
    memory_percent: undefined,
    disk_percent: undefined,
  },
];

interface MockProcess {
  pid: number;
  name: string;
  cpu: number;
  mem: number;
  threads: number;
  status: string;
}

const MOCK_PROCESSES: MockProcess[] = [
  { pid: 1842, name: "postgres",       cpu: 42.1, mem: 28.3, threads: 18, status: "running" },
  { pid: 3201, name: "node",           cpu: 31.7, mem: 14.2, threads: 12, status: "running" },
  { pid: 4510, name: "nginx",          cpu: 18.3, mem: 3.1,  threads: 8,  status: "running" },
  { pid: 2340, name: "redis-server",   cpu: 12.8, mem: 6.7,  threads: 4,  status: "running" },
  { pid: 5901, name: "python3",        cpu: 9.4,  mem: 11.2, threads: 6,  status: "running" },
  { pid: 1120, name: "java",           cpu: 8.1,  mem: 35.8, threads: 24, status: "running" },
  { pid: 6230, name: "mysqld",         cpu: 5.6,  mem: 18.4, threads: 16, status: "running" },
  { pid: 2890, name: "ruby",           cpu: 4.2,  mem: 8.9,  threads: 3,  status: "running" },
  { pid: 7120, name: "mongod",         cpu: 3.8,  mem: 22.1, threads: 14, status: "running" },
  { pid: 3450, name: "go-server",      cpu: 2.9,  mem: 4.3,  threads: 8,  status: "running" },
  { pid: 8901, name: "elasticsearch",  cpu: 2.1,  mem: 41.2, threads: 20, status: "running" },
  { pid: 1560, name: "sshd",           cpu: 0.4,  mem: 0.8,  threads: 2,  status: "running" },
  { pid: 2001, name: "systemd",        cpu: 0.2,  mem: 1.1,  threads: 1,  status: "running" },
  { pid: 4780, name: "cron",           cpu: 0.1,  mem: 0.3,  threads: 1,  status: "sleeping" },
  { pid: 9012, name: "logrotate",      cpu: 0.0,  mem: 0.2,  threads: 1,  status: "sleeping" },
];

const MOCK_ALERTS: ApmAlert[] = [
  {
    id: "alert-001",
    severity: "CRITICAL",
    rule_name: "High CPU Usage",
    agent_id: "agent-003",
    metric_name: "cpu_percent",
    metric_value: 91.3,
    threshold: 90.0,
    fired_at: new Date(Date.now() - 300000).toISOString(),
  },
  {
    id: "alert-002",
    severity: "WARNING",
    rule_name: "High Memory Usage",
    agent_id: "agent-002",
    metric_name: "memory_usage_percent",
    metric_value: 85.3,
    threshold: 80.0,
    fired_at: new Date(Date.now() - 600000).toISOString(),
  },
  {
    id: "alert-003",
    severity: "WARNING",
    rule_name: "High Disk Usage",
    agent_id: "agent-003",
    metric_name: "disk_percent",
    threshold: 85.0,
    metric_value: 88.7,
    fired_at: new Date(Date.now() - 1200000).toISOString(),
  },
  {
    id: "alert-004",
    severity: "INFO",
    rule_name: "Agent Offline",
    agent_id: "agent-004",
    metric_name: "heartbeat",
    metric_value: 0,
    threshold: 1,
    fired_at: new Date(Date.now() - 900000).toISOString(),
  },
];

/* ============================================================
 * Helper functions
 * ============================================================ */

function metricColor(v: number | undefined, warn = 70, crit = 85): string {
  if (v === undefined) return "#64748b";
  if (v >= crit) return "#ef4444";
  if (v >= warn) return "#f59e0b";
  return "#10b981";
}

function statusDotColor(status: string): string {
  switch (status) {
    case "running":  return "#10b981";
    case "degraded": return "#f59e0b";
    case "offline":  return "#ef4444";
    default:         return "#64748b";
  }
}

function statusBadgeVariant(status: string): "green" | "yellow" | "red" | "default" {
  switch (status) {
    case "running":  return "green";
    case "degraded": return "yellow";
    case "offline":  return "red";
    default:         return "default";
  }
}

function severityBadgeVariant(severity: string): "red" | "yellow" | "default" {
  switch (severity) {
    case "CRITICAL": return "red";
    case "WARNING":  return "yellow";
    default:         return "default";
  }
}

function severityDotColor(severity: string): string {
  switch (severity) {
    case "CRITICAL": return "#ef4444";
    case "WARNING":  return "#f59e0b";
    default:         return "#3b82f6";
  }
}

function formatRelative(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const s = Math.floor(diff / 1000);
  if (s < 60)  return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60)  return `${m}m ago`;
  const h = Math.floor(m / 60);
  return `${h}h ago`;
}

function formatBytes(val: number): string {
  if (val >= 1_000_000) return `${(val / 1_000_000).toFixed(1)} MB/s`;
  if (val >= 1_000)     return `${(val / 1_000).toFixed(1)} KB/s`;
  return `${val.toFixed(0)} B/s`;
}

function trendArrow(points: ApmMetricPoint[]): "up" | "down" | "stable" {
  if (points.length < 4) return "stable";
  const recent = points.slice(-4).reduce((s, p) => s + p.value, 0) / 4;
  const older  = points.slice(-8, -4).reduce((s, p) => s + p.value, 0) / 4;
  if (recent > older + 2) return "up";
  if (recent < older - 2) return "down";
  return "stable";
}

function trendPct(points: ApmMetricPoint[]): number {
  if (points.length < 8) return 0;
  const recent = points.slice(-4).reduce((s, p) => s + p.value, 0) / 4;
  const older  = points.slice(-8, -4).reduce((s, p) => s + p.value, 0) / 4;
  if (older === 0) return 0;
  return ((recent - older) / older) * 100;
}

/* ============================================================
 * Sparkline (30px tall inline SVG)
 * ============================================================ */

const Sparkline = memo(function Sparkline({
  points,
  color,
  width = 80,
  height = 30,
}: {
  points: number[];
  color: string;
  width?: number;
  height?: number;
}) {
  if (points.length < 2) return null;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const range = max - min || 1;
  const toX = (i: number) => (i / (points.length - 1)) * width;
  const toY = (v: number) => height - ((v - min) / range) * (height - 2) - 1;
  const d = points.map((v, i) => `${i === 0 ? "M" : "L"}${toX(i).toFixed(1)},${toY(v).toFixed(1)}`).join(" ");
  const areaD = `${d} L${toX(points.length - 1).toFixed(1)},${height} L0,${height} Z`;
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} className="shrink-0">
      <path d={areaD} fill={color} opacity={0.15} />
      <path d={d} fill="none" stroke={color} strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
});

/* ============================================================
 * Progress bar
 * ============================================================ */

function ProgressBar({ value, warn = 70, crit = 85, width = "100%" }: {
  value: number | undefined;
  warn?: number;
  crit?: number;
  width?: string;
}) {
  const pct = Math.min(100, Math.max(0, value ?? 0));
  const color = metricColor(value, warn, crit);
  return (
    <div className="h-1.5 rounded-full bg-[#1e293b] overflow-hidden" style={{ width }}>
      <div
        className="h-full rounded-full transition-all"
        style={{ width: `${pct}%`, backgroundColor: color }}
      />
    </div>
  );
}

/* ============================================================
 * Multi-agent line chart (full panel)
 * ============================================================ */

interface ChartSeries {
  label: string;
  color: string;
  points: ApmMetricPoint[];
}

const MetricsPanel = memo(function MetricsPanel({
  title,
  series,
  unit = "%",
  yMax = 100,
}: {
  title: string;
  series: ChartSeries[];
  unit?: string;
  yMax?: number;
}) {
  const W = 560;
  const H = 140;
  const PAD = { top: 12, right: 12, bottom: 28, left: 42 };
  const cW = W - PAD.left - PAD.right;
  const cH = H - PAD.top - PAD.bottom;

  const allPoints = series.flatMap((s) => s.points.map((p) => p.value));
  const dynMax = allPoints.length > 0 ? Math.max(...allPoints, 1) : yMax;
  const effectiveMax = unit === "%" ? Math.max(dynMax, 10) : Math.max(dynMax, 1);

  const toX = (i: number, total: number) =>
    PAD.left + (total <= 1 ? cW / 2 : (i / (total - 1)) * cW);
  const toY = (v: number) =>
    PAD.top + cH - (v / effectiveMax) * cH;

  const gridVals = unit === "%"
    ? [0, 25, 50, 75, 100].filter((v) => v <= effectiveMax)
    : [0, effectiveMax * 0.25, effectiveMax * 0.5, effectiveMax * 0.75, effectiveMax];

  return (
    <div>
      <p className="text-xs text-[#64748b] uppercase tracking-wider mb-2 font-medium">{title}</p>
      <div className="relative">
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full" preserveAspectRatio="none">
          {/* Grid */}
          {gridVals.map((val) => {
            const y = toY(val);
            if (y < PAD.top - 1) return null;
            return (
              <g key={val}>
                <line x1={PAD.left} x2={W - PAD.right} y1={y} y2={y} stroke="#1e293b" strokeWidth={1} />
                <text x={PAD.left - 4} y={y + 3.5} textAnchor="end" fill="#475569" fontSize={8} fontFamily="monospace">
                  {unit === "%" ? `${Math.round(val)}%` : formatBytes(val)}
                </text>
              </g>
            );
          })}

          {/* Series */}
          {series.map((s) => {
            if (s.points.length < 2) return null;
            const d = s.points
              .map((p, i) => `${i === 0 ? "M" : "L"}${toX(i, s.points.length).toFixed(1)},${toY(p.value).toFixed(1)}`)
              .join(" ");
            const last = s.points[s.points.length - 1];
            const areaD = `${d} L${toX(s.points.length - 1, s.points.length).toFixed(1)},${(PAD.top + cH).toFixed(1)} L${PAD.left.toFixed(1)},${(PAD.top + cH).toFixed(1)} Z`;
            return (
              <g key={s.label}>
                <path d={areaD} fill={s.color} opacity={0.06} />
                <path d={d} fill="none" stroke={s.color} strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" />
                <circle
                  cx={toX(s.points.length - 1, s.points.length)}
                  cy={toY(last.value)}
                  r={2.5}
                  fill={s.color}
                  stroke="#111827"
                  strokeWidth={1.5}
                />
              </g>
            );
          })}

          {/* X-axis time labels */}
          {series[0]?.points && (() => {
            const pts = series[0].points;
            const idxs = [0, Math.floor(pts.length / 4), Math.floor(pts.length / 2), Math.floor((pts.length * 3) / 4), pts.length - 1];
            return idxs.map((idx) => {
              if (idx >= pts.length) return null;
              const d = new Date(pts[idx].bucket_epoch * 1000);
              const lbl = `${d.getHours().toString().padStart(2, "0")}:${d.getMinutes().toString().padStart(2, "0")}`;
              return (
                <text key={idx} x={toX(idx, pts.length)} y={H - 4} textAnchor="middle" fill="#475569" fontSize={8}>
                  {lbl}
                </text>
              );
            });
          })()}
        </svg>
      </div>
      {/* Legend */}
      {series.length > 1 && (
        <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2">
          {series.map((s) => (
            <div key={s.label} className="flex items-center gap-1.5 text-xs text-[#64748b]">
              <span className="w-2.5 h-0.5 rounded" style={{ backgroundColor: s.color, display: "inline-block" }} />
              {s.label}
            </div>
          ))}
        </div>
      )}
    </div>
  );
});

/* ============================================================
 * Stat Card with sparkline
 * ============================================================ */

function StatCard({
  label,
  value,
  unit,
  sparkPoints,
  color,
  trend,
  trendPctVal,
  icon,
}: {
  label: string;
  value: string;
  unit: string;
  sparkPoints: number[];
  color: string;
  trend: "up" | "down" | "stable";
  trendPctVal: number;
  icon: React.ReactNode;
}) {
  const TrendIcon = trend === "up" ? ArrowUpRight : trend === "down" ? ArrowDownRight : Minus;
  const trendColorCls = trend === "up" ? "text-red-400" : trend === "down" ? "text-emerald-400" : "text-[#64748b]";
  return (
    <Card>
      <div className="flex items-start justify-between mb-3">
        <p className="text-xs text-[#64748b] uppercase tracking-wider font-medium">{label}</p>
        <span className="text-[#64748b]">{icon}</span>
      </div>
      <div className="flex items-end justify-between gap-2">
        <div>
          <p className="text-2xl font-extrabold font-mono leading-none" style={{ color }}>
            {value}
            <span className="text-base font-normal text-[#64748b] ml-0.5">{unit}</span>
          </p>
          <div className={`flex items-center gap-0.5 mt-1 text-xs ${trendColorCls}`}>
            <TrendIcon size={11} />
            <span>{Math.abs(trendPctVal).toFixed(1)}%</span>
          </div>
        </div>
        <Sparkline points={sparkPoints} color={color} />
      </div>
    </Card>
  );
}

/* ============================================================
 * Infrastructure host card
 * ============================================================ */

function HostCard({
  agent,
  color,
  selected,
  onClick,
  seriesData,
}: {
  agent: ApmAgent;
  color: string;
  selected: boolean;
  onClick: () => void;
  seriesData?: AgentTimeSeries;
}) {
  const cpuPts = seriesData?.cpu.slice(-20).map((p) => p.value) ?? [];
  return (
    <div
      onClick={onClick}
      className={`rounded-lg border p-3 cursor-pointer transition-all ${
        selected
          ? "border-[#FFD700]/40 bg-[#FFD700]/5"
          : "border-[#1e293b] bg-[#111827] hover:border-[#334155]"
      }`}
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span
            className="w-2 h-2 rounded-full shrink-0"
            style={{ backgroundColor: statusDotColor(agent.status) }}
          />
          <span className="font-semibold text-sm text-[#e2e8f0]">{agent.hostname}</span>
          <span className="text-xs text-[#64748b] font-mono">{agent.ip_address}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-[#475569]">{agent.os_info}</span>
          {selected && (
            <span className="text-xs px-1.5 py-0.5 rounded bg-[#FFD700]/10 text-[#FFD700] border border-[#FFD700]/20 font-medium">
              selected
            </span>
          )}
        </div>
      </div>
      <div className="grid grid-cols-3 gap-3 mb-2">
        {[
          { label: "CPU", val: agent.cpu_percent, warn: 70, crit: 85 },
          { label: "MEM", val: agent.memory_percent, warn: 75, crit: 90 },
          { label: "DISK", val: agent.disk_percent, warn: 80, crit: 90 },
        ].map(({ label, val, warn, crit }) => (
          <div key={label}>
            <div className="flex justify-between text-xs mb-1">
              <span className="text-[#64748b]">{label}</span>
              <span className="font-mono" style={{ color: metricColor(val, warn, crit) }}>
                {val !== undefined ? `${val.toFixed(0)}%` : "—"}
              </span>
            </div>
            <ProgressBar value={val} warn={warn} crit={crit} />
          </div>
        ))}
      </div>
      {cpuPts.length > 2 && (
        <div className="flex items-center gap-2">
          <Sparkline points={cpuPts} color={color} width={100} height={20} />
          <span className="text-xs text-[#475569]">CPU trend</span>
        </div>
      )}
    </div>
  );
}

/* ============================================================
 * Main Page
 * ============================================================ */

export default function ApmPage() {
  const locale = useLocale();
  const t = appDict.apm[locale] ?? appDict.apm.en;

  const [agents, setAgents] = useState<ApmAgent[]>([]);
  const [alerts, setAlerts] = useState<ApmAlert[]>([]);
  const [allSeries, setAllSeries] = useState<Record<string, AgentTimeSeries>>({});
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [timeRange, setTimeRange] = useState<TimeRange>("1h");
  const [showSetup, setShowSetup] = useState(false);
  const [processSearch, setProcessSearch] = useState("");
  const [processSortKey, setProcessSortKey] = useState<"cpu" | "mem" | "pid" | "name" | "threads">("cpu");
  const [processSortAsc, setProcessSortAsc] = useState(false);
  const [acknowledgedAlerts, setAcknowledgedAlerts] = useState<Set<string>>(new Set());

  const loadData = useCallback(async (silent = false) => {
    if (silent) setRefreshing(true);
    else setLoading(true);
    try {
      let token: string | undefined;
      try {
        const session = localStorage.getItem("faultray_session");
        if (session) {
          const parsed = JSON.parse(session) as { access_token?: string };
          token = parsed.access_token;
        }
      } catch { /* ignore */ }

      const [agentsData, alertsData] = await Promise.all([
        api.getApmAgents(token),
        api.getApmAlerts(undefined, token),
      ]);
      if (agentsData.length > 0) {
        setAgents(agentsData);
        setAlerts(alertsData);
      } else {
        throw new Error("empty");
      }
    } catch {
      setAgents(MOCK_AGENTS);
      setAlerts(MOCK_ALERTS);
    } finally {
      const series = generateAllMockSeries(timeRange);
      setAllSeries(series);
      if (silent) setRefreshing(false);
      else setLoading(false);
    }
  }, [timeRange]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  // Auto-refresh every 15s
  useEffect(() => {
    if (!autoRefresh) return;
    const id = setInterval(() => {
      void loadData(true);
    }, 15000);
    return () => clearInterval(id);
  }, [autoRefresh, loadData]);

  // Export
  const handleExport = useCallback(() => {
    const data = { agents, alerts, exportedAt: new Date().toISOString() };
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "faultray-apm-export.json";
    a.click();
    URL.revokeObjectURL(a.href);
  }, [agents, alerts]);

  // ── Computed stats ──
  const stats = useMemo(() => {
    const connected = agents.filter((a) => a.status !== "offline").length;
    const critical  = alerts.filter((a) => a.severity === "CRITICAL").length;
    const warning   = alerts.filter((a) => a.severity === "WARNING").length;
    const info      = alerts.filter((a) => a.severity === "INFO").length;
    const cpuVals   = agents.filter((a) => a.cpu_percent !== undefined).map((a) => a.cpu_percent!);
    const memVals   = agents.filter((a) => a.memory_percent !== undefined).map((a) => a.memory_percent!);
    const diskVals  = agents.filter((a) => a.disk_percent !== undefined).map((a) => a.disk_percent!);
    const avgCpu    = cpuVals.length  > 0 ? cpuVals.reduce((s, v)  => s + v, 0)  / cpuVals.length  : 0;
    const avgMem    = memVals.length  > 0 ? memVals.reduce((s, v)  => s + v, 0)  / memVals.length  : 0;
    const avgDisk   = diskVals.length > 0 ? diskVals.reduce((s, v) => s + v, 0)  / diskVals.length : 0;
    return { connected, total: agents.length, critical, warning, info, avgCpu, avgMem, avgDisk };
  }, [agents, alerts]);

  // ── Series for selected agent(s) ──
  const visibleAgentIds = useMemo(
    () => (selectedAgent ? [selectedAgent] : agents.map((a) => a.agent_id)),
    [selectedAgent, agents]
  );

  const cpuSeries = useMemo<ChartSeries[]>(() =>
    visibleAgentIds.map((id, i) => ({
      label: agents.find((a) => a.agent_id === id)?.hostname ?? id,
      color: AGENT_COLORS[i % AGENT_COLORS.length],
      points: allSeries[id]?.cpu ?? [],
    })),
    [visibleAgentIds, agents, allSeries]
  );

  const memSeries = useMemo<ChartSeries[]>(() =>
    visibleAgentIds.map((id, i) => ({
      label: agents.find((a) => a.agent_id === id)?.hostname ?? id,
      color: AGENT_COLORS[i % AGENT_COLORS.length],
      points: allSeries[id]?.mem ?? [],
    })),
    [visibleAgentIds, agents, allSeries]
  );

  const netSentSeries = useMemo<ChartSeries[]>(() =>
    visibleAgentIds.map((id, i) => ({
      label: `${agents.find((a) => a.agent_id === id)?.hostname ?? id} ↑`,
      color: AGENT_COLORS[i % AGENT_COLORS.length],
      points: allSeries[id]?.netSent ?? [],
    })),
    [visibleAgentIds, agents, allSeries]
  );

  const netRecvSeries = useMemo<ChartSeries[]>(() =>
    visibleAgentIds.map((id, i) => ({
      label: `${agents.find((a) => a.agent_id === id)?.hostname ?? id} ↓`,
      color: AGENT_COLORS[(i + 1) % AGENT_COLORS.length],
      points: allSeries[id]?.netRecv ?? [],
    })),
    [visibleAgentIds, agents, allSeries]
  );

  const loadSeries = useMemo<ChartSeries[]>(() => {
    const firstId = visibleAgentIds[0] ?? "";
    const s = allSeries[firstId];
    if (!s) return [];
    return [
      { label: "load 1m",  color: "#10b981", points: s.load1  },
      { label: "load 5m",  color: "#3b82f6", points: s.load5  },
      { label: "load 15m", color: "#8b5cf6", points: s.load15 },
    ];
  }, [visibleAgentIds, allSeries]);

  // ── Sparkline data for stat cards ──
  const cpuSparkAll = useMemo(() => {
    const merged: number[] = [];
    for (const id of visibleAgentIds) {
      const pts = allSeries[id]?.cpu.slice(-20) ?? [];
      pts.forEach((p, i) => { merged[i] = (merged[i] ?? 0) + p.value / visibleAgentIds.length; });
    }
    return merged;
  }, [visibleAgentIds, allSeries]);

  const memSparkAll = useMemo(() => {
    const merged: number[] = [];
    for (const id of visibleAgentIds) {
      const pts = allSeries[id]?.mem.slice(-20) ?? [];
      pts.forEach((p, i) => { merged[i] = (merged[i] ?? 0) + p.value / visibleAgentIds.length; });
    }
    return merged;
  }, [visibleAgentIds, allSeries]);

  const netSparkAll = useMemo(() => {
    const merged: number[] = [];
    for (const id of visibleAgentIds) {
      const pts = allSeries[id]?.netSent.slice(-20) ?? [];
      pts.forEach((p, i) => { merged[i] = (merged[i] ?? 0) + p.value / visibleAgentIds.length; });
    }
    return merged;
  }, [visibleAgentIds, allSeries]);

  // ── Process table ──
  const sortedProcesses = useMemo(() => {
    const filtered = MOCK_PROCESSES.filter(
      (p) =>
        p.name.toLowerCase().includes(processSearch.toLowerCase()) ||
        String(p.pid).includes(processSearch)
    );
    return [...filtered].sort((a, b) => {
      const av = a[processSortKey] as number | string;
      const bv = b[processSortKey] as number | string;
      const cmp = typeof av === "string" ? av.localeCompare(bv as string) : (av as number) - (bv as number);
      return processSortAsc ? cmp : -cmp;
    });
  }, [processSearch, processSortKey, processSortAsc]);

  const timeRangeLabel: Record<TimeRange, string> = {
    "5m":  t.last5m,
    "15m": t.last15m,
    "1h":  t.last1h,
    "6h":  t.last6h,
    "24h": t.last24h,
    "7d":  t.last7d,
    "30d": t.last30d,
  };

  /* ============================================================
   * Render
   * ============================================================ */

  if (loading) {
    return (
      <div className="max-w-[1400px] mx-auto px-6 py-10 flex items-center justify-center min-h-[60vh]">
        <div className="text-center">
          <RefreshCw size={32} className="animate-spin text-[#FFD700] mx-auto mb-4" />
          <p className="text-[#64748b]">Loading APM data...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-[1400px] mx-auto px-4 md:px-6 py-6 space-y-6">

      {/* ══ Top Bar ══════════════════════════════════════════════ */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <Radio size={22} className="text-[#FFD700] shrink-0" />
          <div>
            <h1 className="text-xl font-bold leading-none">{t.title}</h1>
            <p className="text-xs text-[#64748b] mt-0.5">{t.subtitle}</p>
          </div>
          {/* auto-refresh indicator */}
          {autoRefresh && (
            <div className="flex items-center gap-1.5 ml-2 px-2 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/20">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              <span className="text-xs text-emerald-400">
                {refreshing ? t.refreshing : t.autoRefresh}
              </span>
            </div>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Time range */}
          <div className="flex gap-0.5 bg-[#111827] border border-[#1e293b] rounded-lg p-0.5">
            {TIME_RANGES.map((r) => (
              <button
                key={r}
                onClick={() => setTimeRange(r)}
                className={`px-2 py-1 rounded text-xs font-medium transition-colors ${
                  timeRange === r
                    ? "bg-[#FFD700]/15 text-[#FFD700] border border-[#FFD700]/30"
                    : "text-[#64748b] hover:text-[#94a3b8]"
                }`}
              >
                {timeRangeLabel[r]}
              </button>
            ))}
          </div>

          {/* Agent selector */}
          <select
            value={selectedAgent ?? ""}
            onChange={(e) => setSelectedAgent(e.target.value || null)}
            className="bg-[#111827] border border-[#1e293b] rounded-lg px-3 py-1.5 text-xs text-[#e2e8f0] focus:outline-none focus:border-[#FFD700]/40"
          >
            <option value="">{t.allAgents}</option>
            {agents.map((a) => (
              <option key={a.agent_id} value={a.agent_id}>{a.hostname}</option>
            ))}
          </select>

          {/* Auto-refresh toggle */}
          <button
            onClick={() => setAutoRefresh(!autoRefresh)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
              autoRefresh
                ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400"
                : "bg-[#111827] border-[#1e293b] text-[#64748b] hover:text-[#94a3b8]"
            }`}
          >
            {t.autoRefresh}
          </button>

          <Button variant="secondary" size="sm" onClick={() => void loadData(true)} disabled={refreshing}>
            <RefreshCw size={13} className={refreshing ? "animate-spin" : ""} />
            {t.refresh}
          </Button>
          <Button variant="secondary" size="sm" onClick={handleExport}>
            <Download size={13} />
            {t.export}
          </Button>
        </div>
      </div>

      {/* ══ Section 1: Key Metric Stat Cards ═════════════════════ */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label={t.cpuUsage}
          value={stats.avgCpu.toFixed(1)}
          unit="%"
          sparkPoints={cpuSparkAll}
          color={metricColor(stats.avgCpu)}
          trend={trendArrow(cpuSeries[0]?.points ?? [])}
          trendPctVal={trendPct(cpuSeries[0]?.points ?? [])}
          icon={<Cpu size={15} />}
        />
        <StatCard
          label={t.memoryUsage}
          value={stats.avgMem.toFixed(1)}
          unit="%"
          sparkPoints={memSparkAll}
          color={metricColor(stats.avgMem, 75, 90)}
          trend={trendArrow(memSeries[0]?.points ?? [])}
          trendPctVal={trendPct(memSeries[0]?.points ?? [])}
          icon={<HardDrive size={15} />}
        />
        <StatCard
          label={t.diskUsage}
          value={stats.avgDisk.toFixed(1)}
          unit="%"
          sparkPoints={[]}
          color={metricColor(stats.avgDisk, 80, 90)}
          trend="stable"
          trendPctVal={0}
          icon={<Server size={15} />}
        />
        <StatCard
          label={t.networkIo}
          value={
            netSparkAll.length > 0
              ? ((netSparkAll[netSparkAll.length - 1] ?? 0) / 1000).toFixed(1)
              : "0.0"
          }
          unit=" KB/s"
          sparkPoints={netSparkAll}
          color="#3b82f6"
          trend={trendArrow(netSentSeries[0]?.points ?? [])}
          trendPctVal={trendPct(netSentSeries[0]?.points ?? [])}
          icon={<Network size={15} />}
        />
      </div>

      {/* ══ Section 2: Time Series Grid (2×2) ════════════════════ */}
      <div className="grid md:grid-cols-2 gap-4">
        <Card>
          <MetricsPanel title={t.cpuUsage} series={cpuSeries} unit="%" yMax={100} />
        </Card>
        <Card>
          <MetricsPanel title={t.memoryUsage} series={memSeries} unit="%" yMax={100} />
        </Card>
        <Card>
          <MetricsPanel
            title={t.networkIo}
            series={[...netSentSeries, ...netRecvSeries]}
            unit="bytes"
            yMax={5000}
          />
        </Card>
        <Card>
          <MetricsPanel title={t.loadAverage} series={loadSeries} unit="load" yMax={10} />
        </Card>
      </div>

      {/* ══ Section 3: Infrastructure Map ════════════════════════ */}
      <Card>
        <h3 className="text-sm font-bold mb-4 flex items-center gap-2">
          <Server size={15} className="text-[#FFD700]" />
          {t.infrastructureMap}
          <span className="text-xs text-[#64748b] font-normal">
            — {stats.connected}/{stats.total} {t.running.toLowerCase()}
          </span>
        </h3>
        <div className="grid md:grid-cols-2 gap-3">
          {agents.map((agent, i) => (
            <HostCard
              key={agent.agent_id}
              agent={agent}
              color={AGENT_COLORS[i % AGENT_COLORS.length]}
              selected={selectedAgent === agent.agent_id}
              onClick={() => setSelectedAgent(
                selectedAgent === agent.agent_id ? null : agent.agent_id
              )}
              seriesData={allSeries[agent.agent_id]}
            />
          ))}
        </div>
      </Card>

      {/* ══ Section 4: Process Table ══════════════════════════════ */}
      <Card>
        <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
          <h3 className="text-sm font-bold flex items-center gap-2">
            <Activity size={15} className="text-[#FFD700]" />
            {t.processExplorer}
          </h3>
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={processSearch}
              onChange={(e) => setProcessSearch(e.target.value)}
              placeholder={t.search}
              className="bg-[#0a0e1a] border border-[#1e293b] rounded-lg px-3 py-1.5 text-xs text-[#e2e8f0] placeholder:text-[#475569] focus:outline-none focus:border-[#FFD700]/30 w-40"
            />
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-[#1e293b]">
                {(
                  [
                    { key: "pid",     label: t.pid     },
                    { key: "name",    label: t.name    },
                    { key: "cpu",     label: "CPU%"    },
                    { key: "mem",     label: "MEM%"    },
                    { key: "threads", label: t.threads },
                    { key: null,      label: t.status  },
                  ] as Array<{ key: "pid" | "name" | "cpu" | "mem" | "threads" | null; label: string }>
                ).map(({ key, label }) => (
                  <th
                    key={label}
                    className={`py-2.5 px-2 text-left text-[#64748b] font-medium ${key ? "cursor-pointer hover:text-[#94a3b8] select-none" : ""}`}
                    onClick={() => {
                      if (!key) return;
                      if (processSortKey === key) setProcessSortAsc(!processSortAsc);
                      else { setProcessSortKey(key); setProcessSortAsc(false); }
                    }}
                  >
                    {label}
                    {processSortKey === key && (
                      <span className="ml-1 text-[#FFD700]">{processSortAsc ? "↑" : "↓"}</span>
                    )}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sortedProcesses.map((proc) => (
                <tr key={proc.pid} className="border-b border-[#1e293b]/40 hover:bg-white/[0.02] transition-colors">
                  <td className="py-2.5 px-2 font-mono text-[#64748b]">{proc.pid}</td>
                  <td className="py-2.5 px-2 font-medium text-[#e2e8f0]">{proc.name}</td>
                  <td className="py-2.5 px-2 font-mono" style={{ color: metricColor(proc.cpu, 50, 80) }}>
                    {proc.cpu.toFixed(1)}%
                  </td>
                  <td className="py-2.5 px-2 font-mono" style={{ color: metricColor(proc.mem, 20, 40) }}>
                    {proc.mem.toFixed(1)}%
                  </td>
                  <td className="py-2.5 px-2 font-mono text-[#94a3b8]">{proc.threads}</td>
                  <td className="py-2.5 px-2">
                    <span className={`text-xs ${proc.status === "running" ? "text-emerald-400" : "text-[#64748b]"}`}>
                      {proc.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {/* ══ Section 5: Alert Timeline ════════════════════════════ */}
      <Card>
        <h3 className="text-sm font-bold mb-4 flex items-center gap-2">
          <AlertTriangle size={15} className="text-amber-400" />
          {t.alertTimeline}
          {alerts.length > 0 && (
            <Badge variant="red">{alerts.length}</Badge>
          )}
        </h3>

        {alerts.length === 0 ? (
          <div className="flex flex-col items-center py-10 text-center gap-3">
            <CheckCircle size={36} className="text-emerald-400" />
            <p className="text-emerald-400 font-medium">{t.allClear}</p>
            <p className="text-xs text-[#64748b]">{t.noActiveAlerts}</p>
          </div>
        ) : (
          <div className="space-y-1">
            {alerts.map((alert) => {
              const acked = acknowledgedAlerts.has(alert.id);
              return (
                <div
                  key={alert.id}
                  className={`flex items-start gap-3 py-3 border-b border-[#1e293b]/50 last:border-0 transition-opacity ${acked ? "opacity-40" : ""}`}
                >
                  {/* Timeline dot */}
                  <div className="flex flex-col items-center mt-1 shrink-0">
                    <span
                      className="w-2.5 h-2.5 rounded-full"
                      style={{ backgroundColor: severityDotColor(alert.severity) }}
                    />
                    <span className="w-px flex-1 bg-[#1e293b] mt-1" style={{ minHeight: 12 }} />
                  </div>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <Badge variant={severityBadgeVariant(alert.severity)}>
                        {t[alert.severity.toLowerCase() as "critical" | "warning" | "info"] ?? alert.severity}
                      </Badge>
                      <span className="text-sm font-medium text-[#e2e8f0]">{alert.rule_name}</span>
                      <span className="text-xs text-[#64748b] font-mono">{alert.agent_id}</span>
                    </div>
                    <div className="flex items-center gap-3 mt-1 flex-wrap">
                      <span className="text-xs text-[#64748b]">
                        {alert.metric_name}:{" "}
                        <span style={{ color: severityDotColor(alert.severity) }}>
                          {alert.metric_value.toFixed(1)}
                        </span>
                        {" "}/ threshold {alert.threshold.toFixed(1)}
                      </span>
                      <span className="text-xs text-[#475569]">{formatRelative(alert.fired_at)}</span>
                    </div>
                  </div>

                  <button
                    onClick={() =>
                      setAcknowledgedAlerts((prev) => {
                        const next = new Set(prev);
                        if (next.has(alert.id)) next.delete(alert.id);
                        else next.add(alert.id);
                        return next;
                      })
                    }
                    className={`text-xs px-2.5 py-1 rounded border transition-colors shrink-0 ${
                      acked
                        ? "border-emerald-500/30 text-emerald-400 bg-emerald-500/10"
                        : "border-[#1e293b] text-[#64748b] hover:border-[#334155] hover:text-[#94a3b8]"
                    }`}
                  >
                    {acked ? "✓ Acked" : t.acknowledge}
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </Card>

      {/* ══ Section 6: Quick Setup (collapsible) ═════════════════ */}
      <Card className="border-[#FFD700]/10">
        <button
          onClick={() => setShowSetup(!showSetup)}
          className="w-full flex items-center justify-between"
        >
          <h3 className="text-sm font-bold flex items-center gap-2">
            <Server size={14} className="text-[#FFD700]" />
            {t.quickSetup}
          </h3>
          {showSetup ? (
            <ChevronUp size={16} className="text-[#64748b]" />
          ) : (
            <ChevronDown size={16} className="text-[#64748b]" />
          )}
        </button>

        {showSetup && (
          <div className="mt-4 pt-4 border-t border-[#1e293b]">
            <p className="text-xs text-[#94a3b8] mb-4">{t.setupDescription}</p>
            <ol className="space-y-3">
              {[t.setupStep1, t.setupStep2, t.setupStep3, t.setupStep4].map((step, i) => (
                <li key={i} className="flex gap-3">
                  <span className="shrink-0 w-6 h-6 rounded-full bg-[#FFD700]/10 border border-[#FFD700]/30 text-[#FFD700] text-xs flex items-center justify-center font-bold">
                    {i + 1}
                  </span>
                  <span className="text-xs text-[#94a3b8] pt-1">{step}</span>
                </li>
              ))}
            </ol>
          </div>
        )}
      </Card>
    </div>
  );
}
