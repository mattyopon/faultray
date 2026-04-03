"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useEffect, useState, useCallback, useRef, useMemo } from "react";
import { api } from "@/lib/api";
import {
  Network,
  ArrowRight,
  Loader2,
  RefreshCw,
  AlertTriangle,
  Lightbulb,
  X,
  Info,
  Shield,
  Activity,
  Zap,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useLocale } from "@/lib/useLocale";
import type { Locale } from "@/i18n/config";
import { appDict } from "@/i18n/app-dict";
import { CloudIcon, getServiceColor } from "@/components/cloud-icons";

// ─── Data Types ────────────────────────────────────────────────

interface GraphNode {
  id: string;
  name: string;
  type: string;
  risk: number;
  replicas?: number;
  provider?: string;
  region?: string;
}

interface GraphEdge {
  source: string;
  target: string;
  type?: string;
}

interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

interface NodeRiskData {
  risk_score: number;
  failure_scenarios: string[];
  suggestions: string[];
  metrics?: { latency_p99?: string; throughput?: string; error_rate?: string };
}

// ─── Demo Data (extended architecture) ─────────────────────────

const DEMO_DATA: GraphData = {
  nodes: [
    { id: "cdn", name: "CloudFront CDN", type: "cloudfront", risk: 12, replicas: 3, provider: "aws", region: "global" },
    { id: "gateway", name: "API Gateway", type: "alb", risk: 25, replicas: 2, provider: "aws", region: "ap-northeast-1" },
    { id: "auth", name: "Auth Service", type: "ec2", risk: 45, replicas: 2, provider: "aws", region: "ap-northeast-1" },
    { id: "api", name: "API Server", type: "ec2", risk: 38, replicas: 3, provider: "aws", region: "ap-northeast-1" },
    { id: "users_db", name: "Users DB", type: "rds", risk: 55, replicas: 1, provider: "aws", region: "ap-northeast-1" },
    { id: "db_primary", name: "Main DB", type: "rds", risk: 78, replicas: 1, provider: "aws", region: "ap-northeast-1" },
    { id: "cache", name: "Redis Cache", type: "elasticache", risk: 35, replicas: 3, provider: "aws", region: "ap-northeast-1" },
    { id: "worker", name: "Worker", type: "lambda", risk: 20, replicas: undefined, provider: "aws", region: "ap-northeast-1" },
    { id: "queue", name: "Job Queue", type: "sqs", risk: 15, replicas: undefined, provider: "aws", region: "ap-northeast-1" },
    { id: "db_replica", name: "DB Replica", type: "rds", risk: 30, replicas: 2, provider: "aws", region: "ap-northeast-1" },
  ],
  edges: [
    { source: "cdn", target: "gateway", type: "requires" },
    { source: "gateway", target: "auth", type: "requires" },
    { source: "gateway", target: "api", type: "requires" },
    { source: "auth", target: "users_db", type: "requires" },
    { source: "api", target: "db_primary", type: "requires" },
    { source: "api", target: "cache", type: "optional" },
    { source: "api", target: "queue", type: "async" },
    { source: "queue", target: "worker", type: "async" },
    { source: "worker", target: "db_primary", type: "requires" },
    { source: "db_primary", target: "db_replica", type: "async" },
  ],
};

