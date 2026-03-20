# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Compliance Posture Analyzer — assess infrastructure compliance posture.

Evaluates infrastructure against multiple compliance frameworks (SOC2,
ISO 27001, PCI DSS, HIPAA, GDPR, NIST CSF, FedRAMP, DORA, CIS Benchmark)
by inspecting component configurations, security profiles, dependency edges,
and operational readiness. Produces structured reports with gap analysis,
remediation priorities, cost estimates, audit evidence, and trend tracking.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, field_validator

from faultray.model.components import ComponentType
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Framework(str, Enum):
    """Supported compliance frameworks."""

    SOC2 = "soc2"
    ISO27001 = "iso27001"
    PCI_DSS = "pci_dss"
    HIPAA = "hipaa"
    GDPR = "gdpr"
    NIST_CSF = "nist_csf"
    FEDRAMP = "fedramp"
    DORA = "dora"
    CIS_BENCHMARK = "cis_benchmark"


class ControlStatus(str, Enum):
    """Assessment status for an individual compliance control."""

    COMPLIANT = "compliant"
    PARTIALLY_COMPLIANT = "partially_compliant"
    NON_COMPLIANT = "non_compliant"
    NOT_APPLICABLE = "not_applicable"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class Control(BaseModel):
    """Result of assessing a single compliance control."""

    framework: Framework
    control_id: str
    title: str
    description: str
    status: ControlStatus
    evidence: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    remediation: str = ""


class PostureReport(BaseModel):
    """Aggregated posture report for a single compliance framework."""

    framework: Framework
    overall_score: float = Field(default=0.0, ge=0.0, le=100.0)
    controls: list[Control] = Field(default_factory=list)
    compliant_count: int = 0
    non_compliant_count: int = 0
    critical_gaps: list[str] = Field(default_factory=list)
    remediation_priority: list[str] = Field(default_factory=list)
    estimated_remediation_hours: float = 0.0
    recommendations: list[str] = Field(default_factory=list)

    @field_validator("overall_score")
    @classmethod
    def _clamp_score(cls, v: float) -> float:
        return max(0.0, min(100.0, v))


class CrossFrameworkGap(BaseModel):
    """A compliance gap that affects multiple frameworks."""

    gap_description: str
    affected_frameworks: list[Framework] = Field(default_factory=list)
    affected_control_ids: list[str] = Field(default_factory=list)
    severity: str = "medium"  # low, medium, high, critical
    shared_remediation: str = ""


class ComplianceCostEstimate(BaseModel):
    """Estimated cost to achieve compliance for a framework."""

    framework: Framework
    total_estimated_hours: float = 0.0
    total_estimated_cost_usd: float = 0.0
    cost_by_category: dict[str, float] = Field(default_factory=dict)
    hourly_rate_usd: float = 150.0
    controls_needing_work: int = 0
    timeline_weeks: int = 0


class AuditEvidence(BaseModel):
    """A single piece of audit evidence."""

    control_id: str
    evidence_type: str = ""  # configuration, documentation, log, screenshot
    description: str = ""
    component_ids: list[str] = Field(default_factory=list)
    status: str = "collected"  # collected, pending, missing


class AuditPackage(BaseModel):
    """Complete audit evidence package for a framework assessment."""

    framework: Framework
    evidence_items: list[AuditEvidence] = Field(default_factory=list)
    coverage_percent: float = 0.0
    missing_evidence: list[str] = Field(default_factory=list)
    summary: str = ""


class PostureTrendPoint(BaseModel):
    """A single data point in a posture trend."""

    framework: Framework
    score: float = 0.0
    compliant_count: int = 0
    non_compliant_count: int = 0


class PostureTrend(BaseModel):
    """Trend analysis across multiple posture reports."""

    data_points: list[PostureTrendPoint] = Field(default_factory=list)
    direction: str = "stable"  # improving, stable, degrading
    average_score: float = 0.0
    score_delta: float = 0.0
    recommendations: list[str] = Field(default_factory=list)


class RemediationPriority(BaseModel):
    """A prioritized remediation item across frameworks."""

    rank: int = 0
    control_id: str = ""
    framework: Framework = Framework.SOC2
    gap_description: str = ""
    impact_score: float = 0.0
    effort_hours: float = 0.0
    priority: str = "medium"  # low, medium, high, critical


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Hours to remediate per control status
_REMEDIATION_HOURS: dict[ControlStatus, float] = {
    ControlStatus.NON_COMPLIANT: 16.0,
    ControlStatus.PARTIALLY_COMPLIANT: 8.0,
    ControlStatus.UNKNOWN: 12.0,
    ControlStatus.COMPLIANT: 0.0,
    ControlStatus.NOT_APPLICABLE: 0.0,
}

