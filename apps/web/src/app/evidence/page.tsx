"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useState } from "react";
import {
  ShieldCheck,
  FileText,
  Download,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Building2,
  AlertOctagon,
  Clock,
  User,
} from "lucide-react";
import { useLocale } from "@/lib/useLocale";
import type { Locale } from "@/i18n/config";
import { appDict } from "@/i18n/app-dict";

// ─── Types ────────────────────────────────────────────────────

type ComplianceStatus = "compliant" | "partial" | "non_compliant";

interface EvidenceItem {
  fileName: string;
  uploadedAt: string;
}

interface ControlEvidence {
  id: string;
  name: Record<string, string>;
  description: Record<string, string>;
  status: ComplianceStatus;
  evidence: EvidenceItem[];
  lastReviewDate: string;
  reviewer: string;
}

interface ICTProvider {
  name: string;
  leiEuid: string;
  service: Record<string, string>;
  criticality: "critical" | "important" | "standard";
  contractPeriod: string;
  dataLocation: string;
  annualCostEur: number;
}

interface IncidentField {
  label: Record<string, string>;
  value: string;
}

interface IncidentReport {
  type: "initial" | "intermediate" | "final";
  title: Record<string, string>;
  deadline: Record<string, string>;
  fields: IncidentField[];
}

// ─── Tab Enum ─────────────────────────────────────────────────

type MainTab = "evidence" | "register" | "incident";
type PillarTab = "pillar1" | "pillar2" | "pillar3" | "pillar4" | "pillar5";

// ─── Demo Data: Evidence ──────────────────────────────────────

