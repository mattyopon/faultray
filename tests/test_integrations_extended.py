"""Extended integration tests for untested modules.

Covers:
  1. src/faultray/integrations/observability.py
     - ObservabilityHub.import_from_json with valid data
     - ObservabilityHub.import_from_json with missing component
     - ObservabilityHub.import_from_json with invalid JSON file
     - ObservabilityHub.import_from_json with non-dict root
     - ObservabilityHub._find_component_by_host matching logic
     - ObservabilityHub._apply_metric for each metric type

  2. src/faultray/log_config.py
     - setup_logging with different levels (DEBUG, INFO, WARNING)
     - setup_logging with json_format=True
     - setup_logging idempotent (no duplicate handlers)

  3. src/faultray/model/demo.py
     - create_demo_graph produces valid graph
     - Graph has expected components and dependencies
     - Graph can be saved and reloaded
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from faultray.model.demo import create_demo_graph
from faultray.model.graph import InfraGraph


# ===========================================================================
# 1. ObservabilityHub - import_from_json
# ===========================================================================

class TestObservabilityHubImportJson:
    """Tests for ObservabilityHub.import_from_json with sample data."""

    def _make_hub(self) -> "ObservabilityHub":
        from faultray.integrations.observability import ObservabilityHub

        graph = create_demo_graph()
        return ObservabilityHub(graph)

    def test_import_valid_json(self, tmp_path):
        hub = self._make_hub()

        metrics_data = {
            "nginx": {
                "cpu_percent": 85.0,
                "memory_percent": 72.5,
                "disk_percent": 45.0,
            },
            "postgres": {
                "cpu_percent": 60.0,
                "memory_percent": 90.0,
            },
        }
        json_path = tmp_path / "metrics.json"
        json_path.write_text(json.dumps(metrics_data))

        result = hub.import_from_json(json_path)

        assert result.source == "json"
        assert result.components_updated == 2
        assert result.metrics_imported == 5
        assert result.calibration_applied is True
        assert len(result.errors) == 0

    def test_import_with_unknown_component(self, tmp_path):
        hub = self._make_hub()

        metrics_data = {
            "nonexistent-service": {
                "cpu_percent": 50.0,
            },
        }
        json_path = tmp_path / "metrics.json"
        json_path.write_text(json.dumps(metrics_data))

        result = hub.import_from_json(json_path)

        assert result.source == "json"
        assert result.components_updated == 0
        assert result.metrics_imported == 0
        assert result.calibration_applied is False
        assert len(result.errors) > 0
        assert "not found" in result.errors[0].lower()

    def test_import_invalid_json_file(self, tmp_path):
        hub = self._make_hub()

        json_path = tmp_path / "bad.json"
        json_path.write_text("not valid json {{{")

        result = hub.import_from_json(json_path)

        assert result.source == "json"
        assert result.components_updated == 0
        assert result.metrics_imported == 0
        assert result.calibration_applied is False
        assert len(result.errors) > 0

    def test_import_nonexistent_file(self, tmp_path):
        hub = self._make_hub()

        json_path = tmp_path / "does_not_exist.json"

        result = hub.import_from_json(json_path)

        assert result.source == "json"
        assert result.calibration_applied is False
        assert len(result.errors) > 0

    def test_import_non_dict_root(self, tmp_path):
        hub = self._make_hub()

        json_path = tmp_path / "array.json"
        json_path.write_text(json.dumps([1, 2, 3]))

        result = hub.import_from_json(json_path)

        assert result.source == "json"
        assert result.calibration_applied is False
        assert len(result.errors) > 0
        assert "object" in result.errors[0].lower()

    def test_import_with_invalid_metric_value(self, tmp_path):
        hub = self._make_hub()

        metrics_data = {
            "nginx": {
                "cpu_percent": "not_a_number",
                "memory_percent": 50.0,
            },
        }
        json_path = tmp_path / "metrics.json"
        json_path.write_text(json.dumps(metrics_data))

        result = hub.import_from_json(json_path)

        assert result.source == "json"
        # memory_percent should still be imported
        assert result.metrics_imported >= 1
        # cpu_percent should produce an error
        assert len(result.errors) > 0

    def test_import_with_unknown_metric_name(self, tmp_path):
        hub = self._make_hub()

        metrics_data = {
            "nginx": {
                "cpu_percent": 50.0,
                "unknown_metric": 123.0,
            },
        }
        json_path = tmp_path / "metrics.json"
        json_path.write_text(json.dumps(metrics_data))

        result = hub.import_from_json(json_path)

        # unknown_metric should be silently skipped (not in metric_fields set)
        assert result.metrics_imported == 1  # only cpu_percent
        assert result.calibration_applied is True

    def test_import_non_dict_metrics(self, tmp_path):
        hub = self._make_hub()

        metrics_data = {
            "nginx": "not a dict",
        }
        json_path = tmp_path / "metrics.json"
        json_path.write_text(json.dumps(metrics_data))

        result = hub.import_from_json(json_path)

        assert result.metrics_imported == 0
        assert len(result.errors) > 0
        assert "must be a dict" in result.errors[0]

    def test_import_network_connections(self, tmp_path):
        hub = self._make_hub()

        metrics_data = {
            "nginx": {
                "network_connections": 500,
            },
        }
        json_path = tmp_path / "metrics.json"
        json_path.write_text(json.dumps(metrics_data))

        result = hub.import_from_json(json_path)

        assert result.metrics_imported == 1
        assert result.calibration_applied is True

    def test_import_details_structure(self, tmp_path):
        hub = self._make_hub()

        metrics_data = {
            "redis": {
                "cpu_percent": 25.0,
            },
        }
        json_path = tmp_path / "metrics.json"
        json_path.write_text(json.dumps(metrics_data))

        result = hub.import_from_json(json_path)

        assert len(result.details) == 1
        detail = result.details[0]
        assert detail["component_id"] == "redis"
        assert detail["metric"] == "cpu_percent"
        assert detail["value"] == 25.0


class TestObservabilityHubFindComponent:
    """Tests for _find_component_by_host matching logic."""

    def _make_hub(self):
        from faultray.integrations.observability import ObservabilityHub

        graph = create_demo_graph()
        return ObservabilityHub(graph), graph

    def test_find_by_host(self):
        hub, graph = self._make_hub()
        comp = hub._find_component_by_host("web01")
        assert comp is not None
        assert comp.id == "nginx"

    def test_find_by_host_with_port(self):
        hub, graph = self._make_hub()
        comp = hub._find_component_by_host("db01:5432")
        assert comp is not None
        assert comp.id == "postgres"

    def test_find_by_component_id(self):
        hub, graph = self._make_hub()
        comp = hub._find_component_by_host("redis")
        assert comp is not None
        assert comp.id == "redis"

    def test_find_empty_string(self):
        hub, graph = self._make_hub()
        comp = hub._find_component_by_host("")
        assert comp is None

    def test_find_unknown_host(self):
        hub, graph = self._make_hub()
        comp = hub._find_component_by_host("unknown-host-999")
        assert comp is None


class TestObservabilityHubApplyMetric:
    """Tests for _apply_metric static method."""

    def _make_component(self):
        from faultray.model.components import Component, ComponentType, ResourceMetrics, Capacity

        return Component(
            id="test",
            name="test-comp",
            type=ComponentType.APP_SERVER,
            host="test01",
            port=8080,
            replicas=1,
            metrics=ResourceMetrics(cpu_percent=10, memory_percent=20),
            capacity=Capacity(max_connections=100),
        )

    def test_apply_cpu_percent(self):
        from faultray.integrations.observability import ObservabilityHub

        comp = self._make_component()
        ObservabilityHub._apply_metric(comp, "cpu_percent", 85.0)
        assert comp.metrics.cpu_percent == 85.0

    def test_apply_memory_percent(self):
        from faultray.integrations.observability import ObservabilityHub

        comp = self._make_component()
        ObservabilityHub._apply_metric(comp, "memory_percent", 92.5)
        assert comp.metrics.memory_percent == 92.5

    def test_apply_disk_percent(self):
        from faultray.integrations.observability import ObservabilityHub

        comp = self._make_component()
        ObservabilityHub._apply_metric(comp, "disk_percent", 77.0)
        assert comp.metrics.disk_percent == 77.0

    def test_apply_network_connections(self):
        from faultray.integrations.observability import ObservabilityHub

        comp = self._make_component()
        ObservabilityHub._apply_metric(comp, "network_connections", 500.0)
        assert comp.metrics.network_connections == 500


# ===========================================================================
# 2. log_config - setup_logging
# ===========================================================================

class TestSetupLogging:
    """Tests for faultray.log_config.setup_logging."""

    def setup_method(self):
        """Reset the faultray logger before each test."""
        logger = logging.getLogger("faultray")
        logger.handlers.clear()
        logger.setLevel(logging.WARNING)

    def test_setup_debug_level(self):
        from faultray.log_config import setup_logging

        setup_logging(level="DEBUG")

        logger = logging.getLogger("faultray")
        assert logger.level == logging.DEBUG
        assert len(logger.handlers) == 1

    def test_setup_info_level(self):
        from faultray.log_config import setup_logging

        setup_logging(level="INFO")

        logger = logging.getLogger("faultray")
        assert logger.level == logging.INFO
        assert len(logger.handlers) == 1

    def test_setup_warning_level(self):
        from faultray.log_config import setup_logging

        setup_logging(level="WARNING")

        logger = logging.getLogger("faultray")
        assert logger.level == logging.WARNING
        assert len(logger.handlers) == 1

    def test_setup_json_format(self):
        from faultray.log_config import setup_logging

        setup_logging(level="INFO", json_format=True)

        logger = logging.getLogger("faultray")
        assert len(logger.handlers) == 1
        handler = logger.handlers[0]
        # JSON format should contain "timestamp" in the format string
        fmt = handler.formatter._fmt
        assert "timestamp" in fmt
        assert "level" in fmt

    def test_no_duplicate_handlers(self):
        from faultray.log_config import setup_logging

        setup_logging(level="INFO")
        setup_logging(level="DEBUG")  # second call should be a no-op for handlers

        logger = logging.getLogger("faultray")
        # Should still have only 1 handler
        assert len(logger.handlers) == 1

    def test_handler_outputs_to_stderr(self):
        from faultray.log_config import setup_logging
        import sys

        setup_logging(level="INFO")

        logger = logging.getLogger("faultray")
        handler = logger.handlers[0]
        assert handler.stream is sys.stderr

    def test_invalid_level_falls_back(self):
        from faultray.log_config import setup_logging

        setup_logging(level="NONEXISTENT")

        logger = logging.getLogger("faultray")
        # getattr(logging, "NONEXISTENT", logging.WARNING) -> WARNING
        assert logger.level == logging.WARNING


# ===========================================================================
# 3. model/demo.py - create_demo_graph
# ===========================================================================

class TestCreateDemoGraph:
    """Tests for faultray.model.demo.create_demo_graph."""

    def test_produces_valid_graph(self):
        graph = create_demo_graph()
        assert isinstance(graph, InfraGraph)

    def test_has_expected_components(self):
        graph = create_demo_graph()
        expected_ids = {"nginx", "app-1", "app-2", "postgres", "redis", "rabbitmq"}
        assert set(graph.components.keys()) == expected_ids

    def test_component_count(self):
        graph = create_demo_graph()
        assert len(graph.components) == 6

    def test_has_dependencies(self):
        graph = create_demo_graph()
        # nginx depends on app-1 and app-2
        deps = graph.get_dependencies("nginx")
        dep_ids = {d.id for d in deps}
        assert "app-1" in dep_ids
        assert "app-2" in dep_ids

    def test_app_depends_on_db(self):
        graph = create_demo_graph()
        deps = graph.get_dependencies("app-1")
        dep_ids = {d.id for d in deps}
        assert "postgres" in dep_ids

    def test_app_has_optional_redis(self):
        graph = create_demo_graph()
        deps = graph.get_dependencies("app-1")
        dep_ids = {d.id for d in deps}
        assert "redis" in dep_ids

    def test_component_types(self):
        from faultray.model.components import ComponentType

        graph = create_demo_graph()
        assert graph.get_component("nginx").type == ComponentType.LOAD_BALANCER
        assert graph.get_component("app-1").type == ComponentType.APP_SERVER
        assert graph.get_component("postgres").type == ComponentType.DATABASE
        assert graph.get_component("redis").type == ComponentType.CACHE
        assert graph.get_component("rabbitmq").type == ComponentType.QUEUE

    def test_components_have_metrics(self):
        graph = create_demo_graph()
        for comp in graph.components.values():
            assert comp.metrics is not None
            assert comp.metrics.cpu_percent >= 0
            assert comp.metrics.memory_percent >= 0

    def test_components_have_capacity(self):
        graph = create_demo_graph()
        for comp in graph.components.values():
            assert comp.capacity is not None
            assert comp.capacity.max_connections > 0

    def test_save_and_reload(self, tmp_path):
        graph = create_demo_graph()
        model_path = tmp_path / "demo.json"
        graph.save(model_path)

        assert model_path.exists()

        loaded = InfraGraph.load(model_path)
        assert len(loaded.components) == len(graph.components)
        assert set(loaded.components.keys()) == set(graph.components.keys())

    def test_save_produces_valid_json(self, tmp_path):
        graph = create_demo_graph()
        model_path = tmp_path / "demo.json"
        graph.save(model_path)

        data = json.loads(model_path.read_text())
        assert "components" in data
        assert "dependencies" in data
        assert len(data["components"]) == 6

    def test_nginx_port(self):
        graph = create_demo_graph()
        nginx = graph.get_component("nginx")
        assert nginx.port == 443
        assert nginx.host == "web01"

    def test_postgres_capacity(self):
        graph = create_demo_graph()
        pg = graph.get_component("postgres")
        assert pg.capacity.max_connections == 100
        assert pg.capacity.max_disk_gb == 500
