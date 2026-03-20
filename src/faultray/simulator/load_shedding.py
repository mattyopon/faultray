# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Load Shedding & Backpressure Simulator.

Simulates load shedding strategies and backpressure mechanisms to protect
services from overload.  Evaluates how different shedding policies affect
throughput, latency, priority fairness, and overall system stability.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from faultray.model.components import Component, ComponentType, HealthStatus
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class SheddingStrategy(str, Enum):
    """Load shedding strategies."""

    RANDOM_DROP = "random_drop"
    PRIORITY_BASED = "priority_based"
    LIFO = "lifo"
    FIFO = "fifo"
    TOKEN_BUCKET = "token_bucket"
    ADAPTIVE = "adaptive"
    CIRCUIT_BASED = "circuit_based"
    CLIENT_THROTTLE = "client_throttle"


class BackpressureSignal(str, Enum):
    """Backpressure signalling mechanisms."""

    HTTP_429 = "http_429"
    TCP_BACKOFF = "tcp_backoff"
    QUEUE_FULL = "queue_full"
    RESPONSE_DEGRADATION = "response_degradation"
    CONNECTION_REFUSE = "connection_refuse"
    RATE_LIMIT_HEADER = "rate_limit_header"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class LoadProfile(BaseModel):
    """Describes the incoming load characteristics."""

    requests_per_second: float = Field(default=1000.0, ge=0.0)
    burst_multiplier: float = Field(default=1.0, ge=1.0)
    duration_seconds: float = Field(default=60.0, ge=0.0)
    priority_distribution: dict[str, float] = Field(
        default_factory=lambda: {"high": 0.2, "medium": 0.5, "low": 0.3},
    )


class SheddingConfig(BaseModel):
    """Configuration for a load shedding policy."""

    strategy: SheddingStrategy = SheddingStrategy.RANDOM_DROP
    threshold_percent: float = Field(default=80.0, ge=0.0, le=100.0)
    max_queue_depth: int = Field(default=1000, ge=0)
    priority_levels: int = Field(default=3, ge=1)
    graceful_degradation: bool = True
    backpressure_signal: BackpressureSignal = BackpressureSignal.HTTP_429


class SheddingResult(BaseModel):
    """Result of a load shedding simulation."""

    requests_accepted: int = 0
    requests_shed: int = 0
    shed_percentage: float = 0.0
    avg_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    priority_impact: dict[str, float] = Field(default_factory=dict)
    system_stability: float = Field(default=100.0, ge=0.0, le=100.0)
    recommendations: list[str] = Field(default_factory=list)


class StrategyComparison(BaseModel):
    """Side-by-side comparison entry for a single strategy."""

    strategy: SheddingStrategy
    result: SheddingResult
    fairness_score: float = Field(default=0.0, ge=0.0, le=100.0)
    efficiency_score: float = Field(default=0.0, ge=0.0, le=100.0)


class BackpressureResult(BaseModel):
    """Result of a cascade backpressure simulation."""

    affected_components: list[str] = Field(default_factory=list)
    propagation_depth: int = 0
    max_queue_saturation: float = 0.0
    recovery_time_seconds: float = 0.0
    signal_effectiveness: dict[str, float] = Field(default_factory=dict)
    recommendations: list[str] = Field(default_factory=list)


class DegradationResult(BaseModel):
    """Result of a graceful degradation simulation."""

    degradation_levels: list[str] = Field(default_factory=list)
    features_disabled: list[str] = Field(default_factory=list)
    remaining_capacity_percent: float = 0.0
    user_impact_score: float = Field(default=0.0, ge=0.0, le=100.0)
    recovery_sequence: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class GoodputAnalysis(BaseModel):
    """Goodput (useful throughput) analysis."""

    total_throughput_rps: float = 0.0
    goodput_rps: float = 0.0
    wasted_rps: float = 0.0
    goodput_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    latency_overhead_ms: float = 0.0
    recommendations: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


# Strategy base overhead (latency penalty in ms)
_STRATEGY_OVERHEAD: dict[SheddingStrategy, float] = {
    SheddingStrategy.RANDOM_DROP: 0.5,
    SheddingStrategy.PRIORITY_BASED: 2.0,
    SheddingStrategy.LIFO: 1.5,
    SheddingStrategy.FIFO: 1.0,
    SheddingStrategy.TOKEN_BUCKET: 1.0,
    SheddingStrategy.ADAPTIVE: 3.0,
    SheddingStrategy.CIRCUIT_BASED: 2.5,
    SheddingStrategy.CLIENT_THROTTLE: 1.5,
}

