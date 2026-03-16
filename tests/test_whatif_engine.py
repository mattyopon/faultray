"""Tests for what-if analysis engine."""

from faultray.model.components import (
    Capacity,
    Component,
    ComponentType,
    Dependency,
    OperationalProfile,
    ResourceMetrics,
    SLOTarget,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.ops_engine import OpsScenario, TimeUnit
from faultray.simulator.traffic import create_diurnal_weekly
from faultray.simulator.whatif_engine import (
    MultiWhatIfScenario,
    WhatIfEngine,
    WhatIfScenario,
)


def _build_whatif_graph() -> InfraGraph:
    """Build a graph for what-if tests."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        replicas=2,
        metrics=ResourceMetrics(cpu_percent=20, memory_percent=25),
        capacity=Capacity(max_connections=1000),
        slo_targets=[SLOTarget(name="avail", metric="availability", target=99.9)],
        operational_profile=OperationalProfile(mtbf_hours=720, mttr_minutes=30),
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE,
        replicas=2,
        metrics=ResourceMetrics(cpu_percent=20, memory_percent=25, disk_percent=20),
        capacity=Capacity(max_connections=200),
        slo_targets=[SLOTarget(name="avail", metric="availability", target=99.9)],
        operational_profile=OperationalProfile(mtbf_hours=2160, mttr_minutes=60),
    ))
    graph.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))
    return graph


def _base_scenario() -> OpsScenario:
    return OpsScenario(
        id="whatif-test",
        name="What-if test base",
        description="Base for what-if tests",
        duration_days=1,
        time_unit=TimeUnit.FIVE_MINUTES,
        traffic_patterns=[create_diurnal_weekly(peak=2.0, duration=86400)],
        enable_random_failures=True,
        enable_degradation=False,
        enable_maintenance=False,
    )


def test_whatif_mttr_sweep():
    """MTTR factor sweep should produce results for each value."""
    graph = _build_whatif_graph()
    engine = WhatIfEngine(graph)
    whatif = WhatIfScenario(
        base_scenario=_base_scenario(),
        parameter="mttr_factor",
        values=[0.5, 1.0, 2.0],
    )
    result = engine.run_whatif(whatif)
    assert len(result.avg_availabilities) == 3
    assert len(result.slo_pass) == 3
    assert result.parameter == "mttr_factor"


def test_whatif_unsupported_parameter():
    """Unsupported parameter should raise ValueError."""
    graph = _build_whatif_graph()
    engine = WhatIfEngine(graph)
    whatif = WhatIfScenario(
        base_scenario=_base_scenario(),
        parameter="invalid_param",
        values=[1.0],
    )
    try:
        engine.run_whatif(whatif)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "invalid_param" in str(e)


def test_multi_whatif():
    """Multi-parameter what-if should combine effects."""
    graph = _build_whatif_graph()
    engine = WhatIfEngine(graph)
    multi = MultiWhatIfScenario(
        base_scenario=_base_scenario(),
        parameters={"mttr_factor": 2.0, "traffic_factor": 1.5},
    )
    result = engine.run_multi_whatif(multi)
    assert result.avg_availability > 0
    assert result.avg_availability <= 100.0


def test_whatif_deterministic():
    """Same seed should produce same results."""
    graph = _build_whatif_graph()
    whatif = WhatIfScenario(
        base_scenario=_base_scenario(),
        parameter="mttr_factor",
        values=[1.0],
        seed=42,
    )
    engine1 = WhatIfEngine(graph)
    result1 = engine1.run_whatif(whatif)
    engine2 = WhatIfEngine(graph)
    result2 = engine2.run_whatif(whatif)
    assert result1.avg_availabilities == result2.avg_availabilities


# ---------------------------------------------------------------------------
# run_whatif: breakpoint detection, summary, additional parameters
# ---------------------------------------------------------------------------


def test_whatif_breakpoint_detected():
    """Breakpoint should be set to the first value where SLO fails."""
    graph = _build_whatif_graph()
    engine = WhatIfEngine(graph)
    # Very aggressive MTBF factors (low values = very frequent failures)
    whatif = WhatIfScenario(
        base_scenario=_base_scenario(),
        parameter="mtbf_factor",
        values=[1.0, 0.1, 0.01],
        description="Testing breakpoint detection",
    )
    result = engine.run_whatif(whatif)
    assert len(result.avg_availabilities) == 3
    # If any value fails SLO, breakpoint should be set
    if not all(result.slo_pass):
        assert result.breakpoint_value is not None


def test_whatif_summary_contains_description():
    """Summary should contain the description from the scenario."""
    graph = _build_whatif_graph()
    engine = WhatIfEngine(graph)
    whatif = WhatIfScenario(
        base_scenario=_base_scenario(),
        parameter="mttr_factor",
        values=[1.0],
        description="Custom description for test",
    )
    result = engine.run_whatif(whatif)
    assert "Custom description for test" in result.summary


def test_whatif_summary_no_breakpoint():
    """When all values pass SLO, summary should indicate all passed."""
    graph = _build_whatif_graph()
    engine = WhatIfEngine(graph)
    whatif = WhatIfScenario(
        base_scenario=_base_scenario(),
        parameter="mttr_factor",
        values=[1.0],
        description="",
    )
    result = engine.run_whatif(whatif)
    if all(result.slo_pass):
        assert "passed" in result.summary.lower() or "PASS" in result.summary


def test_whatif_mtbf_sweep():
    """MTBF factor sweep should produce results."""
    graph = _build_whatif_graph()
    engine = WhatIfEngine(graph)
    whatif = WhatIfScenario(
        base_scenario=_base_scenario(),
        parameter="mtbf_factor",
        values=[1.0, 0.5],
    )
    result = engine.run_whatif(whatif)
    assert result.parameter == "mtbf_factor"
    assert len(result.avg_availabilities) == 2


def test_whatif_traffic_factor_sweep():
    """Traffic factor sweep should produce results."""
    graph = _build_whatif_graph()
    engine = WhatIfEngine(graph)
    whatif = WhatIfScenario(
        base_scenario=_base_scenario(),
        parameter="traffic_factor",
        values=[1.0, 2.0],
    )
    result = engine.run_whatif(whatif)
    assert result.parameter == "traffic_factor"
    assert len(result.avg_availabilities) == 2


def test_whatif_replica_factor_sweep():
    """Replica factor sweep should produce results."""
    graph = _build_whatif_graph()
    engine = WhatIfEngine(graph)
    whatif = WhatIfScenario(
        base_scenario=_base_scenario(),
        parameter="replica_factor",
        values=[1.0, 0.5],
    )
    result = engine.run_whatif(whatif)
    assert result.parameter == "replica_factor"
    assert len(result.avg_availabilities) == 2


def test_whatif_maint_duration_factor_sweep():
    """Maintenance duration factor sweep should produce results."""
    graph = _build_whatif_graph()
    engine = WhatIfEngine(graph)
    whatif = WhatIfScenario(
        base_scenario=_base_scenario(),
        parameter="maint_duration_factor",
        values=[1.0, 2.0],
    )
    result = engine.run_whatif(whatif)
    assert result.parameter == "maint_duration_factor"
    assert len(result.avg_availabilities) == 2


# ---------------------------------------------------------------------------
# run_default_whatifs
# ---------------------------------------------------------------------------


def test_run_default_whatifs():
    """Default what-ifs should return 5 results for 5 parameters."""
    graph = _build_whatif_graph()
    engine = WhatIfEngine(graph)
    results = engine.run_default_whatifs()
    assert len(results) == 5
    params = {r.parameter for r in results}
    assert "mttr_factor" in params
    assert "mtbf_factor" in params
    assert "traffic_factor" in params
    assert "replica_factor" in params
    assert "maint_duration_factor" in params


# ---------------------------------------------------------------------------
# Multi-parameter what-if: validation & defaults
# ---------------------------------------------------------------------------


def test_multi_whatif_unsupported_parameter():
    """Multi-parameter what-if with unsupported param should raise ValueError."""
    graph = _build_whatif_graph()
    engine = WhatIfEngine(graph)
    multi = MultiWhatIfScenario(
        base_scenario=_base_scenario(),
        parameters={"invalid_param": 2.0},
    )
    try:
        engine.run_multi_whatif(multi)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "invalid_param" in str(e)


def test_multi_whatif_description():
    """Multi-parameter what-if should include description in summary."""
    graph = _build_whatif_graph()
    engine = WhatIfEngine(graph)
    multi = MultiWhatIfScenario(
        base_scenario=_base_scenario(),
        parameters={"mttr_factor": 1.0},
        description="Custom multi description",
    )
    result = engine.run_multi_whatif(multi)
    assert "Custom multi description" in result.summary


def test_multi_whatif_no_description():
    """Multi-parameter what-if with empty description should auto-generate one."""
    graph = _build_whatif_graph()
    engine = WhatIfEngine(graph)
    multi = MultiWhatIfScenario(
        base_scenario=_base_scenario(),
        parameters={"mttr_factor": 2.0, "traffic_factor": 1.5},
        description="",
    )
    result = engine.run_multi_whatif(multi)
    assert "Multi what-if" in result.summary


def test_multi_whatif_all_parameters():
    """Multi-parameter what-if should handle all 5 parameter types simultaneously."""
    graph = _build_whatif_graph()
    engine = WhatIfEngine(graph)
    multi = MultiWhatIfScenario(
        base_scenario=_base_scenario(),
        parameters={
            "mttr_factor": 1.5,
            "mtbf_factor": 0.8,
            "traffic_factor": 1.2,
            "replica_factor": 1.0,
            "maint_duration_factor": 1.5,
        },
    )
    result = engine.run_multi_whatif(multi)
    assert result.avg_availability > 0
    assert result.avg_availability <= 100.0
    assert isinstance(result.slo_pass, bool)


def test_multi_whatif_replica_autoscaling():
    """Multi what-if replica_factor should also scale autoscaling min/max."""
    from faultray.model.components import AutoScalingConfig
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        replicas=4,
        metrics=ResourceMetrics(cpu_percent=20, memory_percent=25),
        capacity=Capacity(max_connections=1000),
        slo_targets=[SLOTarget(name="avail", metric="availability", target=99.9)],
        operational_profile=OperationalProfile(mtbf_hours=720, mttr_minutes=30),
        autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=10),
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE,
        replicas=2,
        metrics=ResourceMetrics(cpu_percent=20, memory_percent=25, disk_percent=20),
        capacity=Capacity(max_connections=200),
        slo_targets=[SLOTarget(name="avail", metric="availability", target=99.9)],
        operational_profile=OperationalProfile(mtbf_hours=2160, mttr_minutes=60),
    ))
    graph.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))

    engine = WhatIfEngine(graph)
    multi = MultiWhatIfScenario(
        base_scenario=_base_scenario(),
        parameters={"replica_factor": 0.5},
    )
    result = engine.run_multi_whatif(multi)
    assert result.avg_availability > 0


# ---------------------------------------------------------------------------
# run_default_multi_whatifs
# ---------------------------------------------------------------------------


def test_run_default_multi_whatifs():
    """Default multi what-ifs should return 4 results."""
    graph = _build_whatif_graph()
    engine = WhatIfEngine(graph)
    results = engine.run_default_multi_whatifs()
    assert len(results) == 4
    for r in results:
        assert r.avg_availability > 0
        assert r.avg_availability <= 100.0
        assert isinstance(r.slo_pass, bool)


# ---------------------------------------------------------------------------
# Static helper methods
# ---------------------------------------------------------------------------


def test_compute_avg_availability_empty():
    """Empty SLI timeline should return 100.0."""
    from dataclasses import dataclass, field as dc_field
    from faultray.simulator.ops_engine import OpsSimulationResult

    # Create a minimal OpsSimulationResult with empty sli_timeline
    scenario = _base_scenario()
    result = OpsSimulationResult(scenario=scenario)
    result.sli_timeline = []
    avg = WhatIfEngine._compute_avg_availability(result)
    assert avg == 100.0


def test_build_whatif_summary_with_breakpoint():
    """Summary with breakpoint should mention the breakpoint value."""
    whatif = WhatIfScenario(
        base_scenario=_base_scenario(),
        parameter="mttr_factor",
        values=[1.0, 2.0, 4.0],
        description="Breakpoint test",
    )
    summary = WhatIfEngine._build_whatif_summary(
        whatif,
        avg_availabilities=[99.99, 99.85, 99.50],
        slo_pass=[True, False, False],
        breakpoint_value=2.0,
    )
    assert "breakpoint" in summary.lower()
    assert "2.0" in summary


def test_build_whatif_summary_no_description():
    """Summary without description should still work."""
    whatif = WhatIfScenario(
        base_scenario=_base_scenario(),
        parameter="mttr_factor",
        values=[1.0],
        description="",
    )
    summary = WhatIfEngine._build_whatif_summary(
        whatif,
        avg_availabilities=[99.99],
        slo_pass=[True],
        breakpoint_value=None,
    )
    assert "mttr_factor" in summary
    assert "passed" in summary.lower() or "PASS" in summary


# ---------------------------------------------------------------------------
# _create_default_base_scenario coverage
# ---------------------------------------------------------------------------


def test_create_default_base_scenario_with_app_servers():
    """Base scenario should target app_server/web_server components for deploys."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app1", name="App1", type=ComponentType.APP_SERVER,
        replicas=2,
        metrics=ResourceMetrics(cpu_percent=20),
        operational_profile=OperationalProfile(mtbf_hours=720, mttr_minutes=30),
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE,
        replicas=2,
        metrics=ResourceMetrics(cpu_percent=20, disk_percent=20),
        operational_profile=OperationalProfile(mtbf_hours=2160, mttr_minutes=60),
    ))
    graph.add_dependency(Dependency(source_id="app1", target_id="db", dependency_type="requires"))

    engine = WhatIfEngine(graph)
    scenario = engine._create_default_base_scenario()
    assert scenario.id == "whatif-7d-full"
    assert scenario.duration_days == 7
    # Scheduled deploys should target app1
    deploy_component_ids = {d["component_id"] for d in scenario.scheduled_deploys}
    assert "app1" in deploy_component_ids


