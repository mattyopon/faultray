# ChaosProof 商用化改善 ハンドオフプロンプト v2

> **目的**: ChaosProofを商用プロダクトとして成立させるための機能追加
> **規模**: L（大規模） — 7エンジン追加 + 可用性モデル拡張 + レポート拡張 + API追加 + プラグイン拡張
> **作成日**: 2026-03-15
> **前版**: HANDOFF_CHAOSPROOF_IMPROVEMENTS.md（特許分析ベース。本版は商用化観点で再構成）

---

## プロンプト（以下をそのまま別セッションのエージェントに渡す）

ChaosProof（旧InfraSim）の商用化に向けた大規模機能追加を実装してください。

**プロダクトポジショニング**: "Infrastructure Resilience Intelligence"
— 本番環境に一切触れずに、インフラの障害耐性を数学的に証明するシミュレーションプラットフォーム

**3本柱**:
1. **Simulate** — 仮想カオステスト（既存の強み）
2. **Predict** — 障害予知・セキュリティ耐性分析（新規）
3. **Certify** — 規制準拠証明・保険スコアリング（新規）

**ターゲット市場**: 金融機関（DORA義務化）、サイバー保険引受、SaaS/クラウドベンダー、監査法人

**プロジェクトパス**: /home/user/projects/tools/infrasim/

---

## 現在のコードベース構造

```
src/infrasim/
├── simulator/           # シミュレーションエンジン（ここに新エンジン追加）
│   ├── engine.py        (206行) — 基本シミュレーション・シナリオオーケストレーション
│   ├── cascade.py       (701行) — カスケード障害伝搬エンジン
│   ├── dynamic_engine.py (1,091行) — 時間ステップ動的シミュレータ（トラフィック+フェイルオーバー）
│   ├── ops_engine.py    (1,908行) — 運用シミュレータ（MTBF/MTTR/SLO/劣化）
│   ├── whatif_engine.py  (858行) — What-if パラメトリックスイープ
│   ├── capacity_engine.py (668行) — キャパシティプランニング・飽和分析
│   ├── availability_model.py (284行) — 3層可用性上限モデル（解析的/閉形式）
│   ├── scenarios.py     (904行) — シナリオ/障害定義（30カテゴリ、FaultType 8種）
│   ├── traffic.py       (460行) — トラフィックパターン（DDoS/Flash Crowd/Diurnal等9種）
│   └── service.py       — サービスレベル耐性モデル
├── model/               # コアデータモデル
│   ├── components.py    (224行) — Component, ComponentType, Dependency, Capacity, AutoScaling, Failover, CB, SLO, OperationalProfile, DegradationConfig等
│   ├── graph.py         (203行) — InfraGraph（networkx DiGraph + resilience_score算出）
│   ├── loader.py        (232行) — YAMLインフラ定義ローダー
│   └── demo.py          (123行) — デモインフラファクトリ
├── feeds/               # セキュリティフィード（実世界インシデント→シナリオ自動変換）
│   ├── analyzer.py      (416行) — 15+インシデントパターン、キーワードマッチ→シナリオ生成
│   ├── fetcher.py       (152行) — RSS/Atomフィードフェッチャー
│   ├── sources.py       (69行) — フィードソース定義（NVD, CISA等）
│   └── store.py         (139行) — シナリオ永続ストア（~/.infrasim/）
├── plugins/             # プラグインシステム
│   └── registry.py      (77行) — ScenarioPlugin/AnalyzerPlugin Protocol + PluginRegistry
├── reporter/            # レポート生成
│   ├── compliance.py    (438行) — DORAコンプライアンスレポート（HTML）
│   ├── html_report.py   (308行) — HTMLレポート（Jinja2, SVG依存グラフ）
│   ├── pdf_report.py    (215行) — PDFレポート（WeasyPrint）
│   ├── export.py        (142行) — JSON/CSVエクスポート
│   └── report.py        (144行) — Richコンソール出力
├── ai/
│   └── analyzer.py      (636行) — ルールエンジン + 可用性Nines算出 + レコメンデーション
├── cli/                 # Typer CLIコマンド
│   ├── main.py          (376行) — エントリポイント・サブコマンド定義
│   ├── evaluate.py      (889行) — 総合評価パイプライン
│   ├── simulate.py      (351行) — 静的シミュレーション
│   ├── ops.py           (443行) — 運用シミュレーション
│   ├── feeds.py         (203行) — フィード管理
│   ├── discovery.py     (212行) — インフラ検出（Prometheus/Terraform）
│   ├── admin.py         (112行) — 管理コマンド
│   └── analyze.py       (89行) — AI分析
├── discovery/           # インフラ自動検出
│   ├── terraform.py     (526行) — .tfstate → InfraGraph変換
│   ├── prometheus.py    (308行) — Prometheusメトリクス取得
│   ├── scanner.py       (193行) — サービスディスカバリ
│   └── prometheus_monitor.py (82行) — バックグラウンド監視デーモン
├── api/                 # FastAPI Webダッシュボード
│   ├── server.py        (883行) — エンドポイント、レート制限、WebSocket
│   ├── database.py      (212行) — aiosqlite永続化
│   ├── auth.py          (114行) — 基本認証・トークン管理
│   └── oauth.py         (187行) — OAuth2統合
└── integrations/
    └── webhooks.py      (102行) — Webhook受信（インシデント通知連携）
```

