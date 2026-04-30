-- SAAS-03: Audit log table for compliance (SOC 2 / GDPR Article 30 / ISO 27001)
CREATE TABLE IF NOT EXISTS public.audit_logs (
  id uuid DEFAULT uuid_generate_v4() PRIMARY KEY,
  team_id uuid REFERENCES public.teams(id) ON DELETE SET NULL,
  user_id uuid REFERENCES public.profiles(id) ON DELETE SET NULL,
  actor_email text NOT NULL,
  action text NOT NULL CHECK (action IN (
    'LOGIN', 'LOGOUT', 'SIMULATION_RUN', 'REPORT_EXPORT',
    'SETTINGS_CHANGE', 'API_KEY_CREATED', 'API_KEY_REVOKED',
    'PROJECT_CREATED', 'PROJECT_DELETED', 'MEMBER_INVITED',
    'PLAN_CHANGED', 'DATA_EXPORT'
  )),
  resource text,
  ip_address text,
  user_agent text,
  outcome text NOT NULL DEFAULT 'SUCCESS' CHECK (outcome IN ('SUCCESS', 'FAILURE')),
  details text,
  created_at timestamptz DEFAULT now()
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_audit_logs_team ON public.audit_logs(team_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_user ON public.audit_logs(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON public.audit_logs(action, created_at DESC);

-- RLS: team members can view their team's audit logs
ALTER TABLE public.audit_logs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Team members can view audit logs"
  ON public.audit_logs FOR SELECT
  USING (
    team_id IN (
      SELECT team_id FROM public.team_members WHERE user_id = auth.uid()
    )
  );

-- 90-day retention policy helper (run via pg_cron or manual)
-- DELETE FROM public.audit_logs WHERE created_at < now() - interval '90 days';
