# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""FaultRay Streamlit UI — インフラ障害シミュレーターのWebインターフェース.

初めてのユーザーが迷わず使えるUI。オンボーディングフロー付き。
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
try:
    from faultray.model.graph import InfraGraph
    from faultray.model.components import Component, ComponentType, Dependency
    from faultray.simulator.engine import SimulationEngine, SimulationReport
    FAULTRAY_AVAILABLE = True
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
}
for _k, _v in _defaults.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

# ---------------------------------------------------------------------------
# カスタムCSS
# ---------------------------------------------------------------------------

st.markdown("""
<style>
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
    /* サンプルカード */
    .sample-card {
        background: #f8f9fa;
        border: 1px solid #e9ecef;
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 12px;
    }
    .sample-card:hover {
        border-color: #667eea;
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
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# サンプルトポロジー
# ---------------------------------------------------------------------------

SAMPLE_TOPOLOGIES: dict[str, dict[str, Any]] = {
    "Webアプリ 3層構成": {
        "description": "典型的な Nginx + アプリサーバー + DB + キャッシュ の3層構成",
        "icon": "1",
        "detail": "ロードバランサー、アプリサーバー2台、PostgreSQL、Redis、RabbitMQで構成される標準的なWebアプリケーション",
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
        "icon": "2",
        "detail": "API Gateway経由でUser/Order/Payment/Notificationサービスが連携する、ECサイト向け構成",
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
        "icon": "3",
        "detail": "Claude API/OpenAIをバックエンドに、Router/Research/Writerエージェントが協調するAIアプリケーション構成",
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

    st.markdown(
        f"""
        <div class="score-gauge">
            <div class="score-number" style="color: {color};">
                {score:.1f}
            </div>
            <div class="score-sublabel">/ 100</div>
            <div class="score-label" style="color: {color};">
                {_tooltip("耐障害スコア", "インフラがどれだけ障害に強いかを0-100で示す総合スコアです")} - {label}
            </div>
        </div>
        """,
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


# ══════════════════════════════════════════════════════════════════
# ウェルカム + オンボーディング
# ══════════════════════════════════════════════════════════════════

def show_welcome() -> None:
    """ウェルカム画面を表示する."""
    st.markdown("""
    <div class="welcome-card">
        <h1>FaultRay</h1>
        <p>インフラ障害をシミュレーション - 本番を壊さずにカスケード障害をテスト</p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("### 3つのステップで始めましょう")
    st.markdown("")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("""
        <div class="step-card">
            <div style="font-size:2em">1</div>
            <h3>サンプルを選ぶ</h3>
            <p>Webアプリ3層、マイクロサービス、AIパイプラインから選択</p>
            <p style="color:#6c757d;font-size:0.9em">入力の手間ゼロ</p>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown("""
        <div class="step-card">
            <div style="font-size:2em">2</div>
            <h3>シミュレーション実行</h3>
            <p>ボタン1つで障害シナリオを自動生成・テスト</p>
            <p style="color:#6c757d;font-size:0.9em">数秒で完了</p>
        </div>
        """, unsafe_allow_html=True)

    with col3:
        st.markdown("""
        <div class="step-card">
            <div style="font-size:2em">3</div>
            <h3>結果を確認する</h3>
            <p>耐障害スコア、発見された問題、具体的な改善提案</p>
            <p style="color:#6c757d;font-size:0.9em">すぐ表示</p>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("")
    st.markdown("")

    # エンジン状態
    if FAULTRAY_AVAILABLE:
        st.success("FaultRayエンジン: 有効 - 実際のシミュレーションを実行します")
    else:
        st.info(
            "**デモモード**で動作しています。サンプル結果をすぐに体験できます。  \n"
            "実際のシミュレーションには `pip install faultray` を実行してください。"
        )

    _col_l, col_center, _col_r = st.columns([1, 2, 1])
    with col_center:
        if st.button("試してみる", type="primary", use_container_width=True):
            st.session_state.onboarded = True
            st.session_state.current_page = "page_simulation"
            st.rerun()


# ══════════════════════════════════════════════════════════════════
# ページ 1: ダッシュボード
# ══════════════════════════════════════════════════════════════════

def page_dashboard() -> None:
    """ダッシュボード: 直近のシミュレーション結果サマリー."""
    st.header("ダッシュボード")
    st.caption("直近のシミュレーション結果を一目で確認できます。")

    result = st.session_state.sim_result
    history = st.session_state.sim_history

    if result is None:
        # まだシミュレーションしていない
        st.markdown("""
        <div class="empty-state">
            <h3>まだシミュレーションを実行していません</h3>
            <p>インフラトポロジーを入力して、障害シミュレーションを実行すると<br>
            ここにスコアと結果のサマリーが表示されます。</p>
        </div>
        """, unsafe_allow_html=True)
        st.markdown("")
        _col_l, col_center, _col_r = st.columns([1, 2, 1])
        with col_center:
            if st.button("シミュレーションを始める", type="primary", use_container_width=True):
                st.session_state.current_page = "page_simulation"
                st.rerun()
        return

    # -- メインスコア
    render_score_gauge(result["resilience_score"])

    # -- サマリーメトリクス
    st.markdown("#### シナリオ集計")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("総シナリオ数", result["total_scenarios"])
    c2.metric(
        "CRITICAL",
        result["critical"],
        help="即座に対応が必要な重大な障害シナリオの数です",
    )
    c3.metric(
        "WARNING",
        result["warning"],
        help="注意が必要な障害シナリオの数です",
    )
    c4.metric(
        "PASS",
        result["passed"],
        help="冗長化等が機能しており、問題のないシナリオの数です",
    )

    # -- 次にやるべきこと: CRITICALな改善提案トップ3
    suggestions = result.get("suggestions", [])
    critical_suggestions = [s for s in suggestions if isinstance(s, dict) and s.get("priority") == "critical"]
    if critical_suggestions:
        st.markdown("---")
        st.markdown("#### 最優先で対応すべきこと")
        for i, sug in enumerate(critical_suggestions[:3], 1):
            st.markdown(
                f'<div class="suggestion-card suggestion-card-critical">'
                f'<strong>{i}. {__import__("html").escape(sug["title"])}</strong><br>'
                f'<span style="color:#6c757d">{__import__("html").escape(sug["detail"])}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
        st.markdown("")
        if st.button("すべての改善提案を見る"):
            st.session_state.current_page = "page_suggestions"
            st.rerun()

    # -- 実行履歴
    if len(history) > 1:
        st.markdown("---")
        st.markdown("#### 実行履歴")
        for i, h in enumerate(reversed(history[-5:])):
            score = h["resilience_score"]
            color = "#22c55e" if score >= 80 else "#f59e0b" if score >= 60 else "#ef4444"
            st.markdown(
                f"<span style='color:{color};font-weight:bold'>{score:.1f}</span>"
                f" / 100  -  CRITICAL: {h['critical']}, WARNING: {h['warning']}, PASS: {h['passed']}",
                unsafe_allow_html=True,
            )


# ══════════════════════════════════════════════════════════════════
# ページ 2: シミュレーション実行
# ══════════════════════════════════════════════════════════════════

def page_simulation() -> None:
    """シミュレーション実行: サンプル選択 or YAML入力 -> 実行."""
    st.header("シミュレーション実行")
    st.caption(
        "サンプルトポロジーを選ぶか、YAML/JSONを直接入力してシミュレーションを実行できます。"
    )

    # エンジン状態
    if not FAULTRAY_AVAILABLE:
        st.info(
            "**デモモード**で動作中。サンプル結果を表示します。  \n"
            "実際のシミュレーションには `pip install faultray` を実行してください。"
        )

    # -- サンプル選択
    st.markdown("#### サンプルトポロジーを選ぶ")

    sample_cols = st.columns(3)
    sample_names = list(SAMPLE_TOPOLOGIES.keys())

    for idx, col in enumerate(sample_cols):
        name = sample_names[idx]
        sample = SAMPLE_TOPOLOGIES[name]
        with col:
            st.markdown(
                f'<div class="sample-card">'
                f'<div style="font-size:1.5em;margin-bottom:4px">{sample["icon"]}</div>'
                f'<strong>{name}</strong><br>'
                f'<span style="color:#6c757d;font-size:0.9em">{sample["detail"]}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
            if st.button("この構成を使う", key=f"sample_{idx}", use_container_width=True):
                st.session_state.topology_yaml = sample["yaml"]
                st.session_state.selected_sample = name
                st.rerun()

    # -- カスタム入力
    st.markdown("---")
    st.markdown("#### または YAML / JSON を直接入力")

    default_yaml = st.session_state.topology_yaml
    if not default_yaml:
        default_yaml = SAMPLE_TOPOLOGIES["Webアプリ 3層構成"]["yaml"]
        st.session_state.selected_sample = "Webアプリ 3層構成"

    if st.session_state.selected_sample:
        st.caption(f"選択中: **{st.session_state.selected_sample}**")

    topology_text = st.text_area(
        "トポロジー定義",
        value=default_yaml,
        height=250,
        help="components（コンポーネント定義）とdependencies（依存関係）をYAMLまたはJSONで記述します",
        key="topology_input",
    )
    # text_areaの編集をsession_stateに反映（ページ遷移後も保持）
    if topology_text != default_yaml:
        st.session_state.topology_yaml = topology_text
        st.session_state.selected_sample = None  # カスタム入力に切り替え

    # -- ボタン行
    col_preview, col_run = st.columns([1, 1])

    with col_preview:
        if st.button("トポロジーを可視化", use_container_width=True):
            try:
                topo = parse_topology(topology_text)
                st.session_state.parsed_topology = topo
                st.session_state.show_topology_preview = True
            except Exception as e:
                st.error(f"パースエラー: {e}")

    with col_run:
        run_clicked = st.button(
            "シミュレーション開始",
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

    # -- シミュレーション実行
    if run_clicked:
        try:
            topo = parse_topology(topology_text)
        except Exception as e:
            st.error(f"トポロジーのパースに失敗しました: {e}")
            return

        with st.spinner("シミュレーション実行中..."):
            if FAULTRAY_AVAILABLE:
                try:
                    results = run_simulation(topo)
                except Exception as e:
                    st.error(f"シミュレーションエラー: {e}")
                    st.code(traceback.format_exc(), language="python")
                    return
            else:
                # デモモード
                time.sleep(0.8)
                sample_key = st.session_state.selected_sample
                if not sample_key or sample_key not in DEMO_RESULTS:
                    st.warning("デモモードではカスタムトポロジーのシミュレーションは実行できません。サンプルを選択してください。")
                    return
                results = DEMO_RESULTS[sample_key]

        st.session_state.sim_result = results
        st.session_state.sim_history.append(results)
        # 履歴は最新20件に制限（メモリ膨張防止）
        if len(st.session_state.sim_history) > 20:
            st.session_state.sim_history = st.session_state.sim_history[-20:]
        st.session_state.current_page = "page_results"
        st.rerun()


# ══════════════════════════════════════════════════════════════════
# ページ 3: 結果詳細
# ══════════════════════════════════════════════════════════════════

def page_results() -> None:
    """結果詳細: シナリオ一覧とフィルタ."""
    st.header("結果詳細")
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
        if st.button("シミュレーションを始める", type="primary"):
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
            "CRITICAL",
            result["critical"],
            help="即座に対応が必要な重大な障害シナリオです",
        )
        c3.metric(
            "WARNING",
            result["warning"],
            help="注意が必要な障害シナリオです",
        )
        c4.metric(
            "PASS",
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
        for scenario in scenarios_sorted:
            render_scenario_card(scenario)

    # -- JSON エクスポート
    st.markdown("---")
    st.markdown("#### 結果エクスポート")
    export_data = json.dumps(result, ensure_ascii=False, indent=2)
    st.download_button(
        label="JSON でダウンロード",
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
    st.header("改善提案")
    st.caption("発見された問題とその対策を優先度順に確認できます。")

    result = st.session_state.sim_result
    if result is None:
        st.markdown("""
        <div class="empty-state">
            <h3>まだシミュレーションを実行していません</h3>
            <p>シミュレーションを実行すると、ここに改善提案が表示されます。</p>
        </div>
        """, unsafe_allow_html=True)
        if st.button("シミュレーションを始める", type="primary"):
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
        "CRITICAL",
        f"{critical_count}件",
        help="即座に対応が必要な重大な問題です",
    )
    col2.metric(
        "WARNING",
        f"{warning_count}件",
        help="早めに対応すべき問題です",
    )
    col3.metric(
        "情報",
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
    st.header("設定")
    st.caption("トポロジーの保存・読み込みとデータ管理ができます。")

    # -- トポロジーの保存
    st.subheader("トポロジーの保存")

    current_yaml = st.session_state.topology_yaml
    if current_yaml:
        st.caption("現在のトポロジーをファイルとしてダウンロードできます。")
        st.download_button(
            label="YAML でダウンロード",
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
        if st.button("シミュレーション結果をリセット"):
            st.session_state.sim_result = None
            st.session_state.sim_history = []
            st.success("シミュレーション結果をリセットしました。")
    with col2:
        if st.button("トポロジーをリセット"):
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
# ルーティング
# ══════════════════════════════════════════════════════════════════

if not st.session_state.onboarded:
    show_welcome()
else:
    # サイドバー
    st.sidebar.title("FaultRay")
    st.sidebar.caption("インフラ障害シミュレーター")
    st.sidebar.markdown("---")

    page = st.sidebar.radio(
        "メニュー",
        [
            "ダッシュボード",
            "シミュレーション実行",
            "結果詳細",
            "改善提案",
            "設定",
        ],
        label_visibility="collapsed",
    )

    # エンジン状態バッジ
    st.sidebar.markdown("---")
    if FAULTRAY_AVAILABLE:
        st.sidebar.success("エンジン: 有効")
    else:
        st.sidebar.warning("デモモード")

    st.sidebar.markdown("---")
    st.sidebar.markdown(
        "<div style='text-align:center;color:#64748b;font-size:0.8em'>"
        "FaultRay - Zero-risk chaos engineering<br>"
        "&copy; 2025-2026 Yutaro Maeda"
        "</div>",
        unsafe_allow_html=True,
    )

    # ページ遷移（ボタンからの直接遷移をサポート）
    override_page = st.session_state.current_page
    if override_page in (
        "page_dashboard", "page_simulation", "page_results",
        "page_suggestions", "page_settings",
    ):
        page_map = {
            "page_dashboard": "ダッシュボード",
            "page_simulation": "シミュレーション実行",
            "page_results": "結果詳細",
            "page_suggestions": "改善提案",
            "page_settings": "設定",
        }
        page = page_map.get(override_page, page)
        st.session_state.current_page = None

    PAGE_MAP = {
        "ダッシュボード": page_dashboard,
        "シミュレーション実行": page_simulation,
        "結果詳細": page_results,
        "改善提案": page_suggestions,
        "設定": page_settings,
    }

    page_fn = PAGE_MAP.get(page, page_dashboard)
    page_fn()
