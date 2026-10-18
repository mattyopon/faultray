/**
 * L2: Unit Test — /api/cron/trial-expiry (Issue #30)
 *
 * Route は PL/pgSQL function `public.downgrade_expired_trials()` を RPC で
 * 呼ぶだけの薄いラッパーなので、テスト観点は:
 *   - auth / env / rate-limit が期待通り
 *   - RPC 結果 (成功/空/error) を適切にマップして返却
 *   - 呼び出し先が正確 (rpc 名 "downgrade_expired_trials")
 *
 * 実際の DB レベル downgrade ロジックは pgTAP tests で別途 lock すべき
 * (このテストは route の wiring のみ検証)。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

vi.mock("@/lib/rate-limit", () => ({
  applyRateLimit: () => undefined,
  // verifyCronAuth (now used by the route) reads the client IP for the
  // optional CRON_ALLOWED_IPS check.
  getClientIp: () => "127.0.0.1",
}));

// RPC mock state
let rpcResult: { data: Array<{ id: string; email: string }> | null; error: { message: string } | null } = {
  data: [],
  error: null,
};
let capturedRpcNames: string[] = [];

vi.mock("@supabase/supabase-js", () => ({
  createClient: vi.fn(() => ({
    rpc: vi.fn((name: string) => {
      capturedRpcNames.push(name);
      return Promise.resolve(rpcResult);
    }),
  })),
}));

describe("L2: /api/cron/trial-expiry", () => {
  const ORIGINAL_ENV = { ...process.env };

  beforeEach(() => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    vi.spyOn(console, "info").mockImplementation(() => undefined);
    rpcResult = { data: [], error: null };
    capturedRpcNames = [];
    process.env.CRON_SECRET = "test-secret";  // pragma: allowlist secret
    process.env.NEXT_PUBLIC_SUPABASE_URL = "https://test.supabase.co";
    process.env.SUPABASE_SERVICE_ROLE_KEY = "test-service-key";  // pragma: allowlist secret
  });

  afterEach(() => {
    process.env = { ...ORIGINAL_ENV };
    vi.restoreAllMocks();
    vi.resetModules();
  });

  async function invoke(
    headers: Record<string, string> = {},
    method: "POST" | "GET" = "POST",
  ) {
    const route = await import("@/app/api/cron/trial-expiry/route");
    const handler = method === "GET" ? route.GET : route.POST;
    const req = new Request("https://test.local/api/cron/trial-expiry", {
      method,
      headers,
    });
    const res = await handler(req);
    const body = (await res.json()) as Record<string, unknown>;
    return { status: res.status, body };
  }

  it("returns 401 without authorization header", async () => {
    const { status, body } = await invoke();
    expect(status).toBe(401);
    expect(body.error).toBe("Unauthorized");
    // RPC must not have been called when unauthorized
    expect(capturedRpcNames).toEqual([]);
  });

  it("returns 401 with wrong bearer token", async () => {
    const { status } = await invoke({ authorization: "Bearer wrong" });
    expect(status).toBe(401);
    expect(capturedRpcNames).toEqual([]);
  });

  it("returns 503 when Supabase env is missing", async () => {
    delete process.env.SUPABASE_SERVICE_ROLE_KEY;
    const { status, body } = await invoke({
      authorization: "Bearer test-secret",
    });
    expect(status).toBe(503);
    expect(body.error).toBe("Supabase not configured");
  });

  it("returns downgraded:0 when RPC returns empty array", async () => {
    rpcResult = { data: [], error: null };
    const { status, body } = await invoke({
      authorization: "Bearer test-secret",
    });
    expect(status).toBe(200);
    expect(body.downgraded).toBe(0);
    expect(capturedRpcNames[0]).toBe("downgrade_expired_trials");
  });

  it("returns downgraded count equal to RPC rows", async () => {
    rpcResult = {
      data: [
        { id: "u1", email: "u1@test.local" },
        { id: "u2", email: "u2@test.local" },
        { id: "u3", email: "u3@test.local" },
      ],
      error: null,
    };
    const { status, body } = await invoke({
      authorization: "Bearer test-secret",
    });
    expect(status).toBe(200);
    expect(body.downgraded).toBe(3);
  });

  it("returns 500 on RPC error", async () => {
    rpcResult = { data: null, error: { message: "function does not exist" } };
    const { status, body } = await invoke({
      authorization: "Bearer test-secret",
    });
    expect(status).toBe(500);
    expect(body.error).toBe("Downgrade failed");
  });

  it("handles null data gracefully (treats as 0 downgrades)", async () => {
    rpcResult = { data: null, error: null };
    const { status, body } = await invoke({
      authorization: "Bearer test-secret",
    });
    expect(status).toBe(200);
    expect(body.downgraded).toBe(0);
  });

  it("invokes the exact RPC function name", async () => {
    await invoke({ authorization: "Bearer test-secret" });
    expect(capturedRpcNames[0]).toBe("downgrade_expired_trials");
  });

  // Vercel Cron invokes the path with GET; a POST-only route 405s every
  // scheduled run, so the GET handler is the one production actually uses.
  it("GET (Vercel Cron) runs the downgrade with valid secret", async () => {
    rpcResult = { data: [{ id: "u1", email: "u1@test.local" }], error: null };
    const { status, body } = await invoke(
      { authorization: "Bearer test-secret" },
      "GET",
    );
    expect(status).toBe(200);
    expect(body.downgraded).toBe(1);
    expect(capturedRpcNames[0]).toBe("downgrade_expired_trials");
  });

  it("GET still requires the cron secret", async () => {
    const { status } = await invoke({}, "GET");
    expect(status).toBe(401);
    expect(capturedRpcNames).toEqual([]);
  });
});
