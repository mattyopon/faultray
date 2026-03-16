"""Incident Timeline Reconstructor.

Creates detailed timelines of infrastructure incidents by analyzing
component states, dependencies, and cascade chains in an InfraGraph.

Features:
- Manual event addition for known incidents
- Auto-detection of FAILURE / DEGRADATION from component health
- Cascade chain detection from the dependency graph
- Root cause identification (deepest unhealthy dependency)
- Impact summary generation
- Severity determination based on affected components
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from faultray.model.components import HealthStatus
from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class EventType(str, Enum):
    """Types of events that can appear on an incident timeline."""

    DEGRADATION_START = "degradation_start"
    FAILURE = "failure"
    RECOVERY = "recovery"
    ESCALATION = "escalation"
    MITIGATION = "mitigation"
    ALERT_FIRED = "alert_fired"
    ALERT_RESOLVED = "alert_resolved"
    MANUAL_ACTION = "manual_action"
    CASCADE_START = "cascade_start"
    CASCADE_END = "cascade_end"


class Severity(str, Enum):
    """Incident severity levels (SEV1 = most severe)."""

    SEV1 = "sev1"
    SEV2 = "sev2"
    SEV3 = "sev3"
    SEV4 = "sev4"
    SEV5 = "sev5"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class TimelineEvent:
    """A single event on an incident timeline."""

    timestamp: datetime
    event_type: EventType
    component_id: str
    description: str
    severity: Severity
    metadata: dict = field(default_factory=dict)


@dataclass
class IncidentTimeline:
    """A complete incident timeline with events and analysis."""

    incident_id: str
    title: str
    severity: Severity
    events: list[TimelineEvent]
    start_time: datetime
    end_time: datetime | None
    duration_minutes: float
    root_cause_component: str
    affected_components: list[str]
    impact_summary: str
    lessons_learned: list[str]


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


class IncidentTimelineBuilder:
    """Builds incident timelines from manual events or by auto-detecting
    issues from an InfraGraph's current health state and dependency
    structure.
    """

    def __init__(self) -> None:
        self._events: list[TimelineEvent] = []

    # -- public API ---------------------------------------------------------

    def add_event(self, event: TimelineEvent) -> None:
        """Add a manually created event to the timeline."""
        self._events.append(event)

    def build(self, incident_id: str, title: str) -> IncidentTimeline:
        """Build an IncidentTimeline from the events added so far.

        The builder determines severity, root cause, affected components,
        duration, and impact summary automatically from the collected events.
        """
        if not self._events:
            now = datetime.now(timezone.utc)
            return IncidentTimeline(
                incident_id=incident_id,
                title=title,
                severity=Severity.SEV5,
                events=[],
                start_time=now,
                end_time=now,
                duration_minutes=0.0,
                root_cause_component="unknown",
                affected_components=[],
                impact_summary="No events recorded.",
                lessons_learned=[],
            )

        sorted_events = sorted(self._events, key=lambda e: e.timestamp)
        start_time = sorted_events[0].timestamp
        end_time = sorted_events[-1].timestamp
        duration = (end_time - start_time).total_seconds() / 60.0

        severity = self._determine_severity(sorted_events)
        root_cause = self._identify_root_cause(sorted_events)
        affected = self._collect_affected(sorted_events)
        impact = self._generate_impact_summary(sorted_events, affected)
        lessons = self._generate_lessons(sorted_events)

        timeline = IncidentTimeline(
            incident_id=incident_id,
            title=title,
            severity=severity,
            events=sorted_events,
            start_time=start_time,
            end_time=end_time,
            duration_minutes=duration,
            root_cause_component=root_cause,
            affected_components=affected,
            impact_summary=impact,
            lessons_learned=lessons,
        )

        # Reset builder state for reuse
        self._events = []
        return timeline

    def build_from_graph(
        self,
        graph: InfraGraph,
        incident_id: str,
        title: str,
    ) -> IncidentTimeline:
        """Auto-detect issues from the current graph health and build a
        timeline.

        * DOWN components produce FAILURE events.
        * DEGRADED components produce DEGRADATION_START events.
        * Cascade chains are detected from the dependency graph and produce
          CASCADE_START / CASCADE_END events.
        """
        now = datetime.now(timezone.utc)

        # 1. Detect unhealthy components
        down_ids: list[str] = []
        degraded_ids: list[str] = []

        for comp in graph.components.values():
            if comp.health == HealthStatus.DOWN:
                down_ids.append(comp.id)
                self._events.append(
                    TimelineEvent(
                        timestamp=now,
                        event_type=EventType.FAILURE,
                        component_id=comp.id,
                        description=f"Component {comp.name} ({comp.id}) is DOWN",
                        severity=Severity.SEV1,
                        metadata={"health": comp.health.value, "type": comp.type.value},
                    )
                )
            elif comp.health == HealthStatus.DEGRADED:
                degraded_ids.append(comp.id)
                self._events.append(
                    TimelineEvent(
                        timestamp=now,
                        event_type=EventType.DEGRADATION_START,
                        component_id=comp.id,
                        description=f"Component {comp.name} ({comp.id}) is DEGRADED",
                        severity=Severity.SEV3,
                        metadata={"health": comp.health.value, "type": comp.type.value},
                    )
                )

        # 2. Detect cascade chains
        unhealthy_ids = down_ids + degraded_ids
        for cid in unhealthy_ids:
            affected = graph.get_all_affected(cid)
            if affected:
                self._events.append(
                    TimelineEvent(
                        timestamp=now,
                        event_type=EventType.CASCADE_START,
                        component_id=cid,
                        description=(
                            f"Cascade from {cid} affects "
                            f"{len(affected)} component(s): {', '.join(sorted(affected))}"
                        ),
                        severity=Severity.SEV2,
                        metadata={
                            "source": cid,
                            "affected": sorted(affected),
                        },
                    )
                )

        return self.build(incident_id, title)

    @staticmethod
    def get_impact_summary(timeline: IncidentTimeline) -> str:
        """Return a human-readable impact summary for a built timeline."""
        if not timeline.events:
            return "No impact detected."

        failure_count = sum(
            1 for e in timeline.events if e.event_type == EventType.FAILURE
        )
        degraded_count = sum(
            1 for e in timeline.events if e.event_type == EventType.DEGRADATION_START
        )
        cascade_count = sum(
            1 for e in timeline.events if e.event_type == EventType.CASCADE_START
        )

        parts: list[str] = []
        parts.append(
            f"Incident '{timeline.title}' ({timeline.severity.value.upper()})."
        )
        if failure_count:
            parts.append(f"{failure_count} component(s) failed.")
        if degraded_count:
            parts.append(f"{degraded_count} component(s) degraded.")
        if cascade_count:
            parts.append(f"{cascade_count} cascade chain(s) detected.")
        parts.append(
            f"{len(timeline.affected_components)} total component(s) affected."
        )
        parts.append(f"Duration: {timeline.duration_minutes:.1f} minutes.")
        parts.append(f"Root cause: {timeline.root_cause_component}.")

        return " ".join(parts)

    # -- internal helpers ---------------------------------------------------

    @staticmethod
    def _determine_severity(events: list[TimelineEvent]) -> Severity:
        """Pick the most severe severity from all events."""
        order = [Severity.SEV1, Severity.SEV2, Severity.SEV3, Severity.SEV4, Severity.SEV5]
        for sev in order:
            if any(e.severity == sev for e in events):
                return sev
        return Severity.SEV5

    @staticmethod
    def _identify_root_cause(events: list[TimelineEvent]) -> str:
        """Identify the root cause component.

        Heuristic: the component from the earliest FAILURE or
        DEGRADATION_START event is considered the root cause.
        """
        causal_types = {EventType.FAILURE, EventType.DEGRADATION_START}
        for event in events:  # already sorted by timestamp
            if event.event_type in causal_types:
                return event.component_id
        # Fallback: first event's component
        return events[0].component_id if events else "unknown"

    @staticmethod
    def _collect_affected(events: list[TimelineEvent]) -> list[str]:
        """Collect unique affected component IDs preserving first-seen order."""
        seen: set[str] = set()
        result: list[str] = []
        for event in events:
            if event.component_id not in seen:
                seen.add(event.component_id)
                result.append(event.component_id)
        return result

    @staticmethod
    def _generate_impact_summary(
        events: list[TimelineEvent],
        affected: list[str],
    ) -> str:
        """Generate a short impact summary string."""
        failure_count = sum(
            1 for e in events if e.event_type == EventType.FAILURE
        )
        degraded_count = sum(
            1 for e in events if e.event_type == EventType.DEGRADATION_START
        )
        parts: list[str] = []
        if failure_count:
            parts.append(f"{failure_count} failure(s)")
        if degraded_count:
            parts.append(f"{degraded_count} degradation(s)")
        parts.append(f"{len(affected)} component(s) affected")
        return "; ".join(parts)

    @staticmethod
    def _generate_lessons(events: list[TimelineEvent]) -> list[str]:
        """Generate lessons learned from the events."""
        lessons: list[str] = []
        has_cascade = any(e.event_type == EventType.CASCADE_START for e in events)
        has_failure = any(e.event_type == EventType.FAILURE for e in events)
        has_degradation = any(
            e.event_type == EventType.DEGRADATION_START for e in events
        )

        if has_cascade:
            lessons.append(
                "Cascade failures detected. Consider adding circuit breakers "
                "or reducing tight coupling between components."
            )
        if has_failure:
            lessons.append(
                "Component failures occurred. Review redundancy and failover "
                "configurations for affected components."
            )
        if has_degradation:
            lessons.append(
                "Component degradation observed. Improve monitoring and "
                "alerting to catch issues before full failure."
            )
        return lessons
