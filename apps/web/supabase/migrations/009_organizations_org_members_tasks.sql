-- 009: organizations / org_members / tasks (schema-drift fix)
-- ----------------------------------------------------------------------------
-- 背景:
--   2026-04 まで mattyopon/faultray-app#47 で報告されていた schema drift。
--   本番 (faultray-pro) と staging (faultray-staging) には organizations,
--   org_members, tasks テーブルが既に存在し、5つの API route がこれを参照
--   しているが、001-008 migration には DDL が含まれていなかった。
--   新環境を立ち上げると CI (RLS pgTAP test) と Vercel Preview が壊れる
--   ため、本 migration で本番 DDL を逆抽出して同期する。
--
-- 抽出元: information_schema.columns + pg_policies + pg_constraint
--          (faultray-pro 2026-04-30 時点のスナップショット)
--
-- 既存 DB との idempotency:
--   - CREATE TABLE IF NOT EXISTS で本番には影響なし
--   - DROP POLICY IF EXISTS → CREATE POLICY で policy も同期
--
-- 順序:
--   1. 3 テーブル全部 CREATE (FK の forward reference を許容するため
--      organizations → org_members → tasks の依存順)
--   2. RLS 有効化
--   3. policies 作成 (subquery で他テーブル参照するため、テーブル全部
--      作成後でないと relation not exist エラー)
--   4. trigger
--
-- 既知の検討事項 (followup):
--   - org_members の SELECT/INSERT policy が org_members 自身を subquery
--     参照しており、本番では今のところ動作しているが PostgreSQL の
--     infinite-recursion 検出強化で破綻する可能性。SECURITY DEFINER
--     function (例: public.user_org_ids(uuid)) への抽象化を検討。
--   - org_members に UNIQUE(org_id, user_id) が無い。同一ユーザーが
--     同一 org に複数 row 作成可能。本番運用上は invited→joined の
--     履歴を兼ねている可能性があるため、この migration では現状維持。
-- ----------------------------------------------------------------------------

-- ======== Phase 1: tables (FK 依存順) ========
create table if not exists public.organizations (
  id          uuid not null default gen_random_uuid() primary key,
  name        text not null,
  owner_id    uuid not null references auth.users(id),
  plan        text not null default 'free',
  created_at  timestamptz not null default now()
);

create table if not exists public.org_members (
  id          uuid not null default gen_random_uuid() primary key,
  org_id      uuid not null references public.organizations(id) on delete cascade,
  user_id     uuid references auth.users(id),
  email       text not null,
  role        text not null default 'member',
  status      text not null default 'pending',
  invited_at  timestamptz not null default now(),
  joined_at   timestamptz
);

create table if not exists public.tasks (
  id           uuid not null default gen_random_uuid() primary key,
  org_id       uuid not null references public.organizations(id) on delete cascade,
  title        text not null,
  description  text default '',
  status       text not null default 'open',
  priority     text not null default 'medium',
  assignee_id  uuid references public.org_members(id),
  created_by   uuid not null references auth.users(id),
  due_date     date,
  source       text default '',
  source_id    text default '',
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);

-- ======== Phase 2: RLS enable ========
alter table public.organizations enable row level security;
alter table public.org_members   enable row level security;
alter table public.tasks         enable row level security;

-- ======== Phase 3: policies (テーブル全部作成後に subquery 解決可能) ========

-- organizations
drop policy if exists "Auth users can create orgs" on public.organizations;
create policy "Auth users can create orgs"
  on public.organizations
  for insert
  with check (auth.uid() = owner_id);

drop policy if exists "Org members can read their org" on public.organizations;
create policy "Org members can read their org"
  on public.organizations
  for select
  using (
    id in (
      select om.org_id
      from public.org_members om
      where om.user_id = auth.uid()
        and om.status = 'active'
    )
    or owner_id = auth.uid()
  );

-- org_members
drop policy if exists "Org members can read members" on public.org_members;
create policy "Org members can read members"
  on public.org_members
  for select
  using (
    org_id in (
      select om.org_id
      from public.org_members om
      where om.user_id = auth.uid()
        and om.status = 'active'
    )
  );

drop policy if exists "Admins can invite" on public.org_members;
create policy "Admins can invite"
  on public.org_members
  for insert
  with check (
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
  );

-- tasks
drop policy if exists "Org members can manage tasks" on public.tasks;
create policy "Org members can manage tasks"
  on public.tasks
  for all
  using (
    org_id in (
      select om.org_id
      from public.org_members om
      where om.user_id = auth.uid()
        and om.status = 'active'
    )
  );

-- ======== Phase 4: trigger (set_updated_at は 003 で定義済) ========
drop trigger if exists set_tasks_updated_at on public.tasks;
create trigger set_tasks_updated_at
  before update on public.tasks
  for each row
  execute function public.set_updated_at();
