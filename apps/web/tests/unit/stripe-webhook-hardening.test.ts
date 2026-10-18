/**
 * Behavioral regression suite for the Stripe webhook security hardening
 * (#77 / #82, epic #77). Covers three findings:
 *
 *   1. #77 P1-3 — forged `metadata.user_id` must NOT be able to mutate another
 *      user's plan. The webhook resolves users by `stripe_customer_id` for
 *      subscription/invoice events and cross-checks the bootstrap path, so a
 *      checkout session carrying a victim's user_id but a customer already
 *      bound to a different profile is rejected (customer_mismatch).
 *
 *   2. #82 / P2-4 — last-write-wins / TOCTOU. An older event (smaller
 *      `event.created`) arriving after a newer one for the same customer must
 *      NOT overwrite the newer state. Enforced atomically in the DB: every
 *      plan/status write is a conditional UPDATE on `profiles` guarded by
 *      `subscription_event_at` (apply only when the incoming event is
 *      newer-or-equal), so even concurrent in-flight events cannot reorder.
 *
 *   3. #77 P2-3 — a customer_id mapping miss must be surfaced, not silently
 *      200'd. For `customer.subscription.deleted` against an unmapped customer
 *      we emit a structured `console.warn` (visible/alertable) while keeping
 *      the 200 ack so the legitimate account-delete flow is not broken. For the
 *      other customer-keyed events an unmapped customer throws → 500 → Stripe
 *      retries.
 *
 * These are BEHAVIORAL tests (drive POST end-to-end with mocked Stripe +
 * Supabase), complementing the static-source tests in
 * stripe-webhook-plan-preserve.test.ts / stripe-webhook-no-any.test.ts.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// ── rate-limit: always allow ────────────────────────────────────────────────
vi.mock("@/lib/rate-limit", () => ({
  applyRateLimit: async () => undefined,
}));

// ── Stripe SDK stub ─────────────────────────────────────────────────────────
// constructEvent returns whatever the test stages in `_nextEvent`. Signature
// verification is assumed to have passed (the route calls constructEvent and we
// short-circuit it). subscriptions.retrieve returns a staged subscription.
let _nextEvent: unknown = null;
let _constructThrows = false;
// Status returned by subscriptions.retrieve (tests override per case).
let _subscriptionStatus = "active";
// Price ID + metadata returned by subscriptions.retrieve (tests override per
// case). Checkout creates subs with inline price_data → a generated, UNMAPPED
// price ID and the real tier carried in metadata.plan (#144).
let _subscriptionPriceId = "price_pro_test";
let _subscriptionMetadata: Record<string, string> = {};
vi.mock("stripe", () => {
  class StripeStub {
    webhooks = {
      constructEvent: (_raw: string, _sig: string, _secret: string) => {
        if (_constructThrows) throw new Error("bad signature");
        return _nextEvent;
      },
    };
    subscriptions = {
      retrieve: vi.fn(async (_id: string) => ({
        status: _subscriptionStatus,
        items: { data: [{ price: { id: _subscriptionPriceId } }] },
        metadata: _subscriptionMetadata,
      })),
    };
    constructor(..._args: unknown[]) {}
  }
  return { default: StripeStub };
});

// ── Supabase admin client stub ──────────────────────────────────────────────
// In-memory ledger + profiles, with a chainable query builder that supports
// every call shape the route uses, including the conditional recency UPDATE
//   .update({...}).eq("id", id).or("subscription_event_at.is.null,...lte.X").select("id")
type LedgerRow = {
  event_id: string;
  event_type: string;
  customer_id: string | null;
  status: "processing" | "processed" | "failed";
  updated_at: string;
  last_error?: string | null;
};
type ProfileRow = {
  id: string;
  stripe_customer_id: string | null;
  plan?: string | null;
  subscription_status?: string | null;
  // #82 P2-4: per-customer recency high-water (Stripe event.created of the last
  // applied event). Undefined/null = no event applied yet.
  subscription_event_at?: string | null;
};

let _ledger: LedgerRow[] = [];
let _profiles: ProfileRow[] = [];
// Force the ledger INSERT to report a unique-violation (simulate duplicate).
let _ledgerInsertConflict = false;
// Simulate `profiles.subscription_event_at` not existing yet (migration 022 not
// applied): a guarded profiles UPDATE (payload carries subscription_event_at)
// reports an unknown-column error so the route can fail open.
let _profilesColumnMissing = false;
// Captured profile updates so tests can assert plan/status writes.
const _profileUpdates: Array<{ id: string; payload: Record<string, unknown> }> = [];

function makeBuilder(table: string) {
  // Accumulated state across the fluent chain.
  const filters: Array<{ op: string; col: string; val: unknown }> = [];
  // OR groups (from `.or("col.op.val,col.op.val")`): satisfied if ANY holds.
  const orGroups: Array<Array<{ col: string; op: string; val: string }>> = [];
  let mode: "select" | "insert" | "update" = "select";
  let updatePayload: Record<string, unknown> | null = null;
  let orderDesc = false;
  let orderCol: string | null = null;
  let limitN: number | null = null;

  const condMatch = (
    row: Record<string, unknown>,
    c: { col: string; op: string; val: string }
  ) => {
    const v = row[c.col];
    if (c.op === "is") {
      return c.val === "null" ? v === null || v === undefined : String(v) === c.val;
    }
    if (c.op === "lte") return v != null && (v as string) <= c.val;
    if (c.op === "lt") return v != null && (v as string) < c.val;
    if (c.op === "gte") return v != null && (v as string) >= c.val;
    if (c.op === "eq") return String(v) === c.val;
    return true;
  };

  const matches = (row: Record<string, unknown>) =>
    filters.every((f) => {
      const v = row[f.col];
      if (f.op === "eq") return v === f.val;
      if (f.op === "neq") return v !== f.val;
      if (f.op === "lt") return (v as string) < (f.val as string);
      return true;
    }) && orGroups.every((group) => group.some((c) => condMatch(row, c)));

  const rowsFor = (): Record<string, unknown>[] => {
    const store: Record<string, unknown>[] =
      table === "processed_stripe_events"
        ? (_ledger as unknown as Record<string, unknown>[])
        : (_profiles as unknown as Record<string, unknown>[]);
    let rows = store.filter(matches);
    if (orderCol) {
      rows = [...rows].sort((a, b) => {
        const av = (a[orderCol!] ?? "") as string;
        const bv = (b[orderCol!] ?? "") as string;
        return orderDesc ? (av < bv ? 1 : av > bv ? -1 : 0) : av < bv ? -1 : av > bv ? 1 : 0;
      });
    }
    if (limitN !== null) rows = rows.slice(0, limitN);
    return rows;
  };

  // Simulate the migration-022-not-applied window: a guarded profiles UPDATE
  // (payload carries subscription_event_at) is rejected with an unknown column.
  const columnMissingError = () =>
    table === "profiles" &&
    _profilesColumnMissing &&
    updatePayload != null &&
    Object.prototype.hasOwnProperty.call(updatePayload, "subscription_event_at");

  const applyUpdate = (): Record<string, unknown>[] => {
    const rows = rowsFor();
    for (const row of rows) {
      Object.assign(row, updatePayload);
      if (table === "profiles") {
        _profileUpdates.push({
          id: row.id as string,
          payload: { ...(updatePayload as Record<string, unknown>) },
        });
      }
    }
    return rows;
  };

  const builder: Record<string, unknown> = {
    select(_cols?: string) {
      if (mode === "select") mode = "select";
      return builder;
    },
    insert(payload: Record<string, unknown>) {
      mode = "insert";
      // INSERT resolves immediately (no further chain) — return a thenable.
      return {
        then: (resolve: (v: { error: unknown }) => void) => {
          if (table === "processed_stripe_events") {
            if (
              _ledgerInsertConflict ||
              _ledger.some((r) => r.event_id === payload.event_id)
            ) {
              resolve({ error: { code: "23505", message: "unique_violation" } });
              return;
            }
            _ledger.push(payload as unknown as LedgerRow);
          }
          resolve({ error: null });
        },
      };
    },
    update(payload: Record<string, unknown>) {
      mode = "update";
      updatePayload = payload;
      return builder;
    },
    eq(col: string, val: unknown) {
      filters.push({ op: "eq", col, val });
      return builder;
    },
    neq(col: string, val: unknown) {
      filters.push({ op: "neq", col, val });
      return builder;
    },
    lt(col: string, val: unknown) {
      filters.push({ op: "lt", col, val });
      return builder;
    },
    or(orString: string) {
      // PostgREST or syntax: "col.op.val,col.op.val" → satisfied if ANY holds.
      const conds = orString.split(",").map((part) => {
        const [col, op, ...rest] = part.split(".");
        return { col, op, val: rest.join(".") };
      });
      orGroups.push(conds);
      return builder;
    },
    order(col: string, opts?: { ascending?: boolean }) {
      orderCol = col;
      orderDesc = opts?.ascending === false;
      return builder;
    },
    limit(n: number) {
      limitN = n;
      return builder;
    },
    async maybeSingle() {
      const rows = rowsFor();
      return { data: rows[0] ?? null, error: null };
    },
    // Awaited UPDATE chains without a terminal `.select()`
    // (updateUserPlan's unguarded path, bootstrap, markFailed/markProcessed).
    then(resolve: (v: { data?: unknown; error: unknown }) => void) {
      if (mode === "update") {
        if (columnMissingError()) {
          resolve({
            data: null,
            error: { code: "42703", message: 'column "subscription_event_at" does not exist' },
          });
          return;
        }
        resolve({ data: applyUpdate(), error: null });
        return;
      }
      resolve({ data: null, error: null });
    },
  };

  // `.select()` after `.update()` must return a thenable resolving to affected
  // rows. We override select to detect post-update terminal selects.
  const origSelect = builder.select as (cols?: string) => unknown;
  builder.select = (cols?: string) => {
    if (mode === "update") {
      return {
        then: (resolve: (v: { data: unknown; error: unknown }) => void) => {
          if (columnMissingError()) {
            resolve({
              data: null,
              error: { code: "42703", message: 'column "subscription_event_at" does not exist' },
            });
            return;
          }
          resolve({ data: applyUpdate(), error: null });
        },
      };
    }
    return origSelect(cols);
  };

  return builder;
}

vi.mock("@supabase/supabase-js", () => ({
  createClient: () => ({
    from: (table: string) => makeBuilder(table),
  }),
}));

// ── Test harness ────────────────────────────────────────────────────────────
const ORIG_ENV = { ...process.env };

function nowIso(offsetMs = 0) {
  return new Date(Date.now() + offsetMs).toISOString();
}
function evIso(unixSeconds: number) {
  return new Date(unixSeconds * 1000).toISOString();
}

async function invoke(event: unknown) {
  _nextEvent = event;
  const { POST } = await import("@/app/api/stripe/webhook/route");
  const req = new Request("https://test.local/api/stripe/webhook", {
    method: "POST",
    body: "{}",
    headers: { "stripe-signature": "t=1,v1=deadbeef" },
  });
  const res = await POST(req);
  let body: Record<string, unknown> = {};
  try {
    body = (await res.json()) as Record<string, unknown>;
  } catch {
    /* no body */
  }
  return { status: res.status, body };
}

