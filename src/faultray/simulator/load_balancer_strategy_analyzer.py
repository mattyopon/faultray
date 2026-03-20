# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Load Balancer Strategy Analyzer — evaluate LB strategies for resilience.

Analyzes load balancing algorithms, health check configurations, sticky
sessions, connection draining, cross-zone balancing, SSL/TLS termination,
backend weight optimization, slow-start ramp-up, LB redundancy modes,
traffic distribution fairness, failover behaviour with unhealthy backends,
and session persistence vs availability tradeoffs.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

from faultray.model.components import Component, ComponentType, HealthStatus
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_HEALTH_CHECK_INTERVAL_S = 10.0
_DEFAULT_HEALTH_CHECK_TIMEOUT_S = 5.0
_DEFAULT_HEALTH_CHECK_THRESHOLD = 3

_FAIRNESS_PERFECT = 1.0
_FAIRNESS_GOOD_THRESHOLD = 0.85
_FAIRNESS_ACCEPTABLE_THRESHOLD = 0.60

_DRAINING_TIMEOUT_MIN_S = 5.0
_DRAINING_TIMEOUT_MAX_S = 300.0
_DRAINING_TIMEOUT_DEFAULT_S = 30.0

_SLOW_START_MIN_S = 10.0
_SLOW_START_MAX_S = 900.0
_SLOW_START_DEFAULT_S = 60.0

_CROSS_ZONE_LATENCY_PENALTY_MS = 2.0
_CROSS_ZONE_COST_MULTIPLIER = 1.15

_SSL_TERMINATION_OVERHEAD_MS = 1.5
_SSL_PASSTHROUGH_OVERHEAD_MS = 0.3
_SSL_REENCRYPT_OVERHEAD_MS = 2.8

_SESSION_PERSISTENCE_AVAILABILITY_PENALTY = 0.05

_ACTIVE_PASSIVE_FAILOVER_S = 15.0
_ACTIVE_ACTIVE_FAILOVER_S = 2.0


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class LBAlgorithm(str, Enum):
    """Load balancing algorithm."""

    ROUND_ROBIN = "round_robin"
    WEIGHTED_ROUND_ROBIN = "weighted_round_robin"
    LEAST_CONNECTIONS = "least_connections"
    IP_HASH = "ip_hash"
    RANDOM = "random"
    LEAST_RESPONSE_TIME = "least_response_time"


class HealthCheckVerdict(str, Enum):
    """Health check configuration assessment verdict."""

    OPTIMAL = "optimal"
    ACCEPTABLE = "acceptable"
    RISKY = "risky"
    DANGEROUS = "dangerous"


class SSLTerminationPoint(str, Enum):
    """Where SSL/TLS is terminated."""

    LOAD_BALANCER = "load_balancer"
    BACKEND = "backend"
    REENCRYPT = "reencrypt"
    PASSTHROUGH = "passthrough"


class RedundancyMode(str, Enum):
    """Load balancer redundancy mode."""

    SINGLE = "single"
    ACTIVE_PASSIVE = "active_passive"
    ACTIVE_ACTIVE = "active_active"


class FairnessGrade(str, Enum):
    """Traffic distribution fairness grade."""

    EXCELLENT = "excellent"
    GOOD = "good"
    ACCEPTABLE = "acceptable"
    POOR = "poor"


class FailoverBehaviour(str, Enum):
    """How the LB behaves when backends go unhealthy."""

    REMOVE_AND_REDISTRIBUTE = "remove_and_redistribute"
    DRAIN_THEN_REMOVE = "drain_then_remove"
    KEEP_SENDING = "keep_sending"
    RETURN_503 = "return_503"


class SessionPersistenceMode(str, Enum):
    """Session persistence / sticky-session mode."""

    NONE = "none"
    COOKIE = "cookie"
    SOURCE_IP = "source_ip"
    HEADER = "header"


# ---------------------------------------------------------------------------
# Pydantic data models
# ---------------------------------------------------------------------------


class HealthCheckConfig(BaseModel):
    """Health check configuration for a load balancer."""

    interval_seconds: float = Field(default=_DEFAULT_HEALTH_CHECK_INTERVAL_S, ge=0.1)
    timeout_seconds: float = Field(default=_DEFAULT_HEALTH_CHECK_TIMEOUT_S, ge=0.1)
    healthy_threshold: int = Field(default=2, ge=1)
    unhealthy_threshold: int = Field(default=_DEFAULT_HEALTH_CHECK_THRESHOLD, ge=1)
    path: str = "/health"
    protocol: str = "HTTP"


class HealthCheckAssessment(BaseModel):
    """Result of analysing a health check configuration."""

    verdict: HealthCheckVerdict = HealthCheckVerdict.ACCEPTABLE
    interval_ok: bool = True
    timeout_ok: bool = True
    threshold_ok: bool = True
    detection_time_seconds: float = 0.0
    false_positive_risk: float = 0.0
    false_negative_risk: float = 0.0
    recommendations: list[str] = Field(default_factory=list)


class StickySessionAssessment(BaseModel):
    """Assessment of sticky session impact on failover."""

    mode: SessionPersistenceMode = SessionPersistenceMode.NONE
    enabled: bool = False
    failover_impact: str = "none"
    session_loss_on_failure: bool = False
    availability_penalty: float = 0.0
    recommendations: list[str] = Field(default_factory=list)


class ConnectionDrainingConfig(BaseModel):
    """Connection draining configuration."""

    enabled: bool = True
    timeout_seconds: float = Field(default=_DRAINING_TIMEOUT_DEFAULT_S, ge=0.0)
    active_connections_handled: bool = True


