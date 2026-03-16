"""Tests for Distributed Tracing Resilience Analyzer.

130+ tests covering all enums, data models, pipeline assessment,
trace loss simulation, sampling optimization, observability gap
detection, storage cost estimation, collector scaling, and
trace-resilience correlation.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from faultray.model.components import Component, ComponentType, Dependency, HealthStatus
from faultray.model.graph import InfraGraph
from faultray.simulator.distributed_tracing_resilience import (
    CollectorScalingResult,
    DistributedTracingEngine,
    ObservabilityGap,
    SamplingRecommendation,
    SamplingStrategy,
    StorageCostEstimate,
    TraceLossResult,
    TraceLossScenario,
    TracePipelineAssessment,
    TraceReliabilityMetrics,
    TraceResilienceCorrelation,
    TracingComponent,
    TracingConfig,
    _COLLECTOR_CAPACITY_SPANS_PER_SEC,
    _COMPONENT_OVERHEAD_MS,
    _COST_PER_GB_USD,
    _DEFAULT_SPAN_SIZE_KB,
    _SCENARIO_BASE_IMPACT,
    _clamp,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(
    cid: str,
    name: str,
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    failover: bool = False,
    health: HealthStatus = HealthStatus.HEALTHY,
) -> Component:
    c = Component(id=cid, name=name, type=ctype, replicas=replicas, health=health)
    if failover:
        c.failover.enabled = True
    return c


def _graph(*components: Component) -> InfraGraph:
    g = InfraGraph()
    for c in components:
        g.add_component(c)
    return g


def _engine() -> DistributedTracingEngine:
    return DistributedTracingEngine()


def _default_config(**overrides) -> TracingConfig:
    defaults = dict(
        collectors=2,
        sampling_strategy=SamplingStrategy.PROBABILISTIC,
        sampling_rate=0.1,
        exporters=2,
        storage_retention_days=7,
        storage_capacity_gb=500.0,
        has_redundant_collectors=True,
        has_tail_sampling=True,
        max_spans_per_second=10000,
        instrumented_services=["api", "web", "db"],
    )
    defaults.update(overrides)
    return TracingConfig(**defaults)


def _weak_config(**overrides) -> TracingConfig:
    defaults = dict(
        collectors=1,
        sampling_strategy=SamplingStrategy.PROBABILISTIC,
        sampling_rate=0.01,
        exporters=1,
        storage_retention_days=3,
        storage_capacity_gb=10.0,
        has_redundant_collectors=False,
        has_tail_sampling=False,
        max_spans_per_second=1000,
        instrumented_services=[],
    )
    defaults.update(overrides)
    return TracingConfig(**defaults)


# ===========================================================================
# 1. Enum completeness
# ===========================================================================


class TestTracingComponentEnum:
    def test_all_values_exist(self):
        expected = {
            "instrumentation", "collector", "sampler", "exporter",
            "storage_backend", "query_engine", "alerting",
        }
        assert {tc.value for tc in TracingComponent} == expected

    def test_count(self):
        assert len(TracingComponent) == 7

    @pytest.mark.parametrize("tc", list(TracingComponent))
    def test_is_str_enum(self, tc: TracingComponent):
        assert isinstance(tc.value, str)


class TestTraceLossScenarioEnum:
    def test_all_values_exist(self):
        expected = {
            "collector_overload", "sampling_misconfiguration", "exporter_failure",
            "storage_full", "network_partition", "clock_skew", "span_drop",
            "context_propagation_failure", "high_cardinality_explosion",
            "circular_trace",
        }
        assert {s.value for s in TraceLossScenario} == expected

    def test_count(self):
        assert len(TraceLossScenario) == 10

    @pytest.mark.parametrize("scenario", list(TraceLossScenario))
    def test_is_str_enum(self, scenario: TraceLossScenario):
        assert isinstance(scenario.value, str)

    @pytest.mark.parametrize("scenario", list(TraceLossScenario))
    def test_has_base_impact(self, scenario: TraceLossScenario):
        assert scenario in _SCENARIO_BASE_IMPACT


class TestSamplingStrategyEnum:
    def test_all_values_exist(self):
        expected = {
            "always_on", "probabilistic", "rate_limiting",
            "adaptive", "tail_based", "parent_based",
        }
        assert {s.value for s in SamplingStrategy} == expected

    def test_count(self):
        assert len(SamplingStrategy) == 6

    @pytest.mark.parametrize("ss", list(SamplingStrategy))
    def test_is_str_enum(self, ss: SamplingStrategy):
        assert isinstance(ss.value, str)


# ===========================================================================
# 2. Constants
# ===========================================================================


class TestConstants:
    def test_scenario_base_impact_all_positive(self):
        for val in _SCENARIO_BASE_IMPACT.values():
            assert val > 0.0

    def test_scenario_base_impact_within_100(self):
        for val in _SCENARIO_BASE_IMPACT.values():
            assert 0.0 < val <= 100.0

    def test_default_span_size_positive(self):
        assert _DEFAULT_SPAN_SIZE_KB > 0

    def test_cost_per_gb_positive(self):
        assert _COST_PER_GB_USD > 0

    def test_collector_capacity_positive(self):
        assert _COLLECTOR_CAPACITY_SPANS_PER_SEC > 0

    def test_component_overhead_all_present(self):
        for tc in TracingComponent:
            assert tc in _COMPONENT_OVERHEAD_MS

    def test_component_overhead_non_negative(self):
        for val in _COMPONENT_OVERHEAD_MS.values():
            assert val >= 0.0


# ===========================================================================
# 3. Utility: _clamp
# ===========================================================================


class TestClamp:
    def test_within_range(self):
        assert _clamp(50.0) == 50.0

    def test_below_lo(self):
        assert _clamp(-10.0) == 0.0

    def test_above_hi(self):
        assert _clamp(150.0) == 100.0

    def test_at_lo(self):
        assert _clamp(0.0) == 0.0

    def test_at_hi(self):
        assert _clamp(100.0) == 100.0

    def test_custom_range(self):
        assert _clamp(5.0, 1.0, 10.0) == 5.0

    def test_custom_range_below(self):
        assert _clamp(-1.0, 1.0, 10.0) == 1.0

    def test_custom_range_above(self):
        assert _clamp(20.0, 1.0, 10.0) == 10.0


# ===========================================================================
# 4. Data model defaults
# ===========================================================================


class TestTracingConfig:
    def test_defaults(self):
        c = TracingConfig()
        assert c.collectors == 1
        assert c.sampling_rate == 0.1
        assert c.exporters == 1
        assert c.storage_retention_days == 7
        assert c.instrumented_services == []

    def test_custom_values(self):
        c = TracingConfig(collectors=4, sampling_rate=0.5, exporters=3)
        assert c.collectors == 4
        assert c.sampling_rate == 0.5
        assert c.exporters == 3


class TestTraceReliabilityMetrics:
    def test_defaults(self):
        m = TraceReliabilityMetrics()
        assert m.trace_completeness == 1.0
        assert m.span_drop_rate == 0.0
        assert m.latency_overhead_ms == 0.0
        assert m.storage_cost_per_day == 0.0
        assert m.mean_time_to_detect_minutes == 0.0
        assert m.sampling_effectiveness == 1.0

    def test_custom_values(self):
        m = TraceReliabilityMetrics(trace_completeness=0.8, span_drop_rate=0.05)
        assert m.trace_completeness == 0.8
        assert m.span_drop_rate == 0.05


class TestTracePipelineAssessment:
    def test_defaults(self):
        a = TracePipelineAssessment()
        assert a.pipeline_components == []
        assert a.single_points_of_failure == []
        assert a.estimated_trace_loss_percent == 0.0
        assert a.bottlenecks == []
        assert a.recommendations == []
        assert a.overall_reliability == 0.0


class TestTraceLossResult:
    def test_defaults(self):
        r = TraceLossResult(scenario=TraceLossScenario.SPAN_DROP)
        assert r.scenario == TraceLossScenario.SPAN_DROP
        assert r.affected_services == []
        assert r.estimated_loss_percent == 0.0
        assert r.data_loss_possible is False
        assert r.mitigations == []
        assert r.severity == 0.0


class TestSamplingRecommendation:
    def test_defaults(self):
        r = SamplingRecommendation(strategy=SamplingStrategy.ADAPTIVE)
        assert r.strategy == SamplingStrategy.ADAPTIVE
        assert r.recommended_rate == 1.0
        assert r.within_budget is True


class TestObservabilityGap:
    def test_defaults(self):
        g = ObservabilityGap(component_id="x", component_name="X", component_type="app_server")
        assert g.gap_type == "no_instrumentation"
        assert g.risk_level == "medium"


class TestStorageCostEstimate:
    def test_defaults(self):
        e = StorageCostEstimate()
        assert e.retention_days == 7
        assert e.daily_storage_gb == 0.0
        assert e.recommendations == []


class TestCollectorScalingResult:
    def test_defaults(self):
        r = CollectorScalingResult()
        assert r.current_collectors == 1
        assert r.needs_scaling is False


class TestTraceResilienceCorrelation:
    def test_defaults(self):
        c = TraceResilienceCorrelation()
        assert c.observability_score == 0.0
        assert c.correlation_strength == "none"
        assert c.blind_spots == []


# ===========================================================================
# 5. assess_pipeline
# ===========================================================================


class TestAssessPipeline:
    def test_returns_assessment_type(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.assess_pipeline(g, _default_config())
        assert isinstance(result, TracePipelineAssessment)

    def test_pipeline_components_listed(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.assess_pipeline(g, _default_config())
        assert len(result.pipeline_components) == len(TracingComponent)

    def test_no_spof_with_redundancy(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        config = _default_config(collectors=2, exporters=2, has_redundant_collectors=True)
        result = e.assess_pipeline(g, config)
        assert "collector" not in result.single_points_of_failure
        assert "exporter" not in result.single_points_of_failure

    def test_collector_spof_single_no_redundancy(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        config = _weak_config()
        result = e.assess_pipeline(g, config)
        assert "collector" in result.single_points_of_failure

    def test_exporter_spof_single(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        config = _weak_config(exporters=1)
        result = e.assess_pipeline(g, config)
        assert "exporter" in result.single_points_of_failure

    def test_always_on_bottleneck(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        config = _default_config(sampling_strategy=SamplingStrategy.ALWAYS_ON)
        result = e.assess_pipeline(g, config)
        assert any("always_on" in b for b in result.bottlenecks)

    def test_low_sampling_rate_recommendation(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        config = _default_config(sampling_rate=0.005)
        result = e.assess_pipeline(g, config)
        assert any("sampling rate" in r.lower() for r in result.recommendations)

    def test_low_instrumentation_coverage_bottleneck(self):
        e = _engine()
        g = _graph(
            _comp("api", "API"),
            _comp("web", "Web"),
            _comp("db", "DB", ctype=ComponentType.DATABASE),
            _comp("cache", "Cache", ctype=ComponentType.CACHE),
        )
        config = _default_config(instrumented_services=["api"])
        result = e.assess_pipeline(g, config)
        assert any("instrumentation" in b.lower() or "coverage" in b.lower() for b in result.bottlenecks)

    def test_storage_capacity_bottleneck(self):
        e = _engine()
        g = _graph(*[_comp(f"s{i}", f"Svc{i}") for i in range(20)])
        config = _default_config(
            storage_capacity_gb=0.001,
            storage_retention_days=30,
            sampling_rate=1.0,
        )
        result = e.assess_pipeline(g, config)
        assert any("storage" in b.lower() for b in result.bottlenecks)

    def test_reliability_higher_with_redundancy(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        strong = e.assess_pipeline(g, _default_config())
        weak = e.assess_pipeline(g, _weak_config())
        assert strong.overall_reliability > weak.overall_reliability

    def test_reliability_bounded(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.assess_pipeline(g, _default_config())
        assert 0.0 <= result.overall_reliability <= 100.0

    def test_estimated_trace_loss_bounded(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.assess_pipeline(g, _weak_config())
        assert 0.0 <= result.estimated_trace_loss_percent <= 100.0

    def test_empty_graph(self):
        e = _engine()
        g = InfraGraph()
        result = e.assess_pipeline(g, _default_config())
        assert isinstance(result, TracePipelineAssessment)
        assert result.overall_reliability >= 0.0

    def test_collector_capacity_bottleneck(self):
        """Many services with high sampling rate and few collectors triggers bottleneck."""
        e = _engine()
        # 50 services * 100 * 1.0 = 5000 spans/s; 1 collector = 10000 capacity; 5000 > 8000 is false
        # Need more services: 100 * 100 * 1.0 = 10000 > 0.8 * 10000 = 8000
        g = _graph(*[_comp(f"s{i}", f"Svc{i}") for i in range(100)])
        config = _default_config(
            collectors=1,
            has_redundant_collectors=True,
            sampling_strategy=SamplingStrategy.ALWAYS_ON,
            sampling_rate=1.0,
            instrumented_services=[f"s{i}" for i in range(100)],
        )
        result = e.assess_pipeline(g, config)
        assert any("collector capacity" in b.lower() for b in result.bottlenecks)


# ===========================================================================
# 6. simulate_trace_loss
# ===========================================================================


class TestSimulateTraceLoss:
    @pytest.mark.parametrize("scenario", list(TraceLossScenario))
    def test_returns_result_for_every_scenario(self, scenario: TraceLossScenario):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.simulate_trace_loss(g, scenario)
        assert isinstance(result, TraceLossResult)
        assert result.scenario == scenario

    @pytest.mark.parametrize("scenario", list(TraceLossScenario))
    def test_loss_percent_bounded(self, scenario: TraceLossScenario):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.simulate_trace_loss(g, scenario)
        assert 0.0 <= result.estimated_loss_percent <= 100.0

    @pytest.mark.parametrize("scenario", list(TraceLossScenario))
    def test_severity_bounded(self, scenario: TraceLossScenario):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.simulate_trace_loss(g, scenario)
        assert 0.0 <= result.severity <= 1.0

    @pytest.mark.parametrize("scenario", list(TraceLossScenario))
    def test_has_mitigations(self, scenario: TraceLossScenario):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.simulate_trace_loss(g, scenario)
        assert len(result.mitigations) > 0

    def test_collector_overload_redundancy_reduces_loss(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        with_red = e.simulate_trace_loss(g, TraceLossScenario.COLLECTOR_OVERLOAD, _default_config(has_redundant_collectors=True))
        without_red = e.simulate_trace_loss(g, TraceLossScenario.COLLECTOR_OVERLOAD, _weak_config())
        assert with_red.estimated_loss_percent < without_red.estimated_loss_percent

    def test_exporter_failure_redundancy_reduces_loss(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        with_exp = e.simulate_trace_loss(g, TraceLossScenario.EXPORTER_FAILURE, _default_config(exporters=3))
        without_exp = e.simulate_trace_loss(g, TraceLossScenario.EXPORTER_FAILURE, _weak_config(exporters=1))
        assert with_exp.estimated_loss_percent < without_exp.estimated_loss_percent

    def test_storage_full_always_data_loss(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.simulate_trace_loss(g, TraceLossScenario.STORAGE_FULL)
        assert result.data_loss_possible is True

    def test_network_partition_data_loss_without_redundancy(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.simulate_trace_loss(g, TraceLossScenario.NETWORK_PARTITION, _weak_config())
        assert result.data_loss_possible is True

    def test_network_partition_no_data_loss_with_redundancy(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.simulate_trace_loss(g, TraceLossScenario.NETWORK_PARTITION, _default_config())
        assert result.data_loss_possible is False

    def test_clock_skew_detection_delay_high(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.simulate_trace_loss(g, TraceLossScenario.CLOCK_SKEW)
        assert result.detection_delay_minutes >= 20.0

    def test_span_drop_reduced_with_tail_sampling(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        with_tail = e.simulate_trace_loss(g, TraceLossScenario.SPAN_DROP, _default_config(has_tail_sampling=True))
        without_tail = e.simulate_trace_loss(g, TraceLossScenario.SPAN_DROP, _weak_config(has_tail_sampling=False))
        assert with_tail.estimated_loss_percent < without_tail.estimated_loss_percent

    def test_affected_services_populated(self):
        e = _engine()
        g = _graph(_comp("api", "API"), _comp("web", "Web"))
        result = e.simulate_trace_loss(g, TraceLossScenario.STORAGE_FULL)
        assert len(result.affected_services) > 0

    def test_sampling_misconfiguration_adaptive_reduces_loss(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        adaptive = e.simulate_trace_loss(g, TraceLossScenario.SAMPLING_MISCONFIGURATION, _default_config(sampling_strategy=SamplingStrategy.ADAPTIVE))
        prob = e.simulate_trace_loss(g, TraceLossScenario.SAMPLING_MISCONFIGURATION, _weak_config())
        assert adaptive.estimated_loss_percent < prob.estimated_loss_percent

    def test_default_config_used_when_none(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.simulate_trace_loss(g, TraceLossScenario.SPAN_DROP, None)
        assert isinstance(result, TraceLossResult)

    def test_detection_delay_non_negative(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        for scenario in TraceLossScenario:
            result = e.simulate_trace_loss(g, scenario)
            assert result.detection_delay_minutes >= 0.0


# ===========================================================================
# 7. optimize_sampling
# ===========================================================================


class TestOptimizeSampling:
    def test_returns_recommendation_type(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.optimize_sampling(g, 5000)
        assert isinstance(result, SamplingRecommendation)

    def test_always_on_when_budget_exceeds_raw(self):
        e = _engine()
        g = _graph(_comp("api", "API"))  # 1 service * 100 = 100 spans/s
        result = e.optimize_sampling(g, 1000)  # budget >> 100
        assert result.strategy == SamplingStrategy.ALWAYS_ON
        assert result.recommended_rate == 1.0

    def test_within_budget_flag(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.optimize_sampling(g, 500)
        assert result.within_budget is True

    def test_zero_budget(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.optimize_sampling(g, 0)
        assert result.recommended_rate == 0.0
        assert result.strategy == SamplingStrategy.RATE_LIMITING

    def test_tight_budget_uses_rate_limiting(self):
        e = _engine()
        g = _graph(*[_comp(f"s{i}", f"Svc{i}") for i in range(100)])
        # 100 services * 100 = 10000 spans/s; budget = 5
        result = e.optimize_sampling(g, 5)
        assert result.strategy == SamplingStrategy.RATE_LIMITING

    def test_moderate_budget_uses_probabilistic(self):
        e = _engine()
        g = _graph(*[_comp(f"s{i}", f"Svc{i}") for i in range(10)])
        # 10 services * 100 = 1000; budget = 50 => rate ~0.05
        result = e.optimize_sampling(g, 50)
        assert result.strategy == SamplingStrategy.PROBABILISTIC

    def test_high_budget_uses_tail_based(self):
        e = _engine()
        g = _graph(*[_comp(f"s{i}", f"Svc{i}") for i in range(10)])
        # 1000 raw, budget 200 => rate 0.2
        result = e.optimize_sampling(g, 200)
        assert result.strategy == SamplingStrategy.TAIL_BASED

    def test_generous_budget_uses_adaptive(self):
        e = _engine()
        g = _graph(*[_comp(f"s{i}", f"Svc{i}") for i in range(10)])
        # 1000 raw, budget 600 => rate 0.6
        result = e.optimize_sampling(g, 600)
        assert result.strategy == SamplingStrategy.ADAPTIVE

    def test_recommended_rate_bounded(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.optimize_sampling(g, 50)
        assert 0.0 <= result.recommended_rate <= 1.0

    def test_estimated_spans_non_negative(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.optimize_sampling(g, 50)
        assert result.estimated_spans_per_second >= 0

    def test_storage_estimate_non_negative(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.optimize_sampling(g, 50)
        assert result.estimated_storage_gb_per_day >= 0.0

    def test_trade_off_summary_present(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.optimize_sampling(g, 50)
        assert len(result.trade_off_summary) > 0

    def test_empty_graph_budget(self):
        e = _engine()
        g = InfraGraph()
        result = e.optimize_sampling(g, 5000)
        assert result.strategy == SamplingStrategy.ALWAYS_ON


# ===========================================================================
# 8. detect_observability_gaps
# ===========================================================================


class TestDetectObservabilityGaps:
    def test_no_gaps_fully_instrumented(self):
        e = _engine()
        g = _graph(_comp("api", "API"), _comp("web", "Web"))
        config = _default_config(instrumented_services=["api", "web"])
        gaps = e.detect_observability_gaps(g, config)
        assert len(gaps) == 0

    def test_all_gaps_when_none_instrumented(self):
        e = _engine()
        g = _graph(_comp("api", "API"), _comp("web", "Web"))
        config = _default_config(instrumented_services=[])
        gaps = e.detect_observability_gaps(g, config)
        assert len(gaps) == 2

    def test_partial_gaps(self):
        e = _engine()
        g = _graph(_comp("api", "API"), _comp("web", "Web"), _comp("db", "DB"))
        config = _default_config(instrumented_services=["api"])
        gaps = e.detect_observability_gaps(g, config)
        assert len(gaps) == 2
        gap_ids = {gap.component_id for gap in gaps}
        assert "web" in gap_ids
        assert "db" in gap_ids

    def test_gap_type_is_no_instrumentation(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        config = _default_config(instrumented_services=[])
        gaps = e.detect_observability_gaps(g, config)
        assert gaps[0].gap_type == "no_instrumentation"

    def test_database_gets_high_risk(self):
        e = _engine()
        g = _graph(_comp("db", "DB", ctype=ComponentType.DATABASE))
        config = _default_config(instrumented_services=[])
        gaps = e.detect_observability_gaps(g, config)
        assert gaps[0].risk_level == "high"

    def test_queue_gets_high_risk(self):
        e = _engine()
        g = _graph(_comp("q", "Queue", ctype=ComponentType.QUEUE))
        config = _default_config(instrumented_services=[])
        gaps = e.detect_observability_gaps(g, config)
        assert gaps[0].risk_level == "high"

    def test_isolated_component_gets_low_risk(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        config = _default_config(instrumented_services=[])
        gaps = e.detect_observability_gaps(g, config)
        assert gaps[0].risk_level == "low"

    def test_connected_component_gets_medium_or_high_risk(self):
        e = _engine()
        g = _graph(_comp("api", "API"), _comp("web", "Web"))
        g.add_dependency(Dependency(source_id="web", target_id="api"))
        config = _default_config(instrumented_services=[])
        gaps = e.detect_observability_gaps(g, config)
        api_gap = [gap for gap in gaps if gap.component_id == "api"][0]
        assert api_gap.risk_level in ("medium", "high")

    def test_highly_connected_gets_high_risk(self):
        e = _engine()
        g = _graph(
            _comp("api", "API"),
            _comp("a", "A"), _comp("b", "B"), _comp("c", "C"),
        )
        g.add_dependency(Dependency(source_id="a", target_id="api"))
        g.add_dependency(Dependency(source_id="b", target_id="api"))
        g.add_dependency(Dependency(source_id="c", target_id="api"))
        config = _default_config(instrumented_services=[])
        gaps = e.detect_observability_gaps(g, config)
        api_gap = [gap for gap in gaps if gap.component_id == "api"][0]
        assert api_gap.risk_level == "high"

    def test_recommendation_contains_name(self):
        e = _engine()
        g = _graph(_comp("api", "MyAPI"))
        config = _default_config(instrumented_services=[])
        gaps = e.detect_observability_gaps(g, config)
        assert "MyAPI" in gaps[0].recommendation

    def test_default_config_when_none(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        gaps = e.detect_observability_gaps(g, None)
        assert len(gaps) == 1

    def test_empty_graph_no_gaps(self):
        e = _engine()
        g = InfraGraph()
        gaps = e.detect_observability_gaps(g)
        assert len(gaps) == 0


# ===========================================================================
# 9. estimate_trace_storage_cost
# ===========================================================================


class TestEstimateTraceStorageCost:
    def test_returns_estimate_type(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.estimate_trace_storage_cost(g, 7)
        assert isinstance(result, StorageCostEstimate)

    def test_retention_days_set(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.estimate_trace_storage_cost(g, 30)
        assert result.retention_days == 30

    def test_total_storage_is_daily_times_retention(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.estimate_trace_storage_cost(g, 10)
        # Allow for rounding differences (each value rounded to 2 decimals independently)
        assert abs(result.total_storage_gb - result.daily_storage_gb * 10) < 0.1

    def test_cost_scales_with_retention(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        short = e.estimate_trace_storage_cost(g, 7)
        long = e.estimate_trace_storage_cost(g, 30)
        assert long.estimated_total_cost > short.estimated_total_cost

    def test_cost_scales_with_services(self):
        e = _engine()
        small = _graph(_comp("api", "API"))
        large = _graph(*[_comp(f"s{i}", f"Svc{i}") for i in range(10)])
        r_small = e.estimate_trace_storage_cost(small, 7)
        r_large = e.estimate_trace_storage_cost(large, 7)
        assert r_large.daily_storage_gb > r_small.daily_storage_gb

    def test_always_on_costs_more(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        always = e.estimate_trace_storage_cost(g, 7, _default_config(sampling_strategy=SamplingStrategy.ALWAYS_ON, sampling_rate=1.0))
        prob = e.estimate_trace_storage_cost(g, 7, _default_config(sampling_strategy=SamplingStrategy.PROBABILISTIC, sampling_rate=0.1))
        assert always.daily_storage_gb > prob.daily_storage_gb

    def test_cost_per_million_spans_positive(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.estimate_trace_storage_cost(g, 7)
        assert result.cost_per_million_spans > 0.0

    def test_daily_cost_non_negative(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.estimate_trace_storage_cost(g, 7)
        assert result.estimated_daily_cost >= 0.0

    def test_recommendations_for_high_cost(self):
        e = _engine()
        g = _graph(*[_comp(f"s{i}", f"Svc{i}") for i in range(50)])
        config = _default_config(sampling_strategy=SamplingStrategy.ALWAYS_ON, sampling_rate=1.0)
        result = e.estimate_trace_storage_cost(g, 60, config)
        assert len(result.recommendations) > 0

    def test_default_config_when_none(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.estimate_trace_storage_cost(g, 7, None)
        assert isinstance(result, StorageCostEstimate)


# ===========================================================================
# 10. simulate_collector_scaling
# ===========================================================================


class TestSimulateCollectorScaling:
    def test_returns_result_type(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.simulate_collector_scaling(g, 5000)
        assert isinstance(result, CollectorScalingResult)

    def test_no_scaling_needed_low_volume(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        config = _default_config(collectors=2)
        result = e.simulate_collector_scaling(g, 1000, config)
        assert result.needs_scaling is False

    def test_scaling_needed_high_volume(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        config = _default_config(collectors=1)
        result = e.simulate_collector_scaling(g, 9000, config)
        assert result.needs_scaling is True

    def test_recommended_collectors_increases(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        config = _default_config(collectors=1)
        result = e.simulate_collector_scaling(g, 50000, config)
        assert result.recommended_collectors > result.current_collectors

    def test_utilization_bounded(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.simulate_collector_scaling(g, 5000)
        assert 0.0 <= result.utilization_percent <= 100.0

    def test_headroom_bounded(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.simulate_collector_scaling(g, 5000)
        assert 0.0 <= result.headroom_percent <= 100.0

    def test_single_collector_gets_recommendation(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        config = _default_config(collectors=1)
        result = e.simulate_collector_scaling(g, 100, config)
        assert any("redundant" in r.lower() for r in result.recommendations)

    def test_sufficient_headroom_gets_recommendation(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        config = _default_config(collectors=5)
        result = e.simulate_collector_scaling(g, 100, config)
        assert any("headroom" in r.lower() for r in result.recommendations)

    def test_default_config_when_none(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.simulate_collector_scaling(g, 5000, None)
        assert isinstance(result, CollectorScalingResult)

    def test_spans_per_second_stored(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.simulate_collector_scaling(g, 7777)
        assert result.spans_per_second == 7777

    def test_zero_capacity_constant_gives_full_utilization(self):
        """Edge case: if collector capacity constant is zero, utilization is 100%."""
        e = _engine()
        g = _graph(_comp("api", "API"))
        with patch("faultray.simulator.distributed_tracing_resilience._COLLECTOR_CAPACITY_SPANS_PER_SEC", 0):
            result = e.simulate_collector_scaling(g, 5000)
            assert result.utilization_percent == 100.0


# ===========================================================================
# 11. correlate_trace_with_resilience
# ===========================================================================


class TestCorrelateTraceWithResilience:
    def test_returns_correlation_type(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.correlate_trace_with_resilience(g, _default_config())
        assert isinstance(result, TraceResilienceCorrelation)

    def test_observability_score_bounded(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.correlate_trace_with_resilience(g, _default_config())
        assert 0.0 <= result.observability_score <= 100.0

    def test_resilience_score_bounded(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.correlate_trace_with_resilience(g, _default_config())
        assert 0.0 <= result.resilience_score <= 100.0

    def test_full_coverage_high_obs_score(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        config = _default_config(
            instrumented_services=["api"],
            has_redundant_collectors=True,
            has_tail_sampling=True,
            sampling_strategy=SamplingStrategy.ALWAYS_ON,
            exporters=2,
            collectors=2,
        )
        result = e.correlate_trace_with_resilience(g, config)
        assert result.observability_score >= 80.0

    def test_no_coverage_low_obs_score(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        config = _weak_config()
        result = e.correlate_trace_with_resilience(g, config)
        assert result.observability_score < 50.0

    def test_blind_spots_are_uninstrumented(self):
        e = _engine()
        g = _graph(_comp("api", "API"), _comp("web", "Web"))
        config = _default_config(instrumented_services=["api"])
        result = e.correlate_trace_with_resilience(g, config)
        assert "web" in result.blind_spots

    def test_no_blind_spots_fully_instrumented(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        config = _default_config(instrumented_services=["api"])
        result = e.correlate_trace_with_resilience(g, config)
        assert len(result.blind_spots) == 0

    def test_correlation_strength_values(self):
        e = _engine()
        g = _graph(_comp("api", "API", replicas=3, failover=True))
        config = _default_config(instrumented_services=["api"])
        result = e.correlate_trace_with_resilience(g, config)
        assert result.correlation_strength in ("none", "weak", "moderate", "strong")

    def test_timestamp_present(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.correlate_trace_with_resilience(g, _default_config())
        assert len(result.timestamp) > 0

    def test_recommendations_when_low_coverage(self):
        e = _engine()
        g = _graph(_comp("api", "API"), _comp("web", "Web"))
        config = _default_config(instrumented_services=["api"])
        result = e.correlate_trace_with_resilience(g, config)
        assert any("instrument" in r.lower() for r in result.recommendations)

    def test_empty_graph(self):
        e = _engine()
        g = InfraGraph()
        result = e.correlate_trace_with_resilience(g, _default_config())
        assert result.observability_score >= 0.0

    def test_tail_sampling_recommendation_when_missing(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        config = _default_config(has_tail_sampling=False, instrumented_services=["api"])
        result = e.correlate_trace_with_resilience(g, config)
        assert any("tail" in r.lower() for r in result.recommendations)

    def test_adaptive_strategy_obs_score_bonus(self):
        """Adaptive/tail-based strategy should give higher obs score than probabilistic."""
        e = _engine()
        g = _graph(_comp("api", "API"))
        adaptive_config = _default_config(
            sampling_strategy=SamplingStrategy.ADAPTIVE,
            has_redundant_collectors=False,
            has_tail_sampling=False,
            exporters=1,
            collectors=1,
            instrumented_services=["api"],
        )
        prob_config = _default_config(
            sampling_strategy=SamplingStrategy.PROBABILISTIC,
            has_redundant_collectors=False,
            has_tail_sampling=False,
            exporters=1,
            collectors=1,
            instrumented_services=["api"],
        )
        adaptive_result = e.correlate_trace_with_resilience(g, adaptive_config)
        prob_result = e.correlate_trace_with_resilience(g, prob_config)
        assert adaptive_result.observability_score > prob_result.observability_score


# ===========================================================================
# 12. Integration / cross-method tests
# ===========================================================================


class TestIntegration:
    def test_assess_and_simulate_consistent(self):
        """Pipeline with SPOFs should show higher loss in simulation too."""
        e = _engine()
        g = _graph(_comp("api", "API"), _comp("web", "Web"))
        weak = _weak_config()
        assessment = e.assess_pipeline(g, weak)
        loss_result = e.simulate_trace_loss(g, TraceLossScenario.COLLECTOR_OVERLOAD, weak)
        # Both should indicate issues
        assert assessment.estimated_trace_loss_percent > 0.0
        assert loss_result.estimated_loss_percent > 0.0

    def test_gaps_detected_for_uninstrumented_in_assessment(self):
        e = _engine()
        g = _graph(_comp("api", "API"), _comp("web", "Web"), _comp("db", "DB"))
        config = _default_config(instrumented_services=["api"])
        gaps = e.detect_observability_gaps(g, config)
        assert len(gaps) == 2

    def test_sampling_recommendation_aligns_with_cost(self):
        e = _engine()
        g = _graph(*[_comp(f"s{i}", f"Svc{i}") for i in range(5)])
        rec = e.optimize_sampling(g, 300)
        cost = e.estimate_trace_storage_cost(g, 7, _default_config(sampling_rate=rec.recommended_rate))
        assert cost.estimated_total_cost >= 0.0

    def test_collector_scaling_matches_assessment_bottleneck(self):
        e = _engine()
        g = _graph(*[_comp(f"s{i}", f"Svc{i}") for i in range(20)])
        config = _default_config(collectors=1, has_redundant_collectors=False)
        scaling = e.simulate_collector_scaling(g, 50000, config)
        assert scaling.needs_scaling is True

    def test_full_workflow(self):
        """Complete analysis workflow on a realistic graph."""
        e = _engine()
        g = _graph(
            _comp("lb", "LB", ctype=ComponentType.LOAD_BALANCER),
            _comp("api", "API"),
            _comp("web", "Web", ctype=ComponentType.WEB_SERVER),
            _comp("db", "DB", ctype=ComponentType.DATABASE),
            _comp("cache", "Cache", ctype=ComponentType.CACHE),
        )
        g.add_dependency(Dependency(source_id="lb", target_id="web"))
        g.add_dependency(Dependency(source_id="web", target_id="api"))
        g.add_dependency(Dependency(source_id="api", target_id="db"))
        g.add_dependency(Dependency(source_id="api", target_id="cache"))

        config = _default_config(instrumented_services=["api", "web", "db"])

        assess = e.assess_pipeline(g, config)
        assert isinstance(assess, TracePipelineAssessment)

        gaps = e.detect_observability_gaps(g, config)
        gap_ids = {gap.component_id for gap in gaps}
        assert "lb" in gap_ids
        assert "cache" in gap_ids

        cost = e.estimate_trace_storage_cost(g, 14, config)
        assert cost.estimated_total_cost > 0.0

        for scenario in TraceLossScenario:
            r = e.simulate_trace_loss(g, scenario, config)
            assert isinstance(r, TraceLossResult)

        corr = e.correlate_trace_with_resilience(g, config)
        assert isinstance(corr, TraceResilienceCorrelation)
