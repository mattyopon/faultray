# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""DORA Article 8 — ICT Risk Assessment Engine.

Provides structured risk identification, assessment, and tracking aligned
with DORA (Digital Operational Resilience Act) Article 8 requirements for
ICT risk management frameworks applicable to EU financial entities.

Key capabilities:
- Auto-detect risks from InfraGraph (SPOFs, unencrypted links, missing monitoring)
- Likelihood × Impact scoring (5×5 matrix)
- Inherent vs residual risk tracking
- Risk register with owner and review date management
- Risk treatment plan workflows
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from faultray.model.components import Component, ComponentType, HealthStatus
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class RiskCategory(str, Enum):
    """DORA Art. 8 — top-level ICT risk categories."""

    AVAILABILITY = "availability"
    INTEGRITY = "integrity"
    CONFIDENTIALITY = "confidentiality"
    CONTINUITY = "continuity"


class BusinessCriticality(str, Enum):
    """Asset classification by business importance."""

    CRITICAL = "critical"        # Failure causes immediate regulatory/financial impact
    HIGH = "high"                # Significant business disruption
    MEDIUM = "medium"            # Moderate business impact
    LOW = "low"                  # Minimal business impact


class RiskTreatmentOption(str, Enum):
    """DORA-compliant risk treatment strategies."""

    ACCEPT = "accept"        # Formally accept within risk appetite
    MITIGATE = "mitigate"    # Reduce likelihood or impact via controls
    TRANSFER = "transfer"    # Shift risk (insurance, contract clauses)
    AVOID = "avoid"          # Eliminate the activity creating the risk


class TreatmentStatus(str, Enum):
    """Progress state for a risk treatment action."""

    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    OVERDUE = "overdue"


class AssessmentStatus(str, Enum):
    """Workflow state for an annual assessment cycle."""

    DRAFT = "draft"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    ARCHIVED = "archived"


# ---------------------------------------------------------------------------
# Risk scoring helpers
# ---------------------------------------------------------------------------

# Score boundaries for the 5×5 matrix (1-25)
_LOW_THRESHOLD = 5
_MEDIUM_THRESHOLD = 10
_HIGH_THRESHOLD = 19


def _score_label(score: int) -> str:
    """Return a human-readable band for a raw 1-25 risk score."""
    if score <= _LOW_THRESHOLD:
        return "low"
    if score <= _MEDIUM_THRESHOLD:
        return "medium"
    if score <= _HIGH_THRESHOLD:
        return "high"
    return "critical"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class ICTRisk(BaseModel):
    """A single identified ICT risk entry.

    Covers the mandatory fields expected in a DORA-compliant risk register
    per Article 8(2) of the regulation.
    """

    risk_id: str = Field(default_factory=lambda: f"RISK-{uuid.uuid4().hex[:8].upper()}")
    category: RiskCategory
    description: str
    affected_component_ids: list[str] = Field(default_factory=list)
    asset_criticality: BusinessCriticality = BusinessCriticality.MEDIUM

    # 5×5 matrix values (1 = lowest, 5 = highest)
    likelihood: int = Field(ge=1, le=5, default=3)
    impact: int = Field(ge=1, le=5, default=3)

    # Inherent risk (before controls)
    inherent_score: int = 0
    inherent_label: str = "medium"

    # Controls already in place
    controls: list[str] = Field(default_factory=list)

    # Residual risk (after controls are applied)
    residual_likelihood: int = Field(ge=1, le=5, default=3)
    residual_impact: int = Field(ge=1, le=5, default=3)
    residual_score: int = 0
    residual_label: str = "medium"

    # Governance
    owner: str = "ICT Risk Manager"
    review_date: date = Field(
        default_factory=lambda: (datetime.now(timezone.utc) + timedelta(days=365)).date()
    )
    auto_detected: bool = True
    notes: str = ""

    def model_post_init(self, __context: Any) -> None:  # noqa: D401
        """Derive score fields after construction."""
        self.inherent_score = self.likelihood * self.impact
        self.inherent_label = _score_label(self.inherent_score)
        self.residual_score = self.residual_likelihood * self.residual_impact
        self.residual_label = _score_label(self.residual_score)


