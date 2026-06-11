import { landingMetadata } from "@/i18n/landing-metadata";

export function generateMetadata() {
  return landingMetadata("es");
}

export default function EsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <div lang="es">{children}</div>; // I18N-04
}
