# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""DORA Article 26 — Threat-Led Penetration Testing (TLPT) Support.

Provides TLPT readiness assessment, scope definition, tester qualification
management, and workflow integration for DORA-compliant TLPT programmes.

IMPORTANT DISCLAIMER
--------------------
FaultRay provides **readiness assessment** and **scope definition** tooling
only. FaultRay simulations help organisations validate their infrastructure
resilience and prepare for TLPT, but they are NOT a substitute for actual
TLPT. Actual Threat-Led Penetration Testing must be performed on live
production systems by qualified testers meeting all requirements of
DORA Articles 26 and 27 (minimum 5 years experience, 5+ references,
professional indemnity insurance, and recognised certifications).
Competent authorities must be notified before TLPT commences where required.

Regulatory references:
    DORA Regulation (EU) 2022/2554
    Article 26 — Advanced testing of ICT tools, systems and processes based
                 on TLPT
    Article 27 — Requirements for testers for the carrying out of TLPT
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from faultray.model.graph import InfraGraph

from faultray.model.components import Component, ComponentType

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DISCLAIMER — always emitted when this module is imported
# ---------------------------------------------------------------------------

_TLPT_DISCLAIMER = (
    "TLPT DISCLAIMER: FaultRay provides readiness assessment and scope "
    "definition only. Actual TLPT must be performed on live production "
    "systems by testers meeting DORA Art. 27 requirements (5+ years "
    "experience, 5+ references, professional indemnity insurance, recognised "
    "certifications). FaultRay simulations are NOT a substitute for real TLPT."
)
logger.warning(_TLPT_DISCLAIMER)


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class TLPTReadinessStatus(str, Enum):
    """Overall TLPT readiness assessment outcome."""

    READY = "ready"
    PARTIALLY_READY = "partially_ready"
    NOT_READY = "not_ready"


class ChecklistItemStatus(str, Enum):
    """Status of a single pre-TLPT checklist item."""

    SATISFIED = "satisfied"
    UNSATISFIED = "unsatisfied"
    NOT_APPLICABLE = "not_applicable"
    NEEDS_REVIEW = "needs_review"


class TesterType(str, Enum):
    """Whether a tester is internal or external to the organisation."""

    INTERNAL = "internal"
    EXTERNAL = "external"


class TLPTPhase(str, Enum):
    """Phase of the TLPT lifecycle."""

    PRE_TEST = "pre_test"
    IN_TEST = "in_test"
    POST_TEST = "post_test"
    REMEDIATION = "remediation"
    CLOSED = "closed"


