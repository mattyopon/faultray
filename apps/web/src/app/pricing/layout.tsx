import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Pricing — FaultRay",
  description:
    "FaultRay pricing plans — Free, Pro ($299/mo), and Business ($999/mo). Start for free, upgrade when you need more.",
  alternates: {
    canonical: "https://faultray.com/pricing",
  },
  robots: {
    index: true,
    follow: true,
  },
};

export default function PricingLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
