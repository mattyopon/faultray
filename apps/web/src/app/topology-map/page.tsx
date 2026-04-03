"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useEffect, useState, useRef, useCallback } from "react";
import { Network, Loader2, ZoomIn, ZoomOut, RefreshCw, Maximize2 } from "lucide-react";
import { useLocale } from "@/lib/useLocale";
import { appDict } from "@/i18n/app-dict";

interface MapNode {
  id: string;
  name: string;
  type: string;
  risk_score: number;
  x: number;
  y: number;
  layer: number;
}

interface MapEdge {
  source: string;
  target: string;
  type: "sync" | "async" | "depends";
}

interface TopologyMapData {
  nodes: MapNode[];
  edges: MapEdge[];
}

const DEMO_DATA: TopologyMapData = {
  nodes: [
    { id: "user", name: "Users", type: "client", risk_score: 0, x: 400, y: 40, layer: 0 },
    { id: "cdn", name: "CDN / Edge", type: "cdn", risk_score: 12, x: 400, y: 130, layer: 1 },
    { id: "gateway", name: "API Gateway", type: "gateway", risk_score: 25, x: 400, y: 230, layer: 2 },
    { id: "auth", name: "Auth Service", type: "app", risk_score: 45, x: 180, y: 340, layer: 3 },
    { id: "api", name: "API Server", type: "app", risk_score: 38, x: 400, y: 340, layer: 3 },
    { id: "worker", name: "Background Worker", type: "worker", risk_score: 30, x: 620, y: 340, layer: 3 },
    { id: "db_primary", name: "PostgreSQL Primary", type: "database", risk_score: 72, x: 250, y: 460, layer: 4 },
    { id: "redis", name: "Redis Cache", type: "cache", risk_score: 55, x: 400, y: 460, layer: 4 },
    { id: "queue", name: "Message Queue", type: "queue", risk_score: 40, x: 550, y: 460, layer: 4 },
    { id: "storage", name: "Object Storage", type: "storage", risk_score: 15, x: 700, y: 460, layer: 4 },
    { id: "db_replica", name: "PostgreSQL Replica", type: "database", risk_score: 35, x: 100, y: 460, layer: 4 },
  ],
  edges: [
    { source: "user", target: "cdn", type: "sync" },
    { source: "cdn", target: "gateway", type: "sync" },
    { source: "gateway", target: "auth", type: "sync" },
    { source: "gateway", target: "api", type: "sync" },
    { source: "api", target: "worker", type: "async" },
    { source: "api", target: "db_primary", type: "sync" },
    { source: "api", target: "redis", type: "sync" },
    { source: "api", target: "queue", type: "async" },
    { source: "worker", target: "queue", type: "depends" },
    { source: "worker", target: "storage", type: "sync" },
    { source: "db_primary", target: "db_replica", type: "async" },
    { source: "auth", target: "redis", type: "sync" },
  ],
};

function nodeColor(risk: number): string {
  if (risk >= 70) return "#ef4444";
  if (risk >= 50) return "#f59e0b";
  if (risk >= 30) return "#eab308";
  if (risk === 0) return "#64748b";
  return "#10b981";
}

function edgeColor(type: string): string {
  if (type === "sync") return "#3b82f6";
  if (type === "async") return "#8b5cf6";
  return "#64748b";
}

function typeIcon(type: string): string {
  const icons: Record<string, string> = {
    client: "👤", cdn: "🌐", gateway: "🔀", app: "⚙️",
    worker: "⚙️", database: "🗄️", cache: "⚡", queue: "📨",
    storage: "💾", monitoring: "📊", dns: "🔍",
  };
  return icons[type] ?? "□";
}

