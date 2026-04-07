import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Features — FaultRay Chaos Engineering Platform",
  description:
    "FaultRay features — 100+ simulation engines, N-Layer availability model, DORA evidence drafts (research prototype), AI root cause analysis, and more.",
  alternates: {
    canonical: "https://faultray.com/features",
  },
  robots: {
    index: true,
    follow: true,
  },
};

export default function FeaturesLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
