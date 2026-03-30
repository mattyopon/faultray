"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useEffect, useState } from "react";
import { api, type AttackSurfaceData } from "@/lib/api";
import { Shield, Loader2, Globe, Lock, AlertTriangle } from "lucide-react";
import { useLocale } from "@/lib/useLocale";
import { appDict } from "@/i18n/app-dict";

const DEMO_DATA: AttackSurfaceData = {
  summary: { total_components: 12, external_facing: 4, internal_only: 8, risk_level: "medium", attack_vectors: 7 },
  external_components: [
    { id: "cdn", name: "CDN / Edge", exposure: "public", ports: [80, 443], protocols: ["HTTP", "HTTPS"], risk_score: 35, vulnerabilities: [
      { type: "DDoS", severity: "medium", mitigation: "Rate limiting configured" },
      { type: "Cache poisoning", severity: "low", mitigation: "Cache-Control headers set" },
    ]},
    { id: "gateway", name: "API Gateway", exposure: "public", ports: [443], protocols: ["HTTPS"], risk_score: 45, vulnerabilities: [
      { type: "Injection attacks", severity: "high", mitigation: "Input validation in place" },
      { type: "Auth bypass", severity: "high", mitigation: "OAuth2 + PKCE configured" },
      { type: "Rate limit exhaustion", severity: "medium", mitigation: "Per-user rate limits" },
    ]},
    { id: "auth", name: "Auth Service", exposure: "semi-public", ports: [443], protocols: ["HTTPS"], risk_score: 55, vulnerabilities: [
      { type: "Brute force", severity: "medium", mitigation: "Account lockout after 5 attempts" },
      { type: "Session hijacking", severity: "high", mitigation: "Secure cookie flags set" },
    ]},
    { id: "dns", name: "DNS", exposure: "public", ports: [53], protocols: ["DNS", "DNSSEC"], risk_score: 25, vulnerabilities: [
      { type: "DNS spoofing", severity: "medium", mitigation: "DNSSEC enabled" },
    ]},
  ],
  internal_components: [
    { id: "api", name: "API Server", risk_score: 30 },
    { id: "worker", name: "Background Worker", risk_score: 15 },
    { id: "db_primary", name: "PostgreSQL Primary", risk_score: 60 },
    { id: "db_replica", name: "PostgreSQL Replica", risk_score: 25 },
    { id: "cache", name: "Redis Cache", risk_score: 40 },
    { id: "queue", name: "Message Queue", risk_score: 20 },
    { id: "storage", name: "Object Storage", risk_score: 15 },
    { id: "monitor", name: "Monitoring", risk_score: 10 },
  ],
  recommendations: [
    "Implement WAF before API Gateway",
    "Enable mutual TLS for internal communication",
    "Add network segmentation between data and app tiers",
    "Implement egress filtering",
    "Deploy IDS for database tier",
  ],
};

function severityColor(sev: string): string {
  switch (sev) {
    case "critical": return "#ef4444";
    case "high": return "#f59e0b";
    case "medium": return "#eab308";
    case "low": return "#10b981";
    default: return "#64748b";
  }
}

