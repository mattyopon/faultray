import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

export async function updateSession(request: NextRequest) {
  let supabaseResponse = NextResponse.next({
    request,
  });

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value }) =>
            request.cookies.set(name, value)
          );
          supabaseResponse = NextResponse.next({
            request,
          });
          cookiesToSet.forEach(({ name, value, options }) =>
            supabaseResponse.cookies.set(name, value, options)
          );
        },
      },
    }
  );

  const {
    data: { user },
  } = await supabase.auth.getUser();

  // Protect dashboard routes
  const protectedPaths = [
    "/dashboard",
    "/simulate",
    "/results",
    "/suggestions",
    "/settings",
    "/admin",
    "/teams",
    "/reports",
    "/remediation",
    "/projects",
    "/ipo-readiness",
    "/governance",
    "/shadow-it",
    "/onboarding",
  ];
  const { pathname } = request.nextUrl;
  // Match on path-segment boundaries so e.g. "/admin" does not also protect
  // a distinct public route like "/admin-public" or "/admininfo".
  const isProtected = protectedPaths.some(
    (path) => pathname === path || pathname.startsWith(path + "/")
  );

  if (isProtected && !user) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    // Preserve the original query string so deep links survive the login
    // round-trip (e.g. /invite?token=abc, /dashboard?tab=billing).
    url.searchParams.set("redirectTo", pathname + request.nextUrl.search);
    return NextResponse.redirect(url);
  }

  return supabaseResponse;
}
