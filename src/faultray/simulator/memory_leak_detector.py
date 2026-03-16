"""Memory Leak Detector.

Analyzes memory leak patterns and their infrastructure impact.
Features include memory growth rate modeling, time-to-OOM estimation,
cascade analysis (one service OOM triggers failures in others),
GC pressure scoring, memory fragmentation risk assessment,
memory pool exhaustion modeling, container memory limit vs actual usage,
statistical anomaly scoring for leak detection, heap vs off-heap split
analysis, remediation priority scoring, autoscaling impact analysis
(memory-based HPA triggers), and historical memory trend extrapolation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Sequence

from faultray.model.components import Component, ComponentType, Dependency
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class LeakSeverity(str, Enum):
    """Severity classification for memory leaks."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"


class MemoryRegion(str, Enum):
    """Memory region classification."""

    HEAP = "heap"
    OFF_HEAP = "off_heap"
    STACK = "stack"
    MMAP = "mmap"
    SHARED = "shared"


class GCAlgorithm(str, Enum):
    """Garbage collection algorithm types."""

    G1 = "g1"
    ZGC = "zgc"
    SHENANDOAH = "shenandoah"
    CMS = "cms"
    SERIAL = "serial"
    PARALLEL = "parallel"
    NO_GC = "no_gc"


class FragmentationLevel(str, Enum):
    """Memory fragmentation severity."""

    SEVERE = "severe"
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"
    MINIMAL = "minimal"


class RemediationAction(str, Enum):
    """Recommended remediation actions."""

    RESTART_SERVICE = "restart_service"
    INCREASE_MEMORY_LIMIT = "increase_memory_limit"
    FIX_CODE_LEAK = "fix_code_leak"
    TUNE_GC = "tune_gc"
    ADD_REPLICAS = "add_replicas"
    ENABLE_AUTOSCALING = "enable_autoscaling"
    REDUCE_CACHE_SIZE = "reduce_cache_size"
    OPTIMIZE_ALLOCATION = "optimize_allocation"


class TrendDirection(str, Enum):
    """Direction of memory usage trend."""

    INCREASING = "increasing"
    STABLE = "stable"
    DECREASING = "decreasing"
    VOLATILE = "volatile"


# ---------------------------------------------------------------------------
# Constants / lookup tables
# ---------------------------------------------------------------------------

# GC pause characteristics: (avg_pause_ms, pause_frequency_factor)
_GC_CHARACTERISTICS: dict[GCAlgorithm, tuple[float, float]] = {
    GCAlgorithm.G1: (10.0, 1.0),
    GCAlgorithm.ZGC: (1.0, 0.5),
    GCAlgorithm.SHENANDOAH: (1.5, 0.6),
    GCAlgorithm.CMS: (20.0, 1.2),
    GCAlgorithm.SERIAL: (100.0, 0.3),
    GCAlgorithm.PARALLEL: (50.0, 0.8),
    GCAlgorithm.NO_GC: (0.0, 0.0),
}

# Weight for leak severity scoring
_SEVERITY_WEIGHT: dict[LeakSeverity, float] = {
    LeakSeverity.CRITICAL: 1.0,
    LeakSeverity.HIGH: 0.75,
    LeakSeverity.MEDIUM: 0.5,
    LeakSeverity.LOW: 0.25,
    LeakSeverity.NONE: 0.0,
}

# Fragmentation risk multipliers per memory region
_REGION_FRAGMENTATION_RISK: dict[MemoryRegion, float] = {
    MemoryRegion.HEAP: 0.6,
    MemoryRegion.OFF_HEAP: 0.8,
    MemoryRegion.STACK: 0.1,
    MemoryRegion.MMAP: 0.4,
    MemoryRegion.SHARED: 0.5,
}

# Remediation effectiveness scores (0-1)
_REMEDIATION_EFFECTIVENESS: dict[RemediationAction, float] = {
    RemediationAction.RESTART_SERVICE: 0.9,
    RemediationAction.INCREASE_MEMORY_LIMIT: 0.5,
    RemediationAction.FIX_CODE_LEAK: 1.0,
    RemediationAction.TUNE_GC: 0.6,
    RemediationAction.ADD_REPLICAS: 0.4,
    RemediationAction.ENABLE_AUTOSCALING: 0.55,
    RemediationAction.REDUCE_CACHE_SIZE: 0.45,
    RemediationAction.OPTIMIZE_ALLOCATION: 0.7,
}

# Remediation cost/effort scores (0-1, higher = more effort)
_REMEDIATION_EFFORT: dict[RemediationAction, float] = {
    RemediationAction.RESTART_SERVICE: 0.1,
    RemediationAction.INCREASE_MEMORY_LIMIT: 0.2,
    RemediationAction.FIX_CODE_LEAK: 0.9,
    RemediationAction.TUNE_GC: 0.5,
    RemediationAction.ADD_REPLICAS: 0.3,
    RemediationAction.ENABLE_AUTOSCALING: 0.4,
    RemediationAction.REDUCE_CACHE_SIZE: 0.3,
    RemediationAction.OPTIMIZE_ALLOCATION: 0.7,
}

# Container memory limit safety margin
_CONTAINER_SAFETY_MARGIN = 0.85  # Alert at 85% of limit

# OOM kill threshold
_OOM_THRESHOLD = 0.95

# Minimum data points for statistical anomaly detection
_MIN_DATA_POINTS = 3

# Default hours for trend extrapolation
_DEFAULT_EXTRAPOLATION_HOURS = 24


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class MemorySnapshot:
    """A point-in-time memory usage measurement."""

    timestamp_hours: float = 0.0
    used_mb: float = 0.0
    total_mb: float = 0.0
    heap_mb: float = 0.0
    off_heap_mb: float = 0.0
    gc_pause_ms: float = 0.0
    allocation_rate_mb_per_sec: float = 0.0


@dataclass
class GrowthRateResult:
    """Result of memory growth rate analysis."""

    component_id: str = ""
    growth_rate_mb_per_hour: float = 0.0
    baseline_mb: float = 0.0
    current_mb: float = 0.0
    total_mb: float = 0.0
    utilization_percent: float = 0.0
    is_leaking: bool = False
    confidence: float = 0.0
    severity: LeakSeverity = LeakSeverity.NONE
    recommendations: list[str] = field(default_factory=list)


@dataclass
class OOMEstimation:
    """Time-to-OOM estimation result."""

    component_id: str = ""
    time_to_oom_hours: float = float("inf")
    current_usage_mb: float = 0.0
    memory_limit_mb: float = 0.0
    growth_rate_mb_per_hour: float = 0.0
    oom_probability_24h: float = 0.0
    severity: LeakSeverity = LeakSeverity.NONE
    recommendations: list[str] = field(default_factory=list)


@dataclass
class CascadeImpact:
    """Impact of one service OOM on other services."""

    source_component_id: str = ""
    affected_components: list[str] = field(default_factory=list)
    cascade_depth: int = 0
    total_impact_score: float = 0.0
    critical_path: list[str] = field(default_factory=list)
    severity: LeakSeverity = LeakSeverity.NONE
    recommendations: list[str] = field(default_factory=list)


