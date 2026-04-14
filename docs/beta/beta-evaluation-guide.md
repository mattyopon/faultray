# FaultRay βテスト評価ガイド

**金融機関向け — 限定配布（NDA締結済み機関のみ）**

> 本ガイドはFaultRay βテストの評価期間（30日間）を通じて参照するものです。
> ご不明な点は、下記サポート連絡先までお問い合わせください。

---

## 1. FaultRayの概要

### 1.1 ゼロリスクカオスエンジニアリングとは

FaultRayは、**本番環境を一切破壊しない**カオスエンジニアリングプラットフォームです。

従来のカオスエンジニアリング（Netflix Chaos Monkey等）では、実際に障害を注入するため本番環境へのリスクが伴います。FaultRayはこの問題を根本から解決します。

| 従来のカオスエンジニアリング | FaultRay |
|---|---|
| 本番環境に障害を注入 | 宣言されたインフラ構成をモデルベースでシミュレーション（研究プロトタイプ） |
| 本番障害リスクあり | 本番への障害注入なし（本番環境に一切触れない） |
| 実際の障害発生後に学習 | 障害発生前に弱点を発見 |
| 障害ログが監査証跡になりうる | クリーンな証跡でコンプライアンス対応 |

### 1.2 DORA全5柱への対応

FaultRayは欧州DORA規制（Digital Operational Resilience Act）の全5柱に対応します。

| DORA 柱 | 対応機能 |
|---|---|
| **ICTリスク管理** (Art. 5–16) | `faultray dora assess` — リスクスコアと弱点の可視化 |
| **ICTインシデント分類・報告** (Art. 17–23) | `faultray simulate` — インシデントシナリオのシミュレーションと影響評価 |
| **デジタル運用レジリエンステスト** (Art. 24–27) | `faultray dora evidence` — テスト証跡の自動生成 |
| **第三者リスク管理** (Art. 28–44) | 集中リスク分析、ベンダー依存度評価 |
| **情報・インテリジェンス共有** (Art. 45–46) | レポートエクスポート、GRCツール連携 |

### 1.3 金融機関でのユースケース

- **DORA Art. 24/25 準拠の証跡確保**: RTS（Regulatory Technical Standards）フォーマットでの出力
- **TLPT（Threat-Led Penetration Testing）事前準備**: 攻撃シナリオのシミュレーションで準備度を確認
- **BCP/DRP見直し**: 障害連鎖シミュレーションによるビジネス継続計画の妥当性検証
- **監査対応**: 規制当局への説明に耐えうる技術的証跡の自動生成

---

## 2. 評価期間

| 項目 | 内容 |
|---|---|
| **評価期間** | 30日間（βテスト開始日より起算） |
| **ライセンス形態** | NDA締結機関への限定配布（インターネット非公開） |
| **利用環境** | 評価機関の社内環境（インターネット接続不要・オンプレ対応） |
| **データ** | 本番データの使用は不要。サンプルインフラ定義ファイルで評価可能 |

---

## 3. 導入手順

### 3.1 前提条件

```
Python   : 3.10 以上
OS       : Linux (推奨) / macOS / Windows (WSL2)
メモリ  : 4GB 以上推奨
ネットワーク: インターネット接続不要（NDA配布版）
```

### 3.2 インストール

FaultRayはNDA締結後、開示者より提供されるプライベートインデックスからインストールします。

```bash
# NDA締結後に提供されるインストール手順（例）
pip install faultray --extra-index-url <NDA配布URLは別途ご連絡>

# インストール確認
faultray --version
```

### 3.3 初回動作確認

```bash
# デモモードで基本機能を確認（サンプルデータ使用）
faultray demo
```

デモが正常に完了すると、ターミナルにシミュレーション結果のサマリーと
レポートHTML（`faultray-demo-report.html`）が出力されます。

### 3.4 インフラYAML定義の作成

FaultRayはYAMLファイルでインフラ構成を定義します。本番環境に接続せず、構成情報を記述するだけで動作します。

