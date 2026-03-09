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
from infrasim.simulator.cascade import CascadeChain, CascadeEffect, CascadeEngine
from infrasim.simulator.engine import SimulationEngine
from infrasim.simulator.scenarios import Fault, FaultType, Scenario


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

    # CONNECTION_POOL_EXHAUSTION is a "what if" scenario - always DOWN
    assert chain.effects[0].component_id == "db"
    assert chain.effects[0].health == HealthStatus.DOWN


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


# --- New severity scoring tests ---


def test_non_cascading_failure_has_low_severity():
    """A failure that only affects the target component should have low severity."""
    graph = InfraGraph()
    # Add 5 components but only one is isolated
    graph.add_component(Component(id="lb", name="LB", type=ComponentType.LOAD_BALANCER))
    graph.add_component(Component(id="app1", name="App1", type=ComponentType.APP_SERVER))
    graph.add_component(Component(id="app2", name="App2", type=ComponentType.APP_SERVER))
    graph.add_component(Component(id="db", name="DB", type=ComponentType.DATABASE))
    graph.add_component(Component(
        id="standalone", name="Standalone", type=ComponentType.CACHE,
    ))

    # Dependencies: lb -> app1 -> db, lb -> app2 -> db
    # standalone has NO dependents
    graph.add_dependency(Dependency(source_id="lb", target_id="app1", dependency_type="requires"))
    graph.add_dependency(Dependency(source_id="lb", target_id="app2", dependency_type="requires"))
    graph.add_dependency(Dependency(source_id="app1", target_id="db", dependency_type="requires"))
    graph.add_dependency(Dependency(source_id="app2", target_id="db", dependency_type="requires"))

    engine = CascadeEngine(graph)
    fault = Fault(target_component_id="standalone", fault_type=FaultType.COMPONENT_DOWN)
    chain = engine.simulate_fault(fault)

    # Only 1 effect (standalone itself), no cascade
    assert len(chain.effects) == 1
    # Non-cascading failure should be low severity (< 4.0)
    assert chain.severity < 4.0, f"Expected < 4.0 but got {chain.severity}"


def test_full_cascade_has_high_severity():
    """A failure cascading through the entire system should have high severity."""
    graph = InfraGraph()
    # 3 components in a chain: lb -> app -> db
    graph.add_component(Component(
        id="lb", name="LB", type=ComponentType.LOAD_BALANCER, replicas=1,
    ))
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=1,
        capacity=Capacity(timeout_seconds=30),
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE, replicas=1,
        capacity=Capacity(timeout_seconds=30),
    ))

    graph.add_dependency(Dependency(source_id="lb", target_id="app", dependency_type="requires"))
    graph.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))

    engine = CascadeEngine(graph)
    # DB goes down -> cascades to app -> cascades to lb (all 3 affected)
    fault = Fault(target_component_id="db", fault_type=FaultType.COMPONENT_DOWN)
    chain = engine.simulate_fault(fault)

    # Should affect all 3 components (100% cascade)
    assert len(chain.effects) == 3
    # Full cascade = high severity (> 7.0)
    assert chain.severity > 7.0, f"Expected > 7.0 but got {chain.severity}"


def test_optional_dependency_cascade_lower_than_required():
    """Optional dependency cascade should produce lower severity than required."""
    # Build two identical graphs, one with optional dep, one with required
    def build_graph(dep_type: str) -> InfraGraph:
        g = InfraGraph()
        g.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER, replicas=1,
            capacity=Capacity(timeout_seconds=30),
        ))
        g.add_component(Component(
            id="dep", name="Dependency", type=ComponentType.CACHE, replicas=1,
        ))
        g.add_dependency(Dependency(
            source_id="app", target_id="dep", dependency_type=dep_type,
        ))
        return g

    optional_graph = build_graph("optional")
    required_graph = build_graph("requires")

    fault = Fault(target_component_id="dep", fault_type=FaultType.COMPONENT_DOWN)

    optional_chain = CascadeEngine(optional_graph).simulate_fault(fault)
    required_chain = CascadeEngine(required_graph).simulate_fault(fault)

    # Optional dependency cascade should be lower severity
    assert optional_chain.severity < required_chain.severity, (
        f"Optional ({optional_chain.severity}) should be < Required ({required_chain.severity})"
    )


