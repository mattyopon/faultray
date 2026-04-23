-- ============================================================
-- Fix #30: Atomic trial expiry downgrade via PL/pgSQL function
--
-- 背景 (#30 の CC 自己レビューで検出):
--   naive な SELECT → filter → UPDATE 2-step 実装には 2 つの問題があった:
--   1) Supabase JS の .select() は default で 1000 行上限 → 1001人目以降が
--      silent に切り捨てられ、日次 downgrade から漏れて revenue leak が残る
--   2) SELECT と UPDATE の間に Stripe webhook が status='active' に更新した
--      場合、UPDATE 時に paying customer を誤って free 化する race がある
--
-- 対処:
--   downgrade 判定と update を単一 set-based SQL (SECURITY DEFINER) に
--   集約し、RPC 経由で呼ぶ。WHERE 節に subscription_status allow-list を
--   含めることで race-safe、かつ件数上限なし。
--
-- subscription_status allow-list (feature を保持する):
--   active   — 支払中
--   trialing — Stripe 側の trial (coupon 経由等)
--   past_due — dunning window 中 (決済リトライ 3-7 日)。この間 feature を
--              保持するのが業界標準 (Stripe docs "Handle payment failures")
--   それ以外 (null / canceled / incomplete / unpaid) は downgrade 対象
-- ============================================================

-- CI-SAFE: Legacy columns trial_ends_at / subscription_status were added
-- post-001 via supabase/add_*.sql (not a numbered migration). Fresh CI
-- databases run 001-008 in order, so those columns must exist here before
-- the RPC references them. IF NOT EXISTS is idempotent for production.
alter table public.profiles
  add column if not exists trial_ends_at timestamptz;

alter table public.profiles
  add column if not exists subscription_status text default 'active';

-- The CHECK constraint from add_subscription_status.sql, only applied if
-- we added the column above (same IF NOT EXISTS semantics via DO block).
do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conrelid = 'public.profiles'::regclass
      and conname  = 'profiles_subscription_status_check'
  ) then
    alter table public.profiles
      add constraint profiles_subscription_status_check
      check (subscription_status in ('active', 'past_due', 'canceled', 'trialing'));
  end if;
end $$;

create or replace function public.downgrade_expired_trials()
returns table (id uuid, email text)
language sql
security definer
set search_path = public, pg_temp
as $$
  -- Self-review follow-up: also clear subscription_status to 'canceled'
  -- so UI and downstream filters don't keep reading 'trialing' after the
  -- plan has been downgraded to 'free'. Without this, a user whose trial
  -- expires without a Stripe subscription still shows status='trialing'
  -- which is logically inconsistent.
  update public.profiles
  set
    plan = 'free',
    trial_ends_at = null,
    subscription_status = 'canceled'
  where
    trial_ends_at is not null
    and trial_ends_at < now()
    and plan <> 'free'
    and (
      subscription_status is null
      or subscription_status not in ('active', 'trialing', 'past_due')
    )
  returning id, email
$$;

-- service_role が呼べれば十分。authenticated / anon は呼ぶ必要なし。
revoke all on function public.downgrade_expired_trials() from public;
grant execute on function public.downgrade_expired_trials() to service_role;
