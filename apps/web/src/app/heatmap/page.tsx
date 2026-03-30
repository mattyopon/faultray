"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useEffect, useState } from "react";
import { api, type HeatmapData, type HeatmapComponent } from "@/lib/api";
import { Flame, Loader2 } from "lucide-react";

const DEMO_DATA: HeatmapData = {
  components: [
    { id: "cdn", name: "CDN / Edge", type: "load_balancer", risk_score: 12, category: "Network" },
    { id: "gateway", name: "API Gateway", type: "load_balancer", risk_score: 25, category: "Network" },
    { id: "auth", name: "Auth Service", type: "app_server", risk_score: 45, category: "Application" },
    { id: "api", name: "API Server", type: "app_server", risk_score: 38, category: "Application" },
    { id: "worker", name: "Background Worker", type: "app_server", risk_score: 30, category: "Application" },
    { id: "db_primary", name: "PostgreSQL Primary", type: "database", risk_score: 72, category: "Data" },
    { id: "db_replica", name: "PostgreSQL Replica", type: "database", risk_score: 35, category: "Data" },
    { id: "cache", name: "Redis Cache", type: "cache", risk_score: 55, category: "Data" },
    { id: "queue", name: "Message Queue", type: "queue", risk_score: 40, category: "Messaging" },
    { id: "storage", name: "Object Storage", type: "storage", risk_score: 15, category: "Data" },
    { id: "monitor", name: "Monitoring", type: "app_server", risk_score: 20, category: "Ops" },
    { id: "dns", name: "DNS", type: "dns", risk_score: 18, category: "Network" },
  ],
  categories: ["Network", "Application", "Data", "Messaging", "Ops"],
  max_risk: 100,
};

function riskColor(score: number): string {
  if (score >= 70) return "#ef4444";
  if (score >= 50) return "#f59e0b";
  if (score >= 30) return "#eab308";
  return "#10b981";
}

function riskBg(score: number): string {
  if (score >= 70) return "bg-red-500/10 border-red-500/20";
  if (score >= 50) return "bg-yellow-500/10 border-yellow-500/20";
  if (score >= 30) return "bg-yellow-500/5 border-yellow-500/10";
  return "bg-emerald-500/5 border-emerald-500/10";
}

function riskLabel(score: number): string {
  if (score >= 70) return "High Risk";
  if (score >= 50) return "Medium Risk";
  if (score >= 30) return "Low-Medium";
  return "Low Risk";
}

