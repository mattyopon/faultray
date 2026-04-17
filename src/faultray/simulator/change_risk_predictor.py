# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Change Risk Predictor — predict resilience impact of proposed changes.

Predicts how adding, removing, or modifying infrastructure components
affects the overall resilience score *before* changes are applied.
Enables pre-deployment risk assessment in CI/CD pipelines.
"""

from __future__ import annotations

import copy
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from faultray.model.components import (
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    HealthStatus,
)
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ChangeType(str, Enum):
    """Type of infrastructure change."""

    ADD_COMPONENT = "add_component"
    REMOVE_COMPONENT = "remove_component"
    MODIFY_REPLICAS = "modify_replicas"
    MODIFY_FAILOVER = "modify_failover"
    ADD_DEPENDENCY = "add_dependency"
    REMOVE_DEPENDENCY = "remove_dependency"
    CHANGE_REGION = "change_region"
    UPGRADE_VERSION = "upgrade_version"


class RiskCategory(str, Enum):
    """Risk classification for a change."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NEGLIGIBLE = "negligible"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class ProposedChange(BaseModel):
    """A single proposed infrastructure change."""

    change_type: ChangeType
    target_component_id: str
    description: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)


class ChangeImpact(BaseModel):
    """Impact assessment for a single proposed change."""

    change: ProposedChange
    before_score: float
    after_score: float
    delta: float
    risk_category: RiskCategory
    affected_components: list[str] = Field(default_factory=list)
    blast_radius: float = 0.0  # 0-1 fraction of total components
    rollback_complexity: str = "simple"  # simple | moderate | complex


class ChangeSet(BaseModel):
    """Analysis of multiple proposed changes together."""

    changes: list[ProposedChange] = Field(default_factory=list)
    combined_impact: float = 0.0
    interaction_effects: list[str] = Field(default_factory=list)
    recommended_order: list[int] = Field(default_factory=list)


class ChangeRiskReport(BaseModel):
    """Full report for a set of proposed changes."""

    total_changes: int = 0
    impacts: list[ChangeImpact] = Field(default_factory=list)
    overall_risk: RiskCategory = RiskCategory.NEGLIGIBLE
    safe_to_proceed: bool = True
    warnings: list[str] = Field(default_factory=list)
    recommended_sequence: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Predictor
# ---------------------------------------------------------------------------


