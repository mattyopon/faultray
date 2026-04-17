# FaultRay World-Class Product Design

**Date**: 2026-04-17
**Status**: Approved (brainstorming complete, self-review applied)
**Author**: Yutaro Maeda + Claude Code

---

## 1. Vision

FaultRay を「production に触らず infrastructure の resilience を予測・定量化・可視化する」唯一の統合ツールとして、OSS + SaaS で世界展開する。

## 2. Strategic Decisions

| 軸 | 決定 |
|---|---|
| 目標 | OSS + 学術 + 商業の全方位 |
| 投入方針 | I' Gate 撤回、全力投入 |
| 機能優先 | 独自領域 → 予測精度 → 実用性 |
| ターゲット | SRE → DevOps → CTO → 研究者 |
| ポジション | Gremlin 等の補完 → 新カテゴリ「Infrastructure Resilience Intelligence」へ移行 |
| プロダクト形態 | OSS CLI (無料) + SaaS ダッシュボード (有料) |
| 学術の位置づけ | 研究的新規性ではなくプロダクトで勝負。論文は enablement / credibility の道具 |

## 3. Current State (Self-Review で判明)

### 3.1 既存 CLI コマンド — 既に動作する

2026-04-17 実機検証の結果、以下は**既に動作する**:

| コマンド | 状態 | 検証結果 |
|---|---|---|
| `faultray simulate` | 動作する | demo で 255 scenarios tested, resilience score 出力 |
| `faultray financial` | 動作する | Annual Loss $6,082, component 別 risk table 出力 |
| `faultray gate check` | 動作する (help確認) | before/after model 比較 + terraform-plan サブコマンドあり |
| `faultray tf-check` | 動作する (help確認) | `--fail-on-regression` オプションあり |
| `faultray scan --k8s` | 動作する (help確認) | `--context`, `--namespace` オプションあり |
| `faultray tf-import` | 動作する (help確認) | Terraform state からインポート |

### 3.2 既存 faultray-app ページ — 84 ページ

関連する既存ページ:
- `/whatif` — What-If シナリオ (存在するがハードコードデータ)
- `/topology-map` — トポロジー可視化 (存在するがハードコードデータ)
- `/cost` — コスト分析 (存在するがハードコードデータ)
- `/simulate` — シミュレーション実行 (存在するがハードコードデータ)
- `/heatmap` — ヒートマップ (存在するがハードコードデータ)
- `/external-impact` — 外部影響分析
- `/sla-budget` — SLA バジェット
- `/gameday` — GameDay 管理
- `/incidents` — インシデント管理

