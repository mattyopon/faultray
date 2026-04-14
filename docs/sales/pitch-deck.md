# FaultRay Pitch Deck — DORA対応インフラレジリエンス検証プラットフォーム

---

## 1. Executive Summary / エグゼクティブサマリー

### 日本語

FaultRayは、**本番環境に一切触れずに**インフラの構造的な可用性上限を宣言されたトポロジーからモデルベースで推定する、デプロイ前レジリエンス検証の研究プロトタイププラットフォームです。EU Digital Operational Resilience Act（DORA）が2025年1月17日に施行され、金融機関はICTリスク管理フレームワークの構築を義務付けられています。FaultRayは、DORAの要求するICTリスクシナリオテスト（第26条）とデジタルオペレーショナルレジリエンステスト（第24条〜第27条）の**事前準備・社内検討**を支援します。出力は研究プロトタイプによるエビデンスドラフトであり、規制監査向けの正式証跡ではありません（ランタイム・カオスエンジニアリングを補完する位置づけです）。

### English

FaultRay is a research-prototype pre-deployment resilience simulation platform that **estimates your infrastructure's structural availability ceiling from declared topology, without touching production**. With the EU Digital Operational Resilience Act (DORA) enforced since January 17, 2025, financial entities are required to build ICT risk management frameworks. FaultRay supports **pre-audit preparation** for the ICT risk scenario testing (Article 26) and digital operational resilience testing (Articles 24–27) mandated by DORA. Outputs are research-prototype evidence drafts for internal review — not a substitute for audit-certified compliance evidence. FaultRay complements runtime chaos engineering rather than replacing it.

---

## 2. The Problem / 課題

### 日本語

**従来のカオスエンジニアリングツール（Gremlin, Steadybit, AWS FIS）の問題:**

1. **本番リスク**: 実際の障害を注入するため、テスト中に本物のダウンタイムが発生するリスク
2. **高コスト**: ステージング環境の構築・維持に年間数百万円〜数千万円
3. **セットアップの複雑さ**: 導入に数日〜数週間、専門知識が必要
4. **DORAコンプライアンスの困難さ**: テスト結果が定性的で、監査証跡として不十分
5. **AI Agent時代の盲点**: LLMベースのAIエージェントの障害伝播を検証できない

### English

**Problems with traditional chaos engineering tools (Gremlin, Steadybit, AWS FIS):**

1. **Production risk**: Real fault injection creates actual downtime risk during testing
2. **High cost**: Staging environment setup and maintenance costs millions per year
3. **Complex setup**: Days to weeks of deployment, requires specialized expertise
4. **DORA compliance difficulty**: Qualitative test results insufficient as audit evidence
5. **AI Agent blind spot**: Cannot verify failure propagation in LLM-based AI agents

---

## 3. The Solution: FaultRay / ソリューション

### 日本語

FaultRayは**純粋な数学的シミュレーション**によるカオスエンジニアリングを提供します:

- **本番への障害注入なし**: シミュレーションのみ。宣言されたYAMLトポロジーファイルから実行
- **ゼロコスト環境**: ラップトップ上で実行可能。ステージング環境不要
- **5分で開始**: `pip install faultray` → YAML定義 → 即座に結果
- **数学的証明**: 3-Layer Availability Limit Model（特許出願済み）による可用性上限の定量的証明
- **150+シナリオ自動生成**: トポロジーから障害シナリオを自動生成
- **AI Agent対応**: LLM/AIエージェントの障害伝播シミュレーション

### English

FaultRay provides chaos engineering through **pure mathematical simulation**:

- **No production fault injection**: Simulation only — runs from declared YAML topology file
- **Zero cost infrastructure**: Runs on a laptop. No staging environment needed
- **5-minute setup**: `pip install faultray` → YAML definition → instant results
- **Mathematical proof**: Quantitative availability ceiling proof via 3-Layer Availability Limit Model (patent pending)
- **150+ auto-generated scenarios**: Automatically generates failure scenarios from topology
- **AI Agent support**: LLM/AI agent failure propagation simulation

