# RLS multi-tenant isolation tests (#28, #73)

**Legacy 7 テーブル** (#28):
`profiles` / `teams` / `team_members` / `projects` / `simulation_runs` / `usage` / `billing_events`

**Org/タスク 3 テーブル** (#73 で追加, migration 009 + 013 + 015):
`organizations` / `org_members` / `tasks`

これら 10 テーブルの Row Level Security ポリシーを **pgTAP** で assert する。

## 目的

- 他テナント (team / org) のデータが絶対に漏れないこと (`SELECT`)
- 権限昇格ができないこと (`team_members` への `admin` 挿入、`org_members` への `role='owner'` / `status='active'` 直接 INSERT 等)
- クロステナント書込が silent に効かないこと (RLS は違反 row を silent filter する)
- `anon` role は何も見えないこと / 何も書き込めないこと
- `usage` / `billing_events` は authenticated role から書込不能 (service-role 経由のみ)
- migration 013 で fix 済の P1-7 (org_members invite role/status 制約) が regression しないこと
- migration 015 で fix 済の #70 finding 2 (`tasks.created_by` 偽装) が regression しないこと
- migration 015 で解消した self-referential recursion (#70 finding 1) のため、`organizations` / `org_members` SELECT が fresh DB でも実行できること (recursion で死なないこと)

## ローカル実行

Supabase CLI + local postgres を前提:

```bash
# 1. ローカル DB 起動 + migrations 適用
supabase db reset

# 2. pgTAP 拡張が入っていなければ有効化
psql -h 127.0.0.1 -p 54322 -U postgres -d postgres \
  -c "create extension if not exists pgtap"

# 3. テスト実行
psql -h 127.0.0.1 -p 54322 -U postgres -d postgres \
  -f supabase/tests/rls/multitenant.test.sql
```

## CI 実行

`.github/workflows/ci.yml` の `test-rls` job が自動で実行する。ubuntu-latest + postgres:16 サービスコンテナ + `postgresql-16-pgtap` で走る。

## テストで使用する固定 UUID

| 役割 | UUID |
|---|---|
| User A (team X owner / org_p admin / org_p owner) | `11111111-1111-...` |
| User B (team X member / org_p member) | `22222222-2222-...` |
| User C (team Y owner / org_q owner) | `33333333-3333-...` |
| Team X | `44444444-4444-...` |
| Team Y | `55555555-5555-...` |
| Org P (`organizations.id`) | `aaaaaaaa-aaaa-...` |
| Org Q (`organizations.id`) | `bbbbbbbb-bbbb-...` |
| Task P1 | `cccccccc-cccc-...` |
| Task Q1 | `dddddddd-dddd-...` |
| Org Bootstrap (self-bootstrap test 用) | `eeeeeeee-eeee-...` |

## 既知の scope 外

- migration 010 (`apm_*`) と 011 (`audit_logs`) の RLS は別 Issue で追跡
- migration 013 で `processed_stripe_events` が追加されたが service_role only なので本テスト範囲外
- Supabase 本番の `auth.uid()` 実装と CI スタブは挙動一致しているが、新 feature 使用時は再確認要
- pgTAP の `throws_ok` は PostgreSQL error code での比較。RLS の DELETE/UPDATE は `42501` ではなく silent filter されるため、件数確認で検証している
- #70 finding 3-5 (`auth.users` への FK の `ON DELETE` 未指定) はスキーマ変更で別 PR/Issue で扱う