**現状の問題**: 12 新規ページがハードコードデータのまま (GitHub Issue faultray-app#8 関連)。Python API との接続が未実装。

### 3.3 既存コードベース

| モジュール | ファイル | 状態 |
|---|---|---|
| `src/faultray/discovery/k8s_scanner.py` | 302行 | K8s discovery のフル実装あり |
| `src/faultray/discovery/aws_scanner.py` | 存在 | AWS discovery |
| `src/faultray/iac/exporter.py` | 存在 | Terraform/K8s/CloudFormation エクスポート |
| `src/faultray/simulator/cascade.py` | 903行 | cascade engine (Tier 0+1 修正適用済み) |
| `src/faultray/simulator/availability_model.py` | 490行 | N-layer model (B3 修正適用済み) |

**重要**: Phase 1 は「新規開発」ではなく「既存 skeleton の production-ready 化 + 実 K8s/Terraform 環境での検証」が正しいスコープ。

## 4. Product Architecture

### 4.1 Free Tier (OSS CLI)

`pip install faultray` で即座に使える。1人のSREが自分の環境で試せる。

| 機能 | コマンド | 既存/新規 |
|---|---|---|
| K8s Topology Discovery | `faultray scan --k8s` | 既存 (production-ready 化) |
| Terraform Blast Radius | `faultray tf-check plan.json` | 既存 (production-ready 化) |
| Cascade Simulation | `faultray simulate` | 既存 (動作確認済み) |
| CI/CD Gate | `faultray gate check` | 既存 (GitHub Action wrapper は新規) |
| Financial Impact | `faultray financial model.yaml` | 既存 (動作確認済み) |
| LLM Topology Discovery | `faultray discover postmortem` | **新規** |
| JSON/YAML Output | `--format json` | 既存 |

### 4.2 Paid Tier (SaaS Dashboard)

チームで使い始めると必要になる機能群。

| 機能 | 既存ページ | 状態 |
|---|---|---|
| What-If Scenario Builder | `/whatif` | 存在するがハードコード → API 接続が必要 |
| Topology Visualization | `/topology-map` | 同上 |
| Financial Impact Dashboard | `/cost` | 同上 |
| Heatmap | `/heatmap` | 同上 |
| GameDay 管理 | `/gameday` | 同上 |
| Team Sharing | 新規 | URL でシナリオ共有 |
| History & Trends | 新規 | availability ceiling の推移 |
| Multi-Project | `/projects` | 存在する |
| Slack / PagerDuty 連携 | 新規 | アラート通知 |

### 4.3 Paid Add-on

| 機能 | 説明 |
|---|---|
| LLM Post-Mortem → Topology | incident report テキストから dependency graph を自動生成 |
| PagerDuty / Statuspage API 連携 | インシデント履歴から topology を継続的に学習 |

## 5. Phase Plan (Self-Review 修正版)

### Phase 0: Baseline — 既存機能の実動検証 (1-2 weeks)

**新しくコードを書く前に、今あるものがどこまで動くか確認する。**

- [ ] `faultray scan --k8s` を実 K8s クラスタ (minikube or kind) で実行。出力 YAML の品質を確認
- [ ] `faultray tf-check` を実 Terraform plan JSON で実行。blast radius 出力の妥当性を確認
- [ ] `faultray gate check` を2つの model file で実行。regression 検出の動作確認
- [ ] `faultray financial` を demo 以外の model で実行。出力の妥当性を確認
- [ ] faultray-app の `/whatif`, `/topology-map`, `/cost`, `/simulate` を実ブラウザで確認。ハードコードの範囲を特定
- [ ] 65% 孤島コード (PR #40) の問題を解決: 削除のみの PR に分割

**成果物**: 各コマンドの「動作する / skeleton のみ / 壊れている」を判定した status report

### Phase 1: Production-Ready 化 (0-3 months)

既存コマンドを「demo でしか動かない」から「実インフラで信頼できる」に引き上げる。

#### 5.1.1 K8s Discovery の堅牢化

**現状**: `k8s_scanner.py` (302行) が存在。Phase 0 で実動検証。

**やること (Phase 0 結果に依存)**:
- 実 K8s クラスタでの edge case 修正 (CRD, multi-cluster, EKS/GKE/AKS 差異)
- `--watch` mode の実装 (WEAKNESS_ANALYSIS C3「静的トポロジー」の解決)
- 出力 YAML の品質保証 (topology → simulate → 結果が妥当か end-to-end 検証)

#### 5.1.2 Terraform Integration の堅牢化

**現状**: `tf-check`, `tf-import`, `iac/exporter.py` が存在。

**やること**:
- 実 Terraform plan JSON (AWS/GCP/Azure provider) での動作検証
- resource type → FaultRay component type のマッピング精度向上
- `--fail-on-regression` の exit code が CI で正しく使えることの保証

#### 5.1.3 GitHub Action の作成

**現状**: `faultray gate` コマンドは存在。GitHub Action wrapper は未作成。

**やること (真に新規)**:
- `mattyopon/faultray-action` リポジトリ作成
- Docker container action (faultray CLI を内包)
- PR コメントに blast radius 可視化を投稿
- GitHub Marketplace に公開

#### 5.1.4 faultray-app API 接続

**現状**: 12ページがハードコードデータ。Python API との接続未実装。

**やること**:
- Next.js API routes → Python FastAPI (faultray core) の gateway 構築
- `/whatif`, `/topology-map`, `/cost`, `/simulate` の4ページを優先的に実データ化
- SaaS Backend 確定: **Next.js API routes → Python FastAPI gateway パターン**

### Phase 2: Nobody Else Does This (3-6 months)

他に存在しない機能。moat を作る。

#### 5.2.1 LLM Post-Mortem → Topology (新規)

**コマンド**: `faultray discover postmortem --input incident-2026-03.md`

**仕組み**:
1. incident report テキストを LLM (Claude API) に投入
2. 抽出: コンポーネント名、依存関係、障害伝播パス、影響範囲
3. confidence score 付きで topology YAML を生成
4. 既存 topology とマージ提案 (diff 表示)
5. `--approve` で human-in-the-loop 承認

**入力ソース対応**:
- Markdown / plain text ファイル
- PagerDuty API (`--source pagerduty --api-key $PD_KEY`)
- Statuspage API
- Confluence / Notion ページ URL

**差別化**: Krasnovsky は Jaeger traces (APM) から自動構築。FaultRay は **テキストから構築**。APM 未導入の組織でも使える。

#### 5.2.2 Financial Impact — cascade 連動強化

**現状**: `faultray financial` は動作するが、cascade simulation との連動が浅い。

**やること**:
- cascade blast radius の各コンポーネントに revenue_per_hour を自動適用
- 「この障害シナリオで推定 $X/hour」をシナリオごとに算出
- SaaS: Financial risk heatmap、コンポーネント別 risk ranking、経時トレンド

#### 5.2.3 What-If Scenario Builder — 実データ化 (SaaS)

**現状**: `/whatif` ページは存在するがハードコードデータ。

**やること**:
- Python API と接続し、リアルタイムで cascade simulation を実行
- トポロジーグラフのインタラクティブ操作 (D3.js / Cytoscape.js)
- コンポーネントクリック → Kill / Degrade / Overload → blast radius アニメーション
- 複数シナリオの並列比較
- URL でチーム共有

### Phase 2.5: Prediction Credibility (6-7 months)

**プロダクトの信頼性を実証する。論文用ではなく README に貼る credibility 用。**

- [ ] 自前の K8s クラスタ (minikube + microservices demo app) で FaultRay 予測を実行
- [ ] 実際に fault injection (LitmusChaos or manual) し、FaultRay 予測 vs 実影響を比較
- [ ] 結果を README の "Prediction Accuracy" セクションとして公開
- [ ] blog post / dev.to 記事として発信

**目的**: 「FaultRay の予測は実際の障害とXX%一致した」を言えるようにする。SRE が信用する根拠。

## 6. Free / Paid 切り分け

| 機能 | Free (OSS CLI) | Paid (SaaS) |
|---|---|---|
| `faultray scan --k8s` | Yes | Yes + GUI (topology-map) |
| `faultray simulate` | Yes (JSON output) | Yes + visualization (whatif) |
| `faultray tf-check` | Yes | Yes + history |
| `faultray gate` | Yes | Yes + dashboard |
| `faultray financial` | CLI (single run) | Dashboard + trends (cost) |
| LLM topology | CLI (single file) | API連携 + 継続学習 |
| What-If Builder | — | Yes (既存 /whatif 実データ化) |
| Team sharing | — | Yes |
| Multi-project | — | Yes (既存 /projects) |
| Slack / PagerDuty alerts | — | Yes |

## 7. Pricing (Draft)

| Plan | Price | Target |
|---|---|---|
| **Community** | Free | 個人 SRE、OSS プロジェクト |
| **Team** | $299/mo | 5-20人チーム、2-5プロジェクト |
| **Business** | $999/mo | 20-100人、unlimited projects、SSO、SLA |
| **Enterprise** | Custom | 100+人、on-prem deploy option、dedicated support |

## 8. Technology Stack

| Layer | Technology | 決定根拠 |
|---|---|---|
| CLI | Python (existing faultray package) | 既存 |
| CI/CD Action | Docker container action | 新規作成 |
| SaaS Frontend | Next.js (existing faultray-app, 84 pages) | 既存 |
| SaaS Backend | Next.js API routes → Python FastAPI gateway | Next.js が frontend、Python が core engine。API routes がproxy |
| LLM Integration | Claude API (Anthropic SDK) | Phase 2 新規 |
| Database | Supabase (existing) | 既存 |
| Auth | Supabase Auth (existing) | 既存 |
| Payments | Stripe (existing) | 既存 |
| Hosting | Vercel (frontend) + Railway/Fly.io (Python API) | frontend 既存、Python API は新規 deploy |

## 9. Success Metrics

### 6 months
- GitHub stars: 100+ (現在 13 → 8x。控えめな目標)
- PyPI downloads: 3K/month (現在 1.2K → 2.5x)
- Paying teams: 3+
- Phase 1 全機能 production-ready

### 12 months
- GitHub stars: 500+
- PyPI downloads: 10K/month
- Paying teams: 20+
- ARR: $70K+
- CNCF Landscape 申請

### 24 months
- GitHub stars: 2,000+
- Paying teams: 100+
- ARR: $500K+
- 「Infrastructure Resilience Intelligence」カテゴリの認知開始

## 10. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| 既存コードが skeleton で実用に耐えない | Phase 0 で実動検証してから Phase 1 のスコープを決定 |
| Gremlin が同じ機能を出す | Phase 2 の独自機能 (LLM topology) で差別化。速度で勝つ |
| K8s topology の精度が低い | NetworkPolicy + DNS + actual traffic (optional eBPF) の多層取得 |
| LLM topology の hallucination | confidence score + human-in-the-loop 承認 |
| 1人開発のスケール限界 | OSS contributor + Devin AI 活用。ARR 到達で採用 |
| 学術的批判 (BFS 等価) | プロダクトで売る。Phase 2.5 で実測 credibility を確保 |
| faultray-app 84ページの保守負荷 | Phase 1 で4ページ優先、残りは段階的。不要ページは削除 |
| 成功指標が楽観的 | 6ヶ月目標を現実的に修正済み (stars 100+, downloads 3K) |

## 11. NOT Doing (Scope Boundary)

- Production fault injection (Gremlin の領域)
- APM / observability (Datadog の領域)
- Incident management (PagerDuty の領域)
- DORA metrics / compliance certification (前回の over-claim 教訓)
- Mobile app
- On-premise SaaS (Enterprise plan の将来オプション以外)
- TLA+ / Coq mechanized proof (学術的投資は ROI に見合わない)
- DeathStarBench benchmark (Phase 2.5 の実測で代替)
