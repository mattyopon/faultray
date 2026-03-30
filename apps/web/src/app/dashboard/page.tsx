"use client";

import { useAuth } from "@/components/auth-provider";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type SimulationRun } from "@/lib/api";
import { Onboarding } from "@/components/onboarding";
import {
  Zap,
  TrendingUp,
  Shield,
  AlertTriangle,
  Clock,
  ArrowRight,
  BarChart3,
} from "lucide-react";

function ScoreRing({ score, size = 120 }: { score: number; size?: number }) {
  const radius = 45;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (score / 100) * circumference;
  const color = score >= 90 ? "#10B981" : score >= 70 ? "#FFD700" : "#ef4444";

  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg viewBox="0 0 100 100" className="transform -rotate-90" style={{ width: size, height: size }}>
        <circle cx="50" cy="50" r={radius} stroke="#1e293b" strokeWidth="8" fill="none" />
        <circle
          cx="50" cy="50" r={radius}
          stroke={color} strokeWidth="8" fill="none"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          className="transition-all duration-1000 ease-out"
          style={{ animation: "score-fill 1.5s ease-out" }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-2xl font-extrabold" style={{ color }}>{score.toFixed(1)}</span>
        <span className="text-[10px] text-[#64748b] uppercase tracking-wider">Score</span>
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const { user } = useAuth();
  const [runs, setRuns] = useState<SimulationRun[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getRuns(undefined, 5)
      .then((data) => setRuns(data.runs || []))
      .catch(() => setRuns([]))
      .finally(() => setLoading(false));
  }, []);

  const latestRun = runs[0];
  const latestScore = latestRun?.overall_score ?? 85.2;

  return (
    <div className="max-w-[1200px] mx-auto px-6 py-10">
      <Onboarding />
      {/* Header */}
      <div className="flex items-center justify-between mb-10">
        <div>
          <h1 className="text-2xl font-bold mb-1">Dashboard</h1>
          <p className="text-[#94a3b8] text-sm">
            Welcome back{user?.user_metadata?.full_name ? `, ${user.user_metadata.full_name}` : ""}
          </p>
        </div>
        <Link href="/simulate">
          <Button>
            <Zap size={16} />
            New Simulation
          </Button>
        </Link>
      </div>

      {/* Stats */}
      <div className="grid md:grid-cols-4 gap-6 mb-10">
        <Card className="flex items-center gap-6">
          <ScoreRing score={latestScore} size={100} />
          <div>
            <p className="text-xs text-[#64748b] uppercase tracking-wider mb-1">Resilience Score</p>
            <p className="text-lg font-bold">{latestScore.toFixed(1)} / 100</p>
            <Badge variant={latestScore >= 90 ? "green" : latestScore >= 70 ? "gold" : "red"}>
              {latestScore >= 90 ? "Excellent" : latestScore >= 70 ? "Good" : "Needs Work"}
            </Badge>
          </div>
        </Card>

        <Card>
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 rounded-lg bg-emerald-500/10 flex items-center justify-center">
              <TrendingUp size={20} className="text-emerald-400" />
            </div>
            <p className="text-xs text-[#64748b] uppercase tracking-wider">Availability</p>
          </div>
          <p className="text-2xl font-bold font-mono">99.99%</p>
          <p className="text-xs text-[#64748b] mt-1">4.00 nines</p>
        </Card>

        <Card>
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 rounded-lg bg-[#FFD700]/10 flex items-center justify-center">
              <Shield size={20} className="text-[#FFD700]" />
            </div>
            <p className="text-xs text-[#64748b] uppercase tracking-wider">Scenarios</p>
          </div>
          <p className="text-2xl font-bold font-mono">{latestRun?.total_scenarios ?? 152}</p>
          <div className="flex items-center gap-2 mt-1">
            <span className="text-xs text-emerald-400">{latestRun?.scenarios_passed ?? 147} passed</span>
            <span className="text-xs text-[#64748b]">/</span>
            <span className="text-xs text-red-400">{latestRun?.scenarios_failed ?? 5} failed</span>
          </div>
        </Card>

        <Card>
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 rounded-lg bg-red-500/10 flex items-center justify-center">
              <AlertTriangle size={20} className="text-red-400" />
            </div>
            <p className="text-xs text-[#64748b] uppercase tracking-wider">Critical Issues</p>
          </div>
          <p className="text-2xl font-bold font-mono">3</p>
          <p className="text-xs text-red-400 mt-1">Requires attention</p>
        </Card>
      </div>

      {/* 3-Layer Bar Chart */}
      <Card className="mb-10">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-lg font-bold flex items-center gap-2">
            <BarChart3 size={20} className="text-[#FFD700]" />
            3-Layer Availability Model
          </h2>
        </div>
        <div className="space-y-4">
          {[
            { label: "Software", value: 4.0, max: 7, color: "bg-emerald-400" },
            { label: "Hardware", value: 5.91, max: 7, color: "bg-[#FFD700]" },
            { label: "Theoretical", value: 6.65, max: 7, color: "bg-blue-400" },
          ].map((layer) => (
            <div key={layer.label} className="grid grid-cols-[80px_1fr_60px] items-center gap-4">
              <span className="text-sm text-[#64748b]">{layer.label}</span>
              <div className="h-3 bg-white/5 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full ${layer.color} transition-all duration-1000`}
                  style={{ width: `${(layer.value / layer.max) * 100}%` }}
                />
              </div>
              <span className="text-sm font-mono font-semibold text-right">{layer.value.toFixed(2)}</span>
            </div>
          ))}
        </div>
      </Card>

      {/* Recent Runs */}
      <Card>
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-lg font-bold flex items-center gap-2">
            <Clock size={20} className="text-[#FFD700]" />
            Recent Simulations
          </h2>
          <Link href="/results" className="text-sm text-[#FFD700] hover:underline flex items-center gap-1">
            View all <ArrowRight size={14} />
          </Link>
        </div>
        {loading ? (
          <div className="text-center py-8 text-[#64748b]">Loading...</div>
        ) : runs.length === 0 ? (
          <div className="text-center py-12">
            <p className="text-[#64748b] mb-4">No simulations yet. Run your first simulation to see results here.</p>
            <Link href="/simulate">
              <Button size="sm"><Zap size={14} /> Run Simulation</Button>
            </Link>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[#1e293b]">
                  <th className="text-left py-3 px-2 text-[#64748b] font-medium">Date</th>
                  <th className="text-left py-3 px-2 text-[#64748b] font-medium">Score</th>
                  <th className="text-left py-3 px-2 text-[#64748b] font-medium">Availability</th>
                  <th className="text-left py-3 px-2 text-[#64748b] font-medium">Scenarios</th>
                  <th className="text-right py-3 px-2 text-[#64748b] font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => (
                  <tr key={run.id} className="border-b border-[#1e293b]/50 hover:bg-white/[0.02]">
                    <td className="py-3 px-2 text-[#94a3b8]">
                      {new Date(run.created_at).toLocaleDateString()}
                    </td>
                    <td className="py-3 px-2 font-mono font-semibold">
                      {run.overall_score.toFixed(1)}
                    </td>
                    <td className="py-3 px-2 text-[#94a3b8]">{run.availability_estimate}</td>
                    <td className="py-3 px-2 text-[#94a3b8]">
                      <span className="text-emerald-400">{run.scenarios_passed}</span>
                      {" / "}
                      <span>{run.total_scenarios}</span>
                    </td>
                    <td className="py-3 px-2 text-right">
                      <Badge variant={run.scenarios_failed === 0 ? "green" : "yellow"}>
                        {run.scenarios_failed === 0 ? "All Passed" : `${run.scenarios_failed} Failed`}
                      </Badge>
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
