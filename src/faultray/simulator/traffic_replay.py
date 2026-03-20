# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Traffic Replay Simulator -- replay production traffic patterns against infra.

Simulates replaying production traffic patterns against infrastructure
configurations to test resilience under realistic load conditions.  Generates
synthetic traffic snapshots for various patterns (steady-state, spike, diurnal,
etc.) and evaluates how the infrastructure graph responds, identifying
bottlenecks, saturation events, and breaking points.
"""

from __future__ import annotations

import logging
import math
import random
from enum import Enum

from pydantic import BaseModel, Field

from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)

# Seeded RNG for reproducible pattern generation.
_rng = random.Random(42)

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TrafficPattern(str, Enum):
    """Types of production traffic patterns that can be replayed."""

    STEADY_STATE = "steady_state"
    RAMP_UP = "ramp_up"
    SPIKE = "spike"
    DIURNAL = "diurnal"
    WEEKLY_CYCLE = "weekly_cycle"
    EVENT_DRIVEN = "event_driven"
    SEASONAL = "seasonal"
    RANDOM_BURST = "random_burst"


class ReplayMode(str, Enum):
    """How recorded traffic should be replayed."""

    EXACT = "exact"
    SCALED = "scaled"
    FILTERED = "filtered"
    TIME_COMPRESSED = "time_compressed"
    REVERSED = "reversed"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class TrafficSnapshot(BaseModel):
    """A point-in-time observation of traffic metrics."""

    timestamp: str = Field(description="ISO-8601 or relative timestamp.")
    requests_per_second: float = Field(
        ge=0.0, description="Observed RPS at this instant."
    )
    error_rate: float = Field(
        ge=0.0, le=1.0, description="Error rate as a fraction 0-1."
    )
    latency_p50_ms: float = Field(ge=0.0, description="Median latency (ms).")
    latency_p99_ms: float = Field(ge=0.0, description="99th-percentile latency (ms).")
    unique_endpoints: int = Field(ge=0, description="Number of unique endpoints hit.")


class ReplayConfig(BaseModel):
    """Configuration for a traffic replay session."""

    mode: ReplayMode = ReplayMode.EXACT
    scale_factor: float = Field(
        default=1.0, ge=0.0, description="Multiplier applied to RPS."
    )
    time_compression: float = Field(
        default=1.0, gt=0.0, description="Speed-up factor for time-compressed mode."
    )
    pattern: TrafficPattern = TrafficPattern.STEADY_STATE
    duration_minutes: float = Field(
        default=60.0, gt=0.0, description="Total replay duration in minutes."
    )
    snapshots: list[TrafficSnapshot] = Field(
        default_factory=list,
        description="Pre-recorded snapshots to replay.",
    )


class ReplayResult(BaseModel):
    """Outcome of replaying traffic against an infrastructure graph."""

    total_requests: int = Field(ge=0)
    successful_requests: int = Field(ge=0)
    failed_requests: int = Field(ge=0)
    peak_rps: float = Field(ge=0.0)
    avg_latency_ms: float = Field(ge=0.0)
    p99_latency_ms: float = Field(ge=0.0)
    bottleneck_components: list[str] = Field(default_factory=list)
    saturation_events: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class ReplayComparison(BaseModel):
    """Side-by-side comparison of multiple replay results."""

    results: list[ReplayResult] = Field(default_factory=list)
    best_index: int = Field(
        default=0, description="Index of the best-performing result."
    )
    worst_index: int = Field(
        default=0, description="Index of the worst-performing result."
    )
    delta_peak_rps: float = Field(
        default=0.0, description="Difference in peak RPS across results."
    )
    delta_avg_latency_ms: float = Field(
        default=0.0,
        description="Difference in avg latency across results.",
    )
    summary: str = Field(default="", description="Human-readable comparison summary.")


class CapacityHeadroom(BaseModel):
    """How much capacity headroom remains before saturation."""

    current_rps: float = Field(default=0.0, ge=0.0)
    max_sustainable_rps: float = Field(default=0.0, ge=0.0)
    headroom_percent: float = Field(
        default=0.0, description="Percentage of remaining capacity."
    )
    limiting_component: str = Field(
        default="", description="Component that hits capacity first."
    )
    time_to_saturation_minutes: float = Field(
        default=0.0,
        description="Estimated minutes until saturation under current growth.",
    )
    recommendations: list[str] = Field(default_factory=list)


class TrafficShiftResult(BaseModel):
    """Result of shifting from one traffic pattern to another."""

    from_pattern: TrafficPattern
    to_pattern: TrafficPattern
    transition_duration_minutes: float = Field(default=0.0, ge=0.0)
    peak_rps_during_shift: float = Field(default=0.0, ge=0.0)
    errors_during_shift: int = Field(default=0, ge=0)
    latency_spike_ms: float = Field(default=0.0, ge=0.0)
    components_affected: list[str] = Field(default_factory=list)
    stable_after_minutes: float = Field(default=0.0, ge=0.0)
    recommendations: list[str] = Field(default_factory=list)


class BreakingPointResult(BaseModel):
    """Result of finding the infrastructure's breaking point."""

    breaking_rps: float = Field(default=0.0, ge=0.0)
    breaking_component: str = Field(default="")
    max_sustainable_rps: float = Field(default=0.0, ge=0.0)
    safety_margin_percent: float = Field(default=0.0)
    cascade_components: list[str] = Field(default_factory=list)
    failure_mode: str = Field(
        default="", description="How the system fails (e.g. 'timeout', 'OOM')."
    )
    recommendations: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

