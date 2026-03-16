# FaultRay プロダクト化ハンドオフプロンプト v3

> **目的**: FaultRayを「売れるプロダクト」にするための非機能要件・UX・インテグレーション改善
> **前提**: v2（エンジン追加）と並行または後続で実施
> **焦点**: コードの機能ではなく「使ってもらえる状態」にすること
> **作成日**: 2026-03-15

---

## プロンプト（以下をそのまま別セッションのエージェントに渡す）

FaultRay（旧FaultRay）を「売れるプロダクト」にするための改善を実装してください。
エンジン追加（v2プロンプト）とは別の軸で、**プロダクトとしての完成度**を上げる作業です。

**プロジェクトパス**: /home/user/projects/tools/faultray/

---

## 現在の状態（すでにあるもの）

実装前に必ず現状を把握すること。想像以上に土台がある。

### Web UI（すでにある）
- **FastAPI + Jinja2 SSR** でダッシュボードが動作中
- **6ページ**: Dashboard / Components / Simulation / Graph / Analyze / Demo
- **D3.js** による力学モデルのインタラクティブ依存グラフ（ズーム/パン/ホバー/クリック）
- **ダークテーマ（Grafana風）**: 1,735行のCSS、アニメーション付き
- テンプレート: `src/faultray/api/templates/` (base.html, dashboard.html, components.html, simulation.html, graph.html, analyze.html)
- スタイル: `src/faultray/api/static/style.css`
- グラフJS: `src/faultray/api/static/graph.js`

### 認証・マルチテナント（すでにある）
- **OAuth2 SSO**: GitHub / Google 対応済み
- **API Key認証**: Bearer token + SHA-256ハッシュ保存
- **マルチテナント**: teams → users → projects → simulation_runs のDB構造
- **監査ログ**: 全APIアクションをaudit_logsテーブルに記録
- **レート制限**: 60 req/60s per IP
- 後方互換: ユーザーゼロなら認証なしで動作

### インテグレーション（すでにある）
- **Slack**: 構造化ブロック通知（Resilience Score + 重大度別カウント）
- **PagerDuty**: Critical検出時にイベント送信（Events API v2）
- **Prometheus**: メトリクス自動取得 + コンポーネント自動検出
- **Terraform**: .tfstate パース（AWS 17種 / GCP 7種 / Azure 7種 = 31リソースタイプ対応）
- **Generic Webhook**: 任意URLへJSON POST
- **ローカルスキャン**: psutilベースのプロセス/ポート/接続自動検出

### データベース（すでにある）
- **SQLite + SQLAlchemy 2.0 + aiosqlite**
- テーブル: teams, users, projects, simulation_runs, audit_logs

---

## 改善カテゴリ 1: Webダッシュボードの本番品質化【最重要】

### 現状の課題
現在のJinja2 SSRは**機能的には動く**が、SaaS顧客に月額課金するレベルではない。
ただし、**フルSPA化は過剰投資**。Jinja2 + htmx + Alpine.js で十分プロダクト品質になる。

### 1-1. ダッシュボード強化
**ファイル**: `src/faultray/api/templates/dashboard.html`（既存を大幅改修）

現在のダッシュボードに以下を追加:

#### a) リアルタイムスコアカード（トップ）
```html
<!-- 4つのメインスコアを横並びカードで表示 -->
<div class="score-grid">
  <div class="score-card">
    <div class="score-ring" data-value="73">73</div>
    <div class="score-label">Resilience Score</div>
    <div class="score-trend">↑ +5 from last run</div>
  </div>
  <div class="score-card">
    <div class="score-ring security" data-value="61">61</div>
    <div class="score-label">Security Score</div>
  </div>
  <div class="score-card">
    <div class="score-value">$2.4M</div>
    <div class="score-label">Annual Risk Exposure</div>
  </div>
  <div class="score-card">
    <div class="score-value">3.92</div>
    <div class="score-label">Availability (Nines)</div>
  </div>
</div>
```

