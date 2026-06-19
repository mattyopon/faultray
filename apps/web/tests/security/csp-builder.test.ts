/**
 * #85 / ZAP mattyopon/faultray#172 — Content-Security-Policy builder.
 *
 * Verifies the two modes of src/lib/csp.ts:
 *   - default (non-strict): historical 'unsafe-inline' policy, unchanged.
 *   - strict + nonce: 'unsafe-inline' removed from script-src (nonce +
 *     strict-dynamic) and style-src (nonce), with inline style *attributes*
 *     still permitted via style-src-attr.
 */
import { describe, it, expect } from "vitest";
import { buildCsp, cspStrictEnabled } from "../../src/lib/csp";

const SUPA = "https://proj.supabase.co";

describe("cspStrictEnabled — strict is the default (#85)", () => {
  it("is on when the flag is unset", () => {
    expect(cspStrictEnabled({})).toBe(true);
  });

  it("is on for any value other than '0'", () => {
    expect(cspStrictEnabled({ FAULTRAY_CSP_STRICT: "1" })).toBe(true);
    expect(cspStrictEnabled({ FAULTRAY_CSP_STRICT: "true" })).toBe(true);
  });

  it("is the ONLY off switch: FAULTRAY_CSP_STRICT='0' (rollback hatch)", () => {
    expect(cspStrictEnabled({ FAULTRAY_CSP_STRICT: "0" })).toBe(false);
  });
});

describe("buildCsp — default (non-strict) policy", () => {
  const csp = buildCsp({ strict: false, isDev: false, supabaseOrigin: SUPA });

  it("keeps 'unsafe-inline' on script-src and style-src (historical policy)", () => {
    expect(csp).toContain("script-src 'self' 'unsafe-inline'");
    expect(csp).toContain("style-src 'self' 'unsafe-inline'");
  });

  it("does not use a nonce or strict-dynamic", () => {
    expect(csp).not.toContain("nonce-");
    expect(csp).not.toContain("strict-dynamic");
  });

  it("retains the clickjacking + base-uri + form-action guards", () => {
    expect(csp).toContain("frame-ancestors 'none'");
    expect(csp).toContain("base-uri 'self'");
    expect(csp).toContain("form-action 'self'");
  });

  it("includes the Supabase origin in connect-src and the third-party hosts", () => {
    expect(csp).toContain(`connect-src 'self' ${SUPA}`);
    expect(csp).toContain("https://js.stripe.com");
    expect(csp).toContain("https://www.googletagmanager.com");
  });

  it("ignores the nonce / dev flags when not strict", () => {
    const a = buildCsp({ strict: false, isDev: true, supabaseOrigin: SUPA, nonce: "abc" });
    expect(a).not.toContain("nonce-");
    expect(a).not.toContain("'unsafe-eval'");
  });
});

describe("buildCsp — strict (nonce-based) policy", () => {
  const nonce = "TESTNONCE123";
  const csp = buildCsp({ strict: true, isDev: false, supabaseOrigin: SUPA, nonce });

  it("removes 'unsafe-inline' from script-src and uses nonce + strict-dynamic", () => {
    const scriptSrc = csp.split("; ").find((d) => d.startsWith("script-src"))!;
    expect(scriptSrc).toContain(`'nonce-${nonce}'`);
    expect(scriptSrc).toContain("'strict-dynamic'");
    expect(scriptSrc).not.toContain("'unsafe-inline'");
  });

  it("removes 'unsafe-inline' from style-src (element) and uses a nonce", () => {
    const styleSrc = csp.split("; ").find((d) => d.startsWith("style-src ") || d === "style-src")!;
    expect(styleSrc).toContain(`'nonce-${nonce}'`);
    expect(styleSrc).not.toContain("'unsafe-inline'");
  });

  it("permits inline style ATTRIBUTES via style-src-attr (React style={{…}})", () => {
    expect(csp).toContain("style-src-attr 'unsafe-inline'");
  });

  it("adds object-src 'none' and keeps the other guards", () => {
    expect(csp).toContain("object-src 'none'");
    expect(csp).toContain("frame-ancestors 'none'");
    expect(csp).toContain("upgrade-insecure-requests");
  });

  it("keeps the third-party script hosts as a CSP2 fallback", () => {
    const scriptSrc = csp.split("; ").find((d) => d.startsWith("script-src"))!;
    expect(scriptSrc).toContain("https://js.stripe.com");
    expect(scriptSrc).toContain("https://static.hotjar.com");
  });

  it("adds 'unsafe-eval' to script-src in development only", () => {
    const dev = buildCsp({ strict: true, isDev: true, supabaseOrigin: SUPA, nonce });
    expect(dev.split("; ").find((d) => d.startsWith("script-src"))).toContain("'unsafe-eval'");
    expect(csp.split("; ").find((d) => d.startsWith("script-src"))).not.toContain("'unsafe-eval'");
  });

  it("falls back to the non-strict policy when strict is set without a nonce", () => {
    const noNonce = buildCsp({ strict: true, isDev: false, supabaseOrigin: SUPA });
    expect(noNonce).toContain("script-src 'self' 'unsafe-inline'");
    expect(noNonce).not.toContain("strict-dynamic");
  });
});
