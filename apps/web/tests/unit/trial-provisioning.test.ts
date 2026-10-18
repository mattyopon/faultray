/**
 * #114: trial provisioning for trigger-created profiles.
 *
 * The handle_new_user trigger creates the profile row at sign-up, so the
 * callback's "no profile → grant trial" branch never ran. The fix provisions
 * on first sign-in when the profile is still in its trigger default state AND
 * the auth user was created within the freshness window — the window is what
 * keeps old free accounts from being upgraded on a routine login.
 */
import { describe, it, expect } from "vitest";
import {
  shouldProvisionTrial,
  trialEndIso,
  FRESH_SIGNUP_WINDOW_MS,
  TRIAL_DAYS,
} from "@/lib/trial-provisioning";

const NOW = Date.parse("2026-06-12T00:00:00Z");
const fresh = new Date(NOW - 60_000).toISOString(); // signed up 1 min ago
const stale = new Date(NOW - FRESH_SIGNUP_WINDOW_MS - 1).toISOString();

const defaultProfile = {
  plan: "free",
  trial_ends_at: null,
  stripe_customer_id: null,
};

describe("#114: shouldProvisionTrial", () => {
  it("provisions a fresh signup with a trigger-default profile", () => {
    expect(shouldProvisionTrial(defaultProfile, fresh, NOW)).toBe(true);
  });

  it("never upgrades a long-standing free account on login", () => {
    expect(shouldProvisionTrial(defaultProfile, stale, NOW)).toBe(false);
  });

  it("skips profiles that already had a trial", () => {
    expect(
      shouldProvisionTrial(
        { ...defaultProfile, trial_ends_at: "2026-01-01T00:00:00Z" },
        fresh,
        NOW
      )
    ).toBe(false);
  });

  it("skips paid plans (coupon/business/pro state must not be overwritten)", () => {
    for (const plan of ["pro", "business", "starter"]) {
      expect(shouldProvisionTrial({ ...defaultProfile, plan }, fresh, NOW)).toBe(false);
    }
  });

  it("skips profiles already linked to Stripe", () => {
    expect(
      shouldProvisionTrial(
        { ...defaultProfile, stripe_customer_id: "cus_123" },
        fresh,
        NOW
      )
    ).toBe(false);
  });

  it("requires a parseable user created_at (no provisioning on missing data)", () => {
    expect(shouldProvisionTrial(defaultProfile, undefined, NOW)).toBe(false);
    expect(shouldProvisionTrial(defaultProfile, "not-a-date", NOW)).toBe(false);
  });

  it("rejects a created_at from the future (clock skew safety)", () => {
    const future = new Date(NOW + 60_000).toISOString();
    expect(shouldProvisionTrial(defaultProfile, future, NOW)).toBe(false);
  });

  it("returns false for a missing profile (that path inserts instead)", () => {
    expect(shouldProvisionTrial(null, fresh, NOW)).toBe(false);
  });
});

describe("#114: trialEndIso", () => {
  it(`is ${TRIAL_DAYS} days out`, () => {
    const end = Date.parse(trialEndIso(NOW));
    expect(end - NOW).toBe(TRIAL_DAYS * 24 * 60 * 60 * 1000);
  });
});
