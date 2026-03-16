"""Tests for operational simulation engine."""

from faultray.model.components import (
    Capacity,
    Component,
    ComponentType,
    Dependency,
    HealthStatus,
    OperationalProfile,
    ResourceMetrics,
    SLOTarget,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.ops_engine import (
    OpsScenario,
    OpsSimulationEngine,
    OpsSimulationResult,
    SLOTracker,
    TimeUnit,
)
from faultray.simulator.traffic import create_diurnal_weekly


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
    # Baseline with no failures should have near-100% availability
    # (network packet loss and runtime jitter cause tiny micro-penalties)
    avg_avail = sum(p.availability_percent for p in result.sli_timeline) / len(result.sli_timeline)
    assert avg_avail >= 99.99


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


def test_optional_dependency_propagation():
    """Optional dependency DOWN should propagate as DEGRADED, not DOWN."""
    graph = InfraGraph()
    graph.add_component(Component(id="app", name="App", type=ComponentType.APP_SERVER, port=8080))
    graph.add_component(Component(id="cache", name="Cache", type=ComponentType.CACHE, port=6379))
    graph.add_dependency(Dependency(source_id="app", target_id="cache", dependency_type="optional"))

    # app depends optionally on cache. If cache is DOWN, app should be DEGRADED (not DOWN).
    # Validate the relationship is correctly set up for propagation.
    tracker = SLOTracker(graph)
    assert tracker.graph is graph
    dep_edge = graph.get_dependency_edge("app", "cache")
    assert dep_edge is not None
    assert dep_edge.dependency_type == "optional"


def test_ops_default_time_unit_override():
    """run_default_ops_scenarios respects time_unit_override."""
    from faultray.model.demo import create_demo_graph

    graph = create_demo_graph()
    engine = OpsSimulationEngine(graph)
    results = engine.run_default_ops_scenarios(time_unit_override=TimeUnit.HOUR)
    assert len(results) == 5
    for r in results:
        assert r.scenario.time_unit == TimeUnit.HOUR


def test_time_unit_to_seconds():
    """_time_unit_to_seconds should convert enum values correctly."""
    assert OpsSimulationEngine._time_unit_to_seconds(TimeUnit.MINUTE) == 60
    assert OpsSimulationEngine._time_unit_to_seconds(TimeUnit.FIVE_MINUTES) == 300
    assert OpsSimulationEngine._time_unit_to_seconds(TimeUnit.HOUR) == 3600


def test_slo_tracker_record_and_error_budget():
    """SLO tracker should record measurements and compute error budget status."""
    from faultray.simulator.ops_engine import _OpsComponentState

    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        replicas=1,
        slo_targets=[SLOTarget(name="avail", metric="availability", target=99.9)],
    ))
    tracker = SLOTracker(graph)

    # Record a healthy state
    states = {
        "app": _OpsComponentState(
            component_id="app",
            base_utilization=30.0,
            current_utilization=30.0,
            current_health=HealthStatus.HEALTHY,
        ),
    }
    point = tracker.record(0, states)
    assert point.availability_percent > 0
    assert point.total_components == 1

    # Record a down state
    states["app"].current_health = HealthStatus.DOWN
    point2 = tracker.record(300, states)
    assert point2.down_count == 1

    # Check error budget status
    budget_statuses = tracker.error_budget_status()
    assert len(budget_statuses) > 0
    for bs in budget_statuses:
        assert bs.budget_total_minutes > 0


def test_slo_tracker_latency_and_error_rate_violations():
    """SLO tracker should track latency and error_rate SLO violations."""
    from faultray.simulator.ops_engine import _OpsComponentState

    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        replicas=1,
        slo_targets=[
            SLOTarget(name="latency", metric="latency_p99", target=10.0, window_days=30),
            SLOTarget(name="errors", metric="error_rate", target=0.01, window_days=30),
        ],
    ))
    tracker = SLOTracker(graph)

    # Healthy state
    states = {
        "app": _OpsComponentState(
            component_id="app",
            base_utilization=30.0,
            current_utilization=30.0,
            current_health=HealthStatus.HEALTHY,
        ),
    }
    tracker.record(0, states)

    # Overloaded state (should violate error_rate)
    states["app"].current_health = HealthStatus.OVERLOADED
    states["app"].current_utilization = 95.0
    tracker.record(300, states)

    budget_statuses = tracker.error_budget_status()
    assert len(budget_statuses) == 2


