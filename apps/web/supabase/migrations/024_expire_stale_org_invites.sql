-- ============================================================
-- 024: U6 — expire stale pending org invites
--
-- org invites are email-based: a row in public.org_members with
-- status='pending' bound to the invited email (the verified email is the
-- binding; there is no separate invite token). Those pending rows never
-- expired, so a long-abandoned invite stayed acceptable indefinitely — e.g.
-- if an invited mailbox is later recycled to a different person, they could
-- still join the org. This function expires pending invites older than
-- max_age_days by setting status='removed' (the same terminal state an admin
-- removal uses, which the invite route already treats as re-invitable via its
-- `status <> 'removed'` existing-invite check).
--
-- SECURITY DEFINER + service_role-only execute: invoked by the daily
-- /api/cron/trial-expiry cron (service-role client). Idempotent (CREATE OR
-- REPLACE).
-- ============================================================

create or replace function public.expire_stale_org_invites(max_age_days integer default 14)
returns integer
language plpgsql
security definer
set search_path = public
as $$
declare
  expired_count integer;
begin
  if max_age_days is null or max_age_days <= 0 then
    raise exception 'max_age_days must be a positive integer';
  end if;

  update public.org_members
     set status = 'removed'
   where status = 'pending'
     and invited_at < now() - make_interval(days => max_age_days);

  get diagnostics expired_count = row_count;
  return expired_count;
end;
$$;

-- Only the cron's service-role client may run this (it mutates membership rows).
revoke all on function public.expire_stale_org_invites(integer) from public;
revoke all on function public.expire_stale_org_invites(integer) from anon, authenticated;
grant execute on function public.expire_stale_org_invites(integer) to service_role;
