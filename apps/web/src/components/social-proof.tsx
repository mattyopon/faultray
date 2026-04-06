import Link from "next/link";
import { Star, GitFork, ExternalLink, Download } from "lucide-react";

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
  pypiDownloads?: number;
}

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
              <span className="text-4xl font-extrabold">BSL 1.1</span>
            </div>
            <span className="text-sm text-[var(--text-muted)]">{dict.openSource}</span>
          </a>

          {/* PyPI Downloads */}
          {pypiDownloads != null && pypiDownloads > 0 && (
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
              <span className="text-sm text-[var(--text-muted)]">PyPI Downloads</span>
            </a>
          )}
        </div>

        {/* Beta feedback CTA */}
        <div className="max-w-[640px] mx-auto text-center p-8 rounded-2xl border border-[var(--gold)]/20 bg-gradient-to-br from-[var(--gold)]/[0.04] to-[var(--bg-card)]">
          <p className="text-lg font-semibold text-[var(--text-primary)] mb-2">{dict.betaMessage}</p>
          <p className="text-[var(--text-secondary)] mb-6 text-sm">
            現在アーリーアクセス段階です。ご意見・ご要望をお寄せいただけると大変助かります。
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
