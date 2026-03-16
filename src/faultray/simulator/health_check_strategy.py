"""Health Check Strategy -- Optimization engine for health check configurations.

Analyzes and optimizes health check configurations across services.  Covers
liveness vs readiness vs startup probe differentiation, interval optimization,
cascading health check failure analysis, dependency chain analysis,
false-positive rate estimation, grace period and threshold tuning, endpoint
design recommendations, deep vs shallow trade-offs, timeout vs response time
matching, monitoring blind spot detection, service mesh health check
integration analysis, and a custom scoring rubric.
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
# Constants
# ---------------------------------------------------------------------------

_MIN_INTERVAL_SECONDS: float = 5.0
_MAX_INTERVAL_SECONDS: float = 120.0
_MIN_TIMEOUT_SECONDS: float = 1.0
_MAX_TIMEOUT_SECONDS: float = 30.0
_MIN_GRACE_PERIOD_SECONDS: float = 0.0
_MAX_GRACE_PERIOD_SECONDS: float = 600.0
_DEFAULT_RESPONSE_TIME_MS: float = 100.0
_NOISE_THRESHOLD_CHECKS_PER_MINUTE: float = 12.0
_SLOW_DETECTION_INTERVAL: float = 60.0
_CASCADE_DEPTH_WARN: int = 3
_CASCADE_DEPTH_CRITICAL: int = 5
_MAX_RUBRIC_SCORE: float = 100.0
_BLIND_SPOT_COVERAGE_THRESHOLD: float = 0.8


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class ProbeType(str, Enum):
    """Kubernetes-style probe types."""

    LIVENESS = "liveness"
    READINESS = "readiness"
    STARTUP = "startup"


class ProbeProtocol(str, Enum):
    """Supported probe protocols."""

    HTTP_GET = "http_get"
    TCP_SOCKET = "tcp_socket"
    GRPC = "grpc"
    EXEC = "exec"


class CheckDepth(str, Enum):
    """Depth of health check verification."""

    SHALLOW = "shallow"
    DEEP = "deep"
    DEPENDENCY_AWARE = "dependency_aware"


class Severity(str, Enum):
    """Finding severity levels."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class BlindSpotCategory(str, Enum):
    """Categories of health-check monitoring blind spots."""

    NO_STARTUP_PROBE = "no_startup_probe"
    NO_READINESS_PROBE = "no_readiness_probe"
    NO_LIVENESS_PROBE = "no_liveness_probe"
    MISSING_DEPENDENCY_CHECK = "missing_dependency_check"
    NO_DEEP_CHECK = "no_deep_check"
    TIMEOUT_MISMATCH = "timeout_mismatch"
    NO_GRACE_PERIOD = "no_grace_period"
    UNCHECKED_COMPONENT = "unchecked_component"
    SINGLE_PROTOCOL = "single_protocol"
    NO_SERVICE_MESH_CHECK = "no_service_mesh_check"


class ServiceMeshType(str, Enum):
    """Known service mesh implementations."""

    ISTIO = "istio"
    LINKERD = "linkerd"
    CONSUL_CONNECT = "consul_connect"
    NONE = "none"


class IntervalQuality(str, Enum):
    """Quality classification for health check intervals."""

    TOO_FREQUENT = "too_frequent"
    OPTIMAL = "optimal"
    TOO_INFREQUENT = "too_infrequent"


class RubricCategory(str, Enum):
    """Categories in the health check scoring rubric."""

    PROBE_COVERAGE = "probe_coverage"
    INTERVAL_TUNING = "interval_tuning"
    TIMEOUT_ALIGNMENT = "timeout_alignment"
    THRESHOLD_TUNING = "threshold_tuning"
    DEPTH_STRATEGY = "depth_strategy"
    GRACE_PERIOD = "grace_period"
    DEPENDENCY_AWARENESS = "dependency_awareness"
    CASCADE_SAFETY = "cascade_safety"
    ENDPOINT_DESIGN = "endpoint_design"
    MESH_INTEGRATION = "mesh_integration"


# ---------------------------------------------------------------------------
# Data-classes (result models)
# ---------------------------------------------------------------------------


@dataclass
class HealthCheckProbeConfig:
    """Configuration for a single health check probe."""

    probe_type: ProbeType
    protocol: ProbeProtocol
    endpoint: str = "/healthz"
    port: int = 8080
    interval_seconds: float = 10.0
    timeout_seconds: float = 5.0
    failure_threshold: int = 3
    success_threshold: int = 1
    initial_delay_seconds: float = 0.0
    grace_period_seconds: float = 0.0
    depth: CheckDepth = CheckDepth.SHALLOW
    checks_dependencies: list[str] = field(default_factory=list)


@dataclass
class IntervalAnalysis:
    """Result of analysing a health check interval."""

    component_id: str
    probe_type: ProbeType
    current_interval: float
    recommended_interval: float
    quality: IntervalQuality
    checks_per_minute: float
    noise_risk: float
    detection_delay_seconds: float
    findings: list[str] = field(default_factory=list)


@dataclass
class CascadeChain:
    """A single cascade chain from a root failure."""

    root_component_id: str
    chain: list[str] = field(default_factory=list)
    depth: int = 0
    estimated_total_detection_seconds: float = 0.0
    severity: Severity = Severity.LOW


@dataclass
class CascadeAnalysis:
    """Result of cascading health check failure analysis."""

    component_id: str
    chains: list[CascadeChain] = field(default_factory=list)
    max_depth: int = 0
    total_affected: int = 0
    severity: Severity = Severity.LOW
    recommendations: list[str] = field(default_factory=list)


@dataclass
class DependencyChainLink:
    """A single link in a health check dependency chain."""

    component_id: str
    probe_type: ProbeType
    depth: CheckDepth
    checks_component_ids: list[str] = field(default_factory=list)


@dataclass
class DependencyChainAnalysis:
    """Result of health check dependency chain analysis."""

    root_component_id: str
    links: list[DependencyChainLink] = field(default_factory=list)
    chain_length: int = 0
    circular_dependency_detected: bool = False
    severity: Severity = Severity.LOW
    recommendations: list[str] = field(default_factory=list)


@dataclass
class FalsePositiveEstimate:
    """Estimated false-positive rate for a health check configuration."""

    component_id: str
    estimated_rate_percent: float = 0.0
    timeout_induced_percent: float = 0.0
    dependency_induced_percent: float = 0.0
    network_induced_percent: float = 0.0
    risk_level: Severity = Severity.LOW
    contributing_factors: list[str] = field(default_factory=list)


@dataclass
class GracePeriodRecommendation:
    """Recommendation for grace period and threshold tuning."""

    component_id: str
    probe_type: ProbeType
    current_grace_period: float
    recommended_grace_period: float
    current_failure_threshold: int
    recommended_failure_threshold: int
    current_success_threshold: int
    recommended_success_threshold: int
    findings: list[str] = field(default_factory=list)


@dataclass
class EndpointRecommendation:
    """Recommendation for health check endpoint design."""

    component_id: str
    recommended_liveness_endpoint: str = "/healthz"
    recommended_readiness_endpoint: str = "/readyz"
    recommended_startup_endpoint: str = "/startupz"
    recommended_liveness_depth: CheckDepth = CheckDepth.SHALLOW
    recommended_readiness_depth: CheckDepth = CheckDepth.DEPENDENCY_AWARE
    recommended_startup_depth: CheckDepth = CheckDepth.DEEP
    findings: list[str] = field(default_factory=list)