const warnIncludes = (
  spy: ReturnType<typeof vi.spyOn>,
  needle: string
): boolean =>
  spy.mock.calls.flat().some((a: unknown) => typeof a === "string" && a.includes(needle));

describe("Stripe webhook hardening (#77 / #82)", () => {
  let warnSpy: ReturnType<typeof vi.spyOn>;
  let errorSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    warnSpy = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    errorSpy = vi.spyOn(console, "error").mockImplementation(() => undefined);
    vi.spyOn(console, "info").mockImplementation(() => undefined);
    _ledger = [];
    _profiles = [];
    _profileUpdates.length = 0;
    _ledgerInsertConflict = false;
    _profilesColumnMissing = false;
    _subscriptionStatus = "active";
    _subscriptionPriceId = "price_pro_test";
    _subscriptionMetadata = {};
    _nextEvent = null;
    _constructThrows = false;
    process.env.NEXT_PUBLIC_SUPABASE_URL = "https://test.supabase.co";
    process.env.SUPABASE_SERVICE_ROLE_KEY = "test-service-role-key"; // pragma: allowlist secret
    process.env.STRIPE_SECRET_KEY = "sk_test_real"; // pragma: allowlist secret
    process.env.STRIPE_WEBHOOK_SECRET = "whsec_real"; // pragma: allowlist secret
    process.env.STRIPE_PRO_PRICE_IDS = "price_pro_test";
    process.env.STRIPE_STARTER_PRICE_IDS = "price_starter_test";
    process.env.STRIPE_BUSINESS_PRICE_IDS = "price_business_test";
  });

  afterEach(() => {
    process.env = { ...ORIG_ENV };
    vi.restoreAllMocks();
    vi.resetModules();
  });

  // ── Finding 1: #77 P1-3 — forged metadata.user_id ────────────────────────
  describe("#77 P1-3: forged metadata.user_id cannot hijack another user", () => {
    it("rejects checkout where metadata.user_id maps to a customer-mismatched profile", async () => {
      // Victim already has a different stripe_customer_id bound to their profile.
      _profiles = [{ id: "victim-user", stripe_customer_id: "cus_victim_real" }];
      const event = {
        id: "evt_forge_1",
        type: "checkout.session.completed",
        created: 1_700_000_000,
        data: {
          object: {
            metadata: { user_id: "victim-user", plan: "business" },
            // Attacker-controlled customer that does NOT match victim's bound one.
            customer: "cus_attacker_controlled",
          },
        },
      };
      const { status } = await invoke(event);
      // 200 ack (no retry storm), but plan was NOT mutated.
      expect(status).toBe(200);
      const victimUpdates = _profileUpdates.filter(
        (u) => u.id === "victim-user" && "plan" in u.payload
      );
      expect(victimUpdates).toHaveLength(0);
      // The mismatch was surfaced as an error log (attack indicator).
      const loggedMismatch = errorSpy.mock.calls
        .flat()
        .some((a: unknown) => typeof a === "string" && a.includes("customer_mismatch"));
      expect(loggedMismatch).toBe(true);
    });

    it("subscription.updated resolves user by customer_id, ignoring any metadata", async () => {
      // The legitimate owner of cus_legit. metadata is irrelevant for this path.
      _profiles = [{ id: "owner-user", stripe_customer_id: "cus_legit" }];
      const event = {
        id: "evt_subupd_1",
        type: "customer.subscription.updated",
        created: 1_700_000_100,
        data: {
          object: {
            // Even if metadata claimed someone else, the route never reads it here.
            metadata: { user_id: "attacker-target-user" },
            customer: "cus_legit",
            status: "active",
            items: { data: [{ price: { id: "price_pro_test" } }] },
          },
        },
      };
      const { status } = await invoke(event);
      expect(status).toBe(200);
      // Only the customer-resolved owner was updated.
      const updated = _profileUpdates.filter((u) => u.id === "owner-user");
      expect(updated.length).toBeGreaterThan(0);
      expect(_profileUpdates.some((u) => u.id === "attacker-target-user")).toBe(false);
    });

    it("legitimate checkout (matching/unset customer) still applies the plan", async () => {
      _profiles = [{ id: "new-user", stripe_customer_id: null }];
      const event = {
        id: "evt_legit_checkout",
        type: "checkout.session.completed",
        created: 1_700_000_200,
        data: {
          object: {
            metadata: { user_id: "new-user", plan: "pro" },
            customer: "cus_new",
          },
        },
      };
      const { status } = await invoke(event);
      expect(status).toBe(200);
      const planUpdate = _profileUpdates.find(
        (u) => u.id === "new-user" && u.payload.plan === "pro"
      );
      expect(planUpdate).toBeTruthy();
    });
  });

  // ── Finding 2: #82 P2-4 — ordering / last-write-wins ─────────────────────
  // Recency is enforced by the DB-atomic guard on profiles.subscription_event_at.
  describe("#82 P2-4: older events do not overwrite newer state", () => {
    it("an older subscription.updated does NOT overwrite a newer applied event", async () => {
      // Profile's high-water already at a NEWER event time.
      _profiles = [
        {
          id: "u1",
          stripe_customer_id: "cus_seq",
          subscription_event_at: evIso(1_700_000_500),
        },
      ];
      const event = {
        id: "evt_older",
        type: "customer.subscription.updated",
        created: 1_700_000_100, // older than the stored high-water
        data: {
          object: {
            customer: "cus_seq",
            status: "active",
            items: { data: [{ price: { id: "price_pro_test" } }] },
          },
        },
      };
      const { status } = await invoke(event);
      expect(status).toBe(200);
      // Stale update skipped: the guarded UPDATE matched 0 rows → no write.
      expect(_profileUpdates.filter((u) => u.id === "u1")).toHaveLength(0);
      expect(warnIncludes(warnSpy, "superseded by newer")).toBe(true);
    });

    it("a newer event DOES apply over an older high-water mark", async () => {
      _profiles = [
        {
          id: "u2",
          stripe_customer_id: "cus_seq2",
          subscription_event_at: evIso(1_700_000_100),
        },
      ];
      const event = {
        id: "evt_new_incoming",
        type: "customer.subscription.updated",
        created: 1_700_000_900, // newer
        data: {
          object: {
            customer: "cus_seq2",
            status: "active",
            items: { data: [{ price: { id: "price_pro_test" } }] },
          },
        },
      };
      const { status } = await invoke(event);
      expect(status).toBe(200);
      const updates = _profileUpdates.filter((u) => u.id === "u2");
      expect(updates.length).toBeGreaterThan(0);
      expect(updates.some((u) => u.payload.subscription_status === "active")).toBe(true);
      // High-water advanced to the incoming event time.
      expect(_profiles[0].subscription_event_at).toBe(evIso(1_700_000_900));
    });

    it("an older subscription.deleted does NOT cancel after a newer active event", async () => {
      _profiles = [
        {
          id: "u3",
          stripe_customer_id: "cus_seq3",
          plan: "pro",
          subscription_event_at: evIso(1_700_001_000),
        },
      ];
      const event = {
        id: "evt_delete_old",
        type: "customer.subscription.deleted",
        created: 1_700_000_500, // older than the stored high-water
        data: { object: { customer: "cus_seq3", status: "canceled" } },
      };
      const { status } = await invoke(event);
      expect(status).toBe(200);
      const downgrade = _profileUpdates.find(
        (u) => u.id === "u3" && u.payload.plan === "free"
      );
      expect(downgrade).toBeUndefined();
    });

    it("recency gate fails OPEN when event.created is missing (still applies)", async () => {
      _profiles = [
        {
          id: "u4",
          stripe_customer_id: "cus_seq4",
          subscription_event_at: evIso(1_700_001_000),
        },
      ];
      const event = {
        id: "evt_no_created",
        type: "customer.subscription.updated",
        // created intentionally omitted → cannot order → fail-open (apply unguarded).
        data: {
          object: {
            customer: "cus_seq4",
            status: "active",
            items: { data: [{ price: { id: "price_pro_test" } }] },
          },
        },
      };
      const { status } = await invoke(event);
      expect(status).toBe(200);
      expect(_profileUpdates.filter((u) => u.id === "u4").length).toBeGreaterThan(0);
    });
  });

  // ── Finding 2 review (Codex): DB-atomic recency guard ─────────────────────
  describe("#82 P2-4 review: atomic per-customer recency guard", () => {
    it("a no-op event (payment_failed attempt<2) does NOT advance the high-water, so a later older real event still applies", async () => {
      _profiles = [{ id: "u_noop", stripe_customer_id: "cus_noop" }];
      // 1) NEWER no-op: payment_failed attempt_count=1 → no plan/status write,
      //    so subscription_event_at must stay unset.
      const noop = {
        id: "evt_noop_newer",
        type: "invoice.payment_failed",
        created: 1_700_010_000, // newer
        data: { object: { customer: "cus_noop", attempt_count: 1 } },
      };
      const noopRes = await invoke(noop);
      expect(noopRes.status).toBe(200);
      expect(_profileUpdates.filter((u) => u.id === "u_noop")).toHaveLength(0);
      expect(_profiles[0].subscription_event_at ?? null).toBeNull();

      // 2) OLDER real subscription.updated still applies (no high-water set).
      const real = {
        id: "evt_real_older",
        type: "customer.subscription.updated",
        created: 1_700_009_000, // older than the no-op
        data: {
          object: {
            customer: "cus_noop",
            status: "active",
            items: { data: [{ price: { id: "price_pro_test" } }] },
          },
        },
      };
      const realRes = await invoke(real);
      expect(realRes.status).toBe(200);
      expect(
        _profileUpdates.some(
          (u) => u.id === "u_noop" && u.payload.subscription_status === "active"
        )
      ).toBe(true);
    });

    it("an expanded-customer event is gated by the SAME profile high-water as string-customer events", async () => {
      _profiles = [{ id: "u_exp", stripe_customer_id: "cus_exp" }];
      // 1) NEWER subscription.updated whose `customer` is an EXPANDED object.
      const expanded = {
        id: "evt_expanded_new",
        type: "customer.subscription.updated",
        created: 1_700_020_000, // newer
        data: {
          object: {
            customer: { id: "cus_exp" }, // expanded, not a bare string
            status: "active",
            items: { data: [{ price: { id: "price_pro_test" } }] },
          },
        },
      };
      const r1 = await invoke(expanded);
      expect(r1.status).toBe(200);
      // High-water advanced (recency keyed by resolved profile, not raw field).
      expect(_profiles[0].subscription_event_at).toBe(evIso(1_700_020_000));

      // 2) OLDER string-customer event for the same customer is suppressed.
      const olderStr = {
        id: "evt_str_old",
        type: "customer.subscription.updated",
        created: 1_700_019_000, // older
        data: {
          object: {
            customer: "cus_exp",
            status: "past_due",
            items: { data: [{ price: { id: "price_pro_test" } }] },
          },
        },
      };
      const r2 = await invoke(olderStr);
      expect(r2.status).toBe(200);
      expect(
        _profileUpdates.some(
          (u) => u.id === "u_exp" && u.payload.subscription_status === "past_due"
        )
      ).toBe(false);
      expect(warnIncludes(warnSpy, "superseded by newer")).toBe(true);
    });

    it("an older checkout.session.completed does NOT re-activate a profile after a newer event (repeat checkout)", async () => {
      // Repeat checkout reusing an already-bootstrapped customer whose high-water
      // is already at a NEWER cancellation event.
      _profiles = [
        {
          id: "u_co",
          stripe_customer_id: "cus_co",
          plan: "free",
          subscription_status: "canceled",
          subscription_event_at: evIso(1_700_040_000),
        },
      ];
      const event = {
        id: "evt_checkout_old",
        type: "checkout.session.completed",
        created: 1_700_039_000, // older than the cancellation high-water
        data: {
          object: {
            metadata: { user_id: "u_co", plan: "pro" },
            customer: "cus_co",
          },
        },
      };
      const { status } = await invoke(event);
      expect(status).toBe(200);
      // Stale activation skipped: no write flipping the profile back to active/pro.
      expect(
        _profileUpdates.some(
          (u) =>
            u.id === "u_co" &&
            (u.payload.plan === "pro" || u.payload.subscription_status === "active")
        )
      ).toBe(false);
      expect(warnIncludes(warnSpy, "superseded by newer")).toBe(true);
    });

    it("invoice.payment_succeeded for a CANCELED subscription does not mark the profile active or advance the high-water", async () => {
      _profiles = [
        {
          id: "u_cxl",
          stripe_customer_id: "cus_cxl",
          plan: "free",
          subscription_status: "canceled",
        },
      ];
      _subscriptionStatus = "canceled"; // final/outstanding invoice paid after cancellation
      const event = {
        id: "evt_pay_after_cancel",
        type: "invoice.payment_succeeded",
        created: 1_700_050_000,
        data: {
          object: {
            customer: "cus_cxl",
            parent: { subscription_details: { subscription: "sub_cxl" } },
          },
        },
      };
      const { status } = await invoke(event);
      expect(status).toBe(200);
      // Not reactivated…
      expect(
        _profileUpdates.some(
          (u) => u.id === "u_cxl" && u.payload.subscription_status === "active"
        )
      ).toBe(false);
      // …and the high-water was NOT advanced, so a later/delayed delete still applies.
      expect(_profiles[0].subscription_event_at ?? null).toBeNull();
      expect(warnIncludes(warnSpy, "not active/trialing")).toBe(true);
    });

    it("invoice.payment_failed for a CANCELED subscription does not mark the profile past_due or advance the high-water", async () => {
      _profiles = [
        {
          id: "u_pf_cxl",
          stripe_customer_id: "cus_pf_cxl",
          plan: "free",
          subscription_status: "canceled",
        },
      ];
      _subscriptionStatus = "canceled"; // final/outstanding invoice's dunning fails after cancellation
      const event = {
        id: "evt_pay_failed_after_cancel",
        type: "invoice.payment_failed",
        created: 1_700_055_000,
        data: {
          object: {
            customer: "cus_pf_cxl",
            attempt_count: 3, // >= 2 → would normally mark past_due
            parent: { subscription_details: { subscription: "sub_pf_cxl" } },
          },
        },
      };
      const { status } = await invoke(event);
      expect(status).toBe(200);
      // Not flipped to past_due…
      expect(
        _profileUpdates.some(
          (u) => u.id === "u_pf_cxl" && u.payload.subscription_status === "past_due"
        )
      ).toBe(false);
      // …and the high-water was NOT advanced, so a later/delayed delete still applies.
      expect(_profiles[0].subscription_event_at ?? null).toBeNull();
      expect(warnIncludes(warnSpy, "(terminal) — not marking past_due")).toBe(true);
    });

    it("invoice.payment_failed for an ACTIVE subscription still marks the profile past_due (dunning)", async () => {
      _profiles = [
        {
          id: "u_pf_act",
          stripe_customer_id: "cus_pf_act",
          plan: "pro",
          subscription_status: "active",
        },
      ];
      _subscriptionStatus = "active"; // first failure while still active — legitimate dunning
      const event = {
        id: "evt_pay_failed_active",
        type: "invoice.payment_failed",
        created: 1_700_056_000,
        data: {
          object: {
            customer: "cus_pf_act",
            attempt_count: 2,
            parent: { subscription_details: { subscription: "sub_pf_act" } },
          },
        },
      };
      const { status } = await invoke(event);
      expect(status).toBe(200);
      // The non-terminal path is preserved: past_due IS written.
      expect(
        _profileUpdates.some(
          (u) => u.id === "u_pf_act" && u.payload.subscription_status === "past_due"
        )
      ).toBe(true);
    });

    it("falls open (applies) when subscription_event_at column is missing (migration 022 not yet applied)", async () => {
      _profiles = [{ id: "u_pre", stripe_customer_id: "cus_pre" }];
      _profilesColumnMissing = true; // guarded UPDATE rejected with unknown column
      const event = {
        id: "evt_pre_migrate",
        type: "customer.subscription.updated",
        created: 1_700_030_000,
        data: {
          object: {
            customer: "cus_pre",
            status: "active",
            items: { data: [{ price: { id: "price_pro_test" } }] },
          },
        },
      };
      const { status } = await invoke(event);
      // Ack succeeds — a missing column must not brick the webhook…
      expect(status).toBe(200);
      // …and the billing mutation still applied via the unguarded fallback.
      expect(
        _profileUpdates.some(
          (u) => u.id === "u_pre" && u.payload.subscription_status === "active"
        )
      ).toBe(true);
      // The degraded condition was surfaced.
      const logged = errorSpy.mock.calls
        .flat()
        .some(
          (a: unknown) => typeof a === "string" && a.includes("subscription_event_at missing")
        );
      expect(logged).toBe(true);
    });
  });

  // ── #144 review: inline price_data plans + non-subscription invoices ──────
  describe("#144 review: checkout inline price_data plan resolution", () => {
    it("subscription.updated for an inline-price_data (unmapped) active sub resolves the plan from metadata, not free", async () => {
      _profiles = [
        {
          id: "u_inl",
          stripe_customer_id: "cus_inl",
          plan: "free",
          subscription_status: null,
        },
      ];
      // Checkout creates the sub with inline price_data → generated, UNMAPPED
      // price ID; the real tier is in subscription metadata.plan.
      const event = {
        id: "evt_sub_updated_inline",
        type: "customer.subscription.updated",
        created: 1_700_060_000,
        data: {
          object: {
            customer: "cus_inl",
            status: "active",
            items: { data: [{ price: { id: "price_inline_generated" } }] },
            metadata: { plan: "pro", user_id: "u_inl" },
          },
        },
      };
      const { status } = await invoke(event);
      expect(status).toBe(200);
      // Resolved to pro (from metadata) — NOT downgraded to free…
      expect(
        _profileUpdates.some(
          (u) => u.id === "u_inl" && u.payload.plan === "pro"
        )
      ).toBe(true);
      expect(
        _profileUpdates.some(
          (u) => u.id === "u_inl" && u.payload.plan === "free"
        )
      ).toBe(false);
      // …and the high-water advanced to this event.
      expect(_profiles[0].subscription_event_at).toBe(evIso(1_700_060_000));
    });

    it("subscription.updated for an active sub with NO mapping and NO metadata preserves the plan (never forces free)", async () => {
      _profiles = [
        {
          id: "u_keep",
          stripe_customer_id: "cus_keep",
          plan: "business",
          subscription_status: "active",
        },
      ];
      const event = {
        id: "evt_sub_updated_unknown",
        type: "customer.subscription.updated",
        created: 1_700_061_000,
        data: {
          object: {
            customer: "cus_keep",
            status: "active",
            items: { data: [{ price: { id: "price_inline_generated" } }] },
            // no metadata.plan → genuinely unresolvable
          },
        },
      };
      const { status } = await invoke(event);
      expect(status).toBe(200);
      // Status still written (active), but plan is NOT forced to free.
      expect(
        _profileUpdates.some(
          (u) => u.id === "u_keep" && u.payload.subscription_status === "active"
        )
      ).toBe(true);
      expect(
        _profileUpdates.some(
          (u) => u.id === "u_keep" && u.payload.plan === "free"
        )
      ).toBe(false);
    });

    it("a non-active subscription.updated still downgrades the plan to free", async () => {
      _profiles = [
        {
          id: "u_dwn",
          stripe_customer_id: "cus_dwn",
          plan: "pro",
          subscription_status: "active",
        },
      ];
      const event = {
        id: "evt_sub_updated_canceled",
        type: "customer.subscription.updated",
        created: 1_700_062_000,
        data: {
          object: {
            customer: "cus_dwn",
            status: "canceled",
            items: { data: [{ price: { id: "price_pro_test" } }] },
          },
        },
      };
      const { status } = await invoke(event);
      expect(status).toBe(200);
      expect(
        _profileUpdates.some(
          (u) => u.id === "u_dwn" && u.payload.plan === "free"
        )
      ).toBe(true);
    });

    it("payment_succeeded for an inline-price_data (unmapped) active sub resolves the plan from metadata", async () => {
      _profiles = [
        {
          id: "u_pay_inl",
          stripe_customer_id: "cus_pay_inl",
          plan: "free",
          subscription_status: null,
        },
      ];
      _subscriptionStatus = "active";
      _subscriptionPriceId = "price_inline_generated"; // unmapped
      _subscriptionMetadata = { plan: "business", user_id: "u_pay_inl" };
      const event = {
        id: "evt_pay_inline",
        type: "invoice.payment_succeeded",
        created: 1_700_063_000,
        data: {
          object: {
            customer: "cus_pay_inl",
            parent: { subscription_details: { subscription: "sub_pay_inl" } },
          },
        },
      };
      const { status } = await invoke(event);
      expect(status).toBe(200);
      expect(
        _profileUpdates.some(
          (u) => u.id === "u_pay_inl" && u.payload.plan === "business"
        )
      ).toBe(true);
      expect(_profiles[0].subscription_event_at).toBe(evIso(1_700_063_000));
    });

    it("payment_failed with NO subscription does not mark past_due or advance the high-water", async () => {
      _profiles = [
        {
          id: "u_nosub",
          stripe_customer_id: "cus_nosub",
          plan: "pro",
          subscription_status: "active",
        },
      ];
      const event = {
        id: "evt_pay_failed_nosub",
        type: "invoice.payment_failed",
        created: 1_700_064_000,
        data: {
          object: {
            customer: "cus_nosub",
            attempt_count: 3, // >= 2 → would normally mark past_due
            // no parent.subscription_details / subscription → one-off invoice
          },
        },
      };
      const { status } = await invoke(event);
      expect(status).toBe(200);
      // No write at all for a non-subscription invoice…
      expect(_profileUpdates.filter((u) => u.id === "u_nosub")).toHaveLength(0);
      // …and the high-water is untouched, so a later cancellation still applies.
      expect(_profiles[0].subscription_event_at ?? null).toBeNull();
      expect(warnIncludes(warnSpy, "has no subscription")).toBe(true);
    });
  });

  // ── Finding 3: #77 P2-3 — customer mapping miss is surfaced ───────────────
  describe("#77 P2-3: unmapped customer is surfaced, not silently lost", () => {
    it("subscription.deleted for an unmapped customer warns (not silent) and still 200s", async () => {
      _profiles = []; // nobody maps to this customer
      const event = {
        id: "evt_unmapped_delete",
        type: "customer.subscription.deleted",
        created: 1_700_002_000,
        data: { object: { customer: "cus_orphan", status: "canceled" } },
      };
      const { status } = await invoke(event);
      // 200 preserved (account-delete flow must not break / no retry storm),
      expect(status).toBe(200);
      // but the miss is SURFACED as a warn referencing the unmapped customer.
      const surfaced = warnSpy.mock.calls
        .flat()
        .some(
          (a: unknown) =>
            typeof a === "string" && a.includes("UNMAPPED") && a.includes("cus_orphan")
        );
      expect(surfaced).toBe(true);
    });

    it("subscription.updated for an unmapped customer 500s so Stripe retries", async () => {
      _profiles = [];
      const event = {
        id: "evt_unmapped_update",
        type: "customer.subscription.updated",
        created: 1_700_002_100,
        data: {
          object: {
            customer: "cus_orphan2",
            status: "active",
            items: { data: [{ price: { id: "price_pro_test" } }] },
          },
        },
      };
      const { status } = await invoke(event);
      // Not a silent 200 — surfaced as a 500 so Stripe retries.
      expect(status).toBe(500);
      // Ledger row marked failed (reclaimable on retry).
      const row = _ledger.find((r) => r.event_id === "evt_unmapped_update");
      expect(row?.status).toBe("failed");
    });

    it("payment_succeeded for an unmapped customer 500s so Stripe retries", async () => {
      _profiles = [];
      const event = {
        id: "evt_unmapped_pay",
        type: "invoice.payment_succeeded",
        created: 1_700_002_200,
        data: {
          object: {
            customer: "cus_orphan3",
            // subscription id present so the handler attempts a mutation.
            parent: { subscription_details: { subscription: "sub_x" } },
          },
        },
      };
      const { status } = await invoke(event);
      expect(status).toBe(500);
      const row = _ledger.find((r) => r.event_id === "evt_unmapped_pay");
      expect(row?.status).toBe("failed");
    });
  });

  // ── Idempotency / ledger integrity preserved ──────────────────────────────
  describe("ledger integrity (regression guard for the 2-state ledger)", () => {
    it("a duplicate already-processed event returns 200 duplicate without re-mutating", async () => {
      _profiles = [{ id: "u9", stripe_customer_id: "cus_dup" }];
      _ledger = [
        {
          event_id: "evt_dup",
          event_type: "customer.subscription.updated",
          customer_id: "cus_dup",
          status: "processed",
          updated_at: nowIso(),
        },
      ];
      const event = {
        id: "evt_dup",
        type: "customer.subscription.updated",
        created: 1_700_003_000,
        data: {
          object: {
            customer: "cus_dup",
            status: "active",
            items: { data: [{ price: { id: "price_pro_test" } }] },
          },
        },
      };
      const { status, body } = await invoke(event);
      expect(status).toBe(200);
      expect(body.duplicate).toBe(true);
      expect(_profileUpdates.filter((u) => u.id === "u9")).toHaveLength(0);
    });

    it("a new mutating event advances profiles.subscription_event_at to its event.created", async () => {
      _profiles = [{ id: "u10", stripe_customer_id: "cus_rec" }];
      const event = {
        id: "evt_rec",
        type: "customer.subscription.updated",
        created: 1_700_004_000,
        data: {
          object: {
            customer: "cus_rec",
            status: "active",
            items: { data: [{ price: { id: "price_pro_test" } }] },
          },
        },
      };
      await invoke(event);
      expect(_profiles[0].subscription_event_at).toBe(evIso(1_700_004_000));
      // The ledger row is the idempotency claim only (no recency column on it).
      const row = _ledger.find((r) => r.event_id === "evt_rec");
      expect(row?.status).toBe("processed");
    });
  });
});