# Severity weights for gap priority calculation
_SEVERITY_WEIGHTS: dict[str, float] = {
    "critical": 4.0,
    "high": 3.0,
    "medium": 2.0,
    "low": 1.0,
}

# Framework-specific control definitions (control_id, title, description)
_FRAMEWORK_CONTROLS: dict[Framework, list[tuple[str, str, str]]] = {
    Framework.SOC2: [
        ("CC6.1", "Access Control", "Logical and physical access controls"),
        ("CC6.6", "Encryption", "Encryption of data in transit"),
        ("CC7.2", "Monitoring", "System monitoring and anomaly detection"),
        ("CC8.1", "Change Management", "Change management process"),
        ("A1.2", "Availability", "Redundancy and failover mechanisms"),
    ],
    Framework.ISO27001: [
        ("A.9.1.1", "Access Control", "Access control policy"),
        ("A.10.1.1", "Cryptography", "Policy on use of cryptographic controls"),
        ("A.12.4.1", "Logging", "Event logging and monitoring"),
        ("A.17.1.1", "BC Planning", "Business continuity planning"),
        ("A.17.1.2", "BC Implementation", "Implementing redundancy for continuity"),
    ],
    Framework.PCI_DSS: [
        ("Req-1.3", "Network Segmentation", "Prohibit direct public access to cardholder data"),
        ("Req-3.4", "Data Protection", "Render PAN unreadable with encryption at rest"),
        ("Req-6.1", "Vulnerability Mgmt", "Identify and address security vulnerabilities"),
        ("Req-10.1", "Audit Trails", "Implement audit trails for system components"),
        ("Req-10.5", "Audit Security", "Secure audit trails against alteration"),
    ],
    Framework.HIPAA: [
        ("164.312(a)", "Access Control", "Unique user identification and access controls"),
        ("164.312(c)", "Integrity", "Mechanisms to authenticate electronic PHI"),
        ("164.312(d)", "Authentication", "Person or entity authentication"),
        ("164.312(e)", "Transmission", "Encryption of PHI in transit"),
        ("164.308(a)(5)", "Security Training", "Security awareness and training"),
    ],
    Framework.GDPR: [
        ("Art.25", "Privacy by Design", "Data protection by design and by default"),
        ("Art.30", "Records", "Records of processing activities"),
        ("Art.32", "Security", "Security of processing"),
        ("Art.33", "Breach Notification", "Notification of data breach to authority"),
        ("Art.35", "DPIA", "Data protection impact assessment"),
    ],
    Framework.NIST_CSF: [
        ("ID.AM-1", "Asset Management", "Physical devices and systems inventoried"),
        ("PR.AC-1", "Access Control", "Identities and credentials managed"),
        ("PR.DS-2", "Data Protection", "Data-in-transit is protected"),
        ("DE.CM-1", "Monitoring", "Network monitoring for cybersecurity events"),
        ("RC.RP-1", "Recovery", "Recovery plan executed during/after an event"),
    ],
    Framework.FEDRAMP: [
        ("AC-2", "Account Management", "Information system account management"),
        ("AU-2", "Audit Events", "Auditable events defined and reviewed"),
        ("SC-7", "Boundary Protection", "System boundary protection mechanisms"),
        ("SC-28", "Data at Rest", "Protection of information at rest"),
        ("CP-10", "System Recovery", "System recovery and reconstitution"),
    ],
    Framework.DORA: [
        ("Art.5", "ICT Risk Mgmt", "ICT risk management framework"),
        ("Art.9", "Protection", "Protection and prevention measures"),
        ("Art.10", "Detection", "Detection of anomalous activities"),
        ("Art.11", "Response", "Response and recovery plans"),
        ("Art.25", "Third Party", "ICT third-party risk management"),
    ],
    Framework.CIS_BENCHMARK: [
        ("CIS-1.1", "Inventory", "Inventory of authorized and unauthorized devices"),
        ("CIS-4.1", "Admin Privileges", "Controlled use of administrative privileges"),
        ("CIS-6.1", "Audit Logs", "Maintenance and monitoring of audit logs"),
        ("CIS-10.1", "Data Recovery", "Data recovery capabilities"),
        ("CIS-14.1", "Access Control", "Controlled access based on need to know"),
    ],
}

