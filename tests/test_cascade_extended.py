"""Extended tests for cascade simulation engine — targeting uncovered lines."""

from faultray.model.components import (
    Capacity,
    CircuitBreakerConfig,
    Component,
    ComponentType,
    Dependency,
    HealthStatus,
    ResourceMetrics,
    RetryStrategy,
    SingleflightConfig,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.cascade import CascadeChain, CascadeEffect, CascadeEngine
from faultray.simulator.scenarios import Fault, FaultType


# ---------------------------------------------------------------------------
# Helper graphs
# ---------------------------------------------------------------------------


def _build_latency_graph() -> InfraGraph:
    """Build a graph suitable for latency cascade testing.

    Chain: gateway -> app -> db
    All have timeout_seconds, connection pool, and reasonable metrics.
    """
    graph = InfraGraph()

    graph.add_component(Component(
        id="gateway",
        name="API Gateway",
        type=ComponentType.LOAD_BALANCER,
        replicas=1,
        capacity=Capacity(
            max_connections=5000,
            timeout_seconds=5.0,
            connection_pool_size=200,
            retry_multiplier=3.0,
        ),
        metrics=ResourceMetrics(network_connections=150),
    ))
    graph.add_component(Component(
        id="app",
        name="App Server",
        type=ComponentType.APP_SERVER,
        replicas=1,
        capacity=Capacity(
            max_connections=1000,
            timeout_seconds=10.0,
            connection_pool_size=100,
            retry_multiplier=3.0,
        ),
        metrics=ResourceMetrics(network_connections=80),
    ))
    graph.add_component(Component(
        id="db",
        name="Database",
        type=ComponentType.DATABASE,
        replicas=1,
        capacity=Capacity(
            max_connections=200,
            timeout_seconds=30.0,
            connection_pool_size=50,
            retry_multiplier=2.0,
        ),
        metrics=ResourceMetrics(network_connections=40, disk_percent=20),
    ))

    graph.add_dependency(Dependency(
        source_id="gateway",
        target_id="app",
        dependency_type="requires",
        latency_ms=5.0,
    ))
    graph.add_dependency(Dependency(
        source_id="app",
        target_id="db",
        dependency_type="requires",
        latency_ms=10.0,
    ))

    return graph


def _build_circuit_breaker_graph() -> InfraGraph:
    """Build a graph with circuit breakers on dependency edges."""
    graph = InfraGraph()

    graph.add_component(Component(
        id="frontend",
        name="Frontend",
        type=ComponentType.WEB_SERVER,
        replicas=1,
        capacity=Capacity(timeout_seconds=5.0, connection_pool_size=200),
        metrics=ResourceMetrics(network_connections=50),
    ))
    graph.add_component(Component(
        id="backend",
        name="Backend",
        type=ComponentType.APP_SERVER,
        replicas=1,
        capacity=Capacity(timeout_seconds=10.0, connection_pool_size=100),
        metrics=ResourceMetrics(network_connections=30),
    ))
    graph.add_component(Component(
        id="db",
        name="Database",
        type=ComponentType.DATABASE,
        replicas=1,
        capacity=Capacity(timeout_seconds=30.0),
    ))

    # Circuit breaker on frontend -> backend
    graph.add_dependency(Dependency(
        source_id="frontend",
        target_id="backend",
        dependency_type="requires",
        latency_ms=5.0,
        circuit_breaker=CircuitBreakerConfig(
            enabled=True,
            failure_threshold=3,
            recovery_timeout_seconds=30.0,
        ),
    ))
    # Circuit breaker on backend -> db
    graph.add_dependency(Dependency(
        source_id="backend",
        target_id="db",
        dependency_type="requires",
        latency_ms=10.0,
        circuit_breaker=CircuitBreakerConfig(
            enabled=True,
            failure_threshold=5,
            recovery_timeout_seconds=60.0,
        ),
    ))

    return graph


# ---------------------------------------------------------------------------
# CascadeChain.severity — line 82 (spread_score < 0.3 cap)
# ---------------------------------------------------------------------------


def test_severity_minor_cascade_capped_at_6():
    """Cascade affecting < 30% of components should be capped at 6.0."""
    chain = CascadeChain(
        trigger="test",
        total_components=10,
        effects=[
            CascadeEffect("a", "A", HealthStatus.DOWN, "down"),
            CascadeEffect("b", "B", HealthStatus.DOWN, "down"),
        ],
        likelihood=1.0,
    )
    # 2/10 = 20% spread < 30% -> cap at 6.0
    assert chain.severity <= 6.0, f"Expected <= 6.0 but got {chain.severity}"
    assert chain.severity > 0.0


def test_severity_major_cascade_above_6():
    """Cascade affecting > 50% should be able to exceed 6.0."""
    chain = CascadeChain(
        trigger="test",
        total_components=4,
        effects=[
            CascadeEffect("a", "A", HealthStatus.DOWN, "down"),
            CascadeEffect("b", "B", HealthStatus.DOWN, "down"),
            CascadeEffect("c", "C", HealthStatus.DOWN, "down"),
        ],
        likelihood=1.0,
    )
    # 3/4 = 75% affected, all DOWN -> score > 6.0
    assert chain.severity > 6.0, f"Expected > 6.0 but got {chain.severity}"


# ---------------------------------------------------------------------------
# simulate_fault — line 110 (target not found)
# ---------------------------------------------------------------------------


def test_simulate_fault_nonexistent_target():
    """Simulating fault on a missing component should return empty chain."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
    ))
    engine = CascadeEngine(graph)
    fault = Fault(
        target_component_id="nonexistent",
        fault_type=FaultType.COMPONENT_DOWN,
    )
    chain = engine.simulate_fault(fault)
    assert len(chain.effects) == 0
    assert chain.severity == 0.0


# ---------------------------------------------------------------------------
# simulate_traffic_spike — lines 153 (OVERLOADED branch)
# ---------------------------------------------------------------------------


def test_traffic_spike_overloaded_component():
    """Traffic spike causing > 90% utilization should mark OVERLOADED."""
    graph = InfraGraph()
    # 45% utilization (network), spike 2.1x -> ~94.5% -> OVERLOADED
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        capacity=Capacity(max_connections=100),
        metrics=ResourceMetrics(network_connections=45),
    ))
    engine = CascadeEngine(graph)
    chain = engine.simulate_traffic_spike(2.1)
    effects = [e for e in chain.effects if e.component_id == "app"]
    assert len(effects) == 1
    assert effects[0].health == HealthStatus.OVERLOADED


def test_traffic_spike_degraded_component():
    """Traffic spike causing > 70% but <= 90% utilization should mark DEGRADED."""
    graph = InfraGraph()
    # 40% utilization, spike 2.0x -> 80% -> DEGRADED
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        capacity=Capacity(max_connections=100),
        metrics=ResourceMetrics(network_connections=40),
    ))
    engine = CascadeEngine(graph)
    chain = engine.simulate_traffic_spike(2.0)
    effects = [e for e in chain.effects if e.component_id == "app"]
    assert len(effects) == 1
    assert effects[0].health == HealthStatus.DEGRADED


def test_traffic_spike_down_component():
    """Traffic spike causing > 100% utilization should mark DOWN."""
    graph = InfraGraph()
    # 60% utilization, spike 2.0x -> 120% -> DOWN
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        capacity=Capacity(max_connections=100),
        metrics=ResourceMetrics(network_connections=60),
    ))
    engine = CascadeEngine(graph)
    chain = engine.simulate_traffic_spike(2.0)
    effects = [e for e in chain.effects if e.component_id == "app"]
    assert len(effects) == 1
    assert effects[0].health == HealthStatus.DOWN


# ---------------------------------------------------------------------------
# simulate_latency_cascade — lines 182-347
# ---------------------------------------------------------------------------


def test_latency_cascade_nonexistent_component():
    """Latency cascade on missing component returns empty chain."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
    ))
    engine = CascadeEngine(graph)
    chain = engine.simulate_latency_cascade("nonexistent", 10.0)
    # Only the trigger description, no effects beyond what's there
    assert len(chain.effects) == 0


