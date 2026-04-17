# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Compliance scorecard generator — automated framework scoring.

Scores infrastructure against multiple compliance frameworks
(SOC2, ISO 27001, PCI DSS, HIPAA, NIST CSF, DORA) by analyzing
component configurations, security profiles, and resilience posture.
Each control is scored 0-100 with evidence references.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from faultray.model.components import ComponentType
from faultray.model.graph import InfraGraph


class Framework(str, Enum):
    """Supported compliance frameworks."""

    SOC2 = "SOC2"
    ISO27001 = "ISO27001"
    PCI_DSS = "PCI_DSS"
    HIPAA = "HIPAA"
    NIST_CSF = "NIST_CSF"
    DORA = "DORA"


class ControlStatus(str, Enum):
    """Status of a compliance control."""

    COMPLIANT = "compliant"
    PARTIAL = "partial"
    NON_COMPLIANT = "non_compliant"
    NOT_APPLICABLE = "not_applicable"


@dataclass
class ControlEvidence:
    """Evidence supporting a control assessment."""

    component_id: str
    component_name: str
    finding: str
    supports_compliance: bool


@dataclass
class ControlAssessment:
    """Assessment of a single compliance control."""

    control_id: str
    control_name: str
    description: str
    score: float  # 0-100
    status: ControlStatus
    evidence: list[ControlEvidence]
    gaps: list[str]
    recommendations: list[str]


@dataclass
class FrameworkScorecard:
    """Scorecard for a single compliance framework."""

    framework: Framework
    overall_score: float  # 0-100
    controls: list[ControlAssessment]
    compliant_count: int
    partial_count: int
    non_compliant_count: int
    not_applicable_count: int
    grade: str  # A, B, C, D, F
    summary: str


@dataclass
class ComplianceReport:
    """Full compliance report across all assessed frameworks."""

    scorecards: dict[str, FrameworkScorecard]
    overall_score: float
    overall_grade: str
    top_gaps: list[str]
    priority_actions: list[str]
    component_count: int
    frameworks_assessed: int


def _score_to_grade(score: float) -> str:
    """Convert a numeric score to a letter grade."""
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


def _control_status(score: float) -> ControlStatus:
    """Determine control status from score."""
    if score >= 80:
        return ControlStatus.COMPLIANT
    if score >= 40:
        return ControlStatus.PARTIAL
    return ControlStatus.NON_COMPLIANT


# ---------------------------------------------------------------------------
# Framework control definitions
# ---------------------------------------------------------------------------

_SOC2_CONTROLS = [
    ("CC6.1", "Logical Access Controls", "Access to systems is restricted to authorized users"),
    ("CC6.6", "Encryption in Transit", "Data in transit is protected using encryption"),
    ("CC6.7", "Encryption at Rest", "Data at rest is protected using encryption"),
    ("CC7.2", "System Monitoring", "Systems are monitored for anomalies and security events"),
    ("CC7.3", "Change Management", "Changes are managed through a controlled process"),
    ("CC8.1", "Incident Response", "Security incidents are identified and responded to"),
    ("A1.1", "Availability Commitment", "System availability meets defined commitments"),
    ("A1.2", "Redundancy", "Redundancy mechanisms support availability commitments"),
    ("A1.3", "Recovery", "Recovery mechanisms are tested and operational"),
    ("CC9.1", "Risk Mitigation", "Risks are identified and mitigated"),
]

_ISO27001_CONTROLS = [
    ("A.8.1", "Asset Management", "Information assets are identified and managed"),
    ("A.8.24", "Cryptography", "Cryptographic controls protect data confidentiality"),
    ("A.8.9", "Configuration Management", "Configurations are securely managed"),
    ("A.8.15", "Logging", "Events are logged for monitoring and forensics"),
    ("A.8.25", "Secure Development", "Security is integrated into the development lifecycle"),
    ("A.5.23", "Cloud Security", "Cloud service usage is managed securely"),
    ("A.8.6", "Capacity Management", "Capacity is managed to ensure availability"),
    ("A.5.29", "Business Continuity", "ICT continuity is planned and tested"),
    ("A.5.30", "ICT Readiness", "ICT is ready for business continuity"),
    ("A.8.14", "Redundancy", "Information processing facilities are redundant"),
]

