"""Tests for cascade simulation engine."""

from infrasim.model.components import (
    Capacity,
    Component,
    ComponentType,
    Dependency,
    HealthStatus,
    ResourceMetrics,
)
from infrasim.model.graph import InfraGraph
from infrasim.simulator.cascade import CascadeEngine
from infrasim.simulator.scenarios import Fault, FaultType


def _build_test_graph() -> InfraGraph:
    """Build a simple test infrastructure graph."""
    graph = InfraGraph()

    graph.add_component(Component(
        id="lb", name="Load Balancer", type=ComponentType.LOAD_BALANCER,
        replicas=1, capacity=Capacity(max_connections=10000),
    ))
    graph.add_component(Component(
        id="app", name="App Server", type=ComponentType.APP_SERVER,
        replicas=1, capacity=Capacity(max_connections=500, timeout_seconds=30),
        metrics=ResourceMetrics(network_connections=450),
    ))
    graph.add_component(Component(
        id="db", name="Database", type=ComponentType.DATABASE,
        replicas=1, capacity=Capacity(max_connections=100),
        metrics=ResourceMetrics(network_connections=90, disk_percent=72),
    ))

    graph.add_dependency(Dependency(source_id="lb", target_id="app", dependency_type="requires"))
    graph.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))

    return graph


def test_component_down_cascades():
    graph = _build_test_graph()
    engine = CascadeEngine(graph)

    fault = Fault(target_component_id="db", fault_type=FaultType.COMPONENT_DOWN)
    chain = engine.simulate_fault(fault)

    assert len(chain.effects) >= 2  # db + at least app
    assert chain.effects[0].component_id == "db"
    assert chain.effects[0].health == HealthStatus.DOWN

    # App should be affected
    app_effects = [e for e in chain.effects if e.component_id == "app"]
    assert len(app_effects) > 0
    assert app_effects[0].health in (HealthStatus.DOWN, HealthStatus.DEGRADED)


def test_connection_pool_exhaustion():
    graph = _build_test_graph()
    engine = CascadeEngine(graph)

    fault = Fault(
        target_component_id="db",
        fault_type=FaultType.CONNECTION_POOL_EXHAUSTION,
    )
    chain = engine.simulate_fault(fault)

    # DB has 90/100 connections, so pool is nearly exhausted
    assert chain.effects[0].component_id == "db"
    assert chain.effects[0].health in (HealthStatus.DOWN, HealthStatus.OVERLOADED)


def test_optional_dependency_limits_cascade():
    graph = InfraGraph()

    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
    ))
    graph.add_component(Component(
        id="cache", name="Cache", type=ComponentType.CACHE,
    ))

    graph.add_dependency(Dependency(
        source_id="app", target_id="cache", dependency_type="optional",
    ))

    engine = CascadeEngine(graph)
    fault = Fault(target_component_id="cache", fault_type=FaultType.COMPONENT_DOWN)
    chain = engine.simulate_fault(fault)

    # App should only be degraded, not down
    app_effects = [e for e in chain.effects if e.component_id == "app"]
    assert len(app_effects) > 0
    assert app_effects[0].health == HealthStatus.DEGRADED


def test_traffic_spike():
    graph = _build_test_graph()
    engine = CascadeEngine(graph)

    chain = engine.simulate_traffic_spike(2.0)

    # DB has 90% connection utilization, 2x should push it over
    db_effects = [e for e in chain.effects if e.component_id == "db"]
    assert len(db_effects) > 0


def test_severity_score():
    graph = _build_test_graph()
    engine = CascadeEngine(graph)

    fault = Fault(target_component_id="db", fault_type=FaultType.COMPONENT_DOWN)
    chain = engine.simulate_fault(fault)

    assert chain.severity > 0


def test_no_cascade_for_isolated_component():
    graph = InfraGraph()
    graph.add_component(Component(
        id="standalone", name="Standalone", type=ComponentType.APP_SERVER,
    ))

    engine = CascadeEngine(graph)
    fault = Fault(target_component_id="standalone", fault_type=FaultType.COMPONENT_DOWN)
    chain = engine.simulate_fault(fault)

    # Only the direct effect, no cascade
    assert len(chain.effects) == 1


def test_graph_resilience_score():
    graph = _build_test_graph()
    score = graph.resilience_score()
    assert 0 <= score <= 100


def test_graph_save_and_load(tmp_path):
    graph = _build_test_graph()
    path = tmp_path / "test-model.json"
    graph.save(path)

    loaded = InfraGraph.load(path)
    assert len(loaded.components) == len(graph.components)