**テスト**: `tests/` に40+テストファイル（cascade, dynamic, ops, whatif, api, cli, feeds等）
**総コード量**: 約15,900行（テスト・venv除く）

---

## 改善カテゴリ 1: 新シミュレーションエンジン（7エンジン）

### 優先度に基づく実装順序:

```
P0 (最優先): Security Resilience Engine → Cost Impact Engine
P1 (重要):   Compliance Engine → Multi-Region DR Engine
P2 (推奨):   Predictive Engine → Game Day Engine → Chaos Advisor Engine
```

---

### 1-1. Security Resilience Engine（セキュリティ耐性エンジン）【P0 — 最重要】
**ファイル**: `src/infrasim/simulator/security_engine.py`（新規）

**なぜ最優先か**: ChaosProofの独自ポジション＝「脆弱性を見つける」のではなく「脆弱性が悪用されたときにインフラがどう壊れるかをシミュレーションする」。既存のセキュリティツール（Snyk/Qualys/Tenable）と競合せず、補完する立場。

**実装要件**:

#### a) セキュリティ攻撃シナリオの定義
```python
class AttackType(str, Enum):
    DDOS_VOLUMETRIC = "ddos_volumetric"           # 大量トラフィック攻撃
    DDOS_APPLICATION = "ddos_application"          # L7アプリケーション層攻撃
    CREDENTIAL_STUFFING = "credential_stuffing"    # 資格情報総当たり
    SQL_INJECTION = "sql_injection"                # SQLインジェクション成功時
    RANSOMWARE = "ransomware"                      # ランサムウェア感染拡大
    SUPPLY_CHAIN = "supply_chain"                  # サプライチェーン攻撃
    INSIDER_THREAT = "insider_threat"              # 内部不正
    ZERO_DAY = "zero_day"                          # ゼロデイ脆弱性悪用
    API_ABUSE = "api_abuse"                        # API乱用・レート制限突破
    DATA_EXFILTRATION = "data_exfiltration"        # データ持ち出し

class SecurityScenario(BaseModel):
    id: str
    name: str
    attack_type: AttackType
    entry_point_component_id: str          # 攻撃の侵入口
    lateral_movement_paths: list[str] = [] # 横展開経路（コンポーネントIDリスト）
    target_data_components: list[str] = [] # 最終標的（DBなど）
    severity: float = 1.0                  # 0.0-1.0
    mitre_attack_ids: list[str] = []       # MITRE ATT&CK ID（参考）
```

#### b) セキュリティ構成の評価
Component に `security_profile` を追加:
```python
class SecurityProfile(BaseModel):
    encryption_at_rest: bool = False       # 保存時暗号化
    encryption_in_transit: bool = False     # 転送時暗号化(TLS)
    waf_protected: bool = False            # WAF保護下
    rate_limiting: bool = False            # レート制限あり
    auth_required: bool = False            # 認証必須
    network_segmented: bool = False        # ネットワーク分離
    backup_enabled: bool = False           # バックアップあり
    backup_frequency_hours: float = 24.0   # バックアップ頻度
    patch_sla_hours: float = 72.0          # パッチ適用SLA
    log_enabled: bool = False              # ログ有効
    ids_monitored: bool = False            # IDS/IPS監視下
```

#### c) シミュレーション機能
- **攻撃カスケード分析**: 侵入口から横展開して最終標的に到達するパスを全列挙
  - 既存の `cascade.py` を内部で再利用（CascadeEngine を呼び出す）
  - セキュリティ防御層（WAF, 認証, ネットワーク分離）を通過条件として追加
