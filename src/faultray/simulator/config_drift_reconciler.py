# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Configuration Drift Reconciler Engine.

Detects and reconciles configuration drift between desired state (IaC/GitOps)
and actual runtime state.  Compares field-by-field, scores risk, recommends
reconciliation actions, simulates applying them, and generates full reports.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from faultray.model.components import Component
from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class DriftSource(str, Enum):
    """Origin of a configuration drift."""

    MANUAL_CHANGE = "manual_change"
    AUTO_SCALING_EVENT = "auto_scaling_event"
    FAILOVER_EVENT = "failover_event"
    HOTFIX = "hotfix"
    CONFIG_MANAGEMENT_FAILURE = "config_management_failure"
    OPERATOR_ERROR = "operator_error"
    MIGRATION_INCOMPLETE = "migration_incomplete"
    ENVIRONMENT_PROMOTION = "environment_promotion"


class ReconciliationAction(str, Enum):
    """Action to take for reconciling a drifted field."""

    APPLY_DESIRED = "apply_desired"
    ACCEPT_ACTUAL = "accept_actual"
    MERGE = "merge"
    ROLLBACK = "rollback"
    FLAG_FOR_REVIEW = "flag_for_review"
    AUTO_REMEDIATE = "auto_remediate"


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------


class ConfigField(BaseModel):
    """A single drifted configuration field."""

    path: str
    desired_value: str
    actual_value: str
    drift_source: DriftSource
    last_changed: str
    risk_level: str


class ReconciliationStep(BaseModel):
    """One step of a reconciliation plan for a drifted field."""

    field_path: str
    action: ReconciliationAction
    rationale: str
    risk: str
    rollback_safe: bool


class DriftAnalysis(BaseModel):
    """Analysis of configuration drift for a single component."""

    component_id: str
    total_fields_checked: int
    drifted_fields: list[ConfigField] = Field(default_factory=list)
    drift_percentage: float = 0.0
    risk_score: float = 0.0
    recommended_actions: list[ReconciliationStep] = Field(default_factory=list)


class ReconciliationResult(BaseModel):
    """Outcome of simulating or applying reconciliation actions."""

    component_id: str
    steps_applied: int = 0
    steps_failed: int = 0
    fields_reconciled: list[str] = Field(default_factory=list)
    fields_remaining: list[str] = Field(default_factory=list)
    risk_before: float = 0.0
    risk_after: float = 0.0
    success: bool = True


class DriftReport(BaseModel):
    """Full drift report across all analysed components."""

    total_components: int = 0
    components_with_drift: int = 0
    total_drifted_fields: int = 0
    overall_risk_score: float = 0.0
    analyses: list[DriftAnalysis] = Field(default_factory=list)
    reconciliation_order: list[str] = Field(default_factory=list)
    summary: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Fields to inspect on every Component (dotted-path, getter)
_FIELD_SPECS: list[tuple[str, Any]] = [
    ("replicas", lambda c: str(c.replicas)),
    ("capacity.max_rps", lambda c: str(c.capacity.max_rps)),
    ("capacity.max_connections", lambda c: str(c.capacity.max_connections)),
    ("capacity.max_memory_mb", lambda c: str(int(c.capacity.max_memory_mb))),
    ("capacity.max_disk_gb", lambda c: str(int(c.capacity.max_disk_gb))),
    ("capacity.timeout_seconds", lambda c: str(c.capacity.timeout_seconds)),
    ("autoscaling.enabled", lambda c: str(c.autoscaling.enabled)),
    ("autoscaling.min_replicas", lambda c: str(c.autoscaling.min_replicas)),
    ("autoscaling.max_replicas", lambda c: str(c.autoscaling.max_replicas)),
    ("failover.enabled", lambda c: str(c.failover.enabled)),
    ("failover.promotion_time_seconds", lambda c: str(c.failover.promotion_time_seconds)),
    ("failover.health_check_interval_seconds",
     lambda c: str(c.failover.health_check_interval_seconds)),
    ("health", lambda c: c.health.value),
    ("type", lambda c: c.type.value),
]

