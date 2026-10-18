/**
 * L7: Generality — nav/navExtra i18n key completeness
 * Verifies that every key present in the English (en) baseline of
 * appDict.nav and appDict.navExtra also exists in all 8 locales,
 * and that no value is an empty string.
 */
import { describe, it, expect } from "vitest";
import { appDict } from "@/i18n/app-dict";
import { locales } from "@/i18n/config";

// ── helpers ──────────────────────────────────────────────────────────────────

type StringRecord = Record<string, string>;

function getMissingKeys(
  baseline: StringRecord,
  target: StringRecord
): string[] {
  return Object.keys(baseline).filter((k) => !(k in target));
}

function getEmptyValueKeys(target: StringRecord): string[] {
  return Object.keys(target).filter((k) => target[k] === "");
}

// ── appDict.nav ───────────────────────────────────────────────────────────────

describe("L7: appDict.nav — all locales have all en keys", () => {
  const enNav = appDict.nav.en as StringRecord;

  for (const locale of locales) {
    if (locale === "en") continue;

    it(`nav[${locale}]: no missing keys`, () => {
      const localeNav = (appDict.nav as Record<string, StringRecord>)[locale];
      expect(
        localeNav,
        `appDict.nav["${locale}"] is undefined`
      ).toBeDefined();
      const missing = getMissingKeys(enNav, localeNav);
      expect(
        missing,
        `nav[${locale}] missing keys: ${missing.join(", ")}`
      ).toHaveLength(0);
    });

    it(`nav[${locale}]: no empty-string values`, () => {
      const localeNav = (appDict.nav as Record<string, StringRecord>)[locale];
      if (!localeNav) return; // already caught above
      const empty = getEmptyValueKeys(localeNav);
      expect(
        empty,
        `nav[${locale}] has empty-string values: ${empty.join(", ")}`
      ).toHaveLength(0);
    });
  }
});

// ── appDict.navExtra ──────────────────────────────────────────────────────────

describe("L7: appDict.navExtra — all locales have all en keys", () => {
  const enNavExtra = appDict.navExtra.en as StringRecord;

  for (const locale of locales) {
    if (locale === "en") continue;

    it(`navExtra[${locale}]: no missing keys`, () => {
      const localeNavExtra = (
        appDict.navExtra as Record<string, StringRecord>
      )[locale];
      expect(
        localeNavExtra,
        `appDict.navExtra["${locale}"] is undefined`
      ).toBeDefined();
      const missing = getMissingKeys(enNavExtra, localeNavExtra);
      expect(
        missing,
        `navExtra[${locale}] missing keys: ${missing.join(", ")}`
      ).toHaveLength(0);
    });

    it(`navExtra[${locale}]: no empty-string values`, () => {
      const localeNavExtra = (
        appDict.navExtra as Record<string, StringRecord>
      )[locale];
      if (!localeNavExtra) return;
      const empty = getEmptyValueKeys(localeNavExtra);
      expect(
        empty,
        `navExtra[${locale}] has empty-string values: ${empty.join(", ")}`
      ).toHaveLength(0);
    });
  }
});
