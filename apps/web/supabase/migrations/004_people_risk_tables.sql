-- ============================================================
-- People Risk テーブル群
-- - companies      : テナント（組織）
-- - members        : 組織メンバー（在籍/退職済み）
-- - systems        : 管理対象システム
-- - member_systems : メンバー × システム の関係
-- - actions        : 改善アクション
-- - risk_snapshots : 週次リスクスナップショット
-- ============================================================

-- ── companies ───────────────────────────────────────────────
create table if not exists public.companies (
  id          uuid default uuid_generate_v4() primary key,
  name        text not null,
  owner_id    uuid references public.profiles(id) on delete set null,
  created_at  timestamptz default now()
);

alter table public.companies enable row level security;

-- 自分が所有する会社のみ参照可
create policy "Owner can view own company"
  on public.companies for select
  using (owner_id = auth.uid());

create policy "Owner can insert own company"
  on public.companies for insert
  with check (owner_id = auth.uid());

create policy "Owner can update own company"
  on public.companies for update
  using (owner_id = auth.uid())
  with check (owner_id = auth.uid());

-- ── members ─────────────────────────────────────────────────
create table if not exists public.members (
  id          uuid default uuid_generate_v4() primary key,
  company_id  uuid references public.companies(id) on delete cascade not null,
  name        text not null,
  department  text,
  role        text,
  status      text default 'active' check (status in ('active', 'left')),
  created_at  timestamptz default now()
);

create index if not exists idx_members_company on public.members(company_id);

alter table public.members enable row level security;

create policy "Company owner can view members"
  on public.members for select
  using (
    company_id in (
      select id from public.companies where owner_id = auth.uid()
    )
  );

create policy "Company owner can insert members"
  on public.members for insert
  with check (
    company_id in (
      select id from public.companies where owner_id = auth.uid()
    )
  );

create policy "Company owner can update members"
  on public.members for update
  using (
    company_id in (
      select id from public.companies where owner_id = auth.uid()
    )
  )
  with check (
    company_id in (
      select id from public.companies where owner_id = auth.uid()
    )
  );

create policy "Company owner can delete members"
  on public.members for delete
  using (
    company_id in (
      select id from public.companies where owner_id = auth.uid()
    )
  );

-- ── systems ──────────────────────────────────────────────────
create table if not exists public.systems (
  id           uuid default uuid_generate_v4() primary key,
  company_id   uuid references public.companies(id) on delete cascade not null,
  name         text not null,
  type         text check (type in ('gas', 'aws', 'saas', 'database', 'infra', 'process')),
  description  text,
  status       text default 'active' check (status in ('active', 'orphaned', 'dormant')),
  last_updated timestamptz,
  created_at   timestamptz default now()
);

create index if not exists idx_systems_company on public.systems(company_id);

alter table public.systems enable row level security;

create policy "Company owner can view systems"
  on public.systems for select
  using (
    company_id in (
      select id from public.companies where owner_id = auth.uid()
    )
  );

create policy "Company owner can insert systems"
  on public.systems for insert
  with check (
    company_id in (
      select id from public.companies where owner_id = auth.uid()
    )
  );

create policy "Company owner can update systems"
  on public.systems for update
  using (
    company_id in (
      select id from public.companies where owner_id = auth.uid()
    )
  )
  with check (
    company_id in (
      select id from public.companies where owner_id = auth.uid()
    )
  );

create policy "Company owner can delete systems"
  on public.systems for delete
  using (
    company_id in (
      select id from public.companies where owner_id = auth.uid()
    )
  );

-- ── member_systems ───────────────────────────────────────────
create table if not exists public.member_systems (
  id           uuid default uuid_generate_v4() primary key,
  member_id    uuid references public.members(id) on delete cascade not null,
  system_id    uuid references public.systems(id) on delete cascade not null,
  access_level text check (access_level in ('owner', 'admin', 'editor', 'viewer')),
  is_sole_owner boolean default false not null,
  risk_level   text check (risk_level in ('critical', 'warning', 'safe')),
  notes        text,
  unique (member_id, system_id)
);

create index if not exists idx_member_systems_member on public.member_systems(member_id);
create index if not exists idx_member_systems_system on public.member_systems(system_id);

alter table public.member_systems enable row level security;

-- member_systems の RLS: 所属する company_id を辿って判定
create policy "Company owner can view member_systems"
  on public.member_systems for select
  using (
    member_id in (
      select m.id from public.members m
      join public.companies c on c.id = m.company_id
      where c.owner_id = auth.uid()
    )
  );

create policy "Company owner can insert member_systems"
  on public.member_systems for insert
  with check (
    member_id in (
      select m.id from public.members m
      join public.companies c on c.id = m.company_id
      where c.owner_id = auth.uid()
    )
  );

create policy "Company owner can update member_systems"
  on public.member_systems for update
  using (
    member_id in (
      select m.id from public.members m
      join public.companies c on c.id = m.company_id
      where c.owner_id = auth.uid()
    )
  );