@dataclass
class DepthTradeoff:
    """Analysis of deep vs shallow health check trade-offs."""

    component_id: str
    current_depth: CheckDepth
    recommended_depth: CheckDepth
    shallow_detection_time_seconds: float = 0.0
    deep_detection_time_seconds: float = 0.0
    shallow_false_positive_rate: float = 0.0
    deep_false_positive_rate: float = 0.0
    shallow_cost_score: float = 0.0
    deep_cost_score: float = 0.0
    recommendation: str = ""


@dataclass
class TimeoutAlignment:
    """Alignment analysis between timeout and service response time."""

    component_id: str
    configured_timeout_seconds: float
    estimated_p99_response_seconds: float
    ratio: float = 0.0
    is_aligned: bool = True
    recommended_timeout_seconds: float = 0.0
    findings: list[str] = field(default_factory=list)


@dataclass
class BlindSpot:
    """A detected health check monitoring blind spot."""

    component_id: str
    category: BlindSpotCategory
    severity: Severity
    description: str
    recommendation: str


@dataclass
class BlindSpotReport:
    """Report of all detected blind spots."""

    blind_spots: list[BlindSpot] = field(default_factory=list)
    coverage_ratio: float = 0.0
    total_components: int = 0
    covered_components: int = 0
    severity_counts: dict[str, int] = field(default_factory=dict)


@dataclass
class ServiceMeshHealthAnalysis:
    """Analysis of service mesh health check integration."""

    component_id: str
    mesh_type: ServiceMeshType = ServiceMeshType.NONE
    sidecar_probe_aligned: bool = False
    mtls_health_impact: float = 0.0
    retry_overlap_detected: bool = False
    circuit_breaker_conflict: bool = False
    findings: list[str] = field(default_factory=list)


@dataclass
class RubricScore:
    """Individual rubric category score."""

    category: RubricCategory
    score: float = 0.0
    max_score: float = 10.0
    weight: float = 1.0
    findings: list[str] = field(default_factory=list)


@dataclass
class HealthCheckScorecard:
    """Comprehensive health check scoring rubric result."""

    component_id: str
    overall_score: float = 0.0
    max_possible_score: float = _MAX_RUBRIC_SCORE
    grade: str = "F"
    rubric_scores: list[RubricScore] = field(default_factory=list)
    timestamp: str = ""
    recommendations: list[str] = field(default_factory=list)


@dataclass
class StrategyReport:
    """Overall health check strategy optimization report."""

    graph_id: str
    timestamp: str
    scorecards: list[HealthCheckScorecard] = field(default_factory=list)
    cascade_analysis: list[CascadeAnalysis] = field(default_factory=list)
    blind_spot_report: BlindSpotReport | None = None
    interval_analyses: list[IntervalAnalysis] = field(default_factory=list)
    overall_health_score: float = 0.0
    top_recommendations: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers (pure functions)
# ---------------------------------------------------------------------------


def _checks_per_minute(interval: float) -> float:
    """Calculate the number of checks per minute for a given interval."""
    if interval <= 0:
        return 0.0
    return 60.0 / interval


def _detection_delay(interval: float, failure_threshold: int) -> float:
    """Estimate worst-case detection delay in seconds."""
    return interval * failure_threshold


def _classify_interval(interval: float) -> IntervalQuality:
    """Classify the interval as too frequent, optimal, or too infrequent."""
    if interval < _MIN_INTERVAL_SECONDS:
        return IntervalQuality.TOO_FREQUENT
    if interval > _SLOW_DETECTION_INTERVAL:
        return IntervalQuality.TOO_INFREQUENT
    return IntervalQuality.OPTIMAL


def _noise_risk(interval: float) -> float:
    """Estimate noise risk from 0.0 (no noise) to 1.0 (very noisy)."""
    cpm = _checks_per_minute(interval)
    if cpm <= 0:
        return 0.0
    if cpm >= _NOISE_THRESHOLD_CHECKS_PER_MINUTE:
        return 1.0
    return min(1.0, cpm / _NOISE_THRESHOLD_CHECKS_PER_MINUTE)


def _severity_from_depth(depth: int) -> Severity:
    """Derive severity from cascade depth."""
    if depth >= _CASCADE_DEPTH_CRITICAL:
        return Severity.CRITICAL
    if depth >= _CASCADE_DEPTH_WARN:
        return Severity.HIGH
    if depth >= 2:
        return Severity.MEDIUM
    if depth >= 1:
        return Severity.LOW
    return Severity.INFO


def _grade_from_score(score: float) -> str:
    """Convert numeric score to letter grade."""
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


def _clamp(value: float, lo: float, hi: float) -> float:
    """Clamp value between lo and hi."""
    return max(lo, min(hi, value))


def _estimate_p99_from_component(comp: Component | None) -> float:
    """Estimate p99 response time in seconds from component profile."""
    if comp is None:
        return _DEFAULT_RESPONSE_TIME_MS / 1000.0
    base_ms = _DEFAULT_RESPONSE_TIME_MS
    if comp.type == ComponentType.DATABASE:
        base_ms = 200.0
    elif comp.type == ComponentType.EXTERNAL_API:
        base_ms = 500.0
    elif comp.type == ComponentType.CACHE:
        base_ms = 5.0
    elif comp.type == ComponentType.QUEUE:
        base_ms = 50.0
    elif comp.type == ComponentType.DNS:
        base_ms = 10.0
    elif comp.type == ComponentType.LOAD_BALANCER:
        base_ms = 20.0
    elif comp.type == ComponentType.STORAGE:
        base_ms = 150.0
    utilization = comp.utilization()
    if utilization > 80:
        base_ms *= 3.0
    elif utilization > 60:
        base_ms *= 1.5
    return base_ms / 1000.0


def _recommend_interval(comp: Component | None, dependents_count: int) -> float:
    """Recommend an optimal interval for a component."""
    base = 10.0
    if comp is not None:
        if comp.type in (ComponentType.LOAD_BALANCER, ComponentType.DNS):
            base = 5.0
        elif comp.type == ComponentType.DATABASE:
            base = 15.0
        elif comp.type == ComponentType.EXTERNAL_API:
            base = 30.0
        elif comp.type == ComponentType.CACHE:
            base = 10.0
    if dependents_count > 5:
        base = max(base, 15.0)
    elif dependents_count > 10:
        base = max(base, 30.0)
    return _clamp(base, _MIN_INTERVAL_SECONDS, _MAX_INTERVAL_SECONDS)


def _recommend_timeout(p99_response_seconds: float) -> float:
    """Recommend timeout as ~2-3x the p99 latency, clamped."""
    recommended = p99_response_seconds * 2.5
    return _clamp(recommended, _MIN_TIMEOUT_SECONDS, _MAX_TIMEOUT_SECONDS)


def _probe_coverage_score(probes: list[HealthCheckProbeConfig]) -> RubricScore:
    """Score probe type coverage (liveness + readiness + startup)."""
    types_present = {p.probe_type for p in probes}
    score = 0.0
    findings: list[str] = []
    if ProbeType.LIVENESS in types_present:
        score += 3.0
    else:
        findings.append("Missing liveness probe.")
    if ProbeType.READINESS in types_present:
        score += 4.0
    else:
        findings.append("Missing readiness probe.")
    if ProbeType.STARTUP in types_present:
        score += 3.0
    else:
        findings.append("Missing startup probe; slow-starting pods may be killed.")
    return RubricScore(
        category=RubricCategory.PROBE_COVERAGE,
        score=min(10.0, score),
        max_score=10.0,
        weight=1.5,
        findings=findings,
    )


