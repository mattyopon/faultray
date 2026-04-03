"use client";

import { Card } from "@/components/ui/card";
import {
  HelpCircle,
  Rocket,
  BookOpen,
  LayoutDashboard,
  Zap,
  Network,
  Flame,
  FlaskConical,
  ShieldCheck,
  BarChart3,
  DollarSign,
  Shield,
  AlertOctagon,
  Bot,
  FileText,
  Activity,
  Trophy,
  Terminal,
  MessageCircleQuestion,
  ChevronDown,
} from "lucide-react";
import { useState } from "react";
import { useLocale } from "@/lib/useLocale";
import { appDict } from "@/i18n/app-dict";

function Section({
  icon: Icon,
  title,
  children,
}: {
  icon: React.ComponentType<{ size?: number; className?: string }>;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <Card className="mb-6">
      <div className="flex items-center gap-3 mb-4">
        <Icon size={20} className="text-[var(--gold)]" />
        <h2 className="text-lg font-bold">{title}</h2>
      </div>
      {children}
    </Card>
  );
}

function FeatureItem({
  icon: Icon,
  title,
  description,
}: {
  icon: React.ComponentType<{ size?: number; className?: string }>;
  title: string;
  description: string;
}) {
  return (
    <div className="flex gap-3 p-3 rounded-lg hover:bg-black/5 transition-colors">
      <div className="mt-0.5">
        <Icon size={16} className="text-[var(--gold)]" />
      </div>
      <div>
        <p className="text-sm font-semibold text-[var(--text-primary)] mb-1">{title}</p>
        <p className="text-sm text-[var(--text-secondary)] leading-relaxed">{description}</p>
      </div>
    </div>
  );
}

