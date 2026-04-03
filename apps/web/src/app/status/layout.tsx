import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "System Status — FaultRay",
  description: "Real-time operational status of FaultRay services — API, simulation engine, and dashboard uptime.",
  alternates: { canonical: "https://faultray.com/status" },
  robots: { index: true, follow: true },
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
