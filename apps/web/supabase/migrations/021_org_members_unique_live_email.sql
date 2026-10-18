-- ============================================================
-- 021 (#117): org_members の「生きている招待/メンバー行」を DB 層で一意化
--
-- 背景:
--   招待の重複チェックは route の pre-insert read のみで、DB に一意性保証が
--   ない。並行リクエストは両方とも read を通過して pending 行を二重作成でき、
--   一度重複ができると route の .single() がエラーになり (error は無視される)
--   さらに重複が通る構造バグだった。
--
-- 一意性の単位:
--   (org_id, lower(email)) につき status <> 'removed' の行は最大 1 行。
--   'removed' は再招待を許すため除外 (route も status !== 'removed' を
--   既存判定に使っている)。
--
-- 手順 (冪等):
--   1. 既存重複の整理。同一 (org_id, lower(email)) の生存行のうち
--      active 優先 → invited_at が最古 → id 順で 1 行を残す。
--   2. 削除予定行を tasks.assignee_id が参照している場合は残す行へ付け替え
--      (同一人物のため意味は保存される)。FK 違反の防止。
--   3. partial unique index を作成。
-- ============================================================

do $$
begin
  -- 1+2. 重複行の解決 (空テーブル/重複なしでは no-op)
  create temp table _om_dupes on commit drop as
  select id as dup_id,
         first_value(id) over (
           partition by org_id, lower(email)
           order by (status = 'active') desc, invited_at asc, id asc
         ) as keep_id
  from public.org_members
  where status <> 'removed';

  delete from _om_dupes where dup_id = keep_id;

  update public.tasks t
     set assignee_id = d.keep_id
    from _om_dupes d
   where t.assignee_id = d.dup_id;

  delete from public.org_members om
   using _om_dupes d
   where om.id = d.dup_id;
end $$;

-- 3. 生存行 (pending/active 等) の一意化。'removed' は対象外なので
--    退会→再招待のフローは引き続き成立する。
create unique index if not exists org_members_live_email_unique
  on public.org_members (org_id, lower(email))
  where status <> 'removed';