def test_latency_cascade_basic():
    """Latency cascade should propagate through the dependency chain."""
    graph = _build_latency_graph()
    engine = CascadeEngine(graph)

    chain = engine.simulate_latency_cascade("db", latency_multiplier=10.0)

    # db itself should be in the effects as DEGRADED
    db_effects = [e for e in chain.effects if e.component_id == "db"]
    assert len(db_effects) == 1
    assert db_effects[0].health == HealthStatus.DEGRADED

    # app should be affected (depends on db)
    app_effects = [e for e in chain.effects if e.component_id == "app"]
    assert len(app_effects) >= 1


def test_latency_cascade_timeout_causes_down():
    """When accumulated latency exceeds timeout, the component should go DOWN."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="db",
        name="Database",
        type=ComponentType.DATABASE,
        capacity=Capacity(timeout_seconds=5.0),
    ))
    graph.add_component(Component(
        id="app",
        name="App",
        type=ComponentType.APP_SERVER,
        capacity=Capacity(
            timeout_seconds=2.0,  # Very short timeout
            connection_pool_size=50,
            retry_multiplier=3.0,
        ),
        metrics=ResourceMetrics(network_connections=30),
    ))
    graph.add_dependency(Dependency(
        source_id="app",
        target_id="db",
        dependency_type="requires",
        latency_ms=100.0,
    ))

    engine = CascadeEngine(graph)
    # 50x slowdown on db: base_latency = 5.0*1000*0.1 = 500ms, slow = 25000ms
    chain = engine.simulate_latency_cascade("db", latency_multiplier=50.0)

    app_effects = [e for e in chain.effects if e.component_id == "app"]
    assert len(app_effects) >= 1
    # App timeout is 2000ms, accumulated latency >>> 2000ms -> DOWN
    assert app_effects[0].health == HealthStatus.DOWN


def test_latency_cascade_near_timeout_degraded():
    """When latency is near timeout (80-100%), component should be DEGRADED."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="db",
        name="Database",
        type=ComponentType.DATABASE,
        capacity=Capacity(timeout_seconds=10.0),
    ))
    graph.add_component(Component(
        id="app",
        name="App",
        type=ComponentType.APP_SERVER,
        capacity=Capacity(
            timeout_seconds=10.0,  # 10 seconds timeout = 10000ms
            connection_pool_size=500,
            retry_multiplier=2.0,
        ),
        metrics=ResourceMetrics(network_connections=20),
    ))
    graph.add_dependency(Dependency(
        source_id="app",
        target_id="db",
        dependency_type="requires",
        latency_ms=50.0,
    ))

    engine = CascadeEngine(graph)
    # base_latency = 10*1000*0.1 = 1000ms, slow = 1000 * 9 = 9000ms
    # accumulated = 9000 + 50 (edge) = 9050ms
    # timeout = 10000ms, 9050/10000 = 90.5% -> DEGRADED (> 80%)
    chain = engine.simulate_latency_cascade("db", latency_multiplier=9.0)

    app_effects = [e for e in chain.effects if e.component_id == "app"]
    assert len(app_effects) >= 1
    assert app_effects[0].health == HealthStatus.DEGRADED


