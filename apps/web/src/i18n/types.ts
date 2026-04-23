/**
 * Type definitions for the i18n dictionary (#35).
 *
 * `LocaleDict` is intentionally deep-partial in the leaf — sections may
 * have keys missing in some locales until we finish the extraction
 * sweep.
 */

export type Locale = "en" | "ja" | "de" | "fr" | "es" | "zh" | "ko" | "pt";

export const LOCALES: readonly Locale[] = [
  "en",
  "ja",
  "de",
  "fr",
  "es",
  "zh",
  "ko",
  "pt",
];

/** Section-level dictionary — string keys only at the leaf. */
export type SectionDict = Readonly<
  Record<string, string | Readonly<Record<string, string>>>
>;

/** Per-locale dictionary = all sections the locale supports. */
export type LocaleDict = Readonly<Record<string, SectionDict>>;
