# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Compliance-Driven Chaos Generator.

Automatically generates chaos experiments from compliance requirements.
Given a compliance framework (SOC2, HIPAA, PCI-DSS, ISO27001, GDPR),
generates chaos experiments that test whether the infrastructure meets
those requirements under failure conditions.

This is a unique FaultRay feature — no competitor offers compliance-driven
chaos experiment generation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from faultray.model.components import Component, ComponentType
from faultray.model.graph import InfraGraph


class ComplianceFramework(str, Enum):
    """Supported compliance frameworks."""

    SOC2 = "soc2"
    HIPAA = "hipaa"
    PCI_DSS = "pci_dss"
    ISO27001 = "iso27001"
    GDPR = "gdpr"


class ControlCategory(str, Enum):
    """Categories of compliance controls."""

    DATA_PROTECTION = "data_protection"
    ACCESS_CONTROL = "access_control"
    AVAILABILITY = "availability"
    AUDIT_LOGGING = "audit_logging"
    ENCRYPTION = "encryption"
    BACKUP_RECOVERY = "backup_recovery"
    INCIDENT_RESPONSE = "incident_response"
    NETWORK_SECURITY = "network_security"


@dataclass
class ComplianceControl:
    """A single compliance control within a framework."""

    framework: ComplianceFramework
    category: ControlCategory
    control_id: str
    description: str
    chaos_relevant: bool


@dataclass
class ComplianceChaosExperiment:
    """A chaos experiment generated from a compliance control."""

    control: ComplianceControl
    experiment_description: str
    target_components: list[str]
    validation_criteria: str
    expected_behavior: str
    failure_scenario: str
    severity_if_failed: str  # "critical", "high", "medium", "low"


@dataclass
class ComplianceGap:
    """A compliance gap detected in the infrastructure."""

    control: ComplianceControl
    component_id: str
    component_name: str
    gap_description: str
    remediation: str


@dataclass
class ComplianceChaosReport:
    """Report of compliance chaos analysis for a single framework."""

    framework: ComplianceFramework
    total_controls: int
    chaos_relevant_controls: int
    experiments_generated: int
    gaps_found: int
    experiments: list[ComplianceChaosExperiment]
    gaps: list[ComplianceGap]
    coverage_percentage: float
    summary: str


# ---------------------------------------------------------------------------
# Built-in control definitions per framework
# ---------------------------------------------------------------------------

_SOC2_CONTROLS: list[ComplianceControl] = [
    ComplianceControl(
        framework=ComplianceFramework.SOC2,
        category=ControlCategory.DATA_PROTECTION,
        control_id="CC6.1",
        description="Logical and physical access controls",
        chaos_relevant=True,
    ),
    ComplianceControl(
        framework=ComplianceFramework.SOC2,
        category=ControlCategory.AVAILABILITY,
        control_id="A1.2",
        description="Environmental protections",
        chaos_relevant=True,
    ),
    ComplianceControl(
        framework=ComplianceFramework.SOC2,
        category=ControlCategory.ENCRYPTION,
        control_id="CC6.7",
        description="Encryption of data in transit and at rest",
        chaos_relevant=True,
    ),
    ComplianceControl(
        framework=ComplianceFramework.SOC2,
        category=ControlCategory.AUDIT_LOGGING,
        control_id="CC7.2",
        description="System monitoring",
        chaos_relevant=True,
    ),
    ComplianceControl(
        framework=ComplianceFramework.SOC2,
        category=ControlCategory.BACKUP_RECOVERY,
        control_id="A1.3",
        description="Recovery procedures",
        chaos_relevant=True,
    ),
    ComplianceControl(
        framework=ComplianceFramework.SOC2,
        category=ControlCategory.INCIDENT_RESPONSE,
        control_id="CC7.4",
        description="Incident response",
        chaos_relevant=True,
    ),
]

_HIPAA_CONTROLS: list[ComplianceControl] = [
    ComplianceControl(
        framework=ComplianceFramework.HIPAA,
        category=ControlCategory.DATA_PROTECTION,
        control_id="164.312(a)",
        description="Access control",
        chaos_relevant=True,
    ),
    ComplianceControl(
        framework=ComplianceFramework.HIPAA,
        category=ControlCategory.ENCRYPTION,
        control_id="164.312(e)",
        description="Transmission security",
        chaos_relevant=True,
    ),
    ComplianceControl(
        framework=ComplianceFramework.HIPAA,
        category=ControlCategory.AUDIT_LOGGING,
        control_id="164.312(b)",
        description="Audit controls",
        chaos_relevant=True,
    ),
    ComplianceControl(
        framework=ComplianceFramework.HIPAA,
        category=ControlCategory.BACKUP_RECOVERY,
        control_id="164.308(a)(7)",
        description="Contingency plan",
        chaos_relevant=True,
    ),
    ComplianceControl(
        framework=ComplianceFramework.HIPAA,
        category=ControlCategory.AVAILABILITY,
        control_id="164.308(a)(7)(ii)(B)",
        description="Disaster recovery",
        chaos_relevant=True,
    ),
]

