"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useState, useEffect } from "react";
import { ShieldAlert, Info, ExternalLink } from "lucide-react";
import { useLocale } from "@/lib/useLocale";

const T: Record<string, {
  title: string;
  subtitle: string;
  compliant: string;
  partial: string;
  nonCompliant: string;
  contextTitle: string;
  contextBody: string;
  contextLink: string;
  overallScore: string;
  status: string;
  pillars: string;
  pillarOverview: string;
  dataNote: string;
}> = {
  en: {
    title: "DORA Compliance Dashboard",
    subtitle: "Digital Operational Resilience Act (EU Regulation 2022/2554) — Effective January 17, 2025",
    compliant: "Compliant",
    partial: "Partial",
    nonCompliant: "Non-Compliant",
    contextTitle: "Is DORA relevant to you?",
    contextBody:
      "DORA is mandatory for EU financial entities (banks, insurers, investment firms, crypto-asset service providers). If your customers include EU-regulated financial institutions, you may be in scope as a critical ICT third-party provider. Japanese SMEs that only serve domestic clients are typically out of scope.",
    contextLink: "DORA official text (EUR-Lex)",
    overallScore: "Overall Score",
    status: "Status",
    pillars: "Pillars",
    pillarOverview: "5 Pillar Overview",
    dataNote: "Scores are derived from your simulation results. Run a simulation to update these values.",
  },
  ja: {
    title: "DORA コンプライアンスダッシュボード",
    subtitle: "EU デジタル運用回復力法（規則2022/2554）— 2025年1月17日施行",
    compliant: "準拠",
    partial: "一部準拠",
    nonCompliant: "非準拠",
    contextTitle: "DORAはあなたに関係ありますか？",
    contextBody:
      "DORAはEU域内の金融機関（銀行・保険会社・投資会社・暗号資産事業者）に義務が課される規制です。EU規制金融機関を顧客とする場合、重要ICTサードパーティとして適用される可能性があります。国内顧客のみを対象とする日本の中小IT企業は、通常対象外です。",
    contextLink: "DORA公式テキスト（EUR-Lex）",
    overallScore: "総合スコア",
    status: "ステータス",
    pillars: "柱の数",
    pillarOverview: "5柱の概要",
    dataNote: "スコアはシミュレーション結果から算出されます。最新の値を取得するにはシミュレーションを実行してください。",
  },
};

interface Pillar { id: string; name: string; score: number; status: string; }

// DORA-01: Default pillars — will be overwritten by API response when available
const DEFAULT_PILLARS: Pillar[] = [
  { id: "P1", name: "ICT Risk Management", score: 68, status: "partial" },
  { id: "P2", name: "Incident Management", score: 75, status: "partial" },
  { id: "P3", name: "Resilience Testing", score: 82, status: "partial" },
  { id: "P4", name: "Third-Party Risk", score: 55, status: "non_compliant" },
  { id: "P5", name: "Information Sharing", score: 90, status: "compliant" },
];

export default function DoraPage() {
  const locale = useLocale();
  const t = T[locale] ?? T.en;
  const [score, setScore] = useState<number | null>(null); // DORA-01: null = not yet loaded
  const [pillars, setPillars] = useState<Pillar[]>(DEFAULT_PILLARS);
  const [isFromApi, setIsFromApi] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/governance?action=dora", { signal: controller.signal })
      .then((r) => r.json())
      .then((d: { overall_score?: number; pillars?: Pillar[] }) => {
        if (typeof d?.overall_score === "number") {
          setScore(d.overall_score);
          setIsFromApi(true);
        }
        if (Array.isArray(d?.pillars) && d.pillars.length > 0) {
          setPillars(d.pillars);
        }
      })
      .catch(() => {
        // Fallback: use DEFAULT_PILLARS average
        const avg = Math.round(DEFAULT_PILLARS.reduce((sum, p) => sum + p.score, 0) / DEFAULT_PILLARS.length);
        setScore(avg);
      });
    return () => controller.abort();
  }, []);

  const displayScore = score ?? Math.round(DEFAULT_PILLARS.reduce((s, p) => s + p.score, 0) / DEFAULT_PILLARS.length);

  return (
    <div className="max-w-[1200px] mx-auto px-6 py-10">
      <h1 className="text-2xl font-bold mb-1 flex items-center gap-3">
        <ShieldAlert size={24} className="text-[#FFD700]" />
        {t.title}
      </h1>
      <p className="text-[#94a3b8] text-sm mb-6">{t.subtitle}</p>

      {/* DORA-02: Context banner — clarify applicability for Japanese SMEs */}
      <div className="mb-8 p-4 rounded-xl border border-blue-500/20 bg-blue-500/[0.05] flex gap-3">
        <Info size={16} className="text-blue-400 shrink-0 mt-0.5" />
        <div>
          <p className="text-sm font-semibold text-blue-300 mb-1">{t.contextTitle}</p>
          <p className="text-sm text-[#94a3b8] leading-relaxed mb-2">{t.contextBody}</p>
          <a
            href="https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32022R2554"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300 transition-colors"
          >
            {t.contextLink}
            <ExternalLink size={11} />
          </a>
        </div>
      </div>

      <div className="grid md:grid-cols-3 gap-4 mb-8">
        <Card>
          <p className="text-xs text-[#64748b] uppercase mb-2">{t.overallScore}</p>
          <p className="text-3xl font-bold text-[#FFD700]">{displayScore}%</p>
          {!isFromApi && (
            <p className="text-[10px] text-[#475569] mt-1">{locale === "ja" ? "サンプルデータ" : "Sample data"}</p>
          )}
        </Card>
        <Card>
          <p className="text-xs text-[#64748b] uppercase mb-2">{t.status}</p>
          <Badge variant={displayScore >= 80 ? "green" : displayScore >= 60 ? "yellow" : "red"}>
            {displayScore >= 80 ? t.compliant : displayScore >= 60 ? t.partial : t.nonCompliant}
          </Badge>
        </Card>
        <Card>
          <p className="text-xs text-[#64748b] uppercase mb-2">{t.pillars}</p>
          <p className="text-2xl font-bold">{pillars.length}</p>
        </Card>
      </div>

      <Card>
        <h2 className="text-lg font-bold mb-4">{t.pillarOverview}</h2>
        <div className="space-y-3">
          {pillars.map((p) => (
            <div key={p.id} className="flex items-center gap-4">
              <span className="w-48 text-sm text-[#94a3b8]">{p.name}</span>
              <div className="flex-1 h-3 bg-[#1e293b] rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all duration-500 ${p.score >= 80 ? "bg-emerald-400" : p.score >= 60 ? "bg-amber-400" : "bg-red-400"}`}
                  style={{ width: `${p.score}%` }}
                />
              </div>
              <span className="font-mono w-12 text-right text-sm">{p.score}%</span>
              <Badge variant={p.status === "compliant" ? "green" : p.status === "partial" ? "yellow" : "red"}>
                {p.status === "compliant" ? t.compliant : p.status === "partial" ? t.partial : t.nonCompliant}
              </Badge>
            </div>
          ))}
        </div>
        {!isFromApi && (
          <p className="text-xs text-[#475569] mt-4 pt-3 border-t border-[#1e293b] flex items-center gap-1.5">
            <Info size={11} />
            {t.dataNote}
          </p>
        )}
      </Card>
    </div>
  );
}
