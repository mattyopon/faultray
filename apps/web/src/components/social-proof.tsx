import Link from "next/link";
import { Star, GitFork, ExternalLink } from "lucide-react";

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
