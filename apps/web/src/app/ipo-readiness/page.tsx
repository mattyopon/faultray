"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useState } from "react";
import {
  TrendingUp,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Server,
  ShieldCheck,
  BookOpen,
  GitBranch,
  Activity,
  Lock,
  Globe,
  FileSearch,
  Download,
  ChevronRight,
  Loader2,
} from "lucide-react";
import Link from "next/link";
import { useLocale } from "@/lib/useLocale";
import { appDict } from "@/i18n/app-dict";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

type CheckStatus = "ready" | "needs_work" | "not_started";

interface CheckItem {
  id: string;
  titleKey: string;
  descKey: string;
  icon: React.ElementType;
  status: CheckStatus;
  score: number;
  href: string;
  details: string[];
}

/* ------------------------------------------------------------------ */
/*  Demo data                                                          */
/* ------------------------------------------------------------------ */

const CHECKLIST: CheckItem[] = [
  {
    id: "infra",
    titleKey: "infraReliability",
    descKey: "infraReliabilityDesc",
    icon: Server,
    status: "ready",
    score: 92,
    href: "/dashboard",
    details: [
      "Multi-AZ deployment confirmed",
      "Resilience score 92/100",
      "Auto-scaling configured",
      "Load balancer health checks active",
    ],
  },
  {
    id: "dora",
    titleKey: "doraCompliance",
    descKey: "doraComplianceDesc",
    icon: ShieldCheck,
    status: "needs_work",
    score: 71,
    href: "/dora",
    details: [
      "DORA Pillar 1-3: Compliant",
      "Pillar 4 (Testing): Partial — increase test coverage",
      "Pillar 5 (Third-party): Needs documentation",
      "SOC2 Type II: In progress",
    ],
  },
  {
    id: "incident",
    titleKey: "incidentResponse",
    descKey: "incidentResponseDesc",
    icon: BookOpen,
    status: "ready",
    score: 88,
    href: "/runbooks",
    details: [
      "12 runbooks documented",
      "All critical scenarios covered",
      "Last tabletop exercise: 2026-02-15",
      "Mean time to acknowledge < 5 min",
    ],
  },
  {
    id: "change",
    titleKey: "changeManagement",
    descKey: "changeManagementDesc",
    icon: GitBranch,
    status: "needs_work",
    score: 65,
    href: "/iac",
    details: [
      "IaC: Partially implemented (60%)",
      "CI/CD: Configured for 3/5 services",
      "Rollback procedure: Documented",
      "Change approval: Manual — needs automation",
    ],
  },
  {
    id: "monitoring",
    titleKey: "monitoring",
    descKey: "monitoringDesc",
    icon: Activity,
    status: "ready",
    score: 95,
    href: "/apm",
    details: [
      "APM agent deployed on all services",
      "SLO tracking: 4 SLOs defined",
      "Alert routing: PagerDuty configured",
      "Error budget: 94% remaining",
    ],
  },
  {
    id: "data",
    titleKey: "dataProtection",
    descKey: "dataProtectionDesc",
    icon: Lock,
    status: "needs_work",
    score: 78,
    href: "/security",
    details: [
      "Encryption at rest: Enabled",
      "Encryption in transit: TLS 1.3",
      "Data classification: In progress",
      "GDPR/CCPA: Partial compliance",
    ],
  },
  {
    id: "dr",
    titleKey: "disasterRecovery",
    descKey: "disasterRecoveryDesc",
    icon: Globe,
    status: "not_started",
    score: 35,
    href: "/iac",
    details: [
      "DR plan: Draft exists, not tested",
      "RPO: Undefined",
      "RTO: Undefined",
      "Last backup validation: Never",
    ],
  },
  {
    id: "audit",
    titleKey: "securityAudit",
    descKey: "securityAuditDesc",
    icon: FileSearch,
    status: "ready",
    score: 90,
    href: "/evidence",
    details: [
      "CloudTrail: Enabled, 1-year retention",
      "Audit evidence: 47 artifacts collected",
      "Access logs: Centralized in SIEM",
      "Immutable audit trail: Confirmed",
    ],
  },
];

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function getStatusIcon(status: CheckStatus) {
  switch (status) {
    case "ready":
      return <CheckCircle2 size={16} className="text-green-400" />;
    case "needs_work":
      return <AlertTriangle size={16} className="text-yellow-400" />;
    case "not_started":
      return <XCircle size={16} className="text-red-400" />;
  }
}

