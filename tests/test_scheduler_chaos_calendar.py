"""Tests for Chaos Calendar scheduler — experiment scheduling and tracking."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from infrasim.model.components import (
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    ResourceMetrics,
)
from infrasim.model.graph import InfraGraph
from infrasim.scheduler.chaos_calendar import (
    BlackoutWindow,
    CalendarView,
    ChaosCalendar,
    ChaosExperiment,
    ExperimentStatus,
    RecurrencePattern,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _build_graph() -> InfraGraph:
    """Build a simple 3-component graph."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb", name="Load Balancer", type=ComponentType.LOAD_BALANCER,
        replicas=2,
    ))
    graph.add_component(Component(
        id="app", name="App Server", type=ComponentType.APP_SERVER,
        replicas=1,
        metrics=ResourceMetrics(cpu_percent=75.0),
    ))
    graph.add_component(Component(
        id="db", name="Database", type=ComponentType.DATABASE,
        replicas=1,
    ))
    graph.add_dependency(Dependency(source_id="lb", target_id="app", dependency_type="requires"))
    graph.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))
    return graph


@pytest.fixture
def cal(tmp_path):
    """Return a ChaosCalendar using a temporary file."""
    return ChaosCalendar(store_path=tmp_path / "calendar.json")


@pytest.fixture
def graph():
    return _build_graph()


def _make_experiment(
    name: str = "Test Experiment",
    target: str = "app",
    days_offset: int = 1,
    status: ExperimentStatus = ExperimentStatus.SCHEDULED,
) -> ChaosExperiment:
    """Helper to create an experiment."""
    return ChaosExperiment(
        id="",
        name=name,
        description=f"Testing {target}",
        target_components=[target],
        scheduled_time=datetime.now(timezone.utc) + timedelta(days=days_offset),
        status=status,
    )


# ---------------------------------------------------------------------------
# Tests: Scheduling
# ---------------------------------------------------------------------------

class TestScheduling:
    def test_schedule_returns_id(self, cal):
        exp = _make_experiment()
        eid = cal.schedule(exp)
        assert eid
        assert len(eid) == 8  # UUID[:8]

    def test_schedule_persists(self, tmp_path):
        path = tmp_path / "cal.json"
        cal = ChaosCalendar(store_path=path)
        exp = _make_experiment()
        eid = cal.schedule(exp)

        # Reload
        cal2 = ChaosCalendar(store_path=path)
        loaded = cal2.get_experiment(eid)
        assert loaded is not None
        assert loaded.name == "Test Experiment"

    def test_schedule_generates_id_when_empty(self, cal):
        exp = ChaosExperiment(
            id="",
            name="No ID",
            description="",
        )
        eid = cal.schedule(exp)
        assert len(eid) == 8

    def test_schedule_uses_given_id(self, cal):
        exp = ChaosExperiment(
            id="custom-id",
            name="Custom",
            description="",
        )
        eid = cal.schedule(exp)
        assert eid == "custom-id"


class TestCancel:
    def test_cancel_existing(self, cal):
        exp = _make_experiment()
        eid = cal.schedule(exp)
        assert cal.cancel(eid) is True
        assert cal.get_experiment(eid).status == ExperimentStatus.CANCELLED

    def test_cancel_nonexistent(self, cal):
        assert cal.cancel("nonexistent") is False


class TestReschedule:
    def test_reschedule_updates_time(self, cal):
        exp = _make_experiment()
        eid = cal.schedule(exp)

        new_time = datetime.now(timezone.utc) + timedelta(days=10)
        assert cal.reschedule(eid, new_time) is True

        updated = cal.get_experiment(eid)
        assert updated.scheduled_time == new_time
        assert updated.status == ExperimentStatus.SCHEDULED

    def test_reschedule_nonexistent(self, cal):
        new_time = datetime.now(timezone.utc) + timedelta(days=5)
        assert cal.reschedule("nope", new_time) is False


class TestComplete:
    def test_complete_marks_status(self, cal):
        exp = _make_experiment()
        eid = cal.schedule(exp)

        results = {"passed": True, "score": 95}
        assert cal.complete(eid, results) is True

        completed = cal.get_experiment(eid)
        assert completed.status == ExperimentStatus.COMPLETED
        assert completed.results == results

    def test_complete_nonexistent(self, cal):
        assert cal.complete("nope", {}) is False


# ---------------------------------------------------------------------------
# Tests: Blackout Windows
# ---------------------------------------------------------------------------

