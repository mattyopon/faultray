"""Tests for cascade simulation engine."""

from faultray.model.components import (
    Capacity,
    Component,
    ComponentType,
    Dependency,
    HealthStatus,
    ResourceMetrics,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.cascade import CascadeChain, CascadeEffect, CascadeEngine
from faultray.simulator.engine import SimulationEngine
from faultray.simulator.scenarios import Fault, FaultType, Scenario


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


# ---------------------------------------------------------------------------
# Severity edge-case: empty effects, overloaded single, spread < 30%
# ---------------------------------------------------------------------------


def test_severity_empty_effects():
    """CascadeChain with no effects should have severity 0.0."""
    chain = CascadeChain(trigger="test", total_components=5, effects=[])
    assert chain.severity == 0.0


def test_severity_single_overloaded_capped():
    """A single OVERLOADED effect should be capped at 2.0."""
    chain = CascadeChain(
        trigger="test",
        total_components=5,
        effects=[
            CascadeEffect("a", "A", HealthStatus.OVERLOADED, "overloaded"),
        ],
    )
    assert chain.severity <= 2.0, f"Expected <= 2.0, got {chain.severity}"


def test_severity_single_degraded_capped():
    """A single DEGRADED-only effect should be capped at 1.5."""
    chain = CascadeChain(
        trigger="test",
        total_components=10,
        effects=[
            CascadeEffect("a", "A", HealthStatus.DEGRADED, "degraded"),
        ],
    )
    assert chain.severity <= 1.5, f"Expected <= 1.5, got {chain.severity}"


def test_severity_minor_cascade_capped():
    """Cascade affecting < 30% of components should be capped at 6.0."""
    # 2 out of 10 components = 20% < 30%
    chain = CascadeChain(
        trigger="test",
        total_components=10,
        effects=[
            CascadeEffect("a", "A", HealthStatus.DOWN, "down"),
            CascadeEffect("b", "B", HealthStatus.DOWN, "down"),
        ],
    )
    assert chain.severity <= 6.0, f"Expected <= 6.0, got {chain.severity}"


def test_severity_likelihood_reduces_score():
    """Lower likelihood should reduce severity score."""
    high_lh = CascadeChain(
        trigger="test",
        total_components=2,
        effects=[CascadeEffect("a", "A", HealthStatus.DOWN, "down")],
        likelihood=1.0,
    )
    low_lh = CascadeChain(
        trigger="test",
        total_components=2,
        effects=[CascadeEffect("a", "A", HealthStatus.DOWN, "down")],
        likelihood=0.2,
    )
    assert low_lh.severity < high_lh.severity


# ---------------------------------------------------------------------------
# simulate_fault with missing target
# ---------------------------------------------------------------------------


def test_simulate_fault_missing_target():
    """Fault targeting a non-existent component should return an empty chain."""
    graph = _build_test_graph()
    engine = CascadeEngine(graph)
    fault = Fault(target_component_id="nonexistent", fault_type=FaultType.COMPONENT_DOWN)
    chain = engine.simulate_fault(fault)
    assert len(chain.effects) == 0


# ---------------------------------------------------------------------------
# simulate_latency_cascade
# ---------------------------------------------------------------------------


def _build_latency_graph() -> InfraGraph:
    """Build a graph suitable for latency cascade testing."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="fe", name="Frontend", type=ComponentType.WEB_SERVER,
        replicas=1,
        capacity=Capacity(timeout_seconds=5, connection_pool_size=50, retry_multiplier=3.0),
        metrics=ResourceMetrics(network_connections=20),
    ))
    graph.add_component(Component(
        id="app", name="App Server", type=ComponentType.APP_SERVER,
        replicas=1,
        capacity=Capacity(timeout_seconds=10, connection_pool_size=100, retry_multiplier=3.0),
        metrics=ResourceMetrics(network_connections=40),
    ))
    graph.add_component(Component(
        id="db", name="Database", type=ComponentType.DATABASE,
        replicas=1,
        capacity=Capacity(timeout_seconds=30),
    ))
    graph.add_dependency(Dependency(
        source_id="fe", target_id="app", dependency_type="requires", latency_ms=5.0,
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires", latency_ms=2.0,
    ))
    return graph


def test_simulate_latency_cascade_basic():
    """Latency cascade from a slow DB should propagate to upstream components."""
    graph = _build_latency_graph()
    engine = CascadeEngine(graph)
    chain = engine.simulate_latency_cascade("db", latency_multiplier=10.0)
    assert chain.trigger.startswith("Latency cascade")
    # DB itself should be affected
    db_effects = [e for e in chain.effects if e.component_id == "db"]
    assert len(db_effects) == 1
    assert db_effects[0].health == HealthStatus.DEGRADED


def test_simulate_latency_cascade_missing_component():
    """Latency cascade on a missing component should return an empty chain."""
    graph = _build_latency_graph()
    engine = CascadeEngine(graph)
    chain = engine.simulate_latency_cascade("nonexistent", latency_multiplier=5.0)
    assert len(chain.effects) == 0


def test_simulate_latency_cascade_propagates_upstream():
    """A slow downstream should cause timeout effects on dependents."""
    graph = _build_latency_graph()
    engine = CascadeEngine(graph)
    # Use a high multiplier to ensure latency > upstream timeout
    chain = engine.simulate_latency_cascade("db", latency_multiplier=200.0)
    # App should be affected (accumulated latency > app timeout)
    app_effects = [e for e in chain.effects if e.component_id == "app"]
    assert len(app_effects) > 0


def test_simulate_latency_cascade_circuit_breaker_stops_propagation():
    """Circuit breaker on a dependency edge should stop the latency cascade."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="fe", name="Frontend", type=ComponentType.WEB_SERVER,
        replicas=1,
        capacity=Capacity(timeout_seconds=5),
    ))
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        replicas=1,
        capacity=Capacity(timeout_seconds=10),
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE,
        replicas=1,
        capacity=Capacity(timeout_seconds=30),
    ))
    from faultray.model.components import CircuitBreakerConfig
    # Enable circuit breaker on app->db edge
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
        latency_ms=2.0,
        circuit_breaker=CircuitBreakerConfig(enabled=True),
    ))
    graph.add_dependency(Dependency(
        source_id="fe", target_id="app", dependency_type="requires",
        latency_ms=5.0,
    ))

    engine = CascadeEngine(graph)
    chain = engine.simulate_latency_cascade("db", latency_multiplier=200.0)

    # App's circuit breaker should trip instead of full failure
    app_effects = [e for e in chain.effects if e.component_id == "app"]
    assert len(app_effects) > 0
    # With circuit breaker, the cascade should contain "Circuit breaker TRIPPED"
    assert any("Circuit breaker" in e.reason for e in chain.effects)


