-- 015: org_members self-referential RLS recursion fix + tasks INSERT WITH CHECK
-- ----------------------------------------------------------------------------
-- 背景:
--   009 で導入された org_members の SELECT/INSERT policy は org_members 自身を
--   subquery 参照しており、006 が team_members で除去した同じ pattern を再導入
--   していた。fresh DB で any authenticated read of org_members (および
--   organizations の SELECT が org_members を経由する箇所) が
--   `infinite recursion detected in policy for relation "org_members"` で失敗
--   する。Codex (codex-auto-review) と code-review plugin が独立に flag。
--   実際 PR #95 (#73 pgTAP coverage) で test-rls job が同エラーで停止し顕在化。
--
--   さらに 009 の tasks `Org members can manage tasks` policy は FOR ALL の
--   USING 句のみで WITH CHECK 不在 → INSERT 時に created_by が制約されず、
--   member が他人を created_by に偽装してタスクを作れる (#70 finding 2)。
--
-- 対処:
--   006 (team_members) と同じパターンで以下の SECURITY DEFINER 関数を導入し、
--   各 policy をそれ経由に書き換える:
--
--     public.user_org_ids()        — 自分が active member の org_id 集合
--     public.user_admin_org_ids()  — 自分が owner/admin の org_id 集合
--
--   tasks の FOR ALL policy は SELECT/UPDATE/DELETE と INSERT に分離し、
--   INSERT に WITH CHECK (created_by = auth.uid() AND ...) を追加する。
--
-- 影響:
--   - RLS の機能等価性: 「active member は自org のレコードが見える」「admin/owner
--     は invite ができる」という挙動は不変。性能向上 (subquery が SECURITY
--     DEFINER 関数で 1 回評価) と recursion バグ解消が副次効果。
--   - tasks INSERT は created_by の偽装ができなくなる (breaking change だが
--     現行 API route /api/tasks は req.user.id をそのまま渡すので影響なし)。
-- ----------------------------------------------------------------------------

-- ── Helper functions (auth.uid() 内部バインド、引数なし) ─────
-- 013 の user_team_ids()/user_admin_team_ids() と同設計。
create or replace function public.user_org_ids()
returns setof uuid
language sql
stable
security definer
set search_path = public, pg_temp
as $$
  select org_id from public.org_members
  where user_id = auth.uid() and status = 'active'
$$;

create or replace function public.user_admin_org_ids()
returns setof uuid
language sql
stable
security definer
set search_path = public, pg_temp
as $$
  select org_id from public.org_members
  where user_id = auth.uid()
    and status = 'active'
    and role = any (array['owner', 'admin'])
$$;

-- anon には RLS が org_members を参照する箇所で函数評価が必要なので EXECUTE を残す
-- (anon は auth.uid()=NULL → 関数は空セットを返すので enumeration リスクなし)
revoke execute on function public.user_org_ids()       from public;
revoke execute on function public.user_admin_org_ids() from public;
grant  execute on function public.user_org_ids()       to authenticated, anon;
grant  execute on function public.user_admin_org_ids() to authenticated, anon;

-- ── organizations: SELECT policy を helper 経由に ──
-- INSERT policy "Auth users can create orgs" (with check auth.uid()=owner_id) は
-- 自己参照しないので変更不要。
drop policy if exists "Org members can read their org" on public.organizations;
create policy "Org members can read their org"
  on public.organizations
  for select
  using (
    id in (select public.user_org_ids())
    or owner_id = auth.uid()
  );

-- ── org_members: SELECT/INSERT を helper 経由に (recursion 解消) ──
drop policy if exists "Org members can read members" on public.org_members;
create policy "Org members can read members"
  on public.org_members
  for select
  using (
    org_id in (select public.user_org_ids())
  );

-- INSERT: 013 の "Admins can invite" を helper 経由に書き換え。
-- 013 で導入された status='pending' AND role IN (...) の guard はそのまま維持。
drop policy if exists "Admins can invite" on public.org_members;
create policy "Admins can invite"
  on public.org_members
  for insert
  with check (
    status = 'pending'
    and role in ('member', 'admin', 'viewer')
    and (
      org_id in (select public.user_admin_org_ids())
      or org_id in (
        select o.id
        from public.organizations o
        where o.owner_id = auth.uid()
      )
    )
  );

-- "Org owners can self-bootstrap as active" (013) は organizations のみ参照する
-- ので org_members の自己再帰は起きない。変更不要。

-- ── tasks: FOR ALL を SELECT/UPDATE/DELETE/INSERT に分離 + INSERT WITH CHECK ──
drop policy if exists "Org members can manage tasks" on public.tasks;

create policy "Org members can read tasks"
  on public.tasks for select
  using (org_id in (select public.user_org_ids()));

create policy "Org members can update tasks"
  on public.tasks for update
  using (org_id in (select public.user_org_ids()));

create policy "Org members can delete tasks"
  on public.tasks for delete
  using (org_id in (select public.user_org_ids()));

-- INSERT は created_by を auth.uid() に固定 (#70 finding 2)。
-- 同時に org_id が active membership 内であることを要求。
create policy "Org members can insert tasks"
  on public.tasks for insert
  with check (
    created_by = auth.uid()
    and org_id in (select public.user_org_ids())
  );
