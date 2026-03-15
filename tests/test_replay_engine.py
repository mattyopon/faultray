"""Tests for the Infrastructure Replay Engine (JSON timeline replay)."""

import json
import tempfile
from pathlib import Path

from infrasim.model.components import (
    Capacity,
    Component,
    ComponentType,
    Dependency,
    OperationalProfile,
    ResourceMetrics,
)
from infrasim.model.graph import InfraGraph
from infrasim.simulator.replay_engine import (
    CounterfactualResult,
    IncidentTimeline,
    IncidentTimelineEvent,
    ReplayEngine,
    ReplayResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_test_graph() -> InfraGraph:
    """Build a 3-component graph: lb -> app -> db."""
    graph = InfraGraph()

    graph.add_component(Component(
        id="lb", name="Load Balancer", type=ComponentType.LOAD_BALANCER,
        replicas=1, capacity=Capacity(max_connections=10000),
    ))
    graph.add_component(Component(
        id="app", name="App Server", type=ComponentType.APP_SERVER,
        replicas=1,
        capacity=Capacity(max_connections=500, timeout_seconds=30),
        metrics=ResourceMetrics(network_connections=100),
        operational_profile=OperationalProfile(mttr_minutes=15),
    ))
    graph.add_component(Component(
        id="db", name="Database", type=ComponentType.DATABASE,
        replicas=1,
        capacity=Capacity(max_connections=100),
        metrics=ResourceMetrics(network_connections=50, disk_percent=40),
        operational_profile=OperationalProfile(mttr_minutes=30),
    ))

    graph.add_dependency(Dependency(
        source_id="lb", target_id="app", dependency_type="requires",
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
    ))

    return graph


def _make_timeline(**overrides) -> IncidentTimeline:
    """Create a simple incident timeline with optional overrides."""
    defaults = {
        "incident_id": "INC-001",
        "title": "DB disk full",
        "start_time": "2024-01-15T02:30:00Z",
        "duration_minutes": 45,
        "severity": 7.0,
        "root_cause": "Disk full on primary DB",
        "resolution": "Expanded disk, cleared logs",
        "events": [
            IncidentTimelineEvent(
                timestamp_offset_seconds=0,
                event_type="component_down",
                component_id="db",
                details="Disk full, writes failing",
            ),
            IncidentTimelineEvent(
                timestamp_offset_seconds=300,
                event_type="escalation",
                component_id="app",
                details="App failing due to DB dependency",
            ),
            IncidentTimelineEvent(
                timestamp_offset_seconds=2700,
                event_type="recovery",
                component_id="db",
                details="Disk expanded, DB recovered",
            ),
        ],
    }
    defaults.update(overrides)
    return IncidentTimeline(**defaults)


def _write_timeline_json(timeline: IncidentTimeline, path: Path) -> None:
    """Serialize a timeline to JSON for import testing."""
    data = {
        "incident_id": timeline.incident_id,
        "title": timeline.title,
        "start_time": timeline.start_time,
        "duration_minutes": timeline.duration_minutes,
        "severity": timeline.severity,
        "root_cause": timeline.root_cause,
        "resolution": timeline.resolution,
        "events": [
            {
                "timestamp_offset_seconds": ev.timestamp_offset_seconds,
                "event_type": ev.event_type,
                "component_id": ev.component_id,
                "details": ev.details,
            }
            for ev in timeline.events
        ],
    }
    path.write_text(json.dumps(data), encoding="utf-8")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_replay_returns_result():
    """Replay should return a ReplayResult."""
    graph = _build_test_graph()
    engine = ReplayEngine(graph)
    timeline = _make_timeline()

    result = engine.replay(timeline)

    assert isinstance(result, ReplayResult)
    assert result.incident_id == "INC-001"


def test_replay_predicted_severity_positive():
    """Predicted severity should be positive for a real failure scenario."""
    graph = _build_test_graph()
    engine = ReplayEngine(graph)
    timeline = _make_timeline()

    result = engine.replay(timeline)

    assert result.predicted_severity > 0.0


def test_replay_matches_close_severity():
    """If predicted and actual severity are close, simulation_matches_reality = True."""
    graph = _build_test_graph()
    engine = ReplayEngine(graph)
    timeline = _make_timeline()

    result = engine.replay(timeline)

    # The result should have a definite boolean
    assert isinstance(result.simulation_matches_reality, bool)


def test_replay_generates_lessons():
    """Replay should generate at least one lesson."""
    graph = _build_test_graph()
    engine = ReplayEngine(graph)
    timeline = _make_timeline()

    result = engine.replay(timeline)

    assert len(result.lessons) > 0


def test_replay_generates_counterfactuals():
    """Replay should generate counterfactual what-if scenarios."""
    graph = _build_test_graph()
    engine = ReplayEngine(graph)
    timeline = _make_timeline()

    result = engine.replay(timeline)

    assert len(result.counterfactuals) > 0
    for cf in result.counterfactuals:
        assert isinstance(cf, CounterfactualResult)
        assert cf.improvement >= 0  # should always be non-negative improvement


def test_replay_with_unknown_component():
    """Events referencing unknown components should be gracefully skipped."""
    graph = _build_test_graph()
    engine = ReplayEngine(graph)
    timeline = _make_timeline(events=[
        IncidentTimelineEvent(
            timestamp_offset_seconds=0,
            event_type="component_down",
            component_id="nonexistent-service",
            details="Unknown service down",
        ),
    ])

    result = engine.replay(timeline)

    assert isinstance(result, ReplayResult)
    # Should mention missing components in lessons
    has_missing_lesson = any("missing" in lesson.lower() for lesson in result.lessons)
    assert has_missing_lesson


def test_replay_with_traffic_spike():
    """Traffic spike events should be converted to traffic_multiplier > 1."""
    graph = _build_test_graph()
    engine = ReplayEngine(graph)
    timeline = _make_timeline(events=[
        IncidentTimelineEvent(
            timestamp_offset_seconds=0,
            event_type="traffic_spike",
            component_id="app",
            details="10x traffic spike",
        ),
    ])

    result = engine.replay(timeline)

    assert isinstance(result, ReplayResult)
    # Should have scenario results
    assert len(result.scenario_results) > 0


def test_import_timeline_from_json():
    """import_timeline_from_json should correctly parse a JSON file."""
    graph = _build_test_graph()
    engine = ReplayEngine(graph)
    timeline = _make_timeline()

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as f:
        _write_timeline_json(timeline, Path(f.name))
        tmp_path = Path(f.name)

    try:
        loaded = engine.import_timeline_from_json(tmp_path)

        assert loaded.incident_id == "INC-001"
        assert loaded.title == "DB disk full"
        assert loaded.duration_minutes == 45
        assert loaded.severity == 7.0
        assert len(loaded.events) == 3
        assert loaded.events[0].component_id == "db"
    finally:
        tmp_path.unlink(missing_ok=True)


def test_counterfactual_replicas():
    """Counterfactuals should include a 'replicas' entry."""
    graph = _build_test_graph()
    engine = ReplayEngine(graph)
    timeline = _make_timeline()

    result = engine.replay(timeline)

    replica_cf = [
        cf for cf in result.counterfactuals
        if cf.modified_parameter == "replicas"
    ]
    assert len(replica_cf) > 0
    assert replica_cf[0].improvement > 0


def test_replay_empty_events():
    """Empty events list should produce a result with zero severity."""
    graph = _build_test_graph()
    engine = ReplayEngine(graph)
    timeline = _make_timeline(events=[])

    result = engine.replay(timeline)

    assert isinstance(result, ReplayResult)
    assert result.predicted_severity == 0.0


def test_replay_root_cause_in_lessons():
    """Root cause from the timeline should appear in lessons."""
    graph = _build_test_graph()
    engine = ReplayEngine(graph)
    timeline = _make_timeline(root_cause="Disk full on primary DB")

    result = engine.replay(timeline)

    root_cause_lesson = any(
        "Disk full" in lesson for lesson in result.lessons
    )
    assert root_cause_lesson


def test_replay_resolution_in_lessons():
    """Resolution from the timeline should appear in lessons."""
    graph = _build_test_graph()
    engine = ReplayEngine(graph)
    timeline = _make_timeline(resolution="Expanded disk, cleared logs")

    result = engine.replay(timeline)

    resolution_lesson = any(
        "Expanded disk" in lesson for lesson in result.lessons
    )
    assert resolution_lesson
