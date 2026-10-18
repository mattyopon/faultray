import { landingMetadata } from "@/i18n/landing-metadata";

export function generateMetadata() {
  return landingMetadata("zh");
}

export default function ZhLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <div lang="zh">{children}</div>; // I18N-04
}
