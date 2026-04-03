import type { Metadata } from "next";

export const metadata: Metadata = {
  alternates: { canonical: "https://faultray.com/tokushoho" },
  robots: { index: true, follow: true },
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
