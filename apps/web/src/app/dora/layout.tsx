import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "DORA Compliance",
  description:
    "Track and prove DORA compliance with FaultRay — automated reports aligned to Digital Operational Resilience Act requirements.",
  alternates: { canonical: "https://faultray.com/dora" },
};

export default function DoraLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
