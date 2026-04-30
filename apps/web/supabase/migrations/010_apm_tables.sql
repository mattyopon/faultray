-- APM Agents registry
create table if not exists public.apm_agents (
  agent_id text primary key,
  hostname text not null,
  ip_address text,
  status text default 'running' check (status in ('running', 'degraded', 'offline')),
  os_info text,
  version text,
  labels jsonb default '{}',
  registered_at timestamptz default now(),
  last_seen timestamptz default now()
);

-- APM Metric points (time-series)
create table if not exists public.apm_metrics (
  id uuid default uuid_generate_v4() primary key,
  agent_id text references public.apm_agents(agent_id) on delete cascade,
  metric_name text not null,
  value numeric not null,
  tags jsonb default '{}',
  collected_at timestamptz default now()
);

-- Index for fast time-range queries
create index if not exists idx_apm_metrics_agent_time
  on public.apm_metrics (agent_id, collected_at desc);
create index if not exists idx_apm_metrics_name_time
  on public.apm_metrics (metric_name, collected_at desc);

-- APM Alerts
create table if not exists public.apm_alerts (
  id uuid default uuid_generate_v4() primary key,
  agent_id text references public.apm_agents(agent_id) on delete cascade,
  severity text default 'info' check (severity in ('critical', 'warning', 'info')),
  rule_name text not null,
  metric_name text,
  metric_value numeric,
  threshold numeric,
  message text,
  fired_at timestamptz default now(),
  resolved_at timestamptz
);

create index if not exists idx_apm_alerts_agent
  on public.apm_alerts (agent_id, fired_at desc);
create index if not exists idx_apm_alerts_severity
  on public.apm_alerts (severity, fired_at desc);

-- Enable RLS
alter table public.apm_agents enable row level security;
alter table public.apm_metrics enable row level security;
alter table public.apm_alerts enable row level security;

-- Service role can do everything (used by API)
create policy "Service role full access" on public.apm_agents
  for all using (true) with check (true);
create policy "Service role full access" on public.apm_metrics
  for all using (true) with check (true);
create policy "Service role full access" on public.apm_alerts
  for all using (true) with check (true);

-- Auto-update last_seen on heartbeat
create or replace function update_agent_last_seen()
returns trigger as $$
begin
  NEW.last_seen = now();
  return NEW;
end;
$$ language plpgsql;

create trigger trg_update_agent_last_seen
  before update on public.apm_agents
  for each row execute function update_agent_last_seen();
