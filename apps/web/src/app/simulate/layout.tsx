import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Run Simulation",
  description:
    "Run chaos engineering simulations against your infrastructure topology — zero production risk, 2,000+ failure scenarios.",
};

export default function SimulateLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
