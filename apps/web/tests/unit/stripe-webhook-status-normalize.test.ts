/**
 * Regression: customer.subscription.updated must not write a raw Stripe status
 * that violates the DB CHECK constraint.
 *
 * `profiles_subscription_status_check` only allows
 * (active|past_due|canceled|trialing). Stripe also emits incomplete,
 * incomplete_expired, unpaid, and paused. The webhook used to forward the raw
 * status, so those values raised a CHECK violation (23514), failed the webhook
 * into a ~3-day retry loop, and dropped the intended downgrade.
 * normalizeSubscriptionStatus() coerces any non-allowed status to a permitted
 * value at the single DB-write boundary.
 */
import { describe, it, expect } from "vitest";
import { normalizeSubscriptionStatus } from "@/app/api/stripe/webhook/route";

const ALLOWED = new Set(["active", "past_due", "canceled", "trialing"]);

describe("normalizeSubscriptionStatus", () => {
  it("passes through the four CHECK-allowed statuses unchanged", () => {
    for (const s of ["active", "past_due", "canceled", "trialing"]) {
      expect(normalizeSubscriptionStatus(s)).toBe(s);
    }
  });

  it("maps every other Stripe status to an allowed value (never a CHECK violation)", () => {
    for (const s of [
      "incomplete",
      "incomplete_expired",
      "unpaid",
      "paused",
      "some_future_status",
    ]) {
      const out = normalizeSubscriptionStatus(s);
      expect(out).toBeDefined();
      expect(ALLOWED.has(out as string)).toBe(true);
    }
  });

  it("collapses non-active/non-entitling statuses to 'canceled'", () => {
    expect(normalizeSubscriptionStatus("unpaid")).toBe("canceled");
    expect(normalizeSubscriptionStatus("incomplete_expired")).toBe("canceled");
    expect(normalizeSubscriptionStatus("paused")).toBe("canceled");
  });

  it("preserves undefined (no status change requested)", () => {
    expect(normalizeSubscriptionStatus(undefined)).toBeUndefined();
  });
});
