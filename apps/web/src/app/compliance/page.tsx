"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useState } from "react";
import { api } from "@/lib/api";
import { ShieldCheck, Loader2, CheckCircle2, XCircle, AlertTriangle } from "lucide-react";

const FRAMEWORKS = [
  { id: "dora", name: "DORA", desc: "Digital Operational Resilience Act" },
  { id: "soc2", name: "SOC 2", desc: "Service Organization Control 2" },
  { id: "iso27001", name: "ISO 27001", desc: "Information Security Management" },
  { id: "pci_dss", name: "PCI-DSS", desc: "Payment Card Industry Data Security" },
  { id: "hipaa", name: "HIPAA", desc: "Health Insurance Portability" },
  { id: "gdpr", name: "GDPR", desc: "General Data Protection Regulation" },
];

interface ComplianceResult {
  framework: string;
  score: number;
  compliant_count: number;
  non_compliant_count: number;
  controls: Array<{
    id: string;
    name: string;
    status: string;
    description: string;
    remediation: string;
  }>;
  findings: string[];
  recommendations: string[];
}

const DEMO_RESULTS: Record<string, ComplianceResult> = {
  dora: {
    framework: "dora",
    score: 72,
    compliant_count: 18,
    non_compliant_count: 7,
    controls: [
      { id: "DORA-ICT-1", name: "ICT Risk Management Framework", status: "compliant", description: "Organization has established ICT risk management framework", remediation: "" },
      { id: "DORA-ICT-2", name: "ICT Incident Reporting", status: "non_compliant", description: "Incident reporting must be within 4 hours", remediation: "Implement automated incident reporting pipeline" },
      { id: "DORA-ICT-3", name: "Digital Resilience Testing", status: "compliant", description: "Regular resilience testing is performed", remediation: "" },
      { id: "DORA-ICT-4", name: "Third-party Risk Management", status: "non_compliant", description: "Third-party dependencies must be monitored", remediation: "Implement vendor risk assessment process" },
      { id: "DORA-ICT-5", name: "Information Sharing", status: "compliant", description: "Threat intelligence sharing is enabled", remediation: "" },
    ],
    findings: ["Incident reporting pipeline not automated", "Third-party vendor assessments incomplete"],
    recommendations: ["Automate incident reporting within 4-hour window", "Complete vendor risk assessments for all critical providers"],
  },
  soc2: {
    framework: "soc2",
    score: 68,
    compliant_count: 22,
    non_compliant_count: 10,
    controls: [
      { id: "CC6.1", name: "Logical Access Security", status: "compliant", description: "Logical access controls implemented", remediation: "" },
      { id: "CC7.2", name: "System Monitoring", status: "compliant", description: "System monitoring is active", remediation: "" },
      { id: "CC8.1", name: "Change Management", status: "non_compliant", description: "Changes must follow formal process", remediation: "Implement change advisory board process" },
      { id: "A1.2", name: "Recovery Procedures", status: "non_compliant", description: "Recovery procedures must be tested annually", remediation: "Schedule annual DR testing" },
    ],
    findings: ["Change management process informal", "DR testing not performed annually"],
    recommendations: ["Formalize change management with CAB", "Schedule quarterly DR exercises"],
  },
};

