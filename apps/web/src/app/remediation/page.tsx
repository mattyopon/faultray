"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useState, useEffect, useCallback, useRef } from "react";
import {
  ClipboardCheck,
  AlertTriangle,
  TrendingUp,
  Shield,
  DollarSign,
  Download,
  FileText,
  ArrowRight,
  Zap,
  Calendar,
  BarChart3,
  Users,
} from "lucide-react";
import Link from "next/link";
import { useLocale } from "@/lib/useLocale";
import { appDict } from "@/i18n/app-dict";
import type { SimulationResult } from "@/lib/api";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface ActionItem {
  id: number;
  titleKey: string;
  title: Record<string, string>;
  priority: "critical" | "high" | "medium" | "low";
  effortWeeks: number;
  costEur: number;
  scoreImpact: number;
  doraImpact: number;
  startWeek: number;
}

interface RemediationData {
  score: number;
  doraCompliance: number;
  availability: string;
  actions: ActionItem[];
}

/* ------------------------------------------------------------------ */
/*  Demo data (used when no simulation result exists)                   */
/* ------------------------------------------------------------------ */

const DEMO_ACTIONS: ActionItem[] = [
  {
    id: 1,
    titleKey: "dbFailover",
    title: {
      en: "Database Failover Setup",
      ja: "DBフェイルオーバー構築",
      de: "Datenbank-Failover-Einrichtung",
      fr: "Configuration du basculement BDD",
      zh: "数据库故障转移设置",
      ko: "DB 페일오버 설정",
      es: "Configuración de failover de BD",
      pt: "Configuração de failover do banco",
    },
    priority: "critical",
    effortWeeks: 2,
    costEur: 15000,
    scoreImpact: 12.5,
    doraImpact: 8,
    startWeek: 1,
  },
  {
    id: 2,
    titleKey: "circuitBreaker",
    title: {
      en: "Circuit Breaker Implementation",
      ja: "サーキットブレーカー実装",
      de: "Circuit-Breaker-Implementierung",
      fr: "Implémentation du disjoncteur",
      zh: "熔断器实现",
      ko: "서킷 브레이커 구현",
      es: "Implementación de circuit breaker",
      pt: "Implementação do circuit breaker",
    },
    priority: "high",
    effortWeeks: 1,
    costEur: 8000,
    scoreImpact: 6.3,
    doraImpact: 5,
    startWeek: 2,
  },
  {
    id: 3,
    titleKey: "autoScaling",
    title: {
      en: "Auto-Scaling Configuration",
      ja: "オートスケーリング設定",
      de: "Auto-Scaling-Konfiguration",
      fr: "Configuration de l'auto-scaling",
      zh: "自动扩缩容配置",
      ko: "오토 스케일링 설정",
      es: "Configuración de auto-escalado",
      pt: "Configuração de auto-scaling",
    },
    priority: "high",
    effortWeeks: 3,
    costEur: 20000,
    scoreImpact: 8.1,
    doraImpact: 6,
    startWeek: 3,
  },
  {
    id: 4,
    titleKey: "cacheRedundancy",
    title: {
      en: "Cache Redundancy",
      ja: "キャッシュ冗長化",
      de: "Cache-Redundanz",
      fr: "Redondance du cache",
      zh: "缓存冗余",
      ko: "캐시 이중화",
      es: "Redundancia de caché",
      pt: "Redundância de cache",
    },
    priority: "medium",
    effortWeeks: 1,
    costEur: 5000,
    scoreImpact: 3.2,
    doraImpact: 3,
    startWeek: 6,
  },
  {
    id: 5,
    titleKey: "incidentReporting",
    title: {
      en: "Automated Incident Reporting",
      ja: "インシデント自動報告",
      de: "Automatisierte Vorfallsmeldung",
      fr: "Signalement automatisé des incidents",
      zh: "自动事件报告",
      ko: "자동 인시던트 보고",
      es: "Reporte automatizado de incidentes",
      pt: "Relatório automatizado de incidentes",
    },
    priority: "high",
    effortWeeks: 2,
    costEur: 12000,
    scoreImpact: 4.5,
    doraImpact: 10,
    startWeek: 3,
  },
];

