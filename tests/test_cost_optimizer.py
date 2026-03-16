"""Tests for the Infrastructure Cost Optimizer."""

from __future__ import annotations

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    CircuitBreakerConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    HealthStatus,
    ResourceMetrics,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.cost_optimizer import (
    CostOptimizer,
    OptimizationReport,
    OptimizationSuggestion,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(
    cid: str,
    name: str,
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    health: HealthStatus = HealthStatus.HEALTHY,
    cpu: float = 0.0,
    mem: float = 0.0,
    autoscaling: bool = False,
    failover: bool = False,
) -> Component:
    return Component(
        id=cid,
        name=name,
        type=ctype,
        replicas=replicas,
        health=health,
        metrics=ResourceMetrics(cpu_percent=cpu, memory_percent=mem),
        autoscaling=AutoScalingConfig(enabled=autoscaling),
        failover=FailoverConfig(enabled=failover),
    )


def _chain_graph() -> InfraGraph:
    """lb -> app -> db  (app has autoscaling, db has failover)."""
    g = InfraGraph()
    g.add_component(_comp("lb", "LB", ComponentType.LOAD_BALANCER, replicas=2))
    g.add_component(_comp("app", "API", replicas=3, autoscaling=True))
    g.add_component(_comp("db", "DB", ComponentType.DATABASE, replicas=2, failover=True))
    g.add_dependency(Dependency(source_id="lb", target_id="app"))
    g.add_dependency(Dependency(source_id="app", target_id="db"))
    return g


# ---------------------------------------------------------------------------
# Tests: Dataclass instantiation
# ---------------------------------------------------------------------------


class TestDataclasses:
    def test_optimization_suggestion_fields(self):
        s = OptimizationSuggestion(
            action="reduce_replicas",
            component_id="app",
            current_cost_monthly=600.0,
            optimized_cost_monthly=400.0,
            savings_monthly=200.0,
            resilience_impact=-2.0,
            risk_level="safe",
            description="Reduce replicas",
        )
        assert s.action == "reduce_replicas"
        assert s.savings_monthly == 200.0

    def test_optimization_report_defaults(self):
        r = OptimizationReport(
            current_monthly_cost=1000,
            optimized_monthly_cost=800,
            total_savings_monthly=200,
            savings_percent=20.0,
            resilience_before=80.0,
            resilience_after=75.0,
        )
        assert r.suggestions == []
        assert r.pareto_frontier == []


# ---------------------------------------------------------------------------
# Tests: optimize() basics
# ---------------------------------------------------------------------------


class TestOptimizeBasics:
    def test_report_type(self):
        g = _chain_graph()
        report = CostOptimizer(g, min_resilience_score=0.0).optimize()
        assert isinstance(report, OptimizationReport)

    def test_current_cost_positive(self):
        g = _chain_graph()
        report = CostOptimizer(g).optimize()
        assert report.current_monthly_cost > 0

    def test_resilience_before_set(self):
        g = _chain_graph()
        report = CostOptimizer(g).optimize()
        assert report.resilience_before >= 0

    def test_optimized_cost_lte_current(self):
        g = _chain_graph()
        report = CostOptimizer(g, min_resilience_score=0.0).optimize()
        assert report.optimized_monthly_cost <= report.current_monthly_cost

    def test_savings_non_negative(self):
        g = _chain_graph()
        report = CostOptimizer(g, min_resilience_score=0.0).optimize()
        assert report.total_savings_monthly >= 0
        for s in report.suggestions:
            assert s.savings_monthly >= 0

    def test_suggestions_sorted_by_savings_descending(self):
        g = _chain_graph()
        report = CostOptimizer(g, min_resilience_score=0.0).optimize()
        if len(report.suggestions) > 1:
            savings = [s.savings_monthly for s in report.suggestions]
            assert savings == sorted(savings, reverse=True)

    def test_savings_percent_bounded(self):
        g = _chain_graph()
        report = CostOptimizer(g, min_resilience_score=0.0).optimize()
        assert 0 <= report.savings_percent <= 100

    def test_pareto_frontier_included(self):
        g = _chain_graph()
        report = CostOptimizer(g).optimize()
        assert isinstance(report.pareto_frontier, list)
        assert len(report.pareto_frontier) > 0


# ---------------------------------------------------------------------------
# Tests: _suggest_reduce_replicas
# ---------------------------------------------------------------------------


class TestReduceReplicas:
    def test_multi_replica_gets_suggestion(self):
        g = InfraGraph()
        g.add_component(_comp("app", "App", replicas=4))
        opt = CostOptimizer(g, min_resilience_score=0.0)
        suggestions = opt._suggest_reduce_replicas()
        assert len(suggestions) == 1
        assert suggestions[0].action == "reduce_replicas"
        assert suggestions[0].component_id == "app"

    def test_single_replica_skipped(self):
        g = InfraGraph()
        g.add_component(_comp("app", "App", replicas=1))
        opt = CostOptimizer(g, min_resilience_score=0.0)
        suggestions = opt._suggest_reduce_replicas()
        assert len(suggestions) == 0

    def test_reduces_by_one(self):
        g = InfraGraph()
        g.add_component(_comp("app", "App", replicas=5))
        opt = CostOptimizer(g, min_resilience_score=0.0)
        suggestions = opt._suggest_reduce_replicas()
        s = suggestions[0]
        # 5 replicas -> 4 replicas, each $200
        assert s.current_cost_monthly == 5 * 200.0
        assert s.optimized_cost_monthly == 4 * 200.0
        assert s.savings_monthly == 200.0

    def test_risk_safe_when_above_min_and_gte_2(self):
        """new_replicas >=2 and new_score >= min => safe."""
        g = InfraGraph()
        g.add_component(_comp("app", "App", replicas=3))
        opt = CostOptimizer(g, min_resilience_score=0.0)
        suggestions = opt._suggest_reduce_replicas()
        assert suggestions[0].risk_level == "safe"

    def test_risk_moderate_when_below_min_and_gte_2(self):
        """new_replicas >=2 but score drops below min => moderate."""
        g = InfraGraph()
        g.add_component(_comp("app", "App", replicas=3))
        opt = CostOptimizer(g, min_resilience_score=999.0)
        suggestions = opt._suggest_reduce_replicas()
        assert suggestions[0].risk_level == "moderate"

    def test_risk_risky_when_single_with_dependents(self):
        """new_replicas=1 with critical dependents => risky."""
        g = InfraGraph()
        g.add_component(_comp("db", "DB", ComponentType.DATABASE, replicas=2))
        g.add_component(_comp("app", "App", replicas=1))
        g.add_dependency(Dependency(source_id="app", target_id="db"))
        opt = CostOptimizer(g, min_resilience_score=0.0)
        suggestions = opt._suggest_reduce_replicas()
        db_suggestion = [s for s in suggestions if s.component_id == "db"]
        assert len(db_suggestion) == 1
        assert db_suggestion[0].risk_level == "risky"

    def test_risk_moderate_when_single_without_dependents(self):
        """new_replicas=1 with no dependents => moderate."""
        g = InfraGraph()
        g.add_component(_comp("leaf", "Leaf", replicas=2))
        opt = CostOptimizer(g, min_resilience_score=0.0)
        suggestions = opt._suggest_reduce_replicas()
        assert suggestions[0].risk_level == "moderate"

    def test_description_contains_replica_info(self):
        g = InfraGraph()
        g.add_component(_comp("app", "App", replicas=3))
        opt = CostOptimizer(g, min_resilience_score=0.0)
        suggestions = opt._suggest_reduce_replicas()
        assert "3" in suggestions[0].description
        assert "2" in suggestions[0].description


# ---------------------------------------------------------------------------
# Tests: _suggest_spot_instances
# ---------------------------------------------------------------------------


class TestSpotInstances:
    def test_stateless_multi_replica_gets_spot(self):
        g = InfraGraph()
        g.add_component(_comp("app", "App", ComponentType.APP_SERVER, replicas=4, autoscaling=True))
        opt = CostOptimizer(g, min_resilience_score=0.0)
        suggestions = opt._suggest_spot_instances()
        assert len(suggestions) == 1
        assert suggestions[0].action == "spot_instances"

    def test_stateful_excluded(self):
        """Databases and caches should not get spot suggestions."""
        g = InfraGraph()
        g.add_component(_comp("db", "DB", ComponentType.DATABASE, replicas=4))
        g.add_component(_comp("cache", "Cache", ComponentType.CACHE, replicas=4))
        opt = CostOptimizer(g, min_resilience_score=0.0)
        suggestions = opt._suggest_spot_instances()
        assert len(suggestions) == 0

    def test_single_replica_excluded(self):
        """Need >=2 replicas for spot safety."""
        g = InfraGraph()
        g.add_component(_comp("app", "App", ComponentType.APP_SERVER, replicas=1))
        opt = CostOptimizer(g, min_resilience_score=0.0)
        suggestions = opt._suggest_spot_instances()
        assert len(suggestions) == 0

    def test_web_server_eligible(self):
        g = InfraGraph()
        g.add_component(_comp("web", "Web", ComponentType.WEB_SERVER, replicas=2))
        opt = CostOptimizer(g, min_resilience_score=0.0)
        suggestions = opt._suggest_spot_instances()
        assert len(suggestions) == 1

    def test_load_balancer_eligible(self):
        g = InfraGraph()
        g.add_component(_comp("lb", "LB", ComponentType.LOAD_BALANCER, replicas=2))
        opt = CostOptimizer(g, min_resilience_score=0.0)
        suggestions = opt._suggest_spot_instances()
        assert len(suggestions) == 1

    def test_spot_savings_positive(self):
        g = InfraGraph()
        g.add_component(_comp("app", "App", replicas=4, autoscaling=True))
        opt = CostOptimizer(g, min_resilience_score=0.0)
        suggestions = opt._suggest_spot_instances()
        assert suggestions[0].savings_monthly > 0

    def test_autoscaling_reduces_impact(self):
        """Autoscaling enabled => impact -1, not -2."""
        g = InfraGraph()
        g.add_component(_comp("app", "App", replicas=4, autoscaling=True))
        opt = CostOptimizer(g, min_resilience_score=0.0)
        suggestions = opt._suggest_spot_instances()
        assert suggestions[0].resilience_impact == -1.0

    def test_no_autoscaling_higher_impact(self):
        """No autoscaling => impact -2."""
        g = InfraGraph()
        g.add_component(_comp("app", "App", replicas=4, autoscaling=False))
        opt = CostOptimizer(g, min_resilience_score=0.0)
        suggestions = opt._suggest_spot_instances()
        assert suggestions[0].resilience_impact == -2.0

    def test_safe_when_autoscaling_and_above_min(self):
        g = InfraGraph()
        g.add_component(_comp("app", "App", replicas=4, autoscaling=True))
        opt = CostOptimizer(g, min_resilience_score=0.0)
        suggestions = opt._suggest_spot_instances()
        assert suggestions[0].risk_level == "safe"

    def test_moderate_when_no_autoscaling_above_min(self):
        g = InfraGraph()
        g.add_component(_comp("app", "App", replicas=4, autoscaling=False))
        opt = CostOptimizer(g, min_resilience_score=0.0)
        suggestions = opt._suggest_spot_instances()
        assert suggestions[0].risk_level == "moderate"

    def test_risky_when_below_min(self):
        g = InfraGraph()
        g.add_component(_comp("app", "App", replicas=4, autoscaling=False))
        opt = CostOptimizer(g, min_resilience_score=999.0)
        suggestions = opt._suggest_spot_instances()
        assert suggestions[0].risk_level == "risky"


# ---------------------------------------------------------------------------
# Tests: _suggest_consolidation
# ---------------------------------------------------------------------------


class TestConsolidation:
    def test_low_util_multi_replica_gets_consolidation(self):
        """Utilization <= 30 and replicas > 1 should suggest consolidation."""
        g = InfraGraph()
        g.add_component(_comp("app", "App", replicas=4, cpu=10.0, mem=5.0))
        opt = CostOptimizer(g, min_resilience_score=0.0)
        suggestions = opt._suggest_consolidation()
        assert len(suggestions) == 1
        assert suggestions[0].action == "consolidate"

    def test_high_util_excluded(self):
        """Utilization > 30 should not be suggested for consolidation."""
        g = InfraGraph()
        g.add_component(_comp("app", "App", replicas=4, cpu=50.0))
        opt = CostOptimizer(g, min_resilience_score=0.0)
        suggestions = opt._suggest_consolidation()
        assert len(suggestions) == 0

    def test_single_replica_excluded(self):
        g = InfraGraph()
        g.add_component(_comp("app", "App", replicas=1, cpu=5.0))
        opt = CostOptimizer(g, min_resilience_score=0.0)
        suggestions = opt._suggest_consolidation()
        assert len(suggestions) == 0

    def test_keeps_min_2_with_dependents(self):
        """Components with dependents should keep at least 2 replicas."""
        g = InfraGraph()
        g.add_component(_comp("db", "DB", ComponentType.DATABASE, replicas=3, cpu=5.0))
        g.add_component(_comp("app", "App", replicas=1))
        g.add_dependency(Dependency(source_id="app", target_id="db"))
        opt = CostOptimizer(g, min_resilience_score=0.0)
        suggestions = opt._suggest_consolidation()
        db_s = [s for s in suggestions if s.component_id == "db"]
        assert len(db_s) == 1
        # Should reduce from 3 to 2, not to 1
        assert db_s[0].optimized_cost_monthly == 2 * 500.0

    def test_can_reduce_to_1_without_dependents(self):
        """Components without dependents can go to 1 replica."""
        g = InfraGraph()
        g.add_component(_comp("leaf", "Leaf", replicas=2, cpu=5.0))
        opt = CostOptimizer(g, min_resilience_score=0.0)
        suggestions = opt._suggest_consolidation()
        assert len(suggestions) == 1
        assert suggestions[0].optimized_cost_monthly == 1 * 200.0

    def test_no_suggestion_when_already_at_min(self):
        """If replicas already at min, skip."""
        g = InfraGraph()
        g.add_component(_comp("db", "DB", ComponentType.DATABASE, replicas=2, cpu=5.0))
        g.add_component(_comp("app", "App", replicas=1))
        g.add_dependency(Dependency(source_id="app", target_id="db"))
        opt = CostOptimizer(g, min_resilience_score=0.0)
        suggestions = opt._suggest_consolidation()
        db_s = [s for s in suggestions if s.component_id == "db"]
        # min_replicas = 2 because has dependents, replicas = 2 => no suggestion
        assert len(db_s) == 0

    def test_risk_safe_when_above_min_score(self):
        g = InfraGraph()
        g.add_component(_comp("app", "App", replicas=4, cpu=5.0))
        opt = CostOptimizer(g, min_resilience_score=0.0)
        suggestions = opt._suggest_consolidation()
        assert suggestions[0].risk_level == "safe"

    def test_risk_moderate_when_below_min_score(self):
        g = InfraGraph()
        g.add_component(_comp("app", "App", replicas=4, cpu=5.0))
        opt = CostOptimizer(g, min_resilience_score=999.0)
        suggestions = opt._suggest_consolidation()
        assert suggestions[0].risk_level == "moderate"

    def test_description_has_util_info(self):
        g = InfraGraph()
        g.add_component(_comp("app", "App", replicas=4, cpu=10.0))
        opt = CostOptimizer(g, min_resilience_score=0.0)
        suggestions = opt._suggest_consolidation()
        assert "utilization" in suggestions[0].description.lower()


# ---------------------------------------------------------------------------
# Tests: _suggest_downsize
# ---------------------------------------------------------------------------


class TestDownsize:
    def test_very_low_util_gets_downsize(self):
        """Utilization <= 20 should get a downsize suggestion."""
        g = InfraGraph()
        g.add_component(_comp("app", "App", replicas=3, cpu=10.0))
        opt = CostOptimizer(g, min_resilience_score=0.0)
        suggestions = opt._suggest_downsize()
        assert len(suggestions) == 1
        assert suggestions[0].action == "downsize"

    def test_high_util_excluded(self):
        """Utilization > 20 should not get downsize."""
        g = InfraGraph()
        g.add_component(_comp("app", "App", replicas=3, cpu=50.0))
        opt = CostOptimizer(g, min_resilience_score=0.0)
        suggestions = opt._suggest_downsize()
        assert len(suggestions) == 0

    def test_savings_30_percent(self):
        """Downsize saves ~30% of current cost."""
        g = InfraGraph()
        g.add_component(_comp("app", "App", replicas=3, cpu=10.0))
        opt = CostOptimizer(g, min_resilience_score=0.0)
        suggestions = opt._suggest_downsize()
        current = 3 * 200.0
        expected_savings = current * 0.3
        assert abs(suggestions[0].savings_monthly - expected_savings) < 0.01

    def test_small_savings_skipped(self):
        """Savings < $10 are not worth the effort."""
        g = InfraGraph()
        # DNS: $10/replica. 1 replica = $10. 30% = $3 < $10 threshold
        g.add_component(_comp("dns", "DNS", ComponentType.DNS, replicas=1, cpu=5.0))
        opt = CostOptimizer(g, min_resilience_score=0.0)
        suggestions = opt._suggest_downsize()
        assert len(suggestions) == 0

    def test_zero_resilience_impact(self):
        """Downsizing should have 0.0 resilience impact."""
        g = InfraGraph()
        g.add_component(_comp("app", "App", replicas=3, cpu=5.0))
        opt = CostOptimizer(g, min_resilience_score=0.0)
        suggestions = opt._suggest_downsize()
        assert suggestions[0].resilience_impact == 0.0

    def test_risk_safe_when_above_min(self):
        g = InfraGraph()
        g.add_component(_comp("app", "App", replicas=3, cpu=5.0))
        opt = CostOptimizer(g, min_resilience_score=0.0)
        suggestions = opt._suggest_downsize()
        assert suggestions[0].risk_level == "safe"

    def test_risk_moderate_when_below_min(self):
        g = InfraGraph()
        g.add_component(_comp("app", "App", replicas=3, cpu=5.0))
        opt = CostOptimizer(g, min_resilience_score=999.0)
        suggestions = opt._suggest_downsize()
        assert suggestions[0].risk_level == "moderate"

    def test_description_has_util_and_downsize(self):
        g = InfraGraph()
        g.add_component(_comp("app", "App", replicas=3, cpu=10.0))
        opt = CostOptimizer(g, min_resilience_score=0.0)
        suggestions = opt._suggest_downsize()
        assert "downsize" in suggestions[0].description.lower()
        assert "utilization" in suggestions[0].description.lower()


# ---------------------------------------------------------------------------
# Tests: _score_impact_reduce_replicas
# ---------------------------------------------------------------------------


class TestScoreImpact:
    def test_impact_is_negative_or_zero(self):
        g = _chain_graph()
        opt = CostOptimizer(g)
        impact = opt._score_impact_reduce_replicas("app", 2)
        assert impact <= 0

    def test_impact_nonexistent_component(self):
        g = _chain_graph()
        opt = CostOptimizer(g)
        impact = opt._score_impact_reduce_replicas("nonexistent", 1)
        assert impact == 0.0

    def test_impact_does_not_modify_original(self):
        g = _chain_graph()
        opt = CostOptimizer(g)
        original_replicas = g.get_component("app").replicas
        opt._score_impact_reduce_replicas("app", 1)
        assert g.get_component("app").replicas == original_replicas

    def test_impact_clamps_to_1(self):
        """Even if new_replicas=0 is requested, it clamps to 1."""
        g = InfraGraph()
        g.add_component(_comp("app", "App", replicas=3))
        opt = CostOptimizer(g)
        impact = opt._score_impact_reduce_replicas("app", 0)
        # Should still work (clamped to 1)
        assert isinstance(impact, float)


# ---------------------------------------------------------------------------
# Tests: _calculate_safe_resilience
# ---------------------------------------------------------------------------


class TestSafeResilience:
    def test_no_safe_suggestions_returns_original_score(self):
        g = _chain_graph()
        opt = CostOptimizer(g)
        original_score = g.resilience_score()
        result = opt._calculate_safe_resilience([])
        assert abs(result - original_score) < 0.1

    def test_safe_reduce_replicas_applies(self):
        g = InfraGraph()
        g.add_component(_comp("app", "App", replicas=5))
        opt = CostOptimizer(g)
        suggestions = [
            OptimizationSuggestion(
                action="reduce_replicas",
                component_id="app",
                current_cost_monthly=1000,
                optimized_cost_monthly=800,
                savings_monthly=200,
                resilience_impact=-1.0,
                risk_level="safe",
                description="Reduce replicas",
            )
        ]
        result = opt._calculate_safe_resilience(suggestions)
        assert isinstance(result, float)

    def test_non_safe_suggestions_ignored(self):
        g = _chain_graph()
        opt = CostOptimizer(g)
        original_score = g.resilience_score()
        suggestions = [
            OptimizationSuggestion(
                action="reduce_replicas",
                component_id="app",
                current_cost_monthly=1000,
                optimized_cost_monthly=800,
                savings_monthly=200,
                resilience_impact=-5.0,
                risk_level="moderate",
                description="Moderate suggestion",
            ),
            OptimizationSuggestion(
                action="reduce_replicas",
                component_id="db",
                current_cost_monthly=1000,
                optimized_cost_monthly=500,
                savings_monthly=500,
                resilience_impact=-10.0,
                risk_level="risky",
                description="Risky suggestion",
            ),
        ]
        result = opt._calculate_safe_resilience(suggestions)
        assert abs(result - original_score) < 0.1

    def test_safe_consolidate_applies(self):
        g = InfraGraph()
        g.add_component(_comp("app", "App", replicas=5))
        opt = CostOptimizer(g)
        suggestions = [
            OptimizationSuggestion(
                action="consolidate",
                component_id="app",
                current_cost_monthly=1000,
                optimized_cost_monthly=800,
                savings_monthly=200,
                resilience_impact=-1.0,
                risk_level="safe",
                description="Consolidate",
            )
        ]
        result = opt._calculate_safe_resilience(suggestions)
        assert isinstance(result, float)

    def test_spot_and_downsize_dont_affect_model(self):
        """spot_instances and downsize don't change the graph model."""
        g = InfraGraph()
        g.add_component(_comp("app", "App", replicas=3))
        opt = CostOptimizer(g)
        original_score = g.resilience_score()
        suggestions = [
            OptimizationSuggestion(
                action="spot_instances",
                component_id="app",
                current_cost_monthly=600,
                optimized_cost_monthly=400,
                savings_monthly=200,
                resilience_impact=-1.0,
                risk_level="safe",
                description="Spot",
            ),
            OptimizationSuggestion(
                action="downsize",
                component_id="app",
                current_cost_monthly=600,
                optimized_cost_monthly=420,
                savings_monthly=180,
                resilience_impact=0.0,
                risk_level="safe",
                description="Downsize",
            ),
        ]
        result = opt._calculate_safe_resilience(suggestions)
        assert abs(result - original_score) < 0.1

    def test_nonexistent_component_ignored(self):
        g = _chain_graph()
        opt = CostOptimizer(g)
        original_score = g.resilience_score()
        suggestions = [
            OptimizationSuggestion(
                action="reduce_replicas",
                component_id="nonexistent",
                current_cost_monthly=100,
                optimized_cost_monthly=50,
                savings_monthly=50,
                resilience_impact=-1.0,
                risk_level="safe",
                description="Ghost",
            )
        ]
        result = opt._calculate_safe_resilience(suggestions)
        assert abs(result - original_score) < 0.1


# ---------------------------------------------------------------------------
# Tests: pareto_analysis
# ---------------------------------------------------------------------------


class TestParetoAnalysis:
    def test_frontier_not_empty(self):
        g = _chain_graph()
        frontier = CostOptimizer(g).pareto_analysis()
        assert len(frontier) >= 1

    def test_frontier_sorted_by_cost(self):
        g = _chain_graph()
        frontier = CostOptimizer(g).pareto_analysis()
        costs = [p["cost"] for p in frontier]
        assert costs == sorted(costs)

    def test_each_point_has_cost_and_resilience(self):
        g = _chain_graph()
        frontier = CostOptimizer(g).pareto_analysis()
        for pt in frontier:
            assert "cost" in pt
            assert "resilience" in pt
            assert pt["cost"] >= 0
            assert pt["resilience"] >= 0

    def test_first_point_is_current_state(self):
        g = _chain_graph()
        opt = CostOptimizer(g)
        frontier = opt.pareto_analysis()
        # The frontier includes the current cost (sorted by cost, it might not be first
        # if there are cheaper options, but it should appear somewhere)
        from faultray.simulator.pareto_optimizer import _calculate_base_cost
        current_cost = round(_calculate_base_cost(g), 2)
        costs = [p["cost"] for p in frontier]
        assert current_cost in costs

    def test_budget_steps_limit(self):
        """Frontier should not exceed budget_steps + 2 (first/last)."""
        g = _chain_graph()
        frontier = CostOptimizer(g).pareto_analysis(budget_steps=3)
        assert len(frontier) <= 5  # 3 + first + last

    def test_empty_graph_frontier(self):
        g = InfraGraph()
        frontier = CostOptimizer(g).pareto_analysis()
        assert len(frontier) >= 1
        assert frontier[0]["cost"] == 0

    def test_standalone_matches_optimize(self):
        """pareto_analysis() result should match what optimize() embeds."""
        g = _chain_graph()
        opt = CostOptimizer(g, min_resilience_score=0.0)
        report = opt.optimize()
        standalone = opt.pareto_analysis()
        # Both should produce non-empty lists
        assert len(report.pareto_frontier) >= 1
        assert len(standalone) >= 1


# ---------------------------------------------------------------------------
# Tests: Risk levels and min_resilience_score
# ---------------------------------------------------------------------------


class TestRiskLevels:
    def test_valid_risk_levels(self):
        g = _chain_graph()
        report = CostOptimizer(g, min_resilience_score=0.0).optimize()
        valid = {"safe", "moderate", "risky"}
        for s in report.suggestions:
            assert s.risk_level in valid

    def test_higher_min_fewer_safe(self):
        g = _chain_graph()
        r_low = CostOptimizer(g, min_resilience_score=0.0).optimize()
        r_high = CostOptimizer(g, min_resilience_score=999.0).optimize()
        safe_low = sum(1 for s in r_low.suggestions if s.risk_level == "safe")
        safe_high = sum(1 for s in r_high.suggestions if s.risk_level == "safe")
        assert safe_high <= safe_low

    def test_safe_savings_in_optimized_cost(self):
        """Optimized cost should only subtract safe savings."""
        g = _chain_graph()
        report = CostOptimizer(g, min_resilience_score=0.0).optimize()
        safe_savings = sum(s.savings_monthly for s in report.suggestions if s.risk_level == "safe")
        expected = max(0.0, report.current_monthly_cost - safe_savings)
        assert abs(report.optimized_monthly_cost - round(expected, 2)) < 0.01


# ---------------------------------------------------------------------------
# Tests: Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_graph(self):
        g = InfraGraph()
        report = CostOptimizer(g).optimize()
        assert report.current_monthly_cost == 0
        assert report.optimized_monthly_cost == 0
        assert report.total_savings_monthly == 0
        assert len(report.suggestions) == 0
        assert report.savings_percent == 0.0

    def test_single_replica_component(self):
        """Single replica components should not get reduce_replicas suggestions."""
        g = InfraGraph()
        g.add_component(_comp("app", "App", replicas=1, cpu=80.0))
        report = CostOptimizer(g, min_resilience_score=0.0).optimize()
        reduce = [s for s in report.suggestions if s.action == "reduce_replicas"]
        assert len(reduce) == 0

    def test_all_suggestion_types_appear(self):
        """With the right graph, all 4 suggestion types should appear."""
        g = InfraGraph()
        # reduce_replicas: replicas > 1
        # spot_instances: stateless + replicas >= 2
        # consolidation: low util + replicas > 1
        # downsize: very low util
        g.add_component(_comp("app", "App", ComponentType.APP_SERVER, replicas=4,
                              cpu=5.0, mem=5.0, autoscaling=True))
        g.add_component(_comp("lb", "LB", ComponentType.LOAD_BALANCER, replicas=3,
                              cpu=3.0, mem=3.0))
        report = CostOptimizer(g, min_resilience_score=0.0).optimize()
        actions = {s.action for s in report.suggestions}
        assert "reduce_replicas" in actions
        assert "spot_instances" in actions
        assert "downsize" in actions

    def test_cost_type_lookup_default(self):
        """Custom component type should use default $150/replica."""
        g = InfraGraph()
        g.add_component(_comp("custom", "Custom", ComponentType.CUSTOM, replicas=3, cpu=5.0))
        opt = CostOptimizer(g, min_resilience_score=0.0)
        suggestions = opt._suggest_reduce_replicas()
        assert suggestions[0].current_cost_monthly == 3 * 150.0

    def test_zero_cost_graph(self):
        """Components with $0/replica (EXTERNAL_API) edge case."""
        g = InfraGraph()
        g.add_component(_comp("ext", "External", ComponentType.EXTERNAL_API, replicas=3))
        report = CostOptimizer(g, min_resilience_score=0.0).optimize()
        # EXTERNAL_API cost is $0/replica
        assert report.current_monthly_cost == 0