create policy "Company owner can delete member_systems"
  on public.member_systems for delete
  using (
    member_id in (
      select m.id from public.members m
      join public.companies c on c.id = m.company_id
      where c.owner_id = auth.uid()
    )
  );

-- ── actions ──────────────────────────────────────────────────
create table if not exists public.actions (
  id             uuid default uuid_generate_v4() primary key,
  company_id     uuid references public.companies(id) on delete cascade not null,
  system_id      uuid references public.systems(id) on delete set null,
  title          text not null,
  description    text,
  priority       text check (priority in ('critical', 'warning', 'info')),
  risk_reduction numeric(4,1),
  status         text default 'pending' check (status in ('pending', 'in_progress', 'done')),
  created_at     timestamptz default now()
);

create index if not exists idx_actions_company on public.actions(company_id);

alter table public.actions enable row level security;

create policy "Company owner can view actions"
  on public.actions for select
  using (
    company_id in (
      select id from public.companies where owner_id = auth.uid()
    )
  );

create policy "Company owner can insert actions"
  on public.actions for insert
  with check (
    company_id in (
      select id from public.companies where owner_id = auth.uid()
    )
  );

create policy "Company owner can update actions"
  on public.actions for update
  using (
    company_id in (
      select id from public.companies where owner_id = auth.uid()
    )
  )
  with check (
    company_id in (
      select id from public.companies where owner_id = auth.uid()
    )
  );

create policy "Company owner can delete actions"
  on public.actions for delete
  using (
    company_id in (
      select id from public.companies where owner_id = auth.uid()
    )
  );

-- ── risk_snapshots ───────────────────────────────────────────
create table if not exists public.risk_snapshots (
  id                 uuid default uuid_generate_v4() primary key,
  company_id         uuid references public.companies(id) on delete cascade not null,
  week_start         date not null,
  avg_risk_score     numeric(4,2),
  bus_factor_1_count integer,
  total_systems      integer,
  created_at         timestamptz default now(),
  unique (company_id, week_start)
);

create index if not exists idx_risk_snapshots_company on public.risk_snapshots(company_id);

alter table public.risk_snapshots enable row level security;

create policy "Company owner can view risk_snapshots"
  on public.risk_snapshots for select
  using (
    company_id in (
      select id from public.companies where owner_id = auth.uid()
    )
  );

create policy "Company owner can insert risk_snapshots"
  on public.risk_snapshots for insert
  with check (
    company_id in (
      select id from public.companies where owner_id = auth.uid()
    )
  );

-- ============================================================
-- Seed data: デモ用初期データ（company_id = 固定UUID）
-- ============================================================

-- デモ会社（queries.ts の DEMO_COMPANY_ID と一致）
insert into public.companies (id, name, owner_id)
values (
  '11111111-1111-1111-1111-111111111111',
  'デモ株式会社',
  null  -- デモデータはオーナー不要
)
on conflict (id) do nothing;

-- デモメンバー
insert into public.members (id, company_id, name, department, role, status)
values
  ('aaaaaaaa-0001-0001-0001-000000000001', '11111111-1111-1111-1111-111111111111', '山田 太郎', 'インフラ部', 'SREリード', 'active'),
  ('aaaaaaaa-0001-0001-0001-000000000002', '11111111-1111-1111-1111-111111111111', '鈴木 花子', '開発部', 'バックエンドエンジニア', 'active'),
  ('aaaaaaaa-0001-0001-0001-000000000003', '11111111-1111-1111-1111-111111111111', '田中 次郎', '開発部', 'フロントエンドエンジニア', 'active'),
  ('aaaaaaaa-0001-0001-0001-000000000004', '11111111-1111-1111-1111-111111111111', '佐藤 美咲', '総務部', 'オペレーター', 'left'),
  ('aaaaaaaa-0001-0001-0001-000000000005', '11111111-1111-1111-1111-111111111111', '渡辺 健一', 'データ基盤部', 'データエンジニア', 'active')
on conflict (id) do nothing;

-- デモシステム
insert into public.systems (id, company_id, name, type, description, status, last_updated)
values
  ('bbbbbbbb-0001-0001-0001-000000000001', '11111111-1111-1111-1111-111111111111', '本番DBクラスター',      'database', 'PostgreSQL RDS（本番）',        'active',   now() - interval '2 days'),
  ('bbbbbbbb-0001-0001-0001-000000000002', '11111111-1111-1111-1111-111111111111', 'デプロイパイプライン',   'aws',      'GitHub Actions + ECS',         'active',   now() - interval '1 day'),
  ('bbbbbbbb-0001-0001-0001-000000000003', '11111111-1111-1111-1111-111111111111', '経費精算GAS',           'gas',      'Google Apps Script 経費申請',   'orphaned', now() - interval '30 days'),
  ('bbbbbbbb-0001-0001-0001-000000000004', '11111111-1111-1111-1111-111111111111', 'Slackワークスペース管理','saas',     'Slack 管理者アカウント',        'active',   now() - interval '5 days'),
  ('bbbbbbbb-0001-0001-0001-000000000005', '11111111-1111-1111-1111-111111111111', 'データウェアハウス',     'database', 'BigQuery プロジェクト',         'active',   now() - interval '3 days'),
  ('bbbbbbbb-0001-0001-0001-000000000006', '11111111-1111-1111-1111-111111111111', '顧客オンボーディングGAS','gas',      '顧客登録自動化スクリプト',      'dormant',  now() - interval '60 days')
