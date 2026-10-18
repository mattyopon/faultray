import { landingMetadata } from "@/i18n/landing-metadata";

export function generateMetadata() {
  return landingMetadata("pt");
}

export default function PtLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <div lang="pt">{children}</div>; // I18N-04
}
