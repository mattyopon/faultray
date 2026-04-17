"""Extended property-based tests for simulator and reporter layers.

Covers invariants for:
- Resilience score bounds
- Component/dependency monotonicity
- Simulation scenario counts
- DORA/Governance compliance rate bounds
- Cascade path length
- SPOF detection correctness
"""
# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

from __future__ import annotations

from hypothesis import given, settings, strategies as st

from faultray.model.components import Component, ComponentType, Dependency
from faultray.model.graph import InfraGraph
from faultray.simulator.engine import SimulationEngine
from faultray.simulator.scenarios import Fault, FaultType, Scenario, generate_default_scenarios


# ---------------------------------------------------------------------------
# Shared strategies
# ---------------------------------------------------------------------------

_COMPONENT_TYPE_ST = st.sampled_from(list(ComponentType))


@st.composite
def _component_st(draw: st.DrawFn, cid: str | None = None) -> Component:
    """Generate a random Component with a unique id."""
    comp_id = cid or draw(
        st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789", min_size=1, max_size=12)
    )
    ctype = draw(_COMPONENT_TYPE_ST)
    replicas = draw(st.integers(min_value=1, max_value=20))
    return Component(id=comp_id, name=f"comp-{comp_id}", type=ctype, replicas=replicas)


def _build_graph(n_components: int, replicas: int = 2) -> InfraGraph:
    """Build a simple linear chain graph with *n_components* nodes."""
    graph = InfraGraph()
    ids = [f"c{i}" for i in range(n_components)]
    for cid in ids:
        graph.add_component(
            Component(id=cid, name=cid, type=ComponentType.APP_SERVER, replicas=replicas)
        )
    # Add linear chain dependencies: c0 -> c1 -> c2 -> ...
    for i in range(n_components - 1):
        graph.add_dependency(
            Dependency(source_id=ids[i], target_id=ids[i + 1])
        )
    return graph


# ---------------------------------------------------------------------------
# Property 1: Resilience score is always in [0, 100]
# ---------------------------------------------------------------------------

@given(replicas=st.integers(min_value=1, max_value=100))
@settings(max_examples=40, deadline=None)
def test_resilience_score_always_bounded(replicas: int) -> None:
    """Resilience score must always be between 0 and 100 regardless of replicas."""
    graph = _build_graph(n_components=3, replicas=replicas)
    score = graph.resilience_score()
    assert 0.0 <= score <= 100.0, (
        f"resilience_score()={score} is outside [0, 100] for replicas={replicas}"
    )


@given(n_components=st.integers(min_value=1, max_value=30))
@settings(max_examples=30, deadline=None)
def test_resilience_score_bounded_for_varied_topology(n_components: int) -> None:
    """Score is in [0, 100] for any number of components in a chain."""
    graph = _build_graph(n_components=n_components, replicas=1)
    score = graph.resilience_score()
    assert 0.0 <= score <= 100.0, (
        f"resilience_score()={score} out of bounds for n_components={n_components}"
    )


# ---------------------------------------------------------------------------
# Property 2: Adding components never produces a negative score
# ---------------------------------------------------------------------------

@given(n_components=st.integers(min_value=1, max_value=50))
@settings(max_examples=30, deadline=None)
def test_adding_components_never_negative_score(n_components: int) -> None:
    """Adding any number of components should never result in a negative score."""
    graph = InfraGraph()
    for i in range(n_components):
        graph.add_component(
            Component(id=f"c{i}", name=f"c{i}", type=ComponentType.APP_SERVER, replicas=1)
        )
        score = graph.resilience_score()
        assert score >= 0.0, (
            f"Negative score {score} after adding component #{i + 1}"
        )


# ---------------------------------------------------------------------------
# Property 3: Adding required dependencies does not increase the score
#             (monotonicity: more coupling = equal or lower resilience)
# ---------------------------------------------------------------------------

@given(n_extra_deps=st.integers(min_value=0, max_value=5))
@settings(max_examples=20, deadline=None)
def test_adding_required_deps_does_not_improve_score(n_extra_deps: int) -> None:
    """Adding hard 'requires' dependencies to a hub component should not improve score."""
    # Base graph: one hub with replicas=1 and a downstream node
    graph = InfraGraph()
    graph.add_component(Component(id="hub", name="hub", type=ComponentType.APP_SERVER, replicas=1))
    graph.add_component(Component(id="leaf", name="leaf", type=ComponentType.DATABASE, replicas=2))
    graph.add_dependency(Dependency(source_id="leaf", target_id="hub"))
    base_score = graph.resilience_score()

    # Add extra downstream dependents on hub (increasing SPOF impact)
    for i in range(n_extra_deps):
        extra_id = f"extra-{i}"
        graph.add_component(
            Component(id=extra_id, name=extra_id, type=ComponentType.APP_SERVER, replicas=2)
        )
        graph.add_dependency(
            Dependency(source_id=extra_id, target_id="hub", dependency_type="requires")
        )

    new_score = graph.resilience_score()
    # Score should not improve when we add more required dependents on a SPOF
    assert new_score <= base_score + 0.01, (
        f"Score improved from {base_score} to {new_score} after adding {n_extra_deps} required deps — "
        "expected monotonic non-improvement for SPOF with more dependents"
    )


