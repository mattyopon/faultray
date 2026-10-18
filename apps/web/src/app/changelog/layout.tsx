import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Changelog — FaultRay",
  description:
    "Latest updates, new features, and improvements to FaultRay chaos engineering platform.",
  alternates: {
    canonical: "https://faultray.com/changelog",
  },
  robots: {
    index: true,
    follow: true,
  },
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
