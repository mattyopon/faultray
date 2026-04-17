# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""L7 Resource Constraint Tests — Generality & Adaptability layer.

Validates FaultRay behavior under resource constraints:
- Empty topology handling
- Very large topologies (OOM prevention)
- Edge case component counts
"""

from __future__ import annotations

import pytest

from faultray.model.components import (
    Component,
    ComponentType,
    Dependency,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.engine import SimulationEngine
from faultray.simulator.monte_carlo import run_monte_carlo


# ---------------------------------------------------------------------------
# L7-RES-001: Empty topology doesn't crash
# ---------------------------------------------------------------------------


class TestEmptyTopology:
    """Verify graceful handling of empty or minimal topologies."""

    def test_empty_graph_simulation(self) -> None:
        """SimulationEngine with 0 components should not crash."""
        graph = InfraGraph()
        engine = SimulationEngine(graph)
        report = engine.run_all_defaults(include_feed=False, include_plugins=False)
        assert report.resilience_score >= 0
        # May contain traffic-spike scenarios even with 0 components
        assert isinstance(report.results, list)

    def test_empty_graph_monte_carlo(self) -> None:
        """Monte Carlo on empty graph should return zeroed result."""
        graph = InfraGraph()
        result = run_monte_carlo(graph, n_trials=100, seed=42)
        assert result.availability_mean == 0.0
        assert result.n_trials == 100

    def test_single_component_graph(self) -> None:
        """A graph with a single component should simulate successfully."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="lonely",
            name="Lonely Server",
            type=ComponentType.APP_SERVER,
        ))
        engine = SimulationEngine(graph)
        report = engine.run_all_defaults(include_feed=False, include_plugins=False)
        assert len(report.results) > 0

    def test_single_component_monte_carlo(self) -> None:
        """Monte Carlo with a single component should return valid result."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="solo",
            name="Solo",
            type=ComponentType.DATABASE,
        ))
        result = run_monte_carlo(graph, n_trials=100, seed=42)
        assert 0.0 < result.availability_mean <= 1.0


# ---------------------------------------------------------------------------
# L7-RES-002: Large topology doesn't OOM
# ---------------------------------------------------------------------------


class TestLargeTopology:
    """Verify that large topologies are handled without excessive memory."""

    def test_1000_component_graph_creation(self) -> None:
        """Creating a 1000-component graph should succeed without OOM."""
        graph = InfraGraph()
        for i in range(1000):
            graph.add_component(Component(
                id=f"comp-{i}",
                name=f"Component {i}",
                type=ComponentType.APP_SERVER,
            ))
        assert len(graph.components) == 1000

    def test_1000_component_graph_with_dependencies(self) -> None:
        """A 1000-component linear chain should be constructible."""
        graph = InfraGraph()
        for i in range(1000):
            graph.add_component(Component(
                id=f"c-{i}",
                name=f"C{i}",
                type=ComponentType.APP_SERVER,
            ))
        for i in range(999):
            graph.add_dependency(Dependency(
                source_id=f"c-{i}",
                target_id=f"c-{i+1}",
                dependency_type="requires",
            ))
        assert len(graph.all_dependency_edges()) == 999

    def test_monte_carlo_small_trials_large_graph(self) -> None:
        """Monte Carlo with few trials on large graph should complete."""
        graph = InfraGraph()
        for i in range(200):
            graph.add_component(Component(
                id=f"n-{i}",
                name=f"Node {i}",
                type=ComponentType.APP_SERVER,
            ))
        # Only 10 trials to keep test fast
        result = run_monte_carlo(graph, n_trials=10, seed=42)
        assert result.n_trials == 10
        assert result.availability_mean >= 0.0


# ---------------------------------------------------------------------------
# L7-RES-003: Edge case component counts
# ---------------------------------------------------------------------------


class TestEdgeCaseComponentCounts:
    """Test boundary conditions for component counts."""

    def test_two_component_graph(self) -> None:
        """A minimal dependency graph (2 components) should work."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="a", name="A", type=ComponentType.WEB_SERVER,
        ))
        graph.add_component(Component(
            id="b", name="B", type=ComponentType.DATABASE,
        ))
        graph.add_dependency(Dependency(
            source_id="a", target_id="b", dependency_type="requires",
        ))
        engine = SimulationEngine(graph)
        report = engine.run_all_defaults(include_feed=False, include_plugins=False)
        assert len(report.results) > 0

    def test_all_component_types(self) -> None:
        """A graph with all component types should be simulatable."""
        graph = InfraGraph()
        for ct in ComponentType:
            graph.add_component(Component(
                id=f"comp-{ct.value}",
                name=f"Component {ct.value}",
                type=ct,
            ))
        assert len(graph.components) == len(ComponentType)
        engine = SimulationEngine(graph)
        report = engine.run_all_defaults(include_feed=False, include_plugins=False)
        assert report.resilience_score >= 0

    def test_high_replica_count(self) -> None:
        """Components with high replica counts should not cause issues."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="ha",
            name="HA Server",
            type=ComponentType.APP_SERVER,
            replicas=100,
        ))
        result = run_monte_carlo(graph, n_trials=10, seed=42)
        # High replica count should yield very high availability
        assert result.availability_mean > 0.99