# ---------------------------------------------------------------------------
# Property 4: Simulation always produces at least one scenario result
# ---------------------------------------------------------------------------

@given(n=st.integers(min_value=1, max_value=20))
@settings(max_examples=20, deadline=None)
def test_simulation_always_produces_scenarios(n: int) -> None:
    """Simulation should always produce at least one scenario result."""
    ids = [f"c{i}" for i in range(n)]
    scenarios = generate_default_scenarios(ids)
    assert len(scenarios) > 0, (
        f"generate_default_scenarios returned 0 scenarios for {n} component ids"
    )


@given(n_components=st.integers(min_value=1, max_value=6))
@settings(max_examples=10, deadline=None)
def test_run_scenarios_returns_results_for_all_inputs(n_components: int) -> None:
    """SimulationEngine.run_scenarios returns a report for every scenario submitted."""
    graph = _build_graph(n_components=n_components, replicas=2)
    ids = list(graph.components.keys())
    scenarios = [
        Scenario(
            id=f"s-{cid}",
            name=f"Fail {cid}",
            description=f"Test failure of {cid}",
            faults=[Fault(target_component_id=cid, fault_type=FaultType.COMPONENT_DOWN)],
        )
        for cid in ids
    ]
    engine = SimulationEngine(graph)
    report = engine.run_scenarios(scenarios)

    assert len(report.results) == len(scenarios), (
        f"Expected {len(scenarios)} results, got {len(report.results)}"
    )


# ---------------------------------------------------------------------------
# Property 5: DORA / Governance compliance rate is 0-100%
# ---------------------------------------------------------------------------

@given(
    answers=st.dictionaries(
        keys=st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_", min_size=3, max_size=10),
        values=st.integers(min_value=0, max_value=4),
        min_size=0,
        max_size=30,
    )
)
@settings(max_examples=30, deadline=None)
def test_governance_overall_score_bounded(answers: dict[str, int]) -> None:
    """GovernanceAssessor.assess().overall_score is always in [0, 100]."""
    from faultray.governance.assessor import GovernanceAssessor

    assessor = GovernanceAssessor()
    result = assessor.assess(answers)
    assert 0.0 <= result.overall_score <= 100.0, (
        f"overall_score={result.overall_score} outside [0, 100]"
    )


@given(
    answers=st.dictionaries(
        keys=st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_", min_size=3, max_size=10),
        values=st.integers(min_value=0, max_value=4),
        min_size=0,
        max_size=30,
    )
)
@settings(max_examples=20, deadline=None)
def test_governance_category_scores_bounded(answers: dict[str, int]) -> None:
    """Every category score returned by GovernanceAssessor is in [0, 100]."""
    from faultray.governance.assessor import GovernanceAssessor

    assessor = GovernanceAssessor()
    result = assessor.assess(answers)
    for cat in result.category_scores:
        assert 0.0 <= cat.score_percent <= 100.0, (
            f"Category '{cat.category_id}' score_percent={cat.score_percent} outside [0, 100]"
        )


# ---------------------------------------------------------------------------
# Property 6: Cascade path length never exceeds total component count
# ---------------------------------------------------------------------------

@given(n_components=st.integers(min_value=2, max_value=20))
@settings(max_examples=20, deadline=None)
def test_cascade_path_length_bounded_by_component_count(n_components: int) -> None:
    """No cascade path can be longer than the total number of components."""
    graph = _build_graph(n_components=n_components, replicas=1)
    total = len(graph.components)

    for cid in graph.components:
        paths = graph.get_cascade_path(cid)
        for path in paths:
            assert len(path) <= total, (
                f"Cascade path from '{cid}' has length {len(path)} > total components {total}: {path}"
            )


@given(n_components=st.integers(min_value=2, max_value=15))
@settings(max_examples=20, deadline=None)
def test_critical_paths_bounded_by_component_count(n_components: int) -> None:
    """Critical (longest dependency chain) paths are bounded by component count."""
    graph = _build_graph(n_components=n_components, replicas=1)
    total = len(graph.components)

    critical_paths = graph.get_critical_paths()
    for path in critical_paths:
        assert len(path) <= total, (
            f"Critical path length {len(path)} > total components {total}: {path}"
        )


# ---------------------------------------------------------------------------
# Property 7: SPOFs are only components with replicas=1 that have dependents
# ---------------------------------------------------------------------------

