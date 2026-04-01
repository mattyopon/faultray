"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Users, TrendingUp, TrendingDown, Minus } from "lucide-react";
import { useLocale } from "@/lib/useLocale";
import { appDict } from "@/i18n/app-dict";

const DEMO_TEAMS = [
  {
    rank: 1,
    name: "Platform SRE",
    resilienceScore: 91,
    trend: "up" as const,
    dora: { deployFreq: "8.2/day", leadTime: "1.2h", changeFailRate: "0.8%", mttr: "4.5 min" },
    actionItems: { open: 2, closed: 18 },
    members: [
      { name: "Alice K.", role: "Lead SRE", avatar: "AK" },
      { name: "Bob T.", role: "Senior SRE", avatar: "BT" },
      { name: "Carol L.", role: "SRE", avatar: "CL" },
      { name: "David P.", role: "SRE", avatar: "DP" },
    ],
  },
  {
    rank: 2,
    name: "Backend Engineering",
    resilienceScore: 78,
    trend: "up" as const,
    dora: { deployFreq: "3.1/day", leadTime: "4.8h", changeFailRate: "2.1%", mttr: "12 min" },
    actionItems: { open: 5, closed: 11 },
    members: [
      { name: "Eve R.", role: "Tech Lead", avatar: "ER" },
      { name: "Frank B.", role: "Senior Dev", avatar: "FB" },
      { name: "Grace M.", role: "Developer", avatar: "GM" },
      { name: "Hank W.", role: "Developer", avatar: "HW" },
      { name: "Iris N.", role: "Junior Dev", avatar: "IN" },
    ],
  },
  {
    rank: 3,
    name: "Infrastructure",
    resilienceScore: 65,
    trend: "down" as const,
    dora: { deployFreq: "1.4/week", leadTime: "2.1 days", changeFailRate: "5.2%", mttr: "28 min" },
    actionItems: { open: 8, closed: 6 },
    members: [
      { name: "Jack S.", role: "Infra Lead", avatar: "JS" },
      { name: "Kate V.", role: "DevOps", avatar: "KV" },
      { name: "Liam O.", role: "DevOps", avatar: "LO" },
      { name: "Mia T.", role: "SecOps", avatar: "MT" },
    ],
  },
];

const DORA_LEVELS: Record<string, { elite: string; high: string; medium: string; low: string; color: (val: string) => string }> = {
  deployFreq: {
    elite: "Elite: ≥1/day",
    high: "High: 1/week–1/day",
    medium: "Medium: 1/month–1/week",
    low: "Low: <1/month",
    color: (v) => {
      if (v.includes("day")) return "#10b981";
      if (v.includes("week")) return "#f59e0b";
      return "#ef4444";
    },
  },
  leadTime: {
    elite: "Elite: <1h",
    high: "High: 1h–1 day",
    medium: "Medium: 1–7 days",
    low: "Low: >1 month",
    color: (v) => {
      if (v.includes("min") || (v.includes("h") && !v.includes("day"))) return "#10b981";
      if (v.includes("day") && parseFloat(v) < 7) return "#f59e0b";
      return "#ef4444";
    },
  },
  changeFailRate: {
    elite: "Elite: 0–5%",
    high: "High: 5–10%",
    medium: "Medium: 10–15%",
    low: "Low: >15%",
    color: (v) => {
      const n = parseFloat(v);
      if (n <= 2) return "#10b981";
      if (n <= 5) return "#f59e0b";
      return "#ef4444";
    },
  },
  mttr: {
    elite: "Elite: <1h",
    high: "High: 1h–1 day",
    medium: "Medium: 1–7 days",
    low: "Low: >1 week",
    color: (v) => {
      if (v.includes("min") && parseInt(v) < 30) return "#10b981";
      if (v.includes("min")) return "#f59e0b";
      return "#ef4444";
    },
  },
};

function ScoreBar({ score }: { score: number }) {
  const color = score >= 85 ? "#10b981" : score >= 70 ? "#f59e0b" : "#ef4444";
  return (
    <div className="flex items-center gap-3">
      <div className="flex-1 h-2 bg-[#1e293b] rounded-full overflow-hidden">
        <div className="h-full rounded-full transition-all" style={{ width: `${score}%`, backgroundColor: color }} />
      </div>
      <span className="text-sm font-bold font-mono" style={{ color }}>{score}</span>
    </div>
  );
}

