/**
 * Rate limiter for Next.js API routes (#25).
 *
 * Strategy:
 *   1. If UPSTASH_REDIS_REST_URL + UPSTASH_REDIS_REST_TOKEN are set
 *      AND @upstash/ratelimit is installed → use the distributed
 *      token-bucket backend that works across Vercel serverless
 *      invocations.
 *   2. Else → fall back to the in-memory sliding window. This path
 *      is only effective on single-process deployments (local dev,
 *      self-hosted). Vercel serverless per-instance processes will
 *      **not** share counters — documented limitation.
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
    return null;
  }

  try {
    // Dynamic import so the dependency stays optional. Expect-error on
    // both lines because these packages are not in package.json — the
    // operator installs them only when opting into Upstash backend.
    // @ts-expect-error optional-peer-dep
    const { Ratelimit } = await import("@upstash/ratelimit");
    // @ts-expect-error optional-peer-dep
    const { Redis } = await import("@upstash/redis");
    const redis = new Redis({ url, token });
    _upstashClient = { Ratelimit, redis };
    return _upstashClient;
  } catch {
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
  const cfIp = h.get("cf-connecting-ip");
  if (cfIp) return cfIp;
  const realIp = h.get("x-real-ip");
  if (realIp) return realIp;
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
