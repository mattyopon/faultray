"""Tests for the Observability Cost Optimizer."""

from __future__ import annotations

import math

import pytest

from faultray.model.components import Component, ComponentType, Dependency, HealthStatus
from faultray.model.graph import InfraGraph
from faultray.simulator.observability_cost import (
    CostGrowthDataPoint,
    CostGrowthProjection,
    CostOptimization,
    DetectionCoverage,
    ObservabilityCostEngine,
    ObservabilityCostReport,
    ObservabilityConfig,
    ObservabilityPillar,
    OptimizationAction,
    PillarCoverage,
    RedundancyFinding,
    RetentionRecommendation,
    SamplingRecommendation,
    Vendor,
    VendorCostBreakdown,
    VendorCostComparison,
    _IDEAL_RETENTION,
    _MAX_RECOMMENDED_RETENTION,
    _PILLAR_DETECTION_WEIGHT,
    _RETENTION_COST_FACTOR_PER_30D,
    _VENDOR_COST_PER_UNIT,
    _detection_impact_for_sampling,
    _monthly_cost_for_config,
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
) -> Component:
    """Create a minimal component for testing."""
    return Component(id=cid, name=name, type=ctype, replicas=replicas, health=health)


def _graph(*components: Component, deps: list[tuple[str, str]] | None = None) -> InfraGraph:
    """Build an InfraGraph from components and optional dependency edges."""
    g = InfraGraph()
    for c in components:
        g.add_component(c)
    for src, tgt in (deps or []):
        g.add_dependency(Dependency(source_id=src, target_id=tgt))
    return g


def _cfg(
    pillar: ObservabilityPillar = ObservabilityPillar.LOGS,
    vendor: Vendor = Vendor.DATADOG,
    volume: float = 10.0,
    retention: int = 30,
    cost: float = 2.0,
    sampling: float = 1.0,
    compression: float = 1.0,
) -> ObservabilityConfig:
    """Shorthand for creating an ObservabilityConfig."""
    return ObservabilityConfig(
        pillar=pillar,
        vendor=vendor,
        volume_per_day=volume,
        retention_days=retention,
        cost_per_unit=cost,
        sampling_rate=sampling,
        compression_ratio=compression,
    )


def _engine() -> ObservabilityCostEngine:
    return ObservabilityCostEngine()


# ===================================================================
# ObservabilityPillar enum tests
# ===================================================================


class TestObservabilityPillar:
    def test_all_values(self):
        assert set(ObservabilityPillar) == {
            ObservabilityPillar.METRICS,
            ObservabilityPillar.LOGS,
            ObservabilityPillar.TRACES,
            ObservabilityPillar.PROFILING,
            ObservabilityPillar.RUM,
            ObservabilityPillar.SYNTHETICS,
        }

    def test_string_values(self):
        assert ObservabilityPillar.METRICS.value == "metrics"
        assert ObservabilityPillar.LOGS.value == "logs"
        assert ObservabilityPillar.TRACES.value == "traces"
        assert ObservabilityPillar.PROFILING.value == "profiling"
        assert ObservabilityPillar.RUM.value == "rum"
        assert ObservabilityPillar.SYNTHETICS.value == "synthetics"

    def test_is_str(self):
        assert isinstance(ObservabilityPillar.METRICS, str)

    def test_from_value(self):
        assert ObservabilityPillar("logs") == ObservabilityPillar.LOGS

    def test_count(self):
        assert len(ObservabilityPillar) == 6


# ===================================================================
# Vendor enum tests
# ===================================================================


class TestVendor:
    def test_all_values(self):
        assert set(Vendor) == {
            Vendor.DATADOG,
            Vendor.NEW_RELIC,
            Vendor.SPLUNK,
            Vendor.GRAFANA_CLOUD,
            Vendor.ELASTIC,
            Vendor.AWS_CLOUDWATCH,
            Vendor.PROMETHEUS_SELF_HOSTED,
            Vendor.CUSTOM,
        }

    def test_string_values(self):
        assert Vendor.DATADOG.value == "datadog"
        assert Vendor.NEW_RELIC.value == "new_relic"
        assert Vendor.SPLUNK.value == "splunk"
        assert Vendor.GRAFANA_CLOUD.value == "grafana_cloud"
        assert Vendor.ELASTIC.value == "elastic"
        assert Vendor.AWS_CLOUDWATCH.value == "aws_cloudwatch"
        assert Vendor.PROMETHEUS_SELF_HOSTED.value == "prometheus_self_hosted"
        assert Vendor.CUSTOM.value == "custom"

    def test_is_str(self):
        assert isinstance(Vendor.DATADOG, str)

    def test_count(self):
        assert len(Vendor) == 8


# ===================================================================
# ObservabilityConfig model tests
# ===================================================================


class TestObservabilityConfig:
    def test_basic_creation(self):
        cfg = _cfg()
        assert cfg.pillar == ObservabilityPillar.LOGS
        assert cfg.vendor == Vendor.DATADOG
        assert cfg.volume_per_day == 10.0
        assert cfg.retention_days == 30
        assert cfg.cost_per_unit == 2.0
        assert cfg.sampling_rate == 1.0
        assert cfg.compression_ratio == 1.0

    def test_sampling_default(self):
        cfg = ObservabilityConfig(
            pillar=ObservabilityPillar.METRICS,
            vendor=Vendor.NEW_RELIC,
            volume_per_day=5.0,
            retention_days=90,
            cost_per_unit=7.0,
        )
        assert cfg.sampling_rate == 1.0
        assert cfg.compression_ratio == 1.0

    def test_sampling_min_max(self):
        cfg = _cfg(sampling=0.0)
        assert cfg.sampling_rate == 0.0
        cfg2 = _cfg(sampling=1.0)
        assert cfg2.sampling_rate == 1.0

    def test_sampling_invalid_above_1(self):
        with pytest.raises(Exception):
            _cfg(sampling=1.5)

    def test_sampling_invalid_below_0(self):
        with pytest.raises(Exception):
            _cfg(sampling=-0.1)

    def test_compression_zero_invalid(self):
        with pytest.raises(Exception):
            _cfg(compression=0.0)

    def test_compression_negative_invalid(self):
        with pytest.raises(Exception):
            _cfg(compression=-1.0)

    def test_all_pillars(self):
        for pillar in ObservabilityPillar:
            cfg = _cfg(pillar=pillar)
            assert cfg.pillar == pillar

    def test_all_vendors(self):
        for vendor in Vendor:
            cfg = _cfg(vendor=vendor)
            assert cfg.vendor == vendor


# ===================================================================
# OptimizationAction model tests
# ===================================================================


class TestOptimizationAction:
    def test_creation(self):
        a = OptimizationAction(
            action="Reduce sampling",
            pillar=ObservabilityPillar.LOGS,
            monthly_savings=100.0,
            detection_impact="low",
            implementation_effort="medium",
        )
        assert a.action == "Reduce sampling"
        assert a.monthly_savings == 100.0
        assert a.detection_impact == "low"
        assert a.implementation_effort == "medium"


# ===================================================================
# CostOptimization model tests
# ===================================================================


