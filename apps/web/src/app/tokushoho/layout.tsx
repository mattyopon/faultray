import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "特定商取引法に基づく表示 — FaultRay",
  description: "FaultRay（フォルトレイ）の特定商取引法に基づく表示。販売事業者情報、料金、解約方法等を記載。",
  alternates: { canonical: "https://faultray.com/tokushoho" },
  robots: { index: true, follow: true },
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