#### b) シミュレーション履歴タイムライン
- 過去のシミュレーション結果をタイムラインで表示
- スコアの推移グラフ（SVGまたはChart.js CDN）
- 各実行をクリックで詳細展開

#### c) トップリスク一覧
- 最も影響の大きいシナリオ Top 5
- コスト影響額付き（Cost Engine連携）
- ワンクリックで詳細シミュレーション結果へ

#### d) コンプライアンス準拠率ゲージ
- DORA / SOC2 / ISO 等の準拠率を円形ゲージで表示
- 赤/黄/緑の3色で直感的に

### 1-2. インタラクティブ強化（htmx + Alpine.js 導入）
**ファイル**: `src/faultray/api/templates/base.html`（既存を修正）

```html
<!-- CDNから読み込み。ビルドステップ不要 -->
<script src="https://unpkg.com/htmx.org@2.0.4"></script>
<script src="https://unpkg.com/alpinejs@3.14.8/dist/cdn.min.js" defer></script>
```

- **htmx**: ページ全体リロードなしでサーバーからHTMLフラグメントを取得
  - シミュレーション実行 → 結果だけ差し替え（フルページリロードなし）
  - フィルタ変更 → テーブルだけ更新
  - ポーリング → 実行中のシミュレーション進捗をリアルタイム表示
- **Alpine.js**: UIのトグル/タブ/モーダル等のクライアントサイド状態管理
  - ドロップダウンメニュー
  - モーダルダイアログ（シナリオ詳細）
  - タブ切り替え（コンソール/グラフ/テーブル）

### 1-3. 新ページ追加

#### Cost Impact ページ
**ファイル**: `src/faultray/api/templates/cost.html`（新規）
- 障害シナリオごとの損失額ランキング（棒グラフ）
- 年間リスクエクスポージャーの内訳（ドーナツチャート）
- 「対策前 vs 対策後」の比較表
- ROI計算器（対策コスト入力 → リスク削減額を自動計算）

#### Security ページ
**ファイル**: `src/faultray/api/templates/security.html`（新規）
- セキュリティ耐性スコアの内訳
- 攻撃カスケードの可視化（D3.jsで赤いパスをハイライト）
- 防御カバレッジマトリクス（攻撃タイプ × 防御策）
- MITRE ATT&CK マッピング表

#### Compliance ページ
**ファイル**: `src/faultray/api/templates/compliance.html`（新規）
- フレームワーク選択（DORA / SOC2 / ISO / PCI / NIST）
- 準拠率のゲージ + 要件ごとの PASS/FAIL/N/A 一覧
- ギャップ分析: 不合格項目の修正推奨
- PDFエクスポートボタン（監査提出用）

#### Reports ページ
**ファイル**: `src/faultray/api/templates/reports.html`（新規）
- 生成済みレポート一覧
- HTML/PDF/JSON/CSVダウンロード
- 定期レポート設定（将来のSaaS版向けスタブ）

#### Settings ページ
**ファイル**: `src/faultray/api/templates/settings.html`（新規）
- プロジェクト設定（名前、通知先）
- インテグレーション設定（Slack/PagerDuty/OpsGenie webhook URL）
- API Key管理（生成/失効）
- チームメンバー管理

### 1-4. サイドバーナビゲーション更新
**ファイル**: `src/faultray/api/templates/base.html`（既存を修正）

```
サイドバー構成:
├── 📊 Dashboard（既存改修）
├── 🏗️ Infrastructure
│   ├── Components（既存）
│   └── Dependency Graph（既存）
├── ⚡ Simulation
│   ├── Chaos Simulation（既存改修）
│   ├── Security Analysis（新規）
│   └── Cost Impact（新規）
├── 📋 Compliance
│   ├── Framework Check（新規）
│   └── Reports（新規）
├── 🤖 AI Analysis（既存）
├── ⚙️ Settings（新規）
└── 📖 Documentation（外部リンク）
```

### 1-5. APIエンドポイント追加
**ファイル**: `src/faultray/api/server.py`（既存を拡張）

