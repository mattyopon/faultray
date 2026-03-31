"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useState, useEffect, useCallback, useMemo } from "react";
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
} from "lucide-react";
import { useLocale } from "@/lib/useLocale";
import { appDict } from "@/i18n/app-dict";
import { api, type ApmAgent, type ApmMetricPoint, type ApmAlert } from "@/lib/api";

/* ============================================================
 * Mock data
 * ============================================================ */

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

function generateMetricPoints(metric: string, baseValue: number, variance: number, count = 24): ApmMetricPoint[] {
  const now = Math.floor(Date.now() / 1000);
  return Array.from({ length: count }, (_, i) => ({
    metric_name: metric,
    value: Math.max(0, Math.min(100, baseValue + (Math.random() - 0.5) * variance)),
    sample_count: Math.floor(Math.random() * 10) + 1,
    bucket_epoch: now - (count - i) * 300,
  }));
}

const MOCK_CPU_METRICS = generateMetricPoints("cpu_percent", 52, 30);
const MOCK_MEM_METRICS = generateMetricPoints("memory_usage_percent", 68, 20);
const MOCK_NET_METRICS = generateMetricPoints("net_bytes_sent", 45, 40);

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
 * SVG Chart components
 * ============================================================ */

function MetricLineChart({
  points,
  color,
  label,
  unit = "%",
}: {
  points: ApmMetricPoint[];
  color: string;
  label: string;
  unit?: string;
}) {
  const w = 600;
  const h = 160;
  const pad = { top: 16, right: 16, bottom: 32, left: 48 };
  const chartW = w - pad.left - pad.right;
  const chartH = h - pad.top - pad.bottom;

  if (points.length === 0) return null;

  const values = points.map((p) => p.value);
  const maxVal = Math.max(...values, 1);
  const minVal = Math.min(...values, 0);
  const range = maxVal - minVal || 1;

  const toX = (i: number) => pad.left + (i / (points.length - 1)) * chartW;
  const toY = (v: number) => pad.top + chartH - ((v - minVal) / range) * chartH;

  const pathD = points
    .map((p, i) => `${i === 0 ? "M" : "L"}${toX(i).toFixed(1)},${toY(p.value).toFixed(1)}`)
    .join(" ");

  const areaD =
    pathD +
    ` L${toX(points.length - 1).toFixed(1)},${(pad.top + chartH).toFixed(1)} L${toX(0).toFixed(1)},${(pad.top + chartH).toFixed(1)} Z`;

  const gridLines = [0, 25, 50, 75, 100];

  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full" aria-label={label}>
      {gridLines.map((val) => {
        const y = toY(val);
        if (y < pad.top || y > pad.top + chartH) return null;
        return (
          <g key={val}>
            <line
              x1={pad.left}
              x2={w - pad.right}
              y1={y}
              y2={y}
              stroke="#1e293b"
              strokeWidth={1}
            />
            <text
              x={pad.left - 6}
              y={y + 4}
              textAnchor="end"
              fill="#475569"
              fontSize={9}
              fontFamily="monospace"
            >
              {val}{unit}
            </text>
          </g>
        );
      })}

      {/* Area fill */}
      <path d={areaD} fill={color} opacity={0.08} />

      {/* Line */}
      <path d={pathD} fill="none" stroke={color} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />

      {/* X-axis time labels */}
      {[0, Math.floor(points.length / 3), Math.floor((points.length * 2) / 3), points.length - 1].map((idx) => {
        if (idx >= points.length) return null;
        const pt = points[idx];
        const d = new Date(pt.bucket_epoch * 1000);
        const label = `${d.getHours().toString().padStart(2, "0")}:${d.getMinutes().toString().padStart(2, "0")}`;
        return (
          <text
            key={idx}
            x={toX(idx)}
            y={h - 6}
            textAnchor="middle"
            fill="#475569"
            fontSize={9}
          >
            {label}
          </text>
        );
      })}

      {/* Current value dot */}
      {points.length > 0 && (
        <circle
          cx={toX(points.length - 1)}
          cy={toY(points[points.length - 1].value)}
          r={3}
          fill={color}
          stroke="#0a0e1a"
          strokeWidth={1.5}
        />
      )}
    </svg>
  );
}

/* ============================================================
 * Helpers
 * ============================================================ */

function cpuColor(v: number | undefined): string {
  if (v === undefined) return "#64748b";
  if (v >= 90) return "#ef4444";
  if (v >= 70) return "#f59e0b";
  return "#10b981";
}