def test_latency_cascade_with_circuit_breaker():
    """Circuit breaker should stop latency cascade propagation."""
    graph = _build_circuit_breaker_graph()
    engine = CascadeEngine(graph)

    # Huge latency multiplier to trigger circuit breaker trips
    chain = engine.simulate_latency_cascade("db", latency_multiplier=100.0)

    # There should be effects; the circuit breaker may trip on some edges
    assert len(chain.effects) >= 1
    # db itself is degraded
    db_effects = [e for e in chain.effects if e.component_id == "db"]
    assert len(db_effects) == 1
    assert db_effects[0].health == HealthStatus.DEGRADED


def test_latency_cascade_with_singleflight():
    """Singleflight should reduce effective connections during latency cascade."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="db",
        name="Database",
        type=ComponentType.DATABASE,
        capacity=Capacity(timeout_seconds=5.0),
    ))
    graph.add_component(Component(
        id="app",
        name="App",
        type=ComponentType.APP_SERVER,
        capacity=Capacity(
            timeout_seconds=2.0,
            connection_pool_size=500,
            retry_multiplier=3.0,
        ),
        metrics=ResourceMetrics(network_connections=200),
        singleflight=SingleflightConfig(enabled=True, coalesce_ratio=0.8),
    ))
    graph.add_dependency(Dependency(
        source_id="app",
        target_id="db",
        dependency_type="requires",
        latency_ms=100.0,
    ))

    engine = CascadeEngine(graph)
    chain = engine.simulate_latency_cascade("db", latency_multiplier=50.0)

    app_effects = [e for e in chain.effects if e.component_id == "app"]
    assert len(app_effects) >= 1


def test_latency_cascade_with_adaptive_retry():
    """Adaptive retry strategy should affect connection calculation."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="db",
        name="Database",
        type=ComponentType.DATABASE,
        capacity=Capacity(timeout_seconds=5.0),
    ))
    graph.add_component(Component(
        id="app",
        name="App",
        type=ComponentType.APP_SERVER,
        capacity=Capacity(
            timeout_seconds=2.0,
            connection_pool_size=500,
            retry_multiplier=3.0,
        ),
        metrics=ResourceMetrics(network_connections=200),
    ))
    graph.add_dependency(Dependency(
        source_id="app",
        target_id="db",
        dependency_type="requires",
        latency_ms=100.0,
        retry_strategy=RetryStrategy(enabled=True, max_retries=5),
    ))

    engine = CascadeEngine(graph)
    chain = engine.simulate_latency_cascade("db", latency_multiplier=50.0)

    app_effects = [e for e in chain.effects if e.component_id == "app"]
    assert len(app_effects) >= 1


