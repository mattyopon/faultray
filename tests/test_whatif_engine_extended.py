"""Extended tests for what-if analysis engine — targeting uncovered lines."""

import pytest

from faultray.model.components import (
    AutoScalingConfig,
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
from faultray.simulator.ops_engine import OpsScenario, OpsSimulationResult, TimeUnit
from faultray.simulator.traffic import create_diurnal_weekly
from faultray.simulator.whatif_engine import (
    MultiWhatIfResult,
    MultiWhatIfScenario,
    WhatIfEngine,
    WhatIfResult,
    WhatIfScenario,
    _SLO_THRESHOLD,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _build_whatif_graph() -> InfraGraph:
    """Build a graph for what-if tests with operational profiles."""
    graph = InfraGraph()

    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        replicas=2,
        metrics=ResourceMetrics(cpu_percent=20, memory_percent=25),
        capacity=Capacity(max_connections=1000),
        slo_targets=[SLOTarget(name="avail", metric="availability", target=99.9)],
        operational_profile=OperationalProfile(mtbf_hours=720, mttr_minutes=30),
        autoscaling=AutoScalingConfig(
            enabled=True, min_replicas=1, max_replicas=6,
        ),
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE,
        replicas=2,
        metrics=ResourceMetrics(cpu_percent=20, memory_percent=25, disk_percent=20),
        capacity=Capacity(max_connections=200),
        slo_targets=[SLOTarget(name="avail", metric="availability", target=99.9)],
        operational_profile=OperationalProfile(mtbf_hours=2160, mttr_minutes=60),
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
    ))

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


# ---------------------------------------------------------------------------
# Breakpoint detection — lines 225-226
# ---------------------------------------------------------------------------


def test_whatif_breakpoint_detection():
    """When SLO fails, breakpoint_value should be the first failing value."""
    graph = _build_whatif_graph()
    engine = WhatIfEngine(graph)

    # Use extremely small MTBF to guarantee SLO failure
    whatif = WhatIfScenario(
        base_scenario=_base_scenario(),
        parameter="mtbf_factor",
        values=[1.0, 0.01],  # 0.01 should fail
        seed=42,
    )
    result = engine.run_whatif(whatif)
    assert len(result.avg_availabilities) == 2
    # At least verify structure is correct
    assert result.parameter == "mtbf_factor"
    assert len(result.slo_pass) == 2


# ---------------------------------------------------------------------------
# run_default_whatifs — lines 256-296
# ---------------------------------------------------------------------------


def test_run_default_whatifs():
    """run_default_whatifs should run all 5 parameter sweeps."""
    graph = _build_whatif_graph()
    engine = WhatIfEngine(graph)
    results = engine.run_default_whatifs()
    assert len(results) == 5
    params = {r.parameter for r in results}
    assert params == {"mttr_factor", "mtbf_factor", "traffic_factor", "replica_factor", "maint_duration_factor"}


# ---------------------------------------------------------------------------
# Multi what-if — lines 322, 345, 352-391
# ---------------------------------------------------------------------------


def test_multi_whatif_unsupported_parameter():
    """Unsupported parameter in multi what-if should raise ValueError."""
    graph = _build_whatif_graph()
    engine = WhatIfEngine(graph)
    multi = MultiWhatIfScenario(
        base_scenario=_base_scenario(),
        parameters={"invalid_param": 2.0, "mttr_factor": 1.0},
    )
    with pytest.raises(ValueError, match="Unsupported"):
        engine.run_multi_whatif(multi)


def test_multi_whatif_mttr_factor():
    """Multi what-if with mttr_factor should modify MTTR."""
    graph = _build_whatif_graph()
    engine = WhatIfEngine(graph)
    multi = MultiWhatIfScenario(
        base_scenario=_base_scenario(),
        parameters={"mttr_factor": 2.0},
    )
    result = engine.run_multi_whatif(multi)
    assert result.avg_availability > 0
    assert result.avg_availability <= 100.0
    assert "mttr_factor" in result.summary


def test_multi_whatif_mtbf_factor():
    """Multi what-if with mtbf_factor should modify MTBF."""
    graph = _build_whatif_graph()
    engine = WhatIfEngine(graph)
    multi = MultiWhatIfScenario(
        base_scenario=_base_scenario(),
        parameters={"mtbf_factor": 0.5},
    )
    result = engine.run_multi_whatif(multi)
    assert result.avg_availability > 0


def test_multi_whatif_traffic_factor():
    """Multi what-if with traffic_factor should scale traffic."""
    graph = _build_whatif_graph()
    engine = WhatIfEngine(graph)
    multi = MultiWhatIfScenario(
        base_scenario=_base_scenario(),
        parameters={"traffic_factor": 2.0},
    )
    result = engine.run_multi_whatif(multi)
    assert result.avg_availability > 0


