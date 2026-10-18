/**
 * L2: Unit Tests — Command Palette filtering logic
 *
 * The filtering logic lives inside command-palette.tsx (lines 28-33) and is
 * not exported as a standalone function.  We reproduce the exact same logic
 * here so the tests remain pure (no React/jsdom required) while faithfully
 * capturing the contract.
 *
 * If the filtering logic in command-palette.tsx changes, update this file to
 * match.  The source of truth is:
 *   src/components/command-palette.tsx — filtered = query.trim() === ""
 *     ? items
 *     : items.filter((item) =>
 *         item.label.toLowerCase().includes(query.toLowerCase()) ||
 *         item.group.toLowerCase().includes(query.toLowerCase())
 *       );
 */
import { describe, it, expect } from "vitest";
import type { LucideIcon } from "lucide-react";

// ── Reproduce the CommandItem type (mirrors command-palette.tsx) ─────────────

interface CommandItem {
  href: string;
  label: string;
  group: string;
  icon: LucideIcon;
}

// ── Reproduce the filtering logic (mirrors command-palette.tsx, lines 28-33) ─

function filterItems(items: CommandItem[], query: string): CommandItem[] {
  if (query.trim() === "") return items;
  return items.filter(
    (item) =>
      item.label.toLowerCase().includes(query.toLowerCase()) ||
      item.group.toLowerCase().includes(query.toLowerCase())
  );
}

// ── Fixture ──────────────────────────────────────────────────────────────────

// icon is typed as LucideIcon but filtering never reads it, so a cast suffices.
const stub = null as unknown as LucideIcon;

const ITEMS: CommandItem[] = [
  { href: "/simulate",    label: "Run Simulation",    group: "ANALYZE",   icon: stub },
  { href: "/whatif",      label: "What-if",           group: "ANALYZE",   icon: stub },
  { href: "/fmea",        label: "FMEA",              group: "ANALYZE",   icon: stub },
  { href: "/dashboard",   label: "Dashboard",         group: "OBSERVE",   icon: stub },
  { href: "/topology",    label: "Topology",          group: "VISUALIZE", icon: stub },
  { href: "/heatmap",     label: "Heatmap",           group: "VISUALIZE", icon: stub },
  { href: "/compliance",  label: "Compliance",        group: "COMPLIANCE",icon: stub },
];

// Japanese labels for locale-sensitive tests
const ITEMS_JA: CommandItem[] = [
  { href: "/simulate",  label: "シミュレーション実行", group: "分析", icon: stub },
  { href: "/dashboard", label: "ダッシュボード",       group: "観察", icon: stub },
  { href: "/fmea",      label: "FMEA",                group: "分析", icon: stub },
];

// ── Tests ────────────────────────────────────────────────────────────────────

describe("CommandPalette: filterItems()", () => {
  describe("empty query returns all items", () => {
    it("empty string returns full list", () => {
      expect(filterItems(ITEMS, "")).toHaveLength(ITEMS.length);
    });

    it("whitespace-only string returns full list", () => {
      expect(filterItems(ITEMS, "   ")).toHaveLength(ITEMS.length);
    });
  });

  describe("label matching", () => {
    it('"sim" matches "Run Simulation"', () => {
      const results = filterItems(ITEMS, "sim");
      expect(results.map((r) => r.href)).toContain("/simulate");
    });

    it('"dashboard" matches "Dashboard" (case-insensitive)', () => {
      const results = filterItems(ITEMS, "DASHBOARD");
      expect(results.map((r) => r.href)).toContain("/dashboard");
    });

    it('"heat" matches "Heatmap"', () => {
      const results = filterItems(ITEMS, "heat");
      expect(results.map((r) => r.href)).toContain("/heatmap");
    });
  });

  describe("group matching", () => {
    it('"visualize" matches items in VISUALIZE group', () => {
      const results = filterItems(ITEMS, "visualize");
      const hrefs = results.map((r) => r.href);
      expect(hrefs).toContain("/topology");
      expect(hrefs).toContain("/heatmap");
    });

    it('"analyze" matches items in ANALYZE group', () => {
      const results = filterItems(ITEMS, "analyze");
      const hrefs = results.map((r) => r.href);
      expect(hrefs).toContain("/simulate");
      expect(hrefs).toContain("/whatif");
      expect(hrefs).toContain("/fmea");
    });
  });

  describe("no-match cases", () => {
    it("non-existent keyword returns 0 results", () => {
      expect(filterItems(ITEMS, "xyzzy_no_match")).toHaveLength(0);
    });

    it("query matching nothing in label or group returns empty", () => {
      expect(filterItems(ITEMS, "kubernetes")).toHaveLength(0);
    });
  });

  describe("Japanese label matching", () => {
    it('"シミュレーション" matches Japanese simulation item', () => {
      const results = filterItems(ITEMS_JA, "シミュレーション");
      expect(results.map((r) => r.href)).toContain("/simulate");
    });

    it('"ダッシュボード" matches Japanese dashboard item', () => {
      const results = filterItems(ITEMS_JA, "ダッシュボード");
      expect(results.map((r) => r.href)).toContain("/dashboard");
    });

    it('"分析" matches items in Japanese 分析 group', () => {
      const results = filterItems(ITEMS_JA, "分析");
      const hrefs = results.map((r) => r.href);
      expect(hrefs).toContain("/simulate");
      expect(hrefs).toContain("/fmea");
    });
  });

  describe("edge cases", () => {
    it("empty items list returns empty array for any query", () => {
      expect(filterItems([], "sim")).toHaveLength(0);
    });

    it("empty items list with empty query returns empty array", () => {
      expect(filterItems([], "")).toHaveLength(0);
    });

    it("partial match in middle of label works", () => {
      // "plian" is in "comPlIANce" — case-insensitive substring
      const results = filterItems(ITEMS, "plian");
      expect(results.map((r) => r.href)).toContain("/compliance");
    });
  });
});
