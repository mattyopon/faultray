# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Continuous Compliance Monitor.

Unlike point-in-time compliance checks, this monitors compliance posture
continuously and tracks changes. Detects when infrastructure changes
cause compliance violations, and alerts before audit gaps develop.

Supported frameworks: DORA, SOC2, ISO 27001, PCI DSS, NIST CSF, HIPAA
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from faultray.model.components import ComponentType
from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ComplianceFramework(str, Enum):
    """Supported regulatory compliance frameworks."""

    DORA = "dora"
    SOC2 = "soc2"
    ISO27001 = "iso27001"
    PCI_DSS = "pci_dss"
    NIST_CSF = "nist_csf"
    HIPAA = "hipaa"


class ControlStatus(str, Enum):
    """Status of an individual compliance control."""

    COMPLIANT = "compliant"
    PARTIAL = "partial"
    NON_COMPLIANT = "non_compliant"
    NOT_APPLICABLE = "not_applicable"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ComplianceControl:
    """Result of assessing a single compliance control."""

    control_id: str  # e.g. "DORA-5.1", "SOC2-CC6.1"
    framework: ComplianceFramework
    title: str
    description: str
    status: ControlStatus
    evidence: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    remediation: list[str] = field(default_factory=list)
    last_assessed: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    risk_if_non_compliant: str = ""


@dataclass
class ComplianceSnapshot:
    """Point-in-time compliance snapshot for a single framework."""

    timestamp: datetime
    framework: ComplianceFramework
    total_controls: int
    compliant: int
    partial: int
    non_compliant: int
    compliance_percentage: float
    controls: list[ComplianceControl] = field(default_factory=list)


@dataclass
class ComplianceTrend:
    """Trend analysis across multiple snapshots for a framework."""

    framework: ComplianceFramework
    snapshots: list[ComplianceSnapshot] = field(default_factory=list)
    trend: str = "stable"  # "improving", "stable", "degrading"
    current_percentage: float = 0.0
    delta_30d: float = 0.0
    risk_areas: list[str] = field(default_factory=list)


@dataclass
class ComplianceAlert:
    """Alert generated when compliance posture changes."""

    alert_type: str  # "new_violation", "degradation", "upcoming_audit", "regulation_change"
    framework: ComplianceFramework
    control_id: str
    severity: str  # "critical", "high", "medium", "low"
    message: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Control definitions per framework
# ---------------------------------------------------------------------------

def _build_dora_controls() -> list[dict]:
    """Return DORA control definitions with assessment functions."""
    return [
        {
            "control_id": "DORA-5.1",
            "title": "ICT risk management framework documented",
            "description": "Financial entities shall have an ICT risk management framework that is documented and reviewed at least annually.",
            "risk": "Regulatory penalty and inability to demonstrate risk governance",
            "check": "_check_asset_inventory",
        },
        {
            "control_id": "DORA-5.2",
            "title": "ICT asset inventory maintained",
            "description": "Maintain a complete and up-to-date inventory of all ICT assets.",
            "risk": "Unknown assets create blind spots in risk management",
            "check": "_check_asset_inventory",
        },
        {
            "control_id": "DORA-5.3",
            "title": "Business continuity procedures",
            "description": "Establish and implement business continuity and disaster recovery procedures.",
            "risk": "Extended outage during disruptions with no recovery plan",
            "check": "_check_business_continuity",
        },
        {
            "control_id": "DORA-5.4",
            "title": "Recovery procedures validated",
            "description": "Recovery procedures shall be tested and validated regularly.",
            "risk": "Recovery procedures may not work when actually needed",
            "check": "_check_failover_capability",
        },
        {
            "control_id": "DORA-6.1",
            "title": "Component health monitoring",
            "description": "Continuous monitoring of ICT system health and performance.",
            "risk": "Failures go undetected leading to cascading outages",
            "check": "_check_monitoring",
        },
        {
            "control_id": "DORA-8.1",
            "title": "Incident detection capabilities",
            "description": "ICT-related incident detection mechanisms shall be in place.",
            "risk": "Delayed incident response increases blast radius",
            "check": "_check_incident_detection",
        },
        {
            "control_id": "DORA-8.2",
            "title": "Incident classification procedures",
            "description": "Procedures for classifying and prioritizing ICT-related incidents.",
            "risk": "Misclassification leads to improper response and escalation",
            "check": "_check_monitoring",
        },
        {
            "control_id": "DORA-11.1",
            "title": "ICT concentration risk assessment",
            "description": "Assess concentration risk from dependency on single providers or components.",
            "risk": "Single point of failure takes down entire service",
            "check": "_check_concentration_risk",
        },
        {
            "control_id": "DORA-11.2",
            "title": "Third-party risk management",
            "description": "Manage risks arising from third-party ICT service providers.",
            "risk": "Third-party outage or breach propagates to the organization",
            "check": "_check_third_party_risk",
        },
        {
            "control_id": "DORA-24.1",
            "title": "Regular resilience testing",
            "description": "Conduct regular resilience testing of ICT systems and tools.",
            "risk": "Unknown vulnerabilities remain undiscovered until production failure",
            "check": "_check_redundancy",
        },
        {
            "control_id": "DORA-24.2",
            "title": "Test coverage documentation",
            "description": "Document test coverage and results for ICT resilience testing.",
            "risk": "Audit findings for lack of documented testing evidence",
            "check": "_check_asset_inventory",
        },
        {
            "control_id": "DORA-25.1",
            "title": "Threat-led penetration testing",
            "description": "Threat-led penetration testing (TLPT) for critical functions.",
            "risk": "Advanced threats exploit undiscovered vulnerabilities",
            "check": "_check_security_controls",
        },
        {
            "control_id": "DORA-28.1",
            "title": "Third-party provider assessment",
            "description": "Assess ICT third-party service providers before contracting.",
            "risk": "Unreliable third parties introduce systemic risk",
            "check": "_check_third_party_risk",
        },
        {
            "control_id": "DORA-28.2",
            "title": "Exit strategy for critical providers",
            "description": "Define exit strategies for critical third-party ICT providers.",
            "risk": "Vendor lock-in without migration path",
            "check": "_check_third_party_exit",
        },
        {
            "control_id": "DORA-30.1",
            "title": "Information sharing arrangements",
            "description": "Participate in information sharing on cyber threats and vulnerabilities.",
            "risk": "Missed early warnings about emerging threats",
            "check": "_check_monitoring",
        },
    ]


