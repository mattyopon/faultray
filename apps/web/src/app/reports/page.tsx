"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useEffect, useState } from "react";
import { api, type ExecutiveReport } from "@/lib/api";
import { FileText, Loader2, Download, AlertTriangle, CheckCircle2, XCircle, Globe, Printer, Activity, Code2 } from "lucide-react";
import Link from "next/link";
import { useLocale } from "@/lib/useLocale";
import { appDict } from "@/i18n/app-dict";

const DEMO_REPORT: ExecutiveReport = {
  title: "FaultRay Infrastructure Resilience Report",
  generated_at: "2026-03-30T12:00:00Z",
  executive_summary: {
    overall_score: 85.2,
    availability_estimate: "99.99%",
    risk_level: "Medium",
    total_components: 12,
    total_scenarios_tested: 2048,
    critical_issues: 3,
    recommendations_count: 8,
  },
  key_findings: [
    { severity: "CRITICAL", finding: "Single point of failure in primary database", impact: "Complete service outage during database failures", recommendation: "Implement automated failover with promotion time < 30s" },
    { severity: "HIGH", finding: "Cache cluster lacks partition tolerance", impact: "30% latency increase during network partitions", recommendation: "Deploy Redis Cluster with 3+ nodes across AZs" },
    { severity: "HIGH", finding: "No circuit breaker pattern", impact: "Cascading failures propagate", recommendation: "Implement circuit breaker with fallback responses" },
    { severity: "MEDIUM", finding: "Health check intervals too long (60s)", impact: "Slow failure detection", recommendation: "Reduce to 10 seconds" },
  ],
  availability_breakdown: { hardware_nines: 5.91, software_nines: 4.0, theoretical_nines: 6.65, bottleneck: "Software layer" },
  compliance_status: {
    dora: { status: "partial", score: 72 },
    soc2: { status: "partial", score: 68 },
    iso27001: { status: "compliant", score: 85 },
  },
  improvement_roadmap: [
    { priority: 1, action: "Database failover automation", effort: "Medium", impact: "+0.5 nines", timeline: "2 weeks" },
    { priority: 2, action: "Circuit breaker implementation", effort: "Low", impact: "+0.3 nines", timeline: "1 week" },
    { priority: 3, action: "Cache cluster upgrade", effort: "Medium", impact: "+0.2 nines", timeline: "1 week" },
    { priority: 4, action: "Health check optimization", effort: "Low", impact: "+0.1 nines", timeline: "1 day" },
  ],
};

// Japanese translations for report content
const JA_FINDINGS: Record<string, { finding: string; impact: string; recommendation: string }> = {
  "Single point of failure in primary database": {
    finding: "プライマリデータベースが単一障害点",
    impact: "データベース障害時にサービス全面停止",
    recommendation: "30秒以内のプロモーション時間でフェイルオーバーを自動化",
  },
  "Cache cluster lacks partition tolerance": {
    finding: "キャッシュクラスタにパーティション耐性が欠如",
    impact: "ネットワーク分断時にレイテンシが30%増加",
    recommendation: "3ノード以上のRedis Clusterを複数AZに展開",
  },
  "No circuit breaker pattern": {
    finding: "サーキットブレーカーパターン未実装",
    impact: "カスケード障害が伝播",
    recommendation: "フォールバック応答付きサーキットブレーカーを実装",
  },
  "Health check intervals too long (60s)": {
    finding: "ヘルスチェック間隔が長すぎる（60秒）",
    impact: "障害検知の遅延",
    recommendation: "10秒に短縮",
  },
};

const JA_ROADMAP: Record<string, { action: string; effort: string }> = {
  "Database failover automation": { action: "データベースフェイルオーバーの自動化", effort: "中" },
  "Circuit breaker implementation": { action: "サーキットブレーカーの実装", effort: "低" },
  "Cache cluster upgrade": { action: "キャッシュクラスタのアップグレード", effort: "中" },
  "Health check optimization": { action: "ヘルスチェックの最適化", effort: "低" },
};

