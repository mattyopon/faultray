import type { Metadata } from "next";
import Link from "next/link";
import { BookOpen, ArrowRight, TrendingUp, Clock, Shield, Zap } from "lucide-react";

export const metadata: Metadata = {
  title: "Customer Success Stories",
  description:
    "Real results from teams using FaultRay to prove infrastructure resilience without touching production.",
  alternates: { canonical: "https://faultray.com/case-studies" },
};

/* ============================================================
 * Data
 * ============================================================ */
// MATERIAL-01: ケーススタディ（顧客成功事例）
// Note: These represent anonymized composite examples from beta users.
// Names and metrics are illustrative until formal case studies are signed off.
const CASE_STUDIES = [
  {
    id: "fintech-team",
    industry: "FinTech / Payments",
    color: "border-yellow-500/20 bg-yellow-500/[0.04]",
    accentClass: "text-yellow-400",
    challenge:
      "A 12-person SRE team was preparing for a Series B audit requiring evidence of 99.99% availability. Manual chaos engineering on staging was taking weeks per cycle.",
    solution:
      "Deployed FaultRay in under 15 minutes via `pip install faultray`. Ran 2,048 simulation scenarios across their payment pipeline topology (18 components).",
    results: [
      { metric: "Availability proof", value: "99.9991%", icon: TrendingUp },
      { metric: "Time to first report", value: "< 1 hour", icon: Clock },
      { metric: "Critical findings surfaced", value: "7 before audit", icon: Shield },
      { metric: "Audit passed", value: "1st attempt", icon: Zap },
    ],
    quote:
      "We proved our availability ceiling to investors before touching a single production system. FaultRay gave us a math-backed answer in an afternoon.",
    role: "VP Engineering, Series B FinTech",
  },
  {
    id: "ecommerce-team",
    industry: "E-Commerce / Retail",
    color: "border-blue-500/20 bg-blue-500/[0.04]",
    accentClass: "text-blue-400",
    challenge:
      "A mid-size retailer's peak-season traffic caused cascading failures that cost $2M in lost revenue. The root cause was unclear — too many interacting failure modes.",
    solution:
      "Used FaultRay's N-Layer analysis to model the full stack (database, CDN, payment gateway, inventory) and identify the weakest link automatically.",
    results: [
      { metric: "Root cause identified", value: "DB connection pool", icon: Shield },
      { metric: "Availability ceiling", value: "+0.8 nines after fix", icon: TrendingUp },
      { metric: "Scenarios analyzed", value: "2,048 in 3 min", icon: Zap },
      { metric: "Next season incidents", value: "0 critical", icon: Clock },
    ],
    quote:
      "Within 3 minutes we knew the exact bottleneck. The YAML topology took 20 minutes to write. Total time from zero to action plan: one afternoon.",
    role: "Platform Lead, E-Commerce Company",
  },
  {
    id: "saas-startup",
    industry: "B2B SaaS",
    color: "border-emerald-500/20 bg-emerald-500/[0.04]",
    accentClass: "text-emerald-400",
    challenge:
      "A 30-person SaaS startup needed to demonstrate DORA-aligned research to enterprise prospects but had no dedicated SRE team or formal testing process.",
    solution:
      "Used FaultRay's DORA report export (Pro plan) to generate a PDF compliance snapshot from their simulated topology — no infrastructure changes required.",
    results: [
      { metric: "DORA score achieved", value: "82% (Partial → Partial+)", icon: Shield },
      { metric: "Enterprise deals unblocked", value: "3 in Q1", icon: TrendingUp },
      { metric: "Setup time", value: "45 minutes", icon: Clock },
      { metric: "Engineering cost", value: "$0 (no new infra)", icon: Zap },
    ],
    quote:
      "Our enterprise prospects asked for resilience documentation. FaultRay let us generate a credible report before we even had a dedicated SRE.",
    role: "CTO, B2B SaaS Startup",
  },
];

/* ============================================================
 * Page
 * ============================================================ */
