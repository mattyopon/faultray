import "server-only";
import type { Metadata } from "next";
import { getDictionary } from "@/i18n/get-dictionary";
import { locales, type Locale } from "@/i18n/config";

const BASE = "https://faultray.com";

/**
 * I18N-03: Shared metadata for the locale landing layouts — localized
 * title/description plus canonical + hreflang alternates covering every
 * supported locale. Layouts that need extra fields (e.g. /ja's OpenGraph
 * block) spread this result and extend it.
 */
export async function landingMetadata(locale: Locale): Promise<Metadata> {
  const dict = await getDictionary(locale);
  return {
    title: dict.metadata.title,
    description: dict.metadata.description,
    alternates: {
      canonical: `${BASE}/${locale}`,
      languages: Object.fromEntries(
        locales.map((l) => [l, `${BASE}/${l}`])
      ) as Record<string, string>,
    },
  };
}