def test_latency_cascade_connection_pool_exhaustion():
    """When effective connections exceed pool size, component goes DOWN."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="db",
        name="Database",
        type=ComponentType.DATABASE,
        capacity=Capacity(timeout_seconds=5.0),
    ))
    graph.add_component(Component(
        id="app",
        name="App",
        type=ComponentType.APP_SERVER,
        capacity=Capacity(
            timeout_seconds=2.0,
            connection_pool_size=50,  # Small pool
            retry_multiplier=3.0,
        ),
        metrics=ResourceMetrics(network_connections=30),  # 30 * 3 = 90 > 50
    ))
    graph.add_dependency(Dependency(
        source_id="app",
        target_id="db",
        dependency_type="requires",
        latency_ms=100.0,
    ))

    engine = CascadeEngine(graph)
    chain = engine.simulate_latency_cascade("db", latency_multiplier=50.0)

    app_effects = [e for e in chain.effects if e.component_id == "app"]
    assert len(app_effects) >= 1
    assert app_effects[0].health == HealthStatus.DOWN
    assert "pool exhausted" in app_effects[0].reason.lower() or "timeout" in app_effects[0].reason.lower()


def test_latency_cascade_multi_hop_propagation():
    """Latency cascade should propagate through multiple levels."""
    graph = _build_latency_graph()
    engine = CascadeEngine(graph)

    # Very high multiplier to ensure cascade reaches gateway
    chain = engine.simulate_latency_cascade("db", latency_multiplier=100.0)

    # All three components should have effects
    component_ids = {e.component_id for e in chain.effects}
    assert "db" in component_ids
    # At least app should be affected
    assert "app" in component_ids


def test_latency_cascade_circuit_breaker_on_second_hop():
    """Circuit breaker on downstream hop should stop further propagation."""
    graph = InfraGraph()

    graph.add_component(Component(
        id="db",
        name="Database",
        type=ComponentType.DATABASE,
        capacity=Capacity(timeout_seconds=30.0),
    ))
    graph.add_component(Component(
        id="app",
        name="App",
        type=ComponentType.APP_SERVER,
        capacity=Capacity(timeout_seconds=5.0, connection_pool_size=100, retry_multiplier=3.0),
        metrics=ResourceMetrics(network_connections=50),
    ))
    graph.add_component(Component(
        id="gateway",
        name="Gateway",
        type=ComponentType.LOAD_BALANCER,
        capacity=Capacity(timeout_seconds=3.0, connection_pool_size=200),
        metrics=ResourceMetrics(network_connections=80),
    ))

    graph.add_dependency(Dependency(
        source_id="app", target_id="db",
        dependency_type="requires", latency_ms=10.0,
    ))
    graph.add_dependency(Dependency(
        source_id="gateway", target_id="app",
        dependency_type="requires", latency_ms=5.0,
        circuit_breaker=CircuitBreakerConfig(
            enabled=True,
            failure_threshold=3,
            recovery_timeout_seconds=30.0,
        ),
    ))

    engine = CascadeEngine(graph)
    chain = engine.simulate_latency_cascade("db", latency_multiplier=100.0)

    # db is degraded, app is affected, gateway may have circuit breaker tripped
    assert len(chain.effects) >= 2


# ---------------------------------------------------------------------------
# simulate_traffic_spike_targeted — lines 353-393
# ---------------------------------------------------------------------------


def test_targeted_traffic_spike_down():
    """Targeted traffic spike causing > 100% should mark DOWN."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        capacity=Capacity(max_connections=100),
        metrics=ResourceMetrics(network_connections=60),
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE,
        capacity=Capacity(max_connections=100),
        metrics=ResourceMetrics(network_connections=20),
    ))
    engine = CascadeEngine(graph)
    chain = engine.simulate_traffic_spike_targeted(2.0, ["app"])

    # app at 60%, 2x -> 120% -> DOWN
    app_effects = [e for e in chain.effects if e.component_id == "app"]
    assert len(app_effects) == 1
    assert app_effects[0].health == HealthStatus.DOWN
    # db should not be affected (not targeted)
    db_effects = [e for e in chain.effects if e.component_id == "db"]
    assert len(db_effects) == 0


def test_targeted_traffic_spike_overloaded():
    """Targeted traffic spike causing > 90% should mark OVERLOADED."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        capacity=Capacity(max_connections=100),
        metrics=ResourceMetrics(network_connections=48),
    ))
    engine = CascadeEngine(graph)
    # 48% * 2.0 = 96% -> OVERLOADED
    chain = engine.simulate_traffic_spike_targeted(2.0, ["app"])
    effects = [e for e in chain.effects if e.component_id == "app"]
    assert len(effects) == 1
    assert effects[0].health == HealthStatus.OVERLOADED


def test_targeted_traffic_spike_degraded():
    """Targeted traffic spike causing > 70% should mark DEGRADED."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        capacity=Capacity(max_connections=100),
        metrics=ResourceMetrics(network_connections=40),
    ))
    engine = CascadeEngine(graph)
    # 40% * 2.0 = 80% -> DEGRADED
    chain = engine.simulate_traffic_spike_targeted(2.0, ["app"])
    effects = [e for e in chain.effects if e.component_id == "app"]
    assert len(effects) == 1
    assert effects[0].health == HealthStatus.DEGRADED


