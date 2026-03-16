"""Tests for InfraGraph cascade path and critical path operations."""

from faultray.model.components import Component, ComponentType, Dependency
from faultray.model.demo import create_demo_graph
from faultray.model.graph import InfraGraph


def test_cascade_path_direction():
    """get_cascade_path returns paths FROM failed component to dependents."""
    graph = InfraGraph()
    # Build: frontend -> backend -> database
    # Edge direction: frontend depends on backend, backend depends on database
    graph.add_component(Component(id="frontend", name="Frontend", type=ComponentType.WEB_SERVER, port=80))
    graph.add_component(Component(id="backend", name="Backend", type=ComponentType.APP_SERVER, port=8080))
    graph.add_component(Component(id="database", name="Database", type=ComponentType.DATABASE, port=5432))
    graph.add_dependency(Dependency(source_id="frontend", target_id="backend", dependency_type="requires"))
    graph.add_dependency(Dependency(source_id="backend", target_id="database", dependency_type="requires"))

    # When database fails, cascade should show: database -> backend -> frontend
    paths = graph.get_cascade_path("database")
    assert len(paths) > 0
    for path in paths:
        assert path[0] == "database", f"Path should start from failed component, got {path}"

    # Verify the full cascade chain exists
    path_strs = [" -> ".join(p) for p in paths]
    assert "database -> backend" in path_strs
    assert "database -> backend -> frontend" in path_strs


def test_critical_paths_max_guard():
    """get_critical_paths respects max_paths limit."""
    graph = create_demo_graph()
    # Demo graph has 6 components, should have a few paths
    all_paths = graph.get_critical_paths(max_paths=1000)
    limited = graph.get_critical_paths(max_paths=2)
    assert len(limited) <= 2
    assert len(all_paths) >= len(limited)
