-- 017: #70 finding 3-5 — auth.users FK ON DELETE policy + delete_user_account RPC を 009 テーブル対応に拡張
-- ----------------------------------------------------------------------------
-- 背景:
--   migration 008 (account_delete_atomic) の `delete_user_account(uid uuid)` RPC
--   は teams / team_members / projects / simulation_runs / usage / billing_events
--   / profiles を atomic に削除するが、その後 migration 009 で追加された
--   organizations / org_members / tasks は **未対応**。issue #70 finding 3-5 (Codex
--   2026-04-30 監査) では:
--     - organizations.owner_id REFERENCES auth.users(id) — ON DELETE 未指定 (= NO ACTION)
--     - org_members.user_id   REFERENCES auth.users(id) — 同上
--     - tasks.created_by      REFERENCES auth.users(id) — 同上
--   が指摘されている。production は 0 行で潜在化しているが、行が入った瞬間に
--   `/api/account/delete` が auth.users 削除で FK RESTRICT に当たって fail し、
--   GDPR コンプライアンスが崩れる構造。
--
-- 設計判断 (business decision を含むので PR 本文で議論する):
--   - **organizations.owner_id**: NOT NULL のため SET NULL は不可。CASCADE を採用
--     (= owner 退会 → org 削除)。代替案 (owner 不在で org orphan / ownership transfer
--     義務化) は別 epic 扱い。production は 0 row のため当面影響なし、行が増える前に
--     ownership transfer 機構を入れる前提で CASCADE を取る。
--   - **org_members.user_id**: NULLABLE (pending invitation で email のみの行あり)。
--     CASCADE 採用 (= user 退会 → membership 削除)。pending invitation (user_id NULL)
--     は影響なし。
--   - **tasks.created_by**: NOT NULL のため SET NULL 不可。CASCADE 採用 (= creator 退会
--     → task 削除)。task 履歴を残したい要件は assignee_id の SET NULL + system user
--     reassign で別途対応する epic を立てる。
--   - **tasks.assignee_id REFERENCES org_members(id)**: ON DELETE 未指定。org_members
--     CASCADE で連鎖削除すると assignee_id 持ちの tasks が RESTRICT で fail。SET NULL
--     に変更し、assigner 退会後も task 自体は残す (org_member 単位の退場の semantics)。
--
-- RPC 改訂:
--   FK の ON DELETE は **safety net** であって、本筋は RPC で明示的に処理する設計。
--   RPC 内で:
--     1) tasks.assignee_id を user の org_members.id に紐づく値で NULL 化 (FK SET NULL
--        が効くが、order-of-operations を明示するため先回し)
--     2) tasks.created_by = uid の row を削除 (履歴消失。代替案 = system user に reassign
--        は別 epic)
--     3) org_members から user_id = uid を削除
--     4) organizations から owner_id = uid を削除 (org_id ON DELETE CASCADE で残り
--        org_members / tasks も連鎖削除される)
--     5) (既存) profile / teams / 関連テーブル削除
--   return type に orgs_deleted / org_memberships_deleted / tasks_deleted を追加 (signature
--   変更のため DROP → CREATE)。
-- ----------------------------------------------------------------------------

-- ── 1. FK 改訂 ──

-- (1.a) tasks.assignee_id : ON DELETE SET NULL
alter table public.tasks
  drop constraint if exists tasks_assignee_id_fkey;
alter table public.tasks
  add constraint tasks_assignee_id_fkey
  foreign key (assignee_id) references public.org_members(id) on delete set null;

-- (1.b) org_members.user_id : ON DELETE CASCADE
alter table public.org_members
  drop constraint if exists org_members_user_id_fkey;
alter table public.org_members
  add constraint org_members_user_id_fkey
  foreign key (user_id) references auth.users(id) on delete cascade;

-- (1.c) organizations.owner_id : ON DELETE CASCADE
alter table public.organizations
  drop constraint if exists organizations_owner_id_fkey;
alter table public.organizations
  add constraint organizations_owner_id_fkey
  foreign key (owner_id) references auth.users(id) on delete cascade;

-- (1.d) tasks.created_by : ON DELETE CASCADE
alter table public.tasks
  drop constraint if exists tasks_created_by_fkey;
alter table public.tasks
  add constraint tasks_created_by_fkey
  foreign key (created_by) references auth.users(id) on delete cascade;


-- ── 2. delete_user_account RPC を 009 対応に拡張 ──

-- return type を変更するため DROP → CREATE。signature (uid uuid) は同じ。
-- /api/account/delete/route.ts は error しか見ないので、return type 拡張は
-- caller backward-compatible。
drop function if exists public.delete_user_account(uuid);

create or replace function public.delete_user_account(uid uuid)
returns table (
  teams_deleted          integer,
  runs_deleted           integer,
  projects_deleted       integer,
  memberships_deleted    integer,
  profile_deleted        integer,
  orgs_deleted           integer,
  org_memberships_deleted integer,
  tasks_deleted          integer
)
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  owned_team_ids uuid[];
  v_runs int := 0;
  v_projects int := 0;
  v_teams int := 0;
  v_members int := 0;
  v_profile int := 0;
  v_orgs int := 0;
  v_org_members int := 0;
  v_tasks int := 0;
begin
  -- ── (a) 009 テーブル: tasks → org_members → organizations の順 ──
  -- (a.0) user の org_members.id を assignee として持つ tasks を NULL 化
  --       (assignee_id FK は本 migration で SET NULL に変更済だが、order-of-operations を
  --        明示しておくと意図が読み取りやすい)
  update public.tasks
    set assignee_id = null
    where assignee_id in (select id from public.org_members where user_id = uid);

  -- (a.1) user が created_by の tasks を削除 (created_by NOT NULL のため reassign 不可)
  delete from public.tasks where created_by = uid;
  get diagnostics v_tasks = row_count;

  -- (a.2) user の org_members 行を削除 (NULL pending invitation には触らない)
  delete from public.org_members where user_id = uid;
  get diagnostics v_org_members = row_count;

  -- (a.3) user が owner の organizations を削除 (CASCADE で残 org_members / tasks 連鎖)
  delete from public.organizations where owner_id = uid;
  get diagnostics v_orgs = row_count;

  -- ── (b) 既存ロジック (008 のまま): teams 系列 → profile ──
  select coalesce(array_agg(id), '{}'::uuid[])
    into owned_team_ids
  from public.teams
  where owner_id = uid;

  if array_length(owned_team_ids, 1) is not null then
    delete from public.simulation_runs
      where team_id = any(owned_team_ids);
    get diagnostics v_runs = row_count;

    delete from public.usage
      where team_id = any(owned_team_ids);

    delete from public.billing_events
      where team_id = any(owned_team_ids);

    delete from public.projects
      where team_id = any(owned_team_ids);
    get diagnostics v_projects = row_count;

    delete from public.team_members
      where team_id = any(owned_team_ids);
    get diagnostics v_members = row_count;

    delete from public.teams
      where id = any(owned_team_ids);
    get diagnostics v_teams = row_count;
  end if;

  -- 自分が join している他人の team の membership も削除 (008 と同じ)
  delete from public.team_members
    where user_id = uid;

  -- profile 削除
  delete from public.profiles where id = uid;
  get diagnostics v_profile = row_count;

  return query select
    v_teams, v_runs, v_projects, v_members, v_profile,
    v_orgs, v_org_members, v_tasks;
end;
$$;

-- 008 と同じ権限制御 (service_role からのみ呼び出し可)
revoke all on function public.delete_user_account(uuid) from public;
grant execute on function public.delete_user_account(uuid) to service_role;
