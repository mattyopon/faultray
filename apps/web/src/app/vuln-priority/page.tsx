"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useEffect, useState } from "react";
import { ShieldAlert, Loader2, TrendingUp } from "lucide-react";
import { useLocale } from "@/lib/useLocale";
import { appDict } from "@/i18n/app-dict";

interface RiskFactor {
  name: string;
  value: string;
  weight: number;
}

interface VulnEntry {
  rank: number;
  component: string;
  vuln_id: string;
  vuln_score: number;
  blast_radius: number;
  exploitability: number;
  priority_score: number;
  cve?: string;
  risk_factors: RiskFactor[];
  status: "open" | "patching" | "mitigated";
}

interface VulnPriorityData {
  scan_date: string;
  total_vulns: number;
  critical_count: number;
  high_count: number;
  avg_priority_score: number;
  entries: VulnEntry[];
}

const DEMO_DATA: VulnPriorityData = {
  scan_date: "2026-04-01",
  total_vulns: 24,
  critical_count: 3,
  high_count: 7,
  avg_priority_score: 56.2,
  entries: [
    { rank: 1, component: "PostgreSQL Primary", vuln_id: "CVE-2025-1234", vuln_score: 9.8, blast_radius: 95, exploitability: 8.5, priority_score: 97.1, cve: "CVE-2025-1234", risk_factors: [{ name: "Public Exposure", value: "No", weight: 0.3 }, { name: "Data Sensitivity", value: "PII + Financial", weight: 0.4 }, { name: "Patch Available", value: "Yes", weight: 0.3 }], status: "open" },
    { rank: 2, component: "Auth Service", vuln_id: "CVE-2025-5678", vuln_score: 8.9, blast_radius: 88, exploitability: 7.8, priority_score: 91.4, cve: "CVE-2025-5678", risk_factors: [{ name: "Authentication Bypass", value: "Possible", weight: 0.5 }, { name: "User Impact", value: "All users", weight: 0.5 }], status: "open" },
    { rank: 3, component: "API Gateway", vuln_id: "CVE-2025-9012", vuln_score: 8.2, blast_radius: 100, exploitability: 6.5, priority_score: 88.7, cve: "CVE-2025-9012", risk_factors: [{ name: "Internet Facing", value: "Yes", weight: 0.4 }, { name: "Rate Limiting", value: "Partial", weight: 0.3 }, { name: "WAF Coverage", value: "60%", weight: 0.3 }], status: "patching" },
    { rank: 4, component: "Redis Cache", vuln_id: "CVE-2024-3456", vuln_score: 7.5, blast_radius: 60, exploitability: 7.2, priority_score: 76.3, cve: "CVE-2024-3456", risk_factors: [{ name: "Memory Exposure", value: "Session Data", weight: 0.6 }, { name: "Network Exposure", value: "Internal Only", weight: 0.4 }], status: "open" },
    { rank: 5, component: "CDN / Edge", vuln_id: "CVE-2024-7890", vuln_score: 6.8, blast_radius: 75, exploitability: 5.5, priority_score: 68.9, cve: "CVE-2024-7890", risk_factors: [{ name: "Cache Poisoning Risk", value: "Medium", weight: 0.5 }, { name: "Origin Shield", value: "Enabled", weight: 0.5 }], status: "mitigated" },
    { rank: 6, component: "Background Worker", vuln_id: "INT-2025-001", vuln_score: 6.2, blast_radius: 45, exploitability: 6.0, priority_score: 59.8, risk_factors: [{ name: "Job Injection Risk", value: "Low", weight: 0.5 }, { name: "Queue Access", value: "Internal", weight: 0.5 }], status: "open" },
    { rank: 7, component: "Object Storage", vuln_id: "INT-2025-002", vuln_score: 5.8, blast_radius: 55, exploitability: 4.2, priority_score: 52.4, risk_factors: [{ name: "Public Bucket Risk", value: "None detected", weight: 0.6 }, { name: "Encryption", value: "At-rest only", weight: 0.4 }], status: "patching" },
    { rank: 8, component: "Monitoring Stack", vuln_id: "CVE-2024-2468", vuln_score: 5.1, blast_radius: 30, exploitability: 4.8, priority_score: 44.1, cve: "CVE-2024-2468", risk_factors: [{ name: "Dashboard Exposure", value: "Internal", weight: 0.5 }, { name: "Alerting Bypass", value: "Possible", weight: 0.5 }], status: "open" },
  ],
};

function priorityColor(score: number): string {
  if (score >= 85) return "#ef4444";
  if (score >= 65) return "#f59e0b";
  if (score >= 45) return "#eab308";
  return "#10b981";
}

function statusBadge(status: string): "red" | "yellow" | "green" | "default" {
  if (status === "open") return "red";
  if (status === "patching") return "yellow";
  return "green";
}