```python
# 新ページ用のHTMLルート
@app.get("/cost")          # Cost Impact ページ
@app.get("/security")      # Security Analysis ページ
@app.get("/compliance")    # Compliance ページ
@app.get("/reports")       # Reports ページ
@app.get("/settings")      # Settings ページ

# htmx用のHTMLフラグメントエンドポイント（部分更新）
@app.get("/htmx/simulation-results")   # シミュレーション結果フラグメント
@app.get("/htmx/score-cards")          # スコアカード更新
@app.get("/htmx/risk-table")           # リスクテーブル更新
@app.post("/htmx/run-simulation")      # シミュレーション実行（進捗表示付き）

# JSON API追加
@app.get("/api/cost-analysis")         # コスト影響分析結果
@app.get("/api/security-score")        # セキュリティスコア
@app.get("/api/compliance/{framework}") # コンプライアンスチェック結果
@app.get("/api/score-history")         # スコア履歴（トレンド用）
```

---

## 改善カテゴリ 2: インテグレーション拡張

### 2-1. OpsGenie 連携
**ファイル**: `src/faultray/integrations/opsgenie.py`（新規）

```python
class OpsGenieIntegration:
    """Atlassian OpsGenie alert integration."""

    def __init__(self, api_key: str, base_url: str = "https://api.opsgenie.com"):
        self.api_key = api_key
        self.base_url = base_url

    async def create_alert(
        self,
        message: str,
        description: str,
        priority: str = "P3",  # P1-P5
        tags: list[str] | None = None,
        details: dict | None = None,
    ) -> dict:
        """POST /v2/alerts"""

    async def close_alert(self, alert_id: str) -> dict:
        """POST /v2/alerts/{id}/close"""
```

- Critical検出時にP1/P2アラート自動送信
- CLIフラグ: `--opsgenie-key`

### 2-2. Datadog 連携
**ファイル**: `src/faultray/integrations/datadog.py`（新規）

```python
class DatadogIntegration:
    """Datadog metrics and events integration."""

    def __init__(self, api_key: str, app_key: str, site: str = "datadoghq.com"):
        ...

    async def send_event(self, title: str, text: str, alert_type: str, tags: list[str]) -> dict:
        """POST /api/v1/events — シミュレーション結果をDatadogイベントとして送信"""

    async def submit_metrics(self, metrics: list[dict]) -> dict:
        """POST /api/v2/series — Resilience Score等をカスタムメトリクスとして送信"""
        # メトリクス例:
        # faultray.resilience_score: 73.0
        # faultray.security_score: 61.0
        # faultray.annual_risk_exposure: 2400000.0
        # faultray.availability_nines: 3.92

    async def fetch_metrics(self, query: str, from_ts: int, to_ts: int) -> dict:
        """GET /api/v1/query — Datadogからメトリクスを取得してインフラモデルに反映"""
```

- Datadogのメトリクスを取得してInfraGraphの利用率を更新（Prometheus同等）
- シミュレーション結果をDatadogのカスタムメトリクスとして送信 → 既存ダッシュボードで可視化

### 2-3. Grafana 連携
**ファイル**: `src/faultray/integrations/grafana.py`（新規）

```python
class GrafanaIntegration:
    """Grafana dashboard and annotation integration."""

    async def create_annotation(self, dashboard_id: int, text: str, tags: list[str]) -> dict:
        """POST /api/annotations — シミュレーション実行をGrafanaアノテーションとして記録"""

    async def import_dashboard(self) -> dict:
        """POST /api/dashboards/db — FaultRay専用ダッシュボードをGrafanaにインポート"""
```

- シミュレーション結果をGrafanaのアノテーションとしてタイムラインに表示
- FaultRay専用Grafanaダッシュボード JSON定義を同梱（`examples/grafana-dashboard.json`）

### 2-4. Jira / Linear 連携
**ファイル**: `src/faultray/integrations/issue_tracker.py`（新規）

```python
class JiraIntegration:
    async def create_issue(self, project_key: str, summary: str, description: str, priority: str) -> dict:
        """Critical/High の脆弱性を自動でJiraチケット化"""

class LinearIntegration:
    async def create_issue(self, team_id: str, title: str, description: str, priority: int) -> dict:
        """同上、Linear版"""
```

