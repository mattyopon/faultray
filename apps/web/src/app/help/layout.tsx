import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Help & User Guide — FaultRay",
  description:
    "FaultRay user guide — getting started, dashboard, simulation, DORA-aligned research, settings, and FAQ.",
  alternates: {
    canonical: "https://faultray.com/help",
  },
  robots: {
    index: true,
    follow: true,
  },
};

export default function HelpLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
