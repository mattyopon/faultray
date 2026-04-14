# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""FaultRay Streamlit UI — インフラ障害シミュレーターのWebインターフェース.

初めてのユーザーが迷わず使えるUI。ワンクリックで価値を体験できる設計。
FaultRayがインストールされていない場合はデモモードで動作します。

起動方法:
    streamlit run ui/streamlit_app.py
"""

from __future__ import annotations

import json
import sys
import os
import time
import traceback
from typing import Any

import streamlit as st
import yaml

# faultray パッケージをインポートできるようにパスを挿入
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

# ---------------------------------------------------------------------------
# FaultRayエンジンのインポート（失敗時はデモモードにフォールバック）
# ---------------------------------------------------------------------------

FAULTRAY_AVAILABLE = False
GOVERNANCE_AVAILABLE = False
FINANCIAL_AVAILABLE = False
try:
    from faultray.model.graph import InfraGraph
    from faultray.model.components import Component, ComponentType, Dependency
    from faultray.simulator.engine import SimulationEngine, SimulationReport
    FAULTRAY_AVAILABLE = True
except ImportError:
    pass

try:
    from faultray.governance.assessor import GovernanceAssessor, AssessmentResult, MATURITY_LABELS
    from faultray.governance.frameworks import (
        METI_CATEGORIES, METI_QUESTIONS, GovernanceFramework,
        CROSS_MAPPING, all_meti_requirements, all_iso_requirements, all_act_requirements,
    )
    GOVERNANCE_AVAILABLE = True
except ImportError:
    pass

try:
    from faultray.simulator.financial_impact import (
        calculate_financial_impact, FinancialImpactReport,
        DEFAULT_COST_PER_HOUR, DEFAULT_FIX_COST_PER_YEAR,
    )
    FINANCIAL_AVAILABLE = True
except ImportError:
    pass

# ---------------------------------------------------------------------------
# ページ設定（最初に呼ぶ必要がある）
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="FaultRay — インフラ障害シミュレーター",
    page_icon="\u26a1",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# session_state 初期化
# ---------------------------------------------------------------------------

_defaults: dict[str, Any] = {
    "onboarded": False,
    "current_page": None,
    "topology_yaml": "",
    "sim_result": None,
    "sim_history": [],
    "selected_sample": None,
    "show_topology_preview": False,
    "parsed_topology": None,
    "severity_filter": "すべて",
    "auto_run_demo": False,
    "inline_result": None,
    # Governance assessment
    "gov_answers": {},
    "gov_result": None,
    "gov_framework": "all",
    # Financial / Remediation demo data
    "financial_report": None,
    # Quick Demo
    "quick_demo_result": None,
    # DORA assessment
    "dora_result": None,
    # IaC export
    "iac_export_result": None,
}
for _k, _v in _defaults.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

# ---------------------------------------------------------------------------
# カスタムCSS
# ---------------------------------------------------------------------------

st.markdown("""
<style>
    /* Inter font */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    html, body, [class*="st-"] { font-family: 'Inter', sans-serif !important; }

    /* メトリクスカード */
    div[data-testid="stMetric"] {
        background-color: #f8f9fa;
        border: 1px solid #e9ecef;
        border-radius: 8px;
        padding: 12px 16px;
    }
    /* サイドバー */
    section[data-testid="stSidebar"] > div {
        padding-top: 1rem;
    }
    /* ウェルカムカード */
    .welcome-card {
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
        border-radius: 16px;
        padding: 48px 40px;
        color: white;
        text-align: center;
        margin-bottom: 24px;
        border: 1px solid #334155;
    }
    .welcome-card h1 {
        color: #f8fafc;
        font-size: 2.4em;
        margin-bottom: 8px;
    }
    .welcome-card p {
        color: #94a3b8;
        font-size: 1.15em;
    }
    /* ステップカード */
    .step-card {
        background: #f8f9fa;
        border: 1px solid #e9ecef;
        border-radius: 12px;
        padding: 24px;
        text-align: center;
        height: 100%;
    }
    .step-card h3 { margin-top: 8px; }
    /* スコアゲージ */
    .score-gauge {
        text-align: center;
        padding: 24px;
        border-radius: 12px;
        background: linear-gradient(135deg, #1e293b, #0f172a);
        border: 1px solid #33415533;
        margin-bottom: 1rem;
    }
    .score-gauge .score-number {
        font-size: 4em;
        font-weight: 800;
        line-height: 1;
    }
    .score-gauge .score-sublabel {
        font-size: 1rem;
        color: #94a3b8;
        margin-top: 4px;
    }
    .score-gauge .score-label {
        font-size: 1.25em;
        margin-top: 8px;
    }
    /* サンプルカード — クリッカブル */
    .sample-card-clickable {
        background: #f8f9fa;
        border: 2px solid #e9ecef;
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 12px;
        cursor: pointer;
        transition: all 0.2s ease;
    }
    .sample-card-clickable:hover {
        border-color: #667eea;
        background: #f0f4ff;
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(102, 126, 234, 0.15);
    }
    .sample-card-selected {
        border-color: #667eea !important;
        background: #eef2ff !important;
        box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.2);
    }
    /* 改善提案カード */
    .suggestion-card {
        background: #f8f9fa;
        border: 1px solid #e9ecef;
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 12px;
        border-left: 4px solid;
    }
    .suggestion-card-critical { border-left-color: #ef4444; background: #fff5f5; }
    .suggestion-card-warning { border-left-color: #f59e0b; background: #fffdf0; }
    .suggestion-card-info { border-left-color: #3b82f6; background: #eff6ff; }
    /* 空状態 */
    .empty-state {
        text-align: center;
        padding: 60px 20px;
        color: #6c757d;
    }
    .empty-state h3 { color: #495057; }
    /* ツールチップ */
    .tooltip-term {
        border-bottom: 1px dotted #94a3b8;
        cursor: help;
    }
    /* インラインスコアバッジ */
    .score-badge {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        padding: 8px 16px;
        border-radius: 999px;
        font-weight: 700;
        font-size: 1.1em;
    }
    .score-badge-good { background: #dcfce7; color: #166534; }
    .score-badge-warn { background: #fef3c7; color: #92400e; }
    .score-badge-danger { background: #fee2e2; color: #991b1b; }
    /* クイックスタートの結果カード */
    .quick-result-card {
        background: #f8f9fa;
        border: 1px solid #e9ecef;
        border-radius: 12px;
        padding: 20px;
        margin: 8px 0;
    }
    /* ガバナンス診断 — 質問カード */
    .gov-question-card {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 20px 24px;
        margin-bottom: 16px;
    }
    .gov-question-card .q-number {
        color: #2563eb;
        font-weight: 700;
        font-size: 0.85em;
    }
    /* 大きな数字メトリクス（エグゼクティブ向け） */
    .exec-metric {
        text-align: center;
        padding: 24px 16px;
        border-radius: 12px;
        background: linear-gradient(135deg, #1e293b, #0f172a);
        border: 1px solid #33415533;
        margin-bottom: 1rem;
    }
    .exec-metric .exec-value {
        font-size: 2.5em;
        font-weight: 800;
        line-height: 1.1;
    }
    .exec-metric .exec-label {
        font-size: 0.95em;
        color: #94a3b8;
        margin-top: 4px;
    }
    /* 改善計画タイムライン */
    .timeline-item {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-left: 4px solid #2563eb;
        border-radius: 0 8px 8px 0;
        padding: 16px 20px;
        margin-bottom: 12px;
    }
    .timeline-item-high { border-left-color: #ef4444; }
    .timeline-item-medium { border-left-color: #f59e0b; }
    .timeline-item-low { border-left-color: #22c55e; }
    /* レポートセンター カード */
    .report-card {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 20px 24px;
        margin-bottom: 16px;
    }
    .report-card h4 { margin: 0 0 4px 0; }
    .report-card p { color: #64748b; margin: 0; font-size: 0.9em; }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# サンプルトポロジー
# ---------------------------------------------------------------------------

SAMPLE_TOPOLOGIES: dict[str, dict[str, Any]] = {
    "Webアプリ 3層構成": {
        "description": "典型的な Nginx + アプリサーバー + DB + キャッシュ の3層構成",
        "icon": "🌐",
        "detail": "LB、アプリサーバー2台、PostgreSQL、Redis、RabbitMQ",
        "yaml": """\
components:
  - id: nginx
    name: "nginx (LB)"
    type: load_balancer
    host: web01
    port: 443
    replicas: 2
    capacity:
      max_connections: 10000
      max_rps: 50000
    metrics:
      cpu_percent: 15
      memory_percent: 20

  - id: app-1
    name: "api-server-1"
    type: app_server
    host: app01
    port: 8080
    replicas: 3
    capacity:
      max_connections: 1000
      connection_pool_size: 200
      timeout_seconds: 30
      max_memory_mb: 4096
    metrics:
      cpu_percent: 22
      memory_percent: 25
      network_connections: 200

  - id: app-2
    name: "api-server-2"
    type: app_server
    host: app02
    port: 8080
    replicas: 3
    capacity:
      max_connections: 1000
      connection_pool_size: 200
      timeout_seconds: 30
      max_memory_mb: 4096
    metrics:
      cpu_percent: 20
      memory_percent: 24
      network_connections: 180

  - id: postgres
    name: "PostgreSQL (primary)"
    type: database
    host: db01
    port: 5432
    replicas: 2
    capacity:
      max_connections: 200
      max_disk_gb: 500
    metrics:
      cpu_percent: 20
      memory_percent: 26
      network_connections: 40

  - id: redis
    name: "Redis (cache)"
    type: cache
    host: cache01
    port: 6379
    replicas: 2
    capacity:
      max_connections: 10000
    metrics:
      cpu_percent: 8
      memory_percent: 22
      network_connections: 100

  - id: rabbitmq
    name: "RabbitMQ"
    type: queue
    host: mq01
    port: 5672
    replicas: 2
    capacity:
      max_connections: 1000
    metrics:
      cpu_percent: 10
      memory_percent: 20
      network_connections: 25

dependencies:
  - source: nginx
    target: app-1
    type: requires
    weight: 1.0
  - source: nginx
    target: app-2
    type: requires
    weight: 1.0
  - source: app-1
    target: postgres
    type: requires
    weight: 1.0
  - source: app-2
    target: postgres
    type: requires
    weight: 1.0
  - source: app-1
    target: redis
    type: optional
    weight: 0.7
  - source: app-2
    target: redis
    type: optional
    weight: 0.7
  - source: app-1
    target: rabbitmq
    type: async
    weight: 0.5
  - source: app-2
    target: rabbitmq
    type: async
    weight: 0.5
""",
    },
    "マイクロサービス構成": {
        "description": "API Gateway + 複数のマイクロサービス + 共有DB",
        "icon": "🔗",
        "detail": "User/Order/Payment/Notificationが連携するEC構成",
        "yaml": """\
components:
  - id: api-gateway
    name: "API Gateway"
    type: load_balancer
    host: gateway.internal
    port: 443
    replicas: 3
    capacity:
      max_connections: 50000
      max_rps: 100000
    metrics:
      cpu_percent: 30
      memory_percent: 35

  - id: user-service
    name: "User Service"
    type: app_server
    host: users.internal
    port: 8001
    replicas: 3
    capacity:
      max_connections: 500
      timeout_seconds: 10
    metrics:
      cpu_percent: 25
      memory_percent: 40

  - id: order-service
    name: "Order Service"
    type: app_server
    host: orders.internal
    port: 8002
    replicas: 3
    capacity:
      max_connections: 500
      timeout_seconds: 15
    metrics:
      cpu_percent: 40
      memory_percent: 50

  - id: payment-service
    name: "Payment Service"
    type: app_server
    host: payments.internal
    port: 8003
    replicas: 2
    capacity:
      max_connections: 200
      timeout_seconds: 30
    metrics:
      cpu_percent: 35
      memory_percent: 45

  - id: notification-service
    name: "Notification Service"
    type: app_server
    host: notify.internal
    port: 8004
    replicas: 2
    capacity:
      max_connections: 300
      timeout_seconds: 5
    metrics:
      cpu_percent: 15
      memory_percent: 20

  - id: users-db
    name: "Users DB"
    type: database
    host: userdb.internal
    port: 5432
    replicas: 2
    capacity:
      max_connections: 100
    metrics:
      cpu_percent: 30
      memory_percent: 60

  - id: orders-db
    name: "Orders DB"
    type: database
    host: orderdb.internal
    port: 5432
    replicas: 2
    capacity:
      max_connections: 150
    metrics:
      cpu_percent: 45
      memory_percent: 70

  - id: event-bus
    name: "Event Bus (Kafka)"
    type: queue
    host: kafka.internal
    port: 9092
    replicas: 3
    capacity:
      max_connections: 5000
    metrics:
      cpu_percent: 20
      memory_percent: 40

  - id: session-cache
    name: "Session Cache"
    type: cache
    host: redis.internal
    port: 6379
    replicas: 3
    capacity:
      max_connections: 10000
    metrics:
      cpu_percent: 10
      memory_percent: 30

dependencies:
  - source: api-gateway
    target: user-service
    type: requires
    weight: 1.0
  - source: api-gateway
    target: order-service
    type: requires
    weight: 1.0
  - source: api-gateway
    target: payment-service
    type: requires
    weight: 0.8
  - source: order-service
    target: payment-service
    type: requires
    weight: 1.0
  - source: order-service
    target: notification-service
    type: async
    weight: 0.5
  - source: user-service
    target: users-db
    type: requires
    weight: 1.0
  - source: order-service
    target: orders-db
    type: requires
    weight: 1.0
  - source: payment-service
    target: orders-db
    type: requires
    weight: 0.9
  - source: user-service
    target: session-cache
    type: optional
    weight: 0.8
  - source: order-service
    target: event-bus
    type: async
    weight: 0.6
  - source: notification-service
    target: event-bus
    type: requires
    weight: 1.0
""",
    },
    "AIパイプライン": {
        "description": "LLMエージェント + ツールサービス + インフラ の AI ワークフロー",
        "icon": "🤖",
        "detail": "Claude/OpenAI + Router/Research/Writerエージェント協調",
        "yaml": """\
schema_version: "4.0"

components:
  - id: api-server
    name: API Gateway
    type: app_server
    host: api.example.com
    port: 443
    replicas: 3
    metrics:
      cpu_percent: 35.0
      memory_percent: 50.0
    capacity:
      max_connections: 5000
      max_rps: 10000
      timeout_seconds: 30

  - id: postgres-db
    name: PostgreSQL (User Data)
    type: database
    host: db.internal
    port: 5432
    replicas: 2
    metrics:
      cpu_percent: 40.0
      memory_percent: 60.0
      disk_percent: 45.0
    capacity:
      max_connections: 200
    failover:
      enabled: true
      promotion_time_seconds: 30

  - id: redis-cache
    name: Redis Cache
    type: cache
    host: redis.internal
    port: 6379
    replicas: 3
    metrics:
      memory_percent: 55.0
    capacity:
      max_connections: 1000

  - id: claude-api
    name: Claude API (Anthropic)
    type: llm_endpoint
    host: api.anthropic.com
    port: 443
    replicas: 1
    capacity:
      max_rps: 1000
      timeout_seconds: 60
    llm_config:
      provider: anthropic
      model_id: claude-sonnet-4-20250514
      rate_limit_rpm: 1000
      availability_sla: 99.9

  - id: openai-api
    name: OpenAI API (Fallback)
    type: llm_endpoint
    host: api.openai.com
    port: 443
    replicas: 1
    capacity:
      max_rps: 500
      timeout_seconds: 60
    llm_config:
      provider: openai
      model_id: gpt-4o
      availability_sla: 99.5

  - id: web-search
    name: Web Search Tool
    type: tool_service
    host: search.internal
    port: 8080
    replicas: 2
    capacity:
      max_rps: 100
      timeout_seconds: 10

  - id: db-query-tool
    name: Database Query Tool
    type: tool_service
    host: query.internal
    port: 8081
    replicas: 2
    capacity:
      max_rps: 500
      timeout_seconds: 5

  - id: router-agent
    name: Router Agent
    type: agent_orchestrator
    host: agents.internal
    port: 9000
    replicas: 2
    capacity:
      max_connections: 100
      timeout_seconds: 120

  - id: research-agent
    name: Research Agent
    type: ai_agent
    host: agents.internal
    port: 9001
    replicas: 2
    capacity:
      max_connections: 50
      timeout_seconds: 90
    agent_config:
      hallucination_risk: 0.03

  - id: writer-agent
    name: Writer Agent
    type: ai_agent
    host: agents.internal
    port: 9002
    replicas: 1
    capacity:
      max_connections: 30
      timeout_seconds: 120
    agent_config:
      hallucination_risk: 0.08

dependencies:
  - source: api-server
    target: router-agent
    type: requires
    weight: 1.0
  - source: router-agent
    target: research-agent
    type: requires
    weight: 0.8
  - source: router-agent
    target: writer-agent
    type: requires
    weight: 0.7
  - source: research-agent
    target: web-search
    type: optional
    weight: 0.5
  - source: research-agent
    target: db-query-tool
    type: requires
    weight: 0.9
  - source: research-agent
    target: claude-api
    type: requires
    weight: 1.0
  - source: writer-agent
    target: claude-api
    type: requires
    weight: 1.0
  - source: research-agent
    target: openai-api
    type: optional
    weight: 0.3
  - source: db-query-tool
    target: postgres-db
    type: requires
    weight: 1.0
  - source: db-query-tool
    target: redis-cache
    type: optional
    weight: 0.4
""",
    },
}

# ---------------------------------------------------------------------------
# デモモード用のサンプル結果データ
# ---------------------------------------------------------------------------

DEMO_RESULTS: dict[str, dict[str, Any]] = {
    "Webアプリ 3層構成": {
        "resilience_score": 68.4,
        "total_scenarios": 24,
        "critical": 3,
        "warning": 7,
        "passed": 14,
        "scenarios": [
            {
                "name": "PostgreSQL 完全停止",
                "risk_score": 9.2,
                "severity": "CRITICAL",
                "affected": ["app-1", "app-2", "nginx"],
                "cascade_path": "postgres -> app-1 -> nginx\npostgres -> app-2 -> nginx",
                "suggestion": "PostgreSQLにフェイルオーバーを設定し、レプリカへの自動昇格時間を短縮してください。",
            },
            {
                "name": "トラフィック 3倍スパイク",
                "risk_score": 8.7,
                "severity": "CRITICAL",
                "affected": ["nginx", "app-1", "app-2", "postgres"],
                "cascade_path": "traffic spike -> nginx (overloaded) -> app-1 (saturated)\n-> app-2 (saturated) -> postgres (connection exhaustion)",
                "suggestion": "オートスケーリングを有効にし、Postgresのmax_connectionsとコネクションプーラー（PgBouncer等）を設定してください。",
            },
            {
                "name": "postgres コネクションプール枯渇",
                "risk_score": 7.9,
                "severity": "CRITICAL",
                "affected": ["app-1", "app-2"],
                "cascade_path": "postgres (pool exhausted) -> app-1 (timeout) -> app-2 (timeout)",
                "suggestion": "connection_pool_sizeを見直し、PgBouncerのプーリングを追加してください。",
            },
            {
                "name": "app-1 メモリ枯渇",
                "risk_score": 6.1,
                "severity": "WARNING",
                "affected": ["nginx", "postgres"],
                "cascade_path": "app-1 (OOM) -> nginx (partial) -> postgres (load spike)",
                "suggestion": "app-1のmax_memory_mbを増やすか、水平スケールのしきい値を下げてください。",
            },
            {
                "name": "Redis 停止（キャッシュ消失）",
                "risk_score": 5.8,
                "severity": "WARNING",
                "affected": ["app-1", "app-2"],
                "cascade_path": "redis -> app-1 (degraded)\nredis -> app-2 (degraded)",
                "suggestion": "Redisをoptionalな依存にしており正解ですが、キャッシュなしでのDB負荷増加に備えてコネクションプールを拡張してください。",
            },
            {
                "name": "Redis ネットワーク分断",
                "risk_score": 4.2,
                "severity": "WARNING",
                "affected": ["app-1", "app-2"],
                "cascade_path": "redis (network partition) -> app-1 (cache miss storm)\n-> app-2 (cache miss storm)",
                "suggestion": "サーキットブレーカーを設定し、キャッシュ無効時はDBへのリクエストをスロットリングしてください。",
            },
            {
                "name": "RabbitMQ 遅延スパイク",
                "risk_score": 3.4,
                "severity": "WARNING",
                "affected": ["app-1", "app-2"],
                "cascade_path": "rabbitmq (latency) -> app-1 (queue backup)\nrabbitmq (latency) -> app-2 (queue backup)",
                "suggestion": "非同期処理のタイムアウトを設定し、キューのデッドレターキューを構成してください。",
            },
            {
                "name": "nginx 単一インスタンス障害",
                "risk_score": 2.1,
                "severity": "PASS",
                "affected": [],
                "cascade_path": "nginx (1/2 down) -> サービス継続（冗長化有効）",
                "suggestion": None,
            },
            {
                "name": "app-2 単体障害",
                "risk_score": 1.8,
                "severity": "PASS",
                "affected": [],
                "cascade_path": "app-2 (down) -> nginx routes to app-1 -> サービス継続",
                "suggestion": None,
            },
            {
                "name": "RabbitMQ 単一ノード障害",
                "risk_score": 1.5,
                "severity": "PASS",
                "affected": [],
                "cascade_path": "rabbitmq (1/2 down) -> 冗長化で継続",
                "suggestion": None,
            },
        ],
        "suggestions": [
            {
                "title": "PostgreSQLのフェイルオーバー設定を追加",
                "detail": "現在フェイルオーバーが無効です。プライマリ障害時に全サービスが停止します。レプリカへの自動昇格を30秒以内に設定してください。",
                "priority": "critical",
            },
            {
                "title": "オートスケーリングの導入",
                "detail": "トラフィックスパイク時に全滅リスクがあります。CPU使用率70%超でスケールアウトするポリシーを設定してください。",
                "priority": "critical",
            },
            {
                "title": "コネクションプーラー（PgBouncer）の導入",
                "detail": "アプリサーバーが直接PostgreSQLに接続しており、コネクション枯渇リスクが高い状態です。",
                "priority": "critical",
            },
            {
                "title": "サーキットブレーカーの有効化",
                "detail": "全依存関係でサーキットブレーカーが無効です。障害の連鎖的拡大を防ぐため、各依存にサーキットブレーカーを設定してください。",
                "priority": "warning",
            },
            {
                "title": "RabbitMQのデッドレターキュー設定",
                "detail": "処理に失敗したメッセージが消失するリスクがあります。デッドレターキューを構成し、失敗メッセージを保持してください。",
                "priority": "warning",
            },
        ],
    },
    "マイクロサービス構成": {
        "resilience_score": 55.2,
        "total_scenarios": 32,
        "critical": 5,
        "warning": 10,
        "passed": 17,
        "scenarios": [
            {
                "name": "Orders DB 完全停止",
                "risk_score": 9.5,
                "severity": "CRITICAL",
                "affected": ["order-service", "payment-service", "api-gateway"],
                "cascade_path": "orders-db -> order-service -> api-gateway\norders-db -> payment-service -> api-gateway",
                "suggestion": "Orders DBにフェイルオーバーとリードレプリカを追加してください。",
            },
            {
                "name": "API Gateway 全インスタンス障害",
                "risk_score": 9.0,
                "severity": "CRITICAL",
                "affected": ["user-service", "order-service", "payment-service"],
                "cascade_path": "api-gateway -> 全サービスへのルーティング停止",
                "suggestion": "API Gatewayの前段にCDN/WAFを配置し、ヘルスチェック付きDNSフェイルオーバーを構成してください。",
            },
            {
                "name": "Kafka クラスタ障害",
                "risk_score": 7.5,
                "severity": "CRITICAL",
                "affected": ["order-service", "notification-service"],
                "cascade_path": "event-bus -> notification-service (停止)\nevent-bus -> order-service (イベント送信失敗)",
                "suggestion": "Kafkaクラスタを3AZに分散配置してください。",
            },
            {
                "name": "Payment Service タイムアウト",
                "risk_score": 6.8,
                "severity": "WARNING",
                "affected": ["order-service", "api-gateway"],
                "cascade_path": "payment-service (slow) -> order-service (timeout) -> api-gateway (degraded)",
                "suggestion": "決済処理を非同期化し、サーキットブレーカーを導入してください。",
            },
            {
                "name": "Session Cache 消失",
                "risk_score": 4.5,
                "severity": "WARNING",
                "affected": ["user-service"],
                "cascade_path": "session-cache -> user-service (re-auth required)",
                "suggestion": "セッションをJWTベースに移行し、キャッシュ依存度を下げてください。",
            },
        ],
        "suggestions": [
            {
                "title": "全データベースにフェイルオーバーを設定",
                "detail": "Orders DB, Users DB ともにフェイルオーバーが未設定です。DB障害が即座にサービス停止に直結します。",
                "priority": "critical",
            },
            {
                "title": "API Gatewayの冗長化強化",
                "detail": "単一障害点になっています。マルチAZデプロイとヘルスチェック付きロードバランシングを推奨します。",
                "priority": "critical",
            },
            {
                "title": "サーキットブレーカーの全面導入",
                "detail": "マイクロサービス間の全requires依存にサーキットブレーカーを設定し、障害伝播を遮断してください。",
                "priority": "warning",
            },
        ],
    },
    "AIパイプライン": {
        "resilience_score": 72.1,
        "total_scenarios": 28,
        "critical": 2,
        "warning": 8,
        "passed": 18,
        "scenarios": [
            {
                "name": "Claude API 完全停止",
                "risk_score": 9.0,
                "severity": "CRITICAL",
                "affected": ["research-agent", "writer-agent", "router-agent"],
                "cascade_path": "claude-api -> research-agent (停止)\nclaude-api -> writer-agent (停止)\n-> router-agent (全エージェント利用不可)",
                "suggestion": "OpenAI APIへのフォールバックを自動化してください。現在はoptional依存ですが、Claude停止時の自動切替が未設定です。",
            },
            {
                "name": "PostgreSQL データ損失",
                "risk_score": 8.5,
                "severity": "CRITICAL",
                "affected": ["db-query-tool", "research-agent"],
                "cascade_path": "postgres-db -> db-query-tool -> research-agent (データ取得不可)",
                "suggestion": "定期バックアップとポイントインタイムリカバリを有効にしてください。",
            },
            {
                "name": "Router Agent 過負荷",
                "risk_score": 5.5,
                "severity": "WARNING",
                "affected": ["api-server"],
                "cascade_path": "router-agent (overloaded) -> api-server (queueing)",
                "suggestion": "Router Agentのレプリカ数を増やし、リクエストキューにバックプレッシャーを導入してください。",
            },
        ],
        "suggestions": [
            {
                "title": "LLM APIフォールバックの自動化",
                "detail": "Claude API停止時にOpenAI APIへ自動切替する仕組みが未実装です。SLAの差（99.9% vs 99.5%）を考慮したフォールバック戦略を構築してください。",
                "priority": "critical",
            },
            {
                "title": "エージェントのリクエスト制限",
                "detail": "各エージェントにrate limitとバックプレッシャーを設定し、LLM APIのレート制限超過を防止してください。",
                "priority": "warning",
            },
        ],
    },
}


# ---------------------------------------------------------------------------
# ユーティリティ関数
# ---------------------------------------------------------------------------

def _tooltip(term: str, explanation: str) -> str:
    """専門用語にツールチップを付与する."""
    import html as _html
    return f'<span class="tooltip-term" title="{_html.escape(explanation)}">{_html.escape(term)}</span>'


def _score_emoji(score: float) -> str:
    """スコアに対応する絵文字を返す."""
    if score >= 80:
        return "\U0001f60a"  # 良好
    elif score >= 60:
        return "\u26a0\ufe0f"  # 要改善
    else:
        return "\U0001f6a8"  # 危険


def _score_label(score: float) -> str:
    """スコアに対応するラベルを返す."""
    if score >= 80:
        return "良好"
    elif score >= 60:
        return "要改善"
    else:
        return "危険"


def _score_badge_class(score: float) -> str:
    """スコアに対応するCSSクラスを返す."""
    if score >= 80:
        return "score-badge-good"
    elif score >= 60:
        return "score-badge-warn"
    else:
        return "score-badge-danger"


def parse_topology(text: str) -> dict[str, Any]:
    """YAMLまたはJSONのトポロジー定義をパースする."""
    text = text.strip()
    if not text:
        raise ValueError("トポロジーが空です")
    if text.startswith("{") or text.startswith("["):
        result = json.loads(text)
    else:
        result = yaml.safe_load(text)
    if not isinstance(result, dict):
        raise ValueError(f"トポロジーはオブジェクト（dict）である必要があります。取得した型: {type(result).__name__}")
    return result


def build_infra_graph(topology: dict[str, Any]) -> "InfraGraph":
    """パース済みトポロジーからInfraGraphを構築する."""
    graph = InfraGraph()

    components_raw = topology.get("components", [])
    for c in components_raw:
        ctype_str = c.get("type", "custom")
        try:
            ctype = ComponentType(ctype_str)
        except ValueError:
            ctype = ComponentType.CUSTOM

        capacity_raw = c.get("capacity", {})
        from faultray.model.components import Capacity, ResourceMetrics
        capacity = Capacity(**{k: v for k, v in capacity_raw.items() if k in Capacity.model_fields})

        metrics_raw = c.get("metrics", {})
        metrics = ResourceMetrics(**{k: v for k, v in metrics_raw.items() if k in ResourceMetrics.model_fields})

        failover_raw = c.get("failover", {})
        failover = None
        if failover_raw:
            from faultray.model.components import FailoverConfig
            failover = FailoverConfig(**{k: v for k, v in failover_raw.items() if k in FailoverConfig.model_fields})

        comp = Component(
            id=c["id"],
            name=c.get("name", c["id"]),
            type=ctype,
            host=c.get("host", ""),
            port=c.get("port", 0),
            replicas=c.get("replicas", 1),
            capacity=capacity,
            metrics=metrics,
            **({"failover": failover} if failover else {}),
        )
        graph.add_component(comp)

    for d in topology.get("dependencies", []):
        from faultray.model.components import CircuitBreakerConfig
        dtype_str = d.get("type", "requires")

        cb_raw = d.get("circuit_breaker", {})
        cb = None
        if cb_raw:
            cb = CircuitBreakerConfig(**{k: v for k, v in cb_raw.items() if k in CircuitBreakerConfig.model_fields})

        dep = Dependency(
            source_id=d["source"],
            target_id=d["target"],
            dependency_type=dtype_str,
            weight=d.get("weight", 1.0),
            **({"circuit_breaker": cb} if cb else {}),
        )
        graph.add_dependency(dep)

    return graph


def run_simulation(topology: dict[str, Any]) -> dict[str, Any]:
    """FaultRayエンジンでシミュレーションを実行し、結果を辞書に変換する."""
    graph = build_infra_graph(topology)
    engine = SimulationEngine(graph)
    report = engine.run_all_defaults()

    results = []
    for r in report.results:
        scenario = r.scenario
        cascade = r.cascade

        if cascade.effects:
            path_lines = []
            for eff in cascade.effects:
                health_label = eff.health.value if hasattr(eff.health, "value") else str(eff.health)
                path_lines.append(f"{eff.component_name} -> {health_label.upper()}: {eff.reason}")
            cascade_text = "\n".join(path_lines)
        else:
            cascade_text = "影響なし"

        if r.is_critical:
            severity = "CRITICAL"
        elif r.is_warning:
            severity = "WARNING"
        else:
            severity = "PASS"

        results.append({
            "name": scenario.name,
            "risk_score": round(r.risk_score, 1),
            "severity": severity,
            "affected": [eff.component_name for eff in cascade.effects],
            "cascade_path": cascade_text,
            "suggestion": None,
        })

    score = round(report.resilience_score, 1)

    return {
        "resilience_score": score,
        "total_scenarios": len(report.results),
        "critical": len(report.critical_findings),
        "warning": len(report.warnings),
        "passed": len(report.passed),
        "scenarios": results,
        "suggestions": _generate_suggestions(report),
    }


def _generate_suggestions(report: "SimulationReport") -> list[dict[str, str]]:
    """シミュレーション結果から改善提案を生成する."""
    suggestions: list[dict[str, str]] = []
    critical_names = [r.scenario.name for r in report.critical_findings]
    warning_names = [r.scenario.name for r in report.warnings]

    if any("traffic" in n.lower() or "spike" in n.lower() for n in critical_names):
        suggestions.append({
            "title": "オートスケーリングの導入",
            "detail": "トラフィックスパイクで障害が発生しています。オートスケーリングを設定してください。",
            "priority": "critical",
        })
    if any("connection" in n.lower() or "pool" in n.lower() for n in critical_names + warning_names):
        suggestions.append({
            "title": "コネクションプーラーの導入",
            "detail": "コネクションプール枯渇リスクがあります。PgBouncerまたはコネクションプーラーの導入を検討してください。",
            "priority": "critical",
        })
    if any("database" in n.lower() or "db" in n.lower() or "postgres" in n.lower() for n in critical_names):
        suggestions.append({
            "title": "データベースのフェイルオーバー設定",
            "detail": "データベース障害が致命的な影響を与えています。フェイルオーバー設定とリードレプリカを検討してください。",
            "priority": "critical",
        })
    if report.resilience_score < 60:
        suggestions.append({
            "title": "サーキットブレーカーの導入",
            "detail": "耐障害スコアが60未満です。サーキットブレーカーとリトライ戦略の導入を優先してください。",
            "priority": "warning",
        })
    if not suggestions:
        if report.critical_findings:
            suggestions.append({
                "title": "CRITICALシナリオの対処",
                "detail": f"{len(report.critical_findings)}件のCRITICAL障害シナリオを解消することで大幅にスコアが向上します。",
                "priority": "warning",
            })
        else:
            suggestions.append({
                "title": "WARNINGシナリオの継続対処",
                "detail": "主要なCRITICAL障害はありません。WARNINGシナリオの対処を継続してください。",
                "priority": "info",
            })
    return suggestions


def _execute_demo_simulation(sample_key: str) -> dict[str, Any] | None:
    """デモモードまたは実エンジンでシミュレーションを実行する."""
    # Clear cached financial report when running new simulation
    st.session_state.financial_report = None

    if sample_key not in SAMPLE_TOPOLOGIES:
        return None

    sample = SAMPLE_TOPOLOGIES[sample_key]

    if FAULTRAY_AVAILABLE:
        try:
            topo = parse_topology(sample["yaml"])
            return run_simulation(topo)
        except Exception:
            # エンジン実行失敗時はデモ結果にフォールバック
            pass

    # デモモード
    if sample_key in DEMO_RESULTS:
        return DEMO_RESULTS[sample_key]
    return None


# ---------------------------------------------------------------------------
# UI コンポーネント
# ---------------------------------------------------------------------------

def render_score_gauge(score: float) -> None:
    """耐障害スコアをゲージで表示する."""
    if score >= 80:
        color = "#22c55e"
        label = "良好"
    elif score >= 60:
        color = "#f59e0b"
        label = "要改善"
    else:
        color = "#ef4444"
        label = "危険"

    emoji = _score_emoji(score)

    st.markdown(
        f"""
        <div class="score-gauge">
            <div class="score-number" style="color: {color};">
                {emoji} {score:.1f}
            </div>
            <div class="score-sublabel">/ 100</div>
            <div class="score-label" style="color: {color};">
                {_tooltip("耐障害スコア", "インフラがどれだけ障害に強いかを0-100で示す総合スコアです")} - {label}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_score_inline(score: float) -> None:
    """スコアをインラインバッジで表示する（シミュレーション結果のサマリー用）."""
    emoji = _score_emoji(score)
    label = _score_label(score)
    badge_class = _score_badge_class(score)
    st.markdown(
        f'<div class="score-badge {badge_class}">'
        f'{emoji} 耐障害スコア: {score:.1f} / 100 ({label})'
        f'</div>',
        unsafe_allow_html=True,
    )


def render_scenario_card(scenario: dict[str, Any]) -> None:
    """単一シナリオの結果カードを表示する."""
    sev = scenario["severity"]
    score = scenario["risk_score"]

    if sev == "CRITICAL":
        badge_bg = "#7f1d1d"
        badge_color = "#fca5a5"
        icon = "CRITICAL"
    elif sev == "WARNING":
        badge_bg = "#78350f"
        badge_color = "#fcd34d"
        icon = "WARNING"
    else:
        badge_bg = "#14532d"
        badge_color = "#86efac"
        icon = "PASS"

    with st.expander(
        f"{'[!] ' if sev == 'CRITICAL' else ''}{scenario['name']}  (リスクスコア: {score})",
        expanded=(sev == "CRITICAL"),
    ):
        col1, col2 = st.columns([1, 2])
        with col1:
            st.markdown(
                f"""
                <span style="background:{badge_bg}; color:{badge_color};
                             padding: 2px 10px; border-radius: 999px;
                             font-size: 0.8rem; font-weight: 600;">
                    {icon}
                </span>
                """,
                unsafe_allow_html=True,
            )
            st.metric("リスクスコア", f"{score} / 10.0")

            affected = scenario.get("affected", [])
            if affected:
                st.markdown(
                    f"**影響{_tooltip('コンポーネント', '障害の影響を受けるシステムの構成要素です')}**",
                    unsafe_allow_html=True,
                )
                for a in affected:
                    st.markdown(f"- `{a}`")

        with col2:
            cascade = scenario.get("cascade_path", "")
            if cascade and cascade != "影響なし":
                st.markdown(
                    f"**{_tooltip('カスケード伝播', '障害が連鎖的に広がること。1つの障害が次々と別のコンポーネントに影響します')}**",
                    unsafe_allow_html=True,
                )
                st.code(cascade, language=None)

        suggestion = scenario.get("suggestion")
        if suggestion:
            st.info(f"**改善提案:** {suggestion}")


def render_topology_graph(topology: dict[str, Any]) -> None:
    """トポロジーのテキストベース可視化を表示する."""
    components = {c["id"]: c.get("name", c["id"]) for c in topology.get("components", [])}
    deps = topology.get("dependencies", [])

    if not components:
        st.warning("コンポーネントが定義されていません")
        return

    adjacency: dict[str, list[tuple[str, str]]] = {cid: [] for cid in components}
    for d in deps:
        src, tgt = d.get("source", ""), d.get("target", "")
        if src in adjacency:
            dep_type = d.get("type", "requires")
            adjacency[src].append((tgt, dep_type))

    has_incoming = {d["target"] for d in deps if d.get("target") in components}
    roots = [cid for cid in components if cid not in has_incoming]
    if not roots:
        roots = list(components.keys())[:1]

    type_icon = {"requires": "->", "optional": "~>", "async": ">>"}
    type_label = {"requires": "必須", "optional": "任意", "async": "非同期"}

    lines: list[str] = []
    visited: set[str] = set()

    def render_node(cid: str, depth: int = 0, prefix: str = "") -> None:
        if cid in visited:
            lines.append(f"{'  ' * depth}{prefix}[{components.get(cid, cid)}] (参照)")
            return
        visited.add(cid)
        lines.append(f"{'  ' * depth}{prefix}[{components.get(cid, cid)}]")
        children = adjacency.get(cid, [])
        for i, (child_id, dep_type) in enumerate(children):
            is_last = i == len(children) - 1
            arrow = type_icon.get(dep_type, "->")
            lbl = type_label.get(dep_type, dep_type)
            connector = "L-" if is_last else "|-"
            render_node(child_id, depth + 1, f"{connector}{arrow}({lbl}) ")

    for root in roots:
        render_node(root)

    for cid in components:
        if cid not in visited:
            render_node(cid)

    st.code("\n".join(lines), language=None)


def render_inline_top_issues(result: dict[str, Any], max_issues: int = 3) -> None:
    """シミュレーション結果のトップN問題をインライン表示する."""
    scenarios = result.get("scenarios", [])
    critical_scenarios = sorted(
        [s for s in scenarios if s["severity"] in ("CRITICAL", "WARNING")],
        key=lambda x: x["risk_score"],
        reverse=True,
    )[:max_issues]

    if not critical_scenarios:
        st.success("重大な問題は見つかりませんでした。")
        return

    for s in critical_scenarios:
        sev = s["severity"]
        if sev == "CRITICAL":
            icon = "\U0001f6a8"
        else:
            icon = "\u26a0\ufe0f"
        st.markdown(
            f'<div class="quick-result-card">'
            f'{icon} <strong>{s["name"]}</strong> '
            f'<span style="color:#6c757d">(リスク: {s["risk_score"]}/10)</span><br>'
            f'<span style="color:#6c757d;font-size:0.9em">'
            f'{s.get("suggestion", "") or ""}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )


# ══════════════════════════════════════════════════════════════════
# ウェルカム画面（簡素化）
# ══════════════════════════════════════════════════════════════════

def show_welcome() -> None:
    """ウェルカム画面を表示する. 3つのエントリーポイントを提供."""
    st.markdown("""
    <div class="welcome-card">
        <h1>\u26a1 FaultRay</h1>
        <p>Simulates infrastructure failures from declared topology (model-based) — without touching production. Research prototype.</p>
        <p style="font-size:0.95em;color:#64748b;margin-top:8px">
            Discover single points of failure, cascade risks, and DORA compliance gaps before they hit production.
        </p>
    </div>
    """, unsafe_allow_html=True)

    # --- 3ボタンエントリーポイント ---
    st.markdown("### Try it now:")
    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("""
        <div class="step-card">
            <div style="font-size:2em">🚀</div>
            <h3>Quick Demo</h3>
            <p style="color:#6c757d;font-size:0.9em">Run a 30-second simulation on sample infrastructure</p>
        </div>
        """, unsafe_allow_html=True)
        if st.button("🚀 Quick Demo", use_container_width=True, type="primary", key="welcome_quick_demo"):
            st.session_state.onboarded = True
            st.session_state.auto_run_demo = True
            st.session_state.current_page = "page_quick_demo"
            st.rerun()

    with col2:
        st.markdown("""
        <div class="step-card">
            <div style="font-size:2em">📋</div>
            <h3>DORA Check</h3>
            <p style="color:#6c757d;font-size:0.9em">Check your DORA & AI Governance compliance posture</p>
        </div>
        """, unsafe_allow_html=True)
        if st.button("📋 DORA Check", use_container_width=True, key="welcome_dora"):
            st.session_state.onboarded = True
            st.session_state.current_page = "page_governance"
            st.rerun()

    with col3:
        st.markdown("""
        <div class="step-card">
            <div style="font-size:2em">✏️</div>
            <h3>Upload YAML</h3>
            <p style="color:#6c757d;font-size:0.9em">Simulate your own infrastructure topology</p>
        </div>
        """, unsafe_allow_html=True)
        if st.button("✏️ Upload YAML", use_container_width=True, key="welcome_upload"):
            st.session_state.onboarded = True
            st.session_state.current_page = "page_simulation"
            st.rerun()

    st.markdown("")

    # エンジン状態（簡潔に）
    if FAULTRAY_AVAILABLE:
        st.caption("\u2705 FaultRay engine active — running real simulations")
    else:
        st.caption("\U0001f4cb Demo mode — showing sample results instantly")

    # --- 他のサンプルへの誘導 ---
    st.markdown("---")
    st.markdown("##### Or choose a sample topology to explore:")

    sample_cols = st.columns(3)
    sample_names = list(SAMPLE_TOPOLOGIES.keys())

    for idx, col in enumerate(sample_cols):
        name = sample_names[idx]
        sample = SAMPLE_TOPOLOGIES[name]
        with col:
            is_default = (name == "Webアプリ 3層構成")
            st.markdown(
                f'<div class="sample-card-clickable{"" if not is_default else ""}">'
                f'<div style="font-size:1.8em;margin-bottom:4px">{sample["icon"]}</div>'
                f'<strong>{name}</strong><br>'
                f'<span style="color:#6c757d;font-size:0.9em">{sample["detail"]}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
            if st.button(
                f"{sample['icon']} {name}",
                key=f"welcome_sample_{idx}",
                use_container_width=True,
            ):
                st.session_state.onboarded = True
                st.session_state.auto_run_demo = True
                st.session_state.selected_sample = name
                st.session_state.topology_yaml = sample["yaml"]
                st.session_state.current_page = "page_simulation"
                st.rerun()


# ══════════════════════════════════════════════════════════════════
# ページ 1: ダッシュボード
# ══════════════════════════════════════════════════════════════════

def _render_network_graph(topology: dict[str, Any]) -> None:
    """コンポーネント依存関係のネットワークグラフをPlotlyで表示する."""
    try:
        import plotly.graph_objects as go  # type: ignore[import]
        import math

        components = {c["id"]: c for c in topology.get("components", [])}
        deps = topology.get("dependencies", [])

        if not components:
            st.info("No components found in topology.")
            return

        # Simple circular layout
        n = len(components)
        comp_ids = list(components.keys())
        positions: dict[str, tuple[float, float]] = {}
        for i, cid in enumerate(comp_ids):
            angle = 2 * math.pi * i / max(n, 1)
            positions[cid] = (math.cos(angle) * 2, math.sin(angle) * 2)

        # Type → color mapping
        type_colors: dict[str, str] = {
            "load_balancer": "#3b82f6",
            "app_server": "#8b5cf6",
            "database": "#ef4444",
            "cache": "#f59e0b",
            "queue": "#10b981",
            "storage": "#6366f1",
            "external_api": "#ec4899",
            "ai_agent": "#14b8a6",
            "llm_endpoint": "#f97316",
        }

        # Edges
        edge_x, edge_y = [], []
        for d in deps:
            src, tgt = d.get("source", ""), d.get("target", "")
            if src in positions and tgt in positions:
                x0, y0 = positions[src]
                x1, y1 = positions[tgt]
                edge_x += [x0, x1, None]
                edge_y += [y0, y1, None]

        edge_trace = go.Scatter(
            x=edge_x, y=edge_y,
            mode="lines",
            line={"width": 1, "color": "#94a3b8"},
            hoverinfo="none",
        )

        # Nodes
        node_x = [positions[cid][0] for cid in comp_ids]
        node_y = [positions[cid][1] for cid in comp_ids]
        node_colors = [type_colors.get(components[cid].get("type", ""), "#64748b") for cid in comp_ids]
        node_labels = [components[cid].get("name", cid) for cid in comp_ids]
        node_types = [components[cid].get("type", "custom") for cid in comp_ids]

        node_trace = go.Scatter(
            x=node_x, y=node_y,
            mode="markers+text",
            marker={
                "size": 22,
                "color": node_colors,
                "line": {"width": 2, "color": "#ffffff"},
            },
            text=node_labels,
            textposition="bottom center",
            textfont={"size": 10},
            hovertemplate="<b>%{text}</b><br>Type: %{customdata}<extra></extra>",
            customdata=node_types,
        )

        fig = go.Figure(
            data=[edge_trace, node_trace],
            layout=go.Layout(
                height=400,
                showlegend=False,
                hovermode="closest",
                margin={"l": 10, "r": 10, "t": 10, "b": 10},
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                xaxis={"showgrid": False, "zeroline": False, "showticklabels": False},
                yaxis={"showgrid": False, "zeroline": False, "showticklabels": False},
            ),
        )
        st.plotly_chart(fig, use_container_width=True)
    except ImportError:
        # Fallback to text visualization
        if st.session_state.parsed_topology:
            render_topology_graph(st.session_state.parsed_topology)
        else:
            st.info("Install plotly for interactive network graph: `pip install plotly`")


def _render_risk_heatmap(result: dict[str, Any]) -> None:
    """シナリオリスクのヒートマップをPlotlyで表示する."""
    try:
        import plotly.graph_objects as go  # type: ignore[import]

        scenarios = result.get("scenarios", [])
        if not scenarios:
            return

        # Top 15 scenarios sorted by risk
        top = sorted(scenarios, key=lambda x: x["risk_score"], reverse=True)[:15]
        names = [s["name"][:35] for s in top]
        scores_list = [s["risk_score"] for s in top]
        colors_list = [
            "#ef4444" if s["severity"] == "CRITICAL"
            else "#f59e0b" if s["severity"] == "WARNING"
            else "#22c55e"
            for s in top
        ]

        fig = go.Figure(go.Bar(
            x=scores_list,
            y=names,
            orientation="h",
            marker_color=colors_list,
            text=[f"{s:.1f}" for s in scores_list],
            textposition="outside",
        ))
        fig.update_layout(
            height=max(300, len(names) * 30),
            xaxis_title="Risk Score (0–10)",
            xaxis={"range": [0, 11]},
            yaxis_title="",
            margin={"l": 10, "r": 60, "t": 10, "b": 30},
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font={"color": "#1e293b"},
        )
        st.plotly_chart(fig, use_container_width=True)
    except ImportError:
        st.info("Install plotly for interactive charts: `pip install plotly`")


def page_dashboard() -> None:
    """ダッシュボード: 直近のシミュレーション結果サマリー."""
    st.header("🏠 Dashboard")
    st.caption("Latest simulation results at a glance.")

    result = st.session_state.sim_result
    history = st.session_state.sim_history

    if result is None:
        # まだシミュレーションしていない
        st.markdown("""
        <div class="empty-state">
            <h3>No simulation run yet</h3>
            <p>Run a simulation to see your resilience score and issue summary here.</p>
        </div>
        """, unsafe_allow_html=True)
        st.markdown("")
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("🚀 Quick Demo", type="primary", use_container_width=True):
                st.session_state.auto_run_demo = True
                st.session_state.current_page = "page_quick_demo"
                st.rerun()
        with col_b:
            if st.button("⚡ Custom Simulation", use_container_width=True):
                st.session_state.current_page = "page_simulation"
                st.rerun()
        return

    # -- メインスコア + メトリクス (2カラム)
    col_score, col_metrics = st.columns([1, 2])
    with col_score:
        render_score_gauge(result["resilience_score"])
    with col_metrics:
        st.markdown("#### Scenario Summary")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total", result["total_scenarios"])
        c2.metric(
            "🚨 CRITICAL",
            result["critical"],
            help="Scenarios requiring immediate attention",
        )
        c3.metric(
            "⚠️ WARNING",
            result["warning"],
            help="Scenarios requiring attention",
        )
        c4.metric(
            "✅ PASS",
            result["passed"],
            help="Scenarios where redundancy is working",
        )

        # -- 改善提案トップ3
        suggestions = result.get("suggestions", [])
        critical_suggestions = [s for s in suggestions if isinstance(s, dict) and s.get("priority") == "critical"]
        if critical_suggestions:
            st.markdown("#### 🚨 Top Priority Actions")
            for i, sug in enumerate(critical_suggestions[:3], 1):
                st.markdown(
                    f'<div class="suggestion-card suggestion-card-critical">'
                    f'<strong>{i}. {__import__("html").escape(sug["title"])}</strong><br>'
                    f'<span style="color:#6c757d">{__import__("html").escape(sug["detail"])}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            if st.button("💡 All Suggestions"):
                st.session_state.current_page = "page_suggestions"
                st.rerun()

    # -- Risk heatmap
    st.markdown("---")
    st.markdown("#### Risk Heatmap")
    _render_risk_heatmap(result)

    # -- Network graph (if topology loaded)
    parsed_topo = st.session_state.parsed_topology
    if parsed_topo is None and st.session_state.topology_yaml:
        try:
            parsed_topo = parse_topology(st.session_state.topology_yaml)
        except Exception:
            parsed_topo = None

    if parsed_topo:
        st.markdown("---")
        st.markdown("#### Component Dependency Graph")
        _render_network_graph(parsed_topo)

    # -- 実行履歴
    if len(history) > 1:
        st.markdown("---")
        st.markdown("#### Run History")
        for _i, h in enumerate(reversed(history[-5:])):
            score = h["resilience_score"]
            emoji = _score_emoji(score)
            color = "#22c55e" if score >= 80 else "#f59e0b" if score >= 60 else "#ef4444"
            st.markdown(
                f"{emoji} <span style='color:{color};font-weight:bold'>{score:.1f}</span>"
                f" / 100  —  CRITICAL: {h['critical']}, WARNING: {h['warning']}, PASS: {h['passed']}",
                unsafe_allow_html=True,
            )


# ══════════════════════════════════════════════════════════════════
# ページ 2: シミュレーション実行
# ══════════════════════════════════════════════════════════════════

def page_simulation() -> None:
    """シミュレーション実行: サンプル選択 -> 自動実行 -> 結果をインライン表示."""
    st.header("\u26a1 シミュレーション")

    # --- 自動実行（ウェルカムからのワンクリック遷移時） ---
    if st.session_state.auto_run_demo:
        st.session_state.auto_run_demo = False
        sample_key = st.session_state.selected_sample
        if sample_key:
            with st.spinner(f"「{sample_key}」でシミュレーション実行中..."):
                if not FAULTRAY_AVAILABLE:
                    time.sleep(0.5)
                results = _execute_demo_simulation(sample_key)
            if results:
                st.session_state.sim_result = results
                st.session_state.sim_history.append(results)
                if len(st.session_state.sim_history) > 20:
                    st.session_state.sim_history = st.session_state.sim_history[-20:]
                st.session_state.inline_result = results

    # --- インライン結果表示（シミュレーション直後） ---
    inline_result = st.session_state.inline_result
    if inline_result:
        st.markdown("### 結果サマリー")
        render_score_inline(inline_result["resilience_score"])
        st.markdown("")

        c1, c2, c3 = st.columns(3)
        c1.metric("\U0001f6a8 CRITICAL", inline_result["critical"])
        c2.metric("\u26a0\ufe0f WARNING", inline_result["warning"])
        c3.metric("\u2705 PASS", inline_result["passed"])

        st.markdown("#### 発見された主な問題")
        render_inline_top_issues(inline_result)

        st.markdown("")
        col_detail, col_suggest, col_new = st.columns(3)
        with col_detail:
            if st.button("\U0001f4cb 結果の詳細を見る", use_container_width=True):
                st.session_state.current_page = "page_results"
                st.rerun()
        with col_suggest:
            if st.button("\U0001f4a1 改善提案を見る", use_container_width=True):
                st.session_state.current_page = "page_suggestions"
                st.rerun()
        with col_new:
            if st.button("\U0001f504 別の構成を試す", use_container_width=True):
                st.session_state.inline_result = None
                st.rerun()

        st.markdown("---")

    # --- エンジン状態（簡潔に） ---
    if not FAULTRAY_AVAILABLE:
        st.caption(
            "\U0001f4cb デモモードで動作中 - サンプル結果を表示します。"
            " 実際のシミュレーションには `pip install faultray` を実行してください。"
        )

    # --- サンプル選択（カードクリックで即実行） ---
    st.markdown("#### 構成を選んでシミュレーション")
    st.caption("カードをクリックすると即座にシミュレーションを実行します")

    sample_cols = st.columns(3)
    sample_names = list(SAMPLE_TOPOLOGIES.keys())

    for idx, col in enumerate(sample_cols):
        name = sample_names[idx]
        sample = SAMPLE_TOPOLOGIES[name]
        is_selected = (st.session_state.selected_sample == name)
        with col:
            card_class = "sample-card-clickable"
            if is_selected:
                card_class += " sample-card-selected"
            st.markdown(
                f'<div class="{card_class}">'
                f'<div style="font-size:1.8em;margin-bottom:4px">{sample["icon"]}</div>'
                f'<strong>{name}</strong><br>'
                f'<span style="color:#6c757d;font-size:0.9em">{sample["detail"]}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
            btn_label = "\u2705 選択中" if is_selected else f"{sample['icon']} この構成で実行"
            if st.button(
                btn_label,
                key=f"sample_{idx}",
                use_container_width=True,
                disabled=is_selected,
            ):
                st.session_state.selected_sample = name
                st.session_state.topology_yaml = sample["yaml"]
                st.session_state.auto_run_demo = True
                st.session_state.inline_result = None
                st.rerun()

    # --- 上級者向け: YAML直接入力 ---
    st.markdown("---")
    with st.expander("\U0001f527 上級者向け: YAML / JSON を直接入力", expanded=False):
        # YAML エラー表示
        if st.session_state.get("yaml_error"):
            st.error(st.session_state.yaml_error)
            st.session_state.yaml_error = None

        default_yaml = st.session_state.topology_yaml
        if not default_yaml:
            default_yaml = SAMPLE_TOPOLOGIES["Webアプリ 3層構成"]["yaml"]

        topology_text = st.text_area(
            "トポロジー定義",
            value=default_yaml,
            height=250,
            help="components（コンポーネント定義）とdependencies（依存関係）をYAMLまたはJSONで記述します",
            key="topology_input",
        )

        col_preview, col_run = st.columns([1, 1])

        with col_preview:
            if st.button("\U0001f441\ufe0f トポロジーを可視化", use_container_width=True):
                try:
                    topo = parse_topology(topology_text)
                    st.session_state.parsed_topology = topo
                    st.session_state.show_topology_preview = True
                    st.session_state.yaml_error = None
                except Exception as e:
                    st.session_state.yaml_error = f"パースエラー: {e}"
                    st.rerun()

        with col_run:
            run_clicked = st.button(
                "\u26a1 カスタムシミュレーション開始",
                type="primary",
                use_container_width=True,
            )

        # -- トポロジー可視化
        if st.session_state.show_topology_preview and st.session_state.parsed_topology:
            st.markdown("")
            st.markdown("##### トポロジーグラフ")
            st.markdown(
                "依存関係の種類: "
                f"{_tooltip('-> (必須)', '障害が直接伝播する依存。ターゲット停止でソースも停止')}  "
                f"{_tooltip('~> (任意)', '部分劣化する依存。ターゲット停止でもソースは動作可能')}  "
                f"{_tooltip('>> (非同期)', '遅延して影響する依存。キューやイベントバス経由')}",
                unsafe_allow_html=True,
            )
            render_topology_graph(st.session_state.parsed_topology)

        # -- カスタムシミュレーション実行
        if run_clicked:
            try:
                topo = parse_topology(topology_text)
                st.session_state.yaml_error = None
            except Exception as e:
                st.session_state.yaml_error = f"トポロジーのパースに失敗しました: {e}"
                st.rerun()
                return

            st.session_state.topology_yaml = topology_text
            st.session_state.selected_sample = None

            with st.spinner("シミュレーション実行中..."):
                if FAULTRAY_AVAILABLE:
                    try:
                        results = run_simulation(topo)
                    except Exception as e:
                        st.error(f"シミュレーションエラー: {e}")
                        st.code(traceback.format_exc(), language="python")
                        return
                else:
                    st.warning("デモモードではカスタムトポロジーのシミュレーションは実行できません。サンプルを選択してください。")
                    return

            st.session_state.sim_result = results
            st.session_state.sim_history.append(results)
            if len(st.session_state.sim_history) > 20:
                st.session_state.sim_history = st.session_state.sim_history[-20:]
            st.session_state.inline_result = results
            st.rerun()


# ══════════════════════════════════════════════════════════════════
# ページ 3: 結果詳細
# ══════════════════════════════════════════════════════════════════

def page_results() -> None:
    """結果詳細: シナリオ一覧とフィルタ."""
    st.header("\U0001f4cb 結果詳細")
    st.caption(
        "シミュレーションで発見されたすべての障害シナリオを確認できます。"
    )

    result = st.session_state.sim_result
    if result is None:
        st.markdown("""
        <div class="empty-state">
            <h3>まだシミュレーションを実行していません</h3>
            <p>シミュレーションを実行すると、ここに詳細な結果が表示されます。</p>
        </div>
        """, unsafe_allow_html=True)
        if st.button("\u26a1 シミュレーションを始める", type="primary"):
            st.session_state.current_page = "page_simulation"
            st.rerun()
        return

    # -- スコアとサマリー
    col_score, col_stats = st.columns([1, 2])

    with col_score:
        render_score_gauge(result["resilience_score"])

    with col_stats:
        st.markdown("#### シナリオ集計")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("総数", result["total_scenarios"])
        c2.metric(
            "\U0001f6a8 CRITICAL",
            result["critical"],
            help="即座に対応が必要な重大な障害シナリオです",
        )
        c3.metric(
            "\u26a0\ufe0f WARNING",
            result["warning"],
            help="注意が必要な障害シナリオです",
        )
        c4.metric(
            "\u2705 PASS",
            result["passed"],
            help="冗長化が機能しており問題のないシナリオです",
        )

    st.markdown("---")

    # -- フィルタ
    st.markdown("#### 障害シナリオ一覧")

    filter_col, _ = st.columns([1, 3])
    with filter_col:
        severity_filter = st.selectbox(
            "フィルタ",
            ["すべて", "CRITICAL のみ", "WARNING 以上", "PASS のみ"],
            help="重要度でシナリオを絞り込めます",
        )

    scenarios = result.get("scenarios", [])
    if severity_filter == "CRITICAL のみ":
        scenarios = [s for s in scenarios if s["severity"] == "CRITICAL"]
    elif severity_filter == "WARNING 以上":
        scenarios = [s for s in scenarios if s["severity"] in ("CRITICAL", "WARNING")]
    elif severity_filter == "PASS のみ":
        scenarios = [s for s in scenarios if s["severity"] == "PASS"]

    # リスクスコア降順
    scenarios_sorted = sorted(scenarios, key=lambda x: x["risk_score"], reverse=True)

    st.caption(f"{len(scenarios_sorted)}件のシナリオ")

    if not scenarios_sorted:
        st.info("該当するシナリオがありません")
    else:
        # 最初の10件を表示、残りはexpanderにまとめる
        _INITIAL_DISPLAY = 10
        for scenario in scenarios_sorted[:_INITIAL_DISPLAY]:
            render_scenario_card(scenario)
        if len(scenarios_sorted) > _INITIAL_DISPLAY:
            _remaining = len(scenarios_sorted) - _INITIAL_DISPLAY
            with st.expander(f"残り{_remaining}件のシナリオを表示"):
                for scenario in scenarios_sorted[_INITIAL_DISPLAY:]:
                    render_scenario_card(scenario)

    # -- JSON エクスポート
    st.markdown("---")
    st.markdown("#### 結果エクスポート")
    export_data = json.dumps(result, ensure_ascii=False, indent=2)
    st.download_button(
        label="\U0001f4e5 JSON でダウンロード",
        data=export_data,
        file_name="faultray-results.json",
        mime="application/json",
    )
    with st.expander("JSONプレビュー"):
        st.code(export_data[:3000] + ("..." if len(export_data) > 3000 else ""), language="json")


# ══════════════════════════════════════════════════════════════════
# ページ 4: 改善提案
# ══════════════════════════════════════════════════════════════════

def page_suggestions() -> None:
    """改善提案: 発見された問題と対策の一覧."""
    st.header("\U0001f4a1 改善提案")
    st.caption("発見された問題とその対策を優先度順に確認できます。")

    result = st.session_state.sim_result
    if result is None:
        st.markdown("""
        <div class="empty-state">
            <h3>まだシミュレーションを実行していません</h3>
            <p>シミュレーションを実行すると、ここに改善提案が表示されます。</p>
        </div>
        """, unsafe_allow_html=True)
        if st.button("\u26a1 シミュレーションを始める", type="primary"):
            st.session_state.current_page = "page_simulation"
            st.rerun()
        return

    suggestions = result.get("suggestions", [])

    if not suggestions:
        st.success("現在、対応が必要な改善提案はありません。")
        return

    # -- サマリー
    critical_count = sum(1 for s in suggestions if isinstance(s, dict) and s.get("priority") == "critical")
    warning_count = sum(1 for s in suggestions if isinstance(s, dict) and s.get("priority") == "warning")
    info_count = sum(1 for s in suggestions if isinstance(s, dict) and s.get("priority") == "info")

    col1, col2, col3 = st.columns(3)
    col1.metric(
        "\U0001f6a8 CRITICAL",
        f"{critical_count}件",
        help="即座に対応が必要な重大な問題です",
    )
    col2.metric(
        "\u26a0\ufe0f WARNING",
        f"{warning_count}件",
        help="早めに対応すべき問題です",
    )
    col3.metric(
        "\u2139\ufe0f 情報",
        f"{info_count}件",
        help="参考情報です",
    )

    st.markdown("---")

    # -- 提案一覧（優先度順）
    priority_order = {"critical": 0, "warning": 1, "info": 2}

    # dict形式と文字列形式の両方に対応
    normalized_suggestions: list[dict[str, str]] = []
    for s in suggestions:
        if isinstance(s, dict):
            normalized_suggestions.append(s)
        else:
            normalized_suggestions.append({"title": str(s), "detail": "", "priority": "info"})

    sorted_suggestions = sorted(
        normalized_suggestions,
        key=lambda x: priority_order.get(x.get("priority", "info"), 2),
    )

    for i, sug in enumerate(sorted_suggestions, 1):
        priority = sug.get("priority", "info")
        if priority == "critical":
            card_class = "suggestion-card-critical"
            badge = '<span style="background:#7f1d1d;color:#fca5a5;padding:2px 8px;border-radius:999px;font-size:0.8em">CRITICAL</span>'
        elif priority == "warning":
            card_class = "suggestion-card-warning"
            badge = '<span style="background:#78350f;color:#fcd34d;padding:2px 8px;border-radius:999px;font-size:0.8em">WARNING</span>'
        else:
            card_class = "suggestion-card-info"
            badge = '<span style="background:#1e3a5f;color:#93c5fd;padding:2px 8px;border-radius:999px;font-size:0.8em">INFO</span>'

        detail = sug.get("detail", "")
        st.markdown(
            f'<div class="suggestion-card {card_class}">'
            f'{badge}  '
            f'<strong>{i}. {sug["title"]}</strong><br>'
            f'<span style="color:#6c757d;margin-top:4px;display:inline-block">{detail}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # -- シナリオとの紐付け
    st.markdown("---")
    st.markdown("#### 関連するCRITICALシナリオ")
    scenarios = result.get("scenarios", [])
    critical_scenarios = [s for s in scenarios if s["severity"] == "CRITICAL"]
    if critical_scenarios:
        for scenario in critical_scenarios:
            render_scenario_card(scenario)
    else:
        st.success("CRITICALシナリオは見つかりませんでした。")


# ══════════════════════════════════════════════════════════════════
# ページ 5: 設定
# ══════════════════════════════════════════════════════════════════

def page_settings() -> None:
    """設定: トポロジーの保存/読み込み."""
    st.header("\u2699\ufe0f 設定")
    st.caption("トポロジーの保存・読み込みとデータ管理ができます。")

    # -- トポロジーの保存
    st.subheader("トポロジーの保存")

    current_yaml = st.session_state.topology_yaml
    if current_yaml:
        st.caption("現在のトポロジーをファイルとしてダウンロードできます。")
        st.download_button(
            label="\U0001f4e5 YAML でダウンロード",
            data=current_yaml,
            file_name="faultray-topology.yaml",
            mime="text/yaml",
        )
        with st.expander("現在のトポロジー"):
            st.code(current_yaml[:2000] + ("..." if len(current_yaml) > 2000 else ""), language="yaml")
    else:
        st.caption("トポロジーがまだ入力されていません。シミュレーションページで入力してください。")

    st.markdown("---")

    # -- トポロジーの読み込み
    st.subheader("トポロジーの読み込み")
    st.caption("ファイルからトポロジーを読み込めます（YAML または JSON）。")

    uploaded = st.file_uploader(
        "ファイルを選択",
        type=["yaml", "yml", "json"],
        help="YAML(.yaml, .yml) または JSON(.json) ファイルをアップロードしてください",
    )
    if uploaded is not None:
        try:
            content = uploaded.read().decode("utf-8")
        except UnicodeDecodeError:
            st.error("ファイルのエンコーディングがUTF-8ではありません。UTF-8で保存し直してください。")
            content = None
        if content is not None:
            try:
                parse_topology(content)  # バリデーション
                st.session_state.topology_yaml = content
                st.session_state.selected_sample = None
                st.success(f"ファイル「{uploaded.name}」を読み込みました。シミュレーションページで使用できます。")
            except Exception as e:
                st.error(f"ファイルのパースに失敗しました: {e}")

    st.markdown("---")

    # -- データ管理
    st.subheader("データ管理")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("\U0001f5d1\ufe0f シミュレーション結果をリセット"):
            st.session_state.sim_result = None
            st.session_state.sim_history = []
            st.session_state.inline_result = None
            st.success("シミュレーション結果をリセットしました。")
    with col2:
        if st.button("\U0001f5d1\ufe0f トポロジーをリセット"):
            st.session_state.topology_yaml = ""
            st.session_state.selected_sample = None
            st.session_state.parsed_topology = None
            st.session_state.show_topology_preview = False
            st.success("トポロジーをリセットしました。")

    st.markdown("---")

    # -- 依存タイプの説明
    st.subheader("用語集")
    st.caption("FaultRayで使われる主な用語の説明です。")

    terms = [
        ("耐障害スコア", "インフラがどれだけ障害に強いかを0-100で示す総合スコアです。80以上が良好、60未満は危険です。"),
        ("カスケード伝播", "1つのコンポーネントの障害が、依存関係を通じて連鎖的に他のコンポーネントに影響すること。ドミノ倒しのイメージです。"),
        ("requires（必須依存）", "ターゲットが停止するとソースも停止する依存関係。例: アプリサーバー -> データベース"),
        ("optional（任意依存）", "ターゲットが停止してもソースは部分的に動作できる依存関係。例: アプリサーバー -> キャッシュ"),
        ("async（非同期依存）", "キューやイベントバスを介した遅延性のある依存関係。即座には影響しないが、時間経過で問題が発生します。"),
        ("サーキットブレーカー", "障害が伝播しないようにする仕組み。一定数のエラーが発生すると、それ以上のリクエストを遮断します。"),
        ("フェイルオーバー", "プライマリが停止した際に、待機系（レプリカ）に自動的に切り替える仕組みです。"),
        ("リスクスコア", "各障害シナリオの深刻度を0-10で示すスコアです。影響範囲と伝播の深さから算出します。"),
    ]

    for term, explanation in terms:
        st.markdown(f"**{term}**")
        st.caption(explanation)


# ══════════════════════════════════════════════════════════════════
# デモ用 財務影響データ（エンジン未使用時）
# ══════════════════════════════════════════════════════════════════

DEMO_FINANCIAL: dict[str, dict[str, Any]] = {
    "Webアプリ 3層構成": {
        "resilience_score": 68.4,
        "total_annual_loss": 756_000.0,
        "total_downtime_hours": 87.6,
        "component_impacts": [
            {"component_id": "postgres", "component_type": "database", "availability": 0.9990, "annual_downtime_hours": 8.76, "annual_loss": 87_600.0, "cost_per_hour": 10_000.0, "risk_description": "2 dependent component(s)"},
            {"component_id": "nginx", "component_type": "load_balancer", "availability": 0.9995, "annual_downtime_hours": 4.38, "annual_loss": 35_040.0, "cost_per_hour": 8_000.0, "risk_description": "Baseline operational risk"},
            {"component_id": "app-1", "component_type": "app_server", "availability": 0.9992, "annual_downtime_hours": 7.01, "annual_loss": 35_050.0, "cost_per_hour": 5_000.0, "risk_description": "1 dependent component(s)"},
            {"component_id": "app-2", "component_type": "app_server", "availability": 0.9992, "annual_downtime_hours": 7.01, "annual_loss": 35_050.0, "cost_per_hour": 5_000.0, "risk_description": "1 dependent component(s)"},
            {"component_id": "redis", "component_type": "cache", "availability": 0.9997, "annual_downtime_hours": 2.63, "annual_loss": 5_260.0, "cost_per_hour": 2_000.0, "risk_description": "Baseline operational risk"},
            {"component_id": "rabbitmq", "component_type": "queue", "availability": 0.9996, "annual_downtime_hours": 3.50, "annual_loss": 10_500.0, "cost_per_hour": 3_000.0, "risk_description": "Baseline operational risk"},
        ],
        "recommended_fixes": [
            {"component_id": "postgres", "description": "DBレプリカを追加 (PostgreSQL)", "annual_cost": 24_000.0, "annual_savings": 420_000.0, "roi": 17.5, "difficulty": "Medium", "timeline": "1 week"},
            {"component_id": "redis", "description": "Cacheレプリケーション (Redis)", "annual_cost": 4_800.0, "annual_savings": 180_000.0, "roi": 37.5, "difficulty": "Easy", "timeline": "1 week"},
            {"component_id": "nginx", "description": "LB冗長化 (nginx)", "annual_cost": 6_000.0, "annual_savings": 156_000.0, "roi": 26.0, "difficulty": "Easy", "timeline": "3 days"},
        ],
        "total_fix_cost": 34_800.0,
        "total_savings": 756_000.0,
        "roi": 21.7,
    },
    "マイクロサービス構成": {
        "resilience_score": 55.2,
        "total_annual_loss": 1_250_000.0,
        "total_downtime_hours": 145.2,
        "component_impacts": [
            {"component_id": "orders-db", "component_type": "database", "availability": 0.9985, "annual_downtime_hours": 13.14, "annual_loss": 131_400.0, "cost_per_hour": 10_000.0, "risk_description": "3 dependent component(s)"},
            {"component_id": "api-gateway", "component_type": "load_balancer", "availability": 0.9990, "annual_downtime_hours": 8.76, "annual_loss": 70_080.0, "cost_per_hour": 8_000.0, "risk_description": "3 dependent component(s)"},
            {"component_id": "users-db", "component_type": "database", "availability": 0.9988, "annual_downtime_hours": 10.51, "annual_loss": 105_100.0, "cost_per_hour": 10_000.0, "risk_description": "1 dependent component(s)"},
            {"component_id": "event-bus", "component_type": "queue", "availability": 0.9992, "annual_downtime_hours": 7.01, "annual_loss": 21_030.0, "cost_per_hour": 3_000.0, "risk_description": "2 dependent component(s)"},
        ],
        "recommended_fixes": [
            {"component_id": "orders-db", "description": "Orders DBレプリカ追加", "annual_cost": 24_000.0, "annual_savings": 580_000.0, "roi": 24.2, "difficulty": "Medium", "timeline": "1 week"},
            {"component_id": "users-db", "description": "Users DBレプリカ追加", "annual_cost": 24_000.0, "annual_savings": 320_000.0, "roi": 13.3, "difficulty": "Medium", "timeline": "1 week"},
            {"component_id": "api-gateway", "description": "API Gateway Multi-AZデプロイ", "annual_cost": 6_000.0, "annual_savings": 350_000.0, "roi": 58.3, "difficulty": "Hard", "timeline": "1 month"},
        ],
        "total_fix_cost": 54_000.0,
        "total_savings": 1_250_000.0,
        "roi": 23.1,
    },
    "AIパイプライン": {
        "resilience_score": 72.1,
        "total_annual_loss": 520_000.0,
        "total_downtime_hours": 62.3,
        "component_impacts": [
            {"component_id": "claude-api", "component_type": "llm_endpoint", "availability": 0.9990, "annual_downtime_hours": 8.76, "annual_loss": 35_040.0, "cost_per_hour": 4_000.0, "risk_description": "Single point of failure (no replicas); 2 dependent component(s)"},
            {"component_id": "postgres-db", "component_type": "database", "availability": 0.9992, "annual_downtime_hours": 7.01, "annual_loss": 70_100.0, "cost_per_hour": 10_000.0, "risk_description": "1 dependent component(s)"},
            {"component_id": "router-agent", "component_type": "agent_orchestrator", "availability": 0.9994, "annual_downtime_hours": 5.26, "annual_loss": 26_300.0, "cost_per_hour": 5_000.0, "risk_description": "2 dependent component(s)"},
        ],
        "recommended_fixes": [
            {"component_id": "claude-api", "description": "LLMフォールバック自動化 (Claude -> OpenAI)", "annual_cost": 6_000.0, "annual_savings": 210_000.0, "roi": 35.0, "difficulty": "Medium", "timeline": "2 weeks"},
            {"component_id": "postgres-db", "description": "PostgreSQLレプリカ追加", "annual_cost": 24_000.0, "annual_savings": 310_000.0, "roi": 12.9, "difficulty": "Easy", "timeline": "1 week"},
        ],
        "total_fix_cost": 30_000.0,
        "total_savings": 520_000.0,
        "roi": 17.3,
    },
}


def _get_financial_report() -> dict[str, Any] | None:
    """Get financial report from session state or generate demo data."""
    if st.session_state.financial_report is not None:
        return st.session_state.financial_report

    # Try to generate from sim result + topology
    result = st.session_state.sim_result
    if result is None:
        return None

    # Use demo financial data matched to the selected sample
    sample_key = st.session_state.selected_sample
    if sample_key and sample_key in DEMO_FINANCIAL:
        report = DEMO_FINANCIAL[sample_key]
        st.session_state.financial_report = report
        return report

    # Fallback: generate from simulation result with estimated values
    scenarios = result.get("scenarios", [])
    total_loss = 0.0
    component_impacts = []
    for s in scenarios:
        if s["severity"] == "CRITICAL":
            est_loss = s["risk_score"] * 50_000
        elif s["severity"] == "WARNING":
            est_loss = s["risk_score"] * 15_000
        else:
            est_loss = 0
        total_loss += est_loss
        if est_loss > 0:
            component_impacts.append({
                "component_id": s["name"],
                "component_type": "unknown",
                "availability": max(0.0, 1.0 - s["risk_score"] / 1000),
                "annual_downtime_hours": round(s["risk_score"] * 2.5, 2),
                "annual_loss": round(est_loss, 2),
                "cost_per_hour": 5_000.0,
                "risk_description": s.get("suggestion", "") or "",
            })
    component_impacts.sort(key=lambda x: x["annual_loss"], reverse=True)
    report = {
        "resilience_score": result["resilience_score"],
        "total_annual_loss": round(total_loss, 2),
        "total_downtime_hours": round(sum(c["annual_downtime_hours"] for c in component_impacts), 2),
        "component_impacts": component_impacts,
        "recommended_fixes": [],
        "total_fix_cost": 0.0,
        "total_savings": 0.0,
        "roi": 0.0,
    }
    st.session_state.financial_report = report
    return report


def _generate_exec_pdf(financial: dict[str, Any]) -> bytes:
    """Generate executive damage report PDF as HTML-based bytes."""
    import datetime as _dt
    today = _dt.date.today().isoformat()
    impacts_html = ""
    for c in financial.get("component_impacts", [])[:10]:
        impacts_html += (
            f"<tr><td>{c['component_id']}</td><td>{c['component_type']}</td>"
            f"<td style='text-align:right'>${c['annual_loss']:,.0f}</td>"
            f"<td style='text-align:right'>{c['annual_downtime_hours']:.1f}h</td>"
            f"<td>{c['risk_description'][:60]}</td></tr>"
        )
    fixes_html = ""
    for f in financial.get("recommended_fixes", []):
        fixes_html += (
            f"<tr><td>{f['component_id']}</td><td>{f['description']}</td>"
            f"<td style='text-align:right'>${f['annual_cost']:,.0f}</td>"
            f"<td style='text-align:right'>${f['annual_savings']:,.0f}</td>"
            f"<td style='text-align:right'>{f['roi']:.1f}x</td></tr>"
        )
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>body{{font-family:Inter,Helvetica,sans-serif;color:#1e293b;margin:40px}}
h1{{color:#0f172a;border-bottom:2px solid #2563eb;padding-bottom:8px}}
h2{{color:#334155;margin-top:24px}}
table{{border-collapse:collapse;width:100%;margin:12px 0}}
th,td{{border:1px solid #e2e8f0;padding:8px 12px;font-size:13px}}
th{{background:#f1f5f9;font-weight:600;text-align:left}}
.metric-box{{display:inline-block;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:16px 24px;margin:8px;text-align:center}}
.metric-box .value{{font-size:24px;font-weight:800;color:#0f172a}}
.metric-box .label{{font-size:12px;color:#64748b}}
.footer{{margin-top:32px;color:#94a3b8;font-size:11px;border-top:1px solid #e2e8f0;padding-top:8px}}
</style></head><body>
<h1>Infrastructure Resilience Damage Report</h1>
<p style="color:#64748b">Date: {today} | Generated by FaultRay</p>
<h2>Executive Summary</h2>
<div class="metric-box"><div class="value">${financial['total_annual_loss']:,.0f}</div><div class="label">Estimated Annual Loss</div></div>
<div class="metric-box"><div class="value">{financial['total_downtime_hours']:.1f}h</div><div class="label">Estimated Annual Downtime</div></div>
<div class="metric-box"><div class="value">{financial['resilience_score']:.1f}/100</div><div class="label">Resilience Score</div></div>
<h2>Risk by Component</h2>
<table><tr><th>Component</th><th>Type</th><th>Annual Loss</th><th>Downtime</th><th>Risk</th></tr>{impacts_html}</table>
<h2>Recommended Fixes</h2>
<table><tr><th>Component</th><th>Action</th><th>Cost/yr</th><th>Savings/yr</th><th>ROI</th></tr>{fixes_html}</table>
<h2>Investment Summary</h2>
<p>Total fix cost: <strong>${financial.get('total_fix_cost', 0):,.0f}/yr</strong> |
Total savings: <strong>${financial.get('total_savings', 0):,.0f}/yr</strong> |
ROI: <strong>{financial.get('roi', 0):.1f}x</strong></p>
<div class="footer">FaultRay - Zero-risk chaos engineering | (c) 2025-2026 Yutaro Maeda</div>
</body></html>"""
    return html.encode("utf-8")


def _generate_remediation_csv(financial: dict[str, Any]) -> str:
    """Generate remediation plan as CSV string."""
    import io as _io
    import csv as _csv
    buf = _io.StringIO()
    w = _csv.writer(buf)
    w.writerow(["Priority", "Component", "Action", "Annual Cost (USD)", "Annual Savings (USD)", "ROI", "Difficulty", "Timeline"])
    for i, f in enumerate(financial.get("recommended_fixes", []), 1):
        w.writerow([
            i, f["component_id"], f["description"],
            f"${f['annual_cost']:,.0f}", f"${f['annual_savings']:,.0f}",
            f"{f['roi']:.1f}x",
            f.get("difficulty", "Medium"), f.get("timeline", "1 week"),
        ])
    return buf.getvalue()


def _generate_ics_calendar(fixes: list[dict[str, Any]]) -> str:
    """Generate .ics calendar file from recommended fixes."""
    import datetime as _dt
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//FaultRay//Remediation//EN",
    ]
    start = _dt.date.today() + _dt.timedelta(days=1)
    for i, f in enumerate(fixes):
        timeline = f.get("timeline", "1 week")
        if "day" in timeline:
            days = int("".join(c for c in timeline if c.isdigit()) or "3")
        elif "month" in timeline:
            days = 30
        else:
            days = 7
        end = start + _dt.timedelta(days=days)
        lines += [
            "BEGIN:VEVENT",
            f"SUMMARY:[FaultRay] {f['description']}",
            f"DESCRIPTION:Component: {f['component_id']}\\nCost: ${f['annual_cost']:,.0f}/yr\\nSavings: ${f['annual_savings']:,.0f}/yr\\nROI: {f['roi']:.1f}x",
            f"DTSTART;VALUE=DATE:{start.strftime('%Y%m%d')}",
            f"DTEND;VALUE=DATE:{end.strftime('%Y%m%d')}",
            f"UID:faultray-fix-{i}@faultray.local",
            "END:VEVENT",
        ]
        start = end
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines)


def _google_cal_url(title: str, description: str, start_date: str, end_date: str) -> str:
    """Generate Google Calendar event creation URL."""
    import urllib.parse
    base = "https://calendar.google.com/calendar/render?action=TEMPLATE"
    params = {"text": title, "details": description, "dates": f"{start_date}/{end_date}"}
    return f"{base}&{urllib.parse.urlencode(params)}"


def _generate_wbs_markdown(fixes: list[dict[str, Any]]) -> str:
    """Generate WBS (Work Breakdown Structure) in Markdown."""
    lines = ["# WBS: Infrastructure Resilience Improvement", ""]
    lines.append("## 1. Resilience Improvement Project")

    # Group by component type
    by_type: dict[str, list[dict[str, Any]]] = {}
    for f in fixes:
        ct = f.get("component_id", "other").split("-")[0] if "-" in f.get("component_id", "") else f.get("component_id", "other")
        by_type.setdefault(ct, []).append(f)

    section = 1
    for ct, items in by_type.items():
        section += 1
        lines.append(f"  ### 1.{section - 1}. {ct.upper()} Improvements")
        for j, item in enumerate(items, 1):
            lines.append(f"    - 1.{section - 1}.{j} {item['description']} ({item.get('timeline', '1 week')}, ${item['annual_cost']:,.0f}/yr)")
    return "\n".join(lines)


def _generate_wbs_csv(fixes: list[dict[str, Any]]) -> str:
    """Generate WBS as CSV."""
    import io as _io
    import csv as _csv
    buf = _io.StringIO()
    w = _csv.writer(buf)
    w.writerow(["WBS ID", "Task", "Component", "Timeline", "Annual Cost (USD)"])
    for i, f in enumerate(fixes, 1):
        w.writerow([f"1.{i}", f["description"], f["component_id"], f.get("timeline", "1 week"), f"${f['annual_cost']:,.0f}"])
    return buf.getvalue()


def _generate_raci_csv(fixes: list[dict[str, Any]]) -> str:
    """Generate RACI matrix as CSV."""
    import io as _io
    import csv as _csv
    buf = _io.StringIO()
    w = _csv.writer(buf)
    w.writerow(["Task", "Responsible (R)", "Accountable (A)", "Consulted (C)", "Informed (I)"])
    for f in fixes:
        w.writerow([f["description"], "Engineer", "PM", "DBA/SRE", "Executive"])
    return buf.getvalue()


def _generate_risk_register_csv(result: dict[str, Any]) -> str:
    """Generate risk register from simulation results."""
    import io as _io
    import csv as _csv
    buf = _io.StringIO()
    w = _csv.writer(buf)
    w.writerow(["ID", "Risk", "Severity", "Risk Score", "Affected Components", "Mitigation", "Residual Risk"])
    scenarios = result.get("scenarios", [])
    for i, s in enumerate(sorted(scenarios, key=lambda x: x["risk_score"], reverse=True), 1):
        if s["severity"] == "PASS":
            continue
        w.writerow([
            f"R-{i:03d}", s["name"], s["severity"], s["risk_score"],
            ", ".join(s.get("affected", [])),
            s.get("suggestion", "") or "N/A",
            "Low" if s["risk_score"] < 5 else "Medium" if s["risk_score"] < 8 else "High",
        ])
    return buf.getvalue()


def _generate_cost_estimate_html(fixes: list[dict[str, Any]]) -> bytes:
    """Generate cost estimate document as HTML."""
    import datetime as _dt
    today = _dt.date.today().isoformat()
    rows = ""
    total = 0.0
    for i, f in enumerate(fixes, 1):
        rows += f"<tr><td>{i}</td><td>{f['description']}</td><td>1 set</td><td>${f['annual_cost']:,.0f}/yr</td><td>${f['annual_cost']:,.0f}</td></tr>"
        total += f["annual_cost"]
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>body{{font-family:Inter,Helvetica,sans-serif;color:#1e293b;margin:40px}}
h1{{text-align:center}}table{{border-collapse:collapse;width:100%;margin:16px 0}}
th,td{{border:1px solid #cbd5e1;padding:8px 12px;font-size:13px}}th{{background:#f1f5f9}}</style>
</head><body>
<h1>Cost Estimate</h1>
<p>Subject: Infrastructure Resilience Improvement<br>Date: {today}<br>Generated by: FaultRay</p>
<table><tr><th>#</th><th>Item</th><th>Qty</th><th>Unit Price</th><th>Amount</th></tr>
{rows}
<tr style="font-weight:bold"><td colspan="4" style="text-align:right">Total (Annual)</td><td>${total:,.0f}</td></tr>
</table>
<p style="color:#64748b;font-size:11px;margin-top:24px">Note: Costs are annual estimates in USD.</p>
</body></html>"""
    return html.encode("utf-8")


def _generate_gantt_mermaid(fixes: list[dict[str, Any]]) -> str:
    """Generate Mermaid gantt chart definition."""
    import datetime as _dt
    lines = [
        "gantt",
        "    title Remediation Schedule",
        "    dateFormat YYYY-MM-DD",
    ]
    start = _dt.date.today() + _dt.timedelta(days=1)
    prev_id = None
    for i, f in enumerate(fixes):
        timeline = f.get("timeline", "1 week")
        if "day" in timeline:
            days = int("".join(c for c in timeline if c.isdigit()) or "3")
        elif "month" in timeline:
            days = 30
        else:
            days = 7
        task_id = f"t{i + 1}"
        section = f["component_id"].replace("-", " ").title()
        lines.append(f"    section {section}")
        if prev_id:
            lines.append(f"    {f['description'][:30]} :{task_id}, after {prev_id}, {days}d")
        else:
            lines.append(f"    {f['description'][:30]} :{task_id}, {start.strftime('%Y-%m-%d')}, {days}d")
        prev_id = task_id
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════
# ページ 6: AIガバナンス診断 (Governance Assessment)
# ══════════════════════════════════════════════════════════════════

def page_governance() -> None:
    """AIガバナンス診断: 25問の自己診断とスコア表示."""
    st.header("\U0001f3db\ufe0f AIガバナンス診断 (Governance Assessment)")
    st.caption("METI AI事業者ガイドライン v1.1 に基づく25問の自己診断。シミュレーション不要で単独利用可能です。")

    if not GOVERNANCE_AVAILABLE:
        st.warning("ガバナンスモジュールが利用できません。`pip install faultray` でインストールしてください。")
        st.info("以下はデモ表示です。実際の診断にはfaultrayパッケージが必要です。")

    # Framework selection
    framework_options = {"all": "全フレームワーク (All)", "meti": "METI v1.1", "iso": "ISO 42001", "act": "AI推進法"}
    fw_key = st.selectbox(
        "フレームワーク (Framework)",
        list(framework_options.keys()),
        format_func=lambda x: framework_options[x],
        index=0,
        key="gov_fw_select",
    )
    st.session_state.gov_framework = fw_key

    st.markdown("---")

    # Questions
    if GOVERNANCE_AVAILABLE:
        questions = METI_QUESTIONS
    else:
        # Minimal demo questions
        questions = []

    option_labels = ["0 - 未対応", "1 - 部分的", "2 - 概ね対応", "3 - 対応済み", "4 - 完全対応/継続改善"]

    if GOVERNANCE_AVAILABLE and questions:
        st.markdown("### 診断質問 (Assessment Questions)")
        st.caption("各質問について最も当てはまる選択肢を選んでください。リアルタイムでスコアが更新されます。")

        # Group by category
        cat_questions: dict[str, list[Any]] = {}
        for q in questions:
            cat_questions.setdefault(q.category_id, []).append(q)

        cat_title_map = {c.category_id: c.title for c in METI_CATEGORIES}

        answers = st.session_state.gov_answers.copy()

        for cat_id in sorted(cat_questions.keys()):
            cat_title = cat_title_map.get(cat_id, cat_id)
            with st.expander(f"{cat_title} ({len(cat_questions[cat_id])})", expanded=False):
                for q in cat_questions[cat_id]:
                    st.markdown(
                        f'<div class="gov-question-card"><span class="q-number">{q.question_id}</span> '
                        f'{q.text}</div>',
                        unsafe_allow_html=True,
                    )
                    current_val = answers.get(q.question_id, 0)
                    new_val = st.select_slider(
                        f"{q.question_id}",
                        options=list(range(5)),
                        value=current_val,
                        format_func=lambda x, opts=q.options: opts[x] if x < len(opts) else str(x),
                        key=f"gov_q_{q.question_id}",
                        label_visibility="collapsed",
                    )
                    answers[q.question_id] = new_val

        st.session_state.gov_answers = answers

        # Run assessment
        st.markdown("---")
        col_run, col_reset = st.columns([1, 1])
        with col_run:
            if st.button("\U0001f4ca 診断結果を表示", type="primary", use_container_width=True):
                assessor = GovernanceAssessor()
                result = assessor.assess(answers)
                st.session_state.gov_result = result
        with col_reset:
            if st.button("\U0001f5d1\ufe0f リセット", use_container_width=True):
                st.session_state.gov_answers = {}
                st.session_state.gov_result = None
                st.rerun()

        # Real-time score preview
        answered = sum(1 for v in answers.values() if v > 0)
        total_q = len(questions)
        avg_score = sum(answers.values()) / max(total_q, 1)
        preview_pct = round(avg_score / 4.0 * 100, 1)
        st.progress(answered / total_q if total_q > 0 else 0.0, text=f"回答済み: {answered}/{total_q} | 推定スコア: {preview_pct}%")

    # --- Results display ---
    gov_result = st.session_state.gov_result
    if gov_result is not None and GOVERNANCE_AVAILABLE:
        st.markdown("---")
        st.markdown("### 診断結果 (Assessment Results)")

        # Overall score gauge
        score = gov_result.overall_score
        maturity = gov_result.maturity_level
        maturity_label = MATURITY_LABELS.get(maturity, "")

        if score >= 70:
            color = "#22c55e"
        elif score >= 40:
            color = "#f59e0b"
        else:
            color = "#ef4444"

        st.markdown(
            f'<div class="score-gauge">'
            f'<div class="score-number" style="color:{color}">{score:.1f}</div>'
            f'<div class="score-sublabel">/ 100</div>'
            f'<div class="score-label" style="color:{color}">Maturity Level {maturity}/5 - {maturity_label}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # Per-category bar chart (text-based)
        st.markdown("#### カテゴリ別スコア (Category Scores)")
        for cs in gov_result.category_scores:
            pct = cs.score_percent
            bar_width = max(int(pct / 2), 1)
            bar_color = "#22c55e" if pct >= 70 else "#f59e0b" if pct >= 40 else "#ef4444"
            st.markdown(
                f'<div style="margin-bottom:8px">'
                f'<div style="display:flex;justify-content:space-between;margin-bottom:2px">'
                f'<span style="font-weight:600;font-size:0.9em">{cs.category_title}</span>'
                f'<span style="font-weight:700;color:{bar_color}">{pct:.0f}%</span></div>'
                f'<div style="background:#e2e8f0;border-radius:4px;height:8px;width:100%">'
                f'<div style="background:{bar_color};border-radius:4px;height:8px;width:{pct}%"></div>'
                f'</div></div>',
                unsafe_allow_html=True,
            )

        # Gap analysis
        if gov_result.top_gaps:
            st.markdown("#### ギャップ分析 (Gap Analysis)")
            for gap in gov_result.top_gaps[:7]:
                st.markdown(f"- {gap}")

        # Framework coverage
        if gov_result.framework_coverage:
            st.markdown("#### フレームワークカバレッジ (Framework Coverage)")
            fc_cols = st.columns(len(gov_result.framework_coverage))
            for col, (fw_name, fw_pct) in zip(fc_cols, gov_result.framework_coverage.items()):
                with col:
                    st.metric(fw_name, f"{fw_pct:.1f}%")

        # Cross-mapping view
        if fw_key == "all" and GOVERNANCE_AVAILABLE:
            st.markdown("#### クロスマッピング (Cross-Framework Mapping)")
            mapping_data = []
            for entry in CROSS_MAPPING:
                mapping_data.append({
                    "Theme": entry.theme,
                    "METI": ", ".join(entry.meti_ids) or "-",
                    "ISO 42001": ", ".join(entry.iso_ids) or "-",
                    "AI推進法": ", ".join(entry.act_ids) or "-",
                })
            st.dataframe(mapping_data, use_container_width=True)

        # Recommendations
        if gov_result.top_recommendations:
            st.markdown("#### 改善推奨事項 (Recommendations)")
            for i, rec in enumerate(gov_result.top_recommendations[:5], 1):
                st.markdown(
                    f'<div class="suggestion-card suggestion-card-warning">'
                    f'<strong>{i}.</strong> {rec}'
                    f'</div>',
                    unsafe_allow_html=True,
                )

        # Export
        st.markdown("---")
        st.markdown("#### エクスポート (Export)")
        export_data = {
            "overall_score": gov_result.overall_score,
            "maturity_level": gov_result.maturity_level,
            "framework_coverage": gov_result.framework_coverage,
            "categories": [
                {"id": cs.category_id, "title": cs.category_title, "score": cs.score_percent, "maturity": cs.maturity_level}
                for cs in gov_result.category_scores
            ],
            "gaps": gov_result.top_gaps,
            "recommendations": gov_result.top_recommendations,
        }
        st.download_button(
            "\U0001f4e5 JSON でダウンロード",
            data=json.dumps(export_data, ensure_ascii=False, indent=2),
            file_name="faultray-governance-assessment.json",
            mime="application/json",
        )

    elif not GOVERNANCE_AVAILABLE:
        st.markdown("---")
        st.info("ガバナンスモジュールをインストールすると、25問の診断質問に回答してリアルタイムでスコアを確認できます。")


# ══════════════════════════════════════════════════════════════════
# ページ 7: 損害レポート (Financial Impact / Executive Report)
# ══════════════════════════════════════════════════════════════════

def page_financial() -> None:
    """損害レポート: 財務影響の可視化."""
    st.header("\U0001f4b0 損害レポート (Financial Impact Report)")
    st.caption("シミュレーション結果をもとに、年間推定損失額・ダウンタイム・リスクを可視化します。")

    result = st.session_state.sim_result
    if result is None:
        st.markdown("""
        <div class="empty-state">
            <h3>シミュレーションを先に実行してください</h3>
            <p>損害レポートの生成にはシミュレーション結果が必要です。</p>
        </div>
        """, unsafe_allow_html=True)
        if st.button("\u26a1 シミュレーションを始める", type="primary"):
            st.session_state.current_page = "page_simulation"
            st.rerun()
        return

    financial = _get_financial_report()
    if financial is None:
        st.warning("財務データを生成できませんでした。")
        return

    # --- Big numbers (executive summary) ---
    st.markdown("### Executive Summary")
    c1, c2, c3 = st.columns(3)
    with c1:
        loss_color = "#ef4444" if financial["total_annual_loss"] > 500_000 else "#f59e0b" if financial["total_annual_loss"] > 100_000 else "#22c55e"
        st.markdown(
            f'<div class="exec-metric"><div class="exec-value" style="color:{loss_color}">'
            f'${financial["total_annual_loss"]:,.0f}</div>'
            f'<div class="exec-label">Estimated Annual Loss</div></div>',
            unsafe_allow_html=True,
        )
    with c2:
        dt_color = "#ef4444" if financial["total_downtime_hours"] > 100 else "#f59e0b" if financial["total_downtime_hours"] > 24 else "#22c55e"
        st.markdown(
            f'<div class="exec-metric"><div class="exec-value" style="color:{dt_color}">'
            f'{financial["total_downtime_hours"]:.1f}h</div>'
            f'<div class="exec-label">Estimated Annual Downtime</div></div>',
            unsafe_allow_html=True,
        )
    with c3:
        rs = financial["resilience_score"]
        rs_color = "#22c55e" if rs >= 80 else "#f59e0b" if rs >= 60 else "#ef4444"
        st.markdown(
            f'<div class="exec-metric"><div class="exec-value" style="color:{rs_color}">'
            f'{rs:.1f}</div>'
            f'<div class="exec-label">Resilience Score / 100</div></div>',
            unsafe_allow_html=True,
        )

    # --- Top risks table ---
    st.markdown("---")
    st.markdown("### Top Risks by Financial Impact")
    impacts = financial.get("component_impacts", [])
    if impacts:
        table_data = []
        for c in impacts[:10]:
            table_data.append({
                "Component": c["component_id"],
                "Type": c["component_type"],
                "Annual Loss (USD)": f"${c['annual_loss']:,.0f}",
                "Downtime (hrs/yr)": f"{c['annual_downtime_hours']:.1f}",
                "Availability": f"{c['availability'] * 100:.3f}%",
                "Risk": c["risk_description"][:50],
            })
        st.dataframe(table_data, use_container_width=True)

    # --- Loss by component (bar chart style) ---
    st.markdown("### Loss Distribution by Component")
    max_loss = max((c["annual_loss"] for c in impacts), default=1)
    for c in impacts[:8]:
        pct = (c["annual_loss"] / max_loss * 100) if max_loss > 0 else 0
        bar_color = "#ef4444" if pct > 60 else "#f59e0b" if pct > 30 else "#2563eb"
        st.markdown(
            f'<div style="margin-bottom:8px">'
            f'<div style="display:flex;justify-content:space-between;margin-bottom:2px">'
            f'<span style="font-weight:600;font-size:0.9em">{c["component_id"]}</span>'
            f'<span style="font-weight:700;color:{bar_color}">${c["annual_loss"]:,.0f}</span></div>'
            f'<div style="background:#e2e8f0;border-radius:4px;height:10px;width:100%">'
            f'<div style="background:{bar_color};border-radius:4px;height:10px;width:{pct:.0f}%"></div>'
            f'</div></div>',
            unsafe_allow_html=True,
        )

    # --- PDF Download ---
    st.markdown("---")
    st.markdown("### Download Executive Report")
    pdf_bytes = _generate_exec_pdf(financial)
    st.download_button(
        "\U0001f4e5 Executive Report (HTML)",
        data=pdf_bytes,
        file_name="faultray-damage-report.html",
        mime="text/html",
    )
    st.caption("HTML format - open in browser and print to PDF for executive presentation.")


# ══════════════════════════════════════════════════════════════════
# ページ 8: 改善計画 (Remediation Plan)
# ══════════════════════════════════════════════════════════════════

def page_remediation() -> None:
    """改善計画: 優先度順の改善施策とタイムライン."""
    st.header("\U0001f527 改善計画 (Remediation Plan)")
    st.caption("シミュレーション結果に基づき、優先度・コスト・スケジュール・ROIを提示します。")

    result = st.session_state.sim_result
    if result is None:
        st.markdown("""
        <div class="empty-state">
            <h3>シミュレーションを先に実行してください</h3>
            <p>改善計画の生成にはシミュレーション結果が必要です。</p>
        </div>
        """, unsafe_allow_html=True)
        if st.button("\u26a1 シミュレーションを始める", type="primary"):
            st.session_state.current_page = "page_simulation"
            st.rerun()
        return

    financial = _get_financial_report()
    if financial is None:
        st.warning("財務データを生成できませんでした。")
        return

    fixes = financial.get("recommended_fixes", [])
    if not fixes:
        st.info("現在の構成では推奨される改善施策がありません。")
        return

    # --- Priority-ordered fix list ---
    st.markdown("### Priority-Ordered Remediation Actions")
    for i, f in enumerate(fixes, 1):
        difficulty = f.get("difficulty", "Medium")
        if difficulty == "Easy":
            diff_color = "#22c55e"
            timeline_class = "timeline-item-low"
        elif difficulty == "Hard":
            diff_color = "#ef4444"
            timeline_class = "timeline-item-high"
        else:
            diff_color = "#f59e0b"
            timeline_class = "timeline-item-medium"

        st.markdown(
            f'<div class="timeline-item {timeline_class}">'
            f'<div style="display:flex;justify-content:space-between;align-items:center">'
            f'<div><strong>#{i}. {f["description"]}</strong><br>'
            f'<span style="color:#64748b;font-size:0.9em">Component: {f["component_id"]}</span></div>'
            f'<div style="text-align:right">'
            f'<span style="font-weight:700;color:#2563eb">ROI: {f["roi"]:.1f}x</span></div></div>'
            f'<div style="display:flex;gap:24px;margin-top:8px;font-size:0.9em;color:#475569">'
            f'<span>Cost: ${f["annual_cost"]:,.0f}/yr</span>'
            f'<span>Savings: ${f["annual_savings"]:,.0f}/yr</span>'
            f'<span style="color:{diff_color};font-weight:600">Difficulty: {difficulty}</span>'
            f'<span>Timeline: {f.get("timeline", "1 week")}</span>'
            f'</div></div>',
            unsafe_allow_html=True,
        )

    # --- Gantt-style timeline ---
    st.markdown("---")
    st.markdown("### Implementation Timeline")

    import datetime as _dt
    start = _dt.date.today() + _dt.timedelta(days=1)
    for i, f in enumerate(fixes):
        timeline = f.get("timeline", "1 week")
        if "day" in timeline:
            days = int("".join(c for c in timeline if c.isdigit()) or "3")
        elif "month" in timeline:
            days = 30
        else:
            days = 7
        end = start + _dt.timedelta(days=days)
        pct = min(days / 30 * 100, 100)
        st.markdown(
            f"**Week {i + 1}:** {f['description']} "
            f"(${f['annual_cost']:,.0f}/yr -> saves ${f['annual_savings']:,.0f})"
        )
        st.progress(pct / 100, text=f"{start.strftime('%m/%d')} - {end.strftime('%m/%d')} ({days} days)")
        start = end

    # Gantt chart (Mermaid)
    gantt_code = _generate_gantt_mermaid(fixes)
    with st.expander("Gantt Chart (Mermaid)"):
        st.code(gantt_code, language="text")

    # --- Cost vs Savings summary ---
    st.markdown("---")
    st.markdown("### Investment Summary")
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Annual Cost", f"${financial.get('total_fix_cost', 0):,.0f}")
    c2.metric("Total Annual Savings", f"${financial.get('total_savings', 0):,.0f}")
    c3.metric("Overall ROI", f"{financial.get('roi', 0):.1f}x")

    # --- Google Calendar links ---
    st.markdown("---")
    st.markdown("### Calendar Integration")
    start_date = _dt.date.today() + _dt.timedelta(days=1)
    for i, f in enumerate(fixes):
        timeline = f.get("timeline", "1 week")
        if "day" in timeline:
            days = int("".join(c for c in timeline if c.isdigit()) or "3")
        elif "month" in timeline:
            days = 30
        else:
            days = 7
        end_date = start_date + _dt.timedelta(days=days)
        gcal_start = start_date.strftime("%Y%m%d")
        gcal_end = end_date.strftime("%Y%m%d")
        url = _google_cal_url(
            f"[FaultRay] {f['description']}",
            f"Component: {f['component_id']}\nCost: ${f['annual_cost']:,.0f}/yr\nSavings: ${f['annual_savings']:,.0f}/yr\nROI: {f['roi']:.1f}x",
            gcal_start, gcal_end,
        )
        st.markdown(f"[{f['description']}]({url})")
        start_date = end_date

    # ICS download
    ics_content = _generate_ics_calendar(fixes)
    st.download_button(
        "\U0001f4c5 All Tasks (.ics Calendar)",
        data=ics_content,
        file_name="faultray-remediation.ics",
        mime="text/calendar",
    )

    # --- Export ---
    st.markdown("---")
    st.markdown("### Export")
    col_pdf, col_csv = st.columns(2)
    with col_pdf:
        pdf_bytes = _generate_exec_pdf(financial)
        st.download_button(
            "\U0001f4e5 Remediation Report (HTML)",
            data=pdf_bytes,
            file_name="faultray-remediation-report.html",
            mime="text/html",
        )
    with col_csv:
        csv_data = _generate_remediation_csv(financial)
        st.download_button(
            "\U0001f4e5 Remediation Plan (CSV)",
            data=csv_data,
            file_name="faultray-remediation-plan.csv",
            mime="text/csv",
        )


# ══════════════════════════════════════════════════════════════════
# ページ 9: レポートセンター (Report Center)
# ══════════════════════════════════════════════════════════════════

def page_reports() -> None:
    """レポートセンター: 全レポートの一括ダウンロードハブ."""
    st.header("\U0001f4c4 レポートセンター (Report Center)")
    st.caption("全てのレポートをワンクリックでダウンロードできます。")

    result = st.session_state.sim_result
    financial = _get_financial_report() if result else None
    gov_result = st.session_state.gov_result

    has_sim = result is not None
    has_fin = financial is not None
    has_gov = gov_result is not None and GOVERNANCE_AVAILABLE

    if not has_sim and not has_gov:
        st.markdown("""
        <div class="empty-state">
            <h3>レポートを生成するにはデータが必要です</h3>
            <p>シミュレーションまたはガバナンス診断を実行してください。</p>
        </div>
        """, unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        with col1:
            if st.button("\u26a1 シミュレーションを始める", type="primary", use_container_width=True):
                st.session_state.current_page = "page_simulation"
                st.rerun()
        with col2:
            if st.button("\U0001f3db\ufe0f ガバナンス診断を始める", use_container_width=True):
                st.session_state.current_page = "page_governance"
                st.rerun()
        return

    # Collect all downloadable content for ZIP
    zip_contents: dict[str, bytes] = {}

    # --- Simulation Report ---
    st.markdown(
        '<div class="report-card"><h4>Simulation Report</h4>'
        '<p>Resilience simulation results</p></div>',
        unsafe_allow_html=True,
    )
    if has_sim:
        c1, c2 = st.columns(2)
        sim_json = json.dumps(result, ensure_ascii=False, indent=2)
        zip_contents["simulation-report.json"] = sim_json.encode("utf-8")
        with c1:
            st.download_button("JSON", data=sim_json, file_name="faultray-simulation.json", mime="application/json", key="rc_sim_json")
        with c2:
            # CSV export of scenarios
            import io as _io
            import csv as _csv
            buf = _io.StringIO()
            w = _csv.writer(buf)
            w.writerow(["Scenario", "Severity", "Risk Score", "Affected", "Suggestion"])
            for s in result.get("scenarios", []):
                w.writerow([s["name"], s["severity"], s["risk_score"], ", ".join(s.get("affected", [])), s.get("suggestion", "") or ""])
            csv_data = buf.getvalue()
            zip_contents["simulation-scenarios.csv"] = csv_data.encode("utf-8")
            st.download_button("CSV", data=csv_data, file_name="faultray-scenarios.csv", mime="text/csv", key="rc_sim_csv")
    else:
        st.caption("-- Simulation not yet run --")

    st.markdown("---")

    # --- Damage Report ---
    st.markdown(
        '<div class="report-card"><h4>Damage Report (Executive)</h4>'
        '<p>Financial impact analysis for executive presentation</p></div>',
        unsafe_allow_html=True,
    )
    if has_fin:
        c1, c2 = st.columns(2)
        with c1:
            pdf_bytes = _generate_exec_pdf(financial)
            zip_contents["damage-report.html"] = pdf_bytes
            st.download_button("HTML (PDF-ready)", data=pdf_bytes, file_name="faultray-damage-report.html", mime="text/html", key="rc_dmg_html")
        with c2:
            fin_json = json.dumps(financial, ensure_ascii=False, indent=2)
            zip_contents["damage-report.json"] = fin_json.encode("utf-8")
            st.download_button("JSON", data=fin_json, file_name="faultray-financial.json", mime="application/json", key="rc_dmg_json")
    else:
        st.caption("-- Run simulation first --")

    st.markdown("---")

    # --- Governance Report ---
    st.markdown(
        '<div class="report-card"><h4>AI Governance Assessment Report</h4>'
        '<p>METI v1.1 / ISO 42001 / AI Promotion Act compliance</p></div>',
        unsafe_allow_html=True,
    )
    if has_gov:
        gov_data = {
            "overall_score": gov_result.overall_score,
            "maturity_level": gov_result.maturity_level,
            "framework_coverage": gov_result.framework_coverage,
            "categories": [
                {"id": cs.category_id, "title": cs.category_title, "score": cs.score_percent, "maturity": cs.maturity_level}
                for cs in gov_result.category_scores
            ],
            "gaps": gov_result.top_gaps,
            "recommendations": gov_result.top_recommendations,
        }
        gov_json = json.dumps(gov_data, ensure_ascii=False, indent=2)
        zip_contents["governance-assessment.json"] = gov_json.encode("utf-8")
        st.download_button("JSON", data=gov_json, file_name="faultray-governance.json", mime="application/json", key="rc_gov_json")
    else:
        st.caption("-- Run governance assessment first --")

    st.markdown("---")

    # --- Remediation Plan ---
    st.markdown(
        '<div class="report-card"><h4>Remediation Plan</h4>'
        '<p>Priority-ordered improvement plan with cost and ROI</p></div>',
        unsafe_allow_html=True,
    )
    if has_fin and financial.get("recommended_fixes"):
        c1, c2 = st.columns(2)
        with c1:
            csv_data = _generate_remediation_csv(financial)
            zip_contents["remediation-plan.csv"] = csv_data.encode("utf-8")
            st.download_button("CSV", data=csv_data, file_name="faultray-remediation.csv", mime="text/csv", key="rc_rem_csv")
        with c2:
            ics_data = _generate_ics_calendar(financial["recommended_fixes"])
            zip_contents["remediation-calendar.ics"] = ics_data.encode("utf-8")
            st.download_button("ICS (Calendar)", data=ics_data, file_name="faultray-remediation.ics", mime="text/calendar", key="rc_rem_ics")
    else:
        st.caption("-- No remediation data available --")

    st.markdown("---")

    # --- Project Management Documents ---
    st.markdown(
        '<div class="report-card"><h4>Project Management Documents</h4>'
        '<p>WBS, RACI, Risk Register, Cost Estimate, Gantt Chart</p></div>',
        unsafe_allow_html=True,
    )
    if has_fin and financial.get("recommended_fixes"):
        fixes = financial["recommended_fixes"]
        c1, c2, c3 = st.columns(3)
        with c1:
            wbs_md = _generate_wbs_markdown(fixes)
            zip_contents["wbs.md"] = wbs_md.encode("utf-8")
            st.download_button("WBS (Markdown)", data=wbs_md, file_name="faultray-wbs.md", mime="text/markdown", key="rc_wbs_md")
            wbs_csv = _generate_wbs_csv(fixes)
            zip_contents["wbs.csv"] = wbs_csv.encode("utf-8")
            st.download_button("WBS (CSV)", data=wbs_csv, file_name="faultray-wbs.csv", mime="text/csv", key="rc_wbs_csv")
        with c2:
            raci_csv = _generate_raci_csv(fixes)
            zip_contents["raci-matrix.csv"] = raci_csv.encode("utf-8")
            st.download_button("RACI (CSV)", data=raci_csv, file_name="faultray-raci.csv", mime="text/csv", key="rc_raci_csv")
        with c3:
            cost_html = _generate_cost_estimate_html(fixes)
            zip_contents["cost-estimate.html"] = cost_html
            st.download_button("Cost Estimate (HTML)", data=cost_html, file_name="faultray-cost-estimate.html", mime="text/html", key="rc_cost_html")

        if has_sim:
            risk_csv = _generate_risk_register_csv(result)
            zip_contents["risk-register.csv"] = risk_csv.encode("utf-8")
            st.download_button("Risk Register (CSV)", data=risk_csv, file_name="faultray-risk-register.csv", mime="text/csv", key="rc_risk_csv")
    else:
        st.caption("-- No project data available --")

    st.markdown("---")

    # --- All-in-one ZIP ---
    st.markdown(
        '<div class="report-card"><h4>All Reports Bundle</h4>'
        '<p>Download all available reports in a single ZIP file</p></div>',
        unsafe_allow_html=True,
    )
    if zip_contents:
        import io as _io
        import zipfile as _zipfile
        zip_buf = _io.BytesIO()
        with _zipfile.ZipFile(zip_buf, "w", _zipfile.ZIP_DEFLATED) as zf:
            for name, content in zip_contents.items():
                zf.writestr(f"faultray-reports/{name}", content)
        zip_buf.seek(0)
        st.download_button(
            "\U0001f4e6 Download All Reports (ZIP)",
            data=zip_buf.getvalue(),
            file_name="faultray-all-reports.zip",
            mime="application/zip",
            type="primary",
            key="rc_zip_all",
        )
        st.caption(f"{len(zip_contents)} files included in the bundle.")
    else:
        st.caption("-- No reports to bundle --")


# ══════════════════════════════════════════════════════════════════
# ページ 10: Quick Demo
# ══════════════════════════════════════════════════════════════════

def page_quick_demo() -> None:
    """Quick Demo: ワンクリックでデモインフラのシミュレーションを体験."""
    st.header("🚀 Quick Demo")
    st.markdown("Experience FaultRay in 30 seconds with a sample infrastructure.")

    # Sample selection
    sample_key = st.selectbox(
        "Infrastructure sample",
        list(SAMPLE_TOPOLOGIES.keys()),
        index=0,
        key="quick_demo_sample",
    )

    # Auto-run when coming from Welcome or Dashboard
    should_auto_run = st.session_state.get("auto_run_demo", False)
    if should_auto_run:
        st.session_state.auto_run_demo = False

    if should_auto_run or st.button("▶️ Run Demo", type="primary", use_container_width=True):
        with st.spinner(f"Simulating failure scenarios for «{sample_key}»..."):
            if not FAULTRAY_AVAILABLE:
                time.sleep(0.5)
            result = _execute_demo_simulation(sample_key)
        if result:
            st.session_state.quick_demo_result = result
            st.session_state.sim_result = result
            st.session_state.sim_history.append(result)
            if len(st.session_state.sim_history) > 20:
                st.session_state.sim_history = st.session_state.sim_history[-20:]

    result = st.session_state.quick_demo_result
    if result is None:
        st.info("Press **▶️ Run Demo** above to start the simulation.")
        return

    # --- Score metrics ---
    score = result["resilience_score"]
    if score >= 80:
        score_color = "#22c55e"
    elif score >= 60:
        score_color = "#f59e0b"
    else:
        score_color = "#ef4444"

    st.markdown("---")
    st.markdown("### Results")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Resilience Score", f"{score}/100")
    col2.metric("Scenarios", result["total_scenarios"])
    col3.metric("🚨 Critical", result["critical"])
    col4.metric("✅ Passed", result["passed"])

    # --- Score gauge ---
    render_score_gauge(result["resilience_score"])

    # --- Risk heatmap (bar chart via Plotly) ---
    scenarios = result.get("scenarios", [])
    if scenarios:
        st.markdown("### Risk Heatmap by Scenario")
        try:
            import plotly.graph_objects as go  # type: ignore[import]

            names = [s["name"][:30] for s in scenarios[:15]]
            scores_list = [s["risk_score"] for s in scenarios[:15]]
            colors_list = [
                "#ef4444" if s["severity"] == "CRITICAL"
                else "#f59e0b" if s["severity"] == "WARNING"
                else "#22c55e"
                for s in scenarios[:15]
            ]

            fig = go.Figure(go.Bar(
                x=scores_list,
                y=names,
                orientation="h",
                marker_color=colors_list,
                text=[f"{s:.1f}" for s in scores_list],
                textposition="outside",
            ))
            fig.update_layout(
                height=max(300, len(names) * 32),
                xaxis_title="Risk Score (0–10)",
                yaxis_title="",
                margin={"l": 10, "r": 60, "t": 10, "b": 30},
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font={"color": "#1e293b"},
                xaxis={"range": [0, 10.5]},
            )
            st.plotly_chart(fig, use_container_width=True)
        except ImportError:
            # Plotly not available — fall back to text representation
            render_inline_top_issues(result, max_issues=5)

    # --- Top issues ---
    st.markdown("### Top Issues Found")
    render_inline_top_issues(result, max_issues=5)

    # --- CTA buttons ---
    st.markdown("---")
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        if st.button("📋 Full Results", use_container_width=True):
            st.session_state.current_page = "page_results"
            st.rerun()
    with col_b:
        if st.button("💡 Suggestions", use_container_width=True):
            st.session_state.current_page = "page_suggestions"
            st.rerun()
    with col_c:
        if st.button("🏗️ Export IaC", use_container_width=True):
            st.session_state.selected_sample = sample_key
            st.session_state.topology_yaml = SAMPLE_TOPOLOGIES[sample_key]["yaml"]
            st.session_state.current_page = "page_iac_export"
            st.rerun()


# ══════════════════════════════════════════════════════════════════
# ページ 11: IaC Export
# ══════════════════════════════════════════════════════════════════

def page_iac_export() -> None:
    """IaC Export: InfraGraphをTerraform / CloudFormation / Kubernetesに変換."""
    st.header("🏗️ Export as Infrastructure as Code")
    st.markdown("Convert your infrastructure topology into production-ready IaC files with embedded resilience warnings.")

    topology_yaml = st.session_state.topology_yaml
    if not topology_yaml:
        st.warning("No topology loaded. Please run a simulation first or upload a YAML topology.")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("⚡ Go to Simulation", use_container_width=True):
                st.session_state.current_page = "page_simulation"
                st.rerun()
        with col2:
            uploaded = st.file_uploader("Or upload YAML here", type=["yaml", "yml", "json"])
            if uploaded:
                try:
                    content = uploaded.read().decode("utf-8")
                    parse_topology(content)
                    st.session_state.topology_yaml = content
                    st.rerun()
                except Exception as e:
                    st.error(f"Parse error: {e}")
        return

    # --- Options ---
    col_fmt, col_prov = st.columns(2)
    with col_fmt:
        fmt_label = st.selectbox("Output Format", ["Terraform", "CloudFormation", "Kubernetes"])
    with col_prov:
        region = st.selectbox("AWS Region", ["us-east-1", "us-west-2", "eu-west-1", "ap-northeast-1"])

    mark_spof = st.checkbox("Mark SPOFs with warnings in generated code", value=True)
    include_comments = st.checkbox("Include FaultRay discovery comments", value=True)

    if st.button("⚙️ Generate IaC", type="primary", use_container_width=True):
        if not FAULTRAY_AVAILABLE:
            st.warning("FaultRay engine not available. Install `pip install faultray` to use IaC export.")
            return

        try:
            from faultray.iac.exporter import IacExporter, ExportFormat

            fmt_map = {
                "Terraform": ExportFormat.TERRAFORM,
                "CloudFormation": ExportFormat.CLOUDFORMATION,
                "Kubernetes": ExportFormat.KUBERNETES,
            }
            fmt_enum = fmt_map[fmt_label]

            topo = parse_topology(topology_yaml)
            graph = build_infra_graph(topo)
            exporter = IacExporter(graph)
            export_result = exporter.export(
                fmt=fmt_enum,
                provider_region=region,
                include_comments=include_comments,
                mark_spof=mark_spof,
            )
            st.session_state.iac_export_result = {
                "format": fmt_label,
                "files": export_result.files,
                "warnings": export_result.warnings,
                "spof_components": export_result.spof_components,
            }
        except Exception as e:
            st.error(f"IaC generation error: {e}")
            return

    export_data = st.session_state.iac_export_result
    if export_data is None:
        st.info("Configure options above and click **⚙️ Generate IaC** to generate infrastructure code.")
        return

    # --- Results ---
    st.markdown("---")
    st.markdown(f"### Generated {export_data['format']} Files")

    # SPOF warnings
    if export_data.get("spof_components"):
        spof_list = ", ".join(f"`{c}`" for c in export_data["spof_components"])
        st.warning(f"⚠️ **SPOF components detected:** {spof_list}. Warnings have been embedded in the generated code.")

    # Other warnings
    for w in export_data.get("warnings", []):
        st.caption(f"ℹ️ {w}")

    # Display files
    files = export_data.get("files", {})
    ext_map = {"Terraform": "hcl", "CloudFormation": "yaml", "Kubernetes": "yaml"}
    lang = ext_map.get(export_data["format"], "text")

    for filename, content in files.items():
        with st.expander(f"📄 {filename}", expanded=True):
            st.code(content, language=lang)
            st.download_button(
                f"📥 Download {filename}",
                data=content,
                file_name=filename,
                mime="text/plain",
                key=f"iac_dl_{filename}",
            )

    # Bulk download (ZIP if multiple files)
    if len(files) > 1:
        import io as _io
        import zipfile as _zipfile
        zip_buf = _io.BytesIO()
        with _zipfile.ZipFile(zip_buf, "w", _zipfile.ZIP_DEFLATED) as zf:
            for fname, fcontent in files.items():
                zf.writestr(fname, fcontent)
        zip_buf.seek(0)
        st.download_button(
            "📦 Download All Files (ZIP)",
            data=zip_buf.getvalue(),
            file_name=f"faultray-iac-{export_data['format'].lower()}.zip",
            mime="application/zip",
            type="primary",
        )


# ══════════════════════════════════════════════════════════════════
# ルーティング
# ══════════════════════════════════════════════════════════════════

MENU_ITEMS = [
    "🏠 Dashboard",
    "🚀 Quick Demo",
    "⚡ Simulation",
    "📋 DORA Compliance",
    "📊 Results",
    "💡 Suggestions",
    "💰 Damage Report",
    "🔧 Remediation",
    "📄 Reports",
    "🏗️ IaC Export",
    "⚙️ Settings",
]

MENU_TO_PAGE_KEY = {
    "🏠 Dashboard": "page_dashboard",
    "🚀 Quick Demo": "page_quick_demo",
    "⚡ Simulation": "page_simulation",
    "📋 DORA Compliance": "page_governance",
    "📊 Results": "page_results",
    "💡 Suggestions": "page_suggestions",
    "💰 Damage Report": "page_financial",
    "🔧 Remediation": "page_remediation",
    "📄 Reports": "page_reports",
    "🏗️ IaC Export": "page_iac_export",
    "⚙️ Settings": "page_settings",
}

PAGE_KEY_TO_MENU = {v: k for k, v in MENU_TO_PAGE_KEY.items()}

PAGE_KEY_TO_FN = {
    "page_dashboard": page_dashboard,
    "page_quick_demo": page_quick_demo,
    "page_simulation": page_simulation,
    "page_governance": page_governance,
    "page_results": page_results,
    "page_suggestions": page_suggestions,
    "page_financial": page_financial,
    "page_remediation": page_remediation,
    "page_reports": page_reports,
    "page_iac_export": page_iac_export,
    "page_settings": page_settings,
}

if not st.session_state.onboarded:
    show_welcome()
else:
    # サイドバー
    with st.sidebar:
        # Logo
        import os as _os
        _logo_path = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "docs", "logo.png")
        if _os.path.exists(_logo_path):
            st.image(_logo_path, width=150)
        else:
            st.title("⚡ FaultRay")
        st.caption("Infrastructure Failure Simulator")
        st.markdown("---")

        # ページ遷移（ボタンからの直接遷移をサポート）
        override_page = st.session_state.current_page
        default_index = 0
        if override_page in PAGE_KEY_TO_MENU:
            menu_label = PAGE_KEY_TO_MENU[override_page]
            if menu_label in MENU_ITEMS:
                default_index = MENU_ITEMS.index(menu_label)
            st.session_state.current_page = None

        page = st.radio(
            "Navigation",
            MENU_ITEMS,
            index=default_index,
            label_visibility="collapsed",
        )

        # エンジン状態バッジ
        st.markdown("---")
        if FAULTRAY_AVAILABLE:
            st.success("✅ Engine: Active")
        else:
            st.info("📋 Demo Mode")

        st.markdown("---")
        st.markdown(
            "<div style='text-align:center;color:#64748b;font-size:0.8em'>"
            "FaultRay — Zero-risk chaos engineering<br>"
            "&copy; 2025-2026 Yutaro Maeda"
            "</div>",
            unsafe_allow_html=True,
        )

    page_key = MENU_TO_PAGE_KEY.get(page, "page_dashboard")
    page_fn = PAGE_KEY_TO_FN.get(page_key, page_dashboard)
    page_fn()