def test_compound_failure_scenario():
    """Two simultaneous faults should produce higher risk than either alone."""
    graph = _build_test_graph()
    engine = SimulationEngine(graph)

    # Single fault: DB down
    single_scenario = Scenario(
        id="single-db",
        name="DB down",
        description="DB goes down",
        faults=[Fault(target_component_id="db", fault_type=FaultType.COMPONENT_DOWN)],
    )

    # Compound fault: DB down + App down
    compound_scenario = Scenario(
        id="compound-db-app",
        name="DB + App down",
        description="DB and App both go down",
        faults=[
            Fault(target_component_id="db", fault_type=FaultType.COMPONENT_DOWN),
            Fault(target_component_id="app", fault_type=FaultType.COMPONENT_DOWN),
        ],
    )

    single_result = engine.run_scenario(single_scenario)
    compound_result = engine.run_scenario(compound_scenario)

    assert compound_result.risk_score >= single_result.risk_score, (
        f"Compound ({compound_result.risk_score}) should be >= "
        f"Single ({single_result.risk_score})"
    )


def test_disk_full_always_down():
    """DISK_FULL scenario should always set target to DOWN (it's a 'what if')."""
    graph = InfraGraph()
    # Component with disk at only 20% - far from full
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE,
        metrics=ResourceMetrics(disk_percent=20.0),
    ))

    engine = CascadeEngine(graph)
    fault = Fault(target_component_id="db", fault_type=FaultType.DISK_FULL)
    chain = engine.simulate_fault(fault)

    assert chain.effects[0].health == HealthStatus.DOWN
    # But likelihood should be low since disk is only at 20%
    assert chain.likelihood < 0.5, f"Expected likelihood < 0.5 but got {chain.likelihood}"


def test_disk_full_low_usage_has_low_risk_score():
    """Disk full scenario on a component with low disk usage should have reduced risk score."""
    graph = InfraGraph()
    # Multiple components to properly test ratio scaling
    graph.add_component(Component(
        id="lb", name="LB", type=ComponentType.LOAD_BALANCER,
    ))
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
    ))
    graph.add_component(Component(
        id="db-low", name="DB Low Disk", type=ComponentType.DATABASE,
        metrics=ResourceMetrics(disk_percent=20.0),
    ))
    graph.add_component(Component(
        id="db-high", name="DB High Disk", type=ComponentType.DATABASE,
        metrics=ResourceMetrics(disk_percent=95.0),
    ))

    engine = CascadeEngine(graph)

    low_chain = engine.simulate_fault(
        Fault(target_component_id="db-low", fault_type=FaultType.DISK_FULL)
    )
    high_chain = engine.simulate_fault(
        Fault(target_component_id="db-high", fault_type=FaultType.DISK_FULL)
    )

    # Both are DOWN, but the low-disk one should have lower severity due to likelihood
    assert low_chain.severity < high_chain.severity, (
        f"Low disk ({low_chain.severity}) should be < High disk ({high_chain.severity})"
    )


def test_severity_with_total_components_context():
    """Severity should account for total components in the system."""
    # Small system: 2 components, 1 fails = 50% affected
    small_chain = CascadeChain(
        trigger="test",
        total_components=2,
        effects=[
            CascadeEffect("a", "A", HealthStatus.DOWN, "down"),
        ],
    )

    # Large system: 20 components, 1 fails = 5% affected
    large_chain = CascadeChain(
        trigger="test",
        total_components=20,
        effects=[
            CascadeEffect("a", "A", HealthStatus.DOWN, "down"),
        ],
    )

    # Same effect but in a larger system should be lower severity
    assert large_chain.severity <= small_chain.severity, (
        f"Large system ({large_chain.severity}) should be <= "
        f"Small system ({small_chain.severity})"
    )


def test_degraded_only_capped():
    """Effects that are only DEGRADED (no DOWN, no OVERLOADED) should be capped at 4.0."""
    chain = CascadeChain(
        trigger="test",
        total_components=3,
        effects=[
            CascadeEffect("a", "A", HealthStatus.DEGRADED, "degraded"),
            CascadeEffect("b", "B", HealthStatus.DEGRADED, "degraded"),
            CascadeEffect("c", "C", HealthStatus.DEGRADED, "degraded"),
        ],
    )
    assert chain.severity <= 4.0, f"Degraded-only severity should be <= 4.0 but got {chain.severity}"
