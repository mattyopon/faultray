import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Pricing",
  description:
    "FaultRay pricing plans — Free, Pro ($299/mo), and Business ($999/mo). Start for free, upgrade when you need more.",
};

export default function PricingLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
