"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useState } from "react";
import {
  Landmark,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Download,
  ChevronDown,
  ChevronRight,
  FileText,
  ArrowRight,
  Shield,
} from "lucide-react";
import { useLocale } from "@/lib/useLocale";

/* ============================================================
 * Types
 * ============================================================ */

type ControlStatus = "compliant" | "partial" | "non_compliant";

interface FiscCategory {
  id: string;
  nameJa: string;
  nameEn: string;
  score: number;
  status: ControlStatus;
  compliant: number;
  total: number;
  controls: FiscControl[];
}

interface FiscControl {
  id: string;
  description: string;
  status: ControlStatus;
  lastAssessed: string;
  evidence: string | null;
}

interface FiscGap {
  controlId: string;
  severity: "critical" | "high" | "medium";
  description: string;
  remediation: string;
}

/* ============================================================
 * Demo Data
 * ============================================================ */

const DEMO_CATEGORIES: FiscCategory[] = [
  {
    id: "cat1",
    nameJa: "基本方針・組織体制",
    nameEn: "Basic Policy & Organization",
    score: 85,
    status: "partial",
    compliant: 6,
    total: 8,
    controls: [
      { id: "F1-01", description: "情報セキュリティ基本方針の策定・公表",           status: "compliant",     lastAssessed: "2026-03-20", evidence: "policy_v4.pdf" },
      { id: "F1-02", description: "CISO・情報セキュリティ委員会の設置",              status: "compliant",     lastAssessed: "2026-03-15", evidence: "org_chart.pdf" },
      { id: "F1-03", description: "情報セキュリティ規程類の整備",                   status: "partial",       lastAssessed: "2026-02-28", evidence: "rules_v3.pdf" },
      { id: "F1-04", description: "年次セキュリティ監査の実施",                     status: "non_compliant", lastAssessed: "2026-01-15", evidence: null },
    ],
  },
  {
    id: "cat2",
    nameJa: "人的セキュリティ",
    nameEn: "Personnel Security",
    score: 70,
    status: "partial",
    compliant: 3,
    total: 5,
    controls: [
      { id: "F2-01", description: "従業員に対するセキュリティ教育・訓練",           status: "compliant",     lastAssessed: "2026-03-10", evidence: "training_log.pdf" },
      { id: "F2-02", description: "委託先の管理・監督",                              status: "partial",       lastAssessed: "2026-02-20", evidence: "vendor_mgt.pdf" },
      { id: "F2-03", description: "退職時のアクセス権限削除手順",                   status: "non_compliant", lastAssessed: "2026-01-31", evidence: null },
    ],
  },
  {
    id: "cat3",
    nameJa: "物理的セキュリティ",
    nameEn: "Physical Security",
    score: 90,
    status: "compliant",
    compliant: 4,
    total: 4,
    controls: [
      { id: "F3-01", description: "入退室管理システムの設置・運用",                  status: "compliant",     lastAssessed: "2026-03-25", evidence: "access_log.pdf" },
      { id: "F3-02", description: "サーバ室の環境管理（温湿度・火災対応）",          status: "compliant",     lastAssessed: "2026-03-25", evidence: "env_monitor.pdf" },
      { id: "F3-03", description: "媒体の適切な廃棄・管理",                          status: "compliant",     lastAssessed: "2026-03-20", evidence: "media_disposal.pdf" },
      { id: "F3-04", description: "クラウドデータセンターの物理セキュリティ確認",    status: "compliant",     lastAssessed: "2026-03-18", evidence: "cloud_soc.pdf" },
    ],
  },
  {
    id: "cat4",
    nameJa: "技術的セキュリティ",
    nameEn: "Technical Security",
    score: 55,
    status: "non_compliant",
    compliant: 4,
    total: 8,
    controls: [
      { id: "F4-01", description: "アクセス制御・特権管理",                          status: "partial",       lastAssessed: "2026-02-15", evidence: "iam_policy.pdf" },
      { id: "F4-02", description: "暗号化・鍵管理",                                  status: "compliant",     lastAssessed: "2026-03-10", evidence: "kms_config.pdf" },
      { id: "F4-03", description: "脆弱性管理・パッチ対応",                          status: "non_compliant", lastAssessed: "2026-01-20", evidence: null },
      { id: "F4-04", description: "セキュリティイベントの監視・ログ管理",            status: "non_compliant", lastAssessed: "2026-01-20", evidence: null },
    ],
  },
  {
    id: "cat5",
    nameJa: "システム開発・変更管理",
    nameEn: "System Development & Change Management",
    score: 60,
    status: "partial",
    compliant: 3,
    total: 5,
    controls: [
      { id: "F5-01", description: "セキュアな開発標準の策定",                        status: "compliant",     lastAssessed: "2026-03-05", evidence: "dev_standard.pdf" },
      { id: "F5-02", description: "変更管理手順・承認フロー",                        status: "partial",       lastAssessed: "2026-02-25", evidence: "change_log.pdf" },
      { id: "F5-03", description: "本番リリース前のセキュリティテスト",              status: "non_compliant", lastAssessed: "2026-01-10", evidence: null },
    ],
  },
  {
    id: "cat6",
    nameJa: "障害対応・事業継続",
    nameEn: "Incident Response & BCP",
    score: 72,
    status: "partial",
    compliant: 4,
    total: 6,
    controls: [
      { id: "F6-01", description: "インシデント対応計画・手順書",                    status: "compliant",     lastAssessed: "2026-03-20", evidence: "ir_plan.pdf" },
      { id: "F6-02", description: "システム障害時の顧客通知手順",                    status: "compliant",     lastAssessed: "2026-03-15", evidence: "notify_proc.pdf" },
      { id: "F6-03", description: "BCP/DRテストの年次実施",                         status: "partial",       lastAssessed: "2026-02-10", evidence: "bcp_test_2025.pdf" },
      { id: "F6-04", description: "RTO/RPO目標値の設定と検証",                       status: "non_compliant", lastAssessed: "2026-01-05", evidence: null },
    ],
  },
  {
    id: "cat7",
    nameJa: "外部委託管理",
    nameEn: "Outsourcing Management",
    score: 45,
    status: "non_compliant",
    compliant: 2,
    total: 5,
    controls: [
      { id: "F7-01", description: "委託先選定基準の策定",                            status: "compliant",     lastAssessed: "2026-03-01", evidence: "vendor_criteria.pdf" },
      { id: "F7-02", description: "契約書へのセキュリティ条項の明記",                status: "non_compliant", lastAssessed: "2026-01-15", evidence: null },
      { id: "F7-03", description: "委託先のFISC準拠確認",                            status: "non_compliant", lastAssessed: "2026-01-15", evidence: null },
    ],
  },
  {
    id: "cat8",
    nameJa: "監査証跡・ログ",
    nameEn: "Audit Trail & Logging",
    score: 65,
    status: "partial",
    compliant: 3,
    total: 5,
    controls: [
      { id: "F8-01", description: "業務ログ・操作ログの収集と保管",                  status: "compliant",     lastAssessed: "2026-03-28", evidence: "log_retention.pdf" },
      { id: "F8-02", description: "ログの完全性確保（改ざん防止）",                  status: "partial",       lastAssessed: "2026-02-20", evidence: "log_integrity.pdf" },
      { id: "F8-03", description: "ログの定期的なレビュー・分析",                    status: "non_compliant", lastAssessed: "2026-01-20", evidence: null },
    ],
  },
  {
    id: "cat9",
    nameJa: "クラウド・外部サービス利用",
    nameEn: "Cloud & External Services",
    score: 50,
    status: "non_compliant",
    compliant: 2,
    total: 5,
    controls: [
      { id: "F9-01", description: "クラウドサービス利用方針の策定",                  status: "compliant",     lastAssessed: "2026-03-10", evidence: "cloud_policy.pdf" },
      { id: "F9-02", description: "データ所在地・越境移転の把握",                    status: "non_compliant", lastAssessed: "2026-01-31", evidence: null },
      { id: "F9-03", description: "クラウド集中リスクの評価",                        status: "non_compliant", lastAssessed: "2026-01-15", evidence: null },
    ],
  },
];

