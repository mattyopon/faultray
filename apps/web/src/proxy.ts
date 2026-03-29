import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

const locales = ["en", "ja", "de", "fr"];
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

export async function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Check if the pathname already has a locale prefix
  const pathnameHasLocale = locales.some(
    (locale) => pathname.startsWith(`/${locale}/`) || pathname === `/${locale}`
  );

  // If no locale in path, redirect to preferred locale
  // Only for the root and LP-related paths
  if (!pathnameHasLocale) {
    // Skip locale redirect for app routes (dashboard, login, etc.), API, auth
    const skipPaths = ["/dashboard", "/simulate", "/results", "/suggestions", "/settings", "/login", "/auth", "/api", "/pricing"];
    const shouldSkip = skipPaths.some((path) => pathname.startsWith(path));

    if (!shouldSkip) {
      const locale = getPreferredLocale(request);
      const url = request.nextUrl.clone();
      url.pathname = `/${locale}${pathname}`;
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

  const protectedPaths = ["/dashboard", "/simulate", "/results", "/suggestions", "/settings"];
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
