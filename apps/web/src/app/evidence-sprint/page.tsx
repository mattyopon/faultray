"use client";

import Link from "next/link";
import { Logo } from "@/components/logo";
import { useLocale } from "@/lib/useLocale";
import { appDict } from "@/i18n/app-dict";
import {
  Shield,
  ShieldCheck,
  FileCheck,
  Check,
  Lock,
  ExternalLink,
  ListChecks,
  CalendarClock,
  FileText,
} from "lucide-react";

// Content lives in the 8-locale app dictionary (src/i18n/app-dict.ts) under
// `appDict.evidenceSprint`, consumed below via `appDict.evidenceSprint[locale]
// ?? appDict.evidenceSprint.en` — the repo's standard dictionary-backed page
// pattern (see env-compare / bus-factor / simulate). Real EN + JA copy; the
// other six locales fall back to English, exactly like the #180 hero keys.
export default function EvidenceSprintPage() {
  const locale = useLocale();
  // Route copy through the 8-locale app dictionary (same mechanism as the rest
  // of the site); non-EN/JA locales fall back to English via `?? .en`, matching
  // the #180 hero keys. No inline JA/EN ternary keeps the i18n ratchet green.
  const t = appDict.evidenceSprint[locale] ?? appDict.evidenceSprint.en;
  const homeHref = `/${locale}`;

  return (
    <div className="min-h-screen text-white">
      {/* Nav */}
      <nav className="sticky top-0 z-50 border-b border-[var(--border-color)]/95 backdrop-blur-sm">
        <div className="w-full px-6 h-16 flex items-center justify-between">
          <Link href={homeHref} className="flex items-center gap-2 font-bold">
            <Logo size={24} />
            FaultRay
          </Link>
          <div className="flex items-center gap-4">
            <Link
              href={`${homeHref}#pricing`}
              className="text-sm text-[var(--text-secondary)] hover:text-white transition-colors"
            >
              {t.nav.pricing}
            </Link>
            <Link
              href="/contact"
              className="inline-flex items-center gap-2 px-4 py-2 bg-[var(--gold)] text-[#0a0e1a] font-semibold rounded-xl text-sm hover:bg-[#ffe44d] transition-all"
            >
              <ExternalLink size={14} />
              {t.nav.contact}
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <section className="py-20 text-center">
        <div className="max-w-[820px] mx-auto px-6">
          <div className="inline-block px-4 py-1.5 text-[0.8125rem] font-medium text-[var(--gold)] border border-[var(--gold)]/25 rounded-full bg-[var(--gold)]/5 mb-6">
            {t.hero.eyebrow}
          </div>
          <h1 className="text-[clamp(2rem,5vw,3.5rem)] font-extrabold tracking-tight mb-4">
            {t.hero.headline}
          </h1>
          <p className="text-lg text-[var(--text-secondary)] leading-relaxed mb-6">
            {t.hero.subhead}
          </p>
          <div className="flex items-center justify-center gap-2 text-sm text-[var(--text-muted)] mb-8">
            <ShieldCheck size={15} className="text-[var(--gold)] shrink-0" />
            <span>{t.hero.priceNote}</span>
          </div>
          <div className="flex gap-4 justify-center flex-wrap">
            <Link
              href="/contact"
              className="inline-flex items-center gap-2 px-7 py-3 bg-[var(--gold)] text-[#0a0e1a] font-semibold rounded-xl hover:bg-[#ffe44d] shadow-[0_0_20px_rgba(255,215,0,0.2)] hover:shadow-[0_0_30px_rgba(255,215,0,0.35)] transition-all"
            >
              <ExternalLink size={16} />
              {t.hero.ctaLabel}
            </Link>
            <Link
              href="#how-it-works"
              className="inline-flex items-center gap-2 px-7 py-3 border border-[var(--border-color)] text-white rounded-xl hover:border-[#64748b] hover:bg-white/[0.03] transition-all"
            >
              {t.hero.seeHow}
            </Link>
          </div>
        </div>
      </section>

      {/* What you get */}
      <section className="py-16 border-t border-[var(--border-color)]">
        <div className="max-w-[980px] mx-auto px-6">
          <div className="text-center mb-10">
            <h2 className="text-2xl font-bold mb-2">{t.offer.heading}</h2>
            <p className="text-[var(--text-secondary)] max-w-[640px] mx-auto">
              {t.offer.subheading}
            </p>
          </div>
          <div className="grid md:grid-cols-2 gap-3">
            {t.offer.deliverables.map((d) => (
              <div
                key={d}
                className="flex items-start gap-3 p-4 rounded-xl border border-[var(--border-color)] bg-[var(--bg-card)]"
              >
                <FileCheck size={18} className="text-[var(--gold)] mt-0.5 shrink-0" />
                <span className="text-[0.9375rem] text-[var(--text-secondary)] leading-relaxed">{d}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* DORA article coverage */}
      <section className="py-16 border-t border-[var(--gold)]/15">
        <div className="max-w-[980px] mx-auto px-6">
          <div className="text-center mb-8">
            <h2 className="text-2xl font-bold mb-2">{t.mappingTable.heading}</h2>
            <p className="text-sm text-[var(--text-muted)] max-w-[640px] mx-auto">{t.mappingTable.note}</p>
          </div>
          <div className="overflow-x-auto rounded-2xl border border-[var(--border-color)]">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr>
                  <th scope="col" className="px-5 py-4 text-left bg-[var(--bg-tertiary)] text-[var(--text-secondary)] font-semibold whitespace-nowrap">{t.mappingTable.colArticle}</th>
                  <th scope="col" className="px-5 py-4 text-left bg-[var(--bg-tertiary)] text-[var(--text-secondary)] font-semibold">{t.mappingTable.colTopic}</th>
                  <th scope="col" className="px-5 py-4 text-left bg-[var(--bg-tertiary)] text-[var(--text-secondary)] font-semibold">{t.mappingTable.colEvidence}</th>
                </tr>
              </thead>
              <tbody>
                {t.mappingTable.rows.map((row, i) => (
                  <tr key={row.article} className={i < t.mappingTable.rows.length - 1 ? "border-b border-[var(--border-color)]" : ""}>
                    <td className="px-5 py-4 font-semibold text-[var(--gold)] bg-[var(--bg-card)] whitespace-nowrap align-top">{row.article}</td>
                    <td className="px-5 py-4 text-[var(--text-primary)] bg-[var(--bg-card)] align-top">{row.topic}</td>
                    <td className="px-5 py-4 text-[var(--text-secondary)] bg-[var(--bg-card)] align-top">{row.evidence}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* How it works */}
      <section id="how-it-works" className="scroll-mt-20 py-16 border-t border-[var(--border-color)]">
        <div className="max-w-[980px] mx-auto px-6">
          <h2 className="text-2xl font-bold text-center mb-10">{t.howItWorks.heading}</h2>
          <div className="grid md:grid-cols-4 gap-5 mb-8">
            {t.howItWorks.steps.map((s, i) => (
              <div key={s.title} className="p-6 rounded-2xl border border-[var(--border-color)] bg-[var(--bg-card)]">
                <div className="w-10 h-10 flex items-center justify-center rounded-xl bg-[var(--gold)]/[0.06] border border-[var(--gold)]/10 mb-4">
                  <CalendarClock size={18} className="text-[var(--gold)]" />
                </div>
                <div className="text-xs font-semibold text-[var(--text-muted)] mb-1">Step {i + 1}</div>
                <h3 className="text-base font-bold mb-2">{s.title}</h3>
                <p className="text-sm text-[var(--text-secondary)] leading-relaxed">{s.desc}</p>
              </div>
            ))}
          </div>
          <div className="flex items-start gap-3 p-4 rounded-xl border border-emerald-500/20 bg-emerald-500/[0.04] max-w-[720px] mx-auto">
            <Lock size={18} className="text-emerald-400 mt-0.5 shrink-0" />
            <p className="text-sm text-emerald-300 leading-relaxed">{t.howItWorks.dataNote}</p>
          </div>
        </div>
      </section>

      {/* What we need from you + Pricing */}
      <section className="py-16 border-t border-[var(--border-color)]">
        <div className="max-w-[980px] mx-auto px-6 grid md:grid-cols-2 gap-8">
          <div>
            <div className="flex items-center gap-2 mb-5">
              <ListChecks size={20} className="text-[var(--gold)]" />
              <h2 className="text-xl font-bold">{t.needFromYou.heading}</h2>
            </div>
            <ul className="space-y-3">
              {t.needFromYou.items.map((item) => (
                <li key={item} className="flex items-start gap-2.5 text-[0.9375rem] text-[var(--text-secondary)]">
                  <Check size={16} className="text-emerald-400 mt-0.5 shrink-0" />
                  {item}
                </li>
              ))}
            </ul>
          </div>
          <div className="p-8 rounded-2xl border border-[var(--gold)]/25 bg-[var(--gold)]/[0.04]">
            <h2 className="text-xl font-bold mb-3">{t.pricing.heading}</h2>
            <div className="flex items-baseline gap-2 mb-5">
              <span className="text-4xl font-extrabold tracking-tight text-[var(--gold)]">{t.pricing.price}</span>
              <span className="text-sm text-[var(--text-muted)]">{t.pricing.priceUnit}</span>
            </div>
            <ul className="space-y-3">
              {t.pricing.terms.map((term) => (
                <li key={term} className="flex items-start gap-2.5 text-sm text-[var(--text-secondary)]">
                  <ShieldCheck size={16} className="text-[var(--gold)] mt-0.5 shrink-0" />
                  {term}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      {/* FAQ */}
      <section className="py-16 border-t border-[var(--border-color)]">
        <div className="max-w-[820px] mx-auto px-6">
          <h2 className="text-2xl font-bold text-center mb-10">{t.faq.heading}</h2>
          <div className="space-y-4">
            {t.faq.items.map((item) => (
              <div key={item.q} className="p-6 rounded-2xl border border-[var(--border-color)] bg-[var(--bg-card)]">
                <div className="flex items-start gap-3 mb-2">
                  <FileText size={18} className="text-[var(--gold)] mt-0.5 shrink-0" />
                  <h3 className="text-base font-bold">{item.q}</h3>
                </div>
                <p className="text-[0.9375rem] text-[var(--text-secondary)] leading-relaxed pl-[30px]">{item.a}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Closing CTA */}
      <section className="py-20 text-center border-t border-[var(--gold)]/15">
        <div className="max-w-[640px] mx-auto px-6">
          <h2 className="text-2xl font-bold mb-4">{t.closing.heading}</h2>
          <p className="text-[var(--text-secondary)] mb-8 leading-relaxed">{t.closing.subhead}</p>
          <Link
            href="/contact"
            className="inline-flex items-center gap-2 px-7 py-3 bg-[var(--gold)] text-[#0a0e1a] font-semibold rounded-xl hover:bg-[#ffe44d] shadow-[0_0_20px_rgba(255,215,0,0.2)] hover:shadow-[0_0_30px_rgba(255,215,0,0.35)] transition-all"
          >
            <ExternalLink size={16} />
            {t.closing.ctaLabel}
          </Link>
        </div>
      </section>

      {/* Disclaimer + footer */}
      <footer className="py-8 border-t border-[var(--border-color)]">
        <div className="max-w-[820px] mx-auto px-6 text-center">
          <div className="flex items-start gap-2.5 justify-center mb-4 text-xs text-[var(--text-muted)] leading-relaxed">
            <Shield size={14} className="mt-0.5 shrink-0" />
            <p className="max-w-[640px]">{t.disclaimer}</p>
          </div>
          <p className="text-sm text-[var(--text-muted)]">
            <Link href={homeHref} className="hover:text-white transition-colors">FaultRay</Link>
            {" · "}
            <Link href="/pricing" className="hover:text-white transition-colors">{t.nav.pricing}</Link>
            {" · "}
            <Link href="/contact" className="hover:text-white transition-colors">{t.nav.contact}</Link>
          </p>
        </div>
      </footer>
    </div>
  );
}
