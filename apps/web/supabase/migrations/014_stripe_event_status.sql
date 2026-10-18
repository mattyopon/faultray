-- 014: Stripe event ledger を 2-state (processing → processed) に拡張
-- ----------------------------------------------------------------------------
-- 背景:
--   013 で processed_stripe_events table を追加し、webhook 受信時に
--   INSERT-on-conflict で dedup していた。しかし side effect (updateUserPlan
--   等) が throw した場合、event は永久に dedup された状態で残り、Stripe の
--   retry が duplicate として skip → billing state が壊れたまま固定。
--
--   Codex review (PR #89) の P1 指摘:
--     "do not make the event permanently deduped before successful handling"
--
-- 設計:
--   - status カラムを追加: 'processing' | 'processed' | 'failed'
--   - webhook 受信時: INSERT (event_id, status='processing') ON CONFLICT DO NOTHING
--     - INSERT 成功 (= 新規 event) → 通常処理 → 成功時 UPDATE status='processed'
--     - INSERT 衝突 (= 重複) → 既存 status を check:
--         processed  → 200 duplicate (Stripe は retry を止める)
--         processing → 503 (worker crash 残留時に Stripe retry が止まらないように)
--         failed     → 再処理 (UPDATE status='processing')
--   - side effect 失敗時: UPDATE status='failed', last_error 記録 → 500 return
--     (Stripe retry が来た時に上記 'failed' branch で reclaim される)
--   - 既存 row は status='processed' 扱い (既に side effect 完了している前提)
-- ----------------------------------------------------------------------------

alter table public.processed_stripe_events
  add column if not exists status text not null default 'processed'
    check (status in ('processing', 'processed', 'failed'));

alter table public.processed_stripe_events
  add column if not exists last_error text;

alter table public.processed_stripe_events
  add column if not exists updated_at timestamptz not null default now();

-- updated_at auto-bump trigger (003 の set_updated_at を再利用)
drop trigger if exists set_processed_stripe_events_updated_at
  on public.processed_stripe_events;
create trigger set_processed_stripe_events_updated_at
  before update on public.processed_stripe_events
  for each row
  execute function public.set_updated_at();

-- Index for the rare 'failed' / 'processing' lookup paths
create index if not exists idx_processed_stripe_events_status
  on public.processed_stripe_events (status, processed_at desc)
  where status <> 'processed';