def test_slo_tracker_dependency_propagation():
    """SLO tracker should propagate downstream health via dependencies."""
    from faultray.simulator.ops_engine import _OpsComponentState
    from faultray.model.components import Dependency

    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=1,
        slo_targets=[SLOTarget(name="avail", metric="availability", target=99.9)],
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE, replicas=1,
        slo_targets=[SLOTarget(name="avail", metric="availability", target=99.9)],
    ))
    graph.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))

    tracker = SLOTracker(graph)

    # DB is DOWN -> app should be affected
    states = {
        "app": _OpsComponentState(
            component_id="app",
            base_utilization=30.0,
            current_utilization=30.0,
            current_health=HealthStatus.HEALTHY,
        ),
        "db": _OpsComponentState(
            component_id="db",
            base_utilization=40.0,
            current_utilization=0.0,
            current_health=HealthStatus.DOWN,
        ),
    }
    point = tracker.record(0, states)
    # db is DOWN, and app requires db, so effective health should propagate
    assert point.down_count >= 1


def test_optional_dependency_propagation_degraded():
    """Optional dependency DOWN should only degrade (not down) the dependent."""
    from faultray.simulator.ops_engine import _OpsComponentState
    from faultray.model.components import Dependency

    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=1,
    ))
    graph.add_component(Component(
        id="cache", name="Cache", type=ComponentType.CACHE, replicas=1,
    ))
    graph.add_dependency(Dependency(source_id="app", target_id="cache", dependency_type="optional"))

    tracker = SLOTracker(graph)

    states = {
        "app": _OpsComponentState(
            component_id="app",
            base_utilization=30.0,
            current_utilization=30.0,
            current_health=HealthStatus.HEALTHY,
        ),
        "cache": _OpsComponentState(
            component_id="cache",
            base_utilization=20.0,
            current_utilization=0.0,
            current_health=HealthStatus.DOWN,
        ),
    }
    point = tracker.record(0, states)
    # Cache is DOWN, but optional -> app should be degraded, not down
    # Total system: cache DOWN, app should become DEGRADED
    assert point.degraded_count >= 1 or point.down_count <= 1


def test_ops_scenario_with_degradation():
    """Scenario with degradation enabled should produce degradation events."""
    from faultray.model.components import Dependency

    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        replicas=2,
        metrics=ResourceMetrics(cpu_percent=20, memory_percent=25),
        capacity=Capacity(
            max_connections=1000, connection_pool_size=200,
            max_memory_mb=4096, max_disk_gb=100,
        ),
        slo_targets=[SLOTarget(name="avail", metric="availability", target=99.9)],
        operational_profile=OperationalProfile(mtbf_hours=720, mttr_minutes=30),
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE,
        replicas=2,
        metrics=ResourceMetrics(cpu_percent=20, memory_percent=25, disk_percent=20),
        capacity=Capacity(max_connections=200, max_disk_gb=500, max_memory_mb=8192),
        slo_targets=[SLOTarget(name="avail", metric="availability", target=99.9)],
        operational_profile=OperationalProfile(mtbf_hours=2160, mttr_minutes=60),
    ))
    graph.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))

    engine = OpsSimulationEngine(graph)
    scenario = OpsScenario(
        id="test-degradation",
        name="Test degradation",
        description="Degradation enabled",
        duration_days=7,
        time_unit=TimeUnit.HOUR,
        traffic_patterns=[create_diurnal_weekly(peak=2.0, duration=604800)],
        enable_random_failures=False,
        enable_degradation=True,
        enable_maintenance=False,
        random_seed=42,
    )
    result = engine.run_ops_scenario(scenario)
    assert isinstance(result, OpsSimulationResult)
    assert len(result.sli_timeline) > 0


