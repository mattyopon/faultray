# FaultRay (FaultRay) 改善実装ハンドオフプロンプト

> **目的**: 特許分析中に発見した FaultRay の改善ポイントを実装する
> **規模**: L（大規模） — 5つのエンジン追加 + 可用性モデル拡張 + レポート拡張 + プラグイン拡張
> **作成日**: 2026-03-15

---

## プロンプト（以下をそのまま別セッションのエージェントに渡す）

```
FaultRay（旧FaultRay）の大規模改善を実装してください。
特許分析の過程で発見された改善ポイントを5つのカテゴリに分けて実装します。

プロジェクトパス: /home/user/projects/tools/faultray/

## 現在のコードベース構造（重要）

```
src/faultray/
├── simulator/          # シミュレーションエンジン（ここに追加）
│   ├── engine.py       (206行) — 基本シミュレーション・シナリオオーケストレーション
│   ├── cascade.py      (701行) — カスケード障害伝搬エンジン
│   ├── dynamic_engine.py (1,091行) — 時間ステップ動的シミュレータ
│   ├── ops_engine.py   (1,908行) — 運用シミュレータ（MTBF/MTTR/SLO）
│   ├── whatif_engine.py (858行) — What-if パラメトリックスイープ
│   ├── capacity_engine.py (668行) — キャパシティプランニング
│   ├── availability_model.py (284行) — 3層可用性上限モデル
│   ├── scenarios.py    (904行) — シナリオ/障害定義
│   ├── traffic.py      (460行) — トラフィックパターン
│   └── service.py      — サービスレベル耐性モデル
├── model/              # コアデータモデル
│   ├── components.py   (224行) — Component, ComponentType, Dependency等
│   ├── graph.py        (203行) — InfraGraph（networkx依存グラフ + resilience_score）
│   ├── loader.py       (232行) — YAMLローダー
│   └── demo.py         (123行) — デモインフラ
├── feeds/              # セキュリティフィード
│   ├── analyzer.py     (416行) — 15+インシデントパターン
│   ├── fetcher.py      (152行) — RSS/Atomフェッチャー
│   ├── sources.py      (69行) — フィードソース定義
│   └── store.py        (139行) — シナリオストア
├── plugins/            # プラグインシステム
│   └── registry.py     (77行) — ScenarioPlugin/AnalyzerPlugin Protocol
├── reporter/           # レポート生成
│   ├── compliance.py   (438行) — DORAコンプライアンスレポート
│   ├── html_report.py  (308行) — HTMLレポート
│   ├── pdf_report.py   (215行) — PDFレポート
│   ├── export.py       (142行) — JSON/CSVエクスポート
│   └── report.py       (144行) — Richコンソール出力
├── ai/
│   └── analyzer.py     (636行) — AIルールエンジン + レコメンデーション
├── cli/                # CLIコマンド
│   ├── main.py (376行), evaluate.py (889行), simulate.py (351行)
│   ├── ops.py (443行), feeds.py (203行), discovery.py (212行)
│   └── admin.py (112行), analyze.py (89行)
├── discovery/          # インフラ検出
│   ├── terraform.py (526行), prometheus.py (308行)
│   ├── scanner.py (193行), prometheus_monitor.py (82行)
├── api/                # FastAPI WebダッシュボードON
│   ├── server.py (883行), database.py (212行)
│   ├── auth.py (114行), oauth.py (187行)
└── integrations/
    └── webhooks.py     (102行) — Webhook受信
