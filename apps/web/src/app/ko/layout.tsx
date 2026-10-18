import { landingMetadata } from "@/i18n/landing-metadata";

export function generateMetadata() {
  return landingMetadata("ko");
}

export default function KoLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <div lang="ko">{children}</div>; // I18N-04
}