class TestCostOptimization:
    def test_creation(self):
        co = CostOptimization(
            current_monthly_cost=1000.0,
            optimized_monthly_cost=700.0,
            savings_percent=30.0,
            risk_of_blind_spots=25.0,
        )
        assert co.current_monthly_cost == 1000.0
        assert co.optimized_monthly_cost == 700.0
        assert co.savings_percent == 30.0
        assert co.risk_of_blind_spots == 25.0
        assert co.optimizations == []
        assert co.recommendations == []


# ===================================================================
# SamplingRecommendation model tests
# ===================================================================


class TestSamplingRecommendation:
    def test_creation(self):
        sr = SamplingRecommendation(
            pillar=ObservabilityPillar.TRACES,
            current_sampling_rate=1.0,
            recommended_sampling_rate=0.5,
            estimated_monthly_savings=50.0,
            detection_impact="medium",
        )
        assert sr.recommended_sampling_rate == 0.5
        assert sr.estimated_monthly_savings == 50.0


# ===================================================================
# RedundancyFinding model tests
# ===================================================================


class TestRedundancyFinding:
    def test_creation(self):
        rf = RedundancyFinding(
            pillars=[ObservabilityPillar.LOGS],
            vendors=[Vendor.DATADOG, Vendor.SPLUNK],
            description="dup",
            monthly_waste=200.0,
            recommendation="consolidate",
        )
        assert len(rf.vendors) == 2
        assert rf.monthly_waste == 200.0


# ===================================================================
# VendorCostBreakdown / VendorCostComparison model tests
# ===================================================================


class TestVendorCostModels:
    def test_breakdown(self):
        b = VendorCostBreakdown(vendor=Vendor.DATADOG, monthly_cost=500.0)
        assert b.vendor == Vendor.DATADOG
        assert b.per_pillar == {}

    def test_comparison_defaults(self):
        vc = VendorCostComparison()
        assert vc.cheapest_vendor is None
        assert vc.cheapest_monthly_cost == 0.0
        assert vc.potential_savings == 0.0
        assert vc.recommendations == []


# ===================================================================
# PillarCoverage / DetectionCoverage model tests
# ===================================================================


class TestCoverageModels:
    def test_pillar_coverage(self):
        pc = PillarCoverage(
            pillar=ObservabilityPillar.METRICS,
            covered=True,
            sampling_rate=1.0,
            retention_days=90,
            coverage_score=95.0,
        )
        assert pc.covered is True
        assert pc.coverage_score == 95.0

    def test_detection_coverage_defaults(self):
        dc = DetectionCoverage(overall_score=50.0)
        assert dc.per_pillar == []
        assert dc.gaps == []
        assert dc.recommendations == []


# ===================================================================
# RetentionRecommendation model tests
# ===================================================================


class TestRetentionRecommendation:
    def test_creation(self):
        rr = RetentionRecommendation(
            pillar=ObservabilityPillar.LOGS,
            current_retention_days=365,
            recommended_retention_days=90,
            reason="too long",
            monthly_savings=100.0,
        )
        assert rr.recommended_retention_days == 90


# ===================================================================
# CostGrowthDataPoint / CostGrowthProjection model tests
# ===================================================================


class TestGrowthModels:
    def test_data_point(self):
        dp = CostGrowthDataPoint(month=1, monthly_cost=100.0, cumulative_cost=100.0)
        assert dp.month == 1

    def test_projection_defaults(self):
        cp = CostGrowthProjection(
            initial_monthly_cost=100.0,
            final_monthly_cost=200.0,
            total_cost=1800.0,
            growth_rate=0.05,
            months=12,
        )
        assert cp.data_points == []
        assert cp.recommendations == []


# ===================================================================
# ObservabilityCostReport model tests
# ===================================================================


class TestObservabilityCostReport:
    def test_creation(self):
        r = ObservabilityCostReport(
            total_monthly_cost=1000.0,
            optimization=CostOptimization(
                current_monthly_cost=1000.0,
                optimized_monthly_cost=700.0,
                savings_percent=30.0,
                risk_of_blind_spots=10.0,
            ),
            component_count=5,
            config_count=3,
        )
        assert r.total_monthly_cost == 1000.0
        assert r.component_count == 5
        assert r.per_pillar_cost == {}
        assert r.per_vendor_cost == {}


# ===================================================================
# _monthly_cost_for_config helper tests
# ===================================================================


class TestMonthlyCostForConfig:
    def test_basic_cost(self):
        cfg = _cfg(volume=10.0, cost=2.0, retention=30, sampling=1.0, compression=1.0)
        # 10 * 2 * 1 / 1 * 30 = 600
        assert _monthly_cost_for_config(cfg) == pytest.approx(600.0)

    def test_sampling_halves_cost(self):
        full = _cfg(sampling=1.0)
        half = _cfg(sampling=0.5)
        assert _monthly_cost_for_config(half) == pytest.approx(
            _monthly_cost_for_config(full) / 2.0
        )

    def test_compression_reduces_cost(self):
        no_comp = _cfg(compression=1.0)
        comp = _cfg(compression=2.0)
        assert _monthly_cost_for_config(comp) == pytest.approx(
            _monthly_cost_for_config(no_comp) / 2.0
        )

    def test_retention_surcharge_60d(self):
        cfg30 = _cfg(retention=30)
        cfg60 = _cfg(retention=60)
        base = _monthly_cost_for_config(cfg30)
        # 60 days = 1 extra window = 1.0 + 1.0 * 0.15 = 1.15
        assert _monthly_cost_for_config(cfg60) == pytest.approx(base * 1.15)

    def test_retention_surcharge_90d(self):
        cfg30 = _cfg(retention=30)
        cfg90 = _cfg(retention=90)
        base = _monthly_cost_for_config(cfg30)
        # 90 days = 2 extra windows = 1.0 + 2.0 * 0.15 = 1.30
        assert _monthly_cost_for_config(cfg90) == pytest.approx(base * 1.30)

    def test_retention_under_30d(self):
        cfg = _cfg(retention=7)
        # No surcharge — extra_windows = max(0, (7-30)/30) = 0
        base = 10.0 * 2.0 * 1.0 * 30.0  # = 600
        assert _monthly_cost_for_config(cfg) == pytest.approx(base)

    def test_zero_volume(self):
        cfg = _cfg(volume=0.0)
        assert _monthly_cost_for_config(cfg) == 0.0

    def test_zero_sampling(self):
        cfg = _cfg(sampling=0.0)
        assert _monthly_cost_for_config(cfg) == 0.0

    def test_high_compression(self):
        cfg = _cfg(compression=10.0)
        expected = 10.0 * 2.0 * 1.0 / 10.0 * 30.0
        assert _monthly_cost_for_config(cfg) == pytest.approx(expected)


# ===================================================================
# _detection_impact_for_sampling helper tests
# ===================================================================