class ConnectionDrainingAssessment(BaseModel):
    """Assessment of connection draining during backend removal."""

    config: ConnectionDrainingConfig = Field(default_factory=ConnectionDrainingConfig)
    risk_of_dropped_requests: float = 0.0
    estimated_drain_duration_seconds: float = 0.0
    recommendations: list[str] = Field(default_factory=list)


class CrossZoneConfig(BaseModel):
    """Cross-zone load balancing configuration."""

    enabled: bool = False
    zone_count: int = Field(default=1, ge=1)
    backends_per_zone: list[int] = Field(default_factory=lambda: [1])


class CrossZoneAssessment(BaseModel):
    """Cross-zone load balancing cost and latency analysis."""

    config: CrossZoneConfig = Field(default_factory=CrossZoneConfig)
    latency_penalty_ms: float = 0.0
    cost_multiplier: float = 1.0
    zone_imbalance_risk: bool = False
    recommendations: list[str] = Field(default_factory=list)


class SSLAnalysis(BaseModel):
    """SSL/TLS termination point analysis."""

    termination_point: SSLTerminationPoint = SSLTerminationPoint.LOAD_BALANCER
    overhead_ms: float = 0.0
    end_to_end_encryption: bool = False
    certificate_management_complexity: str = "low"
    recommendations: list[str] = Field(default_factory=list)


class BackendWeightConfig(BaseModel):
    """Backend weight configuration for weighted algorithms."""

    backend_id: str = ""
    weight: float = Field(default=1.0, ge=0.0)
    capacity_rps: float = Field(default=1000.0, ge=0.0)


class WeightOptimizationResult(BaseModel):
    """Result of backend weight optimization."""

    original_weights: list[float] = Field(default_factory=list)
    optimized_weights: list[float] = Field(default_factory=list)
    expected_improvement_percent: float = 0.0
    recommendations: list[str] = Field(default_factory=list)


class SlowStartConfig(BaseModel):
    """Slow-start ramp-up configuration for new backends."""

    enabled: bool = False
    duration_seconds: float = Field(default=_SLOW_START_DEFAULT_S, ge=0.0)
    initial_weight_percent: float = Field(default=10.0, ge=0.0, le=100.0)


class SlowStartAssessment(BaseModel):
    """Assessment of slow-start configuration for new backends."""

    config: SlowStartConfig = Field(default_factory=SlowStartConfig)
    cold_start_risk: str = "low"
    ramp_up_adequate: bool = True
    recommendations: list[str] = Field(default_factory=list)


class RedundancyAssessment(BaseModel):
    """Load balancer redundancy assessment."""

    mode: RedundancyMode = RedundancyMode.SINGLE
    failover_time_seconds: float = 0.0
    spof_risk: bool = True
    availability_score: float = 0.0
    recommendations: list[str] = Field(default_factory=list)


class FairnessScore(BaseModel):
    """Traffic distribution fairness scoring."""

    algorithm: LBAlgorithm = LBAlgorithm.ROUND_ROBIN
    score: float = Field(default=1.0, ge=0.0, le=1.0)
    grade: FairnessGrade = FairnessGrade.EXCELLENT
    coefficient_of_variation: float = 0.0
    recommendations: list[str] = Field(default_factory=list)


class FailoverAssessment(BaseModel):
    """Failover behaviour assessment when backends are unhealthy."""

    behaviour: FailoverBehaviour = FailoverBehaviour.REMOVE_AND_REDISTRIBUTE
    all_unhealthy_action: str = "return_503"
    healthy_backend_count: int = 0
    total_backend_count: int = 0
    risk_level: str = "low"
    recommendations: list[str] = Field(default_factory=list)


class SessionTradeoffAnalysis(BaseModel):
    """Session persistence vs availability tradeoff analysis."""

    persistence_mode: SessionPersistenceMode = SessionPersistenceMode.NONE
    availability_impact: float = 0.0
    consistency_benefit: float = 0.0
    tradeoff_score: float = 0.0
    recommendation: str = ""


class LBStrategyReport(BaseModel):
    """Complete load balancer strategy analysis report."""

    analyzed_at: str = ""
    algorithm: LBAlgorithm = LBAlgorithm.ROUND_ROBIN
    health_check: HealthCheckAssessment = Field(default_factory=HealthCheckAssessment)
    sticky_session: StickySessionAssessment = Field(default_factory=StickySessionAssessment)
    connection_draining: ConnectionDrainingAssessment = Field(
        default_factory=ConnectionDrainingAssessment,
    )
    cross_zone: CrossZoneAssessment = Field(default_factory=CrossZoneAssessment)
    ssl_analysis: SSLAnalysis = Field(default_factory=SSLAnalysis)
    weight_optimization: WeightOptimizationResult = Field(
        default_factory=WeightOptimizationResult,
    )
    slow_start: SlowStartAssessment = Field(default_factory=SlowStartAssessment)
    redundancy: RedundancyAssessment = Field(default_factory=RedundancyAssessment)
    fairness: FairnessScore = Field(default_factory=FairnessScore)
    failover: FailoverAssessment = Field(default_factory=FailoverAssessment)
    session_tradeoff: SessionTradeoffAnalysis = Field(
        default_factory=SessionTradeoffAnalysis,
    )
    overall_resilience_score: float = 0.0
    recommendations: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------


