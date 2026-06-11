-- migration 019 — Audit-log INSERT path and action-vocabulary alignment.
--
-- Closes #110: audit_logs had RLS on with a SELECT-only policy. Authenticated
--   POSTs went through the user's Supabase client, were denied by RLS, and the
--   route returned 500 — so every "auditable" event was silently lost. We add
--   a WITH-CHECK INSERT policy that lets a user log under their own user_id
--   and a team_id they actively belong to (or no team).
--
-- Closes #111: route's whitelist used dotted lowercase action names
--   ("simulation.run" etc.) while the existing CHECK constraint only allowed
--   uppercase underscore names. We widen the CHECK to the canonical vocabulary
--   declared in src/lib/audit-log-actions.ts. Old values stay accepted so any
--   pre-existing row is preserved.

ALTER TABLE public.audit_logs DROP CONSTRAINT IF EXISTS audit_logs_action_check;

ALTER TABLE public.audit_logs ADD CONSTRAINT audit_logs_action_check
  CHECK (action IN (
    'LOGIN',
    'LOGOUT',
    'SIMULATION_RUN',
    'REPORT_EXPORT',
    'REPORT_VIEW',
    'SETTINGS_CHANGE',
    'API_KEY_CREATED',
    'API_KEY_REVOKED',
    'PROJECT_CREATED',
    'PROJECT_DELETED',
    'MEMBER_INVITED',
    'PLAN_CHANGED',
    'DATA_EXPORT',
    'TASK_CREATE',
    'TASK_UPDATE',
    'TASK_DELETE'
  ));

DROP POLICY IF EXISTS "Team members can insert their team's audit logs"
  ON public.audit_logs;

CREATE POLICY "Team members can insert their team's audit logs"
  ON public.audit_logs FOR INSERT
  WITH CHECK (
    user_id = auth.uid()
    AND (
      team_id IS NULL
      -- Use the SECURITY DEFINER helper introduced in migration 006 and
      -- hardened in migration 013 (no-arg, binds auth.uid() internally so
      -- no caller can enumerate someone else's teams). A direct SELECT on
      -- public.team_members would return an empty set under RLS and block
      -- every legitimate INSERT.
      OR team_id IN (SELECT public.user_team_ids())
    )
  );

COMMENT ON CONSTRAINT audit_logs_action_check ON public.audit_logs IS
  'Mirrors AUDIT_LOG_ACTIONS in src/lib/audit-log-actions.ts. When adding new actions, update both places in the same PR.';
