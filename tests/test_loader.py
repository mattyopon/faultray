"""Tests for YAML model loader."""

import tempfile
from pathlib import Path

import pytest

from infrasim.model.loader import load_yaml


def _write_yaml(content: str) -> Path:
    """Write YAML content to a temp file and return the path."""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    f.write(content)
    f.close()
    return Path(f.name)


def test_load_minimal_yaml():
    """Minimal valid YAML should load successfully."""
    path = _write_yaml("""
components:
  - id: app
    name: My App
    type: app_server

dependencies: []
""")
    graph = load_yaml(path)
    assert len(graph.components) == 1
    assert "app" in graph.components


def test_load_with_dependencies():
    """Dependencies should be properly loaded."""
    path = _write_yaml("""
components:
  - id: app
    name: App
    type: app_server
  - id: db
    name: DB
    type: database

dependencies:
  - source: app
    target: db
    type: requires
""")
    graph = load_yaml(path)
    assert len(graph.components) == 2
    deps = graph.get_dependencies("app")
    assert len(deps) == 1
    assert deps[0].id == "db"


def test_missing_component_id():
    """Component without 'id' should raise ValueError."""
    path = _write_yaml("""
components:
  - name: No ID
    type: app_server
dependencies: []
""")
    with pytest.raises(ValueError, match="missing 'id'"):
        load_yaml(path)


def test_invalid_component_type():
    """Invalid component type should raise ValueError."""
    path = _write_yaml("""
components:
  - id: x
    name: X
    type: invalid_type
dependencies: []
""")
    with pytest.raises(ValueError, match="Unknown component type"):
        load_yaml(path)


def test_invalid_dependency_type():
    """Invalid dependency type should raise ValueError."""
    path = _write_yaml("""
components:
  - id: a
    name: A
    type: app_server
  - id: b
    name: B
    type: database

dependencies:
  - source: a
    target: b
    type: invalid_dep
""")
    with pytest.raises(ValueError, match="invalid type"):
        load_yaml(path)


def test_invalid_replicas():
    """Replicas < 1 should raise ValueError."""
    path = _write_yaml("""
components:
  - id: app
    name: App
    type: app_server
    replicas: 0
dependencies: []
""")
    with pytest.raises(ValueError, match="replicas"):
        load_yaml(path)


def test_circular_dependency():
    """Circular dependencies should raise ValueError."""
    path = _write_yaml("""
components:
  - id: a
    name: A
    type: app_server
  - id: b
    name: B
    type: database

dependencies:
  - source: a
    target: b
    type: requires
  - source: b
    target: a
    type: requires
""")
    with pytest.raises(ValueError, match="[Cc]ircular"):
        load_yaml(path)


def test_unknown_dependency_source():
    """Dependency with unknown source should raise ValueError."""
    path = _write_yaml("""
components:
  - id: app
    name: App
    type: app_server

dependencies:
  - source: nonexistent
    target: app
    type: requires
""")
    with pytest.raises(ValueError, match="source.*nonexistent"):
        load_yaml(path)


def test_file_not_found():
    """Loading nonexistent file should raise FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        load_yaml("/tmp/nonexistent-infrasim-test.yaml")


def test_load_string_path():
    """load_yaml should accept string paths."""
    path = _write_yaml("""
components:
  - id: app
    name: App
    type: app_server
dependencies: []
""")
    graph = load_yaml(str(path))
    assert len(graph.components) == 1
