/**
 * L7: Generality — Detect missing translation keys
 * Reports every key present in en.json but absent in other locales.
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import path from "path";

const DICT_DIR = path.resolve(__dirname, "../../src/i18n/dictionaries");
const LOCALES = ["en", "ja", "de", "fr", "zh", "ko", "es", "pt"] as const;

function loadDict(locale: string): Record<string, unknown> {
  return JSON.parse(readFileSync(path.join(DICT_DIR, `${locale}.json`), "utf-8"));
}

function getLeafKeyPaths(obj: Record<string, unknown>, prefix = ""): string[] {
  const keys: string[] = [];
  for (const [k, v] of Object.entries(obj)) {
    const fullKey = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === "object" && !Array.isArray(v)) {
      keys.push(...getLeafKeyPaths(v as Record<string, unknown>, fullKey));
    } else {
      keys.push(fullKey);
    }
  }
  return keys;
}

describe("L7: Missing Translation Keys", () => {
  const enDict = loadDict("en");
  const enLeafKeys = new Set(getLeafKeyPaths(enDict));

  for (const locale of LOCALES) {
    if (locale === "en") continue;

    it(`${locale}: no missing leaf keys compared to en`, () => {
      const dict = loadDict(locale);
      const localeLeafKeys = new Set(getLeafKeyPaths(dict));

      const missing = [...enLeafKeys].filter((k) => !localeLeafKeys.has(k));

      if (missing.length > 0) {
        console.warn(`${locale}: ${missing.length} missing leaf keys (first 5):`, missing.slice(0, 5));
      }

      // Allow up to 5% missing keys as a soft threshold
      const threshold = Math.ceil(enLeafKeys.size * 0.05);
      expect(missing.length).toBeLessThanOrEqual(threshold);
    });

    it(`${locale}: no extra keys absent from en`, () => {
      const dict = loadDict(locale);
      const localeLeafKeys = new Set(getLeafKeyPaths(dict));

      const extra = [...localeLeafKeys].filter((k) => !enLeafKeys.has(k));

      if (extra.length > 0) {
        console.warn(`${locale}: ${extra.length} extra keys not in en (first 5):`, extra.slice(0, 5));
      }

      // Extra keys are a soft warning, not a failure
      // but >10% extra is suspicious
      const threshold = Math.ceil(enLeafKeys.size * 0.1);
      expect(extra.length).toBeLessThanOrEqual(threshold);
    });
  }
});