export default function VulnPriorityPage() {
  const [data, setData] = useState<VulnPriorityData>(DEMO_DATA);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<string | null>(null);
  const locale = useLocale();
  const t = appDict.vulnPriority[locale] ?? appDict.vulnPriority.en;

  useEffect(() => {
    fetch("/api/proxy?path=/api/v1/vuln-priority")
      .then((r) => r.json())
      .then((d) => setData(d))
      .catch(() => setData(DEMO_DATA))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="max-w-6xl mx-auto px-6 py-10">
      <div className="mb-10">
        <h1 className="text-2xl font-bold mb-1 flex items-center gap-3">
          <ShieldAlert size={24} className="text-[#FFD700]" />
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
        <>
          {/* Summary */}
          <div className="grid md:grid-cols-4 gap-4 mb-8">
            <Card className="text-center">
              <p className="text-3xl font-extrabold font-mono text-[#94a3b8]">{data.total_vulns}</p>
              <p className="text-xs text-[#64748b] uppercase tracking-wider mt-1">{t.totalVulns}</p>
            </Card>
            <Card className="text-center">
              <p className="text-3xl font-extrabold font-mono text-red-400">{data.critical_count}</p>
              <p className="text-xs text-[#64748b] uppercase tracking-wider mt-1">{t.critical}</p>
            </Card>
            <Card className="text-center">
              <p className="text-3xl font-extrabold font-mono text-[#f59e0b]">{data.high_count}</p>
              <p className="text-xs text-[#64748b] uppercase tracking-wider mt-1">{t.high}</p>
            </Card>
            <Card className="text-center">
              <p className="text-3xl font-extrabold font-mono text-[#FFD700]">{data.avg_priority_score.toFixed(1)}</p>
              <p className="text-xs text-[#64748b] uppercase tracking-wider mt-1">{t.avgPriority}</p>
            </Card>
          </div>

          {/* Priority Matrix */}
          <Card>
            <div className="flex items-center gap-2 mb-4">
              <TrendingUp size={16} className="text-[#FFD700]" />
              <h3 className="text-sm font-semibold text-[#94a3b8] uppercase tracking-wider">{t.priorityMatrix}</h3>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[#1e293b]">
                    <th className="text-center py-3 px-2 text-[#64748b] font-medium w-10">{t.rank}</th>
                    <th className="text-left py-3 px-3 text-[#64748b] font-medium">{t.component}</th>
                    <th className="text-left py-3 px-3 text-[#64748b] font-medium">CVE / ID</th>
                    <th className="text-center py-3 px-2 text-[#64748b] font-medium">{t.vulnScore}</th>
                    <th className="text-center py-3 px-2 text-[#64748b] font-medium">{t.blastRadius}</th>
                    <th className="text-center py-3 px-2 text-[#64748b] font-medium">{t.priorityScore}</th>
                    <th className="text-center py-3 px-2 text-[#64748b] font-medium">{t.status}</th>
                  </tr>
                </thead>
                <tbody>
                  {data.entries.map((entry) => (
                    <>
                      <tr
                        key={entry.vuln_id}
                        className="border-b border-[#1e293b]/50 hover:bg-white/[0.02] cursor-pointer"
                        onClick={() => setExpanded(expanded === entry.vuln_id ? null : entry.vuln_id)}
                      >
                        <td className="py-3 px-2 text-center">
                          <span className="font-mono font-bold text-[#64748b]">#{entry.rank}</span>
                        </td>
                        <td className="py-3 px-3 font-medium">{entry.component}</td>
                        <td className="py-3 px-3 font-mono text-xs text-[#64748b]">{entry.vuln_id}</td>
                        <td className="py-3 px-2 text-center">
                          <span className="font-mono font-bold" style={{ color: entry.vuln_score >= 9 ? "#ef4444" : entry.vuln_score >= 7 ? "#f59e0b" : "#eab308" }}>
                            {entry.vuln_score.toFixed(1)}
                          </span>
                        </td>
                        <td className="py-3 px-2 text-center">
                          <div className="flex items-center justify-center gap-2">
                            <div className="w-16 h-2 bg-white/5 rounded-full overflow-hidden">
                              <div className="h-full rounded-full" style={{ width: `${entry.blast_radius}%`, backgroundColor: priorityColor(entry.blast_radius) }} />
                            </div>
                            <span className="font-mono text-xs text-[#64748b]">{entry.blast_radius}%</span>
                          </div>
                        </td>
                        <td className="py-3 px-2 text-center">
                          <span className="font-mono font-bold text-lg" style={{ color: priorityColor(entry.priority_score) }}>
                            {entry.priority_score.toFixed(1)}
                          </span>
                        </td>
                        <td className="py-3 px-2 text-center">
                          <Badge variant={statusBadge(entry.status)}>{entry.status}</Badge>
                        </td>
                      </tr>
                      {expanded === entry.vuln_id && (
                        <tr key={`${entry.vuln_id}-detail`} className="border-b border-[#1e293b]/50">
                          <td colSpan={7} className="px-4 py-3 bg-white/[0.01]">
                            <div className="flex flex-wrap gap-3">
                              {entry.risk_factors.map((rf) => (
                                <div key={rf.name} className="flex items-center gap-2 bg-white/5 px-3 py-1.5 rounded-lg text-xs">
                                  <span className="text-[#64748b]">{rf.name}:</span>
                                  <span className="font-medium text-[#94a3b8]">{rf.value}</span>
                                  <span className="text-[#FFD700] font-mono">w={rf.weight}</span>
                                </div>
                              ))}
                            </div>
                          </td>
                        </tr>
                      )}
                    </>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}
    </div>
  );
}
