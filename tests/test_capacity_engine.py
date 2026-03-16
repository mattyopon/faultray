"""Tests for capacity planning engine."""

import math

from faultray.model.components import (
    Capacity,
    Component,
    ComponentType,
    OperationalProfile,
    ResourceMetrics,
    SLOTarget,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.capacity_engine import CapacityPlanningEngine


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


def test_months_to_capacity_zero_utilization():
    """Zero current utilization should return inf (can't grow from zero)."""
    result = CapacityPlanningEngine._months_to_capacity(0.0, 0.10)
    assert math.isinf(result)


def test_forecast_with_simulation():
    """forecast_with_simulation should run ops simulation and return a report."""
    from faultray.model.components import FailoverConfig

    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        replicas=2,
        metrics=ResourceMetrics(cpu_percent=40, memory_percent=30),
        capacity=Capacity(max_connections=1000),
        operational_profile=OperationalProfile(mtbf_hours=720, mttr_minutes=15),
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE,
        replicas=2,
        metrics=ResourceMetrics(cpu_percent=50, memory_percent=40),
        capacity=Capacity(max_connections=200),
        operational_profile=OperationalProfile(mtbf_hours=2160, mttr_minutes=30),
        failover=FailoverConfig(enabled=True, promotion_time_seconds=10),
    ))
    graph.add_component(Component(
        id="lb", name="LB", type=ComponentType.LOAD_BALANCER,
        replicas=2,
        metrics=ResourceMetrics(cpu_percent=15),
        capacity=Capacity(max_connections=10000),
    ))
    from faultray.model.components import Dependency
    graph.add_dependency(Dependency(source_id="lb", target_id="app", dependency_type="requires"))
    graph.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))

    engine = CapacityPlanningEngine(graph)
    report = engine.forecast_with_simulation(
        monthly_growth_rate=0.05,
        slo_target=99.9,
        simulation_days=1,
    )
    assert len(report.forecasts) == 3
    assert report.error_budget is not None
    assert report.summary != ""


def test_get_component_utilization_low_reports_type_default():
    """When utilization < 10%, should use type-based default with replica adjustment."""
    graph = InfraGraph()
    # Single replica app_server with 0% utilization -> should use 45.0 + 10.0 = 55.0
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        replicas=1,
        metrics=ResourceMetrics(cpu_percent=0, memory_percent=0),
    ))
    engine = CapacityPlanningEngine(graph)
    comp = graph.get_component("app")
    util = engine._get_component_utilization(comp)
    assert util == 55.0  # 45.0 base + 10.0 single replica


def test_get_component_utilization_many_replicas():
    """When utilization < 10% and replicas >= 5, should reduce base by 5."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        replicas=5,
        metrics=ResourceMetrics(cpu_percent=0, memory_percent=0),
    ))
    engine = CapacityPlanningEngine(graph)
    comp = graph.get_component("app")
    util = engine._get_component_utilization(comp)
    assert util == 40.0  # 45.0 base - 5.0 for >= 5 replicas


def test_ha_min_replicas_for_lb():
    """Load balancer should have min 2 replicas even at low utilization."""
    from faultray.model.components import FailoverConfig

    graph = InfraGraph()
    graph.add_component(Component(
        id="lb", name="LB", type=ComponentType.LOAD_BALANCER,
        replicas=1,
        metrics=ResourceMetrics(cpu_percent=5),
    ))
    engine = CapacityPlanningEngine(graph)
    report = engine.forecast(monthly_growth_rate=0.0)
    fc = report.forecasts[0]
    # LB type → ha_min=2 so recommended should be >= 2
    assert fc.recommended_replicas_3m >= 2


def test_ha_min_replicas_for_cache_cluster():
    """Cache with 3+ replicas should have ha_min of 3 for quorum."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="cache", name="Redis Cluster", type=ComponentType.CACHE,
        replicas=3,
        metrics=ResourceMetrics(cpu_percent=15),
    ))
    engine = CapacityPlanningEngine(graph)
    report = engine.forecast(monthly_growth_rate=0.0)
    fc = report.forecasts[0]
    assert fc.recommended_replicas_3m >= 3


def test_replicas_needed_zero_utilization():
    """Zero utilization should return current replicas (no change)."""
    result = CapacityPlanningEngine._replicas_needed(
        current_replicas=3,
        current_util=0.0,
        growth_rate=0.10,
        months=12,
    )
    assert result == 3


def test_error_budget_exhausted_status():
    """Error budget should be 'exhausted' when consumed >= total."""
    eb = CapacityPlanningEngine._build_error_budget_forecast(
        slo_target=99.9,
        burn_rate_per_day=100.0,  # Very high burn rate
    )
    assert eb.status == "exhausted"


def test_error_budget_critical_status():
    """Error budget should be 'critical' when projected monthly > 100%."""
    # Total budget for 99.9% SLO = 43.2 min
    # If burn rate = 2.0 min/day, projected monthly = 2.0 * 30 / 43.2 * 100 = 138.9%
    eb = CapacityPlanningEngine._build_error_budget_forecast(
        slo_target=99.9,
        burn_rate_per_day=2.0,
    )
    assert eb.status == "critical"


def test_error_budget_warning_status():
    """Error budget should be 'warning' when projected monthly > 50%."""
    # Total budget for 99.9% SLO = 43.2 min
    # burn rate = 1.0 min/day -> projected = 1.0 * 30 / 43.2 * 100 = 69.4%
    eb = CapacityPlanningEngine._build_error_budget_forecast(
        slo_target=99.9,
        burn_rate_per_day=1.0,
    )
    assert eb.status == "warning"


def test_error_budget_zero_burn_rate():
    """Zero burn rate should give days_to_exhaustion=None and healthy status."""
    eb = CapacityPlanningEngine._build_error_budget_forecast(
        slo_target=99.9,
        burn_rate_per_day=0.0,
    )
    assert eb.days_to_exhaustion is None
    assert eb.status == "healthy"


def test_cost_increase_empty_forecasts():
    """Empty forecast list should return 0.0 cost increase."""
    result = CapacityPlanningEngine._estimate_cost_increase([])
    assert result == 0.0


def test_no_bottleneck_recommendations():
    """When recommended replicas match current and no error budget issue, all healthy."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        replicas=1,
        metrics=ResourceMetrics(cpu_percent=50),
    ))
    engine = CapacityPlanningEngine(graph)
    # Provide zero burn rate to avoid error budget warnings
    report = engine.forecast(monthly_growth_rate=0.0, slo_target=99.9, current_burn_rate=0.0)
    # With no urgency, no right-size, and healthy error budget, should produce the fallback
    assert any("healthy" in r.lower() or "headroom" in r.lower()
               for r in report.scaling_recommendations)


def test_warning_urgency_recommendation():
    """Warning urgency component should get planning recommendation."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        replicas=1,
        # 70% utilization + 10% growth -> months to capacity ~1.46 (warning)
        metrics=ResourceMetrics(cpu_percent=70),
    ))
    engine = CapacityPlanningEngine(graph)
    report = engine.forecast(monthly_growth_rate=0.10)
    warning_recs = [r for r in report.scaling_recommendations if "WARNING" in r]
    assert len(warning_recs) > 0
