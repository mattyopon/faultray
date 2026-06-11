import { landingMetadata } from "@/i18n/landing-metadata";

export function generateMetadata() {
  return landingMetadata("de");
}

export default function DeLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <div lang="de">{children}</div>; // I18N-04
}
