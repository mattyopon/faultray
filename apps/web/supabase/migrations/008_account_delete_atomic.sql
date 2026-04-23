-- ============================================================
-- Fix #29: atomic account deletion via PL/pgSQL SECURITY DEFINER function
--
-- 背景:
--   /api/account/delete は profiles/teams/team_members/projects/
--   simulation_runs/usage/billing_events を順次 delete していたが、
--   Supabase JS client に明示的 tx API が無いため、中途で失敗すると
--   orphan row (ex. team が残って team_members だけ消える) が発生し、
--   復旧が customer support 案件化するリスクがあった。GDPR 削除要求
--   の compliance 観点でも問題。
--
-- 対処:
--   set-based で全テーブルを 1 tx 内で削除する SECURITY DEFINER 関数を
--   定義し、API route から RPC 1 回で呼び出す。
--
--   関数の中身は (1) ownedTeams の id を取得、(2) 依存テーブルを
--   一括 delete、(3) team_members membership 解除、(4) profile 削除、
--   までを atomic に実行し、削除件数を返す。
--
--   auth.users と Stripe subscription は外部サービスなので、DB tx の
--   外側で route が個別 cancel する (現状維持)。
-- ============================================================

create or replace function public.delete_user_account(uid uuid)
returns table (
  teams_deleted integer,
  runs_deleted integer,
  projects_deleted integer,
  memberships_deleted integer,
  profile_deleted integer
)
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  owned_team_ids uuid[];
  v_runs int := 0;
  v_projects int := 0;
  v_teams int := 0;
  v_members int := 0;
  v_profile int := 0;
begin
  -- 1) ownedTeams を array で取得
  select coalesce(array_agg(id), '{}'::uuid[])
    into owned_team_ids
  from public.teams
  where owner_id = uid;

  if array_length(owned_team_ids, 1) is not null then
    -- simulation_runs / usage / billing_events はすべて team_id で
    -- cascade 削除できるテーブル。明示的に delete して count を返す。
    delete from public.simulation_runs
      where team_id = any(owned_team_ids);
    get diagnostics v_runs = row_count;

    delete from public.usage
      where team_id = any(owned_team_ids);

    delete from public.billing_events
      where team_id = any(owned_team_ids);

    delete from public.projects
      where team_id = any(owned_team_ids);
    get diagnostics v_projects = row_count;

    -- 所有 team の全 membership を削除
    delete from public.team_members
      where team_id = any(owned_team_ids);
    get diagnostics v_members = row_count;

    -- team 本体
    delete from public.teams
      where id = any(owned_team_ids);
    get diagnostics v_teams = row_count;
  end if;

  -- 2) 自分が join している他人の team の membership も削除
  delete from public.team_members
    where user_id = uid;
  -- (v_members は既に owned 分だけ数えている。join 先 membership は
  --  別カウントにするほどの情報価値がないので合算しない)

  -- 3) profile 削除 (ON DELETE CASCADE で auth.users から降ってくる
  --    削除より先に能動的に実行)
  delete from public.profiles where id = uid;
  get diagnostics v_profile = row_count;

  return query select v_teams, v_runs, v_projects, v_members, v_profile;
end;
$$;

-- service_role からのみ呼び出せるよう権限を明示的に絞る
revoke all on function public.delete_user_account(uuid) from public;
grant execute on function public.delete_user_account(uuid) to service_role;
