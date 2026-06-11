import { landingMetadata } from "@/i18n/landing-metadata";

export function generateMetadata() {
  return landingMetadata("fr");
}

export default function FrLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <div lang="fr">{children}</div>; // I18N-04
}
