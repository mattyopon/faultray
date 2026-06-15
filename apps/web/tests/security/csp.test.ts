/**
 * L8: Security — Content Security Policy
 * Verifies that next.config.ts includes proper security headers.
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import path from "path";

const configPath = path.resolve(__dirname, "../../next.config.ts");

describe("L8: Content Security Policy", () => {
  const configContent = readFileSync(configPath, "utf-8");

  it("sets X-Frame-Options header", () => {
    expect(configContent).toContain("X-Frame-Options");
    expect(configContent).toContain("DENY");
  });

  it("sets X-Content-Type-Options header", () => {
    expect(configContent).toContain("X-Content-Type-Options");
    expect(configContent).toContain("nosniff");
  });

  it("sets Referrer-Policy header", () => {
    expect(configContent).toContain("Referrer-Policy");
    expect(configContent).toContain("strict-origin-when-cross-origin");
  });

  it("sets Content-Security-Policy with frame-ancestors", () => {
    expect(configContent).toContain("Content-Security-Policy");
    expect(configContent).toContain("frame-ancestors 'none'");
  });

  it("sets Cross-Origin-Opener-Policy as same-origin-allow-popups (ZAP #172)", () => {
    // allow-popups preserves OAuth popup logins; bare same-origin would break them.
    expect(configContent).toContain("Cross-Origin-Opener-Policy");
    expect(configContent).toContain("same-origin-allow-popups");
  });

  it("does NOT enable Cross-Origin-Embedder-Policy / require-corp (deferred, ZAP #172)", () => {
    // COEP would force CORP opt-in on every cross-origin resource and break the app.
    // Assert it is not set as a response header KEY. (The deferral rationale in
    // next.config.ts mentions "require-corp" in a comment, so don't grep raw text.)
    expect(configContent).not.toMatch(/key:\s*["']Cross-Origin-Embedder-Policy["']/);
  });

  it("applies headers to all routes", () => {
    // The source pattern should cover all routes
    expect(configContent).toMatch(/source:\s*["']\/(.*?)["']/);
  });
});
