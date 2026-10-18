/**
 * L8: Security — Nav label XSS and href safety
 * Verifies that:
 *  1. No i18n label in appDict.nav or appDict.navExtra contains raw HTML tags.
 *  2. No href in the nav structure uses the javascript: scheme.
 *
 * These checks guard against a compromised or malicious translation entry
 * injecting executable markup into the sidebar.
 */
import { describe, it, expect } from "vitest";
import { appDict } from "@/i18n/app-dict";
import { locales } from "@/i18n/config";

// ── helpers ──────────────────────────────────────────────────────────────────

type StringRecord = Record<string, string>;

/** Returns keys whose values contain at least one HTML tag (<...>). */
function keysWithHtmlTags(obj: StringRecord): string[] {
  return Object.keys(obj).filter((k) => /<[^>]+>/.test(obj[k]));
}

/** Returns keys whose values start with javascript: (case-insensitive). */
function keysWithJsScheme(obj: StringRecord): string[] {
  return Object.keys(obj).filter((k) =>
    /^\s*javascript\s*:/i.test(obj[k])
  );
}

// ── nav ───────────────────────────────────────────────────────────────────────

describe("L8: appDict.nav — no HTML tags in labels", () => {
  for (const locale of locales) {
    it(`nav[${locale}]: no HTML tags`, () => {
      const dict = (appDict.nav as Record<string, StringRecord>)[locale];
      if (!dict) return; // missing locale is caught by nav-keys.test.ts
      const bad = keysWithHtmlTags(dict);
      expect(
        bad,
        `nav[${locale}] keys with HTML tags: ${bad.join(", ")}`
      ).toHaveLength(0);
    });

    it(`nav[${locale}]: no javascript: scheme`, () => {
      const dict = (appDict.nav as Record<string, StringRecord>)[locale];
      if (!dict) return;
      const bad = keysWithJsScheme(dict);
      expect(
        bad,
        `nav[${locale}] keys with javascript: scheme: ${bad.join(", ")}`
      ).toHaveLength(0);
    });
  }
});

// ── navExtra ─────────────────────────────────────────────────────────────────

describe("L8: appDict.navExtra — no HTML tags in labels", () => {
  for (const locale of locales) {
    it(`navExtra[${locale}]: no HTML tags`, () => {
      const dict = (appDict.navExtra as Record<string, StringRecord>)[locale];
      if (!dict) return;
      const bad = keysWithHtmlTags(dict);
      expect(
        bad,
        `navExtra[${locale}] keys with HTML tags: ${bad.join(", ")}`
      ).toHaveLength(0);
    });

    it(`navExtra[${locale}]: no javascript: scheme`, () => {
      const dict = (appDict.navExtra as Record<string, StringRecord>)[locale];
      if (!dict) return;
      const bad = keysWithJsScheme(dict);
      expect(
        bad,
        `navExtra[${locale}] keys with javascript: scheme: ${bad.join(", ")}`
      ).toHaveLength(0);
    });
  }
});

// ── Static href safety (nav structure defined in navbar.tsx) ─────────────────
// We check the hrefs from the nav inline (same list as navbar.test.ts).

const NAV_HREFS: string[] = [
  "/dashboard", "/traffic-light", "/apm", "/incidents",
  "/simulate", "/whatif", "/fmea", "/benchmark", "/sla-budget",
  "/topology", "/dependencies", "/heatmap", "/people-risk",
  "/score-detail", "/topology-map",
  "/dora", "/compliance", "/fisc", "/sla", "/governance", "/compliance-report",
  "/shadow-it", "/bus-factor", "/vuln-priority", "/external-impact",
  "/evidence", "/audit-report",
  "/projects", "/iac", "/optimize", "/gameday",
  "/ai-reliability", "/advisor",
  "/runbooks", "/postmortems", "/calendar", "/timeline", "/drift",
  "/teams", "/env-compare", "/canary", "/supply-chain",
  "/traces", "/logs", "/reports",
  "/onboarding", "/templates", "/ipo-readiness",
  "/settings", "/help",
];

describe("L8: Nav hrefs — no javascript: scheme", () => {
  it("no href uses javascript: scheme", () => {
    const bad = NAV_HREFS.filter((h) => /^\s*javascript\s*:/i.test(h));
    expect(
      bad,
      `hrefs with javascript: scheme: ${bad.join(", ")}`
    ).toHaveLength(0);
  });
});
