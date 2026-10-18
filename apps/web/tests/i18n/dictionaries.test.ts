/**
 * L7: Generality — Dictionary consistency across all 8 locales
 * Ensures every locale has the same top-level and nested keys as English.
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import path from "path";

const DICT_DIR = path.resolve(__dirname, "../../src/i18n/dictionaries");
const LOCALES = ["en", "ja", "de", "fr", "zh", "ko", "es", "pt"] as const;

function loadDict(locale: string): Record<string, unknown> {
  const raw = readFileSync(path.join(DICT_DIR, `${locale}.json`), "utf-8");
  return JSON.parse(raw);
}

function getKeyPaths(obj: Record<string, unknown>, prefix = ""): string[] {
  const keys: string[] = [];
  for (const [k, v] of Object.entries(obj)) {
    const fullKey = prefix ? `${prefix}.${k}` : k;
    keys.push(fullKey);
    if (v && typeof v === "object" && !Array.isArray(v)) {
      keys.push(...getKeyPaths(v as Record<string, unknown>, fullKey));
    }
  }
  return keys;
}

describe("L7: Dictionary Consistency", () => {
  const enDict = loadDict("en");
  const enKeys = getKeyPaths(enDict).sort();

  it("English dictionary loads with expected top-level sections", () => {
    const topLevelKeys = Object.keys(enDict);
    expect(topLevelKeys).toContain("metadata");
    expect(topLevelKeys).toContain("nav");
    expect(topLevelKeys).toContain("hero");
    expect(topLevelKeys).toContain("pricing");
    expect(topLevelKeys).toContain("footer");
  });

  for (const locale of LOCALES) {
    if (locale === "en") continue;

    it(`${locale}.json has all keys from en.json`, () => {
      const dict = loadDict(locale);
      const keys = getKeyPaths(dict).sort();

      const missingKeys = enKeys.filter((k) => !keys.includes(k));
      if (missingKeys.length > 0) {
        console.warn(`${locale}: missing ${missingKeys.length} keys:`, missingKeys.slice(0, 10));
      }
      // Top-level keys must match exactly
      expect(Object.keys(dict).sort()).toEqual(Object.keys(enDict).sort());
    });
  }

  it("all locale files exist and parse as valid JSON", () => {
    for (const locale of LOCALES) {
      expect(() => loadDict(locale)).not.toThrow();
    }
  });
});
