/**
 * #116: production rate-limit backend guard.
 *
 * The build-time guard (scripts/check-rate-limit-backend.mjs, wired as the
 * npm `prebuild` step) must block a Vercel production build that has no shared
 * Upstash backend configured, while staying a no-op for every other build
 * context (CI, preview deploys, local dev, self-hosted).
 */
import { describe, it, expect } from "vitest";
import { evaluateRateLimitBackend } from "../../scripts/check-rate-limit-backend.mjs";

describe("#116: production rate-limit backend guard", () => {
  it("is inactive (and ok) outside a Vercel production build", () => {
    expect(evaluateRateLimitBackend({})).toMatchObject({ ok: true, enforced: false });
    expect(evaluateRateLimitBackend({ VERCEL_ENV: "preview" })).toMatchObject({
      ok: true,
      enforced: false,
    });
    expect(evaluateRateLimitBackend({ VERCEL_ENV: "development" })).toMatchObject({
      ok: true,
      enforced: false,
    });
  });

  it("does NOT require Upstash for a preview deploy even if it is otherwise unset", () => {
    // Preview must keep working on the in-memory fallback without blocking.
    const r = evaluateRateLimitBackend({ VERCEL_ENV: "preview" });
    expect(r.ok).toBe(true);
  });

  it("blocks a production build when no Upstash backend is configured", () => {
    const r = evaluateRateLimitBackend({ VERCEL_ENV: "production" });
    expect(r.ok).toBe(false);
    expect(r.enforced).toBe(true);
    expect(r.reason).toMatch(/UPSTASH/);
  });

  it("passes a production build when both Upstash env vars are set", () => {
    const r = evaluateRateLimitBackend({
      VERCEL_ENV: "production",
      UPSTASH_REDIS_REST_URL: "https://example.upstash.io",
      UPSTASH_REDIS_REST_TOKEN: "tkn", // pragma: allowlist secret
    });
    expect(r.ok).toBe(true);
    expect(r.enforced).toBe(true);
  });

  it("requires BOTH url and token (one alone is insufficient)", () => {
    expect(
      evaluateRateLimitBackend({
        VERCEL_ENV: "production",
        UPSTASH_REDIS_REST_URL: "https://example.upstash.io",
      }).ok
    ).toBe(false);
    expect(
      evaluateRateLimitBackend({
        VERCEL_ENV: "production",
        UPSTASH_REDIS_REST_TOKEN: "tkn", // pragma: allowlist secret
      }).ok
    ).toBe(false);
  });

  describe("ALLOW_INMEMORY_RATELIMIT opt-out", () => {
    it("unblocks a production build (with a warning) when explicitly set", () => {
      for (const v of ["1", "true", "TRUE", " true "]) {
        const r = evaluateRateLimitBackend({
          VERCEL_ENV: "production",
          ALLOW_INMEMORY_RATELIMIT: v,
        });
        expect(r.ok, `value=${JSON.stringify(v)}`).toBe(true);
        expect(r.warn, `value=${JSON.stringify(v)}`).toBe(true);
      }
    });

    it("does NOT opt out for falsy / unrelated values — block stays the default", () => {
      for (const v of ["", "0", "false", "no", "yes", "enabled"]) {
        const r = evaluateRateLimitBackend({
          VERCEL_ENV: "production",
          ALLOW_INMEMORY_RATELIMIT: v,
        });
        expect(r.ok, `value=${JSON.stringify(v)}`).toBe(false);
      }
    });

    it("prefers a real Upstash backend over the opt-out (no spurious warning)", () => {
      const r = evaluateRateLimitBackend({
        VERCEL_ENV: "production",
        ALLOW_INMEMORY_RATELIMIT: "1",
        UPSTASH_REDIS_REST_URL: "https://example.upstash.io",
        UPSTASH_REDIS_REST_TOKEN: "tkn", // pragma: allowlist secret
      });
      expect(r.ok).toBe(true);
      expect(r.warn).toBe(false);
    });

    it("stays a no-op outside production even when the opt-out is set", () => {
      const r = evaluateRateLimitBackend({
        VERCEL_ENV: "preview",
        ALLOW_INMEMORY_RATELIMIT: "1",
      });
      expect(r).toMatchObject({ ok: true, enforced: false, warn: false });
    });
  });
});
