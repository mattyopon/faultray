"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useState, useEffect, useCallback, useMemo } from "react";
import {
  DollarSign,
  TrendingUp,
  ArrowRight,
  Shield,
  Users,
  AlertTriangle,
  BarChart3,
  Printer,
  FileSpreadsheet,
} from "lucide-react";
import { useLocale } from "@/lib/useLocale";
import { appDict } from "@/i18n/app-dict";

/* ============================================================
 * Constants
 * ============================================================ */

const INDUSTRIES = [
  { id: "fintech", name: "FinTech" },
  { id: "healthcare", name: "Healthcare" },
  { id: "ecommerce", name: "E-Commerce" },
  { id: "saas", name: "SaaS" },
  { id: "media", name: "Media" },
] as const;

const SLA_OPTIONS = [
  { value: 99.0, label: "99.0%" },
  { value: 99.5, label: "99.5%" },
  { value: 99.9, label: "99.9%" },
  { value: 99.95, label: "99.95%" },
  { value: 99.99, label: "99.99%" },
  { value: 99.999, label: "99.999%" },
] as const;

/** Industry-specific avg incidents/year at score ~70 */
const INDUSTRY_INCIDENT_RATES: Record<string, number> = {
  fintech: 18,
  healthcare: 14,
  ecommerce: 22,
  saas: 16,
  media: 12,
};

/** Avg hours per incident response by industry */
const INDUSTRY_INCIDENT_HOURS: Record<string, number> = {
  fintech: 4.5,
  healthcare: 5.0,
  ecommerce: 3.5,
  saas: 3.0,
  media: 2.5,
};

/** Industry avg downtime cost multiplier (indirect costs) */
const INDUSTRY_INDIRECT_MULTIPLIER: Record<string, number> = {
  fintech: 1.8,
  healthcare: 2.2,
  ecommerce: 1.5,
  saas: 1.6,
  media: 1.3,
};

/* ============================================================
 * Types
 * ============================================================ */

interface SimulationData {
  overall_score: number;
  nines: number;
  availability_estimate: string;
  timestamp: string;
}

interface ScenarioResult {
  label: string;
  directLoss: number;
  slaPenalty: number;
  doraPenalty: number;
  insuranceCost: number;
  humanCost: number;
  total: number;
}

/* ============================================================
 * Helpers
 * ============================================================ */

/** Locale → currency, Intl locale, exchange rate from EUR base */
const LOCALE_CURRENCY: Record<string, { currency: string; intl: string; rate: number }> = {
  en: { currency: "USD", intl: "en-US", rate: 1.08 },
  ja: { currency: "JPY", intl: "ja-JP", rate: 160.0 },
  de: { currency: "EUR", intl: "de-DE", rate: 1.0 },
  fr: { currency: "EUR", intl: "fr-FR", rate: 1.0 },
  zh: { currency: "CNY", intl: "zh-CN", rate: 7.8 },
  ko: { currency: "KRW", intl: "ko-KR", rate: 1420.0 },
  es: { currency: "EUR", intl: "es-ES", rate: 1.0 },
  pt: { currency: "BRL", intl: "pt-BR", rate: 5.4 },
};

function getCurrencyFormatter(locale: string): (n: number) => string {
  const config = LOCALE_CURRENCY[locale] ?? LOCALE_CURRENCY.en;
  const fmt = new Intl.NumberFormat(config.intl, {
    style: "currency",
    currency: config.currency,
    maximumFractionDigits: 0,
  });
  return (n: number) => fmt.format(Math.round(n * config.rate));
}

function getCurrencySymbol(locale: string): string {
  const symbols: Record<string, string> = {
    en: "$", ja: "¥", de: "€", fr: "€", zh: "¥", ko: "₩", es: "€", pt: "R$",
  };
  return symbols[locale] ?? "$";
}



function downtimeHoursPerYear(nines: number): number {
  const availability = 1 - Math.pow(10, -nines);
  return (1 - availability) * 8760;
}

function scoreToNines(score: number): number {
  if (score >= 95) return 4.5;
  if (score >= 90) return 4.0;
  if (score >= 85) return 3.75;
  if (score >= 80) return 3.5;
  if (score >= 70) return 3.0;
  if (score >= 60) return 2.5;
  return 2.0;
}

function scoreToDoraCompliance(score: number): number {
  return Math.min(100, Math.max(0, score * 1.1 - 8));
}

function clamp(v: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, v));
}

/* ============================================================
 * SVG Chart components
 * ============================================================ */