function memColor(v: number | undefined): string {
  if (v === undefined) return "#64748b";
  if (v >= 90) return "#ef4444";
  if (v >= 75) return "#f59e0b";
  return "#10b981";
}

function statusColor(status: string): string {
  switch (status) {
    case "running": return "green";
    case "degraded": return "yellow";
    case "offline": return "red";
    default: return "default";
  }
}

function severityColor(severity: string): string {
  switch (severity) {
    case "CRITICAL": return "red";
    case "WARNING": return "yellow";
    case "INFO": return "default";
    default: return "default";
  }
}

function formatRelative(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const s = Math.floor(diff / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  return `${h}h ago`;
}

type TimeRange = "1h" | "6h" | "24h" | "7d";

/* ============================================================
 * Main Page
 * ============================================================ */

export default function ApmPage() {
  const locale = useLocale();
  const t = appDict.apm[locale] ?? appDict.apm.en;

  const [agents, setAgents] = useState<ApmAgent[]>([]);
  const [cpuMetrics, setCpuMetrics] = useState<ApmMetricPoint[]>([]);
  const [memMetrics, setMemMetrics] = useState<ApmMetricPoint[]>([]);
  const [netMetrics, setNetMetrics] = useState<ApmMetricPoint[]>([]);
  const [alerts, setAlerts] = useState<ApmAlert[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [timeRange, setTimeRange] = useState<TimeRange>("1h");
  const [showSetup, setShowSetup] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      // Try to get auth token from localStorage
      let token: string | undefined;
      try {
        const session = localStorage.getItem("faultray_session");
        if (session) {
          const parsed = JSON.parse(session) as { access_token?: string };
          token = parsed.access_token;
        }
      } catch {
        // ignore
      }

      const [agentsData, alertsData] = await Promise.all([
        api.getApmAgents(token),
        api.getApmAlerts(undefined, token),
      ]);
      setAgents(agentsData);
      setAlerts(alertsData);

      // Load metrics for first agent or selected
      const targetAgent = selectedAgent ?? agentsData[0]?.agent_id;
      if (targetAgent) {
        const [cpu, mem, net] = await Promise.all([
          api.getApmMetrics(targetAgent, "cpu_percent", token),
          api.getApmMetrics(targetAgent, "memory_usage_percent", token),
          api.getApmMetrics(targetAgent, "net_bytes_sent", token),
        ]);
        setCpuMetrics(cpu);
        setMemMetrics(mem);
        setNetMetrics(net);
      }
    } catch {
      // Fallback to mock data
      setAgents(MOCK_AGENTS);
      setAlerts(MOCK_ALERTS);
      setCpuMetrics(MOCK_CPU_METRICS);
      setMemMetrics(MOCK_MEM_METRICS);
      setNetMetrics(MOCK_NET_METRICS);
    } finally {
      setLoading(false);
    }
  }, [selectedAgent]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  // ── Computed stats ──
  const stats = useMemo(() => {
    const connected = agents.filter((a) => a.status !== "offline").length;
    const critical = alerts.filter((a) => a.severity === "CRITICAL").length;
    const warning = alerts.filter((a) => a.severity === "WARNING").length;
    const info = alerts.filter((a) => a.severity === "INFO").length;
    const cpuValues = agents.filter((a) => a.cpu_percent !== undefined).map((a) => a.cpu_percent!);
    const memValues = agents.filter((a) => a.memory_percent !== undefined).map((a) => a.memory_percent!);
    const avgCpu = cpuValues.length > 0 ? cpuValues.reduce((s, v) => s + v, 0) / cpuValues.length : 0;
    const avgMem = memValues.length > 0 ? memValues.reduce((s, v) => s + v, 0) / memValues.length : 0;
    return { connected, total: agents.length, critical, warning, info, avgCpu, avgMem };
  }, [agents, alerts]);

  // ── Export ──
  const handleExport = useCallback(() => {
    const data = { agents, alerts, exportedAt: new Date().toISOString() };
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "faultray-apm-export.json";
    a.click();
    URL.revokeObjectURL(a.href);
  }, [agents, alerts]);

  /* ============================================================
   * Render
   * ============================================================ */

  return (
    <div className="max-w-[1200px] mx-auto px-6 py-10">
      {/* Header */}
      <div className="mb-8 flex items-start justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-bold mb-1 flex items-center gap-3">
            <Radio size={24} className="text-[#FFD700]" />
            {t.title}
          </h1>
          <p className="text-[#94a3b8] text-sm">{t.subtitle}</p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <Button variant="secondary" size="sm" onClick={() => void loadData()} disabled={loading}>
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
            {t.refresh}
          </Button>
          <Button variant="secondary" size="sm" onClick={handleExport}>
            <Download size={14} />
            {t.export}
          </Button>
          <Button size="sm" onClick={() => setShowSetup(!showSetup)}>
            <Server size={14} />
            {t.setupAgent}
          </Button>
        </div>
      </div>

      {/* ── Setup Panel ── */}
      {showSetup && (
        <Card className="mb-8 border-[#FFD700]/20">
          <h3 className="text-base font-bold mb-3 flex items-center gap-2">
            <Server size={16} className="text-[#FFD700]" />
            {t.setupTitle}
          </h3>
          <p className="text-sm text-[#94a3b8] mb-4">{t.setupDescription}</p>
          <ol className="space-y-2 text-sm">
            {[t.setupStep1, t.setupStep2, t.setupStep3, t.setupStep4].map((step, i) => (
              <li key={i} className="flex gap-3">
                <span className="shrink-0 w-6 h-6 rounded-full bg-[#FFD700]/10 border border-[#FFD700]/30 text-[#FFD700] text-xs flex items-center justify-center font-bold">
                  {i + 1}
                </span>
                <span className="text-[#94a3b8] pt-0.5">{step}</span>
              </li>
            ))}
          </ol>
        </Card>
      )}

      {/* ── Section 1: Overview Cards ── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        {/* Connected Agents */}
        <Card>
          <div className="flex items-start justify-between mb-2">
            <p className="text-xs text-[#64748b] uppercase tracking-wider">{t.connectedAgents}</p>
            <Wifi size={16} className={stats.connected > 0 ? "text-emerald-400" : "text-red-400"} />
          </div>
          <p className="text-3xl font-extrabold font-mono">
            <span className={stats.connected > 0 ? "text-emerald-400" : "text-red-400"}>{stats.connected}</span>
            <span className="text-[#475569] text-lg font-normal">/{stats.total}</span>
          </p>
          <p className="text-xs text-[#64748b] mt-1">
            {stats.total - stats.connected} {t.offline}
          </p>
        </Card>

        {/* Active Alerts */}
        <Card>
          <div className="flex items-start justify-between mb-2">
            <p className="text-xs text-[#64748b] uppercase tracking-wider">{t.activeAlerts}</p>
            <AlertTriangle size={16} className={stats.critical > 0 ? "text-red-400" : "text-[#64748b]"} />
          </div>
          <p className="text-3xl font-extrabold font-mono text-[#e2e8f0]">
            {alerts.length}
          </p>
          <div className="flex gap-2 mt-1 flex-wrap">
            {stats.critical > 0 && (
              <span className="text-xs text-red-400">{stats.critical} {t.critical}</span>
            )}
            {stats.warning > 0 && (
              <span className="text-xs text-amber-400">{stats.warning} {t.warning}</span>
            )}
            {stats.info > 0 && (
              <span className="text-xs text-blue-400">{stats.info} {t.info}</span>
            )}
          </div>
        </Card>

        {/* Avg CPU */}
        <Card>
          <div className="flex items-start justify-between mb-2">
            <p className="text-xs text-[#64748b] uppercase tracking-wider">{t.avgCpu}</p>
            <Cpu size={16} style={{ color: cpuColor(stats.avgCpu) }} />
          </div>
          <p className="text-3xl font-extrabold font-mono" style={{ color: cpuColor(stats.avgCpu) }}>
            {stats.avgCpu.toFixed(1)}%
          </p>
          <div className="mt-2 h-1.5 rounded-full bg-[#1e293b] overflow-hidden">
            <div
              className="h-full rounded-full transition-all"
              style={{ width: `${stats.avgCpu}%`, backgroundColor: cpuColor(stats.avgCpu) }}
            />
          </div>
        </Card>

        {/* Avg Memory */}
        <Card>
          <div className="flex items-start justify-between mb-2">
            <p className="text-xs text-[#64748b] uppercase tracking-wider">{t.avgMemory}</p>
            <HardDrive size={16} style={{ color: memColor(stats.avgMem) }} />
          </div>
          <p className="text-3xl font-extrabold font-mono" style={{ color: memColor(stats.avgMem) }}>
            {stats.avgMem.toFixed(1)}%
          </p>
          <div className="mt-2 h-1.5 rounded-full bg-[#1e293b] overflow-hidden">
            <div
              className="h-full rounded-full transition-all"
              style={{ width: `${stats.avgMem}%`, backgroundColor: memColor(stats.avgMem) }}
            />
          </div>
        </Card>
      </div>

      {/* ── Section 2: Agents Table ── */}
      <Card className="mb-8">
        <h3 className="text-base font-bold mb-4 flex items-center gap-2">
          <Activity size={16} className="text-[#FFD700]" />
          {t.connectedAgents}
        </h3>
        {agents.length === 0 ? (
          <p className="text-[#64748b] text-sm py-6 text-center">{t.noAgents}</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[#1e293b]">
                  <th className="text-left py-2.5 px-2 text-[#64748b] font-medium">{t.agentId}</th>
                  <th className="text-left py-2.5 px-2 text-[#64748b] font-medium">{t.hostname}</th>
                  <th className="text-left py-2.5 px-2 text-[#64748b] font-medium hidden md:table-cell">{t.ip}</th>
                  <th className="text-left py-2.5 px-2 text-[#64748b] font-medium">{t.status}</th>
                  <th className="text-right py-2.5 px-2 text-[#64748b] font-medium hidden sm:table-cell">{t.cpu}</th>
                  <th className="text-right py-2.5 px-2 text-[#64748b] font-medium hidden sm:table-cell">{t.memory}</th>
                  <th className="text-right py-2.5 px-2 text-[#64748b] font-medium hidden lg:table-cell">{t.disk}</th>
                  <th className="text-right py-2.5 px-2 text-[#64748b] font-medium hidden md:table-cell">{t.lastSeen}</th>
                </tr>
              </thead>
              <tbody>
                {agents.map((agent) => {
                  const isSelected = selectedAgent === agent.agent_id;
                  return (
                    <tr
                      key={agent.agent_id}
                      onClick={() => setSelectedAgent(isSelected ? null : agent.agent_id)}
                      className={`border-b border-[#1e293b]/50 cursor-pointer transition-colors ${
                        isSelected
                          ? "bg-[#FFD700]/5 border-[#FFD700]/20"
                          : "hover:bg-white/[0.02]"
                      }`}
                    >
                      <td className="py-3 px-2 font-mono text-xs text-[#64748b]">{agent.agent_id}</td>
                      <td className="py-3 px-2 font-medium text-[#e2e8f0]">{agent.hostname}</td>
                      <td className="py-3 px-2 font-mono text-xs text-[#94a3b8] hidden md:table-cell">{agent.ip_address}</td>
                      <td className="py-3 px-2">
                        <Badge variant={statusColor(agent.status) as "green" | "yellow" | "red" | "default"}>
                          {t[agent.status as "running" | "offline" | "degraded"] ?? agent.status}
                        </Badge>
                      </td>
                      <td className="py-3 px-2 text-right font-mono hidden sm:table-cell">
                        {agent.cpu_percent !== undefined ? (
                          <span style={{ color: cpuColor(agent.cpu_percent) }}>
                            {agent.cpu_percent.toFixed(1)}%
                          </span>
                        ) : (
                          <span className="text-[#475569]">—</span>
                        )}
                      </td>
                      <td className="py-3 px-2 text-right font-mono hidden sm:table-cell">
                        {agent.memory_percent !== undefined ? (
                          <span style={{ color: memColor(agent.memory_percent) }}>
                            {agent.memory_percent.toFixed(1)}%
                          </span>
                        ) : (
                          <span className="text-[#475569]">—</span>
                        )}
                      </td>
                      <td className="py-3 px-2 text-right font-mono hidden lg:table-cell">
                        {agent.disk_percent !== undefined ? (
                          <span className={agent.disk_percent >= 85 ? "text-red-400" : "text-[#94a3b8]"}>
                            {agent.disk_percent.toFixed(1)}%
                          </span>
                        ) : (
                          <span className="text-[#475569]">—</span>
                        )}
                      </td>
                      <td className="py-3 px-2 text-right text-xs text-[#64748b] hidden md:table-cell">
                        {formatRelative(agent.last_seen)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* ── Section 3: Metrics Charts ── */}
      <Card className="mb-8">
        <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
          <h3 className="text-base font-bold flex items-center gap-2">
            <Activity size={16} className="text-[#FFD700]" />
            {t.metricsTitle}
            {selectedAgent && (
              <span className="text-xs text-[#FFD700] font-normal font-mono">
                — {agents.find((a) => a.agent_id === selectedAgent)?.hostname ?? selectedAgent}
              </span>
            )}
          </h3>
          <div className="flex gap-1">
            {(["1h", "6h", "24h", "7d"] as TimeRange[]).map((r) => (
              <button
                key={r}
                onClick={() => setTimeRange(r)}
                className={`px-2.5 py-1 rounded text-xs transition-colors ${
                  timeRange === r
                    ? "bg-[#FFD700]/10 text-[#FFD700] border border-[#FFD700]/30"
                    : "text-[#64748b] border border-[#1e293b] hover:border-[#64748b]"
                }`}
              >
                {t[`last${r.charAt(0).toUpperCase() + r.slice(1)}` as keyof typeof t] ?? r}
              </button>
            ))}
          </div>
        </div>
        <div className="grid md:grid-cols-1 gap-6">
          {/* CPU */}
          <div>
            <p className="text-xs text-[#64748b] uppercase tracking-wider mb-2 flex items-center gap-1.5">
              <Cpu size={12} />
              {t.cpuUsage}
            </p>
            <MetricLineChart points={cpuMetrics} color="#10b981" label={t.cpuUsage} />
          </div>
          {/* Memory */}
          <div>
            <p className="text-xs text-[#64748b] uppercase tracking-wider mb-2 flex items-center gap-1.5">
              <HardDrive size={12} />
              {t.memoryUsage}
            </p>
            <MetricLineChart points={memMetrics} color="#3b82f6" label={t.memoryUsage} />
          </div>
          {/* Network I/O */}
          <div>
            <p className="text-xs text-[#64748b] uppercase tracking-wider mb-2 flex items-center gap-1.5">
              <Wifi size={12} />
              {t.networkIo}
            </p>
            <MetricLineChart points={netMetrics} color="#a855f7" label={t.networkIo} unit=" MB/s" />
          </div>
        </div>
      </Card>

      {/* ── Section 4: Active Alerts ── */}
      <Card className="mb-8">
        <h3 className="text-base font-bold mb-4 flex items-center gap-2">
          <AlertTriangle size={16} className="text-amber-400" />
          {t.alertsTitle}
        </h3>
        {alerts.length === 0 ? (
          <p className="text-[#64748b] text-sm py-6 text-center">{t.noAlerts}</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[#1e293b]">
                  <th className="text-left py-2.5 px-2 text-[#64748b] font-medium">{t.severity}</th>
                  <th className="text-left py-2.5 px-2 text-[#64748b] font-medium">{t.rule}</th>
                  <th className="text-left py-2.5 px-2 text-[#64748b] font-medium hidden md:table-cell">{t.agent}</th>
                  <th className="text-left py-2.5 px-2 text-[#64748b] font-medium hidden sm:table-cell">{t.metric}</th>
                  <th className="text-right py-2.5 px-2 text-[#64748b] font-medium hidden sm:table-cell">{t.value}</th>
                  <th className="text-right py-2.5 px-2 text-[#64748b] font-medium hidden sm:table-cell">{t.threshold}</th>
                  <th className="text-right py-2.5 px-2 text-[#64748b] font-medium">{t.firedAt}</th>
                </tr>
              </thead>
              <tbody>
                {alerts.map((alert) => (
                  <tr key={alert.id} className="border-b border-[#1e293b]/50 hover:bg-white/[0.02] transition-colors">
                    <td className="py-3 px-2">
                      <Badge variant={severityColor(alert.severity) as "red" | "yellow" | "default"}>
                        {t[alert.severity.toLowerCase() as "critical" | "warning" | "info"] ?? alert.severity}
                      </Badge>
                    </td>
                    <td className="py-3 px-2 font-medium text-[#e2e8f0]">{alert.rule_name}</td>
                    <td className="py-3 px-2 text-[#94a3b8] font-mono text-xs hidden md:table-cell">{alert.agent_id}</td>
                    <td className="py-3 px-2 text-[#94a3b8] font-mono text-xs hidden sm:table-cell">{alert.metric_name}</td>
                    <td className="py-3 px-2 text-right font-mono hidden sm:table-cell">
                      <span className={alert.severity === "CRITICAL" ? "text-red-400" : "text-amber-400"}>
                        {alert.metric_value.toFixed(1)}
                      </span>
                    </td>
                    <td className="py-3 px-2 text-right font-mono text-[#64748b] hidden sm:table-cell">
                      {alert.threshold.toFixed(1)}
                    </td>
                    <td className="py-3 px-2 text-right text-xs text-[#64748b]">
                      {formatRelative(alert.fired_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
