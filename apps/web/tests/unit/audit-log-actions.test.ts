/**
 * L2 Regression: audit-log vocabulary wiring and migration continuity.
 *
 * The POST /api/audit-log whitelist used to contain lowercase dotted values
 * ("simulation.run", …) while the DB CHECK on audit_logs.action only accepts
 * uppercase values, turning every insert into a guaranteed 500. The canonical
 * vocabulary now lives in src/lib/audit-log-actions.ts; the integration test
 * (tests/integration/audit-log-vocabulary.test.ts) proves it matches the
 * migration-019 CHECK. This file covers the two gaps that test leaves open:
 *
 *  1. route.ts must actually USE the canonical set — an inline list could
 *     drift from the constraint while the integration test stays green.
 *  2. Migration 019 replaces the 011 CHECK, so 019's vocabulary must remain
 *     a superset of 011's — otherwise rows written under the old constraint
 *     would violate the new one and the ALTER would fail on deploy.
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { AUDIT_LOG_ACTIONS } from "@/lib/audit-log-actions";

const ROUTE_PATH = resolve(__dirname, "../../src/app/api/audit-log/route.ts");
const MIGRATION_011 = resolve(
  __dirname,
  "../../supabase/migrations/011_audit_logs.sql"
);

function legacyDbActions(): string[] {
  const sql = readFileSync(MIGRATION_011, "utf-8");
  const block = sql.match(/action text NOT NULL CHECK \(action IN \(([\s\S]*?)\)\)/);
  if (!block) throw new Error("action CHECK constraint not found in migration 011");
  return [...block[1].matchAll(/'([^']+)'/g)].map((m) => m[1]);
}

describe("L2: audit-log action vocabulary wiring", () => {
  it("route.ts wires ALLOWED_ACTIONS to the canonical AUDIT_LOG_ACTION_SET", () => {
    const src = readFileSync(ROUTE_PATH, "utf-8");
    expect(src).toMatch(
      /import \{ AUDIT_LOG_ACTION_SET \} from "@\/lib\/audit-log-actions"/
    );
    expect(src).toMatch(/const ALLOWED_ACTIONS = AUDIT_LOG_ACTION_SET;/);
    // No parallel inline vocabulary that could drift from the canonical set.
    expect(src).not.toMatch(/ALLOWED_ACTIONS = new Set\(\[/);
  });

  it("canonical vocabulary keeps every action from the legacy 011 constraint", () => {
    const canonical = new Set<string>(AUDIT_LOG_ACTIONS);
    const dropped = legacyDbActions().filter((a) => !canonical.has(a));
    expect(
      dropped,
      `actions valid under migration 011 but missing from the canonical set ` +
        `(existing rows would violate the migration-019 CHECK): ${dropped.join(", ")}`
    ).toHaveLength(0);
  });
});