# Mapping of check functions to their control assessment keys
_CHECK_KEYS = [
    "has_auth",
    "has_encryption",
    "has_monitoring",
    "has_redundancy",
    "has_failover",
    "has_dr",
    "has_autoscaling",
    "has_network_segmentation",
    "has_encryption_at_rest",
    "has_backup",
    "has_logging",
    "has_circuit_breakers",
]


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class CompliancePostureEngine:
    """Assesses infrastructure compliance posture against multiple frameworks.

    Analyzes an :class:`InfraGraph` to determine compliance status for
    individual controls within each supported framework, calculates
    posture scores, identifies gaps, and produces remediation priorities.
    """

    # ------------------------------------------------------------------ checks

    @staticmethod
    def _has_auth(graph: InfraGraph) -> bool:
        """Check for authentication / WAF / access control components."""
        keywords = {"auth", "waf", "firewall", "gateway", "oauth", "iam", "keycloak"}
        for comp in graph.components.values():
            name_lower = (comp.id + " " + comp.name).lower()
            if any(kw in name_lower for kw in keywords):
                return True
            if comp.security.auth_required:
                return True
        return False

    @staticmethod
    def _has_encryption(graph: InfraGraph) -> bool:
        """Check for TLS / encryption in transit."""
        for comp in graph.components.values():
            if comp.port == 443:
                return True
            if comp.security.encryption_in_transit:
                return True
        return False

    @staticmethod
    def _has_monitoring(graph: InfraGraph) -> bool:
        """Check for monitoring / observability components."""
        keywords = {"otel", "monitoring", "prometheus", "grafana", "datadog", "newrelic"}
        for comp in graph.components.values():
            name_lower = (comp.id + " " + comp.name).lower()
            if any(kw in name_lower for kw in keywords):
                return True
            if comp.security.log_enabled and comp.security.ids_monitored:
                return True
        return False

    @staticmethod
    def _has_redundancy(graph: InfraGraph) -> bool:
        """Check if critical components have replicas >= 2."""
        for comp in graph.components.values():
            if comp.replicas >= 2:
                return True
        return False

    @staticmethod
    def _has_failover(graph: InfraGraph) -> bool:
        """Check if any database/cache has failover enabled."""
        for comp in graph.components.values():
            if comp.type in (ComponentType.DATABASE, ComponentType.CACHE):
                if comp.failover.enabled:
                    return True
        return False

    @staticmethod
    def _has_dr(graph: InfraGraph) -> bool:
        """Check for DR region configuration."""
        for comp in graph.components.values():
            if comp.region.dr_target_region:
                return True
            if not comp.region.is_primary:
                return True
        return False

    @staticmethod
    def _has_autoscaling(graph: InfraGraph) -> bool:
        """Check if any component has autoscaling enabled."""
        for comp in graph.components.values():
            if comp.autoscaling.enabled:
                return True
        return False

    @staticmethod
    def _has_network_segmentation(graph: InfraGraph) -> bool:
        """Check if components use network segmentation."""
        for comp in graph.components.values():
            if comp.security.network_segmented:
                return True
        return False

    @staticmethod
    def _has_encryption_at_rest(graph: InfraGraph) -> bool:
        """Check if components have encryption at rest."""
        for comp in graph.components.values():
            if comp.security.encryption_at_rest:
                return True
        return False

    @staticmethod
    def _has_backup(graph: InfraGraph) -> bool:
        """Check if backup is enabled on any component."""
        for comp in graph.components.values():
            if comp.security.backup_enabled:
                return True
        return False

    @staticmethod
    def _has_logging(graph: InfraGraph) -> bool:
        """Check if logging is enabled on any component."""
        for comp in graph.components.values():
            if comp.security.log_enabled:
                return True
            if comp.compliance_tags.audit_logging:
                return True
        return False

    @staticmethod
    def _has_circuit_breakers(graph: InfraGraph) -> bool:
        """Check if any dependency edge has circuit breakers."""
        for edge in graph.all_dependency_edges():
            if edge.circuit_breaker.enabled:
                return True
        return False

    @staticmethod
    def _components_without_redundancy(graph: InfraGraph) -> list[str]:
        """Return IDs of components with replicas < 2 that have dependents."""
        result = []
        for comp in graph.components.values():
            dependents = graph.get_dependents(comp.id)
            if comp.replicas < 2 and len(dependents) > 0:
                result.append(comp.id)
        return result

    @staticmethod
    def _non_encrypted_components(graph: InfraGraph) -> list[str]:
        """Return IDs of components on port 80 or without encryption in transit."""
        return [
            comp.id
            for comp in graph.components.values()
            if comp.port == 80 or (
                comp.port != 443
                and not comp.security.encryption_in_transit
                and comp.type in (
                    ComponentType.WEB_SERVER,
                    ComponentType.APP_SERVER,
                    ComponentType.LOAD_BALANCER,
                )
            )
        ]

    @staticmethod
    def _pii_components(graph: InfraGraph) -> list[str]:
        """Return IDs of components containing PII data."""
        return [
            comp.id
            for comp in graph.components.values()
            if comp.compliance_tags.contains_pii
        ]

    @staticmethod
    def _phi_components(graph: InfraGraph) -> list[str]:
        """Return IDs of components containing PHI data."""
        return [
            comp.id
            for comp in graph.components.values()
            if comp.compliance_tags.contains_phi
        ]

    # ------------------------------------------------------------------ gather

    def _gather_checks(self, graph: InfraGraph) -> dict[str, bool]:
        """Gather all boolean check results for the graph."""
        return {
            "has_auth": self._has_auth(graph),
            "has_encryption": self._has_encryption(graph),
            "has_monitoring": self._has_monitoring(graph),
            "has_redundancy": self._has_redundancy(graph),
            "has_failover": self._has_failover(graph),
            "has_dr": self._has_dr(graph),
            "has_autoscaling": self._has_autoscaling(graph),
            "has_network_segmentation": self._has_network_segmentation(graph),
            "has_encryption_at_rest": self._has_encryption_at_rest(graph),
            "has_backup": self._has_backup(graph),
            "has_logging": self._has_logging(graph),
            "has_circuit_breakers": self._has_circuit_breakers(graph),
        }

    # ------------------------------------------------------------------ assess

    def _assess_control(
        self,
        framework: Framework,
        control_id: str,
        title: str,
        description: str,
        checks: dict[str, bool],
        graph: InfraGraph,
    ) -> Control:
        """Assess a single control based on gathered checks and framework rules."""
        evidence: list[str] = []
        gaps: list[str] = []
        remediation = ""

        # Determine which checks matter for each control based on framework + id
        status = self._evaluate_control(
            framework, control_id, checks, graph, evidence, gaps,
        )

        if status == ControlStatus.NON_COMPLIANT:
            remediation = f"Address gaps for {control_id}: " + "; ".join(gaps) if gaps else f"Implement controls for {control_id}"
        elif status == ControlStatus.PARTIALLY_COMPLIANT:
            remediation = f"Complete implementation for {control_id}: " + "; ".join(gaps) if gaps else f"Improve controls for {control_id}"

        return Control(
            framework=framework,
            control_id=control_id,
            title=title,
            description=description,
            status=status,
            evidence=evidence,
            gaps=gaps,
            remediation=remediation,
        )

    def _evaluate_control(
        self,
        framework: Framework,
        control_id: str,
        checks: dict[str, bool],
        graph: InfraGraph,
        evidence: list[str],
        gaps: list[str],
    ) -> ControlStatus:
        """Evaluate a specific control and populate evidence/gaps lists."""
        # Map control_id to check requirements
        requirements = self._get_control_requirements(framework, control_id)
        if not requirements:
            evidence.append("No specific infrastructure requirements mapped")
            return ControlStatus.NOT_APPLICABLE

        met_count = 0
        total = len(requirements)
        for req_key, req_label in requirements:
            val = checks.get(req_key, False)
            if val:
                evidence.append(f"{req_label}: satisfied")
                met_count += 1
            else:
                gaps.append(f"{req_label}: not satisfied")

        if met_count == total:
            return ControlStatus.COMPLIANT
        elif met_count > 0:
            return ControlStatus.PARTIALLY_COMPLIANT
        else:
            return ControlStatus.NON_COMPLIANT

    @staticmethod
    def _get_control_requirements(
        framework: Framework,
        control_id: str,
    ) -> list[tuple[str, str]]:
        """Return (check_key, human_label) pairs for a given control."""
        # Universal mapping: framework + control_id -> list of required checks
        _map: dict[tuple[Framework, str], list[tuple[str, str]]] = {
            # SOC2
            (Framework.SOC2, "CC6.1"): [
                ("has_auth", "Access control"),
                ("has_network_segmentation", "Network segmentation"),
            ],
            (Framework.SOC2, "CC6.6"): [
                ("has_encryption", "Encryption in transit"),
            ],
            (Framework.SOC2, "CC7.2"): [
                ("has_monitoring", "Monitoring"),
                ("has_logging", "Logging"),
            ],
            (Framework.SOC2, "CC8.1"): [
                ("has_monitoring", "Change monitoring"),
                ("has_circuit_breakers", "Circuit breakers"),
            ],
            (Framework.SOC2, "A1.2"): [
                ("has_redundancy", "Redundancy"),
                ("has_failover", "Failover"),
            ],
            # ISO27001
            (Framework.ISO27001, "A.9.1.1"): [
                ("has_auth", "Access control"),
            ],
            (Framework.ISO27001, "A.10.1.1"): [
                ("has_encryption", "Encryption in transit"),
                ("has_encryption_at_rest", "Encryption at rest"),
            ],
            (Framework.ISO27001, "A.12.4.1"): [
                ("has_logging", "Logging"),
                ("has_monitoring", "Monitoring"),
            ],
            (Framework.ISO27001, "A.17.1.1"): [
                ("has_dr", "Disaster recovery"),
                ("has_failover", "Failover"),
            ],
            (Framework.ISO27001, "A.17.1.2"): [
                ("has_redundancy", "Redundancy"),
                ("has_autoscaling", "Autoscaling"),
            ],
            # PCI_DSS
            (Framework.PCI_DSS, "Req-1.3"): [
                ("has_network_segmentation", "Network segmentation"),
                ("has_auth", "Access control"),
            ],
            (Framework.PCI_DSS, "Req-3.4"): [
                ("has_encryption_at_rest", "Encryption at rest"),
            ],
            (Framework.PCI_DSS, "Req-6.1"): [
                ("has_monitoring", "Vulnerability monitoring"),
                ("has_circuit_breakers", "Error handling"),
            ],
            (Framework.PCI_DSS, "Req-10.1"): [
                ("has_logging", "Audit logging"),
                ("has_monitoring", "Monitoring"),
            ],
            (Framework.PCI_DSS, "Req-10.5"): [
                ("has_encryption", "Encryption in transit"),
                ("has_encryption_at_rest", "Encryption at rest"),
            ],
            # HIPAA
            (Framework.HIPAA, "164.312(a)"): [
                ("has_auth", "Access control"),
                ("has_network_segmentation", "Network segmentation"),
            ],
            (Framework.HIPAA, "164.312(c)"): [
                ("has_encryption_at_rest", "Integrity protection"),
                ("has_backup", "Backup"),
            ],
            (Framework.HIPAA, "164.312(d)"): [
                ("has_auth", "Authentication"),
            ],
            (Framework.HIPAA, "164.312(e)"): [
                ("has_encryption", "Encryption in transit"),
            ],
            (Framework.HIPAA, "164.308(a)(5)"): [
                ("has_monitoring", "Security monitoring"),
                ("has_logging", "Audit logging"),
            ],
            # GDPR
            (Framework.GDPR, "Art.25"): [
                ("has_encryption", "Privacy by design (encryption)"),
                ("has_network_segmentation", "Data isolation"),
            ],
            (Framework.GDPR, "Art.30"): [
                ("has_logging", "Processing records"),
                ("has_monitoring", "Activity monitoring"),
            ],
            (Framework.GDPR, "Art.32"): [
                ("has_encryption", "Encryption"),
                ("has_auth", "Access control"),
                ("has_backup", "Backup / resilience"),
            ],
            (Framework.GDPR, "Art.33"): [
                ("has_monitoring", "Breach detection"),
                ("has_logging", "Incident logging"),
            ],
            (Framework.GDPR, "Art.35"): [
                ("has_monitoring", "Impact monitoring"),
            ],
            # NIST_CSF
            (Framework.NIST_CSF, "ID.AM-1"): [
                ("has_monitoring", "Asset discovery"),
            ],
            (Framework.NIST_CSF, "PR.AC-1"): [
                ("has_auth", "Access control"),
            ],
            (Framework.NIST_CSF, "PR.DS-2"): [
                ("has_encryption", "Data-in-transit protection"),
            ],
            (Framework.NIST_CSF, "DE.CM-1"): [
                ("has_monitoring", "Network monitoring"),
                ("has_logging", "Event logging"),
            ],
            (Framework.NIST_CSF, "RC.RP-1"): [
                ("has_failover", "Failover"),
                ("has_dr", "Disaster recovery"),
                ("has_backup", "Backup"),
            ],
            # FedRAMP
            (Framework.FEDRAMP, "AC-2"): [
                ("has_auth", "Account management"),
                ("has_logging", "Account activity logging"),
            ],
            (Framework.FEDRAMP, "AU-2"): [
                ("has_logging", "Audit logging"),
                ("has_monitoring", "Audit monitoring"),
            ],
            (Framework.FEDRAMP, "SC-7"): [
                ("has_network_segmentation", "Boundary protection"),
                ("has_auth", "Access enforcement"),
            ],
            (Framework.FEDRAMP, "SC-28"): [
                ("has_encryption_at_rest", "Data-at-rest protection"),
            ],
            (Framework.FEDRAMP, "CP-10"): [
                ("has_dr", "Disaster recovery"),
                ("has_backup", "Backup"),
                ("has_failover", "Failover"),
            ],
            # DORA
            (Framework.DORA, "Art.5"): [
                ("has_monitoring", "ICT risk monitoring"),
                ("has_circuit_breakers", "Risk mitigation"),
            ],
            (Framework.DORA, "Art.9"): [
                ("has_encryption", "Protection measures"),
                ("has_auth", "Prevention measures"),
            ],
            (Framework.DORA, "Art.10"): [
                ("has_monitoring", "Anomaly detection"),
                ("has_logging", "Event logging"),
            ],
            (Framework.DORA, "Art.11"): [
                ("has_failover", "Recovery mechanisms"),
                ("has_dr", "Response plans"),
                ("has_backup", "Data restoration"),
            ],
            (Framework.DORA, "Art.25"): [
                ("has_monitoring", "Third-party monitoring"),
                ("has_circuit_breakers", "Third-party risk controls"),
            ],
            # CIS Benchmark
            (Framework.CIS_BENCHMARK, "CIS-1.1"): [
                ("has_monitoring", "Device inventory"),
            ],
            (Framework.CIS_BENCHMARK, "CIS-4.1"): [
                ("has_auth", "Admin privilege control"),
                ("has_network_segmentation", "Privilege segmentation"),
            ],
            (Framework.CIS_BENCHMARK, "CIS-6.1"): [
                ("has_logging", "Audit log maintenance"),
                ("has_monitoring", "Log monitoring"),
            ],
            (Framework.CIS_BENCHMARK, "CIS-10.1"): [
                ("has_backup", "Data recovery"),
                ("has_dr", "Recovery planning"),
            ],
            (Framework.CIS_BENCHMARK, "CIS-14.1"): [
                ("has_auth", "Access control"),
                ("has_encryption_at_rest", "Data protection"),
            ],
        }
        return _map.get((framework, control_id), [])

    # ------------------------------------------------------------------ public

    def assess_posture(self, graph: InfraGraph, framework: Framework) -> PostureReport:
        """Assess compliance posture for a single framework.

        Evaluates all controls defined for *framework* against the topology
        in *graph* and returns a :class:`PostureReport` with scores, gaps,
        and remediation priorities.
        """
        checks = self._gather_checks(graph)
        control_defs = _FRAMEWORK_CONTROLS.get(framework, [])

        controls: list[Control] = []
        for cid, title, desc in control_defs:
            ctrl = self._assess_control(framework, cid, title, desc, checks, graph)
            controls.append(ctrl)

        compliant = sum(1 for c in controls if c.status == ControlStatus.COMPLIANT)
        non_compliant = sum(1 for c in controls if c.status == ControlStatus.NON_COMPLIANT)
        partially = sum(1 for c in controls if c.status == ControlStatus.PARTIALLY_COMPLIANT)
        na = sum(1 for c in controls if c.status == ControlStatus.NOT_APPLICABLE)

        # Score: compliant = 100%, partial = 50%, non_compliant = 0%, N/A excluded
        scoreable = len(controls) - na
        if scoreable > 0:
            score = ((compliant * 100.0) + (partially * 50.0)) / scoreable
        else:
            score = 100.0

        critical_gaps: list[str] = []
        remediation_priority: list[str] = []
        total_hours = 0.0

        for c in controls:
            hours = _REMEDIATION_HOURS.get(c.status, 0.0)
            total_hours += hours
            if c.status == ControlStatus.NON_COMPLIANT:
                critical_gaps.append(f"{c.control_id}: {c.title}")
                remediation_priority.insert(0, c.control_id)
            elif c.status == ControlStatus.PARTIALLY_COMPLIANT:
                remediation_priority.append(c.control_id)

        recommendations = self._build_recommendations(controls, checks)

        return PostureReport(
            framework=framework,
            overall_score=round(score, 1),
            controls=controls,
            compliant_count=compliant,
            non_compliant_count=non_compliant,
            critical_gaps=critical_gaps,
            remediation_priority=remediation_priority,
            estimated_remediation_hours=total_hours,
            recommendations=recommendations,
        )

    def assess_all_frameworks(self, graph: InfraGraph) -> list[PostureReport]:
        """Assess compliance posture for all supported frameworks."""
        return [self.assess_posture(graph, fw) for fw in Framework]

    def find_cross_framework_gaps(self, graph: InfraGraph) -> list[CrossFrameworkGap]:
        """Find gaps that affect multiple frameworks.

        Groups missing checks across frameworks and returns cross-cutting
        gaps with severity ratings and shared remediation recommendations.
        """
        reports = self.assess_all_frameworks(graph)
        # Build a map: gap_description -> (frameworks, control_ids)
        gap_map: dict[str, tuple[list[Framework], list[str]]] = {}
        for report in reports:
            for ctrl in report.controls:
                for gap in ctrl.gaps:
                    if gap not in gap_map:
                        gap_map[gap] = ([], [])
                    if report.framework not in gap_map[gap][0]:
                        gap_map[gap][0].append(report.framework)
                    gap_map[gap][1].append(ctrl.control_id)

        # Only return gaps that affect 2+ frameworks
        cross_gaps: list[CrossFrameworkGap] = []
        for desc, (frameworks, control_ids) in gap_map.items():
            if len(frameworks) < 2:
                continue
            severity = "critical" if len(frameworks) >= 5 else (
                "high" if len(frameworks) >= 3 else "medium"
            )
            cross_gaps.append(CrossFrameworkGap(
                gap_description=desc,
                affected_frameworks=frameworks,
                affected_control_ids=list(set(control_ids)),
                severity=severity,
                shared_remediation=f"Implement: {desc.split(':')[0].strip()}",
            ))

        # Sort by severity (critical first)
        cross_gaps.sort(
            key=lambda g: _SEVERITY_WEIGHTS.get(g.severity, 0), reverse=True,
        )
        return cross_gaps

    def estimate_compliance_cost(
        self, graph: InfraGraph, framework: Framework,
    ) -> ComplianceCostEstimate:
        """Estimate the cost to achieve full compliance for a framework."""
        report = self.assess_posture(graph, framework)
        controls_needing_work = report.non_compliant_count + sum(
            1 for c in report.controls
            if c.status == ControlStatus.PARTIALLY_COMPLIANT
        )

        hourly_rate = 150.0
        total_hours = report.estimated_remediation_hours
        total_cost = total_hours * hourly_rate

        # Category breakdown
        cost_by_category: dict[str, float] = {}
        for ctrl in report.controls:
            h = _REMEDIATION_HOURS.get(ctrl.status, 0.0)
            if h > 0:
                cat = ctrl.title
                cost_by_category[cat] = cost_by_category.get(cat, 0.0) + h * hourly_rate

        # Estimate timeline: assume 40h/week with 2 engineers
        weeks = max(1, int(total_hours / 80) + (1 if total_hours % 80 > 0 else 0)) if total_hours > 0 else 0

        return ComplianceCostEstimate(
            framework=framework,
            total_estimated_hours=total_hours,
            total_estimated_cost_usd=total_cost,
            cost_by_category=cost_by_category,
            hourly_rate_usd=hourly_rate,
            controls_needing_work=controls_needing_work,
            timeline_weeks=weeks,
        )

    def generate_audit_evidence(
        self, graph: InfraGraph, framework: Framework,
    ) -> AuditPackage:
        """Generate an audit evidence package for a framework assessment."""
        report = self.assess_posture(graph, framework)
        items: list[AuditEvidence] = []
        missing: list[str] = []

        for ctrl in report.controls:
            component_ids = [c.id for c in graph.components.values()]
            if ctrl.status == ControlStatus.COMPLIANT:
                items.append(AuditEvidence(
                    control_id=ctrl.control_id,
                    evidence_type="configuration",
                    description=f"Control {ctrl.control_id} is compliant: " + "; ".join(ctrl.evidence),
                    component_ids=component_ids,
                    status="collected",
                ))
            elif ctrl.status == ControlStatus.PARTIALLY_COMPLIANT:
                items.append(AuditEvidence(
                    control_id=ctrl.control_id,
                    evidence_type="configuration",
                    description=f"Control {ctrl.control_id} is partially compliant: " + "; ".join(ctrl.evidence),
                    component_ids=component_ids,
                    status="collected",
                ))
                missing.append(f"{ctrl.control_id}: partial compliance gaps - " + "; ".join(ctrl.gaps))
            elif ctrl.status == ControlStatus.NON_COMPLIANT:
                items.append(AuditEvidence(
                    control_id=ctrl.control_id,
                    evidence_type="documentation",
                    description=f"Control {ctrl.control_id} is non-compliant",
                    component_ids=component_ids,
                    status="missing",
                ))
                missing.append(f"{ctrl.control_id}: non-compliant - " + "; ".join(ctrl.gaps))
            elif ctrl.status == ControlStatus.NOT_APPLICABLE:
                items.append(AuditEvidence(
                    control_id=ctrl.control_id,
                    evidence_type="documentation",
                    description=f"Control {ctrl.control_id}: not applicable",
                    component_ids=component_ids,
                    status="collected",
                ))

        # Coverage = items with status=="collected" / total
        collected = sum(1 for i in items if i.status == "collected")
        coverage = (collected / len(items) * 100.0) if items else 0.0

        summary = (
            f"Framework {framework.value}: {len(items)} controls assessed, "
            f"{collected} evidence items collected ({coverage:.1f}% coverage), "
            f"{len(missing)} gaps identified"
        )

        return AuditPackage(
            framework=framework,
            evidence_items=items,
            coverage_percent=round(coverage, 1),
            missing_evidence=missing,
            summary=summary,
        )

    def track_posture_trend(self, reports: list[PostureReport]) -> PostureTrend:
        """Track posture trend across multiple posture report snapshots.

        Accepts a chronologically ordered list of :class:`PostureReport` and
        returns a :class:`PostureTrend` with direction analysis.
        """
        if not reports:
            return PostureTrend(direction="stable", average_score=0.0, score_delta=0.0)

        points = [
            PostureTrendPoint(
                framework=r.framework,
                score=r.overall_score,
                compliant_count=r.compliant_count,
                non_compliant_count=r.non_compliant_count,
            )
            for r in reports
        ]

        scores = [r.overall_score for r in reports]
        avg = sum(scores) / len(scores)
        delta = scores[-1] - scores[0] if len(scores) > 1 else 0.0

        if delta > 5.0:
            direction = "improving"
        elif delta < -5.0:
            direction = "degrading"
        else:
            direction = "stable"

        recommendations: list[str] = []
        if direction == "degrading":
            recommendations.append("Compliance posture is degrading. Review recent infrastructure changes.")
        if avg < 50.0:
            recommendations.append("Overall posture is below 50%. Prioritize critical gap remediation.")
        if reports[-1].non_compliant_count > 0:
            recommendations.append(
                f"{reports[-1].non_compliant_count} controls are non-compliant. "
                "Address critical gaps immediately."
            )

        return PostureTrend(
            data_points=points,
            direction=direction,
            average_score=round(avg, 1),
            score_delta=round(delta, 1),
            recommendations=recommendations,
        )

    def prioritize_remediation(
        self, reports: list[PostureReport],
    ) -> list[RemediationPriority]:
        """Prioritize remediation actions across all reports.

        Returns a ranked list of :class:`RemediationPriority` items sorted
        by impact (non-compliant first, then partially compliant), with
        controls appearing in more reports ranked higher.
        """
        # Collect all non-compliant and partially-compliant controls
        items: dict[str, RemediationPriority] = {}
        for report in reports:
            for ctrl in report.controls:
                if ctrl.status in (ControlStatus.COMPLIANT, ControlStatus.NOT_APPLICABLE):
                    continue

                key = f"{ctrl.framework.value}:{ctrl.control_id}"
                hours = _REMEDIATION_HOURS.get(ctrl.status, 0.0)

                if ctrl.status == ControlStatus.NON_COMPLIANT:
                    priority = "critical"
                    impact = 4.0
                elif ctrl.status == ControlStatus.PARTIALLY_COMPLIANT:
                    priority = "high"
                    impact = 2.0
                else:
                    priority = "medium"
                    impact = 1.0

                if key not in items:
                    items[key] = RemediationPriority(
                        control_id=ctrl.control_id,
                        framework=ctrl.framework,
                        gap_description="; ".join(ctrl.gaps) if ctrl.gaps else ctrl.title,
                        impact_score=impact,
                        effort_hours=hours,
                        priority=priority,
                    )
                else:
                    # Increase impact when same gap appears multiple times
                    items[key].impact_score += impact

        # Sort: highest impact first, then lowest effort
        sorted_items = sorted(
            items.values(),
            key=lambda x: (-x.impact_score, x.effort_hours),
        )

        # Assign ranks
        for i, item in enumerate(sorted_items):
            item.rank = i + 1

        return sorted_items

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _build_recommendations(
        controls: list[Control],
        checks: dict[str, bool],
    ) -> list[str]:
        """Build actionable recommendations from control assessments."""
        recs: list[str] = []
        if not checks.get("has_auth"):
            recs.append("Implement authentication and access control mechanisms.")
        if not checks.get("has_encryption"):
            recs.append("Enforce TLS encryption on all external-facing components.")
        if not checks.get("has_monitoring"):
            recs.append("Deploy monitoring and observability tools (e.g., Prometheus, Datadog).")
        if not checks.get("has_redundancy"):
            recs.append("Add replicas >= 2 for critical components to ensure availability.")
        if not checks.get("has_failover"):
            recs.append("Enable failover on databases and caches for continuity.")
        if not checks.get("has_encryption_at_rest"):
            recs.append("Enable encryption at rest for sensitive data stores.")
        if not checks.get("has_backup"):
            recs.append("Enable backup on components storing critical data.")
        if not checks.get("has_logging"):
            recs.append("Enable audit logging on all components for compliance.")
        if not checks.get("has_network_segmentation"):
            recs.append("Implement network segmentation to limit blast radius.")
        if not checks.get("has_circuit_breakers"):
            recs.append("Enable circuit breakers on dependency edges to prevent cascade failures.")
        if not checks.get("has_dr"):
            recs.append("Configure disaster recovery regions for business continuity.")
        # If everything passes, give a positive recommendation
        if all(checks.values()):
            recs.append("All baseline controls are satisfied. Consider continuous monitoring.")
        return recs
