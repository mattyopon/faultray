"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useState } from "react";
import { Gauge, DollarSign, TrendingDown, CheckCircle2 } from "lucide-react";
import { useLocale } from "@/lib/useLocale";
import { appDict } from "@/i18n/app-dict";

type RecoCategory = "right-sizing" | "idle" | "reserved";
type Effort = "low" | "medium" | "high";

const RECOMMENDATIONS: {
  id: string;
  category: RecoCategory;
  resource: string;
  type: string;
  currentSpec: string;
  suggestedSpec: string;
  monthlySaving: number;
  effort: Effort;
  reason: string;
}[] = [
  {
    id: "OPT-001",
    category: "right-sizing",
    resource: "api-server-prod",
    type: "EC2 Instance",
    currentSpec: "m5.2xlarge (8 vCPU, 32GB)",
    suggestedSpec: "m5.xlarge (4 vCPU, 16GB)",
    monthlySaving: 280,
    effort: "low",
    reason: "Average CPU utilization is 22% over the last 30 days. Memory peaks at 45%.",
  },
  {
    id: "OPT-002",
    category: "right-sizing",
    resource: "worker-batch-jobs",
    type: "ECS Task",
    currentSpec: "4 vCPU, 8GB memory",
    suggestedSpec: "2 vCPU, 4GB memory",
    monthlySaving: 190,
    effort: "low",
    reason: "Batch job CPU usage averages 18%. Memory never exceeds 2.5GB.",
  },
  {
    id: "OPT-003",
    category: "idle",
    resource: "staging-db-replica-2",
    type: "RDS Read Replica",
    currentSpec: "db.r5.large",
    suggestedSpec: "Terminate (use replica-1 only)",
    monthlySaving: 420,
    effort: "medium",
    reason: "This replica has 0 read queries for 14 days. Staging uses only 1 replica.",
  },
  {
    id: "OPT-004",
    category: "idle",
    resource: "elk-dev-cluster",
    type: "Elasticsearch Cluster",
    currentSpec: "3x m5.large nodes",
    suggestedSpec: "Schedule off 22:00–08:00 UTC",
    monthlySaving: 310,
    effort: "medium",
    reason: "No log queries outside business hours (08:00–22:00 UTC) for dev environment.",
  },
  {
    id: "OPT-005",
    category: "reserved",
    resource: "api-server-prod (fleet)",
    type: "EC2 Reserved Instance",
    currentSpec: "On-demand pricing",
    suggestedSpec: "1-year Reserved (no upfront)",
    monthlySaving: 820,
    effort: "high",
    reason: "API servers have run continuously for 18 months. 1-year RI saves 36% vs on-demand.",
  },
];

// Category labels are resolved from i18n keys at render time

const CATEGORY_COLORS: Record<RecoCategory, string> = {
  "right-sizing": "#3b82f6",
  "idle": "#f59e0b",
  "reserved": "#10b981",
};

const EFFORT_COLORS: Record<Effort, "green" | "yellow" | "red"> = {
  low: "green",
  medium: "yellow",
  high: "red",
};