def _interval_tuning_score(probes: list[HealthCheckProbeConfig]) -> RubricScore:
    """Score interval configuration quality."""
    if not probes:
        return RubricScore(
            category=RubricCategory.INTERVAL_TUNING,
            score=0.0,
            findings=["No probes configured."],
        )
    total = 0.0
    findings: list[str] = []
    for p in probes:
        q = _classify_interval(p.interval_seconds)
        if q == IntervalQuality.OPTIMAL:
            total += 10.0
        elif q == IntervalQuality.TOO_FREQUENT:
            total += 4.0
            findings.append(
                f"{p.probe_type.value} interval {p.interval_seconds}s is too frequent."
            )
        else:
            total += 5.0
            findings.append(
                f"{p.probe_type.value} interval {p.interval_seconds}s is too infrequent."
            )
    avg = total / len(probes)
    return RubricScore(
        category=RubricCategory.INTERVAL_TUNING,
        score=min(10.0, avg),
        max_score=10.0,
        weight=1.0,
        findings=findings,
    )


def _timeout_alignment_score(
    probes: list[HealthCheckProbeConfig],
    comp: Component | None,
) -> RubricScore:
    """Score timeout alignment with estimated response time."""
    if not probes:
        return RubricScore(
            category=RubricCategory.TIMEOUT_ALIGNMENT,
            score=0.0,
            findings=["No probes configured."],
        )
    p99 = _estimate_p99_from_component(comp)
    total = 0.0
    findings: list[str] = []
    for p in probes:
        ratio = p.timeout_seconds / p99 if p99 > 0 else 0.0
        if 1.5 <= ratio <= 5.0:
            total += 10.0
        elif ratio < 1.0:
            total += 2.0
            findings.append(
                f"{p.probe_type.value} timeout {p.timeout_seconds}s < p99 {p99:.3f}s."
            )
        elif ratio > 10.0:
            total += 5.0
            findings.append(
                f"{p.probe_type.value} timeout {p.timeout_seconds}s >> p99 {p99:.3f}s."
            )
        else:
            total += 7.0
    avg = total / len(probes)
    return RubricScore(
        category=RubricCategory.TIMEOUT_ALIGNMENT,
        score=min(10.0, avg),
        max_score=10.0,
        weight=1.2,
        findings=findings,
    )


def _threshold_tuning_score(probes: list[HealthCheckProbeConfig]) -> RubricScore:
    """Score failure/success threshold configuration."""
    if not probes:
        return RubricScore(
            category=RubricCategory.THRESHOLD_TUNING,
            score=0.0,
            findings=["No probes configured."],
        )
    total = 0.0
    findings: list[str] = []
    for p in probes:
        sub_score = 10.0
        if p.failure_threshold < 2:
            sub_score -= 4.0
            findings.append(
                f"{p.probe_type.value} failure_threshold={p.failure_threshold} is too low."
            )
        elif p.failure_threshold > 10:
            sub_score -= 3.0
            findings.append(
                f"{p.probe_type.value} failure_threshold={p.failure_threshold} is too high."
            )
        if p.success_threshold < 1:
            sub_score -= 3.0
            findings.append(
                f"{p.probe_type.value} success_threshold={p.success_threshold} is too low."
            )
        elif p.success_threshold > 5:
            sub_score -= 2.0
            findings.append(
                f"{p.probe_type.value} success_threshold too high for fast recovery."
            )
        total += max(0.0, sub_score)
    avg = total / len(probes)
    return RubricScore(
        category=RubricCategory.THRESHOLD_TUNING,
        score=min(10.0, avg),
        max_score=10.0,
        weight=1.0,
        findings=findings,
    )


def _depth_strategy_score(probes: list[HealthCheckProbeConfig]) -> RubricScore:
    """Score depth strategy (shallow liveness, deep readiness)."""
    findings: list[str] = []
    score = 5.0
    liveness = [p for p in probes if p.probe_type == ProbeType.LIVENESS]
    readiness = [p for p in probes if p.probe_type == ProbeType.READINESS]
    for p in liveness:
        if p.depth == CheckDepth.SHALLOW:
            score += 2.5
        else:
            findings.append("Liveness probe should be shallow to avoid cascading restarts.")
            score -= 2.0
    for p in readiness:
        if p.depth in (CheckDepth.DEEP, CheckDepth.DEPENDENCY_AWARE):
            score += 2.5
        else:
            findings.append("Readiness probe should be deep/dependency-aware.")
            score -= 1.0
    return RubricScore(
        category=RubricCategory.DEPTH_STRATEGY,
        score=_clamp(score, 0.0, 10.0),
        max_score=10.0,
        weight=1.3,
        findings=findings,
    )


def _grace_period_score(probes: list[HealthCheckProbeConfig]) -> RubricScore:
    """Score grace period / initial delay configuration."""
    findings: list[str] = []
    score = 5.0
    startup_probes = [p for p in probes if p.probe_type == ProbeType.STARTUP]
    liveness_probes = [p for p in probes if p.probe_type == ProbeType.LIVENESS]
    if startup_probes:
        for p in startup_probes:
            if p.grace_period_seconds > 0 or p.initial_delay_seconds > 0:
                score += 2.5
            else:
                findings.append("Startup probe has no grace period or initial delay.")
                score -= 1.0
    else:
        for p in liveness_probes:
            if p.initial_delay_seconds >= 10.0:
                score += 1.5
            else:
                findings.append(
                    "No startup probe and liveness initial delay < 10s. "
                    "Slow-starting containers may be killed."
                )
                score -= 2.0
    if not startup_probes and not liveness_probes:
        score = 0.0
        findings.append("No probes configured for grace period assessment.")
    return RubricScore(
        category=RubricCategory.GRACE_PERIOD,
        score=_clamp(score, 0.0, 10.0),
        max_score=10.0,
        weight=0.8,
        findings=findings,
    )


def _dependency_awareness_score(
    probes: list[HealthCheckProbeConfig],
    dependency_count: int,
) -> RubricScore:
    """Score dependency awareness in health checks."""
    findings: list[str] = []
    score = 5.0
    if dependency_count == 0:
        score = 10.0
        return RubricScore(
            category=RubricCategory.DEPENDENCY_AWARENESS,
            score=score,
            max_score=10.0,
            weight=1.0,
            findings=findings,
        )
    dep_aware_probes = [
        p for p in probes
        if p.depth == CheckDepth.DEPENDENCY_AWARE or len(p.checks_dependencies) > 0
    ]
    if dep_aware_probes:
        score += 3.0
        total_checked = sum(len(p.checks_dependencies) for p in dep_aware_probes)
        if total_checked >= dependency_count:
            score += 2.0
        else:
            findings.append(
                f"Only {total_checked}/{dependency_count} dependencies checked."
            )
    else:
        findings.append(
            "Component has dependencies but no probe checks them."
        )
        score -= 3.0
    return RubricScore(
        category=RubricCategory.DEPENDENCY_AWARENESS,
        score=_clamp(score, 0.0, 10.0),
        max_score=10.0,
        weight=1.1,
        findings=findings,
    )