class LoadBalancerStrategyAnalyzer:
    """Analyzes load balancing strategies and their resilience characteristics."""

    def __init__(self, graph: InfraGraph) -> None:
        self._graph = graph

    # -- Health Check Analysis -----------------------------------------------

    def assess_health_check(
        self,
        config: HealthCheckConfig,
    ) -> HealthCheckAssessment:
        """Analyse a health check configuration and return an assessment."""

        recommendations: list[str] = []
        interval_ok = True
        timeout_ok = True
        threshold_ok = True
        false_positive_risk = 0.0
        false_negative_risk = 0.0

        # Timeout must be less than interval
        if config.timeout_seconds >= config.interval_seconds:
            timeout_ok = False
            recommendations.append(
                "Health check timeout should be less than the interval to avoid "
                "overlapping checks."
            )
            false_positive_risk += 0.3

        # Interval analysis
        if config.interval_seconds < 2.0:
            interval_ok = False
            recommendations.append(
                "Health check interval is very short (< 2s). This may cause "
                "excessive load on backends."
            )
            false_positive_risk += 0.2
        elif config.interval_seconds > 60.0:
            interval_ok = False
            recommendations.append(
                "Health check interval is very long (> 60s). Unhealthy backends "
                "may not be detected promptly."
            )
            false_negative_risk += 0.3

        # Timeout analysis
        if config.timeout_seconds < 1.0:
            timeout_ok = False
            recommendations.append(
                "Health check timeout is very short (< 1s). Slow but healthy "
                "backends may be marked unhealthy."
            )
            false_positive_risk += 0.2
        elif config.timeout_seconds > 30.0:
            timeout_ok = False
            recommendations.append(
                "Health check timeout is very long (> 30s). Unresponsive backends "
                "will take too long to detect."
            )
            false_negative_risk += 0.2

        # Threshold analysis
        if config.unhealthy_threshold < 2:
            threshold_ok = False
            recommendations.append(
                "Unhealthy threshold of 1 is too aggressive. A single transient "
                "failure will mark the backend down."
            )
            false_positive_risk += 0.3
        elif config.unhealthy_threshold > 10:
            threshold_ok = False
            recommendations.append(
                "Unhealthy threshold > 10 is too lenient. Failing backends will "
                "serve traffic for too long."
            )
            false_negative_risk += 0.3

        if config.healthy_threshold < 1:
            threshold_ok = False
            recommendations.append(
                "Healthy threshold must be at least 1."
            )

        # Detection time
        detection_time = config.interval_seconds * config.unhealthy_threshold

        # Verdict
        issues = sum(1 for ok in (interval_ok, timeout_ok, threshold_ok) if not ok)
        high_risk = false_positive_risk > 0.4 or false_negative_risk > 0.4
        if issues == 0:
            verdict = HealthCheckVerdict.OPTIMAL
        elif issues == 1 and not high_risk:
            verdict = HealthCheckVerdict.ACCEPTABLE
        elif issues <= 2 and not high_risk:
            verdict = HealthCheckVerdict.RISKY
        else:
            verdict = HealthCheckVerdict.DANGEROUS

        return HealthCheckAssessment(
            verdict=verdict,
            interval_ok=interval_ok,
            timeout_ok=timeout_ok,
            threshold_ok=threshold_ok,
            detection_time_seconds=detection_time,
            false_positive_risk=min(1.0, false_positive_risk),
            false_negative_risk=min(1.0, false_negative_risk),
            recommendations=recommendations,
        )

    # -- Sticky Session Impact -----------------------------------------------

    def assess_sticky_session(
        self,
        mode: SessionPersistenceMode = SessionPersistenceMode.NONE,
        backend_count: int = 1,
    ) -> StickySessionAssessment:
        """Assess sticky session impact on failover."""

        recommendations: list[str] = []
        enabled = mode != SessionPersistenceMode.NONE

        if not enabled:
            return StickySessionAssessment(
                mode=mode,
                enabled=False,
                failover_impact="none",
                session_loss_on_failure=False,
                availability_penalty=0.0,
                recommendations=["No sticky sessions configured. "
                                  "Maximum failover flexibility."],
            )

        # Session loss is inherent with sticky sessions
        session_loss_on_failure = True

        # Availability penalty scales with fewer backends
        if backend_count <= 1:
            availability_penalty = _SESSION_PERSISTENCE_AVAILABILITY_PENALTY * 3
            failover_impact = "critical"
            recommendations.append(
                "Sticky sessions with a single backend means no failover. "
                "Add more backends."
            )
        elif backend_count <= 2:
            availability_penalty = _SESSION_PERSISTENCE_AVAILABILITY_PENALTY * 2
            failover_impact = "high"
            recommendations.append(
                "Sticky sessions with only 2 backends. 50% of sessions lost on "
                "single failure."
            )
        elif backend_count <= 4:
            availability_penalty = _SESSION_PERSISTENCE_AVAILABILITY_PENALTY
            failover_impact = "moderate"
            recommendations.append(
                "Consider externalising session state to reduce failover impact."
            )
        else:
            availability_penalty = _SESSION_PERSISTENCE_AVAILABILITY_PENALTY * 0.5
            failover_impact = "low"

        if mode == SessionPersistenceMode.SOURCE_IP:
            recommendations.append(
                "Source-IP persistence can cause imbalanced distribution when "
                "clients are behind NAT."
            )

        return StickySessionAssessment(
            mode=mode,
            enabled=True,
            failover_impact=failover_impact,
            session_loss_on_failure=session_loss_on_failure,
            availability_penalty=availability_penalty,
            recommendations=recommendations,
        )

    # -- Connection Draining -------------------------------------------------

    def assess_connection_draining(
        self,
        config: ConnectionDrainingConfig,
        avg_request_duration_seconds: float = 1.0,
    ) -> ConnectionDrainingAssessment:
        """Assess connection draining configuration."""

        recommendations: list[str] = []
        risk_of_dropped = 0.0

        if not config.enabled:
            risk_of_dropped = 0.8
            recommendations.append(
                "Connection draining is disabled. In-flight requests will be "
                "dropped when a backend is removed."
            )
            return ConnectionDrainingAssessment(
                config=config,
                risk_of_dropped_requests=risk_of_dropped,
                estimated_drain_duration_seconds=0.0,
                recommendations=recommendations,
            )

        # Timeout too short relative to average request duration
        if config.timeout_seconds < avg_request_duration_seconds * 2:
            risk_of_dropped = 0.5
            recommendations.append(
                "Drain timeout is less than 2x average request duration. "
                "Long-running requests may be dropped."
            )
        elif config.timeout_seconds < avg_request_duration_seconds * 5:
            risk_of_dropped = 0.2
        else:
            risk_of_dropped = 0.05

        if config.timeout_seconds < _DRAINING_TIMEOUT_MIN_S:
            recommendations.append(
                f"Drain timeout ({config.timeout_seconds}s) is below recommended "
                f"minimum of {_DRAINING_TIMEOUT_MIN_S}s."
            )
            risk_of_dropped = max(risk_of_dropped, 0.4)

        if config.timeout_seconds > _DRAINING_TIMEOUT_MAX_S:
            recommendations.append(
                f"Drain timeout ({config.timeout_seconds}s) is very long. Backend "
                "removal will be delayed."
            )

        estimated_drain = min(config.timeout_seconds, avg_request_duration_seconds * 3)

        return ConnectionDrainingAssessment(
            config=config,
            risk_of_dropped_requests=risk_of_dropped,
            estimated_drain_duration_seconds=estimated_drain,
            recommendations=recommendations,
        )

    # -- Cross-Zone Load Balancing -------------------------------------------

    def assess_cross_zone(
        self,
        config: CrossZoneConfig,
    ) -> CrossZoneAssessment:
        """Analyse cross-zone load balancing cost and latency."""

        recommendations: list[str] = []
        latency_penalty = 0.0
        cost_multiplier = 1.0
        zone_imbalance = False

        if not config.enabled or config.zone_count <= 1:
            if config.zone_count > 1:
                recommendations.append(
                    "Cross-zone LB is disabled with multiple zones. Traffic may "
                    "be unevenly distributed."
                )
                zone_imbalance = True
            return CrossZoneAssessment(
                config=config,
                latency_penalty_ms=0.0,
                cost_multiplier=1.0,
                zone_imbalance_risk=zone_imbalance,
                recommendations=recommendations,
            )

        # Latency penalty for cross-zone traffic
        latency_penalty = _CROSS_ZONE_LATENCY_PENALTY_MS * (config.zone_count - 1)

        # Cost multiplier
        cost_multiplier = _CROSS_ZONE_COST_MULTIPLIER

        # Check for uneven backend distribution across zones
        if config.backends_per_zone and len(config.backends_per_zone) >= 2:
            max_bpz = max(config.backends_per_zone)
            min_bpz = min(config.backends_per_zone)
            if max_bpz > 0 and min_bpz > 0:
                ratio = min_bpz / max_bpz
                if ratio < 0.5:
                    zone_imbalance = True
                    recommendations.append(
                        "Backend distribution across zones is uneven. Consider "
                        "rebalancing for better fault tolerance."
                    )
            elif min_bpz == 0:
                zone_imbalance = True
                recommendations.append(
                    "At least one zone has zero backends. This defeats the purpose "
                    "of cross-zone balancing."
                )

        if latency_penalty > 4.0:
            recommendations.append(
                f"Cross-zone latency penalty ({latency_penalty:.1f}ms) is "
                "significant. Consider zone-affinity routing for latency-"
                "sensitive workloads."
            )

        return CrossZoneAssessment(
            config=config,
            latency_penalty_ms=latency_penalty,
            cost_multiplier=cost_multiplier,
            zone_imbalance_risk=zone_imbalance,
            recommendations=recommendations,
        )

    # -- SSL/TLS Termination -------------------------------------------------

    def analyze_ssl_termination(
        self,
        termination_point: SSLTerminationPoint = SSLTerminationPoint.LOAD_BALANCER,
    ) -> SSLAnalysis:
        """Analyse SSL/TLS termination point for performance and security."""

        recommendations: list[str] = []
        end_to_end = False
        complexity = "low"

        if termination_point == SSLTerminationPoint.LOAD_BALANCER:
            overhead = _SSL_TERMINATION_OVERHEAD_MS
            recommendations.append(
                "SSL terminates at LB. Traffic between LB and backends is "
                "unencrypted unless internal TLS is used."
            )
        elif termination_point == SSLTerminationPoint.PASSTHROUGH:
            overhead = _SSL_PASSTHROUGH_OVERHEAD_MS
            end_to_end = True
            complexity = "medium"
            recommendations.append(
                "SSL passthrough provides end-to-end encryption but prevents "
                "LB from inspecting HTTP headers (no L7 routing)."
            )
        elif termination_point == SSLTerminationPoint.REENCRYPT:
            overhead = _SSL_REENCRYPT_OVERHEAD_MS
            end_to_end = True
            complexity = "high"
            recommendations.append(
                "SSL re-encryption provides end-to-end encryption with L7 "
                "inspection, but adds latency from double TLS handshake."
            )
        else:  # BACKEND
            overhead = _SSL_TERMINATION_OVERHEAD_MS
            end_to_end = True
            complexity = "medium"
            recommendations.append(
                "SSL terminated at backend. LB cannot do L7 routing. "
                "Certificate management is distributed across backends."
            )

        return SSLAnalysis(
            termination_point=termination_point,
            overhead_ms=overhead,
            end_to_end_encryption=end_to_end,
            certificate_management_complexity=complexity,
            recommendations=recommendations,
        )

    # -- Backend Weight Optimization -----------------------------------------

    def optimize_backend_weights(
        self,
        backends: list[BackendWeightConfig],
    ) -> WeightOptimizationResult:
        """Optimize backend weights based on capacity."""

        if not backends:
            return WeightOptimizationResult(
                recommendations=["No backends provided for weight optimization."],
            )

        original_weights = [b.weight for b in backends]
        total_capacity = sum(b.capacity_rps for b in backends)

        if total_capacity <= 0:
            return WeightOptimizationResult(
                original_weights=original_weights,
                optimized_weights=original_weights,
                expected_improvement_percent=0.0,
                recommendations=["All backends report zero capacity. Cannot optimize."],
            )

        # Optimized weights are proportional to capacity
        optimized_weights = [
            round(b.capacity_rps / total_capacity * len(backends), 3)
            for b in backends
        ]

        # Normalise to sum to len(backends) like round-robin would
        weight_sum = sum(optimized_weights)
        if weight_sum > 0:
            optimized_weights = [
                round(w / weight_sum * len(backends), 3) for w in optimized_weights
            ]

        # Estimate improvement as the reduction in coefficient of variation
        orig_cv = _coefficient_of_variation(original_weights)
        cap_cv = _coefficient_of_variation([b.capacity_rps for b in backends])
        improvement = 0.0
        if orig_cv > 0 and cap_cv > 0:
            # If original weights don't match capacity distribution, there's room
            weight_ratios_orig = [
                w / c if c > 0 else 0
                for w, c in zip(original_weights, [b.capacity_rps for b in backends])
            ]
            weight_ratios_opt = [
                w / c if c > 0 else 0
                for w, c in zip(optimized_weights, [b.capacity_rps for b in backends])
            ]
            cv_orig = _coefficient_of_variation(weight_ratios_orig)
            cv_opt = _coefficient_of_variation(weight_ratios_opt)
            if cv_orig > 0:
                improvement = max(0.0, (cv_orig - cv_opt) / cv_orig * 100.0)

        recommendations: list[str] = []
        if improvement > 5.0:
            recommendations.append(
                f"Weights can be improved by ~{improvement:.1f}% by aligning "
                "with backend capacity."
            )
        elif all(w == original_weights[0] for w in original_weights) and cap_cv > 0.1:
            recommendations.append(
                "All backends have equal weights but different capacities. "
                "Consider using weighted round-robin."
            )

        return WeightOptimizationResult(
            original_weights=original_weights,
            optimized_weights=optimized_weights,
            expected_improvement_percent=round(improvement, 2),
            recommendations=recommendations,
        )

    # -- Slow Start ----------------------------------------------------------

    def assess_slow_start(
        self,
        config: SlowStartConfig,
    ) -> SlowStartAssessment:
        """Assess slow-start configuration for newly added backends."""

        recommendations: list[str] = []
        cold_start_risk = "low"
        ramp_up_adequate = True

        if not config.enabled:
            cold_start_risk = "high"
            ramp_up_adequate = False
            recommendations.append(
                "Slow start is disabled. Newly added backends will receive "
                "full traffic immediately, risking overload."
            )
            return SlowStartAssessment(
                config=config,
                cold_start_risk=cold_start_risk,
                ramp_up_adequate=ramp_up_adequate,
                recommendations=recommendations,
            )

        if config.duration_seconds < _SLOW_START_MIN_S:
            cold_start_risk = "high"
            ramp_up_adequate = False
            recommendations.append(
                f"Slow-start duration ({config.duration_seconds}s) is very short. "
                f"Minimum recommended is {_SLOW_START_MIN_S}s."
            )
        elif config.duration_seconds > _SLOW_START_MAX_S:
            cold_start_risk = "low"
            recommendations.append(
                f"Slow-start duration ({config.duration_seconds}s) is very long. "
                "New backends will be underutilized for an extended period."
            )

        if config.initial_weight_percent > 50.0:
            cold_start_risk = "medium"
            recommendations.append(
                "Initial weight is high (> 50%). The backend may be overwhelmed "
                "before caches and connection pools warm up."
            )
        elif config.initial_weight_percent < 1.0:
            recommendations.append(
                "Initial weight is very low (< 1%). The backend may take too "
                "long to ramp up."
            )

        return SlowStartAssessment(
            config=config,
            cold_start_risk=cold_start_risk,
            ramp_up_adequate=ramp_up_adequate,
            recommendations=recommendations,
        )

    # -- LB Redundancy -------------------------------------------------------

    def assess_redundancy(
        self,
        mode: RedundancyMode = RedundancyMode.SINGLE,
    ) -> RedundancyAssessment:
        """Assess load balancer redundancy configuration."""

        recommendations: list[str] = []
        spof_risk = True
        failover_time = 0.0

        if mode == RedundancyMode.SINGLE:
            spof_risk = True
            failover_time = float("inf")
            availability = 0.995  # ~99.5%
            recommendations.append(
                "Single LB is a single point of failure. Deploy in "
                "active-passive or active-active for high availability."
            )
        elif mode == RedundancyMode.ACTIVE_PASSIVE:
            spof_risk = False
            failover_time = _ACTIVE_PASSIVE_FAILOVER_S
            availability = 0.9995  # ~99.95%
            recommendations.append(
                "Active-passive provides HA but failover takes ~15s. "
                "Consider active-active for near-zero downtime."
            )
        elif mode == RedundancyMode.ACTIVE_ACTIVE:
            spof_risk = False
            failover_time = _ACTIVE_ACTIVE_FAILOVER_S
            availability = 0.99995  # ~99.995%

        return RedundancyAssessment(
            mode=mode,
            failover_time_seconds=failover_time,
            spof_risk=spof_risk,
            availability_score=availability,
            recommendations=recommendations,
        )

    # -- Traffic Distribution Fairness ---------------------------------------

    def score_fairness(
        self,
        algorithm: LBAlgorithm,
        backend_weights: list[float] | None = None,
        backend_count: int = 1,
    ) -> FairnessScore:
        """Score traffic distribution fairness for a given algorithm."""

        recommendations: list[str] = []

        if backend_count <= 0:
            return FairnessScore(
                algorithm=algorithm,
                score=0.0,
                grade=FairnessGrade.POOR,
                coefficient_of_variation=1.0,
                recommendations=["No backends available."],
            )

        if backend_count == 1:
            return FairnessScore(
                algorithm=algorithm,
                score=1.0,
                grade=FairnessGrade.EXCELLENT,
                coefficient_of_variation=0.0,
                recommendations=["Single backend — fairness is trivially perfect."],
            )

        # Simulate distribution based on algorithm
        if algorithm == LBAlgorithm.ROUND_ROBIN:
            # Perfect fairness for equal backends
            score = _FAIRNESS_PERFECT
            cv = 0.0
        elif algorithm == LBAlgorithm.WEIGHTED_ROUND_ROBIN:
            if backend_weights:
                cv = _coefficient_of_variation(backend_weights)
                # High CV means intentional unevenness (not unfairness per se)
                score = max(0.0, 1.0 - cv * 0.3)
            else:
                score = _FAIRNESS_PERFECT
                cv = 0.0
        elif algorithm == LBAlgorithm.LEAST_CONNECTIONS:
            # Generally good fairness, slight variance
            score = 0.92
            cv = 0.08
        elif algorithm == LBAlgorithm.IP_HASH:
            # Depends on IP distribution, can be quite unfair
            cv = 0.25 + 0.1 * math.log(max(1, backend_count))
            score = max(0.0, 1.0 - cv)
            recommendations.append(
                "IP hash distribution fairness depends on client IP diversity. "
                "NAT or proxied clients may skew distribution."
            )
        elif algorithm == LBAlgorithm.RANDOM:
            # Random has natural variance
            cv = 1.0 / math.sqrt(max(1, backend_count * 100))
            score = max(0.0, 1.0 - cv * 5)
        elif algorithm == LBAlgorithm.LEAST_RESPONSE_TIME:
            # Adaptive, generally fair but may overload fast backends
            score = 0.88
            cv = 0.12
            recommendations.append(
                "Least-response-time may cause thundering herd on the fastest "
                "backend after a slow backend recovers."
            )
        else:
            score = 0.5
            cv = 0.5

        # Grade
        if score >= _FAIRNESS_PERFECT - 0.01:
            grade = FairnessGrade.EXCELLENT
        elif score >= _FAIRNESS_GOOD_THRESHOLD:
            grade = FairnessGrade.GOOD
        elif score >= _FAIRNESS_ACCEPTABLE_THRESHOLD:
            grade = FairnessGrade.ACCEPTABLE
        else:
            grade = FairnessGrade.POOR

        return FairnessScore(
            algorithm=algorithm,
            score=round(score, 4),
            grade=grade,
            coefficient_of_variation=round(cv, 4),
            recommendations=recommendations,
        )

    # -- Failover Behaviour --------------------------------------------------

    def assess_failover(
        self,
        behaviour: FailoverBehaviour = FailoverBehaviour.REMOVE_AND_REDISTRIBUTE,
        healthy_count: int = 0,
        total_count: int = 0,
    ) -> FailoverAssessment:
        """Assess failover behaviour when backends are unhealthy."""

        recommendations: list[str] = []
        risk_level = "low"

        if total_count == 0:
            return FailoverAssessment(
                behaviour=behaviour,
                all_unhealthy_action="no_backends",
                healthy_backend_count=0,
                total_backend_count=0,
                risk_level="critical",
                recommendations=["No backends configured."],
            )

        unhealthy_ratio = 1.0 - (healthy_count / total_count) if total_count > 0 else 1.0

        if healthy_count == 0:
            risk_level = "critical"
            recommendations.append(
                "All backends are unhealthy. Service is unavailable."
            )
        elif unhealthy_ratio > 0.5:
            risk_level = "high"
            recommendations.append(
                f"More than 50% of backends are unhealthy ({total_count - healthy_count}"
                f"/{total_count}). Remaining backends may be overloaded."
            )
        elif unhealthy_ratio > 0.2:
            risk_level = "moderate"
            recommendations.append(
                "Multiple backends are unhealthy. Monitor remaining backend load."
            )

        if behaviour == FailoverBehaviour.KEEP_SENDING:
            risk_level = "critical"
            recommendations.append(
                "LB is configured to keep sending traffic to unhealthy backends. "
                "This will cause request failures."
            )
        elif behaviour == FailoverBehaviour.RETURN_503:
            if healthy_count > 0:
                recommendations.append(
                    "Consider using 'remove_and_redistribute' instead of returning "
                    "503 when some backends are still healthy."
                )

        all_unhealthy_action = "return_503"
        if behaviour == FailoverBehaviour.KEEP_SENDING:
            all_unhealthy_action = "keep_sending_to_unhealthy"
        elif behaviour == FailoverBehaviour.DRAIN_THEN_REMOVE:
            all_unhealthy_action = "drain_then_503"

        return FailoverAssessment(
            behaviour=behaviour,
            all_unhealthy_action=all_unhealthy_action,
            healthy_backend_count=healthy_count,
            total_backend_count=total_count,
            risk_level=risk_level,
            recommendations=recommendations,
        )

    # -- Session Persistence vs Availability Tradeoff ------------------------

    def analyze_session_tradeoff(
        self,
        mode: SessionPersistenceMode = SessionPersistenceMode.NONE,
        backend_count: int = 1,
        session_duration_minutes: float = 30.0,
    ) -> SessionTradeoffAnalysis:
        """Analyse the tradeoff between session persistence and availability."""

        if mode == SessionPersistenceMode.NONE:
            return SessionTradeoffAnalysis(
                persistence_mode=mode,
                availability_impact=0.0,
                consistency_benefit=0.0,
                tradeoff_score=1.0,
                recommendation="No session persistence. Maximum availability, "
                               "no session consistency guarantees.",
            )

        # Availability impact grows with fewer backends and longer sessions
        base_impact = _SESSION_PERSISTENCE_AVAILABILITY_PENALTY
        if backend_count <= 1:
            availability_impact = base_impact * 3.0
        elif backend_count <= 3:
            availability_impact = base_impact * (4.0 - backend_count)
        else:
            availability_impact = base_impact * (1.0 / math.log2(max(2, backend_count)))

        # Session duration amplifies impact
        duration_factor = min(2.0, session_duration_minutes / 30.0)
        availability_impact *= duration_factor

        # Consistency benefit
        if mode == SessionPersistenceMode.COOKIE:
            consistency_benefit = 0.9
        elif mode == SessionPersistenceMode.SOURCE_IP:
            consistency_benefit = 0.7  # NAT can break this
        elif mode == SessionPersistenceMode.HEADER:
            consistency_benefit = 0.85
        else:
            consistency_benefit = 0.5

        # Tradeoff score: higher is better (more benefit relative to cost)
        if availability_impact > 0:
            tradeoff_score = max(
                0.0, min(1.0, consistency_benefit - availability_impact)
            )
        else:
            tradeoff_score = consistency_benefit

        if tradeoff_score < 0.3:
            recommendation = (
                "Session persistence has a significant negative impact on "
                "availability. Consider externalising session state."
            )
        elif tradeoff_score < 0.6:
            recommendation = (
                "Moderate tradeoff. Session persistence provides consistency "
                "but limits failover options."
            )
        else:
            recommendation = (
                "Good tradeoff. Session persistence is well-balanced with "
                "the available backend capacity."
            )

        return SessionTradeoffAnalysis(
            persistence_mode=mode,
            availability_impact=round(availability_impact, 4),
            consistency_benefit=round(consistency_benefit, 4),
            tradeoff_score=round(tradeoff_score, 4),
            recommendation=recommendation,
        )

    # -- Full Report ---------------------------------------------------------

    def generate_report(
        self,
        algorithm: LBAlgorithm = LBAlgorithm.ROUND_ROBIN,
        health_check: HealthCheckConfig | None = None,
        sticky_mode: SessionPersistenceMode = SessionPersistenceMode.NONE,
        draining_config: ConnectionDrainingConfig | None = None,
        cross_zone: CrossZoneConfig | None = None,
        ssl_termination: SSLTerminationPoint = SSLTerminationPoint.LOAD_BALANCER,
        backends: list[BackendWeightConfig] | None = None,
        slow_start: SlowStartConfig | None = None,
        redundancy_mode: RedundancyMode = RedundancyMode.SINGLE,
        failover_behaviour: FailoverBehaviour = FailoverBehaviour.REMOVE_AND_REDISTRIBUTE,
        healthy_backend_count: int = 0,
        total_backend_count: int = 0,
        session_duration_minutes: float = 30.0,
    ) -> LBStrategyReport:
        """Generate a comprehensive LB strategy analysis report."""

        now = datetime.now(timezone.utc).isoformat()

        hc = health_check or HealthCheckConfig()
        dc = draining_config or ConnectionDrainingConfig()
        cz = cross_zone or CrossZoneConfig()
        ss = slow_start or SlowStartConfig()
        be = backends or []

        backend_count = total_backend_count or len(be) or 1

        health_assessment = self.assess_health_check(hc)
        sticky_assessment = self.assess_sticky_session(sticky_mode, backend_count)
        drain_assessment = self.assess_connection_draining(dc)
        cz_assessment = self.assess_cross_zone(cz)
        ssl_analysis = self.analyze_ssl_termination(ssl_termination)
        weight_opt = self.optimize_backend_weights(be)
        slow_start_assessment = self.assess_slow_start(ss)
        redundancy_assessment = self.assess_redundancy(redundancy_mode)
        fairness = self.score_fairness(algorithm, backend_count=backend_count)
        failover_assessment = self.assess_failover(
            failover_behaviour,
            healthy_count=healthy_backend_count,
            total_count=total_backend_count,
        )
        session_tradeoff = self.analyze_session_tradeoff(
            sticky_mode, backend_count, session_duration_minutes,
        )

        # Overall resilience score (0 - 100)
        score = _compute_overall_score(
            health_assessment,
            sticky_assessment,
            drain_assessment,
            cz_assessment,
            redundancy_assessment,
            fairness,
            failover_assessment,
        )

        # Aggregate top-level recommendations
        all_recs: list[str] = []
        for sub in (
            health_assessment.recommendations,
            sticky_assessment.recommendations,
            drain_assessment.recommendations,
            cz_assessment.recommendations,
            ssl_analysis.recommendations,
            weight_opt.recommendations,
            slow_start_assessment.recommendations,
            redundancy_assessment.recommendations,
            fairness.recommendations,
            failover_assessment.recommendations,
        ):
            all_recs.extend(sub)
        if session_tradeoff.recommendation:
            all_recs.append(session_tradeoff.recommendation)
        # Deduplicate
        seen: set[str] = set()
        unique_recs: list[str] = []
        for r in all_recs:
            if r not in seen:
                seen.add(r)
                unique_recs.append(r)

        return LBStrategyReport(
            analyzed_at=now,
            algorithm=algorithm,
            health_check=health_assessment,
            sticky_session=sticky_assessment,
            connection_draining=drain_assessment,
            cross_zone=cz_assessment,
            ssl_analysis=ssl_analysis,
            weight_optimization=weight_opt,
            slow_start=slow_start_assessment,
            redundancy=redundancy_assessment,
            fairness=fairness,
            failover=failover_assessment,
            session_tradeoff=session_tradeoff,
            overall_resilience_score=round(score, 2),
            recommendations=unique_recs,
        )

    # -- Graph-Aware Helpers -------------------------------------------------

    def find_load_balancers(self) -> list[Component]:
        """Find all load balancer components in the graph."""
        return [
            c for c in self._graph.components.values()
            if c.type == ComponentType.LOAD_BALANCER
        ]

    def find_backends_for(self, lb_id: str) -> list[Component]:
        """Find all backend components behind a specific load balancer."""
        return self._graph.get_dependencies(lb_id)

    def assess_graph_lb_resilience(self) -> list[LBStrategyReport]:
        """Assess LB resilience for all load balancers in the graph."""

        reports: list[LBStrategyReport] = []
        for lb in self.find_load_balancers():
            backends = self.find_backends_for(lb.id)
            total = len(backends)
            healthy = sum(1 for b in backends if b.health == HealthStatus.HEALTHY)

            redundancy_mode = RedundancyMode.SINGLE
            if lb.replicas >= 2 and lb.failover.enabled:
                redundancy_mode = RedundancyMode.ACTIVE_ACTIVE
            elif lb.replicas >= 2 or lb.failover.enabled:
                redundancy_mode = RedundancyMode.ACTIVE_PASSIVE

            report = self.generate_report(
                algorithm=LBAlgorithm.ROUND_ROBIN,
                redundancy_mode=redundancy_mode,
                healthy_backend_count=healthy,
                total_backend_count=total,
            )
            reports.append(report)

        return reports


