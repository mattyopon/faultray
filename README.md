<p align="center">
  <h1 align="center">FaultRay</h1>
  <p align="center"><strong>Zero-Risk Chaos Engineering for Infrastructure & AI Agents</strong></p>
  <p align="center"><strong>インフラ & AIエージェントのためのゼロリスク・カオスエンジニアリング</strong></p>
</p>

<p align="center">
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.11+-blue.svg" alt="Python 3.11+"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-BSL%201.1-orange.svg" alt="License: BSL 1.1"></a>
  <a href="#"><img src="https://img.shields.io/badge/tests-19%2C757%20passed-brightgreen.svg" alt="Tests"></a>
  <a href="#"><img src="https://img.shields.io/badge/version-11.0.0-blue.svg" alt="Version"></a>
  <a href="Dockerfile"><img src="https://img.shields.io/badge/docker-ready-2496ED.svg" alt="Docker"></a>
  <a href="https://pypi.org/project/faultray/"><img src="https://img.shields.io/pypi/v/faultray" alt="PyPI"></a>
  <a href="https://pypi.org/project/faultray/"><img src="https://img.shields.io/pypi/dm/faultray" alt="Downloads"></a>
  <a href="https://github.com/mattyopon/faultray"><img src="https://img.shields.io/github/stars/mattyopon/faultray" alt="GitHub stars"></a>
</p>

---

# English

## What is FaultRay?

**FaultRay is a tool that tests whether your systems can survive failures — without actually breaking anything.**

Think of it like a flight simulator for your infrastructure. Pilots don't learn to handle engine failures by breaking real engines. They use simulators. FaultRay does the same thing for your servers, databases, load balancers, and even AI agents.

Traditional chaos engineering tools (like Gremlin or AWS FIS) literally break things in your production environment to see what happens. That's scary and risky. FaultRay takes a completely different approach: it builds a **mathematical model** of your entire system and simulates over **2,000 failure scenarios** entirely in memory. Nothing gets touched. Nothing breaks. You just get answers.

### What Can FaultRay Do?

#### 1. Find Your System's Weak Points — Before They Break

FaultRay automatically discovers single points of failure, cascade paths, and hidden dependencies in your infrastructure. You define your system in a simple YAML file (or import from Terraform/Prometheus), and FaultRay runs thousands of "what if" scenarios:

- What if your database goes down?
- What if traffic spikes 10x during a sale?
- What if two servers fail at the same time?
- What if a DDoS attack hits your load balancer?

```bash
pip install faultray
faultray demo
```

```
╭────────── FaultRay Chaos Simulation Report ──────────╮
│ Resilience Score: 36/100                             │
│ Scenarios tested: 2,000+                             │
│ Critical: 7  Warning: 66  Passed: 77                 │
╰──────────────────────────────────────────────────────╯
```

#### 2. Prove Your Availability Ceiling Mathematically

Ever wondered: "Can we actually achieve 99.99% uptime?" FaultRay answers this with its unique **3-Layer Availability Limit Model**:

```
Layer 3: Theoretical Limit   → 6.65 nines (99.99997%)  — Math says this is the max
Layer 2: Hardware Limit      → 5.91 nines (99.999%)    — Your hardware caps it here
Layer 1: Software Limit      → 4.00 nines (99.99%)     — Human error brings it here
```

If your SLO target is 99.99% but your architecture can only physically reach 99.95%, **no amount of engineering effort will close the gap** without architectural changes. FaultRay tells you this before you waste months trying.

#### 3. Simulate AI Agent Failures (v11.0 — NEW)

As AI agents become part of production systems, a new class of failures emerges. FaultRay is the **first chaos engineering tool** to model AI-specific failure modes:

| Failure Type | What It Means |
|---|---|
| **Hallucination** | Agent produces confident but wrong answers when its data source goes down |
| **Context Overflow** | Agent exceeds token limits and loses critical context |
| **LLM Rate Limiting** | API provider throttles your requests during peak load |
| **Token Exhaustion** | You run out of API budget mid-conversation |
| **Tool Failure** | External tools the agent depends on become unavailable |
| **Agent Loops** | Agent gets stuck in infinite retry cycles |
| **Prompt Injection** | Malicious input hijacks agent behavior |

