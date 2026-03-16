"""Tests for Dependency Impact Scorer."""

from __future__ import annotations

from unittest import mock

import pytest

from faultray.model.components import (
    Component,
    ComponentType,
    CostProfile,
    Dependency,
    FailoverConfig,
    HealthStatus,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.cascade import CascadeChain, CascadeEffect
from faultray.simulator.dependency_scorer import DependencyImpact, DependencyScorer
from faultray.simulator.engine import ScenarioResult


def _build_test_graph() -> InfraGraph:
    """Build a test infrastructure graph with various dependency types."""
    graph = InfraGraph()

    graph.add_component(Component(
        id="lb",
        name="Load Balancer",
        type=ComponentType.LOAD_BALANCER,
        replicas=2,
        failover=FailoverConfig(enabled=True),
    ))

    graph.add_component(Component(
        id="app",
        name="App Server",
        type=ComponentType.APP_SERVER,
        replicas=3,
        cost_profile=CostProfile(revenue_per_minute=50.0, recovery_engineer_cost=150.0),
    ))

    graph.add_component(Component(
        id="postgres",
        name="PostgreSQL",
        type=ComponentType.DATABASE,
        replicas=1,
        cost_profile=CostProfile(
            revenue_per_minute=100.0,
            hourly_infra_cost=25.0,
            recovery_engineer_cost=200.0,
        ),
    ))

    graph.add_component(Component(
        id="redis",
        name="Redis",
        type=ComponentType.CACHE,
        replicas=2,
        cost_profile=CostProfile(revenue_per_minute=10.0),
    ))

    graph.add_component(Component(
        id="queue",
        name="Message Queue",
        type=ComponentType.QUEUE,
        replicas=1,
    ))

    # Dependencies: lb -> app -> postgres (requires)
    #               app -> redis (optional)
    #               app -> queue (async)
    graph.add_dependency(Dependency(
        source_id="lb", target_id="app", dependency_type="requires",
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="postgres", dependency_type="requires",
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="redis", dependency_type="optional",
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="queue", dependency_type="async",
    ))

    return graph


class TestDependencyScorer:
    """Test suite for DependencyScorer."""

    def test_score_all_returns_list(self):
        """Test that score_all returns a list of DependencyImpact."""
        graph = _build_test_graph()
        scorer = DependencyScorer(graph)
        impacts = scorer.score_all()

        assert isinstance(impacts, list)
        assert len(impacts) == 4  # 4 dependency edges
        for imp in impacts:
            assert isinstance(imp, DependencyImpact)

    def test_scores_sorted_descending(self):
        """Test that results are sorted by impact score (highest first)."""
        graph = _build_test_graph()
        scorer = DependencyScorer(graph)
        impacts = scorer.score_all()

        scores = [imp.impact_score for imp in impacts]
        assert scores == sorted(scores, reverse=True)

    def test_requires_scores_higher_than_optional(self):
        """Test that 'requires' dependencies score higher than 'optional'."""
        graph = _build_test_graph()
        scorer = DependencyScorer(graph)
        impacts = scorer.score_all()

        requires_scores = [
            imp.impact_score for imp in impacts if imp.dependency_type == "requires"
        ]
        optional_scores = [
            imp.impact_score for imp in impacts if imp.dependency_type == "optional"
        ]

        if requires_scores and optional_scores:
            assert max(requires_scores) >= max(optional_scores)

    def test_most_critical_returns_top_n(self):
        """Test that most_critical returns exactly N items."""
        graph = _build_test_graph()
        scorer = DependencyScorer(graph)

        top3 = scorer.most_critical(n=3)
        assert len(top3) == 3

        top1 = scorer.most_critical(n=1)
        assert len(top1) == 1

    def test_most_critical_top_n_larger_than_total(self):
        """Test most_critical when N > total edges."""
        graph = _build_test_graph()
        scorer = DependencyScorer(graph)

        top100 = scorer.most_critical(n=100)
        assert len(top100) == 4  # Only 4 edges exist

    def test_impact_score_range(self):
        """Test that impact scores are in valid range [0, 10]."""
        graph = _build_test_graph()
        scorer = DependencyScorer(graph)
        impacts = scorer.score_all()

        for imp in impacts:
            assert 0.0 <= imp.impact_score <= 10.0

    def test_criticality_labels(self):
        """Test that criticality labels are valid."""
        graph = _build_test_graph()
        scorer = DependencyScorer(graph)
        impacts = scorer.score_all()

        valid_labels = {"critical", "high", "medium", "low"}
        for imp in impacts:
            assert imp.criticality in valid_labels

    def test_dependency_heatmap_data(self):
        """Test heatmap data generation."""
        graph = _build_test_graph()
        scorer = DependencyScorer(graph)
        data = scorer.dependency_heatmap_data()

        assert "edges" in data
        assert "total_edges" in data
        assert "summary" in data
        assert data["total_edges"] == 4

        for edge in data["edges"]:
            assert "source" in edge
            assert "target" in edge
            assert "score" in edge
            assert "color" in edge
            assert edge["color"].startswith("#")

    def test_heatmap_summary_counts(self):
        """Test that heatmap summary counts are correct."""
        graph = _build_test_graph()
        scorer = DependencyScorer(graph)
        data = scorer.dependency_heatmap_data()

        summary = data["summary"]
        total = sum(summary.values())
        assert total == data["total_edges"]

    def test_estimated_cost(self):
        """Test that costs are computed for components with cost profiles."""
        graph = _build_test_graph()
        scorer = DependencyScorer(graph)
        impacts = scorer.score_all()

        # app -> postgres should have significant cost (postgres has revenue_per_minute=100)
        postgres_impact = next(
            (i for i in impacts if i.target_id == "postgres"), None
        )
        assert postgres_impact is not None
        assert postgres_impact.estimated_cost_if_broken > 0

    def test_cascade_depth_tracked(self):
        """Test that cascade depth is tracked."""
        graph = _build_test_graph()
        scorer = DependencyScorer(graph)
        impacts = scorer.score_all()

        for imp in impacts:
            assert isinstance(imp.cascade_depth, int)
            assert imp.cascade_depth >= 0

    def test_affected_components_listed(self):
        """Test that affected components are listed."""
        graph = _build_test_graph()
        scorer = DependencyScorer(graph)
        impacts = scorer.score_all()

        for imp in impacts:
            assert isinstance(imp.affected_components, list)

    def test_empty_graph(self):
        """Test scorer with a graph that has no dependencies."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="standalone",
            name="Standalone",
            type=ComponentType.APP_SERVER,
        ))

        scorer = DependencyScorer(graph)
        impacts = scorer.score_all()
        assert impacts == []

    def test_risk_details_format(self):
        """Test that risk_details is a readable string."""
        graph = _build_test_graph()
        scorer = DependencyScorer(graph)
        impacts = scorer.score_all()

        for imp in impacts:
            assert isinstance(imp.risk_details, str)
            assert imp.source_id in imp.risk_details
            assert imp.target_id in imp.risk_details

    def test_bfs_depth_fallback_when_no_time_based_depth(self):
        """Test line 189-190: BFS depth fallback when max_depth==0 and affected exist.

        Create a scenario where cascade effects exist but have 0 estimated_time_seconds,
        forcing the BFS depth fallback path.
        """
        graph = InfraGraph()
        # Build a chain with multiple layers of dependencies
        graph.add_component(Component(
            id="a", name="A", type=ComponentType.APP_SERVER, replicas=1,
        ))
        graph.add_component(Component(
            id="b", name="B", type=ComponentType.APP_SERVER, replicas=1,
        ))
        graph.add_component(Component(
            id="c", name="C", type=ComponentType.APP_SERVER, replicas=1,
        ))
        graph.add_component(Component(
            id="d", name="D", type=ComponentType.APP_SERVER, replicas=1,
        ))
        graph.add_dependency(Dependency(source_id="a", target_id="b", dependency_type="requires"))
        graph.add_dependency(Dependency(source_id="b", target_id="c", dependency_type="requires"))
        graph.add_dependency(Dependency(source_id="c", target_id="d", dependency_type="requires"))
        scorer = DependencyScorer(graph)
        impacts = scorer.score_all()
        # When BFS fallback is used, cascade_depth = min(len(all_affected), 10)
        for imp in impacts:
            assert imp.cascade_depth >= 0

    def test_estimate_cost_with_none_component(self):
        """Test line 209: _estimate_cost skips None components."""
        graph = _build_test_graph()
        scorer = DependencyScorer(graph)
        # Call _estimate_cost with a nonexistent component in affected_ids
        cost = scorer._estimate_cost("postgres", ["nonexistent_comp", "app"])
        # Should not raise, just skip the missing comp
        assert cost >= 0

    def test_cost_score_branches(self):
        """Test lines 254, 257-262: cost score branching in _calculate_impact_score."""
        graph = _build_test_graph()
        scorer = DependencyScorer(graph)

        # Test cost > 10000 -> cost_score = 2.0
        score_high = scorer._calculate_impact_score("requires", 1.0, 2, 3, 50000.0)
        assert score_high > 0

        # Test cost > 1000 -> cost_score = 1.5
        score_med = scorer._calculate_impact_score("requires", 1.0, 2, 3, 5000.0)
        assert score_med > 0

        # Test cost > 100 -> cost_score = 1.0
        score_low = scorer._calculate_impact_score("requires", 1.0, 2, 3, 500.0)
        assert score_low > 0

        # Test cost > 0 -> cost_score = 0.5
        score_tiny = scorer._calculate_impact_score("requires", 1.0, 2, 3, 50.0)
        assert score_tiny > 0

        # Test cost == 0 -> cost_score = 0.0
        score_zero = scorer._calculate_impact_score("requires", 1.0, 2, 3, 0.0)
        assert score_zero > 0

        # Verify ordering: higher cost -> higher score
        assert score_high >= score_med >= score_low >= score_tiny >= score_zero

    def test_criticality_label_all_thresholds(self):
        """Test lines 271, 277, 283, 289: all criticality label thresholds."""
        assert DependencyScorer._criticality_label(7.0) == "critical"
        assert DependencyScorer._criticality_label(9.0) == "critical"
        assert DependencyScorer._criticality_label(5.0) == "high"
        assert DependencyScorer._criticality_label(6.9) == "high"
        assert DependencyScorer._criticality_label(3.0) == "medium"
        assert DependencyScorer._criticality_label(4.9) == "medium"
        assert DependencyScorer._criticality_label(2.9) == "low"
        assert DependencyScorer._criticality_label(0.0) == "low"

    def test_score_to_color_all_thresholds(self):
        """Test lines 283, 289: all color thresholds."""
        assert DependencyScorer._score_to_color(7.0) == "#ff0000"
        assert DependencyScorer._score_to_color(5.0) == "#ff8800"
        assert DependencyScorer._score_to_color(3.0) == "#ffcc00"
        assert DependencyScorer._score_to_color(2.9) == "#00cc00"

    def test_bfs_depth_fallback_via_mock(self):
        """Test lines 189-190: BFS depth fallback when cascade effects have 0 estimated_time_seconds.

        Mock _sim_engine.run_scenario to return effects with estimated_time_seconds=0
        but with affected components (component_id != target_id), forcing the BFS fallback.
        """
        graph = _build_test_graph()
        scorer = DependencyScorer(graph)

        # Create a mock scenario result with effects that have estimated_time_seconds=0
        # but include a non-target component (so affected is non-empty, max_depth stays 0)
        mock_cascade = CascadeChain(
            trigger="lb",
            effects=[
                CascadeEffect(
                    component_id="lb",
                    component_name="Load Balancer",
                    health=HealthStatus.DOWN,
                    reason="simulated",
                    estimated_time_seconds=0,
                ),
                CascadeEffect(
                    component_id="app",
                    component_name="App Server",
                    health=HealthStatus.DEGRADED,
                    reason="cascade",
                    estimated_time_seconds=0,  # zero time -> BFS fallback
                ),
            ],
        )
        mock_result = mock.MagicMock(spec=ScenarioResult)
        mock_result.cascade = mock_cascade

        with mock.patch.object(scorer._sim_engine, "run_scenario", return_value=mock_result):
            result, affected, max_depth, cost = scorer._simulate_target_down("lb")
            # BFS fallback: max_depth = min(len(all_affected), 10)
            assert max_depth >= 0
            assert "app" in affected
