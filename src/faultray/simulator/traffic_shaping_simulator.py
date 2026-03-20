# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Traffic Shaping Simulator -- evaluate traffic management strategies.

Simulates and evaluates traffic shaping and management strategies across
infrastructure topologies.  Covers traffic pattern generation (steady,
bursty, sinusoidal, spike, ramp-up, seasonal), traffic splitting
(canary, A/B, blue-green, shadow), geographic distribution analysis,
traffic mirroring impact, request prioritization/queuing, TLS handshake
overhead, CDN offload modelling, origin shield evaluation, WebSocket vs
HTTP traffic mix, API gateway throttling, traffic replay capabilities,
and anomaly detection (DDoS vs organic spike).
"""

from __future__ import annotations

import logging
import math
import random
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)

# Seeded RNG for reproducible simulations.
_rng = random.Random(42)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TrafficPatternKind(str, Enum):
    """Supported traffic pattern shapes."""

    STEADY = "steady"
    BURSTY = "bursty"
    SINUSOIDAL = "sinusoidal"
    SPIKE = "spike"
    RAMP_UP = "ramp_up"
    SEASONAL = "seasonal"


class SplitStrategy(str, Enum):
    """Traffic splitting / deployment strategies."""

    CANARY = "canary"
    AB_TEST = "ab_test"
    BLUE_GREEN = "blue_green"
    SHADOW = "shadow"


class RequestPriority(str, Enum):
    """Priority tiers for request queuing."""

    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"
    BACKGROUND = "background"


class AnomalyVerdict(str, Enum):
    """Classification of a traffic anomaly."""

    ORGANIC_SPIKE = "organic_spike"
    DDOS_VOLUMETRIC = "ddos_volumetric"
    DDOS_SLOWLORIS = "ddos_slowloris"
    BOT_SCRAPING = "bot_scraping"
    NORMAL = "normal"


class ProtocolMix(str, Enum):
    """Connection protocol types for traffic mix analysis."""

    HTTP1 = "http1"
    HTTP2 = "http2"
    HTTP3 = "http3"
    WEBSOCKET = "websocket"
    GRPC = "grpc"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class TrafficShapeSnapshot(BaseModel):
    """A single point-in-time traffic observation."""

    timestamp_offset_s: int = Field(
        default=0, ge=0, description="Seconds from simulation start."
    )
    requests_per_second: float = Field(default=0.0, ge=0.0)
    error_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    latency_ms: float = Field(default=0.0, ge=0.0)


class SplitConfig(BaseModel):
    """Configuration for a traffic split simulation."""

    strategy: SplitStrategy = SplitStrategy.CANARY
    primary_weight: float = Field(
        default=0.9, ge=0.0, le=1.0,
        description="Fraction of traffic routed to the primary target.",
    )
    secondary_weight: float = Field(
        default=0.1, ge=0.0, le=1.0,
        description="Fraction of traffic routed to the secondary target.",
    )
    mirror_copy: bool = Field(
        default=False,
        description="Whether shadow traffic is a full copy (adds load).",
    )


class SplitResult(BaseModel):
    """Outcome of a traffic-split simulation."""

    strategy: SplitStrategy
    primary_rps: float = 0.0
    secondary_rps: float = 0.0
    primary_error_rate: float = 0.0
    secondary_error_rate: float = 0.0
    primary_latency_ms: float = 0.0
    secondary_latency_ms: float = 0.0
    additional_infra_cost_pct: float = Field(
        default=0.0,
        description="Extra infrastructure cost as a percentage of baseline.",
    )
    recommendations: list[str] = Field(default_factory=list)


class GeoRegion(BaseModel):
    """A geographic region with traffic weight."""

    region_name: str = ""
    weight: float = Field(default=0.0, ge=0.0, le=1.0)
    latency_penalty_ms: float = Field(default=0.0, ge=0.0)
    pop_count: int = Field(default=0, ge=0, description="Points of presence.")


class GeoDistributionResult(BaseModel):
    """Result of geographic traffic distribution analysis."""

    regions: list[GeoRegion] = Field(default_factory=list)
    global_avg_latency_ms: float = 0.0
    worst_region: str = ""
    worst_latency_ms: float = 0.0
    cdn_benefit_pct: float = 0.0
    recommendations: list[str] = Field(default_factory=list)


class MirrorImpact(BaseModel):
    """Impact assessment of traffic mirroring."""

    mirror_rps: float = 0.0
    additional_bandwidth_mbps: float = 0.0
    additional_cpu_pct: float = 0.0
    additional_latency_ms: float = 0.0
    storage_cost_factor: float = 1.0
    risk_level: str = "low"
    recommendations: list[str] = Field(default_factory=list)


class PriorityQueueResult(BaseModel):
    """Result of request priority / queuing analysis."""

    priority: RequestPriority
    queue_depth: int = 0
    avg_wait_ms: float = 0.0
    drop_rate: float = 0.0
    throughput_rps: float = 0.0


class PriorityAnalysisResult(BaseModel):
    """Aggregate result for all priority tiers."""

    tiers: list[PriorityQueueResult] = Field(default_factory=list)
    total_throughput_rps: float = 0.0
    total_drop_rate: float = 0.0
    fairness_index: float = Field(default=0.0, ge=0.0, le=1.0)
    recommendations: list[str] = Field(default_factory=list)


class TlsOverheadResult(BaseModel):
    """TLS handshake overhead analysis."""

    handshake_latency_ms: float = 0.0
    session_resumption_rate: float = 0.0
    full_handshake_pct: float = 0.0
    cpu_overhead_pct: float = 0.0
    throughput_reduction_pct: float = 0.0
    recommendations: list[str] = Field(default_factory=list)


class CdnOffloadResult(BaseModel):
    """CDN offload effectiveness modelling result."""

    cache_hit_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    origin_rps: float = 0.0
    cdn_rps: float = 0.0
    bandwidth_savings_pct: float = 0.0
    latency_improvement_ms: float = 0.0
    cost_savings_pct: float = 0.0
    recommendations: list[str] = Field(default_factory=list)


class OriginShieldResult(BaseModel):
    """Origin shield pattern evaluation result."""

    shield_hit_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    origin_load_reduction_pct: float = 0.0
    cache_fill_latency_ms: float = 0.0
    additional_hop_latency_ms: float = 0.0
    effective: bool = False
    recommendations: list[str] = Field(default_factory=list)


class ProtocolMixResult(BaseModel):
    """Analysis of WebSocket / HTTP protocol mix."""

    http_rps: float = 0.0
    websocket_connections: int = 0
    connection_overhead_pct: float = 0.0
    memory_per_ws_conn_kb: float = 64.0
    total_ws_memory_mb: float = 0.0
    mixed_latency_ms: float = 0.0
    recommendations: list[str] = Field(default_factory=list)


class ThrottleConfig(BaseModel):
    """API gateway throttling configuration."""

    rate_limit_rps: float = Field(default=1000.0, ge=0.0)
    burst_size: int = Field(default=100, ge=0)
    window_seconds: float = Field(default=1.0, gt=0.0)
    per_client: bool = False
    num_clients: int = Field(default=100, ge=1)


class ThrottleResult(BaseModel):
    """API gateway throttling analysis result."""

    allowed_rps: float = 0.0
    rejected_rps: float = 0.0
    rejection_rate_pct: float = 0.0
    queue_depth: int = 0
    effective_throughput_rps: float = 0.0
    recommendations: list[str] = Field(default_factory=list)


class ReplayScenario(BaseModel):
    """A traffic replay scenario for testing."""

    name: str = ""
    snapshots: list[TrafficShapeSnapshot] = Field(default_factory=list)
    speed_multiplier: float = Field(default=1.0, gt=0.0)
    scale_factor: float = Field(default=1.0, ge=0.0)


class ReplayResult(BaseModel):
    """Result of a traffic replay scenario."""

    scenario_name: str = ""
    peak_rps: float = 0.0
    avg_rps: float = 0.0
    total_requests: int = 0
    errors: int = 0
    avg_latency_ms: float = 0.0
    bottleneck_components: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class AnomalyDetectionResult(BaseModel):
    """Traffic anomaly detection result."""

    verdict: AnomalyVerdict = AnomalyVerdict.NORMAL
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    anomaly_score: float = Field(default=0.0, ge=0.0, le=100.0)
    baseline_rps: float = 0.0
    observed_rps: float = 0.0
    deviation_factor: float = 0.0
    distinct_sources: int = 0
    recommendations: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# Baseline latency per component type (ms).
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

# Priority weights: higher = more resources allocated.
_PRIORITY_WEIGHT: dict[RequestPriority, float] = {
    RequestPriority.CRITICAL: 5.0,
    RequestPriority.HIGH: 3.0,
    RequestPriority.NORMAL: 1.0,
    RequestPriority.LOW: 0.5,
    RequestPriority.BACKGROUND: 0.2,
}

# Default geo regions if none provided.
_DEFAULT_REGIONS: list[dict[str, object]] = [
    {"region_name": "us-east-1", "weight": 0.35, "latency_penalty_ms": 10.0, "pop_count": 8},
    {"region_name": "eu-west-1", "weight": 0.25, "latency_penalty_ms": 80.0, "pop_count": 6},
    {"region_name": "ap-northeast-1", "weight": 0.20, "latency_penalty_ms": 150.0, "pop_count": 4},
    {"region_name": "sa-east-1", "weight": 0.10, "latency_penalty_ms": 200.0, "pop_count": 2},
    {"region_name": "af-south-1", "weight": 0.10, "latency_penalty_ms": 250.0, "pop_count": 1},
]


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def _effective_max_rps(graph: InfraGraph) -> tuple[float, str]:
    """Return (max_rps, limiting_component_id) for the bottleneck."""
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
    """Estimate latency for a component type under a given load ratio."""
    base = _BASE_LATENCY.get(comp_type, 10.0)
    if load_ratio <= 1.0:
        return base * (1.0 + load_ratio)
    return base * (1.0 + load_ratio * 3.0)


def _error_rate_for_load(load_ratio: float) -> float:
    """Estimate error rate for a given load ratio (0.0 - 1.0+)."""
    if load_ratio < 0.01:
        return 0.0
    if load_ratio <= 0.8:
        return 0.001
    if load_ratio <= 1.0:
        return 0.001 + (load_ratio - 0.8) / 0.2 * 0.049
    excess = load_ratio - 1.0
    return min(0.05 + excess * 0.5, 1.0)


def _generate_pattern_rps(
    kind: TrafficPatternKind,
    t: float,
    peak_rps: float,
    rng: random.Random,
) -> float:
    """Return RPS at normalised time *t* (0.0-1.0) for *kind*."""
    if kind == TrafficPatternKind.STEADY:
        return peak_rps * 0.6

    if kind == TrafficPatternKind.BURSTY:
        # Random bursts between 20-100% of peak.
        burst = ((int(t * 10000) * 2654435761) & 0xFFFFFFFF) / 0xFFFFFFFF
        return peak_rps * (0.2 + 0.8 * burst)

    if kind == TrafficPatternKind.SINUSOIDAL:
        return peak_rps * (0.3 + 0.7 * (0.5 + 0.5 * math.sin(2 * math.pi * t)))

    if kind == TrafficPatternKind.SPIKE:
        # Sharp Gaussian spike centred at t=0.5
        return peak_rps * (0.1 + 0.9 * math.exp(-((t - 0.5) ** 2) / 0.01))

    if kind == TrafficPatternKind.RAMP_UP:
        return peak_rps * (0.1 + 0.9 * t)

    if kind == TrafficPatternKind.SEASONAL:
        return peak_rps * (0.2 + 0.8 * math.sin(math.pi * t))

    return peak_rps * 0.5


def _detect_bottlenecks(graph: InfraGraph, rps: float) -> list[str]:
    """Return component IDs that are bottlenecks at the given RPS."""
    bottlenecks: list[str] = []
    for comp in graph.components.values():
        effective_max = comp.capacity.max_rps * comp.replicas
        if comp.autoscaling.enabled:
            effective_max = comp.capacity.max_rps * comp.autoscaling.max_replicas
        if effective_max > 0 and rps / effective_max > 0.8:
            bottlenecks.append(comp.id)
    return sorted(bottlenecks)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class TrafficShapingSimulator:
    """Stateless engine for traffic shaping simulations.

    Provides methods covering traffic pattern generation, splitting
    strategies, geographic analysis, mirroring impact, prioritization,
    TLS overhead, CDN offload, origin shield, protocol mix, API gateway
    throttling, traffic replay, and anomaly detection.
    """

    def __init__(self, seed: int = 42) -> None:
        self._rng = random.Random(seed)
        self._created_at = datetime.now(timezone.utc)

    # -- traffic pattern generation -----------------------------------------

    def generate_pattern(
        self,
        kind: TrafficPatternKind,
        duration_seconds: int = 300,
        peak_rps: float = 1000.0,
        interval_seconds: int = 10,
    ) -> list[TrafficShapeSnapshot]:
        """Generate traffic snapshots for the given pattern kind.

        One :class:`TrafficShapeSnapshot` is emitted every
        *interval_seconds* over *duration_seconds*.
        """
        if duration_seconds <= 0 or interval_seconds <= 0:
            return []

        count = max(1, duration_seconds // interval_seconds)
        snapshots: list[TrafficShapeSnapshot] = []

        for i in range(count):
            t = i / max(count - 1, 1)
            rps = _generate_pattern_rps(kind, t, peak_rps, self._rng)
            err = _error_rate_for_load(rps / max(peak_rps, 1.0))
            lat = _BASE_LATENCY.get("app_server", 15.0) * (1.0 + rps / max(peak_rps, 1.0))

            snapshots.append(
                TrafficShapeSnapshot(
                    timestamp_offset_s=i * interval_seconds,
                    requests_per_second=round(rps, 2),
                    error_rate=round(err, 4),
                    latency_ms=round(lat, 2),
                )
            )

        return snapshots

    # -- traffic splitting --------------------------------------------------

    def simulate_split(
        self,
        graph: InfraGraph,
        total_rps: float,
        config: SplitConfig,
    ) -> SplitResult:
        """Simulate a traffic split between primary and secondary targets."""
        max_rps, limiting = _effective_max_rps(graph)
        if max_rps <= 0:
            max_rps = 1.0

        primary_rps = total_rps * config.primary_weight
        secondary_rps = total_rps * config.secondary_weight

        # Shadow strategy: secondary is a copy, not split.
        extra_cost = 0.0
        if config.strategy == SplitStrategy.SHADOW:
            if config.mirror_copy:
                extra_cost = config.secondary_weight * 100.0
            else:
                extra_cost = config.secondary_weight * 50.0

        # Blue-green keeps both stacks running full capacity.
        if config.strategy == SplitStrategy.BLUE_GREEN:
            extra_cost = 100.0  # duplicate infra

        # Canary has minimal overhead.
        if config.strategy == SplitStrategy.CANARY:
            extra_cost = config.secondary_weight * 100.0

        # AB test: two variants proportional.
        if config.strategy == SplitStrategy.AB_TEST:
            extra_cost = 0.0  # same infra, different code paths

        primary_load = primary_rps / max_rps
        secondary_load = secondary_rps / max_rps

        primary_err = _error_rate_for_load(primary_load)
        secondary_err = _error_rate_for_load(secondary_load)

        primary_lat = sum(
            _component_latency(c.type.value, primary_load)
            for c in graph.components.values()
        )
        secondary_lat = sum(
            _component_latency(c.type.value, secondary_load)
            for c in graph.components.values()
        )

        recs: list[str] = []
        if config.strategy == SplitStrategy.CANARY and config.secondary_weight > 0.2:
            recs.append(
                "Canary weight exceeds 20%; keep it below 10% for safe rollouts."
            )
        if config.strategy == SplitStrategy.SHADOW and config.mirror_copy:
            recs.append(
                "Shadow mode with full mirror doubles infrastructure load."
            )
        if config.strategy == SplitStrategy.BLUE_GREEN:
            recs.append(
                "Blue-green requires 2x infrastructure; plan capacity accordingly."
            )
        if primary_err > 0.05 or secondary_err > 0.05:
            recs.append(
                "Error rate exceeds 5% in at least one target; scale up capacity."
            )
        if not recs:
            recs.append("Traffic split configuration is healthy.")

        return SplitResult(
            strategy=config.strategy,
            primary_rps=round(primary_rps, 2),
            secondary_rps=round(secondary_rps, 2),
            primary_error_rate=round(primary_err, 4),
            secondary_error_rate=round(secondary_err, 4),
            primary_latency_ms=round(primary_lat, 2),
            secondary_latency_ms=round(secondary_lat, 2),
            additional_infra_cost_pct=round(extra_cost, 2),
            recommendations=recs,
        )

    # -- geographic distribution --------------------------------------------

    def analyse_geo_distribution(
        self,
        graph: InfraGraph,
        total_rps: float,
        regions: list[GeoRegion] | None = None,
    ) -> GeoDistributionResult:
        """Analyse traffic distribution across geographic regions."""
        if regions is None:
            regions = [GeoRegion(**r) for r in _DEFAULT_REGIONS]

        if not regions:
            return GeoDistributionResult(
                recommendations=["No regions provided for analysis."],
            )

        max_rps, _ = _effective_max_rps(graph)
        if max_rps <= 0:
            max_rps = 1.0

        weighted_latencies: list[float] = []
        worst_region = ""
        worst_latency = 0.0

        for region in regions:
            region_rps = total_rps * region.weight
            load_ratio = region_rps / max_rps
            base_lat = sum(
                _component_latency(c.type.value, load_ratio)
                for c in graph.components.values()
            ) if graph.components else 10.0
            total_lat = base_lat + region.latency_penalty_ms
            weighted_latencies.append(total_lat * region.weight)

            if total_lat > worst_latency:
                worst_latency = total_lat
                worst_region = region.region_name

        global_avg = sum(weighted_latencies) if weighted_latencies else 0.0

        # CDN benefit: reduces cross-region latency by ~60%.
        cdn_benefit = 0.0
        if regions:
            avg_penalty = sum(r.latency_penalty_ms * r.weight for r in regions)
            cdn_benefit = min(60.0, avg_penalty / max(worst_latency, 1.0) * 100.0)

        recs: list[str] = []
        if worst_latency > 200.0:
            recs.append(
                f"Region '{worst_region}' has high latency ({worst_latency:.0f}ms); "
                "deploy a regional edge or CDN PoP."
            )
        low_pop = [r for r in regions if r.pop_count < 2 and r.weight > 0.05]
        if low_pop:
            names = ", ".join(r.region_name for r in low_pop)
            recs.append(
                f"Regions [{names}] have few PoPs for their traffic share; "
                "add edge locations."
            )
        if not recs:
            recs.append("Geographic distribution is well-balanced.")

        return GeoDistributionResult(
            regions=regions,
            global_avg_latency_ms=round(global_avg, 2),
            worst_region=worst_region,
            worst_latency_ms=round(worst_latency, 2),
            cdn_benefit_pct=round(cdn_benefit, 2),
            recommendations=recs,
        )

    # -- traffic mirroring impact -------------------------------------------

    def assess_mirror_impact(
        self,
        graph: InfraGraph,
        baseline_rps: float,
        mirror_fraction: float = 1.0,
    ) -> MirrorImpact:
        """Assess the impact of mirroring a fraction of production traffic."""
        mirror_fraction = _clamp(mirror_fraction, 0.0, 1.0)
        mirror_rps = baseline_rps * mirror_fraction

        # Bandwidth: ~2 KB per request average.
        bw_mbps = mirror_rps * 2.0 / 1024.0

        # CPU overhead: roughly proportional to mirrored traffic.
        max_rps, _ = _effective_max_rps(graph)
        if max_rps <= 0:
            max_rps = 1.0
        cpu_pct = (mirror_rps / max_rps) * 100.0 * 0.3  # mirroring is lighter

        # Additional latency from serialising mirrored requests.
        add_latency = 0.5 if mirror_fraction > 0 else 0.0

        # Storage cost: mirrored request logs.
        storage_factor = 1.0 + mirror_fraction * 0.5

        risk = "low"
        if cpu_pct > 30.0:
            risk = "high"
        elif cpu_pct > 15.0:
            risk = "medium"

        recs: list[str] = []
        if risk == "high":
            recs.append(
                "Mirror traffic imposes significant CPU load; use async "
                "mirroring or sample a subset."
            )
        if bw_mbps > 100.0:
            recs.append(
                f"Mirror bandwidth is {bw_mbps:.0f} Mbps; ensure network "
                "capacity can absorb the extra traffic."
            )
        if not recs:
            recs.append("Traffic mirroring overhead is acceptable.")

        return MirrorImpact(
            mirror_rps=round(mirror_rps, 2),
            additional_bandwidth_mbps=round(bw_mbps, 2),
            additional_cpu_pct=round(_clamp(cpu_pct), 2),
            additional_latency_ms=round(add_latency, 2),
            storage_cost_factor=round(storage_factor, 2),
            risk_level=risk,
            recommendations=recs,
        )

    # -- request prioritization / queuing -----------------------------------

    def analyse_priority_queuing(
        self,
        graph: InfraGraph,
        total_rps: float,
        priority_distribution: dict[RequestPriority, float] | None = None,
    ) -> PriorityAnalysisResult:
        """Analyse request priority queuing effectiveness.

        *priority_distribution* maps each priority to its fraction of total
        traffic (must sum to 1.0 or less).
        """
        if priority_distribution is None:
            priority_distribution = {
                RequestPriority.CRITICAL: 0.05,
                RequestPriority.HIGH: 0.15,
                RequestPriority.NORMAL: 0.50,
                RequestPriority.LOW: 0.20,
                RequestPriority.BACKGROUND: 0.10,
            }

        max_rps, _ = _effective_max_rps(graph)
        if max_rps <= 0:
            max_rps = 1.0

        tiers: list[PriorityQueueResult] = []
        total_throughput = 0.0
        total_dropped = 0

        total_weight = sum(
            _PRIORITY_WEIGHT[p] * priority_distribution.get(p, 0.0)
            for p in RequestPriority
        )
        if total_weight <= 0:
            total_weight = 1.0

        for priority in RequestPriority:
            frac = priority_distribution.get(priority, 0.0)
            tier_rps = total_rps * frac
            weight = _PRIORITY_WEIGHT[priority]

            # Allocated capacity proportional to priority weight.
            allocated = max_rps * (weight * frac / total_weight)

            load_ratio = tier_rps / max(allocated, 1.0)
            drop_rate = max(0.0, 1.0 - 1.0 / max(load_ratio, 0.01)) if load_ratio > 1.0 else 0.0

            queue_depth = max(0, int(tier_rps - allocated)) if tier_rps > allocated else 0
            wait_ms = queue_depth * 0.5  # 0.5ms per queued request

            throughput = min(tier_rps, allocated)
            total_throughput += throughput
            total_dropped += int(tier_rps * drop_rate)

            tiers.append(
                PriorityQueueResult(
                    priority=priority,
                    queue_depth=queue_depth,
                    avg_wait_ms=round(wait_ms, 2),
                    drop_rate=round(_clamp(drop_rate, 0.0, 1.0), 4),
                    throughput_rps=round(throughput, 2),
                )
            )

        total_requests = int(total_rps)
        overall_drop = total_dropped / max(total_requests, 1)

        # Jain's fairness index on throughput ratios.
        throughputs = [t.throughput_rps for t in tiers if t.throughput_rps > 0]
        if len(throughputs) >= 2:
            s = sum(throughputs)
            s2 = sum(x ** 2 for x in throughputs)
            n = len(throughputs)
            fairness = (s ** 2) / (n * s2) if s2 > 0 else 0.0
        else:
            fairness = 1.0

        recs: list[str] = []
        critical_tier = next((t for t in tiers if t.priority == RequestPriority.CRITICAL), None)
        if critical_tier and critical_tier.drop_rate > 0:
            recs.append(
                "Critical requests are being dropped; increase capacity or "
                "reduce lower-priority traffic."
            )
        if overall_drop > 0.1:
            recs.append(
                f"Overall drop rate is {overall_drop*100:.1f}%; scale up "
                "infrastructure or implement load shedding."
            )
        bg_tier = next((t for t in tiers if t.priority == RequestPriority.BACKGROUND), None)
        if bg_tier and bg_tier.queue_depth > 100:
            recs.append(
                "Background queue is deep; consider off-peak scheduling."
            )
        if not recs:
            recs.append("Priority queuing is well-configured.")

        return PriorityAnalysisResult(
            tiers=tiers,
            total_throughput_rps=round(total_throughput, 2),
            total_drop_rate=round(_clamp(overall_drop, 0.0, 1.0), 4),
            fairness_index=round(_clamp(fairness, 0.0, 1.0), 4),
            recommendations=recs,
        )

    # -- TLS handshake overhead ---------------------------------------------

    def analyse_tls_overhead(
        self,
        graph: InfraGraph,
        total_rps: float,
        new_connection_rate: float = 0.3,
        session_resumption_rate: float = 0.7,
    ) -> TlsOverheadResult:
        """Analyse TLS handshake overhead on throughput and latency.

        *new_connection_rate* is the fraction of requests that require a
        full TLS handshake (the rest use session resumption or keep-alive).
        """
        new_connection_rate = _clamp(new_connection_rate, 0.0, 1.0)
        session_resumption_rate = _clamp(session_resumption_rate, 0.0, 1.0)

        # Full handshake: ~30ms, resumed: ~5ms.
        full_hs_ms = 30.0
        resume_ms = 5.0
        full_frac = new_connection_rate * (1.0 - session_resumption_rate)
        resume_frac = new_connection_rate * session_resumption_rate

        avg_hs_latency = full_frac * full_hs_ms + resume_frac * resume_ms

        # CPU overhead: RSA/ECDHE operations per handshake.
        max_rps, _ = _effective_max_rps(graph)
        if max_rps <= 0:
            max_rps = 1.0
        handshakes_per_sec = total_rps * new_connection_rate
        cpu_overhead = (handshakes_per_sec / max_rps) * 15.0  # ~15% at full capacity

        # Throughput reduction from handshake latency eating into connection time.
        throughput_reduction = min(20.0, avg_hs_latency / 5.0)

        recs: list[str] = []
        if full_frac > 0.2:
            recs.append(
                "High full-handshake rate; enable TLS session tickets or "
                "0-RTT resumption."
            )
        if cpu_overhead > 10.0:
            recs.append(
                "TLS handshakes consume significant CPU; consider hardware "
                "acceleration or ECDHE-only cipher suites."
            )
        if throughput_reduction > 10.0:
            recs.append(
                "TLS overhead reduces throughput noticeably; use HTTP/2 "
                "multiplexing to reduce new connections."
            )
        if not recs:
            recs.append("TLS configuration is efficient.")

        return TlsOverheadResult(
            handshake_latency_ms=round(avg_hs_latency, 2),
            session_resumption_rate=round(session_resumption_rate, 4),
            full_handshake_pct=round(full_frac * 100.0, 2),
            cpu_overhead_pct=round(_clamp(cpu_overhead), 2),
            throughput_reduction_pct=round(_clamp(throughput_reduction), 2),
            recommendations=recs,
        )

    # -- CDN offload --------------------------------------------------------

    def model_cdn_offload(
        self,
        graph: InfraGraph,
        total_rps: float,
        cacheable_fraction: float = 0.6,
        cache_hit_ratio: float = 0.85,
    ) -> CdnOffloadResult:
        """Model CDN offload effectiveness for the given traffic.

        *cacheable_fraction* is the share of requests eligible for caching.
        *cache_hit_ratio* is the hit ratio for cacheable requests at the CDN.
        """
        cacheable_fraction = _clamp(cacheable_fraction, 0.0, 1.0)
        cache_hit_ratio = _clamp(cache_hit_ratio, 0.0, 1.0)

        effective_hit = cacheable_fraction * cache_hit_ratio
        cdn_rps = total_rps * effective_hit
        origin_rps = total_rps - cdn_rps

        # Bandwidth savings: CDN-served requests don't hit origin.
        bw_savings = effective_hit * 100.0

        # Latency improvement: CDN edge is ~5ms; origin path ~50ms.
        cdn_lat = 5.0
        origin_lat = 50.0
        avg_before = origin_lat
        avg_after = effective_hit * cdn_lat + (1.0 - effective_hit) * origin_lat
        lat_improvement = avg_before - avg_after

        # Cost savings: reduced origin compute and bandwidth.
        cost_savings = effective_hit * 70.0  # up to 70% savings

        recs: list[str] = []
        if effective_hit < 0.3:
            recs.append(
                "CDN hit ratio is low; review cache-control headers and "
                "cacheable content types."
            )
        if cacheable_fraction < 0.4:
            recs.append(
                "Less than 40% of traffic is cacheable; consider query "
                "parameter normalisation and edge-side caching."
            )
        if origin_rps > 0:
            max_rps, limiting = _effective_max_rps(graph)
            if max_rps > 0 and origin_rps / max_rps > 0.8:
                recs.append(
                    f"Origin is near capacity even with CDN ({origin_rps:.0f} RPS); "
                    "scale origin or improve cache hit ratio."
                )
        if not recs:
            recs.append("CDN offload is effective.")

        return CdnOffloadResult(
            cache_hit_ratio=round(effective_hit, 4),
            origin_rps=round(origin_rps, 2),
            cdn_rps=round(cdn_rps, 2),
            bandwidth_savings_pct=round(_clamp(bw_savings), 2),
            latency_improvement_ms=round(max(0.0, lat_improvement), 2),
            cost_savings_pct=round(_clamp(cost_savings), 2),
            recommendations=recs,
        )

    # -- origin shield ------------------------------------------------------

    def evaluate_origin_shield(
        self,
        graph: InfraGraph,
        total_rps: float,
        num_edge_pops: int = 10,
        shield_hit_ratio: float = 0.7,
    ) -> OriginShieldResult:
        """Evaluate origin shield pattern effectiveness.

        An origin shield collapses cache-fill requests from many edge PoPs
        into a single shield node, reducing origin load.
        """
        shield_hit_ratio = _clamp(shield_hit_ratio, 0.0, 1.0)
        num_edge_pops = max(1, num_edge_pops)

        # Without shield: each PoP sends cache misses independently.
        # With shield: one shield absorbs misses from all PoPs.
        without_shield_origin_rps = total_rps * 0.15 * num_edge_pops  # 15% miss per PoP
        with_shield_origin_rps = total_rps * 0.15 * (1.0 - shield_hit_ratio)

        load_reduction = 0.0
        if without_shield_origin_rps > 0:
            load_reduction = (
                (without_shield_origin_rps - with_shield_origin_rps)
                / without_shield_origin_rps
            ) * 100.0

        # Extra hop from edge to shield adds ~10ms.
        extra_hop_ms = 10.0
        # Cache fill via shield: shield-to-origin adds latency only on miss.
        cache_fill_lat = extra_hop_ms + 50.0 * (1.0 - shield_hit_ratio)

        effective = load_reduction > 30.0

        recs: list[str] = []
        if not effective:
            recs.append(
                "Origin shield provides limited benefit; ensure shield cache "
                "is properly configured and sized."
            )
        if shield_hit_ratio < 0.5:
            recs.append(
                "Shield hit ratio is below 50%; increase cache TTLs or "
                "pre-warm the shield cache."
            )
        if num_edge_pops < 3:
            recs.append(
                "Few edge PoPs reduce origin shield benefit; consider "
                "direct cache optimization instead."
            )
        if not recs:
            recs.append("Origin shield pattern is effective for this topology.")

        return OriginShieldResult(
            shield_hit_ratio=round(shield_hit_ratio, 4),
            origin_load_reduction_pct=round(_clamp(load_reduction), 2),
            cache_fill_latency_ms=round(cache_fill_lat, 2),
            additional_hop_latency_ms=round(extra_hop_ms, 2),
            effective=effective,
            recommendations=recs,
        )

    # -- WebSocket / HTTP protocol mix --------------------------------------

    def analyse_protocol_mix(
        self,
        graph: InfraGraph,
        http_rps: float = 1000.0,
        websocket_connections: int = 500,
        memory_per_ws_kb: float = 64.0,
    ) -> ProtocolMixResult:
        """Analyse mixed HTTP + WebSocket traffic impact on resources."""
        max_rps, _ = _effective_max_rps(graph)
        if max_rps <= 0:
            max_rps = 1.0

        # WebSocket connections are long-lived and consume memory.
        ws_memory_mb = websocket_connections * memory_per_ws_kb / 1024.0

        # Connection overhead: each WS consumes file descriptors and CPU.
        total_connections_equiv = http_rps * 0.01 + websocket_connections
        max_connections = 0
        for c in graph.components.values():
            max_connections = max(max_connections, c.capacity.max_connections * c.replicas)
        if max_connections <= 0:
            max_connections = 10000

        conn_overhead = (total_connections_equiv / max_connections) * 100.0

        # Mixed latency: HTTP requests affected by WS connection pool.
        base_lat = sum(
            _component_latency(c.type.value, http_rps / max_rps)
            for c in graph.components.values()
        ) if graph.components else 15.0
        ws_contention = min(10.0, websocket_connections / 1000.0 * 5.0)
        mixed_lat = base_lat + ws_contention

        recs: list[str] = []
        if conn_overhead > 70.0:
            recs.append(
                "Connection overhead is high; consider separate WebSocket "
                "and HTTP worker pools."
            )
        if ws_memory_mb > 512.0:
            recs.append(
                f"WebSocket connections consume {ws_memory_mb:.0f} MB; "
                "implement connection limits or idle timeouts."
            )
        if websocket_connections > 0 and http_rps > max_rps * 0.7:
            recs.append(
                "HTTP traffic is near capacity alongside active WebSocket "
                "connections; scale horizontally."
            )
        if not recs:
            recs.append("Protocol mix is within acceptable resource bounds.")

        return ProtocolMixResult(
            http_rps=round(http_rps, 2),
            websocket_connections=websocket_connections,
            connection_overhead_pct=round(_clamp(conn_overhead), 2),
            memory_per_ws_conn_kb=memory_per_ws_kb,
            total_ws_memory_mb=round(ws_memory_mb, 2),
            mixed_latency_ms=round(mixed_lat, 2),
            recommendations=recs,
        )

    # -- API gateway throttling ---------------------------------------------

    def simulate_gateway_throttle(
        self,
        graph: InfraGraph,
        incoming_rps: float,
        config: ThrottleConfig,
    ) -> ThrottleResult:
        """Simulate API gateway throttling for the given configuration."""
        effective_limit = config.rate_limit_rps
        if config.per_client:
            effective_limit = config.rate_limit_rps * config.num_clients

        burst_capacity = effective_limit + config.burst_size / max(config.window_seconds, 0.01)

        if incoming_rps <= burst_capacity:
            rejected = 0.0
            allowed = incoming_rps
        else:
            rejected = incoming_rps - burst_capacity
            allowed = burst_capacity

        rejection_rate = (rejected / max(incoming_rps, 1.0)) * 100.0
        queue_depth = max(0, int(rejected * 0.3))  # 30% of rejected get queued

        # Effective throughput includes queued requests that drain.
        effective = allowed + queue_depth * 0.5

        recs: list[str] = []
        if rejection_rate > 20.0:
            recs.append(
                f"Rejection rate is {rejection_rate:.0f}%; increase rate limit "
                "or add burst capacity."
            )
        if config.per_client and config.num_clients > 1000:
            recs.append(
                "Per-client limits with many clients require distributed "
                "rate-limit storage (e.g., Redis)."
            )
        if config.burst_size < 10:
            recs.append(
                "Burst size is very small; increase to absorb transient spikes."
            )
        max_rps, _ = _effective_max_rps(graph)
        if max_rps > 0 and effective / max_rps > 0.9:
            recs.append(
                "Effective throughput approaches infrastructure capacity; "
                "scale upstream."
            )
        if not recs:
            recs.append("API gateway throttle configuration is adequate.")

        return ThrottleResult(
            allowed_rps=round(allowed, 2),
            rejected_rps=round(rejected, 2),
            rejection_rate_pct=round(_clamp(rejection_rate), 2),
            queue_depth=queue_depth,
            effective_throughput_rps=round(effective, 2),
            recommendations=recs,
        )

    # -- traffic replay capabilities ----------------------------------------

    def replay_traffic(
        self,
        graph: InfraGraph,
        scenario: ReplayScenario,
    ) -> ReplayResult:
        """Replay a traffic scenario against the infrastructure graph."""
        if not scenario.snapshots:
            return ReplayResult(
                scenario_name=scenario.name,
                recommendations=["No snapshots provided for replay."],
            )

        max_rps, _ = _effective_max_rps(graph)
        if max_rps <= 0:
            max_rps = 1.0

        peak = 0.0
        total_rps_sum = 0.0
        total_requests = 0
        errors = 0
        latencies: list[float] = []
        all_bottlenecks: set[str] = set()

        for snap in scenario.snapshots:
            rps = snap.requests_per_second * scenario.scale_factor
            if rps > peak:
                peak = rps
            total_rps_sum += rps

            interval = max(1, int(10 / scenario.speed_multiplier))
            interval_requests = int(rps * interval)
            total_requests += interval_requests

            load_ratio = rps / max_rps
            err = _error_rate_for_load(load_ratio)
            errors += int(interval_requests * err)

            lat = sum(
                _component_latency(c.type.value, load_ratio)
                for c in graph.components.values()
            ) if graph.components else 15.0
            latencies.append(lat)

            bns = _detect_bottlenecks(graph, rps)
            all_bottlenecks.update(bns)

        avg_rps = total_rps_sum / len(scenario.snapshots)
        avg_lat = sum(latencies) / len(latencies) if latencies else 0.0

        recs: list[str] = []
        if all_bottlenecks:
            recs.append(
                f"Bottleneck components: {', '.join(sorted(all_bottlenecks))}."
            )
        error_rate = errors / max(total_requests, 1)
        if error_rate > 0.05:
            recs.append(
                "Error rate during replay exceeds 5%; review capacity for "
                "the replayed traffic pattern."
            )
        if not recs:
            recs.append("Replay completed within acceptable parameters.")

        return ReplayResult(
            scenario_name=scenario.name,
            peak_rps=round(peak, 2),
            avg_rps=round(avg_rps, 2),
            total_requests=total_requests,
            errors=errors,
            avg_latency_ms=round(avg_lat, 2),
            bottleneck_components=sorted(all_bottlenecks),
            recommendations=recs,
        )

    # -- traffic anomaly detection ------------------------------------------

    def detect_anomaly(
        self,
        baseline_rps: float,
        observed_rps: float,
        distinct_sources: int = 100,
        request_entropy: float = 0.8,
    ) -> AnomalyDetectionResult:
        """Detect whether observed traffic is an anomaly.

        Uses heuristics based on deviation from baseline, source diversity,
        and request pattern entropy to classify traffic.

        *request_entropy* is 0.0 (all requests identical) to 1.0 (fully
        diverse).  Organic spikes tend to have high entropy; attacks tend
        to have low entropy.
        """
        request_entropy = _clamp(request_entropy, 0.0, 1.0)
        if baseline_rps <= 0:
            baseline_rps = 1.0

        deviation = observed_rps / baseline_rps

        if deviation <= 1.5:
            return AnomalyDetectionResult(
                verdict=AnomalyVerdict.NORMAL,
                confidence=0.9,
                anomaly_score=round(deviation * 10.0, 2),
                baseline_rps=round(baseline_rps, 2),
                observed_rps=round(observed_rps, 2),
                deviation_factor=round(deviation, 2),
                distinct_sources=distinct_sources,
                recommendations=["Traffic is within normal range."],
            )

        # High deviation: classify based on patterns.
        score = min(100.0, deviation * 15.0)

        # Low entropy + few sources = attack.
        # High entropy + many sources = organic spike.
        if request_entropy < 0.3 and distinct_sources < 20:
            if deviation > 10.0:
                verdict = AnomalyVerdict.DDOS_VOLUMETRIC
                confidence = min(0.95, 0.6 + (1.0 - request_entropy) * 0.3)
            else:
                verdict = AnomalyVerdict.BOT_SCRAPING
                confidence = 0.7
        elif request_entropy < 0.4 and deviation > 5.0:
            verdict = AnomalyVerdict.DDOS_SLOWLORIS
            confidence = 0.75
        elif request_entropy > 0.6 and distinct_sources > 50:
            verdict = AnomalyVerdict.ORGANIC_SPIKE
            confidence = min(0.9, 0.5 + request_entropy * 0.4)
        else:
            # Ambiguous: moderate entropy, moderate sources.
            if deviation > 8.0:
                verdict = AnomalyVerdict.DDOS_VOLUMETRIC
                confidence = 0.55
            else:
                verdict = AnomalyVerdict.ORGANIC_SPIKE
                confidence = 0.5

        recs: list[str] = []
        if verdict in (AnomalyVerdict.DDOS_VOLUMETRIC, AnomalyVerdict.DDOS_SLOWLORIS):
            recs.append(
                "Potential DDoS detected; activate WAF rules and rate limiting."
            )
            recs.append(
                "Enable upstream scrubbing (e.g. CloudFlare, AWS Shield) for "
                "volumetric attacks."
            )
        elif verdict == AnomalyVerdict.BOT_SCRAPING:
            recs.append(
                "Bot scraping detected; implement CAPTCHA or bot detection."
            )
        elif verdict == AnomalyVerdict.ORGANIC_SPIKE:
            recs.append(
                "Organic traffic spike; ensure autoscaling is enabled and "
                "CDN caching is active."
            )
        if deviation > 5.0:
            recs.append(
                f"Traffic is {deviation:.1f}x baseline; activate emergency "
                "capacity plans."
            )

        return AnomalyDetectionResult(
            verdict=verdict,
            confidence=round(_clamp(confidence, 0.0, 1.0), 4),
            anomaly_score=round(_clamp(score), 2),
            baseline_rps=round(baseline_rps, 2),
            observed_rps=round(observed_rps, 2),
            deviation_factor=round(deviation, 2),
            distinct_sources=distinct_sources,
            recommendations=recs,
        )
