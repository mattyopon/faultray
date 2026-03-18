"""Property-based tests using Hypothesis for FaultRay."""
from __future__ import annotations

import tempfile
from pathlib import Path

from hypothesis import given, settings, strategies as st
import pytest

from faultray.model.components import Component, ComponentType, Dependency, SCHEMA_VERSION
from faultray.model.graph import InfraGraph
from faultray.simulator.engine import SimulationEngine, SimulationReport
from faultray.simulator.scenarios import Scenario, Fault, FaultType, generate_default_scenarios


# ---------------------------------------------------------------------------
# Property: Every ComponentType value must be a valid non-empty string
# ---------------------------------------------------------------------------
@given(ct=st.sampled_from(list(ComponentType)))
def test_component_type_is_string(ct: ComponentType) -> None:
    assert isinstance(ct.value, str)
    assert len(ct.value) > 0


# ---------------------------------------------------------------------------
# Property: SCHEMA_VERSION is a valid dot-separated numeric string
# ---------------------------------------------------------------------------
def test_schema_version_format() -> None:
    parts = SCHEMA_VERSION.split(".")
    assert len(parts) >= 1
    assert all(p.isdigit() for p in parts)


# ---------------------------------------------------------------------------
# InfraGraph invariants
# ---------------------------------------------------------------------------
_component_type_st = st.sampled_from(list(ComponentType))


@st.composite
def component_strategy(draw: st.DrawFn) -> Component:
    """Generate a random Component with a unique id."""
    cid = draw(st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789", min_size=1, max_size=12))
    ctype = draw(_component_type_st)
    replicas = draw(st.integers(min_value=1, max_value=10))
    return Component(id=cid, name=f"comp-{cid}", type=ctype, replicas=replicas)


@given(components=st.lists(component_strategy(), min_size=1, max_size=10))
@settings(max_examples=30)
def test_infragraph_add_components_maintains_invariants(
    components: list[Component],
) -> None:
    """Adding components to InfraGraph always keeps component count consistent."""
    graph = InfraGraph()
    unique_ids: set[str] = set()
    for comp in components:
        graph.add_component(comp)
        unique_ids.add(comp.id)

    # Component count equals number of unique IDs added
    assert len(graph.components) == len(unique_ids)
    # Every added component is retrievable
    for cid in unique_ids:
        assert graph.get_component(cid) is not None


@given(
    comp_a=component_strategy(),
    comp_b=component_strategy(),
)
@settings(max_examples=30)
def test_infragraph_dependency_preserves_components(
    comp_a: Component,
    comp_b: Component,
) -> None:
    """Adding a dependency never removes components from the graph."""
    # Ensure distinct ids
    if comp_a.id == comp_b.id:
        comp_b = comp_b.model_copy(update={"id": comp_b.id + "_2"})

    graph = InfraGraph()
    graph.add_component(comp_a)
    graph.add_component(comp_b)

    dep = Dependency(source_id=comp_a.id, target_id=comp_b.id)
    graph.add_dependency(dep)

    assert len(graph.components) == 2
    assert graph.get_dependency_edge(comp_a.id, comp_b.id) is not None


# ---------------------------------------------------------------------------
# SimulationEngine: result counts always sum to total
# ---------------------------------------------------------------------------
@given(
    num_components=st.integers(min_value=1, max_value=5),
)
@settings(max_examples=10, deadline=None)
def test_simulation_result_counts_sum_to_total(num_components: int) -> None:
    """critical + warnings + passed always equals total results."""
    graph = InfraGraph()
    ids = []
    for i in range(num_components):
        cid = f"comp-{i}"
        ids.append(cid)
        graph.add_component(
            Component(id=cid, name=cid, type=ComponentType.APP_SERVER)
        )

    engine = SimulationEngine(graph)
    # Use a small subset of scenarios to keep test fast
    scenarios = [
        Scenario(
            id=f"test-{cid}",
            name=f"Test {cid}",
            description=f"Test failure of {cid}",
            faults=[Fault(target_component_id=cid, fault_type=FaultType.COMPONENT_DOWN)],
        )
        for cid in ids
    ]
    report = engine.run_scenarios(scenarios)

    total = len(report.results)
    critical_count = len(report.critical_findings)
    warning_count = len(report.warnings)
    passed_count = len(report.passed)
    assert critical_count + warning_count + passed_count == total


# ---------------------------------------------------------------------------
# Scenarios: generated scenarios always have non-empty fault lists or traffic
# ---------------------------------------------------------------------------
@given(
    num_components=st.integers(min_value=1, max_value=4),
)
@settings(max_examples=10, deadline=None)
def test_generated_scenarios_have_faults_or_traffic(num_components: int) -> None:
    """Every generated scenario has at least one fault or a non-default traffic multiplier."""
    ids = [f"c{i}" for i in range(num_components)]
    scenarios = generate_default_scenarios(ids)
    assert len(scenarios) > 0
    for s in scenarios:
        assert len(s.faults) > 0 or s.traffic_multiplier != 1.0, (
            f"Scenario {s.id} has no faults and default traffic"
        )


# ---------------------------------------------------------------------------
# Loader roundtrip: save(graph) -> load preserves component count
# ---------------------------------------------------------------------------
@given(
    num_components=st.integers(min_value=1, max_value=6),
)
@settings(max_examples=10)
def test_graph_save_load_roundtrip_preserves_count(num_components: int) -> None:
    """Saving an InfraGraph to JSON and loading it back preserves the component count."""
    graph = InfraGraph()
    for i in range(num_components):
        cid = f"rt-{i}"
        graph.add_component(
            Component(id=cid, name=cid, type=ComponentType.DATABASE)
        )

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        tmp_path = Path(f.name)

    try:
        graph.save(tmp_path)
        loaded = InfraGraph.load(tmp_path)
        assert len(loaded.components) == len(graph.components)
        for cid in graph.components:
            assert cid in loaded.components
    finally:
        tmp_path.unlink(missing_ok=True)
