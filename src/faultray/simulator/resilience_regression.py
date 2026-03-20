# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Resilience regression detector — detect regressions across snapshots.

Compares infrastructure snapshots over time to detect resilience regressions
such as score drops, SPOF introductions, circuit-breaker removals, replica
reductions, failover disablement, capacity reductions, new dependencies,
security downgrades, SLO loosening, and recovery-time increases.
"""

from __future__ import annotations

from enum import Enum
from statistics import linear_regression

from pydantic import BaseModel, Field

from faultray.model.components import ComponentType
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class RegressionType(str, Enum):
    """Types of resilience regressions that can be detected."""

    SCORE_DROP = "score_drop"
    SPOF_INTRODUCED = "spof_introduced"
    CIRCUIT_BREAKER_REMOVED = "circuit_breaker_removed"
    REPLICA_REDUCED = "replica_reduced"
    FAILOVER_DISABLED = "failover_disabled"
    CAPACITY_REDUCED = "capacity_reduced"
    DEPENDENCY_ADDED = "dependency_added"
    SECURITY_DOWNGRADE = "security_downgrade"
    SLO_LOOSENED = "slo_loosened"
    RECOVERY_TIME_INCREASED = "recovery_time_increased"


class RegressionSeverity(str, Enum):
    """Severity of a detected regression."""

    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"
    INFO = "info"


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class Regression(BaseModel):
    """A single detected resilience regression."""

    regression_type: RegressionType
    severity: RegressionSeverity
    component_id: str
    previous_value: str
    current_value: str
    impact_description: str
    recommendation: str


class RegressionReport(BaseModel):
    """Full report of regressions detected between two snapshots."""

    total_regressions: int
    critical_count: int
    major_count: int
    minor_count: int
    regressions: list[Regression] = Field(default_factory=list)
    overall_trend: str  # improving | stable | degrading
    score_delta: float
    recommendations: list[str] = Field(default_factory=list)


class ScorePoint(BaseModel):
    """A single score measurement at a point in time."""

    timestamp_index: int
    score: float


class ScoreHistory(BaseModel):
    """Tracked score history from multiple snapshots."""

    points: list[ScorePoint] = Field(default_factory=list)
    trend: str  # improving | stable | degrading
    average_score: float
    min_score: float
    max_score: float
    volatility: float


class GradualDegradation(BaseModel):
    """Detected pattern of gradual resilience degradation."""

    metric_name: str
    component_id: str
    values: list[float] = Field(default_factory=list)
    slope: float
    description: str


class CIGateResult(BaseModel):
    """Result of a CI/CD gate check for resilience regressions."""

    passed: bool
    score_current: float
    score_previous: float
    score_delta: float
    threshold: float
    regressions_found: int
    critical_regressions: int
    gate_message: str
    details: list[str] = Field(default_factory=list)


class RemediationStep(BaseModel):
    """A recommended remediation step for addressing regressions."""

    priority: int
    regression_type: RegressionType
    component_id: str
    action: str
    effort: str  # low | medium | high
    impact: str  # low | medium | high


# ---------------------------------------------------------------------------
# Internal snapshot helper
# ---------------------------------------------------------------------------


class _ComponentSnapshot(BaseModel):
    """Internal snapshot of a single component's resilience properties."""

    component_id: str
    name: str
    component_type: ComponentType
    replicas: int
    failover_enabled: bool
    circuit_breakers: list[str] = Field(default_factory=list)
    dependency_ids: list[str] = Field(default_factory=list)
    dependent_ids: list[str] = Field(default_factory=list)
    slo_targets: list[float] = Field(default_factory=list)
    recovery_time_seconds: float
    encryption_at_rest: bool
    encryption_in_transit: bool
    capacity_max_rps: int
    capacity_max_connections: int


class _GraphSnapshot(BaseModel):
    """Internal full graph snapshot for comparison."""

    score: float
    component_snapshots: dict[str, _ComponentSnapshot] = Field(default_factory=dict)
    total_components: int
    total_dependencies: int


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


