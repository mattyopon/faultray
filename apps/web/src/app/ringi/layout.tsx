import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "稟議書テンプレート | FaultRay",
  description:
    "FaultRay導入のための稟議書テンプレート。コスト、ROI、セキュリティ、コンプライアンス対応をまとめた日本語テンプレートを無償提供します。",
  alternates: { canonical: "https://faultray.com/ringi" },
  robots: { index: true, follow: true },
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