def _cascade_safety_score(
    cascade: CascadeAnalysis | None,
) -> RubricScore:
    """Score cascade safety from cascade analysis."""
    findings: list[str] = []
    if cascade is None or cascade.max_depth == 0:
        return RubricScore(
            category=RubricCategory.CASCADE_SAFETY,
            score=10.0,
            max_score=10.0,
            weight=1.5,
            findings=findings,
        )
    score = 10.0
    if cascade.max_depth >= _CASCADE_DEPTH_CRITICAL:
        score -= 8.0
        findings.append(f"Cascade depth {cascade.max_depth} is critical.")
    elif cascade.max_depth >= _CASCADE_DEPTH_WARN:
        score -= 5.0
        findings.append(f"Cascade depth {cascade.max_depth} is concerning.")
    elif cascade.max_depth >= 2:
        score -= 2.0
    if cascade.total_affected > 5:
        score -= 2.0
        findings.append(f"{cascade.total_affected} components affected by cascade.")
    return RubricScore(
        category=RubricCategory.CASCADE_SAFETY,
        score=_clamp(score, 0.0, 10.0),
        max_score=10.0,
        weight=1.5,
        findings=findings,
    )


def _endpoint_design_score(probes: list[HealthCheckProbeConfig]) -> RubricScore:
    """Score endpoint design best practices."""
    findings: list[str] = []
    score = 5.0
    endpoints = [p.endpoint for p in probes]
    if any(e in ("/healthz", "/health", "/livez") for e in endpoints):
        score += 1.5
    else:
        findings.append("No standard liveness endpoint (/healthz) detected.")
    if any(e in ("/readyz", "/ready") for e in endpoints):
        score += 1.5
    else:
        findings.append("No standard readiness endpoint (/readyz) detected.")
    if any(e in ("/startupz", "/startup") for e in endpoints):
        score += 1.0
    unique_endpoints = set(endpoints)
    if len(unique_endpoints) < len(probes) and len(probes) > 1:
        findings.append("Multiple probes share the same endpoint.")
        score -= 2.0
    http_probes = [p for p in probes if p.protocol == ProbeProtocol.HTTP_GET]
    if http_probes:
        score += 1.0
    return RubricScore(
        category=RubricCategory.ENDPOINT_DESIGN,
        score=_clamp(score, 0.0, 10.0),
        max_score=10.0,
        weight=0.7,
        findings=findings,
    )