const DEMO_GAPS: FiscGap[] = [
  { controlId: "F7-02", severity: "critical", description: "委託契約の約23件にFISC要求セキュリティ条項が未記載", remediation: "全委託契約を2026年6月末までに改訂し、FISC要求条項を追加する" },
  { controlId: "F9-03", severity: "critical", description: "AWS/Azureへの集中リスク評価が未実施。金融機関としての要件未達", remediation: "クラウド集中リスク評価を実施し、マルチクラウド戦略を文書化する" },
  { controlId: "F4-04", severity: "high",     description: "セキュリティイベントのリアルタイム監視体制が未整備", remediation: "SIEMを導入し、24時間監視体制を構築する" },
];

/* ============================================================
 * Helpers
 * ============================================================ */

function scoreColor(score: number): string {
  if (score >= 80) return "#10b981";
  if (score >= 60) return "#f59e0b";
  return "#ef4444";
}

function statusVariant(status: ControlStatus): "green" | "yellow" | "red" {
  if (status === "compliant") return "green";
  if (status === "partial") return "yellow";
  return "red";
}

function statusLabel(status: ControlStatus): string {
  if (status === "compliant") return "準拠";
  if (status === "partial") return "一部準拠";
  return "未準拠";
}

/* ============================================================
 * Main Page
 * ============================================================ */

