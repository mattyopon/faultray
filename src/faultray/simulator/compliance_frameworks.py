# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Compliance Frameworks Engine — Multi-regulation compliance assessment.

Evaluate infrastructure against SOC 2 Type II, ISO 27001, PCI DSS,
and DORA requirements with gap analysis and remediation guidance.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ComplianceFramework(str, Enum):
    DORA = "dora"
    SOC2 = "soc2"
    ISO27001 = "iso27001"
    PCI_DSS = "pci_dss"
    HIPAA = "hipaa"
    GDPR = "gdpr"


class ControlStatus(str, Enum):
    COMPLIANT = "compliant"
    PARTIAL = "partial"
    NON_COMPLIANT = "non_compliant"
    NOT_APPLICABLE = "not_applicable"


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass
class ComplianceControl:
    """A specific compliance control/requirement."""
    control_id: str
    framework: ComplianceFramework
    title: str
    description: str
    status: ControlStatus = ControlStatus.NON_COMPLIANT
    severity: Severity = Severity.MEDIUM
    evidence: list[str] = field(default_factory=list)
    remediation: str = ""


@dataclass
class ComplianceReport:
    """Compliance assessment report for a framework."""
    framework: ComplianceFramework
    overall_score: float  # 0-100
    compliant_count: int = 0
    partial_count: int = 0
    non_compliant_count: int = 0
    not_applicable_count: int = 0
    controls: list[ComplianceControl] = field(default_factory=list)
    critical_gaps: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


@dataclass
class InfrastructureEvidence:
    """Evidence collected from infrastructure for compliance checking."""
    encryption_at_rest: bool = False
    encryption_in_transit: bool = False
    backup_enabled: bool = False
    backup_tested: bool = False
    mfa_enabled: bool = False
    audit_logging: bool = False
    access_reviews: bool = False
    network_segmentation: bool = False
    vulnerability_scanning: bool = False
    incident_response_plan: bool = False
    change_management: bool = False
    monitoring_enabled: bool = False
    dr_plan: bool = False
    dr_tested: bool = False
    data_classification: bool = False
    retention_policy: bool = False