function CumulativeCostChart({
  currentAnnualCost,
  improvedAnnualCost,
  investmentCost,
  formatCurrency,
  t,
}: {
  currentAnnualCost: number;
  improvedAnnualCost: number;
  investmentCost: number;
  formatCurrency: (n: number) => string;
  t: Record<string, string>;
}) {
  const years = 3;
  const points = 36; // monthly
  const w = 600;
  const h = 300;
  const pad = { top: 20, right: 20, bottom: 40, left: 80 };
  const chartW = w - pad.left - pad.right;
  const chartH = h - pad.top - pad.bottom;

  const maxCost = currentAnnualCost * years * 1.15;
  const noActionData: number[] = [];
  const improvedData: number[] = [];

  for (let m = 0; m <= points; m++) {
    const yearFrac = m / 12;
    // No action: linear growth with 8% annual increase
    noActionData.push(
      currentAnnualCost * yearFrac * (1 + 0.08 * yearFrac * 0.5)
    );
    // Improved: initial investment + reduced ongoing cost
    improvedData.push(investmentCost + improvedAnnualCost * yearFrac);
  }

  const effectiveMax = Math.max(maxCost, ...noActionData, ...improvedData);

  const toX = (m: number) => pad.left + (m / points) * chartW;
  const toY = (v: number) => pad.top + chartH - (v / effectiveMax) * chartH;

  const pathD = (data: number[]) =>
    data.map((v, i) => `${i === 0 ? "M" : "L"}${toX(i).toFixed(1)},${toY(v).toFixed(1)}`).join(" ");

  // Find crossover month
  let crossMonth = -1;
  for (let m = 1; m <= points; m++) {
    if (improvedData[m] < noActionData[m] && crossMonth === -1) {
      crossMonth = m;
    }
  }

  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full" aria-label={t.cumulativeCostChart}>
      {/* Grid lines */}
      {[0, 0.25, 0.5, 0.75, 1].map((frac) => {
        const y = pad.top + chartH * (1 - frac);
        return (
          <g key={frac}>
            <line x1={pad.left} x2={w - pad.right} y1={y} y2={y} stroke="#1e293b" strokeWidth={1} />
            <text x={pad.left - 8} y={y + 4} textAnchor="end" fill="#64748b" fontSize={10} fontFamily="monospace">
              {formatCurrency(effectiveMax * frac)}
            </text>
          </g>
        );
      })}

      {/* X axis labels */}
      {[0, 1, 2, 3].map((yr) => (
        <text key={yr} x={toX(yr * 12)} y={h - 8} textAnchor="middle" fill="#64748b" fontSize={10}>
          {t.year} {yr}
        </text>
      ))}

      {/* No-action line (red) */}
      <path d={pathD(noActionData)} fill="none" stroke="#ef4444" strokeWidth={2.5} strokeLinecap="round" />
      {/* Improved line (green) */}
      <path d={pathD(improvedData)} fill="none" stroke="#10b981" strokeWidth={2.5} strokeLinecap="round" />

      {/* Crossover point */}
      {crossMonth > 0 && (
        <g>
          <circle cx={toX(crossMonth)} cy={toY(noActionData[crossMonth])} r={5} fill="#FFD700" stroke="#0a0e1a" strokeWidth={2} />
          <text x={toX(crossMonth)} y={toY(noActionData[crossMonth]) - 12} textAnchor="middle" fill="#FFD700" fontSize={10} fontWeight="bold">
            ROI {t.breakeven}: {crossMonth}{t.months}
          </text>
        </g>
      )}

      {/* Legend */}
      <g transform={`translate(${pad.left + 10}, ${pad.top + 10})`}>
        <rect x={0} y={0} width={12} height={3} fill="#ef4444" rx={1} />
        <text x={16} y={5} fill="#94a3b8" fontSize={10}>{t.noAction}</text>
        <rect x={0} y={14} width={12} height={3} fill="#10b981" rx={1} />
        <text x={16} y={19} fill="#94a3b8" fontSize={10}>{t.withImprovements}</text>
      </g>
    </svg>
  );
}

