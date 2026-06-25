/**
 * i18n ratchet: cap inline `locale === "ja"` ternaries.
 *
 * ~600 inline `locale === "ja" ? jaText : enText` ternaries across src/app
 * hardcode a JA/EN pair, so the other six locales (de/fr/zh/ko/es/pt) silently
 * fall back to English. The real fix is to route copy through the 8-locale
 * `appDict`, which is a large translation effort. Until then, this guard stops
 * the debt from GROWING: the count may only decrease. When you migrate strings
 * to appDict, lower BASELINE to the new count.
 *
 * Do NOT add new `locale === "ja"` ternaries — add keys to src/i18n/app-dict.ts
 * (all 8 locales) and read `appDict.section[locale] ?? appDict.section.en`.
 */
import { describe, it, expect } from "vitest";
import fs from "fs";
import path from "path";

const APP_DIR = path.resolve(__dirname, "..", "..", "src", "app");

// Current count — a ceiling, not a target. Lower it as you migrate.
const BASELINE = 603;

function walk(dir: string): string[] {
  const out: string[] = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...walk(full));
    else if (/\.(ts|tsx)$/.test(entry.name)) out.push(full);
  }
  return out;
}

function countLocaleJa(): number {
  const re = /locale === ("ja"|'ja')/g;
  let total = 0;
  for (const file of walk(APP_DIR)) {
    const matches = fs.readFileSync(file, "utf8").match(re);
    if (matches) total += matches.length;
  }
  return total;
}

describe("i18n ratchet", () => {
  it(`does not exceed the inline locale==='ja' baseline (${BASELINE})`, () => {
    const count = countLocaleJa();
    expect(
      count,
      `Inline \`locale === "ja"\` ternaries rose to ${count} (baseline ${BASELINE}). ` +
        `Route new copy through appDict (all 8 locales) instead of a JA/EN ternary. ` +
        `If you migrated some, lower BASELINE in this test to ${count}.`,
    ).toBeLessThanOrEqual(BASELINE);
  });
});
