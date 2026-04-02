/**
 * L2: Unit Tests — Nav group structure invariants
 * Verifies that the getNavGroups() data structure in navbar.tsx satisfies
 * the structural contracts expected by the sidebar renderer.
 *
 * We duplicate the group definitions inline (without importing the React
 * component) so this test has no jsdom/React dependency.  When new groups or
 * items are added to navbar.tsx, add them here too.
 */
import { describe, it, expect } from "vitest";

// ── Minimal types (mirrors navbar.tsx) ───────────────────────────────────────

interface NavItem {
  href: string;
  label: string | undefined;
  // icon is a React component — we only care that it is not null/undefined
  icon: unknown;
}

interface NavGroup {
  label: string | undefined;
  items: NavItem[];
}

// ── Inline nav groups (mirrors getNavGroups in navbar.tsx) ───────────────────
// Labels use English fallbacks (the ?? branch) so this test is locale-agnostic.

const NAV_GROUPS: NavGroup[] = [
  {
    label: "OBSERVE",
    items: [
      { href: "/dashboard",     label: "Dashboard",    icon: true },
      { href: "/traffic-light", label: "Status",       icon: true },
      { href: "/apm",           label: "APM",          icon: true },
      { href: "/incidents",     label: "Incidents",    icon: true },
    ],
  },
  {
    label: "ANALYZE",
    items: [
      { href: "/simulate",  label: "Run Simulation", icon: true },
      { href: "/whatif",    label: "What-if",        icon: true },
      { href: "/fmea",      label: "FMEA",           icon: true },
      { href: "/benchmark", label: "Monte Carlo",    icon: true },
      { href: "/sla-budget",label: "SLA Budget",     icon: true },
    ],
  },
  {
    label: "VISUALIZE",
    items: [
      { href: "/topology",      label: "Topology",        icon: true },
      { href: "/dependencies",  label: "Dependencies",    icon: true },
      { href: "/heatmap",       label: "Heatmap",         icon: true },
      { href: "/people-risk",   label: "People Risk",     icon: true },
      { href: "/score-detail",  label: "Score Detail",    icon: true },
      { href: "/topology-map",  label: "Interactive Map", icon: true },
    ],
  },
  {
    label: "COMPLIANCE",
    items: [
      { href: "/dora",              label: "DORA",           icon: true },
      { href: "/compliance",        label: "Compliance",     icon: true },
      { href: "/fisc",              label: "FISC",           icon: true },
      { href: "/sla",               label: "SLA/SLO",        icon: true },
      { href: "/governance",        label: "Governance",     icon: true },
      { href: "/compliance-report", label: "Evidence Report",icon: true },
    ],
  },
  {
    label: "RISK",
    items: [
      { href: "/shadow-it",       label: "Shadow IT",      icon: true },
      { href: "/bus-factor",      label: "Bus Factor",     icon: true },
      { href: "/vuln-priority",   label: "Vuln Priority",  icon: true },
      { href: "/external-impact", label: "SaaS Impact",    icon: true },
    ],
  },
  {
    label: "AUDIT & EVIDENCE",
    items: [
      { href: "/evidence",     label: "Audit Evidence", icon: true },
      { href: "/audit-report", label: "Audit Report",   icon: true },
    ],
  },
  {
    label: "IMPROVE ACTIONS",
    items: [
      { href: "/projects", label: "Remediation Plan", icon: true },
      { href: "/iac",      label: "IaC Generator",    icon: true },
      { href: "/optimize", label: "Optimize",         icon: true },
      { href: "/gameday",  label: "GameDay",          icon: true },
    ],
  },
  {
    label: "AI",
    items: [
      { href: "/ai-reliability", label: "AI Reliability", icon: true },
      { href: "/advisor",        label: "AI Advisor",     icon: true },
    ],
  },
  {
    label: "OPERATIONS",
    items: [
      { href: "/runbooks",    label: "Runbooks",        icon: true },
      { href: "/postmortems", label: "Post-Mortems",    icon: true },
      { href: "/calendar",    label: "Calendar",        icon: true },
      { href: "/timeline",    label: "Timeline",        icon: true },
      { href: "/drift",       label: "Drift Detection", icon: true },
    ],
  },
  {
    label: "TEAMS & ENV",
    items: [
      { href: "/teams",        label: "Team Metrics", icon: true },
      { href: "/env-compare",  label: "Env Compare",  icon: true },
      { href: "/canary",       label: "Canary",       icon: true },
      { href: "/supply-chain", label: "Supply Chain", icon: true },
    ],
  },
  {
    label: "REPORTS & LOGS",
    items: [
      { href: "/traces",  label: "Traces",  icon: true },
      { href: "/logs",    label: "Logs",    icon: true },
      { href: "/reports", label: "Reports", icon: true },
    ],
  },
  {
    label: "GETTING STARTED",
    items: [
      { href: "/onboarding",    label: "Get Started",   icon: true },
      { href: "/templates",     label: "Templates",     icon: true },
      { href: "/ipo-readiness", label: "IPO Readiness", icon: true },
    ],
  },
  {
    label: "ACCOUNT",
    items: [
      { href: "/settings", label: "Settings", icon: true },
      { href: "/help",     label: "Help",     icon: true },
    ],
  },
];

