# FaultRay - 仮想インフラ カオスエンジニアリング シミュレータ

## システム概要

---

### 概要

FaultRayは、実際のインフラに一切触れることなく、インフラ障害の連鎖的影響をシミュレーションする仮想カオスエンジニアリングツールである。インフラの依存関係グラフをモデル化し、150以上のカオスシナリオを自動生成・実行して、システムの脆弱性と障害連鎖リスクを可視化する。

### コンセプト

- **仮想シミュレーション**: 実インフラ・ステージング環境に影響を与えない。全てメモリ上で完結
- **依存関係グラフ分析**: NetworkXを用いた有向グラフでコンポーネント間の依存関係をモデル化
- **自動シナリオ生成**: 30カテゴリ・150以上のカオスシナリオを自動生成
- **セキュリティニュース連動**: 実際のセキュリティニュースからシナリオを自動追加
- **リスクスコアリング**: 影響度 x 拡散率 x 発生確率の3軸でリスクを定量評価

### 技術スタック

| カテゴリ | 技術 | 用途 |
|---------|------|------|
| 言語 | Python 3.11+ | メインランタイム |
| CLI | Typer + Rich | コマンドライン・ターミナル出力 |
| データモデル | Pydantic | バリデーション・シリアライゼーション |
| グラフ解析 | NetworkX | 依存関係グラフ・連鎖解析 |
| HTTP | httpx | 非同期HTTP通信（Prometheus・RSS） |
| Web | FastAPI + Jinja2 + D3.js | Webダッシュボード |
| メトリクス | psutil | ローカルシステムスキャン |
| 設定 | PyYAML | YAML定義ファイル読み込み |

---

## アーキテクチャ

### システム構成図

```
+------------------+     +------------------+     +------------------+
|  Discovery Layer |     |   Model Layer    |     | Simulator Layer  |
|                  | --> |                  | --> |                  |
| - Local Scanner  |     | - InfraGraph     |     | - ScenarioGen    |
| - Prometheus     |     | - Components     |     | - CascadeEngine  |
| - Terraform      |     | - Dependencies   |     | - SimEngine      |
| - YAML Loader    |     | - Save/Load JSON |     | - Feed Scenarios |
+------------------+     +------------------+     +------------------+
                                                          |
                         +------------------+     +------------------+
                         |    API Layer     | <-- |  Reporter Layer  |
                         |                  |     |                  |
                         | - FastAPI        |     | - CLI Report     |
                         | - D3.js Graph    |     | - HTML Report    |
                         | - Dashboard      |     | - SVG Diagram    |
                         +------------------+     +------------------+
```

### ディレクトリ構成

```
faultray/
  src/faultray/
    cli.py                 # CLIインターフェース（13コマンド）
    model/                 # インフラモデル定義
      components.py        # Component, Dependency, ResourceMetrics等
      graph.py             # InfraGraph（NetworkXラッパー）
      loader.py            # YAML読み込み
    discovery/             # インフラ検出
      scanner.py           # ローカルシステムスキャン
      prometheus.py        # Prometheusメトリクス連携
      terraform.py         # Terraform state/plan解析
    simulator/             # カオスシミュレーション
      scenarios.py         # 30カテゴリのシナリオ定義
      engine.py            # シミュレーション実行エンジン
      cascade.py           # 障害連鎖伝播エンジン
    feeds/                 # セキュリティニュースフィード
      sources.py           # 8つのRSS/Atomフィードソース
      fetcher.py           # フィード取得・パース
      analyzer.py          # インシデントパターン分析
      store.py             # シナリオ永続ストア
    reporter/              # レポート生成
      report.py            # CLI出力フォーマット
      html_report.py       # HTMLレポート生成
    api/                   # Webダッシュボード
      server.py            # FastAPIルーティング
      templates/           # Jinja2テンプレート
      static/              # CSS, D3.jsスクリプト
  tests/
    test_cascade.py        # カスケードテスト（16件）
    test_feeds.py          # フィードテスト（11件）
  examples/
    demo-infra.yaml        # YAMLインフラ定義例
    sample-tfstate.json    # Terraform state例
```

---

## データモデル

### コンポーネント種別

