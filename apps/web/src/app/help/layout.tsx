import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Help & User Guide",
  description:
    "FaultRay user guide — getting started, dashboard, simulation, DORA compliance, settings, and FAQ.",
};

export default function HelpLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
