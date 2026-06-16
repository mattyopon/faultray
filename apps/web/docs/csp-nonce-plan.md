# CSP nonce migration plan (#32 / #85)

Previous state: `next.config.ts` served
```
Content-Security-Policy: script-src 'self' 'unsafe-inline' ...; style-src 'self' 'unsafe-inline' ...;
```

`'unsafe-inline'` neutralises the main value of CSP (inline XSS blocking).
Removing it requires nonce-tagging every executable inline `<script>` Next.js +
the app produce. ZAP (mattyopon/faultray#172) flags both `script-src` and
`style-src` `'unsafe-inline'`.

## Phases

### Phase 1 — scaffolding (done)
- [x] `src/proxy.ts` generates a per-request nonce
- [x] Nonce flows through the `x-faultray-nonce` request header
- [x] This doc tracks the plan

### Phase 2 — consumer opt-in (done, #85)
- [x] CSP generation moved out of `next.config.ts` into `src/lib/csp.ts`
      (`buildCsp`), produced per request by `src/proxy.ts` so it can carry the
      nonce. `next.config.ts` no longer sets a CSP header (avoids a duplicate,
      intersected policy).
- [x] Root layout (`src/app/layout.tsx`) reads the nonce via `next/headers` and
      stamps it on every executable `<script>` / `next/script` `<Script>` it
      emits (JSON-LD, GA4 loader + init, Hotjar init, the pre-hydration theme
      script). Reading `headers()` is gated on the strict flag so static
      rendering is preserved when strict CSP is off.
- [x] Next.js auto-applies the nonce to its own framework/inline scripts: in
      strict mode the proxy also forwards the policy on the **request**
      `Content-Security-Policy` header, from which Next extracts `'nonce-…'`.

      Note: locale JSON-LD blocks (`/en`, `/ja`) use
      `type="application/ld+json"`, which is a non-executed *data block* not
      subject to `script-src`, so they are intentionally left un-nonced. If
      preview telemetry shows them blocked, nonce them the same way.

### Phase 3 — enforce (done behind a flag, #85)
- [x] `buildCsp({ strict: true, nonce })` replaces `'unsafe-inline'` with
      `'nonce-${nonce}' 'strict-dynamic'` on `script-src` and `'nonce-${nonce}'`
      on `style-src`. Inline style *attributes* (React `style={{…}}`, which a
      nonce cannot cover) are kept working via `style-src-attr 'unsafe-inline'`,
      so `style-src` itself is `unsafe-inline`-free.
- [x] Strict mode ships behind `FAULTRAY_CSP_STRICT=1` so the change can be
      verified on a preview deploy without a production rollback. When unset,
      `buildCsp` returns the historical `'unsafe-inline'` policy unchanged and
      pages render statically as before.
- [ ] **Operator step:** set `FAULTRAY_CSP_STRICT=1` on a Vercel **preview**
      deploy and verify (no CSP violations in the console; GA4 / Hotjar /
      Stripe load; fonts + inline styles render; hydration works on app pages).
- [ ] Flip the default on (set `FAULTRAY_CSP_STRICT=1` in production) once
      preview telemetry is clean, then drop the flag and make strict the default
      in a follow-up.

## Tradeoff: dynamic rendering

Nonce-based CSP requires per-request rendering, so when `FAULTRAY_CSP_STRICT=1`
every page is dynamically rendered (no static optimization / CDN caching, higher
server cost). This is why it is staged behind the flag rather than flipped on
unconditionally. With the flag off there is **no** rendering change.

## Why not cut over immediately

Next.js 16 ships internal inline scripts (hydration marker, route prefetch)
whose nonce propagation should be handled automatically via the request CSP
header, but cannot be browser-verified from CI here. A flag-gated rollout lets
the nonce path be validated on a preview before it becomes the production
default, without bricking hydration for every user.