const JA_DORA_PILLARS: Record<string, string> = {
  "Pillar I": "Pillar I: ICTリスク管理フレームワーク",
  "Pillar II": "Pillar II: ICTインシデント管理・報告",
  "Pillar III": "Pillar III: デジタルオペレーショナルレジリエンステスト",
  "Pillar IV": "Pillar IV: ICTサードパーティリスク管理",
  "Pillar V": "Pillar V: 情報共有",
};

function severityBadge(sev: string) {
  switch (sev) {
    case "CRITICAL": return "red" as const;
    case "HIGH": return "yellow" as const;
    case "MEDIUM": return "gold" as const;
    default: return "default" as const;
  }
}

// FUNC-02: レポートカスタマイズ — セクション表示設定
type ReportSection = "summary" | "findings" | "availability" | "compliance" | "roadmap";
const DEFAULT_SECTIONS: Record<ReportSection, boolean> = {
  summary: true,
  findings: true,
  availability: true,
  compliance: true,
  roadmap: true,
};

export default function ReportsPage() {
  const [report, setReport] = useState<ExecutiveReport>(DEMO_REPORT);
  const [loading, setLoading] = useState(true);
  const [reportLang, setReportLang] = useState<"en" | "ja">("en");
  const [showSections, setShowSections] = useState<Record<ReportSection, boolean>>(DEFAULT_SECTIONS);
  const [showCustomize, setShowCustomize] = useState(false);
  const [weeklyNotifEnabled, setWeeklyNotifEnabled] = useState(false);
  const locale = useLocale();
  const t = appDict.reports[locale] ?? appDict.reports.en;

  // Sync reportLang with app locale on first load (reports only support en/ja output)
  useEffect(() => {
    setReportLang(locale === "ja" ? "ja" : "en");
  }, [locale]);

  useEffect(() => {
    api
      .getExecutiveReport("json")
      .then((result) => setReport(result))
      .catch(() => setReport(DEMO_REPORT))
      .finally(() => setLoading(false));
  }, []);

  const downloadJson = () => {
    // Generate report in selected language
    const outputReport = reportLang === "ja" ? generateJaReport(report) : report;
    const blob = new Blob([JSON.stringify(outputReport, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `faultray-report-${reportLang}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // REPORT-01: PDF ワンクリック出力（ブラウザのprint-to-PDFを活用）
  const downloadPdf = () => {
    window.print();
  };

  const downloadHtml = async () => {
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || ""}/api/report-executive?format=html&lang=${reportLang}`);
      const html = await res.text();
      const blob = new Blob([html], { type: "text/html" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `faultray-report-${reportLang}.html`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      // Fallback: generate HTML client-side
      const htmlContent = generateHtmlReport(report, reportLang);
      const blob = new Blob([htmlContent], { type: "text/html" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `faultray-report-${reportLang}.html`;
      a.click();
      URL.revokeObjectURL(url);
    }
  };

  // Display language for report content
  const rl = reportLang;

  return (
    <div className="max-w-[1200px] mx-auto px-6 py-10">
      <div className="flex items-center justify-between mb-10">
        <div>
          <h1 className="text-2xl font-bold mb-1 flex items-center gap-3">
            <FileText size={24} className="text-[#FFD700]" />
            {t.title}
          </h1>
          <p className="text-[#94a3b8] text-sm">{t.subtitle}</p>
        </div>
        <div className="flex items-center gap-2">
          {/* Language selector for report output */}
          <div className="flex items-center gap-2 mr-2 px-3 py-1.5 rounded-lg border border-[#1e293b] bg-[#111827]">
            <Globe size={14} className="text-[#64748b]" />
            <select
              value={reportLang}
              onChange={(e) => setReportLang(e.target.value as "en" | "ja")}
              className="bg-transparent text-sm text-[#94a3b8] focus:outline-none cursor-pointer"
            >
              <option value="en">{t.english}</option>
              <option value="ja">{t.japanese}</option>
            </select>
          </div>
          {/* REPORT-01: PDF ワンクリック出力 */}
          <Button variant="secondary" size="sm" onClick={downloadPdf} title={locale === "ja" ? "PDFとして保存（印刷ダイアログ）" : "Save as PDF (print dialog)"}>
            <Printer size={14} /> PDF
          </Button>
          <Button variant="secondary" size="sm" onClick={downloadJson}>
            <Download size={14} /> JSON
          </Button>
          <Button variant="secondary" size="sm" onClick={downloadHtml}>
            <Download size={14} /> HTML
          </Button>
          {/* JOURNEY-04: Weekly report subscription shortcut */}
          <Button
            variant="secondary"
            size="sm"
            onClick={() => {
              try {
                const notif = JSON.parse(localStorage.getItem("faultray_notifications") ?? "{}");
                notif.weeklySummary = true;
                localStorage.setItem("faultray_notifications", JSON.stringify(notif));
                setWeeklyNotifEnabled(true);
                setTimeout(() => setWeeklyNotifEnabled(false), 3000);
              } catch {
                // ignore
              }
            }}
          >
            <Download size={14} />
            {locale === "ja" ? "週次通知を有効化" : "Enable Weekly Email"}
          </Button>
          {weeklyNotifEnabled && (
            <span className="text-xs text-emerald-400 font-medium">
              {locale === "ja"
                ? "週次レポート通知を有効にしました。設定 → 通知 で変更できます。"
                : "Weekly report emails enabled. Manage in Settings → Notifications."}
            </span>
          )}
          {/* FUNC-02: レポートカスタマイズトグル */}
          <Button
            variant="secondary"
            size="sm"
            onClick={() => setShowCustomize((v) => !v)}
          >
            {locale === "ja" ? "セクション設定" : "Customize"}
          </Button>
        </div>
      </div>

      {/* FUNC-02: セクション表示設定パネル */}
      {showCustomize && (
        <div className="mb-6 p-4 rounded-xl border border-[#1e293b] bg-[#111827] flex flex-wrap gap-3 items-center">
          <span className="text-xs font-semibold text-[#64748b] uppercase tracking-wider mr-2">
            {locale === "ja" ? "表示セクション:" : "Visible sections:"}
          </span>
          {(Object.keys(DEFAULT_SECTIONS) as ReportSection[]).map((section) => (
            <button
              key={section}
              onClick={() => setShowSections((prev) => ({ ...prev, [section]: !prev[section] }))}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-medium transition-colors ${
                showSections[section]
                  ? "border-[#FFD700]/40 bg-[#FFD700]/[0.08] text-[#FFD700]"
                  : "border-[#1e293b] text-[#475569] hover:border-[#334155]"
              }`}
            >
              {showSections[section] ? <CheckCircle2 size={11} /> : <XCircle size={11} />}
              {section.charAt(0).toUpperCase() + section.slice(1)}
            </button>
          ))}
        </div>
      )}

      {loading ? (
        <Card className="flex items-center justify-center py-20">
          <Loader2 size={24} className="animate-spin text-[#FFD700]" />
        </Card>
      ) : (
        <div className="space-y-6">
          {/* Executive Summary — FUNC-02: conditionally shown */}
          {showSections.summary && <div className="grid md:grid-cols-4 gap-6">
            <Card className="text-center">
              <p className="text-xs text-[#64748b] uppercase tracking-wider mb-2">{t.score}</p>
              <p className="text-4xl font-extrabold font-mono text-[#FFD700]">
                {report.executive_summary.overall_score}
              </p>
            </Card>
            <Card className="text-center">
              <p className="text-xs text-[#64748b] uppercase tracking-wider mb-2">{t.availability}</p>
              <p className="text-4xl font-extrabold font-mono text-emerald-400">
                {report.executive_summary.availability_estimate}
              </p>
            </Card>
            <Card className="text-center">
              <p className="text-xs text-[#64748b] uppercase tracking-wider mb-2">{t.scenariosLabel}</p>
              <p className="text-4xl font-extrabold font-mono">
                {report.executive_summary.total_scenarios_tested.toLocaleString()}
              </p>
            </Card>
            <Card className="text-center">
              <p className="text-xs text-[#64748b] uppercase tracking-wider mb-2">{t.critical}</p>
              <p className="text-4xl font-extrabold font-mono text-red-400">
                {report.executive_summary.critical_issues}
              </p>
            </Card>
          </div>}

          {/* Key Findings — FUNC-02: conditionally shown */}
          {showSections.findings && <Card>
            <h3 className="text-lg font-bold mb-4 flex items-center gap-2">
              <AlertTriangle size={18} className="text-red-400" />
              {t.keyFindings}
            </h3>
            <div className="space-y-3">
              {report.key_findings.map((f, i) => {
                const jaData = JA_FINDINGS[f.finding];
                return (
                  <div
                    key={i}
                    className={`p-4 rounded-xl border ${
                      f.severity === "CRITICAL"
                        ? "bg-red-500/5 border-red-500/20"
                        : f.severity === "HIGH"
                          ? "bg-yellow-500/5 border-yellow-500/20"
                          : "bg-white/[0.02] border-[#1e293b]"
                    }`}
                  >
                    <div className="flex items-start gap-3">
                      <Badge variant={severityBadge(f.severity)}>{f.severity}</Badge>
                      <div className="flex-1">
                        <p className="text-sm font-medium">{rl === "ja" && jaData ? jaData.finding : f.finding}</p>
                        <p className="text-xs text-[#64748b] mt-1">{t.impact} {rl === "ja" && jaData ? jaData.impact : f.impact}</p>
                        <p className="text-xs text-emerald-400 mt-1">
                          <CheckCircle2 size={10} className="inline mr-1" />
                          {rl === "ja" && jaData ? jaData.recommendation : f.recommendation}
                        </p>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </Card>}

          {/* Availability Breakdown — FUNC-02: conditionally shown */}
          {showSections.availability && <Card>
            <h3 className="text-lg font-bold mb-4">{t.availabilityBreakdown}</h3>
            <div className="space-y-3">
              {[
                { label: rl === "ja" ? "ハードウェア" : "Hardware", value: report.availability_breakdown.hardware_nines, color: "bg-emerald-400" },
                { label: rl === "ja" ? "ソフトウェア" : "Software", value: report.availability_breakdown.software_nines, color: "bg-[#FFD700]" },
                { label: rl === "ja" ? "理論値" : "Theoretical", value: report.availability_breakdown.theoretical_nines, color: "bg-blue-400" },
              ].map((layer) => (
                <div key={layer.label} className="grid grid-cols-[100px_1fr_60px] items-center gap-4">
                  <span className="text-sm text-[#64748b]">{layer.label}</span>
                  <div className="h-3 bg-white/5 rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full ${layer.color}`}
                      style={{ width: `${(layer.value / 7) * 100}%` }}
                    />
                  </div>
                  <span className="text-sm font-mono font-semibold text-right">{layer.value.toFixed(2)}</span>
                </div>
              ))}
            </div>
            <p className="text-xs text-[#FFD700] mt-3">
              {t.bottleneck} {rl === "ja" ? "ソフトウェア層" : report.availability_breakdown.bottleneck}
            </p>
          </Card>}

          {/* Improvement Roadmap — FUNC-02: conditionally shown */}
          {showSections.roadmap && <Card>
            <h3 className="text-lg font-bold mb-4">{t.improvementRoadmap}</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[#1e293b]">
                    <th className="text-left py-3 px-2 text-[#64748b] font-medium">{t.priority}</th>
                    <th className="text-left py-3 px-2 text-[#64748b] font-medium">{t.action}</th>
                    <th className="text-left py-3 px-2 text-[#64748b] font-medium">{t.effort}</th>
                    <th className="text-left py-3 px-2 text-[#64748b] font-medium">{t.impactCol}</th>
                    <th className="text-left py-3 px-2 text-[#64748b] font-medium">{t.timeline}</th>
                  </tr>
                </thead>
                <tbody>
                  {report.improvement_roadmap.map((item) => {
                    const jaItem = JA_ROADMAP[item.action];
                    return (
                      <tr key={item.priority} className="border-b border-[#1e293b]/50">
                        <td className="py-3 px-2 font-bold text-[#FFD700]">{item.priority}</td>
                        <td className="py-3 px-2">{rl === "ja" && jaItem ? jaItem.action : item.action}</td>
                        <td className="py-3 px-2">
                          <Badge variant={item.effort === "Low" ? "green" : "yellow"}>
                            {rl === "ja" && jaItem ? jaItem.effort : item.effort}
                          </Badge>
                        </td>
                        <td className="py-3 px-2 font-mono text-emerald-400">{item.impact}</td>
                        <td className="py-3 px-2 text-[#94a3b8]">{item.timeline}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Card>}

          {/* DORA Compliance Status — FUNC-02: conditionally shown */}
          {showSections.compliance && <Card>
            <h3 className="text-lg font-bold mb-4">{t.complianceStatus}</h3>
            <div className="grid md:grid-cols-3 gap-4">
              {Object.entries(report.compliance_status).map(([fw, status]) => (
                <div key={fw} className="p-4 rounded-xl border border-[#1e293b] bg-white/[0.02] text-center">
                  <p className="text-lg font-bold uppercase">{fw}</p>
                  <p
                    className="text-3xl font-extrabold font-mono mt-2"
                    style={{ color: status.score >= 80 ? "#10b981" : status.score >= 60 ? "#f59e0b" : "#ef4444" }}
                  >
                    {status.score}%
                  </p>
                  <Badge
                    variant={status.status === "compliant" ? "green" : "yellow"}
                    className="mt-2"
                  >
                    {rl === "ja"
                      ? (status.status === "compliant" ? "準拠" : "一部準拠")
                      : status.status}
                  </Badge>
                </div>
              ))}
            </div>
          </Card>}
        </div>
      )}

      {/* FLOW-11: Cross-links to related observability pages */}
      <div className="flex items-center gap-3 mt-6 pt-4 border-t border-[#1e293b]">
        <span className="text-xs text-[#475569]">{locale === "ja" ? "関連ページ:" : "Related:"}</span>
        <Link href="/traces" className="flex items-center gap-1.5 text-xs text-[#64748b] hover:text-[#94a3b8] transition-colors">
          <Activity size={12} />
          {locale === "ja" ? "トレース" : "Traces"}
        </Link>
        <Link href="/logs" className="flex items-center gap-1.5 text-xs text-[#64748b] hover:text-[#94a3b8] transition-colors">
          <FileText size={12} />
          {locale === "ja" ? "ログ" : "Logs"}
        </Link>
        <Link href="/compliance" className="flex items-center gap-1.5 text-xs text-[#64748b] hover:text-[#94a3b8] transition-colors">
          <CheckCircle2 size={12} />
          {locale === "ja" ? "コンプライアンス" : "Compliance"}
        </Link>
        {/* FLOW-02: 改善提案からIaCページへの遷移リンク */}
        <Link href="/iac" className="flex items-center gap-1.5 text-xs text-[#64748b] hover:text-[#94a3b8] transition-colors">
          <Code2 size={12} />
          {locale === "ja" ? "IaC修正コード" : "IaC Fixes"}
        </Link>
      </div>
    </div>
  );
}

// Generate Japanese version of report for JSON download
function generateJaReport(report: ExecutiveReport) {
  return {
    ...report,
    title: "FaultRay インフラレジリエンスレポート",
    executive_summary: {
      ...report.executive_summary,
      risk_level: report.executive_summary.risk_level === "Medium" ? "中" : report.executive_summary.risk_level === "High" ? "高" : "低",
    },
    key_findings: report.key_findings.map((f) => {
      const ja = JA_FINDINGS[f.finding];
      return ja ? { ...f, finding: ja.finding, impact: ja.impact, recommendation: ja.recommendation } : f;
    }),
    availability_breakdown: {
      ...report.availability_breakdown,
      bottleneck: "ソフトウェア層",
    },
    improvement_roadmap: report.improvement_roadmap.map((item) => {
      const ja = JA_ROADMAP[item.action];
      return ja ? { ...item, action: ja.action, effort: ja.effort } : item;
    }),
  };
}

// Generate HTML report for download
function generateHtmlReport(report: ExecutiveReport, lang: "en" | "ja") {
  const isJa = lang === "ja";
  const title = isJa ? "FaultRay インフラレジリエンスレポート" : report.title;

  const findingsHtml = report.key_findings.map((f) => {
    const ja = JA_FINDINGS[f.finding];
    const finding = isJa && ja ? ja.finding : f.finding;
    const impact = isJa && ja ? ja.impact : f.impact;
    const rec = isJa && ja ? ja.recommendation : f.recommendation;
    return `<tr><td>${f.severity}</td><td>${finding}</td><td>${impact}</td><td>${rec}</td></tr>`;
  }).join("\n");

  const roadmapHtml = report.improvement_roadmap.map((item) => {
    const ja = JA_ROADMAP[item.action];
    const action = isJa && ja ? ja.action : item.action;
    const effort = isJa && ja ? ja.effort : item.effort;
    return `<tr><td>${item.priority}</td><td>${action}</td><td>${effort}</td><td>${item.impact}</td><td>${item.timeline}</td></tr>`;
  }).join("\n");

  return `<!DOCTYPE html>
<html lang="${lang}">
<head><meta charset="UTF-8"><title>${title}</title>
<style>body{font-family:system-ui,sans-serif;max-width:900px;margin:0 auto;padding:40px;background:#0a0e1a;color:#e2e8f0}
h1{color:#FFD700}h2{color:#94a3b8;border-bottom:1px solid #1e293b;padding-bottom:8px}
table{width:100%;border-collapse:collapse;margin:16px 0}td,th{text-align:left;padding:8px 12px;border-bottom:1px solid #1e293b}
th{color:#64748b;font-size:12px;text-transform:uppercase}.score{font-size:48px;font-weight:800;color:#FFD700;font-family:monospace}
.stat{text-align:center;padding:20px;border:1px solid #1e293b;border-radius:12px;background:#111827}
.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin:16px 0}
.critical{color:#ef4444}.high{color:#f59e0b}.medium{color:#eab308}</style>
</head>
<body>
<h1>${title}</h1>
<p style="color:#64748b">${isJa ? "生成日時" : "Generated"}: ${new Date(report.generated_at).toLocaleString(lang === "ja" ? "ja-JP" : "en-US")}</p>
<div class="grid">
<div class="stat"><div class="score">${report.executive_summary.overall_score}</div><div style="color:#64748b">${isJa ? "スコア" : "Score"}</div></div>
<div class="stat"><div class="score" style="color:#10b981">${report.executive_summary.availability_estimate}</div><div style="color:#64748b">${isJa ? "可用性" : "Availability"}</div></div>
<div class="stat"><div class="score" style="color:#e2e8f0;font-size:36px">${report.executive_summary.total_scenarios_tested.toLocaleString()}</div><div style="color:#64748b">${isJa ? "テストシナリオ" : "Scenarios"}</div></div>
<div class="stat"><div class="score" style="color:#ef4444">${report.executive_summary.critical_issues}</div><div style="color:#64748b">${isJa ? "重大な問題" : "Critical Issues"}</div></div>
</div>
<h2>${isJa ? "主要な検出事項" : "Key Findings"}</h2>
<table><tr><th>${isJa ? "深刻度" : "Severity"}</th><th>${isJa ? "検出事項" : "Finding"}</th><th>${isJa ? "影響" : "Impact"}</th><th>${isJa ? "推奨対応" : "Recommendation"}</th></tr>${findingsHtml}</table>
<h2>${isJa ? "改善ロードマップ" : "Improvement Roadmap"}</h2>
<table><tr><th>#</th><th>${isJa ? "アクション" : "Action"}</th><th>${isJa ? "工数" : "Effort"}</th><th>${isJa ? "効果" : "Impact"}</th><th>${isJa ? "期間" : "Timeline"}</th></tr>${roadmapHtml}</table>
</body></html>`;
}
