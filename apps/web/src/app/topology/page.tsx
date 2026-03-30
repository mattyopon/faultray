"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import { Network, ArrowRight, Loader2, RefreshCw, AlertTriangle, Shield, Lightbulb, X } from "lucide-react";
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

const TYPE_LABELS: Record<string, string> = {
  load_balancer: "LB",
  app_server: "APP",
  database: "DB",
  cache: "CACHE",
  queue: "QUEUE",
  dns: "DNS",
  storage: "STORE",
  custom: "SVC",
};

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
  const svgWidth = 900;
  const layerHeight = 130;

  for (let i = 0; i < layers.length; i++) {
    const layer = layers[i];
    const spacing = svgWidth / (layer.length + 1);
    for (let j = 0; j < layer.length; j++) {
      positions[layer[j]] = {
        x: spacing * (j + 1),
        y: 70 + i * layerHeight,
      };
    }
  }

  return { positions, height: 70 + layers.length * layerHeight + 50 };
}

export default function TopologyPage() {
  const [data, setData] = useState<GraphData>(DEMO_DATA);
  const [loading, setLoading] = useState(true);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
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

  return (
    <div className="max-w-[1200px] mx-auto px-6 py-10">
      <div className="flex items-center justify-between mb-10">
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

      {loading ? (
        <Card className="flex items-center justify-center py-20">
          <Loader2 size={24} className="animate-spin text-[#FFD700]" />
          <span className="ml-3 text-[#94a3b8]">{t.loading}</span>
        </Card>
      ) : (
        <div className="grid lg:grid-cols-[1fr_320px] gap-6">
          <Card className="p-4 overflow-auto">
            <svg viewBox={`0 0 900 ${height}`} className="w-full" style={{ minHeight: 400 }}>
              {/* Edges */}
              {data.edges.map((edge, i) => {
                const from = positions[edge.source];
                const to = positions[edge.target];
                if (!from || !to) return null;
                const dashArray =
                  edge.type === "optional" ? "8,4" : edge.type === "async" ? "4,4" : "none";
                const isHovered = hoveredEdge === i;
                const edgeLabel = edge.type === "requires"
                  ? (locale === "ja" ? "必須" : "requires")
                  : edge.type === "optional"
                    ? (locale === "ja" ? "任意" : "optional")
                    : (locale === "ja" ? "非同期" : "async");
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
                      y1={from.y + 22}
                      x2={to.x}
                      y2={to.y - 22}
                      stroke="transparent"
                      strokeWidth={16}
                    />
                    <line
                      x1={from.x}
                      y1={from.y + 22}
                      x2={to.x}
                      y2={to.y - 22}
                      stroke={isHovered ? "#FFD700" : "#334155"}
                      strokeWidth={isHovered ? 2.5 : 2}
                      strokeDasharray={dashArray}
                      markerEnd={isHovered ? "url(#arrow-active)" : "url(#arrow)"}
                      className="transition-all duration-200"
                    />
                    {isHovered && (
                      <>
                        <rect
                          x={(from.x + to.x) / 2 - 36}
                          y={(from.y + to.y) / 2 - 10}
                          width={72}
                          height={20}
                          rx={4}
                          fill="#0a0e1a"
                          stroke="#FFD700"
                          strokeWidth={1}
                        />
                        <text
                          x={(from.x + to.x) / 2}
                          y={(from.y + to.y) / 2 + 4}
                          textAnchor="middle"
                          fontSize="10"
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
              <defs>
                <marker id="arrow" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="6" markerHeight="6" orient="auto">
                  <path d="M 0 0 L 10 5 L 0 10 z" fill="#334155" />
                </marker>
                <marker id="arrow-active" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="6" markerHeight="6" orient="auto">
                  <path d="M 0 0 L 10 5 L 0 10 z" fill="#FFD700" />
                </marker>
              </defs>
              {/* Nodes */}
              {data.nodes.map((node) => {
                const pos = positions[node.id];
                if (!pos) return null;
                const risk = DEMO_RISK[node.id];
                const score = risk?.risk_score ?? 0;
                const nodeColor = riskColor(score);
                const nodeBorder = riskBorderColor(score);
                const nodeBg = riskBgColor(score);
                const isSelected = selectedNode === node.id;
                // Calculate node width based on name length
                const nodeWidth = Math.max(140, node.name.length * 8 + 60);
                return (
                  <g
                    key={node.id}
                    className="cursor-pointer"
                    onClick={() => setSelectedNode(isSelected ? null : node.id)}
                  >
                    {/* Glow effect for high risk */}
                    {score >= 70 && (
                      <rect
                        x={pos.x - nodeWidth / 2 - 3}
                        y={pos.y - 23}
                        width={nodeWidth + 6}
                        height={46}
                        rx={11}
                        fill="none"
                        stroke="#ef4444"
                        strokeWidth={1}
                        opacity={0.4}
                        className="animate-pulse"
                      />
                    )}
                    <rect
                      x={pos.x - nodeWidth / 2}
                      y={pos.y - 20}
                      width={nodeWidth}
                      height={40}
                      rx={8}
                      fill={isSelected ? nodeBg : "#111827"}
                      stroke={isSelected ? nodeColor : nodeBorder}
                      strokeWidth={isSelected ? 2 : 1.5}
                    />
                    {/* Risk score circle */}
                    <circle cx={pos.x - nodeWidth / 2 + 18} cy={pos.y} r={12} fill={nodeColor + "20"} stroke={nodeColor} strokeWidth={1.5} />
                    <text x={pos.x - nodeWidth / 2 + 18} y={pos.y + 4} textAnchor="middle" fontSize="8" fill={nodeColor} fontWeight="bold">
                      {score}
                    </text>
                    {/* Type label */}
                    <text x={pos.x - nodeWidth / 2 + 38} y={pos.y - 4} textAnchor="start" fontSize="8" fill="#64748b" fontWeight="500">
                      {TYPE_LABELS[node.type] || "?"}
                    </text>
                    {/* Full node name */}
                    <text x={pos.x - nodeWidth / 2 + 38} y={pos.y + 9} textAnchor="start" fontSize="11" fill="#e2e8f0" fontWeight="500">
                      {node.name}
                    </text>
                  </g>
                );
              })}
            </svg>
          </Card>

          {/* Sidebar: Legend, Risk Legend, Details */}
          <div className="space-y-6">
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
                  <div className="w-8 h-0 border-t-2 border-[#334155]" />
                  <span className="text-xs text-[#64748b]">{t.requires}</span>
                </div>
                <div className="flex items-center gap-3">
                  <div className="w-8 h-0 border-t-2 border-dashed border-[#334155]" />
                  <span className="text-xs text-[#64748b]">{t.optional}</span>
                </div>
                <div className="flex items-center gap-3">
                  <div className="w-8 h-0 border-t-2 border-dotted border-[#334155]" />
                  <span className="text-xs text-[#64748b]">{t.async}</span>
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
                  <button onClick={() => setSelectedNode(null)} className="text-[#64748b] hover:text-white">
                    <X size={14} />
                  </button>
                </div>
                <div className="space-y-4">
                  <div>
                    <p className="text-lg font-bold">{selected.name}</p>
                    <div className="flex items-center gap-2 mt-1">
                      <Badge variant="gold">{selected.type.replace("_", " ")}</Badge>
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
                  {locale === "ja" ? "ノードをクリックして詳細を表示" : "Click a node to view details"}
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