const PILLAR_CONTROLS: Record<PillarTab, ControlEvidence[]> = {
  pillar1: [
    {
      id: "P1-01",
      name: { en: "ICT Risk Management Policy", ja: "ICTリスク管理ポリシー" },
      description: { en: "Documented ICT risk management framework with board-level oversight", ja: "取締役会レベルの監督を伴うICTリスク管理フレームワーク" },
      status: "compliant",
      evidence: [
        { fileName: "ict-risk-policy-v3.2.pdf", uploadedAt: "2026-02-15T10:30:00Z" },
        { fileName: "board-approval-minutes-2026Q1.pdf", uploadedAt: "2026-01-20T14:00:00Z" },
      ],
      lastReviewDate: "2026-03-01",
      reviewer: "M. Tanaka (CISO)",
    },
    {
      id: "P1-02",
      name: { en: "Asset Management & Classification", ja: "資産管理・分類" },
      description: { en: "All ICT assets inventoried and classified by criticality", ja: "全ICT資産がインベントリ化され重要度別に分類" },
      status: "compliant",
      evidence: [
        { fileName: "asset-inventory-2026Q1.xlsx", uploadedAt: "2026-03-10T09:00:00Z" },
      ],
      lastReviewDate: "2026-03-10",
      reviewer: "K. Suzuki (IT Ops)",
    },
    {
      id: "P1-03",
      name: { en: "Risk Assessment Process", ja: "リスクアセスメントプロセス" },
      description: { en: "Risk assessments performed but not at required frequency", ja: "リスクアセスメントは実施済みだが要求頻度を満たしていない" },
      status: "partial",
      evidence: [
        { fileName: "risk-assessment-2025H2.pdf", uploadedAt: "2025-12-20T11:00:00Z" },
      ],
      lastReviewDate: "2026-01-15",
      reviewer: "M. Tanaka (CISO)",
    },
    {
      id: "P1-04",
      name: { en: "Protection & Prevention", ja: "保護と予防" },
      description: { en: "Insufficient network segmentation between critical and non-critical systems", ja: "重要システムと非重要システム間のネットワーク分離が不十分" },
      status: "non_compliant",
      evidence: [],
      lastReviewDate: "2026-02-01",
      reviewer: "T. Yamamoto (NetOps)",
    },
  ],
  pillar2: [
    {
      id: "P2-01",
      name: { en: "Incident Detection & Classification", ja: "インシデント検知・分類" },
      description: { en: "Automated monitoring and alerting with severity classification", ja: "重要度分類を伴う自動監視・アラート" },
      status: "compliant",
      evidence: [
        { fileName: "monitoring-config-export.json", uploadedAt: "2026-03-05T08:00:00Z" },
        { fileName: "alert-policy-document.pdf", uploadedAt: "2026-02-28T16:00:00Z" },
      ],
      lastReviewDate: "2026-03-05",
      reviewer: "A. Nakamura (SRE Lead)",
    },
    {
      id: "P2-02",
      name: { en: "Major Incident Reporting Obligation", ja: "重大インシデントの報告義務" },
      description: { en: "Incident reporting pipeline not automated within 4-hour window", ja: "4時間以内のインシデント報告パイプラインが未自動化" },
      status: "non_compliant",
      evidence: [],
      lastReviewDate: "2026-02-20",
      reviewer: "A. Nakamura (SRE Lead)",
    },
    {
      id: "P2-03",
      name: { en: "Incident Response Procedures", ja: "インシデント対応手順" },
      description: { en: "Runbooks exist but are incomplete for all failure scenarios", ja: "ランブックは存在するが全障害シナリオをカバーしていない" },
      status: "partial",
      evidence: [
        { fileName: "runbook-db-failure.md", uploadedAt: "2026-01-10T10:00:00Z" },
      ],
      lastReviewDate: "2026-02-15",
      reviewer: "A. Nakamura (SRE Lead)",
    },
    {
      id: "P2-04",
      name: { en: "Root Cause Analysis", ja: "ルートコーズ分析" },
      description: { en: "Post-incident reviews conducted with documented root cause analysis", ja: "文書化された根本原因分析を伴うインシデント後レビュー" },
      status: "compliant",
      evidence: [
        { fileName: "postmortem-INC-2026-003.pdf", uploadedAt: "2026-03-01T13:00:00Z" },
      ],
      lastReviewDate: "2026-03-01",
      reviewer: "S. Watanabe (Engineering Manager)",
    },
  ],
  pillar3: [
    {
      id: "P3-01",
      name: { en: "Periodic ICT Tool Testing", ja: "ICTツールの定期テスト" },
      description: { en: "Regular resilience testing via FaultRay simulations", ja: "FaultRayシミュレーションによる定期的なレジリエンステスト" },
      status: "compliant",
      evidence: [
        { fileName: "faultray-report-2026Q1.pdf", uploadedAt: "2026-03-15T11:00:00Z" },
        { fileName: "test-schedule-2026.xlsx", uploadedAt: "2026-01-05T09:00:00Z" },
      ],
      lastReviewDate: "2026-03-15",
      reviewer: "K. Suzuki (IT Ops)",
    },
    {
      id: "P3-02",
      name: { en: "Threat-Led Penetration Testing (TLPT)", ja: "脅威ベースの侵入テスト（TLPT）" },
      description: { en: "No TLPT program established", ja: "TLPTプログラムが未確立" },
      status: "non_compliant",
      evidence: [],
      lastReviewDate: "2026-02-01",
      reviewer: "M. Tanaka (CISO)",
    },
    {
      id: "P3-03",
      name: { en: "Test Result Remediation", ja: "テスト結果の是正措置" },
      description: { en: "Test findings tracked and remediated within defined timelines", ja: "テスト発見事項は追跡・定められた期限内に是正" },
      status: "compliant",
      evidence: [
        { fileName: "remediation-tracker-2026Q1.xlsx", uploadedAt: "2026-03-12T10:00:00Z" },
      ],
      lastReviewDate: "2026-03-12",
      reviewer: "K. Suzuki (IT Ops)",
    },
    {
      id: "P3-04",
      name: { en: "Test Evidence Retention", ja: "テスト証跡の保存" },
      description: { en: "Test evidence partially retained, retention policy needs update", ja: "テスト証跡は部分的に保存、保存ポリシーの更新が必要" },
      status: "partial",
      evidence: [],
      lastReviewDate: "2026-02-28",
      reviewer: "K. Suzuki (IT Ops)",
    },
  ],
  pillar4: [
    {
      id: "P4-01",
      name: { en: "Third-Party Identification & Classification", ja: "サードパーティの識別・分類" },
      description: { en: "Major vendors identified but classification incomplete", ja: "主要ベンダーは識別済みだが分類が未完了" },
      status: "partial",
      evidence: [
        { fileName: "vendor-register-draft.xlsx", uploadedAt: "2026-02-20T14:00:00Z" },
      ],
      lastReviewDate: "2026-02-20",
      reviewer: "Y. Ito (Procurement)",
    },
    {
      id: "P4-02",
      name: { en: "Contract Clause Standardization", ja: "契約条項の標準化" },
      description: { en: "Contracts lack standardized DORA-required clauses", ja: "契約にDORA要求の標準条項が含まれていない" },
      status: "non_compliant",
      evidence: [],
      lastReviewDate: "2026-01-30",
      reviewer: "H. Saito (Legal)",
    },
    {
      id: "P4-03",
      name: { en: "Concentration Risk Assessment", ja: "集中リスクの評価" },
      description: { en: "No concentration risk assessment for cloud providers", ja: "クラウドプロバイダーの集中リスク評価が未実施" },
      status: "non_compliant",
      evidence: [],
      lastReviewDate: "2026-02-10",
      reviewer: "M. Tanaka (CISO)",
    },
    {
      id: "P4-04",
      name: { en: "Critical Third-Party Oversight", ja: "重要サードパーティの監督" },
      description: { en: "Monitoring exists but oversight framework needs formalization", ja: "モニタリングは実施しているが監督フレームワークの正式化が必要" },
      status: "partial",
      evidence: [
        { fileName: "vendor-monitoring-dashboard.pdf", uploadedAt: "2026-03-01T10:00:00Z" },
      ],
      lastReviewDate: "2026-03-01",
      reviewer: "Y. Ito (Procurement)",
    },
  ],
  pillar5: [
    {
      id: "P5-01",
      name: { en: "Cyber Threat Intelligence Sharing", ja: "サイバー脅威情報の共有" },
      description: { en: "Active participation in industry ISAC", ja: "業界ISACへの積極的な参加" },
      status: "compliant",
      evidence: [
        { fileName: "isac-membership-cert-2026.pdf", uploadedAt: "2026-01-15T09:00:00Z" },
        { fileName: "threat-intel-sharing-log-Q1.csv", uploadedAt: "2026-03-20T16:00:00Z" },
      ],
      lastReviewDate: "2026-03-20",
      reviewer: "M. Tanaka (CISO)",
    },
    {
      id: "P5-02",
      name: { en: "Incident Information Exchange", ja: "インシデント情報の交換" },
      description: { en: "Established channels for incident information sharing with regulators", ja: "規制当局とのインシデント情報共有チャネルが確立" },
      status: "compliant",
      evidence: [
        { fileName: "regulator-comm-protocol.pdf", uploadedAt: "2026-02-10T11:00:00Z" },
      ],
      lastReviewDate: "2026-02-10",
      reviewer: "M. Tanaka (CISO)",
    },
    {
      id: "P5-03",
      name: { en: "Cross-Industry Collaboration", ja: "業界間の連携" },
      description: { en: "Participating in some cross-industry forums but coverage can be expanded", ja: "一部の業界横断フォーラムに参加しているがカバレッジ拡大が可能" },
      status: "partial",
      evidence: [
        { fileName: "forum-participation-log-2026.xlsx", uploadedAt: "2026-03-10T14:00:00Z" },
      ],
      lastReviewDate: "2026-03-10",
      reviewer: "R. Kobayashi (GRC)",
    },
  ],
};

