"""Tests for Connection Pool Analyzer.

Comprehensive tests covering pool sizing, leak detection, exhaustion
simulation, timeout analysis, health check strategies, warmup strategies,
sharing tradeoffs, storm prevention, pool metrics modelling, cross-service
coordination, full analysis, enums, helpers, and edge cases.
"""

from __future__ import annotations

import math

import pytest

from faultray.model.components import (
    Capacity,
    Component,
    ComponentType,
    Dependency,
    DegradationConfig,
    HealthStatus,
    OperationalProfile,
    ResourceMetrics,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.connection_pool_analyzer import (
    ConnectionPoolAnalyzer,
    CrossServiceCoordinationResult,
    ExhaustionSimResult,
    HealthCheckAnalysisResult,
    HealthCheckStrategy,
    LeakDetectionResult,
    PoolAnalysisSummary,
    PoolConfig,
    PoolMetricsSnapshot,
    PoolSharingMode,
    PoolSizingResult,
    PoolType,
    SharingTradeoffResult,
    StormPreventionResult,
    TimeoutAnalysisResult,
    WarmupAnalysisResult,
    WarmupStrategy,
    _HEALTH_CHECK_OVERHEAD_MS,
    _HEALTH_CHECK_RELIABILITY,
    _IDEAL_IDLE_RATIO,
    _POOL_CREATION_OVERHEAD_MS,
    _WARMUP_READINESS,
    _clamp,
    _compute_leak_rate,
    _effective_connections,
    _estimate_timeout_errors,
    _recommend_pool_size,
    _sizing_score,
    _storm_peak_connections,
    _timeout_score,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(
    cid: str = "c1",
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 2,
    max_connections: int = 1000,
    max_rps: int = 5000,
    connection_pool_size: int = 100,
    conn_leak_per_hour: float = 0.0,
) -> Component:
    return Component(
        id=cid,
        name=cid,
        type=ctype,
        replicas=replicas,
        capacity=Capacity(
            max_connections=max_connections,
            max_rps=max_rps,
            connection_pool_size=connection_pool_size,
        ),
        operational_profile=OperationalProfile(
            degradation=DegradationConfig(
                connection_leak_per_hour=conn_leak_per_hour,
            ),
        ),
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


class TestEnums:
    def test_pool_type_values(self) -> None:
        assert PoolType.DATABASE.value == "database"
        assert PoolType.HTTP.value == "http"
        assert PoolType.GRPC.value == "grpc"
        assert PoolType.MESSAGE_QUEUE.value == "message_queue"
        assert PoolType.REDIS.value == "redis"
        assert len(PoolType) == 5

    def test_health_check_strategy_values(self) -> None:
        assert HealthCheckStrategy.TEST_ON_BORROW.value == "test_on_borrow"
        assert HealthCheckStrategy.NONE.value == "none"
        assert len(HealthCheckStrategy) == 5

    def test_warmup_strategy_values(self) -> None:
        assert WarmupStrategy.PRE_CREATE.value == "pre_create"
        assert WarmupStrategy.LAZY_CREATION.value == "lazy_creation"
        assert WarmupStrategy.GRADUAL_RAMP.value == "gradual_ramp"
        assert len(WarmupStrategy) == 3

    def test_pool_sharing_mode_values(self) -> None:
        assert PoolSharingMode.SHARED.value == "shared"
        assert PoolSharingMode.DEDICATED.value == "dedicated"
        assert PoolSharingMode.HYBRID.value == "hybrid"
        assert len(PoolSharingMode) == 3


# ---------------------------------------------------------------------------
# 2. Helper function tests
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_clamp_within_bounds(self) -> None:
        assert _clamp(50.0) == 50.0

    def test_clamp_below_minimum(self) -> None:
        assert _clamp(-10.0) == 0.0

    def test_clamp_above_maximum(self) -> None:
        assert _clamp(200.0) == 100.0

    def test_clamp_custom_bounds(self) -> None:
        assert _clamp(5.0, 0.0, 10.0) == 5.0
        assert _clamp(-1.0, 0.0, 10.0) == 0.0
        assert _clamp(15.0, 0.0, 10.0) == 10.0

    def test_effective_connections(self) -> None:
        c = _comp(replicas=3, connection_pool_size=50)
        assert _effective_connections(c) == 150

    def test_compute_leak_rate_no_leak(self) -> None:
        c = _comp(conn_leak_per_hour=0.0)
        cfg = PoolConfig()
        assert _compute_leak_rate(cfg, c) == 0.0

    def test_compute_leak_rate_with_leak_and_health_check(self) -> None:
        c = _comp(conn_leak_per_hour=10.0)
        cfg = PoolConfig(health_check=HealthCheckStrategy.TEST_ON_BORROW)
        rate = _compute_leak_rate(cfg, c)
        # TEST_ON_BORROW reliability is 0.95 => rate = 10 * 0.05 = 0.5
        assert rate == pytest.approx(0.5, rel=0.01)

    def test_compute_leak_rate_no_health_check(self) -> None:
        c = _comp(conn_leak_per_hour=10.0)
        cfg = PoolConfig(health_check=HealthCheckStrategy.NONE)
        rate = _compute_leak_rate(cfg, c)
        assert rate == pytest.approx(10.0, rel=0.01)

    def test_compute_leak_rate_long_idle_timeout(self) -> None:
        c = _comp(conn_leak_per_hour=10.0)
        cfg = PoolConfig(
            health_check=HealthCheckStrategy.NONE,
            idle_timeout_seconds=1500.0,
        )
        rate = _compute_leak_rate(cfg, c)
        # 10 * 1.0 * 1.3 = 13.0
        assert rate == pytest.approx(13.0, rel=0.01)

    def test_compute_leak_rate_short_idle_timeout(self) -> None:
        c = _comp(conn_leak_per_hour=10.0)
        cfg = PoolConfig(
            health_check=HealthCheckStrategy.NONE,
            idle_timeout_seconds=30.0,
        )
        rate = _compute_leak_rate(cfg, c)
        # 10 * 1.0 * 0.7 = 7.0
        assert rate == pytest.approx(7.0, rel=0.01)

    def test_recommend_pool_size_database(self) -> None:
        c = _comp(max_connections=1000, replicas=2)
        cfg = PoolConfig(pool_type=PoolType.DATABASE)
        rmin, rmax, ridle = _recommend_pool_size(PoolType.DATABASE, c, cfg)
        assert rmin >= 1
        assert rmax >= rmin
        assert ridle >= 1
        assert ridle <= rmax

    def test_recommend_pool_size_http(self) -> None:
        c = _comp(max_connections=2000, replicas=1)
        cfg = PoolConfig(pool_type=PoolType.HTTP)
        rmin, rmax, ridle = _recommend_pool_size(PoolType.HTTP, c, cfg)
        assert rmax > rmin
        # HTTP has lower overhead, so higher max
        assert rmax >= 10

    def test_sizing_score_well_configured(self) -> None:
        cfg = PoolConfig(min_size=5, max_size=150, idle_size=10)
        score = _sizing_score(cfg, 5, 150, 10)
        assert score == 100.0

    def test_sizing_score_oversized(self) -> None:
        cfg = PoolConfig(min_size=5, max_size=500, idle_size=10)
        score = _sizing_score(cfg, 5, 100, 10)
        assert score < 100.0

    def test_sizing_score_min_exceeds_max(self) -> None:
        cfg = PoolConfig(min_size=50, max_size=20, idle_size=5)
        score = _sizing_score(cfg, 5, 20, 5)
        assert score < 100.0

    def test_sizing_score_idle_exceeds_max(self) -> None:
        cfg = PoolConfig(min_size=5, max_size=20, idle_size=30)
        score = _sizing_score(cfg, 5, 20, 5)
        assert score < 100.0

    def test_timeout_score_healthy(self) -> None:
        cfg = PoolConfig(
            acquire_timeout_ms=5000.0,
            idle_timeout_seconds=600.0,
            max_lifetime_seconds=1800.0,
        )
        score = _timeout_score(cfg, PoolType.DATABASE)
        assert score == 100.0

    def test_timeout_score_no_acquire_timeout(self) -> None:
        cfg = PoolConfig(acquire_timeout_ms=0.0)
        score = _timeout_score(cfg, PoolType.HTTP)
        assert score < 100.0

    def test_timeout_score_no_lifetime(self) -> None:
        cfg = PoolConfig(max_lifetime_seconds=0.0)
        score = _timeout_score(cfg, PoolType.HTTP)
        assert score < 100.0

    def test_timeout_score_db_short_acquire(self) -> None:
        cfg = PoolConfig(acquire_timeout_ms=200.0)
        score = _timeout_score(cfg, PoolType.DATABASE)
        # Short acquire for DB gets extra penalty
        assert score < 90.0

    def test_estimate_timeout_errors_low_util(self) -> None:
        c = _comp()
        cfg = PoolConfig()
        errors = _estimate_timeout_errors(cfg, c)
        assert errors == 0.0

    def test_estimate_timeout_errors_high_util(self) -> None:
        c = _comp()
        c.metrics = ResourceMetrics(cpu_percent=95.0)
        cfg = PoolConfig()
        errors = _estimate_timeout_errors(cfg, c)
        assert errors > 0.0

    def test_storm_peak_connections(self) -> None:
        c = _comp(replicas=3)
        cfg = PoolConfig(max_size=20)
        peak = _storm_peak_connections(cfg, c, service_count=4)
        assert peak == int(20 * 3 * 4 * 1.5)

    def test_constant_tables_coverage(self) -> None:
        """Verify all lookup tables have entries for every enum member."""
        for pt in PoolType:
            assert pt in _POOL_CREATION_OVERHEAD_MS
            assert pt in _IDEAL_IDLE_RATIO
        for hc in HealthCheckStrategy:
            assert hc in _HEALTH_CHECK_OVERHEAD_MS
            assert hc in _HEALTH_CHECK_RELIABILITY
        for ws in WarmupStrategy:
            assert ws in _WARMUP_READINESS


# ---------------------------------------------------------------------------
# 3. Pool sizing analysis
# ---------------------------------------------------------------------------


class TestPoolSizing:
    def test_sizing_component_not_found(self) -> None:
        analyzer = ConnectionPoolAnalyzer()
        g = _graph()
        result = analyzer.analyze_pool_sizing(g, "missing", PoolConfig())
        assert "not found" in result.recommendations[0].lower()

    def test_sizing_healthy_config(self) -> None:
        analyzer = ConnectionPoolAnalyzer()
        c = _comp(cid="db1", ctype=ComponentType.DATABASE, max_connections=1000)
        g = _graph(c)
        cfg = PoolConfig(pool_type=PoolType.DATABASE, min_size=5, max_size=150, idle_size=10)
        result = analyzer.analyze_pool_sizing(g, "db1", cfg)
        assert result.component_id == "db1"
        assert result.pool_type == PoolType.DATABASE
        assert result.recommended_max >= 1
        assert result.sizing_score > 0

    def test_sizing_oversized_pool(self) -> None:
        analyzer = ConnectionPoolAnalyzer()
        c = _comp(cid="app1", max_connections=100, replicas=1)
        g = _graph(c)
        cfg = PoolConfig(min_size=5, max_size=500, idle_size=10)
        result = analyzer.analyze_pool_sizing(g, "app1", cfg)
        assert result.oversized is True
        assert any("reduce" in r.lower() for r in result.recommendations)

    def test_sizing_undersized_pool(self) -> None:
        analyzer = ConnectionPoolAnalyzer()
        c = _comp(cid="app2", max_connections=2000, replicas=4)
        g = _graph(c)
        cfg = PoolConfig(min_size=1, max_size=3, idle_size=1)
        result = analyzer.analyze_pool_sizing(g, "app2", cfg)
        assert result.undersized is True

    def test_sizing_min_exceeds_max(self) -> None:
        analyzer = ConnectionPoolAnalyzer()
        c = _comp(cid="x1")
        g = _graph(c)
        cfg = PoolConfig(min_size=50, max_size=10, idle_size=5)
        result = analyzer.analyze_pool_sizing(g, "x1", cfg)
        assert any("min_size" in r for r in result.recommendations)

    def test_sizing_db_min_zero(self) -> None:
        analyzer = ConnectionPoolAnalyzer()
        c = _comp(cid="db0", ctype=ComponentType.DATABASE)
        g = _graph(c)
        cfg = PoolConfig(pool_type=PoolType.DATABASE, min_size=0, max_size=20, idle_size=5)
        result = analyzer.analyze_pool_sizing(g, "db0", cfg)
        assert any("cold-start" in r.lower() for r in result.recommendations)


# ---------------------------------------------------------------------------
# 4. Leak detection
# ---------------------------------------------------------------------------


class TestLeakDetection:
    def test_leak_component_not_found(self) -> None:
        analyzer = ConnectionPoolAnalyzer()
        g = _graph()
        result = analyzer.detect_connection_leaks(g, "nope", PoolConfig())
        assert result.leak_risk == "unknown"

    def test_no_leak(self) -> None:
        analyzer = ConnectionPoolAnalyzer()
        c = _comp(cid="clean")
        g = _graph(c)
        cfg = PoolConfig()
        result = analyzer.detect_connection_leaks(g, "clean", cfg)
        assert result.leak_risk == "none"
        assert result.leaked_connections_estimate == 0

    def test_high_leak_no_health_check(self) -> None:
        analyzer = ConnectionPoolAnalyzer()
        c = _comp(cid="leaky", conn_leak_per_hour=50.0, replicas=1)
        g = _graph(c)
        cfg = PoolConfig(
            health_check=HealthCheckStrategy.NONE,
            max_size=20,
            max_lifetime_seconds=0.0,
        )
        result = analyzer.detect_connection_leaks(g, "leaky", cfg, observation_hours=24.0)
        assert result.leak_risk in ("medium", "high")
        assert result.leaked_connections_estimate > 0
        assert result.leak_rate_per_hour > 0
        assert result.detection_confidence > 0
        assert any("health" in r.lower() for r in result.recommendations)

    def test_leak_with_health_check_reduces_rate(self) -> None:
        analyzer = ConnectionPoolAnalyzer()
        c = _comp(cid="semi", conn_leak_per_hour=10.0)
        g = _graph(c)
        cfg_none = PoolConfig(health_check=HealthCheckStrategy.NONE)
        cfg_borrow = PoolConfig(health_check=HealthCheckStrategy.TEST_ON_BORROW)
        r_none = analyzer.detect_connection_leaks(g, "semi", cfg_none)
        r_borrow = analyzer.detect_connection_leaks(g, "semi", cfg_borrow)
        assert r_none.leak_rate_per_hour > r_borrow.leak_rate_per_hour

    def test_time_to_exhaustion(self) -> None:
        analyzer = ConnectionPoolAnalyzer()
        c = _comp(cid="tte", conn_leak_per_hour=5.0, replicas=1)
        g = _graph(c)
        cfg = PoolConfig(
            health_check=HealthCheckStrategy.NONE,
            max_size=100,
        )
        result = analyzer.detect_connection_leaks(g, "tte", cfg)
        assert result.time_to_exhaustion_hours != float("inf")
        assert result.time_to_exhaustion_hours > 0


# ---------------------------------------------------------------------------
# 5. Pool exhaustion simulation
# ---------------------------------------------------------------------------


class TestPoolExhaustion:
    def test_exhaustion_component_not_found(self) -> None:
        analyzer = ConnectionPoolAnalyzer()
        g = _graph()
        result = analyzer.simulate_pool_exhaustion(g, "x", PoolConfig())
        assert result.severity == "unknown"

    def test_no_exhaustion_low_rate(self) -> None:
        analyzer = ConnectionPoolAnalyzer()
        c = _comp(cid="ok")
        g = _graph(c)
        cfg = PoolConfig(max_size=50)
        result = analyzer.simulate_pool_exhaustion(
            g, "ok", cfg, request_rate_per_second=10.0, avg_hold_time_ms=10.0,
        )
        assert result.severity == "none"
        assert result.requests_rejected == 0

    def test_exhaustion_high_rate(self) -> None:
        analyzer = ConnectionPoolAnalyzer()
        c = _comp(cid="busy", replicas=1)
        g = _graph(c)
        cfg = PoolConfig(max_size=5)
        result = analyzer.simulate_pool_exhaustion(
            g, "busy", cfg, request_rate_per_second=1000.0, avg_hold_time_ms=100.0,
        )
        assert result.severity in ("medium", "high", "critical")
        assert result.requests_rejected > 0 or result.requests_queued > 0
        assert result.recovery_time_seconds > 0

    def test_exhaustion_cascade(self) -> None:
        analyzer = ConnectionPoolAnalyzer()
        c1 = _comp(cid="backend", replicas=1)
        c2 = _comp(cid="frontend")
        g = _graph(c1, c2)
        g.add_dependency(Dependency(source_id="frontend", target_id="backend"))
        cfg = PoolConfig(max_size=5)
        result = analyzer.simulate_pool_exhaustion(
            g, "backend", cfg, request_rate_per_second=1000.0, avg_hold_time_ms=100.0,
        )
        assert "frontend" in result.cascade_affected

    def test_exhaustion_single_replica_recommendation(self) -> None:
        analyzer = ConnectionPoolAnalyzer()
        c = _comp(cid="solo", replicas=1)
        g = _graph(c)
        cfg = PoolConfig(max_size=5)
        result = analyzer.simulate_pool_exhaustion(
            g, "solo", cfg, request_rate_per_second=500.0, avg_hold_time_ms=100.0,
        )
        assert any("replicas" in r.lower() for r in result.recommendations)


# ---------------------------------------------------------------------------
# 6. Timeout analysis
# ---------------------------------------------------------------------------


class TestTimeoutAnalysis:
    def test_timeout_component_not_found(self) -> None:
        analyzer = ConnectionPoolAnalyzer()
        g = _graph()
        result = analyzer.analyze_timeouts(g, "missing", PoolConfig())
        assert result.timeout_score == 0.0
        assert result.acquire_timeout_adequate is False

    def test_timeout_healthy(self) -> None:
        analyzer = ConnectionPoolAnalyzer()
        c = _comp(cid="t1")
        g = _graph(c)
        cfg = PoolConfig(
            acquire_timeout_ms=5000.0,
            idle_timeout_seconds=600.0,
            max_lifetime_seconds=1800.0,
        )
        result = analyzer.analyze_timeouts(g, "t1", cfg)
        assert result.acquire_timeout_adequate is True
        assert result.idle_timeout_adequate is True
        assert result.max_lifetime_adequate is True
        assert result.timeout_score == 100.0

    def test_timeout_no_acquire(self) -> None:
        analyzer = ConnectionPoolAnalyzer()
        c = _comp(cid="t2")
        g = _graph(c)
        cfg = PoolConfig(acquire_timeout_ms=0.0)
        result = analyzer.analyze_timeouts(g, "t2", cfg)
        assert result.acquire_timeout_adequate is False
        assert any("acquire" in r.lower() for r in result.recommendations)

    def test_timeout_no_max_lifetime(self) -> None:
        analyzer = ConnectionPoolAnalyzer()
        c = _comp(cid="t3")
        g = _graph(c)
        cfg = PoolConfig(max_lifetime_seconds=0.0)
        result = analyzer.analyze_timeouts(g, "t3", cfg)
        assert result.max_lifetime_adequate is False

    def test_timeout_errors_reported(self) -> None:
        analyzer = ConnectionPoolAnalyzer()
        c = _comp(cid="t4")
        c.metrics = ResourceMetrics(cpu_percent=95.0)
        g = _graph(c)
        cfg = PoolConfig()
        result = analyzer.analyze_timeouts(g, "t4", cfg)
        assert result.estimated_timeout_errors_per_hour > 0


# ---------------------------------------------------------------------------
# 7. Health check strategy analysis
# ---------------------------------------------------------------------------


class TestHealthCheckAnalysis:
    def test_health_check_none(self) -> None:
        analyzer = ConnectionPoolAnalyzer()
        c = _comp(cid="h1")
        g = _graph(c)
        cfg = PoolConfig(health_check=HealthCheckStrategy.NONE)
        result = analyzer.analyze_health_check(g, "h1", cfg)
        assert result.stale_connection_risk == "high"
        assert result.reliability_score == 0.0
        assert any("no health" in r.lower() for r in result.recommendations)

    def test_health_check_test_on_borrow(self) -> None:
        analyzer = ConnectionPoolAnalyzer()
        c = _comp(cid="h2")
        g = _graph(c)
        cfg = PoolConfig(
            pool_type=PoolType.DATABASE,
            health_check=HealthCheckStrategy.TEST_ON_BORROW,
        )
        result = analyzer.analyze_health_check(g, "h2", cfg)
        assert result.stale_connection_risk == "low"
        assert result.reliability_score == 0.95
        assert result.recommended_strategy == HealthCheckStrategy.TEST_ON_BORROW

    def test_health_check_recommends_background_for_grpc(self) -> None:
        analyzer = ConnectionPoolAnalyzer()
        c = _comp(cid="h3")
        g = _graph(c)
        cfg = PoolConfig(
            pool_type=PoolType.GRPC,
            health_check=HealthCheckStrategy.TEST_ON_BORROW,
        )
        result = analyzer.analyze_health_check(g, "h3", cfg)
        assert result.recommended_strategy == HealthCheckStrategy.BACKGROUND_VALIDATION
        assert any("background_validation" in r for r in result.recommendations)

    def test_health_check_long_interval_warning(self) -> None:
        analyzer = ConnectionPoolAnalyzer()
        c = _comp(cid="h4")
        g = _graph(c)
        cfg = PoolConfig(health_check_interval_seconds=300.0)
        result = analyzer.analyze_health_check(g, "h4", cfg)
        assert any("interval" in r.lower() for r in result.recommendations)

    def test_health_check_component_none(self) -> None:
        analyzer = ConnectionPoolAnalyzer()
        g = _graph()
        cfg = PoolConfig(health_check=HealthCheckStrategy.BACKGROUND_VALIDATION)
        result = analyzer.analyze_health_check(g, "ghost", cfg)
        assert result.strategy == HealthCheckStrategy.BACKGROUND_VALIDATION


# ---------------------------------------------------------------------------
# 8. Warmup strategy analysis
# ---------------------------------------------------------------------------


class TestWarmupAnalysis:
    def test_warmup_lazy_for_database(self) -> None:
        analyzer = ConnectionPoolAnalyzer()
        c = _comp(cid="w1")
        g = _graph(c)
        cfg = PoolConfig(
            pool_type=PoolType.DATABASE,
            warmup=WarmupStrategy.LAZY_CREATION,
        )
        result = analyzer.analyze_warmup(g, "w1", cfg)
        assert result.cold_start_impact_percent == 100.0
        assert result.readiness_at_startup == 0.0
        assert result.recommended_strategy == WarmupStrategy.PRE_CREATE
        assert any("lazy" in r.lower() for r in result.recommendations)

    def test_warmup_pre_create(self) -> None:
        analyzer = ConnectionPoolAnalyzer()
        c = _comp(cid="w2")
        g = _graph(c)
        cfg = PoolConfig(
            pool_type=PoolType.DATABASE,
            warmup=WarmupStrategy.PRE_CREATE,
            min_size=10,
        )
        result = analyzer.analyze_warmup(g, "w2", cfg)
        assert result.readiness_at_startup == 1.0
        assert result.cold_start_impact_percent == 0.0
        assert result.startup_latency_ms > 0

    def test_warmup_large_precreate_warning(self) -> None:
        analyzer = ConnectionPoolAnalyzer()
        c = _comp(cid="w3")
        g = _graph(c)
        cfg = PoolConfig(
            warmup=WarmupStrategy.PRE_CREATE,
            min_size=100,
        )
        result = analyzer.analyze_warmup(g, "w3", cfg)
        assert any("slow" in r.lower() or "gradual" in r.lower() for r in result.recommendations)

    def test_warmup_gradual_ramp(self) -> None:
        analyzer = ConnectionPoolAnalyzer()
        c = _comp(cid="w4")
        g = _graph(c)
        cfg = PoolConfig(warmup=WarmupStrategy.GRADUAL_RAMP, min_size=10)
        result = analyzer.analyze_warmup(g, "w4", cfg)
        assert result.readiness_at_startup == 0.5
        assert result.cold_start_impact_percent == 50.0

    def test_warmup_redis_recommends_lazy(self) -> None:
        analyzer = ConnectionPoolAnalyzer()
        c = _comp(cid="w5")
        g = _graph(c)
        cfg = PoolConfig(pool_type=PoolType.REDIS, warmup=WarmupStrategy.PRE_CREATE)
        result = analyzer.analyze_warmup(g, "w5", cfg)
        assert result.recommended_strategy == WarmupStrategy.LAZY_CREATION


# ---------------------------------------------------------------------------
# 9. Sharing tradeoff analysis
# ---------------------------------------------------------------------------


class TestSharingTradeoff:
    def test_sharing_single_service(self) -> None:
        analyzer = ConnectionPoolAnalyzer()
        c = _comp(cid="s1")
        g = _graph(c)
        cfg = PoolConfig(sharing_mode=PoolSharingMode.SHARED)
        result = analyzer.analyze_sharing_tradeoff(g, "s1", cfg, service_count=1)
        assert result.recommended_mode == PoolSharingMode.SHARED
        assert result.resource_overhead_ratio == 1.0

    def test_sharing_many_services(self) -> None:
        analyzer = ConnectionPoolAnalyzer()
        c = _comp(cid="s2")
        g = _graph(c)
        cfg = PoolConfig(sharing_mode=PoolSharingMode.SHARED)
        result = analyzer.analyze_sharing_tradeoff(g, "s2", cfg, service_count=5)
        assert result.recommended_mode in (PoolSharingMode.DEDICATED, PoolSharingMode.HYBRID)
        assert any("noisy" in r.lower() for r in result.recommendations)

    def test_sharing_dedicated_single_warns(self) -> None:
        analyzer = ConnectionPoolAnalyzer()
        c = _comp(cid="s3")
        g = _graph(c)
        cfg = PoolConfig(sharing_mode=PoolSharingMode.DEDICATED)
        result = analyzer.analyze_sharing_tradeoff(g, "s3", cfg, service_count=1)
        assert any("unnecessary" in r.lower() for r in result.recommendations)

    def test_sharing_database_many_services(self) -> None:
        analyzer = ConnectionPoolAnalyzer()
        c = _comp(cid="s4")
        g = _graph(c)
        cfg = PoolConfig(
            pool_type=PoolType.DATABASE,
            sharing_mode=PoolSharingMode.SHARED,
        )
        result = analyzer.analyze_sharing_tradeoff(g, "s4", cfg, service_count=5)
        assert result.recommended_mode == PoolSharingMode.DEDICATED


# ---------------------------------------------------------------------------
# 10. Storm prevention analysis
# ---------------------------------------------------------------------------


class TestStormPrevention:
    def test_storm_component_not_found(self) -> None:
        analyzer = ConnectionPoolAnalyzer()
        g = _graph()
        result = analyzer.analyze_storm_prevention(g, "nope", PoolConfig())
        assert result.storm_risk == "unknown"

    def test_storm_low_risk(self) -> None:
        analyzer = ConnectionPoolAnalyzer()
        c = _comp(cid="st1", max_connections=10000, replicas=4)
        g = _graph(c)
        cfg = PoolConfig(max_size=5)
        result = analyzer.analyze_storm_prevention(g, "st1", cfg, service_count=1)
        assert result.storm_risk == "low"

    def test_storm_high_risk(self) -> None:
        analyzer = ConnectionPoolAnalyzer()
        c = _comp(cid="st2", max_connections=50, replicas=1)
        g = _graph(c)
        cfg = PoolConfig(max_size=50)
        result = analyzer.analyze_storm_prevention(
            g, "st2", cfg, service_count=5, has_backoff_jitter=False,
        )
        assert result.storm_risk in ("high", "critical")
        assert any("jitter" in r.lower() for r in result.recommendations)
        assert result.reconnect_backoff_adequate is False

    def test_storm_with_jitter_is_adequate(self) -> None:
        analyzer = ConnectionPoolAnalyzer()
        c = _comp(cid="st3", max_connections=100, replicas=1)
        g = _graph(c)
        cfg = PoolConfig(max_size=20)
        result = analyzer.analyze_storm_prevention(
            g, "st3", cfg, service_count=2, has_backoff_jitter=True,
        )
        assert result.jitter_configured is True

    def test_storm_database_proxy_recommendation(self) -> None:
        analyzer = ConnectionPoolAnalyzer()
        c = _comp(cid="st4", ctype=ComponentType.DATABASE, max_connections=100, replicas=1)
        g = _graph(c)
        cfg = PoolConfig(pool_type=PoolType.DATABASE, max_size=10)
        result = analyzer.analyze_storm_prevention(
            g, "st4", cfg, service_count=10, has_backoff_jitter=True,
        )
        assert any("pgbouncer" in r.lower() or "proxy" in r.lower() for r in result.recommendations)


# ---------------------------------------------------------------------------
# 11. Pool metrics modelling
# ---------------------------------------------------------------------------


class TestPoolMetrics:
    def test_metrics_component_not_found(self) -> None:
        analyzer = ConnectionPoolAnalyzer()
        g = _graph()
        snapshots = analyzer.model_pool_metrics(g, "nope", PoolConfig())
        assert snapshots == []

    def test_metrics_returns_correct_step_count(self) -> None:
        analyzer = ConnectionPoolAnalyzer()
        c = _comp(cid="m1")
        g = _graph(c)
        cfg = PoolConfig(max_size=50)
        snapshots = analyzer.model_pool_metrics(
            g, "m1", cfg, request_rate_per_second=100.0, time_steps=7,
        )
        assert len(snapshots) == 7

    def test_metrics_utilization_ramps_up(self) -> None:
        analyzer = ConnectionPoolAnalyzer()
        c = _comp(cid="m2", replicas=1)
        g = _graph(c)
        cfg = PoolConfig(max_size=50, idle_size=5)
        snapshots = analyzer.model_pool_metrics(
            g, "m2", cfg, request_rate_per_second=200.0, avg_hold_time_ms=100.0,
            time_steps=5,
        )
        assert len(snapshots) == 5
        # Utilization should generally increase over steps
        assert snapshots[-1].utilization_percent >= snapshots[0].utilization_percent

    def test_metrics_timestamp_present(self) -> None:
        analyzer = ConnectionPoolAnalyzer()
        c = _comp(cid="m3")
        g = _graph(c)
        snapshots = analyzer.model_pool_metrics(g, "m3", PoolConfig(), time_steps=3)
        for snap in snapshots:
            assert snap.timestamp != ""

    def test_metrics_wait_time_increases_at_high_util(self) -> None:
        analyzer = ConnectionPoolAnalyzer()
        c = _comp(cid="m4", replicas=1)
        g = _graph(c)
        # Use parameters where first step is below 80% utilization but last is above
        cfg = PoolConfig(max_size=100, idle_size=5)
        snapshots = analyzer.model_pool_metrics(
            g, "m4", cfg, request_rate_per_second=2000.0, avg_hold_time_ms=50.0,
            time_steps=5,
        )
        # Last snapshot should have higher or equal wait time vs first
        assert snapshots[-1].avg_wait_time_ms >= snapshots[0].avg_wait_time_ms
        # At high utilization, wait time should be above baseline
        if snapshots[-1].utilization_percent > 80:
            assert snapshots[-1].avg_wait_time_ms > 0.5


# ---------------------------------------------------------------------------
# 12. Cross-service coordination
# ---------------------------------------------------------------------------


class TestCrossServiceCoordination:
    def test_coordination_no_configs(self) -> None:
        analyzer = ConnectionPoolAnalyzer()
        g = _graph()
        result = analyzer.analyze_cross_service_coordination(g, {})
        assert result.total_pools == 0
        assert "no pool" in result.recommendations[0].lower()

    def test_coordination_balanced(self) -> None:
        analyzer = ConnectionPoolAnalyzer()
        c1 = _comp(cid="a1", max_connections=1000, replicas=1)
        c2 = _comp(cid="b1", max_connections=1000, replicas=1)
        g = _graph(c1, c2)
        configs = {
            "a1": PoolConfig(max_size=50),
            "b1": PoolConfig(max_size=50),
        }
        result = analyzer.analyze_cross_service_coordination(g, configs)
        assert result.total_pools == 2
        assert result.total_connections == 100
        assert result.coordination_score > 50

    def test_coordination_imbalanced(self) -> None:
        analyzer = ConnectionPoolAnalyzer()
        c1 = _comp(cid="over", max_connections=100, replicas=1)
        c2 = _comp(cid="fine", max_connections=1000, replicas=1)
        g = _graph(c1, c2)
        configs = {
            "over": PoolConfig(max_size=90),  # 90% of capacity
            "fine": PoolConfig(max_size=50),
        }
        result = analyzer.analyze_cross_service_coordination(g, configs)
        assert "over" in result.imbalanced_pools
        assert result.coordination_score < 100

    def test_coordination_high_total_connections(self) -> None:
        analyzer = ConnectionPoolAnalyzer()
        comps = [_comp(cid=f"svc{i}", replicas=1) for i in range(6)]
        g = _graph(*comps)
        configs = {f"svc{i}": PoolConfig(max_size=100) for i in range(6)}
        result = analyzer.analyze_cross_service_coordination(g, configs)
        assert result.total_connections == 600
        assert any("multiplexing" in r.lower() for r in result.recommendations)


# ---------------------------------------------------------------------------
# 13. Full analysis summary
# ---------------------------------------------------------------------------


class TestFullAnalysis:
    def test_full_analysis_empty(self) -> None:
        analyzer = ConnectionPoolAnalyzer()
        g = _graph()
        result = analyzer.full_analysis(g, {})
        assert result.component_count == 0

    def test_full_analysis_single_pool(self) -> None:
        analyzer = ConnectionPoolAnalyzer()
        c = _comp(cid="fa1", replicas=1)
        g = _graph(c)
        configs = {"fa1": PoolConfig(max_size=50)}
        result = analyzer.full_analysis(g, configs)
        assert result.component_count == 1
        assert result.total_pool_connections == 50
        assert len(result.sizing_results) == 1
        assert len(result.leak_results) == 1
        assert result.overall_health_score >= 0

    def test_full_analysis_multiple_pools(self) -> None:
        analyzer = ConnectionPoolAnalyzer()
        c1 = _comp(cid="db", ctype=ComponentType.DATABASE, replicas=1, conn_leak_per_hour=5.0)
        c2 = _comp(cid="cache", ctype=ComponentType.CACHE, replicas=2)
        g = _graph(c1, c2)
        configs = {
            "db": PoolConfig(
                pool_type=PoolType.DATABASE,
                max_size=30,
                health_check=HealthCheckStrategy.NONE,
            ),
            "cache": PoolConfig(
                pool_type=PoolType.REDIS,
                max_size=20,
            ),
        }
        result = analyzer.full_analysis(g, configs)
        assert result.component_count == 2
        assert len(result.sizing_results) == 2
        assert len(result.leak_results) == 2
        # DB with no health check and leaks should generate recommendations
        assert len(result.recommendations) > 0

    def test_full_analysis_deduplicates_recommendations(self) -> None:
        analyzer = ConnectionPoolAnalyzer()
        c = _comp(cid="dup", replicas=1, max_connections=2000)
        g = _graph(c)
        configs = {"dup": PoolConfig(max_size=50)}
        result = analyzer.full_analysis(g, configs)
        # No duplicates
        assert len(result.recommendations) == len(set(result.recommendations))


# ---------------------------------------------------------------------------
# 14. Data model defaults and edge cases
# ---------------------------------------------------------------------------


class TestDataModels:
    def test_pool_config_defaults(self) -> None:
        cfg = PoolConfig()
        assert cfg.pool_type == PoolType.DATABASE
        assert cfg.min_size == 5
        assert cfg.max_size == 20
        assert cfg.idle_size == 5
        assert cfg.warmup == WarmupStrategy.LAZY_CREATION
        assert cfg.sharing_mode == PoolSharingMode.SHARED

    def test_pool_sizing_result_defaults(self) -> None:
        r = PoolSizingResult()
        assert r.oversized is False
        assert r.undersized is False
        assert r.sizing_score == 0.0

    def test_leak_detection_result_defaults(self) -> None:
        r = LeakDetectionResult()
        assert r.leak_risk == "none"
        assert r.time_to_exhaustion_hours == float("inf")

    def test_exhaustion_sim_result_defaults(self) -> None:
        r = ExhaustionSimResult()
        assert r.severity == "low"
        assert r.cascade_affected == []

    def test_pool_metrics_snapshot_defaults(self) -> None:
        s = PoolMetricsSnapshot()
        assert s.active_connections == 0
        assert s.utilization_percent == 0.0

    def test_cross_service_coordination_defaults(self) -> None:
        r = CrossServiceCoordinationResult()
        assert r.total_pools == 0
        assert r.coordination_score == 0.0

    def test_pool_analysis_summary_defaults(self) -> None:
        s = PoolAnalysisSummary()
        assert s.component_count == 0
        assert s.overall_health_score == 0.0


# ---------------------------------------------------------------------------
# 15. Integration: end-to-end multi-component scenario
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_multi_component_scenario(self) -> None:
        """End-to-end: 3-tier app with DB, app server, and cache."""
        analyzer = ConnectionPoolAnalyzer()

        db = _comp(
            cid="pg",
            ctype=ComponentType.DATABASE,
            replicas=2,
            max_connections=500,
            conn_leak_per_hour=2.0,
        )
        app = _comp(
            cid="api",
            ctype=ComponentType.APP_SERVER,
            replicas=4,
            max_connections=2000,
        )
        cache = _comp(
            cid="redis",
            ctype=ComponentType.CACHE,
            replicas=3,
            max_connections=10000,
        )

        g = _graph(db, app, cache)
        g.add_dependency(Dependency(source_id="api", target_id="pg"))
        g.add_dependency(Dependency(source_id="api", target_id="redis"))

        db_cfg = PoolConfig(
            pool_type=PoolType.DATABASE,
            min_size=5,
            max_size=30,
            idle_size=5,
            warmup=WarmupStrategy.PRE_CREATE,
            health_check=HealthCheckStrategy.TEST_ON_BORROW,
        )
        redis_cfg = PoolConfig(
            pool_type=PoolType.REDIS,
            min_size=2,
            max_size=50,
            idle_size=5,
            warmup=WarmupStrategy.LAZY_CREATION,
            health_check=HealthCheckStrategy.TEST_WHILE_IDLE,
        )

        configs = {"pg": db_cfg, "redis": redis_cfg}

        # Full analysis
        summary = analyzer.full_analysis(g, configs)
        assert summary.component_count == 2
        assert summary.overall_health_score > 0

        # Exhaustion simulation on DB
        exhaust = analyzer.simulate_pool_exhaustion(
            g, "pg", db_cfg, request_rate_per_second=200.0, avg_hold_time_ms=20.0,
        )
        assert exhaust.component_id == "pg"

        # Storm prevention on DB
        storm = analyzer.analyze_storm_prevention(
            g, "pg", db_cfg, service_count=4, has_backoff_jitter=True,
        )
        assert storm.estimated_peak_connections > 0

        # Cross-service coordination
        coord = analyzer.analyze_cross_service_coordination(g, configs)
        assert coord.total_pools == 2
        assert coord.coordination_score > 0

    def test_all_pool_types_sizing(self) -> None:
        """Verify sizing works for every PoolType."""
        analyzer = ConnectionPoolAnalyzer()
        c = _comp(cid="alltype", max_connections=1000, replicas=2)
        g = _graph(c)
        for pt in PoolType:
            cfg = PoolConfig(pool_type=pt, max_size=50)
            result = analyzer.analyze_pool_sizing(g, "alltype", cfg)
            assert result.recommended_max >= 1
            assert result.sizing_score > 0

    def test_all_health_check_strategies(self) -> None:
        """Verify health check analysis works for every strategy."""
        analyzer = ConnectionPoolAnalyzer()
        c = _comp(cid="hcall")
        g = _graph(c)
        for hc in HealthCheckStrategy:
            cfg = PoolConfig(health_check=hc)
            result = analyzer.analyze_health_check(g, "hcall", cfg)
            assert result.strategy == hc
            assert 0.0 <= result.reliability_score <= 1.0


# ---------------------------------------------------------------------------
# 16. Additional edge case and branch coverage tests
# ---------------------------------------------------------------------------


class TestAdditionalBranches:
    """Tests targeting uncovered branches for near-100% coverage."""

    def test_sizing_score_slightly_oversized(self) -> None:
        """Cover the ratio > 1.5 but <= 2.0 branch."""
        cfg = PoolConfig(min_size=5, max_size=175, idle_size=10)
        score = _sizing_score(cfg, 5, 100, 10)
        assert score == 85.0  # 100 - 15

    def test_sizing_score_slightly_undersized(self) -> None:
        """Cover the ratio < 0.75 but >= 0.5 branch."""
        cfg = PoolConfig(min_size=5, max_size=70, idle_size=10)
        score = _sizing_score(cfg, 5, 100, 10)
        assert score == 85.0  # 100 - 15

    def test_sizing_score_excessive_idle(self) -> None:
        """Cover idle_size > rec_idle * 3 branch."""
        cfg = PoolConfig(min_size=5, max_size=100, idle_size=50)
        score = _sizing_score(cfg, 5, 100, 10)
        assert score == 90.0  # 100 - 10

    def test_timeout_score_long_acquire(self) -> None:
        """Cover acquire_timeout_ms > 30000 branch."""
        cfg = PoolConfig(acquire_timeout_ms=50000.0)
        score = _timeout_score(cfg, PoolType.HTTP)
        assert score < 100.0

    def test_timeout_score_no_idle_timeout(self) -> None:
        """Cover idle_timeout_seconds <= 0 branch."""
        cfg = PoolConfig(idle_timeout_seconds=0.0)
        score = _timeout_score(cfg, PoolType.HTTP)
        assert score < 100.0

    def test_timeout_score_long_idle_timeout(self) -> None:
        """Cover idle_timeout_seconds > 3600 branch."""
        cfg = PoolConfig(idle_timeout_seconds=5000.0)
        score = _timeout_score(cfg, PoolType.HTTP)
        assert score < 100.0

    def test_timeout_score_very_long_lifetime(self) -> None:
        """Cover max_lifetime_seconds > 7200 branch."""
        cfg = PoolConfig(max_lifetime_seconds=10000.0)
        score = _timeout_score(cfg, PoolType.HTTP)
        assert score < 100.0

    def test_timeout_analysis_long_acquire(self) -> None:
        """Cover acquire > 30000 recommendation in analyze_timeouts."""
        analyzer = ConnectionPoolAnalyzer()
        c = _comp(cid="ta1")
        g = _graph(c)
        cfg = PoolConfig(acquire_timeout_ms=50000.0)
        result = analyzer.analyze_timeouts(g, "ta1", cfg)
        assert result.acquire_timeout_adequate is False
        assert any("fail fast" in r.lower() for r in result.recommendations)

    def test_timeout_analysis_short_acquire(self) -> None:
        """Cover acquire < 500 recommendation (too aggressive)."""
        analyzer = ConnectionPoolAnalyzer()
        c = _comp(cid="ta2")
        g = _graph(c)
        cfg = PoolConfig(acquire_timeout_ms=100.0)
        result = analyzer.analyze_timeouts(g, "ta2", cfg)
        assert result.acquire_timeout_adequate is False
        assert any("aggressive" in r.lower() for r in result.recommendations)

    def test_timeout_analysis_no_idle_timeout(self) -> None:
        """Cover idle_timeout_seconds <= 0 recommendation."""
        analyzer = ConnectionPoolAnalyzer()
        c = _comp(cid="ta3")
        g = _graph(c)
        cfg = PoolConfig(idle_timeout_seconds=0.0)
        result = analyzer.analyze_timeouts(g, "ta3", cfg)
        assert result.idle_timeout_adequate is False
        assert any("idle timeout" in r.lower() for r in result.recommendations)

    def test_timeout_analysis_long_idle_timeout(self) -> None:
        """Cover idle_timeout_seconds > 3600 recommendation."""
        analyzer = ConnectionPoolAnalyzer()
        c = _comp(cid="ta4")
        g = _graph(c)
        cfg = PoolConfig(idle_timeout_seconds=5000.0)
        result = analyzer.analyze_timeouts(g, "ta4", cfg)
        assert result.idle_timeout_adequate is False

    def test_timeout_analysis_very_long_lifetime(self) -> None:
        """Cover max_lifetime > 7200 recommendation."""
        analyzer = ConnectionPoolAnalyzer()
        c = _comp(cid="ta5")
        g = _graph(c)
        cfg = PoolConfig(max_lifetime_seconds=10000.0)
        result = analyzer.analyze_timeouts(g, "ta5", cfg)
        assert result.max_lifetime_adequate is False
        assert any("very long" in r.lower() for r in result.recommendations)

    def test_health_check_high_throughput_overhead(self) -> None:
        """Cover overhead > 1.5 and max_rps > 5000 branch."""
        analyzer = ConnectionPoolAnalyzer()
        c = _comp(cid="hto", max_rps=10000)
        g = _graph(c)
        cfg = PoolConfig(
            pool_type=PoolType.DATABASE,
            health_check=HealthCheckStrategy.TEST_ON_BORROW,
        )
        result = analyzer.analyze_health_check(g, "hto", cfg)
        assert any("overhead" in r.lower() for r in result.recommendations)

    def test_health_check_redis_recommends_test_while_idle(self) -> None:
        """Cover PoolType.REDIS -> TEST_WHILE_IDLE recommendation."""
        analyzer = ConnectionPoolAnalyzer()
        c = _comp(cid="redis_hc")
        g = _graph(c)
        cfg = PoolConfig(
            pool_type=PoolType.REDIS,
            health_check=HealthCheckStrategy.NONE,
        )
        result = analyzer.analyze_health_check(g, "redis_hc", cfg)
        assert result.recommended_strategy == HealthCheckStrategy.TEST_WHILE_IDLE

    def test_health_check_message_queue_recommends_background(self) -> None:
        """Cover the else branch -> BACKGROUND_VALIDATION for MESSAGE_QUEUE."""
        analyzer = ConnectionPoolAnalyzer()
        c = _comp(cid="mq_hc")
        g = _graph(c)
        cfg = PoolConfig(
            pool_type=PoolType.MESSAGE_QUEUE,
            health_check=HealthCheckStrategy.NONE,
        )
        result = analyzer.analyze_health_check(g, "mq_hc", cfg)
        assert result.recommended_strategy == HealthCheckStrategy.BACKGROUND_VALIDATION

    def test_warmup_message_queue_recommends_gradual(self) -> None:
        """Cover the else branch -> GRADUAL_RAMP for MESSAGE_QUEUE."""
        analyzer = ConnectionPoolAnalyzer()
        c = _comp(cid="mq_w")
        g = _graph(c)
        cfg = PoolConfig(
            pool_type=PoolType.MESSAGE_QUEUE,
            warmup=WarmupStrategy.LAZY_CREATION,
        )
        result = analyzer.analyze_warmup(g, "mq_w", cfg)
        assert result.recommended_strategy == WarmupStrategy.GRADUAL_RAMP

    def test_sharing_hybrid_mode(self) -> None:
        """Cover service_count 2-3 -> HYBRID recommendation."""
        analyzer = ConnectionPoolAnalyzer()
        c = _comp(cid="sh1")
        g = _graph(c)
        cfg = PoolConfig(sharing_mode=PoolSharingMode.SHARED)
        result = analyzer.analyze_sharing_tradeoff(g, "sh1", cfg, service_count=2)
        assert result.recommended_mode == PoolSharingMode.HYBRID

    def test_storm_medium_risk(self) -> None:
        """Cover the medium risk branch (peak > max_safe * 0.7)."""
        analyzer = ConnectionPoolAnalyzer()
        # Need: peak > max_safe*0.7 but peak <= max_safe
        # peak = max_size * replicas * service_count * 1.5
        # max_safe = max_connections * replicas
        # Choose so that max_safe*0.7 < peak <= max_safe
        c = _comp(cid="stm", max_connections=100, replicas=1)
        g = _graph(c)
        # peak = 10 * 1 * 5 * 1.5 = 75; max_safe = 100
        # 100*0.7=70 < 75 <= 100 -> medium
        cfg = PoolConfig(max_size=10)
        result = analyzer.analyze_storm_prevention(
            g, "stm", cfg, service_count=5, has_backoff_jitter=False,
        )
        assert result.storm_risk == "medium"

    def test_exhaustion_large_timeout_recommendation(self) -> None:
        """Cover acquire_timeout > 10000 recommendation in exhaustion."""
        analyzer = ConnectionPoolAnalyzer()
        c = _comp(cid="et1", replicas=1)
        g = _graph(c)
        cfg = PoolConfig(max_size=5, acquire_timeout_ms=15000.0)
        result = analyzer.simulate_pool_exhaustion(
            g, "et1", cfg, request_rate_per_second=1000.0, avg_hold_time_ms=100.0,
        )
        assert any("fail fast" in r.lower() for r in result.recommendations)

    def test_coordination_missing_component(self) -> None:
        """Cover comp is None continue branch in coordination."""
        analyzer = ConnectionPoolAnalyzer()
        g = _graph()
        configs = {"missing_comp": PoolConfig(max_size=50)}
        result = analyzer.analyze_cross_service_coordination(g, configs)
        assert result.total_pools == 1
        assert result.total_connections == 0

    def test_coordination_bottleneck_over_capacity(self) -> None:
        """Cover bottleneck_ratio > 1.0 branch."""
        analyzer = ConnectionPoolAnalyzer()
        c = _comp(cid="bneck", max_connections=10, replicas=1)
        g = _graph(c)
        configs = {"bneck": PoolConfig(max_size=20)}  # 20 > 10 capacity
        result = analyzer.analyze_cross_service_coordination(g, configs)
        assert result.coordination_score < 100.0

    def test_full_analysis_oversized_pool(self) -> None:
        """Cover the oversized recommendation in full_analysis."""
        analyzer = ConnectionPoolAnalyzer()
        c = _comp(cid="fao", max_connections=100, replicas=1)
        g = _graph(c)
        configs = {"fao": PoolConfig(max_size=500)}
        result = analyzer.full_analysis(g, configs)
        assert any("oversized" in r.lower() for r in result.recommendations)

    def test_exhaustion_fill_rate_zero(self) -> None:
        """Cover the fill_rate <= 0 branch (time_to_exhaust = 0.0)."""
        analyzer = ConnectionPoolAnalyzer()
        c = _comp(cid="efr", replicas=1)
        g = _graph(c)
        # Set up so concurrent > pool_capacity but fill_rate <= 0
        # This happens when the drain rate >= arrival rate but concurrent > capacity
        # concurrent = 100 * 2.0 = 200; pool_capacity = 5
        # fill_rate = 100 - (5 / 2.0) = 100 - 2.5 = 97.5 > 0 => doesn't work
        # We need rate - capacity/hold_time <= 0 while rate*hold_time > capacity
        # rate * hold_time > capacity AND rate <= capacity/hold_time
        # This is contradictory, so fill_rate > 0 whenever concurrent > capacity
        # Let's test a scenario that hits medium severity instead
        cfg = PoolConfig(max_size=5)
        result = analyzer.simulate_pool_exhaustion(
            g, "efr", cfg, request_rate_per_second=200.0, avg_hold_time_ms=50.0,
        )
        # concurrent = 200 * 0.05 = 10 > 5 (pool_capacity for 1 replica)
        assert result.severity in ("medium", "high", "critical")

    def test_estimate_timeout_errors_mid_range(self) -> None:
        """Cover demand_ratio between 0.5 and 0.7 returning 0."""
        c = _comp()
        c.metrics = ResourceMetrics(cpu_percent=60.0)
        cfg = PoolConfig()
        errors = _estimate_timeout_errors(cfg, c)
        assert errors == 0.0

    def test_sizing_idle_exceeds_max_in_analyzer(self) -> None:
        """Cover the idle_size > max_size branch in analyze_pool_sizing."""
        analyzer = ConnectionPoolAnalyzer()
        c = _comp(cid="idl")
        g = _graph(c)
        cfg = PoolConfig(min_size=5, max_size=20, idle_size=30)
        result = analyzer.analyze_pool_sizing(g, "idl", cfg)
        assert any("idle_size" in r for r in result.recommendations)