_PCI_DSS_CONTROLS: list[ComplianceControl] = [
    ComplianceControl(
        framework=ComplianceFramework.PCI_DSS,
        category=ControlCategory.NETWORK_SECURITY,
        control_id="Req 1",
        description="Network security controls",
        chaos_relevant=True,
    ),
    ComplianceControl(
        framework=ComplianceFramework.PCI_DSS,
        category=ControlCategory.ENCRYPTION,
        control_id="Req 4",
        description="Protect cardholder data in transit",
        chaos_relevant=True,
    ),
    ComplianceControl(
        framework=ComplianceFramework.PCI_DSS,
        category=ControlCategory.ACCESS_CONTROL,
        control_id="Req 7",
        description="Restrict access",
        chaos_relevant=True,
    ),
    ComplianceControl(
        framework=ComplianceFramework.PCI_DSS,
        category=ControlCategory.AUDIT_LOGGING,
        control_id="Req 10",
        description="Log and monitor",
        chaos_relevant=True,
    ),
    ComplianceControl(
        framework=ComplianceFramework.PCI_DSS,
        category=ControlCategory.AVAILABILITY,
        control_id="Req 12.10",
        description="Incident response plan",
        chaos_relevant=True,
    ),
]

_ISO27001_CONTROLS: list[ComplianceControl] = [
    ComplianceControl(
        framework=ComplianceFramework.ISO27001,
        category=ControlCategory.ACCESS_CONTROL,
        control_id="A.9",
        description="Access control",
        chaos_relevant=True,
    ),
    ComplianceControl(
        framework=ComplianceFramework.ISO27001,
        category=ControlCategory.ENCRYPTION,
        control_id="A.10",
        description="Cryptography",
        chaos_relevant=True,
    ),
    ComplianceControl(
        framework=ComplianceFramework.ISO27001,
        category=ControlCategory.AVAILABILITY,
        control_id="A.17",
        description="Business continuity",
        chaos_relevant=True,
    ),
    ComplianceControl(
        framework=ComplianceFramework.ISO27001,
        category=ControlCategory.BACKUP_RECOVERY,
        control_id="A.12.3",
        description="Backup",
        chaos_relevant=True,
    ),
]

_GDPR_CONTROLS: list[ComplianceControl] = [
    ComplianceControl(
        framework=ComplianceFramework.GDPR,
        category=ControlCategory.DATA_PROTECTION,
        control_id="Art.32",
        description="Security of processing",
        chaos_relevant=True,
    ),
    ComplianceControl(
        framework=ComplianceFramework.GDPR,
        category=ControlCategory.ENCRYPTION,
        control_id="Art.32(1)(a)",
        description="Encryption",
        chaos_relevant=True,
    ),
    ComplianceControl(
        framework=ComplianceFramework.GDPR,
        category=ControlCategory.AVAILABILITY,
        control_id="Art.32(1)(b)",
        description="Availability and resilience",
        chaos_relevant=True,
    ),
    ComplianceControl(
        framework=ComplianceFramework.GDPR,
        category=ControlCategory.BACKUP_RECOVERY,
        control_id="Art.32(1)(c)",
        description="Restore availability",
        chaos_relevant=True,
    ),
]

_CONTROLS_MAP: dict[ComplianceFramework, list[ComplianceControl]] = {
    ComplianceFramework.SOC2: _SOC2_CONTROLS,
    ComplianceFramework.HIPAA: _HIPAA_CONTROLS,
    ComplianceFramework.PCI_DSS: _PCI_DSS_CONTROLS,
    ComplianceFramework.ISO27001: _ISO27001_CONTROLS,
    ComplianceFramework.GDPR: _GDPR_CONTROLS,
}

# ---------------------------------------------------------------------------
# Data-store component types (subject to encryption / backup controls)
# ---------------------------------------------------------------------------

_DATA_STORE_TYPES = {ComponentType.DATABASE, ComponentType.STORAGE, ComponentType.CACHE}


