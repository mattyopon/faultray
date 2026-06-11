-- ============================================================
-- RLS multi-tenant isolation tests (#28, #73)
--
-- 対象 (legacy): profiles / teams / team_members / projects / simulation_runs /
--                 usage / billing_events の RLS policies
-- 対象 (#73 追加): organizations / org_members / tasks (migration 009/013)
--
-- 検証シナリオ (legacy):
--   User A (team X owner), User B (team X member), User C (team Y owner)
--   - 自分の team のデータは見える
--   - 他人の team のデータは見えない
--   - member は admin 権限が必要な操作 (team update, insert member 等) ができない
--   - anon (未ログイン) は一切見えない
--
-- 検証シナリオ (org/tasks, #73):
--   User A は org_p の admin (active), User B は org_p の member (active),
--   User C は org_q の owner (active, organizations.owner_id でもある)
--   - SELECT cross-org isolation
--   - org_members INSERT: admin は member/admin/viewer の pending invite のみ許可
--                         (#70 P1-7 → migration 013 で fix 済を assert)
--   - org_members INSERT: org owner self-bootstrap (role='owner', status='active', user_id=self)
--                         は許可される (migration 013 line 110-122)
--   - tasks: 自org は CRUD 可能、cross-org は block。created_by は auth.uid() に固定
--           (#70 finding 2 → migration 015 で fix 済を assert)
--   - 関連 fix: migration 015 で org_members の self-referential RLS recursion を
--               SECURITY DEFINER 関数経由に書き換えて解消 (#70 finding 1)
--
-- 実行方法 (ローカル Supabase):
--   supabase db reset  # migrations 全適用
--   psql "postgresql://postgres@localhost:54322/postgres" \
--        -f supabase/tests/rls/multitenant.test.sql
-- (ローカル開発用 postgres のデフォルトパスワードは Supabase CLI が管理)
--
-- CI: .github/workflows/ci.yml の test-rls job で自動実行される
-- ============================================================

begin;

-- pgTAP 拡張 (必要なら)
create extension if not exists pgtap;

-- ---------- テストプラン ----------
-- legacy 7 テーブル        : 40 assertion (#28)
-- org/tasks 拡張           : 33 assertion (#73)
--   organizations          :  8  (SELECT × 6 + INSERT lives/throws × 2)
--   org_members            : 12  (SELECT × 6 + INSERT lives × 2 + INSERT throws × 4)
--   tasks                  :  9  (SELECT × 6 + INSERT lives × 2 + TODO forgery × 1)
--   anon                   :  4  (SELECT × 3 + INSERT throw × 1)
-- contact_requests/coupons :  8 assertion (#72)
--   contact_requests       :  4  (anon INSERT lives + SELECT 0row, auth INSERT lives + SELECT 0row)
--   coupons                :  4  (auth SELECT 1row, anon SELECT 0row, auth INSERT throws, auth UPDATE 0 affected)
-- tasks.assignee_id guard  :  4 assertion (#80, migration 018)
--   INSERT same-org lives + cross-org throws + NULL lives + UPDATE cross-org throws
-- member_systems WITH CHECK:  2 assertion (#83, migration 018, structural existence)
-- delete_user_account RPC  :  6 assertion (#70 finding 3-5, migration 017)
--   pre/post check         :  6  (org_p delete via owner CASCADE + cascade chain, org_q untouched)
select plan(98);

-- ============================================================
-- Setup: auth.users を直接 INSERT して 3 ユーザー + 2 team を作成
-- (auth.users は Supabase が管理するが test では raw insert で代替)
-- ============================================================

-- ユーザー ID を固定
\set user_a_id '11111111-1111-1111-1111-111111111111'
\set user_b_id '22222222-2222-2222-2222-222222222222'
\set user_c_id '33333333-3333-3333-3333-333333333333'
\set team_x_id '44444444-4444-4444-4444-444444444444'
\set team_y_id '55555555-5555-5555-5555-555555555555'
-- #73 organizations / tasks 用 ID 固定
\set org_p_id   'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
\set org_q_id   'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'
\set task_p_id  'cccccccc-cccc-cccc-cccc-cccccccccccc'
\set task_q_id  'dddddddd-dddd-dddd-dddd-dddddddddddd'
-- #80 org_members.id を固定 (assignee_id same-org guard test 用)
\set om_a_p_id  'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee'
\set om_b_p_id  'ffffffff-ffff-ffff-ffff-ffffffffffff'
\set om_c_q_id  '00000000-1111-2222-3333-444444444444'

-- auth.users (最小フィールド)
insert into auth.users (id, email, raw_user_meta_data, aud, role)
values
  (:'user_a_id'::uuid, 'a@test.local', '{"full_name":"User A"}'::jsonb, 'authenticated', 'authenticated'),
  (:'user_b_id'::uuid, 'b@test.local', '{"full_name":"User B"}'::jsonb, 'authenticated', 'authenticated'),
  (:'user_c_id'::uuid, 'c@test.local', '{"full_name":"User C"}'::jsonb, 'authenticated', 'authenticated')
on conflict (id) do nothing;

-- handle_new_user trigger で profiles + teams が作成されるが、
-- 既存 trigger に依存すると brittle なので RLS bypass (SECURITY DEFINER 相当) で直接 insert する。
-- ここでは trigger 経由の自動生成を待たず、テスト用に明示的に作成する。

-- trigger-created default teams を削除 (test 向けに deterministic state)
set local session_replication_role = replica;  -- triggers OFF

-- #73: org/tasks も deterministic にするため事前 cleanup
-- (FK 順: tasks → org_members → organizations。assignee_id は org_members を参照)
delete from public.tasks
  where created_by in (:'user_a_id'::uuid, :'user_b_id'::uuid, :'user_c_id'::uuid);
delete from public.org_members
  where user_id in (:'user_a_id'::uuid, :'user_b_id'::uuid, :'user_c_id'::uuid);
delete from public.organizations
  where owner_id in (:'user_a_id'::uuid, :'user_b_id'::uuid, :'user_c_id'::uuid);

delete from public.team_members
  where user_id in (:'user_a_id'::uuid, :'user_b_id'::uuid, :'user_c_id'::uuid);
delete from public.teams
  where owner_id in (:'user_a_id'::uuid, :'user_b_id'::uuid, :'user_c_id'::uuid);
delete from public.profiles
  where id in (:'user_a_id'::uuid, :'user_b_id'::uuid, :'user_c_id'::uuid);

-- profiles: A, B, C
insert into public.profiles (id, email, full_name) values
  (:'user_a_id'::uuid, 'a@test.local', 'User A'),
  (:'user_b_id'::uuid, 'b@test.local', 'User B'),
  (:'user_c_id'::uuid, 'c@test.local', 'User C');

-- team X: owner A, member B
insert into public.teams (id, name, owner_id) values (:'team_x_id'::uuid, 'Team X', :'user_a_id'::uuid);
insert into public.team_members (team_id, user_id, role) values
  (:'team_x_id'::uuid, :'user_a_id'::uuid, 'owner'),
  (:'team_x_id'::uuid, :'user_b_id'::uuid, 'member');

-- team Y: owner C
insert into public.teams (id, name, owner_id) values (:'team_y_id'::uuid, 'Team Y', :'user_c_id'::uuid);
insert into public.team_members (team_id, user_id, role) values
  (:'team_y_id'::uuid, :'user_c_id'::uuid, 'owner');

-- projects: 1 per team
insert into public.projects (id, team_id, name) values
  ('66666666-6666-6666-6666-666666666666'::uuid, :'team_x_id'::uuid, 'X project'),
  ('77777777-7777-7777-7777-777777777777'::uuid, :'team_y_id'::uuid, 'Y project');

-- simulation_runs: 1 per team
insert into public.simulation_runs (id, project_id, team_id, user_id, overall_score) values
  ('88888888-8888-8888-8888-888888888888'::uuid,
   '66666666-6666-6666-6666-666666666666'::uuid, :'team_x_id'::uuid, :'user_a_id'::uuid, 80),
  ('99999999-9999-9999-9999-999999999999'::uuid,
   '77777777-7777-7777-7777-777777777777'::uuid, :'team_y_id'::uuid, :'user_c_id'::uuid, 70);

-- usage: 1 per team
insert into public.usage (team_id, month, simulation_count) values
  (:'team_x_id'::uuid, '2026-04', 5),
  (:'team_y_id'::uuid, '2026-04', 3);

-- billing_events: 1 per team
insert into public.billing_events (team_id, event_type, data) values
  (:'team_x_id'::uuid, 'test_event', '{"n":1}'::jsonb),
  (:'team_y_id'::uuid, 'test_event', '{"n":2}'::jsonb);

-- ============================================================
-- #73 SEED: organizations / org_members / tasks
-- ============================================================
-- org_p: owner=A, A は admin (active), B は member (active)
-- org_q: owner=C, C は owner (active)
insert into public.organizations (id, name, owner_id) values
  (:'org_p_id'::uuid, 'Org P', :'user_a_id'::uuid),
  (:'org_q_id'::uuid, 'Org Q', :'user_c_id'::uuid);

insert into public.org_members (id, org_id, user_id, email, role, status) values
  (:'om_a_p_id'::uuid, :'org_p_id'::uuid, :'user_a_id'::uuid, 'a@test.local', 'admin',  'active'),
  (:'om_b_p_id'::uuid, :'org_p_id'::uuid, :'user_b_id'::uuid, 'b@test.local', 'member', 'active'),
  (:'om_c_q_id'::uuid, :'org_q_id'::uuid, :'user_c_id'::uuid, 'c@test.local', 'owner',  'active');

-- tasks: 1 per org (assignee_id は省略 → null)
insert into public.tasks (id, org_id, title, created_by) values
  (:'task_p_id'::uuid, :'org_p_id'::uuid, 'Task P1', :'user_a_id'::uuid),
  (:'task_q_id'::uuid, :'org_q_id'::uuid, 'Task Q1', :'user_c_id'::uuid);

set local session_replication_role = origin;  -- triggers ON

-- ============================================================
-- ヘルパー関数: 指定 user として RLS を再評価する
-- ============================================================

create or replace function test_as_user(user_uuid uuid) returns void as $$
begin
  perform set_config('role', 'authenticated', true);
  perform set_config('request.jwt.claims',
    jsonb_build_object('sub', user_uuid::text, 'role', 'authenticated')::text,
    true);
end;
$$ language plpgsql;

create or replace function test_as_anon() returns void as $$
begin
  perform set_config('role', 'anon', true);
  perform set_config('request.jwt.claims',
    jsonb_build_object('role', 'anon')::text, true);
end;
$$ language plpgsql;

create or replace function test_as_service_role() returns void as $$
begin
  perform set_config('role', 'service_role', true);
end;
$$ language plpgsql;

-- ============================================================
-- profiles: self-read / cross-read / self-update のみ
-- ============================================================

select test_as_user(:'user_a_id'::uuid);

select is(
  (select count(*)::int from public.profiles where id = :'user_a_id'::uuid),
  1,
  'profiles: User A can see own profile'
);

select is(
  (select count(*)::int from public.profiles where id = :'user_b_id'::uuid),
  0,
  'profiles: User A CANNOT see User B profile'
);

select is(
  (select count(*)::int from public.profiles where id = :'user_c_id'::uuid),
  0,
  'profiles: User A CANNOT see User C profile (other tenant)'
);

-- ============================================================
-- teams: own membership only
-- ============================================================

select is(
  (select count(*)::int from public.teams where id = :'team_x_id'::uuid),
  1,
  'teams: User A (owner) can see own team X'
);

select is(
  (select count(*)::int from public.teams where id = :'team_y_id'::uuid),
  0,
  'teams: User A CANNOT see team Y (other tenant)'
);

select test_as_user(:'user_b_id'::uuid);

select is(
  (select count(*)::int from public.teams where id = :'team_x_id'::uuid),
  1,
  'teams: User B (member) can see team X'
);

select is(
  (select count(*)::int from public.teams where id = :'team_y_id'::uuid),
  0,
  'teams: User B CANNOT see team Y (other tenant)'
);

select test_as_user(:'user_c_id'::uuid);

select is(
  (select count(*)::int from public.teams where id = :'team_x_id'::uuid),
  0,
  'teams: User C CANNOT see team X (other tenant)'
);

-- ============================================================
-- team_members: visible only for own teams
-- ============================================================

select test_as_user(:'user_a_id'::uuid);

select is(
  (select count(*)::int from public.team_members where team_id = :'team_x_id'::uuid),
  2,
  'team_members: User A sees both members of team X'
);

select is(
  (select count(*)::int from public.team_members where team_id = :'team_y_id'::uuid),
  0,
  'team_members: User A CANNOT see team Y membership'
);

-- ============================================================
-- projects: team scope
-- ============================================================

select test_as_user(:'user_a_id'::uuid);

select is(
  (select count(*)::int from public.projects where team_id = :'team_x_id'::uuid),
  1,
  'projects: User A sees own team X project'
);

select is(
  (select count(*)::int from public.projects where team_id = :'team_y_id'::uuid),
  0,
  'projects: User A CANNOT see team Y projects'
);

select test_as_user(:'user_c_id'::uuid);

select is(
  (select count(*)::int from public.projects where team_id = :'team_x_id'::uuid),
  0,
  'projects: User C CANNOT see team X projects'
);

-- ============================================================
-- simulation_runs: team scope
-- ============================================================

select test_as_user(:'user_a_id'::uuid);

select is(
  (select count(*)::int from public.simulation_runs where team_id = :'team_x_id'::uuid),
  1,
  'simulation_runs: User A sees team X runs'
);

select is(
  (select count(*)::int from public.simulation_runs where team_id = :'team_y_id'::uuid),
  0,
  'simulation_runs: User A CANNOT see team Y runs'
);

-- ============================================================
-- usage: team scope (select only)
-- ============================================================

select test_as_user(:'user_a_id'::uuid);

select is(
  (select count(*)::int from public.usage where team_id = :'team_x_id'::uuid),
  1,
  'usage: User A sees team X usage'
);

select is(
  (select count(*)::int from public.usage where team_id = :'team_y_id'::uuid),
  0,
  'usage: User A CANNOT see team Y usage'
);

-- ============================================================
-- billing_events: owner/admin only
-- ============================================================

select test_as_user(:'user_a_id'::uuid);  -- owner of team X

select is(
  (select count(*)::int from public.billing_events where team_id = :'team_x_id'::uuid),
  1,
  'billing_events: User A (owner) sees team X billing'
);

select is(
  (select count(*)::int from public.billing_events where team_id = :'team_y_id'::uuid),
  0,
  'billing_events: User A CANNOT see team Y billing'
);

select test_as_user(:'user_b_id'::uuid);  -- member of team X

select is(
  (select count(*)::int from public.billing_events where team_id = :'team_x_id'::uuid),
  0,
  'billing_events: User B (member, not admin) CANNOT see team X billing'
);

-- ============================================================
-- WRITE operations: role escalation / cross-tenant block
-- ============================================================

-- User B (member) should not be able to UPDATE team X metadata
select test_as_user(:'user_b_id'::uuid);

select lives_ok(
  $$ update public.teams set name = 'Hacked' where id = '44444444-4444-4444-4444-444444444444'::uuid $$,
  'teams: User B UPDATE statement does not throw (silent RLS filter)'
);

select test_as_service_role();

select is(
  (select name from public.teams where id = :'team_x_id'::uuid),
  'Team X',
  'teams: User B UPDATE actually had 0 effect (RLS blocked row)'
);

-- User B (member) should not be able to INSERT into team_members (admin only)
select test_as_user(:'user_b_id'::uuid);

-- pgTAP 3-arg throws_ok(text, text, text) は 2 引数目を errmsg として解釈するため
-- SQLSTATE を強制したい場合は char(5) にキャストする必要がある。
-- ここでは「RLS により INSERT がブロックされる」ことだけ保証できればよいので
-- 2-arg form (query, description) を使い「何らかの error が throw される」を
-- assert する。
-- pgTAP throws_ok(sql, errcode, errmsg, description): errcode/errmsg を NULL にすると
-- 「何らかの error が throw される」を assert する形になる
select throws_ok(
  $$ insert into public.team_members (team_id, user_id, role)
     values ('44444444-4444-4444-4444-444444444444'::uuid,
             '33333333-3333-3333-3333-333333333333'::uuid, 'admin') $$,
  NULL::text, NULL::text,
  'team_members: User B (member, not admin) cannot INSERT new team member'
);

-- User A (owner of X) cannot INSERT member into team Y
select test_as_user(:'user_a_id'::uuid);

select throws_ok(
  $$ insert into public.team_members (team_id, user_id, role)
     values ('55555555-5555-5555-5555-555555555555'::uuid,
             '11111111-1111-1111-1111-111111111111'::uuid, 'member') $$,
  NULL::text, NULL::text,
  'team_members: User A cannot INSERT into team Y membership'
);

-- User A cannot UPDATE team Y (cross-tenant)
select test_as_user(:'user_a_id'::uuid);

select lives_ok(
  $$ update public.teams set name = 'HackedY' where id = '55555555-5555-5555-5555-555555555555'::uuid $$,
  'teams: User A UPDATE on team Y does not throw (silent RLS filter)'
);

select test_as_service_role();

select is(
  (select name from public.teams where id = :'team_y_id'::uuid),
  'Team Y',
  'teams: User A UPDATE on team Y had 0 effect (RLS blocked)'
);

-- User A (owner of X) cannot DELETE team Y
select test_as_user(:'user_a_id'::uuid);

select lives_ok(
  $$ delete from public.teams where id = '55555555-5555-5555-5555-555555555555'::uuid $$,
  'teams: User A DELETE on team Y does not throw (silent RLS filter)'
);

select test_as_service_role();

select is(
  (select count(*)::int from public.teams where id = :'team_y_id'::uuid),
  1,
  'teams: team Y still exists after User A DELETE attempt'
);

-- ============================================================
-- anon role: nothing visible
-- ============================================================

select test_as_anon();

select is(
  (select count(*)::int from public.profiles),
  0,
  'anon: profiles rows = 0 (all hidden)'
);

select is(
  (select count(*)::int from public.teams),
  0,
  'anon: teams rows = 0'
);

select is(
  (select count(*)::int from public.team_members),
  0,
  'anon: team_members rows = 0'
);

select is(
  (select count(*)::int from public.projects),
  0,
  'anon: projects rows = 0'
);

select is(
  (select count(*)::int from public.simulation_runs),
  0,
  'anon: simulation_runs rows = 0'
);

select is(
  (select count(*)::int from public.usage),
  0,
  'anon: usage rows = 0'
);

select is(
  (select count(*)::int from public.billing_events),
  0,
  'anon: billing_events rows = 0'
);

-- anon cannot INSERT (grant 無し → permission denied)
select throws_ok(
  $$ insert into public.profiles (id, email) values
     ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'::uuid, 'evil@anon.local') $$,
  NULL::text, NULL::text,
  'anon: INSERT into profiles blocked'
);

-- ============================================================
-- billing_events: authenticated role cannot INSERT / DELETE (no policy)
-- ============================================================

select test_as_user(:'user_a_id'::uuid);

select throws_ok(
  $$ insert into public.billing_events (team_id, event_type, data)
     values ('44444444-4444-4444-4444-444444444444'::uuid, 'hacked', '{}'::jsonb) $$,
  NULL::text, NULL::text,
  'billing_events: authenticated user cannot INSERT (append-only reserved for service-role webhook)'
);

select lives_ok(
  $$ delete from public.billing_events where team_id = '44444444-4444-4444-4444-444444444444'::uuid $$,
  'billing_events: authenticated user DELETE does not throw (silent filter)'
);

select test_as_service_role();

select is(
  (select count(*)::int from public.billing_events where team_id = :'team_x_id'::uuid),
  1,
  'billing_events: row still exists after authenticated DELETE attempt (RLS blocked)'
);

-- ============================================================
-- usage: authenticated role cannot INSERT/UPDATE/DELETE (no policy)
-- ============================================================

select test_as_user(:'user_a_id'::uuid);

select throws_ok(
  $$ insert into public.usage (team_id, month, simulation_count)
     values ('44444444-4444-4444-4444-444444444444'::uuid, '2026-05', 999) $$,
  NULL::text, NULL::text,
  'usage: authenticated user cannot INSERT (reserved for service-role)'
);

-- ============================================================
-- #73: organizations / org_members / tasks RLS coverage
-- (migration 009 + 013 + 015 を対象。011 audit_logs / 010 apm は別 issue)
-- ============================================================

-- ────────────────────────────────────────────────────────────
-- organizations: SELECT cross-tenant isolation
--   Policy: SELECT は org_members(active) または owner_id=auth.uid()
--           INSERT は owner_id = auth.uid() (with check)
-- ────────────────────────────────────────────────────────────
select test_as_user(:'user_a_id'::uuid);

select is(
  (select count(*)::int from public.organizations where id = :'org_p_id'::uuid),
  1,
  'organizations: User A (admin/owner of org_p) sees own org P'
);

select is(
  (select count(*)::int from public.organizations where id = :'org_q_id'::uuid),
  0,
  'organizations: User A CANNOT see org Q (other tenant)'
);

select test_as_user(:'user_b_id'::uuid);

select is(
  (select count(*)::int from public.organizations where id = :'org_p_id'::uuid),
  1,
  'organizations: User B (member, active) sees org P'
);

select is(
  (select count(*)::int from public.organizations where id = :'org_q_id'::uuid),
  0,
  'organizations: User B CANNOT see org Q (other tenant)'
);

select test_as_user(:'user_c_id'::uuid);

select is(
  (select count(*)::int from public.organizations where id = :'org_p_id'::uuid),
  0,
  'organizations: User C CANNOT see org P (other tenant)'
);

select is(
  (select count(*)::int from public.organizations where id = :'org_q_id'::uuid),
  1,
  'organizations: User C (owner) sees own org Q'
);

-- INSERT: A は自分を owner として org を作れる (with check 通過)
select test_as_user(:'user_a_id'::uuid);

select lives_ok(
  $$ insert into public.organizations (name, owner_id)
     values ('A self org', '11111111-1111-1111-1111-111111111111'::uuid) $$,
  'organizations: User A can create org with owner_id = self'
);

-- INSERT: A は他人 (B) を owner として org を作ることはできない (with check 違反)
select throws_ok(
  $$ insert into public.organizations (name, owner_id)
     values ('Hijack', '22222222-2222-2222-2222-222222222222'::uuid) $$,
  NULL::text, NULL::text,
  'organizations: User A cannot create org with another user as owner'
);

-- ────────────────────────────────────────────────────────────
-- org_members: SELECT cross-tenant isolation
--   Policy (009): SELECT は org_id IN (subquery same table where user_id=auth.uid() and status='active')
--   Policy (013): INSERT は status='pending' AND role IN ('member','admin','viewer')
--                 + admin/owner of the org OR organizations.owner_id=auth.uid()
--   Policy (013 additional): "Org owners can self-bootstrap as active"
--                            user_id=auth.uid() AND role='owner' AND status='active'
--                            AND organizations.owner_id=auth.uid()
-- ────────────────────────────────────────────────────────────
select test_as_user(:'user_a_id'::uuid);

select is(
  (select count(*)::int from public.org_members where org_id = :'org_p_id'::uuid),
  2,
  'org_members: User A sees both members of org P (admin A + member B)'
);

select is(
  (select count(*)::int from public.org_members where org_id = :'org_q_id'::uuid),
  0,
  'org_members: User A CANNOT see org Q membership'
);

select test_as_user(:'user_b_id'::uuid);

select is(
  (select count(*)::int from public.org_members where org_id = :'org_p_id'::uuid),
  2,
  'org_members: User B (member, active) sees both members of org P'
);

select is(
  (select count(*)::int from public.org_members where org_id = :'org_q_id'::uuid),
  0,
  'org_members: User B CANNOT see org Q membership'
);

select test_as_user(:'user_c_id'::uuid);

select is(
  (select count(*)::int from public.org_members where org_id = :'org_q_id'::uuid),
  1,
  'org_members: User C sees own membership in org Q'
);

select is(
  (select count(*)::int from public.org_members where org_id = :'org_p_id'::uuid),
  0,
  'org_members: User C CANNOT see org P membership'
);

-- INSERT: A (admin of org_p) は member/admin/viewer を pending で招待できる (013 fix済)
select test_as_user(:'user_a_id'::uuid);

select lives_ok(
  $$ insert into public.org_members (org_id, email, role, status)
     values ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'::uuid,
             'invited@test.local', 'member', 'pending') $$,
  'org_members: admin A can INSERT pending invite (role=member)'
);

-- INSERT: A (admin) が role='owner' を直接 INSERT しようとすると block (013 P1-7 fix)
select throws_ok(
  $$ insert into public.org_members (org_id, user_id, email, role, status)
     values ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'::uuid,
             '33333333-3333-3333-3333-333333333333'::uuid,
             'evil-owner@test.local', 'owner', 'pending') $$,
  NULL::text, NULL::text,
  'org_members: admin A cannot escalate to role=owner via direct INSERT (#70 P1-7 fixed in 013)'
);

-- INSERT: A (admin) が status='active' を直接 INSERT しようとすると block
-- (self-bootstrap policy は user_id=self+role=owner を要求するので、role=member+status=active は block)
select throws_ok(
  $$ insert into public.org_members (org_id, user_id, email, role, status)
     values ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'::uuid,
             '33333333-3333-3333-3333-333333333333'::uuid,
             'evil-active@test.local', 'member', 'active') $$,
  NULL::text, NULL::text,
  'org_members: admin A cannot bypass invite acceptance (status must be pending for non-self-bootstrap)'
);

-- INSERT: B (member, not admin) は招待 INSERT を block される
select test_as_user(:'user_b_id'::uuid);

select throws_ok(
  $$ insert into public.org_members (org_id, email, role, status)
     values ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'::uuid,
             'b-invite@test.local', 'member', 'pending') $$,
  NULL::text, NULL::text,
  'org_members: member B (not admin) cannot INSERT invite'
);

-- INSERT: C (owner of org_q) は org_p に招待を作れない (org_p の admin/owner ではない)
select test_as_user(:'user_c_id'::uuid);

select throws_ok(
  $$ insert into public.org_members (org_id, email, role, status)
     values ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'::uuid,
             'c-cross@test.local', 'member', 'pending') $$,
  NULL::text, NULL::text,
  'org_members: User C cannot INSERT into org_p (not admin/owner of org_p)'
);

-- INSERT: org owner self-bootstrap policy (013) — A が新 org 作成後に
-- 自分自身を role=owner, status=active で INSERT できる
select test_as_user(:'user_a_id'::uuid);

-- まず service_role で新規 org を作る (RLS 経由ではなく seed 同等)
select test_as_service_role();
insert into public.organizations (id, name, owner_id) values
  ('eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee'::uuid, 'Org Bootstrap', :'user_a_id'::uuid);

select test_as_user(:'user_a_id'::uuid);
select lives_ok(
  $$ insert into public.org_members (org_id, user_id, email, role, status)
     values ('eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee'::uuid,
             '11111111-1111-1111-1111-111111111111'::uuid,
             'a@test.local', 'owner', 'active') $$,
  'org_members: org owner can self-bootstrap (role=owner, status=active, user_id=self) (013)'
);

-- ────────────────────────────────────────────────────────────
-- tasks: SELECT cross-tenant isolation + CRUD
--   Policy (009): FOR ALL using (org_id IN active membership)
--                 WITH CHECK は USING を流用 → created_by 偽装が現状可能 (#70 finding 2)
-- ────────────────────────────────────────────────────────────
select test_as_user(:'user_a_id'::uuid);

select is(
  (select count(*)::int from public.tasks where org_id = :'org_p_id'::uuid),
  1,
  'tasks: User A sees org_p tasks'
);

select is(
  (select count(*)::int from public.tasks where org_id = :'org_q_id'::uuid),
  0,
  'tasks: User A CANNOT see org_q tasks'
);

select test_as_user(:'user_b_id'::uuid);

select is(
  (select count(*)::int from public.tasks where org_id = :'org_p_id'::uuid),
  1,
  'tasks: User B (member) sees org_p tasks'
);

select is(
  (select count(*)::int from public.tasks where org_id = :'org_q_id'::uuid),
  0,
  'tasks: User B CANNOT see org_q tasks'
);

select test_as_user(:'user_c_id'::uuid);

select is(
  (select count(*)::int from public.tasks where org_id = :'org_q_id'::uuid),
  1,
  'tasks: User C sees own org_q tasks'
);

select is(
  (select count(*)::int from public.tasks where org_id = :'org_p_id'::uuid),
  0,
  'tasks: User C CANNOT see org_p tasks'
);

-- INSERT: A は org_p に task を作れる
select test_as_user(:'user_a_id'::uuid);

select lives_ok(
  $$ insert into public.tasks (org_id, title, created_by)
     values ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'::uuid,
             'A new task in org_p', '11111111-1111-1111-1111-111111111111'::uuid) $$,
  'tasks: User A (member of org_p) can INSERT task in org_p'
);

-- INSERT: A は cross-org に task を作れない (org_q の active member ではない)
select throws_ok(
  $$ insert into public.tasks (org_id, title, created_by)
     values ('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'::uuid,
             'A cross-tenant', '11111111-1111-1111-1111-111111111111'::uuid) $$,
  NULL::text, NULL::text,
  'tasks: User A cannot INSERT into org_q (cross-tenant blocked by RLS)'
);

-- tasks INSERT は migration 015 で WITH CHECK (created_by = auth.uid()) が
-- 追加されたので、member B が created_by を A に偽装する INSERT は block される。
-- (#70 finding 2 を 015 で fix 済 → 恒常 regression-lock)
select test_as_user(:'user_b_id'::uuid);

select throws_ok(
  $$ insert into public.tasks (org_id, title, created_by)
     values ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'::uuid,
             'forged authorship', '11111111-1111-1111-1111-111111111111'::uuid) $$,
  NULL::text, NULL::text,
  'tasks: member B cannot forge created_by to another user (#70 finding 2 fixed in 015)'
);

-- ────────────────────────────────────────────────────────────
-- anon: org tables も全て不可視 + INSERT block
-- ────────────────────────────────────────────────────────────
select test_as_anon();

select is(
  (select count(*)::int from public.organizations),
  0,
  'anon: organizations rows = 0 (all hidden)'
);

select is(
  (select count(*)::int from public.org_members),
  0,
  'anon: org_members rows = 0'
);

select is(
  (select count(*)::int from public.tasks),
  0,
  'anon: tasks rows = 0'
);

select throws_ok(
  $$ insert into public.organizations (name, owner_id)
     values ('Anon org', '11111111-1111-1111-1111-111111111111'::uuid) $$,
  NULL::text, NULL::text,
  'anon: INSERT into organizations blocked'
);

-- ============================================================
-- #72 contact_requests / coupons (schema-drift fix, migration 016)
-- ============================================================
-- production faithful な RLS 設計の regression-lock:
--   contact_requests : INSERT は誰でも可、SELECT 等は policy 不在 → RLS deny
--   coupons          : SELECT は authenticated のみ、INSERT 等は RLS deny

-- ── contact_requests: anon が INSERT 可、SELECT 不可 ──
select test_as_anon();

select lives_ok(
  $$ insert into public.contact_requests (company, name, email, company_size, message)
     values ('Acme', 'Anon Sender', 'anon@test.local', '11-50', 'inquiry from public form') $$,
  'contact_requests: anon CAN INSERT (public form path)'
);

select is(
  (select count(*)::int from public.contact_requests),
  0,
  'contact_requests: anon SELECT returns 0 rows (no SELECT policy)'
);

-- ── contact_requests: authenticated も INSERT 可、SELECT 不可 ──
select test_as_user(:'user_a_id'::uuid);

select lives_ok(
  $$ insert into public.contact_requests (company, name, email, company_size, message)
     values ('Acme2', 'User A', 'a@test.local', '50-200', 'logged-in user inquiry') $$,
  'contact_requests: authenticated CAN INSERT'
);

select is(
  (select count(*)::int from public.contact_requests),
  0,
  'contact_requests: authenticated SELECT returns 0 rows (no SELECT policy)'
);

-- ── coupons: service_role でテスト用クーポン投入 (RLS bypass) ──
select test_as_service_role();
insert into public.coupons (code, tier, days, max_uses) values
  ('TESTCODE72', 'pro', 30, 5);

-- ── coupons: authenticated は SELECT 可 ──
select test_as_user(:'user_a_id'::uuid);

select is(
  (select count(*)::int from public.coupons where code = 'TESTCODE72'),
  1,
  'coupons: authenticated CAN SELECT (auth.role()=authenticated policy matches)'
);

-- ── coupons: anon は SELECT 0 行 ──
select test_as_anon();

select is(
  (select count(*)::int from public.coupons),
  0,
  'coupons: anon SELECT returns 0 rows (auth.role()!=authenticated)'
);

-- ── coupons: authenticated は INSERT block (INSERT policy 不在 → RLS deny) ──
select test_as_user(:'user_a_id'::uuid);

select throws_ok(
  $$ insert into public.coupons (code, tier, days, max_uses)
     values ('FORGED72', 'pro', 365, 0) $$,
  NULL::text, NULL::text,
  'coupons: authenticated CANNOT INSERT (no INSERT policy → RLS deny)'
);

-- ── coupons: authenticated は UPDATE silently denied (UPDATE policy 不在 → RLS deny) ──
-- Postgres の RLS は UPDATE policy 不在の場合、視認できる行を更新しようとしても
-- 0 affected (silent skip) になる (throws ではない)。これが /api/coupon/redeem を
-- user client で increment しようとすると 409 に落ちる原因 (PR #100 Codex P1 review
-- 指摘 → admin client へ修正)。本 assertion は redeem path の regression-lock:
-- authenticated として UPDATE を試行し、service_role で current_uses が変更されて
-- いないことを検証する。
update public.coupons set current_uses = current_uses + 1 where code = 'TESTCODE72';

select test_as_service_role();
select is(
  (select current_uses from public.coupons where code = 'TESTCODE72'),
  0,
  'coupons: authenticated UPDATE silently denied (current_uses unchanged after attempted increment)'
);

-- ============================================================
-- #80: tasks.assignee_id same-org WITH CHECK guard (migration 018)
-- ============================================================
-- user_a (admin of org_p) として 4 ケース:
--   (a) same-org assignee (om_b_p_id) → allowed
--   (b) cross-org assignee (om_c_q_id) → blocked by WITH CHECK
--   (c) NULL assignee → allowed
--   (d) UPDATE existing task assignee to cross-org → blocked by WITH CHECK

select test_as_user(:'user_a_id'::uuid);

select lives_ok(
  format(
    $sql$ insert into public.tasks (org_id, title, created_by, assignee_id)
          values (%L::uuid, '%s', %L::uuid, %L::uuid) $sql$,
    :'org_p_id', 'task with same-org assignee', :'user_a_id', :'om_b_p_id'
  ),
  '#80: INSERT task with same-org assignee_id (B in org_p) — allowed'
);

select throws_ok(
  format(
    $sql$ insert into public.tasks (org_id, title, created_by, assignee_id)
          values (%L::uuid, '%s', %L::uuid, %L::uuid) $sql$,
    :'org_p_id', 'task with cross-org assignee', :'user_a_id', :'om_c_q_id'
  ),
  NULL::text, NULL::text,
  '#80: INSERT task with cross-org assignee_id (C in org_q) — blocked'
);

select lives_ok(
  format(
    $sql$ insert into public.tasks (org_id, title, created_by, assignee_id)
          values (%L::uuid, '%s', %L::uuid, NULL) $sql$,
    :'org_p_id', 'task with NULL assignee', :'user_a_id'
  ),
  '#80: INSERT task with NULL assignee_id — allowed'
);

select throws_ok(
  format(
    $sql$ update public.tasks set assignee_id = %L::uuid where id = %L::uuid $sql$,
    :'om_c_q_id', :'task_p_id'
  ),
  NULL::text, NULL::text,
  '#80: UPDATE task assignee_id to cross-org member — blocked'
);

-- ============================================================
-- #83: member_systems WITH CHECK 構造的存在 (migration 018)
-- ============================================================
-- member_systems / members / companies / systems の完全 SEED は scope 拡大に
-- なるため、本 PR では migration 018 が「INSERT/UPDATE policy を WITH CHECK
-- 付きで作成した」ことを構造的に確認する (DB drift 検出として十分)。

select test_as_service_role();

select isnt(
  (select with_check from pg_policies
    where schemaname = 'public'
      and tablename = 'member_systems'
      and policyname = 'Company owner can insert member_systems'),
  NULL,
  '#83: member_systems INSERT policy exists with WITH CHECK (cross-company guard)'
);

select isnt(
  (select with_check from pg_policies
    where schemaname = 'public'
      and tablename = 'member_systems'
      and policyname = 'Company owner can update member_systems'),
  NULL,
  '#83: member_systems UPDATE policy exists with WITH CHECK (cross-company guard)'
);

-- ============================================================
-- #110 + #111: audit_logs INSERT path + action vocabulary alignment
-- (migration 019) — Must run BEFORE the delete_user_account block below,
-- since that block removes user_a from auth.users / profiles.
-- ============================================================
--
-- 1) user_a is a team_x member → INSERT under user_a's own user_id with
--    team_x is accepted; SELECT also returns it. The action value uses the
--    canonical UPPER_SNAKE vocabulary (rejected before #111).
-- 2) Spoofing user_id (user_a sets user_id = user_b) is rejected by WITH CHECK.
-- 3) user_a inserting into team_y (cross-team) is rejected by WITH CHECK.
-- 4) team_id = NULL is allowed when user_id matches auth.uid().

select test_as_user(:'user_a_id'::uuid);

prepare ok_insert as
  insert into public.audit_logs (team_id, user_id, actor_email, action, outcome)
  values (:'team_x_id'::uuid, :'user_a_id'::uuid, 'a@example.com', 'SIMULATION_RUN', 'SUCCESS');
select lives_ok(
  'execute ok_insert',
  '#110: same-team member can INSERT audit_logs under own user_id'
);

select is(
  (select count(*)::int from public.audit_logs
   where team_id = :'team_x_id'::uuid and user_id = :'user_a_id'::uuid),
  1,
  '#110: the row landed and is visible via SELECT'
);

prepare spoof_user as
  insert into public.audit_logs (team_id, user_id, actor_email, action)
  values (:'team_x_id'::uuid, :'user_b_id'::uuid, 'b@example.com', 'LOGIN');
select throws_ok(
  'execute spoof_user',
  NULL,
  NULL,
  '#110: user_id spoofing (user_id <> auth.uid()) is rejected by WITH CHECK'
);

prepare cross_team as
  insert into public.audit_logs (team_id, user_id, actor_email, action)
  values (:'team_y_id'::uuid, :'user_a_id'::uuid, 'a@example.com', 'LOGIN');
select throws_ok(
  'execute cross_team',
  NULL,
  NULL,
  '#110: cross-team INSERT rejected — user_a cannot log against team_y'
);

prepare null_team as
  insert into public.audit_logs (team_id, user_id, actor_email, action)
  values (NULL, :'user_a_id'::uuid, 'a@example.com', 'SETTINGS_CHANGE');
select lives_ok(
  'execute null_team',
  '#110: team_id NULL is accepted when user_id matches auth.uid()'
);

deallocate ok_insert;
deallocate spoof_user;
deallocate cross_team;
deallocate null_team;

-- ============================================================
-- #70 finding 3-5: delete_user_account RPC が 009 テーブル対応 (migration 017)
-- ============================================================
-- user_a (org_p の owner かつ admin member) を delete_user_account で削除し、
-- 以下の semantics を regression-lock する:
--   - organizations CASCADE: org_p (owner=A) が消える
--   - org_members CASCADE: org_p の members (A + B) が連鎖削除
--   - tasks CASCADE: org_p 配下の task_p1 が連鎖削除
--   - 他人 (C) の org_q / org_q membership / org_q tasks は影響なし

-- pre-condition: setup で作成された org_p / org_q 両方が見える
select test_as_service_role();
select is(
  (select count(*)::int from public.organizations
   where id in (:'org_p_id'::uuid, :'org_q_id'::uuid)),
  2,
  '#70: pre — both org_p and org_q exist before user_a delete'
);

-- RPC 実行: user_a を削除
select count(*) from public.delete_user_account(:'user_a_id'::uuid);

-- post: org_p (owner=A) は消失
select is(
  (select count(*)::int from public.organizations where id = :'org_p_id'::uuid),
  0,
  '#70: organizations CASCADE — org_p (owner=A) removed by RPC'
);

-- post: org_q (owner=C) は残る
select is(
  (select count(*)::int from public.organizations where id = :'org_q_id'::uuid),
  1,
  '#70: unrelated org_q (owner=C) preserved across user_a delete'
);

-- post: org_p の members (A admin + B member) は連鎖削除されている
select is(
  (select count(*)::int from public.org_members where org_id = :'org_p_id'::uuid),
  0,
  '#70: org_members CASCADE on organizations delete — all org_p members removed'
);

-- post: org_p の tasks (task_p1) は連鎖削除されている
select is(
  (select count(*)::int from public.tasks where id = :'task_p_id'::uuid),
  0,
  '#70: tasks CASCADE on organizations delete — task_p1 removed'
);

-- post: org_q の C 自身の membership は残る
select is(
  (select count(*)::int from public.org_members where user_id = :'user_c_id'::uuid),
  1,
  '#70: unrelated user_c org_membership preserved'
);

-- ============================================================
-- finish
-- ============================================================

select * from finish();
rollback;
