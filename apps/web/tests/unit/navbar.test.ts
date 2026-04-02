/**
 * L2: Unit Tests — Navbar navigation integrity
 * Verifies that href values in getNavGroups() satisfy structural invariants.
 *
 * Note: Some hrefs (e.g. /sla-budget, /topology-map, /shadow-it, /bus-factor,
 * /vuln-priority, /external-impact, /compliance-report) do not yet have
 * corresponding page.tsx files. Those are tracked in the KNOWN_MISSING set
 * below and excluded from the existence check so that this test fails fast
 * when NEW missing pages are introduced, while not blocking CI on already-known gaps.
 */
import { describe, it, expect } from "vitest";
import { existsSync } from "fs";
import path from "path";

// ── Inline the nav structure (mirrors navbar.tsx getNavGroups) ──────────────
// We duplicate hrefs here rather than importing the React component so that
// this test remains a pure unit test with no jsdom/React dependency.

const NAV_HREFS: string[] = [
  // OBSERVE
  "/dashboard",
  "/traffic-light",
  "/apm",
  "/incidents",
  // ANALYZE
  "/simulate",
  "/whatif",
  "/fmea",
  "/benchmark",
  "/sla-budget",
  // VISUALIZE
  "/topology",
  "/dependencies",
  "/heatmap",
  "/people-risk",
  "/score-detail",
  "/topology-map",
  // COMPLIANCE
  "/dora",
  "/compliance",
  "/fisc",
  "/sla",
  "/governance",
  "/compliance-report",
  // RISK
  "/shadow-it",
  "/bus-factor",
  "/vuln-priority",
  "/external-impact",
  // AUDIT
  "/evidence",
  "/audit-report",
  // IMPROVE ACTIONS
  "/projects",
  "/iac",
  "/optimize",
  "/gameday",
  // AI
  "/ai-reliability",
  "/advisor",
  // OPERATIONS
  "/runbooks",
  "/postmortems",
  "/calendar",
  "/timeline",
  "/drift",
  // TEAMS & ENV
  "/teams",
  "/env-compare",
  "/canary",
  "/supply-chain",
  // REPORTS & LOGS
  "/traces",
  "/logs",
  "/reports",
  // GETTING STARTED
  "/onboarding",
  "/templates",
  "/ipo-readiness",
  // ACCOUNT
  "/settings",
  "/help",
];

// Pages that are referenced in the navbar but do not yet have page.tsx.
// When a page is created, remove it from this set — the test will then
// enforce its existence automatically.
const KNOWN_MISSING = new Set([
  "/sla-budget",
  "/topology-map",
  "/compliance-report",
  "/shadow-it",
  "/bus-factor",
  "/vuln-priority",
  "/external-impact",
]);

const APP_DIR = path.resolve(__dirname, "../../src/app");

describe("Navbar: navigation integrity", () => {
  it("all hrefs start with /", () => {
    const bad = NAV_HREFS.filter((h) => !h.startsWith("/"));
    expect(bad, `hrefs not starting with /: ${bad.join(", ")}`).toHaveLength(0);
  });

  it("no duplicate hrefs", () => {
    const seen = new Set<string>();
    const dups: string[] = [];
    for (const h of NAV_HREFS) {
      if (seen.has(h)) dups.push(h);
      seen.add(h);
    }
    expect(dups, `duplicate hrefs: ${dups.join(", ")}`).toHaveLength(0);
  });

  it("all hrefs (except known-missing) have a corresponding page.tsx", () => {
    const missing: string[] = [];
    for (const href of NAV_HREFS) {
      if (KNOWN_MISSING.has(href)) continue;
      const pagePath = path.join(APP_DIR, href, "page.tsx");
      if (!existsSync(pagePath)) {
        missing.push(href);
      }
    }
    expect(
      missing,
      `hrefs without page.tsx (add to KNOWN_MISSING if intentional): ${missing.join(", ")}`
    ).toHaveLength(0);
  });

  it("KNOWN_MISSING set contains only hrefs that are actually missing", () => {
    // If a page.tsx is created, this test reminds us to update KNOWN_MISSING.
    const spurious: string[] = [];
    for (const href of KNOWN_MISSING) {
      const pagePath = path.join(APP_DIR, href, "page.tsx");
      if (existsSync(pagePath)) {
        spurious.push(href);
      }
    }
    expect(
      spurious,
      `these hrefs are in KNOWN_MISSING but page.tsx now exists — remove from set: ${spurious.join(", ")}`
    ).toHaveLength(0);
  });
});
