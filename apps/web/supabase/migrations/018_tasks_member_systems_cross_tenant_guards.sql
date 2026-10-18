-- 018: #80 + #83 — cross-tenant data integrity guards
-- ----------------------------------------------------------------------------
-- #80 (tasks.assignee_id cross-tenant): tasks INSERT/UPDATE で attacker が
--      他 org の `org_members.id` を assignee に詰める可能性。RLS USING で row
--      自体は隔離されるが、新規 row に他 org の reference が紛れ込むのは
--      下流 UI/通知/分析で leak の温床になる。WITH CHECK で assignee_id が
--      同 org_id の active member に属することを強制する。
--      app side (api/tasks routes) でも先に reject する double-defense。
--
-- #83 (member_systems cross-company): migration 004 の `Company owner can
--      insert/update member_systems` policies は member_id の所属 company を
--      確認するが system_id は無検査。同じ company owner であれば自社 member
--      の row を作れるが、system_id に他社の system を指定可能。
--      WITH CHECK に system_id 側の company match 条件を追加する。
-- ----------------------------------------------------------------------------

-- ── 1. tasks: assignee_id 同 org check + UPDATE WITH CHECK 追加 ──
-- 015 で導入済の SELECT/UPDATE/DELETE/INSERT policies のうち、INSERT と
-- UPDATE を WITH CHECK 強化する。SELECT/DELETE はそのまま。

drop policy if exists "Org members can insert tasks" on public.tasks;
drop policy if exists "Org members can update tasks" on public.tasks;

-- INSERT: 015 の created_by + org_id check に assignee_id same-org guard を追加
create policy "Org members can insert tasks"
  on public.tasks for insert
  with check (
    created_by = auth.uid()
    and org_id in (select public.user_org_ids())
    and (
      assignee_id is null
      or exists (
        select 1 from public.org_members om
        where om.id = assignee_id
          and om.org_id = public.tasks.org_id
          and om.status = 'active'
      )
    )
  );

-- UPDATE: 元 USING のみ → WITH CHECK で post-update 値も同 RLS scope を強制
-- (cross-tenant 移動防止 + assignee_id same-org 維持)
create policy "Org members can update tasks"
  on public.tasks for update
  using (org_id in (select public.user_org_ids()))
  with check (
    org_id in (select public.user_org_ids())
    and (
      assignee_id is null
      or exists (
        select 1 from public.org_members om
        where om.id = assignee_id
          and om.org_id = public.tasks.org_id
          and om.status = 'active'
      )
    )
  );


-- ── 2. member_systems: INSERT/UPDATE policy を再作成し system_id 側の同 company を強制 ──
-- production では migration 004 の "Company owner can ..." policies が現在不在で
-- "Allow read access" の SELECT のみ存在 (drift)。fresh env では 004 で作られる
-- ため、IF EXISTS で安全に DROP → CREATE する。
-- どちらの env でも同一の最終状態 (member.company_id = system.company_id 強制
-- された INSERT/UPDATE policy) に揃える。

drop policy if exists "Company owner can insert member_systems"
  on public.member_systems;
drop policy if exists "Company owner can update member_systems"
  on public.member_systems;

create policy "Company owner can insert member_systems"
  on public.member_systems for insert
  with check (
    exists (
      select 1
      from public.members m
      join public.companies c on c.id = m.company_id
      join public.systems s on s.company_id = c.id
      where m.id = member_systems.member_id
        and s.id = member_systems.system_id
        and c.owner_id = auth.uid()
    )
  );

create policy "Company owner can update member_systems"
  on public.member_systems for update
  using (
    exists (
      select 1
      from public.members m
      join public.companies c on c.id = m.company_id
      where m.id = member_systems.member_id
        and c.owner_id = auth.uid()
    )
  )
  with check (
    exists (
      select 1
      from public.members m
      join public.companies c on c.id = m.company_id
      join public.systems s on s.company_id = c.id
      where m.id = member_systems.member_id
        and s.id = member_systems.system_id
        and c.owner_id = auth.uid()
    )
  );
