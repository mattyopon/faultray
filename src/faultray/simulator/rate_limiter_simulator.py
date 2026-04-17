# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Rate Limiter Simulator.

Simulates and analyses rate-limiting strategies across infrastructure
components.  Supports multiple algorithms (Token Bucket, Leaky Bucket,
Fixed Window, Sliding Window Log, Sliding Window Counter), multi-tier
rate limiting, cascade backpressure analysis, burst handling, distributed
coordination, throttling strategy evaluation, Retry-After / client
backoff simulation, quota allocation optimisation, and end-to-end impact
analysis on latency and error rates.
"""

from __future__ import annotations

import math
from enum import Enum

from pydantic import BaseModel, Field

from faultray.model.components import Component, ComponentType
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class RateLimitAlgorithm(str, Enum):
    """Supported rate-limiting algorithms."""

    TOKEN_BUCKET = "token_bucket"
    LEAKY_BUCKET = "leaky_bucket"
    FIXED_WINDOW = "fixed_window"
    SLIDING_WINDOW_LOG = "sliding_window_log"
    SLIDING_WINDOW_COUNTER = "sliding_window_counter"


class RateLimitTier(str, Enum):
    """Multi-tier rate-limit scope."""

    PER_USER = "per_user"
    PER_IP = "per_ip"
    PER_API_KEY = "per_api_key"
    GLOBAL = "global"


class ThrottleAction(str, Enum):
    """What to do when a request exceeds the rate limit."""

    HARD_REJECT = "hard_reject"
    QUEUE = "queue"
    DEGRADE = "degrade"


class BackoffStrategy(str, Enum):
    """Client retry-backoff strategies."""

    CONSTANT = "constant"
    LINEAR = "linear"
    EXPONENTIAL = "exponential"
    EXPONENTIAL_JITTER = "exponential_jitter"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class RateLimitRule(BaseModel):
    """A single rate-limit rule attached to a component."""

    algorithm: RateLimitAlgorithm = RateLimitAlgorithm.TOKEN_BUCKET
    tier: RateLimitTier = RateLimitTier.GLOBAL
    requests_per_second: float = Field(default=100.0, ge=0.0)
    burst_size: int = Field(default=50, ge=0)
    window_seconds: float = Field(default=1.0, gt=0.0)
    throttle_action: ThrottleAction = ThrottleAction.HARD_REJECT
    queue_capacity: int = Field(default=500, ge=0)
    degrade_latency_factor: float = Field(default=2.0, ge=1.0)


class TrafficProfile(BaseModel):
    """Describes incoming traffic for a simulation run."""

    avg_rps: float = Field(default=100.0, ge=0.0)
    peak_rps: float = Field(default=200.0, ge=0.0)
    burst_duration_seconds: float = Field(default=5.0, ge=0.0)
    duration_seconds: float = Field(default=60.0, ge=0.0)
    num_unique_clients: int = Field(default=100, ge=1)


class RetryConfig(BaseModel):
    """Client retry / back-off configuration."""

    backoff_strategy: BackoffStrategy = BackoffStrategy.EXPONENTIAL_JITTER
    initial_delay_ms: float = Field(default=100.0, ge=0.0)
    max_delay_ms: float = Field(default=30000.0, ge=0.0)
    max_retries: int = Field(default=3, ge=0)
    jitter_factor: float = Field(default=0.5, ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Result models
# ---------------------------------------------------------------------------


class AlgorithmSimResult(BaseModel):
    """Result of simulating a single rate-limit algorithm."""

    algorithm: RateLimitAlgorithm
    requests_allowed: int = 0
    requests_rejected: int = 0
    requests_queued: int = 0
    requests_degraded: int = 0
    rejection_rate: float = Field(default=0.0, ge=0.0, le=100.0)
    avg_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    burst_handling_score: float = Field(default=0.0, ge=0.0, le=100.0)
    fairness_score: float = Field(default=0.0, ge=0.0, le=100.0)
    recommendations: list[str] = Field(default_factory=list)


class TierAnalysis(BaseModel):
    """Analysis of a single rate-limit tier."""

    tier: RateLimitTier
    effective_limit_rps: float = 0.0
    utilisation_percent: float = 0.0
    overflow_rps: float = 0.0
    clients_affected: int = 0
    recommendations: list[str] = Field(default_factory=list)


class CascadeImpact(BaseModel):
    """Impact of upstream rate-limiting on downstream components."""

    component_id: str
    incoming_rps: float = 0.0
    effective_rps_after_limit: float = 0.0
    backpressure_percent: float = 0.0
    queue_saturation_percent: float = 0.0
    estimated_retry_amplification: float = 1.0


class CascadeAnalysisResult(BaseModel):
    """Result of cascade / backpressure analysis."""

    impacts: list[CascadeImpact] = Field(default_factory=list)
    total_backpressure_depth: int = 0
    max_queue_saturation: float = 0.0
    system_throughput_rps: float = 0.0
    retry_storm_risk: float = Field(default=0.0, ge=0.0, le=100.0)
    recommendations: list[str] = Field(default_factory=list)


class RetryAfterResult(BaseModel):
    """Retry-After header and client back-off analysis."""

    retry_after_seconds: float = 0.0
    expected_client_wait_ms: float = 0.0
    retry_amplification_factor: float = 1.0
    total_retries: int = 0
    wasted_requests: int = 0
    effective_goodput_ratio: float = Field(default=1.0, ge=0.0, le=1.0)
    recommendations: list[str] = Field(default_factory=list)


class QuotaAllocation(BaseModel):
    """Optimal quota allocation for a component."""

    component_id: str
    allocated_rps: float = 0.0
    utilisation_ratio: float = 0.0
    headroom_rps: float = 0.0


class QuotaOptimisationResult(BaseModel):
    """Result of quota optimisation across services."""

    allocations: list[QuotaAllocation] = Field(default_factory=list)
    total_capacity_rps: float = 0.0
    total_allocated_rps: float = 0.0
    utilisation_efficiency: float = Field(default=0.0, ge=0.0, le=100.0)
    recommendations: list[str] = Field(default_factory=list)


class EndToEndImpact(BaseModel):
    """End-to-end impact of rate-limiting on latency and error rates."""

    base_latency_ms: float = 0.0
    added_latency_ms: float = 0.0
    total_latency_ms: float = 0.0
    base_error_rate: float = 0.0
    added_error_rate: float = 0.0
    total_error_rate: float = 0.0
    throughput_rps: float = 0.0
    goodput_rps: float = 0.0
    recommendations: list[str] = Field(default_factory=list)


class ThrottleStrategyComparison(BaseModel):
    """Side-by-side comparison of throttling strategies."""

    action: ThrottleAction
    rejection_rate: float = 0.0
    avg_latency_ms: float = 0.0
    queue_depth: int = 0
    goodput_ratio: float = 0.0
    user_experience_score: float = Field(default=0.0, ge=0.0, le=100.0)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


# Algorithm characteristics
_ALGO_BURST_TOLERANCE: dict[RateLimitAlgorithm, float] = {
    RateLimitAlgorithm.TOKEN_BUCKET: 0.9,
    RateLimitAlgorithm.LEAKY_BUCKET: 0.3,
    RateLimitAlgorithm.FIXED_WINDOW: 0.7,
    RateLimitAlgorithm.SLIDING_WINDOW_LOG: 0.5,
    RateLimitAlgorithm.SLIDING_WINDOW_COUNTER: 0.6,
}

_ALGO_FAIRNESS: dict[RateLimitAlgorithm, float] = {
    RateLimitAlgorithm.TOKEN_BUCKET: 0.7,
    RateLimitAlgorithm.LEAKY_BUCKET: 0.95,
    RateLimitAlgorithm.FIXED_WINDOW: 0.5,
    RateLimitAlgorithm.SLIDING_WINDOW_LOG: 0.9,
    RateLimitAlgorithm.SLIDING_WINDOW_COUNTER: 0.85,
}

_ALGO_OVERHEAD_MS: dict[RateLimitAlgorithm, float] = {
    RateLimitAlgorithm.TOKEN_BUCKET: 0.1,
    RateLimitAlgorithm.LEAKY_BUCKET: 0.2,
    RateLimitAlgorithm.FIXED_WINDOW: 0.05,
    RateLimitAlgorithm.SLIDING_WINDOW_LOG: 1.5,
    RateLimitAlgorithm.SLIDING_WINDOW_COUNTER: 0.8,
}

_TIER_PRIORITY: dict[RateLimitTier, int] = {
    RateLimitTier.GLOBAL: 0,
    RateLimitTier.PER_API_KEY: 1,
    RateLimitTier.PER_IP: 2,
    RateLimitTier.PER_USER: 3,
}

_THROTTLE_UX: dict[ThrottleAction, float] = {
    ThrottleAction.HARD_REJECT: 0.4,
    ThrottleAction.QUEUE: 0.75,
    ThrottleAction.DEGRADE: 0.6,
}


def _compute_rejection_fraction(
    rule: RateLimitRule,
    effective_rps: float,
) -> float:
    """Return fraction of requests that will be rejected (0.0 - 1.0)."""
    if effective_rps <= 0.0:
        return 0.0

    capacity = rule.requests_per_second
    burst_tolerance = _ALGO_BURST_TOLERANCE.get(rule.algorithm, 0.5)

    # Effective capacity including burst allowance
    effective_capacity = capacity + rule.burst_size * burst_tolerance / max(rule.window_seconds, 0.01)

    if effective_rps <= effective_capacity:
        return 0.0

    over = effective_rps - effective_capacity
    fraction = over / effective_rps
    return _clamp(fraction, 0.0, 1.0)


def _compute_algo_latency(
    rule: RateLimitRule,
    rejection_fraction: float,
    component: Component | None,
) -> tuple[float, float]:
    """Return (avg_latency_ms, p99_latency_ms) including rate-limiter overhead."""
    base = 5.0
    if component is not None:
        base = max(1.0, component.capacity.timeout_seconds * 0.01 * 1000)

    overhead = _ALGO_OVERHEAD_MS.get(rule.algorithm, 0.5)

    # Queueing delay proportional to how close we are to limit
    queue_factor = 1.0 / max(1.0 - min(1.0 - rejection_fraction, 0.95), 0.05)

    if rule.throttle_action == ThrottleAction.QUEUE:
        # Queued requests experience additional wait
        queue_factor *= 1.5
    elif rule.throttle_action == ThrottleAction.DEGRADE:
        base *= rule.degrade_latency_factor

    avg = base * queue_factor + overhead
    p99 = avg * 3.0
    return round(avg, 2), round(p99, 2)


def _burst_handling_score(
    rule: RateLimitRule,
    peak_rps: float,
) -> float:
    """Score (0-100) representing how well the algorithm handles bursts."""
    tolerance = _ALGO_BURST_TOLERANCE.get(rule.algorithm, 0.5)
    burst_capacity = rule.requests_per_second + rule.burst_size * tolerance
    if peak_rps <= 0.0:
        return 100.0
    ratio = burst_capacity / peak_rps
    return round(_clamp(ratio * 100.0), 1)


def _retry_delay_ms(
    config: RetryConfig,
    attempt: int,
) -> float:
    """Calculate delay for a given retry attempt number (0-based)."""
    if attempt < 0:
        return 0.0

    strategy = config.backoff_strategy
    base = config.initial_delay_ms

    if strategy == BackoffStrategy.CONSTANT:
        delay = base
    elif strategy == BackoffStrategy.LINEAR:
        delay = base * (attempt + 1)
    elif strategy == BackoffStrategy.EXPONENTIAL:
        delay = base * (2.0 ** attempt)
    elif strategy == BackoffStrategy.EXPONENTIAL_JITTER:
        delay = base * (2.0 ** attempt)
        # Deterministic "jitter" for simulation: multiply by (1 - jitter/2)
        delay *= (1.0 - config.jitter_factor * 0.5)
    else:
        delay = base

    return min(delay, config.max_delay_ms)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class RateLimiterSimulator:
    """Stateless engine for rate-limiter simulations."""

    # -- single-algorithm simulation ----------------------------------------

    def simulate_algorithm(
        self,
        graph: InfraGraph,
        component_id: str,
        rule: RateLimitRule,
        traffic: TrafficProfile,
    ) -> AlgorithmSimResult:
        """Simulate a single rate-limit algorithm for *component_id*."""
        component = graph.get_component(component_id)

        effective_rps = traffic.peak_rps
        total_requests = int(traffic.avg_rps * traffic.duration_seconds)
        if total_requests <= 0:
            return AlgorithmSimResult(
                algorithm=rule.algorithm,
                burst_handling_score=100.0,
                fairness_score=100.0,
            )

        rejection_frac = _compute_rejection_fraction(rule, effective_rps)

        rejected = int(total_requests * rejection_frac)
        queued = 0
        degraded = 0

        if rule.throttle_action == ThrottleAction.QUEUE:
            # Some rejections become queued instead
            queueable = min(rejected, rule.queue_capacity)
            queued = queueable
            rejected -= queueable
        elif rule.throttle_action == ThrottleAction.DEGRADE:
            # Rejections become degraded responses
            degraded = rejected
            rejected = 0

        allowed = total_requests - rejected - queued - degraded
        # Queued requests eventually get processed
        allowed += queued

        rejection_rate = round(
            (rejected / max(total_requests, 1)) * 100.0, 2
        )

        avg_lat, p99_lat = _compute_algo_latency(rule, rejection_frac, component)
        burst_score = _burst_handling_score(rule, traffic.peak_rps)
        fairness = round(
            _ALGO_FAIRNESS.get(rule.algorithm, 0.5) * 100.0, 1
        )

        recs: list[str] = []
        if rejection_frac > 0.5:
            recs.append(
                "Over 50% of traffic is rejected; increase rate limit or "
                "scale the service"
            )
        if rejection_frac > 0.0 and rule.throttle_action == ThrottleAction.HARD_REJECT:
            recs.append(
                "Hard reject drops traffic immediately; consider queuing or "
                "graceful degradation for a better user experience"
            )
        if burst_score < 50.0:
            recs.append(
                f"Burst handling is poor ({burst_score}%); increase burst_size "
                "or switch to Token Bucket algorithm"
            )
        if rule.algorithm == RateLimitAlgorithm.FIXED_WINDOW and rejection_frac > 0.0:
            recs.append(
                "Fixed Window can cause boundary-burst issues; consider "
                "Sliding Window Counter for smoother limiting"
            )

        return AlgorithmSimResult(
            algorithm=rule.algorithm,
            requests_allowed=max(0, allowed),
            requests_rejected=max(0, rejected),
            requests_queued=max(0, queued),
            requests_degraded=max(0, degraded),
            rejection_rate=_clamp(rejection_rate),
            avg_latency_ms=avg_lat,
            p99_latency_ms=p99_lat,
            burst_handling_score=burst_score,
            fairness_score=fairness,
            recommendations=recs,
        )

    # -- compare all algorithms ---------------------------------------------

    def compare_algorithms(
        self,
        graph: InfraGraph,
        component_id: str,
        traffic: TrafficProfile,
    ) -> list[AlgorithmSimResult]:
        """Compare all rate-limit algorithms for a traffic scenario."""
        results: list[AlgorithmSimResult] = []
        for algo in RateLimitAlgorithm:
            rule = RateLimitRule(algorithm=algo)
            results.append(
                self.simulate_algorithm(graph, component_id, rule, traffic)
            )
        return results

    # -- multi-tier analysis ------------------------------------------------

    def analyse_tiers(
        self,
        graph: InfraGraph,
        component_id: str,
        rules: list[RateLimitRule],
        traffic: TrafficProfile,
    ) -> list[TierAnalysis]:
        """Analyse rate limits across multiple tiers for a component."""
        if not rules:
            return []

        graph.get_component(component_id)
        analyses: list[TierAnalysis] = []

        # Sort rules by tier priority (global checked first)
        sorted_rules = sorted(
            rules, key=lambda r: _TIER_PRIORITY.get(r.tier, 99)
        )

        remaining_rps = traffic.peak_rps

        for rule in sorted_rules:
            effective_limit = rule.requests_per_second

            # For per-user / per-IP tiers, scale by number of clients
            if rule.tier in (RateLimitTier.PER_USER, RateLimitTier.PER_IP):
                effective_limit = rule.requests_per_second * traffic.num_unique_clients
            elif rule.tier == RateLimitTier.PER_API_KEY:
                # Approximate: fewer API keys than users
                effective_limit = rule.requests_per_second * max(
                    1, traffic.num_unique_clients // 10
                )

            utilisation = (remaining_rps / max(effective_limit, 0.01)) * 100.0
            overflow = max(0.0, remaining_rps - effective_limit)
            affected = 0
            if overflow > 0:
                per_client_rps = remaining_rps / max(traffic.num_unique_clients, 1)
                if per_client_rps > rule.requests_per_second:
                    affected = int(
                        min(
                            traffic.num_unique_clients,
                            math.ceil(overflow / max(per_client_rps, 0.01)),
                        )
                    )

            recs: list[str] = []
            if utilisation > 90.0:
                recs.append(
                    f"Tier '{rule.tier.value}' is near capacity ({utilisation:.0f}%); "
                    "consider raising the limit"
                )
            if utilisation > 100.0:
                recs.append(
                    f"Tier '{rule.tier.value}' is over capacity; requests will be dropped"
                )
            if rule.tier == RateLimitTier.GLOBAL and overflow > 0:
                recs.append(
                    "Global rate limit is the bottleneck; add per-tier limits "
                    "to distribute capacity more fairly"
                )

            analyses.append(
                TierAnalysis(
                    tier=rule.tier,
                    effective_limit_rps=round(effective_limit, 2),
                    utilisation_percent=round(_clamp(utilisation, 0.0, 200.0), 1),
                    overflow_rps=round(overflow, 2),
                    clients_affected=affected,
                    recommendations=recs,
                )
            )

            # Downstream sees only what passes this tier
            remaining_rps = min(remaining_rps, effective_limit)

        return analyses

    # -- cascade / backpressure analysis ------------------------------------

    def analyse_cascade(
        self,
        graph: InfraGraph,
        source_id: str,
        rules_map: dict[str, RateLimitRule],
        traffic: TrafficProfile,
    ) -> CascadeAnalysisResult:
        """Analyse how rate-limiting at *source_id* cascades downstream.

        ``rules_map`` maps component-id -> RateLimitRule for each component
        that has rate-limiting enabled.
        """
        impacts: list[CascadeImpact] = []
        visited: set[str] = set()
        queue: list[tuple[str, float]] = [(source_id, traffic.peak_rps)]
        depth = 0
        max_queue_sat = 0.0

        while queue:
            next_level: list[tuple[str, float]] = []
            for cid, incoming in queue:
                if cid in visited:
                    continue
                visited.add(cid)

                rule = rules_map.get(cid)
                if rule is not None:
                    rej_frac = _compute_rejection_fraction(rule, incoming)
                    effective = incoming * (1.0 - rej_frac)
                else:
                    rej_frac = 0.0
                    effective = incoming

                backpressure = rej_frac * 100.0

                comp = graph.get_component(cid)
                q_sat = 0.0
                if comp is not None:
                    max_rps = float(comp.capacity.max_rps) * comp.replicas
                    q_sat = (effective / max(max_rps, 1.0)) * 100.0
                max_queue_sat = max(max_queue_sat, q_sat)

                retry_amp = 1.0 + rej_frac * 0.5  # rejected requests cause retries

                impacts.append(
                    CascadeImpact(
                        component_id=cid,
                        incoming_rps=round(incoming, 2),
                        effective_rps_after_limit=round(effective, 2),
                        backpressure_percent=round(_clamp(backpressure), 1),
                        queue_saturation_percent=round(
                            _clamp(q_sat, 0.0, 200.0), 1
                        ),
                        estimated_retry_amplification=round(retry_amp, 2),
                    )
                )

                # Walk downstream dependencies (guard against missing nodes)
                if cid in graph.components:
                    deps = graph.get_dependencies(cid)
                    for dep_comp in deps:
                        if dep_comp.id not in visited:
                            next_level.append((dep_comp.id, effective))

            if next_level:
                depth += 1
            queue = next_level

        # Retry storm risk
        total_retry_amp = sum(i.estimated_retry_amplification for i in impacts)
        storm_risk = _clamp(
            (total_retry_amp - len(impacts)) / max(len(impacts), 1) * 100.0
        )

        system_throughput = impacts[-1].effective_rps_after_limit if impacts else 0.0

        recs: list[str] = []
        if depth > 2:
            recs.append(
                "Rate-limiting cascades through many layers; add per-service "
                "limits to prevent deep backpressure"
            )
        if storm_risk > 30.0:
            recs.append(
                "High retry-storm risk detected; implement client back-off "
                "and Retry-After headers"
            )
        if max_queue_sat > 100.0:
            recs.append(
                "Queue saturation exceeds 100%; downstream services will "
                "experience request drops"
            )
        if not impacts:
            recs.append("No components affected; system is well-isolated")

        return CascadeAnalysisResult(
            impacts=impacts,
            total_backpressure_depth=depth,
            max_queue_saturation=round(_clamp(max_queue_sat, 0.0, 200.0), 1),
            system_throughput_rps=round(system_throughput, 2),
            retry_storm_risk=round(storm_risk, 1),
            recommendations=recs,
        )

    # -- retry-after / backoff simulation -----------------------------------

    def simulate_retry_backoff(
        self,
        rule: RateLimitRule,
        traffic: TrafficProfile,
        retry_config: RetryConfig,
    ) -> RetryAfterResult:
        """Simulate Retry-After headers and client back-off behaviour."""
        effective_rps = traffic.peak_rps
        rejection_frac = _compute_rejection_fraction(rule, effective_rps)

        total_requests = int(traffic.avg_rps * traffic.duration_seconds)
        if total_requests <= 0:
            return RetryAfterResult()

        rejected_initial = int(total_requests * rejection_frac)

        # Calculate Retry-After from window size and current load
        if rejection_frac > 0.0:
            retry_after = rule.window_seconds * (1.0 + rejection_frac)
        else:
            retry_after = 0.0

        # Simulate retry waves
        total_retries = 0
        wasted = 0
        attempt_success_rate = 1.0 - rejection_frac * 0.5  # decreasing congestion

        remaining_rejected = rejected_initial
        for attempt in range(retry_config.max_retries):
            retrying = remaining_rejected
            total_retries += retrying

            succeeded = int(retrying * attempt_success_rate)
            still_rejected = retrying - succeeded
            wasted += still_rejected
            remaining_rejected = still_rejected

            # Congestion eases with each wave
            attempt_success_rate = min(1.0, attempt_success_rate + 0.15)

        # Expected client wait: sum of delays across retries
        expected_wait = sum(
            _retry_delay_ms(retry_config, a) for a in range(retry_config.max_retries)
        )

        retry_amplification = (total_requests + total_retries) / max(total_requests, 1)

        goodput = max(0, total_requests - wasted)
        goodput_ratio = goodput / max(total_requests, 1)

        recs: list[str] = []
        if retry_amplification > 1.5:
            recs.append(
                "Retry amplification is high; retries are generating significant "
                "extra load. Implement exponential back-off with jitter"
            )
        if goodput_ratio < 0.7:
            recs.append(
                "Effective goodput is below 70%; increase rate limits or reduce "
                "client retry aggressiveness"
            )
        if retry_config.backoff_strategy == BackoffStrategy.CONSTANT:
            recs.append(
                "Constant back-off can cause thundering-herd retries; switch "
                "to exponential back-off with jitter"
            )
        if retry_after > 10.0:
            recs.append(
                f"Retry-After of {retry_after:.1f}s is long; users will "
                "experience noticeable delays"
            )

        return RetryAfterResult(
            retry_after_seconds=round(retry_after, 2),
            expected_client_wait_ms=round(expected_wait, 2),
            retry_amplification_factor=round(retry_amplification, 3),
            total_retries=total_retries,
            wasted_requests=wasted,
            effective_goodput_ratio=round(_clamp(goodput_ratio, 0.0, 1.0), 4),
            recommendations=recs,
        )

    # -- throttle strategy comparison ---------------------------------------

    def compare_throttle_strategies(
        self,
        graph: InfraGraph,
        component_id: str,
        rule: RateLimitRule,
        traffic: TrafficProfile,
    ) -> list[ThrottleStrategyComparison]:
        """Compare hard-reject vs queue vs degrade throttling strategies."""
        results: list[ThrottleStrategyComparison] = []

        for action in ThrottleAction:
            variant = rule.model_copy(update={"throttle_action": action})
            sim = self.simulate_algorithm(graph, component_id, variant, traffic)

            total = sim.requests_allowed + sim.requests_rejected + sim.requests_degraded
            goodput = sim.requests_allowed / max(total, 1)

            ux_base = _THROTTLE_UX.get(action, 0.5)
            # Adjust UX by rejection rate
            ux_score = ux_base * (1.0 - sim.rejection_rate / 200.0) * 100.0

            results.append(
                ThrottleStrategyComparison(
                    action=action,
                    rejection_rate=sim.rejection_rate,
                    avg_latency_ms=sim.avg_latency_ms,
                    queue_depth=sim.requests_queued,
                    goodput_ratio=round(goodput, 4),
                    user_experience_score=round(_clamp(ux_score), 1),
                )
            )

        return results

    # -- quota optimisation -------------------------------------------------

    def optimise_quotas(
        self,
        graph: InfraGraph,
        component_ids: list[str],
        total_capacity_rps: float,
        traffic_weights: dict[str, float] | None = None,
    ) -> QuotaOptimisationResult:
        """Allocate rate-limit quotas across services to maximise utilisation.

        *traffic_weights* maps component_id to a relative weight (higher =
        more capacity allocated).  If ``None``, capacity is split equally.
        """
        if not component_ids:
            return QuotaOptimisationResult(
                total_capacity_rps=total_capacity_rps,
                recommendations=["No components provided for quota allocation"],
            )

        if traffic_weights is None:
            traffic_weights = {cid: 1.0 for cid in component_ids}

        # Fill in missing weights
        for cid in component_ids:
            if cid not in traffic_weights:
                traffic_weights[cid] = 1.0

        total_weight = sum(traffic_weights.get(cid, 1.0) for cid in component_ids)
        if total_weight <= 0:
            total_weight = 1.0

        allocations: list[QuotaAllocation] = []
        total_allocated = 0.0

        for cid in component_ids:
            weight = traffic_weights.get(cid, 1.0)
            allocated = total_capacity_rps * (weight / total_weight)

            comp = graph.get_component(cid)
            if comp is not None:
                max_rps = float(comp.capacity.max_rps) * comp.replicas
                utilisation = allocated / max(max_rps, 1.0)
            else:
                utilisation = 0.0

            headroom = max(0.0, allocated * 0.2)  # 20% headroom target

            allocations.append(
                QuotaAllocation(
                    component_id=cid,
                    allocated_rps=round(allocated, 2),
                    utilisation_ratio=round(_clamp(utilisation, 0.0, 2.0), 4),
                    headroom_rps=round(headroom, 2),
                )
            )
            total_allocated += allocated

        efficiency = (total_allocated / max(total_capacity_rps, 1.0)) * 100.0

        recs: list[str] = []
        over_utilised = [a for a in allocations if a.utilisation_ratio > 0.9]
        under_utilised = [a for a in allocations if a.utilisation_ratio < 0.3]

        if over_utilised:
            ids = ", ".join(a.component_id for a in over_utilised)
            recs.append(
                f"Components [{ids}] are over-utilised; consider increasing "
                "total capacity or redistributing quotas"
            )
        if under_utilised:
            ids = ", ".join(a.component_id for a in under_utilised)
            recs.append(
                f"Components [{ids}] are under-utilised; redistribute their "
                "unused capacity to busier services"
            )
        if total_allocated > total_capacity_rps * 0.95:
            recs.append(
                "Total allocation is near 100% of capacity; maintain at least "
                "10-20% headroom for burst absorption"
            )

        return QuotaOptimisationResult(
            allocations=allocations,
            total_capacity_rps=round(total_capacity_rps, 2),
            total_allocated_rps=round(total_allocated, 2),
            utilisation_efficiency=round(_clamp(efficiency), 1),
            recommendations=recs,
        )

    # -- end-to-end impact analysis -----------------------------------------

    def analyse_end_to_end_impact(
        self,
        graph: InfraGraph,
        path_component_ids: list[str],
        rules_map: dict[str, RateLimitRule],
        traffic: TrafficProfile,
    ) -> EndToEndImpact:
        """Analyse how rate-limiting across a request path affects latency and errors.

        *path_component_ids* is the ordered list of component IDs a request
        traverses from entry to leaf.
        """
        if not path_component_ids:
            return EndToEndImpact(recommendations=[
                "No path components provided for analysis"
            ])

        base_latency = 0.0
        added_latency = 0.0
        cumulative_pass_rate = 1.0

        current_rps = traffic.peak_rps

        for cid in path_component_ids:
            comp = graph.get_component(cid)

            # Base latency from network/processing
            hop_latency = 5.0
            if comp is not None:
                hop_latency = max(1.0, comp.network.rtt_ms)
            base_latency += hop_latency

            rule = rules_map.get(cid)
            if rule is not None:
                rej_frac = _compute_rejection_fraction(rule, current_rps)
                overhead = _ALGO_OVERHEAD_MS.get(rule.algorithm, 0.5)
                added_latency += overhead

                if rej_frac > 0.0:
                    # Queue delay from partial rejection
                    added_latency += rej_frac * 10.0

                cumulative_pass_rate *= (1.0 - rej_frac)
                current_rps *= (1.0 - rej_frac)

        total_latency = base_latency + added_latency
        base_error = 1.0 - cumulative_pass_rate
        # Additional errors from timeouts when latency is high
        timeout_error = max(0.0, (total_latency - 1000.0) / 10000.0) if total_latency > 1000.0 else 0.0
        total_error = min(1.0, base_error + timeout_error)

        goodput = traffic.avg_rps * cumulative_pass_rate

        recs: list[str] = []
        if total_error > 0.1:
            recs.append(
                f"End-to-end error rate is {total_error*100:.1f}%; rate limits "
                "are too aggressive for current traffic"
            )
        if added_latency > base_latency:
            recs.append(
                "Rate-limiting overhead exceeds base latency; simplify the "
                "rate-limit chain or use faster algorithms"
            )
        if cumulative_pass_rate < 0.5:
            recs.append(
                "Less than 50% of traffic passes all rate limits; review and "
                "increase limits on the tightest bottleneck"
            )
        if len(path_component_ids) > 5:
            recs.append(
                "Request path traverses many components; each rate-limit layer "
                "compounds rejection probability"
            )

        return EndToEndImpact(
            base_latency_ms=round(base_latency, 2),
            added_latency_ms=round(added_latency, 2),
            total_latency_ms=round(total_latency, 2),
            base_error_rate=round(_clamp(base_error, 0.0, 1.0), 4),
            added_error_rate=round(_clamp(timeout_error, 0.0, 1.0), 4),
            total_error_rate=round(_clamp(total_error, 0.0, 1.0), 4),
            throughput_rps=round(current_rps, 2),
            goodput_rps=round(goodput, 2),
            recommendations=recs,
        )

    # -- distributed coordination ------------------------------------------

    def evaluate_coordination(
        self,
        graph: InfraGraph,
        component_ids: list[str],
        rules_map: dict[str, RateLimitRule],
        traffic: TrafficProfile,
    ) -> dict:
        """Evaluate rate-limit coordination across distributed services.

        Returns a dict with consistency scores, split-brain risk, and
        recommendations for improving coordination.
        """
        if not component_ids:
            return {
                "consistency_score": 0.0,
                "split_brain_risk": 0.0,
                "total_effective_rps": 0.0,
                "per_component": {},
                "recommendations": ["No components to evaluate"],
            }

        per_component: dict[str, dict] = {}
        algos_used: set[str] = set()
        total_effective = 0.0

        for cid in component_ids:
            rule = rules_map.get(cid)
            comp = graph.get_component(cid)

            if rule is None:
                per_component[cid] = {
                    "has_rate_limit": False,
                    "effective_rps": 0.0,
                }
                continue

            algos_used.add(rule.algorithm.value)
            rej_frac = _compute_rejection_fraction(rule, traffic.peak_rps)
            effective = traffic.peak_rps * (1.0 - rej_frac)
            total_effective += effective

            replicas = 1
            if comp is not None:
                replicas = comp.replicas

            per_component[cid] = {
                "has_rate_limit": True,
                "algorithm": rule.algorithm.value,
                "effective_rps": round(effective, 2),
                "replicas": replicas,
                "per_replica_limit": round(rule.requests_per_second / max(replicas, 1), 2),
            }

        # Consistency: all using the same algorithm scores high
        consistency = 100.0 if len(algos_used) <= 1 else max(0.0, 100.0 - (len(algos_used) - 1) * 25.0)

        # Split-brain risk: multiple replicas with per-instance counters
        multi_replica_count = sum(
            1 for info in per_component.values()
            if isinstance(info, dict) and info.get("replicas", 1) > 1
        )
        split_brain = _clamp(multi_replica_count / max(len(component_ids), 1) * 100.0)

        recs: list[str] = []
        if len(algos_used) > 1:
            recs.append(
                "Multiple rate-limit algorithms are in use; standardise on "
                "one algorithm for consistent behaviour"
            )
        if split_brain > 50.0:
            recs.append(
                "Many services have multiple replicas; use a centralised "
                "rate-limit store (e.g. Redis) to avoid split-brain counting"
            )
        unlimited = [
            cid for cid in component_ids if cid not in rules_map
        ]
        if unlimited:
            recs.append(
                f"Components [{', '.join(unlimited)}] have no rate limits; "
                "add limits to prevent uncontrolled traffic"
            )

        return {
            "consistency_score": round(consistency, 1),
            "split_brain_risk": round(split_brain, 1),
            "total_effective_rps": round(total_effective, 2),
            "per_component": per_component,
            "recommendations": recs,
        }

    # -- recommend rule -----------------------------------------------------

    def recommend_rule(
        self,
        graph: InfraGraph,
        component_id: str,
        traffic: TrafficProfile,
    ) -> RateLimitRule:
        """Generate a recommended rate-limit rule for a component."""
        comp = graph.get_component(component_id)

        algo = RateLimitAlgorithm.TOKEN_BUCKET
        tier = RateLimitTier.GLOBAL
        rps = traffic.avg_rps * 1.5  # 50% headroom
        burst = max(10, int(traffic.peak_rps - traffic.avg_rps))
        window = 1.0
        action = ThrottleAction.HARD_REJECT

        if comp is not None:
            max_rps = float(comp.capacity.max_rps) * comp.replicas
            rps = min(rps, max_rps * 0.8)

            if comp.type == ComponentType.LOAD_BALANCER:
                algo = RateLimitAlgorithm.TOKEN_BUCKET
                action = ThrottleAction.QUEUE
                tier = RateLimitTier.GLOBAL
            elif comp.type == ComponentType.APP_SERVER:
                algo = RateLimitAlgorithm.SLIDING_WINDOW_COUNTER
                action = ThrottleAction.DEGRADE
                tier = RateLimitTier.PER_API_KEY
            elif comp.type == ComponentType.DATABASE:
                algo = RateLimitAlgorithm.LEAKY_BUCKET
                action = ThrottleAction.QUEUE
                tier = RateLimitTier.GLOBAL
                rps = min(rps, max_rps * 0.6)
            elif comp.type == ComponentType.EXTERNAL_API:
                algo = RateLimitAlgorithm.SLIDING_WINDOW_LOG
                action = ThrottleAction.HARD_REJECT
                tier = RateLimitTier.PER_API_KEY
            elif comp.type == ComponentType.CACHE:
                algo = RateLimitAlgorithm.TOKEN_BUCKET
                action = ThrottleAction.HARD_REJECT
                tier = RateLimitTier.GLOBAL
                rps = max_rps * 0.9  # caches can handle more
            elif comp.type == ComponentType.WEB_SERVER:
                algo = RateLimitAlgorithm.SLIDING_WINDOW_COUNTER
                action = ThrottleAction.DEGRADE
                tier = RateLimitTier.PER_IP

        return RateLimitRule(
            algorithm=algo,
            tier=tier,
            requests_per_second=max(1.0, round(rps, 1)),
            burst_size=max(1, burst),
            window_seconds=window,
            throttle_action=action,
        )
