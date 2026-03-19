"""DORA (Digital Operational Resilience Act) Compliance Evidence Engine.

Automatically generates audit-ready evidence for EU financial regulation DORA
(Regulation (EU) 2022/2554, effective January 2025). Maps infrastructure state
and chaos test results to DORA articles and generates structured audit trails.

Coverage:
  - Pillar 1: ICT Risk Management (Art. 5-16)
  - Pillar 2: Incident Management (Art. 17-23) — interface/stub
  - Pillar 3: Resilience Testing (Art. 24-27)
  - Pillar 4: Third-Party Risk (Art. 28-30)
  - Pillar 5: Information Sharing (Art. 45)

Regulatory Technical Standards (RTS) referenced:
  - RTS 2024/1774: ICT risk management framework details
  - ITS 2024/2956: Register of information template format
  - RTS 2025/301: Incident reporting content and timeline

This module is the core evaluator. Higher-level report formatting lives in
``faultray.reporter.dora_audit_report``.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from enum import Enum

from pydantic import BaseModel, Field

from faultray.model.components import Component, ComponentType, HealthStatus
from faultray.model.graph import InfraGraph


# =====================================================================
# Enums
# =====================================================================


class DORAArticle(str, Enum):
    """DORA regulation articles covered by the evidence engine.

    Organised by pillar for clarity. The original five articles are preserved
    as-is; new articles extend the enum.
    """

    # Pillar 1 — ICT Risk Management
    ARTICLE_5 = "article_5"    # ICT risk management framework
    ARTICLE_6 = "article_6"    # ICT risk management framework — governance
    ARTICLE_7 = "article_7"    # ICT systems, protocols and tools
    ARTICLE_8 = "article_8"    # Identification
    ARTICLE_9 = "article_9"    # Protection and prevention
    ARTICLE_10 = "article_10"  # Detection
    ARTICLE_11 = "article_11"  # Response and recovery / testing
    ARTICLE_12 = "article_12"  # Backup policies and recovery
    ARTICLE_13 = "article_13"  # Learning and evolving
    ARTICLE_14 = "article_14"  # Communication
    ARTICLE_15 = "article_15"  # Simplified ICT risk management (smaller entities)
    ARTICLE_16 = "article_16"  # Further harmonisation via RTS

    # Pillar 2 — Incident Management (stub/interface)
    ARTICLE_17 = "article_17"  # ICT-related incident management process
    ARTICLE_18 = "article_18"  # Classification of ICT-related incidents
    ARTICLE_19 = "article_19"  # Reporting of major ICT-related incidents
    ARTICLE_20 = "article_20"  # Harmonisation of reporting content/templates
    ARTICLE_21 = "article_21"  # Centralisation of incident reporting
    ARTICLE_22 = "article_22"  # Supervisory feedback
    ARTICLE_23 = "article_23"  # Operational/security payment incidents

    # Pillar 3 — Resilience Testing
    ARTICLE_24 = "article_24"  # General requirements for testing
    ARTICLE_25 = "article_25"  # TLPT (Threat-Led Penetration Testing)
    ARTICLE_26 = "article_26"  # Requirements for testers
    ARTICLE_27 = "article_27"  # Mutual recognition of TLPT

    # Pillar 4 — Third-Party Risk
    ARTICLE_28 = "article_28"  # Key principles for ICT third-party risk
    ARTICLE_29 = "article_29"  # Preliminary assessment of ICT concentration risk
    ARTICLE_30 = "article_30"  # Key contractual provisions

    # Pillar 5 — Information Sharing
    ARTICLE_45 = "article_45"  # Arrangements for sharing cyber-threat info


class DORAPillar(str, Enum):
    """The five pillars of DORA for grouping."""

    ICT_RISK_MANAGEMENT = "ict_risk_management"
    INCIDENT_MANAGEMENT = "incident_management"
    RESILIENCE_TESTING = "resilience_testing"
    THIRD_PARTY_RISK = "third_party_risk"
    INFORMATION_SHARING = "information_sharing"


class TestClassification(str, Enum):
    """Classification of test types under DORA."""

    BASIC_TESTING = "basic_testing"
    ADVANCED_TESTING = "advanced_testing"
    TLPT = "tlpt"  # Threat-Led Penetration Testing


class EvidenceStatus(str, Enum):
    """Compliance status for a DORA control."""

    COMPLIANT = "compliant"
    PARTIALLY_COMPLIANT = "partially_compliant"
    NON_COMPLIANT = "non_compliant"
    NOT_APPLICABLE = "not_applicable"


class EvaluationMethod(str, Enum):
    """How a control was evaluated — helps auditors assess confidence."""

    AUTOMATED = "automated"                # Fully checked by infrastructure analysis
    PARTIAL_AUTOMATED = "partial_automated" # Some checks automated, some require manual
    MANUAL_REQUIRED = "manual_required"     # Requires human/organisational verification
    EXTERNAL_ASSESSMENT = "external_assessment"  # Requires external party (e.g. TLPT)
    STUB = "stub"                          # Interface only — not yet automatable


# =====================================================================
# Pydantic Models (backwards-compatible, extended)
# =====================================================================


class DORAControl(BaseModel):
    """A single DORA compliance control."""

    article: DORAArticle
    control_id: str
    description: str
    test_requirements: list[str] = Field(default_factory=list)
    # --- New fields (all optional for backwards compatibility) ---
    pillar: DORAPillar = DORAPillar.ICT_RISK_MANAGEMENT
    rts_references: list[str] = Field(default_factory=list)
    evaluation_method: EvaluationMethod = EvaluationMethod.AUTOMATED
    default_risk_weight: float = 1.0
    remediation_deadline_days: int = 90


class EvidenceRecord(BaseModel):
    """An audit evidence record from a chaos test."""

    control_id: str
    timestamp: datetime
    test_type: str
    test_description: str
    result: str  # pass, fail, partial
    severity: str  # critical, high, medium, low
    remediation_required: bool = False
    artifacts: list[str] = Field(default_factory=list)


class DORAGapAnalysis(BaseModel):
    """Gap analysis for a single DORA control."""

    control_id: str
    status: EvidenceStatus
    gaps: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    risk_score: float = 0.0  # 0.0 (no risk) to 1.0 (critical risk)
    # --- New fields ---
    evaluation_method: EvaluationMethod = EvaluationMethod.AUTOMATED
    rts_references: list[str] = Field(default_factory=list)
    evidence_items: list[str] = Field(default_factory=list)


class DORAComplianceReport(BaseModel):
    """Complete DORA compliance report."""

    overall_status: EvidenceStatus
    article_results: dict[str, EvidenceStatus] = Field(default_factory=dict)
    gap_analyses: list[DORAGapAnalysis] = Field(default_factory=list)
    evidence_records: list[EvidenceRecord] = Field(default_factory=list)
    report_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    next_review_date: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc) + timedelta(days=90)
    )
    # --- New fields ---
    pillar_results: dict[str, EvidenceStatus] = Field(default_factory=dict)


# =====================================================================
# Risk configuration (no more hardcoded values)
# =====================================================================


class RiskConfig(BaseModel):
    """Configurable risk weights and remediation deadlines.

    Financial institutions can override these defaults to match their
    own risk appetite and regulatory expectations.
    """

    # Per-pillar risk weights (how much each pillar contributes to overall score)
    pillar_weights: dict[str, float] = Field(default_factory=lambda: {
        DORAPillar.ICT_RISK_MANAGEMENT.value: 0.30,
        DORAPillar.INCIDENT_MANAGEMENT.value: 0.15,
        DORAPillar.RESILIENCE_TESTING.value: 0.25,
        DORAPillar.THIRD_PARTY_RISK.value: 0.25,
        DORAPillar.INFORMATION_SHARING.value: 0.05,
    })

    # Remediation deadline days by severity
    remediation_deadlines: dict[str, int] = Field(default_factory=lambda: {
        "critical": 30,
        "high": 60,
        "medium": 90,
        "low": 180,
    })

    # Thresholds for status determination
    non_compliant_threshold: float = 0.5  # risk >= this -> NON_COMPLIANT
    partial_compliant_threshold: float = 0.01  # risk >= this -> PARTIALLY_COMPLIANT

    # Concentration risk: Herfindahl-Hirschman Index threshold
    hhi_concentration_threshold: float = 0.25  # HHI above this = high concentration

    # Minimum replicas for redundancy
    min_replicas_for_redundancy: int = 2

    # Backup frequency threshold (hours)
    max_backup_frequency_hours: float = 24.0

    # Test frequency threshold (days since last test)
    max_test_age_days: int = 90


# =====================================================================
# Article-to-pillar mapping
# =====================================================================

_ARTICLE_PILLAR_MAP: dict[DORAArticle, DORAPillar] = {
    DORAArticle.ARTICLE_5: DORAPillar.ICT_RISK_MANAGEMENT,
    DORAArticle.ARTICLE_6: DORAPillar.ICT_RISK_MANAGEMENT,
    DORAArticle.ARTICLE_7: DORAPillar.ICT_RISK_MANAGEMENT,
    DORAArticle.ARTICLE_8: DORAPillar.ICT_RISK_MANAGEMENT,
    DORAArticle.ARTICLE_9: DORAPillar.ICT_RISK_MANAGEMENT,
    DORAArticle.ARTICLE_10: DORAPillar.ICT_RISK_MANAGEMENT,
    DORAArticle.ARTICLE_11: DORAPillar.ICT_RISK_MANAGEMENT,
    DORAArticle.ARTICLE_12: DORAPillar.ICT_RISK_MANAGEMENT,
    DORAArticle.ARTICLE_13: DORAPillar.ICT_RISK_MANAGEMENT,
    DORAArticle.ARTICLE_14: DORAPillar.ICT_RISK_MANAGEMENT,
    DORAArticle.ARTICLE_15: DORAPillar.ICT_RISK_MANAGEMENT,
    DORAArticle.ARTICLE_16: DORAPillar.ICT_RISK_MANAGEMENT,
    DORAArticle.ARTICLE_17: DORAPillar.INCIDENT_MANAGEMENT,
    DORAArticle.ARTICLE_18: DORAPillar.INCIDENT_MANAGEMENT,
    DORAArticle.ARTICLE_19: DORAPillar.INCIDENT_MANAGEMENT,
    DORAArticle.ARTICLE_20: DORAPillar.INCIDENT_MANAGEMENT,
    DORAArticle.ARTICLE_21: DORAPillar.INCIDENT_MANAGEMENT,
    DORAArticle.ARTICLE_22: DORAPillar.INCIDENT_MANAGEMENT,
    DORAArticle.ARTICLE_23: DORAPillar.INCIDENT_MANAGEMENT,
    DORAArticle.ARTICLE_24: DORAPillar.RESILIENCE_TESTING,
    DORAArticle.ARTICLE_25: DORAPillar.RESILIENCE_TESTING,
    DORAArticle.ARTICLE_26: DORAPillar.RESILIENCE_TESTING,
    DORAArticle.ARTICLE_27: DORAPillar.RESILIENCE_TESTING,
    DORAArticle.ARTICLE_28: DORAPillar.THIRD_PARTY_RISK,
    DORAArticle.ARTICLE_29: DORAPillar.THIRD_PARTY_RISK,
    DORAArticle.ARTICLE_30: DORAPillar.THIRD_PARTY_RISK,
    DORAArticle.ARTICLE_45: DORAPillar.INFORMATION_SHARING,
}


# =====================================================================
# Built-in DORA controls — each with unique evaluation semantics
# =====================================================================

_DORA_CONTROLS: list[dict] = [
    # ---------------------------------------------------------------
    # Pillar 1: ICT Risk Management (Art. 5-16)
    # ---------------------------------------------------------------

    # Art. 5 — ICT risk management framework
    {
        "article": "article_5", "control_id": "DORA-5.01",
        "description": "ICT risk management framework is established and maintained",
        "test_requirements": ["Framework documentation exists", "Governance structure defined"],
        "pillar": "ict_risk_management",
        "rts_references": ["RTS 2024/1774 Art. 1-3"],
        "evaluation_method": "manual_required",
        "default_risk_weight": 1.0,
        "remediation_deadline_days": 60,
    },

    # Art. 6 — Governance
    {
        "article": "article_6", "control_id": "DORA-6.01",
        "description": "Management body defines and approves ICT risk management strategy",
        "test_requirements": ["Board-level oversight documented", "Risk appetite statement"],
        "pillar": "ict_risk_management",
        "rts_references": ["RTS 2024/1774 Art. 4"],
        "evaluation_method": "manual_required",
        "default_risk_weight": 1.0,
        "remediation_deadline_days": 60,
    },

    # Art. 7 — ICT systems, protocols and tools
    {
        "article": "article_7", "control_id": "DORA-7.01",
        "description": "ICT systems are reliable, have sufficient capacity and are resilient",
        "test_requirements": ["Capacity headroom assessment", "System reliability metrics"],
        "pillar": "ict_risk_management",
        "rts_references": ["RTS 2024/1774 Art. 5-7"],
        "evaluation_method": "automated",
        "default_risk_weight": 1.2,
        "remediation_deadline_days": 60,
    },
    {
        "article": "article_7", "control_id": "DORA-7.02",
        "description": "ICT systems are kept up to date with patches and security updates",
        "test_requirements": ["Patch SLA compliance", "Vulnerability window measurement"],
        "pillar": "ict_risk_management",
        "rts_references": ["RTS 2024/1774 Art. 5"],
        "evaluation_method": "partial_automated",
        "default_risk_weight": 1.1,
        "remediation_deadline_days": 30,
    },

    # Art. 8 — Identification
    {
        "article": "article_8", "control_id": "DORA-8.01",
        "description": "All ICT assets and dependencies are identified and documented",
        "test_requirements": ["Asset inventory completeness", "Dependency mapping"],
        "pillar": "ict_risk_management",
        "rts_references": ["RTS 2024/1774 Art. 8"],
        "evaluation_method": "automated",
        "default_risk_weight": 1.0,
        "remediation_deadline_days": 60,
    },
    {
        "article": "article_8", "control_id": "DORA-8.02",
        "description": "Critical or important functions are identified",
        "test_requirements": ["Criticality classification", "Business impact analysis"],
        "pillar": "ict_risk_management",
        "rts_references": ["RTS 2024/1774 Art. 8"],
        "evaluation_method": "partial_automated",
        "default_risk_weight": 1.0,
        "remediation_deadline_days": 60,
    },

    # Art. 9 — Protection and prevention
    {
        "article": "article_9", "control_id": "DORA-9.01",
        "description": "Encryption mechanisms protect data at rest and in transit",
        "test_requirements": ["TLS/mTLS configuration check", "Encryption at rest verification"],
        "pillar": "ict_risk_management",
        "rts_references": ["RTS 2024/1774 Art. 9"],
        "evaluation_method": "automated",
        "default_risk_weight": 1.2,
        "remediation_deadline_days": 30,
    },
    {
        "article": "article_9", "control_id": "DORA-9.02",
        "description": "Access controls and authentication mechanisms are in place",
        "test_requirements": ["Auth configuration check", "Rate limiting verification"],
        "pillar": "ict_risk_management",
        "rts_references": ["RTS 2024/1774 Art. 9"],
        "evaluation_method": "automated",
        "default_risk_weight": 1.2,
        "remediation_deadline_days": 30,
    },
    {
        "article": "article_9", "control_id": "DORA-9.03",
        "description": "Network segmentation and perimeter protection are implemented",
        "test_requirements": ["Network segmentation check", "WAF/firewall presence"],
        "pillar": "ict_risk_management",
        "rts_references": ["RTS 2024/1774 Art. 9"],
        "evaluation_method": "automated",
        "default_risk_weight": 1.1,
        "remediation_deadline_days": 60,
    },

    # Art. 10 — Detection
    {
        "article": "article_10", "control_id": "DORA-10.01",
        "description": "Anomalous activity detection mechanisms are in place",
        "test_requirements": ["Monitoring system presence", "Alerting configuration"],
        "pillar": "ict_risk_management",
        "rts_references": ["RTS 2024/1774 Art. 10"],
        "evaluation_method": "automated",
        "default_risk_weight": 1.1,
        "remediation_deadline_days": 60,
    },
    {
        "article": "article_10", "control_id": "DORA-10.02",
        "description": "Audit logging is enabled for critical systems",
        "test_requirements": ["Log collection verification", "Audit trail completeness"],
        "pillar": "ict_risk_management",
        "rts_references": ["RTS 2024/1774 Art. 10"],
        "evaluation_method": "automated",
        "default_risk_weight": 1.0,
        "remediation_deadline_days": 60,
    },

    # Art. 11 — Response and recovery / testing (original 6 controls)
    {
        "article": "article_11", "control_id": "DORA-11.01",
        "description": "ICT systems and tools are periodically tested for resilience",
        "test_requirements": ["Periodic resilience testing", "Test coverage of critical systems"],
        "pillar": "ict_risk_management",
        "rts_references": ["RTS 2024/1774 Art. 11"],
        "evaluation_method": "automated",
        "default_risk_weight": 1.2,
        "remediation_deadline_days": 60,
    },
    {
        "article": "article_11", "control_id": "DORA-11.02",
        "description": "Vulnerability assessments and scans are performed",
        "test_requirements": ["Vulnerability scanning", "Security assessment"],
        "pillar": "ict_risk_management",
        "rts_references": ["RTS 2024/1774 Art. 11"],
        "evaluation_method": "partial_automated",
        "default_risk_weight": 1.2,
        "remediation_deadline_days": 30,
    },
    {
        "article": "article_11", "control_id": "DORA-11.03",
        "description": "Network security tests are conducted",
        "test_requirements": ["Network security testing", "Firewall validation"],
        "pillar": "ict_risk_management",
        "rts_references": ["RTS 2024/1774 Art. 11"],
        "evaluation_method": "automated",
        "default_risk_weight": 1.1,
        "remediation_deadline_days": 60,
    },
    {
        "article": "article_11", "control_id": "DORA-11.04",
        "description": "Compatibility and performance testing under stress",
        "test_requirements": ["Stress testing", "Performance benchmarks"],
        "pillar": "ict_risk_management",
        "rts_references": ["RTS 2024/1774 Art. 11"],
        "evaluation_method": "automated",
        "default_risk_weight": 1.1,
        "remediation_deadline_days": 60,
    },
    {
        "article": "article_11", "control_id": "DORA-11.05",
        "description": "Scenario-based tests including failover and switchover",
        "test_requirements": ["Failover testing", "Switchover testing", "DR simulation"],
        "pillar": "ict_risk_management",
        "rts_references": ["RTS 2024/1774 Art. 11"],
        "evaluation_method": "automated",
        "default_risk_weight": 1.3,
        "remediation_deadline_days": 60,
    },
    {
        "article": "article_11", "control_id": "DORA-11.06",
        "description": "Source code reviews where applicable",
        "test_requirements": ["Code review", "Static analysis"],
        "pillar": "ict_risk_management",
        "rts_references": ["RTS 2024/1774 Art. 11"],
        "evaluation_method": "partial_automated",
        "default_risk_weight": 0.9,
        "remediation_deadline_days": 90,
    },

    # Art. 12 — Backup policies and recovery
    {
        "article": "article_12", "control_id": "DORA-12.01",
        "description": "Backup policies cover all critical ICT systems",
        "test_requirements": ["Backup configuration check", "RPO validation"],
        "pillar": "ict_risk_management",
        "rts_references": ["RTS 2024/1774 Art. 12"],
        "evaluation_method": "automated",
        "default_risk_weight": 1.3,
        "remediation_deadline_days": 30,
    },
    {
        "article": "article_12", "control_id": "DORA-12.02",
        "description": "Recovery and restoration procedures are established and tested",
        "test_requirements": ["RTO validation", "DR region configuration"],
        "pillar": "ict_risk_management",
        "rts_references": ["RTS 2024/1774 Art. 12"],
        "evaluation_method": "automated",
        "default_risk_weight": 1.3,
        "remediation_deadline_days": 30,
    },

    # Art. 13 — Learning and evolving
    {
        "article": "article_13", "control_id": "DORA-13.01",
        "description": "Lessons learned from incidents and tests are incorporated",
        "test_requirements": ["Post-incident review process", "Test result incorporation"],
        "pillar": "ict_risk_management",
        "rts_references": ["RTS 2024/1774 Art. 13"],
        "evaluation_method": "manual_required",
        "default_risk_weight": 0.8,
        "remediation_deadline_days": 90,
    },

    # Art. 14 — Communication
    {
        "article": "article_14", "control_id": "DORA-14.01",
        "description": "Crisis communication plans are documented and tested",
        "test_requirements": ["Communication plan existence", "Stakeholder notification"],
        "pillar": "ict_risk_management",
        "rts_references": ["RTS 2024/1774 Art. 14"],
        "evaluation_method": "manual_required",
        "default_risk_weight": 0.7,
        "remediation_deadline_days": 90,
    },

    # Art. 15 — Simplified framework (smaller entities) - single control
    {
        "article": "article_15", "control_id": "DORA-15.01",
        "description": "Simplified ICT risk management framework for smaller entities",
        "test_requirements": ["Proportionality assessment"],
        "pillar": "ict_risk_management",
        "rts_references": [],
        "evaluation_method": "manual_required",
        "default_risk_weight": 0.5,
        "remediation_deadline_days": 180,
    },

    # Art. 16 — Further harmonisation
    {
        "article": "article_16", "control_id": "DORA-16.01",
        "description": "RTS alignment for ICT risk management framework",
        "test_requirements": ["RTS compliance verification"],
        "pillar": "ict_risk_management",
        "rts_references": ["RTS 2024/1774"],
        "evaluation_method": "manual_required",
        "default_risk_weight": 0.5,
        "remediation_deadline_days": 180,
    },

    # ---------------------------------------------------------------
    # Pillar 2: Incident Management (Art. 17-23) — stub/interface
    # ---------------------------------------------------------------

    {
        "article": "article_17", "control_id": "DORA-17.01",
        "description": "ICT incident management process is established",
        "test_requirements": ["Incident process documentation", "Escalation procedures"],
        "pillar": "incident_management",
        "rts_references": ["RTS 2025/301 Art. 1-3"],
        "evaluation_method": "stub",
        "default_risk_weight": 1.0,
        "remediation_deadline_days": 60,
    },
    {
        "article": "article_18", "control_id": "DORA-18.01",
        "description": "ICT incidents are classified by severity and impact",
        "test_requirements": ["Classification taxonomy", "Severity thresholds"],
        "pillar": "incident_management",
        "rts_references": ["RTS 2025/301 Art. 4-6"],
        "evaluation_method": "stub",
        "default_risk_weight": 1.0,
        "remediation_deadline_days": 60,
    },
    {
        "article": "article_19", "control_id": "DORA-19.01",
        "description": "Major ICT-related incidents are reported to competent authorities",
        "test_requirements": ["Reporting procedures", "Timeline compliance"],
        "pillar": "incident_management",
        "rts_references": ["RTS 2025/301 Art. 7-10"],
        "evaluation_method": "stub",
        "default_risk_weight": 1.2,
        "remediation_deadline_days": 30,
    },
    {
        "article": "article_20", "control_id": "DORA-20.01",
        "description": "Incident reports follow harmonised content and templates",
        "test_requirements": ["Report template compliance", "Content completeness"],
        "pillar": "incident_management",
        "rts_references": ["ITS 2024/2956", "RTS 2025/301"],
        "evaluation_method": "stub",
        "default_risk_weight": 0.8,
        "remediation_deadline_days": 90,
    },
    {
        "article": "article_21", "control_id": "DORA-21.01",
        "description": "Incident reporting feeds into centralised EU hub",
        "test_requirements": ["Centralised reporting capability"],
        "pillar": "incident_management",
        "rts_references": [],
        "evaluation_method": "stub",
        "default_risk_weight": 0.6,
        "remediation_deadline_days": 180,
    },
    {
        "article": "article_22", "control_id": "DORA-22.01",
        "description": "Supervisory feedback on incident reports is acted upon",
        "test_requirements": ["Feedback loop documentation"],
        "pillar": "incident_management",
        "rts_references": [],
        "evaluation_method": "stub",
        "default_risk_weight": 0.5,
        "remediation_deadline_days": 180,
    },
    {
        "article": "article_23", "control_id": "DORA-23.01",
        "description": "Operational and security payment incidents reported",
        "test_requirements": ["Payment incident classification", "PSD2 alignment"],
        "pillar": "incident_management",
        "rts_references": [],
        "evaluation_method": "stub",
        "default_risk_weight": 0.8,
        "remediation_deadline_days": 60,
    },

    # ---------------------------------------------------------------
    # Pillar 3: Resilience Testing (Art. 24-27)
    # ---------------------------------------------------------------

    # Art. 24 — General requirements
    {
        "article": "article_24", "control_id": "DORA-24.01",
        "description": "Testing programme is risk-based and proportionate",
        "test_requirements": ["Risk-based test planning", "Proportionality assessment"],
        "pillar": "resilience_testing",
        "rts_references": [],
        "evaluation_method": "automated",
        "default_risk_weight": 1.2,
        "remediation_deadline_days": 60,
    },
    {
        "article": "article_24", "control_id": "DORA-24.02",
        "description": "Testing covers all critical ICT systems",
        "test_requirements": ["Critical system identification", "Test completeness"],
        "pillar": "resilience_testing",
        "rts_references": [],
        "evaluation_method": "automated",
        "default_risk_weight": 1.2,
        "remediation_deadline_days": 60,
    },
    {
        "article": "article_24", "control_id": "DORA-24.03",
        "description": "Test results are documented and reported",
        "test_requirements": ["Test documentation", "Result reporting"],
        "pillar": "resilience_testing",
        "rts_references": [],
        "evaluation_method": "partial_automated",
        "default_risk_weight": 0.8,
        "remediation_deadline_days": 90,
    },
    {
        "article": "article_24", "control_id": "DORA-24.04",
        "description": "Identified issues are remediated in a timely manner",
        "test_requirements": ["Remediation tracking", "Timeline adherence"],
        "pillar": "resilience_testing",
        "rts_references": [],
        "evaluation_method": "partial_automated",
        "default_risk_weight": 1.0,
        "remediation_deadline_days": 60,
    },
    {
        "article": "article_24", "control_id": "DORA-24.05",
        "description": "Testing frequency is adequate for risk profile",
        "test_requirements": ["Test scheduling", "Frequency validation"],
        "pillar": "resilience_testing",
        "rts_references": [],
        "evaluation_method": "automated",
        "default_risk_weight": 1.0,
        "remediation_deadline_days": 60,
    },

    # Art. 25 — TLPT
    {
        "article": "article_25", "control_id": "DORA-25.01",
        "description": "TLPT covers critical or important functions",
        "test_requirements": ["Critical function mapping", "TLPT scope definition"],
        "pillar": "resilience_testing",
        "rts_references": [],
        "evaluation_method": "external_assessment",
        "default_risk_weight": 1.3,
        "remediation_deadline_days": 90,
    },
    {
        "article": "article_25", "control_id": "DORA-25.02",
        "description": "TLPT simulates real-world attack techniques",
        "test_requirements": ["Attack simulation", "TTPs coverage"],
        "pillar": "resilience_testing",
        "rts_references": [],
        "evaluation_method": "external_assessment",
        "default_risk_weight": 1.2,
        "remediation_deadline_days": 90,
    },
    {
        "article": "article_25", "control_id": "DORA-25.03",
        "description": "TLPT includes live production systems",
        "test_requirements": ["Production system testing", "Live environment coverage"],
        "pillar": "resilience_testing",
        "rts_references": [],
        "evaluation_method": "external_assessment",
        "default_risk_weight": 1.3,
        "remediation_deadline_days": 90,
    },
    {
        "article": "article_25", "control_id": "DORA-25.04",
        "description": "TLPT is performed at least every three years",
        "test_requirements": ["TLPT scheduling", "Three-year cycle"],
        "pillar": "resilience_testing",
        "rts_references": [],
        "evaluation_method": "external_assessment",
        "default_risk_weight": 1.0,
        "remediation_deadline_days": 180,
    },
    {
        "article": "article_25", "control_id": "DORA-25.05",
        "description": "TLPT results are reviewed by management",
        "test_requirements": ["Management review", "Executive sign-off"],
        "pillar": "resilience_testing",
        "rts_references": [],
        "evaluation_method": "manual_required",
        "default_risk_weight": 0.8,
        "remediation_deadline_days": 90,
    },

    # Art. 26 — Requirements for testers
    {
        "article": "article_26", "control_id": "DORA-26.01",
        "description": "Testers have appropriate qualifications",
        "test_requirements": ["Tester certification", "Qualification verification"],
        "pillar": "resilience_testing",
        "rts_references": [],
        "evaluation_method": "manual_required",
        "default_risk_weight": 0.7,
        "remediation_deadline_days": 90,
    },
    {
        "article": "article_26", "control_id": "DORA-26.02",
        "description": "Testers are independent from the tested entity",
        "test_requirements": ["Independence verification", "Conflict of interest check"],
        "pillar": "resilience_testing",
        "rts_references": [],
        "evaluation_method": "manual_required",
        "default_risk_weight": 0.7,
        "remediation_deadline_days": 90,
    },
    {
        "article": "article_26", "control_id": "DORA-26.03",
        "description": "Testers maintain professional standards",
        "test_requirements": ["Professional standards", "Ethical conduct"],
        "pillar": "resilience_testing",
        "rts_references": [],
        "evaluation_method": "manual_required",
        "default_risk_weight": 0.5,
        "remediation_deadline_days": 180,
    },
    {
        "article": "article_26", "control_id": "DORA-26.04",
        "description": "Testers carry professional indemnity insurance",
        "test_requirements": ["Insurance verification", "Liability coverage"],
        "pillar": "resilience_testing",
        "rts_references": [],
        "evaluation_method": "manual_required",
        "default_risk_weight": 0.5,
        "remediation_deadline_days": 180,
    },

    # Art. 27 — Mutual recognition
    {
        "article": "article_27", "control_id": "DORA-27.01",
        "description": "TLPT results are mutually recognised across EU member states",
        "test_requirements": ["Cross-border TLPT recognition", "Regulatory coordination"],
        "pillar": "resilience_testing",
        "rts_references": [],
        "evaluation_method": "manual_required",
        "default_risk_weight": 0.4,
        "remediation_deadline_days": 180,
    },

    # ---------------------------------------------------------------
    # Pillar 4: Third-Party Risk (Art. 28-30)
    # ---------------------------------------------------------------

    {
        "article": "article_28", "control_id": "DORA-28.01",
        "description": "Third-party ICT providers are assessed for risk",
        "test_requirements": ["Third-party risk assessment", "Provider evaluation"],
        "pillar": "third_party_risk",
        "rts_references": ["ITS 2024/2956"],
        "evaluation_method": "automated",
        "default_risk_weight": 1.2,
        "remediation_deadline_days": 60,
    },
    {
        "article": "article_28", "control_id": "DORA-28.02",
        "description": "Concentration risk from third parties is managed",
        "test_requirements": ["Concentration risk analysis", "Provider diversification"],
        "pillar": "third_party_risk",
        "rts_references": ["ITS 2024/2956"],
        "evaluation_method": "automated",
        "default_risk_weight": 1.3,
        "remediation_deadline_days": 60,
    },
    {
        "article": "article_28", "control_id": "DORA-28.03",
        "description": "Contractual arrangements include resilience requirements",
        "test_requirements": ["Contract review", "SLA verification"],
        "pillar": "third_party_risk",
        "rts_references": ["ITS 2024/2956"],
        "evaluation_method": "manual_required",
        "default_risk_weight": 1.0,
        "remediation_deadline_days": 90,
    },
    {
        "article": "article_28", "control_id": "DORA-28.04",
        "description": "Exit strategies for critical third-party services",
        "test_requirements": ["Exit strategy", "Transition planning"],
        "pillar": "third_party_risk",
        "rts_references": ["ITS 2024/2956"],
        "evaluation_method": "automated",
        "default_risk_weight": 1.2,
        "remediation_deadline_days": 60,
    },

    # Art. 29 — Preliminary assessment of concentration risk
    {
        "article": "article_29", "control_id": "DORA-29.01",
        "description": "Concentration risk assessment is performed before new ICT contracts",
        "test_requirements": ["Pre-contract concentration analysis", "Alternative assessment"],
        "pillar": "third_party_risk",
        "rts_references": ["ITS 2024/2956"],
        "evaluation_method": "partial_automated",
        "default_risk_weight": 1.0,
        "remediation_deadline_days": 60,
    },

    # Art. 30 — Key contractual provisions
    {
        "article": "article_30", "control_id": "DORA-30.01",
        "description": "ICT contracts contain mandatory DORA provisions",
        "test_requirements": ["Contract clause verification", "SLA audit rights"],
        "pillar": "third_party_risk",
        "rts_references": [],
        "evaluation_method": "manual_required",
        "default_risk_weight": 1.0,
        "remediation_deadline_days": 90,
    },

    # ---------------------------------------------------------------
    # Pillar 5: Information Sharing (Art. 45)
    # ---------------------------------------------------------------

    {
        "article": "article_45", "control_id": "DORA-45.01",
        "description": "Arrangements for sharing cyber-threat intelligence exist",
        "test_requirements": ["Threat intel sharing agreements", "Community participation"],
        "pillar": "information_sharing",
        "rts_references": [],
        "evaluation_method": "manual_required",
        "default_risk_weight": 0.5,
        "remediation_deadline_days": 180,
    },
]


def _build_controls() -> list[DORAControl]:
    """Build the list of DORA controls from the static definition."""
    return [DORAControl(**c) for c in _DORA_CONTROLS]


# =====================================================================
# DORAEvidenceEngine — main class
# =====================================================================


class DORAEvidenceEngine:
    """DORA Compliance Evidence Engine.

    Evaluates an InfraGraph against DORA regulation articles and generates
    audit-ready evidence, gap analyses, and compliance reports.

    Each control has its own unique evaluation logic appropriate to what
    it actually measures. Controls that cannot be evaluated from
    infrastructure alone are flagged with the appropriate
    ``EvaluationMethod``.

    Args:
        graph: The infrastructure topology to evaluate.
        risk_config: Optional risk configuration overrides. When ``None``,
            sensible defaults for a mid-size financial institution are used.
    """

    def __init__(
        self,
        graph: InfraGraph,
        risk_config: RiskConfig | None = None,
    ) -> None:
        self.graph = graph
        self.controls = _build_controls()
        self.risk_config = risk_config or RiskConfig()

    # ------------------------------------------------------------------
    # Classification
    # ------------------------------------------------------------------

    def classify_test(
        self, scenario_name: str, involves_third_party: bool = False
    ) -> TestClassification:
        """Classify a test scenario per DORA test categories."""
        name_lower = scenario_name.lower()
        tlpt_keywords = {"tlpt", "penetration", "red team", "attack", "threat-led"}
        advanced_keywords = {
            "failover", "switchover", "disaster", "cascade", "chaos",
            "stress", "performance", "load", "recovery",
        }
        if any(kw in name_lower for kw in tlpt_keywords):
            return TestClassification.TLPT
        if any(kw in name_lower for kw in advanced_keywords):
            return TestClassification.ADVANCED_TESTING
        if involves_third_party:
            return TestClassification.ADVANCED_TESTING
        return TestClassification.BASIC_TESTING

    # ------------------------------------------------------------------
    # Infrastructure analysis helpers (shared by multiple evaluators)
    # ------------------------------------------------------------------

    def _has_redundancy(self) -> bool:
        for c in self.graph.components.values():
            if c.replicas >= self.risk_config.min_replicas_for_redundancy:
                return True
        return False

    def _has_failover(self) -> bool:
        for c in self.graph.components.values():
            if c.failover.enabled:
                return True
        return False

    def _has_monitoring(self) -> bool:
        keywords = {"monitoring", "prometheus", "grafana", "otel", "datadog"}
        for c in self.graph.components.values():
            combined = (c.id + " " + c.name).lower()
            if any(kw in combined for kw in keywords):
                return True
        return False

    def _has_third_party(self) -> bool:
        for c in self.graph.components.values():
            if c.type == ComponentType.EXTERNAL_API:
                return True
        return False

    def _third_party_count(self) -> int:
        return sum(
            1 for c in self.graph.components.values()
            if c.type == ComponentType.EXTERNAL_API
        )

    def _component_count(self) -> int:
        return len(self.graph.components)

    def _unhealthy_count(self) -> int:
        return sum(
            1 for c in self.graph.components.values()
            if c.health != HealthStatus.HEALTHY
        )

    # --- Helpers for specific evaluators ---

    def _components_by_type(self, ctype: ComponentType) -> list[Component]:
        """Return all components of a given type."""
        return [c for c in self.graph.components.values() if c.type == ctype]

    def _has_ci_cd(self) -> bool:
        """Check for CI/CD pipeline components."""
        ci_cd_keywords = {"ci", "cd", "jenkins", "github", "gitlab", "circleci",
                          "pipeline", "deploy", "argo", "tekton", "ci_cd", "ci/cd"}
        for c in self.graph.components.values():
            if c.type == ComponentType.TOOL_SERVICE:
                combined = (c.id + " " + c.name).lower()
                if any(kw in combined for kw in ci_cd_keywords):
                    return True
            combined = (c.id + " " + c.name).lower()
            if any(kw in combined for kw in ci_cd_keywords):
                return True
        return False

    def _encryption_coverage(self) -> tuple[float, list[str]]:
        """Calculate encryption coverage ratio, return (ratio, gaps)."""
        if not self.graph.components:
            return 1.0, []
        total = 0
        encrypted = 0
        gap_components: list[str] = []
        for c in self.graph.components.values():
            total += 1
            has_enc = c.security.encryption_at_rest or c.security.encryption_in_transit
            if has_enc:
                encrypted += 1
            else:
                gap_components.append(c.id)
        ratio = encrypted / total if total > 0 else 0.0
        return ratio, gap_components

    def _auth_coverage(self) -> tuple[float, list[str]]:
        """Calculate auth/access control coverage."""
        if not self.graph.components:
            return 1.0, []
        total = 0
        secured = 0
        gap_components: list[str] = []
        for c in self.graph.components.values():
            total += 1
            if c.security.auth_required or c.security.rate_limiting:
                secured += 1
            else:
                gap_components.append(c.id)
        ratio = secured / total if total > 0 else 0.0
        return ratio, gap_components

    def _network_segmentation_coverage(self) -> tuple[float, list[str]]:
        """Calculate network segmentation coverage."""
        if not self.graph.components:
            return 1.0, []
        total = 0
        segmented = 0
        gap_components: list[str] = []
        for c in self.graph.components.values():
            total += 1
            if c.security.network_segmented or c.security.waf_protected:
                segmented += 1
            else:
                gap_components.append(c.id)
        ratio = segmented / total if total > 0 else 0.0
        return ratio, gap_components

    def _audit_logging_coverage(self) -> tuple[float, list[str]]:
        """Calculate audit logging coverage."""
        if not self.graph.components:
            return 1.0, []
        total = 0
        logging_enabled = 0
        gap_components: list[str] = []
        for c in self.graph.components.values():
            total += 1
            if c.security.log_enabled or c.compliance_tags.audit_logging:
                logging_enabled += 1
            else:
                gap_components.append(c.id)
        ratio = logging_enabled / total if total > 0 else 0.0
        return ratio, gap_components

    def _backup_coverage(self) -> tuple[float, list[str]]:
        """Check backup configuration for critical data stores."""
        databases = self._components_by_type(ComponentType.DATABASE)
        storages = self._components_by_type(ComponentType.STORAGE)
        data_components = databases + storages
        if not data_components:
            return 1.0, []
        backed_up = 0
        gap_components: list[str] = []
        for c in data_components:
            if c.security.backup_enabled:
                backed_up += 1
            else:
                gap_components.append(c.id)
        ratio = backed_up / len(data_components) if data_components else 0.0
        return ratio, gap_components

    def _dr_coverage(self) -> tuple[float, list[str]]:
        """Check disaster recovery configuration."""
        if not self.graph.components:
            return 1.0, []
        total = 0
        dr_configured = 0
        gap_components: list[str] = []
        for c in self.graph.components.values():
            total += 1
            has_dr = bool(c.region.dr_target_region) or (
                c.failover.enabled and c.replicas >= 2
            )
            if has_dr:
                dr_configured += 1
            else:
                gap_components.append(c.id)
        ratio = dr_configured / total if total > 0 else 0.0
        return ratio, gap_components

    def _capacity_headroom(self) -> tuple[float, list[str]]:
        """Calculate capacity headroom. Returns (ratio of components with headroom, warnings)."""
        if not self.graph.components:
            return 1.0, []
        total = 0
        adequate = 0
        warnings: list[str] = []
        for c in self.graph.components.values():
            total += 1
            util = c.utilization()
            if util < 80.0:
                adequate += 1
            else:
                warnings.append(f"{c.id} at {util:.0f}% utilization")
        ratio = adequate / total if total > 0 else 0.0
        return ratio, warnings

    def _herfindahl_index(self) -> float:
        """Calculate Herfindahl-Hirschman Index for third-party provider concentration.

        HHI ranges from 0 (perfect diversity) to 1 (single provider).
        In practice, each EXTERNAL_API component is treated as a provider.
        Components sharing a host are grouped as one provider.
        """
        externals = self._components_by_type(ComponentType.EXTERNAL_API)
        if not externals:
            return 0.0
        # Group by host (proxy for unique provider)
        provider_groups: Counter[str] = Counter()
        for c in externals:
            provider_key = c.host if c.host else c.id
            provider_groups[provider_key] += 1
        total_services = sum(provider_groups.values())
        if total_services == 0:
            return 0.0
        hhi = sum((count / total_services) ** 2 for count in provider_groups.values())
        return hhi

    def _exit_strategy_coverage(self) -> tuple[float, list[str]]:
        """Check exit strategy documentation for third-party providers.

        Uses failover.enabled as a proxy for whether an exit/migration path exists.
        """
        externals = self._components_by_type(ComponentType.EXTERNAL_API)
        if not externals:
            return 1.0, []
        covered = 0
        gap_providers: list[str] = []
        for c in externals:
            if c.failover.enabled:
                covered += 1
            else:
                gap_providers.append(c.name)
        ratio = covered / len(externals) if externals else 0.0
        return ratio, gap_providers

    # ------------------------------------------------------------------
    # Evaluate a single control — unique logic per control
    # ------------------------------------------------------------------

    def evaluate_control(self, control: DORAControl) -> DORAGapAnalysis:
        """Evaluate a single DORA control against the infrastructure graph.

        Each control is dispatched to a specific evaluator method. Controls
        that require human/organisational verification are flagged
        appropriately rather than producing false positives from irrelevant
        infrastructure checks.
        """
        n_comps = self._component_count()
        if n_comps == 0:
            return DORAGapAnalysis(
                control_id=control.control_id,
                status=EvidenceStatus.NOT_APPLICABLE,
                gaps=["No components in graph"],
                recommendations=["Add infrastructure components to evaluate"],
                risk_score=0.0,
                evaluation_method=control.evaluation_method,
                rts_references=control.rts_references,
            )

        # Dispatch to the specific evaluator
        evaluator_name = f"_eval_{control.control_id.replace('-', '_').replace('.', '_').lower()}"
        evaluator = getattr(self, evaluator_name, None)
        if evaluator is not None:
            return evaluator(control)

        # Fallback: use article-level evaluator for controls without specific logic
        return self._eval_by_article(control)

    # ------------------------------------------------------------------
    # Article-level fallback evaluator (for articles without per-control)
    # ------------------------------------------------------------------

    def _eval_by_article(self, control: DORAControl) -> DORAGapAnalysis:
        """Fallback evaluator — used when no control-specific evaluator exists.

        Groups by article for controls that share evaluation patterns,
        but marks them as requiring manual verification where appropriate.
        """

        # Stub controls (Pillar 2 incident management, etc.)
        if control.evaluation_method in (
            EvaluationMethod.STUB, EvaluationMethod.MANUAL_REQUIRED
        ):
            return self._eval_manual_required(control)

        # External assessment (TLPT)
        if control.evaluation_method == EvaluationMethod.EXTERNAL_ASSESSMENT:
            return self._eval_external_assessment(control)

        # For any remaining automated controls, do basic infra check
        return self._eval_generic_automated(control)

    def _eval_manual_required(self, control: DORAControl) -> DORAGapAnalysis:
        """Controls requiring organisational/human verification.

        Instead of faking compliance from infrastructure data, these are
        honestly flagged as requiring manual verification.
        """
        return DORAGapAnalysis(
            control_id=control.control_id,
            status=EvidenceStatus.PARTIALLY_COMPLIANT,
            gaps=[f"{control.description} — requires organisational verification"],
            recommendations=[
                f"Provide documentary evidence for: {control.description}",
                "Upload governance documentation to evidence repository",
            ],
            risk_score=0.2,
            evaluation_method=control.evaluation_method,
            rts_references=control.rts_references,
            evidence_items=["Manual verification required — not automatable from infrastructure"],
        )

    def _eval_external_assessment(self, control: DORAControl) -> DORAGapAnalysis:
        """Controls requiring external assessment (e.g. TLPT by qualified testers)."""
        # Check if infrastructure supports safe TLPT execution
        has_red = self._has_redundancy()
        has_fo = self._has_failover()

        gaps: list[str] = []
        recommendations: list[str] = []
        risk = 0.15  # baseline — external assessment always carries some risk

        if not has_red:
            gaps.append("Insufficient redundancy for safe TLPT execution")
            recommendations.append("Add redundancy before scheduling TLPT")
            risk += 0.2
        if not has_fo:
            gaps.append("No failover capability — TLPT on production carries elevated risk")
            recommendations.append("Enable failover for critical systems before TLPT")
            risk += 0.15

        gaps.append("Requires external qualified testers (DORA Art. 26)")
        recommendations.append("Engage qualified TLPT provider and schedule assessment")

        risk = min(risk, 1.0)
        status = (
            EvidenceStatus.NON_COMPLIANT if risk >= self.risk_config.non_compliant_threshold
            else EvidenceStatus.PARTIALLY_COMPLIANT if risk >= self.risk_config.partial_compliant_threshold
            else EvidenceStatus.COMPLIANT
        )

        return DORAGapAnalysis(
            control_id=control.control_id,
            status=status,
            gaps=gaps,
            recommendations=recommendations,
            risk_score=round(risk, 2),
            evaluation_method=EvaluationMethod.EXTERNAL_ASSESSMENT,
            rts_references=control.rts_references,
            evidence_items=["External assessment scheduling required"],
        )

    def _eval_generic_automated(self, control: DORAControl) -> DORAGapAnalysis:
        """Generic automated check — redundancy + failover + monitoring baseline."""
        gaps: list[str] = []
        recommendations: list[str] = []
        risk = 0.0

        has_red = self._has_redundancy()
        has_fo = self._has_failover()
        has_mon = self._has_monitoring()

        if not has_red:
            gaps.append("No redundancy detected")
            recommendations.append("Add replicas >= 2 for critical components")
            risk += 0.2
        if not has_fo:
            gaps.append("No failover configured")
            recommendations.append("Enable failover for critical services")
            risk += 0.2
        if not has_mon:
            gaps.append("No monitoring detected")
            recommendations.append("Deploy monitoring (Prometheus, Datadog, etc.)")
            risk += 0.1

        risk = min(risk, 1.0)
        status = self._risk_to_status(risk)

        return DORAGapAnalysis(
            control_id=control.control_id,
            status=status,
            gaps=gaps,
            recommendations=recommendations,
            risk_score=round(risk, 2),
            evaluation_method=control.evaluation_method,
            rts_references=control.rts_references,
        )

    # ------------------------------------------------------------------
    # Per-control evaluators — UNIQUE logic for each
    # ------------------------------------------------------------------

    # --- Art. 7: ICT systems reliability and capacity ---

    def _eval_dora_7_01(self, control: DORAControl) -> DORAGapAnalysis:
        """DORA-7.01: ICT systems are reliable, have sufficient capacity and are resilient."""
        gaps: list[str] = []
        recommendations: list[str] = []
        evidence: list[str] = []
        risk = 0.0

        # Check capacity headroom
        headroom_ratio, headroom_warnings = self._capacity_headroom()
        if headroom_ratio < 0.8:
            gaps.append(f"Capacity headroom insufficient: {headroom_ratio:.0%} of components below 80% utilization")
            for w in headroom_warnings[:3]:
                gaps.append(f"  - {w}")
            recommendations.append("Scale up or enable autoscaling for high-utilization components")
            risk += 0.3
        evidence.append(f"Capacity headroom: {headroom_ratio:.0%} adequate")

        # Check redundancy for reliability
        has_red = self._has_redundancy()
        if not has_red:
            gaps.append("No redundant components — single points of failure exist")
            recommendations.append("Add replicas >= 2 for critical components")
            risk += 0.25

        # Check failover for resilience
        has_fo = self._has_failover()
        if not has_fo:
            gaps.append("No failover configured — recovery from failures is manual")
            recommendations.append("Enable failover for databases and critical services")
            risk += 0.25

        # Check unhealthy components
        unhealthy = self._unhealthy_count()
        if unhealthy > 0:
            gaps.append(f"{unhealthy} component(s) currently not healthy")
            recommendations.append("Investigate and remediate unhealthy components")
            risk += 0.2

        risk = min(risk, 1.0)
        return DORAGapAnalysis(
            control_id=control.control_id,
            status=self._risk_to_status(risk),
            gaps=gaps, recommendations=recommendations,
            risk_score=round(risk, 2),
            evaluation_method=EvaluationMethod.AUTOMATED,
            rts_references=control.rts_references,
            evidence_items=evidence,
        )

    def _eval_dora_7_02(self, control: DORAControl) -> DORAGapAnalysis:
        """DORA-7.02: Systems are kept up to date with patches/security updates."""
        gaps: list[str] = []
        recommendations: list[str] = []
        risk = 0.0

        # Check patch SLA configuration
        long_patch_sla: list[str] = []
        for c in self.graph.components.values():
            if c.security.patch_sla_hours > 72.0:
                long_patch_sla.append(f"{c.id} (SLA: {c.security.patch_sla_hours:.0f}h)")

        if long_patch_sla:
            gaps.append(f"{len(long_patch_sla)} component(s) with patch SLA > 72h")
            for item in long_patch_sla[:3]:
                gaps.append(f"  - {item}")
            recommendations.append("Reduce patch SLA to <= 72h for critical systems")
            risk += 0.3

        # This control also needs vulnerability scan data (partial automated)
        gaps.append("Patch compliance requires periodic vulnerability scan data (not available from static infra)")
        recommendations.append("Integrate vulnerability scanner results into FaultRay evidence pipeline")
        risk += 0.1

        risk = min(risk, 1.0)
        return DORAGapAnalysis(
            control_id=control.control_id,
            status=self._risk_to_status(risk),
            gaps=gaps, recommendations=recommendations,
            risk_score=round(risk, 2),
            evaluation_method=EvaluationMethod.PARTIAL_AUTOMATED,
            rts_references=control.rts_references,
        )

    # --- Art. 8: Identification ---

    def _eval_dora_8_01(self, control: DORAControl) -> DORAGapAnalysis:
        """DORA-8.01: All ICT assets and dependencies are identified and documented."""
        gaps: list[str] = []
        recommendations: list[str] = []
        evidence: list[str] = []
        risk = 0.0

        n_comps = self._component_count()
        n_deps = self.graph._graph.number_of_edges()
        evidence.append(f"Asset inventory: {n_comps} components, {n_deps} dependencies documented")

        # Check for orphan components (no dependencies at all)
        orphans: list[str] = []
        for c in self.graph.components.values():
            deps = self.graph.get_dependencies(c.id)
            dependents = self.graph.get_dependents(c.id)
            if not deps and not dependents and n_comps > 1:
                orphans.append(c.id)

        if orphans:
            gaps.append(f"{len(orphans)} component(s) have no documented dependencies (orphaned)")
            for o in orphans[:3]:
                gaps.append(f"  - {o}")
            recommendations.append("Document all dependency relationships for orphaned components")
            risk += 0.2

        # Check for components without tags/classification
        untagged = [c.id for c in self.graph.components.values() if not c.tags]
        if untagged and len(untagged) > n_comps * 0.5:
            gaps.append(f"{len(untagged)} component(s) lack classification tags")
            recommendations.append("Tag all components with environment, team, and criticality labels")
            risk += 0.1

        risk = min(risk, 1.0)
        return DORAGapAnalysis(
            control_id=control.control_id,
            status=self._risk_to_status(risk),
            gaps=gaps, recommendations=recommendations,
            risk_score=round(risk, 2),
            evaluation_method=EvaluationMethod.AUTOMATED,
            rts_references=control.rts_references,
            evidence_items=evidence,
        )

    def _eval_dora_8_02(self, control: DORAControl) -> DORAGapAnalysis:
        """DORA-8.02: Critical or important functions are identified."""
        gaps: list[str] = []
        recommendations: list[str] = []
        risk = 0.0

        # Check data classification coverage
        classified = sum(
            1 for c in self.graph.components.values()
            if c.compliance_tags.data_classification != "internal"
        )
        self._component_count()
        if classified == 0:
            gaps.append("No components have explicit data classification beyond default 'internal'")
            recommendations.append("Classify all components by data sensitivity (public/internal/confidential/restricted)")
            risk += 0.3

        # Check SLO definition
        with_slo = sum(1 for c in self.graph.components.values() if c.slo_targets)
        if with_slo == 0:
            gaps.append("No SLO targets defined — criticality cannot be derived from service level objectives")
            recommendations.append("Define SLO targets for critical systems to establish importance ranking")
            risk += 0.2

        risk = min(risk, 1.0)
        return DORAGapAnalysis(
            control_id=control.control_id,
            status=self._risk_to_status(risk),
            gaps=gaps, recommendations=recommendations,
            risk_score=round(risk, 2),
            evaluation_method=EvaluationMethod.PARTIAL_AUTOMATED,
            rts_references=control.rts_references,
        )

    # --- Art. 9: Protection and prevention ---

    def _eval_dora_9_01(self, control: DORAControl) -> DORAGapAnalysis:
        """DORA-9.01: Encryption mechanisms protect data at rest and in transit."""
        gaps: list[str] = []
        recommendations: list[str] = []
        evidence: list[str] = []
        risk = 0.0

        enc_ratio, enc_gaps = self._encryption_coverage()
        evidence.append(f"Encryption coverage: {enc_ratio:.0%}")

        if enc_ratio < 1.0:
            gaps.append(f"{len(enc_gaps)} component(s) lack encryption at rest or in transit")
            for g in enc_gaps[:5]:
                gaps.append(f"  - {g}")
            risk += (1.0 - enc_ratio) * 0.6

        if enc_ratio < 0.5:
            recommendations.append("CRITICAL: Enable encryption in transit (TLS) for all components")
            recommendations.append("Enable encryption at rest for databases and storage")
        elif enc_ratio < 1.0:
            recommendations.append("Enable encryption for remaining unprotected components")

        # Check TLS configuration via network profile
        weak_tls: list[str] = []
        for c in self.graph.components.values():
            if c.network.tls_handshake_ms == 0.0 and c.port > 0:
                weak_tls.append(c.id)
        if weak_tls:
            gaps.append(f"{len(weak_tls)} component(s) have TLS handshake time = 0 (possibly no TLS)")
            risk += 0.1

        risk = min(risk, 1.0)
        return DORAGapAnalysis(
            control_id=control.control_id,
            status=self._risk_to_status(risk),
            gaps=gaps, recommendations=recommendations,
            risk_score=round(risk, 2),
            evaluation_method=EvaluationMethod.AUTOMATED,
            rts_references=control.rts_references,
            evidence_items=evidence,
        )

    def _eval_dora_9_02(self, control: DORAControl) -> DORAGapAnalysis:
        """DORA-9.02: Access controls and authentication mechanisms."""
        gaps: list[str] = []
        recommendations: list[str] = []
        risk = 0.0

        auth_ratio, auth_gaps = self._auth_coverage()

        if auth_ratio < 1.0:
            gaps.append(f"{len(auth_gaps)} component(s) lack access control / rate limiting")
            for g in auth_gaps[:5]:
                gaps.append(f"  - {g}")
            risk += (1.0 - auth_ratio) * 0.5

        if auth_ratio < 0.5:
            recommendations.append("CRITICAL: Implement authentication for all externally accessible components")
            recommendations.append("Enable rate limiting to prevent brute-force attacks")
        elif auth_ratio < 1.0:
            recommendations.append("Enable access controls for remaining unprotected components")

        risk = min(risk, 1.0)
        return DORAGapAnalysis(
            control_id=control.control_id,
            status=self._risk_to_status(risk),
            gaps=gaps, recommendations=recommendations,
            risk_score=round(risk, 2),
            evaluation_method=EvaluationMethod.AUTOMATED,
            rts_references=control.rts_references,
        )

    def _eval_dora_9_03(self, control: DORAControl) -> DORAGapAnalysis:
        """DORA-9.03: Network segmentation and perimeter protection."""
        gaps: list[str] = []
        recommendations: list[str] = []
        risk = 0.0

        seg_ratio, seg_gaps = self._network_segmentation_coverage()

        if seg_ratio < 1.0:
            gaps.append(f"{len(seg_gaps)} component(s) lack network segmentation / WAF protection")
            for g in seg_gaps[:5]:
                gaps.append(f"  - {g}")
            risk += (1.0 - seg_ratio) * 0.4

        # Check for IDS monitoring
        ids_count = sum(1 for c in self.graph.components.values() if c.security.ids_monitored)
        self._component_count()
        if ids_count == 0:
            gaps.append("No components have IDS/IPS monitoring enabled")
            recommendations.append("Deploy intrusion detection system for network-facing components")
            risk += 0.15

        if seg_ratio < 0.5:
            recommendations.append("Implement network segmentation (VPC, subnets) for all critical systems")
        elif seg_ratio < 1.0:
            recommendations.append("Extend network segmentation to remaining components")

        risk = min(risk, 1.0)
        return DORAGapAnalysis(
            control_id=control.control_id,
            status=self._risk_to_status(risk),
            gaps=gaps, recommendations=recommendations,
            risk_score=round(risk, 2),
            evaluation_method=EvaluationMethod.AUTOMATED,
            rts_references=control.rts_references,
        )

    # --- Art. 10: Detection ---

    def _eval_dora_10_01(self, control: DORAControl) -> DORAGapAnalysis:
        """DORA-10.01: Anomalous activity detection mechanisms."""
        gaps: list[str] = []
        recommendations: list[str] = []
        risk = 0.0

        has_mon = self._has_monitoring()
        if not has_mon:
            gaps.append("No monitoring system detected in the infrastructure graph")
            recommendations.append("Deploy monitoring (Prometheus, Grafana, Datadog, or OpenTelemetry)")
            risk += 0.4

        # Check health check intervals
        long_healthcheck: list[str] = []
        for c in self.graph.components.values():
            if c.failover.health_check_interval_seconds > 30.0:
                long_healthcheck.append(
                    f"{c.id} (interval: {c.failover.health_check_interval_seconds:.0f}s)"
                )
        if long_healthcheck:
            gaps.append(f"{len(long_healthcheck)} component(s) with health check interval > 30s")
            recommendations.append("Reduce health check intervals to <= 30s for faster anomaly detection")
            risk += 0.1

        risk = min(risk, 1.0)
        return DORAGapAnalysis(
            control_id=control.control_id,
            status=self._risk_to_status(risk),
            gaps=gaps, recommendations=recommendations,
            risk_score=round(risk, 2),
            evaluation_method=EvaluationMethod.AUTOMATED,
            rts_references=control.rts_references,
        )

    def _eval_dora_10_02(self, control: DORAControl) -> DORAGapAnalysis:
        """DORA-10.02: Audit logging is enabled for critical systems."""
        gaps: list[str] = []
        recommendations: list[str] = []
        risk = 0.0

        log_ratio, log_gaps = self._audit_logging_coverage()

        if log_ratio < 1.0:
            gaps.append(f"{len(log_gaps)} component(s) lack audit logging")
            for g in log_gaps[:5]:
                gaps.append(f"  - {g}")
            risk += (1.0 - log_ratio) * 0.4
            recommendations.append("Enable audit logging for all components handling sensitive data")

        risk = min(risk, 1.0)
        return DORAGapAnalysis(
            control_id=control.control_id,
            status=self._risk_to_status(risk),
            gaps=gaps, recommendations=recommendations,
            risk_score=round(risk, 2),
            evaluation_method=EvaluationMethod.AUTOMATED,
            rts_references=control.rts_references,
        )

    # --- Art. 11: Response and recovery / Testing ---

    def _eval_dora_11_01(self, control: DORAControl) -> DORAGapAnalysis:
        """DORA-11.01: Periodic resilience testing — check test history/frequency."""
        gaps: list[str] = []
        recommendations: list[str] = []
        evidence: list[str] = []
        risk = 0.0

        has_red = self._has_redundancy()
        has_fo = self._has_failover()
        has_mon = self._has_monitoring()
        unhealthy = self._unhealthy_count()

        # Resilience testing requires redundancy, failover, and monitoring to be meaningful
        if not has_red:
            gaps.append("No redundancy detected — resilience testing has limited scope")
            recommendations.append("Add replicas >= 2 for critical components before testing")
            risk += 0.3
        if not has_fo:
            gaps.append("No failover configured — failover scenarios cannot be tested")
            recommendations.append("Enable failover for databases and critical services")
            risk += 0.3
        if not has_mon:
            gaps.append("No monitoring detected — test observability is insufficient")
            recommendations.append("Deploy monitoring to observe resilience test outcomes")
            risk += 0.2
        if unhealthy > 0:
            gaps.append(f"{unhealthy} component(s) not healthy — testing on degraded infra")
            recommendations.append("Remediate unhealthy components before resilience testing")
            risk += 0.2

        evidence.append(f"Redundancy: {'Yes' if has_red else 'No'}")
        evidence.append(f"Failover: {'Yes' if has_fo else 'No'}")
        evidence.append(f"Monitoring: {'Yes' if has_mon else 'No'}")

        risk = min(risk, 1.0)
        return DORAGapAnalysis(
            control_id=control.control_id,
            status=self._risk_to_status(risk),
            gaps=gaps, recommendations=recommendations,
            risk_score=round(risk, 2),
            evaluation_method=EvaluationMethod.AUTOMATED,
            rts_references=control.rts_references,
            evidence_items=evidence,
        )

    def _eval_dora_11_02(self, control: DORAControl) -> DORAGapAnalysis:
        """DORA-11.02: Vulnerability assessments — check security scanning components."""
        gaps: list[str] = []
        recommendations: list[str] = []
        risk = 0.0

        # Check for components with high patch SLAs (proxy for vuln exposure)
        high_exposure: list[str] = []
        for c in self.graph.components.values():
            if c.security.patch_sla_hours > 72.0:
                high_exposure.append(f"{c.id} (patch SLA: {c.security.patch_sla_hours:.0f}h)")

        if high_exposure:
            gaps.append(f"{len(high_exposure)} component(s) with elevated vulnerability exposure (patch SLA > 72h)")
            for h in high_exposure[:3]:
                gaps.append(f"  - {h}")
            recommendations.append("Reduce patch SLA to <= 72h; integrate vulnerability scanning")
            risk += 0.3

        # Check encryption coverage as proxy for security posture
        enc_ratio, _ = self._encryption_coverage()
        if enc_ratio < 0.8:
            gaps.append(f"Low encryption coverage ({enc_ratio:.0%}) increases vulnerability surface")
            recommendations.append("Improve encryption coverage to reduce attack surface")
            risk += 0.2

        # This is partially automated — needs actual scan results
        gaps.append("Full vulnerability assessment requires integration with scanning tools (e.g. Trivy, Snyk)")
        recommendations.append("Connect vulnerability scanner results to FaultRay evidence pipeline")
        risk += 0.1

        risk = min(risk, 1.0)
        return DORAGapAnalysis(
            control_id=control.control_id,
            status=self._risk_to_status(risk),
            gaps=gaps, recommendations=recommendations,
            risk_score=round(risk, 2),
            evaluation_method=EvaluationMethod.PARTIAL_AUTOMATED,
            rts_references=control.rts_references,
        )

    def _eval_dora_11_03(self, control: DORAControl) -> DORAGapAnalysis:
        """DORA-11.03: Network security tests — check segmentation, firewall, TLS."""
        gaps: list[str] = []
        recommendations: list[str] = []
        risk = 0.0

        # Network segmentation
        seg_ratio, seg_gaps = self._network_segmentation_coverage()
        if seg_ratio < 0.5:
            gaps.append(f"Poor network segmentation: only {seg_ratio:.0%} of components segmented")
            recommendations.append("Implement network segmentation for all production components")
            risk += 0.3
        elif seg_ratio < 1.0:
            gaps.append(f"Partial network segmentation: {seg_ratio:.0%} coverage")
            recommendations.append("Extend network segmentation to remaining components")
            risk += 0.15

        # TLS configuration
        enc_ratio, _ = self._encryption_coverage()
        if enc_ratio < 0.8:
            gaps.append(f"Encryption in transit coverage: {enc_ratio:.0%}")
            recommendations.append("Enable TLS for all inter-component communication")
            risk += 0.2

        # WAF protection for load balancers
        lbs = self._components_by_type(ComponentType.LOAD_BALANCER)
        unprotected_lbs = [lb.id for lb in lbs if not lb.security.waf_protected]
        if unprotected_lbs:
            gaps.append(f"{len(unprotected_lbs)} load balancer(s) without WAF protection")
            recommendations.append("Enable WAF on all public-facing load balancers")
            risk += 0.2

        risk = min(risk, 1.0)
        return DORAGapAnalysis(
            control_id=control.control_id,
            status=self._risk_to_status(risk),
            gaps=gaps, recommendations=recommendations,
            risk_score=round(risk, 2),
            evaluation_method=EvaluationMethod.AUTOMATED,
            rts_references=control.rts_references,
        )

    def _eval_dora_11_04(self, control: DORAControl) -> DORAGapAnalysis:
        """DORA-11.04: Performance testing under stress — check capacity headroom."""
        gaps: list[str] = []
        recommendations: list[str] = []
        evidence: list[str] = []
        risk = 0.0

        # Capacity headroom
        headroom_ratio, headroom_warnings = self._capacity_headroom()
        evidence.append(f"Components with adequate headroom: {headroom_ratio:.0%}")

        if headroom_ratio < 0.7:
            gaps.append(f"Stress test risk: {1.0 - headroom_ratio:.0%} of components at high utilization")
            for w in headroom_warnings[:3]:
                gaps.append(f"  - {w}")
            recommendations.append("Scale up high-utilization components before stress testing")
            risk += 0.3

        # Autoscaling capability
        autoscale_count = sum(
            1 for c in self.graph.components.values() if c.autoscaling.enabled
        )
        total = self._component_count()
        if autoscale_count == 0:
            gaps.append("No components have autoscaling enabled — limited stress absorption")
            recommendations.append("Enable autoscaling for app servers and stateless components")
            risk += 0.2
        else:
            evidence.append(f"Autoscaling enabled: {autoscale_count}/{total} components")

        # Circuit breaker coverage
        edges = self.graph.all_dependency_edges()
        cb_count = sum(1 for e in edges if e.circuit_breaker.enabled)
        if edges and cb_count / len(edges) < 0.5:
            gaps.append(f"Low circuit breaker coverage: {cb_count}/{len(edges)} edges")
            recommendations.append("Add circuit breakers to prevent cascade failure under stress")
            risk += 0.15

        risk = min(risk, 1.0)
        return DORAGapAnalysis(
            control_id=control.control_id,
            status=self._risk_to_status(risk),
            gaps=gaps, recommendations=recommendations,
            risk_score=round(risk, 2),
            evaluation_method=EvaluationMethod.AUTOMATED,
            rts_references=control.rts_references,
            evidence_items=evidence,
        )

    def _eval_dora_11_05(self, control: DORAControl) -> DORAGapAnalysis:
        """DORA-11.05: Failover/switchover scenarios — check actual DR setup."""
        gaps: list[str] = []
        recommendations: list[str] = []
        evidence: list[str] = []
        risk = 0.0

        # Failover configuration
        fo_count = sum(1 for c in self.graph.components.values() if c.failover.enabled)
        total = self._component_count()
        fo_ratio = fo_count / total if total > 0 else 0.0
        evidence.append(f"Failover enabled: {fo_count}/{total} ({fo_ratio:.0%})")

        if fo_count == 0:
            gaps.append("No components have failover configured")
            recommendations.append("Enable failover for all critical components (databases, app servers)")
            risk += 0.4
        elif fo_ratio < 0.5:
            gaps.append(f"Low failover coverage: only {fo_ratio:.0%} of components")
            recommendations.append("Extend failover configuration to all critical components")
            risk += 0.25

        # DR region configuration
        dr_ratio, dr_gaps = self._dr_coverage()
        evidence.append(f"DR coverage: {dr_ratio:.0%}")
        if dr_ratio < 0.3:
            gaps.append(f"Poor DR coverage: {dr_ratio:.0%} of components have DR configured")
            recommendations.append("Configure DR target regions for critical components")
            risk += 0.25

        # Redundancy for switchover
        red_count = sum(
            1 for c in self.graph.components.values()
            if c.replicas >= self.risk_config.min_replicas_for_redundancy
        )
        if red_count == 0:
            gaps.append("No redundant components — switchover requires at least 2 replicas")
            recommendations.append("Add replicas >= 2 for components requiring switchover")
            risk += 0.2

        risk = min(risk, 1.0)
        return DORAGapAnalysis(
            control_id=control.control_id,
            status=self._risk_to_status(risk),
            gaps=gaps, recommendations=recommendations,
            risk_score=round(risk, 2),
            evaluation_method=EvaluationMethod.AUTOMATED,
            rts_references=control.rts_references,
            evidence_items=evidence,
        )

    def _eval_dora_11_06(self, control: DORAControl) -> DORAGapAnalysis:
        """DORA-11.06: Source code reviews — check CI/CD integration, static analysis."""
        gaps: list[str] = []
        recommendations: list[str] = []
        risk = 0.0

        has_cicd = self._has_ci_cd()
        if has_cicd:
            pass  # Good — CI/CD pipeline present
        else:
            gaps.append("No CI/CD pipeline detected in infrastructure graph")
            recommendations.append("Integrate CI/CD pipeline with static analysis (SonarQube, CodeQL, Semgrep)")
            risk += 0.25

        # Check change management tags
        cm_count = sum(
            1 for c in self.graph.components.values()
            if c.compliance_tags.change_management
        )
        if cm_count == 0:
            gaps.append("No components flagged for change management — code review enforcement unclear")
            recommendations.append("Enable change management tagging; require PR reviews before deployment")
            risk += 0.15

        # This is partially automated — actual code review metrics need external data
        gaps.append("Code review metrics (coverage, review turnaround) require CI/CD tool integration")
        recommendations.append("Export code review metrics from GitHub/GitLab to evidence pipeline")
        risk += 0.1

        risk = min(risk, 1.0)
        return DORAGapAnalysis(
            control_id=control.control_id,
            status=self._risk_to_status(risk),
            gaps=gaps, recommendations=recommendations,
            risk_score=round(risk, 2),
            evaluation_method=EvaluationMethod.PARTIAL_AUTOMATED,
            rts_references=control.rts_references,
        )

    # --- Art. 12: Backup policies and recovery ---

    def _eval_dora_12_01(self, control: DORAControl) -> DORAGapAnalysis:
        """DORA-12.01: Backup policies cover all critical ICT systems."""
        gaps: list[str] = []
        recommendations: list[str] = []
        evidence: list[str] = []
        risk = 0.0

        backup_ratio, backup_gaps = self._backup_coverage()
        evidence.append(f"Backup coverage for data stores: {backup_ratio:.0%}")

        if backup_ratio < 1.0:
            gaps.append(f"{len(backup_gaps)} data store(s) lack backup configuration")
            for g in backup_gaps[:3]:
                gaps.append(f"  - {g}")
            risk += (1.0 - backup_ratio) * 0.5
            recommendations.append("Enable backups for all databases and storage components")

        # Check backup frequency
        slow_backups: list[str] = []
        for c in self.graph.components.values():
            if c.security.backup_enabled and c.security.backup_frequency_hours > self.risk_config.max_backup_frequency_hours:
                slow_backups.append(f"{c.id} (every {c.security.backup_frequency_hours:.0f}h)")
        if slow_backups:
            gaps.append(f"{len(slow_backups)} component(s) with backup frequency > {self.risk_config.max_backup_frequency_hours:.0f}h")
            recommendations.append(f"Increase backup frequency to <= {self.risk_config.max_backup_frequency_hours:.0f}h")
            risk += 0.15

        if backup_ratio == 0.0 and self._component_count() > 0:
            # Check if there are any data stores at all
            dbs = self._components_by_type(ComponentType.DATABASE)
            storage = self._components_by_type(ComponentType.STORAGE)
            if not dbs and not storage:
                # No data stores — backup check is not directly applicable
                return DORAGapAnalysis(
                    control_id=control.control_id,
                    status=EvidenceStatus.PARTIALLY_COMPLIANT,
                    gaps=["No persistent data stores in graph — backup policy applicability uncertain"],
                    recommendations=["Verify that all data stores are included in infrastructure model"],
                    risk_score=0.15,
                    evaluation_method=EvaluationMethod.AUTOMATED,
                    rts_references=control.rts_references,
                    evidence_items=["No databases or storage components detected"],
                )

        risk = min(risk, 1.0)
        return DORAGapAnalysis(
            control_id=control.control_id,
            status=self._risk_to_status(risk),
            gaps=gaps, recommendations=recommendations,
            risk_score=round(risk, 2),
            evaluation_method=EvaluationMethod.AUTOMATED,
            rts_references=control.rts_references,
            evidence_items=evidence,
        )

    def _eval_dora_12_02(self, control: DORAControl) -> DORAGapAnalysis:
        """DORA-12.02: Recovery and restoration procedures — RTO/RPO validation."""
        gaps: list[str] = []
        recommendations: list[str] = []
        evidence: list[str] = []
        risk = 0.0

        # Check DR configuration
        dr_ratio, dr_gaps = self._dr_coverage()
        evidence.append(f"DR configuration coverage: {dr_ratio:.0%}")

        if dr_ratio < 0.5:
            gaps.append(f"Poor DR coverage: only {dr_ratio:.0%} of components have recovery targets")
            recommendations.append("Configure RTO/RPO and DR target regions for critical components")
            risk += 0.35

        # Check RPO/RTO definitions
        components_with_rpo = sum(
            1 for c in self.graph.components.values()
            if c.region.rpo_seconds > 0
        )
        components_with_rto = sum(
            1 for c in self.graph.components.values()
            if c.region.rto_seconds > 0
        )
        self._component_count()
        if components_with_rpo == 0:
            gaps.append("No RPO (Recovery Point Objective) configured for any component")
            recommendations.append("Define RPO for all critical data stores")
            risk += 0.2
        if components_with_rto == 0:
            gaps.append("No RTO (Recovery Time Objective) configured for any component")
            recommendations.append("Define RTO for all critical systems")
            risk += 0.2

        # Failover as recovery mechanism
        has_fo = self._has_failover()
        if not has_fo:
            gaps.append("No failover configured — recovery is manual")
            recommendations.append("Enable automated failover to meet RTO targets")
            risk += 0.15

        risk = min(risk, 1.0)
        return DORAGapAnalysis(
            control_id=control.control_id,
            status=self._risk_to_status(risk),
            gaps=gaps, recommendations=recommendations,
            risk_score=round(risk, 2),
            evaluation_method=EvaluationMethod.AUTOMATED,
            rts_references=control.rts_references,
            evidence_items=evidence,
        )

    # --- Art. 24: General Requirements for Testing ---

    def _eval_dora_24_01(self, control: DORAControl) -> DORAGapAnalysis:
        """DORA-24.01: Testing programme is risk-based — check test coverage vs critical systems."""
        gaps: list[str] = []
        recommendations: list[str] = []
        risk = 0.0

        # Risk-based: check if resilience mechanisms exist proportional to system count
        self._component_count()
        has_red = self._has_redundancy()
        has_fo = self._has_failover()

        if not has_red and not has_fo:
            gaps.append("No resilience mechanisms configured — testing programme lacks foundation")
            recommendations.append("Implement redundancy and failover as baseline for risk-based testing")
            risk += 0.5
        elif not has_red or not has_fo:
            gaps.append("Partial resilience coverage — testing programme scope may be insufficient")
            recommendations.append("Ensure both redundancy and failover are configured for risk-based test coverage")
            risk += 0.25

        # Check if monitoring exists for test observability
        has_mon = self._has_monitoring()
        if not has_mon:
            gaps.append("No monitoring — test outcomes cannot be observed")
            recommendations.append("Deploy monitoring infrastructure for test result collection")
            risk += 0.15

        risk = min(risk, 1.0)
        return DORAGapAnalysis(
            control_id=control.control_id,
            status=self._risk_to_status(risk),
            gaps=gaps, recommendations=recommendations,
            risk_score=round(risk, 2),
            evaluation_method=EvaluationMethod.AUTOMATED,
            rts_references=control.rts_references,
        )

    def _eval_dora_24_02(self, control: DORAControl) -> DORAGapAnalysis:
        """DORA-24.02: Testing covers all critical ICT systems."""
        gaps: list[str] = []
        recommendations: list[str] = []
        risk = 0.0

        total = self._component_count()
        # Systems with SLOs are implicitly "critical"
        critical_count = sum(1 for c in self.graph.components.values() if c.slo_targets)
        if critical_count == 0:
            # If no SLOs defined, consider all systems critical
            critical_count = total

        # Check which critical systems have resilience mechanisms (proxy for testability)
        testable = sum(
            1 for c in self.graph.components.values()
            if c.replicas >= 2 or c.failover.enabled
        )
        coverage = testable / total if total > 0 else 0.0

        if coverage < 0.5:
            gaps.append(f"Only {coverage:.0%} of systems have resilience mechanisms (testable)")
            recommendations.append("Extend resilience mechanisms to all critical ICT systems")
            risk += 0.35
        elif coverage < 1.0:
            gaps.append(f"Test coverage: {coverage:.0%} — some systems not yet testable")
            recommendations.append("Add redundancy/failover to remaining untestable systems")
            risk += 0.15

        risk = min(risk, 1.0)
        return DORAGapAnalysis(
            control_id=control.control_id,
            status=self._risk_to_status(risk),
            gaps=gaps, recommendations=recommendations,
            risk_score=round(risk, 2),
            evaluation_method=EvaluationMethod.AUTOMATED,
            rts_references=control.rts_references,
        )

    def _eval_dora_24_05(self, control: DORAControl) -> DORAGapAnalysis:
        """DORA-24.05: Testing frequency — check actual test scheduling data."""
        gaps: list[str] = []
        recommendations: list[str] = []
        risk = 0.0

        # Testing frequency assessment based on infrastructure readiness
        has_mon = self._has_monitoring()
        has_red = self._has_redundancy()

        if not has_mon:
            gaps.append("No monitoring infrastructure — test frequency cannot be tracked automatically")
            recommendations.append("Deploy monitoring to enable automated test frequency tracking")
            risk += 0.2

        if not has_red:
            gaps.append("Lack of redundancy limits safe testing frequency")
            recommendations.append("Add redundancy to enable more frequent testing without service impact")
            risk += 0.15

        # Note: actual test schedule data would come from external CI/CD integration
        gaps.append("Test scheduling data requires CI/CD pipeline integration for full frequency analysis")
        recommendations.append(
            f"Ensure resilience tests run at least every {self.risk_config.max_test_age_days} days"
        )
        risk += 0.1

        risk = min(risk, 1.0)
        return DORAGapAnalysis(
            control_id=control.control_id,
            status=self._risk_to_status(risk),
            gaps=gaps, recommendations=recommendations,
            risk_score=round(risk, 2),
            evaluation_method=EvaluationMethod.AUTOMATED,
            rts_references=control.rts_references,
        )

    # --- Art. 25: TLPT ---

    def _eval_dora_25_03(self, control: DORAControl) -> DORAGapAnalysis:
        """DORA-25.03: TLPT on live production — flag as requiring external assessment."""
        gaps: list[str] = []
        recommendations: list[str] = []
        risk = 0.15

        has_red = self._has_redundancy()
        has_fo = self._has_failover()

        if not has_red:
            gaps.append("TLPT on production requires redundancy for safe execution")
            recommendations.append("Add redundancy before scheduling production TLPT")
            risk += 0.25
        if not has_fo:
            gaps.append("TLPT on production requires failover to prevent service disruption")
            recommendations.append("Enable failover for critical systems before production TLPT")
            risk += 0.2

        gaps.append("CRITICAL: TLPT on live production requires external qualified testers (Art. 26)")
        gaps.append("This control cannot be satisfied by automated infrastructure assessment alone")
        recommendations.append("Engage qualified TLPT provider for live production testing")
        recommendations.append("Ensure DR/failover is tested before conducting TLPT on production")

        risk = min(risk, 1.0)
        return DORAGapAnalysis(
            control_id=control.control_id,
            status=EvidenceStatus.PARTIALLY_COMPLIANT,
            gaps=gaps, recommendations=recommendations,
            risk_score=round(risk, 2),
            evaluation_method=EvaluationMethod.EXTERNAL_ASSESSMENT,
            rts_references=control.rts_references,
            evidence_items=["Requires external assessment — flagged for manual follow-up"],
        )

    # --- Art. 26: Requirements for testers (all manual) ---

    def _eval_dora_26_04(self, control: DORAControl) -> DORAGapAnalysis:
        """DORA-26.04: Professional indemnity insurance — organisational verification only."""
        return DORAGapAnalysis(
            control_id=control.control_id,
            status=EvidenceStatus.PARTIALLY_COMPLIANT,
            gaps=[
                "Professional indemnity insurance verification is an organisational requirement",
                "This control cannot be evaluated from infrastructure data",
            ],
            recommendations=[
                "Verify testers carry professional indemnity insurance before engagement",
                "Include insurance verification in TLPT procurement checklist",
                "Retain copies of insurance certificates in evidence repository",
            ],
            risk_score=0.2,
            evaluation_method=EvaluationMethod.MANUAL_REQUIRED,
            rts_references=control.rts_references,
            evidence_items=["Organisational verification required — not an infrastructure check"],
        )

    # --- Art. 28: Third-Party Risk ---

    def _eval_dora_28_01(self, control: DORAControl) -> DORAGapAnalysis:
        """DORA-28.01: Third-party providers assessed for risk."""
        tp_count = self._third_party_count()
        if tp_count == 0:
            return DORAGapAnalysis(
                control_id=control.control_id,
                status=EvidenceStatus.NOT_APPLICABLE,
                gaps=[], recommendations=[],
                risk_score=0.0,
                evaluation_method=EvaluationMethod.AUTOMATED,
                rts_references=control.rts_references,
            )

        gaps: list[str] = []
        recommendations: list[str] = []
        risk = 0.1  # baseline risk for having third parties

        n_comps = self._component_count()
        tp_ratio = tp_count / n_comps if n_comps > 0 else 0.0

        if tp_ratio > 0.5:
            gaps.append(f"High third-party dependency: {tp_count}/{n_comps} components ({tp_ratio:.0%})")
            recommendations.append("Reduce third-party dependency ratio or document risk acceptance")
            risk += 0.3
        elif tp_ratio > 0.3:
            gaps.append(f"Moderate third-party dependency: {tp_count}/{n_comps} ({tp_ratio:.0%})")
            risk += 0.1

        # Check external SLA configuration
        externals = self._components_by_type(ComponentType.EXTERNAL_API)
        no_sla = [c.name for c in externals if c.external_sla is None]
        if no_sla:
            gaps.append(f"{len(no_sla)} third-party provider(s) lack documented SLA")
            recommendations.append("Document SLA for all third-party ICT providers")
            risk += 0.15

        risk = min(risk, 1.0)
        return DORAGapAnalysis(
            control_id=control.control_id,
            status=self._risk_to_status(risk),
            gaps=gaps, recommendations=recommendations,
            risk_score=round(risk, 2),
            evaluation_method=EvaluationMethod.AUTOMATED,
            rts_references=control.rts_references,
        )

    def _eval_dora_28_02(self, control: DORAControl) -> DORAGapAnalysis:
        """DORA-28.02: Concentration risk — Herfindahl-style index analysis."""
        tp_count = self._third_party_count()
        if tp_count == 0:
            return DORAGapAnalysis(
                control_id=control.control_id,
                status=EvidenceStatus.NOT_APPLICABLE,
                gaps=[], recommendations=[],
                risk_score=0.0,
                evaluation_method=EvaluationMethod.AUTOMATED,
                rts_references=control.rts_references,
            )

        gaps: list[str] = []
        recommendations: list[str] = []
        evidence: list[str] = []
        risk = 0.0

        hhi = self._herfindahl_index()
        evidence.append(f"Herfindahl-Hirschman Index (HHI): {hhi:.3f}")

        threshold = self.risk_config.hhi_concentration_threshold
        if hhi >= threshold:
            gaps.append(
                f"High concentration risk: HHI = {hhi:.3f} (threshold: {threshold:.3f})"
            )
            recommendations.append("Diversify third-party providers to reduce concentration risk")
            recommendations.append("Consider multi-provider strategy for critical services")
            risk += 0.5
        elif hhi >= threshold * 0.6:
            gaps.append(f"Moderate concentration risk: HHI = {hhi:.3f}")
            recommendations.append("Monitor concentration trend; plan for provider diversification")
            risk += 0.2

        # Also check raw ratio
        n_comps = self._component_count()
        if tp_count > n_comps * 0.5:
            gaps.append(f"Third-party ratio: {tp_count}/{n_comps} exceeds 50%")
            risk += 0.15

        risk = min(risk, 1.0)
        return DORAGapAnalysis(
            control_id=control.control_id,
            status=self._risk_to_status(risk),
            gaps=gaps, recommendations=recommendations,
            risk_score=round(risk, 2),
            evaluation_method=EvaluationMethod.AUTOMATED,
            rts_references=control.rts_references,
            evidence_items=evidence,
        )

    def _eval_dora_28_03(self, control: DORAControl) -> DORAGapAnalysis:
        """DORA-28.03: Contractual arrangements — requires manual review."""
        tp_count = self._third_party_count()
        if tp_count == 0:
            return DORAGapAnalysis(
                control_id=control.control_id,
                status=EvidenceStatus.NOT_APPLICABLE,
                gaps=[], recommendations=[],
                risk_score=0.0,
                evaluation_method=EvaluationMethod.MANUAL_REQUIRED,
                rts_references=control.rts_references,
            )

        return DORAGapAnalysis(
            control_id=control.control_id,
            status=EvidenceStatus.PARTIALLY_COMPLIANT,
            gaps=[
                f"Contractual review required for {tp_count} third-party provider(s)",
                "Contract clause compliance cannot be verified from infrastructure data",
            ],
            recommendations=[
                "Review all ICT third-party contracts for DORA-mandated provisions",
                "Ensure SLA, audit rights, incident notification, and exit clauses are included",
                "Retain signed contract evidence in compliance repository",
            ],
            risk_score=0.25,
            evaluation_method=EvaluationMethod.MANUAL_REQUIRED,
            rts_references=control.rts_references,
        )

    def _eval_dora_28_04(self, control: DORAControl) -> DORAGapAnalysis:
        """DORA-28.04: Exit strategies — check documented exit plans per provider."""
        tp_count = self._third_party_count()
        if tp_count == 0:
            return DORAGapAnalysis(
                control_id=control.control_id,
                status=EvidenceStatus.NOT_APPLICABLE,
                gaps=[], recommendations=[],
                risk_score=0.0,
                evaluation_method=EvaluationMethod.AUTOMATED,
                rts_references=control.rts_references,
            )

        gaps: list[str] = []
        recommendations: list[str] = []
        evidence: list[str] = []
        risk = 0.0

        exit_ratio, exit_gaps = self._exit_strategy_coverage()
        evidence.append(f"Exit strategy coverage: {exit_ratio:.0%}")

        if exit_ratio < 1.0:
            gaps.append(f"{len(exit_gaps)} third-party provider(s) lack exit strategy (failover/migration path)")
            for g in exit_gaps[:3]:
                gaps.append(f"  - {g}")
            risk += (1.0 - exit_ratio) * 0.5
            recommendations.append("Document exit strategy and migration plan for each third-party provider")
            recommendations.append("Enable failover configuration to demonstrate migration capability")

        if exit_ratio == 0.0:
            recommendations.append("CRITICAL: No exit strategies in place — full vendor lock-in risk")

        risk = min(risk, 1.0)
        return DORAGapAnalysis(
            control_id=control.control_id,
            status=self._risk_to_status(risk),
            gaps=gaps, recommendations=recommendations,
            risk_score=round(risk, 2),
            evaluation_method=EvaluationMethod.AUTOMATED,
            rts_references=control.rts_references,
            evidence_items=evidence,
        )

    # --- Art. 29: Preliminary concentration risk assessment ---

    def _eval_dora_29_01(self, control: DORAControl) -> DORAGapAnalysis:
        """DORA-29.01: Concentration risk assessed before new ICT contracts."""
        tp_count = self._third_party_count()
        if tp_count == 0:
            return DORAGapAnalysis(
                control_id=control.control_id,
                status=EvidenceStatus.NOT_APPLICABLE,
                gaps=[], recommendations=[],
                risk_score=0.0,
                evaluation_method=EvaluationMethod.PARTIAL_AUTOMATED,
                rts_references=control.rts_references,
            )

        hhi = self._herfindahl_index()
        gaps: list[str] = []
        recommendations: list[str] = []
        risk = 0.0

        if hhi >= self.risk_config.hhi_concentration_threshold:
            gaps.append(f"Current HHI ({hhi:.3f}) exceeds threshold — adding more services from concentrated providers increases risk")
            recommendations.append("Conduct concentration impact assessment before any new ICT contracts")
            risk += 0.3

        # This is partially automated — process aspects need manual verification
        gaps.append("Pre-contract assessment process requires organisational verification")
        recommendations.append("Establish mandatory concentration risk check in procurement process")
        risk += 0.1

        risk = min(risk, 1.0)
        return DORAGapAnalysis(
            control_id=control.control_id,
            status=self._risk_to_status(risk),
            gaps=gaps, recommendations=recommendations,
            risk_score=round(risk, 2),
            evaluation_method=EvaluationMethod.PARTIAL_AUTOMATED,
            rts_references=control.rts_references,
        )

    # ------------------------------------------------------------------
    # Status determination helper
    # ------------------------------------------------------------------

    def _risk_to_status(self, risk: float) -> EvidenceStatus:
        """Convert a risk score to an EvidenceStatus using configured thresholds."""
        if risk >= self.risk_config.non_compliant_threshold:
            return EvidenceStatus.NON_COMPLIANT
        if risk >= self.risk_config.partial_compliant_threshold:
            return EvidenceStatus.PARTIALLY_COMPLIANT
        return EvidenceStatus.COMPLIANT

    # ------------------------------------------------------------------
    # Evidence generation
    # ------------------------------------------------------------------

    def generate_evidence(
        self, scenarios_run: list[dict]
    ) -> list[EvidenceRecord]:
        """Create evidence records from test scenario results.

        Each scenario dict should have keys: name, result, severity, description
        (all optional with defaults).
        """
        records: list[EvidenceRecord] = []
        now = datetime.now(timezone.utc)
        for i, scenario in enumerate(scenarios_run):
            name = scenario.get("name", f"scenario_{i}")
            result = scenario.get("result", "pass")
            severity = scenario.get("severity", "medium")
            description = scenario.get("description", name)
            involves_tp = scenario.get("involves_third_party", False)
            classification = self.classify_test(name, involves_tp)
            # Map to relevant control
            if classification == TestClassification.TLPT:
                control_id = "DORA-25.01"
            elif involves_tp:
                control_id = "DORA-28.01"
            elif classification == TestClassification.ADVANCED_TESTING:
                control_id = "DORA-11.05"
            else:
                control_id = "DORA-24.01"
            records.append(EvidenceRecord(
                control_id=control_id,
                timestamp=now,
                test_type=classification.value,
                test_description=description,
                result=result,
                severity=severity,
                remediation_required=(result != "pass"),
                artifacts=[f"evidence/{name.replace(' ', '_')}.json"],
            ))
        return records

    # ------------------------------------------------------------------
    # Gap analysis
    # ------------------------------------------------------------------

    def gap_analysis(self) -> list[DORAGapAnalysis]:
        """Run gap analysis across all DORA controls."""
        return [self.evaluate_control(c) for c in self.controls]

    # ------------------------------------------------------------------
    # Report generation
    # ------------------------------------------------------------------

    def generate_report(
        self, scenarios_run: list[dict]
    ) -> DORAComplianceReport:
        """Generate a complete DORA compliance report."""
        gaps = self.gap_analysis()
        evidence = self.generate_evidence(scenarios_run)

        # Aggregate per-article status
        article_statuses: dict[str, list[EvidenceStatus]] = {}
        for g in gaps:
            ctrl = next(
                (c for c in self.controls if c.control_id == g.control_id), None
            )
            if ctrl:
                art = ctrl.article.value
                article_statuses.setdefault(art, []).append(g.status)

        article_results: dict[str, EvidenceStatus] = {}
        for art, statuses in article_statuses.items():
            if all(s == EvidenceStatus.NOT_APPLICABLE for s in statuses):
                article_results[art] = EvidenceStatus.NOT_APPLICABLE
            elif all(s == EvidenceStatus.COMPLIANT for s in statuses):
                article_results[art] = EvidenceStatus.COMPLIANT
            elif all(
                s in (EvidenceStatus.COMPLIANT, EvidenceStatus.NOT_APPLICABLE)
                for s in statuses
            ):
                article_results[art] = EvidenceStatus.COMPLIANT
            elif any(s == EvidenceStatus.NON_COMPLIANT for s in statuses):
                article_results[art] = EvidenceStatus.NON_COMPLIANT
            else:
                article_results[art] = EvidenceStatus.PARTIALLY_COMPLIANT

        # Aggregate per-pillar status
        pillar_statuses: dict[str, list[EvidenceStatus]] = {}
        for g in gaps:
            ctrl = next(
                (c for c in self.controls if c.control_id == g.control_id), None
            )
            if ctrl:
                pillar = ctrl.pillar.value
                pillar_statuses.setdefault(pillar, []).append(g.status)

        pillar_results: dict[str, EvidenceStatus] = {}
        for pillar, statuses in pillar_statuses.items():
            if all(s == EvidenceStatus.NOT_APPLICABLE for s in statuses):
                pillar_results[pillar] = EvidenceStatus.NOT_APPLICABLE
            elif all(
                s in (EvidenceStatus.COMPLIANT, EvidenceStatus.NOT_APPLICABLE)
                for s in statuses
            ):
                pillar_results[pillar] = EvidenceStatus.COMPLIANT
            elif any(s == EvidenceStatus.NON_COMPLIANT for s in statuses):
                pillar_results[pillar] = EvidenceStatus.NON_COMPLIANT
            else:
                pillar_results[pillar] = EvidenceStatus.PARTIALLY_COMPLIANT

        # Overall status
        all_statuses = list(article_results.values())
        if not all_statuses:
            overall = EvidenceStatus.NOT_APPLICABLE
        elif all(s == EvidenceStatus.NOT_APPLICABLE for s in all_statuses):
            overall = EvidenceStatus.NOT_APPLICABLE
        elif all(
            s in (EvidenceStatus.COMPLIANT, EvidenceStatus.NOT_APPLICABLE)
            for s in all_statuses
        ):
            overall = EvidenceStatus.COMPLIANT
        elif any(s == EvidenceStatus.NON_COMPLIANT for s in all_statuses):
            overall = EvidenceStatus.NON_COMPLIANT
        else:
            overall = EvidenceStatus.PARTIALLY_COMPLIANT

        return DORAComplianceReport(
            overall_status=overall,
            article_results=article_results,
            gap_analyses=gaps,
            evidence_records=evidence,
            pillar_results=pillar_results,
        )

    # ------------------------------------------------------------------
    # Audit export
    # ------------------------------------------------------------------

    def export_audit_package(self) -> dict:
        """Export all evidence and analysis as a structured audit package."""
        gaps = self.gap_analysis()
        return {
            "framework": "DORA",
            "version": "2022/2554",
            "export_timestamp": datetime.now(timezone.utc).isoformat(),
            "controls": [c.model_dump() for c in self.controls],
            "gap_analyses": [g.model_dump() for g in gaps],
            "total_controls": len(self.controls),
            "compliant_count": sum(
                1 for g in gaps if g.status == EvidenceStatus.COMPLIANT
            ),
            "non_compliant_count": sum(
                1 for g in gaps if g.status == EvidenceStatus.NON_COMPLIANT
            ),
            "partially_compliant_count": sum(
                1 for g in gaps
                if g.status == EvidenceStatus.PARTIALLY_COMPLIANT
            ),
            "not_applicable_count": sum(
                1 for g in gaps if g.status == EvidenceStatus.NOT_APPLICABLE
            ),
            "pillar_summary": self._pillar_summary(gaps),
            "rts_coverage": self._rts_coverage_summary(),
        }

    def _pillar_summary(self, gaps: list[DORAGapAnalysis]) -> dict[str, dict]:
        """Generate per-pillar compliance summary."""
        pillar_gaps: dict[str, list[DORAGapAnalysis]] = defaultdict(list)
        for g in gaps:
            ctrl = next(
                (c for c in self.controls if c.control_id == g.control_id), None
            )
            if ctrl:
                pillar_gaps[ctrl.pillar.value].append(g)

        summary: dict[str, dict] = {}
        for pillar, p_gaps in pillar_gaps.items():
            total = len(p_gaps)
            compliant = sum(1 for g in p_gaps if g.status == EvidenceStatus.COMPLIANT)
            non_compliant = sum(1 for g in p_gaps if g.status == EvidenceStatus.NON_COMPLIANT)
            partial = sum(1 for g in p_gaps if g.status == EvidenceStatus.PARTIALLY_COMPLIANT)
            na = sum(1 for g in p_gaps if g.status == EvidenceStatus.NOT_APPLICABLE)
            avg_risk = sum(g.risk_score for g in p_gaps) / max(total, 1)
            summary[pillar] = {
                "total_controls": total,
                "compliant": compliant,
                "non_compliant": non_compliant,
                "partially_compliant": partial,
                "not_applicable": na,
                "average_risk_score": round(avg_risk, 3),
                "weight": self.risk_config.pillar_weights.get(pillar, 0.0),
            }
        return summary

    def _rts_coverage_summary(self) -> dict[str, list[str]]:
        """Summarise which RTS references are covered by which controls."""
        rts_map: dict[str, list[str]] = defaultdict(list)
        for ctrl in self.controls:
            for ref in ctrl.rts_references:
                rts_map[ref].append(ctrl.control_id)
        return dict(rts_map)
