"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useState } from "react";
import { ShieldCheck, CheckCircle2, XCircle, AlertTriangle, ChevronDown, ChevronRight, FileText, ArrowRight, BookOpen, Wrench } from "lucide-react";
import Link from "next/link";
import { useLocale } from "@/lib/useLocale";
import type { Locale } from "@/i18n/config";
import { appDict } from "@/i18n/app-dict";

// DORA 5 Pillar structure
interface PillarControl {
  id: string;
  name: Record<string, string>;
  status: "compliant" | "non_compliant" | "partial";
  evidence: boolean;
  description: Record<string, string>;
  remediation?: Record<string, string>;
}

interface DoraPillar {
  id: string;
  nameKey: "pillar1" | "pillar2" | "pillar3" | "pillar4" | "pillar5";
  score: number;
  controls: PillarControl[];
}

const DORA_PILLARS: DoraPillar[] = [
  {
    id: "pillar1", nameKey: "pillar1", score: 78,
    controls: [
      { id: "P1-01", name: { en: "ICT Risk Management Policy", ja: "ICTリスク管理ポリシー" }, status: "compliant", evidence: true, description: { en: "Documented ICT risk management framework with board-level oversight", ja: "取締役会レベルの監督を伴うICTリスク管理フレームワークが文書化されています" } },
      { id: "P1-02", name: { en: "Asset Management & Classification", ja: "資産管理・分類" }, status: "compliant", evidence: true, description: { en: "All ICT assets are inventoried and classified by criticality", ja: "全ICT資産がインベントリ化され、重要度別に分類されています" } },
      { id: "P1-03", name: { en: "Risk Assessment Process", ja: "リスクアセスメントプロセス" }, status: "partial", evidence: true, description: { en: "Risk assessments performed but not at required frequency", ja: "リスクアセスメントは実施済みですが、要求頻度を満たしていません" }, remediation: { en: "Increase assessment frequency to quarterly", ja: "アセスメント頻度を四半期ごとに引き上げてください" } },
      { id: "P1-04", name: { en: "Protection & Prevention", ja: "保護と予防" }, status: "non_compliant", evidence: false, description: { en: "Insufficient network segmentation between critical and non-critical systems", ja: "重要システムと非重要システム間のネットワーク分離が不十分です" }, remediation: { en: "Implement network segmentation between data and application tiers", ja: "データ層とアプリケーション層間のネットワーク分離を実装してください" } },
    ],
  },
  {
    id: "pillar2", nameKey: "pillar2", score: 62,
    controls: [
      { id: "P2-01", name: { en: "Incident Detection & Classification", ja: "インシデント検知・分類" }, status: "compliant", evidence: true, description: { en: "Automated monitoring and alerting with severity classification", ja: "重要度分類を伴う自動監視・アラートが実装されています" } },
      { id: "P2-02", name: { en: "Major Incident Reporting Obligation", ja: "重大インシデントの報告義務" }, status: "non_compliant", evidence: false, description: { en: "Incident reporting pipeline not automated within 4-hour window", ja: "4時間以内のインシデント報告パイプラインが自動化されていません" }, remediation: { en: "Implement automated incident reporting pipeline with 4-hour SLA", ja: "4時間SLAの自動インシデント報告パイプラインを実装してください" } },
      { id: "P2-03", name: { en: "Incident Response Procedures", ja: "インシデント対応手順" }, status: "partial", evidence: true, description: { en: "Runbooks exist but are incomplete for all failure scenarios", ja: "ランブックは存在しますが、全障害シナリオをカバーしていません" }, remediation: { en: "Complete runbooks for all critical failure scenarios", ja: "全重要障害シナリオのランブックを完成させてください" } },
      { id: "P2-04", name: { en: "Root Cause Analysis", ja: "ルートコーズ分析" }, status: "compliant", evidence: true, description: { en: "Post-incident reviews conducted with documented root cause analysis", ja: "文書化された根本原因分析を伴うインシデント後レビューを実施しています" } },
    ],
  },
  {
    id: "pillar3", nameKey: "pillar3", score: 70,
    controls: [
      { id: "P3-01", name: { en: "Periodic ICT Tool Testing", ja: "ICTツールの定期テスト" }, status: "compliant", evidence: true, description: { en: "Regular resilience testing via FaultRay simulations", ja: "FaultRayシミュレーションによる定期的なレジリエンステストを実施" } },
      { id: "P3-02", name: { en: "Threat-Led Penetration Testing (TLPT)", ja: "脅威ベースの侵入テスト（TLPT）" }, status: "non_compliant", evidence: false, description: { en: "No TLPT program established", ja: "TLPTプログラムが未確立です" }, remediation: { en: "Establish annual TLPT program with qualified external testers", ja: "認定された外部テスターによる年次TLPTプログラムを確立してください" } },
      { id: "P3-03", name: { en: "Test Result Remediation", ja: "テスト結果の是正措置" }, status: "compliant", evidence: true, description: { en: "Test findings tracked and remediated within defined timelines", ja: "テストで発見された事項は追跡され、定められた期限内に是正されています" } },
      { id: "P3-04", name: { en: "Test Evidence Retention", ja: "テスト証跡の保存" }, status: "partial", evidence: false, description: { en: "Test evidence partially retained, retention policy needs update", ja: "テスト証跡は部分的に保存されていますが、保存ポリシーの更新が必要です" }, remediation: { en: "Update evidence retention policy to meet 5-year requirement", ja: "5年の保存要件を満たすよう証跡保存ポリシーを更新してください" } },
    ],
  },
  {
    id: "pillar4", nameKey: "pillar4", score: 55,
    controls: [
      { id: "P4-01", name: { en: "Third-Party Identification & Classification", ja: "サードパーティの識別・分類" }, status: "partial", evidence: true, description: { en: "Major vendors identified but classification incomplete", ja: "主要ベンダーは識別済みですが、分類が完了していません" }, remediation: { en: "Complete vendor classification for all ICT service providers", ja: "全ICTサービスプロバイダーのベンダー分類を完了してください" } },
      { id: "P4-02", name: { en: "Contract Clause Standardization", ja: "契約条項の標準化" }, status: "non_compliant", evidence: false, description: { en: "Contracts lack standardized DORA-required clauses", ja: "契約にDORA要求の標準条項が含まれていません" }, remediation: { en: "Update all vendor contracts with DORA-required provisions", ja: "全ベンダー契約をDORA要求の条項で更新してください" } },
      { id: "P4-03", name: { en: "Concentration Risk Assessment", ja: "集中リスクの評価" }, status: "non_compliant", evidence: false, description: { en: "No concentration risk assessment for cloud providers", ja: "クラウドプロバイダーの集中リスク評価が未実施です" }, remediation: { en: "Perform concentration risk assessment for all critical third parties", ja: "全重要サードパーティの集中リスク評価を実施してください" } },
      { id: "P4-04", name: { en: "Critical Third-Party Oversight", ja: "重要サードパーティの監督" }, status: "partial", evidence: true, description: { en: "Monitoring exists but oversight framework needs formalization", ja: "モニタリングは実施していますが、監督フレームワークの正式化が必要です" }, remediation: { en: "Formalize oversight framework with KPIs and escalation procedures", ja: "KPIとエスカレーション手順を含む監督フレームワークを正式化してください" } },
    ],
  },
  {
    id: "pillar5", nameKey: "pillar5", score: 82,
    controls: [
      { id: "P5-01", name: { en: "Cyber Threat Intelligence Sharing", ja: "サイバー脅威情報の共有" }, status: "compliant", evidence: true, description: { en: "Active participation in industry ISAC", ja: "業界ISACへの積極的な参加" } },
      { id: "P5-02", name: { en: "Incident Information Exchange", ja: "インシデント情報の交換" }, status: "compliant", evidence: true, description: { en: "Established channels for incident information sharing with regulators", ja: "規制当局とのインシデント情報共有チャネルが確立されています" } },
      { id: "P5-03", name: { en: "Cross-Industry Collaboration", ja: "業界間の連携" }, status: "partial", evidence: true, description: { en: "Participating in some cross-industry forums but coverage can be expanded", ja: "一部の業界横断フォーラムに参加していますが、カバレッジの拡大が可能です" }, remediation: { en: "Expand participation to additional cross-sector forums", ja: "追加のクロスセクターフォーラムへの参加を拡大してください" } },
    ],
  },
];

