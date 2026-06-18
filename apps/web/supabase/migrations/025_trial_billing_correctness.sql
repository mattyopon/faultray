-- 025: Trial / billing correctness fixes (dual-model review follow-up)
-- ----------------------------------------------------------------------------
-- (A) downgrade_expired_trials — REVENUE LEAK
--     `profiles.subscription_status` DEFAULTs to 'active' (007:32). Self-serve
--     OAuth trials and coupon grants set plan='business'/tier + trial_ends_at
--     but never set subscription_status, so it stays at the 'active' default —
--     which is in the downgrade keep-list (active/trialing/past_due). Result:
--     once trial_ends_at passes, downgrade_expired_trials() SKIPS these rows and
--     they keep their paid plan forever, for free. A profile with an expired
--     trial and NO stripe_customer_id is definitively non-paying, so downgrade it
--     regardless of the masking status default.
--
-- (B) provision_business_trial — TRIAL SILENTLY NEVER GRANTED
--     The OAuth callback (#114) UPDATEs plan/trial_ends_at with the authenticated
--     USER client, but migration 013 revoked authenticated UPDATE on the billing
--     columns (plan/subscription_status/stripe_*/trial_ends_at) → the write is
--     column-grant DENIED and the promised 7-day Business trial never applied for
--     the common (trigger-created profile) path. Provision through a narrowly
--     scoped SECURITY DEFINER RPC that re-asserts the trigger-default precondition
--     (so it can't clobber billing history or re-trial a returning user) and
--     stamps subscription_status='trialing'.
-- ----------------------------------------------------------------------------

-- (A) -------------------------------------------------------------------------
create or replace function public.downgrade_expired_trials()
returns table (id uuid, email text)
language sql
security definer
set search_path = public, pg_temp
as $$
  update public.profiles
  set
    plan = 'free',
    trial_ends_at = null,
    subscription_status = 'canceled'
  where
    trial_ends_at is not null
    and trial_ends_at < now()
    and plan <> 'free'
    and (
      -- No real Stripe subscription → self-serve trial or coupon grant. Once the
      -- trial has expired this is non-paying, so downgrade it even though the
      -- subscription_status DEFAULT ('active') would otherwise keep it.
      stripe_customer_id is null
      or subscription_status is null
      or subscription_status not in ('active', 'trialing', 'past_due')
    )
  returning id, email
$$;

revoke all on function public.downgrade_expired_trials() from public;
grant execute on function public.downgrade_expired_trials() to service_role;

-- (B) -------------------------------------------------------------------------
create or replace function public.provision_business_trial()
returns boolean
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  uid uuid := auth.uid();
  updated_rows int;
begin
  if uid is null then
    return false;
  end if;

  update public.profiles
  set
    plan = 'business',
    trial_ends_at = now() + interval '7 days',
    subscription_status = 'trialing'
  where id = uid
    -- Trigger-created default state only. Re-asserting these means a concurrent
    -- webhook/coupon write between the caller's read and this RPC can't be
    -- clobbered, and a returning free user can't re-grant themselves a trial.
    and plan = 'free'
    and trial_ends_at is null
    and stripe_customer_id is null;

  get diagnostics updated_rows = row_count;
  return updated_rows > 0;
end;
$$;

revoke all on function public.provision_business_trial() from public;
grant execute on function public.provision_business_trial() to authenticated;