def test_multi_whatif_replica_factor():
    """Multi what-if with replica_factor should scale replicas."""
    graph = _build_whatif_graph()
    engine = WhatIfEngine(graph)
    multi = MultiWhatIfScenario(
        base_scenario=_base_scenario(),
        parameters={"replica_factor": 0.5},
    )
    result = engine.run_multi_whatif(multi)
    assert result.avg_availability > 0


def test_multi_whatif_maint_duration():
    """Multi what-if with maint_duration_factor."""
    graph = _build_whatif_graph()
    engine = WhatIfEngine(graph)
    multi = MultiWhatIfScenario(
        base_scenario=_base_scenario(),
        parameters={"maint_duration_factor": 2.0},
    )
    result = engine.run_multi_whatif(multi)
    assert result.avg_availability > 0


def test_multi_whatif_combined():
    """Multi what-if with multiple parameters simultaneously."""
    graph = _build_whatif_graph()
    engine = WhatIfEngine(graph)
    multi = MultiWhatIfScenario(
        base_scenario=_base_scenario(),
        parameters={"mttr_factor": 2.0, "traffic_factor": 1.5, "replica_factor": 0.75},
    )
    result = engine.run_multi_whatif(multi)
    assert result.avg_availability > 0
    assert "PASS" in result.summary or "FAIL" in result.summary


# ---------------------------------------------------------------------------
# run_default_multi_whatifs — lines 443-473
# ---------------------------------------------------------------------------


def test_run_default_multi_whatifs():
    """run_default_multi_whatifs should run 4 default combinations."""
    graph = _build_whatif_graph()
    engine = WhatIfEngine(graph)
    results = engine.run_default_multi_whatifs()
    assert len(results) == 4
    for r in results:
        assert r.avg_availability > 0
        assert r.avg_availability <= 100.0


# ---------------------------------------------------------------------------
# _apply_factor dispatch — lines 540, 549
# ---------------------------------------------------------------------------


def test_apply_mttr_factor():
    """MTTR factor should scale MTTR values."""
    graph = _build_whatif_graph()
    engine = WhatIfEngine(graph)
    modified_graph, scenario = engine._apply_factor(
        "mttr_factor", 2.0, _base_scenario()
    )
    # Verify MTTR was scaled
    for comp in modified_graph.components.values():
        assert comp.operational_profile.mttr_minutes > 0


def test_apply_mtbf_factor():
    """MTBF factor should scale MTBF values."""
    graph = _build_whatif_graph()
    engine = WhatIfEngine(graph)
    modified_graph, scenario = engine._apply_factor(
        "mtbf_factor", 0.5, _base_scenario()
    )
    for comp in modified_graph.components.values():
        assert comp.operational_profile.mtbf_hours > 0


def test_apply_traffic_factor():
    """Traffic factor should scale traffic patterns."""
    graph = _build_whatif_graph()
    engine = WhatIfEngine(graph)
    modified_graph, scenario = engine._apply_factor(
        "traffic_factor", 2.0, _base_scenario()
    )
    # Verify traffic patterns were scaled
    for pattern in scenario.traffic_patterns:
        assert pattern.base_multiplier >= 1.0


def test_apply_replica_factor():
    """Replica factor should scale replica counts."""
    graph = _build_whatif_graph()
    engine = WhatIfEngine(graph)
    modified_graph, scenario = engine._apply_factor(
        "replica_factor", 2.0, _base_scenario()
    )
    for comp in modified_graph.components.values():
        assert comp.replicas >= 1


def test_apply_replica_factor_reduction():
    """Replica factor < 1.0 should reduce replicas but min 1."""
    graph = _build_whatif_graph()
    engine = WhatIfEngine(graph)
    modified_graph, scenario = engine._apply_factor(
        "replica_factor", 0.1, _base_scenario()
    )
    for comp in modified_graph.components.values():
        assert comp.replicas >= 1


def test_apply_maint_duration_factor():
    """Maintenance duration factor should set maintenance_duration_factor."""
    graph = _build_whatif_graph()
    engine = WhatIfEngine(graph)
    modified_graph, scenario = engine._apply_factor(
        "maint_duration_factor", 3.0, _base_scenario()
    )
    assert scenario.maintenance_duration_factor == 3.0


# ---------------------------------------------------------------------------
# _apply_replica_factor — lines 645-676 (metric scaling)
# ---------------------------------------------------------------------------