| 種別 | 値 | 例 |
|------|------|------|
| ロードバランサー | load_balancer | nginx, ALB, HAProxy |
| Webサーバー | web_server | Apache, Caddy |
| アプリサーバー | app_server | Express, Gunicorn, ECS Service |
| データベース | database | PostgreSQL, MySQL, RDS |
| キャッシュ | cache | Redis, Memcached, ElastiCache |
| キュー | queue | RabbitMQ, SQS, Kafka |
| ストレージ | storage | S3, EBS, NFS |
| DNS | dns | Route53, CoreDNS |
| 外部API | external_api | Stripe, Twilio |

### ヘルスステータス

| ステータス | 説明 |
|-----------|------|
| HEALTHY | 正常稼働 |
| DEGRADED | 劣化（応答遅延、一部機能停止） |
| OVERLOADED | 過負荷（処理能力の限界付近） |
| DOWN | 完全停止 |

### 依存関係の種類

| 種類 | 値 | 障害伝播の挙動 |
|------|------|------|
| 必須 | requires | 依存先DOWN → 自身もDOWN（レプリカなし時） |
| オプション | optional | 依存先DOWN → 自身はDEGRADED（停止しない） |
| 非同期 | async | 依存先DOWN → 遅延DEGRADED（キュー溜まり） |

### ResourceMetrics（リソースメトリクス）

| フィールド | 型 | 説明 |
|-----------|------|------|
| cpu_percent | float | CPU使用率 (0-100) |
| memory_percent | float | メモリ使用率 (0-100) |
| disk_percent | float | ディスク使用率 (0-100) |
| network_connections | int | 現在のネットワーク接続数 |
| open_files | int | オープンファイル数 |

### Capacity（キャパシティ制限）

| フィールド | 型 | 説明 |
|-----------|------|------|
| max_connections | int | 最大接続数 |
| max_rps | int | 最大リクエスト/秒 |
| connection_pool_size | int | 接続プールサイズ |
| max_memory_mb | int | 最大メモリ (MB) |
| max_disk_gb | int | 最大ディスク (GB) |
| timeout_seconds | float | タイムアウト秒数 |
| retry_multiplier | float | リトライ倍率 |

---

## CLIコマンド一覧

### インフラ検出

| コマンド | 説明 | 主要オプション |
|---------|------|------|
| **faultray scan** | ローカルシステム/Prometheusからインフラ検出 | --output, --hostname, --prometheus-url |
| **faultray load** | YAMLファイルからインフラ読み込み | YAML_FILE, --output |
| **faultray tf-import** | Terraform stateからインポート | --state, --dir, --output |

### シミュレーション

| コマンド | 説明 | 主要オプション |
|---------|------|------|
| **faultray simulate** | カオスシミュレーション実行 | --model, --html |
| **faultray demo** | デモインフラでシミュレーション実行 | --web, --host, --port |
| **faultray tf-plan** | Terraform planの変更影響分析 | PLAN_FILE, --dir, --html |

### レポート・表示

| コマンド | 説明 | 主要オプション |
|---------|------|------|
| **faultray show** | インフラモデルのサマリー表示 | --model |
| **faultray report** | HTMLレポート生成 | --model, --output |
| **faultray serve** | Webダッシュボード起動 | --model, --host, --port |

### セキュリティフィード

| コマンド | 説明 | 主要オプション |
|---------|------|------|
| **faultray feed-update** | セキュリティニュースからシナリオ自動生成 | --model, --timeout |
| **faultray feed-list** | 保存済みフィードシナリオ一覧表示 | なし |
| **faultray feed-sources** | 設定されたフィードソース一覧 | なし |
| **faultray feed-clear** | フィードシナリオストアのクリア | なし |

---

## カオスシナリオ

### 障害タイプ

| 障害タイプ | 値 | 直接効果 |
|-----------|------|------|
| コンポーネント停止 | component_down | DOWN |
| CPU飽和 | cpu_saturation | OVERLOADED |
| メモリ枯渇 | memory_exhaustion | DOWN (OOM) |
| ディスクフル | disk_full | DOWN |
| 接続プール枯渇 | connection_pool_exhaustion | DOWN |
| ネットワーク分断 | network_partition | DOWN |
| レイテンシスパイク | latency_spike | DEGRADED |
| トラフィックスパイク | traffic_spike | OVERLOADED |

### 自動生成シナリオ（30カテゴリ）

#### 単一障害シナリオ

