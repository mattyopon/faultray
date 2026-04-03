import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Service Level Agreement — FaultRay",
  description: "FaultRay's SLA terms — uptime guarantees, error budgets, support response times, and service credits by plan.",
  alternates: { canonical: "https://faultray.com/service-level-agreement" },
  robots: { index: true, follow: true },
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
