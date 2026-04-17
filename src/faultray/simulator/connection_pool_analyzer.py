# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Connection Pool Analyzer.

Analyzes connection pool configurations and their impact on reliability.
Supports database, HTTP, gRPC, message queue, and Redis pool types.
Evaluates pool sizing, leak detection, exhaustion scenarios, timeout
analysis, health checking strategies, warmup strategies, cross-service
coordination, connection storm prevention, and pool metrics modelling.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

from faultray.model.components import Component
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class PoolType(str, Enum):
    """Supported connection pool types."""

    DATABASE = "database"
    HTTP = "http"
    GRPC = "grpc"
    MESSAGE_QUEUE = "message_queue"
    REDIS = "redis"


class HealthCheckStrategy(str, Enum):
    """Connection health checking strategies."""

    TEST_ON_BORROW = "test_on_borrow"
    TEST_ON_RETURN = "test_on_return"
    BACKGROUND_VALIDATION = "background_validation"
    TEST_WHILE_IDLE = "test_while_idle"
    NONE = "none"


class WarmupStrategy(str, Enum):
    """Pool warmup (initialization) strategies."""

    PRE_CREATE = "pre_create"
    LAZY_CREATION = "lazy_creation"
    GRADUAL_RAMP = "gradual_ramp"


class PoolSharingMode(str, Enum):
    """Pool sharing vs dedicated pool mode."""

    SHARED = "shared"
    DEDICATED = "dedicated"
    HYBRID = "hybrid"


# ---------------------------------------------------------------------------
# Constants / lookup tables
# ---------------------------------------------------------------------------

# Base connection overhead per pool type (ms per connection create)
_POOL_CREATION_OVERHEAD_MS: dict[PoolType, float] = {
    PoolType.DATABASE: 50.0,
    PoolType.HTTP: 5.0,
    PoolType.GRPC: 15.0,
    PoolType.MESSAGE_QUEUE: 30.0,
    PoolType.REDIS: 3.0,
}

# Ideal idle-to-max ratio by pool type
_IDEAL_IDLE_RATIO: dict[PoolType, float] = {
    PoolType.DATABASE: 0.25,
    PoolType.HTTP: 0.10,
    PoolType.GRPC: 0.20,
    PoolType.MESSAGE_QUEUE: 0.15,
    PoolType.REDIS: 0.10,
}

# Health check overhead per strategy (ms per check)
_HEALTH_CHECK_OVERHEAD_MS: dict[HealthCheckStrategy, float] = {
    HealthCheckStrategy.TEST_ON_BORROW: 2.0,
    HealthCheckStrategy.TEST_ON_RETURN: 1.5,
    HealthCheckStrategy.BACKGROUND_VALIDATION: 0.5,
    HealthCheckStrategy.TEST_WHILE_IDLE: 0.3,
    HealthCheckStrategy.NONE: 0.0,
}

# Health check reliability score (how well stale connections are detected)
_HEALTH_CHECK_RELIABILITY: dict[HealthCheckStrategy, float] = {
    HealthCheckStrategy.TEST_ON_BORROW: 0.95,
    HealthCheckStrategy.TEST_ON_RETURN: 0.70,
    HealthCheckStrategy.BACKGROUND_VALIDATION: 0.90,
    HealthCheckStrategy.TEST_WHILE_IDLE: 0.80,
    HealthCheckStrategy.NONE: 0.0,
}

# Warmup speed factor (fraction of pool ready at startup, 0-1)
_WARMUP_READINESS: dict[WarmupStrategy, float] = {
    WarmupStrategy.PRE_CREATE: 1.0,
    WarmupStrategy.LAZY_CREATION: 0.0,
    WarmupStrategy.GRADUAL_RAMP: 0.5,
}


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class PoolConfig(BaseModel):
    """Configuration for a connection pool."""

    pool_type: PoolType = PoolType.DATABASE
    min_size: int = Field(default=5, ge=0)
    max_size: int = Field(default=20, ge=1)
    idle_size: int = Field(default=5, ge=0)
    acquire_timeout_ms: float = Field(default=5000.0, ge=0.0)
    idle_timeout_seconds: float = Field(default=600.0, ge=0.0)
    max_lifetime_seconds: float = Field(default=1800.0, ge=0.0)
    health_check: HealthCheckStrategy = HealthCheckStrategy.TEST_ON_BORROW
    warmup: WarmupStrategy = WarmupStrategy.LAZY_CREATION
    sharing_mode: PoolSharingMode = PoolSharingMode.SHARED
    health_check_interval_seconds: float = Field(default=30.0, ge=0.0)
    max_wait_queue_size: int = Field(default=100, ge=0)
    validation_query: str = ""


class PoolSizingResult(BaseModel):
    """Result of pool sizing analysis."""

    component_id: str = ""
    pool_type: PoolType = PoolType.DATABASE
    current_min: int = 0
    current_max: int = 0
    current_idle: int = 0
    recommended_min: int = 0
    recommended_max: int = 0
    recommended_idle: int = 0
    sizing_score: float = Field(default=0.0, ge=0.0, le=100.0)
    oversized: bool = False
    undersized: bool = False
    recommendations: list[str] = Field(default_factory=list)


