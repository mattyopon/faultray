/**
 * L7: Generality — app-dict.ts consistency
 * Verifies that appDict has entries for all 8 locales in every section.
 */
import { describe, it, expect } from "vitest";
import { appDict } from "@/i18n/app-dict";
import { locales } from "@/i18n/config";

describe("L7: appDict locale coverage", () => {
  const sections = Object.keys(appDict) as (keyof typeof appDict)[];

  it("appDict has at least one section", () => {
    expect(sections.length).toBeGreaterThan(0);
  });

  for (const section of sections) {
    it(`section "${section}" has all 8 locales`, () => {
      const sectionData = appDict[section] as Record<string, unknown>;
      for (const locale of locales) {
        expect(
          sectionData[locale],
          `appDict.${section} is missing locale "${locale}"`
        ).toBeDefined();
      }
    });
  }
});