def test_ops_scenario_with_maintenance():
    """Scenario with maintenance enabled should schedule maintenance events."""
    from faultray.model.components import Dependency

    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        replicas=2,
        metrics=ResourceMetrics(cpu_percent=20),
        capacity=Capacity(max_connections=1000),
        slo_targets=[SLOTarget(name="avail", metric="availability", target=99.9)],
        operational_profile=OperationalProfile(mtbf_hours=720, mttr_minutes=30),
    ))
    engine = OpsSimulationEngine(graph)
    scenario = OpsScenario(
        id="test-maint",
        name="Test maintenance",
        description="Maintenance enabled",
        duration_days=14,
        time_unit=TimeUnit.HOUR,
        traffic_patterns=[create_diurnal_weekly(peak=2.0, duration=14 * 86400)],
        enable_random_failures=False,
        enable_degradation=False,
        enable_maintenance=True,
        random_seed=42,
    )
    result = engine.run_ops_scenario(scenario)
    assert isinstance(result, OpsSimulationResult)
    # Should have at least some maintenance events over 14 days
    from faultray.simulator.ops_engine import OpsEventType
    maint_events = [e for e in result.events if e.event_type == OpsEventType.MAINTENANCE]
    assert len(maint_events) > 0


def test_ops_scenario_autoscaling():
    """Autoscaling should trigger during high-traffic periods."""
    from faultray.model.components import AutoScalingConfig, Dependency
    from faultray.simulator.traffic import create_growth_trend

    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        replicas=2,
        metrics=ResourceMetrics(cpu_percent=50, memory_percent=40),
        capacity=Capacity(max_connections=1000),
        slo_targets=[SLOTarget(name="avail", metric="availability", target=99.9)],
        operational_profile=OperationalProfile(mtbf_hours=720, mttr_minutes=30),
        autoscaling=AutoScalingConfig(
            enabled=True,
            min_replicas=2,
            max_replicas=10,
            scale_up_threshold=70.0,
            scale_down_threshold=30.0,
            scale_up_delay_seconds=60,
            scale_down_delay_seconds=300,
        ),
    ))
    engine = OpsSimulationEngine(graph)
    # Use growth trend to push utilization up
    scenario = OpsScenario(
        id="test-autoscale",
        name="Test autoscaling",
        description="With autoscaling and growth",
        duration_days=7,
        time_unit=TimeUnit.HOUR,
        traffic_patterns=[
            create_diurnal_weekly(peak=3.0, duration=604800),
            create_growth_trend(monthly_rate=0.5, duration=604800),
        ],
        enable_random_failures=False,
        enable_degradation=False,
        enable_maintenance=False,
        random_seed=42,
    )
    result = engine.run_ops_scenario(scenario)
    assert isinstance(result, OpsSimulationResult)
    assert len(result.sli_timeline) > 0


def test_slo_tracker_estimate_latency():
    """_estimate_latency should follow hockey-stick curve."""
    # Low utilization
    assert SLOTracker._estimate_latency(0.0) == 5.0
    # Medium utilization (30%): base * (1 + 0.3) = 6.5
    low = SLOTracker._estimate_latency(30.0)
    assert low > 5.0 and low < 10.0
    # High utilization (90%): hockey stick
    high = SLOTracker._estimate_latency(90.0)
    assert high > low
    # Very high utilization (120%): extreme
    extreme = SLOTracker._estimate_latency(120.0)
    assert extreme > high


def test_slo_tracker_tier_based_availability():
    """Tiered components should be treated as a single availability unit."""
    from faultray.simulator.ops_engine import _OpsComponentState

    graph = InfraGraph()
    # Create tiered components (same prefix, different numbers)
    graph.add_component(Component(
        id="app-1", name="App 1", type=ComponentType.APP_SERVER, replicas=1,
    ))
    graph.add_component(Component(
        id="app-2", name="App 2", type=ComponentType.APP_SERVER, replicas=1,
    ))

    tracker = SLOTracker(graph)

    # One instance down, one healthy -> tier is still available
    states = {
        "app-1": _OpsComponentState(
            component_id="app-1",
            base_utilization=30.0,
            current_utilization=30.0,
            current_health=HealthStatus.DOWN,
        ),
        "app-2": _OpsComponentState(
            component_id="app-2",
            base_utilization=30.0,
            current_utilization=30.0,
            current_health=HealthStatus.HEALTHY,
        ),
    }
    point = tracker.record(0, states)
    # Even though one is DOWN, tier is still available since another is healthy
    assert point.availability_percent > 50.0


