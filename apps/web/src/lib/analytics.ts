/**
 * Google Analytics 4 event tracking utility.
 *
 * Events are silently ignored when:
 *  - Running server-side (window is undefined)
 *  - NEXT_PUBLIC_GA_ID is not set
 *  - gtag has not been initialised yet (script not loaded)
 */
export function trackEvent(
  event: string,
  params?: Record<string, unknown>
): void {
  if (typeof window === "undefined") {
    return;
  }
  const w = window as unknown as { gtag?: (...args: unknown[]) => void };
  if (!w.gtag) {
    return;
  }
  w.gtag("event", event, params ?? {});
}

/** Convenience wrappers for the main product events */
export const analytics = {
  /** New user registered */
  signup: () => trackEvent("signup"),

  /** User ran their first simulation */
  firstSimulation: () => trackEvent("first_simulation"),

  /** User clicked a checkout button */
  checkoutStart: (plan: string, interval: string) =>
    trackEvent("checkout_start", { plan, interval }),

  /** Stripe checkout.session.completed received */
  subscriptionCreated: (plan: string) =>
    trackEvent("subscription_created", { plan }),

  /** Coupon applied successfully */
  couponRedeemed: (code: string, tier: string) =>
    trackEvent("coupon_redeemed", { coupon_code: code, tier }),
} as const;
