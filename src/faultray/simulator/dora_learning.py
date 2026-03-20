# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""DORA Article 13 — Learning and Evolving Engine.

Implements the post-incident and post-test learning framework required by
DORA (Digital Operational Resilience Act) Article 13: financial entities must
draw lessons from ICT-related incidents and resilience tests, translate them
into improvement actions, and demonstrate a culture of continuous improvement.

Key capabilities:
- Structured post-incident review templates with timeline and root cause
- Post-test learning records linked to simulation runs
- Trend analysis for recurring failure modes
- Improvement velocity tracking (discovery → resolution time)
- Knowledge base of lessons learned with pattern detection
- ICT learning maturity assessment (1–5 scale)
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from statistics import mean

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class ReviewStatus(str, Enum):
    """Workflow state of a post-incident or post-test review."""

    PENDING = "pending"
    DRAFT = "draft"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    CLOSED = "closed"


class ActionStatus(str, Enum):
    """Implementation state for an improvement action."""

    OPEN = "open"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    OVERDUE = "overdue"


class ActionPriority(str, Enum):
    """Priority classification for improvement actions."""

    CRITICAL = "critical"   # Must be resolved immediately (e.g. regulatory)
    HIGH = "high"           # Resolve within 30 days
    MEDIUM = "medium"       # Resolve within 90 days
    LOW = "low"             # Best-effort


class FailureMode(str, Enum):
    """Taxonomy of recurring failure patterns for trend detection."""

    SINGLE_POINT_OF_FAILURE = "single_point_of_failure"
    CAPACITY_EXHAUSTION = "capacity_exhaustion"
    DEPENDENCY_FAILURE = "dependency_failure"
    CONFIGURATION_ERROR = "configuration_error"
    DEPLOYMENT_FAILURE = "deployment_failure"
    SECURITY_INCIDENT = "security_incident"
    DATA_INTEGRITY = "data_integrity"
    NETWORK_PARTITION = "network_partition"
    MONITORING_GAP = "monitoring_gap"
    RUNBOOK_MISSING = "runbook_missing"
    OTHER = "other"


class MaturityLevel(int, Enum):
    """ICT learning maturity scale per DORA Article 13."""

    INITIAL = 1       # Ad-hoc reviews; no systematic process
    DEVELOPING = 2    # Reviews happen but inconsistently
    DEFINED = 3       # Structured process; templates in use
    MANAGED = 4       # Metrics tracked; improvement actions completed
    OPTIMISING = 5    # Continuous learning loop; trend-driven improvements


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class TimelineEvent(BaseModel):
    """A single event in the incident timeline."""

    timestamp: datetime
    description: str
    actor: str = ""
    event_type: str = "observation"  # detection, escalation, mitigation, resolution, observation


class RootCauseAnalysis(BaseModel):
    """Structured root cause analysis output."""

    primary_cause: str
    contributing_factors: list[str] = Field(default_factory=list)
    failure_mode: FailureMode = FailureMode.OTHER
    affected_component_ids: list[str] = Field(default_factory=list)
    five_whys: list[str] = Field(default_factory=list)


class ImprovementAction(BaseModel):
    """A concrete action item resulting from a review.

    Tracks ownership, deadline, and completion evidence as required
    by DORA Article 13(3) for follow-through on identified lessons.
    """

    action_id: str = Field(default_factory=lambda: f"IMP-{uuid.uuid4().hex[:8].upper()}")
    description: str
    owner: str = "ICT Risk Manager"
    priority: ActionPriority = ActionPriority.MEDIUM
    status: ActionStatus = ActionStatus.OPEN
    due_date: date = Field(
        default_factory=lambda: (datetime.now(timezone.utc) + timedelta(days=90)).date()
    )
    completion_date: date | None = None
    evidence: str = ""
    source_review_id: str = ""
    failure_mode: FailureMode = FailureMode.OTHER

    @property
    def days_to_resolution(self) -> int | None:
        """Days from creation (approximated via due date context) to completion."""
        if self.completion_date is None:
            return None
        # Approximate creation as due_date minus typical lead time per priority
        lead_days = {"critical": 7, "high": 30, "medium": 90, "low": 180}
        lead = lead_days.get(self.priority.value, 90)
        created = self.due_date - timedelta(days=lead)
        return (self.completion_date - created).days

    def is_overdue(self) -> bool:
        today = datetime.now(timezone.utc).date()
        return self.status not in (ActionStatus.COMPLETED, ActionStatus.CANCELLED) and self.due_date < today


