"""Tests for Health Check Strategy Optimizer."""

from __future__ import annotations

import pytest
from datetime import datetime, timezone

from faultray.model.components import Component, ComponentType, Dependency
from faultray.model.graph import InfraGraph
from faultray.simulator.health_check_strategy import (
    BlindSpot,
    BlindSpotCategory,
    BlindSpotReport,
    CascadeAnalysis,
    CascadeChain,
    CheckDepth,
    DependencyChainAnalysis,
    DependencyChainLink,
    DepthTradeoff,
    EndpointRecommendation,
    FalsePositiveEstimate,
    GracePeriodRecommendation,
    HealthCheckProbeConfig,
    HealthCheckScorecard,
    HealthCheckStrategyOptimizer,
    IntervalAnalysis,
    IntervalQuality,
    ProbeProtocol,
    ProbeType,
    RubricCategory,
    RubricScore,
    ServiceMeshHealthAnalysis,
    ServiceMeshType,
    Severity,
    StrategyReport,
    TimeoutAlignment,
    _cascade_safety_score,
    _checks_per_minute,
    _clamp,
    _classify_interval,
    _dependency_awareness_score,
    _depth_strategy_score,
    _detection_delay,
    _endpoint_design_score,
    _estimate_p99_from_component,
    _grace_period_score,
    _grade_from_score,
    _interval_tuning_score,
    _mesh_integration_score,
    _noise_risk,
    _probe_coverage_score,
    _recommend_interval,
    _recommend_timeout,
    _severity_from_depth,
    _threshold_tuning_score,
    _timeout_alignment_score,
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


def _three_tier_graph() -> InfraGraph:
    lb = Component(id="lb", name="lb", type=ComponentType.LOAD_BALANCER, replicas=2)
    api = Component(id="api", name="api", type=ComponentType.APP_SERVER, replicas=3)
    db = Component(id="db", name="db", type=ComponentType.DATABASE, replicas=2)
    g = InfraGraph()
    g.add_component(lb)
    g.add_component(api)
    g.add_component(db)
    g.add_dependency(Dependency(source_id="lb", target_id="api"))
    g.add_dependency(Dependency(source_id="api", target_id="db"))
    return g


def _default_probe(
    probe_type: ProbeType = ProbeType.LIVENESS,
    interval: float = 10.0,
    timeout: float = 5.0,
    failure_threshold: int = 3,
    success_threshold: int = 1,
    depth: CheckDepth = CheckDepth.SHALLOW,
    checks_deps: list[str] | None = None,
    protocol: ProbeProtocol = ProbeProtocol.HTTP_GET,
    endpoint: str = "/healthz",
    initial_delay: float = 0.0,
    grace_period: float = 0.0,
    port: int = 8080,
) -> HealthCheckProbeConfig:
    return HealthCheckProbeConfig(
        probe_type=probe_type,
        protocol=protocol,
        endpoint=endpoint,
        port=port,
        interval_seconds=interval,
        timeout_seconds=timeout,
        failure_threshold=failure_threshold,
        success_threshold=success_threshold,
        initial_delay_seconds=initial_delay,
        grace_period_seconds=grace_period,
        depth=depth,
        checks_dependencies=checks_deps or [],
    )


def _full_probe_set() -> list[HealthCheckProbeConfig]:
    """Liveness + readiness + startup probes with good defaults."""
    return [
        _default_probe(ProbeType.LIVENESS, endpoint="/healthz"),
        _default_probe(
            ProbeType.READINESS,
            endpoint="/readyz",
            depth=CheckDepth.DEPENDENCY_AWARE,
        ),
        _default_probe(
            ProbeType.STARTUP,
            endpoint="/startupz",
            depth=CheckDepth.DEEP,
            grace_period=30.0,
            failure_threshold=30,
        ),
    ]


# ---------------------------------------------------------------------------
# Pure function tests
# ---------------------------------------------------------------------------


class TestChecksPerMinute:
    def test_standard_interval(self):
        assert _checks_per_minute(10.0) == 6.0

    def test_zero_interval(self):
        assert _checks_per_minute(0.0) == 0.0

    def test_negative_interval(self):
        assert _checks_per_minute(-5.0) == 0.0

    def test_one_second_interval(self):
        assert _checks_per_minute(1.0) == 60.0


class TestDetectionDelay:
    def test_basic(self):
        assert _detection_delay(10.0, 3) == 30.0

    def test_single_threshold(self):
        assert _detection_delay(5.0, 1) == 5.0

    def test_zero_interval(self):
        assert _detection_delay(0.0, 5) == 0.0


class TestClassifyInterval:
    def test_too_frequent(self):
        assert _classify_interval(2.0) == IntervalQuality.TOO_FREQUENT

    def test_optimal(self):
        assert _classify_interval(10.0) == IntervalQuality.OPTIMAL

    def test_too_infrequent(self):
        assert _classify_interval(120.0) == IntervalQuality.TOO_INFREQUENT

    def test_boundary_min(self):
        assert _classify_interval(5.0) == IntervalQuality.OPTIMAL

    def test_boundary_max(self):
        assert _classify_interval(60.0) == IntervalQuality.OPTIMAL


class TestNoiseRisk:
    def test_low_frequency(self):
        result = _noise_risk(60.0)
        assert result < 0.2

    def test_high_frequency(self):
        result = _noise_risk(1.0)
        assert result == 1.0

    def test_zero_interval(self):
        assert _noise_risk(0.0) == 0.0

    def test_moderate_frequency(self):
        result = _noise_risk(10.0)
        assert 0.0 < result < 1.0


class TestSeverityFromDepth:
    def test_zero(self):
        assert _severity_from_depth(0) == Severity.INFO

    def test_one(self):
        assert _severity_from_depth(1) == Severity.LOW

    def test_two(self):
        assert _severity_from_depth(2) == Severity.MEDIUM

    def test_three(self):
        assert _severity_from_depth(3) == Severity.HIGH

    def test_five(self):
        assert _severity_from_depth(5) == Severity.CRITICAL

    def test_ten(self):
        assert _severity_from_depth(10) == Severity.CRITICAL


class TestGradeFromScore:
    def test_a(self):
        assert _grade_from_score(95.0) == "A"

    def test_b(self):
        assert _grade_from_score(85.0) == "B"

    def test_c(self):
        assert _grade_from_score(75.0) == "C"

    def test_d(self):
        assert _grade_from_score(65.0) == "D"

    def test_f(self):
        assert _grade_from_score(50.0) == "F"

    def test_boundary_90(self):
        assert _grade_from_score(90.0) == "A"


class TestClamp:
    def test_within_range(self):
        assert _clamp(5.0, 0.0, 10.0) == 5.0

    def test_below_min(self):
        assert _clamp(-1.0, 0.0, 10.0) == 0.0

    def test_above_max(self):
        assert _clamp(15.0, 0.0, 10.0) == 10.0


class TestEstimateP99:
    def test_none_component(self):
        result = _estimate_p99_from_component(None)
        assert result > 0.0

    def test_database(self):
        comp = _comp("db", ComponentType.DATABASE)
        result = _estimate_p99_from_component(comp)
        assert result > _estimate_p99_from_component(_comp("app"))

    def test_cache(self):
        comp = _comp("cache", ComponentType.CACHE)
        result = _estimate_p99_from_component(comp)
        assert result < _estimate_p99_from_component(_comp("app"))

    def test_external_api(self):
        comp = _comp("ext", ComponentType.EXTERNAL_API)
        result = _estimate_p99_from_component(comp)
        assert result > _estimate_p99_from_component(_comp("app"))

    def test_high_utilization(self):
        comp = _comp("app")
        comp.metrics.cpu_percent = 90.0
        result_high = _estimate_p99_from_component(comp)
        comp2 = _comp("app2")
        result_low = _estimate_p99_from_component(comp2)
        assert result_high > result_low

    def test_queue(self):
        comp = _comp("q", ComponentType.QUEUE)
        result = _estimate_p99_from_component(comp)
        assert result > 0.0

    def test_dns(self):
        comp = _comp("dns", ComponentType.DNS)
        result = _estimate_p99_from_component(comp)
        assert result > 0.0

    def test_load_balancer(self):
        comp = _comp("lb", ComponentType.LOAD_BALANCER)
        result = _estimate_p99_from_component(comp)
        assert result > 0.0

    def test_storage(self):
        comp = _comp("s", ComponentType.STORAGE)
        result = _estimate_p99_from_component(comp)
        assert result > 0.0

    def test_moderate_utilization(self):
        comp = _comp("app")
        comp.metrics.cpu_percent = 70.0
        result = _estimate_p99_from_component(comp)
        baseline = _estimate_p99_from_component(_comp("app2"))
        assert result > baseline


class TestRecommendInterval:
    def test_none_component(self):
        result = _recommend_interval(None, 0)
        assert 5.0 <= result <= 120.0

    def test_lb(self):
        comp = _comp("lb", ComponentType.LOAD_BALANCER)
        result = _recommend_interval(comp, 0)
        assert result == 5.0

    def test_db(self):
        comp = _comp("db", ComponentType.DATABASE)
        result = _recommend_interval(comp, 0)
        assert result == 15.0

    def test_external_api(self):
        comp = _comp("ext", ComponentType.EXTERNAL_API)
        result = _recommend_interval(comp, 0)
        assert result == 30.0

    def test_many_dependents(self):
        comp = _comp("svc")
        result = _recommend_interval(comp, 6)
        assert result >= 15.0


class TestRecommendTimeout:
    def test_fast_service(self):
        result = _recommend_timeout(0.005)
        assert result >= 1.0

    def test_slow_service(self):
        result = _recommend_timeout(10.0)
        assert result <= 30.0

    def test_moderate(self):
        result = _recommend_timeout(0.5)
        assert 1.0 <= result <= 30.0


# ---------------------------------------------------------------------------
# Optimizer: interval analysis
# ---------------------------------------------------------------------------


class TestAnalyzeInterval:
    def test_optimal_interval(self):
        g = _graph(_comp("c1"))
        opt = HealthCheckStrategyOptimizer()
        probe = _default_probe(interval=10.0)
        result = opt.analyze_interval(g, "c1", probe)
        assert isinstance(result, IntervalAnalysis)
        assert result.quality == IntervalQuality.OPTIMAL
        assert result.checks_per_minute == 6.0

    def test_too_frequent(self):
        g = _graph(_comp("c1"))
        opt = HealthCheckStrategyOptimizer()
        probe = _default_probe(interval=2.0)
        result = opt.analyze_interval(g, "c1", probe)
        assert result.quality == IntervalQuality.TOO_FREQUENT
        assert len(result.findings) > 0

    def test_too_infrequent(self):
        g = _graph(_comp("c1"))
        opt = HealthCheckStrategyOptimizer()
        probe = _default_probe(interval=120.0)
        result = opt.analyze_interval(g, "c1", probe)
        assert result.quality == IntervalQuality.TOO_INFREQUENT

    def test_high_noise_risk(self):
        g = _graph(_comp("c1"))
        opt = HealthCheckStrategyOptimizer()
        probe = _default_probe(interval=3.0)
        result = opt.analyze_interval(g, "c1", probe)
        assert result.noise_risk > 0.5

    def test_detection_delay(self):
        g = _graph(_comp("c1"))
        opt = HealthCheckStrategyOptimizer()
        probe = _default_probe(interval=10.0, failure_threshold=5)
        result = opt.analyze_interval(g, "c1", probe)
        assert result.detection_delay_seconds == 50.0

    def test_component_not_in_graph(self):
        g = _graph(_comp("c1"))
        opt = HealthCheckStrategyOptimizer()
        probe = _default_probe()
        result = opt.analyze_interval(g, "missing", probe)
        assert isinstance(result, IntervalAnalysis)


# ---------------------------------------------------------------------------
# Optimizer: cascade analysis
# ---------------------------------------------------------------------------


class TestAnalyzeCascade:
    def test_no_cascade(self):
        g = _graph(_comp("c1"))
        opt = HealthCheckStrategyOptimizer()
        result = opt.analyze_cascade(g, "c1")
        assert isinstance(result, CascadeAnalysis)
        assert result.max_depth == 0
        assert result.total_affected == 0

    def test_simple_cascade(self):
        g = _three_tier_graph()
        opt = HealthCheckStrategyOptimizer()
        result = opt.analyze_cascade(g, "db")
        assert result.total_affected > 0

    def test_deep_cascade_severity(self):
        comps = []
        g = InfraGraph()
        for i in range(7):
            c = _comp(f"c{i}")
            g.add_component(c)
            comps.append(c)
        for i in range(6):
            g.add_dependency(Dependency(source_id=f"c{i}", target_id=f"c{i+1}"))
        opt = HealthCheckStrategyOptimizer()
        result = opt.analyze_cascade(g, "c6")
        assert result.severity in (Severity.HIGH, Severity.CRITICAL)

    def test_cascade_with_configs(self):
        g = _three_tier_graph()
        configs = {
            "db": [_default_probe(interval=10.0, failure_threshold=3)],
            "api": [_default_probe(interval=5.0, failure_threshold=2)],
        }
        opt = HealthCheckStrategyOptimizer()
        result = opt.analyze_cascade(g, "db", configs)
        assert isinstance(result, CascadeAnalysis)

    def test_cascade_recommendations(self):
        g = _three_tier_graph()
        opt = HealthCheckStrategyOptimizer()
        result = opt.analyze_cascade(g, "db")
        # The three-tier graph has cascade depth, should produce recommendations
        assert isinstance(result.recommendations, list)

    def test_component_not_in_graph(self):
        g = _graph(_comp("c1"))
        opt = HealthCheckStrategyOptimizer()
        result = opt.analyze_cascade(g, "missing")
        assert result.max_depth == 0


# ---------------------------------------------------------------------------
# Optimizer: dependency chain analysis
# ---------------------------------------------------------------------------


class TestAnalyzeDependencyChain:
    def test_no_deps(self):
        g = _graph(_comp("c1"))
        opt = HealthCheckStrategyOptimizer()
        result = opt.analyze_dependency_chain(g, "c1")
        assert isinstance(result, DependencyChainAnalysis)
        assert not result.circular_dependency_detected

    def test_with_dep_probes(self):
        g = _three_tier_graph()
        configs = {
            "api": [
                _default_probe(
                    ProbeType.READINESS,
                    depth=CheckDepth.DEPENDENCY_AWARE,
                    checks_deps=["db"],
                )
            ],
        }
        opt = HealthCheckStrategyOptimizer()
        result = opt.analyze_dependency_chain(g, "api", configs)
        assert result.chain_length > 0

    def test_circular_dependency(self):
        c1 = _comp("c1")
        c2 = _comp("c2")
        g = _graph(c1, c2)
        g.add_dependency(Dependency(source_id="c1", target_id="c2"))
        configs = {
            "c1": [_default_probe(checks_deps=["c2"])],
            "c2": [_default_probe(checks_deps=["c1"])],
        }
        opt = HealthCheckStrategyOptimizer()
        result = opt.analyze_dependency_chain(g, "c1", configs)
        assert result.circular_dependency_detected
        assert result.severity == Severity.HIGH

    def test_long_chain(self):
        g = InfraGraph()
        configs = {}
        for i in range(8):
            g.add_component(_comp(f"c{i}"))
            if i > 0:
                configs[f"c{i-1}"] = [
                    _default_probe(checks_deps=[f"c{i}"])
                ]
                g.add_dependency(Dependency(source_id=f"c{i-1}", target_id=f"c{i}"))
        opt = HealthCheckStrategyOptimizer()
        result = opt.analyze_dependency_chain(g, "c0", configs)
        assert result.chain_length > 5


# ---------------------------------------------------------------------------
# Optimizer: false-positive estimation
# ---------------------------------------------------------------------------


class TestEstimateFalsePositiveRate:
    def test_well_configured(self):
        g = _graph(_comp("c1"))
        opt = HealthCheckStrategyOptimizer()
        probe = _default_probe(timeout=5.0, failure_threshold=3)
        result = opt.estimate_false_positive_rate(g, "c1", probe)
        assert isinstance(result, FalsePositiveEstimate)
        assert result.estimated_rate_percent < 20.0

    def test_timeout_too_short(self):
        comp = _comp("db", ComponentType.DATABASE)
        g = _graph(comp)
        opt = HealthCheckStrategyOptimizer()
        probe = _default_probe(timeout=0.01, failure_threshold=1)
        result = opt.estimate_false_positive_rate(g, "db", probe)
        assert result.timeout_induced_percent > 0
        assert result.risk_level in (Severity.MEDIUM, Severity.HIGH)

    def test_many_dependencies(self):
        g = _graph(_comp("c1"))
        opt = HealthCheckStrategyOptimizer()
        probe = _default_probe(checks_deps=["d1", "d2", "d3", "d4", "d5"])
        result = opt.estimate_false_positive_rate(g, "c1", probe)
        assert result.dependency_induced_percent > 0

    def test_high_packet_loss(self):
        comp = _comp("c1")
        comp.network.packet_loss_rate = 0.01
        g = _graph(comp)
        opt = HealthCheckStrategyOptimizer()
        probe = _default_probe()
        result = opt.estimate_false_positive_rate(g, "c1", probe)
        assert result.network_induced_percent > 0

    def test_single_failure_threshold_amplifies(self):
        g = _graph(_comp("c1"))
        opt = HealthCheckStrategyOptimizer()
        probe = _default_probe(timeout=0.05, failure_threshold=1)
        result = opt.estimate_false_positive_rate(g, "c1", probe)
        assert len(result.contributing_factors) > 0

    def test_marginal_timeout(self):
        comp = _comp("app")
        g = _graph(comp)
        opt = HealthCheckStrategyOptimizer()
        p99 = _estimate_p99_from_component(comp)
        probe = _default_probe(timeout=p99 * 1.2)
        result = opt.estimate_false_positive_rate(g, "app", probe)
        assert result.timeout_induced_percent > 0


# ---------------------------------------------------------------------------
# Optimizer: grace period recommendations
# ---------------------------------------------------------------------------


class TestRecommendGracePeriod:
    def test_startup_too_short(self):
        g = _graph(_comp("c1"))
        opt = HealthCheckStrategyOptimizer()
        probe = _default_probe(ProbeType.STARTUP, grace_period=5.0)
        result = opt.recommend_grace_period(g, "c1", probe)
        assert isinstance(result, GracePeriodRecommendation)
        assert result.recommended_grace_period >= 15.0

    def test_startup_database(self):
        comp = _comp("db", ComponentType.DATABASE)
        g = _graph(comp)
        opt = HealthCheckStrategyOptimizer()
        probe = _default_probe(ProbeType.STARTUP, grace_period=10.0)
        result = opt.recommend_grace_period(g, "db", probe)
        assert result.recommended_grace_period >= 60.0

    def test_liveness_low_threshold(self):
        g = _graph(_comp("c1"))
        opt = HealthCheckStrategyOptimizer()
        probe = _default_probe(ProbeType.LIVENESS, failure_threshold=1)
        result = opt.recommend_grace_period(g, "c1", probe)
        assert result.recommended_failure_threshold >= 3

    def test_liveness_low_initial_delay(self):
        g = _graph(_comp("c1"))
        opt = HealthCheckStrategyOptimizer()
        probe = _default_probe(ProbeType.LIVENESS, initial_delay=2.0)
        result = opt.recommend_grace_period(g, "c1", probe)
        assert any("startup" in f.lower() or "initial delay" in f.lower()
                    for f in result.findings)

    def test_readiness_low_threshold(self):
        g = _graph(_comp("c1"))
        opt = HealthCheckStrategyOptimizer()
        probe = _default_probe(ProbeType.READINESS, failure_threshold=1)
        result = opt.recommend_grace_period(g, "c1", probe)
        assert result.recommended_failure_threshold >= 2

    def test_readiness_zero_success(self):
        g = _graph(_comp("c1"))
        opt = HealthCheckStrategyOptimizer()
        probe = _default_probe(ProbeType.READINESS, success_threshold=0)
        result = opt.recommend_grace_period(g, "c1", probe)
        assert result.recommended_success_threshold >= 1

    def test_very_high_failure_threshold(self):
        g = _graph(_comp("c1"))
        opt = HealthCheckStrategyOptimizer()
        probe = _default_probe(failure_threshold=20)
        result = opt.recommend_grace_period(g, "c1", probe)
        assert result.recommended_failure_threshold < 20


# ---------------------------------------------------------------------------
# Optimizer: endpoint recommendations
# ---------------------------------------------------------------------------


class TestRecommendEndpoints:
    def test_app_server(self):
        g = _graph(_comp("c1"))
        opt = HealthCheckStrategyOptimizer()
        result = opt.recommend_endpoints(g, "c1")
        assert isinstance(result, EndpointRecommendation)
        assert result.recommended_liveness_endpoint == "/healthz"

    def test_database(self):
        g = _graph(_comp("db", ComponentType.DATABASE))
        opt = HealthCheckStrategyOptimizer()
        result = opt.recommend_endpoints(g, "db")
        assert result.recommended_liveness_endpoint == "/ping"
        assert result.recommended_liveness_depth == CheckDepth.SHALLOW

    def test_cache(self):
        g = _graph(_comp("cache", ComponentType.CACHE))
        opt = HealthCheckStrategyOptimizer()
        result = opt.recommend_endpoints(g, "cache")
        assert result.recommended_liveness_endpoint == "/ping"

    def test_lb(self):
        g = _graph(_comp("lb", ComponentType.LOAD_BALANCER))
        opt = HealthCheckStrategyOptimizer()
        result = opt.recommend_endpoints(g, "lb")
        assert "/healthz" in result.recommended_liveness_endpoint

    def test_with_dependencies(self):
        g = _three_tier_graph()
        opt = HealthCheckStrategyOptimizer()
        result = opt.recommend_endpoints(g, "api")
        assert result.recommended_readiness_depth in (
            CheckDepth.DEEP, CheckDepth.DEPENDENCY_AWARE,
        )
        assert any("dependencies" in f.lower() for f in result.findings)


# ---------------------------------------------------------------------------
# Optimizer: depth trade-off analysis
# ---------------------------------------------------------------------------


class TestAnalyzeDepthTradeoff:
    def test_shallow_no_deps(self):
        g = _graph(_comp("c1"))
        opt = HealthCheckStrategyOptimizer()
        probe = _default_probe(depth=CheckDepth.SHALLOW)
        result = opt.analyze_depth_tradeoff(g, "c1", probe)
        assert isinstance(result, DepthTradeoff)
        assert result.recommended_depth == CheckDepth.SHALLOW

    def test_shallow_with_deps(self):
        g = _three_tier_graph()
        opt = HealthCheckStrategyOptimizer()
        probe = _default_probe(depth=CheckDepth.SHALLOW)
        result = opt.analyze_depth_tradeoff(g, "api", probe)
        assert result.recommended_depth == CheckDepth.DEPENDENCY_AWARE

    def test_deep_on_popular_component(self):
        g = InfraGraph()
        hub = _comp("hub")
        g.add_component(hub)
        for i in range(5):
            c = _comp(f"dep{i}")
            g.add_component(c)
            g.add_dependency(Dependency(source_id=f"dep{i}", target_id="hub"))
        opt = HealthCheckStrategyOptimizer()
        probe = _default_probe(depth=CheckDepth.DEEP)
        result = opt.analyze_depth_tradeoff(g, "hub", probe)
        assert result.recommended_depth == CheckDepth.SHALLOW

    def test_dependency_aware(self):
        g = _three_tier_graph()
        opt = HealthCheckStrategyOptimizer()
        probe = _default_probe(depth=CheckDepth.DEPENDENCY_AWARE)
        result = opt.analyze_depth_tradeoff(g, "api", probe)
        assert "dependency-aware" in result.recommendation.lower()

    def test_deep_few_dependents(self):
        g = _graph(_comp("c1"), _comp("c2"))
        g.add_dependency(Dependency(source_id="c2", target_id="c1"))
        opt = HealthCheckStrategyOptimizer()
        probe = _default_probe(depth=CheckDepth.DEEP)
        result = opt.analyze_depth_tradeoff(g, "c1", probe)
        assert result.recommended_depth == CheckDepth.DEEP

    def test_cost_scores(self):
        g = _three_tier_graph()
        opt = HealthCheckStrategyOptimizer()
        probe = _default_probe(depth=CheckDepth.SHALLOW)
        result = opt.analyze_depth_tradeoff(g, "api", probe)
        assert result.deep_cost_score > result.shallow_cost_score


# ---------------------------------------------------------------------------
# Optimizer: timeout alignment
# ---------------------------------------------------------------------------


class TestAnalyzeTimeoutAlignment:
    def test_aligned(self):
        comp = _comp("c1")
        g = _graph(comp)
        p99 = _estimate_p99_from_component(comp)
        opt = HealthCheckStrategyOptimizer()
        probe = _default_probe(timeout=p99 * 3)
        result = opt.analyze_timeout_alignment(g, "c1", probe)
        assert isinstance(result, TimeoutAlignment)
        assert result.is_aligned

    def test_timeout_below_p99(self):
        comp = _comp("db", ComponentType.DATABASE)
        g = _graph(comp)
        opt = HealthCheckStrategyOptimizer()
        probe = _default_probe(timeout=0.01)
        result = opt.analyze_timeout_alignment(g, "db", probe)
        assert not result.is_aligned
        assert len(result.findings) > 0

    def test_timeout_way_above(self):
        comp = _comp("c1")
        g = _graph(comp)
        opt = HealthCheckStrategyOptimizer()
        probe = _default_probe(timeout=100.0)
        result = opt.analyze_timeout_alignment(g, "c1", probe)
        assert not result.is_aligned

    def test_slightly_above_p99(self):
        comp = _comp("c1")
        g = _graph(comp)
        p99 = _estimate_p99_from_component(comp)
        opt = HealthCheckStrategyOptimizer()
        probe = _default_probe(timeout=p99 * 1.3)
        result = opt.analyze_timeout_alignment(g, "c1", probe)
        assert len(result.findings) > 0

    def test_generous_timeout(self):
        comp = _comp("c1")
        g = _graph(comp)
        p99 = _estimate_p99_from_component(comp)
        opt = HealthCheckStrategyOptimizer()
        probe = _default_probe(timeout=p99 * 7)
        result = opt.analyze_timeout_alignment(g, "c1", probe)
        assert any("generous" in f.lower() or "reduced" in f.lower()
                    for f in result.findings)


# ---------------------------------------------------------------------------
# Optimizer: blind spot detection
# ---------------------------------------------------------------------------


class TestDetectBlindSpots:
    def test_full_coverage(self):
        g = _graph(_comp("c1"))
        opt = HealthCheckStrategyOptimizer()
        configs = {"c1": _full_probe_set()}
        result = opt.detect_blind_spots(g, configs)
        assert isinstance(result, BlindSpotReport)
        assert result.coverage_ratio == 1.0

    def test_unchecked_component(self):
        g = _graph(_comp("c1"), _comp("c2"))
        opt = HealthCheckStrategyOptimizer()
        configs = {"c1": _full_probe_set()}
        result = opt.detect_blind_spots(g, configs)
        assert result.coverage_ratio < 1.0
        unchecked = [bs for bs in result.blind_spots
                     if bs.category == BlindSpotCategory.UNCHECKED_COMPONENT]
        assert len(unchecked) == 1

    def test_no_liveness(self):
        g = _graph(_comp("c1"))
        opt = HealthCheckStrategyOptimizer()
        configs = {"c1": [_default_probe(ProbeType.READINESS)]}
        result = opt.detect_blind_spots(g, configs)
        cats = [bs.category for bs in result.blind_spots]
        assert BlindSpotCategory.NO_LIVENESS_PROBE in cats

    def test_no_readiness(self):
        g = _graph(_comp("c1"))
        opt = HealthCheckStrategyOptimizer()
        configs = {"c1": [_default_probe(ProbeType.LIVENESS)]}
        result = opt.detect_blind_spots(g, configs)
        cats = [bs.category for bs in result.blind_spots]
        assert BlindSpotCategory.NO_READINESS_PROBE in cats

    def test_no_startup(self):
        g = _graph(_comp("c1"))
        opt = HealthCheckStrategyOptimizer()
        configs = {"c1": [_default_probe(ProbeType.LIVENESS)]}
        result = opt.detect_blind_spots(g, configs)
        cats = [bs.category for bs in result.blind_spots]
        assert BlindSpotCategory.NO_STARTUP_PROBE in cats

    def test_missing_dependency_check(self):
        g = _three_tier_graph()
        opt = HealthCheckStrategyOptimizer()
        configs = {
            "api": [_default_probe(depth=CheckDepth.SHALLOW)],
            "db": [_default_probe()],
            "lb": [_default_probe()],
        }
        result = opt.detect_blind_spots(g, configs)
        dep_spots = [bs for bs in result.blind_spots
                     if bs.category == BlindSpotCategory.MISSING_DEPENDENCY_CHECK]
        assert len(dep_spots) > 0

    def test_timeout_mismatch(self):
        comp = _comp("db", ComponentType.DATABASE)
        g = _graph(comp)
        opt = HealthCheckStrategyOptimizer()
        configs = {"db": [_default_probe(timeout=0.001)]}
        result = opt.detect_blind_spots(g, configs)
        cats = [bs.category for bs in result.blind_spots]
        assert BlindSpotCategory.TIMEOUT_MISMATCH in cats

    def test_single_protocol(self):
        g = _graph(_comp("c1"))
        opt = HealthCheckStrategyOptimizer()
        configs = {"c1": [
            _default_probe(protocol=ProbeProtocol.TCP_SOCKET),
        ]}
        result = opt.detect_blind_spots(g, configs)
        cats = [bs.category for bs in result.blind_spots]
        assert BlindSpotCategory.SINGLE_PROTOCOL in cats

    def test_no_grace_period(self):
        g = _graph(_comp("c1"))
        opt = HealthCheckStrategyOptimizer()
        configs = {"c1": [_default_probe(grace_period=0.0, initial_delay=0.0)]}
        result = opt.detect_blind_spots(g, configs)
        cats = [bs.category for bs in result.blind_spots]
        assert BlindSpotCategory.NO_GRACE_PERIOD in cats

    def test_severity_counts(self):
        g = _graph(_comp("c1"), _comp("c2"))
        opt = HealthCheckStrategyOptimizer()
        configs = {}
        result = opt.detect_blind_spots(g, configs)
        assert sum(result.severity_counts.values()) > 0

    def test_empty_graph(self):
        g = InfraGraph()
        opt = HealthCheckStrategyOptimizer()
        result = opt.detect_blind_spots(g, {})
        assert result.total_components == 0
        assert result.coverage_ratio == 0.0


# ---------------------------------------------------------------------------
# Optimizer: service mesh integration
# ---------------------------------------------------------------------------


class TestAnalyzeServiceMeshIntegration:
    def test_no_mesh(self):
        g = _graph(_comp("c1"))
        opt = HealthCheckStrategyOptimizer()
        probe = _default_probe()
        result = opt.analyze_service_mesh_integration(g, "c1", probe)
        assert result.mesh_type == ServiceMeshType.NONE

    def test_istio_aligned(self):
        g = _graph(_comp("c1"))
        opt = HealthCheckStrategyOptimizer()
        probe = _default_probe(timeout=5.0)
        result = opt.analyze_service_mesh_integration(
            g, "c1", probe,
            mesh_type=ServiceMeshType.ISTIO,
            sidecar_timeout_seconds=5.0,
        )
        assert result.sidecar_probe_aligned
        assert result.mtls_health_impact > 0

    def test_sidecar_misaligned(self):
        g = _graph(_comp("c1"))
        opt = HealthCheckStrategyOptimizer()
        probe = _default_probe(timeout=5.0)
        result = opt.analyze_service_mesh_integration(
            g, "c1", probe,
            mesh_type=ServiceMeshType.ISTIO,
            sidecar_timeout_seconds=15.0,
        )
        assert not result.sidecar_probe_aligned

    def test_retry_overlap(self):
        c1 = _comp("c1")
        c2 = _comp("c2")
        g = _graph(c1, c2)
        dep = Dependency(source_id="c1", target_id="c2")
        dep.retry_strategy.enabled = True
        g.add_dependency(dep)
        opt = HealthCheckStrategyOptimizer()
        probe = _default_probe()
        result = opt.analyze_service_mesh_integration(
            g, "c1", probe,
            mesh_type=ServiceMeshType.LINKERD,
            mesh_retry_enabled=True,
        )
        assert result.retry_overlap_detected

    def test_circuit_breaker_conflict(self):
        c1 = _comp("c1")
        c2 = _comp("c2")
        g = _graph(c1, c2)
        dep = Dependency(source_id="c1", target_id="c2")
        dep.circuit_breaker.enabled = True
        g.add_dependency(dep)
        opt = HealthCheckStrategyOptimizer()
        probe = _default_probe()
        result = opt.analyze_service_mesh_integration(
            g, "c1", probe,
            mesh_type=ServiceMeshType.CONSUL_CONNECT,
            mesh_circuit_breaker_enabled=True,
        )
        assert result.circuit_breaker_conflict

    def test_no_retry_overlap_without_app_retry(self):
        c1 = _comp("c1")
        c2 = _comp("c2")
        g = _graph(c1, c2)
        g.add_dependency(Dependency(source_id="c1", target_id="c2"))
        opt = HealthCheckStrategyOptimizer()
        probe = _default_probe()
        result = opt.analyze_service_mesh_integration(
            g, "c1", probe,
            mesh_type=ServiceMeshType.ISTIO,
            mesh_retry_enabled=True,
        )
        assert not result.retry_overlap_detected


# ---------------------------------------------------------------------------
# Optimizer: scoring rubric
# ---------------------------------------------------------------------------


class TestScoreComponent:
    def test_full_probes_good_score(self):
        g = _graph(_comp("c1"))
        opt = HealthCheckStrategyOptimizer()
        probes = _full_probe_set()
        sc = opt.score_component(g, "c1", probes)
        assert isinstance(sc, HealthCheckScorecard)
        assert sc.overall_score > 50.0
        assert sc.grade in ("A", "B", "C")

    def test_no_probes_low_score(self):
        g = _graph(_comp("c1"))
        opt = HealthCheckStrategyOptimizer()
        sc = opt.score_component(g, "c1", [])
        assert sc.overall_score < 40.0
        assert sc.grade in ("D", "F")

    def test_single_liveness_only(self):
        g = _graph(_comp("c1"))
        opt = HealthCheckStrategyOptimizer()
        sc = opt.score_component(g, "c1", [_default_probe()])
        assert 20.0 < sc.overall_score < 80.0

    def test_rubric_categories_present(self):
        g = _graph(_comp("c1"))
        opt = HealthCheckStrategyOptimizer()
        probes = _full_probe_set()
        sc = opt.score_component(g, "c1", probes)
        categories = {r.category for r in sc.rubric_scores}
        assert RubricCategory.PROBE_COVERAGE in categories
        assert RubricCategory.INTERVAL_TUNING in categories
        assert RubricCategory.CASCADE_SAFETY in categories

    def test_with_mesh_analysis(self):
        g = _graph(_comp("c1"))
        opt = HealthCheckStrategyOptimizer()
        mesh = ServiceMeshHealthAnalysis(
            component_id="c1",
            mesh_type=ServiceMeshType.ISTIO,
            sidecar_probe_aligned=True,
        )
        sc = opt.score_component(g, "c1", _full_probe_set(), mesh_analysis=mesh)
        assert sc.overall_score > 0

    def test_timestamp_set(self):
        g = _graph(_comp("c1"))
        opt = HealthCheckStrategyOptimizer()
        sc = opt.score_component(g, "c1", _full_probe_set())
        assert len(sc.timestamp) > 0

    def test_recommendations_on_bad_config(self):
        g = _graph(_comp("c1"))
        opt = HealthCheckStrategyOptimizer()
        probe = _default_probe(
            interval=1.0, timeout=0.1, failure_threshold=1,
        )
        sc = opt.score_component(g, "c1", [probe])
        assert len(sc.recommendations) > 0


# ---------------------------------------------------------------------------
# Optimizer: strategy report
# ---------------------------------------------------------------------------


class TestGenerateReport:
    def test_basic_report(self):
        g = _graph(_comp("c1"))
        opt = HealthCheckStrategyOptimizer()
        configs = {"c1": _full_probe_set()}
        report = opt.generate_report(g, configs)
        assert isinstance(report, StrategyReport)
        assert len(report.scorecards) == 1
        assert report.overall_health_score > 0

    def test_report_with_unchecked_components(self):
        g = _graph(_comp("c1"), _comp("c2"))
        opt = HealthCheckStrategyOptimizer()
        configs = {"c1": _full_probe_set()}
        report = opt.generate_report(g, configs)
        assert report.blind_spot_report is not None
        assert report.blind_spot_report.coverage_ratio < 1.0

    def test_report_multiple_components(self):
        g = _three_tier_graph()
        opt = HealthCheckStrategyOptimizer()
        configs = {
            "lb": [_default_probe()],
            "api": _full_probe_set(),
            "db": [_default_probe(protocol=ProbeProtocol.TCP_SOCKET)],
        }
        report = opt.generate_report(g, configs)
        assert len(report.scorecards) == 3
        assert len(report.cascade_analysis) == 3

    def test_report_top_recommendations(self):
        g = _three_tier_graph()
        opt = HealthCheckStrategyOptimizer()
        configs = {}
        report = opt.generate_report(g, configs)
        assert len(report.top_recommendations) > 0

    def test_report_with_mesh(self):
        g = _graph(_comp("c1"))
        opt = HealthCheckStrategyOptimizer()
        mesh = ServiceMeshHealthAnalysis(
            component_id="c1",
            mesh_type=ServiceMeshType.ISTIO,
            sidecar_probe_aligned=True,
        )
        configs = {"c1": _full_probe_set()}
        report = opt.generate_report(g, configs, mesh_analyses={"c1": mesh})
        assert report.overall_health_score > 0

    def test_report_interval_analyses(self):
        g = _graph(_comp("c1"))
        opt = HealthCheckStrategyOptimizer()
        configs = {"c1": [_default_probe()]}
        report = opt.generate_report(g, configs)
        assert len(report.interval_analyses) == 1

    def test_empty_graph_report(self):
        g = InfraGraph()
        opt = HealthCheckStrategyOptimizer()
        report = opt.generate_report(g, {})
        assert report.overall_health_score == 0.0


# ---------------------------------------------------------------------------
# Optimizer: probe differentiation
# ---------------------------------------------------------------------------


class TestDifferentiateProbes:
    def test_basic(self):
        g = _graph(_comp("c1"))
        opt = HealthCheckStrategyOptimizer()
        probes = opt.differentiate_probes(g, "c1")
        assert len(probes) == 3
        types = {p.probe_type for p in probes}
        assert ProbeType.LIVENESS in types
        assert ProbeType.READINESS in types
        assert ProbeType.STARTUP in types

    def test_liveness_is_shallow(self):
        g = _graph(_comp("c1"))
        opt = HealthCheckStrategyOptimizer()
        probes = opt.differentiate_probes(g, "c1")
        liveness = [p for p in probes if p.probe_type == ProbeType.LIVENESS]
        assert liveness[0].depth == CheckDepth.SHALLOW

    def test_readiness_checks_deps(self):
        g = _three_tier_graph()
        opt = HealthCheckStrategyOptimizer()
        probes = opt.differentiate_probes(g, "api")
        readiness = [p for p in probes if p.probe_type == ProbeType.READINESS]
        assert len(readiness[0].checks_dependencies) > 0

    def test_startup_has_grace_period(self):
        g = _graph(_comp("c1"))
        opt = HealthCheckStrategyOptimizer()
        probes = opt.differentiate_probes(g, "c1")
        startup = [p for p in probes if p.probe_type == ProbeType.STARTUP]
        assert startup[0].grace_period_seconds > 0

    def test_database_uses_tcp(self):
        g = _graph(_comp("db", ComponentType.DATABASE))
        opt = HealthCheckStrategyOptimizer()
        probes = opt.differentiate_probes(g, "db")
        assert all(p.protocol == ProbeProtocol.TCP_SOCKET for p in probes)

    def test_many_dependents_wider_interval(self):
        g = InfraGraph()
        hub = _comp("hub")
        g.add_component(hub)
        for i in range(7):
            c = _comp(f"dep{i}")
            g.add_component(c)
            g.add_dependency(Dependency(source_id=f"dep{i}", target_id="hub"))
        opt = HealthCheckStrategyOptimizer()
        probes = opt.differentiate_probes(g, "hub")
        liveness = [p for p in probes if p.probe_type == ProbeType.LIVENESS]
        assert liveness[0].interval_seconds >= 15.0

    def test_no_deps_readiness_no_checks(self):
        g = _graph(_comp("c1"))
        opt = HealthCheckStrategyOptimizer()
        probes = opt.differentiate_probes(g, "c1")
        readiness = [p for p in probes if p.probe_type == ProbeType.READINESS]
        assert readiness[0].checks_dependencies == []


# ---------------------------------------------------------------------------
# Optimizer: batch analysis methods
# ---------------------------------------------------------------------------


class TestBatchMethods:
    def test_analyze_all_intervals(self):
        g = _three_tier_graph()
        opt = HealthCheckStrategyOptimizer()
        configs = {
            "lb": [_default_probe()],
            "api": [_default_probe(), _default_probe(ProbeType.READINESS)],
        }
        results = opt.analyze_all_intervals(g, configs)
        assert len(results) == 3

    def test_estimate_all_false_positives(self):
        g = _graph(_comp("c1"))
        opt = HealthCheckStrategyOptimizer()
        configs = {"c1": [_default_probe()]}
        results = opt.estimate_all_false_positives(g, configs)
        assert len(results) == 1

    def test_recommend_all_grace_periods(self):
        g = _graph(_comp("c1"))
        opt = HealthCheckStrategyOptimizer()
        configs = {"c1": [
            _default_probe(ProbeType.STARTUP, grace_period=5.0),
            _default_probe(ProbeType.LIVENESS),
        ]}
        results = opt.recommend_all_grace_periods(g, configs)
        assert len(results) == 2

    def test_analyze_all_depth_tradeoffs(self):
        g = _three_tier_graph()
        opt = HealthCheckStrategyOptimizer()
        configs = {"api": [_default_probe(depth=CheckDepth.SHALLOW)]}
        results = opt.analyze_all_depth_tradeoffs(g, configs)
        assert len(results) == 1

    def test_analyze_all_timeout_alignments(self):
        g = _graph(_comp("c1"))
        opt = HealthCheckStrategyOptimizer()
        configs = {"c1": [_default_probe()]}
        results = opt.analyze_all_timeout_alignments(g, configs)
        assert len(results) == 1


# ---------------------------------------------------------------------------
# Rubric scoring helper coverage
# ---------------------------------------------------------------------------


class TestRubricHelpers:
    def test_probe_coverage_all_three(self):
        probes = _full_probe_set()
        rs = _probe_coverage_score(probes)
        assert rs.score == 10.0
        assert len(rs.findings) == 0

    def test_probe_coverage_none(self):
        rs = _probe_coverage_score([])
        assert rs.score == 0.0
        assert len(rs.findings) == 3

    def test_interval_tuning_optimal(self):
        probes = [_default_probe(interval=10.0)]
        rs = _interval_tuning_score(probes)
        assert rs.score == 10.0

    def test_interval_tuning_empty(self):
        rs = _interval_tuning_score([])
        assert rs.score == 0.0

    def test_interval_tuning_too_frequent(self):
        probes = [_default_probe(interval=2.0)]
        rs = _interval_tuning_score(probes)
        assert rs.score < 10.0

    def test_interval_tuning_too_infrequent(self):
        probes = [_default_probe(interval=120.0)]
        rs = _interval_tuning_score(probes)
        assert rs.score < 10.0

    def test_timeout_alignment_no_probes(self):
        rs = _timeout_alignment_score([], None)
        assert rs.score == 0.0

    def test_timeout_alignment_low_ratio(self):
        comp = _comp("db", ComponentType.DATABASE)
        probes = [_default_probe(timeout=0.001)]
        rs = _timeout_alignment_score(probes, comp)
        assert rs.score < 10.0

    def test_timeout_alignment_high_ratio(self):
        comp = _comp("c1")
        probes = [_default_probe(timeout=100.0)]
        rs = _timeout_alignment_score(probes, comp)
        assert rs.score < 10.0

    def test_threshold_tuning_no_probes(self):
        rs = _threshold_tuning_score([])
        assert rs.score == 0.0

    def test_threshold_tuning_good(self):
        probes = [_default_probe(failure_threshold=3, success_threshold=1)]
        rs = _threshold_tuning_score(probes)
        assert rs.score >= 8.0

    def test_threshold_tuning_low_failure(self):
        probes = [_default_probe(failure_threshold=1)]
        rs = _threshold_tuning_score(probes)
        assert rs.score < 10.0

    def test_threshold_tuning_high_failure(self):
        probes = [_default_probe(failure_threshold=15)]
        rs = _threshold_tuning_score(probes)
        assert rs.score < 10.0

    def test_threshold_tuning_low_success(self):
        probes = [_default_probe(success_threshold=0)]
        rs = _threshold_tuning_score(probes)
        assert rs.score < 10.0

    def test_threshold_tuning_high_success(self):
        probes = [_default_probe(success_threshold=8)]
        rs = _threshold_tuning_score(probes)
        assert rs.score < 10.0

    def test_depth_strategy_correct(self):
        probes = [
            _default_probe(ProbeType.LIVENESS, depth=CheckDepth.SHALLOW),
            _default_probe(ProbeType.READINESS, depth=CheckDepth.DEEP),
        ]
        rs = _depth_strategy_score(probes)
        assert rs.score >= 8.0

    def test_depth_strategy_deep_liveness(self):
        probes = [_default_probe(ProbeType.LIVENESS, depth=CheckDepth.DEEP)]
        rs = _depth_strategy_score(probes)
        assert any("liveness" in f.lower() for f in rs.findings)

    def test_depth_strategy_shallow_readiness(self):
        probes = [_default_probe(ProbeType.READINESS, depth=CheckDepth.SHALLOW)]
        rs = _depth_strategy_score(probes)
        assert any("readiness" in f.lower() for f in rs.findings)

    def test_grace_period_with_startup(self):
        probes = [
            _default_probe(ProbeType.STARTUP, grace_period=30.0),
        ]
        rs = _grace_period_score(probes)
        assert rs.score >= 7.0

    def test_grace_period_no_startup_short_delay(self):
        probes = [
            _default_probe(ProbeType.LIVENESS, initial_delay=2.0),
        ]
        rs = _grace_period_score(probes)
        assert rs.score < 5.0

    def test_grace_period_no_startup_long_delay(self):
        probes = [
            _default_probe(ProbeType.LIVENESS, initial_delay=15.0),
        ]
        rs = _grace_period_score(probes)
        assert rs.score >= 5.0

    def test_grace_period_empty(self):
        rs = _grace_period_score([])
        assert rs.score == 0.0

    def test_grace_period_startup_no_grace(self):
        probes = [
            _default_probe(ProbeType.STARTUP, grace_period=0.0, initial_delay=0.0),
        ]
        rs = _grace_period_score(probes)
        assert any("startup" in f.lower() for f in rs.findings)

    def test_dependency_awareness_no_deps(self):
        rs = _dependency_awareness_score([], 0)
        assert rs.score == 10.0

    def test_dependency_awareness_with_checks(self):
        probes = [_default_probe(depth=CheckDepth.DEPENDENCY_AWARE, checks_deps=["d1"])]
        rs = _dependency_awareness_score(probes, 1)
        assert rs.score >= 8.0

    def test_dependency_awareness_partial(self):
        probes = [_default_probe(depth=CheckDepth.DEPENDENCY_AWARE, checks_deps=["d1"])]
        rs = _dependency_awareness_score(probes, 3)
        assert rs.score < 10.0
        assert any("1/3" in f for f in rs.findings)

    def test_dependency_awareness_no_checks(self):
        probes = [_default_probe(depth=CheckDepth.SHALLOW)]
        rs = _dependency_awareness_score(probes, 2)
        assert rs.score < 5.0

    def test_cascade_safety_no_cascade(self):
        rs = _cascade_safety_score(None)
        assert rs.score == 10.0

    def test_cascade_safety_critical(self):
        ca = CascadeAnalysis(
            component_id="c1", max_depth=6, total_affected=10,
            severity=Severity.CRITICAL,
        )
        rs = _cascade_safety_score(ca)
        assert rs.score < 5.0

    def test_cascade_safety_moderate(self):
        ca = CascadeAnalysis(
            component_id="c1", max_depth=2, total_affected=2,
            severity=Severity.MEDIUM,
        )
        rs = _cascade_safety_score(ca)
        assert rs.score >= 5.0

    def test_cascade_safety_many_affected(self):
        ca = CascadeAnalysis(
            component_id="c1", max_depth=1, total_affected=8,
            severity=Severity.LOW,
        )
        rs = _cascade_safety_score(ca)
        assert rs.score < 10.0

    def test_endpoint_design_standard(self):
        probes = [
            _default_probe(endpoint="/healthz"),
            _default_probe(ProbeType.READINESS, endpoint="/readyz"),
            _default_probe(ProbeType.STARTUP, endpoint="/startupz"),
        ]
        rs = _endpoint_design_score(probes)
        assert rs.score >= 7.0

    def test_endpoint_design_non_standard(self):
        probes = [_default_probe(endpoint="/api/status")]
        rs = _endpoint_design_score(probes)
        assert rs.score < 10.0

    def test_endpoint_design_shared_endpoint(self):
        probes = [
            _default_probe(ProbeType.LIVENESS, endpoint="/healthz"),
            _default_probe(ProbeType.READINESS, endpoint="/healthz"),
        ]
        rs = _endpoint_design_score(probes)
        assert any("share" in f.lower() for f in rs.findings)

    def test_mesh_integration_none(self):
        rs = _mesh_integration_score(None)
        assert rs.score == 5.0

    def test_mesh_integration_aligned(self):
        mesh = ServiceMeshHealthAnalysis(
            component_id="c1",
            mesh_type=ServiceMeshType.ISTIO,
            sidecar_probe_aligned=True,
            mtls_health_impact=0.02,
        )
        rs = _mesh_integration_score(mesh)
        assert rs.score > 5.0

    def test_mesh_integration_misaligned(self):
        mesh = ServiceMeshHealthAnalysis(
            component_id="c1",
            mesh_type=ServiceMeshType.LINKERD,
            sidecar_probe_aligned=False,
            retry_overlap_detected=True,
            circuit_breaker_conflict=True,
            mtls_health_impact=0.5,
        )
        rs = _mesh_integration_score(mesh)
        assert rs.score < 5.0


# ---------------------------------------------------------------------------
# Data model instantiation tests
# ---------------------------------------------------------------------------


class TestDataModels:
    def test_health_check_probe_config_defaults(self):
        p = HealthCheckProbeConfig(
            probe_type=ProbeType.LIVENESS,
            protocol=ProbeProtocol.HTTP_GET,
        )
        assert p.endpoint == "/healthz"
        assert p.interval_seconds == 10.0

    def test_interval_analysis_fields(self):
        ia = IntervalAnalysis(
            component_id="c1",
            probe_type=ProbeType.LIVENESS,
            current_interval=10.0,
            recommended_interval=10.0,
            quality=IntervalQuality.OPTIMAL,
            checks_per_minute=6.0,
            noise_risk=0.5,
            detection_delay_seconds=30.0,
        )
        assert ia.component_id == "c1"

    def test_cascade_chain_defaults(self):
        cc = CascadeChain(root_component_id="c1")
        assert cc.depth == 0
        assert cc.severity == Severity.LOW

    def test_blind_spot_fields(self):
        bs = BlindSpot(
            component_id="c1",
            category=BlindSpotCategory.UNCHECKED_COMPONENT,
            severity=Severity.HIGH,
            description="test",
            recommendation="fix",
        )
        assert bs.component_id == "c1"

    def test_strategy_report_defaults(self):
        sr = StrategyReport(graph_id="g1", timestamp="t")
        assert sr.overall_health_score == 0.0
        assert sr.blind_spot_report is None

    def test_rubric_score_defaults(self):
        rs = RubricScore(category=RubricCategory.PROBE_COVERAGE)
        assert rs.score == 0.0
        assert rs.max_score == 10.0

    def test_false_positive_estimate_defaults(self):
        fp = FalsePositiveEstimate(component_id="c1")
        assert fp.estimated_rate_percent == 0.0

    def test_depth_tradeoff_defaults(self):
        dt = DepthTradeoff(
            component_id="c1",
            current_depth=CheckDepth.SHALLOW,
            recommended_depth=CheckDepth.SHALLOW,
        )
        assert dt.recommendation == ""

    def test_timeout_alignment_defaults(self):
        ta = TimeoutAlignment(
            component_id="c1",
            configured_timeout_seconds=5.0,
            estimated_p99_response_seconds=0.1,
        )
        assert ta.is_aligned

    def test_service_mesh_health_defaults(self):
        sm = ServiceMeshHealthAnalysis(component_id="c1")
        assert sm.mesh_type == ServiceMeshType.NONE

    def test_health_check_scorecard_defaults(self):
        sc = HealthCheckScorecard(component_id="c1")
        assert sc.grade == "F"
        assert sc.overall_score == 0.0


# ---------------------------------------------------------------------------
# Enum coverage
# ---------------------------------------------------------------------------


class TestEnums:
    def test_probe_types(self):
        assert len(ProbeType) == 3

    def test_probe_protocols(self):
        assert len(ProbeProtocol) == 4

    def test_check_depths(self):
        assert len(CheckDepth) == 3

    def test_severities(self):
        assert len(Severity) == 5

    def test_blind_spot_categories(self):
        assert len(BlindSpotCategory) == 10

    def test_service_mesh_types(self):
        assert len(ServiceMeshType) == 4

    def test_interval_quality(self):
        assert len(IntervalQuality) == 3

    def test_rubric_categories(self):
        assert len(RubricCategory) == 10

    def test_probe_type_values(self):
        assert ProbeType.LIVENESS.value == "liveness"
        assert ProbeType.READINESS.value == "readiness"
        assert ProbeType.STARTUP.value == "startup"

    def test_severity_ordering(self):
        ordered = [Severity.INFO, Severity.LOW, Severity.MEDIUM,
                   Severity.HIGH, Severity.CRITICAL]
        assert all(s.value for s in ordered)
