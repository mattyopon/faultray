import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Features — FaultRay Pre-Deployment Resilience Simulation",
  description:
    "FaultRay features — multiple simulation engines (Cascade, Dynamic, Ops, What-If, Capacity), N-Layer availability model, DORA evidence drafts (research prototype, not audit-certified), AI-assisted analysis, and more.",
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
