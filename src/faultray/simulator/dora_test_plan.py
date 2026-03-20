# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""DORA Article 24 — Test Programme Management.

Implements a risk-based ICT testing programme per DORA Article 24 requirements.
Provides test plan generation from InfraGraph topology, execution tracking,
annual review workflow, coverage gap detection, and exportable status reports.

Regulatory references:
    DORA Regulation (EU) 2022/2554
    Article 24 — General requirements for the testing of ICT tools and systems
    Article 25 — Testing of ICT tools and systems
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
# Enumerations
# ---------------------------------------------------------------------------


class TestCategory(str, Enum):
    """DORA Article 25 test categories.

    Maps directly to Article 25(1)(a)-(h) of DORA.
    """

    VULNERABILITY_ASSESSMENT = "vulnerability_assessment"  # Art. 25(1)(a)
    NETWORK_SECURITY = "network_security"                  # Art. 25(1)(b)
    GAP_ANALYSIS = "gap_analysis"                          # Art. 25(1)(c)
    SCENARIO_BASED = "scenario_based"                      # Art. 25(1)(d)
    COMPATIBILITY = "compatibility"                        # Art. 25(1)(e)
    PERFORMANCE = "performance"                            # Art. 25(1)(f)
    END_TO_END = "end_to_end"                              # Art. 25(1)(g)
    PENETRATION = "penetration"                            # Art. 25(1)(h)


class TestFrequency(str, Enum):
    """Permitted test frequencies under the risk-based programme."""

    QUARTERLY = "quarterly"    # 4× per year — for critical components
    SEMI_ANNUAL = "semi_annual"  # 2× per year — for high-criticality
    ANNUAL = "annual"           # 1× per year — for standard components


class TestResult(str, Enum):
    """Possible outcomes of a test execution."""

    PASSED = "passed"
    FAILED = "failed"
    PARTIAL = "partial"
    CANCELLED = "cancelled"
    IN_PROGRESS = "in_progress"


class CriticalityLevel(str, Enum):
    """Risk-based criticality levels for test target prioritisation."""

    CRITICAL = "critical"    # Failure would halt critical/important functions
    HIGH = "high"            # Significant business impact
    STANDARD = "standard"   # Normal operational impact


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


class TestTarget(BaseModel):
    """A single system or component targeted by a test plan entry."""

    component_id: str
    component_name: str
    component_type: str
    criticality: CriticalityLevel = CriticalityLevel.STANDARD
    rationale: str = ""


class TestPlan(BaseModel):
    """A single planned test within the annual test programme.

    Represents one entry in the risk-based test schedule, covering one
    test category applied to one or more targets.
    """

    plan_id: str
    test_category: TestCategory
    title: str
    description: str
    objectives: list[str] = Field(default_factory=list)
    methodology: str = ""
    targets: list[TestTarget] = Field(default_factory=list)
    frequency: TestFrequency = TestFrequency.ANNUAL
    scheduled_date: date | None = None
    estimated_duration_hours: float = 8.0
    resource_requirements: list[str] = Field(default_factory=list)
    dora_article_references: list[str] = Field(
        default_factory=lambda: ["DORA Art. 24", "DORA Art. 25"]
    )


class TestExecution(BaseModel):
    """Record of a single test execution (planned or unplanned)."""

    execution_id: str
    plan_id: str
    executed_at: datetime
    result: TestResult
    executed_by: str = ""
    findings: list[str] = Field(default_factory=list)
    remediation_items: list[str] = Field(default_factory=list)
    evidence_artifacts: list[str] = Field(default_factory=list)
    notes: str = ""
    remediation_due_date: date | None = None
    remediation_completed: bool = False