- **防御有効性スコア**: 各セキュリティ対策がどの攻撃を何%軽減するかを定量化
  ```
  例: WAF有効 → DDoS L7 を 80%軽減 / SQLi を 90%軽減
      ネットワーク分離 → 横展開を 70%軽減
      暗号化 → データ持ち出し被害を 95%軽減
  ```
- **Blast Radius分析**: 攻撃成功時の影響範囲（侵害されるコンポーネント数・データ量）
- **復旧シミュレーション**: ランサムウェア後のバックアップ復旧時間推定（RPO/RTOベース）

#### d) セキュリティ耐性スコア（0-100）
```python
def security_resilience_score(self) -> float:
    score = 100.0
    # 暗号化カバレッジ不足: -15（保存時/転送時のいずれか欠落）
    # WAF/レート制限不足: -10（公開エンドポイントに保護なし）
    # ネットワーク分離不足: -10（DBが公開セグメントに直接公開）
    # バックアップ不足: -15（ステートフルコンポーネントにバックアップなし）
    # ログ/監視不足: -10（侵害検知不能）
    # パッチSLA超過: -5（72h以上）
    # 認証不足: -10（内部サービス間認証なし）
    # 横展開可能パス: -5 per path（分離されていない隣接サービス）
    return max(0.0, min(100.0, score))
```

#### e) YAML定義の拡張例
```yaml
components:
  - id: api-server
    security:
      encryption_at_rest: false
      encryption_in_transit: true
      waf_protected: true
      rate_limiting: true
      auth_required: true
      network_segmented: true
      log_enabled: true
      ids_monitored: true
```

---

### 1-2. Cost Impact Engine（コスト影響エンジン）【P0】
**ファイル**: `src/infrasim/simulator/cost_engine.py`（新規）

**なぜP0か**: 「障害1件で○○万円の損失」→ 経営層への最強の説得材料。保険会社の引受判断にも直結。

**実装要件**:

#### a) コストモデル定義
Component に `cost_profile` を追加:
```python
class CostProfile(BaseModel):
    hourly_infra_cost: float = 0.0         # インフラ時間単価（$）
    revenue_per_minute: float = 0.0        # 分あたり売上影響（$）
    sla_credit_percent: float = 0.0        # SLA違反時のクレジット率（%）
    monthly_contract_value: float = 0.0    # 月額契約金額（SLAペナルティ計算用）
    recovery_engineer_hourly: float = 100.0 # 復旧要員時間単価（$）
    recovery_team_size: int = 2            # 復旧チーム人数
    customer_ltv: float = 0.0              # 顧客LTV（レピュテーション損失計算用）
    churn_rate_per_hour_outage: float = 0.001 # 障害1時間あたりの解約率
    data_loss_cost_per_gb: float = 0.0     # データ損失コスト（$/GB）
```

#### b) コスト影響計算
```python
@dataclass
class CostImpactResult:
    scenario_id: str
    scenario_name: str
    downtime_minutes: float
    affected_components: list[str]

    # 4種のコスト
    direct_revenue_loss: float        # 直接売上損失
    sla_penalty: float                # SLA違反ペナルティ
    recovery_cost: float              # 復旧コスト（人件費）
    reputation_cost: float            # レピュテーション損失（推定解約×LTV）

    total_cost: float                 # 合計
    annual_expected_loss: float       # 年間期待損失（= total × 年間発生確率）

    @property
    def cost_breakdown(self) -> dict[str, float]:
        return {
            "direct_revenue_loss": self.direct_revenue_loss,
            "sla_penalty": self.sla_penalty,
            "recovery_cost": self.recovery_cost,
            "reputation_cost": self.reputation_cost,
        }
```

#### c) 入力データ
- 既存の cascade.py の CascadeChain（ダウンしたコンポーネント + 時間）
- 既存の ops_engine.py の OpsSimulationResult（SLO違反回数 + ダウンタイム）
- 既存の dynamic_engine.py の TimeStepSnapshot（時系列の健全性変化）

#### d) 出力
- シナリオごとの想定損失額ランキング（Top 10 Most Expensive Failures）
- 年間リスクエクスポージャー（全シナリオの期待損失合計）
- コスト削減提案（「レプリカ追加で年間○○万円のリスク削減」）
- ROI計算（対策コスト vs リスク削減額）

