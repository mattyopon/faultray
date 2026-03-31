/**
 * L2: Unit Tests — i18n config
 */
import { describe, it, expect } from "vitest";
import { locales, defaultLocale, isValidLocale } from "@/i18n/config";

describe("i18n config", () => {
  it("exports exactly 8 locales", () => {
    expect(locales).toHaveLength(8);
  });

  it("includes all expected locales", () => {
    const expected = ["en", "ja", "de", "fr", "zh", "ko", "es", "pt"];
    for (const loc of expected) {
      expect(locales).toContain(loc);
    }
  });

  it("has 'en' as default locale", () => {
    expect(defaultLocale).toBe("en");
  });

  describe("isValidLocale()", () => {
    it("returns true for valid locales", () => {
      for (const loc of locales) {
        expect(isValidLocale(loc)).toBe(true);
      }
    });

    it("returns false for invalid locales", () => {
      expect(isValidLocale("xx")).toBe(false);
      expect(isValidLocale("")).toBe(false);
      expect(isValidLocale("english")).toBe(false);
    });
  });
});
