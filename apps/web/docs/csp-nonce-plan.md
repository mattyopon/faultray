# CSP nonce migration plan (#32)

Current state: `next.config.ts` serves
```
Content-Security-Policy: script-src 'self' 'unsafe-inline' ...; style-src 'self' 'unsafe-inline' ...;
```

`'unsafe-inline'` neutralises the main value of CSP (inline XSS blocking).
Removing it requires nonce-tagging every inline `<script>` and `<style>`
site produced by Next.js + the app.

## Phases

### Phase 1 — scaffolding (THIS PR)
- [x] `src/middleware.ts` generates a per-request nonce
- [x] Nonce flows through `x-faultray-nonce` request + response header
- [x] This doc tracks the plan

### Phase 2 — consumer opt-in
- [ ] Root layout reads the nonce via `next/headers` and passes it into
      every `<Script>` and `<style>` tag it emits
- [ ] `CookieConsent`, `language-switcher`, analytics snippets read the
      nonce attribute

### Phase 3 — enforce
- [ ] Update `next.config.ts` CSP: replace `'unsafe-inline'` with
      `'nonce-${nonce}'` (value comes from middleware).
- [ ] Ship behind `FAULTRAY_CSP_STRICT=1` env for 1 release cycle so
      breakage can be detected without rollback.
- [ ] Flip default on once telemetry is clean.

## Why not cut over immediately

Next.js 16 still ships some internal inline scripts (hydration marker,
route prefetch) whose nonce propagation is not guaranteed across
versions. A progressive migration lets us stage verification without
bricking hydration for every user.