export default function TeamsPage() {
  const locale = useLocale();
  const t = appDict.teams[locale] ?? appDict.teams.en;

  return (
    <div className="max-w-[1200px] mx-auto px-6 py-10">
      <div className="mb-8">
        <h1 className="text-2xl font-bold mb-1 flex items-center gap-3">
          <Users size={24} className="text-[#FFD700]" />
          {t.title}
        </h1>
        <p className="text-[#94a3b8] text-sm">{t.subtitle}</p>
      </div>

      {/* Leaderboard */}
      <Card className="mb-8">
        <p className="text-sm font-semibold text-[#FFD700] mb-4">{t.leaderboard}</p>
        <div className="space-y-4">
          {DEMO_TEAMS.map((team) => (
            <div key={team.name} className="flex items-center gap-4">
              <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold shrink-0 ${
                team.rank === 1 ? "bg-[#FFD700] text-black" : team.rank === 2 ? "bg-[#94a3b8] text-black" : "bg-[#a16207] text-white"
              }`}>
                {team.rank}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <p className="font-semibold text-sm">{team.name}</p>
                  {team.trend === "up" ? (
                    <TrendingUp size={14} className="text-[#10b981]" />
                  ) : team.trend === "down" ? (
                    <TrendingDown size={14} className="text-red-400" />
                  ) : (
                    <Minus size={14} className="text-[#64748b]" />
                  )}
                </div>
                <ScoreBar score={team.resilienceScore} />
              </div>
              <div className="text-right shrink-0">
                <p className="text-xs text-[#64748b]">{t.actionItems}</p>
                <p className="text-xs">
                  <span className="text-[#10b981] font-mono">{team.actionItems.closed}</span>
                  <span className="text-[#475569]">/{team.actionItems.open + team.actionItems.closed}</span>
                </p>
              </div>
            </div>
          ))}
        </div>
      </Card>

      {/* Team details */}
      <div className="space-y-6">
        {DEMO_TEAMS.map((team) => (
          <Card key={team.name}>
            <div className="flex items-center gap-3 mb-6">
              <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold shrink-0 ${
                team.rank === 1 ? "bg-[#FFD700] text-black" : team.rank === 2 ? "bg-[#94a3b8] text-black" : "bg-[#a16207] text-white"
              }`}>
                {team.rank}
              </div>
              <div>
                <p className="font-bold">{team.name}</p>
                <p className="text-xs text-[#64748b]">{team.members.length} {t.members}</p>
              </div>
            </div>

            <div className="grid md:grid-cols-2 gap-6">
              {/* DORA metrics */}
              <div>
                <p className="text-xs text-[#64748b] uppercase tracking-wider mb-3">DORA Metrics</p>
                <div className="space-y-2">
                  {[
                    { label: t.deployFreq, value: team.dora.deployFreq, key: "deployFreq" },
                    { label: t.leadTime, value: team.dora.leadTime, key: "leadTime" },
                    { label: t.changeFailRate, value: team.dora.changeFailRate, key: "changeFailRate" },
                    { label: t.mttr, value: team.dora.mttr, key: "mttr" },
                  ].map(({ label, value, key }) => {
                    const color = DORA_LEVELS[key]?.color(value) ?? "#94a3b8";
                    return (
                      <div key={key} className="flex items-center justify-between bg-[#0a0e1a] rounded-lg px-3 py-2">
                        <p className="text-xs text-[#64748b]">{label}</p>
                        <p className="text-sm font-mono font-bold" style={{ color }}>{value}</p>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Members */}
              <div>
                <p className="text-xs text-[#64748b] uppercase tracking-wider mb-3">{t.members}</p>
                <div className="space-y-2">
                  {team.members.map((member) => (
                    <div key={member.name} className="flex items-center gap-3 bg-[#0a0e1a] rounded-lg px-3 py-2">
                      <div className="w-7 h-7 rounded-full bg-[#1e293b] flex items-center justify-center text-xs font-bold text-[#94a3b8] shrink-0">
                        {member.avatar}
                      </div>
                      <div>
                        <p className="text-sm font-semibold">{member.name}</p>
                        <p className="text-xs text-[#64748b]">{member.role}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Action items progress */}
            <div className="mt-4 pt-4 border-t border-[#1e293b]">
              <div className="flex items-center justify-between mb-2">
                <p className="text-xs text-[#64748b] uppercase tracking-wider">{t.actionItems} {t.completionRate}</p>
                <p className="text-sm font-mono font-bold text-[#10b981]">
                  {Math.round(team.actionItems.closed / (team.actionItems.open + team.actionItems.closed) * 100)}%
                </p>
              </div>
              <div className="h-2 bg-[#1e293b] rounded-full overflow-hidden">
                <div
                  className="h-full bg-[#10b981] rounded-full"
                  style={{ width: `${Math.round(team.actionItems.closed / (team.actionItems.open + team.actionItems.closed) * 100)}%` }}
                />
              </div>
              <div className="flex justify-between text-xs text-[#64748b] mt-1">
                <span>{team.actionItems.closed} {t.closed}</span>
                <span>{team.actionItems.open} {t.open}</span>
              </div>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