class TestDetectionImpact:
    def test_same_rate(self):
        assert _detection_impact_for_sampling(1.0, 1.0) == "none"

    def test_increase(self):
        assert _detection_impact_for_sampling(0.5, 1.0) == "none"

    def test_low_reduction(self):
        # 0.85 / 1.0 = 0.85 >= 0.8 => low
        assert _detection_impact_for_sampling(1.0, 0.85) == "low"

    def test_medium_reduction(self):
        # 0.6 / 1.0 = 0.6 >= 0.5 => medium
        assert _detection_impact_for_sampling(1.0, 0.6) == "medium"

    def test_high_reduction(self):
        # 0.3 / 1.0 = 0.3 < 0.5 => high
        assert _detection_impact_for_sampling(1.0, 0.3) == "high"

    def test_zero_current(self):
        # current=0 => ratio = 1.0 since proposed / current guard => "none" for increase
        assert _detection_impact_for_sampling(0.0, 0.0) == "none"

    def test_boundary_80(self):
        assert _detection_impact_for_sampling(1.0, 0.8) == "low"

    def test_boundary_50(self):
        assert _detection_impact_for_sampling(1.0, 0.5) == "medium"

    def test_boundary_below_50(self):
        assert _detection_impact_for_sampling(1.0, 0.49) == "high"


# ===================================================================
# Constants tests
# ===================================================================


class TestConstants:
    def test_vendor_cost_covers_all_vendors(self):
        for v in Vendor:
            assert v in _VENDOR_COST_PER_UNIT

    def test_vendor_cost_covers_all_pillars(self):
        for v in Vendor:
            for p in ObservabilityPillar:
                assert p in _VENDOR_COST_PER_UNIT[v]

    def test_pillar_detection_weight_covers_all(self):
        for p in ObservabilityPillar:
            assert p in _PILLAR_DETECTION_WEIGHT

    def test_ideal_retention_covers_all(self):
        for p in ObservabilityPillar:
            assert p in _IDEAL_RETENTION

    def test_max_retention_covers_all(self):
        for p in ObservabilityPillar:
            assert p in _MAX_RECOMMENDED_RETENTION

    def test_retention_factor_positive(self):
        assert _RETENTION_COST_FACTOR_PER_30D > 0


# ===================================================================
# ObservabilityCostEngine.analyze_cost tests
# ===================================================================


class TestAnalyzeCost:
    def test_empty_configs(self):
        e = _engine()
        g = _graph()
        report = e.analyze_cost(g, [])
        assert report.total_monthly_cost == 0.0
        assert report.per_pillar_cost == {}
        assert report.per_vendor_cost == {}
        assert report.config_count == 0
        assert report.component_count == 0

    def test_single_config(self):
        e = _engine()
        g = _graph(_comp("c1", "App"))
        cfgs = [_cfg(pillar=ObservabilityPillar.LOGS, vendor=Vendor.DATADOG)]
        report = e.analyze_cost(g, cfgs)
        assert report.total_monthly_cost > 0
        assert "logs" in report.per_pillar_cost
        assert "datadog" in report.per_vendor_cost
        assert report.component_count == 1
        assert report.config_count == 1

    def test_multiple_pillars(self):
        e = _engine()
        g = _graph()
        cfgs = [
            _cfg(pillar=ObservabilityPillar.LOGS),
            _cfg(pillar=ObservabilityPillar.METRICS),
        ]
        report = e.analyze_cost(g, cfgs)
        assert len(report.per_pillar_cost) == 2
        assert "logs" in report.per_pillar_cost
        assert "metrics" in report.per_pillar_cost

    def test_multiple_vendors(self):
        e = _engine()
        g = _graph()
        cfgs = [
            _cfg(vendor=Vendor.DATADOG),
            _cfg(vendor=Vendor.SPLUNK),
        ]
        report = e.analyze_cost(g, cfgs)
        assert len(report.per_vendor_cost) == 2

    def test_total_equals_sum_of_pillars(self):
        e = _engine()
        g = _graph()
        cfgs = [
            _cfg(pillar=ObservabilityPillar.LOGS, volume=10.0),
            _cfg(pillar=ObservabilityPillar.METRICS, volume=5.0, cost=3.0),
            _cfg(pillar=ObservabilityPillar.TRACES, volume=2.0, cost=5.0),
        ]
        report = e.analyze_cost(g, cfgs)
        assert report.total_monthly_cost == pytest.approx(
            sum(report.per_pillar_cost.values()), rel=1e-2
        )

    def test_graph_component_count(self):
        e = _engine()
        g = _graph(
            _comp("c1", "A"),
            _comp("c2", "B"),
            _comp("c3", "C"),
        )
        report = e.analyze_cost(g, [_cfg()])
        assert report.component_count == 3

    def test_optimization_included(self):
        e = _engine()
        g = _graph()
        cfgs = [_cfg(volume=10.0, sampling=1.0)]
        report = e.analyze_cost(g, cfgs)
        assert report.optimization is not None
        assert report.optimization.current_monthly_cost == report.total_monthly_cost

    def test_same_pillar_costs_aggregate(self):
        e = _engine()
        g = _graph()
        c1 = _cfg(pillar=ObservabilityPillar.LOGS, volume=5.0, cost=2.0)
        c2 = _cfg(pillar=ObservabilityPillar.LOGS, volume=5.0, cost=2.0)
        report = e.analyze_cost(g, [c1, c2])
        expected = _monthly_cost_for_config(c1) + _monthly_cost_for_config(c2)
        assert report.per_pillar_cost["logs"] == pytest.approx(expected, rel=1e-2)


# ===================================================================
# ObservabilityCostEngine.optimize_sampling tests
# ===================================================================


class TestOptimizeSampling:
    def test_empty_configs(self):
        e = _engine()
        result = e.optimize_sampling([], budget=1000.0)
        assert result == []

    def test_within_budget(self):
        e = _engine()
        cfgs = [_cfg(volume=1.0, cost=1.0)]  # cost = 30/month
        recs = e.optimize_sampling(cfgs, budget=1000.0)
        assert len(recs) == 1
        assert recs[0].recommended_sampling_rate == recs[0].current_sampling_rate
        assert recs[0].estimated_monthly_savings == 0.0
        assert recs[0].detection_impact == "none"

    def test_over_budget_reduces(self):
        e = _engine()
        cfgs = [_cfg(volume=100.0, cost=10.0)]  # cost = 30000/month
        recs = e.optimize_sampling(cfgs, budget=1000.0)
        assert len(recs) == 1
        assert recs[0].recommended_sampling_rate < recs[0].current_sampling_rate
        assert recs[0].estimated_monthly_savings > 0

    def test_multiple_configs_over_budget(self):
        e = _engine()
        cfgs = [
            _cfg(pillar=ObservabilityPillar.LOGS, volume=50.0, cost=5.0),
            _cfg(pillar=ObservabilityPillar.METRICS, volume=50.0, cost=5.0),
        ]
        recs = e.optimize_sampling(cfgs, budget=100.0)
        assert len(recs) == 2
        # At least some reduction must happen to meet budget
        total_savings = sum(r.estimated_monthly_savings for r in recs)
        assert total_savings > 0

    def test_higher_weight_pillar_less_reduction(self):
        e = _engine()
        cfgs = [
            _cfg(pillar=ObservabilityPillar.METRICS, volume=100.0, cost=10.0),  # weight 1.0
            _cfg(pillar=ObservabilityPillar.RUM, volume=100.0, cost=10.0),  # weight 0.4
        ]
        recs = e.optimize_sampling(cfgs, budget=100.0)
        metrics_rec = [r for r in recs if r.pillar == ObservabilityPillar.METRICS][0]
        rum_rec = [r for r in recs if r.pillar == ObservabilityPillar.RUM][0]
        assert metrics_rec.recommended_sampling_rate >= rum_rec.recommended_sampling_rate

    def test_rate_never_below_0_01(self):
        e = _engine()
        cfgs = [_cfg(volume=1000.0, cost=100.0)]
        recs = e.optimize_sampling(cfgs, budget=0.01)
        assert recs[0].recommended_sampling_rate >= 0.01

    def test_exact_budget_match(self):
        e = _engine()
        cfgs = [_cfg(volume=1.0, cost=1.0)]
        cost = _monthly_cost_for_config(cfgs[0])
        recs = e.optimize_sampling(cfgs, budget=cost)
        assert recs[0].recommended_sampling_rate == recs[0].current_sampling_rate

    def test_zero_cost_configs(self):
        e = _engine()
        cfgs = [_cfg(volume=0.0)]
        recs = e.optimize_sampling(cfgs, budget=100.0)
        assert recs == []


