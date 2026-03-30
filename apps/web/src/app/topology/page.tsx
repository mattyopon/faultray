"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import {
  Network,
  ArrowRight,
  Loader2,
  RefreshCw,
  AlertTriangle,
  Lightbulb,
  X,
  Database,
  Server,
  Globe,
  HardDrive,
  MessageSquare,
  Info,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useLocale } from "@/lib/useLocale";
import type { Locale } from "@/i18n/config";
import { appDict } from "@/i18n/app-dict";

interface GraphNode {
  id: string;
  name: string;
  type: string;
  replicas?: number;
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

// Risk data per node - from simulation results
interface NodeRiskData {
  risk_score: number;
  failure_scenarios: string[];
  suggestions: string[];
}

const DEMO_DATA: GraphData = {
  nodes: [
    { id: "cdn", name: "CDN / Edge", type: "load_balancer", replicas: 3 },
    { id: "gateway", name: "API Gateway", type: "load_balancer", replicas: 2 },
    { id: "auth", name: "Auth Service", type: "app_server", replicas: 2 },
    { id: "api", name: "API Server", type: "app_server", replicas: 3 },
    { id: "worker", name: "Background Worker", type: "app_server", replicas: 2 },
    { id: "db_primary", name: "PostgreSQL Primary", type: "database", replicas: 1 },
    { id: "db_replica", name: "PostgreSQL Replica", type: "database", replicas: 2 },
    { id: "cache", name: "Redis Cache", type: "cache", replicas: 3 },
  ],
  edges: [
    { source: "cdn", target: "gateway", type: "requires" },
    { source: "gateway", target: "auth", type: "requires" },
    { source: "gateway", target: "api", type: "requires" },
    { source: "api", target: "db_primary", type: "requires" },
    { source: "api", target: "cache", type: "optional" },
    { source: "api", target: "worker", type: "async" },
    { source: "worker", target: "db_primary", type: "requires" },
    { source: "db_primary", target: "db_replica", type: "async" },
  ],
};

// Demo risk data for each node
const DEMO_RISK: Record<string, NodeRiskData> = {
  cdn: { risk_score: 12, failure_scenarios: ["DDoS attack overwhelms edge capacity"], suggestions: ["Add rate limiting at edge layer"] },
  gateway: { risk_score: 25, failure_scenarios: ["Certificate expiry blocks all HTTPS", "Rate limit misconfiguration"], suggestions: ["Automate certificate renewal", "Configure adaptive rate limits"] },
  auth: { risk_score: 45, failure_scenarios: ["Token validation service outage", "Brute force attack"], suggestions: ["Implement token caching", "Add account lockout policy"] },
  api: { risk_score: 38, failure_scenarios: ["Thread pool exhaustion under load", "Memory leak in long-running processes"], suggestions: ["Configure connection limits and auto-scaling", "Add memory monitoring alerts"] },
  worker: { risk_score: 30, failure_scenarios: ["Job queue backlog during peak"], suggestions: ["Implement dead letter queue with monitoring"] },
  db_primary: { risk_score: 78, failure_scenarios: ["Single point of failure - complete crash causes full outage", "Disk I/O saturation", "Connection pool exhaustion"], suggestions: ["Implement automated failover with < 30s switchover", "Add read replicas for load distribution", "Monitor disk I/O and set alerts at 80%"] },
  db_replica: { risk_score: 35, failure_scenarios: ["Replication lag exceeds threshold"], suggestions: ["Monitor replication lag, alert at > 5s"] },
  cache: { risk_score: 55, failure_scenarios: ["Memory exhaustion causes eviction storm", "Network partition causes split-brain"], suggestions: ["Set memory limits and eviction policies", "Deploy across multiple AZs"] },
};

// Component type config: icon component, color, label
const TYPE_CONFIG: Record<string, { color: string; bgColor: string; label: string }> = {
  database: { color: "#f97316", bgColor: "#f9731615", label: "DB" },
  app_server: { color: "#22c55e", bgColor: "#22c55e15", label: "APP" },
  load_balancer: { color: "#3b82f6", bgColor: "#3b82f615", label: "LB" },
  cache: { color: "#ef4444", bgColor: "#ef444415", label: "CACHE" },
  queue: { color: "#a855f7", bgColor: "#a855f715", label: "QUEUE" },
  dns: { color: "#06b6d4", bgColor: "#06b6d415", label: "DNS" },
  storage: { color: "#64748b", bgColor: "#64748b15", label: "STORE" },
  custom: { color: "#94a3b8", bgColor: "#94a3b815", label: "SVC" },
};

function getTypeConfig(type: string) {
  return TYPE_CONFIG[type] || TYPE_CONFIG.custom;
}

function TypeIcon({ type, size = 16 }: { type: string; size?: number }) {
  const props = { size, className: "shrink-0" };
  switch (type) {
    case "database": return <Database {...props} />;
    case "cache": return <HardDrive {...props} />;
    case "load_balancer": return <Globe {...props} />;
    case "queue": return <MessageSquare {...props} />;
    default: return <Server {...props} />;
  }
}

// Risk-based color (green -> yellow -> red)
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

// Layout nodes in layers
function layoutNodes(nodes: GraphNode[], edges: GraphEdge[]) {
  const layers: string[][] = [];
  const placed = new Set<string>();
  const targets = new Set(edges.map((e) => e.target));
  const sources = new Set(edges.map((e) => e.source));

  const roots = nodes.filter((n) => sources.has(n.id) && !targets.has(n.id));
  if (roots.length === 0 && nodes.length > 0) roots.push(nodes[0]);

  const queue = roots.map((r) => ({ id: r.id, depth: 0 }));
  const depthMap: Record<string, number> = {};
  for (const r of roots) depthMap[r.id] = 0;

  while (queue.length > 0) {
    const item = queue.shift()!;
    if (placed.has(item.id)) continue;
    placed.add(item.id);

    if (!layers[item.depth]) layers[item.depth] = [];
    layers[item.depth].push(item.id);

    for (const edge of edges) {
      if (edge.source === item.id && !placed.has(edge.target)) {
        const newDepth = item.depth + 1;
        if (!depthMap[edge.target] || depthMap[edge.target] < newDepth) {
          depthMap[edge.target] = newDepth;
        }
        queue.push({ id: edge.target, depth: newDepth });
      }
    }
  }

  for (const n of nodes) {
    if (!placed.has(n.id)) {
      if (!layers[0]) layers[0] = [];
      layers[0].push(n.id);
    }
  }

  const positions: Record<string, { x: number; y: number }> = {};
  const svgWidth = 960;
  const layerHeight = 150;

  for (let i = 0; i < layers.length; i++) {
    const layer = layers[i];
    const spacing = svgWidth / (layer.length + 1);
    for (let j = 0; j < layer.length; j++) {
      positions[layer[j]] = {
        x: spacing * (j + 1),
        y: 80 + i * layerHeight,
      };
    }
  }

  return { positions, height: 80 + layers.length * layerHeight + 60 };
}

export default function TopologyPage() {
  const [data, setData] = useState<GraphData>(DEMO_DATA);
  const [loading, setLoading] = useState(true);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const [hoveredEdge, setHoveredEdge] = useState<number | null>(null);
  const locale = useLocale();
  const t = appDict.topology[locale] ?? appDict.topology.en;

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const result = await api.getGraphData();
      const graphData = result as unknown as GraphData;
      if (graphData.nodes && graphData.edges) {
        setData(graphData);
      }
    } catch {
      // Use demo data
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const { positions, height } = layoutNodes(data.nodes, data.edges);
  const nodeMap = Object.fromEntries(data.nodes.map((n) => [n.id, n]));
  const selected = selectedNode ? nodeMap[selectedNode] : null;
  const selectedRisk = selectedNode ? DEMO_RISK[selectedNode] : null;

  // Find connected edges for highlighting
  const connectedEdges = new Set<number>();
  if (hoveredNode || selectedNode) {
    const targetId = hoveredNode || selectedNode;
    data.edges.forEach((e, i) => {
      if (e.source === targetId || e.target === targetId) {
        connectedEdges.add(i);
      }
    });
  }

  return (
    <div className="max-w-[1200px] mx-auto px-6 py-10">
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

      {loading ? (
        <Card className="flex items-center justify-center py-20">
          <Loader2 size={24} className="animate-spin text-[#FFD700]" />
          <span className="ml-3 text-[#94a3b8]">{t.loading}</span>
        </Card>
      ) : (
        <div className="grid lg:grid-cols-[1fr_340px] gap-6">
          <Card className="p-4 overflow-auto">
            <svg viewBox={`0 0 960 ${height}`} className="w-full" style={{ minHeight: 450 }}>
              <defs>
                <marker id="arrow" viewBox="0 0 12 12" refX="12" refY="6" markerWidth="10" markerHeight="10" orient="auto">
                  <path d="M 0 0 L 12 6 L 0 12 z" fill="#475569" />
                </marker>
                <marker id="arrow-active" viewBox="0 0 12 12" refX="12" refY="6" markerWidth="10" markerHeight="10" orient="auto">
                  <path d="M 0 0 L 12 6 L 0 12 z" fill="#FFD700" />
                </marker>
                <marker id="arrow-connected" viewBox="0 0 12 12" refX="12" refY="6" markerWidth="10" markerHeight="10" orient="auto">
                  <path d="M 0 0 L 12 6 L 0 12 z" fill="#94a3b8" />
                </marker>
                {/* Glow filter for high-risk nodes */}
                <filter id="glow-red" x="-20%" y="-20%" width="140%" height="140%">
                  <feGaussianBlur stdDeviation="4" result="blur" />
                  <feFlood floodColor="#ef4444" floodOpacity="0.3" result="color" />
                  <feComposite in="color" in2="blur" operator="in" result="glow" />
                  <feMerge>
                    <feMergeNode in="glow" />
                    <feMergeNode in="SourceGraphic" />
                  </feMerge>
                </filter>
              </defs>

              {/* Edges */}
              {data.edges.map((edge, i) => {
                const from = positions[edge.source];
                const to = positions[edge.target];
                if (!from || !to) return null;

                const isRequires = edge.type === "requires" || !edge.type;
                const isOptional = edge.type === "optional";
                const isAsync = edge.type === "async";

                const dashArray = isOptional ? "10,5" : isAsync ? "5,5" : "none";
                const isHovered = hoveredEdge === i;
                const isConnected = connectedEdges.has(i);

                const strokeColor = isHovered ? "#FFD700" : isConnected ? "#94a3b8" : "#334155";
                const strokeWidth = isRequires
                  ? (isHovered ? 3.5 : isConnected ? 2.5 : 2.5)
                  : (isHovered ? 3 : isConnected ? 2 : 1.5);

                const markerEnd = isHovered
                  ? "url(#arrow-active)"
                  : isConnected
                    ? "url(#arrow-connected)"
                    : "url(#arrow)";

                const edgeLabel = edge.type === "requires"
                  ? t.requires
                  : edge.type === "optional"
                    ? t.optional
                    : t.async;

                // Calculate line endpoints to stop at node card edges
                const nodeHeight = 56;
                const fromY = from.y + nodeHeight / 2;
                const toY = to.y - nodeHeight / 2;

                return (
                  <g
                    key={i}
                    onMouseEnter={() => setHoveredEdge(i)}
                    onMouseLeave={() => setHoveredEdge(null)}
                    className="cursor-pointer"
                  >
                    {/* Wider invisible hit area */}
                    <line
                      x1={from.x}
                      y1={fromY}
                      x2={to.x}
                      y2={toY}
                      stroke="transparent"
                      strokeWidth={20}
                    />
                    <line
                      x1={from.x}
                      y1={fromY}
                      x2={to.x}
                      y2={toY}
                      stroke={strokeColor}
                      strokeWidth={strokeWidth}
                      strokeDasharray={dashArray}
                      markerEnd={markerEnd}
                      className="transition-all duration-200"
                      strokeLinecap="round"
                    />
                    {isHovered && (
                      <>
                        <rect
                          x={(from.x + to.x) / 2 - 44}
                          y={(fromY + toY) / 2 - 12}
                          width={88}
                          height={24}
                          rx={6}
                          fill="#0f172a"
                          stroke="#FFD700"
                          strokeWidth={1}
                        />
                        <text
                          x={(from.x + to.x) / 2}
                          y={(fromY + toY) / 2 + 4}
                          textAnchor="middle"
                          fontSize="11"
                          fill="#FFD700"
                          fontWeight="600"
                        >
                          {edgeLabel}
                        </text>
                      </>
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
                const typeConf = getTypeConfig(node.type);
                const isSelected = selectedNode === node.id;
                const isHovered = hoveredNode === node.id;

                // Card dimensions
                const cardWidth = 170;
                const cardHeight = 56;
                const cardX = pos.x - cardWidth / 2;
                const cardY = pos.y - cardHeight / 2;

                const isHighRisk = score >= 70;

                return (
                  <g
                    key={node.id}
                    className="cursor-pointer"
                    onClick={() => setSelectedNode(isSelected ? null : node.id)}
                    onMouseEnter={() => setHoveredNode(node.id)}
                    onMouseLeave={() => setHoveredNode(null)}
                    filter={isHighRisk ? "url(#glow-red)" : undefined}
                  >
                    {/* Card background */}
                    <rect
                      x={cardX}
                      y={cardY}
                      width={cardWidth}
                      height={cardHeight}
                      rx={10}
                      fill={isSelected ? "#1e293b" : isHovered ? "#151d2e" : "#111827"}
                      stroke={isSelected ? typeConf.color : isHovered ? "#475569" : "#1e293b"}
                      strokeWidth={isSelected ? 2 : 1.5}
                    />

                    {/* Type color indicator bar (left side) */}
                    <rect
                      x={cardX}
                      y={cardY}
                      width={4}
                      height={cardHeight}
                      rx={2}
                      fill={typeConf.color}
                    />
                    {/* Fix corner: overlay rounded corners on left */}
                    <rect
                      x={cardX}
                      y={cardY}
                      width={10}
                      height={cardHeight}
                      rx={10}
                      fill={isSelected ? "#1e293b" : isHovered ? "#151d2e" : "#111827"}
                      stroke="none"
                    />
                    <rect
                      x={cardX}
                      y={cardY}
                      width={5}
                      height={cardHeight}
                      fill={typeConf.color}
                      clipPath={`inset(0 0 0 0 round 10px 0 0 10px)`}
                    />
                    {/* Simpler approach: just a colored left border */}
                    <line
                      x1={cardX + 1.5}
                      y1={cardY + 10}
                      x2={cardX + 1.5}
                      y2={cardY + cardHeight - 10}
                      stroke={typeConf.color}
                      strokeWidth={3}
                      strokeLinecap="round"
                    />

                    {/* Risk score badge (top right) */}
                    <rect
                      x={cardX + cardWidth - 38}
                      y={cardY + 6}
                      width={30}
                      height={18}
                      rx={9}
                      fill={riskBgColor(score)}
                      stroke={riskBorderColor(score)}
                      strokeWidth={1}
                    />
                    <text
                      x={cardX + cardWidth - 23}
                      y={cardY + 19}
                      textAnchor="middle"
                      fontSize="10"
                      fill={riskColor(score)}
                      fontWeight="bold"
                      fontFamily="monospace"
                    >
                      {score}
                    </text>

                    {/* Type badge */}
                    <rect
                      x={cardX + 12}
                      y={cardY + 6}
                      width={36}
                      height={16}
                      rx={4}
                      fill={typeConf.bgColor}
                    />
                    <text
                      x={cardX + 30}
                      y={cardY + 17}
                      textAnchor="middle"
                      fontSize="8"
                      fill={typeConf.color}
                      fontWeight="700"
                      letterSpacing="0.5"
                    >
                      {typeConf.label}
                    </text>

                    {/* Node name - full display with wrapping */}
                    <text
                      x={cardX + 12}
                      y={cardY + 38}
                      textAnchor="start"
                      fontSize="12"
                      fill="#e2e8f0"
                      fontWeight="600"
                    >
                      {node.name}
                    </text>

                    {/* Replicas indicator */}
                    {node.replicas && (
                      <>
                        <circle
                          cx={cardX + cardWidth - 23}
                          cy={cardY + cardHeight - 12}
                          r={8}
                          fill="#1e293b"
                          stroke="#334155"
                          strokeWidth={1}
                        />
                        <text
                          x={cardX + cardWidth - 23}
                          y={cardY + cardHeight - 8}
                          textAnchor="middle"
                          fontSize="8"
                          fill="#94a3b8"
                          fontWeight="600"
                          fontFamily="monospace"
                        >
                          x{node.replicas}
                        </text>
                      </>
                    )}
                  </g>
                );
              })}
            </svg>
          </Card>

          {/* Sidebar: Legend, Risk Legend, Details */}
          <div className="space-y-6">
            {/* Component Type Legend */}
            <Card>
              <h3 className="text-sm font-semibold text-[#94a3b8] uppercase tracking-wider mb-4">{t.typeLegend}</h3>
              <div className="space-y-2">
                {Object.entries(TYPE_CONFIG).filter(([key]) =>
                  data.nodes.some(n => n.type === key)
                ).map(([key, conf]) => (
                  <div key={key} className="flex items-center gap-3">
                    <div className="w-3 h-3 rounded" style={{ backgroundColor: conf.color }} />
                    <TypeIcon type={key} size={14} />
                    <span className="text-sm text-[#e2e8f0]">{conf.label}</span>
                    <span className="text-xs text-[#64748b]">{key.replace("_", " ")}</span>
                  </div>
                ))}
              </div>
            </Card>

            {/* Risk Color Legend */}
            <Card>
              <h3 className="text-sm font-semibold text-[#94a3b8] uppercase tracking-wider mb-4">{t.riskLegend}</h3>
              <div className="space-y-2">
                <div className="flex items-center gap-3">
                  <div className="w-3 h-3 rounded-full" style={{ backgroundColor: "#10b981" }} />
                  <span className="text-sm text-[#e2e8f0]">{t.lowRisk} (0-29)</span>
                </div>
                <div className="flex items-center gap-3">
                  <div className="w-3 h-3 rounded-full" style={{ backgroundColor: "#eab308" }} />
                  <span className="text-sm text-[#e2e8f0]">{t.mediumRisk} (30-49)</span>
                </div>
                <div className="flex items-center gap-3">
                  <div className="w-3 h-3 rounded-full" style={{ backgroundColor: "#f59e0b" }} />
                  <span className="text-sm text-[#e2e8f0]">{t.mediumRisk} (50-69)</span>
                </div>
                <div className="flex items-center gap-3">
                  <div className="w-3 h-3 rounded-full" style={{ backgroundColor: "#ef4444" }} />
                  <span className="text-sm text-[#e2e8f0]">{t.highRisk} (70+)</span>
                </div>
              </div>
              <div className="mt-4 pt-4 border-t border-[#1e293b] space-y-2">
                <div className="flex items-center gap-3">
                  <div className="w-8 h-0 border-t-[2.5px] border-[#475569]" />
                  <span className="text-xs text-[#64748b]">{t.requires} ({t.edgeSolid})</span>
                </div>
                <div className="flex items-center gap-3">
                  <div className="w-8 h-0 border-t-2 border-dashed border-[#475569]" />
                  <span className="text-xs text-[#64748b]">{t.optional} ({t.edgeDashed})</span>
                </div>
                <div className="flex items-center gap-3">
                  <div className="w-8 h-0 border-t-2 border-dotted border-[#475569]" />
                  <span className="text-xs text-[#64748b]">{t.async} ({t.edgeDotted})</span>
                </div>
              </div>
            </Card>

            {/* Node Details Panel */}
            {selected && selectedRisk ? (
              <Card>
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-sm font-semibold text-[#94a3b8] uppercase tracking-wider">
                    {t.componentDetails}
                  </h3>
                  <button onClick={() => setSelectedNode(null)} className="text-[#64748b] hover:text-white transition-colors">
                    <X size={14} />
                  </button>
                </div>
                <div className="space-y-4">
                  <div>
                    <div className="flex items-center gap-2 mb-2">
                      <TypeIcon type={selected.type} size={18} />
                      <p className="text-lg font-bold">{selected.name}</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge
                        variant="gold"
                        style={{ backgroundColor: getTypeConfig(selected.type).bgColor, color: getTypeConfig(selected.type).color, borderColor: getTypeConfig(selected.type).color + "40" }}
                      >
                        {selected.type.replace("_", " ")}
                      </Badge>
                      <Badge variant={selectedRisk.risk_score >= 70 ? "red" : selectedRisk.risk_score >= 50 ? "yellow" : "green"}>
                        {riskLabel(selectedRisk.risk_score, locale)}
                      </Badge>
                    </div>
                  </div>

                  {/* Risk Score */}
                  <div className="flex items-center justify-between p-3 rounded-lg" style={{ backgroundColor: riskBgColor(selectedRisk.risk_score) }}>
                    <span className="text-sm text-[#94a3b8]">{t.riskScore}</span>
                    <span className="text-2xl font-extrabold font-mono" style={{ color: riskColor(selectedRisk.risk_score) }}>
                      {selectedRisk.risk_score}
                    </span>
                  </div>

                  {selected.replicas && (
                    <div className="flex justify-between text-sm">
                      <span className="text-[#64748b]">{t.replicas}</span>
                      <span className="font-mono">{selected.replicas}</span>
                    </div>
                  )}

                  {/* Dependencies */}
                  <div>
                    <p className="text-xs text-[#64748b] mb-2">{t.dependenciesLabel}</p>
                    {data.edges
                      .filter((e) => e.source === selected.id)
                      .map((e) => (
                        <div key={e.target} className="flex items-center gap-2 text-sm text-[#94a3b8] mb-1">
                          <ArrowRight size={12} />
                          {nodeMap[e.target]?.name || e.target}
                          <Badge variant={e.type === "requires" ? "red" : "default"}>
                            {e.type || "requires"}
                          </Badge>
                        </div>
                      ))}
                    {data.edges.filter((e) => e.source === selected.id).length === 0 && (
                      <p className="text-xs text-[#64748b]">{t.noOutgoing}</p>
                    )}
                  </div>

                  {/* Failure Scenarios */}
                  <div>
                    <p className="text-xs text-[#64748b] mb-2 flex items-center gap-1">
                      <AlertTriangle size={12} className="text-red-400" />
                      {t.failureScenarios}
                    </p>
                    <div className="space-y-1">
                      {selectedRisk.failure_scenarios.map((scenario, i) => (
                        <div key={i} className="text-xs text-[#94a3b8] p-2 rounded-lg bg-red-500/5 border border-red-500/10">
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
                    <div className="space-y-1">
                      {selectedRisk.suggestions.map((suggestion, i) => (
                        <div key={i} className="text-xs text-[#94a3b8] p-2 rounded-lg bg-[#FFD700]/5 border border-[#FFD700]/10">
                          {suggestion}
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </Card>
            ) : (
              <Card>
                <p className="text-sm text-[#64748b] text-center py-4">
                  {t.clickToViewDetails}
                </p>
              </Card>
            )}

            <Card>
              <div className="flex justify-between text-sm">
                <span className="text-[#64748b]">{t.componentsCount}</span>
                <span className="font-mono font-bold">{data.nodes.length}</span>
              </div>
              <div className="flex justify-between text-sm mt-2">
                <span className="text-[#64748b]">{t.dependenciesCount}</span>
                <span className="font-mono font-bold">{data.edges.length}</span>
              </div>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}
