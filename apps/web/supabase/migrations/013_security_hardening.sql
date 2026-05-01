-- 013: Security hardening — Codex audit 2026-04-30 findings
-- ----------------------------------------------------------------------------
-- 監査結果 (4並列 codex-auto-review):
--   P0-1  apm_* policies が TO service_role 不在で PUBLIC 適用 → 全テナント read/write
--   P1-1  profiles の UPDATE が列無制限 → ユーザー自身で plan='business' に書き換え可能 (billing bypass)
--   P1-7  "Admins can invite" の WITH CHECK が値無制限 → admin が role='owner', status='active' を直接 INSERT で承諾フローバイパス
--   P1-8  teams の UPDATE が列無制限 → 非owner admin が owner_id/plan/stripe_* 書き換え可能
--   P1-9  user_team_ids(uid)/user_admin_team_ids(uid) が任意 UID を anon/authenticated に EXECUTE 許可 → 他人のチーム列挙可能
--   P1-4  Stripe webhook に event.id dedup 用の processed_stripe_events テーブルなし
--
-- 設計方針:
--   - 列単位 GRANT を導入。billing 関連列 (plan/subscription_status/stripe_*/trial_ends_at) は
--     service_role のみ UPDATE 可能。Stripe webhook と coupon/redeem は service_role 経由で更新する
--     ように route 側を変更する (PR の別コミット)。
--   - SECURITY DEFINER 関数は `auth.uid()` を内部バインドするゼロ引数版に置き換える。旧版は drop。
--   - org_members "Admins can invite" は status='pending' を強制し、role を 'member'/'admin' に制限。
--     owner 昇格は service_role 経由のみ。
-- ----------------------------------------------------------------------------

-- ============================================================================
-- P0-1: APM tables — restrict policies to service_role only
-- ============================================================================
drop policy if exists "Service role full access" on public.apm_agents;
drop policy if exists "Service role full access" on public.apm_metrics;
drop policy if exists "Service role full access" on public.apm_alerts;

create policy "Service role full access" on public.apm_agents
  for all to service_role using (true) with check (true);
create policy "Service role full access" on public.apm_metrics
  for all to service_role using (true) with check (true);
create policy "Service role full access" on public.apm_alerts
  for all to service_role using (true) with check (true);

-- Defense in depth: revoke direct table grants from anon/authenticated.
-- (RLS alone gives empty result set; revoke prevents UPDATE/DELETE attempts even
--  via raw HTTP if a future policy bug re-opens it.)
revoke all on public.apm_agents  from anon, authenticated;
revoke all on public.apm_metrics from anon, authenticated;
revoke all on public.apm_alerts  from anon, authenticated;

-- ============================================================================
-- P1-1: profiles — column-level UPDATE GRANT (billing bypass prevention)
-- ============================================================================
-- Strategy: revoke table-level UPDATE, then re-grant only for non-sensitive columns.
-- Sensitive columns (must NOT be user-writable): plan, subscription_status,
-- stripe_customer_id, stripe_subscription_id, trial_ends_at.
-- These are written exclusively by service_role (Stripe webhook + coupon redeem
-- after route refactor).

revoke update on public.profiles from anon, authenticated;

-- Re-grant UPDATE on non-sensitive columns only.
-- NOTE: column list is derived from 001/003/007/012 migrations. If new
-- non-sensitive columns are added later, extend this GRANT in a follow-up
-- migration.
grant update (
  email,
  full_name,
  avatar_url,
  notification_preferences
) on public.profiles to authenticated;

-- ============================================================================
-- P1-8: teams — column-level UPDATE GRANT
-- ============================================================================
-- Sensitive (service_role only): owner_id, plan, stripe_customer_id,
-- stripe_subscription_id.
revoke update on public.teams from anon, authenticated;

-- Re-grant UPDATE on non-sensitive columns. Adjust if 001 schema differs.
grant update (
  name
) on public.teams to authenticated;

-- ============================================================================
-- P1-7: org_members — Tighten "Admins can invite" WITH CHECK
-- ============================================================================
-- Old policy allowed admin to insert any role/status. New policy:
--   - status MUST be 'pending' (no direct active membership)
--   - role MUST be 'member' / 'admin' / 'viewer' (no owner promotion)
-- Owner promotion is moved to service_role-backed RPC (followup).
-- (VALID_ROLES at src/app/api/org/invite/route.ts is ['admin','member','viewer'].)
drop policy if exists "Admins can invite" on public.org_members;
create policy "Admins can invite"
  on public.org_members
  for insert
  with check (
    status = 'pending'
    and role in ('member', 'admin', 'viewer')
    and (
      org_id in (
        select om.org_id
        from public.org_members om
        where om.user_id = auth.uid()
          and om.role = any (array['owner', 'admin'])
          and om.status = 'active'
      )
      or org_id in (
        select o.id
        from public.organizations o
        where o.owner_id = auth.uid()
      )
    )
  );

-- Separate policy for org owner self-bootstrap (creating an org and
-- inserting themselves as 'owner' / 'active'). Restricted to inserter being
-- the org's owner_id and the row referring to the same auth.uid().
drop policy if exists "Org owners can self-bootstrap as active" on public.org_members;
create policy "Org owners can self-bootstrap as active"
  on public.org_members
  for insert
  with check (
    user_id = auth.uid()
    and role = 'owner'
    and status = 'active'
    and org_id in (
      select o.id
      from public.organizations o
      where o.owner_id = auth.uid()
    )
  );

