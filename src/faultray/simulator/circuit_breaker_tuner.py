"""Circuit Breaker Tuner -- analysis and optimisation of circuit breaker configurations.

Analyses circuit breaker parameters across service dependency graphs.  Provides
failure-threshold optimisation from historical error rates, recovery-timeout
tuning via service recovery patterns, half-open request budget calculation,
cascading breaker coordination, false-positive / false-negative trip risk
analysis, retry-policy interaction, bulkhead integration, state-machine
simulation, optimal placement detection, monitoring-gap detection,
thundering-herd risk after recovery, success-rate threshold recommendations,
and circuit-breaker testing-coverage analysis.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from faultray.model.components import (
    CircuitBreakerConfig,
    ComponentType,
)
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Severity(str, Enum):
    """Issue severity levels."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class BreakerState(str, Enum):
    """Circuit breaker state-machine states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class RiskCategory(str, Enum):
    """Risk categories for circuit breaker analysis."""

    FALSE_POSITIVE = "false_positive"
    FALSE_NEGATIVE = "false_negative"
    THUNDERING_HERD = "thundering_herd"
    CASCADE_FAILURE = "cascade_failure"
    MONITORING_GAP = "monitoring_gap"
    RETRY_INTERACTION = "retry_interaction"
    BULKHEAD_MISMATCH = "bulkhead_mismatch"


class PlacementStrategy(str, Enum):
    """Strategies for circuit breaker placement in a service mesh."""

    CLIENT_SIDE = "client_side"
    SERVER_SIDE = "server_side"
    SIDECAR = "sidecar"
    MESH_LEVEL = "mesh_level"


class TestCoverageLevel(str, Enum):
    """How thoroughly a circuit breaker has been tested."""

    NONE = "none"
    BASIC = "basic"
    MODERATE = "moderate"
    COMPREHENSIVE = "comprehensive"


# ---------------------------------------------------------------------------
# Data classes -- result models
# ---------------------------------------------------------------------------


@dataclass
class ErrorRateSnapshot:
    """Historical error-rate snapshot for a dependency."""

    source_id: str
    target_id: str
    error_rate: float  # 0.0 - 1.0
    sample_window_seconds: float = 60.0
    sample_count: int = 0


@dataclass
class ThresholdRecommendation:
    """Recommended failure-threshold for a circuit breaker."""

    source_id: str
    target_id: str
    current_threshold: int
    recommended_threshold: int
    error_rate: float
    rationale: str


@dataclass
class RecoveryPattern:
    """Observed recovery pattern for a service."""

    component_id: str
    mean_recovery_seconds: float
    p95_recovery_seconds: float
    recovery_variance: float
    sample_count: int = 0


@dataclass
class RecoveryTimeoutRecommendation:
    """Recommended recovery timeout for a circuit breaker."""

    source_id: str
    target_id: str
    current_timeout_seconds: float
    recommended_timeout_seconds: float
    recovery_pattern: RecoveryPattern
    rationale: str


@dataclass
class HalfOpenBudget:
    """Calculated half-open request budget."""

    source_id: str
    target_id: str
    current_max_requests: int
    recommended_max_requests: int
    success_threshold: int
    expected_success_rate: float
    rationale: str


@dataclass
class CascadeLink:
    """A single link in a cascading breaker chain."""

    source_id: str
    target_id: str
    breaker_enabled: bool
    failure_threshold: int
    recovery_timeout_seconds: float
    will_cascade: bool


@dataclass
class CascadeAnalysis:
    """Analysis of cascading circuit breaker behaviour along a path."""

    path: list[str]
    links: list[CascadeLink]
    cascade_depth: int
    total_recovery_seconds: float
    has_unprotected_link: bool
    severity: Severity


@dataclass
class FalsePositiveRisk:
    """Risk of a circuit breaker tripping when the service is healthy."""

    source_id: str
    target_id: str
    risk_score: float  # 0.0 - 1.0
    contributing_factors: list[str]
    severity: Severity
    recommendation: str


@dataclass
class FalseNegativeRisk:
    """Risk of a circuit breaker remaining closed during an actual outage."""

    source_id: str
    target_id: str
    risk_score: float  # 0.0 - 1.0
    contributing_factors: list[str]
    severity: Severity
    recommendation: str


@dataclass
class RetryBreakerInteraction:
    """Analysis of interaction between retry policies and circuit breakers."""

    source_id: str
    target_id: str
    retry_enabled: bool
    breaker_enabled: bool
    retries_before_trip: int
    total_attempts_before_trip: int
    amplification_factor: float
    risk_description: str
    severity: Severity


@dataclass
class BulkheadConfig:
    """Bulkhead configuration for a dependency."""

    source_id: str
    target_id: str
    max_concurrent: int = 10
    max_queue_size: int = 20
    queue_timeout_ms: float = 1000.0


@dataclass
class BulkheadBreakerIntegration:
    """Analysis of bulkhead + circuit breaker interaction."""

    source_id: str
    target_id: str
    bulkhead_max_concurrent: int
    breaker_failure_threshold: int
    saturation_trips_breaker: bool
    queue_timeout_triggers_failure: bool
    recommendation: str
    severity: Severity


@dataclass
class StateTransition:
    """A single state transition in a circuit breaker simulation."""

    time_seconds: float
    from_state: BreakerState
    to_state: BreakerState
    trigger: str
    failure_count: int
    success_count: int


@dataclass
class SimulationResult:
    """Result of simulating a circuit breaker state machine."""

    source_id: str
    target_id: str
    transitions: list[StateTransition]
    total_time_seconds: float
    time_in_open_seconds: float
    time_in_closed_seconds: float
    time_in_half_open_seconds: float
    availability_ratio: float
    trip_count: int


@dataclass
class PlacementRecommendation:
    """Recommended circuit breaker placement for a dependency."""

    source_id: str
    target_id: str
    recommended_strategy: PlacementStrategy
    current_has_breaker: bool
    dependency_type: str
    fan_out: int
    rationale: str


@dataclass
class MonitoringGap:
    """Detected monitoring gap for a circuit breaker."""

    source_id: str
    target_id: str
    gap_type: str
    description: str
    severity: Severity
    recommendation: str


@dataclass
class ThunderingHerdRisk:
    """Risk of thundering herd after circuit breaker recovery."""

    source_id: str
    target_id: str
    queued_request_estimate: int
    recovery_burst_ratio: float
    target_max_rps: int
    will_overwhelm: bool
    severity: Severity
    recommendation: str


@dataclass
class SuccessRateRecommendation:
    """Recommended success-rate threshold for half-open to closed transition."""

    source_id: str
    target_id: str
    current_success_threshold: int
    recommended_success_threshold: int
    current_half_open_requests: int
    recommended_success_rate: float
    rationale: str


@dataclass
class TestCoverageResult:
    """Circuit breaker testing coverage analysis."""

    source_id: str
    target_id: str
    coverage_level: TestCoverageLevel
    tested_states: list[BreakerState]
    missing_tests: list[str]
    coverage_score: float  # 0.0 - 1.0
    recommendation: str


@dataclass
class CircuitBreakerTuningReport:
    """Comprehensive circuit breaker tuning report."""

    generated_at: datetime
    total_dependencies: int
    breaker_enabled_count: int
    threshold_recommendations: list[ThresholdRecommendation]
    recovery_timeout_recommendations: list[RecoveryTimeoutRecommendation]
    half_open_budgets: list[HalfOpenBudget]
    cascade_analyses: list[CascadeAnalysis]
    false_positive_risks: list[FalsePositiveRisk]
    false_negative_risks: list[FalseNegativeRisk]
    retry_interactions: list[RetryBreakerInteraction]
    bulkhead_integrations: list[BulkheadBreakerIntegration]
    simulation_results: list[SimulationResult]
    placement_recommendations: list[PlacementRecommendation]
    monitoring_gaps: list[MonitoringGap]
    thundering_herd_risks: list[ThunderingHerdRisk]
    success_rate_recommendations: list[SuccessRateRecommendation]
    test_coverage_results: list[TestCoverageResult]
    overall_health: Severity
    recommendations: list[str]


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------


class CircuitBreakerTuner:
    """Analyses and optimises circuit breaker configurations across a service graph."""

    def __init__(self, graph: InfraGraph) -> None:
        self._graph = graph
        self._error_rates: dict[tuple[str, str], ErrorRateSnapshot] = {}
        self._recovery_patterns: dict[str, RecoveryPattern] = {}
        self._bulkhead_configs: dict[tuple[str, str], BulkheadConfig] = {}
        self._test_coverage: dict[tuple[str, str], list[str]] = {}
        self._request_rates: dict[str, float] = {}

    # -- configuration helpers ------------------------------------------------

    def set_error_rate(self, snapshot: ErrorRateSnapshot) -> None:
        """Register an error-rate snapshot for a dependency."""
        self._error_rates[(snapshot.source_id, snapshot.target_id)] = snapshot

    def get_error_rate(self, source_id: str, target_id: str) -> ErrorRateSnapshot | None:
        """Return the error-rate snapshot for a dependency, if set."""
        return self._error_rates.get((source_id, target_id))

    def set_recovery_pattern(self, pattern: RecoveryPattern) -> None:
        """Register a recovery pattern for a component."""
        self._recovery_patterns[pattern.component_id] = pattern

    def get_recovery_pattern(self, component_id: str) -> RecoveryPattern | None:
        """Return recovery pattern for a component, if set."""
        return self._recovery_patterns.get(component_id)

    def set_bulkhead_config(self, config: BulkheadConfig) -> None:
        """Register a bulkhead configuration for a dependency."""
        self._bulkhead_configs[(config.source_id, config.target_id)] = config

    def get_bulkhead_config(self, source_id: str, target_id: str) -> BulkheadConfig | None:
        """Return bulkhead config for a dependency, if set."""
        return self._bulkhead_configs.get((source_id, target_id))

    def set_test_coverage(self, source_id: str, target_id: str, tested_aspects: list[str]) -> None:
        """Register tested aspects for a circuit breaker."""
        self._test_coverage[(source_id, target_id)] = tested_aspects

    def set_request_rate(self, component_id: str, rps: float) -> None:
        """Set the request rate (requests per second) for a component."""
        self._request_rates[component_id] = rps

    def get_request_rate(self, component_id: str) -> float:
        """Return the request rate for a component, with default."""
        if component_id in self._request_rates:
            return self._request_rates[component_id]
        comp = self._graph.get_component(component_id)
        if comp:
            return float(comp.capacity.max_rps)
        return 100.0

    # -- core analyses --------------------------------------------------------

    def optimize_failure_thresholds(self) -> list[ThresholdRecommendation]:
        """Optimise failure thresholds based on historical error rates."""
        results: list[ThresholdRecommendation] = []
        for dep in self._graph.all_dependency_edges():
            cb: CircuitBreakerConfig = dep.circuit_breaker
            snapshot = self._error_rates.get((dep.source_id, dep.target_id))

            if snapshot is None:
                # No data -- use a conservative heuristic
                error_rate = 0.01
            else:
                error_rate = snapshot.error_rate

            current = cb.failure_threshold

            # Recommended threshold: inversely related to error rate.
            # High error rates -> lower threshold (trip sooner).
            # Low error rates -> higher threshold (avoid false trips).
            if error_rate >= 0.5:
                recommended = max(2, int(3 * (1.0 - error_rate) + 1))
            elif error_rate >= 0.1:
                recommended = max(3, int(5 * (1.0 - error_rate)))
            elif error_rate >= 0.01:
                recommended = max(5, int(10 * (1.0 - error_rate)))
            else:
                recommended = max(8, int(15 * (1.0 - error_rate)))

            if error_rate >= 0.5:
                rationale = (
                    f"High error rate ({error_rate:.1%}) warrants aggressive threshold "
                    f"of {recommended} to trip quickly."
                )
            elif error_rate >= 0.1:
                rationale = (
                    f"Moderate error rate ({error_rate:.1%}) suggests threshold "
                    f"of {recommended} for balanced protection."
                )
            elif error_rate >= 0.01:
                rationale = (
                    f"Low error rate ({error_rate:.1%}) allows higher threshold "
                    f"of {recommended} to avoid false trips."
                )
            else:
                rationale = (
                    f"Very low error rate ({error_rate:.2%}) -- threshold "
                    f"of {recommended} minimises false-positive trips."
                )

            results.append(
                ThresholdRecommendation(
                    source_id=dep.source_id,
                    target_id=dep.target_id,
                    current_threshold=current,
                    recommended_threshold=recommended,
                    error_rate=error_rate,
                    rationale=rationale,
                )
            )
        return results

    def tune_recovery_timeouts(self) -> list[RecoveryTimeoutRecommendation]:
        """Tune recovery timeouts based on service recovery patterns."""
        results: list[RecoveryTimeoutRecommendation] = []
        for dep in self._graph.all_dependency_edges():
            cb: CircuitBreakerConfig = dep.circuit_breaker
            pattern = self._recovery_patterns.get(dep.target_id)

            if pattern is None:
                # Create a default pattern
                pattern = RecoveryPattern(
                    component_id=dep.target_id,
                    mean_recovery_seconds=30.0,
                    p95_recovery_seconds=60.0,
                    recovery_variance=10.0,
                    sample_count=0,
                )

            current = cb.recovery_timeout_seconds

            # Recommended: p95 recovery time * 1.2 safety margin, minimum 10s
            recommended = max(10.0, pattern.p95_recovery_seconds * 1.2)

            # If variance is high, add extra buffer
            if pattern.recovery_variance > pattern.mean_recovery_seconds * 0.5:
                recommended *= 1.3
                rationale = (
                    f"High recovery variance ({pattern.recovery_variance:.1f}s) for "
                    f"{dep.target_id}. Using p95 ({pattern.p95_recovery_seconds:.1f}s) "
                    f"* 1.56 safety margin = {recommended:.1f}s."
                )
            elif pattern.sample_count == 0:
                rationale = (
                    f"No recovery data for {dep.target_id}. "
                    f"Using default estimate of {recommended:.1f}s."
                )
            else:
                rationale = (
                    f"Based on {pattern.sample_count} recovery samples for "
                    f"{dep.target_id}. p95={pattern.p95_recovery_seconds:.1f}s, "
                    f"recommended={recommended:.1f}s."
                )

            results.append(
                RecoveryTimeoutRecommendation(
                    source_id=dep.source_id,
                    target_id=dep.target_id,
                    current_timeout_seconds=current,
                    recommended_timeout_seconds=round(recommended, 1),
                    recovery_pattern=pattern,
                    rationale=rationale,
                )
            )
        return results

    def calculate_half_open_budgets(self) -> list[HalfOpenBudget]:
        """Calculate optimal half-open request budgets."""
        results: list[HalfOpenBudget] = []
        for dep in self._graph.all_dependency_edges():
            cb: CircuitBreakerConfig = dep.circuit_breaker
            snapshot = self._error_rates.get((dep.source_id, dep.target_id))

            if snapshot is not None:
                expected_success = 1.0 - snapshot.error_rate
            else:
                expected_success = 0.8  # conservative default

            current_max = cb.half_open_max_requests
            success_threshold = cb.success_threshold

            # Need enough requests so that success_threshold successes are likely.
            # If expected success rate is p, we need n requests such that
            # P(successes >= success_threshold) is high.
            if expected_success > 0:
                # Expected requests needed = success_threshold / expected_success
                recommended = max(
                    success_threshold,
                    int(success_threshold / expected_success + 0.5),
                )
                # Add buffer for safety
                recommended = max(recommended, success_threshold + 1)
            else:
                # Service is expected to be down -- minimal budget
                recommended = max(1, success_threshold)

            # Cap at reasonable maximum
            recommended = min(recommended, 20)

            if expected_success >= 0.9:
                rationale = (
                    f"High expected success rate ({expected_success:.0%}). "
                    f"{recommended} half-open requests should suffice to observe "
                    f"{success_threshold} successes."
                )
            elif expected_success >= 0.5:
                rationale = (
                    f"Moderate expected success rate ({expected_success:.0%}). "
                    f"{recommended} half-open requests provides enough samples "
                    f"to confirm recovery."
                )
            else:
                rationale = (
                    f"Low expected success rate ({expected_success:.0%}). "
                    f"Minimal budget of {recommended} to probe without overload."
                )

            results.append(
                HalfOpenBudget(
                    source_id=dep.source_id,
                    target_id=dep.target_id,
                    current_max_requests=current_max,
                    recommended_max_requests=recommended,
                    success_threshold=success_threshold,
                    expected_success_rate=round(expected_success, 4),
                    rationale=rationale,
                )
            )
        return results

    def analyze_cascading_breakers(self) -> list[CascadeAnalysis]:
        """Analyse cascading circuit breaker behaviour across dependency chains."""
        results: list[CascadeAnalysis] = []
        paths = self._graph.get_critical_paths(max_paths=100)
        if not paths:
            paths = [[cid] for cid in self._graph.components]

        for path in paths:
            if len(path) < 2:
                continue

            links: list[CascadeLink] = []
            total_recovery = 0.0
            cascade_depth = 0
            has_unprotected = False

            for i in range(len(path) - 1):
                src, tgt = path[i], path[i + 1]
                dep = self._graph.get_dependency_edge(src, tgt)
                if dep is None:
                    links.append(
                        CascadeLink(
                            source_id=src,
                            target_id=tgt,
                            breaker_enabled=False,
                            failure_threshold=0,
                            recovery_timeout_seconds=0.0,
                            will_cascade=True,
                        )
                    )
                    has_unprotected = True
                    continue

                cb = dep.circuit_breaker
                will_cascade = not cb.enabled or dep.dependency_type == "requires"

                if cb.enabled:
                    total_recovery += cb.recovery_timeout_seconds
                    if will_cascade:
                        cascade_depth += 1
                else:
                    has_unprotected = True
                    if dep.dependency_type == "requires":
                        cascade_depth += 1

                links.append(
                    CascadeLink(
                        source_id=src,
                        target_id=tgt,
                        breaker_enabled=cb.enabled,
                        failure_threshold=cb.failure_threshold,
                        recovery_timeout_seconds=cb.recovery_timeout_seconds,
                        will_cascade=will_cascade,
                    )
                )

            if cascade_depth >= 3 or (has_unprotected and cascade_depth >= 2):
                severity = Severity.CRITICAL
            elif cascade_depth >= 2 or has_unprotected:
                severity = Severity.WARNING
            else:
                severity = Severity.INFO

            results.append(
                CascadeAnalysis(
                    path=list(path),
                    links=links,
                    cascade_depth=cascade_depth,
                    total_recovery_seconds=round(total_recovery, 1),
                    has_unprotected_link=has_unprotected,
                    severity=severity,
                )
            )
        return results

    def assess_false_positive_risk(self) -> list[FalsePositiveRisk]:
        """Assess risk of breakers tripping on healthy services (false positives)."""
        results: list[FalsePositiveRisk] = []
        for dep in self._graph.all_dependency_edges():
            cb = dep.circuit_breaker
            if not cb.enabled:
                continue

            factors: list[str] = []
            risk = 0.0

            # Low failure threshold increases false-positive risk
            if cb.failure_threshold <= 2:
                risk += 0.35
                factors.append(
                    f"Very low failure threshold ({cb.failure_threshold}) -- "
                    "transient errors may trip the breaker."
                )
            elif cb.failure_threshold <= 3:
                risk += 0.2
                factors.append(
                    f"Low failure threshold ({cb.failure_threshold}) increases "
                    "sensitivity to transient errors."
                )

            # Network jitter can cause spurious timeouts
            target = self._graph.get_component(dep.target_id)
            if target and target.network.jitter_ms > 5.0:
                risk += 0.15
                factors.append(
                    f"High network jitter ({target.network.jitter_ms:.1f}ms) "
                    "may cause spurious timeout failures."
                )

            # Retry policy amplifies failure count
            if dep.retry_strategy.enabled and dep.retry_strategy.max_retries >= 3:
                risk += 0.1
                factors.append(
                    f"Retry policy ({dep.retry_strategy.max_retries} retries) "
                    "can amplify failure counts towards threshold."
                )

            # Short recovery timeout may not allow transient issues to clear
            if cb.recovery_timeout_seconds < 10.0:
                risk += 0.1
                factors.append(
                    f"Short recovery timeout ({cb.recovery_timeout_seconds:.0f}s) "
                    "may cycle rapidly through states."
                )

            # Error rate data
            snapshot = self._error_rates.get((dep.source_id, dep.target_id))
            if snapshot and snapshot.error_rate < 0.01:
                risk += 0.1
                factors.append(
                    f"Very low baseline error rate ({snapshot.error_rate:.2%}) "
                    "combined with low threshold may cause unnecessary trips."
                )

            risk = min(1.0, risk)

            if risk >= 0.5:
                severity = Severity.CRITICAL
                recommendation = (
                    "Increase failure threshold or add error-rate sliding window "
                    "to prevent false trips."
                )
            elif risk >= 0.25:
                severity = Severity.WARNING
                recommendation = (
                    "Consider increasing failure threshold or adding jitter "
                    "tolerance to reduce false-positive risk."
                )
            else:
                severity = Severity.INFO
                recommendation = "False-positive risk is acceptable."

            if not factors:
                factors.append("No significant false-positive risk factors detected.")

            results.append(
                FalsePositiveRisk(
                    source_id=dep.source_id,
                    target_id=dep.target_id,
                    risk_score=round(risk, 4),
                    contributing_factors=factors,
                    severity=severity,
                    recommendation=recommendation,
                )
            )
        return results

    def assess_false_negative_risk(self) -> list[FalseNegativeRisk]:
        """Assess risk of breakers staying closed during actual outages."""
        results: list[FalseNegativeRisk] = []
        for dep in self._graph.all_dependency_edges():
            cb = dep.circuit_breaker
            factors: list[str] = []
            risk = 0.0

            if not cb.enabled:
                risk = 1.0
                factors.append("Circuit breaker is disabled -- no protection.")
                severity = Severity.CRITICAL
                if dep.dependency_type == "requires":
                    recommendation = (
                        "Enable circuit breaker on this critical dependency "
                        "to prevent cascade failure."
                    )
                else:
                    recommendation = (
                        "Consider enabling circuit breaker for faster failure "
                        "detection."
                    )
            else:
                # High threshold delays detection
                if cb.failure_threshold >= 10:
                    risk += 0.3
                    factors.append(
                        f"High failure threshold ({cb.failure_threshold}) delays "
                        "outage detection."
                    )
                elif cb.failure_threshold >= 7:
                    risk += 0.15
                    factors.append(
                        f"Moderately high failure threshold ({cb.failure_threshold}) "
                        "may delay detection."
                    )

                # Long recovery timeout means slow response to new outage
                if cb.recovery_timeout_seconds >= 120.0:
                    risk += 0.2
                    factors.append(
                        f"Long recovery timeout ({cb.recovery_timeout_seconds:.0f}s) "
                        "slows re-detection of recurring failures."
                    )

                # Low request rate means slower failure accumulation
                rps = self.get_request_rate(dep.source_id)
                if rps < 10:
                    risk += 0.15
                    factors.append(
                        f"Low request rate ({rps:.0f} rps) means failures "
                        "accumulate slowly towards threshold."
                    )

                # Optional/async dependencies are less critical
                if dep.dependency_type in ("optional", "async"):
                    risk *= 0.5
                    factors.append(
                        f"Dependency type '{dep.dependency_type}' reduces "
                        "blast radius of false negative."
                    )

                risk = min(1.0, risk)

                if risk >= 0.4:
                    severity = Severity.CRITICAL
                    recommendation = (
                        "Lower the failure threshold or implement health-check "
                        "probing to detect outages faster."
                    )
                elif risk >= 0.2:
                    severity = Severity.WARNING
                    recommendation = (
                        "Consider supplementing threshold-based detection with "
                        "active health checks."
                    )
                else:
                    severity = Severity.INFO
                    recommendation = "False-negative risk is acceptable."

                if not factors:
                    factors.append("No significant false-negative risk factors detected.")

            results.append(
                FalseNegativeRisk(
                    source_id=dep.source_id,
                    target_id=dep.target_id,
                    risk_score=round(risk, 4),
                    contributing_factors=factors,
                    severity=severity,
                    recommendation=recommendation,
                )
            )
        return results

    def analyze_retry_interactions(self) -> list[RetryBreakerInteraction]:
        """Analyse interaction between retry policies and circuit breakers."""
        results: list[RetryBreakerInteraction] = []
        for dep in self._graph.all_dependency_edges():
            cb = dep.circuit_breaker
            rs = dep.retry_strategy

            if not rs.enabled and not cb.enabled:
                # Neither enabled -- informational
                results.append(
                    RetryBreakerInteraction(
                        source_id=dep.source_id,
                        target_id=dep.target_id,
                        retry_enabled=False,
                        breaker_enabled=False,
                        retries_before_trip=0,
                        total_attempts_before_trip=0,
                        amplification_factor=1.0,
                        risk_description="Neither retry nor breaker enabled.",
                        severity=Severity.INFO,
                    )
                )
                continue

            if rs.enabled and cb.enabled:
                # Each request attempt can be retried max_retries times.
                # Failures accumulate: 1 user request = max_retries+1 potential failures
                attempts_per_request = rs.max_retries + 1
                retries_before_trip = max(
                    1,
                    cb.failure_threshold // attempts_per_request,
                )
                total_attempts = retries_before_trip * attempts_per_request
                amplification = float(attempts_per_request)

                if amplification >= 4:
                    severity = Severity.CRITICAL
                    desc = (
                        f"Retries ({rs.max_retries}) amplify failures {amplification:.0f}x. "
                        f"Breaker trips after only {retries_before_trip} user requests "
                        f"(total {total_attempts} attempts vs threshold {cb.failure_threshold})."
                    )
                elif amplification >= 2:
                    severity = Severity.WARNING
                    desc = (
                        f"Retries ({rs.max_retries}) amplify failures {amplification:.0f}x. "
                        f"Breaker trips after {retries_before_trip} user requests."
                    )
                else:
                    severity = Severity.INFO
                    desc = (
                        f"Retry-breaker interaction is within acceptable bounds. "
                        f"Amplification factor {amplification:.0f}x."
                    )
            elif rs.enabled and not cb.enabled:
                attempts_per_request = rs.max_retries + 1
                amplification = float(attempts_per_request)
                retries_before_trip = 0
                total_attempts = 0
                severity = Severity.WARNING
                desc = (
                    f"Retry enabled ({rs.max_retries} retries) but no circuit breaker. "
                    "Retries will continue indefinitely during outage."
                )
            else:
                # cb.enabled but no retries
                attempts_per_request = 1
                amplification = 1.0
                retries_before_trip = cb.failure_threshold
                total_attempts = cb.failure_threshold
                severity = Severity.INFO
                desc = (
                    "Circuit breaker without retries. Each failure counts directly "
                    f"towards threshold ({cb.failure_threshold})."
                )

            results.append(
                RetryBreakerInteraction(
                    source_id=dep.source_id,
                    target_id=dep.target_id,
                    retry_enabled=rs.enabled,
                    breaker_enabled=cb.enabled,
                    retries_before_trip=retries_before_trip,
                    total_attempts_before_trip=total_attempts,
                    amplification_factor=amplification,
                    risk_description=desc,
                    severity=severity,
                )
            )
        return results

    def analyze_bulkhead_integration(self) -> list[BulkheadBreakerIntegration]:
        """Analyse integration between bulkhead pattern and circuit breakers."""
        results: list[BulkheadBreakerIntegration] = []
        for dep in self._graph.all_dependency_edges():
            cb = dep.circuit_breaker
            bh = self._bulkhead_configs.get((dep.source_id, dep.target_id))

            if bh is None:
                # No bulkhead configured -- skip
                continue

            saturation_trips = False
            queue_triggers = False
            recommendation_parts: list[str] = []

            if cb.enabled:
                # If bulkhead max_concurrent < failure_threshold, bulkhead
                # rejection can cause breaker trip
                if bh.max_concurrent < cb.failure_threshold:
                    saturation_trips = False
                    recommendation_parts.append(
                        "Bulkhead limits concurrent requests below breaker threshold; "
                        "rejections alone won't trip the breaker."
                    )
                else:
                    saturation_trips = True
                    recommendation_parts.append(
                        "Bulkhead allows enough concurrent failures to trip the breaker "
                        "during saturation."
                    )

                # Queue timeout failures count towards breaker
                if bh.queue_timeout_ms > 0 and bh.max_queue_size > 0:
                    queue_triggers = True
                    recommendation_parts.append(
                        "Queue timeouts will increment the breaker failure counter."
                    )
            else:
                recommendation_parts.append(
                    "No circuit breaker on this dependency. Bulkhead provides "
                    "isolation but no automatic tripping on failure."
                )

            if saturation_trips and queue_triggers:
                severity = Severity.WARNING
            elif not cb.enabled:
                severity = Severity.WARNING
            else:
                severity = Severity.INFO

            results.append(
                BulkheadBreakerIntegration(
                    source_id=dep.source_id,
                    target_id=dep.target_id,
                    bulkhead_max_concurrent=bh.max_concurrent,
                    breaker_failure_threshold=cb.failure_threshold,
                    saturation_trips_breaker=saturation_trips,
                    queue_timeout_triggers_failure=queue_triggers,
                    recommendation=" ".join(recommendation_parts),
                    severity=severity,
                )
            )
        return results

    def simulate_state_machine(
        self,
        source_id: str,
        target_id: str,
        error_sequence: list[bool],
        request_interval_seconds: float = 0.1,
    ) -> SimulationResult:
        """Simulate circuit breaker state machine over a sequence of outcomes.

        *error_sequence* is a list of booleans where ``True`` means the request
        failed and ``False`` means it succeeded.
        """
        dep = self._graph.get_dependency_edge(source_id, target_id)
        if dep is None:
            cb = CircuitBreakerConfig()
        else:
            cb = dep.circuit_breaker

        state = BreakerState.CLOSED
        failure_count = 0
        success_count = 0
        transitions: list[StateTransition] = []
        time_cursor = 0.0
        open_time = 0.0
        closed_time = 0.0
        half_open_time = 0.0
        trip_count = 0
        half_open_requests = 0
        last_state_change_time = 0.0

        for is_error in error_sequence:
            elapsed_in_state = time_cursor - last_state_change_time

            if state == BreakerState.CLOSED:
                if is_error:
                    failure_count += 1
                    if cb.enabled and failure_count >= cb.failure_threshold:
                        closed_time += time_cursor - last_state_change_time
                        state = BreakerState.OPEN
                        trip_count += 1
                        transitions.append(
                            StateTransition(
                                time_seconds=round(time_cursor, 4),
                                from_state=BreakerState.CLOSED,
                                to_state=BreakerState.OPEN,
                                trigger=f"failure_count={failure_count} >= threshold={cb.failure_threshold}",
                                failure_count=failure_count,
                                success_count=success_count,
                            )
                        )
                        last_state_change_time = time_cursor
                        failure_count = 0
                        success_count = 0
                else:
                    success_count += 1
                    # Reset failure count on success (consecutive model)
                    failure_count = 0

            elif state == BreakerState.OPEN:
                # In OPEN state, requests are rejected.
                # Check if recovery timeout has elapsed.
                if elapsed_in_state >= cb.recovery_timeout_seconds:
                    open_time += time_cursor - last_state_change_time
                    state = BreakerState.HALF_OPEN
                    half_open_requests = 0
                    failure_count = 0
                    success_count = 0
                    transitions.append(
                        StateTransition(
                            time_seconds=round(time_cursor, 4),
                            from_state=BreakerState.OPEN,
                            to_state=BreakerState.HALF_OPEN,
                            trigger=f"recovery_timeout={cb.recovery_timeout_seconds}s elapsed",
                            failure_count=failure_count,
                            success_count=success_count,
                        )
                    )
                    last_state_change_time = time_cursor
                # else: request is rejected, no state change

            elif state == BreakerState.HALF_OPEN:
                half_open_requests += 1
                if is_error:
                    failure_count += 1
                    half_open_time += time_cursor - last_state_change_time
                    state = BreakerState.OPEN
                    trip_count += 1
                    transitions.append(
                        StateTransition(
                            time_seconds=round(time_cursor, 4),
                            from_state=BreakerState.HALF_OPEN,
                            to_state=BreakerState.OPEN,
                            trigger=f"failure in half-open (attempt {half_open_requests})",
                            failure_count=failure_count,
                            success_count=success_count,
                        )
                    )
                    last_state_change_time = time_cursor
                    failure_count = 0
                    success_count = 0
                    half_open_requests = 0
                else:
                    success_count += 1
                    if success_count >= cb.success_threshold:
                        half_open_time += time_cursor - last_state_change_time
                        state = BreakerState.CLOSED
                        transitions.append(
                            StateTransition(
                                time_seconds=round(time_cursor, 4),
                                from_state=BreakerState.HALF_OPEN,
                                to_state=BreakerState.CLOSED,
                                trigger=f"success_count={success_count} >= success_threshold={cb.success_threshold}",
                                failure_count=failure_count,
                                success_count=success_count,
                            )
                        )
                        last_state_change_time = time_cursor
                        failure_count = 0
                        success_count = 0

            time_cursor += request_interval_seconds

        # Account for time in final state
        final_elapsed = time_cursor - last_state_change_time
        if state == BreakerState.CLOSED:
            closed_time += final_elapsed
        elif state == BreakerState.OPEN:
            open_time += final_elapsed
        else:
            half_open_time += final_elapsed

        total_time = time_cursor
        availability = (
            (closed_time + half_open_time) / total_time
            if total_time > 0
            else 1.0
        )

        return SimulationResult(
            source_id=source_id,
            target_id=target_id,
            transitions=transitions,
            total_time_seconds=round(total_time, 4),
            time_in_open_seconds=round(open_time, 4),
            time_in_closed_seconds=round(closed_time, 4),
            time_in_half_open_seconds=round(half_open_time, 4),
            availability_ratio=round(availability, 4),
            trip_count=trip_count,
        )

    def recommend_placement(self) -> list[PlacementRecommendation]:
        """Recommend optimal circuit breaker placement for each dependency."""
        results: list[PlacementRecommendation] = []
        for dep in self._graph.all_dependency_edges():
            self._graph.get_component(dep.source_id)
            target = self._graph.get_component(dep.target_id)

            # Compute fan-out from source
            source_deps = self._graph.get_dependencies(dep.source_id)
            fan_out = len(source_deps)

            # Determine recommendation
            if fan_out >= 5:
                strategy = PlacementStrategy.MESH_LEVEL
                rationale = (
                    f"High fan-out ({fan_out} dependencies) from {dep.source_id}. "
                    "Mesh-level breakers centralise configuration."
                )
            elif target and target.type == ComponentType.EXTERNAL_API:
                strategy = PlacementStrategy.SIDECAR
                rationale = (
                    f"External API dependency ({dep.target_id}). "
                    "Sidecar breaker decouples retry/circuit logic from application."
                )
            elif dep.dependency_type == "requires" and target and target.replicas <= 1:
                strategy = PlacementStrategy.CLIENT_SIDE
                rationale = (
                    f"Critical dependency on single-instance {dep.target_id}. "
                    "Client-side breaker provides fastest failure detection."
                )
            elif fan_out >= 3:
                strategy = PlacementStrategy.SIDECAR
                rationale = (
                    f"Moderate fan-out ({fan_out}) from {dep.source_id}. "
                    "Sidecar placement provides per-destination isolation."
                )
            else:
                strategy = PlacementStrategy.CLIENT_SIDE
                rationale = (
                    f"Standard dependency from {dep.source_id} to {dep.target_id}. "
                    "Client-side breaker is simplest and most responsive."
                )

            results.append(
                PlacementRecommendation(
                    source_id=dep.source_id,
                    target_id=dep.target_id,
                    recommended_strategy=strategy,
                    current_has_breaker=dep.circuit_breaker.enabled,
                    dependency_type=dep.dependency_type,
                    fan_out=fan_out,
                    rationale=rationale,
                )
            )
        return results

    def detect_monitoring_gaps(self) -> list[MonitoringGap]:
        """Detect monitoring gaps for circuit breakers."""
        gaps: list[MonitoringGap] = []
        for dep in self._graph.all_dependency_edges():
            cb = dep.circuit_breaker

            if not cb.enabled:
                if dep.dependency_type == "requires":
                    gaps.append(
                        MonitoringGap(
                            source_id=dep.source_id,
                            target_id=dep.target_id,
                            gap_type="no_breaker",
                            description=(
                                f"Critical dependency {dep.source_id}->{dep.target_id} "
                                "has no circuit breaker."
                            ),
                            severity=Severity.CRITICAL,
                            recommendation="Enable circuit breaker on this dependency.",
                        )
                    )
                continue

            # Check for missing error-rate data
            snapshot = self._error_rates.get((dep.source_id, dep.target_id))
            if snapshot is None or snapshot.sample_count == 0:
                gaps.append(
                    MonitoringGap(
                        source_id=dep.source_id,
                        target_id=dep.target_id,
                        gap_type="no_error_metrics",
                        description=(
                            f"No error-rate metrics for {dep.source_id}->"
                            f"{dep.target_id}. Cannot validate breaker thresholds."
                        ),
                        severity=Severity.WARNING,
                        recommendation=(
                            "Instrument error-rate metrics for this dependency."
                        ),
                    )
                )

            # Check for missing recovery data
            if dep.target_id not in self._recovery_patterns:
                gaps.append(
                    MonitoringGap(
                        source_id=dep.source_id,
                        target_id=dep.target_id,
                        gap_type="no_recovery_metrics",
                        description=(
                            f"No recovery-time metrics for {dep.target_id}. "
                            "Cannot validate recovery timeout."
                        ),
                        severity=Severity.WARNING,
                        recommendation=(
                            "Track recovery times for this service to tune "
                            "circuit breaker recovery timeout."
                        ),
                    )
                )

            # Check for state transition alerting
            target = self._graph.get_component(dep.target_id)
            if target and not target.compliance_tags.audit_logging:
                gaps.append(
                    MonitoringGap(
                        source_id=dep.source_id,
                        target_id=dep.target_id,
                        gap_type="no_state_alerts",
                        description=(
                            f"No audit logging for {dep.target_id}. "
                            "Circuit breaker state changes may go unnoticed."
                        ),
                        severity=Severity.INFO,
                        recommendation=(
                            "Enable alerting on circuit breaker state transitions."
                        ),
                    )
                )
        return gaps

    def assess_thundering_herd_risk(self) -> list[ThunderingHerdRisk]:
        """Assess thundering herd risk after circuit breaker recovery."""
        results: list[ThunderingHerdRisk] = []
        for dep in self._graph.all_dependency_edges():
            cb = dep.circuit_breaker
            if not cb.enabled:
                continue

            source_rps = self.get_request_rate(dep.source_id)
            target = self._graph.get_component(dep.target_id)
            target_max_rps = target.capacity.max_rps if target else 5000

            # Estimate queued requests during OPEN state
            queued_estimate = int(source_rps * cb.recovery_timeout_seconds)

            # Recovery burst: all queued requests hit at once
            if target_max_rps > 0:
                burst_ratio = queued_estimate / target_max_rps
            else:
                burst_ratio = float("inf") if queued_estimate > 0 else 0.0

            will_overwhelm = burst_ratio > 1.0

            # Also check fan-in: how many sources point to target
            dependents = self._graph.get_dependents(dep.target_id)
            total_fan_in_rps = sum(
                self.get_request_rate(d.id) for d in dependents
            )
            if total_fan_in_rps > 0:
                fan_in_queued = int(total_fan_in_rps * cb.recovery_timeout_seconds)
                fan_in_ratio = fan_in_queued / target_max_rps if target_max_rps > 0 else float("inf")
                if fan_in_ratio > burst_ratio:
                    burst_ratio = fan_in_ratio
                    queued_estimate = fan_in_queued
                    will_overwhelm = burst_ratio > 1.0

            if will_overwhelm and burst_ratio > 5.0:
                severity = Severity.CRITICAL
                recommendation = (
                    "Implement gradual ramp-up (e.g. token bucket) after breaker "
                    "recovery to prevent thundering herd."
                )
            elif will_overwhelm:
                severity = Severity.WARNING
                recommendation = (
                    "Consider rate limiting or gradual ramp-up on recovery "
                    "to mitigate thundering herd risk."
                )
            else:
                severity = Severity.INFO
                recommendation = "Thundering herd risk is manageable."

            results.append(
                ThunderingHerdRisk(
                    source_id=dep.source_id,
                    target_id=dep.target_id,
                    queued_request_estimate=queued_estimate,
                    recovery_burst_ratio=round(burst_ratio, 2),
                    target_max_rps=target_max_rps,
                    will_overwhelm=will_overwhelm,
                    severity=severity,
                    recommendation=recommendation,
                )
            )
        return results

    def recommend_success_rates(self) -> list[SuccessRateRecommendation]:
        """Recommend success-rate thresholds for half-open to closed transition."""
        results: list[SuccessRateRecommendation] = []
        for dep in self._graph.all_dependency_edges():
            cb = dep.circuit_breaker
            if not cb.enabled:
                continue

            current_success = cb.success_threshold
            current_half_open = cb.half_open_max_requests

            # Target: success_threshold / half_open_max_requests should be
            # high enough to confirm genuine recovery.
            if current_half_open > 0:
                current_rate = current_success / current_half_open
            else:
                current_rate = 0.0

            # Recommend based on dependency criticality
            if dep.dependency_type == "requires":
                target_rate = 0.8
                min_success = max(2, int(current_half_open * target_rate))
            elif dep.dependency_type == "optional":
                target_rate = 0.6
                min_success = max(1, int(current_half_open * target_rate))
            else:
                target_rate = 0.5
                min_success = max(1, int(current_half_open * target_rate))

            recommended_success = max(min_success, current_success)
            # Don't exceed half_open_max_requests
            recommended_success = min(recommended_success, current_half_open)

            if current_rate < target_rate * 0.5:
                rationale = (
                    f"Current success rate ({current_rate:.0%}) is much lower than "
                    f"recommended ({target_rate:.0%}). Increase success threshold "
                    "to prevent premature closure."
                )
            elif current_rate < target_rate:
                rationale = (
                    f"Current success rate ({current_rate:.0%}) is below "
                    f"recommended ({target_rate:.0%}). Consider raising threshold."
                )
            else:
                rationale = (
                    f"Current success rate ({current_rate:.0%}) meets or exceeds "
                    f"recommended ({target_rate:.0%}). Configuration is adequate."
                )

            results.append(
                SuccessRateRecommendation(
                    source_id=dep.source_id,
                    target_id=dep.target_id,
                    current_success_threshold=current_success,
                    recommended_success_threshold=recommended_success,
                    current_half_open_requests=current_half_open,
                    recommended_success_rate=round(target_rate, 2),
                    rationale=rationale,
                )
            )
        return results

    def analyze_test_coverage(self) -> list[TestCoverageResult]:
        """Analyse circuit breaker testing coverage."""
        all_aspects = [
            "trip_on_failure",
            "recovery_after_timeout",
            "half_open_success",
            "half_open_failure",
            "concurrent_requests",
            "retry_interaction",
            "monitoring_alerts",
            "graceful_degradation",
        ]
        results: list[TestCoverageResult] = []
        for dep in self._graph.all_dependency_edges():
            cb = dep.circuit_breaker
            if not cb.enabled:
                results.append(
                    TestCoverageResult(
                        source_id=dep.source_id,
                        target_id=dep.target_id,
                        coverage_level=TestCoverageLevel.NONE,
                        tested_states=[],
                        missing_tests=list(all_aspects),
                        coverage_score=0.0,
                        recommendation=(
                            "Enable and test circuit breaker for this dependency."
                        ),
                    )
                )
                continue

            tested = self._test_coverage.get(
                (dep.source_id, dep.target_id), []
            )
            missing = [a for a in all_aspects if a not in tested]
            score = len(tested) / len(all_aspects) if all_aspects else 0.0

            tested_states: list[BreakerState] = []
            if "trip_on_failure" in tested:
                tested_states.append(BreakerState.CLOSED)
                tested_states.append(BreakerState.OPEN)
            if "half_open_success" in tested or "half_open_failure" in tested:
                tested_states.append(BreakerState.HALF_OPEN)
            if "recovery_after_timeout" in tested:
                if BreakerState.OPEN not in tested_states:
                    tested_states.append(BreakerState.OPEN)
                if BreakerState.HALF_OPEN not in tested_states:
                    tested_states.append(BreakerState.HALF_OPEN)

            if score >= 0.75:
                level = TestCoverageLevel.COMPREHENSIVE
                recommendation = "Test coverage is comprehensive."
            elif score >= 0.5:
                level = TestCoverageLevel.MODERATE
                recommendation = f"Add tests for: {', '.join(missing)}."
            elif score > 0:
                level = TestCoverageLevel.BASIC
                recommendation = f"Significant gaps. Add tests for: {', '.join(missing)}."
            else:
                level = TestCoverageLevel.NONE
                recommendation = "No circuit breaker tests exist. Add comprehensive tests."

            results.append(
                TestCoverageResult(
                    source_id=dep.source_id,
                    target_id=dep.target_id,
                    coverage_level=level,
                    tested_states=tested_states,
                    missing_tests=missing,
                    coverage_score=round(score, 4),
                    recommendation=recommendation,
                )
            )
        return results

    # -- full report ----------------------------------------------------------

    def generate_report(self) -> CircuitBreakerTuningReport:
        """Generate a comprehensive circuit breaker tuning report."""
        all_edges = self._graph.all_dependency_edges()
        enabled_count = sum(1 for e in all_edges if e.circuit_breaker.enabled)

        thresholds = self.optimize_failure_thresholds()
        recovery_recs = self.tune_recovery_timeouts()
        half_open = self.calculate_half_open_budgets()
        cascades = self.analyze_cascading_breakers()
        fp_risks = self.assess_false_positive_risk()
        fn_risks = self.assess_false_negative_risk()
        retry_ints = self.analyze_retry_interactions()
        bulkhead_ints = self.analyze_bulkhead_integration()
        placements = self.recommend_placement()
        monitoring = self.detect_monitoring_gaps()
        herd_risks = self.assess_thundering_herd_risk()
        success_recs = self.recommend_success_rates()
        test_cov = self.analyze_test_coverage()

        # Run state-machine simulation for each enabled breaker
        simulations: list[SimulationResult] = []
        for dep in all_edges:
            if dep.circuit_breaker.enabled:
                snapshot = self._error_rates.get((dep.source_id, dep.target_id))
                error_rate = snapshot.error_rate if snapshot else 0.05
                # Generate a synthetic error sequence
                seq_len = 100
                seq: list[bool] = []
                accumulator = 0.0
                for i in range(seq_len):
                    accumulator += error_rate
                    if accumulator >= 1.0:
                        seq.append(True)
                        accumulator -= 1.0
                    else:
                        seq.append(False)
                sim = self.simulate_state_machine(
                    dep.source_id, dep.target_id, seq
                )
                simulations.append(sim)

        # Compile recommendations
        recommendations: list[str] = []

        crit_fp = sum(1 for r in fp_risks if r.severity == Severity.CRITICAL)
        crit_fn = sum(1 for r in fn_risks if r.severity == Severity.CRITICAL)
        crit_cascade = sum(1 for c in cascades if c.severity == Severity.CRITICAL)
        crit_herd = sum(1 for h in herd_risks if h.severity == Severity.CRITICAL)
        crit_monitoring = sum(1 for g in monitoring if g.severity == Severity.CRITICAL)
        crit_retry = sum(1 for r in retry_ints if r.severity == Severity.CRITICAL)

        if enabled_count == 0 and len(all_edges) > 0:
            recommendations.append(
                "No circuit breakers enabled on any dependency. "
                "Enable breakers on critical paths."
            )
        elif enabled_count < len(all_edges):
            unprotected = len(all_edges) - enabled_count
            recommendations.append(
                f"{unprotected} of {len(all_edges)} dependencies lack circuit breakers."
            )

        if crit_fp > 0:
            recommendations.append(
                f"{crit_fp} dependencies have critical false-positive trip risk."
            )
        if crit_fn > 0:
            recommendations.append(
                f"{crit_fn} dependencies have critical false-negative risk."
            )
        if crit_cascade > 0:
            recommendations.append(
                f"{crit_cascade} dependency chains have critical cascade risk."
            )
        if crit_herd > 0:
            recommendations.append(
                f"{crit_herd} dependencies have critical thundering herd risk."
            )
        if crit_monitoring > 0:
            recommendations.append(
                f"{crit_monitoring} critical monitoring gaps detected."
            )
        if crit_retry > 0:
            recommendations.append(
                f"{crit_retry} dependencies have critical retry-breaker amplification."
            )

        # Threshold mismatches
        threshold_mismatches = sum(
            1 for t in thresholds if t.current_threshold != t.recommended_threshold
        )
        if threshold_mismatches > 0:
            recommendations.append(
                f"{threshold_mismatches} circuit breakers have sub-optimal "
                "failure thresholds."
            )

        # Recovery timeout mismatches
        recovery_mismatches = sum(
            1
            for r in recovery_recs
            if abs(r.current_timeout_seconds - r.recommended_timeout_seconds) > 10
        )
        if recovery_mismatches > 0:
            recommendations.append(
                f"{recovery_mismatches} circuit breakers have sub-optimal "
                "recovery timeouts."
            )

        # Low test coverage
        low_coverage = sum(
            1
            for t in test_cov
            if t.coverage_level in (TestCoverageLevel.NONE, TestCoverageLevel.BASIC)
        )
        if low_coverage > 0:
            recommendations.append(
                f"{low_coverage} circuit breakers have insufficient test coverage."
            )

        # Determine overall health
        total_critical = (
            crit_fp + crit_fn + crit_cascade + crit_herd
            + crit_monitoring + crit_retry
        )
        total_warning = (
            sum(1 for r in fp_risks if r.severity == Severity.WARNING)
            + sum(1 for r in fn_risks if r.severity == Severity.WARNING)
            + sum(1 for c in cascades if c.severity == Severity.WARNING)
            + sum(1 for h in herd_risks if h.severity == Severity.WARNING)
            + sum(1 for g in monitoring if g.severity == Severity.WARNING)
            + sum(1 for r in retry_ints if r.severity == Severity.WARNING)
        )

        if total_critical > 0:
            overall = Severity.CRITICAL
        elif total_warning > 0:
            overall = Severity.WARNING
        else:
            overall = Severity.INFO

        return CircuitBreakerTuningReport(
            generated_at=datetime.now(timezone.utc),
            total_dependencies=len(all_edges),
            breaker_enabled_count=enabled_count,
            threshold_recommendations=thresholds,
            recovery_timeout_recommendations=recovery_recs,
            half_open_budgets=half_open,
            cascade_analyses=cascades,
            false_positive_risks=fp_risks,
            false_negative_risks=fn_risks,
            retry_interactions=retry_ints,
            bulkhead_integrations=bulkhead_ints,
            simulation_results=simulations,
            placement_recommendations=placements,
            monitoring_gaps=monitoring,
            thundering_herd_risks=herd_risks,
            success_rate_recommendations=success_recs,
            test_coverage_results=test_cov,
            overall_health=overall,
            recommendations=recommendations,
        )
