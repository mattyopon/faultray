"""Tests for capacity planning engine."""

from __future__ import annotations

import pytest

from infrasim.model.components import Component, ComponentType, HealthStatus
from infrasim.model.graph import InfraGraph
from infrasim.simulator.capacity_planner import (
    CapacityForecast,
    CapacityPlan,
    CapacityPlanner,
    CapacityRisk,
    GrowthModel,
    ScalingEvent,
    _classify_risk,
    _days_to_threshold,
    _identify_bottleneck,
    _project_utilization,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(
    cid: str,
    name: str,
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    cpu: float = 30.0,
    mem: float = 30.0,
    disk: float = 0.0,
    connections: int = 0,
    max_conn: int = 1000,
    autoscale: bool = False,
) -> Component:
    c = Component(id=cid, name=name, type=ctype, replicas=replicas)
    c.metrics.cpu_percent = cpu
    c.metrics.memory_percent = mem
    c.metrics.disk_percent = disk
    c.metrics.network_connections = connections
    c.capacity.max_connections = max_conn
    if autoscale:
        c.autoscaling.enabled = True
        c.autoscaling.min_replicas = replicas
        c.autoscaling.max_replicas = replicas * 3
    return c


def _simple_infra() -> InfraGraph:
    g = InfraGraph()
    g.add_component(_comp("lb", "Load Balancer", ComponentType.LOAD_BALANCER, replicas=2, cpu=40.0))
    g.add_component(_comp("api", "API Server", replicas=3, cpu=55.0, mem=60.0))
    g.add_component(_comp("db", "Database", ComponentType.DATABASE, cpu=75.0, mem=70.0))
    from infrasim.model.components import Dependency
    g.add_dependency(Dependency(source_id="lb", target_id="api"))
    g.add_dependency(Dependency(source_id="api", target_id="db"))
    return g


# ---------------------------------------------------------------------------
# Tests: _project_utilization
# ---------------------------------------------------------------------------


class TestProjectUtilization:
    def test_linear(self):
        result = _project_utilization(50, 10, 1.0, GrowthModel.LINEAR)
        assert result == 60.0

    def test_exponential(self):
        result = _project_utilization(50, 30, 5.0, GrowthModel.EXPONENTIAL)
        assert result > 50  # Should grow

    def test_logarithmic(self):
        result = _project_utilization(50, 30, 5.0, GrowthModel.LOGARITHMIC)
        assert result > 50

    def test_plateau(self):
        result = _project_utilization(50, 100, 5.0, GrowthModel.PLATEAU)
        assert result > 50
        assert result <= 100

    def test_zero_days(self):
        result = _project_utilization(50, 0, 5.0, GrowthModel.LINEAR)
        assert result == 50

    def test_logarithmic_zero_days(self):
        result = _project_utilization(50, 0, 5.0, GrowthModel.LOGARITHMIC)
        assert result == 50


# ---------------------------------------------------------------------------
# Tests: _days_to_threshold
# ---------------------------------------------------------------------------


class TestDaysToThreshold:
    def test_already_exceeded(self):
        days = _days_to_threshold(90, 80, 1.0, GrowthModel.LINEAR)
        assert days == 0

    def test_linear_growth(self):
        days = _days_to_threshold(50, 80, 1.0, GrowthModel.LINEAR)
        assert days == 30

    def test_no_growth(self):
        days = _days_to_threshold(50, 80, 0, GrowthModel.LINEAR)
        assert days is None

    def test_negative_growth(self):
        days = _days_to_threshold(50, 80, -1.0, GrowthModel.LINEAR)
        assert days is None

    def test_beyond_max_days(self):
        days = _days_to_threshold(10, 99, 0.01, GrowthModel.LINEAR, max_days=100)
        assert days is None


# ---------------------------------------------------------------------------
# Tests: _identify_bottleneck
# ---------------------------------------------------------------------------


class TestIdentifyBottleneck:
    def test_cpu_bottleneck(self):
        c = _comp("x", "X", cpu=90.0, mem=30.0)
        assert _identify_bottleneck(c) == "cpu"

    def test_memory_bottleneck(self):
        c = _comp("x", "X", cpu=30.0, mem=90.0)
        assert _identify_bottleneck(c) == "memory"

    def test_disk_bottleneck(self):
        c = _comp("x", "X", cpu=10.0, mem=10.0, disk=90.0)
        assert _identify_bottleneck(c) == "disk"

    def test_connection_bottleneck(self):
        c = _comp("x", "X", cpu=10.0, mem=10.0, connections=900, max_conn=1000)
        assert _identify_bottleneck(c) == "connections"


# ---------------------------------------------------------------------------
# Tests: _classify_risk
# ---------------------------------------------------------------------------


class TestClassifyRisk:
    def test_exceeded(self):
        assert _classify_risk(96, None) == CapacityRisk.EXCEEDED

    def test_critical_high_util(self):
        assert _classify_risk(88, None) == CapacityRisk.CRITICAL

    def test_critical_days(self):
        assert _classify_risk(60, 5) == CapacityRisk.CRITICAL

    def test_warning_util(self):
        assert _classify_risk(72, None) == CapacityRisk.WARNING

    def test_warning_days(self):
        assert _classify_risk(40, 25) == CapacityRisk.WARNING

    def test_watch(self):
        assert _classify_risk(55, 80) == CapacityRisk.WATCH

    def test_safe(self):
        assert _classify_risk(30, None) == CapacityRisk.SAFE


# ---------------------------------------------------------------------------
# Tests: CapacityPlanner.plan
# ---------------------------------------------------------------------------


class TestPlan:
    def test_empty_graph(self):
        planner = CapacityPlanner()
        g = InfraGraph()
        plan = planner.plan(g)
        assert plan.overall_risk == CapacityRisk.SAFE
        assert len(plan.forecasts) == 0
        assert plan.days_to_first_bottleneck is None

    def test_simple_infra(self):
        planner = CapacityPlanner(growth_rate_percent=5.0)
        g = _simple_infra()
        plan = planner.plan(g)
        assert len(plan.forecasts) == 3
        assert plan.growth_model == GrowthModel.LINEAR
        assert plan.growth_rate_percent == 5.0

    def test_high_growth_triggers_events(self):
        planner = CapacityPlanner(growth_rate_percent=20.0)
        g = _simple_infra()
        plan = planner.plan(g)
        # High util DB with 20% monthly growth should trigger scaling
        db_forecast = next(f for f in plan.forecasts if f.component_id == "db")
        assert db_forecast.risk in (CapacityRisk.WARNING, CapacityRisk.CRITICAL, CapacityRisk.EXCEEDED)

    def test_forecast_has_correct_fields(self):
        planner = CapacityPlanner()
        g = _simple_infra()
        plan = planner.plan(g)
        for fc in plan.forecasts:
            assert fc.component_id
            assert fc.component_name
            assert 0 <= fc.current_utilization <= 100
            assert 0 <= fc.current_headroom <= 100
            assert fc.recommended_replicas >= fc.current_replicas
            assert fc.bottleneck_resource in ("cpu", "memory", "disk", "connections")
            assert fc.cost_multiplier >= 0

    def test_plan_has_recommendations(self):
        planner = CapacityPlanner(growth_rate_percent=15.0)
        g = _simple_infra()
        plan = planner.plan(g)
        # With high growth, should have recommendations
        assert len(plan.recommendations) > 0

    def test_overall_risk_is_max(self):
        planner = CapacityPlanner(growth_rate_percent=10.0)
        g = _simple_infra()
        plan = planner.plan(g)
        risks = [f.risk for f in plan.forecasts]
        risk_order = [CapacityRisk.SAFE, CapacityRisk.WATCH, CapacityRisk.WARNING,
                      CapacityRisk.CRITICAL, CapacityRisk.EXCEEDED]
        max_risk = max(risks, key=lambda r: risk_order.index(r))
        assert plan.overall_risk == max_risk


# ---------------------------------------------------------------------------
# Tests: forecast_component
# ---------------------------------------------------------------------------


class TestForecastComponent:
    def test_existing_component(self):
        planner = CapacityPlanner()
        g = _simple_infra()
        fc = planner.forecast_component(g, "db")
        assert fc is not None
        assert fc.component_name == "Database"

    def test_nonexistent_component(self):
        planner = CapacityPlanner()
        g = _simple_infra()
        fc = planner.forecast_component(g, "nonexistent")
        assert fc is None

    def test_low_util_component(self):
        planner = CapacityPlanner(growth_rate_percent=2.0)
        g = InfraGraph()
        g.add_component(_comp("idle", "Idle Server", cpu=5.0, mem=5.0))
        fc = planner.forecast_component(g, "idle")
        assert fc is not None
        assert fc.risk == CapacityRisk.SAFE

    def test_high_util_component(self):
        planner = CapacityPlanner()
        g = InfraGraph()
        g.add_component(_comp("hot", "Hot Server", cpu=92.0, mem=88.0))
        fc = planner.forecast_component(g, "hot")
        assert fc is not None
        assert fc.risk in (CapacityRisk.CRITICAL, CapacityRisk.EXCEEDED)


# ---------------------------------------------------------------------------
# Tests: what_if_growth
# ---------------------------------------------------------------------------


class TestWhatIfGrowth:
    def test_higher_growth_worse_risk(self):
        planner = CapacityPlanner(growth_rate_percent=5.0)
        g = _simple_infra()
        plan_normal = planner.plan(g)
        plan_high = planner.what_if_growth(g, 30.0)

        # Higher growth should have at least as bad risk
        risk_order = [CapacityRisk.SAFE, CapacityRisk.WATCH, CapacityRisk.WARNING,
                      CapacityRisk.CRITICAL, CapacityRisk.EXCEEDED]
        assert risk_order.index(plan_high.overall_risk) >= risk_order.index(plan_normal.overall_risk)

    def test_zero_growth(self):
        planner = CapacityPlanner(growth_rate_percent=5.0)
        g = InfraGraph()
        g.add_component(_comp("api", "API", cpu=30.0))
        plan = planner.what_if_growth(g, 0.0)
        # No growth = safe
        fc = plan.forecasts[0]
        assert fc.days_to_100_percent is None

    def test_preserves_original_rate(self):
        planner = CapacityPlanner(growth_rate_percent=5.0)
        g = InfraGraph()
        g.add_component(_comp("api", "API"))
        planner.what_if_growth(g, 50.0)
        # Original rate should be preserved
        assert planner._growth_rate == 5.0


# ---------------------------------------------------------------------------
# Tests: Growth models
# ---------------------------------------------------------------------------


class TestGrowthModels:
    @pytest.mark.parametrize("model", list(GrowthModel))
    def test_each_model(self, model):
        planner = CapacityPlanner(growth_model=model, growth_rate_percent=10.0)
        g = _simple_infra()
        plan = planner.plan(g)
        assert plan.growth_model == model
        assert len(plan.forecasts) == 3


# ---------------------------------------------------------------------------
# Tests: Autoscaling
# ---------------------------------------------------------------------------


class TestAutoscaling:
    def test_autoscale_component(self):
        planner = CapacityPlanner()
        g = InfraGraph()
        g.add_component(_comp("api", "API", replicas=2, cpu=60.0, autoscale=True))
        fc = planner.forecast_component(g, "api")
        assert fc is not None
        assert fc.recommended_replicas >= 2  # At least min_replicas


# ---------------------------------------------------------------------------
# Tests: Scaling events
# ---------------------------------------------------------------------------


class TestScalingEvents:
    def test_no_events_for_safe(self):
        planner = CapacityPlanner(growth_rate_percent=1.0)
        g = InfraGraph()
        g.add_component(_comp("idle", "Idle", cpu=10.0))
        plan = planner.plan(g)
        assert len(plan.scaling_events) == 0

    def test_critical_immediate_event(self):
        planner = CapacityPlanner(growth_rate_percent=10.0)
        g = InfraGraph()
        g.add_component(_comp("hot", "Hot Server", cpu=92.0, mem=90.0))
        plan = planner.plan(g)
        immediate = [e for e in plan.scaling_events if e.day == 0]
        assert len(immediate) >= 1

    def test_event_attributes(self):
        planner = CapacityPlanner(growth_rate_percent=10.0)
        g = InfraGraph()
        g.add_component(_comp("hot", "Hot", cpu=90.0))
        plan = planner.plan(g)
        for event in plan.scaling_events:
            assert event.component_id
            assert event.component_name
            assert event.action in ("scale_up", "scale_out")
            assert event.to_replicas >= event.from_replicas
            assert event.reason
            assert event.estimated_cost_impact


# ---------------------------------------------------------------------------
# Tests: Enum values
# ---------------------------------------------------------------------------


class TestEnums:
    def test_growth_model_values(self):
        assert GrowthModel.LINEAR.value == "linear"
        assert GrowthModel.EXPONENTIAL.value == "exponential"
        assert GrowthModel.LOGARITHMIC.value == "logarithmic"
        assert GrowthModel.PLATEAU.value == "plateau"

    def test_capacity_risk_values(self):
        assert CapacityRisk.SAFE.value == "safe"
        assert CapacityRisk.WATCH.value == "watch"
        assert CapacityRisk.WARNING.value == "warning"
        assert CapacityRisk.CRITICAL.value == "critical"
        assert CapacityRisk.EXCEEDED.value == "exceeded"


# ---------------------------------------------------------------------------
# Tests: Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_single_component(self):
        planner = CapacityPlanner()
        g = InfraGraph()
        g.add_component(_comp("solo", "Solo"))
        plan = planner.plan(g)
        assert len(plan.forecasts) == 1

    def test_all_component_types(self):
        planner = CapacityPlanner(growth_rate_percent=5.0)
        g = InfraGraph()
        for ct in ComponentType:
            g.add_component(_comp(ct.value, ct.value, ct, cpu=50.0))
        plan = planner.plan(g)
        assert len(plan.forecasts) == len(ComponentType)

    def test_zero_utilization(self):
        planner = CapacityPlanner()
        g = InfraGraph()
        g.add_component(_comp("empty", "Empty", cpu=0.0, mem=0.0))
        fc = planner.forecast_component(g, "empty")
        assert fc is not None
        assert fc.current_utilization == 0.0
        assert fc.current_headroom == 100.0

    def test_max_utilization(self):
        planner = CapacityPlanner()
        g = InfraGraph()
        g.add_component(_comp("full", "Full", cpu=100.0, mem=100.0))
        fc = planner.forecast_component(g, "full")
        assert fc is not None
        assert fc.risk in (CapacityRisk.CRITICAL, CapacityRisk.EXCEEDED)
        assert fc.days_to_100_percent == 0

    def test_custom_horizon(self):
        planner = CapacityPlanner(planning_horizon_days=30)
        g = _simple_infra()
        plan = planner.plan(g)
        assert plan.planning_horizon_days == 30

    def test_events_sorted_by_day(self):
        planner = CapacityPlanner(growth_rate_percent=15.0)
        g = _simple_infra()
        plan = planner.plan(g)
        if len(plan.scaling_events) > 1:
            for i in range(len(plan.scaling_events) - 1):
                assert plan.scaling_events[i].day <= plan.scaling_events[i + 1].day