// ─── Demo Data: Register of Information ───────────────────────

const ICT_PROVIDERS: ICTProvider[] = [
  {
    name: "Amazon Web Services (AWS)",
    leiEuid: "LEIX-5493001MZ0YLHT4YON30",
    service: { en: "Cloud IaaS/PaaS — Compute, Storage, Networking", ja: "クラウドIaaS/PaaS — コンピュート、ストレージ、ネットワーク" },
    criticality: "critical",
    contractPeriod: "2024-01-01 — 2027-12-31",
    dataLocation: "EU (Frankfurt, Ireland)",
    annualCostEur: 480000,
  },
  {
    name: "Google Cloud Platform",
    leiEuid: "LEIX-5493006MHB84DD3ZS680",
    service: { en: "BigQuery Analytics, Vertex AI", ja: "BigQuery分析、Vertex AI" },
    criticality: "important",
    contractPeriod: "2025-04-01 — 2028-03-31",
    dataLocation: "EU (Belgium, Netherlands)",
    annualCostEur: 120000,
  },
  {
    name: "Cloudflare, Inc.",
    leiEuid: "LEIX-5493008WQ2PB4LNO25F7",
    service: { en: "CDN, DDoS Protection, DNS", ja: "CDN、DDoS防御、DNS" },
    criticality: "critical",
    contractPeriod: "2025-01-01 — 2026-12-31",
    dataLocation: "Global (EU-primary)",
    annualCostEur: 36000,
  },
  {
    name: "Stripe, Inc.",
    leiEuid: "LEIX-5493003GCSBRP5T4SZ49",
    service: { en: "Payment Processing, Billing", ja: "決済処理、課金" },
    criticality: "critical",
    contractPeriod: "2024-06-01 — 2027-05-31",
    dataLocation: "EU (Ireland)",
    annualCostEur: 24000,
  },
  {
    name: "Supabase, Inc.",
    leiEuid: "N/A (Private)",
    service: { en: "Database Hosting, Authentication", ja: "データベースホスティング、認証" },
    criticality: "important",
    contractPeriod: "2025-01-01 — 2026-12-31",
    dataLocation: "EU (Frankfurt)",
    annualCostEur: 9600,
  },
];

