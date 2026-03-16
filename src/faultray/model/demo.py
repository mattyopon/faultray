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

    for dep in dependencies:
        graph.add_dependency(dep)

    return graph
