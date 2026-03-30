"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useEffect, useState } from "react";
import { api, type ExecutiveReport } from "@/lib/api";
import { FileText, Loader2, Download, AlertTriangle, CheckCircle2 } from "lucide-react";

const DEMO_REPORT: ExecutiveReport = {
  title: "FaultRay Infrastructure Resilience Report",
  generated_at: "2026-03-30T12:00:00Z",
  executive_summary: {
    overall_score: 85.2,
    availability_estimate: "99.99%",
    risk_level: "Medium",
    total_components: 12,
    total_scenarios_tested: 2048,
    critical_issues: 3,
    recommendations_count: 8,
  },
  key_findings: [
    { severity: "CRITICAL", finding: "Single point of failure in primary database", impact: "Complete service outage during database failures", recommendation: "Implement automated failover with promotion time < 30s" },
    { severity: "HIGH", finding: "Cache cluster lacks partition tolerance", impact: "30% latency increase during network partitions", recommendation: "Deploy Redis Cluster with 3+ nodes across AZs" },
    { severity: "HIGH", finding: "No circuit breaker pattern", impact: "Cascading failures propagate", recommendation: "Implement circuit breaker with fallback responses" },
    { severity: "MEDIUM", finding: "Health check intervals too long (60s)", impact: "Slow failure detection", recommendation: "Reduce to 10 seconds" },
  ],
  availability_breakdown: { hardware_nines: 5.91, software_nines: 4.0, theoretical_nines: 6.65, bottleneck: "Software layer" },
  compliance_status: {
    dora: { status: "partial", score: 72 },
    soc2: { status: "partial", score: 68 },
    iso27001: { status: "compliant", score: 85 },
  },
  improvement_roadmap: [
    { priority: 1, action: "Database failover automation", effort: "Medium", impact: "+0.5 nines", timeline: "2 weeks" },
    { priority: 2, action: "Circuit breaker implementation", effort: "Low", impact: "+0.3 nines", timeline: "1 week" },
    { priority: 3, action: "Cache cluster upgrade", effort: "Medium", impact: "+0.2 nines", timeline: "1 week" },
    { priority: 4, action: "Health check optimization", effort: "Low", impact: "+0.1 nines", timeline: "1 day" },
  ],
};

function severityBadge(sev: string) {
  switch (sev) {
    case "CRITICAL": return "red" as const;
    case "HIGH": return "yellow" as const;
    case "MEDIUM": return "gold" as const;
    default: return "default" as const;
  }
}

