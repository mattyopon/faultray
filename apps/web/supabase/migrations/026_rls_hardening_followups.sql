-- 026: RLS hardening follow-ups (dual-model review)
-- ----------------------------------------------------------------------------
-- (A) actions.system_id cross-tenant reference (#83-class gap)
--     migration 004's "Company owner can insert/update actions" policies check
--     company_id ∈ owned companies but DO NOT constrain system_id. A company
--     owner can therefore create/update an action in their own company that
--     references another company's system_id (a UUID), exactly the gap 018
--     closed for member_systems.system_id and tasks.assignee_id. Add the
--     system_id-side company match (system_id is nullable here — actions.system_id
--     is `on delete set null` — so allow NULL).
--
-- (B) organizations missing DELETE policy
--     /api/org/create inserts the org then the owner membership; on membership
--     failure it rolls back with `delete organizations where id=...` via the
--     authenticated user client. organizations has INSERT + SELECT policies but
--     no DELETE policy, so the rollback is RLS-denied and an owner-less org is
--     left behind. Add an owner-scoped DELETE policy.
--
-- (C) expire_stale_org_invites search_path hardening
--     024 created it with `set search_path = public` (missing pg_temp). Every
--     other SECURITY DEFINER function in this repo pins `public, pg_temp` to
--     prevent pg_temp search-path hijacking. Recreate with the convention.
-- ----------------------------------------------------------------------------

-- (A) actions: enforce system_id same-company on INSERT/UPDATE -----------------
drop policy if exists "Company owner can insert actions" on public.actions;
create policy "Company owner can insert actions"
  on public.actions for insert
  with check (
    company_id in (
      select id from public.companies where owner_id = auth.uid()
    )
    and (
      system_id is null
      or system_id in (
        select s.id
        from public.systems s
        join public.companies c on c.id = s.company_id
        where c.owner_id = auth.uid()
          and s.company_id = actions.company_id
      )
    )
  );

drop policy if exists "Company owner can update actions" on public.actions;
create policy "Company owner can update actions"
  on public.actions for update
  using (
    company_id in (
      select id from public.companies where owner_id = auth.uid()
    )
  )
  with check (
    company_id in (
      select id from public.companies where owner_id = auth.uid()
    )
    and (
      system_id is null
      or system_id in (
        select s.id
        from public.systems s
        join public.companies c on c.id = s.company_id
        where c.owner_id = auth.uid()
          and s.company_id = actions.company_id
      )
    )
  );

-- (B) organizations: owner-scoped DELETE policy -------------------------------
drop policy if exists "Org owners can delete their org" on public.organizations;
create policy "Org owners can delete their org"
  on public.organizations for delete
  using (owner_id = auth.uid());

-- (C) expire_stale_org_invites: pin search_path = public, pg_temp -------------
-- Faithful copy of 024's body; only the search_path is changed.
create or replace function public.expire_stale_org_invites(max_age_days integer default 14)
returns integer
language plpgsql
security definer
set search_path = public, pg_temp
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

revoke all on function public.expire_stale_org_invites(integer) from public;
revoke all on function public.expire_stale_org_invites(integer) from anon, authenticated;
grant execute on function public.expire_stale_org_invites(integer) to service_role;
