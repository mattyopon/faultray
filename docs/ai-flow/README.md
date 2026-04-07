# AI駆動開発ワークフロー (ai-flow)

Zenn記事「AI駆動開発ワークフロー：要件定義からPRマージまでの自動化」(maya_honey, 2026) を、Linear→GitHub Issues に置き換えてFaultRayに適用したワークフロー。

**発端**: 2026-04-07 構築、2026-04-08 Devin競争レビュー結果を反映して **Devin主軸ポリシー** に確定。

## 開発フロー (Devin主軸)

```
Claude Code (指示者) → Devin (実装者・VM内) → CodeRabbit + Claude Code (レビュアー) → 人間 (最終マージ)
                                              ↑ 必須通過、Devin Self-reviewはカウントしない
```

**Claude Code は FaultRay コードを直接実装しない**。実装は必ず Devin 経由。理由は `feedback_claude_code_fakework.md` (Claude Code の作業偽装リスク) と `project_faultray_dev_policy.md` を参照。例外条件は CLAUDE.md の「FaultRay 開発の Devin 主軸ポリシー」セクション。

### 役割分担 (CRITICAL)

| 主体 | 担当 | 担当しないこと |
|------|------|---------------|
| **Claude Code (PM)** | 指示書設計、Devin プロンプト構築、コードレビュー (5次元)、技術質問の自律回答 (Read/Grep verbatim 添付必須)、ai-flow メタ作業 | FaultRay コード直接実装、UI 動作確認 |
| **Devin** | コード実装、テスト実行、UI 動作確認 (Browser操作)、Before/Afterスクリーンショット撮影、PR作成、PR body 整備 (verbatim/Read verification 含む) | 設計判断、ビジネス判断、レビュー (self-review はカウントしない) |
| **CodeRabbit** | 自動コードレビュー (independent AI レビュアー、必須通過) | 設計レビュー |
| **Claude Code (Reviewer モード)** | 5次元レビュー、Forbidden Phrases 検出、Read verification 確認、Devin self-review との重複排除 | コード書き換え |
| **人間 (Yutaro)** | 設計承認 (`/approve`)、ビジネス判断 (Slack)、最終マージボタン | コード書く、CI待ち、PRローカルチェックアウト (Devinがスクショ提供するため不要) |

### independent review の定義

**「Devin Review」 (= app/devin-ai-integration による review) は self-review として扱い、independent review にカウントしない**。これは2026-04-08 PR #29 の競争レビューで露呈した「AI self-approval ループ」問題への対処。

independent review として認めるのは以下のみ:
- `coderabbitai[bot]` の review
- 人間 (Yutaro) の review
- (将来的に) GitHub Copilot Workspace 等の third-party AI review

`pr-agent` (PR-Agent by qodo) は Devin と異なる組織だが、現状 ai-flow では「補助的レビュー」扱い (必須ではないがあれば加点)。

### マージ前の必須通過条件 (babysitter が物理ブロック)

- [x] CI all green (test 3.11/3.12/3.13, Security Scan, Detect Secrets, E2E, Docker, Performance)
- [x] CodeRabbit approved (`coderabbitai[bot]` reviews あり)
- [x] PR body に Forbidden Phrases なし (フックでも物理ブロック)
- [x] Read verification 出力が PR body に含まれる
- [x] UI 変更フラグ true の場合、Before/After スクリーンショット添付
- [x] Human Review Checklist 全項目チェック済み
- [x] cla-check SUCCESS

## 目的
要件定義→PR作成→マージまでを **人間介入3点のみ** で自動化する:
1. アーキテクチャ設計の承認
2. Devinからのビジネス判断質問への回答
3. 最終PRマージ判断 (Claude Code 5次元レビュー + CodeRabbit 自動レビュー両方OKが前提)

## システム構成