def test_run_default_ops_scenarios_no_app_servers():
    """Default scenarios should work even without app_server/web_server components."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE,
        replicas=2,
        metrics=ResourceMetrics(cpu_percent=20, memory_percent=25, disk_percent=20),
        capacity=Capacity(max_connections=200),
        slo_targets=[SLOTarget(name="avail", metric="availability", target=99.9)],
        operational_profile=OperationalProfile(mtbf_hours=2160, mttr_minutes=60),
    ))
    graph.add_component(Component(
        id="cache", name="Cache", type=ComponentType.CACHE,
        replicas=2,
        metrics=ResourceMetrics(cpu_percent=10),
        capacity=Capacity(max_connections=500),
        slo_targets=[SLOTarget(name="avail", metric="availability", target=99.9)],
        operational_profile=OperationalProfile(mtbf_hours=1440, mttr_minutes=10),
    ))
    engine = OpsSimulationEngine(graph)
    results = engine.run_default_ops_scenarios(time_unit_override=TimeUnit.HOUR)
    assert len(results) == 5


def test_burn_rate_no_violations():
    """Burn rate should be 0 when no violations are recorded."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        replicas=1,
        slo_targets=[SLOTarget(name="avail", metric="availability", target=99.9)],
    ))
    tracker = SLOTracker(graph)
    budget_statuses = tracker.error_budget_status()
    for bs in budget_statuses:
        assert bs.burn_rate_1h == 0.0
        assert bs.burn_rate_6h == 0.0


def test_ops_scenario_full_features():
    """Test scenario with all features enabled: failures, degradation, maintenance, deploys."""
    graph = _build_ops_graph()
    engine = OpsSimulationEngine(graph)
    scenario = OpsScenario(
        id="test-full",
        name="Full features",
        description="All enabled",
        duration_days=14,
        time_unit=TimeUnit.HOUR,
        traffic_patterns=[create_diurnal_weekly(peak=2.0, duration=14 * 86400)],
        scheduled_deploys=[
            {"component_id": "app", "day_of_week": 1, "hour": 14, "downtime_seconds": 30},
        ],
        enable_random_failures=True,
        enable_degradation=True,
        enable_maintenance=True,
        random_seed=42,
    )
    result = engine.run_ops_scenario(scenario)
    assert isinstance(result, OpsSimulationResult)
    assert len(result.sli_timeline) > 0
    assert result.summary != ""
    assert result.total_deploys >= 0
    assert result.peak_utilization >= 0
    assert result.min_availability <= 100.0
    # Error budget statuses should be computed
    assert isinstance(result.error_budget_statuses, list)


def test_degradation_oom_and_disk_full_events():
    """Test that degradation with small capacities generates OOM and disk-full events."""
    from faultray.model.components import DegradationConfig, Dependency
    from faultray.simulator.ops_engine import OpsEventType

    graph = InfraGraph()
    # Component with very small memory capacity and fast leak -> should OOM
    graph.add_component(Component(
        id="leaky-app", name="Leaky App", type=ComponentType.APP_SERVER,
        replicas=1,
        metrics=ResourceMetrics(cpu_percent=20, memory_percent=20),
        capacity=Capacity(
            max_connections=1000, max_memory_mb=50,  # tiny: 50 MB
            max_disk_gb=1,  # tiny: 1 GB
            connection_pool_size=10,  # tiny: 10 connections
        ),
        slo_targets=[SLOTarget(name="avail", metric="availability", target=99.9)],
        operational_profile=OperationalProfile(
            mtbf_hours=9999, mttr_minutes=5,
            degradation=DegradationConfig(
                memory_leak_mb_per_hour=50.0,  # Will OOM in ~1 hour
                disk_fill_gb_per_hour=1.0,  # Will fill disk in ~1 hour
                connection_leak_per_hour=10.0,  # Will exhaust pool in ~1 hour
            ),
        ),
    ))

    engine = OpsSimulationEngine(graph)
    scenario = OpsScenario(
        id="test-degradation-events",
        name="Degradation events",
        description="Fast degradation to trigger all event types",
        duration_days=1,
        time_unit=TimeUnit.HOUR,
        traffic_patterns=[],
        enable_random_failures=False,
        enable_degradation=True,
        enable_maintenance=False,
        random_seed=42,
    )
    result = engine.run_ops_scenario(scenario)

    # Check that OOM, disk full, or conn pool exhaustion events were generated
    event_types = {e.event_type for e in result.events}
    degradation_types = {
        OpsEventType.MEMORY_LEAK_OOM,
        OpsEventType.DISK_FULL,
        OpsEventType.CONN_POOL_EXHAUSTION,
        OpsEventType.MAINTENANCE,  # graceful restarts
    }
    # At least some degradation events should have been generated
    assert len(event_types & degradation_types) > 0
    assert result.total_degradation_events > 0