@given(
    components=st.lists(
        st.builds(
            Component,
            id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=8),
            name=st.just("comp"),
            type=st.just(ComponentType.APP_SERVER),
            replicas=st.integers(min_value=1, max_value=5),
        ),
        min_size=2,
        max_size=10,
        unique_by=lambda c: c.id,
    )
)
@settings(max_examples=30, deadline=None)
def test_spof_only_for_replicas_one_with_dependents(components: list[Component]) -> None:
    """A component is a SPOF only if replicas==1 AND it has at least one dependent."""
    graph = InfraGraph()
    for comp in components:
        graph.add_component(comp)

    # Add dependencies: each component depends on the next (linear chain)
    ids = [c.id for c in components]
    for i in range(len(ids) - 1):
        graph.add_dependency(
            Dependency(source_id=ids[i], target_id=ids[i + 1], dependency_type="requires")
        )

    # Verify SPOF definition: replicas==1 AND has dependents
    for comp in components:
        dependents = graph.get_dependents(comp.id)
        is_potential_spof = comp.replicas <= 1 and len(dependents) > 0

        if not is_potential_spof:
            # If not a potential SPOF (replicas > 1 OR no dependents),
            # resilience_score should NOT apply a SPOF penalty for this component.
            # We verify this indirectly: increasing replicas to >=2 should not *raise* the
            # penalty. Build a twin graph with this component at replicas=2.
            twin = InfraGraph()
            for c in components:
                r = 2 if c.id == comp.id else c.replicas
                twin.add_component(
                    Component(id=c.id, name=c.name, type=c.type, replicas=r)
                )
            for i in range(len(ids) - 1):
                twin.add_dependency(
                    Dependency(source_id=ids[i], target_id=ids[i + 1], dependency_type="requires")
                )

            original_score = graph.resilience_score()
            twin_score = twin.resilience_score()
            # If original has this component at replicas>1, score should be the same or better
            if comp.replicas > 1:
                assert twin_score <= original_score + 0.01, (
                    f"Unexpected score change: original={original_score}, twin={twin_score} "
                    f"for component '{comp.id}' replicas={comp.replicas}"
                )


@given(replicas=st.integers(min_value=1, max_value=10))
@settings(max_examples=20, deadline=None)
def test_single_component_replicas_one_is_spof_candidate(replicas: int) -> None:
    """With two components where hub has replicas=1, it is a SPOF; replicas>1 reduces penalty."""
    graph_low = InfraGraph()
    graph_low.add_component(Component(id="hub", name="hub", type=ComponentType.APP_SERVER, replicas=1))
    graph_low.add_component(Component(id="dep", name="dep", type=ComponentType.DATABASE, replicas=2))
    graph_low.add_dependency(Dependency(source_id="dep", target_id="hub", dependency_type="requires"))

    graph_high = InfraGraph()
    graph_high.add_component(Component(id="hub", name="hub", type=ComponentType.APP_SERVER, replicas=replicas))
    graph_high.add_component(Component(id="dep", name="dep", type=ComponentType.DATABASE, replicas=2))
    graph_high.add_dependency(Dependency(source_id="dep", target_id="hub", dependency_type="requires"))

    score_low = graph_low.resilience_score()
    score_high = graph_high.resilience_score()

    if replicas > 1:
        # More replicas → hub is no longer a SPOF → equal or better score
        assert score_high >= score_low, (
            f"score with replicas={replicas} ({score_high}) < score with replicas=1 ({score_low})"
        )


# ---------------------------------------------------------------------------
# Property 8: ScenarioResult counts always sum to total
# (extended from test_property_based.py with different graph topologies)
# ---------------------------------------------------------------------------

@given(
    n_components=st.integers(min_value=1, max_value=8),
    replicas=st.integers(min_value=1, max_value=4),
)
@settings(max_examples=15, deadline=None)
def test_result_counts_sum_to_total_varied_topology(n_components: int, replicas: int) -> None:
    """critical + warning + passed always equals total for varied graph topologies."""
    graph = _build_graph(n_components=n_components, replicas=replicas)
    ids = list(graph.components.keys())
    scenarios = [
        Scenario(
            id=f"s-{cid}",
            name=f"Fail {cid}",
            description=f"Test failure of {cid}",
            faults=[Fault(target_component_id=cid, fault_type=FaultType.COMPONENT_DOWN)],
        )
        for cid in ids
    ]
    engine = SimulationEngine(graph)
    report = engine.run_scenarios(scenarios)

    total = len(report.results)
    count_c = len(report.critical_findings)
    count_w = len(report.warnings)
    count_p = len(report.passed)
    assert count_c + count_w + count_p == total, (
        f"critical({count_c}) + warning({count_w}) + passed({count_p}) != total({total})"
    )


# ---------------------------------------------------------------------------
# Property 9: Resilience score v2 breakdown components are all in [0, 100]
# ---------------------------------------------------------------------------

@given(n_components=st.integers(min_value=1, max_value=15))
@settings(max_examples=20, deadline=None)
def test_resilience_score_v2_bounded(n_components: int) -> None:
    """All components of resilience_score_v2 breakdown are in [0, 100]."""
    graph = _build_graph(n_components=n_components, replicas=1)
    result = graph.resilience_score_v2()

    score = result["score"]
    assert isinstance(score, float)
    assert 0.0 <= score <= 100.0, f"resilience_score_v2 score={score} out of [0, 100]"

    breakdown = result.get("breakdown", {})
    for key, val in breakdown.items():
        assert isinstance(val, (int, float)), f"Breakdown '{key}' value is not numeric: {val}"
        assert 0.0 <= float(val) <= 100.0, (
            f"Breakdown '{key}'={val} is outside [0, 100]"
        )