- セキュリティ/コンプライアンスのFAIL項目を自動チケット化
- 「FaultRay: [CRITICAL] SPOFが検出されました — api-server」のようなチケットが自動作成される

### 2-5. AWS / GCP / Azure メトリクス取得
**ファイル**: `src/faultray/discovery/cloud_metrics.py`（新規）

```python
class AWSCloudWatchDiscovery:
    """CloudWatch メトリクスからインフラ状態を取得"""
    async def fetch_metrics(self, namespace: str, metric_name: str, dimensions: list) -> list:
        """boto3.client('cloudwatch').get_metric_data()"""

    async def discover_from_cloudwatch(self) -> InfraGraph:
        """CloudWatchのアクティブメトリクスからコンポーネントを自動検出"""

class GCPMonitoringDiscovery:
    """Cloud Monitoring メトリクス取得"""
    ...

class AzureMonitorDiscovery:
    """Azure Monitor メトリクス取得"""
    ...
```

- Prometheus がない環境でも、クラウドネイティブのメトリクスAPIからインフラ状態を取得
- CLIフラグ: `--cloudwatch-region ap-northeast-1`
- 既存の `discovery/` パッケージに自然に統合

### 2-6. webhooks.py の統合リファクタ
**ファイル**: `src/faultray/integrations/webhooks.py`（既存を拡張）

```python
class NotificationManager:
    """全通知チャネルの統合管理"""

    def __init__(self):
        self.channels: list[NotificationChannel] = []

    def add_slack(self, webhook_url: str): ...
    def add_pagerduty(self, routing_key: str): ...
    def add_opsgenie(self, api_key: str): ...
    def add_datadog(self, api_key: str, app_key: str): ...
    def add_jira(self, base_url: str, email: str, token: str): ...
    def add_generic(self, url: str): ...

    async def notify_all(self, event: SimulationEvent):
        """全登録チャネルに並行通知（個別エラーは握りつぶさない）"""
        results = await asyncio.gather(
            *[ch.send(event) for ch in self.channels],
            return_exceptions=True
        )
```

- 通知設定をSettings画面からUI管理できるように
- DB永続化（integrations テーブル追加）

---

## 改善カテゴリ 3: SaaS化の土台強化

### 3-1. 課金基盤のスタブ
**ファイル**: `src/faultray/api/billing.py`（新規）

**注意**: 実際のStripe統合はまだ不要。まず課金モデルの**データ構造とAPI**だけ定義。

```python
class PricingTier(str, Enum):
    FREE = "free"           # 5コンポーネント / 月10回シミュレーション
    PRO = "pro"             # 50コンポーネント / 無制限シミュレーション / コンプライアンスレポート
    ENTERPRISE = "enterprise"  # 無制限 / Insurance API / SSOカスタム / SLA保証

@dataclass
class UsageLimits:
    max_components: int
    max_simulations_per_month: int
    compliance_reports: bool
    insurance_api: bool
    custom_sso: bool
    support_sla: str  # "community" / "email_24h" / "dedicated_1h"

TIER_LIMITS = {
    PricingTier.FREE: UsageLimits(5, 10, False, False, False, "community"),
    PricingTier.PRO: UsageLimits(50, -1, True, False, False, "email_24h"),
    PricingTier.ENTERPRISE: UsageLimits(-1, -1, True, True, True, "dedicated_1h"),
}

class UsageTracker:
    """利用量のトラッキング（課金判定用）"""
    async def track_simulation(self, team_id: str): ...
    async def check_limit(self, team_id: str, resource: str) -> bool: ...
    async def get_usage(self, team_id: str) -> dict: ...
```

- DBに `subscriptions` テーブルと `usage_logs` テーブルを追加
- 各APIエンドポイントで `check_limit()` を呼び出し、超過時は 402 Payment Required
- Stripe Webhookのスタブエンドポイント: `POST /api/billing/webhook`

