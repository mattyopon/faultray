# FaultRay Cloud Setup Assistant

Chrome拡張機能。非エンジニアがAWSのIAMロール作成 → アクセスキー生成 → FaultRayへの自動連携をガイド付きで完了できる。

## 機能

- FaultRayアカウントとの認証連携
- AWSコンソール上でのステップバイステップガイドオーバーレイ
- アクセスキーの安全なFaultRay送信（送信後即時削除）
- 接続済みクラウド環境の一覧表示
- GCP / Azure サポート（近日公開）

## インストール（開発者モード）

1. このリポジトリをクローン:
   ```bash
   git clone https://github.com/mattyopon/faultray-chrome-extension.git
   cd faultray-chrome-extension
   ```

2. 依存関係をインストール:
   ```bash
   npm install
   ```

3. ビルド:
   ```bash
   npm run build
   ```

4. Chromeに読み込む:
   - `chrome://extensions` を開く
   - 右上の **「デベロッパーモード」** をONにする
   - **「パッケージ化されていない拡張機能を読み込む」** をクリック
   - `dist/` フォルダを選択

## 使い方

1. 拡張機能アイコンをクリック
2. **「FaultRayにログイン」** でfaultray.comにログイン
3. ポップアップに戻り **「AWS セットアップ開始」** をクリック
4. AWSコンソールが開き、画面右下にガイドパネルが表示される
5. パネルの指示に従いIAMユーザー作成 → アクセスキー生成を完了
6. Step 5でアクセスキーを入力し **「FaultRayに送信」** をクリック

## セキュリティ

### アクセスキーの取り扱い
- AWSアクセスキーは `chrome.storage.session` に一時保管（ブラウザを閉じると自動削除）
- FaultRay APIへの送信はHTTPS通信のみ
- 送信成功後、即座にセッションストレージから削除
- ローカルストレージには保存しない

### 推奨IAM設定
- **ReadOnlyAccess** ポリシーのみをアタッチすることを強く推奨
- 書き込み権限は不要（FaultRayは読み取り専用でクラウド環境を分析）

### 権限
この拡張機能が要求する権限:

| 権限 | 理由 |
|------|------|
| `storage` | FaultRayセッションと接続情報の保存 |
| `activeTab` | AWSコンソールのタブ検出 |
| `tabs` | セットアップウィザードでの新しいタブ開く |
| `alarms` | Service Workerの維持 |
| `https://console.aws.amazon.com/*` | AWSコンソールへのガイドオーバーレイ注入 |
| `https://faultray.com/*` | FaultRay APIとの通信 |

## 開発

```bash
# 型チェック
npm run typecheck

# ビルド
npm run build

# アイコン生成（sharpが必要）
npm run build:icons
```

## アーキテクチャ

```
src/
├── popup/          React UI（拡張機能ポップアップ）
├── content/        AWSコンソール用コンテンツスクリプト
├── background/     Service Worker（認証・API通信）
└── lib/            共有型定義・ストレージ・APIクライアント
```

## バックエンドAPI（未実装）

`POST https://faultray.com/api/cloud-credentials` は現在未実装。
フロントエンド（この拡張）は完成済み。バックエンドの実装後に自動的に動作します。

## ライセンス

MIT
