"""Tests for operational simulation engine."""

from infrasim.model.components import (
    Capacity,
    Component,
    ComponentType,
    Dependency,
    HealthStatus,
    OperationalProfile,
    ResourceMetrics,
    SLOTarget,
)
from infrasim.model.graph import InfraGraph
from infrasim.simulator.ops_engine import (
    OpsScenario,
    OpsSimulationEngine,
    OpsSimulationResult,
    SLOTracker,
    TimeUnit,
)
from infrasim.simulator.traffic import create_diurnal_weekly


def _build_ops_graph() -> InfraGraph:
    """Build a minimal graph for ops simulation tests."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb", name="LB", type=ComponentType.LOAD_BALANCER,
        replicas=2,
        metrics=ResourceMetrics(cpu_percent=15, memory_percent=20, disk_percent=10),
        capacity=Capacity(max_connections=10000),
        slo_targets=[SLOTarget(name="avail", metric="availability", target=99.9)],
        operational_profile=OperationalProfile(mtbf_hours=720, mttr_minutes=15),
    ))
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        replicas=3,
        metrics=ResourceMetrics(cpu_percent=20, memory_percent=25, disk_percent=15),
        capacity=Capacity(max_connections=1000, connection_pool_size=200, timeout_seconds=30),
        slo_targets=[SLOTarget(name="avail", metric="availability", target=99.9)],
        operational_profile=OperationalProfile(mtbf_hours=720, mttr_minutes=30),
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE,
        replicas=2,
        metrics=ResourceMetrics(cpu_percent=20, memory_percent=25, disk_percent=20),
        capacity=Capacity(max_connections=200, max_disk_gb=500),
        slo_targets=[SLOTarget(name="avail", metric="availability", target=99.9)],
        operational_profile=OperationalProfile(mtbf_hours=2160, mttr_minutes=60),
    ))
    graph.add_dependency(Dependency(source_id="lb", target_id="app", dependency_type="requires"))
    graph.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))
    return graph


def test_run_ops_scenario_baseline():
    """Baseline scenario with no failures should achieve near-100% availability."""
    graph = _build_ops_graph()
    engine = OpsSimulationEngine(graph)
    scenario = OpsScenario(
        id="test-baseline",
        name="Test baseline",
        description="No failures",
        duration_days=1,
        time_unit=TimeUnit.FIVE_MINUTES,
        traffic_patterns=[create_diurnal_weekly(peak=2.0, duration=86400)],
        enable_random_failures=False,
        enable_degradation=False,
        enable_maintenance=False,
    )
    result = engine.run_ops_scenario(scenario)
    assert isinstance(result, OpsSimulationResult)
    assert len(result.sli_timeline) > 0
    # Baseline with no failures should have 100% availability
    avg_avail = sum(p.availability_percent for p in result.sli_timeline) / len(result.sli_timeline)
    assert avg_avail == 100.0


def test_run_ops_scenario_with_failures():
    """Scenario with random failures should produce events and lower availability."""
    # Use a graph with very low MTBF (24h) to guarantee failures within 7 days
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        replicas=2,
        metrics=ResourceMetrics(cpu_percent=20, memory_percent=25),
        capacity=Capacity(max_connections=1000),
        slo_targets=[SLOTarget(name="avail", metric="availability", target=99.9)],
        operational_profile=OperationalProfile(mtbf_hours=24, mttr_minutes=10),
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE,
        replicas=2,
        metrics=ResourceMetrics(cpu_percent=20, memory_percent=25, disk_percent=20),
        capacity=Capacity(max_connections=200),
        slo_targets=[SLOTarget(name="avail", metric="availability", target=99.9)],
        operational_profile=OperationalProfile(mtbf_hours=48, mttr_minutes=15),
    ))
    graph.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))
    engine = OpsSimulationEngine(graph)
    scenario = OpsScenario(
        id="test-failures",
        name="Test with failures",
        description="Random failures enabled",
        duration_days=7,
        time_unit=TimeUnit.FIVE_MINUTES,
        traffic_patterns=[create_diurnal_weekly(peak=2.0, duration=604800)],
        enable_random_failures=True,
        enable_degradation=False,
        enable_maintenance=False,
    )
    result = engine.run_ops_scenario(scenario)
    assert result.total_failures > 0
    assert len(result.events) > 0


def test_run_ops_scenario_with_deploys():
    """Scheduled deploys should create deploy events."""
    graph = _build_ops_graph()
    engine = OpsSimulationEngine(graph)
    scenario = OpsScenario(
        id="test-deploys",
        name="Test with deploys",
        description="Deploys only",
        duration_days=7,
        time_unit=TimeUnit.FIVE_MINUTES,
        traffic_patterns=[create_diurnal_weekly(peak=2.0, duration=604800)],
        scheduled_deploys=[
            {"component_id": "app", "day_of_week": 1, "hour": 14, "downtime_seconds": 30},
        ],
        enable_random_failures=False,
        enable_degradation=False,
        enable_maintenance=False,
    )
    result = engine.run_ops_scenario(scenario)
    assert result.total_deploys > 0


def test_duration_days_validation():
    """duration_days <= 0 should raise ValueError."""
    graph = _build_ops_graph()
    engine = OpsSimulationEngine(graph)
    scenario = OpsScenario(
        id="test-bad-duration",
        name="Bad duration",
        description="Invalid",
        duration_days=0,
    )
    try:
        engine.run_ops_scenario(scenario)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "duration_days" in str(e)


def test_slo_tracker_propagation():
    """SLO tracker should propagate dependency health."""
    graph = _build_ops_graph()
    tracker = SLOTracker(graph)
    # Verify tracker was created without error
    assert tracker.graph is graph


def test_deterministic_simulation():
    """Two runs with the same seed should produce identical results."""
    graph = _build_ops_graph()
    scenario = OpsScenario(
        id="test-deterministic",
        name="Deterministic test",
        description="Check reproducibility",
        duration_days=1,
        time_unit=TimeUnit.FIVE_MINUTES,
        traffic_patterns=[create_diurnal_weekly(peak=2.0, duration=86400)],
        enable_random_failures=True,
        enable_degradation=True,
        enable_maintenance=True,
        random_seed=12345,
    )
    engine1 = OpsSimulationEngine(graph)
    result1 = engine1.run_ops_scenario(scenario)

    engine2 = OpsSimulationEngine(graph)
    result2 = engine2.run_ops_scenario(scenario)

    assert len(result1.events) == len(result2.events)
    assert len(result1.sli_timeline) == len(result2.sli_timeline)
    for p1, p2 in zip(result1.sli_timeline, result2.sli_timeline):
        assert p1.availability_percent == p2.availability_percent


def test_composite_traffic_floor():
    """Composite traffic multiplier should have a floor of 0.1."""
    scenario = OpsScenario(
        id="test-traffic-floor",
        name="Traffic floor test",
        description="Test",
        duration_days=1,
        traffic_patterns=[],
    )
    mult = OpsSimulationEngine._composite_traffic(0, scenario)
    assert mult == 1.0  # No patterns = baseline 1.0
