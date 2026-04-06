import { type NextRequest } from "next/server";
import { updateSession } from "@/lib/supabase/middleware";

/**
 * Next.js Middleware — 全リクエストで Supabase セッションを更新し、
 * 保護ルートへの未認証アクセスを /login にリダイレクトする。
 */
export async function middleware(request: NextRequest) {
  return await updateSession(request);
}

export const config = {
  matcher: [
    /*
     * 以下を除く全パスにマッチ:
     * - _next/static (静的ファイル)
     * - _next/image  (画像最適化)
     * - favicon.ico, sitemap.xml, robots.txt
     * - 拡張子付きの静的アセット
     */
    "/((?!_next/static|_next/image|favicon.ico|sitemap.xml|robots.txt|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico|css|js)$).*)",
  ],
};
