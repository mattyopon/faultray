-- ============================================================
-- Fix: team_members RLS policies cause infinite recursion (#28 で検出)
--
-- 背景:
--   001_initial_schema.sql と 002_rls_update_delete_policies.sql の
--   team_members 対象 policy が自テーブルを subquery で参照していた:
--
--     select team_id from public.team_members where user_id = auth.uid()
--
--   team_members の select / insert / update / delete policy 内で
--   上記 subquery を評価すると、その team_members select が再び policy を
--   評価し → 無限再帰 → Postgres が `infinite recursion detected in
--   policy for relation "team_members"` で error。
--
--   他テーブル (teams/projects/simulation_runs/usage/billing_events) の
--   policy も同じ subquery を含むため、間接的に同エラーが伝播していた。
--
-- 対処:
--   SECURITY DEFINER 関数 `public.user_team_ids(uid)` と
--   `public.user_admin_team_ids(uid)` を用意し、RLS を bypass して
--   team_members を参照する。policy はこの関数の結果 set と照合する。
--
-- 影響:
--   全 RLS policy の機能は等価。production で本バグが露見していた可能性あり
--   (team_members への直接 select で error 返却)。supabase/tests/rls/ の
--   pgTAP テストで regression lock される。
-- ============================================================

-- ── Helper 関数 ───────────────────────────────────────────────
create or replace function public.user_team_ids(uid uuid)
returns setof uuid
language sql
stable
security definer
set search_path = public, pg_temp
as $$
  select team_id from public.team_members where user_id = uid
$$;

create or replace function public.user_admin_team_ids(uid uuid)
returns setof uuid
language sql
stable
security definer
set search_path = public, pg_temp
as $$
  select team_id from public.team_members
  where user_id = uid and role in ('owner', 'admin')
$$;

-- 実行権限を authenticated / anon に付与 (service_role は bypass で不要)
grant execute on function public.user_team_ids(uuid) to authenticated, anon;
grant execute on function public.user_admin_team_ids(uuid) to authenticated, anon;

-- ── team_members 自己参照 policy を修正 ───────────────────────

-- SELECT (001)
drop policy if exists "Members can view team members" on public.team_members;
create policy "Members can view team members"
  on public.team_members for select
  using (team_id in (select public.user_team_ids(auth.uid())));

-- INSERT (002)
drop policy if exists "Team admins can insert team members" on public.team_members;
create policy "Team admins can insert team members"
  on public.team_members for insert
  with check (team_id in (select public.user_admin_team_ids(auth.uid())));

-- UPDATE (002)
drop policy if exists "Team admins can update team members" on public.team_members;
create policy "Team admins can update team members"
  on public.team_members for update
  using (team_id in (select public.user_admin_team_ids(auth.uid())));

-- DELETE (002) — members can remove themselves OR admins can remove anyone
drop policy if exists "Team admins can delete team members" on public.team_members;
create policy "Team admins can delete team members"
  on public.team_members for delete
  using (
    user_id = auth.uid()
    or team_id in (select public.user_admin_team_ids(auth.uid()))
  );

-- ── 他テーブルの policy も helper 経由に統一 ─────────────────
-- (subquery 書換は再帰エラーの直接原因ではないが、統一性・保守性・性能のため)

drop policy if exists "Team members can view teams" on public.teams;
create policy "Team members can view teams"
  on public.teams for select
  using (id in (select public.user_team_ids(auth.uid())));

drop policy if exists "Team owner can update team" on public.teams;
create policy "Team owner can update team"
  on public.teams for update
  using (id in (select public.user_admin_team_ids(auth.uid())));

drop policy if exists "Team members can view projects" on public.projects;
create policy "Team members can view projects"
  on public.projects for select
  using (team_id in (select public.user_team_ids(auth.uid())));

drop policy if exists "Team members can create projects" on public.projects;
create policy "Team members can create projects"
  on public.projects for insert
  with check (team_id in (select public.user_team_ids(auth.uid())));

drop policy if exists "Team members can update projects" on public.projects;
create policy "Team members can update projects"
  on public.projects for update
  using (team_id in (select public.user_team_ids(auth.uid())));

drop policy if exists "Team admins can delete projects" on public.projects;
create policy "Team admins can delete projects"
  on public.projects for delete
  using (team_id in (select public.user_admin_team_ids(auth.uid())));

drop policy if exists "Team members can view runs" on public.simulation_runs;
create policy "Team members can view runs"
  on public.simulation_runs for select
  using (team_id in (select public.user_team_ids(auth.uid())));

drop policy if exists "Team members can create runs" on public.simulation_runs;
create policy "Team members can create runs"
  on public.simulation_runs for insert
  with check (team_id in (select public.user_team_ids(auth.uid())));

drop policy if exists "Team admins can delete runs" on public.simulation_runs;
create policy "Team admins can delete runs"
  on public.simulation_runs for delete
  using (team_id in (select public.user_admin_team_ids(auth.uid())));

drop policy if exists "Team members can view usage" on public.usage;
create policy "Team members can view usage"
  on public.usage for select
  using (team_id in (select public.user_team_ids(auth.uid())));

drop policy if exists "Team admins can view billing" on public.billing_events;
create policy "Team admins can view billing"
  on public.billing_events for select
  using (team_id in (select public.user_admin_team_ids(auth.uid())));
