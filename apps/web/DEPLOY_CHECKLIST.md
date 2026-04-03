# FaultRay デプロイチェックリスト

> アーキテクチャの詳細・ステップバイステップのセットアップ手順は [DEPLOY.md](./DEPLOY.md) を参照。
> このファイルはデプロイ直前の最終チェックリスト。

デプロイ前に全項目を確認すること。1つでも漏れると本番で障害が発生する。

## 1. Vercel 環境変数

| 変数名 | 値 | 必須 |
|--------|-----|------|
| `NEXT_PUBLIC_SUPABASE_URL` | `https://xxx.supabase.co` | 必須 |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | `eyJhb...` | 必須 |
| `NEXT_PUBLIC_SITE_URL` | `https://faultray.com` | 必須 |
| `STRIPE_SECRET_KEY` | `sk_test_...` or `sk_live_...` | 決済時必須 |
| `STRIPE_WEBHOOK_SECRET` | `whsec_...` | Webhook時必須 |
| `STRIPE_PRO_PRICE_ID` | `price_...` | 決済時必須 |
| `STRIPE_BUSINESS_PRICE_ID` | `price_...` | 決済時必須 |

## 2. Supabase 設定

- [ ] **Site URL**: `https://faultray.com` に設定（Auth → URL Configuration）
- [ ] **Redirect URLs**: `https://faultray.com/**` を許可リストに追加
- [ ] **Google OAuth**: Enable → Client ID + Secret 設定済み
- [ ] **GitHub OAuth**: Enable → Client ID + Secret 設定済み
- [ ] **テーブル作成**: profiles, teams, team_members, projects, simulation_runs, billing_events, usage
- [ ] **RLSポリシー**: 全テーブルに設定済み
- [ ] **トリガー**: handle_new_user が auth.users に設定済み

## 3. OAuth プロバイダーのコールバックURL

**全プロバイダーのコールバックURLは Supabase の URL を指す（faultray.com ではない）**

| プロバイダー | コールバックURL |
|-------------|----------------|
| Google (Cloud Console) | `https://xxx.supabase.co/auth/v1/callback` |
| GitHub (Developer Settings) | `https://xxx.supabase.co/auth/v1/callback` |

**よくある間違い**: `https://faultray.com/api/v1/auth/callback/google` を設定してしまう → Supabaseを経由しないため認証が壊れる

## 4. DNS / ドメイン

- [ ] Vercel Domains に `faultray.com` 追加済み
- [ ] Cloudflare DNS: A レコード → Vercel IP
- [ ] SSL証明書: Vercelが自動発行（DNS only推奨、Cloudflare Proxy有効でも動く場合あり）

## 5. 全URL動作確認

以下の全URLで200または適切なリダイレクトが返ること：

```
/ → /en (307)
/en, /ja, /de, /fr, /zh, /ko, /es, /pt → 200
/login → 200
/dashboard → /login (307, 未認証時)
/simulate → /login (307, 未認証時)
/results → /login (307, 未認証時)
/pricing → 200
/demo → /simulate (307)
/en/login → /login (307)
/ja/demo → /demo → /simulate (307)
/api/health → 200
/api/simulate (POST) → 200
/api/compliance (POST) → 200
```

## 6. 認証フロー動作確認

- [ ] Google サインイン → Supabase → faultray.com にリダイレクト → ダッシュボード表示
- [ ] GitHub サインイン → 同上
- [ ] ログアウト → ログインページに戻る
- [ ] 未認証で /dashboard → /login にリダイレクト

## 7. セキュリティ

- [ ] `.env.local` が .gitignore に含まれている
- [ ] ソースコードに機密情報がコミットされていない
- [ ] Supabase service_role key がフロントエンドに露出していない（anon keyのみ）
- [ ] リポジトリが private

## 8. 決済フロー（Stripe）

- [ ] Stripe Checkout → 決済完了 → Webhook → DB更新
- [ ] Customer Portal → プラン変更/解約
- [ ] サンドボックスで全フローをテスト済み
// redeploy 1774827263