# ===================================================================
# ObservabilityCostEngine.detect_redundant_telemetry tests
# ===================================================================


class TestDetectRedundantTelemetry:
    def test_no_configs(self):
        e = _engine()
        assert e.detect_redundant_telemetry([]) == []

    def test_no_redundancy(self):
        e = _engine()
        cfgs = [
            _cfg(pillar=ObservabilityPillar.LOGS, vendor=Vendor.DATADOG),
            _cfg(pillar=ObservabilityPillar.METRICS, vendor=Vendor.NEW_RELIC),
        ]
        assert e.detect_redundant_telemetry(cfgs) == []

    def test_multi_vendor_same_pillar(self):
        e = _engine()
        cfgs = [
            _cfg(pillar=ObservabilityPillar.LOGS, vendor=Vendor.DATADOG),
            _cfg(pillar=ObservabilityPillar.LOGS, vendor=Vendor.SPLUNK),
        ]
        findings = e.detect_redundant_telemetry(cfgs)
        assert len(findings) == 1
        assert findings[0].monthly_waste > 0
        assert ObservabilityPillar.LOGS in findings[0].pillars

    def test_duplicate_same_vendor(self):
        e = _engine()
        cfgs = [
            _cfg(pillar=ObservabilityPillar.LOGS, vendor=Vendor.DATADOG, volume=10.0),
            _cfg(pillar=ObservabilityPillar.LOGS, vendor=Vendor.DATADOG, volume=5.0),
        ]
        findings = e.detect_redundant_telemetry(cfgs)
        assert len(findings) == 1
        assert findings[0].vendors == [Vendor.DATADOG]

    def test_multiple_redundancies(self):
        e = _engine()
        cfgs = [
            _cfg(pillar=ObservabilityPillar.LOGS, vendor=Vendor.DATADOG),
            _cfg(pillar=ObservabilityPillar.LOGS, vendor=Vendor.SPLUNK),
            _cfg(pillar=ObservabilityPillar.METRICS, vendor=Vendor.NEW_RELIC),
            _cfg(pillar=ObservabilityPillar.METRICS, vendor=Vendor.ELASTIC),
        ]
        findings = e.detect_redundant_telemetry(cfgs)
        assert len(findings) == 2

    def test_single_config_no_redundancy(self):
        e = _engine()
        cfgs = [_cfg()]
        assert e.detect_redundant_telemetry(cfgs) == []

    def test_same_vendor_same_volume_streams(self):
        e = _engine()
        cfgs = [
            _cfg(pillar=ObservabilityPillar.TRACES, vendor=Vendor.DATADOG, volume=10.0),
            _cfg(pillar=ObservabilityPillar.TRACES, vendor=Vendor.DATADOG, volume=10.0),
        ]
        findings = e.detect_redundant_telemetry(cfgs)
        assert len(findings) == 1
        # When volumes are equal, the min is the same as max, so waste = total - max = cost
        assert findings[0].monthly_waste > 0

    def test_description_mentions_vendors(self):
        e = _engine()
        cfgs = [
            _cfg(pillar=ObservabilityPillar.LOGS, vendor=Vendor.DATADOG),
            _cfg(pillar=ObservabilityPillar.LOGS, vendor=Vendor.GRAFANA_CLOUD),
        ]
        findings = e.detect_redundant_telemetry(cfgs)
        assert len(findings) == 1
        assert "logs" in findings[0].description.lower()


# ===================================================================
# ObservabilityCostEngine.estimate_vendor_cost tests
# ===================================================================


class TestEstimateVendorCost:
    def test_empty_configs(self):
        e = _engine()
        result = e.estimate_vendor_cost([])
        assert result.current_vendors == []
        assert result.cheapest_vendor is not None  # smallest vendor by cost table
        assert result.potential_savings == 0.0

    def test_single_vendor(self):
        e = _engine()
        cfgs = [_cfg(vendor=Vendor.SPLUNK)]
        result = e.estimate_vendor_cost(cfgs)
        assert len(result.current_vendors) == 1
        assert result.current_vendors[0].vendor == Vendor.SPLUNK

    def test_cheapest_vendor_found(self):
        e = _engine()
        cfgs = [_cfg(vendor=Vendor.SPLUNK, volume=10.0, cost=3.0)]
        result = e.estimate_vendor_cost(cfgs)
        assert result.cheapest_vendor is not None
        # Prometheus self-hosted should be cheapest
        assert result.cheapest_vendor == Vendor.PROMETHEUS_SELF_HOSTED

    def test_potential_savings_positive(self):
        e = _engine()
        cfgs = [
            _cfg(vendor=Vendor.SPLUNK, volume=50.0, cost=10.0),
        ]
        result = e.estimate_vendor_cost(cfgs)
        assert result.potential_savings >= 0.0

    def test_multi_vendor_recommendation(self):
        e = _engine()
        cfgs = [
            _cfg(vendor=Vendor.DATADOG, pillar=ObservabilityPillar.LOGS),
            _cfg(vendor=Vendor.SPLUNK, pillar=ObservabilityPillar.METRICS),
        ]
        result = e.estimate_vendor_cost(cfgs)
        assert len(result.current_vendors) == 2
        assert any("multiple" in r.lower() for r in result.recommendations)

    def test_per_pillar_breakdown(self):
        e = _engine()
        cfgs = [
            _cfg(vendor=Vendor.DATADOG, pillar=ObservabilityPillar.LOGS),
            _cfg(vendor=Vendor.DATADOG, pillar=ObservabilityPillar.METRICS),
        ]
        result = e.estimate_vendor_cost(cfgs)
        assert len(result.current_vendors) == 1
        dd = result.current_vendors[0]
        assert "logs" in dd.per_pillar
        assert "metrics" in dd.per_pillar

    def test_cheapest_cost_not_negative(self):
        e = _engine()
        cfgs = [_cfg()]
        result = e.estimate_vendor_cost(cfgs)
        assert result.cheapest_monthly_cost >= 0.0

    def test_savings_recommendation_text(self):
        e = _engine()
        cfgs = [_cfg(vendor=Vendor.SPLUNK, volume=100.0, cost=10.0)]
        result = e.estimate_vendor_cost(cfgs)
        if result.potential_savings > 0:
            assert any("save" in r.lower() for r in result.recommendations)