class TestBlackoutWindows:
    def test_add_blackout(self, cal):
        bw = BlackoutWindow(
            start=datetime.now(timezone.utc) + timedelta(days=5),
            end=datetime.now(timezone.utc) + timedelta(days=7),
            reason="Holiday freeze",
        )
        cal.add_blackout(bw)
        view = cal.get_calendar_view()
        assert len(view.blackout_windows) == 1

    def test_experiment_in_blackout_is_skipped(self, cal):
        bw = BlackoutWindow(
            start=datetime.now(timezone.utc) + timedelta(days=2),
            end=datetime.now(timezone.utc) + timedelta(days=4),
            reason="Release freeze",
        )
        cal.add_blackout(bw)

        exp = ChaosExperiment(
            id="",
            name="Should be skipped",
            description="",
            scheduled_time=datetime.now(timezone.utc) + timedelta(days=3),
        )
        eid = cal.schedule(exp)
        assert cal.get_experiment(eid).status == ExperimentStatus.SKIPPED

    def test_reschedule_into_blackout(self, cal):
        bw = BlackoutWindow(
            start=datetime.now(timezone.utc) + timedelta(days=5),
            end=datetime.now(timezone.utc) + timedelta(days=7),
            reason="Deploy window",
        )
        cal.add_blackout(bw)

        exp = _make_experiment(days_offset=1)
        eid = cal.schedule(exp)
        assert cal.get_experiment(eid).status == ExperimentStatus.SCHEDULED

        # Reschedule into the blackout
        new_time = datetime.now(timezone.utc) + timedelta(days=6)
        cal.reschedule(eid, new_time)
        assert cal.get_experiment(eid).status == ExperimentStatus.SKIPPED

    def test_blackout_marks_existing_experiments(self, cal):
        exp = ChaosExperiment(
            id="",
            name="Already scheduled",
            description="",
            scheduled_time=datetime.now(timezone.utc) + timedelta(days=3),
        )
        eid = cal.schedule(exp)
        assert cal.get_experiment(eid).status == ExperimentStatus.SCHEDULED

        # Now add a blackout covering that time
        bw = BlackoutWindow(
            start=datetime.now(timezone.utc) + timedelta(days=2),
            end=datetime.now(timezone.utc) + timedelta(days=4),
            reason="Maintenance",
        )
        cal.add_blackout(bw)
        assert cal.get_experiment(eid).status == ExperimentStatus.SKIPPED


# ---------------------------------------------------------------------------
# Tests: Queries
# ---------------------------------------------------------------------------

class TestQueries:
    def test_get_upcoming(self, cal):
        cal.schedule(_make_experiment(name="Tomorrow", days_offset=1))
        cal.schedule(_make_experiment(name="Next week", days_offset=8))

        upcoming = cal.get_upcoming(days=7)
        assert len(upcoming) == 1
        assert upcoming[0].name == "Tomorrow"

    def test_get_overdue(self, cal):
        exp = ChaosExperiment(
            id="",
            name="Past due",
            description="",
            scheduled_time=datetime.now(timezone.utc) - timedelta(days=2),
        )
        cal.schedule(exp)
        overdue = cal.get_overdue()
        assert len(overdue) == 1
        assert overdue[0].name == "Past due"

    def test_get_history(self, cal):
        exp = _make_experiment()
        eid = cal.schedule(exp)
        cal.complete(eid, {"ok": True})

        history = cal.get_history(days=90)
        assert len(history) == 1
        assert history[0].status == ExperimentStatus.COMPLETED

    def test_get_history_excludes_old(self, cal):
        exp = ChaosExperiment(
            id="old",
            name="Old experiment",
            description="",
            scheduled_time=datetime.now(timezone.utc) - timedelta(days=200),
            status=ExperimentStatus.COMPLETED,
            updated_at=datetime.now(timezone.utc) - timedelta(days=200),
        )
        cal._experiments[exp.id] = exp
        assert len(cal.get_history(days=90)) == 0


class TestCalendarView:
    def test_calendar_view_structure(self, cal):
        view = cal.get_calendar_view()
        assert isinstance(view, CalendarView)
        assert isinstance(view.experiments, list)
        assert isinstance(view.upcoming, list)
        assert isinstance(view.overdue, list)
        assert isinstance(view.history, list)
        assert isinstance(view.blackout_windows, list)
        assert isinstance(view.coverage_score, float)
        assert isinstance(view.experiment_frequency, float)
        assert isinstance(view.streak, int)


class TestCoverage:
    def test_coverage_all_untested(self, cal, graph):
        coverage = cal.get_coverage(graph)
        assert all(v is False for v in coverage.values())
        assert len(coverage) == 3  # lb, app, db

    def test_coverage_after_completion(self, cal, graph):
        exp = ChaosExperiment(
            id="",
            name="Test App",
            description="",
            target_components=["app"],
            scheduled_time=datetime.now(timezone.utc) - timedelta(days=1),
            status=ExperimentStatus.COMPLETED,
            updated_at=datetime.now(timezone.utc),
        )
        cal._experiments["test"] = exp
        exp.id = "test"

        coverage = cal.get_coverage(graph)
        assert coverage["app"] is True
        assert coverage["lb"] is False
        assert coverage["db"] is False


# ---------------------------------------------------------------------------
# Tests: Auto-scheduling
# ---------------------------------------------------------------------------

