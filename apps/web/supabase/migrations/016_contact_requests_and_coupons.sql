-- 016: schema-drift fix #72 — contact_requests + coupons
-- ----------------------------------------------------------------------------
-- 背景:
--   PR #67 (#47) で production faultray-pro DDL を migrations に sync したが、
--   `contact_requests` と `coupons` の 2 テーブルが漏れていた (Codex 4並列
--   audit 2026-04-30 で検出 — issue #72)。
--
--   両テーブルとも production には存在し、アプリコードから参照されている:
--     - contact_requests : src/app/contact/page.tsx (公開フォーム送信)
--     - coupons          : src/app/api/coupon/redeem/route.ts (有料プラン引換)
--
--   migrations に欠落しているため fresh env (staging / local / preview deploy)
--   でこれらの code path が 500 を返す。本マイグレーションは production の
--   実 DDL (information_schema + pg_policies + pg_constraint + pg_indexes 経由
--   で 2026-05-05 に Supabase Management API 抽出) を再現する。
--
-- Hardening についての注記:
--   production の table-level grants は anon/authenticated/service_role に
--   全 CRUD が付与されているが、これは Supabase の默认 grant 挙動
--   (grant select, insert, update, delete on all tables in schema public to
--   anon, authenticated) の副産物で、設計意図ではない。
--   実際のアクセス制御は RLS policy で担保:
--     - contact_requests : INSERT のみ任意 role 可、SELECT/UPDATE/DELETE は
--                          policy 不在 → RLS deny (service_role bypass のみ)
--     - coupons          : SELECT は authenticated のみ、INSERT/UPDATE/DELETE
--                          は policy 不在 → RLS deny (service_role bypass のみ)
--   grant 最小化と coupons.code への enumeration 対策 (rate-limit, secret code)
--   は別 hardening issue で扱う。
-- ----------------------------------------------------------------------------

-- ── contact_requests: 公開問い合わせフォーム送信先 ──
create table if not exists public.contact_requests (
  id            uuid primary key default gen_random_uuid(),
  company       text not null,
  name          text not null,
  email         text not null,
  company_size  text not null,
  message       text not null,
  created_at    timestamptz not null default now()
);

alter table public.contact_requests enable row level security;

-- 公開フォーム (anon client) からの INSERT を許可。
-- SELECT/UPDATE/DELETE は policy 不在 → RLS deny (service_role bypass で運用)。
drop policy if exists "Anyone can insert contact requests" on public.contact_requests;
create policy "Anyone can insert contact requests"
  on public.contact_requests
  for insert
  to public
  with check (true);

-- production faithful な grants (RLS で実アクセスを制限する前提)。
grant select, insert, update, delete on public.contact_requests
  to anon, authenticated;
grant all on public.contact_requests to service_role;


-- ── coupons: 有料プラン引換用クーポン ──
create table if not exists public.coupons (
  id             uuid primary key default gen_random_uuid(),
  code           text not null unique,
  tier           text not null default 'pro',
  days           integer not null default 30,
  max_uses       integer not null default 0,
  current_uses   integer not null default 0,
  note           text default '',
  revoked        boolean not null default false,
  created_at     timestamptz not null default now()
);

alter table public.coupons enable row level security;

-- authenticated ユーザーのみ SELECT 可 (anon にコード列挙させない)。
-- INSERT/UPDATE/DELETE policy は不在 → RLS deny。
-- redeem (route.ts) は service_role client で current_uses をインクリメント。
-- 手動発行は Supabase Studio (= service_role) で行う運用。
drop policy if exists "Authenticated users can read coupons" on public.coupons;
create policy "Authenticated users can read coupons"
  on public.coupons
  for select
  to public
  using (auth.role() = 'authenticated');

grant select, insert, update, delete on public.coupons
  to anon, authenticated;
grant all on public.coupons to service_role;
