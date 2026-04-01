"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useState } from "react";
import {
  UserX,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  ChevronDown,
  ChevronRight,
  FileCode2,
  FileSpreadsheet,
  Database,
  Key,
  Settings,
  TrendingDown,
  TrendingUp,
  Users,
  Activity,
  ArrowDown,
} from "lucide-react";
import { useLocale } from "@/lib/useLocale";
import { appDict } from "@/i18n/app-dict";

/* ============================================================
 * Types
 * ============================================================ */

type RiskLevel = "critical" | "warning" | "ok";
type SystemType = "gas" | "sheet" | "db" | "credential" | "infra";
type GasStatus = "active" | "dormant" | "orphaned";

interface SystemAccess {
  id: string;
  name: string;
  type: SystemType;
  role: string;
  riskLevel: RiskLevel;
}

interface Person {
  id: string;
  name: string;
  department: string;
  riskScore: number;
  systems: SystemAccess[];
  departureImpact: string;
}

interface GasScript {
  id: string;
  name: string;
  owner: string;
  status: GasStatus;
  risk: RiskLevel;
  dependents: number;
  lastUpdated: string;
}

interface ImprovementAction {
  id: string;
  priority: RiskLevel;
  action: string;
  riskReduction: number;
}

/* ============================================================
 * Demo Data
 * ============================================================ */

const PEOPLE: Person[] = [
  {
    id: "tanaka",
    name: "田中太郎",
    department: "経理部",
    riskScore: 9.4,
    systems: [
      { id: "s1", name: "請求書自動送信.gs",   type: "gas",        role: "唯一の管理者", riskLevel: "critical" },
      { id: "s2", name: "売上集計シート",       type: "sheet",      role: "編集権限",     riskLevel: "ok" },
      { id: "s3", name: "請求DB直接アクセス",   type: "db",         role: "直接アクセス", riskLevel: "critical" },
    ],
    departureImpact: "月次締め処理が停止し、請求書発行が不可能になります",
  },
  {
    id: "suzuki",
    name: "鈴木花子",
    department: "人事部",
    riskScore: 7.2,
    systems: [
      { id: "s4", name: "採用通知自動化.gs",   type: "gas",        role: "唯一の管理者", riskLevel: "warning" },
      { id: "s5", name: "採用管理シート",       type: "sheet",      role: "編集権限",     riskLevel: "ok" },
    ],
    departureImpact: "採用通知が手動対応に戻り、採用プロセスが遅延します",
  },
  {
    id: "yamada",
    name: "山田健一",
    department: "インフラ",
    riskScore: 8.8,
    systems: [
      { id: "s6", name: "本番DBパスワード",     type: "credential", role: "唯一の知識者", riskLevel: "critical" },
      { id: "s7", name: "AWS踏み台SSH鍵",       type: "credential", role: "3名共有",       riskLevel: "warning" },
      { id: "s8", name: "Terraform設定",        type: "infra",      role: "IaC化済み",    riskLevel: "ok" },
    ],
    departureImpact: "本番DBへのアクセスが不能となり、障害対応が困難になります",
  },
  {
    id: "sato",
    name: "佐藤美咲",
    department: "営業部",
    riskScore: 5.1,
    systems: [
      { id: "s9",  name: "顧客データ集計.gs",   type: "gas",        role: "唯一の管理者", riskLevel: "warning" },
      { id: "s10", name: "商談管理シート",       type: "sheet",      role: "編集権限",     riskLevel: "ok" },
    ],
    departureImpact: "週次営業レポートの自動生成が停止し、手動集計が必要になります",
  },
  {
    id: "ito",
    name: "伊藤次郎",
    department: "経理部",
    riskScore: 6.8,
    systems: [
      { id: "s11", name: "経費精算自動化.gs",   type: "gas",        role: "共同管理者",   riskLevel: "ok" },
      { id: "s12", name: "経費DB読み取り",       type: "db",         role: "読み取り専用", riskLevel: "ok" },
    ],
    departureImpact: "経費精算の自動化に影響が出る可能性があります",
  },
  {
    id: "nakamura",
    name: "中村愛",
    department: "人事部",
    riskScore: 4.3,
    systems: [
      { id: "s13", name: "勤怠管理シート",       type: "sheet",      role: "編集権限",     riskLevel: "ok" },
      { id: "s14", name: "人事DB読み取り",        type: "db",         role: "読み取り専用", riskLevel: "ok" },
    ],
    departureImpact: "勤怠管理への影響は限定的です",
  },
  {
    id: "kobayashi",
    name: "小林拓也",
    department: "インフラ",
    riskScore: 7.5,
    systems: [
      { id: "s15", name: "AWS IAM管理",          type: "credential", role: "唯一の管理者", riskLevel: "critical" },
      { id: "s16", name: "監視ダッシュボード",    type: "infra",      role: "閲覧権限",     riskLevel: "ok" },
    ],
    departureImpact: "AWSのIAM管理が停止し、新規アクセス付与が不可能になります",
  },
  {
    id: "watanabe",
    name: "渡辺翔",
    department: "営業部",
    riskScore: 3.8,
    systems: [
      { id: "s17", name: "見積書テンプレート.gs", type: "gas",        role: "共同管理者",   riskLevel: "ok" },
    ],
    departureImpact: "見積書作成への影響は最小限です",
  },
];

