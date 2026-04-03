"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useEffect, useState } from "react";
import { Globe, Loader2, AlertTriangle, CheckCircle2, XCircle } from "lucide-react";
import { useLocale } from "@/lib/useLocale";
import { appDict } from "@/i18n/app-dict";

interface ExternalService {
  id: string;
  name: string;
  category: string;
  risk_level: "critical" | "high" | "medium" | "low";
  blast_radius_percent: number;
  monthly_downtime_minutes: number;
  fallback_available: boolean;
  sla_percent: number;
  dependent_components: string[];
  last_incident?: string;
}

interface ExternalImpactData {
  scan_date: string;
  total_services: number;
  unprotected_count: number;
  critical_count: number;
  avg_blast_radius: number;
  services: ExternalService[];
}

const DEMO_DATA: ExternalImpactData = {
  scan_date: "2026-04-01",
  total_services: 12,
  unprotected_count: 5,
  critical_count: 3,
  avg_blast_radius: 42.5,
  services: [
    { id: "ext-001", name: "AWS (Primary Cloud)", category: "Cloud Infrastructure", risk_level: "critical", blast_radius_percent: 100, monthly_downtime_minutes: 4.3, fallback_available: false, sla_percent: 99.99, dependent_components: ["All services"], last_incident: "2025-07-14" },
    { id: "ext-002", name: "Stripe Payments", category: "Payment Gateway", risk_level: "critical", blast_radius_percent: 85, monthly_downtime_minutes: 0.5, fallback_available: false, sla_percent: 99.99, dependent_components: ["Payment Service", "Subscription API", "Invoice Generator"] },
    { id: "ext-003", name: "Auth0 / Okta", category: "Identity Provider", risk_level: "critical", blast_radius_percent: 100, monthly_downtime_minutes: 1.2, fallback_available: false, sla_percent: 99.9, dependent_components: ["Auth Service", "API Gateway", "Admin Panel"], last_incident: "2025-12-03" },
    { id: "ext-004", name: "Cloudflare CDN", category: "CDN / DNS", risk_level: "high", blast_radius_percent: 75, monthly_downtime_minutes: 0.2, fallback_available: true, sla_percent: 99.99, dependent_components: ["Frontend", "Static Assets", "DNS Resolution"] },
    { id: "ext-005", name: "SendGrid / Email", category: "Email Service", risk_level: "high", blast_radius_percent: 40, monthly_downtime_minutes: 8.5, fallback_available: false, sla_percent: 99.95, dependent_components: ["Notification Service", "User Onboarding"], last_incident: "2026-01-22" },
    { id: "ext-006", name: "Datadog APM", category: "Monitoring", risk_level: "medium", blast_radius_percent: 30, monthly_downtime_minutes: 5.0, fallback_available: true, sla_percent: 99.9, dependent_components: ["Alerting", "Dashboards"] },
    { id: "ext-007", name: "GitHub Actions", category: "CI/CD", risk_level: "high", blast_radius_percent: 60, monthly_downtime_minutes: 15.3, fallback_available: false, sla_percent: 99.9, dependent_components: ["Deployment Pipeline", "Automated Tests"], last_incident: "2026-02-15" },
    { id: "ext-008", name: "Twilio SMS", category: "Messaging", risk_level: "medium", blast_radius_percent: 25, monthly_downtime_minutes: 2.1, fallback_available: true, sla_percent: 99.95, dependent_components: ["2FA Service", "Alert Notifications"] },
    { id: "ext-009", name: "Google Maps API", category: "Geolocation", risk_level: "low", blast_radius_percent: 15, monthly_downtime_minutes: 0.8, fallback_available: true, sla_percent: 99.9, dependent_components: ["Location Features"] },
    { id: "ext-010", name: "PagerDuty", category: "Incident Management", risk_level: "medium", blast_radius_percent: 35, monthly_downtime_minutes: 1.0, fallback_available: false, sla_percent: 99.9, dependent_components: ["On-Call Routing", "Escalations"] },
  ],
};

function riskColor(level: string): string {
  if (level === "critical") return "#ef4444";
  if (level === "high") return "#f59e0b";
  if (level === "medium") return "#eab308";
  return "#10b981";
}

function riskBadge(level: string): "red" | "yellow" | "green" | "default" {
  if (level === "critical") return "red";
  if (level === "high") return "yellow";
  if (level === "medium") return "default";
  return "green";
}

