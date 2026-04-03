import { getDictionary } from "@/i18n/get-dictionary";
import type { Metadata } from "next";

const BASE = "https://faultray.com";
const LOCALES = ["en", "ja", "de", "fr", "zh", "ko", "es", "pt"] as const;

export async function generateMetadata(): Promise<Metadata> {
  const dict = await getDictionary("fr");
  return {
    title: dict.metadata.title,
    description: dict.metadata.description,
    alternates: {
      canonical: `${BASE}/fr`,
      languages: Object.fromEntries(
        LOCALES.map((locale) => [locale, `${BASE}/${locale}`])
      ) as Record<string, string>,
    },
  };
}

export default function FrLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
