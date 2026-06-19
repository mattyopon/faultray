/**
 * Live health probes for Supabase / Stripe / Resend (#37).
 *
 * Shared between:
 *   - GET /api/status (JSON endpoint for external consumers)
 *   - /status page (SSR rendering)
 *
 * Each probe has a 1.5s timeout. Services with missing env are
 * labelled "unknown" (not a failure).
 */

export type ServiceStatus = "operational" | "degraded" | "outage" | "unknown";

export interface ServiceProbe {
  name: string;
  status: ServiceStatus;
  latency_ms: number | null;
  note?: string;
}

// Fetch with a hard timeout that actually aborts the underlying request and
// always clears its timer. A plain Promise.race against a setTimeout would let
// the HTTP request keep running (holding a socket) after the timeout "wins",
// and would leak the timer on a fast success — repeated probes against a hung
// dependency could exhaust sockets/fds.
async function _fetchWithTimeout(
  url: string,
  init: RequestInit,
  ms: number
): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), ms);
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") {
      throw new Error(`timeout after ${ms}ms`);
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

export async function probeSupabase(): Promise<ServiceProbe> {
  const start = Date.now();
  try {
    const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
    if (!url) return { name: "Supabase", status: "unknown", latency_ms: null, note: "not configured" };
    const res = await _fetchWithTimeout(`${url}/rest/v1/`, { method: "HEAD" }, 1500);
    const latency = Date.now() - start;
    // Don't blindly treat any completed response as operational: a 5xx means
    // Supabase is up but failing (outage). The unauthenticated /rest/v1/ probe
    // legitimately returns 401/404 when the service is healthy, so only 5xx is
    // a failure here.
    if (res.status >= 500) {
      return { name: "Supabase", status: "outage", latency_ms: latency, note: `HTTP ${res.status}` };
    }
    return { name: "Supabase", status: "operational", latency_ms: latency };
  } catch (err) {
    return {
      name: "Supabase",
      status: "outage",
      latency_ms: Date.now() - start,
      note: err instanceof Error ? err.message : String(err),
    };
  }
}

export async function probeStripe(): Promise<ServiceProbe> {
  const start = Date.now();
  try {
    const key = process.env.STRIPE_SECRET_KEY;
    if (!key || key === "sk_test_placeholder")
      return { name: "Stripe", status: "unknown", latency_ms: null, note: "not configured" };
    const res = await _fetchWithTimeout(
      "https://api.stripe.com/v1/charges?limit=1",
      {
        method: "GET",
        headers: { Authorization: `Bearer ${key}` },
      },
      1500
    );
    const latency = Date.now() - start;
    if (res.ok) return { name: "Stripe", status: "operational", latency_ms: latency };
    return {
      name: "Stripe",
      status: res.status >= 500 ? "outage" : "degraded",
      latency_ms: latency,
      note: `HTTP ${res.status}`,
    };
  } catch (err) {
    return {
      name: "Stripe",
      status: "outage",
      latency_ms: Date.now() - start,
      note: err instanceof Error ? err.message : String(err),
    };
  }
}

export async function probeResend(): Promise<ServiceProbe> {
  const start = Date.now();
  try {
    const key = process.env.RESEND_API_KEY;
    if (!key)
      return { name: "Email (Resend)", status: "unknown", latency_ms: null, note: "not configured" };
    const res = await _fetchWithTimeout(
      "https://api.resend.com/domains",
      {
        method: "GET",
        headers: { Authorization: `Bearer ${key}` },
      },
      1500
    );
    const latency = Date.now() - start;
    if (res.ok) return { name: "Email (Resend)", status: "operational", latency_ms: latency };
    return {
      name: "Email (Resend)",
      status: res.status >= 500 ? "outage" : "degraded",
      latency_ms: latency,
      note: `HTTP ${res.status}`,
    };
  } catch (err) {
    return {
      name: "Email (Resend)",
      status: "outage",
      latency_ms: Date.now() - start,
      note: err instanceof Error ? err.message : String(err),
    };
  }
}

export async function probeAll(): Promise<{
  overall: ServiceStatus;
  services: ServiceProbe[];
  checked_at: string;
}> {
  const services = await Promise.all([probeSupabase(), probeStripe(), probeResend()]);
  let overall: ServiceStatus = "operational";
  if (services.some((s) => s.status === "outage")) overall = "outage";
  else if (services.some((s) => s.status === "degraded")) overall = "degraded";
  else if (services.every((s) => s.status === "unknown")) overall = "unknown";
  return { overall, services, checked_at: new Date().toISOString() };
}
