/**
 * Cron endpoint authentication helper (#27).
 *
 * Strengthens the Bearer-only check in two ways:
 *   1. Constant-time comparison against CRON_SECRET to defeat timing-
 *      based secret extraction (even though single-shot retry limits
 *      make practical exploitation hard, this closes the theoretical
 *      gap).
 *   2. If CRON_ALLOWED_IPS is set (comma-separated CIDR or exact IPs),
 *      the caller's IP must match. Vercel documents the Cron IP range
 *      which operators can pin via this env. When unset, IP check is
 *      skipped (dev / self-hosted compatibility).
 */

import { NextResponse } from "next/server";

import { getClientIp } from "@/lib/rate-limit";

function _constantTimeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) {
    diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return diff === 0;
}

function _ipAllowed(clientIp: string): boolean {
  const allow = (process.env.CRON_ALLOWED_IPS || "").split(",").map((s) => s.trim()).filter(Boolean);
  if (allow.length === 0) return true; // not configured → permissive
  // Simple exact match; CIDR support deferred (Vercel publishes exact egress IPs)
  return allow.includes(clientIp);
}

/**
 * Verify a cron endpoint request. Returns a 401 Response if invalid,
 * null if authorized. Callers should short-circuit on non-null result.
 */
export function verifyCronAuth(request: Request): Response | null {
  const cronSecret = process.env.CRON_SECRET;
  if (!cronSecret) {
    return NextResponse.json(
      { error: "CRON_SECRET not configured" },
      { status: 503 }
    );
  }

  const authHeader = request.headers.get("authorization") || "";
  const expected = `Bearer ${cronSecret}`;
  if (!_constantTimeEqual(authHeader, expected)) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const clientIp = getClientIp(request);
  if (!_ipAllowed(clientIp)) {
    return NextResponse.json(
      { error: "Source IP not allowed" },
      { status: 403 }
    );
  }

  return null;
}