export default function OptimizePage() {
  const locale = useLocale();
  const t = appDict.optimize[locale] ?? appDict.optimize.en;
  const tAny = t as unknown as Record<string, string>;
  const [applied, setApplied] = useState<Set<string>>(new Set());

  const CATEGORY_LABELS: Record<RecoCategory, string> = {
    "right-sizing": tAny.rightSizing ?? "Right-Sizing",
    "idle": tAny.idle ?? "Idle Resource",
    "reserved": tAny.reserved ?? "Reserved Instance",
  };

  const handleApply = (id: string) => {
    setApplied((prev) => new Set([...prev, id]));
  };

  const totalSavings = RECOMMENDATIONS.reduce((sum, r) => sum + r.monthlySaving, 0);
  const appliedSavings = RECOMMENDATIONS.filter((r) => applied.has(r.id)).reduce((sum, r) => sum + r.monthlySaving, 0);

  const categoryCounts = RECOMMENDATIONS.reduce((acc, r) => {
    acc[r.category] = (acc[r.category] ?? 0) + 1;
    return acc;
  }, {} as Record<RecoCategory, number>);

  return (
    <div className="w-full px-6 py-10">
      <div className="flex items-start justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold mb-1 flex items-center gap-3">
            <Gauge size={24} className="text-[var(--gold)]" />
            {t.title}
          </h1>
          <p className="text-[var(--text-secondary)] text-sm">{t.subtitle}</p>
        </div>
        <Button
          size="sm"
          className="shrink-0"
          onClick={() => setApplied(new Set(RECOMMENDATIONS.map((r) => r.id)))}
        >
          {t.applyAll}
        </Button>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        <Card className="text-center">
          <div className="flex items-center justify-center gap-1 mb-1">
            <DollarSign size={18} className="text-[var(--gold)]" />
            <p className="text-3xl font-extrabold font-mono text-[var(--gold)]">${totalSavings.toLocaleString()}</p>
          </div>
          <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider">{t.totalSavings}</p>
        </Card>
        <Card className="text-center">
          <p className="text-3xl font-extrabold font-mono">{RECOMMENDATIONS.length}</p>
          <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider mt-1">{t.recommendations}</p>
        </Card>
        <Card className="text-center">
          <p className="text-3xl font-extrabold font-mono text-[#10b981]">{applied.size}</p>
          <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider mt-1">{tAny.applied ?? "Applied"}</p>
        </Card>
        <Card className="text-center">
          <div className="flex items-center justify-center gap-1 mb-1">
            <TrendingDown size={16} className="text-[#10b981]" />
            <p className="text-2xl font-extrabold font-mono text-[#10b981]">${appliedSavings.toLocaleString()}</p>
          </div>
          <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider">{tAny.lockedIn ?? "Locked In"}</p>
        </Card>
      </div>

      {/* Category breakdown */}
      <div className="grid md:grid-cols-3 gap-4 mb-8">
        {(Object.keys(categoryCounts) as RecoCategory[]).map((cat) => {
          const savings = RECOMMENDATIONS.filter((r) => r.category === cat).reduce((s, r) => s + r.monthlySaving, 0);
          return (
            <Card key={cat} className="flex items-center gap-3">
              <div className="w-3 h-10 rounded-full shrink-0" style={{ backgroundColor: CATEGORY_COLORS[cat] }} />
              <div>
                <p className="font-semibold text-sm">{CATEGORY_LABELS[cat]}</p>
                <p className="text-xs text-[var(--text-muted)]">{categoryCounts[cat]} items · <span className="text-[#10b981]">${savings}/mo</span></p>
              </div>
            </Card>
          );
        })}
      </div>

      {/* Recommendations */}
      <div className="space-y-4">
        {RECOMMENDATIONS.map((rec) => {
          const isApplied = applied.has(rec.id);
          return (
            <Card key={rec.id} className={isApplied ? "opacity-60" : ""}>
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-2 flex-wrap">
                    <Badge variant="default" style={{ color: CATEGORY_COLORS[rec.category] }}>
                      {CATEGORY_LABELS[rec.category]}
                    </Badge>
                    <Badge variant={EFFORT_COLORS[rec.effort]}>
                      {t[rec.effort]} {t.effort}
                    </Badge>
                    <Badge variant="default">{rec.type}</Badge>
                  </div>
                  <p className="font-bold text-sm mb-1 font-mono">{rec.resource}</p>
                  <p className="text-xs text-[var(--text-secondary)] mb-3">{rec.reason}</p>

                  {/* Spec comparison */}
                  <div className="grid md:grid-cols-2 gap-2">
                    <div className="bg-[var(--bg-tertiary)] rounded-lg p-2.5">
                      <p className="text-xs text-[var(--text-muted)] mb-1">{t.currentSpec}</p>
                      <p className="text-xs font-mono text-[var(--text-secondary)]">{rec.currentSpec}</p>
                    </div>
                    <div className="bg-[#10b981]/5 border border-[#10b981]/20 rounded-lg p-2.5">
                      <p className="text-xs text-[var(--text-muted)] mb-1">{t.suggestedSpec}</p>
                      <p className="text-xs font-mono text-[#10b981]">{rec.suggestedSpec}</p>
                    </div>
                  </div>
                </div>

                <div className="text-right shrink-0 ml-2">
                  <div className="flex items-center gap-1 mb-1">
                    <DollarSign size={14} className="text-[#10b981]" />
                    <p className="text-lg font-extrabold font-mono text-[#10b981]">{rec.monthlySaving}</p>
                  </div>
                  <p className="text-xs text-[var(--text-muted)] mb-3">{tAny.perMonth ?? "per month"}</p>
                  {isApplied ? (
                    <div className="flex items-center gap-1 text-[#10b981]">
                      <CheckCircle2 size={16} />
                      <span className="text-xs">{tAny.applied ?? "Applied"}</span>
                    </div>
                  ) : (
                    <Button size="sm" onClick={() => handleApply(rec.id)}>
                      {tAny.apply ?? "Apply"}
                    </Button>
                  )}
                </div>
              </div>
            </Card>
          );
        })}
      </div>

      {/* Annual summary */}
      <Card className="mt-8 bg-[var(--gold)]/5 border border-[var(--gold)]/20">
        <div className="flex items-center justify-between">
          <div>
            <p className="font-bold text-lg">{tAny.annualSavings ?? "Annual Savings Potential"}</p>
            <p className="text-sm text-[var(--text-secondary)]">
              {(tAny.ifAllApplied ?? "If all {n} recommendations are applied").replace("{n}", String(RECOMMENDATIONS.length))}
            </p>
          </div>
          <div className="text-right">
            <div className="flex items-center gap-1">
              <DollarSign size={20} className="text-[var(--gold)]" />
              <p className="text-3xl font-extrabold font-mono text-[var(--gold)]">{(totalSavings * 12).toLocaleString()}</p>
            </div>
            <p className="text-sm text-[var(--text-muted)]">{tAny.perYear ?? "per year"}</p>
          </div>
        </div>
      </Card>
    </div>
  );
}
