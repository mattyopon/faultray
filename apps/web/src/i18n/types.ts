/**
 * Type definitions for the i18n dictionary (#35).
 *
 * `LocaleDict` is intentionally deep-partial in the leaf — sections may
 * have keys missing in some locales until we finish the extraction
 * sweep.
 */

// Single source of truth for locales lives in ./config. Re-export it here so
// there is only one Locale union / locale list — a second, independently
// ordered copy previously lived here and could silently diverge from config
// (and from the dictionaries map) when locales were added or removed.
export { locales as LOCALES, type Locale } from "./config";

/** Section-level dictionary — string keys only at the leaf. */
export type SectionDict = Readonly<
  Record<string, string | Readonly<Record<string, string>>>
>;

/** Per-locale dictionary = all sections the locale supports. */
export type LocaleDict = Readonly<Record<string, SectionDict>>;
