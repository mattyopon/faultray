/**
 * L5: Quality — Build verification
 * Verifies that `next build` succeeds.
 * This test is slow (~30s+), so it is separated from unit tests.
 */
import { describe, it, expect } from "vitest";
import { execSync } from "child_process";
import path from "path";

const ROOT = path.resolve(__dirname, "../..");

describe("L5: Build Quality", () => {
  it("next build completes successfully", { timeout: 180_000 }, () => {
    expect(() => {
      execSync("npx next build", {
        cwd: ROOT,
        stdio: "pipe",
        timeout: 180_000,
        env: {
          ...process.env,
          // Provide dummy Supabase env vars for build
          NEXT_PUBLIC_SUPABASE_URL: process.env.NEXT_PUBLIC_SUPABASE_URL || "https://placeholder.supabase.co",
          NEXT_PUBLIC_SUPABASE_ANON_KEY: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || "placeholder-key",
        },
      });
    }).not.toThrow();
  });
});
