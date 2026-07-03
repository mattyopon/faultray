import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "DORA Resilience Evidence Sprint — FaultRay",
  description:
    "A fixed-scope, 5-business-day Sprint that assembles a structured resilience evidence pack for DORA pre-audit preparation. Sanitized data only — no production access, no PII. $2,500 fixed. Decision-support material, not legal advice, an audit, or certification.",
  alternates: {
    canonical: "https://faultray.com/evidence-sprint",
  },
  robots: {
    index: true,
    follow: true,
  },
};

export default function EvidenceSprintLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