_RISK_WEIGHTS: dict[str, float] = {
    "replicas": 15.0,
    "capacity.max_rps": 10.0,
    "capacity.max_connections": 8.0,
    "capacity.max_memory_mb": 6.0,
    "capacity.max_disk_gb": 4.0,
    "capacity.timeout_seconds": 5.0,
    "autoscaling.enabled": 12.0,
    "autoscaling.min_replicas": 7.0,
    "autoscaling.max_replicas": 7.0,
    "failover.enabled": 14.0,
    "failover.promotion_time_seconds": 6.0,
    "failover.health_check_interval_seconds": 5.0,
    "health": 10.0,
    "type": 3.0,
}

_SAFE_ACTIONS: set[ReconciliationAction] = {
    ReconciliationAction.APPLY_DESIRED,
    ReconciliationAction.ACCEPT_ACTUAL,
    ReconciliationAction.AUTO_REMEDIATE,
}


def _infer_drift_source(path: str, desired: str, actual: str) -> DriftSource:
    """Heuristically infer the most likely drift source."""
    if path == "replicas":
        try:
            if int(actual) > int(desired):
                return DriftSource.AUTO_SCALING_EVENT
        except ValueError:
            pass
        return DriftSource.MANUAL_CHANGE
    if path.startswith("failover.") and actual != desired:
        return DriftSource.FAILOVER_EVENT
    if path.startswith("autoscaling.") and actual != desired:
        return DriftSource.AUTO_SCALING_EVENT
    if path == "health":
        return DriftSource.FAILOVER_EVENT
    if path == "type":
        return DriftSource.MIGRATION_INCOMPLETE
    return DriftSource.MANUAL_CHANGE


def _risk_level_label(score: float) -> str:
    if score >= 70:
        return "critical"
    if score >= 50:
        return "high"
    if score >= 30:
        return "medium"
    return "low"