# ---------------------------------------------------------------------------
# Helpers (module-private)
# ---------------------------------------------------------------------------


def _coefficient_of_variation(values: list[float]) -> float:
    """Compute coefficient of variation (stddev / mean) for a list of values."""
    if not values or len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    if mean == 0:
        return 0.0
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    stddev = math.sqrt(variance)
    return stddev / mean


def _compute_overall_score(
    health: HealthCheckAssessment,
    sticky: StickySessionAssessment,
    draining: ConnectionDrainingAssessment,
    cross_zone: CrossZoneAssessment,
    redundancy: RedundancyAssessment,
    fairness: FairnessScore,
    failover: FailoverAssessment,
) -> float:
    """Compute a weighted overall resilience score (0-100)."""


    # Health check quality (0-20 points)
    hc_score = {
        HealthCheckVerdict.OPTIMAL: 20.0,
        HealthCheckVerdict.ACCEPTABLE: 15.0,
        HealthCheckVerdict.RISKY: 8.0,
        HealthCheckVerdict.DANGEROUS: 2.0,
    }.get(health.verdict, 10.0)

    # Sticky session impact (0-15 points)
    if not sticky.enabled:
        ss_score = 15.0
    else:
        ss_score = max(0.0, 15.0 - sticky.availability_penalty * 100)

    # Connection draining (0-15 points)
    drain_score = max(0.0, 15.0 * (1.0 - draining.risk_of_dropped_requests))

    # Cross-zone (0-10 points)
    cz_score = 10.0
    if cross_zone.zone_imbalance_risk:
        cz_score -= 5.0
    if cross_zone.latency_penalty_ms > 4.0:
        cz_score -= 3.0

    # Redundancy (0-20 points)
    if redundancy.spof_risk:
        red_score = 5.0
    elif redundancy.mode == RedundancyMode.ACTIVE_ACTIVE:
        red_score = 20.0
    else:
        red_score = 15.0

    # Fairness (0-10 points)
    fair_score = fairness.score * 10.0

    # Failover (0-10 points)
    fail_map = {"low": 10.0, "moderate": 7.0, "high": 4.0, "critical": 0.0}
    fail_score = fail_map.get(failover.risk_level, 5.0)

    total = hc_score + ss_score + drain_score + cz_score + red_score + fair_score + fail_score
    return max(0.0, min(100.0, total))
