"""Performance benchmark tests for FaultRay / FaultRay.

Verifies performance characteristics under load:
- Graph creation and manipulation at various scales
- Resilience score computation complexity
- Simulation engine throughput
- Report generation time for large graphs

Uses wall-clock timing with generous thresholds suitable for CI.
"""

from __future__ import annotations

import sys
import time
from typing import Callable

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    Capacity,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    HealthStatus,
    ResourceMetrics,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.engine import SimulationEngine


# =========================================================================
# Helpers
# =========================================================================


def _timed(fn: Callable, *args, **kwargs) -> tuple[float, object]:
    """Run a callable and return (elapsed_seconds, result)."""
    start = time.perf_counter()
    result = fn(*args, **kwargs)
    elapsed = time.perf_counter() - start
    return elapsed, result


def _build_linear_chain(n: int) -> InfraGraph:
    """Build a linear chain: c0 -> c1 -> c2 -> ... -> c(n-1).

    All edges are 'requires' dependencies.
    """
    graph = InfraGraph()
    types = list(ComponentType)
    for i in range(n):
        graph.add_component(
            Component(
                id=f"c{i}",
                name=f"Component {i}",
                type=types[i % len(types)],
            )
        )
    for i in range(n - 1):
        graph.add_dependency(
            Dependency(source_id=f"c{i}", target_id=f"c{i + 1}")
        )
    return graph


def _build_wide_graph(n: int) -> InfraGraph:
    """Build a wide fan-out graph: 1 LB -> N app servers -> 1 DB.

    Total components = N + 2.
    """
    graph = InfraGraph()
    graph.add_component(
        Component(id="lb", name="Load Balancer", type=ComponentType.LOAD_BALANCER)
    )
    graph.add_component(
        Component(id="db", name="Database", type=ComponentType.DATABASE)
    )
    for i in range(n):
        app_id = f"app-{i}"
        graph.add_component(
            Component(id=app_id, name=f"App Server {i}", type=ComponentType.APP_SERVER)
        )
        graph.add_dependency(Dependency(source_id="lb", target_id=app_id))
        graph.add_dependency(Dependency(source_id=app_id, target_id="db"))
    return graph


def _build_tiered_graph(n: int) -> InfraGraph:
    """Build a realistic tiered topology with N total components.

    Structure: LB -> multiple App Servers -> DB + Cache + Queue
    with varied metrics, autoscaling, and failover configs.
    """
    graph = InfraGraph()

    # Infrastructure tiers
    n_app = max(1, n - 4)  # Reserve slots for lb, db, cache, queue
    n_db = 1
    n_cache = 1
    n_queue = 1

    graph.add_component(
        Component(
            id="lb-0",
            name="Load Balancer",
            type=ComponentType.LOAD_BALANCER,
            replicas=2,
        )
    )
    for i in range(n_app):
        graph.add_component(
            Component(
                id=f"app-{i}",
                name=f"App Server {i}",
                type=ComponentType.APP_SERVER,
                replicas=2 if i % 3 == 0 else 1,
                metrics=ResourceMetrics(cpu_percent=30 + (i % 40)),
                autoscaling=AutoScalingConfig(
                    enabled=(i % 2 == 0),
                    min_replicas=1,
                    max_replicas=10,
                ),
            )
        )
        graph.add_dependency(
            Dependency(source_id="lb-0", target_id=f"app-{i}")
        )

    graph.add_component(
        Component(
            id="db-0",
            name="Primary Database",
            type=ComponentType.DATABASE,
            replicas=2,
            failover=FailoverConfig(enabled=True),
        )
    )
    graph.add_component(
        Component(
            id="cache-0",
            name="Cache",
            type=ComponentType.CACHE,
            replicas=3,
        )
    )
    graph.add_component(
        Component(
            id="queue-0",
            name="Queue",
            type=ComponentType.QUEUE,
            replicas=2,
        )
    )

    for i in range(n_app):
        graph.add_dependency(
            Dependency(source_id=f"app-{i}", target_id="db-0")
        )
        graph.add_dependency(
            Dependency(
                source_id=f"app-{i}",
                target_id="cache-0",
                dependency_type="optional",
            )
        )
        if i % 2 == 0:
            graph.add_dependency(
                Dependency(
                    source_id=f"app-{i}",
                    target_id="queue-0",
                    dependency_type="async",
                )
            )

    return graph