### 3-2. マルチテナント強化
**ファイル**: `src/faultray/api/database.py`（既存を拡張）

```python
# 新テーブル
class Subscription(Base):
    __tablename__ = "subscriptions"
    id: str
    team_id: str
    tier: str          # free / pro / enterprise
    status: str        # active / canceled / past_due
    started_at: datetime
    expires_at: datetime | None

class UsageLog(Base):
    __tablename__ = "usage_logs"
    id: str
    team_id: str
    resource_type: str  # "simulation" / "component" / "api_call"
    count: int
    period: str         # "2026-03"
    created_at: datetime

class IntegrationConfig(Base):
    __tablename__ = "integration_configs"
    id: str
    team_id: str
    provider: str       # "slack" / "pagerduty" / "opsgenie" / "datadog" / "jira"
    config_json: str    # 暗号化された設定値
    enabled: bool
    created_at: datetime
```

### 3-3. APIバージョニング
**ファイル**: `src/faultray/api/server.py`（既存を修正）

```python
# /api/ → /api/v1/ にバージョニング
# 既存の /api/* は /api/v1/* にリダイレクト（後方互換）
v1_router = APIRouter(prefix="/api/v1")

# OpenAPI仕様を充実させる（顧客のAPI統合用）
app.title = "FaultRay API"
app.version = "1.0.0"
app.description = "Infrastructure Resilience Intelligence Platform API"
```

---

## 改善カテゴリ 4: 精度実証フレームワーク

### 4-1. バックテストエンジン
**ファイル**: `src/faultray/simulator/backtest_engine.py`（新規）

過去の実際の障害とFaultRayのシミュレーション結果を比較して精度を検証する。

```python
@dataclass
class RealIncident:
    """実際に発生した障害の記録"""
    incident_id: str
    timestamp: str
    failed_component: str              # 障害が起きたコンポーネント
    actual_affected_components: list[str]  # 実際に影響を受けたコンポーネント
    actual_downtime_minutes: float
    actual_severity: str               # "critical" / "high" / "medium" / "low"
    root_cause: str
    recovery_actions: list[str]

@dataclass
class BacktestResult:
    """バックテスト結果"""
    incident: RealIncident

    # FaultRayの予測
    predicted_affected: list[str]
    predicted_severity: float
    predicted_downtime_minutes: float

    # 精度メトリクス
    precision: float      # 予測した影響コンポーネントのうち、実際に影響を受けた割合
    recall: float         # 実際に影響を受けたコンポーネントのうち、予測できた割合
    f1_score: float
    downtime_error_percent: float  # ダウンタイム予測の誤差率

class BacktestEngine:
    def run_backtest(
        self,
        graph: InfraGraph,
        incidents: list[RealIncident],
    ) -> list[BacktestResult]:
        """
        各実際の障害について:
        1. 障害コンポーネントをDOWNにするシナリオを生成
        2. CascadeEngineでカスケード分析を実行
        3. 予測結果と実際の結果を比較
        4. Precision/Recall/F1を算出
        """
```

#### CLIコマンド
```bash
# 過去の障害記録JSONを食わせてバックテスト
faultray backtest <infra.yaml> --incidents incidents.json

# 出力例:
# Backtest Results (5 incidents):
#   Incident 2025-11-03 DB failure:  Precision=0.92  Recall=0.85  F1=0.88
#   Incident 2025-12-15 LB failure:  Precision=1.00  Recall=0.78  F1=0.88
#   ...
#   Overall F1: 0.87 (87% accuracy)
```

#### incidents.json フォーマット
```json
[
  {
    "incident_id": "INC-2025-001",
    "timestamp": "2025-11-03T14:30:00Z",
    "failed_component": "aurora-primary",
    "actual_affected_components": ["pgbouncer", "hono-api-1", "hono-api-2", "hono-api-3"],
    "actual_downtime_minutes": 23,
    "actual_severity": "critical",
    "root_cause": "Storage full",
    "recovery_actions": ["failover to replica", "disk expansion"]
  }
]
```

