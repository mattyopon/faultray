"""Tests for incident timeline reconstructor."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from faultray.model.components import Component, ComponentType, Dependency, HealthStatus
from faultray.model.graph import InfraGraph
from faultray.simulator.incident_timeline import (
    EventType,
    IncidentTimeline,
    IncidentTimelineBuilder,
    Severity,
    TimelineEvent,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc)


def _comp(
    cid: str,
    name: str,
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    failover: bool = False,
    health: HealthStatus = HealthStatus.HEALTHY,
) -> Component:
    c = Component(id=cid, name=name, type=ctype, replicas=replicas)
    c.health = health
    if failover:
        c.failover.enabled = True
    return c


def _chain_graph(
    healths: dict[str, HealthStatus] | None = None,
) -> InfraGraph:
    """lb -> api -> db  with optional per-component health overrides."""
    healths = healths or {}
    g = InfraGraph()
    g.add_component(
        _comp(
            "lb", "Load Balancer",
            ComponentType.LOAD_BALANCER,
            health=healths.get("lb", HealthStatus.HEALTHY),
        )
    )
    g.add_component(
        _comp(
            "api", "API Server",
            health=healths.get("api", HealthStatus.HEALTHY),
        )
    )
    g.add_component(
        _comp(
            "db", "Database",
            ComponentType.DATABASE,
            health=healths.get("db", HealthStatus.HEALTHY),
        )
    )
    g.add_dependency(Dependency(source_id="lb", target_id="api"))
    g.add_dependency(Dependency(source_id="api", target_id="db"))
    return g


def _make_event(
    event_type: EventType = EventType.FAILURE,
    component_id: str = "app",
    severity: Severity = Severity.SEV2,
    ts: datetime | None = None,
    description: str = "Something happened",
    metadata: dict | None = None,
) -> TimelineEvent:
    return TimelineEvent(
        timestamp=ts or _NOW,
        event_type=event_type,
        component_id=component_id,
        description=description,
        severity=severity,
        metadata=metadata or {},
    )


# ===========================================================================
# 1. Enum value tests
# ===========================================================================


class TestEventTypeEnum:
    def test_all_event_types_exist(self):
        expected = {
            "DEGRADATION_START", "FAILURE", "RECOVERY", "ESCALATION",
            "MITIGATION", "ALERT_FIRED", "ALERT_RESOLVED",
            "MANUAL_ACTION", "CASCADE_START", "CASCADE_END",
        }
        assert {e.name for e in EventType} == expected

    def test_event_type_values_are_strings(self):
        for et in EventType:
            assert isinstance(et.value, str)

    def test_event_type_from_value(self):
        assert EventType("failure") is EventType.FAILURE
        assert EventType("cascade_start") is EventType.CASCADE_START


class TestSeverityEnum:
    def test_all_severity_levels_exist(self):
        expected = {"SEV1", "SEV2", "SEV3", "SEV4", "SEV5"}
        assert {s.name for s in Severity} == expected

    def test_severity_values_are_strings(self):
        for s in Severity:
            assert isinstance(s.value, str)

    def test_severity_from_value(self):
        assert Severity("sev1") is Severity.SEV1
        assert Severity("sev5") is Severity.SEV5


# ===========================================================================
# 2. TimelineEvent dataclass tests
# ===========================================================================


class TestTimelineEvent:
    def test_create_event_basic(self):
        evt = _make_event()
        assert evt.event_type == EventType.FAILURE
        assert evt.component_id == "app"
        assert evt.severity == Severity.SEV2
        assert evt.timestamp == _NOW
        assert evt.description == "Something happened"
        assert evt.metadata == {}

    def test_event_with_metadata(self):
        evt = _make_event(metadata={"key": "value", "count": 42})
        assert evt.metadata["key"] == "value"
        assert evt.metadata["count"] == 42

    def test_event_default_metadata_is_empty_dict(self):
        evt = TimelineEvent(
            timestamp=_NOW,
            event_type=EventType.ALERT_FIRED,
            component_id="x",
            description="alert",
            severity=Severity.SEV4,
        )
        assert evt.metadata == {}


# ===========================================================================
# 3. Manual event addition and timeline building
# ===========================================================================


class TestManualBuild:
    def test_build_empty_timeline(self):
        builder = IncidentTimelineBuilder()
        tl = builder.build("INC-001", "Empty incident")
        assert tl.incident_id == "INC-001"
        assert tl.title == "Empty incident"
        assert tl.severity == Severity.SEV5
        assert tl.events == []
        assert tl.duration_minutes == 0.0
        assert tl.root_cause_component == "unknown"
        assert tl.affected_components == []
        assert tl.impact_summary == "No events recorded."
        assert tl.lessons_learned == []

    def test_build_single_event(self):
        builder = IncidentTimelineBuilder()
        evt = _make_event(ts=_NOW)
        builder.add_event(evt)
        tl = builder.build("INC-002", "Single event")
        assert len(tl.events) == 1
        assert tl.start_time == _NOW
        assert tl.end_time == _NOW
        assert tl.duration_minutes == 0.0
        assert tl.root_cause_component == "app"
        assert tl.affected_components == ["app"]

    def test_build_multiple_events_sorted(self):
        builder = IncidentTimelineBuilder()
        t1 = _NOW
        t2 = _NOW + timedelta(minutes=5)
        t3 = _NOW + timedelta(minutes=10)

        builder.add_event(_make_event(ts=t3, component_id="cache"))
        builder.add_event(_make_event(ts=t1, component_id="db"))
        builder.add_event(_make_event(ts=t2, component_id="api"))

        tl = builder.build("INC-003", "Multi event")
        assert tl.events[0].timestamp == t1
        assert tl.events[1].timestamp == t2
        assert tl.events[2].timestamp == t3

    def test_duration_calculation(self):
        builder = IncidentTimelineBuilder()
        t1 = _NOW
        t2 = _NOW + timedelta(minutes=30)
        builder.add_event(_make_event(ts=t1))
        builder.add_event(_make_event(ts=t2, component_id="db"))
        tl = builder.build("INC-004", "Duration test")
        assert tl.duration_minutes == pytest.approx(30.0)

    def test_duration_fractional_minutes(self):
        builder = IncidentTimelineBuilder()
        t1 = _NOW
        t2 = _NOW + timedelta(seconds=90)
        builder.add_event(_make_event(ts=t1))
        builder.add_event(_make_event(ts=t2, component_id="db"))
        tl = builder.build("INC-005", "Fractional")
        assert tl.duration_minutes == pytest.approx(1.5)

    def test_builder_resets_after_build(self):
        builder = IncidentTimelineBuilder()
        builder.add_event(_make_event())
        tl1 = builder.build("INC-A", "First")
        assert len(tl1.events) == 1

        # Builder should be empty now
        tl2 = builder.build("INC-B", "Second")
        assert len(tl2.events) == 0

    def test_affected_components_preserves_order(self):
        builder = IncidentTimelineBuilder()
        builder.add_event(_make_event(ts=_NOW, component_id="db"))
        builder.add_event(
            _make_event(ts=_NOW + timedelta(seconds=1), component_id="api")
        )
        builder.add_event(
            _make_event(ts=_NOW + timedelta(seconds=2), component_id="lb")
        )
        # Duplicate should not appear twice
        builder.add_event(
            _make_event(ts=_NOW + timedelta(seconds=3), component_id="db")
        )
        tl = builder.build("INC-006", "Order test")
        assert tl.affected_components == ["db", "api", "lb"]


# ===========================================================================
# 4. Severity determination
# ===========================================================================


class TestSeverityDetermination:
    def test_most_severe_wins(self):
        builder = IncidentTimelineBuilder()
        builder.add_event(_make_event(severity=Severity.SEV3))
        builder.add_event(_make_event(severity=Severity.SEV1, component_id="x"))
        builder.add_event(_make_event(severity=Severity.SEV4, component_id="y"))
        tl = builder.build("INC-SEV", "Severity")
        assert tl.severity == Severity.SEV1

    def test_single_sev5(self):
        builder = IncidentTimelineBuilder()
        builder.add_event(_make_event(severity=Severity.SEV5))
        tl = builder.build("INC-S5", "Low sev")
        assert tl.severity == Severity.SEV5

    def test_sev2_without_sev1(self):
        builder = IncidentTimelineBuilder()
        builder.add_event(_make_event(severity=Severity.SEV2))
        builder.add_event(_make_event(severity=Severity.SEV4, component_id="x"))
        tl = builder.build("INC-S2", "Sev2")
        assert tl.severity == Severity.SEV2


# ===========================================================================
# 5. Root cause identification
# ===========================================================================


class TestRootCause:
    def test_root_cause_is_earliest_failure(self):
        builder = IncidentTimelineBuilder()
        builder.add_event(
            _make_event(
                event_type=EventType.FAILURE,
                ts=_NOW + timedelta(minutes=5),
                component_id="api",
            )
        )
        builder.add_event(
            _make_event(
                event_type=EventType.FAILURE,
                ts=_NOW,
                component_id="db",
            )
        )
        tl = builder.build("INC-RC1", "Root cause earliest")
        assert tl.root_cause_component == "db"

    def test_root_cause_degradation_when_no_failure(self):
        builder = IncidentTimelineBuilder()
        builder.add_event(
            _make_event(
                event_type=EventType.DEGRADATION_START,
                ts=_NOW,
                component_id="cache",
            )
        )
        builder.add_event(
            _make_event(
                event_type=EventType.ALERT_FIRED,
                ts=_NOW + timedelta(minutes=1),
                component_id="api",
            )
        )
        tl = builder.build("INC-RC2", "Root cause degradation")
        assert tl.root_cause_component == "cache"

    def test_root_cause_fallback_to_first_event(self):
        builder = IncidentTimelineBuilder()
        builder.add_event(
            _make_event(
                event_type=EventType.ALERT_FIRED,
                ts=_NOW,
                component_id="monitoring",
            )
        )
        tl = builder.build("INC-RC3", "Root cause fallback")
        assert tl.root_cause_component == "monitoring"


# ===========================================================================
# 6. Impact summary generation
# ===========================================================================


class TestImpactSummary:
    def test_impact_summary_with_failures(self):
        builder = IncidentTimelineBuilder()
        builder.add_event(_make_event(event_type=EventType.FAILURE))
        tl = builder.build("INC-IS1", "Impact test")
        assert "1 failure(s)" in tl.impact_summary
        assert "1 component(s) affected" in tl.impact_summary

    def test_impact_summary_with_degradation(self):
        builder = IncidentTimelineBuilder()
        builder.add_event(
            _make_event(event_type=EventType.DEGRADATION_START, component_id="c1")
        )
        builder.add_event(
            _make_event(event_type=EventType.DEGRADATION_START, component_id="c2")
        )
        tl = builder.build("INC-IS2", "Degradation impact")
        assert "2 degradation(s)" in tl.impact_summary

    def test_impact_summary_no_events(self):
        builder = IncidentTimelineBuilder()
        tl = builder.build("INC-IS3", "No events")
        assert tl.impact_summary == "No events recorded."

    def test_get_impact_summary_static(self):
        builder = IncidentTimelineBuilder()
        builder.add_event(_make_event(event_type=EventType.FAILURE, component_id="db"))
        builder.add_event(
            _make_event(
                event_type=EventType.CASCADE_START,
                component_id="api",
                ts=_NOW + timedelta(seconds=1),
            )
        )
        tl = builder.build("INC-IS4", "Static summary")
        summary = IncidentTimelineBuilder.get_impact_summary(tl)
        assert "INC-IS4" not in summary  # incident_id not in summary
        assert "Static summary" in summary
        assert "1 component(s) failed" in summary
        assert "1 cascade chain(s) detected" in summary
        assert "Duration:" in summary
        assert "Root cause:" in summary

    def test_get_impact_summary_empty_timeline(self):
        builder = IncidentTimelineBuilder()
        tl = builder.build("INC-IS5", "Empty")
        summary = IncidentTimelineBuilder.get_impact_summary(tl)
        assert summary == "No impact detected."


# ===========================================================================
# 7. Lessons learned
# ===========================================================================


class TestLessonsLearned:
    def test_lessons_for_cascade(self):
        builder = IncidentTimelineBuilder()
        builder.add_event(
            _make_event(event_type=EventType.CASCADE_START, component_id="db")
        )
        tl = builder.build("INC-LL1", "Cascade lessons")
        assert any("circuit breakers" in l.lower() for l in tl.lessons_learned)

    def test_lessons_for_failure(self):
        builder = IncidentTimelineBuilder()
        builder.add_event(
            _make_event(event_type=EventType.FAILURE, component_id="api")
        )
        tl = builder.build("INC-LL2", "Failure lessons")
        assert any("redundancy" in l.lower() or "failover" in l.lower() for l in tl.lessons_learned)

    def test_lessons_for_degradation(self):
        builder = IncidentTimelineBuilder()
        builder.add_event(
            _make_event(event_type=EventType.DEGRADATION_START, component_id="cache")
        )
        tl = builder.build("INC-LL3", "Degradation lessons")
        assert any("monitoring" in l.lower() for l in tl.lessons_learned)

    def test_no_lessons_for_recovery_only(self):
        builder = IncidentTimelineBuilder()
        builder.add_event(
            _make_event(event_type=EventType.RECOVERY, component_id="api")
        )
        tl = builder.build("INC-LL4", "Recovery only")
        assert tl.lessons_learned == []


# ===========================================================================
# 8. Auto-detection from graph — build_from_graph
# ===========================================================================


class TestBuildFromGraph:
    def test_all_healthy_graph(self):
        g = _chain_graph()
        builder = IncidentTimelineBuilder()
        tl = builder.build_from_graph(g, "INC-H1", "All healthy")
        assert tl.severity == Severity.SEV5
        assert tl.events == []
        assert tl.affected_components == []

    def test_single_down_component(self):
        g = _chain_graph(healths={"db": HealthStatus.DOWN})
        builder = IncidentTimelineBuilder()
        tl = builder.build_from_graph(g, "INC-D1", "DB down")

        failure_events = [e for e in tl.events if e.event_type == EventType.FAILURE]
        assert len(failure_events) == 1
        assert failure_events[0].component_id == "db"
        assert "db" in tl.affected_components

    def test_single_degraded_component(self):
        g = _chain_graph(healths={"api": HealthStatus.DEGRADED})
        builder = IncidentTimelineBuilder()
        tl = builder.build_from_graph(g, "INC-DG1", "API degraded")

        degradation_events = [
            e for e in tl.events if e.event_type == EventType.DEGRADATION_START
        ]
        assert len(degradation_events) == 1
        assert degradation_events[0].component_id == "api"

    def test_down_component_metadata(self):
        g = _chain_graph(healths={"db": HealthStatus.DOWN})
        builder = IncidentTimelineBuilder()
        tl = builder.build_from_graph(g, "INC-DM1", "Metadata test")

        failure = [e for e in tl.events if e.event_type == EventType.FAILURE][0]
        assert failure.metadata["health"] == "down"
        assert failure.metadata["type"] == "database"

    def test_multiple_down_components(self):
        g = _chain_graph(healths={
            "db": HealthStatus.DOWN,
            "api": HealthStatus.DOWN,
        })
        builder = IncidentTimelineBuilder()
        tl = builder.build_from_graph(g, "INC-MD1", "Multiple down")

        failure_events = [e for e in tl.events if e.event_type == EventType.FAILURE]
        failed_ids = {e.component_id for e in failure_events}
        assert "db" in failed_ids
        assert "api" in failed_ids

    def test_mixed_health_states(self):
        g = _chain_graph(healths={
            "db": HealthStatus.DOWN,
            "api": HealthStatus.DEGRADED,
        })
        builder = IncidentTimelineBuilder()
        tl = builder.build_from_graph(g, "INC-MX1", "Mixed health")

        types = {e.event_type for e in tl.events}
        assert EventType.FAILURE in types
        assert EventType.DEGRADATION_START in types

    def test_severity_is_sev1_when_down(self):
        g = _chain_graph(healths={"db": HealthStatus.DOWN})
        builder = IncidentTimelineBuilder()
        tl = builder.build_from_graph(g, "INC-SV1", "Sev check")
        # FAILURE events get SEV1, so overall severity should be SEV1
        assert tl.severity == Severity.SEV1


# ===========================================================================
# 9. Cascade chain detection
# ===========================================================================


class TestCascadeDetection:
    def test_cascade_from_down_leaf(self):
        """db is DOWN; api depends on db; lb depends on api.
        Cascade from db should affect api (and lb through api)."""
        g = _chain_graph(healths={"db": HealthStatus.DOWN})
        builder = IncidentTimelineBuilder()
        tl = builder.build_from_graph(g, "INC-CC1", "Cascade from db")

        cascade_events = [
            e for e in tl.events if e.event_type == EventType.CASCADE_START
        ]
        assert len(cascade_events) >= 1

        # The cascade from db should mention affected components
        db_cascade = [e for e in cascade_events if e.component_id == "db"]
        assert len(db_cascade) == 1
        assert "api" in db_cascade[0].metadata["affected"]

    def test_no_cascade_when_no_dependents(self):
        """A standalone component with no dependents should not cascade."""
        g = InfraGraph()
        g.add_component(
            _comp("solo", "Solo Server", health=HealthStatus.DOWN)
        )
        builder = IncidentTimelineBuilder()
        tl = builder.build_from_graph(g, "INC-CC2", "No cascade")

        cascade_events = [
            e for e in tl.events if e.event_type == EventType.CASCADE_START
        ]
        assert len(cascade_events) == 0

    def test_cascade_event_severity_is_sev2(self):
        g = _chain_graph(healths={"db": HealthStatus.DOWN})
        builder = IncidentTimelineBuilder()
        tl = builder.build_from_graph(g, "INC-CC3", "Cascade sev")

        cascade_events = [
            e for e in tl.events if e.event_type == EventType.CASCADE_START
        ]
        for ce in cascade_events:
            assert ce.severity == Severity.SEV2

    def test_cascade_from_degraded(self):
        g = _chain_graph(healths={"db": HealthStatus.DEGRADED})
        builder = IncidentTimelineBuilder()
        tl = builder.build_from_graph(g, "INC-CC4", "Degraded cascade")

        cascade_events = [
            e for e in tl.events if e.event_type == EventType.CASCADE_START
        ]
        # db is degraded and has dependents (api -> lb), so cascade is generated
        assert len(cascade_events) >= 1

    def test_cascade_wider_graph(self):
        """Test cascade in a wider dependency graph:
        lb -> api -> db
        lb -> api -> cache
        """
        g = InfraGraph()
        g.add_component(_comp("lb", "LB", ComponentType.LOAD_BALANCER))
        g.add_component(_comp("api", "API"))
        g.add_component(_comp("db", "DB", ComponentType.DATABASE, health=HealthStatus.DOWN))
        g.add_component(_comp("cache", "Cache", ComponentType.CACHE))
        g.add_dependency(Dependency(source_id="lb", target_id="api"))
        g.add_dependency(Dependency(source_id="api", target_id="db"))
        g.add_dependency(Dependency(source_id="api", target_id="cache"))

        builder = IncidentTimelineBuilder()
        tl = builder.build_from_graph(g, "INC-CC5", "Wider cascade")

        cascade_events = [
            e for e in tl.events if e.event_type == EventType.CASCADE_START
        ]
        assert len(cascade_events) >= 1
        db_cascade = [e for e in cascade_events if e.component_id == "db"]
        assert len(db_cascade) == 1
        assert "api" in db_cascade[0].metadata["affected"]


# ===========================================================================
# 10. IncidentTimeline dataclass tests
# ===========================================================================


class TestIncidentTimelineDataclass:
    def test_timeline_fields(self):
        tl = IncidentTimeline(
            incident_id="INC-T1",
            title="Test",
            severity=Severity.SEV3,
            events=[],
            start_time=_NOW,
            end_time=_NOW + timedelta(hours=1),
            duration_minutes=60.0,
            root_cause_component="db",
            affected_components=["db", "api"],
            impact_summary="Summary text",
            lessons_learned=["Lesson 1"],
        )
        assert tl.incident_id == "INC-T1"
        assert tl.title == "Test"
        assert tl.severity == Severity.SEV3
        assert tl.duration_minutes == 60.0
        assert tl.root_cause_component == "db"
        assert len(tl.affected_components) == 2
        assert tl.impact_summary == "Summary text"
        assert tl.lessons_learned == ["Lesson 1"]

    def test_timeline_end_time_none(self):
        tl = IncidentTimeline(
            incident_id="INC-T2",
            title="Ongoing",
            severity=Severity.SEV1,
            events=[],
            start_time=_NOW,
            end_time=None,
            duration_minutes=0.0,
            root_cause_component="unknown",
            affected_components=[],
            impact_summary="",
            lessons_learned=[],
        )
        assert tl.end_time is None


# ===========================================================================
# 11. Edge cases
# ===========================================================================


class TestEdgeCases:
    def test_graph_with_only_healthy_components(self):
        g = _chain_graph()
        builder = IncidentTimelineBuilder()
        tl = builder.build_from_graph(g, "INC-EC1", "Healthy")
        assert len(tl.events) == 0
        assert tl.severity == Severity.SEV5

    def test_graph_with_single_component_down(self):
        g = InfraGraph()
        g.add_component(_comp("solo", "Solo", health=HealthStatus.DOWN))
        builder = IncidentTimelineBuilder()
        tl = builder.build_from_graph(g, "INC-EC2", "Solo down")
        assert len(tl.events) == 1
        assert tl.events[0].event_type == EventType.FAILURE
        assert tl.root_cause_component == "solo"

    def test_overloaded_health_not_detected(self):
        """OVERLOADED health status should NOT produce events
        (only DOWN and DEGRADED are detected)."""
        g = InfraGraph()
        g.add_component(_comp("srv", "Server", health=HealthStatus.OVERLOADED))
        builder = IncidentTimelineBuilder()
        tl = builder.build_from_graph(g, "INC-EC3", "Overloaded")
        assert len(tl.events) == 0

    def test_empty_graph(self):
        g = InfraGraph()
        builder = IncidentTimelineBuilder()
        tl = builder.build_from_graph(g, "INC-EC4", "Empty graph")
        assert tl.events == []
        assert tl.severity == Severity.SEV5

    def test_many_events_same_timestamp(self):
        builder = IncidentTimelineBuilder()
        for i in range(10):
            builder.add_event(
                _make_event(component_id=f"c{i}", ts=_NOW, severity=Severity.SEV3)
            )
        tl = builder.build("INC-EC5", "Same timestamp")
        assert len(tl.events) == 10
        assert tl.duration_minutes == 0.0
        assert len(tl.affected_components) == 10

    def test_events_with_all_event_types(self):
        builder = IncidentTimelineBuilder()
        for i, et in enumerate(EventType):
            builder.add_event(
                _make_event(
                    event_type=et,
                    component_id=f"c{i}",
                    ts=_NOW + timedelta(seconds=i),
                )
            )
        tl = builder.build("INC-EC6", "All types")
        assert len(tl.events) == len(EventType)

    def test_graph_all_down(self):
        g = _chain_graph(healths={
            "lb": HealthStatus.DOWN,
            "api": HealthStatus.DOWN,
            "db": HealthStatus.DOWN,
        })
        builder = IncidentTimelineBuilder()
        tl = builder.build_from_graph(g, "INC-EC7", "All down")

        failure_events = [e for e in tl.events if e.event_type == EventType.FAILURE]
        assert len(failure_events) == 3
        assert tl.severity == Severity.SEV1
