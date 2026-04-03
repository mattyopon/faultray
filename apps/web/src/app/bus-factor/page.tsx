"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useEffect, useState } from "react";
import { Users, Loader2, AlertTriangle, UserX } from "lucide-react";
import { useLocale } from "@/lib/useLocale";
import { appDict } from "@/i18n/app-dict";

interface PersonRisk {
  id: string;
  name: string;
  role: string;
  risk_score: number;
  managed_components: string[];
  impact_if_leaves: "critical" | "high" | "medium" | "low";
  single_point: boolean;
  days_since_vacation: number;
}

interface UnownedComponent {
  id: string;
  name: string;
  type: string;
  criticality: "critical" | "high" | "medium" | "low";
}

interface BusFactorData {
  bus_factor: number;
  risk_score: number;
  total_people: number;
  single_point_count: number;
  unowned_count: number;
  people: PersonRisk[];
  unowned_components: UnownedComponent[];
}

const DEMO_DATA: BusFactorData = {
  bus_factor: 2,
  risk_score: 68,
  total_people: 12,
  single_point_count: 4,
  unowned_count: 5,
  people: [
    { id: "p-001", name: "Alice Chen", role: "Lead SRE", risk_score: 92, managed_components: ["PostgreSQL Primary", "Redis Cluster", "Backup Pipeline", "Monitoring Stack"], impact_if_leaves: "critical", single_point: true, days_since_vacation: 180 },
    { id: "p-002", name: "Bob Tanaka", role: "Platform Engineer", risk_score: 85, managed_components: ["Kubernetes Control Plane", "CI/CD Pipeline", "Secrets Manager"], impact_if_leaves: "critical", single_point: true, days_since_vacation: 92 },
    { id: "p-003", name: "Carol Smith", role: "Backend Lead", risk_score: 74, managed_components: ["Auth Service", "Payment Service", "API Gateway Config"], impact_if_leaves: "high", single_point: true, days_since_vacation: 45 },
    { id: "p-004", name: "David Lee", role: "Security Engineer", risk_score: 71, managed_components: ["WAF Rules", "Certificate Management", "Audit Log System"], impact_if_leaves: "high", single_point: true, days_since_vacation: 210 },
    { id: "p-005", name: "Emma Müller", role: "Frontend Lead", risk_score: 45, managed_components: ["CDN Config", "Static Assets Pipeline"], impact_if_leaves: "medium", single_point: false, days_since_vacation: 30 },
    { id: "p-006", name: "Frank Nakamura", role: "DevOps Engineer", risk_score: 38, managed_components: ["Terraform Modules", "Alerting Rules"], impact_if_leaves: "medium", single_point: false, days_since_vacation: 60 },
  ],
  unowned_components: [
    { id: "uc-001", name: "legacy-billing-adapter", type: "app_server", criticality: "critical" },
    { id: "uc-002", name: "data-export-cron", type: "worker", criticality: "high" },
    { id: "uc-003", name: "email-bounce-handler", type: "worker", criticality: "medium" },
    { id: "uc-004", name: "metrics-archive-db", type: "database", criticality: "high" },
    { id: "uc-005", name: "staging-load-balancer", type: "load_balancer", criticality: "low" },
  ],
};

function impactColor(level: string): string {
  if (level === "critical") return "#ef4444";
  if (level === "high") return "#f59e0b";
  if (level === "medium") return "#eab308";
  return "#10b981";
}

function impactBadge(level: string): "red" | "yellow" | "green" | "default" {
  if (level === "critical") return "red";
  if (level === "high") return "yellow";
  if (level === "medium") return "default";
  return "green";
}