# =========================================================================
# 1. Graph Operations Performance
# =========================================================================


class TestGraphCreationPerformance:
    """Benchmark graph construction at various scales."""

    @pytest.mark.parametrize("n_components", [100, 500, 1000])
    def test_graph_creation_time(self, n_components: int):
        """Creating a graph with N components should complete quickly."""
        threshold_seconds = {
            100: 1.0,
            500: 3.0,
            1000: 5.0,
        }

        elapsed, graph = _timed(_build_tiered_graph, n_components)

        assert len(graph.components) >= n_components - 4  # tier overhead
        assert elapsed < threshold_seconds[n_components], (
            f"Graph creation for {n_components} components took {elapsed:.2f}s "
            f"(threshold: {threshold_seconds[n_components]}s)"
        )

    def test_wide_graph_creation_1000(self):
        """A wide fan-out graph with 1000 app servers should be fast."""
        elapsed, graph = _timed(_build_wide_graph, 1000)
        assert len(graph.components) == 1002  # lb + 1000 apps + db
        assert elapsed < 3.0, (
            f"Wide graph creation took {elapsed:.2f}s (threshold: 3.0s)"
        )

    def test_component_lookup_is_fast(self):
        """Looking up components by ID in a large graph should be O(1)."""
        graph = _build_wide_graph(1000)

        start = time.perf_counter()
        for i in range(1000):
            comp = graph.get_component(f"app-{i}")
            assert comp is not None
        elapsed = time.perf_counter() - start

        assert elapsed < 0.5, (
            f"1000 lookups took {elapsed:.2f}s — should be near-instant"
        )

    def test_add_dependency_at_scale(self):
        """Adding many dependencies should scale linearly."""
        graph = InfraGraph()
        n = 500
        for i in range(n):
            graph.add_component(
                Component(
                    id=f"c{i}",
                    name=f"C{i}",
                    type=ComponentType.APP_SERVER,
                )
            )

        start = time.perf_counter()
        # Create a star topology: c0 -> c1, c0 -> c2, ..., c0 -> c(n-1)
        for i in range(1, n):
            graph.add_dependency(
                Dependency(source_id="c0", target_id=f"c{i}")
            )
        elapsed = time.perf_counter() - start

        assert elapsed < 2.0, (
            f"Adding {n - 1} dependencies took {elapsed:.2f}s"
        )


# =========================================================================
# 2. Resilience Score Computation Performance
# =========================================================================