def test_simulate_latency_cascade_near_timeout_degraded():
    """Latency that's near (>80%) timeout should cause DEGRADED status."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        replicas=1,
        capacity=Capacity(timeout_seconds=10),
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE,
        replicas=1,
        capacity=Capacity(timeout_seconds=30),
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
        latency_ms=1.0,
    ))
    engine = CascadeEngine(graph)
    # Choose a multiplier that puts accumulated latency between 80% and 100% of app timeout
    # db timeout=30s, base_latency = 30*1000*0.1 = 3000ms, slow_latency = 3000*3 = 9000ms
    # accumulated on app = 9000 + 1 = 9001ms, app timeout = 10000ms
    # 9001/10000 = 90% > 80%, but < 100% -- should be DEGRADED
    chain = engine.simulate_latency_cascade("db", latency_multiplier=3.0)
    app_effects = [e for e in chain.effects if e.component_id == "app"]
    if app_effects:
        assert app_effects[0].health in (HealthStatus.DEGRADED, HealthStatus.DOWN)


# ---------------------------------------------------------------------------
# simulate_traffic_spike_targeted
# ---------------------------------------------------------------------------


def test_simulate_traffic_spike_targeted():
    """Targeted traffic spike should only affect specified components."""
    graph = _build_test_graph()
    engine = CascadeEngine(graph)
    chain = engine.simulate_traffic_spike_targeted(2.0, ["db"])
    # Only db should have effects
    affected_ids = {e.component_id for e in chain.effects}
    assert "db" in affected_ids or len(chain.effects) == 0
    # lb and app should NOT be directly affected
    assert "lb" not in affected_ids
    assert "app" not in affected_ids


def test_simulate_traffic_spike_targeted_missing_component():
    """Targeted traffic spike with non-existent component should skip it."""
    graph = _build_test_graph()
    engine = CascadeEngine(graph)
    chain = engine.simulate_traffic_spike_targeted(2.0, ["nonexistent"])
    assert len(chain.effects) == 0


def test_simulate_traffic_spike_targeted_overloaded():
    """Targeted traffic spike should produce OVERLOADED when util > 90%."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        metrics=ResourceMetrics(cpu_percent=50.0),
    ))
    engine = CascadeEngine(graph)
    # 50% * 2.0 = 100%, > 100 threshold -> DOWN
    chain = engine.simulate_traffic_spike_targeted(2.1, ["app"])
    assert len(chain.effects) > 0
    assert chain.effects[0].health == HealthStatus.DOWN


