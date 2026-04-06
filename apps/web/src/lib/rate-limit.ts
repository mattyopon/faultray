/**
 * In-memory rate limiter for Next.js API routes.
 *
 * Uses a sliding window algorithm with a Map<string, number[]>.
 * This works per-process. For multi-instance deployments, use
 * Redis (e.g. @upstash/ratelimit) instead.
 *
 * WARNING: Vercel serverless環境ではリクエストごとに別プロセスが起動するため、
 * このMapはプロセス間で共有されない。本番環境では Upstash Redis
 * (@upstash/ratelimit) 等の外部ストアに移行すること。
 * 現状の実装は開発環境・単一プロセス環境でのみ有効。
 *
 * API-08: レート制限実装
 */

interface RateLimitOptions {
  /** Maximum requests allowed per window */
  limit: number;
  /** Window size in milliseconds */
  windowMs: number;
}

interface RateLimitResult {
  success: boolean;
  /** Remaining requests in current window */
  remaining: number;
  /** Epoch ms when the window resets */
  resetAt: number;
}

// Global store — persists across requests within a single process
const store = new Map<string, number[]>();

// メモリリーク対策: 期限切れエントリを定期削除（5分ごと）
// setIntervalの参照を保持することで GC による早期解放を防ぐ
const CLEANUP_INTERVAL_MS = 5 * 60 * 1000;
const _cleanupTimer = setInterval(() => {
  const now = Date.now();
  for (const [key, timestamps] of store.entries()) {
    // windowMsが不明なので保守的に最大ウィンドウ（1時間）を使用
    const maxWindowMs = 60 * 60 * 1000;
    const valid = timestamps.filter((t) => t > now - maxWindowMs);
    if (valid.length === 0) {
      store.delete(key);
    } else {
      store.set(key, valid);
    }
  }
}, CLEANUP_INTERVAL_MS);

// Node.js プロセス終了時にタイマーをクリーンアップ（テスト環境でのリーク防止）
if (typeof _cleanupTimer === "object" && _cleanupTimer !== null && "unref" in _cleanupTimer) {
  (_cleanupTimer as NodeJS.Timeout).unref();
}

/**
 * Check and record a request for the given identifier.
 *
 * @param identifier - Unique key, typically IP or user ID
 * @param options    - Limit configuration
 */
export function rateLimit(
  identifier: string,
  options: RateLimitOptions = { limit: 60, windowMs: 60_000 }
): RateLimitResult {
  const now = Date.now();
  const windowStart = now - options.windowMs;

  // Retrieve and prune expired timestamps
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

/**
 * Extract a best-effort IP from a Next.js Request object.
 *
 * Header priority: cf-connecting-ip → x-real-ip → x-forwarded-for → "anonymous"
 */
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
 * Convenience: check rate limit and return a 429 Response if exceeded.
 *
 * Usage in a route handler:
 *   const limited = applyRateLimit(request, { limit: 10, windowMs: 60_000 });
 *   if (limited) return limited;
 */
export function applyRateLimit(
  request: Request,
  options?: RateLimitOptions
): Response | null {
  const ip = getClientIp(request);
  const result = rateLimit(ip, options);

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
