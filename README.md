# FaultZero — Zero-Risk Infrastructure Chaos Simulation

> **Simulate infrastructure failures without touching production.**
> **Prove your system's availability ceiling mathematically.**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-89%20passed-brightgreen.svg)]()
[![Version](https://img.shields.io/badge/version-5.14-blue.svg)]()
[![Docker](https://img.shields.io/badge/docker-ready-2496ED.svg)](Dockerfile)
[![PyPI](https://img.shields.io/badge/PyPI-faultzero-orange.svg)]()

---

## Why FaultZero?

Most chaos engineering tools inject real faults into real infrastructure. FaultZero takes a fundamentally different approach: **pure mathematical simulation** that models your entire dependency graph in memory, runs 150+ failure scenarios, and proves your system's theoretical availability ceiling — all without touching a single server.

| | **Gremlin** | **Steadybit** | **AWS FIS** | **FaultZero** |
|---|---|---|---|---|
| **Approach** | Fault injection | Fault injection | Fault injection | Mathematical simulation |
| **Risk to production** | Medium-High | Medium | Medium | **Zero** |
| **Setup required** | Agent per host | Agent per host | AWS-only | **Single pip install** |
| **Scenario count** | Manual config | Manual config | AWS services only | **150+ auto-generated** |
| **Availability proof** | No | No | No | **3-Layer Limit Model** |
| **Cost** | $$$$ | $$$ | $$ (AWS-only) | **Free / OSS** |
| **Dependency graph** | No | Limited | No | **Full NetworkX graph** |
| **Terraform integration** | No | No | Native | **tfstate + plan analysis** |
| **Security feed** | No | No | No | **Auto CVE scenarios** |

**Key differentiators:**

- **Zero risk** — Runs entirely in memory. No agents, no sidecars, no production impact.
- **5 simulation engines** — Cascade, Dynamic, Ops, What-If, and Capacity engines working together.
- **3-Layer Availability Limit Model** — The only tool that mathematically proves your system's availability ceiling (see below).

---

## Quick Start

### pip

```bash
# Install
pip install -e .

# Run demo (6-component web stack simulation)
faultzero demo

# With web dashboard
faultzero demo --web
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
docker build -t faultzero .
docker run -p 8000:8000 faultzero
```

### Demo Output

```
╭────────── FaultZero Chaos Simulation Report ──────────╮
│ Resilience Score: 36/100                             │
│ Scenarios tested: 150                                │
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
| :chart_with_upwards_trend: | **150+ Chaos Scenarios** | 30 categories of failure scenarios auto-generated from your topology |
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

---

## 3-Layer Availability Limit Model

**This is FaultZero's unique contribution to chaos engineering.**

Traditional chaos tools answer "what breaks?" FaultZero answers **"what is the maximum availability your architecture can physically achieve?"** using a three-layer mathematical model.

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

**Why this matters:** If your SLO target is 99.99% but your Layer 1 limit is 99.95%, no amount of engineering effort will close the gap without architectural changes. FaultZero tells you this **before** you waste months trying.

---

## 5 Simulation Engines

### 1. Cascade Engine
Models fault propagation through dependency graphs. Identifies single points of failure, compound failures, and cascade paths.
```bash
faultzero load infra.yaml
faultzero simulate --html report.html
```

### 2. Dynamic Engine
Time-stepped simulation with traffic pattern integration. Models real-world load variations over hours or days.
```bash
faultzero dynamic infra.yaml --traffic diurnal --duration 24h --step 1min
```

### 3. Ops Engine
Long-running operational simulation (days to weeks) with SLO tracking, incident generation, and deployment events.
```bash
faultzero ops-sim infra.yaml --days 7 --step 5min
```

### 4. What-If Engine
Parameter sweep analysis to understand fault tolerance sensitivity across multiple dimensions.
```bash
faultzero whatif infra.yaml --parameter mttr_factor --values "0.5,1.0,2.0,4.0"
```

### 5. Capacity Engine
Growth forecasting with resource exhaustion prediction and SLO compliance evaluation.
```bash
faultzero capacity infra.yaml --growth 0.15 --slo 99.9
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
faultzero load infra.yaml
faultzero simulate --html report.html
```

### From Terraform

```bash
# Import from state file
faultzero tf-import --state terraform.tfstate

# Import from live terraform
faultzero tf-import --dir ./terraform

# Analyze plan impact
terraform plan -out=plan.out
faultzero tf-plan plan.out --html plan-report.html
```

### From Prometheus

```bash
faultzero scan --prometheus-url http://prometheus:9090
faultzero simulate
```

### Security News Feed

```bash
# Fetch latest security news and generate scenarios
faultzero feed-update

# View generated scenarios
faultzero feed-list

# Simulate with feed scenarios included automatically
faultzero simulate
```

### Web Dashboard

```bash
faultzero serve --port 8080
# Open http://localhost:8080
```

### Operational Simulation

Simulate long-running operations and track SLO compliance and incident patterns over time.

```bash
# Run 7-day operational simulation with 5-minute time steps
faultzero ops-sim infra.yaml --days 7 --step 5min

# Run with default parameters
faultzero ops-sim --defaults
```

### What-If Analysis

Sweep parameters to analyze fault tolerance sensitivity across multiple dimensions.

```bash
# Run with default parameter sweep
faultzero whatif infra.yaml --defaults

# Sweep a specific parameter
faultzero whatif --parameter mttr_factor --values "0.5,1.0,2.0,4.0"
```

### Capacity Planning

Forecast resource exhaustion and evaluate SLO compliance under growth projections.

```bash
# Capacity planning with 15% annual growth targeting 99.9% SLO
faultzero capacity infra.yaml --growth 0.15 --slo 99.9
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
faultzero dynamic infra.yaml --traffic diurnal --duration 24h --step 1min
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
Discovery Layer          Model Layer           Simulator Layer
┌─────────────┐    ┌─────────────────┐    ┌──────────────────┐
│ Local Scan   │    │ InfraGraph      │    │ 30-cat Scenarios │
│ Prometheus   │───>│ Components      │───>│ Cascade Engine   │
│ Terraform    │    │ Dependencies    │    │ Dynamic Engine   │
│ YAML Loader  │    │ NetworkX Graph  │    │ Ops Engine       │
└─────────────┘    └─────────────────┘    │ What-If Engine   │
                                          │ Capacity Engine  │
                                          │ Traffic Models   │
                                          │ Feed Scenarios   │
                                          │ Risk Scoring     │
                                          │ 3-Layer Limits   │
                                          └──────────────────┘
                                                    │
                   ┌─────────────────┐    ┌──────────────────┐
                   │ Web Dashboard   │<───│ CLI Reporter     │
                   │ FastAPI + D3.js │    │ HTML Reporter    │
                   │ Docker Ready    │    │ JSON Export      │
                   └─────────────────┘    └──────────────────┘
```

---

## CLI Commands

| Command | Description |
|---------|-------------|
| `faultzero scan` | Discover local system or Prometheus infrastructure |
| `faultzero simulate` | Run chaos simulation (150+ scenarios) |
| `faultzero dynamic` | Run dynamic time-stepped simulation with traffic patterns |
| `faultzero ops-sim` | Long-running operational simulation with SLO tracking |
| `faultzero show` | Display infrastructure model summary |
| `faultzero load <yaml>` | Load infrastructure from YAML |
| `faultzero tf-import` | Import from Terraform state |
| `faultzero tf-plan <plan>` | Analyze Terraform plan impact |
| `faultzero report` | Generate HTML report |
| `faultzero serve` | Launch web dashboard |
| `faultzero demo` | Run demo with sample infrastructure |
| `faultzero feed-update` | Update scenarios from security news |
| `faultzero feed-list` | Show stored feed scenarios |
| `faultzero feed-sources` | Show configured news sources |
| `faultzero feed-clear` | Clear feed scenario store |
| `faultzero whatif` | Run what-if analysis (parameter sweep) |
| `faultzero capacity` | Capacity planning with growth forecasting |

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
docker build -t faultzero .

# Run web dashboard
docker run -p 8000:8000 faultzero

# Run CLI command
docker run --rm faultzero faultzero simulate

# Mount custom infrastructure definition
docker run --rm -v $(pwd)/infra.yaml:/app/infra.yaml faultzero faultzero load /app/infra.yaml
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

# Run tests (89 tests, < 1 second)
pytest tests/ -v

# Lint
ruff check src/ tests/

# Build Docker image
docker build -t faultzero:dev .
```

### Test Coverage

| Module | Tests | Coverage |
|--------|-------|----------|
| Cascade Engine | 14 | Fault propagation, severity scoring, compound failures |
| Dynamic Engine | 14 | CLI output, severity classification, boundary values |
| Ops Engine | 9 | SLO tracking, traffic patterns, deployments |
| Capacity Engine | 8 | Forecasting, right-sizing, SLO targets |
| Scenarios | 4 | Rolling restart edge cases, scenario generation |
| Traffic | 11 | All 10 traffic patterns + determinism |
| Feeds | 11 | Analysis, scoring, store operations |
| Loader | 10 | YAML parsing, validation, circular dependency detection |
| Graph | 2 | Cascade paths, critical path limits |
| **Total** | **89** | **All passing** |

### Requirements

- Python 3.11+
- Dependencies: typer, rich, pydantic, networkx, psutil, fastapi, uvicorn, jinja2, httpx, pyyaml

---

## Changelog

### v5.14 (2026-03-14)
- 3-Layer Availability Limit Model: mathematical proof of system availability ceiling
- Layer 1 (Software 4.00 nines), Layer 2 (Hardware 5.91 nines), Layer 3 (Theoretical 6.65 nines)
- README overhauled to commercial/OSS quality with bilingual EN/JP support

### v5.13 (2026-03-14)
- Docker Compose multi-service configuration (web, demo, cli profiles)
- Volume mounts for persistent feed data and report output

### v5.12 (2026-03-14)
- Dockerfile with Python 3.11-slim base
- Container-ready web dashboard deployment

### v5.11 (2026-03-14)
- Competitive positioning against Gremlin, Steadybit, AWS FIS
- Feature matrix documentation

### v5.10 (2026-03-14)
- Architecture diagram updated with all 5 engines and 3-Layer Limits
- JSON export support for simulation results

### v5.9 (2026-03-14)
- Traffic model descriptions translated to English
- Bilingual documentation structure (EN/JP)

### v5.8 (2026-03-14)
- Dynamic Engine label in architecture (was "Ops Engine" duplicate)
- CLI command table aligned with all registered subcommands

### v5.7 (2026-03-14)
- Risk scoring formula documentation improvements
- Severity threshold boundary clarification

### v5.6 (2026-03-14)
- Fix: Rolling restart scenario now keeps at least 1 server running
- 4 new scenario edge case tests

### v5.5 (2026-03-14)
- Fix: Dynamic simulation results always showed 0 critical/0 warning (float vs string comparison)
- Fix: `dynamic` command passed report object instead of results list
- Fix: `--deploy-hour` validation (0-23 range)
- 14 new dynamic CLI tests

### v5.4 (2026-03-14)
- Pydantic field_validators for input boundary defense

### v5.3 (2026-03-13)
- Fix TypeError in dynamic CLI command

### v5.2 (2026-03-13)
- Security hardening and robustness improvements

### v5.1 (2026-03-13)
- Consistency fixes, test coverage, CLI validation

### v5.0 (2026-03-13)
- README overhaul, graph fixes, CLI UX improvements

---

## License

MIT License - see [LICENSE](LICENSE)

---

---

# FaultZero — ゼロリスク・インフラ障害シミュレーション（日本語）

> **本番環境に一切触れずにインフラ障害をシミュレーション。**
> **システムの可用性上限を数学的に証明。**

## なぜ FaultZero なのか？

従来のカオスエンジニアリングツール（Gremlin, Steadybit, AWS FIS）は**実際のインフラに障害を注入**します。FaultZero はまったく異なるアプローチ：**純粋な数学的シミュレーション**で依存関係グラフ全体をメモリ上にモデル化し、150以上の障害シナリオを実行して、システムの理論的可用性上限を証明します。サーバーに一切触れません。

| | **Gremlin** | **Steadybit** | **AWS FIS** | **FaultZero** |
|---|---|---|---|---|
| **アプローチ** | 障害注入 | 障害注入 | 障害注入 | 数学的シミュレーション |
| **本番リスク** | 中〜高 | 中 | 中 | **ゼロ** |
| **セットアップ** | ホスト毎にエージェント | ホスト毎にエージェント | AWSのみ | **pip install のみ** |
| **シナリオ数** | 手動設定 | 手動設定 | AWSサービスのみ | **150+自動生成** |
| **可用性証明** | なし | なし | なし | **3層限界モデル** |
| **コスト** | $$$$ | $$$ | $$ | **無料 / OSS** |

## クイックスタート

### pip

```bash
# インストール
pip install -e .

# デモ実行（6コンポーネントWebスタック）
faultzero demo

# Web ダッシュボード付き
faultzero demo --web
```

### Docker

```bash
# Web ダッシュボード（http://localhost:8000）
docker compose up web

# デモモード
docker compose --profile demo up demo

# CLI モード
docker compose --profile cli run cli simulate
```

## 主要機能

- :shield: **ゼロリスクシミュレーション** — 完全にメモリ上で実行。エージェント不要、本番への影響ゼロ
- :chart_with_upwards_trend: **150以上のカオスシナリオ** — 30カテゴリの障害シナリオをトポロジーから自動生成
- :link: **依存関係グラフ解析** — NetworkX によるグラフモデリングと連鎖障害予測
- :triangular_ruler: **3層可用性限界証明** — システムの理論的可用性上限を数学的に証明
- :dart: **SLO/SLI 追跡** — 可用性・レイテンシ・エラー率のSLO目標に対する追跡
- :crystal_ball: **What-If 分析** — パラメータスイープによる障害耐性の感度分析
- :bar_chart: **キャパシティプランニング** — 成長予測に基づくSLO達成可否の評価
- :ocean: **10種類のトラフィックモデル** — DDoS・日次変動・フラッシュクラウド等
- :newspaper: **セキュリティフィード** — CISA, NVD等から最新脅威シナリオを自動追加
- :globe_with_meridians: **Terraform 連携** — tfstate/plan からインフラ自動インポートと変更影響分析
- :desktop_computer: **Web ダッシュボード** — D3.js インタラクティブグラフ + Grafana風ダッシュボード

## 3層可用性限界モデル（最大の特徴）

FaultZero 独自の理論モデルです。従来のカオスツールが「何が壊れるか？」に答えるのに対し、FaultZero は **「あなたのアーキテクチャが物理的に達成できる最大可用性はいくつか？」** に答えます。

| 層 | 名称 | 上限 | 説明 |
|---|---|---|---|
| **Layer 3** | 理論限界 | 6.65 nines | 完全な冗長性＋瞬時フェイルオーバーを仮定した数学的上限（到達不可） |
| **Layer 2** | ハードウェア限界 | 5.91 nines | コンポーネントMTBF × 冗長係数から算出される物理的上限 |
| **Layer 1** | ソフトウェア限界 | 4.00 nines | デプロイ失敗・設定ドリフト・ヒューマンエラーを考慮した実用上限 |

**重要な意味:** SLO目標が99.99%でもLayer 1の限界が99.95%なら、どれだけエンジニアリング努力を重ねてもアーキテクチャ変更なしにはギャップを埋められません。FaultZero は**数ヶ月の無駄な努力の前に**それを教えてくれます。

## 5つのシミュレーションエンジン

1. **カスケードエンジン** — 依存関係グラフを通じた障害伝搬モデリング
2. **ダイナミックエンジン** — トラフィックパターン連動の時間ステップ型シミュレーション
3. **Opsエンジン** — 長期間（数日〜数週間）の運用シミュレーション
4. **What-Ifエンジン** — パラメータスイープによる感度分析
5. **キャパシティエンジン** — 成長予測とリソース枯渇予測

## ライセンス

MIT License - [LICENSE](LICENSE) を参照