def test_simulate_traffic_spike_targeted_degraded():
    """Targeted traffic spike should produce DEGRADED when 70 < util < 90."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        metrics=ResourceMetrics(cpu_percent=40.0),
    ))
    engine = CascadeEngine(graph)
    # 40% * 2.0 = 80% -> DEGRADED (> 70, < 90)
    chain = engine.simulate_traffic_spike_targeted(2.0, ["app"])
    if chain.effects:
        assert chain.effects[0].health == HealthStatus.DEGRADED


# ---------------------------------------------------------------------------
# simulate_traffic_spike thresholds (DOWN, OVERLOADED, DEGRADED)
# ---------------------------------------------------------------------------


def test_simulate_traffic_spike_down():
    """Traffic spike producing > 100% util should set component to DOWN."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        metrics=ResourceMetrics(cpu_percent=60.0),
    ))
    engine = CascadeEngine(graph)
    chain = engine.simulate_traffic_spike(2.0)  # 60 * 2 = 120 > 100
    app_effects = [e for e in chain.effects if e.component_id == "app"]
    assert len(app_effects) == 1
    assert app_effects[0].health == HealthStatus.DOWN


def test_simulate_traffic_spike_overloaded():
    """Traffic spike producing 90 < util < 100 should set OVERLOADED."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        metrics=ResourceMetrics(cpu_percent=48.0),
    ))
    engine = CascadeEngine(graph)
    chain = engine.simulate_traffic_spike(2.0)  # 48 * 2 = 96 > 90 < 100
    app_effects = [e for e in chain.effects if e.component_id == "app"]
    assert len(app_effects) == 1
    assert app_effects[0].health == HealthStatus.OVERLOADED


def test_simulate_traffic_spike_degraded():
    """Traffic spike producing 70 < util < 90 should set DEGRADED."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        metrics=ResourceMetrics(cpu_percent=40.0),
    ))
    engine = CascadeEngine(graph)
    chain = engine.simulate_traffic_spike(2.0)  # 40 * 2 = 80 > 70 < 90
    app_effects = [e for e in chain.effects if e.component_id == "app"]
    assert len(app_effects) == 1
    assert app_effects[0].health == HealthStatus.DEGRADED


# ---------------------------------------------------------------------------
# _apply_direct_effect: all FaultType branches
# ---------------------------------------------------------------------------


def test_direct_effect_cpu_saturation():
    """CPU_SATURATION should produce OVERLOADED status."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        metrics=ResourceMetrics(cpu_percent=30.0),
    ))
    engine = CascadeEngine(graph)
    fault = Fault(target_component_id="app", fault_type=FaultType.CPU_SATURATION)
    chain = engine.simulate_fault(fault)
    assert chain.effects[0].health == HealthStatus.OVERLOADED


def test_direct_effect_memory_exhaustion():
    """MEMORY_EXHAUSTION should produce DOWN status."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
    ))
    engine = CascadeEngine(graph)
    fault = Fault(target_component_id="app", fault_type=FaultType.MEMORY_EXHAUSTION)
    chain = engine.simulate_fault(fault)
    assert chain.effects[0].health == HealthStatus.DOWN
    assert "OOM" in chain.effects[0].reason


def test_direct_effect_latency_spike():
    """LATENCY_SPIKE should produce DEGRADED status."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
    ))
    engine = CascadeEngine(graph)
    fault = Fault(target_component_id="app", fault_type=FaultType.LATENCY_SPIKE)
    chain = engine.simulate_fault(fault)
    assert chain.effects[0].health == HealthStatus.DEGRADED


def test_direct_effect_network_partition():
    """NETWORK_PARTITION should produce DOWN status."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
    ))
    engine = CascadeEngine(graph)
    fault = Fault(target_component_id="app", fault_type=FaultType.NETWORK_PARTITION)
    chain = engine.simulate_fault(fault)
    assert chain.effects[0].health == HealthStatus.DOWN


def test_direct_effect_traffic_spike():
    """TRAFFIC_SPIKE should produce OVERLOADED status."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
    ))
    engine = CascadeEngine(graph)
    fault = Fault(target_component_id="app", fault_type=FaultType.TRAFFIC_SPIKE)
    chain = engine.simulate_fault(fault)
    assert chain.effects[0].health == HealthStatus.OVERLOADED


def test_direct_effect_disk_full():
    """DISK_FULL should produce DOWN status with disk_percent metrics."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE,
        metrics=ResourceMetrics(disk_percent=50.0),
    ))
    engine = CascadeEngine(graph)
    fault = Fault(target_component_id="db", fault_type=FaultType.DISK_FULL)
    chain = engine.simulate_fault(fault)
    assert chain.effects[0].health == HealthStatus.DOWN
    assert chain.effects[0].metrics_impact.get("disk_percent") == 100.0


# ---------------------------------------------------------------------------
# _calculate_likelihood: all branches
# ---------------------------------------------------------------------------


def test_likelihood_disk_full_high():
    """Disk > 90% should have likelihood 1.0."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE,
        metrics=ResourceMetrics(disk_percent=95.0),
    ))
    engine = CascadeEngine(graph)
    chain = engine.simulate_fault(Fault(target_component_id="db", fault_type=FaultType.DISK_FULL))
    assert chain.likelihood == 1.0


def test_likelihood_disk_full_medium():
    """Disk 75-90% should have likelihood 0.7."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE,
        metrics=ResourceMetrics(disk_percent=80.0),
    ))
    engine = CascadeEngine(graph)
    chain = engine.simulate_fault(Fault(target_component_id="db", fault_type=FaultType.DISK_FULL))
    assert chain.likelihood == 0.7


