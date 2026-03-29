-- FaultRay SaaS Database Schema
-- Run this in the Supabase SQL editor

-- Enable UUID extension
create extension if not exists "uuid-ossp";

-- Users profile table (extends auth.users)
create table if not exists public.profiles (
  id uuid references auth.users(id) on delete cascade primary key,
  email text,
  full_name text,
  avatar_url text,
  plan text default 'free' check (plan in ('free', 'pro', 'business')),
  stripe_customer_id text,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

-- Teams
create table if not exists public.teams (
  id uuid default uuid_generate_v4() primary key,
  name text not null,
  owner_id uuid references public.profiles(id) on delete cascade not null,
  plan text default 'free' check (plan in ('free', 'pro', 'business')),
  stripe_customer_id text,
  stripe_subscription_id text,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

-- Team members
create table if not exists public.team_members (
  team_id uuid references public.teams(id) on delete cascade,
  user_id uuid references public.profiles(id) on delete cascade,
  role text default 'member' check (role in ('owner', 'admin', 'member')),
  created_at timestamptz default now(),
  primary key (team_id, user_id)
);

-- Projects
create table if not exists public.projects (
  id uuid default uuid_generate_v4() primary key,
  team_id uuid references public.teams(id) on delete cascade,
  name text not null,
  description text,
  topology_yaml text,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

-- Simulation runs
create table if not exists public.simulation_runs (
  id uuid default uuid_generate_v4() primary key,
  project_id uuid references public.projects(id) on delete cascade,
  team_id uuid references public.teams(id) on delete cascade,
  user_id uuid references public.profiles(id),
  overall_score numeric(5,2),
  availability_estimate text,
  nines numeric(5,2),
  engine_type text default 'static',
  scenarios_passed integer default 0,
  scenarios_failed integer default 0,
  total_scenarios integer default 0,
  result_data jsonb,
  created_at timestamptz default now()
);

-- Billing events
create table if not exists public.billing_events (
  id uuid default uuid_generate_v4() primary key,
  team_id uuid references public.teams(id) on delete cascade,
  event_type text not null,
  stripe_event_id text,
  data jsonb,
  created_at timestamptz default now()
);

-- Usage tracking
create table if not exists public.usage (
  id uuid default uuid_generate_v4() primary key,
  team_id uuid references public.teams(id) on delete cascade,
  month text not null, -- '2026-03'
  simulation_count integer default 0,
  created_at timestamptz default now(),
  unique(team_id, month)
);

-- Row Level Security
alter table public.profiles enable row level security;
alter table public.teams enable row level security;
alter table public.team_members enable row level security;
alter table public.projects enable row level security;
alter table public.simulation_runs enable row level security;
alter table public.billing_events enable row level security;
alter table public.usage enable row level security;

-- Profiles: users can read/update their own profile
create policy "Users can view own profile"
  on public.profiles for select
  using (auth.uid() = id);

create policy "Users can update own profile"
  on public.profiles for update
  using (auth.uid() = id);

-- Teams: members can view their teams
create policy "Team members can view teams"
  on public.teams for select
  using (
    id in (
      select team_id from public.team_members
      where user_id = auth.uid()
    )
  );

create policy "Users can create teams"
  on public.teams for insert
  with check (owner_id = auth.uid());

-- Team members: members can view team membership
create policy "Members can view team members"
  on public.team_members for select
  using (
    team_id in (
      select team_id from public.team_members
      where user_id = auth.uid()
    )
  );

-- Projects: team members can view/create projects
create policy "Team members can view projects"
  on public.projects for select
  using (
    team_id in (
      select team_id from public.team_members
      where user_id = auth.uid()
    )
  );

create policy "Team members can create projects"
  on public.projects for insert
  with check (
    team_id in (
      select team_id from public.team_members
      where user_id = auth.uid()
    )
  );

-- Simulation runs: team members can view/create runs
create policy "Team members can view runs"
  on public.simulation_runs for select
  using (
    team_id in (
      select team_id from public.team_members
      where user_id = auth.uid()
    )
  );

create policy "Team members can create runs"
  on public.simulation_runs for insert
  with check (
    team_id in (
      select team_id from public.team_members
      where user_id = auth.uid()
    )
  );

-- Usage: team members can view usage
create policy "Team members can view usage"
  on public.usage for select
  using (
    team_id in (
      select team_id from public.team_members
      where user_id = auth.uid()
    )
  );

-- Billing events: team owners/admins can view
create policy "Team admins can view billing"
  on public.billing_events for select
  using (
    team_id in (
      select team_id from public.team_members
      where user_id = auth.uid() and role in ('owner', 'admin')
    )
  );

-- Auto-create profile on signup
create or replace function public.handle_new_user()
returns trigger as $$
begin
  insert into public.profiles (id, email, full_name, avatar_url)
  values (
    new.id,
    new.email,
    new.raw_user_meta_data->>'full_name',
    new.raw_user_meta_data->>'avatar_url'
  );

  -- Create a default personal team
  insert into public.teams (name, owner_id)
  values (coalesce(new.raw_user_meta_data->>'full_name', split_part(new.email, '@', 1)) || '''s Team', new.id)
  returning id into new.id;

  return new;
end;
$$ language plpgsql security definer;

-- Trigger on auth.users insert
drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- Indexes
create index if not exists idx_simulation_runs_team on public.simulation_runs(team_id);
create index if not exists idx_simulation_runs_created on public.simulation_runs(created_at desc);
create index if not exists idx_projects_team on public.projects(team_id);
create index if not exists idx_team_members_user on public.team_members(user_id);
create index if not exists idx_usage_team_month on public.usage(team_id, month);