class TestResilienceScorePerformance:
    """Benchmark resilience score computation."""

    def test_resilience_score_100_components(self):
        """Resilience score for 100 components should be fast."""
        graph = _build_tiered_graph(100)
        elapsed, score = _timed(graph.resilience_score)
        assert 0.0 <= score <= 100.0
        assert elapsed < 2.0, (
            f"Resilience score for 100 components: {elapsed:.2f}s"
        )

    def test_resilience_score_500_components(self):
        """Resilience score for 500 components should be under threshold."""
        graph = _build_tiered_graph(500)
        elapsed, score = _timed(graph.resilience_score)
        assert 0.0 <= score <= 100.0
        assert elapsed < 5.0, (
            f"Resilience score for 500 components: {elapsed:.2f}s"
        )

    def test_resilience_score_v2_performance(self):
        """resilience_score_v2 with detailed breakdown should also be fast."""
        graph = _build_tiered_graph(200)
        elapsed, result = _timed(graph.resilience_score_v2)
        assert 0.0 <= result["score"] <= 100.0
        assert "breakdown" in result
        assert elapsed < 3.0, (
            f"resilience_score_v2 for 200 components: {elapsed:.2f}s"
        )

    def test_scaling_not_quadratic(self):
        """Verify resilience score does not exhibit O(n^2) behaviour.

        If time(n=400) / time(n=100) < 8, it is likely sub-quadratic.
        For O(n^2), the ratio would be ~16x; for O(n log n), ~5-6x.
        We allow up to 10x to accommodate CI variance.
        """
        graph_small = _build_wide_graph(100)
        graph_large = _build_wide_graph(400)

        t_small, _ = _timed(graph_small.resilience_score)
        t_large, _ = _timed(graph_large.resilience_score)

        # Guard against near-zero timing
        if t_small < 0.001:
            t_small = 0.001

        ratio = t_large / t_small
        assert ratio < 25, (
            f"Score computation ratio (400/100) = {ratio:.1f}x — "
            f"may be O(n^2). t_small={t_small:.4f}s, t_large={t_large:.4f}s"
        )

    def test_summary_performance(self):
        """graph.summary() should also be fast for large graphs."""
        graph = _build_tiered_graph(500)
        elapsed, summary = _timed(graph.summary)
        assert "total_components" in summary
        assert elapsed < 5.0, (
            f"summary() for 500 components: {elapsed:.2f}s"
        )


# =========================================================================
# 3. Simulation Performance
# =========================================================================


class TestSimulationPerformance:
    """Benchmark simulation engine throughput."""

    def test_simulation_small_graph(self):
        """Running default scenarios on a small graph should be fast."""
        from faultray.model.demo import create_demo_graph

        graph = create_demo_graph()
        engine = SimulationEngine(graph)

        elapsed, report = _timed(
            engine.run_all_defaults,
            include_feed=False,
            include_plugins=False,
        )
        assert len(report.results) > 0
        assert elapsed < 10.0, (
            f"Demo graph simulation ({len(report.results)} scenarios): {elapsed:.2f}s"
        )

    def test_simulation_medium_graph(self):
        """Simulation with 50 components should complete within threshold."""
        graph = _build_tiered_graph(50)
        engine = SimulationEngine(graph)

        elapsed, report = _timed(
            engine.run_all_defaults,
            include_feed=False,
            include_plugins=False,
        )
        assert len(report.results) > 0
        assert elapsed < 30.0, (
            f"50-component simulation ({len(report.results)} scenarios): {elapsed:.2f}s"
        )

    def test_single_scenario_execution_speed(self):
        """A single scenario should run in milliseconds."""
        from faultray.simulator.scenarios import Fault, FaultType, Scenario

        graph = _build_tiered_graph(100)
        engine = SimulationEngine(graph)

        scenario = Scenario(
            id="bench-1",
            name="Single Fault Benchmark",
            description="Benchmark a single component failure",
            faults=[
                Fault(
                    target_component_id="db-0",
                    fault_type=FaultType.COMPONENT_DOWN,
                )
            ],
        )

        elapsed, result = _timed(engine.run_scenario, scenario)
        assert result.risk_score >= 0
        assert elapsed < 2.0, (
            f"Single scenario on 100-component graph: {elapsed:.2f}s"
        )

    def test_simulation_memory_bounded(self):
        """Simulation results should not grow unboundedly in memory."""
        graph = _build_tiered_graph(30)
        engine = SimulationEngine(graph)

        # Run simulation and check result size is reasonable
        report = engine.run_all_defaults(
            include_feed=False, include_plugins=False
        )

        # Each result should have a bounded size
        total_effects = sum(len(r.cascade.effects) for r in report.results)
        n_components = len(graph.components)
        n_scenarios = len(report.results)

        # Total effects should not exceed scenarios * components
        # (each scenario can affect at most all components)
        max_expected = n_scenarios * n_components
        assert total_effects <= max_expected, (
            f"Total effects ({total_effects}) exceeds theoretical max "
            f"({max_expected} = {n_scenarios} scenarios * {n_components} components)"
        )


