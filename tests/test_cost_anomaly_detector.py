"""Tests for the Infrastructure Cost Anomaly Detector engine."""

from __future__ import annotations

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    Component,
    ComponentType,
    DegradationConfig,
    Dependency,
    OperationalProfile,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.cost_anomaly_detector import (
    AnomalySeverity,
    AnomalyType,
    CostAnomaly,
    CostAnomalyDetectorEngine,
    CostAnomalyReport,
    CostBaseline,
    CostDataPoint,
    CostOptimization,
    DetectionMethod,
    _compute_deviation,
    _quantile,
    _severity_from_deviation,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(cid: str = "c1", ctype: ComponentType = ComponentType.APP_SERVER, **kw):
    return Component(id=cid, name=kw.pop("name", cid), type=ctype, **kw)


def _graph(*comps: Component) -> InfraGraph:
    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    return g


def _dp(
    cid: str = "c1",
    cost: float = 100.0,
    ts: str = "2026-01-01T00:00:00Z",
    category: str = "general",
) -> CostDataPoint:
    return CostDataPoint(
        timestamp=ts, cost_usd=cost, component_id=cid, category=category
    )


# ---------------------------------------------------------------------------
# Enum sanity
# ---------------------------------------------------------------------------


class TestEnums:
    def test_anomaly_type_values(self):
        assert AnomalyType.SPIKE.value == "spike"
        assert AnomalyType.DROP.value == "drop"
        assert AnomalyType.TREND_CHANGE.value == "trend_change"
        assert AnomalyType.SEASONAL_DEVIATION.value == "seasonal_deviation"
        assert AnomalyType.RESOURCE_LEAK.value == "resource_leak"
        assert AnomalyType.PRICING_CHANGE.value == "pricing_change"
        assert AnomalyType.OVER_PROVISIONING.value == "over_provisioning"
        assert AnomalyType.ORPHANED_RESOURCE.value == "orphaned_resource"

    def test_anomaly_type_count(self):
        assert len(AnomalyType) == 8

    def test_severity_values(self):
        assert AnomalySeverity.INFO.value == "info"
        assert AnomalySeverity.LOW.value == "low"
        assert AnomalySeverity.MEDIUM.value == "medium"
        assert AnomalySeverity.HIGH.value == "high"
        assert AnomalySeverity.CRITICAL.value == "critical"

    def test_severity_count(self):
        assert len(AnomalySeverity) == 5

    def test_detection_method_values(self):
        assert DetectionMethod.Z_SCORE.value == "z_score"
        assert DetectionMethod.IQR.value == "iqr"
        assert DetectionMethod.MOVING_AVERAGE.value == "moving_average"
        assert DetectionMethod.PERCENTAGE_CHANGE.value == "percentage_change"
        assert DetectionMethod.FORECAST_DEVIATION.value == "forecast_deviation"

    def test_detection_method_count(self):
        assert len(DetectionMethod) == 5


# ---------------------------------------------------------------------------
# Pydantic model construction
# ---------------------------------------------------------------------------


class TestModels:
    def test_cost_data_point_defaults(self):
        dp = CostDataPoint(
            timestamp="2026-01-01", cost_usd=10.0, component_id="c1"
        )
        assert dp.category == "general"

    def test_cost_data_point_custom_category(self):
        dp = CostDataPoint(
            timestamp="2026-01-01",
            cost_usd=5.0,
            component_id="c1",
            category="compute",
        )
        assert dp.category == "compute"

    def test_cost_anomaly_construction(self):
        a = CostAnomaly(
            anomaly_type=AnomalyType.SPIKE,
            severity=AnomalySeverity.HIGH,
            detection_method=DetectionMethod.Z_SCORE,
            component_id="c1",
            expected_cost=100.0,
            actual_cost=300.0,
            deviation_percent=200.0,
        )
        assert a.description == ""
        assert a.recommendation == ""

    def test_cost_baseline_construction(self):
        b = CostBaseline(
            component_id="c1",
            avg_daily_cost=50.0,
            std_dev=5.0,
            p95_cost=60.0,
            min_cost=40.0,
            max_cost=65.0,
        )
        assert b.component_id == "c1"

    def test_cost_optimization_defaults(self):
        o = CostOptimization(
            component_id="c1",
            current_monthly_cost=200.0,
            optimized_monthly_cost=100.0,
            savings_percent=50.0,
        )
        assert o.recommendation == ""
        assert o.confidence == 0.0

    def test_cost_anomaly_report_defaults(self):
        r = CostAnomalyReport()
        assert r.anomalies == []
        assert r.baselines == []
        assert r.total_spend == 0.0
        assert r.anomaly_spend == 0.0
        assert r.optimization_potential_usd == 0.0
        assert r.optimizations == []
        assert r.timestamp == ""


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_severity_from_deviation_info(self):
        assert _severity_from_deviation(5.0) == AnomalySeverity.INFO

    def test_severity_from_deviation_low(self):
        assert _severity_from_deviation(25.0) == AnomalySeverity.LOW

    def test_severity_from_deviation_medium(self):
        assert _severity_from_deviation(75.0) == AnomalySeverity.MEDIUM

    def test_severity_from_deviation_high(self):
        assert _severity_from_deviation(150.0) == AnomalySeverity.HIGH

    def test_severity_from_deviation_critical(self):
        assert _severity_from_deviation(250.0) == AnomalySeverity.CRITICAL

    def test_severity_negative_deviation(self):
        assert _severity_from_deviation(-250.0) == AnomalySeverity.CRITICAL

    def test_compute_deviation_normal(self):
        assert _compute_deviation(150.0, 100.0) == 50.0

    def test_compute_deviation_zero_expected(self):
        assert _compute_deviation(50.0, 0.0) == 100.0

    def test_compute_deviation_both_zero(self):
        assert _compute_deviation(0.0, 0.0) == 0.0

    def test_compute_deviation_negative(self):
        assert _compute_deviation(50.0, 100.0) == -50.0

    def test_quantile_empty(self):
        assert _quantile([], 0.5) == 0.0

    def test_quantile_single(self):
        assert _quantile([10.0], 0.5) == 10.0

    def test_quantile_median(self):
        assert _quantile([1.0, 2.0, 3.0], 0.5) == 2.0

    def test_quantile_p95(self):
        vals = sorted([float(i) for i in range(1, 101)])
        p95 = _quantile(vals, 0.95)
        assert 94.0 <= p95 <= 96.0


# ---------------------------------------------------------------------------
# Engine: compute_baselines
# ---------------------------------------------------------------------------


class TestComputeBaselines:
    def setup_method(self):
        self.engine = CostAnomalyDetectorEngine()

    def test_empty_data(self):
        assert self.engine.compute_baselines([]) == []

    def test_single_point_per_component(self):
        data = [_dp("c1", 100.0)]
        baselines = self.engine.compute_baselines(data)
        assert len(baselines) == 1
        assert baselines[0].avg_daily_cost == 100.0
        assert baselines[0].std_dev == 0.0

    def test_multiple_points(self):
        data = [_dp("c1", c) for c in [100.0, 110.0, 90.0, 105.0, 95.0]]
        baselines = self.engine.compute_baselines(data)
        assert len(baselines) == 1
        b = baselines[0]
        assert b.avg_daily_cost == 100.0
        assert b.std_dev > 0
        assert b.min_cost == 90.0
        assert b.max_cost == 110.0

    def test_multiple_components(self):
        data = [_dp("c1", 10.0), _dp("c1", 20.0), _dp("c2", 50.0)]
        baselines = self.engine.compute_baselines(data)
        assert len(baselines) == 2
        ids = {b.component_id for b in baselines}
        assert ids == {"c1", "c2"}

    def test_p95_cost(self):
        data = [_dp("c1", float(i)) for i in range(1, 21)]
        baselines = self.engine.compute_baselines(data)
        b = baselines[0]
        assert b.p95_cost >= 19.0


# ---------------------------------------------------------------------------
# Engine: detect_by_zscore
# ---------------------------------------------------------------------------


class TestDetectByZScore:
    def setup_method(self):
        self.engine = CostAnomalyDetectorEngine()

    def test_no_data(self):
        assert self.engine.detect_by_zscore([]) == []

    def test_single_point_no_anomaly(self):
        assert self.engine.detect_by_zscore([_dp("c1", 100.0)]) == []

    def test_constant_costs_no_anomaly(self):
        data = [_dp("c1", 100.0) for _ in range(10)]
        assert self.engine.detect_by_zscore(data) == []

    def test_spike_detected(self):
        data = [_dp("c1", 100.0) for _ in range(10)]
        data.append(_dp("c1", 1000.0))
        anomalies = self.engine.detect_by_zscore(data)
        assert len(anomalies) >= 1
        assert any(a.anomaly_type == AnomalyType.SPIKE for a in anomalies)

    def test_drop_detected(self):
        data = [_dp("c1", 1000.0) for _ in range(10)]
        data.append(_dp("c1", 10.0))
        anomalies = self.engine.detect_by_zscore(data)
        assert len(anomalies) >= 1
        assert any(a.anomaly_type == AnomalyType.DROP for a in anomalies)

    def test_custom_threshold(self):
        data = [_dp("c1", 100.0) for _ in range(10)]
        data.append(_dp("c1", 200.0))
        # Very high threshold — no anomalies
        assert self.engine.detect_by_zscore(data, threshold=100.0) == []

    def test_detection_method_is_zscore(self):
        data = [_dp("c1", 100.0) for _ in range(10)]
        data.append(_dp("c1", 1000.0))
        anomalies = self.engine.detect_by_zscore(data)
        for a in anomalies:
            assert a.detection_method == DetectionMethod.Z_SCORE


# ---------------------------------------------------------------------------
# Engine: detect_by_iqr
# ---------------------------------------------------------------------------


class TestDetectByIQR:
    def setup_method(self):
        self.engine = CostAnomalyDetectorEngine()

    def test_no_data(self):
        assert self.engine.detect_by_iqr([]) == []

    def test_too_few_points(self):
        data = [_dp("c1", 100.0), _dp("c1", 110.0), _dp("c1", 120.0)]
        assert self.engine.detect_by_iqr(data) == []

    def test_constant_values_no_iqr_anomaly(self):
        data = [_dp("c1", 100.0) for _ in range(10)]
        assert self.engine.detect_by_iqr(data) == []

    def test_outlier_detected(self):
        # Need variance in baseline so IQR > 0
        data = [_dp("c1", 90.0 + i * 2.0) for i in range(20)]
        data.append(_dp("c1", 1000.0))
        anomalies = self.engine.detect_by_iqr(data)
        assert len(anomalies) >= 1
        assert anomalies[0].detection_method == DetectionMethod.IQR

    def test_low_outlier_detected(self):
        data = [_dp("c1", 400.0 + i * 5.0) for i in range(20)]
        data.append(_dp("c1", 1.0))
        anomalies = self.engine.detect_by_iqr(data)
        assert len(anomalies) >= 1
        assert any(a.anomaly_type == AnomalyType.DROP for a in anomalies)


# ---------------------------------------------------------------------------
# Engine: detect_by_moving_average
# ---------------------------------------------------------------------------


class TestDetectByMovingAverage:
    def setup_method(self):
        self.engine = CostAnomalyDetectorEngine()

    def test_no_data(self):
        assert self.engine.detect_by_moving_average([]) == []

    def test_not_enough_data_for_window(self):
        data = [_dp("c1", 100.0), _dp("c1", 110.0)]
        assert self.engine.detect_by_moving_average(data, window=3) == []

    def test_stable_series(self):
        data = [_dp("c1", 100.0) for _ in range(10)]
        assert self.engine.detect_by_moving_average(data, window=3) == []

    def test_spike_after_stable(self):
        data = [_dp("c1", 100.0) for _ in range(5)]
        data.append(_dp("c1", 300.0))
        anomalies = self.engine.detect_by_moving_average(data, window=3)
        assert len(anomalies) >= 1
        assert anomalies[0].detection_method == DetectionMethod.MOVING_AVERAGE

    def test_window_zero_treated_as_one(self):
        data = [_dp("c1", 100.0) for _ in range(5)]
        data.append(_dp("c1", 300.0))
        anomalies = self.engine.detect_by_moving_average(data, window=0)
        assert len(anomalies) >= 1

    def test_drop_detection(self):
        data = [_dp("c1", 300.0) for _ in range(5)]
        data.append(_dp("c1", 50.0))
        anomalies = self.engine.detect_by_moving_average(data, window=3)
        assert any(a.anomaly_type == AnomalyType.DROP for a in anomalies)


# ---------------------------------------------------------------------------
# Engine: identify_optimizations
# ---------------------------------------------------------------------------


class TestIdentifyOptimizations:
    def setup_method(self):
        self.engine = CostAnomalyDetectorEngine()

    def test_empty_graph(self):
        g = InfraGraph()
        assert self.engine.identify_optimizations(g, []) == []

    def test_over_provisioned_replicas(self):
        c = _comp("c1", replicas=5)
        g = _graph(c)
        baselines = [
            CostBaseline(
                component_id="c1",
                avg_daily_cost=100.0,
                std_dev=5.0,
                p95_cost=110.0,
                min_cost=90.0,
                max_cost=120.0,
            )
        ]
        opts = self.engine.identify_optimizations(g, baselines)
        assert any("Reduce replicas" in o.recommendation for o in opts)

    def test_under_utilised_resource(self):
        c = _comp("c1")
        g = _graph(c)
        opts = self.engine.identify_optimizations(g, [])
        assert any("Right-size" in o.recommendation for o in opts)

    def test_autoscaling_suggestion(self):
        c = _comp("c1", ctype=ComponentType.APP_SERVER, replicas=3)
        g = _graph(c)
        opts = self.engine.identify_optimizations(g, [])
        assert any("autoscaling" in o.recommendation.lower() for o in opts)

    def test_no_autoscaling_suggestion_when_enabled(self):
        c = _comp("c1", ctype=ComponentType.APP_SERVER, replicas=3)
        c.autoscaling = AutoScalingConfig(enabled=True, min_replicas=1, max_replicas=5)
        g = _graph(c)
        opts = self.engine.identify_optimizations(g, [])
        assert not any("autoscaling" in o.recommendation.lower() for o in opts)

    def test_spot_instance_recommendation(self):
        c = _comp("c1", ctype=ComponentType.APP_SERVER)
        g = _graph(c)
        baselines = [
            CostBaseline(
                component_id="c1",
                avg_daily_cost=100.0,
                std_dev=70.0,
                p95_cost=200.0,
                min_cost=10.0,
                max_cost=300.0,
            )
        ]
        opts = self.engine.identify_optimizations(g, baselines)
        assert any("spot" in o.recommendation.lower() for o in opts)

    def test_orphaned_resource(self):
        c1 = _comp("c1")
        c2 = _comp("c2")
        g = _graph(c1, c2)
        g.add_dependency(Dependency(source_id="c1", target_id="c2"))
        c3 = _comp("c3")
        g.add_component(c3)
        opts = self.engine.identify_optimizations(g, [])
        assert any(
            "Orphaned" in o.recommendation and o.component_id == "c3"
            for o in opts
        )

    def test_external_api_skips_underutil(self):
        c = _comp("c1", ctype=ComponentType.EXTERNAL_API)
        g = _graph(c)
        opts = self.engine.identify_optimizations(g, [])
        assert not any("Right-size" in o.recommendation for o in opts)

    def test_savings_percent_positive(self):
        c = _comp("c1", replicas=5)
        g = _graph(c)
        opts = self.engine.identify_optimizations(g, [])
        for o in opts:
            assert o.savings_percent >= 0.0


# ---------------------------------------------------------------------------
# Engine: classify_anomaly_root_cause
# ---------------------------------------------------------------------------


class TestClassifyAnomalyRootCause:
    def setup_method(self):
        self.engine = CostAnomalyDetectorEngine()

    def _anomaly(self, cid="c1", atype=AnomalyType.SPIKE, dev=50.0):
        return CostAnomaly(
            anomaly_type=atype,
            severity=AnomalySeverity.MEDIUM,
            detection_method=DetectionMethod.Z_SCORE,
            component_id=cid,
            expected_cost=100.0,
            actual_cost=150.0,
            deviation_percent=dev,
        )

    def test_unknown_component(self):
        g = InfraGraph()
        result = self.engine.classify_anomaly_root_cause(self._anomaly("x"), g)
        assert "Unknown" in result

    def test_autoscaling_event(self):
        c = _comp("c1")
        c.autoscaling = AutoScalingConfig(enabled=True, max_replicas=10)
        g = _graph(c)
        result = self.engine.classify_anomaly_root_cause(self._anomaly(), g)
        assert "Auto-scaling" in result

    def test_over_provisioned(self):
        c = _comp("c1", replicas=5)
        g = _graph(c)
        a = self._anomaly(dev=60.0)
        result = self.engine.classify_anomaly_root_cause(a, g)
        assert "Over-provisioned" in result

    def test_resource_leak(self):
        c = _comp("c1")
        c.operational_profile = OperationalProfile(
            degradation=DegradationConfig(memory_leak_mb_per_hour=10.0)
        )
        g = _graph(c)
        a = self._anomaly(dev=150.0)
        result = self.engine.classify_anomaly_root_cause(a, g)
        assert "leak" in result.lower()

    def test_external_api_pricing(self):
        c = _comp("c1", ctype=ComponentType.EXTERNAL_API)
        g = _graph(c)
        result = self.engine.classify_anomaly_root_cause(self._anomaly(), g)
        assert "pricing" in result.lower()

    def test_orphaned_resource_classification(self):
        c1 = _comp("c1")
        c2 = _comp("c2")
        g = _graph(c1, c2)
        result = self.engine.classify_anomaly_root_cause(self._anomaly("c1"), g)
        assert "Orphaned" in result

    def test_generic_spike_label(self):
        c1 = _comp("c1")
        c2 = _comp("c2")
        g = _graph(c1, c2)
        g.add_dependency(Dependency(source_id="c1", target_id="c2"))
        a = self._anomaly(dev=30.0)
        result = self.engine.classify_anomaly_root_cause(a, g)
        assert "spike" in result.lower() or "c1" in result

    def test_drop_label(self):
        c = _comp("c1")
        c2 = _comp("c2")
        g = _graph(c, c2)
        g.add_dependency(Dependency(source_id="c1", target_id="c2"))
        a = self._anomaly(atype=AnomalyType.DROP, dev=30.0)
        result = self.engine.classify_anomaly_root_cause(a, g)
        assert "drop" in result.lower() or "c1" in result


# ---------------------------------------------------------------------------
# Engine: detect_anomalies (full pipeline)
# ---------------------------------------------------------------------------


class TestDetectAnomaliesPipeline:
    def setup_method(self):
        self.engine = CostAnomalyDetectorEngine()

    def test_empty_data_returns_empty_report(self):
        g = _graph(_comp("c1"))
        report = self.engine.detect_anomalies(g, [])
        assert isinstance(report, CostAnomalyReport)
        assert report.anomalies == []
        assert report.timestamp != ""

    def test_report_has_timestamp(self):
        g = _graph(_comp("c1"))
        report = self.engine.detect_anomalies(g, [_dp("c1", 100.0)])
        assert report.timestamp != ""

    def test_normal_data_no_anomalies(self):
        g = _graph(_comp("c1"))
        data = [_dp("c1", 100.0 + i * 0.1) for i in range(20)]
        report = self.engine.detect_anomalies(g, data)
        assert len(report.anomalies) == 0

    def test_spike_data_produces_anomalies(self):
        g = _graph(_comp("c1"))
        data = [_dp("c1", 100.0) for _ in range(20)]
        data.append(_dp("c1", 1000.0))
        report = self.engine.detect_anomalies(g, data)
        assert len(report.anomalies) >= 1

    def test_total_spend_calculated(self):
        g = _graph(_comp("c1"))
        data = [_dp("c1", 100.0) for _ in range(5)]
        report = self.engine.detect_anomalies(g, data)
        assert report.total_spend == 500.0

    def test_sensitivity_high_fewer_anomalies(self):
        g = _graph(_comp("c1"))
        data = [_dp("c1", 100.0) for _ in range(20)]
        data.append(_dp("c1", 250.0))
        low_sens = self.engine.detect_anomalies(g, data, sensitivity=0.5)
        high_sens = self.engine.detect_anomalies(g, data, sensitivity=5.0)
        assert len(low_sens.anomalies) >= len(high_sens.anomalies)

    def test_deduplication(self):
        g = _graph(_comp("c1"))
        data = [_dp("c1", 100.0) for _ in range(20)]
        data.append(_dp("c1", 1000.0))
        report = self.engine.detect_anomalies(g, data)
        keys = [(a.component_id, a.anomaly_type) for a in report.anomalies]
        assert len(keys) == len(set(keys))

    def test_anomaly_spend_tracks_flagged_components(self):
        g = _graph(_comp("c1"), _comp("c2"))
        data = [_dp("c1", 100.0) for _ in range(20)]
        data.append(_dp("c1", 1000.0))
        data.extend([_dp("c2", 50.0) for _ in range(20)])
        report = self.engine.detect_anomalies(g, data)
        if report.anomalies:
            assert report.anomaly_spend > 0.0

    def test_optimization_potential_included(self):
        c = _comp("c1", replicas=6)
        g = _graph(c)
        data = [_dp("c1", 100.0) for _ in range(5)]
        report = self.engine.detect_anomalies(g, data)
        assert report.optimization_potential_usd >= 0.0

    def test_baselines_in_report(self):
        g = _graph(_comp("c1"))
        data = [_dp("c1", 100.0) for _ in range(5)]
        report = self.engine.detect_anomalies(g, data)
        assert len(report.baselines) == 1


# ---------------------------------------------------------------------------
# Edge cases & boundary conditions
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def setup_method(self):
        self.engine = CostAnomalyDetectorEngine()

    def test_zero_cost_data(self):
        g = _graph(_comp("c1"))
        data = [_dp("c1", 0.0) for _ in range(10)]
        report = self.engine.detect_anomalies(g, data)
        assert report.total_spend == 0.0

    def test_single_data_point(self):
        g = _graph(_comp("c1"))
        data = [_dp("c1", 100.0)]
        report = self.engine.detect_anomalies(g, data)
        assert len(report.baselines) == 1

    def test_negative_costs_handled(self):
        data = [_dp("c1", -10.0), _dp("c1", 100.0), _dp("c1", 200.0)]
        baselines = self.engine.compute_baselines(data)
        assert len(baselines) == 1

    def test_very_large_costs(self):
        data = [_dp("c1", 1e12) for _ in range(5)]
        baselines = self.engine.compute_baselines(data)
        assert baselines[0].avg_daily_cost == 1e12

    def test_many_components(self):
        comps = [_comp(f"c{i}") for i in range(50)]
        g = _graph(*comps)
        data = []
        for i in range(50):
            data.extend([_dp(f"c{i}", 100.0) for _ in range(5)])
        report = self.engine.detect_anomalies(g, data)
        assert len(report.baselines) == 50

    def test_mixed_categories(self):
        data = [
            _dp("c1", 100.0, category="compute"),
            _dp("c1", 110.0, category="storage"),
            _dp("c1", 105.0, category="network"),
        ]
        baselines = self.engine.compute_baselines(data)
        assert len(baselines) == 1

    def test_graph_with_dependencies(self):
        c1 = _comp("c1")
        c2 = _comp("c2")
        g = _graph(c1, c2)
        g.add_dependency(Dependency(source_id="c1", target_id="c2"))
        data = [_dp("c1", 100.0) for _ in range(10)]
        data.append(_dp("c1", 1000.0))
        report = self.engine.detect_anomalies(g, data)
        assert isinstance(report, CostAnomalyReport)

    def test_component_not_in_graph(self):
        g = _graph(_comp("c1"))
        data = [_dp("c2", 100.0) for _ in range(10)]
        data.append(_dp("c2", 1000.0))
        report = self.engine.detect_anomalies(g, data)
        for a in report.anomalies:
            assert a.component_id == "c2"

    def test_iqr_all_same_values(self):
        data = [_dp("c1", 50.0) for _ in range(20)]
        anomalies = self.engine.detect_by_iqr(data)
        assert anomalies == []

    def test_moving_average_window_larger_than_data(self):
        data = [_dp("c1", 100.0), _dp("c1", 200.0)]
        anomalies = self.engine.detect_by_moving_average(data, window=10)
        assert anomalies == []

    def test_zscore_two_points(self):
        data = [_dp("c1", 100.0), _dp("c1", 200.0)]
        anomalies = self.engine.detect_by_zscore(data)
        assert isinstance(anomalies, list)

    def test_moving_average_with_zero_costs(self):
        data = [_dp("c1", 0.0) for _ in range(5)]
        data.append(_dp("c1", 100.0))
        anomalies = self.engine.detect_by_moving_average(data, window=3)
        assert isinstance(anomalies, list)

    def test_optimization_single_component_no_orphan(self):
        c = _comp("c1")
        g = _graph(c)
        opts = self.engine.identify_optimizations(g, [])
        assert not any("Orphaned" in o.recommendation for o in opts)

    def test_severity_boundary_20(self):
        assert _severity_from_deviation(20.0) == AnomalySeverity.LOW

    def test_severity_boundary_50(self):
        assert _severity_from_deviation(50.0) == AnomalySeverity.MEDIUM

    def test_severity_boundary_100(self):
        assert _severity_from_deviation(100.0) == AnomalySeverity.HIGH

    def test_severity_boundary_200(self):
        assert _severity_from_deviation(200.0) == AnomalySeverity.CRITICAL

    def test_quantile_two_values(self):
        assert _quantile([1.0, 3.0], 0.5) == 2.0

    def test_quantile_boundary_zero(self):
        assert _quantile([5.0, 10.0, 15.0], 0.0) == 5.0

    def test_quantile_boundary_one(self):
        assert _quantile([5.0, 10.0, 15.0], 1.0) == 15.0
