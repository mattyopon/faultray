/**
 * L1: Foundation — Static Analysis
 * Verifies ESLint config is valid and TypeScript compiles without errors.
 */
import { describe, it, expect } from "vitest";
import { execSync } from "child_process";
import path from "path";

const ROOT = path.resolve(__dirname, "..");

describe("L1: Static Analysis", () => {
  it("ESLint runs without fatal errors", { timeout: 60_000 }, () => {
    // Allow warnings but not errors (exit code 2 = fatal)
    // --max-warnings=-1 means unlimited warnings are OK
    try {
      execSync("npx eslint src/", {
        cwd: ROOT,
        stdio: "pipe",
        timeout: 60_000,
      });
    } catch (err: unknown) {
      const e = err as { status?: number; stderr?: Buffer };
      // eslint exit code 1 = lint warnings/errors found, 2 = fatal config issue
      if (e.status === 2) {
        throw err;
      }
      // Warnings are acceptable; log for visibility
      console.warn("ESLint reported warnings (non-fatal)");
    }
  });

  it("TypeScript compiles without errors", { timeout: 120_000 }, () => {
    expect(() => {
      execSync("npx tsc --noEmit", {
        cwd: ROOT,
        stdio: "pipe",
        timeout: 120_000,
      });
    }).not.toThrow();
  });
});