---

## 4. DORA Compliance Mapping / DORAコンプライアンス対応

### 日本語

| DORA条文 | 要件 | FaultRayの対応 |
|---------|------|---------------|
| **第5条〜第14条** ICTリスク管理フレームワーク | ICTシステムの特定・保護・検出・対応・復旧 | トポロジー分析による全ICT資産の障害影響マッピング |
| **第24条** デジタルオペレーショナルレジリエンステストの一般要件 | リスクベースのテストプログラム確立 | 150+シナリオの自動生成、リスクスコアリング |
| **第25条** テストツール・システムの要件 | テストが事業運営を阻害しないこと | 本番への障害注入なし（シミュレーションのみ、本番影響なし） |
| **第26条** 高度なテスト: TLPT (Threat-Led Penetration Testing) | 脅威ベースの侵入テスト | カスケード障害シナリオ、依存関係障害チェーン分析 |
| **第27条** テスターの要件 | テスト結果の文書化と監査証跡 | HTML/PDFレポート自動生成、DORA準拠フォーマット |
| **第28条〜第30条** 第三者ICTリスク管理 | サードパーティプロバイダのリスク評価 | 外部依存関係の障害伝播シミュレーション |

### English

| DORA Article | Requirement | FaultRay Coverage |
|-------------|-------------|-------------------|
| **Articles 5–14** ICT Risk Management Framework | Identify, protect, detect, respond, recover ICT systems | Topology analysis mapping failure impact across all ICT assets |
| **Article 24** General Requirements for Resilience Testing | Establish risk-based testing programs | 150+ auto-generated scenarios, risk scoring |
| **Article 25** Testing Tools & Systems Requirements | Testing must not disrupt business operations | No production fault injection (simulation only, no production impact) |
| **Article 26** Advanced Testing: TLPT | Threat-led penetration testing | Cascading failure scenarios, dependency chain analysis |
| **Article 27** Tester Requirements | Documentation and audit trails of test results | Auto-generated HTML/PDF reports, DORA-compliant format |
| **Articles 28–30** Third-party ICT Risk Management | Risk assessment of third-party providers | External dependency failure propagation simulation |

---

## 5. ROI Calculation / ROI計算

### 日本語

#### 従来のカオスエンジニアリング（年間コスト）
| 項目 | コスト |
|-----|-------|
| ツールライセンス（Gremlin等） | $10,000〜$50,000 |
| ステージング環境（クラウド） | $24,000〜$120,000 |
| 専任エンジニア（セットアップ・運用） | $80,000〜$150,000 |
| テスト中のダウンタイムリスク | $10,000〜$500,000 |
| **合計** | **$124,000〜$820,000** |

#### FaultRay（年間コスト）
| プラン | コスト | 対象 |
|-------|-------|------|
| Pro | $3,588/年 ($299/月) | 中規模金融機関 |
| Business | $11,988/年 ($999/月) | 大規模金融機関 |

#### ROI
- **Pro**: 最大**97%のコスト削減**（$124,000 → $3,588）
- **Business**: 最大**99%のコスト削減**（$820,000 → $11,988）
- **追加価値**: DORA準拠レポート自動生成による監査対応工数の削減（推定80%削減）

### English

#### Traditional Chaos Engineering (Annual Cost)
| Item | Cost |
|------|------|
| Tool license (Gremlin, etc.) | $10,000–$50,000 |
| Staging environment (cloud) | $24,000–$120,000 |
| Dedicated engineer (setup & ops) | $80,000–$150,000 |
| Downtime risk during testing | $10,000–$500,000 |
| **Total** | **$124,000–$820,000** |