class ComplianceChaosGenerator:
    """Generate chaos experiments from compliance requirements.

    Given an :class:`InfraGraph`, the generator inspects component
    configurations and produces :class:`ComplianceChaosExperiment` entries
    that, when executed, validate whether the infrastructure meets the
    selected compliance framework under failure conditions.
    """

    def __init__(self, graph: InfraGraph) -> None:
        self._graph = graph

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(self, framework: ComplianceFramework) -> ComplianceChaosReport:
        """Generate a compliance chaos report for a single framework."""
        controls = self._get_controls(framework)
        components = list(self._graph.components.values())
        chaos_relevant = [c for c in controls if c.chaos_relevant]

        experiments = self._generate_experiments(chaos_relevant, components)
        gaps = self._find_gaps(chaos_relevant, components)

        total = len(controls)
        relevant = len(chaos_relevant)

        # Coverage = controls that have at least one experiment / total chaos-relevant
        if relevant > 0:
            covered_controls = {exp.control.control_id for exp in experiments}
            coverage = len(covered_controls) / relevant * 100.0
        else:
            coverage = 100.0

        summary = (
            f"Compliance chaos analysis for {framework.value.upper()}: "
            f"{len(experiments)} experiments generated from {relevant} chaos-relevant controls "
            f"({total} total). {len(gaps)} compliance gaps detected. "
            f"Coverage: {coverage:.1f}%."
        )

        return ComplianceChaosReport(
            framework=framework,
            total_controls=total,
            chaos_relevant_controls=relevant,
            experiments_generated=len(experiments),
            gaps_found=len(gaps),
            experiments=experiments,
            gaps=gaps,
            coverage_percentage=round(coverage, 1),
            summary=summary,
        )

    def generate_all(self) -> list[ComplianceChaosReport]:
        """Generate compliance chaos reports for **all** supported frameworks."""
        return [self.generate(fw) for fw in ComplianceFramework]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_controls(self, framework: ComplianceFramework) -> list[ComplianceControl]:
        """Return the built-in control definitions for *framework*."""
        return list(_CONTROLS_MAP.get(framework, []))

    def _generate_experiments(
        self,
        controls: list[ComplianceControl],
        components: list[Component],
    ) -> list[ComplianceChaosExperiment]:
        """Map controls x components into concrete chaos experiments."""
        experiments: list[ComplianceChaosExperiment] = []

        for control in controls:
            cat = control.category
            handler = _CATEGORY_EXPERIMENT_HANDLERS.get(cat)
            if handler is None:
                continue
            for comp in components:
                exp = handler(control, comp)
                if exp is not None:
                    experiments.append(exp)

        return experiments

    def _find_gaps(
        self,
        controls: list[ComplianceControl],
        components: list[Component],
    ) -> list[ComplianceGap]:
        """Detect compliance gaps in the current infrastructure."""
        gaps: list[ComplianceGap] = []

        for control in controls:
            cat = control.category
            handler = _CATEGORY_GAP_HANDLERS.get(cat)
            if handler is None:
                continue
            for comp in components:
                gap = handler(control, comp)
                if gap is not None:
                    gaps.append(gap)

        return gaps


# ======================================================================
# Experiment generation handlers (one per ControlCategory)
# ======================================================================


def _experiment_data_protection(
    control: ComplianceControl, comp: Component
) -> ComplianceChaosExperiment | None:
    """DATA_PROTECTION: DB/STORAGE without encryption -> unauthorized access experiment."""
    if comp.type not in _DATA_STORE_TYPES:
        return None
    if comp.security.encryption_at_rest:
        return None
    return ComplianceChaosExperiment(
        control=control,
        experiment_description=(
            f"Simulate unauthorized access during component failure on '{comp.name}'"
        ),
        target_components=[comp.id],
        validation_criteria="Data must remain inaccessible to unauthorized parties during failure",
        expected_behavior="Access controls enforce data protection even under degraded conditions",
        failure_scenario=f"Component '{comp.name}' fails with unencrypted data at rest",
        severity_if_failed="critical",
    )


def _experiment_availability(
    control: ComplianceControl, comp: Component
) -> ComplianceChaosExperiment | None:
    """AVAILABILITY: single-replica -> kill instance to test SLA."""
    if comp.replicas > 1:
        return None
    return ComplianceChaosExperiment(
        control=control,
        experiment_description=(
            f"Kill single instance to test availability SLA on '{comp.name}'"
        ),
        target_components=[comp.id],
        validation_criteria="Service must remain available after instance termination",
        expected_behavior="Failover or restart restores availability within SLA",
        failure_scenario=f"Single instance of '{comp.name}' is terminated",
        severity_if_failed="high",
    )