class LeakDetectionResult(BaseModel):
    """Result of connection leak detection analysis."""

    component_id: str = ""
    leak_risk: str = "none"
    leaked_connections_estimate: int = 0
    leak_rate_per_hour: float = 0.0
    time_to_exhaustion_hours: float = Field(default=float("inf"))
    detection_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    recommendations: list[str] = Field(default_factory=list)


class ExhaustionSimResult(BaseModel):
    """Result of pool exhaustion simulation."""

    component_id: str = ""
    time_to_exhaustion_seconds: float = 0.0
    requests_queued: int = 0
    requests_rejected: int = 0
    cascade_affected: list[str] = Field(default_factory=list)
    severity: str = "low"
    recovery_time_seconds: float = 0.0
    recommendations: list[str] = Field(default_factory=list)


class TimeoutAnalysisResult(BaseModel):
    """Result of connection timeout analysis."""

    component_id: str = ""
    acquire_timeout_adequate: bool = True
    idle_timeout_adequate: bool = True
    max_lifetime_adequate: bool = True
    timeout_score: float = Field(default=100.0, ge=0.0, le=100.0)
    estimated_timeout_errors_per_hour: float = 0.0
    recommendations: list[str] = Field(default_factory=list)


class HealthCheckAnalysisResult(BaseModel):
    """Result of health check strategy analysis."""

    strategy: HealthCheckStrategy = HealthCheckStrategy.NONE
    overhead_ms: float = 0.0
    reliability_score: float = Field(default=0.0, ge=0.0, le=1.0)
    stale_connection_risk: str = "high"
    recommended_strategy: HealthCheckStrategy = HealthCheckStrategy.TEST_ON_BORROW
    recommendations: list[str] = Field(default_factory=list)


class WarmupAnalysisResult(BaseModel):
    """Result of pool warmup strategy analysis."""

    strategy: WarmupStrategy = WarmupStrategy.LAZY_CREATION
    startup_latency_ms: float = 0.0
    cold_start_impact_percent: float = 0.0
    readiness_at_startup: float = 0.0
    recommended_strategy: WarmupStrategy = WarmupStrategy.PRE_CREATE
    recommendations: list[str] = Field(default_factory=list)


class SharingTradeoffResult(BaseModel):
    """Result of shared vs dedicated pool tradeoff analysis."""

    current_mode: PoolSharingMode = PoolSharingMode.SHARED
    recommended_mode: PoolSharingMode = PoolSharingMode.SHARED
    shared_efficiency: float = Field(default=0.0, ge=0.0, le=100.0)
    dedicated_isolation: float = Field(default=0.0, ge=0.0, le=100.0)
    resource_overhead_ratio: float = 0.0
    recommendations: list[str] = Field(default_factory=list)


class StormPreventionResult(BaseModel):
    """Result of connection storm (thundering herd) prevention analysis."""

    storm_risk: str = "low"
    estimated_peak_connections: int = 0
    max_safe_connections: int = 0
    reconnect_backoff_adequate: bool = True
    jitter_configured: bool = False
    recommendations: list[str] = Field(default_factory=list)


class PoolMetricsSnapshot(BaseModel):
    """Modelled pool metrics at a point in time."""

    timestamp: str = ""
    active_connections: int = 0
    idle_connections: int = 0
    waiting_threads: int = 0
    total_connections: int = 0
    utilization_percent: float = Field(default=0.0, ge=0.0, le=100.0)
    avg_wait_time_ms: float = 0.0
    avg_use_time_ms: float = 0.0
    created_count: int = 0
    destroyed_count: int = 0


class CrossServiceCoordinationResult(BaseModel):
    """Result of cross-service connection pool coordination analysis."""

    total_pools: int = 0
    total_connections: int = 0
    bottleneck_component: str = ""
    coordination_score: float = Field(default=0.0, ge=0.0, le=100.0)
    imbalanced_pools: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class PoolAnalysisSummary(BaseModel):
    """Overall summary of connection pool analysis for a graph."""

    component_count: int = 0
    total_pool_connections: int = 0
    overall_health_score: float = Field(default=0.0, ge=0.0, le=100.0)
    sizing_results: list[PoolSizingResult] = Field(default_factory=list)
    leak_results: list[LeakDetectionResult] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    """Clamp *value* to [lo, hi]."""
    return max(lo, min(hi, value))


def _effective_connections(component: Component) -> int:
    """Return the effective connection pool size for a component."""
    return component.capacity.connection_pool_size * component.replicas


