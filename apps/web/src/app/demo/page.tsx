"use client";

/**
 * DEMO-01 fix: Replace bare redirect with a real demo landing page.
 * DEMO-02 fix: Show Free vs Pro feature distinction to drive upgrades.
 */

import Link from "next/link";
import { useState } from "react";
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
  Building2,
  Info,
} from "lucide-react";

// DEMO-01: Industry templates for one-click demo
const INDUSTRY_TEMPLATES = {
  saas:       { scenario: "web-saas",     score: 82.5, nines: "99.97%", critical: 3, warning: 7 },
  ec:         { scenario: "web-saas",     score: 76.3, nines: "99.95%", critical: 5, warning: 9 },
  finance:    { scenario: "microservice", score: 88.1, nines: "99.99%", critical: 2, warning: 4 },
  healthcare: { scenario: "microservice", score: 71.8, nines: "99.93%", critical: 6, warning: 11 },
  media:      { scenario: "web-saas",     score: 79.4, nines: "99.96%", critical: 4, warning: 8 },
} as const;

type IndustryKey = keyof typeof INDUSTRY_TEMPLATES;

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
    selectIndustry: "Select your industry",
    industries: [
      { key: "saas" as IndustryKey,       label: "SaaS" },
      { key: "ec" as IndustryKey,         label: "E-commerce" },
      { key: "finance" as IndustryKey,    label: "Finance" },
      { key: "healthcare" as IndustryKey, label: "Healthcare" },
      { key: "media" as IndustryKey,      label: "Media" },
    ],
    oneClickCTA: "Try with one click",
    oneClickDesc: "Run a simulation with a pre-built template for your industry",
    previewTitle: "Sample Result Preview",
    previewBanner: "This is sample data. Run your own simulation for real results.",
    previewScore: "Resilience Score",
    previewAvailability: "Availability",
    previewCritical: "Critical Issues",
    previewWarning: "Warnings",
    previewCTA: "Run real simulation →",
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
    selectIndustry: "業種を選択",
    industries: [
      { key: "saas" as IndustryKey,       label: "SaaS" },
      { key: "ec" as IndustryKey,         label: "EC・小売" },
      { key: "finance" as IndustryKey,    label: "金融" },
      { key: "healthcare" as IndustryKey, label: "ヘルスケア" },
      { key: "media" as IndustryKey,      label: "メディア" },
    ],
    oneClickCTA: "ワンクリックで試す",
    oneClickDesc: "業種に合わせたテンプレートでシミュレーションを即実行",
    previewTitle: "サンプル結果プレビュー",
    previewBanner: "これはサンプルデータです。実際の結果を得るにはシミュレーションを実行してください。",
    previewScore: "レジリエンススコア",
    previewAvailability: "可用性",
    previewCritical: "重大な問題",
    previewWarning: "警告",
    previewCTA: "実際のシミュレーションを実行 →",
  },
} as const;

// DEMO-01: Score ring for result preview
function PreviewScoreRing({ score }: { score: number }) {
  const radius = 40;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (score / 100) * circumference;
  const color = score >= 90 ? "#10B981" : score >= 70 ? "#FFD700" : "#ef4444";
  return (
    <div className="relative" style={{ width: 96, height: 96 }}>
      <svg viewBox="0 0 100 100" className="transform -rotate-90" style={{ width: 96, height: 96 }} aria-hidden="true">
        <circle cx="50" cy="50" r={radius} stroke="#1e293b" strokeWidth="7" fill="none" />
        <circle cx="50" cy="50" r={radius} stroke={color} strokeWidth="7" fill="none" strokeLinecap="round" strokeDasharray={circumference} strokeDashoffset={offset} className="transition-all duration-700" />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-xl font-extrabold" style={{ color }}>{score.toFixed(1)}</span>
      </div>
    </div>
  );
}

