// Single source of truth for the public (no-auth) marketing / legal pages.
//
// Imported by BOTH:
//   - src/proxy.ts          — locale-redirect skip + route classification
//   - src/app/layout.tsx    — the pre-hydration theme script, which must NOT
//                             flip these marketing pages to the dark "app" theme
//
// Keep these two consumers in sync via this constant. The layout previously kept
// its own hand-edited copy that drifted out of date (it omitted the /zh /ko /es
// /pt locale roots and /service-level-agreement), which force-darkened those
// public pages and triggered a client/server hydration mismatch. Driving both
// from one list prevents that class of bug.
//
// Matching is prefix-based (startsWith) at the call sites, so "/security" would
// also cover "/security-checklist" — list only the canonical roots here.
export const PUBLIC_PAGES = [
  // Legal / public pages (no locale prefix)
  "/tokushoho", "/dpa", "/privacy", "/terms", "/service-level-agreement",
  "/contact", "/features", "/pricing", "/demo",
  "/status", "/support", "/help", "/changelog", "/ringi", "/case-studies",
  "/evidence-sprint",
] as const;

// Segment-boundary check (exact path or a "/"-delimited child) used where a
// public page must take precedence over the prefix-based APP_ROUTES protection
// in src/proxy.ts: "/evidence-sprint" is public even though it shares the
// "/evidence" prefix with a protected app route. Boundary matching keeps the
// precedence narrow — "/evidence" itself and "/evidence/..." stay protected.
export function isPublicPage(path: string): boolean {
  return PUBLIC_PAGES.some((p) => path === p || path.startsWith(p + "/"));
}