function PillarCard({ pillar, expanded, onToggle, locale }: { pillar: DoraPillar; expanded: boolean; onToggle: () => void; locale: Locale }) {
  const dp = appDict.doraPillars[locale] ?? appDict.doraPillars.en;
  const ct = appDict.compliance[locale] ?? appDict.compliance.en;
  const pillarName = dp[pillar.nameKey];
  const compliantCount = pillar.controls.filter(c => c.status === "compliant").length;
  const totalCount = pillar.controls.length;

  return (
    <Card>
      <button className="w-full text-left" onClick={onToggle}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            {expanded ? <ChevronDown size={16} className="text-[#64748b]" /> : <ChevronRight size={16} className="text-[#64748b]" />}
            <div className="flex-1">
              <p className="font-bold text-sm">{pillarName}</p>
              <p className="text-xs text-[#64748b] mt-0.5">{compliantCount}/{totalCount} {locale === "ja" ? "コントロール準拠" : "controls compliant"}</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {/* Progress bar */}
            <div className="w-24 h-2 bg-white/5 rounded-full overflow-hidden">
              <div
                className="h-full rounded-full transition-all duration-500"
                style={{
                  width: `${pillar.score}%`,
                  backgroundColor: pillar.score >= 80 ? "#10b981" : pillar.score >= 60 ? "#f59e0b" : "#ef4444",
                }}
              />
            </div>
            <span
              className="text-xl font-extrabold font-mono min-w-[50px] text-right"
              style={{ color: pillar.score >= 80 ? "#10b981" : pillar.score >= 60 ? "#f59e0b" : "#ef4444" }}
            >
              {pillar.score}%
            </span>
          </div>
        </div>
      </button>

      {expanded && (
        <div className="mt-4 pt-4 border-t border-[#1e293b] space-y-3">
          {pillar.controls.map((ctrl) => (
            <div
              key={ctrl.id}
              className={`p-4 rounded-xl border ${
                ctrl.status === "compliant"
                  ? "bg-emerald-500/5 border-emerald-500/10"
                  : ctrl.status === "partial"
                    ? "bg-yellow-500/5 border-yellow-500/10"
                    : "bg-red-500/5 border-red-500/10"
              }`}
            >
              <div className="flex items-start gap-3">
                {ctrl.status === "compliant" ? (
                  <CheckCircle2 size={18} className="text-emerald-400 mt-0.5 shrink-0" />
                ) : ctrl.status === "partial" ? (
                  <AlertTriangle size={18} className="text-yellow-400 mt-0.5 shrink-0" />
                ) : (
                  <XCircle size={18} className="text-red-400 mt-0.5 shrink-0" />
                )}
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-sm font-mono text-[#64748b]">{ctrl.id}</span>
                    <span className="text-sm font-medium">{ctrl.name[locale] ?? ctrl.name.en}</span>
                  </div>
                  <p className="text-xs text-[#94a3b8]">{ctrl.description[locale] ?? ctrl.description.en}</p>
                  {ctrl.remediation && (
                    <p className="text-xs text-[#FFD700] mt-2">
                      {ct.remediation} {ctrl.remediation[locale] ?? ctrl.remediation.en}
                    </p>
                  )}
                  <div className="flex items-center gap-2 mt-2">
                    <Badge variant={ctrl.status === "compliant" ? "green" : ctrl.status === "partial" ? "yellow" : "red"}>
                      {ctrl.status === "compliant" ? ct.pass : ctrl.status === "partial" ? ct.partial : ct.fail}
                    </Badge>
                    {ctrl.evidence ? (
                      <Badge variant="default"><FileText size={10} className="mr-1" />{locale === "ja" ? "エビデンスあり" : "Evidence"}</Badge>
                    ) : (
                      <Badge variant="red"><FileText size={10} className="mr-1" />{locale === "ja" ? "エビデンス未整備" : "No Evidence"}</Badge>
                    )}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

export default function CompliancePage() {
  const [expandedPillar, setExpandedPillar] = useState<string | null>("pillar1");
  // DORA-03: サマリーモードとデータモードの切替でUIの圧倒感を軽減
  const [detailMode, setDetailMode] = useState(false);
  const locale = useLocale();
  const t = appDict.compliance[locale] ?? appDict.compliance.en;
  const dp = appDict.doraPillars[locale] ?? appDict.doraPillars.en;

  // Calculate overall stats
  const allControls = DORA_PILLARS.flatMap(p => p.controls);
  const compliantCount = allControls.filter(c => c.status === "compliant").length;
  const partialCount = allControls.filter(c => c.status === "partial").length;
  const nonCompliantCount = allControls.filter(c => c.status === "non_compliant").length;
  const overallScore = Math.round(DORA_PILLARS.reduce((acc, p) => acc + p.score, 0) / DORA_PILLARS.length);

  // Priority actions sorted by pillar score (lowest first)
  const priorityActions = DORA_PILLARS
    .flatMap(p => p.controls
      .filter(c => c.status !== "compliant" && c.remediation)
      .map(c => ({
        pillarName: dp[p.nameKey as keyof typeof dp],
        controlId: c.id,
        controlName: c.name[locale] ?? c.name.en,
        remediation: c.remediation![locale] ?? c.remediation!.en,
        status: c.status,
        pillarScore: p.score,
      }))
    )
    .sort((a, b) => a.pillarScore - b.pillarScore);

  return (
    <div className="max-w-[1200px] mx-auto px-6 py-10">
      <div className="mb-10">
        <h1 className="text-2xl font-bold mb-1 flex items-center gap-3">
          <ShieldCheck size={24} className="text-[#FFD700]" />
          DORA {t.title}
        </h1>
        <p className="text-[#94a3b8] text-sm">
          {locale === "ja"
            ? "DORA 5 Pillarごとの準拠状況と推奨アクション"
            : "DORA 5 Pillar compliance status and recommended actions"}
        </p>
      </div>

      {/* Overall Score */}
      <div className="grid md:grid-cols-4 gap-6 mb-8">
        <Card className="text-center">
          <p className="text-xs text-[#64748b] uppercase tracking-wider mb-2">
            {locale === "ja" ? "DORA 総合準拠率" : "DORA Overall Compliance"}
          </p>
          <p
            className="text-5xl font-extrabold font-mono"
            style={{ color: overallScore >= 80 ? "#10b981" : overallScore >= 60 ? "#f59e0b" : "#ef4444" }}
          >
            {overallScore}%
          </p>
          <Badge
            variant={overallScore >= 80 ? "green" : overallScore >= 60 ? "yellow" : "red"}
            className="mt-2"
          >
            {overallScore >= 80 ? t.compliant : overallScore >= 60 ? t.partial : t.nonCompliant}
          </Badge>
        </Card>
        <Card className="text-center">
          <p className="text-xs text-[#64748b] uppercase tracking-wider mb-2">{t.controlsPassed}</p>
          <p className="text-5xl font-extrabold font-mono text-emerald-400">{compliantCount}</p>
          <p className="text-xs text-[#64748b] mt-2">{allControls.length} {locale === "ja" ? "件中" : "total"}</p>
        </Card>
        <Card className="text-center">
          <p className="text-xs text-[#64748b] uppercase tracking-wider mb-2">{locale === "ja" ? "一部準拠" : "Partial"}</p>
          <p className="text-5xl font-extrabold font-mono text-[#f59e0b]">{partialCount}</p>
          <p className="text-xs text-[#64748b] mt-2">{locale === "ja" ? "追加対応が必要" : "needs improvement"}</p>
        </Card>
        <Card className="text-center">
          <p className="text-xs text-[#64748b] uppercase tracking-wider mb-2">{t.nonCompliantCount}</p>
          <p className="text-5xl font-extrabold font-mono text-red-400">{nonCompliantCount}</p>
          <p className="text-xs text-[#64748b] mt-2">{t.requiresRemediation}</p>
        </Card>
      </div>

      {/* DORA-03: サマリー/詳細切替ボタン */}
      <div className="flex justify-end mb-4">
        <div className="flex rounded-lg overflow-hidden border border-[#1e293b]">
          <button
            onClick={() => setDetailMode(false)}
            className={`px-4 py-2 text-xs font-semibold transition-colors ${!detailMode ? "bg-[#FFD700] text-[#0a0e1a]" : "text-[#94a3b8] hover:text-white hover:bg-white/5"}`}
          >
            {locale === "ja" ? "サマリー" : "Summary"}
          </button>
          <button
            onClick={() => setDetailMode(true)}
            className={`px-4 py-2 text-xs font-semibold transition-colors ${detailMode ? "bg-[#FFD700] text-[#0a0e1a]" : "text-[#94a3b8] hover:text-white hover:bg-white/5"}`}
          >
            {locale === "ja" ? "詳細" : "Details"}
          </button>
        </div>
      </div>

      {/* 5 Pillar Progress Overview */}
      <Card className="mb-8">
        <h3 className="text-lg font-bold mb-4 flex items-center gap-2">
          <ShieldCheck size={18} className="text-[#FFD700]" />
          DORA 5 Pillar {locale === "ja" ? "準拠概要" : "Overview"}
        </h3>
        <div className="space-y-4">
          {DORA_PILLARS.map((pillar) => {
            const shortName = dp[`${pillar.nameKey}Short` as keyof typeof dp];
            return (
              <div key={pillar.id} className="grid grid-cols-[200px_1fr_60px] items-center gap-4">
                <span className="text-sm text-[#94a3b8] truncate">{shortName}</span>
                <div className="h-3 bg-white/5 rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all duration-700"
                    style={{
                      width: `${pillar.score}%`,
                      backgroundColor: pillar.score >= 80 ? "#10b981" : pillar.score >= 60 ? "#f59e0b" : "#ef4444",
                    }}
                  />
                </div>
                <span
                  className="text-sm font-mono font-bold text-right"
                  style={{ color: pillar.score >= 80 ? "#10b981" : pillar.score >= 60 ? "#f59e0b" : "#ef4444" }}
                >
                  {pillar.score}%
                </span>
              </div>
            );
          })}
        </div>
      </Card>

      {/* Pillar Details — DORA-03: 詳細モードのみ表示 */}
      {detailMode && (
        <div className="space-y-4 mb-8">
          {DORA_PILLARS.map((pillar) => (
            <PillarCard
              key={pillar.id}
              pillar={pillar}
              expanded={expandedPillar === pillar.id}
              onToggle={() => setExpandedPillar(expandedPillar === pillar.id ? null : pillar.id)}
              locale={locale}
            />
          ))}
        </div>
      )}

      {/* Priority Action List */}
      <Card>
        <h3 className="text-lg font-bold mb-4 flex items-center gap-2">
          <AlertTriangle size={18} className="text-[#FFD700]" />
          {locale === "ja" ? "優先対応アクション" : "Priority Action Items"}
        </h3>
        <p className="text-xs text-[#64748b] mb-4">
          {locale === "ja"
            ? "準拠率が低いPillarから優先順位付けされています"
            : "Prioritized by lowest pillar compliance score"}
        </p>
        <div className="space-y-3">
          {priorityActions.map((action, i) => (
            <div key={action.controlId} className="flex items-start gap-3 p-3 rounded-lg bg-white/[0.02] border border-[#1e293b]">
              <span className="text-sm font-bold text-[#FFD700] shrink-0 w-6">{i + 1}.</span>
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-sm font-mono text-[#64748b]">{action.controlId}</span>
                  <span className="text-sm font-medium">{action.controlName}</span>
                  <Badge variant={action.status === "partial" ? "yellow" : "red"}>
                    {action.status === "partial" ? (locale === "ja" ? "一部準拠" : "Partial") : (locale === "ja" ? "非準拠" : "Non-Compliant")}
                  </Badge>
                </div>
                <p className="text-xs text-[#94a3b8]">
                  <ArrowRight size={10} className="inline mr-1 text-[#FFD700]" />
                  {action.remediation}
                </p>
                <p className="text-xs text-[#64748b] mt-1">{action.pillarName}</p>
              </div>
            </div>
          ))}
        </div>
      </Card>

      {/* FLOW-12: 改善提案の統一導線 */}
      <div className="flex items-center gap-3 mt-6 pt-4 border-t border-[#1e293b]">
        <span className="text-xs text-[#475569]">{locale === "ja" ? "関連ページ:" : "Related:"}</span>
        <Link href="/reports" className="flex items-center gap-1.5 text-xs text-[#64748b] hover:text-[#94a3b8] transition-colors">
          <BookOpen size={12} />
          {locale === "ja" ? "エグゼクティブレポート" : "Executive Report"}
        </Link>
        <Link href="/remediation" className="flex items-center gap-1.5 text-xs text-[#64748b] hover:text-[#94a3b8] transition-colors">
          <Wrench size={12} />
          {locale === "ja" ? "改善アクション" : "Remediation"}
        </Link>
        {/* FLOW-03: complianceからaudit-reportへの遷移リンク */}
        <Link href="/audit-report" className="flex items-center gap-1.5 text-xs text-[#64748b] hover:text-[#94a3b8] transition-colors">
          <BookOpen size={12} />
          {locale === "ja" ? "監査レポート" : "Audit Report"}
        </Link>
      </div>
    </div>
  );
}
