"""Change risk scorer — assess risk of infrastructure changes.

Evaluates proposed infrastructure changes (adding/removing components,
scaling, configuration changes) and scores the risk of each change
considering blast radius, time of day, and system criticality.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from faultray.model.components import HealthStatus
from faultray.model.graph import InfraGraph


class RiskLevel(str, Enum):
    """Risk level of a change."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    MINIMAL = "minimal"


class ChangeCategory(str, Enum):
    """Category of infrastructure change."""

    SCALE_UP = "scale_up"
    SCALE_DOWN = "scale_down"
    ADD_COMPONENT = "add_component"
    REMOVE_COMPONENT = "remove_component"
    CONFIG_CHANGE = "config_change"
    FAILOVER_TOGGLE = "failover_toggle"
    DEPENDENCY_CHANGE = "dependency_change"
    SECURITY_CHANGE = "security_change"
    MIGRATION = "migration"


@dataclass
class ProposedChange:
    """A proposed infrastructure change to evaluate."""

    category: ChangeCategory
    component_id: str
    description: str
    is_reversible: bool = True
    requires_downtime: bool = False
    is_peak_hours: bool = False


@dataclass
class RiskFactor:
    """A single risk factor contributing to overall risk."""

    name: str
    score: float  # 0-100
    weight: float  # importance multiplier
    description: str


@dataclass
class ChangeRiskAssessment:
    """Risk assessment for a single change."""

    change: ProposedChange
    risk_level: RiskLevel
    risk_score: float  # 0-100
    risk_factors: list[RiskFactor]
    blast_radius: int
    affected_components: list[str]
    requires_approval: bool
    recommended_safeguards: list[str]
    rollback_plan: str


@dataclass
class BatchRiskAssessment:
    """Risk assessment for a batch of changes."""

    assessments: list[ChangeRiskAssessment]
    overall_risk_level: RiskLevel
    overall_risk_score: float
    total_blast_radius: int
    deployment_order: list[str]  # recommended order
    can_proceed: bool
    blockers: list[str]