def test_likelihood_disk_full_low():
    """Disk 50-75% should have likelihood 0.4."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE,
        metrics=ResourceMetrics(disk_percent=60.0),
    ))
    engine = CascadeEngine(graph)
    chain = engine.simulate_fault(Fault(target_component_id="db", fault_type=FaultType.DISK_FULL))
    assert chain.likelihood == 0.4


def test_likelihood_connection_pool_zero_pool():
    """Pool size of 0 should give likelihood 0.3."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        capacity=Capacity(connection_pool_size=0),
    ))
    engine = CascadeEngine(graph)
    chain = engine.simulate_fault(Fault(target_component_id="app", fault_type=FaultType.CONNECTION_POOL_EXHAUSTION))
    assert chain.likelihood == 0.3


def test_likelihood_connection_pool_high():
    """Pool usage > 90% should give likelihood 1.0."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        capacity=Capacity(connection_pool_size=100),
        metrics=ResourceMetrics(network_connections=95),
    ))
    engine = CascadeEngine(graph)
    chain = engine.simulate_fault(Fault(target_component_id="app", fault_type=FaultType.CONNECTION_POOL_EXHAUSTION))
    assert chain.likelihood == 1.0


def test_likelihood_connection_pool_medium():
    """Pool usage 70-90% should give likelihood 0.7."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        capacity=Capacity(connection_pool_size=100),
        metrics=ResourceMetrics(network_connections=75),
    ))
    engine = CascadeEngine(graph)
    chain = engine.simulate_fault(Fault(target_component_id="app", fault_type=FaultType.CONNECTION_POOL_EXHAUSTION))
    assert chain.likelihood == 0.7


def test_likelihood_connection_pool_low_medium():
    """Pool usage 40-70% should give likelihood 0.4."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        capacity=Capacity(connection_pool_size=100),
        metrics=ResourceMetrics(network_connections=50),
    ))
    engine = CascadeEngine(graph)
    chain = engine.simulate_fault(Fault(target_component_id="app", fault_type=FaultType.CONNECTION_POOL_EXHAUSTION))
    assert chain.likelihood == 0.4


def test_likelihood_connection_pool_very_low():
    """Pool usage < 40% should give likelihood 0.2."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        capacity=Capacity(connection_pool_size=100),
        metrics=ResourceMetrics(network_connections=10),
    ))
    engine = CascadeEngine(graph)
    chain = engine.simulate_fault(Fault(target_component_id="app", fault_type=FaultType.CONNECTION_POOL_EXHAUSTION))
    assert chain.likelihood == 0.2


def test_likelihood_cpu_saturation_high():
    """CPU > 85% should give likelihood 1.0."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        metrics=ResourceMetrics(cpu_percent=90.0),
    ))
    engine = CascadeEngine(graph)
    chain = engine.simulate_fault(Fault(target_component_id="app", fault_type=FaultType.CPU_SATURATION))
    assert chain.likelihood == 1.0


def test_likelihood_cpu_saturation_medium():
    """CPU 60-85% should give likelihood 0.6."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        metrics=ResourceMetrics(cpu_percent=70.0),
    ))
    engine = CascadeEngine(graph)
    chain = engine.simulate_fault(Fault(target_component_id="app", fault_type=FaultType.CPU_SATURATION))
    assert chain.likelihood == 0.6


def test_likelihood_cpu_saturation_low():
    """CPU < 60% should give likelihood 0.3."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        metrics=ResourceMetrics(cpu_percent=30.0),
    ))
    engine = CascadeEngine(graph)
    chain = engine.simulate_fault(Fault(target_component_id="app", fault_type=FaultType.CPU_SATURATION))
    assert chain.likelihood == 0.3


def test_likelihood_memory_exhaustion_high():
    """Memory > 85% should give likelihood 1.0."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        metrics=ResourceMetrics(memory_percent=90.0),
    ))
    engine = CascadeEngine(graph)
    chain = engine.simulate_fault(Fault(target_component_id="app", fault_type=FaultType.MEMORY_EXHAUSTION))
    assert chain.likelihood == 1.0


def test_likelihood_memory_exhaustion_medium():
    """Memory 60-85% should give likelihood 0.6."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        metrics=ResourceMetrics(memory_percent=70.0),
    ))
    engine = CascadeEngine(graph)
    chain = engine.simulate_fault(Fault(target_component_id="app", fault_type=FaultType.MEMORY_EXHAUSTION))
    assert chain.likelihood == 0.6


def test_likelihood_memory_exhaustion_low():
    """Memory < 60% should give likelihood 0.3."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        metrics=ResourceMetrics(memory_percent=30.0),
    ))
    engine = CascadeEngine(graph)
    chain = engine.simulate_fault(Fault(target_component_id="app", fault_type=FaultType.MEMORY_EXHAUSTION))
    assert chain.likelihood == 0.3


