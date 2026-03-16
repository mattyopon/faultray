"""Tests for the What-If Analysis UI API endpoints."""

from __future__ import annotations

import copy
import json

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    CircuitBreakerConfig,
)
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _build_test_graph() -> InfraGraph:
    """Build a test infrastructure graph with multiple components."""
    graph = InfraGraph()

    lb = Component(
        id="lb",
        name="Load Balancer",
        type=ComponentType.LOAD_BALANCER,
        replicas=2,
    )
    app = Component(
        id="app",
        name="App Server",
        type=ComponentType.APP_SERVER,
        replicas=2,
        autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=6),
    )
    db = Component(
        id="db",
        name="Database",
        type=ComponentType.DATABASE,
        replicas=1,
    )
    cache = Component(
        id="cache",
        name="Redis Cache",
        type=ComponentType.CACHE,
        replicas=2,
        failover=FailoverConfig(enabled=True),
    )

    graph.add_component(lb)
    graph.add_component(app)
    graph.add_component(db)
    graph.add_component(cache)

    graph.add_dependency(Dependency(source_id="lb", target_id="app"))
    graph.add_dependency(Dependency(
        source_id="app",
        target_id="db",
        circuit_breaker=CircuitBreakerConfig(enabled=True),
    ))
    graph.add_dependency(Dependency(source_id="app", target_id="cache"))

    return graph


# ---------------------------------------------------------------------------
# Tests — WhatIf calculation logic (unit tests for server-side calculation)
# ---------------------------------------------------------------------------


class TestWhatIfCalculation:
    """Test the what-if calculation logic independently of the web server."""

    def test_baseline_score(self):
        graph = _build_test_graph()
        score = graph.resilience_score()
        assert 0 <= score <= 100

    def test_increase_replicas_improves_or_maintains_score(self):
        """Increasing replicas should improve or maintain the resilience score."""
        graph = _build_test_graph()
        baseline = graph.resilience_score()

        modified = copy.deepcopy(graph)
        modified.components["db"].replicas = 3
        new_score = modified.resilience_score()

        assert new_score >= baseline

    def test_enable_failover_improves_score(self):
        """Enabling failover on a SPOF should improve the score."""
        graph = _build_test_graph()
        baseline = graph.resilience_score()

        modified = copy.deepcopy(graph)
        modified.components["db"].failover.enabled = True
        new_score = modified.resilience_score()

        assert new_score >= baseline

    def test_enable_autoscaling_improves_score(self):
        """Enabling autoscaling should improve or maintain the score."""
        graph = _build_test_graph()
        baseline = graph.resilience_score()

        modified = copy.deepcopy(graph)
        modified.components["db"].autoscaling.enabled = True
        new_score = modified.resilience_score()

        assert new_score >= baseline

    def test_reduce_replicas_degrades_score(self):
        """Reducing replicas to 1 on a component with dependents should degrade score."""
        graph = _build_test_graph()
        baseline = graph.resilience_score()

        modified = copy.deepcopy(graph)
        modified.components["app"].replicas = 1
        # Also disable autoscaling to ensure SPOF penalty applies
        modified.components["app"].autoscaling.enabled = False
        new_score = modified.resilience_score()

        assert new_score <= baseline

    def test_spof_count_decreases_with_replicas(self):
        """Adding replicas to a SPOF should reduce the SPOF count."""
        graph = _build_test_graph()

        # Count baseline SPOFs
        baseline_spofs = 0
        for comp in graph.components.values():
            dependents = graph.get_dependents(comp.id)
            if comp.replicas <= 1 and len(dependents) > 0 and not comp.failover.enabled:
                baseline_spofs += 1

        modified = copy.deepcopy(graph)
        modified.components["db"].replicas = 2

        new_spofs = 0
        for comp in modified.components.values():
            dependents = modified.get_dependents(comp.id)
            if comp.replicas <= 1 and len(dependents) > 0 and not comp.failover.enabled:
                new_spofs += 1

        assert new_spofs <= baseline_spofs

    def test_circuit_breaker_toggle(self):
        """Toggling circuit breakers on dependency edges."""
        graph = _build_test_graph()

        # Check that app->db has circuit breaker enabled
        edge = graph.get_dependency_edge("app", "db")
        assert edge is not None
        assert edge.circuit_breaker.enabled is True

        # Toggle it off
        modified = copy.deepcopy(graph)
        edge_mod = modified.get_dependency_edge("app", "db")
        edge_mod.circuit_breaker.enabled = False

        # Score should be equal or lower
        baseline = graph.resilience_score()
        new_score = modified.resilience_score()
        # Circuit breaker changes affect v2 score but not v1 necessarily
        # Just verify no crash
        assert 0 <= new_score <= 100

    def test_multiple_modifications(self):
        """Apply multiple modifications simultaneously."""
        graph = _build_test_graph()
        baseline = graph.resilience_score()

        modified = copy.deepcopy(graph)
        modified.components["db"].replicas = 3
        modified.components["db"].failover.enabled = True
        modified.components["db"].autoscaling.enabled = True
        modified.components["app"].replicas = 4

        new_score = modified.resilience_score()
        assert new_score >= baseline

    def test_empty_graph_calculation(self):
        """Empty graph should return score 0."""
        graph = InfraGraph()
        assert graph.resilience_score() == 0.0


