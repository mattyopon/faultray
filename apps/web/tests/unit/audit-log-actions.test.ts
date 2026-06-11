/**
 * L2 Regression: audit-log API whitelist must match the DB CHECK constraint.
 *
 * The POST /api/audit-log whitelist (ALLOWED_ACTIONS) used to contain
 * lowercase dotted values ("simulation.run", "task.create", …) while the
 * CHECK constraint on audit_logs.action (migration 011) only accepts
 * uppercase values ('SIMULATION_RUN', …). Every insert that passed the API
 * whitelist was then rejected by Postgres, turning the endpoint into a
 * guaranteed 500. This test parses both sources and asserts the API set is
 * a subset of the DB set so they cannot silently drift again.
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const ROUTE_PATH = resolve(__dirname, "../../src/app/api/audit-log/route.ts");
const MIGRATION_PATH = resolve(
  __dirname,
  "../../supabase/migrations/011_audit_logs.sql"
);

function apiActions(): string[] {
  const src = readFileSync(ROUTE_PATH, "utf-8");
  const block = src.match(/ALLOWED_ACTIONS = new Set\(\[([\s\S]*?)\]\)/);
  if (!block) throw new Error("ALLOWED_ACTIONS set not found in route.ts");
  return [...block[1].matchAll(/"([^"]+)"/g)].map((m) => m[1]);
}

function dbActions(): string[] {
  const sql = readFileSync(MIGRATION_PATH, "utf-8");
  const block = sql.match(/action text NOT NULL CHECK \(action IN \(([\s\S]*?)\)\)/);
  if (!block) throw new Error("action CHECK constraint not found in migration 011");
  return [...block[1].matchAll(/'([^']+)'/g)].map((m) => m[1]);
}

describe("L2: audit-log action whitelist vs DB constraint", () => {
  it("parses a non-empty whitelist from both sources", () => {
    expect(apiActions().length).toBeGreaterThan(0);
    expect(dbActions().length).toBeGreaterThan(0);
  });

  it("every API-allowed action is accepted by the DB CHECK constraint", () => {
    const db = new Set(dbActions());
    const rejected = apiActions().filter((a) => !db.has(a));
    expect(
      rejected,
      `actions allowed by the API but rejected by audit_logs.action CHECK: ${rejected.join(", ")}`
    ).toHaveLength(0);
  });
});