# Fairness multiplier: 1.0 = perfectly fair, lower = less fair
_STRATEGY_FAIRNESS: dict[SheddingStrategy, float] = {
    SheddingStrategy.RANDOM_DROP: 0.9,
    SheddingStrategy.PRIORITY_BASED: 0.6,
    SheddingStrategy.LIFO: 0.5,
    SheddingStrategy.FIFO: 0.95,
    SheddingStrategy.TOKEN_BUCKET: 0.85,
    SheddingStrategy.ADAPTIVE: 0.8,
    SheddingStrategy.CIRCUIT_BASED: 0.7,
    SheddingStrategy.CLIENT_THROTTLE: 0.75,
}

# Efficiency multiplier: how well the strategy preserves goodput
_STRATEGY_EFFICIENCY: dict[SheddingStrategy, float] = {
    SheddingStrategy.RANDOM_DROP: 0.7,
    SheddingStrategy.PRIORITY_BASED: 0.9,
    SheddingStrategy.LIFO: 0.65,
    SheddingStrategy.FIFO: 0.6,
    SheddingStrategy.TOKEN_BUCKET: 0.85,
    SheddingStrategy.ADAPTIVE: 0.95,
    SheddingStrategy.CIRCUIT_BASED: 0.8,
    SheddingStrategy.CLIENT_THROTTLE: 0.75,
}

# Backpressure signal effectiveness (fraction of load reduction, 0-1)
_SIGNAL_EFFECTIVENESS: dict[BackpressureSignal, float] = {
    BackpressureSignal.HTTP_429: 0.6,
    BackpressureSignal.TCP_BACKOFF: 0.7,
    BackpressureSignal.QUEUE_FULL: 0.5,
    BackpressureSignal.RESPONSE_DEGRADATION: 0.4,
    BackpressureSignal.CONNECTION_REFUSE: 0.8,
    BackpressureSignal.RATE_LIMIT_HEADER: 0.65,
}


def _compute_shed_fraction(
    load: LoadProfile,
    config: SheddingConfig,
    component: Component | None,
) -> float:
    """Return fraction of requests to shed (0.0 to 1.0)."""
    effective_rps = load.requests_per_second * load.burst_multiplier

    # Determine capacity from component or from config threshold
    if component is not None:
        max_rps = float(component.capacity.max_rps) * component.replicas
    else:
        max_rps = effective_rps  # no component → assume capacity = demand

    threshold_rps = max_rps * (config.threshold_percent / 100.0)

    if effective_rps <= threshold_rps:
        return 0.0

    overload_fraction = (effective_rps - threshold_rps) / max(effective_rps, 1.0)
    return _clamp(overload_fraction, 0.0, 1.0)


def _compute_priority_impact(
    load: LoadProfile,
    config: SheddingConfig,
    shed_fraction: float,
) -> dict[str, float]:
    """Return per-priority acceptance rates (0-100%)."""
    priority_impact: dict[str, float] = {}
    dist = load.priority_distribution

    if not dist or shed_fraction <= 0.0:
        for p in dist:
            priority_impact[p] = 100.0
        return priority_impact

    strategy = config.strategy

    # Sort priorities by assumed importance (high > medium > low)
    rank_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    sorted_priorities = sorted(
        dist.keys(), key=lambda k: rank_order.get(k, 4)
    )

    if strategy == SheddingStrategy.PRIORITY_BASED:
        # Shed from lowest priority first
        remaining_shed = shed_fraction
        for prio in reversed(sorted_priorities):
            frac = dist.get(prio, 0.0)
            if frac <= 0.0:
                priority_impact[prio] = 100.0
                continue
            shed_from_this = min(remaining_shed / max(frac, 1e-9), 1.0) * frac
            acceptance = max(0.0, 1.0 - shed_from_this / max(frac, 1e-9))
            priority_impact[prio] = round(_clamp(acceptance * 100.0), 1)
            remaining_shed = max(0.0, remaining_shed - shed_from_this)
    elif strategy == SheddingStrategy.LIFO:
        # Later arrivals shed more — approximate higher shed on lower priority
        for i, prio in enumerate(sorted_priorities):
            rank_factor = 1.0 - (i / max(len(sorted_priorities), 1))
            acceptance = 1.0 - shed_fraction * (1.0 - rank_factor * 0.5)
            priority_impact[prio] = round(_clamp(acceptance * 100.0), 1)
    elif strategy == SheddingStrategy.FIFO:
        # Oldest arrivals processed first → uniform shedding
        for prio in sorted_priorities:
            acceptance = 1.0 - shed_fraction
            priority_impact[prio] = round(_clamp(acceptance * 100.0), 1)
    else:
        # Random, token_bucket, adaptive, circuit_based, client_throttle
        # All treat priorities roughly equally (±small noise)
        for prio in sorted_priorities:
            acceptance = 1.0 - shed_fraction
            priority_impact[prio] = round(_clamp(acceptance * 100.0), 1)

    return priority_impact