class RiskTreatmentAction(BaseModel):
    """A specific action within a risk treatment plan."""

    action_id: str = Field(default_factory=lambda: f"ACT-{uuid.uuid4().hex[:8].upper()}")
    description: str
    owner: str = "ICT Risk Manager"
    due_date: date = Field(
        default_factory=lambda: (datetime.now(timezone.utc) + timedelta(days=90)).date()
    )
    status: TreatmentStatus = TreatmentStatus.PLANNED
    completion_date: date | None = None
    evidence: str = ""


class RiskTreatmentPlan(BaseModel):
    """Treatment plan for a risk that exceeds the configured risk appetite.

    Captures the chosen treatment option and the concrete actions needed
    to bring residual risk within appetite.
    """

    plan_id: str = Field(default_factory=lambda: f"PLAN-{uuid.uuid4().hex[:8].upper()}")
    risk_id: str
    treatment_option: RiskTreatmentOption
    rationale: str = ""
    actions: list[RiskTreatmentAction] = Field(default_factory=list)
    target_residual_score: int = Field(ge=1, le=25, default=5)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    approved_by: str = ""

    @property
    def completion_rate(self) -> float:
        """Fraction of actions completed (0.0 – 1.0)."""
        if not self.actions:
            return 0.0
        done = sum(1 for a in self.actions if a.status == TreatmentStatus.COMPLETED)
        return done / len(self.actions)

    @property
    def has_overdue_actions(self) -> bool:
        today = datetime.now(timezone.utc).date()
        return any(
            a.status not in (TreatmentStatus.COMPLETED,) and a.due_date < today
            for a in self.actions
        )


class RiskAppetiteConfig(BaseModel):
    """Configurable thresholds for the organisation's risk appetite.

    Any risk with a residual score exceeding ``max_acceptable_residual``
    requires a formal treatment plan before it can be approved.
    """

    max_acceptable_residual: int = Field(ge=1, le=25, default=9)
    critical_asset_max_residual: int = Field(ge=1, le=25, default=6)
    annual_assessment_required: bool = True
    treatment_plan_approval_required: bool = True

    def exceeds_appetite(self, risk: ICTRisk) -> bool:
        """Return True if the residual risk exceeds the configured appetite."""
        if risk.asset_criticality == BusinessCriticality.CRITICAL:
            return risk.residual_score > self.critical_asset_max_residual
        return risk.residual_score > self.max_acceptable_residual


class RiskAssessment(BaseModel):
    """Snapshot of the full assessment for an annual cycle.

    Tracks the assessment workflow from draft through approval.
    """

    assessment_id: str = Field(default_factory=lambda: f"ASSESS-{uuid.uuid4().hex[:8].upper()}")
    period_start: date = Field(default_factory=lambda: datetime.now(timezone.utc).date())
    period_end: date = Field(
        default_factory=lambda: (datetime.now(timezone.utc) + timedelta(days=365)).date()
    )
    status: AssessmentStatus = AssessmentStatus.DRAFT
    risks_above_appetite: int = 0
    risks_within_appetite: int = 0
    total_risks: int = 0
    open_treatment_plans: int = 0
    reviewed_by: str = ""
    approved_by: str = ""
    approved_at: datetime | None = None
    notes: str = ""