# ===================================================================
# ObservabilityCostEngine.calculate_detection_coverage tests
# ===================================================================


class TestCalculateDetectionCoverage:
    def test_empty_configs(self):
        e = _engine()
        g = _graph()
        result = e.calculate_detection_coverage(g, [])
        assert result.overall_score == 0.0
        assert len(result.per_pillar) == len(ObservabilityPillar)
        assert len(result.gaps) == len(ObservabilityPillar)

    def test_full_coverage_all_pillars(self):
        e = _engine()
        g = _graph()
        cfgs = [
            _cfg(pillar=p, retention=_IDEAL_RETENTION[p], sampling=1.0)
            for p in ObservabilityPillar
        ]
        result = e.calculate_detection_coverage(g, cfgs)
        assert result.overall_score == pytest.approx(100.0, rel=0.1)
        assert len(result.gaps) == 0

    def test_partial_coverage(self):
        e = _engine()
        g = _graph()
        cfgs = [_cfg(pillar=ObservabilityPillar.LOGS, retention=30, sampling=1.0)]
        result = e.calculate_detection_coverage(g, cfgs)
        assert 0 < result.overall_score < 100

    def test_low_sampling_flagged(self):
        e = _engine()
        g = _graph()
        cfgs = [_cfg(pillar=ObservabilityPillar.LOGS, sampling=0.1)]
        result = e.calculate_detection_coverage(g, cfgs)
        assert any("sampling" in gap.lower() for gap in result.gaps)

    def test_low_retention_flagged(self):
        e = _engine()
        g = _graph()
        cfgs = [_cfg(pillar=ObservabilityPillar.METRICS, retention=7)]
        result = e.calculate_detection_coverage(g, cfgs)
        assert any("retention" in gap.lower() for gap in result.gaps)

    def test_missing_pillar_gap(self):
        e = _engine()
        g = _graph()
        cfgs = [_cfg(pillar=ObservabilityPillar.LOGS)]
        result = e.calculate_detection_coverage(g, cfgs)
        uncovered_names = [
            pc.pillar.value for pc in result.per_pillar if not pc.covered
        ]
        assert "metrics" in uncovered_names
        assert "traces" in uncovered_names

    def test_coverage_score_components(self):
        e = _engine()
        g = _graph()
        # 50% sampling * 50 + retention adequate (30d >= 30d for logs) = 25 + 50 = 75
        cfgs = [_cfg(pillar=ObservabilityPillar.LOGS, sampling=0.5, retention=30)]
        result = e.calculate_detection_coverage(g, cfgs)
        logs_pc = [pc for pc in result.per_pillar if pc.pillar == ObservabilityPillar.LOGS][0]
        assert logs_pc.coverage_score == pytest.approx(75.0, rel=0.1)

    def test_multiple_configs_same_pillar_uses_max(self):
        e = _engine()
        g = _graph()
        cfgs = [
            _cfg(pillar=ObservabilityPillar.LOGS, sampling=0.3, retention=7),
            _cfg(pillar=ObservabilityPillar.LOGS, sampling=0.8, retention=60),
        ]
        result = e.calculate_detection_coverage(g, cfgs)
        logs_pc = [pc for pc in result.per_pillar if pc.pillar == ObservabilityPillar.LOGS][0]
        assert logs_pc.sampling_rate == 0.8
        assert logs_pc.retention_days == 60

    def test_all_pillars_in_output(self):
        e = _engine()
        g = _graph()
        result = e.calculate_detection_coverage(g, [_cfg()])
        pillars_in_output = {pc.pillar for pc in result.per_pillar}
        assert pillars_in_output == set(ObservabilityPillar)

    def test_recommendations_for_gaps(self):
        e = _engine()
        g = _graph()
        result = e.calculate_detection_coverage(g, [])
        for p in ObservabilityPillar:
            assert any(p.value in r.lower() for r in result.recommendations)


# ===================================================================
# ObservabilityCostEngine.recommend_retention_policy tests
# ===================================================================


class TestRecommendRetentionPolicy:
    def test_empty_configs(self):
        e = _engine()
        assert e.recommend_retention_policy([]) == []

    def test_within_range(self):
        e = _engine()
        cfgs = [_cfg(pillar=ObservabilityPillar.LOGS, retention=30)]
        recs = e.recommend_retention_policy(cfgs)
        assert len(recs) == 1
        assert recs[0].recommended_retention_days == 30
        assert recs[0].monthly_savings == 0.0

    def test_over_max_recommended(self):
        e = _engine()
        # Max for logs = 90
        cfgs = [_cfg(pillar=ObservabilityPillar.LOGS, retention=365)]
        recs = e.recommend_retention_policy(cfgs)
        assert len(recs) == 1
        assert recs[0].recommended_retention_days == 90
        assert recs[0].monthly_savings > 0

    def test_under_min_recommended(self):
        e = _engine()
        # Ideal for metrics = 90
        cfgs = [_cfg(pillar=ObservabilityPillar.METRICS, retention=7)]
        recs = e.recommend_retention_policy(cfgs)
        assert len(recs) == 1
        assert recs[0].recommended_retention_days == 90
        # Negative savings (extra cost)
        assert recs[0].monthly_savings < 0

    def test_all_pillars_within_range(self):
        e = _engine()
        cfgs = [
            _cfg(pillar=p, retention=_IDEAL_RETENTION[p]) for p in ObservabilityPillar
        ]
        recs = e.recommend_retention_policy(cfgs)
        for r in recs:
            # All within range should have either 0 or match current
            assert r.recommended_retention_days == r.current_retention_days

    def test_multiple_configs(self):
        e = _engine()
        cfgs = [
            _cfg(pillar=ObservabilityPillar.LOGS, retention=365),
            _cfg(pillar=ObservabilityPillar.TRACES, retention=1),
        ]
        recs = e.recommend_retention_policy(cfgs)
        assert len(recs) == 2
        logs_rec = [r for r in recs if r.pillar == ObservabilityPillar.LOGS][0]
        traces_rec = [r for r in recs if r.pillar == ObservabilityPillar.TRACES][0]
        assert logs_rec.monthly_savings > 0
        assert traces_rec.monthly_savings <= 0

    def test_reason_text_for_over(self):
        e = _engine()
        cfgs = [_cfg(pillar=ObservabilityPillar.LOGS, retention=365)]
        recs = e.recommend_retention_policy(cfgs)
        assert "exceeds" in recs[0].reason.lower()

    def test_reason_text_for_under(self):
        e = _engine()
        cfgs = [_cfg(pillar=ObservabilityPillar.METRICS, retention=7)]
        recs = e.recommend_retention_policy(cfgs)
        assert "below" in recs[0].reason.lower()

    def test_reason_text_for_ok(self):
        e = _engine()
        cfgs = [_cfg(pillar=ObservabilityPillar.LOGS, retention=60)]
        recs = e.recommend_retention_policy(cfgs)
        assert "within" in recs[0].reason.lower()

    def test_profiling_short_retention(self):
        e = _engine()
        # Ideal for profiling = 7, max = 14
        cfgs = [_cfg(pillar=ObservabilityPillar.PROFILING, retention=3)]
        recs = e.recommend_retention_policy(cfgs)
        assert recs[0].recommended_retention_days == 7

    def test_profiling_long_retention(self):
        e = _engine()
        cfgs = [_cfg(pillar=ObservabilityPillar.PROFILING, retention=100)]
        recs = e.recommend_retention_policy(cfgs)
        assert recs[0].recommended_retention_days == 14
        assert recs[0].monthly_savings > 0


