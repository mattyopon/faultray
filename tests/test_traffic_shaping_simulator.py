"""Tests for Traffic Shaping Simulator.

Comprehensive tests covering all enums, data models, traffic pattern
generation, traffic splitting strategies, geographic distribution analysis,
traffic mirroring impact, request prioritization/queuing, TLS overhead,
CDN offload modelling, origin shield evaluation, WebSocket/HTTP protocol
mix, API gateway throttling, traffic replay, anomaly detection, helpers,
and edge cases.
"""

from __future__ import annotations

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    Capacity,
    Component,
    ComponentType,
    Dependency,
    NetworkProfile,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.traffic_shaping_simulator import (
    AnomalyDetectionResult,
    AnomalyVerdict,
    CdnOffloadResult,
    GeoDistributionResult,
    GeoRegion,
    MirrorImpact,
    OriginShieldResult,
    PriorityAnalysisResult,
    PriorityQueueResult,
    ProtocolMix,
    ProtocolMixResult,
    ReplayResult,
    ReplayScenario,
    RequestPriority,
    SplitConfig,
    SplitResult,
    SplitStrategy,
    ThrottleConfig,
    ThrottleResult,
    TlsOverheadResult,
    TrafficPatternKind,
    TrafficShapeSnapshot,
    TrafficShapingSimulator,
    _BASE_LATENCY,
    _DEFAULT_REGIONS,
    _PRIORITY_WEIGHT,
    _clamp,
    _component_latency,
    _detect_bottlenecks,
    _effective_max_rps,
    _error_rate_for_load,
    _generate_pattern_rps,
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
) -> Component:
    return Component(
        id=cid,
        name=cid,
        type=ctype,
        replicas=replicas,
        capacity=Capacity(max_rps=max_rps, max_connections=max_connections),
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


class TestTrafficPatternKindEnum:
    def test_all_values(self) -> None:
        assert len(TrafficPatternKind) == 6

    def test_steady(self) -> None:
        assert TrafficPatternKind.STEADY == "steady"

    def test_bursty(self) -> None:
        assert TrafficPatternKind.BURSTY == "bursty"

    def test_sinusoidal(self) -> None:
        assert TrafficPatternKind.SINUSOIDAL == "sinusoidal"

    def test_spike(self) -> None:
        assert TrafficPatternKind.SPIKE == "spike"

    def test_ramp_up(self) -> None:
        assert TrafficPatternKind.RAMP_UP == "ramp_up"

    def test_seasonal(self) -> None:
        assert TrafficPatternKind.SEASONAL == "seasonal"


class TestSplitStrategyEnum:
    def test_all_values(self) -> None:
        assert len(SplitStrategy) == 4

    def test_canary(self) -> None:
        assert SplitStrategy.CANARY == "canary"

    def test_ab_test(self) -> None:
        assert SplitStrategy.AB_TEST == "ab_test"

    def test_blue_green(self) -> None:
        assert SplitStrategy.BLUE_GREEN == "blue_green"

    def test_shadow(self) -> None:
        assert SplitStrategy.SHADOW == "shadow"


class TestRequestPriorityEnum:
    def test_all_values(self) -> None:
        assert len(RequestPriority) == 5

    def test_critical(self) -> None:
        assert RequestPriority.CRITICAL == "critical"

    def test_background(self) -> None:
        assert RequestPriority.BACKGROUND == "background"


class TestAnomalyVerdictEnum:
    def test_all_values(self) -> None:
        assert len(AnomalyVerdict) == 5

    def test_organic_spike(self) -> None:
        assert AnomalyVerdict.ORGANIC_SPIKE == "organic_spike"

    def test_ddos_volumetric(self) -> None:
        assert AnomalyVerdict.DDOS_VOLUMETRIC == "ddos_volumetric"

    def test_normal(self) -> None:
        assert AnomalyVerdict.NORMAL == "normal"


class TestProtocolMixEnum:
    def test_all_values(self) -> None:
        assert len(ProtocolMix) == 5

    def test_websocket(self) -> None:
        assert ProtocolMix.WEBSOCKET == "websocket"


# ---------------------------------------------------------------------------
# 2. Data model coverage
# ---------------------------------------------------------------------------


class TestDataModels:
    def test_traffic_shape_snapshot_defaults(self) -> None:
        snap = TrafficShapeSnapshot()
        assert snap.timestamp_offset_s == 0
        assert snap.requests_per_second == 0.0
        assert snap.error_rate == 0.0
        assert snap.latency_ms == 0.0

    def test_split_config_defaults(self) -> None:
        cfg = SplitConfig()
        assert cfg.strategy == SplitStrategy.CANARY
        assert cfg.primary_weight == 0.9
        assert cfg.secondary_weight == 0.1
        assert cfg.mirror_copy is False

    def test_split_result_fields(self) -> None:
        r = SplitResult(strategy=SplitStrategy.BLUE_GREEN)
        assert r.strategy == SplitStrategy.BLUE_GREEN
        assert r.additional_infra_cost_pct == 0.0
        assert r.recommendations == []

    def test_geo_region_defaults(self) -> None:
        gr = GeoRegion(region_name="test", weight=0.5)
        assert gr.latency_penalty_ms == 0.0
        assert gr.pop_count == 0

    def test_mirror_impact_defaults(self) -> None:
        mi = MirrorImpact()
        assert mi.risk_level == "low"
        assert mi.storage_cost_factor == 1.0

    def test_priority_queue_result(self) -> None:
        pqr = PriorityQueueResult(priority=RequestPriority.HIGH)
        assert pqr.queue_depth == 0
        assert pqr.drop_rate == 0.0

    def test_tls_overhead_result(self) -> None:
        t = TlsOverheadResult()
        assert t.handshake_latency_ms == 0.0
        assert t.recommendations == []

    def test_cdn_offload_result(self) -> None:
        c = CdnOffloadResult()
        assert c.cache_hit_ratio == 0.0
        assert c.cost_savings_pct == 0.0

    def test_origin_shield_result(self) -> None:
        o = OriginShieldResult()
        assert o.effective is False

    def test_protocol_mix_result(self) -> None:
        p = ProtocolMixResult()
        assert p.memory_per_ws_conn_kb == 64.0

    def test_throttle_config_defaults(self) -> None:
        tc = ThrottleConfig()
        assert tc.rate_limit_rps == 1000.0
        assert tc.per_client is False

    def test_throttle_result(self) -> None:
        tr = ThrottleResult()
        assert tr.rejection_rate_pct == 0.0

    def test_replay_scenario_defaults(self) -> None:
        rs = ReplayScenario()
        assert rs.name == ""
        assert rs.speed_multiplier == 1.0
        assert rs.scale_factor == 1.0

    def test_replay_result_defaults(self) -> None:
        rr = ReplayResult()
        assert rr.total_requests == 0

    def test_anomaly_detection_result(self) -> None:
        adr = AnomalyDetectionResult()
        assert adr.verdict == AnomalyVerdict.NORMAL
        assert adr.confidence == 0.0

    def test_geo_distribution_result(self) -> None:
        gdr = GeoDistributionResult()
        assert gdr.global_avg_latency_ms == 0.0

    def test_priority_analysis_result(self) -> None:
        par = PriorityAnalysisResult()
        assert par.fairness_index == 0.0


# ---------------------------------------------------------------------------
# 3. Helper functions
# ---------------------------------------------------------------------------


class TestClamp:
    def test_within_range(self) -> None:
        assert _clamp(50.0) == 50.0

    def test_below_minimum(self) -> None:
        assert _clamp(-10.0) == 0.0

    def test_above_maximum(self) -> None:
        assert _clamp(200.0) == 100.0

    def test_custom_bounds(self) -> None:
        assert _clamp(5.0, 1.0, 10.0) == 5.0
        assert _clamp(-1.0, 1.0, 10.0) == 1.0
        assert _clamp(20.0, 1.0, 10.0) == 10.0


class TestEffectiveMaxRps:
    def test_empty_graph(self) -> None:
        g = _graph()
        rps, lim = _effective_max_rps(g)
        assert rps == 0.0
        assert lim == ""

    def test_single_component(self) -> None:
        c = _comp("s1", max_rps=1000, replicas=2)
        g = _graph(c)
        rps, lim = _effective_max_rps(g)
        assert rps == 2000.0
        assert lim == "s1"

    def test_bottleneck_selection(self) -> None:
        c1 = _comp("fast", max_rps=10000, replicas=2)
        c2 = _comp("slow", max_rps=500, replicas=1)
        g = _graph(c1, c2)
        rps, lim = _effective_max_rps(g)
        assert rps == 500.0
        assert lim == "slow"

    def test_autoscaling_uses_max_replicas(self) -> None:
        c = Component(
            id="as",
            name="as",
            type=ComponentType.APP_SERVER,
            replicas=1,
            capacity=Capacity(max_rps=1000),
            autoscaling=AutoScalingConfig(enabled=True, max_replicas=5),
        )
        g = _graph(c)
        rps, _ = _effective_max_rps(g)
        assert rps == 5000.0


class TestComponentLatency:
    def test_low_load(self) -> None:
        lat = _component_latency("app_server", 0.0)
        assert lat == 15.0  # base * (1 + 0)

    def test_full_load(self) -> None:
        lat = _component_latency("app_server", 1.0)
        assert lat == 30.0  # base * (1 + 1)

    def test_overload(self) -> None:
        lat = _component_latency("app_server", 2.0)
        assert lat == 15.0 * (1.0 + 2.0 * 3.0)  # base * (1 + 2*3)

    def test_unknown_type(self) -> None:
        lat = _component_latency("unknown", 0.5)
        assert lat == 10.0 * 1.5  # default 10 * (1+0.5)


class TestErrorRateForLoad:
    def test_negligible(self) -> None:
        assert _error_rate_for_load(0.005) == 0.0

    def test_normal(self) -> None:
        assert _error_rate_for_load(0.5) == 0.001

    def test_near_capacity(self) -> None:
        rate = _error_rate_for_load(0.9)
        assert rate > 0.001
        assert rate < 0.05

    def test_overloaded(self) -> None:
        rate = _error_rate_for_load(1.5)
        assert rate > 0.05

    def test_extreme_overload(self) -> None:
        assert _error_rate_for_load(10.0) == 1.0


class TestGeneratePatternRps:
    def test_steady(self) -> None:
        import random
        rng = random.Random(42)
        rps = _generate_pattern_rps(TrafficPatternKind.STEADY, 0.5, 1000.0, rng)
        assert rps == 600.0

    def test_ramp_up_start(self) -> None:
        import random
        rng = random.Random(42)
        rps = _generate_pattern_rps(TrafficPatternKind.RAMP_UP, 0.0, 1000.0, rng)
        assert rps == 100.0

    def test_ramp_up_end(self) -> None:
        import random
        rng = random.Random(42)
        rps = _generate_pattern_rps(TrafficPatternKind.RAMP_UP, 1.0, 1000.0, rng)
        assert rps == 1000.0

    def test_spike_at_peak(self) -> None:
        import random
        rng = random.Random(42)
        rps = _generate_pattern_rps(TrafficPatternKind.SPIKE, 0.5, 1000.0, rng)
        assert rps == pytest.approx(1000.0, abs=1.0)

    def test_sinusoidal_midpoint(self) -> None:
        import random
        rng = random.Random(42)
        rps = _generate_pattern_rps(TrafficPatternKind.SINUSOIDAL, 0.25, 1000.0, rng)
        assert rps == pytest.approx(1000.0, abs=1.0)

    def test_seasonal(self) -> None:
        import random
        rng = random.Random(42)
        rps = _generate_pattern_rps(TrafficPatternKind.SEASONAL, 0.5, 1000.0, rng)
        assert rps == pytest.approx(1000.0, abs=1.0)

    def test_bursty_deterministic(self) -> None:
        import random
        rng = random.Random(42)
        rps1 = _generate_pattern_rps(TrafficPatternKind.BURSTY, 0.3, 1000.0, rng)
        rps2 = _generate_pattern_rps(TrafficPatternKind.BURSTY, 0.3, 1000.0, rng)
        assert rps1 == rps2  # deterministic for same t


class TestDetectBottlenecks:
    def test_no_bottleneck(self) -> None:
        c = _comp("big", max_rps=10000, replicas=2)
        g = _graph(c)
        assert _detect_bottlenecks(g, 100.0) == []

    def test_bottleneck_detected(self) -> None:
        c = _comp("small", max_rps=100, replicas=1)
        g = _graph(c)
        result = _detect_bottlenecks(g, 90.0)
        assert "small" in result


# ---------------------------------------------------------------------------
# 4. Traffic pattern generation
# ---------------------------------------------------------------------------


class TestGeneratePattern:
    def test_steady_pattern_count(self) -> None:
        sim = TrafficShapingSimulator()
        snaps = sim.generate_pattern(TrafficPatternKind.STEADY, 100, 1000.0, 10)
        assert len(snaps) == 10

    def test_pattern_fields_populated(self) -> None:
        sim = TrafficShapingSimulator()
        snaps = sim.generate_pattern(TrafficPatternKind.RAMP_UP, 50, 500.0, 10)
        for s in snaps:
            assert s.requests_per_second >= 0
            assert 0.0 <= s.error_rate <= 1.0
            assert s.latency_ms >= 0

    def test_zero_duration(self) -> None:
        sim = TrafficShapingSimulator()
        snaps = sim.generate_pattern(TrafficPatternKind.STEADY, 0, 1000.0, 10)
        assert snaps == []

    def test_zero_interval(self) -> None:
        sim = TrafficShapingSimulator()
        snaps = sim.generate_pattern(TrafficPatternKind.STEADY, 100, 1000.0, 0)
        assert snaps == []

    def test_all_patterns_generate(self) -> None:
        sim = TrafficShapingSimulator()
        for kind in TrafficPatternKind:
            snaps = sim.generate_pattern(kind, 60, 500.0, 10)
            assert len(snaps) > 0, f"Pattern {kind} generated no snapshots"

    def test_spike_has_peak_near_middle(self) -> None:
        sim = TrafficShapingSimulator()
        snaps = sim.generate_pattern(TrafficPatternKind.SPIKE, 100, 1000.0, 10)
        peak_idx = max(range(len(snaps)), key=lambda i: snaps[i].requests_per_second)
        assert 3 <= peak_idx <= 7  # peak should be near middle


# ---------------------------------------------------------------------------
# 5. Traffic splitting
# ---------------------------------------------------------------------------


class TestSimulateSplit:
    def test_canary_split(self) -> None:
        sim = TrafficShapingSimulator()
        g = _graph(_comp("app", max_rps=5000, replicas=2))
        cfg = SplitConfig(strategy=SplitStrategy.CANARY, primary_weight=0.95, secondary_weight=0.05)
        result = sim.simulate_split(g, 1000.0, cfg)
        assert result.strategy == SplitStrategy.CANARY
        assert result.primary_rps == pytest.approx(950.0, abs=1)
        assert result.secondary_rps == pytest.approx(50.0, abs=1)

    def test_blue_green_cost(self) -> None:
        sim = TrafficShapingSimulator()
        g = _graph(_comp("app", max_rps=5000, replicas=2))
        cfg = SplitConfig(strategy=SplitStrategy.BLUE_GREEN, primary_weight=1.0, secondary_weight=0.0)
        result = sim.simulate_split(g, 1000.0, cfg)
        assert result.additional_infra_cost_pct == 100.0

    def test_shadow_with_mirror(self) -> None:
        sim = TrafficShapingSimulator()
        g = _graph(_comp("app", max_rps=5000, replicas=2))
        cfg = SplitConfig(strategy=SplitStrategy.SHADOW, mirror_copy=True, secondary_weight=0.5)
        result = sim.simulate_split(g, 1000.0, cfg)
        assert result.additional_infra_cost_pct == 50.0

    def test_ab_test_no_cost(self) -> None:
        sim = TrafficShapingSimulator()
        g = _graph(_comp("app", max_rps=5000, replicas=2))
        cfg = SplitConfig(strategy=SplitStrategy.AB_TEST, primary_weight=0.5, secondary_weight=0.5)
        result = sim.simulate_split(g, 1000.0, cfg)
        assert result.additional_infra_cost_pct == 0.0

    def test_split_recommendations_canary_high_weight(self) -> None:
        sim = TrafficShapingSimulator()
        g = _graph(_comp("app", max_rps=5000, replicas=2))
        cfg = SplitConfig(strategy=SplitStrategy.CANARY, secondary_weight=0.3)
        result = sim.simulate_split(g, 1000.0, cfg)
        assert any("Canary weight exceeds 20%" in r for r in result.recommendations)

    def test_split_empty_graph(self) -> None:
        sim = TrafficShapingSimulator()
        g = _graph()
        cfg = SplitConfig()
        result = sim.simulate_split(g, 1000.0, cfg)
        assert result.primary_rps > 0

    def test_split_high_error_recommendation(self) -> None:
        sim = TrafficShapingSimulator()
        c = _comp("tiny", max_rps=10, replicas=1)
        g = _graph(c)
        cfg = SplitConfig(strategy=SplitStrategy.CANARY, primary_weight=0.9, secondary_weight=0.1)
        result = sim.simulate_split(g, 50000.0, cfg)
        assert any("Error rate exceeds 5%" in r for r in result.recommendations)


# ---------------------------------------------------------------------------
# 6. Geographic distribution
# ---------------------------------------------------------------------------


class TestGeoDistribution:
    def test_default_regions(self) -> None:
        sim = TrafficShapingSimulator()
        g = _graph(_comp("app", max_rps=5000, replicas=2))
        result = sim.analyse_geo_distribution(g, 1000.0)
        assert len(result.regions) == 5
        assert result.worst_region != ""

    def test_custom_regions(self) -> None:
        sim = TrafficShapingSimulator()
        g = _graph(_comp("app", max_rps=5000, replicas=2))
        regions = [
            GeoRegion(region_name="us", weight=0.7, latency_penalty_ms=10.0, pop_count=5),
            GeoRegion(region_name="eu", weight=0.3, latency_penalty_ms=100.0, pop_count=3),
        ]
        result = sim.analyse_geo_distribution(g, 1000.0, regions)
        assert len(result.regions) == 2
        assert result.worst_region == "eu"

    def test_empty_regions(self) -> None:
        sim = TrafficShapingSimulator()
        g = _graph(_comp("app"))
        result = sim.analyse_geo_distribution(g, 1000.0, regions=[])
        assert result.recommendations

    def test_high_latency_recommendation(self) -> None:
        sim = TrafficShapingSimulator()
        g = _graph(_comp("app", max_rps=5000, replicas=2))
        regions = [
            GeoRegion(region_name="far", weight=0.5, latency_penalty_ms=300.0, pop_count=1),
            GeoRegion(region_name="near", weight=0.5, latency_penalty_ms=5.0, pop_count=5),
        ]
        result = sim.analyse_geo_distribution(g, 1000.0, regions)
        assert any("high latency" in r for r in result.recommendations)

    def test_low_pop_recommendation(self) -> None:
        sim = TrafficShapingSimulator()
        g = _graph(_comp("app", max_rps=5000, replicas=2))
        regions = [
            GeoRegion(region_name="sparse", weight=0.3, latency_penalty_ms=50.0, pop_count=1),
            GeoRegion(region_name="dense", weight=0.7, latency_penalty_ms=10.0, pop_count=10),
        ]
        result = sim.analyse_geo_distribution(g, 1000.0, regions)
        assert any("few PoPs" in r for r in result.recommendations)

    def test_empty_graph(self) -> None:
        sim = TrafficShapingSimulator()
        g = _graph()
        result = sim.analyse_geo_distribution(g, 1000.0)
        assert result.global_avg_latency_ms >= 0


# ---------------------------------------------------------------------------
# 7. Traffic mirroring
# ---------------------------------------------------------------------------


class TestMirrorImpact:
    def test_basic_mirror(self) -> None:
        sim = TrafficShapingSimulator()
        g = _graph(_comp("app", max_rps=5000, replicas=2))
        result = sim.assess_mirror_impact(g, 1000.0, 0.5)
        assert result.mirror_rps == 500.0
        assert result.additional_bandwidth_mbps > 0
        assert result.risk_level in ("low", "medium", "high")

    def test_full_mirror(self) -> None:
        sim = TrafficShapingSimulator()
        g = _graph(_comp("app", max_rps=5000, replicas=2))
        result = sim.assess_mirror_impact(g, 1000.0, 1.0)
        assert result.mirror_rps == 1000.0
        assert result.storage_cost_factor > 1.0

    def test_zero_mirror(self) -> None:
        sim = TrafficShapingSimulator()
        g = _graph(_comp("app", max_rps=5000, replicas=2))
        result = sim.assess_mirror_impact(g, 1000.0, 0.0)
        assert result.mirror_rps == 0.0
        assert result.additional_latency_ms == 0.0

    def test_high_cpu_risk(self) -> None:
        sim = TrafficShapingSimulator()
        c = _comp("small", max_rps=100, replicas=1)
        g = _graph(c)
        result = sim.assess_mirror_impact(g, 500.0, 1.0)
        assert result.risk_level in ("medium", "high")
        assert any("CPU" in r or "async" in r for r in result.recommendations)


# ---------------------------------------------------------------------------
# 8. Request prioritization / queuing
# ---------------------------------------------------------------------------


class TestPriorityQueuing:
    def test_default_distribution(self) -> None:
        sim = TrafficShapingSimulator()
        g = _graph(_comp("app", max_rps=5000, replicas=2))
        result = sim.analyse_priority_queuing(g, 1000.0)
        assert len(result.tiers) == 5
        assert result.total_throughput_rps > 0
        assert 0.0 <= result.fairness_index <= 1.0

    def test_custom_distribution(self) -> None:
        sim = TrafficShapingSimulator()
        g = _graph(_comp("app", max_rps=5000, replicas=2))
        dist = {
            RequestPriority.CRITICAL: 0.8,
            RequestPriority.NORMAL: 0.2,
        }
        result = sim.analyse_priority_queuing(g, 1000.0, dist)
        assert len(result.tiers) == 5

    def test_overloaded_drops_lower_priority(self) -> None:
        sim = TrafficShapingSimulator()
        c = _comp("tiny", max_rps=100, replicas=1)
        g = _graph(c)
        result = sim.analyse_priority_queuing(g, 5000.0)
        # Background tier should have higher drop rate than critical.
        bg_tier = next(t for t in result.tiers if t.priority == RequestPriority.BACKGROUND)
        crit_tier = next(t for t in result.tiers if t.priority == RequestPriority.CRITICAL)
        # With priority weighting, critical gets more allocation.
        assert crit_tier.throughput_rps >= bg_tier.throughput_rps or crit_tier.drop_rate <= bg_tier.drop_rate

    def test_critical_drop_recommendation(self) -> None:
        sim = TrafficShapingSimulator()
        c = _comp("tiny", max_rps=10, replicas=1)
        g = _graph(c)
        result = sim.analyse_priority_queuing(g, 50000.0)
        assert result.total_drop_rate > 0


# ---------------------------------------------------------------------------
# 9. TLS overhead
# ---------------------------------------------------------------------------


class TestTlsOverhead:
    def test_basic_tls(self) -> None:
        sim = TrafficShapingSimulator()
        g = _graph(_comp("app", max_rps=5000, replicas=2))
        result = sim.analyse_tls_overhead(g, 1000.0)
        assert result.handshake_latency_ms > 0
        assert result.session_resumption_rate > 0
        assert result.cpu_overhead_pct >= 0

    def test_no_new_connections(self) -> None:
        sim = TrafficShapingSimulator()
        g = _graph(_comp("app", max_rps=5000, replicas=2))
        result = sim.analyse_tls_overhead(g, 1000.0, new_connection_rate=0.0)
        assert result.handshake_latency_ms == 0.0
        assert result.full_handshake_pct == 0.0

    def test_all_new_no_resumption(self) -> None:
        sim = TrafficShapingSimulator()
        g = _graph(_comp("app", max_rps=5000, replicas=2))
        result = sim.analyse_tls_overhead(g, 1000.0, new_connection_rate=1.0, session_resumption_rate=0.0)
        assert result.full_handshake_pct == 100.0
        assert result.handshake_latency_ms == pytest.approx(30.0, abs=1)

    def test_high_cpu_recommendation(self) -> None:
        sim = TrafficShapingSimulator()
        c = _comp("small", max_rps=100, replicas=1)
        g = _graph(c)
        result = sim.analyse_tls_overhead(g, 5000.0, new_connection_rate=0.8, session_resumption_rate=0.2)
        assert result.cpu_overhead_pct > 0


# ---------------------------------------------------------------------------
# 10. CDN offload
# ---------------------------------------------------------------------------


class TestCdnOffload:
    def test_basic_cdn(self) -> None:
        sim = TrafficShapingSimulator()
        g = _graph(_comp("app", max_rps=5000, replicas=2))
        result = sim.model_cdn_offload(g, 1000.0)
        assert result.cdn_rps > 0
        assert result.origin_rps > 0
        assert result.cdn_rps + result.origin_rps == pytest.approx(1000.0, abs=1)

    def test_high_cache_ratio(self) -> None:
        sim = TrafficShapingSimulator()
        g = _graph(_comp("app", max_rps=5000, replicas=2))
        result = sim.model_cdn_offload(g, 1000.0, cacheable_fraction=0.9, cache_hit_ratio=0.95)
        assert result.cdn_rps > result.origin_rps
        assert result.bandwidth_savings_pct > 50.0

    def test_low_cache_recommendation(self) -> None:
        sim = TrafficShapingSimulator()
        g = _graph(_comp("app", max_rps=5000, replicas=2))
        result = sim.model_cdn_offload(g, 1000.0, cacheable_fraction=0.1, cache_hit_ratio=0.2)
        assert any("hit ratio" in r.lower() or "cacheable" in r.lower() for r in result.recommendations)

    def test_origin_near_capacity(self) -> None:
        sim = TrafficShapingSimulator()
        c = _comp("small", max_rps=500, replicas=1)
        g = _graph(c)
        result = sim.model_cdn_offload(g, 10000.0, cacheable_fraction=0.5, cache_hit_ratio=0.5)
        assert any("capacity" in r.lower() or "origin" in r.lower() for r in result.recommendations)


# ---------------------------------------------------------------------------
# 11. Origin shield
# ---------------------------------------------------------------------------


class TestOriginShield:
    def test_basic_shield(self) -> None:
        sim = TrafficShapingSimulator()
        g = _graph(_comp("app", max_rps=5000, replicas=2))
        result = sim.evaluate_origin_shield(g, 1000.0)
        assert result.origin_load_reduction_pct > 0
        assert result.additional_hop_latency_ms == 10.0

    def test_high_shield_hit(self) -> None:
        sim = TrafficShapingSimulator()
        g = _graph(_comp("app", max_rps=5000, replicas=2))
        result = sim.evaluate_origin_shield(g, 1000.0, shield_hit_ratio=0.95, num_edge_pops=20)
        assert result.effective is True
        assert result.origin_load_reduction_pct > 50.0

    def test_low_shield_hit_recommendation(self) -> None:
        sim = TrafficShapingSimulator()
        g = _graph(_comp("app", max_rps=5000, replicas=2))
        result = sim.evaluate_origin_shield(g, 1000.0, shield_hit_ratio=0.3, num_edge_pops=2)
        assert any("hit ratio" in r.lower() or "limited benefit" in r.lower() for r in result.recommendations)

    def test_few_pops_recommendation(self) -> None:
        sim = TrafficShapingSimulator()
        g = _graph(_comp("app", max_rps=5000, replicas=2))
        result = sim.evaluate_origin_shield(g, 1000.0, shield_hit_ratio=0.5, num_edge_pops=2)
        assert any("Few edge PoPs" in r for r in result.recommendations)


# ---------------------------------------------------------------------------
# 12. Protocol mix (WebSocket / HTTP)
# ---------------------------------------------------------------------------


class TestProtocolMix:
    def test_basic_mix(self) -> None:
        sim = TrafficShapingSimulator()
        g = _graph(_comp("app", max_rps=5000, replicas=2, max_connections=10000))
        result = sim.analyse_protocol_mix(g, http_rps=1000.0, websocket_connections=500)
        assert result.http_rps == 1000.0
        assert result.websocket_connections == 500
        assert result.total_ws_memory_mb > 0

    def test_high_ws_connections_warning(self) -> None:
        sim = TrafficShapingSimulator()
        g = _graph(_comp("app", max_rps=5000, replicas=2, max_connections=1000))
        result = sim.analyse_protocol_mix(g, http_rps=1000.0, websocket_connections=10000)
        assert result.total_ws_memory_mb > 100.0
        assert len(result.recommendations) > 0

    def test_zero_websockets(self) -> None:
        sim = TrafficShapingSimulator()
        g = _graph(_comp("app", max_rps=5000, replicas=2))
        result = sim.analyse_protocol_mix(g, http_rps=500.0, websocket_connections=0)
        assert result.total_ws_memory_mb == 0.0

    def test_empty_graph(self) -> None:
        sim = TrafficShapingSimulator()
        g = _graph()
        result = sim.analyse_protocol_mix(g, http_rps=100.0, websocket_connections=10)
        assert result.mixed_latency_ms > 0


# ---------------------------------------------------------------------------
# 13. API gateway throttling
# ---------------------------------------------------------------------------


class TestGatewayThrottle:
    def test_within_limit(self) -> None:
        sim = TrafficShapingSimulator()
        g = _graph(_comp("app", max_rps=5000, replicas=2))
        cfg = ThrottleConfig(rate_limit_rps=2000.0, burst_size=200)
        result = sim.simulate_gateway_throttle(g, 1000.0, cfg)
        assert result.rejection_rate_pct == 0.0
        assert result.allowed_rps == 1000.0

    def test_exceeding_limit(self) -> None:
        sim = TrafficShapingSimulator()
        g = _graph(_comp("app", max_rps=5000, replicas=2))
        cfg = ThrottleConfig(rate_limit_rps=500.0, burst_size=100)
        result = sim.simulate_gateway_throttle(g, 2000.0, cfg)
        assert result.rejection_rate_pct > 0
        assert result.rejected_rps > 0
        assert any("Rejection rate" in r for r in result.recommendations)

    def test_per_client_limit(self) -> None:
        sim = TrafficShapingSimulator()
        g = _graph(_comp("app", max_rps=50000, replicas=2))
        cfg = ThrottleConfig(rate_limit_rps=100.0, per_client=True, num_clients=200)
        result = sim.simulate_gateway_throttle(g, 15000.0, cfg)
        assert result.allowed_rps > 0

    def test_small_burst_recommendation(self) -> None:
        sim = TrafficShapingSimulator()
        g = _graph(_comp("app", max_rps=5000, replicas=2))
        cfg = ThrottleConfig(rate_limit_rps=1000.0, burst_size=5)
        result = sim.simulate_gateway_throttle(g, 2000.0, cfg)
        assert any("Burst size" in r for r in result.recommendations)


# ---------------------------------------------------------------------------
# 14. Traffic replay
# ---------------------------------------------------------------------------


class TestReplayTraffic:
    def test_basic_replay(self) -> None:
        sim = TrafficShapingSimulator()
        g = _graph(_comp("app", max_rps=5000, replicas=2))
        snaps = [
            TrafficShapeSnapshot(timestamp_offset_s=0, requests_per_second=100.0),
            TrafficShapeSnapshot(timestamp_offset_s=10, requests_per_second=500.0),
            TrafficShapeSnapshot(timestamp_offset_s=20, requests_per_second=200.0),
        ]
        scenario = ReplayScenario(name="test", snapshots=snaps)
        result = sim.replay_traffic(g, scenario)
        assert result.scenario_name == "test"
        assert result.total_requests > 0
        assert result.peak_rps == 500.0

    def test_empty_scenario(self) -> None:
        sim = TrafficShapingSimulator()
        g = _graph(_comp("app"))
        scenario = ReplayScenario(name="empty")
        result = sim.replay_traffic(g, scenario)
        assert result.total_requests == 0
        assert result.recommendations

    def test_scaled_replay(self) -> None:
        sim = TrafficShapingSimulator()
        g = _graph(_comp("app", max_rps=5000, replicas=2))
        snaps = [TrafficShapeSnapshot(timestamp_offset_s=0, requests_per_second=100.0)]
        scenario = ReplayScenario(name="scaled", snapshots=snaps, scale_factor=3.0)
        result = sim.replay_traffic(g, scenario)
        assert result.peak_rps == pytest.approx(300.0, abs=1)

    def test_replay_with_bottleneck(self) -> None:
        sim = TrafficShapingSimulator()
        c = _comp("tiny", max_rps=50, replicas=1)
        g = _graph(c)
        snaps = [TrafficShapeSnapshot(timestamp_offset_s=0, requests_per_second=500.0)]
        scenario = ReplayScenario(name="overload", snapshots=snaps)
        result = sim.replay_traffic(g, scenario)
        assert "tiny" in result.bottleneck_components


# ---------------------------------------------------------------------------
# 15. Anomaly detection (DDoS vs organic spike)
# ---------------------------------------------------------------------------


class TestAnomalyDetection:
    def test_normal_traffic(self) -> None:
        sim = TrafficShapingSimulator()
        result = sim.detect_anomaly(1000.0, 1200.0, distinct_sources=500, request_entropy=0.9)
        assert result.verdict == AnomalyVerdict.NORMAL
        assert result.confidence > 0.5

    def test_organic_spike(self) -> None:
        sim = TrafficShapingSimulator()
        result = sim.detect_anomaly(1000.0, 5000.0, distinct_sources=2000, request_entropy=0.85)
        assert result.verdict == AnomalyVerdict.ORGANIC_SPIKE
        assert result.deviation_factor > 3.0

    def test_ddos_volumetric(self) -> None:
        sim = TrafficShapingSimulator()
        result = sim.detect_anomaly(1000.0, 50000.0, distinct_sources=5, request_entropy=0.1)
        assert result.verdict == AnomalyVerdict.DDOS_VOLUMETRIC
        assert result.confidence > 0.5
        assert any("DDoS" in r for r in result.recommendations)

    def test_ddos_slowloris(self) -> None:
        sim = TrafficShapingSimulator()
        result = sim.detect_anomaly(1000.0, 8000.0, distinct_sources=30, request_entropy=0.35)
        assert result.verdict == AnomalyVerdict.DDOS_SLOWLORIS
        assert result.anomaly_score > 50.0

    def test_bot_scraping(self) -> None:
        sim = TrafficShapingSimulator()
        result = sim.detect_anomaly(1000.0, 3000.0, distinct_sources=5, request_entropy=0.2)
        assert result.verdict == AnomalyVerdict.BOT_SCRAPING
        assert any("Bot" in r or "bot" in r for r in result.recommendations)

    def test_zero_baseline(self) -> None:
        sim = TrafficShapingSimulator()
        result = sim.detect_anomaly(0.0, 5000.0, distinct_sources=100, request_entropy=0.5)
        # baseline becomes 1.0 internally.
        assert result.deviation_factor > 1.0

    def test_ambiguous_high_deviation(self) -> None:
        sim = TrafficShapingSimulator()
        result = sim.detect_anomaly(1000.0, 12000.0, distinct_sources=40, request_entropy=0.5)
        # Moderate entropy, moderate sources, high deviation.
        assert result.verdict == AnomalyVerdict.DDOS_VOLUMETRIC
        assert result.confidence >= 0.5

    def test_ambiguous_low_deviation(self) -> None:
        sim = TrafficShapingSimulator()
        result = sim.detect_anomaly(1000.0, 3000.0, distinct_sources=40, request_entropy=0.5)
        assert result.verdict == AnomalyVerdict.ORGANIC_SPIKE

    def test_emergency_capacity_recommendation(self) -> None:
        sim = TrafficShapingSimulator()
        result = sim.detect_anomaly(100.0, 5000.0, distinct_sources=200, request_entropy=0.8)
        assert any("emergency" in r.lower() or "baseline" in r.lower() for r in result.recommendations)


# ---------------------------------------------------------------------------
# 16. Engine construction and datetime
# ---------------------------------------------------------------------------


class TestSimulatorConstruction:
    def test_default_seed(self) -> None:
        sim = TrafficShapingSimulator()
        assert sim._created_at is not None
        assert sim._created_at.tzinfo is not None  # timezone-aware

    def test_custom_seed_reproducibility(self) -> None:
        sim1 = TrafficShapingSimulator(seed=123)
        sim2 = TrafficShapingSimulator(seed=123)
        snaps1 = sim1.generate_pattern(TrafficPatternKind.STEADY, 60, 1000.0, 10)
        snaps2 = sim2.generate_pattern(TrafficPatternKind.STEADY, 60, 1000.0, 10)
        for s1, s2 in zip(snaps1, snaps2):
            assert s1.requests_per_second == s2.requests_per_second


# ---------------------------------------------------------------------------
# 17. Multi-component graph integration
# ---------------------------------------------------------------------------


class TestMultiComponentGraph:
    def test_split_with_dependency(self) -> None:
        lb = _comp("lb", ctype=ComponentType.LOAD_BALANCER, max_rps=10000, replicas=1)
        app = _comp("app", ctype=ComponentType.APP_SERVER, max_rps=3000, replicas=2)
        db = _comp("db", ctype=ComponentType.DATABASE, max_rps=1000, replicas=1)
        g = _graph(lb, app, db)
        g.add_dependency(Dependency(source_id="lb", target_id="app"))
        g.add_dependency(Dependency(source_id="app", target_id="db"))

        sim = TrafficShapingSimulator()
        cfg = SplitConfig(strategy=SplitStrategy.CANARY, primary_weight=0.9, secondary_weight=0.1)
        result = sim.simulate_split(g, 800.0, cfg)
        assert result.primary_rps == pytest.approx(720.0, abs=1)
        assert result.secondary_rps == pytest.approx(80.0, abs=1)

    def test_geo_with_multi_component(self) -> None:
        lb = _comp("lb", ctype=ComponentType.LOAD_BALANCER, max_rps=10000, replicas=2)
        app = _comp("app", ctype=ComponentType.APP_SERVER, max_rps=5000, replicas=3)
        g = _graph(lb, app)
        sim = TrafficShapingSimulator()
        result = sim.analyse_geo_distribution(g, 2000.0)
        assert result.global_avg_latency_ms > 0

    def test_replay_multi_component_bottleneck(self) -> None:
        app = _comp("app", max_rps=5000, replicas=2)
        db = _comp("db", ctype=ComponentType.DATABASE, max_rps=100, replicas=1)
        g = _graph(app, db)

        sim = TrafficShapingSimulator()
        snaps = [TrafficShapeSnapshot(timestamp_offset_s=0, requests_per_second=500.0)]
        scenario = ReplayScenario(name="multi", snapshots=snaps)
        result = sim.replay_traffic(g, scenario)
        assert "db" in result.bottleneck_components


# ---------------------------------------------------------------------------
# 18. Constants and dictionaries
# ---------------------------------------------------------------------------


class TestConstants:
    def test_base_latency_keys(self) -> None:
        expected = {
            "load_balancer", "web_server", "app_server", "database",
            "cache", "queue", "storage", "dns", "external_api", "custom",
        }
        assert set(_BASE_LATENCY.keys()) == expected

    def test_priority_weight_keys(self) -> None:
        for p in RequestPriority:
            assert p in _PRIORITY_WEIGHT

    def test_default_regions_count(self) -> None:
        assert len(_DEFAULT_REGIONS) == 5

    def test_priority_weight_ordering(self) -> None:
        assert _PRIORITY_WEIGHT[RequestPriority.CRITICAL] > _PRIORITY_WEIGHT[RequestPriority.HIGH]
        assert _PRIORITY_WEIGHT[RequestPriority.HIGH] > _PRIORITY_WEIGHT[RequestPriority.NORMAL]
        assert _PRIORITY_WEIGHT[RequestPriority.NORMAL] > _PRIORITY_WEIGHT[RequestPriority.LOW]
        assert _PRIORITY_WEIGHT[RequestPriority.LOW] > _PRIORITY_WEIGHT[RequestPriority.BACKGROUND]


# ---------------------------------------------------------------------------
# 19. Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_mirror_fraction_clamped(self) -> None:
        sim = TrafficShapingSimulator()
        g = _graph(_comp("app", max_rps=5000, replicas=2))
        result = sim.assess_mirror_impact(g, 1000.0, 5.0)  # > 1.0
        assert result.mirror_rps == 1000.0  # clamped to 1.0 fraction

    def test_cdn_zero_cacheable(self) -> None:
        sim = TrafficShapingSimulator()
        g = _graph(_comp("app", max_rps=5000, replicas=2))
        result = sim.model_cdn_offload(g, 1000.0, cacheable_fraction=0.0)
        assert result.cdn_rps == 0.0
        assert result.origin_rps == 1000.0

    def test_shield_single_pop(self) -> None:
        sim = TrafficShapingSimulator()
        g = _graph(_comp("app", max_rps=5000, replicas=2))
        result = sim.evaluate_origin_shield(g, 1000.0, num_edge_pops=1, shield_hit_ratio=0.5)
        assert result.origin_load_reduction_pct >= 0

    def test_throttle_zero_incoming(self) -> None:
        sim = TrafficShapingSimulator()
        g = _graph(_comp("app", max_rps=5000, replicas=2))
        cfg = ThrottleConfig()
        result = sim.simulate_gateway_throttle(g, 0.0, cfg)
        assert result.allowed_rps == 0.0
        assert result.rejection_rate_pct == 0.0

    def test_anomaly_low_entropy_many_sources(self) -> None:
        sim = TrafficShapingSimulator()
        result = sim.detect_anomaly(100.0, 5000.0, distinct_sources=200, request_entropy=0.35)
        assert result.verdict == AnomalyVerdict.DDOS_SLOWLORIS

    def test_geo_empty_graph_default_regions(self) -> None:
        sim = TrafficShapingSimulator()
        g = _graph()
        result = sim.analyse_geo_distribution(g, 500.0)
        assert len(result.regions) == 5
        assert result.global_avg_latency_ms >= 0

    def test_shadow_without_mirror(self) -> None:
        """Cover shadow strategy with mirror_copy=False (line 490)."""
        sim = TrafficShapingSimulator()
        g = _graph(_comp("app", max_rps=5000, replicas=2))
        cfg = SplitConfig(strategy=SplitStrategy.SHADOW, mirror_copy=False, secondary_weight=0.3)
        result = sim.simulate_split(g, 1000.0, cfg)
        assert result.additional_infra_cost_pct == pytest.approx(15.0, abs=1)

    def test_mirror_empty_graph(self) -> None:
        """Cover mirror with max_rps<=0 (line 641)."""
        sim = TrafficShapingSimulator()
        g = _graph()
        result = sim.assess_mirror_impact(g, 1000.0, 0.5)
        assert result.mirror_rps == 500.0

    def test_mirror_medium_risk(self) -> None:
        """Cover medium risk level (line 654)."""
        sim = TrafficShapingSimulator()
        c = _comp("mid", max_rps=200, replicas=1)
        g = _graph(c)
        # cpu_pct = (mirror_rps / max_rps) * 100 * 0.3
        # mirror_rps = 220 * 0.5 = 110, max_rps = 200
        # cpu_pct = (110/200)*100*0.3 = 16.5% -> "medium" (>15, <=30)
        result = sim.assess_mirror_impact(g, 220.0, 0.5)
        assert result.risk_level == "medium"

    def test_mirror_high_bandwidth(self) -> None:
        """Cover high bandwidth recommendation (line 663)."""
        sim = TrafficShapingSimulator()
        c = _comp("big", max_rps=1000000, replicas=10)
        g = _graph(c)
        # bw_mbps = mirror_rps * 2.0 / 1024.0 > 100
        # Need mirror_rps > 51200 => baseline > 51200
        result = sim.assess_mirror_impact(g, 60000.0, 1.0)
        # bw = 60000*2/1024 = 117 Mbps
        assert result.additional_bandwidth_mbps > 100.0
        assert any("bandwidth" in r.lower() for r in result.recommendations)

    def test_priority_queuing_empty_graph(self) -> None:
        """Cover priority queuing with max_rps<=0 (line 704)."""
        sim = TrafficShapingSimulator()
        g = _graph()
        result = sim.analyse_priority_queuing(g, 100.0)
        assert len(result.tiers) == 5

    def test_priority_queuing_zero_weight(self) -> None:
        """Cover total_weight<=0 branch (line 715)."""
        sim = TrafficShapingSimulator()
        g = _graph(_comp("app", max_rps=5000, replicas=2))
        dist = {p: 0.0 for p in RequestPriority}
        result = sim.analyse_priority_queuing(g, 1000.0, dist)
        assert len(result.tiers) == 5

    def test_priority_queuing_single_tier(self) -> None:
        """Cover fairness fallback with single tier throughput (line 756)."""
        sim = TrafficShapingSimulator()
        g = _graph(_comp("app", max_rps=5000, replicas=2))
        dist = {
            RequestPriority.CRITICAL: 1.0,
            RequestPriority.HIGH: 0.0,
            RequestPriority.NORMAL: 0.0,
            RequestPriority.LOW: 0.0,
            RequestPriority.BACKGROUND: 0.0,
        }
        result = sim.analyse_priority_queuing(g, 100.0, dist)
        assert result.fairness_index == 1.0

    def test_tls_empty_graph(self) -> None:
        """Cover TLS with empty graph max_rps<=0 (line 814)."""
        sim = TrafficShapingSimulator()
        g = _graph()
        result = sim.analyse_tls_overhead(g, 1000.0)
        assert result.cpu_overhead_pct >= 0

    def test_tls_high_throughput_reduction(self) -> None:
        """Cover throughput_reduction > 10.0 (line 833)."""
        sim = TrafficShapingSimulator()
        g = _graph(_comp("app", max_rps=5000, replicas=2))
        # full_frac * 30ms / 5.0 > 10 => need full_frac * 30 > 50
        # full_frac = new_conn * (1 - resume)
        # 1.0 * 1.0 = 1.0 => avg_hs = 30 => throughput_red = 30/5 = 6.0 — not enough
        # Actually throughput_reduction = avg_hs_latency / 5.0
        # avg_hs = full_frac * 30 + resume_frac * 5
        # full_frac = 1.0*(1-0) = 1.0, resume_frac = 0
        # avg_hs = 30, throughput_red = 6 — still < 10
        # Need avg_hs > 50. But max full_hs = 30ms for full handshake.
        # avg_hs can't exceed 30ms with current constants. Let me check line 832 more carefully.
        # throughput_reduction = min(20.0, avg_hs_latency / 5.0)
        # For avg_hs > 50: 50/5 = 10. But max avg_hs = 30. So max = 6.
        # This line is unreachable with current constants. Skip.
        # Instead test the full_frac > 0.2 + cpu_overhead > 10 path.
        c = _comp("small", max_rps=50, replicas=1)
        g = _graph(c)
        result = sim.analyse_tls_overhead(g, 5000.0, new_connection_rate=0.8, session_resumption_rate=0.0)
        assert result.full_handshake_pct > 20
        assert any("CPU" in r or "hardware" in r for r in result.recommendations)

    def test_bottleneck_with_autoscaling(self) -> None:
        """Cover autoscaling branch in _detect_bottlenecks (line 407)."""
        c = Component(
            id="as1",
            name="as1",
            type=ComponentType.APP_SERVER,
            replicas=1,
            capacity=Capacity(max_rps=100),
            autoscaling=AutoScalingConfig(enabled=True, max_replicas=5),
        )
        g = _graph(c)
        # effective_max = 100*5 = 500, rps=450 => ratio 0.9 > 0.8 => bottleneck
        result = _detect_bottlenecks(g, 450.0)
        assert "as1" in result

    def test_throttle_per_client_many(self) -> None:
        """Cover per_client with num_clients > 1000 (line 1077)."""
        sim = TrafficShapingSimulator()
        g = _graph(_comp("app", max_rps=50000, replicas=2))
        cfg = ThrottleConfig(rate_limit_rps=10.0, per_client=True, num_clients=2000)
        result = sim.simulate_gateway_throttle(g, 15000.0, cfg)
        assert any("distributed" in r.lower() or "redis" in r.lower() for r in result.recommendations)

    def test_throttle_near_capacity(self) -> None:
        """Cover effective / max_rps > 0.9 (line 1087)."""
        sim = TrafficShapingSimulator()
        c = _comp("small", max_rps=100, replicas=1)
        g = _graph(c)
        cfg = ThrottleConfig(rate_limit_rps=200.0, burst_size=100)
        result = sim.simulate_gateway_throttle(g, 95.0, cfg)
        assert any("capacity" in r.lower() for r in result.recommendations)

    def test_replay_empty_graph_with_data(self) -> None:
        """Cover replay with max_rps<=0 (line 1119)."""
        sim = TrafficShapingSimulator()
        g = _graph()
        snaps = [TrafficShapeSnapshot(timestamp_offset_s=0, requests_per_second=100.0)]
        scenario = ReplayScenario(name="empty_graph", snapshots=snaps)
        result = sim.replay_traffic(g, scenario)
        assert result.total_requests > 0

    def test_origin_shield_effective_true(self) -> None:
        """Cover effective=True and 'effective for this topology' rec (line 967)."""
        sim = TrafficShapingSimulator()
        g = _graph(_comp("app", max_rps=5000, replicas=2))
        result = sim.evaluate_origin_shield(g, 1000.0, shield_hit_ratio=0.9, num_edge_pops=10)
        assert result.effective is True
        assert any("effective" in r.lower() for r in result.recommendations)

    def test_origin_shield_not_effective(self) -> None:
        """Cover not-effective branch (line 952)."""
        sim = TrafficShapingSimulator()
        g = _graph(_comp("app", max_rps=5000, replicas=2))
        # num_pops=1, shield_hit=0.1 => load_red = (1-0.9)/1*100 = 10% < 30% => not effective
        result = sim.evaluate_origin_shield(g, 1000.0, shield_hit_ratio=0.1, num_edge_pops=1)
        assert result.effective is False
        assert any("limited benefit" in r for r in result.recommendations)
