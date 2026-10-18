/**
 * L3 Integration: prove the TypeScript audit-log vocabulary and the Postgres
 * CHECK constraint declared in migration 019 stay in lockstep.
 *
 * Closes #111: previously the route accepted dotted lowercase names while the
 * DB only allowed uppercase underscore names, so every authenticated POST
 * crashed at the constraint. This test fails loudly if anyone touches one
 * side without the other.
 */
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { AUDIT_LOG_ACTIONS } from "@/lib/audit-log-actions";

const MIGRATION_019 = resolve(
  __dirname,
  "../../supabase/migrations/019_audit_log_insert_and_vocabulary.sql"
);

function parseCheckActions(sql: string): string[] {
  const match = sql.match(
    /ADD CONSTRAINT audit_logs_action_check[\s\S]*?CHECK \(action IN \(([\s\S]*?)\)\);/
  );
  if (!match) {
    throw new Error("Could not locate audit_logs_action_check in migration 019");
  }
  return Array.from(match[1].matchAll(/'([A-Z_]+)'/g)).map((m) => m[1]);
}

describe("audit-log action vocabulary", () => {
  it("TypeScript constant matches migration 019 CHECK constraint exactly", () => {
    const sql = readFileSync(MIGRATION_019, "utf-8");
    const sqlActions = parseCheckActions(sql);
    expect(new Set(sqlActions)).toEqual(new Set(AUDIT_LOG_ACTIONS));
  });

  it("does not regress to the dotted lowercase names that triggered #111", () => {
    for (const action of AUDIT_LOG_ACTIONS) {
      expect(action).toMatch(/^[A-Z][A-Z_]*$/);
    }
  });
});