const DEMO_DATA: RemediationData = {
  score: 68.4,
  doraCompliance: 69,
  availability: "99.97%",
  actions: DEMO_ACTIONS,
};

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function buildRemediationData(sim: SimulationResult): RemediationData {
  const score = sim.overall_score;
  const doraCompliance = Math.min(100, Math.round(score * 1.01));

  // Generate actions from critical_failures + suggestions
  const actions: ActionItem[] = [];
  let id = 1;
  let startWeek = 1;

  for (const failure of sim.critical_failures) {
    const effortWeeks = failure.severity === "CRITICAL" ? 2 : 1;
    const costEur = failure.severity === "CRITICAL" ? 15000 : 8000;
    const scoreImpact = failure.severity === "CRITICAL" ? 10 + Math.random() * 5 : 4 + Math.random() * 4;
    actions.push({
      id: id++,
      titleKey: `failure_${id}`,
      title: {
        en: `Fix: ${failure.scenario}`,
        ja: `修正: ${failure.scenario}`,
        de: `Beheben: ${failure.scenario}`,
        fr: `Corriger : ${failure.scenario}`,
        zh: `修复: ${failure.scenario}`,
        ko: `수정: ${failure.scenario}`,
        es: `Corregir: ${failure.scenario}`,
        pt: `Corrigir: ${failure.scenario}`,
      },
      priority: failure.severity === "CRITICAL" ? "critical" : "high",
      effortWeeks,
      costEur,
      scoreImpact: Math.round(scoreImpact * 10) / 10,
      doraImpact: failure.severity === "CRITICAL" ? 8 : 5,
      startWeek,
    });
    startWeek += effortWeeks;
  }

  for (const sug of sim.suggestions) {
    const effortMap: Record<string, number> = { Low: 1, Medium: 2, High: 3 };
    const effortWeeks = effortMap[sug.effort] ?? 2;
    const costMap: Record<string, number> = { Low: 5000, Medium: 12000, High: 20000 };
    const costEur = costMap[sug.effort] ?? 10000;
    const ninesMatch = sug.impact.match(/([\d.]+)/);
    const scoreImpact = ninesMatch ? parseFloat(ninesMatch[1]) * 5 : 3;
    actions.push({
      id: id++,
      titleKey: `sug_${id}`,
      title: {
        en: sug.title,
        ja: sug.title,
        de: sug.title,
        fr: sug.title,
        zh: sug.title,
        ko: sug.title,
        es: sug.title,
        pt: sug.title,
      },
      priority: sug.effort === "Low" ? "medium" : "high",
      effortWeeks,
      costEur,
      scoreImpact: Math.round(scoreImpact * 10) / 10,
      doraImpact: Math.round(scoreImpact * 0.8),
      startWeek,
    });
    startWeek += effortWeeks;
  }

  return { score, doraCompliance, availability: sim.availability_estimate, actions };
}

function calcProjectedScore(data: RemediationData): number {
  const totalImpact = data.actions.reduce((sum, a) => sum + a.scoreImpact, 0);
  return Math.min(100, Math.round((data.score + totalImpact) * 10) / 10);
}

function calcProjectedDora(data: RemediationData): number {
  const totalImpact = data.actions.reduce((sum, a) => sum + a.doraImpact, 0);
  return Math.min(100, data.doraCompliance + totalImpact);
}

function calcAnnualDowntimeCost(score: number): number {
  // Industry benchmark: base cost per point below 100
  return Math.round(((100 - score) / 100) * 500000 * 8.76) / 100 * 100;
}

function calcDowntimePerHour(score: number): number {
  return Math.round(calcAnnualDowntimeCost(score) / 8760);
}

function calcRoi(data: RemediationData): number {
  const totalCost = data.actions.reduce((sum, a) => sum + a.costEur, 0);
  const currentAnnual = calcAnnualDowntimeCost(data.score);
  const projectedAnnual = calcAnnualDowntimeCost(calcProjectedScore(data));
  const annualSaving = currentAnnual - projectedAnnual;
  if (annualSaving <= 0) return 99;
  return Math.round((totalCost / (annualSaving / 12)) * 10) / 10;
}

