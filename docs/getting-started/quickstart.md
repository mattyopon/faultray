# Quick Start

Get FaultRay up and running in under 5 minutes. This tutorial walks you through defining a 3-tier web application, running a chaos simulation, and viewing the results in the web dashboard.

## Prerequisites

- Python 3.11 or later
- pip 21.0 or later

## Step 1: Install FaultRay

```bash
pip install faultray
```

Verify the installation:

```bash
faultray --version
```

## Step 2: Define Your Infrastructure (YAML)

Create a file called `my-infra.yaml` that describes a standard 3-tier web application with a load balancer, application servers, and a database:

```yaml
# my-infra.yaml -- 3-Tier Web Application
schema_version: "3.0"

components:
  - id: lb
    name: "Load Balancer (nginx)"
    type: load_balancer
    host: lb.web.internal
    port: 443
    replicas: 2
    capacity:
      max_connections: 20000
      max_rps: 50000
    metrics:
      cpu_percent: 12
      memory_percent: 15
    failover:
      enabled: true
      promotion_time_seconds: 10
    cost_profile:
      hourly_infra_cost: 0.25
      revenue_per_minute: 50.0

  - id: app
    name: "Application Server"
    type: app_server
    host: app.web.internal
    port: 8080
    replicas: 3
    capacity:
      max_connections: 2000
      max_rps: 10000
      connection_pool_size: 200
      timeout_seconds: 30
    metrics:
      cpu_percent: 35
      memory_percent: 45
    autoscaling:
      enabled: true
      min_replicas: 2
      max_replicas: 8
      scale_up_threshold: 70
      scale_down_threshold: 30
    cost_profile:
      hourly_infra_cost: 0.50

  - id: db
    name: "PostgreSQL Database"
    type: database
    host: db.web.internal
    port: 5432
    replicas: 2
    capacity:
      max_connections: 500
      max_disk_gb: 200
    metrics:
      cpu_percent: 25
      memory_percent: 40
      disk_percent: 35
    failover:
      enabled: true
      promotion_time_seconds: 30
    security:
      encryption_at_rest: true
      encryption_in_transit: true
      backup_enabled: true
    cost_profile:
      hourly_infra_cost: 1.20

dependencies:
  - source: lb
    target: app
    type: requires
    protocol: http
    latency_ms: 1.0
    circuit_breaker:
      enabled: true
      failure_threshold: 5
      recovery_timeout_seconds: 30

  - source: app
    target: db
    type: requires
    protocol: tcp
    port: 5432
    latency_ms: 2.0
    circuit_breaker:
      enabled: true
      failure_threshold: 3
      recovery_timeout_seconds: 60
    retry_strategy:
      enabled: true
      max_retries: 3
      initial_delay_ms: 100
```

> **Tip:** FaultRay ships with built-in templates. You can generate this file automatically:
>
> ```bash
> faultray template use web-app --output my-infra.yaml
> ```
>
> Available templates: `web-app`, `microservices`, `ecommerce`, `data-pipeline`, `fintech`

## Step 3: Run the Simulation

Load the infrastructure definition and run a full chaos simulation:

```bash
faultray load my-infra.yaml
faultray simulate --html report.html
```

FaultRay will automatically generate and execute 2,000+ failure scenarios across 5 simulation engines:

```
+---------- FaultRay Chaos Simulation Report ----------+
| Resilience Score: 72/100                              |
| Scenarios tested: 2,000+                              |
| Critical: 2  Warning: 18  Passed: 130                 |
+-------------------------------------------------------+

AVAILABILITY CEILING (3-Layer Limit Model)
  Layer 3 (Theoretical):  6.65 nines  (99.99997%)
  Layer 2 (Hardware):     5.91 nines  (99.999%)
  Layer 1 (Software):     4.00 nines  (99.99%)

CRITICAL FINDINGS

  8.5/10 CRITICAL  Database single-region failure
  Cascade path:
  +-- DOWN PostgreSQL (primary)
  +-- DOWN Application Server (connection refused)

  7.2/10 CRITICAL  Traffic spike (10x)
  Cascade path:
  +-- OVERLOADED nginx (LB)
  +-- DEGRADED Application Server
  +-- OVERLOADED PostgreSQL (connection pool exhausted)
```

