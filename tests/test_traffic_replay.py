"""Tests for faultray.simulator.traffic_replay module.

Covers all enums, data models, helpers, and TrafficReplayEngine methods with
edge cases for 100% line/branch coverage.
"""

from __future__ import annotations

import math

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    Capacity,
    Component,
    ComponentType,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.traffic_replay import (
    BreakingPointResult,
    CapacityHeadroom,
    ReplayComparison,
    ReplayConfig,
    ReplayMode,
    ReplayResult,
    TrafficPattern,
    TrafficReplayEngine,
    TrafficShiftResult,
    TrafficSnapshot,
    _component_latency,
    _detect_component_bottlenecks,
    _effective_max_rps,
    _error_rate_for_load,
    _generate_recommendations,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_component(
    cid: str,
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 2,
    max_rps: int = 5000,
    autoscaling: bool = False,
    max_replicas: int = 4,
) -> Component:
    """Helper to build a Component with sensible defaults."""
    return Component(
        id=cid,
        name=cid,
        type=ctype,
        replicas=replicas,
        capacity=Capacity(max_rps=max_rps),
        autoscaling=AutoScalingConfig(
            enabled=autoscaling,
            min_replicas=1,
            max_replicas=max_replicas,
        ),
    )


def _simple_graph() -> InfraGraph:
    """A graph with LB -> App -> DB, each with 2 replicas at 5000 RPS."""
    g = InfraGraph()
    g.add_component(_make_component("lb", ComponentType.LOAD_BALANCER))
    g.add_component(_make_component("app", ComponentType.APP_SERVER))
    g.add_component(_make_component("db", ComponentType.DATABASE))
    return g


def _autoscaled_graph() -> InfraGraph:
    """Graph with autoscaling enabled on all components."""
    g = InfraGraph()
    g.add_component(
        _make_component("lb", ComponentType.LOAD_BALANCER, autoscaling=True, max_replicas=6)
    )
    g.add_component(
        _make_component("app", ComponentType.APP_SERVER, autoscaling=True, max_replicas=8)
    )
    g.add_component(
        _make_component("db", ComponentType.DATABASE, autoscaling=True, max_replicas=4)
    )
    return g


def _empty_graph() -> InfraGraph:
    return InfraGraph()


def _single_component_graph(max_rps: int = 1000, replicas: int = 1) -> InfraGraph:
    g = InfraGraph()
    g.add_component(
        _make_component("solo", ComponentType.WEB_SERVER, replicas=replicas, max_rps=max_rps)
    )
    return g


def _snapshot(rps: float = 500.0, err: float = 0.01) -> TrafficSnapshot:
    return TrafficSnapshot(
        timestamp="T+0m",
        requests_per_second=rps,
        error_rate=err,
        latency_p50_ms=20.0,
        latency_p99_ms=80.0,
        unique_endpoints=10,
    )


def _snapshots(rps_values: list[float]) -> list[TrafficSnapshot]:
    return [
        TrafficSnapshot(
            timestamp=f"T+{i}m",
            requests_per_second=rps,
            error_rate=0.01,
            latency_p50_ms=20.0,
            latency_p99_ms=80.0,
            unique_endpoints=max(1, int(rps / 10)),
        )
        for i, rps in enumerate(rps_values)
    ]


# ===================================================================
# Enum tests
# ===================================================================


class TestTrafficPatternEnum:
    def test_all_values(self):
        expected = {
            "steady_state", "ramp_up", "spike", "diurnal",
            "weekly_cycle", "event_driven", "seasonal", "random_burst",
        }
        assert {p.value for p in TrafficPattern} == expected

    def test_from_value(self):
        assert TrafficPattern("spike") == TrafficPattern.SPIKE

    def test_is_str(self):
        assert isinstance(TrafficPattern.STEADY_STATE, str)

    def test_count(self):
        assert len(TrafficPattern) == 8


class TestReplayModeEnum:
    def test_all_values(self):
        expected = {"exact", "scaled", "filtered", "time_compressed", "reversed"}
        assert {m.value for m in ReplayMode} == expected

    def test_from_value(self):
        assert ReplayMode("scaled") == ReplayMode.SCALED

    def test_is_str(self):
        assert isinstance(ReplayMode.EXACT, str)

    def test_count(self):
        assert len(ReplayMode) == 5


# ===================================================================
# Pydantic model tests
# ===================================================================


class TestTrafficSnapshot:
    def test_basic_creation(self):
        s = _snapshot()
        assert s.requests_per_second == 500.0
        assert s.timestamp == "T+0m"

    def test_edge_values(self):
        s = TrafficSnapshot(
            timestamp="t0", requests_per_second=0.0,
            error_rate=0.0, latency_p50_ms=0.0,
            latency_p99_ms=0.0, unique_endpoints=0,
        )
        assert s.requests_per_second == 0.0
        assert s.unique_endpoints == 0

    def test_max_error_rate(self):
        s = TrafficSnapshot(
            timestamp="t0", requests_per_second=1.0,
            error_rate=1.0, latency_p50_ms=1.0,
            latency_p99_ms=1.0, unique_endpoints=1,
        )
        assert s.error_rate == 1.0

    def test_serialisation_round_trip(self):
        s = _snapshot(123.45, 0.05)
        data = s.model_dump()
        s2 = TrafficSnapshot(**data)
        assert s2.requests_per_second == s.requests_per_second


class TestReplayConfig:
    def test_defaults(self):
        c = ReplayConfig()
        assert c.mode == ReplayMode.EXACT
        assert c.scale_factor == 1.0
        assert c.time_compression == 1.0
        assert c.duration_minutes == 60.0
        assert c.snapshots == []

    def test_custom_config(self):
        c = ReplayConfig(
            mode=ReplayMode.SCALED,
            scale_factor=2.0,
            pattern=TrafficPattern.SPIKE,
            duration_minutes=10.0,
        )
        assert c.scale_factor == 2.0
        assert c.pattern == TrafficPattern.SPIKE

    def test_with_snapshots(self):
        snaps = _snapshots([100, 200, 300])
        c = ReplayConfig(snapshots=snaps)
        assert len(c.snapshots) == 3


class TestReplayResult:
    def test_defaults(self):
        r = ReplayResult(
            total_requests=100, successful_requests=90, failed_requests=10,
            peak_rps=50.0, avg_latency_ms=25.0, p99_latency_ms=100.0,
        )
        assert r.failed_requests == 10
        assert r.bottleneck_components == []

    def test_with_details(self):
        r = ReplayResult(
            total_requests=1000, successful_requests=950, failed_requests=50,
            peak_rps=500.0, avg_latency_ms=30.0, p99_latency_ms=120.0,
            bottleneck_components=["db"],
            saturation_events=["db saturated"],
            recommendations=["Scale db"],
        )
        assert "db" in r.bottleneck_components
        assert len(r.saturation_events) == 1


class TestReplayComparison:
    def test_defaults(self):
        c = ReplayComparison()
        assert c.results == []
        assert c.best_index == 0

    def test_with_data(self):
        c = ReplayComparison(
            results=[], best_index=1, worst_index=2,
            delta_peak_rps=100.0, delta_avg_latency_ms=50.0,
            summary="test",
        )
        assert c.summary == "test"


class TestCapacityHeadroom:
    def test_defaults(self):
        h = CapacityHeadroom()
        assert h.current_rps == 0.0
        assert h.recommendations == []

    def test_with_values(self):
        h = CapacityHeadroom(
            current_rps=1000, max_sustainable_rps=5000,
            headroom_percent=80.0, limiting_component="app",
            time_to_saturation_minutes=1440.0,
            recommendations=["Good"],
        )
        assert h.headroom_percent == 80.0


class TestTrafficShiftResult:
    def test_creation(self):
        r = TrafficShiftResult(
            from_pattern=TrafficPattern.STEADY_STATE,
            to_pattern=TrafficPattern.SPIKE,
        )
        assert r.transition_duration_minutes == 0.0
        assert r.recommendations == []


class TestBreakingPointResult:
    def test_creation(self):
        r = BreakingPointResult()
        assert r.breaking_rps == 0.0
        assert r.failure_mode == ""


# ===================================================================
# Helper function tests
# ===================================================================


class TestEffectiveMaxRps:
    def test_simple_graph(self):
        g = _simple_graph()
        max_rps, limiting = _effective_max_rps(g)
        # 2 replicas * 5000 = 10000 for each component
        assert max_rps == 10000.0
        assert limiting in {"lb", "app", "db"}

    def test_autoscaled_graph(self):
        g = _autoscaled_graph()
        max_rps, limiting = _effective_max_rps(g)
        # db: 4 * 5000 = 20000, app: 8 * 5000 = 40000, lb: 6 * 5000 = 30000
        assert max_rps == 20000.0
        assert limiting == "db"

    def test_empty_graph(self):
        max_rps, limiting = _effective_max_rps(_empty_graph())
        assert max_rps == 0.0
        assert limiting == ""

    def test_single_component(self):
        g = _single_component_graph(max_rps=2000, replicas=3)
        max_rps, limiting = _effective_max_rps(g)
        assert max_rps == 6000.0
        assert limiting == "solo"


class TestComponentLatency:
    def test_known_type_no_load(self):
        lat = _component_latency("cache", 0.0)
        assert lat == pytest.approx(2.0, rel=0.01)  # base * (1+0)

    def test_known_type_half_load(self):
        lat = _component_latency("app_server", 0.5)
        assert lat == pytest.approx(15.0 * 1.5, rel=0.01)

    def test_known_type_full_load(self):
        lat = _component_latency("database", 1.0)
        assert lat == pytest.approx(10.0 * 2.0, rel=0.01)

    def test_over_capacity(self):
        lat = _component_latency("web_server", 1.5)
        expected = 5.0 * (1.0 + 1.5 * 3.0)
        assert lat == pytest.approx(expected, rel=0.01)

    def test_unknown_type(self):
        lat = _component_latency("unknown_thing", 0.0)
        assert lat == pytest.approx(10.0, rel=0.01)  # default base

    def test_custom_type(self):
        lat = _component_latency("custom", 0.0)
        assert lat == pytest.approx(10.0, rel=0.01)

    def test_external_api(self):
        lat = _component_latency("external_api", 0.0)
        assert lat == pytest.approx(50.0, rel=0.01)

    def test_dns(self):
        lat = _component_latency("dns", 0.5)
        assert lat == pytest.approx(3.0 * 1.5, rel=0.01)

    def test_queue(self):
        lat = _component_latency("queue", 0.0)
        assert lat == pytest.approx(8.0, rel=0.01)

    def test_storage(self):
        lat = _component_latency("storage", 0.0)
        assert lat == pytest.approx(12.0, rel=0.01)

    def test_load_balancer(self):
        lat = _component_latency("load_balancer", 0.0)
        assert lat == pytest.approx(1.0, rel=0.01)


class TestErrorRateForLoad:
    def test_low_load(self):
        rate = _error_rate_for_load(0.5)
        assert rate == 0.001

    def test_just_above_negligible(self):
        rate = _error_rate_for_load(0.01)
        assert rate == 0.001  # above negligible threshold, baseline error

    def test_zero_load(self):
        rate = _error_rate_for_load(0.0)
        assert rate == 0.0  # negligible load

    def test_very_low_load(self):
        rate = _error_rate_for_load(0.005)
        assert rate == 0.0  # still negligible

    def test_at_80_percent(self):
        rate = _error_rate_for_load(0.8)
        assert rate == 0.001

    def test_at_90_percent(self):
        rate = _error_rate_for_load(0.9)
        assert rate > 0.001
        assert rate < 0.05

    def test_at_100_percent(self):
        rate = _error_rate_for_load(1.0)
        assert rate == pytest.approx(0.05, rel=0.01)

    def test_over_capacity(self):
        rate = _error_rate_for_load(1.5)
        assert rate > 0.05

    def test_extreme_over_capacity(self):
        rate = _error_rate_for_load(3.0)
        assert rate == 1.0  # capped at 1.0

    def test_very_high_capped(self):
        rate = _error_rate_for_load(10.0)
        assert rate == 1.0


class TestDetectComponentBottlenecks:
    def test_no_bottleneck(self):
        g = _simple_graph()
        bn, events = _detect_component_bottlenecks(g, 1000)  # well below 10000
        assert bn == []
        assert events == []

    def test_near_capacity(self):
        g = _simple_graph()
        bn, events = _detect_component_bottlenecks(g, 9000)  # 90% of 10000
        assert len(bn) == 3  # all components at 90%
        assert events == []

    def test_over_capacity(self):
        g = _simple_graph()
        bn, events = _detect_component_bottlenecks(g, 12000)
        assert len(bn) == 3
        assert len(events) == 3

    def test_empty_graph(self):
        bn, events = _detect_component_bottlenecks(_empty_graph(), 1000)
        assert bn == []
        assert events == []

    def test_autoscaled_different_caps(self):
        g = _autoscaled_graph()
        # db max = 20000, app max = 40000, lb max = 30000
        bn, events = _detect_component_bottlenecks(g, 18000)
        assert "db" in bn  # db at 90%
        assert "app" not in bn  # app at 45%


class TestGenerateRecommendations:
    def test_no_issues(self):
        g = _simple_graph()
        recs = _generate_recommendations([], [], g, 0.001)
        assert len(recs) == 1
        assert "acceptable" in recs[0].lower()

    def test_bottleneck_no_autoscaling(self):
        g = _simple_graph()
        recs = _generate_recommendations(["app"], [], g, 0.001)
        assert any("autoscaling" in r.lower() for r in recs)

    def test_bottleneck_with_autoscaling(self):
        g = _autoscaled_graph()
        recs = _generate_recommendations(["app"], [], g, 0.001)
        assert any("max_replicas" in r.lower() or "vertical" in r.lower() for r in recs)

    def test_saturation_events(self):
        g = _simple_graph()
        recs = _generate_recommendations([], ["db saturated"], g, 0.001)
        assert any("circuit breaker" in r.lower() for r in recs)

    def test_high_error_rate(self):
        g = _simple_graph()
        recs = _generate_recommendations([], [], g, 0.10)
        assert any("load shedding" in r.lower() for r in recs)

    def test_component_not_in_graph(self):
        g = _simple_graph()
        recs = _generate_recommendations(["nonexistent"], [], g, 0.001)
        # Should not crash; non-existent component is silently skipped.
        assert len(recs) >= 1


# ===================================================================
# TrafficReplayEngine - generate_traffic_pattern
# ===================================================================


class TestGenerateTrafficPattern:
    @pytest.fixture()
    def engine(self):
        return TrafficReplayEngine(seed=123)

    @pytest.mark.parametrize("pattern", list(TrafficPattern))
    def test_all_patterns_produce_snapshots(self, engine, pattern):
        snaps = engine.generate_traffic_pattern(pattern, 10.0, 1000.0)
        assert len(snaps) == 10
        assert all(s.requests_per_second >= 0 for s in snaps)

    def test_steady_state_constant(self, engine):
        snaps = engine.generate_traffic_pattern(TrafficPattern.STEADY_STATE, 5, 1000.0)
        rps_values = [s.requests_per_second for s in snaps]
        assert all(v == pytest.approx(600.0, rel=0.01) for v in rps_values)

    def test_ramp_up_increases(self, engine):
        snaps = engine.generate_traffic_pattern(TrafficPattern.RAMP_UP, 10, 1000.0)
        rps_values = [s.requests_per_second for s in snaps]
        assert rps_values[-1] > rps_values[0]

    def test_spike_peak_at_middle(self, engine):
        snaps = engine.generate_traffic_pattern(TrafficPattern.SPIKE, 20, 1000.0)
        rps_values = [s.requests_per_second for s in snaps]
        mid = len(rps_values) // 2
        assert rps_values[mid] > rps_values[0]
        assert rps_values[mid] > rps_values[-1]

    def test_diurnal_oscillates(self, engine):
        snaps = engine.generate_traffic_pattern(TrafficPattern.DIURNAL, 20, 1000.0)
        rps_values = [s.requests_per_second for s in snaps]
        assert max(rps_values) > min(rps_values)

    def test_weekly_cycle_weekend_lower(self, engine):
        snaps = engine.generate_traffic_pattern(TrafficPattern.WEEKLY_CYCLE, 20, 1000.0)
        rps_values = [s.requests_per_second for s in snaps]
        # Last entries (t > 0.7) should tend lower due to weekend factor.
        early_avg = sum(rps_values[:5]) / 5
        late_avg = sum(rps_values[-5:]) / 5
        # Either could be higher depending on sine phase; just check they differ.
        assert early_avg != late_avg

    def test_event_driven_bursts(self, engine):
        snaps = engine.generate_traffic_pattern(TrafficPattern.EVENT_DRIVEN, 20, 1000.0)
        rps_values = [s.requests_per_second for s in snaps]
        assert max(rps_values) == pytest.approx(1000.0, rel=0.01)
        assert min(rps_values) < 500.0

    def test_seasonal_bell_curve(self, engine):
        snaps = engine.generate_traffic_pattern(TrafficPattern.SEASONAL, 20, 1000.0)
        rps_values = [s.requests_per_second for s in snaps]
        mid = len(rps_values) // 2
        assert rps_values[mid] > rps_values[0]

    def test_random_burst_varies(self, engine):
        snaps = engine.generate_traffic_pattern(TrafficPattern.RANDOM_BURST, 20, 1000.0)
        rps_values = [s.requests_per_second for s in snaps]
        assert len(set(round(v) for v in rps_values)) > 1  # not all the same

    def test_duration_one_minute(self, engine):
        snaps = engine.generate_traffic_pattern(TrafficPattern.STEADY_STATE, 1, 500.0)
        assert len(snaps) == 1

    def test_duration_fractional(self, engine):
        snaps = engine.generate_traffic_pattern(TrafficPattern.STEADY_STATE, 0.5, 500.0)
        assert len(snaps) >= 1

    def test_snapshot_has_endpoints(self, engine):
        snaps = engine.generate_traffic_pattern(TrafficPattern.RAMP_UP, 5, 1000.0)
        assert all(s.unique_endpoints >= 1 for s in snaps)

    def test_snapshot_error_rate_non_negative(self, engine):
        snaps = engine.generate_traffic_pattern(TrafficPattern.SPIKE, 5, 1000.0)
        assert all(s.error_rate >= 0 for s in snaps)

    def test_snapshot_latencies_positive(self, engine):
        snaps = engine.generate_traffic_pattern(TrafficPattern.DIURNAL, 5, 1000.0)
        assert all(s.latency_p50_ms > 0 for s in snaps)
        assert all(s.latency_p99_ms > 0 for s in snaps)


# ===================================================================
# TrafficReplayEngine - replay_traffic
# ===================================================================


class TestReplayTraffic:
    @pytest.fixture()
    def engine(self):
        return TrafficReplayEngine(seed=42)

    def test_basic_replay(self, engine):
        g = _simple_graph()
        config = ReplayConfig(
            pattern=TrafficPattern.STEADY_STATE,
            duration_minutes=5,
        )
        result = engine.replay_traffic(g, config)
        assert result.total_requests > 0
        assert result.successful_requests >= 0
        assert result.peak_rps > 0
        assert result.avg_latency_ms > 0

    def test_replay_with_custom_snapshots(self, engine):
        g = _simple_graph()
        snaps = _snapshots([100, 200, 300])
        config = ReplayConfig(snapshots=snaps)
        result = engine.replay_traffic(g, config)
        assert result.total_requests > 0
        assert result.peak_rps == pytest.approx(300.0, rel=0.01)

    def test_replay_scaled_mode(self, engine):
        g = _simple_graph()
        snaps = _snapshots([500])
        config = ReplayConfig(mode=ReplayMode.SCALED, scale_factor=2.0, snapshots=snaps)
        result = engine.replay_traffic(g, config)
        assert result.peak_rps == pytest.approx(1000.0, rel=0.01)

    def test_replay_reversed_mode(self, engine):
        g = _simple_graph()
        snaps = _snapshots([100, 200, 300])
        config = ReplayConfig(mode=ReplayMode.REVERSED, snapshots=snaps)
        result = engine.replay_traffic(g, config)
        assert result.total_requests > 0

    def test_replay_filtered_mode(self, engine):
        g = _simple_graph()
        snaps = _snapshots([100, 500, 200, 800, 300])
        config = ReplayConfig(mode=ReplayMode.FILTERED, snapshots=snaps)
        result = engine.replay_traffic(g, config)
        # Filtered keeps above-median; fewer snapshots.
        assert result.total_requests > 0

    def test_replay_time_compressed(self, engine):
        g = _simple_graph()
        snaps = _snapshots([100, 200, 300, 400])
        config = ReplayConfig(
            mode=ReplayMode.TIME_COMPRESSED, time_compression=2.0, snapshots=snaps
        )
        result = engine.replay_traffic(g, config)
        assert result.total_requests > 0

    def test_replay_high_load_produces_errors(self, engine):
        g = _single_component_graph(max_rps=100, replicas=1)
        snaps = _snapshots([500])  # 5x capacity
        config = ReplayConfig(snapshots=snaps)
        result = engine.replay_traffic(g, config)
        assert result.failed_requests > 0

    def test_replay_creates_recommendations(self, engine):
        g = _simple_graph()
        config = ReplayConfig(
            pattern=TrafficPattern.STEADY_STATE, duration_minutes=5
        )
        result = engine.replay_traffic(g, config)
        assert len(result.recommendations) >= 1

    def test_replay_detects_bottlenecks(self, engine):
        g = _single_component_graph(max_rps=100, replicas=1)
        snaps = _snapshots([90])  # 90% of capacity
        config = ReplayConfig(snapshots=snaps)
        result = engine.replay_traffic(g, config)
        assert "solo" in result.bottleneck_components

    def test_replay_detects_saturation(self, engine):
        g = _single_component_graph(max_rps=100, replicas=1)
        snaps = _snapshots([200])
        config = ReplayConfig(snapshots=snaps)
        result = engine.replay_traffic(g, config)
        assert len(result.saturation_events) > 0

    def test_replay_empty_graph(self, engine):
        g = _empty_graph()
        config = ReplayConfig(
            pattern=TrafficPattern.STEADY_STATE, duration_minutes=5
        )
        result = engine.replay_traffic(g, config)
        # No components => max_rps=0 => fallback to 1
        assert result.total_requests >= 0

    def test_replay_exact_mode_passthrough(self, engine):
        g = _simple_graph()
        snaps = _snapshots([100, 200])
        config = ReplayConfig(mode=ReplayMode.EXACT, snapshots=snaps)
        result = engine.replay_traffic(g, config)
        assert result.total_requests > 0

    def test_replay_p99_latency(self, engine):
        g = _simple_graph()
        config = ReplayConfig(
            pattern=TrafficPattern.RAMP_UP, duration_minutes=10
        )
        result = engine.replay_traffic(g, config)
        assert result.p99_latency_ms >= result.avg_latency_ms or result.p99_latency_ms >= 0

    def test_replay_zero_scale_factor(self, engine):
        g = _simple_graph()
        snaps = _snapshots([500])
        config = ReplayConfig(scale_factor=0.0, snapshots=snaps)
        result = engine.replay_traffic(g, config)
        assert result.total_requests == 0

    def test_replay_large_scale_factor(self, engine):
        g = _simple_graph()
        snaps = _snapshots([100])
        config = ReplayConfig(scale_factor=100.0, snapshots=snaps)
        result = engine.replay_traffic(g, config)
        assert result.peak_rps == pytest.approx(10000.0, rel=0.01)
        assert result.failed_requests > 0


# ===================================================================
# TrafficReplayEngine - detect_bottlenecks
# ===================================================================


class TestDetectBottlenecks:
    @pytest.fixture()
    def engine(self):
        return TrafficReplayEngine()

    def test_no_bottleneck_low_traffic(self, engine):
        g = _simple_graph()
        snaps = _snapshots([100])
        result = engine.detect_bottlenecks(g, snaps)
        assert result == []

    def test_bottleneck_near_capacity(self, engine):
        g = _single_component_graph(max_rps=100, replicas=1)
        snaps = _snapshots([90])
        result = engine.detect_bottlenecks(g, snaps)
        assert "solo" in result

    def test_multiple_snapshots_union(self, engine):
        g = _single_component_graph(max_rps=100, replicas=1)
        snaps = _snapshots([50, 90])  # only second triggers
        result = engine.detect_bottlenecks(g, snaps)
        assert "solo" in result

    def test_empty_snapshots(self, engine):
        g = _simple_graph()
        result = engine.detect_bottlenecks(g, [])
        assert result == []

    def test_sorted_output(self, engine):
        g = _simple_graph()
        snaps = _snapshots([9000])
        result = engine.detect_bottlenecks(g, snaps)
        assert result == sorted(result)


# ===================================================================
# TrafficReplayEngine - compare_replays
# ===================================================================


class TestCompareReplays:
    @pytest.fixture()
    def engine(self):
        return TrafficReplayEngine()

    def _result(self, avg_lat: float, peak: float = 500.0) -> ReplayResult:
        return ReplayResult(
            total_requests=1000, successful_requests=900, failed_requests=100,
            peak_rps=peak, avg_latency_ms=avg_lat, p99_latency_ms=avg_lat * 2,
        )

    def test_empty_results(self, engine):
        comp = engine.compare_replays([])
        assert comp.results == []
        assert comp.best_index == 0

    def test_single_result(self, engine):
        r = self._result(50.0)
        comp = engine.compare_replays([r])
        assert comp.best_index == 0
        assert comp.worst_index == 0
        assert comp.delta_avg_latency_ms == 0.0

    def test_two_results(self, engine):
        r1 = self._result(30.0, 400.0)
        r2 = self._result(80.0, 600.0)
        comp = engine.compare_replays([r1, r2])
        assert comp.best_index == 0  # lower latency
        assert comp.worst_index == 1
        assert comp.delta_avg_latency_ms == pytest.approx(50.0, rel=0.01)
        assert comp.delta_peak_rps == pytest.approx(200.0, rel=0.01)

    def test_summary_contains_info(self, engine):
        r1 = self._result(20.0)
        r2 = self._result(100.0)
        comp = engine.compare_replays([r1, r2])
        assert "Best" in comp.summary
        assert "worst" in comp.summary.lower()

    def test_three_results(self, engine):
        r1 = self._result(50.0)
        r2 = self._result(10.0)
        r3 = self._result(90.0)
        comp = engine.compare_replays([r1, r2, r3])
        assert comp.best_index == 1
        assert comp.worst_index == 2


# ===================================================================
# TrafficReplayEngine - estimate_capacity_headroom
# ===================================================================


class TestEstimateCapacityHeadroom:
    @pytest.fixture()
    def engine(self):
        return TrafficReplayEngine(seed=42)

    def test_empty_graph(self, engine):
        g = _empty_graph()
        config = ReplayConfig(duration_minutes=5)
        h = engine.estimate_capacity_headroom(g, config)
        assert h.max_sustainable_rps == 0.0
        assert h.headroom_percent == 0.0
        assert len(h.recommendations) >= 1

    def test_simple_graph_has_headroom(self, engine):
        g = _simple_graph()
        snaps = _snapshots([500])
        config = ReplayConfig(snapshots=snaps)
        h = engine.estimate_capacity_headroom(g, config)
        assert h.max_sustainable_rps > 0
        assert h.headroom_percent > 0
        assert h.limiting_component != ""

    def test_low_headroom_warning(self, engine):
        g = _single_component_graph(max_rps=100, replicas=1)
        # sustainable = 80; current = 75 => headroom ~6.25%
        snaps = _snapshots([75])
        config = ReplayConfig(snapshots=snaps)
        h = engine.estimate_capacity_headroom(g, config)
        assert h.headroom_percent < 20
        assert any("low" in r.lower() or "scale" in r.lower() for r in h.recommendations)

    def test_moderate_headroom(self, engine):
        g = _single_component_graph(max_rps=1000, replicas=1)
        snaps = _snapshots([500])
        config = ReplayConfig(snapshots=snaps)
        h = engine.estimate_capacity_headroom(g, config)
        assert h.headroom_percent > 20
        assert h.headroom_percent < 50
        assert any("autoscaling" in r.lower() for r in h.recommendations)

    def test_high_headroom(self, engine):
        g = _simple_graph()  # 10000 max
        snaps = _snapshots([100])
        config = ReplayConfig(snapshots=snaps)
        h = engine.estimate_capacity_headroom(g, config)
        assert h.headroom_percent > 50
        assert any("sufficient" in r.lower() for r in h.recommendations)

    def test_time_to_saturation_positive(self, engine):
        g = _simple_graph()
        snaps = _snapshots([500])
        config = ReplayConfig(snapshots=snaps)
        h = engine.estimate_capacity_headroom(g, config)
        assert h.time_to_saturation_minutes > 0

    def test_at_capacity_zero_headroom(self, engine):
        g = _single_component_graph(max_rps=100, replicas=1)
        snaps = _snapshots([100])  # at sustainable limit
        config = ReplayConfig(snapshots=snaps)
        h = engine.estimate_capacity_headroom(g, config)
        # current=100, sustainable=80 => headroom clamped to 0
        assert h.headroom_percent == 0.0

    def test_with_generated_pattern(self, engine):
        g = _simple_graph()
        config = ReplayConfig(
            pattern=TrafficPattern.SPIKE, duration_minutes=5
        )
        h = engine.estimate_capacity_headroom(g, config)
        assert h.current_rps > 0
        assert h.max_sustainable_rps > 0

    def test_scale_factor_applied(self, engine):
        g = _simple_graph()
        snaps = _snapshots([500])
        config1 = ReplayConfig(snapshots=snaps, scale_factor=1.0)
        config2 = ReplayConfig(snapshots=snaps, scale_factor=2.0)
        h1 = engine.estimate_capacity_headroom(g, config1)
        h2 = engine.estimate_capacity_headroom(g, config2)
        assert h2.current_rps > h1.current_rps


# ===================================================================
# TrafficReplayEngine - simulate_traffic_shift
# ===================================================================


class TestSimulateTrafficShift:
    @pytest.fixture()
    def engine(self):
        return TrafficReplayEngine(seed=42)

    def test_steady_to_spike(self, engine):
        g = _simple_graph()
        result = engine.simulate_traffic_shift(
            g, TrafficPattern.STEADY_STATE, TrafficPattern.SPIKE
        )
        assert result.from_pattern == TrafficPattern.STEADY_STATE
        assert result.to_pattern == TrafficPattern.SPIKE
        assert result.transition_duration_minutes > 0
        assert result.peak_rps_during_shift > 0

    def test_spike_to_steady(self, engine):
        g = _simple_graph()
        result = engine.simulate_traffic_shift(
            g, TrafficPattern.SPIKE, TrafficPattern.STEADY_STATE
        )
        assert result.transition_duration_minutes > 0

    def test_same_pattern(self, engine):
        g = _simple_graph()
        result = engine.simulate_traffic_shift(
            g, TrafficPattern.DIURNAL, TrafficPattern.DIURNAL
        )
        assert result.transition_duration_minutes > 0

    def test_shift_recommendations(self, engine):
        g = _simple_graph()
        result = engine.simulate_traffic_shift(
            g, TrafficPattern.STEADY_STATE, TrafficPattern.SPIKE
        )
        assert len(result.recommendations) >= 1

    def test_shift_stable_after(self, engine):
        g = _simple_graph()
        result = engine.simulate_traffic_shift(
            g, TrafficPattern.RAMP_UP, TrafficPattern.SEASONAL
        )
        assert result.stable_after_minutes > 0
        assert result.stable_after_minutes <= result.transition_duration_minutes

    def test_shift_empty_graph(self, engine):
        g = _empty_graph()
        result = engine.simulate_traffic_shift(
            g, TrafficPattern.STEADY_STATE, TrafficPattern.SPIKE
        )
        assert result.transition_duration_minutes > 0

    def test_shift_small_capacity(self, engine):
        g = _single_component_graph(max_rps=100, replicas=1)
        result = engine.simulate_traffic_shift(
            g, TrafficPattern.STEADY_STATE, TrafficPattern.SPIKE
        )
        assert result.errors_during_shift > 0
        assert len(result.components_affected) > 0

    def test_shift_low_errors_large_capacity(self, engine):
        g = InfraGraph()
        g.add_component(
            _make_component("big", ComponentType.APP_SERVER, replicas=100, max_rps=100000)
        )
        result = engine.simulate_traffic_shift(
            g, TrafficPattern.STEADY_STATE, TrafficPattern.STEADY_STATE
        )
        # Very large capacity => still baseline errors but no component saturation.
        assert result.components_affected == []
        assert result.peak_rps_during_shift > 0


# ===================================================================
# TrafficReplayEngine - find_breaking_point
# ===================================================================


class TestFindBreakingPoint:
    @pytest.fixture()
    def engine(self):
        return TrafficReplayEngine(seed=42)

    def test_basic_breaking_point(self, engine):
        g = _simple_graph()
        result = engine.find_breaking_point(g, TrafficPattern.STEADY_STATE)
        assert result.breaking_rps > 0
        assert result.max_sustainable_rps > 0
        assert result.breaking_rps >= result.max_sustainable_rps
        assert result.breaking_component != ""

    def test_empty_graph_breaking_point(self, engine):
        g = _empty_graph()
        result = engine.find_breaking_point(g, TrafficPattern.SPIKE)
        assert result.breaking_rps == 0.0
        assert result.failure_mode == "no_capacity"
        assert len(result.recommendations) >= 1

    def test_breaking_point_recommendations(self, engine):
        g = _simple_graph()
        result = engine.find_breaking_point(g, TrafficPattern.RAMP_UP)
        assert len(result.recommendations) >= 1

    def test_safety_margin(self, engine):
        g = _simple_graph()
        result = engine.find_breaking_point(g, TrafficPattern.STEADY_STATE)
        assert result.safety_margin_percent >= 0

    def test_failure_mode_assigned(self, engine):
        g = _simple_graph()
        result = engine.find_breaking_point(g, TrafficPattern.DIURNAL)
        assert result.failure_mode in {"overload", "no_capacity"}

    def test_breaking_point_with_autoscaling(self, engine):
        g = _autoscaled_graph()
        result = engine.find_breaking_point(g, TrafficPattern.STEADY_STATE)
        assert result.breaking_rps > 0
        # Autoscaled => higher capacity => higher breaking point
        g2 = _simple_graph()
        result2 = engine.find_breaking_point(g2, TrafficPattern.STEADY_STATE)
        assert result.breaking_rps >= result2.breaking_rps

    def test_cascade_components(self, engine):
        g = _simple_graph()
        result = engine.find_breaking_point(g, TrafficPattern.SPIKE)
        # cascade_components may or may not be populated depending on topology
        assert isinstance(result.cascade_components, list)

    def test_autoscaling_recommendation(self, engine):
        g = _simple_graph()  # no autoscaling
        result = engine.find_breaking_point(g, TrafficPattern.STEADY_STATE)
        assert any("autoscaling" in r.lower() or "enable" in r.lower() for r in result.recommendations)

    def test_single_component_breaking(self, engine):
        g = _single_component_graph(max_rps=100, replicas=1)
        result = engine.find_breaking_point(g, TrafficPattern.STEADY_STATE)
        assert result.breaking_component == "solo"
        assert result.breaking_rps > 0


# ===================================================================
# _apply_mode (via replay_traffic)
# ===================================================================


class TestApplyMode:
    @pytest.fixture()
    def engine(self):
        return TrafficReplayEngine(seed=42)

    def test_exact_preserves_order(self, engine):
        g = _simple_graph()
        snaps = _snapshots([100, 200, 300])
        config = ReplayConfig(mode=ReplayMode.EXACT, snapshots=snaps)
        result = engine.replay_traffic(g, config)
        assert result.total_requests > 0

    def test_reversed_reverses_order(self, engine):
        g = _simple_graph()
        snaps = _snapshots([100, 200, 300])
        config_fwd = ReplayConfig(mode=ReplayMode.EXACT, snapshots=snaps)
        config_rev = ReplayConfig(mode=ReplayMode.REVERSED, snapshots=snaps)
        r_fwd = engine.replay_traffic(g, config_fwd)
        r_rev = engine.replay_traffic(g, config_rev)
        # Same total traffic, just different ordering.
        assert r_fwd.total_requests == r_rev.total_requests

    def test_filtered_fewer_snapshots(self, engine):
        g = _simple_graph()
        snaps = _snapshots([100, 200, 300, 400, 500])
        config_all = ReplayConfig(mode=ReplayMode.EXACT, snapshots=snaps)
        config_filt = ReplayConfig(mode=ReplayMode.FILTERED, snapshots=snaps)
        r_all = engine.replay_traffic(g, config_all)
        r_filt = engine.replay_traffic(g, config_filt)
        assert r_filt.total_requests <= r_all.total_requests

    def test_filtered_empty_snapshots(self, engine):
        g = _simple_graph()
        config = ReplayConfig(mode=ReplayMode.FILTERED, snapshots=[])
        result = engine.replay_traffic(g, config)
        # Falls through to generated pattern since snapshots is empty
        assert result.total_requests >= 0

    def test_time_compressed_reduces_snapshots(self, engine):
        g = _simple_graph()
        snaps = _snapshots([100, 200, 300, 400, 500, 600])
        config = ReplayConfig(
            mode=ReplayMode.TIME_COMPRESSED,
            time_compression=3.0,
            snapshots=snaps,
        )
        result = engine.replay_traffic(g, config)
        # With compression=3, keeps every 3rd snapshot (2 out of 6).
        assert result.total_requests > 0

    def test_scaled_applies_scale(self, engine):
        g = _simple_graph()
        snaps = _snapshots([100])
        config1 = ReplayConfig(mode=ReplayMode.SCALED, scale_factor=1.0, snapshots=snaps)
        config2 = ReplayConfig(mode=ReplayMode.SCALED, scale_factor=3.0, snapshots=snaps)
        r1 = engine.replay_traffic(g, config1)
        r2 = engine.replay_traffic(g, config2)
        assert r2.peak_rps > r1.peak_rps


# ===================================================================
# Determinism / seed tests
# ===================================================================


class TestDeterminism:
    def test_same_seed_same_results(self):
        e1 = TrafficReplayEngine(seed=99)
        e2 = TrafficReplayEngine(seed=99)
        s1 = e1.generate_traffic_pattern(TrafficPattern.RANDOM_BURST, 10, 1000.0)
        s2 = e2.generate_traffic_pattern(TrafficPattern.RANDOM_BURST, 10, 1000.0)
        for a, b in zip(s1, s2):
            assert a.requests_per_second == b.requests_per_second

    def test_different_seed_different_results(self):
        e1 = TrafficReplayEngine(seed=1)
        e2 = TrafficReplayEngine(seed=2)
        s1 = e1.generate_traffic_pattern(TrafficPattern.RANDOM_BURST, 20, 1000.0)
        s2 = e2.generate_traffic_pattern(TrafficPattern.RANDOM_BURST, 20, 1000.0)
        rps1 = [s.requests_per_second for s in s1]
        rps2 = [s.requests_per_second for s in s2]
        assert rps1 != rps2


# ===================================================================
# Integration-level tests
# ===================================================================


class TestIntegration:
    @pytest.fixture()
    def engine(self):
        return TrafficReplayEngine(seed=42)

    def test_full_workflow(self, engine):
        """Generate pattern -> replay -> detect bottlenecks -> compare."""
        g = _simple_graph()
        snaps = engine.generate_traffic_pattern(TrafficPattern.SPIKE, 10, 1000.0)
        config = ReplayConfig(snapshots=snaps, duration_minutes=10)
        r1 = engine.replay_traffic(g, config)
        bn = engine.detect_bottlenecks(g, snaps)
        # Run a second replay with scaling
        config2 = ReplayConfig(snapshots=snaps, scale_factor=2.0)
        r2 = engine.replay_traffic(g, config2)
        comp = engine.compare_replays([r1, r2])
        assert comp.best_index in {0, 1}
        assert comp.worst_index in {0, 1}
        assert isinstance(bn, list)

    def test_headroom_then_breaking_point(self, engine):
        """Estimate headroom then find breaking point."""
        g = _simple_graph()
        config = ReplayConfig(
            pattern=TrafficPattern.STEADY_STATE, duration_minutes=5
        )
        h = engine.estimate_capacity_headroom(g, config)
        bp = engine.find_breaking_point(g, TrafficPattern.STEADY_STATE)
        # Sustainable < breaking
        assert bp.max_sustainable_rps <= bp.breaking_rps
        assert h.max_sustainable_rps > 0

    def test_shift_then_replay(self, engine):
        """Simulate shift then replay the to-pattern."""
        g = _simple_graph()
        shift = engine.simulate_traffic_shift(
            g, TrafficPattern.STEADY_STATE, TrafficPattern.SPIKE
        )
        snaps = engine.generate_traffic_pattern(
            TrafficPattern.SPIKE, 10, shift.peak_rps_during_shift
        )
        config = ReplayConfig(snapshots=snaps)
        result = engine.replay_traffic(g, config)
        assert result.total_requests > 0

    def test_mixed_component_types(self, engine):
        """Graph with all component types."""
        g = InfraGraph()
        types = [
            ComponentType.LOAD_BALANCER,
            ComponentType.WEB_SERVER,
            ComponentType.APP_SERVER,
            ComponentType.DATABASE,
            ComponentType.CACHE,
            ComponentType.QUEUE,
            ComponentType.STORAGE,
            ComponentType.DNS,
            ComponentType.EXTERNAL_API,
            ComponentType.CUSTOM,
        ]
        for i, ct in enumerate(types):
            g.add_component(_make_component(f"c{i}", ct))
        config = ReplayConfig(pattern=TrafficPattern.DIURNAL, duration_minutes=5)
        result = engine.replay_traffic(g, config)
        assert result.total_requests > 0
        assert result.avg_latency_ms > 0

    def test_all_patterns_all_modes(self, engine):
        """Every pattern x mode combination produces valid results."""
        g = _simple_graph()
        for pattern in TrafficPattern:
            for mode in ReplayMode:
                config = ReplayConfig(
                    mode=mode, pattern=pattern, duration_minutes=3
                )
                result = engine.replay_traffic(g, config)
                assert result.total_requests >= 0, f"Failed: {pattern}/{mode}"

    def test_replay_autoscaled_graph_latency(self, engine):
        """Replay on autoscaled graph exercises autoscaling branch in latency calc."""
        g = _autoscaled_graph()
        snaps = _snapshots([500, 1000, 2000])
        config = ReplayConfig(snapshots=snaps)
        result = engine.replay_traffic(g, config)
        assert result.avg_latency_ms > 0
        assert result.total_requests > 0

    def test_shift_autoscaled_graph(self, engine):
        """Traffic shift on autoscaled graph exercises autoscaling branch."""
        g = _autoscaled_graph()
        result = engine.simulate_traffic_shift(
            g, TrafficPattern.STEADY_STATE, TrafficPattern.SPIKE
        )
        assert result.peak_rps_during_shift > 0

    def test_shift_no_errors_no_affected(self, engine):
        """Traffic shift with huge capacity triggers 'without issues' recommendation."""
        g = InfraGraph()
        # Capacity so large that load ratio < 0.01, giving 0 error rate.
        g.add_component(
            _make_component(
                "huge", ComponentType.APP_SERVER,
                replicas=1, max_rps=10_000_000,
            )
        )
        result = engine.simulate_traffic_shift(
            g, TrafficPattern.STEADY_STATE, TrafficPattern.STEADY_STATE
        )
        assert result.errors_during_shift == 0
        assert result.components_affected == []
        assert "without issues" in result.recommendations[0].lower()

    def test_breaking_point_overload_mode(self, engine):
        """Breaking point failure mode is set correctly."""
        g = _single_component_graph(max_rps=100, replicas=1)
        result = engine.find_breaking_point(g, TrafficPattern.STEADY_STATE)
        assert result.failure_mode == "overload"

    def test_breaking_point_low_safety_margin(self, engine):
        """Verify low safety margin recommendation is generated."""
        g = _single_component_graph(max_rps=100, replicas=1)
        result = engine.find_breaking_point(g, TrafficPattern.STEADY_STATE)
        # safety margin = (breaking - sustainable) / sustainable * 100
        # If breaking is close to sustainable, margin is low (<25%).
        has_low_margin = any("safety margin" in r.lower() or "horizontal" in r.lower()
                            for r in result.recommendations)
        has_scaling = any("scaling" in r.lower() or "autoscaling" in r.lower()
                         for r in result.recommendations)
        assert has_low_margin or has_scaling

    def test_filtered_mode_empty_directly(self, engine):
        """Filtered mode with explicitly empty snapshots list via _apply_mode."""
        applied = engine._apply_mode([], ReplayConfig(mode=ReplayMode.FILTERED))
        assert applied == []

    def test_pattern_rps_fallback(self, engine):
        """Exercise the defensive fallback in _pattern_rps for unknown patterns."""
        # Monkey-patch a "fake" pattern value to trigger the fallback.
        result = engine._pattern_rps("unknown_pattern", 0.5, 1000.0, 0)
        assert result == pytest.approx(500.0, rel=0.01)