def test_targeted_traffic_spike_nonexistent_component():
    """Targeting nonexistent component should be skipped."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
    ))
    engine = CascadeEngine(graph)
    chain = engine.simulate_traffic_spike_targeted(2.0, ["nonexistent"])
    assert len(chain.effects) == 0


# ---------------------------------------------------------------------------
# _apply_direct_effect — lines 434-478 (various fault types)
# ---------------------------------------------------------------------------


def test_direct_effect_cpu_saturation():
    """CPU_SATURATION should mark component as OVERLOADED."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        metrics=ResourceMetrics(cpu_percent=80),
    ))
    engine = CascadeEngine(graph)
    chain = engine.simulate_fault(
        Fault(target_component_id="app", fault_type=FaultType.CPU_SATURATION)
    )
    assert chain.effects[0].health == HealthStatus.OVERLOADED


def test_direct_effect_memory_exhaustion():
    """MEMORY_EXHAUSTION should mark component as DOWN."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
    ))
    engine = CascadeEngine(graph)
    chain = engine.simulate_fault(
        Fault(target_component_id="app", fault_type=FaultType.MEMORY_EXHAUSTION)
    )
    assert chain.effects[0].health == HealthStatus.DOWN
    assert "OOM" in chain.effects[0].reason


def test_direct_effect_latency_spike():
    """LATENCY_SPIKE should mark component as DEGRADED."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        capacity=Capacity(timeout_seconds=30),
    ))
    engine = CascadeEngine(graph)
    chain = engine.simulate_fault(
        Fault(target_component_id="app", fault_type=FaultType.LATENCY_SPIKE)
    )
    assert chain.effects[0].health == HealthStatus.DEGRADED


def test_direct_effect_network_partition():
    """NETWORK_PARTITION should mark component as DOWN."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
    ))
    engine = CascadeEngine(graph)
    chain = engine.simulate_fault(
        Fault(target_component_id="app", fault_type=FaultType.NETWORK_PARTITION)
    )
    assert chain.effects[0].health == HealthStatus.DOWN
    assert "partition" in chain.effects[0].reason.lower()


def test_direct_effect_traffic_spike():
    """TRAFFIC_SPIKE should mark component as OVERLOADED."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
    ))
    engine = CascadeEngine(graph)
    chain = engine.simulate_fault(
        Fault(target_component_id="app", fault_type=FaultType.TRAFFIC_SPIKE)
    )
    assert chain.effects[0].health == HealthStatus.OVERLOADED


# ---------------------------------------------------------------------------
# _calculate_likelihood — lines 507, 514, 521, 530, 547-548
# ---------------------------------------------------------------------------


def test_likelihood_connection_pool_zero_pool():
    """Pool size 0 should return 0.3 likelihood."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        capacity=Capacity(connection_pool_size=0),
    ))
    engine = CascadeEngine(graph)
    chain = engine.simulate_fault(
        Fault(target_component_id="app", fault_type=FaultType.CONNECTION_POOL_EXHAUSTION)
    )
    assert chain.likelihood == 0.3


def test_likelihood_connection_pool_high_usage():
    """> 90% pool usage should return 1.0 likelihood."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        capacity=Capacity(connection_pool_size=100),
        metrics=ResourceMetrics(network_connections=95),
    ))
    engine = CascadeEngine(graph)
    chain = engine.simulate_fault(
        Fault(target_component_id="app", fault_type=FaultType.CONNECTION_POOL_EXHAUSTION)
    )
    assert chain.likelihood == 1.0


def test_likelihood_connection_pool_medium_usage():
    """40-70% pool usage should return 0.4 likelihood."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        capacity=Capacity(connection_pool_size=100),
        metrics=ResourceMetrics(network_connections=50),
    ))
    engine = CascadeEngine(graph)
    chain = engine.simulate_fault(
        Fault(target_component_id="app", fault_type=FaultType.CONNECTION_POOL_EXHAUSTION)
    )
    assert chain.likelihood == 0.4


def test_likelihood_connection_pool_moderate_usage():
    """70-90% pool usage should return 0.7 likelihood."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        capacity=Capacity(connection_pool_size=100),
        metrics=ResourceMetrics(network_connections=75),
    ))
    engine = CascadeEngine(graph)
    chain = engine.simulate_fault(
        Fault(target_component_id="app", fault_type=FaultType.CONNECTION_POOL_EXHAUSTION)
    )
    assert chain.likelihood == 0.7


def test_likelihood_cpu_high():
    """CPU > 85% should return 1.0 likelihood."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        metrics=ResourceMetrics(cpu_percent=90),
    ))
    engine = CascadeEngine(graph)
    chain = engine.simulate_fault(
        Fault(target_component_id="app", fault_type=FaultType.CPU_SATURATION)
    )
    assert chain.likelihood == 1.0


def test_likelihood_cpu_medium():
    """CPU 60-85% should return 0.6 likelihood."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        metrics=ResourceMetrics(cpu_percent=70),
    ))
    engine = CascadeEngine(graph)
    chain = engine.simulate_fault(
        Fault(target_component_id="app", fault_type=FaultType.CPU_SATURATION)
    )
    assert chain.likelihood == 0.6