function calcProjectedAvailability(data: RemediationData): string {
  const projected = calcProjectedScore(data);
  if (projected >= 95) return "99.99%";
  if (projected >= 85) return "99.98%";
  if (projected >= 75) return "99.97%";
  return "99.95%";
}

function formatEur(amount: number): string {
  if (amount >= 1000000) return `\u20AC${(amount / 1000000).toFixed(1)}M`;
  if (amount >= 1000) return `\u20AC${Math.round(amount / 1000)}K`;
  return `\u20AC${amount}`;
}

function priorityColor(p: string): "red" | "yellow" | "default" | "green" {
  if (p === "critical") return "red";
  if (p === "high") return "yellow";
  if (p === "medium") return "default";
  return "green";
}

/* ------------------------------------------------------------------ */
/*  PDF / HTML export                                                   */
/* ------------------------------------------------------------------ */

function generateHtmlReport(data: RemediationData, t: Record<string, string>, locale: string): string {
  const projected = calcProjectedScore(data);
  const projectedDora = calcProjectedDora(data);
  const annualCost = calcAnnualDowntimeCost(data.score);
  const projectedCost = calcAnnualDowntimeCost(projected);
  const roi = calcRoi(data);

  const rows = data.actions
    .map(
      (a) =>
        `<tr>
          <td>${a.id}</td>
          <td>${a.title[locale] ?? a.title.en}</td>
          <td>${t[a.priority] ?? a.priority}</td>
          <td>${a.effortWeeks} ${a.effortWeeks > 1 ? t.weeks : t.week}</td>
          <td>${formatEur(a.costEur)}</td>
          <td>+${a.scoreImpact}</td>
        </tr>`
    )
    .join("\n");

  return `<!DOCTYPE html>
<html lang="${locale}">
<head>
<meta charset="UTF-8">
<title>${t.title} - FaultRay</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 900px; margin: 0 auto; padding: 40px 20px; color: #1a1a2e; }
  h1 { color: #0a0e1a; border-bottom: 3px solid #FFD700; padding-bottom: 12px; }
  h2 { color: #1e293b; margin-top: 32px; }
  .summary-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; margin: 20px 0; }
  .summary-card { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; }
  .summary-card .label { font-size: 12px; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; }
  .summary-card .value { font-size: 28px; font-weight: 700; margin-top: 4px; }
  table { width: 100%; border-collapse: collapse; margin: 16px 0; }
  th, td { border: 1px solid #e2e8f0; padding: 10px 14px; text-align: left; font-size: 14px; }
  th { background: #f1f5f9; font-weight: 600; }
  .before-after { display: grid; grid-template-columns: 1fr auto 1fr; gap: 16px; align-items: center; margin: 20px 0; }
  .ba-col { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; }
  .ba-arrow { font-size: 32px; color: #FFD700; }
  .footer { margin-top: 40px; padding-top: 16px; border-top: 1px solid #e2e8f0; font-size: 12px; color: #94a3b8; }
</style>
</head>
<body>
<h1>${t.title}</h1>
<p style="color:#64748b">${t.subtitle}</p>

<h2>${t.executiveSummary}</h2>
<div class="summary-grid">
  <div class="summary-card"><div class="label">${t.currentScore}</div><div class="value">${data.score} / 100</div></div>
  <div class="summary-card"><div class="label">${t.doraCompliance}</div><div class="value">${data.doraCompliance}%</div></div>
  <div class="summary-card"><div class="label">${t.estimatedAnnualDowntimeCost}</div><div class="value">${formatEur(annualCost)}</div></div>
  <div class="summary-card"><div class="label">${t.projectedScore}</div><div class="value" style="color:#10b981">${projected} / 100</div></div>
  <div class="summary-card"><div class="label">${t.roiPayback}</div><div class="value">${roi} ${t.months}</div></div>
</div>

<h2>${t.prioritizedActions}</h2>
<table>
  <thead><tr><th>#</th><th>${t.action}</th><th>${t.priority}</th><th>${t.effort}</th><th>${t.cost}</th><th>${t.expectedEffect}</th></tr></thead>
  <tbody>${rows}</tbody>
</table>

<h2>${t.beforeAfter}</h2>
<div class="before-after">
  <div class="ba-col">
    <strong>${t.before}</strong><br/>
    ${t.score}: ${data.score}<br/>
    ${t.availability}: ${data.availability}<br/>
    ${t.doraComplianceShort}: ${data.doraCompliance}%<br/>
    ${t.annualCost}: ${formatEur(annualCost)}
  </div>
  <div class="ba-arrow">\u2192</div>
  <div class="ba-col">
    <strong>${t.after}</strong><br/>
    ${t.score}: ${projected}<br/>
    ${t.availability}: ${calcProjectedAvailability(data)}<br/>
    ${t.doraComplianceShort}: ${projectedDora}%<br/>
    ${t.annualCost}: ${formatEur(projectedCost)}
  </div>
</div>

<div class="footer">Generated by FaultRay &mdash; ${new Date().toISOString().split("T")[0]}</div>
</body>
</html>`;
}

