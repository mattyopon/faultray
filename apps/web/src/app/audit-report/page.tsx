"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useState, useRef } from "react";
import {
  FileSpreadsheet,
  Download,
  CheckCircle2,
  AlertTriangle,
  FileText,
  Shield,
  Link,
  Clock,
  Hash,
  Eye,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import { useLocale } from "@/lib/useLocale";

/* ============================================================
 * Types
 * ============================================================ */

type Framework = "SOC2" | "DORA" | "ISO27001" | "FISC";
type Format = "PDF" | "Excel" | "HTML";
type Severity = "critical" | "high" | "medium" | "low";

interface ReportSection {
  id: string;
  title: string;
  summary: string;
  expanded?: boolean;
}

interface Finding {
  id: string;
  title: string;
  severity: Severity;
  control: string;
  description: string;
  recommendation: string;
}

interface AuditTrailEntry {
  hash: string;
  timestamp: string;
  author: string;
  action: string;
  prevHash: string | null;
}

/* ============================================================
 * Demo Data
 * ============================================================ */

const REPORT_METADATA: Record<Framework, {
  name: string; period: string; type: string; score: number; status: string;
}> = {
  SOC2:    { name: "SOC 2 Type II", period: "2025-04-01 to 2026-03-31", type: "Attestation Report", score: 87, status: "Opinion Issued" },
  DORA:    { name: "DORA Compliance", period: "FY2026 Q1 Assessment", type: "Gap Assessment", score: 72, status: "Partial Compliance" },
  ISO27001:{ name: "ISO/IEC 27001", period: "Annual Surveillance Audit 2026", type: "Certification Audit", score: 91, status: "Certified" },
  FISC:    { name: "FISC 安全対策基準", period: "2026年度 定期評価", type: "Compliance Assessment", score: 65, status: "部分準拠" },
};

const SECTIONS: ReportSection[] = [
  {
    id: "exec",
    title: "Executive Summary",
    summary: "This report covers the assessment period April 1, 2025 through March 31, 2026. FaultRay Demo Organization has demonstrated a strong control environment with 87% of controls operating effectively. Three control deficiencies were identified, none of which constitute a material weakness.",
  },
  {
    id: "scope",
    title: "Scope & Objectives",
    summary: "The assessment covers all in-scope systems including: Production API (GCP us-central1), Database cluster (RDS PostgreSQL), Authentication service, and Monitoring infrastructure. Excluded from scope: legacy reporting system (decommission planned Q3 2026).",
  },
  {
    id: "findings",
    title: "Findings & Observations",
    summary: "3 findings were identified: 1 high-severity (access review not performed quarterly), 1 medium-severity (vendor contract lacks GDPR DPA addendum), 1 low-severity (log retention policy not formally documented). All findings have been acknowledged by management.",
  },
  {
    id: "evidence",
    title: "Evidence Summary",
    summary: "142 evidence artifacts collected across 9 control categories. Evidence types include: system-generated reports (63%), policy documents (24%), screenshots (8%), interview notes (5%). All artifacts stored in immutable evidence vault with SHA-256 hash chain.",
  },
  {
    id: "recommendations",
    title: "Recommendations",
    summary: "Priority 1: Implement automated quarterly access reviews by 2026-06-30. Priority 2: Execute DPA addenda with all EU-based processors by 2026-05-31. Priority 3: Formalize log retention policy document by 2026-04-30.",
  },
];

const DEMO_FINDINGS: Finding[] = [
  {
    id: "F-001",
    title: "Quarterly Access Reviews Not Performed",
    severity: "high",
    control: "CC6.2",
    description: "Access reviews for privileged accounts were performed annually rather than quarterly as required by the entity's access management policy and SOC2 CC6.2.",
    recommendation: "Implement automated quarterly access review workflows. Configure identity platform to auto-generate review tasks every 90 days.",
  },
  {
    id: "F-002",
    title: "Vendor DPA Addenda Missing",
    severity: "medium",
    control: "P8.1",
    description: "2 of 7 EU-based data processors do not have GDPR Data Processing Agreements on file, creating potential compliance exposure under GDPR Article 28.",
    recommendation: "Execute DPA addenda with remaining vendors. Establish a vendor onboarding checklist that requires DPA execution before data sharing.",
  },
  {
    id: "F-003",
    title: "Log Retention Policy Not Formally Documented",
    severity: "low",
    control: "A1.2",
    description: "Log retention periods are configured correctly in the system (90 days hot, 365 days archive), but no formal policy document exists to support this configuration.",
    recommendation: "Create a Log Management Policy document. Include retention periods, access controls, and review procedures.",
  },
];

const AUDIT_TRAIL: AuditTrailEntry[] = [
  { hash: "sha256:a8f2d3e9c1b4...", timestamp: "2026-04-01T09:00:00Z", author: "FaultRay System", action: "Report generated from evidence vault snapshot", prevHash: null },
  { hash: "sha256:7c4e9f1d2a8b...", timestamp: "2026-04-01T08:55:00Z", author: "Alice Chen",       action: "Evidence package finalized and sealed", prevHash: "sha256:3d1a8c2f5e9..." },
  { hash: "sha256:3d1a8c2f5e9b...", timestamp: "2026-03-28T17:30:00Z", author: "Bob Tanaka",       action: "Finding F-003 reviewed and accepted by management", prevHash: "sha256:9e2b7f4d1c3..." },
  { hash: "sha256:9e2b7f4d1c3a...", timestamp: "2026-03-25T14:15:00Z", author: "FaultRay System", action: "Control testing completed: 47 controls tested", prevHash: null },
];

/* ============================================================
 * Helpers
 * ============================================================ */

function severityVariant(sev: Severity): "green" | "yellow" | "red" | "default" {
  if (sev === "critical") return "red";
  if (sev === "high") return "red";
  if (sev === "medium") return "yellow";
  return "default";
}

function scoreColor(score: number): string {
  if (score >= 80) return "#10b981";
  if (score >= 60) return "#f59e0b";
  return "#ef4444";
}

/* ============================================================
 * Main Page
 * ============================================================ */

export default function AuditReportPage() {
  useLocale();

  // eslint-disable-next-line react-hooks/purity
  const reportSizeKb = useRef(Math.round(Math.random() * 200 + 150));
  const [selectedFramework, setSelectedFramework] = useState<Framework>("SOC2");
  const [selectedFormat, setSelectedFormat] = useState<Format>("PDF");
  const [isGenerating, setIsGenerating] = useState(false);
  const [generated, setGenerated] = useState(false);
  const [expandedSection, setExpandedSection] = useState<string | null>("exec");
  const [expandedFinding, setExpandedFinding] = useState<string | null>(null);

  const meta = REPORT_METADATA[selectedFramework];

  function handleGenerate() {
    setIsGenerating(true);
    setGenerated(false);
    setTimeout(() => {
      setIsGenerating(false);
      setGenerated(true);
    }, 1800);
  }

  return (
    <div className="w-full px-6 py-10">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold mb-1 flex items-center gap-3">
          <FileSpreadsheet size={24} className="text-[var(--gold)]" />
          Audit Report Generator
        </h1>
        <p className="text-[var(--text-secondary)] text-sm">
          Generate audit-ready reports for external auditors and regulators (Layer 4)
        </p>
      </div>

      <div className="grid lg:grid-cols-3 gap-6">
        {/* Configuration Panel */}
        <div className="lg:col-span-1">
          <Card className="sticky top-24">
            <h3 className="text-sm font-semibold text-[var(--text-secondary)] uppercase tracking-wider mb-4">Report Configuration</h3>

            {/* Framework */}
            <div className="mb-4">
              <label className="text-xs text-[var(--text-muted)] mb-2 block font-medium">Framework</label>
              <div className="grid grid-cols-2 gap-2">
                {(["SOC2", "DORA", "ISO27001", "FISC"] as Framework[]).map((fw) => (
                  <button
                    key={fw}
                    className={`px-3 py-2 rounded-lg text-sm font-medium border transition-colors ${
                      selectedFramework === fw
                        ? "bg-[var(--gold)]/10 border-[var(--gold)]/30 text-[var(--gold)]"
                        : "border-[var(--border-color)] text-[var(--text-muted)] hover:border-[var(--border-color)] hover:text-[var(--text-secondary)]"
                    }`}
                    onClick={() => { setSelectedFramework(fw); setGenerated(false); }}
                  >
                    {fw}
                  </button>
                ))}
              </div>
            </div>

            {/* Format */}
            <div className="mb-6">
              <label className="text-xs text-[var(--text-muted)] mb-2 block font-medium">Export Format</label>
              <div className="flex gap-2">
                {(["PDF", "Excel", "HTML"] as Format[]).map((fmt) => (
                  <button
                    key={fmt}
                    className={`flex-1 py-2 rounded-lg text-sm font-medium border transition-colors ${
                      selectedFormat === fmt
                        ? "bg-[var(--gold)]/10 border-[var(--gold)]/30 text-[var(--gold)]"
                        : "border-[var(--border-color)] text-[var(--text-muted)] hover:border-[var(--border-color)]"
                    }`}
                    onClick={() => setSelectedFormat(fmt)}
                  >
                    {fmt}
                  </button>
                ))}
              </div>
            </div>

            {/* Report Metadata Preview */}
            <div className="space-y-2 mb-6 p-3 rounded-xl bg-white/[0.02] border border-[var(--border-color)]">
              <div className="flex justify-between text-xs">
                <span className="text-[var(--text-muted)]">Framework</span>
                <span className="text-[#e2e8f0] font-medium">{meta.name}</span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-[var(--text-muted)]">Period</span>
                <span className="text-[var(--text-secondary)]">{meta.period.split(" ")[0]}…</span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-[var(--text-muted)]">Score</span>
                <span className="font-mono font-bold" style={{ color: scoreColor(meta.score) }}>{meta.score}%</span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-[var(--text-muted)]">Status</span>
                <Badge variant={meta.score >= 80 ? "green" : "yellow"} className="text-[10px]">{meta.status}</Badge>
              </div>
            </div>

            <Button
              className="w-full"
              disabled={isGenerating}
              onClick={handleGenerate}
            >
              {isGenerating ? (
                <>
                  <Clock size={14} className="animate-spin" />
                  Generating…
                </>
              ) : generated ? (
                <>
                  <Download size={14} />
                  Download {selectedFormat}
                </>
              ) : (
                <>
                  <FileSpreadsheet size={14} />
                  Generate Report
                </>
              )}
            </Button>

            {generated && (
              <p className="text-xs text-emerald-400 text-center mt-2 flex items-center justify-center gap-1">
                <CheckCircle2 size={11} />
                Report ready · {reportSizeKb.current} KB
              </p>
            )}
          </Card>
        </div>

        {/* Report Preview */}
        <div className="lg:col-span-2 space-y-4">
          {/* Report Header */}
          <Card className="border-[var(--gold)]/10">
            <div className="flex items-start gap-4">
              <div className="w-12 h-12 rounded-xl bg-[var(--gold)]/10 border border-[var(--gold)]/20 flex items-center justify-center shrink-0">
                <FileText size={20} className="text-[var(--gold)]" />
              </div>
              <div className="flex-1">
                <h2 className="text-lg font-bold text-[#e2e8f0] mb-1">{meta.name}</h2>
                <p className="text-sm text-[var(--text-muted)]">{meta.period}</p>
                <p className="text-xs text-[var(--text-muted)]">{meta.type} · Generated 2026-04-01 · FaultRay v2.14</p>
              </div>
              <div className="text-right">
                <p className="text-3xl font-extrabold font-mono" style={{ color: scoreColor(meta.score) }}>{meta.score}%</p>
                <Badge variant={meta.score >= 80 ? "green" : "yellow"}>{meta.status}</Badge>
              </div>
            </div>
          </Card>

          {/* Sections */}
          {SECTIONS.map((section) => {
            const isExpanded = expandedSection === section.id;
            return (
              <Card key={section.id}>
                <button
                  className="w-full text-left"
                  onClick={() => setExpandedSection(isExpanded ? null : section.id)}
                >
                  <div className="flex items-center gap-3">
                    {isExpanded
                      ? <ChevronDown size={14} className="text-[var(--text-muted)] shrink-0" />
                      : <ChevronRight size={14} className="text-[var(--text-muted)] shrink-0" />}
                    <span className="font-semibold text-[#e2e8f0]">{section.title}</span>
                    <Eye size={13} className="text-[var(--text-muted)] ml-auto" />
                  </div>
                </button>
                {isExpanded && (
                  <p className="mt-3 pt-3 border-t border-[var(--border-color)] text-sm text-[var(--text-secondary)] leading-relaxed">
                    {section.summary}
                  </p>
                )}
              </Card>
            );
          })}

          {/* Findings */}
          <Card>
            <h3 className="text-base font-bold mb-4 flex items-center gap-2">
              <AlertTriangle size={16} className="text-[var(--gold)]" />
              Findings ({DEMO_FINDINGS.length})
            </h3>
            <div className="space-y-3">
              {DEMO_FINDINGS.map((finding) => {
                const isExpanded = expandedFinding === finding.id;
                return (
                  <div
                    key={finding.id}
                    className={`p-4 rounded-xl border ${
                      finding.severity === "high" ? "bg-red-500/5 border-red-500/15"
                      : finding.severity === "medium" ? "bg-yellow-500/5 border-yellow-500/15"
                      : "bg-white/[0.02] border-[var(--border-color)]"
                    }`}
                  >
                    <button
                      className="w-full text-left"
                      onClick={() => setExpandedFinding(isExpanded ? null : finding.id)}
                    >
                      <div className="flex items-center gap-3 flex-wrap">
                        {isExpanded
                          ? <ChevronDown size={13} className="text-[var(--text-muted)]" />
                          : <ChevronRight size={13} className="text-[var(--text-muted)]" />}
                        <span className="font-mono text-xs text-[var(--text-muted)]">{finding.id}</span>
                        <Badge variant={severityVariant(finding.severity)}>{finding.severity.toUpperCase()}</Badge>
                        <span className="text-sm font-medium text-[#e2e8f0] flex-1">{finding.title}</span>
                        <span className="text-xs font-mono text-[var(--text-muted)]">{finding.control}</span>
                      </div>
                    </button>
                    {isExpanded && (
                      <div className="mt-3 pt-3 border-t border-white/5 space-y-2">
                        <p className="text-sm text-[var(--text-secondary)]">{finding.description}</p>
                        <p className="text-sm text-[var(--gold)] flex items-start gap-1">
                          <Shield size={12} className="shrink-0 mt-0.5" />
                          {finding.recommendation}
                        </p>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </Card>

          {/* Audit Trail */}
          <Card>
            <h3 className="text-base font-bold mb-4 flex items-center gap-2">
              <Hash size={16} className="text-[var(--gold)]" />
              Audit Trail — Hash Chain Integrity
            </h3>
            <div className="space-y-2">
              {AUDIT_TRAIL.map((entry, i) => (
                <div key={i} className="flex items-start gap-3 p-3 rounded-lg bg-white/[0.02] border border-[var(--border-color)]">
                  <div className="flex flex-col items-center shrink-0">
                    <div className="w-2 h-2 rounded-full bg-emerald-400 mt-1.5" />
                    {i < AUDIT_TRAIL.length - 1 && <div className="w-0.5 h-6 bg-[var(--border-color)] mt-1" />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap mb-0.5">
                      <span className="text-xs font-mono text-emerald-400">{entry.hash.slice(0, 22)}…</span>
                      {entry.prevHash && (
                        <span className="flex items-center gap-1 text-[10px] text-[var(--text-muted)]">
                          <Link size={9} />
                          ← {entry.prevHash.slice(0, 16)}…
                        </span>
                      )}
                    </div>
                    <p className="text-sm text-[var(--text-secondary)]">{entry.action}</p>
                    <p className="text-xs text-[var(--text-muted)]">{entry.author} · {new Date(entry.timestamp).toLocaleString()}</p>
                  </div>
                  <CheckCircle2 size={13} className="text-emerald-400 shrink-0 mt-1" />
                </div>
              ))}
            </div>
            <p className="text-xs text-[var(--text-muted)] mt-3 border-t border-[var(--border-color)] pt-3">
              All entries are cryptographically linked (SHA-256). Chain integrity verified: <span className="text-emerald-400">VALID</span>
            </p>
          </Card>
        </div>
      </div>
    </div>
  );
}