export default function ReportsPage() {
  const [report, setReport] = useState<ExecutiveReport>(DEMO_REPORT);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .getExecutiveReport("json")
      .then((result) => setReport(result))
      .catch(() => setReport(DEMO_REPORT))
      .finally(() => setLoading(false));
  }, []);

  const downloadJson = () => {
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "faultray-report.json";
    a.click();
    URL.revokeObjectURL(url);
  };

  const downloadHtml = async () => {
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || ""}/api/report-executive?format=html`);
      const html = await res.text();
      const blob = new Blob([html], { type: "text/html" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "faultray-report.html";
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      // Fallback: just download JSON
      downloadJson();
    }
  };

  return (
    <div className="max-w-[1200px] mx-auto px-6 py-10">
      <div className="flex items-center justify-between mb-10">
        <div>
          <h1 className="text-2xl font-bold mb-1 flex items-center gap-3">
            <FileText size={24} className="text-[#FFD700]" />
            Reports
          </h1>
          <p className="text-[#94a3b8] text-sm">Executive summary and downloadable reports</p>
        </div>
        <div className="flex gap-2">
          <Button variant="secondary" size="sm" onClick={downloadJson}>
            <Download size={14} /> JSON
          </Button>
          <Button variant="secondary" size="sm" onClick={downloadHtml}>
            <Download size={14} /> HTML
          </Button>
        </div>
      </div>

      {loading ? (
        <Card className="flex items-center justify-center py-20">
          <Loader2 size={24} className="animate-spin text-[#FFD700]" />
        </Card>
      ) : (
        <div className="space-y-6">
          {/* Executive Summary */}
          <div className="grid md:grid-cols-4 gap-6">
            <Card className="text-center">
              <p className="text-xs text-[#64748b] uppercase tracking-wider mb-2">Score</p>
              <p className="text-4xl font-extrabold font-mono text-[#FFD700]">
                {report.executive_summary.overall_score}
              </p>
            </Card>
            <Card className="text-center">
              <p className="text-xs text-[#64748b] uppercase tracking-wider mb-2">Availability</p>
              <p className="text-4xl font-extrabold font-mono text-emerald-400">
                {report.executive_summary.availability_estimate}
              </p>
            </Card>
            <Card className="text-center">
              <p className="text-xs text-[#64748b] uppercase tracking-wider mb-2">Scenarios</p>
              <p className="text-4xl font-extrabold font-mono">
                {report.executive_summary.total_scenarios_tested.toLocaleString()}
              </p>
            </Card>
            <Card className="text-center">
              <p className="text-xs text-[#64748b] uppercase tracking-wider mb-2">Critical</p>
              <p className="text-4xl font-extrabold font-mono text-red-400">
                {report.executive_summary.critical_issues}
              </p>
            </Card>
          </div>

          {/* Key Findings */}
          <Card>
            <h3 className="text-lg font-bold mb-4 flex items-center gap-2">
              <AlertTriangle size={18} className="text-red-400" />
              Key Findings
            </h3>
            <div className="space-y-3">
              {report.key_findings.map((f, i) => (
                <div
                  key={i}
                  className={`p-4 rounded-xl border ${
                    f.severity === "CRITICAL"
                      ? "bg-red-500/5 border-red-500/20"
                      : f.severity === "HIGH"
                        ? "bg-yellow-500/5 border-yellow-500/20"
                        : "bg-white/[0.02] border-[#1e293b]"
                  }`}
                >
                  <div className="flex items-start gap-3">
                    <Badge variant={severityBadge(f.severity)}>{f.severity}</Badge>
                    <div className="flex-1">
                      <p className="text-sm font-medium">{f.finding}</p>
                      <p className="text-xs text-[#64748b] mt-1">Impact: {f.impact}</p>
                      <p className="text-xs text-emerald-400 mt-1">
                        <CheckCircle2 size={10} className="inline mr-1" />
                        {f.recommendation}
                      </p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </Card>

          {/* Availability Breakdown */}
          <Card>
            <h3 className="text-lg font-bold mb-4">Availability Breakdown</h3>
            <div className="space-y-3">
              {[
                { label: "Hardware", value: report.availability_breakdown.hardware_nines, color: "bg-emerald-400" },
                { label: "Software", value: report.availability_breakdown.software_nines, color: "bg-[#FFD700]" },
                { label: "Theoretical", value: report.availability_breakdown.theoretical_nines, color: "bg-blue-400" },
              ].map((layer) => (
                <div key={layer.label} className="grid grid-cols-[100px_1fr_60px] items-center gap-4">
                  <span className="text-sm text-[#64748b]">{layer.label}</span>
                  <div className="h-3 bg-white/5 rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full ${layer.color}`}
                      style={{ width: `${(layer.value / 7) * 100}%` }}
                    />
                  </div>
                  <span className="text-sm font-mono font-semibold text-right">{layer.value.toFixed(2)}</span>
                </div>
              ))}
            </div>
            <p className="text-xs text-[#FFD700] mt-3">
              Bottleneck: {report.availability_breakdown.bottleneck}
            </p>
          </Card>

          {/* Improvement Roadmap */}
          <Card>
            <h3 className="text-lg font-bold mb-4">Improvement Roadmap</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[#1e293b]">
                    <th className="text-left py-3 px-2 text-[#64748b] font-medium">#</th>
                    <th className="text-left py-3 px-2 text-[#64748b] font-medium">Action</th>
                    <th className="text-left py-3 px-2 text-[#64748b] font-medium">Effort</th>
                    <th className="text-left py-3 px-2 text-[#64748b] font-medium">Impact</th>
                    <th className="text-left py-3 px-2 text-[#64748b] font-medium">Timeline</th>
                  </tr>
                </thead>
                <tbody>
                  {report.improvement_roadmap.map((item) => (
                    <tr key={item.priority} className="border-b border-[#1e293b]/50">
                      <td className="py-3 px-2 font-bold text-[#FFD700]">{item.priority}</td>
                      <td className="py-3 px-2">{item.action}</td>
                      <td className="py-3 px-2">
                        <Badge variant={item.effort === "Low" ? "green" : "yellow"}>{item.effort}</Badge>
                      </td>
                      <td className="py-3 px-2 font-mono text-emerald-400">{item.impact}</td>
                      <td className="py-3 px-2 text-[#94a3b8]">{item.timeline}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          {/* Compliance Status */}
          <Card>
            <h3 className="text-lg font-bold mb-4">Compliance Status</h3>
            <div className="grid md:grid-cols-3 gap-4">
              {Object.entries(report.compliance_status).map(([fw, status]) => (
                <div key={fw} className="p-4 rounded-xl border border-[#1e293b] bg-white/[0.02] text-center">
                  <p className="text-lg font-bold uppercase">{fw}</p>
                  <p
                    className="text-3xl font-extrabold font-mono mt-2"
                    style={{ color: status.score >= 80 ? "#10b981" : status.score >= 60 ? "#f59e0b" : "#ef4444" }}
                  >
                    {status.score}%
                  </p>
                  <Badge
                    variant={status.status === "compliant" ? "green" : "yellow"}
                    className="mt-2"
                  >
                    {status.status}
                  </Badge>
                </div>
              ))}
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}