_REGRESSION_SEVERITY_MAP: dict[RegressionType, RegressionSeverity] = {
    RegressionType.SCORE_DROP: RegressionSeverity.CRITICAL,
    RegressionType.SPOF_INTRODUCED: RegressionSeverity.CRITICAL,
    RegressionType.CIRCUIT_BREAKER_REMOVED: RegressionSeverity.MAJOR,
    RegressionType.REPLICA_REDUCED: RegressionSeverity.MAJOR,
    RegressionType.FAILOVER_DISABLED: RegressionSeverity.CRITICAL,
    RegressionType.CAPACITY_REDUCED: RegressionSeverity.MINOR,
    RegressionType.DEPENDENCY_ADDED: RegressionSeverity.INFO,
    RegressionType.SECURITY_DOWNGRADE: RegressionSeverity.MAJOR,
    RegressionType.SLO_LOOSENED: RegressionSeverity.MINOR,
    RegressionType.RECOVERY_TIME_INCREASED: RegressionSeverity.MINOR,
}


_RECOMMENDATION_MAP: dict[RegressionType, str] = {
    RegressionType.SCORE_DROP: "Investigate the root cause of the score drop and address the underlying issues.",
    RegressionType.SPOF_INTRODUCED: "Add replicas or failover to eliminate the single point of failure.",
    RegressionType.CIRCUIT_BREAKER_REMOVED: "Re-enable circuit breakers to prevent cascade failures.",
    RegressionType.REPLICA_REDUCED: "Restore replica count to previous level for redundancy.",
    RegressionType.FAILOVER_DISABLED: "Re-enable failover to ensure automatic recovery on failure.",
    RegressionType.CAPACITY_REDUCED: "Restore capacity limits to handle expected traffic load.",
    RegressionType.DEPENDENCY_ADDED: "Evaluate new dependency for resilience impact and add circuit breaker.",
    RegressionType.SECURITY_DOWNGRADE: "Restore security controls to previous level.",
    RegressionType.SLO_LOOSENED: "Tighten SLO targets back to previous level or justify the change.",
    RegressionType.RECOVERY_TIME_INCREASED: "Reduce recovery time by tuning failover or adding health checks.",
}