# ===================================================================
# ObservabilityCostEngine.simulate_cost_growth tests
# ===================================================================


class TestSimulateCostGrowth:
    def test_zero_growth(self):
        e = _engine()
        cfgs = [_cfg(volume=10.0, cost=2.0)]
        proj = e.simulate_cost_growth(cfgs, growth_rate=0.0, months=12)
        assert proj.initial_monthly_cost == proj.final_monthly_cost
        assert proj.growth_rate == 0.0
        assert proj.months == 12
        assert len(proj.data_points) == 12
        # All months should have same cost
        for dp in proj.data_points:
            assert dp.monthly_cost == pytest.approx(proj.initial_monthly_cost)

    def test_positive_growth(self):
        e = _engine()
        cfgs = [_cfg(volume=10.0, cost=2.0)]
        proj = e.simulate_cost_growth(cfgs, growth_rate=0.1, months=6)
        assert proj.final_monthly_cost > proj.initial_monthly_cost
        assert len(proj.data_points) == 6
        # Costs should be monotonically increasing
        costs = [dp.monthly_cost for dp in proj.data_points]
        for i in range(1, len(costs)):
            assert costs[i] >= costs[i - 1]

    def test_cumulative_cost(self):
        e = _engine()
        cfgs = [_cfg(volume=10.0, cost=2.0)]
        proj = e.simulate_cost_growth(cfgs, growth_rate=0.05, months=3)
        cumulative = sum(dp.monthly_cost for dp in proj.data_points)
        assert proj.total_cost == pytest.approx(cumulative, rel=1e-2)

    def test_one_month(self):
        e = _engine()
        cfgs = [_cfg(volume=10.0, cost=2.0)]
        proj = e.simulate_cost_growth(cfgs, growth_rate=0.1, months=1)
        assert len(proj.data_points) == 1
        assert proj.data_points[0].month == 1
        assert proj.initial_monthly_cost == proj.final_monthly_cost

    def test_zero_months(self):
        e = _engine()
        cfgs = [_cfg()]
        proj = e.simulate_cost_growth(cfgs, growth_rate=0.1, months=0)
        assert len(proj.data_points) == 0
        assert proj.total_cost == 0.0

    def test_high_growth_recommendation(self):
        e = _engine()
        cfgs = [_cfg(volume=10.0, cost=2.0)]
        proj = e.simulate_cost_growth(cfgs, growth_rate=0.15, months=12)
        assert any("growth rate" in r.lower() for r in proj.recommendations)

    def test_doubling_recommendation(self):
        e = _engine()
        cfgs = [_cfg(volume=10.0, cost=2.0)]
        proj = e.simulate_cost_growth(cfgs, growth_rate=0.1, months=12)
        # 1.1^11 ≈ 2.85 > 2, so should trigger doubling warning
        assert any("double" in r.lower() for r in proj.recommendations)

    def test_empty_configs_zero_cost(self):
        e = _engine()
        proj = e.simulate_cost_growth([], growth_rate=0.1, months=6)
        assert proj.initial_monthly_cost == 0.0
        assert proj.final_monthly_cost == 0.0

    def test_growth_rate_zero_no_doubling_rec(self):
        e = _engine()
        cfgs = [_cfg()]
        proj = e.simulate_cost_growth(cfgs, growth_rate=0.0, months=12)
        assert not any("double" in r.lower() for r in proj.recommendations)

    def test_multiple_configs(self):
        e = _engine()
        cfgs = [
            _cfg(volume=10.0, cost=2.0),
            _cfg(volume=5.0, cost=3.0),
        ]
        proj = e.simulate_cost_growth(cfgs, growth_rate=0.05, months=6)
        expected_initial = sum(_monthly_cost_for_config(c) for c in cfgs)
        assert proj.initial_monthly_cost == pytest.approx(expected_initial, rel=1e-2)

    def test_month_numbering(self):
        e = _engine()
        cfgs = [_cfg()]
        proj = e.simulate_cost_growth(cfgs, growth_rate=0.0, months=5)
        assert [dp.month for dp in proj.data_points] == [1, 2, 3, 4, 5]


# ===================================================================
# _build_optimization tests (via analyze_cost)
# ===================================================================


class TestBuildOptimization:
    def test_no_actions_when_efficient(self):
        e = _engine()
        g = _graph()
        # Low volume, already compressed metrics don't trigger most actions
        cfgs = [
            _cfg(
                pillar=ObservabilityPillar.METRICS,
                volume=0.5,
                sampling=0.3,
                retention=30,
            )
        ]
        report = e.analyze_cost(g, cfgs)
        opt = report.optimization
        assert opt.current_monthly_cost == report.total_monthly_cost

    def test_sampling_action_suggested(self):
        e = _engine()
        g = _graph()
        cfgs = [_cfg(volume=10.0, sampling=1.0)]
        report = e.analyze_cost(g, cfgs)
        opt = report.optimization
        sampling_actions = [a for a in opt.optimizations if "sampling" in a.action.lower()]
        assert len(sampling_actions) > 0

    def test_retention_action_suggested(self):
        e = _engine()
        g = _graph()
        # Logs max recommended = 90, so 365 triggers retention action
        cfgs = [_cfg(pillar=ObservabilityPillar.LOGS, retention=365, volume=10.0)]
        report = e.analyze_cost(g, cfgs)
        opt = report.optimization
        retention_actions = [a for a in opt.optimizations if "retention" in a.action.lower()]
        assert len(retention_actions) > 0

    def test_compression_action_for_logs(self):
        e = _engine()
        g = _graph()
        cfgs = [
            _cfg(
                pillar=ObservabilityPillar.LOGS,
                volume=10.0,
                compression=1.0,
                sampling=0.3,
            )
        ]
        report = e.analyze_cost(g, cfgs)
        opt = report.optimization
        comp_actions = [a for a in opt.optimizations if "compression" in a.action.lower()]
        assert len(comp_actions) > 0

    def test_compression_action_for_traces(self):
        e = _engine()
        g = _graph()
        cfgs = [
            _cfg(
                pillar=ObservabilityPillar.TRACES,
                volume=10.0,
                compression=1.0,
                sampling=0.3,
            )
        ]
        report = e.analyze_cost(g, cfgs)
        opt = report.optimization
        comp_actions = [a for a in opt.optimizations if "compression" in a.action.lower()]
        assert len(comp_actions) > 0

    def test_no_compression_for_metrics(self):
        e = _engine()
        g = _graph()
        cfgs = [_cfg(pillar=ObservabilityPillar.METRICS, volume=10.0, compression=1.0)]
        report = e.analyze_cost(g, cfgs)
        opt = report.optimization
        comp_actions = [a for a in opt.optimizations if "compression" in a.action.lower()]
        assert len(comp_actions) == 0

    def test_savings_percent_positive(self):
        e = _engine()
        g = _graph()
        cfgs = [_cfg(volume=100.0, sampling=1.0, retention=365)]
        report = e.analyze_cost(g, cfgs)
        opt = report.optimization
        assert opt.savings_percent > 0

    def test_optimized_cost_lower(self):
        e = _engine()
        g = _graph()
        cfgs = [_cfg(volume=100.0, sampling=1.0, retention=365)]
        report = e.analyze_cost(g, cfgs)
        opt = report.optimization
        assert opt.optimized_monthly_cost < opt.current_monthly_cost

    def test_blind_spot_risk(self):
        e = _engine()
        g = _graph()
        cfgs = [_cfg(volume=100.0, sampling=1.0)]
        report = e.analyze_cost(g, cfgs)
        opt = report.optimization
        assert 0 <= opt.risk_of_blind_spots <= 100

    def test_recommendations_not_empty(self):
        e = _engine()
        g = _graph()
        cfgs = [_cfg(volume=100.0, sampling=1.0)]
        report = e.analyze_cost(g, cfgs)
        opt = report.optimization
        assert len(opt.recommendations) > 0

    def test_already_efficient_recommendation(self):
        e = _engine()
        g = _graph()
        cfgs = [
            _cfg(
                pillar=ObservabilityPillar.METRICS,
                volume=0.5,
                sampling=0.3,
                retention=90,
                compression=3.0,
            )
        ]
        report = e.analyze_cost(g, cfgs)
        opt = report.optimization
        if len(opt.optimizations) == 0:
            assert any("efficient" in r.lower() for r in opt.recommendations)

    def test_high_blind_spot_risk_warning(self):
        e = _engine()
        g = _graph()
        # Many high-volume configs with high sampling → many medium/high actions
        cfgs = [
            _cfg(pillar=ObservabilityPillar.LOGS, volume=100.0, sampling=1.0),
            _cfg(pillar=ObservabilityPillar.TRACES, volume=100.0, sampling=1.0),
            _cfg(pillar=ObservabilityPillar.METRICS, volume=100.0, sampling=1.0),
        ]
        report = e.analyze_cost(g, cfgs)
        opt = report.optimization
        # Check that blind_spot risk is calculated
        assert opt.risk_of_blind_spots >= 0