def _experiment_encryption(
    control: ComplianceControl, comp: Component
) -> ComplianceChaosExperiment | None:
    """ENCRYPTION: missing encryption in transit -> data exposure during network partition."""
    if comp.security.encryption_in_transit:
        return None
    return ComplianceChaosExperiment(
        control=control,
        experiment_description=(
            f"Test data exposure during network partition on '{comp.name}'"
        ),
        target_components=[comp.id],
        validation_criteria="Data must not be exposed in plaintext during network disruption",
        expected_behavior="All data in transit is encrypted regardless of network state",
        failure_scenario=(
            f"Network partition isolates '{comp.name}' with unencrypted traffic"
        ),
        severity_if_failed="critical",
    )


def _experiment_audit_logging(
    control: ComplianceControl, comp: Component
) -> ComplianceChaosExperiment | None:
    """AUDIT_LOGGING: no logging -> verify audit trail during incident."""
    if comp.security.log_enabled:
        return None
    return ComplianceChaosExperiment(
        control=control,
        experiment_description=(
            f"Verify audit trail during incident on '{comp.name}'"
        ),
        target_components=[comp.id],
        validation_criteria="Audit logs must capture all events during failure",
        expected_behavior="Complete audit trail is available for post-incident analysis",
        failure_scenario=f"Incident occurs on '{comp.name}' with logging disabled",
        severity_if_failed="high",
    )


def _experiment_backup_recovery(
    control: ComplianceControl, comp: Component
) -> ComplianceChaosExperiment | None:
    """BACKUP_RECOVERY: DB/STORAGE/CACHE without backup -> data loss experiment."""
    if comp.type not in _DATA_STORE_TYPES:
        return None
    if comp.security.backup_enabled:
        return None
    return ComplianceChaosExperiment(
        control=control,
        experiment_description=(
            f"Simulate data loss and recovery on '{comp.name}'"
        ),
        target_components=[comp.id],
        validation_criteria="Data must be recoverable within RTO/RPO targets",
        expected_behavior="Backup and recovery procedures restore data successfully",
        failure_scenario=f"Data loss event on '{comp.name}' without backup configured",
        severity_if_failed="critical",
    )


def _experiment_incident_response(
    control: ComplianceControl, comp: Component
) -> ComplianceChaosExperiment | None:
    """INCIDENT_RESPONSE: for all components -> cascade failure to test response time."""
    return ComplianceChaosExperiment(
        control=control,
        experiment_description=(
            f"Cascade failure to test incident response time on '{comp.name}'"
        ),
        target_components=[comp.id],
        validation_criteria="Incident response team must acknowledge and respond within SLA",
        expected_behavior="Incident detection, escalation and mitigation complete within target time",
        failure_scenario=f"Cascading failure originating from '{comp.name}'",
        severity_if_failed="high",
    )


def _experiment_network_security(
    control: ComplianceControl, comp: Component
) -> ComplianceChaosExperiment | None:
    """NETWORK_SECURITY: WEB_SERVER without WAF -> DDoS / network attack simulation."""
    if comp.type != ComponentType.WEB_SERVER:
        return None
    if comp.security.waf_protected:
        return None
    return ComplianceChaosExperiment(
        control=control,
        experiment_description=(
            f"Simulate DDoS/network attack on '{comp.name}'"
        ),
        target_components=[comp.id],
        validation_criteria="Web server must withstand network attack without service disruption",
        expected_behavior="WAF and rate limiting mitigate attack traffic",
        failure_scenario=f"DDoS attack targets '{comp.name}' without WAF protection",
        severity_if_failed="critical",
    )


def _experiment_access_control(
    control: ComplianceControl, comp: Component
) -> ComplianceChaosExperiment | None:
    """ACCESS_CONTROL: components without auth_required -> test access during partial outage."""
    if comp.security.auth_required:
        return None
    return ComplianceChaosExperiment(
        control=control,
        experiment_description=(
            f"Test access during partial outage on '{comp.name}'"
        ),
        target_components=[comp.id],
        validation_criteria="Access controls must remain enforced during partial failures",
        expected_behavior="Authentication and authorization are maintained under degraded conditions",
        failure_scenario=f"Partial outage of '{comp.name}' with no authentication required",
        severity_if_failed="high",
    )