export default function SecurityPage() {
  const [data, setData] = useState<AttackSurfaceData>(DEMO_DATA);
  const [loading, setLoading] = useState(true);
  const locale = useLocale();
  const t = locale === "ja" ? appDict.security.ja : appDict.security.en;

  useEffect(() => {
    api
      .getAttackSurface()
      .then((result) => setData(result))
      .catch(() => setData(DEMO_DATA))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="max-w-[1200px] mx-auto px-6 py-10">
      <div className="mb-10">
        <h1 className="text-2xl font-bold mb-1 flex items-center gap-3">
          <Shield size={24} className="text-[#FFD700]" />
          {t.title}
        </h1>
        <p className="text-[#94a3b8] text-sm">{t.subtitle}</p>
      </div>

      {loading ? (
        <Card className="flex items-center justify-center py-20">
          <Loader2 size={24} className="animate-spin text-[#FFD700]" />
        </Card>
      ) : (
        <>
          {/* Summary */}
          <div className="grid md:grid-cols-4 gap-6 mb-8">
            <Card className="text-center">
              <Globe size={20} className="mx-auto mb-2 text-red-400" />
              <p className="text-3xl font-extrabold font-mono">{data.summary.external_facing}</p>
              <p className="text-xs text-[#64748b] uppercase tracking-wider">{t.external}</p>
            </Card>
            <Card className="text-center">
              <Lock size={20} className="mx-auto mb-2 text-emerald-400" />
              <p className="text-3xl font-extrabold font-mono">{data.summary.internal_only}</p>
              <p className="text-xs text-[#64748b] uppercase tracking-wider">{t.internal}</p>
            </Card>
            <Card className="text-center">
              <AlertTriangle size={20} className="mx-auto mb-2 text-[#FFD700]" />
              <p className="text-3xl font-extrabold font-mono">{data.summary.attack_vectors}</p>
              <p className="text-xs text-[#64748b] uppercase tracking-wider">{t.attackVectors}</p>
            </Card>
            <Card className="text-center">
              <Shield size={20} className="mx-auto mb-2 text-[#FFD700]" />
              <Badge variant={data.summary.risk_level === "high" ? "red" : data.summary.risk_level === "medium" ? "yellow" : "green"} className="text-base">
                {data.summary.risk_level.toUpperCase()}
              </Badge>
              <p className="text-xs text-[#64748b] uppercase tracking-wider mt-2">{t.riskLevel}</p>
            </Card>
          </div>

          {/* External Components */}
          <Card className="mb-6">
            <h3 className="text-lg font-bold mb-4 flex items-center gap-2">
              <Globe size={18} className="text-red-400" />
              {t.externalComponents}
            </h3>
            <div className="space-y-4">
              {data.external_components.map((comp) => (
                <div key={comp.id} className="p-4 rounded-xl border border-[#1e293b] bg-white/[0.02]">
                  <div className="flex items-center justify-between mb-3">
                    <div>
                      <p className="font-bold">{comp.name}</p>
                      <div className="flex items-center gap-2 mt-1">
                        <Badge variant="red">{comp.exposure}</Badge>
                        {comp.ports.map((p) => (
                          <span key={p} className="text-xs font-mono text-[#64748b]">:{p}</span>
                        ))}
                        {comp.protocols.map((p) => (
                          <Badge key={p} variant="default">{p}</Badge>
                        ))}
                      </div>
                    </div>
                    <div className="text-right">
                      <p className="text-2xl font-bold font-mono" style={{ color: comp.risk_score >= 50 ? "#f59e0b" : "#10b981" }}>
                        {comp.risk_score}
                      </p>
                      <p className="text-xs text-[#64748b]">{t.riskScore}</p>
                    </div>
                  </div>
                  <div className="space-y-2">
                    {comp.vulnerabilities.map((vuln, i) => (
                      <div key={i} className="flex items-center justify-between p-2 rounded-lg bg-white/[0.02]">
                        <div className="flex items-center gap-2">
                          <div className="w-2 h-2 rounded-full" style={{ backgroundColor: severityColor(vuln.severity) }} />
                          <span className="text-sm">{vuln.type}</span>
                          <Badge variant={vuln.severity === "high" ? "red" : vuln.severity === "medium" ? "yellow" : "green"}>
                            {vuln.severity}
                          </Badge>
                        </div>
                        <span className="text-xs text-[#64748b]">{vuln.mitigation}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </Card>

          <div className="grid lg:grid-cols-2 gap-6">
            {/* Internal Components */}
            <Card>
              <h3 className="text-lg font-bold mb-4 flex items-center gap-2">
                <Lock size={18} className="text-emerald-400" />
                {t.internalComponents}
              </h3>
              <div className="space-y-2">
                {data.internal_components.sort((a, b) => b.risk_score - a.risk_score).map((comp) => (
                  <div key={comp.id} className="flex items-center justify-between p-3 rounded-lg bg-white/[0.02]">
                    <span className="text-sm">{comp.name}</span>
                    <div className="flex items-center gap-2">
                      <div className="w-24 h-2 bg-white/5 rounded-full overflow-hidden">
                        <div
                          className="h-full rounded-full"
                          style={{
                            width: `${comp.risk_score}%`,
                            backgroundColor: comp.risk_score >= 50 ? "#f59e0b" : "#10b981",
                          }}
                        />
                      </div>
                      <span className="text-sm font-mono w-8 text-right">{comp.risk_score}</span>
                    </div>
                  </div>
                ))}
              </div>
            </Card>

            {/* Recommendations */}
            <Card>
              <h3 className="text-lg font-bold mb-4 flex items-center gap-2">
                <Shield size={18} className="text-[#FFD700]" />
                {t.recommendations}
              </h3>
              <div className="space-y-3">
                {data.recommendations.map((rec, i) => (
                  <div key={i} className="flex items-start gap-3 p-3 rounded-lg bg-[#FFD700]/5 border border-[#FFD700]/10">
                    <span className="text-sm font-bold text-[#FFD700] shrink-0">{i + 1}.</span>
                    <span className="text-sm text-[#94a3b8]">{rec}</span>
                  </div>
                ))}
              </div>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
