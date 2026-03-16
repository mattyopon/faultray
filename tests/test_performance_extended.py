"""Performance tests -- verify acceptable speed and resource usage under load.

Uses generous timeouts to accommodate CI environments.  All tests
exercise real simulation paths with no mocking.
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

import pytest

from faultray.model.components import (
    Capacity,
    Component,
    ComponentType,
    Dependency,
    ResourceMetrics,
)
from faultray.model.demo import create_demo_graph
from faultray.model.graph import InfraGraph
from faultray.simulator.engine import SimulationEngine


# ── Helpers ───────────────────────────────────────────────────────────────


def _build_large_graph(n_components: int) -> InfraGraph:
    """Build an N-component tiered graph: 1 LB -> N-3 app -> 1 DB + 1 cache."""
    graph = InfraGraph()

    # Load balancer
    graph.add_component(
        Component(
            id="lb-0",
            name="Load Balancer",
            type=ComponentType.LOAD_BALANCER,
            host="lb01",
            port=443,
            replicas=1,
            metrics=ResourceMetrics(cpu_percent=30, memory_percent=25),
            capacity=Capacity(max_connections=50000),
        )
    )

    # Database
    graph.add_component(
        Component(
            id="db-0",
            name="PostgreSQL primary",
            type=ComponentType.DATABASE,
            host="db01",
            port=5432,
            replicas=1,
            metrics=ResourceMetrics(cpu_percent=40, memory_percent=70, disk_percent=60),
            capacity=Capacity(max_connections=200),
        )
    )

    # Cache
    graph.add_component(
        Component(
            id="cache-0",
            name="Redis",
            type=ComponentType.CACHE,
            host="cache01",
            port=6379,
            replicas=1,
            metrics=ResourceMetrics(cpu_percent=15, memory_percent=50),
            capacity=Capacity(max_connections=10000),
        )
    )

    # App servers
    n_apps = max(1, n_components - 3)
    for i in range(n_apps):
        app_id = f"app-{i}"
        graph.add_component(
            Component(
                id=app_id,
                name=f"App Server {i}",
                type=ComponentType.APP_SERVER,
                host=f"app{i:03d}",
                port=8080,
                replicas=1,
                metrics=ResourceMetrics(
                    cpu_percent=50 + (i % 30),
                    memory_percent=55 + (i % 25),
                    disk_percent=40,
                    network_connections=200 + (i * 5),
                ),
                capacity=Capacity(max_connections=1000, timeout_seconds=30),
            )
        )
        # LB -> App
        graph.add_dependency(
            Dependency(source_id="lb-0", target_id=app_id, dependency_type="requires", weight=1.0)
        )
        # App -> DB
        graph.add_dependency(
            Dependency(source_id=app_id, target_id="db-0", dependency_type="requires", weight=1.0)
        )
        # App -> Cache (optional)
        graph.add_dependency(
            Dependency(source_id=app_id, target_id="cache-0", dependency_type="optional", weight=0.5)
        )

    return graph


# ── Demo simulation timing ────────────────────────────────────────────────


def test_demo_simulation_under_1_second():
    """6-component demo simulation should complete in < 1 second."""
    graph = create_demo_graph()
    engine = SimulationEngine(graph)
    start = time.perf_counter()
    report = engine.run_all_defaults()
    elapsed = time.perf_counter() - start
    assert elapsed < 1.0, f"Demo simulation took {elapsed:.2f}s (limit: 1.0s)"
    assert report.resilience_score >= 0.0


# ── Medium graph ──────────────────────────────────────────────────────────


def test_50_component_simulation_under_10_seconds():
    """50-component graph should simulate in < 10 seconds."""
    graph = _build_large_graph(50)
    engine = SimulationEngine(graph)
    start = time.perf_counter()
    report = engine.run_all_defaults(max_scenarios=500)
    elapsed = time.perf_counter() - start
    assert elapsed < 10.0, f"50-component simulation took {elapsed:.2f}s (limit: 10s)"
    assert len(report.results) > 0


# ── YAML load performance ────────────────────────────────────────────────


def test_yaml_load_100_components_under_2_seconds():
    """Loading a YAML with 100 components should take < 2 seconds."""
    import yaml
    from faultray.model.loader import load_yaml

    # Build a 100-component YAML dict
    components = []
    dependencies = []
    # 1 LB + 96 apps + 2 DB + 1 cache
    components.append({"id": "lb", "name": "LB", "type": "load_balancer"})
    components.append({"id": "db-primary", "name": "DB Primary", "type": "database"})
    components.append({"id": "db-replica", "name": "DB Replica", "type": "database"})
    components.append({"id": "cache", "name": "Cache", "type": "cache"})
    for i in range(96):
        components.append({
            "id": f"app-{i}",
            "name": f"App {i}",
            "type": "app_server",
            "host": f"app{i:03d}",
            "port": 8080,
        })
        dependencies.append({"source": "lb", "target": f"app-{i}", "type": "requires"})
        dependencies.append({"source": f"app-{i}", "target": "db-primary", "type": "requires"})
        dependencies.append({"source": f"app-{i}", "target": "cache", "type": "optional"})

    yaml_data = {
        "schema_version": "3.0",
        "components": components,
        "dependencies": dependencies,
    }

    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
        yaml.dump(yaml_data, f)
        tmp_path = Path(f.name)

    try:
        start = time.perf_counter()
        graph = load_yaml(tmp_path)
        elapsed = time.perf_counter() - start
        assert elapsed < 2.0, f"YAML load took {elapsed:.2f}s (limit: 2.0s)"
        assert len(graph.components) == 100
    finally:
        tmp_path.unlink(missing_ok=True)


# ── Cost engine performance ──────────────────────────────────────────────


def test_cost_engine_performance():
    """Cost engine on 50 components should run in < 5 seconds."""
    from faultray.simulator.cost_engine import CostImpactEngine

    graph = _build_large_graph(50)
    engine = SimulationEngine(graph)
    report = engine.run_all_defaults(max_scenarios=200)

    start = time.perf_counter()
    cost_engine = CostImpactEngine(graph)
    cost_report = cost_engine.analyze(report)
    elapsed = time.perf_counter() - start
    assert elapsed < 5.0, f"Cost engine took {elapsed:.2f}s (limit: 5.0s)"
    assert len(cost_report.impacts) > 0


# ── Security engine performance ──────────────────────────────────────────


def test_security_engine_performance():
    """Security engine on 20 components should run in < 3 seconds."""
    from faultray.simulator.security_engine import SecurityResilienceEngine

    graph = _build_large_graph(20)
    start = time.perf_counter()
    sec_engine = SecurityResilienceEngine(graph)
    report = sec_engine.simulate_all_attacks()
    elapsed = time.perf_counter() - start
    assert elapsed < 3.0, f"Security engine took {elapsed:.2f}s (limit: 3.0s)"
    assert report.total_attacks_simulated > 0


# ── Monte Carlo performance ──────────────────────────────────────────────


def test_monte_carlo_10000_trials_under_10_seconds():
    """10,000 Monte Carlo trials should complete in < 10 seconds."""
    from faultray.simulator.monte_carlo import run_monte_carlo

    graph = create_demo_graph()
    start = time.perf_counter()
    result = run_monte_carlo(graph, n_trials=10000)
    elapsed = time.perf_counter() - start
    assert elapsed < 10.0, f"Monte Carlo took {elapsed:.2f}s (limit: 10.0s)"
    assert result.n_trials == 10000
    assert 0.0 <= result.availability_mean <= 100.0


# ── Fuzzer performance ───────────────────────────────────────────────────


def test_fuzzer_100_iterations_under_30_seconds():
    """100 fuzzer iterations should complete in < 30 seconds."""
    from faultray.simulator.chaos_fuzzer import ChaosFuzzer

    graph = create_demo_graph()
    fuzzer = ChaosFuzzer(graph, seed=42)
    start = time.perf_counter()
    report = fuzzer.fuzz(iterations=100)
    elapsed = time.perf_counter() - start
    assert elapsed < 30.0, f"Fuzzer took {elapsed:.2f}s (limit: 30.0s)"
    assert report.total_iterations == 100


# ── Save / load roundtrip ────────────────────────────────────────────────


def test_graph_save_load_roundtrip_performance():
    """Save + load of 100-component graph should take < 1 second."""
    graph = _build_large_graph(100)

    with tempfile.TemporaryDirectory() as td:
        out_path = Path(td) / "model.json"

        start = time.perf_counter()
        graph.save(out_path)
        loaded = InfraGraph.load(out_path)
        elapsed = time.perf_counter() - start

        assert elapsed < 1.0, f"Save + load took {elapsed:.2f}s (limit: 1.0s)"
        assert len(loaded.components) == len(graph.components)


# ── Memory usage ──────────────────────────────────────────────────────────


def test_memory_usage_stays_reasonable():
    """Simulation should not use more than 500 MB for demo graph."""
    import tracemalloc

    tracemalloc.start()
    graph = create_demo_graph()
    engine = SimulationEngine(graph)
    report = engine.run_all_defaults()
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    peak_mb = peak / (1024 * 1024)
    assert peak < 500 * 1024 * 1024, f"Peak memory: {peak_mb:.0f} MB (limit: 500 MB)"
    assert report.resilience_score >= 0.0


# ── Concurrent simulations ───────────────────────────────────────────────


def test_concurrent_simulations_safe():
    """Running 2 simulations concurrently should not corrupt results."""
    import threading

    results: list[float] = []
    errors: list[str] = []

    def run_sim():
        try:
            g = create_demo_graph()
            e = SimulationEngine(g)
            r = e.run_all_defaults()
            results.append(r.resilience_score)
        except Exception as exc:
            errors.append(str(exc))

    t1 = threading.Thread(target=run_sim)
    t2 = threading.Thread(target=run_sim)
    t1.start()
    t2.start()
    t1.join(timeout=30)
    t2.join(timeout=30)

    assert not errors, f"Concurrent simulation errors: {errors}"
    assert len(results) == 2
    # Both should get the same score (independent graphs, no shared mutable state)
    assert results[0] == results[1], (
        f"Concurrent results diverged: {results[0]} vs {results[1]}"
    )
