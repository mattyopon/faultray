# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Security Resilience Engine — Evaluate infrastructure security posture.

Analyzes security configurations, simulates attack scenarios,
and scores resilience against common threat patterns.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ThreatCategory(str, Enum):
    DDOS = "ddos"
    DATA_BREACH = "data_breach"
    RANSOMWARE = "ransomware"
    INSIDER_THREAT = "insider_threat"
    SUPPLY_CHAIN = "supply_chain"
    API_ABUSE = "api_abuse"
    CREDENTIAL_STUFFING = "credential_stuffing"
    LATERAL_MOVEMENT = "lateral_movement"


class SecurityControl(str, Enum):
    ENCRYPTION_AT_REST = "encryption_at_rest"
    ENCRYPTION_IN_TRANSIT = "encryption_in_transit"
    WAF = "waf"
    RATE_LIMITING = "rate_limiting"
    MFA = "mfa"
    NETWORK_SEGMENTATION = "network_segmentation"
    BACKUP_ENCRYPTION = "backup_encryption"
    SECRET_ROTATION = "secret_rotation"
    LEAST_PRIVILEGE = "least_privilege"
    AUDIT_LOGGING = "audit_logging"
    INTRUSION_DETECTION = "intrusion_detection"
    DLP = "dlp"


class RiskLevel(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    MINIMAL = "minimal"


@dataclass
class SecurityProfile:
    """Security configuration for a component."""
    controls: list[SecurityControl] = field(default_factory=list)
    public_facing: bool = False
    stores_pii: bool = False
    stores_financial: bool = False
    authentication_required: bool = True
    network_zone: str = "private"  # public, dmz, private, restricted


@dataclass
class ThreatAssessment:
    """Assessment of a specific threat against infrastructure."""
    threat: ThreatCategory
    risk_level: RiskLevel
    likelihood_score: float  # 0-10
    impact_score: float  # 0-10
    overall_score: float  # 0-100
    vulnerable_components: list[str] = field(default_factory=list)
    missing_controls: list[SecurityControl] = field(default_factory=list)
    mitigations: list[str] = field(default_factory=list)


@dataclass
class SecurityScorecard:
    """Overall security resilience scorecard."""
    overall_score: float  # 0-100
    grade: str  # A+ to F
    threat_assessments: list[ThreatAssessment] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    compliance_gaps: list[str] = field(default_factory=list)
    control_coverage: dict[str, bool] = field(default_factory=dict)


class SecurityResilienceEngine:
    """Evaluate infrastructure security posture and attack resilience."""

    # Define which controls mitigate which threats
    THREAT_CONTROLS: dict[ThreatCategory, list[SecurityControl]] = {
        ThreatCategory.DDOS: [SecurityControl.WAF, SecurityControl.RATE_LIMITING],
        ThreatCategory.DATA_BREACH: [
            SecurityControl.ENCRYPTION_AT_REST, SecurityControl.ENCRYPTION_IN_TRANSIT,
            SecurityControl.DLP, SecurityControl.AUDIT_LOGGING,
        ],
        ThreatCategory.RANSOMWARE: [
            SecurityControl.BACKUP_ENCRYPTION, SecurityControl.NETWORK_SEGMENTATION,
            SecurityControl.LEAST_PRIVILEGE,
        ],
        ThreatCategory.INSIDER_THREAT: [
            SecurityControl.LEAST_PRIVILEGE, SecurityControl.AUDIT_LOGGING,
            SecurityControl.DLP, SecurityControl.MFA,
        ],
        ThreatCategory.SUPPLY_CHAIN: [
            SecurityControl.NETWORK_SEGMENTATION, SecurityControl.INTRUSION_DETECTION,
        ],
        ThreatCategory.API_ABUSE: [
            SecurityControl.RATE_LIMITING, SecurityControl.WAF,
            SecurityControl.AUDIT_LOGGING,
        ],
        ThreatCategory.CREDENTIAL_STUFFING: [
            SecurityControl.MFA, SecurityControl.RATE_LIMITING,
        ],
        ThreatCategory.LATERAL_MOVEMENT: [
            SecurityControl.NETWORK_SEGMENTATION, SecurityControl.LEAST_PRIVILEGE,
            SecurityControl.INTRUSION_DETECTION,
        ],
    }

    def __init__(self):
        self.component_profiles: dict[str, SecurityProfile] = {}

    def set_component_profile(self, component_id: str, profile: SecurityProfile) -> None:
        self.component_profiles[component_id] = profile

    def assess_threat(self, threat: ThreatCategory) -> ThreatAssessment:
        """Assess risk level for a specific threat category."""
        required_controls = self.THREAT_CONTROLS.get(threat, [])
        all_controls = set()
        vulnerable = []

        for comp_id, profile in self.component_profiles.items():
            all_controls.update(profile.controls)
            comp_controls = set(profile.controls)
            missing = [c for c in required_controls if c not in comp_controls]
            if missing and (profile.public_facing or profile.stores_pii):
                vulnerable.append(comp_id)

        missing_controls = [c for c in required_controls if c not in all_controls]
        coverage = len([c for c in required_controls if c in all_controls])
        total = len(required_controls) if required_controls else 1

        coverage_ratio = coverage / total
        likelihood = round(10 * (1 - coverage_ratio), 1)

        # Impact based on data sensitivity
        impact_factors = []
        for profile in self.component_profiles.values():
            if profile.stores_financial:
                impact_factors.append(9)
            elif profile.stores_pii:
                impact_factors.append(7)
            elif profile.public_facing:
                impact_factors.append(5)
            else:
                impact_factors.append(3)

        impact = round(max(impact_factors) if impact_factors else 5, 1)
        overall = round((likelihood * impact) / 10 * 100, 1)
        overall = min(overall, 100)

        # Determine risk level
        if overall >= 70:
            risk = RiskLevel.CRITICAL
        elif overall >= 50:
            risk = RiskLevel.HIGH
        elif overall >= 30:
            risk = RiskLevel.MEDIUM
        elif overall >= 10:
            risk = RiskLevel.LOW
        else:
            risk = RiskLevel.MINIMAL

        mitigations = []
        for ctrl in missing_controls:
            mitigations.append(f"Implement {ctrl.value} to mitigate {threat.value} risk")

        return ThreatAssessment(
            threat=threat,
            risk_level=risk,
            likelihood_score=likelihood,
            impact_score=impact,
            overall_score=overall,
            vulnerable_components=vulnerable,
            missing_controls=missing_controls,
            mitigations=mitigations,
        )

    def generate_scorecard(self) -> SecurityScorecard:
        """Generate comprehensive security scorecard."""
        assessments = [self.assess_threat(t) for t in ThreatCategory]

        avg_score = sum(a.overall_score for a in assessments) / len(assessments) if assessments else 0
        # Invert: higher score = worse, we want higher = better
        security_score = round(100 - avg_score, 1)
        security_score = max(0, min(100, security_score))

        # Grade
        if security_score >= 95:
            grade = "A+"
        elif security_score >= 90:
            grade = "A"
        elif security_score >= 85:
            grade = "A-"
        elif security_score >= 80:
            grade = "B+"
        elif security_score >= 75:
            grade = "B"
        elif security_score >= 70:
            grade = "B-"
        elif security_score >= 65:
            grade = "C+"
        elif security_score >= 60:
            grade = "C"
        elif security_score >= 50:
            grade = "D"
        else:
            grade = "F"

        # Control coverage
        all_controls = set()
        for profile in self.component_profiles.values():
            all_controls.update(profile.controls)
        coverage = {c.value: c in all_controls for c in SecurityControl}

        # Strengths & weaknesses
        strengths = [c.value for c in SecurityControl if c in all_controls]
        weaknesses = [c.value for c in SecurityControl if c not in all_controls]

        [a for a in assessments if a.risk_level == RiskLevel.CRITICAL]
        recs = []
        for a in sorted(assessments, key=lambda x: x.overall_score, reverse=True)[:3]:
            if a.mitigations:
                recs.extend(a.mitigations[:2])

        return SecurityScorecard(
            overall_score=security_score,
            grade=grade,
            threat_assessments=assessments,
            strengths=strengths[:5],
            weaknesses=weaknesses[:5],
            recommendations=recs[:5],
            control_coverage=coverage,
        )
