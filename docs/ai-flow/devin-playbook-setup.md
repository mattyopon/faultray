# Devin Playbook 設定手順 (手動)

ai-flowワークフローはClaude Code側で大半が自動化されているが、Devin側にも以下のPlaybookを設定しておくとDevinがGitHub Issueの仕様書を正確に解釈する。**この設定はDevin管理画面で人間が手動で行う必要がある** (Devin APIにはPlaybook作成エンドポイントがない、2026-04-07時点)。

## 前提
- Devin Org: `org-f889e8855a3f41b684e28a234acf1b5d`
- Repo: mattyopon/faultray を Devin Knowledge に登録済みであること
- Slack連携: `#devin-faultray` (Webhook URL は env DEVIN_SLACK_WEBHOOK)

## Playbook 1: spec_to_pr (FaultRay用)

### Trigger
- 起動方法: API (`POST /v1/sessions` から呼ばれる)
- 入力: `/ai-flow:devin-exec` が生成したプロンプト (verbatim検証要求 + Hard limits + Pre-flight実測値を含む)

### Behavior
1. プロンプト内の `Hard limits` セクションを最優先で守る
   - ACU上限を超えそうなら即停止
   - "Touch only these N files" 以外は触らない
   - "Do NOT use Deep Mode"
2. プロンプト内の `Background (already verified by the requester)` の数値を信頼し、二重実測しない
3. `Required changes` の通りにコードを書く
4. `Verification` セクションのコマンドを **完全 verbatim** で実行
5. PR body に検証結果を verbatim で貼り付ける (省略禁止)
6. 詰まったら GitHub Issue にコメントで質問する (`gh issue comment` 経由) — babysitter が3分以内に拾う

### Forbidden
- `--no-verify` で hook を skip
- テストファイルの runtime behavior 変更
- "おそらく" "たぶん" "推定" 等の曖昧表現
- 数値の paraphrase ("33049 passed" を "約33000 passed" にする等)

### Stop conditions
- ACU が上限の80%に達したら一旦停止し、現状を Issue にコメント
- 検証コマンドが新規 failure を出したら **push しない**、Issue に報告

## Playbook 2: question_handling

Devinが質問を投げるとき、以下のフォーマットで Issue にコメント:

```
@babysitter QUESTION (TECHNICAL|BUSINESS)

Context: <何を読んだ・何を試した>
Question: <具体的な質問>
Blocking: <この質問が解決しないと先に進めないか YES/NO>
```

`@babysitter` プレフィックスがあると babysitter が拾える。`TECHNICAL` か `BUSINESS` のヒントがあると分類精度が上がる。

## Playbook 3: human_escalation

ビジネス判断が必要な場合 Devin から直接 Slack に通知してもよい:
```
[Devin → human] Issue #<id>: <question>
Decision needed: <choice A vs B>
```

## 設定方法

1. Devin管理画面 → Settings → Playbooks
2. 「New Playbook」 → 上記3つを順番に作成
3. 各PlaybookはMarkdown形式でDevinに教える (Devinの内部知識として参照される)
4. Save & Apply to Org

## 動作確認
1. Claude Code で `/ai-flow:devin-exec mattyopon/faultray#<test>` を実行
2. Devin session が起動するのを確認
3. babysitter ログ (`tail -f /tmp/team-ai-flow/babysitter.log`) で監視
4. PR が作成されるか確認

## トラブルシューティング

| 症状 | 原因 | 対処 |
|------|------|------|
| Devin が verbatim を省略する | Playbook 1 が設定されていない | Playbook 1 を有効化 |
| babysitter が質問を拾わない | `@babysitter` プレフィックスがない | Playbook 2 を強化 |
| ACU 上限 3 を超える | 仕様が複雑すぎる | `/ai-flow:decompose` で再分解 |
