# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Latency injection simulator and P99 tail latency analyzer.

Simulates various latency injection patterns and analyzes tail latency
behavior across infrastructure dependency graphs.  Uses only stdlib math
(no numpy) for distribution generation and percentile computation.
"""

from __future__ import annotations

import math
import random
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class LatencyPattern(str, Enum):
    """Latency injection pattern types."""

    CONSTANT_DELAY = "constant_delay"
    RANDOM_UNIFORM = "random_uniform"
    RANDOM_GAUSSIAN = "random_gaussian"
    SPIKE = "spike"
    GRADUAL_INCREASE = "gradual_increase"
    PERIODIC_SPIKE = "periodic_spike"
    JITTER = "jitter"
    CASCADE_DELAY = "cascade_delay"
    NETWORK_PARTITION_DELAY = "network_partition_delay"
    GC_PAUSE_SIMULATION = "gc_pause_simulation"
    THUNDERING_HERD = "thundering_herd"
    CONNECTION_POOL_EXHAUSTION = "connection_pool_exhaustion"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class LatencyProfile(BaseModel):
    """Configuration for a latency injection experiment."""

    pattern: LatencyPattern
    base_latency_ms: float = 10.0
    injected_latency_ms: float = 100.0
    duration_seconds: float = 60.0
    affected_percentile: float = 100.0
    parameters: dict[str, float | int | str] = Field(default_factory=dict)


class LatencyDistribution(BaseModel):
    """Statistical summary of a latency sample."""

    p50_ms: float = 0.0
    p90_ms: float = 0.0
    p95_ms: float = 0.0
    p99_ms: float = 0.0
    p999_ms: float = 0.0
    mean_ms: float = 0.0
    median_ms: float = 0.0
    stddev_ms: float = 0.0
    min_ms: float = 0.0
    max_ms: float = 0.0
    sample_count: int = 0


class AmplificationResult(BaseModel):
    """Result of latency amplification detection across a dependency chain."""

    chain: list[str]
    per_hop_latency: dict[str, float]
    total_latency_ms: float = 0.0
    amplification_factor: float = 1.0
    bottleneck_component: str = ""


class TimeoutCascadeResult(BaseModel):
    """Result of a timeout cascade simulation."""

    origin_component_id: str
    timeout_ms: float
    timed_out_components: list[str] = Field(default_factory=list)
    cascade_depth: int = 0
    total_affected: int = 0
    cascade_timeline: list[dict[str, object]] = Field(default_factory=list)


class TailLatencyAnalysis(BaseModel):
    """Full tail-latency analysis result for a single component."""

    component_id: str
    baseline_distribution: LatencyDistribution = Field(
        default_factory=LatencyDistribution
    )
    injected_distribution: LatencyDistribution = Field(
        default_factory=LatencyDistribution
    )
    amplification_factor: float = 1.0
    slo_breach: bool = False
    slo_target_ms: float = 500.0
    breach_percentile: str = ""
    cascade_latency_impact: dict[str, float] = Field(default_factory=dict)
    recommendations: list[str] = Field(default_factory=list)
    timestamp: str = ""


# ---------------------------------------------------------------------------
# Internal helpers (stdlib-only statistics)
# ---------------------------------------------------------------------------


def _percentile(sorted_data: list[float], pct: float) -> float:
    """Compute the *pct*-th percentile of *sorted_data* (already sorted)."""
    if not sorted_data:
        return 0.0
    if len(sorted_data) == 1:
        return sorted_data[0]
    k = (pct / 100.0) * (len(sorted_data) - 1)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_data[int(k)]
    d0 = sorted_data[int(f)] * (c - k)
    d1 = sorted_data[int(c)] * (k - f)
    return d0 + d1


def _mean(data: list[float]) -> float:
    if not data:
        return 0.0
    return sum(data) / len(data)


def _stddev(data: list[float], mean_val: float) -> float:
    if len(data) < 2:
        return 0.0
    variance = sum((x - mean_val) ** 2 for x in data) / (len(data) - 1)
    return math.sqrt(variance)


def _distribution_from_samples(samples: list[float]) -> LatencyDistribution:
    """Build a ``LatencyDistribution`` from raw latency samples."""
    if not samples:
        return LatencyDistribution()
    s = sorted(samples)
    m = _mean(s)
    return LatencyDistribution(
        p50_ms=round(_percentile(s, 50), 4),
        p90_ms=round(_percentile(s, 90), 4),
        p95_ms=round(_percentile(s, 95), 4),
        p99_ms=round(_percentile(s, 99), 4),
        p999_ms=round(_percentile(s, 99.9), 4),
        mean_ms=round(m, 4),
        median_ms=round(_percentile(s, 50), 4),
        stddev_ms=round(_stddev(s, m), 4),
        min_ms=round(s[0], 4),
        max_ms=round(s[-1], 4),
        sample_count=len(s),
    )


# ---------------------------------------------------------------------------
# Sample generation per pattern
# ---------------------------------------------------------------------------


def _generate_samples(profile: LatencyProfile, rng: random.Random, n: int = 1000) -> list[float]:
    """Generate *n* latency samples according to the given profile."""
    base = profile.base_latency_ms
    injected = profile.injected_latency_ms
    affected_ratio = profile.affected_percentile / 100.0
    params = profile.parameters
    samples: list[float] = []

    for i in range(n):
        # Decide whether this request is "affected" by the injection
        if rng.random() > affected_ratio:
            # Not affected — use baseline latency with small jitter
            samples.append(max(0.0, base + rng.gauss(0, base * 0.05)))
            continue

        pattern = profile.pattern

        if pattern == LatencyPattern.CONSTANT_DELAY:
            samples.append(base + injected)

        elif pattern == LatencyPattern.RANDOM_UNIFORM:
            lo = float(params.get("min_ms", 0))
            hi = float(params.get("max_ms", injected))
            samples.append(base + rng.uniform(lo, hi))

        elif pattern == LatencyPattern.RANDOM_GAUSSIAN:
            stddev = float(params.get("stddev_ms", injected * 0.3))
            val = rng.gauss(injected, stddev)
            samples.append(max(0.0, base + val))

        elif pattern == LatencyPattern.SPIKE:
            spike_ratio = float(params.get("spike_ratio", 0.05))
            if rng.random() < spike_ratio:
                multiplier = float(params.get("spike_multiplier", 10.0))
                samples.append(base + injected * multiplier)
            else:
                samples.append(base + rng.gauss(0, base * 0.05))

        elif pattern == LatencyPattern.GRADUAL_INCREASE:
            progress = i / max(n - 1, 1)
            samples.append(base + injected * progress)

        elif pattern == LatencyPattern.PERIODIC_SPIKE:
            period = int(params.get("period", 100))
            spike_multiplier = float(params.get("spike_multiplier", 5.0))
            if i % period == 0:
                samples.append(base + injected * spike_multiplier)
            else:
                samples.append(base + rng.gauss(0, base * 0.05))

        elif pattern == LatencyPattern.JITTER:
            jitter_range = float(params.get("jitter_range_ms", injected))
            samples.append(base + rng.uniform(0, jitter_range))

        elif pattern == LatencyPattern.CASCADE_DELAY:
            hop_count = int(params.get("hop_count", 3))
            per_hop = injected / max(hop_count, 1)
            total = sum(per_hop + rng.gauss(0, per_hop * 0.1) for _ in range(hop_count))
            samples.append(max(0.0, base + total))

        elif pattern == LatencyPattern.NETWORK_PARTITION_DELAY:
            partition_prob = float(params.get("partition_probability", 0.1))
            partition_latency = float(params.get("partition_latency_ms", injected * 5))
            if rng.random() < partition_prob:
                samples.append(base + partition_latency)
            else:
                samples.append(base + rng.gauss(0, base * 0.05))

        elif pattern == LatencyPattern.GC_PAUSE_SIMULATION:
            gc_prob = float(params.get("gc_probability", 0.02))
            minor_gc_ms = float(params.get("minor_gc_ms", injected * 0.5))
            major_gc_ms = float(params.get("major_gc_ms", injected * 3))
            major_gc_ratio = float(params.get("major_gc_ratio", 0.1))
            if rng.random() < gc_prob:
                if rng.random() < major_gc_ratio:
                    samples.append(base + major_gc_ms)
                else:
                    samples.append(base + minor_gc_ms)
            else:
                samples.append(base + rng.gauss(0, base * 0.05))

        elif pattern == LatencyPattern.THUNDERING_HERD:
            herd_size = int(params.get("herd_size", 50))
            position = i % herd_size
            queue_factor = 1.0 + (position / max(herd_size - 1, 1)) * float(
                params.get("queue_multiplier", 5.0)
            )
            samples.append(base + injected * queue_factor)

        elif pattern == LatencyPattern.CONNECTION_POOL_EXHAUSTION:
            int(params.get("pool_size", 20))
            utilization = float(params.get("pool_utilization", 0.95))
            if rng.random() < utilization:
                wait_factor = rng.expovariate(1.0 / injected)
                samples.append(base + wait_factor)
            else:
                samples.append(base + rng.gauss(0, base * 0.05))

        else:
            # Fallback for unknown patterns
            samples.append(base + injected)

    return samples


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class LatencyInjectionEngine:
    """Stateless engine for latency injection simulation and analysis.

    All state is passed in via parameters — the engine itself holds no
    mutable data.  Supply an optional ``seed`` to get reproducible results.
    """

    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)

    # -- public API ----------------------------------------------------------

    def inject_latency(
        self,
        component: object,  # Component, but kept generic for testability
        profile: LatencyProfile,
        *,
        sample_count: int = 1000,
    ) -> LatencyDistribution:
        """Simulate latency injection and return the resulting distribution."""
        samples = _generate_samples(profile, self._rng, n=sample_count)
        return _distribution_from_samples(samples)

    def analyze_tail_latency(
        self,
        graph: InfraGraph,
        component_id: str,
        profile: LatencyProfile,
        *,
        slo_target_ms: float = 500.0,
        sample_count: int = 1000,
    ) -> TailLatencyAnalysis:
        """Run a full tail-latency analysis for *component_id*."""
        component = graph.get_component(component_id)
        if component is None:
            return TailLatencyAnalysis(
                component_id=component_id,
                slo_target_ms=slo_target_ms,
                recommendations=["Component not found in graph."],
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

        # Baseline (no injection)
        baseline_profile = LatencyProfile(
            pattern=LatencyPattern.CONSTANT_DELAY,
            base_latency_ms=profile.base_latency_ms,
            injected_latency_ms=0.0,
            duration_seconds=profile.duration_seconds,
            affected_percentile=0.0,
        )
        baseline_dist = self.inject_latency(component, baseline_profile, sample_count=sample_count)

        # Injected
        injected_dist = self.inject_latency(component, profile, sample_count=sample_count)

        # Amplification factor
        base_p99 = baseline_dist.p99_ms if baseline_dist.p99_ms > 0 else 1.0
        amp_factor = injected_dist.p99_ms / base_p99

        # SLO breach detection
        slo_breach = False
        breach_pct = ""
        for label, val in [
            ("p50", injected_dist.p50_ms),
            ("p90", injected_dist.p90_ms),
            ("p95", injected_dist.p95_ms),
            ("p99", injected_dist.p99_ms),
            ("p999", injected_dist.p999_ms),
        ]:
            if val > slo_target_ms:
                slo_breach = True
                breach_pct = label
                break

        # Cascade impact on downstream dependents
        cascade_impact: dict[str, float] = {}
        dependents = graph.get_dependents(component_id)
        for dep in dependents:
            edge = graph.get_dependency_edge(dep.id, component_id)
            edge_latency = edge.latency_ms if edge else 0.0
            added = injected_dist.p99_ms - baseline_dist.p99_ms + edge_latency
            cascade_impact[dep.id] = round(added, 4)

        # Recommendations
        recs = self._generate_recommendations(
            profile, injected_dist, amp_factor, slo_breach, slo_target_ms
        )

        return TailLatencyAnalysis(
            component_id=component_id,
            baseline_distribution=baseline_dist,
            injected_distribution=injected_dist,
            amplification_factor=round(amp_factor, 4),
            slo_breach=slo_breach,
            slo_target_ms=slo_target_ms,
            breach_percentile=breach_pct,
            cascade_latency_impact=cascade_impact,
            recommendations=recs,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def detect_latency_amplification(
        self,
        graph: InfraGraph,
        profiles: dict[str, LatencyProfile],
        *,
        sample_count: int = 1000,
    ) -> list[AmplificationResult]:
        """Detect latency amplification across dependency chains.

        *profiles* maps component-id to its ``LatencyProfile``.  Returns an
        ``AmplificationResult`` for each critical path where amplification
        exceeds 1.0.
        """
        results: list[AmplificationResult] = []
        critical_paths = graph.get_critical_paths(max_paths=50)

        for path in critical_paths:
            per_hop: dict[str, float] = {}
            total = 0.0
            bottleneck = ""
            max_lat = 0.0

            for comp_id in path:
                component = graph.get_component(comp_id)
                if component is None:
                    continue
                prof = profiles.get(comp_id)
                if prof:
                    dist = self.inject_latency(component, prof, sample_count=sample_count)
                    hop_lat = dist.p99_ms
                else:
                    # No injection profile — use a small baseline
                    hop_lat = 5.0
                per_hop[comp_id] = round(hop_lat, 4)
                total += hop_lat
                if hop_lat > max_lat:
                    max_lat = hop_lat
                    bottleneck = comp_id

            # Calculate expected (sum of baselines)
            expected = sum(
                profiles[c].base_latency_ms if c in profiles else 5.0
                for c in path
            )
            amp = total / expected if expected > 0 else 1.0

            results.append(
                AmplificationResult(
                    chain=path,
                    per_hop_latency=per_hop,
                    total_latency_ms=round(total, 4),
                    amplification_factor=round(amp, 4),
                    bottleneck_component=bottleneck,
                )
            )

        # Sort by amplification factor descending
        results.sort(key=lambda r: r.amplification_factor, reverse=True)
        return results

    def simulate_timeout_cascade(
        self,
        graph: InfraGraph,
        component_id: str,
        timeout_ms: float,
        *,
        sample_count: int = 500,
    ) -> TimeoutCascadeResult:
        """Simulate cascading timeouts starting from *component_id*.

        When a component's p99 latency exceeds *timeout_ms*, its upstream
        dependents inherit additional latency and may also time out.
        """
        timed_out: list[str] = []
        timeline: list[dict[str, object]] = []
        visited: set[str] = set()

        # Seed: the origin component always "times out"
        queue: list[tuple[str, int]] = [(component_id, 0)]
        component_latencies: dict[str, float] = {}

        while queue:
            cid, depth = queue.pop(0)
            if cid in visited:
                continue
            visited.add(cid)

            comp = graph.get_component(cid)
            if comp is None:
                continue

            # For the origin, assume full timeout; for others, compute
            if cid == component_id:
                effective_latency = timeout_ms
            else:
                # Latency = timeout of downstream dep + own processing
                own_base = comp.network.rtt_ms
                dep_ids = [d.id for d in graph.get_dependencies(cid)]
                max_downstream = max(
                    (component_latencies.get(did, 0.0)
                     for did in dep_ids if did in component_latencies),
                    default=0.0,
                )
                effective_latency = own_base + max_downstream

            component_latencies[cid] = effective_latency

            status = "timeout" if effective_latency >= timeout_ms else "ok"
            timeline.append(
                {
                    "component_id": cid,
                    "depth": depth,
                    "latency_ms": round(effective_latency, 2),
                    "status": status,
                }
            )
            if status == "timeout":
                timed_out.append(cid)
            # Always propagate upstream so we can report ok/timeout for all
            # reachable components in the dependency chain.
            for dep in graph.get_dependents(cid):
                if dep.id not in visited:
                    queue.append((dep.id, depth + 1))

        max_depth = max((e["depth"] for e in timeline), default=0)  # type: ignore[arg-type]

        return TimeoutCascadeResult(
            origin_component_id=component_id,
            timeout_ms=timeout_ms,
            timed_out_components=timed_out,
            cascade_depth=int(max_depth),
            total_affected=len(timed_out),
            cascade_timeline=timeline,
        )

    def recommend_timeout_budget(
        self,
        graph: InfraGraph,
        slo_target_ms: float,
    ) -> dict[str, float]:
        """Recommend per-component timeout budgets to meet the overall SLO.

        The budget is distributed proportionally based on the component's
        position in the longest critical path, reserving headroom.
        """
        critical_paths = graph.get_critical_paths(max_paths=10)
        if not critical_paths:
            # No paths — give every component the full budget
            return {
                cid: round(slo_target_ms, 2)
                for cid in graph.components
            }

        # Use the longest path
        longest = critical_paths[0]
        hop_count = len(longest)

        # Reserve 20% headroom
        usable = slo_target_ms * 0.8
        per_hop = usable / max(hop_count, 1)

        budgets: dict[str, float] = {}
        for cid in graph.components:
            if cid in longest:
                budgets[cid] = round(per_hop, 2)
            else:
                # Components not on the critical path get a generous budget
                budgets[cid] = round(slo_target_ms * 0.5, 2)

        return budgets

    def generate_latency_heatmap(
        self,
        graph: InfraGraph,
        profiles: dict[str, LatencyProfile],
        *,
        sample_count: int = 500,
    ) -> dict:
        """Generate heatmap data suitable for visualization.

        Returns a dict with ``components`` (list of per-component data),
        ``edges`` (source/target latency), and ``metadata``.
        """
        components_data: list[dict] = []
        for cid, comp in graph.components.items():
            prof = profiles.get(cid)
            if prof:
                dist = self.inject_latency(comp, prof, sample_count=sample_count)
            else:
                dist = LatencyDistribution(
                    p50_ms=comp.network.rtt_ms,
                    p90_ms=comp.network.rtt_ms * 1.2,
                    p95_ms=comp.network.rtt_ms * 1.5,
                    p99_ms=comp.network.rtt_ms * 2.0,
                    p999_ms=comp.network.rtt_ms * 3.0,
                    mean_ms=comp.network.rtt_ms,
                    median_ms=comp.network.rtt_ms,
                    stddev_ms=comp.network.rtt_ms * 0.1,
                    min_ms=comp.network.rtt_ms * 0.8,
                    max_ms=comp.network.rtt_ms * 3.0,
                    sample_count=0,
                )
            severity = "low"
            if dist.p99_ms > 500:
                severity = "critical"
            elif dist.p99_ms > 200:
                severity = "high"
            elif dist.p99_ms > 50:
                severity = "medium"

            components_data.append(
                {
                    "component_id": cid,
                    "component_name": comp.name,
                    "p50_ms": dist.p50_ms,
                    "p99_ms": dist.p99_ms,
                    "severity": severity,
                    "has_injection": cid in profiles,
                }
            )

        edges_data: list[dict] = []
        for dep in graph.all_dependency_edges():
            edges_data.append(
                {
                    "source": dep.source_id,
                    "target": dep.target_id,
                    "latency_ms": dep.latency_ms,
                }
            )

        return {
            "components": components_data,
            "edges": edges_data,
            "metadata": {
                "total_components": len(graph.components),
                "total_edges": len(edges_data),
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
        }

    # -- internal helpers ----------------------------------------------------

    @staticmethod
    def _generate_recommendations(
        profile: LatencyProfile,
        dist: LatencyDistribution,
        amp_factor: float,
        slo_breach: bool,
        slo_target_ms: float,
    ) -> list[str]:
        """Generate actionable recommendations based on analysis results."""
        recs: list[str] = []

        if slo_breach:
            recs.append(
                f"SLO breach detected: tail latency ({dist.p99_ms:.1f}ms) "
                f"exceeds target ({slo_target_ms:.1f}ms). "
                "Consider adding caching or reducing injected latency."
            )

        if amp_factor > 5.0:
            recs.append(
                "Severe latency amplification (>5x). "
                "Implement circuit breakers and request hedging."
            )
        elif amp_factor > 2.0:
            recs.append(
                "Moderate latency amplification (>2x). "
                "Consider adding timeouts and retry budgets."
            )

        if profile.pattern == LatencyPattern.THUNDERING_HERD:
            recs.append(
                "Thundering herd pattern detected. "
                "Implement request coalescing or jittered retries."
            )

        if profile.pattern == LatencyPattern.CONNECTION_POOL_EXHAUSTION:
            recs.append(
                "Connection pool exhaustion pattern. "
                "Increase pool size or implement connection queuing."
            )

        if profile.pattern == LatencyPattern.GC_PAUSE_SIMULATION:
            recs.append(
                "GC pause impact detected. "
                "Consider tuning GC parameters or switching to a low-pause collector."
            )

        if dist.stddev_ms > dist.mean_ms:
            recs.append(
                "High latency variance (stddev > mean). "
                "Investigate sources of non-deterministic latency."
            )

        if dist.p99_ms > dist.p50_ms * 10:
            recs.append(
                "Large gap between p50 and p99 (>10x). "
                "Long-tail requests may indicate resource contention."
            )

        if not recs:
            recs.append("Latency profile is within acceptable bounds.")

        return recs