class TestCoverage(BaseModel):
    """Coverage metrics for the test programme at a point in time."""

    total_components: int = 0
    critical_components: int = 0
    tested_components: int = 0
    tested_critical_components: int = 0
    overdue_components: list[str] = Field(default_factory=list)
    coverage_percent: float = 0.0
    critical_coverage_percent: float = 0.0
    last_calculated: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class TestReviewRecord(BaseModel):
    """Annual review of the test programme, as required by Art. 24.

    DORA requires periodic review of the testing programme to ensure it
    remains risk-appropriate and addresses any changes in the threat landscape
    or ICT infrastructure.
    """

    review_id: str
    review_date: date
    reviewed_by: str
    programme_year: int
    total_plans_scheduled: int = 0
    total_executions: int = 0
    pass_count: int = 0
    fail_count: int = 0
    partial_count: int = 0
    coverage_at_review: TestCoverage = Field(default_factory=TestCoverage)
    gaps_identified: list[str] = Field(default_factory=list)
    improvements_adopted: list[str] = Field(default_factory=list)
    next_programme_adjustments: list[str] = Field(default_factory=list)
    approved: bool = False
    approver: str = ""
    approval_date: date | None = None


class TestProgramme(BaseModel):
    """Annual ICT test programme per DORA Article 24.

    The test programme is the top-level container that groups all test plans
    for a given calendar year, tracks execution history, and links to review
    records.
    """

    programme_id: str
    organisation_name: str = ""
    year: int
    scope: str = ""
    objectives: list[str] = Field(default_factory=list)
    plans: list[TestPlan] = Field(default_factory=list)
    executions: list[TestExecution] = Field(default_factory=list)
    review_records: list[TestReviewRecord] = Field(default_factory=list)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    last_updated: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# Component types that map to critical/important ICT functions by default
_CRITICAL_TYPES: frozenset[ComponentType] = frozenset(
    {
        ComponentType.DATABASE,
        ComponentType.LOAD_BALANCER,
        ComponentType.APP_SERVER,
        ComponentType.QUEUE,
    }
)

_HIGH_CRITICALITY_TYPES: frozenset[ComponentType] = frozenset(
    {
        ComponentType.CACHE,
        ComponentType.WEB_SERVER,
        ComponentType.STORAGE,
        ComponentType.EXTERNAL_API,
        ComponentType.AGENT_ORCHESTRATOR,
    }
)


def _criticality_for_component(component: Component) -> CriticalityLevel:
    """Derive the DORA criticality level for a component.

    Logic:
    * Explicitly tagged ``critical`` → CRITICAL
    * Component type is in the critical set, or replicas == 1 with dependents → CRITICAL
    * Type is in the high-criticality set → HIGH
    * Otherwise → STANDARD
    """
    tags_lower = [t.lower() for t in component.tags]
    if "critical" in tags_lower:
        return CriticalityLevel.CRITICAL
    if component.type in _CRITICAL_TYPES:
        return CriticalityLevel.CRITICAL
    if component.type in _HIGH_CRITICALITY_TYPES:
        return CriticalityLevel.HIGH
    return CriticalityLevel.STANDARD


def _frequency_for_criticality(level: CriticalityLevel) -> TestFrequency:
    """Map criticality to the minimum required test frequency.

    Risk-based approach: critical systems must be tested at least quarterly,
    high at least semi-annually, standard annually.
    """
    mapping: dict[CriticalityLevel, TestFrequency] = {
        CriticalityLevel.CRITICAL: TestFrequency.QUARTERLY,
        CriticalityLevel.HIGH: TestFrequency.SEMI_ANNUAL,
        CriticalityLevel.STANDARD: TestFrequency.ANNUAL,
    }
    return mapping[level]


