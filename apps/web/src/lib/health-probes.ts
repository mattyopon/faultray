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

async function _withTimeout<T>(p: Promise<T>, ms: number): Promise<T> {
  return Promise.race([
    p,
    new Promise<T>((_, reject) =>
      setTimeout(() => reject(new Error(`timeout after ${ms}ms`)), ms)
    ),
  ]);
}

export async function probeSupabase(): Promise<ServiceProbe> {
  const start = Date.now();
  try {
    const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
    if (!url) return { name: "Supabase", status: "unknown", latency_ms: null, note: "not configured" };
    await _withTimeout(fetch(`${url}/rest/v1/`, { method: "HEAD" }), 1500);
    return { name: "Supabase", status: "operational", latency_ms: Date.now() - start };
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
    const res = await _withTimeout(
      fetch("https://api.stripe.com/v1/charges?limit=1", {
        method: "GET",
        headers: { Authorization: `Bearer ${key}` },
      }),
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
    const res = await _withTimeout(
      fetch("https://api.resend.com/domains", {
        method: "GET",
        headers: { Authorization: `Bearer ${key}` },
      }),
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