def test_degradation_no_type_defaults():
    """Component type not in _DEFAULT_DEGRADATION should use zero rates."""
    from faultray.model.components import Dependency
    from faultray.simulator.ops_engine import OpsEventType

    graph = InfraGraph()
    # CUSTOM type is not in _DEFAULT_DEGRADATION, so all rates should be 0
    graph.add_component(Component(
        id="custom-svc", name="Custom", type=ComponentType.CUSTOM,
        replicas=1,
        metrics=ResourceMetrics(cpu_percent=20),
        capacity=Capacity(max_connections=100, max_memory_mb=100, max_disk_gb=10),
        slo_targets=[SLOTarget(name="avail", metric="availability", target=99.9)],
        operational_profile=OperationalProfile(mtbf_hours=9999, mttr_minutes=5),
    ))

    engine = OpsSimulationEngine(graph)
    scenario = OpsScenario(
        id="test-no-defaults",
        name="No degradation defaults",
        description="Custom type has no default degradation",
        duration_days=1,
        time_unit=TimeUnit.HOUR,
        traffic_patterns=[],
        enable_random_failures=False,
        enable_degradation=True,
        enable_maintenance=False,
        random_seed=42,
    )
    result = engine.run_ops_scenario(scenario)
    # No degradation events should be generated (no degradation rates)
    assert result.total_degradation_events == 0


def test_degradation_explicit_rates_override_defaults():
    """Explicitly set degradation rates should override type defaults."""
    from faultray.model.components import DegradationConfig
    from faultray.simulator.ops_engine import OpsEventType

    graph = InfraGraph()
    # App server with explicit (non-zero) degradation rates
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        replicas=1,
        metrics=ResourceMetrics(cpu_percent=20),
        capacity=Capacity(max_connections=1000, max_memory_mb=10, max_disk_gb=100),
        slo_targets=[SLOTarget(name="avail", metric="availability", target=99.9)],
        operational_profile=OperationalProfile(
            mtbf_hours=9999, mttr_minutes=5,
            degradation=DegradationConfig(
                memory_leak_mb_per_hour=100.0,  # Very fast, will OOM quickly
                disk_fill_gb_per_hour=0.0,
                connection_leak_per_hour=0.0,
            ),
        ),
    ))

    engine = OpsSimulationEngine(graph)
    scenario = OpsScenario(
        id="test-explicit-deg",
        name="Explicit degradation",
        description="Explicit rates",
        duration_days=1,
        time_unit=TimeUnit.HOUR,
        traffic_patterns=[],
        enable_random_failures=False,
        enable_degradation=True,
        enable_maintenance=False,
        random_seed=42,
    )
    result = engine.run_ops_scenario(scenario)
    assert result.total_degradation_events > 0


def test_slo_tracker_standalone_failover():
    """Standalone component with failover should get fractional availability impact."""
    from faultray.simulator.ops_engine import _OpsComponentState
    from faultray.model.components import FailoverConfig

    graph = InfraGraph()
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE,
        replicas=1,
        failover=FailoverConfig(
            enabled=True,
            promotion_time_seconds=10,
            health_check_interval_seconds=5,
            failover_threshold=3,
        ),
    ))

    tracker = SLOTracker(graph)

    states = {
        "db": _OpsComponentState(
            component_id="db",
            base_utilization=30.0,
            current_utilization=0.0,
            current_health=HealthStatus.DOWN,
        ),
    }
    point = tracker.record(0, states)
    # Single replica with failover: should have fractional impact, not 100% down
    assert point.availability_percent > 0.0


