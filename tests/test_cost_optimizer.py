"""Tests for the Infrastructure Cost Optimizer."""

from __future__ import annotations

import pytest

from infrasim.model.components import (
    AutoScalingConfig,
    CircuitBreakerConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    ResourceMetrics,
)
from infrasim.model.graph import InfraGraph
from infrasim.simulator.cost_optimizer import (
    CostOptimizer,
    OptimizationReport,
    OptimizationSuggestion,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def overprovisioned_graph() -> InfraGraph:
    """Graph with many replicas and low utilization - ripe for optimization."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb", name="Load Balancer", type=ComponentType.LOAD_BALANCER,
        replicas=4,
        metrics=ResourceMetrics(cpu_percent=5.0, memory_percent=10.0),
    ))
    graph.add_component(Component(
        id="app", name="App Server", type=ComponentType.APP_SERVER,
        replicas=5,
        metrics=ResourceMetrics(cpu_percent=10.0, memory_percent=15.0),
        autoscaling=AutoScalingConfig(enabled=True),
    ))
    graph.add_component(Component(
        id="db", name="PostgreSQL", type=ComponentType.DATABASE,
        replicas=3,
        metrics=ResourceMetrics(cpu_percent=8.0, memory_percent=12.0),
        failover=FailoverConfig(enabled=True),
    ))
    graph.add_component(Component(
        id="cache", name="Redis", type=ComponentType.CACHE,
        replicas=3,
        metrics=ResourceMetrics(cpu_percent=3.0, memory_percent=5.0),
    ))
    graph.add_dependency(Dependency(source_id="lb", target_id="app", dependency_type="requires"))
    graph.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))
    graph.add_dependency(Dependency(source_id="app", target_id="cache", dependency_type="optional"))
    return graph


@pytest.fixture
def minimal_graph() -> InfraGraph:
    """Graph with minimal resources - no room for optimization."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App Server", type=ComponentType.APP_SERVER,
        replicas=1,
        metrics=ResourceMetrics(cpu_percent=80.0, memory_percent=70.0),
    ))
    graph.add_component(Component(
        id="db", name="PostgreSQL", type=ComponentType.DATABASE,
        replicas=1,
        metrics=ResourceMetrics(cpu_percent=60.0, memory_percent=50.0),
    ))
    graph.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))
    return graph


