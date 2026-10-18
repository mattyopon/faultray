/**
 * Trial-provisioning decision logic for the OAuth callback (#114).
 *
 * The `handle_new_user` trigger (migration 001) creates a profile row at
 * sign-up, so the callback's "no profile yet → grant trial" branch never ran
 * and new users landed without the promised 7-day Business trial. The fix
 * provisions the trial on first sign-in when the profile is still in its
 * trigger-created default state AND the auth user itself was created moments
 * ago. The freshness gate is what keeps this from upgrading long-standing
 * free users who simply log in again.
 *
 * Kept as a pure function so the branch matrix is unit-testable without a
 * Supabase session.
 */

export const TRIAL_DAYS = 7;

/** Auth-user age within which a default-state profile counts as a fresh signup. */
export const FRESH_SIGNUP_WINDOW_MS = 10 * 60 * 1000;

export interface TrialProfileState {
  plan?: string | null;
  trial_ends_at?: string | null;
  stripe_customer_id?: string | null;
}

export function shouldProvisionTrial(
  profile: TrialProfileState | null | undefined,
  userCreatedAt: string | null | undefined,
  now: number = Date.now()
): boolean {
  if (!profile) return false;
  // Default trigger-created state only: any prior trial, paid tier, or Stripe
  // linkage means this account has billing history we must not overwrite.
  if (profile.plan !== "free") return false;
  if (profile.trial_ends_at) return false;
  if (profile.stripe_customer_id) return false;

  if (!userCreatedAt) return false;
  const createdMs = Date.parse(userCreatedAt);
  if (Number.isNaN(createdMs)) return false;

  const age = now - createdMs;
  return age >= 0 && age < FRESH_SIGNUP_WINDOW_MS;
}

export function trialEndIso(now: number = Date.now()): string {
  return new Date(now + TRIAL_DAYS * 24 * 60 * 60 * 1000).toISOString();
}