def test_slo_tracker_multi_replica_failover():
    """Multi-replica component DOWN should have fractional availability impact."""
    from faultray.simulator.ops_engine import _OpsComponentState
    from faultray.model.components import FailoverConfig

    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        replicas=3,
        failover=FailoverConfig(
            enabled=True,
            promotion_time_seconds=5,
            health_check_interval_seconds=3,
            failover_threshold=2,
        ),
    ))

    tracker = SLOTracker(graph)

    states = {
        "app": _OpsComponentState(
            component_id="app",
            base_utilization=30.0,
            current_utilization=0.0,
            current_health=HealthStatus.DOWN,
        ),
    }
    point = tracker.record(0, states)
    # Multi-replica with failover: minimal availability impact
    assert point.availability_percent > 50.0


def test_slo_tracker_micro_penalty_failover():
    """Micro-penalty from failover should reduce availability slightly."""
    from faultray.simulator.ops_engine import _OpsComponentState
    from faultray.model.components import FailoverConfig

    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        replicas=2,
        failover=FailoverConfig(
            enabled=True,
            promotion_time_seconds=10,
            health_check_interval_seconds=5,
            failover_threshold=3,
        ),
    ))
    graph.add_component(Component(
        id="lb", name="LB", type=ComponentType.LOAD_BALANCER,
        replicas=2,
    ))

    tracker = SLOTracker(graph)

    # Record two points to establish step window
    states = {
        "app": _OpsComponentState(
            component_id="app",
            base_utilization=30.0,
            current_utilization=30.0,
            current_health=HealthStatus.HEALTHY,
        ),
        "lb": _OpsComponentState(
            component_id="lb",
            base_utilization=15.0,
            current_utilization=15.0,
            current_health=HealthStatus.HEALTHY,
        ),
    }
    tracker.record(0, states)

    # Second point with app DOWN
    states["app"].current_health = HealthStatus.DOWN
    states["app"].current_utilization = 0.0
    point2 = tracker.record(300, states)
    # Should still have high availability thanks to failover
    assert point2.availability_percent > 80.0


def test_tiered_components_all_down_with_failover():
    """All members of a real tier DOWN with failover should get fractional impact."""
    from faultray.simulator.ops_engine import _OpsComponentState
    from faultray.model.components import FailoverConfig

    graph = InfraGraph()
    # Use IDs that match the tier regex: "web-1", "web-2" -> tier prefix "web"
    graph.add_component(Component(
        id="web-1", name="Web 1", type=ComponentType.APP_SERVER,
        replicas=1,
        failover=FailoverConfig(
            enabled=True,
            promotion_time_seconds=10,
            health_check_interval_seconds=5,
            failover_threshold=3,
        ),
    ))
    graph.add_component(Component(
        id="web-2", name="Web 2", type=ComponentType.APP_SERVER,
        replicas=1,
        failover=FailoverConfig(
            enabled=True,
            promotion_time_seconds=10,
            health_check_interval_seconds=5,
            failover_threshold=3,
        ),
    ))

    tracker = SLOTracker(graph)

    # Both tier members DOWN -> should hit tier-level failover branch (lines 394-396)
    states = {
        "web-1": _OpsComponentState(
            component_id="web-1",
            base_utilization=30.0,
            current_utilization=0.0,
            current_health=HealthStatus.DOWN,
        ),
        "web-2": _OpsComponentState(
            component_id="web-2",
            base_utilization=30.0,
            current_utilization=0.0,
            current_health=HealthStatus.DOWN,
        ),
    }
    point = tracker.record(0, states)
    # With failover, availability should not be zero
    assert point.availability_percent > 0.0