# Baseline latency per component type (ms per request hop).
_BASE_LATENCY: dict[str, float] = {
    "load_balancer": 1.0,
    "web_server": 5.0,
    "app_server": 15.0,
    "database": 10.0,
    "cache": 2.0,
    "queue": 8.0,
    "storage": 12.0,
    "dns": 3.0,
    "external_api": 50.0,
    "custom": 10.0,
}

# Saturation multiplier: latency increases by this factor when utilization
# exceeds the component's max_rps threshold.
_SATURATION_LATENCY_FACTOR = 3.0


def _effective_max_rps(graph: InfraGraph) -> tuple[float, str]:
    """Return (max_rps, limiting_component_id) for the bottleneck component."""
    min_rps = float("inf")
    limiting = ""
    for comp in graph.components.values():
        effective = comp.capacity.max_rps * comp.replicas
        if comp.autoscaling.enabled:
            effective = comp.capacity.max_rps * comp.autoscaling.max_replicas
        if effective < min_rps:
            min_rps = effective
            limiting = comp.id
    if min_rps == float("inf"):
        return (0.0, "")
    return (min_rps, limiting)


def _component_latency(comp_type: str, load_ratio: float) -> float:
    """Estimate latency for a component type under a given load ratio (0-1+)."""
    base = _BASE_LATENCY.get(comp_type, 10.0)
    if load_ratio <= 1.0:
        # Linear ramp from base to 2x base at full utilisation.
        return base * (1.0 + load_ratio)
    # Beyond capacity: exponential degradation.
    return base * (1.0 + load_ratio * _SATURATION_LATENCY_FACTOR)


def _error_rate_for_load(load_ratio: float) -> float:
    """Estimate error rate for a given load ratio."""
    if load_ratio < 0.01:
        return 0.0  # negligible load, no errors
    if load_ratio <= 0.8:
        return 0.001  # baseline
    if load_ratio <= 1.0:
        # Ramp errors from 0.1% to 5% between 80-100% load.
        return 0.001 + (load_ratio - 0.8) / 0.2 * 0.049
    # Beyond capacity: errors grow rapidly.
    excess = load_ratio - 1.0
    return min(0.05 + excess * 0.5, 1.0)


def _detect_component_bottlenecks(
    graph: InfraGraph, rps: float
) -> tuple[list[str], list[str]]:
    """Return (bottleneck_ids, saturation_event_messages)."""
    bottlenecks: list[str] = []
    events: list[str] = []
    for comp in graph.components.values():
        effective_max = comp.capacity.max_rps * comp.replicas
        if comp.autoscaling.enabled:
            effective_max = comp.capacity.max_rps * comp.autoscaling.max_replicas
        ratio = rps / effective_max if effective_max > 0 else float("inf")
        if ratio > 0.8:
            bottlenecks.append(comp.id)
        if ratio > 1.0:
            events.append(
                f"{comp.id} saturated at {rps:.0f} RPS "
                f"(capacity {effective_max:.0f} RPS)"
            )
    return bottlenecks, events