```bash
faultray agent assess infra.yaml    # Check your AI system's risk level
faultray agent scenarios infra.yaml # See what could go wrong
faultray agent monitor infra.yaml   # Generate monitoring rules
```

#### 4. Five Simulation Engines Working Together

| Engine | What It Does | Example |
|---|---|---|
| **Cascade** | Traces how one failure spreads through your system | "If Redis dies, what else goes down?" |
| **Dynamic** | Simulates real traffic patterns over time | "What happens during a 24h diurnal cycle?" |
| **Ops** | Runs week-long operational simulations | "Will our SLOs hold over 7 days?" |
| **What-If** | Sweeps parameters to find breaking points | "At what MTTR do we violate our SLA?" |
| **Capacity** | Forecasts when you'll run out of resources | "When do we need to scale up?" |

#### 5. Enterprise-Ready Features

- **Terraform Integration** — Import directly from `tfstate`, analyze `tf plan` impact before apply
- **Prometheus Discovery** — Auto-discover your infrastructure from Prometheus targets
- **Security Feed** — Auto-generate chaos scenarios from real CVE/CISA/NVD advisories
- **Cost Impact Engine** — Quantify downtime costs, SLA penalties, and ROI of improvements
- **Compliance Engine** — SOC 2, ISO 27001, PCI DSS, DORA, HIPAA, GDPR gap analysis
- **Multi-Region DR** — Evaluate disaster recovery strategies, compare RTO/RPO across regions
- **Web Dashboard** — Interactive D3.js dependency graph + Grafana-style dashboard
- **CI/CD Integration** — GitHub Actions marketplace action for pre-deploy validation

---

### How Does FaultRay Compare?

| | **Gremlin** | **Steadybit** | **AWS FIS** | **FaultRay** |
|---|---|---|---|---|
| **Approach** | Breaks real things | Breaks real things | Breaks real things | Math simulation |
| **Risk to production** | Medium-High | Medium | Medium | **Zero** |
| **Setup** | Agent per host | Agent per host | AWS only | **`pip install faultray`** |
| **Scenarios** | You write them | You write them | AWS services only | **2,000+ auto-generated** |
| **Availability proof** | No | No | No | **3-Layer Limit Model** |
| **AI agent testing** | No | No | No | **7 agent-specific fault types** |
| **Cost** | $$$$ | $$$ | $$ | **Free / Open Source** |

---

### Quick Start

**Option 1: pip (recommended)**

```bash
pip install faultray
faultray demo              # Run a demo simulation
faultray demo --web        # With web dashboard at http://localhost:8000
```

**Option 2: Docker**

```bash
docker compose up web                          # Web dashboard
docker compose --profile demo up demo          # Demo mode
docker compose --profile cli run cli simulate  # CLI mode
```

**Option 3: From source**

```bash
git clone https://github.com/mattyopon/faultray.git
cd faultray
pip install -e .
faultray demo
```

### Define Your Infrastructure

```yaml
# infra.yaml
components:
  - id: nginx
    type: load_balancer
    port: 443
    replicas: 2

  - id: api
    type: app_server
    port: 8080
    replicas: 3

  - id: postgres
    type: database
    port: 5432
    replicas: 1   # <-- FaultRay will flag this as a single point of failure

dependencies:
  - source: nginx
    target: api
    type: requires
  - source: api
    target: postgres
    type: requires
```

```bash
faultray load infra.yaml
faultray simulate --html report.html   # Get a full HTML report
```

### CLI Reference

| Command | What It Does |
|---|---|
| `faultray demo` | Run a demo with sample infrastructure |
| `faultray load <yaml>` | Load your infrastructure definition |
| `faultray simulate` | Run 2,000+ chaos scenarios |
| `faultray dynamic <yaml>` | Time-stepped simulation with traffic patterns |
| `faultray ops-sim <yaml>` | Long-running (days/weeks) operational simulation |
| `faultray whatif <yaml>` | Parameter sweep analysis |
| `faultray capacity <yaml>` | Growth forecasting and capacity planning |
| `faultray agent assess <yaml>` | Assess AI agent deployment risk |
| `faultray agent scenarios <yaml>` | Generate agent-specific chaos scenarios |
| `faultray agent monitor <yaml>` | Generate monitoring rules for agents |
| `faultray tf-import` | Import from Terraform state |
| `faultray tf-plan <plan>` | Analyze Terraform plan impact |
| `faultray scan` | Discover local/Prometheus infrastructure |
| `faultray serve` | Launch the web dashboard |
| `faultray feed-update` | Fetch latest security news and generate scenarios |
| `faultray report` | Generate HTML report |

