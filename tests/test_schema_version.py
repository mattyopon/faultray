"""Tests for schema versioning in model loading and saving."""

import json
import logging
import tempfile
from pathlib import Path

import pytest

from faultray.model.components import SCHEMA_VERSION, Component, ComponentType, Dependency
from faultray.model.graph import InfraGraph
from faultray.model.loader import load_yaml


def _write_yaml(content: str) -> Path:
    """Write YAML content to a temp file and return the path."""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    f.write(content)
    f.close()
    return Path(f.name)


def test_schema_version_constant():
    """SCHEMA_VERSION should be '3.0'."""
    assert SCHEMA_VERSION == "3.0"


def test_to_dict_includes_schema_version():
    """InfraGraph.to_dict() should include schema_version."""
    graph = InfraGraph()
    graph.add_component(
        Component(id="app", name="App", type=ComponentType.APP_SERVER)
    )
    data = graph.to_dict()
    assert "schema_version" in data
    assert data["schema_version"] == SCHEMA_VERSION


def test_save_and_load_preserves_schema_version():
    """Schema version should be included in saved JSON and handled on load."""
    with tempfile.TemporaryDirectory() as tmp:
        save_path = Path(tmp) / "model.json"
        graph = InfraGraph()
        graph.add_component(
            Component(id="db", name="DB", type=ComponentType.DATABASE)
        )
        graph.save(save_path)

        # Verify the JSON contains schema_version
        data = json.loads(save_path.read_text())
        assert data["schema_version"] == SCHEMA_VERSION

        # Load should work with schema_version present
        loaded = InfraGraph.load(save_path)
        assert len(loaded.components) == 1
        assert "db" in loaded.components


def test_load_json_without_schema_version(caplog):
    """Loading JSON without schema_version should log a warning."""
    with tempfile.TemporaryDirectory() as tmp:
        save_path = Path(tmp) / "old_model.json"
        data = {
            "components": [
                {"id": "web", "name": "Web", "type": "web_server"}
            ],
            "dependencies": [],
        }
        save_path.write_text(json.dumps(data))

        with caplog.at_level(logging.WARNING, logger="faultray.model.graph"):
            loaded = InfraGraph.load(save_path)

        assert len(loaded.components) == 1
        assert any("v1.0" in msg for msg in caplog.messages)


def test_load_json_with_old_schema_version(caplog):
    """Loading JSON with old schema_version should log a migration warning."""
    with tempfile.TemporaryDirectory() as tmp:
        save_path = Path(tmp) / "old_model.json"
        data = {
            "schema_version": "2.0",
            "components": [
                {"id": "app", "name": "App", "type": "app_server"}
            ],
            "dependencies": [],
        }
        save_path.write_text(json.dumps(data))

        with caplog.at_level(logging.WARNING, logger="faultray.model.graph"):
            loaded = InfraGraph.load(save_path)

        assert len(loaded.components) == 1
        assert any("v2.0" in msg for msg in caplog.messages)
        assert any("v3.0" in msg for msg in caplog.messages)


def test_yaml_without_schema_version_logs_warning(caplog):
    """Loading YAML without schema_version should log a migration warning."""
    path = _write_yaml("""
components:
  - id: app
    name: App
    type: app_server
dependencies: []
""")
    with caplog.at_level(logging.WARNING, logger="faultray.model.loader"):
        graph = load_yaml(path)

    assert len(graph.components) == 1
    assert any("v1.0" in msg for msg in caplog.messages)


def test_yaml_with_current_schema_version_no_warning(caplog):
    """Loading YAML with current schema_version should not log a warning."""
    path = _write_yaml(f"""
schema_version: "{SCHEMA_VERSION}"
components:
  - id: app
    name: App
    type: app_server
dependencies: []
""")
    with caplog.at_level(logging.WARNING, logger="faultray.model.loader"):
        graph = load_yaml(path)

    assert len(graph.components) == 1
    # No migration warning should be logged
    migration_messages = [
        msg for msg in caplog.messages if "migrating" in msg.lower()
    ]
    assert len(migration_messages) == 0


def test_yaml_with_old_schema_version_logs_migration(caplog):
    """Loading YAML with old schema_version should log migration."""
    path = _write_yaml("""
schema_version: "1.5"
components:
  - id: app
    name: App
    type: app_server
dependencies: []
""")
    with caplog.at_level(logging.WARNING, logger="faultray.model.loader"):
        graph = load_yaml(path)

    assert len(graph.components) == 1
    assert any("v1.5" in msg for msg in caplog.messages)
    assert any("v3.0" in msg for msg in caplog.messages)
