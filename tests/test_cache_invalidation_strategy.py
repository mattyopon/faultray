"""Tests for Cache Invalidation Strategy Analyzer.

Comprehensive test suite covering all enums, data models, utility functions,
stampede analysis, consistency windows, hit-rate modelling, coherence protocol
transitions, cache poisoning risk assessment, eviction policy analysis,
invalidation scope cost estimation, cache warming, graph-aware resilience
assessment, and full analysis integration.
"""

from __future__ import annotations

import pytest

from faultray.model.components import Component, ComponentType, Dependency, HealthStatus
from faultray.model.graph import InfraGraph
from faultray.simulator.cache_invalidation_strategy import (
    CacheInvalidationEngine,
    CacheInvalidationReport,
    CacheLayerConfig,
    CacheLevel,
    CachePoisoningRisk,
    CoherenceState,
    CoherenceTransition,
    ConsistencyWindow,
    EvictionAnalysis,
    EvictionPolicy,
    HitRateModel,
    InvalidationConfig,
    InvalidationScope,
    InvalidationStrategy,
    StampedeAnalysis,
    StampedeRisk,
    _DEFAULT_TTL_SECONDS,
    _MAX_SCORE,
    _STAMPEDE_CONCURRENCY_THRESHOLD,
    _clamp,
    _compute_warm_up_seconds,
    _effective_multilayer_hit_rate,
    _eviction_pressure,
    _stampede_risk_level,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(cid="c1", ctype=ComponentType.APP_SERVER):
    return Component(id=cid, name=cid, type=ctype)


def _graph(*comps):
    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    return g


def _engine() -> CacheInvalidationEngine:
    return CacheInvalidationEngine()


def _l1(**overrides) -> CacheLayerConfig:
    defaults = dict(
        level=CacheLevel.L1_LOCAL,
        capacity_mb=64.0,
        ttl_seconds=60,
        eviction_policy=EvictionPolicy.LRU,
        hit_rate=0.95,
        latency_ms=0.5,
    )
    defaults.update(overrides)
    return CacheLayerConfig(**defaults)


def _l2(**overrides) -> CacheLayerConfig:
    defaults = dict(
        level=CacheLevel.L2_SHARED,
        capacity_mb=512.0,
        ttl_seconds=300,
        eviction_policy=EvictionPolicy.LRU,
        hit_rate=0.85,
        latency_ms=2.0,
    )
    defaults.update(overrides)
    return CacheLayerConfig(**defaults)


def _cdn(**overrides) -> CacheLayerConfig:
    defaults = dict(
        level=CacheLevel.CDN,
        capacity_mb=2048.0,
        ttl_seconds=3600,
        eviction_policy=EvictionPolicy.LFU,
        hit_rate=0.92,
        latency_ms=5.0,
    )
    defaults.update(overrides)
    return CacheLayerConfig(**defaults)


def _default_config(**overrides) -> InvalidationConfig:
    defaults = dict(
        strategy=InvalidationStrategy.TTL_BASED,
        scope=InvalidationScope.SINGLE_KEY,
        layers=[_l1(), _l2()],
        event_propagation_delay_ms=10.0,
        concurrent_readers=100,
        origin_latency_ms=50.0,
    )
    defaults.update(overrides)
    return InvalidationConfig(**defaults)


# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------


class TestEnums:
    """Test all enum values are accessible."""

    def test_invalidation_strategy_values(self):
        assert InvalidationStrategy.TTL_BASED == "ttl_based"
        assert InvalidationStrategy.EVENT_DRIVEN == "event_driven"
        assert InvalidationStrategy.WRITE_THROUGH == "write_through"
        assert InvalidationStrategy.WRITE_BEHIND == "write_behind"
        assert InvalidationStrategy.WRITE_AROUND == "write_around"
        assert len(InvalidationStrategy) == 5

    def test_eviction_policy_values(self):
        assert EvictionPolicy.LRU == "lru"
        assert EvictionPolicy.LFU == "lfu"
        assert EvictionPolicy.ARC == "arc"
        assert EvictionPolicy.FIFO == "fifo"
        assert EvictionPolicy.RANDOM == "random"
        assert EvictionPolicy.TTL == "ttl"
        assert len(EvictionPolicy) == 6

    def test_coherence_state_values(self):
        assert CoherenceState.MODIFIED == "modified"
        assert CoherenceState.EXCLUSIVE == "exclusive"
        assert CoherenceState.SHARED == "shared"
        assert CoherenceState.INVALID == "invalid"
        assert len(CoherenceState) == 4

    def test_cache_level_values(self):
        assert CacheLevel.L1_LOCAL == "l1_local"
        assert CacheLevel.L2_SHARED == "l2_shared"
        assert CacheLevel.CDN == "cdn"
        assert CacheLevel.ORIGIN == "origin"
        assert len(CacheLevel) == 4

    def test_invalidation_scope_values(self):
        assert InvalidationScope.SINGLE_KEY == "single_key"
        assert InvalidationScope.TAG_BASED == "tag_based"
        assert InvalidationScope.PATTERN_BASED == "pattern_based"
        assert InvalidationScope.FULL_FLUSH == "full_flush"
        assert len(InvalidationScope) == 4

    def test_stampede_risk_values(self):
        assert StampedeRisk.NONE == "none"
        assert StampedeRisk.LOW == "low"
        assert StampedeRisk.MEDIUM == "medium"
        assert StampedeRisk.HIGH == "high"
        assert StampedeRisk.CRITICAL == "critical"
        assert len(StampedeRisk) == 5


# ---------------------------------------------------------------------------
# Data model tests
# ---------------------------------------------------------------------------


class TestDataModels:
    """Test data model construction and defaults."""

    def test_cache_layer_config_defaults(self):
        layer = CacheLayerConfig(level=CacheLevel.L1_LOCAL)
        assert layer.capacity_mb == 256.0
        assert layer.ttl_seconds == _DEFAULT_TTL_SECONDS
        assert layer.eviction_policy == EvictionPolicy.LRU
        assert layer.hit_rate == 0.9
        assert layer.latency_ms == 1.0
        assert layer.replicas == 1
        assert layer.stale_while_revalidate is False
        assert layer.stale_ttl_seconds == 0

    def test_invalidation_config_defaults(self):
        cfg = InvalidationConfig()
        assert cfg.strategy == InvalidationStrategy.TTL_BASED
        assert cfg.scope == InvalidationScope.SINGLE_KEY
        assert cfg.layers == []
        assert cfg.event_propagation_delay_ms == 10.0
        assert cfg.concurrent_readers == 100

    def test_stampede_analysis_defaults(self):
        sa = StampedeAnalysis()
        assert sa.risk_level == StampedeRisk.NONE
        assert sa.estimated_concurrent_misses == 0
        assert sa.origin_load_multiplier == 1.0
        assert sa.mitigations == []

    def test_consistency_window_defaults(self):
        cw = ConsistencyWindow()
        assert cw.layer_pair == ("", "")
        assert cw.max_staleness_ms == 0.0
        assert cw.stale_reads_percent == 0.0

    def test_hit_rate_model_defaults(self):
        hr = HitRateModel()
        assert hr.effective_hit_rate == 0.0
        assert hr.cold_start_hit_rate == 0.0
        assert hr.steady_state_hit_rate == 0.0
        assert hr.warm_up_time_seconds == 0.0
        assert hr.eviction_pressure == 0.0
        assert hr.recommendations == []

    def test_cache_poisoning_risk_defaults(self):
        pr = CachePoisoningRisk()
        assert pr.risk_score == 0.0
        assert pr.vulnerable_layers == []
        assert pr.attack_vectors == []
        assert pr.mitigations == []

    def test_eviction_analysis_defaults(self):
        ea = EvictionAnalysis(policy=EvictionPolicy.LRU)
        assert ea.estimated_eviction_rate == 0.0
        assert ea.fairness_score == 0.0
        assert ea.recommendations == []

    def test_coherence_transition_has_timestamp(self):
        ct = CoherenceTransition(
            node_id="n1",
            from_state=CoherenceState.SHARED,
            to_state=CoherenceState.MODIFIED,
        )
        assert ct.timestamp is not None
        assert ct.trigger == ""

    def test_cache_invalidation_report_defaults(self):
        rpt = CacheInvalidationReport(strategy=InvalidationStrategy.TTL_BASED)
        assert rpt.overall_score == 0.0
        assert rpt.recommendations == []
        assert rpt.analyzed_at is not None


# ---------------------------------------------------------------------------
# Utility function tests
# ---------------------------------------------------------------------------


class TestUtilityFunctions:
    """Test helper / utility functions."""

    def test_clamp_within_range(self):
        assert _clamp(50.0) == 50.0

    def test_clamp_below_zero(self):
        assert _clamp(-10.0) == 0.0

    def test_clamp_above_max(self):
        assert _clamp(150.0) == _MAX_SCORE

    def test_clamp_custom_bounds(self):
        assert _clamp(5.0, 2.0, 8.0) == 5.0
        assert _clamp(1.0, 2.0, 8.0) == 2.0
        assert _clamp(10.0, 2.0, 8.0) == 8.0

    def test_effective_multilayer_hit_rate_empty(self):
        assert _effective_multilayer_hit_rate([]) == 0.0

    def test_effective_multilayer_hit_rate_single(self):
        layer = _l1(hit_rate=0.9)
        assert _effective_multilayer_hit_rate([layer]) == pytest.approx(0.9, abs=0.01)

    def test_effective_multilayer_hit_rate_two_layers(self):
        # miss_rate = (1-0.9) * (1-0.8) = 0.1 * 0.2 = 0.02 ⇒ hit = 0.98
        layers = [_l1(hit_rate=0.9), _l2(hit_rate=0.8)]
        assert _effective_multilayer_hit_rate(layers) == pytest.approx(0.98, abs=0.01)

    def test_effective_multilayer_hit_rate_perfect(self):
        layers = [_l1(hit_rate=1.0)]
        assert _effective_multilayer_hit_rate(layers) == 1.0

    def test_effective_multilayer_hit_rate_zero(self):
        layers = [_l1(hit_rate=0.0), _l2(hit_rate=0.0)]
        assert _effective_multilayer_hit_rate(layers) == 0.0

    def test_compute_warm_up_empty(self):
        assert _compute_warm_up_seconds([]) == 0.0

    def test_compute_warm_up_single(self):
        assert _compute_warm_up_seconds([_l1(ttl_seconds=60)]) == 60.0

    def test_compute_warm_up_multiple(self):
        layers = [_l1(ttl_seconds=60), _l2(ttl_seconds=300)]
        assert _compute_warm_up_seconds(layers) == 300.0

    def test_eviction_pressure_normal(self):
        layer = _l1(capacity_mb=256.0)
        p = _eviction_pressure(layer, 128.0)
        assert p == pytest.approx(0.5, abs=0.01)

    def test_eviction_pressure_over_capacity(self):
        layer = _l1(capacity_mb=100.0)
        p = _eviction_pressure(layer, 200.0)
        assert p == 1.0  # clamped

    def test_eviction_pressure_zero_capacity(self):
        layer = _l1(capacity_mb=0.0)
        p = _eviction_pressure(layer, 100.0)
        assert p == 1.0

    def test_stampede_risk_level_none(self):
        assert _stampede_risk_level(0) == StampedeRisk.NONE
        assert _stampede_risk_level(-5) == StampedeRisk.NONE

    def test_stampede_risk_level_low(self):
        assert _stampede_risk_level(5) == StampedeRisk.LOW

    def test_stampede_risk_level_medium(self):
        assert _stampede_risk_level(25) == StampedeRisk.MEDIUM

    def test_stampede_risk_level_high(self):
        assert _stampede_risk_level(100) == StampedeRisk.HIGH

    def test_stampede_risk_level_critical(self):
        assert _stampede_risk_level(300) == StampedeRisk.CRITICAL

    def test_stampede_risk_level_boundary_at_threshold(self):
        assert _stampede_risk_level(10) == StampedeRisk.MEDIUM
        assert _stampede_risk_level(9) == StampedeRisk.LOW
        assert _stampede_risk_level(_STAMPEDE_CONCURRENCY_THRESHOLD) == StampedeRisk.HIGH
        assert _stampede_risk_level(200) == StampedeRisk.CRITICAL


# ---------------------------------------------------------------------------
# Stampede analysis tests
# ---------------------------------------------------------------------------


class TestStampedeAnalysis:
    """Test thundering herd / cache stampede analysis."""

    def test_basic_stampede_ttl_based(self):
        cfg = _default_config(concurrent_readers=100)
        result = _engine().analyze_stampede(cfg)
        assert result.risk_level == StampedeRisk.HIGH
        assert result.estimated_concurrent_misses == 100
        assert result.estimated_recovery_ms > 0

    def test_stampede_with_swr_reduces_risk(self):
        cfg = _default_config(
            concurrent_readers=100,
            layers=[_l1(stale_while_revalidate=True), _l2()],
        )
        result = _engine().analyze_stampede(cfg)
        assert result.estimated_concurrent_misses == 10
        assert result.risk_level == StampedeRisk.MEDIUM

    def test_stampede_event_driven_reduces_risk(self):
        cfg = _default_config(
            strategy=InvalidationStrategy.EVENT_DRIVEN,
            concurrent_readers=100,
        )
        result = _engine().analyze_stampede(cfg)
        assert result.estimated_concurrent_misses == 20

    def test_stampede_low_concurrency(self):
        cfg = _default_config(concurrent_readers=3)
        result = _engine().analyze_stampede(cfg)
        assert result.risk_level == StampedeRisk.LOW

    def test_stampede_critical_has_mitigations(self):
        cfg = _default_config(concurrent_readers=500)
        result = _engine().analyze_stampede(cfg)
        assert result.risk_level == StampedeRisk.CRITICAL
        assert len(result.mitigations) >= 3
        assert any("singleflight" in m.lower() or "coalescing" in m.lower() for m in result.mitigations)
        assert any("probabilistic" in m.lower() for m in result.mitigations)

    def test_stampede_high_has_jitter_mitigation(self):
        cfg = _default_config(concurrent_readers=100)
        result = _engine().analyze_stampede(cfg)
        assert any("jitter" in m.lower() for m in result.mitigations)

    def test_stampede_no_readers(self):
        cfg = _default_config(concurrent_readers=0)
        result = _engine().analyze_stampede(cfg)
        assert result.risk_level == StampedeRisk.NONE
        assert result.estimated_concurrent_misses == 0


# ---------------------------------------------------------------------------
# Consistency window tests
# ---------------------------------------------------------------------------


class TestConsistencyWindows:
    """Test consistency window analysis between cache layers."""

    def test_no_windows_single_layer(self):
        cfg = _default_config(layers=[_l1()])
        result = _engine().analyze_consistency_windows(cfg)
        assert result == []

    def test_no_windows_empty_layers(self):
        cfg = _default_config(layers=[])
        result = _engine().analyze_consistency_windows(cfg)
        assert result == []

    def test_ttl_based_consistency(self):
        cfg = _default_config(
            strategy=InvalidationStrategy.TTL_BASED,
            layers=[_l1(ttl_seconds=60), _l2(ttl_seconds=300)],
        )
        windows = _engine().analyze_consistency_windows(cfg)
        assert len(windows) == 1
        assert windows[0].layer_pair == ("l1_local", "l2_shared")
        # max staleness = max(60, 300) * 1000 = 300000 ms
        assert windows[0].max_staleness_ms == 300_000.0

    def test_event_driven_consistency(self):
        cfg = _default_config(
            strategy=InvalidationStrategy.EVENT_DRIVEN,
            event_propagation_delay_ms=15.0,
            layers=[_l1(), _l2()],
        )
        windows = _engine().analyze_consistency_windows(cfg)
        assert len(windows) == 1
        assert windows[0].max_staleness_ms == 15.0
        assert windows[0].expected_staleness_ms == 7.5

    def test_write_through_consistency(self):
        cfg = _default_config(
            strategy=InvalidationStrategy.WRITE_THROUGH,
            layers=[_l1(ttl_seconds=60), _l2(ttl_seconds=300)],
        )
        windows = _engine().analyze_consistency_windows(cfg)
        assert len(windows) == 1
        # abs(60 - 300) * 1000 = 240000
        assert windows[0].max_staleness_ms == 240_000.0

    def test_write_behind_adds_buffer_flush(self):
        cfg = _default_config(
            strategy=InvalidationStrategy.WRITE_BEHIND,
            write_buffer_flush_interval_ms=500.0,
            layers=[_l1(ttl_seconds=60), _l2(ttl_seconds=300)],
        )
        windows = _engine().analyze_consistency_windows(cfg)
        # abs(60-300)*1000 + 500 = 240500
        assert windows[0].max_staleness_ms == 240_500.0

    def test_three_layer_consistency(self):
        cfg = _default_config(
            strategy=InvalidationStrategy.TTL_BASED,
            layers=[_l1(), _l2(), _cdn()],
        )
        windows = _engine().analyze_consistency_windows(cfg)
        assert len(windows) == 2
        assert windows[0].layer_pair == ("l1_local", "l2_shared")
        assert windows[1].layer_pair == ("l2_shared", "cdn")

    def test_stale_reads_percent_bounded(self):
        cfg = _default_config(
            strategy=InvalidationStrategy.TTL_BASED,
            layers=[_l1(ttl_seconds=1), _l2(ttl_seconds=1)],
        )
        windows = _engine().analyze_consistency_windows(cfg)
        assert 0.0 <= windows[0].stale_reads_percent <= 100.0


# ---------------------------------------------------------------------------
# Hit-rate model tests
# ---------------------------------------------------------------------------


class TestHitRateModel:
    """Test hit-rate modelling."""

    def test_no_layers_returns_zero(self):
        cfg = _default_config(layers=[])
        model = _engine().model_hit_rate(cfg)
        assert model.effective_hit_rate == 0.0
        assert len(model.recommendations) == 1

    def test_single_layer_hit_rate(self):
        cfg = _default_config(layers=[_l1(hit_rate=0.9)])
        model = _engine().model_hit_rate(cfg, working_set_mb=32.0)
        assert model.steady_state_hit_rate >= 0.9
        assert model.cold_start_hit_rate < model.steady_state_hit_rate
        assert model.warm_up_time_seconds == 60.0  # max TTL of single layer

    def test_event_driven_boost(self):
        cfg_ttl = _default_config(
            strategy=InvalidationStrategy.TTL_BASED,
            layers=[_l1(hit_rate=0.9)],
        )
        cfg_event = _default_config(
            strategy=InvalidationStrategy.EVENT_DRIVEN,
            layers=[_l1(hit_rate=0.9)],
        )
        model_ttl = _engine().model_hit_rate(cfg_ttl, working_set_mb=32.0)
        model_event = _engine().model_hit_rate(cfg_event, working_set_mb=32.0)
        assert model_event.steady_state_hit_rate >= model_ttl.steady_state_hit_rate

    def test_high_pressure_degrades_hit_rate(self):
        cfg = _default_config(layers=[_l1(hit_rate=0.9, capacity_mb=10.0)])
        model = _engine().model_hit_rate(cfg, working_set_mb=100.0)
        # Very high pressure should degrade effective hit rate
        assert model.effective_hit_rate < 0.9
        assert model.eviction_pressure > 0.5

    def test_high_pressure_generates_recommendation(self):
        cfg = _default_config(layers=[_l1(hit_rate=0.9, capacity_mb=10.0)])
        model = _engine().model_hit_rate(cfg, working_set_mb=100.0)
        assert any("pressure" in r.lower() or "capacity" in r.lower() for r in model.recommendations)

    def test_low_hit_rate_generates_recommendation(self):
        cfg = _default_config(layers=[_l1(hit_rate=0.3)])
        model = _engine().model_hit_rate(cfg, working_set_mb=32.0)
        assert any("hit rate" in r.lower() for r in model.recommendations)

    def test_long_warmup_generates_recommendation(self):
        cfg = _default_config(layers=[_l1(ttl_seconds=1200)])  # 20 min TTL
        model = _engine().model_hit_rate(cfg, working_set_mb=32.0)
        assert model.warm_up_time_seconds == 1200.0
        assert any("warm" in r.lower() for r in model.recommendations)

    def test_write_through_boost(self):
        cfg = _default_config(
            strategy=InvalidationStrategy.WRITE_THROUGH,
            layers=[_l1(hit_rate=0.9)],
        )
        model = _engine().model_hit_rate(cfg, working_set_mb=32.0)
        # Write-through gets a 0.01 boost
        assert model.steady_state_hit_rate >= 0.91


# ---------------------------------------------------------------------------
# Coherence protocol tests
# ---------------------------------------------------------------------------


class TestCoherenceTransitions:
    """Test MESI-like coherence protocol simulation."""

    def test_empty_nodes(self):
        result = _engine().simulate_coherence_transitions([], "write")
        assert result == []

    def test_write_single_node(self):
        result = _engine().simulate_coherence_transitions(["n1"], "write")
        assert len(result) == 1
        assert result[0].node_id == "n1"
        assert result[0].to_state == CoherenceState.MODIFIED

    def test_write_multiple_nodes(self):
        result = _engine().simulate_coherence_transitions(
            ["n1", "n2", "n3"], "write"
        )
        assert len(result) == 3
        # Writer gets MODIFIED
        assert result[0].to_state == CoherenceState.MODIFIED
        assert result[0].trigger == "local_write"
        # Others get INVALID
        for t in result[1:]:
            assert t.to_state == CoherenceState.INVALID
            assert t.trigger == "remote_write_invalidation"

    def test_read_single_node_exclusive(self):
        result = _engine().simulate_coherence_transitions(["n1"], "read")
        assert len(result) == 1
        assert result[0].to_state == CoherenceState.EXCLUSIVE

    def test_read_multiple_nodes_shared(self):
        result = _engine().simulate_coherence_transitions(
            ["n1", "n2"], "read"
        )
        assert len(result) == 2
        assert result[0].to_state == CoherenceState.SHARED
        assert result[0].trigger == "local_read_shared"
        assert result[1].to_state == CoherenceState.SHARED
        assert result[1].trigger == "remote_read_downgrade"

    def test_transitions_have_timestamps(self):
        result = _engine().simulate_coherence_transitions(["n1"], "write")
        assert result[0].timestamp is not None

    def test_unknown_operation_returns_empty(self):
        result = _engine().simulate_coherence_transitions(
            ["n1", "n2"], "delete"
        )
        assert result == []


# ---------------------------------------------------------------------------
# Poisoning risk tests
# ---------------------------------------------------------------------------


class TestCachePoisoningRisk:
    """Test cache poisoning risk assessment."""

    def test_minimal_config_low_risk(self):
        cfg = _default_config(
            strategy=InvalidationStrategy.EVENT_DRIVEN,
            layers=[_l1(ttl_seconds=60)],
        )
        risk = _engine().assess_poisoning_risk(cfg)
        # Event-driven subtracts 10, short TTL, single non-CDN layer
        assert risk.risk_score < 30.0

    def test_cdn_layer_increases_risk(self):
        cfg = _default_config(
            layers=[_cdn(ttl_seconds=7200)],
        )
        risk = _engine().assess_poisoning_risk(cfg)
        assert risk.risk_score > 0.0
        assert "cdn" in risk.vulnerable_layers

    def test_long_ttl_increases_risk(self):
        cfg_short = _default_config(layers=[_l1(ttl_seconds=60)])
        cfg_long = _default_config(layers=[_l1(ttl_seconds=7200)])
        risk_short = _engine().assess_poisoning_risk(cfg_short)
        risk_long = _engine().assess_poisoning_risk(cfg_long)
        assert risk_long.risk_score > risk_short.risk_score

    def test_ttl_strategy_adds_risk(self):
        cfg = _default_config(
            strategy=InvalidationStrategy.TTL_BASED,
            layers=[_l1()],
        )
        risk = _engine().assess_poisoning_risk(cfg)
        assert any("ttl-based" in v.lower() or "time expiry" in v.lower() for v in risk.attack_vectors)

    def test_write_through_reduces_risk(self):
        cfg = _default_config(
            strategy=InvalidationStrategy.WRITE_THROUGH,
            layers=[_l1()],
        )
        risk = _engine().assess_poisoning_risk(cfg)
        assert any("write-through" in m.lower() for m in risk.mitigations)

    def test_graph_cache_no_encryption(self):
        cache = _comp("cache1", ComponentType.CACHE)
        g = _graph(cache)
        cfg = _default_config(layers=[_l1()])
        risk = _engine().assess_poisoning_risk(cfg, g)
        # No encryption + no auth ⇒ vectors added
        assert any("encryption" in v.lower() or "mitm" in v.lower() for v in risk.attack_vectors)
        assert any("authentication" in v.lower() or "unauthorized" in v.lower() for v in risk.attack_vectors)

    def test_graph_with_no_cache_components(self):
        app = _comp("app1", ComponentType.APP_SERVER)
        g = _graph(app)
        cfg = _default_config(layers=[_l1()])
        risk = _engine().assess_poisoning_risk(cfg, g)
        # No cache components ⇒ no graph-based vectors
        assert risk.risk_score >= 0.0

    def test_risk_score_clamped(self):
        cfg = _default_config(
            strategy=InvalidationStrategy.TTL_BASED,
            layers=[_cdn(ttl_seconds=86400)] * 5,  # many long-TTL CDN layers
        )
        risk = _engine().assess_poisoning_risk(cfg)
        assert risk.risk_score <= _MAX_SCORE

    def test_default_mitigations_when_none_from_strategy(self):
        cfg = _default_config(
            strategy=InvalidationStrategy.WRITE_AROUND,
            layers=[_l1()],
        )
        risk = _engine().assess_poisoning_risk(cfg)
        assert len(risk.mitigations) >= 1


# ---------------------------------------------------------------------------
# Eviction policy tests
# ---------------------------------------------------------------------------


class TestEvictionAnalysis:
    """Test eviction policy analysis under memory pressure."""

    @pytest.mark.parametrize(
        "policy",
        list(EvictionPolicy),
    )
    def test_all_policies_produce_result(self, policy):
        layer = _l1(eviction_policy=policy, capacity_mb=64.0)
        result = _engine().analyze_eviction_policy(layer, working_set_mb=32.0)
        assert result.policy == policy
        assert 0.0 <= result.hit_rate_under_pressure <= 1.0
        assert result.fairness_score >= 0.0

    def test_arc_has_highest_effectiveness(self):
        layer_arc = _l1(eviction_policy=EvictionPolicy.ARC)
        layer_fifo = _l1(eviction_policy=EvictionPolicy.FIFO)
        result_arc = _engine().analyze_eviction_policy(layer_arc, 32.0)
        result_fifo = _engine().analyze_eviction_policy(layer_fifo, 32.0)
        assert result_arc.hit_rate_under_pressure > result_fifo.hit_rate_under_pressure

    def test_high_pressure_generates_recommendation(self):
        layer = _l1(capacity_mb=10.0)
        result = _engine().analyze_eviction_policy(layer, working_set_mb=100.0)
        assert len(result.recommendations) >= 1
        assert any("pressure" in r.lower() or "capacity" in r.lower() for r in result.recommendations)

    def test_fifo_under_pressure_gets_recommendation(self):
        layer = _l1(eviction_policy=EvictionPolicy.FIFO, capacity_mb=50.0)
        result = _engine().analyze_eviction_policy(layer, working_set_mb=40.0)
        assert any("fifo" in r.lower() for r in result.recommendations)

    def test_random_gets_recommendation(self):
        layer = _l1(eviction_policy=EvictionPolicy.RANDOM, capacity_mb=256.0)
        result = _engine().analyze_eviction_policy(layer, working_set_mb=32.0)
        assert any("random" in r.lower() for r in result.recommendations)

    def test_lfu_high_pressure_gets_recommendation(self):
        layer = _l1(eviction_policy=EvictionPolicy.LFU, capacity_mb=30.0)
        result = _engine().analyze_eviction_policy(layer, working_set_mb=30.0)
        assert any("lfu" in r.lower() or "arc" in r.lower() for r in result.recommendations)

    def test_eviction_rate_proportional_to_pressure(self):
        layer = _l1(capacity_mb=64.0, hit_rate=0.9)
        low = _engine().analyze_eviction_policy(layer, 10.0)
        high = _engine().analyze_eviction_policy(layer, 60.0)
        assert high.estimated_eviction_rate > low.estimated_eviction_rate


# ---------------------------------------------------------------------------
# Invalidation scope cost tests
# ---------------------------------------------------------------------------


class TestInvalidationCost:
    """Test invalidation scope cost estimation."""

    def test_single_key_cost(self):
        cfg = _default_config(scope=InvalidationScope.SINGLE_KEY)
        cost = _engine().estimate_invalidation_cost(cfg, num_keys=1000)
        assert cost["affected_keys"] == 1.0
        assert cost["scope"] == "single_key"
        assert cost["total_cost_ms"] > 0

    def test_tag_based_cost(self):
        cfg = _default_config(
            scope=InvalidationScope.TAG_BASED,
            tags_per_key=5,
        )
        cost = _engine().estimate_invalidation_cost(cfg, num_keys=1000)
        assert cost["affected_keys"] == 200.0  # 1000 / 5

    def test_tag_based_zero_tags(self):
        cfg = _default_config(
            scope=InvalidationScope.TAG_BASED,
            tags_per_key=0,
        )
        cost = _engine().estimate_invalidation_cost(cfg, num_keys=1000)
        assert cost["affected_keys"] == 1000.0

    def test_pattern_based_cost(self):
        cfg = _default_config(scope=InvalidationScope.PATTERN_BASED)
        cost = _engine().estimate_invalidation_cost(cfg, num_keys=1000)
        assert cost["affected_keys"] == 200.0  # 1000 / 5

    def test_full_flush_cost(self):
        cfg = _default_config(scope=InvalidationScope.FULL_FLUSH)
        cost = _engine().estimate_invalidation_cost(cfg, num_keys=1000)
        assert cost["affected_keys"] == 1000.0

    def test_multi_layer_multiplies_cost(self):
        cfg_one = _default_config(
            scope=InvalidationScope.SINGLE_KEY,
            layers=[_l1()],
        )
        cfg_two = _default_config(
            scope=InvalidationScope.SINGLE_KEY,
            layers=[_l1(), _l2()],
        )
        cost_one = _engine().estimate_invalidation_cost(cfg_one, 100)
        cost_two = _engine().estimate_invalidation_cost(cfg_two, 100)
        assert cost_two["total_cost_ms"] > cost_one["total_cost_ms"]

    def test_no_layers_still_works(self):
        cfg = _default_config(scope=InvalidationScope.SINGLE_KEY, layers=[])
        cost = _engine().estimate_invalidation_cost(cfg, num_keys=100)
        assert cost["layer_count"] == 1.0  # max(0, 1)
        assert cost["total_cost_ms"] > 0


# ---------------------------------------------------------------------------
# Cache warming tests
# ---------------------------------------------------------------------------


class TestCacheWarming:
    """Test cache warming and cold-start analysis."""

    def test_no_layers(self):
        cfg = _default_config(layers=[])
        result = _engine().analyze_cache_warming(cfg)
        assert result["warming_needed"] is False
        assert result["warming_time_seconds"] == 0.0

    def test_cold_start_impact_calculated(self):
        cfg = _default_config(layers=[_l1(capacity_mb=64.0)])
        result = _engine().analyze_cache_warming(cfg, cold_start=True)
        assert result["warming_needed"] is True
        assert result["warming_time_seconds"] > 0

    def test_no_cold_start(self):
        cfg = _default_config(layers=[_l1()])
        result = _engine().analyze_cache_warming(cfg, cold_start=False)
        assert result["cold_start_impact"] == "none"

    def test_large_capacity_high_impact(self):
        cfg = _default_config(
            layers=[_l2(capacity_mb=4096.0)],
            origin_latency_ms=100.0,
        )
        result = _engine().analyze_cache_warming(cfg, cold_start=True)
        assert result["cold_start_impact"] == "high"
        assert len(result["recommendations"]) >= 1

    def test_cdn_warming_recommendation(self):
        cfg = _default_config(layers=[_cdn()])
        result = _engine().analyze_cache_warming(cfg, cold_start=True)
        assert any("cdn" in r.lower() for r in result["recommendations"])

    def test_swr_recommendation_absent_when_enabled(self):
        cfg = _default_config(
            layers=[_l1(stale_while_revalidate=True)],
        )
        result = _engine().analyze_cache_warming(cfg, cold_start=True)
        swr_recs = [r for r in result["recommendations"] if "stale-while-revalidate" in r.lower()]
        assert len(swr_recs) == 0


# ---------------------------------------------------------------------------
# Graph-aware tests
# ---------------------------------------------------------------------------


class TestGraphAware:
    """Test graph-aware cache resilience assessment."""

    def test_find_cache_components_none(self):
        g = _graph(_comp("app", ComponentType.APP_SERVER))
        result = _engine().find_cache_components(g)
        assert result == []

    def test_find_cache_components(self):
        c1 = _comp("cache1", ComponentType.CACHE)
        c2 = _comp("app1", ComponentType.APP_SERVER)
        g = _graph(c1, c2)
        result = _engine().find_cache_components(g)
        assert len(result) == 1
        assert result[0].id == "cache1"

    def test_assess_no_caches(self):
        g = _graph(_comp("app", ComponentType.APP_SERVER))
        result = _engine().assess_graph_cache_resilience(g)
        assert result["cache_count"] == 0
        assert result["overall_risk"] == "high"

    def test_assess_spof_cache(self):
        cache = _comp("cache1", ComponentType.CACHE)
        app = _comp("app1", ComponentType.APP_SERVER)
        g = _graph(cache, app)
        g.add_dependency(Dependency(source_id="app1", target_id="cache1"))
        result = _engine().assess_graph_cache_resilience(g)
        assert "cache1" in result["spof_caches"]
        assert result["overall_risk"] in ("medium", "high")

    def test_assess_redundant_cache(self):
        cache = Component(
            id="cache1", name="cache1", type=ComponentType.CACHE, replicas=3,
        )
        app = _comp("app1", ComponentType.APP_SERVER)
        g = _graph(cache, app)
        g.add_dependency(Dependency(source_id="app1", target_id="cache1"))
        result = _engine().assess_graph_cache_resilience(g)
        assert "cache1" in result["redundant_caches"]
        assert result["overall_risk"] == "low"

    def test_assess_with_config_runs_full_analysis(self):
        cache = _comp("cache1", ComponentType.CACHE)
        g = _graph(cache)
        cfg = _default_config(layers=[_l1()])
        result = _engine().assess_graph_cache_resilience(g, cfg)
        assert "invalidation_report" in result
        report = result["invalidation_report"]
        assert isinstance(report, CacheInvalidationReport)

    def test_assess_mixed_caches(self):
        c1 = _comp("cache_spof", ComponentType.CACHE)
        c2 = Component(
            id="cache_ok", name="cache_ok", type=ComponentType.CACHE, replicas=3,
        )
        app = _comp("app", ComponentType.APP_SERVER)
        g = _graph(c1, c2, app)
        g.add_dependency(Dependency(source_id="app", target_id="cache_spof"))
        result = _engine().assess_graph_cache_resilience(g)
        assert result["overall_risk"] == "medium"


# ---------------------------------------------------------------------------
# Full analysis integration tests
# ---------------------------------------------------------------------------


class TestFullAnalysis:
    """Test the full analyze() integration."""

    def test_basic_analysis(self):
        cfg = _default_config()
        report = _engine().analyze(cfg)
        assert isinstance(report, CacheInvalidationReport)
        assert report.strategy == InvalidationStrategy.TTL_BASED
        assert 0 <= report.overall_score <= _MAX_SCORE
        assert report.analyzed_at is not None

    def test_analysis_with_graph(self):
        cache = _comp("cache1", ComponentType.CACHE)
        g = _graph(cache)
        cfg = _default_config()
        report = _engine().analyze(cfg, g)
        # Coherence transitions should be generated for cache components
        assert len(report.coherence_transitions) >= 1

    def test_analysis_no_graph_no_coherence(self):
        cfg = _default_config()
        report = _engine().analyze(cfg)
        assert report.coherence_transitions == []

    def test_score_degrades_with_high_stampede(self):
        cfg_low = _default_config(concurrent_readers=3)
        cfg_high = _default_config(concurrent_readers=500)
        score_low = _engine().analyze(cfg_low).overall_score
        score_high = _engine().analyze(cfg_high).overall_score
        assert score_low > score_high

    def test_score_degrades_with_poor_hit_rate(self):
        cfg_good = _default_config(layers=[_l1(hit_rate=0.99)])
        cfg_poor = _default_config(layers=[_l1(hit_rate=0.3)])
        score_good = _engine().analyze(cfg_good, working_set_mb=32.0).overall_score
        score_poor = _engine().analyze(cfg_poor, working_set_mb=32.0).overall_score
        assert score_good > score_poor

    def test_write_behind_recommendation(self):
        cfg = _default_config(strategy=InvalidationStrategy.WRITE_BEHIND)
        report = _engine().analyze(cfg)
        assert any("write-behind" in r.lower() for r in report.recommendations)

    def test_write_around_recommendation(self):
        cfg = _default_config(strategy=InvalidationStrategy.WRITE_AROUND)
        report = _engine().analyze(cfg)
        assert any("write-around" in r.lower() for r in report.recommendations)

    def test_full_flush_recommendation(self):
        cfg = _default_config(scope=InvalidationScope.FULL_FLUSH)
        report = _engine().analyze(cfg)
        assert any("flush" in r.lower() for r in report.recommendations)

    def test_eviction_analyses_per_layer(self):
        cfg = _default_config(layers=[_l1(), _l2(), _cdn()])
        report = _engine().analyze(cfg)
        assert len(report.eviction_analyses) == 3

    def test_recommendations_deduplicated(self):
        cfg = _default_config(
            concurrent_readers=500,
            strategy=InvalidationStrategy.WRITE_BEHIND,
            scope=InvalidationScope.FULL_FLUSH,
            layers=[_l1(hit_rate=0.3, capacity_mb=5.0)],
        )
        report = _engine().analyze(cfg, working_set_mb=200.0)
        # All recommendations should be unique
        assert len(report.recommendations) == len(set(report.recommendations))

    def test_score_clamped_to_range(self):
        # Worst-case config to push score below 0
        cfg = _default_config(
            concurrent_readers=1000,
            strategy=InvalidationStrategy.TTL_BASED,
            layers=[_cdn(ttl_seconds=86400, hit_rate=0.1, capacity_mb=5.0)],
        )
        report = _engine().analyze(cfg, working_set_mb=500.0)
        assert 0.0 <= report.overall_score <= _MAX_SCORE

    def test_medium_staleness_degrades_score_moderately(self):
        """Consistency windows between 10s and 60s trigger a moderate penalty."""
        # Event-driven with 30_000ms propagation delay ⇒ max_staleness = 30000
        cfg = _default_config(
            strategy=InvalidationStrategy.EVENT_DRIVEN,
            event_propagation_delay_ms=30_000.0,
            layers=[_l1(ttl_seconds=10), _l2(ttl_seconds=10)],
        )
        report = _engine().analyze(cfg)
        # Score should be penalised but not as much as > 60s staleness
        cfg_low = _default_config(
            strategy=InvalidationStrategy.EVENT_DRIVEN,
            event_propagation_delay_ms=1.0,
            layers=[_l1(ttl_seconds=10), _l2(ttl_seconds=10)],
        )
        report_low = _engine().analyze(cfg_low)
        assert report_low.overall_score > report.overall_score

    def test_large_staleness_degrades_score(self):
        cfg_fast = _default_config(
            strategy=InvalidationStrategy.EVENT_DRIVEN,
            layers=[_l1(ttl_seconds=10), _l2(ttl_seconds=10)],
        )
        cfg_slow = _default_config(
            strategy=InvalidationStrategy.TTL_BASED,
            layers=[_l1(ttl_seconds=600), _l2(ttl_seconds=3600)],
        )
        score_fast = _engine().analyze(cfg_fast).overall_score
        score_slow = _engine().analyze(cfg_slow).overall_score
        assert score_fast > score_slow

    def test_eviction_pressure_degrades_score(self):
        cfg_low = _default_config(layers=[_l1(capacity_mb=1024.0)])
        cfg_high = _default_config(layers=[_l1(capacity_mb=10.0)])
        score_low = _engine().analyze(cfg_low, working_set_mb=50.0).overall_score
        score_high = _engine().analyze(cfg_high, working_set_mb=200.0).overall_score
        assert score_low > score_high

    def test_multiple_cache_components_in_graph(self):
        c1 = _comp("cache_a", ComponentType.CACHE)
        c2 = _comp("cache_b", ComponentType.CACHE)
        g = _graph(c1, c2)
        cfg = _default_config()
        report = _engine().analyze(cfg, g)
        # Should generate coherence transitions for both caches
        assert len(report.coherence_transitions) >= 2

    def test_analysis_empty_config(self):
        cfg = InvalidationConfig()
        report = _engine().analyze(cfg)
        assert report.strategy == InvalidationStrategy.TTL_BASED
        assert report.overall_score >= 0.0


# ---------------------------------------------------------------------------
# Edge cases and boundary tests
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_zero_ttl_layer(self):
        layer = CacheLayerConfig(level=CacheLevel.L1_LOCAL, ttl_seconds=0)
        cfg = _default_config(layers=[layer])
        result = _engine().model_hit_rate(cfg)
        assert result.warm_up_time_seconds == 0.0

    def test_zero_capacity_layer(self):
        layer = CacheLayerConfig(level=CacheLevel.L1_LOCAL, capacity_mb=0.0)
        cfg = _default_config(layers=[layer])
        result = _engine().model_hit_rate(cfg, working_set_mb=100.0)
        assert result.eviction_pressure == 1.0

    def test_zero_hit_rate_layer(self):
        layer = CacheLayerConfig(level=CacheLevel.L1_LOCAL, hit_rate=0.0)
        assert _effective_multilayer_hit_rate([layer]) == 0.0

    def test_perfect_hit_rate_layer(self):
        layer = CacheLayerConfig(level=CacheLevel.L1_LOCAL, hit_rate=1.0)
        assert _effective_multilayer_hit_rate([layer]) == 1.0

    def test_many_layers(self):
        layers = [
            CacheLayerConfig(level=CacheLevel.L1_LOCAL, hit_rate=0.5)
            for _ in range(10)
        ]
        # miss = 0.5^10 ≈ 0.001 ⇒ hit ≈ 0.999
        assert _effective_multilayer_hit_rate(layers) == pytest.approx(
            1.0 - 0.5**10, abs=0.001,
        )

    def test_single_node_coherence_read(self):
        result = _engine().simulate_coherence_transitions(["single"], "read")
        assert result[0].to_state == CoherenceState.EXCLUSIVE

    def test_invalidation_cost_one_key(self):
        cfg = _default_config(scope=InvalidationScope.SINGLE_KEY, layers=[_l1()])
        cost = _engine().estimate_invalidation_cost(cfg, num_keys=1)
        assert cost["affected_keys"] == 1.0

    def test_dependency_used_correctly(self):
        dep = Dependency(source_id="a1", target_id="b1")
        assert dep.source_id == "a1"
        assert dep.target_id == "b1"
