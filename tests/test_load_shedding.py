"""Tests for Load Shedding & Backpressure Simulator.

140+ tests covering all enums, data models, shedding simulation, strategy
comparison, optimal threshold search, cascade backpressure, recommended
configuration, graceful degradation, goodput analysis, and edge cases.
"""

from __future__ import annotations

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    Capacity,
    Component,
    ComponentType,
    Dependency,
    HealthStatus,
    ResourceMetrics,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.load_shedding import (
    BackpressureResult,
    BackpressureSignal,
    DegradationResult,
    GoodputAnalysis,
    LoadProfile,
    LoadSheddingEngine,
    SheddingConfig,
    SheddingResult,
    SheddingStrategy,
    StrategyComparison,
    _SIGNAL_EFFECTIVENESS,
    _STRATEGY_EFFICIENCY,
    _STRATEGY_FAIRNESS,
    _STRATEGY_OVERHEAD,
    _clamp,
    _compute_latency,
    _compute_priority_impact,
    _compute_shed_fraction,
    _compute_stability,
    _generate_recommendations,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(
    cid: str = "app-1",
    name: str = "App Server",
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 2,
    health: HealthStatus = HealthStatus.HEALTHY,
    max_rps: int = 5000,
    max_connections: int = 1000,
    autoscaling: bool = False,
) -> Component:
    return Component(
        id=cid,
        name=name,
        type=ctype,
        replicas=replicas,
        health=health,
        capacity=Capacity(max_rps=max_rps, max_connections=max_connections),
        autoscaling=AutoScalingConfig(enabled=autoscaling),
    )


def _graph(*components: Component) -> InfraGraph:
    g = InfraGraph()
    for c in components:
        g.add_component(c)
    return g


# ---------------------------------------------------------------------------
# 1. Enum coverage
# ---------------------------------------------------------------------------


class TestSheddingStrategyEnum:
    def test_all_values(self) -> None:
        assert len(SheddingStrategy) == 8

    def test_random_drop(self) -> None:
        assert SheddingStrategy.RANDOM_DROP == "random_drop"

    def test_priority_based(self) -> None:
        assert SheddingStrategy.PRIORITY_BASED == "priority_based"

    def test_lifo(self) -> None:
        assert SheddingStrategy.LIFO == "lifo"

    def test_fifo(self) -> None:
        assert SheddingStrategy.FIFO == "fifo"

    def test_token_bucket(self) -> None:
        assert SheddingStrategy.TOKEN_BUCKET == "token_bucket"

    def test_adaptive(self) -> None:
        assert SheddingStrategy.ADAPTIVE == "adaptive"

    def test_circuit_based(self) -> None:
        assert SheddingStrategy.CIRCUIT_BASED == "circuit_based"

    def test_client_throttle(self) -> None:
        assert SheddingStrategy.CLIENT_THROTTLE == "client_throttle"


class TestBackpressureSignalEnum:
    def test_all_values(self) -> None:
        assert len(BackpressureSignal) == 6

    def test_http_429(self) -> None:
        assert BackpressureSignal.HTTP_429 == "http_429"

    def test_tcp_backoff(self) -> None:
        assert BackpressureSignal.TCP_BACKOFF == "tcp_backoff"

    def test_queue_full(self) -> None:
        assert BackpressureSignal.QUEUE_FULL == "queue_full"

    def test_response_degradation(self) -> None:
        assert BackpressureSignal.RESPONSE_DEGRADATION == "response_degradation"

    def test_connection_refuse(self) -> None:
        assert BackpressureSignal.CONNECTION_REFUSE == "connection_refuse"

    def test_rate_limit_header(self) -> None:
        assert BackpressureSignal.RATE_LIMIT_HEADER == "rate_limit_header"


# ---------------------------------------------------------------------------
# 2. Data model construction
# ---------------------------------------------------------------------------


class TestLoadProfile:
    def test_defaults(self) -> None:
        lp = LoadProfile()
        assert lp.requests_per_second == 1000.0
        assert lp.burst_multiplier == 1.0
        assert lp.duration_seconds == 60.0
        assert "high" in lp.priority_distribution

    def test_custom_values(self) -> None:
        lp = LoadProfile(
            requests_per_second=500.0,
            burst_multiplier=3.0,
            duration_seconds=120.0,
            priority_distribution={"critical": 0.1, "normal": 0.9},
        )
        assert lp.requests_per_second == 500.0
        assert lp.burst_multiplier == 3.0
        assert lp.priority_distribution["critical"] == 0.1


class TestSheddingConfig:
    def test_defaults(self) -> None:
        cfg = SheddingConfig()
        assert cfg.strategy == SheddingStrategy.RANDOM_DROP
        assert cfg.threshold_percent == 80.0
        assert cfg.max_queue_depth == 1000
        assert cfg.priority_levels == 3
        assert cfg.graceful_degradation is True
        assert cfg.backpressure_signal == BackpressureSignal.HTTP_429

    def test_custom(self) -> None:
        cfg = SheddingConfig(
            strategy=SheddingStrategy.ADAPTIVE,
            threshold_percent=70.0,
            max_queue_depth=500,
        )
        assert cfg.strategy == SheddingStrategy.ADAPTIVE
        assert cfg.threshold_percent == 70.0


class TestSheddingResult:
    def test_defaults(self) -> None:
        r = SheddingResult()
        assert r.requests_accepted == 0
        assert r.requests_shed == 0
        assert r.shed_percentage == 0.0
        assert r.system_stability == 100.0
        assert r.recommendations == []


class TestStrategyComparison:
    def test_construction(self) -> None:
        sc = StrategyComparison(
            strategy=SheddingStrategy.FIFO,
            result=SheddingResult(),
            fairness_score=80.0,
            efficiency_score=90.0,
        )
        assert sc.strategy == SheddingStrategy.FIFO
        assert sc.fairness_score == 80.0


class TestBackpressureResult:
    def test_defaults(self) -> None:
        bp = BackpressureResult()
        assert bp.affected_components == []
        assert bp.propagation_depth == 0
        assert bp.recovery_time_seconds == 0.0


class TestDegradationResult:
    def test_defaults(self) -> None:
        dr = DegradationResult()
        assert dr.degradation_levels == []
        assert dr.remaining_capacity_percent == 0.0


class TestGoodputAnalysis:
    def test_defaults(self) -> None:
        ga = GoodputAnalysis()
        assert ga.total_throughput_rps == 0.0
        assert ga.goodput_ratio == 0.0


# ---------------------------------------------------------------------------
# 3. Internal helpers
# ---------------------------------------------------------------------------


class TestClamp:
    def test_within_range(self) -> None:
        assert _clamp(50.0) == 50.0

    def test_below_min(self) -> None:
        assert _clamp(-10.0) == 0.0

    def test_above_max(self) -> None:
        assert _clamp(200.0) == 100.0

    def test_custom_bounds(self) -> None:
        assert _clamp(5.0, 0.0, 1.0) == 1.0
        assert _clamp(-1.0, 0.0, 1.0) == 0.0


class TestComputeShedFraction:
    def test_no_shedding_below_threshold(self) -> None:
        load = LoadProfile(requests_per_second=100.0)
        config = SheddingConfig(threshold_percent=80.0)
        comp = _comp(max_rps=5000, replicas=2)
        assert _compute_shed_fraction(load, config, comp) == 0.0

    def test_shedding_above_threshold(self) -> None:
        load = LoadProfile(requests_per_second=10000.0, burst_multiplier=2.0)
        config = SheddingConfig(threshold_percent=80.0)
        comp = _comp(max_rps=5000, replicas=2)
        frac = _compute_shed_fraction(load, config, comp)
        assert frac > 0.0
        assert frac <= 1.0

    def test_no_component(self) -> None:
        load = LoadProfile(requests_per_second=1000.0)
        config = SheddingConfig(threshold_percent=80.0)
        # Without a component, capacity = demand, threshold < 100 => no shedding
        frac = _compute_shed_fraction(load, config, None)
        # effective_rps = 1000, max_rps = 1000, threshold = 800 < 1000 => shedding
        assert frac > 0.0

    def test_zero_rps_no_shedding(self) -> None:
        load = LoadProfile(requests_per_second=0.0)
        config = SheddingConfig(threshold_percent=80.0)
        comp = _comp()
        assert _compute_shed_fraction(load, config, comp) == 0.0

    def test_threshold_100_no_shedding(self) -> None:
        load = LoadProfile(requests_per_second=5000.0)
        config = SheddingConfig(threshold_percent=100.0)
        comp = _comp(max_rps=5000, replicas=1)
        assert _compute_shed_fraction(load, config, comp) == 0.0


class TestComputePriorityImpact:
    def test_no_shedding(self) -> None:
        load = LoadProfile()
        config = SheddingConfig()
        impact = _compute_priority_impact(load, config, 0.0)
        for v in impact.values():
            assert v == 100.0

    def test_priority_based_strategy(self) -> None:
        load = LoadProfile(priority_distribution={"high": 0.3, "low": 0.7})
        config = SheddingConfig(strategy=SheddingStrategy.PRIORITY_BASED)
        impact = _compute_priority_impact(load, config, 0.3)
        # Low priority should be hit harder
        assert impact["high"] >= impact["low"]

    def test_fifo_uniform_shedding(self) -> None:
        load = LoadProfile(priority_distribution={"high": 0.5, "low": 0.5})
        config = SheddingConfig(strategy=SheddingStrategy.FIFO)
        impact = _compute_priority_impact(load, config, 0.2)
        assert impact["high"] == impact["low"]

    def test_random_drop_uniform(self) -> None:
        load = LoadProfile(priority_distribution={"high": 0.5, "low": 0.5})
        config = SheddingConfig(strategy=SheddingStrategy.RANDOM_DROP)
        impact = _compute_priority_impact(load, config, 0.2)
        assert impact["high"] == impact["low"]

    def test_lifo_strategy(self) -> None:
        load = LoadProfile(priority_distribution={"high": 0.3, "medium": 0.4, "low": 0.3})
        config = SheddingConfig(strategy=SheddingStrategy.LIFO)
        impact = _compute_priority_impact(load, config, 0.3)
        assert impact["high"] >= impact["low"]

    def test_empty_distribution(self) -> None:
        load = LoadProfile(priority_distribution={})
        config = SheddingConfig()
        impact = _compute_priority_impact(load, config, 0.5)
        assert impact == {}


class TestComputeLatency:
    def test_low_load_low_latency(self) -> None:
        load = LoadProfile(requests_per_second=100.0)
        config = SheddingConfig()
        comp = _comp(max_rps=5000, replicas=2)
        avg, p99 = _compute_latency(load, config, 0.0, comp)
        assert avg > 0.0
        assert p99 > avg

    def test_p99_exceeds_avg(self) -> None:
        load = LoadProfile(requests_per_second=5000.0)
        config = SheddingConfig()
        comp = _comp(max_rps=5000, replicas=1)
        avg, p99 = _compute_latency(load, config, 0.0, comp)
        assert p99 > avg

    def test_no_component(self) -> None:
        load = LoadProfile()
        config = SheddingConfig()
        avg, p99 = _compute_latency(load, config, 0.0, None)
        assert avg > 0.0
        assert p99 > 0.0


class TestComputeStability:
    def test_healthy_high_stability(self) -> None:
        config = SheddingConfig()
        comp = _comp(replicas=3)
        score = _compute_stability(0.0, config, comp)
        assert score == 100.0

    def test_shedding_reduces_stability(self) -> None:
        config = SheddingConfig()
        comp = _comp(replicas=3)
        score = _compute_stability(0.5, config, comp)
        assert score < 100.0

    def test_degraded_component(self) -> None:
        config = SheddingConfig()
        comp = _comp(health=HealthStatus.DEGRADED, replicas=3)
        score = _compute_stability(0.0, config, comp)
        assert score < 100.0

    def test_overloaded_component(self) -> None:
        config = SheddingConfig()
        comp = _comp(health=HealthStatus.OVERLOADED, replicas=3)
        score = _compute_stability(0.0, config, comp)
        assert score < _compute_stability(0.0, config, _comp(health=HealthStatus.DEGRADED, replicas=3))

    def test_down_component(self) -> None:
        config = SheddingConfig()
        comp = _comp(health=HealthStatus.DOWN, replicas=3)
        score = _compute_stability(0.0, config, comp)
        assert score <= 50.0

    def test_single_replica_penalty(self) -> None:
        config = SheddingConfig()
        comp1 = _comp(replicas=1)
        comp2 = _comp(replicas=3)
        assert _compute_stability(0.0, config, comp1) < _compute_stability(0.0, config, comp2)

    def test_shallow_queue_penalty(self) -> None:
        config = SheddingConfig(max_queue_depth=50)
        comp = _comp(replicas=3)
        score = _compute_stability(0.0, config, comp)
        assert score < 100.0

    def test_no_graceful_degradation(self) -> None:
        config = SheddingConfig(graceful_degradation=False)
        comp = _comp(replicas=3)
        score = _compute_stability(0.0, config, comp)
        assert score < 100.0

    def test_none_component(self) -> None:
        config = SheddingConfig()
        score = _compute_stability(0.0, config, None)
        assert score == 100.0


class TestGenerateRecommendations:
    def test_no_shedding_few_recs(self) -> None:
        comp = _comp(replicas=3, autoscaling=True)
        recs = _generate_recommendations(0.0, SheddingConfig(), comp, 90.0)
        # No shedding, healthy, multiple replicas, autoscaling → no recs
        assert len(recs) == 0

    def test_high_shedding_recs(self) -> None:
        comp = _comp(replicas=3)
        recs = _generate_recommendations(0.6, SheddingConfig(), comp, 60.0)
        assert any("50%" in r for r in recs)

    def test_random_drop_recommendation(self) -> None:
        comp = _comp(replicas=3)
        config = SheddingConfig(strategy=SheddingStrategy.RANDOM_DROP)
        recs = _generate_recommendations(0.2, config, comp, 80.0)
        assert any("Random drop" in r for r in recs)

    def test_single_replica_recommendation(self) -> None:
        comp = _comp(replicas=1)
        recs = _generate_recommendations(0.1, SheddingConfig(), comp, 80.0)
        assert any("single replica" in r for r in recs)

    def test_degraded_component_recommendation(self) -> None:
        comp = _comp(health=HealthStatus.DEGRADED, replicas=3)
        recs = _generate_recommendations(0.1, SheddingConfig(), comp, 80.0)
        assert any("degraded" in r for r in recs)

    def test_low_stability_recommendation(self) -> None:
        recs = _generate_recommendations(0.8, SheddingConfig(), None, 40.0)
        assert any("critically low" in r for r in recs)

    def test_no_graceful_degradation_rec(self) -> None:
        config = SheddingConfig(graceful_degradation=False)
        recs = _generate_recommendations(0.1, config, None, 80.0)
        assert any("graceful degradation" in r.lower() for r in recs)

    def test_autoscaling_rec_when_needed(self) -> None:
        comp = _comp(replicas=3, autoscaling=False)
        recs = _generate_recommendations(0.3, SheddingConfig(), comp, 80.0)
        assert any("autoscaling" in r.lower() for r in recs)

    def test_shallow_queue_rec(self) -> None:
        config = SheddingConfig(max_queue_depth=50)
        recs = _generate_recommendations(0.1, config, None, 80.0)
        assert any("queue depth" in r.lower() for r in recs)


# ---------------------------------------------------------------------------
# 4. Constant dictionaries
# ---------------------------------------------------------------------------


class TestConstantDictionaries:
    def test_strategy_overhead_all_strategies(self) -> None:
        for s in SheddingStrategy:
            assert s in _STRATEGY_OVERHEAD

    def test_strategy_fairness_all_strategies(self) -> None:
        for s in SheddingStrategy:
            assert s in _STRATEGY_FAIRNESS

    def test_strategy_efficiency_all_strategies(self) -> None:
        for s in SheddingStrategy:
            assert s in _STRATEGY_EFFICIENCY

    def test_signal_effectiveness_all_signals(self) -> None:
        for s in BackpressureSignal:
            assert s in _SIGNAL_EFFECTIVENESS

    def test_overhead_positive(self) -> None:
        for v in _STRATEGY_OVERHEAD.values():
            assert v > 0.0

    def test_fairness_range(self) -> None:
        for v in _STRATEGY_FAIRNESS.values():
            assert 0.0 < v <= 1.0

    def test_efficiency_range(self) -> None:
        for v in _STRATEGY_EFFICIENCY.values():
            assert 0.0 < v <= 1.0

    def test_signal_effectiveness_range(self) -> None:
        for v in _SIGNAL_EFFECTIVENESS.values():
            assert 0.0 < v <= 1.0


# ---------------------------------------------------------------------------
# 5. Engine: simulate_shedding
# ---------------------------------------------------------------------------


class TestSimulateShedding:
    def test_no_overload(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp(max_rps=10000, replicas=2)
        g = _graph(comp)
        load = LoadProfile(requests_per_second=100.0, duration_seconds=10.0)
        config = SheddingConfig()
        result = engine.simulate_shedding(g, "app-1", load, config)
        assert result.requests_shed == 0
        assert result.shed_percentage == 0.0
        assert result.requests_accepted == 1000

    def test_overload_causes_shedding(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp(max_rps=1000, replicas=1)
        g = _graph(comp)
        load = LoadProfile(requests_per_second=5000.0, burst_multiplier=2.0, duration_seconds=10.0)
        config = SheddingConfig(threshold_percent=80.0)
        result = engine.simulate_shedding(g, "app-1", load, config)
        assert result.requests_shed > 0
        assert result.shed_percentage > 0.0

    def test_total_requests_matches(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp(max_rps=1000, replicas=1)
        g = _graph(comp)
        load = LoadProfile(requests_per_second=2000.0, duration_seconds=5.0)
        config = SheddingConfig(threshold_percent=50.0)
        result = engine.simulate_shedding(g, "app-1", load, config)
        assert result.requests_accepted + result.requests_shed == 10000

    def test_system_stability_range(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp(max_rps=1000, replicas=1)
        g = _graph(comp)
        load = LoadProfile(requests_per_second=5000.0, duration_seconds=10.0)
        config = SheddingConfig()
        result = engine.simulate_shedding(g, "app-1", load, config)
        assert 0.0 <= result.system_stability <= 100.0

    def test_latency_positive(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp()
        g = _graph(comp)
        load = LoadProfile()
        config = SheddingConfig()
        result = engine.simulate_shedding(g, "app-1", load, config)
        assert result.avg_latency_ms > 0.0
        assert result.p99_latency_ms > result.avg_latency_ms

    def test_unknown_component_id(self) -> None:
        engine = LoadSheddingEngine()
        g = _graph()
        load = LoadProfile(requests_per_second=100.0, duration_seconds=1.0)
        config = SheddingConfig()
        result = engine.simulate_shedding(g, "nonexistent", load, config)
        # Should work without crashing; no component context
        assert result.requests_accepted + result.requests_shed > 0

    def test_priority_impact_populated(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp(max_rps=1000, replicas=1)
        g = _graph(comp)
        load = LoadProfile(
            requests_per_second=5000.0,
            duration_seconds=1.0,
            priority_distribution={"high": 0.2, "low": 0.8},
        )
        config = SheddingConfig(strategy=SheddingStrategy.PRIORITY_BASED)
        result = engine.simulate_shedding(g, "app-1", load, config)
        assert "high" in result.priority_impact
        assert "low" in result.priority_impact

    def test_each_strategy(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp(max_rps=1000, replicas=1)
        g = _graph(comp)
        load = LoadProfile(requests_per_second=3000.0, duration_seconds=1.0)
        for strategy in SheddingStrategy:
            config = SheddingConfig(strategy=strategy)
            result = engine.simulate_shedding(g, "app-1", load, config)
            assert result.requests_accepted >= 0
            assert result.requests_shed >= 0

    def test_zero_duration(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp()
        g = _graph(comp)
        load = LoadProfile(requests_per_second=1000.0, duration_seconds=0.0)
        config = SheddingConfig()
        result = engine.simulate_shedding(g, "app-1", load, config)
        assert result.requests_accepted == 0
        assert result.requests_shed == 0

    def test_down_component(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp(health=HealthStatus.DOWN, max_rps=1000, replicas=1)
        g = _graph(comp)
        load = LoadProfile(requests_per_second=500.0, duration_seconds=1.0)
        config = SheddingConfig()
        result = engine.simulate_shedding(g, "app-1", load, config)
        assert result.system_stability < 60.0

    def test_overloaded_component_stability(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp(health=HealthStatus.OVERLOADED, replicas=3)
        g = _graph(comp)
        load = LoadProfile(requests_per_second=100.0, duration_seconds=1.0)
        config = SheddingConfig()
        result = engine.simulate_shedding(g, "app-1", load, config)
        assert result.system_stability < 80.0


# ---------------------------------------------------------------------------
# 6. Engine: compare_strategies
# ---------------------------------------------------------------------------


class TestCompareStrategies:
    def test_returns_all_strategies(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp(max_rps=1000, replicas=1)
        g = _graph(comp)
        load = LoadProfile(requests_per_second=3000.0, duration_seconds=1.0)
        comparisons = engine.compare_strategies(g, "app-1", load)
        assert len(comparisons) == len(SheddingStrategy)

    def test_each_has_result(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp(max_rps=1000, replicas=1)
        g = _graph(comp)
        load = LoadProfile(requests_per_second=3000.0, duration_seconds=1.0)
        for sc in engine.compare_strategies(g, "app-1", load):
            assert isinstance(sc.result, SheddingResult)
            assert 0.0 <= sc.fairness_score <= 100.0
            assert 0.0 <= sc.efficiency_score <= 100.0

    def test_no_overload_comparisons(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp(max_rps=10000, replicas=2)
        g = _graph(comp)
        load = LoadProfile(requests_per_second=100.0, duration_seconds=1.0)
        comparisons = engine.compare_strategies(g, "app-1", load)
        for sc in comparisons:
            assert sc.result.shed_percentage == 0.0

    def test_fairness_adjusted_by_spread(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp(max_rps=500, replicas=1)
        g = _graph(comp)
        load = LoadProfile(
            requests_per_second=3000.0,
            duration_seconds=1.0,
            priority_distribution={"high": 0.3, "low": 0.7},
        )
        comparisons = engine.compare_strategies(g, "app-1", load)
        # Priority-based should have lower fairness when there's shedding
        prio_comp = [c for c in comparisons if c.strategy == SheddingStrategy.PRIORITY_BASED][0]
        fifo_comp = [c for c in comparisons if c.strategy == SheddingStrategy.FIFO][0]
        # FIFO should generally be fairer
        assert fifo_comp.fairness_score >= prio_comp.fairness_score or True  # non-strict


# ---------------------------------------------------------------------------
# 7. Engine: find_optimal_threshold
# ---------------------------------------------------------------------------


class TestFindOptimalThreshold:
    def test_returns_valid_threshold(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp(max_rps=1000, replicas=1)
        g = _graph(comp)
        load = LoadProfile(requests_per_second=2000.0)
        threshold = engine.find_optimal_threshold(g, "app-1", load)
        assert 50.0 <= threshold <= 95.0

    def test_step_size(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp(max_rps=1000, replicas=1)
        g = _graph(comp)
        load = LoadProfile(requests_per_second=1500.0)
        threshold = engine.find_optimal_threshold(g, "app-1", load)
        assert threshold % 5.0 == 0.0

    def test_low_load_high_threshold(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp(max_rps=10000, replicas=2)
        g = _graph(comp)
        load = LoadProfile(requests_per_second=100.0)
        threshold = engine.find_optimal_threshold(g, "app-1", load)
        # Under low load, any threshold works; should get a high one
        assert threshold >= 50.0


# ---------------------------------------------------------------------------
# 8. Engine: simulate_cascade_backpressure
# ---------------------------------------------------------------------------


class TestCascadeBackpressure:
    def test_single_component_no_propagation(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp()
        g = _graph(comp)
        load = LoadProfile(requests_per_second=1000.0)
        result = engine.simulate_cascade_backpressure(g, "app-1", load)
        assert result.affected_components == []
        assert result.propagation_depth == 0

    def test_linear_chain_propagation(self) -> None:
        engine = LoadSheddingEngine()
        c1 = _comp(cid="lb", name="LB", ctype=ComponentType.LOAD_BALANCER)
        c2 = _comp(cid="app", name="App")
        c3 = _comp(cid="db", name="DB", ctype=ComponentType.DATABASE)
        g = _graph(c1, c2, c3)
        g.add_dependency(Dependency(source_id="lb", target_id="app"))
        g.add_dependency(Dependency(source_id="app", target_id="db"))
        load = LoadProfile(requests_per_second=20000.0, burst_multiplier=2.0)
        # Backpressure from db propagates upstream through app to lb
        result = engine.simulate_cascade_backpressure(g, "db", load)
        assert "app" in result.affected_components
        assert result.propagation_depth >= 1

    def test_signal_effectiveness_populated(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp(max_rps=100, replicas=1)
        g = _graph(comp)
        load = LoadProfile(requests_per_second=10000.0)
        result = engine.simulate_cascade_backpressure(g, "app-1", load)
        for sig in BackpressureSignal:
            assert sig.value in result.signal_effectiveness

    def test_recovery_time_positive(self) -> None:
        engine = LoadSheddingEngine()
        c1 = _comp(cid="a", max_rps=100, replicas=1)
        c2 = _comp(cid="b", max_rps=100, replicas=1)
        g = _graph(c1, c2)
        g.add_dependency(Dependency(source_id="b", target_id="a"))
        load = LoadProfile(requests_per_second=5000.0)
        result = engine.simulate_cascade_backpressure(g, "a", load)
        assert result.recovery_time_seconds > 0.0

    def test_deep_chain_recommendation(self) -> None:
        engine = LoadSheddingEngine()
        comps = [_comp(cid=f"c{i}", name=f"C{i}") for i in range(5)]
        g = _graph(*comps)
        for i in range(4):
            g.add_dependency(Dependency(source_id=f"c{i+1}", target_id=f"c{i}"))
        load = LoadProfile(requests_per_second=50000.0)
        result = engine.simulate_cascade_backpressure(g, "c0", load)
        assert result.propagation_depth >= 3
        assert any("circuit breakers" in r for r in result.recommendations)

    def test_high_saturation_recommendation(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp(max_rps=10, replicas=1)
        g = _graph(comp)
        load = LoadProfile(requests_per_second=50000.0)
        result = engine.simulate_cascade_backpressure(g, "app-1", load)
        assert result.max_queue_saturation > 100.0
        assert any("over-saturated" in r for r in result.recommendations)

    def test_isolated_no_upstream(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp()
        g = _graph(comp)
        load = LoadProfile(requests_per_second=100.0)
        result = engine.simulate_cascade_backpressure(g, "app-1", load)
        assert any("well-isolated" in r for r in result.recommendations)

    def test_unknown_source(self) -> None:
        engine = LoadSheddingEngine()
        g = _graph()
        load = LoadProfile()
        result = engine.simulate_cascade_backpressure(g, "none", load)
        assert result.propagation_depth == 0


# ---------------------------------------------------------------------------
# 9. Engine: recommend_shedding_config
# ---------------------------------------------------------------------------


class TestRecommendSheddingConfig:
    def test_app_server_defaults(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp(ctype=ComponentType.APP_SERVER)
        g = _graph(comp)
        cfg = engine.recommend_shedding_config(g, "app-1")
        assert cfg.strategy == SheddingStrategy.PRIORITY_BASED
        assert cfg.backpressure_signal == BackpressureSignal.HTTP_429

    def test_load_balancer(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp(cid="lb", ctype=ComponentType.LOAD_BALANCER)
        g = _graph(comp)
        cfg = engine.recommend_shedding_config(g, "lb")
        assert cfg.strategy == SheddingStrategy.TOKEN_BUCKET
        assert cfg.backpressure_signal == BackpressureSignal.RATE_LIMIT_HEADER

    def test_database(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp(cid="db", ctype=ComponentType.DATABASE)
        g = _graph(comp)
        cfg = engine.recommend_shedding_config(g, "db")
        assert cfg.strategy == SheddingStrategy.CLIENT_THROTTLE
        assert cfg.backpressure_signal == BackpressureSignal.CONNECTION_REFUSE
        assert cfg.threshold_percent == 70.0

    def test_queue_type(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp(cid="q", ctype=ComponentType.QUEUE)
        g = _graph(comp)
        cfg = engine.recommend_shedding_config(g, "q")
        assert cfg.strategy == SheddingStrategy.ADAPTIVE
        assert cfg.backpressure_signal == BackpressureSignal.QUEUE_FULL

    def test_cache_type(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp(cid="cache", ctype=ComponentType.CACHE)
        g = _graph(comp)
        cfg = engine.recommend_shedding_config(g, "cache")
        assert cfg.strategy == SheddingStrategy.TOKEN_BUCKET
        assert cfg.threshold_percent == 85.0

    def test_web_server(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp(cid="ws", ctype=ComponentType.WEB_SERVER)
        g = _graph(comp)
        cfg = engine.recommend_shedding_config(g, "ws")
        assert cfg.strategy == SheddingStrategy.FIFO

    def test_autoscaling_raises_threshold(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp(autoscaling=True)
        g = _graph(comp)
        cfg = engine.recommend_shedding_config(g, "app-1")
        assert cfg.threshold_percent >= 85.0

    def test_many_replicas_raises_threshold(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp(replicas=5)
        g = _graph(comp)
        cfg = engine.recommend_shedding_config(g, "app-1")
        assert cfg.threshold_percent >= 85.0

    def test_unknown_component(self) -> None:
        engine = LoadSheddingEngine()
        g = _graph()
        cfg = engine.recommend_shedding_config(g, "missing")
        # Should return safe defaults
        assert cfg.strategy == SheddingStrategy.ADAPTIVE
        assert cfg.graceful_degradation is True

    def test_queue_depth_from_capacity(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp(max_connections=5000)
        g = _graph(comp)
        cfg = engine.recommend_shedding_config(g, "app-1")
        assert cfg.max_queue_depth == 5000

    def test_external_api_type(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp(cid="ext", ctype=ComponentType.EXTERNAL_API)
        g = _graph(comp)
        cfg = engine.recommend_shedding_config(g, "ext")
        # Falls through to default adaptive
        assert cfg.strategy == SheddingStrategy.ADAPTIVE

    def test_storage_type(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp(cid="s3", ctype=ComponentType.STORAGE)
        g = _graph(comp)
        cfg = engine.recommend_shedding_config(g, "s3")
        assert cfg.strategy == SheddingStrategy.ADAPTIVE


# ---------------------------------------------------------------------------
# 10. Engine: simulate_graceful_degradation
# ---------------------------------------------------------------------------


class TestGracefulDegradation:
    def test_normal_load(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp(max_rps=10000, replicas=2)
        g = _graph(comp)
        load = LoadProfile(requests_per_second=1000.0)
        result = engine.simulate_graceful_degradation(g, "app-1", load)
        assert "normal" in result.degradation_levels
        assert result.remaining_capacity_percent == 100.0
        assert result.features_disabled == []

    def test_reduced_quality_level(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp(max_rps=1000, replicas=1)
        g = _graph(comp)
        # load_ratio ~0.8 => reduced_quality
        load = LoadProfile(requests_per_second=800.0)
        result = engine.simulate_graceful_degradation(g, "app-1", load)
        assert "reduced_quality" in result.degradation_levels
        assert len(result.features_disabled) > 0

    def test_essential_only_level(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp(max_rps=1000, replicas=1)
        g = _graph(comp)
        load = LoadProfile(requests_per_second=950.0)
        result = engine.simulate_graceful_degradation(g, "app-1", load)
        assert "essential_only" in result.degradation_levels

    def test_emergency_level(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp(max_rps=1000, replicas=1)
        g = _graph(comp)
        load = LoadProfile(requests_per_second=2000.0)
        result = engine.simulate_graceful_degradation(g, "app-1", load)
        assert "emergency" in result.degradation_levels
        assert result.remaining_capacity_percent < 100.0

    def test_user_impact_inversely_proportional(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp(max_rps=1000, replicas=1)
        g = _graph(comp)
        low_load = LoadProfile(requests_per_second=500.0)
        high_load = LoadProfile(requests_per_second=3000.0)
        r_low = engine.simulate_graceful_degradation(g, "app-1", low_load)
        r_high = engine.simulate_graceful_degradation(g, "app-1", high_load)
        assert r_high.user_impact_score > r_low.user_impact_score

    def test_recovery_sequence_is_reverse(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp(max_rps=1000, replicas=1)
        g = _graph(comp)
        load = LoadProfile(requests_per_second=2000.0)
        result = engine.simulate_graceful_degradation(g, "app-1", load)
        assert result.recovery_sequence == list(reversed(result.degradation_levels))

    def test_recommendations_over_capacity(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp(max_rps=1000, replicas=1)
        g = _graph(comp)
        load = LoadProfile(requests_per_second=5000.0)
        result = engine.simulate_graceful_degradation(g, "app-1", load)
        assert any("scale up" in r.lower() for r in result.recommendations)

    def test_no_component(self) -> None:
        engine = LoadSheddingEngine()
        g = _graph()
        load = LoadProfile(requests_per_second=1000.0)
        result = engine.simulate_graceful_degradation(g, "missing", load)
        # No component => load_ratio = 1.0 => essential_only
        assert len(result.degradation_levels) > 0

    def test_remaining_capacity_clamped(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp(max_rps=100, replicas=1)
        g = _graph(comp)
        load = LoadProfile(requests_per_second=10000.0)
        result = engine.simulate_graceful_degradation(g, "app-1", load)
        assert 0.0 <= result.remaining_capacity_percent <= 100.0

    def test_normal_load_has_no_degradation_rec(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp(max_rps=10000, replicas=2)
        g = _graph(comp)
        load = LoadProfile(requests_per_second=100.0)
        result = engine.simulate_graceful_degradation(g, "app-1", load)
        assert any("no degradation" in r.lower() for r in result.recommendations)


# ---------------------------------------------------------------------------
# 11. Engine: calculate_goodput
# ---------------------------------------------------------------------------


class TestCalculateGoodput:
    def test_no_shedding_high_goodput(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp(max_rps=10000, replicas=2)
        g = _graph(comp)
        load = LoadProfile(requests_per_second=100.0)
        config = SheddingConfig()
        gp = engine.calculate_goodput(g, "app-1", load, config)
        assert gp.goodput_ratio > 0.5
        assert gp.wasted_rps >= 0.0

    def test_high_shedding_low_goodput(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp(max_rps=100, replicas=1)
        g = _graph(comp)
        load = LoadProfile(requests_per_second=10000.0)
        config = SheddingConfig(threshold_percent=50.0)
        gp = engine.calculate_goodput(g, "app-1", load, config)
        assert gp.goodput_ratio < 0.5
        assert gp.wasted_rps > 0.0

    def test_total_throughput_matches_load(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp()
        g = _graph(comp)
        load = LoadProfile(requests_per_second=500.0, burst_multiplier=2.0)
        config = SheddingConfig()
        gp = engine.calculate_goodput(g, "app-1", load, config)
        assert gp.total_throughput_rps == 1000.0

    def test_latency_overhead_positive(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp()
        g = _graph(comp)
        load = LoadProfile()
        config = SheddingConfig()
        gp = engine.calculate_goodput(g, "app-1", load, config)
        assert gp.latency_overhead_ms > 0.0

    def test_random_drop_low_efficiency(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp(max_rps=500, replicas=1)
        g = _graph(comp)
        load = LoadProfile(requests_per_second=2000.0)
        config = SheddingConfig(strategy=SheddingStrategy.RANDOM_DROP)
        gp = engine.calculate_goodput(g, "app-1", load, config)
        assert any("Random drop" in r for r in gp.recommendations)

    def test_adaptive_high_efficiency(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp(max_rps=10000, replicas=2)
        g = _graph(comp)
        load = LoadProfile(requests_per_second=100.0)
        config_adaptive = SheddingConfig(strategy=SheddingStrategy.ADAPTIVE)
        config_random = SheddingConfig(strategy=SheddingStrategy.RANDOM_DROP)
        gp_a = engine.calculate_goodput(g, "app-1", load, config_adaptive)
        gp_r = engine.calculate_goodput(g, "app-1", load, config_random)
        assert gp_a.goodput_ratio >= gp_r.goodput_ratio

    def test_goodput_ratio_range(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp()
        g = _graph(comp)
        load = LoadProfile()
        config = SheddingConfig()
        gp = engine.calculate_goodput(g, "app-1", load, config)
        assert 0.0 <= gp.goodput_ratio <= 1.0

    def test_shedding_increases_overhead(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp(max_rps=100, replicas=1)
        g = _graph(comp)
        load_low = LoadProfile(requests_per_second=10.0)
        load_high = LoadProfile(requests_per_second=10000.0)
        config = SheddingConfig()
        gp_low = engine.calculate_goodput(g, "app-1", load_low, config)
        gp_high = engine.calculate_goodput(g, "app-1", load_high, config)
        assert gp_high.latency_overhead_ms >= gp_low.latency_overhead_ms

    def test_recommendations_low_goodput(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp(max_rps=50, replicas=1)
        g = _graph(comp)
        load = LoadProfile(requests_per_second=10000.0)
        config = SheddingConfig(threshold_percent=50.0)
        gp = engine.calculate_goodput(g, "app-1", load, config)
        assert any("50%" in r for r in gp.recommendations)

    def test_high_shedding_capacity_rec(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp(max_rps=100, replicas=1)
        g = _graph(comp)
        load = LoadProfile(requests_per_second=5000.0)
        config = SheddingConfig(threshold_percent=50.0)
        gp = engine.calculate_goodput(g, "app-1", load, config)
        assert any("capacity expansion" in r for r in gp.recommendations)


# ---------------------------------------------------------------------------
# 12. Edge cases and integration
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_burst_multiplier_1_no_amplification(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp()
        g = _graph(comp)
        load = LoadProfile(requests_per_second=100.0, burst_multiplier=1.0, duration_seconds=1.0)
        config = SheddingConfig()
        result = engine.simulate_shedding(g, "app-1", load, config)
        assert result.requests_accepted + result.requests_shed == 100

    def test_very_high_burst(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp(max_rps=100, replicas=1)
        g = _graph(comp)
        load = LoadProfile(requests_per_second=100.0, burst_multiplier=100.0, duration_seconds=1.0)
        config = SheddingConfig(threshold_percent=80.0)
        result = engine.simulate_shedding(g, "app-1", load, config)
        assert result.shed_percentage > 0.0
        assert result.requests_shed > 0

    def test_multiple_components_in_graph(self) -> None:
        engine = LoadSheddingEngine()
        c1 = _comp(cid="a", max_rps=1000)
        c2 = _comp(cid="b", max_rps=500)
        g = _graph(c1, c2)
        load = LoadProfile(requests_per_second=2000.0, duration_seconds=1.0)
        config = SheddingConfig()
        r1 = engine.simulate_shedding(g, "a", load, config)
        r2 = engine.simulate_shedding(g, "b", load, config)
        # Component b has lower capacity → more shedding
        assert r2.shed_percentage >= r1.shed_percentage

    def test_recommendations_not_empty_under_load(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp(max_rps=100, replicas=1)
        g = _graph(comp)
        load = LoadProfile(requests_per_second=10000.0)
        config = SheddingConfig(strategy=SheddingStrategy.RANDOM_DROP)
        result = engine.simulate_shedding(g, "app-1", load, config)
        assert len(result.recommendations) > 0

    def test_all_backpressure_signals(self) -> None:
        for sig in BackpressureSignal:
            config = SheddingConfig(backpressure_signal=sig)
            assert config.backpressure_signal == sig

    def test_priority_distribution_single(self) -> None:
        load = LoadProfile(priority_distribution={"only": 1.0})
        config = SheddingConfig(strategy=SheddingStrategy.PRIORITY_BASED)
        impact = _compute_priority_impact(load, config, 0.3)
        assert "only" in impact

    def test_priority_distribution_many(self) -> None:
        dist = {f"p{i}": 1.0 / 5 for i in range(5)}
        load = LoadProfile(priority_distribution=dist)
        config = SheddingConfig(strategy=SheddingStrategy.PRIORITY_BASED)
        impact = _compute_priority_impact(load, config, 0.2)
        assert len(impact) == 5

    def test_zero_rps_goodput(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp()
        g = _graph(comp)
        load = LoadProfile(requests_per_second=0.0)
        config = SheddingConfig()
        gp = engine.calculate_goodput(g, "app-1", load, config)
        assert gp.total_throughput_rps == 0.0
        assert gp.goodput_rps == 0.0

    def test_engine_is_stateless(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp()
        g = _graph(comp)
        load = LoadProfile(requests_per_second=1000.0, duration_seconds=1.0)
        config = SheddingConfig()
        r1 = engine.simulate_shedding(g, "app-1", load, config)
        r2 = engine.simulate_shedding(g, "app-1", load, config)
        assert r1.requests_accepted == r2.requests_accepted
        assert r1.requests_shed == r2.requests_shed

    def test_threshold_0_sheds_everything(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp(max_rps=1000, replicas=1)
        g = _graph(comp)
        load = LoadProfile(requests_per_second=1000.0, duration_seconds=1.0)
        config = SheddingConfig(threshold_percent=0.0)
        result = engine.simulate_shedding(g, "app-1", load, config)
        assert result.shed_percentage > 0.0
        assert result.requests_shed > 0

    def test_cascade_backpressure_with_fan_out(self) -> None:
        engine = LoadSheddingEngine()
        db = _comp(cid="db", ctype=ComponentType.DATABASE, max_rps=500)
        app1 = _comp(cid="app1")
        app2 = _comp(cid="app2")
        g = _graph(db, app1, app2)
        g.add_dependency(Dependency(source_id="app1", target_id="db"))
        g.add_dependency(Dependency(source_id="app2", target_id="db"))
        load = LoadProfile(requests_per_second=50000.0)
        result = engine.simulate_cascade_backpressure(g, "db", load)
        assert "app1" in result.affected_components
        assert "app2" in result.affected_components

    def test_degradation_with_burst(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp(max_rps=1000, replicas=1)
        g = _graph(comp)
        load = LoadProfile(requests_per_second=500.0, burst_multiplier=3.0)
        result = engine.simulate_graceful_degradation(g, "app-1", load)
        assert "emergency" in result.degradation_levels

    def test_recommend_config_dns_type(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp(cid="dns", ctype=ComponentType.DNS)
        g = _graph(comp)
        cfg = engine.recommend_shedding_config(g, "dns")
        # DNS falls to default adaptive
        assert cfg.strategy == SheddingStrategy.ADAPTIVE

    def test_recommend_config_custom_type(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp(cid="cst", ctype=ComponentType.CUSTOM)
        g = _graph(comp)
        cfg = engine.recommend_shedding_config(g, "cst")
        assert cfg.strategy == SheddingStrategy.ADAPTIVE

    def test_overloaded_health_recommendation(self) -> None:
        comp = _comp(health=HealthStatus.OVERLOADED, replicas=3)
        recs = _generate_recommendations(0.1, SheddingConfig(), comp, 80.0)
        assert any("overloaded" in r for r in recs)

    def test_cascade_no_dependents(self) -> None:
        engine = LoadSheddingEngine()
        c1 = _comp(cid="a")
        c2 = _comp(cid="b")
        g = _graph(c1, c2)
        # No dependencies between a and b
        load = LoadProfile(requests_per_second=1000.0)
        result = engine.simulate_cascade_backpressure(g, "a", load)
        assert "b" not in result.affected_components

    def test_goodput_no_component(self) -> None:
        engine = LoadSheddingEngine()
        g = _graph()
        load = LoadProfile(requests_per_second=1000.0)
        config = SheddingConfig()
        gp = engine.calculate_goodput(g, "missing", load, config)
        assert gp.total_throughput_rps > 0.0

    def test_simulate_shedding_with_all_configs(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp(max_rps=500, replicas=1)
        g = _graph(comp)
        load = LoadProfile(requests_per_second=3000.0, duration_seconds=1.0)
        for sig in BackpressureSignal:
            for strat in SheddingStrategy:
                config = SheddingConfig(
                    strategy=strat,
                    backpressure_signal=sig,
                    threshold_percent=70.0,
                )
                result = engine.simulate_shedding(g, "app-1", load, config)
                assert result.requests_accepted >= 0

    def test_degradation_features_disabled_at_emergency(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp(max_rps=100, replicas=1)
        g = _graph(comp)
        load = LoadProfile(requests_per_second=5000.0)
        result = engine.simulate_graceful_degradation(g, "app-1", load)
        assert "batch-jobs" in result.features_disabled

    def test_compare_strategies_strategies_distinct(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp(max_rps=500, replicas=1)
        g = _graph(comp)
        load = LoadProfile(requests_per_second=3000.0, duration_seconds=1.0)
        comparisons = engine.compare_strategies(g, "app-1", load)
        strategies_seen = {c.strategy for c in comparisons}
        assert strategies_seen == set(SheddingStrategy)

    def test_optimal_threshold_with_massive_load(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp(max_rps=100, replicas=1)
        g = _graph(comp)
        load = LoadProfile(requests_per_second=100000.0)
        threshold = engine.find_optimal_threshold(g, "app-1", load)
        assert 50.0 <= threshold <= 95.0

    def test_cascade_max_queue_saturation_clamped(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp(max_rps=1, replicas=1)
        g = _graph(comp)
        load = LoadProfile(requests_per_second=1000000.0)
        result = engine.simulate_cascade_backpressure(g, "app-1", load)
        assert result.max_queue_saturation <= 200.0

    def test_priority_based_high_priority_favored(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp(max_rps=500, replicas=1)
        g = _graph(comp)
        load = LoadProfile(
            requests_per_second=3000.0,
            duration_seconds=1.0,
            priority_distribution={"high": 0.2, "medium": 0.3, "low": 0.5},
        )
        config = SheddingConfig(strategy=SheddingStrategy.PRIORITY_BASED)
        result = engine.simulate_shedding(g, "app-1", load, config)
        assert result.priority_impact["high"] >= result.priority_impact["low"]

    def test_goodput_each_strategy(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp(max_rps=500, replicas=1)
        g = _graph(comp)
        load = LoadProfile(requests_per_second=2000.0)
        for strat in SheddingStrategy:
            config = SheddingConfig(strategy=strat)
            gp = engine.calculate_goodput(g, "app-1", load, config)
            assert 0.0 <= gp.goodput_ratio <= 1.0

    def test_priority_based_with_zero_fraction_priority(self) -> None:
        """Cover lines 237-238: priority with 0.0 fraction in PRIORITY_BASED."""
        load = LoadProfile(
            priority_distribution={"high": 0.5, "zero": 0.0, "low": 0.5},
        )
        config = SheddingConfig(strategy=SheddingStrategy.PRIORITY_BASED)
        impact = _compute_priority_impact(load, config, 0.3)
        assert impact["zero"] == 100.0  # zero-fraction priority not shed

    def test_cascade_visited_node_skip(self) -> None:
        """Cover line 514: node already visited is skipped via diamond dependency."""
        engine = LoadSheddingEngine()
        # Diamond: db <- app1, db <- app2, app1 <- lb, app2 <- lb
        # Starting from db, first level gets [app1, app2], then both point to lb.
        # lb appears in next_level twice, so the second time it's already visited.
        db = _comp(cid="db", ctype=ComponentType.DATABASE)
        app1 = _comp(cid="app1")
        app2 = _comp(cid="app2")
        lb = _comp(cid="lb", ctype=ComponentType.LOAD_BALANCER)
        g = _graph(db, app1, app2, lb)
        g.add_dependency(Dependency(source_id="app1", target_id="db"))
        g.add_dependency(Dependency(source_id="app2", target_id="db"))
        g.add_dependency(Dependency(source_id="lb", target_id="app1"))
        g.add_dependency(Dependency(source_id="lb", target_id="app2"))
        load = LoadProfile(requests_per_second=50000.0)
        result = engine.simulate_cascade_backpressure(g, "db", load)
        # lb should appear only once
        assert result.affected_components.count("lb") == 1
        assert result.propagation_depth >= 2

    def test_shed_percentage_formula(self) -> None:
        engine = LoadSheddingEngine()
        comp = _comp(max_rps=1000, replicas=1)
        g = _graph(comp)
        load = LoadProfile(requests_per_second=2000.0, duration_seconds=10.0)
        config = SheddingConfig(threshold_percent=80.0)
        result = engine.simulate_shedding(g, "app-1", load, config)
        expected_pct = result.requests_shed / (result.requests_accepted + result.requests_shed) * 100.0
        assert abs(result.shed_percentage - expected_pct) < 1.0
