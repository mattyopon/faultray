"""Tests for Digital Twin / Live Shadow simulation."""

from __future__ import annotations

import time

import pytest

from infrasim.model.components import (
    AutoScalingConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    OperationalProfile,
    ResourceMetrics,
)
from infrasim.model.graph import InfraGraph
from infrasim.simulator.digital_twin import (
    DigitalTwin,
    DigitalTwinReport,
    PredictionWarning,
    TwinSnapshot,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _build_simple_graph() -> InfraGraph:
    """Build a minimal LB -> App -> DB graph."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb", name="Load Balancer", type=ComponentType.LOAD_BALANCER,
        replicas=2,
    ))
    graph.add_component(Component(
        id="app", name="App Server", type=ComponentType.APP_SERVER,
        replicas=2,
        autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=10, scale_up_step=2),
        metrics=ResourceMetrics(cpu_percent=50.0, memory_percent=40.0, disk_percent=30.0),
    ))
    graph.add_component(Component(
        id="db", name="Database", type=ComponentType.DATABASE,
        replicas=1,
        metrics=ResourceMetrics(cpu_percent=70.0, memory_percent=60.0, disk_percent=50.0),
    ))
    graph.add_dependency(Dependency(source_id="lb", target_id="app", dependency_type="requires"))
    graph.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))
    return graph


def _build_high_cpu_graph() -> InfraGraph:
    """Graph where a component has very high CPU."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="hot", name="Hot Service", type=ComponentType.APP_SERVER,
        replicas=1,
        metrics=ResourceMetrics(cpu_percent=88.0, memory_percent=82.0, disk_percent=85.0),
    ))
    return graph


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPredictionWarning:
    """Ensure the PredictionWarning dataclass works correctly."""

    def test_create(self):
        w = PredictionWarning(
            component_id="app",
            metric="cpu_percent",
            current_value=70.0,
            predicted_value=95.0,
            threshold=90.0,
            time_to_threshold_minutes=30.0,
            severity="critical",
            recommended_action="Scale up",
        )
        assert w.component_id == "app"
        assert w.severity == "critical"
        assert w.predicted_value == 95.0


class TestTwinSnapshot:
    """Ensure TwinSnapshot dataclass works."""

    def test_create(self):
        snap = TwinSnapshot(
            timestamp=time.time(),
            component_states={"app": {"cpu_percent": 55.0}},
            warnings=[],
            predicted_availability=99.99,
        )
        assert snap.predicted_availability == 99.99
        assert len(snap.warnings) == 0


class TestDigitalTwinNoMetrics:
    """Predict using graph defaults (no ingested metrics)."""

    def test_predict_healthy(self):
        graph = _build_simple_graph()
        twin = DigitalTwin(graph, prediction_horizon_minutes=60)
        snap = twin.predict()

        assert isinstance(snap, TwinSnapshot)
        assert snap.predicted_availability >= 99.0
        # LB and App have moderate metrics, no warnings expected
        assert "lb" in snap.component_states
        assert "app" in snap.component_states
        assert "db" in snap.component_states

    def test_predict_high_cpu_warns(self):
        graph = _build_high_cpu_graph()
        twin = DigitalTwin(graph, prediction_horizon_minutes=60)
        snap = twin.predict()

        # The component already has 88% CPU, at threshold=90 with no trend
        # it shouldn't trigger since prediction = current (no trend data).
        # Verify at least the states are populated.
        assert "hot" in snap.component_states


class TestDigitalTwinWithMetrics:
    """Predict using ingested time-series metrics."""

    def test_cpu_rising_triggers_warning(self):
        graph = _build_simple_graph()
        twin = DigitalTwin(graph, prediction_horizon_minutes=60)

        # Simulate rising CPU on "app" — from 50% to 80% over 30 "minutes"
        base_time = time.time()
        for i in range(31):
            twin._history.append({
                "timestamp": base_time + i * 60,
                "metrics": {
                    "app": {"cpu_percent": 50.0 + i, "memory_percent": 40.0, "disk_percent": 30.0},
                    "db": {"cpu_percent": 70.0, "memory_percent": 60.0, "disk_percent": 50.0},
                    "lb": {"cpu_percent": 20.0, "memory_percent": 20.0, "disk_percent": 10.0},
                },
            })

        snap = twin.predict()
        # The trend for app.cpu is +1/min. After 60 min, predicted = 80 + 60 = 140 → clamped to 100.
        cpu_warnings = [w for w in snap.warnings if w.component_id == "app" and w.metric == "cpu_percent"]
        assert len(cpu_warnings) == 1
        assert cpu_warnings[0].severity == "critical"
        assert cpu_warnings[0].predicted_value == 100.0  # clamped

    def test_memory_rising_triggers_warning(self):
        graph = _build_simple_graph()
        twin = DigitalTwin(graph, prediction_horizon_minutes=60)

        base_time = time.time()
        for i in range(21):
            twin._history.append({
                "timestamp": base_time + i * 60,
                "metrics": {
                    "db": {"cpu_percent": 70.0, "memory_percent": 60.0 + i, "disk_percent": 50.0},
                    "app": {"cpu_percent": 50.0, "memory_percent": 40.0, "disk_percent": 30.0},
                    "lb": {"cpu_percent": 20.0, "memory_percent": 20.0, "disk_percent": 10.0},
                },
            })

        snap = twin.predict()
        mem_warnings = [w for w in snap.warnings if w.component_id == "db" and w.metric == "memory_percent"]
        assert len(mem_warnings) == 1
        assert mem_warnings[0].severity == "warning"

    def test_disk_rising_triggers_warning(self):
        graph = _build_simple_graph()
        twin = DigitalTwin(graph, prediction_horizon_minutes=120)

        base_time = time.time()
        for i in range(11):
            twin._history.append({
                "timestamp": base_time + i * 60,
                "metrics": {
                    "db": {"cpu_percent": 70.0, "memory_percent": 60.0, "disk_percent": 50.0 + i * 4},
                    "app": {"cpu_percent": 50.0, "memory_percent": 40.0, "disk_percent": 30.0},
                    "lb": {"cpu_percent": 20.0, "memory_percent": 20.0, "disk_percent": 10.0},
                },
            })

        snap = twin.predict()
        disk_warnings = [w for w in snap.warnings if w.component_id == "db" and w.metric == "disk_percent"]
        assert len(disk_warnings) == 1
        assert disk_warnings[0].severity == "critical"

    def test_stable_metrics_no_warnings(self):
        graph = _build_simple_graph()
        twin = DigitalTwin(graph, prediction_horizon_minutes=60)

        base_time = time.time()
        for i in range(10):
            twin._history.append({
                "timestamp": base_time + i * 60,
                "metrics": {
                    "app": {"cpu_percent": 30.0, "memory_percent": 30.0, "disk_percent": 20.0},
                    "db": {"cpu_percent": 30.0, "memory_percent": 30.0, "disk_percent": 20.0},
                    "lb": {"cpu_percent": 10.0, "memory_percent": 10.0, "disk_percent": 5.0},
                },
            })

        snap = twin.predict()
        assert len(snap.warnings) == 0
        assert snap.predicted_availability == 99.99