function getStatusColor(status: CheckStatus) {
  switch (status) {
    case "ready": return "bg-green-500/10 text-green-400 border-green-500/20";
    case "needs_work": return "bg-yellow-500/10 text-yellow-400 border-yellow-500/20";
    case "not_started": return "bg-red-500/10 text-red-400 border-red-500/20";
  }
}

function calcOverallScore(items: CheckItem[]): number {
  return Math.round(items.reduce((acc, item) => acc + item.score, 0) / items.length);
}

function generateHTMLReport(items: CheckItem[], t: Record<string, string>, overall: number): string {
  const rows = items.map((item) => `
    <tr>
      <td style="padding:12px;border-bottom:1px solid #1e293b;">${t[item.titleKey] ?? item.id}</td>
      <td style="padding:12px;border-bottom:1px solid #1e293b;">${item.status === "ready" ? "✅ Ready" : item.status === "needs_work" ? "⚠️ Needs Work" : "❌ Not Started"}</td>
      <td style="padding:12px;border-bottom:1px solid #1e293b;">${item.score}/100</td>
      <td style="padding:12px;border-bottom:1px solid #1e293b;font-size:12px;">${item.details.join("<br>")}</td>
    </tr>
  `).join("");

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>FaultRay IPO Audit Package</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0a0e1a; color: #e2e8f0; margin: 0; padding: 40px; }
  h1 { color: #FFD700; margin-bottom: 4px; }
  p { color: #94a3b8; margin: 0 0 32px; }
  .score { font-size: 48px; font-weight: 700; color: ${overall >= 80 ? "#4ade80" : overall >= 60 ? "#facc15" : "#f87171"}; }
  table { width: 100%; border-collapse: collapse; background: #0f1629; border-radius: 8px; overflow: hidden; }
  th { background: #1e293b; padding: 12px; text-align: left; font-size: 13px; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; }
  td { color: #94a3b8; font-size: 14px; }
  .footer { margin-top: 32px; color: #475569; font-size: 12px; text-align: center; }
</style>
</head>
<body>
<h1>FaultRay IPO Audit Package</h1>
<p>Generated: ${new Date().toISOString().slice(0, 10)} | Prepared for investor and auditor review</p>
<div class="score">${overall}<span style="font-size:20px;color:#64748b">/100</span></div>
<p style="margin-bottom:24px;">Overall IPO Readiness Score</p>
<table>
  <thead>
    <tr>
      <th>Area</th>
      <th>Status</th>
      <th>Score</th>
      <th>Details</th>
    </tr>
  </thead>
  <tbody>${rows}</tbody>
</table>
<div class="footer">Generated by FaultRay — Infrastructure Resilience Intelligence</div>
</body>
</html>`;
}

/* ------------------------------------------------------------------ */
/*  Page                                                               */
/* ------------------------------------------------------------------ */

export default function IpoReadinessPage() {
  const locale = useLocale();
  const t = (appDict.ipoReadiness as Record<string, Record<string, string>>)[locale] ?? appDict.ipoReadiness.en;

  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [reportReady, setReportReady] = useState(false);
  const [reportBlob, setReportBlob] = useState<string | null>(null);

  const overall = calcOverallScore(CHECKLIST);
  const ready = CHECKLIST.filter((c) => c.status === "ready").length;
  const needsWork = CHECKLIST.filter((c) => c.status === "needs_work").length;
  const notStarted = CHECKLIST.filter((c) => c.status === "not_started").length;

  function handleGenerate() {
    setGenerating(true);
    setReportReady(false);
    setTimeout(() => {
      const html = generateHTMLReport(CHECKLIST, t, overall);
      const blob = URL.createObjectURL(new Blob([html], { type: "text/html" }));
      setReportBlob(blob);
      setGenerating(false);
      setReportReady(true);
    }, 1800);
  }

  function handleDownload() {
    if (!reportBlob) return;
    const a = document.createElement("a");
    a.href = reportBlob;
    a.download = `faultray-ipo-audit-${new Date().toISOString().slice(0, 10)}.html`;
    a.click();
  }

  const overallColor = overall >= 80 ? "text-green-400" : overall >= 60 ? "text-yellow-400" : "text-red-400";
  const progressWidth = `${overall}%`;

  return (
    <div className="min-h-screen pt-4 pb-12">
      <div className="w-full px-6 py-10">
        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center gap-3 mb-2">
            <TrendingUp size={28} className="text-[#FFD700]" />
            <h1 className="text-2xl font-bold">{t.title}</h1>
          </div>
          <p className="text-[#94a3b8]">{t.subtitle}</p>
        </div>

        {/* Score overview */}
        <Card className="bg-[#0f1629] border-[#1e293b] p-6 mb-6">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-4">
            <div>
              <p className="text-xs text-[#64748b] uppercase tracking-wider mb-1">{t.overallScore}</p>
              <div className="flex items-baseline gap-2">
                <span className={`text-5xl font-bold ${overallColor}`}>{overall}</span>
                <span className="text-[#475569] text-lg">/100</span>
              </div>
            </div>
            <div className="flex items-center gap-4 text-sm">
              <div className="flex items-center gap-1.5">
                <CheckCircle2 size={14} className="text-green-400" />
                <span className="text-[#94a3b8]">{ready} {t.statusReady}</span>
              </div>
              <div className="flex items-center gap-1.5">
                <AlertTriangle size={14} className="text-yellow-400" />
                <span className="text-[#94a3b8]">{needsWork} {t.statusNeedsWork}</span>
              </div>
              <div className="flex items-center gap-1.5">
                <XCircle size={14} className="text-red-400" />
                <span className="text-[#94a3b8]">{notStarted} {t.statusNotStarted}</span>
              </div>
            </div>
          </div>

          {/* Progress bar */}
          <div className="w-full bg-[#1e293b] rounded-full h-2.5 overflow-hidden">
            <div
              className={`h-2.5 rounded-full transition-all duration-700 ${
                overall >= 80 ? "bg-green-400" : overall >= 60 ? "bg-yellow-400" : "bg-red-400"
              }`}
              style={{ width: progressWidth }}
            />
          </div>
          <div className="flex justify-between text-[10px] text-[#475569] mt-1">
            <span>0</span>
            <span>50</span>
            <span>100</span>
          </div>
        </Card>

        {/* Checklist */}
        <Card className="bg-[#0f1629] border-[#1e293b] p-6 mb-6">
          <h2 className="text-sm font-semibold text-white mb-4">{t.checklistTitle}</h2>
          <div className="space-y-2">
            {CHECKLIST.map((item) => {
              const Icon = item.icon;
              const isExpanded = expandedId === item.id;
              return (
                <div
                  key={item.id}
                  className={`rounded-lg border transition-colors ${
                    isExpanded ? "border-[#334155] bg-[#060b16]" : "border-[#1e293b] hover:border-[#334155]"
                  }`}
                >
                  {/* Row */}
                  <button
                    className="w-full flex items-center gap-3 p-4 text-left"
                    onClick={() => setExpandedId(isExpanded ? null : item.id)}
                  >
                    <div className="w-8 h-8 rounded-lg bg-[#1e293b] flex items-center justify-center shrink-0">
                      <Icon size={15} className="text-[#64748b]" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-0.5">
                        {getStatusIcon(item.status)}
                        <p className="text-sm font-medium text-white">{t[item.titleKey]}</p>
                      </div>
                      <p className="text-xs text-[#64748b] truncate">{t[item.descKey]}</p>
                    </div>
                    <div className="flex items-center gap-3 shrink-0">
                      <Badge className={`text-[9px] ${getStatusColor(item.status)}`}>
                        {item.status === "ready"
                          ? t.statusReady
                          : item.status === "needs_work"
                          ? t.statusNeedsWork
                          : t.statusNotStarted}
                      </Badge>
                      <span className={`text-sm font-semibold w-10 text-right ${
                        item.score >= 85 ? "text-green-400" :
                        item.score >= 65 ? "text-yellow-400" :
                        "text-red-400"
                      }`}>
                        {item.score}
                      </span>
                      <ChevronRight
                        size={14}
                        className={`text-[#475569] transition-transform ${isExpanded ? "rotate-90" : ""}`}
                      />
                    </div>
                  </button>

                  {/* Expanded details */}
                  {isExpanded && (
                    <div className="px-4 pb-4 border-t border-[#1e293b]">
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5 mt-3 mb-3">
                        {item.details.map((detail, i) => (
                          <div key={i} className="flex items-start gap-2">
                            <div className="w-1 h-1 rounded-full bg-[#475569] mt-1.5 shrink-0" />
                            <p className="text-xs text-[#64748b]">{detail}</p>
                          </div>
                        ))}
                      </div>
                      <Link href={item.href}>
                        <Button
                          size="sm"
                          variant="secondary"
                          className="h-7 text-xs border-[#334155] text-[#94a3b8] hover:text-white"
                        >
                          {t.viewPage} <ChevronRight size={11} className="ml-1" />
                        </Button>
                      </Link>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </Card>

        {/* Generate package */}
        <Card className="bg-[#0f1629] border-[#1e293b] p-6">
          <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4">
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-1">
                <FileSearch size={18} className="text-[#FFD700]" />
                <h3 className="text-sm font-semibold text-white">{t.generatePackage}</h3>
              </div>
              <p className="text-xs text-[#64748b]">{t.packageDesc}</p>
            </div>
            <div className="flex items-center gap-3 shrink-0">
              {reportReady && (
                <Button
                  onClick={handleDownload}
                  variant="secondary"
                  className="border-green-500/30 text-green-400 hover:bg-green-500/10"
                >
                  <Download size={14} className="mr-2" />
                  {t.downloadReady}
                </Button>
              )}
              <Button
                onClick={handleGenerate}
                disabled={generating}
                className="bg-[#FFD700] text-black hover:bg-[#FFD700]/90 disabled:opacity-60"
              >
                {generating ? (
                  <>
                    <Loader2 size={14} className="mr-2 animate-spin" />
                    {t.generating}
                  </>
                ) : (
                  <>
                    <TrendingUp size={14} className="mr-2" />
                    {t.generatePackage}
                  </>
                )}
              </Button>
            </div>
          </div>

          {/* Score summary in report context */}
          {(generating || reportReady) && (
            <div className="mt-4 grid grid-cols-4 gap-3">
              {CHECKLIST.slice(0, 4).map((item) => {
                const Icon = item.icon;
                return (
                  <div key={item.id} className="bg-[#060b16] rounded-lg p-3 text-center">
                    <Icon size={16} className="text-[#475569] mx-auto mb-1" />
                    <p className="text-[10px] text-[#475569] mb-1 truncate">{t[item.titleKey]}</p>
                    <p className={`text-lg font-bold ${
                      item.score >= 85 ? "text-green-400" : item.score >= 65 ? "text-yellow-400" : "text-red-400"
                    }`}>{item.score}</p>
                  </div>
                );
              })}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
