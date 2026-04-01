"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useState, useEffect } from "react";
import { ShieldAlert } from "lucide-react";
import { useLocale } from "@/lib/useLocale";

const T: Record<string, Record<string, string>> = {
  en: { title: "DORA Compliance Dashboard", subtitle: "Digital Operational Resilience Act", compliant: "Compliant", partial: "Partial", nonCompliant: "Non-Compliant" },
  ja: { title: "DORA コンプライアンスダッシュボード", subtitle: "EU金融機関向け規制", compliant: "準拠", partial: "一部準拠", nonCompliant: "非準拠" },
};

interface Pillar { id: string; name: string; score: number; status: string; }

const PILLARS: Pillar[] = [
  { id: "P1", name: "ICT Risk Management", score: 68, status: "partial" },
  { id: "P2", name: "Incident Management", score: 75, status: "partial" },
  { id: "P3", name: "Resilience Testing", score: 82, status: "partial" },
  { id: "P4", name: "Third-Party Risk", score: 55, status: "non_compliant" },
  { id: "P5", name: "Information Sharing", score: 90, status: "compliant" },
];

export default function DoraPage() {
  const locale = useLocale();
  const t = T[locale] ?? T.en;
  const [score, setScore] = useState(72);
  const [pillars] = useState(PILLARS);

  useEffect(() => {
    fetch("/api/governance?action=dora")
      .then((r) => r.json())
      .then((d) => { if (d?.overall_score) setScore(d.overall_score); })
      .catch(() => {});
  }, []);

  return (
    <div className="max-w-[1200px] mx-auto px-6 py-10">
      <h1 className="text-2xl font-bold mb-1 flex items-center gap-3">
        <ShieldAlert size={24} className="text-[#FFD700]" />
        {t.title}
      </h1>
      <p className="text-[#94a3b8] text-sm mb-8">{t.subtitle}</p>

      <div className="grid md:grid-cols-3 gap-4 mb-8">
        <Card>
          <p className="text-xs text-[#64748b] uppercase mb-2">Overall Score</p>
          <p className="text-3xl font-bold text-[#FFD700]">{score}%</p>
        </Card>
        <Card>
          <p className="text-xs text-[#64748b] uppercase mb-2">Status</p>
          <Badge variant={score >= 80 ? "green" : score >= 60 ? "yellow" : "red"}>
            {score >= 80 ? t.compliant : score >= 60 ? t.partial : t.nonCompliant}
          </Badge>
        </Card>
        <Card>
          <p className="text-xs text-[#64748b] uppercase mb-2">Pillars</p>
          <p className="text-2xl font-bold">{pillars.length}</p>
        </Card>
      </div>

      <Card>
        <h2 className="text-lg font-bold mb-4">5 Pillar Overview</h2>
        <div className="space-y-3">
          {pillars.map((p) => (
            <div key={p.id} className="flex items-center gap-4">
              <span className="w-48 text-sm text-[#94a3b8]">{p.name}</span>
              <div className="flex-1 h-3 bg-[#1e293b] rounded-full overflow-hidden">
                <div className={`h-full rounded-full ${p.score >= 80 ? "bg-emerald-400" : p.score >= 60 ? "bg-amber-400" : "bg-red-400"}`} style={{ width: `${p.score}%` }} />
              </div>
              <span className="font-mono w-12 text-right text-sm">{p.score}%</span>
              <Badge variant={p.status === "compliant" ? "green" : p.status === "partial" ? "yellow" : "red"}>
                {p.status === "compliant" ? t.compliant : p.status === "partial" ? t.partial : t.nonCompliant}
              </Badge>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