def _build_soc2_controls() -> list[dict]:
    """Return SOC2 Trust Service Criteria control definitions."""
    return [
        {
            "control_id": "SOC2-CC6.1",
            "title": "Logical access controls",
            "description": "Logical access security software, infrastructure, and architectures are in place.",
            "risk": "Unauthorized access to systems and data",
            "check": "_check_access_controls",
        },
        {
            "control_id": "SOC2-CC6.2",
            "title": "Encryption at rest and in transit",
            "description": "Data is encrypted at rest and during transmission.",
            "risk": "Data exposure during storage or transmission",
            "check": "_check_encryption",
        },
        {
            "control_id": "SOC2-CC6.3",
            "title": "Network security",
            "description": "Network security controls protect against unauthorized access.",
            "risk": "Network-based attacks compromise infrastructure",
            "check": "_check_network_security",
        },
        {
            "control_id": "SOC2-CC7.1",
            "title": "System monitoring",
            "description": "System activity is monitored for anomalies indicative of threats.",
            "risk": "Threats go undetected until damage occurs",
            "check": "_check_monitoring",
        },
        {
            "control_id": "SOC2-CC7.2",
            "title": "Incident response",
            "description": "Procedures exist for responding to identified security incidents.",
            "risk": "Uncoordinated response worsens incident impact",
            "check": "_check_incident_detection",
        },
        {
            "control_id": "SOC2-CC8.1",
            "title": "Change management",
            "description": "Changes to infrastructure are managed through a change management process.",
            "risk": "Uncontrolled changes introduce instability or security holes",
            "check": "_check_change_management",
        },
        {
            "control_id": "SOC2-CC9.1",
            "title": "Risk mitigation",
            "description": "Risks are identified and mitigated through appropriate controls.",
            "risk": "Unmitigated risks lead to compliance failures and outages",
            "check": "_check_redundancy",
        },
        {
            "control_id": "SOC2-A1.1",
            "title": "Availability commitments",
            "description": "System availability meets defined commitments and SLAs.",
            "risk": "SLA breaches result in financial penalties and customer churn",
            "check": "_check_redundancy",
        },
        {
            "control_id": "SOC2-A1.2",
            "title": "Disaster recovery",
            "description": "Disaster recovery plans are in place and tested.",
            "risk": "Extended outage during disasters with no recovery path",
            "check": "_check_business_continuity",
        },
        {
            "control_id": "SOC2-A1.3",
            "title": "Backup procedures",
            "description": "Data backup procedures are established and followed.",
            "risk": "Data loss during system failures with no backup available",
            "check": "_check_backup_procedures",
        },
    ]


def _build_hipaa_controls() -> list[dict]:
    """Return HIPAA Security Rule control definitions."""
    return [
        {
            "control_id": "HIPAA-164.308(a)(1)",
            "title": "Security management process",
            "description": "Implement policies and procedures to prevent, detect, contain, and correct security violations.",
            "risk": "PHI breaches due to lack of security governance",
            "check": "_check_security_management",
        },
        {
            "control_id": "HIPAA-164.308(a)(5)",
            "title": "Security awareness and training",
            "description": "Implement security awareness and training program for workforce.",
            "risk": "Human error causes PHI exposure",
            "check": "_check_monitoring",
        },
        {
            "control_id": "HIPAA-164.310(a)(1)",
            "title": "Facility access controls",
            "description": "Implement policies and procedures to limit physical access to electronic information systems.",
            "risk": "Physical access leads to unauthorized data access",
            "check": "_check_network_security",
        },
        {
            "control_id": "HIPAA-164.312(a)(1)",
            "title": "Access control",
            "description": "Implement technical policies and procedures for access to ePHI.",
            "risk": "Unauthorized access to protected health information",
            "check": "_check_access_controls",
        },
        {
            "control_id": "HIPAA-164.312(b)",
            "title": "Audit controls",
            "description": "Implement hardware, software, and procedural mechanisms to record and examine activity.",
            "risk": "Inability to detect or investigate security incidents",
            "check": "_check_audit_controls",
        },
        {
            "control_id": "HIPAA-164.312(c)(1)",
            "title": "Data integrity",
            "description": "Implement policies and procedures to protect ePHI from improper alteration or destruction.",
            "risk": "Corrupted or altered health records lead to patient harm",
            "check": "_check_data_integrity",
        },
        {
            "control_id": "HIPAA-164.312(d)",
            "title": "Person or entity authentication",
            "description": "Implement procedures to verify identity of persons seeking access to ePHI.",
            "risk": "Impersonation attacks access patient data",
            "check": "_check_access_controls",
        },
        {
            "control_id": "HIPAA-164.312(e)(1)",
            "title": "Transmission security",
            "description": "Implement technical security measures to guard against unauthorized access to ePHI transmitted over electronic networks.",
            "risk": "ePHI intercepted during transmission",
            "check": "_check_encryption",
        },
    ]


# ---------------------------------------------------------------------------
# ComplianceMonitor
# ---------------------------------------------------------------------------


