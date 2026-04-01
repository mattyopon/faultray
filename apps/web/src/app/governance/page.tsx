"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useState, useEffect } from "react";
import { Scale } from "lucide-react";
import { useLocale } from "@/lib/useLocale";

const T: Record<string, Record<string, string>> = {
  en: { title: "AI Governance Dashboard", subtitle: "METI / ISO 42001 / AI Act compliance", maturity: "Maturity Level", meti: "METI Score", iso: "ISO 42001 Score", frameworks: "Framework Status", gaps: "Top Gaps", policies: "Policy Templates" },
  ja: { title: "AI ガバナンスダッシュボード", subtitle: "METI / ISO 42001 / AI推進法 コンプライアンス", maturity: "成熟度レベル", meti: "METIスコア", iso: "ISO 42001スコア", frameworks: "フレームワーク状況", gaps: "主要ギャップ", policies: "ポリシーテンプレート" },
};

const FRAMEWORKS = [
  { name: "METI AI Guidelines", reqs: 28, score: 71 },
  { name: "ISO 42001", reqs: 25, score: 64 },
  { name: "AI推進法", reqs: 15, score: 80 },
];

const GAPS = [
  { title: "Bias evaluation process not defined", severity: "critical" },
  { title: "Incident response for AI failures missing", severity: "high" },
  { title: "Third-party AI vendor audit incomplete", severity: "high" },
  { title: "Model versioning policy not documented", severity: "medium" },
  { title: "Data lineage tracking not implemented", severity: "medium" },
];

const POLICIES = ["AI Usage Policy", "Data Governance Policy", "Model Risk Policy", "Incident Response Policy", "Vendor AI Policy"];

export default function GovernancePage() {
  const locale = useLocale();
  const t = T[locale] ?? T.en;
  const [maturity, setMaturity] = useState(3);
  const [metiScore, setMetiScore] = useState(71);
  const [isoScore, setIsoScore] = useState(64);

  useEffect(() => {
    fetch("/api/governance?action=ai-governance")
      .then((r) => r.json())
      .then((d) => {
        if (d?.maturity_level) setMaturity(d.maturity_level);
        if (d?.meti_score) setMetiScore(d.meti_score);
        if (d?.iso_42001_score) setIsoScore(d.iso_42001_score);
      })
      .catch(() => {});
  }, []);

  return (
    <div className="max-w-[1200px] mx-auto px-6 py-10">
      <h1 className="text-2xl font-bold mb-1 flex items-center gap-3">
        <Scale size={24} className="text-[#FFD700]" />
        {t.title}
      </h1>
      <p className="text-[#94a3b8] text-sm mb-8">{t.subtitle}</p>

      <div className="grid md:grid-cols-3 gap-4 mb-8">
        <Card>
          <p className="text-xs text-[#64748b] uppercase mb-2">{t.maturity}</p>
          <p className="text-3xl font-bold text-[#FFD700]">{maturity} / 5</p>
        </Card>
        <Card>
          <p className="text-xs text-[#64748b] uppercase mb-2">{t.meti}</p>
          <p className="text-3xl font-bold text-[#FFD700]">{metiScore}%</p>
        </Card>
        <Card>
          <p className="text-xs text-[#64748b] uppercase mb-2">{t.iso}</p>
          <p className="text-3xl font-bold text-[#FFD700]">{isoScore}%</p>
        </Card>
      </div>

      <div className="grid md:grid-cols-2 gap-6 mb-6">
        <Card>
          <h2 className="text-lg font-bold mb-4">{t.frameworks}</h2>
          <div className="space-y-4">
            {FRAMEWORKS.map((f) => (
              <div key={f.name}>
                <div className="flex justify-between text-sm mb-1">
                  <span className="text-[#94a3b8]">{f.name}</span>
                  <span className="font-mono">{f.score}%</span>
                </div>
                <div className="h-2 bg-[#1e293b] rounded-full overflow-hidden">
                  <div className={`h-full rounded-full ${f.score >= 80 ? "bg-emerald-400" : f.score >= 60 ? "bg-amber-400" : "bg-red-400"}`} style={{ width: `${f.score}%` }} />
                </div>
                <p className="text-xs text-[#475569] mt-1">{f.reqs} requirements</p>
              </div>
            ))}
          </div>
        </Card>

        <Card>
          <h2 className="text-lg font-bold mb-4">{t.gaps}</h2>
          <div className="space-y-2">
            {GAPS.map((g, i) => (
              <div key={i} className="flex items-start gap-3">
                <Badge variant={g.severity === "critical" ? "red" : g.severity === "high" ? "yellow" : "default"}>{g.severity}</Badge>
                <span className="text-sm text-[#94a3b8]">{g.title}</span>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <Card>
        <h2 className="text-lg font-bold mb-4">{t.policies}</h2>
        <div className="flex flex-wrap gap-2">
          {POLICIES.map((p) => (
            <Button key={p} variant="secondary" size="sm">{p}</Button>
          ))}
        </div>
      </Card>
    </div>
  );
}