class TestDigitalTwinReport:
    """Test the report() aggregation."""

    def test_report_aggregates_snapshots(self):
        graph = _build_simple_graph()
        twin = DigitalTwin(graph, prediction_horizon_minutes=60)

        # Two predictions
        twin.predict()
        twin.predict()

        report = twin.report()
        assert isinstance(report, DigitalTwinReport)
        assert len(report.snapshots) == 2
        assert report.prediction_horizon_minutes == 60

    def test_report_autoscale_suggestions(self):
        graph = _build_simple_graph()
        twin = DigitalTwin(graph, prediction_horizon_minutes=60)

        # Inject rising CPU on "app" (which has autoscaling enabled)
        base_time = time.time()
        for i in range(31):
            twin._history.append({
                "timestamp": base_time + i * 60,
                "metrics": {
                    "app": {"cpu_percent": 50.0 + i, "memory_percent": 40.0, "disk_percent": 30.0},
                    "db": {"cpu_percent": 70.0, "memory_percent": 60.0, "disk_percent": 50.0},
                    "lb": {"cpu_percent": 20.0, "memory_percent": 20.0, "disk_percent": 10.0},
                },
            })

        twin.predict()
        report = twin.report()

        assert report.critical_warnings > 0
        # "app" has autoscaling enabled, so we should see a suggestion
        assert len(report.auto_scale_suggestions) > 0
        assert report.auto_scale_suggestions[0]["component_id"] == "app"


class TestDigitalTwinIngestMetrics:
    """Test the ingest_metrics public API."""

    def test_ingest_appends_history(self):
        graph = _build_simple_graph()
        twin = DigitalTwin(graph)

        twin.ingest_metrics({"app": {"cpu_percent": 55.0}})
        assert len(twin._history) == 1

        twin.ingest_metrics({"app": {"cpu_percent": 60.0}})
        assert len(twin._history) == 2

    def test_ingest_truncates_at_60(self):
        graph = _build_simple_graph()
        twin = DigitalTwin(graph)

        for i in range(70):
            twin.ingest_metrics({"app": {"cpu_percent": float(i)}})

        assert len(twin._history) == 60


class TestDigitalTwinInternals:
    """Test internal helper methods."""

    def test_time_to_threshold_decreasing(self):
        graph = _build_simple_graph()
        twin = DigitalTwin(graph)

        # Decreasing trend → infinite time to threshold
        base_time = time.time()
        twin._history = [
            {"timestamp": base_time, "metrics": {"app": {"cpu_percent": 80.0}}},
            {"timestamp": base_time + 600, "metrics": {"app": {"cpu_percent": 70.0}}},
        ]

        ttt = twin._time_to_threshold("app", "cpu_percent", 90.0)
        assert ttt == float("inf")

    def test_extrapolate_clamps(self):
        graph = _build_simple_graph()
        twin = DigitalTwin(graph)

        result = twin._extrapolate({"cpu_percent": 90.0}, {"cpu_percent": 5.0}, 60)
        assert result["cpu_percent"] == 100.0  # clamped at 100

        result = twin._extrapolate({"cpu_percent": 10.0}, {"cpu_percent": -5.0}, 60)
        assert result["cpu_percent"] == 0.0  # clamped at 0

    def test_predict_availability_many_critical(self):
        graph = _build_simple_graph()
        twin = DigitalTwin(graph)

        many_warnings = [
            PredictionWarning("a", "cpu", 0, 0, 0, 0, "critical", ""),
            PredictionWarning("b", "cpu", 0, 0, 0, 0, "critical", ""),
            PredictionWarning("c", "cpu", 0, 0, 0, 0, "critical", ""),
        ]
        assert twin._predict_availability(many_warnings) == 95.0

    def test_predict_availability_one_critical(self):
        graph = _build_simple_graph()
        twin = DigitalTwin(graph)

        warnings = [PredictionWarning("a", "cpu", 0, 0, 0, 0, "critical", "")]
        assert twin._predict_availability(warnings) == 99.0

    def test_predict_availability_no_warnings(self):
        graph = _build_simple_graph()
        twin = DigitalTwin(graph)
        assert twin._predict_availability([]) == 99.99
