export const locales = ["en", "ja", "de", "fr", "zh", "ko", "es", "pt"] as const;
export type Locale = (typeof locales)[number];
export const defaultLocale: Locale = "en";

export function isValidLocale(locale: string): locale is Locale {
  // Widen to readonly string[] so the untrusted input is checked without an
  // unsafe `as Locale` cast at this validation boundary.
  return (locales as readonly string[]).includes(locale);
}
