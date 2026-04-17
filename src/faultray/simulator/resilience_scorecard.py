# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Resilience scorecard — executive-level infrastructure health report.

Provides a simple, actionable scorecard that rates infrastructure
across multiple resilience dimensions. Designed for CTO/VP-level
reporting with clear grades and prioritized action items.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from faultray.model.components import ComponentType, HealthStatus
from faultray.model.graph import InfraGraph


class Grade(str, Enum):
    """Letter grades for resilience dimensions."""

    A_PLUS = "A+"
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    F = "F"


class Dimension(str, Enum):
    """Resilience assessment dimensions."""

    AVAILABILITY = "availability"
    REDUNDANCY = "redundancy"
    FAULT_TOLERANCE = "fault_tolerance"
    SCALABILITY = "scalability"
    SECURITY_POSTURE = "security_posture"
    OBSERVABILITY = "observability"
    RECOVERY = "recovery"
    DEPENDENCY_HEALTH = "dependency_health"


# Dimension descriptions
_DIMENSION_DESCRIPTIONS: dict[Dimension, str] = {
    Dimension.AVAILABILITY: "Overall system uptime and health status",
    Dimension.REDUNDANCY: "Replication and elimination of single points of failure",
    Dimension.FAULT_TOLERANCE: "Ability to handle component failures gracefully",
    Dimension.SCALABILITY: "Capacity to handle increased load automatically",
    Dimension.SECURITY_POSTURE: "Security controls and data protection",
    Dimension.OBSERVABILITY: "Monitoring, logging, and alerting coverage",
    Dimension.RECOVERY: "Backup and disaster recovery readiness",
    Dimension.DEPENDENCY_HEALTH: "Health and management of dependencies",
}


@dataclass
class DimensionScore:
    """Score for a single resilience dimension."""

    dimension: Dimension
    description: str
    score: float  # 0-100
    grade: Grade
    findings: list[str]
    recommendations: list[str]
    component_scores: dict[str, float]  # component_id → score


@dataclass
class ActionItem:
    """A prioritized action item."""

    priority: int  # 1 = highest
    dimension: Dimension
    action: str
    impact: str
    effort: str  # "low", "medium", "high"
    components_affected: list[str]


@dataclass
class Scorecard:
    """Complete resilience scorecard."""

    overall_score: float  # 0-100
    overall_grade: Grade
    dimension_scores: list[DimensionScore]
    action_items: list[ActionItem]
    total_components: int
    healthy_components: int
    at_risk_components: int
    strengths: list[str]
    weaknesses: list[str]
    executive_summary: str