def _field_risk(path: str) -> float:
    return _RISK_WEIGHTS.get(path, 5.0)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class ConfigDriftReconcilerEngine:
    """Stateless engine for detecting and reconciling configuration drift."""

    # -- public API ---------------------------------------------------------

    def analyze_drift(
        self,
        graph: InfraGraph,
        desired_graph: InfraGraph,
    ) -> list[DriftAnalysis]:
        """Compare *actual* graph against *desired* graph, per component."""
        analyses: list[DriftAnalysis] = []
        all_ids = set(graph.components.keys()) | set(desired_graph.components.keys())

        for cid in sorted(all_ids):
            actual = graph.get_component(cid)
            desired = desired_graph.get_component(cid)

            if actual is None or desired is None:
                # Component exists only in one side — emit a single synthetic drift field.
                analysis = self._missing_component_analysis(cid, actual, desired)
                analyses.append(analysis)
                continue

            drifted = self.detect_field_drift(actual, desired)
            total_fields = len(_FIELD_SPECS)
            pct = (len(drifted) / total_fields * 100.0) if total_fields else 0.0
            risk = self.calculate_drift_risk(drifted)
            analysis = DriftAnalysis(
                component_id=cid,
                total_fields_checked=total_fields,
                drifted_fields=drifted,
                drift_percentage=round(pct, 2),
                risk_score=round(risk, 2),
            )
            analysis.recommended_actions = self.recommend_reconciliation(analysis)
            analyses.append(analysis)

        return analyses

    def detect_field_drift(
        self,
        component: Component,
        desired_component: Component,
    ) -> list[ConfigField]:
        """Field-level diff between an actual and desired component."""
        drifted: list[ConfigField] = []
        for path, getter in _FIELD_SPECS:
            actual_val = getter(component)
            desired_val = getter(desired_component)
            if actual_val != desired_val:
                source = _infer_drift_source(path, desired_val, actual_val)
                weight = _field_risk(path)
                drifted.append(
                    ConfigField(
                        path=path,
                        desired_value=desired_val,
                        actual_value=actual_val,
                        drift_source=source,
                        last_changed="unknown",
                        risk_level=_risk_level_label(weight * 5),
                    )
                )
        return drifted

    def recommend_reconciliation(
        self,
        drift_analysis: DriftAnalysis,
    ) -> list[ReconciliationStep]:
        """Produce reconciliation steps for every drifted field."""
        steps: list[ReconciliationStep] = []
        for cf in drift_analysis.drifted_fields:
            action, rationale, risk, rollback_safe = self._pick_action(cf)
            steps.append(
                ReconciliationStep(
                    field_path=cf.path,
                    action=action,
                    rationale=rationale,
                    risk=risk,
                    rollback_safe=rollback_safe,
                )
            )
        return steps

    def simulate_reconciliation(
        self,
        graph: InfraGraph,
        desired_graph: InfraGraph,
        actions: list[ReconciliationStep],
    ) -> ReconciliationResult:
        """Simulate applying reconciliation actions (dry-run)."""
        reconciled: list[str] = []
        remaining: list[str] = []
        failed = 0

        analyses = self.analyze_drift(graph, desired_graph)
        risk_before = self.calculate_drift_risk(
            [f for a in analyses for f in a.drifted_fields]
        )

        action_map: dict[str, ReconciliationStep] = {s.field_path: s for s in actions}

        for a in analyses:
            for cf in a.drifted_fields:
                step = action_map.get(cf.path)
                if step is None:
                    remaining.append(cf.path)
                    continue
                if step.action == ReconciliationAction.FLAG_FOR_REVIEW:
                    remaining.append(cf.path)
                    continue
                if step.action == ReconciliationAction.ROLLBACK and not step.rollback_safe:
                    failed += 1
                    remaining.append(cf.path)
                    continue
                reconciled.append(cf.path)

        risk_after = risk_before * max(0.0, 1.0 - len(reconciled) / max(len(reconciled) + len(remaining), 1))

        # Determine component_id (use first analysis or empty)
        cid = analyses[0].component_id if analyses else ""

        return ReconciliationResult(
            component_id=cid,
            steps_applied=len(reconciled),
            steps_failed=failed,
            fields_reconciled=reconciled,
            fields_remaining=remaining,
            risk_before=round(risk_before, 2),
            risk_after=round(risk_after, 2),
            success=failed == 0 and len(remaining) == 0,
        )

    def calculate_drift_risk(self, drifts: list[ConfigField]) -> float:
        """Overall risk score (0-100) from a collection of drifted fields."""
        if not drifts:
            return 0.0
        total = 0.0
        for cf in drifts:
            weight = _field_risk(cf.path)
            # Amplify for critical sources
            source_mult = 1.0
            if cf.drift_source in (
                DriftSource.CONFIG_MANAGEMENT_FAILURE,
                DriftSource.OPERATOR_ERROR,
            ):
                source_mult = 1.5
            elif cf.drift_source == DriftSource.HOTFIX:
                source_mult = 1.2
            total += weight * source_mult
        return min(100.0, total)

    def generate_drift_report(
        self,
        analyses: list[DriftAnalysis],
    ) -> DriftReport:
        """Generate a full report from a list of analyses."""
        components_with = sum(1 for a in analyses if a.drifted_fields)
        total_drifted = sum(len(a.drifted_fields) for a in analyses)
        all_fields = [f for a in analyses for f in a.drifted_fields]
        overall = self.calculate_drift_risk(all_fields)
        order = self._determine_reconciliation_order(analyses)

        if total_drifted == 0:
            summary = "No configuration drift detected."
        else:
            summary = (
                f"Detected {total_drifted} drifted field(s) across "
                f"{components_with} component(s). "
                f"Overall risk score: {overall:.1f}/100."
            )

        return DriftReport(
            total_components=len(analyses),
            components_with_drift=components_with,
            total_drifted_fields=total_drifted,
            overall_risk_score=round(overall, 2),
            analyses=analyses,
            reconciliation_order=order,
            summary=summary,
        )

    def find_safe_reconciliation_order(
        self,
        graph: InfraGraph,
        analyses: list[DriftAnalysis],
    ) -> list[str]:
        """Determine a safe order to reconcile components.

        Strategy: reconcile leaf-nodes first (fewest dependents) so that
        reconciliation of upstream components doesn't cascade through
        already-drifted downstream services.  Among components at the same
        dependency depth, sort by ascending risk so low-risk changes are
        validated first.
        """
        cid_risk: dict[str, float] = {a.component_id: a.risk_score for a in analyses}
        # Only include components that actually drifted
        drifted_ids = [a.component_id for a in analyses if a.drifted_fields]
        if not drifted_ids:
            return []

        def _depth(cid: str) -> int:
            """Number of dependents (upstream components that rely on *cid*)."""
            comp = graph.get_component(cid)
            if comp is None:
                return 0
            return len(graph.get_dependents(cid))

        drifted_ids.sort(key=lambda c: (_depth(c), cid_risk.get(c, 0.0)))
        return drifted_ids

    # -- internal -----------------------------------------------------------

    def _missing_component_analysis(
        self,
        cid: str,
        actual: Component | None,
        desired: Component | None,
    ) -> DriftAnalysis:
        """Create an analysis for a component that exists only on one side."""
        if actual is None:
            # Present in desired but missing from actual
            cf = ConfigField(
                path="component_exists",
                desired_value="true",
                actual_value="false",
                drift_source=DriftSource.CONFIG_MANAGEMENT_FAILURE,
                last_changed="unknown",
                risk_level="critical",
            )
        else:
            cf = ConfigField(
                path="component_exists",
                desired_value="false",
                actual_value="true",
                drift_source=DriftSource.MANUAL_CHANGE,
                last_changed="unknown",
                risk_level="high",
            )

        analysis = DriftAnalysis(
            component_id=cid,
            total_fields_checked=1,
            drifted_fields=[cf],
            drift_percentage=100.0,
            risk_score=round(_field_risk(cf.path) * (1.5 if actual is None else 1.0), 2),
        )
        analysis.recommended_actions = self.recommend_reconciliation(analysis)
        return analysis

    @staticmethod
    def _pick_action(
        cf: ConfigField,
    ) -> tuple[ReconciliationAction, str, str, bool]:
        """Pick the best reconciliation action for a single drifted field."""
        path = cf.path
        source = cf.drift_source
        risk = cf.risk_level

        # Hotfix drift — accept actual state by default
        if source == DriftSource.HOTFIX:
            return (
                ReconciliationAction.ACCEPT_ACTUAL,
                f"Hotfix applied to '{path}'; accepting current value to preserve fix.",
                "low",
                True,
            )

        # Auto-scaling events — accept actual if replicas grew
        if source == DriftSource.AUTO_SCALING_EVENT and path == "replicas":
            return (
                ReconciliationAction.ACCEPT_ACTUAL,
                "Replicas increased by auto-scaler; accepting to maintain capacity.",
                "low",
                True,
            )

        # Failover events — flag for review
        if source == DriftSource.FAILOVER_EVENT:
            return (
                ReconciliationAction.FLAG_FOR_REVIEW,
                f"Failover event changed '{path}'; manual review recommended.",
                risk,
                False,
            )

        # Operator error — rollback is safe
        if source == DriftSource.OPERATOR_ERROR:
            return (
                ReconciliationAction.ROLLBACK,
                f"Operator error detected on '{path}'; rolling back to desired state.",
                risk,
                True,
            )

        # Config management failure — auto-remediate
        if source == DriftSource.CONFIG_MANAGEMENT_FAILURE:
            return (
                ReconciliationAction.AUTO_REMEDIATE,
                f"Config management failed for '{path}'; auto-remediating.",
                risk,
                True,
            )

        # Migration incomplete — merge
        if source == DriftSource.MIGRATION_INCOMPLETE:
            return (
                ReconciliationAction.MERGE,
                f"Migration incomplete for '{path}'; merging values.",
                risk,
                False,
            )

        # Environment promotion — apply desired
        if source == DriftSource.ENVIRONMENT_PROMOTION:
            return (
                ReconciliationAction.APPLY_DESIRED,
                f"Environment promotion drift on '{path}'; applying desired state.",
                "low",
                True,
            )

        # Critical risk — flag for review
        if risk == "critical":
            return (
                ReconciliationAction.FLAG_FOR_REVIEW,
                f"Critical risk on '{path}'; flagging for manual review.",
                "critical",
                False,
            )

        # Default — apply desired state
        return (
            ReconciliationAction.APPLY_DESIRED,
            f"Applying desired value for '{path}'.",
            risk,
            True,
        )

    @staticmethod
    def _determine_reconciliation_order(
        analyses: list[DriftAnalysis],
    ) -> list[str]:
        """Order components by descending risk for the report summary."""
        drifted = [a for a in analyses if a.drifted_fields]
        drifted.sort(key=lambda a: a.risk_score, reverse=True)
        return [a.component_id for a in drifted]
