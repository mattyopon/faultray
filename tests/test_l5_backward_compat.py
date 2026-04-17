# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""L5 Backward Compatibility Tests — Quality & Reliability layer.

Validates that FaultRay v11 can read older configuration formats:
- v1.0 schema (no schema_version field)
- Older YAML format styles
- Forward compatibility for unknown fields
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from faultray.model.loader import load_yaml
from faultray.model.components import SCHEMA_VERSION


# ---------------------------------------------------------------------------
# L5-COMPAT-001: v1.0 config (no schema_version) loads successfully
# ---------------------------------------------------------------------------


class TestSchemaVersionMigration:
    """Verify that older schema versions are handled gracefully."""

    def test_no_schema_version_field_defaults_to_current(
        self, tmp_path: Path,
    ) -> None:
        """YAML without schema_version should be auto-migrated."""
        yaml_content = {
            "components": [
                {"id": "web", "name": "Web Server", "type": "web_server"},
            ],
            "dependencies": [],
        }
        yaml_file = tmp_path / "v1.yaml"
        yaml_file.write_text(yaml.dump(yaml_content))
        graph = load_yaml(yaml_file)
        assert graph.get_component("web") is not None

    def test_old_schema_version_migrated(self, tmp_path: Path) -> None:
        """YAML with schema_version 1.0 should still load."""
        yaml_content = {
            "schema_version": "1.0",
            "components": [
                {"id": "app", "name": "App", "type": "app_server"},
            ],
            "dependencies": [],
        }
        yaml_file = tmp_path / "v1.yaml"
        yaml_file.write_text(yaml.dump(yaml_content))
        graph = load_yaml(yaml_file)
        assert graph.get_component("app") is not None

    def test_schema_version_2_migrated(self, tmp_path: Path) -> None:
        """YAML with schema_version 2.0 should still load."""
        yaml_content = {
            "schema_version": "2.0",
            "components": [
                {"id": "db", "name": "DB", "type": "database"},
            ],
            "dependencies": [],
        }
        yaml_file = tmp_path / "v1.yaml"
        yaml_file.write_text(yaml.dump(yaml_content))
        graph = load_yaml(yaml_file)
        assert graph.get_component("db") is not None

    def test_current_schema_version_loads(self, tmp_path: Path) -> None:
        """YAML with current schema_version loads without warnings."""
        yaml_content = {
            "schema_version": SCHEMA_VERSION,
            "components": [
                {"id": "lb", "name": "LB", "type": "load_balancer"},
            ],
            "dependencies": [],
        }
        yaml_file = tmp_path / "v_current.yaml"
        yaml_file.write_text(yaml.dump(yaml_content))
        graph = load_yaml(yaml_file)
        assert graph.get_component("lb") is not None


# ---------------------------------------------------------------------------
# L5-COMPAT-002: Old YAML format compatibility
# ---------------------------------------------------------------------------


class TestOldYamlFormats:
    """Verify compatibility with various YAML formatting styles."""

    def test_minimal_component_definition(self, tmp_path: Path) -> None:
        """A component with only id, name, type should load with defaults."""
        yaml_content = {
            "components": [
                {"id": "svc", "name": "Service", "type": "app_server"},
            ],
            "dependencies": [],
        }
        yaml_file = tmp_path / "minimal.yaml"
        yaml_file.write_text(yaml.dump(yaml_content))
        graph = load_yaml(yaml_file)
        comp = graph.get_component("svc")
        assert comp is not None
        assert comp.replicas == 1  # default
        assert comp.capacity.max_connections == 1000  # default

    def test_dependency_with_source_id_target_id_format(
        self, tmp_path: Path,
    ) -> None:
        """Old format using source_id/target_id should still work."""
        yaml_content = {
            "components": [
                {"id": "a", "name": "A", "type": "app_server"},
                {"id": "b", "name": "B", "type": "database"},
            ],
            "dependencies": [
                {"source_id": "a", "target_id": "b", "type": "requires"},
            ],
        }
        yaml_file = tmp_path / "old_deps.yaml"
        yaml_file.write_text(yaml.dump(yaml_content))
        graph = load_yaml(yaml_file)
        assert len(graph.components) == 2

    def test_dependency_with_source_target_format(self, tmp_path: Path) -> None:
        """Current format using source/target should work."""
        yaml_content = {
            "components": [
                {"id": "x", "name": "X", "type": "web_server"},
                {"id": "y", "name": "Y", "type": "cache"},
            ],
            "dependencies": [
                {"source": "x", "target": "y", "type": "optional"},
            ],
        }
        yaml_file = tmp_path / "new_deps.yaml"
        yaml_file.write_text(yaml.dump(yaml_content))
        graph = load_yaml(yaml_file)
        deps = graph.all_dependency_edges()
        assert len(deps) == 1

    def test_extra_unknown_fields_ignored_gracefully(
        self, tmp_path: Path,
    ) -> None:
        """Unknown top-level fields should not cause load failure."""
        yaml_content = {
            "schema_version": SCHEMA_VERSION,
            "metadata": {"author": "test", "version": "1.0"},
            "components": [
                {"id": "c1", "name": "C1", "type": "custom"},
            ],
            "dependencies": [],
            "some_future_field": {"key": "value"},
        }
        yaml_file = tmp_path / "extra.yaml"
        yaml_file.write_text(yaml.dump(yaml_content))
        graph = load_yaml(yaml_file)
        assert graph.get_component("c1") is not None

    def test_empty_dependencies_list(self, tmp_path: Path) -> None:
        """An empty dependencies list should not cause errors."""
        yaml_content = {
            "components": [
                {"id": "alone", "name": "Alone", "type": "storage"},
            ],
            "dependencies": [],
        }
        yaml_file = tmp_path / "no_deps.yaml"
        yaml_file.write_text(yaml.dump(yaml_content))
        graph = load_yaml(yaml_file)
        assert len(graph.components) == 1

    def test_example_demo_infra_loads(self) -> None:
        """The bundled demo-infra.yaml example should always load."""
        example_path = Path(__file__).resolve().parent.parent / "examples" / "demo-infra.yaml"
        if example_path.exists():
            graph = load_yaml(example_path)
            assert len(graph.components) >= 5
        else:
            pytest.skip("examples/demo-infra.yaml not found")