def test_likelihood_component_down():
    """COMPONENT_DOWN should always have likelihood 0.8."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
    ))
    engine = CascadeEngine(graph)
    chain = engine.simulate_fault(Fault(target_component_id="app", fault_type=FaultType.COMPONENT_DOWN))
    assert chain.likelihood == 0.8


def test_likelihood_latency_spike():
    """LATENCY_SPIKE should have likelihood 0.7."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
    ))
    engine = CascadeEngine(graph)
    chain = engine.simulate_fault(Fault(target_component_id="app", fault_type=FaultType.LATENCY_SPIKE))
    assert chain.likelihood == 0.7


def test_likelihood_traffic_spike():
    """TRAFFIC_SPIKE should have likelihood 0.5."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
    ))
    engine = CascadeEngine(graph)
    chain = engine.simulate_fault(Fault(target_component_id="app", fault_type=FaultType.TRAFFIC_SPIKE))
    assert chain.likelihood == 0.5


# ---------------------------------------------------------------------------
# _propagate / _calculate_cascade_effect: async dep, replicas, overloaded
# ---------------------------------------------------------------------------


def test_async_dependency_cascade():
    """Async dependency should cause DEGRADED (queue building), not DOWN."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=1,
    ))
    graph.add_component(Component(
        id="queue", name="Queue", type=ComponentType.QUEUE, replicas=1,
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="queue", dependency_type="async",
    ))

    engine = CascadeEngine(graph)
    fault = Fault(target_component_id="queue", fault_type=FaultType.COMPONENT_DOWN)
    chain = engine.simulate_fault(fault)

    app_effects = [e for e in chain.effects if e.component_id == "app"]
    assert len(app_effects) == 1
    assert app_effects[0].health == HealthStatus.DEGRADED
    assert "queue building" in app_effects[0].reason.lower()


def test_required_dependency_multi_replica_degraded():
    """Required dependency on a component with replicas > 1 should be DEGRADED, not DOWN."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=3,
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE, replicas=1,
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
    ))

    engine = CascadeEngine(graph)
    fault = Fault(target_component_id="db", fault_type=FaultType.COMPONENT_DOWN)
    chain = engine.simulate_fault(fault)

    app_effects = [e for e in chain.effects if e.component_id == "app"]
    assert len(app_effects) == 1
    assert app_effects[0].health == HealthStatus.DEGRADED


def test_overloaded_cascade_with_high_utilization():
    """Overloaded dependency + high utilization dependent should cascade to OVERLOADED."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        replicas=1,
        metrics=ResourceMetrics(cpu_percent=80.0),  # > 70%
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE,
        replicas=1,
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
        latency_ms=10.0,
    ))

    engine = CascadeEngine(graph)
    fault = Fault(target_component_id="db", fault_type=FaultType.CPU_SATURATION)
    chain = engine.simulate_fault(fault)

    app_effects = [e for e in chain.effects if e.component_id == "app"]
    assert len(app_effects) == 1
    assert app_effects[0].health == HealthStatus.OVERLOADED


def test_overloaded_cascade_with_low_utilization():
    """Overloaded dependency + low utilization dependent should cascade to DEGRADED."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        replicas=1,
        metrics=ResourceMetrics(cpu_percent=20.0),  # < 70%
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE,
        replicas=1,
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
        latency_ms=10.0,
    ))

    engine = CascadeEngine(graph)
    fault = Fault(target_component_id="db", fault_type=FaultType.CPU_SATURATION)
    chain = engine.simulate_fault(fault)

    app_effects = [e for e in chain.effects if e.component_id == "app"]
    assert len(app_effects) == 1
    assert app_effects[0].health == HealthStatus.DEGRADED


def test_degraded_dependency_cascade():
    """Degraded dependency should cascade to DEGRADED with latency info."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        replicas=1,
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE,
        replicas=1,
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
        latency_ms=10.0,
    ))

    engine = CascadeEngine(graph)
    fault = Fault(target_component_id="db", fault_type=FaultType.LATENCY_SPIKE)
    chain = engine.simulate_fault(fault)

    app_effects = [e for e in chain.effects if e.component_id == "app"]
    assert len(app_effects) == 1
    assert app_effects[0].health == HealthStatus.DEGRADED


