"""Performance benchmarking tests for ChaosProof simulation engine.

Verifies that simulations complete within acceptable time bounds
across small, medium, and large infrastructure graphs.
"""

from __future__ import annotations

import time

import pytest

from infrasim.model.components import (
    Capacity,
    Component,
    ComponentType,
    Dependency,
    ResourceMetrics,
)
from infrasim.model.demo import create_demo_graph
from infrasim.model.graph import InfraGraph
from infrasim.simulator.engine import SimulationEngine


def _build_tiered_graph(
    num_app_servers: int,
    num_db_replicas: int = 1,
    num_caches: int = 1,
    num_queues: int = 1,
) -> InfraGraph:
    """Build a realistic tiered topology: LB -> App(N) -> DB + Cache + Queue.

    Parameters
    ----------
    num_app_servers:
        Number of application server instances behind the load balancer.
    num_db_replicas:
        Number of database replicas (first is primary).
    num_caches:
        Number of cache nodes.
    num_queues:
        Number of message queue nodes.
    """
    graph = InfraGraph()

    # Load balancer
    lb = Component(
        id="lb-1",
        name="Load Balancer",
        type=ComponentType.LOAD_BALANCER,
        host="lb01",
        port=443,
        replicas=1,
        metrics=ResourceMetrics(cpu_percent=30, memory_percent=25, disk_percent=20),
        capacity=Capacity(max_connections=50000, max_rps=100000),
    )
    graph.add_component(lb)

    # App servers
    app_ids = []
    for i in range(num_app_servers):
        app = Component(
            id=f"app-{i}",
            name=f"App Server {i}",
            type=ComponentType.APP_SERVER,
            host=f"app{i:02d}",
            port=8080,
            replicas=1,
            metrics=ResourceMetrics(
                cpu_percent=55 + (i % 20),
                memory_percent=60 + (i % 15),
                disk_percent=40,
                network_connections=300 + (i * 10),
            ),
            capacity=Capacity(max_connections=1000, connection_pool_size=200, timeout_seconds=30),
        )
        graph.add_component(app)
        app_ids.append(app.id)
        # LB -> App
        graph.add_dependency(
            Dependency(
                source_id="lb-1",
                target_id=app.id,
                dependency_type="requires",
                weight=1.0,
            )
        )

    # Databases
    db_ids = []
    for i in range(num_db_replicas):
        db = Component(
            id=f"db-{i}",
            name=f"PostgreSQL {'primary' if i == 0 else f'replica-{i}'}",
            type=ComponentType.DATABASE,
            host=f"db{i:02d}",
            port=5432,
            replicas=1,
            metrics=ResourceMetrics(
                cpu_percent=40 + (i * 5),
                memory_percent=70,
                disk_percent=65,
                network_connections=80 + (i * 10),
            ),
            capacity=Capacity(max_connections=200, max_disk_gb=1000),
        )
        graph.add_component(db)
        db_ids.append(db.id)

    # Caches
    cache_ids = []
    for i in range(num_caches):
        cache = Component(
            id=f"cache-{i}",
            name=f"Redis {i}",
            type=ComponentType.CACHE,
            host=f"cache{i:02d}",
            port=6379,
            replicas=1,
            metrics=ResourceMetrics(
                cpu_percent=15, memory_percent=55, network_connections=500
            ),
            capacity=Capacity(max_connections=10000),
        )
        graph.add_component(cache)
        cache_ids.append(cache.id)

    # Queues
    queue_ids = []
    for i in range(num_queues):
        q = Component(
            id=f"queue-{i}",
            name=f"RabbitMQ {i}",
            type=ComponentType.QUEUE,
            host=f"mq{i:02d}",
            port=5672,
            replicas=1,
            metrics=ResourceMetrics(
                cpu_percent=20, memory_percent=35, disk_percent=30, network_connections=40
            ),
            capacity=Capacity(max_connections=2000),
        )
        graph.add_component(q)
        queue_ids.append(q.id)

    # Wire up: each app -> primary DB (required), optional cache, async queue
    for app_id in app_ids:
        # Required: app -> primary DB
        graph.add_dependency(
            Dependency(
                source_id=app_id,
                target_id=db_ids[0],
                dependency_type="requires",
                weight=1.0,
            )
        )
        # Optional: app -> cache (round-robin assignment)
        if cache_ids:
            cache_target = cache_ids[int(app_id.split("-")[1]) % len(cache_ids)]
            graph.add_dependency(
                Dependency(
                    source_id=app_id,
                    target_id=cache_target,
                    dependency_type="optional",
                    weight=0.7,
                )
            )
        # Async: app -> queue (round-robin assignment)
        if queue_ids:
            queue_target = queue_ids[int(app_id.split("-")[1]) % len(queue_ids)]
            graph.add_dependency(
                Dependency(
                    source_id=app_id,
                    target_id=queue_target,
                    dependency_type="async",
                    weight=0.5,
                )
            )

    # DB replicas depend on primary for replication
    for db_id in db_ids[1:]:
        graph.add_dependency(
            Dependency(
                source_id=db_id,
                target_id=db_ids[0],
                dependency_type="requires",
                weight=0.8,
            )
        )

    return graph


def _build_50_component_graph() -> InfraGraph:
    """Build a 50-component graph with realistic LB -> App -> DB/Cache/Queue topology."""
    # 1 LB + 40 App + 3 DB + 4 Cache + 2 Queue = 50
    return _build_tiered_graph(
        num_app_servers=40,
        num_db_replicas=3,
        num_caches=4,
        num_queues=2,
    )


def _build_100_component_graph() -> InfraGraph:
    """Build a 100-component graph with realistic topology."""
    # 1 LB + 85 App + 5 DB + 6 Cache + 3 Queue = 100
    return _build_tiered_graph(
        num_app_servers=85,
        num_db_replicas=5,
        num_caches=6,
        num_queues=3,
    )


class TestPerformanceBenchmarks:
    """Performance benchmarks for the simulation engine."""

    def test_small_graph_performance(self):
        """6-component demo should simulate in < 1 second."""
        graph = create_demo_graph()
        assert len(graph.components) == 6
        engine = SimulationEngine(graph)
        start = time.perf_counter()
        report = engine.run_all_defaults(include_feed=False, include_plugins=False)
        elapsed = time.perf_counter() - start
        assert elapsed < 1.0, f"Small graph took {elapsed:.3f}s (limit: 1.0s)"
        assert report.results, "Simulation should produce results"

    def test_medium_graph_performance(self):
        """50-component graph should simulate in < 10 seconds."""
        graph = _build_50_component_graph()
        assert len(graph.components) == 50
        engine = SimulationEngine(graph)
        start = time.perf_counter()
        report = engine.run_all_defaults(include_feed=False, include_plugins=False)
        elapsed = time.perf_counter() - start
        assert elapsed < 10.0, f"Medium graph took {elapsed:.3f}s (limit: 10.0s)"
        assert report.results, "Simulation should produce results"

    @pytest.mark.timeout(60)
    def test_large_graph_performance(self):
        """100-component graph should simulate in < 30 seconds."""
        graph = _build_100_component_graph()
        assert len(graph.components) == 100
        engine = SimulationEngine(graph)
        start = time.perf_counter()
        report = engine.run_all_defaults(include_feed=False, include_plugins=False)
        elapsed = time.perf_counter() - start
        assert elapsed < 30.0, f"Large graph took {elapsed:.3f}s (limit: 30.0s)"
        assert report.results, "Simulation should produce results"