---

### 1-3. Compliance Engine（コンプライアンスエンジン）【P1】
**ファイル**: `src/infrasim/simulator/compliance_engine.py`（新規）

インフラ構成が各規制フレームワークに準拠しているかを自動チェック。

#### a) 対応フレームワーク
```python
class ComplianceFramework(str, Enum):
    DORA = "dora"           # Digital Operational Resilience Act (EU金融)
    SOC2 = "soc2"           # SOC 2 Type II
    ISO27001 = "iso27001"   # ISO 27001
    PCI_DSS = "pci_dss"     # PCI DSS v4.0
    NIST_CSF = "nist_csf"   # NIST Cybersecurity Framework
    HIPAA = "hipaa"         # HIPAA（医療）
    ISMAP = "ismap"         # ISMAP（日本政府クラウド）
```

#### b) チェック項目マッピング
各フレームワークの要件を構造化:
```python
@dataclass
class ComplianceControl:
    control_id: str           # e.g., "DORA-Art.11", "SOC2-CC7.1"
    framework: ComplianceFramework
    title: str
    description: str
    check_fn: str             # 評価関数名（動的ディスパッチ）
    severity: str             # critical / high / medium / low

@dataclass
class ComplianceResult:
    framework: ComplianceFramework
    total_controls: int
    passed: int
    failed: int
    not_applicable: int
    compliance_rate: float    # passed / (total - not_applicable) * 100
    findings: list[ComplianceFinding]
    grade: str                # A/B/C/D/F
```

#### c) ChaosProofシミュレーション結果からの自動マッピング
- Resilience Score → DORA Art.11（ICTリスク管理フレームワーク）
- カスケード分析結果 → DORA Art.26（主要ICTサードパーティリスク）
- 可用性モデル → SOC2 A1.2（可用性コミットメント）
- セキュリティ耐性スコア → ISO 27001 A.17（事業継続管理）
- バックアップ設定 → PCI DSS Req.9.5（メディア保護）

#### d) Component に `compliance_tags` を追加
```python
class ComplianceTags(BaseModel):
    data_classification: str = "internal"   # public/internal/confidential/restricted
    pci_scope: bool = False                 # PCI DSS対象範囲内か
    contains_pii: bool = False              # 個人情報を含むか
    contains_phi: bool = False              # 医療情報を含むか
    audit_logging: bool = False             # 監査ログ有効か
    change_management: bool = False         # 変更管理プロセス適用か
```

---

### 1-4. Multi-Region DR Engine（マルチリージョンDRエンジン）【P1】
**ファイル**: `src/infrasim/simulator/dr_engine.py`（新規）

#### a) リージョン/AZ定義
Component に `region_config` を追加:
```python
class RegionConfig(BaseModel):
    region: str = "ap-northeast-1"
    availability_zone: str = ""
    is_primary: bool = True
    dr_target_region: str = ""             # DR先リージョン
    replication_mode: str = "async"        # sync / async / none
    replication_lag_seconds: float = 0.0   # レプリケーション遅延
    rpo_seconds: int = 0                   # Recovery Point Objective
    rto_seconds: int = 0                   # Recovery Time Objective
```

#### b) シミュレーションシナリオ
- 単一AZ障害（AZ内の全コンポーネントがDOWN）
- リージョン全体障害（リージョン内の全コンポーネントがDOWN）
- リージョン間ネットワーク分断（レプリケーション停止）
- DR切り替え（DNS切替時間 + データ同期 + アプリ起動）

#### c) 出力
```python
@dataclass
class DRSimulationResult:
    scenario: str                    # "az_failure" / "region_failure" / "network_partition"
    rpo_achieved_seconds: float      # 実際のデータ損失時間
    rto_achieved_seconds: float      # 実際の復旧時間
    rpo_target_met: bool             # RPO目標達成？
    rto_target_met: bool             # RTO目標達成？
    data_loss_estimate_gb: float     # 推定データ損失量
    affected_components: list[str]
    failover_timeline: list[dict]    # 各フェーズの時系列
```

---

### 1-5. Predictive Engine（予測エンジン）【P2】
**ファイル**: `src/infrasim/simulator/predictive_engine.py`（新規）

**制約**: scikit-learn等の重い依存は使わない。NumPy + 標準ライブラリのみ。

