"use client";

import { useState, useMemo } from "react";
import { Calculator } from "lucide-react";

interface RoiDict {
  heading: string;
  subheading: string;
  monthlyRevenue: string;
  incidentCount: string;
  incidentHours: string;
  annualLoss: string;
  estimatedReduction: string;
  roi: string;
  annualCost: string;
  disclaimer: string;
  unit: string;
}

interface RoiCalculatorProps {
  dict: RoiDict;
  lang: string;
}

function formatNumber(n: number, lang: string): string {
  return n.toLocaleString(lang === "ja" ? "ja-JP" : "en-US");
}

export function RoiCalculator({ dict, lang }: RoiCalculatorProps) {
  // ja: 万円単位, others: $K単位
  const isJa = lang === "ja";

  const [monthlyRevenue, setMonthlyRevenue] = useState(isJa ? 1000 : 500); // 万円 or $K
  const [incidentCount, setIncidentCount] = useState(6);
  const [incidentHours, setIncidentHours] = useState(4);

  const calc = useMemo(() => {
    // 年間損失 = 月売上 × (障害時間/720) × 障害回数 × 12
    const annualLoss = monthlyRevenue * (incidentHours / 720) * incidentCount * 12;
    // FaultRay効果 = 年間損失 × 0.7 (70%削減)
    const savings = annualLoss * 0.7;
    // 年間コスト (Pro): ja = 45万円/年, others = $3,588/年
    const annualCost = isJa ? 54 : 3.588; // 万円 or $K
    // ROI = (削減額 - 年間コスト) / 年間コスト × 100
    const roi = annualCost > 0 ? ((savings - annualCost) / annualCost) * 100 : 0;
    return { annualLoss, savings, annualCost, roi };
  }, [monthlyRevenue, incidentCount, incidentHours, isJa]);

  const unit = dict.unit;

  return (
    <section id="roi" className="py-24 bg-[var(--bg-primary)]">
      <div className="max-w-[1200px] mx-auto px-6">
        <div className="text-center mb-12">
          <div className="inline-flex items-center gap-2 px-4 py-1.5 text-[0.8125rem] font-medium text-[var(--gold)] border border-[var(--gold)]/25 rounded-full bg-[var(--gold)]/5 mb-4">
            <Calculator size={14} />
            ROI
          </div>
          <h2 className="text-[clamp(1.75rem,4vw,2.5rem)] font-bold tracking-tight mb-3">
            {dict.heading}
          </h2>
          <p className="text-lg text-[var(--text-secondary)] max-w-[540px] mx-auto">{dict.subheading}</p>
        </div>

        <div className="max-w-[900px] mx-auto grid md:grid-cols-2 gap-8 items-start">
          {/* Input panel */}
          <div className="p-8 rounded-2xl border border-[var(--border-color)] bg-[var(--bg-card)] space-y-7">
            {/* Monthly revenue */}
            <div>
              <div className="flex justify-between mb-2">
                <label className="text-sm font-semibold text-[var(--text-primary)]">{dict.monthlyRevenue}</label>
                <span className="text-sm font-bold text-[var(--gold)]">
                  {formatNumber(monthlyRevenue, lang)} {unit}
                </span>
              </div>
              <input
                type="range"
                min={isJa ? 100 : 50}
                max={isJa ? 10000 : 5000}
                step={isJa ? 100 : 50}
                value={monthlyRevenue}
                onChange={(e) => setMonthlyRevenue(Number(e.target.value))}
                className="w-full h-2 rounded-full appearance-none cursor-pointer accent-[#055ec1] bg-[var(--border-color)]"
              />
              <div className="flex justify-between text-xs text-[var(--text-muted)] mt-1">
                <span>{isJa ? "100万円" : "$50K"}</span>
                <span>{isJa ? "1億円" : "$5M"}</span>
              </div>
            </div>

            {/* Incident count */}
            <div>
              <div className="flex justify-between mb-2">
                <label className="text-sm font-semibold text-[var(--text-primary)]">{dict.incidentCount}</label>
                <span className="text-sm font-bold text-[var(--gold)]">{incidentCount}回</span>
              </div>
              <input
                type="range"
                min={1}
                max={50}
                step={1}
                value={incidentCount}
                onChange={(e) => setIncidentCount(Number(e.target.value))}
                className="w-full h-2 rounded-full appearance-none cursor-pointer accent-[#055ec1] bg-[var(--border-color)]"
              />
              <div className="flex justify-between text-xs text-[var(--text-muted)] mt-1">
                <span>1回</span>
                <span>50回</span>
              </div>
            </div>

            {/* Incident hours */}
            <div>
              <div className="flex justify-between mb-2">
                <label className="text-sm font-semibold text-[var(--text-primary)]">{dict.incidentHours}</label>
                <span className="text-sm font-bold text-[var(--gold)]">{incidentHours}時間</span>
              </div>
              <input
                type="range"
                min={0.5}
                max={24}
                step={0.5}
                value={incidentHours}
                onChange={(e) => setIncidentHours(Number(e.target.value))}
                className="w-full h-2 rounded-full appearance-none cursor-pointer accent-[#055ec1] bg-[var(--border-color)]"
              />
              <div className="flex justify-between text-xs text-[var(--text-muted)] mt-1">
                <span>0.5時間</span>
                <span>24時間</span>
              </div>
            </div>
          </div>

          {/* Output panel */}
          <div className="space-y-4">
            {/* Annual loss */}
            <div className="p-6 rounded-2xl border border-red-500/25 bg-red-500/[0.04]">
              <div className="text-sm text-[var(--text-secondary)] mb-1">{dict.annualLoss}</div>
              <div className="text-3xl font-extrabold text-red-400">
                {formatNumber(Math.round(calc.annualLoss * 10) / 10, lang)} {unit}
              </div>
            </div>

            {/* Savings */}
            <div className="p-6 rounded-2xl border border-emerald-500/25 bg-emerald-500/[0.04]">
              <div className="text-sm text-[var(--text-secondary)] mb-1">{dict.estimatedReduction}</div>
              <div className="text-3xl font-extrabold text-emerald-400">
                {formatNumber(Math.round(calc.savings * 10) / 10, lang)} {unit}
              </div>
            </div>

            {/* Annual cost */}
            <div className="p-5 rounded-xl border border-[var(--border-color)] bg-[var(--bg-card)]">
              <div className="flex justify-between items-center">
                <span className="text-sm text-[var(--text-muted)]">{dict.annualCost}</span>
                <span className="text-base font-semibold text-[var(--text-secondary)]">
                  {formatNumber(Math.round(calc.annualCost * 10) / 10, lang)} {unit}
                </span>
              </div>
            </div>

            {/* ROI */}
            <div className="p-6 rounded-2xl border border-[var(--gold)]/30 bg-[var(--gold)]/[0.05]">
              <div className="text-sm text-[var(--text-secondary)] mb-1">{dict.roi}</div>
              <div className="text-4xl font-extrabold text-[var(--gold)]">
                {calc.roi > 0 ? "+" : ""}{Math.round(calc.roi).toLocaleString()}%
              </div>
            </div>

            <p className="text-xs text-[var(--text-muted)] leading-relaxed">{dict.disclaimer}</p>
          </div>
        </div>
      </div>
    </section>
  );
}
