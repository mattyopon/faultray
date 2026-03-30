"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useState } from "react";
import { api, type CostAnalysis } from "@/lib/api";
import { DollarSign, Loader2, TrendingUp, ArrowRight } from "lucide-react";
import { useLocale } from "@/lib/useLocale";
import { appDict } from "@/i18n/app-dict";

const INDUSTRIES = [
  { id: "fintech", name: "FinTech" },
  { id: "healthcare", name: "Healthcare" },
  { id: "ecommerce", name: "E-Commerce" },
  { id: "saas", name: "SaaS" },
  { id: "media", name: "Media" },
];

function formatCurrency(n: number): string {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(n);
}

export default function CostPage() {
  const [industry, setIndustry] = useState("saas");
  const [revenue, setRevenue] = useState(15000);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<CostAnalysis | null>(null);
  const locale = useLocale();
  const t = locale === "ja" ? appDict.cost.ja : appDict.cost.en;

  const runAnalysis = async () => {
    setLoading(true);
    try {
      const res = await api.analyzeCost(revenue, industry);
      setResult(res);
    } catch {
      // Demo fallback
      setResult({
        current: { nines: 3.5, downtime_hours_per_year: 2.77, annual_cost: 103875 },
        target: { nines: 4.0, downtime_hours_per_year: 0.88, annual_cost: 33000 },
        potential_savings: 70875,
        revenue_per_hour: revenue,
        industry,
        improvements: [
          { action: "Add database read replica", cost: 2400, score_gain: 5.0, nines_gain: 0.3, annual_savings: 21263, roi_percent: 886, payback_days: 41 },
          { action: "Implement circuit breaker", cost: 800, score_gain: 3.2, nines_gain: 0.15, annual_savings: 10631, roi_percent: 1329, payback_days: 27 },
          { action: "Multi-region deployment", cost: 18000, score_gain: 8.5, nines_gain: 0.5, annual_savings: 35438, roi_percent: 197, payback_days: 185 },
          { action: "Auto-scaling configuration", cost: 1200, score_gain: 2.8, nines_gain: 0.1, annual_savings: 7088, roi_percent: 591, payback_days: 62 },
        ],
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-[1200px] mx-auto px-6 py-10">
      <div className="mb-10">
        <h1 className="text-2xl font-bold mb-1 flex items-center gap-3">
          <DollarSign size={24} className="text-[#FFD700]" />
          {t.title}
        </h1>
        <p className="text-[#94a3b8] text-sm">
          {t.subtitle}
        </p>
      </div>

      {/* Input */}
      <Card className="mb-8">
        <div className="grid md:grid-cols-3 gap-6">
          <div>
            <label className="text-xs font-medium text-[#94a3b8] mb-2 block">{t.industry}</label>
            <div className="space-y-2">
              {INDUSTRIES.map((ind) => (
                <button
                  key={ind.id}
                  onClick={() => setIndustry(ind.id)}
                  className={`w-full px-3 py-2 rounded-lg text-sm text-left transition-all ${
                    industry === ind.id
                      ? "bg-[#FFD700]/10 text-[#FFD700] border border-[#FFD700]/30"
                      : "text-[#94a3b8] border border-[#1e293b] hover:border-[#64748b]"
                  }`}
                >
                  {ind.name}
                </button>
              ))}
            </div>
          </div>
          <div>
            <label className="text-xs font-medium text-[#94a3b8] mb-2 block">{t.revenuePerHour}</label>
            <input
              type="number"
              value={revenue}
              onChange={(e) => setRevenue(Number(e.target.value))}
              className="w-full px-3 py-2.5 bg-[#0d1117] border border-[#1e293b] rounded-lg text-sm font-mono text-[#e2e8f0] focus:border-[#FFD700]/50 focus:outline-none"
            />
            <input
              type="range"
              min={1000}
              max={200000}
              step={1000}
              value={revenue}
              onChange={(e) => setRevenue(Number(e.target.value))}
              className="w-full mt-2 accent-[#FFD700]"
            />
            <div className="flex justify-between text-xs text-[#64748b] mt-1">
              <span>$1K</span>
              <span>$200K</span>
            </div>
          </div>
          <div className="flex items-end">
            <Button onClick={runAnalysis} disabled={loading} className="w-full">
              {loading ? (
                <>
                  <Loader2 size={16} className="animate-spin" />
                  {t.calculating}
                </>
              ) : (
                <>
                  <DollarSign size={16} />
                  {t.calculateCost}
                </>
              )}
            </Button>
          </div>
        </div>
      </Card>

      {/* Results */}
      {result && (
        <div className="space-y-6">
          {/* Cost Comparison */}
          <div className="grid md:grid-cols-3 gap-6">
            <Card className="text-center border-red-500/20">
              <p className="text-xs text-[#64748b] uppercase tracking-wider mb-2">{t.currentAnnualCost}</p>
              <p className="text-3xl font-extrabold font-mono text-red-400">
                {formatCurrency(result.current.annual_cost)}
              </p>
              <p className="text-xs text-[#64748b] mt-2">
                {result.current.downtime_hours_per_year.toFixed(1)}h downtime/year @ {result.current.nines} nines
              </p>
            </Card>
            <Card className="flex flex-col items-center justify-center">
              <ArrowRight size={24} className="text-[#FFD700] mb-2" />
              <Badge variant="green" className="text-base px-4 py-1">
                {t.save} {formatCurrency(result.potential_savings)}{t.perYear}
              </Badge>
            </Card>
            <Card className="text-center border-emerald-500/20">
              <p className="text-xs text-[#64748b] uppercase tracking-wider mb-2">{t.targetAnnualCost}</p>
              <p className="text-3xl font-extrabold font-mono text-emerald-400">
                {formatCurrency(result.target.annual_cost)}
              </p>
              <p className="text-xs text-[#64748b] mt-2">
                {result.target.downtime_hours_per_year.toFixed(1)}h downtime/year @ {result.target.nines} nines
              </p>
            </Card>
          </div>

          {/* ROI Table */}
          <Card>
            <h3 className="text-lg font-bold mb-4 flex items-center gap-2">
              <TrendingUp size={18} className="text-[#FFD700]" />
              {t.improvementRoi}
            </h3>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[#1e293b]">
                    <th className="text-left py-3 px-2 text-[#64748b] font-medium">{t.action}</th>
                    <th className="text-right py-3 px-2 text-[#64748b] font-medium">{t.costCol}</th>
                    <th className="text-right py-3 px-2 text-[#64748b] font-medium">{t.savingsPerYear}</th>
                    <th className="text-right py-3 px-2 text-[#64748b] font-medium">{t.roi}</th>
                    <th className="text-right py-3 px-2 text-[#64748b] font-medium">{t.payback}</th>
                    <th className="text-right py-3 px-2 text-[#64748b] font-medium">{t.impact}</th>
                  </tr>
                </thead>
                <tbody>
                  {result.improvements.map((imp) => (
                    <tr key={imp.action} className="border-b border-[#1e293b]/50 hover:bg-white/[0.02]">
                      <td className="py-3 px-2">{imp.action}</td>
                      <td className="py-3 px-2 text-right font-mono">{formatCurrency(imp.cost)}</td>
                      <td className="py-3 px-2 text-right font-mono text-emerald-400">
                        {formatCurrency(imp.annual_savings)}
                      </td>
                      <td className="py-3 px-2 text-right">
                        <Badge variant={imp.roi_percent >= 500 ? "green" : "yellow"}>
                          {imp.roi_percent}%
                        </Badge>
                      </td>
                      <td className="py-3 px-2 text-right font-mono text-[#94a3b8]">
                        {imp.payback_days}d
                      </td>
                      <td className="py-3 px-2 text-right font-mono text-[#FFD700]">
                        +{imp.nines_gain} nines
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}
