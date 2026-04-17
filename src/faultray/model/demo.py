# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Shared demo infrastructure builder.

Provides a canonical 6-component web application stack used by both the CLI
``demo`` command and the web dashboard ``/demo`` endpoint, ensuring they stay
in sync.
"""

from __future__ import annotations

from faultray.model.components import (
    Capacity,
    Component,
    ComponentType,
    Dependency,
    ResourceMetrics,
)
from faultray.model.graph import InfraGraph


def create_demo_graph() -> InfraGraph:
    """Build a realistic web application stack for demonstration.

    Components:
        - nginx (LB) on web01
        - api-server-1 on app01
        - api-server-2 on app02
        - PostgreSQL (primary) on db01
        - Redis (cache) on cache01
        - RabbitMQ on mq01
    """
    graph = InfraGraph()

    components = [
        Component(
            id="nginx",
            name="nginx (LB)",
            type=ComponentType.LOAD_BALANCER,
            host="web01",
            port=443,
            replicas=1,
            metrics=ResourceMetrics(cpu_percent=25, memory_percent=30, disk_percent=45),
            capacity=Capacity(max_connections=10000, max_rps=50000),
        ),
        Component(
            id="app-1",
            name="api-server-1",
            type=ComponentType.APP_SERVER,
            host="app01",
            port=8080,
            replicas=1,
            metrics=ResourceMetrics(
                cpu_percent=65, memory_percent=70, disk_percent=55, network_connections=450
            ),
            capacity=Capacity(max_connections=500, connection_pool_size=100, timeout_seconds=30),
        ),
        Component(
            id="app-2",
            name="api-server-2",
            type=ComponentType.APP_SERVER,
            host="app02",
            port=8080,
            replicas=1,
            metrics=ResourceMetrics(
                cpu_percent=60, memory_percent=68, disk_percent=55, network_connections=420
            ),
            capacity=Capacity(max_connections=500, connection_pool_size=100, timeout_seconds=30),
        ),
        Component(
            id="postgres",
            name="PostgreSQL (primary)",
            type=ComponentType.DATABASE,
            host="db01",
            port=5432,
            replicas=1,
            metrics=ResourceMetrics(
                cpu_percent=45, memory_percent=80, disk_percent=72, network_connections=90
            ),
            capacity=Capacity(max_connections=100, max_disk_gb=500),
        ),
        Component(
            id="redis",
            name="Redis (cache)",
            type=ComponentType.CACHE,
            host="cache01",
            port=6379,
            replicas=1,
            metrics=ResourceMetrics(
                cpu_percent=15, memory_percent=60, network_connections=200
            ),
            capacity=Capacity(max_connections=10000),
        ),
        Component(
            id="rabbitmq",
            name="RabbitMQ",
            type=ComponentType.QUEUE,
            host="mq01",
            port=5672,
            replicas=1,
            metrics=ResourceMetrics(
                cpu_percent=20, memory_percent=40, disk_percent=35, network_connections=50
            ),
            capacity=Capacity(max_connections=1000),
        ),
    ]

    for comp in components:
        graph.add_component(comp)

    dependencies = [
        Dependency(source_id="nginx", target_id="app-1", dependency_type="requires", weight=1.0),
        Dependency(source_id="nginx", target_id="app-2", dependency_type="requires", weight=1.0),
        Dependency(source_id="app-1", target_id="postgres", dependency_type="requires", weight=1.0),
        Dependency(source_id="app-2", target_id="postgres", dependency_type="requires", weight=1.0),
        Dependency(source_id="app-1", target_id="redis", dependency_type="optional", weight=0.7),
        Dependency(source_id="app-2", target_id="redis", dependency_type="optional", weight=0.7),
        Dependency(source_id="app-1", target_id="rabbitmq", dependency_type="async", weight=0.5),
        Dependency(source_id="app-2", target_id="rabbitmq", dependency_type="async", weight=0.5),
    ]

    # Agent components
    agent_components = [
        Component(
            id="support-agent",
            name="Support AI Agent",
            type=ComponentType.AI_AGENT,
            host="agent01",
            port=8090,
            replicas=1,
            metrics=ResourceMetrics(cpu_percent=40, memory_percent=55),
            parameters={
                "framework": "langchain",
                "model_id": "claude-sonnet-4-20250514",
                "max_context_tokens": 200000,
                "temperature": 0.7,
                "hallucination_risk": 0.05,
                "requires_grounding": 1,
                "max_iterations": 50,
                "circuit_breaker_on_hallucination": 1,
            },
        ),
        Component(
            id="llm-endpoint",
            name="Claude API Endpoint",
            type=ComponentType.LLM_ENDPOINT,
            host="api.anthropic.com",
            port=443,
            replicas=3,
            metrics=ResourceMetrics(cpu_percent=30, memory_percent=45),
            parameters={
                "provider": "anthropic",
                "rate_limit_rpm": 1000,
                "avg_latency_ms": 500.0,
                "availability_sla": 99.9,
            },
        ),
        Component(
            id="tool-db-query",
            name="DB Query Tool",
            type=ComponentType.TOOL_SERVICE,
            host="tool01",
            port=8091,
            replicas=1,
            metrics=ResourceMetrics(cpu_percent=20, memory_percent=30),
            parameters={
                "tool_type": "database_query",
                "idempotent": 1,
                "side_effects": 0,
                "avg_latency_ms": 100.0,
                "failure_rate": 0.02,
            },
        ),
    ]

    for comp in agent_components:
        graph.add_component(comp)

    agent_dependencies = [
        Dependency(source_id="support-agent", target_id="llm-endpoint", dependency_type="requires", weight=1.0),
        Dependency(source_id="support-agent", target_id="tool-db-query", dependency_type="requires", weight=0.8),
        Dependency(source_id="tool-db-query", target_id="postgres", dependency_type="requires", weight=1.0),
        Dependency(source_id="support-agent", target_id="redis", dependency_type="optional", weight=0.5),
    ]

    for dep in agent_dependencies:
        graph.add_dependency(dep)

    for dep in dependencies:
        graph.add_dependency(dep)

    return graph
