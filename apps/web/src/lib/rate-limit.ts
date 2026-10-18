/**
 * Rate limiter for Next.js API routes (#25).
 *
 * Strategy:
 *   1. If UPSTASH_REDIS_REST_URL + UPSTASH_REDIS_REST_TOKEN are set →
 *      use the distributed sliding-window backend (@upstash/ratelimit +
 *      @upstash/redis, first-class deps as of #116) that shares counters
 *      across Vercel serverless invocations.
 *   2. Else → fall back to the in-memory sliding window. This path is only
 *      effective on single-process deployments (local dev, self-hosted).
 *      Vercel serverless per-instance processes do **not** share counters.
 *      To stop production from silently shipping on this fallback, a
 *      build-time guard (scripts/check-rate-limit-backend.mjs, wired as the
 *      `prebuild` step) fails a Vercel production build when the Upstash env
 *      is absent (#116). The runtime request path is unchanged.
 *
 * The public API (applyRateLimit, rateLimit, getClientIp) is stable
 * across both backends.
 */

interface RateLimitOptions {
  limit: number;
  windowMs: number;
}

interface RateLimitResult {
  success: boolean;
  remaining: number;
  resetAt: number;
}

// ─────────────────────────────────────────────────────────────
// Backend selection (performed lazily on first call)
// ─────────────────────────────────────────────────────────────
let _upstashClient: unknown | null = null;
let _upstashUnavailable = false;

async function _getUpstashClient(): Promise<unknown | null> {
  if (_upstashUnavailable) return null;
  if (_upstashClient) return _upstashClient;

  const url = process.env.UPSTASH_REDIS_REST_URL;
  const token = process.env.UPSTASH_REDIS_REST_TOKEN;
  if (!url || !token) {
    _upstashUnavailable = true;
    // #116: the in-memory fallback is per-process — on multi-instance
    // serverless it is trivially bypassed with concurrency. Surface that
    // loudly (once per instance) so production isn't silently running on
    // best-effort limits. Configuring Upstash remains an operator opt-in.
    if (process.env.VERCEL_ENV === "production") {
      console.warn(
        "[rate-limit] UPSTASH_REDIS_REST_URL/TOKEN not set — falling back to " +
          "per-instance in-memory rate limiting. Limits are not shared across " +
          "serverless instances; configure Upstash for production-grade limiting."
      );
    }
    return null;
  }

  try {
    // Lazy dynamic import: only pull the Upstash SDK into the runtime when the
    // backend is actually configured, keeping cold-starts light on the
    // in-memory path. The packages are first-class dependencies (#116), so no
    // optional-peer-dep / @ts-expect-error handling is needed.
    const { Ratelimit } = await import("@upstash/ratelimit");
    const { Redis } = await import("@upstash/redis");
    const redis = new Redis({ url, token });
    _upstashClient = { Ratelimit, redis };
    return _upstashClient;
  } catch (err) {
    // The env is configured but client init failed (bad URL/token, network).
    // Surface it rather than silently degrading to the per-instance limiter.
    console.error(
      "[rate-limit] Upstash backend init failed despite configuration — " +
        "falling back to in-memory:",
      err instanceof Error ? err.message : err
    );
    _upstashUnavailable = true;
    return null;
  }
}

// ─────────────────────────────────────────────────────────────
// In-memory fallback (kept from the original implementation)
// ─────────────────────────────────────────────────────────────
const store = new Map<string, number[]>();
const CLEANUP_INTERVAL_MS = 5 * 60 * 1000;
const _cleanupTimer = setInterval(() => {
  const now = Date.now();
  for (const [key, timestamps] of store.entries()) {
    const maxWindowMs = 60 * 60 * 1000;
    const valid = timestamps.filter((t) => t > now - maxWindowMs);
    if (valid.length === 0) store.delete(key);
    else store.set(key, valid);
  }
}, CLEANUP_INTERVAL_MS);
if (typeof _cleanupTimer === "object" && _cleanupTimer !== null && "unref" in _cleanupTimer) {
  (_cleanupTimer as NodeJS.Timeout).unref();
}

