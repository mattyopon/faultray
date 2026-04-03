"use client";

/**
 * DEMO-01 fix: Replace bare redirect with a real demo landing page.
 * DEMO-02 fix: Show Free vs Pro feature distinction to drive upgrades.
 */

import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { useLocale } from "@/lib/useLocale";
import {
  Zap,
  Shield,
  BarChart3,
  FileText,
  Lock,
  CheckCircle2,
  ArrowRight,
  Play,
} from "lucide-react";

const T = {
  en: {
    headline: "See FaultRay in Action",
    sub: "Explore a live simulation of a real-world SaaS topology — no sign-up required.",
    freeBadge: "Free Plan",
    proBadge: "Pro Plan",
    freeCTA: "Try Free Demo",
    proCTA: "Start Pro Trial",
    pricingLink: "See all plans",
    freeTitle: "Free — Get Started",
    proTitle: "Pro — Full Power",
    freeDesc: "Run up to 5 simulations per month. Discover your top vulnerabilities instantly.",
    proDesc: "Unlimited simulations, AI advisor, PDF reports, GameDay planner, and more.",
    freeFeatures: [
      "Up to 5 simulations / month",
      "Core fault-chain analysis",
      "Availability score (N-nines)",
      "Top 3 remediation suggestions",
      "Manual topology (YAML)",
    ] as string[],
    proFeatures: [
      "Unlimited simulations",
      "AI reliability advisor",
      "Exportable PDF / HTML reports",
      "GameDay & incident planner",
      "Cloud discovery (AWS / GCP / Azure)",
      "Compliance dashboards (SOC 2, DORA)",
      "Priority email support",
    ] as string[],
    demoScenarios: "Try a scenario",
    scenarios: [
      { id: "web-saas",     label: "SaaS Web App",    desc: "3-tier: CDN → API → PostgreSQL" },
      { id: "microservice", label: "Microservices",   desc: "12 services with circuit breakers" },
      { id: "ml-pipeline",  label: "ML Pipeline",     desc: "Training + inference + feature store" },
    ] as Array<{ id: string; label: string; desc: string }>,
  },
  ja: {
    headline: "FaultRay を実際に体験する",
    sub: "登録不要で、実際の SaaS トポロジーのシミュレーションをお試しいただけます。",
    freeBadge: "Freeプラン",
    proBadge: "Proプラン",
    freeCTA: "無料デモを試す",
    proCTA: "Pro トライアル開始",
    pricingLink: "全プランを見る",
    freeTitle: "Free — まず始める",
    proTitle: "Pro — フル機能",
    freeDesc: "月5回のシミュレーションで主要な脆弱性を即座に発見。",
    proDesc: "無制限シミュレーション、AI アドバイザー、PDFレポート、GameDay プランナーなど。",
    freeFeatures: [
      "月5回のシミュレーション",
      "コア障害チェーン分析",
      "可用性スコア（N ナイン）",
      "改善提案トップ3",
      "手動トポロジー（YAML）",
    ] as string[],
    proFeatures: [
      "無制限シミュレーション",
      "AI 信頼性アドバイザー",
      "PDF / HTML レポート出力",
      "GameDay・インシデントプランナー",
      "クラウド自動検出（AWS / GCP / Azure）",
      "コンプライアンスダッシュボード（SOC 2, DORA）",
      "優先メールサポート",
    ] as string[],
    demoScenarios: "シナリオを試す",
    scenarios: [
      { id: "web-saas",     label: "SaaS Web アプリ", desc: "3 層構成: CDN → API → PostgreSQL" },
      { id: "microservice", label: "マイクロサービス", desc: "12 サービス + サーキットブレーカー" },
      { id: "ml-pipeline",  label: "ML パイプライン",  desc: "学習・推論・特徴量ストア" },
    ] as Array<{ id: string; label: string; desc: string }>,
  },
} as const;

