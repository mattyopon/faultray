# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""DORA Manual Control Guidance.

Provides auditor-ready guidance for DORA controls that cannot be evaluated
automatically from infrastructure state (``evaluation_method = manual_required``).

Each ``ManualControlGuidance`` entry answers three questions an auditor asks:
  1. What documents must be produced?
  2. What are the acceptance criteria for those documents?
  3. Who is responsible, and how often must the evidence be refreshed?

References:
  - Regulation (EU) 2022/2554 (DORA), Articles 5–16, 24–27, 30, 45
  - RTS 2024/1774 on ICT risk management framework
  - TIBER-EU framework (for TLPT tester requirements)
  - EBA Guidelines on ICT and security risk management
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ManualControlGuidance:
    """Auditor guidance for a single manual-required DORA control.

    Attributes:
        control_id: The DORA control identifier (e.g. ``"DORA-5.01"``).
        article: The DORA article number as a human-readable string.
        title: Short title of the control.
        required_documents: Documents that must exist and be producible on demand.
        acceptance_criteria: Conditions each document must satisfy to be accepted.
        example_evidence: Concrete examples of what acceptable evidence looks like.
        responsible_role: Job title / organisational role accountable for this control.
        review_frequency: How often evidence must be renewed or re-confirmed.
    """

    control_id: str
    article: str
    title: str
    required_documents: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)
    example_evidence: list[str] = field(default_factory=list)
    responsible_role: str = ""
    review_frequency: str = ""


# ---------------------------------------------------------------------------
# Guidance registry
# ---------------------------------------------------------------------------