```yaml
# infra-sample.yaml（記述例）
infrastructure:
  name: "基幹系システム（評価用）"
  components:
    - id: app-server-primary
      type: application_server
      tier: 1
      availability: 0.9999
      dependencies:
        - db-primary
        - cache-cluster

    - id: db-primary
      type: database
      tier: 2
      availability: 0.9995
      recovery_time_objective_minutes: 4
      dependencies:
        - db-replica

    - id: db-replica
      type: database
      tier: 3
      availability: 0.9990
      role: replica

    - id: cache-cluster
      type: cache
      tier: 2
      availability: 0.9998

  external_dependencies:
    - id: cloud-provider-a
      provider: "主要クラウドプロバイダー"
      criticality: high
```

詳細なYAML仕様は https://faultray.com/docs/infra-schema で参照できます。

---

## 4. 評価シナリオ（4週間プログラム）

### Week 1: 基本機能の確認

**目標**: FaultRayのコアシミュレーション機能を把握する。

#### Day 1–2: シミュレーション実行

```bash
# YAMLから基本シミュレーションを実行（JSON出力）
faultray simulate --model infra-sample.yaml --json

# HTMLレポートを生成
faultray simulate --model infra-sample.yaml --html week1-report.html

# エグゼクティブレポートを生成
faultray report executive infra-sample.yaml --output week1-exec-report.html
```

**確認ポイント**:
- [ ] 単一障害点（SPOF）が検出されているか
- [ ] 可用性スコア（Availability Score）が表示されているか
- [ ] 障害連鎖のカスケードパスが可視化されているか

#### Day 3–4: DORA初期評価

```bash
# DORA準拠の初期アセスメント（JSON出力）
faultray dora assess infra-sample.yaml --json

# スコアサマリーを画面に表示
faultray dora assess infra-sample.yaml
```

**確認ポイント**:
- [ ] DORA各柱のスコアが数値化されているか
- [ ] 改善推奨事項が具体的に提示されているか
- [ ] 優先度付きのアクションリストが出力されているか

#### Day 5: レポート品質の確認

```bash
# DORAコンプライアンスレポートをHTMLで出力
faultray dora report infra-sample.yaml --output week1-dora-report.html

# PDFで出力
faultray dora report infra-sample.yaml --output week1-dora-report.pdf --pdf
```

**確認ポイント**:
- [ ] PDFレポートが日本語で出力されているか
- [ ] 監査担当者・規制当局への説明に使えるレベルか

---

### Week 2: DORA準拠評価

**目標**: DORA規制要件への具体的な対応状況を評価する。

#### Day 8–10: 証跡自動生成

```bash
# DORA Art.24 に対応する証跡パッケージを生成
faultray dora evidence infra-sample.yaml \
  --output ./week2-evidence-art24/ \
  --framework article-24

# DORA Art.25 に対応する証跡パッケージを生成
faultray dora evidence infra-sample.yaml \
  --output ./week2-evidence-art25/ \
  --framework article-25

# DORA Art.28 に対応する証跡パッケージを生成
faultray dora evidence infra-sample.yaml \
  --output ./week2-evidence-art28/ \
  --framework article-28
```

**確認ポイント**:
- [ ] 証跡の内容がDORA条項の要件に対応しているか
- [ ] タイムスタンプと一意の証跡IDが付与されているか
- [ ] 改ざん防止のハッシュ値が含まれているか

#### Day 11–12: RTSフォーマットエクスポート

```bash
# DORA RTS（Regulatory Technical Standards）準拠フォーマットでエクスポート（JSON）
faultray dora rts-export infra-sample.yaml \
  --output ./week2-rts-export/

# CSV形式でエクスポート
faultray dora rts-export infra-sample.yaml \
  --output ./week2-rts-export-csv/ \
  --format csv
```

**確認ポイント**:
- [ ] RTS規定のXMLスキーマに準拠しているか
- [ ] 規制当局への提出フォーマットとして使用可能か
- [ ] 既存の規制報告ワークフローに組み込めるか

#### Day 13–14: Gap分析レポート