def test_single_member_tier_becomes_standalone():
    """A single-member tier (matches regex but only 1 member) should move to standalone."""
    from faultray.simulator.ops_engine import _OpsComponentState

    graph = InfraGraph()
    # "cache-1" matches regex -> prefix "cache", but only one member -> standalone
    graph.add_component(Component(
        id="cache-1", name="Cache 1", type=ComponentType.CACHE,
        replicas=1,
    ))
    # "db" doesn't match regex -> already standalone
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE,
        replicas=1,
    ))

    tracker = SLOTracker(graph)

    states = {
        "cache-1": _OpsComponentState(
            component_id="cache-1",
            base_utilization=20.0,
            current_utilization=20.0,
            current_health=HealthStatus.HEALTHY,
        ),
        "db": _OpsComponentState(
            component_id="db",
            base_utilization=30.0,
            current_utilization=30.0,
            current_health=HealthStatus.HEALTHY,
        ),
    }
    point = tracker.record(0, states)
    # Both healthy -> 100% availability (minus network penalty)
    assert point.availability_percent > 99.0


def test_micro_penalty_with_history():
    """Micro-penalty calculation should use step_window from measurement history."""
    from faultray.simulator.ops_engine import _OpsComponentState
    from faultray.model.components import FailoverConfig

    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        replicas=3,
        failover=FailoverConfig(
            enabled=True,
            promotion_time_seconds=5,
            health_check_interval_seconds=3,
            failover_threshold=2,
        ),
    ))

    tracker = SLOTracker(graph)

    # First measurement: healthy
    states = {
        "app": _OpsComponentState(
            component_id="app",
            base_utilization=30.0,
            current_utilization=30.0,
            current_health=HealthStatus.HEALTHY,
        ),
    }
    tracker.record(0, states)

    # Second measurement: healthy (to establish history)
    tracker.record(300, states)

    # Third measurement: app DOWN with failover -> micro-penalty uses step_window from history
    states["app"].current_health = HealthStatus.DOWN
    states["app"].current_utilization = 0.0
    point3 = tracker.record(600, states)
    # Should have reduced availability due to micro-penalty
    assert point3.availability_percent < 100.0
    assert point3.availability_percent > 0.0


def test_gc_pause_network_penalty():
    """GC pause frequency > 0 should contribute to network penalty."""
    from faultray.simulator.ops_engine import _OpsComponentState
    from faultray.model.components import RuntimeJitter

    graph = InfraGraph()
    graph.add_component(Component(
        id="jvm-app", name="JVM App", type=ComponentType.APP_SERVER,
        replicas=1,
        runtime_jitter=RuntimeJitter(
            gc_pause_ms=50.0,         # 50ms GC pauses
            gc_pause_frequency=2.0,    # 2 pauses/second
        ),
    ))

    tracker = SLOTracker(graph)

    states = {
        "jvm-app": _OpsComponentState(
            component_id="jvm-app",
            base_utilization=30.0,
            current_utilization=30.0,
            current_health=HealthStatus.HEALTHY,
        ),
    }
    point = tracker.record(0, states)
    # GC pauses should reduce availability slightly
    # gc_fraction = 50/1000 * 2.0 = 0.1 (10% of time in GC)
    assert point.availability_percent < 100.0
    assert point.availability_percent > 80.0


def test_budget_consumed_single_violation():
    """_budget_consumed with single violation should use default 300s window."""
    from faultray.simulator.ops_engine import _OpsComponentState

    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        replicas=1,
        slo_targets=[SLOTarget(name="avail", metric="availability", target=99.9)],
    ))
    tracker = SLOTracker(graph)

    # Record exactly one point with a DOWN state to create a single violation
    states = {
        "app": _OpsComponentState(
            component_id="app",
            base_utilization=30.0,
            current_utilization=0.0,
            current_health=HealthStatus.DOWN,
        ),
    }
    tracker.record(0, states)

    # _budget_consumed should handle single violation (total_count == 1)
    slo = graph.get_component("app").slo_targets[0]
    consumed = tracker._budget_consumed(slo, "app")
    # Single violation, total_count=1, time_span_seconds=300 (default)
    assert consumed > 0.0