**これが最も重要な機能**。「FaultRayの予測精度は F1=0.87」と言えれば、信頼性の実証になる。

### 4-2. 継続的バリデーション
**ファイル**: `src/faultray/validator/continuous.py`（新規）

Prometheus等の実メトリクスと定期的に照合して予測精度を改善。

```python
class ContinuousValidator:
    """実メトリクスとシミュレーション予測の継続的比較"""

    async def validate_utilization(self, graph: InfraGraph, prometheus_url: str) -> dict:
        """
        FaultRayのモデル上の利用率と、Prometheusの実測値を比較。
        乖離が大きいコンポーネントをリストアップ。
        """

    async def validate_availability(self, graph: InfraGraph, uptime_data: dict) -> dict:
        """
        FaultRayの可用性モデル出力と、実際のSLI実績値を比較。
        """

    def generate_accuracy_report(self) -> dict:
        """精度レポート: 予測値 vs 実測値の散布図データ"""
```

---

## 改善カテゴリ 5: デモ・オンボーディング強化

### 5-1. インタラクティブデモ
**ファイル**: `src/faultray/api/templates/demo.html`（既存を大幅改修）

現在の `/demo` ページを、**セールスデモとして使える品質**に。

```
デモフロー（ガイド付き）:
1. 「サンプルインフラをロード」ボタン → Xclone-v2相当の38コンポーネント構成
2. ダッシュボードにスコア表示 → 「Resilience Score: 73/100」
3. 「障害を注入」ボタン → DB障害シナリオを実行
4. カスケード可視化 → D3.jsグラフで赤いパスがアニメーション表示
5. 「修正を適用」ボタン → サーキットブレーカー追加
6. 再シミュレーション → 「Resilience Score: 89/100 (↑16)」
7. 「レポートをダウンロード」→ DORA準拠HTMLレポート

所要時間: 3分で価値が伝わる
```

### 5-2. サンプルインフラ拡充
**ファイル**: `examples/` ディレクトリに追加

```
examples/
├── demo-infra.yaml           （既存: 基本デモ）
├── fintech-banking.yaml       （新規: 銀行システム — DORA対象）
├── ecommerce-platform.yaml    （新規: EC — PCI DSS対象）
├── healthcare-ehr.yaml        （新規: 電子カルテ — HIPAA対象）
├── saas-multi-tenant.yaml     （新規: SaaS — SOC2対象）
├── gaming-realtime.yaml       （新規: ゲームサーバー — 低レイテンシ）
├── incidents/
│   ├── aws-us-east-1-2024.json  （新規: AWS US-East-1 障害再現）
│   ├── cloudflare-2024.json     （新規: Cloudflare障害再現）
│   └── crowdstrike-2024.json    （新規: CrowdStrike BSOD再現）
└── grafana-dashboard.json      （新規: Grafana用ダッシュボード）
```

各サンプルにはターゲット業界の規制要件に合わせた `security` / `compliance` / `cost` 設定を含める。
`incidents/` は実際の大規模障害をFaultRayで再現するデモ用。

### 5-3. クイックスタートガイド（CLI出力）
**ファイル**: `src/faultray/cli/main.py`（既存を修正）

```bash
$ faultray quickstart
# 対話形式でインフラ定義を生成:
# > インフラの種類は？ [web-app / microservices / data-pipeline]
# > 主要コンポーネント数は？ [5 / 10 / 20 / 50]
# > クラウドプロバイダーは？ [aws / gcp / azure / on-premise]
# > コンプライアンス要件は？ [none / dora / soc2 / pci-dss / hipaa]
# → infra.yaml を自動生成
# → 初回シミュレーション実行
# → ダッシュボードURL表示
```

---

## 改善カテゴリ 6: ランディングページ / ドキュメントサイト

### 6-1. ランディングページ
**ファイル**: `src/faultray/api/templates/landing.html`（新規）

認証前の `/` をランディングページにする（認証後は既存ダッシュボードへ）。

