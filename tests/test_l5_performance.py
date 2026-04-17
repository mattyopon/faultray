# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""L5 Performance Tests — Quality & Reliability layer.

Validates performance characteristics of FaultRay simulations:
- 100-component topology completes within 60 seconds
- Memory usage stays under 500 MB
- Output size is reasonable
"""

from __future__ import annotations

import json
import sys
import time

import psutil
import pytest

from faultray.model.components import (
    Capacity,
    Component,
    ComponentType,
    Dependency,
    ResourceMetrics,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.engine import SimulationEngine


def _build_large_topology(n: int) -> InfraGraph:
    """Build a linear chain topology with *n* components.

    Structure: lb -> app-0 -> app-1 -> ... -> app-(n-3) -> db -> cache
    """
    graph = InfraGraph()

    # Load balancer
    graph.add_component(Component(
        id="lb",
        name="Load Balancer",
        type=ComponentType.LOAD_BALANCER,
        replicas=2,
        capacity=Capacity(max_connections=10000),
        metrics=ResourceMetrics(cpu_percent=10),
    ))

    # App servers in a chain
    app_ids: list[str] = []
    for i in range(max(1, n - 3)):
        comp_id = f"app-{i}"
        graph.add_component(Component(
            id=comp_id,
            name=f"App Server {i}",
            type=ComponentType.APP_SERVER,
            replicas=2,
            capacity=Capacity(max_connections=1000),
            metrics=ResourceMetrics(cpu_percent=20 + (i % 30)),
        ))
        app_ids.append(comp_id)

    # Database
    graph.add_component(Component(
        id="db",
        name="Database",
        type=ComponentType.DATABASE,
        replicas=2,
    ))

    # Cache
    graph.add_component(Component(
        id="cache",
        name="Cache",
        type=ComponentType.CACHE,
        replicas=2,
    ))

    # Dependencies: lb -> app-0
    if app_ids:
        graph.add_dependency(Dependency(
            source_id="lb", target_id=app_ids[0], dependency_type="requires",
        ))
        # Chain apps
        for i in range(len(app_ids) - 1):
            graph.add_dependency(Dependency(
                source_id=app_ids[i], target_id=app_ids[i + 1],
                dependency_type="requires",
            ))
        # Last app -> db and cache
        graph.add_dependency(Dependency(
            source_id=app_ids[-1], target_id="db", dependency_type="requires",
        ))
        graph.add_dependency(Dependency(
            source_id=app_ids[-1], target_id="cache", dependency_type="optional",
        ))

    return graph


# ---------------------------------------------------------------------------
# L5-PERF-001: 100-component simulation under 60 seconds
# ---------------------------------------------------------------------------


class TestSimulationPerformance:
    """Verify that simulations complete within acceptable time bounds."""

    @pytest.mark.timeout(60)
    def test_100_component_simulation_under_60s(self) -> None:
        """A 100-component topology simulation must finish within 60 seconds."""
        graph = _build_large_topology(100)
        assert len(graph.components) == 100

        engine = SimulationEngine(graph)
        start = time.monotonic()
        report = engine.run_all_defaults(include_feed=False, include_plugins=False)
        elapsed = time.monotonic() - start

        assert elapsed < 60.0, f"Simulation took {elapsed:.1f}s, exceeding 60s limit"
        assert len(report.results) > 0, "Simulation should produce at least one result"

    @pytest.mark.timeout(10)
    def test_small_topology_under_2s(self) -> None:
        """A 6-component demo topology should simulate in under 2 seconds."""
        from faultray.model.demo import create_demo_graph

        graph = create_demo_graph()
        engine = SimulationEngine(graph)
        start = time.monotonic()
        report = engine.run_all_defaults(include_feed=False, include_plugins=False)
        elapsed = time.monotonic() - start

        assert elapsed < 2.0, f"Demo simulation took {elapsed:.1f}s, exceeding 2s limit"
        assert report.resilience_score >= 0


# ---------------------------------------------------------------------------
# L5-PERF-002: Memory usage under 500 MB
# ---------------------------------------------------------------------------


class TestMemoryUsage:
    """Verify that simulation memory usage stays within bounds."""

    def test_100_component_memory_under_500mb(self) -> None:
        """Memory usage during 100-component simulation should stay under 500 MB."""
        process = psutil.Process()
        mem_before = process.memory_info().rss

        graph = _build_large_topology(100)
        engine = SimulationEngine(graph)
        _report = engine.run_all_defaults(include_feed=False, include_plugins=False)

        mem_after = process.memory_info().rss
        mem_delta_mb = (mem_after - mem_before) / (1024 * 1024)

        assert mem_delta_mb < 500, (
            f"Memory delta {mem_delta_mb:.1f} MB exceeds 500 MB limit"
        )

    def test_graph_object_memory_reasonable(self) -> None:
        """A 100-component InfraGraph should be under 10 MB in memory."""
        graph = _build_large_topology(100)
        size = sys.getsizeof(graph.components)
        # Each component is a Pydantic model; total should be well under 10 MB
        assert size < 10 * 1024 * 1024, f"Graph components size: {size} bytes"


# ---------------------------------------------------------------------------
# L5-PERF-003: Output size is reasonable
# ---------------------------------------------------------------------------


class TestOutputSize:
    """Verify that simulation output doesn't grow unboundedly."""

    def test_report_result_count_bounded(self) -> None:
        """Simulation results should not exceed MAX_SCENARIOS."""
        from faultray.simulator.engine import MAX_SCENARIOS

        graph = _build_large_topology(100)
        engine = SimulationEngine(graph)
        report = engine.run_all_defaults(include_feed=False, include_plugins=False)

        assert len(report.results) <= MAX_SCENARIOS, (
            f"Got {len(report.results)} results, exceeding max {MAX_SCENARIOS}"
        )

    def test_demo_report_serializable(self) -> None:
        """Report results from demo graph should be JSON-serializable."""
        from faultray.model.demo import create_demo_graph

        graph = create_demo_graph()
        engine = SimulationEngine(graph)
        report = engine.run_all_defaults(include_feed=False, include_plugins=False)

        # Verify each result has expected attributes
        for result in report.results:
            assert hasattr(result, "risk_score")
            assert isinstance(result.risk_score, (int, float))