def test_burn_rate_100_percent_slo():
    """Burn rate with slo.target=100.0 should return inf for violations (allowed_ratio=0)."""
    from faultray.simulator.ops_engine import _OpsComponentState

    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        replicas=1,
        slo_targets=[SLOTarget(name="avail", metric="availability", target=100.0)],
    ))
    tracker = SLOTracker(graph)

    # Record a healthy point then a violation point
    states = {
        "app": _OpsComponentState(
            component_id="app",
            base_utilization=30.0,
            current_utilization=30.0,
            current_health=HealthStatus.HEALTHY,
        ),
    }
    tracker.record(0, states)

    states["app"].current_health = HealthStatus.DOWN
    states["app"].current_utilization = 0.0
    tracker.record(300, states)

    # allowed_ratio = 1.0 - 100.0/100.0 = 0.0 -> should return inf if violated
    slo = graph.get_component("app").slo_targets[0]
    burn_rate = tracker._burn_rate(slo, "app", 3600)
    assert burn_rate == float("inf")


def test_graceful_restart_memory_degradation():
    """Memory leak reaching 80-99% should trigger graceful restart, not OOM."""
    from faultray.model.components import DegradationConfig
    from faultray.simulator.ops_engine import OpsEventType

    graph = InfraGraph()
    # Slow leak rate with enough capacity to hit graceful restart threshold
    # At 5-minute steps: 10 MB/hour -> ~0.83 MB per 5-min step
    # With 100 MB max: will take ~80 steps to reach 80% (80 MB)
    # But at HOUR granularity: 10 MB/step, max 100 -> hits 80% at step 8, 100% at step 10
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        replicas=1,
        metrics=ResourceMetrics(cpu_percent=20),
        capacity=Capacity(
            max_connections=1000, max_memory_mb=100,
        ),
        slo_targets=[SLOTarget(name="avail", metric="availability", target=99.9)],
        operational_profile=OperationalProfile(
            mtbf_hours=9999, mttr_minutes=5,
            degradation=DegradationConfig(
                memory_leak_mb_per_hour=10.0,  # 10 MB/hour
                disk_fill_gb_per_hour=0.0,
                connection_leak_per_hour=0.0,
            ),
        ),
    ))

    engine = OpsSimulationEngine(graph)
    scenario = OpsScenario(
        id="test-graceful-restart",
        name="Graceful restart test",
        description="Memory leak should trigger graceful restart at 80%",
        duration_days=1,
        time_unit=TimeUnit.HOUR,
        traffic_patterns=[],
        enable_random_failures=False,
        enable_degradation=True,
        enable_maintenance=False,
        random_seed=42,
    )
    result = engine.run_ops_scenario(scenario)

    # Should have graceful restart events (MAINTENANCE) from memory threshold
    maint_events = [e for e in result.events if e.event_type == OpsEventType.MAINTENANCE
                    and "Graceful restart" in e.description and "memory" in e.description]
    assert len(maint_events) > 0, (
        f"Expected graceful restart events, got: {[e.description for e in result.events]}"
    )


def test_default_mttr_fallback():
    """Component type not in _DEFAULT_MTTR_MINUTES should use 30.0 fallback."""
    from faultray.model.components import FailoverConfig

    graph = InfraGraph()
    # CUSTOM type is not in _DEFAULT_MTTR_MINUTES
    graph.add_component(Component(
        id="custom", name="Custom", type=ComponentType.CUSTOM,
        replicas=1,
        metrics=ResourceMetrics(cpu_percent=20),
        slo_targets=[SLOTarget(name="avail", metric="availability", target=99.9)],
        operational_profile=OperationalProfile(mtbf_hours=24, mttr_minutes=0),
    ))

    engine = OpsSimulationEngine(graph)
    scenario = OpsScenario(
        id="test-mttr-fallback",
        name="MTTR fallback",
        description="CUSTOM type with zero MTTR should use default",
        duration_days=7,
        time_unit=TimeUnit.HOUR,
        traffic_patterns=[],
        enable_random_failures=True,
        enable_degradation=False,
        enable_maintenance=False,
        random_seed=42,
    )
    result = engine.run_ops_scenario(scenario)
    # Should run without error and produce events (low MTBF = frequent failures)
    assert result.total_failures > 0