# ===================================================================
# Integration tests
# ===================================================================


class TestIntegration:
    def test_full_workflow(self):
        """End-to-end: analyze, optimize, detect redundancy."""
        e = _engine()
        g = _graph(
            _comp("lb", "LB", ComponentType.LOAD_BALANCER),
            _comp("app", "App", ComponentType.APP_SERVER, replicas=3),
            _comp("db", "DB", ComponentType.DATABASE),
            deps=[("lb", "app"), ("app", "db")],
        )
        cfgs = [
            _cfg(
                pillar=ObservabilityPillar.LOGS,
                vendor=Vendor.DATADOG,
                volume=50.0,
                cost=2.5,
                retention=90,
            ),
            _cfg(
                pillar=ObservabilityPillar.METRICS,
                vendor=Vendor.DATADOG,
                volume=20.0,
                cost=8.0,
                retention=90,
            ),
            _cfg(
                pillar=ObservabilityPillar.TRACES,
                vendor=Vendor.NEW_RELIC,
                volume=10.0,
                cost=4.5,
                retention=30,
            ),
        ]

        report = e.analyze_cost(g, cfgs)
        assert report.total_monthly_cost > 0
        assert report.component_count == 3
        assert report.config_count == 3

        recs = e.optimize_sampling(cfgs, budget=report.total_monthly_cost * 0.5)
        assert len(recs) == 3
        for r in recs:
            assert r.recommended_sampling_rate <= r.current_sampling_rate

        redundancies = e.detect_redundant_telemetry(cfgs)
        # No same-pillar multi-vendor in this config
        assert len(redundancies) == 0

        vendor_cmp = e.estimate_vendor_cost(cfgs)
        assert vendor_cmp.cheapest_vendor is not None

        coverage = e.calculate_detection_coverage(g, cfgs)
        assert 0 < coverage.overall_score < 100

        retention_recs = e.recommend_retention_policy(cfgs)
        assert len(retention_recs) == 3

        growth = e.simulate_cost_growth(cfgs, growth_rate=0.1, months=12)
        assert growth.final_monthly_cost > growth.initial_monthly_cost

    def test_redundant_multi_vendor_workflow(self):
        e = _engine()
        g = _graph(_comp("c1", "App"))
        cfgs = [
            _cfg(pillar=ObservabilityPillar.LOGS, vendor=Vendor.DATADOG, volume=10.0),
            _cfg(pillar=ObservabilityPillar.LOGS, vendor=Vendor.SPLUNK, volume=10.0),
            _cfg(pillar=ObservabilityPillar.METRICS, vendor=Vendor.GRAFANA_CLOUD, volume=5.0),
        ]
        report = e.analyze_cost(g, cfgs)
        assert report.total_monthly_cost > 0

        redundancies = e.detect_redundant_telemetry(cfgs)
        assert len(redundancies) == 1
        assert redundancies[0].monthly_waste > 0

    def test_all_methods_with_empty_graph(self):
        e = _engine()
        g = _graph()
        cfgs = [_cfg()]

        report = e.analyze_cost(g, cfgs)
        assert report.component_count == 0

        recs = e.optimize_sampling(cfgs, budget=1e6)
        assert len(recs) == 1

        red = e.detect_redundant_telemetry(cfgs)
        assert len(red) == 0

        vc = e.estimate_vendor_cost(cfgs)
        assert vc.cheapest_vendor is not None

        cov = e.calculate_detection_coverage(g, cfgs)
        assert cov.overall_score > 0

        ret = e.recommend_retention_policy(cfgs)
        assert len(ret) == 1

        grow = e.simulate_cost_growth(cfgs, 0.05, 6)
        assert grow.months == 6

    def test_high_compression_lowers_cost(self):
        e = _engine()
        g = _graph()
        no_comp = [_cfg(compression=1.0)]
        hi_comp = [_cfg(compression=5.0)]
        r1 = e.analyze_cost(g, no_comp)
        r2 = e.analyze_cost(g, hi_comp)
        assert r2.total_monthly_cost < r1.total_monthly_cost

    def test_retention_impacts_cost(self):
        e = _engine()
        g = _graph()
        short = [_cfg(retention=7)]
        long = [_cfg(retention=365)]
        r1 = e.analyze_cost(g, short)
        r2 = e.analyze_cost(g, long)
        assert r2.total_monthly_cost > r1.total_monthly_cost

    def test_sampling_impacts_cost(self):
        e = _engine()
        g = _graph()
        full = [_cfg(sampling=1.0)]
        half = [_cfg(sampling=0.5)]
        r1 = e.analyze_cost(g, full)
        r2 = e.analyze_cost(g, half)
        assert r2.total_monthly_cost < r1.total_monthly_cost


# ===================================================================
# Edge case tests
# ===================================================================


