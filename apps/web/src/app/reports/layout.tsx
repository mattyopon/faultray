import type { Metadata } from "next";

// SEOMETA-06: ページレベルのcanonicalタグ
export const metadata: Metadata = {
  title: "Executive Reports",
  description: "Generate and export executive-ready resilience reports for your infrastructure. DORA-aligned, boardroom-ready.",
  robots: { index: false, follow: false },
};

export default function ReportsLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
