import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Privacy Policy — FaultRay",
  description:
    "FaultRay Privacy Policy — how we collect, use, and protect your personal data in compliance with GDPR and applicable law.",
  alternates: {
    canonical: "https://faultray.com/privacy",
  },
  robots: {
    index: true,
    follow: true,
  },
};

export default function PrivacyLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
