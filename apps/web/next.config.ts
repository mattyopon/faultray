import type { NextConfig } from "next";

// SEC-03 / #32 / #85: the Content-Security-Policy is now generated per request
// in src/proxy.ts (so it can carry a per-request nonce under FAULTRAY_CSP_STRICT
// and remove 'unsafe-inline'). It is intentionally NOT set here — a static
// next.config header cannot vary per request, and setting CSP in both places
// would emit two CSP headers that the browser enforces as their intersection.
// See src/lib/csp.ts (buildCsp) and docs/csp-nonce-plan.md.

const nextConfig: NextConfig = {
  // SEC: do not advertise the framework. Next.js adds `X-Powered-By: Next.js`
  // by default; setting this to false removes it.
  // ZAP 10037 "Server Leaks Information via X-Powered-By" — Refs mattyopon/faultray#172
  poweredByHeader: false,
  // #116: the Upstash rate-limit backend (@upstash/ratelimit + @upstash/redis)
  // are first-class dependencies. Keep them server-external so they are loaded
  // at runtime (only when UPSTASH_* env is configured, via the lazy dynamic
  // import in src/lib/rate-limit.ts) rather than bundled into every server chunk.
  serverExternalPackages: ["@upstash/ratelimit", "@upstash/redis"],
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
    const CANONICAL_ORIGIN = "https://faultray.com";
    const configuredOrigin =
      process.env.ALLOWED_ORIGIN ||
      process.env.NEXT_PUBLIC_SITE_URL ||
      CANONICAL_ORIGIN;
    // SEC: this /api block also emits `Access-Control-Allow-Credentials: true`,
    // and the CORS spec forbids the `*` wildcard together with credentials
    // (browsers reject the response). A misconfigured `ALLOWED_ORIGIN=*` is an
    // easy footgun; the empty-string case is already handled by the `||` chain
    // above, so reject `*` the same way and fall back to the canonical origin
    // instead of serving an invalid, insecure header.
    const allowedOrigin =
      configuredOrigin === "*" ? CANONICAL_ORIGIN : configuredOrigin;

    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          // ZAP #172: Cross-Origin-Opener-Policy isolates this top-level browsing
          // context from cross-origin openers (Spectre / tab-nabbing mitigation).
          // We use `same-origin-allow-popups` (NOT bare `same-origin`): the
          // allow-popups form keeps a reference to popups WE open, so OAuth popup
          // logins (Google / GitHub via Supabase) and Stripe popups keep working,
          // while still severing the opener link for cross-origin pages that open us.
          {
            key: "Cross-Origin-Opener-Policy",
            value: "same-origin-allow-popups",
          },
          // ZAP #172: Cross-Origin-Embedder-Policy (COEP: require-corp) is
          // intentionally DEFERRED. Enabling it would force every cross-origin
          // resource (Supabase, Stripe, Google Fonts, GA4/Hotjar, OG images) to
          // opt in via a Cross-Origin-Resource-Policy / CORP header; any resource
          // that does not would be blocked, almost certainly breaking the app.
          // Tracked separately in mattyopon/faultray#172 (follow-up).
          //
          // Content-Security-Policy is set per request in src/proxy.ts (nonce
          // support under FAULTRAY_CSP_STRICT), not here — see the note at the
          // top of this file.
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
