# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Compliance Drift Detector — detect drift from compliance baselines over time.

Compares current infrastructure state against compliance snapshots, identifies
policy violations that have crept in since the last audit, tracks compliance
score trajectory, and generates remediation plans prioritised by regulatory risk.
"""

from __future__ import annotations

import hashlib
import logging
from enum import Enum

from pydantic import BaseModel, Field

from faultray.model.components import Component
from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ComplianceFramework(str, Enum):
    SOC2 = "soc2"
    HIPAA = "hipaa"
    PCI_DSS = "pci_dss"
    GDPR = "gdpr"
    ISO_27001 = "iso_27001"
    NIST_CSF = "nist_csf"
    FedRAMP = "fedramp"
    CIS_BENCHMARK = "cis_benchmark"


class DriftType(str, Enum):
    NEW_VIOLATION = "new_violation"
    REGRESSION = "regression"
    CONFIGURATION_CHANGE = "configuration_change"
    PERMISSION_ESCALATION = "permission_escalation"
    ENCRYPTION_REMOVED = "encryption_removed"
    LOGGING_DISABLED = "logging_disabled"
    BACKUP_POLICY_CHANGED = "backup_policy_changed"
    NETWORK_EXPOSURE = "network_exposure"


class DriftSeverity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class RemediationPriority(str, Enum):
    IMMEDIATE = "immediate"
    URGENT = "urgent"
    STANDARD = "standard"
    DEFERRED = "deferred"


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------


class ComplianceBaseline(BaseModel):
    """Snapshot of compliance state at a point in time."""

    snapshot_id: str
    framework: ComplianceFramework
    timestamp: str
    controls_assessed: int = 0
    controls_passing: int = 0
    controls_failing: int = 0
    score: float = 0.0


class ComplianceDriftItem(BaseModel):
    """A single detected compliance drift."""

    component_id: str
    drift_type: DriftType
    severity: DriftSeverity
    framework: ComplianceFramework
    control_id: str
    baseline_state: str
    current_state: str
    description: str
    remediation: str


class ComplianceTrajectory(BaseModel):
    """Compliance score trajectory over time for a given framework."""

    framework: ComplianceFramework
    scores: list[float] = Field(default_factory=list)
    timestamps: list[str] = Field(default_factory=list)
    trend: str = "stable"
    projected_score: float = 0.0


class RemediationPlan(BaseModel):
    """Prioritised remediation plan for a detected drift item."""

    drift_item_id: str
    priority: RemediationPriority
    estimated_effort_hours: float = 0.0
    regulatory_risk: str = ""
    remediation_steps: list[str] = Field(default_factory=list)


class ComplianceDriftReport(BaseModel):
    """Full compliance drift analysis report."""

    drifts: list[ComplianceDriftItem] = Field(default_factory=list)
    trajectory: list[ComplianceTrajectory] = Field(default_factory=list)
    remediation_plans: list[RemediationPlan] = Field(default_factory=list)
    overall_drift_score: float = 0.0
    frameworks_affected: list[str] = Field(default_factory=list)
    total_controls_drifted: int = 0
    recommendations: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Severity / risk mapping tables
# ---------------------------------------------------------------------------

_FRAMEWORK_SEVERITY: dict[ComplianceFramework, dict[DriftType, DriftSeverity]] = {
    ComplianceFramework.SOC2: {
        DriftType.ENCRYPTION_REMOVED: DriftSeverity.CRITICAL,
        DriftType.LOGGING_DISABLED: DriftSeverity.HIGH,
        DriftType.PERMISSION_ESCALATION: DriftSeverity.HIGH,
        DriftType.BACKUP_POLICY_CHANGED: DriftSeverity.MEDIUM,
        DriftType.CONFIGURATION_CHANGE: DriftSeverity.MEDIUM,
        DriftType.NETWORK_EXPOSURE: DriftSeverity.HIGH,
        DriftType.NEW_VIOLATION: DriftSeverity.HIGH,
        DriftType.REGRESSION: DriftSeverity.HIGH,
    },
    ComplianceFramework.HIPAA: {
        DriftType.ENCRYPTION_REMOVED: DriftSeverity.CRITICAL,
        DriftType.LOGGING_DISABLED: DriftSeverity.CRITICAL,
        DriftType.PERMISSION_ESCALATION: DriftSeverity.CRITICAL,
        DriftType.BACKUP_POLICY_CHANGED: DriftSeverity.HIGH,
        DriftType.CONFIGURATION_CHANGE: DriftSeverity.MEDIUM,
        DriftType.NETWORK_EXPOSURE: DriftSeverity.CRITICAL,
        DriftType.NEW_VIOLATION: DriftSeverity.HIGH,
        DriftType.REGRESSION: DriftSeverity.HIGH,
    },
    ComplianceFramework.PCI_DSS: {
        DriftType.ENCRYPTION_REMOVED: DriftSeverity.CRITICAL,
        DriftType.LOGGING_DISABLED: DriftSeverity.CRITICAL,
        DriftType.PERMISSION_ESCALATION: DriftSeverity.CRITICAL,
        DriftType.BACKUP_POLICY_CHANGED: DriftSeverity.HIGH,
        DriftType.CONFIGURATION_CHANGE: DriftSeverity.HIGH,
        DriftType.NETWORK_EXPOSURE: DriftSeverity.CRITICAL,
        DriftType.NEW_VIOLATION: DriftSeverity.CRITICAL,
        DriftType.REGRESSION: DriftSeverity.CRITICAL,
    },
    ComplianceFramework.GDPR: {
        DriftType.ENCRYPTION_REMOVED: DriftSeverity.CRITICAL,
        DriftType.LOGGING_DISABLED: DriftSeverity.HIGH,
        DriftType.PERMISSION_ESCALATION: DriftSeverity.HIGH,
        DriftType.BACKUP_POLICY_CHANGED: DriftSeverity.MEDIUM,
        DriftType.CONFIGURATION_CHANGE: DriftSeverity.MEDIUM,
        DriftType.NETWORK_EXPOSURE: DriftSeverity.HIGH,
        DriftType.NEW_VIOLATION: DriftSeverity.HIGH,
        DriftType.REGRESSION: DriftSeverity.HIGH,
    },
    ComplianceFramework.ISO_27001: {
        DriftType.ENCRYPTION_REMOVED: DriftSeverity.HIGH,
        DriftType.LOGGING_DISABLED: DriftSeverity.HIGH,
        DriftType.PERMISSION_ESCALATION: DriftSeverity.HIGH,
        DriftType.BACKUP_POLICY_CHANGED: DriftSeverity.MEDIUM,
        DriftType.CONFIGURATION_CHANGE: DriftSeverity.MEDIUM,
        DriftType.NETWORK_EXPOSURE: DriftSeverity.HIGH,
        DriftType.NEW_VIOLATION: DriftSeverity.MEDIUM,
        DriftType.REGRESSION: DriftSeverity.MEDIUM,
    },
    ComplianceFramework.NIST_CSF: {
        DriftType.ENCRYPTION_REMOVED: DriftSeverity.HIGH,
        DriftType.LOGGING_DISABLED: DriftSeverity.HIGH,
        DriftType.PERMISSION_ESCALATION: DriftSeverity.HIGH,
        DriftType.BACKUP_POLICY_CHANGED: DriftSeverity.MEDIUM,
        DriftType.CONFIGURATION_CHANGE: DriftSeverity.MEDIUM,
        DriftType.NETWORK_EXPOSURE: DriftSeverity.HIGH,
        DriftType.NEW_VIOLATION: DriftSeverity.MEDIUM,
        DriftType.REGRESSION: DriftSeverity.MEDIUM,
    },
    ComplianceFramework.FedRAMP: {
        DriftType.ENCRYPTION_REMOVED: DriftSeverity.CRITICAL,
        DriftType.LOGGING_DISABLED: DriftSeverity.CRITICAL,
        DriftType.PERMISSION_ESCALATION: DriftSeverity.CRITICAL,
        DriftType.BACKUP_POLICY_CHANGED: DriftSeverity.HIGH,
        DriftType.CONFIGURATION_CHANGE: DriftSeverity.HIGH,
        DriftType.NETWORK_EXPOSURE: DriftSeverity.CRITICAL,
        DriftType.NEW_VIOLATION: DriftSeverity.CRITICAL,
        DriftType.REGRESSION: DriftSeverity.CRITICAL,
    },
    ComplianceFramework.CIS_BENCHMARK: {
        DriftType.ENCRYPTION_REMOVED: DriftSeverity.HIGH,
        DriftType.LOGGING_DISABLED: DriftSeverity.HIGH,
        DriftType.PERMISSION_ESCALATION: DriftSeverity.MEDIUM,
        DriftType.BACKUP_POLICY_CHANGED: DriftSeverity.MEDIUM,
        DriftType.CONFIGURATION_CHANGE: DriftSeverity.LOW,
        DriftType.NETWORK_EXPOSURE: DriftSeverity.HIGH,
        DriftType.NEW_VIOLATION: DriftSeverity.MEDIUM,
        DriftType.REGRESSION: DriftSeverity.MEDIUM,
    },
}

_REGULATORY_RISK: dict[ComplianceFramework, str] = {
    ComplianceFramework.SOC2: "Audit failure risk — may lose SOC 2 attestation",
    ComplianceFramework.HIPAA: "HIPAA violation — up to $1.5M per category per year",
    ComplianceFramework.PCI_DSS: "PCI non-compliance — fines $5K-$100K/month, card processing revocation",
    ComplianceFramework.GDPR: "GDPR breach — up to 4% of annual global turnover",
    ComplianceFramework.ISO_27001: "ISO 27001 non-conformity — certification suspension risk",
    ComplianceFramework.NIST_CSF: "NIST CSF gap — increased cyber-insurance premiums",
    ComplianceFramework.FedRAMP: "FedRAMP revocation — loss of federal contracts",
    ComplianceFramework.CIS_BENCHMARK: "CIS deviation — increased attack surface exposure",
}

_SEVERITY_WEIGHT: dict[DriftSeverity, float] = {
    DriftSeverity.CRITICAL: 10.0,
    DriftSeverity.HIGH: 5.0,
    DriftSeverity.MEDIUM: 2.0,
    DriftSeverity.LOW: 1.0,
    DriftSeverity.INFO: 0.0,
}

_SEVERITY_EFFORT: dict[DriftSeverity, float] = {
    DriftSeverity.CRITICAL: 8.0,
    DriftSeverity.HIGH: 4.0,
    DriftSeverity.MEDIUM: 2.0,
    DriftSeverity.LOW: 1.0,
    DriftSeverity.INFO: 0.5,
}

_SEVERITY_PRIORITY: dict[DriftSeverity, RemediationPriority] = {
    DriftSeverity.CRITICAL: RemediationPriority.IMMEDIATE,
    DriftSeverity.HIGH: RemediationPriority.URGENT,
    DriftSeverity.MEDIUM: RemediationPriority.STANDARD,
    DriftSeverity.LOW: RemediationPriority.DEFERRED,
    DriftSeverity.INFO: RemediationPriority.DEFERRED,
}

# ---------------------------------------------------------------------------
# Remediation step templates
# ---------------------------------------------------------------------------

_REMEDIATION_STEPS: dict[DriftType, list[str]] = {
    DriftType.ENCRYPTION_REMOVED: [
        "Re-enable encryption at rest on the affected component",
        "Verify encryption keys are rotated per policy",
        "Validate encryption in transit (TLS) is active",
        "Run compliance scan to confirm remediation",
    ],
    DriftType.LOGGING_DISABLED: [
        "Re-enable audit logging on the affected component",
        "Verify log retention policy meets framework requirements",
        "Ensure logs are forwarded to centralised SIEM",
        "Confirm alerting rules are active for the component",
    ],
    DriftType.PERMISSION_ESCALATION: [
        "Review and revoke excessive permissions",
        "Apply principle of least privilege",
        "Audit recent access logs for unauthorised actions",
        "Implement or update RBAC policies",
    ],
    DriftType.BACKUP_POLICY_CHANGED: [
        "Restore backup policy to baseline configuration",
        "Verify backup frequency meets RPO requirements",
        "Test backup restoration procedure",
        "Update disaster recovery documentation",
    ],
    DriftType.CONFIGURATION_CHANGE: [
        "Compare current configuration with baseline",
        "Revert unauthorised configuration changes",
        "Update change management records",
        "Re-run compliance validation",
    ],
    DriftType.NETWORK_EXPOSURE: [
        "Review and tighten security group / firewall rules",
        "Re-enable network segmentation where removed",
        "Verify WAF rules are active",
        "Scan for open ports and exposed services",
    ],
    DriftType.NEW_VIOLATION: [
        "Identify the root cause of the new violation",
        "Implement required controls for the framework",
        "Document the remediation in change management",
        "Schedule follow-up compliance audit",
    ],
    DriftType.REGRESSION: [
        "Investigate why previously passing control now fails",
        "Check recent deployments for regression cause",
        "Re-apply the original fix or workaround",
        "Add automated test to prevent future regression",
    ],
}

# ---------------------------------------------------------------------------
# Control ID mappings per framework
# ---------------------------------------------------------------------------

_CONTROL_IDS: dict[ComplianceFramework, dict[DriftType, str]] = {
    ComplianceFramework.SOC2: {
        DriftType.ENCRYPTION_REMOVED: "CC6.1",
        DriftType.LOGGING_DISABLED: "CC7.2",
        DriftType.PERMISSION_ESCALATION: "CC6.3",
        DriftType.BACKUP_POLICY_CHANGED: "A1.2",
        DriftType.CONFIGURATION_CHANGE: "CC8.1",
        DriftType.NETWORK_EXPOSURE: "CC6.6",
        DriftType.NEW_VIOLATION: "CC1.1",
        DriftType.REGRESSION: "CC7.1",
    },
    ComplianceFramework.HIPAA: {
        DriftType.ENCRYPTION_REMOVED: "164.312(a)(2)(iv)",
        DriftType.LOGGING_DISABLED: "164.312(b)",
        DriftType.PERMISSION_ESCALATION: "164.312(a)(1)",
        DriftType.BACKUP_POLICY_CHANGED: "164.308(a)(7)(ii)(A)",
        DriftType.CONFIGURATION_CHANGE: "164.312(e)(2)(ii)",
        DriftType.NETWORK_EXPOSURE: "164.312(e)(1)",
        DriftType.NEW_VIOLATION: "164.308(a)(1)(i)",
        DriftType.REGRESSION: "164.308(a)(8)",
    },
    ComplianceFramework.PCI_DSS: {
        DriftType.ENCRYPTION_REMOVED: "Req-3.4",
        DriftType.LOGGING_DISABLED: "Req-10.2",
        DriftType.PERMISSION_ESCALATION: "Req-7.1",
        DriftType.BACKUP_POLICY_CHANGED: "Req-9.5",
        DriftType.CONFIGURATION_CHANGE: "Req-6.4",
        DriftType.NETWORK_EXPOSURE: "Req-1.3",
        DriftType.NEW_VIOLATION: "Req-12.1",
        DriftType.REGRESSION: "Req-11.2",
    },
    ComplianceFramework.GDPR: {
        DriftType.ENCRYPTION_REMOVED: "Art.32(1)(a)",
        DriftType.LOGGING_DISABLED: "Art.30(1)",
        DriftType.PERMISSION_ESCALATION: "Art.25(2)",
        DriftType.BACKUP_POLICY_CHANGED: "Art.32(1)(c)",
        DriftType.CONFIGURATION_CHANGE: "Art.32(1)(d)",
        DriftType.NETWORK_EXPOSURE: "Art.32(1)(b)",
        DriftType.NEW_VIOLATION: "Art.5(1)(f)",
        DriftType.REGRESSION: "Art.32(1)(d)",
    },
    ComplianceFramework.ISO_27001: {
        DriftType.ENCRYPTION_REMOVED: "A.10.1.1",
        DriftType.LOGGING_DISABLED: "A.12.4.1",
        DriftType.PERMISSION_ESCALATION: "A.9.2.3",
        DriftType.BACKUP_POLICY_CHANGED: "A.12.3.1",
        DriftType.CONFIGURATION_CHANGE: "A.14.2.2",
        DriftType.NETWORK_EXPOSURE: "A.13.1.1",
        DriftType.NEW_VIOLATION: "A.18.2.2",
        DriftType.REGRESSION: "A.18.2.3",
    },
    ComplianceFramework.NIST_CSF: {
        DriftType.ENCRYPTION_REMOVED: "PR.DS-1",
        DriftType.LOGGING_DISABLED: "DE.AE-3",
        DriftType.PERMISSION_ESCALATION: "PR.AC-4",
        DriftType.BACKUP_POLICY_CHANGED: "PR.IP-4",
        DriftType.CONFIGURATION_CHANGE: "PR.IP-1",
        DriftType.NETWORK_EXPOSURE: "PR.AC-5",
        DriftType.NEW_VIOLATION: "ID.GV-1",
        DriftType.REGRESSION: "DE.CM-8",
    },
    ComplianceFramework.FedRAMP: {
        DriftType.ENCRYPTION_REMOVED: "SC-28",
        DriftType.LOGGING_DISABLED: "AU-2",
        DriftType.PERMISSION_ESCALATION: "AC-6",
        DriftType.BACKUP_POLICY_CHANGED: "CP-9",
        DriftType.CONFIGURATION_CHANGE: "CM-3",
        DriftType.NETWORK_EXPOSURE: "SC-7",
        DriftType.NEW_VIOLATION: "CA-2",
        DriftType.REGRESSION: "CA-7",
    },
    ComplianceFramework.CIS_BENCHMARK: {
        DriftType.ENCRYPTION_REMOVED: "CIS-2.1.1",
        DriftType.LOGGING_DISABLED: "CIS-3.1",
        DriftType.PERMISSION_ESCALATION: "CIS-1.16",
        DriftType.BACKUP_POLICY_CHANGED: "CIS-2.2.1",
        DriftType.CONFIGURATION_CHANGE: "CIS-5.1",
        DriftType.NETWORK_EXPOSURE: "CIS-4.1",
        DriftType.NEW_VIOLATION: "CIS-1.1",
        DriftType.REGRESSION: "CIS-1.2",
    },
}


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


def _drift_item_id(item: ComplianceDriftItem) -> str:
    """Deterministic identifier for a drift item."""
    raw = f"{item.component_id}:{item.framework.value}:{item.control_id}:{item.drift_type.value}"
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def _resolve_severity(
    framework: ComplianceFramework,
    drift_type: DriftType,
) -> DriftSeverity:
    fw_map = _FRAMEWORK_SEVERITY.get(framework, {})
    return fw_map.get(drift_type, DriftSeverity.MEDIUM)


def _resolve_control_id(
    framework: ComplianceFramework,
    drift_type: DriftType,
) -> str:
    fw_map = _CONTROL_IDS.get(framework, {})
    return fw_map.get(drift_type, f"{framework.value}-UNKNOWN")


class ComplianceDriftEngine:
    """Stateless engine for detecting compliance drift.

    All methods are pure functions on their arguments — no internal state
    is mutated across calls.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect_drift(
        self,
        graph: InfraGraph,
        baselines: list[ComplianceBaseline],
        current_state: dict,
    ) -> ComplianceDriftReport:
        """Detect compliance drift between baselines and current infrastructure.

        *current_state* is a dict keyed by component id with sub-dicts for each
        compliance-relevant property, e.g.::

            {
                "web-1": {
                    "encryption_at_rest": False,
                    "logging_enabled": True,
                    ...
                },
            }
        """
        drifts: list[ComplianceDriftItem] = []
        frameworks_seen: set[str] = set()

        baseline_frameworks: set[ComplianceFramework] = set()
        for bl in baselines:
            baseline_frameworks.add(bl.framework)

        for comp_id, comp in graph.components.items():
            state = current_state.get(comp_id, {})
            for fw in baseline_frameworks:
                comp_drifts = self._detect_component_drifts(comp, state, fw)
                drifts.extend(comp_drifts)
                if comp_drifts:
                    frameworks_seen.add(fw.value)

        trajectory = self.compute_trajectory(baselines)
        remediation_plans = self.prioritize_remediations(drifts)
        overall_score = self._compute_overall_drift_score(drifts)
        recommendations = self._generate_recommendations(drifts, trajectory)

        return ComplianceDriftReport(
            drifts=drifts,
            trajectory=trajectory,
            remediation_plans=remediation_plans,
            overall_drift_score=overall_score,
            frameworks_affected=sorted(frameworks_seen),
            total_controls_drifted=len(drifts),
            recommendations=recommendations,
        )

    def compare_baselines(
        self,
        old_baseline: ComplianceBaseline,
        new_baseline: ComplianceBaseline,
    ) -> list[ComplianceDriftItem]:
        """Compare two baselines and identify regressions."""
        items: list[ComplianceDriftItem] = []

        if old_baseline.framework != new_baseline.framework:
            return items

        fw = old_baseline.framework

        if new_baseline.controls_failing > old_baseline.controls_failing:
            regression_count = new_baseline.controls_failing - old_baseline.controls_failing
            severity = _resolve_severity(fw, DriftType.REGRESSION)
            items.append(
                ComplianceDriftItem(
                    component_id="baseline-comparison",
                    drift_type=DriftType.REGRESSION,
                    severity=severity,
                    framework=fw,
                    control_id=_resolve_control_id(fw, DriftType.REGRESSION),
                    baseline_state=f"failing={old_baseline.controls_failing}",
                    current_state=f"failing={new_baseline.controls_failing}",
                    description=(
                        f"{regression_count} additional control(s) now failing "
                        f"in {fw.value} (was {old_baseline.controls_failing}, "
                        f"now {new_baseline.controls_failing})"
                    ),
                    remediation=(
                        f"Investigate and remediate the {regression_count} regressed controls"
                    ),
                )
            )

        if new_baseline.score < old_baseline.score:
            score_drop = old_baseline.score - new_baseline.score
            sev = DriftSeverity.CRITICAL if score_drop >= 20 else (
                DriftSeverity.HIGH if score_drop >= 10 else DriftSeverity.MEDIUM
            )
            items.append(
                ComplianceDriftItem(
                    component_id="baseline-comparison",
                    drift_type=DriftType.REGRESSION,
                    severity=sev,
                    framework=fw,
                    control_id=_resolve_control_id(fw, DriftType.REGRESSION),
                    baseline_state=f"score={old_baseline.score:.1f}",
                    current_state=f"score={new_baseline.score:.1f}",
                    description=(
                        f"Compliance score dropped by {score_drop:.1f} points "
                        f"({old_baseline.score:.1f} → {new_baseline.score:.1f})"
                    ),
                    remediation="Review recent changes and restore compliance posture",
                )
            )

        if new_baseline.controls_passing < old_baseline.controls_passing:
            items.append(
                ComplianceDriftItem(
                    component_id="baseline-comparison",
                    drift_type=DriftType.NEW_VIOLATION,
                    severity=_resolve_severity(fw, DriftType.NEW_VIOLATION),
                    framework=fw,
                    control_id=_resolve_control_id(fw, DriftType.NEW_VIOLATION),
                    baseline_state=f"passing={old_baseline.controls_passing}",
                    current_state=f"passing={new_baseline.controls_passing}",
                    description=(
                        f"Passing controls decreased from {old_baseline.controls_passing} "
                        f"to {new_baseline.controls_passing}"
                    ),
                    remediation="Identify and fix newly failing controls",
                )
            )

        return items

    def compute_trajectory(
        self,
        baselines: list[ComplianceBaseline],
    ) -> list[ComplianceTrajectory]:
        """Compute compliance score trajectory grouped by framework."""
        by_framework: dict[ComplianceFramework, list[ComplianceBaseline]] = {}
        for bl in baselines:
            by_framework.setdefault(bl.framework, []).append(bl)

        trajectories: list[ComplianceTrajectory] = []
        for fw, fw_baselines in sorted(by_framework.items(), key=lambda x: x[0].value):
            sorted_bl = sorted(fw_baselines, key=lambda b: b.timestamp)
            scores = [b.score for b in sorted_bl]
            timestamps = [b.timestamp for b in sorted_bl]
            trend = self._compute_trend(scores)
            projected = self._project_score(scores)
            trajectories.append(
                ComplianceTrajectory(
                    framework=fw,
                    scores=scores,
                    timestamps=timestamps,
                    trend=trend,
                    projected_score=projected,
                )
            )

        return trajectories

    def generate_remediation_plan(
        self,
        drift_item: ComplianceDriftItem,
    ) -> RemediationPlan:
        """Generate a remediation plan for a single drift item."""
        item_id = _drift_item_id(drift_item)
        priority = _SEVERITY_PRIORITY.get(drift_item.severity, RemediationPriority.STANDARD)
        effort = _SEVERITY_EFFORT.get(drift_item.severity, 2.0)
        risk = self.assess_regulatory_risk(drift_item)
        steps = list(_REMEDIATION_STEPS.get(drift_item.drift_type, [
            "Investigate the drift root cause",
            "Apply corrective action",
            "Validate compliance is restored",
        ]))

        return RemediationPlan(
            drift_item_id=item_id,
            priority=priority,
            estimated_effort_hours=effort,
            regulatory_risk=risk,
            remediation_steps=steps,
        )

    def assess_regulatory_risk(
        self,
        drift_item: ComplianceDriftItem,
    ) -> str:
        """Return a human-readable regulatory risk description."""
        base_risk = _REGULATORY_RISK.get(
            drift_item.framework,
            f"Compliance risk for {drift_item.framework.value}",
        )
        if drift_item.severity == DriftSeverity.CRITICAL:
            return f"CRITICAL: {base_risk}"
        if drift_item.severity == DriftSeverity.HIGH:
            return f"HIGH: {base_risk}"
        return base_risk

    def prioritize_remediations(
        self,
        drift_items: list[ComplianceDriftItem],
    ) -> list[RemediationPlan]:
        """Generate and prioritise remediation plans for all drift items."""
        plans: list[RemediationPlan] = []
        for item in drift_items:
            plans.append(self.generate_remediation_plan(item))

        priority_order = {
            RemediationPriority.IMMEDIATE: 0,
            RemediationPriority.URGENT: 1,
            RemediationPriority.STANDARD: 2,
            RemediationPriority.DEFERRED: 3,
        }
        plans.sort(key=lambda p: (
            priority_order.get(p.priority, 99),
            -p.estimated_effort_hours,
        ))
        return plans

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _detect_component_drifts(
        self,
        comp: Component,
        state: dict,
        framework: ComplianceFramework,
    ) -> list[ComplianceDriftItem]:
        """Detect drifts for a single component against a framework."""
        drifts: list[ComplianceDriftItem] = []

        # Encryption at rest check
        baseline_encrypt = comp.security.encryption_at_rest
        current_encrypt = state.get("encryption_at_rest", baseline_encrypt)
        if baseline_encrypt and not current_encrypt:
            drifts.append(ComplianceDriftItem(
                component_id=comp.id,
                drift_type=DriftType.ENCRYPTION_REMOVED,
                severity=_resolve_severity(framework, DriftType.ENCRYPTION_REMOVED),
                framework=framework,
                control_id=_resolve_control_id(framework, DriftType.ENCRYPTION_REMOVED),
                baseline_state="encryption_at_rest=true",
                current_state="encryption_at_rest=false",
                description=f"Encryption at rest was disabled on {comp.id}",
                remediation=f"Re-enable encryption at rest on {comp.id}",
            ))

        # Encryption in transit check
        baseline_transit = comp.security.encryption_in_transit
        current_transit = state.get("encryption_in_transit", baseline_transit)
        if baseline_transit and not current_transit:
            drifts.append(ComplianceDriftItem(
                component_id=comp.id,
                drift_type=DriftType.ENCRYPTION_REMOVED,
                severity=_resolve_severity(framework, DriftType.ENCRYPTION_REMOVED),
                framework=framework,
                control_id=_resolve_control_id(framework, DriftType.ENCRYPTION_REMOVED),
                baseline_state="encryption_in_transit=true",
                current_state="encryption_in_transit=false",
                description=f"Encryption in transit was disabled on {comp.id}",
                remediation=f"Re-enable TLS/encryption in transit on {comp.id}",
            ))

        # Logging check
        baseline_log = comp.security.log_enabled
        current_log = state.get("logging_enabled", baseline_log)
        if baseline_log and not current_log:
            drifts.append(ComplianceDriftItem(
                component_id=comp.id,
                drift_type=DriftType.LOGGING_DISABLED,
                severity=_resolve_severity(framework, DriftType.LOGGING_DISABLED),
                framework=framework,
                control_id=_resolve_control_id(framework, DriftType.LOGGING_DISABLED),
                baseline_state="logging_enabled=true",
                current_state="logging_enabled=false",
                description=f"Audit logging was disabled on {comp.id}",
                remediation=f"Re-enable audit logging on {comp.id}",
            ))

        # Auth / permission check
        baseline_auth = comp.security.auth_required
        current_auth = state.get("auth_required", baseline_auth)
        if baseline_auth and not current_auth:
            drifts.append(ComplianceDriftItem(
                component_id=comp.id,
                drift_type=DriftType.PERMISSION_ESCALATION,
                severity=_resolve_severity(framework, DriftType.PERMISSION_ESCALATION),
                framework=framework,
                control_id=_resolve_control_id(framework, DriftType.PERMISSION_ESCALATION),
                baseline_state="auth_required=true",
                current_state="auth_required=false",
                description=f"Authentication requirement removed on {comp.id}",
                remediation=f"Re-enable authentication on {comp.id}",
            ))

        # Backup policy check
        baseline_backup = comp.security.backup_enabled
        current_backup = state.get("backup_enabled", baseline_backup)
        if baseline_backup and not current_backup:
            drifts.append(ComplianceDriftItem(
                component_id=comp.id,
                drift_type=DriftType.BACKUP_POLICY_CHANGED,
                severity=_resolve_severity(framework, DriftType.BACKUP_POLICY_CHANGED),
                framework=framework,
                control_id=_resolve_control_id(framework, DriftType.BACKUP_POLICY_CHANGED),
                baseline_state="backup_enabled=true",
                current_state="backup_enabled=false",
                description=f"Backup policy was disabled on {comp.id}",
                remediation=f"Re-enable backup on {comp.id}",
            ))

        # Network segmentation check
        baseline_seg = comp.security.network_segmented
        current_seg = state.get("network_segmented", baseline_seg)
        if baseline_seg and not current_seg:
            drifts.append(ComplianceDriftItem(
                component_id=comp.id,
                drift_type=DriftType.NETWORK_EXPOSURE,
                severity=_resolve_severity(framework, DriftType.NETWORK_EXPOSURE),
                framework=framework,
                control_id=_resolve_control_id(framework, DriftType.NETWORK_EXPOSURE),
                baseline_state="network_segmented=true",
                current_state="network_segmented=false",
                description=f"Network segmentation removed on {comp.id}",
                remediation=f"Restore network segmentation on {comp.id}",
            ))

        # WAF check
        baseline_waf = comp.security.waf_protected
        current_waf = state.get("waf_protected", baseline_waf)
        if baseline_waf and not current_waf:
            drifts.append(ComplianceDriftItem(
                component_id=comp.id,
                drift_type=DriftType.NETWORK_EXPOSURE,
                severity=_resolve_severity(framework, DriftType.NETWORK_EXPOSURE),
                framework=framework,
                control_id=_resolve_control_id(framework, DriftType.NETWORK_EXPOSURE),
                baseline_state="waf_protected=true",
                current_state="waf_protected=false",
                description=f"WAF protection removed on {comp.id}",
                remediation=f"Re-enable WAF on {comp.id}",
            ))

        # Rate limiting check
        baseline_rate = comp.security.rate_limiting
        current_rate = state.get("rate_limiting", baseline_rate)
        if baseline_rate and not current_rate:
            drifts.append(ComplianceDriftItem(
                component_id=comp.id,
                drift_type=DriftType.CONFIGURATION_CHANGE,
                severity=_resolve_severity(framework, DriftType.CONFIGURATION_CHANGE),
                framework=framework,
                control_id=_resolve_control_id(framework, DriftType.CONFIGURATION_CHANGE),
                baseline_state="rate_limiting=true",
                current_state="rate_limiting=false",
                description=f"Rate limiting was disabled on {comp.id}",
                remediation=f"Re-enable rate limiting on {comp.id}",
            ))

        # IDS monitoring check
        baseline_ids = comp.security.ids_monitored
        current_ids = state.get("ids_monitored", baseline_ids)
        if baseline_ids and not current_ids:
            drifts.append(ComplianceDriftItem(
                component_id=comp.id,
                drift_type=DriftType.LOGGING_DISABLED,
                severity=_resolve_severity(framework, DriftType.LOGGING_DISABLED),
                framework=framework,
                control_id=_resolve_control_id(framework, DriftType.LOGGING_DISABLED),
                baseline_state="ids_monitored=true",
                current_state="ids_monitored=false",
                description=f"IDS monitoring was disabled on {comp.id}",
                remediation=f"Re-enable IDS monitoring on {comp.id}",
            ))

        return drifts

    def _compute_overall_drift_score(
        self,
        drifts: list[ComplianceDriftItem],
    ) -> float:
        """Compute a 0-100 drift score where 100 = maximum drift (worst)."""
        if not drifts:
            return 0.0
        total_weight = sum(_SEVERITY_WEIGHT.get(d.severity, 0.0) for d in drifts)
        # Normalise: cap at 100
        return min(100.0, round(total_weight, 1))

    def _compute_trend(self, scores: list[float]) -> str:
        """Determine trend direction from a list of scores."""
        if len(scores) < 2:
            return "stable"
        first_half = scores[: len(scores) // 2] or scores[:1]
        second_half = scores[len(scores) // 2 :]
        avg_first = sum(first_half) / len(first_half)
        avg_second = sum(second_half) / len(second_half)
        diff = avg_second - avg_first
        if diff > 2.0:
            return "improving"
        if diff < -2.0:
            return "declining"
        return "stable"

    def _project_score(self, scores: list[float]) -> float:
        """Simple linear projection of the next compliance score."""
        if len(scores) == 0:
            return 0.0
        if len(scores) == 1:
            return scores[0]
        # Use last two data points for linear extrapolation
        delta = scores[-1] - scores[-2]
        projected = scores[-1] + delta
        return max(0.0, min(100.0, round(projected, 1)))

    def _generate_recommendations(
        self,
        drifts: list[ComplianceDriftItem],
        trajectories: list[ComplianceTrajectory],
    ) -> list[str]:
        """Generate actionable recommendations based on drift analysis."""
        recs: list[str] = []

        critical_count = sum(1 for d in drifts if d.severity == DriftSeverity.CRITICAL)
        high_count = sum(1 for d in drifts if d.severity == DriftSeverity.HIGH)

        if critical_count > 0:
            recs.append(
                f"URGENT: {critical_count} critical drift(s) detected — "
                "initiate immediate remediation"
            )

        if high_count > 0:
            recs.append(
                f"{high_count} high-severity drift(s) require attention within 48 hours"
            )

        # Check for encryption drifts
        encryption_drifts = [d for d in drifts if d.drift_type == DriftType.ENCRYPTION_REMOVED]
        if encryption_drifts:
            recs.append(
                "Encryption controls have been weakened — review encryption posture across all components"
            )

        # Check for logging drifts
        logging_drifts = [d for d in drifts if d.drift_type == DriftType.LOGGING_DISABLED]
        if logging_drifts:
            recs.append(
                "Audit logging has been disabled on some components — restore logging immediately"
            )

        # Trajectory-based recommendations
        for traj in trajectories:
            if traj.trend == "declining":
                recs.append(
                    f"Compliance score for {traj.framework.value} is declining "
                    f"(projected: {traj.projected_score:.1f}) — schedule a compliance review"
                )

        # Network exposure
        network_drifts = [d for d in drifts if d.drift_type == DriftType.NETWORK_EXPOSURE]
        if network_drifts:
            recs.append(
                "Network exposure has increased — review firewall rules and network segmentation"
            )

        # Multi-framework impact
        affected_fw = {d.framework.value for d in drifts}
        if len(affected_fw) > 2:
            recs.append(
                f"Drift affects {len(affected_fw)} frameworks — consider a comprehensive compliance audit"
            )

        if not recs and not drifts:
            recs.append("No compliance drift detected — maintain current posture")

        return recs