// ─── Demo Data: Incident Reports ──────────────────────────────

const INCIDENT_REPORTS: IncidentReport[] = [
  {
    type: "initial",
    title: { en: "Initial Notification (within 4 hours)", ja: "初期通知（4時間以内）" },
    deadline: { en: "Deadline: 4 hours after classification as major", ja: "期限: 重大インシデント分類後4時間以内" },
    fields: [
      { label: { en: "Reporting Entity", ja: "報告機関" }, value: "FaultRay Technologies Ltd." },
      { label: { en: "Incident Reference", ja: "インシデント参照番号" }, value: "INC-2026-0042" },
      { label: { en: "Date/Time of Detection", ja: "検知日時" }, value: "2026-03-28T14:23:00Z" },
      { label: { en: "Date/Time of Classification", ja: "分類日時" }, value: "2026-03-28T14:35:00Z" },
      { label: { en: "Type of Incident", ja: "インシデント種別" }, value: "ICT Service Disruption" },
      { label: { en: "Affected Services", ja: "影響サービス" }, value: "Core API, Database Cluster" },
      { label: { en: "EU Member States Affected", ja: "影響EU加盟国" }, value: "DE, FR, NL, IE" },
      { label: { en: "Impact on Clients", ja: "顧客への影響" }, value: "Approx. 12,000 clients affected" },
      { label: { en: "Initial Assessment", ja: "初期アセスメント" }, value: "Major — service unavailability exceeding 2 hours" },
    ],
  },
  {
    type: "intermediate",
    title: { en: "Intermediate Report (within 72 hours)", ja: "中間報告書（72時間以内）" },
    deadline: { en: "Deadline: 72 hours after initial notification", ja: "期限: 初期通知後72時間以内" },
    fields: [
      { label: { en: "Reporting Entity", ja: "報告機関" }, value: "FaultRay Technologies Ltd." },
      { label: { en: "Incident Reference", ja: "インシデント参照番号" }, value: "INC-2026-0042" },
      { label: { en: "Status Update", ja: "ステータス更新" }, value: "Resolved" },
      { label: { en: "Root Cause (preliminary)", ja: "根本原因（暫定）" }, value: "Primary database disk I/O saturation triggered cascading failures" },
      { label: { en: "Duration of Disruption", ja: "障害継続時間" }, value: "2h 15m (14:23 — 16:38 UTC)" },
      { label: { en: "Data Integrity Impact", ja: "データ整合性への影響" }, value: "No data loss or corruption detected" },
      { label: { en: "Financial Impact (estimated)", ja: "財務影響（推定）" }, value: "EUR 45,000 (lost revenue + incident response)" },
      { label: { en: "Clients Notified", ja: "顧客通知" }, value: "Yes — via status page and email at T+30min" },
      { label: { en: "Recovery Actions Taken", ja: "復旧アクション" }, value: "Manual failover to replica, disk replacement, capacity upgrade" },
      { label: { en: "Third-Party Involvement", ja: "サードパーティの関与" }, value: "AWS Support engaged for disk replacement (case #12345678)" },
    ],
  },
  {
    type: "final",
    title: { en: "Final Report (within 1 month)", ja: "最終報告書（1ヶ月以内）" },
    deadline: { en: "Deadline: 1 month after initial notification", ja: "期限: 初期通知後1ヶ月以内" },
    fields: [
      { label: { en: "Reporting Entity", ja: "報告機関" }, value: "FaultRay Technologies Ltd." },
      { label: { en: "Incident Reference", ja: "インシデント参照番号" }, value: "INC-2026-0042" },
      { label: { en: "Root Cause (confirmed)", ja: "根本原因（確定）" }, value: "NVMe SSD firmware bug causing I/O queue stall under sustained write load" },
      { label: { en: "Full Timeline", ja: "全体タイムライン" }, value: "T+0: Disk I/O 100% → T+1m: Query latency >5s → T+2m: Connection pool exhausted → T+5m: Alert → T+8m: Failover → T+2h15m: Full recovery" },
      { label: { en: "Total Financial Impact", ja: "財務影響合計" }, value: "EUR 52,300 (lost revenue: 38,000 + incident response: 8,500 + hardware: 5,800)" },
      { label: { en: "Affected Clients (final)", ja: "影響顧客（最終）" }, value: "11,847 clients across 4 EU member states" },
      { label: { en: "Preventive Measures", ja: "再発防止策" }, value: "1. Firmware update applied to all NVMe SSDs\n2. Automated failover threshold reduced from 5min to 30s\n3. Added disk I/O predictive alerts\n4. Quarterly chaos testing of database failover" },
      { label: { en: "Changes to ICT Risk Framework", ja: "ICTリスクフレームワークの変更" }, value: "Updated risk register: Added 'Storage firmware vulnerability' as high-risk item. Updated BIA for database tier." },
      { label: { en: "Lessons Learned", ja: "教訓" }, value: "Manual failover SOP was outdated. FaultRay simulation coverage did not include firmware-level storage failures." },
    ],
  },
];