on conflict (id) do nothing;

-- デモ member_systems
insert into public.member_systems (member_id, system_id, access_level, is_sole_owner, risk_level, notes)
values
  ('aaaaaaaa-0001-0001-0001-000000000001', 'bbbbbbbb-0001-0001-0001-000000000001', 'owner',  true,  'critical', '唯一のDBA。引き継ぎが急務'),
  ('aaaaaaaa-0001-0001-0001-000000000001', 'bbbbbbbb-0001-0001-0001-000000000002', 'admin',  false, 'warning',  null),
  ('aaaaaaaa-0001-0001-0001-000000000002', 'bbbbbbbb-0001-0001-0001-000000000002', 'owner',  true,  'critical', 'デプロイ権限が山田・鈴木の2名のみ'),
  ('aaaaaaaa-0001-0001-0001-000000000002', 'bbbbbbbb-0001-0001-0001-000000000005', 'admin',  false, 'warning',  null),
  ('aaaaaaaa-0001-0001-0001-000000000003', 'bbbbbbbb-0001-0001-0001-000000000004', 'admin',  false, 'safe',     null),
  ('aaaaaaaa-0001-0001-0001-000000000004', 'bbbbbbbb-0001-0001-0001-000000000003', 'owner',  true,  'critical', '退職済み。GASが孤立状態'),
  ('aaaaaaaa-0001-0001-0001-000000000004', 'bbbbbbbb-0001-0001-0001-000000000006', 'owner',  true,  'critical', '退職済み。引き継ぎ未完了'),
  ('aaaaaaaa-0001-0001-0001-000000000005', 'bbbbbbbb-0001-0001-0001-000000000005', 'owner',  true,  'warning',  'データ基盤の唯一の担当者'),
  ('aaaaaaaa-0001-0001-0001-000000000005', 'bbbbbbbb-0001-0001-0001-000000000001', 'viewer', false, 'safe',     null)
on conflict (member_id, system_id) do nothing;

-- デモアクション
insert into public.actions (company_id, system_id, title, description, priority, risk_reduction, status)
values
  ('11111111-1111-1111-1111-111111111111', 'bbbbbbbb-0001-0001-0001-000000000001', '本番DBのバックアップDBAを任命する',     '山田氏が唯一のDBオーナーであるため、後継者を育成する必要があります', 'critical', 8.0, 'pending'),
  ('11111111-1111-1111-1111-111111111111', 'bbbbbbbb-0001-0001-0001-000000000003', '経費精算GASの引き継ぎを完了する',       '佐藤氏退職後に孤立。業務プロセスへの影響を確認してください',       'critical', 7.5, 'in_progress'),
  ('11111111-1111-1111-1111-111111111111', 'bbbbbbbb-0001-0001-0001-000000000006', 'オンボーディングGASの管理者を再設定する','退職メンバーが唯一のオーナー。新規顧客対応に影響あり',             'critical', 7.0, 'pending'),
  ('11111111-1111-1111-1111-111111111111', 'bbbbbbbb-0001-0001-0001-000000000005', 'データ基盤の属人化を解消する',          '渡辺氏が唯一の担当者。ドキュメントを整備し副担当を設定してください', 'warning',  5.0, 'pending'),
  ('11111111-1111-1111-1111-111111111111', 'bbbbbbbb-0001-0001-0001-000000000002', 'デプロイ権限を3名以上に拡大する',       '現在2名のみ。障害発生時の対応力を高めるためにも追加権限付与を推奨', 'warning',  4.5, 'pending')
on conflict do nothing;

-- デモ risk_snapshots（直近5週）
insert into public.risk_snapshots (company_id, week_start, avg_risk_score, bus_factor_1_count, total_systems)
values
  ('11111111-1111-1111-1111-111111111111', current_date - interval '28 days', 7.2, 5, 6),
  ('11111111-1111-1111-1111-111111111111', current_date - interval '21 days', 6.8, 4, 6),
  ('11111111-1111-1111-1111-111111111111', current_date - interval '14 days', 6.5, 4, 6),
  ('11111111-1111-1111-1111-111111111111', current_date - interval '7 days',  6.1, 3, 6),
  ('11111111-1111-1111-1111-111111111111', current_date,                       5.8, 3, 6)
on conflict (company_id, week_start) do nothing;