class LessonLearned(BaseModel):
    """A distilled lesson from a review, stored in the knowledge base.

    Lessons are catalogued with their failure mode so they can be surfaced
    when similar issues recur, forming the knowledge base described in
    DORA Article 13(2).
    """

    lesson_id: str = Field(default_factory=lambda: f"LL-{uuid.uuid4().hex[:8].upper()}")
    summary: str
    detail: str = ""
    failure_mode: FailureMode = FailureMode.OTHER
    source_review_id: str = ""
    source_type: str = "incident"  # incident | test
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    tags: list[str] = Field(default_factory=list)
    validated: bool = False


class PostIncidentReview(BaseModel):
    """Structured post-incident review (PIR).

    Covers the full lifecycle from detection through resolution and captures
    all artefacts required by DORA Article 13 for incident-driven learning.
    """

    review_id: str = Field(default_factory=lambda: f"PIR-{uuid.uuid4().hex[:8].upper()}")
    incident_id: str
    incident_title: str
    severity: str = "SEV2"
    status: ReviewStatus = ReviewStatus.DRAFT

    # Timeline
    detected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: datetime | None = None
    review_completed_at: datetime | None = None
    timeline: list[TimelineEvent] = Field(default_factory=list)

    # Impact assessment
    affected_component_ids: list[str] = Field(default_factory=list)
    customer_impact: str = ""
    financial_impact_estimate: float = 0.0
    regulatory_notification_required: bool = False

    # Root cause
    root_cause: RootCauseAnalysis | None = None

    # Lessons and actions
    lessons_learned: list[LessonLearned] = Field(default_factory=list)
    improvement_actions: list[ImprovementAction] = Field(default_factory=list)

    # Sign-off
    reviewed_by: list[str] = Field(default_factory=list)
    approved_by: str = ""

    @property
    def duration_minutes(self) -> float | None:
        if self.resolved_at is None:
            return None
        return (self.resolved_at - self.detected_at).total_seconds() / 60

    @property
    def time_to_complete_review_days(self) -> float | None:
        if self.review_completed_at is None:
            return None
        return (self.review_completed_at - self.detected_at).total_seconds() / 86400

    @property
    def open_actions(self) -> list[ImprovementAction]:
        return [a for a in self.improvement_actions if a.status == ActionStatus.OPEN]


class PostTestLearning(BaseModel):
    """Learning record captured after a chaos or resilience test.

    Links test results to concrete improvement actions, forming a feedback
    loop between testing and hardening activities.
    """

    record_id: str = Field(default_factory=lambda: f"PTL-{uuid.uuid4().hex[:8].upper()}")
    test_id: str
    test_name: str
    test_type: str = "chaos"  # chaos | failover | load | dr | penetration
    executed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: ReviewStatus = ReviewStatus.DRAFT

    # Test findings
    components_tested: list[str] = Field(default_factory=list)
    failures_observed: list[str] = Field(default_factory=list)
    unexpected_behaviours: list[str] = Field(default_factory=list)
    slo_breaches: list[str] = Field(default_factory=list)

    # Learning output
    lessons_learned: list[LessonLearned] = Field(default_factory=list)
    improvement_actions: list[ImprovementAction] = Field(default_factory=list)

    # Comparison with previous run
    previous_record_id: str | None = None
    regression_detected: bool = False
    regression_description: str = ""