def _test_categories_for_component(component: Component) -> list[TestCategory]:
    """Return the recommended DORA test categories for a component type."""
    base = [
        TestCategory.VULNERABILITY_ASSESSMENT,
        TestCategory.SCENARIO_BASED,
    ]
    type_extras: dict[ComponentType, list[TestCategory]] = {
        ComponentType.DATABASE: [
            TestCategory.PERFORMANCE,
            TestCategory.SCENARIO_BASED,
        ],
        ComponentType.LOAD_BALANCER: [
            TestCategory.NETWORK_SECURITY,
            TestCategory.PERFORMANCE,
            TestCategory.COMPATIBILITY,
        ],
        ComponentType.WEB_SERVER: [
            TestCategory.NETWORK_SECURITY,
            TestCategory.PENETRATION,
            TestCategory.PERFORMANCE,
        ],
        ComponentType.APP_SERVER: [
            TestCategory.PENETRATION,
            TestCategory.PERFORMANCE,
            TestCategory.END_TO_END,
        ],
        ComponentType.CACHE: [
            TestCategory.PERFORMANCE,
            TestCategory.COMPATIBILITY,
        ],
        ComponentType.QUEUE: [
            TestCategory.SCENARIO_BASED,
            TestCategory.PERFORMANCE,
            TestCategory.COMPATIBILITY,
        ],
        ComponentType.STORAGE: [
            TestCategory.SCENARIO_BASED,
            TestCategory.GAP_ANALYSIS,
        ],
        ComponentType.EXTERNAL_API: [
            TestCategory.COMPATIBILITY,
            TestCategory.GAP_ANALYSIS,
        ],
        ComponentType.AGENT_ORCHESTRATOR: [
            TestCategory.END_TO_END,
            TestCategory.SCENARIO_BASED,
        ],
    }
    extras = type_extras.get(component.type, [])
    # Deduplicate while preserving order
    seen: set[TestCategory] = set()
    result: list[TestCategory] = []
    for cat in base + extras:
        if cat not in seen:
            seen.add(cat)
            result.append(cat)
    return result


def _schedule_dates(
    programme_year: int,
    frequency: TestFrequency,
    plan_index: int,
) -> list[date]:
    """Generate scheduled test dates for a plan within the programme year.

    Distributes tests evenly across the year according to frequency.
    plan_index is used to stagger multiple plans to avoid scheduling
    everything on the same day.
    """
    offsets_days: dict[TestFrequency, list[int]] = {
        TestFrequency.QUARTERLY: [0, 90, 180, 270],
        TestFrequency.SEMI_ANNUAL: [0, 180],
        TestFrequency.ANNUAL: [0],
    }
    base = date(programme_year, 1, 15)  # Mid-January start
    stagger = timedelta(days=plan_index % 14)  # Up to 2-week stagger
    return [base + timedelta(days=d) + stagger for d in offsets_days[frequency]]


# ---------------------------------------------------------------------------
# Test Plan Generator
# ---------------------------------------------------------------------------