def _compute_latency(
    load: LoadProfile,
    config: SheddingConfig,
    shed_fraction: float,
    component: Component | None,
) -> tuple[float, float]:
    """Return (avg_latency_ms, p99_latency_ms)."""
    base_latency = 5.0  # baseline ms
    if component is not None:
        base_latency = max(1.0, component.capacity.timeout_seconds * 0.01 * 1000)

    overhead = _STRATEGY_OVERHEAD.get(config.strategy, 1.0)

    effective_rps = load.requests_per_second * load.burst_multiplier
    if component is not None:
        max_rps = float(component.capacity.max_rps) * component.replicas
    else:
        max_rps = effective_rps

    load_ratio = effective_rps / max(max_rps, 1.0)

    # Latency rises with load using a queueing-theory-inspired curve
    queueing_factor = 1.0 / max(1.0 - min(load_ratio * (1.0 - shed_fraction), 0.95), 0.05)

    avg = base_latency * queueing_factor + overhead
    p99 = avg * 3.5  # p99 ~ 3.5x average (heavy-tail)

    return round(avg, 2), round(p99, 2)


def _compute_stability(
    shed_fraction: float,
    config: SheddingConfig,
    component: Component | None,
) -> float:
    """Return system stability score (0-100)."""
    score = 100.0

    # High shedding reduces perceived stability
    score -= shed_fraction * 40.0

    # Non-graceful degradation is riskier
    if not config.graceful_degradation:
        score -= 10.0

    # Shallow queue can cause drops
    if config.max_queue_depth < 100:
        score -= 5.0

    # Component health matters
    if component is not None:
        if component.health == HealthStatus.DEGRADED:
            score -= 15.0
        elif component.health == HealthStatus.OVERLOADED:
            score -= 25.0
        elif component.health == HealthStatus.DOWN:
            score -= 50.0

        if component.replicas <= 1:
            score -= 10.0

    return round(_clamp(score), 1)