```

## 改善カテゴリ 1: 新シミュレーションエンジン追加（5エンジン）

### 1-1. Cost Impact Engine（コスト影響エンジン）
**ファイル**: `src/faultray/simulator/cost_engine.py`（新規）

障害発生時のコスト影響を定量化するエンジン。

実装要件:
- 障害発生時のビジネス損失を金額で算出
  - ダウンタイムコスト = (1分あたりの売上) × ダウンタイム分数
  - SLA違反ペナルティ = SLA契約に基づくクレジット返金額
  - レピュテーションコスト = 推定顧客離脱率 × LTV
  - 復旧コスト = 人件費 × MTTR × 要員数
- Component モデルに `cost_profile` を追加:
  ```python
  class CostProfile(BaseModel):
      hourly_infra_cost: float = 0.0  # インフラ時間単価
      revenue_per_minute: float = 0.0  # 分あたり売上影響
      sla_credit_percent: float = 0.0  # SLA違反時のクレジット率
      recovery_engineer_cost: float = 100.0  # 復旧要員時間単価
  ```
- 既存の cascade.py / ops_engine.py の出力（ダウンタイム分数、影響コンポーネント）を入力として使用
- レポート出力: 障害シナリオごとの想定損失額ランキング

### 1-2. Compliance Engine（コンプライアンスエンジン）
**ファイル**: `src/faultray/simulator/compliance_engine.py`（新規）

インフラ構成が各規制フレームワークに準拠しているかを自動チェック。

実装要件:
- 対応フレームワーク:
  - DORA（既存compliance.pyの拡張）
  - SOC 2 Type II（可用性/機密性/処理の完全性/プライバシー/セキュリティ）
  - ISO 27001（情報セキュリティ管理）
  - PCI DSS（決済カード業界）
  - NIST CSF（サイバーセキュリティフレームワーク）
- チェック項目の例:
  - 暗号化（保存時/転送時）の有無
  - 冗長化要件の充足
  - バックアップ/DR設計の有無
  - アクセス制御の設定
  - ログ/監査証跡の設定
- Component に `compliance_tags` を追加（暗号化対応、バックアップ有無等）
- 出力: フレームワークごとの準拠率 + ギャップ分析レポート

### 1-3. Predictive Engine（予測エンジン — ML/統計ベース）
**ファイル**: `src/faultray/simulator/predictive_engine.py`（新規）

過去のシミュレーション結果やメトリクスから将来の障害を予測。

実装要件:
- **注意**: 外部ML依存（scikit-learn等）は使わず、NumPy + 標準ライブラリのみで実装
- 手法:
  - 時系列外挿（移動平均 + 線形回帰）でリソース枯渇予測
  - ポアソン過程ベースの障害発生確率予測（MTBFから導出）
  - 劣化トレンド分析（メモリリーク、ディスク消費の傾き）
- 既存の ops_engine.py の `DegradationConfig`（memory_leak_mb_per_hour, disk_growth_gb_per_day）を入力
- 出力:
  - 「X日後にディスク枯渇」「Y日後にメモリ枯渇」等のアラート
  - 障害確率の時系列グラフデータ（JSON）
  - 推奨アクション（スケールアウト時期、メンテナンスウィンドウ提案）

### 1-4. Multi-Region DR Engine（マルチリージョンDRエンジン）
**ファイル**: `src/faultray/simulator/dr_engine.py`（新規）

リージョン障害/AZ障害時のDR（災害復旧）をシミュレート。

実装要件:
- リージョン/AZ情報を Component に追加:
  ```python
  class RegionConfig(BaseModel):
      region: str = "ap-northeast-1"
      availability_zone: str = ""
      is_primary: bool = True
      dr_target_region: str = ""
      rpo_seconds: int = 0  # Recovery Point Objective
      rto_seconds: int = 0  # Recovery Time Objective
  ```
- シミュレーションシナリオ:
  - 単一AZ障害（AZ内の全コンポーネントダウン）
  - リージョン全体障害（リージョン内の全コンポーネントダウン）
  - ネットワーク分断（リージョン間通信断絶）
- DR切り替えプロセスのシミュレーション:
  - DNS切替時間
  - データ同期遅延（RPO検証）
  - フェイルオーバー完了時間（RTO検証）
- 出力: RPO/RTO達成可否、データ損失量の推定

### 1-5. Game Day Engine（ゲームデイエンジン）
**ファイル**: `src/faultray/simulator/gameday_engine.py`（新規）

実際のGame Day演習をシミュレート環境で事前検証。

実装要件:
- Game Day シナリオ定義:
  ```python
  class GameDayStep(BaseModel):
      time_offset_seconds: int  # 開始からの経過時間
      action: str  # inject_fault / verify_metric / manual_intervention
      fault: Fault | None = None
      expected_outcome: str = ""
      runbook_step: str = ""  # 参照Runbook手順

  class GameDayPlan(BaseModel):
      name: str
      steps: list[GameDayStep]
      success_criteria: list[str]
      rollback_plan: str
  ```
- 時系列実行:
  - 各ステップを時間順に実行
  - 障害注入 → メトリクス変化 → 自動復旧確認 → 手動介入判定
  - dynamic_engine.py を内部で使用してリアルタイムシミュレーション
- 出力:
  - 各ステップのPASS/FAIL
  - タイムライン（何分何秒に何が起きたか）
  - 改善推奨事項

## 改善カテゴリ 2: 可用性上限モデルの拡張

### 現在: 3層モデル（availability_model.py: 284行）
- Layer 1: Software Limit（デプロイ + ヒューマンエラー + 設定ドリフト）
- Layer 2: Hardware Limit（MTBF/MTTR × 冗長化 × フェイルオーバー）
- Layer 3: Theoretical Limit（パケットロス + GCポーズ + カーネルジッタ）

### 追加する層:
**ファイル**: `src/faultray/simulator/availability_model.py`（既存を拡張）

#### Layer 4: Operational Limit（運用上限）
- インシデント対応時間の制約
- チーム規模 × オンコール体制 × タイムゾーンカバレッジ
- 計算式: `operational_avail = 1 - (incident_rate × mean_response_time / 8760)`

#### Layer 5: External SLA Cascading（外部SLA連鎖）
- AWS/GCP等のプラットフォームSLA上限
- 依存外部APIのSLAの積
- 計算式: `external_avail = product(external_sla[i] for each external dependency)`

### 追加する数学的手法:

#### Monte Carlo シミュレーション
**ファイル**: `src/faultray/simulator/monte_carlo.py`（新規）
- 確率的な可用性シミュレーション（N回試行の統計分布）
- MTBF/MTTRに正規分布やワイブル分布を適用
- 出力: 可用性の確率分布（p50/p95/p99）、信頼区間

#### Markov Chain モデル
**ファイル**: `src/faultray/simulator/markov_model.py`（新規）
- コンポーネントの状態遷移（Healthy → Degraded → Down → Recovering → Healthy）
- 遷移確率行列から定常状態を計算
- 出力: 各状態の定常確率、可用性の解析解

#### Bayesian Network モデル
**ファイル**: `src/faultray/simulator/bayesian_model.py`（新規）
- 条件付き確率で障害の連鎖を表現
- 「Aが落ちたときにBが落ちる確率」を依存関係から推論
- 出力: 事後確率による影響分析

### データクラス変更:
```python
# ThreeLayerResult → FiveLayerResult に拡張
@dataclass
class FiveLayerResult:
    layer1_software: AvailabilityLayer
    layer2_hardware: AvailabilityLayer
    layer3_theoretical: AvailabilityLayer
    layer4_operational: AvailabilityLayer  # 新規
    layer5_external: AvailabilityLayer     # 新規