const GAS_SCRIPTS: GasScript[] = [
  { id: "g1", name: "請求書自動送信.gs",   owner: "田中太郎",  status: "active",   risk: "critical", dependents: 5, lastUpdated: "2026-03-28" },
  { id: "g2", name: "採用通知自動化.gs",   owner: "鈴木花子",  status: "active",   risk: "warning",  dependents: 3, lastUpdated: "2026-02-14" },
  { id: "g3", name: "顧客データ集計.gs",   owner: "佐藤美咲",  status: "active",   risk: "warning",  dependents: 2, lastUpdated: "2026-01-20" },
  { id: "g4", name: "経費精算自動化.gs",   owner: "伊藤次郎",  status: "active",   risk: "ok",       dependents: 4, lastUpdated: "2026-03-01" },
  { id: "g5", name: "見積書テンプレート.gs",owner: "渡辺翔",    status: "active",   risk: "ok",       dependents: 2, lastUpdated: "2026-03-15" },
  { id: "g6", name: "旧メール通知.gs",     owner: "（退職済み）",status: "orphaned", risk: "critical", dependents: 0, lastUpdated: "2024-11-05" },
  { id: "g7", name: "月次バックアップ.gs", owner: "（退職済み）",status: "orphaned", risk: "warning",  dependents: 1, lastUpdated: "2025-06-12" },
  { id: "g8", name: "在庫確認自動化.gs",   owner: "（不明）",  status: "dormant",  risk: "warning",  dependents: 0, lastUpdated: "2025-01-03" },
];

const IMPROVEMENT_ACTIONS: ImprovementAction[] = [
  { id: "a1", priority: "critical", action: "請求書自動送信.gs に共同管理者を追加する",              riskReduction: 3.0 },
  { id: "a2", priority: "critical", action: "本番DBパスワードをAWS Secrets Managerに移行する",     riskReduction: 2.0 },
  { id: "a3", priority: "critical", action: "AWS IAM管理を複数名体制に変更する",                   riskReduction: 2.5 },
  { id: "a4", priority: "warning",  action: "採用通知自動化.gs のランブックを作成する",             riskReduction: 1.5 },
  { id: "a5", priority: "warning",  action: "AWS SSH鍵をSSM Session Managerで管理する",           riskReduction: 1.0 },
  { id: "a6", priority: "warning",  action: "孤立GASスクリプトの棚卸しと無効化を行う",             riskReduction: 1.2 },
];

const TREND_DATA = [
  { week: "W1", score: 8.1 },
  { week: "W2", score: 7.8 },
  { week: "W3", score: 7.2 },
  { week: "W4", score: 6.9 },
];

/* ============================================================
 * Helpers
 * ============================================================ */