class RiskRegister(BaseModel):
    """Full ICT risk register for the organisation.

    Acts as the single source of truth for all identified ICT risks and
    their associated treatment plans, as required by DORA Article 8.
    """

    register_id: str = Field(default_factory=lambda: f"REG-{uuid.uuid4().hex[:8].upper()}")
    organisation: str = "Organisation"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    risks: list[ICTRisk] = Field(default_factory=list)
    treatment_plans: list[RiskTreatmentPlan] = Field(default_factory=list)
    assessments: list[RiskAssessment] = Field(default_factory=list)

    def get_risk(self, risk_id: str) -> ICTRisk | None:
        return next((r for r in self.risks if r.risk_id == risk_id), None)

    def get_treatment_plan(self, risk_id: str) -> RiskTreatmentPlan | None:
        return next((p for p in self.treatment_plans if p.risk_id == risk_id), None)

    @property
    def critical_risks(self) -> list[ICTRisk]:
        return [r for r in self.risks if r.residual_label == "critical"]

    @property
    def high_risks(self) -> list[ICTRisk]:
        return [r for r in self.risks if r.residual_label == "high"]

    def summary(self) -> dict:
        return {
            "total_risks": len(self.risks),
            "by_category": {
                cat.value: sum(1 for r in self.risks if r.category == cat)
                for cat in RiskCategory
            },
            "by_residual_label": {
                label: sum(1 for r in self.risks if r.residual_label == label)
                for label in ("critical", "high", "medium", "low")
            },
            "open_treatment_plans": sum(
                1 for p in self.treatment_plans
                if p.completion_rate < 1.0
            ),
            "overdue_actions": sum(
                1 for p in self.treatment_plans if p.has_overdue_actions
            ),
        }


# ---------------------------------------------------------------------------
# Keyword helpers for auto-detection
# ---------------------------------------------------------------------------

_MONITORING_KEYWORDS = {
    "prometheus", "grafana", "datadog", "newrelic", "otel", "opentelemetry",
    "monitoring", "alertmanager", "jaeger", "zipkin", "cloudwatch",
}


def _has_monitoring_keywords(component: Component) -> bool:
    combined = (component.id + " " + component.name).lower()
    return any(kw in combined for kw in _MONITORING_KEYWORDS)


# ---------------------------------------------------------------------------
# Main engine
# ---------------------------------------------------------------------------