@dataclass
class GCPressureScore:
    """GC pressure analysis result."""

    component_id: str = ""
    gc_algorithm: GCAlgorithm = GCAlgorithm.NO_GC
    pressure_score: float = 0.0
    estimated_pause_ms: float = 0.0
    pause_frequency_per_minute: float = 0.0
    throughput_impact_percent: float = 0.0
    allocation_rate_mb_per_sec: float = 0.0
    severity: LeakSeverity = LeakSeverity.NONE
    recommendations: list[str] = field(default_factory=list)


@dataclass
class FragmentationRisk:
    """Memory fragmentation risk assessment."""

    component_id: str = ""
    fragmentation_level: FragmentationLevel = FragmentationLevel.MINIMAL
    risk_score: float = 0.0
    largest_free_block_mb: float = 0.0
    total_free_mb: float = 0.0
    fragmentation_ratio: float = 0.0
    region_risks: dict[str, float] = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)


@dataclass
class PoolExhaustionResult:
    """Memory pool exhaustion modeling result."""

    component_id: str = ""
    pool_name: str = ""
    current_usage_percent: float = 0.0
    time_to_exhaustion_hours: float = float("inf")
    exhaustion_impact: str = "none"
    allocation_rate_mb_per_hour: float = 0.0
    deallocation_rate_mb_per_hour: float = 0.0
    net_growth_mb_per_hour: float = 0.0
    severity: LeakSeverity = LeakSeverity.NONE
    recommendations: list[str] = field(default_factory=list)


@dataclass
class ContainerMemoryAnalysis:
    """Container memory limit vs actual usage analysis."""

    component_id: str = ""
    container_limit_mb: float = 0.0
    actual_usage_mb: float = 0.0
    usage_ratio: float = 0.0
    headroom_mb: float = 0.0
    oom_kill_risk: str = "low"
    limit_recommendation_mb: float = 0.0
    over_provisioned: bool = False
    under_provisioned: bool = False
    severity: LeakSeverity = LeakSeverity.NONE
    recommendations: list[str] = field(default_factory=list)


@dataclass
class AnomalyScore:
    """Memory leak detection via statistical anomaly scoring."""

    component_id: str = ""
    anomaly_score: float = 0.0
    z_score: float = 0.0
    is_anomalous: bool = False
    mean_usage_mb: float = 0.0
    std_dev_mb: float = 0.0
    current_usage_mb: float = 0.0
    trend_direction: TrendDirection = TrendDirection.STABLE
    severity: LeakSeverity = LeakSeverity.NONE
    recommendations: list[str] = field(default_factory=list)


@dataclass
class HeapOffHeapSplit:
    """Heap vs off-heap memory split analysis."""

    component_id: str = ""
    total_memory_mb: float = 0.0
    heap_mb: float = 0.0
    off_heap_mb: float = 0.0
    heap_ratio: float = 0.0
    off_heap_ratio: float = 0.0
    heap_growth_rate_mb_per_hour: float = 0.0
    off_heap_growth_rate_mb_per_hour: float = 0.0
    leak_region: MemoryRegion = MemoryRegion.HEAP
    balance_score: float = 0.0
    recommendations: list[str] = field(default_factory=list)


@dataclass
class RemediationPriority:
    """Memory leak remediation priority scoring."""

    component_id: str = ""
    priority_score: float = 0.0
    recommended_actions: list[RemediationAction] = field(default_factory=list)
    urgency: LeakSeverity = LeakSeverity.NONE
    estimated_fix_time_hours: float = 0.0
    business_impact_score: float = 0.0
    technical_debt_score: float = 0.0
    recommendations: list[str] = field(default_factory=list)


@dataclass
class AutoscalingImpact:
    """Impact of memory leaks on autoscaling."""

    component_id: str = ""
    hpa_triggered: bool = False
    memory_threshold_percent: float = 0.0
    current_memory_percent: float = 0.0
    time_to_scale_hours: float = float("inf")
    scale_events_predicted_24h: int = 0
    cost_increase_percent: float = 0.0
    scaling_effective: bool = True
    recommendations: list[str] = field(default_factory=list)


@dataclass
class TrendExtrapolation:
    """Historical memory trend extrapolation."""

    component_id: str = ""
    data_points: int = 0
    trend_direction: TrendDirection = TrendDirection.STABLE
    slope_mb_per_hour: float = 0.0
    intercept_mb: float = 0.0
    r_squared: float = 0.0
    predicted_usage_mb: float = 0.0
    prediction_horizon_hours: float = 0.0
    confidence: float = 0.0
    recommendations: list[str] = field(default_factory=list)


@dataclass
class MemoryLeakReport:
    """Comprehensive memory leak analysis report."""

    timestamp: str = ""
    component_count: int = 0
    leaking_components: int = 0
    overall_risk_score: float = 0.0
    growth_rates: list[GrowthRateResult] = field(default_factory=list)
    oom_estimations: list[OOMEstimation] = field(default_factory=list)
    cascade_impacts: list[CascadeImpact] = field(default_factory=list)
    gc_pressures: list[GCPressureScore] = field(default_factory=list)
    fragmentation_risks: list[FragmentationRisk] = field(default_factory=list)
    container_analyses: list[ContainerMemoryAnalysis] = field(default_factory=list)
    anomaly_scores: list[AnomalyScore] = field(default_factory=list)
    remediation_priorities: list[RemediationPriority] = field(default_factory=list)
    autoscaling_impacts: list[AutoscalingImpact] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    """Clamp *value* to [lo, hi]."""
    return max(lo, min(hi, value))


def _classify_severity(score: float) -> LeakSeverity:
    """Classify a 0-100 risk score into a severity level."""
    if score >= 80.0:
        return LeakSeverity.CRITICAL
    if score >= 60.0:
        return LeakSeverity.HIGH
    if score >= 40.0:
        return LeakSeverity.MEDIUM
    if score >= 20.0:
        return LeakSeverity.LOW
    return LeakSeverity.NONE


def _classify_fragmentation(ratio: float) -> FragmentationLevel:
    """Classify a fragmentation ratio (0-1) into a level."""
    if ratio >= 0.8:
        return FragmentationLevel.SEVERE
    if ratio >= 0.6:
        return FragmentationLevel.HIGH
    if ratio >= 0.4:
        return FragmentationLevel.MODERATE
    if ratio >= 0.2:
        return FragmentationLevel.LOW
    return FragmentationLevel.MINIMAL


def _linear_regression(
    xs: Sequence[float], ys: Sequence[float]
) -> tuple[float, float, float]:
    """Simple linear regression returning (slope, intercept, r_squared).

    Returns (0, 0, 0) for fewer than 2 data points.
    """
    n = len(xs)
    if n < 2:
        return 0.0, 0.0, 0.0

    sum_x = sum(xs)
    sum_y = sum(ys)
    sum_xy = sum(x * y for x, y in zip(xs, ys))
    sum_x2 = sum(x * x for x in xs)
    sum_y2 = sum(y * y for y in ys)

    denom = n * sum_x2 - sum_x * sum_x
    if abs(denom) < 1e-12:
        return 0.0, sum_y / n if n > 0 else 0.0, 0.0

    slope = (n * sum_xy - sum_x * sum_y) / denom
    intercept = (sum_y - slope * sum_x) / n

    # R-squared
    ss_tot = sum_y2 - (sum_y * sum_y) / n
    ss_res = sum(
        (y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys)
    )
    r_squared = 1.0 - (ss_res / ss_tot) if abs(ss_tot) > 1e-12 else 0.0
    r_squared = max(0.0, min(1.0, r_squared))

    return slope, intercept, r_squared


