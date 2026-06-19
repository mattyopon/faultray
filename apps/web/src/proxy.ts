import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";
import { buildCsp, cspStrictEnabled } from "@/lib/csp";

const locales = ["en", "ja", "de", "fr", "zh", "ko", "es", "pt"];
const defaultLocale = "en";

// Single source of truth for route classification. Every app route MUST be
// listed here: a route missing from this list gets locale-prefixed by the
// landing redirect below (e.g. /admin → /en/admin) and 404s, because only
// the marketing landing pages exist under /{locale}.
// Matching is prefix-based (startsWith), so "/security" also covers
// "/security-checklist".
const PUBLIC_PAGES = [
  // Legal / public pages (no locale prefix)
  "/tokushoho", "/dpa", "/privacy", "/terms", "/service-level-agreement",
  "/contact", "/features", "/pricing", "/demo",
  "/status", "/support", "/help", "/changelog", "/ringi", "/case-studies",
];

// Authenticated app routes — also the auth-protection list.
const APP_ROUTES = [
  "/admin", "/audit-log",
  "/dashboard", "/simulate", "/results", "/suggestions", "/settings",
  "/topology", "/heatmap", "/whatif", "/compliance", "/score-detail",
  "/cost", "/security", "/fmea", "/advisor", "/reports",
  "/incidents", "/benchmark", "/remediation",
  "/evidence", "/apm", "/projects",
  "/dora", "/governance", "/sla",
  "/runbooks", "/postmortems", "/supply-chain", "/drift", "/calendar",
  "/timeline", "/teams", "/env-compare", "/canary", "/optimize",
  "/iac", "/onboarding", "/templates", "/ipo-readiness",
  "/traces", "/logs", "/dependencies", "/gameday",
  "/ai-reliability", "/fisc", "/audit-report", "/traffic-light",
  "/people-risk",
  "/shadow-it", "/bus-factor", "/vuln-priority", "/external-impact",
  "/sla-budget", "/compliance-report", "/topology-map",
];

function getPreferredLocale(request: NextRequest): string {
  // Check cookie first
  const cookieLocale = request.cookies.get("NEXT_LOCALE")?.value;
  if (cookieLocale && locales.includes(cookieLocale)) {
    return cookieLocale;
  }

  // Parse Accept-Language header
  const acceptLanguage = request.headers.get("accept-language");
  if (acceptLanguage) {
    const preferred = acceptLanguage
      .split(",")
      .map((part) => {
        const [lang, q] = part.trim().split(";q=");
        return { lang: lang.trim().toLowerCase(), q: q ? parseFloat(q) : 1 };
      })
      .sort((a, b) => b.q - a.q);

    for (const { lang } of preferred) {
      // Exact match (e.g., "ja", "de", "fr")
      const exact = locales.find((l) => l === lang);
      if (exact) return exact;
      // Prefix match (e.g., "ja-JP" -> "ja", "de-DE" -> "de")
      const prefix = locales.find((l) => lang.startsWith(l + "-"));
      if (prefix) return prefix;
      // Reverse prefix match (e.g., "en" matches "en")
      const langBase = lang.split("-")[0];
      const baseMatch = locales.find((l) => l === langBase);
      if (baseMatch) return baseMatch;
    }
  }

  return defaultLocale;
}

function isAllowedIp(request: NextRequest): boolean {
  const allowedIps = process.env.ALLOWED_IPS;
  if (!allowedIps) return true; // No restriction if not configured

  const siteUrl = process.env.NEXT_PUBLIC_SITE_URL;
  if (siteUrl === "https://faultray.com") return true; // Production — no restriction

  // SEC: the leftmost `x-forwarded-for` value is client-controlled — a request
  // can send `X-Forwarded-For: <allowed-ip>` to bypass this allowlist. This app
  // is fronted by Vercel, which sets `x-real-ip` to the real peer address that
  // the client cannot override; prefer it (mirrors getClientIp in
  // src/lib/rate-limit.ts) and only fall back to the XFF leftmost when absent.
  const realIp = request.headers.get("x-real-ip")?.trim();
  const forwardedFor = request.headers.get("x-forwarded-for");
  const clientIp =
    realIp || (forwardedFor ? forwardedFor.split(",")[0].trim() : "");

  const allowed = allowedIps.split(",").map((ip) => ip.trim());
  return allowed.includes(clientIp);
}

const MAX_BODY_SIZE = 1 * 1024 * 1024; // 1MB

