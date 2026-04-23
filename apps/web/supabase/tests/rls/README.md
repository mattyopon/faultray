# RLS multi-tenant isolation tests (#28)

`profiles` / `teams` / `team_members` / `projects` / `simulation_runs` / `usage` / `billing_events` の Row Level Security ポリシーを **pgTAP** で assert する。

## 目的

- 他テナントのデータが絶対に漏れないこと (`SELECT`)
- 権限昇格ができないこと (`team_members` への `admin` 挿入等)
- クロステナント書込が silent に効かないこと (RLS は違反 row を silent filter する)
- `anon` role は何も見えないこと / 何も書き込めないこと
- `usage` / `billing_events` は authenticated role から書込不能 (service-role 経由のみ)

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
| User A (team X owner) | `11111111-1111-...` |
| User B (team X member) | `22222222-2222-...` |
| User C (team Y owner) | `33333333-3333-...` |
| Team X | `44444444-4444-...` |
| Team Y | `55555555-5555-...` |

## 既知の scope 外

- `organizations` / `org_members` テーブルは migration に未定義 (API route は参照中) → 別 Issue で追跡
- Supabase 本番の `auth.uid()` 実装と CI スタブは挙動一致しているが、新 feature 使用時は再確認要
- pgTAP の throws_ok は PostgreSQL error code での比較。RLS の DELETE/UPDATE は `42501` ではなく silent filter されるため、件数確認で検証している