export default function HeatmapPage() {
  const [data, setData] = useState<HeatmapData>(DEMO_DATA);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<HeatmapComponent | null>(null);

  useEffect(() => {
    api
      .getHeatmap()
      .then((result) => setData(result))
      .catch(() => setData(DEMO_DATA))
      .finally(() => setLoading(false));
  }, []);

  const grouped = data.categories.map((cat) => ({
    category: cat,
    components: data.components.filter((c) => c.category === cat).sort((a, b) => b.risk_score - a.risk_score),
  }));

  const sorted = [...data.components].sort((a, b) => b.risk_score - a.risk_score);

  return (
    <div className="max-w-[1200px] mx-auto px-6 py-10">
      <div className="mb-10">
        <h1 className="text-2xl font-bold mb-1 flex items-center gap-3">
          <Flame size={24} className="text-[#FFD700]" />
          Risk Heatmap
        </h1>
        <p className="text-[#94a3b8] text-sm">Component-level risk visualization</p>
      </div>

      {loading ? (
        <Card className="flex items-center justify-center py-20">
          <Loader2 size={24} className="animate-spin text-[#FFD700]" />
          <span className="ml-3 text-[#94a3b8]">Loading heatmap...</span>
        </Card>
      ) : (
        <>
          {/* Color Legend */}
          <Card className="mb-6">
            <div className="flex items-center gap-6 flex-wrap">
              <span className="text-xs text-[#64748b] uppercase tracking-wider">Risk Level:</span>
              <div className="flex items-center gap-2">
                <div className="w-4 h-4 rounded" style={{ backgroundColor: "#10b981" }} />
                <span className="text-xs text-[#94a3b8]">Low (0-29)</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-4 h-4 rounded" style={{ backgroundColor: "#eab308" }} />
                <span className="text-xs text-[#94a3b8]">Low-Medium (30-49)</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-4 h-4 rounded" style={{ backgroundColor: "#f59e0b" }} />
                <span className="text-xs text-[#94a3b8]">Medium (50-69)</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-4 h-4 rounded" style={{ backgroundColor: "#ef4444" }} />
                <span className="text-xs text-[#94a3b8]">High (70-100)</span>
              </div>
            </div>
          </Card>

          {/* Heatmap Grid */}
          <div className="grid lg:grid-cols-[1fr_320px] gap-6">
            <div className="space-y-6">
              {grouped.map((group) => (
                <Card key={group.category}>
                  <h3 className="text-sm font-semibold text-[#94a3b8] uppercase tracking-wider mb-4">
                    {group.category}
                  </h3>
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                    {group.components.map((comp) => (
                      <button
                        key={comp.id}
                        onClick={() => setSelected(selected?.id === comp.id ? null : comp)}
                        className={`p-4 rounded-xl border text-left transition-all ${riskBg(comp.risk_score)} ${
                          selected?.id === comp.id ? "ring-2 ring-[#FFD700]/50" : ""
                        } hover:scale-[1.02]`}
                      >
                        <div className="flex items-center justify-between mb-2">
                          <span
                            className="text-2xl font-bold font-mono"
                            style={{ color: riskColor(comp.risk_score) }}
                          >
                            {comp.risk_score}
                          </span>
                          <div
                            className="w-3 h-3 rounded-full"
                            style={{ backgroundColor: riskColor(comp.risk_score) }}
                          />
                        </div>
                        <p className="text-sm font-medium text-[#e2e8f0] truncate">{comp.name}</p>
                        <p className="text-xs text-[#64748b]">{comp.type.replace("_", " ")}</p>
                      </button>
                    ))}
                  </div>
                </Card>
              ))}
            </div>

            {/* Detail Panel */}
            <div className="space-y-6">
              {selected ? (
                <Card>
                  <h3 className="text-sm font-semibold text-[#94a3b8] uppercase tracking-wider mb-4">
                    Component Detail
                  </h3>
                  <div className="text-center mb-4">
                    <span
                      className="text-5xl font-extrabold font-mono"
                      style={{ color: riskColor(selected.risk_score) }}
                    >
                      {selected.risk_score}
                    </span>
                    <p className="text-xs text-[#64748b] mt-1">Risk Score</p>
                  </div>
                  <div className="space-y-3">
                    <div className="flex justify-between text-sm">
                      <span className="text-[#64748b]">Name</span>
                      <span className="font-medium">{selected.name}</span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-[#64748b]">Type</span>
                      <span className="font-mono">{selected.type}</span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-[#64748b]">Category</span>
                      <span>{selected.category}</span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-[#64748b]">Risk Level</span>
                      <Badge
                        variant={
                          selected.risk_score >= 70
                            ? "red"
                            : selected.risk_score >= 50
                              ? "yellow"
                              : "green"
                        }
                      >
                        {riskLabel(selected.risk_score)}
                      </Badge>
                    </div>
                  </div>
                </Card>
              ) : (
                <Card>
                  <p className="text-sm text-[#64748b] text-center py-4">
                    Click a component to view details
                  </p>
                </Card>
              )}

              <Card>
                <h3 className="text-sm font-semibold text-[#94a3b8] uppercase tracking-wider mb-4">
                  Top Risks
                </h3>
                <div className="space-y-2">
                  {sorted.slice(0, 5).map((comp) => (
                    <div
                      key={comp.id}
                      className="flex items-center justify-between p-2 rounded-lg bg-white/[0.02]"
                    >
                      <span className="text-sm">{comp.name}</span>
                      <span className="font-mono font-bold text-sm" style={{ color: riskColor(comp.risk_score) }}>
                        {comp.risk_score}
                      </span>
                    </div>
                  ))}
                </div>
              </Card>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