def _generate_recommendations(
    bottlenecks: list[str],
    saturation_events: list[str],
    graph: InfraGraph,
    error_rate: float,
) -> list[str]:
    """Build actionable recommendations based on simulation findings."""
    recs: list[str] = []
    for cid in bottlenecks:
        comp = graph.get_component(cid)
        if comp is None:
            continue
        if not comp.autoscaling.enabled:
            recs.append(f"Enable autoscaling for {cid} to handle load spikes.")
        elif comp.replicas < comp.autoscaling.max_replicas:
            recs.append(
                f"Increase max_replicas for {cid} "
                f"(currently {comp.autoscaling.max_replicas})."
            )
        if comp.capacity.max_rps < 10000:
            recs.append(
                f"Consider vertical scaling for {cid} to raise per-instance RPS."
            )
    if saturation_events:
        recs.append("Add circuit breakers to prevent cascade failures during saturation.")
    if error_rate > 0.05:
        recs.append("Implement load shedding to protect downstream services.")
    if not recs:
        recs.append("Infrastructure handled replay traffic within acceptable limits.")
    return recs


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class TrafficReplayEngine:
    """Replays production traffic patterns against an InfraGraph.

    Provides methods to generate traffic patterns, replay them, detect
    bottlenecks, compare replays, estimate capacity headroom, and find
    the infrastructure's breaking point under increasing load.
    """

    def __init__(self, seed: int = 42) -> None:
        self._rng = random.Random(seed)

    # -- public API ----------------------------------------------------------

    def replay_traffic(
        self, graph: InfraGraph, config: ReplayConfig
    ) -> ReplayResult:
        """Replay traffic against *graph* according to *config*.

        Returns a :class:`ReplayResult` summarising the simulated outcome.
        """
        snapshots = config.snapshots
        if not snapshots:
            snapshots = self.generate_traffic_pattern(
                config.pattern,
                config.duration_minutes,
                peak_rps=1000.0,
            )

        # Apply replay-mode transformations.
        snapshots = self._apply_mode(snapshots, config)

        total_requests = 0
        failed_requests = 0
        latencies: list[float] = []
        peak_rps = 0.0
        all_bottlenecks: set[str] = set()
        all_saturation: list[str] = []

        max_rps, limiting = _effective_max_rps(graph)
        if max_rps == 0.0:
            max_rps = 1.0  # avoid division by zero

        for snap in snapshots:
            rps = snap.requests_per_second * config.scale_factor
            if rps > peak_rps:
                peak_rps = rps

            load_ratio = rps / max_rps
            error_rate = _error_rate_for_load(load_ratio)

            # Requests in this snapshot interval (assume 1-minute buckets).
            interval_requests = int(rps * 60)
            interval_failed = int(interval_requests * error_rate)
            total_requests += interval_requests
            failed_requests += interval_failed

            # Compute latency contribution across all component types.
            avg_lat = 0.0
            for comp in graph.components.values():
                comp_max = comp.capacity.max_rps * comp.replicas
                if comp.autoscaling.enabled:
                    comp_max = comp.capacity.max_rps * comp.autoscaling.max_replicas
                comp_ratio = rps / comp_max if comp_max > 0 else load_ratio
                avg_lat += _component_latency(comp.type.value, comp_ratio)
            latencies.append(avg_lat)

            bn, se = _detect_component_bottlenecks(graph, rps)
            all_bottlenecks.update(bn)
            all_saturation.extend(se)

        successful_requests = total_requests - failed_requests
        avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
        p99_latency = (
            sorted(latencies)[int(len(latencies) * 0.99)] if latencies else 0.0
        )

        overall_error_rate = (
            failed_requests / total_requests if total_requests > 0 else 0.0
        )
        recommendations = _generate_recommendations(
            list(all_bottlenecks), all_saturation, graph, overall_error_rate
        )

        return ReplayResult(
            total_requests=total_requests,
            successful_requests=successful_requests,
            failed_requests=failed_requests,
            peak_rps=peak_rps,
            avg_latency_ms=round(avg_latency, 2),
            p99_latency_ms=round(p99_latency, 2),
            bottleneck_components=sorted(all_bottlenecks),
            saturation_events=all_saturation,
            recommendations=recommendations,
        )

    def generate_traffic_pattern(
        self,
        pattern: TrafficPattern,
        duration: float,
        peak_rps: float,
    ) -> list[TrafficSnapshot]:
        """Generate a list of :class:`TrafficSnapshot` for *pattern*.

        *duration* is in minutes; one snapshot is emitted per minute.
        """
        count = max(1, int(duration))
        snapshots: list[TrafficSnapshot] = []

        for i in range(count):
            t = i / max(count - 1, 1)  # normalised time 0-1
            rps = self._pattern_rps(pattern, t, peak_rps, i)
            error_rate = _error_rate_for_load(rps / max(peak_rps, 1.0))
            base_lat = 10.0 + 40.0 * (rps / max(peak_rps, 1.0))
            snapshots.append(
                TrafficSnapshot(
                    timestamp=f"T+{i}m",
                    requests_per_second=round(rps, 2),
                    error_rate=round(error_rate, 4),
                    latency_p50_ms=round(base_lat, 2),
                    latency_p99_ms=round(base_lat * 2.5, 2),
                    unique_endpoints=max(1, int(rps / 10)),
                )
            )
        return snapshots

    def detect_bottlenecks(
        self, graph: InfraGraph, snapshots: list[TrafficSnapshot]
    ) -> list[str]:
        """Return component IDs that are bottlenecks for the given snapshots."""
        all_bn: set[str] = set()
        for snap in snapshots:
            bn, _ = _detect_component_bottlenecks(graph, snap.requests_per_second)
            all_bn.update(bn)
        return sorted(all_bn)

    def compare_replays(self, results: list[ReplayResult]) -> ReplayComparison:
        """Compare multiple :class:`ReplayResult` instances side-by-side."""
        if not results:
            return ReplayComparison()

        # Best = lowest avg latency; worst = highest.
        best_idx = min(range(len(results)), key=lambda i: results[i].avg_latency_ms)
        worst_idx = max(range(len(results)), key=lambda i: results[i].avg_latency_ms)

        peak_rps_values = [r.peak_rps for r in results]
        latency_values = [r.avg_latency_ms for r in results]

        delta_rps = max(peak_rps_values) - min(peak_rps_values)
        delta_lat = max(latency_values) - min(latency_values)

        best = results[best_idx]
        worst = results[worst_idx]
        summary = (
            f"Best replay (#{best_idx}) avg latency {best.avg_latency_ms:.1f} ms, "
            f"worst (#{worst_idx}) {worst.avg_latency_ms:.1f} ms. "
            f"Delta: {delta_lat:.1f} ms latency, {delta_rps:.1f} RPS range."
        )

        return ReplayComparison(
            results=results,
            best_index=best_idx,
            worst_index=worst_idx,
            delta_peak_rps=round(delta_rps, 2),
            delta_avg_latency_ms=round(delta_lat, 2),
            summary=summary,
        )

    def estimate_capacity_headroom(
        self, graph: InfraGraph, config: ReplayConfig
    ) -> CapacityHeadroom:
        """Estimate how much headroom the infra has before saturation."""
        max_rps, limiting = _effective_max_rps(graph)
        if max_rps == 0.0:
            return CapacityHeadroom(
                current_rps=0.0,
                max_sustainable_rps=0.0,
                headroom_percent=0.0,
                limiting_component=limiting,
                time_to_saturation_minutes=0.0,
                recommendations=["No components in graph."],
            )

        # Sustainable RPS = 80% of theoretical max (before error rate spikes).
        sustainable = max_rps * 0.8

        # Current RPS = average across snapshots (or pattern-generated).
        snapshots = config.snapshots
        if not snapshots:
            snapshots = self.generate_traffic_pattern(
                config.pattern, config.duration_minutes, peak_rps=1000.0
            )
        current = (
            sum(s.requests_per_second for s in snapshots) / len(snapshots)
            if snapshots
            else 0.0
        ) * config.scale_factor

        headroom = (
            ((sustainable - current) / sustainable * 100.0) if sustainable > 0 else 0.0
        )
        headroom = max(headroom, 0.0)

        # Rough time-to-saturation assuming 10% monthly growth.
        if current > 0 and current < sustainable:
            growth_rate = 0.10  # 10% monthly
            months = math.log(sustainable / current) / math.log(1 + growth_rate)
            time_to_sat = months * 30.0 * 24.0 * 60.0  # minutes
        else:
            time_to_sat = 0.0

        recs: list[str] = []
        if headroom < 20:
            recs.append(
                f"Capacity headroom is low ({headroom:.0f}%). "
                f"Scale {limiting} proactively."
            )
        if headroom < 50:
            recs.append("Consider enabling autoscaling if not already active.")
        if not recs:
            recs.append("Sufficient capacity headroom for projected growth.")

        return CapacityHeadroom(
            current_rps=round(current, 2),
            max_sustainable_rps=round(sustainable, 2),
            headroom_percent=round(headroom, 2),
            limiting_component=limiting,
            time_to_saturation_minutes=round(time_to_sat, 2),
            recommendations=recs,
        )

    def simulate_traffic_shift(
        self,
        graph: InfraGraph,
        from_pattern: TrafficPattern,
        to_pattern: TrafficPattern,
    ) -> TrafficShiftResult:
        """Simulate shifting from one traffic pattern to another."""
        duration = 30.0  # minutes for the transition
        half = int(duration / 2)
        peak_rps = 1000.0

        from_snaps = self.generate_traffic_pattern(from_pattern, half, peak_rps)
        to_snaps = self.generate_traffic_pattern(to_pattern, half, peak_rps)

        max_rps_val, limiting = _effective_max_rps(graph)
        if max_rps_val == 0.0:
            max_rps_val = 1.0

        transition_peak = 0.0
        total_errors = 0
        max_latency = 0.0
        affected: set[str] = set()

        all_snaps = from_snaps + to_snaps
        for snap in all_snaps:
            rps = snap.requests_per_second
            if rps > transition_peak:
                transition_peak = rps
            load_ratio = rps / max_rps_val
            err = _error_rate_for_load(load_ratio)
            total_errors += int(rps * 60 * err)
            lat = 0.0
            for comp in graph.components.values():
                comp_max = comp.capacity.max_rps * comp.replicas
                if comp.autoscaling.enabled:
                    comp_max = comp.capacity.max_rps * comp.autoscaling.max_replicas
                cr = rps / comp_max if comp_max > 0 else load_ratio
                lat += _component_latency(comp.type.value, cr)
                if cr > 0.8:
                    affected.add(comp.id)
            if lat > max_latency:
                max_latency = lat

        stable_after = duration * 0.7  # system stabilises after ~70% of window
        recs: list[str] = []
        if total_errors > 0:
            recs.append("Pre-warm caches before traffic pattern shifts.")
        if affected:
            recs.append(
                f"Monitor components during transition: {', '.join(sorted(affected))}."
            )
        if not recs:
            recs.append("Traffic shift completed without issues.")

        return TrafficShiftResult(
            from_pattern=from_pattern,
            to_pattern=to_pattern,
            transition_duration_minutes=duration,
            peak_rps_during_shift=round(transition_peak, 2),
            errors_during_shift=total_errors,
            latency_spike_ms=round(max_latency, 2),
            components_affected=sorted(affected),
            stable_after_minutes=round(stable_after, 2),
            recommendations=recs,
        )

    def find_breaking_point(
        self, graph: InfraGraph, pattern: TrafficPattern
    ) -> BreakingPointResult:
        """Progressively increase load until the infrastructure breaks."""
        max_rps_val, limiting = _effective_max_rps(graph)
        if max_rps_val == 0.0:
            return BreakingPointResult(
                breaking_rps=0.0,
                breaking_component=limiting,
                max_sustainable_rps=0.0,
                safety_margin_percent=0.0,
                cascade_components=[],
                failure_mode="no_capacity",
                recommendations=["No components with defined capacity."],
            )

        sustainable = max_rps_val * 0.8
        breaking = max_rps_val  # theoretical break point

        # Walk upward to find the actual breaking point.
        test_rps = sustainable
        step = max_rps_val * 0.05
        breaking_comp = limiting
        cascade: list[str] = []

        while test_rps <= max_rps_val * 2.0:
            err = _error_rate_for_load(test_rps / max_rps_val)
            if err > 0.10:  # >10% error rate = broken
                breaking = test_rps
                bn, _ = _detect_component_bottlenecks(graph, test_rps)
                if bn:
                    breaking_comp = bn[0]
                    cascade = bn[1:]
                break
            test_rps += step

        safety = (
            ((breaking - sustainable) / sustainable * 100.0) if sustainable > 0 else 0.0
        )

        # Failure mode describes how the system fails under excessive load.
        failure_mode = "overload"

        recs: list[str] = []
        recs.append(
            f"Breaking point at {breaking:.0f} RPS; "
            f"sustainable limit {sustainable:.0f} RPS."
        )
        if safety < 50:
            recs.append("Low safety margin. Add horizontal scaling capacity.")
        comp = graph.get_component(breaking_comp)
        if comp and not comp.autoscaling.enabled:
            recs.append(f"Enable autoscaling on {breaking_comp}.")
        if cascade:
            recs.append(
                f"Cascade risk: {', '.join(cascade)} may also fail."
            )

        return BreakingPointResult(
            breaking_rps=round(breaking, 2),
            breaking_component=breaking_comp,
            max_sustainable_rps=round(sustainable, 2),
            safety_margin_percent=round(safety, 2),
            cascade_components=cascade,
            failure_mode=failure_mode,
            recommendations=recs,
        )

    # -- internal helpers ----------------------------------------------------

    def _pattern_rps(
        self,
        pattern: TrafficPattern,
        t: float,
        peak_rps: float,
        index: int,
    ) -> float:
        """Compute RPS at normalised time *t* (0-1) for *pattern*."""
        if pattern == TrafficPattern.STEADY_STATE:
            return peak_rps * 0.6

        if pattern == TrafficPattern.RAMP_UP:
            return peak_rps * (0.1 + 0.9 * t)

        if pattern == TrafficPattern.SPIKE:
            # Gaussian spike centred at t=0.5.
            return peak_rps * (0.2 + 0.8 * math.exp(-((t - 0.5) ** 2) / 0.02))

        if pattern == TrafficPattern.DIURNAL:
            # Sinusoidal daily cycle.
            return peak_rps * (0.3 + 0.7 * (0.5 + 0.5 * math.sin(2 * math.pi * t)))

        if pattern == TrafficPattern.WEEKLY_CYCLE:
            # Weekly pattern: lower on "weekends" (t > 0.7).
            base = 0.5 + 0.5 * math.sin(2 * math.pi * t)
            weekend = 0.6 if t > 0.7 else 1.0
            return peak_rps * (0.2 + 0.8 * base * weekend)

        if pattern == TrafficPattern.EVENT_DRIVEN:
            # Sudden bursts at t=0.3 and t=0.7.
            if 0.28 <= t <= 0.32 or 0.68 <= t <= 0.72:
                return peak_rps
            return peak_rps * 0.3

        if pattern == TrafficPattern.SEASONAL:
            # Gradual seasonal build-up then decline.
            return peak_rps * (0.2 + 0.8 * math.sin(math.pi * t))

        if pattern == TrafficPattern.RANDOM_BURST:
            base = peak_rps * 0.4
            burst = self._rng.random() * peak_rps * 0.6
            return base + burst

        # All enum values are handled above; this is a defensive fallback
        # for forward-compatibility if new patterns are added.
        return peak_rps * 0.5

    def _apply_mode(
        self, snapshots: list[TrafficSnapshot], config: ReplayConfig
    ) -> list[TrafficSnapshot]:
        """Apply replay-mode transformations to snapshots."""
        if config.mode == ReplayMode.EXACT:
            return list(snapshots)

        if config.mode == ReplayMode.REVERSED:
            return list(reversed(snapshots))

        if config.mode == ReplayMode.FILTERED:
            # Keep only high-traffic snapshots (above median RPS).
            if not snapshots:
                return []
            median_rps = sorted(s.requests_per_second for s in snapshots)[
                len(snapshots) // 2
            ]
            return [s for s in snapshots if s.requests_per_second >= median_rps]

        if config.mode == ReplayMode.TIME_COMPRESSED:
            # Keep every Nth snapshot based on compression factor.
            step = max(1, int(config.time_compression))
            return snapshots[::step]

        # SCALED mode: scale_factor is applied during replay (in replay_traffic).
        return list(snapshots)