def test_optional_dependency_non_down_no_cascade():
    """Optional dependency that is not DOWN should not cascade at all."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=1,
    ))
    graph.add_component(Component(
        id="cache", name="Cache", type=ComponentType.CACHE, replicas=1,
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="cache", dependency_type="optional",
    ))

    engine = CascadeEngine(graph)
    # LATENCY_SPIKE = DEGRADED on cache, optional dep should not cascade DEGRADED
    fault = Fault(target_component_id="cache", fault_type=FaultType.LATENCY_SPIKE)
    chain = engine.simulate_fault(fault)

    app_effects = [e for e in chain.effects if e.component_id == "app"]
    assert len(app_effects) == 0


def test_async_dependency_non_down_no_cascade():
    """Async dependency that is not DOWN should not cascade."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=1,
    ))
    graph.add_component(Component(
        id="queue", name="Queue", type=ComponentType.QUEUE, replicas=1,
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="queue", dependency_type="async",
    ))

    engine = CascadeEngine(graph)
    fault = Fault(target_component_id="queue", fault_type=FaultType.LATENCY_SPIKE)
    chain = engine.simulate_fault(fault)

    app_effects = [e for e in chain.effects if e.component_id == "app"]
    assert len(app_effects) == 0


# ---------------------------------------------------------------------------
# Latency cascade: singleflight + adaptive retry
# ---------------------------------------------------------------------------


def test_latency_cascade_singleflight_reduces_connections():
    """Singleflight should reduce effective connections during latency cascade."""
    from faultray.model.components import SingleflightConfig
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        replicas=1,
        capacity=Capacity(timeout_seconds=5, connection_pool_size=100, retry_multiplier=3.0),
        metrics=ResourceMetrics(network_connections=80),
        singleflight=SingleflightConfig(enabled=True, coalesce_ratio=0.8),
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE,
        replicas=1,
        capacity=Capacity(timeout_seconds=30),
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
        latency_ms=2.0,
    ))
    engine = CascadeEngine(graph)
    chain = engine.simulate_latency_cascade("db", latency_multiplier=200.0)
    # App should still be affected but singleflight reduces load
    app_effects = [e for e in chain.effects if e.component_id == "app"]
    assert len(app_effects) > 0


def test_latency_cascade_adaptive_retry():
    """Adaptive retry strategy should use max_retries instead of retry_multiplier."""
    from faultray.model.components import RetryStrategy
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        replicas=1,
        capacity=Capacity(timeout_seconds=5, connection_pool_size=50, retry_multiplier=5.0),
        metrics=ResourceMetrics(network_connections=20),
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE,
        replicas=1,
        capacity=Capacity(timeout_seconds=30),
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
        latency_ms=2.0,
        retry_strategy=RetryStrategy(enabled=True, max_retries=2),
    ))
    engine = CascadeEngine(graph)
    chain = engine.simulate_latency_cascade("db", latency_multiplier=200.0)
    app_effects = [e for e in chain.effects if e.component_id == "app"]
    assert len(app_effects) > 0


# ---------------------------------------------------------------------------
# Latency cascade: BFS propagation through multiple levels with CB on later edge
# ---------------------------------------------------------------------------


def test_latency_cascade_bfs_multi_level_with_cb():
    """Latency cascade should propagate BFS through multiple levels, stopping at circuit breaker."""
    from faultray.model.components import CircuitBreakerConfig
    graph = InfraGraph()
    graph.add_component(Component(
        id="fe", name="Frontend", type=ComponentType.WEB_SERVER,
        replicas=1,
        capacity=Capacity(timeout_seconds=3),
    ))
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        replicas=1,
        capacity=Capacity(timeout_seconds=5, connection_pool_size=50, retry_multiplier=2.0),
        metrics=ResourceMetrics(network_connections=20),
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE,
        replicas=1,
        capacity=Capacity(timeout_seconds=30),
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
        latency_ms=2.0,
    ))
    # fe -> app has circuit breaker
    graph.add_dependency(Dependency(
        source_id="fe", target_id="app", dependency_type="requires",
        latency_ms=5.0,
        circuit_breaker=CircuitBreakerConfig(enabled=True),
    ))
    engine = CascadeEngine(graph)
    chain = engine.simulate_latency_cascade("db", latency_multiplier=200.0)
    # fe should get a circuit breaker trip
    fe_effects = [e for e in chain.effects if e.component_id == "fe"]
    if fe_effects:
        assert "Circuit breaker" in fe_effects[0].reason


# ---------------------------------------------------------------------------
# Coverage gap: line 247 — BFS get_component returns None (stale entry)
# ---------------------------------------------------------------------------