class ResilienceScorecard:
    """Generate executive-level resilience scorecards."""

    def __init__(self, graph: InfraGraph) -> None:
        self._graph = graph

    def generate(self) -> Scorecard:
        """Generate a complete resilience scorecard."""
        if not self._graph.components:
            return Scorecard(
                overall_score=0.0,
                overall_grade=Grade.F,
                dimension_scores=[],
                action_items=[],
                total_components=0,
                healthy_components=0,
                at_risk_components=0,
                strengths=[],
                weaknesses=[],
                executive_summary="No infrastructure components to assess.",
            )

        # Score each dimension
        dimension_scores = [
            self._score_availability(),
            self._score_redundancy(),
            self._score_fault_tolerance(),
            self._score_scalability(),
            self._score_security_posture(),
            self._score_observability(),
            self._score_recovery(),
            self._score_dependency_health(),
        ]

        # Calculate overall score (weighted average)
        weights = {
            Dimension.AVAILABILITY: 2.0,
            Dimension.REDUNDANCY: 1.5,
            Dimension.FAULT_TOLERANCE: 1.5,
            Dimension.SCALABILITY: 1.0,
            Dimension.SECURITY_POSTURE: 1.5,
            Dimension.OBSERVABILITY: 1.0,
            Dimension.RECOVERY: 1.5,
            Dimension.DEPENDENCY_HEALTH: 1.0,
        }

        weighted_sum = sum(
            ds.score * weights.get(ds.dimension, 1.0) for ds in dimension_scores
        )
        total_weight = sum(weights.get(ds.dimension, 1.0) for ds in dimension_scores)
        overall = weighted_sum / total_weight if total_weight > 0 else 0.0

        # Component health counts
        total = len(self._graph.components)
        healthy = sum(
            1
            for c in self._graph.components.values()
            if c.health == HealthStatus.HEALTHY
        )
        at_risk = total - healthy

        # Build action items
        action_items = self._build_action_items(dimension_scores)

        # Identify strengths/weaknesses
        strengths = [
            f"{ds.dimension.value}: {ds.grade.value}"
            for ds in dimension_scores
            if ds.score >= 80
        ]
        weaknesses = [
            f"{ds.dimension.value}: {ds.grade.value}"
            for ds in dimension_scores
            if ds.score < 50
        ]

        summary = self._build_summary(overall, dimension_scores, action_items)

        return Scorecard(
            overall_score=round(overall, 1),
            overall_grade=self._score_to_grade(overall),
            dimension_scores=dimension_scores,
            action_items=action_items,
            total_components=total,
            healthy_components=healthy,
            at_risk_components=at_risk,
            strengths=strengths,
            weaknesses=weaknesses,
            executive_summary=summary,
        )

    # ------------------------------------------------------------------
    # Dimension scoring methods
    # ------------------------------------------------------------------

    def _score_availability(self) -> DimensionScore:
        """Score overall availability based on component health."""
        findings: list[str] = []
        recs: list[str] = []
        comp_scores: dict[str, float] = {}

        for comp in self._graph.components.values():
            health_scores = {
                HealthStatus.HEALTHY: 100,
                HealthStatus.DEGRADED: 50,
                HealthStatus.OVERLOADED: 25,
                HealthStatus.DOWN: 0,
            }
            s = health_scores.get(comp.health, 0)
            comp_scores[comp.id] = s

            if comp.health != HealthStatus.HEALTHY:
                findings.append(f"{comp.name}: {comp.health.value}")
                if comp.health == HealthStatus.DOWN:
                    recs.append(f"CRITICAL: Restore {comp.name} immediately")
                elif comp.health == HealthStatus.OVERLOADED:
                    recs.append(f"Scale {comp.name} to reduce load")

        avg = sum(comp_scores.values()) / len(comp_scores) if comp_scores else 0
        if not findings:
            findings.append("All components healthy")

        return DimensionScore(
            dimension=Dimension.AVAILABILITY,
            description=_DIMENSION_DESCRIPTIONS[Dimension.AVAILABILITY],
            score=round(avg, 1),
            grade=self._score_to_grade(avg),
            findings=findings,
            recommendations=recs[:3],
            component_scores=comp_scores,
        )

    def _score_redundancy(self) -> DimensionScore:
        """Score redundancy based on replica counts and SPOFs."""
        findings: list[str] = []
        recs: list[str] = []
        comp_scores: dict[str, float] = {}

        for comp in self._graph.components.values():
            if comp.replicas >= 3:
                s = 100.0
            elif comp.replicas == 2:
                s = 70.0
            else:
                s = 20.0
                dependents = self._graph.get_dependents(comp.id)
                if dependents:
                    findings.append(
                        f"SPOF: {comp.name} (1 replica, {len(dependents)} dependents)"
                    )
                    recs.append(f"Add replica to {comp.name}")
                    s = 10.0
                else:
                    findings.append(f"{comp.name}: single replica")

            comp_scores[comp.id] = s

        avg = sum(comp_scores.values()) / len(comp_scores) if comp_scores else 0
        if not findings:
            findings.append("All components have redundancy")

        return DimensionScore(
            dimension=Dimension.REDUNDANCY,
            description=_DIMENSION_DESCRIPTIONS[Dimension.REDUNDANCY],
            score=round(avg, 1),
            grade=self._score_to_grade(avg),
            findings=findings,
            recommendations=recs[:3],
            component_scores=comp_scores,
        )

    def _score_fault_tolerance(self) -> DimensionScore:
        """Score fault tolerance based on failover and circuit breakers."""
        findings: list[str] = []
        recs: list[str] = []
        comp_scores: dict[str, float] = {}

        for comp in self._graph.components.values():
            s = 0.0
            if comp.failover.enabled:
                s += 50.0
                if comp.failover.promotion_time_seconds <= 30:
                    s += 20.0
                    findings.append(f"{comp.name}: fast failover ({comp.failover.promotion_time_seconds}s)")
                else:
                    s += 10.0
            else:
                recs.append(f"Enable failover for {comp.name}")

            if comp.replicas >= 2:
                s += 30.0

            comp_scores[comp.id] = min(100.0, s)

        avg = sum(comp_scores.values()) / len(comp_scores) if comp_scores else 0
        if not findings and not recs:
            findings.append("No fault tolerance issues detected")

        return DimensionScore(
            dimension=Dimension.FAULT_TOLERANCE,
            description=_DIMENSION_DESCRIPTIONS[Dimension.FAULT_TOLERANCE],
            score=round(avg, 1),
            grade=self._score_to_grade(avg),
            findings=findings,
            recommendations=recs[:3],
            component_scores=comp_scores,
        )

    def _score_scalability(self) -> DimensionScore:
        """Score scalability based on autoscaling and resource headroom."""
        findings: list[str] = []
        recs: list[str] = []
        comp_scores: dict[str, float] = {}

        for comp in self._graph.components.values():
            s = 0.0

            # Autoscaling
            if comp.autoscaling.enabled:
                s += 50.0
            else:
                if comp.metrics.cpu_percent > 60:
                    recs.append(f"Enable autoscaling for {comp.name} (CPU: {comp.metrics.cpu_percent}%)")

            # Resource headroom
            cpu_headroom = max(0, 100 - comp.metrics.cpu_percent)
            mem_headroom = max(0, 100 - comp.metrics.memory_percent)
            avg_headroom = (cpu_headroom + mem_headroom) / 2
            s += avg_headroom * 0.5  # Up to 50 points for headroom

            comp_scores[comp.id] = min(100.0, s)

            if avg_headroom < 20:
                findings.append(f"{comp.name}: low headroom (CPU:{cpu_headroom:.0f}%, Mem:{mem_headroom:.0f}%)")

        avg = sum(comp_scores.values()) / len(comp_scores) if comp_scores else 0
        if not findings:
            findings.append("Adequate resource headroom across all components")

        return DimensionScore(
            dimension=Dimension.SCALABILITY,
            description=_DIMENSION_DESCRIPTIONS[Dimension.SCALABILITY],
            score=round(avg, 1),
            grade=self._score_to_grade(avg),
            findings=findings,
            recommendations=recs[:3],
            component_scores=comp_scores,
        )

    def _score_security_posture(self) -> DimensionScore:
        """Score security based on encryption, WAF, rate limiting, etc."""
        findings: list[str] = []
        recs: list[str] = []
        comp_scores: dict[str, float] = {}

        for comp in self._graph.components.values():
            s = 0.0
            checks = 0

            if comp.security.encryption_at_rest:
                s += 20
            else:
                if comp.type in (ComponentType.DATABASE, ComponentType.STORAGE):
                    recs.append(f"Enable encryption at rest for {comp.name}")
            checks += 1

            if comp.security.encryption_in_transit:
                s += 20
            checks += 1

            if comp.security.waf_protected:
                s += 20
            checks += 1

            if comp.security.rate_limiting:
                s += 20
            checks += 1

            if comp.security.auth_required:
                s += 20
            checks += 1

            comp_scores[comp.id] = s

            missing = []
            if not comp.security.encryption_at_rest:
                missing.append("encryption_at_rest")
            if not comp.security.encryption_in_transit:
                missing.append("encryption_in_transit")
            if missing and comp.type in (ComponentType.DATABASE, ComponentType.STORAGE):
                findings.append(f"{comp.name}: missing {', '.join(missing)}")

        avg = sum(comp_scores.values()) / len(comp_scores) if comp_scores else 0
        if not findings:
            findings.append("Security controls configured across all components")

        return DimensionScore(
            dimension=Dimension.SECURITY_POSTURE,
            description=_DIMENSION_DESCRIPTIONS[Dimension.SECURITY_POSTURE],
            score=round(avg, 1),
            grade=self._score_to_grade(avg),
            findings=findings,
            recommendations=recs[:3],
            component_scores=comp_scores,
        )

    def _score_observability(self) -> DimensionScore:
        """Score observability based on logging and monitoring."""
        findings: list[str] = []
        recs: list[str] = []
        comp_scores: dict[str, float] = {}

        for comp in self._graph.components.values():
            s = 0.0

            if comp.security.log_enabled:
                s += 50
            else:
                findings.append(f"{comp.name}: logging not enabled")
                recs.append(f"Enable logging for {comp.name}")

            if comp.security.ids_monitored:
                s += 50
            else:
                if not comp.security.log_enabled:
                    recs.append(f"Enable IDS monitoring for {comp.name}")

            comp_scores[comp.id] = s

        avg = sum(comp_scores.values()) / len(comp_scores) if comp_scores else 0
        if not findings:
            findings.append("Full observability coverage")

        return DimensionScore(
            dimension=Dimension.OBSERVABILITY,
            description=_DIMENSION_DESCRIPTIONS[Dimension.OBSERVABILITY],
            score=round(avg, 1),
            grade=self._score_to_grade(avg),
            findings=findings,
            recommendations=recs[:3],
            component_scores=comp_scores,
        )

    def _score_recovery(self) -> DimensionScore:
        """Score recovery readiness based on backups."""
        findings: list[str] = []
        recs: list[str] = []
        comp_scores: dict[str, float] = {}

        data_types = {ComponentType.DATABASE, ComponentType.STORAGE, ComponentType.CACHE}

        for comp in self._graph.components.values():
            s = 50.0  # Base score

            if comp.type in data_types:
                if comp.security.backup_enabled:
                    s += 50.0
                else:
                    s = 20.0
                    findings.append(f"{comp.name}: no backup configured")
                    recs.append(f"Enable automated backup for {comp.name}")
            else:
                # Non-data components get credit for replicas
                if comp.replicas >= 2:
                    s += 30.0
                if comp.failover.enabled:
                    s += 20.0

            comp_scores[comp.id] = min(100.0, s)

        avg = sum(comp_scores.values()) / len(comp_scores) if comp_scores else 0
        if not findings:
            findings.append("All data stores have backup configured")

        return DimensionScore(
            dimension=Dimension.RECOVERY,
            description=_DIMENSION_DESCRIPTIONS[Dimension.RECOVERY],
            score=round(avg, 1),
            grade=self._score_to_grade(avg),
            findings=findings,
            recommendations=recs[:3],
            component_scores=comp_scores,
        )

    def _score_dependency_health(self) -> DimensionScore:
        """Score dependency management and health."""
        findings: list[str] = []
        recs: list[str] = []
        comp_scores: dict[str, float] = {}

        for comp in self._graph.components.values():
            deps = self._graph.get_dependencies(comp.id)
            if not deps:
                comp_scores[comp.id] = 100.0
                continue

            # Score based on dependency health
            dep_scores = []
            for dep in deps:
                if dep.health == HealthStatus.HEALTHY:
                    dep_scores.append(100.0)
                elif dep.health == HealthStatus.DEGRADED:
                    dep_scores.append(50.0)
                    findings.append(f"{comp.name}: dependency {dep.name} is degraded")
                elif dep.health == HealthStatus.OVERLOADED:
                    dep_scores.append(25.0)
                    findings.append(f"{comp.name}: dependency {dep.name} is overloaded")
                else:
                    dep_scores.append(0.0)
                    findings.append(f"{comp.name}: dependency {dep.name} is DOWN")
                    recs.append(f"Restore {dep.name} — blocks {comp.name}")

            avg_dep = sum(dep_scores) / len(dep_scores) if dep_scores else 100.0
            comp_scores[comp.id] = avg_dep

        avg = sum(comp_scores.values()) / len(comp_scores) if comp_scores else 0
        if not findings:
            findings.append("All dependencies healthy")

        return DimensionScore(
            dimension=Dimension.DEPENDENCY_HEALTH,
            description=_DIMENSION_DESCRIPTIONS[Dimension.DEPENDENCY_HEALTH],
            score=round(avg, 1),
            grade=self._score_to_grade(avg),
            findings=findings,
            recommendations=recs[:3],
            component_scores=comp_scores,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _score_to_grade(score: float) -> Grade:
        """Convert numeric score to letter grade."""
        if score >= 95:
            return Grade.A_PLUS
        elif score >= 80:
            return Grade.A
        elif score >= 65:
            return Grade.B
        elif score >= 50:
            return Grade.C
        elif score >= 30:
            return Grade.D
        else:
            return Grade.F

    def _build_action_items(
        self, dimension_scores: list[DimensionScore]
    ) -> list[ActionItem]:
        """Build prioritized action items from dimension recommendations."""
        items: list[ActionItem] = []
        priority = 0

        # Sort dimensions by score ascending (worst first)
        sorted_dims = sorted(dimension_scores, key=lambda d: d.score)

        for ds in sorted_dims:
            for rec in ds.recommendations:
                priority += 1
                # Determine effort level
                if any(
                    word in rec.lower()
                    for word in ["restore", "critical", "immediately"]
                ):
                    effort = "low"
                    impact = "Critical — immediate action required"
                elif any(
                    word in rec.lower()
                    for word in ["enable", "add replica", "scale"]
                ):
                    effort = "medium"
                    impact = "High — improves resilience score"
                else:
                    effort = "high"
                    impact = "Moderate — long-term improvement"

                # Find affected components
                affected = [
                    cid
                    for cid, score in ds.component_scores.items()
                    if score < 50
                ]

                items.append(
                    ActionItem(
                        priority=priority,
                        dimension=ds.dimension,
                        action=rec,
                        impact=impact,
                        effort=effort,
                        components_affected=affected[:5],
                    )
                )

        return items[:10]

    def _build_summary(
        self,
        overall: float,
        dimensions: list[DimensionScore],
        actions: list[ActionItem],
    ) -> str:
        """Build an executive summary."""
        grade = self._score_to_grade(overall)

        strong = [d for d in dimensions if d.score >= 80]
        weak = [d for d in dimensions if d.score < 50]

        parts = [f"Overall resilience: {grade.value} ({overall:.0f}/100)."]

        if strong:
            parts.append(
                f"Strong: {', '.join(d.dimension.value for d in strong)}."
            )

        if weak:
            parts.append(
                f"Needs attention: {', '.join(d.dimension.value for d in weak)}."
            )

        if actions:
            parts.append(f"{len(actions)} action item{'s' if len(actions) > 1 else ''} identified.")

        return " ".join(parts)