class TestEdgeCases:
    def test_very_small_volume(self):
        e = _engine()
        g = _graph()
        cfgs = [_cfg(volume=0.001)]
        report = e.analyze_cost(g, cfgs)
        assert report.total_monthly_cost >= 0

    def test_very_large_volume(self):
        e = _engine()
        g = _graph()
        cfgs = [_cfg(volume=1_000_000.0)]
        report = e.analyze_cost(g, cfgs)
        assert report.total_monthly_cost > 0

    def test_min_sampling(self):
        e = _engine()
        g = _graph()
        cfgs = [_cfg(sampling=0.0)]
        report = e.analyze_cost(g, cfgs)
        assert report.total_monthly_cost == 0.0

    def test_very_long_retention(self):
        e = _engine()
        cfgs = [_cfg(retention=3650)]
        recs = e.recommend_retention_policy(cfgs)
        assert recs[0].recommended_retention_days < 3650
        assert recs[0].monthly_savings > 0

    def test_retention_1_day(self):
        e = _engine()
        cfgs = [_cfg(pillar=ObservabilityPillar.METRICS, retention=1)]
        recs = e.recommend_retention_policy(cfgs)
        assert recs[0].recommended_retention_days > 1

    def test_vendor_comparison_all_pillars(self):
        e = _engine()
        cfgs = [
            _cfg(pillar=p, vendor=Vendor.DATADOG, volume=10.0, cost=5.0)
            for p in ObservabilityPillar
        ]
        result = e.estimate_vendor_cost(cfgs)
        assert result.cheapest_vendor is not None
        assert result.cheapest_monthly_cost > 0

    def test_growth_negative_rate(self):
        e = _engine()
        cfgs = [_cfg()]
        proj = e.simulate_cost_growth(cfgs, growth_rate=-0.1, months=6)
        assert proj.final_monthly_cost < proj.initial_monthly_cost

    def test_growth_very_high_rate(self):
        e = _engine()
        cfgs = [_cfg()]
        proj = e.simulate_cost_growth(cfgs, growth_rate=1.0, months=3)
        # 2^2 = 4x after 3 months
        assert proj.final_monthly_cost > proj.initial_monthly_cost * 3

    def test_coverage_with_large_graph(self):
        e = _engine()
        comps = [_comp(f"c{i}", f"Component{i}") for i in range(50)]
        g = _graph(*comps)
        cfgs = [_cfg(pillar=ObservabilityPillar.LOGS)]
        cov = e.calculate_detection_coverage(g, cfgs)
        assert cov.overall_score > 0

    def test_all_vendors_one_pillar(self):
        e = _engine()
        cfgs = [
            _cfg(pillar=ObservabilityPillar.LOGS, vendor=v) for v in Vendor
        ]
        findings = e.detect_redundant_telemetry(cfgs)
        assert len(findings) == 1
        assert len(findings[0].vendors) == len(Vendor)

    def test_identical_configs_duplicate(self):
        e = _engine()
        cfgs = [_cfg(), _cfg()]
        findings = e.detect_redundant_telemetry(cfgs)
        assert len(findings) == 1

    def test_sampling_budget_zero(self):
        e = _engine()
        cfgs = [_cfg(volume=10.0)]
        recs = e.optimize_sampling(cfgs, budget=0.0)
        # Should try to reduce, though weight-prioritised pillars retain more
        assert len(recs) == 1
        assert recs[0].recommended_sampling_rate < recs[0].current_sampling_rate
        assert recs[0].estimated_monthly_savings > 0


# ===================================================================
# Additional coverage tests for detection impact edge cases
# ===================================================================


class TestDetectionImpactEdgeCases:
    def test_very_small_current(self):
        assert _detection_impact_for_sampling(0.001, 0.0005) == "medium"

    def test_proposed_zero(self):
        assert _detection_impact_for_sampling(1.0, 0.0) == "high"

    def test_proposed_equals_current_nonzero(self):
        assert _detection_impact_for_sampling(0.5, 0.5) == "none"

    def test_proposed_slightly_below(self):
        # 0.81/1.0 = 0.81 >= 0.8 => low
        assert _detection_impact_for_sampling(1.0, 0.81) == "low"

    def test_ratio_exactly_0_5(self):
        assert _detection_impact_for_sampling(1.0, 0.5) == "medium"


# ===================================================================
# Additional model validation tests
# ===================================================================


class TestModelValidation:
    def test_config_with_all_fields(self):
        cfg = ObservabilityConfig(
            pillar=ObservabilityPillar.PROFILING,
            vendor=Vendor.ELASTIC,
            volume_per_day=100.0,
            retention_days=14,
            cost_per_unit=7.0,
            sampling_rate=0.5,
            compression_ratio=2.0,
        )
        assert cfg.pillar == ObservabilityPillar.PROFILING
        assert cfg.vendor == Vendor.ELASTIC
        assert cfg.sampling_rate == 0.5
        assert cfg.compression_ratio == 2.0

    def test_cost_growth_projection_fields(self):
        dp = CostGrowthDataPoint(month=3, monthly_cost=150.0, cumulative_cost=450.0)
        proj = CostGrowthProjection(
            initial_monthly_cost=100.0,
            final_monthly_cost=200.0,
            total_cost=1800.0,
            growth_rate=0.05,
            months=12,
            data_points=[dp],
            recommendations=["reduce volume"],
        )
        assert len(proj.data_points) == 1
        assert proj.data_points[0].monthly_cost == 150.0

    def test_observability_report_full(self):
        opt = CostOptimization(
            current_monthly_cost=1000.0,
            optimized_monthly_cost=800.0,
            savings_percent=20.0,
            risk_of_blind_spots=10.0,
            optimizations=[
                OptimizationAction(
                    action="test",
                    pillar=ObservabilityPillar.LOGS,
                    monthly_savings=200.0,
                    detection_impact="low",
                    implementation_effort="low",
                )
            ],
            recommendations=["test rec"],
        )
        report = ObservabilityCostReport(
            total_monthly_cost=1000.0,
            per_pillar_cost={"logs": 600.0, "metrics": 400.0},
            per_vendor_cost={"datadog": 1000.0},
            optimization=opt,
            component_count=3,
            config_count=2,
        )
        assert report.total_monthly_cost == 1000.0
        assert len(report.optimization.optimizations) == 1


# ===================================================================
# Cost calculation precision tests
# ===================================================================


class TestCostPrecision:
    def test_fractional_retention(self):
        # 45 days: extra_windows = (45-30)/30 = 0.5
        cfg = _cfg(retention=45)
        base = 10.0 * 2.0 * 30.0
        expected = base * (1.0 + 0.5 * _RETENTION_COST_FACTOR_PER_30D)
        assert _monthly_cost_for_config(cfg) == pytest.approx(expected)

    def test_combined_sampling_compression(self):
        cfg = _cfg(volume=20.0, cost=3.0, sampling=0.5, compression=2.0, retention=30)
        # effective = 20 * 0.5 / 2.0 = 5.0
        # cost = 5.0 * 3.0 * 30 = 450
        assert _monthly_cost_for_config(cfg) == pytest.approx(450.0)

    def test_retention_365_multiplier(self):
        cfg = _cfg(retention=365)
        extra = (365 - 30) / 30.0
        mult = 1.0 + extra * _RETENTION_COST_FACTOR_PER_30D
        base = 10.0 * 2.0 * 30.0
        assert _monthly_cost_for_config(cfg) == pytest.approx(base * mult)