---

## Why FaultRay is a Big Deal

### The Problem With Traditional Chaos Engineering

Netflix invented chaos engineering in 2011 with Chaos Monkey — a tool that randomly kills production servers to test resilience. Since then, the industry has followed this pattern: **break things in production to see what happens.**

But this approach has serious problems:

1. **It's risky.** You're literally injecting faults into real systems. Things can go wrong.
2. **It's expensive.** You need agents on every host, complex setup, and enterprise licenses.
3. **It's limited.** You can only test scenarios you manually configure.
4. **It doesn't work for regulated industries.** Banks, healthcare, and government can't casually break production.
5. **It can't test AI agents.** Traditional fault injection doesn't model hallucinations or context overflow.

### FaultRay's Approach: Simulate, Don't Break

FaultRay represents a **paradigm shift** in chaos engineering. Instead of breaking things and hoping for the best, FaultRay builds a mathematical model of your system and exhaustively simulates every failure scenario.

This means:
- **Zero risk** — Nothing in production is touched. Ever.
- **Complete coverage** — 2,000+ scenarios tested automatically, including compound failures that would be too dangerous to test in production.
- **Mathematical proof** — The 3-Layer Availability Limit Model gives you a mathematical ceiling for your system's uptime. No other tool does this.
- **Instant setup** — One `pip install` and you're running. No agents, no sidecars, no infrastructure changes.

### The Future: Why This Matters Now

The chaos engineering market is projected to reach **$3.5 billion by 2030** (Mordor Intelligence, CAGR 8.28%). Several converging trends make FaultRay's approach increasingly relevant:

**1. AI Agents Are Becoming Infrastructure**

AI agents are moving from experimental tools to critical production components. When an AI agent handles customer support, processes financial transactions, or manages supply chains, its failures have real-world consequences. FaultRay is the **first tool** to simulate AI-specific failure modes like hallucination cascades, context overflow, and prompt injection — testing what happens when the LLM behind your agent goes down while the agent keeps serving (incorrect) responses.

**2. Regulation Is Driving Adoption**

The EU's **Digital Operational Resilience Act (DORA)**, effective January 2025, mandates resilience testing for financial institutions. The **EU AI Act** (fully enforced August 2026) requires algorithmic accountability for AI systems. These regulations create a **compliance-driven market** where organizations must prove their systems are resilient — and FaultRay's mathematical proofs and compliance engine (SOC 2, ISO 27001, PCI DSS, DORA, HIPAA, GDPR) are purpose-built for this.

**3. Shift-Left Resilience**

The industry is moving chaos engineering from post-deployment to **every stage of the software development lifecycle**. FaultRay's zero-risk approach is ideal for this: you can run simulations in CI/CD pipelines, during design reviews, or before Terraform apply — no production environment needed.

**4. Multi-Cloud Complexity**

89% of large enterprises run workloads across 2+ cloud providers, but most failure testing is designed for single vendors. FaultRay's vendor-agnostic simulation works across any infrastructure topology, making it uniquely suited for multi-cloud environments.

**5. Security Chaos Engineering**

Security chaos engineering is the fastest-growing sub-segment (CAGR 11.34%). FaultRay's security feed automatically generates chaos scenarios from real-world CVE/CISA advisories, bridging the gap between security intelligence and resilience testing.

### Where FaultRay Fits in the Market