_PCI_DSS_CONTROLS = [
    ("1.1", "Network Segmentation", "Network is segmented to isolate cardholder data"),
    ("2.1", "Secure Configuration", "Systems use secure default configurations"),
    ("3.1", "Data Protection", "Stored cardholder data is protected"),
    ("4.1", "Encryption in Transit", "Data is encrypted during transmission"),
    ("5.1", "Malware Protection", "Systems are protected against malware"),
    ("6.1", "Secure Development", "Security vulnerabilities are identified and addressed"),
    ("7.1", "Access Control", "Access to data is restricted by business need"),
    ("8.1", "Authentication", "Users are identified and authenticated"),
    ("10.1", "Audit Logging", "Access to system components is tracked and monitored"),
    ("11.1", "Security Testing", "Security systems and processes are regularly tested"),
]

_HIPAA_CONTROLS = [
    ("164.312(a)", "Access Control", "Technical safeguards for access to ePHI"),
    ("164.312(c)", "Integrity Controls", "Mechanisms to protect ePHI from alteration"),
    ("164.312(d)", "Authentication", "Person or entity authentication"),
    ("164.312(e)", "Transmission Security", "Encryption of ePHI in transit"),
    ("164.308(a)(1)", "Risk Analysis", "Conduct accurate risk assessments"),
    ("164.308(a)(5)", "Security Awareness", "Security awareness and training programs"),
    ("164.308(a)(6)", "Incident Response", "Security incident response procedures"),
    ("164.310(d)", "Device Controls", "Hardware and electronic media controls"),
    ("164.308(a)(7)", "Contingency Plan", "Data backup and disaster recovery plans"),
    ("164.312(b)", "Audit Controls", "Mechanisms to record and examine ePHI access"),
]

_NIST_CSF_CONTROLS = [
    ("ID.AM", "Asset Management", "Physical and software assets are identified"),
    ("ID.RA", "Risk Assessment", "Organizational risks are identified and assessed"),
    ("PR.AC", "Access Control", "Access to assets is managed and protected"),
    ("PR.DS", "Data Security", "Data is managed consistent with risk strategy"),
    ("PR.IP", "Protective Technology", "Security policies and procedures are maintained"),
    ("DE.AE", "Anomaly Detection", "Anomalous activity is detected"),
    ("DE.CM", "Continuous Monitoring", "Systems are monitored for security events"),
    ("RS.RP", "Response Planning", "Response processes and procedures are maintained"),
    ("RC.RP", "Recovery Planning", "Recovery processes and procedures are maintained"),
    ("RC.CO", "Recovery Communication", "Restoration activities are coordinated"),
]

_DORA_CONTROLS = [
    ("Art.5", "ICT Governance", "ICT risk management governance framework"),
    ("Art.6", "ICT Risk Framework", "ICT risk management framework is established"),
    ("Art.7", "ICT Systems", "ICT systems are identified and classified"),
    ("Art.9", "Protection", "ICT systems are protected and resilient"),
    ("Art.10", "Detection", "Anomalous activities are detected promptly"),
    ("Art.11", "Response & Recovery", "ICT-related incident response capabilities"),
    ("Art.17", "Incident Reporting", "Major ICT incidents are reported"),
    ("Art.24", "Resilience Testing", "Digital operational resilience testing program"),
    ("Art.28", "Third-Party Risk", "ICT third-party risk is managed"),
    ("Art.30", "Subcontracting", "ICT subcontracting arrangements are monitored"),
]

_FRAMEWORK_CONTROLS = {
    Framework.SOC2: _SOC2_CONTROLS,
    Framework.ISO27001: _ISO27001_CONTROLS,
    Framework.PCI_DSS: _PCI_DSS_CONTROLS,
    Framework.HIPAA: _HIPAA_CONTROLS,
    Framework.NIST_CSF: _NIST_CSF_CONTROLS,
    Framework.DORA: _DORA_CONTROLS,
}


