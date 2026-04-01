"use client";

import { useState } from "react";
import { useLocale } from "@/lib/useLocale";

const DORA_DICT: Record<string, Record<string, string>> = {
  en: { title: "DORA Compliance Dashboard", subtitle: "Digital Operational Resilience Act", loading: "Loading...", overallScore: "DORA Compliance", compliant: "Compliant", partial: "Partial", nonCompliant: "Non-Compliant" },
  ja: { title: "DORA コンプライアンスダッシュボード", subtitle: "EU金融機関向け規制", loading: "読み込み中...", overallScore: "DORA 準拠率", compliant: "準拠", partial: "一部準拠", nonCompliant: "非準拠" },
};

interface DoraPillar {
  id: string;
  name: string;
  score: number;
  status: string;
}

const DEMO_PILLARS: DoraPillar[] = [
  { id: "P1", name: "ICT Risk Management", score: 68, status: "partial" },
  { id: "P2", name: "Incident Management", score: 75, status: "partial" },
  { id: "P3", name: "Resilience Testing", score: 82, status: "partial" },
  { id: "P4", name: "Third-Party Risk", score: 55, status: "non_compliant" },
  { id: "P5", name: "Information Sharing", score: 90, status: "compliant" },
];

export default function DoraPage() {
  const locale = useLocale();
  const t = DORA_DICT[locale] ?? DORA_DICT.en;
  const [pillars] = useState(DEMO_PILLARS);

  return (
    <div className="max-w-[1200px] mx-auto px-6 py-10">
      <h1 className="text-2xl font-bold mb-1 text-white">{t.title}</h1>
      <p className="text-[#94a3b8] text-sm mb-4">{t.subtitle}</p>
      <p className="text-white mb-4">Overall: 72%</p>
      <div className="space-y-2">
        {pillars.map((p) => (
          <div key={p.id} className="flex items-center gap-4 text-white">
            <span className="w-48">{p.name}</span>
            <div className="flex-1 h-3 bg-[#1e293b] rounded-full overflow-hidden">
              <div className="h-full bg-emerald-400 rounded-full" style={{ width: `${p.score}%` }} />
            </div>
            <span className="font-mono w-12 text-right">{p.score}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}