class RecurringPattern(BaseModel):
    """A detected pattern of recurring failures across reviews."""

    pattern_id: str = Field(default_factory=lambda: f"PAT-{uuid.uuid4().hex[:8].upper()}")
    failure_mode: FailureMode
    occurrences: int
    affected_review_ids: list[str] = Field(default_factory=list)
    first_seen: datetime
    last_seen: datetime
    risk_score: float = Field(ge=0.0, le=1.0, default=0.0)
    recommendation: str = ""

    @property
    def recurrence_interval_days(self) -> float:
        if self.occurrences <= 1:
            return 0.0
        span = (self.last_seen - self.first_seen).total_seconds() / 86400
        return span / (self.occurrences - 1)


class LearningMaturity(BaseModel):
    """ICT learning maturity assessment output.

    Measures the organisation's learning culture across four dimensions and
    aggregates them into an overall maturity level (1–5).
    """

    assessment_id: str = Field(default_factory=lambda: f"MAT-{uuid.uuid4().hex[:8].upper()}")
    assessed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    overall_level: MaturityLevel = MaturityLevel.INITIAL

    # Input metrics
    total_incidents_reviewed: int = 0
    total_tests_reviewed: int = 0
    review_completion_rate: float = 0.0     # 0.0–1.0
    action_implementation_rate: float = 0.0  # 0.0–1.0
    recurrence_rate: float = 0.0            # fraction of incidents that recur
    avg_review_completion_days: float = 0.0

    # Per-dimension scores (0.0–1.0)
    review_process_score: float = 0.0
    action_follow_through_score: float = 0.0
    knowledge_sharing_score: float = 0.0
    trend_detection_score: float = 0.0

    gaps: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Main engine
# ---------------------------------------------------------------------------