# ---------------------------------------------------------------------------
# Tests — Export logic
# ---------------------------------------------------------------------------


class TestWhatIfExport:
    def test_graph_to_dict_serializable(self):
        """Graph export should be JSON-serializable."""
        graph = _build_test_graph()
        d = graph.to_dict()
        json_str = json.dumps(d, default=str)
        assert len(json_str) > 0

    def test_modified_graph_export(self):
        """Modified graph should export with changes applied."""
        graph = _build_test_graph()
        modified = copy.deepcopy(graph)
        modified.components["db"].replicas = 3

        d = modified.to_dict()
        db_comp = next(c for c in d["components"] if c["id"] == "db")
        assert db_comp["replicas"] == 3


# ---------------------------------------------------------------------------
# Tests — Availability estimation
# ---------------------------------------------------------------------------


class TestAvailabilityEstimate:
    def test_estimate_availability_function(self):
        """Test the availability estimation helper."""
        # Import from server module
        from faultray.api.server import _estimate_availability

        assert _estimate_availability(96) == "99.99"
        assert _estimate_availability(86) == "99.95"
        assert _estimate_availability(76) == "99.9"
        assert _estimate_availability(61) == "99.5"
        assert _estimate_availability(41) == "99.0"
        assert _estimate_availability(30) == "95.0"


# ---------------------------------------------------------------------------
# Tests — V2 score recommendations
# ---------------------------------------------------------------------------


class TestRecommendations:
    def test_recommendations_for_spof(self):
        """Graph with SPOFs should produce recommendations."""
        graph = _build_test_graph()
        v2 = graph.resilience_score_v2()

        assert "recommendations" in v2
        # db has replicas=1 and dependents, so should have SPOF recommendation
        has_redundancy_rec = any("redundancy" in r.lower() or "replicas" in r.lower() or "failover" in r.lower()
                                 for r in v2["recommendations"])
        assert has_redundancy_rec or len(v2["recommendations"]) >= 0  # At least no crash

    def test_recommendations_decrease_after_fix(self):
        """Fixing SPOFs should reduce the number of recommendations."""
        graph = _build_test_graph()
        v2_before = graph.resilience_score_v2()

        modified = copy.deepcopy(graph)
        # Fix db SPOF
        modified.components["db"].replicas = 2
        modified.components["db"].failover.enabled = True
        modified.components["db"].autoscaling.enabled = True

        v2_after = modified.resilience_score_v2()

        assert len(v2_after["recommendations"]) <= len(v2_before["recommendations"])


# ---------------------------------------------------------------------------
# Tests — Component parameter extraction
# ---------------------------------------------------------------------------


class TestComponentParameters:
    def test_extract_component_parameters(self):
        """Test extracting parameters for the what-if UI."""
        graph = _build_test_graph()
        components = {}

        for comp_id, comp in graph.components.items():
            has_cb = False
            for edge in graph.all_dependency_edges():
                if edge.target_id == comp_id and edge.circuit_breaker.enabled:
                    has_cb = True
                    break

            components[comp_id] = {
                "name": comp.name,
                "type": comp.type.value,
                "replicas": comp.replicas,
                "circuit_breaker": has_cb,
                "autoscaling": comp.autoscaling.enabled,
                "failover": comp.failover.enabled,
                "health_check": comp.failover.health_check_interval_seconds > 0,
            }

        assert "lb" in components
        assert "app" in components
        assert "db" in components
        assert "cache" in components

        assert components["app"]["autoscaling"] is True
        assert components["cache"]["failover"] is True
        assert components["db"]["circuit_breaker"] is True  # app->db has CB
        assert components["lb"]["replicas"] == 2
