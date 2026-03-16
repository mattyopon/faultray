"""Tests for YAML model loader."""

import tempfile
from pathlib import Path

import pytest

from faultray.model.loader import load_yaml


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
        load_yaml("/tmp/nonexistent-faultray-test.yaml")


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


# ===========================================================================
# NetworkProfile and RuntimeJitter YAML parsing (v5.14)
# ===========================================================================


def test_load_network_profile_from_yaml():
    """YAML with 'network' fields should populate NetworkProfile correctly."""
    path = _write_yaml("""
components:
  - id: api
    name: API Server
    type: app_server
    network:
      rtt_ms: 5.0
      packet_loss_rate: 0.001
      jitter_ms: 2.0
      dns_resolution_ms: 10.0
      tls_handshake_ms: 20.0

dependencies: []
""")
    graph = load_yaml(path)
    comp = graph.get_component("api")
    assert comp is not None
    assert comp.network.rtt_ms == 5.0
    assert comp.network.packet_loss_rate == 0.001
    assert comp.network.jitter_ms == 2.0
    assert comp.network.dns_resolution_ms == 10.0
    assert comp.network.tls_handshake_ms == 20.0


def test_load_runtime_jitter_from_yaml():
    """YAML with 'runtime_jitter' fields should populate RuntimeJitter correctly."""
    path = _write_yaml("""
components:
  - id: jvm-app
    name: JVM App
    type: app_server
    runtime_jitter:
      gc_pause_ms: 50.0
      gc_pause_frequency: 2.0
      scheduling_jitter_ms: 0.5

dependencies: []
""")
    graph = load_yaml(path)
    comp = graph.get_component("jvm-app")
    assert comp is not None
    assert comp.runtime_jitter.gc_pause_ms == 50.0
    assert comp.runtime_jitter.gc_pause_frequency == 2.0
    assert comp.runtime_jitter.scheduling_jitter_ms == 0.5


def test_load_network_and_runtime_jitter_combined():
    """Both network and runtime_jitter should load correctly on the same component."""
    path = _write_yaml("""
components:
  - id: full-app
    name: Full App
    type: app_server
    network:
      rtt_ms: 3.0
      packet_loss_rate: 0.0005
    runtime_jitter:
      gc_pause_ms: 30.0
      gc_pause_frequency: 1.0

dependencies: []
""")
    graph = load_yaml(path)
    comp = graph.get_component("full-app")
    assert comp is not None
    # NetworkProfile fields
    assert comp.network.rtt_ms == 3.0
    assert comp.network.packet_loss_rate == 0.0005
    # RuntimeJitter fields
    assert comp.runtime_jitter.gc_pause_ms == 30.0
    assert comp.runtime_jitter.gc_pause_frequency == 1.0


def test_network_defaults_when_omitted():
    """When 'network' is omitted from YAML, defaults should be used."""
    path = _write_yaml("""
components:
  - id: simple
    name: Simple
    type: app_server

dependencies: []
""")
    graph = load_yaml(path)
    comp = graph.get_component("simple")
    assert comp is not None
    # Should use default NetworkProfile values
    assert comp.network.rtt_ms == 1.0
    assert comp.network.packet_loss_rate == 0.0001
    assert comp.network.jitter_ms == 0.5
    # Should use default RuntimeJitter values
    assert comp.runtime_jitter.gc_pause_ms == 0.0
    assert comp.runtime_jitter.gc_pause_frequency == 0.0


def test_partial_network_profile():
    """Specifying only some network fields should use defaults for the rest."""
    path = _write_yaml("""
components:
  - id: partial
    name: Partial
    type: app_server
    network:
      packet_loss_rate: 0.01

dependencies: []
""")
    graph = load_yaml(path)
    comp = graph.get_component("partial")
    assert comp is not None
    assert comp.network.packet_loss_rate == 0.01
    # Other fields should be defaults
    assert comp.network.rtt_ms == 1.0
    assert comp.network.jitter_ms == 0.5