```
- 既存の `compute_three_layer_model()` は後方互換のため残す
- 新関数 `compute_five_layer_model()` を追加
- CLI/レポートでは5層を表示しつつ、既存の3層APIも維持

## 改善カテゴリ 3: レポート拡張

### 現在のレポート:
- DORAコンプライアンス（compliance.py）
- HTMLレポート（html_report.py）
- PDFレポート（pdf_report.py）
- JSON/CSVエクスポート（export.py）

### 追加するレポート:
**ファイル**: `src/faultray/reporter/compliance.py`（既存を拡張）+ 新規ファイル

#### 3-1. SOC 2 Type II レポート
- Trust Service Criteria（TSC）へのマッピング
- CC6（論理的/物理的アクセス制御）、CC7（システム運用）、CC8（変更管理）
- FaultRay結果からの自動マッピング

#### 3-2. ISO 27001 レポート
- Annex A管理策との対応表
- A.17（情報セキュリティ側面の事業継続管理）の評価
- リスクアセスメント結果の出力

#### 3-3. PCI DSS レポート
- 要件6（安全なシステムの開発と保守）
- 要件10（ネットワークリソースへのアクセス追跡と監視）
- カード会員データ環境の分離状況の検証

#### 3-4. NIST CSF レポート
- 5機能（識別/防御/検知/対応/復旧）へのマッピング
- 成熟度レベルの評価（Tier 1-4）

#### 3-5. SLA Compliance レポート
- SLO目標 vs 実測（シミュレーション結果）の比較
- Error Budget残量の可視化
- 月次/四半期トレンド

#### 3-6. Incident Response レポート
- インシデント対応手順の有効性評価
- MTTR/MTTA（Mean Time to Acknowledge）の分析
- エスカレーションパスの検証

## 改善カテゴリ 4: プラグインシステム拡張

### 現在のプラグインProtocol:
```python
class ScenarioPlugin(Protocol):
    name: str
    description: str
    def generate_scenarios(self, graph, component_ids, components) -> list: ...

class AnalyzerPlugin(Protocol):
    name: str
    def analyze(self, graph, report) -> dict: ...
```

### 追加するプラグインProtocol:
**ファイル**: `src/faultray/plugins/registry.py`（既存を拡張）

```python
class EnginePlugin(Protocol):
    """カスタムシミュレーションエンジン"""
    name: str
    def simulate(self, graph: InfraGraph, scenarios: list) -> dict: ...

class ReporterPlugin(Protocol):
    """カスタムレポート生成"""
    name: str
    def generate(self, graph: InfraGraph, results: dict) -> str: ...

class DiscoveryPlugin(Protocol):
    """カスタムインフラ検出"""
    name: str
    def discover(self, config: dict) -> InfraGraph: ...
