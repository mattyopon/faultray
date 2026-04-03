import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Data Processing Agreement — FaultRay",
  description: "FaultRay's Data Processing Agreement (DPA) — GDPR compliance, data handling practices, and sub-processor list.",
  alternates: { canonical: "https://faultray.com/dpa" },
  robots: { index: true, follow: true },
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