def _compute_growth_rate(snapshots: Sequence[MemorySnapshot]) -> float:
    """Compute memory growth rate in MB/hour from snapshots using regression."""
    if len(snapshots) < 2:
        return 0.0

    xs = [s.timestamp_hours for s in snapshots]
    ys = [s.used_mb for s in snapshots]
    slope, _, _ = _linear_regression(xs, ys)
    return slope


def _mean(values: Sequence[float]) -> float:
    """Compute arithmetic mean. Returns 0 for empty sequences."""
    if not values:
        return 0.0
    return sum(values) / len(values)


def _std_dev(values: Sequence[float]) -> float:
    """Compute population standard deviation. Returns 0 for < 2 values."""
    n = len(values)
    if n < 2:
        return 0.0
    m = _mean(values)
    variance = sum((v - m) ** 2 for v in values) / n
    return math.sqrt(variance)


def _z_score(value: float, mean: float, std: float) -> float:
    """Compute z-score. Returns 0 if std is near zero."""
    if abs(std) < 1e-12:
        return 0.0
    return (value - mean) / std


def _estimate_time_to_threshold(
    current: float, limit: float, growth_rate: float
) -> float:
    """Estimate time (hours) until current + growth reaches limit."""
    if growth_rate <= 0.0:
        return float("inf")
    remaining = limit - current
    if remaining <= 0.0:
        return 0.0
    return remaining / growth_rate


def _oom_probability_in_window(
    time_to_oom: float, window_hours: float = 24.0
) -> float:
    """Estimate probability of OOM within a time window.

    Uses a simple model: if time_to_oom <= window, probability is high.
    """
    if time_to_oom <= 0.0:
        return 1.0
    if time_to_oom >= window_hours * 3:
        return 0.0
    # Linear decay: 1.0 at time=0, 0.0 at time=3*window
    return _clamp(1.0 - (time_to_oom / (window_hours * 3)), 0.0, 1.0)


def _gc_pause_estimate(
    algorithm: GCAlgorithm,
    heap_size_mb: float,
    allocation_rate: float,
) -> tuple[float, float]:
    """Estimate GC pause duration (ms) and frequency (pauses/minute).

    Returns (pause_ms, pauses_per_minute).
    """
    base_pause, freq_factor = _GC_CHARACTERISTICS.get(
        algorithm, (0.0, 0.0)
    )
    if base_pause == 0.0:
        return 0.0, 0.0

    # Pause scales with log of heap size
    heap_factor = 1.0 + math.log2(max(1.0, heap_size_mb / 256.0))
    pause_ms = base_pause * heap_factor

    # Frequency scales with allocation rate
    if allocation_rate <= 0.0:
        pauses_per_min = freq_factor * 1.0  # baseline
    else:
        pauses_per_min = freq_factor * (1.0 + math.log2(max(1.0, allocation_rate)))

    return pause_ms, pauses_per_min


def _throughput_impact(pause_ms: float, pauses_per_min: float) -> float:
    """Estimate throughput impact as percentage from GC pauses.

    Total pause time per minute / 60000ms * 100.
    """
    total_pause_per_min = pause_ms * pauses_per_min
    impact = (total_pause_per_min / 60000.0) * 100.0
    return _clamp(impact)


def _cascade_depth_bfs(
    graph: InfraGraph, source_id: str
) -> tuple[list[str], int, list[str]]:
    """BFS to find affected components and max cascade depth.

    Returns (affected_ids, max_depth, critical_path).
    """
    affected: list[str] = []
    visited: set[str] = {source_id}
    queue: list[tuple[str, int, list[str]]] = [(source_id, 0, [source_id])]
    max_depth = 0
    longest_path: list[str] = [source_id]

    while queue:
        current, depth, path = queue.pop(0)
        dependents = graph.get_dependents(current)
        for dep in dependents:
            if dep.id not in visited:
                visited.add(dep.id)
                affected.append(dep.id)
                new_path = path + [dep.id]
                new_depth = depth + 1
                if new_depth > max_depth:
                    max_depth = new_depth
                    longest_path = new_path
                queue.append((dep.id, new_depth, new_path))

    return affected, max_depth, longest_path


def _remediation_priority_score(
    severity: LeakSeverity,
    time_to_oom: float,
    dependents_count: int,
    revenue_per_minute: float,
) -> float:
    """Compute a 0-100 remediation priority score.

    Higher = more urgent.
    """
    severity_factor = _SEVERITY_WEIGHT.get(severity, 0.0) * 40.0

    # Time urgency: closer to OOM = higher priority
    if time_to_oom <= 0.0:
        time_factor = 30.0
    elif time_to_oom < 1.0:
        time_factor = 25.0
    elif time_to_oom < 6.0:
        time_factor = 20.0
    elif time_to_oom < 24.0:
        time_factor = 15.0
    elif time_to_oom < 72.0:
        time_factor = 10.0
    else:
        time_factor = 5.0 if time_to_oom < float("inf") else 0.0

    # Business impact: dependents and revenue
    dep_factor = min(15.0, dependents_count * 3.0)
    rev_factor = min(15.0, math.log2(max(1.0, revenue_per_minute + 1.0)) * 3.0)

    return _clamp(severity_factor + time_factor + dep_factor + rev_factor)


def _select_remediation_actions(
    severity: LeakSeverity,
    time_to_oom: float,
    has_autoscaling: bool,
    gc_algorithm: GCAlgorithm,
) -> list[RemediationAction]:
    """Select recommended remediation actions based on context."""
    actions: list[RemediationAction] = []

    # Immediate actions for critical situations
    if time_to_oom < 1.0:
        actions.append(RemediationAction.RESTART_SERVICE)

    if severity in (LeakSeverity.CRITICAL, LeakSeverity.HIGH):
        actions.append(RemediationAction.FIX_CODE_LEAK)
        if time_to_oom < 24.0:
            actions.append(RemediationAction.INCREASE_MEMORY_LIMIT)

    if gc_algorithm != GCAlgorithm.NO_GC:
        if severity in (LeakSeverity.CRITICAL, LeakSeverity.HIGH, LeakSeverity.MEDIUM):
            actions.append(RemediationAction.TUNE_GC)

    if not has_autoscaling and severity != LeakSeverity.NONE:
        actions.append(RemediationAction.ENABLE_AUTOSCALING)

    if severity in (LeakSeverity.MEDIUM, LeakSeverity.LOW):
        actions.append(RemediationAction.OPTIMIZE_ALLOCATION)
        actions.append(RemediationAction.REDUCE_CACHE_SIZE)

    if severity != LeakSeverity.NONE and RemediationAction.ADD_REPLICAS not in actions:
        actions.append(RemediationAction.ADD_REPLICAS)

    # Deduplicate while preserving order
    seen: set[RemediationAction] = set()
    unique: list[RemediationAction] = []
    for a in actions:
        if a not in seen:
            seen.add(a)
            unique.append(a)

    return unique


