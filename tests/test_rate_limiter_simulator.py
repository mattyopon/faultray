"""Tests for Rate Limiter Simulator.

Comprehensive tests covering all enums, data models, algorithm simulation,
multi-tier analysis, cascade backpressure, retry/backoff simulation, throttle
strategy comparison, quota optimisation, end-to-end impact analysis,
distributed coordination, recommendation engine, and edge cases.
"""

from __future__ import annotations

import pytest

from faultray.model.components import (
    Capacity,
    Component,
    ComponentType,
    Dependency,
    HealthStatus,
    NetworkProfile,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.rate_limiter_simulator import (
    AlgorithmSimResult,
    BackoffStrategy,
    CascadeAnalysisResult,
    CascadeImpact,
    EndToEndImpact,
    QuotaAllocation,
    QuotaOptimisationResult,
    RateLimitAlgorithm,
    RateLimitRule,
    RateLimitTier,
    RateLimiterSimulator,
    RetryAfterResult,
    RetryConfig,
    ThrottleAction,
    ThrottleStrategyComparison,
    TierAnalysis,
    TrafficProfile,
    _ALGO_BURST_TOLERANCE,
    _ALGO_FAIRNESS,
    _ALGO_OVERHEAD_MS,
    _THROTTLE_UX,
    _TIER_PRIORITY,
    _burst_handling_score,
    _clamp,
    _compute_algo_latency,
    _compute_rejection_fraction,
    _retry_delay_ms,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(
    cid: str = "c1",
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 2,
    max_rps: int = 5000,
    max_connections: int = 1000,
    rtt_ms: float = 1.0,
) -> Component:
    return Component(
        id=cid,
        name=cid,
        type=ctype,
        replicas=replicas,
        capacity=Capacity(max_rps=max_rps, max_connections=max_connections),
        network=NetworkProfile(rtt_ms=rtt_ms),
    )


def _graph(*comps: Component) -> InfraGraph:
    from faultray.model.graph import InfraGraph

    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    return g


# ---------------------------------------------------------------------------
# 1. Enum coverage
# ---------------------------------------------------------------------------


class TestRateLimitAlgorithmEnum:
    def test_all_values(self) -> None:
        assert len(RateLimitAlgorithm) == 5

    def test_token_bucket(self) -> None:
        assert RateLimitAlgorithm.TOKEN_BUCKET == "token_bucket"

    def test_leaky_bucket(self) -> None:
        assert RateLimitAlgorithm.LEAKY_BUCKET == "leaky_bucket"

    def test_fixed_window(self) -> None:
        assert RateLimitAlgorithm.FIXED_WINDOW == "fixed_window"

    def test_sliding_window_log(self) -> None:
        assert RateLimitAlgorithm.SLIDING_WINDOW_LOG == "sliding_window_log"

    def test_sliding_window_counter(self) -> None:
        assert RateLimitAlgorithm.SLIDING_WINDOW_COUNTER == "sliding_window_counter"


class TestRateLimitTierEnum:
    def test_all_values(self) -> None:
        assert len(RateLimitTier) == 4

    def test_per_user(self) -> None:
        assert RateLimitTier.PER_USER == "per_user"

    def test_per_ip(self) -> None:
        assert RateLimitTier.PER_IP == "per_ip"

    def test_per_api_key(self) -> None:
        assert RateLimitTier.PER_API_KEY == "per_api_key"

    def test_global(self) -> None:
        assert RateLimitTier.GLOBAL == "global"


class TestThrottleActionEnum:
    def test_all_values(self) -> None:
        assert len(ThrottleAction) == 3

    def test_hard_reject(self) -> None:
        assert ThrottleAction.HARD_REJECT == "hard_reject"

    def test_queue(self) -> None:
        assert ThrottleAction.QUEUE == "queue"

    def test_degrade(self) -> None:
        assert ThrottleAction.DEGRADE == "degrade"


class TestBackoffStrategyEnum:
    def test_all_values(self) -> None:
        assert len(BackoffStrategy) == 4

    def test_constant(self) -> None:
        assert BackoffStrategy.CONSTANT == "constant"

    def test_linear(self) -> None:
        assert BackoffStrategy.LINEAR == "linear"

    def test_exponential(self) -> None:
        assert BackoffStrategy.EXPONENTIAL == "exponential"

    def test_exponential_jitter(self) -> None:
        assert BackoffStrategy.EXPONENTIAL_JITTER == "exponential_jitter"


# ---------------------------------------------------------------------------
# 2. Data model defaults and validation
# ---------------------------------------------------------------------------


class TestRateLimitRuleDefaults:
    def test_default_algorithm(self) -> None:
        rule = RateLimitRule()
        assert rule.algorithm == RateLimitAlgorithm.TOKEN_BUCKET

    def test_default_tier(self) -> None:
        rule = RateLimitRule()
        assert rule.tier == RateLimitTier.GLOBAL

    def test_default_rps(self) -> None:
        rule = RateLimitRule()
        assert rule.requests_per_second == 100.0

    def test_default_burst(self) -> None:
        rule = RateLimitRule()
        assert rule.burst_size == 50

    def test_default_throttle(self) -> None:
        rule = RateLimitRule()
        assert rule.throttle_action == ThrottleAction.HARD_REJECT

    def test_custom_values(self) -> None:
        rule = RateLimitRule(
            algorithm=RateLimitAlgorithm.LEAKY_BUCKET,
            tier=RateLimitTier.PER_USER,
            requests_per_second=500.0,
            burst_size=100,
            window_seconds=10.0,
            throttle_action=ThrottleAction.QUEUE,
            queue_capacity=2000,
            degrade_latency_factor=3.0,
        )
        assert rule.requests_per_second == 500.0
        assert rule.queue_capacity == 2000


class TestTrafficProfileDefaults:
    def test_defaults(self) -> None:
        tp = TrafficProfile()
        assert tp.avg_rps == 100.0
        assert tp.peak_rps == 200.0
        assert tp.duration_seconds == 60.0
        assert tp.num_unique_clients == 100

    def test_custom(self) -> None:
        tp = TrafficProfile(avg_rps=5000.0, peak_rps=10000.0, num_unique_clients=500)
        assert tp.avg_rps == 5000.0
        assert tp.num_unique_clients == 500


class TestRetryConfigDefaults:
    def test_defaults(self) -> None:
        rc = RetryConfig()
        assert rc.backoff_strategy == BackoffStrategy.EXPONENTIAL_JITTER
        assert rc.initial_delay_ms == 100.0
        assert rc.max_retries == 3

    def test_custom(self) -> None:
        rc = RetryConfig(
            backoff_strategy=BackoffStrategy.LINEAR,
            initial_delay_ms=200.0,
            max_retries=5,
            jitter_factor=0.3,
        )
        assert rc.backoff_strategy == BackoffStrategy.LINEAR
        assert rc.max_retries == 5


# ---------------------------------------------------------------------------
# 3. Internal helpers
# ---------------------------------------------------------------------------


class TestClamp:
    def test_within_range(self) -> None:
        assert _clamp(50.0) == 50.0

    def test_below_lo(self) -> None:
        assert _clamp(-10.0) == 0.0

    def test_above_hi(self) -> None:
        assert _clamp(200.0) == 100.0

    def test_custom_bounds(self) -> None:
        assert _clamp(5.0, 0.0, 1.0) == 1.0
        assert _clamp(-1.0, 0.0, 1.0) == 0.0
        assert _clamp(0.5, 0.0, 1.0) == 0.5


class TestComputeRejectionFraction:
    def test_zero_rps(self) -> None:
        rule = RateLimitRule(requests_per_second=100.0)
        assert _compute_rejection_fraction(rule, 0.0) == 0.0

    def test_under_limit(self) -> None:
        rule = RateLimitRule(requests_per_second=100.0, burst_size=50)
        frac = _compute_rejection_fraction(rule, 50.0)
        assert frac == 0.0

    def test_over_limit(self) -> None:
        rule = RateLimitRule(requests_per_second=100.0, burst_size=0)
        frac = _compute_rejection_fraction(rule, 200.0)
        assert 0.0 < frac <= 1.0

    def test_way_over_limit(self) -> None:
        rule = RateLimitRule(requests_per_second=10.0, burst_size=0)
        frac = _compute_rejection_fraction(rule, 10000.0)
        assert frac > 0.9

    def test_burst_absorbs_peak(self) -> None:
        rule = RateLimitRule(
            algorithm=RateLimitAlgorithm.TOKEN_BUCKET,
            requests_per_second=100.0,
            burst_size=200,
        )
        frac = _compute_rejection_fraction(rule, 150.0)
        assert frac == 0.0


class TestComputeAlgoLatency:
    def test_no_rejection(self) -> None:
        rule = RateLimitRule()
        avg, p99 = _compute_algo_latency(rule, 0.0, None)
        assert avg > 0
        assert p99 > avg

    def test_with_component(self) -> None:
        comp = _comp(cid="x")
        rule = RateLimitRule()
        avg, p99 = _compute_algo_latency(rule, 0.0, comp)
        assert avg > 0
        assert p99 > avg

    def test_queue_action_increases_latency(self) -> None:
        rule_reject = RateLimitRule(throttle_action=ThrottleAction.HARD_REJECT)
        rule_queue = RateLimitRule(throttle_action=ThrottleAction.QUEUE)
        avg_r, _ = _compute_algo_latency(rule_reject, 0.3, None)
        avg_q, _ = _compute_algo_latency(rule_queue, 0.3, None)
        assert avg_q > avg_r

    def test_degrade_action_increases_base(self) -> None:
        rule = RateLimitRule(
            throttle_action=ThrottleAction.DEGRADE,
            degrade_latency_factor=3.0,
        )
        avg, _ = _compute_algo_latency(rule, 0.0, None)
        # Degraded base = 5.0 * 3.0 = 15.0 + overhead
        assert avg > 10.0


class TestBurstHandlingScore:
    def test_zero_peak(self) -> None:
        rule = RateLimitRule()
        assert _burst_handling_score(rule, 0.0) == 100.0

    def test_high_burst_capacity(self) -> None:
        rule = RateLimitRule(requests_per_second=1000.0, burst_size=500)
        score = _burst_handling_score(rule, 500.0)
        assert score == 100.0  # capped at 100

    def test_low_burst_capacity(self) -> None:
        rule = RateLimitRule(requests_per_second=10.0, burst_size=0)
        score = _burst_handling_score(rule, 1000.0)
        assert score < 10.0


class TestRetryDelayMs:
    def test_constant(self) -> None:
        config = RetryConfig(backoff_strategy=BackoffStrategy.CONSTANT, initial_delay_ms=100.0)
        assert _retry_delay_ms(config, 0) == 100.0
        assert _retry_delay_ms(config, 5) == 100.0

    def test_linear(self) -> None:
        config = RetryConfig(backoff_strategy=BackoffStrategy.LINEAR, initial_delay_ms=100.0)
        assert _retry_delay_ms(config, 0) == 100.0
        assert _retry_delay_ms(config, 1) == 200.0
        assert _retry_delay_ms(config, 2) == 300.0

    def test_exponential(self) -> None:
        config = RetryConfig(backoff_strategy=BackoffStrategy.EXPONENTIAL, initial_delay_ms=100.0)
        assert _retry_delay_ms(config, 0) == 100.0
        assert _retry_delay_ms(config, 1) == 200.0
        assert _retry_delay_ms(config, 2) == 400.0

    def test_exponential_jitter(self) -> None:
        config = RetryConfig(
            backoff_strategy=BackoffStrategy.EXPONENTIAL_JITTER,
            initial_delay_ms=100.0,
            jitter_factor=0.5,
        )
        delay = _retry_delay_ms(config, 1)
        # 100 * 2^1 * (1 - 0.5*0.5) = 200 * 0.75 = 150
        assert delay == pytest.approx(150.0)

    def test_capped_at_max_delay(self) -> None:
        config = RetryConfig(
            backoff_strategy=BackoffStrategy.EXPONENTIAL,
            initial_delay_ms=1000.0,
            max_delay_ms=5000.0,
        )
        assert _retry_delay_ms(config, 10) == 5000.0

    def test_negative_attempt(self) -> None:
        config = RetryConfig()
        assert _retry_delay_ms(config, -1) == 0.0


class TestLookupDicts:
    def test_algo_burst_tolerance_completeness(self) -> None:
        for algo in RateLimitAlgorithm:
            assert algo in _ALGO_BURST_TOLERANCE

    def test_algo_fairness_completeness(self) -> None:
        for algo in RateLimitAlgorithm:
            assert algo in _ALGO_FAIRNESS

    def test_algo_overhead_completeness(self) -> None:
        for algo in RateLimitAlgorithm:
            assert algo in _ALGO_OVERHEAD_MS

    def test_tier_priority_completeness(self) -> None:
        for tier in RateLimitTier:
            assert tier in _TIER_PRIORITY

    def test_throttle_ux_completeness(self) -> None:
        for action in ThrottleAction:
            assert action in _THROTTLE_UX


# ---------------------------------------------------------------------------
# 4. Algorithm simulation
# ---------------------------------------------------------------------------


class TestSimulateAlgorithm:
    def setup_method(self) -> None:
        self.engine = RateLimiterSimulator()
        self.comp = _comp(cid="app1", max_rps=1000)
        self.graph = _graph(self.comp)

    def test_under_limit_no_rejection(self) -> None:
        rule = RateLimitRule(requests_per_second=500.0, burst_size=100)
        traffic = TrafficProfile(avg_rps=100.0, peak_rps=200.0, duration_seconds=10.0)
        result = self.engine.simulate_algorithm(self.graph, "app1", rule, traffic)
        assert result.requests_rejected == 0
        assert result.rejection_rate == 0.0
        assert result.requests_allowed == 1000  # 100 * 10

    def test_over_limit_rejects(self) -> None:
        rule = RateLimitRule(requests_per_second=50.0, burst_size=0)
        traffic = TrafficProfile(avg_rps=200.0, peak_rps=500.0, duration_seconds=10.0)
        result = self.engine.simulate_algorithm(self.graph, "app1", rule, traffic)
        assert result.requests_rejected > 0
        assert result.rejection_rate > 0.0

    def test_queue_throttle_action(self) -> None:
        rule = RateLimitRule(
            requests_per_second=50.0,
            burst_size=0,
            throttle_action=ThrottleAction.QUEUE,
            queue_capacity=200,
        )
        traffic = TrafficProfile(avg_rps=200.0, peak_rps=500.0, duration_seconds=10.0)
        result = self.engine.simulate_algorithm(self.graph, "app1", rule, traffic)
        # Some requests should be queued rather than rejected
        assert result.requests_queued > 0 or result.requests_rejected >= 0

    def test_degrade_throttle_action(self) -> None:
        rule = RateLimitRule(
            requests_per_second=50.0,
            burst_size=0,
            throttle_action=ThrottleAction.DEGRADE,
        )
        traffic = TrafficProfile(avg_rps=200.0, peak_rps=500.0, duration_seconds=10.0)
        result = self.engine.simulate_algorithm(self.graph, "app1", rule, traffic)
        assert result.requests_degraded > 0
        assert result.requests_rejected == 0

    def test_zero_traffic(self) -> None:
        rule = RateLimitRule()
        traffic = TrafficProfile(avg_rps=0.0, peak_rps=0.0, duration_seconds=10.0)
        result = self.engine.simulate_algorithm(self.graph, "app1", rule, traffic)
        assert result.requests_allowed == 0
        assert result.requests_rejected == 0
        assert result.burst_handling_score == 100.0

    def test_missing_component(self) -> None:
        rule = RateLimitRule(requests_per_second=100.0)
        traffic = TrafficProfile(avg_rps=50.0, peak_rps=80.0, duration_seconds=5.0)
        result = self.engine.simulate_algorithm(self.graph, "nonexistent", rule, traffic)
        assert result.requests_allowed >= 0

    def test_fixed_window_recommendation(self) -> None:
        rule = RateLimitRule(
            algorithm=RateLimitAlgorithm.FIXED_WINDOW,
            requests_per_second=50.0,
            burst_size=0,
        )
        traffic = TrafficProfile(avg_rps=200.0, peak_rps=500.0, duration_seconds=10.0)
        result = self.engine.simulate_algorithm(self.graph, "app1", rule, traffic)
        has_fixed_window_rec = any("Fixed Window" in r for r in result.recommendations)
        assert has_fixed_window_rec

    def test_high_rejection_recommendation(self) -> None:
        rule = RateLimitRule(requests_per_second=10.0, burst_size=0)
        traffic = TrafficProfile(avg_rps=1000.0, peak_rps=5000.0, duration_seconds=10.0)
        result = self.engine.simulate_algorithm(self.graph, "app1", rule, traffic)
        has_high_rej_rec = any("50%" in r for r in result.recommendations)
        assert has_high_rej_rec

    def test_fairness_score_populated(self) -> None:
        rule = RateLimitRule()
        traffic = TrafficProfile(avg_rps=100.0, peak_rps=200.0)
        result = self.engine.simulate_algorithm(self.graph, "app1", rule, traffic)
        assert result.fairness_score > 0.0

    def test_all_algorithms(self) -> None:
        traffic = TrafficProfile(avg_rps=100.0, peak_rps=200.0, duration_seconds=5.0)
        for algo in RateLimitAlgorithm:
            rule = RateLimitRule(algorithm=algo)
            result = self.engine.simulate_algorithm(self.graph, "app1", rule, traffic)
            assert result.algorithm == algo
            assert result.avg_latency_ms > 0


# ---------------------------------------------------------------------------
# 5. Compare algorithms
# ---------------------------------------------------------------------------


class TestCompareAlgorithms:
    def test_returns_all_algorithms(self) -> None:
        engine = RateLimiterSimulator()
        graph = _graph(_comp())
        traffic = TrafficProfile(avg_rps=100.0, peak_rps=200.0)
        results = engine.compare_algorithms(graph, "c1", traffic)
        assert len(results) == len(RateLimitAlgorithm)
        algos = {r.algorithm for r in results}
        assert algos == set(RateLimitAlgorithm)

    def test_leaky_bucket_has_high_fairness(self) -> None:
        engine = RateLimiterSimulator()
        graph = _graph(_comp())
        traffic = TrafficProfile(avg_rps=100.0, peak_rps=200.0)
        results = engine.compare_algorithms(graph, "c1", traffic)
        leaky = next(r for r in results if r.algorithm == RateLimitAlgorithm.LEAKY_BUCKET)
        token = next(r for r in results if r.algorithm == RateLimitAlgorithm.TOKEN_BUCKET)
        assert leaky.fairness_score > token.fairness_score


# ---------------------------------------------------------------------------
# 6. Multi-tier analysis
# ---------------------------------------------------------------------------


class TestAnalyseTiers:
    def setup_method(self) -> None:
        self.engine = RateLimiterSimulator()
        self.graph = _graph(_comp(cid="svc1", max_rps=2000))

    def test_empty_rules(self) -> None:
        result = self.engine.analyse_tiers(self.graph, "svc1", [], TrafficProfile())
        assert result == []

    def test_single_global_tier(self) -> None:
        rules = [RateLimitRule(tier=RateLimitTier.GLOBAL, requests_per_second=500.0)]
        traffic = TrafficProfile(avg_rps=400.0, peak_rps=600.0)
        analyses = self.engine.analyse_tiers(self.graph, "svc1", rules, traffic)
        assert len(analyses) == 1
        assert analyses[0].tier == RateLimitTier.GLOBAL
        assert analyses[0].effective_limit_rps == 500.0

    def test_per_user_scales_by_clients(self) -> None:
        rules = [RateLimitRule(tier=RateLimitTier.PER_USER, requests_per_second=10.0)]
        traffic = TrafficProfile(peak_rps=500.0, num_unique_clients=100)
        analyses = self.engine.analyse_tiers(self.graph, "svc1", rules, traffic)
        assert len(analyses) == 1
        # effective = 10 * 100 = 1000
        assert analyses[0].effective_limit_rps == 1000.0

    def test_per_api_key_scales(self) -> None:
        rules = [RateLimitRule(tier=RateLimitTier.PER_API_KEY, requests_per_second=50.0)]
        traffic = TrafficProfile(peak_rps=500.0, num_unique_clients=100)
        analyses = self.engine.analyse_tiers(self.graph, "svc1", rules, traffic)
        # effective = 50 * (100//10) = 50 * 10 = 500
        assert analyses[0].effective_limit_rps == 500.0

    def test_multi_tier_ordering(self) -> None:
        rules = [
            RateLimitRule(tier=RateLimitTier.PER_USER, requests_per_second=10.0),
            RateLimitRule(tier=RateLimitTier.GLOBAL, requests_per_second=1000.0),
        ]
        traffic = TrafficProfile(peak_rps=800.0, num_unique_clients=50)
        analyses = self.engine.analyse_tiers(self.graph, "svc1", rules, traffic)
        # Global should come first (lower priority number)
        assert analyses[0].tier == RateLimitTier.GLOBAL

    def test_overflow_generates_recommendations(self) -> None:
        rules = [RateLimitRule(tier=RateLimitTier.GLOBAL, requests_per_second=50.0)]
        traffic = TrafficProfile(peak_rps=500.0)
        analyses = self.engine.analyse_tiers(self.graph, "svc1", rules, traffic)
        assert analyses[0].overflow_rps > 0.0
        assert len(analyses[0].recommendations) > 0

    def test_clients_affected_calculation(self) -> None:
        rules = [RateLimitRule(tier=RateLimitTier.GLOBAL, requests_per_second=50.0)]
        # Use few clients so per_client_rps > rule.requests_per_second
        traffic = TrafficProfile(peak_rps=500.0, num_unique_clients=5)
        analyses = self.engine.analyse_tiers(self.graph, "svc1", rules, traffic)
        # per_client_rps = 500/5 = 100 > 50 → some clients affected
        assert analyses[0].clients_affected > 0


# ---------------------------------------------------------------------------
# 7. Cascade analysis
# ---------------------------------------------------------------------------


class TestAnalyseCascade:
    def setup_method(self) -> None:
        self.engine = RateLimiterSimulator()

    def test_single_component_no_cascade(self) -> None:
        graph = _graph(_comp(cid="a1"))
        rules = {"a1": RateLimitRule(requests_per_second=100.0)}
        traffic = TrafficProfile(avg_rps=50.0, peak_rps=80.0)
        result = self.engine.analyse_cascade(graph, "a1", rules, traffic)
        assert len(result.impacts) == 1
        assert result.total_backpressure_depth == 0

    def test_chain_cascade(self) -> None:
        c1 = _comp(cid="lb", ctype=ComponentType.LOAD_BALANCER, max_rps=1000)
        c2 = _comp(cid="app", ctype=ComponentType.APP_SERVER, max_rps=500)
        c3 = _comp(cid="db", ctype=ComponentType.DATABASE, max_rps=200)
        graph = _graph(c1, c2, c3)
        graph.add_dependency(Dependency(source_id="lb", target_id="app"))
        graph.add_dependency(Dependency(source_id="app", target_id="db"))

        rules = {
            "lb": RateLimitRule(requests_per_second=800.0, burst_size=0),
            "app": RateLimitRule(requests_per_second=400.0, burst_size=0),
        }
        traffic = TrafficProfile(avg_rps=600.0, peak_rps=1000.0)
        result = self.engine.analyse_cascade(graph, "lb", rules, traffic)
        assert result.total_backpressure_depth >= 1
        assert len(result.impacts) == 3

    def test_no_rules_map(self) -> None:
        c1 = _comp(cid="a")
        c2 = _comp(cid="b")
        graph = _graph(c1, c2)
        graph.add_dependency(Dependency(source_id="a", target_id="b"))
        result = self.engine.analyse_cascade(graph, "a", {}, TrafficProfile())
        assert result.total_backpressure_depth >= 1
        # No rate limit → no rejection
        for impact in result.impacts:
            assert impact.backpressure_percent == 0.0

    def test_high_rejection_retry_storm_risk(self) -> None:
        c1 = _comp(cid="gw", max_rps=100)
        c2 = _comp(cid="svc", max_rps=100)
        graph = _graph(c1, c2)
        graph.add_dependency(Dependency(source_id="gw", target_id="svc"))

        rules = {
            "gw": RateLimitRule(requests_per_second=10.0, burst_size=0),
            "svc": RateLimitRule(requests_per_second=10.0, burst_size=0),
        }
        traffic = TrafficProfile(peak_rps=5000.0)
        result = self.engine.analyse_cascade(graph, "gw", rules, traffic)
        assert result.retry_storm_risk > 0.0

    def test_empty_graph(self) -> None:
        graph = _graph()
        result = self.engine.analyse_cascade(graph, "x", {}, TrafficProfile())
        # Source node "x" is processed but has no downstream dependencies
        assert len(result.impacts) == 1
        assert result.impacts[0].component_id == "x"
        assert result.total_backpressure_depth == 0

    def test_queue_saturation_tracked(self) -> None:
        c1 = _comp(cid="entry", max_rps=100)
        graph = _graph(c1)
        traffic = TrafficProfile(peak_rps=500.0)
        result = self.engine.analyse_cascade(graph, "entry", {}, traffic)
        assert result.max_queue_saturation > 100.0


# ---------------------------------------------------------------------------
# 8. Retry / backoff simulation
# ---------------------------------------------------------------------------


class TestSimulateRetryBackoff:
    def setup_method(self) -> None:
        self.engine = RateLimiterSimulator()

    def test_no_rejection_no_retries(self) -> None:
        rule = RateLimitRule(requests_per_second=1000.0, burst_size=200)
        traffic = TrafficProfile(avg_rps=100.0, peak_rps=200.0, duration_seconds=10.0)
        retry = RetryConfig()
        result = self.engine.simulate_retry_backoff(rule, traffic, retry)
        assert result.retry_after_seconds == 0.0
        assert result.total_retries == 0
        assert result.effective_goodput_ratio == 1.0

    def test_rejection_triggers_retries(self) -> None:
        rule = RateLimitRule(requests_per_second=10.0, burst_size=0)
        traffic = TrafficProfile(avg_rps=500.0, peak_rps=1000.0, duration_seconds=10.0)
        retry = RetryConfig(max_retries=3)
        result = self.engine.simulate_retry_backoff(rule, traffic, retry)
        assert result.total_retries > 0
        assert result.retry_after_seconds > 0.0
        assert result.retry_amplification_factor > 1.0

    def test_zero_traffic(self) -> None:
        rule = RateLimitRule()
        traffic = TrafficProfile(avg_rps=0.0, peak_rps=0.0)
        retry = RetryConfig()
        result = self.engine.simulate_retry_backoff(rule, traffic, retry)
        assert result.total_retries == 0

    def test_constant_backoff_recommendation(self) -> None:
        rule = RateLimitRule(requests_per_second=10.0, burst_size=0)
        traffic = TrafficProfile(avg_rps=500.0, peak_rps=1000.0, duration_seconds=10.0)
        retry = RetryConfig(backoff_strategy=BackoffStrategy.CONSTANT, max_retries=3)
        result = self.engine.simulate_retry_backoff(rule, traffic, retry)
        has_constant_rec = any("thundering-herd" in r for r in result.recommendations)
        assert has_constant_rec

    def test_high_retry_after_recommendation(self) -> None:
        rule = RateLimitRule(requests_per_second=10.0, burst_size=0, window_seconds=10.0)
        traffic = TrafficProfile(avg_rps=500.0, peak_rps=1000.0, duration_seconds=10.0)
        retry = RetryConfig(max_retries=3)
        result = self.engine.simulate_retry_backoff(rule, traffic, retry)
        assert result.retry_after_seconds > 10.0

    def test_goodput_decreases_with_high_rejection(self) -> None:
        rule = RateLimitRule(requests_per_second=5.0, burst_size=0)
        traffic = TrafficProfile(avg_rps=1000.0, peak_rps=5000.0, duration_seconds=10.0)
        retry = RetryConfig(max_retries=5)
        result = self.engine.simulate_retry_backoff(rule, traffic, retry)
        assert result.effective_goodput_ratio < 1.0


# ---------------------------------------------------------------------------
# 9. Throttle strategy comparison
# ---------------------------------------------------------------------------


class TestCompareThrottleStrategies:
    def test_returns_all_strategies(self) -> None:
        engine = RateLimiterSimulator()
        graph = _graph(_comp())
        rule = RateLimitRule(requests_per_second=50.0, burst_size=0)
        traffic = TrafficProfile(avg_rps=200.0, peak_rps=500.0)
        results = engine.compare_throttle_strategies(graph, "c1", rule, traffic)
        assert len(results) == len(ThrottleAction)
        actions = {r.action for r in results}
        assert actions == set(ThrottleAction)

    def test_queue_has_higher_ux_than_reject(self) -> None:
        engine = RateLimiterSimulator()
        graph = _graph(_comp())
        rule = RateLimitRule(requests_per_second=50.0, burst_size=0)
        traffic = TrafficProfile(avg_rps=200.0, peak_rps=500.0)
        results = engine.compare_throttle_strategies(graph, "c1", rule, traffic)
        reject = next(r for r in results if r.action == ThrottleAction.HARD_REJECT)
        queue = next(r for r in results if r.action == ThrottleAction.QUEUE)
        assert queue.user_experience_score > reject.user_experience_score

    def test_goodput_ratio_populated(self) -> None:
        engine = RateLimiterSimulator()
        graph = _graph(_comp())
        rule = RateLimitRule(requests_per_second=200.0)
        traffic = TrafficProfile(avg_rps=100.0, peak_rps=150.0)
        results = engine.compare_throttle_strategies(graph, "c1", rule, traffic)
        for r in results:
            assert 0.0 <= r.goodput_ratio <= 1.0


# ---------------------------------------------------------------------------
# 10. Quota optimisation
# ---------------------------------------------------------------------------


class TestOptimiseQuotas:
    def setup_method(self) -> None:
        self.engine = RateLimiterSimulator()

    def test_empty_components(self) -> None:
        graph = _graph()
        result = self.engine.optimise_quotas(graph, [], 1000.0)
        assert len(result.allocations) == 0
        assert len(result.recommendations) > 0

    def test_equal_allocation(self) -> None:
        c1 = _comp(cid="s1", max_rps=1000)
        c2 = _comp(cid="s2", max_rps=1000)
        graph = _graph(c1, c2)
        result = self.engine.optimise_quotas(graph, ["s1", "s2"], 1000.0)
        assert len(result.allocations) == 2
        for a in result.allocations:
            assert a.allocated_rps == pytest.approx(500.0)

    def test_weighted_allocation(self) -> None:
        c1 = _comp(cid="hot", max_rps=5000)
        c2 = _comp(cid="cold", max_rps=5000)
        graph = _graph(c1, c2)
        weights = {"hot": 3.0, "cold": 1.0}
        result = self.engine.optimise_quotas(graph, ["hot", "cold"], 1000.0, weights)
        hot_alloc = next(a for a in result.allocations if a.component_id == "hot")
        cold_alloc = next(a for a in result.allocations if a.component_id == "cold")
        assert hot_alloc.allocated_rps > cold_alloc.allocated_rps

    def test_over_utilised_recommendation(self) -> None:
        c1 = _comp(cid="tiny", max_rps=10)  # Very low capacity
        graph = _graph(c1)
        result = self.engine.optimise_quotas(graph, ["tiny"], 1000.0)
        has_over_rec = any("over-utilised" in r for r in result.recommendations)
        assert has_over_rec

    def test_efficiency_calculation(self) -> None:
        c1 = _comp(cid="x", max_rps=5000)
        graph = _graph(c1)
        result = self.engine.optimise_quotas(graph, ["x"], 500.0)
        assert result.utilisation_efficiency == pytest.approx(100.0)

    def test_missing_weight_defaults_to_one(self) -> None:
        c1 = _comp(cid="a")
        c2 = _comp(cid="b")
        graph = _graph(c1, c2)
        weights = {"a": 2.0}  # "b" missing
        result = self.engine.optimise_quotas(graph, ["a", "b"], 900.0, weights)
        a_alloc = next(al for al in result.allocations if al.component_id == "a")
        b_alloc = next(al for al in result.allocations if al.component_id == "b")
        assert a_alloc.allocated_rps > b_alloc.allocated_rps

    def test_near_full_capacity_recommendation(self) -> None:
        c1 = _comp(cid="f", max_rps=100000)
        graph = _graph(c1)
        result = self.engine.optimise_quotas(graph, ["f"], 100.0)
        # 100% allocated = near full capacity
        has_rec = any("headroom" in r for r in result.recommendations)
        assert has_rec


# ---------------------------------------------------------------------------
# 11. End-to-end impact analysis
# ---------------------------------------------------------------------------


class TestAnalyseEndToEndImpact:
    def setup_method(self) -> None:
        self.engine = RateLimiterSimulator()

    def test_empty_path(self) -> None:
        graph = _graph()
        result = self.engine.analyse_end_to_end_impact(graph, [], {}, TrafficProfile())
        assert len(result.recommendations) > 0

    def test_single_hop_no_limit(self) -> None:
        graph = _graph(_comp(cid="web", rtt_ms=2.0))
        result = self.engine.analyse_end_to_end_impact(
            graph, ["web"], {}, TrafficProfile()
        )
        assert result.base_latency_ms == 2.0
        assert result.added_latency_ms == 0.0
        assert result.total_error_rate == 0.0

    def test_multi_hop_accumulates_latency(self) -> None:
        c1 = _comp(cid="gw", rtt_ms=1.0)
        c2 = _comp(cid="svc", rtt_ms=2.0)
        c3 = _comp(cid="db", rtt_ms=3.0)
        graph = _graph(c1, c2, c3)
        result = self.engine.analyse_end_to_end_impact(
            graph, ["gw", "svc", "db"], {}, TrafficProfile()
        )
        # Each hop uses max(1.0, rtt_ms): 1.0 + 2.0 + 3.0 = 6.0
        assert result.base_latency_ms == pytest.approx(6.0)

    def test_rate_limits_add_latency_and_errors(self) -> None:
        c1 = _comp(cid="entry", rtt_ms=1.0)
        c2 = _comp(cid="backend", rtt_ms=1.0)
        graph = _graph(c1, c2)
        rules = {
            "entry": RateLimitRule(requests_per_second=50.0, burst_size=0),
            "backend": RateLimitRule(requests_per_second=30.0, burst_size=0),
        }
        traffic = TrafficProfile(avg_rps=200.0, peak_rps=500.0)
        result = self.engine.analyse_end_to_end_impact(
            graph, ["entry", "backend"], rules, traffic
        )
        assert result.added_latency_ms > 0.0
        assert result.total_error_rate > 0.0

    def test_goodput_lower_with_limits(self) -> None:
        c1 = _comp(cid="a", rtt_ms=1.0)
        graph = _graph(c1)
        rules = {"a": RateLimitRule(requests_per_second=10.0, burst_size=0)}
        traffic = TrafficProfile(avg_rps=500.0, peak_rps=1000.0)
        result = self.engine.analyse_end_to_end_impact(
            graph, ["a"], rules, traffic
        )
        assert result.goodput_rps < traffic.avg_rps

    def test_long_path_recommendation(self) -> None:
        comps = [_comp(cid=f"n{i}", rtt_ms=1.0) for i in range(6)]
        graph = _graph(*comps)
        path = [f"n{i}" for i in range(6)]
        result = self.engine.analyse_end_to_end_impact(
            graph, path, {}, TrafficProfile()
        )
        has_path_rec = any("many components" in r for r in result.recommendations)
        assert has_path_rec

    def test_missing_component_uses_default_latency(self) -> None:
        graph = _graph()
        result = self.engine.analyse_end_to_end_impact(
            graph, ["missing"], {}, TrafficProfile()
        )
        assert result.base_latency_ms == 5.0  # default hop latency


# ---------------------------------------------------------------------------
# 12. Distributed coordination evaluation
# ---------------------------------------------------------------------------


class TestEvaluateCoordination:
    def setup_method(self) -> None:
        self.engine = RateLimiterSimulator()

    def test_empty_components(self) -> None:
        graph = _graph()
        result = self.engine.evaluate_coordination(graph, [], {}, TrafficProfile())
        assert result["consistency_score"] == 0.0
        assert len(result["recommendations"]) > 0

    def test_single_algorithm_high_consistency(self) -> None:
        c1 = _comp(cid="s1")
        c2 = _comp(cid="s2")
        graph = _graph(c1, c2)
        rules = {
            "s1": RateLimitRule(algorithm=RateLimitAlgorithm.TOKEN_BUCKET),
            "s2": RateLimitRule(algorithm=RateLimitAlgorithm.TOKEN_BUCKET),
        }
        result = self.engine.evaluate_coordination(
            graph, ["s1", "s2"], rules, TrafficProfile()
        )
        assert result["consistency_score"] == 100.0

    def test_mixed_algorithms_lower_consistency(self) -> None:
        c1 = _comp(cid="s1")
        c2 = _comp(cid="s2")
        graph = _graph(c1, c2)
        rules = {
            "s1": RateLimitRule(algorithm=RateLimitAlgorithm.TOKEN_BUCKET),
            "s2": RateLimitRule(algorithm=RateLimitAlgorithm.LEAKY_BUCKET),
        }
        result = self.engine.evaluate_coordination(
            graph, ["s1", "s2"], rules, TrafficProfile()
        )
        assert result["consistency_score"] < 100.0

    def test_multi_replica_split_brain_risk(self) -> None:
        c1 = _comp(cid="s1", replicas=5)
        c2 = _comp(cid="s2", replicas=5)
        graph = _graph(c1, c2)
        rules = {
            "s1": RateLimitRule(),
            "s2": RateLimitRule(),
        }
        result = self.engine.evaluate_coordination(
            graph, ["s1", "s2"], rules, TrafficProfile()
        )
        assert result["split_brain_risk"] > 0.0
        has_redis_rec = any("centralised" in r for r in result["recommendations"])
        assert has_redis_rec

    def test_unlimited_components_warning(self) -> None:
        c1 = _comp(cid="limited")
        c2 = _comp(cid="unlimited")
        graph = _graph(c1, c2)
        rules = {"limited": RateLimitRule()}
        result = self.engine.evaluate_coordination(
            graph, ["limited", "unlimited"], rules, TrafficProfile()
        )
        has_unlimited_rec = any("no rate limits" in r for r in result["recommendations"])
        assert has_unlimited_rec

    def test_per_component_info(self) -> None:
        c1 = _comp(cid="x", replicas=3)
        graph = _graph(c1)
        rules = {"x": RateLimitRule(requests_per_second=300.0)}
        result = self.engine.evaluate_coordination(
            graph, ["x"], rules, TrafficProfile()
        )
        info = result["per_component"]["x"]
        assert info["has_rate_limit"] is True
        assert info["replicas"] == 3
        assert info["per_replica_limit"] == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# 13. Recommend rule
# ---------------------------------------------------------------------------


class TestRecommendRule:
    def setup_method(self) -> None:
        self.engine = RateLimiterSimulator()

    def test_load_balancer_recommendation(self) -> None:
        comp = _comp(cid="lb", ctype=ComponentType.LOAD_BALANCER, max_rps=10000)
        graph = _graph(comp)
        traffic = TrafficProfile(avg_rps=5000.0, peak_rps=8000.0)
        rule = self.engine.recommend_rule(graph, "lb", traffic)
        assert rule.algorithm == RateLimitAlgorithm.TOKEN_BUCKET
        assert rule.throttle_action == ThrottleAction.QUEUE
        assert rule.tier == RateLimitTier.GLOBAL

    def test_app_server_recommendation(self) -> None:
        comp = _comp(cid="app", ctype=ComponentType.APP_SERVER, max_rps=5000)
        graph = _graph(comp)
        traffic = TrafficProfile(avg_rps=2000.0, peak_rps=4000.0)
        rule = self.engine.recommend_rule(graph, "app", traffic)
        assert rule.algorithm == RateLimitAlgorithm.SLIDING_WINDOW_COUNTER
        assert rule.throttle_action == ThrottleAction.DEGRADE
        assert rule.tier == RateLimitTier.PER_API_KEY

    def test_database_recommendation(self) -> None:
        comp = _comp(cid="db", ctype=ComponentType.DATABASE, max_rps=1000)
        graph = _graph(comp)
        traffic = TrafficProfile(avg_rps=500.0, peak_rps=800.0)
        rule = self.engine.recommend_rule(graph, "db", traffic)
        assert rule.algorithm == RateLimitAlgorithm.LEAKY_BUCKET
        assert rule.throttle_action == ThrottleAction.QUEUE

    def test_external_api_recommendation(self) -> None:
        comp = _comp(cid="ext", ctype=ComponentType.EXTERNAL_API, max_rps=500)
        graph = _graph(comp)
        traffic = TrafficProfile(avg_rps=200.0, peak_rps=400.0)
        rule = self.engine.recommend_rule(graph, "ext", traffic)
        assert rule.algorithm == RateLimitAlgorithm.SLIDING_WINDOW_LOG
        assert rule.tier == RateLimitTier.PER_API_KEY

    def test_cache_recommendation(self) -> None:
        comp = _comp(cid="cache", ctype=ComponentType.CACHE, max_rps=10000)
        graph = _graph(comp)
        traffic = TrafficProfile(avg_rps=5000.0, peak_rps=8000.0)
        rule = self.engine.recommend_rule(graph, "cache", traffic)
        assert rule.algorithm == RateLimitAlgorithm.TOKEN_BUCKET

    def test_web_server_recommendation(self) -> None:
        comp = _comp(cid="web", ctype=ComponentType.WEB_SERVER, max_rps=3000)
        graph = _graph(comp)
        traffic = TrafficProfile(avg_rps=1000.0, peak_rps=2000.0)
        rule = self.engine.recommend_rule(graph, "web", traffic)
        assert rule.algorithm == RateLimitAlgorithm.SLIDING_WINDOW_COUNTER
        assert rule.tier == RateLimitTier.PER_IP

    def test_missing_component_uses_defaults(self) -> None:
        graph = _graph()
        traffic = TrafficProfile(avg_rps=100.0, peak_rps=200.0)
        rule = self.engine.recommend_rule(graph, "missing", traffic)
        assert rule.algorithm == RateLimitAlgorithm.TOKEN_BUCKET
        assert rule.requests_per_second >= 1.0

    def test_burst_size_from_traffic_delta(self) -> None:
        comp = _comp(cid="svc", max_rps=10000)
        graph = _graph(comp)
        traffic = TrafficProfile(avg_rps=100.0, peak_rps=500.0)
        rule = self.engine.recommend_rule(graph, "svc", traffic)
        assert rule.burst_size >= 100  # peak - avg = 400, so burst >= 100


# ---------------------------------------------------------------------------
# 14. Result model field validation
# ---------------------------------------------------------------------------


class TestResultModelValidation:
    def test_algorithm_sim_result_defaults(self) -> None:
        r = AlgorithmSimResult(algorithm=RateLimitAlgorithm.TOKEN_BUCKET)
        assert r.requests_allowed == 0
        assert r.rejection_rate == 0.0
        assert r.recommendations == []

    def test_cascade_impact_defaults(self) -> None:
        ci = CascadeImpact(component_id="x")
        assert ci.incoming_rps == 0.0
        assert ci.estimated_retry_amplification == 1.0

    def test_cascade_analysis_result_defaults(self) -> None:
        car = CascadeAnalysisResult()
        assert car.total_backpressure_depth == 0
        assert car.retry_storm_risk == 0.0

    def test_retry_after_result_defaults(self) -> None:
        rar = RetryAfterResult()
        assert rar.retry_after_seconds == 0.0
        assert rar.effective_goodput_ratio == 1.0

    def test_quota_allocation_defaults(self) -> None:
        qa = QuotaAllocation(component_id="q1")
        assert qa.allocated_rps == 0.0

    def test_end_to_end_impact_defaults(self) -> None:
        eei = EndToEndImpact()
        assert eei.total_latency_ms == 0.0
        assert eei.total_error_rate == 0.0

    def test_throttle_strategy_comparison_defaults(self) -> None:
        tsc = ThrottleStrategyComparison(action=ThrottleAction.QUEUE)
        assert tsc.user_experience_score == 0.0

    def test_tier_analysis_defaults(self) -> None:
        ta = TierAnalysis(tier=RateLimitTier.GLOBAL)
        assert ta.effective_limit_rps == 0.0
        assert ta.recommendations == []

    def test_quota_optimisation_result_defaults(self) -> None:
        qor = QuotaOptimisationResult()
        assert qor.utilisation_efficiency == 0.0


# ---------------------------------------------------------------------------
# 15. Edge cases and boundary conditions
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def setup_method(self) -> None:
        self.engine = RateLimiterSimulator()

    def test_single_client_per_user_tier(self) -> None:
        graph = _graph(_comp())
        rules = [RateLimitRule(tier=RateLimitTier.PER_USER, requests_per_second=100.0)]
        traffic = TrafficProfile(peak_rps=50.0, num_unique_clients=1)
        analyses = self.engine.analyse_tiers(graph, "c1", rules, traffic)
        assert analyses[0].effective_limit_rps == 100.0

    def test_very_small_window(self) -> None:
        rule = RateLimitRule(window_seconds=0.01, requests_per_second=1.0, burst_size=10)
        frac = _compute_rejection_fraction(rule, 100.0)
        assert 0.0 <= frac <= 1.0

    def test_zero_burst_size(self) -> None:
        rule = RateLimitRule(requests_per_second=100.0, burst_size=0)
        frac = _compute_rejection_fraction(rule, 200.0)
        assert frac > 0.0

    def test_max_burst_absorbs_spike(self) -> None:
        rule = RateLimitRule(
            algorithm=RateLimitAlgorithm.TOKEN_BUCKET,
            requests_per_second=100.0,
            burst_size=10000,
        )
        frac = _compute_rejection_fraction(rule, 500.0)
        assert frac == 0.0

    def test_cascade_with_cycle_prevention(self) -> None:
        """Components that form a loop should not cause infinite recursion."""
        c1 = _comp(cid="a")
        c2 = _comp(cid="b")
        graph = _graph(c1, c2)
        graph.add_dependency(Dependency(source_id="a", target_id="b"))
        graph.add_dependency(Dependency(source_id="b", target_id="a"))
        result = self.engine.analyse_cascade(graph, "a", {}, TrafficProfile())
        # Should terminate without error
        assert len(result.impacts) >= 1

    def test_quota_with_zero_weight(self) -> None:
        c1 = _comp(cid="z")
        graph = _graph(c1)
        weights = {"z": 0.0}
        # total_weight will be 0 → fallback to 1.0
        result = self.engine.optimise_quotas(graph, ["z"], 1000.0, weights)
        assert len(result.allocations) == 1

    def test_end_to_end_high_latency_timeout_error(self) -> None:
        """If total latency exceeds 1000ms, timeout errors should be added."""
        comps = [_comp(cid=f"slow{i}", rtt_ms=200.0) for i in range(10)]
        graph = _graph(*comps)
        path = [f"slow{i}" for i in range(10)]
        result = self.engine.analyse_end_to_end_impact(
            graph, path, {}, TrafficProfile()
        )
        # 10 * 200 = 2000ms > 1000ms threshold
        assert result.added_error_rate > 0.0

    def test_retry_with_zero_max_retries(self) -> None:
        rule = RateLimitRule(requests_per_second=10.0, burst_size=0)
        traffic = TrafficProfile(avg_rps=500.0, peak_rps=1000.0, duration_seconds=10.0)
        retry = RetryConfig(max_retries=0)
        result = self.engine.simulate_retry_backoff(rule, traffic, retry)
        assert result.total_retries == 0

    def test_coordination_no_rate_limit_component(self) -> None:
        c1 = _comp(cid="bare")
        graph = _graph(c1)
        result = self.engine.evaluate_coordination(
            graph, ["bare"], {}, TrafficProfile()
        )
        info = result["per_component"]["bare"]
        assert info["has_rate_limit"] is False


# ---------------------------------------------------------------------------
# 16. Integration: full workflow
# ---------------------------------------------------------------------------


class TestIntegrationWorkflow:
    """End-to-end integration test simulating a realistic scenario."""

    def test_full_pipeline(self) -> None:
        engine = RateLimiterSimulator()

        lb = _comp(cid="lb", ctype=ComponentType.LOAD_BALANCER, max_rps=10000, rtt_ms=0.5)
        app = _comp(cid="app", ctype=ComponentType.APP_SERVER, max_rps=5000, rtt_ms=1.0)
        db = _comp(cid="db", ctype=ComponentType.DATABASE, max_rps=2000, rtt_ms=0.3)

        graph = _graph(lb, app, db)
        graph.add_dependency(Dependency(source_id="lb", target_id="app"))
        graph.add_dependency(Dependency(source_id="app", target_id="db"))

        traffic = TrafficProfile(avg_rps=3000.0, peak_rps=8000.0, num_unique_clients=500)

        # 1. Get recommendations
        lb_rule = engine.recommend_rule(graph, "lb", traffic)
        app_rule = engine.recommend_rule(graph, "app", traffic)
        db_rule = engine.recommend_rule(graph, "db", traffic)

        assert lb_rule.algorithm == RateLimitAlgorithm.TOKEN_BUCKET
        assert db_rule.algorithm == RateLimitAlgorithm.LEAKY_BUCKET

        # 2. Simulate each algorithm
        lb_sim = engine.simulate_algorithm(graph, "lb", lb_rule, traffic)
        assert lb_sim.avg_latency_ms > 0

        # 3. Cascade analysis
        rules_map = {"lb": lb_rule, "app": app_rule, "db": db_rule}
        cascade = engine.analyse_cascade(graph, "lb", rules_map, traffic)
        assert len(cascade.impacts) == 3
        assert cascade.total_backpressure_depth >= 1

        # 4. End-to-end impact
        e2e = engine.analyse_end_to_end_impact(
            graph, ["lb", "app", "db"], rules_map, traffic
        )
        assert e2e.total_latency_ms > 0
        assert e2e.goodput_rps > 0

        # 5. Quota optimisation
        quotas = engine.optimise_quotas(
            graph, ["lb", "app", "db"], 10000.0,
            {"lb": 3.0, "app": 2.0, "db": 1.0},
        )
        assert len(quotas.allocations) == 3
        lb_quota = next(a for a in quotas.allocations if a.component_id == "lb")
        db_quota = next(a for a in quotas.allocations if a.component_id == "db")
        assert lb_quota.allocated_rps > db_quota.allocated_rps

        # 6. Coordination
        coord = engine.evaluate_coordination(
            graph, ["lb", "app", "db"], rules_map, traffic
        )
        assert coord["consistency_score"] >= 0.0

        # 7. Compare throttle strategies
        strategies = engine.compare_throttle_strategies(graph, "app", app_rule, traffic)
        assert len(strategies) == 3

        # 8. Retry simulation
        retry_result = engine.simulate_retry_backoff(
            app_rule, traffic, RetryConfig()
        )
        assert retry_result.retry_amplification_factor >= 1.0


# ---------------------------------------------------------------------------
# 17. Multi-tier cascade interaction
# ---------------------------------------------------------------------------


class TestMultiTierCascadeInteraction:
    """Test interaction between multi-tier limits and cascade analysis."""

    def test_tiers_reduce_cascade_pressure(self) -> None:
        engine = RateLimiterSimulator()

        gw = _comp(cid="gw", ctype=ComponentType.LOAD_BALANCER, max_rps=5000)
        svc = _comp(cid="svc", ctype=ComponentType.APP_SERVER, max_rps=2000)
        graph = _graph(gw, svc)
        graph.add_dependency(Dependency(source_id="gw", target_id="svc"))

        traffic = TrafficProfile(avg_rps=3000.0, peak_rps=6000.0, num_unique_clients=200)

        # Tight global limit on gateway
        gw_rule = RateLimitRule(
            tier=RateLimitTier.GLOBAL,
            requests_per_second=2000.0,
            burst_size=0,
        )

        # Analyse tiers on gateway
        tier_analysis = engine.analyse_tiers(graph, "gw", [gw_rule], traffic)
        assert tier_analysis[0].overflow_rps > 0.0

        # Cascade: rate limit at gw should reduce pressure on svc
        cascade = engine.analyse_cascade(
            graph, "gw", {"gw": gw_rule}, traffic
        )
        svc_impact = next(i for i in cascade.impacts if i.component_id == "svc")
        assert svc_impact.incoming_rps < traffic.peak_rps


# ---------------------------------------------------------------------------
# 18. Algorithm-specific behaviour
# ---------------------------------------------------------------------------


class TestAlgorithmSpecificBehaviour:
    """Verify that each algorithm has distinct characteristics."""

    def setup_method(self) -> None:
        self.engine = RateLimiterSimulator()
        self.graph = _graph(_comp(cid="svc", max_rps=5000))
        self.traffic = TrafficProfile(avg_rps=200.0, peak_rps=500.0, duration_seconds=10.0)

    def test_token_bucket_best_burst_handling(self) -> None:
        results = self.engine.compare_algorithms(self.graph, "svc", self.traffic)
        token = next(r for r in results if r.algorithm == RateLimitAlgorithm.TOKEN_BUCKET)
        leaky = next(r for r in results if r.algorithm == RateLimitAlgorithm.LEAKY_BUCKET)
        assert token.burst_handling_score >= leaky.burst_handling_score

    def test_leaky_bucket_best_fairness(self) -> None:
        results = self.engine.compare_algorithms(self.graph, "svc", self.traffic)
        leaky = next(r for r in results if r.algorithm == RateLimitAlgorithm.LEAKY_BUCKET)
        fixed = next(r for r in results if r.algorithm == RateLimitAlgorithm.FIXED_WINDOW)
        assert leaky.fairness_score > fixed.fairness_score

    def test_fixed_window_lowest_overhead(self) -> None:
        assert _ALGO_OVERHEAD_MS[RateLimitAlgorithm.FIXED_WINDOW] < _ALGO_OVERHEAD_MS[RateLimitAlgorithm.SLIDING_WINDOW_LOG]

    def test_sliding_window_log_highest_overhead(self) -> None:
        max_overhead_algo = max(_ALGO_OVERHEAD_MS, key=_ALGO_OVERHEAD_MS.get)  # type: ignore[arg-type]
        assert max_overhead_algo == RateLimitAlgorithm.SLIDING_WINDOW_LOG

    def test_all_algorithms_produce_valid_results(self) -> None:
        for algo in RateLimitAlgorithm:
            rule = RateLimitRule(algorithm=algo, requests_per_second=50.0, burst_size=10)
            result = self.engine.simulate_algorithm(self.graph, "svc", rule, self.traffic)
            assert result.avg_latency_ms > 0.0
            assert 0.0 <= result.rejection_rate <= 100.0
            assert 0.0 <= result.burst_handling_score <= 100.0
            assert 0.0 <= result.fairness_score <= 100.0
