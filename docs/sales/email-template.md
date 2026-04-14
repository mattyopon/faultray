# FaultRay Cold Email Templates — 金融機関向け

---

## Template 1: 情報セキュリティ部門向け / For Information Security Departments

### 日本語

**件名**: DORA対応の事前レジリエンス評価 — 本番環境への障害注入なしで実現

---

{担当者名} 様

突然のご連絡失礼いたします。
FaultRayの前田と申します。

EU Digital Operational Resilience Act（DORA）が2025年1月に施行され、金融機関はICTシステムのデジタルオペレーショナルレジリエンステスト（第24条〜第27条）を定期的に実施する義務を負っています。

しかし、従来のカオスエンジニアリングツール（Gremlin, AWS FIS等）は**本番環境に実際の障害を注入する**ため、テスト自体がダウンタイムリスクとなるジレンマがありました。

**FaultRay**（研究プロトタイプ）は、このジレンマに対する**事前評価**アプローチを提供します:

- **本番への障害注入なし**: 宣言されたインフラ定義からモデルベースでシミュレーション。本番環境に一切触れません
- **DORA事前準備支援**: 第24条〜第27条が求めるテスト要件の**社内レビュー向けエビデンスドラフト**を自動生成（監査認証ではなく、独立した法務・技術レビューが必要です）
- **即座に開始**: YAMLでインフラ構成を定義するだけ。5分でセットアップ完了
- **定量的推定**: 可用性上限を3-Layer Availability Limit Model（特許出願済み）でモデルベース推定（精度はトポロジー定義の完全性に依存）

現在、30分のオンラインデモを無料で実施しております。
貴社のインフラ構成を元にした実際のシミュレーション結果をお見せいたします。

ご都合の良い日時をいくつかお知らせいただけますでしょうか。

何卒よろしくお願い申し上げます。

前田 悠太郎
FaultRay
hello@faultray.dev
https://faultray.dev

---

### English

**Subject**: DORA-Compliant ICT Resilience Testing — Zero Production Risk

---

Dear {Name},

I hope this message finds you well.
My name is Yutaro Maeda from FaultRay.

With the EU Digital Operational Resilience Act (DORA) enforced since January 2025, financial entities are required to conduct regular digital operational resilience testing of ICT systems (Articles 24–27).

However, traditional chaos engineering tools (Gremlin, AWS FIS, etc.) **inject real faults into production**, making the testing itself a downtime risk — a fundamental dilemma.

**FaultRay** solves this dilemma at its root:

- **Zero risk**: Pure mathematical simulation only. Never touches production
- **DORA-compliant**: Auto-generates reports meeting the testing requirements of Articles 24–27
- **Instant start**: Define your infrastructure in YAML. Setup in 5 minutes
- **Quantitative proof**: Calculates availability ceiling via the 3-Layer Availability Limit Model (patent pending)

We currently offer a complimentary 30-minute online demo where we can show you actual simulation results based on your infrastructure configuration.

Would you have any availability for a brief call this week or next?

Best regards,

Yutaro Maeda
FaultRay
hello@faultray.dev
https://faultray.dev

---

## Template 2: コンプライアンス部門向け / For Compliance Departments

### 日本語

**件名**: DORA第24条〜第27条のテスト要件 — 監査対応レポート自動生成ツール

---

{担当者名} 様

突然のご連絡失礼いたします。
FaultRayの前田と申します。

DORA（EU Digital Operational Resilience Act）の施行に伴い、貴社ではICTシステムのオペレーショナルレジリエンステストプログラムの整備を進められていることと存じます。

特に以下の条文への対応は、多くの金融機関が課題として挙げています:

- **第24条**: リスクベースのテストプログラムの確立
- **第25条**: テストが事業運営を阻害しないこと
- **第26条**: 高度なテスト（TLPT）の実施
- **第27条**: テスト結果の文書化と監査証跡