function downloadFile(content: string, filename: string, type: string) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export default function RemediationPage() {
  const locale = useLocale();
  const t = appDict.remediation[locale] ?? appDict.remediation.en;
  const [data, setData] = useState<RemediationData | null>(null);
  const [isDemo, setIsDemo] = useState(false);
  const loadedRef = useRef(false);

  useEffect(() => {
    if (loadedRef.current) return;
    loadedRef.current = true;
    try {
      const raw = localStorage.getItem("faultray_last_simulation");
      if (raw) {
        const sim: SimulationResult = JSON.parse(raw);
        setData(buildRemediationData(sim));
      }
    } catch {
      // ignore parse errors
    }
  }, []);

  const loadDemo = useCallback(() => {
    setData(DEMO_DATA);
    setIsDemo(true);
  }, []);

  const handleDownloadHtml = useCallback(() => {
    if (!data) return;
    const html = generateHtmlReport(data, t as unknown as Record<string, string>, locale);
    downloadFile(html, `faultray-remediation-plan-${locale}.html`, "text/html;charset=utf-8");
  }, [data, t, locale]);

  const handleDownloadPdf = useCallback(() => {
    if (!data) return;
    // Generate HTML and open in new window for printing to PDF
    const html = generateHtmlReport(data, t as unknown as Record<string, string>, locale);
    const win = window.open("", "_blank");
    if (win) {
      win.document.write(html);
      win.document.close();
      setTimeout(() => win.print(), 500);
    }
  }, [data, t, locale]);

  /* No simulation data yet */
  if (!data) {
    return (
      <div className="max-w-[1200px] mx-auto px-6 py-10">
        <div className="mb-10">
          <h1 className="text-2xl font-bold mb-1">{t.title}</h1>
          <p className="text-[#94a3b8] text-sm">{t.subtitle}</p>
        </div>
        <Card className="text-center py-16">
          <ClipboardCheck size={48} className="mx-auto text-[#475569] mb-4" />
          <h2 className="text-xl font-bold mb-2">{t.noSimulation}</h2>
          <p className="text-[#94a3b8] mb-6">{t.noSimulationDesc}</p>
          <div className="flex items-center justify-center gap-4">
            <Button onClick={loadDemo} variant="secondary">
              <BarChart3 size={16} />
              {t.viewDemo}
            </Button>
            <Link href="/simulate">
              <Button>
                <Zap size={16} />
                {t.runSimulation}
              </Button>
            </Link>
          </div>
        </Card>
      </div>
    );
  }

  const projected = calcProjectedScore(data);
  const projectedDora = calcProjectedDora(data);
  const annualCost = calcAnnualDowntimeCost(data.score);
  const projectedCost = calcAnnualDowntimeCost(projected);
  const roi = calcRoi(data);
  const totalActionCost = data.actions.reduce((s, a) => s + a.costEur, 0);
  const maxWeek = Math.max(...data.actions.map((a) => a.startWeek + a.effortWeeks));
  const scoreLabel = data.score >= 85 ? t.excellent : data.score >= 70 ? t.good : t.needsImprovement;
  const scoreColor = data.score >= 85 ? "text-emerald-400" : data.score >= 70 ? "text-yellow-400" : "text-red-400";

  return (
    <div className="max-w-[1200px] mx-auto px-6 py-10">
      {/* Header */}
      <div className="flex items-center justify-between mb-10">
        <div>
          <h1 className="text-2xl font-bold mb-1">{t.title}</h1>
          <p className="text-[#94a3b8] text-sm">
            {t.subtitle}
            {isDemo && (
              <Badge variant="yellow" className="ml-2">DEMO</Badge>
            )}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="secondary" size="sm" onClick={handleDownloadHtml}>
            <FileText size={14} />
            {t.downloadHtml}
          </Button>
          <Button size="sm" onClick={handleDownloadPdf}>
            <Download size={14} />
            {t.downloadPdf}
          </Button>
        </div>
      </div>

      {/* A. Executive Summary */}
      <h2 className="text-lg font-bold mb-4 flex items-center gap-2">
        <BarChart3 size={20} className="text-[#FFD700]" />
        {t.executiveSummary}
      </h2>
      <div className="grid md:grid-cols-5 gap-4 mb-10">
        <Card>
          <p className="text-[10px] text-[#64748b] uppercase tracking-wider mb-1">{t.currentScore}</p>
          <p className={`text-2xl font-bold font-mono ${scoreColor}`}>
            {data.score} <span className="text-sm text-[#475569]">/ 100</span>
          </p>
          <p className={`text-xs ${scoreColor}`}>{scoreLabel}</p>
        </Card>
        <Card>
          <p className="text-[10px] text-[#64748b] uppercase tracking-wider mb-1">{t.doraCompliance}</p>
          <p className={`text-2xl font-bold font-mono ${data.doraCompliance < 80 ? "text-red-400" : "text-yellow-400"}`}>
            {data.doraCompliance}%
          </p>
          {data.doraCompliance < 80 && (
            <p className="text-xs text-red-400">{t.nonCompliantRisk}</p>
          )}
        </Card>
        <Card>
          <p className="text-[10px] text-[#64748b] uppercase tracking-wider mb-1">{t.estimatedAnnualDowntimeCost}</p>
          <p className="text-2xl font-bold font-mono text-red-400">{formatEur(annualCost)}</p>
        </Card>
        <Card>
          <p className="text-[10px] text-[#64748b] uppercase tracking-wider mb-1">{t.projectedScore}</p>
          <p className="text-2xl font-bold font-mono text-emerald-400">
            {projected} <span className="text-sm text-[#475569]">/ 100</span>
          </p>
        </Card>
        <Card>
          <p className="text-[10px] text-[#64748b] uppercase tracking-wider mb-1">{t.roiPayback}</p>
          <p className="text-2xl font-bold font-mono text-[#FFD700]">
            {roi} <span className="text-sm text-[#475569]">{t.months}</span>
          </p>
        </Card>
      </div>

      {/* B. Risk Motivation */}
      <h2 className="text-lg font-bold mb-4 flex items-center gap-2">
        <AlertTriangle size={20} className="text-red-400" />
        {t.riskMotivation}
      </h2>
      <p className="text-sm text-[#94a3b8] mb-4">{t.whyFix}</p>
      <div className="grid md:grid-cols-4 gap-4 mb-10">
        <Card>
          <div className="w-10 h-10 rounded-lg bg-red-500/10 flex items-center justify-center mb-3">
            <Shield size={20} className="text-red-400" />
          </div>
          <p className="font-bold text-sm mb-1">{t.doraPenaltyRisk}</p>
          <p className="text-xs text-[#94a3b8]">{t.doraPenaltyDesc}</p>
        </Card>
        <Card>
          <div className="w-10 h-10 rounded-lg bg-orange-500/10 flex items-center justify-center mb-3">
            <DollarSign size={20} className="text-orange-400" />
          </div>
          <p className="font-bold text-sm mb-1">{t.downtimeCost}</p>
          <p className="text-xs text-[#94a3b8]">
            {formatEur(calcDowntimePerHour(data.score))} {t.perHour}
          </p>
        </Card>
        <Card>
          <div className="w-10 h-10 rounded-lg bg-yellow-500/10 flex items-center justify-center mb-3">
            <DollarSign size={20} className="text-yellow-400" />
          </div>
          <p className="font-bold text-sm mb-1">{t.cyberInsurance}</p>
          <p className="text-xs text-[#94a3b8]">{t.cyberInsuranceDesc}</p>
        </Card>
        <Card>
          <div className="w-10 h-10 rounded-lg bg-purple-500/10 flex items-center justify-center mb-3">
            <Users size={20} className="text-purple-400" />
          </div>
          <p className="font-bold text-sm mb-1">{t.reputationRisk}</p>
          <p className="text-xs text-[#94a3b8]">{t.reputationRiskDesc}</p>
        </Card>
      </div>

      {/* C. Prioritized Action List */}
      <h2 className="text-lg font-bold mb-4 flex items-center gap-2">
        <ClipboardCheck size={20} className="text-[#FFD700]" />
        {t.prioritizedActions}
      </h2>
      <Card className="mb-10 overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[#1e293b] text-[#64748b] text-xs uppercase tracking-wider">
              <th className="py-3 px-4 text-left">#</th>
              <th className="py-3 px-4 text-left">{t.action}</th>
              <th className="py-3 px-4 text-left">{t.priority}</th>
              <th className="py-3 px-4 text-left">{t.effort}</th>
              <th className="py-3 px-4 text-left">{t.cost}</th>
              <th className="py-3 px-4 text-left">{t.expectedEffect}</th>
            </tr>
          </thead>
          <tbody>
            {data.actions.map((a) => (
              <tr key={a.id} className="border-b border-[#1e293b]/50 hover:bg-white/[0.02]">
                <td className="py-3 px-4 font-mono text-[#64748b]">{a.id}</td>
                <td className="py-3 px-4 font-medium">{a.title[locale] ?? a.title.en}</td>
                <td className="py-3 px-4">
                  <Badge variant={priorityColor(a.priority)}>
                    {t[a.priority] ?? a.priority}
                  </Badge>
                </td>
                <td className="py-3 px-4 text-[#94a3b8]">
                  {a.effortWeeks} {a.effortWeeks > 1 ? t.weeks : t.week}
                </td>
                <td className="py-3 px-4 font-mono text-[#94a3b8]">{formatEur(a.costEur)}</td>
                <td className="py-3 px-4 font-mono text-emerald-400">+{a.scoreImpact}</td>
              </tr>
            ))}
            <tr className="bg-white/[0.02]">
              <td className="py-3 px-4" colSpan={3} />
              <td className="py-3 px-4 font-bold text-xs text-[#64748b] uppercase">Total</td>
              <td className="py-3 px-4 font-mono font-bold">{formatEur(totalActionCost)}</td>
              <td className="py-3 px-4 font-mono font-bold text-emerald-400">
                +{Math.round(data.actions.reduce((s, a) => s + a.scoreImpact, 0) * 10) / 10}
              </td>
            </tr>
          </tbody>
        </table>
      </Card>

      {/* D. Implementation Roadmap */}
      <h2 className="text-lg font-bold mb-4 flex items-center gap-2">
        <Calendar size={20} className="text-[#FFD700]" />
        {t.implementationRoadmap}
      </h2>
      <Card className="mb-10">
        <div className="space-y-3">
          {data.actions.map((a) => {
            const pct = ((a.startWeek - 1) / maxWeek) * 100;
            const widthPct = (a.effortWeeks / maxWeek) * 100;
            const cumulativeScore = data.score + data.actions
              .filter((x) => x.startWeek + x.effortWeeks <= a.startWeek + a.effortWeeks)
              .reduce((s, x) => s + x.scoreImpact, 0);
            const barColor =
              a.priority === "critical"
                ? "bg-red-500/60"
                : a.priority === "high"
                  ? "bg-yellow-500/60"
                  : "bg-blue-500/60";
            return (
              <div key={a.id} className="flex items-center gap-4">
                <div className="w-48 shrink-0 text-xs text-[#94a3b8] truncate" title={a.title[locale] ?? a.title.en}>
                  {a.title[locale] ?? a.title.en}
                </div>
                <div className="flex-1 relative h-7 bg-white/[0.03] rounded-md overflow-hidden">
                  <div
                    className={`absolute top-0 h-full rounded-md ${barColor} flex items-center justify-center text-[10px] font-mono text-white/80`}
                    style={{ left: `${pct}%`, width: `${Math.max(widthPct, 5)}%` }}
                  >
                    W{a.startWeek}-{a.startWeek + a.effortWeeks - 1}
                  </div>
                </div>
                <div className="w-20 text-right text-xs text-[#94a3b8] font-mono shrink-0">
                  {Math.min(100, Math.round(cumulativeScore * 10) / 10)}pts
                </div>
              </div>
            );
          })}
        </div>
        <p className="text-[10px] text-[#475569] mt-4">{t.predictedScoreAfterPhase}</p>
      </Card>

      {/* E. Before/After */}
      <h2 className="text-lg font-bold mb-4 flex items-center gap-2">
        <TrendingUp size={20} className="text-emerald-400" />
        {t.beforeAfter}
      </h2>
      <div className="grid md:grid-cols-[1fr_auto_1fr] gap-4 items-center mb-10">
        <Card>
          <p className="text-xs text-[#64748b] uppercase tracking-wider mb-3 font-semibold">{t.before}</p>
          <div className="space-y-3">
            <div className="flex justify-between">
              <span className="text-sm text-[#94a3b8]">{t.score}</span>
              <span className="font-mono font-bold">{data.score}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-sm text-[#94a3b8]">{t.availability}</span>
              <span className="font-mono font-bold">{data.availability}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-sm text-[#94a3b8]">{t.doraComplianceShort}</span>
              <span className="font-mono font-bold">{data.doraCompliance}%</span>
            </div>
            <div className="flex justify-between">
              <span className="text-sm text-[#94a3b8]">{t.annualCost}</span>
              <span className="font-mono font-bold text-red-400">{formatEur(annualCost)}</span>
            </div>
          </div>
        </Card>
        <div className="flex justify-center">
          <div className="w-12 h-12 rounded-full bg-[#FFD700]/10 flex items-center justify-center">
            <ArrowRight size={24} className="text-[#FFD700]" />
          </div>
        </div>
        <Card className="border-emerald-500/20">
          <p className="text-xs text-emerald-400 uppercase tracking-wider mb-3 font-semibold">{t.after}</p>
          <div className="space-y-3">
            <div className="flex justify-between">
              <span className="text-sm text-[#94a3b8]">{t.score}</span>
              <span className="font-mono font-bold text-emerald-400">{projected} <span className="text-xs text-emerald-500">(+{Math.round((projected - data.score) * 10) / 10})</span></span>
            </div>
            <div className="flex justify-between">
              <span className="text-sm text-[#94a3b8]">{t.availability}</span>
              <span className="font-mono font-bold text-emerald-400">{calcProjectedAvailability(data)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-sm text-[#94a3b8]">{t.doraComplianceShort}</span>
              <span className="font-mono font-bold text-emerald-400">{projectedDora}% <span className="text-xs text-emerald-500">(+{projectedDora - data.doraCompliance}%)</span></span>
            </div>
            <div className="flex justify-between">
              <span className="text-sm text-[#94a3b8]">{t.annualCost}</span>
              <span className="font-mono font-bold text-emerald-400">{formatEur(projectedCost)} <span className="text-xs text-emerald-500">(-{formatEur(annualCost - projectedCost)})</span></span>
            </div>
          </div>
        </Card>
      </div>

      {/* F. Export section */}
      <Card className="text-center py-8">
        <h3 className="font-bold mb-4">{t.exportPlan}</h3>
        <div className="flex items-center justify-center gap-4">
          <Button variant="secondary" onClick={handleDownloadHtml}>
            <FileText size={16} />
            {t.downloadHtml}
          </Button>
          <Button onClick={handleDownloadPdf}>
            <Download size={16} />
            {t.downloadPdf}
          </Button>
        </div>
      </Card>
    </div>
  );
}