| カテゴリ | 内容 | 生成数 |
|---------|------|------|
| 単一コンポーネント停止 | 各コンポーネントの完全停止 | N |
| CPU飽和 | 各コンポーネントのCPU 100% | N |
| メモリ枯渇 (OOM) | 各コンポーネントのメモリ使い切り | N |
| 接続プール枯渇 | DB/App/Cacheのプール使い切り | 該当数 |
| ディスクフル | DB/Storage/App/Queueのディスク満杯 | 該当数 |
| ネットワーク分断 | 各コンポーネントの完全隔離 | N |
| レイテンシスパイク (5x) | 各コンポーネントの応答遅延5倍 | N |
| DB高レイテンシ (20x) | DB応答遅延20倍 | DB数 |

#### トラフィックシナリオ

| カテゴリ | 内容 | 生成数 |
|---------|------|------|
| トラフィック 1.5x | 通常の1.5倍トラフィック | 1 |
| トラフィック 2x | 通常の2倍トラフィック | 1 |
| トラフィック 3x | 通常の3倍トラフィック | 1 |
| トラフィック 5x | 通常の5倍トラフィック | 1 |
| トラフィック 10x | DDoSレベル10倍トラフィック | 1 |

#### 複合障害シナリオ

| カテゴリ | 内容 | 生成数 |
|---------|------|------|
| ペア障害 | 全2コンポーネント組み合わせの同時障害 | C(N,2) |
| トリプル障害 | 全3コンポーネント組み合わせの同時障害 | C(N,3) |
| コンポーネント停止 + トラフィック | 1台停止 + 2x/3xトラフィック | N x 2 |
| キャッシュスタンピード | キャッシュ停止 + 2x/5xトラフィック | Cache数 x 2 |

#### インフラ種別特化シナリオ

| カテゴリ | 内容 | 対象 |
|---------|------|------|
| DBログ爆発 | トランザクションログの異常増大 | database |
| DBレプリケーション遅延 | レプリカの同期遅延 | database |
| DB接続嵐 | 接続プール枯渇+リトライ嵐 | database |
| DBロック競合 | テーブルロックによる全クエリブロック | database |
| キューバックプレッシャー | メッセージ処理追いつかず蓄積 | queue |
| ポイズンメッセージ | 処理不能メッセージによるキュー詰まり | queue |
| LBヘルスチェック失敗 | 全バックエンドのヘルスチェック失敗 | load_balancer |
| TLS証明書期限切れ | SSL/TLS証明書の有効期限切れ | load_balancer |
| LB設定リロード失敗 | 設定変更失敗によるLBダウン | load_balancer |
| メモリリーク | 徐々にメモリを消費するリーク | app_server |
| スレッドプール枯渇 | ワーカースレッドの使い切り | app_server |
| GCポーズ | GC Full発生による一時停止 | app_server |
| 不良デプロイ | バグを含むデプロイメント | app_server |
| キャッシュエビクション嵐 | メモリ圧迫による大量キー退避 | cache |
| キャッシュスプリットブレイン | レプリカ間の不整合 | cache |

#### 大規模障害シナリオ

| カテゴリ | 内容 | 生成数 |
|---------|------|------|
| ゾーン障害 | 同一ホスト上の全コンポーネント同時停止 | ホスト数 |
| ティア間ネットワーク分断 | App-DB、App-Cache、LB-App間の通信断 | 3 |
| カスケードタイムアウト連鎖 | DB遅延→App タイムアウト→504応答 | 1 |
| 全インフラ崩壊 | 全コンポーネント同時停止 | 1 |
| ノイジーネイバー | 1プロセスが他のリソースを圧迫 | App数 |
| ピーク時DB遅延 | 3xトラフィック中のDB応答遅延 | DB数 |
| ローリングリスタート失敗 | デプロイ中にApp半数停止 | 1 |
| 全リソース枯渇 | CPU+メモリ+ディスク全て逼迫 | App数 |
| フェイルオーバーテスト | プライマリ障害時のフェイルオーバー検証 | 該当DB数 |
| ブラックフライデー | 10xトラフィック+キャッシュ圧力 | 1 |

### デモ構成（6コンポーネント）での実績

デフォルトシナリオ: **124件**、フィード追加: **26件**、合計: **150件**

---

## リスクスコアリング