#### a) 予測手法
- **リソース枯渇予測**: ops_engine.py の DegradationConfig から線形外挿
  - 「あと○日でディスク100%」「あと○日でメモリ枯渇」
- **障害発生確率**: ポアソン過程（MTBFから λ = 1/MTBF で計算）
  - 「今後30日間に障害が発生する確率: ○%」
- **季節性トレンド**: 過去のトラフィックパターンから将来の負荷ピークを予測

#### b) 出力
```python
@dataclass
class PredictionAlert:
    component_id: str
    alert_type: str           # "disk_exhaustion" / "memory_exhaustion" / "failure_probability"
    predicted_date: str       # ISO形式の日付
    confidence: float         # 0.0-1.0
    current_value: float
    threshold_value: float
    recommendation: str       # 推奨アクション
```

---

### 1-6. Game Day Engine（ゲームデイエンジン）【P2】
**ファイル**: `src/infrasim/simulator/gameday_engine.py`（新規）

#### a) Game Day プラン定義
```python
class GameDayStep(BaseModel):
    time_offset_seconds: int       # 開始からの経過時間
    action: str                    # "inject_fault" / "verify_recovery" / "manual_intervention"
    fault: Fault | None = None     # 障害注入時
    expected_outcome: str = ""     # 期待結果
    timeout_seconds: int = 300     # タイムアウト
    runbook_reference: str = ""    # 参照Runbook

class GameDayPlan(BaseModel):
    name: str
    description: str
    steps: list[GameDayStep]
    success_criteria: list[str]
    rollback_plan: str
    estimated_duration_minutes: int = 60
```

#### b) 実行
- dynamic_engine.py を内部で呼び出し、各ステップを時間順に実行
- 各ステップのPASS/FAIL判定
- タイムライン出力

---

### 1-7. Chaos Advisor Engine（カオスアドバイザーエンジン）【P2】
**ファイル**: `src/infrasim/simulator/advisor_engine.py`（新規）

依存グラフのトポロジーから「やるべきカオステスト」を自動提案。

#### a) 分析手法
- **SPOF検出**: replicas=1 かつ dependents > 0 のコンポーネントを障害注入候補に
- **ボトルネック検出**: 最も多くのパスを通過するノード（betweenness centrality）
- **見逃しシナリオ検出**: 過去のシミュレーション結果と比較して未テストの障害パターンを提案
- **組み合わせ障害提案**: 単一障害で問題なかったコンポーネント同士の同時障害

#### b) 出力
```python
@dataclass
class ChaosRecommendation:
    priority: str                # "critical" / "high" / "medium" / "low"
    scenario: Scenario           # 提案するシナリオ
    reasoning: str               # なぜこのテストが必要か
    risk_if_untested: str        # テストしないリスク
    estimated_blast_radius: int  # 影響コンポーネント数
```

---

## 改善カテゴリ 2: 可用性上限モデルの拡張

**ファイル**: `src/infrasim/simulator/availability_model.py`（既存を拡張）

### 現在: 3層モデル
- Layer 1: Software Limit — `1 - (deploy_unavail + human_error + config_drift)`
- Layer 2: Hardware Limit — `Π(1 - (1-A_single)^replicas)` × failover penalty
- Layer 3: Theoretical Limit — `Layer2 × (1 - packet_loss) × (1 - gc_fraction)`

### 追加: 2層

#### Layer 4: Operational Limit（運用上限）
チームの運用能力による可用性の制約。

```python
# Component に追加するフィールド
class OperationalTeamConfig(BaseModel):
    team_size: int = 3                          # オンコールチーム人数
    oncall_coverage_hours: float = 24.0         # カバレッジ時間（24=24/7）
    timezone_coverage: int = 1                  # カバーするタイムゾーン数
    mean_acknowledge_time_minutes: float = 5.0  # 平均応答時間
    mean_diagnosis_time_minutes: float = 15.0   # 平均診断時間
    runbook_coverage_percent: float = 50.0      # Runbookカバレッジ率
    automation_percent: float = 20.0            # 自動復旧率

# 計算式:
# response_time = acknowledge + diagnosis + (manual_recovery if not automated)
# incident_rate = sum(1/MTBF for each component) per year
# operational_unavail = incident_rate × response_time / (365.25 × 24 × 3600)
# layer4 = min(layer2, 1 - operational_unavail)
```

#### Layer 5: External SLA Cascading（外部SLA連鎖上限）
外部依存サービスのSLAによる理論上限。

