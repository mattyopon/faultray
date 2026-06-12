/**
 * L2 Regression: Codex-audit correctness fixes (#113, #115, #120, #121, #122).
 *
 * These are source-scan assertions in the same style as the audit-log and
 * stripe-webhook regression tests: they pin the corrected shape so a later
 * edit can't silently revert it, without standing up a Supabase mock.
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const SRC = resolve(__dirname, "../..");
const read = (p: string) => readFileSync(resolve(SRC, p), "utf-8");

describe("#113: CSRF guard fails closed in production", () => {
  const src = read("src/lib/api-auth.ts");

  it("returns 403 from the empty-allowlist branch when in production", () => {
    // The empty-allowlist block must gate on isProduction and 403, not just
    // `return null` unconditionally.
    const block = src.match(/if \(allowed\.size === 0\)\s*\{[\s\S]*?\n  \}/);
    expect(block, "allowed.size === 0 block not found").toBeTruthy();
    expect(block![0]).toMatch(/isProduction/);
    expect(block![0]).toMatch(/status:\s*403/);
  });

  it("does not unconditionally fail open on an empty allowlist", () => {
    // Guard against regressing to a bare `return null` as the only action.
    const block = src.match(/if \(allowed\.size === 0\)\s*\{[\s\S]*?\n  \}/)![0];
    const lines = block.split("\n").map((l) => l.trim());
    const idx = lines.findIndex((l) => l.startsWith("if (allowed.size === 0)"));
    // The statement immediately inside the block must not be `return null;`.
    expect(lines[idx + 1]).not.toBe("return null;");
  });
});

describe("#115: trial-reminders targets unconverted trialers, not plan=free", () => {
  const src = read("src/app/api/cron/trial-reminders/route.ts");

  it("filters on a null stripe_customer_id", () => {
    expect(src).toMatch(/\.is\(\s*["']stripe_customer_id["']\s*,\s*null\s*\)/);
  });

  it("no longer filters the population by plan='free'", () => {
    expect(src).not.toMatch(/\.eq\(\s*["']plan["']\s*,\s*["']free["']\s*\)/);
  });
});

describe("#120/#121: deterministic org selection", () => {
  it("org/members orders both membership and ownership queries", () => {
    const src = read("src/app/api/org/members/route.ts");
    expect(src).toMatch(/\.order\(\s*["']invited_at["']/);
    expect(src).toMatch(/\.order\(\s*["']created_at["']/);
  });

  it("tasks getOrgId orders both membership and ownership queries", () => {
    const src = read("src/app/api/tasks/route.ts");
    expect(src).toMatch(/\.order\(\s*["']invited_at["']/);
    expect(src).toMatch(/\.order\(\s*["']created_at["']/);
  });
});

describe("#122: tasks/[id] distinguishes query failure from missing row", () => {
  const src = read("src/app/api/tasks/[id]/route.ts");

  it("uses maybeSingle for the existence lookup and surfaces DB errors as 500", () => {
    expect(src).toMatch(/existingError/);
    // The 500 branch text appears once per handler (PATCH + DELETE).
    const matches = src.match(/Failed to look up task/g) ?? [];
    expect(matches.length).toBe(2);
  });

  it("existence lookup no longer uses .single() (which 404s on any error)", () => {
    // The existence query selects "id, org_id"; assert that specific query
    // resolves via maybeSingle, not single.
    expect(src).toMatch(/\.select\("id, org_id"\)[\s\S]*?\.maybeSingle\(\)/);
  });
});