def _estimate_fix_time(actions: list[RemediationAction]) -> float:
    """Estimate total fix time in hours for a set of remediation actions."""
    if not actions:
        return 0.0
    # Pick the max effort action as dominating factor, add 20% per additional
    efforts = [_REMEDIATION_EFFORT.get(a, 0.5) for a in actions]
    max_effort = max(efforts)
    # Base: max_effort * 8 hours (workday), +20% per extra action
    base_hours = max_effort * 8.0
    extra = sum(e * 1.6 for e in efforts if e != max_effort)
    return round(base_hours + extra, 1)


# ---------------------------------------------------------------------------
# Main analyzer class
# ---------------------------------------------------------------------------


class MemoryLeakDetector:
    """Analyzes memory leak patterns and their infrastructure impact."""

    def __init__(
        self,
        graph: InfraGraph,
        snapshots: dict[str, list[MemorySnapshot]] | None = None,
        gc_algorithms: dict[str, GCAlgorithm] | None = None,
    ) -> None:
        self._graph = graph
        self._snapshots: dict[str, list[MemorySnapshot]] = snapshots or {}
        self._gc_algorithms: dict[str, GCAlgorithm] = gc_algorithms or {}

    # -- Growth Rate Analysis -------------------------------------------------

    def analyze_growth_rate(self, component_id: str) -> GrowthRateResult:
        """Analyze memory growth rate for a single component."""
        comp = self._graph.get_component(component_id)
        if comp is None:
            return GrowthRateResult(
                component_id=component_id,
                recommendations=["Component not found in graph."],
            )

        snaps = self._snapshots.get(component_id, [])
        growth_rate = _compute_growth_rate(snaps)
        total_mb = comp.capacity.max_memory_mb
        current_mb = comp.metrics.memory_used_mb if comp.metrics.memory_used_mb > 0 else (
            snaps[-1].used_mb if snaps else 0.0
        )
        baseline_mb = snaps[0].used_mb if snaps else 0.0
        utilization = (current_mb / total_mb * 100.0) if total_mb > 0 else 0.0

        # Determine if leaking: positive growth over threshold
        is_leaking = growth_rate > 0.5  # > 0.5 MB/hour is suspicious

        # Severity based on growth rate relative to total memory
        if total_mb > 0 and growth_rate > 0:
            hours_to_fill = (total_mb - current_mb) / growth_rate if growth_rate > 0 else float("inf")
            if hours_to_fill <= 0:
                score = 100.0
            elif hours_to_fill < 6:
                score = 90.0
            elif hours_to_fill < 24:
                score = 70.0
            elif hours_to_fill < 72:
                score = 50.0
            elif hours_to_fill < 168:
                score = 30.0
            else:
                score = 10.0
        else:
            score = 0.0

        severity = _classify_severity(score)
        confidence = min(1.0, len(snaps) / 10.0) if snaps else 0.0

        recs: list[str] = []
        if is_leaking:
            recs.append(
                f"Memory growing at {growth_rate:.1f} MB/hour. "
                f"Investigate allocation patterns."
            )
        if utilization > 80.0:
            recs.append(
                f"Memory utilization at {utilization:.0f}%. "
                f"Consider increasing memory limit or fixing leak."
            )
        if not snaps:
            recs.append("No memory snapshots available. Enable memory monitoring.")

        return GrowthRateResult(
            component_id=component_id,
            growth_rate_mb_per_hour=round(growth_rate, 3),
            baseline_mb=round(baseline_mb, 2),
            current_mb=round(current_mb, 2),
            total_mb=round(total_mb, 2),
            utilization_percent=round(utilization, 2),
            is_leaking=is_leaking,
            confidence=round(confidence, 2),
            severity=severity,
            recommendations=recs,
        )

    # -- Time-to-OOM Estimation -----------------------------------------------

    def estimate_time_to_oom(self, component_id: str) -> OOMEstimation:
        """Estimate time until OOM for a component."""
        comp = self._graph.get_component(component_id)
        if comp is None:
            return OOMEstimation(
                component_id=component_id,
                recommendations=["Component not found in graph."],
            )

        snaps = self._snapshots.get(component_id, [])
        growth_rate = _compute_growth_rate(snaps)
        limit_mb = comp.capacity.max_memory_mb
        current_mb = comp.metrics.memory_used_mb if comp.metrics.memory_used_mb > 0 else (
            snaps[-1].used_mb if snaps else 0.0
        )

        # Use OOM threshold (95% of limit)
        effective_limit = limit_mb * _OOM_THRESHOLD
        time_to_oom = _estimate_time_to_threshold(current_mb, effective_limit, growth_rate)
        probability = _oom_probability_in_window(time_to_oom, 24.0)

        # Severity
        if time_to_oom <= 1.0:
            severity = LeakSeverity.CRITICAL
        elif time_to_oom <= 6.0:
            severity = LeakSeverity.HIGH
        elif time_to_oom <= 24.0:
            severity = LeakSeverity.MEDIUM
        elif time_to_oom <= 72.0:
            severity = LeakSeverity.LOW
        else:
            severity = LeakSeverity.NONE

        recs: list[str] = []
        if time_to_oom < 24.0:
            recs.append(
                f"OOM predicted in {time_to_oom:.1f} hours. "
                f"Immediate action required."
            )
        if growth_rate > 0:
            recs.append(
                f"Growth rate: {growth_rate:.1f} MB/hour. "
                f"Monitor and plan for capacity increase."
            )
        if probability > 0.5:
            recs.append(
                f"OOM probability in next 24h: {probability:.0%}. "
                f"Consider restarting or scaling the service."
            )

        return OOMEstimation(
            component_id=component_id,
            time_to_oom_hours=round(time_to_oom, 2) if time_to_oom != float("inf") else float("inf"),
            current_usage_mb=round(current_mb, 2),
            memory_limit_mb=round(limit_mb, 2),
            growth_rate_mb_per_hour=round(growth_rate, 3),
            oom_probability_24h=round(probability, 3),
            severity=severity,
            recommendations=recs,
        )

    # -- Cascade Analysis -----------------------------------------------------

    def analyze_cascade(self, component_id: str) -> CascadeImpact:
        """Analyze how an OOM in one component cascades to others."""
        comp = self._graph.get_component(component_id)
        if comp is None:
            return CascadeImpact(
                source_component_id=component_id,
                recommendations=["Component not found in graph."],
            )

        affected, depth, critical_path = _cascade_depth_bfs(
            self._graph, component_id
        )

        # Impact score based on number of affected, depth, and dependency types
        base_score = min(50.0, len(affected) * 10.0)
        depth_score = min(30.0, depth * 10.0)

        # Check weight of edges from source
        edge_weight_score = 0.0
        dependents = self._graph.get_dependents(component_id)
        for dep in dependents:
            edge = self._graph.get_dependency_edge(dep.id, component_id)
            if edge and edge.dependency_type == "requires":
                edge_weight_score += 5.0
            elif edge and edge.dependency_type == "optional":
                edge_weight_score += 2.0
            else:
                edge_weight_score += 1.0

        total_score = _clamp(base_score + depth_score + min(20.0, edge_weight_score))
        severity = _classify_severity(total_score)

        recs: list[str] = []
        if len(affected) > 0:
            recs.append(
                f"OOM in {component_id} affects {len(affected)} component(s). "
                f"Max cascade depth: {depth}."
            )
        if depth >= 3:
            recs.append(
                "Deep cascade chain detected. Add circuit breakers or "
                "graceful degradation."
            )
        if any(
            self._graph.get_dependency_edge(d.id, component_id)
            and self._graph.get_dependency_edge(d.id, component_id).dependency_type == "requires"
            for d in dependents
        ):
            recs.append(
                "Hard dependencies on this component. Consider adding "
                "fallback mechanisms."
            )

        return CascadeImpact(
            source_component_id=component_id,
            affected_components=affected,
            cascade_depth=depth,
            total_impact_score=round(total_score, 2),
            critical_path=critical_path,
            severity=severity,
            recommendations=recs,
        )

    # -- GC Pressure Scoring --------------------------------------------------

    def analyze_gc_pressure(self, component_id: str) -> GCPressureScore:
        """Analyze GC pressure for a component."""
        comp = self._graph.get_component(component_id)
        if comp is None:
            return GCPressureScore(
                component_id=component_id,
                recommendations=["Component not found in graph."],
            )

        gc_algo = self._gc_algorithms.get(component_id, GCAlgorithm.NO_GC)

        if gc_algo == GCAlgorithm.NO_GC:
            return GCPressureScore(
                component_id=component_id,
                gc_algorithm=gc_algo,
                pressure_score=0.0,
                severity=LeakSeverity.NONE,
                recommendations=["No GC configured. Language may use manual memory management."],
            )

        snaps = self._snapshots.get(component_id, [])
        heap_mb = comp.metrics.memory_used_mb * 0.7  # Approximate heap as 70%
        if snaps:
            last = snaps[-1]
            heap_mb = last.heap_mb if last.heap_mb > 0 else heap_mb
            alloc_rate = last.allocation_rate_mb_per_sec
        else:
            alloc_rate = 0.0

        pause_ms, pauses_per_min = _gc_pause_estimate(gc_algo, heap_mb, alloc_rate)
        impact = _throughput_impact(pause_ms, pauses_per_min)

        # Pressure score: combine pause time, frequency, and throughput impact
        pressure = _clamp(
            (pause_ms / 100.0) * 30.0
            + (pauses_per_min / 10.0) * 30.0
            + impact * 0.4
        )
        severity = _classify_severity(pressure)

        recs: list[str] = []
        if pressure > 50.0:
            recs.append(
                f"High GC pressure ({pressure:.0f}/100). "
                f"Consider switching to a low-pause GC (ZGC/Shenandoah)."
            )
        if pause_ms > 50.0:
            recs.append(
                f"GC pauses averaging {pause_ms:.1f}ms. "
                f"Reduce heap size or tune GC parameters."
            )
        if alloc_rate > 100.0:
            recs.append(
                f"High allocation rate ({alloc_rate:.0f} MB/s). "
                f"Reduce object creation or use object pools."
            )

        return GCPressureScore(
            component_id=component_id,
            gc_algorithm=gc_algo,
            pressure_score=round(pressure, 2),
            estimated_pause_ms=round(pause_ms, 2),
            pause_frequency_per_minute=round(pauses_per_min, 2),
            throughput_impact_percent=round(impact, 2),
            allocation_rate_mb_per_sec=round(alloc_rate, 2),
            severity=severity,
            recommendations=recs,
        )

    # -- Fragmentation Risk ---------------------------------------------------

    def analyze_fragmentation(
        self,
        component_id: str,
        region_usages: dict[MemoryRegion, tuple[float, float]] | None = None,
    ) -> FragmentationRisk:
        """Assess memory fragmentation risk.

        *region_usages* maps region -> (used_mb, total_mb).
        """
        comp = self._graph.get_component(component_id)
        if comp is None:
            return FragmentationRisk(
                component_id=component_id,
                recommendations=["Component not found in graph."],
            )

        if region_usages is None:
            # Infer from component metrics
            total = comp.capacity.max_memory_mb
            used = comp.metrics.memory_used_mb
            region_usages = {
                MemoryRegion.HEAP: (used * 0.7, total * 0.7),
                MemoryRegion.OFF_HEAP: (used * 0.2, total * 0.2),
                MemoryRegion.STACK: (used * 0.1, total * 0.1),
            }

        total_free = 0.0
        total_used = 0.0
        region_risks: dict[str, float] = {}

        for region, (used, total) in region_usages.items():
            free = max(0.0, total - used)
            total_free += free
            total_used += used
            util = used / total if total > 0 else 0.0
            risk_mult = _REGION_FRAGMENTATION_RISK.get(region, 0.5)
            # Fragmentation risk increases with utilization
            region_risk = util * risk_mult
            region_risks[region.value] = round(region_risk, 3)

        total_capacity = total_free + total_used
        fragmentation_ratio = 0.0
        if total_capacity > 0:
            # Simulate fragmentation as ratio of free memory that's unusable
            # Higher utilization means more fragmentation
            utilization = total_used / total_capacity
            fragmentation_ratio = utilization * 0.4 + (1.0 - (total_free / total_capacity)) * 0.3

        fragmentation_ratio = _clamp(fragmentation_ratio, 0.0, 1.0)
        level = _classify_fragmentation(fragmentation_ratio)
        risk_score = fragmentation_ratio * 100.0

        # Estimate largest free block (simplified)
        largest_free = total_free * (1.0 - fragmentation_ratio) if total_free > 0 else 0.0

        recs: list[str] = []
        if level in (FragmentationLevel.SEVERE, FragmentationLevel.HIGH):
            recs.append(
                "High memory fragmentation detected. Consider defragmentation "
                "or service restart."
            )
        if fragmentation_ratio > 0.5:
            recs.append(
                "Over 50% fragmentation. Use memory pools or slab allocators "
                "to reduce fragmentation."
            )

        return FragmentationRisk(
            component_id=component_id,
            fragmentation_level=level,
            risk_score=round(risk_score, 2),
            largest_free_block_mb=round(largest_free, 2),
            total_free_mb=round(total_free, 2),
            fragmentation_ratio=round(fragmentation_ratio, 3),
            region_risks=region_risks,
            recommendations=recs,
        )

    # -- Memory Pool Exhaustion -----------------------------------------------

    def analyze_pool_exhaustion(
        self,
        component_id: str,
        pool_name: str = "default",
        pool_total_mb: float = 0.0,
        pool_used_mb: float = 0.0,
        alloc_rate_mb_per_hour: float = 0.0,
        dealloc_rate_mb_per_hour: float = 0.0,
    ) -> PoolExhaustionResult:
        """Model memory pool exhaustion for a component."""
        comp = self._graph.get_component(component_id)
        if comp is None:
            return PoolExhaustionResult(
                component_id=component_id,
                pool_name=pool_name,
                recommendations=["Component not found in graph."],
            )

        if pool_total_mb <= 0:
            pool_total_mb = comp.capacity.max_memory_mb * 0.5  # default pool = 50% of max
        if pool_used_mb <= 0:
            pool_used_mb = comp.metrics.memory_used_mb * 0.5

        usage_pct = (pool_used_mb / pool_total_mb * 100.0) if pool_total_mb > 0 else 0.0
        net_growth = alloc_rate_mb_per_hour - dealloc_rate_mb_per_hour
        time_to_exhaust = _estimate_time_to_threshold(pool_used_mb, pool_total_mb, net_growth)

        if time_to_exhaust <= 1.0:
            impact = "critical"
            severity = LeakSeverity.CRITICAL
        elif time_to_exhaust <= 6.0:
            impact = "high"
            severity = LeakSeverity.HIGH
        elif time_to_exhaust <= 24.0:
            impact = "medium"
            severity = LeakSeverity.MEDIUM
        elif time_to_exhaust < float("inf"):
            impact = "low"
            severity = LeakSeverity.LOW
        else:
            impact = "none"
            severity = LeakSeverity.NONE

        recs: list[str] = []
        if net_growth > 0:
            recs.append(
                f"Pool '{pool_name}' growing at {net_growth:.1f} MB/hour (net). "
                f"Time to exhaustion: {time_to_exhaust:.1f}h."
            )
        if usage_pct > 80.0:
            recs.append(
                f"Pool '{pool_name}' at {usage_pct:.0f}% capacity. "
                f"Consider increasing pool size or reducing allocations."
            )

        return PoolExhaustionResult(
            component_id=component_id,
            pool_name=pool_name,
            current_usage_percent=round(usage_pct, 2),
            time_to_exhaustion_hours=round(time_to_exhaust, 2) if time_to_exhaust != float("inf") else float("inf"),
            exhaustion_impact=impact,
            allocation_rate_mb_per_hour=round(alloc_rate_mb_per_hour, 2),
            deallocation_rate_mb_per_hour=round(dealloc_rate_mb_per_hour, 2),
            net_growth_mb_per_hour=round(net_growth, 2),
            severity=severity,
            recommendations=recs,
        )

    # -- Container Memory Limit Analysis --------------------------------------

    def analyze_container_memory(self, component_id: str) -> ContainerMemoryAnalysis:
        """Analyze container memory limit vs actual usage."""
        comp = self._graph.get_component(component_id)
        if comp is None:
            return ContainerMemoryAnalysis(
                component_id=component_id,
                recommendations=["Component not found in graph."],
            )

        limit_mb = comp.capacity.max_memory_mb
        actual_mb = comp.metrics.memory_used_mb
        ratio = (actual_mb / limit_mb) if limit_mb > 0 else 0.0
        headroom = max(0.0, limit_mb - actual_mb)

        # OOM kill risk
        if ratio >= _OOM_THRESHOLD:
            risk = "critical"
            severity = LeakSeverity.CRITICAL
        elif ratio >= _CONTAINER_SAFETY_MARGIN:
            risk = "high"
            severity = LeakSeverity.HIGH
        elif ratio >= 0.7:
            risk = "medium"
            severity = LeakSeverity.MEDIUM
        elif ratio >= 0.5:
            risk = "low"
            severity = LeakSeverity.LOW
        else:
            risk = "minimal"
            severity = LeakSeverity.NONE

        over_provisioned = ratio < 0.3 and limit_mb > 512
        under_provisioned = ratio > _CONTAINER_SAFETY_MARGIN

        # Recommend limit based on usage + 30% headroom
        recommended = actual_mb * 1.3 if actual_mb > 0 else limit_mb

        recs: list[str] = []
        if under_provisioned:
            recs.append(
                f"Container is under-provisioned (using {ratio:.0%} of limit). "
                f"Increase memory limit to at least {recommended:.0f} MB."
            )
        if over_provisioned:
            recs.append(
                f"Container is over-provisioned (using only {ratio:.0%} of limit). "
                f"Reduce limit to save resources."
            )
        if risk in ("critical", "high"):
            recs.append(
                f"OOM kill risk is {risk}. Immediate action required."
            )

        return ContainerMemoryAnalysis(
            component_id=component_id,
            container_limit_mb=round(limit_mb, 2),
            actual_usage_mb=round(actual_mb, 2),
            usage_ratio=round(ratio, 3),
            headroom_mb=round(headroom, 2),
            oom_kill_risk=risk,
            limit_recommendation_mb=round(recommended, 2),
            over_provisioned=over_provisioned,
            under_provisioned=under_provisioned,
            severity=severity,
            recommendations=recs,
        )

    # -- Statistical Anomaly Scoring ------------------------------------------

    def detect_anomaly(self, component_id: str) -> AnomalyScore:
        """Detect memory leak via statistical anomaly scoring."""
        comp = self._graph.get_component(component_id)
        if comp is None:
            return AnomalyScore(
                component_id=component_id,
                recommendations=["Component not found in graph."],
            )

        snaps = self._snapshots.get(component_id, [])
        if len(snaps) < _MIN_DATA_POINTS:
            return AnomalyScore(
                component_id=component_id,
                recommendations=[
                    f"Insufficient data ({len(snaps)} snapshots). "
                    f"Need at least {_MIN_DATA_POINTS} for anomaly detection."
                ],
            )

        values = [s.used_mb for s in snaps]
        current = values[-1]
        mean_val = _mean(values)
        std_val = _std_dev(values)
        z = _z_score(current, mean_val, std_val)

        # Anomaly if z-score > 2.0 (beyond 2 standard deviations)
        is_anomalous = abs(z) > 2.0
        anomaly_score = _clamp(abs(z) * 25.0)

        # Determine trend direction
        growth = _compute_growth_rate(snaps)
        if abs(growth) < 0.1:
            direction = TrendDirection.STABLE
        elif growth > 0:
            # Check if volatile
            if std_val > mean_val * 0.3:
                direction = TrendDirection.VOLATILE
            else:
                direction = TrendDirection.INCREASING
        else:
            direction = TrendDirection.DECREASING

        severity = _classify_severity(anomaly_score)

        recs: list[str] = []
        if is_anomalous:
            recs.append(
                f"Memory usage anomaly detected (z-score: {z:.2f}). "
                f"Current: {current:.1f} MB, Mean: {mean_val:.1f} MB."
            )
        if direction == TrendDirection.INCREASING:
            recs.append("Sustained upward memory trend. Investigate for leaks.")
        if direction == TrendDirection.VOLATILE:
            recs.append("Volatile memory usage. Check for bursty workloads or intermittent leaks.")

        return AnomalyScore(
            component_id=component_id,
            anomaly_score=round(anomaly_score, 2),
            z_score=round(z, 3),
            is_anomalous=is_anomalous,
            mean_usage_mb=round(mean_val, 2),
            std_dev_mb=round(std_val, 2),
            current_usage_mb=round(current, 2),
            trend_direction=direction,
            severity=severity,
            recommendations=recs,
        )

    # -- Heap vs Off-Heap Split Analysis --------------------------------------

    def analyze_heap_split(self, component_id: str) -> HeapOffHeapSplit:
        """Analyze heap vs off-heap memory split."""
        comp = self._graph.get_component(component_id)
        if comp is None:
            return HeapOffHeapSplit(
                component_id=component_id,
                recommendations=["Component not found in graph."],
            )

        snaps = self._snapshots.get(component_id, [])
        total_mem = comp.capacity.max_memory_mb

        if snaps:
            last = snaps[-1]
            heap_mb = last.heap_mb
            off_heap_mb = last.off_heap_mb
            if heap_mb <= 0 and off_heap_mb <= 0:
                # Estimate: 70% heap, 30% off-heap
                used = last.used_mb
                heap_mb = used * 0.7
                off_heap_mb = used * 0.3
        else:
            used = comp.metrics.memory_used_mb
            heap_mb = used * 0.7
            off_heap_mb = used * 0.3

        total_used = heap_mb + off_heap_mb
        heap_ratio = heap_mb / total_used if total_used > 0 else 0.0
        off_heap_ratio = off_heap_mb / total_used if total_used > 0 else 0.0

        # Compute growth rates for each region
        if len(snaps) >= 2:
            heap_values = [s.heap_mb if s.heap_mb > 0 else s.used_mb * 0.7 for s in snaps]
            off_heap_values = [s.off_heap_mb if s.off_heap_mb > 0 else s.used_mb * 0.3 for s in snaps]
            times = [s.timestamp_hours for s in snaps]

            heap_slope, _, _ = _linear_regression(times, heap_values)
            off_heap_slope, _, _ = _linear_regression(times, off_heap_values)
        else:
            heap_slope = 0.0
            off_heap_slope = 0.0

        # Determine which region is leaking
        if heap_slope > off_heap_slope and heap_slope > 0.1:
            leak_region = MemoryRegion.HEAP
        elif off_heap_slope > heap_slope and off_heap_slope > 0.1:
            leak_region = MemoryRegion.OFF_HEAP
        else:
            leak_region = MemoryRegion.HEAP  # default

        # Balance score: ideal is around 70/30 for JVM-like apps
        ideal_heap_ratio = 0.7
        balance_deviation = abs(heap_ratio - ideal_heap_ratio)
        balance_score = _clamp((1.0 - balance_deviation) * 100.0)

        recs: list[str] = []
        if off_heap_ratio > 0.5:
            recs.append(
                "Off-heap memory exceeds heap. Check native memory allocations, "
                "direct buffers, or JNI usage."
            )
        if heap_slope > 1.0:
            recs.append(
                f"Heap growing at {heap_slope:.1f} MB/hour. "
                "Likely object retention leak."
            )
        if off_heap_slope > 1.0:
            recs.append(
                f"Off-heap growing at {off_heap_slope:.1f} MB/hour. "
                "Check for native memory leaks or direct buffer leaks."
            )

        return HeapOffHeapSplit(
            component_id=component_id,
            total_memory_mb=round(total_mem, 2),
            heap_mb=round(heap_mb, 2),
            off_heap_mb=round(off_heap_mb, 2),
            heap_ratio=round(heap_ratio, 3),
            off_heap_ratio=round(off_heap_ratio, 3),
            heap_growth_rate_mb_per_hour=round(heap_slope, 3),
            off_heap_growth_rate_mb_per_hour=round(off_heap_slope, 3),
            leak_region=leak_region,
            balance_score=round(balance_score, 2),
            recommendations=recs,
        )

    # -- Remediation Priority Scoring -----------------------------------------

    def compute_remediation_priority(self, component_id: str) -> RemediationPriority:
        """Compute remediation priority score for a leaking component."""
        comp = self._graph.get_component(component_id)
        if comp is None:
            return RemediationPriority(
                component_id=component_id,
                recommendations=["Component not found in graph."],
            )

        # Get OOM estimation for time urgency
        oom = self.estimate_time_to_oom(component_id)
        growth = self.analyze_growth_rate(component_id)

        # Count dependents
        dependents = self._graph.get_dependents(component_id)
        dep_count = len(dependents)

        # Business impact from cost profile
        revenue = comp.cost_profile.revenue_per_minute

        priority = _remediation_priority_score(
            growth.severity, oom.time_to_oom_hours, dep_count, revenue
        )

        gc_algo = self._gc_algorithms.get(component_id, GCAlgorithm.NO_GC)
        actions = _select_remediation_actions(
            growth.severity, oom.time_to_oom_hours,
            comp.autoscaling.enabled, gc_algo
        )
        fix_time = _estimate_fix_time(actions)

        # Business impact score
        business_impact = _clamp(
            dep_count * 10.0 + math.log2(max(1.0, revenue + 1.0)) * 10.0
        )

        # Technical debt score based on leak rate
        tech_debt = _clamp(growth.growth_rate_mb_per_hour * 5.0)

        urgency = _classify_severity(priority)

        recs: list[str] = []
        if priority > 60.0:
            recs.append(
                f"High remediation priority ({priority:.0f}/100). "
                f"Fix within {fix_time:.0f} hours."
            )
        for action in actions[:3]:  # Top 3 actions
            effectiveness = _REMEDIATION_EFFECTIVENESS.get(action, 0.0)
            recs.append(
                f"Action: {action.value} (effectiveness: {effectiveness:.0%})"
            )

        return RemediationPriority(
            component_id=component_id,
            priority_score=round(priority, 2),
            recommended_actions=actions,
            urgency=urgency,
            estimated_fix_time_hours=fix_time,
            business_impact_score=round(business_impact, 2),
            technical_debt_score=round(tech_debt, 2),
            recommendations=recs,
        )

    # -- Autoscaling Impact ---------------------------------------------------

    def analyze_autoscaling_impact(
        self,
        component_id: str,
        memory_threshold_percent: float = 80.0,
    ) -> AutoscalingImpact:
        """Analyze impact of memory leaks on autoscaling (HPA triggers)."""
        comp = self._graph.get_component(component_id)
        if comp is None:
            return AutoscalingImpact(
                component_id=component_id,
                recommendations=["Component not found in graph."],
            )

        limit_mb = comp.capacity.max_memory_mb
        current_mb = comp.metrics.memory_used_mb
        current_pct = (current_mb / limit_mb * 100.0) if limit_mb > 0 else 0.0

        snaps = self._snapshots.get(component_id, [])
        growth_rate = _compute_growth_rate(snaps)

        # Time to reach scaling threshold
        threshold_mb = limit_mb * (memory_threshold_percent / 100.0)
        time_to_scale = _estimate_time_to_threshold(current_mb, threshold_mb, growth_rate)

        # Will HPA trigger?
        hpa_enabled = comp.autoscaling.enabled
        hpa_triggered = current_pct >= memory_threshold_percent

        # Predict scale events in 24h
        if growth_rate > 0 and hpa_enabled:
            # Assume each scale event buys ~20% headroom temporarily
            headroom_per_scale = limit_mb * 0.2
            memory_consumed_24h = growth_rate * 24.0
            scale_events = int(memory_consumed_24h / headroom_per_scale) if headroom_per_scale > 0 else 0
        else:
            scale_events = 0

        # Cost increase from scaling
        if scale_events > 0 and hpa_enabled:
            max_replicas = comp.autoscaling.max_replicas
            current_replicas = comp.replicas
            max_additional = max_replicas - current_replicas
            actual_scale_events = min(scale_events, max_additional)
            cost_increase = (actual_scale_events / max(1, current_replicas)) * 100.0
        else:
            cost_increase = 0.0
            actual_scale_events = scale_events

        # Is scaling effective? (only if leak is not faster than scaling)
        scaling_effective = True
        if growth_rate > 0 and hpa_enabled:
            # If even max replicas can't keep up, scaling is ineffective
            if scale_events > (comp.autoscaling.max_replicas - comp.replicas):
                scaling_effective = False

        recs: list[str] = []
        if not hpa_enabled and growth_rate > 0:
            recs.append(
                "Autoscaling not enabled. Memory leak will cause OOM without "
                "automatic recovery."
            )
        if hpa_triggered:
            recs.append(
                f"Memory at {current_pct:.0f}%, exceeding HPA threshold "
                f"({memory_threshold_percent:.0f}%). Scaling in progress."
            )
        if not scaling_effective:
            recs.append(
                "Memory growth rate exceeds autoscaling capacity. "
                "Fix the leak; scaling alone cannot resolve this."
            )
        if cost_increase > 50.0:
            recs.append(
                f"Predicted {cost_increase:.0f}% cost increase from memory-driven scaling. "
                "Address the leak to control costs."
            )

        return AutoscalingImpact(
            component_id=component_id,
            hpa_triggered=hpa_triggered,
            memory_threshold_percent=round(memory_threshold_percent, 2),
            current_memory_percent=round(current_pct, 2),
            time_to_scale_hours=round(time_to_scale, 2) if time_to_scale != float("inf") else float("inf"),
            scale_events_predicted_24h=actual_scale_events if hpa_enabled else scale_events,
            cost_increase_percent=round(cost_increase, 2),
            scaling_effective=scaling_effective,
            recommendations=recs,
        )

    # -- Trend Extrapolation --------------------------------------------------

    def extrapolate_trend(
        self,
        component_id: str,
        horizon_hours: float = _DEFAULT_EXTRAPOLATION_HOURS,
    ) -> TrendExtrapolation:
        """Extrapolate historical memory trends."""
        comp = self._graph.get_component(component_id)
        if comp is None:
            return TrendExtrapolation(
                component_id=component_id,
                recommendations=["Component not found in graph."],
            )

        snaps = self._snapshots.get(component_id, [])
        if len(snaps) < 2:
            return TrendExtrapolation(
                component_id=component_id,
                data_points=len(snaps),
                prediction_horizon_hours=horizon_hours,
                recommendations=[
                    "Insufficient data for trend extrapolation. "
                    "Need at least 2 snapshots."
                ],
            )

        xs = [s.timestamp_hours for s in snaps]
        ys = [s.used_mb for s in snaps]
        slope, intercept, r_sq = _linear_regression(xs, ys)

        # Predict at horizon
        last_time = xs[-1]
        predicted = slope * (last_time + horizon_hours) + intercept
        predicted = max(0.0, predicted)

        # Trend direction
        if abs(slope) < 0.1:
            direction = TrendDirection.STABLE
        elif slope > 0:
            direction = TrendDirection.INCREASING
        else:
            direction = TrendDirection.DECREASING

        # Confidence based on R-squared and data points
        data_confidence = min(1.0, len(snaps) / 20.0)
        confidence = r_sq * 0.7 + data_confidence * 0.3

        recs: list[str] = []
        if direction == TrendDirection.INCREASING and slope > 1.0:
            recs.append(
                f"Memory increasing at {slope:.1f} MB/hour. "
                f"Predicted: {predicted:.0f} MB in {horizon_hours:.0f}h "
                f"(R²={r_sq:.2f})."
            )
        if predicted > comp.capacity.max_memory_mb:
            recs.append(
                f"Predicted usage ({predicted:.0f} MB) exceeds capacity "
                f"({comp.capacity.max_memory_mb:.0f} MB) within {horizon_hours:.0f}h."
            )
        if confidence < 0.5:
            recs.append(
                "Low prediction confidence. Collect more data points "
                "for reliable extrapolation."
            )

        return TrendExtrapolation(
            component_id=component_id,
            data_points=len(snaps),
            trend_direction=direction,
            slope_mb_per_hour=round(slope, 3),
            intercept_mb=round(intercept, 2),
            r_squared=round(r_sq, 3),
            predicted_usage_mb=round(predicted, 2),
            prediction_horizon_hours=horizon_hours,
            confidence=round(confidence, 3),
            recommendations=recs,
        )

    # -- Full Analysis --------------------------------------------------------

    def full_analysis(self) -> MemoryLeakReport:
        """Run comprehensive memory leak analysis across all components."""
        components = self._graph.components
        timestamp = datetime.now(timezone.utc).isoformat()

        growth_rates: list[GrowthRateResult] = []
        oom_estimations: list[OOMEstimation] = []
        cascade_impacts: list[CascadeImpact] = []
        gc_pressures: list[GCPressureScore] = []
        frag_risks: list[FragmentationRisk] = []
        container_analyses: list[ContainerMemoryAnalysis] = []
        anomaly_scores: list[AnomalyScore] = []
        remediation_priorities: list[RemediationPriority] = []
        autoscaling_impacts: list[AutoscalingImpact] = []
        all_recs: list[str] = []

        leaking_count = 0

        for cid in components:
            gr = self.analyze_growth_rate(cid)
            growth_rates.append(gr)

            oom = self.estimate_time_to_oom(cid)
            oom_estimations.append(oom)

            cascade = self.analyze_cascade(cid)
            cascade_impacts.append(cascade)

            gc = self.analyze_gc_pressure(cid)
            gc_pressures.append(gc)

            frag = self.analyze_fragmentation(cid)
            frag_risks.append(frag)

            container = self.analyze_container_memory(cid)
            container_analyses.append(container)

            snaps = self._snapshots.get(cid, [])
            if len(snaps) >= _MIN_DATA_POINTS:
                anomaly = self.detect_anomaly(cid)
                anomaly_scores.append(anomaly)

            remed = self.compute_remediation_priority(cid)
            remediation_priorities.append(remed)

            autoscale = self.analyze_autoscaling_impact(cid)
            autoscaling_impacts.append(autoscale)

            if gr.is_leaking:
                leaking_count += 1

        # Overall risk score: average of top remediation priorities
        if remediation_priorities:
            scores = sorted(
                [r.priority_score for r in remediation_priorities], reverse=True
            )
            top_scores = scores[:max(1, len(scores) // 2)]
            overall_risk = _mean(top_scores)
        else:
            overall_risk = 0.0

        # Aggregate recommendations
        if leaking_count > 0:
            all_recs.append(
                f"{leaking_count} of {len(components)} components show memory leaks."
            )
        critical_ooms = [o for o in oom_estimations if o.severity == LeakSeverity.CRITICAL]
        if critical_ooms:
            all_recs.append(
                f"{len(critical_ooms)} component(s) at critical OOM risk."
            )
        high_gc = [g for g in gc_pressures if g.severity in (LeakSeverity.CRITICAL, LeakSeverity.HIGH)]
        if high_gc:
            all_recs.append(
                f"{len(high_gc)} component(s) under high GC pressure."
            )

        return MemoryLeakReport(
            timestamp=timestamp,
            component_count=len(components),
            leaking_components=leaking_count,
            overall_risk_score=round(overall_risk, 2),
            growth_rates=growth_rates,
            oom_estimations=oom_estimations,
            cascade_impacts=cascade_impacts,
            gc_pressures=gc_pressures,
            fragmentation_risks=frag_risks,
            container_analyses=container_analyses,
            anomaly_scores=anomaly_scores,
            remediation_priorities=remediation_priorities,
            autoscaling_impacts=autoscaling_impacts,
            recommendations=all_recs,
        )