_GUIDANCE: dict[str, ManualControlGuidance] = {

    # -----------------------------------------------------------------------
    # Pillar 1: ICT Risk Management (Art. 5-16)
    # -----------------------------------------------------------------------

    "DORA-5.01": ManualControlGuidance(
        control_id="DORA-5.01",
        article="Article 5",
        title="ICT Risk Management Framework — establishment and maintenance",
        required_documents=[
            "ICT risk management framework document",
            "Board approval minutes",
            "Framework version history / change log",
        ],
        acceptance_criteria=[
            "Framework document is dated, version-controlled, and signed by the CISO/CRO",
            "Board approval minutes reference the framework explicitly and are dated",
            "Framework covers scope, risk appetite, governance structure, and review cycle",
            "Change log shows the framework has been reviewed within the past 12 months",
        ],
        example_evidence=[
            "ICT Risk Management Framework v2.3 — approved by Board 2025-11-14",
            "Board minutes extract: 'Item 6 — ICT Risk Framework approved by unanimous vote'",
            "Annual review memo signed by CISO confirming no material changes required",
        ],
        responsible_role="CISO / CRO",
        review_frequency="Annual",
    ),

    "DORA-6.01": ManualControlGuidance(
        control_id="DORA-6.01",
        article="Article 6",
        title="ICT Risk Governance — management body oversight",
        required_documents=[
            "Organisational chart with ICT responsibilities",
            "RACI matrix for ICT risk decisions",
            "Board oversight records (minutes or reports)",
        ],
        acceptance_criteria=[
            "Org chart explicitly shows reporting lines for ICT risk roles to management body",
            "RACI matrix covers at minimum: risk identification, assessment, treatment, and reporting",
            "Board oversight records demonstrate management body reviews ICT risk at least annually",
            "Risk appetite statement is present and referenced in governance documents",
        ],
        example_evidence=[
            "ICT governance org chart — version 3.1, reviewed Q4 2025",
            "RACI matrix: ICT Risk — identifies CRO as Accountable, IT teams as Responsible",
            "Board Risk Committee minutes Q3 2025 — ICT risk dashboard presented and noted",
        ],
        responsible_role="Board Secretary / CRO",
        review_frequency="Annual",
    ),

    "DORA-13.01": ManualControlGuidance(
        control_id="DORA-13.01",
        article="Article 13",
        title="Learning and Evolving — post-incident and post-test learning",
        required_documents=[
            "Post-incident review (PIR) records for all major incidents",
            "Lessons learned register",
            "Training records showing lessons incorporated into staff awareness",
        ],
        acceptance_criteria=[
            "Each major ICT incident has a corresponding PIR completed within 30 days",
            "PIRs include root cause, contributing factors, corrective actions, and owners",
            "Lessons learned register is maintained and entries link back to source incidents/tests",
            "Training records show lessons learned have been communicated to relevant staff",
        ],
        example_evidence=[
            "PIR for P1 incident 2025-09-03: database failover failure — root cause identified, "
            "action items assigned to DBA team with 30-day resolution target",
            "Lessons learned register — 12 entries from chaos game day Q2 2025",
            "Staff awareness training completion record — 'Incident Response Updates Q3 2025'",
        ],
        responsible_role="Head of IT Operations",
        review_frequency="After each major incident; quarterly summary review",
    ),

    "DORA-14.01": ManualControlGuidance(
        control_id="DORA-14.01",
        article="Article 14",
        title="Communication — crisis communication plans",
        required_documents=[
            "Crisis communication plan",
            "Stakeholder notification matrix",
            "Communication log (per incident)",
        ],
        acceptance_criteria=[
            "Crisis communication plan covers internal escalation, regulator notification, "
            "and client/public communication channels",
            "Stakeholder notification matrix specifies who to notify, within what timeframe, "
            "and via which channel for each incident severity level",
            "Communication log for each major incident shows notifications were sent within "
            "required DORA timelines (4 h initial, 24 h intermediate, 1 month final report)",
            "Plan is tested at least annually via tabletop exercise",
        ],
        example_evidence=[
            "Crisis Communication Plan v1.4 — last tested in annual tabletop exercise 2025-10",
            "Stakeholder matrix: Regulators (ECB) — notified within 4h; Clients — 24h; "
            "Board — immediate",
            "Communication log for incident INC-2025-047: ECB notified 2025-11-02T09:45Z "
            "(within 4h window)",
        ],
        responsible_role="Head of Communications / CISO",
        review_frequency="Annual review; updated after each incident requiring external notification",
    ),

    "DORA-15.01": ManualControlGuidance(
        control_id="DORA-15.01",
        article="Article 15",
        title="Simplified ICT Risk Management — proportionality assessment",
        required_documents=[
            "Proportionality assessment document",
            "Simplified framework justification signed by CRO",
        ],
        acceptance_criteria=[
            "Proportionality assessment references the entity classification criteria "
            "in DORA Art. 16(1) and demonstrates the entity qualifies for the simplified regime",
            "Justification is reviewed and reconfirmed annually by the CRO",
            "Simplified framework document is aligned with the applicable RTS provisions",
        ],
        example_evidence=[
            "Proportionality assessment 2025: total assets EUR 480M — below EUR 500M threshold; "
            "qualifies for simplified regime under Art. 16(1)(b)",
            "CRO sign-off memo: 'Simplified ICT Risk Framework remains appropriate — "
            "confirmed 2025-12-01'",
        ],
        responsible_role="CRO",
        review_frequency="Annual",
    ),

    "DORA-16.01": ManualControlGuidance(
        control_id="DORA-16.01",
        article="Article 16",
        title="RTS Harmonisation — alignment with regulatory technical standards",
        required_documents=[
            "RTS mapping document showing framework alignment to RTS 2024/1774",
            "Regulatory change log",
        ],
        acceptance_criteria=[
            "RTS mapping document cross-references each RTS article to the corresponding "
            "internal policy or procedure section",
            "Regulatory change log tracks publication of new or amended RTSs and records "
            "the assessment of impact and any remediation actions taken",
            "Mapping is reviewed whenever a new RTS is published or amended",
        ],
        example_evidence=[
            "RTS 2024/1774 mapping table: Art. 1-3 (framework) → ICT Risk Policy §3.1; "
            "Art. 5-7 (systems) → ICT System Standards v2.0",
            "Regulatory change log entry: RTS 2024/1774 published 2024-06-19 — "
            "gap analysis completed 2024-08-30, no material gaps identified",
        ],
        responsible_role="Compliance Officer",
        review_frequency="As RTSs are published or amended; annual gap review",
    ),

    # -----------------------------------------------------------------------
    # Pillar 3: Resilience Testing (Art. 24-27)
    # -----------------------------------------------------------------------

    "DORA-25.05": ManualControlGuidance(
        control_id="DORA-25.05",
        article="Article 25",
        title="TLPT Management Review — executive sign-off on TLPT results",
        required_documents=[
            "TLPT results management review minutes",
            "Executive sign-off records",
        ],
        acceptance_criteria=[
            "Management review minutes record that the management body was briefed on TLPT findings",
            "Executive sign-off explicitly approves the remediation plan arising from TLPT results",
            "Sign-off is dated and attributable to a named member of the management body",
        ],
        example_evidence=[
            "Board Risk Committee minutes 2025-06-18: 'TLPT results presented by CISO — "
            "3 critical findings; remediation plan approved by Board'",
            "CEO/CIO sign-off letter on TLPT remediation plan — dated 2025-06-20",
        ],
        responsible_role="CIO / CTO",
        review_frequency="After each TLPT cycle (at minimum every 3 years per Art. 25(4))",
    ),

    "DORA-26.01": ManualControlGuidance(
        control_id="DORA-26.01",
        article="Article 26",
        title="Tester Qualifications — certification and experience verification",
        required_documents=[
            "Tester certification copies (CREST, GIAC, or CHECK scheme)",
            "CV / experience records for each lead tester",
        ],
        acceptance_criteria=[
            "At least one lead tester holds a current CREST CCSAS, GIAC GPEN/GXPN, "
            "or equivalent CHECK/CBEST certification",
            "Certifications are valid (not expired) at the time of the TLPT engagement",
            "CVs demonstrate a minimum of 3 years practical penetration testing experience",
        ],
        example_evidence=[
            "CREST CCSAS certificate for lead tester Jane Smith — valid until 2026-11",
            "CV summary: 5 years penetration testing; 3 previous TIBER-EU engagements",
        ],
        responsible_role="TLPT Project Manager",
        review_frequency="Per TLPT engagement",
    ),

    "DORA-26.02": ManualControlGuidance(
        control_id="DORA-26.02",
        article="Article 26",
        title="Tester Independence — conflict of interest checks",
        required_documents=[
            "Conflict of interest declarations (one per tester)",
            "Independence attestations signed by the testing firm",
        ],
        acceptance_criteria=[
            "Each tester declares no material relationship with the tested entity within "
            "the prior 12 months (employment, significant contracting, financial interest)",
            "The testing firm's independence attestation confirms organisational separation "
            "from any internal IT function of the financial entity",
            "Declarations are dated and retained for the duration of the engagement plus 5 years",
        ],
        example_evidence=[
            "Conflict of interest declaration — Tester John Doe, signed 2025-04-01: "
            "'No material relationship with ACME Financial in the past 12 months'",
            "Independence attestation from SecTest Ltd: 'No contractual or ownership "
            "link with ACME Financial as of engagement start date 2025-04-15'",
        ],
        responsible_role="TLPT Project Manager",
        review_frequency="Per TLPT engagement",
    ),

    "DORA-26.03": ManualControlGuidance(
        control_id="DORA-26.03",
        article="Article 26",
        title="Tester Professional Standards — conduct and ethics",
        required_documents=[
            "Professional conduct attestation",
            "Code of ethics acknowledgment signed by each tester",
        ],
        acceptance_criteria=[
            "Attestation references a recognised professional code of conduct "
            "(e.g. CREST Code of Conduct, EC-Council Code of Ethics)",
            "Each tester acknowledges the scope boundaries and non-disclosure obligations "
            "applicable to the engagement",
            "Documents are retained and available for regulatory inspection",
        ],
        example_evidence=[
            "CREST Code of Conduct acknowledgment signed by all testers — 2025-04-01",
            "Rules of engagement document signed by testers and financial entity "
            "CISO — defining scope, prohibited actions, and data handling rules",
        ],
        responsible_role="External tester / TLPT Project Manager",
        review_frequency="Per TLPT engagement",
    ),

    "DORA-26.04": ManualControlGuidance(
        control_id="DORA-26.04",
        article="Article 26",
        title="Tester Insurance and Liability — professional indemnity",
        required_documents=[
            "Professional indemnity (PI) insurance certificate",
            "Liability cap agreement between tester and financial entity",
        ],
        acceptance_criteria=[
            "PI insurance certificate is current and covers the specific TLPT activities performed",
            "Minimum coverage is commensurate with the scope and risk level of the engagement",
            "Liability cap agreement is executed before testing commences and defines "
            "the maximum liability of the testing provider",
        ],
        example_evidence=[
            "Professional indemnity insurance certificate — SecTest Ltd, "
            "coverage EUR 5M, valid 2025-01 to 2026-01",
            "Liability cap agreement — maximum liability EUR 2M; signed by both parties "
            "2025-04-10",
        ],
        responsible_role="Procurement / Legal",
        review_frequency="Per TLPT engagement",
    ),

    "DORA-27.01": ManualControlGuidance(
        control_id="DORA-27.01",
        article="Article 27",
        title="Mutual Recognition of TLPT — cross-border coordination",
        required_documents=[
            "Cross-border TLPT coordination records",
            "Authority attestation from lead competent authority",
        ],
        acceptance_criteria=[
            "Coordination records show that all competent authorities in scope were notified "
            "prior to TLPT commencement in each jurisdiction",
            "Lead authority attestation confirms acceptance of TLPT results for the purposes "
            "of regulatory compliance in other member states",
            "Results letter references the specific entities and jurisdictions covered",
        ],
        example_evidence=[
            "Joint TLPT coordination record — lead CA: BaFin; participating CAs: "
            "De Nederlandsche Bank, Autorità di Vigilanza — all notified 2025-03-01",
            "BaFin attestation letter: 'TLPT results for ACME Group recognised for "
            "regulatory purposes in DE, NL, IT — dated 2025-07-30'",
        ],
        responsible_role="Compliance Officer",
        review_frequency="Per cross-border TLPT engagement",
    ),

    # -----------------------------------------------------------------------
    # Pillar 4: Third-Party Risk (Art. 28, 30)
    # -----------------------------------------------------------------------

    "DORA-28.03": ManualControlGuidance(
        control_id="DORA-28.03",
        article="Article 28",
        title="Third-Party Contractual Resilience Requirements",
        required_documents=[
            "Contracts with ICT third-party providers including resilience clauses",
            "Contract review checklist confirming DORA Art. 30 mandatory provisions",
        ],
        acceptance_criteria=[
            "Each material ICT contract includes provisions on: availability SLAs, "
            "business continuity, data access and portability, audit rights, "
            "incident notification, and exit/termination assistance",
            "Contract review checklist is completed for each new or renewed contract",
            "Legal sign-off confirms compliance with DORA Art. 30 requirements",
        ],
        example_evidence=[
            "Cloud services agreement — AWS, executed 2025-01-15: §12 (Availability), "
            "§18 (Audit Rights), §21 (Incident Notification), §25 (Exit Assistance) "
            "all present and reviewed",
            "Contract checklist: 8/8 mandatory DORA Art. 30 provisions present — "
            "reviewed by Legal 2025-02-01",
        ],
        responsible_role="Legal / Procurement",
        review_frequency="Per contract execution; annual review of all material contracts",
    ),

    "DORA-30.01": ManualControlGuidance(
        control_id="DORA-30.01",
        article="Article 30",
        title="Key Contractual Provisions — mandatory DORA contract clauses",
        required_documents=[
            "Contract clause compliance matrix covering all 8 mandatory DORA Art. 30 provisions",
            "Legal review records for each material ICT third-party contract",
        ],
        acceptance_criteria=[
            "Compliance matrix covers all provisions listed in DORA Art. 30(2): "
            "(a) description of services; (b) data locations; (c) incident notification; "
            "(d) full assistance on ICT operational disruption; (e) cooperation with "
            "competent authorities; (f) termination rights; (g) audit rights; "
            "(h) sub-contracting restrictions",
            "Legal review sign-off is dated and names the reviewing lawyer/team",
            "Any gaps identified in the matrix have a documented remediation plan",
        ],
        example_evidence=[
            "DORA Art. 30 contract matrix — AWS MSA 2025: provisions (a)–(h) all verified "
            "as present; cross-referenced to specific contract sections",
            "Legal review memo from in-house counsel 2025-03-15: "
            "'All 8 mandatory provisions confirmed in MSA §§ 4, 7, 12, 15, 18, 21, 24, 27'",
        ],
        responsible_role="Legal / Procurement",
        review_frequency="Per contract execution; annual review",
    ),

    # -----------------------------------------------------------------------
    # Pillar 5: Information Sharing (Art. 45)
    # -----------------------------------------------------------------------

    "DORA-45.01": ManualControlGuidance(
        control_id="DORA-45.01",
        article="Article 45",
        title="Cyber-Threat Intelligence Sharing — arrangements and participation",
        required_documents=[
            "Information sharing agreements (ISAs) with threat intelligence communities",
            "Participation records in relevant threat intelligence sharing forums",
        ],
        acceptance_criteria=[
            "At least one ISA is in place with a recognised threat intelligence platform "
            "(e.g. FS-ISAC, CERT-EU, national financial sector CERT)",
            "Participation records show active contribution or consumption of threat "
            "intelligence within the past 12 months",
            "CISO reviews the value of participation annually and documents the outcome",
        ],
        example_evidence=[
            "FS-ISAC membership agreement — executed 2024-06-01; renewed annually",
            "Threat intelligence log 2025: 47 IOCs received from FS-ISAC; "
            "12 contributed to community",
            "CISO annual review memo 2025-11: 'FS-ISAC participation delivering value — "
            "2 active threat campaigns detected via shared intelligence'",
        ],
        responsible_role="CISO",
        review_frequency="Annual",
    ),
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_guidance(control_id: str) -> ManualControlGuidance | None:
    """Return guidance for a given control ID, or ``None`` if not available.

    Args:
        control_id: A DORA control identifier, e.g. ``"DORA-5.01"``.

    Returns:
        A :class:`ManualControlGuidance` instance, or ``None`` if no guidance
        has been defined for the requested control.
    """
    return _GUIDANCE.get(control_id)


def get_all_guidance() -> dict[str, ManualControlGuidance]:
    """Return all guidance entries as an immutable-safe copy.

    Returns:
        A shallow copy of the internal guidance registry keyed by control ID.
    """
    return dict(_GUIDANCE)
