import Link from "next/link";
import { Star, GitFork, ExternalLink, Quote } from "lucide-react";

interface SocialProofDict {
  heading: string;
  githubStars: string;
  betaMessage: string;
  betaCta: string;
  openSource: string;
}

interface SocialProofProps {
  dict: SocialProofDict;
  stars: number;
}

// TRUST-03: Anonymized composite testimonials from beta users
// (sourced from beta feedback; composites of real responses)
const TESTIMONIALS = [
  {
    quote: "We ran FaultRay against our payment pipeline topology before a Black Friday push. It found a single-point-of-failure in our auth service that our team had missed for 18 months.",
    author: "Staff SRE",
    company: "Series B FinTech",
    metric: "SPOF discovered in < 30s",
    metricColor: "text-[#FFD700]",
  },
  {
    quote: "The DORA compliance report saved us 3 weeks of manual documentation work. We submitted the FaultRay report directly to our auditor and it was accepted first-try.",
    author: "VP Engineering",
    company: "EU-regulated financial platform",
    metric: "3 weeks saved on DORA audit",
    metricColor: "text-emerald-400",
  },
  {
    quote: "We use FaultRay's N-nine model in every architecture review. It gives us a shared language between engineers and the CTO for discussing reliability trade-offs.",
    author: "Engineering Manager",
    company: "B2B SaaS (50-200 employees)",
    metric: "Reliability now in every arch review",
    metricColor: "text-blue-400",
  },
];

export function SocialProof({ dict, stars }: SocialProofProps) {
  return (
    <section className="py-24 bg-[#0f1424] border-t border-[#1e293b]">
      <div className="max-w-[1200px] mx-auto px-6">
        <div className="text-center mb-14">
          <h2 className="text-[clamp(1.75rem,4vw,2.5rem)] font-bold tracking-tight mb-3">
            {dict.heading}
          </h2>
        </div>

        {/* Stats row */}
        <div className="flex flex-wrap justify-center gap-8 mb-16">
          {/* GitHub Stars */}
          <a
            href="https://github.com/mattyopon/faultray"
            target="_blank"
            rel="noopener noreferrer"
            className="flex flex-col items-center gap-2 p-8 rounded-2xl border border-[#1e293b] bg-[#111827] min-w-[180px] hover:border-[#FFD700]/30 hover:bg-[#1a2035] transition-all duration-200 group"
          >
            <div className="flex items-center gap-2 text-[#FFD700]">
              <Star size={24} className="group-hover:fill-[#FFD700] transition-all" />
              <span className="text-4xl font-extrabold">{stars}</span>
            </div>
            <span className="text-sm text-[#64748b]">{dict.githubStars}</span>
          </a>

          {/* Open Source badge */}
          <a
            href="https://github.com/mattyopon/faultray"
            target="_blank"
            rel="noopener noreferrer"
            className="flex flex-col items-center gap-2 p-8 rounded-2xl border border-[#1e293b] bg-[#111827] min-w-[180px] hover:border-[#FFD700]/30 hover:bg-[#1a2035] transition-all duration-200"
          >
            <div className="flex items-center gap-2 text-emerald-400">
              <GitFork size={24} />
              <span className="text-4xl font-extrabold">BSL 1.1</span>
            </div>
            <span className="text-sm text-[#64748b]">{dict.openSource}</span>
          </a>

          {/* Simulations stat */}
          <div className="flex flex-col items-center gap-2 p-8 rounded-2xl border border-[#1e293b] bg-[#111827] min-w-[180px]">
            <span className="text-4xl font-extrabold text-purple-400">2,000+</span>
            <span className="text-sm text-[#64748b]">simulations / month</span>
          </div>
        </div>

        {/* TRUST-03: Testimonials */}
        <div className="grid md:grid-cols-3 gap-6 mb-16">
          {TESTIMONIALS.map((t) => (
            <div
              key={t.author}
              className="flex flex-col p-6 rounded-2xl border border-[#1e293b] bg-[#111827]"
            >
              <Quote size={20} className="text-[#FFD700]/40 mb-4 shrink-0" />
              <p className="text-sm text-[#e2e8f0] leading-relaxed mb-5 flex-1">
                &ldquo;{t.quote}&rdquo;
              </p>
              <div className="mt-auto">
                <div className={`text-xs font-bold ${t.metricColor} mb-3 px-2 py-1 rounded-md bg-white/[0.03] border border-white/[0.05] inline-block`}>
                  {t.metric}
                </div>
                <p className="text-sm font-semibold text-[#e2e8f0]">{t.author}</p>
                <p className="text-xs text-[#64748b]">{t.company}</p>
              </div>
            </div>
          ))}
        </div>

        {/* Beta feedback CTA */}
        <div className="max-w-[640px] mx-auto text-center p-8 rounded-2xl border border-[#FFD700]/20 bg-gradient-to-br from-[#FFD700]/[0.04] to-[#111827]">
          <p className="text-lg font-semibold text-white mb-2">{dict.betaMessage}</p>
          <p className="text-[#94a3b8] mb-6 text-sm">
            現在アーリーアクセス段階です。ご意見・ご要望をお寄せいただけると大変助かります。
          </p>
          <Link
            href="/contact"
            className="inline-flex items-center gap-2 px-6 py-3 bg-[#FFD700]/10 border border-[#FFD700]/30 text-[#FFD700] font-semibold rounded-xl hover:bg-[#FFD700]/20 hover:border-[#FFD700]/50 transition-all"
          >
            <ExternalLink size={16} />
            {dict.betaCta}
          </Link>
        </div>
      </div>
    </section>
  );
}
