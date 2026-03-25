# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""FaultRay Streamlit UI — インフラ障害シミュレーターのWebインターフェース。

起動方法:
    streamlit run ui/streamlit_app.py

FaultRayがインストールされていない場合はデモモードで動作します。
"""

from __future__ import annotations

import json
import traceback
from typing import Any

import streamlit as st
import yaml

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
# サンプルトポロジー
# ---------------------------------------------------------------------------

SAMPLE_TOPOLOGIES: dict[str, dict[str, Any]] = {
    "Webアプリ 3層構成": {
        "description": "典型的な Nginx → アプリサーバー → DB + キャッシュ の3層構成",
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

DEMO_RESULTS: dict[str, Any] = {
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
            "cascade_path": "postgres → app-1 → nginx\npostgres → app-2 → nginx",
            "suggestion": "PostgreSQLにフェイルオーバーを設定し、レプリカへの自動昇格時間を短縮してください。",
        },
        {
            "name": "Redis 停止（キャッシュ消失）",
            "risk_score": 5.8,
            "severity": "WARNING",
            "affected": ["app-1", "app-2"],
            "cascade_path": "redis → app-1 (degraded)\nredis → app-2 (degraded)",
            "suggestion": "Redisをoptionalな依存にしており正解ですが、キャッシュなしでのDB負荷増加に備えてコネクションプールを拡張してください。",
        },
        {
            "name": "app-1 メモリ枯渇",
            "risk_score": 6.1,
            "severity": "WARNING",
            "affected": ["nginx", "postgres"],
            "cascade_path": "app-1 (OOM) → nginx (partial) → postgres (load spike)",
            "suggestion": "app-1のmax_memory_mbを増やすか、水平スケールのしきい値を下げてください。",
        },
        {
            "name": "nginx 単一インスタンス障害",
            "risk_score": 2.1,
            "severity": "PASS",
            "affected": [],
            "cascade_path": "nginx (1/2 down) → サービス継続（冗長化有効）",
            "suggestion": None,
        },
        {
            "name": "RabbitMQ 遅延スパイク",
            "risk_score": 3.4,
            "severity": "WARNING",
            "affected": ["app-1", "app-2"],
            "cascade_path": "rabbitmq (latency) → app-1 (queue backup)\nrabbitmq (latency) → app-2 (queue backup)",
            "suggestion": "非同期処理のタイムアウトを設定し、キューのデッドレターキューを構成してください。",
        },
        {
            "name": "トラフィック 3倍スパイク",
            "risk_score": 8.7,
            "severity": "CRITICAL",
            "affected": ["nginx", "app-1", "app-2", "postgres"],
            "cascade_path": "traffic spike → nginx (overloaded) → app-1 (saturated)\n→ app-2 (saturated) → postgres (connection exhaustion)",
            "suggestion": "オートスケーリングを有効にし、Postgresのmax_connectionsとコネクションプーラー（PgBouncer等）を設定してください。",
        },
        {
            "name": "postgres コネクションプール枯渇",
            "risk_score": 7.9,
            "severity": "CRITICAL",
            "affected": ["app-1", "app-2"],
            "cascade_path": "postgres (pool exhausted) → app-1 (timeout) → app-2 (timeout)",
            "suggestion": "connection_pool_sizeを現在の200から100に下げ、PgBouncerのプーリングを追加してください。",
        },
        {
            "name": "Redis ネットワーク分断",
            "risk_score": 4.2,
            "severity": "WARNING",
            "affected": ["app-1", "app-2"],
            "cascade_path": "redis (network partition) → app-1 (cache miss storm)\n→ app-2 (cache miss storm)",
            "suggestion": "サーキットブレーカーを設定し、キャッシュ無効時はDBへのリクエストをスロットリングしてください。",
        },
    ],
    "suggestions": [
        "PostgreSQLのフェイルオーバー設定を追加してください（現在: 無効）",
        "オートスケーリングが未設定です。トラフィックスパイク時に全滅リスクがあります",
        "コネクションプーラー（PgBouncer）の導入を推奨します",
        "RabbitMQのデッドレターキューが未設定です",
        "サーキットブレーカーが全依存関係で無効です",
    ],
}

# ---------------------------------------------------------------------------
# ユーティリティ関数
# ---------------------------------------------------------------------------

def parse_topology(text: str) -> dict[str, Any]:
    """YAMLまたはJSONのトポロジー定義をパースする。"""
    text = text.strip()
    if not text:
        raise ValueError("トポロジーが空です")
    # JSONを試みる
    if text.startswith("{") or text.startswith("["):
        return json.loads(text)
    # YAMLをパース
    return yaml.safe_load(text)


def build_infra_graph(topology: dict[str, Any]) -> "InfraGraph":
    """パース済みトポロジーからInfraGraphを構築する。"""
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

        # フェイルオーバー設定
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
    """FaultRayエンジンでシミュレーションを実行し、結果を辞書に変換する。"""
    graph = build_infra_graph(topology)
    engine = SimulationEngine(graph)
    report = engine.run_all_defaults()

    results = []
    for r in report.results:
        scenario = r.scenario
        cascade = r.cascade

        # カスケードパスをテキスト表現に変換
        if cascade.effects:
            path_lines = []
            for eff in cascade.effects:
                health_label = eff.health.value if hasattr(eff.health, "value") else str(eff.health)
                path_lines.append(f"{eff.component_name} → {health_label.upper()}: {eff.reason}")
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

    # スコア計算
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


def _generate_suggestions(report: "SimulationReport") -> list[str]:
    """シミュレーション結果から改善提案を生成する。"""
    suggestions = []
    critical_names = [r.scenario.name for r in report.critical_findings]
    warning_names = [r.scenario.name for r in report.warnings]

    if any("traffic" in n.lower() or "spike" in n.lower() for n in critical_names):
        suggestions.append("トラフィックスパイクで障害が発生しています。オートスケーリングを設定してください。")
    if any("connection" in n.lower() or "pool" in n.lower() for n in critical_names + warning_names):
        suggestions.append("コネクションプール枯渇リスクがあります。PgBouncerまたはコネクションプーラーの導入を検討してください。")
    if any("database" in n.lower() or "db" in n.lower() or "postgres" in n.lower() for n in critical_names):
        suggestions.append("データベース障害が致命的な影響を与えています。フェイルオーバー設定とリードレプリカを検討してください。")
    if report.resilience_score < 60:
        suggestions.append("耐障害スコアが60未満です。サーキットブレーカーとリトライ戦略の導入を優先してください。")
    if not suggestions:
        if report.critical_findings:
            suggestions.append(f"{len(report.critical_findings)}件のCRITICAL障害シナリオを解消することで大幅にスコアが向上します。")
        else:
            suggestions.append("主要なCRITICAL障害はありません。WARNINGシナリオの対処を継続してください。")
    return suggestions


# ---------------------------------------------------------------------------
# UI コンポーネント
# ---------------------------------------------------------------------------

def render_score_gauge(score: float) -> None:
    """耐障害スコアをゲージで表示する。"""
    if score >= 80:
        color = "#22c55e"  # green
        label = "良好"
        emoji = "✅"
    elif score >= 60:
        color = "#f59e0b"  # amber
        label = "要改善"
        emoji = "⚠️"
    else:
        color = "#ef4444"  # red
        label = "危険"
        emoji = "🚨"

    st.markdown(
        f"""
        <div style="text-align:center; padding: 1.5rem; border-radius: 12px;
                    background: linear-gradient(135deg, #1e293b, #0f172a);
                    border: 1px solid {color}33; margin-bottom: 1rem;">
            <div style="font-size: 4rem; font-weight: 800; color: {color}; line-height: 1;">
                {score:.1f}
            </div>
            <div style="font-size: 1rem; color: #94a3b8; margin-top: 0.25rem;">/ 100</div>
            <div style="font-size: 1.25rem; color: {color}; margin-top: 0.5rem;">
                {emoji} 耐障害スコア — {label}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_scenario_card(scenario: dict[str, Any], index: int) -> None:
    """単一シナリオの結果カードを表示する。"""
    sev = scenario["severity"]
    score = scenario["risk_score"]

    if sev == "CRITICAL":
        border_color = "#ef4444"
        badge_bg = "#7f1d1d"
        badge_color = "#fca5a5"
        icon = "🔴"
    elif sev == "WARNING":
        border_color = "#f59e0b"
        badge_bg = "#78350f"
        badge_color = "#fcd34d"
        icon = "🟡"
    else:
        border_color = "#22c55e"
        badge_bg = "#14532d"
        badge_color = "#86efac"
        icon = "🟢"

    with st.expander(f"{icon} {scenario['name']}　（リスクスコア: {score}）", expanded=(sev == "CRITICAL")):
        col1, col2 = st.columns([1, 2])
        with col1:
            st.markdown(
                f"""
                <span style="background:{badge_bg}; color:{badge_color};
                             padding: 2px 10px; border-radius: 999px;
                             font-size: 0.8rem; font-weight: 600;">
                    {sev}
                </span>
                """,
                unsafe_allow_html=True,
            )
            st.metric("リスクスコア", f"{score} / 10.0")

            affected = scenario.get("affected", [])
            if affected:
                st.markdown("**影響コンポーネント**")
                for a in affected:
                    st.markdown(f"- `{a}`")

        with col2:
            cascade = scenario.get("cascade_path", "")
            if cascade and cascade != "影響なし":
                st.markdown("**カスケード伝播**")
                st.code(cascade, language=None)

        suggestion = scenario.get("suggestion")
        if suggestion:
            st.info(f"💡 **改善提案:** {suggestion}")


def render_topology_graph(topology: dict[str, Any]) -> None:
    """トポロジーのテキストベース可視化を表示する。"""
    components = {c["id"]: c.get("name", c["id"]) for c in topology.get("components", [])}
    deps = topology.get("dependencies", [])

    if not components:
        st.warning("コンポーネントが定義されていません")
        return

    # 隣接リストを構築
    adjacency: dict[str, list[tuple[str, str]]] = {cid: [] for cid in components}
    for d in deps:
        src, tgt = d.get("source", ""), d.get("target", "")
        if src in adjacency:
            dep_type = d.get("type", "requires")
            adjacency[src].append((tgt, dep_type))

    # 入次数が0のノード（根）を探す
    has_incoming = {d["target"] for d in deps if d.get("target") in components}
    roots = [cid for cid in components if cid not in has_incoming]
    if not roots:
        roots = list(components.keys())[:1]

    type_icon = {
        "requires": "→",
        "optional": "⇢",
        "async": "⇝",
    }
    type_label = {
        "requires": "必須",
        "optional": "任意",
        "async": "非同期",
    }

    lines = []
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
            arrow = type_icon.get(dep_type, "→")
            lbl = type_label.get(dep_type, dep_type)
            connector = "└─" if is_last else "├─"
            render_node(child_id, depth + 1, f"{connector}{arrow}({lbl}) ")

    for root in roots:
        render_node(root)

    # 孤立ノードも表示
    for cid in components:
        if cid not in visited:
            render_node(cid)

    st.code("\n".join(lines), language=None)


# ---------------------------------------------------------------------------
# メインアプリ
# ---------------------------------------------------------------------------

def main() -> None:
    st.set_page_config(
        page_title="FaultRay UI",
        page_icon="⚡",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # ヘッダー
    st.markdown(
        """
        <div style="background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
                    padding: 2rem; border-radius: 12px; margin-bottom: 2rem;
                    border: 1px solid #334155;">
            <h1 style="color: #f8fafc; margin: 0; font-size: 2.2rem;">
                ⚡ FaultRay
            </h1>
            <p style="color: #94a3b8; margin: 0.5rem 0 0; font-size: 1.1rem;">
                インフラ障害シミュレーター — 本番を壊さずにカスケード障害をテスト
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # エンジン状態バッジ
    if FAULTRAY_AVAILABLE:
        st.success("✅ FaultRayエンジン: 有効 — 実際のシミュレーションを実行します")
    else:
        st.warning(
            "⚠️ FaultRayエンジンが見つかりません。**デモモード**で動作しています。"
            "  \n実際のシミュレーションには `pip install faultray` を実行してください。"
        )

    # ---------------------------------------------------------------------------
    # サイドバー: サンプル選択
    # ---------------------------------------------------------------------------
    with st.sidebar:
        st.header("サンプルトポロジー")
        sample_choice = st.radio(
            "テンプレートを選択",
            options=list(SAMPLE_TOPOLOGIES.keys()),
            index=0,
        )
        selected = SAMPLE_TOPOLOGIES[sample_choice]
        st.caption(selected["description"])

        if st.button("📋 サンプルを使う", use_container_width=True):
            st.session_state["topology_text"] = selected["yaml"]
            st.rerun()

        st.divider()
        st.header("使い方")
        st.markdown(
            """
            1. サンプルを選ぶか、YAMLを貼り付ける
            2. **シミュレーション開始** をクリック
            3. 結果・スコア・改善提案を確認する

            **依存タイプ:**
            - `requires` — 必須依存（障害が伝播）
            - `optional` — 任意依存（部分劣化）
            - `async` — 非同期依存（遅延伝播）
            """
        )

    # ---------------------------------------------------------------------------
    # メイン: トポロジー入力
    # ---------------------------------------------------------------------------
    st.subheader("1. インフラトポロジー")

    default_yaml = st.session_state.get("topology_text", SAMPLE_TOPOLOGIES["Webアプリ 3層構成"]["yaml"])

    topology_text = st.text_area(
        "YAML または JSON で定義してください",
        value=default_yaml,
        height=300,
        help="components（コンポーネント定義）とdependencies（依存関係）を記述します",
        key="topology_input",
    )

    # トポロジープレビュー
    col_preview, col_run = st.columns([1, 1])

    with col_preview:
        if st.button("🗺️ トポロジーを可視化", use_container_width=True):
            try:
                topo = parse_topology(topology_text)
                st.session_state["parsed_topology"] = topo
                st.session_state["show_topology"] = True
            except Exception as e:
                st.error(f"パースエラー: {e}")

    with col_run:
        run_clicked = st.button(
            "▶ シミュレーション開始",
            type="primary",
            use_container_width=True,
        )

    # トポロジー可視化
    if st.session_state.get("show_topology") and "parsed_topology" in st.session_state:
        st.subheader("トポロジーグラフ（テキスト表現）")
        render_topology_graph(st.session_state["parsed_topology"])

    # ---------------------------------------------------------------------------
    # シミュレーション実行
    # ---------------------------------------------------------------------------
    if run_clicked:
        try:
            topo = parse_topology(topology_text)
        except Exception as e:
            st.error(f"❌ トポロジーのパースに失敗しました: {e}")
            return

        with st.spinner("シミュレーション実行中..."):
            if FAULTRAY_AVAILABLE:
                try:
                    results = run_simulation(topo)
                    st.session_state["sim_results"] = results
                    st.session_state["sim_mode"] = "real"
                except Exception as e:
                    st.error(f"❌ シミュレーションエラー: {e}")
                    st.code(traceback.format_exc(), language="python")
                    return
            else:
                # デモモード: サンプル結果を使用
                import time
                time.sleep(0.8)  # 実行感を演出
                st.session_state["sim_results"] = DEMO_RESULTS
                st.session_state["sim_mode"] = "demo"

    # ---------------------------------------------------------------------------
    # 結果表示
    # ---------------------------------------------------------------------------
    if "sim_results" in st.session_state:
        results = st.session_state["sim_results"]
        mode = st.session_state.get("sim_mode", "demo")

        st.divider()
        st.subheader("2. シミュレーション結果")

        if mode == "demo":
            st.info("📊 デモモードのサンプルデータを表示しています（Webアプリ3層構成の例）")

        # スコアとサマリー
        col_score, col_stats = st.columns([1, 2])

        with col_score:
            render_score_gauge(results["resilience_score"])

        with col_stats:
            st.markdown("### シナリオ集計")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("総シナリオ数", results["total_scenarios"])
            c2.metric("🔴 CRITICAL", results["critical"], delta=None)
            c3.metric("🟡 WARNING", results["warning"], delta=None)
            c4.metric("🟢 PASS", results["passed"], delta=None)

            # 改善提案
            suggestions = results.get("suggestions", [])
            if suggestions:
                st.markdown("### 改善提案")
                for i, sug in enumerate(suggestions, 1):
                    st.markdown(f"**{i}.** {sug}")

        # 障害シナリオ一覧
        st.divider()
        st.subheader("3. 障害シナリオ詳細")

        # フィルタリング
        filter_col1, filter_col2 = st.columns([1, 3])
        with filter_col1:
            severity_filter = st.selectbox(
                "フィルタ",
                ["すべて", "CRITICAL のみ", "WARNING 以上", "PASS のみ"],
            )

        scenarios = results.get("scenarios", [])
        if severity_filter == "CRITICAL のみ":
            scenarios = [s for s in scenarios if s["severity"] == "CRITICAL"]
        elif severity_filter == "WARNING 以上":
            scenarios = [s for s in scenarios if s["severity"] in ("CRITICAL", "WARNING")]
        elif severity_filter == "PASS のみ":
            scenarios = [s for s in scenarios if s["severity"] == "PASS"]

        # スコア降順でソート
        scenarios_sorted = sorted(scenarios, key=lambda x: x["risk_score"], reverse=True)

        if not scenarios_sorted:
            st.info("該当するシナリオがありません")
        else:
            for i, scenario in enumerate(scenarios_sorted):
                render_scenario_card(scenario, i)

        # JSONエクスポート
        st.divider()
        st.subheader("4. 結果エクスポート")
        export_data = json.dumps(results, ensure_ascii=False, indent=2)
        st.download_button(
            label="📥 JSON でダウンロード",
            data=export_data,
            file_name="faultray-results.json",
            mime="application/json",
        )
        with st.expander("JSONプレビュー"):
            st.code(export_data[:3000] + ("..." if len(export_data) > 3000 else ""), language="json")

    # ---------------------------------------------------------------------------
    # フッター
    # ---------------------------------------------------------------------------
    st.divider()
    st.markdown(
        """
        <div style="text-align: center; color: #64748b; font-size: 0.85rem; padding: 1rem;">
            <strong>FaultRay</strong> — Zero-risk infrastructure chaos engineering simulator<br>
            © 2025-2026 Yutaro Maeda. Licensed under BSL 1.1.
        </div>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
