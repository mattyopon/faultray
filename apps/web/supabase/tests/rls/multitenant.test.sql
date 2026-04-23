-- ============================================================
-- RLS multi-tenant isolation tests (#28)
--
-- 対象: profiles / teams / team_members / projects / simulation_runs /
--       usage / billing_events の RLS policies
--
-- 検証シナリオ:
--   User A (team X owner), User B (team X member), User C (team Y owner)
--   - 自分の team のデータは見える
--   - 他人の team のデータは見えない
--   - member は admin 権限が必要な操作 (team update, insert member 等) ができない
--   - anon (未ログイン) は一切見えない
--
-- 実行方法 (ローカル Supabase):
--   supabase db reset  # migrations 全適用
--   psql "postgresql://postgres@localhost:54322/postgres" \
--        -f supabase/tests/rls/multitenant.test.sql
-- (ローカル開発用 postgres のデフォルトパスワードは Supabase CLI が管理)
--
-- CI: .github/workflows/ci.yml の rls-tests job で自動実行される
-- ============================================================

begin;

-- pgTAP 拡張 (必要なら)
create extension if not exists pgtap;

-- ---------- テストプラン ----------
-- RLS 対象 7 テーブル × 各シナリオ (正例 + 反例) = 40 assertion
select plan(40);

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
-- finish
-- ============================================================

select * from finish();
rollback;