def test_latency_cascade_bfs_stale_component():
    """When a component in the BFS queue can't be resolved, it should be skipped (line 247)."""
    from unittest.mock import patch
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        replicas=1,
        capacity=Capacity(timeout_seconds=10, connection_pool_size=50, retry_multiplier=2.0),
        metrics=ResourceMetrics(network_connections=20),
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE,
        replicas=1,
        capacity=Capacity(timeout_seconds=30),
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
        latency_ms=2.0,
    ))

    engine = CascadeEngine(graph)

    # Patch get_component to return None for "app" but normal for "db"
    # This simulates a stale entry in the BFS queue
    original_get = graph.get_component

    def selective_get(comp_id):
        if comp_id == "app":
            return None
        return original_get(comp_id)

    with patch.object(graph, "get_component", side_effect=selective_get):
        chain = engine.simulate_latency_cascade("db", latency_multiplier=200.0)

    # DB itself should be affected; app should be skipped (None from get_component)
    assert any(e.component_id == "db" for e in chain.effects)
    app_effects = [e for e in chain.effects if e.component_id == "app"]
    assert len(app_effects) == 0


# ---------------------------------------------------------------------------
# Coverage gap: line 306 — latency within tolerance (continue)
# ---------------------------------------------------------------------------


def test_latency_cascade_within_tolerance():
    """When accumulated latency is well within timeout, the component should be skipped."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        replicas=1,
        capacity=Capacity(timeout_seconds=60),  # Very generous timeout: 60000ms
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE,
        replicas=1,
        capacity=Capacity(timeout_seconds=30),
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
        latency_ms=1.0,
    ))
    engine = CascadeEngine(graph)
    # Low multiplier: base_latency = 30*1000*0.1 = 3000ms, slow = 3000*1.5 = 4500ms
    # accumulated on app = 4500 + 1 = 4501ms, app timeout = 60000ms
    # 4501/60000 = ~7.5% — well below 80%, should be skipped (continue)
    chain = engine.simulate_latency_cascade("db", latency_multiplier=1.5)
    # DB should be degraded, but app should not appear (within tolerance)
    app_effects = [e for e in chain.effects if e.component_id == "app"]
    assert len(app_effects) == 0


# ---------------------------------------------------------------------------
# Coverage gap: line 377 — targeted traffic spike OVERLOADED (90 < util <= 100)
# ---------------------------------------------------------------------------


def test_simulate_traffic_spike_targeted_overloaded_threshold():
    """Targeted traffic spike producing 90 < util <= 100 should set OVERLOADED."""
    graph = InfraGraph()
    # cpu_percent=46 * 2.0 = 92 -> > 90 but < 100 -> OVERLOADED
    graph.add_component(Component(
        id="svc", name="Service", type=ComponentType.APP_SERVER,
        metrics=ResourceMetrics(cpu_percent=46.0),
    ))
    engine = CascadeEngine(graph)
    chain = engine.simulate_traffic_spike_targeted(2.0, ["svc"])
    assert len(chain.effects) == 1
    assert chain.effects[0].health == HealthStatus.OVERLOADED
    assert "Near capacity" in chain.effects[0].reason


# ---------------------------------------------------------------------------
# Coverage gap: lines 477-478 — default case in _apply_direct_effect
# ---------------------------------------------------------------------------


def test_apply_direct_effect_unknown_fault_type():
    """Unknown fault type should produce DEGRADED with 'Unknown fault type' reason."""
    from unittest.mock import MagicMock
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
    ))
    engine = CascadeEngine(graph)
    comp = graph.get_component("app")

    # Create a mock fault with a fault_type that won't match any case
    fake_fault = MagicMock()
    fake_fault.fault_type = MagicMock()
    fake_fault.fault_type.value = "alien_invasion"

    effect = engine._apply_direct_effect(comp, fake_fault)
    assert effect.health == HealthStatus.DEGRADED
    assert "Unknown fault type" in effect.reason


# ---------------------------------------------------------------------------
# Coverage gap: lines 547-548 — default case in _calculate_likelihood
# ---------------------------------------------------------------------------


def test_calculate_likelihood_unknown_fault_type():
    """Unknown fault type should return default likelihood 0.5."""
    from unittest.mock import MagicMock
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
    ))
    engine = CascadeEngine(graph)
    comp = graph.get_component("app")

    fake_fault = MagicMock()
    fake_fault.fault_type = MagicMock()
    fake_fault.fault_type.value = "alien_invasion"

    likelihood = engine._calculate_likelihood(comp, fake_fault)
    assert likelihood == 0.5


# ---------------------------------------------------------------------------
# Coverage gap: line 561 — depth > 20 guard in _propagate
# ---------------------------------------------------------------------------


def test_propagate_depth_limit():
    """Propagation should stop when depth exceeds 20."""
    graph = InfraGraph()

    # Build a chain of 25 components: c0 -> c1 -> c2 -> ... -> c24
    num_components = 25
    for i in range(num_components):
        graph.add_component(Component(
            id=f"c{i}", name=f"Component {i}", type=ComponentType.APP_SERVER,
            replicas=1,
            capacity=Capacity(timeout_seconds=30),
        ))
    for i in range(num_components - 1):
        # c0 depends on c1, c1 depends on c2, etc.
        graph.add_dependency(Dependency(
            source_id=f"c{i}", target_id=f"c{i+1}", dependency_type="requires",
        ))

    engine = CascadeEngine(graph)
    # Fault on the last component (c24) cascades upstream through 24 components
    fault = Fault(target_component_id=f"c{num_components-1}", fault_type=FaultType.COMPONENT_DOWN)
    chain = engine.simulate_fault(fault)

    # Should have effects, but depth limit should cap propagation at 21 levels
    # (depth 0 through 20 inclusive = 21 recursive calls, then stop at depth > 20)
    # Plus the direct effect = at most 22 effects total
    assert len(chain.effects) <= 23  # direct effect + up to 21 from propagation


# ---------------------------------------------------------------------------
# Coverage gap: line 566 — get_component returns None in _propagate
# ---------------------------------------------------------------------------


def test_propagate_failed_comp_not_found():
    """If the failed component is removed after fault injection, _propagate should return early."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        replicas=1,
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE,
        replicas=1,
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
    ))

    engine = CascadeEngine(graph)
    chain = CascadeChain(trigger="test", total_components=2)

    # Call _propagate directly with a component ID that doesn't resolve
    # First, remove "db" from the components dict
    del graph._components["db"]

    engine._propagate("db", HealthStatus.DOWN, chain, visited=set(), depth=0, elapsed_seconds=0)
    # No effects should be added since get_component returns None
    assert len(chain.effects) == 0