const DEMO_RISK: Record<string, NodeRiskData> = {
  cdn: {
    risk_score: 12,
    failure_scenarios: ["DDoS attack overwhelms edge capacity", "Cache invalidation storm"],
    suggestions: ["Add rate limiting at edge layer", "Configure stale-while-revalidate"],
    metrics: { latency_p99: "45ms", throughput: "12k rps", error_rate: "0.01%" },
  },
  gateway: {
    risk_score: 25,
    failure_scenarios: ["Certificate expiry blocks all HTTPS", "Rate limit misconfiguration"],
    suggestions: ["Automate certificate renewal", "Configure adaptive rate limits"],
    metrics: { latency_p99: "12ms", throughput: "8k rps", error_rate: "0.05%" },
  },
  auth: {
    risk_score: 45,
    failure_scenarios: ["Token validation service outage", "Brute force attack"],
    suggestions: ["Implement token caching", "Add account lockout policy"],
    metrics: { latency_p99: "85ms", throughput: "2k rps", error_rate: "0.2%" },
  },
  api: {
    risk_score: 38,
    failure_scenarios: ["Thread pool exhaustion under load", "Memory leak in long-running processes"],
    suggestions: ["Configure connection limits and auto-scaling", "Add memory monitoring alerts"],
    metrics: { latency_p99: "120ms", throughput: "5k rps", error_rate: "0.1%" },
  },
  users_db: {
    risk_score: 62,
    failure_scenarios: ["Single writer bottleneck during auth spikes", "Connection pool exhaustion"],
    suggestions: ["Add read replica for auth queries", "Implement connection pooling with PgBouncer"],
    metrics: { latency_p99: "25ms", throughput: "3k qps", error_rate: "0.02%" },
  },
  db_primary: {
    risk_score: 78,
    failure_scenarios: ["Single point of failure - complete crash causes full outage", "Disk I/O saturation", "Connection pool exhaustion"],
    suggestions: ["Implement automated failover with < 30s switchover", "Add read replicas for load distribution", "Monitor disk I/O and set alerts at 80%"],
    metrics: { latency_p99: "35ms", throughput: "4k qps", error_rate: "0.03%" },
  },
  cache: {
    risk_score: 55,
    failure_scenarios: ["Memory exhaustion causes eviction storm", "Network partition causes split-brain"],
    suggestions: ["Set memory limits and eviction policies", "Deploy across multiple AZs"],
    metrics: { latency_p99: "2ms", throughput: "50k rps", error_rate: "0.01%" },
  },
  worker: {
    risk_score: 30,
    failure_scenarios: ["Cold start latency spikes", "Concurrent execution limit reached"],
    suggestions: ["Configure provisioned concurrency", "Implement dead letter queue"],
    metrics: { latency_p99: "800ms", throughput: "500 rps", error_rate: "0.5%" },
  },
  queue: {
    risk_score: 15,
    failure_scenarios: ["Message visibility timeout causes duplicate processing"],
    suggestions: ["Implement idempotent consumers", "Configure DLQ for poison messages"],
    metrics: { latency_p99: "5ms", throughput: "10k mps", error_rate: "0.001%" },
  },
  db_replica: {
    risk_score: 35,
    failure_scenarios: ["Replication lag exceeds threshold"],
    suggestions: ["Monitor replication lag, alert at > 5s"],
    metrics: { latency_p99: "20ms", throughput: "6k qps", error_rate: "0.01%" },
  },
};

// ─── Utility Functions ─────────────────────────────────────────

function riskColor(score: number): string {
  if (score >= 70) return "#ef4444";
  if (score >= 50) return "#f59e0b";
  if (score >= 30) return "#eab308";
  return "#10b981";
}

function riskBorderColor(score: number): string {
  if (score >= 70) return "#ef444480";
  if (score >= 50) return "#f59e0b80";
  if (score >= 30) return "#eab30860";
  return "#10b98160";
}

function riskBgColor(score: number): string {
  if (score >= 70) return "#ef444420";
  if (score >= 50) return "#f59e0b15";
  if (score >= 30) return "#eab30810";
  return "#10b98110";
}

function riskLabel(score: number, locale: Locale): string {
  const t = appDict.topology[locale] ?? appDict.topology.en;
  if (score >= 70) return t.highRisk;
  if (score >= 50) return t.mediumRisk;
  if (score >= 30) return t.lowRisk;
  return t.lowRisk;
}

// ─── Hierarchical Layout Engine ────────────────────────────────

function layoutNodes(nodes: GraphNode[], edges: GraphEdge[], canvasWidth: number) {
  const adj: Record<string, string[]> = {};
  const inDeg: Record<string, number> = {};

  for (const n of nodes) {
    adj[n.id] = [];
    inDeg[n.id] = 0;
  }
  for (const e of edges) {
    if (adj[e.source]) adj[e.source].push(e.target);
    if (inDeg[e.target] !== undefined) inDeg[e.target]++;
  }

  // Topological sort with BFS for layer assignment
  const layers: string[][] = [];
  const depth: Record<string, number> = {};
  const queue: string[] = [];

  for (const n of nodes) {
    if (inDeg[n.id] === 0) {
      queue.push(n.id);
      depth[n.id] = 0;
    }
  }

  while (queue.length > 0) {
    const id = queue.shift()!;
    const d = depth[id];
    if (!layers[d]) layers[d] = [];
    layers[d].push(id);

    for (const next of (adj[id] || [])) {
      const newDepth = d + 1;
      if (depth[next] === undefined || depth[next] < newDepth) {
        depth[next] = newDepth;
      }
      inDeg[next]--;
      if (inDeg[next] === 0) {
        queue.push(next);
      }
    }
  }

  // Handle unplaced nodes (cycles, disconnected)
  const placed = new Set(layers.flat());
  for (const n of nodes) {
    if (!placed.has(n.id)) {
      if (!layers[0]) layers[0] = [];
      layers[0].push(n.id);
    }
  }

  const NODE_W = 220;
  const NODE_H = 120;
  const LAYER_GAP = 160;
  const NODE_GAP = 40;
  const PAD_TOP = 60;
  const PAD_LEFT = 40;

  // Compute total width needed
  const maxLayerWidth = Math.max(...layers.map(l => l.length * (NODE_W + NODE_GAP) - NODE_GAP));
  const effectiveWidth = Math.max(canvasWidth - PAD_LEFT * 2, maxLayerWidth);

  const positions: Record<string, { x: number; y: number }> = {};

  for (let i = 0; i < layers.length; i++) {
    const layer = layers[i];
    const totalW = layer.length * NODE_W + (layer.length - 1) * NODE_GAP;
    const startX = PAD_LEFT + (effectiveWidth - totalW) / 2;

    for (let j = 0; j < layer.length; j++) {
      positions[layer[j]] = {
        x: startX + j * (NODE_W + NODE_GAP),
        y: PAD_TOP + i * (NODE_H + LAYER_GAP),
      };
    }
  }

  const totalHeight = PAD_TOP + layers.length * (NODE_H + LAYER_GAP) + 40;
  const totalWidth = effectiveWidth + PAD_LEFT * 2;

  return { positions, totalHeight, totalWidth, nodeW: NODE_W, nodeH: NODE_H };
}