| Use Case | Who Benefits | How FaultRay Helps |
|---|---|---|
| **Pre-deploy validation** | DevOps / SRE teams | Run simulations in CI/CD before every deploy |
| **Architecture review** | Platform engineers | Prove availability ceiling before building |
| **Compliance** | Finance, healthcare, government | Generate audit-ready resilience reports |
| **AI agent reliability** | AI/ML engineers | Test agent failure modes before production |
| **Capacity planning** | Infrastructure teams | Forecast resource exhaustion and scaling needs |
| **Incident prevention** | On-call engineers | Identify cascade paths before incidents happen |
| **Security posture** | Security teams | Test resilience against real-world threat scenarios |

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                      FaultRay                         │
├──────────┬──────────┬──────────┬──────────┬──────────┤
│ Cascade  │ Dynamic  │   Ops    │ What-If  │ Capacity │
│ Engine   │ Engine   │  Engine  │  Engine  │  Engine  │
├──────────┴──────────┴──────────┴──────────┴──────────┤
│            AI Agent Resilience Layer (v11)             │
├───────────────────────────────────────────────────────┤
│           Dependency Graph (NetworkX)                  │
├──────────┬──────────┬──────────┬─────────────────────┤
│   YAML   │Terraform │Prometheus│    Cloud APIs        │
│  Loader  │ Importer │Discovery │   (AWS/GCP)          │
└──────────┴──────────┴──────────┴─────────────────────┘
```

## Development

```bash
pip install -e ".[dev]"         # Install in dev mode
pytest tests/ -v                # Run 19,757 tests
ruff check src/ tests/          # Lint
docker build -t faultray:dev .  # Build Docker image
```

## Community

- [Contributing Guide](CONTRIBUTING.md)
- [Security Policy](SECURITY.md)
- [Code of Conduct](CODE_OF_CONDUCT.md)
- [Changelog](CHANGELOG.md)

## License

BSL 1.1 (Business Source License) — see [LICENSE](LICENSE). Converts to Apache 2.0 on 2030-03-17.

---

---

# 日本語

## FaultRay とは？

**FaultRay は、本番環境を一切壊さずに「システムが障害に耐えられるか」をテストするツールです。**

たとえるなら、インフラのための「フライトシミュレーター」です。パイロットはエンジン故障の対処法を、実際にエンジンを壊して学んだりしません。シミュレーターを使います。FaultRay も同じです。サーバー、データベース、ロードバランサー、そして AI エージェントまで、すべてをメモリ上で数学的にシミュレーションします。

従来のカオスエンジニアリングツール（Gremlin, AWS FIS など）は、**本番環境に実際に障害を注入**してシステムの挙動を確認します。これにはリスクが伴います。FaultRay はまったく異なるアプローチを取ります。システム全体の**数学モデル**を構築し、メモリ内で **2,000以上の障害シナリオ**をシミュレーションします。何も壊れません。答えだけが得られます。

### FaultRay にできること

#### 1. システムの弱点を、壊れる前に発見する

FaultRay は、単一障害点（SPOF）、障害の連鎖経路、隠れた依存関係を自動的に発見します。シンプルな YAML ファイルでシステムを定義（Terraform/Prometheus からのインポートも可能）するだけで、何千もの「もし〜が起きたら？」を検証します：

- データベースがダウンしたら？
- セール中にトラフィックが10倍に急増したら？
- 2台のサーバーが同時に故障したら？
- ロードバランサーに DDoS 攻撃が来たら？

```bash
pip install faultray
faultray demo
```

```
╭────────── FaultRay Chaos Simulation Report ──────────╮
│ Resilience Score: 36/100                             │
│ Scenarios tested: 2,000+                             │
│ Critical: 7  Warning: 66  Passed: 77                 │
╰──────────────────────────────────────────────────────╯
```

#### 2. 可用性の上限を数学的に証明する

「本当に 99.99% のアップタイムを達成できるのか？」と思ったことはありませんか？FaultRay は独自の **3層可用性限界モデル** でこの問いに答えます：

```
Layer 3: 理論限界      → 6.65 nines (99.99997%)  — 数学的にこれが最大値
Layer 2: ハードウェア限界 → 5.91 nines (99.999%)  — ハードウェアの物理的限界
Layer 1: ソフトウェア限界 → 4.00 nines (99.99%)   — 人為的ミスを含む現実的な限界
```

SLO 目標が 99.99% でも、アーキテクチャの限界が 99.95% なら、**どれだけエンジニアリング努力を重ねてもアーキテクチャ変更なしにギャップは埋まりません**。FaultRay は、数ヶ月の無駄な努力の前にそれを教えてくれます。

#### 3. AIエージェントの障害をシミュレーション（v11.0 — 最新機能）

AI エージェントが本番システムの一部になるにつれ、新しい種類の障害が生まれています。FaultRay は AI 固有の障害モードをモデル化する**世界初のカオスエンジニアリングツール**です：

| 障害タイプ | どういうことか |
|---|---|
| **ハルシネーション** | データソースがダウンした時、エージェントが自信満々に誤った回答を返す |
| **コンテキストオーバーフロー** | トークン上限を超え、重要なコンテキストを失う |
| **LLMレート制限** | ピーク時にAPIプロバイダーがリクエストを制限する |
| **トークン枯渇** | 会話の途中でAPI予算が尽きる |
| **ツール障害** | エージェントが依存する外部ツールが利用不能になる |
| **エージェントループ** | 無限リトライのサイクルに陥る |
| **プロンプトインジェクション** | 悪意のある入力がエージェントの挙動を乗っ取る |

```bash
faultray agent assess infra.yaml    # AIシステムのリスクレベルを確認
faultray agent scenarios infra.yaml # 何が起こりうるかを確認
faultray agent monitor infra.yaml   # モニタリングルールを生成
```

#### 4. 5つのシミュレーションエンジンが連携

| エンジン | 何をするか | 例 |
|---|---|---|
| **カスケード** | 1つの障害がシステム全体にどう伝搬するかを追跡 | 「Redisが死んだら、他に何が落ちる？」 |
| **ダイナミック** | 実際のトラフィックパターンを時系列でシミュレーション | 「24時間の日周パターンで何が起きる？」 |
| **Ops** | 数日〜数週間の運用シミュレーション | 「7日間でSLOを維持できるか？」 |
| **What-If** | パラメータを変えて限界点を発見 | 「MTTRがどこまで伸びたらSLA違反になる？」 |
| **キャパシティ** | リソース枯渇のタイミングを予測 | 「スケールアップはいつ必要？」 |

#### 5. エンタープライズ対応の機能

- **Terraform 統合** — `tfstate` から直接インポート、`tf plan` の影響を事前分析
- **Prometheus 連携** — Prometheus のターゲットからインフラを自動検出
- **セキュリティフィード** — CVE/CISA/NVD の実際の脆弱性情報からシナリオを自動生成
- **コスト影響エンジン** — ダウンタイムコスト、SLA ペナルティ、改善の ROI を定量化
- **コンプライアンスエンジン** — SOC 2, ISO 27001, PCI DSS, DORA, HIPAA, GDPR のギャップ分析
- **マルチリージョン DR** — DR 戦略の評価、リージョン間の RTO/RPO 比較
- **Web ダッシュボード** — D3.js インタラクティブグラフ + Grafana スタイルのダッシュボード
- **CI/CD 統合** — GitHub Actions マーケットプレイスアクションでデプロイ前検証

---

### 他のツールとの比較

| | **Gremlin** | **Steadybit** | **AWS FIS** | **FaultRay** |
|---|---|---|---|---|
| **アプローチ** | 本番を壊す | 本番を壊す | 本番を壊す | 数学的シミュレーション |
| **本番リスク** | 中〜高 | 中 | 中 | **ゼロ** |
| **セットアップ** | ホスト毎にエージェント | ホスト毎にエージェント | AWS のみ | **`pip install faultray`** |
| **シナリオ** | 手動で作成 | 手動で作成 | AWS サービスのみ | **2,000+ 自動生成** |
| **可用性の証明** | できない | できない | できない | **3層限界モデル** |
| **AIエージェントテスト** | できない | できない | できない | **7種のエージェント障害** |
| **コスト** | $$$$ | $$$ | $$ | **無料 / オープンソース** |

---

### クイックスタート

**方法1: pip（おすすめ）**

```bash
pip install faultray
faultray demo              # デモシミュレーションを実行
faultray demo --web        # Web ダッシュボード付き (http://localhost:8000)
```

**方法2: Docker**

```bash
docker compose up web                          # Web ダッシュボード
docker compose --profile demo up demo          # デモモード
docker compose --profile cli run cli simulate  # CLI モード
```

**方法3: ソースから**

```bash
git clone https://github.com/mattyopon/faultray.git
cd faultray
pip install -e .
faultray demo
```

### インフラの定義

```yaml
# infra.yaml
components:
  - id: nginx
    type: load_balancer
    port: 443
    replicas: 2

  - id: api
    type: app_server
    port: 8080
    replicas: 3

  - id: postgres
    type: database
    port: 5432
    replicas: 1   # <-- FaultRay はこれを単一障害点として警告します

