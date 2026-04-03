import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Live Demo — FaultRay Chaos Engineering",
  description: "Try FaultRay live — run a chaos engineering simulation against a sample infrastructure topology with zero risk in under 60 seconds.",
  alternates: { canonical: "https://faultray.com/demo" },
  robots: { index: true, follow: true },
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