def _mesh_integration_score(
    mesh_analysis: ServiceMeshHealthAnalysis | None,
) -> RubricScore:
    """Score service mesh integration quality."""
    findings: list[str] = []
    if mesh_analysis is None or mesh_analysis.mesh_type == ServiceMeshType.NONE:
        return RubricScore(
            category=RubricCategory.MESH_INTEGRATION,
            score=5.0,
            max_score=10.0,
            weight=0.5,
            findings=["No service mesh detected; score neutral."],
        )
    score = 5.0
    if mesh_analysis.sidecar_probe_aligned:
        score += 2.0
    else:
        findings.append("Sidecar proxy health check not aligned with app probes.")
        score -= 1.0
    if mesh_analysis.retry_overlap_detected:
        findings.append("Retry policy overlap between mesh and app-level retries.")
        score -= 1.5
    if mesh_analysis.circuit_breaker_conflict:
        findings.append("Circuit breaker conflict between mesh and app configuration.")
        score -= 1.5
    if mesh_analysis.mtls_health_impact > 0.1:
        findings.append(
            f"mTLS adds {mesh_analysis.mtls_health_impact:.1f}s latency; "
            "adjust timeout accordingly."
        )
        score -= 1.0
    else:
        score += 1.5
    return RubricScore(
        category=RubricCategory.MESH_INTEGRATION,
        score=_clamp(score, 0.0, 10.0),
        max_score=10.0,
        weight=0.5,
        findings=findings,
    )


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class HealthCheckStrategyOptimizer:
    """Analyzes and optimizes health check strategies for an infrastructure graph.

    Provides interval optimization, cascade analysis, dependency chain
    analysis, false-positive estimation, grace period tuning, endpoint
    design recommendations, depth trade-off analysis, timeout alignment,
    blind spot detection, service mesh integration analysis, and a
    comprehensive scoring rubric.
    """

    def __init__(self) -> None:
        self._now = datetime.now(timezone.utc)

    # ------------------------------------------------------------------
    # Interval optimization
    # ------------------------------------------------------------------

    def analyze_interval(
        self,
        graph: InfraGraph,
        component_id: str,
        probe: HealthCheckProbeConfig,
    ) -> IntervalAnalysis:
        """Analyze a health check interval for a component.

        Too frequent intervals generate noise; too infrequent ones delay
        failure detection.
        """
        comp = graph.get_component(component_id)
        dependents = self._safe_dependents(graph, component_id)
        quality = _classify_interval(probe.interval_seconds)
        cpm = _checks_per_minute(probe.interval_seconds)
        nr = _noise_risk(probe.interval_seconds)
        delay = _detection_delay(probe.interval_seconds, probe.failure_threshold)
        recommended = _recommend_interval(comp, len(dependents))
        findings: list[str] = []
        if quality == IntervalQuality.TOO_FREQUENT:
            findings.append(
                f"Interval {probe.interval_seconds}s generates {cpm:.1f} checks/min; "
                "consider increasing to reduce noise."
            )
        elif quality == IntervalQuality.TOO_INFREQUENT:
            findings.append(
                f"Interval {probe.interval_seconds}s means worst-case detection in "
                f"{delay:.0f}s; consider reducing."
            )
        if nr > 0.7:
            findings.append("High noise risk from frequent checks.")
        return IntervalAnalysis(
            component_id=component_id,
            probe_type=probe.probe_type,
            current_interval=probe.interval_seconds,
            recommended_interval=recommended,
            quality=quality,
            checks_per_minute=cpm,
            noise_risk=nr,
            detection_delay_seconds=delay,
            findings=findings,
        )

    # ------------------------------------------------------------------
    # Cascading health check failure analysis
    # ------------------------------------------------------------------

    def analyze_cascade(
        self,
        graph: InfraGraph,
        component_id: str,
        configs: dict[str, list[HealthCheckProbeConfig]] | None = None,
    ) -> CascadeAnalysis:
        """Analyze cascading health check failures from a component.

        Walks upstream through the dependency graph to find all components
        whose health checks would fail if *component_id* becomes unhealthy.
        """
        affected = self._safe_all_affected(graph, component_id)
        paths = self._safe_cascade_paths(graph, component_id)
        chains: list[CascadeChain] = []
        max_depth = 0
        for path in paths:
            depth = len(path) - 1
            detection_time = self._estimate_chain_detection(
                path, configs or {},
            )
            severity = _severity_from_depth(depth)
            chains.append(CascadeChain(
                root_component_id=component_id,
                chain=path,
                depth=depth,
                estimated_total_detection_seconds=detection_time,
                severity=severity,
            ))
            if depth > max_depth:
                max_depth = depth
        overall_severity = _severity_from_depth(max_depth)
        recommendations: list[str] = []
        if max_depth >= _CASCADE_DEPTH_CRITICAL:
            recommendations.append(
                "Critical cascade depth detected. Add circuit breakers and "
                "separate liveness from readiness probes on intermediary components."
            )
        elif max_depth >= _CASCADE_DEPTH_WARN:
            recommendations.append(
                "Cascade depth is concerning. Consider shallow liveness probes "
                "on upstream components to prevent restart cascades."
            )
        if len(affected) > 3:
            recommendations.append(
                f"{len(affected)} components affected. Use readiness-gated "
                "traffic routing to contain blast radius."
            )
        return CascadeAnalysis(
            component_id=component_id,
            chains=chains,
            max_depth=max_depth,
            total_affected=len(affected),
            severity=overall_severity,
            recommendations=recommendations,
        )

    # ------------------------------------------------------------------
    # Dependency chain analysis
    # ------------------------------------------------------------------

    def analyze_dependency_chain(
        self,
        graph: InfraGraph,
        component_id: str,
        configs: dict[str, list[HealthCheckProbeConfig]] | None = None,
    ) -> DependencyChainAnalysis:
        """Analyze health check dependency chains starting from a component.

        Detects circular dependencies and overly long chains where a
        readiness probe checks a dependency that itself checks back.
        """
        configs = configs or {}
        visited: set[str] = set()
        links: list[DependencyChainLink] = []
        circular = False
        queue = [component_id]
        while queue:
            cid = queue.pop(0)
            if cid in visited:
                circular = True
                continue
            visited.add(cid)
            probes = configs.get(cid, [])
            for probe in probes:
                link = DependencyChainLink(
                    component_id=cid,
                    probe_type=probe.probe_type,
                    depth=probe.depth,
                    checks_component_ids=list(probe.checks_dependencies),
                )
                links.append(link)
                for dep_id in probe.checks_dependencies:
                    if dep_id not in visited:
                        queue.append(dep_id)
                    else:
                        circular = True
        chain_length = len(links)
        severity = Severity.INFO
        recommendations: list[str] = []
        if circular:
            severity = Severity.HIGH
            recommendations.append(
                "Circular health check dependency detected. A readiness probe "
                "checks a dependency whose probe checks back. Break the cycle "
                "by using shallow liveness on one side."
            )
        if chain_length > 5:
            if severity.value < Severity.MEDIUM.value:
                severity = Severity.MEDIUM
            recommendations.append(
                f"Health check dependency chain length {chain_length} is long. "
                "Reduce depth of intermediate probes."
            )
        return DependencyChainAnalysis(
            root_component_id=component_id,
            links=links,
            chain_length=chain_length,
            circular_dependency_detected=circular,
            severity=severity,
            recommendations=recommendations,
        )

    # ------------------------------------------------------------------
    # False-positive rate estimation
    # ------------------------------------------------------------------

    def estimate_false_positive_rate(
        self,
        graph: InfraGraph,
        component_id: str,
        probe: HealthCheckProbeConfig,
    ) -> FalsePositiveEstimate:
        """Estimate the false-positive health check failure rate."""
        comp = graph.get_component(component_id)
        p99 = _estimate_p99_from_component(comp)
        factors: list[str] = []
        timeout_fp = 0.0
        if probe.timeout_seconds < p99:
            timeout_fp = min(50.0, (p99 / probe.timeout_seconds - 1.0) * 20.0)
            factors.append(
                f"Timeout {probe.timeout_seconds}s < p99 {p99:.3f}s induces false positives."
            )
        elif probe.timeout_seconds < p99 * 1.5:
            timeout_fp = 5.0
            factors.append("Timeout marginally above p99; transient spikes may trigger.")
        dep_fp = 0.0
        if probe.checks_dependencies:
            dep_count = len(probe.checks_dependencies)
            dep_fp = min(30.0, dep_count * 5.0)
            factors.append(
                f"Checking {dep_count} dependencies adds transient failure risk."
            )
        network_fp = 0.0
        if comp and comp.network.packet_loss_rate > 0.001:
            network_fp = min(15.0, comp.network.packet_loss_rate * 1000.0)
            factors.append("Elevated packet loss increases false-positive risk.")
        if probe.failure_threshold <= 1:
            timeout_fp *= 1.5
            factors.append("Single-check failure threshold amplifies false positives.")
        total = timeout_fp + dep_fp + network_fp
        total = min(100.0, total)
        if total >= 20.0:
            risk = Severity.HIGH
        elif total >= 10.0:
            risk = Severity.MEDIUM
        elif total >= 3.0:
            risk = Severity.LOW
        else:
            risk = Severity.INFO
        return FalsePositiveEstimate(
            component_id=component_id,
            estimated_rate_percent=round(total, 2),
            timeout_induced_percent=round(timeout_fp, 2),
            dependency_induced_percent=round(dep_fp, 2),
            network_induced_percent=round(network_fp, 2),
            risk_level=risk,
            contributing_factors=factors,
        )

    # ------------------------------------------------------------------
    # Grace period and threshold tuning
    # ------------------------------------------------------------------

    def recommend_grace_period(
        self,
        graph: InfraGraph,
        component_id: str,
        probe: HealthCheckProbeConfig,
    ) -> GracePeriodRecommendation:
        """Recommend grace period and threshold tuning for a probe."""
        comp = graph.get_component(component_id)
        findings: list[str] = []
        rec_grace = probe.grace_period_seconds
        rec_failure = probe.failure_threshold
        rec_success = probe.success_threshold
        if probe.probe_type == ProbeType.STARTUP:
            min_grace = 30.0
            if comp and comp.type == ComponentType.DATABASE:
                min_grace = 60.0
            elif comp and comp.type == ComponentType.APP_SERVER:
                min_grace = 15.0
            if probe.grace_period_seconds < min_grace:
                rec_grace = min_grace
                findings.append(
                    f"Startup grace period {probe.grace_period_seconds}s too short; "
                    f"recommend {min_grace}s."
                )
        elif probe.probe_type == ProbeType.LIVENESS:
            if probe.failure_threshold < 3:
                rec_failure = 3
                findings.append(
                    "Liveness failure threshold < 3 risks killing pods "
                    "during transient issues."
                )
            if probe.initial_delay_seconds < 10.0:
                findings.append(
                    "Liveness initial delay < 10s; consider a startup probe."
                )
        elif probe.probe_type == ProbeType.READINESS:
            if probe.failure_threshold < 2:
                rec_failure = 2
                findings.append(
                    "Readiness failure threshold < 2 causes traffic flapping."
                )
            if probe.success_threshold < 1:
                rec_success = 1
                findings.append("Readiness success threshold should be >= 1.")
        if probe.failure_threshold > 10:
            rec_failure = 5
            findings.append(
                f"Failure threshold {probe.failure_threshold} is very high; "
                "detection will be slow."
            )
        return GracePeriodRecommendation(
            component_id=component_id,
            probe_type=probe.probe_type,
            current_grace_period=probe.grace_period_seconds,
            recommended_grace_period=rec_grace,
            current_failure_threshold=probe.failure_threshold,
            recommended_failure_threshold=rec_failure,
            current_success_threshold=probe.success_threshold,
            recommended_success_threshold=rec_success,
            findings=findings,
        )

    # ------------------------------------------------------------------
    # Endpoint design recommendations
    # ------------------------------------------------------------------

    def recommend_endpoints(
        self,
        graph: InfraGraph,
        component_id: str,
    ) -> EndpointRecommendation:
        """Recommend health check endpoint design for a component."""
        comp = graph.get_component(component_id)
        deps = self._safe_dependencies(graph, component_id)
        findings: list[str] = []
        liveness_ep = "/healthz"
        readiness_ep = "/readyz"
        startup_ep = "/startupz"
        liveness_depth = CheckDepth.SHALLOW
        readiness_depth = CheckDepth.DEPENDENCY_AWARE if deps else CheckDepth.DEEP
        startup_depth = CheckDepth.DEEP
        if comp and comp.type == ComponentType.DATABASE:
            liveness_ep = "/ping"
            readiness_ep = "/ready"
            startup_ep = "/startup"
            liveness_depth = CheckDepth.SHALLOW
            readiness_depth = CheckDepth.DEEP
            findings.append("Database: use /ping for liveness (fast), /ready for readiness.")
        elif comp and comp.type == ComponentType.CACHE:
            liveness_ep = "/ping"
            readiness_ep = "/ready"
            findings.append("Cache: lightweight /ping for liveness.")
        elif comp and comp.type == ComponentType.LOAD_BALANCER:
            liveness_ep = "/healthz"
            readiness_ep = "/readyz"
            findings.append("Load balancer: standard /healthz and /readyz.")
        if deps:
            findings.append(
                f"Component has {len(deps)} dependencies; readiness should check them."
            )
        return EndpointRecommendation(
            component_id=component_id,
            recommended_liveness_endpoint=liveness_ep,
            recommended_readiness_endpoint=readiness_ep,
            recommended_startup_endpoint=startup_ep,
            recommended_liveness_depth=liveness_depth,
            recommended_readiness_depth=readiness_depth,
            recommended_startup_depth=startup_depth,
            findings=findings,
        )

    # ------------------------------------------------------------------
    # Deep vs shallow trade-offs
    # ------------------------------------------------------------------

    def analyze_depth_tradeoff(
        self,
        graph: InfraGraph,
        component_id: str,
        probe: HealthCheckProbeConfig,
    ) -> DepthTradeoff:
        """Analyze trade-offs between deep and shallow health checks."""
        comp = graph.get_component(component_id)
        deps = self._safe_dependencies(graph, component_id)
        p99 = _estimate_p99_from_component(comp)
        shallow_detection = probe.interval_seconds * probe.failure_threshold
        deep_detection = shallow_detection * 0.7
        shallow_fp = 2.0
        deep_fp = 2.0 + len(deps) * 3.0
        shallow_cost = 1.0
        deep_cost = 1.0 + len(deps) * 0.5
        if probe.depth == CheckDepth.SHALLOW:
            if deps:
                recommended = CheckDepth.DEPENDENCY_AWARE
                recommendation = (
                    "Component has dependencies; consider a dependency-aware "
                    "readiness probe to detect downstream failures faster."
                )
            else:
                recommended = CheckDepth.SHALLOW
                recommendation = "No dependencies; shallow check is appropriate."
        elif probe.depth == CheckDepth.DEEP:
            dependents = self._safe_dependents(graph, component_id)
            if len(dependents) > 3:
                recommended = CheckDepth.SHALLOW
                recommendation = (
                    "Deep check on a heavily depended-upon component risks "
                    "cascading restarts. Use shallow liveness + separate readiness."
                )
            else:
                recommended = CheckDepth.DEEP
                recommendation = "Deep check is acceptable given low dependent count."
        else:
            recommended = probe.depth
            recommendation = "Current dependency-aware depth is well-suited."
        return DepthTradeoff(
            component_id=component_id,
            current_depth=probe.depth,
            recommended_depth=recommended,
            shallow_detection_time_seconds=shallow_detection,
            deep_detection_time_seconds=deep_detection,
            shallow_false_positive_rate=shallow_fp,
            deep_false_positive_rate=deep_fp,
            shallow_cost_score=shallow_cost,
            deep_cost_score=deep_cost,
            recommendation=recommendation,
        )

    # ------------------------------------------------------------------
    # Timeout vs response time matching
    # ------------------------------------------------------------------

    def analyze_timeout_alignment(
        self,
        graph: InfraGraph,
        component_id: str,
        probe: HealthCheckProbeConfig,
    ) -> TimeoutAlignment:
        """Analyze alignment between timeout and service response time."""
        comp = graph.get_component(component_id)
        p99 = _estimate_p99_from_component(comp)
        ratio = probe.timeout_seconds / p99 if p99 > 0 else 0.0
        is_aligned = 1.5 <= ratio <= 5.0
        recommended = _recommend_timeout(p99)
        findings: list[str] = []
        if ratio < 1.0:
            findings.append(
                f"Timeout {probe.timeout_seconds}s is shorter than p99 "
                f"response time {p99:.3f}s. Many false positives expected."
            )
        elif ratio < 1.5:
            findings.append(
                "Timeout is slightly above p99; consider a small buffer."
            )
        elif ratio > 10.0:
            findings.append(
                f"Timeout {probe.timeout_seconds}s is >10x p99 {p99:.3f}s. "
                "Failures will take very long to detect."
            )
        elif ratio > 5.0:
            findings.append(
                "Timeout is generous; could be reduced for faster detection."
            )
        return TimeoutAlignment(
            component_id=component_id,
            configured_timeout_seconds=probe.timeout_seconds,
            estimated_p99_response_seconds=round(p99, 4),
            ratio=round(ratio, 2),
            is_aligned=is_aligned,
            recommended_timeout_seconds=round(recommended, 2),
            findings=findings,
        )

    # ------------------------------------------------------------------
    # Blind spot detection
    # ------------------------------------------------------------------

    def detect_blind_spots(
        self,
        graph: InfraGraph,
        configs: dict[str, list[HealthCheckProbeConfig]],
    ) -> BlindSpotReport:
        """Detect health check monitoring blind spots across the graph."""
        blind_spots: list[BlindSpot] = []
        total = len(graph.components)
        covered_ids: set[str] = set()
        for comp_id, comp in graph.components.items():
            probes = configs.get(comp_id, [])
            if not probes:
                blind_spots.append(BlindSpot(
                    component_id=comp_id,
                    category=BlindSpotCategory.UNCHECKED_COMPONENT,
                    severity=Severity.HIGH,
                    description=f"Component {comp_id} has no health check probes.",
                    recommendation="Add at least a liveness probe.",
                ))
                continue
            covered_ids.add(comp_id)
            probe_types = {p.probe_type for p in probes}
            if ProbeType.LIVENESS not in probe_types:
                blind_spots.append(BlindSpot(
                    component_id=comp_id,
                    category=BlindSpotCategory.NO_LIVENESS_PROBE,
                    severity=Severity.MEDIUM,
                    description=f"Component {comp_id} has no liveness probe.",
                    recommendation="Add a lightweight liveness probe.",
                ))
            if ProbeType.READINESS not in probe_types:
                blind_spots.append(BlindSpot(
                    component_id=comp_id,
                    category=BlindSpotCategory.NO_READINESS_PROBE,
                    severity=Severity.MEDIUM,
                    description=f"Component {comp_id} has no readiness probe.",
                    recommendation="Add a readiness probe to control traffic routing.",
                ))
            if ProbeType.STARTUP not in probe_types:
                blind_spots.append(BlindSpot(
                    component_id=comp_id,
                    category=BlindSpotCategory.NO_STARTUP_PROBE,
                    severity=Severity.LOW,
                    description=f"Component {comp_id} has no startup probe.",
                    recommendation="Add a startup probe for slow-starting services.",
                ))
            deps = self._safe_dependencies(graph, comp_id)
            if deps:
                has_dep_check = any(
                    p.depth == CheckDepth.DEPENDENCY_AWARE or len(p.checks_dependencies) > 0
                    for p in probes
                )
                if not has_dep_check:
                    blind_spots.append(BlindSpot(
                        component_id=comp_id,
                        category=BlindSpotCategory.MISSING_DEPENDENCY_CHECK,
                        severity=Severity.MEDIUM,
                        description=(
                            f"Component {comp_id} has {len(deps)} dependencies "
                            "but no probe checks them."
                        ),
                        recommendation="Add dependency checks to readiness probe.",
                    ))
            p99 = _estimate_p99_from_component(comp)
            for p in probes:
                if p.timeout_seconds < p99:
                    blind_spots.append(BlindSpot(
                        component_id=comp_id,
                        category=BlindSpotCategory.TIMEOUT_MISMATCH,
                        severity=Severity.HIGH,
                        description=(
                            f"Timeout {p.timeout_seconds}s < estimated p99 "
                            f"{p99:.3f}s for {p.probe_type.value} probe."
                        ),
                        recommendation="Increase timeout to at least 2x p99.",
                    ))
                    break
            protocols = {p.protocol for p in probes}
            if len(protocols) == 1 and ProbeProtocol.TCP_SOCKET in protocols:
                blind_spots.append(BlindSpot(
                    component_id=comp_id,
                    category=BlindSpotCategory.SINGLE_PROTOCOL,
                    severity=Severity.LOW,
                    description=(
                        f"Component {comp_id} uses only TCP probes; "
                        "application-level issues may be missed."
                    ),
                    recommendation="Add an HTTP or gRPC probe for application health.",
                ))
            has_grace = any(
                p.grace_period_seconds > 0 or p.initial_delay_seconds > 0
                for p in probes
            )
            if not has_grace:
                blind_spots.append(BlindSpot(
                    component_id=comp_id,
                    category=BlindSpotCategory.NO_GRACE_PERIOD,
                    severity=Severity.LOW,
                    description=(
                        f"Component {comp_id} has no grace period or initial delay."
                    ),
                    recommendation="Add initial delay or startup probe grace period.",
                ))
        coverage = len(covered_ids) / total if total > 0 else 0.0
        severity_counts: dict[str, int] = {}
        for bs in blind_spots:
            key = bs.severity.value
            severity_counts[key] = severity_counts.get(key, 0) + 1
        return BlindSpotReport(
            blind_spots=blind_spots,
            coverage_ratio=round(coverage, 4),
            total_components=total,
            covered_components=len(covered_ids),
            severity_counts=severity_counts,
        )

    # ------------------------------------------------------------------
    # Service mesh health check integration
    # ------------------------------------------------------------------

    def analyze_service_mesh_integration(
        self,
        graph: InfraGraph,
        component_id: str,
        probe: HealthCheckProbeConfig,
        mesh_type: ServiceMeshType = ServiceMeshType.NONE,
        sidecar_timeout_seconds: float = 0.0,
        mesh_retry_enabled: bool = False,
        mesh_circuit_breaker_enabled: bool = False,
    ) -> ServiceMeshHealthAnalysis:
        """Analyze service mesh health check integration for a component."""
        comp = graph.get_component(component_id)
        findings: list[str] = []
        if mesh_type == ServiceMeshType.NONE:
            return ServiceMeshHealthAnalysis(
                component_id=component_id,
                mesh_type=mesh_type,
                findings=["No service mesh detected."],
            )
        sidecar_aligned = True
        if sidecar_timeout_seconds > 0:
            if abs(sidecar_timeout_seconds - probe.timeout_seconds) > 2.0:
                sidecar_aligned = False
                findings.append(
                    f"Sidecar timeout {sidecar_timeout_seconds}s differs from "
                    f"app probe timeout {probe.timeout_seconds}s by >2s."
                )
        mtls_impact = 0.0
        if mesh_type in (ServiceMeshType.ISTIO, ServiceMeshType.LINKERD):
            mtls_impact = 0.05
            findings.append(
                f"mTLS overhead estimated at {mtls_impact}s for {mesh_type.value}."
            )
        retry_overlap = False
        if mesh_retry_enabled:
            dep_edge = None
            deps = self._safe_dependencies(graph, component_id)
            for d in deps:
                edge = graph.get_dependency_edge(component_id, d.id)
                if edge and edge.retry_strategy.enabled:
                    retry_overlap = True
                    break
            if retry_overlap:
                findings.append(
                    "Both mesh-level and app-level retries are enabled; "
                    "this can cause retry storms."
                )
        cb_conflict = False
        if mesh_circuit_breaker_enabled:
            deps = self._safe_dependencies(graph, component_id)
            for d in deps:
                edge = graph.get_dependency_edge(component_id, d.id)
                if edge and edge.circuit_breaker.enabled:
                    cb_conflict = True
                    break
            if cb_conflict:
                findings.append(
                    "Both mesh and app circuit breakers are configured. "
                    "Ensure thresholds are aligned to prevent conflict."
                )
        return ServiceMeshHealthAnalysis(
            component_id=component_id,
            mesh_type=mesh_type,
            sidecar_probe_aligned=sidecar_aligned,
            mtls_health_impact=mtls_impact,
            retry_overlap_detected=retry_overlap,
            circuit_breaker_conflict=cb_conflict,
            findings=findings,
        )

    # ------------------------------------------------------------------
    # Custom scoring rubric
    # ------------------------------------------------------------------

    def score_component(
        self,
        graph: InfraGraph,
        component_id: str,
        probes: list[HealthCheckProbeConfig],
        mesh_analysis: ServiceMeshHealthAnalysis | None = None,
    ) -> HealthCheckScorecard:
        """Score a component's health check configuration using a rubric."""
        comp = graph.get_component(component_id)
        deps = self._safe_dependencies(graph, component_id)
        cascade = self.analyze_cascade(graph, component_id)
        rubrics: list[RubricScore] = [
            _probe_coverage_score(probes),
            _interval_tuning_score(probes),
            _timeout_alignment_score(probes, comp),
            _threshold_tuning_score(probes),
            _depth_strategy_score(probes),
            _grace_period_score(probes),
            _dependency_awareness_score(probes, len(deps)),
            _cascade_safety_score(cascade),
            _endpoint_design_score(probes),
            _mesh_integration_score(mesh_analysis),
        ]
        total_weighted = sum(r.score * r.weight for r in rubrics)
        total_max_weighted = sum(r.max_score * r.weight for r in rubrics)
        if total_max_weighted > 0:
            normalized = (total_weighted / total_max_weighted) * _MAX_RUBRIC_SCORE
        else:
            normalized = 0.0
        normalized = _clamp(normalized, 0.0, _MAX_RUBRIC_SCORE)
        grade = _grade_from_score(normalized)
        all_findings: list[str] = []
        for r in rubrics:
            all_findings.extend(r.findings)
        recommendations: list[str] = []
        for r in rubrics:
            if r.score < r.max_score * 0.5:
                recommendations.append(
                    f"Improve {r.category.value}: scored {r.score:.1f}/{r.max_score:.1f}."
                )
        ts = datetime.now(timezone.utc).isoformat()
        return HealthCheckScorecard(
            component_id=component_id,
            overall_score=round(normalized, 1),
            max_possible_score=_MAX_RUBRIC_SCORE,
            grade=grade,
            rubric_scores=rubrics,
            timestamp=ts,
            recommendations=recommendations,
        )

    # ------------------------------------------------------------------
    # Full strategy report
    # ------------------------------------------------------------------

    def generate_report(
        self,
        graph: InfraGraph,
        configs: dict[str, list[HealthCheckProbeConfig]],
        mesh_analyses: dict[str, ServiceMeshHealthAnalysis] | None = None,
    ) -> StrategyReport:
        """Generate a comprehensive health check strategy report."""
        mesh_analyses = mesh_analyses or {}
        scorecards: list[HealthCheckScorecard] = []
        cascade_list: list[CascadeAnalysis] = []
        interval_list: list[IntervalAnalysis] = []
        for comp_id in graph.components:
            probes = configs.get(comp_id, [])
            sc = self.score_component(
                graph, comp_id, probes, mesh_analyses.get(comp_id),
            )
            scorecards.append(sc)
            ca = self.analyze_cascade(graph, comp_id, configs)
            cascade_list.append(ca)
            for probe in probes:
                ia = self.analyze_interval(graph, comp_id, probe)
                interval_list.append(ia)
        blind_spots = self.detect_blind_spots(graph, configs)
        scores = [sc.overall_score for sc in scorecards] if scorecards else [0.0]
        overall = sum(scores) / len(scores)
        top_recs: list[str] = []
        for sc in sorted(scorecards, key=lambda s: s.overall_score):
            for rec in sc.recommendations[:2]:
                if rec not in top_recs:
                    top_recs.append(rec)
                if len(top_recs) >= 10:
                    break
            if len(top_recs) >= 10:
                break
        if blind_spots.coverage_ratio < _BLIND_SPOT_COVERAGE_THRESHOLD:
            top_recs.insert(
                0,
                f"Only {blind_spots.coverage_ratio:.0%} of components have health "
                "checks. Add probes to unchecked components."
            )
        ts = datetime.now(timezone.utc).isoformat()
        return StrategyReport(
            graph_id="infra",
            timestamp=ts,
            scorecards=scorecards,
            cascade_analysis=cascade_list,
            blind_spot_report=blind_spots,
            interval_analyses=interval_list,
            overall_health_score=round(overall, 1),
            top_recommendations=top_recs,
        )

    # ------------------------------------------------------------------
    # Probe differentiation helper
    # ------------------------------------------------------------------

    def differentiate_probes(
        self,
        graph: InfraGraph,
        component_id: str,
    ) -> list[HealthCheckProbeConfig]:
        """Generate differentiated liveness, readiness, and startup probes."""
        comp = graph.get_component(component_id)
        deps = self._safe_dependencies(graph, component_id)
        dependents = self._safe_dependents(graph, component_id)
        dep_ids = [d.id for d in deps]
        ep_rec = self.recommend_endpoints(graph, component_id)
        liveness_interval = 10.0
        readiness_interval = 10.0
        if len(dependents) > 5:
            liveness_interval = 15.0
            readiness_interval = 20.0
        p99 = _estimate_p99_from_component(comp)
        timeout = _recommend_timeout(p99)
        protocol = ProbeProtocol.HTTP_GET
        if comp and comp.type in (ComponentType.DATABASE, ComponentType.CACHE):
            protocol = ProbeProtocol.TCP_SOCKET
        port = comp.port if comp and comp.port else 8080
        liveness = HealthCheckProbeConfig(
            probe_type=ProbeType.LIVENESS,
            protocol=protocol,
            endpoint=ep_rec.recommended_liveness_endpoint,
            port=port,
            interval_seconds=liveness_interval,
            timeout_seconds=timeout,
            failure_threshold=3,
            success_threshold=1,
            initial_delay_seconds=0.0,
            grace_period_seconds=0.0,
            depth=CheckDepth.SHALLOW,
            checks_dependencies=[],
        )
        readiness = HealthCheckProbeConfig(
            probe_type=ProbeType.READINESS,
            protocol=protocol,
            endpoint=ep_rec.recommended_readiness_endpoint,
            port=port,
            interval_seconds=readiness_interval,
            timeout_seconds=timeout,
            failure_threshold=2,
            success_threshold=1,
            initial_delay_seconds=5.0,
            grace_period_seconds=0.0,
            depth=ep_rec.recommended_readiness_depth,
            checks_dependencies=dep_ids if deps else [],
        )
        startup = HealthCheckProbeConfig(
            probe_type=ProbeType.STARTUP,
            protocol=protocol,
            endpoint=ep_rec.recommended_startup_endpoint,
            port=port,
            interval_seconds=5.0,
            timeout_seconds=timeout,
            failure_threshold=30,
            success_threshold=1,
            initial_delay_seconds=0.0,
            grace_period_seconds=30.0,
            depth=CheckDepth.DEEP,
            checks_dependencies=[],
        )
        return [liveness, readiness, startup]

    # ------------------------------------------------------------------
    # Batch analysis helpers
    # ------------------------------------------------------------------

    def analyze_all_intervals(
        self,
        graph: InfraGraph,
        configs: dict[str, list[HealthCheckProbeConfig]],
    ) -> list[IntervalAnalysis]:
        """Analyze intervals for all configured probes."""
        results: list[IntervalAnalysis] = []
        for comp_id, probes in configs.items():
            for probe in probes:
                results.append(self.analyze_interval(graph, comp_id, probe))
        return results

    def estimate_all_false_positives(
        self,
        graph: InfraGraph,
        configs: dict[str, list[HealthCheckProbeConfig]],
    ) -> list[FalsePositiveEstimate]:
        """Estimate false-positive rates for all configured probes."""
        results: list[FalsePositiveEstimate] = []
        for comp_id, probes in configs.items():
            for probe in probes:
                results.append(
                    self.estimate_false_positive_rate(graph, comp_id, probe)
                )
        return results

    def recommend_all_grace_periods(
        self,
        graph: InfraGraph,
        configs: dict[str, list[HealthCheckProbeConfig]],
    ) -> list[GracePeriodRecommendation]:
        """Recommend grace periods for all configured probes."""
        results: list[GracePeriodRecommendation] = []
        for comp_id, probes in configs.items():
            for probe in probes:
                results.append(
                    self.recommend_grace_period(graph, comp_id, probe)
                )
        return results

    def analyze_all_depth_tradeoffs(
        self,
        graph: InfraGraph,
        configs: dict[str, list[HealthCheckProbeConfig]],
    ) -> list[DepthTradeoff]:
        """Analyze depth trade-offs for all configured probes."""
        results: list[DepthTradeoff] = []
        for comp_id, probes in configs.items():
            for probe in probes:
                results.append(
                    self.analyze_depth_tradeoff(graph, comp_id, probe)
                )
        return results

    def analyze_all_timeout_alignments(
        self,
        graph: InfraGraph,
        configs: dict[str, list[HealthCheckProbeConfig]],
    ) -> list[TimeoutAlignment]:
        """Analyze timeout alignment for all configured probes."""
        results: list[TimeoutAlignment] = []
        for comp_id, probes in configs.items():
            for probe in probes:
                results.append(
                    self.analyze_timeout_alignment(graph, comp_id, probe)
                )
        return results

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_dependents(graph: InfraGraph, cid: str) -> list[Component]:
        if cid not in graph.components:
            return []
        return graph.get_dependents(cid)

    @staticmethod
    def _safe_dependencies(graph: InfraGraph, cid: str) -> list[Component]:
        if cid not in graph.components:
            return []
        return graph.get_dependencies(cid)

    @staticmethod
    def _safe_all_affected(graph: InfraGraph, cid: str) -> set[str]:
        if cid not in graph.components:
            return set()
        return graph.get_all_affected(cid)

    @staticmethod
    def _safe_cascade_paths(graph: InfraGraph, cid: str) -> list[list[str]]:
        if cid not in graph.components:
            return []
        return graph.get_cascade_path(cid)

    def _estimate_chain_detection(
        self,
        chain: list[str],
        configs: dict[str, list[HealthCheckProbeConfig]],
    ) -> float:
        """Estimate total detection time along a cascade chain."""
        total = 0.0
        for cid in chain:
            probes = configs.get(cid, [])
            if probes:
                best = min(
                    _detection_delay(p.interval_seconds, p.failure_threshold)
                    for p in probes
                )
                total += best
            else:
                total += 30.0
        return total
