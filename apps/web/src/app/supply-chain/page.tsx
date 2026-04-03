"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PackageSearch, AlertTriangle, CheckCircle2, RefreshCw } from "lucide-react";
import { useLocale } from "@/lib/useLocale";
import { appDict } from "@/i18n/app-dict";

const DEMO_DEPS = [
  { name: "next", version: "15.1.3", riskScore: 2, cve: null, patchStatus: "patched", license: "MIT", vendor: "Vercel" },
  { name: "react", version: "18.3.1", riskScore: 1, cve: null, patchStatus: "patched", license: "MIT", vendor: "Meta" },
  { name: "lodash", version: "4.17.19", riskScore: 72, cve: "CVE-2024-12345", patchStatus: "pending", license: "MIT", vendor: "Community" },
  { name: "axios", version: "1.6.2", riskScore: 35, cve: null, patchStatus: "patched", license: "MIT", vendor: "Community" },
  { name: "jsonwebtoken", version: "8.5.1", riskScore: 88, cve: "CVE-2025-11101", patchStatus: "pending", license: "MIT", vendor: "Auth0" },
  { name: "express", version: "4.18.2", riskScore: 15, cve: null, patchStatus: "patched", license: "MIT", vendor: "OpenJS" },
  { name: "pg", version: "8.11.3", riskScore: 8, cve: null, patchStatus: "patched", license: "MIT", vendor: "Community" },
  { name: "sharp", version: "0.32.6", riskScore: 20, cve: null, patchStatus: "patched", license: "Apache-2.0", vendor: "lovell" },
  { name: "zod", version: "3.22.4", riskScore: 3, cve: null, patchStatus: "patched", license: "MIT", vendor: "Community" },
  { name: "typescript", version: "5.3.3", riskScore: 5, cve: null, patchStatus: "patched", license: "Apache-2.0", vendor: "Microsoft" },
];

const DEMO_ADVISORIES = [
  {
    id: "CVE-2025-11101",
    package: "jsonwebtoken",
    severity: "critical",
    title: "JWT Algorithm Confusion Attack allows forging of tokens",
    publishedAt: "2026-03-15",
    patchVersion: "9.0.0",
  },
  {
    id: "CVE-2024-12345",
    package: "lodash",
    severity: "high",
    title: "Prototype pollution via merge() function with malicious input",
    publishedAt: "2026-02-28",
    patchVersion: "4.17.21",
  },
];

function RiskBar({ score }: { score: number }) {
  const color = score >= 70 ? "#ef4444" : score >= 40 ? "#f59e0b" : "#10b981";
  return (
    <div className="flex items-center gap-2">
      <div className="w-20 h-1.5 bg-[#1e293b] rounded-full overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${Math.min(score, 100)}%`, backgroundColor: color }} />
      </div>
      <span className="text-xs font-mono" style={{ color }}>{score}</span>
    </div>
  );
}