class ComplianceMonitor:
    """Continuous compliance monitoring engine.

    Tracks compliance posture over time and detects drift from compliant
    state. Supports DORA, SOC2, ISO 27001, PCI DSS, NIST CSF, and HIPAA.
    """

    def __init__(self, store_path: Path | None = None) -> None:
        self._store_path = store_path
        self._history: dict[ComplianceFramework, list[ComplianceSnapshot]] = {
            fw: [] for fw in ComplianceFramework
        }
        self._control_defs: dict[ComplianceFramework, list[dict]] = {
            ComplianceFramework.DORA: _build_dora_controls(),
            ComplianceFramework.SOC2: _build_soc2_controls(),
            ComplianceFramework.ISO27001: self._build_iso27001_controls(),
            ComplianceFramework.PCI_DSS: self._build_pci_dss_controls(),
            ComplianceFramework.NIST_CSF: self._build_nist_csf_controls(),
            ComplianceFramework.HIPAA: _build_hipaa_controls(),
        }
        # Initialise SQLite store and load existing history if store_path given
        if self._store_path is not None:
            self._init_store()
            self._load_history_from_store()

    # ------------------------------------------------------------------
    # Additional framework control builders
    # ------------------------------------------------------------------

    @staticmethod
    def _build_iso27001_controls() -> list[dict]:
        """ISO 27001 Annex A controls."""
        return [
            {
                "control_id": "ISO-A.5.1",
                "title": "Information security policies",
                "description": "A set of policies for information security shall be defined and approved.",
                "risk": "No governance framework for information security",
                "check": "_check_asset_inventory",
            },
            {
                "control_id": "ISO-A.9.1",
                "title": "Access control policy",
                "description": "An access control policy shall be established and reviewed.",
                "risk": "Unauthorized access to critical systems",
                "check": "_check_access_controls",
            },
            {
                "control_id": "ISO-A.10.1",
                "title": "Cryptographic controls",
                "description": "A policy on the use of cryptographic controls shall be developed.",
                "risk": "Data exposure due to lack of encryption",
                "check": "_check_encryption",
            },
            {
                "control_id": "ISO-A.12.4",
                "title": "Logging and monitoring",
                "description": "Events shall be recorded and evidence generated.",
                "risk": "Security events go undetected",
                "check": "_check_monitoring",
            },
            {
                "control_id": "ISO-A.12.6",
                "title": "Technical vulnerability management",
                "description": "Information about technical vulnerabilities shall be obtained and evaluated.",
                "risk": "Known vulnerabilities remain unpatched",
                "check": "_check_security_controls",
            },
            {
                "control_id": "ISO-A.14.1",
                "title": "Security in development and support",
                "description": "Rules for the development of software and systems shall include security.",
                "risk": "Insecure software development practices",
                "check": "_check_change_management",
            },
            {
                "control_id": "ISO-A.17.1",
                "title": "Information security continuity",
                "description": "Information security continuity shall be embedded in business continuity management.",
                "risk": "Loss of security controls during business disruptions",
                "check": "_check_business_continuity",
            },
            {
                "control_id": "ISO-A.17.2",
                "title": "Redundancy of information processing",
                "description": "Information processing facilities shall be implemented with sufficient redundancy.",
                "risk": "Single points of failure cause service outages",
                "check": "_check_redundancy",
            },
            {
                "control_id": "ISO-A.18.1",
                "title": "Compliance with legal requirements",
                "description": "All relevant statutory and regulatory requirements shall be identified.",
                "risk": "Legal and regulatory non-compliance penalties",
                "check": "_check_asset_inventory",
            },
            {
                "control_id": "ISO-A.18.2",
                "title": "Information security reviews",
                "description": "Regular independent reviews of the information security approach.",
                "risk": "Stale security posture drifts from requirements",
                "check": "_check_monitoring",
            },
        ]

    @staticmethod
    def _build_pci_dss_controls() -> list[dict]:
        """PCI DSS v4.0 controls."""
        return [
            {
                "control_id": "PCI-1.3",
                "title": "Network segmentation",
                "description": "Restrict inbound and outbound traffic to cardholder data environment.",
                "risk": "CDE exposed to unauthorized network segments",
                "check": "_check_network_security",
            },
            {
                "control_id": "PCI-3.4",
                "title": "Render PAN unreadable",
                "description": "PAN is rendered unreadable anywhere it is stored.",
                "risk": "Cardholder data exposed in cleartext",
                "check": "_check_encryption",
            },
            {
                "control_id": "PCI-6.1",
                "title": "Vulnerability identification",
                "description": "Establish a process to identify security vulnerabilities.",
                "risk": "Known vulnerabilities exploited by attackers",
                "check": "_check_security_controls",
            },
            {
                "control_id": "PCI-6.5",
                "title": "Secure coding practices",
                "description": "Address common coding vulnerabilities in software development.",
                "risk": "Application-level attacks through coding flaws",
                "check": "_check_incident_detection",
            },
            {
                "control_id": "PCI-8.1",
                "title": "User identification",
                "description": "Define and implement policies for user identification and authentication.",
                "risk": "Unauthorized access through shared or default credentials",
                "check": "_check_access_controls",
            },
            {
                "control_id": "PCI-10.1",
                "title": "Audit trails",
                "description": "Implement audit trails to link all access to individual users.",
                "risk": "Cannot attribute actions to individuals during investigation",
                "check": "_check_audit_controls",
            },
            {
                "control_id": "PCI-10.5",
                "title": "Secure audit trails",
                "description": "Secure audit trails so they cannot be altered.",
                "risk": "Evidence tampering covers attacker tracks",
                "check": "_check_data_integrity",
            },
            {
                "control_id": "PCI-10.6",
                "title": "Log review process",
                "description": "Review logs and security events for anomalies.",
                "risk": "Security events go unreviewed and unaddressed",
                "check": "_check_monitoring",
            },
            {
                "control_id": "PCI-11.3",
                "title": "Penetration testing",
                "description": "Perform internal and external penetration testing regularly.",
                "risk": "Exploitable vulnerabilities remain undiscovered",
                "check": "_check_security_controls",
            },
            {
                "control_id": "PCI-12.10",
                "title": "Incident response plan",
                "description": "Implement an incident response plan and be prepared to respond immediately.",
                "risk": "Delayed or chaotic incident response amplifies breach impact",
                "check": "_check_incident_detection",
            },
        ]

    @staticmethod
    def _build_nist_csf_controls() -> list[dict]:
        """NIST Cybersecurity Framework controls."""
        return [
            {
                "control_id": "NIST-ID.AM-1",
                "title": "Asset inventory",
                "description": "Physical devices and systems are inventoried.",
                "risk": "Unknown assets create security blind spots",
                "check": "_check_asset_inventory",
            },
            {
                "control_id": "NIST-ID.AM-2",
                "title": "Software inventory",
                "description": "Software platforms and applications are inventoried.",
                "risk": "Untracked software harbors vulnerabilities",
                "check": "_check_asset_inventory",
            },
            {
                "control_id": "NIST-PR.AC-1",
                "title": "Identity and access management",
                "description": "Identities and credentials are issued, managed, and revoked.",
                "risk": "Unmanaged credentials lead to unauthorized access",
                "check": "_check_access_controls",
            },
            {
                "control_id": "NIST-PR.DS-1",
                "title": "Data-at-rest protection",
                "description": "Data-at-rest is protected.",
                "risk": "Stored data exposed through theft or unauthorized access",
                "check": "_check_encryption",
            },
            {
                "control_id": "NIST-PR.DS-2",
                "title": "Data-in-transit protection",
                "description": "Data-in-transit is protected.",
                "risk": "Data intercepted during network transmission",
                "check": "_check_encryption",
            },
            {
                "control_id": "NIST-DE.CM-1",
                "title": "Network monitoring",
                "description": "The network is monitored to detect potential cybersecurity events.",
                "risk": "Network attacks go undetected",
                "check": "_check_monitoring",
            },
            {
                "control_id": "NIST-DE.AE-3",
                "title": "Event correlation",
                "description": "Event data are collected and correlated from multiple sources.",
                "risk": "Fragmented data prevents holistic threat detection",
                "check": "_check_audit_controls",
            },
            {
                "control_id": "NIST-RS.MI-1",
                "title": "Incident containment",
                "description": "Incidents are contained to minimize impact.",
                "risk": "Unconstrained incidents cascade across systems",
                "check": "_check_incident_detection",
            },
            {
                "control_id": "NIST-RC.RP-1",
                "title": "Recovery planning",
                "description": "Recovery plans are executed during or after a cybersecurity incident.",
                "risk": "No recovery path after security incident",
                "check": "_check_business_continuity",
            },
            {
                "control_id": "NIST-RC.IM-1",
                "title": "Recovery improvements",
                "description": "Recovery plans incorporate lessons learned.",
                "risk": "Repeated failures from same root cause",
                "check": "_check_failover_capability",
            },
        ]

    # ------------------------------------------------------------------
    # Infrastructure assessment checks
    # ------------------------------------------------------------------

    def _check_asset_inventory(self, graph: InfraGraph) -> tuple[ControlStatus, list[str], list[str]]:
        """Check if asset inventory is maintained (components exist in graph)."""
        total = len(graph.components)
        edges = len(graph.all_dependency_edges())
        evidence: list[str] = []
        gaps: list[str] = []

        if total > 0 and edges > 0:
            evidence.append(f"{total} components documented with {edges} dependency mappings")
            return ControlStatus.COMPLIANT, evidence, gaps
        elif total > 0:
            evidence.append(f"{total} components documented")
            gaps.append("Dependency mappings between components are missing")
            return ControlStatus.PARTIAL, evidence, gaps
        else:
            gaps.append("No infrastructure components documented")
            return ControlStatus.NON_COMPLIANT, evidence, gaps

    def _check_redundancy(self, graph: InfraGraph) -> tuple[ControlStatus, list[str], list[str]]:
        """Check if critical components have redundancy (replicas >= 2)."""
        evidence: list[str] = []
        gaps: list[str] = []
        total_critical = 0
        redundant = 0

        for comp in graph.components.values():
            dependents = graph.get_dependents(comp.id)
            if len(dependents) > 0:
                total_critical += 1
                if comp.replicas >= 2:
                    redundant += 1
                    evidence.append(f"{comp.name}: {comp.replicas} replicas")
                else:
                    gaps.append(f"{comp.name}: single instance (replicas=1) with {len(dependents)} dependents")

        if total_critical == 0:
            return ControlStatus.NOT_APPLICABLE, evidence, gaps
        ratio = redundant / total_critical
        if ratio >= 1.0:
            return ControlStatus.COMPLIANT, evidence, gaps
        elif ratio >= 0.5:
            return ControlStatus.PARTIAL, evidence, gaps
        else:
            return ControlStatus.NON_COMPLIANT, evidence, gaps

    def _check_monitoring(self, graph: InfraGraph) -> tuple[ControlStatus, list[str], list[str]]:
        """Check if monitoring capabilities exist."""
        evidence: list[str] = []
        gaps: list[str] = []
        monitoring_keywords = {"otel", "monitoring", "prometheus", "grafana", "datadog", "newrelic", "splunk"}

        has_monitoring = False
        for comp in graph.components.values():
            comp_lower = (comp.id + " " + comp.name).lower()
            if any(kw in comp_lower for kw in monitoring_keywords):
                has_monitoring = True
                evidence.append(f"Monitoring component found: {comp.name}")

        has_logging = any(comp.security.log_enabled for comp in graph.components.values())
        if has_logging:
            evidence.append("Log collection enabled on components")

        if has_monitoring and has_logging:
            return ControlStatus.COMPLIANT, evidence, gaps
        elif has_monitoring or has_logging:
            if not has_monitoring:
                gaps.append("No dedicated monitoring component (Prometheus, Datadog, etc.)")
            if not has_logging:
                gaps.append("Logging not enabled on components")
            return ControlStatus.PARTIAL, evidence, gaps
        else:
            gaps.append("No monitoring or logging infrastructure detected")
            return ControlStatus.NON_COMPLIANT, evidence, gaps

    def _check_incident_detection(self, graph: InfraGraph) -> tuple[ControlStatus, list[str], list[str]]:
        """Check if incident detection mechanisms exist (circuit breakers, monitoring)."""
        evidence: list[str] = []
        gaps: list[str] = []

        # Check circuit breaker coverage
        edges = graph.all_dependency_edges()
        cb_count = sum(1 for e in edges if e.circuit_breaker.enabled) if edges else 0
        total_edges = len(edges)

        if cb_count > 0:
            evidence.append(f"Circuit breakers enabled: {cb_count}/{total_edges} dependency edges")

        # Check monitoring
        mon_status, mon_evidence, mon_gaps = self._check_monitoring(graph)
        evidence.extend(mon_evidence)
        gaps.extend(mon_gaps)

        if cb_count > 0 and mon_status in (ControlStatus.COMPLIANT, ControlStatus.PARTIAL):
            return ControlStatus.COMPLIANT, evidence, gaps
        elif cb_count > 0 or mon_status != ControlStatus.NON_COMPLIANT:
            if cb_count == 0:
                gaps.append("No circuit breakers configured for failure containment")
            return ControlStatus.PARTIAL, evidence, gaps
        else:
            gaps.append("No incident detection mechanisms (circuit breakers, monitoring)")
            return ControlStatus.NON_COMPLIANT, evidence, gaps

    def _check_access_controls(self, graph: InfraGraph) -> tuple[ControlStatus, list[str], list[str]]:
        """Check if access controls are in place (auth, WAF components)."""
        evidence: list[str] = []
        gaps: list[str] = []
        auth_keywords = {"auth", "waf", "firewall", "gateway", "oauth", "iam", "keycloak"}

        has_auth_component = False
        for comp in graph.components.values():
            comp_lower = (comp.id + " " + comp.name).lower()
            if any(kw in comp_lower for kw in auth_keywords):
                has_auth_component = True
                evidence.append(f"Access control component: {comp.name}")

        has_auth_required = any(comp.security.auth_required for comp in graph.components.values())
        if has_auth_required:
            evidence.append("Authentication required flag enabled on components")

        if has_auth_component and has_auth_required:
            return ControlStatus.COMPLIANT, evidence, gaps
        elif has_auth_component or has_auth_required:
            if not has_auth_component:
                gaps.append("No dedicated auth/WAF component found")
            if not has_auth_required:
                gaps.append("auth_required not enabled on components")
            return ControlStatus.PARTIAL, evidence, gaps
        else:
            gaps.append("No access control mechanisms detected (auth, WAF, gateway)")
            return ControlStatus.NON_COMPLIANT, evidence, gaps

    def _check_encryption(self, graph: InfraGraph) -> tuple[ControlStatus, list[str], list[str]]:
        """Check if encryption is in place (at rest and in transit)."""
        evidence: list[str] = []
        gaps: list[str] = []

        enc_rest_count = sum(1 for c in graph.components.values() if c.security.encryption_at_rest)
        enc_transit_count = sum(1 for c in graph.components.values() if c.security.encryption_in_transit)
        tls_count = sum(1 for c in graph.components.values() if c.port == 443)
        total = len(graph.components)

        if enc_rest_count > 0:
            evidence.append(f"Encryption at rest: {enc_rest_count}/{total} components")
        if enc_transit_count > 0 or tls_count > 0:
            evidence.append(f"Encryption in transit: {enc_transit_count}/{total} components, {tls_count} using TLS (port 443)")

        has_rest = enc_rest_count > 0
        has_transit = enc_transit_count > 0 or tls_count > 0

        if has_rest and has_transit:
            if enc_rest_count == total and (enc_transit_count == total or tls_count == total):
                return ControlStatus.COMPLIANT, evidence, gaps
            else:
                gaps.append("Not all components have encryption enabled")
                return ControlStatus.PARTIAL, evidence, gaps
        elif has_rest or has_transit:
            if not has_rest:
                gaps.append("No encryption at rest configured")
            if not has_transit:
                gaps.append("No encryption in transit configured")
            return ControlStatus.PARTIAL, evidence, gaps
        else:
            gaps.append("No encryption configured (at rest or in transit)")
            return ControlStatus.NON_COMPLIANT, evidence, gaps

    def _check_network_security(self, graph: InfraGraph) -> tuple[ControlStatus, list[str], list[str]]:
        """Check network security (WAF, segmentation, rate limiting)."""
        evidence: list[str] = []
        gaps: list[str] = []

        waf_count = sum(1 for c in graph.components.values() if c.security.waf_protected)
        seg_count = sum(1 for c in graph.components.values() if c.security.network_segmented)
        rate_count = sum(1 for c in graph.components.values() if c.security.rate_limiting)

        if waf_count > 0:
            evidence.append(f"WAF protection: {waf_count} components")
        if seg_count > 0:
            evidence.append(f"Network segmentation: {seg_count} components")
        if rate_count > 0:
            evidence.append(f"Rate limiting: {rate_count} components")

        score = sum([waf_count > 0, seg_count > 0, rate_count > 0])

        if score >= 3:
            return ControlStatus.COMPLIANT, evidence, gaps
        elif score >= 1:
            if waf_count == 0:
                gaps.append("WAF protection not enabled")
            if seg_count == 0:
                gaps.append("Network segmentation not configured")
            if rate_count == 0:
                gaps.append("Rate limiting not configured")
            return ControlStatus.PARTIAL, evidence, gaps
        else:
            gaps.append("No network security controls (WAF, segmentation, rate limiting)")
            return ControlStatus.NON_COMPLIANT, evidence, gaps

    def _check_business_continuity(self, graph: InfraGraph) -> tuple[ControlStatus, list[str], list[str]]:
        """Check business continuity (DR, failover, multi-region)."""
        evidence: list[str] = []
        gaps: list[str] = []

        has_dr = False
        has_failover = False
        has_multi_region = False

        for comp in graph.components.values():
            if comp.failover.enabled:
                has_failover = True
                evidence.append(f"{comp.name}: failover enabled (promotion time: {comp.failover.promotion_time_seconds}s)")

            region = getattr(comp, "region", None)
            if region is not None:
                if region.dr_target_region:
                    has_dr = True
                    evidence.append(f"{comp.name}: DR target region configured ({region.dr_target_region})")
                if not region.is_primary:
                    has_multi_region = True
                    evidence.append(f"{comp.name}: secondary region instance")

        dr_keywords = {"dr-", "disaster", "backup-region", "standby"}
        for comp in graph.components.values():
            comp_lower = (comp.id + " " + comp.name).lower()
            if any(kw in comp_lower for kw in dr_keywords):
                has_dr = True
                evidence.append(f"DR component detected: {comp.name}")

        score = sum([has_dr, has_failover, has_multi_region])
        if score >= 2:
            return ControlStatus.COMPLIANT, evidence, gaps
        elif score >= 1:
            if not has_dr:
                gaps.append("No disaster recovery region configured")
            if not has_failover:
                gaps.append("No failover configuration on databases/critical components")
            if not has_multi_region:
                gaps.append("Single-region deployment")
            return ControlStatus.PARTIAL, evidence, gaps
        else:
            gaps.append("No business continuity measures (DR, failover, multi-region)")
            return ControlStatus.NON_COMPLIANT, evidence, gaps

    def _check_failover_capability(self, graph: InfraGraph) -> tuple[ControlStatus, list[str], list[str]]:
        """Check if failover is enabled on critical components."""
        evidence: list[str] = []
        gaps: list[str] = []

        db_cache = [
            c for c in graph.components.values()
            if c.type in (ComponentType.DATABASE, ComponentType.CACHE)
        ]
        if not db_cache:
            return ControlStatus.NOT_APPLICABLE, ["No database/cache components found"], gaps

        with_failover = [c for c in db_cache if c.failover.enabled]
        without_failover = [c for c in db_cache if not c.failover.enabled]

        for c in with_failover:
            evidence.append(f"{c.name}: failover enabled")
        for c in without_failover:
            gaps.append(f"{c.name}: failover not enabled")

        if len(with_failover) == len(db_cache):
            return ControlStatus.COMPLIANT, evidence, gaps
        elif len(with_failover) > 0:
            return ControlStatus.PARTIAL, evidence, gaps
        else:
            return ControlStatus.NON_COMPLIANT, evidence, gaps

    def _check_concentration_risk(self, graph: InfraGraph) -> tuple[ControlStatus, list[str], list[str]]:
        """Check for concentration risk (SPOFs)."""
        evidence: list[str] = []
        gaps: list[str] = []

        spofs = []
        for comp in graph.components.values():
            dependents = graph.get_dependents(comp.id)
            if comp.replicas <= 1 and len(dependents) > 0:
                spofs.append(comp)
                gaps.append(f"SPOF: {comp.name} has {len(dependents)} dependents with only 1 replica")

        if not spofs:
            evidence.append("No single points of failure detected")
            return ControlStatus.COMPLIANT, evidence, gaps
        elif len(spofs) <= len(graph.components) // 3:
            evidence.append(f"{len(spofs)} SPOFs found out of {len(graph.components)} components")
            return ControlStatus.PARTIAL, evidence, gaps
        else:
            return ControlStatus.NON_COMPLIANT, evidence, gaps

    def _check_third_party_risk(self, graph: InfraGraph) -> tuple[ControlStatus, list[str], list[str]]:
        """Check third-party dependency risk management."""
        evidence: list[str] = []
        gaps: list[str] = []

        external = [c for c in graph.components.values() if c.type == ComponentType.EXTERNAL_API]
        if not external:
            evidence.append("No external API dependencies detected")
            return ControlStatus.COMPLIANT, evidence, gaps

        for ext in external:
            if ext.replicas >= 2 or ext.failover.enabled:
                evidence.append(f"{ext.name}: redundancy configured (replicas={ext.replicas}, failover={ext.failover.enabled})")
            else:
                gaps.append(f"{ext.name}: no redundancy for external dependency")

        managed = sum(1 for e in external if e.replicas >= 2 or e.failover.enabled)
        if managed == len(external):
            return ControlStatus.COMPLIANT, evidence, gaps
        elif managed > 0:
            return ControlStatus.PARTIAL, evidence, gaps
        else:
            return ControlStatus.NON_COMPLIANT, evidence, gaps

    def _check_third_party_exit(self, graph: InfraGraph) -> tuple[ControlStatus, list[str], list[str]]:
        """Check exit strategy readiness for critical third-party providers."""
        evidence: list[str] = []
        gaps: list[str] = []

        external = [c for c in graph.components.values() if c.type == ComponentType.EXTERNAL_API]
        if not external:
            evidence.append("No external API dependencies - no exit strategy needed")
            return ControlStatus.NOT_APPLICABLE, evidence, gaps

        # Check if circuit breakers exist (indication of abstraction/decoupling)
        for ext in external:
            dependents = graph.get_dependents(ext.id)
            has_cb = False
            for dep_comp in dependents:
                edge = graph.get_dependency_edge(dep_comp.id, ext.id)
                if edge and edge.circuit_breaker.enabled:
                    has_cb = True
                    break
            if has_cb:
                evidence.append(f"{ext.name}: circuit breaker provides decoupling")
            else:
                gaps.append(f"{ext.name}: no circuit breaker isolation for exit strategy")

        managed = sum(1 for e in evidence if "circuit breaker" in e)
        if managed == len(external):
            return ControlStatus.COMPLIANT, evidence, gaps
        elif managed > 0:
            return ControlStatus.PARTIAL, evidence, gaps
        else:
            return ControlStatus.NON_COMPLIANT, evidence, gaps

    def _check_security_controls(self, graph: InfraGraph) -> tuple[ControlStatus, list[str], list[str]]:
        """Check overall security control posture."""
        evidence: list[str] = []
        gaps: list[str] = []

        checks = 0
        passed = 0

        # IDS/IPS
        ids_count = sum(1 for c in graph.components.values() if c.security.ids_monitored)
        checks += 1
        if ids_count > 0:
            passed += 1
            evidence.append(f"IDS monitoring: {ids_count} components")
        else:
            gaps.append("No IDS/IPS monitoring configured")

        # WAF
        waf_count = sum(1 for c in graph.components.values() if c.security.waf_protected)
        checks += 1
        if waf_count > 0:
            passed += 1
            evidence.append(f"WAF protection: {waf_count} components")
        else:
            gaps.append("WAF not configured")

        # Backup
        backup_count = sum(1 for c in graph.components.values() if c.security.backup_enabled)
        checks += 1
        if backup_count > 0:
            passed += 1
            evidence.append(f"Backup enabled: {backup_count} components")
        else:
            gaps.append("No backup configuration detected")

        if passed == checks:
            return ControlStatus.COMPLIANT, evidence, gaps
        elif passed > 0:
            return ControlStatus.PARTIAL, evidence, gaps
        else:
            return ControlStatus.NON_COMPLIANT, evidence, gaps

    def _check_change_management(self, graph: InfraGraph) -> tuple[ControlStatus, list[str], list[str]]:
        """Check change management controls."""
        evidence: list[str] = []
        gaps: list[str] = []

        cm_count = sum(1 for c in graph.components.values() if c.compliance_tags.change_management)
        total = len(graph.components)

        if cm_count > 0:
            evidence.append(f"Change management tagged: {cm_count}/{total} components")
            if cm_count == total:
                return ControlStatus.COMPLIANT, evidence, gaps
            else:
                gaps.append(f"{total - cm_count} components without change management tags")
                return ControlStatus.PARTIAL, evidence, gaps
        else:
            # Infer from having monitoring and circuit breakers
            mon_status, _, _ = self._check_monitoring(graph)
            if mon_status != ControlStatus.NON_COMPLIANT:
                evidence.append("Monitoring in place supports change detection")
                return ControlStatus.PARTIAL, evidence, gaps
            gaps.append("No change management controls detected")
            return ControlStatus.NON_COMPLIANT, evidence, gaps

    def _check_backup_procedures(self, graph: InfraGraph) -> tuple[ControlStatus, list[str], list[str]]:
        """Check if backup procedures are in place."""
        evidence: list[str] = []
        gaps: list[str] = []

        db_storage = [
            c for c in graph.components.values()
            if c.type in (ComponentType.DATABASE, ComponentType.STORAGE, ComponentType.CACHE)
        ]
        if not db_storage:
            return ControlStatus.NOT_APPLICABLE, ["No data storage components found"], gaps

        backed_up = [c for c in db_storage if c.security.backup_enabled]
        not_backed_up = [c for c in db_storage if not c.security.backup_enabled]

        for c in backed_up:
            evidence.append(f"{c.name}: backup enabled (frequency: {c.security.backup_frequency_hours}h)")
        for c in not_backed_up:
            gaps.append(f"{c.name}: backup not enabled")

        if len(backed_up) == len(db_storage):
            return ControlStatus.COMPLIANT, evidence, gaps
        elif len(backed_up) > 0:
            return ControlStatus.PARTIAL, evidence, gaps
        else:
            return ControlStatus.NON_COMPLIANT, evidence, gaps

    def _check_security_management(self, graph: InfraGraph) -> tuple[ControlStatus, list[str], list[str]]:
        """Check security management process (HIPAA-specific composite check)."""
        # Composite check of access controls + encryption + monitoring
        ac_status, ac_ev, ac_gaps = self._check_access_controls(graph)
        enc_status, enc_ev, enc_gaps = self._check_encryption(graph)
        mon_status, mon_ev, mon_gaps = self._check_monitoring(graph)

        evidence = ac_ev + enc_ev + mon_ev
        all_gaps = ac_gaps + enc_gaps + mon_gaps

        compliant_count = sum(
            1 for s in [ac_status, enc_status, mon_status]
            if s in (ControlStatus.COMPLIANT, ControlStatus.PARTIAL)
        )
        if compliant_count == 3:
            return ControlStatus.COMPLIANT, evidence, all_gaps
        elif compliant_count >= 1:
            return ControlStatus.PARTIAL, evidence, all_gaps
        else:
            return ControlStatus.NON_COMPLIANT, evidence, all_gaps

    def _check_audit_controls(self, graph: InfraGraph) -> tuple[ControlStatus, list[str], list[str]]:
        """Check audit control capabilities."""
        evidence: list[str] = []
        gaps: list[str] = []

        log_count = sum(1 for c in graph.components.values() if c.security.log_enabled)
        audit_count = sum(1 for c in graph.components.values() if c.compliance_tags.audit_logging)
        total = len(graph.components)

        if log_count > 0:
            evidence.append(f"Logging enabled: {log_count}/{total} components")
        if audit_count > 0:
            evidence.append(f"Audit logging tagged: {audit_count}/{total} components")

        if log_count > 0 and audit_count > 0:
            return ControlStatus.COMPLIANT, evidence, gaps
        elif log_count > 0 or audit_count > 0:
            if log_count == 0:
                gaps.append("Logging not enabled on components")
            if audit_count == 0:
                gaps.append("Audit logging tags not set on components")
            return ControlStatus.PARTIAL, evidence, gaps
        else:
            gaps.append("No audit controls (logging, audit tags) detected")
            return ControlStatus.NON_COMPLIANT, evidence, gaps

    def _check_data_integrity(self, graph: InfraGraph) -> tuple[ControlStatus, list[str], list[str]]:
        """Check data integrity controls."""
        evidence: list[str] = []
        gaps: list[str] = []

        enc_rest = sum(1 for c in graph.components.values() if c.security.encryption_at_rest)
        backup = sum(1 for c in graph.components.values() if c.security.backup_enabled)
        total = len(graph.components)

        if enc_rest > 0:
            evidence.append(f"Encryption at rest: {enc_rest}/{total} components")
        if backup > 0:
            evidence.append(f"Backup for integrity: {backup}/{total} components")

        if enc_rest > 0 and backup > 0:
            return ControlStatus.COMPLIANT, evidence, gaps
        elif enc_rest > 0 or backup > 0:
            if enc_rest == 0:
                gaps.append("Encryption at rest not configured for data integrity")
            if backup == 0:
                gaps.append("Backup not configured for data recovery")
            return ControlStatus.PARTIAL, evidence, gaps
        else:
            gaps.append("No data integrity controls (encryption at rest, backup)")
            return ControlStatus.NON_COMPLIANT, evidence, gaps

    # ------------------------------------------------------------------
    # Core assessment methods
    # ------------------------------------------------------------------

    def _run_check(self, check_name: str, graph: InfraGraph) -> tuple[ControlStatus, list[str], list[str]]:
        """Dispatch to the named check method."""
        method = getattr(self, check_name, None)
        if method is None:
            logger.warning("Unknown check method: %s", check_name)
            return ControlStatus.UNKNOWN, [], [f"Check method '{check_name}' not implemented"]
        return method(graph)

    def assess(self, graph: InfraGraph, framework: ComplianceFramework) -> ComplianceSnapshot:
        """Assess compliance for a single framework against the infrastructure graph."""
        now = datetime.now(timezone.utc)
        control_defs = self._control_defs.get(framework, [])
        controls: list[ComplianceControl] = []

        for cdef in control_defs:
            status, evidence, gaps = self._run_check(cdef["check"], graph)
            remediation: list[str] = []
            if status in (ControlStatus.NON_COMPLIANT, ControlStatus.PARTIAL):
                for gap in gaps:
                    remediation.append(f"Address: {gap}")

            controls.append(ComplianceControl(
                control_id=cdef["control_id"],
                framework=framework,
                title=cdef["title"],
                description=cdef["description"],
                status=status,
                evidence=evidence,
                gaps=gaps,
                remediation=remediation,
                last_assessed=now,
                risk_if_non_compliant=cdef.get("risk", ""),
            ))

        compliant = sum(1 for c in controls if c.status == ControlStatus.COMPLIANT)
        partial = sum(1 for c in controls if c.status == ControlStatus.PARTIAL)
        non_compliant = sum(1 for c in controls if c.status == ControlStatus.NON_COMPLIANT)
        total = len(controls)
        applicable = total - sum(1 for c in controls if c.status == ControlStatus.NOT_APPLICABLE)

        pct = 0.0
        if applicable > 0:
            pct = (compliant + partial * 0.5) / applicable * 100.0

        return ComplianceSnapshot(
            timestamp=now,
            framework=framework,
            total_controls=total,
            compliant=compliant,
            partial=partial,
            non_compliant=non_compliant,
            compliance_percentage=round(pct, 1),
            controls=controls,
        )

    def assess_all(self, graph: InfraGraph) -> dict[ComplianceFramework, ComplianceSnapshot]:
        """Assess compliance for all supported frameworks."""
        return {fw: self.assess(graph, fw) for fw in ComplianceFramework}

    def track(self, graph: InfraGraph) -> None:
        """Record a compliance snapshot for all frameworks into history."""
        for fw in ComplianceFramework:
            snapshot = self.assess(graph, fw)
            self._history[fw].append(snapshot)
            if self._store_path is not None:
                self._persist_snapshot(snapshot)

    def get_trends(self, framework: ComplianceFramework) -> ComplianceTrend:
        """Analyze compliance trends for a framework based on recorded history."""
        snapshots = self._history.get(framework, [])
        if not snapshots:
            return ComplianceTrend(framework=framework)

        current = snapshots[-1]
        current_pct = current.compliance_percentage

        # Calculate 30-day delta
        delta_30d = 0.0
        if len(snapshots) >= 2:
            oldest = snapshots[0]
            delta_30d = current_pct - oldest.compliance_percentage

        # Determine trend
        if len(snapshots) >= 2:
            recent_pcts = [s.compliance_percentage for s in snapshots[-3:]]
            all_equal = all(recent_pcts[i] == recent_pcts[i + 1] for i in range(len(recent_pcts) - 1))
            if all_equal:
                trend = "stable"
            elif all(recent_pcts[i] <= recent_pcts[i + 1] for i in range(len(recent_pcts) - 1)):
                trend = "improving"
            elif all(recent_pcts[i] >= recent_pcts[i + 1] for i in range(len(recent_pcts) - 1)):
                trend = "degrading"
            else:
                trend = "stable"
        else:
            trend = "stable"

        # Identify risk areas (non-compliant controls in latest snapshot)
        risk_areas: list[str] = []
        for control in current.controls:
            if control.status == ControlStatus.NON_COMPLIANT:
                risk_areas.append(f"{control.control_id}: {control.title}")

        return ComplianceTrend(
            framework=framework,
            snapshots=snapshots,
            trend=trend,
            current_percentage=current_pct,
            delta_30d=round(delta_30d, 1),
            risk_areas=risk_areas,
        )

    def detect_violations(self, graph: InfraGraph) -> list[ComplianceAlert]:
        """Detect new compliance violations by comparing current state to last snapshot."""
        alerts: list[ComplianceAlert] = []
        now = datetime.now(timezone.utc)

        for fw in ComplianceFramework:
            current_snapshot = self.assess(graph, fw)
            previous_snapshots = self._history.get(fw, [])

            if not previous_snapshots:
                # First assessment - flag any non-compliant controls
                for control in current_snapshot.controls:
                    if control.status == ControlStatus.NON_COMPLIANT:
                        alerts.append(ComplianceAlert(
                            alert_type="new_violation",
                            framework=fw,
                            control_id=control.control_id,
                            severity="high",
                            message=f"{control.control_id} ({control.title}) is non-compliant: {'; '.join(control.gaps)}",
                            timestamp=now,
                        ))
                continue

            previous = previous_snapshots[-1]
            prev_status_map = {c.control_id: c.status for c in previous.controls}

            for control in current_snapshot.controls:
                prev_status = prev_status_map.get(control.control_id)

                if prev_status is None:
                    continue

                # Detect degradation: was compliant/partial, now non-compliant
                if (
                    prev_status in (ControlStatus.COMPLIANT, ControlStatus.PARTIAL)
                    and control.status == ControlStatus.NON_COMPLIANT
                ):
                    alerts.append(ComplianceAlert(
                        alert_type="degradation",
                        framework=fw,
                        control_id=control.control_id,
                        severity="critical",
                        message=(
                            f"{control.control_id} degraded from {prev_status.value} "
                            f"to non_compliant: {'; '.join(control.gaps)}"
                        ),
                        timestamp=now,
                    ))
                # Detect new violation: was compliant, now partial
                elif (
                    prev_status == ControlStatus.COMPLIANT
                    and control.status == ControlStatus.PARTIAL
                ):
                    alerts.append(ComplianceAlert(
                        alert_type="degradation",
                        framework=fw,
                        control_id=control.control_id,
                        severity="medium",
                        message=(
                            f"{control.control_id} partially degraded from compliant "
                            f"to partial: {'; '.join(control.gaps)}"
                        ),
                        timestamp=now,
                    ))

            # Overall degradation check
            if current_snapshot.compliance_percentage < previous.compliance_percentage - 5.0:
                alerts.append(ComplianceAlert(
                    alert_type="degradation",
                    framework=fw,
                    control_id="OVERALL",
                    severity="high",
                    message=(
                        f"{fw.value} compliance dropped from "
                        f"{previous.compliance_percentage:.1f}% to "
                        f"{current_snapshot.compliance_percentage:.1f}%"
                    ),
                    timestamp=now,
                ))

        return alerts

    def get_audit_readiness(self, framework: ComplianceFramework) -> float:
        """Calculate audit readiness score (0-100%) for a framework.

        Considers: compliance percentage, evidence coverage, gap count.
        """
        snapshots = self._history.get(framework, [])
        if not snapshots:
            return 0.0

        latest = snapshots[-1]
        base_score = latest.compliance_percentage

        # Bonus for having evidence
        controls_with_evidence = sum(
            1 for c in latest.controls
            if len(c.evidence) > 0
        )
        evidence_ratio = controls_with_evidence / latest.total_controls if latest.total_controls > 0 else 0
        evidence_bonus = evidence_ratio * 10.0  # up to 10% bonus

        # Penalty for gaps
        total_gaps = sum(len(c.gaps) for c in latest.controls)
        gap_penalty = min(20.0, total_gaps * 2.0)

        score = base_score + evidence_bonus - gap_penalty
        return max(0.0, min(100.0, round(score, 1)))

    def generate_evidence_package(self, framework: ComplianceFramework) -> dict:
        """Generate an evidence package for auditors.

        Returns a dict structure with framework name, assessment date,
        controls with evidence, and summary statistics.
        """
        snapshots = self._history.get(framework, [])
        if not snapshots:
            return {
                "framework": framework.value,
                "assessment_date": datetime.now(timezone.utc).isoformat(),
                "status": "no_assessments",
                "controls": [],
                "summary": {},
            }

        latest = snapshots[-1]

        controls_data = []
        for control in latest.controls:
            controls_data.append({
                "control_id": control.control_id,
                "title": control.title,
                "description": control.description,
                "status": control.status.value,
                "evidence": control.evidence,
                "gaps": control.gaps,
                "remediation": control.remediation,
                "last_assessed": control.last_assessed.isoformat(),
                "risk_if_non_compliant": control.risk_if_non_compliant,
            })

        return {
            "framework": framework.value,
            "assessment_date": latest.timestamp.isoformat(),
            "status": "assessed",
            "audit_readiness": self.get_audit_readiness(framework),
            "summary": {
                "total_controls": latest.total_controls,
                "compliant": latest.compliant,
                "partial": latest.partial,
                "non_compliant": latest.non_compliant,
                "compliance_percentage": latest.compliance_percentage,
            },
            "controls": controls_data,
            "trend": {
                "direction": self.get_trends(framework).trend,
                "delta_30d": self.get_trends(framework).delta_30d,
                "risk_areas": self.get_trends(framework).risk_areas,
            },
        }

    # ------------------------------------------------------------------
    # SQLite persistence
    # ------------------------------------------------------------------

    def _init_store(self) -> None:
        """Create SQLite tables if they do not exist."""
        if self._store_path is None:
            return
        self._store_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._store_path))
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS compliance_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    framework TEXT NOT NULL,
                    total_controls INTEGER NOT NULL,
                    compliant INTEGER NOT NULL,
                    partial INTEGER NOT NULL,
                    non_compliant INTEGER NOT NULL,
                    compliance_percentage REAL NOT NULL,
                    controls_json TEXT NOT NULL
                )
            """)
            conn.commit()
        finally:
            conn.close()

    def _persist_snapshot(self, snapshot: ComplianceSnapshot) -> None:
        """Write a single snapshot to the SQLite store."""
        if self._store_path is None:
            return
        controls_data = []
        for c in snapshot.controls:
            controls_data.append({
                "control_id": c.control_id,
                "framework": c.framework.value,
                "title": c.title,
                "description": c.description,
                "status": c.status.value,
                "evidence": c.evidence,
                "gaps": c.gaps,
                "remediation": c.remediation,
                "last_assessed": c.last_assessed.isoformat(),
                "risk_if_non_compliant": c.risk_if_non_compliant,
            })
        conn = sqlite3.connect(str(self._store_path))
        try:
            conn.execute(
                """INSERT INTO compliance_snapshots
                   (timestamp, framework, total_controls, compliant, partial,
                    non_compliant, compliance_percentage, controls_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    snapshot.timestamp.isoformat(),
                    snapshot.framework.value,
                    snapshot.total_controls,
                    snapshot.compliant,
                    snapshot.partial,
                    snapshot.non_compliant,
                    snapshot.compliance_percentage,
                    json.dumps(controls_data),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def _load_history_from_store(self) -> None:
        """Load all stored snapshots from SQLite into in-memory history."""
        if self._store_path is None or not self._store_path.exists():
            return
        conn = sqlite3.connect(str(self._store_path))
        try:
            cursor = conn.execute(
                "SELECT timestamp, framework, total_controls, compliant, "
                "partial, non_compliant, compliance_percentage, controls_json "
                "FROM compliance_snapshots ORDER BY id ASC"
            )
            for row in cursor:
                ts = datetime.fromisoformat(row[0])
                try:
                    fw = ComplianceFramework(row[1])
                except ValueError:
                    continue
                controls_raw = json.loads(row[7])
                controls: list[ComplianceControl] = []
                for cd in controls_raw:
                    try:
                        ctrl_fw = ComplianceFramework(cd.get("framework", fw.value))
                    except ValueError:
                        ctrl_fw = fw
                    try:
                        ctrl_status = ControlStatus(cd.get("status", "unknown"))
                    except ValueError:
                        ctrl_status = ControlStatus.UNKNOWN
                    controls.append(ComplianceControl(
                        control_id=cd.get("control_id", ""),
                        framework=ctrl_fw,
                        title=cd.get("title", ""),
                        description=cd.get("description", ""),
                        status=ctrl_status,
                        evidence=cd.get("evidence", []),
                        gaps=cd.get("gaps", []),
                        remediation=cd.get("remediation", []),
                        last_assessed=datetime.fromisoformat(cd["last_assessed"])
                        if "last_assessed" in cd else ts,
                        risk_if_non_compliant=cd.get("risk_if_non_compliant", ""),
                    ))
                snapshot = ComplianceSnapshot(
                    timestamp=ts,
                    framework=fw,
                    total_controls=row[2],
                    compliant=row[3],
                    partial=row[4],
                    non_compliant=row[5],
                    compliance_percentage=row[6],
                    controls=controls,
                )
                self._history[fw].append(snapshot)
        finally:
            conn.close()

    def get_stored_snapshot_count(self, framework: ComplianceFramework | None = None) -> int:
        """Return the number of snapshots stored (all frameworks or one)."""
        if framework is None:
            return sum(len(v) for v in self._history.values())
        return len(self._history.get(framework, []))