### 重要度スコア (0.0 - 10.0)

#### 計算式

```
impact_score = (DOWN数 x 1.0 + OVERLOADED数 x 0.5 + DEGRADED数 x 0.25) / 影響コンポーネント数
spread_score = 影響コンポーネント数 / 全コンポーネント数
raw_score = impact_score x spread_score x 10.0
final_score = raw_score x likelihood
```

#### スコアキャップ

| 条件 | 最大スコア |
|------|------|
| 影響が自身のみ（連鎖なし）、DOWN | 3.0 |
| 影響が自身のみ、OVERLOADED | 2.0 |
| 影響が自身のみ、DEGRADED | 1.5 |
| 全体の30%未満に波及 | 6.0 |
| DEGRADEDのみ（DOWNなし） | 4.0 |
| 全体の30%以上に波及 | 10.0 |

#### リスクレベル分類

| レベル | スコア範囲 | 表示 |
|-------|------|------|
| CRITICAL | 7.0 - 10.0 | 赤色で警告表示 |
| WARNING | 4.0 - 6.9 | 黄色で警告表示 |
| PASSED | 0.0 - 3.9 | 低リスクとして記録 |

### 発生確率 (Likelihood: 0.2 - 1.0)

現在のメトリクスに基づき、各障害シナリオの発生確率を算出する。

| 障害タイプ | 条件 | 確率 |
|-----------|------|------|
| ディスクフル | 使用率 >90% | 1.0（切迫） |
| ディスクフル | 使用率 >75% | 0.7 |
| ディスクフル | 使用率 >50% | 0.4 |
| ディスクフル | 使用率 <50% | 0.2（低い） |
| 接続プール枯渇 | 使用率 >90% | 1.0（切迫） |
| 接続プール枯渇 | 使用率 >70% | 0.7 |
| CPU飽和 | 使用率 >85% | 1.0 |
| CPU飽和 | 使用率 >60% | 0.6 |
| メモリ枯渇 | 使用率 >85% | 1.0 |
| コンポーネント停止 | 常時 | 0.8（ハードウェア障害は常に可能） |
| レイテンシスパイク | 常時 | 0.7（頻繁に発生） |
| トラフィックスパイク | 常時 | 0.5（可能性あり） |

### レジリエンススコア (0 - 100)

システム全体の耐障害性を0-100で評価する。

#### 減点要因

| 要因 | 減点 |
|------|------|
| 単一障害点（レプリカ1、依存先あり） | -5 ~ -20 |
| 高使用率（70%超え） | -3 ~ -15 |
| 深い依存チェーン（5ホップ超） | -(深さ-5) x 5 |

---

## セキュリティニュースフィード連携

### 概要

実世界のセキュリティインシデント情報をRSS/Atomフィードから自動取得し、カオスシナリオに変換する。これにより、最新の脅威トレンドを反映したシミュレーションが可能になる。

### データフロー

```
RSS/Atom Feeds  -->  Fetcher  -->  Analyzer  -->  Store  -->  SimEngine
  (8ソース)       (httpx非同期)  (パターン     (~/.faultray/  (自動マージ)
                               マッチング)    feed-scenarios.json)
```

### フィードソース（8件）

| ソース | URL | 種別 |
|-------|------|------|
| CISA Alerts | cisa.gov/cybersecurity-advisories | RSS |
| NIST NVD | nvd.nist.gov/feeds/xml/cve | RSS |
| The Hacker News | feedburner.com/TheHackersNews | RSS |
| BleepingComputer | bleepingcomputer.com/feed | RSS |
| AWS Security Bulletins | aws.amazon.com/security/security-bulletins | Atom |
| Google Cloud Incidents | status.cloud.google.com | Atom |
| Krebs on Security | krebsonsecurity.com/feed | RSS |
| Ars Technica Security | feeds.arstechnica.com/arstechnica/security | RSS |

### インシデントパターン（18種）