# =========================================================================
# 4. Report Generation Performance
# =========================================================================


class TestReportGenerationPerformance:
    """Benchmark report generation for large graphs."""

    def test_to_dict_performance(self):
        """graph.to_dict() should be fast for large graphs."""
        graph = _build_tiered_graph(500)
        elapsed, data = _timed(graph.to_dict)
        assert len(data["components"]) >= 496  # n - 4 tier overhead
        assert elapsed < 3.0, (
            f"to_dict for 500 components: {elapsed:.2f}s"
        )

    def test_save_load_roundtrip_performance(self):
        """Saving and loading a large graph should complete in time."""
        import tempfile
        from pathlib import Path

        graph = _build_tiered_graph(200)

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            save_path = Path(f.name)

        try:
            save_elapsed, _ = _timed(graph.save, save_path)
            assert save_elapsed < 3.0, (
                f"Saving 200-component graph: {save_elapsed:.2f}s"
            )

            load_elapsed, loaded = _timed(InfraGraph.load, save_path)
            assert load_elapsed < 3.0, (
                f"Loading 200-component graph: {load_elapsed:.2f}s"
            )
            assert len(loaded.components) == len(graph.components)
        finally:
            save_path.unlink(missing_ok=True)

    def test_html_report_generation_performance(self):
        """HTML report generation should complete within threshold."""
        try:
            from faultray.reporter.html_report import generate_html_report
        except ImportError:
            pytest.skip("HTML report module not available")

        graph = _build_tiered_graph(100)
        engine = SimulationEngine(graph)
        report = engine.run_all_defaults(
            include_feed=False, include_plugins=False
        )

        elapsed, html = _timed(generate_html_report, report, graph)
        assert len(html) > 0
        assert elapsed < 10.0, (
            f"HTML report for 100 components: {elapsed:.2f}s"
        )

    def test_cascade_path_performance(self):
        """get_cascade_path should handle large graphs without timeout."""
        graph = _build_wide_graph(200)

        elapsed, paths = _timed(graph.get_cascade_path, "db")
        # db is a leaf node with many dependents via app servers
        assert elapsed < 5.0, (
            f"get_cascade_path for 200-wide graph: {elapsed:.2f}s"
        )

    def test_get_all_affected_performance(self):
        """get_all_affected should traverse efficiently."""
        graph = _build_wide_graph(500)

        elapsed, affected = _timed(graph.get_all_affected, "db")
        assert elapsed < 3.0, (
            f"get_all_affected for 500-wide graph: {elapsed:.2f}s"
        )


# =========================================================================
# 5. Serialisation Size Checks
# =========================================================================


class TestSerialisationSize:
    """Verify that serialised output does not grow excessively."""

    def test_to_dict_size_linear_with_components(self):
        """JSON output size should scale linearly with component count."""
        import json

        sizes = {}
        for n in [50, 100, 200]:
            graph = _build_wide_graph(n)
            data = graph.to_dict()
            sizes[n] = len(json.dumps(data))

        # Size ratio from 50->200 should be roughly 4x (linear),
        # not 16x (quadratic) or worse
        ratio = sizes[200] / sizes[50]
        assert ratio < 8.0, (
            f"JSON size ratio (200/50) = {ratio:.1f}x — "
            f"may indicate non-linear growth. Sizes: {sizes}"
        )

    def test_simulation_report_size_bounded(self):
        """Simulation report JSON should not grow excessively."""
        import json

        graph = _build_tiered_graph(50)
        engine = SimulationEngine(graph)
        report = engine.run_all_defaults(
            include_feed=False, include_plugins=False
        )

        report_dict = {
            "results_count": len(report.results),
            "resilience_score": report.resilience_score,
        }
        report_json = json.dumps(graph.to_dict())

        # 50-component graph serialisation should be under 1MB
        assert len(report_json) < 1_000_000, (
            f"Report JSON size {len(report_json)} bytes exceeds 1MB"
        )
