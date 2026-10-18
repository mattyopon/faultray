import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Support — FaultRay",
  description: "FaultRay support resources — documentation, FAQs, troubleshooting guides, and how to contact our team.",
  alternates: { canonical: "https://faultray.com/support" },
  robots: { index: true, follow: true },
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