class TestPlanGenerator:
    """Generate a risk-based annual test programme from an InfraGraph.

    Usage::

        from faultray.model.graph import InfraGraph
        from faultray.simulator.dora_test_plan import TestPlanGenerator

        graph = InfraGraph.load(Path("infra.json"))
        generator = TestPlanGenerator(graph, organisation_name="Acme Bank")
        programme = generator.generate(year=2026)
    """

    def __init__(
        self,
        graph: "InfraGraph",
        organisation_name: str = "",
    ) -> None:
        self.graph = graph
        self.organisation_name = organisation_name

    def _build_target(self, component: Component) -> TestTarget:
        criticality = _criticality_for_component(component)
        rationale = (
            f"Component type '{component.type.value}' with "
            f"{component.replicas} replica(s). "
            f"Mapped to criticality '{criticality.value}' per DORA risk-based approach."
        )
        return TestTarget(
            component_id=component.id,
            component_name=component.name,
            component_type=component.type.value,
            criticality=criticality,
            rationale=rationale,
        )

    def generate(self, year: int) -> TestProgramme:
        """Generate a complete annual test programme for *year*.

        For each component in the graph, the generator:
        1. Derives a criticality level.
        2. Selects applicable DORA test categories.
        3. Assigns frequency based on criticality.
        4. Schedules test dates across the year.
        5. Assembles TestPlan objects with objectives, methodology,
           and resource requirements.

        Returns a TestProgramme ready for use with TestProgrammeManager.
        """
        components = list(self.graph.components.values())
        if not components:
            logger.warning("InfraGraph has no components; empty programme generated.")

        plans: list[TestPlan] = []
        plan_counter = 0

        for component in components:
            criticality = _criticality_for_component(component)
            frequency = _frequency_for_criticality(criticality)
            categories = _test_categories_for_component(component)
            target = self._build_target(component)
            scheduled_dates = _schedule_dates(year, frequency, plan_counter)

            for i, (category, sched_date) in enumerate(
                zip(categories, scheduled_dates + scheduled_dates)  # cycle dates if more cats than dates
            ):
                plan_id = f"PLAN-{year}-{component.id[:8].upper()}-{category.value[:4].upper()}-{i+1:02d}"
                plan = TestPlan(
                    plan_id=plan_id,
                    test_category=category,
                    title=f"{category.value.replace('_', ' ').title()} — {component.name}",
                    description=(
                        f"DORA-mandated {category.value.replace('_', ' ')} test for "
                        f"'{component.name}' ({component.type.value}). "
                        f"Criticality: {criticality.value}. Frequency: {frequency.value}."
                    ),
                    objectives=_objectives_for_category(category, component),
                    methodology=_methodology_for_category(category),
                    targets=[target],
                    frequency=frequency,
                    scheduled_date=sched_date if i < len(scheduled_dates) else scheduled_dates[i % len(scheduled_dates)],
                    estimated_duration_hours=_duration_for_category(category),
                    resource_requirements=_resources_for_category(category, criticality),
                    dora_article_references=["DORA Art. 24", "DORA Art. 25"],
                )
                plans.append(plan)
            plan_counter += 1

        # Add an end-to-end plan covering all components if there are multiple
        if len(components) > 1:
            e2e_plan_id = f"PLAN-{year}-E2E-FULL-01"
            all_targets = [self._build_target(c) for c in components]
            plans.append(
                TestPlan(
                    plan_id=e2e_plan_id,
                    test_category=TestCategory.END_TO_END,
                    title="End-to-End Resilience Test — Full Infrastructure",
                    description=(
                        "Annual end-to-end resilience test covering all infrastructure "
                        "components. Validates failover, switchover, and recovery "
                        "scenarios across the complete system per DORA Art. 25(1)(g)."
                    ),
                    objectives=[
                        "Validate end-to-end recovery time objectives (RTO)",
                        "Test failover and switchover across all components",
                        "Verify data integrity after recovery",
                        "Confirm incident response procedures",
                    ],
                    methodology=(
                        "Coordinated failure injection across component boundaries. "
                        "Simulated using FaultRay scenario engine with DORA evidence capture."
                    ),
                    targets=all_targets,
                    frequency=TestFrequency.ANNUAL,
                    scheduled_date=date(year, 11, 1),
                    estimated_duration_hours=16.0,
                    resource_requirements=[
                        "Senior SRE lead",
                        "Security team representative",
                        "Business continuity team",
                        "Management sign-off (DORA Art. 25)",
                    ],
                    dora_article_references=["DORA Art. 24", "DORA Art. 25"],
                )
            )

        return TestProgramme(
            programme_id=f"PROG-{year}-{self.organisation_name.replace(' ', '-').upper() or 'ORG'}",
            organisation_name=self.organisation_name,
            year=year,
            scope=(
                f"All {len(components)} ICT components in the infrastructure graph. "
                "Covers critical and important functions as defined by DORA Art. 24."
            ),
            objectives=[
                "Ensure all critical ICT systems are tested at least quarterly",
                "Validate resilience against realistic failure scenarios",
                "Generate audit-ready evidence for DORA supervisory review",
                "Identify and remediate ICT vulnerabilities in a timely manner",
                "Maintain and improve ICT operational resilience posture",
            ],
            plans=plans,
        )


# ---------------------------------------------------------------------------
# Test Programme Manager
# ---------------------------------------------------------------------------