function FaqItem({ question, answer }: { question: string; answer: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-b border-[var(--border-color)] last:border-b-0">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between py-4 text-left group"
      >
        <span className="text-sm font-medium text-[var(--text-primary)] group-hover:text-[var(--text-primary)] transition-colors pr-4">
          {question}
        </span>
        <ChevronDown
          size={16}
          className={`text-[var(--text-muted)] shrink-0 transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>
      {open && (
        <p className="text-sm text-[var(--text-secondary)] pb-4 leading-relaxed">{answer}</p>
      )}
    </div>
  );
}

export default function HelpPage() {
  const locale = useLocale();
  const t = appDict.help[locale] ?? appDict.help.en;

  return (
    <div className="max-w-[800px] mx-auto px-6 py-10">
      <div className="mb-10">
        <h1 className="text-2xl font-bold mb-1 flex items-center gap-3">
          <HelpCircle size={24} className="text-[var(--gold)]" />
          {t.title}
        </h1>
        <p className="text-[var(--text-secondary)] text-sm">{t.subtitle}</p>
      </div>

      {/* Getting Started */}
      <Section icon={Rocket} title={t.gettingStarted}>
        <div className="space-y-4">
          <div>
            <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-2">{t.whatIsFaultray}</h3>
            <p className="text-sm text-[var(--text-secondary)] leading-relaxed">{t.whatIsFaultrayDesc}</p>
          </div>
          <div className="border-t border-[var(--border-color)] pt-4">
            <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-2">{t.basicUsage}</h3>
            <div className="space-y-2">
              <p className="text-sm text-[var(--text-secondary)]">{t.basicStep1}</p>
              <p className="text-sm text-[var(--text-secondary)]">{t.basicStep2}</p>
              <p className="text-sm text-[var(--text-secondary)]">{t.basicStep3}</p>
            </div>
          </div>
          {/* NAV-DETAIL-09: Pro tips for returning users */}
          {(t as Record<string, string>).proTips && (
            <div className="border-t border-[var(--border-color)] pt-4">
              <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-2">{(t as Record<string, string>).proTips}</h3>
              <div className="space-y-2">
                <p className="text-sm text-[var(--text-secondary)]">{(t as Record<string, string>).proTip1}</p>
                <p className="text-sm text-[var(--text-secondary)]">{(t as Record<string, string>).proTip2}</p>
                <p className="text-sm text-[var(--text-secondary)]">{(t as Record<string, string>).proTip3}</p>
              </div>
            </div>
          )}
        </div>
      </Section>

      {/* Feature Guide */}
      <Section icon={BookOpen} title={t.features}>
        <div className="space-y-1">
          <FeatureItem icon={LayoutDashboard} title={t.dashboardTitle} description={t.dashboardDesc} />
          <FeatureItem icon={Zap} title={t.simulateTitle} description={t.simulateDesc} />
          <FeatureItem icon={Network} title={t.topologyTitle} description={t.topologyDesc} />
          <FeatureItem icon={Flame} title={t.heatmapTitle} description={t.heatmapDesc} />
          <FeatureItem icon={FlaskConical} title={t.whatifTitle} description={t.whatifDesc} />
          <FeatureItem icon={ShieldCheck} title={t.complianceTitle} description={t.complianceDesc} />
          <FeatureItem icon={BarChart3} title={t.scoreDetailTitle} description={t.scoreDetailDesc} />
          <FeatureItem icon={DollarSign} title={t.costTitle} description={t.costDesc} />
          <FeatureItem icon={Shield} title={t.securityTitle} description={t.securityDesc} />
          <FeatureItem icon={AlertOctagon} title={t.fmeaTitle} description={t.fmeaDesc} />
          <FeatureItem icon={Bot} title={t.aiAdvisorTitle} description={t.aiAdvisorDesc} />
          <FeatureItem icon={FileText} title={t.reportsTitle} description={t.reportsDesc} />
          <FeatureItem icon={Activity} title={t.incidentsTitle} description={t.incidentsDesc} />
          <FeatureItem icon={Trophy} title={t.benchmarkTitle} description={t.benchmarkDesc} />
        </div>
      </Section>

      {/* Agent Connect */}
      <Section icon={Terminal} title={t.agentConnect}>
        <p className="text-sm text-[var(--text-secondary)] mb-4">{t.agentConnectDesc}</p>
        <div className="space-y-2">
          <div className="p-3 rounded-lg bg-[var(--bg-secondary)] border border-[var(--border-color)]">
            <code className="text-sm font-mono text-[var(--text-primary)]">{t.agentStep1}</code>
          </div>
          <div className="p-3 rounded-lg bg-[var(--bg-secondary)] border border-[var(--border-color)]">
            <code className="text-sm font-mono text-[var(--text-primary)]">{t.agentStep2}</code>
          </div>
          <div className="p-3 rounded-lg bg-[var(--bg-secondary)] border border-[var(--border-color)]">
            <code className="text-sm font-mono text-[var(--text-primary)]">{t.agentStep3}</code>
          </div>
        </div>
      </Section>

      {/* FAQ */}
      <Section icon={MessageCircleQuestion} title={t.faq}>
        <div>
          <FaqItem question={t.faqQ1} answer={t.faqA1} />
          <FaqItem question={t.faqQ2} answer={t.faqA2} />
          <FaqItem question={t.faqQ3} answer={t.faqA3} />
          {/* SCRIPT-02: 複雑システムへの対応 反論FAQ */}
          {t.faqQ4 && t.faqA4 && (
            <FaqItem question={t.faqQ4} answer={t.faqA4} />
          )}
        </div>
      </Section>

      {/* COMP-03: コミュニティ・教育コンテンツ */}
      <Section icon={Terminal} title={locale === "ja" ? "コミュニティ & リソース" : "Community & Resources"}>
        <div className="space-y-3">
          {[
            {
              href: "https://github.com/mattyopon/faultray/discussions",
              label: locale === "ja" ? "GitHub Discussions — 質問・アイデア共有" : "GitHub Discussions — Q&A and ideas",
              badge: locale === "ja" ? "コミュニティ" : "Community",
            },
            {
              href: "https://github.com/mattyopon/faultray/blob/main/docs/",
              label: locale === "ja" ? "公式ドキュメント — YAML リファレンス・API仕様" : "Official Docs — YAML reference & API spec",
              badge: locale === "ja" ? "ドキュメント" : "Docs",
            },
            {
              href: "https://github.com/mattyopon/faultray/blob/main/CHANGELOG.md",
              label: locale === "ja" ? "リリースノート — 最新の更新内容" : "Changelog — latest updates",
              badge: locale === "ja" ? "更新情報" : "Updates",
            },
            {
              href: "/case-studies",
              label: locale === "ja" ? "導入事例 — チームの成功例" : "Case Studies — real team results",
              badge: locale === "ja" ? "事例" : "Case Studies",
            },
          ].map((item) => (
            <a
              key={item.href}
              href={item.href}
              target={item.href.startsWith("http") ? "_blank" : undefined}
              rel={item.href.startsWith("http") ? "noopener noreferrer" : undefined}
              className="flex items-center justify-between p-3 rounded-lg hover:bg-black/5 transition-colors group"
            >
              <span className="text-sm text-[var(--text-secondary)] group-hover:text-[var(--text-primary)] transition-colors">{item.label}</span>
              <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-[var(--border-color)] text-[var(--text-muted)] group-hover:text-[var(--text-primary)] transition-colors shrink-0 ml-4">
                {item.badge}
              </span>
            </a>
          ))}
        </div>
      </Section>
    </div>
  );
}
