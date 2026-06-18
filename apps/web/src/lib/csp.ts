/**
 * Content-Security-Policy builder (#32 / #85, ZAP mattyopon/faultray#172).
 *
 * Two modes:
 *  - default (`strict: false`): keeps `'unsafe-inline'` on script-src/style-src.
 *    This is the historical policy, served while the nonce migration is staged
 *    behind `FAULTRAY_CSP_STRICT`. Output is byte-for-byte the policy that used
 *    to live in next.config.ts, so moving CSP generation into src/proxy.ts does
 *    not change the live default policy.
 *  - strict (`strict: true` + a per-request `nonce`): removes `'unsafe-inline'`
 *    from script-src (replaced by `'nonce-…'` + `'strict-dynamic'`) and from
 *    style-src ELEMENTS (replaced by `'nonce-…'`). Inline style ATTRIBUTES —
 *    which React emits for `style={{…}}` and which a nonce cannot cover — are
 *    still permitted via `style-src-attr 'unsafe-inline'`, so the directive ZAP
 *    flags (`style-src 'unsafe-inline'`) no longer carries it. `'unsafe-eval'`
 *    is added to script-src in development only (React's dev error overlay).
 *
 * The strict policy is produced per request by src/proxy.ts (it owns the nonce).
 * `'strict-dynamic'` makes CSP3 browsers ignore the host allowlist and trust
 * scripts loaded by an already-trusted (nonced) script; the explicit GA/Hotjar/
 * Stripe hosts are retained as a CSP2 fallback for older browsers.
 */
export interface CspOptions {
  strict: boolean;
  isDev: boolean;
  /** Supabase project origin (no trailing slash) for connect-src. */
  supabaseOrigin: string;
  /** Per-request nonce; required for strict mode to take effect. */
  nonce?: string;
}

const IMG_SRC =
  "img-src 'self' data: blob: https://faultray.com https://www.google-analytics.com https://www.googletagmanager.com https://*.hotjar.com";
const FONT_SRC = "font-src 'self' https://fonts.gstatic.com";
const FRAME_SRC = "frame-src https://js.stripe.com https://hooks.stripe.com";
const SCRIPT_HOSTS = [
  "https://www.googletagmanager.com",
  "https://static.hotjar.com",
  "https://script.hotjar.com",
  "https://js.stripe.com",
];

function connectSrc(supabaseOrigin: string): string {
  return [
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
    .join(" ");
}

export function buildCsp({ strict, isDev, supabaseOrigin, nonce }: CspOptions): string {
  const useNonce = strict && Boolean(nonce);

  if (!useNonce) {
    // Historical policy — keep identical to the previous next.config.ts output.
    const directives = [
      "default-src 'self'",
      `script-src 'self' 'unsafe-inline' ${SCRIPT_HOSTS.join(" ")}`,
      "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
      IMG_SRC,
      FONT_SRC,
      connectSrc(supabaseOrigin),
      FRAME_SRC,
      "frame-ancestors 'none'",
      "base-uri 'self'",
      "form-action 'self'",
      // SEC (U13): block plugin/embed vectors in the default policy too (this
      // was only present in the strict policy). Safe, no legitimate <object>/
      // <embed> usage in the app.
      "object-src 'none'",
      "upgrade-insecure-requests",
    ];
    return directives.join("; ");
  }

  // Strict, nonce-based policy.
  const scriptSrc = [
    "script-src 'self'",
    `'nonce-${nonce}'`,
    "'strict-dynamic'",
    isDev ? "'unsafe-eval'" : "",
    ...SCRIPT_HOSTS, // CSP2 fallback; ignored by CSP3 strict-dynamic browsers
  ]
    .filter(Boolean)
    .join(" ");

  const directives = [
    "default-src 'self'",
    scriptSrc,
    `style-src 'self' 'nonce-${nonce}' https://fonts.googleapis.com`,
    // React inline style attributes (style={{…}}) cannot be nonced; permit them
    // at the attribute level only so style-src itself stays unsafe-inline-free.
    "style-src-attr 'unsafe-inline'",
    IMG_SRC,
    FONT_SRC,
    connectSrc(supabaseOrigin),
    FRAME_SRC,
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "object-src 'none'",
    "upgrade-insecure-requests",
  ];
  return directives.join("; ");
}