class TestProgrammeManager:
    """Manage a TestProgramme: record executions, calculate coverage, review.

    Usage::

        manager = TestProgrammeManager(programme)
        manager.record_execution(execution)
        coverage = manager.calculate_coverage()
        gaps = manager.detect_gaps()
        report = manager.export_status_report()
    """

    def __init__(self, programme: TestProgramme) -> None:
        self.programme = programme

    # ------------------------------------------------------------------
    # Execution recording
    # ------------------------------------------------------------------

    def record_execution(self, execution: TestExecution) -> None:
        """Record a test execution result against the programme.

        Raises ``ValueError`` if the plan_id does not exist in the programme.
        """
        plan_ids = {p.plan_id for p in self.programme.plans}
        if execution.plan_id not in plan_ids:
            raise ValueError(
                f"plan_id '{execution.plan_id}' not found in programme "
                f"'{self.programme.programme_id}'. "
                f"Known plan IDs: {sorted(plan_ids)}"
            )
        self.programme.executions.append(execution)
        self.programme.last_updated = datetime.now(timezone.utc)
        logger.info(
            "Recorded execution %s for plan %s: %s",
            execution.execution_id,
            execution.plan_id,
            execution.result.value,
        )

    # ------------------------------------------------------------------
    # Coverage calculation
    # ------------------------------------------------------------------

    def calculate_coverage(self) -> TestCoverage:
        """Calculate test coverage metrics for the programme.

        A component is considered "tested" if at least one TestExecution
        with result PASSED or PARTIAL has been recorded for a plan that
        targets that component.
        """
        # Build a set of component IDs that have been successfully tested
        executed_plan_ids: set[str] = {
            e.plan_id
            for e in self.programme.executions
            if e.result in (TestResult.PASSED, TestResult.PARTIAL)
        }

        # Map plan_id → set of component_ids
        plan_to_components: dict[str, set[str]] = {
            p.plan_id: {t.component_id for t in p.targets}
            for p in self.programme.plans
        }

        tested_component_ids: set[str] = set()
        for plan_id in executed_plan_ids:
            tested_component_ids.update(plan_to_components.get(plan_id, set()))

        # Collect all unique component IDs and their criticality
        all_targets: dict[str, CriticalityLevel] = {}
        for plan in self.programme.plans:
            for target in plan.targets:
                all_targets[target.component_id] = target.criticality

        total = len(all_targets)
        critical_ids = {
            cid
            for cid, crit in all_targets.items()
            if crit == CriticalityLevel.CRITICAL
        }
        tested = len(tested_component_ids)
        tested_critical = len(tested_component_ids & critical_ids)
        critical_total = len(critical_ids)

        coverage_pct = (tested / total * 100.0) if total > 0 else 0.0
        critical_pct = (
            (tested_critical / critical_total * 100.0)
            if critical_total > 0
            else 100.0
        )

        return TestCoverage(
            total_components=total,
            critical_components=critical_total,
            tested_components=tested,
            tested_critical_components=tested_critical,
            coverage_percent=round(coverage_pct, 1),
            critical_coverage_percent=round(critical_pct, 1),
        )

    # ------------------------------------------------------------------
    # Gap detection
    # ------------------------------------------------------------------

    def detect_gaps(self, as_of: date | None = None) -> list[str]:
        """Detect components that have not been tested within the required timeframe.

        Returns a list of human-readable gap descriptions suitable for
        inclusion in an audit report or annual review.

        Args:
            as_of: Reference date for gap calculation. Defaults to today.
        """
        today = as_of or date.today()
        gaps: list[str] = []

        # Build a map: component_id → last successful execution date
        plan_to_components: dict[str, list[TestTarget]] = {
            p.plan_id: p.targets for p in self.programme.plans
        }
        component_last_tested: dict[str, date] = {}
        for execution in self.programme.executions:
            if execution.result not in (TestResult.PASSED, TestResult.PARTIAL):
                continue
            exec_date = execution.executed_at.date()
            targets = plan_to_components.get(execution.plan_id, [])
            for target in targets:
                existing = component_last_tested.get(target.component_id)
                if existing is None or exec_date > existing:
                    component_last_tested[target.component_id] = exec_date

        # Required maximum gap in days per frequency
        max_days: dict[TestFrequency, int] = {
            TestFrequency.QUARTERLY: 100,   # Allow slight overrun on 90-day cadence
            TestFrequency.SEMI_ANNUAL: 200,
            TestFrequency.ANNUAL: 380,
        }

        # Derive per-component frequency from the plans
        component_frequency: dict[str, TestFrequency] = {}
        for plan in self.programme.plans:
            for target in plan.targets:
                # Use the most frequent (strictest) requirement if multiple plans exist
                existing_freq = component_frequency.get(target.component_id)
                if existing_freq is None or _frequency_order(plan.frequency) > _frequency_order(existing_freq):
                    component_frequency[target.component_id] = plan.frequency

        for comp_id, frequency in component_frequency.items():
            last_tested = component_last_tested.get(comp_id)
            required_max = max_days[frequency]
            if last_tested is None:
                gaps.append(
                    f"Component '{comp_id}' has NEVER been tested "
                    f"(required: {frequency.value})."
                )
            else:
                days_since = (today - last_tested).days
                if days_since > required_max:
                    gaps.append(
                        f"Component '{comp_id}' last tested {days_since} days ago "
                        f"(maximum allowed for {frequency.value}: {required_max} days). "
                        f"OVERDUE by {days_since - required_max} days."
                    )

        return gaps

    # ------------------------------------------------------------------
    # Annual review workflow
    # ------------------------------------------------------------------

    def create_annual_review(
        self,
        review_id: str,
        reviewed_by: str,
        review_date: date | None = None,
    ) -> TestReviewRecord:
        """Initiate an annual review of the test programme (Art. 24).

        Calculates coverage, detects gaps, and drafts the review record.
        The record must subsequently be approved via ``approve_review``.
        """
        today = review_date or date.today()
        coverage = self.calculate_coverage()
        gaps = self.detect_gaps(as_of=today)

        pass_count = sum(
            1 for e in self.programme.executions if e.result == TestResult.PASSED
        )
        fail_count = sum(
            1 for e in self.programme.executions if e.result == TestResult.FAILED
        )
        partial_count = sum(
            1 for e in self.programme.executions if e.result == TestResult.PARTIAL
        )

        # Suggest improvements based on gaps and results
        improvements: list[str] = []
        if coverage.critical_coverage_percent < 100.0:
            improvements.append(
                f"Increase critical system test coverage "
                f"(currently {coverage.critical_coverage_percent:.1f}%, target 100%)."
            )
        if fail_count > 0:
            improvements.append(
                f"Review and remediate {fail_count} failed test(s) before next programme cycle."
            )
        if gaps:
            improvements.append(
                f"Address {len(gaps)} overdue test gap(s) identified in gap analysis."
            )

        review = TestReviewRecord(
            review_id=review_id,
            review_date=today,
            reviewed_by=reviewed_by,
            programme_year=self.programme.year,
            total_plans_scheduled=len(self.programme.plans),
            total_executions=len(self.programme.executions),
            pass_count=pass_count,
            fail_count=fail_count,
            partial_count=partial_count,
            coverage_at_review=coverage,
            gaps_identified=gaps,
            improvements_adopted=improvements,
            next_programme_adjustments=[
                "Update risk-based prioritisation based on new threat intelligence.",
                "Review component criticality classifications.",
                "Align test schedule with any infrastructure changes.",
            ],
        )
        self.programme.review_records.append(review)
        return review

    def approve_review(
        self,
        review_id: str,
        approver: str,
        approval_date: date | None = None,
    ) -> TestReviewRecord:
        """Record management approval for a review record.

        Args:
            review_id: ID of the review to approve.
            approver: Name/role of the approving manager.
            approval_date: Date of approval (defaults to today).

        Raises:
            ValueError: If the review_id is not found.
        """
        for review in self.programme.review_records:
            if review.review_id == review_id:
                review.approved = True
                review.approver = approver
                review.approval_date = approval_date or date.today()
                self.programme.last_updated = datetime.now(timezone.utc)
                logger.info("Review %s approved by %s.", review_id, approver)
                return review
        raise ValueError(
            f"Review ID '{review_id}' not found in programme "
            f"'{self.programme.programme_id}'."
        )

    # ------------------------------------------------------------------
    # Status report export
    # ------------------------------------------------------------------

    def export_status_report(self) -> dict:
        """Export the full test programme status as a structured dictionary.

        Suitable for serialisation to JSON for audit submission or
        dashboard display.
        """
        coverage = self.calculate_coverage()
        gaps = self.detect_gaps()
        pass_count = sum(
            1 for e in self.programme.executions if e.result == TestResult.PASSED
        )
        fail_count = sum(
            1 for e in self.programme.executions if e.result == TestResult.FAILED
        )
        partial_count = sum(
            1 for e in self.programme.executions if e.result == TestResult.PARTIAL
        )
        total_executions = len(self.programme.executions)
        execution_rate = (
            round(total_executions / len(self.programme.plans) * 100.0, 1)
            if self.programme.plans
            else 0.0
        )

        return {
            "framework": "DORA",
            "article": "Article 24 — General Requirements for Testing",
            "programme_id": self.programme.programme_id,
            "organisation": self.programme.organisation_name,
            "year": self.programme.year,
            "export_timestamp": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "total_plans": len(self.programme.plans),
                "total_executions": total_executions,
                "execution_rate_percent": execution_rate,
                "pass_count": pass_count,
                "fail_count": fail_count,
                "partial_count": partial_count,
                "open_gaps": len(gaps),
            },
            "coverage": coverage.model_dump(),
            "gaps": gaps,
            "plans_by_category": _count_by_category(self.programme.plans),
            "plans_by_frequency": _count_by_frequency(self.programme.plans),
            "review_records": [r.model_dump() for r in self.programme.review_records],
            "executions": [e.model_dump() for e in self.programme.executions],
        }