class DORAICTRiskAssessmentEngine:
    """DORA Article 8 ICT Risk Assessment Engine.

    Analyses an InfraGraph to auto-detect ICT risks and builds a structured
    risk register. Supports manual risk overlays, risk appetite configuration,
    and treatment plan generation.

    Usage::

        engine = DORAICTRiskAssessmentEngine(graph, appetite=RiskAppetiteConfig())
        register = engine.run_assessment()
        report = engine.export_report(register)
    """

    def __init__(
        self,
        graph: InfraGraph,
        appetite: RiskAppetiteConfig | None = None,
        organisation: str = "Organisation",
    ) -> None:
        self.graph = graph
        self.appetite = appetite or RiskAppetiteConfig()
        self.organisation = organisation
        self._manual_risks: list[ICTRisk] = []

    # ------------------------------------------------------------------
    # Manual overlay
    # ------------------------------------------------------------------

    def add_manual_risk(self, risk: ICTRisk) -> None:
        """Add a manually-defined risk (business context not inferable from graph)."""
        risk.auto_detected = False
        self._manual_risks.append(risk)

    # ------------------------------------------------------------------
    # Risk identification — auto-detection from InfraGraph
    # ------------------------------------------------------------------

    def _detect_spof_availability_risks(self) -> list[ICTRisk]:
        """Detect single points of failure (DORA Art. 8 — availability)."""
        risks: list[ICTRisk] = []
        for comp in self.graph.components.values():
            dependents = self.graph.get_dependents(comp.id)
            is_spof = comp.replicas <= 1 and not comp.failover.enabled and len(dependents) > 0
            if not is_spof:
                continue

            dep_count = len(dependents)
            criticality = (
                BusinessCriticality.CRITICAL if dep_count >= 3
                else BusinessCriticality.HIGH if dep_count >= 2
                else BusinessCriticality.MEDIUM
            )
            likelihood = min(5, 2 + dep_count)  # more dependents → higher likelihood of impact
            impact = min(5, 2 + dep_count)

            # Controls reduce residual
            controls: list[str] = []
            residual_l, residual_i = likelihood, impact
            if comp.autoscaling.enabled:
                controls.append("Autoscaling enabled")
                residual_l = max(1, residual_l - 1)
            if comp.health == HealthStatus.HEALTHY:
                controls.append("Current health: HEALTHY")
                residual_i = max(1, residual_i - 1)

            risks.append(ICTRisk(
                category=RiskCategory.AVAILABILITY,
                description=(
                    f"Component '{comp.name}' ({comp.id}) is a single point of failure "
                    f"with {dep_count} dependent(s) and no failover/replication."
                ),
                affected_component_ids=[comp.id] + [d.id for d in dependents],
                asset_criticality=criticality,
                likelihood=likelihood,
                impact=impact,
                controls=controls,
                residual_likelihood=residual_l,
                residual_impact=residual_i,
                owner="Platform Engineering",
                notes=f"replicas={comp.replicas}, failover.enabled={comp.failover.enabled}",
            ))
        return risks

    def _detect_unencrypted_connection_risks(self) -> list[ICTRisk]:
        """Detect unencrypted dependency connections (DORA Art. 8 — confidentiality/integrity)."""
        risks: list[ICTRisk] = []
        seen_pairs: set[tuple[str, str]] = set()

        for dep in self.graph.all_dependency_edges():
            pair = (dep.source_id, dep.target_id)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)

            protocol = (dep.protocol or "").lower()
            plaintext_protocols = {"http", "tcp", "ftp", "telnet", "smtp"}
            if protocol not in plaintext_protocols:
                continue

            src = self.graph.get_component(dep.source_id)
            tgt = self.graph.get_component(dep.target_id)
            src_name = src.name if src else dep.source_id
            tgt_name = tgt.name if tgt else dep.target_id

            # Higher criticality if either endpoint is a data store
            data_types = {ComponentType.DATABASE, ComponentType.STORAGE, ComponentType.QUEUE}
            is_data_link = (
                (src and src.type in data_types) or (tgt and tgt.type in data_types)
            )
            criticality = BusinessCriticality.HIGH if is_data_link else BusinessCriticality.MEDIUM

            controls: list[str] = []
            residual_l, residual_i = 3, 4
            if tgt and tgt.security.network_segmented:
                controls.append("Network segmentation in place")
                residual_i = max(1, residual_i - 1)

            risks.append(ICTRisk(
                category=RiskCategory.CONFIDENTIALITY,
                description=(
                    f"Unencrypted {protocol.upper()} connection from '{src_name}' to "
                    f"'{tgt_name}'. Data in transit is not protected."
                ),
                affected_component_ids=[dep.source_id, dep.target_id],
                asset_criticality=criticality,
                likelihood=2,
                impact=4,
                controls=controls,
                residual_likelihood=residual_l,
                residual_impact=residual_i,
                owner="Security Team",
                notes=f"protocol={protocol}, dep_type={dep.dependency_type}",
            ))
        return risks

    def _detect_missing_monitoring_risks(self) -> list[ICTRisk]:
        """Detect components lacking monitoring (DORA Art. 8 — continuity)."""
        risks: list[ICTRisk] = []
        has_global_monitoring = any(
            _has_monitoring_keywords(c) for c in self.graph.components.values()
        )

        for comp in self.graph.components.values():
            if _has_monitoring_keywords(comp):
                continue
            if not comp.security.log_enabled and not has_global_monitoring:
                controls: list[str] = []
                residual_l, residual_i = 4, 3
                if comp.health == HealthStatus.HEALTHY:
                    controls.append("Current health: HEALTHY")
                    residual_i = max(1, residual_i - 1)

                risks.append(ICTRisk(
                    category=RiskCategory.CONTINUITY,
                    description=(
                        f"Component '{comp.name}' ({comp.id}) has no observable monitoring "
                        "or logging. Failures may go undetected until user impact occurs."
                    ),
                    affected_component_ids=[comp.id],
                    asset_criticality=BusinessCriticality.MEDIUM,
                    likelihood=4,
                    impact=3,
                    controls=controls,
                    residual_likelihood=residual_l,
                    residual_impact=residual_i,
                    owner="SRE Team",
                    notes=f"log_enabled={comp.security.log_enabled}",
                ))
        return risks

    def _detect_outdated_component_risks(self) -> list[ICTRisk]:
        """Detect components flagged as degraded or down (integrity/continuity risk)."""
        risks: list[ICTRisk] = []
        unhealthy_statuses = {HealthStatus.DEGRADED, HealthStatus.OVERLOADED, HealthStatus.DOWN}

        for comp in self.graph.components.values():
            if comp.health not in unhealthy_statuses:
                continue

            severity_map = {
                HealthStatus.DOWN: (5, 5, BusinessCriticality.CRITICAL),
                HealthStatus.DEGRADED: (3, 4, BusinessCriticality.HIGH),
                HealthStatus.OVERLOADED: (4, 3, BusinessCriticality.HIGH),
            }
            likelihood, impact, criticality = severity_map[comp.health]

            controls: list[str] = []
            residual_l, residual_i = likelihood, impact
            if comp.failover.enabled:
                controls.append("Failover enabled")
                residual_l = max(1, residual_l - 2)
                residual_i = max(1, residual_i - 1)
            if comp.replicas > 1:
                controls.append(f"Multiple replicas ({comp.replicas})")
                residual_i = max(1, residual_i - 1)

            risks.append(ICTRisk(
                category=RiskCategory.INTEGRITY,
                description=(
                    f"Component '{comp.name}' ({comp.id}) is in a non-healthy state "
                    f"({comp.health.value}), indicating a potential integrity or availability issue."
                ),
                affected_component_ids=[comp.id],
                asset_criticality=criticality,
                likelihood=likelihood,
                impact=impact,
                controls=controls,
                residual_likelihood=residual_l,
                residual_impact=residual_i,
                owner="Operations Team",
                notes=f"health={comp.health.value}, replicas={comp.replicas}",
            ))
        return risks

    def _detect_high_utilisation_continuity_risks(self) -> list[ICTRisk]:
        """Detect components with dangerously high resource utilisation."""
        risks: list[ICTRisk] = []
        for comp in self.graph.components.values():
            util = comp.utilization()
            if util < 80.0:
                continue

            impact = 5 if util >= 95 else 4 if util >= 90 else 3
            criticality = (
                BusinessCriticality.CRITICAL if util >= 95
                else BusinessCriticality.HIGH
            )

            controls: list[str] = []
            residual_l, residual_i = 4, impact
            if comp.autoscaling.enabled:
                controls.append("Autoscaling enabled")
                residual_l = max(1, residual_l - 2)
                residual_i = max(1, residual_i - 1)

            risks.append(ICTRisk(
                category=RiskCategory.CONTINUITY,
                description=(
                    f"Component '{comp.name}' ({comp.id}) has utilisation at "
                    f"{util:.0f}%, approaching saturation. Service continuity is at risk."
                ),
                affected_component_ids=[comp.id],
                asset_criticality=criticality,
                likelihood=4,
                impact=impact,
                controls=controls,
                residual_likelihood=residual_l,
                residual_impact=residual_i,
                owner="Platform Engineering",
                notes=f"utilisation={util:.1f}%",
            ))
        return risks

    def _detect_missing_encryption_at_rest(self) -> list[ICTRisk]:
        """Detect data-storing components without encryption at rest."""
        risks: list[ICTRisk] = []
        data_types = {ComponentType.DATABASE, ComponentType.STORAGE}

        for comp in self.graph.components.values():
            if comp.type not in data_types:
                continue
            if comp.security.encryption_at_rest:
                continue

            controls: list[str] = []
            residual_l, residual_i = 2, 5
            if comp.compliance_tags.data_classification in ("public",):
                controls.append("Data classified as public")
                residual_i = max(1, residual_i - 2)

            risks.append(ICTRisk(
                category=RiskCategory.CONFIDENTIALITY,
                description=(
                    f"Component '{comp.name}' ({comp.id}) stores data without "
                    "encryption at rest. Exposure of storage media would leak sensitive data."
                ),
                affected_component_ids=[comp.id],
                asset_criticality=BusinessCriticality.HIGH,
                likelihood=2,
                impact=5,
                controls=controls,
                residual_likelihood=residual_l,
                residual_impact=residual_i,
                owner="Security Team",
                notes=(
                    f"type={comp.type.value}, "
                    f"data_classification={comp.compliance_tags.data_classification}"
                ),
            ))
        return risks

    # ------------------------------------------------------------------
    # Assessment orchestration
    # ------------------------------------------------------------------

    def identify_risks(self) -> list[ICTRisk]:
        """Run all detection routines and merge with manual risks.

        Returns a de-duplicated, ordered list of ICTRisk objects.
        """
        auto_risks: list[ICTRisk] = []
        auto_risks.extend(self._detect_spof_availability_risks())
        auto_risks.extend(self._detect_unencrypted_connection_risks())
        auto_risks.extend(self._detect_missing_monitoring_risks())
        auto_risks.extend(self._detect_outdated_component_risks())
        auto_risks.extend(self._detect_high_utilisation_continuity_risks())
        auto_risks.extend(self._detect_missing_encryption_at_rest())

        # Manual risks are appended after auto-detected ones
        all_risks = auto_risks + self._manual_risks

        # Sort: critical first, then descending residual score
        all_risks.sort(
            key=lambda r: (
                r.asset_criticality != BusinessCriticality.CRITICAL,
                -r.residual_score,
            )
        )
        return all_risks

    def generate_treatment_plan(
        self,
        risk: ICTRisk,
        option: RiskTreatmentOption = RiskTreatmentOption.MITIGATE,
    ) -> RiskTreatmentPlan:
        """Auto-generate a treatment plan for a risk that exceeds appetite.

        Produces sensible default actions based on category and option.
        """
        actions: list[RiskTreatmentAction] = []
        base_due = datetime.now(timezone.utc).date()

        if option == RiskTreatmentOption.MITIGATE:
            if risk.category == RiskCategory.AVAILABILITY:
                actions.append(RiskTreatmentAction(
                    description="Add replicas (target ≥ 2) or enable failover for affected component(s).",
                    owner="Platform Engineering",
                    due_date=base_due + timedelta(days=30),
                ))
                actions.append(RiskTreatmentAction(
                    description="Validate recovery time objective (RTO) meets business requirements.",
                    owner="SRE Team",
                    due_date=base_due + timedelta(days=60),
                ))
            elif risk.category == RiskCategory.CONFIDENTIALITY:
                actions.append(RiskTreatmentAction(
                    description="Upgrade connections to TLS 1.2+ or equivalent encrypted protocol.",
                    owner="Security Team",
                    due_date=base_due + timedelta(days=30),
                ))
                actions.append(RiskTreatmentAction(
                    description="Enable encryption at rest for all data-storing components.",
                    owner="Security Team",
                    due_date=base_due + timedelta(days=45),
                ))
            elif risk.category == RiskCategory.CONTINUITY:
                actions.append(RiskTreatmentAction(
                    description="Deploy observability stack (metrics, logs, traces) for affected component(s).",
                    owner="SRE Team",
                    due_date=base_due + timedelta(days=14),
                ))
                actions.append(RiskTreatmentAction(
                    description="Define and configure alerting thresholds based on SLO targets.",
                    owner="SRE Team",
                    due_date=base_due + timedelta(days=30),
                ))
            elif risk.category == RiskCategory.INTEGRITY:
                actions.append(RiskTreatmentAction(
                    description="Investigate root cause of non-healthy component state and remediate.",
                    owner="Operations Team",
                    due_date=base_due + timedelta(days=7),
                ))
                actions.append(RiskTreatmentAction(
                    description="Enable data integrity checks and checksums for affected component.",
                    owner="Operations Team",
                    due_date=base_due + timedelta(days=30),
                ))

        elif option == RiskTreatmentOption.ACCEPT:
            actions.append(RiskTreatmentAction(
                description="Document formal risk acceptance decision with management approval.",
                owner="Risk Manager",
                due_date=base_due + timedelta(days=14),
            ))

        elif option == RiskTreatmentOption.TRANSFER:
            actions.append(RiskTreatmentAction(
                description="Review cyber insurance policy to confirm coverage of identified risk.",
                owner="Risk Manager",
                due_date=base_due + timedelta(days=30),
            ))
            actions.append(RiskTreatmentAction(
                description="Add contractual resilience obligations to relevant third-party agreements.",
                owner="Legal / Procurement",
                due_date=base_due + timedelta(days=60),
            ))

        elif option == RiskTreatmentOption.AVOID:
            actions.append(RiskTreatmentAction(
                description="Decomission or replace the risk-generating ICT activity.",
                owner="ICT Risk Manager",
                due_date=base_due + timedelta(days=90),
            ))

        return RiskTreatmentPlan(
            risk_id=risk.risk_id,
            treatment_option=option,
            rationale=f"Residual score {risk.residual_score} ({risk.residual_label}) exceeds appetite.",
            actions=actions,
            target_residual_score=self.appetite.max_acceptable_residual,
        )

    def run_assessment(self, organisation: str | None = None) -> RiskRegister:
        """Execute a full ICT risk assessment and populate the risk register.

        This is the primary entry point. It:
        1. Identifies all risks from the InfraGraph plus any manual overlays.
        2. Checks each risk against the risk appetite.
        3. Auto-generates treatment plans for out-of-appetite risks.
        4. Creates an assessment snapshot.

        Returns the completed RiskRegister.
        """
        org = organisation or self.organisation
        risks = self.identify_risks()

        treatment_plans: list[RiskTreatmentPlan] = []
        above_appetite: list[ICTRisk] = []
        within_appetite: list[ICTRisk] = []

        for risk in risks:
            if self.appetite.exceeds_appetite(risk):
                above_appetite.append(risk)
                plan = self.generate_treatment_plan(risk)
                treatment_plans.append(plan)
            else:
                within_appetite.append(risk)

        assessment = RiskAssessment(
            status=AssessmentStatus.DRAFT,
            risks_above_appetite=len(above_appetite),
            risks_within_appetite=len(within_appetite),
            total_risks=len(risks),
            open_treatment_plans=len(treatment_plans),
        )

        register = RiskRegister(
            organisation=org,
            risks=risks,
            treatment_plans=treatment_plans,
            assessments=[assessment],
        )
        return register

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def export_report(self, register: RiskRegister) -> dict:
        """Export the risk register as a structured audit-ready dictionary.

        Suitable for serialisation to JSON for regulator submission.
        """
        summary = register.summary()
        latest_assessment = register.assessments[-1] if register.assessments else None

        return {
            "framework": "DORA",
            "article": "Article 8 — ICT Risk Management",
            "regulation": "EU 2022/2554",
            "export_timestamp": datetime.now(timezone.utc).isoformat(),
            "organisation": register.organisation,
            "register_id": register.register_id,
            "risk_appetite": self.appetite.model_dump(),
            "summary": summary,
            "assessment": latest_assessment.model_dump() if latest_assessment else None,
            "risks": [r.model_dump() for r in register.risks],
            "treatment_plans": [p.model_dump() for p in register.treatment_plans],
            "compliance_note": (
                "This register is generated in accordance with DORA Article 8 "
                "requirements for ICT risk identification, assessment, and treatment."
            ),
        }
