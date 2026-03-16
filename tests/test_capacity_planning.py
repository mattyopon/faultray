"""Tests for capacity planning & saturation predictor."""

from __future__ import annotations

import math

import pytest

from faultray.model.components import Component, ComponentType, Dependency, HealthStatus
from faultray.model.graph import InfraGraph
from faultray.simulator.capacity_planning import (
    BottleneckResult,
    CapacityPlan,
    CapacityPlanningEngine,
    CostForecast,
    GrowthModel,
    RightSizeRecommendation,
    SaturationMetric,
    SaturationPrediction,
    ScalingStep,
    SeasonalLoadResult,
    TrafficSpikeResult,
    _best_growth_model,
    _confidence_for_prediction,
    _cost_of_inaction,
    _current_capacity_dict,
    _hours_to_saturation,
    _metric_value,
    _monthly_cost_delta,
    _project_value,
    _recommend_action,
    _recommended_capacity_dict,
    _risk_label,
    _severity_label,
    _slope_for_component,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(
    cid: str = "c1",
    name: str = "comp-1",
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    cpu: float = 50.0,
    mem: float = 40.0,
    disk: float = 20.0,
    connections: int = 200,
    max_conn: int = 1000,
    max_rps: int = 5000,
    autoscale: bool = False,
    hourly_cost: float = 0.0,
    mem_leak: float = 0.0,
    disk_fill: float = 0.0,
    conn_leak: float = 0.0,
) -> Component:
    c = Component(id=cid, name=name, type=ctype, replicas=replicas)
    c.metrics.cpu_percent = cpu
    c.metrics.memory_percent = mem
    c.metrics.disk_percent = disk
    c.metrics.network_connections = connections
    c.capacity.max_connections = max_conn
    c.capacity.max_rps = max_rps
    if autoscale:
        c.autoscaling.enabled = True
        c.autoscaling.min_replicas = replicas
        c.autoscaling.max_replicas = replicas * 3
    if hourly_cost > 0:
        c.cost_profile.hourly_infra_cost = hourly_cost
    if mem_leak > 0:
        c.operational_profile.degradation.memory_leak_mb_per_hour = mem_leak
    if disk_fill > 0:
        c.operational_profile.degradation.disk_fill_gb_per_hour = disk_fill
    if conn_leak > 0:
        c.operational_profile.degradation.connection_leak_per_hour = conn_leak
    return c


def _graph(*components: Component) -> InfraGraph:
    g = InfraGraph()
    for c in components:
        g.add_component(c)
    return g


# ---------------------------------------------------------------------------
# Tests: SaturationMetric enum
# ---------------------------------------------------------------------------


class TestSaturationMetricEnum:
    def test_cpu_value(self):
        assert SaturationMetric.CPU.value == "cpu"

    def test_memory_value(self):
        assert SaturationMetric.MEMORY.value == "memory"

    def test_disk_value(self):
        assert SaturationMetric.DISK.value == "disk"

    def test_network_value(self):
        assert SaturationMetric.NETWORK.value == "network"

    def test_connections_value(self):
        assert SaturationMetric.CONNECTIONS.value == "connections"

    def test_iops_value(self):
        assert SaturationMetric.IOPS.value == "iops"

    def test_bandwidth_value(self):
        assert SaturationMetric.BANDWIDTH.value == "bandwidth"

    def test_queue_depth_value(self):
        assert SaturationMetric.QUEUE_DEPTH.value == "queue_depth"

    def test_all_members_count(self):
        assert len(SaturationMetric) == 8


# ---------------------------------------------------------------------------
# Tests: GrowthModel enum
# ---------------------------------------------------------------------------


class TestGrowthModelEnum:
    def test_linear_value(self):
        assert GrowthModel.LINEAR.value == "linear"

    def test_exponential_value(self):
        assert GrowthModel.EXPONENTIAL.value == "exponential"

    def test_logarithmic_value(self):
        assert GrowthModel.LOGARITHMIC.value == "logarithmic"

    def test_polynomial_value(self):
        assert GrowthModel.POLYNOMIAL.value == "polynomial"

    def test_seasonal_value(self):
        assert GrowthModel.SEASONAL.value == "seasonal"

    def test_all_members_count(self):
        assert len(GrowthModel) == 5


# ---------------------------------------------------------------------------
# Tests: _metric_value
# ---------------------------------------------------------------------------


class TestMetricValue:
    def test_cpu(self):
        c = _comp(cpu=75.0)
        assert _metric_value(c, SaturationMetric.CPU) == 75.0

    def test_memory(self):
        c = _comp(mem=60.0)
        assert _metric_value(c, SaturationMetric.MEMORY) == 60.0

    def test_disk(self):
        c = _comp(disk=30.0)
        assert _metric_value(c, SaturationMetric.DISK) == 30.0

    def test_network(self):
        c = _comp(connections=500, max_conn=1000)
        assert _metric_value(c, SaturationMetric.NETWORK) == 50.0

    def test_connections(self):
        c = _comp(connections=500, max_conn=1000)
        assert _metric_value(c, SaturationMetric.CONNECTIONS) == 50.0

    def test_connections_cap_at_100(self):
        c = _comp(connections=2000, max_conn=1000)
        assert _metric_value(c, SaturationMetric.CONNECTIONS) == 100.0

    def test_iops_derived(self):
        c = _comp(disk=50.0)
        assert _metric_value(c, SaturationMetric.IOPS) == 40.0

    def test_bandwidth_derived(self):
        c = _comp(connections=500, max_conn=1000)
        result = _metric_value(c, SaturationMetric.BANDWIDTH)
        assert result == pytest.approx(35.0)

    def test_queue_depth_derived(self):
        c = _comp(cpu=80.0)
        assert _metric_value(c, SaturationMetric.QUEUE_DEPTH) == 40.0

    def test_zero_max_connections(self):
        c = _comp(connections=100, max_conn=0)
        c.capacity.max_connections = 0
        val = _metric_value(c, SaturationMetric.NETWORK)
        assert val == 100.0  # capped


# ---------------------------------------------------------------------------
# Tests: _project_value
# ---------------------------------------------------------------------------


class TestProjectValue:
    def test_linear_growth(self):
        assert _project_value(50.0, 10.0, 1.0, GrowthModel.LINEAR) == 60.0

    def test_linear_zero_hours(self):
        assert _project_value(50.0, 0.0, 1.0, GrowthModel.LINEAR) == 50.0

    def test_exponential_growth(self):
        result = _project_value(50.0, 100.0, 1.0, GrowthModel.EXPONENTIAL)
        assert result > 50.0

    def test_logarithmic_growth(self):
        result = _project_value(50.0, 100.0, 5.0, GrowthModel.LOGARITHMIC)
        assert result > 50.0

    def test_polynomial_growth(self):
        result = _project_value(50.0, 100.0, 1.0, GrowthModel.POLYNOMIAL)
        assert result > 50.0

    def test_seasonal_growth(self):
        result = _project_value(50.0, 84.0, 1.0, GrowthModel.SEASONAL)
        assert result != 50.0  # has seasonal component

    def test_negative_hours(self):
        assert _project_value(50.0, -5.0, 1.0, GrowthModel.LINEAR) == 50.0


# ---------------------------------------------------------------------------
# Tests: _hours_to_saturation
# ---------------------------------------------------------------------------


class TestHoursToSaturation:
    def test_linear_finite(self):
        hrs = _hours_to_saturation(50.0, 1.0, GrowthModel.LINEAR)
        assert hrs == 50.0

    def test_linear_already_saturated(self):
        assert _hours_to_saturation(100.0, 1.0, GrowthModel.LINEAR) == 0.0

    def test_linear_zero_slope(self):
        hrs = _hours_to_saturation(50.0, 0.0, GrowthModel.LINEAR)
        assert hrs == 8760.0

    def test_linear_negative_slope(self):
        hrs = _hours_to_saturation(50.0, -1.0, GrowthModel.LINEAR)
        assert hrs == 8760.0

    def test_exponential_finite(self):
        hrs = _hours_to_saturation(50.0, 1.0, GrowthModel.EXPONENTIAL)
        assert 0 < hrs < 8760

    def test_exponential_zero_current(self):
        hrs = _hours_to_saturation(0.0, 1.0, GrowthModel.EXPONENTIAL)
        assert hrs == 8760.0

    def test_logarithmic_numerical(self):
        hrs = _hours_to_saturation(50.0, 20.0, GrowthModel.LOGARITHMIC)
        assert 0 < hrs < 8760

    def test_polynomial_numerical(self):
        hrs = _hours_to_saturation(50.0, 1.0, GrowthModel.POLYNOMIAL)
        assert 0 < hrs <= 8760

    def test_max_hours_cap(self):
        hrs = _hours_to_saturation(50.0, 0.0001, GrowthModel.LINEAR, max_hours=100)
        assert hrs == 100


# ---------------------------------------------------------------------------
# Tests: _slope_for_component
# ---------------------------------------------------------------------------


class TestSlopeForComponent:
    def test_cpu_slope_positive(self):
        c = _comp(cpu=50.0)
        slope = _slope_for_component(c, SaturationMetric.CPU)
        assert slope > 0

    def test_memory_slope_with_leak(self):
        c = _comp(mem=30.0, mem_leak=10.0)
        slope = _slope_for_component(c, SaturationMetric.MEMORY)
        assert slope > 0.004 * 30  # includes leak contribution

    def test_disk_slope_with_fill(self):
        c = _comp(disk=10.0, disk_fill=1.0)
        slope = _slope_for_component(c, SaturationMetric.DISK)
        assert slope > 0

    def test_connections_slope_with_leak(self):
        c = _comp(connections=200, max_conn=1000, conn_leak=5.0)
        slope = _slope_for_component(c, SaturationMetric.CONNECTIONS)
        assert slope > 0

    def test_iops_slope(self):
        c = _comp(disk=40.0)
        slope = _slope_for_component(c, SaturationMetric.IOPS)
        assert slope > 0

    def test_bandwidth_slope(self):
        c = _comp(connections=300, max_conn=1000)
        slope = _slope_for_component(c, SaturationMetric.BANDWIDTH)
        assert slope > 0

    def test_queue_depth_slope(self):
        c = _comp(cpu=60.0)
        slope = _slope_for_component(c, SaturationMetric.QUEUE_DEPTH)
        assert slope > 0

    def test_zero_metrics_gives_zero_slope(self):
        c = _comp(cpu=0.0, mem=0.0, disk=0.0, connections=0, max_conn=1000)
        slope = _slope_for_component(c, SaturationMetric.CPU)
        assert slope == 0.0


# ---------------------------------------------------------------------------
# Tests: _best_growth_model
# ---------------------------------------------------------------------------


class TestBestGrowthModel:
    def test_high_utilization_returns_exponential(self):
        assert _best_growth_model(80.0, 1.0) == GrowthModel.EXPONENTIAL

    def test_low_utilization_returns_logarithmic(self):
        assert _best_growth_model(10.0, 1.0) == GrowthModel.LOGARITHMIC

    def test_mid_utilization_returns_linear(self):
        assert _best_growth_model(50.0, 1.0) == GrowthModel.LINEAR

    def test_zero_slope_returns_linear(self):
        assert _best_growth_model(80.0, 0.0) == GrowthModel.LINEAR


# ---------------------------------------------------------------------------
# Tests: _confidence_for_prediction
# ---------------------------------------------------------------------------


class TestConfidenceForPrediction:
    def test_high_slope_high_confidence(self):
        conf = _confidence_for_prediction(80.0, 2.0, 100.0)
        assert 0.5 < conf <= 1.0

    def test_zero_slope_low_confidence(self):
        conf = _confidence_for_prediction(50.0, 0.0, 100.0)
        assert conf == 0.3

    def test_long_horizon_penalised(self):
        short = _confidence_for_prediction(50.0, 1.0, 100.0)
        long_ = _confidence_for_prediction(50.0, 1.0, 1000.0)
        assert long_ <= short

    def test_clamp_to_unit(self):
        conf = _confidence_for_prediction(99.0, 100.0, 1.0)
        assert 0.0 <= conf <= 1.0


# ---------------------------------------------------------------------------
# Tests: _recommend_action
# ---------------------------------------------------------------------------


class TestRecommendAction:
    def test_high_current_suggests_scale_up(self):
        assert _recommend_action(SaturationMetric.CPU, 200, 95.0) == "scale_up"

    def test_imminent_saturation_suggests_scale_up(self):
        assert _recommend_action(SaturationMetric.CPU, 12, 50.0) == "scale_up"

    def test_medium_term_suggests_scale_out(self):
        assert _recommend_action(SaturationMetric.CPU, 100, 50.0) == "scale_out"

    def test_low_usage_suggests_optimize(self):
        assert _recommend_action(SaturationMetric.CPU, 2000, 10.0) == "optimize"

    def test_moderate_future_suggests_scale_out(self):
        assert _recommend_action(SaturationMetric.MEMORY, 500, 50.0) == "scale_out"


# ---------------------------------------------------------------------------
# Tests: _cost_of_inaction
# ---------------------------------------------------------------------------


class TestCostOfInaction:
    def test_positive_slope_returns_positive(self):
        cost = _cost_of_inaction(80.0, 1.0)
        assert cost > 0

    def test_zero_slope_returns_zero(self):
        assert _cost_of_inaction(50.0, 0.0) == 0.0

    def test_higher_value_higher_cost(self):
        low = _cost_of_inaction(20.0, 1.0)
        high = _cost_of_inaction(80.0, 1.0)
        assert high > low


# ---------------------------------------------------------------------------
# Tests: _risk_label / _severity_label
# ---------------------------------------------------------------------------


class TestRiskLabel:
    def test_critical_high_current(self):
        assert _risk_label(500, 95.0) == "critical"

    def test_critical_imminent(self):
        assert _risk_label(12, 50.0) == "critical"

    def test_high(self):
        assert _risk_label(100, 76.0) == "high"

    def test_medium(self):
        assert _risk_label(500, 55.0) == "medium"

    def test_low(self):
        assert _risk_label(1000, 30.0) == "low"

    def test_severity_matches_risk(self):
        assert _severity_label(12, 50.0) == _risk_label(12, 50.0)


# ---------------------------------------------------------------------------
# Tests: _current_capacity_dict
# ---------------------------------------------------------------------------


class TestCurrentCapacityDict:
    def test_keys_present(self):
        c = _comp()
        d = _current_capacity_dict(c)
        assert "cpu_percent" in d
        assert "memory_percent" in d
        assert "replicas" in d

    def test_values_match_component(self):
        c = _comp(cpu=75.0, mem=60.0, connections=300)
        d = _current_capacity_dict(c)
        assert d["cpu_percent"] == 75.0
        assert d["memory_percent"] == 60.0
        assert d["connections"] == 300.0


# ---------------------------------------------------------------------------
# Tests: _recommended_capacity_dict
# ---------------------------------------------------------------------------


class TestRecommendedCapacityDict:
    def test_no_urgent_predictions_keeps_same(self):
        c = _comp()
        preds = [
            SaturationPrediction(
                component_id="c1",
                metric=SaturationMetric.CPU,
                current_value=50.0,
                predicted_saturation_hours=5000.0,
                growth_model=GrowthModel.LINEAR,
                confidence=0.5,
                trend_slope=0.01,
                recommended_action="optimize",
                cost_of_inaction_per_hour=0.0,
            )
        ]
        rec = _recommended_capacity_dict(c, preds)
        assert rec["replicas"] == float(c.replicas)

    def test_urgent_prediction_increases_replicas(self):
        c = _comp()
        preds = [
            SaturationPrediction(
                component_id="c1",
                metric=SaturationMetric.CPU,
                current_value=80.0,
                predicted_saturation_hours=100.0,
                growth_model=GrowthModel.LINEAR,
                confidence=0.8,
                trend_slope=0.5,
                recommended_action="scale_out",
                cost_of_inaction_per_hour=10.0,
            )
        ]
        rec = _recommended_capacity_dict(c, preds)
        assert rec["replicas"] > float(c.replicas)


# ---------------------------------------------------------------------------
# Tests: _monthly_cost_delta
# ---------------------------------------------------------------------------


class TestMonthlyCostDelta:
    def test_no_scale_zero_delta(self):
        c = _comp(replicas=2)
        rec = {"replicas": 2.0}
        assert _monthly_cost_delta(c, rec) == 0.0

    def test_scale_up_positive_delta(self):
        c = _comp(replicas=1, hourly_cost=1.0)
        rec = {"replicas": 3.0}
        delta = _monthly_cost_delta(c, rec)
        assert delta == pytest.approx(2 * 1.0 * 730, rel=0.01)


# ---------------------------------------------------------------------------
# Tests: SaturationPrediction model
# ---------------------------------------------------------------------------


class TestSaturationPredictionModel:
    def test_create_valid(self):
        p = SaturationPrediction(
            component_id="x",
            metric=SaturationMetric.CPU,
            current_value=50.0,
            predicted_saturation_hours=100.0,
            growth_model=GrowthModel.LINEAR,
            confidence=0.8,
            trend_slope=0.1,
            recommended_action="scale_out",
            cost_of_inaction_per_hour=5.0,
        )
        assert p.component_id == "x"

    def test_current_value_upper_bound(self):
        with pytest.raises(Exception):
            SaturationPrediction(
                component_id="x",
                metric=SaturationMetric.CPU,
                current_value=150.0,
                predicted_saturation_hours=100.0,
                growth_model=GrowthModel.LINEAR,
                confidence=0.8,
                trend_slope=0.1,
                recommended_action="scale_out",
                cost_of_inaction_per_hour=5.0,
            )

    def test_confidence_upper_bound(self):
        with pytest.raises(Exception):
            SaturationPrediction(
                component_id="x",
                metric=SaturationMetric.CPU,
                current_value=50.0,
                predicted_saturation_hours=100.0,
                growth_model=GrowthModel.LINEAR,
                confidence=1.5,
                trend_slope=0.1,
                recommended_action="scale_out",
                cost_of_inaction_per_hour=5.0,
            )


# ---------------------------------------------------------------------------
# Tests: ScalingStep model
# ---------------------------------------------------------------------------


class TestScalingStepModel:
    def test_create_valid(self):
        s = ScalingStep(
            trigger_metric=SaturationMetric.MEMORY,
            trigger_threshold=80.0,
            action="scale_out",
            new_capacity={"replicas": 3.0},
            cost_delta=100.0,
            implementation_time_hours=2.0,
        )
        assert s.action == "scale_out"


# ---------------------------------------------------------------------------
# Tests: CapacityPlan model
# ---------------------------------------------------------------------------


class TestCapacityPlanModel:
    def test_create_valid(self):
        p = CapacityPlan(
            component_id="c1",
            current_capacity={"cpu_percent": 50.0},
            recommended_capacity={"cpu_percent": 50.0, "replicas": 2.0},
            scaling_steps=[],
            estimated_monthly_cost_delta=100.0,
            risk_if_no_action="medium",
        )
        assert p.risk_if_no_action == "medium"


# ---------------------------------------------------------------------------
# Tests: BottleneckResult model
# ---------------------------------------------------------------------------


class TestBottleneckResultModel:
    def test_create_valid(self):
        b = BottleneckResult(
            component_id="c1",
            component_name="comp",
            metric=SaturationMetric.CPU,
            current_value=80.0,
            hours_to_saturation=100.0,
            severity="high",
        )
        assert b.severity == "high"


# ---------------------------------------------------------------------------
# Tests: TrafficSpikeResult model
# ---------------------------------------------------------------------------


class TestTrafficSpikeResultModel:
    def test_create_valid(self):
        from datetime import datetime, timezone
        t = TrafficSpikeResult(
            multiplier=2.0,
            total_components=3,
            overloaded_components=["a"],
            surviving_components=["b", "c"],
            first_failure_component="a",
            cascade_risk="low",
            recommended_pre_scaling={"a": 4},
            timestamp=datetime.now(timezone.utc),
        )
        assert t.multiplier == 2.0


# ---------------------------------------------------------------------------
# Tests: RightSizeRecommendation model
# ---------------------------------------------------------------------------


class TestRightSizeRecommendationModel:
    def test_create_valid(self):
        r = RightSizeRecommendation(
            component_id="c1",
            component_name="comp",
            status="right_sized",
            current_utilization=50.0,
            target_utilization=60.0,
            recommended_replicas=2,
            current_replicas=2,
            monthly_savings=0.0,
            risk_delta="same",
        )
        assert r.status == "right_sized"


# ---------------------------------------------------------------------------
# Tests: CostForecast model
# ---------------------------------------------------------------------------


class TestCostForecastModel:
    def test_create_valid(self):
        f = CostForecast(
            months=12,
            growth_rate=5.0,
            monthly_costs=[100.0] * 12,
            total_cost=1200.0,
            cost_trend="stable",
            scaling_events_count=0,
            peak_monthly_cost=100.0,
        )
        assert f.months == 12


# ---------------------------------------------------------------------------
# Tests: SeasonalLoadResult model
# ---------------------------------------------------------------------------


class TestSeasonalLoadResultModel:
    def test_create_valid(self):
        s = SeasonalLoadResult(
            peak_multiplier=3.0,
            duration_hours=48.0,
            components_needing_scaling=["c1"],
            max_required_replicas={"c1": 6},
            estimated_extra_cost=500.0,
            survival_probability=0.9,
            recommendations=["Scale up c1"],
        )
        assert s.peak_multiplier == 3.0


# ---------------------------------------------------------------------------
# Tests: CapacityPlanningEngine.predict_saturation
# ---------------------------------------------------------------------------


class TestPredictSaturation:
    def test_returns_list_for_valid_component(self):
        g = _graph(_comp())
        engine = CapacityPlanningEngine()
        preds = engine.predict_saturation(g, "c1")
        assert isinstance(preds, list)
        assert len(preds) > 0

    def test_returns_empty_for_missing_component(self):
        g = _graph(_comp())
        engine = CapacityPlanningEngine()
        assert engine.predict_saturation(g, "missing") == []

    def test_predictions_have_correct_component_id(self):
        g = _graph(_comp(cid="srv"))
        engine = CapacityPlanningEngine()
        for p in engine.predict_saturation(g, "srv"):
            assert p.component_id == "srv"

    def test_predictions_cover_default_metrics(self):
        g = _graph(_comp())
        engine = CapacityPlanningEngine()
        preds = engine.predict_saturation(g, "c1")
        metrics = {p.metric for p in preds}
        assert SaturationMetric.CPU in metrics
        assert SaturationMetric.MEMORY in metrics

    def test_custom_hours_ahead(self):
        g = _graph(_comp())
        engine = CapacityPlanningEngine()
        preds = engine.predict_saturation(g, "c1", hours_ahead=24.0)
        assert len(preds) > 0

    def test_high_utilization_predicts_imminent_saturation(self):
        g = _graph(_comp(cpu=95.0, mem=95.0))
        engine = CapacityPlanningEngine()
        preds = engine.predict_saturation(g, "c1")
        cpu_pred = [p for p in preds if p.metric == SaturationMetric.CPU][0]
        assert cpu_pred.predicted_saturation_hours < 8760

    def test_zero_utilization_distant_saturation(self):
        g = _graph(_comp(cpu=0.0, mem=0.0, disk=0.0, connections=0))
        engine = CapacityPlanningEngine()
        preds = engine.predict_saturation(g, "c1")
        for p in preds:
            assert p.predicted_saturation_hours >= 8760 or p.current_value == 0.0


# ---------------------------------------------------------------------------
# Tests: CapacityPlanningEngine.generate_capacity_plan
# ---------------------------------------------------------------------------


class TestGenerateCapacityPlan:
    def test_returns_plan_for_valid_component(self):
        g = _graph(_comp())
        engine = CapacityPlanningEngine()
        plan = engine.generate_capacity_plan(g, "c1")
        assert isinstance(plan, CapacityPlan)
        assert plan.component_id == "c1"

    def test_missing_component_returns_empty_plan(self):
        g = _graph(_comp())
        engine = CapacityPlanningEngine()
        plan = engine.generate_capacity_plan(g, "nope")
        assert plan.component_id == "nope"
        assert plan.scaling_steps == []
        assert plan.risk_if_no_action == "low"

    def test_plan_has_current_capacity(self):
        g = _graph(_comp(cpu=70.0))
        engine = CapacityPlanningEngine()
        plan = engine.generate_capacity_plan(g, "c1")
        assert "cpu_percent" in plan.current_capacity

    def test_plan_has_recommended_capacity(self):
        g = _graph(_comp(cpu=85.0, mem=80.0))
        engine = CapacityPlanningEngine()
        plan = engine.generate_capacity_plan(g, "c1")
        assert "replicas" in plan.recommended_capacity

    def test_high_util_creates_scaling_steps(self):
        g = _graph(_comp(cpu=85.0, mem=85.0))
        engine = CapacityPlanningEngine()
        plan = engine.generate_capacity_plan(g, "c1")
        assert len(plan.scaling_steps) > 0

    def test_risk_reflects_utilization(self):
        g = _graph(_comp(cpu=95.0, mem=90.0))
        engine = CapacityPlanningEngine()
        plan = engine.generate_capacity_plan(g, "c1")
        assert plan.risk_if_no_action in ("critical", "high")


# ---------------------------------------------------------------------------
# Tests: CapacityPlanningEngine.find_bottlenecks
# ---------------------------------------------------------------------------


class TestFindBottlenecks:
    def test_returns_list(self):
        g = _graph(_comp())
        engine = CapacityPlanningEngine()
        bns = engine.find_bottlenecks(g)
        assert isinstance(bns, list)

    def test_one_per_component(self):
        g = _graph(
            _comp(cid="a", name="A"),
            _comp(cid="b", name="B"),
        )
        engine = CapacityPlanningEngine()
        bns = engine.find_bottlenecks(g)
        assert len(bns) == 2

    def test_sorted_by_hours(self):
        g = _graph(
            _comp(cid="hot", name="Hot", cpu=95.0),
            _comp(cid="cold", name="Cold", cpu=10.0),
        )
        engine = CapacityPlanningEngine()
        bns = engine.find_bottlenecks(g)
        assert bns[0].hours_to_saturation <= bns[1].hours_to_saturation

    def test_empty_graph(self):
        g = InfraGraph()
        engine = CapacityPlanningEngine()
        assert engine.find_bottlenecks(g) == []

    def test_severity_assigned(self):
        g = _graph(_comp(cpu=92.0))
        engine = CapacityPlanningEngine()
        bns = engine.find_bottlenecks(g)
        assert bns[0].severity in ("critical", "high", "medium", "low")


# ---------------------------------------------------------------------------
# Tests: CapacityPlanningEngine.simulate_traffic_spike
# ---------------------------------------------------------------------------


class TestSimulateTrafficSpike:
    def test_2x_spike(self):
        g = _graph(_comp(cpu=60.0, mem=60.0))
        engine = CapacityPlanningEngine()
        result = engine.simulate_traffic_spike(g, 2.0)
        assert result.multiplier == 2.0
        assert result.total_components == 1

    def test_overloaded_when_exceeds_100(self):
        g = _graph(_comp(cpu=60.0, mem=60.0))
        engine = CapacityPlanningEngine()
        result = engine.simulate_traffic_spike(g, 2.0)
        assert "c1" in result.overloaded_components

    def test_surviving_when_under_100(self):
        g = _graph(_comp(cpu=20.0, mem=20.0, connections=50, max_conn=1000))
        engine = CapacityPlanningEngine()
        result = engine.simulate_traffic_spike(g, 2.0)
        assert "c1" in result.surviving_components

    def test_10x_spike_many_overloaded(self):
        g = _graph(
            _comp(cid="a", name="A", cpu=30.0, mem=30.0),
            _comp(cid="b", name="B", cpu=40.0, mem=40.0),
        )
        engine = CapacityPlanningEngine()
        result = engine.simulate_traffic_spike(g, 10.0)
        assert len(result.overloaded_components) > 0

    def test_first_failure_identified(self):
        g = _graph(
            _comp(cid="a", name="A", cpu=80.0, mem=80.0),
            _comp(cid="b", name="B", cpu=30.0, mem=30.0),
        )
        engine = CapacityPlanningEngine()
        result = engine.simulate_traffic_spike(g, 2.0)
        assert result.first_failure_component is not None

    def test_cascade_risk_critical_many_failures(self):
        comps = [_comp(cid=f"c{i}", name=f"C{i}", cpu=70.0, mem=70.0) for i in range(4)]
        g = _graph(*comps)
        engine = CapacityPlanningEngine()
        result = engine.simulate_traffic_spike(g, 2.0)
        assert result.cascade_risk in ("critical", "high")

    def test_cascade_risk_none_no_failures(self):
        g = _graph(_comp(cpu=10.0, mem=10.0, connections=10, max_conn=10000))
        engine = CapacityPlanningEngine()
        result = engine.simulate_traffic_spike(g, 2.0)
        assert result.cascade_risk == "none"

    def test_empty_graph(self):
        g = InfraGraph()
        engine = CapacityPlanningEngine()
        result = engine.simulate_traffic_spike(g, 2.0)
        assert result.cascade_risk == "none"
        assert result.total_components == 0

    def test_recommended_scaling_present(self):
        g = _graph(_comp(cpu=60.0, mem=60.0))
        engine = CapacityPlanningEngine()
        result = engine.simulate_traffic_spike(g, 2.0)
        if result.overloaded_components:
            assert len(result.recommended_pre_scaling) > 0

    def test_timestamp_is_utc(self):
        from datetime import timezone
        g = _graph(_comp())
        engine = CapacityPlanningEngine()
        result = engine.simulate_traffic_spike(g, 2.0)
        assert result.timestamp.tzinfo == timezone.utc


# ---------------------------------------------------------------------------
# Tests: CapacityPlanningEngine.recommend_right_sizing
# ---------------------------------------------------------------------------


class TestRecommendRightSizing:
    def test_returns_list(self):
        g = _graph(_comp())
        engine = CapacityPlanningEngine()
        recs = engine.recommend_right_sizing(g)
        assert isinstance(recs, list)

    def test_over_provisioned_detected(self):
        g = _graph(_comp(cpu=5.0, mem=5.0, disk=0.0, connections=0, replicas=4))
        engine = CapacityPlanningEngine()
        recs = engine.recommend_right_sizing(g)
        assert recs[0].status == "over_provisioned"

    def test_under_provisioned_detected(self):
        g = _graph(_comp(cpu=90.0, mem=85.0))
        engine = CapacityPlanningEngine()
        recs = engine.recommend_right_sizing(g)
        assert recs[0].status == "under_provisioned"

    def test_right_sized_detected(self):
        g = _graph(_comp(cpu=50.0, mem=40.0, disk=0.0, connections=0))
        engine = CapacityPlanningEngine()
        recs = engine.recommend_right_sizing(g)
        assert recs[0].status == "right_sized"

    def test_over_provisioned_savings_positive(self):
        g = _graph(_comp(cpu=5.0, mem=5.0, disk=0.0, connections=0, replicas=4, hourly_cost=1.0))
        engine = CapacityPlanningEngine()
        recs = engine.recommend_right_sizing(g)
        assert recs[0].monthly_savings > 0

    def test_right_sized_savings_zero(self):
        g = _graph(_comp(cpu=50.0, mem=40.0, disk=0.0, connections=0))
        engine = CapacityPlanningEngine()
        recs = engine.recommend_right_sizing(g)
        assert recs[0].monthly_savings == 0.0

    def test_risk_delta_under_provisioned(self):
        g = _graph(_comp(cpu=90.0))
        engine = CapacityPlanningEngine()
        recs = engine.recommend_right_sizing(g)
        assert recs[0].risk_delta == "lower"

    def test_empty_graph(self):
        g = InfraGraph()
        engine = CapacityPlanningEngine()
        assert engine.recommend_right_sizing(g) == []


# ---------------------------------------------------------------------------
# Tests: CapacityPlanningEngine.forecast_cost
# ---------------------------------------------------------------------------


class TestForecastCost:
    def test_returns_cost_forecast(self):
        g = _graph(_comp(hourly_cost=1.0))
        engine = CapacityPlanningEngine()
        fc = engine.forecast_cost(g, 5.0, 12)
        assert isinstance(fc, CostForecast)

    def test_monthly_costs_length(self):
        g = _graph(_comp(hourly_cost=1.0))
        engine = CapacityPlanningEngine()
        fc = engine.forecast_cost(g, 5.0, 6)
        assert len(fc.monthly_costs) == 6

    def test_total_cost_equals_sum(self):
        g = _graph(_comp(hourly_cost=1.0))
        engine = CapacityPlanningEngine()
        fc = engine.forecast_cost(g, 0.0, 3)
        assert fc.total_cost == pytest.approx(sum(fc.monthly_costs), rel=0.01)

    def test_increasing_trend(self):
        g = _graph(_comp(hourly_cost=1.0))
        engine = CapacityPlanningEngine()
        fc = engine.forecast_cost(g, 10.0, 12)
        assert fc.cost_trend == "increasing"

    def test_stable_trend_zero_growth(self):
        g = _graph(_comp(hourly_cost=1.0))
        engine = CapacityPlanningEngine()
        fc = engine.forecast_cost(g, 0.0, 12)
        assert fc.cost_trend == "stable"

    def test_peak_cost_gte_first(self):
        g = _graph(_comp(hourly_cost=1.0))
        engine = CapacityPlanningEngine()
        fc = engine.forecast_cost(g, 5.0, 12)
        assert fc.peak_monthly_cost >= fc.monthly_costs[0]

    def test_empty_graph(self):
        g = InfraGraph()
        engine = CapacityPlanningEngine()
        fc = engine.forecast_cost(g, 5.0, 6)
        assert fc.total_cost == 0.0

    def test_scaling_events_counted(self):
        g = _graph(_comp(hourly_cost=1.0))
        engine = CapacityPlanningEngine()
        fc = engine.forecast_cost(g, 50.0, 24)
        assert fc.scaling_events_count >= 0


# ---------------------------------------------------------------------------
# Tests: CapacityPlanningEngine.simulate_seasonal_load
# ---------------------------------------------------------------------------


class TestSimulateSeasonalLoad:
    def test_returns_result(self):
        g = _graph(_comp())
        engine = CapacityPlanningEngine()
        result = engine.simulate_seasonal_load(g, 3.0, 48.0)
        assert isinstance(result, SeasonalLoadResult)

    def test_peak_multiplier_stored(self):
        g = _graph(_comp())
        engine = CapacityPlanningEngine()
        result = engine.simulate_seasonal_load(g, 5.0, 24.0)
        assert result.peak_multiplier == 5.0

    def test_duration_stored(self):
        g = _graph(_comp())
        engine = CapacityPlanningEngine()
        result = engine.simulate_seasonal_load(g, 3.0, 72.0)
        assert result.duration_hours == 72.0

    def test_needs_scaling_at_high_multiplier(self):
        g = _graph(_comp(cpu=50.0, mem=50.0))
        engine = CapacityPlanningEngine()
        result = engine.simulate_seasonal_load(g, 5.0, 48.0)
        assert len(result.components_needing_scaling) > 0

    def test_no_scaling_at_low_multiplier(self):
        g = _graph(_comp(cpu=10.0, mem=10.0, connections=10, max_conn=10000))
        engine = CapacityPlanningEngine()
        result = engine.simulate_seasonal_load(g, 1.5, 48.0)
        assert len(result.components_needing_scaling) == 0

    def test_extra_cost_positive_when_scaling(self):
        g = _graph(_comp(cpu=50.0, mem=50.0, hourly_cost=1.0))
        engine = CapacityPlanningEngine()
        result = engine.simulate_seasonal_load(g, 5.0, 48.0)
        assert result.estimated_extra_cost > 0

    def test_survival_probability_range(self):
        g = _graph(_comp(cpu=50.0, mem=50.0))
        engine = CapacityPlanningEngine()
        result = engine.simulate_seasonal_load(g, 3.0, 48.0)
        assert 0.0 <= result.survival_probability <= 1.0

    def test_recommendations_not_empty(self):
        g = _graph(_comp(cpu=50.0, mem=50.0))
        engine = CapacityPlanningEngine()
        result = engine.simulate_seasonal_load(g, 3.0, 48.0)
        assert len(result.recommendations) > 0

    def test_autoscaling_recommendation(self):
        g = _graph(_comp(cpu=50.0, mem=50.0))
        engine = CapacityPlanningEngine()
        result = engine.simulate_seasonal_load(g, 5.0, 48.0)
        has_autoscale_rec = any("autoscaling" in r.lower() for r in result.recommendations)
        assert has_autoscale_rec

    def test_autoscaling_max_replicas_warning(self):
        c = _comp(cpu=50.0, mem=50.0, autoscale=True)
        c.autoscaling.max_replicas = 2
        g = _graph(c)
        engine = CapacityPlanningEngine()
        result = engine.simulate_seasonal_load(g, 10.0, 48.0)
        has_max_rec = any("max_replicas" in r.lower() for r in result.recommendations)
        assert has_max_rec

    def test_empty_graph(self):
        g = InfraGraph()
        engine = CapacityPlanningEngine()
        result = engine.simulate_seasonal_load(g, 3.0, 48.0)
        assert result.survival_probability == 1.0

    def test_max_replicas_dict_has_all_components(self):
        g = _graph(
            _comp(cid="a", name="A"),
            _comp(cid="b", name="B"),
        )
        engine = CapacityPlanningEngine()
        result = engine.simulate_seasonal_load(g, 3.0, 48.0)
        assert "a" in result.max_required_replicas
        assert "b" in result.max_required_replicas

    def test_sufficient_capacity_recommendation(self):
        g = _graph(_comp(cpu=5.0, mem=5.0, connections=5, max_conn=100000))
        engine = CapacityPlanningEngine()
        result = engine.simulate_seasonal_load(g, 1.1, 48.0)
        assert any("sufficient" in r.lower() for r in result.recommendations)


# ---------------------------------------------------------------------------
# Tests: Integration / multi-component scenarios
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_full_pipeline_three_tier(self):
        g = InfraGraph()
        lb = _comp(cid="lb", name="LB", ctype=ComponentType.LOAD_BALANCER, cpu=40.0, mem=30.0)
        api = _comp(cid="api", name="API", cpu=65.0, mem=55.0)
        db = _comp(cid="db", name="DB", ctype=ComponentType.DATABASE, cpu=80.0, mem=75.0)
        g.add_component(lb)
        g.add_component(api)
        g.add_component(db)
        g.add_dependency(Dependency(source_id="lb", target_id="api"))
        g.add_dependency(Dependency(source_id="api", target_id="db"))

        engine = CapacityPlanningEngine()

        # predict_saturation
        preds = engine.predict_saturation(g, "db")
        assert len(preds) > 0

        # generate_capacity_plan
        plan = engine.generate_capacity_plan(g, "db")
        assert plan.risk_if_no_action in ("critical", "high", "medium", "low")

        # find_bottlenecks
        bns = engine.find_bottlenecks(g)
        assert len(bns) == 3
        assert bns[0].component_id == "db"  # highest utilization first

        # traffic spike
        spike = engine.simulate_traffic_spike(g, 2.0)
        assert spike.total_components == 3

        # right sizing
        recs = engine.recommend_right_sizing(g)
        assert len(recs) == 3

        # cost forecast
        fc = engine.forecast_cost(g, 5.0, 6)
        assert fc.months == 6

        # seasonal load
        sl = engine.simulate_seasonal_load(g, 3.0, 48.0)
        assert sl.peak_multiplier == 3.0

    def test_with_degradation_configs(self):
        c = _comp(cpu=60.0, mem=50.0, mem_leak=50.0, disk_fill=0.5, conn_leak=2.0)
        g = _graph(c)
        engine = CapacityPlanningEngine()
        preds = engine.predict_saturation(g, "c1")
        mem_pred = [p for p in preds if p.metric == SaturationMetric.MEMORY][0]
        assert mem_pred.trend_slope > 0

    def test_multiple_component_types(self):
        g = _graph(
            _comp(cid="web", name="Web", ctype=ComponentType.WEB_SERVER, cpu=50.0),
            _comp(cid="cache", name="Cache", ctype=ComponentType.CACHE, cpu=30.0),
            _comp(cid="queue", name="Queue", ctype=ComponentType.QUEUE, cpu=40.0),
        )
        engine = CapacityPlanningEngine()
        bns = engine.find_bottlenecks(g)
        assert len(bns) == 3

    def test_engine_is_stateless(self):
        g1 = _graph(_comp(cid="a", name="A", cpu=90.0))
        g2 = _graph(_comp(cid="b", name="B", cpu=10.0))
        engine = CapacityPlanningEngine()
        bns1 = engine.find_bottlenecks(g1)
        bns2 = engine.find_bottlenecks(g2)
        assert bns1[0].component_id == "a"
        assert bns2[0].component_id == "b"


# ---------------------------------------------------------------------------
# Tests: Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_single_component_graph(self):
        g = _graph(_comp())
        engine = CapacityPlanningEngine()
        assert len(engine.find_bottlenecks(g)) == 1

    def test_zero_utilization_component(self):
        g = _graph(_comp(cpu=0.0, mem=0.0, disk=0.0, connections=0))
        engine = CapacityPlanningEngine()
        recs = engine.recommend_right_sizing(g)
        assert recs[0].status == "right_sized"

    def test_max_utilization_component(self):
        c = _comp(cpu=100.0, mem=100.0)
        g = _graph(c)
        engine = CapacityPlanningEngine()
        preds = engine.predict_saturation(g, "c1")
        cpu_pred = [p for p in preds if p.metric == SaturationMetric.CPU][0]
        assert cpu_pred.current_value == 100.0

    def test_very_large_multiplier_spike(self):
        g = _graph(_comp(cpu=50.0, mem=50.0))
        engine = CapacityPlanningEngine()
        result = engine.simulate_traffic_spike(g, 100.0)
        assert len(result.overloaded_components) == 1

    def test_fractional_multiplier_spike(self):
        g = _graph(_comp(cpu=50.0, mem=50.0, connections=200, max_conn=1000))
        engine = CapacityPlanningEngine()
        result = engine.simulate_traffic_spike(g, 1.1)
        assert result.total_components == 1

    def test_cost_forecast_one_month(self):
        g = _graph(_comp(hourly_cost=1.0))
        engine = CapacityPlanningEngine()
        fc = engine.forecast_cost(g, 0.0, 1)
        assert len(fc.monthly_costs) == 1

    def test_cost_forecast_zero_cost_component(self):
        g = _graph(_comp(hourly_cost=0.0))
        engine = CapacityPlanningEngine()
        fc = engine.forecast_cost(g, 5.0, 6)
        assert fc.total_cost >= 0

    def test_seasonal_load_one_hour(self):
        g = _graph(_comp(cpu=50.0))
        engine = CapacityPlanningEngine()
        result = engine.simulate_seasonal_load(g, 3.0, 1.0)
        assert result.duration_hours == 1.0

    def test_right_sizing_single_replica_low_util(self):
        g = _graph(_comp(cpu=5.0, mem=5.0, disk=0.0, connections=0, replicas=1))
        engine = CapacityPlanningEngine()
        recs = engine.recommend_right_sizing(g)
        # single replica cannot be further reduced
        assert recs[0].status == "right_sized"

    def test_cascade_risk_high(self):
        """30-49% overloaded -> high cascade risk."""
        # 3 components, 1 overloaded = 33%
        g = _graph(
            _comp(cid="a", name="A", cpu=70.0, mem=70.0),
            _comp(cid="b", name="B", cpu=10.0, mem=10.0, connections=10, max_conn=10000),
            _comp(cid="c", name="C", cpu=10.0, mem=10.0, connections=10, max_conn=10000),
        )
        engine = CapacityPlanningEngine()
        result = engine.simulate_traffic_spike(g, 2.0)
        assert result.cascade_risk == "high"

    def test_cascade_risk_medium(self):
        """10-29% overloaded -> medium cascade risk."""
        # 10 components, 2 overloaded = 20%
        comps = [_comp(cid=f"safe{i}", name=f"S{i}", cpu=10.0, mem=10.0, connections=10, max_conn=10000) for i in range(8)]
        comps.append(_comp(cid="hot1", name="H1", cpu=70.0, mem=70.0))
        comps.append(_comp(cid="hot2", name="H2", cpu=70.0, mem=70.0))
        g = _graph(*comps)
        engine = CapacityPlanningEngine()
        result = engine.simulate_traffic_spike(g, 2.0)
        assert result.cascade_risk == "medium"

    def test_cascade_risk_low(self):
        """<10% overloaded -> low cascade risk."""
        comps = [_comp(cid=f"safe{i}", name=f"S{i}", cpu=10.0, mem=10.0, connections=10, max_conn=10000) for i in range(19)]
        comps.append(_comp(cid="hot", name="H", cpu=70.0, mem=70.0))
        g = _graph(*comps)
        engine = CapacityPlanningEngine()
        result = engine.simulate_traffic_spike(g, 2.0)
        assert result.cascade_risk == "low"

    def test_cost_forecast_decreasing_trend(self):
        g = _graph(_comp(hourly_cost=1.0))
        engine = CapacityPlanningEngine()
        fc = engine.forecast_cost(g, -10.0, 12)
        assert fc.cost_trend == "decreasing"

    def test_seasonal_prescale_recommendation(self):
        """When autoscaling is enabled and sufficient, only a pre-scale rec."""
        c = _comp(cpu=50.0, mem=50.0, autoscale=True)
        c.autoscaling.max_replicas = 100
        g = _graph(c)
        engine = CapacityPlanningEngine()
        result = engine.simulate_seasonal_load(g, 3.0, 48.0)
        # Should have recommendations but all autoscaling limits are fine
        assert len(result.recommendations) > 0

    def test_overall_risk_empty_predictions(self):
        engine = CapacityPlanningEngine()
        assert engine._overall_risk([]) == "low"

    def test_seasonal_survival_decreases_with_overload(self):
        g = _graph(_comp(cpu=80.0, mem=80.0))
        engine = CapacityPlanningEngine()
        low = engine.simulate_seasonal_load(g, 2.0, 48.0)
        high = engine.simulate_seasonal_load(g, 10.0, 48.0)
        assert high.survival_probability <= low.survival_probability
