-- SCHEMA-07: simulation_runs に updated_at を追加（変更履歴追跡）
alter table public.simulation_runs
  add column if not exists updated_at timestamptz default now();

-- updated_at を自動更新するトリガー
create or replace function public.set_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists simulation_runs_updated_at on public.simulation_runs;
create trigger simulation_runs_updated_at
  before update on public.simulation_runs
  for each row execute function public.set_updated_at();

-- SCHEMA-09: overall_score 等のデフォルト値設定
-- overall_score は numeric(5,2) だがデフォルト値なし → 0 をデフォルトに
alter table public.simulation_runs
  alter column overall_score set default 0,
  alter column scenarios_passed set default 0,
  alter column scenarios_failed set default 0,
  alter column total_scenarios set default 0;

-- SCHEMA-10: project_id 削除時のカスケード動作確認
-- 現状: simulation_runs.project_id references projects(id) on delete cascade ✓
-- 念のため billing_events も確認（team_id cascade あり）

-- SCHEMA-07 補足: 既存行のupdated_atをcreated_atで初期化
update public.simulation_runs
  set updated_at = created_at
  where updated_at is null;

-- RLS-06: profilesのUPDATEポリシーにWITH CHECKを追加（間接参照の防止）
-- 既存のポリシーを削除して WITH CHECK を含む安全なポリシーで再作成
drop policy if exists "Users can update own profile" on public.profiles;
create policy "Users can update own profile"
  on public.profiles for update
  using (auth.uid() = id)
  with check (auth.uid() = id);