```bash
# 現状とDORA完全準拠のギャップを分析
faultray dora gap-analysis infra-sample.yaml --remediation
```

**確認ポイント**:
- [ ] ギャップが優先度順に整理されているか
- [ ] 各ギャップに対する改善提案が含まれているか

---

### Week 3: 高度機能の評価

**目標**: 金融機関特有の高度なユースケースを検証する。

#### Day 15–17: インシデントシミュレーション

```bash
# インフラモデルを指定してシミュレーション実行
faultray simulate --model infra-sample.yaml --json

# 動的タイムステップシミュレーション（障害連鎖の時間推移を確認）
faultray simulate --model infra-sample.yaml --dynamic --json

# HTMLレポートとして出力
faultray simulate --model infra-sample.yaml --html week3-incident-report.html
```

**確認ポイント**:
- [ ] 障害の連鎖伝播が正確にモデル化されているか
- [ ] RTO（目標復旧時間）とRPO（目標復旧時点）が評価されているか
- [ ] シナリオ結果が経営層向けサマリーとして出力できるか

#### Day 18–19: 集中リスク分析

```bash
# 第三者・クラウド集中リスクの評価（DORA Art.29）
faultray dora concentration-risk infra-sample.yaml

# JSON形式で出力
faultray dora concentration-risk infra-sample.yaml --json
```

**確認ポイント**:
- [ ] DORA Art.28（第三者リスク管理）の要件に対応しているか
- [ ] 特定ベンダーへの集中度が可視化されているか
- [ ] 代替策・分散策の提案が含まれているか

#### Day 20–21: TLPT準備度評価

```bash
# Threat-Led Penetration Testing 準備状況の評価（DORA Art.26）
faultray dora tlpt-readiness infra-sample.yaml

# JSON形式で出力
faultray dora tlpt-readiness infra-sample.yaml --json
```

**確認ポイント**:
- [ ] TLPTスコープ定義の支援ができるか
- [ ] クリティカルファンクションの特定が自動化されているか
- [ ] TIBER-EU/TIBER-JPフレームワークとの整合性があるか

---

### Week 4: 統合テスト

**目標**: 既存システム・ワークフローへの組み込み適性を検証する。

#### Day 22–24: CI/CD連携

```bash
# GitHub Actions / Jenkins等のCI/CDパイプラインへの組み込み
# （サンプルワークフローは https://faultray.com/docs/ci-cd で参照）

# CI/CDモードでの実行（JSON出力で結果をパース可能）
faultray simulate --model infra-sample.yaml --json

# ベースラインを保存して回帰検知
faultray simulate --model infra-sample.yaml --save-baseline baseline.json

# 前回ベースラインと比較
faultray simulate --model infra-sample.yaml --baseline baseline.json --json
```

**確認ポイント**:
- [ ] パイプラインへの組み込みが容易か
- [ ] 閾値を下回った場合にCIをFAILできるか
- [ ] レポートがCI成果物として自動保存できるか

#### Day 25–26: API利用

```bash
# REST APIの起動
faultray api serve --port 8080

# APIエンドポイントの確認
curl http://localhost:8080/api/v1/simulate \
  -X POST \
  -H "Content-Type: application/json" \
  -d @infra-sample.yaml
```

**確認ポイント**:
- [ ] 既存GRCツールとのAPI連携が可能か
- [ ] 認証・認可の仕組みが適切か
- [ ] APIレスポンスのレイテンシーが実用的か

#### Day 27–29: エンドツーエンド レポート出力

```bash
# 総合DORAコンプライアンスレポートを生成
faultray dora report infra-sample.yaml --output final-evaluation-report.html

# シミュレーション結果を含む完全なレポートを生成
faultray dora report infra-sample.yaml --output final-evaluation-report.html --simulate

# PDFで出力（監査担当者・規制当局向け）
faultray dora report infra-sample.yaml --output final-evaluation-report.pdf --pdf
```

#### Day 30: 評価完了・フィードバック提出

評価フォームに回答し、開示者に提出してください（第6章参照）。

