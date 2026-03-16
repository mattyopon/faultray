"""Tests for the Observability Gap Analyzer."""

from __future__ import annotations

import pytest

from faultray.model.components import Component, ComponentType, Dependency
from faultray.model.graph import InfraGraph
from faultray.simulator.observability_gap_analyzer import (
    AlertCoverageResult,
    AlertMapping,
    BlindSpot,
    CorrelationAnalysisResult,
    CorrelationCapability,
    CostOptimizationResult,
    DashboardConfig,
    DashboardCoverageResult,
    GapSeverity,
    GoldenSignal,
    GoldenSignalAnalysisResult,
    GoldenSignalCoverage,
    LogLevel,
    LogLevelAnalysisResult,
    LogLevelConfig,
    MTTDEstimation,
    ObservabilityGap,
    ObservabilityGapAnalyzer,
    ObservabilityGapReport,
    ObservabilityPillar,
    ObservabilitySetup,
    PillarAnalysisResult,
    PillarCoverage,
    SLIMonitoringConfig,
    SLIMonitoringResult,
    TracePropagation,
    TracingCompletenessResult,
    _ANALYSIS_WEIGHTS,
    _DEFAULT_FAILURE_MODES,
    _MTTD_BASE_MINUTES,
    _MTTD_BEST_MINUTES,
    _QUIET_LEVELS,
    _VERBOSE_VOLUME_THRESHOLD_GB,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(cid: str = "c1", ctype: ComponentType = ComponentType.APP_SERVER) -> Component:
    return Component(id=cid, name=cid, type=ctype)


def _graph(*comps: Component) -> InfraGraph:
    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    return g


def _full_pillar(cid: str) -> PillarCoverage:
    """Full pillar coverage for a component."""
    return PillarCoverage(
        component_id=cid,
        metrics_enabled=True,
        logs_enabled=True,
        traces_enabled=True,
        metrics_completeness=1.0,
        logs_completeness=1.0,
        traces_completeness=1.0,
    )


def _full_golden(cid: str) -> GoldenSignalCoverage:
    """Full golden signal coverage for a component."""
    return GoldenSignalCoverage(
        component_id=cid,
        latency_monitored=True,
        traffic_monitored=True,
        errors_monitored=True,
        saturation_monitored=True,
    )


def _full_alert(cid: str, ctype: ComponentType = ComponentType.APP_SERVER) -> AlertMapping:
    """Alert mapping covering all default failure modes for a component type."""
    modes = _DEFAULT_FAILURE_MODES.get(ctype, ["unknown_failure"])
    return AlertMapping(component_id=cid, failure_modes=modes, alerted_modes=modes)


def _full_dashboard(cid: str) -> DashboardConfig:
    return DashboardConfig(component_id=cid, has_dashboard=True, metrics_on_dashboard=10)


def _full_sli(cid: str) -> SLIMonitoringConfig:
    return SLIMonitoringConfig(
        component_id=cid,
        sli_defined=True,
        slo_defined=True,
        error_budget_tracking=True,
        burn_rate_alerting=True,
    )


def _balanced_log(cid: str) -> LogLevelConfig:
    return LogLevelConfig(component_id=cid, level=LogLevel.INFO, estimated_volume_gb_per_day=2.0)


def _full_setup(
    cids: list[str],
    ctypes: list[ComponentType] | None = None,
    graph: InfraGraph | None = None,
) -> ObservabilitySetup:
    """Build a fully observed setup for given component ids."""
    if ctypes is None:
        ctypes = [ComponentType.APP_SERVER] * len(cids)

    props: list[TracePropagation] = []
    if graph is not None:
        for dep in graph.all_dependency_edges():
            props.append(TracePropagation(source_id=dep.source_id, target_id=dep.target_id, propagation_enabled=True))

    return ObservabilitySetup(
        pillar_coverage=[_full_pillar(c) for c in cids],
        golden_signal_coverage=[_full_golden(c) for c in cids],
        alert_mappings=[_full_alert(c, ct) for c, ct in zip(cids, ctypes)],
        trace_propagations=props,
        log_level_configs=[_balanced_log(c) for c in cids],
        dashboard_configs=[_full_dashboard(c) for c in cids],
        sli_monitoring_configs=[_full_sli(c) for c in cids],
    )


# ===================================================================
# Enum tests
# ===================================================================


class TestEnums:
    def test_observability_pillar_values(self):
        assert set(ObservabilityPillar) == {
            ObservabilityPillar.METRICS,
            ObservabilityPillar.LOGS,
            ObservabilityPillar.TRACES,
        }

    def test_golden_signal_values(self):
        assert set(GoldenSignal) == {
            GoldenSignal.LATENCY,
            GoldenSignal.TRAFFIC,
            GoldenSignal.ERRORS,
            GoldenSignal.SATURATION,
        }

    def test_gap_severity_values(self):
        assert len(GapSeverity) == 5
        assert GapSeverity.CRITICAL.value == "critical"
        assert GapSeverity.INFO.value == "info"

    def test_log_level_values(self):
        assert len(LogLevel) == 5
        assert LogLevel.DEBUG.value == "debug"

    def test_correlation_capability_values(self):
        assert set(CorrelationCapability) == {
            CorrelationCapability.NONE,
            CorrelationCapability.PARTIAL,
            CorrelationCapability.FULL,
        }


# ===================================================================
# Data model tests
# ===================================================================


class TestDataModels:
    def test_pillar_coverage_defaults(self):
        pc = PillarCoverage(component_id="x")
        assert not pc.metrics_enabled
        assert not pc.logs_enabled
        assert not pc.traces_enabled
        assert pc.metrics_completeness == 0.0

    def test_golden_signal_coverage_defaults(self):
        gs = GoldenSignalCoverage(component_id="x")
        assert not gs.latency_monitored
        assert not gs.errors_monitored

    def test_alert_mapping_defaults(self):
        am = AlertMapping(component_id="x")
        assert am.failure_modes == []
        assert am.alerted_modes == []

    def test_trace_propagation_defaults(self):
        tp = TracePropagation(source_id="a", target_id="b")
        assert not tp.propagation_enabled

    def test_log_level_config_defaults(self):
        lc = LogLevelConfig(component_id="x")
        assert lc.level == LogLevel.INFO
        assert lc.estimated_volume_gb_per_day == 1.0

    def test_dashboard_config_defaults(self):
        dc = DashboardConfig(component_id="x")
        assert not dc.has_dashboard
        assert dc.metrics_on_dashboard == 0

    def test_sli_monitoring_config_defaults(self):
        sc = SLIMonitoringConfig(component_id="x")
        assert not sc.sli_defined
        assert not sc.slo_defined
        assert not sc.error_budget_tracking
        assert not sc.burn_rate_alerting

    def test_observability_setup_defaults(self):
        s = ObservabilitySetup()
        assert s.pillar_coverage == []
        assert s.monthly_observability_cost_usd == 0.0

    def test_gap_report_defaults(self):
        r = ObservabilityGapReport()
        assert r.total_components == 0
        assert r.overall_score == 0.0
        assert r.gaps == []
        assert r.blind_spots == []


# ===================================================================
# Constants tests
# ===================================================================


class TestConstants:
    def test_analysis_weights_sum_to_one(self):
        assert abs(sum(_ANALYSIS_WEIGHTS.values()) - 1.0) < 1e-9

    def test_default_failure_modes_all_component_types(self):
        for ct in ComponentType:
            assert ct in _DEFAULT_FAILURE_MODES

    def test_verbose_threshold(self):
        assert _VERBOSE_VOLUME_THRESHOLD_GB == 5.0

    def test_quiet_levels(self):
        assert LogLevel.ERROR in _QUIET_LEVELS
        assert LogLevel.CRITICAL in _QUIET_LEVELS
        assert LogLevel.INFO not in _QUIET_LEVELS

    def test_mttd_bounds(self):
        assert _MTTD_BEST_MINUTES < _MTTD_BASE_MINUTES


# ===================================================================
# Empty graph tests
# ===================================================================


class TestEmptyGraph:
    def test_analyze_empty_graph(self):
        g = _graph()
        analyzer = ObservabilityGapAnalyzer(g)
        report = analyzer.analyze(ObservabilitySetup())
        assert report.total_components == 0
        assert "No components" in report.summary

    def test_pillars_empty(self):
        g = _graph()
        analyzer = ObservabilityGapAnalyzer(g)
        r = analyzer.analyze_pillars([], [])
        assert r.total_components == 0
        assert r.pillar_score == 0.0

    def test_golden_signals_empty(self):
        g = _graph()
        analyzer = ObservabilityGapAnalyzer(g)
        r = analyzer.analyze_golden_signals([], [])
        assert r.total_components == 0

    def test_log_levels_empty(self):
        g = _graph()
        analyzer = ObservabilityGapAnalyzer(g)
        r = analyzer.analyze_log_levels([], [])
        assert r.total_components == 0
        assert r.balance_score == 0.0

    def test_dashboard_empty(self):
        g = _graph()
        analyzer = ObservabilityGapAnalyzer(g)
        r = analyzer.analyze_dashboard_coverage([], [])
        assert r.total_components == 0

    def test_sli_monitoring_empty(self):
        g = _graph()
        analyzer = ObservabilityGapAnalyzer(g)
        r = analyzer.analyze_sli_monitoring([], [])
        assert r.total_components == 0


# ===================================================================
# Pillar analysis tests
# ===================================================================


class TestPillarAnalysis:
    def test_full_coverage(self):
        c = _comp("a1")
        g = _graph(c)
        analyzer = ObservabilityGapAnalyzer(g)
        result = analyzer.analyze_pillars(
            [_full_pillar("a1")], [c]
        )
        assert result.metrics_covered == 1
        assert result.logs_covered == 1
        assert result.traces_covered == 1
        assert result.pillar_score == 100.0

    def test_partial_coverage(self):
        c = _comp("a1")
        g = _graph(c)
        analyzer = ObservabilityGapAnalyzer(g)
        pc = PillarCoverage(
            component_id="a1",
            metrics_enabled=True,
            logs_enabled=False,
            traces_enabled=False,
            metrics_completeness=1.0,
        )
        result = analyzer.analyze_pillars([pc], [c])
        assert result.metrics_covered == 1
        assert result.logs_covered == 0
        assert result.traces_covered == 0
        # Score: (1/1 * 1.0 * 100 + 0 + 0) / 3 = 33.3
        assert 33.0 <= result.pillar_score <= 34.0

    def test_no_coverage_entry(self):
        """Component present but no PillarCoverage entry for it."""
        c = _comp("a1")
        g = _graph(c)
        analyzer = ObservabilityGapAnalyzer(g)
        result = analyzer.analyze_pillars([], [c])
        assert result.metrics_covered == 0
        assert result.pillar_score == 0.0

    def test_completeness_factor(self):
        c = _comp("a1")
        g = _graph(c)
        analyzer = ObservabilityGapAnalyzer(g)
        pc = PillarCoverage(
            component_id="a1",
            metrics_enabled=True,
            logs_enabled=True,
            traces_enabled=True,
            metrics_completeness=0.5,
            logs_completeness=0.5,
            traces_completeness=0.5,
        )
        result = analyzer.analyze_pillars([pc], [c])
        assert result.average_metrics_completeness == 0.5
        assert result.pillar_score == 50.0

    def test_multi_component(self):
        c1 = _comp("a1")
        c2 = _comp("a2")
        g = _graph(c1, c2)
        analyzer = ObservabilityGapAnalyzer(g)
        result = analyzer.analyze_pillars(
            [_full_pillar("a1")], [c1, c2]
        )
        # Only a1 covered: metrics 1/2, logs 1/2, traces 1/2 each with completeness 1.0
        # Score: (0.5*1.0*100 + 0.5*1.0*100 + 0.5*1.0*100) / 3 = 50.0
        assert result.pillar_score == 50.0


# ===================================================================
# Golden signal analysis tests
# ===================================================================


class TestGoldenSignalAnalysis:
    def test_full_golden_coverage(self):
        c = _comp("a1")
        g = _graph(c)
        analyzer = ObservabilityGapAnalyzer(g)
        result = analyzer.analyze_golden_signals([_full_golden("a1")], [c])
        assert result.coverage_score == 100.0
        assert result.latency_covered == 1
        assert result.traffic_covered == 1
        assert result.errors_covered == 1
        assert result.saturation_covered == 1

    def test_no_golden_coverage(self):
        c = _comp("a1")
        g = _graph(c)
        analyzer = ObservabilityGapAnalyzer(g)
        result = analyzer.analyze_golden_signals([], [c])
        assert result.coverage_score == 0.0

    def test_partial_golden(self):
        c = _comp("a1")
        g = _graph(c)
        analyzer = ObservabilityGapAnalyzer(g)
        gs = GoldenSignalCoverage(
            component_id="a1",
            latency_monitored=True,
            traffic_monitored=True,
            errors_monitored=False,
            saturation_monitored=False,
        )
        result = analyzer.analyze_golden_signals([gs], [c])
        assert result.latency_covered == 1
        assert result.errors_covered == 0
        assert result.coverage_score == 50.0

    def test_multiple_components_golden(self):
        c1 = _comp("a1")
        c2 = _comp("a2")
        g = _graph(c1, c2)
        analyzer = ObservabilityGapAnalyzer(g)
        result = analyzer.analyze_golden_signals(
            [_full_golden("a1")], [c1, c2]
        )
        # 4 covered out of 8 total = 50%
        assert result.coverage_score == 50.0


# ===================================================================
# Alert coverage tests
# ===================================================================


class TestAlertCoverage:
    def test_full_alert_coverage(self):
        c = _comp("a1")
        g = _graph(c)
        analyzer = ObservabilityGapAnalyzer(g)
        result = analyzer.analyze_alert_coverage(
            [_full_alert("a1", ComponentType.APP_SERVER)], [c]
        )
        assert result.coverage_percent == 100.0
        assert result.unalerted_failure_modes == 0

    def test_no_alert_coverage(self):
        c = _comp("a1")
        g = _graph(c)
        analyzer = ObservabilityGapAnalyzer(g)
        result = analyzer.analyze_alert_coverage([], [c])
        # Should use default failure modes for APP_SERVER
        default_modes = _DEFAULT_FAILURE_MODES[ComponentType.APP_SERVER]
        assert result.total_failure_modes == len(default_modes)
        assert result.alerted_failure_modes == 0
        assert result.unalerted_failure_modes == len(default_modes)

    def test_partial_alert_coverage(self):
        c = _comp("a1")
        g = _graph(c)
        analyzer = ObservabilityGapAnalyzer(g)
        am = AlertMapping(
            component_id="a1",
            failure_modes=["high_latency", "5xx_errors", "memory_leak"],
            alerted_modes=["high_latency"],
        )
        result = analyzer.analyze_alert_coverage([am], [c])
        assert result.total_failure_modes == 3
        assert result.alerted_failure_modes == 1
        assert result.unalerted_failure_modes == 2
        assert len(result.unalerted_details) == 2

    def test_default_failure_modes_for_database(self):
        c = _comp("db1", ComponentType.DATABASE)
        g = _graph(c)
        analyzer = ObservabilityGapAnalyzer(g)
        result = analyzer.analyze_alert_coverage([], [c])
        db_modes = _DEFAULT_FAILURE_MODES[ComponentType.DATABASE]
        assert result.total_failure_modes == len(db_modes)


# ===================================================================
# Tracing completeness tests
# ===================================================================


class TestTracingCompleteness:
    def test_no_edges_complete(self):
        c = _comp("a1")
        g = _graph(c)
        analyzer = ObservabilityGapAnalyzer(g)
        result = analyzer.analyze_tracing_completeness([])
        assert result.completeness_percent == 100.0
        assert result.total_edges == 0

    def test_full_propagation(self):
        c1 = _comp("a1")
        c2 = _comp("b1")
        g = _graph(c1, c2)
        g.add_dependency(Dependency(source_id="a1", target_id="b1"))
        analyzer = ObservabilityGapAnalyzer(g)
        props = [TracePropagation(source_id="a1", target_id="b1", propagation_enabled=True)]
        result = analyzer.analyze_tracing_completeness(props)
        assert result.total_edges == 1
        assert result.propagated_edges == 1
        assert result.completeness_percent == 100.0
        assert result.gap_edges == []

    def test_gap_in_propagation(self):
        c1 = _comp("a1")
        c2 = _comp("b1")
        g = _graph(c1, c2)
        g.add_dependency(Dependency(source_id="a1", target_id="b1"))
        analyzer = ObservabilityGapAnalyzer(g)
        result = analyzer.analyze_tracing_completeness([])
        assert result.completeness_percent == 0.0
        assert result.gap_edges == [("a1", "b1")]

    def test_disabled_propagation_is_gap(self):
        c1 = _comp("a1")
        c2 = _comp("b1")
        g = _graph(c1, c2)
        g.add_dependency(Dependency(source_id="a1", target_id="b1"))
        analyzer = ObservabilityGapAnalyzer(g)
        props = [TracePropagation(source_id="a1", target_id="b1", propagation_enabled=False)]
        result = analyzer.analyze_tracing_completeness(props)
        assert result.completeness_percent == 0.0

    def test_partial_propagation(self):
        c1 = _comp("a1")
        c2 = _comp("b1")
        c3 = _comp("c1", ComponentType.DATABASE)
        g = _graph(c1, c2, c3)
        g.add_dependency(Dependency(source_id="a1", target_id="b1"))
        g.add_dependency(Dependency(source_id="b1", target_id="c1"))
        analyzer = ObservabilityGapAnalyzer(g)
        props = [TracePropagation(source_id="a1", target_id="b1", propagation_enabled=True)]
        result = analyzer.analyze_tracing_completeness(props)
        assert result.total_edges == 2
        assert result.propagated_edges == 1
        assert result.completeness_percent == 50.0
        assert ("b1", "c1") in result.gap_edges


# ===================================================================
# Log level analysis tests
# ===================================================================


class TestLogLevelAnalysis:
    def test_balanced_logs(self):
        c = _comp("a1")
        g = _graph(c)
        analyzer = ObservabilityGapAnalyzer(g)
        lc = LogLevelConfig(component_id="a1", level=LogLevel.INFO, estimated_volume_gb_per_day=2.0)
        result = analyzer.analyze_log_levels([lc], [c])
        assert result.balanced == ["a1"]
        assert result.too_verbose == []
        assert result.too_quiet == []
        assert result.balance_score == 100.0

    def test_verbose_debug_high_volume(self):
        c = _comp("a1")
        g = _graph(c)
        analyzer = ObservabilityGapAnalyzer(g)
        lc = LogLevelConfig(component_id="a1", level=LogLevel.DEBUG, estimated_volume_gb_per_day=10.0)
        result = analyzer.analyze_log_levels([lc], [c])
        assert result.too_verbose == ["a1"]
        assert result.balance_score == 0.0

    def test_debug_low_volume_not_verbose(self):
        c = _comp("a1")
        g = _graph(c)
        analyzer = ObservabilityGapAnalyzer(g)
        lc = LogLevelConfig(component_id="a1", level=LogLevel.DEBUG, estimated_volume_gb_per_day=1.0)
        result = analyzer.analyze_log_levels([lc], [c])
        # DEBUG with low volume is balanced (below threshold)
        assert result.balanced == ["a1"]

    def test_quiet_error_only(self):
        c = _comp("a1")
        g = _graph(c)
        analyzer = ObservabilityGapAnalyzer(g)
        lc = LogLevelConfig(component_id="a1", level=LogLevel.ERROR, estimated_volume_gb_per_day=0.1)
        result = analyzer.analyze_log_levels([lc], [c])
        assert result.too_quiet == ["a1"]

    def test_quiet_critical_only(self):
        c = _comp("a1")
        g = _graph(c)
        analyzer = ObservabilityGapAnalyzer(g)
        lc = LogLevelConfig(component_id="a1", level=LogLevel.CRITICAL, estimated_volume_gb_per_day=0.01)
        result = analyzer.analyze_log_levels([lc], [c])
        assert result.too_quiet == ["a1"]

    def test_no_config_is_quiet(self):
        c = _comp("a1")
        g = _graph(c)
        analyzer = ObservabilityGapAnalyzer(g)
        result = analyzer.analyze_log_levels([], [c])
        assert result.too_quiet == ["a1"]
        assert result.balance_score == 0.0

    def test_volume_accumulation(self):
        c1 = _comp("a1")
        c2 = _comp("a2")
        g = _graph(c1, c2)
        analyzer = ObservabilityGapAnalyzer(g)
        lcs = [
            LogLevelConfig(component_id="a1", level=LogLevel.INFO, estimated_volume_gb_per_day=3.0),
            LogLevelConfig(component_id="a2", level=LogLevel.WARNING, estimated_volume_gb_per_day=2.0),
        ]
        result = analyzer.analyze_log_levels(lcs, [c1, c2])
        assert result.estimated_daily_volume_gb == 5.0
        assert result.balance_score == 100.0


# ===================================================================
# Dashboard coverage tests
# ===================================================================


class TestDashboardCoverage:
    def test_full_dashboard_coverage(self):
        c = _comp("a1")
        g = _graph(c)
        analyzer = ObservabilityGapAnalyzer(g)
        result = analyzer.analyze_dashboard_coverage([_full_dashboard("a1")], [c])
        assert result.components_with_dashboard == 1
        assert result.coverage_percent == 100.0
        assert result.average_metrics_per_dashboard == 10.0

    def test_no_dashboard(self):
        c = _comp("a1")
        g = _graph(c)
        analyzer = ObservabilityGapAnalyzer(g)
        result = analyzer.analyze_dashboard_coverage([], [c])
        assert result.components_with_dashboard == 0
        assert result.coverage_percent == 0.0

    def test_dashboard_present_but_disabled(self):
        c = _comp("a1")
        g = _graph(c)
        analyzer = ObservabilityGapAnalyzer(g)
        dc = DashboardConfig(component_id="a1", has_dashboard=False)
        result = analyzer.analyze_dashboard_coverage([dc], [c])
        assert result.components_with_dashboard == 0

    def test_multiple_dashboards_avg_metrics(self):
        c1 = _comp("a1")
        c2 = _comp("a2")
        g = _graph(c1, c2)
        analyzer = ObservabilityGapAnalyzer(g)
        dcs = [
            DashboardConfig(component_id="a1", has_dashboard=True, metrics_on_dashboard=6),
            DashboardConfig(component_id="a2", has_dashboard=True, metrics_on_dashboard=4),
        ]
        result = analyzer.analyze_dashboard_coverage(dcs, [c1, c2])
        assert result.average_metrics_per_dashboard == 5.0
        assert result.coverage_percent == 100.0


# ===================================================================
# SLI/SLO monitoring tests
# ===================================================================


class TestSLIMonitoring:
    def test_full_sli_monitoring(self):
        c = _comp("a1")
        g = _graph(c)
        analyzer = ObservabilityGapAnalyzer(g)
        result = analyzer.analyze_sli_monitoring([_full_sli("a1")], [c])
        assert result.maturity_score == 100.0
        assert result.sli_defined_count == 1
        assert result.slo_defined_count == 1
        assert result.error_budget_tracking_count == 1
        assert result.burn_rate_alerting_count == 1

    def test_no_sli_monitoring(self):
        c = _comp("a1")
        g = _graph(c)
        analyzer = ObservabilityGapAnalyzer(g)
        result = analyzer.analyze_sli_monitoring([], [c])
        assert result.maturity_score == 0.0

    def test_partial_sli(self):
        c = _comp("a1")
        g = _graph(c)
        analyzer = ObservabilityGapAnalyzer(g)
        sc = SLIMonitoringConfig(
            component_id="a1",
            sli_defined=True,
            slo_defined=True,
            error_budget_tracking=False,
            burn_rate_alerting=False,
        )
        result = analyzer.analyze_sli_monitoring([sc], [c])
        # 30% + 30% + 0 + 0 = 60%
        assert result.maturity_score == 60.0


# ===================================================================
# Correlation analysis tests
# ===================================================================


class TestCorrelationAnalysis:
    def test_full_correlation(self):
        g = _graph(_comp("a1"))
        analyzer = ObservabilityGapAnalyzer(g)
        pc = [_full_pillar("a1")]
        tp = [TracePropagation(source_id="a1", target_id="x", propagation_enabled=True)]
        result = analyzer.analyze_correlation(pc, tp)
        assert result.capability == CorrelationCapability.FULL
        assert result.score == 100.0
        assert result.metrics_logs_correlated
        assert result.metrics_traces_correlated
        assert result.logs_traces_correlated

    def test_no_correlation(self):
        g = _graph(_comp("a1"))
        analyzer = ObservabilityGapAnalyzer(g)
        result = analyzer.analyze_correlation([], [])
        assert result.capability == CorrelationCapability.NONE
        assert result.score == 0.0

    def test_partial_correlation_metrics_logs_only(self):
        g = _graph(_comp("a1"))
        analyzer = ObservabilityGapAnalyzer(g)
        pc = [PillarCoverage(
            component_id="a1",
            metrics_enabled=True,
            logs_enabled=True,
            traces_enabled=False,
        )]
        result = analyzer.analyze_correlation(pc, [])
        assert result.capability == CorrelationCapability.PARTIAL
        assert result.metrics_logs_correlated
        assert not result.metrics_traces_correlated
        assert not result.logs_traces_correlated
        assert abs(result.score - 33.3) < 0.1

    def test_traces_without_propagation(self):
        """Even if traces enabled, no propagation means no trace correlation."""
        g = _graph(_comp("a1"))
        analyzer = ObservabilityGapAnalyzer(g)
        pc = [PillarCoverage(
            component_id="a1",
            metrics_enabled=True,
            logs_enabled=True,
            traces_enabled=True,
        )]
        result = analyzer.analyze_correlation(pc, [])
        # No propagation => metrics_traces and logs_traces are False
        assert result.metrics_logs_correlated
        assert not result.metrics_traces_correlated
        assert result.capability == CorrelationCapability.PARTIAL


# ===================================================================
# Blind spot detection tests
# ===================================================================


class TestBlindSpotDetection:
    def test_no_blind_spots_when_covered(self):
        c = _comp("a1")
        g = _graph(c)
        analyzer = ObservabilityGapAnalyzer(g)
        spots = analyzer.detect_blind_spots([_full_pillar("a1")], [c])
        assert spots == []

    def test_all_blind_spots(self):
        c1 = _comp("a1")
        c2 = _comp("a2", ComponentType.DATABASE)
        g = _graph(c1, c2)
        analyzer = ObservabilityGapAnalyzer(g)
        spots = analyzer.detect_blind_spots([], [c1, c2])
        assert len(spots) == 2
        ids = {s.component_id for s in spots}
        assert ids == {"a1", "a2"}
        for s in spots:
            assert s.severity == GapSeverity.CRITICAL

    def test_partial_pillar_not_blind_spot(self):
        """A component with at least one pillar enabled is not a blind spot."""
        c = _comp("a1")
        g = _graph(c)
        analyzer = ObservabilityGapAnalyzer(g)
        pc = PillarCoverage(component_id="a1", metrics_enabled=True)
        spots = analyzer.detect_blind_spots([pc], [c])
        assert spots == []

    def test_all_pillars_disabled_is_blind_spot(self):
        c = _comp("a1")
        g = _graph(c)
        analyzer = ObservabilityGapAnalyzer(g)
        pc = PillarCoverage(component_id="a1", metrics_enabled=False, logs_enabled=False, traces_enabled=False)
        spots = analyzer.detect_blind_spots([pc], [c])
        assert len(spots) == 1
        assert spots[0].component_id == "a1"


# ===================================================================
# MTTD estimation tests
# ===================================================================


class TestMTTDEstimation:
    def test_excellent_mttd(self):
        g = _graph(_comp("a1"))
        analyzer = ObservabilityGapAnalyzer(g)
        gs_result = GoldenSignalAnalysisResult(
            total_components=1, coverage_score=100.0,
            latency_covered=1, traffic_covered=1, errors_covered=1, saturation_covered=1,
        )
        alert_result = AlertCoverageResult(
            total_failure_modes=4, alerted_failure_modes=4, coverage_percent=100.0,
        )
        pillar_result = PillarAnalysisResult(
            total_components=1, pillar_score=100.0,
        )
        mttd = analyzer.estimate_mttd(gs_result, alert_result, pillar_result)
        assert mttd.estimated_mttd_minutes <= 5.0
        assert mttd.rating == "excellent"

    def test_poor_mttd(self):
        g = _graph(_comp("a1"))
        analyzer = ObservabilityGapAnalyzer(g)
        gs_result = GoldenSignalAnalysisResult(total_components=1, coverage_score=0.0)
        alert_result = AlertCoverageResult(coverage_percent=0.0)
        pillar_result = PillarAnalysisResult(total_components=1, pillar_score=0.0)
        mttd = analyzer.estimate_mttd(gs_result, alert_result, pillar_result)
        assert mttd.estimated_mttd_minutes == _MTTD_BASE_MINUTES
        assert mttd.rating == "poor"

    def test_fair_mttd(self):
        g = _graph(_comp("a1"))
        analyzer = ObservabilityGapAnalyzer(g)
        gs_result = GoldenSignalAnalysisResult(total_components=1, coverage_score=50.0)
        alert_result = AlertCoverageResult(coverage_percent=50.0)
        pillar_result = PillarAnalysisResult(total_components=1, pillar_score=50.0)
        mttd = analyzer.estimate_mttd(gs_result, alert_result, pillar_result)
        # 50% coverage -> combined = 0.5, mttd = 60 - 59 * 0.5 = 30.5
        assert 25.0 <= mttd.estimated_mttd_minutes <= 35.0
        assert mttd.rating in ("fair", "poor")

    def test_good_mttd(self):
        """MTTD between 5 and 15 should rate 'good'."""
        g = _graph(_comp("a1"))
        analyzer = ObservabilityGapAnalyzer(g)
        # We need combined ~= 0.83 to get mttd ~= 60 - 59*0.83 = 11.0
        gs_result = GoldenSignalAnalysisResult(total_components=1, coverage_score=85.0)
        alert_result = AlertCoverageResult(coverage_percent=85.0)
        pillar_result = PillarAnalysisResult(total_components=1, pillar_score=80.0)
        mttd = analyzer.estimate_mttd(gs_result, alert_result, pillar_result)
        assert 5.0 < mttd.estimated_mttd_minutes <= 15.0
        assert mttd.rating == "good"

    def test_contributing_factors_low(self):
        g = _graph(_comp("a1"))
        analyzer = ObservabilityGapAnalyzer(g)
        gs_result = GoldenSignalAnalysisResult(total_components=1, coverage_score=20.0)
        alert_result = AlertCoverageResult(coverage_percent=20.0)
        pillar_result = PillarAnalysisResult(total_components=1, pillar_score=20.0)
        mttd = analyzer.estimate_mttd(gs_result, alert_result, pillar_result)
        assert len(mttd.contributing_factors) >= 3


# ===================================================================
# Cost optimization tests
# ===================================================================


class TestCostOptimization:
    def test_under_budget(self):
        g = _graph(_comp("a1"))
        analyzer = ObservabilityGapAnalyzer(g)
        setup = ObservabilitySetup(
            monthly_observability_cost_usd=100.0,
            target_monthly_budget_usd=200.0,
        )
        result = analyzer.analyze_cost(setup)
        assert not result.over_budget

    def test_over_budget(self):
        g = _graph(_comp("a1"))
        analyzer = ObservabilityGapAnalyzer(g)
        setup = ObservabilitySetup(
            monthly_observability_cost_usd=300.0,
            target_monthly_budget_usd=200.0,
        )
        result = analyzer.analyze_cost(setup)
        assert result.over_budget
        assert any("over budget" in s for s in result.savings_opportunities)

    def test_no_budget_set(self):
        g = _graph(_comp("a1"))
        analyzer = ObservabilityGapAnalyzer(g)
        setup = ObservabilitySetup(monthly_observability_cost_usd=100.0)
        result = analyzer.analyze_cost(setup)
        assert not result.over_budget

    def test_verbose_logging_savings(self):
        g = _graph(_comp("a1"))
        analyzer = ObservabilityGapAnalyzer(g)
        setup = ObservabilitySetup(
            log_level_configs=[
                LogLevelConfig(component_id="a1", level=LogLevel.DEBUG, estimated_volume_gb_per_day=10.0),
            ],
        )
        result = analyzer.analyze_cost(setup)
        assert result.estimated_savings_usd > 0
        assert any("DEBUG" in s for s in result.savings_opportunities)

    def test_empty_dashboard_savings(self):
        g = _graph(_comp("a1"))
        analyzer = ObservabilityGapAnalyzer(g)
        setup = ObservabilitySetup(
            dashboard_configs=[
                DashboardConfig(component_id="a1", has_dashboard=True, metrics_on_dashboard=0),
            ],
        )
        result = analyzer.analyze_cost(setup)
        assert any("0 metrics" in s for s in result.savings_opportunities)


# ===================================================================
# Gap generation tests
# ===================================================================


class TestGapGeneration:
    def test_pillar_gaps_missing_two(self):
        c = _comp("a1")
        g = _graph(c)
        analyzer = ObservabilityGapAnalyzer(g)
        pc = PillarCoverage(component_id="a1", metrics_enabled=True)
        pillar_result = analyzer.analyze_pillars([pc], [c])
        gaps = analyzer._gaps_from_pillars(pillar_result, [pc], [c])
        assert len(gaps) == 1
        assert gaps[0].severity == GapSeverity.HIGH
        assert "logs" in gaps[0].description
        assert "traces" in gaps[0].description

    def test_pillar_gaps_missing_one(self):
        c = _comp("a1")
        g = _graph(c)
        analyzer = ObservabilityGapAnalyzer(g)
        pc = PillarCoverage(component_id="a1", metrics_enabled=True, logs_enabled=True)
        pillar_result = analyzer.analyze_pillars([pc], [c])
        gaps = analyzer._gaps_from_pillars(pillar_result, [pc], [c])
        assert len(gaps) == 1
        assert gaps[0].severity == GapSeverity.MEDIUM

    def test_pillar_gaps_only_metrics_disabled(self):
        """Cover line where metrics is the sole missing pillar."""
        c = _comp("a1")
        g = _graph(c)
        analyzer = ObservabilityGapAnalyzer(g)
        pc = PillarCoverage(component_id="a1", metrics_enabled=False, logs_enabled=True, traces_enabled=True)
        pillar_result = analyzer.analyze_pillars([pc], [c])
        gaps = analyzer._gaps_from_pillars(pillar_result, [pc], [c])
        assert len(gaps) == 1
        assert "metrics" in gaps[0].description
        assert gaps[0].severity == GapSeverity.MEDIUM

    def test_golden_signal_gaps_missing_three(self):
        c = _comp("a1")
        g = _graph(c)
        analyzer = ObservabilityGapAnalyzer(g)
        gs = GoldenSignalCoverage(component_id="a1", latency_monitored=True)
        gs_result = analyzer.analyze_golden_signals([gs], [c])
        gaps = analyzer._gaps_from_golden_signals(gs_result, [gs], [c])
        assert len(gaps) == 1
        assert gaps[0].severity == GapSeverity.HIGH

    def test_golden_signal_gaps_missing_two(self):
        c = _comp("a1")
        g = _graph(c)
        analyzer = ObservabilityGapAnalyzer(g)
        gs = GoldenSignalCoverage(
            component_id="a1", latency_monitored=True, traffic_monitored=True,
        )
        gs_result = analyzer.analyze_golden_signals([gs], [c])
        gaps = analyzer._gaps_from_golden_signals(gs_result, [gs], [c])
        assert len(gaps) == 1
        assert gaps[0].severity == GapSeverity.MEDIUM

    def test_golden_signal_gaps_only_latency_missing(self):
        """Cover line where latency is the sole missing golden signal."""
        c = _comp("a1")
        g = _graph(c)
        analyzer = ObservabilityGapAnalyzer(g)
        gs = GoldenSignalCoverage(
            component_id="a1",
            latency_monitored=False,
            traffic_monitored=True,
            errors_monitored=True,
            saturation_monitored=True,
        )
        gs_result = analyzer.analyze_golden_signals([gs], [c])
        gaps = analyzer._gaps_from_golden_signals(gs_result, [gs], [c])
        assert len(gaps) == 1
        assert "latency" in gaps[0].description
        assert gaps[0].severity == GapSeverity.MEDIUM

    def test_alert_gaps(self):
        c = _comp("a1")
        g = _graph(c)
        analyzer = ObservabilityGapAnalyzer(g)
        am = AlertMapping(
            component_id="a1",
            failure_modes=["high_latency", "5xx_errors"],
            alerted_modes=["high_latency"],
        )
        alert_result = analyzer.analyze_alert_coverage([am], [c])
        gaps = analyzer._gaps_from_alerts(alert_result)
        assert len(gaps) == 1
        assert "5xx_errors" in gaps[0].description

    def test_tracing_gaps(self):
        c1 = _comp("a1")
        c2 = _comp("b1")
        g = _graph(c1, c2)
        g.add_dependency(Dependency(source_id="a1", target_id="b1"))
        analyzer = ObservabilityGapAnalyzer(g)
        result = analyzer.analyze_tracing_completeness([])
        gaps = analyzer._gaps_from_tracing(result)
        assert len(gaps) == 1
        assert gaps[0].gap_type == "trace_propagation"

    def test_log_level_gaps(self):
        c1 = _comp("a1")
        c2 = _comp("a2")
        g = _graph(c1, c2)
        analyzer = ObservabilityGapAnalyzer(g)
        lcs = [
            LogLevelConfig(component_id="a1", level=LogLevel.DEBUG, estimated_volume_gb_per_day=10.0),
            LogLevelConfig(component_id="a2", level=LogLevel.ERROR, estimated_volume_gb_per_day=0.1),
        ]
        result = analyzer.analyze_log_levels(lcs, [c1, c2])
        gaps = analyzer._gaps_from_log_levels(result)
        assert len(gaps) == 2
        verbose_gaps = [g for g in gaps if g.severity == GapSeverity.LOW]
        quiet_gaps = [g for g in gaps if g.severity == GapSeverity.MEDIUM]
        assert len(verbose_gaps) == 1
        assert len(quiet_gaps) == 1

    def test_dashboard_gaps(self):
        c = _comp("a1")
        g = _graph(c)
        analyzer = ObservabilityGapAnalyzer(g)
        result = analyzer.analyze_dashboard_coverage([], [c])
        gaps = analyzer._gaps_from_dashboards(result, [], [c])
        assert len(gaps) == 1
        assert gaps[0].gap_type == "dashboard_coverage"

    def test_sli_gap_no_sli(self):
        c = _comp("a1")
        g = _graph(c)
        analyzer = ObservabilityGapAnalyzer(g)
        result = analyzer.analyze_sli_monitoring([], [c])
        gaps = analyzer._gaps_from_sli(result, [], [c])
        assert len(gaps) == 1
        assert gaps[0].severity == GapSeverity.HIGH

    def test_sli_gap_sli_no_slo(self):
        c = _comp("a1")
        g = _graph(c)
        analyzer = ObservabilityGapAnalyzer(g)
        sc = SLIMonitoringConfig(component_id="a1", sli_defined=True, slo_defined=False)
        result = analyzer.analyze_sli_monitoring([sc], [c])
        gaps = analyzer._gaps_from_sli(result, [sc], [c])
        assert len(gaps) == 1
        assert gaps[0].severity == GapSeverity.MEDIUM

    def test_blind_spot_gaps(self):
        c = _comp("a1")
        g = _graph(c)
        analyzer = ObservabilityGapAnalyzer(g)
        spots = [BlindSpot(
            component_id="a1", component_type="app_server",
            severity=GapSeverity.CRITICAL, description="No monitoring.",
        )]
        gaps = analyzer._gaps_from_blind_spots(spots)
        assert len(gaps) == 1
        assert gaps[0].severity == GapSeverity.CRITICAL

    def test_correlation_gap_none(self):
        g = _graph(_comp("a1"))
        analyzer = ObservabilityGapAnalyzer(g)
        result = CorrelationAnalysisResult(capability=CorrelationCapability.NONE, score=0.0)
        gaps = analyzer._gaps_from_correlation(result)
        assert len(gaps) == 1
        assert gaps[0].severity == GapSeverity.HIGH

    def test_correlation_gap_partial(self):
        g = _graph(_comp("a1"))
        analyzer = ObservabilityGapAnalyzer(g)
        result = CorrelationAnalysisResult(
            capability=CorrelationCapability.PARTIAL,
            metrics_logs_correlated=True,
            metrics_traces_correlated=False,
            logs_traces_correlated=False,
            score=33.3,
        )
        gaps = analyzer._gaps_from_correlation(result)
        assert len(gaps) == 1
        assert gaps[0].severity == GapSeverity.MEDIUM
        assert "metrics-traces" in gaps[0].description

    def test_correlation_gap_partial_metrics_logs_missing(self):
        """Explicitly test the case where metrics-logs is the missing pair."""
        g = _graph(_comp("a1"))
        analyzer = ObservabilityGapAnalyzer(g)
        result = CorrelationAnalysisResult(
            capability=CorrelationCapability.PARTIAL,
            metrics_logs_correlated=False,
            metrics_traces_correlated=True,
            logs_traces_correlated=True,
            score=66.7,
        )
        gaps = analyzer._gaps_from_correlation(result)
        assert len(gaps) == 1
        assert "metrics-logs" in gaps[0].description

    def test_correlation_gap_full_no_gap(self):
        g = _graph(_comp("a1"))
        analyzer = ObservabilityGapAnalyzer(g)
        result = CorrelationAnalysisResult(capability=CorrelationCapability.FULL, score=100.0)
        gaps = analyzer._gaps_from_correlation(result)
        assert gaps == []


# ===================================================================
# Full analysis (end-to-end) tests
# ===================================================================


class TestFullAnalysis:
    def test_fully_observed_system(self):
        c1 = _comp("a1")
        c2 = _comp("b1", ComponentType.DATABASE)
        g = _graph(c1, c2)
        g.add_dependency(Dependency(source_id="a1", target_id="b1"))
        analyzer = ObservabilityGapAnalyzer(g)

        setup = _full_setup(["a1", "b1"], [ComponentType.APP_SERVER, ComponentType.DATABASE], g)
        report = analyzer.analyze(setup)

        assert report.total_components == 2
        assert report.overall_score >= 80.0
        assert report.blind_spots == []
        assert report.pillar_analysis.pillar_score == 100.0
        assert report.golden_signal_analysis.coverage_score == 100.0
        assert report.tracing_completeness.completeness_percent == 100.0
        assert "timestamp" in report.timestamp or report.timestamp != ""

    def test_unobserved_system(self):
        c1 = _comp("a1")
        c2 = _comp("b1")
        g = _graph(c1, c2)
        analyzer = ObservabilityGapAnalyzer(g)
        report = analyzer.analyze(ObservabilitySetup())

        assert report.total_components == 2
        assert report.overall_score < 20.0
        assert len(report.blind_spots) == 2
        assert report.critical_gaps >= 2
        assert len(report.recommendations) > 0
        assert report.mttd_estimation.rating == "poor"

    def test_mixed_coverage(self):
        """One component fully observed, one completely unobserved."""
        c1 = _comp("a1")
        c2 = _comp("b1", ComponentType.CACHE)
        g = _graph(c1, c2)
        analyzer = ObservabilityGapAnalyzer(g)

        setup = _full_setup(["a1"], [ComponentType.APP_SERVER])
        report = analyzer.analyze(setup)

        assert report.total_components == 2
        assert len(report.blind_spots) == 1
        assert report.blind_spots[0].component_id == "b1"
        assert 30.0 <= report.overall_score <= 70.0

    def test_report_summary_format(self):
        c = _comp("a1")
        g = _graph(c)
        analyzer = ObservabilityGapAnalyzer(g)
        report = analyzer.analyze(_full_setup(["a1"]))
        assert "Observability Gap Analysis" in report.summary
        assert "1 components" in report.summary

    def test_gap_severity_counts(self):
        c = _comp("a1")
        g = _graph(c)
        analyzer = ObservabilityGapAnalyzer(g)
        report = analyzer.analyze(ObservabilitySetup())
        total = (
            report.critical_gaps + report.high_gaps + report.medium_gaps
            + report.low_gaps + report.info_gaps
        )
        assert total == report.total_gaps

    def test_many_components(self):
        """Test with several components of different types."""
        comps = [
            _comp("lb1", ComponentType.LOAD_BALANCER),
            _comp("web1", ComponentType.WEB_SERVER),
            _comp("app1", ComponentType.APP_SERVER),
            _comp("db1", ComponentType.DATABASE),
            _comp("cache1", ComponentType.CACHE),
        ]
        g = _graph(*comps)
        g.add_dependency(Dependency(source_id="lb1", target_id="web1"))
        g.add_dependency(Dependency(source_id="web1", target_id="app1"))
        g.add_dependency(Dependency(source_id="app1", target_id="db1"))
        g.add_dependency(Dependency(source_id="app1", target_id="cache1"))

        types = [c.type for c in comps]
        cids = [c.id for c in comps]
        setup = _full_setup(cids, types, g)
        analyzer = ObservabilityGapAnalyzer(g)
        report = analyzer.analyze(setup)

        assert report.total_components == 5
        assert report.overall_score >= 80.0
        assert report.tracing_completeness.completeness_percent == 100.0
        assert report.blind_spots == []


# ===================================================================
# Recommendations tests
# ===================================================================


class TestRecommendations:
    def test_blind_spot_recommendation(self):
        c = _comp("a1")
        g = _graph(c)
        analyzer = ObservabilityGapAnalyzer(g)
        report = analyzer.analyze(ObservabilitySetup())
        assert any("blind-spot" in r for r in report.recommendations)

    def test_low_pillar_recommendation(self):
        c = _comp("a1")
        g = _graph(c)
        analyzer = ObservabilityGapAnalyzer(g)
        # Only partial pillar coverage
        setup = ObservabilitySetup(
            pillar_coverage=[PillarCoverage(component_id="a1", metrics_enabled=True, metrics_completeness=0.3)],
        )
        report = analyzer.analyze(setup)
        assert any("Pillar" in r or "pillar" in r for r in report.recommendations)

    def test_over_budget_recommendation(self):
        c = _comp("a1")
        g = _graph(c)
        analyzer = ObservabilityGapAnalyzer(g)
        setup = _full_setup(["a1"])
        setup.monthly_observability_cost_usd = 500.0
        setup.target_monthly_budget_usd = 100.0
        report = analyzer.analyze(setup)
        assert any("exceeds budget" in r for r in report.recommendations)

    def test_tracing_recommendation(self):
        c1 = _comp("a1")
        c2 = _comp("b1")
        g = _graph(c1, c2)
        g.add_dependency(Dependency(source_id="a1", target_id="b1"))
        analyzer = ObservabilityGapAnalyzer(g)
        setup = _full_setup(["a1", "b1"])
        # No trace propagation in setup
        report = analyzer.analyze(setup)
        assert any("propagation" in r.lower() for r in report.recommendations)

    def test_correlation_recommendation(self):
        c = _comp("a1")
        g = _graph(c)
        analyzer = ObservabilityGapAnalyzer(g)
        report = analyzer.analyze(ObservabilitySetup())
        assert any("correlation" in r.lower() for r in report.recommendations)

    def test_quiet_logging_recommendation(self):
        c = _comp("a1")
        g = _graph(c)
        analyzer = ObservabilityGapAnalyzer(g)
        setup = ObservabilitySetup(
            pillar_coverage=[_full_pillar("a1")],
            golden_signal_coverage=[_full_golden("a1")],
            alert_mappings=[_full_alert("a1")],
            log_level_configs=[LogLevelConfig(component_id="a1", level=LogLevel.ERROR)],
            dashboard_configs=[_full_dashboard("a1")],
            sli_monitoring_configs=[_full_sli("a1")],
        )
        report = analyzer.analyze(setup)
        assert any("insufficient" in r.lower() or "quiet" in r.lower() or "too quiet" in r.lower()
                    or "INFO-level" in r for r in report.recommendations)

    def test_verbose_logging_recommendation(self):
        c = _comp("a1")
        g = _graph(c)
        analyzer = ObservabilityGapAnalyzer(g)
        setup = ObservabilitySetup(
            pillar_coverage=[_full_pillar("a1")],
            golden_signal_coverage=[_full_golden("a1")],
            alert_mappings=[_full_alert("a1")],
            log_level_configs=[LogLevelConfig(component_id="a1", level=LogLevel.DEBUG, estimated_volume_gb_per_day=20.0)],
            dashboard_configs=[_full_dashboard("a1")],
            sli_monitoring_configs=[_full_sli("a1")],
        )
        report = analyzer.analyze(setup)
        assert any("verbose" in r.lower() or "DEBUG" in r for r in report.recommendations)


# ===================================================================
# Edge case tests
# ===================================================================


class TestEdgeCases:
    def test_component_not_in_pillar_coverage(self):
        """PillarCoverage for unknown component id should be ignored safely."""
        c = _comp("a1")
        g = _graph(c)
        analyzer = ObservabilityGapAnalyzer(g)
        pc = PillarCoverage(component_id="unknown", metrics_enabled=True, metrics_completeness=1.0)
        result = analyzer.analyze_pillars([pc], [c])
        assert result.metrics_covered == 0

    def test_duplicate_component_ids_in_setup(self):
        """Duplicate ids in coverage lists should use last one via dict mapping."""
        c = _comp("a1")
        g = _graph(c)
        analyzer = ObservabilityGapAnalyzer(g)
        pcs = [
            PillarCoverage(component_id="a1", metrics_enabled=False),
            PillarCoverage(component_id="a1", metrics_enabled=True, metrics_completeness=1.0),
        ]
        # The implementation creates a dict mapping, so last entry wins
        result = analyzer.analyze_pillars(pcs, [c])
        assert result.metrics_covered == 1

    def test_single_component_full_score(self):
        c = _comp("svc1")
        g = _graph(c)
        analyzer = ObservabilityGapAnalyzer(g)
        setup = _full_setup(["svc1"])
        report = analyzer.analyze(setup)
        # With no edges, tracing completeness is 100%
        assert report.overall_score >= 90.0

    def test_warning_log_level_is_balanced(self):
        c = _comp("a1")
        g = _graph(c)
        analyzer = ObservabilityGapAnalyzer(g)
        lc = LogLevelConfig(component_id="a1", level=LogLevel.WARNING, estimated_volume_gb_per_day=1.0)
        result = analyzer.analyze_log_levels([lc], [c])
        assert "a1" in result.balanced

    def test_zero_volume_log(self):
        c = _comp("a1")
        g = _graph(c)
        analyzer = ObservabilityGapAnalyzer(g)
        lc = LogLevelConfig(component_id="a1", level=LogLevel.INFO, estimated_volume_gb_per_day=0.0)
        result = analyzer.analyze_log_levels([lc], [c])
        assert result.estimated_daily_volume_gb == 0.0
        assert result.balanced == ["a1"]

    def test_report_timestamp_iso_format(self):
        c = _comp("a1")
        g = _graph(c)
        analyzer = ObservabilityGapAnalyzer(g)
        report = analyzer.analyze(_full_setup(["a1"]))
        # Should contain T and timezone info
        assert "T" in report.timestamp