```
GitHub Issue (mattyopon/faultray)
   │ ai:review-req ラベル付与
   ▼
[/ai-flow:review-req <#>]   ← Claude Codeスラッシュコマンド
   │ レビューコメント、ラベル → ai:arch-design
   ▼
[/ai-flow:arch-design <#>]
   │ 設計コメント、🟡 HUMAN APPROVAL REQUIRED
   ▼
人間が `/approve` コメント
   │
   ▼
[/ai-flow:decompose <#>]
   │ 子Issue複数作成、ラベル → ai:spec
   ▼
[/ai-flow:spec <子#>]
   │ 仕様書コメント、ラベル → ai:devin-exec
   ▼
[/ai-flow:devin-exec <子#>]
   │ Devin API POST /v1/sessions
   │ session_id → /tmp/team-ai-flow/sessions.json
   ▼
[devin-babysitter] (cron */3 * * * *)
   │ Devin進捗監視、技術質問→自律回答、ビジネス質問→Slack
   │ PR完成 → ラベル ai:review、Slack通知
   ▼
人間レビュー → マージ
```

## ファイル配置

| パス | 用途 |
|------|------|
| `/home/user/.claude/commands/ai-flow/{review-req,arch-design,decompose,spec,devin-exec}.md` | スラッシュコマンド5本 |
| `/home/user/.claude/skills/devin-babysitter/SKILL.md` | babysitterスキル定義 |
| `/home/user/.claude/skills/devin-babysitter/run.sh` | cron wrapper (claude -p起動) |
| `/home/user/.devin-env` | DEVIN_API_KEY等 (chmod 600) |
| `/tmp/team-ai-flow/sessions.json` | アクティブDevin sessions の追跡 |
| `/tmp/team-ai-flow/babysitter.log` | babysitter実行ログ |
| `/tmp/team-ai-flow/decisions.log` | 全フェーズの決定履歴 (append-only) |
| `/tmp/team-ai-flow/intent-contract.md` | このワークフロー構築の不変契約 |

## babysitter 監視の2方式 (併用)

### 方式A: WSL crontab (永続バックグラウンド)

```cron
*/3 * * * * /home/user/.claude/skills/devin-babysitter/run.sh
```

- セッション0件時はclaudeを起動せず即終了 (コストゼロ)
- PCが起動している限り Claude Code セッションの状態に関係なく動く
- メリット: PC再起動後も自動復旧、Claude Codeを閉じても動く
- デメリット: 毎回新規 `claude --print` 起動、コンテキスト引き継ぎなし

### 方式B: `/loop` (Claude Code セッション内、記事と同方式)

Claude Code セッションがアクティブな間、以下を実行:

```
/loop 3m /devin-babysitter
```

- 同一 Claude Code セッション内で 3分間隔で babysitter スキルを起動
- メリット: コンテキスト引き継ぎ、起動オーバーヘッドなし、記事 (Zenn maya_honey) と同じ運用
- デメリット: Claude Code セッションを閉じると停止、PC再起動で要再設定

### 推奨: 併用

- **常時稼働**: 方式A (crontab) でフォールバック確保
- **アクティブ開発中**: 方式B (`/loop`) で高速応答
- 両方走っても run.sh のフロックロックで多重実行は防がれる (`/tmp/team-ai-flow/babysitter.lock`)
- 出典: https://zenn.dev/maya_honey/articles/3a459fc6c4b79f (記事は方式Bのみ)

## ラベル一覧 (mattyopon/faultray)

| ラベル | 意味 | 次フェーズ |
|--------|------|-----------|
| `ai:review-req` | 要件定義レビュー対象 | → ai:arch-design |
| `ai:arch-design` | アーキテクチャ設計対象 (人間承認待ち) | → ai:decompose (承認後) |
| `ai:decompose` | 親Issue→子Issue分解対象 | → ai:spec |
| `ai:spec` | 仕様書生成対象 | → ai:devin-exec |
| `ai:devin-exec` | Devin実装実行対象 | → ai:review (PR完成後) |

## 関連ドキュメント
- [devin-playbook-setup.md](./devin-playbook-setup.md) — Devin管理画面側の手動設定手順
- [human-approval-protocol.md](./human-approval-protocol.md) — 人間介入3点の判断ルール

## Ground Truth Principle
全コマンドは「実際に確認した事実のみを使う」を遵守。ファイルパスや関数名はRead/Grepで実在確認後にIssueに記載。Devin APIエンドポイントは https://docs.devin.ai/llms.txt で確認済 (2026-04-07)。
