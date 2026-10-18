-- ============================================================
-- 023: People-Risk SELECT isolation + demo readability (U32 / #member_systems-drift)
--
-- Migration 018 documented that production drifted to a permissive
-- "Allow read access" SELECT on public.member_systems (and the 004
-- owner-scoped SELECT policies may be absent there), which allows any
-- authenticated user to read member-system risk rows (risk_level,
-- is_sole_owner, notes) across companies — a cross-tenant exposure.
--
-- This migration re-establishes a KNOWN-GOOD SELECT policy on every
-- People-Risk table regardless of the current drifted state:
--   * owner-scoped: a company's rows are visible only to companies the
--     caller owns (companies.owner_id = auth.uid()), AND
--   * demo-readable: the seeded public demo company is readable by any
--     authenticated user, because the People-Risk feature intentionally
--     surfaces that sample data via a fixed DEMO_COMPANY_ID (see
--     src/lib/people-risk/queries.ts). The demo company has owner_id = NULL,
--     so without this clause an owner-only policy would hide it from everyone.
--
-- Idempotent: drops the legacy/owner-only/permissive SELECT policies if
-- present and recreates a single canonical "owner or demo" SELECT policy.
-- INSERT/UPDATE/DELETE policies are left as hardened by 004 + 018 (writes
-- stay strictly owner-scoped; the demo company has no owner so it is
-- read-only to end users).
-- ============================================================

-- Fixed seed id, matches 004 seed + queries.ts DEMO_COMPANY_ID.
-- (Inlined as a literal because RLS policy expressions can't take params.)

-- ── companies ────────────────────────────────────────────────
drop policy if exists "Allow read access"            on public.companies;
drop policy if exists "Owner can view own company"   on public.companies;
drop policy if exists "Owner or demo can view company" on public.companies;
create policy "Owner or demo can view company"
  on public.companies for select
  using (
    owner_id = auth.uid()
    or id = '11111111-1111-1111-1111-111111111111'
  );

-- ── members ──────────────────────────────────────────────────
drop policy if exists "Allow read access"             on public.members;
drop policy if exists "Company owner can view members" on public.members;
drop policy if exists "Owner or demo can view members" on public.members;
create policy "Owner or demo can view members"
  on public.members for select
  using (
    company_id in (select id from public.companies where owner_id = auth.uid())
    or company_id = '11111111-1111-1111-1111-111111111111'
  );

-- ── systems ──────────────────────────────────────────────────
drop policy if exists "Allow read access"             on public.systems;
drop policy if exists "Company owner can view systems" on public.systems;
drop policy if exists "Owner or demo can view systems" on public.systems;
create policy "Owner or demo can view systems"
  on public.systems for select
  using (
    company_id in (select id from public.companies where owner_id = auth.uid())
    or company_id = '11111111-1111-1111-1111-111111111111'
  );

-- ── member_systems (the documented drift) ────────────────────
drop policy if exists "Allow read access"                   on public.member_systems;
drop policy if exists "Company owner can view member_systems" on public.member_systems;
drop policy if exists "Owner or demo can view member_systems" on public.member_systems;
create policy "Owner or demo can view member_systems"
  on public.member_systems for select
  using (
    member_id in (
      select m.id
      from public.members m
      where m.company_id in (select id from public.companies where owner_id = auth.uid())
         or m.company_id = '11111111-1111-1111-1111-111111111111'
    )
  );

-- ── actions ──────────────────────────────────────────────────
drop policy if exists "Allow read access"             on public.actions;
drop policy if exists "Company owner can view actions" on public.actions;
drop policy if exists "Owner or demo can view actions" on public.actions;
create policy "Owner or demo can view actions"
  on public.actions for select
  using (
    company_id in (select id from public.companies where owner_id = auth.uid())
    or company_id = '11111111-1111-1111-1111-111111111111'
  );

-- ── risk_snapshots ───────────────────────────────────────────
drop policy if exists "Allow read access"                    on public.risk_snapshots;
drop policy if exists "Company owner can view risk_snapshots" on public.risk_snapshots;
drop policy if exists "Owner or demo can view risk_snapshots" on public.risk_snapshots;
create policy "Owner or demo can view risk_snapshots"
  on public.risk_snapshots for select
  using (
    company_id in (select id from public.companies where owner_id = auth.uid())
    or company_id = '11111111-1111-1111-1111-111111111111'
  );