// ─── Edge Path Computation ─────────────────────────────────────

function computeEdgePath(
  fromPos: { x: number; y: number },
  toPos: { x: number; y: number },
  nodeW: number,
  nodeH: number,
): string {
  const fromCx = fromPos.x + nodeW / 2;
  const fromCy = fromPos.y + nodeH;
  const toCx = toPos.x + nodeW / 2;
  const toCy = toPos.y;

  const dy = toCy - fromCy;
  const ctrlOffset = Math.max(40, Math.abs(dy) * 0.4);

  return `M ${fromCx} ${fromCy} C ${fromCx} ${fromCy + ctrlOffset}, ${toCx} ${toCy - ctrlOffset}, ${toCx} ${toCy}`;
}

// ─── Main Page Component ───────────────────────────────────────

export default function TopologyPage() {
  const [data, setData] = useState<GraphData>(DEMO_DATA);
  const [loading, setLoading] = useState(true);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const [hoveredEdge, setHoveredEdge] = useState<number | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerWidth, setContainerWidth] = useState(1100);
  const locale = useLocale();
  const t = appDict.topology[locale] ?? appDict.topology.en;

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const result = await api.getGraphData();
      // Validate shape before casting to GraphData
      if (result && Array.isArray(result.nodes) && Array.isArray(result.edges)) {
        setData(result as unknown as GraphData);
      }
    } catch {
      // Use demo data
    }

    // Apply simulation results from localStorage if available
    try {
      const saved = localStorage.getItem("faultray_last_simulation");
      if (saved) {
        const sim = JSON.parse(saved);
        if (sim.overall_score !== undefined) {
          setData((prev) => ({
            ...prev,
            nodes: prev.nodes.map((node) => {
              const isCritical = (sim.critical_failures || []).some(
                (f: { scenario: string }) => f.scenario.toLowerCase().includes(node.name.toLowerCase().split(" ")[0])
              );
              if (isCritical) {
                return { ...node, risk: Math.max(node.risk, 75) };
              }
              const scoreRatio = (100 - sim.overall_score) / 100;
              return { ...node, risk: Math.round(node.risk * (1 + scoreRatio * 0.3)) };
            }),
          }));
          setSimScore(sim.overall_score);
          setSimTimestamp(sim.timestamp || null);
        }
      }
    } catch {
      // localStorage not available
    }

    setLoading(false);
  }, []);

  const [simScore, setSimScore] = useState<number | null>(null);
  const [simTimestamp, setSimTimestamp] = useState<string | null>(null);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Responsive width
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const obs = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setContainerWidth(entry.contentRect.width);
      }
    });
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  const layout = useMemo(
    () => layoutNodes(data.nodes, data.edges, containerWidth),
    [data.nodes, data.edges, containerWidth],
  );
  const { positions, totalHeight, totalWidth, nodeW, nodeH } = layout;

  const nodeMap = Object.fromEntries(data.nodes.map((n) => [n.id, n]));
  const selected = selectedNode ? nodeMap[selectedNode] : null;
  const selectedRisk = selectedNode ? DEMO_RISK[selectedNode] : null;

  // Connected edges for highlighting
  const connectedEdges = useMemo(() => {
    const set = new Set<number>();
    const targetId = hoveredNode || selectedNode;
    if (targetId) {
      data.edges.forEach((e, i) => {
        if (e.source === targetId || e.target === targetId) set.add(i);
      });
    }
    return set;
  }, [hoveredNode, selectedNode, data.edges]);

  // Connected nodes for dimming
  const connectedNodes = useMemo(() => {
    const set = new Set<string>();
    const targetId = hoveredNode;
    if (targetId) {
      set.add(targetId);
      data.edges.forEach((e) => {
        if (e.source === targetId) set.add(e.target);
        if (e.target === targetId) set.add(e.source);
      });
    }
    return set;
  }, [hoveredNode, data.edges]);

  return (
    <div className="max-w-[1400px] mx-auto px-6 py-10">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold mb-1 flex items-center gap-3">
            <Network size={24} className="text-[#FFD700]" />
            {t.title}
          </h1>
          <p className="text-[#94a3b8] text-sm">{t.subtitle}</p>
        </div>
        <Button variant="secondary" size="sm" onClick={loadData} disabled={loading}>
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          {t.refresh}
        </Button>
      </div>

      {/* Description banner */}
      <div className="flex items-start gap-3 p-4 mb-6 rounded-xl bg-[#1e293b]/40 border border-[#1e293b]">
        <Info size={18} className="text-[#FFD700] mt-0.5 shrink-0" />
        <p className="text-sm text-[#94a3b8] leading-relaxed">
          {t.graphDescription}
        </p>
      </div>

      {/* Simulation score banner */}
      {simScore !== null && (
        <div className={`flex items-center justify-between p-4 mb-6 rounded-xl border ${
          simScore >= 80 ? "bg-emerald-500/5 border-emerald-500/20" : simScore >= 60 ? "bg-[#FFD700]/5 border-[#FFD700]/20" : "bg-red-500/5 border-red-500/20"
        }`}>
          <div className="flex items-center gap-3">
            <Activity size={18} className={simScore >= 80 ? "text-emerald-400" : simScore >= 60 ? "text-[#FFD700]" : "text-red-400"} />
            <div>
              <span className="text-sm font-semibold">{locale === "ja" ? "最新シミュレーション結果を反映中" : "Reflecting latest simulation results"}</span>
              {simTimestamp && (
                <span className="text-xs text-[#64748b] ml-2">
                  {new Date(simTimestamp).toLocaleString(locale === "ja" ? "ja-JP" : "en-US")}
                </span>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className={`text-2xl font-bold font-mono ${simScore >= 80 ? "text-emerald-400" : simScore >= 60 ? "text-[#FFD700]" : "text-red-400"}`}>
              {simScore.toFixed(1)}
            </span>
            <span className="text-xs text-[#64748b]">/ 100</span>
          </div>
        </div>
      )}

      {loading ? (
        <Card className="flex items-center justify-center py-20">
          <Loader2 size={24} className="animate-spin text-[#FFD700]" />
          <span className="ml-3 text-[#94a3b8]">{t.loading}</span>
        </Card>
      ) : (
        <div className="grid lg:grid-cols-[1fr_360px] gap-6">
          {/* Main Graph Canvas */}
          <div ref={containerRef}>
          <Card className="p-0 overflow-auto">
            <div className="p-4 border-b border-[#1e293b] flex items-center justify-between">
              <div className="flex items-center gap-4 text-xs text-[#64748b]">
                <span className="flex items-center gap-1.5">
                  <span className="w-6 h-0 border-t-[2.5px] border-[#475569] inline-block" />
                  {t.requires}
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="w-6 h-0 border-t-2 border-dashed border-[#475569] inline-block" />
                  {t.optional}
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="w-6 h-0 border-t-2 border-dotted border-[#d4a017] inline-block" />
                  {t.async}
                </span>
              </div>
              <div className="flex items-center gap-3 text-xs text-[#64748b]">
                <span>{t.componentsCount}: <strong className="text-white font-mono">{data.nodes.length}</strong></span>
                <span>{t.dependenciesCount}: <strong className="text-white font-mono">{data.edges.length}</strong></span>
              </div>
            </div>

            <svg
              viewBox={`0 0 ${totalWidth} ${totalHeight}`}
              className="w-full"
              style={{ minHeight: 500, background: "linear-gradient(180deg, #0a0f1a 0%, #0d1320 100%)" }}
            >
              <defs>
                {/* Grid pattern */}
                <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
                  <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#1e293b" strokeWidth="0.5" strokeOpacity="0.3" />
                </pattern>
                {/* Arrow markers */}
                <marker id="arrow-default" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="8" markerHeight="8" orient="auto">
                  <path d="M 0 1 L 10 5 L 0 9 z" fill="#475569" />
                </marker>
                <marker id="arrow-highlight" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="8" markerHeight="8" orient="auto">
                  <path d="M 0 1 L 10 5 L 0 9 z" fill="#FFD700" />
                </marker>
                <marker id="arrow-connected" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="8" markerHeight="8" orient="auto">
                  <path d="M 0 1 L 10 5 L 0 9 z" fill="#94a3b8" />
                </marker>
                <marker id="arrow-async" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="8" markerHeight="8" orient="auto">
                  <path d="M 0 1 L 10 5 L 0 9 z" fill="#d4a017" />
                </marker>
                {/* Glow filters */}
                <filter id="glow-red" x="-30%" y="-30%" width="160%" height="160%">
                  <feGaussianBlur stdDeviation="6" result="blur" />
                  <feFlood floodColor="#ef4444" floodOpacity="0.25" result="color" />
                  <feComposite in="color" in2="blur" operator="in" result="glow" />
                  <feMerge>
                    <feMergeNode in="glow" />
                    <feMergeNode in="SourceGraphic" />
                  </feMerge>
                </filter>
                <filter id="glow-selected" x="-20%" y="-20%" width="140%" height="140%">
                  <feGaussianBlur stdDeviation="4" result="blur" />
                  <feFlood floodColor="#FFD700" floodOpacity="0.2" result="color" />
                  <feComposite in="color" in2="blur" operator="in" result="glow" />
                  <feMerge>
                    <feMergeNode in="glow" />
                    <feMergeNode in="SourceGraphic" />
                  </feMerge>
                </filter>
                <filter id="shadow" x="-10%" y="-10%" width="120%" height="130%">
                  <feDropShadow dx="0" dy="4" stdDeviation="8" floodColor="#000000" floodOpacity="0.4" />
                </filter>
              </defs>

              {/* Background grid */}
              <rect width="100%" height="100%" fill="url(#grid)" />

              {/* Edges */}
              {data.edges.map((edge, i) => {
                const from = positions[edge.source];
                const to = positions[edge.target];
                if (!from || !to) return null;

                const isAsync = edge.type === "async";
                const isOptional = edge.type === "optional";
                const isHovered = hoveredEdge === i;
                const isConnected = connectedEdges.has(i);

                const dashArray = isOptional ? "12,6" : isAsync ? "6,6" : "none";
                const baseColor = isAsync ? "#d4a017" : "#334155";
                const strokeColor = isHovered ? "#FFD700" : isConnected ? "#94a3b8" : baseColor;
                const strokeWidth = isHovered ? 3 : isConnected ? 2.5 : isAsync ? 1.5 : 2;

                const markerEnd = isHovered
                  ? "url(#arrow-highlight)"
                  : isConnected
                    ? "url(#arrow-connected)"
                    : isAsync
                      ? "url(#arrow-async)"
                      : "url(#arrow-default)";

                const pathD = computeEdgePath(from, to, nodeW, nodeH);

                const edgeLabel =
                  edge.type === "requires" ? t.requires
                    : edge.type === "optional" ? t.optional
                      : t.async;

                // Midpoint for label
                const midX = (from.x + nodeW / 2 + to.x + nodeW / 2) / 2;
                const midY = (from.y + nodeH + to.y) / 2;

                return (
                  <g
                    key={i}
                    onMouseEnter={() => setHoveredEdge(i)}
                    onMouseLeave={() => setHoveredEdge(null)}
                    className="cursor-pointer"
                    style={{ opacity: hoveredNode && !isConnected && !isHovered ? 0.15 : 1, transition: "opacity 0.2s" }}
                  >
                    {/* Hit area */}
                    <path d={pathD} stroke="transparent" strokeWidth={24} fill="none" />
                    <path
                      d={pathD}
                      stroke={strokeColor}
                      strokeWidth={strokeWidth}
                      strokeDasharray={dashArray}
                      markerEnd={markerEnd}
                      fill="none"
                      strokeLinecap="round"
                      style={{ transition: "stroke 0.2s, stroke-width 0.2s" }}
                    />
                    {isHovered && (
                      <g>
                        <rect
                          x={midX - 40}
                          y={midY - 12}
                          width={80}
                          height={24}
                          rx={12}
                          fill="#0f172a"
                          stroke="#FFD700"
                          strokeWidth={1}
                        />
                        <text
                          x={midX}
                          y={midY + 4}
                          textAnchor="middle"
                          fontSize="10"
                          fill="#FFD700"
                          fontWeight="600"
                          fontFamily="system-ui, sans-serif"
                        >
                          {edgeLabel}
                        </text>
                      </g>
                    )}
                  </g>
                );
              })}

              {/* Nodes */}
              {data.nodes.map((node) => {
                const pos = positions[node.id];
                if (!pos) return null;
                const risk = DEMO_RISK[node.id];
                const score = risk?.risk_score ?? 0;
                const svc = getServiceColor(node.type);
                const isSelected = selectedNode === node.id;
                const isHovered = hoveredNode === node.id;
                const isHighRisk = score >= 70;
                const isDimmed = hoveredNode !== null && connectedNodes.size > 0 && !connectedNodes.has(node.id);

                const x = pos.x;
                const y = pos.y;

                // Risk bar width (max ~100px)
                const barWidth = 100;
                const filledWidth = (score / 100) * barWidth;

                let filterAttr: string | undefined;
                if (isSelected) filterAttr = "url(#glow-selected)";
                else if (isHighRisk) filterAttr = "url(#glow-red)";

                return (
                  <g
                    key={node.id}
                    className="cursor-pointer"
                    onClick={() => setSelectedNode(isSelected ? null : node.id)}
                    onMouseEnter={() => setHoveredNode(node.id)}
                    onMouseLeave={() => setHoveredNode(null)}
                    filter={filterAttr}
                    style={{
                      opacity: isDimmed ? 0.2 : 1,
                      transition: "opacity 0.2s",
                    }}
                  >
                    {/* High risk pulse animation */}
                    {isHighRisk && (
                      <rect
                        x={x - 3}
                        y={y - 3}
                        width={nodeW + 6}
                        height={nodeH + 6}
                        rx={14}
                        fill="none"
                        stroke="#ef4444"
                        strokeWidth={1.5}
                        strokeOpacity={0.4}
                      >
                        <animate
                          attributeName="stroke-opacity"
                          values="0.4;0.1;0.4"
                          dur="2s"
                          repeatCount="indefinite"
                        />
                        <animate
                          attributeName="stroke-width"
                          values="1.5;3;1.5"
                          dur="2s"
                          repeatCount="indefinite"
                        />
                      </rect>
                    )}

                    {/* Card shadow */}
                    <rect
                      x={x}
                      y={y}
                      width={nodeW}
                      height={nodeH}
                      rx={12}
                      fill="none"
                      filter="url(#shadow)"
                    />

                    {/* Card background */}
                    <rect
                      x={x}
                      y={y}
                      width={nodeW}
                      height={nodeH}
                      rx={12}
                      fill={isSelected ? "#1a2235" : isHovered ? "#151d2e" : "#111827"}
                      stroke={isSelected ? "#FFD700" : isHovered ? svc.primary : "#1e293b"}
                      strokeWidth={isSelected ? 2 : 1.5}
                    />

                    {/* Left accent bar */}
                    <rect
                      x={x}
                      y={y + 12}
                      width={4}
                      height={nodeH - 24}
                      rx={2}
                      fill={svc.primary}
                    />

                    {/* Cloud icon (foreignObject for React component) */}
                    <foreignObject x={x + 14} y={y + 12} width={40} height={40}>
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", width: 40, height: 40 }}>
                        <CloudIcon type={node.type} size={36} />
                      </div>
                    </foreignObject>

                    {/* Service name */}
                    <text
                      x={x + 60}
                      y={y + 28}
                      fontSize="13"
                      fill="#e2e8f0"
                      fontWeight="700"
                      fontFamily="system-ui, sans-serif"
                    >
                      {node.name}
                    </text>

                    {/* Service type label */}
                    <text
                      x={x + 60}
                      y={y + 44}
                      fontSize="10"
                      fill={svc.primary}
                      fontWeight="500"
                      fontFamily="system-ui, sans-serif"
                      opacity="0.8"
                    >
                      {svc.label}
                    </text>

                    {/* Replicas badge */}
                    {node.replicas && (
                      <g>
                        <rect
                          x={x + nodeW - 44}
                          y={y + 10}
                          width={34}
                          height={18}
                          rx={9}
                          fill="#10b981"
                          fillOpacity="0.15"
                          stroke="#10b981"
                          strokeWidth={0.5}
                          strokeOpacity={0.4}
                        />
                        <text
                          x={x + nodeW - 27}
                          y={y + 23}
                          textAnchor="middle"
                          fontSize="9"
                          fill="#10b981"
                          fontWeight="700"
                          fontFamily="monospace"
                        >
                          x{node.replicas}
                        </text>
                      </g>
                    )}

                    {/* Risk bar */}
                    <g>
                      <text
                        x={x + 60}
                        y={y + 64}
                        fontSize="9"
                        fill="#64748b"
                        fontFamily="system-ui, sans-serif"
                      >
                        Risk
                      </text>
                      {/* Bar background */}
                      <rect
                        x={x + 60}
                        y={y + 70}
                        width={barWidth}
                        height={6}
                        rx={3}
                        fill="#1e293b"
                      />
                      {/* Bar fill */}
                      <rect
                        x={x + 60}
                        y={y + 70}
                        width={filledWidth}
                        height={6}
                        rx={3}
                        fill={riskColor(score)}
                        fillOpacity="0.8"
                      />
                      {/* Score text */}
                      <text
                        x={x + 60 + barWidth + 8}
                        y={y + 77}
                        fontSize="11"
                        fill={riskColor(score)}
                        fontWeight="800"
                        fontFamily="monospace"
                      >
                        {score}
                      </text>
                    </g>

                    {/* Provider / Region */}
                    {node.provider && (
                      <text
                        x={x + 60}
                        y={y + 95}
                        fontSize="9"
                        fill="#475569"
                        fontFamily="monospace"
                      >
                        {node.provider} / {node.region || "—"}
                      </text>
                    )}

                    {/* Risk score badge top-right */}
                    <rect
                      x={x + nodeW - 44}
                      y={y + nodeH - 28}
                      width={34}
                      height={20}
                      rx={10}
                      fill={riskBgColor(score)}
                      stroke={riskBorderColor(score)}
                      strokeWidth={1}
                    />
                    <text
                      x={x + nodeW - 27}
                      y={y + nodeH - 14}
                      textAnchor="middle"
                      fontSize="10"
                      fill={riskColor(score)}
                      fontWeight="800"
                      fontFamily="monospace"
                    >
                      {score}
                    </text>
                  </g>
                );
              })}
            </svg>
          </Card>
          </div>

          {/* Sidebar */}
          <div className="space-y-4">
            {/* Component Types Legend */}
            <Card className="p-5">
              <h3 className="text-xs font-semibold text-[#64748b] uppercase tracking-wider mb-3">{t.typeLegend}</h3>
              <div className="grid grid-cols-2 gap-2">
                {Array.from(new Set(data.nodes.map(n => n.type))).map((type) => {
                  const svc = getServiceColor(type);
                  return (
                    <div key={type} className="flex items-center gap-2 p-1.5 rounded-lg hover:bg-[#1e293b]/50 transition-colors">
                      <CloudIcon type={type} size={20} />
                      <span className="text-xs text-[#e2e8f0] font-medium truncate">{svc.label}</span>
                    </div>
                  );
                })}
              </div>
            </Card>

            {/* Risk Level Legend */}
            <Card className="p-5">
              <h3 className="text-xs font-semibold text-[#64748b] uppercase tracking-wider mb-3">{t.riskLegend}</h3>
              <div className="space-y-2">
                {[
                  { color: "#10b981", label: t.lowRisk, range: "0-29" },
                  { color: "#eab308", label: t.mediumRisk, range: "30-49" },
                  { color: "#f59e0b", label: t.mediumRisk, range: "50-69" },
                  { color: "#ef4444", label: t.highRisk, range: "70+" },
                ].map((item) => (
                  <div key={item.range} className="flex items-center gap-3">
                    <div className="w-8 h-2 rounded-full" style={{ backgroundColor: item.color, opacity: 0.8 }} />
                    <span className="text-xs text-[#94a3b8]">{item.label}</span>
                    <span className="text-xs text-[#475569] ml-auto font-mono">{item.range}</span>
                  </div>
                ))}
              </div>
            </Card>

            {/* Node Details Panel */}
            {selected && selectedRisk ? (
              <Card className="p-5">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-xs font-semibold text-[#64748b] uppercase tracking-wider">
                    {t.componentDetails}
                  </h3>
                  <button onClick={() => setSelectedNode(null)} className="text-[#64748b] hover:text-white transition-colors">
                    <X size={14} />
                  </button>
                </div>

                <div className="space-y-4">
                  {/* Header */}
                  <div className="flex items-start gap-3">
                    <CloudIcon type={selected.type} size={36} />
                    <div>
                      <p className="text-base font-bold text-white">{selected.name}</p>
                      <div className="flex items-center gap-2 mt-1">
                        <Badge
                          variant="gold"
                          style={{
                            backgroundColor: getServiceColor(selected.type).bg,
                            color: getServiceColor(selected.type).primary,
                            borderColor: getServiceColor(selected.type).primary + "40",
                          }}
                        >
                          {getServiceColor(selected.type).label}
                        </Badge>
                        <Badge variant={selectedRisk.risk_score >= 70 ? "red" : selectedRisk.risk_score >= 50 ? "yellow" : "green"}>
                          {riskLabel(selectedRisk.risk_score, locale)}
                        </Badge>
                      </div>
                    </div>
                  </div>

                  {/* Risk Score Bar */}
                  <div className="p-3 rounded-xl" style={{ backgroundColor: riskBgColor(selectedRisk.risk_score) }}>
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs text-[#94a3b8]">{t.riskScore}</span>
                      <span className="text-2xl font-extrabold font-mono" style={{ color: riskColor(selectedRisk.risk_score) }}>
                        {selectedRisk.risk_score}
                      </span>
                    </div>
                    <div className="w-full h-2 rounded-full bg-[#1e293b]">
                      <div
                        className="h-2 rounded-full transition-all duration-500"
                        style={{
                          width: `${selectedRisk.risk_score}%`,
                          backgroundColor: riskColor(selectedRisk.risk_score),
                          opacity: 0.8,
                        }}
                      />
                    </div>
                  </div>

                  {/* Metrics */}
                  {selectedRisk.metrics && (
                    <div className="grid grid-cols-3 gap-2">
                      {selectedRisk.metrics.latency_p99 && (
                        <div className="text-center p-2 rounded-lg bg-[#1e293b]/50">
                          <Activity size={12} className="mx-auto mb-1 text-[#64748b]" />
                          <p className="text-xs font-mono font-bold text-white">{selectedRisk.metrics.latency_p99}</p>
                          <p className="text-[9px] text-[#475569]">P99</p>
                        </div>
                      )}
                      {selectedRisk.metrics.throughput && (
                        <div className="text-center p-2 rounded-lg bg-[#1e293b]/50">
                          <Zap size={12} className="mx-auto mb-1 text-[#64748b]" />
                          <p className="text-xs font-mono font-bold text-white">{selectedRisk.metrics.throughput}</p>
                          <p className="text-[9px] text-[#475569]">{locale === "ja" ? "スループット" : "Throughput"}</p>
                        </div>
                      )}
                      {selectedRisk.metrics.error_rate && (
                        <div className="text-center p-2 rounded-lg bg-[#1e293b]/50">
                          <Shield size={12} className="mx-auto mb-1 text-[#64748b]" />
                          <p className="text-xs font-mono font-bold text-white">{selectedRisk.metrics.error_rate}</p>
                          <p className="text-[9px] text-[#475569]">{locale === "ja" ? "エラー率" : "Error"}</p>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Info rows */}
                  <div className="space-y-1.5 text-sm">
                    {selected.replicas && (
                      <div className="flex justify-between">
                        <span className="text-[#64748b]">{t.replicas}</span>
                        <span className="font-mono text-white">{selected.replicas}</span>
                      </div>
                    )}
                    {selected.provider && (
                      <div className="flex justify-between">
                        <span className="text-[#64748b]">{locale === "ja" ? "プロバイダー" : "Provider"}</span>
                        <span className="font-mono text-white uppercase">{selected.provider}</span>
                      </div>
                    )}
                    {selected.region && (
                      <div className="flex justify-between">
                        <span className="text-[#64748b]">{locale === "ja" ? "リージョン" : "Region"}</span>
                        <span className="font-mono text-white">{selected.region}</span>
                      </div>
                    )}
                  </div>

                  {/* Dependencies */}
                  <div>
                    <p className="text-xs text-[#64748b] mb-2">{t.dependenciesLabel}</p>
                    {data.edges
                      .filter((e) => e.source === selected.id)
                      .map((e) => (
                        <div
                          key={e.target}
                          className="flex items-center gap-2 text-sm text-[#94a3b8] mb-1 p-1.5 rounded-lg hover:bg-[#1e293b]/50 cursor-pointer transition-colors"
                          onClick={(ev) => { ev.stopPropagation(); setSelectedNode(e.target); }}
                        >
                          <ArrowRight size={12} />
                          <span className="truncate">{nodeMap[e.target]?.name || e.target}</span>
                          <Badge variant={e.type === "requires" ? "red" : e.type === "async" ? "gold" : "default"}>
                            {e.type || "requires"}
                          </Badge>
                        </div>
                      ))}
                    {data.edges.filter((e) => e.source === selected.id).length === 0 && (
                      <p className="text-xs text-[#475569]">{t.noOutgoing}</p>
                    )}
                  </div>

                  {/* Failure Scenarios */}
                  <div>
                    <p className="text-xs text-[#64748b] mb-2 flex items-center gap-1">
                      <AlertTriangle size={12} className="text-red-400" />
                      {t.failureScenarios}
                    </p>
                    <div className="space-y-1.5">
                      {selectedRisk.failure_scenarios.map((scenario, i) => (
                        <div key={i} className="text-xs text-[#94a3b8] p-2.5 rounded-lg bg-red-500/5 border border-red-500/10 leading-relaxed">
                          {scenario}
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Suggestions */}
                  <div>
                    <p className="text-xs text-[#64748b] mb-2 flex items-center gap-1">
                      <Lightbulb size={12} className="text-[#FFD700]" />
                      {t.suggestions}
                    </p>
                    <div className="space-y-1.5">
                      {selectedRisk.suggestions.map((suggestion, i) => (
                        <div key={i} className="text-xs text-[#94a3b8] p-2.5 rounded-lg bg-[#FFD700]/5 border border-[#FFD700]/10 leading-relaxed">
                          {suggestion}
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </Card>
            ) : (
              <Card className="p-5">
                <p className="text-sm text-[#475569] text-center py-6">
                  {t.clickToViewDetails}
                </p>
              </Card>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