---

## 5. 評価観点チェックリスト

評価期間中、以下の観点で継続的に評価してください。

### 5.1 既存GRCツールとの補完性

- [ ] 現在使用しているGRC/IRM（例: ServiceNow GRC, OpenPages, MEGA HOPEX）との重複はどの程度か
- [ ] FaultRayが提供する**シミュレーションベースの定量評価**は既存ツールにはない機能か
- [ ] データのインポート/エクスポートによる連携は実現可能か
- [ ] 既存レポーティングワークフローへの組み込みに追加開発は必要か

### 5.2 監査対応レポートの品質

- [ ] 内部監査部門が受け入れ可能な証跡品質か
- [ ] 外部監査法人（Big4等）への提示に耐えられるか
- [ ] 金融庁・日本銀行考査での活用可能性があるか
- [ ] DORA規制当局（EU圏の場合）への報告書として使用できるか
- [ ] レポートの日本語品質は十分か

### 5.3 導入の容易さ

- [ ] 情報システム部門の担当者が2時間以内に導入できるか
- [ ] 既存インフラの構成情報をYAMLに変換するコストは許容範囲か
- [ ] エージェントレス（本番サーバーへのインストール不要）であることを確認したか
- [ ] セキュリティ審査（ペネトレーション、コードレビュー）のハードルは許容範囲か
- [ ] オンプレミス完結で動作することを確認したか

### 5.4 DORA Art. 24/25/28の要件充足度

**Art. 24（高度テスト — TLPT）**
- [ ] TLPTのスコーピングを支援できるか
- [ ] テスト実施の証跡が適切に記録されるか
- [ ] 当局報告に必要な情報が網羅されているか

**Art. 25（テスト要件）**
- [ ] 年次のICTリスクアセスメントをFaultRayで代替または補完できるか
- [ ] テスト結果の経営陣への報告フォーマットが適切か
- [ ] 修復措置の追跡機能があるか

**Art. 28（第三者サービスプロバイダー管理）**
- [ ] クラウドプロバイダー集中リスクが定量化されているか
- [ ] 代替調達戦略の評価に使用できるか
- [ ] 重要ITSPのサブ委託リスクが分析できるか

### 5.5 総合評価軸

- [ ] 費用対効果（ROI）の見通しがあるか
- [ ] 競合製品（Gremlin、AWS FIS等）との差別化が明確か
- [ ] 3–5年後の継続利用が想定できる成熟度か

---

## 6. フィードバックフォーム

評価完了後（Day 30）に、以下10項目にご回答ください。
回答は前田（maeda@faultray.example）まで提出してください。

---

### FaultRay βテスト評価フィードバック

**機関名**: _______________________________________________

**評価担当者**: _______________________________________________

**評価期間**: _______________年_______________月_______________日 〜 _______________年_______________月_______________日

---

**Q1. FaultRayの全体的な満足度を教えてください。**

```
[ ] 5 — 非常に満足
[ ] 4 — 満足
[ ] 3 — 普通
[ ] 2 — やや不満
[ ] 1 — 不満
```

---

**Q2. DORA準拠評価機能の有用性を教えてください。**

```
[ ] 5 — 非常に有用（そのまま活用できる）
[ ] 4 — 有用（一部カスタマイズで活用できる）
[ ] 3 — 普通（補助ツールとして活用できる）
[ ] 2 — やや有用でない（大幅な改良が必要）
[ ] 1 — 有用でない
```

具体的なコメント:
```
_______________________________________________
_______________________________________________
```

---

**Q3. 監査対応レポートの品質を教えてください。**

```
[ ] 5 — そのまま監査対応に使用できる
[ ] 4 — 軽微な修正で使用できる
[ ] 3 — 参考資料として使用できる
[ ] 2 — 大幅な加工が必要
[ ] 1 — 使用できない
```

不足している情報・改善点（あれば）:
```
_______________________________________________
_______________________________________________
```

---

**Q4. 導入・セットアップの容易さを教えてください。**