class ChangeRiskPredictor:
    """Predict resilience impact of proposed infrastructure changes."""

    def __init__(self, graph: InfraGraph) -> None:
        self._graph = graph

    # -- public API ---------------------------------------------------------

    def predict_impact(self, change: ProposedChange) -> ChangeImpact:
        """Simulate a single change and measure resilience delta."""
        before_score = self._graph.resilience_score()
        sim_graph = copy.deepcopy(self._graph)
        self._apply_change(sim_graph, change)
        after_score = sim_graph.resilience_score()
        delta = after_score - before_score

        affected = self._find_affected(change)
        total = max(len(self._graph.components), 1)
        blast = len(affected) / total

        rollback = self._rollback_complexity(change)
        risk = self.classify_risk(delta, blast)

        return ChangeImpact(
            change=change,
            before_score=round(before_score, 2),
            after_score=round(after_score, 2),
            delta=round(delta, 2),
            risk_category=risk,
            affected_components=affected,
            blast_radius=round(blast, 4),
            rollback_complexity=rollback,
        )

    def analyze_change_set(self, changes: list[ProposedChange]) -> ChangeSet:
        """Analyze multiple changes together for interactions."""
        if not changes:
            return ChangeSet()

        # Compute combined impact by applying all changes sequentially
        before = self._graph.resilience_score()
        sim = copy.deepcopy(self._graph)
        for ch in changes:
            self._apply_change(sim, ch)
        after = sim.resilience_score()
        combined = round(after - before, 2)

        # Detect interaction effects
        interactions: list[str] = []
        individual_sum = 0.0
        for ch in changes:
            impact = self.predict_impact(ch)
            individual_sum += impact.delta

        individual_sum = round(individual_sum, 2)
        if abs(combined - individual_sum) > 0.5:
            interactions.append(
                f"Combined delta ({combined}) differs from sum of individual "
                f"deltas ({individual_sum}); changes interact."
            )

        # Check for conflicting targets
        targets = [ch.target_component_id for ch in changes]
        seen: set[str] = set()
        for t in targets:
            if t in seen:
                interactions.append(
                    f"Multiple changes target component '{t}'; review order."
                )
            seen.add(t)

        # Recommend ordering: improvements first, then risky changes
        impacts = [self.predict_impact(ch) for ch in changes]
        indexed = list(enumerate(impacts))
        indexed.sort(key=lambda x: x[1].delta, reverse=True)
        order = [i for i, _ in indexed]

        return ChangeSet(
            changes=changes,
            combined_impact=combined,
            interaction_effects=interactions,
            recommended_order=order,
        )

    def classify_risk(self, delta: float, blast_radius: float) -> RiskCategory:
        """Classify overall risk from delta and blast radius."""
        # Larger negative delta = worse
        severity = abs(min(delta, 0))
        if severity >= 20 or blast_radius >= 0.8:
            return RiskCategory.CRITICAL
        if severity >= 10 or blast_radius >= 0.5:
            return RiskCategory.HIGH
        if severity >= 5 or blast_radius >= 0.3:
            return RiskCategory.MEDIUM
        if severity >= 1 or blast_radius >= 0.1:
            return RiskCategory.LOW
        return RiskCategory.NEGLIGIBLE

    def suggest_rollback_plan(self, change: ProposedChange) -> str:
        """Generate a human-readable rollback description."""
        ctype = change.change_type
        cid = change.target_component_id
        if ctype == ChangeType.ADD_COMPONENT:
            return f"Remove the newly added component '{cid}' and its dependencies."
        if ctype == ChangeType.REMOVE_COMPONENT:
            return f"Re-deploy component '{cid}' from backup or registry and restore dependencies."
        if ctype == ChangeType.MODIFY_REPLICAS:
            original = change.parameters.get("old_replicas", "original")
            return f"Revert replicas of '{cid}' to {original}."
        if ctype == ChangeType.MODIFY_FAILOVER:
            return f"Toggle failover back to previous state on '{cid}'."
        if ctype == ChangeType.ADD_DEPENDENCY:
            target = change.parameters.get("target_id", "target")
            return f"Remove the new dependency from '{cid}' to '{target}'."
        if ctype == ChangeType.REMOVE_DEPENDENCY:
            target = change.parameters.get("target_id", "target")
            return f"Re-add the dependency from '{cid}' to '{target}'."
        if ctype == ChangeType.CHANGE_REGION:
            old_region = change.parameters.get("old_region", "original region")
            return f"Move '{cid}' back to {old_region}."
        if ctype == ChangeType.UPGRADE_VERSION:
            old_ver = change.parameters.get("old_version", "previous version")
            return f"Downgrade '{cid}' back to {old_ver}."
        return f"Revert changes to '{cid}'."

    def gate_check(
        self, changes: list[ProposedChange], threshold: RiskCategory
    ) -> bool:
        """CI/CD gate: return True if ALL changes are within threshold."""
        rank = _risk_rank(threshold)
        for ch in changes:
            impact = self.predict_impact(ch)
            if _risk_rank(impact.risk_category) > rank:
                return False
        return True

    def generate_report(self, changes: list[ProposedChange]) -> ChangeRiskReport:
        """Produce a full risk report for a list of proposed changes."""
        if not changes:
            return ChangeRiskReport()

        impacts = [self.predict_impact(ch) for ch in changes]
        warnings: list[str] = []

        worst = RiskCategory.NEGLIGIBLE
        for imp in impacts:
            if _risk_rank(imp.risk_category) > _risk_rank(worst):
                worst = imp.risk_category
            if imp.delta < -10:
                warnings.append(
                    f"Change '{imp.change.target_component_id}' causes significant "
                    f"resilience drop ({imp.delta})."
                )
            if imp.blast_radius > 0.5:
                warnings.append(
                    f"Change '{imp.change.target_component_id}' has large blast "
                    f"radius ({imp.blast_radius:.0%})."
                )
            if imp.rollback_complexity == "complex":
                warnings.append(
                    f"Change '{imp.change.target_component_id}' has complex rollback."
                )

        safe = _risk_rank(worst) <= _risk_rank(RiskCategory.MEDIUM)

        # Recommended sequence: positive-delta first
        sorted_impacts = sorted(impacts, key=lambda i: i.delta, reverse=True)
        sequence = [si.change.target_component_id for si in sorted_impacts]

        return ChangeRiskReport(
            total_changes=len(changes),
            impacts=impacts,
            overall_risk=worst,
            safe_to_proceed=safe,
            warnings=warnings,
            recommended_sequence=sequence,
        )

    # -- private helpers ----------------------------------------------------

    def _apply_change(self, graph: InfraGraph, change: ProposedChange) -> None:
        """Apply a proposed change to a *cloned* graph."""
        ctype = change.change_type
        cid = change.target_component_id

        if ctype == ChangeType.ADD_COMPONENT:
            comp_type_str = change.parameters.get("component_type", "app_server")
            comp_type = ComponentType(comp_type_str)
            replicas = int(change.parameters.get("replicas", 1))
            new_comp = Component(
                id=cid,
                name=change.parameters.get("name", cid),
                type=comp_type,
                replicas=replicas,
            )
            graph.add_component(new_comp)

        elif ctype == ChangeType.REMOVE_COMPONENT:
            comp = graph.get_component(cid)
            if comp:
                comp.health = HealthStatus.DOWN
                comp.replicas = 1  # cannot set to 0 due to validator
                comp.failover = FailoverConfig(enabled=False)

        elif ctype == ChangeType.MODIFY_REPLICAS:
            comp = graph.get_component(cid)
            if comp:
                new_replicas = int(change.parameters.get("new_replicas", comp.replicas))
                comp.replicas = max(1, new_replicas)

        elif ctype == ChangeType.MODIFY_FAILOVER:
            comp = graph.get_component(cid)
            if comp:
                enabled = bool(change.parameters.get("enabled", not comp.failover.enabled))
                comp.failover = FailoverConfig(enabled=enabled)

        elif ctype == ChangeType.ADD_DEPENDENCY:
            target = change.parameters.get("target_id", "")
            if target:
                dep_type = change.parameters.get("dependency_type", "requires")
                graph.add_dependency(
                    Dependency(
                        source_id=cid,
                        target_id=target,
                        dependency_type=dep_type,
                    )
                )

        elif ctype == ChangeType.REMOVE_DEPENDENCY:
            # NetworkX edge removal on the cloned graph
            target = change.parameters.get("target_id", "")
            if target and graph._graph.has_edge(cid, target):
                graph._graph.remove_edge(cid, target)

        elif ctype == ChangeType.CHANGE_REGION:
            comp = graph.get_component(cid)
            if comp:
                comp.region.region = str(change.parameters.get("new_region", ""))

        elif ctype == ChangeType.UPGRADE_VERSION:
            # Version upgrade doesn't change topology; no score impact by default
            pass

    def _find_affected(self, change: ProposedChange) -> list[str]:
        """Return list of component IDs affected by this change."""
        cid = change.target_component_id
        ctype = change.change_type

        if ctype == ChangeType.ADD_COMPONENT:
            return [cid]

        comp = self._graph.get_component(cid)
        if not comp:
            return []

        if ctype in (
            ChangeType.REMOVE_COMPONENT,
            ChangeType.MODIFY_REPLICAS,
            ChangeType.MODIFY_FAILOVER,
            ChangeType.CHANGE_REGION,
            ChangeType.UPGRADE_VERSION,
        ):
            affected = self._graph.get_all_affected(cid)
            return [cid] + sorted(affected)

        if ctype == ChangeType.ADD_DEPENDENCY:
            target = change.parameters.get("target_id", "")
            result = [cid]
            if target:
                result.append(target)
            return result

        if ctype == ChangeType.REMOVE_DEPENDENCY:
            target = change.parameters.get("target_id", "")
            result = [cid]
            if target:
                result.append(target)
            return result

        return [cid]

    def _rollback_complexity(self, change: ProposedChange) -> str:
        """Determine rollback complexity for a change."""
        ctype = change.change_type
        if ctype in (ChangeType.MODIFY_REPLICAS, ChangeType.MODIFY_FAILOVER):
            return "simple"
        if ctype in (
            ChangeType.ADD_DEPENDENCY,
            ChangeType.REMOVE_DEPENDENCY,
            ChangeType.CHANGE_REGION,
            ChangeType.UPGRADE_VERSION,
        ):
            return "moderate"
        if ctype in (ChangeType.ADD_COMPONENT, ChangeType.REMOVE_COMPONENT):
            return "complex"
        return "moderate"


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

_RISK_ORDER = {
    RiskCategory.NEGLIGIBLE: 0,
    RiskCategory.LOW: 1,
    RiskCategory.MEDIUM: 2,
    RiskCategory.HIGH: 3,
    RiskCategory.CRITICAL: 4,
}


def _risk_rank(cat: RiskCategory) -> int:
    return _RISK_ORDER.get(cat, 0)
