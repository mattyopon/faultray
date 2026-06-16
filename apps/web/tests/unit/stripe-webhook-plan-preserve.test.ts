/**
 * L2 Regression: #112 — Stripe webhook must NEVER fall back to a paid tier
 * when plan resolution fails. The previous code used
 *
 *     let resolvedPlan: PlanTier = "pro"; // fallback
 *     ...
 *     resolvedPlan = (priceId ? planTierFromPriceId(priceId) : null) ?? "pro";
 *
 * so a transient Stripe retrieve error or an unmapped price ID silently
 * rewrote starter / business customers onto "pro". Preserve semantics
 * (PlanTier | null with null = keep current) must hold from here on.
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const WEBHOOK_PATH = resolve(
  __dirname,
  "../../src/app/api/stripe/webhook/route.ts"
);

function stripComments(src: string): string {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/(^|\s)\/\/.*$/gm, "");
}

describe("L2: stripe webhook plan-preserve (#112)", () => {
  it("never substitutes a paid tier as a fallback in executable code", () => {
    const src = stripComments(readFileSync(WEBHOOK_PATH, "utf-8"));
    // ?? "pro" or ?? "starter" / "business" — the old fallback shape.
    expect(src).not.toMatch(/\?\?\s*["'](?:pro|starter|business)["']/);
    // Annotated default: `let resolvedPlan: PlanTier = "pro"`.
    expect(src).not.toMatch(/:\s*PlanTier\s*=\s*["'](?:pro|starter|business)["']/);
  });

  it("downgrade to 'free' only happens on explicit cancel/delete events", () => {
    const src = stripComments(readFileSync(WEBHOOK_PATH, "utf-8"));
    // The two surviving "free" assignments live inside subscription.updated
    // (status branch handling) and subscription.deleted; both are intentional.
    // What we forbid here is `?? "free"` as a generic fallback.
    expect(src).not.toMatch(/\?\?\s*["']free["']/);
  });

  it("updateUserPlan and updateUserByCustomerId accept PlanTier | null", () => {
    const src = readFileSync(WEBHOOK_PATH, "utf-8");
    expect(src).toMatch(/async function updateUserPlan\([^)]*plan:\s*PlanTier\s*\|\s*null/);
    expect(src).toMatch(/async function updateUserByCustomerId\([^)]*plan:\s*PlanTier\s*\|\s*null/);
  });

  it("payment_failed initializes resolvedPlan to null (not 'pro')", () => {
    const src = readFileSync(WEBHOOK_PATH, "utf-8");
    expect(src).toMatch(/let\s+resolvedPlan:\s*PlanTier\s*\|\s*null\s*=\s*null/);
  });

  it("payment_succeeded resolves resolvedPlan via price→metadata fallback, no paid-tier default (#112/#144)", () => {
    const src = readFileSync(WEBHOOK_PATH, "utf-8");
    // #144: checkout uses inline price_data, so the price ID is unmapped and the
    // tier must be recovered from the trusted subscription metadata.plan. The
    // type stays `PlanTier | null` (null = preserve current) — never a hardcoded
    // paid tier (the `?? "pro"` shapes are forbidden by the tests above).
    expect(src).toMatch(
      /const\s+resolvedPlan:\s*PlanTier\s*\|\s*null\s*=\s*\(priceId\s*\?\s*planTierFromPriceId\(priceId\)\s*:\s*null\)\s*\?\?\s*planTierFromMetadata\(subscription\.metadata\?\.plan\)/
    );
  });
});
