import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

const locales = ["en", "ja", "de", "fr", "zh", "ko", "es", "pt"];
const defaultLocale = "en";

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

  const forwardedFor = request.headers.get("x-forwarded-for");
  const clientIp = forwardedFor ? forwardedFor.split(",")[0].trim() : "";

  const allowed = allowedIps.split(",").map((ip) => ip.trim());
  return allowed.includes(clientIp);
}

const MAX_BODY_SIZE = 1 * 1024 * 1024; // 1MB

export async function proxy(request: NextRequest) {
  // Staging IP restriction
  if (!isAllowedIp(request)) {
    return new NextResponse("Forbidden", { status: 403 });
  }

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
      // Legal / public pages (no locale prefix)
      "/tokushoho", "/dpa", "/privacy", "/terms", "/service-level-agreement",
      "/contact", "/features", "/pricing", "/demo",
      "/status", "/support", "/help", "/changelog", "/ringi", "/case-studies",
      // Auth / API
      "/login", "/auth", "/api",
      // App routes (authenticated)
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
    const appPaths = [
      // Legal / public pages
      "/tokushoho", "/dpa", "/privacy", "/terms", "/service-level-agreement",
      "/contact", "/features", "/pricing", "/demo",
      "/status", "/support", "/help", "/changelog", "/ringi", "/case-studies",
      // Auth
      "/login",
      // App routes
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
    return NextResponse.next();
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

  const {
    data: { user },
  } = await supabase.auth.getUser();

  // Strip locale prefix for protected path check
  let pathForCheck = pathname;
  for (const locale of locales) {
    if (pathname.startsWith(`/${locale}/`)) {
      pathForCheck = pathname.slice(locale.length + 1);
      break;
    }
  }

  const protectedPaths = [
    "/dashboard", "/simulate", "/results", "/suggestions", "/settings",
    "/dora", "/topology", "/teams", "/remediation", "/projects",
    "/heatmap", "/whatif", "/compliance", "/score-detail",
    "/cost", "/security", "/fmea", "/advisor", "/reports",
    "/incidents", "/benchmark", "/evidence", "/apm",
    "/governance", "/sla", "/runbooks", "/postmortems",
    "/supply-chain", "/drift", "/calendar", "/timeline",
    "/env-compare", "/canary", "/optimize", "/iac", "/onboarding",
    "/templates", "/ipo-readiness", "/traces", "/logs",
    "/dependencies", "/gameday", "/ai-reliability", "/fisc",
    "/audit-report", "/traffic-light", "/people-risk",
    "/shadow-it", "/bus-factor", "/vuln-priority", "/external-impact",
    "/sla-budget", "/compliance-report", "/topology-map",
  ];
  const isProtected = protectedPaths.some((path) =>
    pathForCheck.startsWith(path)
  );

  if (isProtected && !user) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.searchParams.set("redirectTo", request.nextUrl.pathname);
    return NextResponse.redirect(url);
  }

  return supabaseResponse;
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};