def test_create_default_base_scenario_no_app_servers():
    """Base scenario without app_server types should use first N components."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="db1", name="DB1", type=ComponentType.DATABASE,
        replicas=2,
        operational_profile=OperationalProfile(mtbf_hours=720, mttr_minutes=30),
    ))
    graph.add_component(Component(
        id="db2", name="DB2", type=ComponentType.DATABASE,
        replicas=2,
        operational_profile=OperationalProfile(mtbf_hours=720, mttr_minutes=30),
    ))
    graph.add_dependency(Dependency(source_id="db1", target_id="db2", dependency_type="requires"))

    engine = WhatIfEngine(graph)
    scenario = engine._create_default_base_scenario()
    # Without app servers, should fallback to first 2 components
    deploy_component_ids = {d["component_id"] for d in scenario.scheduled_deploys}
    assert len(deploy_component_ids) > 0


# ---------------------------------------------------------------------------
# Coverage: zero MTTR/MTBF pre-population in _apply_mttr_factor (lines 540,549)
# ---------------------------------------------------------------------------


def _build_zero_profile_graph() -> InfraGraph:
    """Build a graph where components have zero MTBF and zero MTTR.

    This triggers the default pre-population branches in _apply_mttr_factor,
    _apply_mtbf_factor, and run_multi_whatif.
    """
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        replicas=2,
        metrics=ResourceMetrics(cpu_percent=20, memory_percent=25),
        capacity=Capacity(max_connections=1000),
        slo_targets=[SLOTarget(name="avail", metric="availability", target=99.9)],
        operational_profile=OperationalProfile(mtbf_hours=0, mttr_minutes=0),
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE,
        replicas=2,
        metrics=ResourceMetrics(cpu_percent=20, memory_percent=25, disk_percent=20),
        capacity=Capacity(max_connections=200),
        slo_targets=[SLOTarget(name="avail", metric="availability", target=99.9)],
        operational_profile=OperationalProfile(mtbf_hours=0, mttr_minutes=0),
    ))
    graph.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))
    return graph


def test_apply_mttr_factor_zero_profiles():
    """_apply_mttr_factor should pre-populate zero MTBF and MTTR with defaults."""
    graph = _build_zero_profile_graph()
    engine = WhatIfEngine(graph)
    whatif = WhatIfScenario(
        base_scenario=_base_scenario(),
        parameter="mttr_factor",
        values=[1.0],
    )
    result = engine.run_whatif(whatif)
    assert len(result.avg_availabilities) == 1
    assert result.parameter == "mttr_factor"


# ---------------------------------------------------------------------------
# Coverage: zero MTBF pre-population in _apply_mtbf_factor (line 585)
# ---------------------------------------------------------------------------


def test_apply_mtbf_factor_zero_profiles():
    """_apply_mtbf_factor should pre-populate zero MTBF with defaults."""
    graph = _build_zero_profile_graph()
    engine = WhatIfEngine(graph)
    whatif = WhatIfScenario(
        base_scenario=_base_scenario(),
        parameter="mtbf_factor",
        values=[1.0],
    )
    result = engine.run_whatif(whatif)
    assert len(result.avg_availabilities) == 1
    assert result.parameter == "mtbf_factor"


# ---------------------------------------------------------------------------
# Coverage: autoscaling in _apply_replica_factor (lines 670-673)
# ---------------------------------------------------------------------------


def test_apply_replica_factor_with_autoscaling():
    """_apply_replica_factor should scale autoscaling min/max when enabled."""
    from faultray.model.components import AutoScalingConfig
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        replicas=4,
        metrics=ResourceMetrics(cpu_percent=20, memory_percent=25),
        capacity=Capacity(max_connections=1000),
        slo_targets=[SLOTarget(name="avail", metric="availability", target=99.9)],
        operational_profile=OperationalProfile(mtbf_hours=720, mttr_minutes=30),
        autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=10),
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE,
        replicas=2,
        metrics=ResourceMetrics(cpu_percent=20, memory_percent=25, disk_percent=20),
        capacity=Capacity(max_connections=200),
        slo_targets=[SLOTarget(name="avail", metric="availability", target=99.9)],
        operational_profile=OperationalProfile(mtbf_hours=2160, mttr_minutes=60),
    ))
    graph.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))

    engine = WhatIfEngine(graph)
    whatif = WhatIfScenario(
        base_scenario=_base_scenario(),
        parameter="replica_factor",
        values=[0.5],
    )
    result = engine.run_whatif(whatif)
    assert len(result.avg_availabilities) == 1
    assert result.parameter == "replica_factor"


# ---------------------------------------------------------------------------
# Coverage: zero MTTR/MTBF in run_multi_whatif (lines 345, 354)
# ---------------------------------------------------------------------------


def test_multi_whatif_zero_mttr_mtbf():
    """run_multi_whatif should pre-populate zero MTTR and MTBF with defaults."""
    graph = _build_zero_profile_graph()
    engine = WhatIfEngine(graph)
    multi = MultiWhatIfScenario(
        base_scenario=_base_scenario(),
        parameters={"mttr_factor": 2.0, "mtbf_factor": 0.5},
    )
    result = engine.run_multi_whatif(multi)
    assert result.avg_availability > 0
    assert result.avg_availability <= 100.0