class SignOffStatus(str, Enum):
    """Management sign-off status for a TLPT engagement."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


class TLPTChecklistItem(BaseModel):
    """A single item in the pre-TLPT readiness checklist."""

    item_id: str
    category: str  # "documentation" | "scope" | "environment" | "process" | "legal"
    description: str
    dora_reference: str = ""
    status: ChecklistItemStatus = ChecklistItemStatus.NEEDS_REVIEW
    evidence: str = ""
    notes: str = ""


class TesterQualification(BaseModel):
    """Qualification record for a TLPT tester (DORA Art. 27).

    DORA Art. 27 requires testers to demonstrate:
    - At least 5 years of relevant technical experience in ICT security
    - At least 5 professional references covering comparable assignments
    - Professional indemnity insurance
    - Recognised certifications (e.g. CREST, GIAC, CHECK, TIGER)
    """

    tester_id: str
    name: str
    organisation: str = ""
    tester_type: TesterType = TesterType.EXTERNAL
    years_experience: float = 0.0          # DORA Art. 27: minimum 5 years
    reference_count: int = 0               # DORA Art. 27: minimum 5 references
    has_indemnity_insurance: bool = False  # DORA Art. 27: required
    certifications: list[str] = Field(default_factory=list)  # e.g. CREST, GIAC GPEN
    last_verified: date | None = None
    conflict_of_interest_cleared: bool = False
    conflict_of_interest_notes: str = ""

    def is_dora_compliant(self) -> tuple[bool, list[str]]:
        """Evaluate whether this tester meets DORA Art. 27 minimum requirements.

        Returns:
            (compliant: bool, deficiencies: list[str])
        """
        deficiencies: list[str] = []
        if self.years_experience < 5.0:
            deficiencies.append(
                f"Insufficient experience: {self.years_experience:.1f} years "
                f"(DORA Art. 27 requires ≥5 years)."
            )
        if self.reference_count < 5:
            deficiencies.append(
                f"Insufficient references: {self.reference_count} "
                f"(DORA Art. 27 requires ≥5 professional references)."
            )
        if not self.has_indemnity_insurance:
            deficiencies.append(
                "Professional indemnity insurance not confirmed "
                "(required by DORA Art. 27)."
            )
        if not self.certifications:
            deficiencies.append(
                "No recognised certifications documented "
                "(DORA Art. 27 recommends CREST, GIAC, CHECK, or equivalent)."
            )
        if not self.conflict_of_interest_cleared:
            deficiencies.append(
                "Conflict of interest check not completed "
                "(DORA Art. 27 requires independence from the tested entity)."
            )
        return (len(deficiencies) == 0, deficiencies)


class TLPTScopeComponent(BaseModel):
    """A component included in the TLPT scope."""

    component_id: str
    component_name: str
    component_type: str
    is_critical_function: bool = False
    attack_surface_notes: str = ""
    inclusion_rationale: str = ""


class TLPTScopeDocument(BaseModel):
    """Formal TLPT scope definition document.

    Identifies the critical and important functions to be tested,
    the attack surface, and the boundaries of the test.
    """

    scope_id: str
    tlpt_id: str
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    critical_components: list[TLPTScopeComponent] = Field(default_factory=list)
    excluded_components: list[str] = Field(default_factory=list)
    attack_surface_summary: str = ""
    test_boundaries: list[str] = Field(default_factory=list)
    out_of_scope_items: list[str] = Field(default_factory=list)
    disclaimer: str = _TLPT_DISCLAIMER


class RemediationItem(BaseModel):
    """A single remediation action arising from TLPT findings."""

    item_id: str
    finding: str
    severity: str  # "critical" | "high" | "medium" | "low"
    recommended_action: str
    owner: str = ""
    due_date: date | None = None
    completed: bool = False
    completion_date: date | None = None
    verified_by: str = ""


class TLPTEngagement(BaseModel):
    """A complete TLPT engagement record.

    Tracks the full lifecycle from pre-test readiness through to
    post-test remediation and management sign-off.
    """

    tlpt_id: str
    organisation_name: str = ""
    phase: TLPTPhase = TLPTPhase.PRE_TEST
    scheduled_start: date | None = None
    actual_start: date | None = None
    actual_end: date | None = None
    lead_tester_id: str = ""
    tester_ids: list[str] = Field(default_factory=list)
    scope_document: TLPTScopeDocument | None = None
    readiness_checklist: list[TLPTChecklistItem] = Field(default_factory=list)
    remediation_items: list[RemediationItem] = Field(default_factory=list)
    sign_off_status: SignOffStatus = SignOffStatus.PENDING
    sign_off_by: str = ""
    sign_off_date: date | None = None
    management_notes: str = ""
    competent_authority_notified: bool = False
    competent_authority_reference: str = ""
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    disclaimer: str = _TLPT_DISCLAIMER


class TLPTCycleRecord(BaseModel):
    """3-year TLPT cycle tracking record (DORA Art. 26).

    DORA Art. 26 requires TLPT at least every 3 years for financial entities
    in scope. This record tracks the cycle to ensure compliance.
    """

    entity_name: str
    engagements: list[TLPTEngagement] = Field(default_factory=list)
    next_tlpt_due: date | None = None
    last_external_test_date: date | None = None

    def is_overdue(self, as_of: date | None = None) -> bool:
        """Return True if TLPT is overdue per the 3-year cycle."""
        today = as_of or date.today()
        if self.next_tlpt_due is None:
            return False
        return today > self.next_tlpt_due

    def days_until_due(self, as_of: date | None = None) -> int | None:
        """Return days until next TLPT is due (negative if overdue)."""
        today = as_of or date.today()
        if self.next_tlpt_due is None:
            return None
        return (self.next_tlpt_due - today).days


# ---------------------------------------------------------------------------
# Pre-TLPT Checklist builder
# ---------------------------------------------------------------------------

_PRE_TLPT_CHECKLIST_ITEMS: list[dict] = [
    # Documentation
    {
        "item_id": "DOC-01",
        "category": "documentation",
        "description": "Production environment is fully documented (architecture diagrams, data flows, asset inventory)",
        "dora_reference": "DORA Art. 26(1)",
    },
    {
        "item_id": "DOC-02",
        "category": "documentation",
        "description": "Critical and important functions are formally identified and documented",
        "dora_reference": "DORA Art. 26(1)(a)",
    },
    {
        "item_id": "DOC-03",
        "category": "documentation",
        "description": "Previous test results and remediation actions are documented",
        "dora_reference": "DORA Art. 24(3)",
    },
    # Scope
    {
        "item_id": "SCOPE-01",
        "category": "scope",
        "description": "TLPT scope is formally defined and approved by management",
        "dora_reference": "DORA Art. 26(1)(b)",
    },
    {
        "item_id": "SCOPE-02",
        "category": "scope",
        "description": "Out-of-scope systems and boundaries are clearly documented",
        "dora_reference": "DORA Art. 26(1)(b)",
    },
    {
        "item_id": "SCOPE-03",
        "category": "scope",
        "description": "Third-party ICT providers in scope have been notified and consented",
        "dora_reference": "DORA Art. 26(5)",
    },
    # Environment
    {
        "item_id": "ENV-01",
        "category": "environment",
        "description": "Test is planned against live production systems (not staging-only)",
        "dora_reference": "DORA Art. 26(2)",
    },
    {
        "item_id": "ENV-02",
        "category": "environment",
        "description": "Monitoring and alerting systems are active and ready",
        "dora_reference": "DORA Art. 26(1)",
    },
    {
        "item_id": "ENV-03",
        "category": "environment",
        "description": "FaultRay simulation has been run as readiness baseline (pre-test)",
        "dora_reference": "Best practice: DORA Art. 24 testing programme",
    },
    # Process
    {
        "item_id": "PROC-01",
        "category": "process",
        "description": "Incident response procedures are in place and tested",
        "dora_reference": "DORA Art. 18",
    },
    {
        "item_id": "PROC-02",
        "category": "process",
        "description": "Communication plan for TLPT engagement is established (internal + external)",
        "dora_reference": "DORA Art. 26(1)",
    },
    {
        "item_id": "PROC-03",
        "category": "process",
        "description": "Post-test remediation process and ownership assigned",
        "dora_reference": "DORA Art. 26(6)",
    },
    {
        "item_id": "PROC-04",
        "category": "process",
        "description": "Management sign-off obtained for TLPT commencement",
        "dora_reference": "DORA Art. 26(1)",
    },
    # Tester qualifications
    {
        "item_id": "TESTER-01",
        "category": "tester_qualification",
        "description": "Lead tester has ≥5 years relevant ICT security experience (DORA Art. 27)",
        "dora_reference": "DORA Art. 27(1)(a)",
    },
    {
        "item_id": "TESTER-02",
        "category": "tester_qualification",
        "description": "Lead tester has ≥5 professional references for comparable assignments",
        "dora_reference": "DORA Art. 27(1)(b)",
    },
    {
        "item_id": "TESTER-03",
        "category": "tester_qualification",
        "description": "Lead tester holds professional indemnity insurance",
        "dora_reference": "DORA Art. 27(1)(c)",
    },
    {
        "item_id": "TESTER-04",
        "category": "tester_qualification",
        "description": "Lead tester has recognised certifications (CREST, GIAC, CHECK, TIGER, or equivalent)",
        "dora_reference": "DORA Art. 27(2)",
    },
    {
        "item_id": "TESTER-05",
        "category": "tester_qualification",
        "description": "Conflict of interest check completed for all testers",
        "dora_reference": "DORA Art. 27(1)",
    },
    # Legal / regulatory
    {
        "item_id": "LEGAL-01",
        "category": "legal",
        "description": "Competent authority notified of TLPT where required by national regulation",
        "dora_reference": "DORA Art. 26(7)",
    },
    {
        "item_id": "LEGAL-02",
        "category": "legal",
        "description": "Written agreement / contract signed with external tester(s)",
        "dora_reference": "DORA Art. 27(1)",
    },
    {
        "item_id": "LEGAL-03",
        "category": "legal",
        "description": "Non-disclosure agreement (NDA) in place with all testers",
        "dora_reference": "Best practice",
    },
]


def _build_pre_tlpt_checklist() -> list[TLPTChecklistItem]:
    """Build a fresh pre-TLPT checklist from the canonical item definitions."""
    return [TLPTChecklistItem(**item) for item in _PRE_TLPT_CHECKLIST_ITEMS]


# ---------------------------------------------------------------------------
# TLPT Readiness Assessor
# ---------------------------------------------------------------------------


class TLPTReadinessAssessor:
    """Assess TLPT readiness from an InfraGraph (DORA Art. 26 pre-test phase).

    FaultRay's simulation results feed into this assessor to provide a
    quantified pre-TLPT baseline.  The assessor does NOT perform TLPT itself.

    Usage::

        from faultray.model.graph import InfraGraph
        from faultray.simulator.dora_tlpt import TLPTReadinessAssessor

        graph = InfraGraph.load(Path("infra.json"))
        assessor = TLPTReadinessAssessor(graph)
        engagement = assessor.create_engagement("TLPT-2026-001")
        scope_doc = assessor.generate_scope_document(engagement)
        status, deficiencies = assessor.assess_readiness(engagement)
    """

    # Component types that represent critical/important ICT functions per DORA
    _CRITICAL_TYPES: frozenset[ComponentType] = frozenset(
        {
            ComponentType.DATABASE,
            ComponentType.LOAD_BALANCER,
            ComponentType.APP_SERVER,
            ComponentType.AGENT_ORCHESTRATOR,
        }
    )

    def __init__(self, graph: "InfraGraph", organisation_name: str = "") -> None:
        self.graph = graph
        self.organisation_name = organisation_name

    def create_engagement(
        self,
        tlpt_id: str,
        scheduled_start: date | None = None,
    ) -> TLPTEngagement:
        """Create a new TLPT engagement with a pre-populated readiness checklist.

        Args:
            tlpt_id: Unique identifier for this TLPT engagement.
            scheduled_start: Planned start date (defaults to 90 days from today).

        Returns:
            TLPTEngagement in PRE_TEST phase with blank checklist items.
        """
        start = scheduled_start or (date.today() + timedelta(days=90))
        checklist = _build_pre_tlpt_checklist()
        engagement = TLPTEngagement(
            tlpt_id=tlpt_id,
            organisation_name=self.organisation_name,
            phase=TLPTPhase.PRE_TEST,
            scheduled_start=start,
            readiness_checklist=checklist,
        )
        logger.info(
            "Created TLPT engagement %s for %s (scheduled: %s). %s",
            tlpt_id,
            self.organisation_name or "organisation",
            start,
            _TLPT_DISCLAIMER,
        )
        return engagement

    def generate_scope_document(
        self, engagement: TLPTEngagement
    ) -> TLPTScopeDocument:
        """Generate a TLPT scope document from the InfraGraph.

        Identifies critical and important ICT functions per DORA Art. 26(1)(a),
        maps the attack surface, and documents test boundaries.

        The generated document is also attached to the engagement record.
        """
        scope_id = f"SCOPE-{engagement.tlpt_id}"
        critical_components: list[TLPTScopeComponent] = []
        non_critical_excluded: list[str] = []

        for comp in self.graph.components.values():
            is_critical = comp.type in self._CRITICAL_TYPES or "critical" in [
                t.lower() for t in comp.tags
            ]
            if is_critical:
                rationale = (
                    f"Component type '{comp.type.value}' is classified as a "
                    "critical/important ICT function per DORA Art. 26(1)(a). "
                )
                if comp.replicas == 1:
                    rationale += (
                        "Single replica — single point of failure risk elevates TLPT priority. "
                    )
                scope_comp = TLPTScopeComponent(
                    component_id=comp.id,
                    component_name=comp.name,
                    component_type=comp.type.value,
                    is_critical_function=True,
                    attack_surface_notes=_attack_surface_for_component(comp),
                    inclusion_rationale=rationale,
                )
                critical_components.append(scope_comp)
            else:
                non_critical_excluded.append(
                    f"{comp.id} ({comp.type.value}) — not classified as critical/important function"
                )

        attack_surface_summary = _build_attack_surface_summary(
            self.graph, critical_components
        )

        scope_doc = TLPTScopeDocument(
            scope_id=scope_id,
            tlpt_id=engagement.tlpt_id,
            critical_components=critical_components,
            excluded_components=non_critical_excluded,
            attack_surface_summary=attack_surface_summary,
            test_boundaries=[
                "In scope: all components listed in critical_components",
                "In scope: network paths between listed components",
                "In scope: authentication and access control mechanisms",
                "Out of scope: non-critical components listed in excluded_components",
                "Out of scope: third-party SaaS provider internals (unless explicitly agreed)",
                "Out of scope: physical premises (covered by separate physical security testing)",
            ],
            out_of_scope_items=non_critical_excluded,
        )

        engagement.scope_document = scope_doc
        logger.info(
            "Generated TLPT scope document %s: %d critical components identified.",
            scope_id,
            len(critical_components),
        )
        return scope_doc

    def assess_readiness(
        self, engagement: TLPTEngagement
    ) -> tuple[TLPTReadinessStatus, list[str]]:
        """Derive a readiness status from the checklist and infrastructure state.

        Infrastructure-based checks (not requiring manual inputs):
        - Production documentation: passes if InfraGraph has components
        - Monitoring: passes if any monitoring-tagged component exists
        - Redundancy: warned if critical components lack failover
        - Scope: passes if scope document has been generated

        Checklist-based checks are also evaluated.

        Returns:
            (TLPTReadinessStatus, list[str]) — status and list of deficiencies.
        """
        deficiencies: list[str] = []

        # --- Infrastructure-derived checks ---
        components = self.graph.components
        if not components:
            deficiencies.append(
                "InfraGraph has no components. Production environment must be "
                "documented before TLPT (DORA Art. 26 DOC-01)."
            )

        # Check for monitoring
        has_monitoring = any(
            any(kw in (c.id + " " + c.name).lower() for kw in ("monitor", "prometheus", "datadog", "grafana", "otel"))
            for c in components.values()
        )
        if not has_monitoring:
            deficiencies.append(
                "No monitoring infrastructure detected. Monitoring must be active "
                "during TLPT to capture test activities (DORA Art. 26 ENV-02)."
            )

        # Check critical components have failover
        critical_without_failover = [
            c.name
            for c in components.values()
            if c.type in self._CRITICAL_TYPES and not c.failover.enabled
        ]
        if critical_without_failover:
            deficiencies.append(
                f"Critical components without failover: {critical_without_failover}. "
                "TLPT on live production without failover increases outage risk. "
                "Enable failover before TLPT commencement."
            )

        # Check scope document
        if engagement.scope_document is None:
            deficiencies.append(
                "TLPT scope document has not been generated. "
                "Run generate_scope_document() before TLPT (DORA Art. 26 SCOPE-01)."
            )

        # --- Checklist-based checks ---
        unsatisfied_items = [
            item
            for item in engagement.readiness_checklist
            if item.status == ChecklistItemStatus.UNSATISFIED
        ]
        needs_review_items = [
            item
            for item in engagement.readiness_checklist
            if item.status == ChecklistItemStatus.NEEDS_REVIEW
        ]

        for item in unsatisfied_items:
            deficiencies.append(
                f"[{item.item_id}] UNSATISFIED: {item.description} ({item.dora_reference})"
            )
        if needs_review_items:
            deficiencies.append(
                f"{len(needs_review_items)} checklist item(s) still need review: "
                f"{[i.item_id for i in needs_review_items]}"
            )

        # --- Derive overall status ---
        if not deficiencies:
            status = TLPTReadinessStatus.READY
        elif len(deficiencies) <= 3 and not any(
            "UNSATISFIED" in d and "TESTER" in d for d in deficiencies
        ):
            status = TLPTReadinessStatus.PARTIALLY_READY
        else:
            status = TLPTReadinessStatus.NOT_READY

        return status, deficiencies


# ---------------------------------------------------------------------------
# Tester Manager
# ---------------------------------------------------------------------------


class TLPTTesterManager:
    """Manage DORA Art. 27 tester qualifications and rotation.

    Tracks tester records, validates Art. 27 compliance, checks conflict of
    interest, and enforces the rotation rule that every 3rd TLPT engagement
    must use an external tester.

    Usage::

        manager = TLPTTesterManager()
        manager.register_tester(tester)
        compliant, issues = manager.verify_qualification(tester_id)
        manager.assign_tester(engagement, tester_id)
        rotation_ok, msg = manager.check_rotation_compliance(cycle_record)
    """

    def __init__(self) -> None:
        self._testers: dict[str, TesterQualification] = {}

    def register_tester(self, tester: TesterQualification) -> None:
        """Add or update a tester qualification record."""
        self._testers[tester.tester_id] = tester
        logger.info("Registered tester %s (%s).", tester.tester_id, tester.name)

    def get_tester(self, tester_id: str) -> TesterQualification | None:
        """Retrieve a tester record by ID."""
        return self._testers.get(tester_id)

    def verify_qualification(
        self, tester_id: str
    ) -> tuple[bool, list[str]]:
        """Verify a tester's DORA Art. 27 compliance.

        Returns:
            (compliant: bool, deficiencies: list[str])

        Raises:
            ValueError: If the tester_id is not registered.
        """
        tester = self._testers.get(tester_id)
        if tester is None:
            raise ValueError(
                f"Tester '{tester_id}' not found. "
                "Register with register_tester() before verification."
            )
        return tester.is_dora_compliant()

    def check_conflict_of_interest(
        self, tester_id: str, organisation_name: str
    ) -> tuple[bool, str]:
        """Check whether a tester has a conflict of interest with the organisation.

        A basic check is performed on the organisation field of the tester record.
        In practice this should be supplemented by manual review.

        Returns:
            (clear: bool, message: str)
        """
        tester = self._testers.get(tester_id)
        if tester is None:
            raise ValueError(f"Tester '{tester_id}' not found.")
        if tester.tester_type == TesterType.INTERNAL:
            # Internal testers must not test systems they operate or maintain
            return (
                tester.conflict_of_interest_cleared,
                (
                    "Internal tester conflict of interest must be manually cleared "
                    "by CISO or equivalent before TLPT commencement."
                    if not tester.conflict_of_interest_cleared
                    else "Internal tester conflict of interest cleared."
                ),
            )
        # External testers: basic name overlap check (must be supplemented manually)
        tester_org_lower = tester.organisation.lower()
        org_lower = organisation_name.lower()
        if tester_org_lower and tester_org_lower in org_lower:
            return (
                False,
                f"Potential conflict of interest: tester organisation "
                f"'{tester.organisation}' overlaps with tested entity '{organisation_name}'.",
            )
        return (
            tester.conflict_of_interest_cleared,
            "No automated conflict of interest detected. Manual review recommended.",
        )

    def check_rotation_compliance(
        self, cycle_record: TLPTCycleRecord
    ) -> tuple[bool, str]:
        """Verify that every 3rd TLPT engagement used an external tester.

        DORA Art. 27(5) requires that at least every third TLPT is carried out
        by an external tester.

        Returns:
            (compliant: bool, message: str)
        """
        engagements = cycle_record.engagements
        if len(engagements) < 3:
            return (
                True,
                f"Only {len(engagements)} engagement(s) recorded. "
                "Rotation rule applies from the 3rd TLPT onwards.",
            )
        issues: list[str] = []
        for i, engagement in enumerate(engagements):
            # Every 3rd engagement (1-indexed) must use an external tester
            if (i + 1) % 3 == 0:
                tester_ids = engagement.tester_ids
                tester_types = [
                    self._testers[tid].tester_type
                    for tid in tester_ids
                    if tid in self._testers
                ]
                has_external = TesterType.EXTERNAL in tester_types
                if not has_external:
                    issues.append(
                        f"Engagement #{i+1} ({engagement.tlpt_id}) is every-3rd "
                        "TLPT but no external tester is assigned "
                        "(DORA Art. 27(5) requires external tester for every 3rd TLPT)."
                    )
        if issues:
            return (False, "; ".join(issues))
        return (True, "External tester rotation compliance confirmed.")

    def assign_tester(
        self, engagement: TLPTEngagement, tester_id: str, is_lead: bool = False
    ) -> None:
        """Assign a tester to a TLPT engagement.

        Validates DORA Art. 27 qualification before assignment.

        Raises:
            ValueError: If the tester is not DORA-compliant.
        """
        compliant, deficiencies = self.verify_qualification(tester_id)
        if not compliant:
            raise ValueError(
                f"Cannot assign tester '{tester_id}': DORA Art. 27 non-compliant. "
                f"Deficiencies: {deficiencies}"
            )
        if tester_id not in engagement.tester_ids:
            engagement.tester_ids.append(tester_id)
        if is_lead:
            engagement.lead_tester_id = tester_id
        logger.info(
            "Assigned tester %s to engagement %s (lead=%s).",
            tester_id,
            engagement.tlpt_id,
            is_lead,
        )


# ---------------------------------------------------------------------------
# TLPT Workflow Manager
# ---------------------------------------------------------------------------


class TLPTWorkflowManager:
    """Manage the full TLPT lifecycle: pre-test → in-test → post-test → closure.

    Integrates FaultRay simulation results as pre-test readiness evidence,
    provides monitoring hooks during testing, and tracks post-test
    remediation to closure.

    Usage::

        workflow = TLPTWorkflowManager(graph, cycle_record)
        engagement = workflow.start_pre_test(tlpt_id="TLPT-2026-001")
        workflow.record_simulation_baseline(engagement, sim_results)
        workflow.advance_to_in_test(engagement)
        workflow.import_post_test_findings(engagement, findings)
        workflow.advance_to_post_test(engagement)
        workflow.request_management_sign_off(engagement, manager="CIO")
        workflow.close_engagement(engagement)
    """

    def __init__(
        self,
        graph: "InfraGraph",
        cycle_record: TLPTCycleRecord,
        organisation_name: str = "",
    ) -> None:
        self.graph = graph
        self.cycle_record = cycle_record
        self.organisation_name = organisation_name
        self._assessor = TLPTReadinessAssessor(graph, organisation_name)
        self._tester_manager = TLPTTesterManager()

    @property
    def tester_manager(self) -> TLPTTesterManager:
        """Access the tester manager for registering and assigning testers."""
        return self._tester_manager

    def start_pre_test(
        self,
        tlpt_id: str,
        scheduled_start: date | None = None,
    ) -> TLPTEngagement:
        """Begin the TLPT pre-test phase: create engagement and generate scope.

        Automatically generates the scope document from the current InfraGraph.
        """
        engagement = self._assessor.create_engagement(tlpt_id, scheduled_start)
        self._assessor.generate_scope_document(engagement)
        self.cycle_record.engagements.append(engagement)
        logger.info(
            "Pre-test phase started for TLPT %s. %s", tlpt_id, _TLPT_DISCLAIMER
        )
        return engagement

    def record_simulation_baseline(
        self,
        engagement: TLPTEngagement,
        simulation_results: dict,
    ) -> None:
        """Record FaultRay simulation results as pre-TLPT baseline evidence.

        This documents the resilience posture assessed via simulation before
        real TLPT commences.  The evidence is stored as notes on the
        ENV-03 checklist item.

        Args:
            engagement: The active TLPT engagement.
            simulation_results: Output from a FaultRay simulation run
                (e.g. from DORAEvidenceEngine.export_audit_package()).
        """
        for item in engagement.readiness_checklist:
            if item.item_id == "ENV-03":
                item.status = ChecklistItemStatus.SATISFIED
                item.evidence = (
                    f"FaultRay simulation completed at "
                    f"{datetime.now(timezone.utc).isoformat()}. "
                    f"Resilience score: {simulation_results.get('resilience_score', 'N/A')}. "
                    f"Compliant controls: {simulation_results.get('compliant_count', 'N/A')}."
                )
                item.notes = (
                    "FaultRay simulation is a PRE-TEST readiness tool only. "
                    "It does NOT replace actual TLPT on live production."
                )
                break
        logger.info(
            "FaultRay simulation baseline recorded for engagement %s.",
            engagement.tlpt_id,
        )

    def advance_to_in_test(self, engagement: TLPTEngagement) -> None:
        """Advance the engagement from PRE_TEST to IN_TEST phase.

        Validates readiness before allowing advancement.

        Raises:
            RuntimeError: If the engagement is not sufficiently ready.
        """
        status, deficiencies = self._assessor.assess_readiness(engagement)
        if status == TLPTReadinessStatus.NOT_READY:
            raise RuntimeError(
                f"Engagement {engagement.tlpt_id} is NOT ready for TLPT. "
                f"Resolve {len(deficiencies)} deficiency/deficiencies before proceeding: "
                f"{deficiencies[:3]} ..."
            )
        if status == TLPTReadinessStatus.PARTIALLY_READY:
            logger.warning(
                "Engagement %s is PARTIALLY ready. %d deficiency(ies) noted — "
                "proceeding with management awareness required. Deficiencies: %s",
                engagement.tlpt_id,
                len(deficiencies),
                deficiencies,
            )
        engagement.phase = TLPTPhase.IN_TEST
        engagement.actual_start = date.today()
        logger.info(
            "Engagement %s advanced to IN_TEST phase.", engagement.tlpt_id
        )

    def import_post_test_findings(
        self,
        engagement: TLPTEngagement,
        findings: list[dict],
    ) -> None:
        """Import TLPT findings from external testers as remediation items.

        Each finding dict should have:
        - finding (str): description of the finding
        - severity (str): "critical" | "high" | "medium" | "low"
        - recommended_action (str): remediation recommendation
        - owner (str, optional): assigned remediation owner

        Args:
            engagement: The active TLPT engagement.
            findings: List of finding dicts from the external testers' report.
        """
        for i, f in enumerate(findings):
            item = RemediationItem(
                item_id=f"REM-{engagement.tlpt_id}-{i+1:03d}",
                finding=f.get("finding", f"Finding {i+1}"),
                severity=f.get("severity", "medium"),
                recommended_action=f.get("recommended_action", "Review and remediate."),
                owner=f.get("owner", ""),
                due_date=(
                    date.today() + timedelta(days=30)
                    if f.get("severity") in ("critical", "high")
                    else date.today() + timedelta(days=90)
                ),
            )
            engagement.remediation_items.append(item)
        logger.info(
            "Imported %d finding(s) for engagement %s.",
            len(findings),
            engagement.tlpt_id,
        )

    def advance_to_post_test(self, engagement: TLPTEngagement) -> None:
        """Advance the engagement to POST_TEST phase."""
        if engagement.phase != TLPTPhase.IN_TEST:
            raise RuntimeError(
                f"Cannot advance to POST_TEST from phase '{engagement.phase.value}'. "
                "Engagement must be in IN_TEST phase."
            )
        engagement.phase = TLPTPhase.POST_TEST
        engagement.actual_end = date.today()
        logger.info(
            "Engagement %s advanced to POST_TEST phase. %d remediation item(s) to track.",
            engagement.tlpt_id,
            len(engagement.remediation_items),
        )

    def request_management_sign_off(
        self,
        engagement: TLPTEngagement,
        manager: str,
    ) -> None:
        """Request management sign-off for the TLPT results.

        DORA Art. 26 requires management review and approval of TLPT outcomes.
        """
        engagement.sign_off_status = SignOffStatus.PENDING
        engagement.sign_off_by = manager
        logger.info(
            "Management sign-off requested from '%s' for engagement %s.",
            manager,
            engagement.tlpt_id,
        )

    def approve_management_sign_off(
        self,
        engagement: TLPTEngagement,
        approver: str,
        notes: str = "",
    ) -> None:
        """Record management approval of TLPT results."""
        engagement.sign_off_status = SignOffStatus.APPROVED
        engagement.sign_off_by = approver
        engagement.sign_off_date = date.today()
        engagement.management_notes = notes
        logger.info(
            "Management sign-off approved by '%s' for engagement %s.",
            approver,
            engagement.tlpt_id,
        )

    def close_engagement(self, engagement: TLPTEngagement) -> None:
        """Close the TLPT engagement after all remediation is complete.

        Updates the cycle record with the last external test date and
        calculates the next TLPT due date.

        Raises:
            RuntimeError: If sign-off has not been approved.
        """
        if engagement.sign_off_status != SignOffStatus.APPROVED:
            raise RuntimeError(
                f"Cannot close engagement {engagement.tlpt_id}: "
                "management sign-off has not been approved."
            )
        open_critical = [
            r for r in engagement.remediation_items
            if not r.completed and r.severity in ("critical", "high")
        ]
        if open_critical:
            logger.warning(
                "Closing engagement %s with %d open critical/high remediation item(s). "
                "Ensure these are tracked and resolved promptly.",
                engagement.tlpt_id,
                len(open_critical),
            )
        engagement.phase = TLPTPhase.CLOSED
        # Update cycle record
        end = engagement.actual_end or date.today()
        is_external = any(
            self._tester_manager.get_tester(tid) is not None
            and self._tester_manager.get_tester(tid).tester_type == TesterType.EXTERNAL  # type: ignore[union-attr]
            for tid in engagement.tester_ids
        )
        if is_external:
            self.cycle_record.last_external_test_date = end
        # Schedule next TLPT — DORA Art. 26 requires at least every 3 years
        self.cycle_record.next_tlpt_due = date(end.year + 3, end.month, end.day)
        logger.info(
            "Engagement %s closed. Next TLPT due: %s.",
            engagement.tlpt_id,
            self.cycle_record.next_tlpt_due,
        )

    def readiness_report(self, engagement: TLPTEngagement) -> dict:
        """Export a full readiness and status report for the engagement."""
        status, deficiencies = self._assessor.assess_readiness(engagement)
        scope_summary = None
        if engagement.scope_document:
            scope_summary = {
                "scope_id": engagement.scope_document.scope_id,
                "critical_components": len(engagement.scope_document.critical_components),
                "excluded_components": len(engagement.scope_document.excluded_components),
                "attack_surface_summary": engagement.scope_document.attack_surface_summary,
                "disclaimer": _TLPT_DISCLAIMER,
            }
        checklist_summary = {
            item.category: {
                "satisfied": sum(1 for i in engagement.readiness_checklist if i.category == item.category and i.status == ChecklistItemStatus.SATISFIED),
                "unsatisfied": sum(1 for i in engagement.readiness_checklist if i.category == item.category and i.status == ChecklistItemStatus.UNSATISFIED),
                "needs_review": sum(1 for i in engagement.readiness_checklist if i.category == item.category and i.status == ChecklistItemStatus.NEEDS_REVIEW),
            }
            for item in engagement.readiness_checklist
        }
        return {
            "framework": "DORA",
            "article": "Article 26 — TLPT",
            "tlpt_id": engagement.tlpt_id,
            "organisation": engagement.organisation_name,
            "phase": engagement.phase.value,
            "readiness_status": status.value,
            "deficiencies": deficiencies,
            "scope_summary": scope_summary,
            "checklist_summary": checklist_summary,
            "remediation_items_total": len(engagement.remediation_items),
            "remediation_items_open": sum(1 for r in engagement.remediation_items if not r.completed),
            "sign_off_status": engagement.sign_off_status.value,
            "next_tlpt_due": self.cycle_record.next_tlpt_due.isoformat() if self.cycle_record.next_tlpt_due else None,
            "cycle_overdue": self.cycle_record.is_overdue(),
            "disclaimer": _TLPT_DISCLAIMER,
        }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _attack_surface_for_component(component: Component) -> str:
    """Summarise the attack surface of a component for the scope document."""
    surface_notes: dict[ComponentType, str] = {
        ComponentType.DATABASE: (
            "Network-accessible database service. Attack vectors: SQL injection, "
            "credential brute-force, unencrypted connections, privilege escalation."
        ),
        ComponentType.LOAD_BALANCER: (
            "External-facing entry point. Attack vectors: DDoS, TLS misconfiguration, "
            "header injection, traffic hijacking."
        ),
        ComponentType.APP_SERVER: (
            "Application logic tier. Attack vectors: RCE via vulnerability, "
            "SSRF, insecure deserialization, dependency vulnerabilities."
        ),
        ComponentType.WEB_SERVER: (
            "HTTP/HTTPS service. Attack vectors: XSS, CSRF, HTTP smuggling, "
            "directory traversal, TLS downgrade."
        ),
        ComponentType.CACHE: (
            "In-memory caching layer. Attack vectors: cache poisoning, "
            "unprotected port exposure, eviction manipulation."
        ),
        ComponentType.QUEUE: (
            "Message queue. Attack vectors: message injection, "
            "consumer spoofing, DLQ exploitation, unencrypted messages."
        ),
        ComponentType.STORAGE: (
            "Storage service. Attack vectors: misconfigured ACLs, "
            "pre-signed URL abuse, data exfiltration, ransomware."
        ),
        ComponentType.EXTERNAL_API: (
            "Third-party external API. Attack vectors: supply chain compromise, "
            "credential theft, API key exposure, insecure webhooks."
        ),
        ComponentType.AGENT_ORCHESTRATOR: (
            "AI agent orchestrator. Attack vectors: prompt injection, "
            "tool abuse, privilege escalation via agent actions."
        ),
    }
    base = surface_notes.get(
        component.type,
        f"Service ({component.type.value}). Standard network attack surface applies.",
    )
    extras: list[str] = []
    if not component.security.encryption_in_transit:
        extras.append("No encryption in transit detected — elevated interception risk.")
    if not component.security.auth_required:
        extras.append("Authentication not required — unauthenticated access possible.")
    if not component.security.network_segmented:
        extras.append("Network segmentation not configured — lateral movement risk.")
    return base + (" Additional risks: " + " ".join(extras) if extras else "")


def _build_attack_surface_summary(
    graph: "InfraGraph",
    critical_components: list[TLPTScopeComponent],
) -> str:
    if not critical_components:
        return "No critical components identified in scope."
    summary_parts = [
        f"TLPT scope covers {len(critical_components)} critical/important ICT function(s). "
        "Attack surface includes:"
    ]
    for comp in critical_components:
        summary_parts.append(f"  - {comp.component_name} ({comp.component_type}): {comp.attack_surface_notes}")
    summary_parts.append(
        "Note: FaultRay provides scope mapping based on infrastructure topology. "
        "Actual TLPT must be conducted by qualified testers on live production per DORA Art. 26-27."
    )
    return "\n".join(summary_parts)
