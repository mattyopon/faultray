import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Terms of Service — FaultRay",
  description:
    "FaultRay Terms of Service — the agreement governing your use of the FaultRay platform.",
  alternates: {
    canonical: "https://faultray.com/terms",
  },
  robots: {
    index: true,
    follow: true,
  },
};

export default function TermsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