@pytest.fixture
def medium_graph() -> InfraGraph:
    """A moderately provisioned graph."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb", name="Load Balancer", type=ComponentType.LOAD_BALANCER,
        replicas=2,
    ))
    graph.add_component(Component(
        id="app", name="App Server", type=ComponentType.APP_SERVER,
        replicas=3,
        autoscaling=AutoScalingConfig(enabled=True),
    ))
    graph.add_component(Component(
        id="db", name="PostgreSQL", type=ComponentType.DATABASE,
        replicas=2,
        failover=FailoverConfig(enabled=True),
    ))
    graph.add_dependency(Dependency(source_id="lb", target_id="app", dependency_type="requires"))
    graph.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))
    return graph


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCostOptimizerBasics:
    """Basic cost optimizer functionality."""

    def test_report_structure(self, overprovisioned_graph: InfraGraph):
        """Report should have the expected fields."""
        optimizer = CostOptimizer(overprovisioned_graph, min_resilience_score=50.0)
        report = optimizer.optimize()

        assert isinstance(report, OptimizationReport)
        assert report.current_monthly_cost > 0
        assert report.resilience_before >= 0
        assert report.resilience_after >= 0

    def test_overprovisioned_has_suggestions(self, overprovisioned_graph: InfraGraph):
        """Overprovisioned graph should have optimization suggestions."""
        optimizer = CostOptimizer(overprovisioned_graph, min_resilience_score=50.0)
        report = optimizer.optimize()
        assert len(report.suggestions) > 0

    def test_minimal_has_fewer_suggestions(self, minimal_graph: InfraGraph):
        """Minimal graph should have few or no suggestions."""
        optimizer = CostOptimizer(minimal_graph, min_resilience_score=0.0)
        report = optimizer.optimize()
        # Minimal graph has replicas=1, so no reduce_replicas or spot suggestions
        reduce_suggestions = [
            s for s in report.suggestions if s.action == "reduce_replicas"
        ]
        assert len(reduce_suggestions) == 0

    def test_savings_are_non_negative(self, overprovisioned_graph: InfraGraph):
        """All savings should be non-negative."""
        optimizer = CostOptimizer(overprovisioned_graph, min_resilience_score=50.0)
        report = optimizer.optimize()
        for suggestion in report.suggestions:
            assert suggestion.savings_monthly >= 0

    def test_optimized_cost_is_lower(self, overprovisioned_graph: InfraGraph):
        """Optimized cost should be lower or equal to current cost."""
        optimizer = CostOptimizer(overprovisioned_graph, min_resilience_score=50.0)
        report = optimizer.optimize()
        assert report.optimized_monthly_cost <= report.current_monthly_cost


class TestCostOptimizerSuggestions:
    """Test specific suggestion types."""

    def test_reduce_replicas_suggested(self, overprovisioned_graph: InfraGraph):
        """Should suggest reducing replicas for over-provisioned components."""
        optimizer = CostOptimizer(overprovisioned_graph, min_resilience_score=50.0)
        report = optimizer.optimize()
        reduce_suggestions = [s for s in report.suggestions if s.action == "reduce_replicas"]
        assert len(reduce_suggestions) > 0

    def test_spot_instances_suggested(self, overprovisioned_graph: InfraGraph):
        """Should suggest spot instances for stateless services."""
        optimizer = CostOptimizer(overprovisioned_graph, min_resilience_score=50.0)
        report = optimizer.optimize()
        spot_suggestions = [s for s in report.suggestions if s.action == "spot_instances"]
        assert len(spot_suggestions) > 0

    def test_downsize_suggested_for_low_util(self, overprovisioned_graph: InfraGraph):
        """Should suggest downsizing for very low utilization."""
        optimizer = CostOptimizer(overprovisioned_graph, min_resilience_score=50.0)
        report = optimizer.optimize()
        downsize_suggestions = [s for s in report.suggestions if s.action == "downsize"]
        assert len(downsize_suggestions) > 0

    def test_suggestion_has_description(self, overprovisioned_graph: InfraGraph):
        """Each suggestion should have a description."""
        optimizer = CostOptimizer(overprovisioned_graph, min_resilience_score=50.0)
        report = optimizer.optimize()
        for suggestion in report.suggestions:
            assert suggestion.description != ""
            assert suggestion.component_id != ""

    def test_risk_levels_valid(self, overprovisioned_graph: InfraGraph):
        """Risk levels should be one of safe, moderate, risky."""
        optimizer = CostOptimizer(overprovisioned_graph, min_resilience_score=50.0)
        report = optimizer.optimize()
        valid_risks = {"safe", "moderate", "risky"}
        for suggestion in report.suggestions:
            assert suggestion.risk_level in valid_risks


class TestCostOptimizerRiskLevel:
    """Test risk level classification."""

    def test_high_min_score_makes_more_risky(self, overprovisioned_graph: InfraGraph):
        """Higher min_resilience_score should produce more moderate/risky ratings."""
        optimizer_low = CostOptimizer(overprovisioned_graph, min_resilience_score=30.0)
        optimizer_high = CostOptimizer(overprovisioned_graph, min_resilience_score=95.0)

        report_low = optimizer_low.optimize()
        report_high = optimizer_high.optimize()

        safe_low = sum(1 for s in report_low.suggestions if s.risk_level == "safe")
        safe_high = sum(1 for s in report_high.suggestions if s.risk_level == "safe")

        # Higher threshold should have fewer safe suggestions
        assert safe_high <= safe_low

    def test_safe_suggestions_preserve_resilience(self, overprovisioned_graph: InfraGraph):
        """Safe suggestions should maintain resilience above minimum."""
        min_score = 50.0
        optimizer = CostOptimizer(overprovisioned_graph, min_resilience_score=min_score)
        report = optimizer.optimize()
        assert report.resilience_after >= min_score


class TestCostOptimizerPareto:
    """Test Pareto frontier generation."""

    def test_pareto_frontier_generated(self, overprovisioned_graph: InfraGraph):
        """Should generate a Pareto frontier."""
        optimizer = CostOptimizer(overprovisioned_graph, min_resilience_score=50.0)
        report = optimizer.optimize()
        assert len(report.pareto_frontier) > 0

    def test_pareto_points_have_cost_and_resilience(self, overprovisioned_graph: InfraGraph):
        """Each Pareto point should have cost and resilience."""
        optimizer = CostOptimizer(overprovisioned_graph, min_resilience_score=50.0)
        report = optimizer.optimize()
        for point in report.pareto_frontier:
            assert "cost" in point
            assert "resilience" in point
            assert point["cost"] >= 0
            assert point["resilience"] >= 0

    def test_pareto_sorted_by_cost(self, overprovisioned_graph: InfraGraph):
        """Pareto frontier should be sorted by cost ascending."""
        optimizer = CostOptimizer(overprovisioned_graph, min_resilience_score=50.0)
        report = optimizer.optimize()
        costs = [p["cost"] for p in report.pareto_frontier]
        assert costs == sorted(costs)

    def test_pareto_analysis_standalone(self, medium_graph: InfraGraph):
        """pareto_analysis() should work independently."""
        optimizer = CostOptimizer(medium_graph, min_resilience_score=50.0)
        frontier = optimizer.pareto_analysis(budget_steps=5)
        assert len(frontier) > 0
        assert len(frontier) <= 7  # steps + possible first/last


class TestCostOptimizerSavingsPercent:
    """Test savings percentage calculation."""

    def test_savings_percent_positive(self, overprovisioned_graph: InfraGraph):
        """Overprovisioned graph should have positive savings percent."""
        optimizer = CostOptimizer(overprovisioned_graph, min_resilience_score=50.0)
        report = optimizer.optimize()
        # Should have some safe savings
        if report.total_savings_monthly > 0:
            assert report.savings_percent > 0

    def test_savings_percent_bounded(self, overprovisioned_graph: InfraGraph):
        """Savings percent should be between 0 and 100."""
        optimizer = CostOptimizer(overprovisioned_graph, min_resilience_score=50.0)
        report = optimizer.optimize()
        assert 0 <= report.savings_percent <= 100


class TestCostOptimizerEdgeCases:
    """Test edge cases."""

    def test_empty_graph(self):
        """Should handle empty graph."""
        graph = InfraGraph()
        optimizer = CostOptimizer(graph, min_resilience_score=50.0)
        report = optimizer.optimize()
        assert report.current_monthly_cost == 0
        assert len(report.suggestions) == 0

    def test_single_component(self):
        """Should handle single component."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER, replicas=3,
            metrics=ResourceMetrics(cpu_percent=5.0),
        ))
        optimizer = CostOptimizer(graph, min_resilience_score=0.0)
        report = optimizer.optimize()
        assert report.current_monthly_cost > 0

    def test_suggestions_sorted_by_savings(self, overprovisioned_graph: InfraGraph):
        """Suggestions should be sorted by savings (highest first)."""
        optimizer = CostOptimizer(overprovisioned_graph, min_resilience_score=50.0)
        report = optimizer.optimize()
        if len(report.suggestions) > 1:
            savings = [s.savings_monthly for s in report.suggestions]
            assert savings == sorted(savings, reverse=True)