def _generate_recommendations(
    shed_fraction: float,
    config: SheddingConfig,
    component: Component | None,
    stability: float,
) -> list[str]:
    """Generate actionable recommendations."""
    recs: list[str] = []

    if shed_fraction > 0.5:
        recs.append(
            "Shedding exceeds 50% of traffic; consider scaling out or "
            "increasing capacity before relying solely on shedding"
        )

    if shed_fraction > 0.0 and config.strategy == SheddingStrategy.RANDOM_DROP:
        recs.append(
            "Random drop shedding does not prioritize traffic; "
            "consider priority-based or adaptive shedding"
        )

    if not config.graceful_degradation and shed_fraction > 0.0:
        recs.append(
            "Enable graceful degradation to reduce non-essential features "
            "under load instead of dropping entire requests"
        )

    if config.max_queue_depth < 100 and shed_fraction > 0.0:
        recs.append(
            "Queue depth is very shallow; increase max_queue_depth to "
            "absorb short bursts"
        )

    if component is not None:
        if component.replicas <= 1:
            recs.append(
                f"Component '{component.id}' has a single replica; "
                "add replicas to increase capacity and fault tolerance"
            )
        if component.health in (HealthStatus.DEGRADED, HealthStatus.OVERLOADED):
            recs.append(
                f"Component '{component.id}' is {component.health.value}; "
                "investigate and remediate before relying on shedding"
            )
        if not component.autoscaling.enabled and shed_fraction > 0.2:
            recs.append(
                f"Enable autoscaling for '{component.id}' to dynamically "
                "adjust capacity under varying load"
            )

    if stability < 50.0:
        recs.append("System stability is critically low; urgent remediation required")

    return recs


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class LoadSheddingEngine:
    """Stateless engine for load shedding and backpressure simulations."""

    # -- core simulation ---------------------------------------------------

    def simulate_shedding(
        self,
        graph: InfraGraph,
        component_id: str,
        load: LoadProfile,
        config: SheddingConfig,
    ) -> SheddingResult:
        """Simulate a shedding policy for *component_id* under *load*."""
        component = graph.get_component(component_id)

        shed_fraction = _compute_shed_fraction(load, config, component)

        effective_rps = load.requests_per_second * load.burst_multiplier
        total_requests = int(effective_rps * load.duration_seconds)
        requests_shed = int(total_requests * shed_fraction)
        requests_accepted = total_requests - requests_shed
        shed_pct = round(shed_fraction * 100.0, 2)

        priority_impact = _compute_priority_impact(load, config, shed_fraction)
        avg_lat, p99_lat = _compute_latency(load, config, shed_fraction, component)
        stability = _compute_stability(shed_fraction, config, component)
        recs = _generate_recommendations(shed_fraction, config, component, stability)

        return SheddingResult(
            requests_accepted=max(0, requests_accepted),
            requests_shed=max(0, requests_shed),
            shed_percentage=shed_pct,
            avg_latency_ms=avg_lat,
            p99_latency_ms=p99_lat,
            priority_impact=priority_impact,
            system_stability=stability,
            recommendations=recs,
        )

    # -- strategy comparison -----------------------------------------------

    def compare_strategies(
        self,
        graph: InfraGraph,
        component_id: str,
        load: LoadProfile,
    ) -> list[StrategyComparison]:
        """Compare all shedding strategies for a given load scenario."""
        comparisons: list[StrategyComparison] = []
        for strategy in SheddingStrategy:
            config = SheddingConfig(strategy=strategy)
            result = self.simulate_shedding(graph, component_id, load, config)

            fairness = _STRATEGY_FAIRNESS.get(strategy, 0.5) * 100.0
            efficiency = _STRATEGY_EFFICIENCY.get(strategy, 0.5) * 100.0

            # Adjust fairness based on actual priority impact spread
            if result.priority_impact:
                values = list(result.priority_impact.values())
                if len(values) > 1:
                    spread = max(values) - min(values)
                    fairness = _clamp(fairness - spread * 0.5)

            comparisons.append(
                StrategyComparison(
                    strategy=strategy,
                    result=result,
                    fairness_score=round(fairness, 1),
                    efficiency_score=round(efficiency, 1),
                )
            )
        return comparisons

    # -- optimal threshold search ------------------------------------------

    def find_optimal_threshold(
        self,
        graph: InfraGraph,
        component_id: str,
        load: LoadProfile,
    ) -> float:
        """Find the threshold_percent that maximises stability and goodput.

        Uses a simple sweep from 50% to 95% in 5% steps.
        """
        best_threshold = 80.0
        best_score = -1.0

        for pct in range(50, 100, 5):
            config = SheddingConfig(threshold_percent=float(pct))
            result = self.simulate_shedding(graph, component_id, load, config)
            goodput = self.calculate_goodput(graph, component_id, load, config)

            # Combined score: stability + goodput_ratio (both 0-100 range)
            score = result.system_stability + goodput.goodput_ratio * 100.0
            if score > best_score:
                best_score = score
                best_threshold = float(pct)

        return best_threshold

    # -- cascade backpressure ----------------------------------------------

    def simulate_cascade_backpressure(
        self,
        graph: InfraGraph,
        load_source: str,
        load: LoadProfile,
    ) -> BackpressureResult:
        """Simulate how backpressure propagates upstream from *load_source*."""
        affected: list[str] = []
        signal_eff: dict[str, float] = {}

        # Walk dependents (upstream) from load_source
        visited: set[str] = set()
        queue: list[str] = [load_source]
        depth = 0
        max_saturation = 0.0

        effective_rps = load.requests_per_second * load.burst_multiplier

        while queue:
            next_level: list[str] = []
            for cid in queue:
                if cid in visited:
                    continue
                visited.add(cid)

                comp = graph.get_component(cid)
                if comp is not None:
                    max_rps = float(comp.capacity.max_rps) * comp.replicas
                    saturation = effective_rps / max(max_rps, 1.0) * 100.0
                    max_saturation = max(max_saturation, saturation)

                if cid != load_source:
                    affected.append(cid)

                # Node may not exist in the graph (unknown component_id)
                if cid not in graph.components:
                    continue

                dependents = graph.get_dependents(cid)
                for dep in dependents:
                    if dep.id not in visited:
                        next_level.append(dep.id)

            if next_level:
                depth += 1
            queue = next_level

            # Reduce effective_rps per hop (backpressure dampening)
            effective_rps *= 0.7

        # Recovery time: proportional to depth and saturation
        recovery = depth * 10.0 + max_saturation * 0.5

        # Signal effectiveness for each type
        for sig in BackpressureSignal:
            signal_eff[sig.value] = round(
                _SIGNAL_EFFECTIVENESS.get(sig, 0.5) * min(max_saturation / 100.0, 1.0) * 100.0,
                1,
            )

        recs: list[str] = []
        if depth > 2:
            recs.append(
                "Backpressure propagates through multiple layers; "
                "add circuit breakers at intermediate services"
            )
        if max_saturation > 100.0:
            recs.append(
                "At least one component is over-saturated; "
                "consider rate limiting at the entry point"
            )
        if not affected:
            recs.append("No upstream propagation detected; system is well-isolated")

        return BackpressureResult(
            affected_components=affected,
            propagation_depth=depth,
            max_queue_saturation=round(_clamp(max_saturation, 0.0, 200.0), 1),
            recovery_time_seconds=round(max(0.0, recovery), 1),
            signal_effectiveness=signal_eff,
            recommendations=recs,
        )

    # -- recommend config --------------------------------------------------

    def recommend_shedding_config(
        self,
        graph: InfraGraph,
        component_id: str,
    ) -> SheddingConfig:
        """Generate a recommended shedding config for a component."""
        comp = graph.get_component(component_id)

        strategy = SheddingStrategy.ADAPTIVE
        threshold = 80.0
        queue_depth = 1000
        priority_levels = 3
        graceful = True
        signal = BackpressureSignal.HTTP_429

        if comp is not None:
            # Tailor by component type
            if comp.type == ComponentType.LOAD_BALANCER:
                strategy = SheddingStrategy.TOKEN_BUCKET
                signal = BackpressureSignal.RATE_LIMIT_HEADER
            elif comp.type == ComponentType.APP_SERVER:
                strategy = SheddingStrategy.PRIORITY_BASED
                signal = BackpressureSignal.HTTP_429
            elif comp.type == ComponentType.DATABASE:
                strategy = SheddingStrategy.CLIENT_THROTTLE
                signal = BackpressureSignal.CONNECTION_REFUSE
                threshold = 70.0
            elif comp.type == ComponentType.QUEUE:
                strategy = SheddingStrategy.ADAPTIVE
                signal = BackpressureSignal.QUEUE_FULL
            elif comp.type == ComponentType.CACHE:
                strategy = SheddingStrategy.TOKEN_BUCKET
                signal = BackpressureSignal.RESPONSE_DEGRADATION
                threshold = 85.0
            elif comp.type == ComponentType.WEB_SERVER:
                strategy = SheddingStrategy.FIFO
                signal = BackpressureSignal.HTTP_429

            # Adjust queue depth by capacity
            queue_depth = max(100, comp.capacity.max_connections)

            # If autoscaling is enabled, raise threshold (more headroom)
            if comp.autoscaling.enabled:
                threshold = min(95.0, threshold + 10.0)

            # If replicas > 1, slightly higher threshold
            if comp.replicas > 2:
                threshold = min(95.0, threshold + 5.0)

        return SheddingConfig(
            strategy=strategy,
            threshold_percent=threshold,
            max_queue_depth=queue_depth,
            priority_levels=priority_levels,
            graceful_degradation=graceful,
            backpressure_signal=signal,
        )

    # -- graceful degradation ----------------------------------------------

    def simulate_graceful_degradation(
        self,
        graph: InfraGraph,
        component_id: str,
        load: LoadProfile,
    ) -> DegradationResult:
        """Simulate progressive feature degradation under increasing load."""
        comp = graph.get_component(component_id)

        effective_rps = load.requests_per_second * load.burst_multiplier
        if comp is not None:
            max_rps = float(comp.capacity.max_rps) * comp.replicas
        else:
            max_rps = effective_rps

        load_ratio = effective_rps / max(max_rps, 1.0)

        levels: list[str] = []
        features_off: list[str] = []
        recovery_seq: list[str] = []

        if load_ratio <= 0.7:
            levels.append("normal")
            remaining = 100.0
        elif load_ratio <= 0.85:
            levels.append("normal")
            levels.append("reduced_quality")
            features_off.append("analytics")
            features_off.append("non-critical-logging")
            remaining = 85.0
        elif load_ratio <= 1.0:
            levels.append("normal")
            levels.append("reduced_quality")
            levels.append("essential_only")
            features_off.extend(["analytics", "non-critical-logging", "recommendations", "search-suggestions"])
            remaining = 60.0
        else:
            levels.append("normal")
            levels.append("reduced_quality")
            levels.append("essential_only")
            levels.append("emergency")
            features_off.extend([
                "analytics", "non-critical-logging", "recommendations",
                "search-suggestions", "image-processing", "batch-jobs",
            ])
            remaining = max(10.0, 100.0 - (load_ratio - 1.0) * 80.0)

        remaining = _clamp(remaining)

        # User impact inversely related to remaining capacity
        user_impact = _clamp(100.0 - remaining)

        # Recovery is the reverse order
        recovery_seq = list(reversed(levels))

        recs: list[str] = []
        if load_ratio > 1.0:
            recs.append("System is over capacity; scale up immediately")
        if load_ratio > 0.85:
            recs.append("Enable adaptive shedding to complement degradation")
        if not features_off:
            recs.append("Load is within normal range; no degradation needed")

        return DegradationResult(
            degradation_levels=levels,
            features_disabled=features_off,
            remaining_capacity_percent=round(remaining, 1),
            user_impact_score=round(user_impact, 1),
            recovery_sequence=recovery_seq,
            recommendations=recs,
        )

    # -- goodput analysis --------------------------------------------------

    def calculate_goodput(
        self,
        graph: InfraGraph,
        component_id: str,
        load: LoadProfile,
        config: SheddingConfig,
    ) -> GoodputAnalysis:
        """Calculate the effective useful throughput (goodput)."""
        comp = graph.get_component(component_id)
        shed_fraction = _compute_shed_fraction(load, config, comp)
        efficiency = _STRATEGY_EFFICIENCY.get(config.strategy, 0.5)

        effective_rps = load.requests_per_second * load.burst_multiplier
        accepted_rps = effective_rps * (1.0 - shed_fraction)

        # Goodput = accepted requests that are actually useful
        # Some accepted requests may still be retries / wasted work
        goodput = accepted_rps * efficiency
        wasted = effective_rps - goodput

        goodput_ratio = goodput / max(effective_rps, 1.0)
        goodput_ratio = _clamp(goodput_ratio, 0.0, 1.0)

        # Latency overhead from the shedding logic itself
        overhead = _STRATEGY_OVERHEAD.get(config.strategy, 1.0)
        if shed_fraction > 0:
            overhead += shed_fraction * 5.0  # extra overhead under shedding

        recs: list[str] = []
        if goodput_ratio < 0.5:
            recs.append(
                "Goodput is below 50%; significant resources are wasted. "
                "Consider a more efficient shedding strategy"
            )
        if goodput_ratio < 0.8 and config.strategy == SheddingStrategy.RANDOM_DROP:
            recs.append(
                "Random drop has low efficiency; switch to priority-based or "
                "adaptive shedding for better goodput"
            )
        if shed_fraction > 0.3:
            recs.append("High shedding rate impacts goodput; consider capacity expansion")

        return GoodputAnalysis(
            total_throughput_rps=round(effective_rps, 2),
            goodput_rps=round(goodput, 2),
            wasted_rps=round(max(0.0, wasted), 2),
            goodput_ratio=round(goodput_ratio, 4),
            latency_overhead_ms=round(overhead, 2),
            recommendations=recs,
        )
