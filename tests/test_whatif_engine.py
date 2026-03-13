"""Tests for what-if analysis engine."""

from infrasim.model.components import (
    Capacity,
    Component,
    ComponentType,
    Dependency,
    OperationalProfile,
    ResourceMetrics,
    SLOTarget,
)
from infrasim.model.graph import InfraGraph
from infrasim.simulator.ops_engine import OpsScenario, TimeUnit
from infrasim.simulator.traffic import create_diurnal_weekly
from infrasim.simulator.whatif_engine import (
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