export default function SupplyChainPage() {
  const locale = useLocale();
  const t = appDict.supplyChain[locale] ?? appDict.supplyChain.en;

  const vulnCount = DEMO_DEPS.filter((d) => d.cve).length;
  const criticalCount = DEMO_ADVISORIES.filter((a) => a.severity === "critical").length;
  const highCount = DEMO_ADVISORIES.filter((a) => a.severity === "high").length;

  return (
    <div className="max-w-[1200px] mx-auto px-6 py-10">
      <div className="flex items-start justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold mb-1 flex items-center gap-3">
            <PackageSearch size={24} className="text-[#FFD700]" />
            {t.title}
          </h1>
          <p className="text-[#94a3b8] text-sm">{t.subtitle}</p>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          <span className="text-xs text-[#64748b]">{t.lastScan}: 2026-04-01 08:00 UTC</span>
          <Button size="sm" className="flex items-center gap-2">
            <RefreshCw size={14} />
            {t.scanNow}
          </Button>
        </div>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-8">
        <Card className="text-center">
          <p className="text-3xl font-extrabold font-mono">{DEMO_DEPS.length}</p>
          <p className="text-xs text-[#64748b] uppercase tracking-wider mt-1">{t.totalDeps}</p>
        </Card>
        <Card className="text-center">
          <p className="text-3xl font-extrabold font-mono text-[#f59e0b]">{vulnCount}</p>
          <p className="text-xs text-[#64748b] uppercase tracking-wider mt-1">{t.vulnerabilities}</p>
        </Card>
        <Card className="text-center">
          <p className="text-3xl font-extrabold font-mono text-red-400">{criticalCount}</p>
          <p className="text-xs text-[#64748b] uppercase tracking-wider mt-1">{t.critical}</p>
        </Card>
        <Card className="text-center">
          <p className="text-3xl font-extrabold font-mono text-[#f97316]">{highCount}</p>
          <p className="text-xs text-[#64748b] uppercase tracking-wider mt-1">{t.high}</p>
        </Card>
        <Card className="text-center">
          <p className="text-3xl font-extrabold font-mono text-[#10b981]">
            {DEMO_DEPS.filter((d) => !d.cve).length}
          </p>
          <p className="text-xs text-[#64748b] uppercase tracking-wider mt-1">Clean</p>
        </Card>
      </div>

      {/* Recent CVE Advisories */}
      <Card className="mb-6">
        <p className="text-sm font-semibold text-[#FFD700] mb-4">{t.recentAdvisories}</p>
        <div className="space-y-3">
          {DEMO_ADVISORIES.map((adv) => (
            <div key={adv.id} className="flex items-start gap-3 bg-[#0a0e1a] rounded-lg p-3">
              <AlertTriangle size={16} className={adv.severity === "critical" ? "text-red-400 shrink-0 mt-0.5" : "text-[#f59e0b] shrink-0 mt-0.5"} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-mono text-xs text-[#64748b]">{adv.id}</span>
                  <Badge variant={adv.severity === "critical" ? "red" : "yellow"}>{adv.severity}</Badge>
                  <Badge variant="default">{adv.package}</Badge>
                </div>
                <p className="text-sm mt-1">{adv.title}</p>
                <p className="text-xs text-[#64748b] mt-0.5">Published: {adv.publishedAt} · Fix: v{adv.patchVersion}</p>
              </div>
            </div>
          ))}
        </div>
      </Card>

      {/* Dependency table */}
      <Card>
        <p className="text-sm font-semibold text-[#FFD700] mb-4">Dependency Inventory</p>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-[#64748b] text-xs uppercase tracking-wider border-b border-[#1e293b]">
                <th scope="col" className="text-left py-2 pr-4">{t.dependency}</th>
                <th scope="col" className="text-left py-2 pr-4">{t.version}</th>
                <th scope="col" className="text-left py-2 pr-4">{t.vendor}</th>
                <th scope="col" className="text-left py-2 pr-4">{t.license}</th>
                <th scope="col" className="text-left py-2 pr-4">{t.riskScore}</th>
                <th scope="col" className="text-left py-2 pr-4">{t.cveId}</th>
                <th scope="col" className="text-left py-2">{t.patchStatus}</th>
              </tr>
            </thead>
            <tbody>
              {DEMO_DEPS.map((dep) => (
                <tr key={dep.name} className="border-b border-[#1e293b]/50 hover:bg-white/2">
                  <td className="py-2.5 pr-4 font-mono font-semibold">{dep.name}</td>
                  <td className="py-2.5 pr-4 font-mono text-[#94a3b8]">{dep.version}</td>
                  <td className="py-2.5 pr-4 text-[#94a3b8]">{dep.vendor}</td>
                  <td className="py-2.5 pr-4 text-[#64748b] text-xs">{dep.license}</td>
                  <td className="py-2.5 pr-4"><RiskBar score={dep.riskScore} /></td>
                  <td className="py-2.5 pr-4">
                    {dep.cve ? (
                      <span className="font-mono text-xs text-red-400">{dep.cve}</span>
                    ) : (
                      <span className="text-[#475569] text-xs">—</span>
                    )}
                  </td>
                  <td className="py-2.5">
                    {dep.patchStatus === "patched" ? (
                      <div className="flex items-center gap-1 text-[#10b981]">
                        <CheckCircle2 size={12} />
                        <span className="text-xs">{t.patched}</span>
                      </div>
                    ) : (
                      <Badge variant="yellow">{t.pending}</Badge>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