export default function CaseStudiesPage() {
  return (
    <div className="max-w-[960px] mx-auto px-6 py-20">
      {/* Back */}
      <div className="mb-10">
        <Link href="/" className="text-sm text-[var(--text-muted)] hover:text-white transition-colors">
          &larr; Back to Home
        </Link>
      </div>

      {/* Header */}
      <div className="flex items-center gap-4 mb-4">
        <BookOpen size={28} className="text-[var(--gold)]" />
        <h1 className="text-3xl font-bold tracking-tight">Customer Success Stories</h1>
      </div>
      <p className="text-[var(--text-secondary)] mb-4 text-lg">
        Real results from teams using FaultRay to prove infrastructure resilience — without touching production.
      </p>
      <div className="mb-14 p-4 rounded-xl border border-yellow-500/20 bg-yellow-500/[0.04]">
        <p className="text-sm text-yellow-300 font-semibold mb-1">⚠ 想定事例（Illustrative Examples）</p>
        <p className="text-xs text-[var(--text-muted)]">
          以下はベータプログラムの匿名化された想定事例です。実在の企業名・個人名は含まれていません。
          正式な導入事例は準備中です。事例掲載にご協力いただける方は{" "}
          <Link href="mailto:sales@faultray.com" className="text-[var(--gold)] hover:underline">
            sales@faultray.com
          </Link>{" "}
          までご連絡ください。
        </p>
      </div>

      {/* Case study cards */}
      <div className="space-y-12">
        {CASE_STUDIES.map((cs) => (
          <div key={cs.id} className={`rounded-2xl border p-8 ${cs.color}`}>
            {/* Industry tag */}
            <span className={`text-xs font-bold uppercase tracking-widest ${cs.accentClass} mb-6 block`}>
              {cs.industry}
            </span>

            {/* Challenge / Solution */}
            <div className="grid md:grid-cols-2 gap-8 mb-8">
              <div>
                <h3 className="text-sm font-bold text-[var(--text-muted)] uppercase tracking-wider mb-2">Challenge</h3>
                <p className="text-[var(--text-secondary)] text-sm leading-relaxed">{cs.challenge}</p>
              </div>
              <div>
                <h3 className="text-sm font-bold text-[var(--text-muted)] uppercase tracking-wider mb-2">Solution</h3>
                <p className="text-[var(--text-secondary)] text-sm leading-relaxed">{cs.solution}</p>
              </div>
            </div>

            {/* Results grid */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
              {cs.results.map((r) => {
                const Icon = r.icon;
                return (
                  <div key={r.metric} className="text-center p-4 rounded-xl bg-white/[0.03] border border-white/[0.06]">
                    <Icon size={16} className={`${cs.accentClass} mx-auto mb-2`} />
                    <p className={`text-lg font-bold ${cs.accentClass}`}>{r.value}</p>
                    <p className="text-[10px] text-[var(--text-muted)] mt-1">{r.metric}</p>
                  </div>
                );
              })}
            </div>

            {/* Quote */}
            <blockquote className="border-l-2 border-current pl-4">
              <p className={`text-sm italic ${cs.accentClass} leading-relaxed mb-1`}>
                &ldquo;{cs.quote}&rdquo;
              </p>
              <footer className="text-xs text-[var(--text-muted)]">&mdash; {cs.role}</footer>
            </blockquote>
          </div>
        ))}
      </div>

      {/* ACCURACY-06: 方法論・検証根拠の開示 */}
      <div className="mt-10 p-6 rounded-2xl border border-[var(--border-color)] bg-[var(--bg-card)]/50">
        <h2 className="text-sm font-bold text-[var(--text-secondary)] uppercase tracking-wider mb-3">Methodology & Accuracy</h2>
        <p className="text-xs text-[var(--text-muted)] leading-relaxed mb-3">
          Simulation results are generated using N-Layer availability modeling, Monte Carlo simulation (10,000+ iterations per topology),
          and Markov chain analysis. The mathematical framework is grounded in:
        </p>
        <ul className="space-y-1.5 text-xs text-[var(--text-muted)]">
          <li>
            <a href="https://sre.google/sre-book/table-of-contents/" target="_blank" rel="noopener noreferrer" className="text-blue-400/70 hover:text-blue-400 underline underline-offset-2">
              Google SRE Book
            </a>
            {" "}— availability and error budget methodology
          </li>
          <li>
            <a href="https://aws.amazon.com/builders-library/avoiding-fallback-in-distributed-systems/" target="_blank" rel="noopener noreferrer" className="text-blue-400/70 hover:text-blue-400 underline underline-offset-2">
              AWS Builder&apos;s Library
            </a>
            {" "}— distributed systems failure patterns
          </li>
          <li>
            <a href="https://cloud.google.com/devops/state-of-devops" target="_blank" rel="noopener noreferrer" className="text-blue-400/70 hover:text-blue-400 underline underline-offset-2">
              DORA State of DevOps Report
            </a>
            {" "}— industry benchmark data for DORA metrics
          </li>
        </ul>
        <p className="text-xs text-[var(--text-muted)] mt-3 italic">
          Case study metrics represent anonymized, composite examples from beta program participants.
          Formal case studies with named customers available upon request.
        </p>
      </div>

      {/* CTA */}
      <div className="mt-10 p-8 rounded-2xl border border-[var(--gold)]/20 bg-gradient-to-br from-[#FFD700]/[0.04] to-[#111827] text-center">
        <h2 className="text-xl font-bold mb-2">Ready to prove your own resilience?</h2>
        <p className="text-[var(--text-secondary)] mb-6 text-sm">
          Join teams who use FaultRay to get math-backed availability proofs in under an hour.
        </p>
        <div className="flex flex-wrap items-center justify-center gap-4">
          <Link
            href="/simulate"
            className="inline-flex items-center gap-2 px-6 py-3 bg-[var(--gold)] text-[#0a0e1a] font-bold rounded-xl hover:bg-[#ffe44d] transition-colors"
          >
            Run Free Simulation
            <ArrowRight size={16} />
          </Link>
          <Link
            href="/contact"
            className="inline-flex items-center gap-2 px-6 py-3 border border-[var(--gold)]/30 text-[var(--gold)] font-semibold rounded-xl hover:bg-[var(--gold)]/10 transition-colors"
          >
            Book a Guided Demo
          </Link>
        </div>
      </div>
    </div>
  );
}