| パターン | 検出キーワード例 | 変換先障害タイプ |
|---------|------|------|
| DDoS 体積型攻撃 | ddos, traffic flood, syn flood | TRAFFIC_SPIKE (10x) |
| アプリ層 DDoS | layer 7, slowloris, request flood | POOL_EXHAUSTION + CPU |
| クラウド障害 | aws outage, region down | COMPONENT_DOWN + NETWORK |
| DNS障害 | dns failure, dns hijack | COMPONENT_DOWN |
| DB破損 | data loss, replication fail | COMPONENT_DOWN + DISK |
| DB接続嵐 | connection exhaust, pool limit | POOL_EXHAUSTION |
| メモリリーク | memory leak, oom, heap exhaust | MEMORY_EXHAUSTION |
| TLS証明書障害 | certificate expir, ssl fail | COMPONENT_DOWN |
| ネットワーク分断 | split brain, bgp hijack, fiber cut | NETWORK_PARTITION |
| ストレージ障害 | disk full, ebs fail, io error | DISK_FULL |
| キャッシュ障害 | redis crash, cache stampede | COMPONENT_DOWN + MEMORY |
| キュー障害 | kafka fail, message lost | COMPONENT_DOWN |
| CPU乗っ取り | cryptojack, resource hijack | CPU_SATURATION |
| サプライチェーン | supply chain, npm malicious | COMPONENT_DOWN + LATENCY |
| ランサムウェア | ransomware, lockbit | COMPONENT_DOWN + DISK |
| レイテンシ劣化 | latency spike, timeout increase | LATENCY_SPIKE |
| K8s障害 | kubernetes vuln, pod crash | COMPONENT_DOWN + CPU |
| カスケード障害 | cascading fail, retry storm | DOWN + LATENCY + POOL |

### 自動更新の仕組み

1. `faultray feed-update` を実行
2. 8つのRSS/Atomフィードを並列取得（httpx非同期）
3. 記事タイトル+サマリーに対して18パターンのキーワードマッチング実施
4. マッチした記事からインシデントパターンを抽出、信頼度スコア算出
5. インシデントをカオスシナリオに変換（コンポーネント種別マッピング付き）
6. `~/.faultray/feed-scenarios.json` に永続保存（重複排除付きマージ）
7. 次回の `faultray simulate` 実行時にデフォルトシナリオと自動統合

---

## インフラ検出

### ローカルシステムスキャン

psutilを使用してローカルマシンのサービスを自動検出する。

- リスニングポートからサービス種別を推定（5432→PostgreSQL、6379→Redis等）
- 確立済み接続から依存関係を推定
- CPU/メモリ/ディスク/接続数のメトリクスを取得

### Prometheus連携

Prometheusサーバーに対してPromQLクエリを実行し、メトリクスを取得する。