```python
# Component に追加するフィールド
class ExternalSLAConfig(BaseModel):
    is_external: bool = False                   # 外部サービスか
    provider_sla: float = 0.999                 # プロバイダ公表SLA（0-1）
    provider_name: str = ""                     # e.g., "AWS", "Cloudflare"
    sla_measurement: str = "monthly"            # SLA計測期間
    historical_availability: float | None = None # 実績値（公表値より信頼性高い）

# 計算式:
# external_avail = Π(provider_sla[i]) for each external dependency
# layer5 = min(layer2, external_avail)
```

### データクラス拡張
```python
@dataclass
class FiveLayerResult:
    layer1_software: AvailabilityLayer
    layer2_hardware: AvailabilityLayer
    layer3_theoretical: AvailabilityLayer
    layer4_operational: AvailabilityLayer      # 新規
    layer5_external: AvailabilityLayer          # 新規

    @property
    def bottleneck_layer(self) -> str:
        """可用性のボトルネック（最も低い層）を特定"""
        layers = [
            ("software", self.layer1_software.availability),
            ("hardware", self.layer2_hardware.availability),
            ("operational", self.layer4_operational.availability),
            ("external", self.layer5_external.availability),
        ]
        return min(layers, key=lambda x: x[1])[0]
```

**後方互換**: `compute_three_layer_model()` はそのまま残す。新関数 `compute_five_layer_model()` を追加。

---

### 追加する数学的手法（新規ファイル）

#### Monte Carlo シミュレーション【P0】
**ファイル**: `src/infrasim/simulator/monte_carlo.py`（新規）

```python
@dataclass
class MonteCarloResult:
    n_simulations: int
    availability_mean: float
    availability_p50: float
    availability_p95: float
    availability_p99: float
    availability_std: float
    confidence_interval_95: tuple[float, float]
    downtime_distribution: dict[str, float]  # {"< 1h": 0.85, "1-4h": 0.10, ...}
    worst_case_nines: float                  # p99ワーストケースのNines

def run_monte_carlo(
    graph: InfraGraph,
    n_simulations: int = 10000,
    time_horizon_days: int = 365,
    seed: int | None = None,
) -> MonteCarloResult:
    """
    各コンポーネントのMTBF/MTTRにワイブル分布を適用し、
    N回のシミュレーションで可用性の確率分布を算出。
    NumPyのみ使用（scipy不要 — numpy.random.weibullで代替）。
    """
```

#### Markov Chain モデル【P2】
**ファイル**: `src/infrasim/simulator/markov_model.py`（新規）

```python
# 状態: HEALTHY → DEGRADED → DOWN → RECOVERING → HEALTHY
# 遷移確率行列を構成し、定常状態ベクトルを求解
# numpy.linalg.eig で固有値分解 → 定常確率
```

#### Bayesian Network モデル【P2】
**ファイル**: `src/infrasim/simulator/bayesian_model.py`（新規）

```python
# 依存グラフの各エッジに条件付き確率を設定
# P(B fails | A fails) を dependency_type から導出:
#   requires → 0.95, optional → 0.3, async → 0.05
# ベイズの定理で事後確率を計算（numpy行列演算で実装）
```

---

## 改善カテゴリ 3: Cyber Insurance Scoring API【P1 — 新規追加】

**ファイル**: `src/infrasim/api/insurance_api.py`（新規）

サイバー保険会社が引受審査で使えるスコアリングAPIを提供。

### エンドポイント
```python
# POST /api/v1/insurance/score
# リクエスト: インフラYAML（またはTerraform state）
# レスポンス:
@dataclass
class InsuranceScore:
    overall_score: int              # 0-100（引受可否の判断基準）
    risk_grade: str                 # "A+" / "A" / "B+" / "B" / "C" / "D" / "F"

    # 4カテゴリのサブスコア
    resilience_score: float         # 障害耐性（既存Resilience Score）
    security_score: float           # セキュリティ耐性（Security Resilience Engine）
    recovery_score: float           # 復旧能力（DR Engine + バックアップ評価）
    operational_score: float        # 運用成熟度（Layer 4 Operational）

    # 保険引受に必要な情報
    annual_expected_loss: float     # 年間期待損失（Cost Engine）
    max_single_incident_cost: float # 単一インシデント最大損失
    risk_factors: list[dict]        # リスク要因一覧
    mitigation_recommendations: list[dict]  # リスク軽減提案

    # コンプライアンス
    compliance_summary: dict        # フレームワーク別準拠率

# GET /api/v1/insurance/benchmark
# 業界平均との比較データ（匿名統計）
```

