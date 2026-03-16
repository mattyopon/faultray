"""Tests for the Timeout Budget Analyzer module.

Covers all classes, enums, analysis logic, edge cases, and report generation
to achieve 100% code coverage (280+ statements in source).
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone

from faultray.model.components import (
    CircuitBreakerConfig,
    Component,
    ComponentType,
    Dependency,
    RetryStrategy,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.timeout_budget_analyzer import (
    CircuitBreakerState,
    CircuitBreakerTimeoutImpact,
    CascadeStep,
    DeadlineHop,
    DeadlinePropagation,
    HopBudget,
    JitterRecommendation,
    JitterStrategy,
    OptimalTimeout,
    PathBudgetVisualization,
    RetryTimeoutInteraction,
    Severity,
    SlowConsumerMismatch,
    TimeoutBudgetAnalyzer,
    TimeoutBudgetReport,
    TimeoutCascadeResult,
    TimeoutConfig,
    TimeoutInconsistency,
    TimeoutKind,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(
    cid: str = "c1",
    ctype: ComponentType = ComponentType.APP_SERVER,
    timeout_seconds: float = 30.0,
    max_rps: int = 5000,
) -> Component:
    c = Component(id=cid, name=cid, type=ctype)
    c.capacity.timeout_seconds = timeout_seconds
    c.capacity.max_rps = max_rps
    return c


def _graph(*comps: Component) -> InfraGraph:
    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    return g


# ===================================================================
# 1. Enum tests
# ===================================================================


class TestTimeoutKindEnum:
    def test_values(self):
        assert TimeoutKind.CONNECTION == "connection"
        assert TimeoutKind.READ == "read"
        assert TimeoutKind.WRITE == "write"

    def test_member_count(self):
        assert len(TimeoutKind) == 3

    def test_str_mixin(self):
        assert isinstance(TimeoutKind.CONNECTION, str)


class TestSeverityEnum:
    def test_values(self):
        assert Severity.INFO == "info"
        assert Severity.WARNING == "warning"
        assert Severity.CRITICAL == "critical"

    def test_member_count(self):
        assert len(Severity) == 3


class TestJitterStrategyEnum:
    def test_values(self):
        assert JitterStrategy.NONE == "none"
        assert JitterStrategy.UNIFORM == "uniform"
        assert JitterStrategy.DECORRELATED == "decorrelated"
        assert JitterStrategy.EQUAL == "equal"

    def test_member_count(self):
        assert len(JitterStrategy) == 4


class TestCircuitBreakerStateEnum:
    def test_values(self):
        assert CircuitBreakerState.CLOSED == "closed"
        assert CircuitBreakerState.OPEN == "open"
        assert CircuitBreakerState.HALF_OPEN == "half_open"

    def test_member_count(self):
        assert len(CircuitBreakerState) == 3


# ===================================================================
# 2. Dataclass construction tests
# ===================================================================


class TestTimeoutConfig:
    def test_defaults(self):
        tc = TimeoutConfig(component_id="x")
        assert tc.component_id == "x"
        assert tc.connection_timeout_ms == 1000.0
        assert tc.read_timeout_ms == 5000.0
        assert tc.write_timeout_ms == 3000.0

    def test_max_timeout(self):
        tc = TimeoutConfig(
            component_id="x",
            connection_timeout_ms=100,
            read_timeout_ms=9999,
            write_timeout_ms=500,
        )
        assert tc.max_timeout_ms == 9999

    def test_max_timeout_write_largest(self):
        tc = TimeoutConfig(
            component_id="x",
            connection_timeout_ms=100,
            read_timeout_ms=200,
            write_timeout_ms=5000,
        )
        assert tc.max_timeout_ms == 5000


class TestTimeoutInconsistency:
    def test_construction(self):
        ti = TimeoutInconsistency(
            caller_id="a",
            callee_id="b",
            caller_timeout_ms=1000,
            callee_timeout_ms=5000,
            severity=Severity.CRITICAL,
            description="test",
        )
        assert ti.caller_id == "a"
        assert ti.callee_id == "b"
        assert ti.severity == Severity.CRITICAL


class TestRetryTimeoutInteraction:
    def test_construction(self):
        rti = RetryTimeoutInteraction(
            component_id="a",
            target_id="b",
            single_attempt_timeout_ms=1000,
            max_retries=3,
            retry_delay_total_ms=700,
            total_retry_budget_ms=4700,
            caller_timeout_ms=5000,
            fits_in_caller_window=True,
            description="fits",
        )
        assert rti.fits_in_caller_window is True
        assert rti.max_retries == 3


class TestCascadeStep:
    def test_construction(self):
        cs = CascadeStep(
            component_id="c1",
            timeout_ms=1000,
            cumulative_ms=1000,
            is_blocking=True,
        )
        assert cs.is_blocking is True


class TestDeadlineHop:
    def test_construction(self):
        dh = DeadlineHop(
            component_id="c1",
            processing_time_ms=50.0,
            remaining_before_ms=1000.0,
            remaining_after_ms=950.0,
            exceeded=False,
        )
        assert dh.exceeded is False


class TestSlowConsumerMismatch:
    def test_construction(self):
        sc = SlowConsumerMismatch(
            producer_id="p1",
            consumer_id="c1",
            producer_rate_rps=100.0,
            consumer_processing_ms=50.0,
            consumer_timeout_ms=5000.0,
            queue_buildup_rate=80.0,
            severity=Severity.CRITICAL,
            description="test",
        )
        assert sc.producer_id == "p1"
        assert sc.queue_buildup_rate == 80.0


class TestHopBudget:
    def test_construction(self):
        hb = HopBudget(
            component_id="c1",
            allocated_ms=1000.0,
            expected_latency_ms=50.0,
            percent_of_total=33.3,
        )
        assert hb.percent_of_total == 33.3


# ===================================================================
# 3. TimeoutBudgetAnalyzer -- config helpers
# ===================================================================


class TestAnalyzerConfigHelpers:
    def test_set_and_get_timeout_config(self):
        g = _graph(_comp("s1"))
        analyzer = TimeoutBudgetAnalyzer(g)
        cfg = TimeoutConfig(component_id="s1", read_timeout_ms=2000)
        analyzer.set_timeout_config(cfg)
        got = analyzer.get_timeout_config("s1")
        assert got.read_timeout_ms == 2000

    def test_default_timeout_config_from_component(self):
        """If no config set, derive from component capacity.timeout_seconds."""
        c = _comp("s1", timeout_seconds=10.0)
        g = _graph(c)
        analyzer = TimeoutBudgetAnalyzer(g)
        got = analyzer.get_timeout_config("s1")
        assert got.read_timeout_ms == 10000.0  # 10s * 1000
        assert got.connection_timeout_ms == 5000.0  # capped at 5000
        assert got.write_timeout_ms == 6000.0  # 10000 * 0.6

    def test_default_timeout_config_unknown_component(self):
        """Unknown component falls back to 30s."""
        g = _graph(_comp("s1"))
        analyzer = TimeoutBudgetAnalyzer(g)
        got = analyzer.get_timeout_config("unknown")
        assert got.read_timeout_ms == 30000.0

    def test_set_latency_percentiles(self):
        g = _graph(_comp("s1"))
        analyzer = TimeoutBudgetAnalyzer(g)
        analyzer.set_latency_percentiles("s1", p50_ms=10, p95_ms=50, p99_ms=100)
        assert analyzer._latency_data["s1"]["p99"] == 100

    def test_set_processing_time(self):
        g = _graph(_comp("s1"))
        analyzer = TimeoutBudgetAnalyzer(g)
        analyzer.set_processing_time("s1", 25.0)
        assert analyzer._processing_times["s1"] == 25.0

    def test_set_producer_rate(self):
        g = _graph(_comp("s1"))
        analyzer = TimeoutBudgetAnalyzer(g)
        analyzer.set_producer_rate("s1", 500.0)
        assert analyzer._producer_rates["s1"] == 500.0


# ===================================================================
# 4. Inconsistency detection
# ===================================================================


class TestDetectInconsistencies:
    def test_no_deps_no_issues(self):
        g = _graph(_comp("a"), _comp("b"))
        analyzer = TimeoutBudgetAnalyzer(g)
        assert analyzer.detect_inconsistencies() == []

    def test_caller_shorter_than_callee_warning(self):
        a = _comp("a", timeout_seconds=5)
        b = _comp("b", timeout_seconds=8)
        g = _graph(a, b)
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        analyzer = TimeoutBudgetAnalyzer(g)
        issues = analyzer.detect_inconsistencies()
        assert len(issues) == 1
        assert issues[0].severity == Severity.WARNING
        assert issues[0].caller_id == "a"
        assert issues[0].callee_id == "b"

    def test_caller_much_shorter_critical(self):
        a = _comp("a", timeout_seconds=2)
        b = _comp("b", timeout_seconds=10)
        g = _graph(a, b)
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        analyzer = TimeoutBudgetAnalyzer(g)
        issues = analyzer.detect_inconsistencies()
        assert len(issues) == 1
        assert issues[0].severity == Severity.CRITICAL

    def test_no_issue_when_caller_longer(self):
        a = _comp("a", timeout_seconds=30)
        b = _comp("b", timeout_seconds=5)
        g = _graph(a, b)
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        analyzer = TimeoutBudgetAnalyzer(g)
        assert analyzer.detect_inconsistencies() == []

    def test_caller_zero_timeout(self):
        """Edge case: caller timeout 0 should still detect callee > 0."""
        a = _comp("a", timeout_seconds=0)
        b = _comp("b", timeout_seconds=5)
        g = _graph(a, b)
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        analyzer = TimeoutBudgetAnalyzer(g)
        # With timeout_seconds=0, read_timeout is 0; callee is 5000 => ratio = inf => CRITICAL
        # Actually, connection_timeout_ms = min(0, 5000)=0, read_timeout_ms=0, write_timeout_ms=0
        # So caller_to=0 < callee_to=5000 => ratio = inf => CRITICAL
        issues = analyzer.detect_inconsistencies()
        assert len(issues) == 1
        assert issues[0].severity == Severity.CRITICAL


# ===================================================================
# 5. Retry-timeout interaction analysis
# ===================================================================


class TestRetryTimeoutInteractions:
    def test_no_retries_returns_empty(self):
        a = _comp("a")
        b = _comp("b")
        g = _graph(a, b)
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        analyzer = TimeoutBudgetAnalyzer(g)
        assert analyzer.analyze_retry_timeout_interactions() == []

    def test_retries_fit_in_window(self):
        a = _comp("a", timeout_seconds=60)
        b = _comp("b", timeout_seconds=5)
        g = _graph(a, b)
        g.add_dependency(
            Dependency(
                source_id="a",
                target_id="b",
                retry_strategy=RetryStrategy(
                    enabled=True,
                    max_retries=2,
                    initial_delay_ms=100.0,
                    multiplier=2.0,
                    max_delay_ms=1000.0,
                ),
            )
        )
        analyzer = TimeoutBudgetAnalyzer(g)
        results = analyzer.analyze_retry_timeout_interactions()
        assert len(results) == 1
        assert results[0].fits_in_caller_window is True
        assert "fits" in results[0].description

    def test_retries_exceed_window(self):
        a = _comp("a", timeout_seconds=5)
        b = _comp("b", timeout_seconds=10)
        g = _graph(a, b)
        g.add_dependency(
            Dependency(
                source_id="a",
                target_id="b",
                retry_strategy=RetryStrategy(
                    enabled=True,
                    max_retries=3,
                    initial_delay_ms=500.0,
                    multiplier=2.0,
                    max_delay_ms=5000.0,
                ),
            )
        )
        analyzer = TimeoutBudgetAnalyzer(g)
        results = analyzer.analyze_retry_timeout_interactions()
        assert len(results) == 1
        assert results[0].fits_in_caller_window is False
        assert "EXCEEDS" in results[0].description


# ===================================================================
# 6. Timeout cascade modelling
# ===================================================================


class TestTimeoutCascade:
    def test_single_hop(self):
        a = _comp("a", timeout_seconds=5)
        g = _graph(a)
        analyzer = TimeoutBudgetAnalyzer(g)
        result = analyzer.model_timeout_cascade(["a"])
        assert len(result.steps) == 1
        assert result.total_cascade_ms == 5000.0
        assert result.exceeds_end_to_end is False

    def test_multi_hop_within_budget(self):
        a = _comp("a", timeout_seconds=2)
        b = _comp("b", timeout_seconds=3)
        g = _graph(a, b)
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        analyzer = TimeoutBudgetAnalyzer(g)
        result = analyzer.model_timeout_cascade(["a", "b"], end_to_end_budget_ms=10000)
        assert result.total_cascade_ms == 5000.0
        assert result.exceeds_end_to_end is False

    def test_multi_hop_exceeds_budget(self):
        a = _comp("a", timeout_seconds=5)
        b = _comp("b", timeout_seconds=5)
        c = _comp("c", timeout_seconds=5)
        g = _graph(a, b, c)
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        g.add_dependency(Dependency(source_id="b", target_id="c"))
        analyzer = TimeoutBudgetAnalyzer(g)
        result = analyzer.model_timeout_cascade(
            ["a", "b", "c"], end_to_end_budget_ms=10000
        )
        assert result.total_cascade_ms == 15000.0
        assert result.exceeds_end_to_end is True

    def test_cascade_blocking_detection(self):
        a = _comp("a")
        b = _comp("b")
        g = _graph(a, b)
        g.add_dependency(
            Dependency(source_id="a", target_id="b", dependency_type="requires")
        )
        analyzer = TimeoutBudgetAnalyzer(g)
        result = analyzer.model_timeout_cascade(["a", "b"])
        # "a" has a requires dependency outward, so its step should be blocking
        assert result.steps[0].is_blocking is True


# ===================================================================
# 7. Deadline propagation
# ===================================================================


class TestDeadlinePropagation:
    def test_deadline_not_exceeded(self):
        a = _comp("a")
        b = _comp("b")
        g = _graph(a, b)
        analyzer = TimeoutBudgetAnalyzer(g)
        analyzer.set_processing_time("a", 100.0)
        analyzer.set_processing_time("b", 200.0)
        result = analyzer.propagate_deadline(["a", "b"], initial_deadline_ms=1000.0)
        assert result.deadline_exceeded is False
        assert result.remaining_at_end_ms == 700.0
        assert len(result.hops) == 2
        assert result.hops[0].remaining_after_ms == 900.0
        assert result.hops[1].remaining_after_ms == 700.0

    def test_deadline_exceeded(self):
        a = _comp("a")
        b = _comp("b")
        g = _graph(a, b)
        analyzer = TimeoutBudgetAnalyzer(g)
        analyzer.set_processing_time("a", 600.0)
        analyzer.set_processing_time("b", 600.0)
        result = analyzer.propagate_deadline(["a", "b"], initial_deadline_ms=1000.0)
        assert result.deadline_exceeded is True
        assert result.remaining_at_end_ms == -200.0
        assert result.hops[1].exceeded is True

    def test_deadline_zero_processing(self):
        """Components without explicit processing time default to 0."""
        a = _comp("a")
        g = _graph(a)
        analyzer = TimeoutBudgetAnalyzer(g)
        result = analyzer.propagate_deadline(["a"], initial_deadline_ms=500.0)
        assert result.deadline_exceeded is False
        assert result.remaining_at_end_ms == 500.0


# ===================================================================
# 8. Jitter recommendations
# ===================================================================


class TestJitterRecommendations:
    def test_database_gets_decorrelated(self):
        db = _comp("db1", ctype=ComponentType.DATABASE)
        g = _graph(db)
        analyzer = TimeoutBudgetAnalyzer(g)
        recs = analyzer.recommend_jitter()
        assert len(recs) == 1
        assert recs[0].recommended_strategy == JitterStrategy.DECORRELATED
        assert "thundering herd" in recs[0].reason

    def test_cache_gets_decorrelated(self):
        cache = _comp("cache1", ctype=ComponentType.CACHE)
        g = _graph(cache)
        analyzer = TimeoutBudgetAnalyzer(g)
        recs = analyzer.recommend_jitter()
        assert recs[0].recommended_strategy == JitterStrategy.DECORRELATED

    def test_high_fanin_gets_decorrelated(self):
        target = _comp("target")
        deps = [_comp(f"dep{i}") for i in range(5)]
        g = _graph(target, *deps)
        for d in deps:
            g.add_dependency(Dependency(source_id=d.id, target_id="target"))
        analyzer = TimeoutBudgetAnalyzer(g)
        recs = analyzer.recommend_jitter()
        target_rec = [r for r in recs if r.component_id == "target"][0]
        assert target_rec.recommended_strategy == JitterStrategy.DECORRELATED
        assert "fan-in" in target_rec.reason

    def test_no_jitter_gets_uniform(self):
        app = _comp("app1", ctype=ComponentType.APP_SERVER)
        g = _graph(app)
        analyzer = TimeoutBudgetAnalyzer(g)
        recs = analyzer.recommend_jitter()
        assert recs[0].recommended_strategy == JitterStrategy.UNIFORM

    def test_existing_jitter_kept(self):
        a = _comp("a")
        b = _comp("b")
        g = _graph(a, b)
        g.add_dependency(
            Dependency(
                source_id="a",
                target_id="b",
                retry_strategy=RetryStrategy(enabled=True, jitter=True),
            )
        )
        analyzer = TimeoutBudgetAnalyzer(g)
        recs = analyzer.recommend_jitter()
        a_rec = [r for r in recs if r.component_id == "a"][0]
        # "a" has uniform jitter and is not DB/cache/high-fanin, so current is adequate
        assert a_rec.current_strategy == JitterStrategy.UNIFORM
        assert "adequate" in a_rec.reason

    def test_jitter_range_is_20_percent(self):
        app = _comp("app1", timeout_seconds=10)
        g = _graph(app)
        analyzer = TimeoutBudgetAnalyzer(g)
        recs = analyzer.recommend_jitter()
        assert recs[0].jitter_range_ms == 2000.0  # 20% of 10000


# ===================================================================
# 9. Circuit breaker impact
# ===================================================================


class TestCircuitBreakerImpact:
    def test_no_cb_returns_empty(self):
        a = _comp("a")
        b = _comp("b")
        g = _graph(a, b)
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        analyzer = TimeoutBudgetAnalyzer(g)
        assert analyzer.analyze_circuit_breaker_impact() == []

    def test_cb_with_latency_data(self):
        a = _comp("a", max_rps=1000)
        b = _comp("b", timeout_seconds=5)
        g = _graph(a, b)
        g.add_dependency(
            Dependency(
                source_id="a",
                target_id="b",
                circuit_breaker=CircuitBreakerConfig(
                    enabled=True,
                    failure_threshold=5,
                    recovery_timeout_seconds=60.0,
                ),
            )
        )
        analyzer = TimeoutBudgetAnalyzer(g)
        analyzer.set_latency_percentiles("b", p50_ms=100, p95_ms=2000, p99_ms=6000)
        results = analyzer.analyze_circuit_breaker_impact()
        assert len(results) == 1
        assert results[0].component_id == "a"
        assert results[0].target_id == "b"
        assert results[0].timeout_failure_rate > 0

    def test_cb_without_latency_defaults(self):
        a = _comp("a")
        b = _comp("b")
        g = _graph(a, b)
        g.add_dependency(
            Dependency(
                source_id="a",
                target_id="b",
                circuit_breaker=CircuitBreakerConfig(
                    enabled=True,
                    failure_threshold=10,
                    recovery_timeout_seconds=30.0,
                ),
            )
        )
        analyzer = TimeoutBudgetAnalyzer(g)
        results = analyzer.analyze_circuit_breaker_impact()
        assert len(results) == 1
        # Default failure rate is 0.05 (5%), threshold=10 => 5 < 10 => won't trip
        assert results[0].timeout_failure_rate == 0.05
        assert results[0].will_trip_breaker is False
        assert results[0].state_after_timeouts == CircuitBreakerState.HALF_OPEN

    def test_cb_will_trip_with_high_failure(self):
        a = _comp("a", max_rps=100)
        b = _comp("b", timeout_seconds=1)
        g = _graph(a, b)
        g.add_dependency(
            Dependency(
                source_id="a",
                target_id="b",
                circuit_breaker=CircuitBreakerConfig(
                    enabled=True,
                    failure_threshold=5,
                    recovery_timeout_seconds=60.0,
                ),
            )
        )
        analyzer = TimeoutBudgetAnalyzer(g)
        # p99 is way above timeout => high failure rate
        analyzer.set_latency_percentiles("b", p50_ms=500, p95_ms=900, p99_ms=5000)
        results = analyzer.analyze_circuit_breaker_impact()
        assert len(results) == 1
        assert results[0].will_trip_breaker is True
        assert results[0].state_after_timeouts == CircuitBreakerState.OPEN
        assert "WILL" in results[0].description


# ===================================================================
# 10. Optimal timeout computation
# ===================================================================


class TestOptimalTimeouts:
    def test_no_data_returns_empty(self):
        g = _graph(_comp("a"))
        analyzer = TimeoutBudgetAnalyzer(g)
        assert analyzer.compute_optimal_timeouts() == []

    def test_basic_computation(self):
        a = _comp("a", timeout_seconds=10)
        g = _graph(a)
        analyzer = TimeoutBudgetAnalyzer(g)
        analyzer.set_latency_percentiles("a", p50_ms=50, p95_ms=200, p99_ms=500)
        results = analyzer.compute_optimal_timeouts(headroom_factor=2.0)
        assert len(results) == 1
        assert results[0].recommended_timeout_ms == 1000.0  # 500 * 2.0
        assert results[0].p99_ms == 500

    def test_custom_headroom(self):
        g = _graph(_comp("a", timeout_seconds=5))
        analyzer = TimeoutBudgetAnalyzer(g)
        analyzer.set_latency_percentiles("a", p50_ms=10, p95_ms=80, p99_ms=100)
        results = analyzer.compute_optimal_timeouts(headroom_factor=3.0)
        assert results[0].recommended_timeout_ms == 300.0
        assert results[0].headroom_factor == 3.0


# ===================================================================
# 11. Slow consumer mismatch
# ===================================================================


class TestSlowConsumerMismatch:
    def test_no_async_deps(self):
        a = _comp("a")
        b = _comp("b")
        g = _graph(a, b)
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        analyzer = TimeoutBudgetAnalyzer(g)
        assert analyzer.detect_slow_consumer_mismatches() == []

    def test_slow_consumer_detected(self):
        prod = _comp("prod")
        cons = _comp("cons", timeout_seconds=5)
        g = _graph(prod, cons)
        g.add_dependency(
            Dependency(source_id="prod", target_id="cons", dependency_type="async")
        )
        analyzer = TimeoutBudgetAnalyzer(g)
        analyzer.set_producer_rate("prod", 100.0)  # 100 rps
        analyzer.set_processing_time("cons", 50.0)  # 50ms => 20 rps
        results = analyzer.detect_slow_consumer_mismatches()
        assert len(results) == 1
        assert results[0].queue_buildup_rate == 80.0  # 100 - 20
        assert results[0].severity == Severity.CRITICAL  # 80 > 50% of 100

    def test_consumer_keeps_up(self):
        prod = _comp("prod")
        cons = _comp("cons")
        g = _graph(prod, cons)
        g.add_dependency(
            Dependency(source_id="prod", target_id="cons", dependency_type="async")
        )
        analyzer = TimeoutBudgetAnalyzer(g)
        analyzer.set_producer_rate("prod", 10.0)
        analyzer.set_processing_time("cons", 5.0)  # 200 rps >> 10 rps
        results = analyzer.detect_slow_consumer_mismatches()
        assert len(results) == 0

    def test_no_producer_rate_skipped(self):
        prod = _comp("prod")
        cons = _comp("cons")
        g = _graph(prod, cons)
        g.add_dependency(
            Dependency(source_id="prod", target_id="cons", dependency_type="async")
        )
        analyzer = TimeoutBudgetAnalyzer(g)
        # No producer rate set => skip
        results = analyzer.detect_slow_consumer_mismatches()
        assert len(results) == 0

    def test_slow_consumer_warning_level(self):
        prod = _comp("prod")
        cons = _comp("cons")
        g = _graph(prod, cons)
        g.add_dependency(
            Dependency(source_id="prod", target_id="cons", dependency_type="async")
        )
        analyzer = TimeoutBudgetAnalyzer(g)
        analyzer.set_producer_rate("prod", 100.0)
        analyzer.set_processing_time("cons", 15.0)  # ~66 rps, buildup ~34
        results = analyzer.detect_slow_consumer_mismatches()
        assert len(results) == 1
        assert results[0].severity == Severity.WARNING  # 34 < 50% of 100


# ===================================================================
# 12. Path budget visualization
# ===================================================================


class TestPathBudgetVisualization:
    def test_single_path(self):
        a = _comp("a", timeout_seconds=5)
        b = _comp("b", timeout_seconds=10)
        g = _graph(a, b)
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        analyzer = TimeoutBudgetAnalyzer(g)
        analyzer.set_latency_percentiles("a", p50_ms=100, p95_ms=300, p99_ms=500)
        analyzer.set_latency_percentiles("b", p50_ms=200, p95_ms=600, p99_ms=900)
        results = analyzer.visualize_path_budgets(path=["a", "b"])
        assert len(results) == 1
        r = results[0]
        assert r.path == ["a", "b"]
        assert r.total_budget_ms == 15000.0  # 5000 + 10000
        assert len(r.hop_budgets) == 2
        assert r.hop_budgets[0].expected_latency_ms == 100.0  # p50
        assert r.utilization_percent == pytest.approx(2.0, abs=0.1)

    def test_auto_paths(self):
        a = _comp("a", timeout_seconds=2)
        b = _comp("b", timeout_seconds=3)
        g = _graph(a, b)
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        analyzer = TimeoutBudgetAnalyzer(g)
        results = analyzer.visualize_path_budgets()
        assert len(results) >= 1

    def test_empty_path_falls_back_to_all_paths(self):
        """Empty list is falsy, so visualize_path_budgets falls back to _all_paths."""
        g = _graph(_comp("a"))
        analyzer = TimeoutBudgetAnalyzer(g)
        results = analyzer.visualize_path_budgets(path=[])
        # Empty list is falsy => falls back to _all_paths => ["a"]
        assert len(results) >= 1

    def test_no_latency_data_zero_expected(self):
        a = _comp("a", timeout_seconds=5)
        g = _graph(a)
        analyzer = TimeoutBudgetAnalyzer(g)
        results = analyzer.visualize_path_budgets(path=["a"])
        assert results[0].hop_budgets[0].expected_latency_ms == 0.0
        assert results[0].utilization_percent == 0.0


# ===================================================================
# 13. Timeout kind analysis
# ===================================================================


class TestAnalyzeTimeoutKinds:
    def test_returns_all_kinds(self):
        a = _comp("a", timeout_seconds=10)
        g = _graph(a)
        analyzer = TimeoutBudgetAnalyzer(g)
        kinds = analyzer.analyze_timeout_kinds("a")
        assert TimeoutKind.CONNECTION in kinds
        assert TimeoutKind.READ in kinds
        assert TimeoutKind.WRITE in kinds
        assert kinds[TimeoutKind.READ] == 10000.0

    def test_custom_config(self):
        g = _graph(_comp("x"))
        analyzer = TimeoutBudgetAnalyzer(g)
        analyzer.set_timeout_config(
            TimeoutConfig(
                component_id="x",
                connection_timeout_ms=111,
                read_timeout_ms=222,
                write_timeout_ms=333,
            )
        )
        kinds = analyzer.analyze_timeout_kinds("x")
        assert kinds[TimeoutKind.CONNECTION] == 111
        assert kinds[TimeoutKind.READ] == 222
        assert kinds[TimeoutKind.WRITE] == 333


# ===================================================================
# 14. Full report generation
# ===================================================================


class TestGenerateReport:
    def _build_chain_graph(self):
        """Build a 3-component chain with deps, retries, and CB."""
        a = _comp("gateway", timeout_seconds=10, max_rps=500)
        b = _comp("api", timeout_seconds=15)
        c = _comp("db", ctype=ComponentType.DATABASE, timeout_seconds=20)
        g = _graph(a, b, c)
        g.add_dependency(
            Dependency(
                source_id="gateway",
                target_id="api",
                dependency_type="requires",
                retry_strategy=RetryStrategy(
                    enabled=True,
                    max_retries=2,
                    initial_delay_ms=100,
                    multiplier=2.0,
                    max_delay_ms=1000,
                ),
                circuit_breaker=CircuitBreakerConfig(
                    enabled=True,
                    failure_threshold=5,
                    recovery_timeout_seconds=30.0,
                ),
            )
        )
        g.add_dependency(
            Dependency(
                source_id="api",
                target_id="db",
                dependency_type="requires",
            )
        )
        return g

    def test_report_structure(self):
        g = self._build_chain_graph()
        analyzer = TimeoutBudgetAnalyzer(g)
        analyzer.set_latency_percentiles("api", p50_ms=20, p95_ms=100, p99_ms=300)
        analyzer.set_processing_time("gateway", 10)
        analyzer.set_processing_time("api", 50)
        analyzer.set_processing_time("db", 100)

        report = analyzer.generate_report(
            end_to_end_budget_ms=30000, headroom_factor=1.5
        )
        assert isinstance(report, TimeoutBudgetReport)
        assert report.generated_at.tzinfo == timezone.utc
        assert report.total_paths_analyzed >= 1
        assert isinstance(report.inconsistencies, list)
        assert isinstance(report.retry_interactions, list)
        assert isinstance(report.cascade_results, list)
        assert isinstance(report.deadline_propagations, list)
        assert isinstance(report.jitter_recommendations, list)
        assert isinstance(report.circuit_breaker_impacts, list)
        assert isinstance(report.optimal_timeouts, list)
        assert isinstance(report.path_budgets, list)
        assert report.overall_health in Severity

    def test_report_detects_inconsistencies(self):
        """Gateway (10s) < API (15s) < DB (20s) => inconsistencies."""
        g = self._build_chain_graph()
        analyzer = TimeoutBudgetAnalyzer(g)
        report = analyzer.generate_report()
        assert len(report.inconsistencies) > 0

    def test_report_deadline_propagation_included_with_budget(self):
        g = self._build_chain_graph()
        analyzer = TimeoutBudgetAnalyzer(g)
        analyzer.set_processing_time("gateway", 5000)
        analyzer.set_processing_time("api", 5000)
        analyzer.set_processing_time("db", 5000)
        report = analyzer.generate_report(end_to_end_budget_ms=10000)
        assert len(report.deadline_propagations) >= 1
        # At least some paths should exceed the tight budget
        exceeded = [d for d in report.deadline_propagations if d.deadline_exceeded]
        assert len(exceeded) >= 1

    def test_report_no_deadline_without_budget(self):
        g = self._build_chain_graph()
        analyzer = TimeoutBudgetAnalyzer(g)
        report = analyzer.generate_report(end_to_end_budget_ms=0)
        assert len(report.deadline_propagations) == 0

    def test_report_health_info_when_clean(self):
        """Single component with no deps => clean report."""
        g = _graph(_comp("solo", timeout_seconds=5))
        analyzer = TimeoutBudgetAnalyzer(g)
        report = analyzer.generate_report()
        assert report.overall_health == Severity.INFO
        assert len(report.inconsistencies) == 0

    def test_report_recommendations_for_optimal(self):
        """Recommendations generated when current != recommended."""
        a = _comp("a", timeout_seconds=30)
        g = _graph(a)
        analyzer = TimeoutBudgetAnalyzer(g)
        # p99 = 100ms, recommended = 150ms, current = 30000ms => "much higher"
        analyzer.set_latency_percentiles("a", p50_ms=10, p95_ms=50, p99_ms=100)
        report = analyzer.generate_report(headroom_factor=1.5)
        recs_about_a = [r for r in report.recommendations if "a" in r]
        assert len(recs_about_a) >= 1
        assert "much higher" in recs_about_a[0]

    def test_report_recommendations_for_too_low_timeout(self):
        """When current timeout is lower than recommended."""
        a = _comp("a", timeout_seconds=0.05)  # 50ms
        g = _graph(a)
        analyzer = TimeoutBudgetAnalyzer(g)
        analyzer.set_latency_percentiles("a", p50_ms=10, p95_ms=50, p99_ms=100)
        report = analyzer.generate_report(headroom_factor=1.5)
        # recommended = 150ms > current 50ms
        recs_about_a = [r for r in report.recommendations if "a" in r]
        assert len(recs_about_a) >= 1
        assert "lower than recommended" in recs_about_a[0]


# ===================================================================
# 15. Edge cases and boundary values
# ===================================================================


class TestEdgeCases:
    def test_empty_graph(self):
        g = InfraGraph()
        analyzer = TimeoutBudgetAnalyzer(g)
        report = analyzer.generate_report()
        assert report.total_paths_analyzed == 0
        assert report.overall_health == Severity.INFO

    def test_single_component_no_deps(self):
        g = _graph(_comp("solo"))
        analyzer = TimeoutBudgetAnalyzer(g)
        inconsistencies = analyzer.detect_inconsistencies()
        assert inconsistencies == []
        retries = analyzer.analyze_retry_timeout_interactions()
        assert retries == []

    def test_cascade_with_custom_configs(self):
        a = _comp("a")
        b = _comp("b")
        g = _graph(a, b)
        analyzer = TimeoutBudgetAnalyzer(g)
        analyzer.set_timeout_config(TimeoutConfig(component_id="a", read_timeout_ms=100))
        analyzer.set_timeout_config(TimeoutConfig(component_id="b", read_timeout_ms=200))
        result = analyzer.model_timeout_cascade(["a", "b"], end_to_end_budget_ms=250)
        assert result.total_cascade_ms == 300.0
        assert result.exceeds_end_to_end is True

    def test_deadline_propagation_single_hop(self):
        g = _graph(_comp("x"))
        analyzer = TimeoutBudgetAnalyzer(g)
        analyzer.set_processing_time("x", 999.0)
        dp = analyzer.propagate_deadline(["x"], initial_deadline_ms=1000.0)
        assert dp.remaining_at_end_ms == 1.0
        assert dp.deadline_exceeded is False

    def test_large_chain_performance(self):
        """Ensure reasonable performance with longer chains."""
        comps = [_comp(f"c{i}", timeout_seconds=1) for i in range(20)]
        g = _graph(*comps)
        for i in range(19):
            g.add_dependency(
                Dependency(source_id=f"c{i}", target_id=f"c{i+1}")
            )
        analyzer = TimeoutBudgetAnalyzer(g)
        cascade = analyzer.model_timeout_cascade(
            [f"c{i}" for i in range(20)], end_to_end_budget_ms=5000
        )
        assert cascade.total_cascade_ms == 20000.0
        assert cascade.exceeds_end_to_end is True

    def test_multiple_inconsistencies_in_chain(self):
        a = _comp("a", timeout_seconds=2)
        b = _comp("b", timeout_seconds=5)
        c = _comp("c", timeout_seconds=10)
        g = _graph(a, b, c)
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        g.add_dependency(Dependency(source_id="b", target_id="c"))
        analyzer = TimeoutBudgetAnalyzer(g)
        issues = analyzer.detect_inconsistencies()
        assert len(issues) == 2  # a<b and b<c

    def test_all_paths_fallback_no_edges(self):
        """Without edges, _all_paths falls back to single-component paths."""
        a = _comp("a")
        b = _comp("b")
        g = _graph(a, b)
        analyzer = TimeoutBudgetAnalyzer(g)
        paths = analyzer._all_paths()
        # No entry-to-leaf paths exist, so fallback kicks in
        assert len(paths) == 2  # each component is its own path

    def test_cb_impact_zero_failure_rate(self):
        """When p99 is well below timeout, minimal failure rate."""
        a = _comp("a", max_rps=100)
        b = _comp("b", timeout_seconds=30)
        g = _graph(a, b)
        g.add_dependency(
            Dependency(
                source_id="a",
                target_id="b",
                circuit_breaker=CircuitBreakerConfig(
                    enabled=True,
                    failure_threshold=5,
                    recovery_timeout_seconds=60.0,
                ),
            )
        )
        analyzer = TimeoutBudgetAnalyzer(g)
        analyzer.set_latency_percentiles("b", p50_ms=10, p95_ms=50, p99_ms=100)
        results = analyzer.analyze_circuit_breaker_impact()
        assert len(results) == 1
        # p99=100 vs timeout=30000 => failure_rate should be 0
        assert results[0].timeout_failure_rate == 0.0
        assert results[0].will_trip_breaker is False
        assert results[0].state_after_timeouts == CircuitBreakerState.CLOSED

    def test_slow_consumer_zero_processing_time(self):
        """Edge case: consumer processing time is 0 (infinite throughput)."""
        prod = _comp("prod")
        cons = _comp("cons")
        g = _graph(prod, cons)
        g.add_dependency(
            Dependency(source_id="prod", target_id="cons", dependency_type="async")
        )
        analyzer = TimeoutBudgetAnalyzer(g)
        analyzer.set_producer_rate("prod", 1000.0)
        analyzer.set_processing_time("cons", 0.0)  # 0 => inf throughput
        results = analyzer.detect_slow_consumer_mismatches()
        assert len(results) == 0  # consumer keeps up (infinite throughput)

    def test_report_critical_overall_health(self):
        """Report overall health is CRITICAL when critical inconsistencies exist."""
        a = _comp("a", timeout_seconds=1)
        b = _comp("b", timeout_seconds=30)
        g = _graph(a, b)
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        analyzer = TimeoutBudgetAnalyzer(g)
        report = analyzer.generate_report()
        # a(1s=1000ms) << b(30s=30000ms), ratio=30 => CRITICAL inconsistency
        assert report.overall_health == Severity.CRITICAL
        crit_recs = [r for r in report.recommendations if "critical" in r.lower()]
        assert len(crit_recs) >= 1

    def test_report_slow_consumer_critical_recommendation(self):
        """Report includes slow-consumer critical recommendation."""
        prod = _comp("prod", timeout_seconds=5)
        cons = _comp("cons", timeout_seconds=5)
        g = _graph(prod, cons)
        g.add_dependency(
            Dependency(source_id="prod", target_id="cons", dependency_type="async")
        )
        analyzer = TimeoutBudgetAnalyzer(g)
        analyzer.set_producer_rate("prod", 1000.0)
        analyzer.set_processing_time("cons", 100.0)  # 10 rps << 1000 rps
        report = analyzer.generate_report()
        slow_recs = [r for r in report.recommendations if "slow-consumer" in r]
        assert len(slow_recs) >= 1

    def test_report_warning_level(self):
        """Report overall health is WARNING for warning-level inconsistencies only."""
        # a(5s) < b(8s), ratio=1.6 < 2 => WARNING
        a = _comp("a", timeout_seconds=5)
        b = _comp("b", timeout_seconds=8)
        g = _graph(a, b)
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        analyzer = TimeoutBudgetAnalyzer(g)
        report = analyzer.generate_report()
        assert report.overall_health == Severity.WARNING