function BenchmarkBarChart({
  yourCost,
  avgCost,
  topCost,
  formatCurrency,
  t,
}: {
  yourCost: number;
  avgCost: number;
  topCost: number;
  formatCurrency: (n: number) => string;
  t: Record<string, string>;
}) {
  const maxVal = Math.max(yourCost, avgCost, topCost) * 1.15;
  const bars = [
    { label: t.yourOrg, value: yourCost, color: yourCost > avgCost ? "#ef4444" : "#10b981" },
    { label: t.industryAvg, value: avgCost, color: "#64748b" },
    { label: t.industryTop, value: topCost, color: "#FFD700" },
  ];
  const barH = 36;
  const gap = 12;
  const labelW = 120;
  const chartW = 400;
  const svgH = bars.length * (barH + gap) + gap;

  return (
    <svg viewBox={`0 0 ${labelW + chartW + 140} ${svgH}`} className="w-full" aria-label={t.benchmarkChart}>
      {bars.map((bar, i) => {
        const y = gap + i * (barH + gap);
        const w = (bar.value / maxVal) * chartW;
        return (
          <g key={bar.label}>
            <text x={labelW - 8} y={y + barH / 2 + 4} textAnchor="end" fill="#94a3b8" fontSize={12}>
              {bar.label}
            </text>
            <rect x={labelW} y={y} width={w} height={barH} fill={bar.color} rx={4} opacity={0.8} />
            <text x={labelW + w + 8} y={y + barH / 2 + 4} fill="#e2e8f0" fontSize={11} fontFamily="monospace">
              {formatCurrency(bar.value)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

/* ============================================================
 * Export helpers
 * ============================================================ */

function generateExcelXml(data: {
  summary: Record<string, string | number>[];
  sla: Record<string, string | number>[];
  dora: Record<string, string | number>[];
  insurance: Record<string, string | number>[];
  humanCost: Record<string, string | number>[];
  sensitivity: Record<string, string | number>[];
}): string {
  const escXml = (s: string | number) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

  function sheet(name: string, rows: Record<string, string | number>[]): string {
    if (rows.length === 0) return "";
    const headers = Object.keys(rows[0]);
    const headerRow = headers.map((h) => `<Cell><Data ss:Type="String">${escXml(h)}</Data></Cell>`).join("");
    const dataRows = rows
      .map(
        (row) =>
          "<Row>" +
          headers
            .map((h) => {
              const v = row[h];
              const type = typeof v === "number" ? "Number" : "String";
              return `<Cell><Data ss:Type="${type}">${escXml(v)}</Data></Cell>`;
            })
            .join("") +
          "</Row>"
      )
      .join("\n");
    return `<Worksheet ss:Name="${escXml(name)}"><Table><Row>${headerRow}</Row>${dataRows}</Table></Worksheet>`;
  }

  return `<?xml version="1.0"?>
<?mso-application progid="Excel.Sheet"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
 xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
${sheet("Summary", data.summary)}
${sheet("SLA", data.sla)}
${sheet("DORA", data.dora)}
${sheet("Insurance", data.insurance)}
${sheet("Human Cost", data.humanCost)}
${sheet("Sensitivity", data.sensitivity)}
</Workbook>`;
}

/* ============================================================
 * Main Page
 * ============================================================ */

export default function CostPage() {
  const locale = useLocale();
  const t = appDict.cost[locale] ?? appDict.cost.en;
  const formatCurrency = useMemo(() => getCurrencyFormatter(locale), [locale]);
  const currencySymbol = getCurrencySymbol(locale);

  // ── Inputs ──
  const [industry, setIndustry] = useState("saas");
  const [revenuePerHour, setRevenuePerHour] = useState(15000);
  const [annualRevenue, setAnnualRevenue] = useState(5000000);
  const [contractSla, setContractSla] = useState(99.9);
  const [slaPenaltyRate, setSlaPenaltyRate] = useState(10);
  const [incidentTeamSize, setIncidentTeamSize] = useState(5);
  const [avgHourlyRate, setAvgHourlyRate] = useState(85);
  const [cyberInsurancePremium, setCyberInsurancePremium] = useState(50000);

  // ── Simulation data from localStorage ──
  const [simData, setSimData] = useState<SimulationData | null>(null);
  const [showResults, setShowResults] = useState(false);

  useEffect(() => {
    try {
      const raw = localStorage.getItem("faultray_last_simulation");
      if (raw) {
        const parsed = JSON.parse(raw) as SimulationData;
        if (parsed.overall_score) {
          // eslint-disable-next-line react-hooks/set-state-in-effect
          setSimData(parsed);
        }
      }
    } catch {
      // localStorage not available
    }
  }, []);

  // ── Derived calculations ──
  const currentScore = simData?.overall_score ?? 68;
  const currentNines = simData?.nines ?? scoreToNines(currentScore);
  const improvedScore = Math.min(100, currentScore + 21);
  const improvedNines = scoreToNines(improvedScore);

  const currentDowntimeHours = downtimeHoursPerYear(currentNines);
  const improvedDowntimeHours = downtimeHoursPerYear(improvedNines);

  const currentAvailability = (1 - currentDowntimeHours / 8760) * 100;
  const slaTarget = contractSla;
  const slaViolation = currentAvailability < slaTarget;
  const slaGap = slaTarget - currentAvailability;

  // 1. Direct loss
  const currentDirectLoss = currentDowntimeHours * revenuePerHour;
  const improvedDirectLoss = improvedDowntimeHours * revenuePerHour;

  // 2. SLA penalty
  const monthlyRevenue = annualRevenue / 12;
  const slaViolationMonths = slaViolation ? Math.ceil(slaGap / (100 - slaTarget) * 12) : 0;
  const currentSlaPenalty = slaViolation
    ? monthlyRevenue * (slaPenaltyRate / 100) * clamp(slaViolationMonths, 1, 12)
    : 0;
  const improvedAvailability = (1 - improvedDowntimeHours / 8760) * 100;
  const improvedSlaViolation = improvedAvailability < slaTarget;
  const improvedSlaPenalty = improvedSlaViolation
    ? monthlyRevenue * (slaPenaltyRate / 100) * 1
    : 0;

  // 3. DORA
  const doraCompliance = scoreToDoraCompliance(currentScore);
  const maxDoraFine = annualRevenue * 0.1;
  const doraProbability = doraCompliance < 50 ? 0.25 : doraCompliance < 70 ? 0.12 : doraCompliance < 85 ? 0.05 : 0.01;
  const expectedDoraFine = maxDoraFine * doraProbability;
  const improvedDoraCompliance = scoreToDoraCompliance(improvedScore);
  const improvedDoraProbability = improvedDoraCompliance < 50 ? 0.25 : improvedDoraCompliance < 70 ? 0.12 : improvedDoraCompliance < 85 ? 0.05 : 0.01;
  const improvedExpectedDoraFine = maxDoraFine * improvedDoraProbability;

  // 4. Insurance
  const insuranceReductionPct = clamp((improvedScore - currentScore) * 0.8, 0, 30);
  const currentInsuranceCost = cyberInsurancePremium;
  const improvedInsuranceCost = cyberInsurancePremium * (1 - insuranceReductionPct / 100);
  const insuranceSavings = currentInsuranceCost - improvedInsuranceCost;

  // 5. Human cost
  const incidentRate = INDUSTRY_INCIDENT_RATES[industry] ?? 16;
  const incidentHours = INDUSTRY_INCIDENT_HOURS[industry] ?? 3.5;
  const currentIncidents = Math.round(incidentRate * (1 + (70 - currentScore) * 0.03));
  const improvedIncidents = Math.max(2, Math.round(currentIncidents * 0.4));
  const currentHumanCost = currentIncidents * incidentHours * incidentTeamSize * avgHourlyRate;
  const improvedHumanCost = improvedIncidents * incidentHours * incidentTeamSize * avgHourlyRate;

  // ── Totals ──
  const currentTotalCost = currentDirectLoss + currentSlaPenalty + expectedDoraFine + currentInsuranceCost + currentHumanCost;
  const improvedTotalCost = improvedDirectLoss + improvedSlaPenalty + improvedExpectedDoraFine + improvedInsuranceCost + improvedHumanCost;
  const totalSavings = currentTotalCost - improvedTotalCost;

  // Investment estimate (rough)
  const investmentCost = Math.round(totalSavings * 0.3);

  // ── Sensitivity ──
  const indirectMultiplier = INDUSTRY_INDIRECT_MULTIPLIER[industry] ?? 1.5;
  const scenarios: ScenarioResult[] = useMemo(() => {
    const base: ScenarioResult = {
      label: t.baseScenario,
      directLoss: currentDirectLoss,
      slaPenalty: currentSlaPenalty,
      doraPenalty: expectedDoraFine,
      insuranceCost: currentInsuranceCost,
      humanCost: currentHumanCost,
      total: currentTotalCost,
    };
    const optimistic: ScenarioResult = {
      label: t.optimisticScenario,
      directLoss: currentDirectLoss * 0.5,
      slaPenalty: currentSlaPenalty * 0.3,
      doraPenalty: expectedDoraFine * 0.5,
      insuranceCost: currentInsuranceCost * 0.85,
      humanCost: currentHumanCost * 0.5,
      total: 0,
    };
    optimistic.total = optimistic.directLoss + optimistic.slaPenalty + optimistic.doraPenalty + optimistic.insuranceCost + optimistic.humanCost;

    const pessimistic: ScenarioResult = {
      label: t.pessimisticScenario,
      directLoss: currentDirectLoss * 2.0,
      slaPenalty: currentSlaPenalty * 2.5,
      doraPenalty: expectedDoraFine * 1.5,
      insuranceCost: currentInsuranceCost * 1.3,
      humanCost: currentHumanCost * 2.0,
      total: 0,
    };
    pessimistic.total = pessimistic.directLoss + pessimistic.slaPenalty + pessimistic.doraPenalty + pessimistic.insuranceCost + pessimistic.humanCost;

    return [optimistic, base, pessimistic];
  }, [currentDirectLoss, currentSlaPenalty, expectedDoraFine, currentInsuranceCost, currentHumanCost, currentTotalCost, t]);

  // ── Benchmark ──
  const avgCostMultiplier = indirectMultiplier;
  const industryAvgCost = currentTotalCost / avgCostMultiplier;
  const industryTopCost = industryAvgCost * 0.4;

  // ── Actions ──
  const runAnalysis = useCallback(() => {
    setShowResults(true);
  }, []);

  const downloadExcel = useCallback(() => {
    const fmtNum = (n: number) => Math.round(n);
    const xml = generateExcelXml({
      summary: [
        { Item: t.currentAnnualCost, Value: fmtNum(currentTotalCost) },
        { Item: t.improvedAnnualCost, Value: fmtNum(improvedTotalCost) },
        { Item: t.totalSavings, Value: fmtNum(totalSavings) },
        { Item: t.directLoss, Value: fmtNum(currentDirectLoss) },
        { Item: t.indirectLoss, Value: fmtNum(currentSlaPenalty + expectedDoraFine + currentHumanCost) },
      ],
      sla: [
        { Item: t.contractSla, Value: `${contractSla}%` },
        { Item: t.currentAvailability, Value: `${currentAvailability.toFixed(3)}%` },
        { Item: t.slaViolation, Value: slaViolation ? t.yes : t.no },
        { Item: t.annualPenalty, Value: fmtNum(currentSlaPenalty) },
      ],
      dora: [
        { Item: t.complianceRate, Value: `${doraCompliance.toFixed(0)}%` },
        { Item: t.maxFine, Value: fmtNum(maxDoraFine) },
        { Item: t.probability, Value: `${(doraProbability * 100).toFixed(0)}%` },
        { Item: t.expectedFine, Value: fmtNum(expectedDoraFine) },
      ],
      insurance: [
        { Item: t.currentPremium, Value: fmtNum(currentInsuranceCost) },
        { Item: t.improvedPremium, Value: fmtNum(improvedInsuranceCost) },
        { Item: t.annualSavings, Value: fmtNum(insuranceSavings) },
      ],
      humanCost: [
        { Item: t.annualIncidents, Value: currentIncidents },
        { Item: t.hoursPerIncident, Value: incidentHours },
        { Item: t.annualHumanCost, Value: fmtNum(currentHumanCost) },
        { Item: t.improvedHumanCost, Value: fmtNum(improvedHumanCost) },
      ],
      sensitivity: scenarios.map((s) => ({
        Scenario: s.label,
        DirectLoss: fmtNum(s.directLoss),
        SLAPenalty: fmtNum(s.slaPenalty),
        DORAFine: fmtNum(s.doraPenalty),
        Insurance: fmtNum(s.insuranceCost),
        HumanCost: fmtNum(s.humanCost),
        Total: fmtNum(s.total),
      })),
    });
    const blob = new Blob([xml], { type: "application/vnd.ms-excel" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "faultray-cost-analysis.xls";
    a.click();
    URL.revokeObjectURL(a.href);
  }, [
    currentTotalCost, improvedTotalCost, totalSavings, currentDirectLoss,
    currentSlaPenalty, expectedDoraFine, currentHumanCost, contractSla,
    currentAvailability, slaViolation, doraCompliance, maxDoraFine,
    doraProbability, currentInsuranceCost, improvedInsuranceCost,
    insuranceSavings, currentIncidents, incidentHours, improvedHumanCost, scenarios, t,
  ]);

  const printReport = useCallback(() => {
    window.print();
  }, []);

  /* ============================================================
   * Render
   * ============================================================ */

  return (
    <div className="max-w-[1200px] mx-auto px-6 py-10">
      {/* Header */}
      <div className="mb-10">
        <h1 className="text-2xl font-bold mb-1 flex items-center gap-3">
          <DollarSign size={24} className="text-[#FFD700]" />
          {t.title}
        </h1>
        <p className="text-[#94a3b8] text-sm">{t.subtitle}</p>
      </div>

      {/* ── Input Section ── */}
      <Card className="mb-8">
        <div className="grid md:grid-cols-3 gap-6">
          {/* Column 1: Industry */}
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

          {/* Column 2: Revenue & SLA */}
          <div className="space-y-4">
            <div>
              <label className="text-xs font-medium text-[#94a3b8] mb-2 block">
                {t.revenuePerHour} ({currencySymbol})
              </label>
              <input
                type="number"
                value={revenuePerHour}
                onChange={(e) => setRevenuePerHour(Number(e.target.value))}
                aria-label={`${t.revenuePerHour} (${currencySymbol})`}
                className="w-full px-3 py-2.5 bg-[#0d1117] border border-[#1e293b] rounded-lg text-sm font-mono text-[#e2e8f0] focus:border-[#FFD700]/50 focus:outline-none"
              />
              <input
                type="range"
                min={1000}
                max={200000}
                step={1000}
                value={revenuePerHour}
                onChange={(e) => setRevenuePerHour(Number(e.target.value))}
                aria-label={`${t.revenuePerHour} slider`}
                className="w-full mt-1 accent-[#FFD700]"
              />
              <div className="flex justify-between text-xs text-[#64748b]">
                <span>{currencySymbol}1K</span>
                <span>{currencySymbol}200K</span>
              </div>
            </div>

            <div>
              <label className="text-xs font-medium text-[#94a3b8] mb-2 block">
                {t.annualRevenue} ({currencySymbol})
              </label>
              <input
                type="number"
                value={annualRevenue}
                onChange={(e) => setAnnualRevenue(Number(e.target.value))}
                aria-label={`${t.annualRevenue} (${currencySymbol})`}
                className="w-full px-3 py-2.5 bg-[#0d1117] border border-[#1e293b] rounded-lg text-sm font-mono text-[#e2e8f0] focus:border-[#FFD700]/50 focus:outline-none"
              />
            </div>

            <div>
              <label className="text-xs font-medium text-[#94a3b8] mb-2 block">{t.contractSla}</label>
              <select
                value={contractSla}
                onChange={(e) => setContractSla(Number(e.target.value))}
                aria-label={locale === "ja" ? "契約SLA" : "Contract SLA"}
                className="w-full px-3 py-2.5 bg-[#0d1117] border border-[#1e293b] rounded-lg text-sm text-[#e2e8f0] focus:border-[#FFD700]/50 focus:outline-none"
              >
                {SLA_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="text-xs font-medium text-[#94a3b8] mb-2 block">
                {t.slaPenaltyRate} (%)
              </label>
              <input
                type="number"
                min={0}
                max={100}
                value={slaPenaltyRate}
                onChange={(e) => setSlaPenaltyRate(Number(e.target.value))}
                aria-label={`${t.slaPenaltyRate} (%)`}
                className="w-full px-3 py-2.5 bg-[#0d1117] border border-[#1e293b] rounded-lg text-sm font-mono text-[#e2e8f0] focus:border-[#FFD700]/50 focus:outline-none"
              />
            </div>
          </div>

          {/* Column 3: Team & Insurance */}
          <div className="space-y-4">
            <div>
              <label className="text-xs font-medium text-[#94a3b8] mb-2 block">{t.incidentTeamSize}</label>
              <input
                type="number"
                min={1}
                max={100}
                value={incidentTeamSize}
                onChange={(e) => setIncidentTeamSize(Number(e.target.value))}
                aria-label={t.incidentTeamSize}
                className="w-full px-3 py-2.5 bg-[#0d1117] border border-[#1e293b] rounded-lg text-sm font-mono text-[#e2e8f0] focus:border-[#FFD700]/50 focus:outline-none"
              />
            </div>

            <div>
              <label className="text-xs font-medium text-[#94a3b8] mb-2 block">
                {t.avgHourlyRate} ({currencySymbol})
              </label>
              <input
                type="number"
                min={10}
                max={500}
                value={avgHourlyRate}
                onChange={(e) => setAvgHourlyRate(Number(e.target.value))}
                aria-label={`${t.avgHourlyRate} (${currencySymbol})`}
                className="w-full px-3 py-2.5 bg-[#0d1117] border border-[#1e293b] rounded-lg text-sm font-mono text-[#e2e8f0] focus:border-[#FFD700]/50 focus:outline-none"
              />
            </div>

            <div>
              <label className="text-xs font-medium text-[#94a3b8] mb-2 block">
                {t.cyberInsurance} ({currencySymbol}/{t.perYearLabel})
              </label>
              <input
                type="number"
                min={0}
                value={cyberInsurancePremium}
                onChange={(e) => setCyberInsurancePremium(Number(e.target.value))}
                aria-label={`${t.cyberInsurance} (${currencySymbol}/${t.perYearLabel})`}
                className="w-full px-3 py-2.5 bg-[#0d1117] border border-[#1e293b] rounded-lg text-sm font-mono text-[#e2e8f0] focus:border-[#FFD700]/50 focus:outline-none"
              />
            </div>

            {/* Simulation data indicator */}
            {simData && (
              <div className="px-3 py-2 rounded-lg bg-emerald-500/5 border border-emerald-500/20 text-xs text-emerald-400">
                {t.simLinked}: {t.score} {currentScore} ({currentNines.toFixed(1)} nines)
              </div>
            )}

            <Button onClick={runAnalysis} className="w-full mt-2">
              <DollarSign size={16} />
              {t.calculateCost}
            </Button>
          </div>
        </div>
      </Card>

      {/* ── Results ── */}
      {showResults && (
        <div className="space-y-6 print:space-y-4">
          {/* ━━ 1. Dashboard ━━ */}
          <Card>
            <h3 className="text-lg font-bold mb-6 flex items-center gap-2">
              <DollarSign size={18} className="text-[#FFD700]" />
              {t.dashboardTitle}
            </h3>
            <div className="grid md:grid-cols-3 gap-6">
              <div className="text-center">
                <p className="text-xs text-[#64748b] uppercase tracking-wider mb-2">{t.totalAnnualCost}</p>
                <p className="text-3xl font-extrabold font-mono text-red-400">
                  {formatCurrency(currentTotalCost)}
                </p>
                <p className="text-xs text-[#64748b] mt-2">{t.directPlusIndirect}</p>
              </div>
              <div className="text-center border-x border-[#1e293b] px-4">
                <p className="text-xs text-[#64748b] uppercase tracking-wider mb-2">{t.directLoss}</p>
                <p className="text-2xl font-bold font-mono text-orange-400">
                  {formatCurrency(currentDirectLoss)}
                </p>
                <p className="text-xs text-[#64748b] mt-2">{currentDowntimeHours.toFixed(1)}h {t.downtimePerYear}</p>
              </div>
              <div className="text-center">
                <p className="text-xs text-[#64748b] uppercase tracking-wider mb-2">{t.indirectLoss}</p>
                <p className="text-2xl font-bold font-mono text-yellow-400">
                  {formatCurrency(currentSlaPenalty + expectedDoraFine + currentHumanCost + currentInsuranceCost)}
                </p>
                <p className="text-xs text-[#64748b] mt-2">SLA + DORA + {t.humanCostLabel} + {t.insurance}</p>
              </div>
            </div>
            {/* Savings banner */}
            <div className="mt-6 flex items-center justify-center gap-4 py-4 rounded-xl bg-emerald-500/5 border border-emerald-500/20">
              <ArrowRight size={20} className="text-[#FFD700]" />
              <div className="text-center">
                <Badge variant="green" className="text-base px-6 py-1.5">
                  {t.save} {formatCurrency(totalSavings)}{t.perYear}
                </Badge>
                <p className="text-xs text-[#64748b] mt-2">
                  {t.improvedTo} {improvedNines.toFixed(1)} nines ({improvedAvailability.toFixed(3)}%)
                </p>
              </div>
            </div>
          </Card>

          {/* ━━ 2. SLA Penalty ━━ */}
          <Card className={slaViolation ? "border-red-500/30" : "border-emerald-500/20"}>
            <h3 className="text-lg font-bold mb-4 flex items-center gap-2">
              <Shield size={18} className="text-[#FFD700]" />
              {t.slaPenaltyTitle}
            </h3>
            <div className="grid md:grid-cols-2 gap-6">
              <div className="space-y-3">
                <div className="flex justify-between text-sm">
                  <span className="text-[#94a3b8]">{t.contractSla}</span>
                  <span className="font-mono">{contractSla}%</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-[#94a3b8]">{t.currentAvailability}</span>
                  <span className={`font-mono ${slaViolation ? "text-red-400" : "text-emerald-400"}`}>
                    {currentAvailability.toFixed(3)}%
                  </span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-[#94a3b8]">{t.status}</span>
                  {slaViolation ? (
                    <Badge variant="red">{t.slaBreached}</Badge>
                  ) : (
                    <Badge variant="green">{t.slaMet}</Badge>
                  )}
                </div>
              </div>
              <div className="flex flex-col items-center justify-center">
                {slaViolation ? (
                  <>
                    <p className="text-2xl font-bold font-mono text-red-400">
                      {formatCurrency(currentSlaPenalty)}
                    </p>
                    <p className="text-xs text-[#64748b] mt-1">{t.annualPenaltyRisk}</p>
                    <p className="text-xs text-[#94a3b8] mt-2">
                      {t.slaExplanation.replace("{sla}", String(contractSla)).replace("{avail}", currentAvailability.toFixed(2)).replace("{amount}", formatCurrency(currentSlaPenalty))}
                    </p>
                  </>
                ) : (
                  <p className="text-sm text-emerald-400">{t.slaCompliant}</p>
                )}
              </div>
            </div>
          </Card>

          {/* ━━ 3. DORA Fine Risk ━━ */}
          <Card className="border-amber-500/20">
            <h3 className="text-lg font-bold mb-4 flex items-center gap-2">
              <AlertTriangle size={18} className="text-amber-400" />
              {t.doraTitle}
            </h3>
            <div className="grid md:grid-cols-3 gap-6">
              <div className="text-center">
                <p className="text-xs text-[#64748b] mb-2">{t.complianceRate}</p>
                <p className={`text-3xl font-extrabold font-mono ${doraCompliance < 70 ? "text-red-400" : doraCompliance < 85 ? "text-amber-400" : "text-emerald-400"}`}>
                  {doraCompliance.toFixed(0)}%
                </p>
              </div>
              <div className="text-center">
                <p className="text-xs text-[#64748b] mb-2">{t.maxFine} (10%)</p>
                <p className="text-2xl font-bold font-mono text-[#94a3b8]">{formatCurrency(maxDoraFine)}</p>
              </div>
              <div className="text-center">
                <p className="text-xs text-[#64748b] mb-2">{t.expectedFine}</p>
                <p className="text-2xl font-bold font-mono text-amber-400">{formatCurrency(expectedDoraFine)}</p>
                <p className="text-xs text-[#64748b] mt-1">{t.probability}: {(doraProbability * 100).toFixed(0)}%</p>
              </div>
            </div>
            <p className="text-xs text-[#64748b] mt-4 border-t border-[#1e293b] pt-3">
              {t.doraExplanation.replace("{rate}", doraCompliance.toFixed(0)).replace("{amount}", formatCurrency(expectedDoraFine))}
            </p>
          </Card>

          {/* ━━ 4. Insurance Impact ━━ */}
          <Card>
            <h3 className="text-lg font-bold mb-4 flex items-center gap-2">
              <Shield size={18} className="text-blue-400" />
              {t.insuranceTitle}
            </h3>
            <div className="grid md:grid-cols-3 gap-6">
              <div className="text-center">
                <p className="text-xs text-[#64748b] mb-2">{t.currentPremium}</p>
                <p className="text-2xl font-bold font-mono text-[#e2e8f0]">{formatCurrency(currentInsuranceCost)}</p>
                <p className="text-xs text-[#64748b] mt-1">{t.score}: {currentScore}</p>
              </div>
              <div className="text-center">
                <p className="text-xs text-[#64748b] mb-2">{t.improvedPremium}</p>
                <p className="text-2xl font-bold font-mono text-emerald-400">{formatCurrency(improvedInsuranceCost)}</p>
                <p className="text-xs text-[#64748b] mt-1">{t.score}: {improvedScore}</p>
              </div>
              <div className="text-center">
                <p className="text-xs text-[#64748b] mb-2">{t.annualSavings}</p>
                <Badge variant="green" className="text-lg px-4 py-1">
                  {formatCurrency(insuranceSavings)}
                </Badge>
                <p className="text-xs text-[#64748b] mt-2">
                  {t.reductionPct.replace("{pct}", insuranceReductionPct.toFixed(0))}
                </p>
              </div>
            </div>
          </Card>

          {/* ━━ 5. Human Cost ━━ */}
          <Card>
            <h3 className="text-lg font-bold mb-4 flex items-center gap-2">
              <Users size={18} className="text-purple-400" />
              {t.humanCostTitle}
            </h3>
            <div className="grid md:grid-cols-2 gap-8">
              <div>
                <p className="text-xs text-[#64748b] uppercase tracking-wider mb-3">{t.currentState}</p>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-[#94a3b8]">{t.annualIncidents}</span>
                    <span className="font-mono">{currentIncidents}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-[#94a3b8]">{t.hoursPerIncident}</span>
                    <span className="font-mono">{incidentHours}h</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-[#94a3b8]">{t.teamSize}</span>
                    <span className="font-mono">{incidentTeamSize}</span>
                  </div>
                  <div className="flex justify-between border-t border-[#1e293b] pt-2">
                    <span className="text-[#94a3b8] font-medium">{t.annualHumanCost}</span>
                    <span className="font-mono text-red-400 font-bold">{formatCurrency(currentHumanCost)}</span>
                  </div>
                </div>
              </div>
              <div>
                <p className="text-xs text-[#64748b] uppercase tracking-wider mb-3">{t.afterImprovement}</p>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-[#94a3b8]">{t.annualIncidents}</span>
                    <span className="font-mono text-emerald-400">{improvedIncidents}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-[#94a3b8]">{t.hoursPerIncident}</span>
                    <span className="font-mono">{incidentHours}h</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-[#94a3b8]">{t.teamSize}</span>
                    <span className="font-mono">{incidentTeamSize}</span>
                  </div>
                  <div className="flex justify-between border-t border-[#1e293b] pt-2">
                    <span className="text-[#94a3b8] font-medium">{t.improvedHumanCost}</span>
                    <span className="font-mono text-emerald-400 font-bold">{formatCurrency(improvedHumanCost)}</span>
                  </div>
                </div>
                <div className="mt-3 px-3 py-2 rounded-lg bg-emerald-500/5 border border-emerald-500/20 text-center">
                  <span className="text-emerald-400 font-bold text-sm">
                    {t.save} {formatCurrency(currentHumanCost - improvedHumanCost)}{t.perYear}
                  </span>
                </div>
              </div>
            </div>
          </Card>

          {/* ━━ 6. Cumulative Cost Chart ━━ */}
          <Card>
            <h3 className="text-lg font-bold mb-4 flex items-center gap-2">
              <TrendingUp size={18} className="text-[#FFD700]" />
              {t.cumulativeCostTitle}
            </h3>
            <CumulativeCostChart
              currentAnnualCost={currentTotalCost}
              improvedAnnualCost={improvedTotalCost}
              investmentCost={investmentCost}
              formatCurrency={formatCurrency}
              t={t}
            />
          </Card>

          {/* ━━ 7. Sensitivity Analysis ━━ */}
          <Card>
            <h3 className="text-lg font-bold mb-4 flex items-center gap-2">
              <BarChart3 size={18} className="text-cyan-400" />
              {t.sensitivityTitle}
            </h3>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[#1e293b]">
                    <th scope="col" className="text-left py-3 px-2 text-[#64748b] font-medium">{t.scenario}</th>
                    <th scope="col" className="text-right py-3 px-2 text-[#64748b] font-medium">{t.directLoss}</th>
                    <th scope="col" className="text-right py-3 px-2 text-[#64748b] font-medium">{t.slaPenalty}</th>
                    <th scope="col" className="text-right py-3 px-2 text-[#64748b] font-medium">{t.doraFine}</th>
                    <th scope="col" className="text-right py-3 px-2 text-[#64748b] font-medium">{t.insurance}</th>
                    <th scope="col" className="text-right py-3 px-2 text-[#64748b] font-medium">{t.humanCostLabel}</th>
                    <th scope="col" className="text-right py-3 px-2 text-[#64748b] font-medium">{t.totalCol}</th>
                  </tr>
                </thead>
                <tbody>
                  {scenarios.map((s, i) => (
                    <tr
                      key={s.label}
                      className={`border-b border-[#1e293b]/50 ${i === 1 ? "bg-white/[0.02]" : ""}`}
                    >
                      <td className="py-3 px-2 font-medium">
                        {i === 0 && <span className="text-emerald-400 mr-1">&#9650;</span>}
                        {i === 1 && <span className="text-[#94a3b8] mr-1">&#9644;</span>}
                        {i === 2 && <span className="text-red-400 mr-1">&#9660;</span>}
                        {s.label}
                      </td>
                      <td className="py-3 px-2 text-right font-mono">{formatCurrency(s.directLoss)}</td>
                      <td className="py-3 px-2 text-right font-mono">{formatCurrency(s.slaPenalty)}</td>
                      <td className="py-3 px-2 text-right font-mono">{formatCurrency(s.doraPenalty)}</td>
                      <td className="py-3 px-2 text-right font-mono">{formatCurrency(s.insuranceCost)}</td>
                      <td className="py-3 px-2 text-right font-mono">{formatCurrency(s.humanCost)}</td>
                      <td className="py-3 px-2 text-right font-mono font-bold">
                        {formatCurrency(s.total)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="text-xs text-[#64748b] mt-3">{t.sensitivityNote}</p>
          </Card>

          {/* ━━ 8. Industry Benchmark ━━ */}
          <Card>
            <h3 className="text-lg font-bold mb-4 flex items-center gap-2">
              <BarChart3 size={18} className="text-[#FFD700]" />
              {t.benchmarkTitle}
            </h3>
            <BenchmarkBarChart
              yourCost={currentTotalCost}
              avgCost={industryAvgCost}
              topCost={industryTopCost}
              formatCurrency={formatCurrency}
              t={t}
            />
            <p className="text-sm text-[#94a3b8] mt-4 text-center">
              {currentTotalCost > industryAvgCost
                ? t.benchmarkAbove.replace("{x}", (currentTotalCost / industryAvgCost).toFixed(1))
                : t.benchmarkBelow.replace("{x}", (industryAvgCost / currentTotalCost).toFixed(1))}
            </p>
          </Card>

          {/* ━━ Export ━━ */}
          <div className="flex gap-3 justify-end print:hidden">
            <Button variant="secondary" size="sm" onClick={downloadExcel}>
              <FileSpreadsheet size={14} />
              {t.downloadExcel}
            </Button>
            <Button variant="secondary" size="sm" onClick={printReport}>
              <Printer size={14} />
              {t.printPdf}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
