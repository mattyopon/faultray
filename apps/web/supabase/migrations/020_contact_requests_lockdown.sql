-- ============================================================
-- 020 (#118): contact_requests への browser 直接 INSERT を閉鎖
--
-- 背景:
--   公開フォームが anon クライアントで contact_requests に直接 INSERT して
--   おり (016 の "Anyone can insert" policy)、server-side validation も
--   rate limit も通らない。スクリプトで任意の行を無制限に作成できた。
--
-- 対処:
--   書き込みは新設の /api/contact (server route: validation + rate limit +
--   service_role insert) のみとし、anon/authenticated の INSERT policy と
--   table grant を撤去する。service_role は RLS bypass なので route は
--   引き続き書き込める。
--
-- 互換性:
--   このマイグレーションと同じデプロイでフォームは /api/contact 経由に
--   切り替わる。適用後、旧バンドルをキャッシュしたタブからの直接 INSERT
--   は RLS deny で失敗する (公開フォームなので許容)。
-- ============================================================

drop policy if exists "Anyone can insert contact requests" on public.contact_requests;

revoke insert, update, delete on public.contact_requests from anon, authenticated;
-- SELECT は元々 policy 不在で RLS deny だが、grant も最小化しておく。
revoke select on public.contact_requests from anon, authenticated;
