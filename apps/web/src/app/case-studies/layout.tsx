import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Case Studies — FaultRay",
  description:
    "Real-world infrastructure resilience case studies powered by FaultRay chaos engineering simulations.",
  alternates: {
    canonical: "https://faultray.com/case-studies",
  },
  robots: {
    index: true,
    follow: true,
  },
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