class TestAutoSchedule:
    def test_auto_schedule_creates_experiments(self, cal, graph):
        experiments = cal.auto_schedule(graph)
        assert len(experiments) > 0

    def test_auto_schedule_targets_all_components(self, cal, graph):
        experiments = cal.auto_schedule(graph)
        targeted = set()
        for exp in experiments:
            targeted.update(exp.target_components)
        # Should cover all components
        assert targeted == {"lb", "app", "db"}

    def test_auto_schedule_spreads_across_days(self, cal, graph):
        experiments = cal.auto_schedule(graph)
        dates = [exp.scheduled_time.date() for exp in experiments]
        # All on different days
        assert len(set(dates)) == len(dates)

    def test_auto_schedule_avoids_blackouts(self, cal, graph):
        tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
        bw = BlackoutWindow(
            start=tomorrow,
            end=tomorrow + timedelta(days=3),
            reason="Freeze",
        )
        cal.add_blackout(bw)

        experiments = cal.auto_schedule(graph)
        for exp in experiments:
            assert exp.status != ExperimentStatus.SKIPPED or \
                   not (bw.start <= exp.scheduled_time <= bw.end)

    def test_auto_schedule_sets_owner(self, cal, graph):
        experiments = cal.auto_schedule(graph, owner="sre-team")
        for exp in experiments:
            assert exp.owner == "sre-team"

    def test_auto_schedule_prioritizes_spofs(self, cal, graph):
        experiments = cal.auto_schedule(graph)
        # app and db are SPOFs (1 replica, with dependents)
        # They should be scheduled earlier (lower day offset = higher priority)
        names = [exp.name for exp in experiments]
        # The first experiments should target the SPOFs
        assert any("App Server" in n for n in names[:2])


# ---------------------------------------------------------------------------
# Tests: iCalendar Export
# ---------------------------------------------------------------------------

class TestICalExport:
    def test_ical_structure(self, cal):
        cal.schedule(_make_experiment(name="DB Failover"))
        ical = cal.export_ical()
        assert "BEGIN:VCALENDAR" in ical
        assert "END:VCALENDAR" in ical
        assert "VERSION:2.0" in ical
        assert "PRODID:-//FaultZero//ChaosCalendar//EN" in ical

    def test_ical_contains_event(self, cal):
        cal.schedule(_make_experiment(name="DB Failover"))
        ical = cal.export_ical()
        assert "BEGIN:VEVENT" in ical
        assert "END:VEVENT" in ical
        assert "DB Failover" in ical

    def test_ical_skips_cancelled(self, cal):
        exp = _make_experiment(name="Cancelled Test")
        eid = cal.schedule(exp)
        cal.cancel(eid)
        ical = cal.export_ical()
        assert "Cancelled Test" not in ical

    def test_ical_has_uid(self, cal):
        cal.schedule(_make_experiment())
        ical = cal.export_ical()
        assert "UID:" in ical
        assert "@faultzero" in ical


# ---------------------------------------------------------------------------
# Tests: Serialization
# ---------------------------------------------------------------------------

class TestSerialization:
    def test_experiment_roundtrip(self):
        exp = ChaosExperiment(
            id="abc",
            name="Roundtrip Test",
            description="Testing serialization",
            target_components=["app", "db"],
            recurrence=RecurrencePattern.WEEKLY,
            tags=["critical", "database"],
        )
        d = exp.to_dict()
        restored = ChaosExperiment.from_dict(d)
        assert restored.id == exp.id
        assert restored.name == exp.name
        assert restored.target_components == exp.target_components
        assert restored.recurrence == RecurrencePattern.WEEKLY
        assert restored.tags == ["critical", "database"]

    def test_blackout_roundtrip(self):
        bw = BlackoutWindow(
            start=datetime(2025, 3, 25, tzinfo=timezone.utc),
            end=datetime(2025, 3, 27, tzinfo=timezone.utc),
            reason="Release freeze",
        )
        d = bw.to_dict()
        restored = BlackoutWindow.from_dict(d)
        assert restored.start == bw.start
        assert restored.end == bw.end
        assert restored.reason == "Release freeze"


class TestDurationParsing:
    def test_minutes(self, cal):
        assert cal._parse_duration("30m") == 30

    def test_hours(self, cal):
        assert cal._parse_duration("2h") == 120

    def test_hours_and_minutes(self, cal):
        assert cal._parse_duration("1h30m") == 90

    def test_plain_number(self, cal):
        assert cal._parse_duration("45") == 45

    def test_empty_string(self, cal):
        assert cal._parse_duration("") == 30


class TestStreak:
    def test_no_experiments_zero_streak(self, cal):
        assert cal._calculate_streak() == 0

    def test_streak_with_recent_completion(self, cal):
        exp = ChaosExperiment(
            id="streak-1",
            name="Recent",
            description="",
            status=ExperimentStatus.COMPLETED,
            updated_at=datetime.now(timezone.utc) - timedelta(days=2),
        )
        cal._experiments["streak-1"] = exp
        assert cal._calculate_streak() >= 1
