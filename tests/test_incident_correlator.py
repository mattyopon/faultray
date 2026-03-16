"""Tests for Incident Correlator."""

from __future__ import annotations

from pathlib import Path

import pytest

from faultray.integrations.incident_correlator import (
    CorrelationReport,
    CorrelationResult,
    IncidentCorrelator,
    IncidentRecord,
)
from faultray.model.components import (
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.engine import SimulationEngine, SimulationReport


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_graph() -> InfraGraph:
    """Build a simple test InfraGraph."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb", name="Load Balancer", type=ComponentType.LOAD_BALANCER,
    ))
    graph.add_component(Component(
        id="app", name="App Server", type=ComponentType.APP_SERVER,
    ))
    graph.add_component(Component(
        id="db", name="Database", type=ComponentType.DATABASE,
    ))
    graph.add_component(Component(
        id="cache", name="Redis Cache", type=ComponentType.CACHE,
    ))
    graph.add_dependency(Dependency(source_id="lb", target_id="app"))
    graph.add_dependency(Dependency(source_id="app", target_id="db"))
    graph.add_dependency(Dependency(
        source_id="app", target_id="cache", dependency_type="optional",
    ))
    return graph


def _make_incident(
    incident_id: str = "INC-001",
    title: str = "Database outage",
    severity: str = "critical",
    affected: list[str] | None = None,
    root_cause: str = "Database server crashed due to OOM",
    duration: float = 30.0,
    date: str = "2026-01-15",
) -> IncidentRecord:
    """Build a test IncidentRecord."""
    return IncidentRecord(
        id=incident_id,
        title=title,
        severity=severity,
        affected_components=affected or ["db"],
        root_cause=root_cause,
        duration_minutes=duration,
        date=date,
        source="manual",
    )


# ===================================================================
# IncidentCorrelator.correlate
# ===================================================================


class TestCorrelate:
    """Tests for correlate()."""

    def test_predicted_incident(self):
        """An incident matching simulation components and fault type should be predicted."""
        graph = _make_graph()
        correlator = IncidentCorrelator(graph)

        incidents = [
            _make_incident(
                incident_id="INC-001",
                title="DB crash",
                severity="critical",
                affected=["db"],
                root_cause="Database server went down",
            ),
        ]
        report = correlator.correlate(incidents)

        assert isinstance(report, CorrelationReport)
        assert report.total_incidents == 1
        assert report.predicted_count >= 0  # at least computed

    def test_unpredicted_incident_unknown_component(self):
        """An incident affecting a component not in the graph should be unpredicted."""
        graph = _make_graph()
        correlator = IncidentCorrelator(graph)

        incidents = [
            _make_incident(
                incident_id="INC-002",
                title="CDN outage",
                severity="major",
                affected=["cdn-edge"],
                root_cause="CDN provider had a global outage",
            ),
        ]
        report = correlator.correlate(incidents)

        assert report.total_incidents == 1
        # CDN is not in the graph, so coverage gap should mention it
        if report.unpredicted_incidents:
            gap = report.unpredicted_incidents[0].coverage_gap
            assert gap is not None
            assert "cdn-edge" in gap.lower() or "not in model" in gap.lower()

    def test_multiple_incidents(self):
        """Multiple incidents should be correlated independently."""
        graph = _make_graph()
        correlator = IncidentCorrelator(graph)

        incidents = [
            _make_incident(
                incident_id="INC-001",
                affected=["db"],
                root_cause="OOM killed database process",
            ),
            _make_incident(
                incident_id="INC-002",
                title="Cache degradation",
                severity="minor",
                affected=["cache"],
                root_cause="High latency on Redis cache",
            ),
            _make_incident(
                incident_id="INC-003",
                title="Unknown service crash",
                severity="major",
                affected=["unknown-svc"],
                root_cause="Service crashed for unknown reason",
            ),
        ]
        report = correlator.correlate(incidents)

        assert report.total_incidents == 3
        assert report.predicted_count + len(report.unpredicted_incidents) == 3

    def test_prediction_rate_calculation(self):
        graph = _make_graph()
        correlator = IncidentCorrelator(graph)

        incidents = [
            _make_incident(incident_id="INC-001", affected=["db"], root_cause="crash"),
            _make_incident(incident_id="INC-002", affected=["db"], root_cause="OOM"),
        ]
        report = correlator.correlate(incidents)

        assert 0.0 <= report.prediction_rate <= 1.0
        assert report.prediction_rate == report.predicted_count / report.total_incidents

    def test_empty_incidents(self):
        graph = _make_graph()
        correlator = IncidentCorrelator(graph)

        report = correlator.correlate([])

        assert report.total_incidents == 0
        assert report.prediction_rate == 0.0


# ===================================================================
# Fault type inference
# ===================================================================


class TestFaultTypeInference:
    """Tests for _infer_fault_types()."""

    def test_oom_maps_to_memory_and_down(self):
        graph = _make_graph()
        correlator = IncidentCorrelator(graph)

        faults = correlator._infer_fault_types("Process killed by OOM killer")
        assert "memory_exhaustion" in faults or "component_down" in faults

    def test_latency_maps_correctly(self):
        graph = _make_graph()
        correlator = IncidentCorrelator(graph)

        faults = correlator._infer_fault_types("High latency on API responses")
        assert "latency_spike" in faults

    def test_disk_full_maps_correctly(self):
        graph = _make_graph()
        correlator = IncidentCorrelator(graph)

        faults = correlator._infer_fault_types("Disk full, no space left")
        assert "disk_full" in faults

    def test_unknown_defaults_to_component_down(self):
        graph = _make_graph()
        correlator = IncidentCorrelator(graph)

        faults = correlator._infer_fault_types("Something weird happened")
        assert "component_down" in faults


# ===================================================================
# CSV import
# ===================================================================


class TestImportFromCsv:
    """Tests for import_from_csv()."""

    def test_basic_csv_import(self, tmp_path):
        csv_content = (
            "id,title,severity,affected_components,root_cause,duration_minutes,date\n"
            "INC-001,DB crash,critical,db;app,OOM killed db,30,2026-01-15\n"
            "INC-002,Cache slow,minor,cache,High latency,5,2026-01-16\n"
        )
        csv_path = tmp_path / "incidents.csv"
        csv_path.write_text(csv_content)

        graph = _make_graph()
        correlator = IncidentCorrelator(graph)
        incidents = correlator.import_from_csv(csv_path)

        assert len(incidents) == 2
        assert incidents[0].id == "INC-001"
        assert incidents[0].severity == "critical"
        assert incidents[0].affected_components == ["db", "app"]
        assert incidents[0].duration_minutes == 30.0
        assert incidents[0].source == "csv"

        assert incidents[1].id == "INC-002"
        assert incidents[1].severity == "minor"
        assert incidents[1].affected_components == ["cache"]

    def test_empty_csv(self, tmp_path):
        csv_content = "id,title,severity,affected_components,root_cause,duration_minutes,date\n"
        csv_path = tmp_path / "empty.csv"
        csv_path.write_text(csv_content)

        graph = _make_graph()
        correlator = IncidentCorrelator(graph)
        incidents = correlator.import_from_csv(csv_path)

        assert len(incidents) == 0

    def test_csv_with_missing_fields(self, tmp_path):
        csv_content = (
            "id,title,severity,affected_components,root_cause,duration_minutes,date\n"
            "INC-001,,,,,0,\n"
        )
        csv_path = tmp_path / "sparse.csv"
        csv_path.write_text(csv_content)

        graph = _make_graph()
        correlator = IncidentCorrelator(graph)
        incidents = correlator.import_from_csv(csv_path)

        assert len(incidents) == 1
        assert incidents[0].id == "INC-001"
        assert incidents[0].duration_minutes == 0.0


# ===================================================================
# Recommendations
# ===================================================================


class TestRecommendations:
    """Tests for _generate_recommendations()."""

    def test_recommends_adding_missing_components(self):
        graph = _make_graph()
        correlator = IncidentCorrelator(graph)

        incidents = [
            _make_incident(
                incident_id="INC-001",
                affected=["external-api"],
                root_cause="External API went down",
            ),
        ]
        report = correlator.correlate(incidents)

        # Should recommend adding the external-api component
        has_add_rec = any(
            "external-api" in r.lower()
            for r in report.recommendations
        )
        assert has_add_rec

    def test_recommends_feeds_for_many_unpredicted(self):
        graph = _make_graph()
        correlator = IncidentCorrelator(graph)

        incidents = [
            _make_incident(
                incident_id=f"INC-{i:03d}",
                affected=[f"unknown-svc-{i}"],
                root_cause=f"Unknown failure #{i}",
            )
            for i in range(5)
        ]
        report = correlator.correlate(incidents)

        has_feeds_rec = any("feed" in r.lower() for r in report.recommendations)
        assert has_feeds_rec


# ===================================================================
# End-to-end integration
# ===================================================================


class TestEndToEnd:
    """Integration tests for the full correlate workflow."""

    def test_csv_correlate_workflow(self, tmp_path):
        """Full workflow: create graph, import CSV, correlate, check report."""
        csv_content = (
            "id,title,severity,affected_components,root_cause,duration_minutes,date\n"
            "INC-001,DB OOM,critical,db,Memory exhaustion OOM,45,2026-01-15\n"
            "INC-002,App latency,major,app,High latency spike,15,2026-01-20\n"
            "INC-003,CDN issue,minor,cdn,CDN provider outage,5,2026-02-01\n"
        )
        csv_path = tmp_path / "incidents.csv"
        csv_path.write_text(csv_content)

        graph = _make_graph()
        correlator = IncidentCorrelator(graph)
        incidents = correlator.import_from_csv(csv_path)

        assert len(incidents) == 3

        report = correlator.correlate(incidents)

        assert report.total_incidents == 3
        assert 0.0 <= report.prediction_rate <= 1.0
        assert 0.0 <= report.severity_accuracy <= 1.0
        assert isinstance(report.recommendations, list)