class ComplianceFrameworksEngine:
    """Evaluate infrastructure compliance against multiple frameworks."""

    def __init__(self, evidence: Optional[InfrastructureEvidence] = None):
        self.evidence = evidence or InfrastructureEvidence()

    def assess(self, framework: ComplianceFramework) -> ComplianceReport:
        """Assess compliance against a specific framework."""
        controls = self._get_controls(framework)
        self._evaluate_controls(controls)

        compliant = sum(1 for c in controls if c.status == ControlStatus.COMPLIANT)
        partial = sum(1 for c in controls if c.status == ControlStatus.PARTIAL)
        non_comp = sum(1 for c in controls if c.status == ControlStatus.NON_COMPLIANT)
        na = sum(1 for c in controls if c.status == ControlStatus.NOT_APPLICABLE)

        applicable = len(controls) - na
        score = ((compliant + partial * 0.5) / max(applicable, 1)) * 100

        critical = [c.title for c in controls
                    if c.status == ControlStatus.NON_COMPLIANT and c.severity in (Severity.CRITICAL, Severity.HIGH)]
        recs = [c.remediation for c in controls if c.status == ControlStatus.NON_COMPLIANT and c.remediation][:10]

        return ComplianceReport(
            framework=framework,
            overall_score=round(score, 1),
            compliant_count=compliant,
            partial_count=partial,
            non_compliant_count=non_comp,
            not_applicable_count=na,
            controls=controls,
            critical_gaps=critical[:5],
            recommendations=recs,
        )

    def assess_all(self) -> list[ComplianceReport]:
        """Assess compliance against all supported frameworks."""
        return [self.assess(fw) for fw in ComplianceFramework]

    def _evaluate_controls(self, controls: list[ComplianceControl]) -> None:
        """Evaluate control status based on collected evidence."""
        evidence_map = {
            "encryption_at_rest": self.evidence.encryption_at_rest,
            "encryption_in_transit": self.evidence.encryption_in_transit,
            "backup": self.evidence.backup_enabled,
            "backup_tested": self.evidence.backup_tested,
            "mfa": self.evidence.mfa_enabled,
            "audit_log": self.evidence.audit_logging,
            "access_review": self.evidence.access_reviews,
            "network_seg": self.evidence.network_segmentation,
            "vuln_scan": self.evidence.vulnerability_scanning,
            "incident_response": self.evidence.incident_response_plan,
            "change_mgmt": self.evidence.change_management,
            "monitoring": self.evidence.monitoring_enabled,
            "dr_plan": self.evidence.dr_plan,
            "dr_tested": self.evidence.dr_tested,
            "data_class": self.evidence.data_classification,
            "retention": self.evidence.retention_policy,
        }

        for control in controls:
            # Build a search string from control ID, title, and description
            cid = (control.control_id.lower() + " " + control.title.lower()
                   + " " + control.description.lower())
            category = self._categorize_control(cid)
            if category == "encryption":
                if evidence_map["encryption_at_rest"] and evidence_map["encryption_in_transit"]:
                    control.status = ControlStatus.COMPLIANT
                    control.evidence.append("Encryption at rest and in transit enabled")
                elif evidence_map["encryption_at_rest"] or evidence_map["encryption_in_transit"]:
                    control.status = ControlStatus.PARTIAL
                    control.evidence.append("Partial encryption coverage")
            elif category == "backup":
                if evidence_map["backup"] and evidence_map["backup_tested"]:
                    control.status = ControlStatus.COMPLIANT
                    control.evidence.append("Backups enabled and tested")
                elif evidence_map["backup"]:
                    control.status = ControlStatus.PARTIAL
                    control.evidence.append("Backups enabled but not tested")
            elif category == "auth":
                if evidence_map["mfa"] and evidence_map["access_review"]:
                    control.status = ControlStatus.COMPLIANT
                    control.evidence.append("MFA and access reviews in place")
                elif evidence_map["mfa"]:
                    control.status = ControlStatus.PARTIAL
                    control.evidence.append("MFA enabled, access reviews missing")
            elif category == "monitoring":
                if evidence_map["audit_log"] and evidence_map["monitoring"]:
                    control.status = ControlStatus.COMPLIANT
                    control.evidence.append("Audit logging and monitoring enabled")
                elif evidence_map["audit_log"] or evidence_map["monitoring"]:
                    control.status = ControlStatus.PARTIAL
            elif category == "incident":
                if evidence_map["incident_response"]:
                    control.status = ControlStatus.COMPLIANT
                    control.evidence.append("Incident response plan documented")
            elif category == "change":
                if evidence_map["change_mgmt"]:
                    control.status = ControlStatus.COMPLIANT
                    control.evidence.append("Change management process in place")
            elif category == "network":
                if evidence_map["network_seg"]:
                    control.status = ControlStatus.COMPLIANT
                    control.evidence.append("Network segmentation implemented")
            elif category == "vuln":
                if evidence_map["vuln_scan"]:
                    control.status = ControlStatus.COMPLIANT
                    control.evidence.append("Vulnerability scanning active")
            elif category == "data":
                if evidence_map["data_class"] and evidence_map["retention"]:
                    control.status = ControlStatus.COMPLIANT
                elif evidence_map["data_class"] or evidence_map["retention"]:
                    control.status = ControlStatus.PARTIAL
            elif category == "dr":
                if evidence_map["dr_plan"] and evidence_map["dr_tested"]:
                    control.status = ControlStatus.COMPLIANT
                elif evidence_map["dr_plan"]:
                    control.status = ControlStatus.PARTIAL
            elif category == "risk_management":
                # Composite: needs monitoring + vuln scan + change mgmt
                checks = [evidence_map["monitoring"], evidence_map["vuln_scan"],
                          evidence_map["change_mgmt"]]
                if all(checks):
                    control.status = ControlStatus.COMPLIANT
                    control.evidence.append("Risk management controls in place")
                elif any(checks):
                    control.status = ControlStatus.PARTIAL
            elif category == "resilience_testing":
                # Composite: needs DR tested + vuln scan
                if evidence_map["dr_tested"] and evidence_map["vuln_scan"]:
                    control.status = ControlStatus.COMPLIANT
                    control.evidence.append("Resilience testing procedures verified")
                elif evidence_map["dr_tested"] or evidence_map["vuln_scan"]:
                    control.status = ControlStatus.PARTIAL
            elif category == "third_party":
                # Composite: needs monitoring + change mgmt
                if evidence_map["monitoring"] and evidence_map["change_mgmt"]:
                    control.status = ControlStatus.COMPLIANT
                    control.evidence.append("Third-party risk management in place")
                elif evidence_map["monitoring"] or evidence_map["change_mgmt"]:
                    control.status = ControlStatus.PARTIAL
            elif category == "breach":
                if evidence_map["incident_response"] and evidence_map["monitoring"]:
                    control.status = ControlStatus.COMPLIANT
                    control.evidence.append("Breach detection and notification ready")
                elif evidence_map["incident_response"] or evidence_map["monitoring"]:
                    control.status = ControlStatus.PARTIAL
            elif category == "security_composite":
                # Composite for general security controls (e.g., GDPR-32)
                checks = [evidence_map["encryption_at_rest"], evidence_map["mfa"],
                          evidence_map["monitoring"]]
                if all(checks):
                    control.status = ControlStatus.COMPLIANT
                    control.evidence.append("Security measures implemented")
                elif any(checks):
                    control.status = ControlStatus.PARTIAL
            elif category == "integrity":
                if evidence_map["monitoring"] and evidence_map["audit_log"]:
                    control.status = ControlStatus.COMPLIANT
                    control.evidence.append("Integrity controls in place")
                elif evidence_map["monitoring"] or evidence_map["audit_log"]:
                    control.status = ControlStatus.PARTIAL

    @staticmethod
    def _categorize_control(text: str) -> str:
        """Categorize a control based on keyword matching in combined text.

        Returns a category string used to select evidence-mapping logic.
        Order matters: more specific patterns are checked before general ones.
        """
        # Encryption / cryptography
        if "encrypt" in text or "crypto" in text or "transmission security" in text:
            return "encryption"
        # DR / disaster recovery (before backup, since "continuity" could overlap)
        if "disaster" in text:
            return "dr"
        # Backup / recovery / continuity / contingency
        if "backup" in text or "recovery" in text or "contingency" in text or "continuity" in text:
            return "backup"
        # Network / segmentation / firewall (before auth, since "network access" should be network)
        if "network" in text or "segment" in text or "firewall" in text:
            return "network"
        # Breach notification (before auth, since "authorities" contains "auth")
        if "breach" in text:
            return "breach"
        # Incident management (before auth, since "incident" is more specific)
        if "incident" in text:
            return "incident"
        # Auth / access / identity / MFA
        if "auth" in text or "access" in text or "identity" in text or "mfa" in text:
            return "auth"
        # Security of processing (composite security)
        if "security of processing" in text:
            return "security_composite"
        # Integrity
        if "integrity" in text:
            return "integrity"
        # Audit / logging / monitoring
        if "audit" in text or "log" in text or "monitor" in text:
            return "monitoring"
        # Change management
        if "change" in text:
            return "change"
        # Vulnerability / scanning / patching
        if "vuln" in text or "scan" in text or "patch" in text:
            return "vuln"
        # Resilience testing
        if "resilience test" in text:
            return "resilience_testing"
        # Third party risk
        if "third" in text and "party" in text:
            return "third_party"
        # Risk management (general)
        if "risk management" in text:
            return "risk_management"
        # Data classification / retention
        if "classif" in text or "retention" in text or "data" in text:
            return "data"
        # DR (check after other patterns to avoid false matches with "dora-")
        if "dr" in text and ("continuity" in text or "disaster" in text or text.startswith("dr")):
            return "dr"
        return "unknown"

    def _get_controls(self, framework: ComplianceFramework) -> list[ComplianceControl]:
        """Get control list for a framework."""
        if framework == ComplianceFramework.SOC2:
            return self._soc2_controls()
        elif framework == ComplianceFramework.ISO27001:
            return self._iso27001_controls()
        elif framework == ComplianceFramework.PCI_DSS:
            return self._pci_dss_controls()
        elif framework == ComplianceFramework.DORA:
            return self._dora_controls()
        elif framework == ComplianceFramework.HIPAA:
            return self._hipaa_controls()
        elif framework == ComplianceFramework.GDPR:
            return self._gdpr_controls()
        return []

    def _soc2_controls(self) -> list[ComplianceControl]:
        return [
            ComplianceControl("SOC2-CC6.1", ComplianceFramework.SOC2, "Logical Access Controls",
                "Restrict logical access to information assets", severity=Severity.CRITICAL,
                remediation="Implement RBAC and MFA for all systems"),
            ComplianceControl("SOC2-CC6.6", ComplianceFramework.SOC2, "Encryption",
                "Encrypt data in transit and at rest", severity=Severity.CRITICAL,
                remediation="Enable TLS 1.2+ and AES-256 encryption"),
            ComplianceControl("SOC2-CC7.2", ComplianceFramework.SOC2, "Monitoring",
                "Monitor system components for anomalies", severity=Severity.HIGH,
                remediation="Deploy monitoring and alerting system"),
            ComplianceControl("SOC2-CC7.3", ComplianceFramework.SOC2, "Incident Response",
                "Evaluate and respond to security incidents", severity=Severity.HIGH,
                remediation="Document and test incident response procedures"),
            ComplianceControl("SOC2-CC8.1", ComplianceFramework.SOC2, "Change Management",
                "Manage changes to infrastructure and software", severity=Severity.MEDIUM,
                remediation="Implement change approval and review process"),
            ComplianceControl("SOC2-A1.2", ComplianceFramework.SOC2, "Backup & Recovery",
                "Backup data and test recovery procedures", severity=Severity.HIGH,
                remediation="Enable automated backups with regular restore tests"),
            ComplianceControl("SOC2-CC6.7", ComplianceFramework.SOC2, "Network Security",
                "Restrict network access with segmentation", severity=Severity.MEDIUM,
                remediation="Implement network segmentation and firewall rules"),
            ComplianceControl("SOC2-CC7.1", ComplianceFramework.SOC2, "Vulnerability Management",
                "Identify and remediate vulnerabilities", severity=Severity.HIGH,
                remediation="Run regular vulnerability scans and patch promptly"),
        ]

    def _iso27001_controls(self) -> list[ComplianceControl]:
        return [
            ComplianceControl("ISO-A.8.24", ComplianceFramework.ISO27001, "Cryptography",
                "Use of cryptographic controls", severity=Severity.CRITICAL,
                remediation="Implement encryption for data at rest and in transit"),
            ComplianceControl("ISO-A.8.15", ComplianceFramework.ISO27001, "Logging",
                "Activity logging and monitoring", severity=Severity.HIGH,
                remediation="Enable comprehensive audit logging"),
            ComplianceControl("ISO-A.5.15", ComplianceFramework.ISO27001, "Access Control",
                "Identity and access management", severity=Severity.CRITICAL,
                remediation="Implement MFA and periodic access reviews"),
            ComplianceControl("ISO-A.8.8", ComplianceFramework.ISO27001, "Vulnerability Management",
                "Technical vulnerability management", severity=Severity.HIGH,
                remediation="Establish vulnerability scanning and patching process"),
            ComplianceControl("ISO-A.5.26", ComplianceFramework.ISO27001, "Incident Management",
                "Information security incident management", severity=Severity.HIGH,
                remediation="Document incident response procedures"),
            ComplianceControl("ISO-A.8.13", ComplianceFramework.ISO27001, "Backup",
                "Information backup", severity=Severity.MEDIUM,
                remediation="Implement and test backup procedures"),
            ComplianceControl("ISO-A.8.22", ComplianceFramework.ISO27001, "Network Segmentation",
                "Segregation of networks", severity=Severity.MEDIUM,
                remediation="Implement network segmentation"),
            ComplianceControl("ISO-A.8.32", ComplianceFramework.ISO27001, "Change Management",
                "Change management procedures", severity=Severity.MEDIUM,
                remediation="Establish change management process"),
        ]

    def _pci_dss_controls(self) -> list[ComplianceControl]:
        return [
            ComplianceControl("PCI-3.5", ComplianceFramework.PCI_DSS, "Encryption of Stored Data",
                "Protect stored cardholder data with encryption", severity=Severity.CRITICAL,
                remediation="Encrypt all stored cardholder data with AES-256"),
            ComplianceControl("PCI-4.1", ComplianceFramework.PCI_DSS, "Encryption in Transit",
                "Encrypt transmission of cardholder data", severity=Severity.CRITICAL,
                remediation="Enforce TLS 1.2+ for all data transmission"),
            ComplianceControl("PCI-1.3", ComplianceFramework.PCI_DSS, "Network Firewall",
                "Restrict connections between untrusted networks", severity=Severity.CRITICAL,
                remediation="Implement firewall rules and network segmentation"),
            ComplianceControl("PCI-8.3", ComplianceFramework.PCI_DSS, "Multi-Factor Auth",
                "Secure all individual access with MFA", severity=Severity.CRITICAL,
                remediation="Enable MFA for all administrative access"),
            ComplianceControl("PCI-10.2", ComplianceFramework.PCI_DSS, "Audit Trail",
                "Implement automated audit trails", severity=Severity.HIGH,
                remediation="Enable comprehensive audit logging for all access"),
            ComplianceControl("PCI-11.3", ComplianceFramework.PCI_DSS, "Vulnerability Scanning",
                "Perform regular vulnerability scans", severity=Severity.HIGH,
                remediation="Run quarterly ASV scans and annual penetration tests"),
            ComplianceControl("PCI-12.10", ComplianceFramework.PCI_DSS, "Incident Response",
                "Implement an incident response plan", severity=Severity.HIGH,
                remediation="Document and test incident response plan annually"),
            ComplianceControl("PCI-9.4", ComplianceFramework.PCI_DSS, "Data Classification",
                "Classify data based on sensitivity", severity=Severity.MEDIUM,
                remediation="Implement data classification and retention policies"),
        ]

    def _dora_controls(self) -> list[ComplianceControl]:
        return [
            ComplianceControl("DORA-5", ComplianceFramework.DORA, "ICT Risk Management",
                "ICT risk management framework", severity=Severity.CRITICAL,
                remediation="Establish comprehensive ICT risk management framework"),
            ComplianceControl("DORA-11", ComplianceFramework.DORA, "Resilience Testing",
                "Digital operational resilience testing", severity=Severity.CRITICAL,
                remediation="Conduct regular resilience testing including TLPT"),
            ComplianceControl("DORA-17", ComplianceFramework.DORA, "Incident Reporting",
                "ICT-related incident management and reporting", severity=Severity.HIGH,
                remediation="Implement incident classification and reporting procedures"),
            ComplianceControl("DORA-28", ComplianceFramework.DORA, "Third Party Risk",
                "Managing of ICT third-party risk", severity=Severity.HIGH,
                remediation="Assess and monitor third-party ICT providers"),
            ComplianceControl("DORA-DR", ComplianceFramework.DORA, "DR & Business Continuity",
                "Business continuity and disaster recovery", severity=Severity.HIGH,
                remediation="Implement and test DR/BCP plans"),
            ComplianceControl("DORA-ENCRYPT", ComplianceFramework.DORA, "Data Protection",
                "Protection of data and systems", severity=Severity.HIGH,
                remediation="Implement encryption and data protection measures"),
        ]

    def _hipaa_controls(self) -> list[ComplianceControl]:
        return [
            ComplianceControl("HIPAA-164.312a", ComplianceFramework.HIPAA, "Access Control",
                "Implement technical policies for electronic PHI access", severity=Severity.CRITICAL,
                remediation="Implement RBAC with MFA for PHI access"),
            ComplianceControl("HIPAA-164.312e", ComplianceFramework.HIPAA, "Transmission Security",
                "Encrypt PHI in transmission", severity=Severity.CRITICAL,
                remediation="Enforce TLS for all PHI transmission"),
            ComplianceControl("HIPAA-164.312b", ComplianceFramework.HIPAA, "Audit Controls",
                "Record and examine activity in systems with PHI", severity=Severity.HIGH,
                remediation="Enable audit logging for all PHI access"),
            ComplianceControl("HIPAA-164.308a7", ComplianceFramework.HIPAA, "Contingency Plan",
                "Establish DR and data backup plans for PHI", severity=Severity.HIGH,
                remediation="Implement backup and DR plans for PHI systems"),
            ComplianceControl("HIPAA-164.312c", ComplianceFramework.HIPAA, "Integrity",
                "Protect PHI from improper alteration", severity=Severity.HIGH,
                remediation="Implement integrity controls and monitoring"),
        ]

    def _gdpr_controls(self) -> list[ComplianceControl]:
        return [
            ComplianceControl("GDPR-32", ComplianceFramework.GDPR, "Security of Processing",
                "Implement appropriate technical and organizational measures", severity=Severity.CRITICAL,
                remediation="Implement encryption, access control, and monitoring"),
            ComplianceControl("GDPR-33", ComplianceFramework.GDPR, "Breach Notification",
                "Notify authorities within 72 hours of breach", severity=Severity.CRITICAL,
                remediation="Implement breach detection and notification procedures"),
            ComplianceControl("GDPR-ENCRYPT", ComplianceFramework.GDPR, "Encryption",
                "Encryption of personal data", severity=Severity.HIGH,
                remediation="Encrypt personal data at rest and in transit"),
            ComplianceControl("GDPR-AUDIT", ComplianceFramework.GDPR, "Audit Logging",
                "Logging of data processing activities", severity=Severity.HIGH,
                remediation="Implement comprehensive audit logging"),
            ComplianceControl("GDPR-DATA-CLASS", ComplianceFramework.GDPR, "Data Classification",
                "Classify and inventory personal data", severity=Severity.MEDIUM,
                remediation="Implement data classification and data mapping"),
            ComplianceControl("GDPR-RETENTION", ComplianceFramework.GDPR, "Data Retention",
                "Define and enforce data retention policies", severity=Severity.MEDIUM,
                remediation="Implement data retention policies with automated enforcement"),
        ]
