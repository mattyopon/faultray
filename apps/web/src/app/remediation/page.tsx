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
  CalendarPlus,
  Pencil,
  Check,
  X,
  ListFilter,
  ChevronDown,
  Share2,
  Link2,
  Mail,
  MessageSquare,
  Copy,
  ExternalLink,
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

type TaskStatus = "todo" | "in_progress" | "in_review" | "done";

interface TaskState {
  assignee: string;
  status: TaskStatus;
  comment: string;
  deadline: string; // ISO date string or ""
}

type TaskStatesMap = Record<number, TaskState>;

type TaskFilter = "all" | TaskStatus;

/* ------------------------------------------------------------------ */
/*  Integration settings helpers                                       */
/* ------------------------------------------------------------------ */

const INTEGRATION_STORAGE_KEY = "faultray_integrations";

interface IntegrationSettings {
  jiraDomain: string;
  backlogSpace: string;
  slackWebhook: string;
}

function loadIntegrationSettings(): IntegrationSettings {
  try {
    const raw = localStorage.getItem(INTEGRATION_STORAGE_KEY);
    if (raw) return JSON.parse(raw) as IntegrationSettings;
  } catch {
    // ignore
  }
  return { jiraDomain: "", backlogSpace: "", slackWebhook: "" };
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
      ja: "DB\u30D5\u30A7\u30A4\u30EB\u30AA\u30FC\u30D0\u30FC\u69CB\u7BC9",
      de: "Datenbank-Failover-Einrichtung",
      fr: "Configuration du basculement BDD",
      zh: "\u6570\u636E\u5E93\u6545\u969C\u8F6C\u79FB\u8BBE\u7F6E",
      ko: "DB \uD398\uC77C\uC624\uBC84 \uC124\uC815",
      es: "Configuraci\u00F3n de failover de BD",
      pt: "Configura\u00E7\u00E3o de failover do banco",
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
      ja: "\u30B5\u30FC\u30AD\u30C3\u30C8\u30D6\u30EC\u30FC\u30AB\u30FC\u5B9F\u88C5",
      de: "Circuit-Breaker-Implementierung",
      fr: "Impl\u00E9mentation du disjoncteur",
      zh: "\u7194\u65AD\u5668\u5B9E\u73B0",
      ko: "\uC11C\uD0B7 \uBE0C\uB808\uC774\uCEE4 \uAD6C\uD604",
      es: "Implementaci\u00F3n de circuit breaker",
      pt: "Implementa\u00E7\u00E3o do circuit breaker",
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
      ja: "\u30AA\u30FC\u30C8\u30B9\u30B1\u30FC\u30EA\u30F3\u30B0\u8A2D\u5B9A",
      de: "Auto-Scaling-Konfiguration",
      fr: "Configuration de l'auto-scaling",
      zh: "\u81EA\u52A8\u6269\u7F29\u5BB9\u914D\u7F6E",
      ko: "\uC624\uD1A0 \uC2A4\uCF00\uC77C\uB9C1 \uC124\uC815",
      es: "Configuraci\u00F3n de auto-escalado",
      pt: "Configura\u00E7\u00E3o de auto-scaling",
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
      ja: "\u30AD\u30E3\u30C3\u30B7\u30E5\u5197\u9577\u5316",
      de: "Cache-Redundanz",
      fr: "Redondance du cache",
      zh: "\u7F13\u5B58\u5197\u4F59",
      ko: "\uCE90\uC2DC \uC774\uC911\uD654",
      es: "Redundancia de cach\u00E9",
      pt: "Redund\u00E2ncia de cache",
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
      ja: "\u30A4\u30F3\u30B7\u30C7\u30F3\u30C8\u81EA\u52D5\u5831\u544A",
      de: "Automatisierte Vorfallsmeldung",
      fr: "Signalement automatis\u00E9 des incidents",
      zh: "\u81EA\u52A8\u4E8B\u4EF6\u62A5\u544A",
      ko: "\uC790\uB3D9 \uC778\uC2DC\uB358\uD2B8 \uBCF4\uACE0",
      es: "Reporte automatizado de incidentes",
      pt: "Relat\u00F3rio automatizado de incidentes",
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
        ja: `\u4FEE\u6B63: ${failure.scenario}`,
        de: `Beheben: ${failure.scenario}`,
        fr: `Corriger : ${failure.scenario}`,
        zh: `\u4FEE\u590D: ${failure.scenario}`,
        ko: `\uC218\uC815: ${failure.scenario}`,
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
    // Use score_gain directly if available (new API), fallback to parsing impact string
    const scoreImpact = (sug as Record<string, unknown>).score_gain
      ? Number((sug as Record<string, unknown>).score_gain)
      : (() => { const m = sug.impact.match(/([\d.]+)/); return m ? parseFloat(m[1]) * 5 : 3; })();
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

  // If total score impact doesn't reach 100, add specific hardening tasks
  const totalImpact = actions.reduce((sum, a) => sum + a.scoreImpact, 0);
  if (score + totalImpact < 95 && actions.length < 20) {
    const gap = 100 - (score + totalImpact);
    // Break gap into 4 specific tasks proportionally
    const tlsShare = Math.round(gap * 0.23 * 10) / 10;
    const netShare = Math.round(gap * 0.23 * 10) / 10;
    const drShare = Math.round(gap * 0.31 * 10) / 10;
    const monShare = Math.round((gap - tlsShare - netShare - drShare) * 10) / 10;

    const hardeningTasks: ActionItem[] = [
      {
        id: id++,
        titleKey: "tls_encryption",
        title: {
          en: "Enable encryption in transit (TLS)",
          ja: "転送中の暗号化を有効化 (TLS)",
          de: "Verschlüsselung im Transit aktivieren (TLS)",
          fr: "Activer le chiffrement en transit (TLS)",
          zh: "启用传输加密 (TLS)",
          ko: "전송 중 암호화 활성화 (TLS)",
          es: "Habilitar cifrado en tránsito (TLS)",
          pt: "Habilitar criptografia em trânsito (TLS)",
        },
        priority: "medium",
        effortWeeks: 1,
        costEur: 5000,
        scoreImpact: tlsShare,
        doraImpact: Math.round(tlsShare * 0.7),
        startWeek,
      },
      {
        id: id++,
        titleKey: "network_segmentation",
        title: {
          en: "Add network segmentation",
          ja: "ネットワークセグメンテーションの導入",
          de: "Netzwerksegmentierung hinzufügen",
          fr: "Ajouter la segmentation réseau",
          zh: "添加网络分段",
          ko: "네트워크 세분화 추가",
          es: "Agregar segmentación de red",
          pt: "Adicionar segmentação de rede",
        },
        priority: "medium",
        effortWeeks: 1,
        costEur: 7000,
        scoreImpact: netShare,
        doraImpact: Math.round(netShare * 0.7),
        startWeek: startWeek + 1,
      },
      {
        id: id++,
        titleKey: "dr_testing",
        title: {
          en: "Implement automated DR testing",
          ja: "自動化されたDRテストの実装",
          de: "Automatisiertes DR-Testing implementieren",
          fr: "Mettre en œuvre les tests DR automatisés",
          zh: "实施自动化灾难恢复测试",
          ko: "자동화된 DR 테스트 구현",
          es: "Implementar pruebas de DR automatizadas",
          pt: "Implementar testes de DR automatizados",
        },
        priority: "medium",
        effortWeeks: 2,
        costEur: 10000,
        scoreImpact: drShare,
        doraImpact: Math.round(drShare * 0.7),
        startWeek: startWeek + 2,
      },
      {
        id: id++,
        titleKey: "comprehensive_monitoring",
        title: {
          en: "Add comprehensive monitoring",
          ja: "包括的なモニタリングの追加",
          de: "Umfassendes Monitoring hinzufügen",
          fr: "Ajouter une surveillance complète",
          zh: "添加全面监控",
          ko: "포괄적 모니터링 추가",
          es: "Agregar monitoreo completo",
          pt: "Adicionar monitoramento abrangente",
        },
        priority: "medium",
        effortWeeks: 1,
        costEur: 8000,
        scoreImpact: monShare,
        doraImpact: Math.round(monShare * 0.7),
        startWeek: startWeek + 4,
      },
    ];

    // Only add tasks that contribute meaningfully (>0 score impact)
    for (const task of hardeningTasks) {
      if (task.scoreImpact > 0 && actions.length < 20) {
        actions.push(task);
      }
    }

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
  // Map score to availability nines:
  // 95+ → 4 nines (99.99%), 90-94 → 3.5 nines, 80-89 → 3 nines (99.9%), 70-79 → 2.5 nines, <70 → 2 nines (99%)
  let nines: number;
  if (score >= 95) nines = 4.0;
  else if (score >= 90) nines = 3.5;
  else if (score >= 80) nines = 3.0;
  else if (score >= 70) nines = 2.5;
  else nines = 2.0;

  const availability = 1 - Math.pow(10, -nines);
  const downtimeHours = 8760 * (1 - availability);
  // Industry average revenue impact: €15,000/hour
  const costPerHour = 15000;
  return Math.round(downtimeHours * costPerHour);
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

/** Locale → currency config for remediation costs */
const _LOCALE_CURRENCY: Record<string, { symbol: string; rate: number }> = {
  en: { symbol: "$", rate: 1.08 },
  ja: { symbol: "¥", rate: 160.0 },
  de: { symbol: "€", rate: 1.0 },
  fr: { symbol: "€", rate: 1.0 },
  zh: { symbol: "¥", rate: 7.8 },
  ko: { symbol: "₩", rate: 1420.0 },
  es: { symbol: "€", rate: 1.0 },
  pt: { symbol: "R$", rate: 5.4 },
};

let _activeLocale = "en";

function formatEur(amount: number): string {
  const cfg = _LOCALE_CURRENCY[_activeLocale] ?? _LOCALE_CURRENCY.en;
  const converted = Math.round(amount * cfg.rate);
  if (converted >= 1000000) return `${cfg.symbol}${(converted / 1000000).toFixed(1)}M`;
  if (converted >= 1000) return `${cfg.symbol}${Math.round(converted / 1000)}K`;
  return `${cfg.symbol}${converted}`;
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
/*  Excel XML Spreadsheet 2003 export                                   */
/* ------------------------------------------------------------------ */

function escapeXml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function generateExcelXml(
  data: RemediationData,
  taskStates: TaskStatesMap,
  t: Record<string, string>,
  locale: string,
): string {
  const projected = calcProjectedScore(data);
  const projectedDora = calcProjectedDora(data);
  const annualCost = calcAnnualDowntimeCost(data.score);
  const projectedCost = calcAnnualDowntimeCost(projected);
  const roi = calcRoi(data);
  const totalCost = data.actions.reduce((s, a) => s + a.costEur, 0);
  const maxWeek = Math.max(...data.actions.map((a) => a.startWeek + a.effortWeeks));

  const statusLabel = (s: TaskStatus): string => {
    const map: Record<TaskStatus, string> = {
      todo: t.statusTodo ?? "To Do",
      in_progress: t.statusInProgress ?? "In Progress",
      in_review: t.statusInReview ?? "In Review",
      done: t.statusDone ?? "Done",
    };
    return map[s] ?? s;
  };

  // Sheet 1: Executive Summary
  const sheet1 = `<Worksheet ss:Name="${escapeXml(t.excelSheetSummary ?? "Executive Summary")}">
<Table>
<Column ss:Width="200"/><Column ss:Width="150"/>
<Row><Cell ss:StyleID="Header"><Data ss:Type="String">${escapeXml(t.title)}</Data></Cell></Row>
<Row><Cell><Data ss:Type="String">${escapeXml(t.currentScore)}</Data></Cell><Cell><Data ss:Type="Number">${data.score}</Data></Cell></Row>
<Row><Cell><Data ss:Type="String">${escapeXml(t.doraCompliance)}</Data></Cell><Cell><Data ss:Type="String">${data.doraCompliance}%</Data></Cell></Row>
<Row><Cell><Data ss:Type="String">${escapeXml(t.estimatedAnnualDowntimeCost)}</Data></Cell><Cell><Data ss:Type="Number">${annualCost}</Data></Cell></Row>
<Row><Cell><Data ss:Type="String">${escapeXml(t.projectedScore)}</Data></Cell><Cell><Data ss:Type="Number">${projected}</Data></Cell></Row>
<Row><Cell><Data ss:Type="String">${escapeXml(t.roiPayback)}</Data></Cell><Cell><Data ss:Type="String">${roi} ${escapeXml(t.months)}</Data></Cell></Row>
<Row><Cell><Data ss:Type="String">${escapeXml(t.annualCost)} (${escapeXml(t.after)})</Data></Cell><Cell><Data ss:Type="Number">${projectedCost}</Data></Cell></Row>
</Table>
</Worksheet>`;

  // Sheet 2: Action List
  const actionRows = data.actions.map((a) => {
    const ts = taskStates[a.id] ?? { assignee: "", status: "todo" as TaskStatus, comment: "", deadline: "" };
    const { start } = calcActionDates(a);
    const deadline = ts.deadline || start.toISOString().split("T")[0];
    return `<Row>
<Cell><Data ss:Type="Number">${a.id}</Data></Cell>
<Cell><Data ss:Type="String">${escapeXml(a.title[locale] ?? a.title.en)}</Data></Cell>
<Cell><Data ss:Type="String">${escapeXml(t[a.priority] ?? a.priority)}</Data></Cell>
<Cell><Data ss:Type="String">${escapeXml(ts.assignee || (t.unassigned ?? "Unassigned"))}</Data></Cell>
<Cell><Data ss:Type="String">${escapeXml(statusLabel(ts.status))}</Data></Cell>
<Cell><Data ss:Type="Number">${a.effortWeeks}</Data></Cell>
<Cell><Data ss:Type="Number">${a.costEur}</Data></Cell>
<Cell><Data ss:Type="Number">${a.scoreImpact}</Data></Cell>
<Cell><Data ss:Type="String">${escapeXml(deadline)}</Data></Cell>
</Row>`;
  }).join("\n");

  const sheet2 = `<Worksheet ss:Name="${escapeXml(t.excelSheetActions ?? "Action List")}">
<Table>
<Column ss:Width="40"/><Column ss:Width="250"/><Column ss:Width="80"/><Column ss:Width="100"/><Column ss:Width="100"/><Column ss:Width="60"/><Column ss:Width="80"/><Column ss:Width="80"/><Column ss:Width="100"/>
<Row>
<Cell ss:StyleID="Header"><Data ss:Type="String">#</Data></Cell>
<Cell ss:StyleID="Header"><Data ss:Type="String">${escapeXml(t.action)}</Data></Cell>
<Cell ss:StyleID="Header"><Data ss:Type="String">${escapeXml(t.priority)}</Data></Cell>
<Cell ss:StyleID="Header"><Data ss:Type="String">${escapeXml(t.assignee)}</Data></Cell>
<Cell ss:StyleID="Header"><Data ss:Type="String">${escapeXml(t.status ?? "Status")}</Data></Cell>
<Cell ss:StyleID="Header"><Data ss:Type="String">${escapeXml(t.effort)}</Data></Cell>
<Cell ss:StyleID="Header"><Data ss:Type="String">${escapeXml(t.cost)}</Data></Cell>
<Cell ss:StyleID="Header"><Data ss:Type="String">${escapeXml(t.expectedEffect)}</Data></Cell>
<Cell ss:StyleID="Header"><Data ss:Type="String">${escapeXml(t.deadline)}</Data></Cell>
</Row>
${actionRows}
<Row>
<Cell></Cell><Cell></Cell><Cell></Cell><Cell></Cell><Cell></Cell>
<Cell ss:StyleID="Header"><Data ss:Type="String">Total</Data></Cell>
<Cell ss:StyleID="Header"><Data ss:Type="Number">${totalCost}</Data></Cell>
<Cell ss:StyleID="Header"><Data ss:Type="Number">${Math.round(data.actions.reduce((s, a) => s + a.scoreImpact, 0) * 10) / 10}</Data></Cell>
<Cell></Cell>
</Row>
</Table>
</Worksheet>`;

  // Sheet 3: Roadmap
  const roadmapRows = data.actions.map((a) => {
    const weekCells = Array.from({ length: maxWeek }, (_, i) => {
      const w = i + 1;
      const active = w >= a.startWeek && w < a.startWeek + a.effortWeeks;
      return `<Cell><Data ss:Type="String">${active ? "\u2588" : ""}</Data></Cell>`;
    }).join("");
    return `<Row>
<Cell><Data ss:Type="String">${escapeXml(a.title[locale] ?? a.title.en)}</Data></Cell>
${weekCells}
</Row>`;
  }).join("\n");

  const weekHeaders = Array.from({ length: maxWeek }, (_, i) =>
    `<Cell ss:StyleID="Header"><Data ss:Type="String">W${i + 1}</Data></Cell>`
  ).join("");

  const sheet3 = `<Worksheet ss:Name="${escapeXml(t.excelSheetRoadmap ?? "Roadmap")}">
<Table>
<Column ss:Width="250"/>${Array.from({ length: maxWeek }, () => '<Column ss:Width="40"/>').join("")}
<Row>
<Cell ss:StyleID="Header"><Data ss:Type="String">${escapeXml(t.action)}</Data></Cell>
${weekHeaders}
</Row>
${roadmapRows}
</Table>
</Worksheet>`;

  // Sheet 4: Before/After
  const sheet4 = `<Worksheet ss:Name="${escapeXml(t.excelSheetBeforeAfter ?? "Before After")}">
<Table>
<Column ss:Width="200"/><Column ss:Width="150"/><Column ss:Width="150"/>
<Row>
<Cell ss:StyleID="Header"><Data ss:Type="String"></Data></Cell>
<Cell ss:StyleID="Header"><Data ss:Type="String">${escapeXml(t.before)}</Data></Cell>
<Cell ss:StyleID="Header"><Data ss:Type="String">${escapeXml(t.after)}</Data></Cell>
</Row>
<Row>
<Cell><Data ss:Type="String">${escapeXml(t.score)}</Data></Cell>
<Cell><Data ss:Type="Number">${data.score}</Data></Cell>
<Cell><Data ss:Type="Number">${projected}</Data></Cell>
</Row>
<Row>
<Cell><Data ss:Type="String">${escapeXml(t.availability)}</Data></Cell>
<Cell><Data ss:Type="String">${data.availability}</Data></Cell>
<Cell><Data ss:Type="String">${calcProjectedAvailability(data)}</Data></Cell>
</Row>
<Row>
<Cell><Data ss:Type="String">${escapeXml(t.doraComplianceShort)}</Data></Cell>
<Cell><Data ss:Type="String">${data.doraCompliance}%</Data></Cell>
<Cell><Data ss:Type="String">${projectedDora}%</Data></Cell>
</Row>
<Row>
<Cell><Data ss:Type="String">${escapeXml(t.annualCost)}</Data></Cell>
<Cell><Data ss:Type="Number">${annualCost}</Data></Cell>
<Cell><Data ss:Type="Number">${projectedCost}</Data></Cell>
</Row>
</Table>
</Worksheet>`;

  return `<?xml version="1.0" encoding="UTF-8"?>
<?mso-application progid="Excel.Sheet"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
 xmlns:o="urn:schemas-microsoft-com:office:office"
 xmlns:x="urn:schemas-microsoft-com:office:excel"
 xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
<Styles>
<Style ss:ID="Default" ss:Name="Normal"><Font ss:Size="11"/></Style>
<Style ss:ID="Header"><Font ss:Bold="1" ss:Size="11"/><Interior ss:Color="#F1F5F9" ss:Pattern="Solid"/></Style>
</Styles>
${sheet1}
${sheet2}
${sheet3}
${sheet4}
</Workbook>`;
}

/* ------------------------------------------------------------------ */
/*  Google Calendar helpers                                             */
/* ------------------------------------------------------------------ */

function calcActionDates(action: ActionItem): { start: Date; end: Date } {
  const today = new Date();
  const start = new Date(today);
  start.setDate(today.getDate() + (action.startWeek - 1) * 7);
  // Set to 9:00 AM
  start.setHours(9, 0, 0, 0);
  const end = new Date(start);
  end.setDate(start.getDate() + action.effortWeeks * 7);
  end.setHours(17, 0, 0, 0);
  return { start, end };
}

function formatDateForGCal(d: Date): string {
  return d.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, "");
}

function formatDateForIcs(d: Date): string {
  return d.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, "");
}

function buildGoogleCalendarUrl(
  action: ActionItem,
  locale: string,
  t: Record<string, string>,
): string {
  const { start, end } = calcActionDates(action);
  const title = `${t.calendarEventPrefix} ${action.title[locale] ?? action.title.en}`;
  const details = `${t.calendarPriority}: ${t[action.priority] ?? action.priority}\\n${t.calendarCost}: ${formatEur(action.costEur)}\\n${t.calendarExpectedEffect}: +${action.scoreImpact}`;
  const params = new URLSearchParams({
    action: "TEMPLATE",
    text: title,
    dates: `${formatDateForGCal(start)}/${formatDateForGCal(end)}`,
    details,
  });
  return `https://calendar.google.com/calendar/render?${params.toString()}`;
}

function generateIcsFile(
  actions: ActionItem[],
  locale: string,
  t: Record<string, string>,
): string {
  const events = actions
    .map((action) => {
      const { start, end } = calcActionDates(action);
      const title = `${t.calendarEventPrefix} ${action.title[locale] ?? action.title.en}`;
      const description = `${t.calendarPriority}: ${t[action.priority] ?? action.priority}\\n${t.calendarCost}: ${formatEur(action.costEur)}\\n${t.calendarExpectedEffect}: +${action.scoreImpact}`;
      return `BEGIN:VEVENT
DTSTART:${formatDateForIcs(start)}
DTEND:${formatDateForIcs(end)}
SUMMARY:${title}
DESCRIPTION:${description}
STATUS:CONFIRMED
END:VEVENT`;
    })
    .join("\n");

  return `BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//FaultRay//Remediation Plan//EN
${events}
END:VCALENDAR`;
}

/* ------------------------------------------------------------------ */
/*  Task management helpers                                             */
/* ------------------------------------------------------------------ */

const TASK_STORAGE_KEY = "faultray_remediation_tasks";

function loadTaskStates(): TaskStatesMap {
  try {
    const raw = localStorage.getItem(TASK_STORAGE_KEY);
    if (raw) return JSON.parse(raw) as TaskStatesMap;
  } catch {
    // ignore
  }
  return {};
}

function saveTaskStates(states: TaskStatesMap): void {
  try {
    localStorage.setItem(TASK_STORAGE_KEY, JSON.stringify(states));
  } catch {
    // QuotaExceededError: storage full — silently ignore to avoid breaking UX
  }
}

function getTaskState(states: TaskStatesMap, actionId: number): TaskState {
  return states[actionId] ?? { assignee: "", status: "todo", comment: "", deadline: "" };
}

function statusBadgeVariant(status: TaskStatus): "default" | "yellow" | "gold" | "green" {
  switch (status) {
    case "todo": return "default";
    case "in_progress": return "yellow";
    case "in_review": return "gold";
    case "done": return "green";
  }
}

/* ------------------------------------------------------------------ */
/*  Task export helpers                                                 */
/* ------------------------------------------------------------------ */

function buildActionDescription(
  action: ActionItem,
  locale: string,
  t: Record<string, string>,
  taskState?: TaskState,
): string {
  const lines = [
    `${t.priority}: ${t[action.priority] ?? action.priority}`,
    `${t.effort}: ${action.effortWeeks} ${action.effortWeeks > 1 ? t.weeks : t.week}`,
    `${t.cost}: ${formatEur(action.costEur)}`,
    `${t.expectedEffect}: +${action.scoreImpact}`,
  ];
  if (taskState?.assignee) lines.push(`${t.assignee}: ${taskState.assignee}`);
  if (taskState?.deadline) lines.push(`${t.deadline}: ${taskState.deadline}`);
  if (taskState?.comment) lines.push(`${t.comment}: ${taskState.comment}`);
  lines.push("", "Generated by FaultRay");
  return lines.join("\n");
}

function buildActionMarkdown(
  action: ActionItem,
  locale: string,
  t: Record<string, string>,
  taskState?: TaskState,
): string {
  const title = action.title[locale] ?? action.title.en;
  const lines = [
    `## ${title}`,
    "",
    `- **${t.priority}**: ${t[action.priority] ?? action.priority}`,
    `- **${t.effort}**: ${action.effortWeeks} ${action.effortWeeks > 1 ? t.weeks : t.week}`,
    `- **${t.cost}**: ${formatEur(action.costEur)}`,
    `- **${t.expectedEffect}**: +${action.scoreImpact}`,
  ];
  if (taskState?.assignee) lines.push(`- **${t.assignee}**: ${taskState.assignee}`);
  if (taskState?.deadline) lines.push(`- **${t.deadline}**: ${taskState.deadline}`);
  if (taskState?.comment) lines.push("", `> ${taskState.comment}`);
  return lines.join("\n");
}

function buildAllActionsMarkdown(
  actions: ActionItem[],
  taskStates: TaskStatesMap,
  locale: string,
  t: Record<string, string>,
): string {
  const header = `| # | ${t.action} | ${t.priority} | ${t.effort} | ${t.cost} | ${t.expectedEffect} |`;
  const sep = "|---|---|---|---|---|---|";
  const rows = actions.map((a) => {
    const title = a.title[locale] ?? a.title.en;
    return `| ${a.id} | ${title} | ${t[a.priority] ?? a.priority} | ${a.effortWeeks} ${a.effortWeeks > 1 ? t.weeks : t.week} | ${formatEur(a.costEur)} | +${a.scoreImpact} |`;
  });
  return [header, sep, ...rows].join("\n");
}

function buildAllActionsCsv(
  actions: ActionItem[],
  taskStates: TaskStatesMap,
  locale: string,
  t: Record<string, string>,
): string {
  const csvEscape = (s: string) => `"${s.replace(/"/g, '""')}"`;
  const header = ["#", t.action, t.priority, t.assignee, t.status ?? "Status", t.effort, t.cost, t.expectedEffect, t.deadline].map(csvEscape).join(",");
  const rows = actions.map((a) => {
    const ts = taskStates[a.id] ?? { assignee: "", status: "todo" as TaskStatus, comment: "", deadline: "" };
    const statusMap: Record<TaskStatus, string> = {
      todo: t.statusTodo ?? "To Do",
      in_progress: t.statusInProgress ?? "In Progress",
      in_review: t.statusInReview ?? "In Review",
      done: t.statusDone ?? "Done",
    };
    const { start } = calcActionDates(a);
    return [
      String(a.id),
      csvEscape(a.title[locale] ?? a.title.en),
      csvEscape(t[a.priority] ?? a.priority),
      csvEscape(ts.assignee || ""),
      csvEscape(statusMap[ts.status] ?? ts.status),
      String(a.effortWeeks),
      String(a.costEur),
      `+${a.scoreImpact}`,
      csvEscape(ts.deadline || start.toISOString().split("T")[0]),
    ].join(",");
  });
  return [header, ...rows].join("\n");
}

/* ------------------------------------------------------------------ */
/*  Share helpers                                                       */
/* ------------------------------------------------------------------ */

function buildShareText(
  action: ActionItem,
  locale: string,
  t: Record<string, string>,
): string {
  const title = action.title[locale] ?? action.title.en;
  return `[FaultRay] ${title}\n${t.priority}: ${t[action.priority] ?? action.priority} | ${t.cost}: ${formatEur(action.costEur)} | ${t.expectedEffect}: +${action.scoreImpact}`;
}

function buildPlanShareText(
  data: RemediationData,
  locale: string,
  t: Record<string, string>,
): string {
  const projected = calcProjectedScore(data);
  const lines = [
    `[FaultRay] ${t.title}`,
    `${t.currentScore}: ${data.score}/100 -> ${t.projectedScore}: ${projected}/100`,
    `${t.doraCompliance}: ${data.doraCompliance}%`,
    `${t.action}: ${data.actions.length}`,
    "",
    ...data.actions.map((a) => `- ${a.title[locale] ?? a.title.en} (${t[a.priority] ?? a.priority})`),
  ];
  return lines.join("\n");
}

/* ------------------------------------------------------------------ */
/*  Dropdown Component                                                  */
/* ------------------------------------------------------------------ */

function DropdownMenu({
  trigger,
  items,
  align = "right",
}: {
  trigger: React.ReactNode;
  items: Array<{ label: string; icon?: React.ReactNode; onClick: () => void; separator?: boolean }>;
  align?: "left" | "right";
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    // KEYBOARD-06: Escキーでドロップダウンを閉じる
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    if (open) {
      document.addEventListener("mousedown", handleClickOutside);
      document.addEventListener("keydown", handleKeyDown);
      return () => {
        document.removeEventListener("mousedown", handleClickOutside);
        document.removeEventListener("keydown", handleKeyDown);
      };
    }
  }, [open]);

  return (
    <div className="relative" ref={ref}>
      <div role="button" tabIndex={0} aria-expanded={open} onClick={() => setOpen(!open)} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setOpen(!open); } }}>{trigger}</div>
      {open && (
        <div
          className={`absolute z-50 mt-1 min-w-[200px] bg-[#1a1f2e] border border-[#2d3548] rounded-lg shadow-xl py-1 ${
            align === "right" ? "right-0" : "left-0"
          }`}
        >
          {items.map((item, i) => (
            <div key={i}>
              {item.separator && i > 0 && <div className="border-t border-[#2d3548] my-1" />}
              <button
                onClick={() => {
                  item.onClick();
                  setOpen(false);
                }}
                className="w-full flex items-center gap-2 px-3 py-2 text-sm text-[#e2e8f0] hover:bg-white/[0.06] transition-colors text-left"
              >
                {item.icon}
                {item.label}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export default function RemediationPage() {
  const locale = useLocale();
  // eslint-disable-next-line react-hooks/globals
  _activeLocale = locale;  // Set for formatEur currency conversion
  const t = appDict.remediation[locale] ?? appDict.remediation.en;
  const tAny = t as unknown as Record<string, string>;
  const [data, setData] = useState<RemediationData | null>(null);
  const [expandedAction, setExpandedAction] = useState<number | null>(null);
  const [isDemo, setIsDemo] = useState(false);
  const loadedRef = useRef(false);
  const [taskStates, setTaskStates] = useState<TaskStatesMap>({});
  const [taskFilter, setTaskFilter] = useState<TaskFilter>("all");
  const [editingTaskId, setEditingTaskId] = useState<number | null>(null);
  const [editForm, setEditForm] = useState<TaskState>({ assignee: "", status: "todo", comment: "", deadline: "" });
  const [toast, setToast] = useState<string | null>(null);

  const showToast = useCallback((msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 2500);
  }, []);

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
    setTaskStates(loadTaskStates());
  }, []);

  const loadDemo = useCallback(() => {
    setData(DEMO_DATA);
    setIsDemo(true);
  }, []);

  const handleDownloadHtml = useCallback(() => {
    if (!data) return;
    const html = generateHtmlReport(data, tAny, locale);
    downloadFile(html, `faultray-remediation-plan-${locale}.html`, "text/html;charset=utf-8");
  }, [data, tAny, locale]);

  const handleDownloadPdf = useCallback(() => {
    if (!data) return;
    const html = generateHtmlReport(data, tAny, locale);
    // Use Blob URL instead of document.write to avoid DOM-based XSS
    const blob = new Blob([html], { type: "text/html;charset=utf-8" });
    const blobUrl = URL.createObjectURL(blob);
    const win = window.open(blobUrl, "_blank");
    if (win) {
      setTimeout(() => {
        win.print();
        URL.revokeObjectURL(blobUrl);
      }, 800);
    } else {
      URL.revokeObjectURL(blobUrl);
    }
  }, [data, tAny, locale]);

  const handleDownloadExcel = useCallback(() => {
    if (!data) return;
    const xml = generateExcelXml(data, taskStates, tAny, locale);
    downloadFile(xml, `faultray-remediation-plan-${locale}.xls`, "application/vnd.ms-excel;charset=utf-8");
  }, [data, taskStates, tAny, locale]);

  const handleAddToGoogleCalendar = useCallback(
    (action: ActionItem) => {
      const url = buildGoogleCalendarUrl(action, locale, tAny);
      window.open(url, "_blank");
    },
    [locale, tAny],
  );

  const handleExportAllIcs = useCallback(() => {
    if (!data) return;
    const ics = generateIcsFile(data.actions, locale, tAny);
    downloadFile(ics, "faultray-remediation-plan.ics", "text/calendar;charset=utf-8");
  }, [data, locale, tAny]);

  const handleStartEdit = useCallback(
    (actionId: number) => {
      setEditingTaskId(actionId);
      setEditForm(getTaskState(taskStates, actionId));
    },
    [taskStates],
  );

  const handleSaveTask = useCallback(() => {
    if (editingTaskId === null) return;
    const next = { ...taskStates, [editingTaskId]: editForm };
    setTaskStates(next);
    saveTaskStates(next);
    setEditingTaskId(null);
  }, [editingTaskId, editForm, taskStates]);

  const handleCancelEdit = useCallback(() => {
    setEditingTaskId(null);
  }, []);

  /* ---- Task export handlers ---- */

  const handleExportToJira = useCallback(
    (action: ActionItem) => {
      const settings = loadIntegrationSettings();
      if (!settings.jiraDomain) {
        showToast(tAny.jiraNotConfigured ?? "Jira domain not configured");
        return;
      }
      const title = action.title[locale] ?? action.title.en;
      const desc = buildActionDescription(action, locale, tAny, taskStates[action.id]);
      const url = `https://${settings.jiraDomain}/secure/CreateIssue!default.jspa?summary=${encodeURIComponent(title)}&description=${encodeURIComponent(desc)}`;
      window.open(url, "_blank");
    },
    [locale, tAny, taskStates, showToast],
  );

  const handleExportToBacklog = useCallback(
    (action: ActionItem) => {
      const settings = loadIntegrationSettings();
      if (!settings.backlogSpace) {
        showToast(tAny.backlogNotConfigured ?? "Backlog space not configured");
        return;
      }
      const title = action.title[locale] ?? action.title.en;
      const desc = buildActionDescription(action, locale, tAny, taskStates[action.id]);
      const url = `https://${settings.backlogSpace}/add/FAULTRAY?summary=${encodeURIComponent(title)}&description=${encodeURIComponent(desc)}`;
      window.open(url, "_blank");
    },
    [locale, tAny, taskStates, showToast],
  );

  const handleExportToTrello = useCallback(
    (action: ActionItem) => {
      const title = action.title[locale] ?? action.title.en;
      const desc = buildActionDescription(action, locale, tAny, taskStates[action.id]);
      const url = `https://trello.com/add-card?name=${encodeURIComponent(title)}&desc=${encodeURIComponent(desc)}`;
      window.open(url, "_blank");
    },
    [locale, tAny, taskStates],
  );

  const handleCopyForTool = useCallback(
    (action: ActionItem) => {
      const md = buildActionMarkdown(action, locale, tAny, taskStates[action.id]);
      navigator.clipboard.writeText(md);
      showToast(tAny.copiedToClipboard ?? "Copied!");
    },
    [locale, tAny, taskStates, showToast],
  );

  const handleDownloadAllCsv = useCallback(() => {
    if (!data) return;
    const csv = buildAllActionsCsv(data.actions, taskStates, locale, tAny);
    downloadFile(csv, `faultray-actions-${locale}.csv`, "text/csv;charset=utf-8");
  }, [data, taskStates, locale, tAny]);

  const handleCopyAllMarkdown = useCallback(() => {
    if (!data) return;
    const md = buildAllActionsMarkdown(data.actions, taskStates, locale, tAny);
    navigator.clipboard.writeText(md);
    showToast(tAny.copiedToClipboard ?? "Copied!");
  }, [data, taskStates, locale, tAny, showToast]);

  /* ---- Share handlers ---- */

  const handleCopyLink = useCallback(() => {
    navigator.clipboard.writeText(window.location.href);
    showToast(tAny.copiedToClipboard ?? "Copied!");
  }, [showToast, tAny]);

  const handleShareEmail = useCallback(
    (text: string, subject?: string) => {
      const subj = subject ?? tAny.emailSubject ?? "FaultRay Remediation Plan";
      window.location.href = `mailto:?subject=${encodeURIComponent(subj)}&body=${encodeURIComponent(text)}`;
    },
    [tAny],
  );

  const handleShareSlack = useCallback(
    async (text: string) => {
      const settings = loadIntegrationSettings();
      // Validate webhook URL to prevent SSRF — must be an official Slack incoming webhook
      const webhookUrl = settings.slackWebhook;
      if (!webhookUrl || !webhookUrl.startsWith("https://hooks.slack.com/")) {
        // Fallback to Slack share URL
        const url = `https://slack.com/share?text=${encodeURIComponent(text)}`;
        window.open(url, "_blank");
        return;
      }
      try {
        await fetch(webhookUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text }),
        });
        showToast(tAny.slackSent ?? "Sent to Slack!");
      } catch {
        // CORS likely - fallback to URL
        const url = `https://slack.com/share?text=${encodeURIComponent(text)}`;
        window.open(url, "_blank");
      }
    },
    [showToast, tAny],
  );

  const handleShareTeams = useCallback(
    (text: string) => {
      const url = `https://teams.microsoft.com/share?msgText=${encodeURIComponent(text)}&href=${encodeURIComponent(window.location.href)}`;
      window.open(url, "_blank");
    },
    [],
  );

  const handleCopyText = useCallback(
    (text: string) => {
      navigator.clipboard.writeText(text);
      showToast(tAny.copiedToClipboard ?? "Copied!");
    },
    [showToast, tAny],
  );

  const buildTaskExportItems = useCallback(
    (action: ActionItem) => [
      { label: tAny.exportToJira ?? "Create in Jira", icon: <ExternalLink size={14} />, onClick: () => handleExportToJira(action) },
      { label: tAny.exportToBacklog ?? "Create in Backlog", icon: <ExternalLink size={14} />, onClick: () => handleExportToBacklog(action) },
      { label: tAny.exportToTrello ?? "Add to Trello", icon: <ExternalLink size={14} />, onClick: () => handleExportToTrello(action) },
      { label: tAny.copyForAsana ?? "Copy for Asana", icon: <Copy size={14} />, onClick: () => handleCopyForTool(action), separator: true },
      { label: tAny.copyForNotion ?? "Copy for Notion", icon: <Copy size={14} />, onClick: () => handleCopyForTool(action) },
    ],
    [tAny, handleExportToJira, handleExportToBacklog, handleExportToTrello, handleCopyForTool],
  );

  const buildTaskShareItems = useCallback(
    (action: ActionItem) => {
      const text = buildShareText(action, locale, tAny);
      return [
        { label: tAny.copyLink ?? "Copy Link", icon: <Link2 size={14} />, onClick: handleCopyLink },
        { label: tAny.shareByEmail ?? "Share by Email", icon: <Mail size={14} />, onClick: () => handleShareEmail(text) },
        { label: tAny.sendToSlack ?? "Send to Slack", icon: <MessageSquare size={14} />, onClick: () => handleShareSlack(text), separator: true },
        { label: tAny.sendToTeams ?? "Send to Teams", icon: <ExternalLink size={14} />, onClick: () => handleShareTeams(text) },
        { label: tAny.copyText ?? "Copy Text", icon: <Copy size={14} />, onClick: () => handleCopyText(text), separator: true },
      ];
    },
    [locale, tAny, handleCopyLink, handleShareEmail, handleShareSlack, handleShareTeams, handleCopyText],
  );

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

  const planShareText = buildPlanShareText(data, locale, tAny);

  return (
    <div className="max-w-[1200px] mx-auto px-6 py-10">
      {/* Toast notification */}
      {toast && (
        <div className="fixed top-4 right-4 z-[100] px-4 py-2 rounded-lg bg-emerald-600 text-white text-sm font-medium shadow-lg animate-in fade-in duration-200">
          {toast}
        </div>
      )}

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
          <Button variant="secondary" size="sm" onClick={handleDownloadExcel}>
            <Download size={14} />
            {t.downloadExcel}
          </Button>
          <Button variant="secondary" size="sm" onClick={handleDownloadHtml}>
            <FileText size={14} />
            {t.downloadHtml}
          </Button>
          <Button size="sm" onClick={handleDownloadPdf}>
            <Download size={14} />
            {t.downloadPdf}
          </Button>
          <DropdownMenu
            trigger={
              <Button variant="secondary" size="sm">
                <Share2 size={14} />
                {t.share}
                <ChevronDown size={12} />
              </Button>
            }
            items={[
              { label: tAny.copyLink ?? "Copy Link", icon: <Link2 size={14} />, onClick: handleCopyLink },
              { label: tAny.shareByEmail ?? "Share by Email", icon: <Mail size={14} />, onClick: () => handleShareEmail(planShareText) },
              { label: tAny.sendToSlack ?? "Send to Slack", icon: <MessageSquare size={14} />, onClick: () => handleShareSlack(planShareText), separator: true },
              { label: tAny.sendToTeams ?? "Send to Teams", icon: <ExternalLink size={14} />, onClick: () => handleShareTeams(planShareText) },
              { label: tAny.copyText ?? "Copy Text", icon: <Copy size={14} />, onClick: () => handleCopyText(planShareText), separator: true },
            ]}
          />
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
              <th scope="col" className="py-3 px-4 text-left">#</th>
              <th scope="col" className="py-3 px-4 text-left">{t.action}</th>
              <th scope="col" className="py-3 px-4 text-left">{t.priority}</th>
              <th scope="col" className="py-3 px-4 text-left">{t.effort}</th>
              <th scope="col" className="py-3 px-4 text-left">{t.cost}</th>
              <th scope="col" className="py-3 px-4 text-left">{t.expectedEffect}</th>
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

      {/* F. Task Management */}
      <h2 className="text-lg font-bold mb-4 flex items-center gap-2">
        <ListFilter size={20} className="text-[#FFD700]" />
        {t.taskManagement}
      </h2>
      {(() => {
        const statusLabel = (s: TaskStatus): string => {
          const map: Record<TaskStatus, keyof typeof t> = {
            todo: "statusTodo",
            in_progress: "statusInProgress",
            in_review: "statusInReview",
            done: "statusDone",
          };
          return t[map[s]] ?? s;
        };
        const doneCount = data.actions.filter(
          (a) => getTaskState(taskStates, a.id).status === "done",
        ).length;
        const totalCount = data.actions.length;
        const pctDone = totalCount > 0 ? Math.round((doneCount / totalCount) * 100) : 0;
        const filtered =
          taskFilter === "all"
            ? data.actions
            : data.actions.filter((a) => getTaskState(taskStates, a.id).status === taskFilter);

        return (
          <Card className="mb-10">
            {/* Progress bar + bulk export */}
            <div className="flex items-center justify-between mb-4">
              <span className="text-sm text-[#94a3b8]">
                {t.progress}: {doneCount}/{totalCount} ({pctDone}%)
              </span>
              <div className="flex items-center gap-2">
                <DropdownMenu
                  trigger={
                    <Button variant="secondary" size="sm">
                      <ExternalLink size={14} />
                      {t.exportAllActions}
                      <ChevronDown size={12} />
                    </Button>
                  }
                  items={[
                    { label: tAny.downloadCsv ?? "Download CSV", icon: <Download size={14} />, onClick: handleDownloadAllCsv },
                    { label: tAny.copyMarkdown ?? "Copy Markdown", icon: <Copy size={14} />, onClick: handleCopyAllMarkdown },
                  ]}
                />
                <Button variant="secondary" size="sm" onClick={handleExportAllIcs}>
                  <CalendarPlus size={14} />
                  {t.exportAllToCalendar}
                </Button>
              </div>
            </div>
            <div className="w-full h-2 bg-white/[0.05] rounded-full mb-6 overflow-hidden">
              <div
                className="h-full bg-emerald-500 rounded-full transition-all duration-500"
                style={{ width: `${pctDone}%` }}
              />
            </div>

            {/* Filter tabs */}
            <div className="flex flex-wrap gap-2 mb-6">
              {(["all", "todo", "in_progress", "in_review", "done"] as TaskFilter[]).map((f) => {
                const labels: Record<TaskFilter, string> = {
                  all: t.filterAll,
                  todo: t.filterTodo,
                  in_progress: t.filterInProgress,
                  in_review: t.filterInReview,
                  done: t.filterDone,
                };
                return (
                  <button
                    key={f}
                    onClick={() => setTaskFilter(f)}
                    className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-colors ${
                      taskFilter === f
                        ? "bg-[#FFD700]/20 text-[#FFD700]"
                        : "bg-white/[0.05] text-[#94a3b8] hover:bg-white/[0.08]"
                    }`}
                  >
                    {labels[f]}
                  </button>
                );
              })}
            </div>

            {/* Task list */}
            <div className="space-y-3">
              {filtered.map((a) => {
                const ts = getTaskState(taskStates, a.id);
                const isEditing = editingTaskId === a.id;
                const { start: actionStart } = calcActionDates(a);
                const defaultDeadline = ts.deadline || actionStart.toISOString().split("T")[0];

                return (
                  <div
                    key={a.id}
                    className="border border-[#1e293b] rounded-lg p-4 hover:border-[#334155] transition-colors"
                  >
                    {/* Header row */}
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-3">
                        <span className="text-xs text-[#64748b] font-mono">#{a.id}</span>
                        <span className="font-medium text-sm">
                          {a.title[locale] ?? a.title.en}
                        </span>
                        <Badge variant={priorityColor(a.priority)}>
                          {t[a.priority] ?? a.priority}
                        </Badge>
                        <Badge variant={statusBadgeVariant(ts.status)}>
                          {statusLabel(ts.status)}
                        </Badge>
                      </div>
                      <div className="flex items-center gap-1">
                        <DropdownMenu
                          trigger={
                            <Button variant="ghost" size="sm" title={t.exportTo}>
                              <ExternalLink size={14} />
                              <ChevronDown size={10} />
                            </Button>
                          }
                          items={buildTaskExportItems(a)}
                        />
                        <DropdownMenu
                          trigger={
                            <Button variant="ghost" size="sm" title={t.share}>
                              <Share2 size={14} />
                              <ChevronDown size={10} />
                            </Button>
                          }
                          items={buildTaskShareItems(a)}
                        />
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleAddToGoogleCalendar(a)}
                          title={t.addToCalendar}
                        >
                          <CalendarPlus size={14} />
                        </Button>
                        {!isEditing && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleStartEdit(a.id)}
                          >
                            <Pencil size={14} />
                            {t.edit}
                          </Button>
                        )}
                      </div>
                    </div>

                    {/* Info row */}
                    <div className="flex items-center gap-4 text-xs text-[#94a3b8] mb-2">
                      <span>
                        {t.assignee}: {ts.assignee || t.unassigned}
                      </span>
                      <span>
                        {t.deadline}: {ts.deadline || defaultDeadline}
                      </span>
                      <span>
                        {t.effort}: {a.effortWeeks} {a.effortWeeks > 1 ? t.weeks : t.week}
                      </span>
                      <span className="font-mono">{formatEur(a.costEur)}</span>
                      <span className="font-mono text-emerald-400">+{a.scoreImpact}</span>
                    </div>

                    {/* Expand/Collapse details */}
                    <button
                      onClick={() => setExpandedAction(expandedAction === a.id ? null : a.id)}
                      className="text-xs text-[#FFD700] hover:text-[#FFD700]/80 mt-1 mb-2 flex items-center gap-1 transition-colors"
                    >
                      <ChevronDown size={12} className={`transition-transform ${expandedAction === a.id ? "rotate-180" : ""}`} />
                      {expandedAction === a.id ? (tAny.hideDetails ?? "Hide details") : (tAny.showDetails ?? "Show details")}
                    </button>

                    {expandedAction === a.id && (
                      <div className="bg-white/[0.02] border border-[#1e293b] rounded-lg p-4 mb-2 space-y-3 text-sm">
                        {/* What to do */}
                        <div>
                          <p className="text-xs text-[#64748b] uppercase tracking-wider mb-1">{tAny.whatToDo ?? "What to do"}</p>
                          <p className="text-[#e2e8f0]">
                            {a.priority === "critical"
                              ? (tAny.criticalDesc ?? "This is a critical infrastructure vulnerability. Immediate remediation required to prevent service outage. Add redundancy, configure automatic failover, and implement health checks.")
                              : a.priority === "high"
                              ? (tAny.highDesc ?? "High priority infrastructure improvement. Address within the current sprint. Add replicas, configure circuit breakers, or improve monitoring coverage.")
                              : (tAny.mediumDesc ?? "General infrastructure hardening. Enable encryption in transit, add network segmentation, implement chaos engineering practices, and automate disaster recovery testing.")}
                          </p>
                        </div>

                        {/* Impact breakdown */}
                        <div>
                          <p className="text-xs text-[#64748b] uppercase tracking-wider mb-1">{tAny.impactBreakdown ?? "Impact"}</p>
                          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                            <div className="bg-[#0d1117] rounded p-2">
                              <p className="text-[10px] text-[#475569]">{tAny.scoreGain ?? "Score gain"}</p>
                              <p className="text-emerald-400 font-mono font-bold">+{a.scoreImpact}</p>
                            </div>
                            <div className="bg-[#0d1117] rounded p-2">
                              <p className="text-[10px] text-[#475569]">{tAny.doraImpactLabel ?? "DORA impact"}</p>
                              <p className="text-[#FFD700] font-mono font-bold">+{a.doraImpact}%</p>
                            </div>
                            <div className="bg-[#0d1117] rounded p-2">
                              <p className="text-[10px] text-[#475569]">{t.cost}</p>
                              <p className="text-[#e2e8f0] font-mono font-bold">{formatEur(a.costEur)}</p>
                            </div>
                            <div className="bg-[#0d1117] rounded p-2">
                              <p className="text-[10px] text-[#475569]">{t.effort}</p>
                              <p className="text-[#e2e8f0] font-mono font-bold">{a.effortWeeks} {a.effortWeeks > 1 ? t.weeks : t.week}</p>
                            </div>
                          </div>
                        </div>

                        {/* Steps */}
                        <div>
                          <p className="text-xs text-[#64748b] uppercase tracking-wider mb-1">{tAny.steps ?? "Steps"}</p>
                          <ol className="space-y-1 text-xs text-[#94a3b8] list-decimal list-inside">
                            {a.priority === "critical" ? (
                              <>
                                <li>{tAny.step1Critical ?? "Assess current single point of failure and blast radius"}</li>
                                <li>{tAny.step2Critical ?? "Design redundancy architecture (active-passive or active-active)"}</li>
                                <li>{tAny.step3Critical ?? "Implement failover mechanism with automated health checks"}</li>
                                <li>{tAny.step4Critical ?? "Run FaultRay simulation to verify improvement"}</li>
                                <li>{tAny.step5Critical ?? "Deploy to production with monitoring alerts"}</li>
                              </>
                            ) : a.priority === "high" ? (
                              <>
                                <li>{tAny.step1High ?? "Review affected component topology and dependencies"}</li>
                                <li>{tAny.step2High ?? "Add replica or circuit breaker as appropriate"}</li>
                                <li>{tAny.step3High ?? "Configure monitoring and alerting thresholds"}</li>
                                <li>{tAny.step4High ?? "Run FaultRay simulation to verify improvement"}</li>
                              </>
                            ) : (
                              <>
                                <li>{tAny.step1Medium ?? "Audit current security and reliability posture"}</li>
                                <li>{tAny.step2Medium ?? "Enable encryption, network segmentation, and access controls"}</li>
                                <li>{tAny.step3Medium ?? "Set up automated chaos engineering tests"}</li>
                                <li>{tAny.step4Medium ?? "Implement DR runbooks and test failover procedures"}</li>
                                <li>{tAny.step5Medium ?? "Run FaultRay simulation to verify all improvements"}</li>
                              </>
                            )}
                          </ol>
                        </div>

                        {/* Schedule */}
                        <div className="flex items-center gap-4 text-xs pt-2 border-t border-[#1e293b]">
                          <span className="text-[#64748b]">{tAny.scheduledStart ?? "Start"}: <span className="text-[#e2e8f0] font-mono">{calcActionDates(a).start.toLocaleDateString(locale === "ja" ? "ja-JP" : locale === "ko" ? "ko-KR" : locale === "zh" ? "zh-CN" : "en-US")}</span></span>
                          <span className="text-[#64748b]">{tAny.scheduledEnd ?? "End"}: <span className="text-[#e2e8f0] font-mono">{calcActionDates(a).end.toLocaleDateString(locale === "ja" ? "ja-JP" : locale === "ko" ? "ko-KR" : locale === "zh" ? "zh-CN" : "en-US")}</span></span>
                          <Button variant="ghost" size="sm" onClick={() => handleAddToGoogleCalendar(a)} className="ml-auto">
                            <CalendarPlus size={12} />
                            {tAny.addToCalendar ?? "Add to calendar"}
                          </Button>
                        </div>
                      </div>
                    )}

                    {/* Comment display */}
                    {ts.comment && !isEditing && (
                      <p className="text-xs text-[#64748b] bg-white/[0.02] rounded px-3 py-2 mt-2">
                        {ts.comment}
                      </p>
                    )}

                    {/* Edit form */}
                    {isEditing && (
                      <div className="mt-3 space-y-3 border-t border-[#1e293b] pt-3">
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                          <div>
                            <label className="block text-[10px] text-[#64748b] uppercase tracking-wider mb-1">
                              {t.assignee}
                            </label>
                            <input
                              type="text"
                              value={editForm.assignee}
                              onChange={(e) =>
                                setEditForm({ ...editForm, assignee: e.target.value })
                              }
                              aria-label={t.assignee}
                              className="w-full bg-white/[0.05] border border-[#1e293b] rounded-lg px-3 py-1.5 text-sm text-white focus:border-[#FFD700] focus:outline-none"
                              placeholder={t.unassigned}
                            />
                          </div>
                          <div>
                            <label className="block text-[10px] text-[#64748b] uppercase tracking-wider mb-1">
                              Status
                            </label>
                            <select
                              value={editForm.status}
                              onChange={(e) =>
                                setEditForm({
                                  ...editForm,
                                  status: e.target.value as TaskStatus,
                                })
                              }
                              aria-label="Task status"
                              className="w-full bg-white/[0.05] border border-[#1e293b] rounded-lg px-3 py-1.5 text-sm text-white focus:border-[#FFD700] focus:outline-none"
                            >
                              <option value="todo">{t.statusTodo}</option>
                              <option value="in_progress">{t.statusInProgress}</option>
                              <option value="in_review">{t.statusInReview}</option>
                              <option value="done">{t.statusDone}</option>
                            </select>
                          </div>
                          <div>
                            <label className="block text-[10px] text-[#64748b] uppercase tracking-wider mb-1">
                              {t.deadline}
                            </label>
                            <input
                              type="date"
                              value={editForm.deadline || defaultDeadline}
                              onChange={(e) =>
                                setEditForm({ ...editForm, deadline: e.target.value })
                              }
                              aria-label={t.deadline}
                              className="w-full bg-white/[0.05] border border-[#1e293b] rounded-lg px-3 py-1.5 text-sm text-white focus:border-[#FFD700] focus:outline-none"
                            />
                          </div>
                        </div>
                        <div>
                          <label className="block text-[10px] text-[#64748b] uppercase tracking-wider mb-1">
                            {t.comment}
                          </label>
                          <textarea
                            value={editForm.comment}
                            onChange={(e) =>
                              setEditForm({ ...editForm, comment: e.target.value })
                            }
                            rows={2}
                            aria-label={t.comment}
                            className="w-full bg-white/[0.05] border border-[#1e293b] rounded-lg px-3 py-1.5 text-sm text-white focus:border-[#FFD700] focus:outline-none resize-none"
                            placeholder={t.commentPlaceholder}
                          />
                        </div>
                        <div className="flex items-center gap-2">
                          <Button size="sm" onClick={handleSaveTask}>
                            <Check size={14} />
                            {t.save}
                          </Button>
                          <Button variant="secondary" size="sm" onClick={handleCancelEdit}>
                            <X size={14} />
                            {t.cancel}
                          </Button>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </Card>
        );
      })()}

      {/* G. Export section */}
      <Card className="text-center py-8">
        <h3 className="font-bold mb-4">{t.exportPlan}</h3>
        <div className="flex items-center justify-center gap-4 flex-wrap">
          <Button variant="secondary" onClick={handleDownloadExcel}>
            <Download size={16} />
            {t.downloadExcel}
          </Button>
          <Button variant="secondary" onClick={handleDownloadHtml}>
            <FileText size={16} />
            {t.downloadHtml}
          </Button>
          <Button variant="secondary" onClick={handleExportAllIcs}>
            <CalendarPlus size={16} />
            {t.exportAllToCalendar}
          </Button>
          <Button variant="secondary" onClick={handleDownloadAllCsv}>
            <Download size={16} />
            {t.downloadCsv}
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