export default function DemoPage() {
  const rawLocale = useLocale();
  const locale = rawLocale in T ? (rawLocale as keyof typeof T) : "en";
  const t = T[locale];
  const [selectedIndustry, setSelectedIndustry] = useState<IndustryKey | null>(null);
  const preview = selectedIndustry ? INDUSTRY_TEMPLATES[selectedIndustry] : null;

  return (
    <div className="max-w-5xl mx-auto px-6 py-12">
      {/* PAGE-01: 営業デモ向けショートカットバナー */}
      <div className="mb-8 p-4 rounded-xl border border-[var(--border-color)] bg-[var(--bg-secondary)] flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-xs text-[var(--text-muted)]">
          <BarChart3 size={14} className="text-[var(--gold)]" />
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
              className="text-xs font-medium px-3 py-1.5 rounded-lg border border-[var(--border-color)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:border-[var(--border-color)] transition-colors"
            >
              {link.label}
            </Link>
          ))}
        </div>
      </div>

      {/* Hero */}
      <div className="text-center mb-12">
        <div className="inline-flex items-center gap-2 bg-[var(--gold)]/10 border border-[var(--gold)]/20 rounded-full px-4 py-1.5 mb-5">
          <Play size={14} className="text-[var(--gold)]" />
          <span className="text-xs font-semibold text-[var(--gold)] uppercase tracking-wide">Live Demo</span>
        </div>
        <h1 className="text-4xl font-bold mb-4 leading-tight">{t.headline}</h1>
        <p className="text-[var(--text-secondary)] text-lg max-w-2xl mx-auto">{t.sub}</p>
      </div>

      {/* Quick scenario cards */}
      <div className="mb-12">
        <p className="text-sm font-semibold text-[var(--text-muted)] uppercase tracking-wide mb-4">
          {t.demoScenarios}
        </p>
        <div className="grid sm:grid-cols-3 gap-4">
          {t.scenarios.map((s) => (
            <Link key={s.id} href={`/simulate?sample=${s.id}`}>
              <Card className="hover:border-[var(--gold)]/40 transition-colors cursor-pointer h-full">
                <div className="flex items-start gap-3">
                  <div className="p-2 rounded-lg bg-[var(--gold)]/10">
                    <Zap size={16} className="text-[var(--gold)]" />
                  </div>
                  <div>
                    <p className="font-semibold text-sm mb-1">{s.label}</p>
                    <p className="text-xs text-[var(--text-muted)]">{s.desc}</p>
                  </div>
                </div>
              </Card>
            </Link>
          ))}
        </div>
      </div>

      {/* DEMO-01: Industry selection + one-click demo */}
      <div className="mb-12">
        <div className="flex items-center gap-2 mb-4">
          <Building2 size={16} className="text-[var(--gold)]" />
          <p className="text-sm font-semibold text-[var(--text-muted)] uppercase tracking-wide">
            {t.selectIndustry}
          </p>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-6">
          {t.industries.map((ind) => (
            <button
              key={ind.key}
              onClick={() => setSelectedIndustry(ind.key)}
              className={`px-4 py-3 rounded-xl border text-sm font-medium transition-all ${
                selectedIndustry === ind.key
                  ? "border-[var(--gold)] bg-[var(--gold)]/10 text-[var(--gold)]"
                  : "border-[var(--border-color)] text-[var(--text-secondary)] hover:border-[var(--border-color)] hover:text-[var(--text-primary)]"
              }`}
            >
              {ind.label}
            </button>
          ))}
        </div>

        {/* One-click CTA */}
        {selectedIndustry && preview && (
          <div className="mb-6">
            <Link href={`/simulate?sample=${preview.scenario}`}>
              <Button size="lg" className="w-full sm:w-auto">
                <Play size={16} />
                {t.oneClickCTA}
              </Button>
            </Link>
            <p className="text-xs text-[var(--text-muted)] mt-2">{t.oneClickDesc}</p>
          </div>
        )}

        {/* DEMO-01 + DEMO-05: Sample result preview (always visible with default) */}
        {(() => {
          const displayPreview = preview ?? INDUSTRY_TEMPLATES.saas;
          return (
          <Card id="sample-result" className="border-blue-500/20 bg-blue-500/[0.02]">
            <div className="flex items-center gap-2 mb-4">
              <Info size={14} className="text-blue-400" />
              <Badge variant="default" className="bg-blue-500/10 text-blue-400 border-blue-500/20">
                {locale === "ja" ? "サンプルデータ" : "SAMPLE DATA"}
              </Badge>
              <span className="text-xs text-[var(--text-secondary)]">{t.previewBanner}</span>
            </div>
            <p className="text-base font-bold mb-4">{t.previewTitle}</p>
            <div className="flex flex-col sm:flex-row items-center gap-6">
              <PreviewScoreRing score={displayPreview.score} />
              <div className="grid grid-cols-2 gap-4 flex-1">
                <div className="p-3 rounded-lg bg-black/5 border border-[var(--border-color)]">
                  <p className="text-xs text-[var(--text-muted)] mb-1">{t.previewScore}</p>
                  <p className="text-xl font-bold font-mono" style={{ color: displayPreview.score >= 90 ? "#10B981" : displayPreview.score >= 70 ? "#FFD700" : "#ef4444" }}>
                    {displayPreview.score}
                  </p>
                </div>
                <div className="p-3 rounded-lg bg-black/5 border border-[var(--border-color)]">
                  <p className="text-xs text-[var(--text-muted)] mb-1">{t.previewAvailability}</p>
                  <p className="text-xl font-bold font-mono text-emerald-400">{displayPreview.nines}</p>
                </div>
                <div className="p-3 rounded-lg bg-black/5 border border-[var(--border-color)]">
                  <p className="text-xs text-[var(--text-muted)] mb-1">{t.previewCritical}</p>
                  <p className="text-xl font-bold font-mono text-red-400">{displayPreview.critical}</p>
                </div>
                <div className="p-3 rounded-lg bg-black/5 border border-[var(--border-color)]">
                  <p className="text-xs text-[var(--text-muted)] mb-1">{t.previewWarning}</p>
                  <p className="text-xl font-bold font-mono text-orange-400">{displayPreview.warning}</p>
                </div>
              </div>
            </div>
            <div className="mt-4 text-right">
              <Link href={`/simulate?sample=${displayPreview.scenario}`} className="text-sm font-semibold text-[var(--gold)] hover:underline inline-flex items-center gap-1">
                {t.previewCTA} <ArrowRight size={14} />
              </Link>
            </div>
          </Card>
          );
        })()}
      </div>

      {/* COMP-04: Self-guided tour — step by step */}
      <div className="mb-12">
        <div className="text-center mb-8">
          <h2 className="text-xl font-bold mb-2">
            {locale === "ja" ? "セルフガイドツアー" : "Self-Guided Tour"}
          </h2>
          <p className="text-sm text-[var(--text-secondary)]">
            {locale === "ja"
              ? "4ステップでFaultRayの全体像を体験できます。ログイン不要。"
              : "Experience FaultRay in 4 steps. No login required."}
          </p>
        </div>
        <div className="grid md:grid-cols-4 gap-4">
          {[
            {
              step: 1,
              icon: <Zap size={20} className="text-[var(--gold)]" />,
              title: locale === "ja" ? "インフラ構成を選択" : "Choose Topology",
              desc: locale === "ja"
                ? "SaaS・マイクロサービス・MLパイプラインから選択、またはYAMLを貼り付け"
                : "Pick SaaS, microservices, or ML pipeline — or paste your own YAML",
              cta: locale === "ja" ? "上のシナリオから選択 ↑" : "Pick a scenario above ↑",
              href: null,
            },
            {
              step: 2,
              icon: <Play size={20} className="text-emerald-400" />,
              title: locale === "ja" ? "シミュレーション実行" : "Run Simulation",
              desc: locale === "ja"
                ? "2,000以上の障害シナリオを30秒で実行。本番環境には一切触れません"
                : "2,000+ failure scenarios in 30 seconds. Zero production impact",
              cta: locale === "ja" ? "下のプレビューで確認 ↓" : "See preview below ↓",
              href: "#sample-result",
            },
            {
              step: 3,
              icon: <BarChart3 size={20} className="text-blue-400" />,
              title: locale === "ja" ? "リスクスコア確認" : "Review Risk Score",
              desc: locale === "ja"
                ? "N-Layer可用性モデルで稼働率の上限を数学的に算出。重大な弱点をハイライト"
                : "N-Layer model calculates availability ceiling. Critical weaknesses highlighted",
              cta: locale === "ja" ? "業種を選んでプレビュー ↑" : "Select industry above ↑",
              href: null,
            },
            {
              step: 4,
              icon: <ArrowRight size={20} className="text-purple-400" />,
              title: locale === "ja" ? "無料で始める" : "Get Started Free",
              desc: locale === "ja"
                ? "アカウント作成で月5回まで無料。クレカ不要、14日間Proトライアル付き"
                : "Free account: 5 simulations/month. No credit card. 14-day Pro trial included",
              cta: locale === "ja" ? "無料で始める" : "Sign up free",
              href: "/login",
            },
          ].map((item) => (
            <div key={item.step} className="relative p-5 rounded-2xl border border-[var(--border-color)] bg-[var(--bg-card)]">
              <div className="flex items-center gap-2 mb-3">
                <span className="w-6 h-6 flex items-center justify-center rounded-full bg-[var(--gold)]/10 text-[var(--gold)] text-xs font-bold">
                  {item.step}
                </span>
                {item.icon}
              </div>
              <h3 className="font-semibold text-sm mb-1">{item.title}</h3>
              <p className="text-xs text-[var(--text-muted)] mb-3 leading-relaxed">{item.desc}</p>
              {item.href ? (
                <Link
                  href={item.href}
                  className="text-xs font-semibold text-[var(--gold)] hover:underline inline-flex items-center gap-1"
                >
                  {item.cta} <ArrowRight size={12} />
                </Link>
              ) : (
                <span className="text-xs font-medium text-[var(--text-muted)]">{item.cta}</span>
              )}
            </div>
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
          <p className="text-sm text-[var(--text-secondary)] mb-6">{t.freeDesc}</p>
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
        <Card className="border-[var(--gold)]/30 bg-gradient-to-b from-[var(--gold)]/[0.04] to-transparent">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-bold">{t.proTitle}</h2>
            <Badge variant="gold">{t.proBadge}</Badge>
          </div>
          <p className="text-sm text-[var(--text-secondary)] mb-6">{t.proDesc}</p>
          <ul className="space-y-3 mb-8">
            {t.proFeatures.map((f) => (
              <li key={f} className="flex items-center gap-2 text-sm">
                <CheckCircle2 size={15} className="text-[var(--gold)] shrink-0" />
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
          { icon: <Zap size={22} className="text-[var(--gold)]" />, label: "Simulate in 30s", desc: "Paste YAML → instant risk score" },
          { icon: <Shield size={22} className="text-emerald-400" />, label: "N-nine availability", desc: "Math-backed SLA prediction" },
          { icon: <BarChart3 size={22} className="text-blue-400" />, label: "Cascade analysis", desc: "See failure blast radius" },
          { icon: <FileText size={22} className="text-purple-400" />, label: "Research-draft reports", desc: "PDF export for SOC 2 / DORA" },
          { icon: <Lock size={22} className="text-red-400" />, label: "No data leaves", desc: "YAML processed in memory only" },
          { icon: <CheckCircle2 size={22} className="text-[var(--gold)]" />, label: "14-day Pro trial", desc: "No credit card required" },
        ].map((item) => (
          <div key={item.label} className="flex gap-3 p-4 rounded-xl bg-black/5 border border-[var(--border-color)]">
            <div className="shrink-0 mt-0.5">{item.icon}</div>
            <div>
              <p className="text-sm font-semibold mb-0.5">{item.label}</p>
              <p className="text-xs text-[var(--text-muted)]">{item.desc}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Bottom CTA */}
      <div className="text-center">
        <Link href="/pricing" className="text-sm text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors inline-flex items-center gap-1">
          {t.pricingLink} <ArrowRight size={13} />
        </Link>
      </div>
    </div>
  );
}