export default function ExternalImpactPage() {
  const [data, setData] = useState<ExternalImpactData>(DEMO_DATA);
  const [loading, setLoading] = useState(true);
  const [sortBy, setSortBy] = useState<"blast_radius" | "risk_level" | "downtime">("blast_radius");
  const locale = useLocale();
  const t = appDict.externalImpact[locale] ?? appDict.externalImpact.en;

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/proxy?path=/api/v1/external-impact", { signal: controller.signal })
      .then((r) => r.json())
      .then((d) => setData(d))
      .catch((err) => { console.error("[external-impact] API error, using demo data:", err); setData(DEMO_DATA); })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, []);

  const riskOrder = { critical: 4, high: 3, medium: 2, low: 1 };
  const sorted = [...data.services].sort((a, b) => {
    if (sortBy === "blast_radius") return b.blast_radius_percent - a.blast_radius_percent;
    if (sortBy === "risk_level") return riskOrder[b.risk_level] - riskOrder[a.risk_level];
    return b.monthly_downtime_minutes - a.monthly_downtime_minutes;
  });

  return (
    <div className="max-w-[1200px] mx-auto px-6 py-10">
      <div className="mb-10">
        <h1 className="text-2xl font-bold mb-1 flex items-center gap-3">
          <Globe size={24} className="text-[#FFD700]" />
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
              <p className="text-3xl font-extrabold font-mono text-[#94a3b8]">{data.total_services}</p>
              <p className="text-xs text-[#64748b] uppercase tracking-wider mt-1">{t.totalServices}</p>
            </Card>
            <Card className="text-center">
              <p className="text-3xl font-extrabold font-mono text-red-400">{data.critical_count}</p>
              <p className="text-xs text-[#64748b] uppercase tracking-wider mt-1">{t.critical}</p>
            </Card>
            <Card className="text-center">
              <p className="text-3xl font-extrabold font-mono text-[#f59e0b]">{data.unprotected_count}</p>
              <p className="text-xs text-[#64748b] uppercase tracking-wider mt-1">{t.unprotected}</p>
            </Card>
            <Card className="text-center">
              <p className="text-3xl font-extrabold font-mono text-[#FFD700]">{data.avg_blast_radius.toFixed(1)}%</p>
              <p className="text-xs text-[#64748b] uppercase tracking-wider mt-1">{t.avgBlast}</p>
            </Card>
          </div>

          {/* Sort */}
          <div className="flex items-center gap-2 mb-4">
            <span className="text-xs text-[#64748b] uppercase tracking-wider">{t.sortBy}</span>
            {(["blast_radius", "risk_level", "downtime"] as const).map((s) => (
              <button
                key={s}
                onClick={() => setSortBy(s)}
                className={`px-3 py-1 rounded-lg text-xs font-medium transition-all ${
                  sortBy === s
                    ? "bg-[#FFD700]/10 text-[#FFD700] border border-[#FFD700]/30"
                    : "text-[#94a3b8] border border-[#1e293b] hover:border-[#64748b]"
                }`}
              >
                {s.replace("_", " ").toUpperCase()}
              </button>
            ))}
          </div>

          {/* Services Table */}
          <Card>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[#1e293b]">
                    <th scope="col" className="text-left py-3 px-3 text-[#64748b] font-medium">{t.service}</th>
                    <th scope="col" className="text-left py-3 px-3 text-[#64748b] font-medium">{t.category}</th>
                    <th scope="col" className="text-center py-3 px-3 text-[#64748b] font-medium">{t.blastRadius}</th>
                    <th scope="col" className="text-center py-3 px-3 text-[#64748b] font-medium">{t.downtime}</th>
                    <th scope="col" className="text-center py-3 px-3 text-[#64748b] font-medium">SLA</th>
                    <th scope="col" className="text-center py-3 px-3 text-[#64748b] font-medium">{t.fallback}</th>
                    <th scope="col" className="text-center py-3 px-3 text-[#64748b] font-medium">{t.risk}</th>
                  </tr>
                </thead>
                <tbody>
                  {sorted.map((svc) => (
                    <tr key={svc.id} className="border-b border-[#1e293b]/50 hover:bg-white/[0.02]">
                      <td className="py-3 px-3">
                        <p className="font-medium">{svc.name}</p>
                        <p className="text-xs text-[#64748b] mt-0.5">
                          {svc.dependent_components.slice(0, 2).join(", ")}
                          {svc.dependent_components.length > 2 && ` +${svc.dependent_components.length - 2}`}
                        </p>
                      </td>
                      <td className="py-3 px-3 text-xs text-[#64748b]">{svc.category}</td>
                      <td className="py-3 px-3 text-center">
                        <div className="flex items-center justify-center gap-2">
                          <div className="w-16 h-2 bg-white/5 rounded-full overflow-hidden">
                            <div className="h-full rounded-full" style={{ width: `${svc.blast_radius_percent}%`, backgroundColor: riskColor(svc.risk_level) }} />
                          </div>
                          <span className="font-mono text-xs font-bold" style={{ color: riskColor(svc.risk_level) }}>
                            {svc.blast_radius_percent}%
                          </span>
                        </div>
                      </td>
                      <td className="py-3 px-3 text-center font-mono text-xs text-[#94a3b8]">
                        {svc.monthly_downtime_minutes.toFixed(1)} {locale === "ja" ? "分/月" : "min/mo"}
                      </td>
                      <td className="py-3 px-3 text-center font-mono text-xs text-[#94a3b8]">
                        {svc.sla_percent}%
                      </td>
                      <td className="py-3 px-3 text-center">
                        {svc.fallback_available ? (
                          <CheckCircle2 size={16} className="mx-auto text-emerald-400" />
                        ) : (
                          <XCircle size={16} className="mx-auto text-red-400" />
                        )}
                      </td>
                      <td className="py-3 px-3 text-center">
                        <div className="flex items-center justify-center gap-1">
                          <Badge variant={riskBadge(svc.risk_level)}>{svc.risk_level.toUpperCase()}</Badge>
                          {!svc.fallback_available && svc.risk_level !== "low" && (
                            <AlertTriangle size={12} className="text-red-400" />
                          )}
                        </div>
                      </td>
                    </tr>
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
