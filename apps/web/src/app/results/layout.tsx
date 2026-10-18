import type { Metadata } from "next";

// SEOMETA-06: ページレベルのcanonicalタグ
export const metadata: Metadata = {
  title: "Simulation Results",
  description: "View and compare your FaultRay simulation runs — availability scores, scenario results, and improvement trends.",
  robots: { index: false, follow: false },
};

export default function ResultsLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