dependencies:
  - source: nginx
    target: api
    type: requires
  - source: api
    target: postgres
    type: requires
```

```bash
faultray load infra.yaml
faultray simulate --html report.html   # HTML レポートを生成
```

### コマンド一覧

| コマンド | 説明 |
|---|---|
| `faultray demo` | サンプルインフラでデモ実行 |
| `faultray load <yaml>` | インフラ定義を読み込み |
| `faultray simulate` | 2,000+ のカオスシナリオを実行 |
| `faultray dynamic <yaml>` | トラフィックパターン付き時間ステップシミュレーション |
| `faultray ops-sim <yaml>` | 長期間（数日〜数週間）の運用シミュレーション |
| `faultray whatif <yaml>` | パラメータスイープ分析 |
| `faultray capacity <yaml>` | 成長予測とキャパシティプランニング |
| `faultray agent assess <yaml>` | AI エージェントのデプロイリスク評価 |
| `faultray agent scenarios <yaml>` | エージェント固有のカオスシナリオ生成 |
| `faultray agent monitor <yaml>` | エージェント監視ルールの生成 |
| `faultray tf-import` | Terraform ステートからインポート |
| `faultray tf-plan <plan>` | Terraform プランの影響分析 |
| `faultray scan` | ローカル/Prometheus インフラの検出 |
| `faultray serve` | Web ダッシュボードを起動 |
| `faultray feed-update` | セキュリティニュースからシナリオを生成 |
| `faultray report` | HTML レポートを生成 |

---

## なぜ FaultRay はすごいのか

### 従来のカオスエンジニアリングの問題点

Netflix は 2011 年に Chaos Monkey を発明しました。本番サーバーをランダムに停止させてレジリエンスをテストするツールです。以来、業界はこのパターンに従ってきました：**本番を壊して何が起きるか見る**。

しかし、このアプローチには深刻な問題があります：

1. **リスクがある。** 実際のシステムに障害を注入するため、予期せぬ事態が起きうる。
2. **コストが高い。** ホスト毎にエージェントが必要で、セットアップが複雑、エンタープライズライセンスも高額。
3. **網羅性が低い。** 手動で設定したシナリオしかテストできない。
4. **規制産業で使えない。** 銀行、医療、政府機関は本番を気軽に壊せない。
5. **AIエージェントに対応できない。** 従来の障害注入ではハルシネーションやコンテキストオーバーフローをモデル化できない。

### FaultRay のアプローチ：壊すのではなく、シミュレーションする

FaultRay はカオスエンジニアリングにおける**パラダイムシフト**です。壊して結果を祈るのではなく、システムの数学モデルを構築し、あらゆる障害シナリオを網羅的にシミュレーションします。

これにより：
- **ゼロリスク** — 本番環境には一切触れません
- **完全な網羅性** — 2,000 以上のシナリオを自動テスト。本番では危険すぎる複合障害も含む
- **数学的な証明** — 3層可用性限界モデルでシステムのアップタイムの数学的上限を算出。他のツールにはこの機能はない
- **即座にセットアップ** — `pip install` 一発で実行可能。エージェント不要、サイドカー不要、インフラ変更不要

---

## 今後の市場と FaultRay の役割

カオスエンジニアリング市場は **2030年に35億ドル規模**に成長すると予測されています（Mordor Intelligence, CAGR 8.28%）。いくつかの大きなトレンドが、FaultRay のアプローチをますます重要にしています。

### 1. AIエージェントがインフラの一部になる時代

AI エージェントは実験的なツールから、**本番の重要コンポーネント**へと移行しています。カスタマーサポート、金融取引処理、サプライチェーン管理 — AI エージェントの障害は現実世界に影響を与えます。

FaultRay は、ハルシネーションの連鎖、コンテキストオーバーフロー、プロンプトインジェクションといった **AI固有の障害モード**をシミュレーションできる**世界初のツール**です。LLM がダウンしてもエージェントが（誤った）応答を返し続ける — そんなシナリオをテストできます。

### 2. 規制がレジリエンステストを義務化している

- **EU DORA**（2025年1月施行）: 金融機関にレジリエンステストを義務化
- **EU AI Act**（2026年8月完全施行）: AI システムにアルゴリズムの説明責任を要求
- **Colorado AI Act**: AI の公平性と安全性のテストを義務化

FaultRay のコンプライアンスエンジン（SOC 2, ISO 27001, PCI DSS, DORA, HIPAA, GDPR 対応）と数学的な証明は、これらの**規制要件に応えるために設計**されています。

### 3. 「シフトレフト」レジリエンス

業界はカオスエンジニアリングを、デプロイ後の活動から**ソフトウェア開発ライフサイクル全体**へと移行させています。FaultRay のゼロリスクアプローチはこれに最適です。CI/CD パイプラインで、設計レビューで、Terraform apply の前に — 本番環境なしでシミュレーションを実行できます。

### 4. マルチクラウドの複雑さ

大企業の89%が2つ以上のクラウドプロバイダーでワークロードを運用していますが、ほとんどの障害テストは単一ベンダー向けに設計されています。FaultRay のベンダー非依存のシミュレーションは、あらゆるインフラトポロジーで動作します。

### 5. セキュリティカオスエンジニアリング

セキュリティカオスエンジニアリングは最も急成長しているサブセグメント（CAGR 11.34%）です。FaultRay のセキュリティフィードは、CVE/CISA の脆弱性情報からカオスシナリオを自動生成し、セキュリティインテリジェンスとレジリエンステストを橋渡しします。

### FaultRay の市場ポジション

| ユースケース | 対象ユーザー | FaultRay の貢献 |
|---|---|---|
| **デプロイ前検証** | DevOps / SRE チーム | CI/CD でデプロイ毎にシミュレーション実行 |
| **アーキテクチャレビュー** | プラットフォームエンジニア | 構築前に可用性の上限を証明 |
| **コンプライアンス** | 金融・医療・政府機関 | 監査対応のレジリエンスレポートを生成 |
| **AIエージェントの信頼性** | AI/ML エンジニア | 本番投入前にエージェントの障害モードをテスト |
| **キャパシティプランニング** | インフラチーム | リソース枯渇とスケーリングのタイミングを予測 |
| **インシデント予防** | オンコールエンジニア | インシデント発生前にカスケードパスを特定 |
| **セキュリティ態勢** | セキュリティチーム | 実際の脅威シナリオに対するレジリエンスをテスト |

---

## アーキテクチャ

```
┌──────────────────────────────────────────────────────┐
│                      FaultRay                         │
├──────────┬──────────┬──────────┬──────────┬──────────┤
│ Cascade  │ Dynamic  │   Ops    │ What-If  │ Capacity │
│ Engine   │ Engine   │  Engine  │  Engine  │  Engine  │
├──────────┴──────────┴──────────┴──────────┴──────────┤
│           AI Agent Resilience Layer (v11)              │
├───────────────────────────────────────────────────────┤
│            Dependency Graph (NetworkX)                  │
├──────────┬──────────┬──────────┬─────────────────────┤
│   YAML   │Terraform │Prometheus│    Cloud APIs        │
│  Loader  │ Importer │Discovery │   (AWS/GCP)          │
└──────────┴──────────┴──────────┴─────────────────────┘
```

## 開発

```bash
pip install -e ".[dev]"         # 開発モードでインストール
pytest tests/ -v                # 19,757 テストを実行
ruff check src/ tests/          # リント
docker build -t faultray:dev .  # Docker イメージをビルド
```

## コミュニティ

- [Contributing Guide](CONTRIBUTING.md) — 貢献ガイド
- [Security Policy](SECURITY.md) — 脆弱性報告ポリシー
- [Code of Conduct](CODE_OF_CONDUCT.md) — 行動規範
- [Changelog](CHANGELOG.md) — 変更履歴

## ライセンス

BSL 1.1 (Business Source License) — [LICENSE](LICENSE) を参照。2030-03-17 に Apache 2.0 へ移行。