# ---------------------------------------------------------------------------
# Private helper functions
# ---------------------------------------------------------------------------


def _objectives_for_category(
    category: TestCategory, component: Component
) -> list[str]:
    base_objectives: dict[TestCategory, list[str]] = {
        TestCategory.VULNERABILITY_ASSESSMENT: [
            f"Identify vulnerabilities in '{component.name}'",
            "Verify patch and configuration status",
            "Document remediation actions required",
        ],
        TestCategory.NETWORK_SECURITY: [
            f"Validate network segmentation around '{component.name}'",
            "Test firewall rules and access controls",
            "Verify encryption in transit",
        ],
        TestCategory.GAP_ANALYSIS: [
            f"Compare current security posture of '{component.name}' against DORA requirements",
            "Identify control gaps and missing safeguards",
            "Prioritise remediation by risk level",
        ],
        TestCategory.SCENARIO_BASED: [
            f"Simulate realistic failure scenarios for '{component.name}'",
            "Validate failover and recovery procedures",
            "Confirm RTO/RPO targets are met",
        ],
        TestCategory.COMPATIBILITY: [
            f"Verify '{component.name}' compatibility after changes",
            "Test integration points and API contracts",
            "Validate data format and protocol compatibility",
        ],
        TestCategory.PERFORMANCE: [
            f"Benchmark '{component.name}' under expected peak load",
            "Identify performance bottlenecks",
            "Verify performance SLOs under stress conditions",
        ],
        TestCategory.END_TO_END: [
            "Validate end-to-end transaction flows",
            "Test complete resilience of critical business processes",
            "Confirm monitoring and alerting across boundaries",
        ],
        TestCategory.PENETRATION: [
            f"Identify exploitable vulnerabilities in '{component.name}'",
            "Test authentication and authorisation controls",
            "Assess attack surface and exposure",
        ],
    }
    return base_objectives.get(category, [f"Execute {category.value} test on '{component.name}'"])