export default function FiscPage() {
  useLocale();

  const [expandedCategory, setExpandedCategory] = useState<string | null>("cat1");

  const totalControls = DEMO_CATEGORIES.flatMap((c) => c.controls).length;
  const compliantCount = DEMO_CATEGORIES.flatMap((c) => c.controls).filter((c) => c.status === "compliant").length;
  const overallScore = Math.round(DEMO_CATEGORIES.reduce((s, c) => s + c.score, 0) / DEMO_CATEGORIES.length);

  return (
    <div className="w-full px-6 py-10">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-2">
          <h1 className="text-2xl font-bold flex items-center gap-3">
            <Landmark size={24} className="text-[var(--gold)]" />
            FISC 安全対策基準
          </h1>
          <div className="px-3 py-1 rounded-full bg-[var(--border-color)] border border-[var(--border-color)] text-xs font-semibold text-[var(--text-secondary)]">
            Japan Financial
          </div>
        </div>
        <p className="text-[var(--text-secondary)] text-sm">
          金融情報システムセンター（FISC）安全対策基準への準拠状況 (Layer 4)
        </p>
      </div>

      {/* Overview Score */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        <Card className="text-center">
          <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider mb-1">総合スコア</p>
          <p className="text-5xl font-extrabold font-mono" style={{ color: scoreColor(overallScore) }}>{overallScore}%</p>
          <Badge variant={overallScore >= 80 ? "green" : overallScore >= 60 ? "yellow" : "red"} className="mt-2">
            {overallScore >= 80 ? "準拠" : overallScore >= 60 ? "一部準拠" : "要対応"}
          </Badge>
        </Card>
        <Card className="text-center">
          <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider mb-1">準拠コントロール</p>
          <p className="text-4xl font-extrabold font-mono text-emerald-400">{compliantCount}</p>
          <p className="text-xs text-[var(--text-muted)] mt-1">/ {totalControls} 件</p>
        </Card>
        <Card className="text-center">
          <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider mb-1">重大ギャップ</p>
          <p className="text-4xl font-extrabold font-mono text-red-400">{DEMO_GAPS.filter((g) => g.severity === "critical").length}</p>
          <p className="text-xs text-[var(--text-muted)] mt-1">即時対応が必要</p>
        </Card>
        <Card className="text-center">
          <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider mb-1">カテゴリ数</p>
          <p className="text-4xl font-extrabold font-mono text-[#e2e8f0]">{DEMO_CATEGORIES.length}</p>
          <p className="text-xs text-[var(--text-muted)] mt-1">管理領域</p>
        </Card>
      </div>

      {/* Category Breakdown */}
      <Card className="mb-8">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-base font-bold flex items-center gap-2">
            <Shield size={16} className="text-[var(--gold)]" />
            管理カテゴリ別スコア
          </h3>
          <Button size="sm" variant="secondary">
            <Download size={13} />
            レポート出力
          </Button>
        </div>
        <div className="space-y-3">
          {DEMO_CATEGORIES.map((cat) => (
            <div key={cat.id}>
              <button
                className="w-full text-left"
                onClick={() => setExpandedCategory(expandedCategory === cat.id ? null : cat.id)}
              >
                <div className="flex items-center gap-3 py-2">
                  {expandedCategory === cat.id
                    ? <ChevronDown size={13} className="text-[var(--text-muted)] shrink-0" />
                    : <ChevronRight size={13} className="text-[var(--text-muted)] shrink-0" />}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between mb-1">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-[#e2e8f0]">{cat.nameJa}</span>
                        <span className="text-xs text-[var(--text-muted)]">({cat.nameEn})</span>
                      </div>
                      <div className="flex items-center gap-3 shrink-0 ml-4">
                        <span className="text-xs text-[var(--text-muted)]">{cat.compliant}/{cat.total}</span>
                        <Badge variant={statusVariant(cat.status)}>{statusLabel(cat.status)}</Badge>
                        <span className="text-sm font-bold font-mono min-w-[44px] text-right" style={{ color: scoreColor(cat.score) }}>
                          {cat.score}%
                        </span>
                      </div>
                    </div>
                    <div className="h-2 bg-white/5 rounded-full overflow-hidden">
                      <div
                        className="h-full rounded-full transition-all duration-700"
                        style={{ width: `${cat.score}%`, backgroundColor: scoreColor(cat.score) }}
                      />
                    </div>
                  </div>
                </div>
              </button>

              {expandedCategory === cat.id && (
                <div className="ml-6 mt-2 mb-3 space-y-2">
                  {cat.controls.map((ctrl) => (
                    <div
                      key={ctrl.id}
                      className={`flex items-center gap-3 p-3 rounded-lg border text-sm ${
                        ctrl.status === "compliant"
                          ? "bg-emerald-500/5 border-emerald-500/10"
                          : ctrl.status === "partial"
                            ? "bg-yellow-500/5 border-yellow-500/10"
                            : "bg-red-500/5 border-red-500/10"
                      }`}
                    >
                      {ctrl.status === "compliant"
                        ? <CheckCircle2 size={13} className="text-emerald-400 shrink-0" />
                        : ctrl.status === "partial"
                          ? <AlertTriangle size={13} className="text-yellow-400 shrink-0" />
                          : <XCircle size={13} className="text-red-400 shrink-0" />}
                      <span className="font-mono text-xs text-[var(--text-muted)] shrink-0">{ctrl.id}</span>
                      <span className="flex-1">{ctrl.description}</span>
                      <span className="text-xs text-[var(--text-muted)] shrink-0 hidden md:block">{ctrl.lastAssessed}</span>
                      {ctrl.evidence
                        ? <Badge variant="default" className="shrink-0"><FileText size={10} className="mr-1" />あり</Badge>
                        : <Badge variant="red" className="shrink-0">未提出</Badge>}
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </Card>

      {/* Gap Analysis */}
      <Card>
        <h3 className="text-base font-bold mb-4 flex items-center gap-2">
          <AlertTriangle size={16} className="text-[var(--gold)]" />
          ギャップ分析 — 優先対応事項
        </h3>
        <div className="space-y-3">
          {DEMO_GAPS.map((gap, i) => (
            <div
              key={gap.controlId}
              className={`p-4 rounded-xl border ${
                gap.severity === "critical"
                  ? "bg-red-500/5 border-red-500/20"
                  : "bg-yellow-500/5 border-yellow-500/20"
              }`}
            >
              <div className="flex items-start gap-3">
                <span className="text-sm font-bold text-[var(--gold)] shrink-0 w-5">{i + 1}.</span>
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1 flex-wrap">
                    <span className="font-mono text-xs text-[var(--text-muted)]">{gap.controlId}</span>
                    <Badge variant={gap.severity === "critical" ? "red" : "yellow"}>
                      {gap.severity === "critical" ? "重大" : "高"}
                    </Badge>
                  </div>
                  <p className="text-sm text-[#e2e8f0] mb-1">{gap.description}</p>
                  <p className="text-xs text-[var(--gold)] flex items-center gap-1">
                    <ArrowRight size={10} />
                    {gap.remediation}
                  </p>
                </div>
              </div>
            </div>
          ))}
        </div>
        <p className="text-xs text-[var(--text-muted)] mt-4 border-t border-[var(--border-color)] pt-3">
          FISC安全対策基準 第10版（2024年改訂）に基づく評価 · 次回定期評価: 2026-07-01
        </p>
      </Card>
    </div>
  );
}
