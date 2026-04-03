"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useState } from "react";
import { FileText, Loader2, Download, ExternalLink, ShieldCheck, CheckCircle2, AlertTriangle, XCircle } from "lucide-react";
import { useLocale } from "@/lib/useLocale";
import { appDict } from "@/i18n/app-dict";
import { useToast } from "@/lib/useToast";
import { Toast } from "@/components/ui/toast";

type Framework = "SOC2" | "ISO27001" | "DORA" | "FISC";

interface ControlResult {
  id: string;
  name: string;
  status: "pass" | "partial" | "fail";
  notes: string;
}

interface FrameworkSummary {
  name: Framework;
  score: number;
  controls_total: number;
  controls_pass: number;
  controls_partial: number;
  controls_fail: number;
  controls: ControlResult[];
}

const FRAMEWORK_DATA: Record<Framework, FrameworkSummary> = {
  SOC2: {
    name: "SOC2",
    score: 78,
    controls_total: 12,
    controls_pass: 8,
    controls_partial: 2,
    controls_fail: 2,
    controls: [
      { id: "CC6.1", name: "Logical Access Controls", status: "pass", notes: "MFA enforced for all privileged accounts" },
      { id: "CC6.2", name: "New Access Provisioning", status: "pass", notes: "IAM policy reviewed quarterly" },
      { id: "CC7.1", name: "System Monitoring", status: "pass", notes: "24/7 monitoring with automated alerting" },
      { id: "CC7.2", name: "Vulnerability Management", status: "partial", notes: "Scanning active; patching SLA needs improvement" },
      { id: "CC8.1", name: "Change Management", status: "pass", notes: "All changes go through PR review and staging" },
      { id: "A1.1", name: "Performance Capacity", status: "pass", notes: "Auto-scaling configured; load tested" },
      { id: "A1.2", name: "Backup & Recovery", status: "partial", notes: "Backups exist; RTO not formally tested this quarter" },
      { id: "A1.3", name: "Recovery Testing", status: "fail", notes: "Disaster recovery drills not completed in 2026" },
      { id: "PI1.1", name: "Data Processing Accuracy", status: "pass", notes: "Input validation and checksums implemented" },
      { id: "C1.1", name: "Data Classification", status: "pass", notes: "PII and sensitive data labeled and encrypted" },
      { id: "C1.2", name: "Data Disposal", status: "pass", notes: "Retention policy enforced with automated deletion" },
      { id: "P6.1", name: "Personal Data Correction", status: "fail", notes: "User data edit/deletion API not fully implemented" },
    ],
  },
  ISO27001: {
    name: "ISO27001",
    score: 72,
    controls_total: 10,
    controls_pass: 6,
    controls_partial: 3,
    controls_fail: 1,
    controls: [
      { id: "A.5.1", name: "Information Security Policies", status: "pass", notes: "Policies documented and board-approved" },
      { id: "A.6.1", name: "Organization of Security", status: "pass", notes: "CISO role established with clear responsibilities" },
      { id: "A.8.1", name: "Asset Management", status: "partial", notes: "Asset inventory 85% complete" },
      { id: "A.9.1", name: "Access Control Policy", status: "pass", notes: "RBAC implemented across all systems" },
      { id: "A.10.1", name: "Cryptographic Controls", status: "pass", notes: "TLS 1.3 enforced; AES-256 for data at rest" },
      { id: "A.12.1", name: "Operational Procedures", status: "pass", notes: "Runbooks maintained and reviewed" },
      { id: "A.12.6", name: "Technical Vulnerability Mgmt", status: "partial", notes: "Patching within 30 days for critical CVEs" },
      { id: "A.16.1", name: "Incident Management", status: "partial", notes: "Process exists; post-mortems not always completed" },
      { id: "A.17.1", name: "Business Continuity", status: "fail", notes: "BCP not tested in the past 12 months" },
      { id: "A.18.1", name: "Compliance Review", status: "pass", notes: "Annual internal audit completed" },
    ],
  },
  DORA: {
    name: "DORA",
    score: 69,
    controls_total: 10,
    controls_pass: 5,
    controls_partial: 3,
    controls_fail: 2,
    controls: [
      { id: "P1-01", name: "ICT Risk Management Policy", status: "pass", notes: "Framework documented with executive oversight" },
      { id: "P1-03", name: "Risk Assessment Process", status: "partial", notes: "Quarterly assessments — frequency below DORA requirement" },
      { id: "P2-01", name: "Incident Detection & Classification", status: "pass", notes: "Automated severity classification in place" },
      { id: "P2-02", name: "Major Incident Reporting", status: "fail", notes: "4-hour reporting pipeline not automated" },
      { id: "P3-01", name: "Periodic ICT Tool Testing", status: "pass", notes: "Regular resilience testing via FaultRay" },
      { id: "P3-02", name: "Threat-Led Penetration Testing", status: "fail", notes: "No formal TLPT program established" },
      { id: "P3-04", name: "Test Evidence Retention", status: "partial", notes: "Retention policy needs 5-year update" },
      { id: "P4-01", name: "Third-Party Classification", status: "partial", notes: "Major vendors identified; classification 70% complete" },
      { id: "P4-02", name: "Contract Clause Standardization", status: "pass", notes: "DORA clauses added to new contracts" },
      { id: "P5-01", name: "Threat Intelligence Sharing", status: "pass", notes: "Active ISAC participation" },
    ],
  },
  FISC: {
    name: "FISC",
    score: 81,
    controls_total: 8,
    controls_pass: 6,
    controls_partial: 1,
    controls_fail: 1,
    controls: [
      { id: "FISC-01", name: "System Security Management", status: "pass", notes: "Security management system documented and operational" },
      { id: "FISC-02", name: "Access Control", status: "pass", notes: "Strict access control per FISC guidelines" },
      { id: "FISC-03", name: "System Audit Trail", status: "pass", notes: "All access and operations logged immutably" },
      { id: "FISC-04", name: "Backup & Recovery", status: "pass", notes: "Geographic redundancy with 4-hour RTO" },
      { id: "FISC-05", name: "Operational Continuity", status: "pass", notes: "BCP and DRP documented with annual review" },
      { id: "FISC-06", name: "Vendor Security Assessment", status: "partial", notes: "Cloud providers assessed; minor vendors pending" },
      { id: "FISC-07", name: "Incident Response", status: "pass", notes: "Incident response runbooks updated quarterly" },
      { id: "FISC-08", name: "Employee Security Education", status: "fail", notes: "Annual security training completion rate: 62% (target: 100%)" },
    ],
  },
};