class ChangeRiskScorer:
    """Score risk of infrastructure changes."""

    def __init__(self, graph: InfraGraph) -> None:
        self._graph = graph

    def assess(self, change: ProposedChange) -> ChangeRiskAssessment:
        """Assess risk of a single change."""
        factors: list[RiskFactor] = []
        comp = self._graph.get_component(change.component_id)

        # Factor 1: Blast radius
        blast_radius = 0
        affected: list[str] = []
        if comp:
            affected_set = self._graph.get_all_affected(change.component_id)
            affected = list(affected_set)
            blast_radius = len(affected)

        br_score = min(blast_radius * 15, 100)
        factors.append(RiskFactor(
            name="Blast Radius",
            score=br_score,
            weight=1.5,
            description=f"{blast_radius} component(s) in blast radius",
        ))

        # Factor 2: Change category risk
        cat_scores = {
            ChangeCategory.SCALE_UP: 15,
            ChangeCategory.ADD_COMPONENT: 20,
            ChangeCategory.CONFIG_CHANGE: 30,
            ChangeCategory.DEPENDENCY_CHANGE: 40,
            ChangeCategory.SECURITY_CHANGE: 45,
            ChangeCategory.FAILOVER_TOGGLE: 50,
            ChangeCategory.SCALE_DOWN: 55,
            ChangeCategory.MIGRATION: 70,
            ChangeCategory.REMOVE_COMPONENT: 80,
        }
        cat_score = cat_scores.get(change.category, 50)
        factors.append(RiskFactor(
            name="Change Category",
            score=cat_score,
            weight=1.0,
            description=f"Category '{change.category.value}' has base risk {cat_score}",
        ))

        # Factor 3: Component criticality
        crit_score = 0
        if comp:
            dependents = self._graph.get_dependents(comp.id)
            crit_score = min(len(dependents) * 20, 100)
        factors.append(RiskFactor(
            name="Component Criticality",
            score=crit_score,
            weight=1.3,
            description=f"Component has {len(self._graph.get_dependents(change.component_id)) if comp else 0} dependent(s)",
        ))

        # Factor 4: Reversibility
        rev_score = 0 if change.is_reversible else 60
        factors.append(RiskFactor(
            name="Reversibility",
            score=rev_score,
            weight=1.2,
            description="Reversible" if change.is_reversible else "Irreversible change",
        ))

        # Factor 5: Downtime requirement
        dt_score = 70 if change.requires_downtime else 0
        factors.append(RiskFactor(
            name="Downtime Required",
            score=dt_score,
            weight=1.1,
            description="Requires downtime" if change.requires_downtime else "No downtime needed",
        ))

        # Factor 6: Peak hours
        peak_score = 40 if change.is_peak_hours else 0
        factors.append(RiskFactor(
            name="Peak Hours",
            score=peak_score,
            weight=0.8,
            description="During peak hours" if change.is_peak_hours else "Off-peak",
        ))

        # Factor 7: Current health
        health_score = 0
        if comp:
            if comp.health == HealthStatus.DOWN:
                health_score = 80
            elif comp.health == HealthStatus.OVERLOADED:
                health_score = 60
            elif comp.health == HealthStatus.DEGRADED:
                health_score = 40
        factors.append(RiskFactor(
            name="Current Health",
            score=health_score,
            weight=0.7,
            description=f"Component health: {comp.health.value if comp else 'unknown'}",
        ))

        # Calculate weighted score
        total_weight = sum(f.weight for f in factors)
        risk_score = sum(f.score * f.weight for f in factors) / total_weight

        risk_level = self._score_to_level(risk_score)
        requires_approval = risk_level in (RiskLevel.CRITICAL, RiskLevel.HIGH)

        safeguards = self._recommend_safeguards(change, risk_level, comp)
        rollback = self._generate_rollback_plan(change, comp)

        return ChangeRiskAssessment(
            change=change,
            risk_level=risk_level,
            risk_score=round(risk_score, 1),
            risk_factors=factors,
            blast_radius=blast_radius,
            affected_components=affected,
            requires_approval=requires_approval,
            recommended_safeguards=safeguards,
            rollback_plan=rollback,
        )

    def assess_batch(self, changes: list[ProposedChange]) -> BatchRiskAssessment:
        """Assess risk of multiple changes together."""
        if not changes:
            return BatchRiskAssessment(
                assessments=[],
                overall_risk_level=RiskLevel.MINIMAL,
                overall_risk_score=0,
                total_blast_radius=0,
                deployment_order=[],
                can_proceed=True,
                blockers=[],
            )

        assessments = [self.assess(c) for c in changes]

        # Overall score is max of individual scores (worst case)
        overall_score = max(a.risk_score for a in assessments)
        overall_level = self._score_to_level(overall_score)

        # Total blast radius (union of affected components)
        all_affected: set[str] = set()
        for a in assessments:
            all_affected.update(a.affected_components)

        # Deployment order: lowest risk first
        sorted_assessments = sorted(assessments, key=lambda a: a.risk_score)
        order = [a.change.component_id for a in sorted_assessments]

        # Blockers
        blockers: list[str] = []
        for a in assessments:
            if a.risk_level == RiskLevel.CRITICAL:
                blockers.append(
                    f"CRITICAL: {a.change.description} (score={a.risk_score})"
                )

        can_proceed = len(blockers) == 0

        return BatchRiskAssessment(
            assessments=assessments,
            overall_risk_level=overall_level,
            overall_risk_score=round(overall_score, 1),
            total_blast_radius=len(all_affected),
            deployment_order=order,
            can_proceed=can_proceed,
            blockers=blockers,
        )

    def _score_to_level(self, score: float) -> RiskLevel:
        """Convert risk score to level."""
        if score >= 70:
            return RiskLevel.CRITICAL
        if score >= 50:
            return RiskLevel.HIGH
        if score >= 30:
            return RiskLevel.MEDIUM
        if score >= 15:
            return RiskLevel.LOW
        return RiskLevel.MINIMAL

    def _recommend_safeguards(self, change, risk_level, comp) -> list[str]:
        """Recommend safeguards based on risk."""
        safeguards: list[str] = []

        if risk_level in (RiskLevel.CRITICAL, RiskLevel.HIGH):
            safeguards.append("Require manual approval before proceeding")

        if change.requires_downtime:
            safeguards.append("Schedule maintenance window")

        if not change.is_reversible:
            safeguards.append("Create backup before proceeding")

        if change.is_peak_hours:
            safeguards.append("Consider rescheduling to off-peak hours")

        if change.category in (ChangeCategory.SCALE_DOWN, ChangeCategory.REMOVE_COMPONENT):
            safeguards.append("Monitor error rates after change")

        if comp and comp.replicas <= 1:
            safeguards.append("Consider adding replicas before making changes")

        return safeguards

    def _generate_rollback_plan(self, change, comp) -> str:
        """Generate rollback plan for a change."""
        if change.category == ChangeCategory.SCALE_DOWN:
            return f"Scale {change.component_id} back up to original replica count"
        if change.category == ChangeCategory.SCALE_UP:
            return f"Scale {change.component_id} back down if issues observed"
        if change.category == ChangeCategory.REMOVE_COMPONENT:
            return f"Re-deploy {change.component_id} from backup/registry"
        if change.category == ChangeCategory.ADD_COMPONENT:
            return f"Remove newly added {change.component_id}"
        if change.category == ChangeCategory.CONFIG_CHANGE:
            return f"Revert configuration changes on {change.component_id}"
        if change.category == ChangeCategory.FAILOVER_TOGGLE:
            return f"Toggle failover back on {change.component_id}"
        return f"Revert changes to {change.component_id}"