function riskColor(level: RiskLevel): string {
  if (level === "critical") return "#ef4444";
  if (level === "warning")  return "#f59e0b";
  return "#22c55e";
}

function riskBg(level: RiskLevel): string {
  if (level === "critical") return "rgba(239,68,68,0.12)";
  if (level === "warning")  return "rgba(245,158,11,0.12)";
  return "rgba(34,197,94,0.12)";
}

function riskLabel(level: RiskLevel, locale: string): string {
  const map: Record<string, Record<RiskLevel, string>> = {
    ja: { critical: "危険", warning: "注意", ok: "安全" },
    en: { critical: "Critical", warning: "Warning", ok: "OK" },
    de: { critical: "Kritisch", warning: "Warnung", ok: "OK" },
    fr: { critical: "Critique", warning: "Attention", ok: "OK" },
    zh: { critical: "危险", warning: "警告", ok: "安全" },
    ko: { critical: "위험", warning: "주의", ok: "안전" },
    es: { critical: "Crítico", warning: "Advertencia", ok: "OK" },
    pt: { critical: "Crítico", warning: "Aviso", ok: "OK" },
  };
  return (map[locale] ?? map.en)[level];
}

function scoreColor(score: number): string {
  if (score >= 8) return "#ef4444";
  if (score >= 6) return "#f59e0b";
  return "#22c55e";
}

function systemIcon(type: SystemType) {
  const size = 14;
  if (type === "gas")        return <FileCode2    size={size} style={{ color: "#60a5fa" }} />;
  if (type === "sheet")      return <FileSpreadsheet size={size} style={{ color: "#34d399" }} />;
  if (type === "db")         return <Database     size={size} style={{ color: "#a78bfa" }} />;
  if (type === "credential") return <Key          size={size} style={{ color: "#fb923c" }} />;
  return                            <Settings     size={size} style={{ color: "#94a3b8" }} />;
}

function gasStatusBadge(status: GasStatus) {
  if (status === "orphaned") return <span style={{ background: "rgba(239,68,68,0.18)", color: "#ef4444", border: "1px solid rgba(239,68,68,0.4)", borderRadius: 6, fontSize: 11, padding: "2px 8px", fontWeight: 700 }}>孤立</span>;
  if (status === "dormant")  return <span style={{ background: "rgba(245,158,11,0.18)", color: "#f59e0b", border: "1px solid rgba(245,158,11,0.4)", borderRadius: 6, fontSize: 11, padding: "2px 8px", fontWeight: 700 }}>休眠</span>;
  return                            <span style={{ background: "rgba(34,197,94,0.18)",  color: "#22c55e", border: "1px solid rgba(34,197,94,0.4)",  borderRadius: 6, fontSize: 11, padding: "2px 8px", fontWeight: 700 }}>稼働中</span>;
}

/* ============================================================
 * Sub-components
 * ============================================================ */

function StatCard({ value, label, sub, color }: { value: string; label: string; sub?: string; color: string }) {
  return (
    <div style={{ background: "#0f172a", border: "1px solid #1e293b", borderRadius: 12, padding: "20px 24px", display: "flex", flexDirection: "column", gap: 4 }}>
      <div style={{ fontSize: 32, fontWeight: 800, color }}>{value}</div>
      <div style={{ fontSize: 14, color: "#94a3b8" }}>{label}</div>
      {sub && <div style={{ fontSize: 12, color: "#64748b", marginTop: 2 }}>{sub}</div>}
    </div>
  );
}

function RiskBadge({ level, locale }: { level: RiskLevel; locale: string }) {
  return (
    <span style={{
      background: riskBg(level),
      color: riskColor(level),
      border: `1px solid ${riskColor(level)}40`,
      borderRadius: 6,
      fontSize: 11,
      padding: "2px 8px",
      fontWeight: 700,
      whiteSpace: "nowrap",
    }}>
      {riskLabel(level, locale)}
    </span>
  );
}

