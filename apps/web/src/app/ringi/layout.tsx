import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "IT補助金申請サポート — FaultRay",
  description: "FaultRayを活用したIT導入補助金・持続化補助金の申請サポート。インフラ可用性の向上を補助金で実現。",
  alternates: { canonical: "https://faultray.com/ringi" },
  robots: { index: true, follow: true },
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
