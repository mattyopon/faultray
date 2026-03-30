"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import { Network, ArrowRight, Loader2, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";

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

const TYPE_COLORS: Record<string, string> = {
  load_balancer: "#3b82f6",
  app_server: "#10b981",
  database: "#f59e0b",
  cache: "#ef4444",
  queue: "#8b5cf6",
  dns: "#06b6d4",
  storage: "#64748b",
  custom: "#ec4899",
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

// Layout nodes in layers
function layoutNodes(nodes: GraphNode[], edges: GraphEdge[]) {
  const layers: string[][] = [];
  const placed = new Set<string>();
  const targets = new Set(edges.map((e) => e.target));
  const sources = new Set(edges.map((e) => e.source));

  // Roots: sources that are not targets
  const roots = nodes.filter((n) => sources.has(n.id) && !targets.has(n.id));
  if (roots.length === 0) roots.push(nodes[0]);

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

  // Place unconnected nodes
  for (const n of nodes) {
    if (!placed.has(n.id)) {
      if (!layers[0]) layers[0] = [];
      layers[0].push(n.id);
    }
  }

  const positions: Record<string, { x: number; y: number }> = {};
  const svgWidth = 900;
  const layerHeight = 120;

  for (let i = 0; i < layers.length; i++) {
    const layer = layers[i];
    const spacing = svgWidth / (layer.length + 1);
    for (let j = 0; j < layer.length; j++) {
      positions[layer[j]] = {
        x: spacing * (j + 1),
        y: 60 + i * layerHeight,
      };
    }
  }

  return { positions, height: 60 + layers.length * layerHeight + 40 };
}

export default function TopologyPage() {
  const [data, setData] = useState<GraphData>(DEMO_DATA);
  const [loading, setLoading] = useState(true);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);

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

  return (
    <div className="max-w-[1200px] mx-auto px-6 py-10">
      <div className="flex items-center justify-between mb-10">
        <div>
          <h1 className="text-2xl font-bold mb-1 flex items-center gap-3">
            <Network size={24} className="text-[#FFD700]" />
            Topology Graph
          </h1>
          <p className="text-[#94a3b8] text-sm">
            Interactive infrastructure dependency graph
          </p>
        </div>
        <Button variant="secondary" size="sm" onClick={loadData} disabled={loading}>
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          Refresh
        </Button>
      </div>

      {loading ? (
        <Card className="flex items-center justify-center py-20">
          <Loader2 size={24} className="animate-spin text-[#FFD700]" />
          <span className="ml-3 text-[#94a3b8]">Loading topology...</span>
        </Card>
      ) : (
        <div className="grid lg:grid-cols-[1fr_300px] gap-6">
          <Card className="p-4 overflow-auto">
            <svg viewBox={`0 0 900 ${height}`} className="w-full" style={{ minHeight: 400 }}>
              {/* Edges */}
              {data.edges.map((edge, i) => {
                const from = positions[edge.source];
                const to = positions[edge.target];
                if (!from || !to) return null;
                const dashArray =
                  edge.type === "optional" ? "8,4" : edge.type === "async" ? "4,4" : "none";
                return (
                  <g key={i}>
                    <line
                      x1={from.x}
                      y1={from.y + 20}
                      x2={to.x}
                      y2={to.y - 20}
                      stroke="#334155"
                      strokeWidth={2}
                      strokeDasharray={dashArray}
                      markerEnd="url(#arrow)"
                    />
                  </g>
                );
              })}
              <defs>
                <marker id="arrow" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="6" markerHeight="6" orient="auto">
                  <path d="M 0 0 L 10 5 L 0 10 z" fill="#334155" />
                </marker>
              </defs>
              {/* Nodes */}
              {data.nodes.map((node) => {
                const pos = positions[node.id];
                if (!pos) return null;
                const color = TYPE_COLORS[node.type] || "#64748b";
                const isSelected = selectedNode === node.id;
                return (
                  <g
                    key={node.id}
                    className="cursor-pointer"
                    onClick={() => setSelectedNode(isSelected ? null : node.id)}
                  >
                    <rect
                      x={pos.x - 60}
                      y={pos.y - 20}
                      width={120}
                      height={40}
                      rx={8}
                      fill={isSelected ? color + "30" : "#111827"}
                      stroke={isSelected ? color : "#1e293b"}
                      strokeWidth={isSelected ? 2 : 1}
                    />
                    <circle cx={pos.x - 45} cy={pos.y} r={10} fill={color + "20"} stroke={color} strokeWidth={1} />
                    <text x={pos.x - 45} y={pos.y + 4} textAnchor="middle" fontSize="7" fill={color} fontWeight="bold">
                      {TYPE_LABELS[node.type] || "?"}
                    </text>
                    <text x={pos.x + 5} y={pos.y + 4} textAnchor="middle" fontSize="11" fill="#e2e8f0" fontWeight="500">
                      {node.name.length > 14 ? node.name.slice(0, 13) + "..." : node.name}
                    </text>
                  </g>
                );
              })}
            </svg>
          </Card>

          {/* Legend & Details */}
          <div className="space-y-6">
            <Card>
              <h3 className="text-sm font-semibold text-[#94a3b8] uppercase tracking-wider mb-4">Legend</h3>
              <div className="space-y-2">
                {Object.entries(TYPE_COLORS).map(([type, color]) => (
                  <div key={type} className="flex items-center gap-3">
                    <div className="w-3 h-3 rounded-full" style={{ backgroundColor: color }} />
                    <span className="text-sm text-[#e2e8f0] capitalize">{type.replace("_", " ")}</span>
                  </div>
                ))}
              </div>
              <div className="mt-4 pt-4 border-t border-[#1e293b] space-y-2">
                <div className="flex items-center gap-3">
                  <div className="w-8 h-0 border-t-2 border-[#334155]" />
                  <span className="text-xs text-[#64748b]">requires</span>
                </div>
                <div className="flex items-center gap-3">
                  <div className="w-8 h-0 border-t-2 border-dashed border-[#334155]" />
                  <span className="text-xs text-[#64748b]">optional</span>
                </div>
                <div className="flex items-center gap-3">
                  <div className="w-8 h-0 border-t-2 border-dotted border-[#334155]" />
                  <span className="text-xs text-[#64748b]">async</span>
                </div>
              </div>
            </Card>

            {selected && (
              <Card>
                <h3 className="text-sm font-semibold text-[#94a3b8] uppercase tracking-wider mb-4">
                  Component Details
                </h3>
                <div className="space-y-3">
                  <div>
                    <p className="text-lg font-bold">{selected.name}</p>
                    <Badge variant="gold">{selected.type.replace("_", " ")}</Badge>
                  </div>
                  {selected.replicas && (
                    <div className="flex justify-between text-sm">
                      <span className="text-[#64748b]">Replicas</span>
                      <span className="font-mono">{selected.replicas}</span>
                    </div>
                  )}
                  <div>
                    <p className="text-xs text-[#64748b] mb-2">Dependencies</p>
                    {data.edges
                      .filter((e) => e.source === selected.id)
                      .map((e) => (
                        <div key={e.target} className="flex items-center gap-2 text-sm text-[#94a3b8]">
                          <ArrowRight size={12} />
                          {nodeMap[e.target]?.name || e.target}
                          <Badge variant={e.type === "requires" ? "red" : "default"}>
                            {e.type || "requires"}
                          </Badge>
                        </div>
                      ))}
                    {data.edges.filter((e) => e.source === selected.id).length === 0 && (
                      <p className="text-xs text-[#64748b]">No outgoing dependencies</p>
                    )}
                  </div>
                </div>
              </Card>
            )}

            <Card>
              <div className="flex justify-between text-sm">
                <span className="text-[#64748b]">Components</span>
                <span className="font-mono font-bold">{data.nodes.length}</span>
              </div>
              <div className="flex justify-between text-sm mt-2">
                <span className="text-[#64748b]">Dependencies</span>
                <span className="font-mono font-bold">{data.edges.length}</span>
              </div>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}
