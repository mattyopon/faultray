"""Tests for the Observability Integration Hub."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from faultray.integrations.observability import MetricImportResult, ObservabilityHub
from faultray.model.components import (
    Capacity,
    Component,
    ComponentType,
    Dependency,
    ResourceMetrics,
)
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_test_graph() -> InfraGraph:
    """Build a 3-component graph with hosts for metric matching."""
    graph = InfraGraph()

    graph.add_component(Component(
        id="lb",
        name="Load Balancer",
        type=ComponentType.LOAD_BALANCER,
        host="lb.example.com",
        replicas=2,
        metrics=ResourceMetrics(cpu_percent=10.0, memory_percent=20.0),
    ))
    graph.add_component(Component(
        id="app",
        name="App Server",
        type=ComponentType.APP_SERVER,
        host="app.example.com",
        replicas=3,
        metrics=ResourceMetrics(cpu_percent=30.0, memory_percent=50.0),
    ))
    graph.add_component(Component(
        id="db",
        name="Database",
        type=ComponentType.DATABASE,
        host="db.example.com",
        replicas=1,
        metrics=ResourceMetrics(
            cpu_percent=45.0, memory_percent=70.0, disk_percent=55.0,
        ),
    ))

    graph.add_dependency(Dependency(
        source_id="lb", target_id="app", dependency_type="requires",
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
    ))

    return graph


# ---------------------------------------------------------------------------
# JSON Import Tests
# ---------------------------------------------------------------------------


class TestImportFromJson:
    """Tests for import_from_json."""

    def test_import_basic_metrics(self, tmp_path: Path):
        """Import basic CPU/memory/disk metrics from JSON."""
        graph = _build_test_graph()
        hub = ObservabilityHub(graph)

        metrics_file = tmp_path / "metrics.json"
        metrics_file.write_text(json.dumps({
            "app": {"cpu_percent": 75.0, "memory_percent": 85.0},
            "db": {"disk_percent": 40.0},
        }))

        result = hub.import_from_json(metrics_file)

        assert isinstance(result, MetricImportResult)
        assert result.source == "json"
        assert result.components_updated == 2
        assert result.metrics_imported == 3
        assert result.calibration_applied is True
        assert graph.get_component("app").metrics.cpu_percent == 75.0
        assert graph.get_component("app").metrics.memory_percent == 85.0
        assert graph.get_component("db").metrics.disk_percent == 40.0

    def test_import_all_supported_metrics(self, tmp_path: Path):
        """Import all supported metric fields."""
        graph = _build_test_graph()
        hub = ObservabilityHub(graph)

        metrics_file = tmp_path / "metrics.json"
        metrics_file.write_text(json.dumps({
            "app": {
                "cpu_percent": 50.0,
                "memory_percent": 60.0,
                "disk_percent": 25.0,
                "network_connections": 200,
                "memory_used_mb": 4096.0,
                "memory_total_mb": 8192.0,
                "disk_used_gb": 50.0,
                "disk_total_gb": 100.0,
                "open_files": 1024,
            },
        }))

        result = hub.import_from_json(metrics_file)

        assert result.metrics_imported == 9
        assert result.components_updated == 1
        comp = graph.get_component("app")
        assert comp.metrics.cpu_percent == 50.0
        assert comp.metrics.network_connections == 200
        assert comp.metrics.memory_used_mb == 4096.0
        assert comp.metrics.open_files == 1024

    def test_import_unknown_component_skipped(self, tmp_path: Path):
        """Unknown component IDs should be skipped with an error."""
        graph = _build_test_graph()
        hub = ObservabilityHub(graph)

        metrics_file = tmp_path / "metrics.json"
        metrics_file.write_text(json.dumps({
            "nonexistent": {"cpu_percent": 50.0},
        }))

        result = hub.import_from_json(metrics_file)

        assert result.components_updated == 0
        assert result.metrics_imported == 0
        assert len(result.errors) == 1
        assert "not found" in result.errors[0]

    def test_import_invalid_json(self, tmp_path: Path):
        """Invalid JSON should return an error."""
        graph = _build_test_graph()
        hub = ObservabilityHub(graph)

        metrics_file = tmp_path / "bad.json"
        metrics_file.write_text("not valid json {{{")

        result = hub.import_from_json(metrics_file)

        assert result.source == "json"
        assert result.calibration_applied is False
        assert len(result.errors) >= 1

    def test_import_missing_file(self):
        """Missing file should return an error."""
        graph = _build_test_graph()
        hub = ObservabilityHub(graph)

        result = hub.import_from_json(Path("/nonexistent/metrics.json"))

        assert result.calibration_applied is False
        assert len(result.errors) >= 1

    def test_import_non_dict_root(self, tmp_path: Path):
        """Non-dict root JSON should return an error."""
        graph = _build_test_graph()
        hub = ObservabilityHub(graph)

        metrics_file = tmp_path / "metrics.json"
        metrics_file.write_text(json.dumps([1, 2, 3]))

        result = hub.import_from_json(metrics_file)

        assert result.calibration_applied is False
        assert len(result.errors) >= 1
        assert "object" in result.errors[0].lower()

    def test_import_invalid_metric_value(self, tmp_path: Path):
        """Non-numeric metric values should be skipped with an error."""
        graph = _build_test_graph()
        hub = ObservabilityHub(graph)

        metrics_file = tmp_path / "metrics.json"
        metrics_file.write_text(json.dumps({
            "app": {"cpu_percent": "not_a_number", "memory_percent": 60.0},
        }))

        result = hub.import_from_json(metrics_file)

        assert result.metrics_imported == 1  # only memory_percent
        assert len(result.errors) >= 1
        assert "Invalid value" in result.errors[0]

    def test_import_empty_metrics(self, tmp_path: Path):
        """Empty metrics dict should not error but import nothing."""
        graph = _build_test_graph()
        hub = ObservabilityHub(graph)

        metrics_file = tmp_path / "metrics.json"
        metrics_file.write_text(json.dumps({}))

        result = hub.import_from_json(metrics_file)

        assert result.metrics_imported == 0
        assert result.components_updated == 0
        assert result.calibration_applied is False

    def test_import_unknown_metric_field_ignored(self, tmp_path: Path):
        """Unknown metric fields should be silently ignored."""
        graph = _build_test_graph()
        hub = ObservabilityHub(graph)

        metrics_file = tmp_path / "metrics.json"
        metrics_file.write_text(json.dumps({
            "app": {"unknown_metric": 99.0, "cpu_percent": 42.0},
        }))

        result = hub.import_from_json(metrics_file)

        assert result.metrics_imported == 1  # only cpu_percent
        assert graph.get_component("app").metrics.cpu_percent == 42.0

    def test_import_details_populated(self, tmp_path: Path):
        """Import details should contain per-metric entries."""
        graph = _build_test_graph()
        hub = ObservabilityHub(graph)

        metrics_file = tmp_path / "metrics.json"
        metrics_file.write_text(json.dumps({
            "app": {"cpu_percent": 55.0},
            "db": {"memory_percent": 80.0},
        }))

        result = hub.import_from_json(metrics_file)

        assert len(result.details) == 2
        for d in result.details:
            assert "component_id" in d
            assert "metric" in d
            assert "value" in d


# ---------------------------------------------------------------------------
# Datadog Import Tests (mocked)
# ---------------------------------------------------------------------------


class TestImportFromDatadog:
    """Tests for import_from_datadog with mocked HTTP."""

    def test_import_datadog_basic(self):
        """Import basic metrics from Datadog."""
        graph = _build_test_graph()
        hub = ObservabilityHub(graph)

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "series": [
                {
                    "scope": "app.example.com",
                    "pointlist": [[1000000, 65.0], [1000060, 70.0]],
                },
            ],
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        result = hub.import_from_datadog("api_key", "app_key", _client=mock_client)

        assert isinstance(result, MetricImportResult)
        assert result.source == "datadog"
        assert result.metrics_imported >= 1
        assert result.calibration_applied is True

    def test_import_datadog_no_matching_hosts(self):
        """When no hosts match, no metrics should be imported."""
        graph = _build_test_graph()
        hub = ObservabilityHub(graph)

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "series": [
                {
                    "scope": "unknown-host.example.com",
                    "pointlist": [[1000000, 50.0]],
                },
            ],
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        result = hub.import_from_datadog("api_key", "app_key", _client=mock_client)

        assert result.metrics_imported == 0
        assert result.calibration_applied is False

    def test_import_datadog_api_error(self):
        """API errors should be captured in errors list."""
        graph = _build_test_graph()
        hub = ObservabilityHub(graph)

        mock_client = MagicMock()
        mock_client.get.side_effect = Exception("API error")

        result = hub.import_from_datadog("api_key", "app_key", _client=mock_client)

        assert result.metrics_imported == 0
        assert len(result.errors) >= 1

    def test_import_datadog_empty_pointlist(self):
        """Empty pointlist should be skipped."""
        graph = _build_test_graph()
        hub = ObservabilityHub(graph)

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "series": [
                {"scope": "app.example.com", "pointlist": []},
            ],
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        result = hub.import_from_datadog("api_key", "app_key", _client=mock_client)

        assert result.metrics_imported == 0


# ---------------------------------------------------------------------------
# New Relic Import Tests (mocked)
# ---------------------------------------------------------------------------


class TestImportFromNewRelic:
    """Tests for import_from_newrelic with mocked HTTP."""

    def test_import_newrelic_basic(self):
        """Import basic metrics from New Relic."""
        graph = _build_test_graph()
        hub = ObservabilityHub(graph)

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "facets": [
                {
                    "name": "app.example.com",
                    "results": [{"average": 55.0}],
                },
            ],
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        result = hub.import_from_newrelic("api_key", "123456", _client=mock_client)

        assert isinstance(result, MetricImportResult)
        assert result.source == "newrelic"
        assert result.metrics_imported >= 1
        assert result.calibration_applied is True

    def test_import_newrelic_no_matching_hosts(self):
        """When no hosts match, no metrics should be imported."""
        graph = _build_test_graph()
        hub = ObservabilityHub(graph)

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "facets": [
                {
                    "name": "unknown-host",
                    "results": [{"average": 55.0}],
                },
            ],
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        result = hub.import_from_newrelic("api_key", "123456", _client=mock_client)

        assert result.metrics_imported == 0

    def test_import_newrelic_api_error(self):
        """API errors should be captured."""
        graph = _build_test_graph()
        hub = ObservabilityHub(graph)

        mock_client = MagicMock()
        mock_client.get.side_effect = Exception("NRQL error")

        result = hub.import_from_newrelic("api_key", "123456", _client=mock_client)

        assert result.metrics_imported == 0
        assert len(result.errors) >= 1


# ---------------------------------------------------------------------------
# Grafana Import Tests (mocked)
# ---------------------------------------------------------------------------


class TestImportFromGrafana:
    """Tests for import_from_grafana with mocked HTTP."""

    def test_import_grafana_basic(self):
        """Import basic metrics from Grafana."""
        graph = _build_test_graph()
        hub = ObservabilityHub(graph)

        mock_client = MagicMock()

        # First call: dashboard fetch
        dashboard_response = MagicMock()
        dashboard_response.json.return_value = {
            "dashboard": {
                "panels": [
                    {
                        "title": "CPU Usage",
                        "targets": [{"expr": "node_cpu_percent", "refId": "A"}],
                        "datasource": {"uid": "prom1"},
                    },
                ],
            },
        }
        dashboard_response.raise_for_status = MagicMock()

        # Second call: datasource proxy query
        query_response = MagicMock()
        query_response.json.return_value = {
            "data": {
                "result": [
                    {
                        "metric": {"instance": "app.example.com"},
                        "value": [1000000, "65.0"],
                    },
                ],
            },
        }
        query_response.raise_for_status = MagicMock()

        mock_client.get.side_effect = [dashboard_response, query_response]

        result = hub.import_from_grafana(
            "http://grafana:3000", "api_key", "dashboard-uid",
            _client=mock_client,
        )

        assert isinstance(result, MetricImportResult)
        assert result.source == "grafana"
        assert result.metrics_imported >= 1

    def test_import_grafana_dashboard_fetch_error(self):
        """Dashboard fetch failure should be handled gracefully."""
        graph = _build_test_graph()
        hub = ObservabilityHub(graph)

        mock_client = MagicMock()
        mock_client.get.side_effect = Exception("Dashboard not found")

        result = hub.import_from_grafana(
            "http://grafana:3000", "api_key", "bad-uid",
            _client=mock_client,
        )

        assert result.metrics_imported == 0
        assert result.calibration_applied is False
        assert len(result.errors) >= 1

    def test_import_grafana_no_matching_panels(self):
        """Panels without cpu/memory/disk titles should be skipped."""
        graph = _build_test_graph()
        hub = ObservabilityHub(graph)

        mock_client = MagicMock()
        dashboard_response = MagicMock()
        dashboard_response.json.return_value = {
            "dashboard": {
                "panels": [
                    {
                        "title": "Network Traffic",
                        "targets": [{"expr": "rate(bytes_total)", "refId": "A"}],
                    },
                ],
            },
        }
        dashboard_response.raise_for_status = MagicMock()
        mock_client.get.return_value = dashboard_response

        result = hub.import_from_grafana(
            "http://grafana:3000", "api_key", "uid",
            _client=mock_client,
        )

        assert result.metrics_imported == 0


# ---------------------------------------------------------------------------
# Host Matching Tests
# ---------------------------------------------------------------------------


class TestHostMatching:
    """Tests for component matching by host/id/name."""

    def test_match_by_host(self):
        """Should match components by host field."""
        graph = _build_test_graph()
        hub = ObservabilityHub(graph)

        comp = hub._find_component_by_host("app.example.com")
        assert comp is not None
        assert comp.id == "app"

    def test_match_by_host_with_port(self):
        """Should strip port when matching."""
        graph = _build_test_graph()
        hub = ObservabilityHub(graph)

        comp = hub._find_component_by_host("app.example.com:9100")
        assert comp is not None
        assert comp.id == "app"

    def test_match_by_id(self):
        """Should fallback to matching by component ID."""
        graph = _build_test_graph()
        hub = ObservabilityHub(graph)

        comp = hub._find_component_by_host("lb")
        assert comp is not None
        assert comp.id == "lb"

    def test_match_by_name(self):
        """Should fallback to matching by component name."""
        graph = _build_test_graph()
        hub = ObservabilityHub(graph)

        comp = hub._find_component_by_host("Load Balancer")
        assert comp is not None
        assert comp.id == "lb"

    def test_no_match_returns_none(self):
        """Should return None when no match found."""
        graph = _build_test_graph()
        hub = ObservabilityHub(graph)

        comp = hub._find_component_by_host("nonexistent.host")
        assert comp is None

    def test_empty_host_returns_none(self):
        """Empty host string should return None."""
        graph = _build_test_graph()
        hub = ObservabilityHub(graph)

        comp = hub._find_component_by_host("")
        assert comp is None
