import { getDictionary } from "@/i18n/get-dictionary";
import type { Metadata } from "next";

const BASE = "https://faultray.com";

// I18N-03: hreflang alternates for all supported locales
const LOCALES = ["en", "ja", "de", "fr", "zh", "ko", "es", "pt"] as const;

export async function generateMetadata(): Promise<Metadata> {
  const dict = await getDictionary("en");
  return {
    title: dict.metadata.title,
    description: dict.metadata.description,
    alternates: {
      canonical: `${BASE}/en`,
      languages: Object.fromEntries(
        LOCALES.map((locale) => [locale, `${BASE}/${locale}`])
      ) as Record<string, string>,
    },
  };
}

export default function EnLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