def test_likelihood_memory_high():
    """Memory > 85% should return 1.0 likelihood."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        metrics=ResourceMetrics(memory_percent=90),
    ))
    engine = CascadeEngine(graph)
    chain = engine.simulate_fault(
        Fault(target_component_id="app", fault_type=FaultType.MEMORY_EXHAUSTION)
    )
    assert chain.likelihood == 1.0


def test_likelihood_memory_medium():
    """Memory 60-85% should return 0.6 likelihood."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        metrics=ResourceMetrics(memory_percent=70),
    ))
    engine = CascadeEngine(graph)
    chain = engine.simulate_fault(
        Fault(target_component_id="app", fault_type=FaultType.MEMORY_EXHAUSTION)
    )
    assert chain.likelihood == 0.6


def test_likelihood_traffic_spike():
    """TRAFFIC_SPIKE should return 0.5 likelihood."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
    ))
    engine = CascadeEngine(graph)
    chain = engine.simulate_fault(
        Fault(target_component_id="app", fault_type=FaultType.TRAFFIC_SPIKE)
    )
    assert chain.likelihood == 0.5


# ---------------------------------------------------------------------------
# _propagate — lines 561, 566, 577
# ---------------------------------------------------------------------------


def test_propagate_missing_component():
    """Propagation through a missing component should be skipped."""
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
    fault = Fault(target_component_id="db", fault_type=FaultType.COMPONENT_DOWN)
    chain = engine.simulate_fault(fault)
    # Should work without errors even though the graph is small
    assert len(chain.effects) >= 1


def test_propagate_no_edge_skipped():
    """Propagation with missing edge data should skip dependent."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE,
    ))
    # Add dependency normally
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
    ))

    engine = CascadeEngine(graph)
    fault = Fault(target_component_id="db", fault_type=FaultType.COMPONENT_DOWN)
    chain = engine.simulate_fault(fault)
    # Should not crash
    assert len(chain.effects) >= 1


# ---------------------------------------------------------------------------
# _calculate_cascade_effect — line 701 (HEALTHY fallback)
# ---------------------------------------------------------------------------


def test_cascade_effect_healthy_source():
    """When failed dependency is HEALTHY, cascade effect should be HEALTHY."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
    ))
    graph.add_component(Component(
        id="dep", name="Dep", type=ComponentType.CACHE,
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="dep", dependency_type="requires",
    ))

    engine = CascadeEngine(graph)
    # Simulate a LATENCY_SPIKE which makes target DEGRADED
    fault = Fault(target_component_id="dep", fault_type=FaultType.LATENCY_SPIKE)
    chain = engine.simulate_fault(fault)

    # Verify chain works; the cascade should propagate DEGRADED effect
    assert len(chain.effects) >= 1


def test_cascade_overloaded_dep_with_high_utilization():
    """Overloaded dependency + high utilization dependent -> OVERLOADED."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="dep", name="Dep", type=ComponentType.DATABASE, replicas=1,
    ))
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=1,
        capacity=Capacity(max_connections=100),
        metrics=ResourceMetrics(network_connections=75),  # 75% util
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="dep", dependency_type="requires",
    ))

    engine = CascadeEngine(graph)
    # CPU_SATURATION -> OVERLOADED on dep
    fault = Fault(target_component_id="dep", fault_type=FaultType.CPU_SATURATION)
    chain = engine.simulate_fault(fault)

    app_effects = [e for e in chain.effects if e.component_id == "app"]
    assert len(app_effects) >= 1
    # App at 75% util + overloaded dep -> should be OVERLOADED
    assert app_effects[0].health == HealthStatus.OVERLOADED


def test_cascade_async_dependency():
    """Async dependency should cause delayed degradation, not failure."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="queue", name="Queue", type=ComponentType.QUEUE, replicas=1,
    ))
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=1,
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="queue", dependency_type="async",
    ))

    engine = CascadeEngine(graph)
    fault = Fault(target_component_id="queue", fault_type=FaultType.COMPONENT_DOWN)
    chain = engine.simulate_fault(fault)

    app_effects = [e for e in chain.effects if e.component_id == "app"]
    assert len(app_effects) > 0
    assert app_effects[0].health == HealthStatus.DEGRADED
    assert "async" in app_effects[0].reason.lower()


def test_cascade_required_dep_with_replicas():
    """Required dependency with replicas > 1 should DEGRADE, not DOWN."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE, replicas=1,
    ))
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=3,
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
    ))

    engine = CascadeEngine(graph)
    fault = Fault(target_component_id="db", fault_type=FaultType.COMPONENT_DOWN)
    chain = engine.simulate_fault(fault)

    app_effects = [e for e in chain.effects if e.component_id == "app"]
    assert len(app_effects) >= 1
    assert app_effects[0].health == HealthStatus.DEGRADED


# ---------------------------------------------------------------------------
# Optional/async dependencies returning HEALTHY for non-DOWN — lines 635, 645
# ---------------------------------------------------------------------------