export default function TopologyMapPage() {
  const [data, setData] = useState<TopologyMapData>(DEMO_DATA);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<MapNode | null>(null);
  const [zoom, setZoom] = useState(1);
  const svgRef = useRef<SVGSVGElement>(null);
  const locale = useLocale();
  const t = appDict.topologyMap[locale] ?? appDict.topologyMap.en;

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/proxy?path=/api/v1/topology-map", { signal: controller.signal })
      .then((r) => r.json())
      .then((d) => setData(d))
      .catch(() => setData(DEMO_DATA))
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, []);

  const getNodeById = useCallback((id: string) => data.nodes.find((n) => n.id === id), [data.nodes]);

  const viewBox = `0 0 800 560`;

  return (
    <div className="max-w-[1200px] mx-auto px-6 py-10">
      <div className="mb-8">
        <h1 className="text-2xl font-bold mb-1 flex items-center gap-3">
          <Network size={24} className="text-[#FFD700]" />
          {t.title}
        </h1>
        <p className="text-[#94a3b8] text-sm">{t.subtitle}</p>
      </div>

      {loading ? (
        <Card className="flex items-center justify-center py-20">
          <Loader2 size={24} className="animate-spin text-[#FFD700]" />
          <span className="ml-3 text-[#94a3b8]">{t.loading}</span>
        </Card>
      ) : (
        <div className="grid lg:grid-cols-[1fr_280px] gap-6">
          {/* SVG Map */}
          <Card className="p-4">
            {/* Toolbar */}
            <div className="flex items-center gap-2 mb-4">
              <span className="text-xs text-[#64748b] uppercase tracking-wider flex-1">{t.interactiveMap}</span>
              <Button variant="ghost" size="sm" onClick={() => setZoom((z) => Math.min(z + 0.2, 2))}>
                <ZoomIn size={14} />
              </Button>
              <Button variant="ghost" size="sm" onClick={() => setZoom((z) => Math.max(z - 0.2, 0.4))}>
                <ZoomOut size={14} />
              </Button>
              <Button variant="ghost" size="sm" onClick={() => { setZoom(1); setSelected(null); }}>
                <RefreshCw size={14} />
              </Button>
              <Button variant="ghost" size="sm" onClick={() => { if (svgRef.current) { (svgRef.current as SVGSVGElement & { requestFullscreen?: () => void }).requestFullscreen?.(); } }}>
                <Maximize2 size={14} />
              </Button>
            </div>

            {/* SVG Canvas */}
            <div className="bg-[#0a0e1a] rounded-xl overflow-hidden" style={{ height: 480 }}>
              <svg
                ref={svgRef}
                viewBox={viewBox}
                className="w-full h-full"
                style={{ transform: `scale(${zoom})`, transformOrigin: "center center", transition: "transform 0.2s" }}
              >
                {/* Grid lines */}
                <defs>
                  <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
                    <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#1e293b" strokeWidth="0.5" />
                  </pattern>
                </defs>
                <rect width="800" height="560" fill="url(#grid)" />

                {/* Layer labels */}
                {[
                  { y: 20, label: "Internet" },
                  { y: 110, label: "Edge" },
                  { y: 210, label: "Gateway" },
                  { y: 320, label: "Application" },
                  { y: 440, label: "Data" },
                ].map((layer) => (
                  <text key={layer.y} x="10" y={layer.y + 15} fill="#1e293b" fontSize="11" fontFamily="monospace" fontWeight="bold">
                    {layer.label}
                  </text>
                ))}

                {/* Edges */}
                {data.edges.map((edge) => {
                  const src = getNodeById(edge.source);
                  const tgt = getNodeById(edge.target);
                  if (!src || !tgt) return null;
                  const color = edgeColor(edge.type);
                  return (
                    <g key={`${edge.source}-${edge.target}`}>
                      <line
                        x1={src.x} y1={src.y + 20}
                        x2={tgt.x} y2={tgt.y - 20}
                        stroke={color}
                        strokeWidth={edge.type === "sync" ? 1.5 : 1}
                        strokeDasharray={edge.type === "async" ? "4 3" : edge.type === "depends" ? "2 2" : undefined}
                        opacity={0.6}
                      />
                    </g>
                  );
                })}

                {/* Nodes */}
                {data.nodes.map((node) => {
                  const color = nodeColor(node.risk_score);
                  const isSelected = selected?.id === node.id;
                  return (
                    <g
                      key={node.id}
                      transform={`translate(${node.x}, ${node.y})`}
                      style={{ cursor: "pointer" }}
                      onClick={() => setSelected(isSelected ? null : node)}
                    >
                      {isSelected && (
                        <circle r="28" fill={color} opacity="0.15" />
                      )}
                      <circle
                        r="22"
                        fill="#111827"
                        stroke={color}
                        strokeWidth={isSelected ? 3 : 1.5}
                        opacity={isSelected ? 1 : 0.9}
                      />
                      <text textAnchor="middle" dominantBaseline="middle" fontSize="14">
                        {typeIcon(node.type)}
                      </text>
                      <text
                        y="33"
                        textAnchor="middle"
                        fill="#94a3b8"
                        fontSize="9"
                        fontFamily="sans-serif"
                      >
                        {node.name.length > 16 ? node.name.slice(0, 14) + "…" : node.name}
                      </text>
                      {node.risk_score > 0 && (
                        <text
                          y="-26"
                          textAnchor="middle"
                          fill={color}
                          fontSize="9"
                          fontFamily="monospace"
                          fontWeight="bold"
                        >
                          {node.risk_score}
                        </text>
                      )}
                    </g>
                  );
                })}
              </svg>
            </div>

            {/* Legend */}
            <div className="flex flex-wrap items-center gap-4 mt-3">
              <span className="text-xs text-[#64748b]">{t.edges}:</span>
              {[
                { color: "#3b82f6", label: "sync", dash: undefined },
                { color: "#8b5cf6", label: "async", dash: "4 3" },
                { color: "#64748b", label: "depends", dash: "2 2" },
              ].map((e) => (
                <div key={e.label} className="flex items-center gap-1.5">
                  <svg width="24" height="8"><line x1="0" y1="4" x2="24" y2="4" stroke={e.color} strokeWidth="1.5" strokeDasharray={e.dash} /></svg>
                  <span className="text-xs text-[#94a3b8]">{e.label}</span>
                </div>
              ))}
              <span className="text-xs text-[#64748b] ml-2">{t.nodeRisk}:</span>
              {[
                { color: "#10b981", label: "Low" },
                { color: "#eab308", label: "Med" },
                { color: "#f59e0b", label: "High" },
                { color: "#ef4444", label: "Critical" },
              ].map((r) => (
                <div key={r.label} className="flex items-center gap-1">
                  <div className="w-3 h-3 rounded-full" style={{ backgroundColor: r.color }} />
                  <span className="text-xs text-[#94a3b8]">{r.label}</span>
                </div>
              ))}
            </div>
          </Card>

          {/* Side Panel */}
          <div className="space-y-4">
            {selected ? (
              <Card>
                <h3 className="text-sm font-semibold text-[#94a3b8] uppercase tracking-wider mb-3">{t.nodeDetail}</h3>
                <div className="text-center mb-4">
                  <span className="text-4xl">{typeIcon(selected.type)}</span>
                  <p className="font-bold mt-2">{selected.name}</p>
                  <p className="text-xs text-[#64748b]">{selected.type}</p>
                  {selected.risk_score > 0 && (
                    <div className="mt-2">
                      <span className="text-3xl font-extrabold font-mono" style={{ color: nodeColor(selected.risk_score) }}>
                        {selected.risk_score}
                      </span>
                      <p className="text-xs text-[#64748b]">{t.riskScore}</p>
                    </div>
                  )}
                  {selected.risk_score > 0 && (
                    <Badge
                      variant={selected.risk_score >= 70 ? "red" : selected.risk_score >= 50 ? "yellow" : "green"}
                      className="mt-1"
                    >
                      {selected.risk_score >= 70 ? "HIGH RISK" : selected.risk_score >= 50 ? "MEDIUM RISK" : "LOW RISK"}
                    </Badge>
                  )}
                </div>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-[#64748b]">{t.layer}</span>
                    <span>{selected.layer}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-[#64748b]">{t.connections}</span>
                    <span>{data.edges.filter((e) => e.source === selected.id || e.target === selected.id).length}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-[#64748b]">{t.upstreamDeps}</span>
                    <span>{data.edges.filter((e) => e.target === selected.id).length}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-[#64748b]">{t.downstreamDeps}</span>
                    <span>{data.edges.filter((e) => e.source === selected.id).length}</span>
                  </div>
                </div>
              </Card>
            ) : (
              <Card>
                <p className="text-sm text-[#64748b] text-center py-4">{t.clickNode}</p>
              </Card>
            )}

            {/* Top Risk Nodes */}
            <Card>
              <h3 className="text-sm font-semibold text-[#94a3b8] uppercase tracking-wider mb-3">{t.topRisk}</h3>
              <div className="space-y-2">
                {[...data.nodes]
                  .filter((n) => n.risk_score > 0)
                  .sort((a, b) => b.risk_score - a.risk_score)
                  .slice(0, 5)
                  .map((node) => (
                    <button
                      key={node.id}
                      className="w-full flex items-center justify-between p-2 rounded-lg bg-white/[0.02] hover:bg-white/[0.04] text-left"
                      onClick={() => setSelected(node)}
                    >
                      <span className="text-sm">{node.name}</span>
                      <span className="font-mono font-bold text-sm" style={{ color: nodeColor(node.risk_score) }}>
                        {node.risk_score}
                      </span>
                    </button>
                  ))}
              </div>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}
