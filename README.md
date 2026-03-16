# FaultRay — Zero-Risk Infrastructure Chaos Simulation

> **Simulate infrastructure failures without touching production.**
> **Prove your system's availability ceiling mathematically.**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-19%2C757%20passed-brightgreen.svg)]()
[![Version](https://img.shields.io/badge/version-10.1.0-blue.svg)]()
[![Docker](https://img.shields.io/badge/docker-ready-2496ED.svg)](Dockerfile)
[![PyPI](https://img.shields.io/pypi/v/faultray)](https://pypi.org/project/faultray/)
[![Downloads](https://img.shields.io/pypi/dm/faultray)](https://pypi.org/project/faultray/)
[![GitHub stars](https://img.shields.io/github/stars/mattyopon/faultray)](https://github.com/mattyopon/faultray)

---

## Why FaultRay?

Most chaos engineering tools inject real faults into real infrastructure. FaultRay takes a fundamentally different approach: **pure mathematical simulation** that models your entire dependency graph in memory, runs 2,000+ failure scenarios across 5 engines, and proves your system's theoretical availability ceiling — all without touching a single server.

| | **Gremlin** | **Steadybit** | **AWS FIS** | **FaultRay** |
|---|---|---|---|---|
| **Approach** | Fault injection | Fault injection | Fault injection | Mathematical simulation |
| **Risk to production** | Medium-High | Medium | Medium | **Zero** |
| **Setup required** | Agent per host | Agent per host | AWS-only | **Single pip install** |
| **Scenario count** | Manual config | Manual config | AWS services only | **2,000+ auto-generated** |
| **Availability proof** | No | No | No | **3-Layer Limit Model** |
| **Cost** | $$$$ | $$$ | $$ (AWS-only) | **Free / OSS** |
| **Dependency graph** | No | Limited | No | **Full NetworkX graph** |
| **Terraform integration** | No | No | Native | **tfstate + plan analysis** |
| **Security feed** | No | No | No | **Auto CVE scenarios** |

**Key differentiators:**

- **Zero risk** — Runs entirely in memory. No agents, no sidecars, no production impact.
- **5 simulation engines** — Cascade, Dynamic, Ops, What-If, and Capacity engines working together.
- **3-Layer Availability Limit Model** — The only tool that mathematically proves your system's availability ceiling (see below).
- **HA & Quorum Guards** — Capacity Engine enforces minimum 2 replicas for HA components and minimum 3 for quorum-based clusters (Redis, Kafka).

---

## Quick Start

### pip

```bash
# Install from PyPI
pip install faultray

# Or install from source
pip install -e .

# Run demo (6-component web stack simulation)
faultray demo

# With web dashboard
faultray demo --web
```

### Docker

```bash
# Web dashboard (http://localhost:8000)
docker compose up web

# Demo mode with dashboard
docker compose --profile demo up demo

# CLI mode
docker compose --profile cli run cli simulate

# Build from source
docker build -t faultray .
docker run -p 8000:8000 faultray
```

### Demo Output

```
╭────────── FaultRay Chaos Simulation Report ──────────╮
│ Resilience Score: 36/100                             │
│ Scenarios tested: 2,000+                             │
│ Critical: 7  Warning: 66  Passed: 77                 │
╰──────────────────────────────────────────────────────╯

CRITICAL FINDINGS

  10.0/10 CRITICAL  Traffic spike (10x)
  Cascade path:
  ├── DOWN nginx (LB)
  ├── DOWN api-server-1
  ├── DOWN api-server-2
  ├── DOWN PostgreSQL (primary)
  ├── DOWN Redis (cache)
  └── DOWN RabbitMQ
```

---

## Features

| | Feature | Description |
|---|---|---|
| :shield: | **Zero Risk Simulation** | Runs entirely in memory — no agents, no sidecars, no production impact |
| :chart_with_upwards_trend: | **2,000+ Chaos Scenarios** | 30 categories of failure scenarios auto-generated from your topology |
| :link: | **Dependency Graph Analysis** | NetworkX-powered graph modeling with cascade fault prediction |
| :triangular_ruler: | **3-Layer Availability Proof** | Mathematically proves your system's theoretical availability ceiling |
| :dart: | **SLO/SLI Tracking** | Availability, latency, and error rate tracking against SLO targets |
| :crystal_ball: | **What-If Analysis** | Parameter sweep for fault tolerance sensitivity analysis |
| :bar_chart: | **Capacity Planning** | Growth forecasting with SLO compliance evaluation |
| :ocean: | **10 Traffic Models** | DDoS, diurnal, flash crowd, growth trend, and more |
| :clock1: | **Ops Simulation** | Long-running (days/weeks) operational simulation with SLO tracking |
| :zap: | **Dynamic Simulation** | Time-stepped simulation with traffic pattern integration |
| :newspaper: | **Security Feed** | Auto-generates scenarios from CISA, NVD, Krebs, BleepingComputer |
| :globe_with_meridians: | **Terraform Integration** | Import from tfstate/plan with change impact analysis |
| :desktop_computer: | **Web Dashboard** | D3.js interactive graph + Grafana-style dashboard |
| :mag: | **Multiple Discovery** | Local scan, Prometheus, Terraform, YAML |
| :moneybag: | **Cost Impact Engine** | Quantify downtime costs, SLA penalties, and ROI of resilience improvements |
| :shield: | **Security Resilience Engine** | Assess security posture against 8 threat categories with control gap analysis |

---

## Enterprise Features

| Feature | Description |
|---|---|
| Multi-tenant Dashboard | OAuth2 (GitHub/Google) + API key authentication with role-based access |
| CI/CD Integration | GitHub Actions marketplace action for pre-deploy chaos validation |
| DORA Compliance | Audit-ready reports for Digital Operational Resilience Act |
| Terraform Integration | Import from tfstate, analyze tf plan impact before apply |
| Prometheus Discovery | Auto-discover infrastructure from Prometheus targets |
| Slack & PagerDuty | Real-time notification of critical findings |
| Security Feed | Auto-generate scenarios from CVE/NVD/CISA feeds |
| AI-Powered Analysis | Architecture recommendations and root cause analysis |

---

## 3-Layer Availability Limit Model

**This is FaultRay's unique contribution to chaos engineering.**

Traditional chaos tools answer "what breaks?" FaultRay answers **"what is the maximum availability your architecture can physically achieve?"** using a three-layer mathematical model.

```
                    ┌─────────────────────────────────────────┐
                    │                                         │
  Layer 3 ──────── │  Theoretical Limit       6.65 nines     │ ── Upper bound
                    │  (perfect redundancy + perfect failover)│    (unreachable)
                    │                                         │
  Layer 2 ──────── │  Hardware Limit          5.91 nines     │ ── Physical ceiling
                    │  (component MTBF × redundancy)          │    (hard constraint)
                    │                                         │
  Layer 1 ──────── │  Software Limit          4.00 nines     │ ── Practical ceiling
                    │  (deployment + config + human error)    │    (your real target)
                    │                                         │
                    └─────────────────────────────────────────┘
```

### Layer 1: Software Availability Limit (practical ceiling)

Accounts for deployment failures, configuration drift, human error, and software bugs. Most organizations cannot exceed **4.00 nines (99.99%)** at this layer without extreme operational maturity.

### Layer 2: Hardware Availability Limit (physical ceiling)

Calculated from component MTBF (Mean Time Between Failures), redundancy factor, and failover time. Even with perfect software, hardware constraints cap availability at approximately **5.91 nines (99.999%)**.

### Layer 3: Theoretical Availability Limit (mathematical upper bound)

Assumes perfect redundancy, instant failover, and zero software errors. This is the mathematical ceiling your architecture can never exceed: **6.65 nines (99.99997%)**.

**Why this matters:** If your SLO target is 99.99% but your Layer 1 limit is 99.95%, no amount of engineering effort will close the gap without architectural changes. FaultRay tells you this **before** you waste months trying.

---

## 5 Simulation Engines

### 1. Cascade Engine
Models fault propagation through dependency graphs. Identifies single points of failure, compound failures, and cascade paths.
```bash
faultray load infra.yaml
faultray simulate --html report.html
```

### 2. Dynamic Engine
Time-stepped simulation with traffic pattern integration. Models real-world load variations over hours or days.
```bash
faultray dynamic infra.yaml --traffic diurnal --duration 24h --step 1min
```

### 3. Ops Engine
Long-running operational simulation (days to weeks) with SLO tracking, incident generation, and deployment events.
```bash
faultray ops-sim infra.yaml --days 7 --step 5min
```

### 4. What-If Engine
Parameter sweep analysis to understand fault tolerance sensitivity across multiple dimensions.
```bash
faultray whatif infra.yaml --parameter mttr_factor --values "0.5,1.0,2.0,4.0"
```

### 5. Capacity Engine
Growth forecasting with resource exhaustion prediction and SLO compliance evaluation.
```bash
faultray capacity infra.yaml --growth 0.15 --slo 99.9
```

---

## Usage

### From YAML Definition

```yaml
# infra.yaml
components:
  - id: nginx
    type: load_balancer
    port: 443
    replicas: 2
    metrics: { cpu_percent: 25, memory_percent: 30 }
    capacity: { max_connections: 10000 }

  - id: api
    type: app_server
    port: 8080
    metrics: { cpu_percent: 65, memory_percent: 70 }
    capacity: { max_connections: 500, connection_pool_size: 100 }

  - id: postgres
    type: database
    port: 5432
    metrics: { cpu_percent: 45, memory_percent: 80, disk_percent: 72 }
    capacity: { max_connections: 100 }

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
faultray simulate --html report.html
```

### From Terraform

```bash
# Import from state file
faultray tf-import --state terraform.tfstate

# Import from live terraform
faultray tf-import --dir ./terraform

# Analyze plan impact
terraform plan -out=plan.out
faultray tf-plan plan.out --html plan-report.html
```

### From Prometheus

```bash
faultray scan --prometheus-url http://prometheus:9090
faultray simulate
```

### Security News Feed

```bash
# Fetch latest security news and generate scenarios
faultray feed-update

# View generated scenarios
faultray feed-list

# Simulate with feed scenarios included automatically
faultray simulate
```

### Web Dashboard

```bash
faultray serve --port 8080
# Open http://localhost:8080
```

### Operational Simulation

Simulate long-running operations and track SLO compliance and incident patterns over time.

```bash
# Run 7-day operational simulation with 5-minute time steps
faultray ops-sim infra.yaml --days 7 --step 5min

# Run with default parameters
faultray ops-sim --defaults
```

### What-If Analysis

Sweep parameters to analyze fault tolerance sensitivity across multiple dimensions.

```bash
# Run with default parameter sweep
faultray whatif infra.yaml --defaults

# Sweep a specific parameter
faultray whatif --parameter mttr_factor --values "0.5,1.0,2.0,4.0"
```

### Capacity Planning

Forecast resource exhaustion and evaluate SLO compliance under growth projections.

```bash
# Capacity planning with 15% annual growth targeting 99.9% SLO
faultray capacity infra.yaml --growth 0.15 --slo 99.9
```

### Traffic Patterns

10 traffic models available for dynamic simulation:

| Pattern | Description |
|---------|-------------|
| `CONSTANT` | Steady-state constant traffic |
| `RAMP` | Linear traffic increase |
| `SPIKE` | Instantaneous traffic spike |
| `WAVE` | Sinusoidal wave pattern |
| `DDoS_VOLUMETRIC` | High-volume DDoS attack |
| `DDoS_SLOWLORIS` | Slowloris-style DDoS attack |
| `FLASH_CROWD` | Sudden viral popularity surge |
| `DIURNAL` | Daily cycle (high daytime, low nighttime) |
| `DIURNAL_WEEKLY` | Weekly cycle (high weekdays, low weekends) |
| `GROWTH_TREND` | Long-term organic growth trend |

```bash
# Dynamic simulation with traffic pattern
faultray dynamic infra.yaml --traffic diurnal --duration 24h --step 1min
```

---

## Chaos Scenarios (30 Categories)

| Category | Examples |
|----------|---------|
| **Single Failures** | Component down, CPU saturation, OOM, disk full, network partition |
| **Traffic** | 1.5x, 2x, 3x, 5x, 10x (DDoS-level) traffic spikes |
| **Compound** | All pairwise (C(n,2)) and triple (C(n,3)) simultaneous failures |
| **DB-Specific** | Log explosion, replication lag, connection storm, lock contention |
| **Cache-Specific** | Stampede, eviction storm, split brain |
| **Queue-Specific** | Backpressure, poison message |
| **LB-Specific** | Health check failure, TLS expiry, config reload failure |
| **App-Specific** | Memory leak, thread exhaustion, GC pause, bad deployment |
| **Infrastructure** | Zone failure, cascading timeouts, total meltdown, rolling restart |
| **Real-World** | Black Friday (10x + cache pressure), noisy neighbor, slow DB at peak |
| **Security Feed** | Auto-generated from CISA, NVD, Krebs, BleepingComputer, etc. |

---

## Risk Scoring

```
severity = (impact x spread) x likelihood

impact     = weighted health status (DOWN=1.0, OVERLOADED=0.5, DEGRADED=0.25)
spread     = affected_components / total_components
likelihood = proximity to failure threshold (0.2 = unlikely, 1.0 = imminent)
```

| Level | Score | Meaning |
|-------|-------|---------|
| CRITICAL | 7.0-10.0 | Cascading failure, major outage risk |
| WARNING | 4.0-6.9 | Degradation, limited cascade |
| PASSED | 0.0-3.9 | Low risk, contained impact |

---

## Architecture

```
┌─────────────────────────────────────────────┐
│                  FaultRay                     │
├──────────┬──────────┬──────────┬─────────────┤
│ Cascade  │ Dynamic  │   Ops    │  What-If    │
│ Engine   │ Engine   │  Engine  │  Engine     │
├──────────┴──────────┴──────────┴─────────────┤
│              Capacity Engine                   │
├───────────────────────────────────────────────┤
│          Dependency Graph (NetworkX)           │
├──────────┬──────────┬──────────┬─────────────┤
│   YAML   │Terraform │Prometheus│ Cloud APIs  │
│  Loader  │ Importer │Discovery │  (AWS/GCP)  │
└──────────┴──────────┴──────────┴─────────────┘
```

---

## CLI Commands

| Command | Description |
|---------|-------------|
| `faultray scan` | Discover local system or Prometheus infrastructure |
| `faultray simulate` | Run chaos simulation (2,000+ scenarios) |
| `faultray dynamic` | Run dynamic time-stepped simulation with traffic patterns |
| `faultray ops-sim` | Long-running operational simulation with SLO tracking |
| `faultray show` | Display infrastructure model summary |
| `faultray load <yaml>` | Load infrastructure from YAML |
| `faultray tf-import` | Import from Terraform state |
| `faultray tf-plan <plan>` | Analyze Terraform plan impact |
| `faultray report` | Generate HTML report |
| `faultray serve` | Launch web dashboard |
| `faultray demo` | Run demo with sample infrastructure |
| `faultray feed-update` | Update scenarios from security news |
| `faultray feed-list` | Show stored feed scenarios |
| `faultray feed-sources` | Show configured news sources |
| `faultray feed-clear` | Clear feed scenario store |
| `faultray whatif` | Run what-if analysis (parameter sweep) |
| `faultray capacity` | Capacity planning with growth forecasting |

---

## Docker

### Docker Compose Services

| Service | Description | Command |
|---------|-------------|---------|
| `web` | Web dashboard on port 8000 | `docker compose up web` |
| `demo` | Demo mode with sample infrastructure | `docker compose --profile demo up demo` |
| `cli` | CLI mode for running simulations | `docker compose --profile cli run cli <command>` |

### Docker Build

```bash
# Build
docker build -t faultray .

# Run web dashboard
docker run -p 8000:8000 faultray

# Run CLI command
docker run --rm faultray faultray simulate

# Mount custom infrastructure definition
docker run --rm -v $(pwd)/infra.yaml:/app/infra.yaml faultray faultray load /app/infra.yaml
```

### Docker Compose Examples

```bash
# Start web dashboard
docker compose up web

# Run a simulation via CLI
docker compose --profile cli run cli load examples/demo-infra.yaml

# Run with Terraform state mounted
docker compose --profile cli run -v $(pwd)/terraform.tfstate:/app/terraform.tfstate \
  cli tf-import --state /app/terraform.tfstate
```

---

## Development

```bash
# Install in development mode
pip install -e ".[dev]"

# Run tests (19,757 tests)
pytest tests/ -v

# Lint
ruff check src/ tests/

# Build Docker image
docker build -t faultray:dev .
```

### Test Coverage

**19,757 tests — all passing** (pytest)

| Module | Description |
|--------|-------------|
| Cascade / Static Engine | Fault propagation, severity scoring, compound failures, SPOF detection |
| Dynamic Engine | Time-stepped simulation, autoscaling, circuit breakers, failover, traffic patterns |
| Ops Engine | 7-day operational simulation, SLO tracking, deployments, incident generation |
| Capacity Engine | Growth forecasting, right-sizing, HA guard, quorum guard, cost optimization |
| What-If Engine | Parameter sweep, sensitivity analysis, breakpoint detection |
| Scenarios | 30 categories, rolling restart (maxUnavailable), compound/triple failures |
| Traffic Models | All 10 patterns + determinism + DDoS simulation |
| Security Feeds | CISA/NVD analysis, scoring, store operations |
| Loaders | YAML parsing, validation, circular dependency detection, Terraform import |
| 3-Layer Limits | Availability ceiling calculation, nines computation |
| API / Web | FastAPI endpoints, D3.js dashboard, HTML report generation |

### Requirements

- Python 3.11+
- Dependencies: typer, rich, pydantic, networkx, psutil, fastapi, uvicorn, jinja2, httpx, pyyaml

---

## Related Work & Differentiation

FaultRay occupies a unique position in the chaos engineering landscape: **pure offline simulation with no production fault injection.** This section clarifies how FaultRay relates to prior academic work and existing tools.

### Academic Prior Art

| Paper | Year | Approach | FaultRay Differentiator |
|-------|------|----------|------------------------|
| Krasnovsky & Zorkin, "[Model Discovery and Graph Simulation](https://arxiv.org/abs/2506.11176)" (ICSE-NIER '26) | 2025 | Graph reachability + Monte Carlo for fail-stop availability estimation | FaultRay goes far beyond static graph reachability: **5 integrated engines** (Dynamic, Ops, What-If, Capacity), traffic simulation, autoscaling, circuit breakers, HA/quorum guards |
| Poltronieri et al., "ChaosTwin" (IFIP/IEEE CNSM) | 2021 | Digital twin + chaos event simulation | FaultRay uses declarative YAML models, not digital twins. No runtime environment required |
| Mendonca et al., "Model-Based Analysis of Microservice Resiliency Patterns" (IEEE ICSA) | 2020 | PRISM model checker for Retry/CB patterns | FaultRay uses simulation (not formal verification) and covers 30 failure categories, not just 2 patterns |
| Buldyrev et al., "Catastrophic cascade of failures in interdependent networks" (Nature) | 2010 | Percolation theory for cascade analysis | FaultRay applies cascade analysis specifically to IT infrastructure with practical tooling (CLI, reports, dashboards) |

### Key Differentiators from All Prior Work

1. **5-Engine Integration** — No existing tool or paper combines Static (SPOF/cascade), Dynamic (traffic/autoscaling/CB/failover), Ops (7-day simulation), What-If (parameter sensitivity), and Capacity (right-sizing/HA/quorum) in a single platform.
2. **Declarative YAML Model** — Infrastructure defined as code, no runtime environment or agents required.
3. **HA & Quorum Guards** — Capacity Engine respects HA constraints (min 2 replicas for LB/DNS/failover) and quorum constraints (min 3 for cache/queue clusters), preventing false right-sizing recommendations.
4. **3-Layer Availability Limit Model** — Mathematical proof of system availability ceiling (Software, Hardware, Theoretical layers). No other tool provides this.
5. **Zero Risk** — All simulation runs in memory. No production fault injection, no agents, no sidecars.

### Patent & IP Clearance

FaultRay has been evaluated against all known chaos engineering patents (US11397665B2 JPMorgan, US11356324B2 Dell, US7334222B2) and found **no conflicts**. All existing patents cover real-environment fault injection via APIs or service meshes — a fundamentally different approach from FaultRay's pure mathematical simulation.

---

## Changelog

### v8.0.0 (2026-03-15)
- SRE maturity assessment, anti-pattern detection, A/B testing, observability integration, DORA metrics
- HA minimum replica guard (failover/LB/DNS → min 2 replicas)
- Cluster quorum guard (cache/queue with ≥3 replicas → min 3)
- MAX_SCENARIOS raised from 1,000 to 2,000 (zero truncation)
- Emergency autoscaling (>90% utilization → immediate 2x step scale-up)
- Adaptive circuit breaker recovery (1/3 timeout first OPEN + exponential backoff)
- maxUnavailable-based rolling restart scenarios (K8s 25% default)
- 1,070 tests passing

---

## Community

- [Contributing Guide](CONTRIBUTING.md) — How to contribute
- [Security Policy](SECURITY.md) — Vulnerability reporting
- [Code of Conduct](CODE_OF_CONDUCT.md) — Community guidelines
- [Changelog](CHANGELOG.md) — Release history

## License

MIT License - see [LICENSE](LICENSE)

---

# FaultRay（日本語）

> **本番環境に触れずにインフラ障害をシミュレーション。**
> **数学的にシステムの可用性上限を証明します。**

FaultRayは、純粋な数学的シミュレーションによるゼロリスクのカオスエンジニアリングツールです。
依存グラフ全体をメモリ内でモデル化し、5つのエンジンで2,000以上の障害シナリオを実行します。

### 主な特徴

- **ゼロリスク** — 完全にメモリ内で実行。エージェント不要、本番影響ゼロ
- **5つのシミュレーションエンジン** — カスケード、動的、運用、What-If、キャパシティ
- **3層可用性限界モデル** — システムの可用性上限を数学的に証明する唯一のツール
- **2,000+シナリオ** — 30カテゴリの障害シナリオをトポロジーから自動生成
- **Terraform統合** — tfstateインポート、tfplanの影響分析
- **セキュリティフィード** — CVE/NVD/CISAからシナリオを自動生成
- **コスト影響エンジン** — ダウンタイムコスト、SLAペナルティ、改善ROIを定量化
- **セキュリティ耐性エンジン** — 8種の脅威カテゴリに対するセキュリティ態勢を評価

### クイックスタート

```bash
pip install faultray
faultray demo        # デモ実行
faultray demo --web  # Webダッシュボード付き
```

### なぜ FaultRay なのか？

従来のカオスエンジニアリングツール（Gremlin, Steadybit, AWS FIS）は**実際のインフラに障害を注入**します。FaultRay はまったく異なるアプローチ：**純粋な数学的シミュレーション**で依存関係グラフ全体をメモリ上にモデル化し、5つのエンジンで2,000以上の障害シナリオを実行して、システムの理論的可用性上限を証明します。サーバーに一切触れません。

| | **Gremlin** | **Steadybit** | **AWS FIS** | **FaultRay** |
|---|---|---|---|---|
| **アプローチ** | 障害注入 | 障害注入 | 障害注入 | 数学的シミュレーション |
| **本番リスク** | 中〜高 | 中 | 中 | **ゼロ** |
| **セットアップ** | ホスト毎にエージェント | ホスト毎にエージェント | AWSのみ | **pip install のみ** |
| **シナリオ数** | 手動設定 | 手動設定 | AWSサービスのみ | **2,000+自動生成** |
| **可用性証明** | なし | なし | なし | **3層限界モデル** |
| **コスト** | $$$$ | $$$ | $$ | **無料 / OSS** |

### 3層可用性限界モデル（最大の特徴）

FaultRay 独自の理論モデルです。従来のカオスツールが「何が壊れるか？」に答えるのに対し、FaultRay は **「あなたのアーキテクチャが物理的に達成できる最大可用性はいくつか？」** に答えます。

| 層 | 名称 | 上限 | 説明 |
|---|---|---|---|
| **Layer 3** | 理論限界 | 6.65 nines | 完全な冗長性＋瞬時フェイルオーバーを仮定した数学的上限（到達不可） |
| **Layer 2** | ハードウェア限界 | 5.91 nines | コンポーネントMTBF × 冗長係数から算出される物理的上限 |
| **Layer 1** | ソフトウェア限界 | 4.00 nines | デプロイ失敗・設定ドリフト・ヒューマンエラーを考慮した実用上限 |

**重要な意味:** SLO目標が99.99%でもLayer 1の限界が99.95%なら、どれだけエンジニアリング努力を重ねてもアーキテクチャ変更なしにはギャップを埋められません。FaultRay は**数ヶ月の無駄な努力の前に**それを教えてくれます。

### 5つのシミュレーションエンジン

1. **カスケードエンジン** — 依存関係グラフを通じた障害伝搬モデリング
2. **ダイナミックエンジン** — トラフィックパターン連動の時間ステップ型シミュレーション
3. **Opsエンジン** — 長期間（数日〜数週間）の運用シミュレーション
4. **What-Ifエンジン** — パラメータスイープによる感度分析
5. **キャパシティエンジン** — 成長予測とリソース枯渇予測、HAガード（最低2レプリカ）、クォーラムガード（最低3レプリカ）

### 先行研究との関係

FaultRay は「本番環境に障害を注入しない純粋なオフラインシミュレーション」という独自の立場にあります。

| 論文 | 手法 | FaultRay の差別化 |
|------|------|-------------------|
| Krasnovsky & Zorkin (2025) "[Model Discovery and Graph Simulation](https://arxiv.org/abs/2506.11176)" | グラフ到達可能性 + モンテカルロ | FaultRay は **5エンジン統合**（動的シミュレーション、Ops、What-If、Capacity を含む） |
| Poltronieri et al. (2021) "ChaosTwin" | デジタルツイン | FaultRay は **YAML宣言的モデル**。実行環境不要 |
| Mendonca et al. (2020) "Model-Based Analysis" | PRISM形式検証 | FaultRay は **30カテゴリのシナリオ**を自動生成。2パターンの分析ではない |

**特許・知財クリアランス:** 既存のカオスエンジニアリング特許（US11397665B2, US11356324B2）はすべて「実環境への障害注入」が対象であり、FaultRay の純粋シミュレーションアプローチとは技術カテゴリが異なります。抵触なし。

### コミュニティ

- [Contributing Guide](CONTRIBUTING.md) — 貢献ガイド
- [Security Policy](SECURITY.md) — 脆弱性報告ポリシー
- [Code of Conduct](CODE_OF_CONDUCT.md) — 行動規範
- [Changelog](CHANGELOG.md) — 変更履歴

### ライセンス

MIT License - [LICENSE](LICENSE) を参照
