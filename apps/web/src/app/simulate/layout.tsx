import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Run Simulation — FaultRay",
  description:
    "Run chaos engineering simulations against your infrastructure topology — zero production risk, 2,000+ failure scenarios.",
  robots: { index: false, follow: false },
};

export default function SimulateLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
