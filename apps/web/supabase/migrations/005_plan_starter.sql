-- ============================================================
-- Fix #24: profiles.plan / teams.plan CHECK に 'starter' を追加
--
-- 背景:
--   src/lib/types.ts:36 と src/app/api/stripe/webhook/route.ts:8 で
--   PlanTier = "free" | "starter" | "pro" | "business" と定義されているが、
--   001_initial_schema.sql の CHECK 制約には 'starter' が含まれていなかった。
--
--   結果: Stripe Starter price を契約したユーザーの webhook で
--         profiles.plan='starter' を書き込もうとすると Postgres CHECK 違反となり
--         updateUserPlan が例外を投げる → サイレントに plan 更新に失敗する。
--
-- 実装:
--   001_initial_schema.sql の CHECK は無名 inline 制約であり、Postgres が
--   自動生成した名前 (<table>_<column>_check 規則) で確定的に命名される。
--   profiles.plan → profiles_plan_check / teams.plan → teams_plan_check。
--
--   念のため、過去 migration で別名の CHECK が付与されている環境に備え
--   pg_constraint を走査する冪等ガードも併用する。
-- ============================================================

-- profiles.plan ───────────────────────────────────────────────
-- 1) Postgres 自動命名 (確定) の名前で drop
alter table public.profiles
  drop constraint if exists profiles_plan_check;

-- 2) 別名で付与されている可能性があるケースに備えた冪等ガード
--    (「plan カラムの CHECK」を厳密に特定)
do $$
declare
  c record;
begin
  for c in
    select con.conname
    from pg_constraint con
    join pg_attribute att
      on att.attrelid = con.conrelid
     and att.attnum = any(con.conkey)
    where con.conrelid = 'public.profiles'::regclass
      and con.contype = 'c'
      and att.attname = 'plan'
  loop
    execute format('alter table public.profiles drop constraint %I', c.conname);
  end loop;
end $$;

alter table public.profiles
  add constraint profiles_plan_check
  check (plan in ('free', 'starter', 'pro', 'business'));

-- teams.plan ──────────────────────────────────────────────────
alter table public.teams
  drop constraint if exists teams_plan_check;

do $$
declare
  c record;
begin
  for c in
    select con.conname
    from pg_constraint con
    join pg_attribute att
      on att.attrelid = con.conrelid
     and att.attnum = any(con.conkey)
    where con.conrelid = 'public.teams'::regclass
      and con.contype = 'c'
      and att.attname = 'plan'
  loop
    execute format('alter table public.teams drop constraint %I', c.conname);
  end loop;
end $$;

alter table public.teams
  add constraint teams_plan_check
  check (plan in ('free', 'starter', 'pro', 'business'));