```
[ ] 5 — 非常に容易（1時間以内に導入完了）
[ ] 4 — 容易（半日以内）
[ ] 3 — 普通（1日以内）
[ ] 2 — やや困難（数日必要）
[ ] 1 — 困難（1週間以上）
```

導入で困った点（あれば）:
```
_______________________________________________
```

---

**Q5. 既存システムとの統合容易さを教えてください。**

```
[ ] 5 — 既存GRC/CIツールとスムーズに連携できた
[ ] 4 — 一部設定で連携できた
[ ] 3 — API経由での連携は可能だが手間がかかる
[ ] 2 — 連携には開発工数が必要
[ ] 1 — 連携は困難
```

連携を試みたシステム・ツール名:
```
_______________________________________________
```

---

**Q6. FaultRayが解決する最も価値の高い課題を教えてください。（複数選択可）**

```
[ ] DORA準拠証跡の自動生成
[ ] 本番環境ゼロリスクでの障害シミュレーション
[ ] 第三者・クラウド集中リスクの可視化
[ ] TLPT準備支援
[ ] 障害連鎖（カスケード障害）の事前把握
[ ] 経営層向けレジリエンスレポートの作成
[ ] CI/CDパイプラインへのセキュリティゲート組み込み
[ ] その他: _______________________________________________
```

---

**Q7. 追加してほしい機能・改善してほしい点を教えてください。（優先度が高い順に3つまで）**

```
1. _______________________________________________
2. _______________________________________________
3. _______________________________________________
```

---

**Q8. 正式リリース後の導入を検討しますか？**

```
[ ] 5 — 強く検討する（予算確保も含め前向きに検討）
[ ] 4 — 検討する（社内検討プロセスに乗せる）
[ ] 3 — 条件次第で検討する（主な条件: ___________________________）
[ ] 2 — 現時点では難しい
[ ] 1 — 導入しない
```

---

**Q9. 競合他社製品と比較した場合のFaultRayの優位点・劣位点を教えてください。**

比較した製品（あれば）:
```
_______________________________________________
```

優位点:
```
_______________________________________________
```

劣位点:
```
_______________________________________________
```

---

**Q10. 今後の製品開発に向けて、自由にご意見・ご要望をお聞かせください。**

```
_______________________________________________
_______________________________________________
_______________________________________________
_______________________________________________
```

---

## 7. サポート体制

### 7.1 評価期間中の連絡先

| 種別 | 連絡先 |
|---|---|
| **技術的な質問・バグ報告** | maeda@faultray.example（前田雄太郎）|
| **DORA規制要件に関する相談** | maeda@faultray.example |
| **緊急の技術サポート（平日 9:00–18:00 JST）** | 別途NDA締結時に案内 |

### 7.2 週次ミーティング（推奨）

評価期間中、週1回（30分程度）のオンラインミーティングを設けることを推奨します。

| タイミング | 議題 |
|---|---|
| **Week 1終了後** | 基本機能への質問・疑問解消、Week 2計画の確認 |
| **Week 2終了後** | DORA機能評価の進捗、課題の共有 |
| **Week 3終了後** | 高度機能の評価結果、統合テスト方針の確認 |
| **Week 4終了（Day 30）** | フィードバック回答、今後の進め方の協議 |

ミーティング調整は `maeda@faultray.example` までご連絡ください。

### 7.3 ドキュメント・リソース

```bash
# CLIヘルプの確認
faultray --help
faultray simulate --help
faultray dora --help

# Webドキュメントの参照
# https://faultray.com/docs
# または以下で各コマンドのヘルプを参照:
# faultray --help
```

### 7.4 フィードバック提出期限

**評価開始日より30日以内**に、第6章のフィードバックフォームをご提出ください。

ご提出先: `maeda@faultray.example`
件名: `FaultRay βフィードバック — [機関名] — [評価完了日]`

---

*本ガイドはNDA締結済みの評価機関にのみ配布されます。無断転載・共有は禁止です。*

*このドキュメントはFaultRay βテスト v0.x 対応です。*
*最終更新: 2026-03-19*