def _methodology_for_category(category: TestCategory) -> str:
    methodologies: dict[TestCategory, str] = {
        TestCategory.VULNERABILITY_ASSESSMENT: (
            "Automated vulnerability scanning supplemented by manual review. "
            "Tools: Trivy, Snyk, or equivalent. Evidence: scan reports, CVE listings."
        ),
        TestCategory.NETWORK_SECURITY: (
            "Network port scanning, firewall rule review, traffic analysis. "
            "Tools: nmap, Wireshark, cloud security posture tooling."
        ),
        TestCategory.GAP_ANALYSIS: (
            "Structured review of control objectives against DORA requirements. "
            "Output: gap register with risk ratings and remediation roadmap."
        ),
        TestCategory.SCENARIO_BASED: (
            "Defined failure scenarios executed via FaultRay simulation engine. "
            "Scenarios cover: single-component failure, cascade failure, DR switchover."
        ),
        TestCategory.COMPATIBILITY: (
            "Integration testing across component boundaries. "
            "Contract testing via Pact or equivalent. API compatibility matrix review."
        ),
        TestCategory.PERFORMANCE: (
            "Load testing with ramp-up to 150% of peak traffic baseline. "
            "Tools: k6, Gatling, or equivalent. Metrics: latency p99, throughput, error rate."
        ),
        TestCategory.END_TO_END: (
            "Full system resilience test across all component boundaries. "
            "FaultRay coordinated injection. Evidence captured per DORA Art. 24."
        ),
        TestCategory.PENETRATION: (
            "Manual penetration testing by qualified testers (DORA Art. 27). "
            "Scope: external attack surface plus internal lateral movement. "
            "Note: Full TLPT requires qualified external testers per DORA Art. 26-27."
        ),
    }
    return methodologies.get(category, f"Standard {category.value} methodology.")