class DORALearningEngine:
    """DORA Article 13 Learning and Evolving Engine.

    Manages post-incident reviews, post-test learning records, and the
    organisation's knowledge base of lessons learned. Provides trend
    analysis, improvement velocity metrics, and maturity assessment.

    Usage::

        engine = DORALearningEngine()
        engine.add_incident_review(pir)
        engine.add_test_learning(ptl)
        maturity = engine.assess_maturity()
        patterns = engine.detect_patterns()
    """

    def __init__(self) -> None:
        self._incident_reviews: list[PostIncidentReview] = []
        self._test_records: list[PostTestLearning] = []
        self._knowledge_base: list[LessonLearned] = []

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    def add_incident_review(self, review: PostIncidentReview) -> None:
        """Register a completed (or in-progress) post-incident review."""
        self._incident_reviews.append(review)
        for lesson in review.lessons_learned:
            lesson.source_review_id = review.review_id
            lesson.source_type = "incident"
            self._knowledge_base.append(lesson)

    def add_test_learning(self, record: PostTestLearning) -> None:
        """Register a post-test learning record."""
        self._test_records.append(record)
        for lesson in record.lessons_learned:
            lesson.source_review_id = record.record_id
            lesson.source_type = "test"
            self._knowledge_base.append(lesson)

    # ------------------------------------------------------------------
    # Knowledge base
    # ------------------------------------------------------------------

    def search_lessons(
        self,
        failure_mode: FailureMode | None = None,
        keyword: str | None = None,
    ) -> list[LessonLearned]:
        """Query the knowledge base by failure mode or free-text keyword."""
        results = list(self._knowledge_base)
        if failure_mode is not None:
            results = [entry for entry in results if entry.failure_mode == failure_mode]
        if keyword:
            kw_lower = keyword.lower()
            results = [
                entry for entry in results
                if kw_lower in entry.summary.lower() or kw_lower in entry.detail.lower()
            ]
        return results

    def recommend_actions(self, failure_mode: FailureMode) -> list[str]:
        """Return improvement recommendations derived from past lessons for a failure mode."""
        lessons = self.search_lessons(failure_mode=failure_mode)
        if not lessons:
            return []
        # Surface unique recommendations from improvement actions in source reviews
        recs: list[str] = []
        seen: set[str] = set()

        for lesson in lessons:
            # Retrieve actions from the source review
            review = next(
                (r for r in self._incident_reviews if r.review_id == lesson.source_review_id),
                None,
            )
            if review:
                for action in review.improvement_actions:
                    if action.description not in seen:
                        seen.add(action.description)
                        recs.append(action.description)
            record = next(
                (r for r in self._test_records if r.record_id == lesson.source_review_id),
                None,
            )
            if record:
                for action in record.improvement_actions:
                    if action.description not in seen:
                        seen.add(action.description)
                        recs.append(action.description)
        return recs

    # ------------------------------------------------------------------
    # Pattern detection
    # ------------------------------------------------------------------

    def detect_patterns(self) -> list[RecurringPattern]:
        """Detect recurring failure modes across all reviews and test records.

        A pattern is identified when the same FailureMode appears ≥ 2 times.
        """
        # Collect (failure_mode, review_id, timestamp) from all sources
        observations: list[tuple[FailureMode, str, datetime]] = []

        for review in self._incident_reviews:
            if review.root_cause:
                observations.append((
                    review.root_cause.failure_mode,
                    review.review_id,
                    review.detected_at,
                ))
            for lesson in review.lessons_learned:
                observations.append((
                    lesson.failure_mode,
                    review.review_id,
                    review.detected_at,
                ))

        for record in self._test_records:
            for lesson in record.lessons_learned:
                observations.append((
                    lesson.failure_mode,
                    record.record_id,
                    record.executed_at,
                ))

        if not observations:
            return []

        # Group by failure mode
        mode_map: dict[FailureMode, list[tuple[str, datetime]]] = {}
        for mode, rid, ts in observations:
            mode_map.setdefault(mode, []).append((rid, ts))

        patterns: list[RecurringPattern] = []
        for mode, entries in mode_map.items():
            unique_reviews = list({rid for rid, _ in entries})
            if len(unique_reviews) < 2:
                continue

            timestamps = sorted(ts for _, ts in entries)
            total = len(unique_reviews)
            risk = min(1.0, total / max(len(self._incident_reviews) + len(self._test_records), 1))

            # Default recommendations per mode
            rec_map: dict[FailureMode, str] = {
                FailureMode.SINGLE_POINT_OF_FAILURE: "Add replication/failover for all critical components.",
                FailureMode.CAPACITY_EXHAUSTION: "Implement autoscaling and capacity planning reviews.",
                FailureMode.DEPENDENCY_FAILURE: "Enable circuit breakers and retry strategies on external calls.",
                FailureMode.CONFIGURATION_ERROR: "Enforce infrastructure-as-code and peer review for config changes.",
                FailureMode.MONITORING_GAP: "Expand observability coverage; establish SLO-based alerting.",
                FailureMode.RUNBOOK_MISSING: "Create and validate runbooks for all high-severity failure scenarios.",
            }
            recommendation = rec_map.get(mode, f"Review and remediate recurring {mode.value} failures.")

            patterns.append(RecurringPattern(
                failure_mode=mode,
                occurrences=total,
                affected_review_ids=unique_reviews,
                first_seen=timestamps[0],
                last_seen=timestamps[-1],
                risk_score=round(risk, 4),
                recommendation=recommendation,
            ))

        # Sort by risk descending
        patterns.sort(key=lambda p: -p.risk_score)
        return patterns

    # ------------------------------------------------------------------
    # Improvement velocity
    # ------------------------------------------------------------------

    def improvement_velocity(self) -> dict:
        """Compute metrics on how quickly improvement actions are resolved.

        Returns a dict with:
        - avg_days_to_completion: average resolution time for completed actions
        - overdue_count: number of open past-due actions
        - completion_rate: fraction of all actions completed
        - by_priority: per-priority completion rates
        """
        all_actions: list[ImprovementAction] = []
        for review in self._incident_reviews:
            all_actions.extend(review.improvement_actions)
        for record in self._test_records:
            all_actions.extend(record.improvement_actions)

        if not all_actions:
            return {
                "avg_days_to_completion": None,
                "overdue_count": 0,
                "completion_rate": 0.0,
                "by_priority": {},
            }

        completed = [a for a in all_actions if a.status == ActionStatus.COMPLETED]
        overdue = [a for a in all_actions if a.is_overdue()]

        completion_rate = len(completed) / len(all_actions)

        resolution_times = [a.days_to_resolution for a in completed if a.days_to_resolution is not None]
        avg_days = round(mean(resolution_times), 1) if resolution_times else None

        by_priority: dict[str, dict] = {}
        for priority in ActionPriority:
            p_actions = [a for a in all_actions if a.priority == priority]
            p_done = [a for a in p_actions if a.status == ActionStatus.COMPLETED]
            if p_actions:
                by_priority[priority.value] = {
                    "total": len(p_actions),
                    "completed": len(p_done),
                    "completion_rate": round(len(p_done) / len(p_actions), 4),
                }

        return {
            "avg_days_to_completion": avg_days,
            "overdue_count": len(overdue),
            "completion_rate": round(completion_rate, 4),
            "by_priority": by_priority,
        }

    # ------------------------------------------------------------------
    # Maturity assessment
    # ------------------------------------------------------------------

    def assess_maturity(self) -> LearningMaturity:
        """Assess the organisation's ICT learning maturity level (1–5).

        Dimensions assessed:
        1. Review process — are reviews being completed?
        2. Action follow-through — are improvements implemented?
        3. Knowledge sharing — is the knowledge base being populated?
        4. Trend detection — are recurring patterns being identified?
        """
        gaps: list[str] = []
        recommendations: list[str] = []

        total_incidents = len(self._incident_reviews)
        total_tests = len(self._test_records)

        # --- 1. Review process score ---
        if total_incidents + total_tests == 0:
            review_process_score = 0.0
            gaps.append("No post-incident or post-test reviews have been registered.")
            recommendations.append("Establish a mandatory post-incident review process for all SEV1/SEV2 incidents.")
        else:
            approved = sum(
                1 for r in self._incident_reviews if r.status == ReviewStatus.APPROVED
            ) + sum(
                1 for r in self._test_records if r.status == ReviewStatus.APPROVED
            )
            review_completion_rate = approved / (total_incidents + total_tests)
            review_process_score = review_completion_rate
            if review_completion_rate < 0.5:
                gaps.append(f"Only {review_completion_rate:.0%} of reviews are approved/completed.")
                recommendations.append("Enforce review completion within 14 days of incident resolution.")
            elif review_completion_rate < 0.8:
                recommendations.append("Target 90%+ review completion rate for maturity level 4+.")
        review_completion_rate_val = (
            (
                sum(1 for r in self._incident_reviews if r.status == ReviewStatus.APPROVED)
                + sum(1 for r in self._test_records if r.status == ReviewStatus.APPROVED)
            ) / max(total_incidents + total_tests, 1)
        )

        # --- 2. Action follow-through score ---
        all_actions: list[ImprovementAction] = []
        for r in self._incident_reviews:
            all_actions.extend(r.improvement_actions)
        for r in self._test_records:
            all_actions.extend(r.improvement_actions)

        if not all_actions:
            action_score = 0.0
            gaps.append("No improvement actions have been created from reviews.")
            recommendations.append("Ensure every review produces at least one improvement action.")
        else:
            completed_count = sum(1 for a in all_actions if a.status == ActionStatus.COMPLETED)
            overdue_count = sum(1 for a in all_actions if a.is_overdue())
            action_impl_rate = completed_count / len(all_actions)
            action_score = max(0.0, action_impl_rate - (overdue_count / len(all_actions)) * 0.5)
            action_score = min(1.0, action_score)
            if action_impl_rate < 0.5:
                gaps.append(f"Only {action_impl_rate:.0%} of improvement actions are completed.")
                recommendations.append("Assign DRI and track action items in a dedicated backlog.")
            if overdue_count > 0:
                gaps.append(f"{overdue_count} improvement action(s) are overdue.")
                recommendations.append("Escalate overdue actions to senior management.")

        # --- 3. Knowledge sharing score ---
        kb_size = len(self._knowledge_base)
        validated_count = sum(1 for entry in self._knowledge_base if entry.validated)
        if kb_size == 0:
            kb_score = 0.0
            gaps.append("Knowledge base is empty — no lessons have been catalogued.")
            recommendations.append("Require each review to produce ≥ 1 LessonLearned entry.")
        else:
            validated_ratio = validated_count / kb_size
            kb_score = min(1.0, 0.5 + validated_ratio * 0.5)
            if validated_ratio < 0.3:
                recommendations.append("Validate and peer-review lessons in the knowledge base.")

        # --- 4. Trend detection score ---
        patterns = self.detect_patterns()
        if total_incidents + total_tests < 3:
            trend_score = 0.3  # Insufficient data
        elif not patterns:
            trend_score = 0.6  # No recurrence is good but may reflect sparse data
        else:
            # Having patterns detected AND having recommendations means the process is active
            has_recs_for_patterns = all(p.recommendation for p in patterns)
            trend_score = 0.8 if has_recs_for_patterns else 0.5
            recurring_modes = [p.failure_mode.value for p in patterns]
            gaps.append(
                f"Recurring failure mode(s) detected: {', '.join(recurring_modes)}. "
                "Ensure targeted improvement actions are created."
            )

        # --- Aggregate ---
        composite = (
            review_process_score * 0.30
            + action_score * 0.35
            + kb_score * 0.20
            + trend_score * 0.15
        )

        if composite < 0.20:
            level = MaturityLevel.INITIAL
        elif composite < 0.40:
            level = MaturityLevel.DEVELOPING
        elif composite < 0.65:
            level = MaturityLevel.DEFINED
        elif composite < 0.85:
            level = MaturityLevel.MANAGED
        else:
            level = MaturityLevel.OPTIMISING

        self.improvement_velocity()

        return LearningMaturity(
            overall_level=level,
            total_incidents_reviewed=total_incidents,
            total_tests_reviewed=total_tests,
            review_completion_rate=round(review_completion_rate_val, 4),
            action_implementation_rate=round(
                sum(1 for a in all_actions if a.status == ActionStatus.COMPLETED)
                / max(len(all_actions), 1),
                4,
            ),
            recurrence_rate=round(
                len(patterns) / max(len(self._incident_reviews) + len(self._test_records), 1),
                4,
            ),
            avg_review_completion_days=round(
                mean([
                    r.time_to_complete_review_days
                    for r in self._incident_reviews
                    if r.time_to_complete_review_days is not None
                ] or [0.0]),
                1,
            ),
            review_process_score=round(review_process_score, 4),
            action_follow_through_score=round(action_score, 4),
            knowledge_sharing_score=round(kb_score, 4),
            trend_detection_score=round(trend_score, 4),
            gaps=gaps,
            recommendations=recommendations,
        )

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def generate_report(self) -> dict:
        """Generate a full DORA Article 13 learning report.

        Returns a structured dictionary suitable for audit submission.
        """
        maturity = self.assess_maturity()
        patterns = self.detect_patterns()
        velocity = self.improvement_velocity()

        return {
            "framework": "DORA",
            "article": "Article 13 — Learning and Evolving",
            "regulation": "EU 2022/2554",
            "report_timestamp": datetime.now(timezone.utc).isoformat(),
            "maturity": maturity.model_dump(),
            "recurring_patterns": [p.model_dump() for p in patterns],
            "improvement_velocity": velocity,
            "knowledge_base_size": len(self._knowledge_base),
            "incident_reviews": len(self._incident_reviews),
            "test_learning_records": len(self._test_records),
            "compliance_note": (
                "This report is generated in accordance with DORA Article 13 requirements "
                "for post-incident and post-test learning, continuous improvement tracking, "
                "and organisational learning maturity assessment."
            ),
        }