export default function BusFactorPage() {
  const [data, setData] = useState<BusFactorData>(DEMO_DATA);
  const [loading, setLoading] = useState(true);
  const locale = useLocale();
  const t = appDict.busFactor[locale] ?? appDict.busFactor.en;

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/proxy?path=/api/v1/bus-factor", { signal: controller.signal })
      .then((r) => r.json())
      .then((d) => setData(d))
      .catch((err) => { console.error("[bus-factor] API error, using demo data:", err); setData(DEMO_DATA); })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, []);

  const sorted = [...data.people].sort((a, b) => b.risk_score - a.risk_score);

  return (
    <div className="w-full px-6 py-10">
      <div className="mb-10">
        <h1 className="text-2xl font-bold mb-1 flex items-center gap-3">
          <Users size={24} className="text-[var(--gold)]" />
          {t.title}
        </h1>
        <p className="text-[var(--text-secondary)] text-sm">{t.subtitle}</p>
      </div>

      {loading ? (
        <Card className="flex items-center justify-center py-20">
          <Loader2 size={24} className="animate-spin text-[var(--gold)]" />
          <span className="ml-3 text-[var(--text-secondary)]">{t.loading}</span>
        </Card>
      ) : (
        <>
          {/* Summary */}
          <div className="grid md:grid-cols-4 gap-4 mb-8">
            <Card className="text-center">
              <p className="text-5xl font-extrabold font-mono" style={{ color: data.bus_factor <= 2 ? "#ef4444" : data.bus_factor <= 3 ? "#f59e0b" : "#10b981" }}>
                {data.bus_factor}
              </p>
              <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider mt-2">{t.busFactor}</p>
              <Badge variant={data.bus_factor <= 2 ? "red" : data.bus_factor <= 3 ? "yellow" : "green"} className="mt-2">
                {data.bus_factor <= 2 ? t.critical : data.bus_factor <= 3 ? t.risky : t.healthy}
              </Badge>
            </Card>
            <Card className="text-center">
              <p className="text-3xl font-extrabold font-mono" style={{ color: data.risk_score >= 70 ? "#ef4444" : data.risk_score >= 50 ? "#f59e0b" : "#10b981" }}>
                {data.risk_score}
              </p>
              <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider mt-1">{t.riskScore}</p>
            </Card>
            <Card className="text-center">
              <p className="text-3xl font-extrabold font-mono text-red-400">{data.single_point_count}</p>
              <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider mt-1">{t.singlePoints}</p>
            </Card>
            <Card className="text-center">
              <p className="text-3xl font-extrabold font-mono text-[#f59e0b]">{data.unowned_count}</p>
              <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider mt-1">{t.unownedComponents}</p>
            </Card>
          </div>

          <div className="grid lg:grid-cols-[1fr_360px] gap-6">
            {/* People Risk Table */}
            <Card>
              <h3 className="text-sm font-semibold text-[var(--text-secondary)] uppercase tracking-wider mb-4">
                {t.peopleRisk}
              </h3>
              <div className="space-y-3">
                {sorted.map((person) => (
                  <div key={person.id} className="p-4 rounded-xl border border-[var(--border-color)] hover:bg-white/[0.02]">
                    <div className="flex items-start justify-between mb-2">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-semibold">{person.name}</span>
                          {person.single_point && (
                            <Badge variant="red">
                              <AlertTriangle size={10} className="mr-1" />
                              {t.spof}
                            </Badge>
                          )}
                        </div>
                        <p className="text-xs text-[var(--text-muted)] mt-0.5">{person.role}</p>
                      </div>
                      <div className="text-right">
                        <span className="text-xl font-bold font-mono" style={{ color: impactColor(person.impact_if_leaves) }}>
                          {person.risk_score}
                        </span>
                        <p className="text-xs text-[var(--text-muted)]">{t.riskScore}</p>
                      </div>
                    </div>
                    <div className="flex items-center justify-between mt-2">
                      <div className="flex flex-wrap gap-1">
                        {person.managed_components.slice(0, 3).map((comp) => (
                          <span key={comp} className="text-xs bg-white/5 px-2 py-0.5 rounded-full text-[var(--text-secondary)]">
                            {comp}
                          </span>
                        ))}
                        {person.managed_components.length > 3 && (
                          <span className="text-xs text-[var(--text-muted)]">+{person.managed_components.length - 3}</span>
                        )}
                      </div>
                      <div className="flex items-center gap-2 shrink-0 ml-2">
                        <Badge variant={impactBadge(person.impact_if_leaves)}>
                          {person.impact_if_leaves.toUpperCase()}
                        </Badge>
                        {person.days_since_vacation > 120 && (
                          <span className="text-xs text-red-400">{person.days_since_vacation}d {locale === "ja" ? "有休なし" : "no PTO"}</span>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </Card>

            {/* Unowned Components */}
            <div className="space-y-6">
              <Card>
                <h3 className="text-sm font-semibold text-[var(--text-secondary)] uppercase tracking-wider mb-4 flex items-center gap-2">
                  <UserX size={16} className="text-red-400" />
                  {t.unownedTitle}
                </h3>
                <div className="space-y-2">
                  {data.unowned_components.map((comp) => (
                    <div key={comp.id} className="flex items-center justify-between p-3 rounded-lg bg-white/[0.02] border border-[var(--border-color)]">
                      <div>
                        <p className="text-sm font-medium">{comp.name}</p>
                        <p className="text-xs text-[var(--text-muted)]">{comp.type}</p>
                      </div>
                      <Badge variant={impactBadge(comp.criticality)}>
                        {comp.criticality.toUpperCase()}
                      </Badge>
                    </div>
                  ))}
                </div>
              </Card>

              <Card>
                <h3 className="text-sm font-semibold text-[var(--text-secondary)] uppercase tracking-wider mb-3">{t.recommendation}</h3>
                <div className="space-y-2">
                  {[
                    locale === "ja" ? "クリティカルコンポーネントに副担当者を設定する" : "Assign a backup owner for all critical components",
                    locale === "ja" ? "重要なシステムのドキュメントをWikiに整備する" : "Document institutional knowledge for single-point owners",
                    locale === "ja" ? "バスファクター 3 以上を目標に体制を見直す" : "Target Bus Factor ≥ 3 for all critical paths",
                    locale === "ja" ? "有休消化率を改善しバーンアウトを防ぐ" : "Improve vacation coverage to reduce burnout risk",
                  ].map((rec, i) => (
                    <div key={i} className="flex items-start gap-2 text-xs text-[var(--text-secondary)]">
                      <span className="text-[var(--gold)] shrink-0">{i + 1}.</span>
                      <span>{rec}</span>
                    </div>
                  ))}
                </div>
              </Card>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
