# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""DORA Pillar 2 — ICT Incident Management Engine (Articles 17-23).

Implements the full incident management lifecycle required by DORA regulation:
- Incident classification per Article 18 and RTS criteria
- 3-stage reporting timeline per Article 19 and RTS 2025/301
- Structured incident report templates per ITS 2025/302
- Incident impact simulation using InfraGraph topology
- Incident management maturity assessment per Article 17

Reference regulations:
  - DORA Regulation (EU) 2022/2554, Articles 17-23
  - RTS 2025/301 — Incident reporting timelines
  - ITS 2025/302 — Incident report template
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from faultray.model.components import Component, ComponentType
from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class IncidentSeverity(str, Enum):
    """Incident severity levels aligned with DORA classification."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFORMATIONAL = "informational"


class IncidentClassificationLevel(int, Enum):
    """Classification level 1 (lowest) to 5 (highest) per RTS criteria."""

    LEVEL_1 = 1
    LEVEL_2 = 2
    LEVEL_3 = 3
    LEVEL_4 = 4
    LEVEL_5 = 5


class ReportStage(str, Enum):
    """3-stage reporting timeline per Article 19 / RTS 2025/301."""

    INITIAL = "initial"
    INTERMEDIATE = "intermediate"
    FINAL = "final"


class ReportStatus(str, Enum):
    """Status of an individual stage report."""

    PENDING = "pending"
    SUBMITTED = "submitted"
    OVERDUE = "overdue"


class IncidentPhase(str, Enum):
    """Lifecycle phase of an incident."""

    DETECTION = "detection"
    CLASSIFICATION = "classification"
    NOTIFICATION = "notification"
    CONTAINMENT = "containment"
    ERADICATION = "eradication"
    RECOVERY = "recovery"
    POST_INCIDENT_REVIEW = "post_incident_review"
    CLOSED = "closed"


class MaturityLevel(str, Enum):
    """Maturity levels for incident management assessment."""

    INITIAL = "initial"  # Ad-hoc processes
    DEVELOPING = "developing"  # Documented but inconsistent
    DEFINED = "defined"  # Standardised and consistent
    MANAGED = "managed"  # Measured and controlled
    OPTIMISING = "optimising"  # Continuous improvement


class DataImpactLevel(str, Enum):
    """Data loss / breach impact classification."""

    NONE = "none"
    MINIMAL = "minimal"  # Non-sensitive data, recoverable
    MODERATE = "moderate"  # Internal data, partially recoverable
    SIGNIFICANT = "significant"  # Confidential/PII, limited recovery
    SEVERE = "severe"  # Restricted data, unrecoverable


# ---------------------------------------------------------------------------
# RTS Classification Thresholds
# ---------------------------------------------------------------------------


class ClassificationThresholds(BaseModel):
    """Thresholds for incident classification per RTS criteria.

    Each criterion maps to a set of numeric thresholds that determine the
    classification level (1-5).  The thresholds are *upper bounds* — an
    incident is classified at the highest level where any single criterion
    is met or exceeded.
    """

    # Number of clients / counterparts directly affected
    clients_affected_thresholds: list[int] = Field(
        default=[10, 100, 1_000, 10_000, 100_000],
        description="Upper bound per level 1-5 for affected clients",
    )

    # Duration of the incident in hours
    duration_hours_thresholds: list[float] = Field(
        default=[1.0, 4.0, 12.0, 24.0, 72.0],
        description="Upper bound per level 1-5 for incident duration",
    )

    # Number of geographic areas impacted
    geographic_areas_thresholds: list[int] = Field(
        default=[1, 2, 3, 5, 10],
        description="Upper bound per level 1-5 for geographic spread",
    )

    # Data loss severity (0 = none … 4 = severe)
    data_loss_thresholds: list[int] = Field(
        default=[0, 1, 2, 3, 4],
        description="Upper bound per level 1-5 for data loss severity",
    )

    # Number of critical services affected
    critical_services_thresholds: list[int] = Field(
        default=[0, 1, 3, 5, 10],
        description="Upper bound per level 1-5 for critical services impacted",
    )

    # Estimated economic impact in EUR
    economic_impact_thresholds: list[float] = Field(
        default=[10_000.0, 100_000.0, 1_000_000.0, 10_000_000.0, 100_000_000.0],
        description="Upper bound per level 1-5 for economic impact (EUR)",
    )

    # Classification level at or above which the incident is considered major
    major_incident_threshold: int = Field(
        default=3,
        description="Classification level at or above which the incident is 'major'",
    )


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


class IncidentClassification(BaseModel):
    """Result of classifying an ICT incident per Article 18 / RTS criteria."""

    incident_id: str
    classification_level: int = Field(ge=1, le=5)
    major_incident: bool
    severity: IncidentSeverity

    # Per-criterion scores (level 1-5 each)
    clients_affected_level: int = 1
    duration_level: int = 1
    geographic_level: int = 1
    data_loss_level: int = 1
    critical_services_level: int = 1
    economic_impact_level: int = 1

    # Raw input values used for classification
    clients_affected: int = 0
    estimated_duration_hours: float = 0.0
    geographic_areas: int = 0
    data_loss_severity: int = 0  # 0-4
    critical_services_impacted: int = 0
    estimated_economic_impact_eur: float = 0.0

    classification_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    rationale: str = ""


class IncidentTimeline(BaseModel):
    """Tracks reporting deadlines for the 3-stage process (Art. 19)."""

    incident_id: str

    # Key timestamps
    discovery_timestamp: datetime
    determination_timestamp: datetime | None = None

    # Stage deadlines & status
    initial_report_deadline: datetime | None = None
    initial_report_status: ReportStatus = ReportStatus.PENDING
    initial_report_submitted_at: datetime | None = None

    intermediate_report_deadline: datetime | None = None
    intermediate_report_status: ReportStatus = ReportStatus.PENDING
    intermediate_report_submitted_at: datetime | None = None

    final_report_deadline: datetime | None = None
    final_report_status: ReportStatus = ReportStatus.PENDING
    final_report_submitted_at: datetime | None = None

    def compute_deadlines(self) -> None:
        """Compute reporting deadlines based on determination and discovery."""
        if self.determination_timestamp is None:
            return

        # Initial notification: within 4 hours of determination,
        # but max 24 hours from discovery
        deadline_from_determination = self.determination_timestamp + timedelta(hours=4)
        deadline_from_discovery = self.discovery_timestamp + timedelta(hours=24)
        self.initial_report_deadline = min(
            deadline_from_determination, deadline_from_discovery
        )

        # Intermediate report: within 72 hours of initial notification deadline
        self.intermediate_report_deadline = self.initial_report_deadline + timedelta(
            hours=72
        )

        # Final report: within 1 month of initial notification deadline
        self.final_report_deadline = self.initial_report_deadline + timedelta(days=30)

    def get_overdue_stages(
        self, as_of: datetime | None = None
    ) -> list[ReportStage]:
        """Return list of stages that are overdue as of the given time."""
        now = as_of or datetime.now(timezone.utc)
        overdue: list[ReportStage] = []

        if (
            self.initial_report_deadline
            and now > self.initial_report_deadline
            and self.initial_report_status == ReportStatus.PENDING
        ):
            overdue.append(ReportStage.INITIAL)

        if (
            self.intermediate_report_deadline
            and now > self.intermediate_report_deadline
            and self.intermediate_report_status == ReportStatus.PENDING
        ):
            overdue.append(ReportStage.INTERMEDIATE)

        if (
            self.final_report_deadline
            and now > self.final_report_deadline
            and self.final_report_status == ReportStatus.PENDING
        ):
            overdue.append(ReportStage.FINAL)

        return overdue

    def get_approaching_deadlines(
        self, within_hours: float = 2.0, as_of: datetime | None = None
    ) -> list[tuple[ReportStage, datetime, float]]:
        """Return stages whose deadlines are within *within_hours* from *as_of*.

        Returns list of (stage, deadline, hours_remaining).
        """
        now = as_of or datetime.now(timezone.utc)
        approaching: list[tuple[ReportStage, datetime, float]] = []
        checks = [
            (ReportStage.INITIAL, self.initial_report_deadline, self.initial_report_status),
            (ReportStage.INTERMEDIATE, self.intermediate_report_deadline, self.intermediate_report_status),
            (ReportStage.FINAL, self.final_report_deadline, self.final_report_status),
        ]
        for stage, deadline, status in checks:
            if deadline is None or status != ReportStatus.PENDING:
                continue
            remaining = (deadline - now).total_seconds() / 3600.0
            if 0 < remaining <= within_hours:
                approaching.append((stage, deadline, round(remaining, 2)))
        return approaching


class StageReport(BaseModel):
    """Content of a single stage report (initial / intermediate / final)."""

    stage: ReportStage
    submitted_at: datetime | None = None
    status: ReportStatus = ReportStatus.PENDING

    # Common fields across all stages
    incident_id: str = ""
    reporting_entity_lei: str = ""
    reporting_entity_name: str = ""
    competent_authority: str = ""

    # ITS 2025/302 required fields
    incident_title: str = ""
    incident_description: str = ""
    detection_timestamp: datetime | None = None
    determination_timestamp: datetime | None = None
    classification_level: int = 0
    major_incident: bool = False

    # Affected services and clients
    affected_services: list[str] = Field(default_factory=list)
    affected_service_types: list[str] = Field(default_factory=list)
    estimated_clients_affected: int = 0
    affected_transactions_per_day: int = 0

    # Geographic scope
    geographic_areas_affected: list[str] = Field(default_factory=list)
    cross_border: bool = False

    # Data impact
    data_impact_level: DataImpactLevel = DataImpactLevel.NONE
    data_breach_suspected: bool = False
    personal_data_affected: bool = False
    data_types_affected: list[str] = Field(default_factory=list)

    # Root cause
    root_cause_category: str = ""  # e.g., hardware, software, cyber, human, third-party
    root_cause_description: str = ""
    root_cause_confirmed: bool = False

    # Mitigation & recovery (intermediate and final stages)
    mitigation_actions: list[str] = Field(default_factory=list)
    recovery_actions: list[str] = Field(default_factory=list)
    recovery_timestamp: datetime | None = None
    full_recovery_confirmed: bool = False

    # Communication to clients (Art. 21)
    client_communication_issued: bool = False
    client_communication_timestamp: datetime | None = None
    client_communication_channel: str = ""
    client_communication_summary: str = ""

    # Final stage only
    lessons_learned: list[str] = Field(default_factory=list)
    preventive_measures: list[str] = Field(default_factory=list)
    total_incident_duration_hours: float = 0.0
    total_economic_impact_eur: float = 0.0


class IncidentReport(BaseModel):
    """Full incident report encompassing all 3 stages (ITS 2025/302)."""

    incident_id: str
    classification: IncidentClassification | None = None
    timeline: IncidentTimeline | None = None
    current_phase: IncidentPhase = IncidentPhase.DETECTION

    # The three stage reports
    initial_report: StageReport = Field(
        default_factory=lambda: StageReport(stage=ReportStage.INITIAL)
    )
    intermediate_report: StageReport = Field(
        default_factory=lambda: StageReport(stage=ReportStage.INTERMEDIATE)
    )
    final_report: StageReport = Field(
        default_factory=lambda: StageReport(stage=ReportStage.FINAL)
    )

    # Metadata
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    last_updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def to_submission_json(self) -> dict[str, Any]:
        """Export the full report in a JSON structure matching regulatory template."""
        return {
            "schema": "ITS_2025_302",
            "version": "1.0",
            "incident_id": self.incident_id,
            "current_phase": self.current_phase.value,
            "classification": (
                self.classification.model_dump(mode="json")
                if self.classification
                else None
            ),
            "timeline": (
                self.timeline.model_dump(mode="json") if self.timeline else None
            ),
            "reports": {
                "initial": self.initial_report.model_dump(mode="json"),
                "intermediate": self.intermediate_report.model_dump(mode="json"),
                "final": self.final_report.model_dump(mode="json"),
            },
            "metadata": {
                "created_at": self.created_at.isoformat(),
                "last_updated_at": self.last_updated_at.isoformat(),
            },
        }


class IncidentImpactAssessment(BaseModel):
    """Result of simulating an incident's impact on the infrastructure graph."""

    incident_id: str
    failed_component_id: str
    failed_component_name: str

    # Topology impact
    directly_affected_components: list[str] = Field(default_factory=list)
    transitively_affected_components: list[str] = Field(default_factory=list)
    total_affected_count: int = 0
    cascade_depth: int = 0
    cascade_paths: list[list[str]] = Field(default_factory=list)

    # Estimated client impact
    estimated_clients_affected: int = 0
    affected_service_types: list[str] = Field(default_factory=list)

    # Geographic spread
    geographic_areas_affected: list[str] = Field(default_factory=list)
    cross_border: bool = False

    # Data loss risk
    data_loss_risk: DataImpactLevel = DataImpactLevel.NONE
    components_with_pii: list[str] = Field(default_factory=list)

    # Economic impact estimate
    estimated_downtime_hours: float = 0.0
    estimated_economic_impact_eur: float = 0.0

    # Auto-classification
    classification: IncidentClassification | None = None

    # Pre-filled report template
    prefilled_report: IncidentReport | None = None