### 既存APIサーバーへの統合
`src/infrasim/api/server.py` に新ルーターを追加:
```python
from infrasim.api.insurance_api import insurance_router
app.include_router(insurance_router, prefix="/api/v1/insurance")
```

---

## 改善カテゴリ 4: レポート拡張

**ファイル**: `src/infrasim/reporter/compliance.py`（既存拡張）+ 新規ファイル

### 4-1. SOC 2 Type II レポート
- Trust Service Criteria（TSC）5原則へのマッピング
- CC6（論理的・物理的アクセス制御）, CC7（システム運用）, CC8（変更管理）
- ChaosProofシミュレーション結果 → 各Criteriaの充足判定

### 4-2. ISO 27001 レポート
- Annex A管理策（114項目）との対応表
- A.17（事業継続管理）の自動評価
- リスクアセスメントレポート

### 4-3. PCI DSS v4.0 レポート
- 要件6（安全なシステムの開発と保守）
- 要件10（ネットワークリソースへのアクセス追跡と監視）
- 要件12.10（インシデント対応計画）
- カード会員データ環境（CDE）の分離状況検証

### 4-4. NIST CSF レポート
- 5機能（識別/防御/検知/対応/復旧）へのマッピング
- 成熟度レベル評価（Tier 1: Partial → Tier 4: Adaptive）

### 4-5. SLA Compliance レポート
- SLO目標 vs シミュレーション結果の比較表
- Error Budget残量の可視化
- 「この構成で99.9%は達成可能か？」の判定

### 4-6. Executive Summary レポート【新規】
**ファイル**: `src/infrasim/reporter/executive_report.py`（新規）
- 経営層向け1ページサマリー（非技術者向け）
- 信号機表示（🟢🟡🔴）で可視化
- コスト影響の金額表示
- 「対策しないリスク vs 対策コスト」のROI表

---

## 改善カテゴリ 5: プラグインシステム拡張

**ファイル**: `src/infrasim/plugins/registry.py`（既存を拡張）

### 追加するProtocol
```python
class EnginePlugin(Protocol):
    """カスタムシミュレーションエンジン"""
    name: str
    description: str
    def simulate(self, graph: InfraGraph, scenarios: list[Scenario]) -> dict: ...

class ReporterPlugin(Protocol):
    """カスタムレポート生成"""
    name: str
    def generate(self, graph: InfraGraph, results: dict, output_path: Path) -> Path: ...

class DiscoveryPlugin(Protocol):
    """カスタムインフラ検出"""
    name: str
    def discover(self, config: dict) -> InfraGraph: ...

class ScoringPlugin(Protocol):
    """カスタムスコアリング"""
    name: str
    def score(self, graph: InfraGraph) -> dict[str, float]: ...
```

PluginRegistry に各Protocolの register/get メソッドを追加。
engine.py のシミュレーションループで EnginePlugin を自動呼び出し。

---

## 改善カテゴリ 6: Resilience Score v2

**ファイル**: `src/infrasim/model/graph.py`（既存を拡張）

### 現在の resilience_score()（3要素）
```
score = 100
  - SPOF penalty: min(20, weighted_deps × 5) × failover(0.3) × autoscaling(0.5)
  - Utilization penalty: >90%=-15, >80%=-8, >70%=-3
  - Chain depth penalty: (max_depth - 5) × 5
```

### resilience_score_v2()（8要素に拡張）
```python
def resilience_score_v2(self) -> dict[str, float]:
    """Extended resilience scoring with category breakdown."""
    categories = {
        "spof":              0.0,  # 既存: SPOF検出
        "utilization":       0.0,  # 既存: 利用率
        "chain_depth":       0.0,  # 既存: チェーン深度
        "redundancy_pattern": 0.0, # 新規: Active-Active > Active-Standby > Single
        "circuit_breaker":   0.0,  # 新規: CBカバレッジ率
        "auto_recovery":     0.0,  # 新規: autoscaling + failover充足度
        "external_risk":     0.0,  # 新規: 外部依存リスク
        "security":          0.0,  # 新規: セキュリティ耐性（Security Engineと連携）
    }
    # ... 各カテゴリを0-100で算出
    overall = weighted_average(categories)
    return {"overall": overall, **categories}
```