```

- 各Protocolの register/get メソッドを PluginRegistry に追加
- engine.py のシミュレーション実行ループで EnginePlugin を自動呼び出し
- evaluate コマンドで ReporterPlugin を自動出力

## 改善カテゴリ 5: 特許価値を高める実装改善

### 5-1. Terraform → シミュレーションモデル自動変換の強化
**ファイル**: `src/faultray/discovery/terraform.py`（既存を拡張）

現在のTerraformインポートに以下を追加:
- terraform plan の差分から変更影響シミュレーションを自動実行
- HCL直接パース（.tf ファイルからの直接読み込み）
- Pulumi/CDK対応のスタブ

### 5-2. Resilience Score アルゴリズムの拡張
**ファイル**: `src/faultray/model/graph.py`（既存を拡張）

現在の resilience_score() は3要素（SPOF/利用率/チェーン深度）のみ。追加:
- 冗長化パターンスコア（Active-Active > Active-Standby > Single）
- サーキットブレーカーカバレッジ率
- 自動復旧率（autoscaling + failover設定の充足度）
- 外部依存リスクスコア
- 新スコア: `resilience_score_v2()` として追加（v1は後方互換のため残す）

### 5-3. シナリオ自動生成アルゴリズムの拡張
**ファイル**: `src/faultray/simulator/scenarios.py`（既存を拡張）

現在30カテゴリ → 以下を追加:
- カオスエンジニアリングベストプラクティスからのシナリオ自動提案
- 依存グラフのトポロジー分析からの脆弱ポイント自動検出
- 過去のシミュレーション結果からの「見逃しシナリオ」提案

## 実装優先順位

1. **P0（必須・先に実装）**:
   - Cost Impact Engine（コスト可視化は商用価値が高い）
   - 5層可用性モデル（Layer 4/5追加）
   - Monte Carlo シミュレーション
   - プラグインシステム拡張（EnginePlugin追加）

2. **P1（重要）**:
   - Compliance Engine（SOC2/ISO/PCI/NIST）
   - Multi-Region DR Engine
   - レポート拡張（SOC2/NIST/SLA）
   - Resilience Score v2

3. **P2（あれば良い）**:
   - Predictive Engine
   - Markov Chain モデル
   - Bayesian Network モデル
   - Game Day Engine
   - Terraform強化

## CLI コマンド追加

各エンジンに対応するCLIサブコマンドを追加:
```
faultray cost <yaml>               # コスト影響分析
faultray compliance <yaml> --framework soc2  # コンプライアンスチェック
faultray predict <yaml>            # 予測分析
faultray dr <yaml> --scenario region-failure  # DRシミュレーション
faultray gameday <yaml> --plan gameday.yaml   # ゲームデイ事前検証
faultray monte-carlo <yaml> -n 10000          # モンテカルロ分析
faultray markov <yaml>             # マルコフ連鎖分析
faultray availability <yaml> --layers 5       # 5層可用性モデル
```

## テスト要件

- 各新エンジンに対してユニットテストを作成（tests/ ディレクトリ）
- 既存テストが壊れないことを確認（後方互換性）
- examples/ に各エンジンのデモYAMLを追加

## 注意事項

- **後方互換性を維持**: 既存API（resilience_score, compute_three_layer_model等）は変更しない
- **外部依存は最小限**: NumPy は可（既存で使用）。scikit-learn等の重い依存は避ける
- **networkx は既存で使用中**: グラフ操作はnx前提で実装してよい
- **Pydantic v2 使用中**: BaseModel は pydantic から import
- **Python 3.11+**: match文等のモダン構文使用可
- **既存のコーディングスタイルに合わせる**: docstring、型ヒント、from __future__ import annotations
```

---

## 補足: 現在のResilienceスコアアルゴリズム（graph.py:106-166）

```python
def resilience_score(self) -> float:
    score = 100.0

    # 1. SPOF ペナルティ: replicas<=1 かつ dependents>0
    #    penalty = min(20, weighted_deps * 5)
    #    dependency_type: requires=1.0, optional=0.3, async=0.1
    #    failover.enabled → penalty *= 0.3
    #    autoscaling.enabled → penalty *= 0.5

    # 2. 利用率ペナルティ:
    #    >90% → -15, >80% → -8, >70% → -3

    # 3. チェーン深度ペナルティ:
    #    get_critical_paths() で最長パスを検出
    #    max_depth > 5 → -(max_depth - 5) * 5

    return max(0.0, min(100.0, score))
```

## 補足: 現在の3層可用性モデル（availability_model.py）

- Layer 1: `system_sw = min(1 - (deploy_unavail + human_error + config_drift), system_hw)`
- Layer 2: `system_hw = Π(1 - (1-A_single)^replicas)` for critical path components
- Layer 3: `system_theoretical = system_hw × (1 - avg_packet_loss) × (1 - avg_gc_fraction)`
