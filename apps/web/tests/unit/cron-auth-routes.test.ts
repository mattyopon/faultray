/**
 * L2 Regression: both cron routes must authenticate via verifyCronAuth.
 *
 * /api/cron/trial-reminders already used the shared verifyCronAuth helper
 * (constant-time secret comparison + optional CRON_ALLOWED_IPS), but
 * /api/cron/trial-expiry hand-rolled an inline `authHeader !== \`Bearer
 * ${secret}\`` check — timing-variable and blind to the IP allowlist. This
 * test asserts every cron route delegates to verifyCronAuth and that none
 * reintroduces an inline Bearer comparison.
 */
import { describe, it, expect } from "vitest";
import { readFileSync, readdirSync } from "node:fs";
import { resolve } from "node:path";

const CRON_DIR = resolve(__dirname, "../../src/app/api/cron");

function cronRouteFiles(): string[] {
  return readdirSync(CRON_DIR, { withFileTypes: true })
    .filter((d) => d.isDirectory())
    .map((d) => resolve(CRON_DIR, d.name, "route.ts"));
}

describe("L2: cron route authentication", () => {
  it("discovers at least the two known cron routes", () => {
    expect(cronRouteFiles().length).toBeGreaterThanOrEqual(2);
  });

  for (const file of cronRouteFiles()) {
    const name = file.split("/").slice(-2, -1)[0];

    it(`${name}: authenticates via verifyCronAuth`, () => {
      const src = readFileSync(file, "utf-8");
      expect(src).toMatch(/verifyCronAuth\s*\(/);
    });

    it(`${name}: has no inline Bearer-secret comparison`, () => {
      const src = readFileSync(file, "utf-8");
      // The replaced anti-pattern: comparing the Authorization header to a
      // `Bearer ${CRON_SECRET}` template literal in route code.
      expect(src).not.toMatch(/Bearer \$\{[^}]*[Ss]ecret/);
    });
  }
});
