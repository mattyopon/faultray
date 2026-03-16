"""Tests for resource optimizer."""

from __future__ import annotations

import pytest

from faultray.model.components import Component, ComponentType, Dependency, HealthStatus
from faultray.model.graph import InfraGraph
from faultray.simulator.resource_optimizer import (
    OptimizationReport,
    OptimizationType,
    Priority,
    Recommendation,
    ResourceOptimizer,
    ResourceUsage,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(
    cid: str,
    name: str,
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
) -> Component:
    return Component(id=cid, name=name, type=ctype, replicas=replicas)


def _infra_with_variety() -> InfraGraph:
    g = InfraGraph()
    g.add_component(_comp("api", "API Server", replicas=4))
    g.add_component(_comp("db", "Database", ComponentType.DATABASE, replicas=3))
    g.add_component(_comp("cache", "Cache", ComponentType.CACHE, replicas=2))
    g.add_component(_comp("queue", "Queue", ComponentType.QUEUE, replicas=1))
    g.add_dependency(Dependency(source_id="api", target_id="db"))
    g.add_dependency(Dependency(source_id="api", target_id="cache"))
    g.add_dependency(Dependency(source_id="api", target_id="queue"))
    return g


# ---------------------------------------------------------------------------
# Tests: Enums
# ---------------------------------------------------------------------------


class TestEnums:
    def test_optimization_types(self):
        assert OptimizationType.SCALE_DOWN.value == "scale_down"
        assert OptimizationType.DECOMMISSION.value == "decommission"

    def test_priority_values(self):
        assert Priority.CRITICAL.value == "critical"
        assert Priority.LOW.value == "low"


# ---------------------------------------------------------------------------
# Tests: analyze — empty graph
# ---------------------------------------------------------------------------


class TestEmptyGraph:
    def test_empty_report(self):
        opt = ResourceOptimizer()
        g = InfraGraph()
        report = opt.analyze(g)
        assert report.total_monthly_cost == 0
        assert report.optimization_score == 100.0
        assert len(report.resource_usages) == 0
        assert len(report.recommendations) == 0


# ---------------------------------------------------------------------------
# Tests: ResourceUsage
# ---------------------------------------------------------------------------


class TestResourceUsage:
    def test_get_usage(self):
        opt = ResourceOptimizer()
        g = InfraGraph()
        g.add_component(_comp("api", "API", replicas=2))
        usage = opt.get_usage(g, "api")
        assert usage is not None
        assert usage.component_id == "api"
        assert usage.replicas == 2

    def test_get_usage_nonexistent(self):
        opt = ResourceOptimizer()
        g = InfraGraph()
        assert opt.get_usage(g, "nope") is None

    def test_usage_has_type(self):
        opt = ResourceOptimizer()
        g = InfraGraph()
        g.add_component(_comp("db", "DB", ComponentType.DATABASE))
        usage = opt.get_usage(g, "db")
        assert usage is not None
        assert usage.component_type == "database"

    def test_usage_utilization(self):
        opt = ResourceOptimizer()
        g = InfraGraph()
        g.add_component(_comp("api", "API"))
        usage = opt.get_usage(g, "api")
        assert usage is not None
        assert usage.utilization_percent >= 0

    def test_usage_cost_estimate(self):
        opt = ResourceOptimizer()
        g = InfraGraph()
        g.add_component(_comp("api", "API", replicas=2))
        usage = opt.get_usage(g, "api")
        assert usage is not None
        assert usage.estimated_monthly_cost > 0

    def test_over_provisioned_detection(self):
        opt = ResourceOptimizer(over_threshold=30.0)
        g = InfraGraph()
        c = _comp("api", "API", replicas=5)
        # Default utilization is low → over-provisioned with 5 replicas
        g.add_component(c)
        usage = opt.get_usage(g, "api")
        assert usage is not None
        assert usage.is_over_provisioned is True

    def test_single_replica_not_over_provisioned(self):
        opt = ResourceOptimizer()
        g = InfraGraph()
        g.add_component(_comp("api", "API", replicas=1))
        usage = opt.get_usage(g, "api")
        assert usage is not None
        assert usage.is_over_provisioned is False

    def test_autoscaling_flag(self):
        opt = ResourceOptimizer()
        g = InfraGraph()
        c = _comp("api", "API")
        g.add_component(c)
        usage = opt.get_usage(g, "api")
        assert usage is not None
        assert usage.has_autoscaling is False

    def test_autoscaling_enabled(self):
        opt = ResourceOptimizer()
        g = InfraGraph()
        c = _comp("api", "API")
        c.autoscaling.enabled = True
        g.add_component(c)
        usage = opt.get_usage(g, "api")
        assert usage is not None
        assert usage.has_autoscaling is True


# ---------------------------------------------------------------------------
# Tests: analyze — full report
# ---------------------------------------------------------------------------


class TestAnalyze:
    def test_report_has_usages(self):
        opt = ResourceOptimizer()
        g = _infra_with_variety()
        report = opt.analyze(g)
        assert len(report.resource_usages) == 4

    def test_report_total_cost(self):
        opt = ResourceOptimizer()
        g = _infra_with_variety()
        report = opt.analyze(g)
        assert report.total_monthly_cost > 0

    def test_report_optimization_score(self):
        opt = ResourceOptimizer()
        g = _infra_with_variety()
        report = opt.analyze(g)
        assert 0 <= report.optimization_score <= 100

    def test_sorted_by_savings(self):
        opt = ResourceOptimizer()
        g = _infra_with_variety()
        report = opt.analyze(g)
        if len(report.recommendations) >= 2:
            for i in range(len(report.recommendations) - 1):
                assert (
                    report.recommendations[i].estimated_monthly_savings
                    >= report.recommendations[i + 1].estimated_monthly_savings
                )

    def test_over_under_idle_counts(self):
        opt = ResourceOptimizer()
        g = _infra_with_variety()
        report = opt.analyze(g)
        assert isinstance(report.over_provisioned_count, int)
        assert isinstance(report.under_provisioned_count, int)
        assert isinstance(report.idle_count, int)


# ---------------------------------------------------------------------------
# Tests: Recommendations
# ---------------------------------------------------------------------------


class TestRecommendations:
    def test_scale_down_for_over_provisioned(self):
        # idle_threshold=0 ensures the component isn't classified as idle first
        opt = ResourceOptimizer(over_threshold=50.0, idle_threshold=0.0)
        g = InfraGraph()
        g.add_component(_comp("api", "API", replicas=10))
        report = opt.analyze(g)
        scale_down = [r for r in report.recommendations if r.optimization_type == OptimizationType.SCALE_DOWN]
        assert len(scale_down) >= 1

    def test_decommission_idle_no_dependents(self):
        opt = ResourceOptimizer(idle_threshold=100.0)  # everything is idle
        g = InfraGraph()
        g.add_component(_comp("orphan", "Orphan Service"))
        report = opt.analyze(g)
        decom = [r for r in report.recommendations if r.optimization_type == OptimizationType.DECOMMISSION]
        assert len(decom) >= 1

    def test_autoscaling_recommendation(self):
        opt = ResourceOptimizer()
        g = InfraGraph()
        c = _comp("api", "API", replicas=3)
        # No autoscaling, multiple replicas
        g.add_component(c)
        report = opt.analyze(g)
        auto_recs = [r for r in report.recommendations if r.optimization_type == OptimizationType.ADD_AUTOSCALING]
        assert len(auto_recs) >= 1

    def test_no_autoscaling_rec_when_enabled(self):
        opt = ResourceOptimizer()
        g = InfraGraph()
        c = _comp("api", "API", replicas=3)
        c.autoscaling.enabled = True
        g.add_component(c)
        report = opt.analyze(g)
        auto_recs = [r for r in report.recommendations if r.optimization_type == OptimizationType.ADD_AUTOSCALING]
        assert len(auto_recs) == 0

    def test_recommendation_fields(self):
        opt = ResourceOptimizer(over_threshold=50.0)
        g = InfraGraph()
        g.add_component(_comp("api", "API", replicas=5))
        report = opt.analyze(g)
        if report.recommendations:
            rec = report.recommendations[0]
            assert rec.component_id
            assert rec.component_name
            assert rec.description
            assert rec.risk_level in ("low", "medium", "high")
            assert rec.implementation_effort in ("trivial", "easy", "moderate", "complex")


# ---------------------------------------------------------------------------
# Tests: Custom thresholds
# ---------------------------------------------------------------------------


class TestCustomThresholds:
    def test_custom_over_threshold(self):
        opt = ResourceOptimizer(over_threshold=10.0)
        g = InfraGraph()
        g.add_component(_comp("api", "API", replicas=2))
        usage = opt.get_usage(g, "api")
        assert usage is not None
        # With very low threshold, might be over-provisioned

    def test_custom_idle_threshold(self):
        opt = ResourceOptimizer(idle_threshold=50.0)
        g = InfraGraph()
        g.add_component(_comp("api", "API"))
        usage = opt.get_usage(g, "api")
        assert usage is not None
        # Default utilization is likely < 50%, so idle


# ---------------------------------------------------------------------------
# Tests: Savings calculations
# ---------------------------------------------------------------------------


class TestSavings:
    def test_potential_savings(self):
        opt = ResourceOptimizer()
        g = _infra_with_variety()
        report = opt.analyze(g)
        assert isinstance(report.potential_monthly_savings, float)

    def test_savings_percent(self):
        opt = ResourceOptimizer()
        g = _infra_with_variety()
        report = opt.analyze(g)
        assert isinstance(report.savings_percent, float)
        assert report.savings_percent >= 0

    def test_scale_down_savings_positive(self):
        opt = ResourceOptimizer(over_threshold=50.0)
        g = InfraGraph()
        g.add_component(_comp("api", "API", replicas=10))
        report = opt.analyze(g)
        scale_down = [r for r in report.recommendations if r.optimization_type == OptimizationType.SCALE_DOWN]
        if scale_down:
            assert scale_down[0].estimated_monthly_savings > 0


# ---------------------------------------------------------------------------
# Tests: Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_single_component(self):
        opt = ResourceOptimizer()
        g = InfraGraph()
        g.add_component(_comp("api", "API"))
        report = opt.analyze(g)
        assert len(report.resource_usages) == 1

    def test_external_api_zero_cost(self):
        opt = ResourceOptimizer()
        g = InfraGraph()
        g.add_component(_comp("ext", "Stripe", ComponentType.EXTERNAL_API))
        usage = opt.get_usage(g, "ext")
        assert usage is not None
        assert usage.estimated_monthly_cost == 0

    def test_all_component_types(self):
        opt = ResourceOptimizer()
        g = InfraGraph()
        for ct in ComponentType:
            g.add_component(_comp(ct.value, ct.value.title(), ct))
        report = opt.analyze(g)
        assert len(report.resource_usages) == len(ComponentType)

    def test_custom_cost_profile(self):
        opt = ResourceOptimizer()
        g = InfraGraph()
        c = _comp("api", "API")
        c.cost_profile.hourly_infra_cost = 10.0  # $10/hr → $7200/month
        g.add_component(c)
        usage = opt.get_usage(g, "api")
        assert usage is not None
        assert usage.estimated_monthly_cost == 7200.0

    def test_get_usage_nonexistent_returns_none(self):
        """Test line 208: get_usage returns None for missing component (already tested but explicit)."""
        opt = ResourceOptimizer()
        g = InfraGraph()
        result = opt.get_usage(g, "nonexistent")
        assert result is None

    def test_under_provisioned_scale_up(self):
        """Test lines 258-261: under-provisioned generates SCALE_UP recommendation."""
        opt = ResourceOptimizer(under_threshold=5.0)  # very low threshold
        g = InfraGraph()
        from faultray.model.components import Capacity, ResourceMetrics
        c = _comp("hot", "Hot Server", replicas=2)
        c.capacity = Capacity(max_connections=100)
        c.metrics = ResourceMetrics(cpu_percent=95, memory_percent=90, network_connections=90)
        g.add_component(c)
        report = opt.analyze(g)
        scale_up = [r for r in report.recommendations if r.optimization_type == OptimizationType.SCALE_UP]
        assert len(scale_up) >= 1
        for rec in scale_up:
            assert rec.priority == Priority.HIGH
            assert rec.estimated_monthly_savings < 0  # cost increase, negative savings

    def test_idle_with_dependents_scale_down(self):
        """Test lines 227-238: idle component with dependents gets SCALE_DOWN not DECOMMISSION."""
        opt = ResourceOptimizer(idle_threshold=100.0)  # everything is idle
        g = InfraGraph()
        g.add_component(_comp("api", "API", replicas=2))
        g.add_component(_comp("db", "DB", ComponentType.DATABASE))
        g.add_dependency(Dependency(source_id="api", target_id="db"))
        report = opt.analyze(g)
        db_recs = [r for r in report.recommendations if r.component_id == "db"]
        # db has a dependent (api), so should get scale_down, not decommission
        scale_down = [r for r in db_recs if r.optimization_type == OptimizationType.SCALE_DOWN]
        decom = [r for r in db_recs if r.optimization_type == OptimizationType.DECOMMISSION]
        assert len(scale_down) >= 1
        assert len(decom) == 0

    def test_report_dataclass(self):
        report = OptimizationReport(
            resource_usages=[],
            recommendations=[],
            total_monthly_cost=0,
            potential_monthly_savings=0,
            savings_percent=0,
            over_provisioned_count=0,
            under_provisioned_count=0,
            idle_count=0,
            optimization_score=100.0,
        )
        assert report.optimization_score == 100.0

    def test_generate_recs_skips_none_component(self):
        """Test line 208: _generate_recommendations skips usage with nonexistent component_id."""
        opt = ResourceOptimizer()
        g = InfraGraph()
        # Create a fake usage for a component that doesn't exist in the graph
        fake_usage = ResourceUsage(
            component_id="ghost",
            component_name="Ghost",
            component_type="app_server",
            replicas=1,
            utilization_percent=50.0,
            estimated_monthly_cost=100.0,
            is_idle=False,
            is_over_provisioned=False,
            is_under_provisioned=False,
            has_autoscaling=False,
        )
        recs = opt._generate_recommendations(g, [fake_usage])
        # Should return empty list since the component doesn't exist
        assert recs == []
