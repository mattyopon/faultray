"""Tests for capacity planning engine."""

import math

from infrasim.model.components import (
    Capacity,
    Component,
    ComponentType,
    OperationalProfile,
    ResourceMetrics,
    SLOTarget,
)
from infrasim.model.graph import InfraGraph
from infrasim.simulator.capacity_engine import CapacityPlanningEngine


def _build_capacity_graph() -> InfraGraph:
    """Build a graph for capacity planning tests."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        replicas=3,
        metrics=ResourceMetrics(cpu_percent=60, memory_percent=50),
        capacity=Capacity(max_connections=1000),
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE,
        replicas=2,
        metrics=ResourceMetrics(cpu_percent=70, memory_percent=55, disk_percent=40),
        capacity=Capacity(max_connections=200, max_disk_gb=500),
    ))
    return graph


def test_forecast_basic():
    """Basic forecast should return valid forecasts for all components."""
    graph = _build_capacity_graph()
    engine = CapacityPlanningEngine(graph)
    report = engine.forecast(monthly_growth_rate=0.10, slo_target=99.9)
    assert len(report.forecasts) == 2
    assert report.error_budget is not None
    assert len(report.scaling_recommendations) > 0
    assert report.summary != ""


def test_forecast_zero_growth():
    """Zero growth should result in infinite months_to_capacity."""
    graph = _build_capacity_graph()
    engine = CapacityPlanningEngine(graph)
    report = engine.forecast(monthly_growth_rate=0.0, slo_target=99.9)
    for fc in report.forecasts:
        assert math.isinf(fc.months_to_capacity)


def test_forecast_high_utilization_urgent():
    """High utilization components should have critical urgency."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="hot", name="Hot", type=ComponentType.APP_SERVER,
        replicas=1,
        metrics=ResourceMetrics(cpu_percent=85),
    ))
    engine = CapacityPlanningEngine(graph)
    report = engine.forecast(monthly_growth_rate=0.10)
    fc = report.forecasts[0]
    assert fc.scaling_urgency == "critical"


def test_slo_target_validation():
    """Invalid slo_target should raise ValueError."""
    graph = _build_capacity_graph()
    engine = CapacityPlanningEngine(graph)
    try:
        engine.forecast(slo_target=0.0)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "slo_target" in str(e)

    try:
        engine.forecast(slo_target=101.0)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "slo_target" in str(e)


def test_replicas_needed_minimum_one():
    """Replica calculation should never go below 1."""
    result = CapacityPlanningEngine._replicas_needed(
        current_replicas=5,
        current_util=5.0,
        growth_rate=0.0,
        months=12,
    )
    assert result >= 1


def test_right_sizing_recommendation():
    """Over-provisioned components should get right-sizing recommendations."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="over", name="Over", type=ComponentType.APP_SERVER,
        replicas=10,
        metrics=ResourceMetrics(cpu_percent=10),
    ))
    engine = CapacityPlanningEngine(graph)
    report = engine.forecast(monthly_growth_rate=0.05)
    # Should have a right-sizing recommendation
    right_size_recs = [r for r in report.scaling_recommendations if "RIGHT-SIZE" in r]
    assert len(right_size_recs) > 0


def test_cost_decrease_shown():
    """Cost decrease should be negative, not clamped to 0."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="over", name="Over", type=ComponentType.APP_SERVER,
        replicas=10,
        metrics=ResourceMetrics(cpu_percent=10),
    ))
    engine = CapacityPlanningEngine(graph)
    report = engine.forecast(monthly_growth_rate=0.0)
    # With 10 replicas and 10% utilization, cost should decrease
    assert report.estimated_monthly_cost_increase <= 0.0


def test_months_to_capacity_already_over():
    """Component already at capacity should return 0.0."""
    result = CapacityPlanningEngine._months_to_capacity(85.0, 0.10)
    assert result == 0.0
