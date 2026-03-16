"""Tests for dependency health scorer."""

from __future__ import annotations

import pytest
import networkx as nx

from faultray.model.components import (
    Capacity,
    CircuitBreakerConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    HealthStatus,
    ResourceMetrics,
    RetryStrategy,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.dependency_health_scorer import (
    CircuitBreakerReadiness,
    DependencyCriticality,
    DependencyHealthReport,
    DependencyHealthScore,
    DependencyHealthScorer,
    GraphComplexityMetrics,
    HealthDimensions,
    HealthTrend,
    RetryPolicyEvaluation,
    TimeoutAudit,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(
    cid: str = "c1",
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    health: HealthStatus = HealthStatus.HEALTHY,
    failover: bool = False,
    timeout: float = 30.0,
    cpu: float = 0.0,
    memory: float = 0.0,
) -> Component:
    return Component(
        id=cid,
        name=cid,
        type=ctype,
        replicas=replicas,
        health=health,
        failover=FailoverConfig(enabled=failover),
        capacity=Capacity(timeout_seconds=timeout),
        metrics=ResourceMetrics(cpu_percent=cpu, memory_percent=memory),
    )


def _graph(*comps: Component) -> InfraGraph:
    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    return g


def _dep(
    source: str = "a1",
    target: str = "b1",
    dep_type: str = "requires",
    latency_ms: float = 0.0,
    weight: float = 1.0,
    cb: bool = False,
    cb_threshold: int = 5,
    cb_recovery: float = 60.0,
    cb_half_open: int = 3,
    retry: bool = False,
    retry_multiplier: float = 2.0,
    retry_jitter: bool = True,
    retry_budget: float = 0.0,
    retry_max: int = 3,
) -> Dependency:
    return Dependency(
        source_id=source,
        target_id=target,
        dependency_type=dep_type,
        latency_ms=latency_ms,
        weight=weight,
        circuit_breaker=CircuitBreakerConfig(
            enabled=cb,
            failure_threshold=cb_threshold,
            recovery_timeout_seconds=cb_recovery,
            half_open_max_requests=cb_half_open,
        ),
        retry_strategy=RetryStrategy(
            enabled=retry,
            multiplier=retry_multiplier,
            jitter=retry_jitter,
            retry_budget_per_second=retry_budget,
            max_retries=retry_max,
        ),
    )


def _chain_graph() -> tuple[InfraGraph, DependencyHealthScorer]:
    """LB -> API -> DB chain with minimal config."""
    g = _graph(
        _comp("lb", ctype=ComponentType.LOAD_BALANCER, replicas=2),
        _comp("api", replicas=3),
        _comp("db", ctype=ComponentType.DATABASE),
    )
    g.add_dependency(_dep("lb", "api"))
    g.add_dependency(_dep("api", "db"))
    return g, DependencyHealthScorer()


# ---------------------------------------------------------------------------
# Tests: Enums
# ---------------------------------------------------------------------------


class TestEnums:
    def test_criticality_values(self):
        assert DependencyCriticality.CRITICAL_PATH.value == "critical_path"
        assert DependencyCriticality.NICE_TO_HAVE.value == "nice_to_have"
        assert DependencyCriticality.OPTIONAL.value == "optional"

    def test_health_trend_values(self):
        assert HealthTrend.IMPROVING.value == "improving"
        assert HealthTrend.STABLE.value == "stable"
        assert HealthTrend.DEGRADING.value == "degrading"

    def test_enums_are_str(self):
        assert isinstance(DependencyCriticality.CRITICAL_PATH, str)
        assert isinstance(HealthTrend.STABLE, str)


# ---------------------------------------------------------------------------
# Tests: Health dimensions
# ---------------------------------------------------------------------------


class TestHealthDimensions:
    def test_reliability_healthy_target(self):
        scorer = DependencyHealthScorer()
        target = _comp("t", replicas=3, failover=True)
        score = scorer._reliability_score(target)
        # HEALTHY base (100) + replicas>=3 (+10) + failover (+5) = capped 100
        assert score == 100.0

    def test_reliability_degraded_target(self):
        scorer = DependencyHealthScorer()
        target = _comp("t", health=HealthStatus.DEGRADED)
        score = scorer._reliability_score(target)
        assert score == 60.0  # base for DEGRADED

    def test_reliability_down_target(self):
        scorer = DependencyHealthScorer()
        target = _comp("t", health=HealthStatus.DOWN)
        score = scorer._reliability_score(target)
        assert score == 0.0

    def test_reliability_none_target(self):
        scorer = DependencyHealthScorer()
        score = scorer._reliability_score(None)
        assert score == 50.0

    def test_reliability_two_replicas(self):
        scorer = DependencyHealthScorer()
        target = _comp("t", replicas=2)
        score = scorer._reliability_score(target)
        # HEALTHY(100) + replicas>=2(+5) = 105 capped at 100
        assert score == 100.0

    def test_latency_zero_is_perfect(self):
        scorer = DependencyHealthScorer()
        dep = _dep(latency_ms=0.0)
        score = scorer._latency_score(dep)
        assert score == 100.0

    def test_latency_below_half_threshold(self):
        scorer = DependencyHealthScorer(latency_threshold_ms=100.0)
        dep = _dep(latency_ms=40.0)
        score = scorer._latency_score(dep)
        assert score == 100.0

    def test_latency_at_threshold(self):
        scorer = DependencyHealthScorer(latency_threshold_ms=100.0)
        dep = _dep(latency_ms=100.0)
        score = scorer._latency_score(dep)
        assert 70.0 <= score <= 85.0

    def test_latency_double_threshold(self):
        scorer = DependencyHealthScorer(latency_threshold_ms=100.0)
        dep = _dep(latency_ms=200.0)
        score = scorer._latency_score(dep)
        assert 30.0 <= score <= 45.0

    def test_latency_very_high(self):
        scorer = DependencyHealthScorer(latency_threshold_ms=100.0)
        dep = _dep(latency_ms=1000.0)
        score = scorer._latency_score(dep)
        assert score == 0.0

    def test_throughput_low_util(self):
        scorer = DependencyHealthScorer()
        target = _comp("t", cpu=0.0)
        score = scorer._throughput_score(target)
        assert score == 100.0

    def test_throughput_high_util(self):
        scorer = DependencyHealthScorer()
        target = _comp("t", cpu=95.0)
        score = scorer._throughput_score(target)
        assert score < 30.0

    def test_throughput_none_target(self):
        scorer = DependencyHealthScorer()
        score = scorer._throughput_score(None)
        assert score == 50.0

    def test_error_rate_healthy(self):
        scorer = DependencyHealthScorer()
        target = _comp("t")
        score = scorer._error_rate_score(target)
        assert score == 100.0

    def test_error_rate_overloaded(self):
        scorer = DependencyHealthScorer()
        target = _comp("t", health=HealthStatus.OVERLOADED)
        score = scorer._error_rate_score(target)
        assert score == 30.0

    def test_error_rate_none(self):
        scorer = DependencyHealthScorer()
        score = scorer._error_rate_score(None)
        assert score == 50.0

    def test_freshness_full_weight(self):
        scorer = DependencyHealthScorer()
        target = _comp("t")
        dep = _dep(weight=1.0)
        score = scorer._freshness_score(target, dep)
        assert score == 100.0

    def test_freshness_low_weight(self):
        scorer = DependencyHealthScorer()
        target = _comp("t")
        dep = _dep(weight=0.3)
        score = scorer._freshness_score(target, dep)
        assert score == 60.0

    def test_freshness_degraded_target(self):
        scorer = DependencyHealthScorer()
        target = _comp("t", health=HealthStatus.DEGRADED)
        dep = _dep(weight=1.0)
        score = scorer._freshness_score(target, dep)
        assert score == 90.0


# ---------------------------------------------------------------------------
# Tests: Criticality classification
# ---------------------------------------------------------------------------


class TestCriticalityClassification:
    def test_requires_is_critical(self):
        scorer = DependencyHealthScorer()
        dep = _dep(dep_type="requires")
        crit = scorer._classify_criticality(dep, None, _graph())
        assert crit == DependencyCriticality.CRITICAL_PATH

    def test_optional_is_optional(self):
        scorer = DependencyHealthScorer()
        dep = _dep(dep_type="optional")
        crit = scorer._classify_criticality(dep, None, _graph())
        assert crit == DependencyCriticality.OPTIONAL

    def test_async_is_nice_to_have(self):
        scorer = DependencyHealthScorer()
        dep = _dep(dep_type="async")
        crit = scorer._classify_criticality(dep, None, _graph())
        assert crit == DependencyCriticality.NICE_TO_HAVE

    def test_unknown_high_weight_is_critical(self):
        scorer = DependencyHealthScorer()
        dep = _dep(dep_type="unknown_type", weight=0.9)
        crit = scorer._classify_criticality(dep, None, _graph())
        assert crit == DependencyCriticality.CRITICAL_PATH

    def test_unknown_low_weight_is_nice_to_have(self):
        scorer = DependencyHealthScorer()
        dep = _dep(dep_type="unknown_type", weight=0.5)
        crit = scorer._classify_criticality(dep, None, _graph())
        assert crit == DependencyCriticality.NICE_TO_HAVE


# ---------------------------------------------------------------------------
# Tests: Circuit breaker readiness
# ---------------------------------------------------------------------------


class TestCircuitBreakerReadiness:
    def test_not_enabled(self):
        scorer = DependencyHealthScorer()
        dep = _dep(cb=False)
        result = scorer._assess_circuit_breaker(dep)
        assert result.enabled is False
        assert result.score == 0.0
        assert len(result.issues) >= 1

    def test_well_configured(self):
        scorer = DependencyHealthScorer()
        dep = _dep(cb=True, cb_threshold=5, cb_recovery=60.0, cb_half_open=3)
        result = scorer._assess_circuit_breaker(dep)
        assert result.enabled is True
        assert result.properly_configured is True
        assert result.score == 100.0

    def test_threshold_too_low(self):
        scorer = DependencyHealthScorer()
        dep = _dep(cb=True, cb_threshold=0)
        result = scorer._assess_circuit_breaker(dep)
        assert any("too low" in i for i in result.issues)

    def test_threshold_too_high(self):
        scorer = DependencyHealthScorer()
        dep = _dep(cb=True, cb_threshold=25)
        result = scorer._assess_circuit_breaker(dep)
        assert any("very high" in i for i in result.issues)

    def test_recovery_too_short(self):
        scorer = DependencyHealthScorer()
        dep = _dep(cb=True, cb_recovery=2.0)
        result = scorer._assess_circuit_breaker(dep)
        assert any("very short" in i for i in result.issues)

    def test_recovery_too_long(self):
        scorer = DependencyHealthScorer()
        dep = _dep(cb=True, cb_recovery=700.0)
        result = scorer._assess_circuit_breaker(dep)
        assert any("very long" in i for i in result.issues)

    def test_half_open_zero(self):
        scorer = DependencyHealthScorer()
        dep = _dep(cb=True, cb_half_open=0)
        result = scorer._assess_circuit_breaker(dep)
        assert any("zero" in i.lower() for i in result.issues)


# ---------------------------------------------------------------------------
# Tests: Retry policy evaluation
# ---------------------------------------------------------------------------


class TestRetryPolicyEvaluation:
    def test_not_enabled(self):
        scorer = DependencyHealthScorer()
        dep = _dep(retry=False)
        result = scorer._evaluate_retry_policy(dep)
        assert result.enabled is False
        assert result.score == 0.0

    def test_well_configured(self):
        scorer = DependencyHealthScorer()
        dep = _dep(
            retry=True,
            retry_multiplier=2.0,
            retry_jitter=True,
            retry_budget=10.0,
            retry_max=3,
        )
        result = scorer._evaluate_retry_policy(dep)
        assert result.enabled is True
        assert result.has_backoff is True
        assert result.has_jitter is True
        assert result.has_budget is True
        assert result.score == 100.0

    def test_no_backoff(self):
        scorer = DependencyHealthScorer()
        dep = _dep(retry=True, retry_multiplier=1.0)
        result = scorer._evaluate_retry_policy(dep)
        assert result.has_backoff is False

    def test_no_jitter(self):
        scorer = DependencyHealthScorer()
        dep = _dep(retry=True, retry_jitter=False)
        result = scorer._evaluate_retry_policy(dep)
        assert result.has_jitter is False

    def test_max_retries_too_high(self):
        scorer = DependencyHealthScorer()
        dep = _dep(retry=True, retry_max=15)
        result = scorer._evaluate_retry_policy(dep)
        assert any("high" in i.lower() for i in result.issues)

    def test_max_retries_zero(self):
        scorer = DependencyHealthScorer()
        dep = _dep(retry=True, retry_max=0)
        result = scorer._evaluate_retry_policy(dep)
        assert any("< 1" in i for i in result.issues)


# ---------------------------------------------------------------------------
# Tests: Timeout audit
# ---------------------------------------------------------------------------


class TestTimeoutAudit:
    def test_target_none(self):
        scorer = DependencyHealthScorer()
        dep = _dep()
        result = scorer._audit_timeout(None, dep)
        assert result.adequate is False
        assert result.score == 0.0

    def test_zero_timeout(self):
        scorer = DependencyHealthScorer()
        target = _comp("t", timeout=0.0)
        dep = _dep()
        result = scorer._audit_timeout(target, dep)
        assert result.adequate is False
        assert result.score == 0.0

    def test_adequate_timeout(self):
        scorer = DependencyHealthScorer()
        target = _comp("t", timeout=30.0)
        dep = _dep(latency_ms=5.0)
        result = scorer._audit_timeout(target, dep)
        assert result.adequate is True
        assert result.score == 100.0

    def test_very_high_timeout(self):
        scorer = DependencyHealthScorer()
        target = _comp("t", timeout=200.0)
        dep = _dep()
        result = scorer._audit_timeout(target, dep)
        assert any("very high" in i for i in result.issues)

    def test_very_low_timeout(self):
        scorer = DependencyHealthScorer()
        target = _comp("t", timeout=0.5)
        dep = _dep()
        result = scorer._audit_timeout(target, dep)
        assert any("very low" in i for i in result.issues)

    def test_timeout_less_than_2x_latency(self):
        scorer = DependencyHealthScorer()
        target = _comp("t", timeout=5.0)
        dep = _dep(latency_ms=4000.0)
        result = scorer._audit_timeout(target, dep)
        assert any("2x" in i for i in result.issues)


# ---------------------------------------------------------------------------
# Tests: Composite score and trend
# ---------------------------------------------------------------------------


class TestCompositeAndTrend:
    def test_perfect_dimensions_gives_high_score(self):
        scorer = DependencyHealthScorer()
        dims = HealthDimensions(
            reliability=100, latency=100, throughput=100,
            error_rate=100, freshness=100,
        )
        score = scorer._composite_score(dims, DependencyCriticality.NICE_TO_HAVE)
        assert score >= 95.0

    def test_critical_path_penalty_on_low_score(self):
        scorer = DependencyHealthScorer()
        dims = HealthDimensions(
            reliability=40, latency=40, throughput=40,
            error_rate=40, freshness=40,
        )
        crit_score = scorer._composite_score(dims, DependencyCriticality.CRITICAL_PATH)
        nice_score = scorer._composite_score(dims, DependencyCriticality.NICE_TO_HAVE)
        assert crit_score < nice_score

    def test_optional_boost(self):
        scorer = DependencyHealthScorer()
        dims = HealthDimensions(
            reliability=80, latency=80, throughput=80,
            error_rate=80, freshness=80,
        )
        opt_score = scorer._composite_score(dims, DependencyCriticality.OPTIONAL)
        nice_score = scorer._composite_score(dims, DependencyCriticality.NICE_TO_HAVE)
        assert opt_score >= nice_score

    def test_trend_improving(self):
        scorer = DependencyHealthScorer()
        assert scorer._determine_trend(50.0, 60.0) == HealthTrend.IMPROVING

    def test_trend_degrading(self):
        scorer = DependencyHealthScorer()
        assert scorer._determine_trend(60.0, 50.0) == HealthTrend.DEGRADING

    def test_trend_stable(self):
        scorer = DependencyHealthScorer()
        assert scorer._determine_trend(60.0, 62.0) == HealthTrend.STABLE

    def test_trend_from_snapshots_public(self):
        scorer = DependencyHealthScorer()
        assert scorer.trend_from_snapshots(30.0, 80.0) == HealthTrend.IMPROVING


# ---------------------------------------------------------------------------
# Tests: Fan-in / fan-out / concentration
# ---------------------------------------------------------------------------


class TestFanAnalysis:
    def test_fan_in(self):
        g = _graph(_comp("a"), _comp("b"), _comp("c"))
        g.add_dependency(_dep("a", "c"))
        g.add_dependency(_dep("b", "c"))
        scorer = DependencyHealthScorer()
        assert scorer.compute_fan_in(g, "c") == 2

    def test_fan_out(self):
        g = _graph(_comp("a"), _comp("b"), _comp("c"))
        g.add_dependency(_dep("a", "b"))
        g.add_dependency(_dep("a", "c"))
        scorer = DependencyHealthScorer()
        assert scorer.compute_fan_out(g, "a") == 2

    def test_concentration_risk_high(self):
        g = _graph(
            _comp("hub"),
            _comp("s1"), _comp("s2"), _comp("s3"), _comp("s4"),
        )
        for s in ["s1", "s2", "s3", "s4"]:
            g.add_dependency(_dep(s, "hub"))
        scorer = DependencyHealthScorer()
        risk = scorer.compute_concentration_risk(g, "hub")
        assert risk == pytest.approx(4 / 5, abs=0.01)

    def test_concentration_risk_none(self):
        g = _graph(_comp("solo"))
        scorer = DependencyHealthScorer()
        risk = scorer.compute_concentration_risk(g, "solo")
        assert risk == 0.0


# ---------------------------------------------------------------------------
# Tests: Graph complexity metrics
# ---------------------------------------------------------------------------


class TestGraphComplexity:
    def test_empty_graph(self):
        g = _graph()
        scorer = DependencyHealthScorer()
        metrics = scorer.compute_graph_complexity(g)
        assert metrics.total_nodes == 0
        assert metrics.total_edges == 0
        assert metrics.cyclomatic_complexity == 0

    def test_chain_complexity(self):
        g, scorer = _chain_graph()
        metrics = scorer.compute_graph_complexity(g)
        assert metrics.total_nodes == 3
        assert metrics.total_edges == 2
        assert metrics.max_depth == 3  # lb -> api -> db
        assert metrics.density > 0.0

    def test_diamond_width(self):
        g = _graph(_comp("a"), _comp("b"), _comp("c"), _comp("d"))
        g.add_dependency(_dep("a", "b"))
        g.add_dependency(_dep("a", "c"))
        g.add_dependency(_dep("b", "d"))
        g.add_dependency(_dep("c", "d"))
        scorer = DependencyHealthScorer()
        metrics = scorer.compute_graph_complexity(g)
        assert metrics.max_width >= 2

    def test_avg_fan_computed(self):
        g, scorer = _chain_graph()
        metrics = scorer.compute_graph_complexity(g)
        assert metrics.avg_fan_in >= 0.0
        assert metrics.avg_fan_out >= 0.0

    def test_cyclic_graph_complexity(self):
        g = _graph(_comp("a"), _comp("b"))
        g.add_dependency(_dep("a", "b"))
        g.add_dependency(_dep("b", "a"))
        scorer = DependencyHealthScorer()
        metrics = scorer.compute_graph_complexity(g)
        assert metrics.total_edges == 2
        # Cyclomatic: E - N + 2P = 2 - 2 + 2 = 2
        assert metrics.cyclomatic_complexity == 2


# ---------------------------------------------------------------------------
# Tests: Orphan detection
# ---------------------------------------------------------------------------


class TestOrphanDetection:
    def test_no_orphans_in_chain(self):
        g, scorer = _chain_graph()
        orphans = scorer.find_orphan_dependencies(g)
        assert orphans == []

    def test_orphan_detected(self):
        g = _graph(_comp("a"), _comp("b"), _comp("orphan"))
        g.add_dependency(_dep("a", "b"))
        scorer = DependencyHealthScorer()
        orphans = scorer.find_orphan_dependencies(g)
        assert "orphan" in orphans

    def test_multiple_orphans_sorted(self):
        g = _graph(_comp("z_orphan"), _comp("a_orphan"), _comp("x"))
        scorer = DependencyHealthScorer()
        orphans = scorer.find_orphan_dependencies(g)
        assert orphans == ["a_orphan", "x", "z_orphan"]


# ---------------------------------------------------------------------------
# Tests: Full report (score)
# ---------------------------------------------------------------------------


class TestFullReport:
    def test_report_structure(self):
        g, scorer = _chain_graph()
        report = scorer.score(g)
        assert isinstance(report, DependencyHealthReport)
        assert isinstance(report.scores, list)
        assert isinstance(report.graph_complexity, GraphComplexityMetrics)
        assert isinstance(report.orphan_dependencies, list)
        assert isinstance(report.recommendations, list)
        assert 0 <= report.overall_health <= 100
        assert report.timestamp  # non-empty ISO string

    def test_scores_match_edges(self):
        g, scorer = _chain_graph()
        report = scorer.score(g)
        edges = g.all_dependency_edges()
        assert len(report.scores) == len(edges)

    def test_empty_graph_report(self):
        g = _graph()
        scorer = DependencyHealthScorer()
        report = scorer.score(g)
        assert report.overall_health == 100.0
        assert report.scores == []

    def test_single_component_no_edges(self):
        g = _graph(_comp("solo"))
        scorer = DependencyHealthScorer()
        report = scorer.score(g)
        assert report.scores == []
        assert "solo" in report.orphan_dependencies

    def test_overall_health_is_average(self):
        g = _graph(_comp("a"), _comp("b"), _comp("c"))
        g.add_dependency(_dep("a", "b"))
        g.add_dependency(_dep("b", "c"))
        scorer = DependencyHealthScorer()
        report = scorer.score(g)
        if report.scores:
            expected_avg = sum(
                s.composite_score for s in report.scores
            ) / len(report.scores)
            assert report.overall_health == pytest.approx(expected_avg, abs=0.1)

    def test_score_dependency_returns_none_for_missing(self):
        g = _graph(_comp("a"), _comp("b"))
        scorer = DependencyHealthScorer()
        result = scorer.score_dependency(g, "a", "b")
        assert result is None

    def test_score_dependency_returns_score(self):
        g = _graph(_comp("a"), _comp("b"))
        g.add_dependency(_dep("a", "b"))
        scorer = DependencyHealthScorer()
        result = scorer.score_dependency(g, "a", "b")
        assert isinstance(result, DependencyHealthScore)
        assert result.source_id == "a"
        assert result.target_id == "b"


# ---------------------------------------------------------------------------
# Tests: Critical dependencies
# ---------------------------------------------------------------------------


class TestCriticalDependencies:
    def test_critical_empty_graph(self):
        g = _graph()
        scorer = DependencyHealthScorer()
        crit = scorer.critical_dependencies(g, threshold=50.0)
        assert crit == []

    def test_critical_filters_by_threshold(self):
        g = _graph(
            _comp("a"),
            _comp("b", health=HealthStatus.DOWN),
        )
        g.add_dependency(_dep("a", "b"))
        scorer = DependencyHealthScorer()
        crit = scorer.critical_dependencies(g, threshold=90.0)
        assert len(crit) >= 1

    def test_critical_sorted_ascending(self):
        g = _graph(
            _comp("a"),
            _comp("b", health=HealthStatus.DEGRADED),
            _comp("c", health=HealthStatus.DOWN),
        )
        g.add_dependency(_dep("a", "b"))
        g.add_dependency(_dep("a", "c"))
        scorer = DependencyHealthScorer()
        crit = scorer.critical_dependencies(g, threshold=100.0)
        if len(crit) >= 2:
            assert crit[0].composite_score <= crit[1].composite_score


# ---------------------------------------------------------------------------
# Tests: Recommendations
# ---------------------------------------------------------------------------


class TestRecommendations:
    def test_cb_recommendation_for_critical(self):
        g = _graph(_comp("a"), _comp("b"))
        g.add_dependency(_dep("a", "b", dep_type="requires", cb=False))
        scorer = DependencyHealthScorer()
        report = scorer.score(g)
        assert any("circuit breaker" in r.lower() for r in report.recommendations)

    def test_retry_recommendation_for_critical(self):
        g = _graph(_comp("a"), _comp("b"))
        g.add_dependency(_dep("a", "b", dep_type="requires", retry=False))
        scorer = DependencyHealthScorer()
        report = scorer.score(g)
        assert any("retry" in r.lower() for r in report.recommendations)

    def test_orphan_recommendation(self):
        g = _graph(_comp("a"), _comp("b"), _comp("orphan"))
        g.add_dependency(_dep("a", "b"))
        scorer = DependencyHealthScorer()
        report = scorer.score(g)
        assert any("orphan" in r.lower() for r in report.recommendations)

    def test_deep_graph_recommendation(self):
        comps = [_comp(f"n{i}") for i in range(8)]
        g = _graph(*comps)
        for i in range(7):
            g.add_dependency(_dep(f"n{i}", f"n{i+1}"))
        scorer = DependencyHealthScorer()
        report = scorer.score(g)
        assert any("depth" in r.lower() for r in report.recommendations)

    def test_concentration_recommendation(self):
        hub = _comp("hub")
        spokes = [_comp(f"s{i}") for i in range(6)]
        g = _graph(hub, *spokes)
        for s in spokes:
            g.add_dependency(_dep(s.id, "hub"))
        scorer = DependencyHealthScorer(concentration_threshold=3)
        report = scorer.score(g)
        assert any("concentration" in r.lower() for r in report.recommendations)

    def test_no_duplicate_recommendations(self):
        g, scorer = _chain_graph()
        report = scorer.score(g)
        assert len(report.recommendations) == len(set(report.recommendations))

    def test_high_complexity_recommendation(self):
        # Build a graph with cyclomatic > 10: needs E - N + 2P > 10
        # With 5 nodes fully connected (20 edges): 20 - 5 + 2 = 17
        comps = [_comp(f"n{i}") for i in range(5)]
        g = _graph(*comps)
        for i in range(5):
            for j in range(5):
                if i != j:
                    g.add_dependency(_dep(f"n{i}", f"n{j}"))
        scorer = DependencyHealthScorer()
        report = scorer.score(g)
        assert any("cyclomatic" in r.lower() for r in report.recommendations)

    def test_jitter_recommendation(self):
        g = _graph(_comp("a"), _comp("b"))
        g.add_dependency(
            _dep("a", "b", dep_type="requires", retry=True, retry_jitter=False)
        )
        scorer = DependencyHealthScorer()
        report = scorer.score(g)
        assert any("jitter" in r.lower() for r in report.recommendations)

    def test_low_reliability_recommendation(self):
        g = _graph(_comp("a"), _comp("b", health=HealthStatus.DOWN))
        g.add_dependency(_dep("a", "b"))
        scorer = DependencyHealthScorer()
        report = scorer.score(g)
        assert any("reliability" in r.lower() for r in report.recommendations)


# ---------------------------------------------------------------------------
# Tests: Constructor parameter clamping
# ---------------------------------------------------------------------------


class TestConstructorClamping:
    def test_latency_threshold_min(self):
        scorer = DependencyHealthScorer(latency_threshold_ms=-10.0)
        assert scorer.latency_threshold_ms == 1.0

    def test_error_rate_threshold_clamped(self):
        scorer = DependencyHealthScorer(error_rate_threshold=5.0)
        assert scorer.error_rate_threshold == 1.0

    def test_concentration_threshold_min(self):
        scorer = DependencyHealthScorer(concentration_threshold=0)
        assert scorer.concentration_threshold == 1


# ---------------------------------------------------------------------------
# Tests: Edge cases and complex topologies
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_diamond_topology(self):
        g = _graph(_comp("a"), _comp("b"), _comp("c"), _comp("d"))
        g.add_dependency(_dep("a", "b"))
        g.add_dependency(_dep("a", "c"))
        g.add_dependency(_dep("b", "d"))
        g.add_dependency(_dep("c", "d"))
        scorer = DependencyHealthScorer()
        report = scorer.score(g)
        assert len(report.scores) == 4

    def test_self_referencing_prevented(self):
        # The graph model allows self-edges; scorer should handle them
        g = _graph(_comp("a"))
        g.add_dependency(_dep("a", "a"))
        scorer = DependencyHealthScorer()
        report = scorer.score(g)
        assert len(report.scores) == 1

    def test_disconnected_subgraphs(self):
        g = _graph(_comp("a"), _comp("b"), _comp("x"), _comp("y"))
        g.add_dependency(_dep("a", "b"))
        g.add_dependency(_dep("x", "y"))
        scorer = DependencyHealthScorer()
        report = scorer.score(g)
        assert len(report.scores) == 2

    def test_optional_dep_type_gets_higher_composite(self):
        g1 = _graph(_comp("a"), _comp("b"))
        g1.add_dependency(_dep("a", "b", dep_type="requires"))
        g2 = _graph(_comp("a"), _comp("b"))
        g2.add_dependency(_dep("a", "b", dep_type="optional"))
        scorer = DependencyHealthScorer()
        r1 = scorer.score(g1)
        r2 = scorer.score(g2)
        # Optional dependencies should score higher (less impact)
        s1 = r1.scores[0].composite_score
        s2 = r2.scores[0].composite_score
        assert s2 >= s1

    def test_timestamp_is_utc_iso(self):
        g, scorer = _chain_graph()
        report = scorer.score(g)
        assert "T" in report.timestamp
        assert "+" in report.timestamp or "Z" in report.timestamp

    def test_latency_mid_range(self):
        scorer = DependencyHealthScorer(latency_threshold_ms=100.0)
        dep = _dep(latency_ms=75.0)
        score = scorer._latency_score(dep)
        assert 80.0 <= score <= 100.0

    def test_throughput_mid_util(self):
        scorer = DependencyHealthScorer()
        target = _comp("t", cpu=60.0)
        score = scorer._throughput_score(target)
        assert 80.0 <= score <= 100.0

    def test_freshness_mid_weight(self):
        scorer = DependencyHealthScorer()
        target = _comp("t")
        dep = _dep(weight=0.7)
        score = scorer._freshness_score(target, dep)
        assert score == 85.0

    def test_max_width_no_entries(self):
        """Graph where all nodes have in-degree > 0 (cycle)."""
        g = _graph(_comp("a"), _comp("b"))
        g.add_dependency(_dep("a", "b"))
        g.add_dependency(_dep("b", "a"))
        scorer = DependencyHealthScorer()
        width = scorer._compute_max_width(g._graph)
        assert width >= 1

    def test_throughput_70_to_90_range(self):
        """Covers line 431: util between 70 and 90."""
        scorer = DependencyHealthScorer()
        target = _comp("t", cpu=80.0)
        score = scorer._throughput_score(target)
        # 70 - (80-70)*2.5 = 70 - 25 = 45
        assert 40.0 <= score <= 50.0

    def test_cb_misconfigured_recommendation_in_report(self):
        """Covers lines 863-864: CB enabled but improperly configured."""
        g = _graph(_comp("a"), _comp("b"))
        g.add_dependency(
            _dep("a", "b", dep_type="requires", cb=True, cb_threshold=0)
        )
        scorer = DependencyHealthScorer()
        report = scorer.score(g)
        assert any("circuit breaker" in r.lower() for r in report.recommendations)

    def test_timeout_issues_in_recommendations(self):
        """Covers lines 879-880: timeout not adequate adds recommendation."""
        g = _graph(_comp("a"), _comp("b", timeout=200.0))
        g.add_dependency(_dep("a", "b"))
        scorer = DependencyHealthScorer()
        report = scorer.score(g)
        assert any("timeout" in r.lower() for r in report.recommendations)

    def test_low_latency_recommendation(self):
        """Covers line 889: latency score < 50 adds recommendation."""
        g = _graph(_comp("a"), _comp("b"))
        g.add_dependency(_dep("a", "b", latency_ms=500.0))
        scorer = DependencyHealthScorer(latency_threshold_ms=100.0)
        report = scorer.score(g)
        assert any("latency" in r.lower() for r in report.recommendations)

    def test_cyclic_graph_path_search_with_entries_leaves(self):
        """Covers lines 775-781: cyclic graph path depth calculation.

        Build a graph with a cycle where entry and leaf nodes exist alongside
        the cycle to exercise the simple-paths search in the else branch.
        """
        g = _graph(_comp("entry"), _comp("a"), _comp("b"), _comp("leaf"))
        g.add_dependency(_dep("entry", "a"))
        g.add_dependency(_dep("a", "b"))
        g.add_dependency(_dep("b", "a"))  # cycle
        g.add_dependency(_dep("b", "leaf"))
        scorer = DependencyHealthScorer()
        metrics = scorer.compute_graph_complexity(g)
        assert metrics.max_depth >= 2

    def test_cyclic_graph_no_entries_no_leaves(self):
        """Covers lines 767-770: cycle with no entry/leaf nodes."""
        g = _graph(_comp("a"), _comp("b"), _comp("c"))
        g.add_dependency(_dep("a", "b"))
        g.add_dependency(_dep("b", "c"))
        g.add_dependency(_dep("c", "a"))
        scorer = DependencyHealthScorer()
        metrics = scorer.compute_graph_complexity(g)
        # All nodes have in-degree > 0, so entries fallback to first node
        assert metrics.total_nodes == 3

    def test_cyclic_graph_entry_equals_leaf_skip(self):
        """Covers line 773-774: entry == leaf in cyclic path search."""
        g = _graph(_comp("a"), _comp("b"))
        g.add_dependency(_dep("a", "b"))
        g.add_dependency(_dep("b", "a"))
        scorer = DependencyHealthScorer()
        metrics = scorer.compute_graph_complexity(g)
        # entry fallback = [a], leaf fallback = [a] => entry == leaf => skip
        assert metrics.total_edges == 2

    def test_weakly_connected_networkx_error(self):
        """Covers lines 753-754: NetworkXError on weakly connected components."""
        from unittest.mock import patch

        g, scorer = _chain_graph()

        with patch(
            "networkx.number_weakly_connected_components",
            side_effect=nx.NetworkXError("mock"),
        ):
            metrics = scorer.compute_graph_complexity(g)
        # Fallback num_weakly = 1, so cyclomatic = E - N + 2*1 = 2-3+2 = 1
        assert metrics.cyclomatic_complexity == 1

    def test_dag_longest_path_networkx_error(self):
        """Covers lines 780-781: outer NetworkXError in graph complexity."""
        from unittest.mock import patch

        g, scorer = _chain_graph()

        with patch(
            "networkx.is_directed_acyclic_graph",
            side_effect=nx.NetworkXError("mock"),
        ):
            metrics = scorer.compute_graph_complexity(g)
        assert metrics.max_depth == 0  # fallback when exception caught

    def test_cyclic_simple_paths_networkx_error(self):
        """Covers lines 778-779: NetworkXError in all_simple_paths for cyclic graph."""
        from unittest.mock import patch

        g = _graph(_comp("entry"), _comp("a"), _comp("b"), _comp("leaf"))
        g.add_dependency(_dep("entry", "a"))
        g.add_dependency(_dep("a", "b"))
        g.add_dependency(_dep("b", "a"))  # cycle
        g.add_dependency(_dep("b", "leaf"))

        scorer = DependencyHealthScorer()

        with patch(
            "networkx.all_simple_paths",
            side_effect=nx.NetworkXError("mock"),
        ):
            metrics = scorer.compute_graph_complexity(g)
        assert isinstance(metrics, GraphComplexityMetrics)
