import type { NextConfig } from "next";

// SEC-03: Build a strict Content-Security-Policy.
// Each source list is intentionally minimal — only domains actually loaded by the app.
//
// default-src 'self'            — fallback: block everything not listed below
// script-src                    — Next.js inline chunks + GA4 + Hotjar + Stripe
// style-src                     — Next.js injects inline <style> tags at runtime
// img-src                       — self, data URIs, OG images served via Vercel image optimizer,
//                                 Google/Hotjar tracking pixels
// font-src                      — Google Fonts static assets
// connect-src                   — Supabase API, GA4 collect, Hotjar ingestion, Stripe API
// frame-src                     — Stripe hosted fields run inside an iframe
// frame-ancestors 'none'        — prevent clickjacking (redundant with X-Frame-Options: DENY)
// base-uri 'self'               — prevent <base href> hijack
// form-action 'self'            — prevent form POST to attacker origin
// upgrade-insecure-requests     — force HTTPS for mixed-content resources
function buildCsp(): string {
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
  // Strip trailing slash for use as a CSP source
  const supabaseOrigin = supabaseUrl.replace(/\/$/, "");

  const directives: string[] = [
    "default-src 'self'",
    // TODO: nonce-based CSPに移行すべき。nonce-basedにすれば 'unsafe-inline' を除去できる。
    // ただし Next.js の静的エクスポートおよびインラインスクリプト注入との互換性のために
    // 現状は 'unsafe-inline' を維持している。移行にはカスタムサーバー or middleware での
    // nonce生成と、すべてのインライン <script> / <style> への nonce属性付与が必要。
    // 参照: https://nextjs.org/docs/app/building-your-application/configuring/content-security-policy
    "script-src 'self' 'unsafe-inline' https://www.googletagmanager.com https://static.hotjar.com https://script.hotjar.com https://js.stripe.com",
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "img-src 'self' data: blob: https://faultray.com https://www.google-analytics.com https://www.googletagmanager.com https://*.hotjar.com",
    "font-src 'self' https://fonts.gstatic.com",
    [
      "connect-src 'self'",
      supabaseOrigin,
      "https://www.google-analytics.com",
      "https://analytics.google.com",
      "https://stats.g.doubleclick.net",
      "https://*.hotjar.com",
      "https://*.hotjar.io",
      "wss://*.hotjar.com",
      "https://api.stripe.com",
    ]
      .filter(Boolean)
      .join(" "),
    "frame-src https://js.stripe.com https://hooks.stripe.com",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "upgrade-insecure-requests",
  ];

  return directives.join("; ");
}

const nextConfig: NextConfig = {
  // Optional Upstash backend for src/lib/rate-limit.ts: these packages are
  // intentionally NOT in package.json (operator installs them to opt in).
  // Keep them out of the server bundle so the dynamic import becomes a
  // runtime require (guarded by try/catch), and suppress the expected
  // module-not-found build warning when they are absent.
  serverExternalPackages: ["@upstash/ratelimit", "@upstash/redis"],
  turbopack: {
    ignoreIssue: [
      {
        path: "**/src/lib/rate-limit.ts",
        title: /Module not found/,
      },
    ],
  },
  async headers() {
    // #88 (P3-4): CORS allowlist を server-only env で管理する。
    //   ALLOWED_ORIGIN : single origin。next.config.ts の static header は
    //                    request 単位で値を変えられないため、CORS 仕様 (single
    //                    origin or "*" のみ; comma-separated は browser reject)
    //                    に合わせ単一値だけを受ける。fallback で NEXT_PUBLIC_SITE_URL
    //                    (public bundle 露出だが既存挙動維持)、最終 fallback で
    //                    canonical "https://faultray.com"。
    //   多重 origin を扱いたい場合は middleware で request.headers.origin を echo
    //   する設計に移行する (本 PR の scope 外、followup)。
    //   (review-loop, Codex P2): `||` で繋ぐ — hosted env で `ALLOWED_ORIGIN=`
    //   (空文字) は珍しくない誤設定で、`??` だと "" がそのまま header 値になり
    //   全 browser の CORS check が落ちる。空文字は unset と同義に扱う。
    const allowedOrigin =
      process.env.ALLOWED_ORIGIN ||
      process.env.NEXT_PUBLIC_SITE_URL ||
      "https://faultray.com";

    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          // SEC-03: Strict CSP — replaces the previous frame-ancestors-only policy
          {
            key: "Content-Security-Policy",
            value: buildCsp(),
          },
          // SEC-04: Prevent MIME-type sniffing attacks on downloads
          { key: "X-DNS-Prefetch-Control", value: "on" },
          // SEC-05: Strict Transport Security (max-age 1 year, include subdomains)
          {
            key: "Strict-Transport-Security",
            value: "max-age=31536000; includeSubDomains; preload",
          },
          // SEC-06: Permissions Policy — disable browser features not used by the app
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=(), interest-cohort=()",
          },
        ],
      },
      {
        source: "/api/:path*",
        headers: [
          {
            key: "Access-Control-Allow-Origin",
            value: allowedOrigin,
          },
          {
            key: "Access-Control-Allow-Methods",
            value: "GET, POST, PATCH, DELETE, OPTIONS",
          },
          {
            key: "Access-Control-Allow-Headers",
            value: "Content-Type, Authorization",
          },
          // (#105 review-loop 2, P2-B): cookie-authenticated routes (/api/status
          // ?detailed=true, /api/account/*, etc.) が cross-origin から呼ばれる
          // ケースに備え credentials を許可。Access-Control-Allow-Origin は
          // ALLOWED_ORIGIN single value を返しているため `*` との衝突なし
          // (`*` + credentials は CORS spec 違反)。
          {
            key: "Access-Control-Allow-Credentials",
            value: "true",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