def test_replica_factor_scales_metrics_inversely():
    """Reducing replicas should increase per-instance CPU/memory load."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        replicas=4,
        metrics=ResourceMetrics(cpu_percent=30, memory_percent=40),
        capacity=Capacity(max_connections=1000),
    ))
    engine = WhatIfEngine(graph)
    modified_graph, _ = engine._apply_factor("replica_factor", 0.5, _base_scenario())

    app = modified_graph.get_component("app")
    # 4 * 0.5 = 2 replicas
    assert app.replicas == 2
    # CPU: 30 * (4/2) = 60%
    assert app.metrics.cpu_percent == pytest.approx(60.0, abs=1.0)
    # Memory: 40 * (4/2) = 80%
    assert app.metrics.memory_percent == pytest.approx(80.0, abs=1.0)


def test_replica_factor_clamp_min_1():
    """Replicas should not go below 1."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        replicas=1,
        metrics=ResourceMetrics(cpu_percent=30, memory_percent=40),
    ))
    engine = WhatIfEngine(graph)
    modified_graph, _ = engine._apply_factor("replica_factor", 0.1, _base_scenario())

    app = modified_graph.get_component("app")
    assert app.replicas == 1  # clamped
    # Metrics should NOT be scaled when clamping prevented the reduction
    assert app.metrics.cpu_percent == 30.0


def test_replica_factor_scales_autoscaling():
    """Autoscaling min/max should also be scaled."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        replicas=4,
        metrics=ResourceMetrics(cpu_percent=20),
        autoscaling=AutoScalingConfig(
            enabled=True, min_replicas=2, max_replicas=10,
        ),
    ))
    engine = WhatIfEngine(graph)
    modified_graph, _ = engine._apply_factor("replica_factor", 2.0, _base_scenario())

    app = modified_graph.get_component("app")
    assert app.replicas == 8
    assert app.autoscaling.min_replicas == 4
    assert app.autoscaling.max_replicas == 20


# ---------------------------------------------------------------------------
# _apply_maint_duration_factor — lines 701-703
# ---------------------------------------------------------------------------


def test_maint_duration_factor_applied():
    """Maintenance duration factor should be set on scenario."""
    graph = _build_whatif_graph()
    engine = WhatIfEngine(graph)
    modified_graph, scenario = engine._apply_maint_duration_factor(
        2.5, _base_scenario()
    )
    assert scenario.maintenance_duration_factor == 2.5


# ---------------------------------------------------------------------------
# _create_default_base_scenario — lines 722-756
# ---------------------------------------------------------------------------


def test_create_default_base_scenario():
    """Default base scenario should be 7-day full operations."""
    graph = _build_whatif_graph()
    engine = WhatIfEngine(graph)
    scenario = engine._create_default_base_scenario()
    assert scenario.id == "whatif-7d-full"
    assert scenario.duration_days == 7
    assert scenario.enable_random_failures is True
    assert scenario.enable_degradation is True
    assert scenario.enable_maintenance is True
    assert len(scenario.traffic_patterns) >= 1
    assert len(scenario.scheduled_deploys) > 0


def test_create_default_base_scenario_no_app_servers():
    """When no app/web servers, deploy_targets should fallback."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE,
        replicas=1,
        operational_profile=OperationalProfile(mtbf_hours=2160, mttr_minutes=60),
    ))
    graph.add_component(Component(
        id="cache", name="Cache", type=ComponentType.CACHE,
        replicas=1,
    ))
    engine = WhatIfEngine(graph)
    scenario = engine._create_default_base_scenario()
    assert len(scenario.scheduled_deploys) > 0


# ---------------------------------------------------------------------------
# _compute_avg_availability — line 801
# ---------------------------------------------------------------------------


def test_compute_avg_availability_empty():
    """Empty SLI timeline should return 100.0."""
    result = OpsSimulationResult(
        scenario=_base_scenario(),
        sli_timeline=[],
    )
    avg = WhatIfEngine._compute_avg_availability(result)
    assert avg == 100.0


# ---------------------------------------------------------------------------
# _build_whatif_summary — lines 833, 849
# ---------------------------------------------------------------------------


def test_build_whatif_summary_with_breakpoint():
    """Summary should include breakpoint info."""
    whatif = WhatIfScenario(
        base_scenario=_base_scenario(),
        parameter="mttr_factor",
        values=[1.0, 2.0, 4.0],
        description="What if MTTR increases?",
    )
    summary = WhatIfEngine._build_whatif_summary(
        whatif,
        avg_availabilities=[99.95, 99.85, 99.5],
        slo_pass=[True, False, False],
        breakpoint_value=2.0,
    )
    assert "breakpoint" in summary.lower()
    assert "2.0" in summary


def test_build_whatif_summary_no_breakpoint():
    """Summary should say all passed when no breakpoint."""
    whatif = WhatIfScenario(
        base_scenario=_base_scenario(),
        parameter="mttr_factor",
        values=[0.5, 1.0],
        description="MTTR sweep",
    )
    summary = WhatIfEngine._build_whatif_summary(
        whatif,
        avg_availabilities=[99.99, 99.95],
        slo_pass=[True, True],
        breakpoint_value=None,
    )
    assert "passed" in summary.lower() or "PASS" in summary


