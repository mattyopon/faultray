import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Changelog",
  description: "FaultRay product updates, new features, and improvements.",
  robots: { index: false },
};

interface Release {
  version: string;
  date: string;
  type: "major" | "minor" | "patch";
  highlights: string[];
  breaking?: string[];
}

const releases: Release[] = [
  {
    version: "11.1.0",
    date: "2026-03-15",
    type: "minor",
    highlights: [
      "Multi-language support: Japanese, German, French, Chinese, Korean, Spanish, Portuguese",
      "DORA compliance dashboard with 5-pillar visualization",
      "Slack & Microsoft Teams webhook notifications",
      "14-day Business trial auto-provisioned on first sign-in",
      "Onboarding wizard with personalized resilience score",
      "Coupon/referral code support on pricing page",
    ],
  },
  {
    version: "11.0.0",
    date: "2026-02-01",
    type: "major",
    highlights: [
      "AI Agent Resilience simulation framework",
      "N-Layer Availability Model (5-layer decomposition)",
      "Monte Carlo + Markov chain simulation engines",
      "DORA Article 25 compliance report export (PDF)",
      "Supabase-backed projects & simulation history",
      "APM real-time dashboard (35+ views)",
    ],
    breaking: [
      "API v1 endpoints deprecated — use /api/v2/* (automatic redirect active until v12.0)",
    ],
  },
  {
    version: "10.5.0",
    date: "2025-11-10",
    type: "minor",
    highlights: [
      "Vulnerability feed integration (CVE/NVD)",
      "IAC (Infrastructure-as-Code) health analysis",
      "Bus factor risk calculator",
      "Shadow IT discovery module",
    ],
  },
  {
    version: "10.0.0",
    date: "2025-08-20",
    type: "major",
    highlights: [
      "SaaS launch — faultray.com",
      "Stripe subscription billing (Pro/Business plans)",
      "Supabase authentication (GitHub OAuth, Google OAuth)",
      "Docker self-hosted deployment support",
    ],
  },
];

const typeBadge: Record<Release["type"], { label: string; className: string }> = {
  major: { label: "Major", className: "bg-[#FFD700]/10 text-[#FFD700] border border-[#FFD700]/20" },
  minor: { label: "Minor", className: "bg-blue-500/10 text-blue-400 border border-blue-500/20" },
  patch: { label: "Patch", className: "bg-[#1e293b] text-[#94a3b8] border border-[#334155]" },
};

export default function ChangelogPage() {
  return (
    <div className="w-full px-6 py-10">
      <div className="mb-12">
        <h1 className="text-3xl font-bold tracking-tight mb-3">Changelog</h1>
        <p className="text-[#94a3b8]">
          New features, improvements, and fixes — updated with each release.
        </p>
        <p className="text-sm text-[#64748b] mt-2">
          Subscribe to{" "}
          <a
            href="https://github.com/mattyopon/faultray/releases"
            target="_blank"
            rel="noopener noreferrer"
            className="text-[#94a3b8] underline hover:text-white transition-colors"
          >
            GitHub Releases
          </a>{" "}
          to get notified of new versions.
        </p>
      </div>

      <div className="space-y-12">
        {releases.map((release) => {
          const badge = typeBadge[release.type];
          return (
            <div key={release.version} className="relative pl-8 border-l border-[#1e293b]">
              <div className="absolute -left-1.5 top-1.5 w-3 h-3 rounded-full bg-[#FFD700]" />

              <div className="flex flex-wrap items-center gap-3 mb-4">
                <h2 className="text-xl font-bold">v{release.version}</h2>
                <span
                  className={`inline-block px-2.5 py-0.5 text-xs font-semibold rounded-full ${badge.className}`}
                >
                  {badge.label}
                </span>
                <time className="text-sm text-[#64748b]" dateTime={release.date}>
                  {new Date(release.date).toLocaleDateString("en-US", {
                    year: "numeric",
                    month: "long",
                    day: "numeric",
                  })}
                </time>
              </div>

              <ul className="space-y-2 mb-4">
                {release.highlights.map((item) => (
                  <li key={item} className="flex items-start gap-2 text-sm text-[#cbd5e1]">
                    <span className="text-emerald-400 mt-0.5 shrink-0">+</span>
                    {item}
                  </li>
                ))}
              </ul>

              {release.breaking && release.breaking.length > 0 && (
                <div className="mt-3 p-3 rounded-lg bg-red-500/10 border border-red-500/20">
                  <p className="text-xs font-semibold text-red-400 mb-1 uppercase tracking-wide">
                    Breaking Changes
                  </p>
                  {release.breaking.map((item) => (
                    <p key={item} className="text-xs text-red-300">
                      {item}
                    </p>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div className="mt-16 pt-8 border-t border-[#1e293b] flex flex-wrap gap-4 text-sm text-[#64748b]">
        <Link href="/features" className="hover:text-white transition-colors">
          Features
        </Link>
        <Link href="/pricing" className="hover:text-white transition-colors">
          Pricing
        </Link>
        <a
          href="https://github.com/mattyopon/faultray/releases"
          target="_blank"
          rel="noopener noreferrer"
          className="hover:text-white transition-colors"
        >
          GitHub Releases
        </a>
      </div>
    </div>
  );
}