-- ============================================================================
-- P1-9: user_team_ids/user_admin_team_ids — bind auth.uid() internally
-- ============================================================================
-- Old (006) signature: user_team_ids(uid uuid). The uid argument lets any
-- authenticated user enumerate any other user's team membership. We replace
-- with zero-arg versions that read auth.uid() internally, then update all
-- policies that reference the old signature.

-- Step 1: create zero-arg versions
create or replace function public.user_team_ids()
returns setof uuid
language sql
stable
security definer
set search_path = public, pg_temp
as $$
  select team_id from public.team_members where user_id = auth.uid()
$$;

create or replace function public.user_admin_team_ids()
returns setof uuid
language sql
stable
security definer
set search_path = public, pg_temp
as $$
  select team_id from public.team_members
  where user_id = auth.uid() and role in ('owner', 'admin')
$$;

revoke execute on function public.user_team_ids()        from public;
revoke execute on function public.user_admin_team_ids()  from public;
-- anon role must retain EXECUTE so that RLS policies referencing these
-- functions (teams / team_members / projects / simulation_runs / usage /
-- billing_events) can be evaluated for unauthenticated requests. Without it,
-- a `select * from teams` from anon raises `permission denied for function
-- user_team_ids` before RLS can silently filter to 0 rows. SECURITY DEFINER
-- + auth.uid() (NULL for anon) → the function returns an empty set, so
-- granting to anon does not enable enumeration.
grant execute on function public.user_team_ids()        to authenticated, anon;
grant execute on function public.user_admin_team_ids()  to authenticated, anon;

-- Step 2: re-create all policies that referenced the (uuid) signature.
-- (Mirrors 006_fix_rls_recursion.sql.)

drop policy if exists "Members can view team members" on public.team_members;
create policy "Members can view team members"
  on public.team_members for select
  using (team_id in (select public.user_team_ids()));

drop policy if exists "Team admins can insert team members" on public.team_members;
create policy "Team admins can insert team members"
  on public.team_members for insert
  with check (team_id in (select public.user_admin_team_ids()));

drop policy if exists "Team admins can update team members" on public.team_members;
create policy "Team admins can update team members"
  on public.team_members for update
  using (team_id in (select public.user_admin_team_ids()));

drop policy if exists "Team admins can delete team members" on public.team_members;
create policy "Team admins can delete team members"
  on public.team_members for delete
  using (
    user_id = auth.uid()
    or team_id in (select public.user_admin_team_ids())
  );

drop policy if exists "Team members can view teams" on public.teams;
create policy "Team members can view teams"
  on public.teams for select
  using (id in (select public.user_team_ids()));

drop policy if exists "Team owner can update team" on public.teams;
create policy "Team owner can update team"
  on public.teams for update
  using (id in (select public.user_admin_team_ids()));

drop policy if exists "Team members can view projects" on public.projects;
create policy "Team members can view projects"
  on public.projects for select
  using (team_id in (select public.user_team_ids()));

drop policy if exists "Team members can create projects" on public.projects;
create policy "Team members can create projects"
  on public.projects for insert
  with check (team_id in (select public.user_team_ids()));

drop policy if exists "Team members can update projects" on public.projects;
create policy "Team members can update projects"
  on public.projects for update
  using (team_id in (select public.user_team_ids()));

drop policy if exists "Team admins can delete projects" on public.projects;
create policy "Team admins can delete projects"
  on public.projects for delete
  using (team_id in (select public.user_admin_team_ids()));

drop policy if exists "Team members can view runs" on public.simulation_runs;
create policy "Team members can view runs"
  on public.simulation_runs for select
  using (team_id in (select public.user_team_ids()));

drop policy if exists "Team members can create runs" on public.simulation_runs;
create policy "Team members can create runs"
  on public.simulation_runs for insert
  with check (team_id in (select public.user_team_ids()));

drop policy if exists "Team admins can delete runs" on public.simulation_runs;
create policy "Team admins can delete runs"
  on public.simulation_runs for delete
  using (team_id in (select public.user_admin_team_ids()));

drop policy if exists "Team members can view usage" on public.usage;
create policy "Team members can view usage"
  on public.usage for select
  using (team_id in (select public.user_team_ids()));

drop policy if exists "Team admins can view billing" on public.billing_events;
create policy "Team admins can view billing"
  on public.billing_events for select
  using (team_id in (select public.user_admin_team_ids()));

-- Step 3: drop the old (uuid)-arg versions
drop function if exists public.user_team_ids(uuid);
drop function if exists public.user_admin_team_ids(uuid);

-- ============================================================================
-- P1-4: Stripe webhook idempotency table
-- ============================================================================
-- processed_stripe_events stores Stripe event.id with UNIQUE constraint so
-- the webhook handler can `INSERT ... ON CONFLICT DO NOTHING` and skip
-- duplicates atomically. Optional last_event_at column lets us reject
-- out-of-order events per customer.
create table if not exists public.processed_stripe_events (
  event_id     text primary key,
  event_type   text not null,
  customer_id  text,
  processed_at timestamptz not null default now()
);

create index if not exists idx_processed_stripe_events_customer
  on public.processed_stripe_events (customer_id, processed_at desc);

alter table public.processed_stripe_events enable row level security;

-- service_role only (webhook is server-side and uses service_role key).
drop policy if exists "service_role manages stripe events"
  on public.processed_stripe_events;
create policy "service_role manages stripe events"
  on public.processed_stripe_events
  for all to service_role
  using (true) with check (true);

revoke all on public.processed_stripe_events from anon, authenticated;