class ResilienceRegressionEngine:
    """Stateless engine to detect resilience regressions between graph snapshots."""

    # -- public API ---------------------------------------------------------

    def detect_regressions(
        self,
        current_graph: InfraGraph,
        previous_graph: InfraGraph,
    ) -> RegressionReport:
        """Detect all regressions between current and previous graphs."""
        current_snap = self._snapshot_graph(current_graph)
        previous_snap = self._snapshot_graph(previous_graph)

        regressions: list[Regression] = []

        # 1. Score drop
        score_delta = current_snap.score - previous_snap.score
        if score_delta < -5.0:
            regressions.append(Regression(
                regression_type=RegressionType.SCORE_DROP,
                severity=RegressionSeverity.CRITICAL,
                component_id="__system__",
                previous_value=f"{previous_snap.score:.1f}",
                current_value=f"{current_snap.score:.1f}",
                impact_description=f"Overall resilience score dropped by {abs(score_delta):.1f} points.",
                recommendation=_RECOMMENDATION_MAP[RegressionType.SCORE_DROP],
            ))

        # 2. Per-component regressions
        for comp_id, prev_cs in previous_snap.component_snapshots.items():
            curr_cs = current_snap.component_snapshots.get(comp_id)
            if curr_cs is None:
                continue

            # SPOF introduced
            was_spof = prev_cs.replicas <= 1 and len(prev_cs.dependent_ids) > 0 and not prev_cs.failover_enabled
            is_spof = curr_cs.replicas <= 1 and len(curr_cs.dependent_ids) > 0 and not curr_cs.failover_enabled
            if is_spof and not was_spof:
                regressions.append(Regression(
                    regression_type=RegressionType.SPOF_INTRODUCED,
                    severity=RegressionSeverity.CRITICAL,
                    component_id=comp_id,
                    previous_value=f"replicas={prev_cs.replicas}, failover={prev_cs.failover_enabled}",
                    current_value=f"replicas={curr_cs.replicas}, failover={curr_cs.failover_enabled}",
                    impact_description=f"Component '{curr_cs.name}' is now a single point of failure with {len(curr_cs.dependent_ids)} dependents.",
                    recommendation=_RECOMMENDATION_MAP[RegressionType.SPOF_INTRODUCED],
                ))

            # Circuit breaker removed
            removed_cbs = set(prev_cs.circuit_breakers) - set(curr_cs.circuit_breakers)
            if removed_cbs:
                regressions.append(Regression(
                    regression_type=RegressionType.CIRCUIT_BREAKER_REMOVED,
                    severity=RegressionSeverity.MAJOR,
                    component_id=comp_id,
                    previous_value=f"circuit_breakers={sorted(prev_cs.circuit_breakers)}",
                    current_value=f"circuit_breakers={sorted(curr_cs.circuit_breakers)}",
                    impact_description=f"Circuit breakers removed on edges to: {sorted(removed_cbs)}.",
                    recommendation=_RECOMMENDATION_MAP[RegressionType.CIRCUIT_BREAKER_REMOVED],
                ))

            # Replica reduced
            if curr_cs.replicas < prev_cs.replicas:
                regressions.append(Regression(
                    regression_type=RegressionType.REPLICA_REDUCED,
                    severity=RegressionSeverity.MAJOR,
                    component_id=comp_id,
                    previous_value=str(prev_cs.replicas),
                    current_value=str(curr_cs.replicas),
                    impact_description=f"Replicas reduced from {prev_cs.replicas} to {curr_cs.replicas}.",
                    recommendation=_RECOMMENDATION_MAP[RegressionType.REPLICA_REDUCED],
                ))

            # Failover disabled
            if prev_cs.failover_enabled and not curr_cs.failover_enabled:
                regressions.append(Regression(
                    regression_type=RegressionType.FAILOVER_DISABLED,
                    severity=RegressionSeverity.CRITICAL,
                    component_id=comp_id,
                    previous_value="enabled",
                    current_value="disabled",
                    impact_description=f"Failover disabled on '{curr_cs.name}'. Manual recovery required.",
                    recommendation=_RECOMMENDATION_MAP[RegressionType.FAILOVER_DISABLED],
                ))

            # Capacity reduced
            if curr_cs.capacity_max_rps < prev_cs.capacity_max_rps:
                regressions.append(Regression(
                    regression_type=RegressionType.CAPACITY_REDUCED,
                    severity=RegressionSeverity.MINOR,
                    component_id=comp_id,
                    previous_value=f"max_rps={prev_cs.capacity_max_rps}",
                    current_value=f"max_rps={curr_cs.capacity_max_rps}",
                    impact_description=f"Max RPS reduced from {prev_cs.capacity_max_rps} to {curr_cs.capacity_max_rps}.",
                    recommendation=_RECOMMENDATION_MAP[RegressionType.CAPACITY_REDUCED],
                ))

            # Dependency added
            new_deps = set(curr_cs.dependency_ids) - set(prev_cs.dependency_ids)
            if new_deps:
                regressions.append(Regression(
                    regression_type=RegressionType.DEPENDENCY_ADDED,
                    severity=RegressionSeverity.INFO,
                    component_id=comp_id,
                    previous_value=f"deps={sorted(prev_cs.dependency_ids)}",
                    current_value=f"deps={sorted(curr_cs.dependency_ids)}",
                    impact_description=f"New dependencies added: {sorted(new_deps)}.",
                    recommendation=_RECOMMENDATION_MAP[RegressionType.DEPENDENCY_ADDED],
                ))

            # Security downgrade
            if (prev_cs.encryption_at_rest and not curr_cs.encryption_at_rest) or \
               (prev_cs.encryption_in_transit and not curr_cs.encryption_in_transit):
                regressions.append(Regression(
                    regression_type=RegressionType.SECURITY_DOWNGRADE,
                    severity=RegressionSeverity.MAJOR,
                    component_id=comp_id,
                    previous_value=f"rest={prev_cs.encryption_at_rest}, transit={prev_cs.encryption_in_transit}",
                    current_value=f"rest={curr_cs.encryption_at_rest}, transit={curr_cs.encryption_in_transit}",
                    impact_description="Encryption coverage reduced.",
                    recommendation=_RECOMMENDATION_MAP[RegressionType.SECURITY_DOWNGRADE],
                ))

            # SLO loosened
            if prev_cs.slo_targets and curr_cs.slo_targets:
                for i, (prev_t, curr_t) in enumerate(zip(prev_cs.slo_targets, curr_cs.slo_targets)):
                    if curr_t < prev_t:
                        regressions.append(Regression(
                            regression_type=RegressionType.SLO_LOOSENED,
                            severity=RegressionSeverity.MINOR,
                            component_id=comp_id,
                            previous_value=f"slo[{i}]={prev_t}",
                            current_value=f"slo[{i}]={curr_t}",
                            impact_description=f"SLO target loosened from {prev_t} to {curr_t}.",
                            recommendation=_RECOMMENDATION_MAP[RegressionType.SLO_LOOSENED],
                        ))

            # Recovery time increased
            if curr_cs.recovery_time_seconds > prev_cs.recovery_time_seconds * 1.2:
                regressions.append(Regression(
                    regression_type=RegressionType.RECOVERY_TIME_INCREASED,
                    severity=RegressionSeverity.MINOR,
                    component_id=comp_id,
                    previous_value=f"{prev_cs.recovery_time_seconds:.0f}s",
                    current_value=f"{curr_cs.recovery_time_seconds:.0f}s",
                    impact_description=f"Recovery time increased from {prev_cs.recovery_time_seconds:.0f}s to {curr_cs.recovery_time_seconds:.0f}s.",
                    recommendation=_RECOMMENDATION_MAP[RegressionType.RECOVERY_TIME_INCREASED],
                ))

        critical_count = sum(1 for r in regressions if r.severity == RegressionSeverity.CRITICAL)
        major_count = sum(1 for r in regressions if r.severity == RegressionSeverity.MAJOR)
        minor_count = sum(1 for r in regressions if r.severity == RegressionSeverity.MINOR)

        overall_trend = self._determine_trend(score_delta)

        unique_recs: list[str] = []
        seen: set[str] = set()
        for r in regressions:
            if r.recommendation not in seen:
                seen.add(r.recommendation)
                unique_recs.append(r.recommendation)

        return RegressionReport(
            total_regressions=len(regressions),
            critical_count=critical_count,
            major_count=major_count,
            minor_count=minor_count,
            regressions=regressions,
            overall_trend=overall_trend,
            score_delta=round(score_delta, 2),
            recommendations=unique_recs,
        )

    def track_score_history(self, snapshots: list[InfraGraph]) -> ScoreHistory:
        """Track resilience score over a series of snapshots."""
        if not snapshots:
            return ScoreHistory(
                points=[],
                trend="stable",
                average_score=0.0,
                min_score=0.0,
                max_score=0.0,
                volatility=0.0,
            )

        scores = [g.resilience_score() for g in snapshots]
        points = [
            ScorePoint(timestamp_index=i, score=round(s, 2))
            for i, s in enumerate(scores)
        ]

        avg = sum(scores) / len(scores)
        min_s = min(scores)
        max_s = max(scores)

        # Volatility: standard deviation
        if len(scores) > 1:
            variance = sum((s - avg) ** 2 for s in scores) / len(scores)
            volatility = variance ** 0.5
        else:
            volatility = 0.0

        # Trend: compare first half vs second half
        trend = self._compute_trend(scores)

        return ScoreHistory(
            points=points,
            trend=trend,
            average_score=round(avg, 2),
            min_score=round(min_s, 2),
            max_score=round(max_s, 2),
            volatility=round(volatility, 2),
        )

    def detect_gradual_degradation(
        self, snapshots: list[InfraGraph]
    ) -> list[GradualDegradation]:
        """Detect gradual degradation patterns across snapshots."""
        if len(snapshots) < 3:
            return []

        degradations: list[GradualDegradation] = []

        # 1. Overall score degradation
        scores = [g.resilience_score() for g in snapshots]
        slope = self._compute_slope(scores)
        if slope < -1.0:
            degradations.append(GradualDegradation(
                metric_name="resilience_score",
                component_id="__system__",
                values=[round(s, 2) for s in scores],
                slope=round(slope, 4),
                description=f"Overall resilience score declining at {abs(slope):.2f} points per snapshot.",
            ))

        # 2. Per-component replica trends
        all_comp_ids: set[str] = set()
        for g in snapshots:
            all_comp_ids.update(g.components.keys())

        for comp_id in sorted(all_comp_ids):
            replica_values: list[float] = []
            for g in snapshots:
                comp = g.get_component(comp_id)
                if comp is not None:
                    replica_values.append(float(comp.replicas))
                else:
                    replica_values.append(0.0)

            if len(replica_values) >= 3 and any(v > 0 for v in replica_values):
                r_slope = self._compute_slope(replica_values)
                if r_slope < -0.3:
                    degradations.append(GradualDegradation(
                        metric_name="replica_count",
                        component_id=comp_id,
                        values=replica_values,
                        slope=round(r_slope, 4),
                        description=f"Component '{comp_id}' replicas declining at {abs(r_slope):.2f} per snapshot.",
                    ))

        return degradations

    def generate_ci_gate_result(
        self,
        current: InfraGraph,
        previous: InfraGraph,
        threshold: float = 5.0,
    ) -> CIGateResult:
        """Generate a pass/fail CI gate result comparing two graph versions."""
        report = self.detect_regressions(current, previous)
        score_current = current.resilience_score()
        score_previous = previous.resilience_score()
        score_delta = score_current - score_previous

        passed = True
        details: list[str] = []

        # Fail on critical regressions
        if report.critical_count > 0:
            passed = False
            details.append(f"{report.critical_count} critical regression(s) found.")

        # Fail if score dropped beyond threshold
        if score_delta < -threshold:
            passed = False
            details.append(
                f"Score dropped by {abs(score_delta):.1f} (threshold: {threshold})."
            )

        # Warn on major regressions
        if report.major_count > 0:
            details.append(f"{report.major_count} major regression(s) found.")

        if report.minor_count > 0:
            details.append(f"{report.minor_count} minor regression(s) found.")

        if passed:
            gate_message = "PASSED: No critical regressions and score within threshold."
        else:
            gate_message = "FAILED: Resilience regressions detected."

        return CIGateResult(
            passed=passed,
            score_current=round(score_current, 2),
            score_previous=round(score_previous, 2),
            score_delta=round(score_delta, 2),
            threshold=threshold,
            regressions_found=report.total_regressions,
            critical_regressions=report.critical_count,
            gate_message=gate_message,
            details=details,
        )

    def find_root_cause(self, regression: Regression) -> str:
        """Provide a root cause analysis string for a regression."""
        rt = regression.regression_type

        if rt == RegressionType.SCORE_DROP:
            return (
                f"Overall resilience score dropped from {regression.previous_value} "
                f"to {regression.current_value}. This may be caused by multiple "
                "concurrent changes reducing redundancy, failover, or capacity."
            )
        if rt == RegressionType.SPOF_INTRODUCED:
            return (
                f"Component '{regression.component_id}' became a single point of failure. "
                f"Previous state: {regression.previous_value}. "
                f"Current state: {regression.current_value}. "
                "Root cause: replicas reduced to 1 with failover disabled while "
                "other components depend on it."
            )
        if rt == RegressionType.CIRCUIT_BREAKER_REMOVED:
            return (
                f"Circuit breaker(s) removed from '{regression.component_id}'. "
                "Root cause: dependency configuration changed without retaining "
                "cascade failure protection."
            )
        if rt == RegressionType.REPLICA_REDUCED:
            return (
                f"Replica count on '{regression.component_id}' reduced from "
                f"{regression.previous_value} to {regression.current_value}. "
                "Root cause: likely a cost-optimization or scaling-down action "
                "without resilience review."
            )
        if rt == RegressionType.FAILOVER_DISABLED:
            return (
                f"Failover disabled on '{regression.component_id}'. "
                "Root cause: failover configuration changed. This removes "
                "automatic recovery capability."
            )
        if rt == RegressionType.CAPACITY_REDUCED:
            return (
                f"Capacity reduced on '{regression.component_id}'. "
                f"{regression.impact_description} "
                "Root cause: capacity limits lowered, possibly during rightsizing."
            )
        if rt == RegressionType.DEPENDENCY_ADDED:
            return (
                f"New dependencies added to '{regression.component_id}'. "
                f"{regression.impact_description} "
                "Root cause: architectural change introduced new coupling."
            )
        if rt == RegressionType.SECURITY_DOWNGRADE:
            return (
                f"Security posture degraded on '{regression.component_id}'. "
                "Root cause: encryption settings were weakened or removed."
            )
        if rt == RegressionType.SLO_LOOSENED:
            return (
                f"SLO targets loosened on '{regression.component_id}'. "
                f"Previous: {regression.previous_value}, "
                f"Current: {regression.current_value}. "
                "Root cause: reliability targets reduced, possibly to mask failures."
            )
        if rt == RegressionType.RECOVERY_TIME_INCREASED:
            return (
                f"Recovery time increased on '{regression.component_id}'. "
                f"Previous: {regression.previous_value}, "
                f"Current: {regression.current_value}. "
                "Root cause: failover configuration changes or infrastructure degradation."
            )

        return f"Unknown regression type: {rt}"

    def recommend_remediation(
        self, regressions: list[Regression]
    ) -> list[RemediationStep]:
        """Generate prioritized remediation steps for a list of regressions."""
        steps: list[RemediationStep] = []
        priority = 1

        severity_order = [
            RegressionSeverity.CRITICAL,
            RegressionSeverity.MAJOR,
            RegressionSeverity.MINOR,
            RegressionSeverity.INFO,
        ]

        sorted_regressions = sorted(
            regressions,
            key=lambda r: severity_order.index(r.severity),
        )

        for reg in sorted_regressions:
            effort, impact = self._estimate_effort_impact(reg.regression_type)
            steps.append(RemediationStep(
                priority=priority,
                regression_type=reg.regression_type,
                component_id=reg.component_id,
                action=reg.recommendation,
                effort=effort,
                impact=impact,
            ))
            priority += 1

        return steps

    def calculate_regression_velocity(self, snapshots: list[InfraGraph]) -> float:
        """Calculate the rate of regression occurrence over snapshots.

        Returns regressions-per-snapshot-pair as a float.
        """
        if len(snapshots) < 2:
            return 0.0

        total_regressions = 0
        pairs = 0

        for i in range(1, len(snapshots)):
            report = self.detect_regressions(snapshots[i], snapshots[i - 1])
            total_regressions += report.total_regressions
            pairs += 1

        return round(total_regressions / pairs, 2) if pairs > 0 else 0.0

    # -- private helpers ----------------------------------------------------

    def _snapshot_graph(self, graph: InfraGraph) -> _GraphSnapshot:
        """Create an internal snapshot of a graph for comparison."""
        score = graph.resilience_score()
        comp_snapshots: dict[str, _ComponentSnapshot] = {}

        for comp_id, comp in graph.components.items():
            deps = graph.get_dependencies(comp_id)
            dependents = graph.get_dependents(comp_id)

            # Circuit breakers: check outgoing edges
            cb_list: list[str] = []
            for dep in deps:
                edge = graph.get_dependency_edge(comp_id, dep.id)
                if edge and edge.circuit_breaker.enabled:
                    cb_list.append(dep.id)

            # SLO targets
            slo_vals = [t.target for t in comp.slo_targets]

            # Recovery time
            if comp.failover.enabled:
                recovery_time = comp.failover.promotion_time_seconds
            else:
                recovery_time = comp.operational_profile.mttr_minutes * 60.0

            comp_snapshots[comp_id] = _ComponentSnapshot(
                component_id=comp_id,
                name=comp.name,
                component_type=comp.type,
                replicas=comp.replicas,
                failover_enabled=comp.failover.enabled,
                circuit_breakers=cb_list,
                dependency_ids=[d.id for d in deps],
                dependent_ids=[d.id for d in dependents],
                slo_targets=slo_vals,
                recovery_time_seconds=recovery_time,
                encryption_at_rest=comp.security.encryption_at_rest,
                encryption_in_transit=comp.security.encryption_in_transit,
                capacity_max_rps=comp.capacity.max_rps,
                capacity_max_connections=comp.capacity.max_connections,
            )

        return _GraphSnapshot(
            score=round(score, 2),
            component_snapshots=comp_snapshots,
            total_components=len(comp_snapshots),
            total_dependencies=sum(
                len(cs.dependency_ids) for cs in comp_snapshots.values()
            ),
        )

    @staticmethod
    def _determine_trend(score_delta: float) -> str:
        """Determine overall trend from score delta."""
        if score_delta > 3.0:
            return "improving"
        if score_delta < -3.0:
            return "degrading"
        return "stable"

    @staticmethod
    def _compute_trend(scores: list[float]) -> str:
        """Compute trend from a list of scores."""
        if len(scores) < 2:
            return "stable"
        mid = len(scores) // 2
        first_half = scores[:mid] if mid > 0 else scores[:1]
        second_half = scores[mid:]
        avg_first = sum(first_half) / len(first_half)
        avg_second = sum(second_half) / len(second_half)
        delta = avg_second - avg_first
        if delta > 3.0:
            return "improving"
        if delta < -3.0:
            return "degrading"
        return "stable"

    @staticmethod
    def _compute_slope(values: list[float]) -> float:
        """Compute the slope of a series of values using linear regression."""
        if len(values) < 2:
            return 0.0
        xs = list(range(len(values)))
        try:
            slope, _ = linear_regression(xs, values)
            return slope
        except Exception:
            return 0.0

    @staticmethod
    def _estimate_effort_impact(
        regression_type: RegressionType,
    ) -> tuple[str, str]:
        """Estimate effort and impact for remediating a regression type."""
        mapping: dict[RegressionType, tuple[str, str]] = {
            RegressionType.SCORE_DROP: ("high", "high"),
            RegressionType.SPOF_INTRODUCED: ("medium", "high"),
            RegressionType.CIRCUIT_BREAKER_REMOVED: ("low", "medium"),
            RegressionType.REPLICA_REDUCED: ("low", "high"),
            RegressionType.FAILOVER_DISABLED: ("low", "high"),
            RegressionType.CAPACITY_REDUCED: ("low", "medium"),
            RegressionType.DEPENDENCY_ADDED: ("medium", "low"),
            RegressionType.SECURITY_DOWNGRADE: ("medium", "high"),
            RegressionType.SLO_LOOSENED: ("low", "medium"),
            RegressionType.RECOVERY_TIME_INCREASED: ("medium", "medium"),
        }
        return mapping.get(regression_type, ("medium", "medium"))