**後方互換**: `resilience_score()` は変更しない。`resilience_score_v2()` を新規追加。

---

## 改善カテゴリ 7: IaC自動変換強化

**ファイル**: `src/infrasim/discovery/terraform.py`（既存を拡張）

- `terraform plan -json` の差分出力パース → 変更前後のInfraGraphを生成 → 差分シミュレーション
- HCL直接パース（.tf ファイルからの読み込み）— hcl2ライブラリ使用
- Pulumi/CDK対応のインターフェーススタブ

---

## CLI コマンド追加

```bash
# P0
infrasim security <yaml>                           # セキュリティ耐性分析
infrasim cost <yaml>                               # コスト影響分析
infrasim monte-carlo <yaml> -n 10000               # モンテカルロ可用性分析
infrasim availability <yaml> --layers 5            # 5層可用性モデル

# P1
infrasim compliance <yaml> --framework soc2        # コンプライアンスチェック
infrasim dr <yaml> --scenario region-failure        # DRシミュレーション
infrasim score-v2 <yaml>                           # Resilience Score v2

# P2
infrasim predict <yaml>                            # 障害予測
infrasim gameday <yaml> --plan gameday.yaml        # ゲームデイ事前検証
infrasim markov <yaml>                             # マルコフ連鎖分析
infrasim advise <yaml>                             # カオステスト推奨
```

---

## Component モデル変更サマリー

`src/infrasim/model/components.py` に追加するフィールド:

```python
class Component(BaseModel):
    # ... 既存フィールド ...

    # 新規追加
    security: SecurityProfile = Field(default_factory=SecurityProfile)
    cost: CostProfile = Field(default_factory=CostProfile)
    compliance: ComplianceTags = Field(default_factory=ComplianceTags)
    region: RegionConfig = Field(default_factory=RegionConfig)
    team: OperationalTeamConfig = Field(default_factory=OperationalTeamConfig)
    external_sla: ExternalSLAConfig = Field(default_factory=ExternalSLAConfig)
```

**YAML loader** (`src/infrasim/model/loader.py`) も対応する新フィールドのパースを追加。
全フィールドにデフォルト値があるため、**既存YAMLファイルはそのまま動作する（後方互換）**。

---

## テスト要件

- 各新エンジンに対してユニットテスト作成（`tests/test_security_engine.py` 等）
- 既存テストが壊れないことを確認
- `examples/` にセキュリティ/コスト/DR設定付きのデモYAMLを追加
- 新CLIコマンドのスモークテスト

## 技術的制約

- **後方互換性を維持**: 既存API（resilience_score, compute_three_layer_model, Scenario, Fault等）は変更しない
- **外部依存は最小限**: NumPy は可（既存で使用）。scikit-learn, scipy, tensorflow等は不可
- **networkx は既存で使用中**: グラフ操作はnx前提で実装してよい
- **Pydantic v2 使用中**: BaseModel は pydantic から import
- **Python 3.11+**: match文等のモダン構文使用可
- **既存のコーディングスタイルに合わせる**: `from __future__ import annotations`, docstring, 型ヒント

## 実装優先順位（最終版）

```
Phase 1 (P0): まずこれを実装
  ① Security Resilience Engine (security_engine.py)
  ② Cost Impact Engine (cost_engine.py)
  ③ 5層可用性モデル (availability_model.py 拡張)
  ④ Monte Carlo (monte_carlo.py)
  ⑤ Plugin拡張 (registry.py 拡張)
  ⑥ Component モデル拡張 (components.py + loader.py)

Phase 2 (P1): 次にこれ
  ⑦ Compliance Engine (compliance_engine.py)
  ⑧ Multi-Region DR Engine (dr_engine.py)
  ⑨ Cyber Insurance API (insurance_api.py)
  ⑩ Resilience Score v2 (graph.py 拡張)
  ⑪ レポート拡張 (compliance.py拡張 + executive_report.py)

Phase 3 (P2): 余裕があれば
  ⑫ Predictive Engine (predictive_engine.py)
  ⑬ Game Day Engine (gameday_engine.py)
  ⑭ Chaos Advisor Engine (advisor_engine.py)
  ⑮ Markov Chain (markov_model.py)
  ⑯ Bayesian Network (bayesian_model.py)
  ⑰ IaC変換強化 (terraform.py 拡張)

各Phaseごとにテスト・CLIコマンドも同時に実装すること。
```
