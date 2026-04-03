-- RLS-01: Add missing UPDATE and DELETE policies for all tables.
-- RLS-02: service_role functions use SECURITY DEFINER and bypass RLS by design
--          (Supabase admin operations). No action needed there but documented.
-- RLS-03: Ensure anon role cannot read team composition data.

-- ============================================================
-- profiles
-- ============================================================
-- (SELECT + UPDATE already exist from 001_initial_schema.sql)

-- Allow users to delete their own profile (soft deletion; hard delete via /api/account/delete)
create policy "Users can delete own profile"
  on public.profiles for delete
  using (auth.uid() = id);

-- ============================================================
-- teams
-- ============================================================

-- Only team owner or admin can update team metadata
create policy "Team owner can update team"
  on public.teams for update
  using (
    id in (
      select team_id from public.team_members
      where user_id = auth.uid() and role in ('owner', 'admin')
    )
  );

-- Only team owner can delete a team
create policy "Team owner can delete team"
  on public.teams for delete
  using (owner_id = auth.uid());

-- ============================================================
-- team_members
-- ============================================================

-- Team owners/admins can add members
create policy "Team admins can insert team members"
  on public.team_members for insert
  with check (
    team_id in (
      select team_id from public.team_members
      where user_id = auth.uid() and role in ('owner', 'admin')
    )
  );

-- Team owners/admins can update member roles
create policy "Team admins can update team members"
  on public.team_members for update
  using (
    team_id in (
      select team_id from public.team_members
      where user_id = auth.uid() and role in ('owner', 'admin')
    )
  );

-- Team owners/admins can remove members; members can remove themselves
create policy "Team admins can delete team members"
  on public.team_members for delete
  using (
    user_id = auth.uid()
    or team_id in (
      select team_id from public.team_members
      where user_id = auth.uid() and role in ('owner', 'admin')
    )
  );

-- ============================================================
-- projects
-- ============================================================

-- Team members can update their team's projects
create policy "Team members can update projects"
  on public.projects for update
  using (
    team_id in (
      select team_id from public.team_members
      where user_id = auth.uid()
    )
  );

-- Team owners/admins can delete projects
create policy "Team admins can delete projects"
  on public.projects for delete
  using (
    team_id in (
      select team_id from public.team_members
      where user_id = auth.uid() and role in ('owner', 'admin')
    )
  );

-- ============================================================
-- simulation_runs
-- ============================================================

-- Team owners/admins can delete runs
create policy "Team admins can delete runs"
  on public.simulation_runs for delete
  using (
    team_id in (
      select team_id from public.team_members
      where user_id = auth.uid() and role in ('owner', 'admin')
    )
  );

-- ============================================================
-- usage (insert-only for increment; no user-facing update/delete)
-- ============================================================

-- Prevent any direct row deletion of usage records by non-service-role callers
-- (Service role used by API still works; anon/authenticated role cannot delete)
-- No explicit delete policy → RLS blocks delete for authenticated role by default.

-- ============================================================
-- billing_events (append-only; no user-facing update/delete)
-- ============================================================
-- No explicit update/delete policies. Authenticated role cannot modify billing records.
-- Service role (Stripe webhook) bypasses RLS via SECURITY DEFINER context.