export default function DemoPage() {
  const rawLocale = useLocale();
  const locale = rawLocale in T ? (rawLocale as keyof typeof T) : "en";
  const t = T[locale];

  return (
    <div className="max-w-5xl mx-auto px-6 py-12">
      {/* PAGE-01: 営業デモ向けショートカットバナー */}
      <div className="mb-8 p-4 rounded-xl border border-[#1e293b] bg-[#0d1117] flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-xs text-[#64748b]">
          <BarChart3 size={14} className="text-[#FFD700]" />
          <span>
            {locale === "ja" ? "営業デモ用 クイックリンク:" : "Sales demo quick links:"}
          </span>
        </div>
        <div className="flex flex-wrap gap-2">
          {[
            { label: locale === "ja" ? "シミュレーション" : "Live Simulation", href: "/simulate" },
            { label: locale === "ja" ? "レポート例" : "Sample Report", href: "/reports" },
            { label: locale === "ja" ? "料金プラン" : "Pricing", href: "/pricing" },
            { label: locale === "ja" ? "導入事例" : "Case Studies", href: "/case-studies" },
            { label: locale === "ja" ? "稟議書" : "Enterprise Docs", href: "/ringi" },
          ].map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="text-xs font-medium px-3 py-1.5 rounded-lg border border-[#1e293b] text-[#94a3b8] hover:text-white hover:border-[#334155] transition-colors"
            >
              {link.label}
            </Link>
          ))}
        </div>
      </div>

      {/* Hero */}
      <div className="text-center mb-12">
        <div className="inline-flex items-center gap-2 bg-[#FFD700]/10 border border-[#FFD700]/20 rounded-full px-4 py-1.5 mb-5">
          <Play size={14} className="text-[#FFD700]" />
          <span className="text-xs font-semibold text-[#FFD700] uppercase tracking-wide">Live Demo</span>
        </div>
        <h1 className="text-4xl font-bold mb-4 leading-tight">{t.headline}</h1>
        <p className="text-[#94a3b8] text-lg max-w-2xl mx-auto">{t.sub}</p>
      </div>

      {/* Quick scenario cards */}
      <div className="mb-12">
        <p className="text-sm font-semibold text-[#64748b] uppercase tracking-wide mb-4">
          {t.demoScenarios}
        </p>
        <div className="grid sm:grid-cols-3 gap-4">
          {t.scenarios.map((s) => (
            <Link key={s.id} href={`/simulate?sample=${s.id}`}>
              <Card className="hover:border-[#FFD700]/40 transition-colors cursor-pointer h-full">
                <div className="flex items-start gap-3">
                  <div className="p-2 rounded-lg bg-[#FFD700]/10">
                    <Zap size={16} className="text-[#FFD700]" />
                  </div>
                  <div>
                    <p className="font-semibold text-sm mb-1">{s.label}</p>
                    <p className="text-xs text-[#64748b]">{s.desc}</p>
                  </div>
                </div>
              </Card>
            </Link>
          ))}
        </div>
      </div>

      {/* DEMO-02: Free vs Pro feature grid */}
      <div className="grid md:grid-cols-2 gap-6 mb-12">
        {/* Free */}
        <Card>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-bold">{t.freeTitle}</h2>
            <Badge variant="default">{t.freeBadge}</Badge>
          </div>
          <p className="text-sm text-[#94a3b8] mb-6">{t.freeDesc}</p>
          <ul className="space-y-3 mb-8">
            {t.freeFeatures.map((f) => (
              <li key={f} className="flex items-center gap-2 text-sm">
                <CheckCircle2 size={15} className="text-emerald-400 shrink-0" />
                {f}
              </li>
            ))}
          </ul>
          <Link href="/simulate">
            <Button variant="secondary" className="w-full">
              <Play size={14} />
              {t.freeCTA}
            </Button>
          </Link>
        </Card>

        {/* Pro */}
        <Card className="border-[#FFD700]/30 bg-gradient-to-b from-[#FFD700]/[0.04] to-transparent">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-bold">{t.proTitle}</h2>
            <Badge variant="gold">{t.proBadge}</Badge>
          </div>
          <p className="text-sm text-[#94a3b8] mb-6">{t.proDesc}</p>
          <ul className="space-y-3 mb-8">
            {t.proFeatures.map((f) => (
              <li key={f} className="flex items-center gap-2 text-sm">
                <CheckCircle2 size={15} className="text-[#FFD700] shrink-0" />
                {f}
              </li>
            ))}
          </ul>
          <Link href="/pricing">
            <Button className="w-full">
              <ArrowRight size={14} />
              {t.proCTA}
            </Button>
          </Link>
        </Card>
      </div>

      {/* Feature highlights */}
      <div className="grid sm:grid-cols-3 gap-6 mb-10">
        {[
          { icon: <Zap size={22} className="text-[#FFD700]" />, label: "Simulate in 30s", desc: "Paste YAML → instant risk score" },
          { icon: <Shield size={22} className="text-emerald-400" />, label: "N-nine availability", desc: "Math-backed SLA prediction" },
          { icon: <BarChart3 size={22} className="text-blue-400" />, label: "Cascade analysis", desc: "See failure blast radius" },
          { icon: <FileText size={22} className="text-purple-400" />, label: "Audit-ready reports", desc: "PDF export for SOC 2 / DORA" },
          { icon: <Lock size={22} className="text-red-400" />, label: "No data leaves", desc: "YAML processed in memory only" },
          { icon: <CheckCircle2 size={22} className="text-[#FFD700]" />, label: "14-day Pro trial", desc: "No credit card required" },
        ].map((item) => (
          <div key={item.label} className="flex gap-3 p-4 rounded-xl bg-white/[0.02] border border-[#1e293b]">
            <div className="shrink-0 mt-0.5">{item.icon}</div>
            <div>
              <p className="text-sm font-semibold mb-0.5">{item.label}</p>
              <p className="text-xs text-[#64748b]">{item.desc}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Bottom CTA */}
      <div className="text-center">
        <Link href="/pricing" className="text-sm text-[#64748b] hover:text-white transition-colors inline-flex items-center gap-1">
          {t.pricingLink} <ArrowRight size={13} />
        </Link>
      </div>
    </div>
  );
}
