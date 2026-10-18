/**
 * L2 Regression: post-auth `redirectTo` validation (#26 + deep-link bugfix).
 *
 * The login page and OAuth callback now share one validator
 * (src/lib/safe-redirect → isSafeInternalPath). This test exercises the REAL
 * exported function (no source-string scraping / reimplemented copy), and locks
 * in both the open-redirect protections and the fix for dropped deep links:
 * valid internal paths like `/people-risk/actions` must be accepted (previously
 * the callback's narrow allow-list silently redirected them to /dashboard).
 */
import { describe, it, expect } from "vitest";
import { isSafeInternalPath } from "@/lib/safe-redirect";

describe("L2: isSafeInternalPath (shared post-auth redirect validator)", () => {
  it("rejects open-redirect, traversal and malformed values", () => {
    const bad: Array<string | null | undefined> = [
      "//evil.com",
      "///evil.com",
      "/\\evil.com",
      "\\\\evil.com",
      "https://evil.com",
      "http://evil.com",
      "javascript:alert(1)",
      "/dashboard/../admin", // traversal
      "/dashboard\\..\\admin",
      "/%2e%2e/admin", // percent-encoded traversal
      "/%2E%2E/admin", // percent-encoded traversal (upper)
      "/%252e%252e/admin", // double-encoded traversal
      "/%5Cevil.com", // percent-encoded backslash
      "/foo bar", // internal whitespace
      "/foo\tbar", // internal tab
      "/foo%", // malformed percent-encoding
      "", // empty
      " /dashboard", // leading whitespace
      "/dashboard ", // trailing whitespace
      "evil.com", // no leading slash
      null,
      undefined,
    ];
    for (const v of bad) {
      expect(isSafeInternalPath(v), `expected reject for ${JSON.stringify(v)}`).toBe(false);
    }
  });

  it("accepts same-origin internal paths, including deep links", () => {
    const good = [
      "/dashboard",
      "/dashboard/",
      "/dashboard/123",
      "/settings?tab=account",
      "/compliance#soc2",
      "/whatif",
      // deep links the old narrow allow-list dropped to /dashboard:
      "/people-risk/actions",
      "/people-risk/members/abc",
      "/teams",
      "/audit-log",
      // legitimate encoded space in a query value must still pass (the tightened
      // whitespace check only rejects RAW whitespace, not encoded):
      "/search?q=a%20b",
    ];
    for (const v of good) {
      expect(isSafeInternalPath(v), `expected accept for ${JSON.stringify(v)}`).toBe(true);
    }
  });
});
