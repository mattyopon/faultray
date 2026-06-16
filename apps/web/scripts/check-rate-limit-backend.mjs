// #116: Production deploy guard for the rate-limit backend.
//
// The in-memory rate limiter in src/lib/rate-limit.ts is per-process and is
// trivially bypassed across Vercel serverless instances. To stop a production
// deploy from silently shipping on that fallback, this guard fails the build
// when a Vercel *production* build has no shared (Upstash) backend configured.
//
// Wired as the npm `prebuild` step, so it runs inside `npm run build` — the
// command Vercel runs on deploy. It is a NO-OP everywhere except a Vercel
// production build (VERCEL_ENV === "production"), so CI build checks, preview
// deploys, local dev and self-hosted builds are unaffected. The runtime
// request path is never changed (no per-request 500s).

import { fileURLToPath } from "node:url";

/**
 * Evaluate whether the rate-limit backend configuration is acceptable for the
 * given environment.
 *
 * @param {Record<string, string | undefined>} env
 * @returns {{ ok: boolean, enforced: boolean, reason: string }}
 *   - `ok`: false only when the build should be blocked.
 *   - `enforced`: whether the guard is active for this env (production build).
 *   - `reason`: human-readable explanation for logs.
 */
export function evaluateRateLimitBackend(env) {
  const isProdDeploy = env.VERCEL_ENV === "production";
  const hasUpstash = Boolean(
    env.UPSTASH_REDIS_REST_URL && env.UPSTASH_REDIS_REST_TOKEN
  );

  if (!isProdDeploy) {
    return {
      ok: true,
      enforced: false,
      reason: "not a Vercel production build — rate-limit backend guard inactive",
    };
  }
  if (hasUpstash) {
    return {
      ok: true,
      enforced: true,
      reason: "Upstash shared rate-limit backend configured for production",
    };
  }
  return {
    ok: false,
    enforced: true,
    reason:
      "VERCEL_ENV=production but UPSTASH_REDIS_REST_URL / " +
      "UPSTASH_REDIS_REST_TOKEN are not set. Production must not ship on the " +
      "per-instance in-memory rate limiter (#116). Configure the Upstash " +
      "backend, or unset VERCEL_ENV for a non-production build.",
  };
}

// Run as a CLI when invoked directly (the `prebuild` hook). Importing this file
// (e.g. from tests) must not exit the process, so gate on the entrypoint.
const invokedDirectly =
  process.argv[1] !== undefined &&
  process.argv[1] === fileURLToPath(import.meta.url);

if (invokedDirectly) {
  const result = evaluateRateLimitBackend(process.env);
  if (!result.ok) {
    console.error(`\n[rate-limit guard] BUILD BLOCKED: ${result.reason}\n`);
    process.exit(1);
  }
  if (result.enforced) {
    console.log(`[rate-limit guard] OK: ${result.reason}`);
  }
}