def _compute_leak_rate(
    config: PoolConfig,
    component: Component,
) -> float:
    """Estimate connection leak rate (leaked connections per hour).

    Components with no health check or long idle timeouts are more
    susceptible to leaks.
    """
    base_rate = component.operational_profile.degradation.connection_leak_per_hour

    # Health check reduces leak impact
    reliability = _HEALTH_CHECK_RELIABILITY.get(config.health_check, 0.0)
    effective_rate = base_rate * (1.0 - reliability)

    # Long idle timeouts increase the window for leaks to accumulate
    if config.idle_timeout_seconds > 1200:
        effective_rate *= 1.3
    elif config.idle_timeout_seconds < 60:
        effective_rate *= 0.7

    return max(0.0, effective_rate)


def _recommend_pool_size(
    pool_type: PoolType,
    component: Component,
    config: PoolConfig,
) -> tuple[int, int, int]:
    """Recommend (min, max, idle) pool sizes.

    Returns a tuple of (recommended_min, recommended_max, recommended_idle).
    """
    max_conns = component.capacity.max_connections
    replicas = component.replicas

    # Per-replica target max based on type
    overhead = _POOL_CREATION_OVERHEAD_MS.get(pool_type, 10.0)
    # Heavier connections need fewer but more persistent pools
    if overhead >= 30.0:
        target_max = max(10, int(max_conns / max(replicas, 1) * 0.3))
    else:
        target_max = max(10, int(max_conns / max(replicas, 1) * 0.5))

    ideal_idle_ratio = _IDEAL_IDLE_RATIO.get(pool_type, 0.15)
    target_idle = max(1, int(target_max * ideal_idle_ratio))
    target_min = max(1, target_idle)

    return target_min, target_max, target_idle


def _sizing_score(config: PoolConfig, rec_min: int, rec_max: int, rec_idle: int) -> float:
    """Score how close current config is to recommended (0-100)."""
    score = 100.0

    # Penalize max size deviation
    if config.max_size > 0 and rec_max > 0:
        ratio = config.max_size / rec_max
        if ratio > 2.0:
            score -= 30.0  # grossly oversized
        elif ratio > 1.5:
            score -= 15.0
        elif ratio < 0.5:
            score -= 30.0  # grossly undersized
        elif ratio < 0.75:
            score -= 15.0

    # Penalize min size issues
    if config.min_size > config.max_size:
        score -= 20.0
    if config.idle_size > config.max_size:
        score -= 15.0

    # Penalize idle > recommended idle by a lot
    if rec_idle > 0 and config.idle_size > rec_idle * 3:
        score -= 10.0

    return _clamp(score)


def _timeout_score(config: PoolConfig, pool_type: PoolType) -> float:
    """Score the timeout configuration (0-100)."""
    score = 100.0

    # Acquire timeout
    if config.acquire_timeout_ms <= 0:
        score -= 25.0  # no timeout is dangerous
    elif config.acquire_timeout_ms > 30000:
        score -= 15.0  # too long; threads block excessively
    elif config.acquire_timeout_ms < 500:
        score -= 10.0  # too aggressive; spurious errors

    # Idle timeout
    if config.idle_timeout_seconds <= 0:
        score -= 15.0  # connections never reaped
    elif config.idle_timeout_seconds > 3600:
        score -= 10.0  # stale connections accumulate

    # Max lifetime
    if config.max_lifetime_seconds <= 0:
        score -= 20.0  # no rotation; stale/leaked connections linger
    elif config.max_lifetime_seconds > 7200:
        score -= 10.0  # too long

    # Database connections need longer acquire timeout
    if pool_type == PoolType.DATABASE and config.acquire_timeout_ms < 1000:
        score -= 10.0

    return _clamp(score)


def _estimate_timeout_errors(config: PoolConfig, component: Component) -> float:
    """Estimate timeout errors per hour based on config and load."""
    max_rps = component.capacity.max_rps * component.replicas
    pool_max = config.max_size * component.replicas
    utilization = component.utilization()

    # If utilization is low, few timeout errors
    if utilization < 50 and max_rps > 0:
        return 0.0

    # Simple model: errors when demand approaches pool capacity
    demand_ratio = utilization / 100.0
    if demand_ratio < 0.7:
        return 0.0

    # Errors increase exponentially as demand approaches capacity
    overflow_factor = max(0.0, demand_ratio - 0.7) / 0.3
    base_errors = overflow_factor ** 2 * pool_max * 3600 / max(config.acquire_timeout_ms, 1.0)

    return round(max(0.0, base_errors), 2)