export async function proxy(request: NextRequest) {
  // Staging IP restriction
  if (!isAllowedIp(request)) {
    return new NextResponse("Forbidden", { status: 403 });
  }

  // #32 / #85 CSP nonce — generate a per-request nonce and own the
  // Content-Security-Policy header here (next.config.ts no longer sets it).
  // Docs: docs/csp-nonce-plan.md
  const _nonceBytes = new Uint8Array(16);
  crypto.getRandomValues(_nonceBytes);
  const nonce = Buffer.from(_nonceBytes).toString("base64");

  // Strict (nonce-based) CSP is the default (#85): it removes 'unsafe-inline'
  // from script-src/style-src. Setting FAULTRAY_CSP_STRICT=0 falls back to the
  // historical 'unsafe-inline' policy (and restores static rendering / CDN
  // caching) without a code change — an emergency rollback hatch only. See
  // docs/csp-nonce-plan.md.
  const strictCsp = cspStrictEnabled();
  const cspValue = buildCsp({
    strict: strictCsp,
    isDev: process.env.NODE_ENV === "development",
    supabaseOrigin: (process.env.NEXT_PUBLIC_SUPABASE_URL ?? "").replace(/\/$/, ""),
    nonce,
  });

  // Expose the nonce to the rendering layer so the root layout / <Script> tags
  // can stamp it on executable inline scripts. In strict mode also forward the
  // CSP on the *request* so Next.js auto-applies the nonce to its own framework
  // and inline scripts (it parses `'nonce-…'` out of the request CSP header).
  request.headers.set("x-faultray-nonce", nonce);
  if (strictCsp) {
    request.headers.set("content-security-policy", cspValue);
  }

  // Apply the response CSP to browser-facing document responses. Redirects and
  // the IP-block/oversize early returns don't carry a rendered document, so the
  // CSP is set on the pass-through / authenticated responses below.
  const withCsp = (res: NextResponse): NextResponse => {
    res.headers.set("Content-Security-Policy", cspValue);
    return res;
  };

  const { pathname } = request.nextUrl;

  // API-03: Reject oversized request bodies on API routes
  if (pathname.startsWith("/api/")) {
    const contentLength = request.headers.get("content-length");
    if (contentLength && parseInt(contentLength, 10) > MAX_BODY_SIZE) {
      return NextResponse.json(
        { error: "Request body too large. Maximum size is 1MB." },
        { status: 413 }
      );
    }
  }

  // Check if the pathname already has a locale prefix
  const pathnameHasLocale = locales.some(
    (locale) => pathname.startsWith(`/${locale}/`) || pathname === `/${locale}`
  );

  // If no locale in path, redirect to preferred locale
  // Only for the root and LP-related paths
  if (!pathnameHasLocale) {
    // Skip locale redirect for app routes (dashboard, login, etc.), API, auth
    const skipPaths = [
      // Static/SEO files
      "/robots.txt", "/sitemap.xml", "/manifest.webmanifest",
      ...PUBLIC_PAGES,
      // Auth / API
      "/login", "/auth", "/api",
      ...APP_ROUTES,
    ];
    const shouldSkip = skipPaths.some((path) => pathname.startsWith(path));

    if (!shouldSkip) {
      const locale = getPreferredLocale(request);
      const url = request.nextUrl.clone();
      url.pathname = `/${locale}${pathname}`;
      return NextResponse.redirect(url);
    }
  }

  // If locale-prefixed app route (e.g. /en/login, /ja/pricing), redirect to non-prefixed version
  if (pathnameHasLocale) {
    const appPaths = [...PUBLIC_PAGES, "/login", ...APP_ROUTES];
    let strippedPath = pathname;
    for (const locale of locales) {
      if (pathname.startsWith(`/${locale}/`)) {
        strippedPath = pathname.slice(locale.length + 1);
        break;
      }
    }
    if (appPaths.some((path) => strippedPath === path || strippedPath.startsWith(path + "/"))) {
      const url = request.nextUrl.clone();
      url.pathname = strippedPath;
      return NextResponse.redirect(url);
    }
  }

  // Supabase auth handling
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const supabaseKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  // If Supabase is not configured, pass through
  if (!supabaseUrl || !supabaseKey) {
    return withCsp(NextResponse.next({ request }));
  }

  let supabaseResponse = NextResponse.next({ request });

  const supabase = createServerClient(supabaseUrl, supabaseKey, {
    cookies: {
      getAll() {
        return request.cookies.getAll();
      },
      setAll(cookiesToSet) {
        cookiesToSet.forEach(({ name, value }) =>
          request.cookies.set(name, value)
        );
        supabaseResponse = NextResponse.next({ request });
        cookiesToSet.forEach(({ name, value, options }) =>
          supabaseResponse.cookies.set(name, value, options)
        );
      },
    },
  });

  // SEC: auth checks must fail closed. getUser() can throw or return an error
  // (network / JWT decode failures); a thrown error would otherwise crash the
  // proxy (500) and an error result must not be treated as "authenticated".
  let user = null;
  try {
    const { data, error } = await supabase.auth.getUser();
    if (!error) user = data.user;
  } catch {
    user = null;
  }

  // Strip locale prefix for protected path check
  let pathForCheck = pathname;
  for (const locale of locales) {
    if (pathname.startsWith(`/${locale}/`)) {
      pathForCheck = pathname.slice(locale.length + 1);
      break;
    }
  }

  const isProtected = APP_ROUTES.some((path) =>
    pathForCheck.startsWith(path)
  );

  if (isProtected && !user) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    // Preserve the original query string so e.g. /projects/123?tab=a returns to
    // the same view after login. The login/callback consumers validate this
    // value with isSafeInternalPath (src/lib/safe-redirect.ts), which permits
    // query strings, before using it.
    url.searchParams.set(
      "redirectTo",
      request.nextUrl.pathname + request.nextUrl.search
    );
    return NextResponse.redirect(url);
  }

  return withCsp(supabaseResponse);
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};