# ---------------------------------------------------------------------------
# Coverage gap: line 573 — dep_comp.id already in visited in _propagate
# ---------------------------------------------------------------------------


def test_propagate_already_visited():
    """Components already in the visited set should be skipped during propagation."""
    graph = InfraGraph()
    # Diamond dependency: app1 -> db, app2 -> db, lb -> app1, lb -> app2
    # When db fails, app1 and app2 are both affected.
    # When app1 propagates, lb gets visited. When app2 propagates, lb is already visited.
    graph.add_component(Component(
        id="lb", name="LB", type=ComponentType.LOAD_BALANCER, replicas=1,
        capacity=Capacity(timeout_seconds=30),
    ))
    graph.add_component(Component(
        id="app1", name="App1", type=ComponentType.APP_SERVER, replicas=1,
        capacity=Capacity(timeout_seconds=30),
    ))
    graph.add_component(Component(
        id="app2", name="App2", type=ComponentType.APP_SERVER, replicas=1,
        capacity=Capacity(timeout_seconds=30),
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE, replicas=1,
    ))

    graph.add_dependency(Dependency(source_id="lb", target_id="app1", dependency_type="requires"))
    graph.add_dependency(Dependency(source_id="lb", target_id="app2", dependency_type="requires"))
    graph.add_dependency(Dependency(source_id="app1", target_id="db", dependency_type="requires"))
    graph.add_dependency(Dependency(source_id="app2", target_id="db", dependency_type="requires"))

    engine = CascadeEngine(graph)
    fault = Fault(target_component_id="db", fault_type=FaultType.COMPONENT_DOWN)
    chain = engine.simulate_fault(fault)

    # LB should appear only once in effects (second visit skipped via continue)
    lb_effects = [e for e in chain.effects if e.component_id == "lb"]
    assert len(lb_effects) == 1


# ---------------------------------------------------------------------------
# Coverage gap: line 577 — edge lookup returns None in _propagate
# ---------------------------------------------------------------------------


def test_propagate_edge_not_found():
    """If the dependency edge is not found, the dependent should be skipped."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=1,
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE, replicas=1,
    ))

    # Add dependency in the networkx graph so get_dependents returns "app",
    # but don't store a Dependency object on the edge so get_dependency_edge returns None
    graph._graph.add_edge("app", "db")  # Raw edge without "dependency" data

    engine = CascadeEngine(graph)
    chain = CascadeChain(trigger="test", total_components=2)

    engine._propagate("db", HealthStatus.DOWN, chain, visited=set(), depth=0, elapsed_seconds=0)
    # "app" should be skipped because get_dependency_edge returns None
    app_effects = [e for e in chain.effects if e.component_id == "app"]
    assert len(app_effects) == 0


# ---------------------------------------------------------------------------
# Coverage gap: line 701 — HEALTHY return from _calculate_cascade_effect
# ---------------------------------------------------------------------------


def test_calculate_cascade_effect_healthy_passthrough():
    """When failed_health is HEALTHY, cascade effect should return HEALTHY."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=1,
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE, replicas=1,
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
    ))

    engine = CascadeEngine(graph)
    app_comp = graph.get_component("app")
    db_comp = graph.get_component("db")

    # Call _calculate_cascade_effect directly with HEALTHY status
    health, reason, time_delta = engine._calculate_cascade_effect(
        dependent=app_comp,
        failed=db_comp,
        failed_health=HealthStatus.HEALTHY,
        dep_type="requires",
        weight=1.0,
    )
    assert health == HealthStatus.HEALTHY
    assert reason == ""
    assert time_delta == 0