## Step 4: Launch the Web Dashboard

Start the interactive web dashboard for a visual exploration of the results:

```bash
faultray serve --port 8080
```

Open [http://localhost:8080](http://localhost:8080) in your browser. The dashboard provides:

- **Dependency Graph** -- Interactive D3.js visualization of your infrastructure topology
- **Scenario Explorer** -- Browse all 2,000+ tested scenarios with severity filtering
- **Availability Ceiling** -- Visual representation of the 3-Layer Limit Model
- **Cost Impact** -- Estimated downtime costs and SLA penalty exposure

## Step 5: Try Advanced Simulation Engines

FaultRay includes 5 simulation engines. Try them individually for deeper analysis:

```bash
# Dynamic simulation with diurnal traffic pattern (24-hour cycle)
faultray dynamic my-infra.yaml --traffic diurnal --duration 24h --step 1min

# What-if analysis: how does MTTR affect resilience?
faultray whatif my-infra.yaml --parameter mttr_factor --values "0.5,1.0,2.0,4.0"

# Capacity planning with 15% annual growth
faultray capacity my-infra.yaml --growth 0.15 --slo 99.9

# 7-day operational simulation
faultray ops-sim my-infra.yaml --days 7 --step 5min
```

## Next Steps

- [Your First Simulation](first-simulation.md) -- Deep dive into simulation results and how to interpret them
- [Installation](installation.md) -- Alternative installation methods (Docker, cloud provider support)
- [CLI Reference](../cli/commands.md) -- Full command documentation
- [3-Layer Availability Model](../concepts/five-layer-model.md) -- Understand FaultRay's model-based availability-ceiling estimation (from declared topology)
- [Templates](https://github.com/mattyopon/faultray/tree/main/src/faultray/templates) -- Browse all built-in infrastructure templates

---

# クイックスタート（日本語）

FaultRay を5分で起動し、シミュレーションを実行するチュートリアルです。3層Webアプリケーション（LB + App + DB）を定義し、カオスシミュレーションを実行し、結果をダッシュボードで確認します。

## 前提条件

- Python 3.11 以降
- pip 21.0 以降

## ステップ 1: FaultRay のインストール

```bash
pip install faultray
```

インストールの確認:

```bash
faultray --version
```

## ステップ 2: インフラ定義（YAML）

`my-infra.yaml` という名前のファイルを作成し、ロードバランサー + アプリケーションサーバー + データベースの3層Webアプリケーションを定義します:

```yaml
# my-infra.yaml -- 3層Webアプリケーション
schema_version: "3.0"

components:
  - id: lb
    name: "Load Balancer (nginx)"
    type: load_balancer
    host: lb.web.internal
    port: 443
    replicas: 2
    capacity:
      max_connections: 20000
      max_rps: 50000
    metrics:
      cpu_percent: 12
      memory_percent: 15
    failover:
      enabled: true
      promotion_time_seconds: 10
    cost_profile:
      hourly_infra_cost: 0.25
      revenue_per_minute: 50.0

  - id: app
    name: "Application Server"
    type: app_server
    host: app.web.internal
    port: 8080
    replicas: 3
    capacity:
      max_connections: 2000
      max_rps: 10000
      connection_pool_size: 200
      timeout_seconds: 30
    metrics:
      cpu_percent: 35
      memory_percent: 45
    autoscaling:
      enabled: true
      min_replicas: 2
      max_replicas: 8
      scale_up_threshold: 70
      scale_down_threshold: 30
    cost_profile:
      hourly_infra_cost: 0.50

  - id: db
    name: "PostgreSQL Database"
    type: database
    host: db.web.internal
    port: 5432
    replicas: 2
    capacity:
      max_connections: 500
      max_disk_gb: 200
    metrics:
      cpu_percent: 25
      memory_percent: 40
      disk_percent: 35
    failover:
      enabled: true
      promotion_time_seconds: 30
    security:
      encryption_at_rest: true
      encryption_in_transit: true
      backup_enabled: true
    cost_profile:
      hourly_infra_cost: 1.20

dependencies:
  - source: lb
    target: app
    type: requires
    protocol: http
    latency_ms: 1.0
    circuit_breaker:
      enabled: true
      failure_threshold: 5
      recovery_timeout_seconds: 30

  - source: app
    target: db
    type: requires
    protocol: tcp
    port: 5432
    latency_ms: 2.0
    circuit_breaker:
      enabled: true
      failure_threshold: 3
      recovery_timeout_seconds: 60
    retry_strategy:
      enabled: true
      max_retries: 3
      initial_delay_ms: 100
```

> **ヒント:** FaultRay にはビルトインテンプレートが付属しています。以下のコマンドで自動生成できます:
>
> ```bash
> faultray template use web-app --output my-infra.yaml
> ```
>
> 利用可能なテンプレート: `web-app`, `microservices`, `ecommerce`, `data-pipeline`, `fintech`

## ステップ 3: シミュレーションの実行

インフラ定義をロードし、カオスシミュレーションを実行します:

```bash
faultray load my-infra.yaml
faultray simulate --html report.html
```

FaultRay は5つのシミュレーションエンジンで2,000以上の障害シナリオを自動生成・実行します:

```
+---------- FaultRay Chaos Simulation Report ----------+
| Resilience Score: 72/100                              |
| Scenarios tested: 2,000+                              |
| Critical: 2  Warning: 18  Passed: 130                 |
+-------------------------------------------------------+

AVAILABILITY CEILING（3層限界モデル）
  Layer 3 (理論限界):      6.65 nines  (99.99997%)
  Layer 2 (ハードウェア限界): 5.91 nines  (99.999%)
  Layer 1 (ソフトウェア限界): 4.00 nines  (99.99%)

重大な発見

  8.5/10 CRITICAL  データベース単一リージョン障害
  カスケードパス:
  +-- DOWN PostgreSQL (プライマリ)
  +-- DOWN Application Server (接続拒否)

  7.2/10 CRITICAL  トラフィックスパイク (10倍)
  カスケードパス:
  +-- OVERLOADED nginx (LB)
  +-- DEGRADED Application Server
  +-- OVERLOADED PostgreSQL (コネクションプール枯渇)
```

## ステップ 4: Web ダッシュボードの起動

インタラクティブなWebダッシュボードを起動して、結果を視覚的に確認します:

```bash
faultray serve --port 8080
```

ブラウザで [http://localhost:8080](http://localhost:8080) を開きます。ダッシュボードには以下が含まれます:

- **依存関係グラフ** -- D3.jsによるインフラトポロジーのインタラクティブな可視化
- **シナリオエクスプローラー** -- 2,000以上のテスト済みシナリオを重大度でフィルタリング
- **可用性上限** -- 3層限界モデルのビジュアル表示
- **コスト影響** -- 推定ダウンタイムコストとSLAペナルティ

## ステップ 5: 高度なシミュレーションエンジンを試す

FaultRay は5つのシミュレーションエンジンを搭載しています。個別に実行してより深い分析が可能です:

```bash
# 日周トラフィックパターンでの動的シミュレーション（24時間サイクル）
faultray dynamic my-infra.yaml --traffic diurnal --duration 24h --step 1min

# What-If分析: MTTRが耐障害性にどう影響するか？
faultray whatif my-infra.yaml --parameter mttr_factor --values "0.5,1.0,2.0,4.0"

# 年間15%成長でのキャパシティプランニング
faultray capacity my-infra.yaml --growth 0.15 --slo 99.9

# 7日間の運用シミュレーション
faultray ops-sim my-infra.yaml --days 7 --step 5min
```

## 次のステップ

- [初めてのシミュレーション](first-simulation.md) -- シミュレーション結果の詳細な読み解き方
- [インストール](installation.md) -- Docker やクラウドプロバイダーサポートなどの代替インストール方法
- [CLIリファレンス](../cli/commands.md) -- 全コマンドのドキュメント
- [3層可用性モデル](../concepts/five-layer-model.md) -- FaultRay 独自の可用性上限の数学的証明を理解する
- [テンプレート](https://github.com/mattyopon/faultray/tree/main/src/faultray/templates) -- ビルトインインフラテンプレートの一覧