FaultRayは、これらの要件に対して以下の価値を提供します:

1. **監査証跡の自動生成**: テスト実行ごとに、DORA準拠フォーマットのPDF/HTMLレポートを自動出力
2. **リスクベースのテスト設計**: インフラトポロジーから150+のテストシナリオを自動生成し、リスクスコアを付与
3. **事業影響ゼロ**: シミュレーションベースのため、テスト実施による事業中断リスクが完全にゼロ
4. **定量的エビデンス**: 「可用性99.99%」といった定量的証明を規制当局に提示可能

30分のオンラインデモで、貴社のコンプライアンス要件に対するFaultRayの対応をご説明いたします。

ご検討のほど、よろしくお願い申し上げます。

前田 悠太郎
FaultRay
hello@faultray.dev
https://faultray.dev

---

### English

**Subject**: DORA Articles 24–27 Testing Requirements — Automated Audit-Ready Reports

---

Dear {Name},

I hope this message finds you well.
My name is Yutaro Maeda from FaultRay.

With the enforcement of DORA (EU Digital Operational Resilience Act), I understand your organization is working on establishing an ICT operational resilience testing program.

The following articles in particular are commonly cited as challenges by financial institutions:

- **Article 24**: Establishing risk-based testing programs
- **Article 25**: Ensuring testing does not disrupt business operations
- **Article 26**: Conducting advanced testing (TLPT)
- **Article 27**: Documentation and audit trails of test results

FaultRay delivers the following value against these requirements:

1. **Automated audit trails**: Auto-generates DORA-compliant PDF/HTML reports for each test run
2. **Risk-based test design**: Auto-generates 150+ test scenarios from infrastructure topology with risk scores
3. **Zero business impact**: Simulation-based approach means absolutely zero business disruption risk
4. **Quantitative evidence**: Present quantitative proof like "99.99% availability" to regulators

I would welcome the opportunity to demonstrate how FaultRay addresses your compliance requirements in a 30-minute online demo.

Thank you for your consideration.

Best regards,

Yutaro Maeda
FaultRay
hello@faultray.dev
https://faultray.dev

---

## Template 3: CTO/CIO向け（短縮版） / For CTO/CIO (Short Version)

### 日本語

**件名**: 可用性上限の数学的証明 — カオスエンジニアリングの新しいアプローチ

---

{役職名} {担当者名} 様

FaultRayの前田です。

**1行で**: 本番環境に触れずに宣言されたインフラ定義から可用性上限をモデルベースで推定する研究プロトタイプツールです（ランタイム・カオスエンジニアリングを補完）。

- 従来ツールとの違い: 実障害注入ではなく事前シミュレーション → 本番への障害注入なし
- DORA関連の研究プロトタイプ・エビデンスドラフト自動生成（監査認証ではありません）
- `pip install faultray` → 5分で動作
- 特許出願済みの3-Layer Availability Limit Model（モデルベース推定、精度はトポロジー定義に依存）

デモ: https://faultray.dev/demo

15分のオンラインデモをさせていただけませんか?

前田 悠太郎
hello@faultray.dev

---

### English

**Subject**: Pre-Deployment Resilience Simulation — A Research-Prototype Approach to Chaos Engineering

---

Dear {Name},

This is Yutaro Maeda from FaultRay.

**In one line**: A research-prototype tool that estimates your availability ceiling from declared topology, without touching production (complements runtime chaos engineering).

- Difference from traditional tools: pre-deployment model-based simulation instead of runtime fault injection → no production fault injection required
- Auto-generated DORA research-prototype evidence drafts (not audit-certified; independent legal review required)
- `pip install faultray` → Running in 5 minutes
- Patent-pending 3-Layer Availability Limit Model (model-based estimation; accuracy depends on topology fidelity)

Demo: https://faultray.dev/demo

Would you have 15 minutes for a quick online demo?

Best regards,
Yutaro Maeda
hello@faultray.dev
