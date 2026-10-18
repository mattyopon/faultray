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
- [x] Strict mode is now the **default** (#85): `cspStrictEnabled()` returns
      true unless `FAULTRAY_CSP_STRICT=0`. The historical `'unsafe-inline'`
      policy is retained only as an opt-out / rollback path.
- [x] **Rollback hatch:** setting `FAULTRAY_CSP_STRICT=0` (Vercel env, then
      redeploy) instantly restores the `'unsafe-inline'` policy **and** static
      rendering / CDN caching — no code change needed — if a nonce-propagation
      issue surfaces on a deploy.
- [ ] **Post-deploy smoke check (operator):** after this ships, confirm on the
      live deploy that there are no CSP violations in the browser console, GA4 /
      Hotjar / Stripe load, fonts + inline styles render, and hydration works on
      app pages. If anything breaks, set `FAULTRAY_CSP_STRICT=0`, redeploy, and
      nonce the offending script.

## Tradeoff: dynamic rendering

Nonce-based CSP requires per-request rendering, so with strict mode on (the
default) every page is dynamically rendered (no static optimization / CDN
caching, higher server cost). This is the accepted cost of removing
`'unsafe-inline'`. Setting `FAULTRAY_CSP_STRICT=0` reverts to the static
`'unsafe-inline'` policy if the caching/cost tradeoff ever needs to be undone.

## Residual risk + rollback

Next.js 16 ships internal inline scripts (hydration marker, route prefetch)
whose nonce propagation is handled automatically via the request CSP header
(confirmed against `node_modules/next/dist/docs/.../content-security-policy.md`,
"How nonces work in Next.js"), but cannot be browser-verified from CI here.
That is why the `FAULTRAY_CSP_STRICT=0` rollback hatch is retained rather than
dropped: if hydration breaks on the live deploy, ops flip the env var and
redeploy to instantly restore the previous behavior, no code revert needed.