function statusIcon(status: string) {
  if (status === "pass") return <CheckCircle2 size={16} className="text-emerald-400 shrink-0" />;
  if (status === "partial") return <AlertTriangle size={16} className="text-yellow-400 shrink-0" />;
  return <XCircle size={16} className="text-red-400 shrink-0" />;
}

function statusBadge(status: string): "green" | "yellow" | "red" {
  if (status === "pass") return "green";
  if (status === "partial") return "yellow";
  return "red";
}

export default function ComplianceReportPage() {
  const [selected, setSelected] = useState<Framework>("SOC2");
  const [generating, setGenerating] = useState(false);
  const locale = useLocale();
  const t = appDict.complianceReport[locale] ?? appDict.complianceReport.en;

  const fw = FRAMEWORK_DATA[selected];

  const handleGenerate = () => {
    setGenerating(true);
    // Simulate generation and open report
    setTimeout(() => {
      setGenerating(false);
      const params = new URLSearchParams({ framework: selected, locale });
      window.open(`/api/reports?action=report&format=html&${params.toString()}`, "_blank");
    }, 1500);
  };

  return (
    <div className="max-w-[1200px] mx-auto px-6 py-10">
      <div className="mb-10">
        <h1 className="text-2xl font-bold mb-1 flex items-center gap-3">
          <FileText size={24} className="text-[#FFD700]" />
          {t.title}
        </h1>
        <p className="text-[#94a3b8] text-sm">{t.subtitle}</p>
      </div>

      {/* Framework Selector */}
      <Card className="mb-6">
        <p className="text-xs text-[#64748b] uppercase tracking-wider mb-3">{t.selectFramework}</p>
        <div className="flex flex-wrap gap-3">
          {(["SOC2", "ISO27001", "DORA", "FISC"] as Framework[]).map((fw) => (
            <button
              key={fw}
              onClick={() => setSelected(fw)}
              className={`px-5 py-2.5 rounded-xl text-sm font-semibold transition-all border ${
                selected === fw
                  ? "bg-[#FFD700]/10 text-[#FFD700] border-[#FFD700]/30"
                  : "text-[#94a3b8] border-[#1e293b] hover:border-[#64748b]"
              }`}
            >
              {fw}
            </button>
          ))}
          <div className="ml-auto">
            <Button onClick={handleGenerate} disabled={generating} variant="primary" size="sm">
              {generating ? (
                <><Loader2 size={14} className="animate-spin" /> {t.generating}</>
              ) : (
                <><Download size={14} /> {t.generateReport}</>
              )}
            </Button>
          </div>
        </div>
      </Card>

      {/* Score Overview */}
      <div className="grid md:grid-cols-4 gap-4 mb-8">
        <Card className="text-center">
          <div className="flex items-center justify-center mb-2">
            <ShieldCheck size={20} className="text-[#FFD700]" />
          </div>
          <p className="text-5xl font-extrabold font-mono" style={{ color: fw.score >= 80 ? "#10b981" : fw.score >= 60 ? "#f59e0b" : "#ef4444" }}>
            {fw.score}%
          </p>
          <p className="text-xs text-[#64748b] uppercase tracking-wider mt-2">{t.complianceScore}</p>
          <Badge variant={fw.score >= 80 ? "green" : fw.score >= 60 ? "yellow" : "red"} className="mt-2">
            {fw.score >= 80 ? t.compliant : fw.score >= 60 ? t.partial : t.nonCompliant}
          </Badge>
        </Card>
        <Card className="text-center">
          <p className="text-3xl font-extrabold font-mono text-emerald-400">{fw.controls_pass}</p>
          <p className="text-xs text-[#64748b] uppercase tracking-wider mt-1">{t.pass}</p>
        </Card>
        <Card className="text-center">
          <p className="text-3xl font-extrabold font-mono text-yellow-400">{fw.controls_partial}</p>
          <p className="text-xs text-[#64748b] uppercase tracking-wider mt-1">{t.partial}</p>
        </Card>
        <Card className="text-center">
          <p className="text-3xl font-extrabold font-mono text-red-400">{fw.controls_fail}</p>
          <p className="text-xs text-[#64748b] uppercase tracking-wider mt-1">{t.fail}</p>
        </Card>
      </div>

      {/* Score Bar */}
      <Card className="mb-6">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-medium">{fw.name} {t.overallScore}</span>
          <span className="font-mono font-bold" style={{ color: fw.score >= 80 ? "#10b981" : fw.score >= 60 ? "#f59e0b" : "#ef4444" }}>{fw.score}%</span>
        </div>
        <div className="w-full h-3 bg-white/5 rounded-full overflow-hidden">
          <div className="h-full rounded-full transition-all duration-700" style={{ width: `${fw.score}%`, backgroundColor: fw.score >= 80 ? "#10b981" : fw.score >= 60 ? "#f59e0b" : "#ef4444" }} />
        </div>
      </Card>

      {/* Controls List */}
      <Card>
        <h3 className="text-sm font-semibold text-[#94a3b8] uppercase tracking-wider mb-4">
          {t.controlsDetail} — {fw.name}
        </h3>
        <div className="space-y-2">
          {fw.controls.map((ctrl) => (
            <div
              key={ctrl.id}
              className={`flex items-start gap-3 p-4 rounded-xl border ${
                ctrl.status === "pass"
                  ? "bg-emerald-500/5 border-emerald-500/10"
                  : ctrl.status === "partial"
                    ? "bg-yellow-500/5 border-yellow-500/10"
                    : "bg-red-500/5 border-red-500/10"
              }`}
            >
              {statusIcon(ctrl.status)}
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-0.5">
                  <span className="font-mono text-xs text-[#64748b]">{ctrl.id}</span>
                  <span className="text-sm font-medium">{ctrl.name}</span>
                  <Badge variant={statusBadge(ctrl.status)}>{ctrl.status.toUpperCase()}</Badge>
                </div>
                <p className="text-xs text-[#94a3b8]">{ctrl.notes}</p>
              </div>
              {ctrl.status !== "pass" && (
                <button
                  type="button"
                  className="text-[#FFD700] hover:text-[#ffe44d] shrink-0"
                  aria-label={locale === "ja" ? "詳細を表示" : "View details"}
                >
                  <ExternalLink size={14} />
                </button>
              )}
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