#### FaultRay (Annual Cost)
| Plan | Cost | Target |
|------|------|--------|
| Pro | $3,588/yr ($299/mo) | Mid-size financial institutions |
| Business | $11,988/yr ($999/mo) | Large financial institutions |

#### ROI
- **Pro**: Up to **97% cost reduction** ($124,000 → $3,588)
- **Business**: Up to **99% cost reduction** ($820,000 → $11,988)
- **Additional value**: DORA-compliant report auto-generation reduces audit preparation effort by an estimated 80%

---

## 6. Implementation Steps / 導入ステップ

### 日本語

| ステップ | 期間 | 内容 |
|---------|------|------|
| **1. PoC** | 1日 | `pip install faultray` → 既存インフラYAMLでデモ実行 |
| **2. トポロジー定義** | 1〜3日 | 既存インフラストラクチャのYAMLモデリング |
| **3. ベースライン測定** | 1日 | 現在の可用性上限を3-Layerモデルで算出 |
| **4. シナリオ実行** | 1日 | 150+シナリオの自動実行、脆弱ポイント特定 |
| **5. DORA対応レポート生成** | 即座 | 監査対応PDFレポートの自動生成 |
| **6. 改善サイクル** | 継続 | 指摘事項の改善 → 再測定 → レポート更新 |

**導入から初回レポート生成まで: 最短1日、通常1週間以内**

### English

| Step | Duration | Description |
|------|----------|-------------|
| **1. PoC** | 1 day | `pip install faultray` → Demo run with existing infra YAML |
| **2. Topology definition** | 1–3 days | YAML modeling of existing infrastructure |
| **3. Baseline measurement** | 1 day | Calculate current availability ceiling with 3-Layer model |
| **4. Scenario execution** | 1 day | Auto-execute 150+ scenarios, identify weak points |
| **5. DORA report generation** | Instant | Auto-generate audit-ready PDF reports |
| **6. Improvement cycle** | Ongoing | Fix findings → Re-measure → Update reports |

**From installation to first report: 1 day minimum, typically within 1 week**

---

## 7. Competitive Advantage / 競合優位性

### 日本語

| 機能 | FaultRay | Gremlin | Steadybit | AWS FIS |
|-----|---------|---------|-----------|---------|
| アプローチ | 数学的シミュレーション | 実障害注入 | 実障害注入 | 実障害注入 |
| 本番リスク | ゼロ | 高 | 中 | 高 |
| セットアップ時間 | 5分 | 数日 | 数時間 | 数時間 |
| 可用性の定量証明 | 3-Layer数学モデル | なし | なし | なし |
| AI Agent対応 | あり | なし | なし | なし |
| DORA準拠レポート | 自動生成 | 手動作成 | 部分的 | なし |
| 特許 | 出願済み | - | - | - |
| 初期コスト | $0 (Free tier) | $10,000+/年 | $5,000+/年 | 従量課金 |

### English

| Feature | FaultRay | Gremlin | Steadybit | AWS FIS |
|---------|---------|---------|-----------|---------|
| Approach | Mathematical simulation | Real fault injection | Real fault injection | Real fault injection |
| Production risk | Zero | High | Medium | High |
| Setup time | 5 minutes | Days | Hours | Hours |
| Quantitative availability proof | 3-Layer mathematical model | None | None | None |
| AI Agent support | Yes | No | No | No |
| DORA-compliant reports | Auto-generated | Manual | Partial | None |
| Patent | Filed | - | - | - |
| Starting cost | $0 (Free tier) | $10,000+/yr | $5,000+/yr | Pay per use |

---

## 8. About Us / 会社概要

- **Product**: FaultRay v11.0
- **License**: BSL 1.1 (Business Source License)
- **Patent**: USPTO provisional patent filed (March 2026)
- **Creator**: Yutaro Maeda
- **Contact**: hello@faultray.dev
- **Website**: https://faultray.dev
- **GitHub**: https://github.com/yutaro-and-and-and/faultray