_CATEGORY_EXPERIMENT_HANDLERS = {
    ControlCategory.DATA_PROTECTION: _experiment_data_protection,
    ControlCategory.AVAILABILITY: _experiment_availability,
    ControlCategory.ENCRYPTION: _experiment_encryption,
    ControlCategory.AUDIT_LOGGING: _experiment_audit_logging,
    ControlCategory.BACKUP_RECOVERY: _experiment_backup_recovery,
    ControlCategory.INCIDENT_RESPONSE: _experiment_incident_response,
    ControlCategory.NETWORK_SECURITY: _experiment_network_security,
    ControlCategory.ACCESS_CONTROL: _experiment_access_control,
}


# ======================================================================
# Gap detection handlers (one per ControlCategory)
# ======================================================================


def _gap_data_protection(
    control: ComplianceControl, comp: Component
) -> ComplianceGap | None:
    """Missing encryption on data stores."""
    if comp.type not in _DATA_STORE_TYPES:
        return None
    if comp.security.encryption_at_rest:
        return None
    return ComplianceGap(
        control=control,
        component_id=comp.id,
        component_name=comp.name,
        gap_description=f"Data store '{comp.name}' lacks encryption at rest",
        remediation="Enable encryption at rest for this data store",
    )


def _gap_availability(
    control: ComplianceControl, comp: Component
) -> ComplianceGap | None:
    """Single replica on critical components."""
    if comp.replicas > 1:
        return None
    if not comp.failover.enabled:
        return ComplianceGap(
            control=control,
            component_id=comp.id,
            component_name=comp.name,
            gap_description=(
                f"Component '{comp.name}' has single replica and no failover configured"
            ),
            remediation="Add replicas or enable failover for high availability",
        )
    return None


def _gap_encryption(
    control: ComplianceControl, comp: Component
) -> ComplianceGap | None:
    """Missing encryption in transit."""
    if comp.security.encryption_in_transit:
        return None
    return ComplianceGap(
        control=control,
        component_id=comp.id,
        component_name=comp.name,
        gap_description=f"Component '{comp.name}' lacks encryption in transit",
        remediation="Enable TLS/SSL for all data in transit",
    )


def _gap_audit_logging(
    control: ComplianceControl, comp: Component
) -> ComplianceGap | None:
    """No logging enabled."""
    if comp.security.log_enabled:
        return None
    return ComplianceGap(
        control=control,
        component_id=comp.id,
        component_name=comp.name,
        gap_description=f"Component '{comp.name}' has logging disabled",
        remediation="Enable audit logging for compliance monitoring",
    )


def _gap_backup_recovery(
    control: ComplianceControl, comp: Component
) -> ComplianceGap | None:
    """No backup on data components."""
    if comp.type not in _DATA_STORE_TYPES:
        return None
    if comp.security.backup_enabled:
        return None
    return ComplianceGap(
        control=control,
        component_id=comp.id,
        component_name=comp.name,
        gap_description=f"Data store '{comp.name}' has no backup configured",
        remediation="Enable automated backups with appropriate retention policy",
    )


def _gap_incident_response(
    control: ComplianceControl, comp: Component
) -> ComplianceGap | None:
    """Incident response gaps are not component-specific — always return None."""
    return None


def _gap_network_security(
    control: ComplianceControl, comp: Component
) -> ComplianceGap | None:
    """No WAF on web-facing components."""
    if comp.type != ComponentType.WEB_SERVER:
        return None
    if comp.security.waf_protected:
        return None
    return ComplianceGap(
        control=control,
        component_id=comp.id,
        component_name=comp.name,
        gap_description=f"Web server '{comp.name}' is not WAF-protected",
        remediation="Deploy a Web Application Firewall in front of this web server",
    )


def _gap_access_control(
    control: ComplianceControl, comp: Component
) -> ComplianceGap | None:
    """No auth required."""
    if comp.security.auth_required:
        return None
    return ComplianceGap(
        control=control,
        component_id=comp.id,
        component_name=comp.name,
        gap_description=f"Component '{comp.name}' does not require authentication",
        remediation="Enable authentication and authorization for this component",
    )


_CATEGORY_GAP_HANDLERS = {
    ControlCategory.DATA_PROTECTION: _gap_data_protection,
    ControlCategory.AVAILABILITY: _gap_availability,
    ControlCategory.ENCRYPTION: _gap_encryption,
    ControlCategory.AUDIT_LOGGING: _gap_audit_logging,
    ControlCategory.BACKUP_RECOVERY: _gap_backup_recovery,
    ControlCategory.INCIDENT_RESPONSE: _gap_incident_response,
    ControlCategory.NETWORK_SECURITY: _gap_network_security,
    ControlCategory.ACCESS_CONTROL: _gap_access_control,
}