// ─── Helper: Download JSON ────────────────────────────────────

function downloadJson(data: unknown, filename: string) {
  let json: string;
  try {
    json = JSON.stringify(data, null, 2);
  } catch {
    // Circular reference or non-serializable value — fall back to safe string
    json = JSON.stringify({ error: "Data could not be serialized", timestamp: new Date().toISOString() }, null, 2);
  }
  const blob = new Blob([json], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function downloadCsv(rows: string[][], filename: string) {
  const csvContent = rows
    .map((row) => row.map((cell) => `"${cell.replace(/"/g, '""')}"`).join(","))
    .join("\n");
  const blob = new Blob(["\uFEFF" + csvContent], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// ─── Sub-Components ───────────────────────────────────────────

function StatusBadge({ status, locale }: { status: ComplianceStatus; locale: Locale }) {
  const ct = appDict.evidence[locale] ?? appDict.evidence.en;
  if (status === "compliant") return <Badge variant="green">{ct.statusCompliant}</Badge>;
  if (status === "partial") return <Badge variant="yellow">{ct.statusPartial}</Badge>;
  return <Badge variant="red">{ct.statusNonCompliant}</Badge>;
}

function CriticalityBadge({ criticality, locale }: { criticality: string; locale: Locale }) {
  const ct = appDict.evidence[locale] ?? appDict.evidence.en;
  if (criticality === "critical") return <Badge variant="red">{ct.criticalityCritical}</Badge>;
  if (criticality === "important") return <Badge variant="yellow">{ct.criticalityImportant}</Badge>;
  return <Badge variant="default">{ct.criticalityStandard}</Badge>;
}

// ─── Tab: Evidence Management ─────────────────────────────────

function EvidenceManagementTab({ locale }: { locale: Locale }) {
  const [activePillar, setActivePillar] = useState<PillarTab>("pillar1");
  const ct = appDict.evidence[locale] ?? appDict.evidence.en;
  const dp = appDict.doraPillars[locale] ?? appDict.doraPillars.en;

  const pillarTabs: { key: PillarTab; label: string }[] = [
    { key: "pillar1", label: dp.pillar1Short },
    { key: "pillar2", label: dp.pillar2Short },
    { key: "pillar3", label: dp.pillar3Short },
    { key: "pillar4", label: dp.pillar4Short },
    { key: "pillar5", label: dp.pillar5Short },
  ];

  const controls = PILLAR_CONTROLS[activePillar];

  const handleExportEvidence = () => {
    const exportData = {
      exportedAt: new Date().toISOString(),
      exportedBy: "FaultRay Compliance Module",
      pillars: Object.entries(PILLAR_CONTROLS).map(([pillarKey, ctrls]) => ({
        pillar: pillarKey,
        pillarName: dp[pillarKey as keyof typeof dp] ?? pillarKey,
        controls: ctrls.map((c) => ({
          id: c.id,
          name: c.name.en,
          status: c.status,
          evidence: c.evidence,
          lastReviewDate: c.lastReviewDate,
          reviewer: c.reviewer,
        })),
      })),
    };
    downloadJson(exportData, `dora-evidence-package-${new Date().toISOString().slice(0, 10)}.json`);
  };

  return (
    <div>
      {/* Pillar Tabs */}
      <div className="flex gap-1 mb-6 overflow-x-auto pb-1">
        {pillarTabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActivePillar(tab.key)}
            className={`px-4 py-2 text-xs font-semibold rounded-lg whitespace-nowrap transition-colors ${
              activePillar === tab.key
                ? "bg-[var(--gold)]/10 text-[var(--gold)] border border-[var(--gold)]/30"
                : "text-[var(--text-secondary)] hover:text-white hover:bg-white/5 border border-transparent"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Control Cards */}
      <div className="space-y-4 mb-6">
        {controls.map((ctrl) => (
          <Card key={ctrl.id}>
            <div className="flex items-start justify-between gap-4 flex-wrap">
              <div className="flex items-start gap-3 flex-1 min-w-0">
                {ctrl.status === "compliant" ? (
                  <CheckCircle2 size={18} className="text-emerald-400 mt-1 shrink-0" />
                ) : ctrl.status === "partial" ? (
                  <AlertTriangle size={18} className="text-yellow-400 mt-1 shrink-0" />
                ) : (
                  <XCircle size={18} className="text-red-400 mt-1 shrink-0" />
                )}
                <div className="min-w-0">
                  <div className="flex items-center gap-2 mb-1 flex-wrap">
                    <span className="text-sm font-mono text-[var(--text-muted)]">{ctrl.id}</span>
                    <span className="text-sm font-medium">{ctrl.name[locale] ?? ctrl.name.en}</span>
                    <StatusBadge status={ctrl.status} locale={locale} />
                  </div>
                  <p className="text-xs text-[var(--text-secondary)] mb-3">{ctrl.description[locale] ?? ctrl.description.en}</p>

                  {/* Evidence Files */}
                  <div className="mb-2">
                    <p className="text-xs font-semibold text-[var(--text-muted)] mb-1">{ct.evidenceFiles}</p>
                    {ctrl.evidence.length > 0 ? (
                      <div className="space-y-1">
                        {ctrl.evidence.map((ev, i) => (
                          <div key={i} className="flex items-center gap-2 text-xs">
                            <FileText size={12} className="text-[var(--text-muted)] shrink-0" />
                            <span className="text-[var(--text-secondary)]">{ev.fileName}</span>
                            <span className="text-[var(--text-muted)]">
                              {new Date(ev.uploadedAt).toLocaleDateString(locale === "ja" ? "ja-JP" : "en-US")}
                            </span>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-xs text-red-400">{ct.noEvidence}</p>
                    )}
                  </div>

                  {/* Review info */}
                  <div className="flex items-center gap-4 text-xs text-[var(--text-muted)]">
                    <span className="flex items-center gap-1">
                      <Clock size={10} />
                      {ct.lastReview}: {ctrl.lastReviewDate}
                    </span>
                    <span className="flex items-center gap-1">
                      <User size={10} />
                      {ctrl.reviewer}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </Card>
        ))}
      </div>

      {/* Export Button */}
      <Button variant="secondary" size="sm" onClick={handleExportEvidence}>
        <Download size={14} />
        {ct.downloadEvidencePackage}
      </Button>
    </div>
  );
}

// ─── Tab: Register of Information ─────────────────────────────

function RegisterTab({ locale }: { locale: Locale }) {
  const ct = appDict.evidence[locale] ?? appDict.evidence.en;

  const handleExportCsv = () => {
    const headers = [
      "Provider Name",
      "LEI / EUID",
      "Service Description",
      "Criticality",
      "Contract Period",
      "Data Location",
      "Annual Cost (EUR)",
    ];
    const dataRows = ICT_PROVIDERS.map((p) => [
      p.name,
      p.leiEuid,
      p.service.en,
      p.criticality,
      p.contractPeriod,
      p.dataLocation,
      p.annualCostEur.toString(),
    ]);
    downloadCsv([headers, ...dataRows], `register-of-information-${new Date().toISOString().slice(0, 10)}.csv`);
  };

  return (
    <div>
      <p className="text-xs text-[var(--text-secondary)] mb-4">
        {ct.registerDescription}
      </p>

      {/* Provider Table */}
      <div className="overflow-x-auto mb-4">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[var(--border-color)] text-left">
              <th scope="col" className="pb-3 pr-4 text-xs text-[var(--text-muted)] font-semibold">{ct.providerName}</th>
              <th scope="col" className="pb-3 pr-4 text-xs text-[var(--text-muted)] font-semibold">LEI / EUID</th>
              <th scope="col" className="pb-3 pr-4 text-xs text-[var(--text-muted)] font-semibold">{ct.serviceDescription}</th>
              <th scope="col" className="pb-3 pr-4 text-xs text-[var(--text-muted)] font-semibold">{ct.criticality}</th>
              <th scope="col" className="pb-3 pr-4 text-xs text-[var(--text-muted)] font-semibold">{ct.contractPeriod}</th>
              <th scope="col" className="pb-3 pr-4 text-xs text-[var(--text-muted)] font-semibold">{ct.dataLocation}</th>
              <th scope="col" className="pb-3 text-xs text-[var(--text-muted)] font-semibold text-right">{ct.annualCost}</th>
            </tr>
          </thead>
          <tbody>
            {ICT_PROVIDERS.map((provider) => (
              <tr key={provider.name} className="border-b border-[var(--border-color)]/50 hover:bg-white/[0.02]">
                <td className="py-3 pr-4 font-medium text-sm">{provider.name}</td>
                <td className="py-3 pr-4 text-xs text-[var(--text-muted)] font-mono">{provider.leiEuid}</td>
                <td className="py-3 pr-4 text-xs text-[var(--text-secondary)]">{provider.service[locale] ?? provider.service.en}</td>
                <td className="py-3 pr-4"><CriticalityBadge criticality={provider.criticality} locale={locale} /></td>
                <td className="py-3 pr-4 text-xs text-[var(--text-secondary)]">{provider.contractPeriod}</td>
                <td className="py-3 pr-4 text-xs text-[var(--text-secondary)]">{provider.dataLocation}</td>
                <td className="py-3 text-xs text-[var(--text-secondary)] text-right font-mono">
                  {provider.annualCostEur.toLocaleString("en-US")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="text-xs text-yellow-400/80 mb-4 p-3 rounded-lg bg-yellow-500/5 border border-yellow-500/10">
        {ct.registerDisclaimer}
      </p>

      <Button variant="secondary" size="sm" onClick={handleExportCsv}>
        <Download size={14} />
        {ct.downloadRegisterCsv}
      </Button>
    </div>
  );
}

// ─── Tab: Incident Report ─────────────────────────────────────

function IncidentReportTab({ locale }: { locale: Locale }) {
  const [activeReport, setActiveReport] = useState<"initial" | "intermediate" | "final">("initial");
  const ct = appDict.evidence[locale] ?? appDict.evidence.en;

  const report = INCIDENT_REPORTS.find((r) => r.type === activeReport)!;

  const handleExportIncident = () => {
    const exportData = {
      exportedAt: new Date().toISOString(),
      standard: "DORA ITS 2025/302",
      reports: INCIDENT_REPORTS.map((r) => ({
        type: r.type,
        title: r.title.en,
        fields: r.fields.map((f) => ({
          label: f.label.en,
          value: f.value,
        })),
      })),
    };
    downloadJson(exportData, `incident-report-${new Date().toISOString().slice(0, 10)}.json`);
  };

  const reportTypeButtons: { key: typeof activeReport; label: string }[] = [
    { key: "initial", label: ct.incidentInitial },
    { key: "intermediate", label: ct.incidentIntermediate },
    { key: "final", label: ct.incidentFinal },
  ];

  return (
    <div>
      <p className="text-xs text-[var(--text-secondary)] mb-4">
        DORA ITS 2025/302
      </p>

      {/* Report Type Selector */}
      <div className="flex gap-1 mb-6 overflow-x-auto pb-1">
        {reportTypeButtons.map((btn) => (
          <button
            key={btn.key}
            onClick={() => setActiveReport(btn.key)}
            className={`px-4 py-2 text-xs font-semibold rounded-lg whitespace-nowrap transition-colors ${
              activeReport === btn.key
                ? "bg-[var(--gold)]/10 text-[var(--gold)] border border-[var(--gold)]/30"
                : "text-[var(--text-secondary)] hover:text-white hover:bg-white/5 border border-transparent"
            }`}
          >
            {btn.label}
          </button>
        ))}
      </div>

      {/* Report Form */}
      <Card className="mb-4">
        <div className="flex items-center gap-2 mb-1">
          <AlertOctagon size={16} className="text-[var(--gold)]" />
          <h3 className="text-sm font-bold">{report.title[locale] ?? report.title.en}</h3>
        </div>
        <p className="text-xs text-[var(--text-muted)] mb-4 flex items-center gap-1">
          <Clock size={10} />
          {report.deadline[locale] ?? report.deadline.en}
        </p>

        <div className="space-y-3">
          {report.fields.map((field, i) => (
            <div key={i} className="grid grid-cols-[180px_1fr] gap-3 items-start">
              <label className="text-xs font-semibold text-[var(--text-muted)] pt-2">
                {field.label[locale] ?? field.label.en}
              </label>
              <div className="bg-white/[0.03] border border-[var(--border-color)] rounded-lg px-3 py-2 text-sm text-[var(--text-secondary)] whitespace-pre-wrap">
                {field.value}
              </div>
            </div>
          ))}
        </div>
      </Card>

      <p className="text-xs text-yellow-400/80 mb-4 p-3 rounded-lg bg-yellow-500/5 border border-yellow-500/10">
        {ct.incidentDisclaimer}
      </p>

      <Button variant="secondary" size="sm" onClick={handleExportIncident}>
        <Download size={14} />
        {ct.downloadIncidentJson}
      </Button>
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────

export default function EvidencePage() {
  const [activeTab, setActiveTab] = useState<MainTab>("evidence");
  const locale = useLocale();
  const ct = appDict.evidence[locale] ?? appDict.evidence.en;

  const mainTabs: { key: MainTab; label: string; icon: typeof ShieldCheck }[] = [
    { key: "evidence", label: ct.tabEvidence, icon: ShieldCheck },
    { key: "register", label: ct.tabRegister, icon: Building2 },
    { key: "incident", label: ct.tabIncident, icon: AlertOctagon },
  ];

  return (
    <div className="w-full px-6 py-10">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold mb-1 flex items-center gap-3">
          <ShieldCheck size={24} className="text-[var(--gold)]" />
          {ct.pageTitle}
        </h1>
        <p className="text-[var(--text-secondary)] text-sm">{ct.pageSubtitle}</p>
      </div>

      {/* Main Tabs */}
      <div className="flex gap-2 mb-8 overflow-x-auto pb-1">
        {mainTabs.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`flex items-center gap-2 px-5 py-2.5 text-sm font-semibold rounded-xl whitespace-nowrap transition-all ${
                activeTab === tab.key
                  ? "bg-[var(--gold)]/10 text-[var(--gold)] border border-[var(--gold)]/30 shadow-[0_0_15px_rgba(255,215,0,0.08)]"
                  : "text-[var(--text-secondary)] hover:text-white hover:bg-white/5 border border-[var(--border-color)]"
              }`}
            >
              <Icon size={16} />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Tab Content */}
      {activeTab === "evidence" && <EvidenceManagementTab locale={locale} />}
      {activeTab === "register" && <RegisterTab locale={locale} />}
      {activeTab === "incident" && <IncidentReportTab locale={locale} />}
    </div>
  );
}
