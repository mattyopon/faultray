import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "DORA Research Dashboard (Prototype)",
  description:
    "Research prototype mapping FaultRay simulations to Digital Operational Resilience Act articles. NOT validated for regulatory audit — independent legal and technical review required before any compliance use.",
  alternates: { canonical: "https://faultray.com/dora" },
  robots: { index: false, follow: false },
};

export default function DoraLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