class ComplianceScorecardEngine:
    """Score infrastructure against compliance frameworks."""

    def assess(
        self,
        graph: InfraGraph,
        frameworks: list[Framework] | None = None,
    ) -> ComplianceReport:
        """Assess infrastructure against specified compliance frameworks."""
        if frameworks is None:
            frameworks = list(Framework)

        scorecards: dict[str, FrameworkScorecard] = {}
        all_gaps: list[str] = []
        all_actions: list[str] = []

        for fw in frameworks:
            scorecard = self._assess_framework(graph, fw)
            scorecards[fw.value] = scorecard
            all_gaps.extend(scorecard.controls[i].gaps[0]
                           for i, c in enumerate(scorecard.controls)
                           if c.gaps)
            all_actions.extend(scorecard.controls[i].recommendations[0]
                              for i, c in enumerate(scorecard.controls)
                              if c.recommendations)

        # Overall score = average of framework scores
        fw_scores = [sc.overall_score for sc in scorecards.values()]
        overall = sum(fw_scores) / len(fw_scores) if fw_scores else 0

        # Deduplicate and limit
        seen_gaps: set[str] = set()
        unique_gaps: list[str] = []
        for g in all_gaps:
            if g not in seen_gaps:
                seen_gaps.add(g)
                unique_gaps.append(g)

        seen_actions: set[str] = set()
        unique_actions: list[str] = []
        for a in all_actions:
            if a not in seen_actions:
                seen_actions.add(a)
                unique_actions.append(a)

        return ComplianceReport(
            scorecards=scorecards,
            overall_score=round(overall, 1),
            overall_grade=_score_to_grade(overall),
            top_gaps=unique_gaps[:10],
            priority_actions=unique_actions[:10],
            component_count=len(graph.components),
            frameworks_assessed=len(frameworks),
        )

    def assess_single(
        self, graph: InfraGraph, framework: Framework
    ) -> FrameworkScorecard:
        """Assess infrastructure against a single framework."""
        return self._assess_framework(graph, framework)

    def compare_frameworks(
        self, graph: InfraGraph
    ) -> dict[str, dict]:
        """Compare scores across all frameworks."""
        report = self.assess(graph)
        result: dict[str, dict] = {}
        for fw_name, sc in report.scorecards.items():
            result[fw_name] = {
                "score": sc.overall_score,
                "grade": sc.grade,
                "compliant": sc.compliant_count,
                "partial": sc.partial_count,
                "non_compliant": sc.non_compliant_count,
            }
        return result

    def gap_analysis(
        self, graph: InfraGraph, framework: Framework
    ) -> list[dict]:
        """Return only non-compliant and partial controls with remediation."""
        scorecard = self._assess_framework(graph, framework)
        gaps = []
        for ctrl in scorecard.controls:
            if ctrl.status in (ControlStatus.NON_COMPLIANT, ControlStatus.PARTIAL):
                gaps.append({
                    "control_id": ctrl.control_id,
                    "control_name": ctrl.control_name,
                    "score": ctrl.score,
                    "status": ctrl.status.value,
                    "gaps": ctrl.gaps,
                    "recommendations": ctrl.recommendations,
                })
        return gaps

    def _assess_framework(
        self, graph: InfraGraph, framework: Framework
    ) -> FrameworkScorecard:
        """Assess a single compliance framework."""
        controls_def = _FRAMEWORK_CONTROLS[framework]
        assessments: list[ControlAssessment] = []

        for ctrl_id, ctrl_name, description in controls_def:
            assessment = self._assess_control(
                graph, framework, ctrl_id, ctrl_name, description
            )
            assessments.append(assessment)

        scores = [a.score for a in assessments if a.status != ControlStatus.NOT_APPLICABLE]
        overall = sum(scores) / len(scores) if scores else 0

        compliant = sum(1 for a in assessments if a.status == ControlStatus.COMPLIANT)
        partial = sum(1 for a in assessments if a.status == ControlStatus.PARTIAL)
        non_compliant = sum(1 for a in assessments if a.status == ControlStatus.NON_COMPLIANT)
        na = sum(1 for a in assessments if a.status == ControlStatus.NOT_APPLICABLE)

        summary_parts = []
        if non_compliant > 0:
            summary_parts.append(f"{non_compliant} controls require immediate attention")
        if partial > 0:
            summary_parts.append(f"{partial} controls are partially met")
        if compliant > 0:
            summary_parts.append(f"{compliant} controls are fully compliant")
        summary = ". ".join(summary_parts) + "." if summary_parts else "No controls assessed."

        return FrameworkScorecard(
            framework=framework,
            overall_score=round(overall, 1),
            controls=assessments,
            compliant_count=compliant,
            partial_count=partial,
            non_compliant_count=non_compliant,
            not_applicable_count=na,
            grade=_score_to_grade(overall),
            summary=summary,
        )

    def _assess_control(
        self,
        graph: InfraGraph,
        framework: Framework,
        ctrl_id: str,
        ctrl_name: str,
        description: str,
    ) -> ControlAssessment:
        """Assess a single control by analyzing infrastructure components."""
        evidence: list[ControlEvidence] = []
        gaps: list[str] = []
        recommendations: list[str] = []

        if not graph.components:
            return ControlAssessment(
                control_id=ctrl_id,
                control_name=ctrl_name,
                description=description,
                score=0,
                status=ControlStatus.NOT_APPLICABLE,
                evidence=[],
                gaps=["No infrastructure components to assess"],
                recommendations=["Load infrastructure configuration first"],
            )

        # Categorize control and score based on infrastructure analysis
        score = self._score_control(
            graph, framework, ctrl_id, ctrl_name, evidence, gaps, recommendations
        )

        return ControlAssessment(
            control_id=ctrl_id,
            control_name=ctrl_name,
            description=description,
            score=round(score, 1),
            status=_control_status(score),
            evidence=evidence,
            gaps=gaps,
            recommendations=recommendations,
        )

    def _score_control(
        self,
        graph: InfraGraph,
        framework: Framework,
        ctrl_id: str,
        ctrl_name: str,
        evidence: list[ControlEvidence],
        gaps: list[str],
        recommendations: list[str],
    ) -> float:
        """Score a control based on infrastructure analysis."""
        name_lower = ctrl_name.lower()
        components = list(graph.components.values())

        # ----- Encryption controls -----
        if "encrypt" in name_lower or "cryptograph" in name_lower:
            return self._score_encryption(
                components, ctrl_name, evidence, gaps, recommendations
            )

        # ----- Access control -----
        if "access control" in name_lower or "authentication" in name_lower:
            return self._score_access_control(
                components, evidence, gaps, recommendations
            )

        # ----- Monitoring / Logging / Audit -----
        if any(k in name_lower for k in ("monitor", "logging", "audit", "detection", "anomal")):
            return self._score_monitoring(
                components, evidence, gaps, recommendations
            )

        # ----- Redundancy / Availability -----
        if any(k in name_lower for k in ("redundanc", "availab", "capacity")):
            return self._score_redundancy(
                components, evidence, gaps, recommendations
            )

        # ----- Recovery / Continuity / Contingency -----
        if any(k in name_lower for k in ("recover", "continuity", "contingenc", "resilience")):
            return self._score_recovery(
                graph, components, evidence, gaps, recommendations
            )

        # ----- Change management -----
        if "change" in name_lower or "configuration" in name_lower:
            return self._score_change_management(
                components, evidence, gaps, recommendations
            )

        # ----- Network / Segmentation -----
        if "network" in name_lower or "segment" in name_lower:
            return self._score_network(
                components, evidence, gaps, recommendations
            )

        # ----- Incident response -----
        if "incident" in name_lower or "response" in name_lower:
            return self._score_incident_response(
                components, evidence, gaps, recommendations
            )

        # ----- Third-party (must be before Risk to catch "Third-Party Risk") -----
        if "third" in name_lower or "subcontract" in name_lower or "cloud" in name_lower:
            return self._score_third_party(
                components, evidence, gaps, recommendations
            )

        # ----- Risk / Governance -----
        if any(k in name_lower for k in ("risk", "governance", "asset")):
            return self._score_risk_governance(
                graph, components, evidence, gaps, recommendations
            )

        # ----- Default: security posture -----
        return self._score_general_security(
            components, evidence, gaps, recommendations
        )

    def _score_encryption(self, components, ctrl_name, evidence, gaps, recommendations) -> float:
        encrypted_count = 0
        total = len(components)
        name_lower = ctrl_name.lower()
        for comp in components:
            if "transit" in name_lower:
                if comp.security.encryption_in_transit:
                    encrypted_count += 1
                    evidence.append(ControlEvidence(
                        comp.id, comp.name, "Encryption in transit enabled", True
                    ))
                else:
                    evidence.append(ControlEvidence(
                        comp.id, comp.name, "Encryption in transit not enabled", False
                    ))
            else:
                if comp.security.encryption_at_rest:
                    encrypted_count += 1
                    evidence.append(ControlEvidence(
                        comp.id, comp.name, "Encryption at rest enabled", True
                    ))
                else:
                    evidence.append(ControlEvidence(
                        comp.id, comp.name, "Encryption at rest not enabled", False
                    ))

        score = (encrypted_count / total * 100) if total > 0 else 0
        if score < 100:
            gaps.append(f"{total - encrypted_count}/{total} components lack encryption")
            recommendations.append("Enable encryption for all components")
        return score

    def _score_access_control(self, components, evidence, gaps, recommendations) -> float:
        auth_count = 0
        total = len(components)
        for comp in components:
            if comp.security.auth_required:
                auth_count += 1
                evidence.append(ControlEvidence(
                    comp.id, comp.name, "Authentication required", True
                ))
            else:
                evidence.append(ControlEvidence(
                    comp.id, comp.name, "No authentication configured", False
                ))
        score = (auth_count / total * 100) if total > 0 else 0
        if score < 100:
            gaps.append(f"{total - auth_count}/{total} components lack authentication")
            recommendations.append("Configure authentication for all components")
        return score

    def _score_monitoring(self, components, evidence, gaps, recommendations) -> float:
        monitored = 0
        total = len(components)
        for comp in components:
            if comp.security.log_enabled or comp.security.ids_monitored:
                monitored += 1
                evidence.append(ControlEvidence(
                    comp.id, comp.name, "Logging/monitoring enabled", True
                ))
            else:
                evidence.append(ControlEvidence(
                    comp.id, comp.name, "No logging/monitoring configured", False
                ))
        score = (monitored / total * 100) if total > 0 else 0
        if score < 100:
            gaps.append(f"{total - monitored}/{total} components lack monitoring")
            recommendations.append("Enable logging and monitoring for all components")
        return score

    def _score_redundancy(self, components, evidence, gaps, recommendations) -> float:
        redundant = 0
        total = len(components)
        for comp in components:
            if comp.replicas > 1 or comp.failover.enabled:
                redundant += 1
                evidence.append(ControlEvidence(
                    comp.id, comp.name,
                    f"Redundant: {comp.replicas} replicas, failover={'enabled' if comp.failover.enabled else 'disabled'}",
                    True
                ))
            else:
                evidence.append(ControlEvidence(
                    comp.id, comp.name, "Single instance, no failover", False
                ))
        score = (redundant / total * 100) if total > 0 else 0
        if score < 100:
            gaps.append(f"{total - redundant}/{total} components lack redundancy")
            recommendations.append("Add replicas or enable failover for critical components")
        return score

    def _score_recovery(self, graph, components, evidence, gaps, recommendations) -> float:
        recovery_score = 0
        checks = 0

        for comp in components:
            checks += 1
            comp_score = 0
            if comp.security.backup_enabled:
                comp_score += 40
                evidence.append(ControlEvidence(
                    comp.id, comp.name, "Backups enabled", True
                ))
            if comp.failover.enabled:
                comp_score += 30
            if comp.replicas > 1:
                comp_score += 30
            recovery_score += min(100, comp_score)

        score = (recovery_score / checks) if checks > 0 else 0
        if score < 80:
            gaps.append("Recovery capabilities are insufficient")
            recommendations.append("Enable backups and failover for all critical components")
        return score

    def _score_change_management(self, components, evidence, gaps, recommendations) -> float:
        managed = 0
        total = len(components)
        for comp in components:
            if comp.compliance_tags.change_management:
                managed += 1
                evidence.append(ControlEvidence(
                    comp.id, comp.name, "Change management enabled", True
                ))
            else:
                evidence.append(ControlEvidence(
                    comp.id, comp.name, "No change management process", False
                ))
        score = (managed / total * 100) if total > 0 else 0
        if score < 100:
            gaps.append(f"{total - managed}/{total} components lack change management")
            recommendations.append("Implement change management processes")
        return score

    def _score_network(self, components, evidence, gaps, recommendations) -> float:
        segmented = 0
        total = len(components)
        for comp in components:
            if comp.security.network_segmented:
                segmented += 1
                evidence.append(ControlEvidence(
                    comp.id, comp.name, "Network segmented", True
                ))
            else:
                evidence.append(ControlEvidence(
                    comp.id, comp.name, "Not network segmented", False
                ))
        score = (segmented / total * 100) if total > 0 else 0
        if score < 100:
            gaps.append(f"{total - segmented}/{total} components lack network segmentation")
            recommendations.append("Implement network segmentation")
        return score

    def _score_incident_response(self, components, evidence, gaps, recommendations) -> float:
        # Score based on monitoring + runbook coverage + team readiness
        score = 0
        checks = 0
        for comp in components:
            checks += 1
            comp_score = 0
            if comp.security.log_enabled:
                comp_score += 30
            if comp.security.ids_monitored:
                comp_score += 30
            if comp.team.runbook_coverage_percent > 50:
                comp_score += 20
            if comp.team.oncall_coverage_hours >= 24:
                comp_score += 20
            score += min(100, comp_score)
            evidence.append(ControlEvidence(
                comp.id, comp.name,
                f"Incident readiness: logging={comp.security.log_enabled}, "
                f"IDS={comp.security.ids_monitored}, "
                f"runbook={comp.team.runbook_coverage_percent}%",
                comp_score >= 60,
            ))

        result = (score / checks) if checks > 0 else 0
        if result < 80:
            gaps.append("Incident response capabilities need improvement")
            recommendations.append("Improve logging, IDS, and runbook coverage")
        return result

    def _score_risk_governance(self, graph, components, evidence, gaps, recommendations) -> float:
        # Score based on: components documented, tagged, monitored
        score = 0
        total = len(components)
        for comp in components:
            comp_score = 0
            if comp.tags:
                comp_score += 25
            if comp.compliance_tags.data_classification != "internal":
                comp_score += 25
            if comp.security.log_enabled:
                comp_score += 25
            if comp.compliance_tags.audit_logging:
                comp_score += 25
            score += comp_score
            evidence.append(ControlEvidence(
                comp.id, comp.name,
                f"Governance: tags={bool(comp.tags)}, classified={comp.compliance_tags.data_classification}, audit={comp.compliance_tags.audit_logging}",
                comp_score >= 50,
            ))

        result = (score / total) if total > 0 else 0
        if result < 80:
            gaps.append("Risk governance controls need strengthening")
            recommendations.append("Tag and classify all components, enable audit logging")
        return result

    def _score_third_party(self, components, evidence, gaps, recommendations) -> float:
        external = [c for c in components if c.type == ComponentType.EXTERNAL_API]
        if not external:
            return 80  # No third parties = partial compliance (can't prove management)

        score = 0
        for comp in external:
            comp_score = 0
            if comp.failover.enabled:
                comp_score += 30
            if comp.replicas > 1:
                comp_score += 20
            if comp.security.rate_limiting:
                comp_score += 25
            if comp.security.encryption_in_transit:
                comp_score += 25
            score += comp_score
            evidence.append(ControlEvidence(
                comp.id, comp.name,
                f"Third-party: failover={comp.failover.enabled}, rate_limit={comp.security.rate_limiting}",
                comp_score >= 50,
            ))

        result = (score / len(external)) if external else 80
        if result < 80:
            gaps.append("Third-party risk management is insufficient")
            recommendations.append("Add failover, rate limiting, and encryption for external APIs")
        return result

    def _score_general_security(self, components, evidence, gaps, recommendations) -> float:
        score = 0
        total = len(components)
        for comp in components:
            comp_score = 0
            if comp.security.encryption_at_rest:
                comp_score += 20
            if comp.security.encryption_in_transit:
                comp_score += 20
            if comp.security.auth_required:
                comp_score += 20
            if comp.security.waf_protected:
                comp_score += 20
            if comp.security.rate_limiting:
                comp_score += 20
            score += comp_score

        result = (score / total) if total > 0 else 0
        if result < 80:
            gaps.append("General security posture needs improvement")
            recommendations.append("Review and strengthen security controls across all components")
        return result