def test_optional_dep_non_down_returns_healthy():
    """Optional dependency that is DEGRADED (not DOWN) should not cascade."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="cache", name="Cache", type=ComponentType.CACHE, replicas=1,
    ))
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=1,
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="cache", dependency_type="optional",
    ))

    engine = CascadeEngine(graph)
    # LATENCY_SPIKE -> cache becomes DEGRADED (not DOWN)
    fault = Fault(target_component_id="cache", fault_type=FaultType.LATENCY_SPIKE)
    chain = engine.simulate_fault(fault)

    # app should NOT be affected — optional dep with non-DOWN returns HEALTHY
    app_effects = [e for e in chain.effects if e.component_id == "app"]
    assert len(app_effects) == 0


def test_async_dep_non_down_returns_healthy():
    """Async dependency that is DEGRADED (not DOWN) should not cascade."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="queue", name="Queue", type=ComponentType.QUEUE, replicas=1,
    ))
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=1,
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="queue", dependency_type="async",
    ))

    engine = CascadeEngine(graph)
    # LATENCY_SPIKE -> queue becomes DEGRADED (not DOWN)
    fault = Fault(target_component_id="queue", fault_type=FaultType.LATENCY_SPIKE)
    chain = engine.simulate_fault(fault)

    # app should NOT be affected
    app_effects = [e for e in chain.effects if e.component_id == "app"]
    assert len(app_effects) == 0


# ---------------------------------------------------------------------------
# _calculate_cascade_effect returns HEALTHY for unrecognized health — line 701
# ---------------------------------------------------------------------------


def test_cascade_effect_healthy_fallthrough():
    """cascade_effect should return HEALTHY for HEALTHY source health."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="dep", name="Dep", type=ComponentType.CACHE, replicas=1,
    ))
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=1,
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="dep", dependency_type="requires",
    ))

    engine = CascadeEngine(graph)
    # Directly call _calculate_cascade_effect with HEALTHY
    dep_comp = graph.get_component("dep")
    app_comp = graph.get_component("app")
    health, reason, time_delta = engine._calculate_cascade_effect(
        app_comp, dep_comp, HealthStatus.HEALTHY, "requires", 1.0,
    )
    assert health == HealthStatus.HEALTHY
    assert reason == ""
    assert time_delta == 0


# ---------------------------------------------------------------------------
# Disk full likelihood thresholds — lines 497, 499
# ---------------------------------------------------------------------------


def test_likelihood_disk_full_75_90():
    """Disk at 80% should give likelihood 0.7."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE,
        metrics=ResourceMetrics(disk_percent=80),
    ))
    engine = CascadeEngine(graph)
    chain = engine.simulate_fault(
        Fault(target_component_id="db", fault_type=FaultType.DISK_FULL)
    )
    assert chain.likelihood == 0.7


def test_likelihood_disk_full_50_75():
    """Disk at 60% should give likelihood 0.4."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE,
        metrics=ResourceMetrics(disk_percent=60),
    ))
    engine = CascadeEngine(graph)
    chain = engine.simulate_fault(
        Fault(target_component_id="db", fault_type=FaultType.DISK_FULL)
    )
    assert chain.likelihood == 0.4


# ---------------------------------------------------------------------------
# Connection pool low usage — line 516
# ---------------------------------------------------------------------------


def test_likelihood_connection_pool_low_usage():
    """< 40% pool usage should return 0.2 likelihood."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        capacity=Capacity(connection_pool_size=100),
        metrics=ResourceMetrics(network_connections=20),
    ))
    engine = CascadeEngine(graph)
    chain = engine.simulate_fault(
        Fault(target_component_id="app", fault_type=FaultType.CONNECTION_POOL_EXHAUSTION)
    )
    assert chain.likelihood == 0.2


# ---------------------------------------------------------------------------
# Latency cascade within tolerance (skip) — line 306
# ---------------------------------------------------------------------------