class IncidentManagementCapability(BaseModel):
    """Assessment of a single incident management capability."""

    capability: str
    description: str
    present: bool = False
    maturity: MaturityLevel = MaturityLevel.INITIAL
    evidence: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class IncidentManagementMaturity(BaseModel):
    """Overall incident management maturity assessment (Art. 17)."""

    overall_maturity: MaturityLevel = MaturityLevel.INITIAL
    overall_score: float = 0.0  # 0.0 to 100.0
    capabilities: list[IncidentManagementCapability] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    assessment_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


# ---------------------------------------------------------------------------
# Classification Engine (Article 18)
# ---------------------------------------------------------------------------


class IncidentClassificationEngine:
    """Classify ICT incidents per Article 18 and RTS criteria.

    Uses a multi-criteria approach: each criterion independently determines
    a level (1-5), and the *overall* level is the maximum across all criteria.
    An incident is 'major' if the overall level meets or exceeds the configured
    threshold (default: 3).
    """

    def __init__(
        self, thresholds: ClassificationThresholds | None = None
    ) -> None:
        self.thresholds = thresholds or ClassificationThresholds()

    @staticmethod
    def _level_for_value(value: float | int, thresholds: list[float | int]) -> int:
        """Determine the classification level (1-5) for a single criterion."""
        for level_idx, upper in enumerate(thresholds):
            if value <= upper:
                return level_idx + 1
        return 5

    def _severity_from_level(self, level: int) -> IncidentSeverity:
        mapping = {
            1: IncidentSeverity.LOW,
            2: IncidentSeverity.MEDIUM,
            3: IncidentSeverity.HIGH,
            4: IncidentSeverity.CRITICAL,
            5: IncidentSeverity.CRITICAL,
        }
        return mapping.get(level, IncidentSeverity.INFORMATIONAL)

    def classify(
        self,
        incident_id: str,
        clients_affected: int = 0,
        estimated_duration_hours: float = 0.0,
        geographic_areas: int = 0,
        data_loss_severity: int = 0,
        critical_services_impacted: int = 0,
        estimated_economic_impact_eur: float = 0.0,
    ) -> IncidentClassification:
        """Classify an incident using multi-criteria thresholds.

        Args:
            incident_id: Unique incident identifier.
            clients_affected: Number of clients / counterparts affected.
            estimated_duration_hours: Estimated or actual incident duration.
            geographic_areas: Number of distinct geographic areas impacted.
            data_loss_severity: 0 (none) to 4 (severe).
            critical_services_impacted: Number of critical services affected.
            estimated_economic_impact_eur: Estimated financial impact in EUR.

        Returns:
            IncidentClassification with per-criterion and overall levels.
        """
        t = self.thresholds

        clients_level = self._level_for_value(
            clients_affected, t.clients_affected_thresholds
        )
        duration_level = self._level_for_value(
            estimated_duration_hours, t.duration_hours_thresholds
        )
        geo_level = self._level_for_value(
            geographic_areas, t.geographic_areas_thresholds
        )
        data_level = self._level_for_value(
            data_loss_severity, t.data_loss_thresholds
        )
        services_level = self._level_for_value(
            critical_services_impacted, t.critical_services_thresholds
        )
        economic_level = self._level_for_value(
            estimated_economic_impact_eur, t.economic_impact_thresholds
        )

        overall_level = max(
            clients_level,
            duration_level,
            geo_level,
            data_level,
            services_level,
            economic_level,
        )

        is_major = overall_level >= t.major_incident_threshold

        rationale_parts: list[str] = []
        criteria = [
            ("clients_affected", clients_level, clients_affected),
            ("duration_hours", duration_level, estimated_duration_hours),
            ("geographic_areas", geo_level, geographic_areas),
            ("data_loss_severity", data_level, data_loss_severity),
            ("critical_services", services_level, critical_services_impacted),
            ("economic_impact_eur", economic_level, estimated_economic_impact_eur),
        ]
        driving_criteria = [
            name for name, lvl, _ in criteria if lvl == overall_level
        ]
        rationale_parts.append(
            f"Overall level {overall_level} driven by: {', '.join(driving_criteria)}."
        )
        if is_major:
            rationale_parts.append(
                f"Classified as MAJOR (threshold: level >= {t.major_incident_threshold})."
            )

        return IncidentClassification(
            incident_id=incident_id,
            classification_level=overall_level,
            major_incident=is_major,
            severity=self._severity_from_level(overall_level),
            clients_affected_level=clients_level,
            duration_level=duration_level,
            geographic_level=geo_level,
            data_loss_level=data_level,
            critical_services_level=services_level,
            economic_impact_level=economic_level,
            clients_affected=clients_affected,
            estimated_duration_hours=estimated_duration_hours,
            geographic_areas=geographic_areas,
            data_loss_severity=data_loss_severity,
            critical_services_impacted=critical_services_impacted,
            estimated_economic_impact_eur=estimated_economic_impact_eur,
            rationale=" ".join(rationale_parts),
        )