function PersonCard({ person, locale }: { person: Person; locale: string }) {
  const [expanded, setExpanded] = useState(false);
  const color = scoreColor(person.riskScore);

  return (
    <div style={{ background: "#0f172a", border: `1px solid ${color}33`, borderRadius: 12, overflow: "hidden" }}>
      <button
        onClick={() => setExpanded(!expanded)}
        style={{
          width: "100%", display: "flex", alignItems: "center", gap: 12,
          padding: "16px 20px", background: "transparent", border: "none",
          cursor: "pointer", textAlign: "left",
        }}
      >
        <div style={{ width: 36, height: 36, borderRadius: "50%", background: `${color}22`, border: `2px solid ${color}`, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
          <Users size={16} style={{ color }} />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <span style={{ color: "#f1f5f9", fontWeight: 700, fontSize: 15 }}>{person.name}</span>
            <span style={{ color: "#64748b", fontSize: 13 }}>（{person.department}）</span>
          </div>
          <div style={{ color: "#64748b", fontSize: 12, marginTop: 2 }}>
            {locale === "ja" ? "管理システム数" : "Systems"}: {person.systems.length}
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexShrink: 0 }}>
          <div style={{ textAlign: "right" }}>
            <div style={{ color, fontWeight: 800, fontSize: 18 }}>{person.riskScore.toFixed(1)}</div>
            <div style={{ color: "#64748b", fontSize: 10 }}>{locale === "ja" ? "リスク" : "Risk"}</div>
          </div>
          {expanded ? <ChevronDown size={16} style={{ color: "#64748b" }} /> : <ChevronRight size={16} style={{ color: "#64748b" }} />}
        </div>
      </button>

      {expanded && (
        <div style={{ borderTop: "1px solid #1e293b", padding: "12px 20px 16px" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {person.systems.map((sys) => (
              <div key={sys.id} style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 12px", background: "#0a1628", borderRadius: 8 }}>
                <div style={{ flexShrink: 0 }}>{systemIcon(sys.type)}</div>
                <span style={{ color: "#e2e8f0", fontSize: 13, flex: 1 }}>{sys.name}</span>
                <span style={{ color: "#64748b", fontSize: 12, marginRight: 8 }}>[{sys.role}]</span>
                <RiskBadge level={sys.riskLevel} locale={locale} />
              </div>
            ))}
          </div>
          <div style={{ marginTop: 12, padding: "10px 12px", background: "rgba(239,68,68,0.06)", borderRadius: 8, borderLeft: "3px solid #ef444480" }}>
            <div style={{ color: "#94a3b8", fontSize: 12, marginBottom: 2 }}>
              {locale === "ja" ? "退職した場合の影響" : "Impact if person leaves"}:
            </div>
            <div style={{ color: "#fca5a5", fontSize: 13 }}>{person.departureImpact}</div>
          </div>
        </div>
      )}
    </div>
  );
}

function BlastRadiusSimulator({ locale }: { locale: string }) {
  const [selectedPerson, setSelectedPerson] = useState<string>("");
  const person = PEOPLE.find((p) => p.id === selectedPerson);

  const criticalCount = person?.systems.filter((s) => s.riskLevel === "critical").length ?? 0;
  const warningCount  = person?.systems.filter((s) => s.riskLevel === "warning").length ?? 0;

  return (
    <div style={{ background: "#0f172a", border: "1px solid #1e293b", borderRadius: 12, padding: 20 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
        <Activity size={16} style={{ color: "#60a5fa" }} />
        <span style={{ color: "#f1f5f9", fontWeight: 700, fontSize: 15 }}>
          {locale === "ja" ? "ブラスト半径シミュレーター" : "Blast Radius Simulator"}
        </span>
      </div>
      <div style={{ marginBottom: 16 }}>
        <label style={{ color: "#94a3b8", fontSize: 13, display: "block", marginBottom: 6 }}>
          {locale === "ja" ? "退職を想定する人を選択" : "Select person to simulate departure"}
        </label>
        <select
          value={selectedPerson}
          onChange={(e) => setSelectedPerson(e.target.value)}
          style={{
            width: "100%", background: "#0a1628", border: "1px solid #334155",
            borderRadius: 8, color: "#f1f5f9", padding: "8px 12px", fontSize: 14,
          }}
        >
          <option value="">{locale === "ja" ? "— 人を選んでください —" : "— Select a person —"}</option>
          {PEOPLE.map((p) => (
            <option key={p.id} value={p.id}>{p.name}（{p.department}）</option>
          ))}
        </select>
      </div>

      {person ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <div style={{ display: "flex", gap: 10 }}>
            <div style={{ flex: 1, background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.3)", borderRadius: 8, padding: "12px 16px", textAlign: "center" }}>
              <div style={{ fontSize: 24, fontWeight: 800, color: "#ef4444" }}>{criticalCount}</div>
              <div style={{ color: "#fca5a5", fontSize: 12 }}>{locale === "ja" ? "重大影響システム" : "Critical Systems"}</div>
            </div>
            <div style={{ flex: 1, background: "rgba(245,158,11,0.1)", border: "1px solid rgba(245,158,11,0.3)", borderRadius: 8, padding: "12px 16px", textAlign: "center" }}>
              <div style={{ fontSize: 24, fontWeight: 800, color: "#f59e0b" }}>{warningCount}</div>
              <div style={{ color: "#fde68a", fontSize: 12 }}>{locale === "ja" ? "要注意システム" : "Warning Systems"}</div>
            </div>
            <div style={{ flex: 1, background: "rgba(99,102,241,0.1)", border: "1px solid rgba(99,102,241,0.3)", borderRadius: 8, padding: "12px 16px", textAlign: "center" }}>
              <div style={{ fontSize: 24, fontWeight: 800, color: "#818cf8" }}>{person.systems.length}</div>
              <div style={{ color: "#a5b4fc", fontSize: 12 }}>{locale === "ja" ? "影響システム合計" : "Total Systems"}</div>
            </div>
          </div>

          <div style={{ background: "#0a1628", borderRadius: 8, padding: 14 }}>
            <div style={{ color: "#94a3b8", fontSize: 12, marginBottom: 8 }}>
              {locale === "ja" ? "影響を受けるシステム" : "Affected Systems"}:
            </div>
            {person.systems.map((sys) => (
              <div key={sys.id} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                <ArrowDown size={12} style={{ color: riskColor(sys.riskLevel) }} />
                <span style={{ color: "#e2e8f0", fontSize: 13 }}>{sys.name}</span>
                <span style={{ color: "#64748b", fontSize: 12 }}>— {sys.role}</span>
              </div>
            ))}
          </div>

          <div style={{ background: "rgba(239,68,68,0.06)", borderRadius: 8, borderLeft: "3px solid #ef444480", padding: "10px 14px" }}>
            <div style={{ color: "#fca5a5", fontSize: 13 }}>{person.departureImpact}</div>
          </div>
        </div>
      ) : (
        <div style={{ color: "#334155", fontSize: 14, textAlign: "center", padding: "24px 0" }}>
          {locale === "ja" ? "人を選択すると影響範囲が表示されます" : "Select a person to see blast radius"}
        </div>
      )}
    </div>
  );
}

function MiniTrendChart({ locale }: { locale: string }) {
  const max = 10;
  const width = 280;
  const height = 80;
  const padX = 30;
  const padY = 10;
  const innerW = width - padX * 2;
  const innerH = height - padY * 2;

  const points = TREND_DATA.map((d, i) => ({
    x: padX + (i / (TREND_DATA.length - 1)) * innerW,
    y: padY + (1 - d.score / max) * innerH,
    ...d,
  }));

  const pathD = points.map((p, i) => `${i === 0 ? "M" : "L"}${p.x},${p.y}`).join(" ");
  const lastScore  = TREND_DATA[TREND_DATA.length - 1].score;
  const firstScore = TREND_DATA[0].score;
  const improving  = lastScore < firstScore;

  return (
    <div style={{ background: "#0f172a", border: "1px solid #1e293b", borderRadius: 12, padding: 20 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {improving
            ? <TrendingDown size={16} style={{ color: "#22c55e" }} />
            : <TrendingUp   size={16} style={{ color: "#ef4444" }} />}
          <span style={{ color: "#f1f5f9", fontWeight: 700, fontSize: 14 }}>
            {locale === "ja" ? "属人化スコアの推移（4週間）" : "Personalization Score Trend (4 weeks)"}
          </span>
        </div>
        <span style={{ color: improving ? "#22c55e" : "#ef4444", fontSize: 12, fontWeight: 600 }}>
          {improving ? "▼ 改善中" : "▲ 悪化中"}
        </span>
      </div>
      <svg width={width} height={height} style={{ overflow: "visible" }}>
        <defs>
          <linearGradient id="trendGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#60a5fa" stopOpacity="0.3" />
            <stop offset="100%" stopColor="#60a5fa" stopOpacity="0" />
          </linearGradient>
        </defs>
        {/* fill area */}
        <path
          d={`${pathD} L${points[points.length - 1].x},${padY + innerH} L${points[0].x},${padY + innerH} Z`}
          fill="url(#trendGrad)"
        />
        {/* line */}
        <path d={pathD} stroke="#60a5fa" strokeWidth="2" fill="none" strokeLinejoin="round" />
        {/* dots + labels */}
        {points.map((p) => (
          <g key={p.week}>
            <circle cx={p.x} cy={p.y} r={4} fill="#60a5fa" />
            <text x={p.x} y={p.y - 8} textAnchor="middle" fill="#94a3b8" fontSize="10">{p.score}</text>
            <text x={p.x} y={height - 2}  textAnchor="middle" fill="#64748b" fontSize="10">{p.week}</text>
          </g>
        ))}
      </svg>
    </div>
  );
}

/* ============================================================
 * Main Page
 * ============================================================ */

export default function PeopleRiskPage() {
  const locale = useLocale();
  const t = (appDict as Record<string, Record<string, Record<string, string>>>).peopleRisk?.[locale]
         ?? (appDict as Record<string, Record<string, Record<string, string>>>).peopleRisk?.en
         ?? {};

  const [gasFilter, setGasFilter] = useState<"all" | RiskLevel>("all");
  const [expandedAll, setExpandedAll] = useState(false);

  const filteredGas = GAS_SCRIPTS.filter((g) => gasFilter === "all" || g.risk === gasFilter);

  const totalPeople    = PEOPLE.length;
  const singleDep      = PEOPLE.filter((p) => p.systems.some((s) => s.role.includes("唯一"))).length;
  const busFactor1     = singleDep;
  const avgRisk        = (PEOPLE.reduce((sum, p) => sum + p.riskScore, 0) / PEOPLE.length).toFixed(1);

  const tl = (key: string, fallback: string) => t[key] ?? fallback;

  return (
    <div style={{ minHeight: "100vh", background: "#020817", color: "#f1f5f9", padding: "32px 24px", maxWidth: 1100, margin: "0 auto" }}>

      {/* Header */}
      <div style={{ marginBottom: 32 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 8 }}>
          <div style={{ width: 40, height: 40, borderRadius: 10, background: "rgba(239,68,68,0.15)", border: "1px solid rgba(239,68,68,0.3)", display: "flex", alignItems: "center", justifyContent: "center" }}>
            <UserX size={20} style={{ color: "#ef4444" }} />
          </div>
          <h1 style={{ fontSize: 24, fontWeight: 800, color: "#f1f5f9", margin: 0 }}>
            {tl("title", locale === "ja" ? "属人化リスクダッシュボード" : "People Risk / Personalization Dashboard")}
          </h1>
          <Badge style={{ background: "rgba(239,68,68,0.15)", color: "#ef4444", border: "1px solid rgba(239,68,68,0.3)", fontSize: 11 }}>
            {locale === "ja" ? "日本市場特化" : "Japan Market"}
          </Badge>
        </div>
        <p style={{ color: "#64748b", fontSize: 14, margin: 0 }}>
          {tl("subtitle", locale === "ja"
            ? "誰に依存しているか、誰が退職したら何が壊れるかを可視化します"
            : "Visualize who depends on whom, and what breaks if someone leaves")}
        </p>
      </div>

      {/* Section 1: Risk Overview */}
      <section style={{ marginBottom: 32 }}>
        <h2 style={{ fontSize: 16, fontWeight: 700, color: "#94a3b8", marginBottom: 16, textTransform: "uppercase", letterSpacing: "0.05em" }}>
          {tl("overviewTitle", locale === "ja" ? "リスク概要" : "Risk Overview")}
        </h2>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: 16 }}>
          <StatCard value={String(totalPeople)} label={tl("totalPeople", locale === "ja" ? "システムアクセス者数" : "Total People with Access")} color="#60a5fa" />
          <StatCard value={String(singleDep)}   label={tl("singleDep", locale === "ja" ? "単一担当者依存システム" : "Single-Person Dependency")} sub="🔴 Bus factor = 1" color="#ef4444" />
          <StatCard value={String(busFactor1)}  label={tl("busFactor", locale === "ja" ? "バスファクター = 1" : "Bus Factor = 1 Systems")} color="#ef4444" />
          <StatCard value={`${avgRisk}/10`}      label={tl("avgRisk", locale === "ja" ? "平均リスクスコア" : "Average Risk Score")} color="#f59e0b" />
        </div>
      </section>

      {/* Section 2: Person × System Map */}
      <section style={{ marginBottom: 32 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
          <h2 style={{ fontSize: 16, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.05em", margin: 0 }}>
            {tl("personMapTitle", locale === "ja" ? "人物 × システム マップ" : "Person × System Map")}
          </h2>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setExpandedAll(!expandedAll)}
            style={{ fontSize: 12, color: "#94a3b8", borderColor: "#334155" }}
          >
            {expandedAll
              ? (locale === "ja" ? "すべて折りたたむ" : "Collapse All")
              : (locale === "ja" ? "すべて展開する" : "Expand All")}
          </Button>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))", gap: 12 }}>
          {PEOPLE
            .slice()
            .sort((a, b) => b.riskScore - a.riskScore)
            .map((person) => (
              <PersonCard key={person.id} person={person} locale={locale} />
            ))}
        </div>
      </section>

      {/* Section 3: Blast Radius Simulator */}
      <section style={{ marginBottom: 32 }}>
        <h2 style={{ fontSize: 16, fontWeight: 700, color: "#94a3b8", marginBottom: 16, textTransform: "uppercase", letterSpacing: "0.05em" }}>
          {tl("blastRadiusTitle", locale === "ja" ? "ブラスト半径シミュレーター" : "Blast Radius Simulator")}
        </h2>
        <BlastRadiusSimulator locale={locale} />
      </section>

      {/* Section 4: GAS Inventory */}
      <section style={{ marginBottom: 32 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
          <h2 style={{ fontSize: 16, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.05em", margin: 0 }}>
            {tl("gasTitle", locale === "ja" ? "GAS棚卸し結果" : "GAS Inventory")}
          </h2>
          <div style={{ display: "flex", gap: 8 }}>
            {(["all", "critical", "warning", "ok"] as const).map((f) => (
              <button
                key={f}
                onClick={() => setGasFilter(f)}
                style={{
                  background: gasFilter === f ? (f === "all" ? "#334155" : riskBg(f as RiskLevel)) : "transparent",
                  color: f === "all" ? "#94a3b8" : (gasFilter === f ? riskColor(f as RiskLevel) : "#64748b"),
                  border: `1px solid ${f === "all" ? "#334155" : (gasFilter === f ? riskColor(f as RiskLevel) + "60" : "#1e293b")}`,
                  borderRadius: 6, padding: "4px 10px", fontSize: 12, cursor: "pointer",
                }}
              >
                {f === "all" ? (locale === "ja" ? "すべて" : "All") : riskLabel(f as RiskLevel, locale)}
              </button>
            ))}
          </div>
        </div>
        <div style={{ background: "#0f172a", border: "1px solid #1e293b", borderRadius: 12, overflow: "hidden" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid #1e293b" }}>
                {[
                  locale === "ja" ? "スクリプト名" : "Script Name",
                  locale === "ja" ? "オーナー" : "Owner",
                  locale === "ja" ? "ステータス" : "Status",
                  locale === "ja" ? "リスク" : "Risk",
                  locale === "ja" ? "依存数" : "Deps",
                  locale === "ja" ? "最終更新" : "Last Updated",
                ].map((h) => (
                  <th key={h} style={{ padding: "12px 16px", textAlign: "left", color: "#64748b", fontSize: 12, fontWeight: 600, whiteSpace: "nowrap" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filteredGas.map((g, i) => (
                <tr key={g.id} style={{ borderBottom: i < filteredGas.length - 1 ? "1px solid #0f172a" : "none", background: i % 2 === 0 ? "transparent" : "#0a1628" }}>
                  <td style={{ padding: "10px 16px", color: "#e2e8f0", fontSize: 13, display: "flex", alignItems: "center", gap: 8 }}>
                    <FileCode2 size={13} style={{ color: "#60a5fa", flexShrink: 0 }} />
                    {g.name}
                  </td>
                  <td style={{ padding: "10px 16px", color: g.status === "orphaned" ? "#ef4444" : "#94a3b8", fontSize: 13 }}>{g.owner}</td>
                  <td style={{ padding: "10px 16px" }}>{gasStatusBadge(g.status)}</td>
                  <td style={{ padding: "10px 16px" }}><RiskBadge level={g.risk} locale={locale} /></td>
                  <td style={{ padding: "10px 16px", color: "#94a3b8", fontSize: 13 }}>{g.dependents}</td>
                  <td style={{ padding: "10px 16px", color: "#64748b", fontSize: 12 }}>{g.lastUpdated}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Section 5: Improvement Actions */}
      <section style={{ marginBottom: 32 }}>
        <h2 style={{ fontSize: 16, fontWeight: 700, color: "#94a3b8", marginBottom: 16, textTransform: "uppercase", letterSpacing: "0.05em" }}>
          {tl("actionsTitle", locale === "ja" ? "改善アクション" : "Improvement Actions")}
        </h2>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {IMPROVEMENT_ACTIONS.map((action, i) => (
            <div
              key={action.id}
              style={{
                background: "#0f172a",
                border: `1px solid ${riskColor(action.priority)}33`,
                borderRadius: 10,
                padding: "14px 18px",
                display: "flex",
                alignItems: "center",
                gap: 14,
              }}
            >
              <div style={{ width: 24, height: 24, borderRadius: "50%", background: riskBg(action.priority), border: `1px solid ${riskColor(action.priority)}60`, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                <span style={{ fontSize: 11, fontWeight: 800, color: riskColor(action.priority) }}>{i + 1}</span>
              </div>
              <div style={{ flex: 1 }}>
                <span style={{ color: "#e2e8f0", fontSize: 14 }}>{action.action}</span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
                <RiskBadge level={action.priority} locale={locale} />
                <span style={{ color: "#22c55e", fontSize: 12, fontWeight: 700, whiteSpace: "nowrap" }}>
                  -{action.riskReduction} {locale === "ja" ? "リスク" : "risk"}
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  style={{ fontSize: 11, padding: "3px 10px", color: "#60a5fa", borderColor: "#334155" }}
                >
                  {locale === "ja" ? "対応する" : "Action"}
                </Button>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Section 6: Trend */}
      <section>
        <h2 style={{ fontSize: 16, fontWeight: 700, color: "#94a3b8", marginBottom: 16, textTransform: "uppercase", letterSpacing: "0.05em" }}>
          {tl("trendTitle", locale === "ja" ? "週次トレンド" : "Weekly Trend")}
        </h2>
        <MiniTrendChart locale={locale} />
      </section>

    </div>
  );
}