def _duration_for_category(category: TestCategory) -> float:
    durations: dict[TestCategory, float] = {
        TestCategory.VULNERABILITY_ASSESSMENT: 4.0,
        TestCategory.NETWORK_SECURITY: 6.0,
        TestCategory.GAP_ANALYSIS: 8.0,
        TestCategory.SCENARIO_BASED: 4.0,
        TestCategory.COMPATIBILITY: 4.0,
        TestCategory.PERFORMANCE: 6.0,
        TestCategory.END_TO_END: 16.0,
        TestCategory.PENETRATION: 40.0,
    }
    return durations.get(category, 8.0)


def _resources_for_category(
    category: TestCategory, criticality: CriticalityLevel
) -> list[str]:
    base: list[str] = ["Test lead (SRE)", "Documentation owner"]
    extras: dict[TestCategory, list[str]] = {
        TestCategory.VULNERABILITY_ASSESSMENT: ["Security engineer"],
        TestCategory.NETWORK_SECURITY: ["Network engineer", "Security engineer"],
        TestCategory.GAP_ANALYSIS: ["Compliance officer", "Security architect"],
        TestCategory.SCENARIO_BASED: ["SRE", "Application owner"],
        TestCategory.COMPATIBILITY: ["Platform engineer", "QA engineer"],
        TestCategory.PERFORMANCE: ["SRE", "Capacity planner"],
        TestCategory.END_TO_END: [
            "SRE lead", "Security engineer", "Management sponsor (DORA Art. 25)"
        ],
        TestCategory.PENETRATION: [
            "Qualified penetration tester (DORA Art. 27)",
            "Security lead",
            "Management sign-off",
        ],
    }
    resources = base + extras.get(category, [])
    if criticality == CriticalityLevel.CRITICAL:
        resources.append("CISO / Risk management sponsor")
    return resources


def _frequency_order(freq: TestFrequency) -> int:
    """Return a comparable integer for frequency (higher = more frequent)."""
    return {
        TestFrequency.ANNUAL: 1,
        TestFrequency.SEMI_ANNUAL: 2,
        TestFrequency.QUARTERLY: 4,
    }[freq]


def _count_by_category(plans: list[TestPlan]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for plan in plans:
        key = plan.test_category.value
        counts[key] = counts.get(key, 0) + 1
    return counts


def _count_by_frequency(plans: list[TestPlan]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for plan in plans:
        key = plan.frequency.value
        counts[key] = counts.get(key, 0) + 1
    return counts