# ---------------------------------------------------------------------------
# Reporting Timeline Manager (Article 19 / RTS 2025/301)
# ---------------------------------------------------------------------------


class IncidentReportingManager:
    """Manage the 3-stage reporting lifecycle per Article 19 / RTS 2025/301.

    Tracks timelines, generates alerts for approaching deadlines, and
    produces structured stage reports for regulatory submission.
    """

    def __init__(self) -> None:
        self._reports: dict[str, IncidentReport] = {}
        self._timelines: dict[str, IncidentTimeline] = {}

    @property
    def reports(self) -> dict[str, IncidentReport]:
        return dict(self._reports)

    def create_incident(
        self,
        incident_id: str,
        discovery_timestamp: datetime | None = None,
        reporting_entity_lei: str = "",
        reporting_entity_name: str = "",
        competent_authority: str = "",
    ) -> IncidentReport:
        """Create a new incident and initialise the reporting timeline."""
        now = discovery_timestamp or datetime.now(timezone.utc)

        timeline = IncidentTimeline(
            incident_id=incident_id,
            discovery_timestamp=now,
        )
        self._timelines[incident_id] = timeline

        report = IncidentReport(
            incident_id=incident_id,
            timeline=timeline,
            current_phase=IncidentPhase.DETECTION,
        )
        # Pre-populate entity info on all stage reports
        for stage_report in (
            report.initial_report,
            report.intermediate_report,
            report.final_report,
        ):
            stage_report.incident_id = incident_id
            stage_report.reporting_entity_lei = reporting_entity_lei
            stage_report.reporting_entity_name = reporting_entity_name
            stage_report.competent_authority = competent_authority

        self._reports[incident_id] = report
        logger.info("Created incident %s at %s", incident_id, now.isoformat())
        return report

    def determine_major_incident(
        self,
        incident_id: str,
        classification: IncidentClassification,
        determination_timestamp: datetime | None = None,
    ) -> IncidentTimeline:
        """Record that the incident has been determined as major.

        This triggers deadline computation for the 3-stage reporting process.
        """
        timeline = self._timelines.get(incident_id)
        if timeline is None:
            raise ValueError(f"Unknown incident: {incident_id}")

        det_time = determination_timestamp or datetime.now(timezone.utc)
        timeline.determination_timestamp = det_time
        timeline.compute_deadlines()

        report = self._reports.get(incident_id)
        if report:
            report.classification = classification
            report.current_phase = IncidentPhase.CLASSIFICATION
            report.last_updated_at = datetime.now(timezone.utc)

        logger.info(
            "Incident %s determined as major (level %d) at %s. "
            "Initial report deadline: %s",
            incident_id,
            classification.classification_level,
            det_time.isoformat(),
            timeline.initial_report_deadline.isoformat()
            if timeline.initial_report_deadline
            else "N/A",
        )
        return timeline

    def submit_stage_report(
        self,
        incident_id: str,
        stage: ReportStage,
        stage_report: StageReport,
    ) -> None:
        """Record submission of a stage report."""
        report = self._reports.get(incident_id)
        if report is None:
            raise ValueError(f"Unknown incident: {incident_id}")

        timeline = self._timelines.get(incident_id)
        now = datetime.now(timezone.utc)
        stage_report.submitted_at = now
        stage_report.status = ReportStatus.SUBMITTED

        if stage == ReportStage.INITIAL:
            report.initial_report = stage_report
            report.current_phase = IncidentPhase.NOTIFICATION
            if timeline:
                timeline.initial_report_status = ReportStatus.SUBMITTED
                timeline.initial_report_submitted_at = now
        elif stage == ReportStage.INTERMEDIATE:
            report.intermediate_report = stage_report
            report.current_phase = IncidentPhase.CONTAINMENT
            if timeline:
                timeline.intermediate_report_status = ReportStatus.SUBMITTED
                timeline.intermediate_report_submitted_at = now
        elif stage == ReportStage.FINAL:
            report.final_report = stage_report
            report.current_phase = IncidentPhase.POST_INCIDENT_REVIEW
            if timeline:
                timeline.final_report_status = ReportStatus.SUBMITTED
                timeline.final_report_submitted_at = now

        report.last_updated_at = now
        logger.info(
            "Submitted %s report for incident %s at %s",
            stage.value,
            incident_id,
            now.isoformat(),
        )

    def get_deadline_alerts(
        self,
        within_hours: float = 2.0,
        as_of: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Get alerts for all incidents with approaching or overdue deadlines.

        Returns a list of alert dicts containing incident_id, stage, status,
        deadline, and hours_remaining (negative if overdue).
        """
        alerts: list[dict[str, Any]] = []
        now = as_of or datetime.now(timezone.utc)

        for iid, timeline in self._timelines.items():
            # Overdue stages
            for stage in timeline.get_overdue_stages(as_of=now):
                deadline_map = {
                    ReportStage.INITIAL: timeline.initial_report_deadline,
                    ReportStage.INTERMEDIATE: timeline.intermediate_report_deadline,
                    ReportStage.FINAL: timeline.final_report_deadline,
                }
                deadline = deadline_map.get(stage)
                hours_overdue = (
                    -((now - deadline).total_seconds() / 3600.0) if deadline else 0.0
                )
                alerts.append(
                    {
                        "incident_id": iid,
                        "stage": stage.value,
                        "status": "overdue",
                        "deadline": deadline.isoformat() if deadline else None,
                        "hours_remaining": round(hours_overdue, 2),
                        "severity": "critical",
                    }
                )

            # Approaching deadlines
            for stage, deadline, remaining in timeline.get_approaching_deadlines(
                within_hours=within_hours, as_of=now
            ):
                alerts.append(
                    {
                        "incident_id": iid,
                        "stage": stage.value,
                        "status": "approaching",
                        "deadline": deadline.isoformat(),
                        "hours_remaining": remaining,
                        "severity": "warning",
                    }
                )

        # Sort by urgency: overdue first, then by hours remaining ascending
        alerts.sort(key=lambda a: (a["status"] != "overdue", a["hours_remaining"]))
        return alerts


# ---------------------------------------------------------------------------
# Incident Impact Simulator
# ---------------------------------------------------------------------------


class IncidentImpactSimulator:
    """Simulate the impact of an incident on an InfraGraph.

    Given a component failure, traverses the dependency graph to estimate:
    - Downstream service disruption (cascade analysis)
    - Client impact
    - Geographic spread
    - Data loss risk
    - Economic impact

    The simulation result is auto-classified using
    :class:`IncidentClassificationEngine` and a pre-filled incident report
    template is generated.
    """

    def __init__(
        self,
        graph: InfraGraph,
        classifier: IncidentClassificationEngine | None = None,
    ) -> None:
        self.graph = graph
        self.classifier = classifier or IncidentClassificationEngine()

    def _generate_incident_id(self, component_id: str) -> str:
        """Generate a deterministic incident ID for simulation."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        hash_input = f"{component_id}:{timestamp}"
        short_hash = hashlib.sha256(hash_input.encode()).hexdigest()[:8]
        return f"SIM-{short_hash.upper()}"

    def _collect_regions(self, component_ids: set[str]) -> list[str]:
        """Collect unique region names from a set of component IDs."""
        regions: set[str] = set()
        for cid in component_ids:
            comp = self.graph.get_component(cid)
            if comp and comp.region.region:
                regions.add(comp.region.region)
        return sorted(regions)

    def _assess_data_loss_risk(
        self, failed_id: str, affected_ids: set[str]
    ) -> tuple[DataImpactLevel, list[str]]:
        """Assess data loss risk based on component compliance tags."""
        all_ids = {failed_id} | affected_ids
        pii_components: list[str] = []
        max_severity = 0

        for cid in all_ids:
            comp = self.graph.get_component(cid)
            if comp is None:
                continue

            tags = comp.compliance_tags

            if tags.contains_phi:
                max_severity = max(max_severity, 4)
                pii_components.append(cid)
            elif tags.data_classification == "restricted":
                max_severity = max(max_severity, 4)
                pii_components.append(cid)
            elif tags.contains_pii:
                max_severity = max(max_severity, 3)
                pii_components.append(cid)
            elif tags.data_classification == "confidential":
                max_severity = max(max_severity, 2)
            elif tags.data_classification == "internal":
                max_severity = max(max_severity, 1)

            # Components without backups increase risk
            if not comp.security.backup_enabled and comp.type in (
                ComponentType.DATABASE,
                ComponentType.STORAGE,
            ):
                max_severity = min(max_severity + 1, 4)

        level_map = {
            0: DataImpactLevel.NONE,
            1: DataImpactLevel.MINIMAL,
            2: DataImpactLevel.MODERATE,
            3: DataImpactLevel.SIGNIFICANT,
            4: DataImpactLevel.SEVERE,
        }
        return level_map.get(max_severity, DataImpactLevel.NONE), pii_components

    def _estimate_economic_impact(
        self,
        failed_id: str,
        affected_ids: set[str],
        estimated_duration_hours: float,
    ) -> float:
        """Estimate economic impact based on component cost profiles."""
        all_ids = {failed_id} | affected_ids
        total_eur = 0.0

        for cid in all_ids:
            comp = self.graph.get_component(cid)
            if comp is None:
                continue
            cost = comp.cost_profile
            # Revenue loss
            total_eur += cost.revenue_per_minute * 60.0 * estimated_duration_hours
            # Infrastructure cost (still incurred during outage)
            total_eur += cost.hourly_infra_cost * estimated_duration_hours
            # Recovery engineering cost
            total_eur += cost.recovery_engineer_cost * estimated_duration_hours
            # Customer churn
            total_eur += (
                cost.monthly_contract_value
                * cost.churn_rate_per_hour_outage
                * estimated_duration_hours
            )

        return round(total_eur, 2)

    def _estimate_clients_affected(self, affected_ids: set[str]) -> int:
        """Heuristic estimate of affected clients from impacted components."""
        # Use capacity.max_connections as a proxy for potential client impact
        total_capacity = 0
        for cid in affected_ids:
            comp = self.graph.get_component(cid)
            if comp is None:
                continue
            # Entry-point components (load balancers, web servers) directly serve clients
            if comp.type in (
                ComponentType.LOAD_BALANCER,
                ComponentType.WEB_SERVER,
                ComponentType.APP_SERVER,
            ):
                total_capacity += comp.capacity.max_connections * comp.replicas
        # Assume ~10% of max capacity represents active users
        return max(1, int(total_capacity * 0.1))

    def _collect_service_types(self, component_ids: set[str]) -> list[str]:
        """Collect unique service types from affected components."""
        types: set[str] = set()
        for cid in component_ids:
            comp = self.graph.get_component(cid)
            if comp:
                types.add(comp.type.value)
        return sorted(types)

    def _count_critical_services(self, affected_ids: set[str]) -> int:
        """Count services deemed critical among the affected components.

        A service is considered critical if it is a database, has PII/PHI data,
        or has many dependents.
        """
        count = 0
        for cid in affected_ids:
            comp = self.graph.get_component(cid)
            if comp is None:
                continue
            is_critical = (
                comp.type == ComponentType.DATABASE
                or comp.compliance_tags.contains_pii
                or comp.compliance_tags.contains_phi
                or comp.compliance_tags.data_classification in ("restricted", "confidential")
                or len(self.graph.get_dependents(cid)) >= 3
            )
            if is_critical:
                count += 1
        return count

    def simulate(
        self,
        component_id: str,
        estimated_duration_hours: float = 4.0,
        incident_id: str | None = None,
    ) -> IncidentImpactAssessment:
        """Simulate an incident from a single component failure.

        Args:
            component_id: The component that fails.
            estimated_duration_hours: Assumed incident duration for impact estimation.
            incident_id: Optional custom incident ID. Auto-generated if omitted.

        Returns:
            IncidentImpactAssessment with full impact analysis, auto-classification,
            and a pre-filled incident report template.

        Raises:
            ValueError: If the component_id does not exist in the graph.
        """
        comp = self.graph.get_component(component_id)
        if comp is None:
            raise ValueError(f"Component not found in graph: {component_id}")

        iid = incident_id or self._generate_incident_id(component_id)

        # --- Cascade analysis ---
        directly_affected_ids: set[str] = set()
        for dep in self.graph.get_dependents(component_id):
            directly_affected_ids.add(dep.id)

        all_affected_ids = self.graph.get_all_affected(component_id)
        transitively_affected_ids = all_affected_ids - directly_affected_ids

        cascade_paths = self.graph.get_cascade_path(component_id)
        cascade_depth = max((len(p) for p in cascade_paths), default=0)

        # --- Geographic spread ---
        all_involved = {component_id} | all_affected_ids
        regions = self._collect_regions(all_involved)

        # --- Data loss risk ---
        data_impact, pii_components = self._assess_data_loss_risk(
            component_id, all_affected_ids
        )

        # --- Economic impact ---
        economic_impact = self._estimate_economic_impact(
            component_id, all_affected_ids, estimated_duration_hours
        )

        # --- Client impact ---
        clients_affected = self._estimate_clients_affected(all_involved)

        # --- Service types ---
        service_types = self._collect_service_types(all_involved)

        # --- Critical services ---
        critical_services = self._count_critical_services(all_affected_ids)

        # --- Auto-classify ---
        data_loss_int = {
            DataImpactLevel.NONE: 0,
            DataImpactLevel.MINIMAL: 1,
            DataImpactLevel.MODERATE: 2,
            DataImpactLevel.SIGNIFICANT: 3,
            DataImpactLevel.SEVERE: 4,
        }.get(data_impact, 0)

        classification = self.classifier.classify(
            incident_id=iid,
            clients_affected=clients_affected,
            estimated_duration_hours=estimated_duration_hours,
            geographic_areas=len(regions),
            data_loss_severity=data_loss_int,
            critical_services_impacted=critical_services,
            estimated_economic_impact_eur=economic_impact,
        )

        # --- Pre-filled report ---
        now = datetime.now(timezone.utc)
        timeline = IncidentTimeline(
            incident_id=iid,
            discovery_timestamp=now,
            determination_timestamp=now,
        )
        timeline.compute_deadlines()

        initial_report = StageReport(
            stage=ReportStage.INITIAL,
            incident_id=iid,
            incident_title=f"Simulated failure of {comp.name} ({component_id})",
            incident_description=(
                f"Component {comp.name} ({comp.type.value}) experienced a simulated "
                f"failure affecting {len(all_affected_ids)} downstream components "
                f"across {len(regions)} geographic area(s)."
            ),
            detection_timestamp=now,
            determination_timestamp=now,
            classification_level=classification.classification_level,
            major_incident=classification.major_incident,
            affected_services=sorted(all_affected_ids),
            affected_service_types=service_types,
            estimated_clients_affected=clients_affected,
            geographic_areas_affected=regions,
            cross_border=len(regions) > 1,
            data_impact_level=data_impact,
            personal_data_affected=len(pii_components) > 0,
            root_cause_category="simulated",
            root_cause_description=f"Simulated failure of {comp.type.value}: {comp.name}",
        )

        prefilled_report = IncidentReport(
            incident_id=iid,
            classification=classification,
            timeline=timeline,
            current_phase=IncidentPhase.CLASSIFICATION,
            initial_report=initial_report,
        )

        return IncidentImpactAssessment(
            incident_id=iid,
            failed_component_id=component_id,
            failed_component_name=comp.name,
            directly_affected_components=sorted(directly_affected_ids),
            transitively_affected_components=sorted(transitively_affected_ids),
            total_affected_count=len(all_affected_ids),
            cascade_depth=cascade_depth,
            cascade_paths=cascade_paths[:20],  # limit for readability
            estimated_clients_affected=clients_affected,
            affected_service_types=service_types,
            geographic_areas_affected=regions,
            cross_border=len(regions) > 1,
            data_loss_risk=data_impact,
            components_with_pii=pii_components,
            estimated_downtime_hours=estimated_duration_hours,
            estimated_economic_impact_eur=economic_impact,
            classification=classification,
            prefilled_report=prefilled_report,
        )


# ---------------------------------------------------------------------------
# Incident Management Process Assessment (Article 17)
# ---------------------------------------------------------------------------


class IncidentManagementAssessor:
    """Assess an organisation's incident management maturity (Article 17).

    Evaluates the InfraGraph for evidence of:
    - Incident detection mechanisms (monitoring, alerting)
    - Classification processes (tagging, severity metadata)
    - Escalation procedures (team config, on-call)
    - Communication plans (client-facing components, notification paths)
    - Recovery capabilities (failover, backup, DR)
    """

    # Keyword sets used to detect monitoring / alerting components
    _MONITORING_KEYWORDS: set[str] = {
        "monitoring", "prometheus", "grafana", "otel", "opentelemetry",
        "datadog", "newrelic", "splunk", "elastic", "kibana", "nagios",
        "zabbix", "cloudwatch", "stackdriver",
    }
    _ALERTING_KEYWORDS: set[str] = {
        "alert", "pagerduty", "opsgenie", "victorops", "slack-alert",
        "notification", "oncall", "incident",
    }
    _LOGGING_KEYWORDS: set[str] = {
        "log", "logging", "elk", "fluentd", "logstash", "loki",
        "syslog", "audit-log",
    }

    def __init__(self, graph: InfraGraph) -> None:
        self.graph = graph

    def _component_matches_keywords(
        self, comp: Component, keywords: set[str]
    ) -> bool:
        combined = f"{comp.id} {comp.name}".lower()
        return any(kw in combined for kw in keywords)

    def _has_monitoring(self) -> tuple[bool, list[str]]:
        evidence: list[str] = []
        for comp in self.graph.components.values():
            if self._component_matches_keywords(comp, self._MONITORING_KEYWORDS):
                evidence.append(f"Monitoring component: {comp.id} ({comp.name})")
        return len(evidence) > 0, evidence

    def _has_alerting(self) -> tuple[bool, list[str]]:
        evidence: list[str] = []
        for comp in self.graph.components.values():
            if self._component_matches_keywords(comp, self._ALERTING_KEYWORDS):
                evidence.append(f"Alerting component: {comp.id} ({comp.name})")
        return len(evidence) > 0, evidence

    def _has_logging(self) -> tuple[bool, list[str]]:
        evidence: list[str] = []
        for comp in self.graph.components.values():
            if self._component_matches_keywords(comp, self._LOGGING_KEYWORDS):
                evidence.append(f"Logging component: {comp.id} ({comp.name})")
            if comp.compliance_tags.audit_logging:
                evidence.append(f"Audit logging enabled: {comp.id}")
            if comp.security.log_enabled:
                evidence.append(f"Security logging enabled: {comp.id}")
        return len(evidence) > 0, evidence

    def _has_classification_metadata(self) -> tuple[bool, list[str]]:
        evidence: list[str] = []
        for comp in self.graph.components.values():
            if comp.compliance_tags.data_classification != "internal":
                evidence.append(
                    f"Data classification set: {comp.id} = "
                    f"{comp.compliance_tags.data_classification}"
                )
            if comp.slo_targets:
                evidence.append(
                    f"SLO targets defined: {comp.id} "
                    f"({len(comp.slo_targets)} targets)"
                )
        return len(evidence) > 0, evidence

    def _has_escalation_procedures(self) -> tuple[bool, list[str]]:
        evidence: list[str] = []
        for comp in self.graph.components.values():
            team = comp.team
            if team.oncall_coverage_hours >= 24.0:
                evidence.append(f"24x7 on-call: {comp.id}")
            if team.runbook_coverage_percent > 50.0:
                evidence.append(
                    f"Runbook coverage {team.runbook_coverage_percent:.0f}%: {comp.id}"
                )
            if team.timezone_coverage >= 2:
                evidence.append(
                    f"Multi-timezone coverage ({team.timezone_coverage} TZs): {comp.id}"
                )
        return len(evidence) > 0, evidence

    def _has_recovery_capabilities(self) -> tuple[bool, list[str]]:
        evidence: list[str] = []
        for comp in self.graph.components.values():
            if comp.failover.enabled:
                evidence.append(f"Failover enabled: {comp.id}")
            if comp.security.backup_enabled:
                evidence.append(
                    f"Backup enabled (every {comp.security.backup_frequency_hours}h): "
                    f"{comp.id}"
                )
            if comp.region.dr_target_region:
                evidence.append(
                    f"DR target region ({comp.region.dr_target_region}): {comp.id}"
                )
            if comp.autoscaling.enabled:
                evidence.append(f"Autoscaling enabled: {comp.id}")
        return len(evidence) > 0, evidence

    def _has_communication_plan(self) -> tuple[bool, list[str]]:
        """Check for evidence of client communication readiness."""
        evidence: list[str] = []
        for comp in self.graph.components.values():
            # Status page or notification service
            combined = f"{comp.id} {comp.name}".lower()
            if any(
                kw in combined
                for kw in ("status-page", "statuspage", "notification", "email", "sms")
            ):
                evidence.append(f"Communication channel: {comp.id} ({comp.name})")
        return len(evidence) > 0, evidence

    def _maturity_for_score(self, score: float) -> MaturityLevel:
        if score >= 80.0:
            return MaturityLevel.OPTIMISING
        if score >= 60.0:
            return MaturityLevel.MANAGED
        if score >= 40.0:
            return MaturityLevel.DEFINED
        if score >= 20.0:
            return MaturityLevel.DEVELOPING
        return MaturityLevel.INITIAL

    def assess(self) -> IncidentManagementMaturity:
        """Run the full maturity assessment against the infrastructure graph.

        Returns an :class:`IncidentManagementMaturity` with per-capability
        results, an overall maturity level, and actionable recommendations.
        """
        capabilities: list[IncidentManagementCapability] = []
        total_score = 0.0
        max_score = 0.0

        # --- 1. Detection mechanisms ---
        has_mon, mon_ev = self._has_monitoring()
        has_alert, alert_ev = self._has_alerting()
        has_log, log_ev = self._has_logging()

        detection_present = has_mon or has_alert
        detection_evidence = mon_ev + alert_ev + log_ev
        detection_recs: list[str] = []
        detection_score = 0.0

        if has_mon and has_alert and has_log:
            detection_maturity = MaturityLevel.MANAGED
            detection_score = 20.0
        elif has_mon and (has_alert or has_log):
            detection_maturity = MaturityLevel.DEFINED
            detection_score = 15.0
        elif has_mon or has_alert:
            detection_maturity = MaturityLevel.DEVELOPING
            detection_score = 10.0
        else:
            detection_maturity = MaturityLevel.INITIAL
            detection_score = 0.0
            detection_recs.append(
                "Deploy monitoring infrastructure (e.g., Prometheus, Datadog)."
            )
            detection_recs.append(
                "Implement alerting (e.g., PagerDuty, OpsGenie) for incident detection."
            )

        if not has_log:
            detection_recs.append(
                "Enable centralised logging for incident investigation (e.g., ELK, Loki)."
            )

        capabilities.append(
            IncidentManagementCapability(
                capability="incident_detection",
                description="Mechanisms for detecting ICT incidents (Art. 17(1)(a))",
                present=detection_present,
                maturity=detection_maturity,
                evidence=detection_evidence,
                recommendations=detection_recs,
            )
        )
        total_score += detection_score
        max_score += 20.0

        # --- 2. Classification process ---
        has_class, class_ev = self._has_classification_metadata()
        class_recs: list[str] = []

        if has_class:
            class_maturity = MaturityLevel.DEFINED
            class_score = 15.0
        else:
            class_maturity = MaturityLevel.INITIAL
            class_score = 0.0
            class_recs.append(
                "Define data classification for all components "
                "(public/internal/confidential/restricted)."
            )
            class_recs.append(
                "Set SLO targets for critical services to enable severity-based classification."
            )

        capabilities.append(
            IncidentManagementCapability(
                capability="classification_process",
                description="Incident classification and prioritisation (Art. 17(1)(b))",
                present=has_class,
                maturity=class_maturity,
                evidence=class_ev,
                recommendations=class_recs,
            )
        )
        total_score += class_score
        max_score += 20.0

        # --- 3. Escalation procedures ---
        has_esc, esc_ev = self._has_escalation_procedures()
        esc_recs: list[str] = []

        if has_esc:
            esc_maturity = MaturityLevel.DEFINED
            esc_score = 15.0
        else:
            esc_maturity = MaturityLevel.INITIAL
            esc_score = 0.0
            esc_recs.append(
                "Configure on-call schedules with 24x7 coverage for critical services."
            )
            esc_recs.append(
                "Develop runbooks covering >50% of known failure scenarios."
            )

        capabilities.append(
            IncidentManagementCapability(
                capability="escalation_procedures",
                description="Escalation and response procedures (Art. 17(1)(c))",
                present=has_esc,
                maturity=esc_maturity,
                evidence=esc_ev,
                recommendations=esc_recs,
            )
        )
        total_score += esc_score
        max_score += 20.0

        # --- 4. Communication plans ---
        has_comm, comm_ev = self._has_communication_plan()
        comm_recs: list[str] = []

        if has_comm:
            comm_maturity = MaturityLevel.DEFINED
            comm_score = 15.0
        else:
            comm_maturity = MaturityLevel.INITIAL
            comm_score = 0.0
            comm_recs.append(
                "Implement a status page or notification service for client communication "
                "during incidents (Art. 21 requirement)."
            )

        capabilities.append(
            IncidentManagementCapability(
                capability="communication_plans",
                description="Client and stakeholder communication (Art. 17(3), Art. 21)",
                present=has_comm,
                maturity=comm_maturity,
                evidence=comm_ev,
                recommendations=comm_recs,
            )
        )
        total_score += comm_score
        max_score += 20.0

        # --- 5. Recovery capabilities ---
        has_rec, rec_ev = self._has_recovery_capabilities()
        rec_recs: list[str] = []

        if has_rec:
            rec_maturity = MaturityLevel.DEFINED
            rec_score = 15.0
        else:
            rec_maturity = MaturityLevel.INITIAL
            rec_score = 0.0
            rec_recs.append(
                "Enable failover for critical components (databases, app servers)."
            )
            rec_recs.append(
                "Configure backup strategies with defined RPO/RTO."
            )
            rec_recs.append(
                "Define DR target regions for multi-region resilience."
            )

        capabilities.append(
            IncidentManagementCapability(
                capability="recovery_capabilities",
                description="Incident recovery and business continuity (Art. 17(1)(d))",
                present=has_rec,
                maturity=rec_maturity,
                evidence=rec_ev,
                recommendations=rec_recs,
            )
        )
        total_score += rec_score
        max_score += 20.0

        # --- Overall assessment ---
        overall_percent = (total_score / max_score * 100.0) if max_score > 0 else 0.0
        overall_maturity = self._maturity_for_score(overall_percent)

        strengths = [
            cap.capability
            for cap in capabilities
            if cap.present and cap.maturity.value in ("defined", "managed", "optimising")
        ]
        weaknesses = [cap.capability for cap in capabilities if not cap.present]

        all_recs: list[str] = []
        for cap in capabilities:
            all_recs.extend(cap.recommendations)

        return IncidentManagementMaturity(
            overall_maturity=overall_maturity,
            overall_score=round(overall_percent, 1),
            capabilities=capabilities,
            strengths=strengths,
            weaknesses=weaknesses,
            recommendations=all_recs,
        )


# ---------------------------------------------------------------------------
# Facade: DORAIncidentEngine
# ---------------------------------------------------------------------------


class DORAIncidentEngine:
    """High-level facade combining all DORA Pillar 2 capabilities.

    Provides a single entry point for:
    - Incident classification (Article 18)
    - Reporting timeline management (Article 19 / RTS 2025/301)
    - Incident impact simulation
    - Incident management maturity assessment (Article 17)

    Example::

        from faultray.model.graph import InfraGraph

        graph = InfraGraph.load(Path("infra.json"))
        engine = DORAIncidentEngine(graph)

        # Simulate an incident
        impact = engine.simulate_incident("db-primary", estimated_duration_hours=6.0)
        print(impact.classification.major_incident)

        # Assess maturity
        maturity = engine.assess_incident_management()
        print(maturity.overall_maturity)

        # Create & manage a real incident
        report = engine.create_incident("INC-2025-001")
        classification = engine.classify_incident(
            "INC-2025-001", clients_affected=5000, estimated_duration_hours=8.0
        )
        engine.determine_major("INC-2025-001", classification)
        alerts = engine.get_deadline_alerts()
    """

    def __init__(
        self,
        graph: InfraGraph,
        thresholds: ClassificationThresholds | None = None,
    ) -> None:
        self.graph = graph
        self.classifier = IncidentClassificationEngine(thresholds=thresholds)
        self.reporting_manager = IncidentReportingManager()
        self.impact_simulator = IncidentImpactSimulator(
            graph=graph, classifier=self.classifier
        )
        self.maturity_assessor = IncidentManagementAssessor(graph=graph)

    # --- Classification ---

    def classify_incident(
        self,
        incident_id: str,
        clients_affected: int = 0,
        estimated_duration_hours: float = 0.0,
        geographic_areas: int = 0,
        data_loss_severity: int = 0,
        critical_services_impacted: int = 0,
        estimated_economic_impact_eur: float = 0.0,
    ) -> IncidentClassification:
        """Classify an incident by its impact parameters."""
        return self.classifier.classify(
            incident_id=incident_id,
            clients_affected=clients_affected,
            estimated_duration_hours=estimated_duration_hours,
            geographic_areas=geographic_areas,
            data_loss_severity=data_loss_severity,
            critical_services_impacted=critical_services_impacted,
            estimated_economic_impact_eur=estimated_economic_impact_eur,
        )

    # --- Reporting lifecycle ---

    def create_incident(
        self,
        incident_id: str,
        discovery_timestamp: datetime | None = None,
        reporting_entity_lei: str = "",
        reporting_entity_name: str = "",
        competent_authority: str = "",
    ) -> IncidentReport:
        """Create a new incident and initialise reporting timeline."""
        return self.reporting_manager.create_incident(
            incident_id=incident_id,
            discovery_timestamp=discovery_timestamp,
            reporting_entity_lei=reporting_entity_lei,
            reporting_entity_name=reporting_entity_name,
            competent_authority=competent_authority,
        )

    def determine_major(
        self,
        incident_id: str,
        classification: IncidentClassification,
        determination_timestamp: datetime | None = None,
    ) -> IncidentTimeline:
        """Mark an incident as major, triggering deadline computation."""
        return self.reporting_manager.determine_major_incident(
            incident_id=incident_id,
            classification=classification,
            determination_timestamp=determination_timestamp,
        )

    def submit_report(
        self,
        incident_id: str,
        stage: ReportStage,
        stage_report: StageReport,
    ) -> None:
        """Submit a stage report (initial / intermediate / final)."""
        self.reporting_manager.submit_stage_report(
            incident_id=incident_id,
            stage=stage,
            stage_report=stage_report,
        )

    def get_deadline_alerts(
        self,
        within_hours: float = 2.0,
        as_of: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Get approaching and overdue deadline alerts across all incidents."""
        return self.reporting_manager.get_deadline_alerts(
            within_hours=within_hours, as_of=as_of
        )

    # --- Impact simulation ---

    def simulate_incident(
        self,
        component_id: str,
        estimated_duration_hours: float = 4.0,
        incident_id: str | None = None,
    ) -> IncidentImpactAssessment:
        """Simulate an incident from a component failure."""
        return self.impact_simulator.simulate(
            component_id=component_id,
            estimated_duration_hours=estimated_duration_hours,
            incident_id=incident_id,
        )

    # --- Maturity assessment ---

    def assess_incident_management(self) -> IncidentManagementMaturity:
        """Assess incident management maturity per Article 17."""
        return self.maturity_assessor.assess()

    # --- Convenience: full incident lifecycle simulation ---

    def run_full_simulation(
        self,
        component_id: str,
        estimated_duration_hours: float = 4.0,
    ) -> dict[str, Any]:
        """Run a complete simulation: impact + classification + maturity.

        Returns a dict summarising the simulation suitable for reporting.
        """
        impact = self.simulate_incident(
            component_id=component_id,
            estimated_duration_hours=estimated_duration_hours,
        )
        maturity = self.assess_incident_management()

        return {
            "incident_id": impact.incident_id,
            "failed_component": impact.failed_component_name,
            "total_affected_components": impact.total_affected_count,
            "cascade_depth": impact.cascade_depth,
            "estimated_clients_affected": impact.estimated_clients_affected,
            "geographic_areas": impact.geographic_areas_affected,
            "data_loss_risk": impact.data_loss_risk.value,
            "estimated_economic_impact_eur": impact.estimated_economic_impact_eur,
            "classification_level": (
                impact.classification.classification_level
                if impact.classification
                else None
            ),
            "major_incident": (
                impact.classification.major_incident
                if impact.classification
                else None
            ),
            "severity": (
                impact.classification.severity.value
                if impact.classification
                else None
            ),
            "incident_management_maturity": maturity.overall_maturity.value,
            "incident_management_score": maturity.overall_score,
            "timeline": (
                impact.prefilled_report.timeline.model_dump(mode="json")
                if impact.prefilled_report and impact.prefilled_report.timeline
                else None
            ),
            "report_template": (
                impact.prefilled_report.to_submission_json()
                if impact.prefilled_report
                else None
            ),
            "recommendations": maturity.recommendations,
        }
