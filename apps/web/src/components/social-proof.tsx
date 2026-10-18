import Link from "next/link";
import { Star, GitFork, ExternalLink, Quote, Download } from "lucide-react";

interface SocialProofDict {
  heading: string;
  githubStars: string;
  betaMessage: string;
  betaSubtitle: string;
  betaCta: string;
  openSource: string;
}

interface SocialProofProps {
  dict: SocialProofDict;
  stars: number;
  pypiDownloads?: number;
}

// Example findings on sample/demo topologies — product capability
// demonstrations, NOT customer testimonials. FaultRay is open source and these
// describe what the tool surfaces on representative inputs, so we present them
// as honest "what you'll find" examples (product voice) rather than fabricated
// customer quotes, which destroy rather than build trust.
const TESTIMONIALS = [
  {
    quote: "On a sample payment-pipeline topology, FaultRay surfaced a single-point-of-failure in the auth service in under 30 seconds — before any production change.",
    author: "Example finding",
    company: "Sample topology · payments",
    metric: "SPOF surfaced in < 30s",
    metricColor: "text-[var(--gold)]",
  },
  {
    quote: "A DORA-aligned evidence pack gives teams a structured starting point for internal resilience design review — work you bring to qualified auditors, not a replacement for them.",
    author: "Example use case",
    company: "Pre-audit preparation",
    metric: "Structured evidence pack",
    metricColor: "text-emerald-400",
  },
  {
    quote: "The N-Layer availability model gives engineers and leadership a shared language for reliability trade-offs in architecture reviews.",
    author: "Example use case",
    company: "Architecture review",
    metric: "Shared reliability language",
    metricColor: "text-blue-400",
  },
];

export function SocialProof({ dict, stars, pypiDownloads }: SocialProofProps) {
  return (
    <section className="py-24 bg-[var(--bg-secondary)] border-t border-[var(--border-color)]">
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
            className="flex flex-col items-center gap-2 p-8 rounded-2xl border border-[var(--border-color)] bg-[var(--bg-card)] min-w-[180px] hover:border-[var(--gold)]/30 hover:bg-[var(--bg-card-hover)] transition-all duration-200 group"
          >
            <div className="flex items-center gap-2 text-[var(--gold)]">
              <Star size={24} className="group-hover:fill-[var(--gold)] transition-all" />
              <span className="text-4xl font-extrabold">{stars}</span>
            </div>
            <span className="text-sm text-[var(--text-muted)]">{dict.githubStars}</span>
          </a>

          {/* Open Source badge */}
          <a
            href="https://github.com/mattyopon/faultray"
            target="_blank"
            rel="noopener noreferrer"
            className="flex flex-col items-center gap-2 p-8 rounded-2xl border border-[var(--border-color)] bg-[var(--bg-card)] min-w-[180px] hover:border-[var(--gold)]/30 hover:bg-[var(--bg-card-hover)] transition-all duration-200"
          >
            <div className="flex items-center gap-2 text-emerald-400">
              <GitFork size={24} />
              <span className="text-4xl font-extrabold">Apache 2.0</span>
            </div>
            <span className="text-sm text-[var(--text-muted)]">{dict.openSource}</span>
          </a>

          {/* PyPI downloads stat (if provided) */}
          {pypiDownloads !== undefined && pypiDownloads > 0 && (
            <a
              href="https://pypi.org/project/faultray/"
              target="_blank"
              rel="noopener noreferrer"
              className="flex flex-col items-center gap-2 p-8 rounded-2xl border border-[var(--border-color)] bg-[var(--bg-card)] min-w-[180px] hover:border-[var(--gold)]/30 hover:bg-[var(--bg-card-hover)] transition-all duration-200"
            >
              <div className="flex items-center gap-2 text-purple-400">
                <Download size={24} />
                <span className="text-4xl font-extrabold">{pypiDownloads.toLocaleString()}</span>
              </div>
              <span className="text-sm text-[var(--text-muted)]">PyPI downloads / month</span>
            </a>
          )}
        </div>

        {/* Testimonials */}
        <div className="grid md:grid-cols-3 gap-6 mb-16">
          {TESTIMONIALS.map((t) => (
            <div
              key={t.company}
              className="flex flex-col p-6 rounded-2xl border border-[var(--border-color)] bg-[var(--bg-card)]"
            >
              <Quote size={20} className="text-[var(--gold)]/40 mb-4 shrink-0" />
              <p className="text-sm text-[var(--text-primary)] leading-relaxed mb-5 flex-1">
                &ldquo;{t.quote}&rdquo;
              </p>
              <div className="mt-auto">
                <div className={`text-xs font-bold ${t.metricColor} mb-3 px-2 py-1 rounded-md bg-white/[0.03] border border-white/[0.05] inline-block`}>
                  {t.metric}
                </div>
                <p className="text-sm font-semibold text-[var(--text-primary)]">{t.author}</p>
                <p className="text-xs text-[var(--text-muted)]">{t.company}</p>
              </div>
            </div>
          ))}
        </div>

        {/* Beta feedback CTA */}
        <div className="max-w-[640px] mx-auto text-center p-8 rounded-2xl border border-[var(--gold)]/20 bg-gradient-to-br from-[var(--gold)]/[0.04] to-[var(--bg-card)]">
          <p className="text-lg font-semibold text-[var(--text-primary)] mb-2">{dict.betaMessage}</p>
          <p className="text-[var(--text-secondary)] mb-6 text-sm">
            {dict.betaSubtitle}
          </p>
          <Link
            href="/contact"
            className="inline-flex items-center gap-2 px-6 py-3 bg-[var(--gold)]/10 border border-[var(--gold)]/30 text-[var(--gold)] font-semibold rounded-xl hover:bg-[var(--gold)]/20 hover:border-[var(--gold)]/50 transition-all"
          >
            <ExternalLink size={16} />
            {dict.betaCta}
          </Link>
        </div>
      </div>
    </section>
  );
}
