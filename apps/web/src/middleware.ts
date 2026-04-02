import { NextResponse, type NextRequest } from "next/server";
import { updateSession } from "@/lib/supabase/middleware";

export async function middleware(request: NextRequest) {
  return await updateSession(request);
}

export const config = {
  matcher: [
    /*
     * Match all request paths except:
     * - _next/static, _next/image (Next.js internals)
     * - favicon.ico, icon.svg (static files)
     * - api/ routes
     * - Public assets
     */
    "/((?!_next/static|_next/image|favicon.ico|icon.svg|api/).*)",
  ],
};
