/**
 * L2 Regression: /api/account/delete uses atomic RPC + preserves Stripe cancel (#29).
 *
 * Locks in the refactor:
 * - Single `rpc("delete_user_account", { uid })` replaces the 7-step
 *   non-transactional sequence.
 * - stripe_customer_id is read *before* the RPC so Stripe cancellation
 *   still has its handle after the DB row is gone.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

vi.mock("@/lib/rate-limit", () => ({
  applyRateLimit: () => undefined,
}));

// Stub supabase/server (SSR client for auth.getUser)
const _mockUser = { id: "user-abc-123" };
let _getUserOverride: { user: typeof _mockUser | null; error: { message: string } | null } = {
  user: _mockUser,
  error: null,
};
vi.mock("@/lib/supabase/server", () => ({
  createClient: async () => ({
    auth: {
      getUser: async () => ({
        data: { user: _getUserOverride.user },
        error: _getUserOverride.error,
      }),
    },
  }),
}));

// Stub Stripe SDK
const _mockStripeList = vi.fn();
const _mockStripeCancel = vi.fn();
vi.mock("stripe", () => {
  class StripeStub {
    subscriptions = {
      list: _mockStripeList,
      cancel: _mockStripeCancel,
    };
    constructor(..._args: unknown[]) {}
  }
  return { default: StripeStub };
});

// Stub supabase-js admin client
let _profileRow: { stripe_customer_id: string | null } | null = {
  stripe_customer_id: "cus_test_abc",
};
let _rpcError: { message: string } | null = null;
let _deleteAuthError: { message: string } | null = null;
const _rpcCalls: Array<{ fn: string; args: unknown }> = [];
const _profileSelectCalls: Array<{ eq: string }> = [];

vi.mock("@supabase/supabase-js", () => ({
  createClient: () => ({
    from: (_table: string) => {
      return {
        select: (_cols: string) => ({
          eq: (_col: string, val: string) => ({
            maybeSingle: async () => {
              _profileSelectCalls.push({ eq: val });
              return { data: _profileRow, error: null };
            },
          }),
        }),
      };
    },
    rpc: async (fn: string, args: unknown) => {
      _rpcCalls.push({ fn, args });
      return { error: _rpcError };
    },
    auth: {
      admin: {
        deleteUser: async (_id: string) => ({ error: _deleteAuthError }),
      },
    },
  }),
}));

describe("L2: /api/account/delete — atomic RPC + Stripe preserve (#29)", () => {
  const ORIG_ENV = { ...process.env };

  beforeEach(() => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    vi.spyOn(console, "info").mockImplementation(() => undefined);
    _getUserOverride = { user: _mockUser, error: null };
    _profileRow = { stripe_customer_id: "cus_test_abc" };
    _rpcError = null;
    _deleteAuthError = null;
    _rpcCalls.length = 0;
    _profileSelectCalls.length = 0;
    _mockStripeList.mockReset();
    _mockStripeCancel.mockReset();
    process.env.NEXT_PUBLIC_SUPABASE_URL = "https://test.supabase.co";
    process.env.SUPABASE_SERVICE_ROLE_KEY = "test-service-role-key";  // pragma: allowlist secret
    process.env.STRIPE_SECRET_KEY = "sk_test_real";  // pragma: allowlist secret
  });

  afterEach(() => {
    process.env = { ...ORIG_ENV };
    vi.restoreAllMocks();
    vi.resetModules();
  });

  async function invoke(body: unknown = { confirm: true }) {
    const { DELETE } = await import("@/app/api/account/delete/route");
    const req = new Request("https://test.local/api/account/delete", {
      method: "DELETE",
      body: JSON.stringify(body),
      headers: { "content-type": "application/json" },
    });
    const res = await DELETE(req);
    const respBody = (await res.json()) as Record<string, unknown>;
    return { status: res.status, body: respBody };
  }

  it("requires { confirm: true } (400 otherwise)", async () => {
    const { status } = await invoke({});
    expect(status).toBe(400);
  });

  it("401 when not authenticated", async () => {
    _getUserOverride = { user: null, error: { message: "no session" } };
    const { status } = await invoke();
    expect(status).toBe(401);
  });

  it("calls the atomic RPC with the user id and cancels Stripe subs", async () => {
    _mockStripeList.mockResolvedValue({
      data: [{ id: "sub_1" }, { id: "sub_2" }],
    });
    _mockStripeCancel.mockResolvedValue({});

    const { status, body } = await invoke();
    expect(status).toBe(200);
    expect(body).toEqual({ deleted: true });

    // Exactly one RPC call with the right shape
    expect(_rpcCalls).toEqual([
      { fn: "delete_user_account", args: { uid: _mockUser.id } },
    ]);
    // Profile was read before the RPC (for stripe_customer_id)
    expect(_profileSelectCalls).toEqual([{ eq: _mockUser.id }]);
    // Both subscriptions cancelled
    expect(_mockStripeCancel).toHaveBeenCalledTimes(2);
  });

  it("returns 500 when the RPC fails (and does NOT hit Stripe)", async () => {
    _rpcError = { message: "unique_violation" };

    const { status } = await invoke();
    expect(status).toBe(500);
    expect(_mockStripeCancel).not.toHaveBeenCalled();
  });

  it("Stripe error is non-fatal (deletion still succeeds)", async () => {
    _mockStripeList.mockRejectedValue(new Error("Stripe API down"));

    const { status, body } = await invoke();
    expect(status).toBe(200);
    expect(body.deleted).toBe(true);
  });

  it("skips Stripe when stripe_customer_id is null", async () => {
    _profileRow = { stripe_customer_id: null };

    const { status, body } = await invoke();
    expect(status).toBe(200);
    expect(body.deleted).toBe(true);
    expect(_mockStripeList).not.toHaveBeenCalled();
  });
});