| メトリクス | PromQLクエリ |
|-----------|------|
| CPU使用率 | 100 - avg by(instance)(rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100 |
| メモリ使用率 | (1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100 |
| ディスク使用率 | (1 - node_filesystem_avail_bytes / node_filesystem_size_bytes) * 100 |
| 接続数 | node_netstat_Tcp_CurrEstab |

### Terraform連携

#### 対応リソース（50種以上）

| Terraformリソース | マッピング先 |
|---------|------|
| aws_lb / aws_alb / aws_elb | LOAD_BALANCER |
| aws_ecs_service / aws_lambda_function | APP_SERVER |
| aws_db_instance / aws_rds_cluster | DATABASE |
| aws_elasticache_cluster | CACHE |
| aws_sqs_queue | QUEUE |
| aws_s3_bucket | STORAGE |
| aws_route53_zone | DNS |
| google_compute_instance | APP_SERVER |
| azurerm_virtual_machine | APP_SERVER |

#### Terraform Plan リスク評価

| 変更内容 | リスクスコア |
|---------|------|
| リソース削除 | 8-10 |
| 置換（create + delete） | 9 |
| DB変更（削除以外） | 6-8 |
| DB削除 | 10 |
| インスタンスタイプ変更 | 6-7 |
| スケールダウン | 5 |

---

## Webダッシュボード

### エンドポイント一覧

| パス | メソッド | 説明 |
|------|------|------|
| / | GET | メインダッシュボード |
| /components | GET | コンポーネント一覧 |
| /simulation | GET | シミュレーション結果 |
| /graph | GET | D3.jsインタラクティブグラフ |
| /demo | GET | デモデータ読み込み |
| /simulation/run | GET | シミュレーション実行（JSON） |
| /api/simulate | POST | シミュレーション実行（JSON） |
| /api/graph-data | GET | グラフデータ取得（JSON） |

### UIの特徴

- ダークテーマ（Grafana風）
- D3.js力学グラフによるインタラクティブな依存関係可視化
- コンポーネント種別ごとの色分け
- レジリエンススコアゲージ
- リアルタイムシミュレーション結果表示

---

## 使い方

### クイックスタート

#### デモ実行（最も簡単）

```bash
pip install -e .
faultray demo
```

#### YAML定義からシミュレーション

```bash
faultray load examples/demo-infra.yaml
faultray simulate --html report.html
```

#### Terraformからインポート

```bash
# stateファイルから
faultray tf-import --state terraform.tfstate

# ライブ環境から
faultray tf-import --dir /path/to/terraform

# planの影響分析
terraform plan -out=plan.out
faultray tf-plan plan.out --html plan-report.html
```

#### セキュリティフィード更新

```bash
faultray feed-update --model faultray-model.json
faultray feed-list
faultray simulate  # フィードシナリオも自動統合
```

#### Webダッシュボード

```bash
faultray serve --model faultray-model.json --port 8080
# ブラウザで http://localhost:8080 を開く
```

### YAML定義ファイルの書き方

```yaml
components:
  - id: nginx
    name: "nginx (LB)"
    type: load_balancer
    host: web01
    port: 443
    replicas: 2
    metrics:
      cpu_percent: 25
      memory_percent: 30
    capacity:
      max_connections: 10000

  - id: postgres
    name: "PostgreSQL"
    type: database
    host: db01
    port: 5432
    replicas: 1
    metrics:
      cpu_percent: 45
      memory_percent: 80
      disk_percent: 72
    capacity:
      max_connections: 100
      connection_pool_size: 100

dependencies:
  - source: nginx
    target: app-server
    type: requires
    weight: 1.0

  - source: app-server
    target: redis
    type: optional
    weight: 0.7
```

---

## テスト

### テストカバレッジ

全27テスト:

#### カスケードテスト（16件）

- コンポーネント停止の連鎖伝播
- 接続プール枯渇の影響
- オプション依存の連鎖制限
- トラフィックスパイクの影響
- 重要度スコア計算
- 孤立コンポーネントの非連鎖
- グラフレジリエンススコア
- グラフ保存・読み込み
- 非連鎖障害の低スコア
- 全連鎖障害の高スコア
- オプション vs 必須依存のスコア比較
- 複合障害シナリオ
- ディスクフルの常時DOWN
- 低使用率時の低リスク
- total_componentsコンテキスト
- DEGRADED専用キャップ

#### フィードテスト（11件）

- DDoS記事の検出
- ランサムウェア記事の検出
- メモリリーク記事の検出
- 無関係記事の非マッチ
- 複数パターン同時検出
- 汎用シナリオ生成
- コンポーネント種別マッピング
- ストアの保存・読み込み
- ストアの重複排除
- ストアのクリア
- 信頼度スコアリング

---

## 他ツールとの比較

| 特徴 | FaultRay | Gremlin | Chaos Monkey | Litmus | securiCAD |
|------|---------|---------|------|------|------|
| 実インフラへの影響 | なし（完全仮想） | あり（実障害注入） | あり（実障害注入） | あり（K8s上実行） | なし（モデル） |
| セットアップ | pip install | エージェント必要 | AWS統合必要 | K8s必要 | 企業契約必要 |
| 対象 | 任意のインフラ | クラウド/コンテナ | AWS | Kubernetes | ITインフラ |
| 分析方式 | 依存グラフ+連鎖 | 実験結果 | 実験結果 | 実験結果 | 攻撃パスモデル |
| コスト | 無料（OSS） | 有料SaaS | OSS | OSS | 有料 |
| 安全性 | 最高（仮想） | リスクあり | リスクあり | リスクあり | 高（モデル） |
| ニュースフィード連携 | あり | なし | なし | なし | なし |
| Terraform連携 | あり | なし | なし | なし | なし |

### FaultRayの独自価値

- **ゼロリスク**: 実環境に一切触れないため、本番環境でも安全に使用可能
- **高速**: メモリ上のシミュレーションのため秒単位で完了
- **自動更新**: セキュリティニュースから最新脅威シナリオを自動追加
- **Terraform統合**: IaCからの自動インポートとplan影響分析
- **依存関係可視化**: D3.jsによるインタラクティブグラフ
