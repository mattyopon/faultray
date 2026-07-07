// @vitest-environment node
/**
 * Route protection classification in src/proxy.ts.
 *
 * Regression for the /evidence-sprint funnel outage: APP_ROUTES matching is
 * prefix-based (startsWith), so the public "/evidence-sprint" offer page
 * matched the protected "/evidence" app route and every unauthenticated
 * visitor — i.e. the entire hero-CTA funnel — was redirected to /login.
 * Public pages must take precedence over the prefix match, WITHOUT loosening
 * it: "/security-checklist" is intentionally covered by the "/security"
 * prefix, and "/evidence" itself stays protected.
 *
 * Drives the real proxy() with an unauthenticated Supabase client (mocked at
 * the module boundary) so the assertions cover the actual redirect behavior,
 * not a re-implementation of the matching rules.
 */
import { describe, it, expect, vi, beforeAll } from "vitest";
import { NextRequest } from "next/server";
import { proxy } from "../../src/proxy";
import { PUBLIC_PAGES, isPublicPage } from "../../src/lib/public-routes";

vi.mock("@supabase/ssr", () => ({
  // Unauthenticated session: getUser resolves with no user and no error.
  createServerClient: () => ({
    auth: {
      getUser: async () => ({ data: { user: null }, error: null }),
    },
  }),
}));

beforeAll(() => {
  process.env.NEXT_PUBLIC_SUPABASE_URL = "https://stub.supabase.co";
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = "stub-anon-key";
  delete process.env.ALLOWED_IPS;
});

const run = (path: string) =>
  proxy(new NextRequest(`https://faultray.com${path}`));

const loginRedirect = (res: Response): string | null => {
  const location = res.headers.get("location");
  if (!location) return null;
  return new URL(location).pathname === "/login" ? location : null;
};

describe("proxy route protection (unauthenticated)", () => {
  it("serves /evidence-sprint publicly despite the protected /evidence prefix", async () => {
    const res = await run("/evidence-sprint");
    expect(loginRedirect(res)).toBeNull();
    expect(res.status).toBe(200);
  });

  it("still requires auth for /evidence and its children", async () => {
    for (const path of ["/evidence", "/evidence/packs"]) {
      const res = await run(path);
      const redirect = loginRedirect(res);
      expect(redirect, `${path} must redirect to /login`).not.toBeNull();
      expect(redirect).toContain(`redirectTo=${encodeURIComponent(path)}`);
    }
  });

  it("keeps the intentional prefix coverage: /security-checklist stays protected", async () => {
    const res = await run("/security-checklist");
    expect(loginRedirect(res)).not.toBeNull();
  });

  it("redirects locale-prefixed /ja/evidence-sprint to the canonical public page", async () => {
    const res = await run("/ja/evidence-sprint");
    const location = res.headers.get("location");
    expect(location).not.toBeNull();
    expect(new URL(location!).pathname).toBe("/evidence-sprint");
    expect(res.headers.get("set-cookie")).toContain("NEXT_LOCALE=ja");
  });

  it("keeps every PUBLIC_PAGES entry out of the login wall", async () => {
    for (const page of PUBLIC_PAGES) {
      const res = await run(page);
      expect(loginRedirect(res), `${page} must not redirect to /login`).toBeNull();
    }
  });

  it("isPublicPage matches on segment boundaries only", () => {
    expect(isPublicPage("/evidence-sprint")).toBe(true);
    expect(isPublicPage("/evidence-sprint/details")).toBe(true);
    expect(isPublicPage("/evidence")).toBe(false);
    expect(isPublicPage("/evidence-sprintx")).toBe(false);
    expect(isPublicPage("/dashboard")).toBe(false);
  });
});

describe("public page discoverability (robots / sitemap)", () => {
  // robots.txt semantics: the longest matching rule wins; Allow wins ties.
  // "/evidence-sprint" was crawl-blocked by the prefix-matched "/evidence"
  // disallow until an explicit Allow carve-out was added — assert the
  // longest-match outcome for EVERY public page so a future public route
  // shadowed by an app-path disallow prefix fails here instead of shipping.
  const crawlAllowed = (
    path: string,
    allow: string[],
    disallow: string[]
  ): boolean => {
    const longest = (rules: string[]) =>
      rules.reduce((n, r) => (path.startsWith(r) ? Math.max(n, r.length) : n), 0);
    return longest(allow) >= longest(disallow);
  };

  it("robots longest-match allows every PUBLIC_PAGES entry", async () => {
    const robots = (await import("../../src/app/robots")).default();
    const rule = Array.isArray(robots.rules) ? robots.rules[0] : robots.rules;
    const allow = [rule.allow].flat().filter((r): r is string => !!r);
    const disallow = [rule.disallow].flat().filter((r): r is string => !!r);
    for (const page of PUBLIC_PAGES) {
      expect(
        crawlAllowed(page, allow, disallow),
        `${page} must be crawlable (add an Allow carve-out if an app-path disallow prefix shadows it)`
      ).toBe(true);
    }
  });

  it("sitemap lists the /evidence-sprint offer page", async () => {
    const sitemap = (await import("../../src/app/sitemap")).default();
    const urls = sitemap.map((e) => new URL(e.url).pathname);
    expect(urls).toContain("/evidence-sprint");
  });
});
