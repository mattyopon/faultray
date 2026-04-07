# 人間介入プロトコル (3つの判断ポイント)

ai-flow ワークフローで人間が介入するのは以下の3点のみ。それ以外は全て自動進行する。

## 介入1: アーキテクチャ設計の承認

**いつ**: `/ai-flow:arch-design` 完了時、Issue に "🟡 HUMAN APPROVAL REQUIRED" コメントが付く
**通知**: Slack `#devin-faultray` に「arch-design 完了: <URL>」

### レビューポイント
1. 推薦案が要件を満たしているか
2. 既存FaultRayアーキテクチャ (14レイヤーテスト体系等) と整合しているか
3. 影響範囲・リスクが許容できるか
4. 不採用案の却下理由が妥当か

### 承認方法
Issue に以下のコメントを書く:
```
/approve
```

### 修正依頼
```
/revise
- <修正点1>
- <修正点2>
```
→ `/ai-flow:arch-design` を再実行

### 中止
```
/cancel
理由: <...>
```

## 介入2: Devinからのビジネス判断

**いつ**: babysitter が Devin の質問を BUSINESS に分類した時
**通知**: Slack に `⚠️ Devin requires BUSINESS decision` が来る

### 判断ポイント
- 仕様の選択 (A or B どちらの挙動を採用するか)
- 優先度 (P0/P1/P2)
- UX の選択
- 法務・コンプライアンス
- 価格・課金

### 回答方法
GitHub Issue に Devin への返信としてコメント:
```
@devin DECISION: <選択肢>
理由: <...>
影響範囲: <...>
```

babysitter が次の3分サイクルで Devin に転送する。

### 緊急時
直接 Devin Web UI から session を開いて回答してもよい (babysitterが事後的にIssueを更新)。

## 介入3: 最終PRレビュー・マージ

**いつ**: Devin が PR を作成し babysitter がラベルを `ai:review` に切り替えた時
**通知**: Slack に `✅ Devin completed: <PR URL> — ready for human review`

### レビューポイント (CodeRabbitと併用)
1. CodeRabbit のレビューが通っているか (feedback_coderabbit_review)
2. PR body の verbatim 検証出力が正しいか (feedback_devin_verbatim)
3. CIが green か (FaultRay の14レイヤーテスト)
4. ACU超過や Hard limits 違反がないか
5. 5次元レビュー (辛口/根本原因/矛盾/要否/メタ認知)

### マージ
通常のGitHub PRマージ。マージ後、子Issue は自動 close される (`Closes #<id>` がPR bodyにあれば)。

### 修正依頼
PR にコメントで指示。Devin が同じ session を再開して修正する (babysitter が3分以内に検出して Devin に転送)。

### 却下
PR を close。Issue に却下理由を書く。Issue ラベルを `ai:devin-exec` に戻し、必要なら再実行。

## 介入しない (自動進行する) 例

- 要件定義のレビュー (`/ai-flow:review-req` が自動でCRITICAL/MAJOR/MINORを指摘)
- 子Issueの分解 (`/ai-flow:decompose` が自動)
- 仕様書生成 (`/ai-flow:spec` が自動)
- Devin の技術的質問への回答 (babysitter が grep/read で自律解決)
- ファイルパス・関数シグネチャ等の機械的確認

## エスカレーション基準 (CLAUDE.md準拠)

以下に該当したら自動的に Slack で人間に escalate:
- 修正ループ3回転超過
- Intent Contract の変更が必要
- 設計に根本的な欠陥
- CRITICAL セキュリティ問題
- 全実験ブランチのテスト通過率80%未満
- 外部サービスの仕様が不明