```
構成:
├── ヒーローセクション:
│   「本番に触れずに、インフラの障害耐性を数学的に証明する」
│   [無料で試す] [デモを見る] ボタン
├── 3本柱の説明:
│   Simulate / Predict / Certify
├── 導入効果の数字:
│   「150+シナリオを3分で検証」「DORA準拠レポートを1クリックで生成」
├── ユースケース:
│   金融機関 / SaaS / 保険引受 / 監査法人
├── 技術的差別化:
│   「Gremlinとの違い: 本番環境に一切触れない」
├── 料金プラン:
│   Free / Pro / Enterprise
└── CTA:
    [GitHubで始める] [お問い合わせ]
```

### 6-2. API ドキュメント強化
**ファイル**: `src/faultray/api/server.py`（既存を修正）

FastAPIの自動ドキュメント（/docs）を充実させる:
- 全エンドポイントに description / summary / response_model を追加
- リクエスト/レスポンスの example を追加
- タグでグルーピング（Simulation / Security / Compliance / Insurance / Admin）

---

## 改善カテゴリ 7: Docker / デプロイ簡易化

### 7-1. Docker Compose（ワンコマンド起動）
**ファイル**: `docker-compose.yml`（新規 or 既存改修）

```yaml
version: "3.8"
services:
  faultray:
    build: .
    ports:
      - "8000:8000"
    environment:
      - FAULTRAY_DB_PATH=/data/faultray.db
      - FAULTRAY_CORS_ORIGINS=*
    volumes:
      - faultray-data:/data
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/"]
      interval: 30s

volumes:
  faultray-data:
```

```bash
# ワンコマンドで起動
docker compose up -d
# → http://localhost:8000 でダッシュボード
```

### 7-2. Helm Chart スタブ
**ファイル**: `deploy/helm/faultray/` ディレクトリ（新規）

Kubernetes環境向けのHelm Chartスタブ:
```
deploy/helm/faultray/
├── Chart.yaml
├── values.yaml
├── templates/
│   ├── deployment.yaml
│   ├── service.yaml
│   └── ingress.yaml
```

エンタープライズ顧客のK8s環境に簡単にデプロイできる準備。

---

## 実装優先順位

```
Phase 1（すぐやる — プロダクトとして見せられる状態に）:
  ① htmx + Alpine.js 導入（base.html修正）
  ② ダッシュボード強化（スコアカード、トレンド、トップリスク）
  ③ サイドバー更新 + 新ページ追加（Security, Cost, Compliance, Settings）
  ④ インタラクティブデモ改修（セールスデモ品質に）
  ⑤ ランディングページ

Phase 2（信頼性の実証）:
  ⑥ バックテストエンジン（精度実証の最重要ピース）
  ⑦ サンプルインフラ拡充（業界別 + 実障害再現）
  ⑧ クイックスタートガイド
  ⑨ APIドキュメント強化

Phase 3（エンタープライズ対応）:
  ⑩ インテグレーション拡張（OpsGenie, Datadog, Grafana, Jira）
  ⑪ クラウドメトリクス取得（CloudWatch / Cloud Monitoring / Azure Monitor）
  ⑫ 課金基盤スタブ + 利用量トラッキング
  ⑬ APIバージョニング（/api/v1/）
  ⑭ Docker Compose + Helm Chart

Phase 4（スケール準備）:
  ⑮ 継続的バリデーション
  ⑯ 通知統合マネージャー（NotificationManager）
  ⑰ DB永続化のインテグレーション設定
```

## 技術的制約

- **フロントエンドフレームワーク不要**: React/Vue/Next.jsは導入しない。Jinja2 + htmx + Alpine.js で十分
- **ビルドステップ不要**: npm/webpack不要。CDNからライブラリを読み込む
- **既存のダークテーマを維持**: style.css の変数体系をそのまま使う
- **既存のD3.jsグラフを維持**: graph.js は機能追加のみ、リライト不要
- **SQLite維持**: SaaS化でPostgres移行するまでSQLiteで十分
- **FastAPI維持**: フレームワーク変更なし
- **Python 3.11+**: 既存と同じ
- **後方互換**: 既存のCLI/API/YAMLは動作を変えない
