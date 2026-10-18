/**
 * L2 Regression: Stripe webhook should not contain `as any` casts (#31).
 *
 * Before #31 the webhook used `invoice as any` in two places to reach
 * `parent.subscription_details.subscription`. That erased Stripe SDK
 * typing and was flagged P2 by the codebase review (#31). This test
 * locks in the refactor (InvoiceWithSubscription + extractSubscriptionId)
 * by asserting no `as any` escape hatches remain in the webhook source.
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const WEBHOOK_PATH = resolve(
  __dirname,
  "../../src/app/api/stripe/webhook/route.ts"
);

describe("L2: stripe webhook type safety (#31)", () => {
  it("contains no `as any` casts in executable code", () => {
    const src = readFileSync(WEBHOOK_PATH, "utf-8");
    // Strip block and line comments so the test does not false-positive on
    // explanatory text that legitimately mentions `as any`.
    const stripped = src
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/(^|\s)\/\/.*$/gm, "");
    const matches = stripped.match(/\bas\s+any\b/g) ?? [];
    expect(matches, `found ${matches.length} \`as any\` cast(s) in webhook code`).toHaveLength(0);
  });

  it("contains no @ts-ignore / @ts-nocheck directives", () => {
    const src = readFileSync(WEBHOOK_PATH, "utf-8");
    // Include directives are only valid in comments, so scan raw source.
    expect(/@ts-ignore|@ts-nocheck/.test(src), "webhook should have no @ts-ignore / @ts-nocheck").toBe(false);
  });

  it("exposes the InvoiceWithSubscription helper + extractSubscriptionId", () => {
    const src = readFileSync(WEBHOOK_PATH, "utf-8");
    expect(src).toMatch(/type\s+InvoiceWithSubscription\b/);
    expect(src).toMatch(/function\s+extractSubscriptionId\b/);
  });
});