def _storm_peak_connections(
    config: PoolConfig,
    component: Component,
    service_count: int,
) -> int:
    """Estimate peak connections during a reconnection storm."""
    pool_max = config.max_size
    replicas = component.replicas
    # All services try to reconnect simultaneously
    peak = pool_max * replicas * max(service_count, 1)
    # Without jitter/backoff, overshoot by 1.5x
    return int(peak * 1.5)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class ConnectionPoolAnalyzer:
    """Stateless analyzer for connection pool configurations."""

    # -- pool sizing -------------------------------------------------------

    def analyze_pool_sizing(
        self,
        graph: InfraGraph,
        component_id: str,
        config: PoolConfig,
    ) -> PoolSizingResult:
        """Analyze whether the pool sizing is appropriate for the component."""
        comp = graph.get_component(component_id)
        if comp is None:
            return PoolSizingResult(
                component_id=component_id,
                recommendations=["Component not found in graph"],
            )

        rec_min, rec_max, rec_idle = _recommend_pool_size(
            config.pool_type, comp, config,
        )
        score = _sizing_score(config, rec_min, rec_max, rec_idle)

        oversized = config.max_size > rec_max * 1.5
        undersized = config.max_size < rec_max * 0.5

        recs: list[str] = []
        if oversized:
            recs.append(
                f"Pool max_size ({config.max_size}) is significantly larger "
                f"than recommended ({rec_max}); reduce to save resources"
            )
        if undersized:
            recs.append(
                f"Pool max_size ({config.max_size}) is below recommended "
                f"({rec_max}); increase to avoid exhaustion under load"
            )
        if config.min_size > config.max_size:
            recs.append("min_size exceeds max_size; fix configuration")
        if config.idle_size > config.max_size:
            recs.append("idle_size exceeds max_size; reduce idle_size")
        if config.min_size == 0 and config.pool_type == PoolType.DATABASE:
            recs.append(
                "Database pool min_size is 0; set a minimum to avoid "
                "cold-start latency on first request"
            )
        if not recs:
            recs.append("Pool sizing is within recommended range")

        return PoolSizingResult(
            component_id=component_id,
            pool_type=config.pool_type,
            current_min=config.min_size,
            current_max=config.max_size,
            current_idle=config.idle_size,
            recommended_min=rec_min,
            recommended_max=rec_max,
            recommended_idle=rec_idle,
            sizing_score=round(score, 1),
            oversized=oversized,
            undersized=undersized,
            recommendations=recs,
        )

    # -- leak detection ----------------------------------------------------

    def detect_connection_leaks(
        self,
        graph: InfraGraph,
        component_id: str,
        config: PoolConfig,
        observation_hours: float = 24.0,
    ) -> LeakDetectionResult:
        """Analyze the risk of connection leaks for a component."""
        comp = graph.get_component(component_id)
        if comp is None:
            return LeakDetectionResult(
                component_id=component_id,
                leak_risk="unknown",
                recommendations=["Component not found in graph"],
            )

        leak_rate = _compute_leak_rate(config, comp)
        leaked_estimate = int(leak_rate * observation_hours)
        pool_capacity = config.max_size * comp.replicas

        if leak_rate > 0 and pool_capacity > 0:
            time_to_exhaust = pool_capacity / leak_rate
        else:
            time_to_exhaust = float("inf")

        # Determine risk level
        if leak_rate <= 0:
            risk = "none"
            confidence = 0.0
        elif leaked_estimate < pool_capacity * 0.1:
            risk = "low"
            confidence = 0.3
        elif leaked_estimate < pool_capacity * 0.5:
            risk = "medium"
            confidence = 0.6
        else:
            risk = "high"
            confidence = 0.85

        # Increase confidence if health check is NONE
        if config.health_check == HealthCheckStrategy.NONE:
            confidence = min(1.0, confidence + 0.15)

        recs: list[str] = []
        if risk in ("medium", "high"):
            recs.append(
                "Enable connection leak detection with stack trace logging "
                "for unreturned connections"
            )
        if config.health_check == HealthCheckStrategy.NONE:
            recs.append(
                "Enable health checking to detect and evict stale/leaked "
                "connections"
            )
        if config.max_lifetime_seconds <= 0:
            recs.append(
                "Set max_lifetime_seconds to force connection rotation and "
                "limit leak accumulation"
            )
        if risk == "none":
            recs.append("No connection leak risk detected")

        return LeakDetectionResult(
            component_id=component_id,
            leak_risk=risk,
            leaked_connections_estimate=leaked_estimate,
            leak_rate_per_hour=round(leak_rate, 4),
            time_to_exhaustion_hours=round(time_to_exhaust, 2)
            if time_to_exhaust != float("inf")
            else float("inf"),
            detection_confidence=round(confidence, 2),
            recommendations=recs,
        )

    # -- pool exhaustion ---------------------------------------------------

    def simulate_pool_exhaustion(
        self,
        graph: InfraGraph,
        component_id: str,
        config: PoolConfig,
        request_rate_per_second: float = 100.0,
        avg_hold_time_ms: float = 50.0,
    ) -> ExhaustionSimResult:
        """Simulate what happens when the pool reaches max connections."""
        comp = graph.get_component(component_id)
        if comp is None:
            return ExhaustionSimResult(
                component_id=component_id,
                severity="unknown",
                recommendations=["Component not found in graph"],
            )

        pool_capacity = config.max_size * comp.replicas

        # Connections in use at steady state = rate * hold_time
        concurrent = request_rate_per_second * (avg_hold_time_ms / 1000.0)

        if concurrent <= pool_capacity:
            # Pool is not exhausted
            return ExhaustionSimResult(
                component_id=component_id,
                time_to_exhaustion_seconds=0.0,
                requests_queued=0,
                requests_rejected=0,
                severity="none",
                recommendations=[
                    "Pool can handle the given request rate without exhaustion"
                ],
            )

        # Time until exhaustion from empty pool
        fill_rate = request_rate_per_second - (
            pool_capacity / max(avg_hold_time_ms / 1000.0, 0.001)
        )
        if fill_rate > 0:
            time_to_exhaust = pool_capacity / fill_rate
        else:
            time_to_exhaust = 0.0

        # Excess requests go to wait queue, then rejected
        excess_rps = request_rate_per_second - (
            pool_capacity / max(avg_hold_time_ms / 1000.0, 0.001)
        )
        excess_rps = max(0.0, excess_rps)

        queued = min(int(excess_rps * (config.acquire_timeout_ms / 1000.0)),
                     config.max_wait_queue_size)
        rejected = max(0, int(excess_rps * 60) - queued)

        # Cascade: find components that depend on this one
        cascade = list(graph.get_all_affected(component_id))

        # Severity
        if excess_rps > pool_capacity * 0.5:
            severity = "critical"
        elif excess_rps > pool_capacity * 0.2:
            severity = "high"
        elif excess_rps > 0:
            severity = "medium"
        else:
            severity = "low"

        # Recovery time: drain time + reconnect overhead
        creation_overhead = _POOL_CREATION_OVERHEAD_MS.get(config.pool_type, 10.0)
        recovery = (pool_capacity * creation_overhead / 1000.0) + 5.0

        recs: list[str] = []
        if severity in ("critical", "high"):
            recs.append(
                f"Pool exhaustion is {severity}; increase max_size or add "
                "replicas to handle the request rate"
            )
        if config.acquire_timeout_ms > 10000:
            recs.append(
                "Reduce acquire_timeout to fail fast and avoid thread starvation"
            )
        if len(cascade) > 0:
            recs.append(
                f"Pool exhaustion cascades to {len(cascade)} upstream "
                "component(s); add circuit breakers"
            )
        if comp.replicas <= 1:
            recs.append("Add replicas to distribute connection load")

        return ExhaustionSimResult(
            component_id=component_id,
            time_to_exhaustion_seconds=round(max(0.0, time_to_exhaust), 2),
            requests_queued=queued,
            requests_rejected=rejected,
            cascade_affected=cascade,
            severity=severity,
            recovery_time_seconds=round(recovery, 2),
            recommendations=recs,
        )

    # -- timeout analysis --------------------------------------------------

    def analyze_timeouts(
        self,
        graph: InfraGraph,
        component_id: str,
        config: PoolConfig,
    ) -> TimeoutAnalysisResult:
        """Analyze whether timeout settings are appropriate."""
        comp = graph.get_component(component_id)
        if comp is None:
            return TimeoutAnalysisResult(
                component_id=component_id,
                acquire_timeout_adequate=False,
                idle_timeout_adequate=False,
                max_lifetime_adequate=False,
                timeout_score=0.0,
                recommendations=["Component not found in graph"],
            )

        score = _timeout_score(config, config.pool_type)
        errors = _estimate_timeout_errors(config, comp)

        acquire_ok = 500 <= config.acquire_timeout_ms <= 30000
        idle_ok = 0 < config.idle_timeout_seconds <= 3600
        lifetime_ok = 0 < config.max_lifetime_seconds <= 7200

        recs: list[str] = []
        if not acquire_ok:
            if config.acquire_timeout_ms <= 0:
                recs.append("Set an acquire timeout to prevent indefinite blocking")
            elif config.acquire_timeout_ms > 30000:
                recs.append("Reduce acquire timeout to fail fast under load")
            else:
                recs.append(
                    "Acquire timeout may be too aggressive; consider "
                    "increasing to avoid spurious errors"
                )
        if not idle_ok:
            if config.idle_timeout_seconds <= 0:
                recs.append("Set an idle timeout to reap unused connections")
            else:
                recs.append("Idle timeout is too long; stale connections may accumulate")
        if not lifetime_ok:
            if config.max_lifetime_seconds <= 0:
                recs.append(
                    "Set max_lifetime to force periodic connection rotation"
                )
            else:
                recs.append(
                    "Max lifetime is very long; consider reducing to prevent "
                    "stale connections"
                )
        if errors > 0:
            recs.append(
                f"Estimated {errors:.1f} timeout errors/hour; consider "
                "increasing pool size or reducing hold times"
            )
        if not recs:
            recs.append("Timeout configuration looks healthy")

        return TimeoutAnalysisResult(
            component_id=component_id,
            acquire_timeout_adequate=acquire_ok,
            idle_timeout_adequate=idle_ok,
            max_lifetime_adequate=lifetime_ok,
            timeout_score=round(score, 1),
            estimated_timeout_errors_per_hour=errors,
            recommendations=recs,
        )

    # -- health check strategy analysis ------------------------------------

    def analyze_health_check(
        self,
        graph: InfraGraph,
        component_id: str,
        config: PoolConfig,
    ) -> HealthCheckAnalysisResult:
        """Analyze the effectiveness of the configured health check strategy."""
        comp = graph.get_component(component_id)

        overhead = _HEALTH_CHECK_OVERHEAD_MS.get(config.health_check, 0.0)
        reliability = _HEALTH_CHECK_RELIABILITY.get(config.health_check, 0.0)

        # Determine stale connection risk
        if reliability >= 0.9:
            stale_risk = "low"
        elif reliability >= 0.6:
            stale_risk = "medium"
        else:
            stale_risk = "high"

        # Recommend strategy based on pool type
        if config.pool_type == PoolType.DATABASE:
            recommended = HealthCheckStrategy.TEST_ON_BORROW
        elif config.pool_type in (PoolType.GRPC, PoolType.HTTP):
            recommended = HealthCheckStrategy.BACKGROUND_VALIDATION
        elif config.pool_type == PoolType.REDIS:
            recommended = HealthCheckStrategy.TEST_WHILE_IDLE
        else:
            recommended = HealthCheckStrategy.BACKGROUND_VALIDATION

        recs: list[str] = []
        if config.health_check == HealthCheckStrategy.NONE:
            recs.append(
                "No health checking is configured; stale connections will "
                "cause errors"
            )
        if overhead > 1.5 and comp is not None and comp.capacity.max_rps > 5000:
            recs.append(
                "Health check overhead is significant for high-throughput "
                "component; consider background_validation"
            )
        if config.health_check != recommended:
            recs.append(
                f"Consider switching to {recommended.value} for "
                f"{config.pool_type.value} pools"
            )
        if config.health_check_interval_seconds > 120:
            recs.append(
                "Health check interval is too long; reduce to detect "
                "failures faster"
            )
        if not recs:
            recs.append("Health check strategy is appropriate")

        return HealthCheckAnalysisResult(
            strategy=config.health_check,
            overhead_ms=overhead,
            reliability_score=reliability,
            stale_connection_risk=stale_risk,
            recommended_strategy=recommended,
            recommendations=recs,
        )

    # -- warmup strategy analysis ------------------------------------------

    def analyze_warmup(
        self,
        graph: InfraGraph,
        component_id: str,
        config: PoolConfig,
    ) -> WarmupAnalysisResult:
        """Analyze the pool warmup strategy and its cold-start impact."""
        graph.get_component(component_id)

        readiness = _WARMUP_READINESS.get(config.warmup, 0.0)
        creation_overhead = _POOL_CREATION_OVERHEAD_MS.get(config.pool_type, 10.0)

        # Startup latency: time to create initial connections
        initial_count = int(config.min_size * readiness) if readiness > 0 else 0
        startup_latency = initial_count * creation_overhead

        # Cold start impact: what fraction of early requests hit cold connections
        cold_start_impact = (1.0 - readiness) * 100.0

        # Recommend pre_create for databases, gradual_ramp for others
        if config.pool_type == PoolType.DATABASE:
            recommended = WarmupStrategy.PRE_CREATE
        elif config.pool_type in (PoolType.HTTP, PoolType.REDIS):
            recommended = WarmupStrategy.LAZY_CREATION
        else:
            recommended = WarmupStrategy.GRADUAL_RAMP

        recs: list[str] = []
        if config.warmup == WarmupStrategy.LAZY_CREATION and config.pool_type == PoolType.DATABASE:
            recs.append(
                "Lazy creation for database pools causes high latency on "
                "first requests; use pre_create or gradual_ramp"
            )
        if config.warmup == WarmupStrategy.PRE_CREATE and config.min_size > 50:
            recs.append(
                "Pre-creating many connections slows startup; consider "
                "gradual_ramp for large pools"
            )
        if cold_start_impact > 50:
            recs.append(
                "Cold start impact is high; consider warming up connections "
                "before serving traffic"
            )
        if not recs:
            recs.append("Warmup strategy is appropriate for the pool type")

        return WarmupAnalysisResult(
            strategy=config.warmup,
            startup_latency_ms=round(startup_latency, 2),
            cold_start_impact_percent=round(cold_start_impact, 1),
            readiness_at_startup=readiness,
            recommended_strategy=recommended,
            recommendations=recs,
        )

    # -- sharing tradeoff --------------------------------------------------

    def analyze_sharing_tradeoff(
        self,
        graph: InfraGraph,
        component_id: str,
        config: PoolConfig,
        service_count: int = 1,
    ) -> SharingTradeoffResult:
        """Analyze shared vs dedicated pool tradeoffs."""
        graph.get_component(component_id)

        # Shared pool: better utilisation, less isolation
        shared_eff = _clamp(80.0 + 20.0 / max(service_count, 1))
        # Dedicated pool: better isolation, more resource overhead
        dedicated_iso = _clamp(90.0 + 10.0 / max(service_count, 1))
        overhead = max(1.0, float(service_count))

        if service_count <= 1:
            recommended = PoolSharingMode.SHARED
        elif service_count <= 3:
            recommended = PoolSharingMode.HYBRID
        else:
            recommended = PoolSharingMode.DEDICATED

        # For databases, prefer dedicated pools when service count is high
        if config.pool_type == PoolType.DATABASE and service_count > 2:
            recommended = PoolSharingMode.DEDICATED

        recs: list[str] = []
        if config.sharing_mode == PoolSharingMode.SHARED and service_count > 3:
            recs.append(
                "Shared pool with many services risks noisy-neighbour issues; "
                "consider dedicated or hybrid mode"
            )
        if config.sharing_mode == PoolSharingMode.DEDICATED and service_count <= 1:
            recs.append(
                "Dedicated pool with a single service adds unnecessary overhead; "
                "shared mode is sufficient"
            )
        if config.sharing_mode != recommended:
            recs.append(
                f"Consider {recommended.value} mode for {service_count} "
                f"service(s) using {config.pool_type.value} pools"
            )
        if not recs:
            recs.append("Pool sharing mode is appropriate")

        return SharingTradeoffResult(
            current_mode=config.sharing_mode,
            recommended_mode=recommended,
            shared_efficiency=round(shared_eff, 1),
            dedicated_isolation=round(dedicated_iso, 1),
            resource_overhead_ratio=round(overhead, 2),
            recommendations=recs,
        )

    # -- connection storm prevention ---------------------------------------

    def analyze_storm_prevention(
        self,
        graph: InfraGraph,
        component_id: str,
        config: PoolConfig,
        service_count: int = 1,
        has_backoff_jitter: bool = False,
    ) -> StormPreventionResult:
        """Analyze the risk and prevention of connection storms."""
        comp = graph.get_component(component_id)
        if comp is None:
            return StormPreventionResult(
                storm_risk="unknown",
                recommendations=["Component not found in graph"],
            )

        peak = _storm_peak_connections(config, comp, service_count)
        max_safe = comp.capacity.max_connections * comp.replicas

        if peak > max_safe * 2:
            risk = "critical"
        elif peak > max_safe:
            risk = "high"
        elif peak > max_safe * 0.7:
            risk = "medium"
        else:
            risk = "low"

        backoff_ok = has_backoff_jitter or risk == "low"

        recs: list[str] = []
        if risk in ("critical", "high"):
            recs.append(
                "Connection storm could overwhelm the target; implement "
                "exponential backoff with jitter on reconnect"
            )
        if not has_backoff_jitter and risk != "low":
            recs.append(
                "Add jitter to reconnect backoff to spread out reconnection "
                "attempts"
            )
        if service_count > 5 and config.pool_type == PoolType.DATABASE:
            recs.append(
                "Many services sharing a database pool; consider connection "
                "proxies (e.g., PgBouncer)"
            )
        if peak > max_safe:
            recs.append(
                f"Peak reconnection ({peak}) exceeds safe limit ({max_safe}); "
                "implement connection rate limiting"
            )
        if not recs:
            recs.append("Connection storm risk is within acceptable limits")

        return StormPreventionResult(
            storm_risk=risk,
            estimated_peak_connections=peak,
            max_safe_connections=max_safe,
            reconnect_backoff_adequate=backoff_ok,
            jitter_configured=has_backoff_jitter,
            recommendations=recs,
        )

    # -- pool metrics modelling --------------------------------------------

    def model_pool_metrics(
        self,
        graph: InfraGraph,
        component_id: str,
        config: PoolConfig,
        request_rate_per_second: float = 100.0,
        avg_hold_time_ms: float = 50.0,
        time_steps: int = 5,
    ) -> list[PoolMetricsSnapshot]:
        """Model pool metrics over time steps (each step = 1 minute)."""
        comp = graph.get_component(component_id)
        if comp is None:
            return []

        pool_max = config.max_size * comp.replicas
        snapshots: list[PoolMetricsSnapshot] = []
        now = datetime.now(timezone.utc)

        for step in range(time_steps):
            # Simulate gradual ramp-up: traffic increases over steps
            step_rate = request_rate_per_second * (0.5 + 0.5 * step / max(time_steps - 1, 1))
            concurrent = step_rate * (avg_hold_time_ms / 1000.0)

            active = min(int(concurrent), pool_max)
            idle = max(0, min(config.idle_size * comp.replicas, pool_max - active))
            total = active + idle
            waiting = max(0, int(concurrent - pool_max))
            utilization = (active / max(pool_max, 1)) * 100.0

            # Wait time increases exponentially as pool saturates
            if utilization < 80:
                wait_ms = 0.5
            else:
                wait_ms = 0.5 + (utilization - 80) ** 2 * 0.1

            _POOL_CREATION_OVERHEAD_MS.get(config.pool_type, 10.0)
            created = max(0, active - config.min_size * comp.replicas) if step == 0 else max(0, active - (snapshots[-1].active_connections if snapshots else 0))
            destroyed = max(0, (snapshots[-1].idle_connections if snapshots else 0) - idle) if step > 0 else 0

            ts = f"{now.isoformat()}+{step}m"

            snapshots.append(PoolMetricsSnapshot(
                timestamp=ts,
                active_connections=active,
                idle_connections=idle,
                waiting_threads=waiting,
                total_connections=total,
                utilization_percent=round(_clamp(utilization), 1),
                avg_wait_time_ms=round(wait_ms, 2),
                avg_use_time_ms=round(avg_hold_time_ms, 2),
                created_count=max(0, created),
                destroyed_count=max(0, destroyed),
            ))

        return snapshots

    # -- cross-service coordination ----------------------------------------

    def analyze_cross_service_coordination(
        self,
        graph: InfraGraph,
        configs: dict[str, PoolConfig],
    ) -> CrossServiceCoordinationResult:
        """Analyze connection pool coordination across services in the graph."""
        if not configs:
            return CrossServiceCoordinationResult(
                recommendations=["No pool configurations provided"],
            )

        total_pools = len(configs)
        total_connections = 0
        bottleneck_id = ""
        bottleneck_ratio = 0.0
        imbalanced: list[str] = []

        for cid, cfg in configs.items():
            comp = graph.get_component(cid)
            if comp is None:
                continue

            pool_total = cfg.max_size * comp.replicas
            total_connections += pool_total

            # Check if this component is a bottleneck
            max_conns = comp.capacity.max_connections * comp.replicas
            if max_conns > 0:
                ratio = pool_total / max_conns
                if ratio > bottleneck_ratio:
                    bottleneck_ratio = ratio
                    bottleneck_id = cid

            # Check for imbalance: pool too large relative to component capacity
            if max_conns > 0 and pool_total > max_conns * 0.8:
                imbalanced.append(cid)

        # Coordination score: penalize if many pools are imbalanced
        coord_score = 100.0
        if total_pools > 0:
            coord_score -= (len(imbalanced) / total_pools) * 50.0
        if bottleneck_ratio > 1.0:
            coord_score -= 20.0
        coord_score = _clamp(coord_score)

        recs: list[str] = []
        if imbalanced:
            recs.append(
                f"{len(imbalanced)} pool(s) are consuming >80% of target "
                "connection capacity; coordinate limits across services"
            )
        if bottleneck_id and bottleneck_ratio > 0.8:
            recs.append(
                f"Component '{bottleneck_id}' is the connection bottleneck; "
                "consider increasing its max_connections or adding replicas"
            )
        if total_connections > 500:
            recs.append(
                "High aggregate connection count; consider connection "
                "multiplexing (HTTP/2, gRPC) to reduce total connections"
            )
        if not recs:
            recs.append("Cross-service pool coordination is balanced")

        return CrossServiceCoordinationResult(
            total_pools=total_pools,
            total_connections=total_connections,
            bottleneck_component=bottleneck_id,
            coordination_score=round(coord_score, 1),
            imbalanced_pools=imbalanced,
            recommendations=recs,
        )

    # -- full analysis summary ---------------------------------------------

    def full_analysis(
        self,
        graph: InfraGraph,
        configs: dict[str, PoolConfig],
    ) -> PoolAnalysisSummary:
        """Run a comprehensive analysis of all configured pools."""
        sizing_results: list[PoolSizingResult] = []
        leak_results: list[LeakDetectionResult] = []
        all_recs: list[str] = []
        total_conns = 0
        score_sum = 0.0

        for cid, cfg in configs.items():
            sizing = self.analyze_pool_sizing(graph, cid, cfg)
            sizing_results.append(sizing)
            score_sum += sizing.sizing_score

            leak = self.detect_connection_leaks(graph, cid, cfg)
            leak_results.append(leak)

            comp = graph.get_component(cid)
            if comp is not None:
                total_conns += cfg.max_size * comp.replicas

            if leak.leak_risk in ("medium", "high"):
                all_recs.append(
                    f"Component '{cid}' has {leak.leak_risk} leak risk"
                )
            if sizing.undersized:
                all_recs.append(
                    f"Component '{cid}' pool is undersized"
                )
            if sizing.oversized:
                all_recs.append(
                    f"Component '{cid}' pool is oversized"
                )

        count = len(configs)
        avg_score = score_sum / max(count, 1)

        # Dedup recommendations
        seen: set[str] = set()
        unique_recs: list[str] = []
        for r in all_recs:
            if r not in seen:
                seen.add(r)
                unique_recs.append(r)

        if not unique_recs:
            unique_recs.append("All pools are within healthy parameters")

        return PoolAnalysisSummary(
            component_count=count,
            total_pool_connections=total_conns,
            overall_health_score=round(_clamp(avg_score), 1),
            sizing_results=sizing_results,
            leak_results=leak_results,
            recommendations=unique_recs,
        )