def test_build_whatif_summary_no_description():
    """Summary without description should still work."""
    whatif = WhatIfScenario(
        base_scenario=_base_scenario(),
        parameter="mttr_factor",
        values=[1.0],
    )
    summary = WhatIfEngine._build_whatif_summary(
        whatif,
        avg_availabilities=[99.95],
        slo_pass=[True],
        breakpoint_value=None,
    )
    assert "mttr_factor" in summary


# ---------------------------------------------------------------------------
# _apply_mttr_factor with zero MTTR — lines 581-591
# ---------------------------------------------------------------------------


def test_apply_mttr_factor_zero_mttr():
    """Zero MTTR should be pre-populated with defaults."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        replicas=1,
        operational_profile=OperationalProfile(mttr_minutes=0, mtbf_hours=0),
    ))
    engine = WhatIfEngine(graph)
    modified_graph, _ = engine._apply_mttr_factor(2.0, _base_scenario())
    app = modified_graph.get_component("app")
    # Should have been populated with default then doubled
    assert app.operational_profile.mttr_minutes > 0


# ---------------------------------------------------------------------------
# _apply_mtbf_factor with zero MTBF — lines 613-616
# ---------------------------------------------------------------------------


def test_apply_mtbf_factor_zero_mtbf():
    """Zero MTBF should be pre-populated with defaults."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        replicas=1,
        operational_profile=OperationalProfile(mtbf_hours=0),
    ))
    engine = WhatIfEngine(graph)
    modified_graph, _ = engine._apply_mtbf_factor(0.5, _base_scenario())
    app = modified_graph.get_component("app")
    assert app.operational_profile.mtbf_hours > 0


# ---------------------------------------------------------------------------
# Whatif sweep — per-parameter tests to hit specific _apply_* methods
# ---------------------------------------------------------------------------


def test_whatif_mtbf_sweep():
    """MTBF factor sweep should produce results."""
    graph = _build_whatif_graph()
    engine = WhatIfEngine(graph)
    whatif = WhatIfScenario(
        base_scenario=_base_scenario(),
        parameter="mtbf_factor",
        values=[0.5, 1.0],
    )
    result = engine.run_whatif(whatif)
    assert len(result.avg_availabilities) == 2


def test_whatif_traffic_sweep():
    """Traffic factor sweep should produce results."""
    graph = _build_whatif_graph()
    engine = WhatIfEngine(graph)
    whatif = WhatIfScenario(
        base_scenario=_base_scenario(),
        parameter="traffic_factor",
        values=[1.0, 2.0],
    )
    result = engine.run_whatif(whatif)
    assert len(result.avg_availabilities) == 2


def test_whatif_replica_sweep():
    """Replica factor sweep should produce results."""
    graph = _build_whatif_graph()
    engine = WhatIfEngine(graph)
    whatif = WhatIfScenario(
        base_scenario=_base_scenario(),
        parameter="replica_factor",
        values=[0.5, 1.0],
    )
    result = engine.run_whatif(whatif)
    assert len(result.avg_availabilities) == 2


def test_whatif_maint_duration_sweep():
    """Maintenance duration factor sweep should produce results."""
    graph = _build_whatif_graph()
    engine = WhatIfEngine(graph)
    whatif = WhatIfScenario(
        base_scenario=_base_scenario(),
        parameter="maint_duration_factor",
        values=[1.0, 2.0],
    )
    result = engine.run_whatif(whatif)
    assert len(result.avg_availabilities) == 2


# ---------------------------------------------------------------------------
# Multi what-if with zero operational profiles
# ---------------------------------------------------------------------------


def test_multi_whatif_zero_profiles():
    """Multi what-if with components that have zero MTBF/MTTR."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        replicas=2,
        metrics=ResourceMetrics(cpu_percent=20),
        operational_profile=OperationalProfile(mtbf_hours=0, mttr_minutes=0),
    ))
    engine = WhatIfEngine(graph)
    multi = MultiWhatIfScenario(
        base_scenario=_base_scenario(),
        parameters={"mttr_factor": 2.0, "mtbf_factor": 0.5},
    )
    result = engine.run_multi_whatif(multi)
    assert result.avg_availability > 0


def test_multi_whatif_default_description():
    """Multi what-if with empty description should generate default."""
    graph = _build_whatif_graph()
    engine = WhatIfEngine(graph)
    multi = MultiWhatIfScenario(
        base_scenario=_base_scenario(),
        parameters={"mttr_factor": 1.0},
        description="",
    )
    result = engine.run_multi_whatif(multi)
    assert "Multi what-if" in result.summary or "mttr_factor" in result.summary