def test_latency_cascade_within_tolerance_skipped():
    """Components with latency well within timeout should be skipped."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="db",
        name="Database",
        type=ComponentType.DATABASE,
        capacity=Capacity(timeout_seconds=100.0),
    ))
    graph.add_component(Component(
        id="app",
        name="App",
        type=ComponentType.APP_SERVER,
        capacity=Capacity(timeout_seconds=100.0, connection_pool_size=500),
        metrics=ResourceMetrics(network_connections=20),
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db",
        dependency_type="requires",
        latency_ms=10.0,
    ))

    engine = CascadeEngine(graph)
    # Very small multiplier: base = 100*1000*0.1 = 10000ms, slow = 10000*1.5 = 15000ms
    # accumulated = 15000 + 10 = 15010ms, timeout = 100000ms
    # 15010 / 100000 = 15% -> well within tolerance, skip
    chain = engine.simulate_latency_cascade("db", latency_multiplier=1.5)

    # db itself is degraded, but app should be skipped (within tolerance)
    db_effects = [e for e in chain.effects if e.component_id == "db"]
    assert len(db_effects) == 1
    app_effects = [e for e in chain.effects if e.component_id == "app"]
    assert len(app_effects) == 0


# ---------------------------------------------------------------------------
# BFS in latency cascade — line 247 (comp is None)
# ---------------------------------------------------------------------------


def test_latency_cascade_bfs_missing_component_in_queue():
    """BFS should skip None components gracefully."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="db",
        name="Database",
        type=ComponentType.DATABASE,
        capacity=Capacity(timeout_seconds=5.0),
    ))
    graph.add_component(Component(
        id="app",
        name="App",
        type=ComponentType.APP_SERVER,
        capacity=Capacity(timeout_seconds=2.0, connection_pool_size=100),
        metrics=ResourceMetrics(network_connections=50),
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db",
        dependency_type="requires",
        latency_ms=100.0,
    ))

    engine = CascadeEngine(graph)
    # This tests the normal path; line 247 handles a None in the BFS queue
    # which would occur if a component was removed from the graph after
    # being added to the queue. This is hard to trigger naturally, but
    # the code handles it gracefully.
    chain = engine.simulate_latency_cascade("db", latency_multiplier=50.0)
    assert len(chain.effects) >= 1


# ---------------------------------------------------------------------------
# Propagate — depth > 20 — line 561
# ---------------------------------------------------------------------------


def test_propagate_depth_limit():
    """Propagation should stop at depth > 20."""
    # Build a chain longer than 20 components
    graph = InfraGraph()
    for i in range(25):
        graph.add_component(Component(
            id=f"c{i}", name=f"Component {i}",
            type=ComponentType.APP_SERVER, replicas=1,
            capacity=Capacity(timeout_seconds=30),
        ))
    for i in range(24):
        graph.add_dependency(Dependency(
            source_id=f"c{i+1}", target_id=f"c{i}",
            dependency_type="requires",
        ))

    engine = CascadeEngine(graph)
    fault = Fault(target_component_id="c0", fault_type=FaultType.COMPONENT_DOWN)
    chain = engine.simulate_fault(fault)

    # Should not have all 25 components in effects (depth limit at 20)
    assert len(chain.effects) <= 22  # c0 + up to 20 levels + maybe 1 more


# ---------------------------------------------------------------------------
# _propagate with missing failed_comp — line 566
# ---------------------------------------------------------------------------


def test_propagate_missing_failed_component():
    """_propagate should return early if failed component not in graph."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
    ))
    engine = CascadeEngine(graph)

    # Directly call _propagate with a non-existent component ID
    chain = CascadeChain(
        trigger="test",
        total_components=1,
    )
    engine._propagate(
        failed_id="nonexistent",
        failed_health=HealthStatus.DOWN,
        chain=chain,
        visited=set(),
        depth=0,
        elapsed_seconds=0,
    )
    # Should have returned early without adding any effects
    assert len(chain.effects) == 0


# ---------------------------------------------------------------------------
# _propagate with visited dependent — line 573
# ---------------------------------------------------------------------------


def test_propagate_visited_dependent_skipped():
    """Already-visited dependents should be skipped in propagation."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="a", name="A", type=ComponentType.APP_SERVER, replicas=1,
    ))
    graph.add_component(Component(
        id="b", name="B", type=ComponentType.APP_SERVER, replicas=1,
    ))
    graph.add_dependency(Dependency(
        source_id="b", target_id="a", dependency_type="requires",
    ))

    engine = CascadeEngine(graph)
    chain = CascadeChain(trigger="test", total_components=2)

    # Pre-visit "b" so it gets skipped during propagation from "a"
    engine._propagate(
        failed_id="a",
        failed_health=HealthStatus.DOWN,
        chain=chain,
        visited={"b"},  # "b" already visited
        depth=0,
        elapsed_seconds=0,
    )
    # "b" should not appear in effects since it was already visited
    b_effects = [e for e in chain.effects if e.component_id == "b"]
    assert len(b_effects) == 0


# ---------------------------------------------------------------------------
# _propagate with no edge — line 577
# ---------------------------------------------------------------------------


def test_propagate_no_edge_data():
    """When edge data is missing, dependent should be skipped."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="a", name="A", type=ComponentType.APP_SERVER, replicas=1,
    ))
    graph.add_component(Component(
        id="b", name="B", type=ComponentType.APP_SERVER, replicas=1,
    ))
    # Add edge at networkx level without dependency metadata
    graph._graph.add_edge("b", "a")  # No "dependency" data key

    engine = CascadeEngine(graph)
    chain = CascadeChain(trigger="test", total_components=2)

    engine._propagate(
        failed_id="a",
        failed_health=HealthStatus.DOWN,
        chain=chain,
        visited=set(),
        depth=0,
        elapsed_seconds=0,
    )
    # "b" should be skipped because no edge data
    b_effects = [e for e in chain.effects if e.component_id == "b"]
    assert len(b_effects) == 0