// ── Tests ────────────────────────────────────────────────────────────────────

describe("Nav groups: structural invariants", () => {
  it("at least one group exists", () => {
    expect(NAV_GROUPS.length).toBeGreaterThan(0);
  });

  it("all groups have a non-empty label", () => {
    const bad = NAV_GROUPS.filter(
      (g) => !g.label || g.label.trim() === ""
    );
    expect(bad, `groups without label: ${bad.map((_, i) => i).join(", ")}`).toHaveLength(0);
  });

  it("all groups have at least one item", () => {
    const bad = NAV_GROUPS.filter((g) => !g.items || g.items.length === 0);
    expect(
      bad.map((g) => g.label),
      `groups with 0 items`
    ).toHaveLength(0);
  });

  it("all items have a non-empty href starting with /", () => {
    const bad: string[] = [];
    for (const group of NAV_GROUPS) {
      for (const item of group.items) {
        if (!item.href || !item.href.startsWith("/")) {
          bad.push(`${group.label} → "${item.href}"`);
        }
      }
    }
    expect(bad, `items with invalid href: ${bad.join("; ")}`).toHaveLength(0);
  });

  it("all items have a non-empty label", () => {
    const bad: string[] = [];
    for (const group of NAV_GROUPS) {
      for (const item of group.items) {
        if (!item.label || item.label.trim() === "") {
          bad.push(`${group.label} → href=${item.href}`);
        }
      }
    }
    expect(bad, `items without label: ${bad.join("; ")}`).toHaveLength(0);
  });

  it("all items have an icon (non-null)", () => {
    const bad: string[] = [];
    for (const group of NAV_GROUPS) {
      for (const item of group.items) {
        if (!item.icon) {
          bad.push(`${group.label} → href=${item.href}`);
        }
      }
    }
    expect(bad, `items without icon: ${bad.join("; ")}`).toHaveLength(0);
  });

  it("no duplicate group labels", () => {
    const seen = new Set<string>();
    const dups: string[] = [];
    for (const group of NAV_GROUPS) {
      const key = group.label ?? "";
      if (seen.has(key)) dups.push(key);
      seen.add(key);
    }
    expect(dups, `duplicate group labels: ${dups.join(", ")}`).toHaveLength(0);
  });

  it("no duplicate hrefs across all groups", () => {
    const seen = new Set<string>();
    const dups: string[] = [];
    for (const group of NAV_GROUPS) {
      for (const item of group.items) {
        if (seen.has(item.href)) dups.push(item.href);
        seen.add(item.href);
      }
    }
    expect(dups, `duplicate hrefs: ${dups.join(", ")}`).toHaveLength(0);
  });
});