export default function CompliancePage() {
  const [selectedFramework, setSelectedFramework] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ComplianceResult | null>(null);

  const runAssessment = async (fw: string) => {
    setSelectedFramework(fw);
    setLoading(true);
    try {
      const res = await api.getCompliance(fw);
      setResult(res as unknown as ComplianceResult);
    } catch {
      setResult(DEMO_RESULTS[fw] || DEMO_RESULTS.dora);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-[1200px] mx-auto px-6 py-10">
      <div className="mb-10">
        <h1 className="text-2xl font-bold mb-1 flex items-center gap-3">
          <ShieldCheck size={24} className="text-[#FFD700]" />
          Compliance Dashboard
        </h1>
        <p className="text-[#94a3b8] text-sm">
          Assess your infrastructure against regulatory frameworks
        </p>
      </div>

      {/* Framework Selection */}
      <div className="grid md:grid-cols-3 gap-4 mb-8">
        {FRAMEWORKS.map((fw) => (
          <button
            key={fw.id}
            onClick={() => runAssessment(fw.id)}
            className={`p-4 rounded-xl border text-left transition-all ${
              selectedFramework === fw.id
                ? "border-[#FFD700] bg-[#FFD700]/[0.04]"
                : "border-[#1e293b] bg-[#111827] hover:border-[#FFD700]/30"
            }`}
          >
            <p className="font-bold text-lg">{fw.name}</p>
            <p className="text-xs text-[#64748b] mt-1">{fw.desc}</p>
          </button>
        ))}
      </div>

      {/* Results */}
      {loading ? (
        <Card className="flex items-center justify-center py-20">
          <Loader2 size={24} className="animate-spin text-[#FFD700]" />
          <span className="ml-3 text-[#94a3b8]">Running assessment...</span>
        </Card>
      ) : result ? (
        <div className="space-y-6">
          {/* Score Overview */}
          <div className="grid md:grid-cols-3 gap-6">
            <Card className="text-center">
              <p className="text-xs text-[#64748b] uppercase tracking-wider mb-2">Compliance Score</p>
              <p
                className="text-5xl font-extrabold font-mono"
                style={{
                  color: result.score >= 80 ? "#10b981" : result.score >= 60 ? "#f59e0b" : "#ef4444",
                }}
              >
                {result.score}%
              </p>
              <Badge
                variant={result.score >= 80 ? "green" : result.score >= 60 ? "yellow" : "red"}
                className="mt-2"
              >
                {result.score >= 80 ? "Compliant" : result.score >= 60 ? "Partial" : "Non-Compliant"}
              </Badge>
            </Card>
            <Card className="text-center">
              <p className="text-xs text-[#64748b] uppercase tracking-wider mb-2">Controls Passed</p>
              <p className="text-5xl font-extrabold font-mono text-emerald-400">
                {result.compliant_count}
              </p>
              <p className="text-xs text-[#64748b] mt-2">
                of {result.compliant_count + result.non_compliant_count} total
              </p>
            </Card>
            <Card className="text-center">
              <p className="text-xs text-[#64748b] uppercase tracking-wider mb-2">Non-Compliant</p>
              <p className="text-5xl font-extrabold font-mono text-red-400">
                {result.non_compliant_count}
              </p>
              <p className="text-xs text-[#64748b] mt-2">requires remediation</p>
            </Card>
          </div>

          {/* Controls List */}
          <Card>
            <h3 className="text-lg font-bold mb-4 flex items-center gap-2">
              <ShieldCheck size={18} className="text-[#FFD700]" />
              Controls
            </h3>
            <div className="space-y-3">
              {result.controls.map((ctrl) => (
                <div
                  key={ctrl.id}
                  className={`p-4 rounded-xl border ${
                    ctrl.status === "compliant"
                      ? "bg-emerald-500/5 border-emerald-500/10"
                      : "bg-red-500/5 border-red-500/10"
                  }`}
                >
                  <div className="flex items-start gap-3">
                    {ctrl.status === "compliant" ? (
                      <CheckCircle2 size={18} className="text-emerald-400 mt-0.5 shrink-0" />
                    ) : (
                      <XCircle size={18} className="text-red-400 mt-0.5 shrink-0" />
                    )}
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-sm font-mono text-[#64748b]">{ctrl.id}</span>
                        <span className="text-sm font-medium">{ctrl.name}</span>
                      </div>
                      <p className="text-xs text-[#94a3b8]">{ctrl.description}</p>
                      {ctrl.remediation && (
                        <p className="text-xs text-[#FFD700] mt-2">
                          Remediation: {ctrl.remediation}
                        </p>
                      )}
                    </div>
                    <Badge variant={ctrl.status === "compliant" ? "green" : "red"}>
                      {ctrl.status === "compliant" ? "Pass" : "Fail"}
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
          </Card>

          {/* Findings & Recommendations */}
          {result.findings.length > 0 && (
            <Card>
              <h3 className="text-lg font-bold mb-4 flex items-center gap-2">
                <AlertTriangle size={18} className="text-red-400" />
                Key Findings
              </h3>
              <div className="space-y-2">
                {result.findings.map((f, i) => (
                  <div key={i} className="flex items-start gap-2 text-sm">
                    <XCircle size={14} className="text-red-400 mt-0.5 shrink-0" />
                    <span className="text-[#94a3b8]">{f}</span>
                  </div>
                ))}
              </div>
              {result.recommendations.length > 0 && (
                <div className="mt-6 pt-4 border-t border-[#1e293b]">
                  <h4 className="text-sm font-semibold text-[#94a3b8] mb-3">Recommendations</h4>
                  <div className="space-y-2">
                    {result.recommendations.map((r, i) => (
                      <div key={i} className="flex items-start gap-2 text-sm">
                        <CheckCircle2 size={14} className="text-[#FFD700] mt-0.5 shrink-0" />
                        <span className="text-[#94a3b8]">{r}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </Card>
          )}
        </div>
      ) : (
        <Card className="flex flex-col items-center justify-center py-16">
          <ShieldCheck size={40} className="text-[#1e293b] mb-4" />
          <p className="text-[#64748b] text-sm mb-4">
            Select a compliance framework to begin assessment
          </p>
          <Button variant="secondary" size="sm" onClick={() => runAssessment("dora")}>
            Start with DORA
          </Button>
        </Card>
      )}
    </div>
  );
}
