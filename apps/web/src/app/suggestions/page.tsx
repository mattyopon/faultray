"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Lightbulb,
  TrendingUp,
  ArrowUpRight,
  Shield,
  Database,
  GitBranch,
  Gauge,
  AlertTriangle,
} from "lucide-react";

const suggestions = [
  {
    title: "Add database read replica",
    description: "Implement a read replica for your primary database to handle failover scenarios. This eliminates the single point of failure in your data layer.",
    impact: "+0.5 nines",
    effort: "Medium",
    category: "Redundancy",
    icon: Database,
    priority: "high",
  },
  {
    title: "Implement circuit breaker pattern",
    description: "Add circuit breaker pattern to prevent cascading failures between services. When a downstream service fails, the circuit breaker stops further requests.",
    impact: "+0.3 nines",
    effort: "Low",
    category: "Resilience",
    icon: Shield,
    priority: "high",
  },
  {
    title: "Multi-region DNS failover",
    description: "Configure DNS-based failover to automatically route traffic to a healthy region when the primary region experiences issues.",
    impact: "+0.8 nines",
    effort: "High",
    category: "Availability",
    icon: TrendingUp,
    priority: "high",
  },
  {
    title: "Cache cluster partitioning tolerance",
    description: "Implement graceful degradation when cache clusters experience network partitions. Fallback to direct database queries with rate limiting.",
    impact: "+0.2 nines",
    effort: "Medium",
    category: "Resilience",
    icon: GitBranch,
    priority: "medium",
  },
  {
    title: "Health check endpoint optimization",
    description: "Add deep health checks that verify database connectivity, cache availability, and external service reachability.",
    impact: "+0.1 nines",
    effort: "Low",
    category: "Monitoring",
    icon: Gauge,
    priority: "medium",
  },
  {
    title: "Implement retry with exponential backoff",
    description: "Add retry logic with exponential backoff and jitter for all external service calls to handle transient failures gracefully.",
    impact: "+0.15 nines",
    effort: "Low",
    category: "Resilience",
    icon: AlertTriangle,
    priority: "low",
  },
];

export default function SuggestionsPage() {
  return (
    <div className="max-w-[1200px] mx-auto px-6 py-10">
      <div className="mb-10">
        <h1 className="text-2xl font-bold mb-1">Improvement Suggestions</h1>
        <p className="text-[#94a3b8] text-sm">AI-powered recommendations to improve your infrastructure resilience</p>
      </div>

      {/* Summary */}
      <div className="grid md:grid-cols-3 gap-6 mb-10">
        <Card>
          <div className="flex items-center gap-3 mb-2">
            <div className="w-10 h-10 rounded-lg bg-emerald-500/10 flex items-center justify-center">
              <TrendingUp size={20} className="text-emerald-400" />
            </div>
            <p className="text-xs text-[#64748b] uppercase tracking-wider">Potential Improvement</p>
          </div>
          <p className="text-2xl font-bold font-mono text-emerald-400">+2.05 nines</p>
          <p className="text-xs text-[#64748b] mt-1">If all suggestions implemented</p>
        </Card>
        <Card>
          <div className="flex items-center gap-3 mb-2">
            <div className="w-10 h-10 rounded-lg bg-red-500/10 flex items-center justify-center">
              <AlertTriangle size={20} className="text-red-400" />
            </div>
            <p className="text-xs text-[#64748b] uppercase tracking-wider">High Priority</p>
          </div>
          <p className="text-2xl font-bold font-mono">3</p>
          <p className="text-xs text-[#64748b] mt-1">Immediate attention needed</p>
        </Card>
        <Card>
          <div className="flex items-center gap-3 mb-2">
            <div className="w-10 h-10 rounded-lg bg-[#FFD700]/10 flex items-center justify-center">
              <Lightbulb size={20} className="text-[#FFD700]" />
            </div>
            <p className="text-xs text-[#64748b] uppercase tracking-wider">Total Suggestions</p>
          </div>
          <p className="text-2xl font-bold font-mono">6</p>
          <p className="text-xs text-[#64748b] mt-1">Across 3 categories</p>
        </Card>
      </div>

      {/* Suggestions List */}
      <div className="space-y-4">
        {suggestions.map((s, i) => {
          const Icon = s.icon;
          return (
            <Card key={i} hover className="cursor-pointer">
              <div className="flex items-start gap-5">
                <div className="w-12 h-12 rounded-xl bg-[#FFD700]/[0.06] border border-[#FFD700]/10 flex items-center justify-center shrink-0">
                  <Icon size={22} className="text-[#FFD700]" />
                </div>
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <h3 className="font-bold">{s.title}</h3>
                    <Badge variant={s.priority === "high" ? "red" : s.priority === "medium" ? "yellow" : "default"}>
                      {s.priority}
                    </Badge>
                    <Badge variant="default">{s.category}</Badge>
                  </div>
                  <p className="text-sm text-[#94a3b8] leading-relaxed mb-3">{s.description}</p>
                  <div className="flex items-center gap-4">
                    <div className="flex items-center gap-1.5 text-emerald-400 text-sm font-semibold">
                      <ArrowUpRight size={14} />
                      {s.impact}
                    </div>
                    <span className="text-[#1e293b]">|</span>
                    <span className="text-xs text-[#64748b]">Effort: {s.effort}</span>
                  </div>
                </div>
              </div>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