function _rateLimitInMemory(
  identifier: string,
  options: RateLimitOptions
): RateLimitResult {
  const now = Date.now();
  const windowStart = now - options.windowMs;
  const timestamps = (store.get(identifier) ?? []).filter((t) => t > windowStart);
  const remaining = Math.max(0, options.limit - timestamps.length - 1);
  const resetAt = timestamps[0] ? timestamps[0] + options.windowMs : now + options.windowMs;

  if (timestamps.length >= options.limit) {
    return { success: false, remaining: 0, resetAt };
  }
  timestamps.push(now);
  store.set(identifier, timestamps);
  return { success: true, remaining, resetAt };
}

async function _rateLimitUpstash(
  client: unknown,
  identifier: string,
  options: RateLimitOptions
): Promise<RateLimitResult> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const { Ratelimit, redis } = client as any;
  // Rebuild on each call to honour per-call limit/windowMs. Acceptable
  // because Ratelimit itself is cheap to construct; heavy work is the
  // Redis round-trip which is identical either way.
  const limiter = new Ratelimit({
    redis,
    limiter: Ratelimit.slidingWindow(options.limit, `${options.windowMs} ms`),
    analytics: false,
  });
  const res = await limiter.limit(identifier);
  return {
    success: res.success,
    remaining: res.remaining,
    resetAt: res.reset,
  };
}

/**
 * Check and record a request for the given identifier.
 * Async because Upstash is network-backed.
 */
export async function rateLimit(
  identifier: string,
  options: RateLimitOptions = { limit: 60, windowMs: 60_000 }
): Promise<RateLimitResult> {
  const client = await _getUpstashClient();
  if (client) {
    return _rateLimitUpstash(client, identifier, options);
  }
  return _rateLimitInMemory(identifier, options);
}

export function getClientIp(request: Request): string {
  const h = request.headers;
  // SEC (U14): do NOT blindly trust cf-connecting-ip. Any client can send that
  // header, and this app is fronted by Vercel (not Cloudflare), so an attacker
  // could spoof it to evade rate limits or lock out another user. Only honor it
  // when explicitly deployed behind Cloudflare (TRUST_CF_CONNECTING_IP=1).
  // Otherwise prefer Vercel's platform-set x-real-ip, which the client cannot
  // override at the edge.
  if (process.env.TRUST_CF_CONNECTING_IP === "1") {
    const cfIp = h.get("cf-connecting-ip");
    if (cfIp) return cfIp.trim();
  }
  const realIp = h.get("x-real-ip");
  if (realIp) return realIp.trim();
  const forwarded = h.get("x-forwarded-for");
  if (forwarded) return forwarded.split(",")[0].trim();
  return "anonymous";
}

/**
 * Convenience: return a 429 Response if rate limited, else null.
 *
 * Now async because Upstash backend requires awaiting. Callers must:
 *   const limited = await applyRateLimit(req, { ... });
 *   if (limited) return limited;
 */
export async function applyRateLimit(
  request: Request,
  options?: RateLimitOptions
): Promise<Response | null> {
  const ip = getClientIp(request);
  const result = await rateLimit(ip, options);

  if (!result.success) {
    return new Response(
      JSON.stringify({ error: "Too many requests. Please slow down." }),
      {
        status: 429,
        headers: {
          "Content-Type": "application/json",
          "Retry-After": String(Math.ceil((result.resetAt - Date.now()) / 1000)),
          "X-RateLimit-Limit": String(options?.limit ?? 60),
          "X-RateLimit-Remaining": "0",
          "X-RateLimit-Reset": String(Math.ceil(result.resetAt / 1000)),
        },
      }
    );
  }
  return null;
}
