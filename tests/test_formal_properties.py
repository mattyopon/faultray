# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Property-based verification of the FaultRay cascade formal model.

The FaultRay paper differentiates itself on *formal guarantees* about the
cascade transition system (Termination, Monotonicity, Causality, Attenuation)
and on a 5-layer availability model whose values must stay within [0, 1].

These properties were previously only argued in proof sketches, and the
implementation had drifted from them at least twice (Rule 3 replica handling
was missing; Rule 6 circuit-breaker trips could *improve* an already-worse
component, violating Monotonicity). This module turns the theorems into
executable invariants checked over randomly generated topologies so the same
class of regression cannot recur silently.

Each test names the paper property it pins down.
"""

from __future__ import annotations

import random

from hypothesis import given, settings
from hypothesis import strategies as st

from faultray.model.components import (
    Component,
    ComponentType,
    Dependency,
    HealthStatus,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.availability_model import compute_five_layer_model
from faultray.simulator.cascade import CascadeEngine, Fault, FaultType

_HEALTH_RANK = {
    HealthStatus.HEALTHY: 0,
    HealthStatus.DEGRADED: 1,
    HealthStatus.OVERLOADED: 2,
    HealthStatus.DOWN: 3,
}

# Component types that the cascade model treats as ordinary topology nodes.
_TYPES = [
    ComponentType.LOAD_BALANCER,
    ComponentType.WEB_SERVER,
    ComponentType.APP_SERVER,
    ComponentType.DATABASE,
    ComponentType.CACHE,
    ComponentType.QUEUE,
    ComponentType.STORAGE,
]
_DEP_TYPES = ("requires", "optional", "async")


def _random_graph(
    seed: int,
    n: int,
    edge_types: tuple[str, ...] = _DEP_TYPES,
    allow_cycles: bool = False,
    insertion_order: list[int] | None = None,
) -> tuple[InfraGraph, list[str]]:
    """Build a deterministic pseudo-random graph from *seed*.

    With ``allow_cycles=False`` only forward edges (i -> j, i < j) are added,
    yielding a DAG. ``insertion_order`` controls the order components are added
    to the graph (used to probe order-independence); edges are always added in
    the same logical order so two graphs differing only in insertion order are
    semantically identical.
    """
    rng = random.Random(seed)
    ids = [f"c{i}" for i in range(n)]
    # Decide each component's attributes up front so insertion order cannot
    # change the component set, only the order of add_component calls.
    attrs = {
        cid: (rng.choice(_TYPES), rng.randint(1, 4))
        for cid in ids
    }
    # Decide edges up front too (stable regardless of insertion order).
    edges: list[tuple[str, str, str, float]] = []
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            if not allow_cycles and j <= i:
                continue
            if rng.random() < 0.35:
                etype = rng.choice(edge_types)
                weight = rng.choice([0.05, 0.5, 1.0])
                edges.append((ids[i], ids[j], etype, weight))

    g = InfraGraph()
    order = insertion_order if insertion_order is not None else list(range(n))
    for idx in order:
        cid = ids[idx]
        ctype, replicas = attrs[cid]
        g.add_component(Component(id=cid, name=cid, type=ctype, replicas=replicas))
    for src, tgt, etype, weight in edges:
        g.add_dependency(
            Dependency(source_id=src, target_id=tgt, dependency_type=etype, weight=weight)
        )
    return g, ids


def _affected(graph: InfraGraph, target: str):
    chain = CascadeEngine(graph).simulate_fault(
        Fault(target_component_id=target, fault_type=FaultType.COMPONENT_DOWN)
    )
    return chain


# ---------------------------------------------------------------------------
# Theorem 1 — Termination
# ---------------------------------------------------------------------------
@given(seed=st.integers(0, 1 << 30), n=st.integers(2, 12))
@settings(max_examples=60, deadline=None)
def test_termination_on_arbitrary_cyclic_graph(seed: int, n: int) -> None:
    """The cascade always halts and records each component at most once.

    Even with cycles, the worst-health merge plus the D_max bound guarantee
    termination, so the effect list can never exceed the component count and
    cannot contain duplicates.
    """
    graph, ids = _random_graph(seed, n, allow_cycles=True)
    chain = _affected(graph, ids[seed % n])

    seen = [e.component_id for e in chain.effects]
    assert len(seen) <= len(ids)
    assert len(seen) == len(set(seen)), "a component was recorded twice (non-termination)"


# ---------------------------------------------------------------------------
# Soundness — no spontaneous health, target is down
# ---------------------------------------------------------------------------
@given(seed=st.integers(0, 1 << 30), n=st.integers(2, 12))
@settings(max_examples=60, deadline=None)
def test_effects_are_non_healthy_and_target_is_down(seed: int, n: int) -> None:
    """Cascade only ever records degraded-or-worse states, and the injected
    target ends DOWN. A HEALTHY entry would mean the engine emitted a
    non-effect; a non-DOWN target would mean the injected fault was lost.

    (Rule 6 monotonicity — a circuit-breaker trip must not *improve* an
    already-OVERLOADED/DOWN component — is pinned by the targeted example
    tests in ``test_cascade.py`` around the "Rule 6 + Monotonicity" cases.)
    """
    graph, ids = _random_graph(seed, n, allow_cycles=True)
    target = ids[seed % n]
    chain = _affected(graph, target)

    by_id = {e.component_id: e.health for e in chain.effects}
    for health in by_id.values():
        assert _HEALTH_RANK[health] >= _HEALTH_RANK[HealthStatus.DEGRADED]
    assert by_id.get(target) == HealthStatus.DOWN


# ---------------------------------------------------------------------------
# Monotonicity in coupling — strengthening a dependency never improves resilience
# ---------------------------------------------------------------------------
@given(seed=st.integers(0, 1 << 30), n=st.integers(3, 12))
@settings(max_examples=60, deadline=None)
def test_strengthening_a_dependency_never_reduces_blast_radius(
    seed: int, n: int
) -> None:
    """Promoting one soft edge (optional/async) to a hard ``requires`` edge can
    only spread or intensify a cascade — never shrink it. This is the
    operational form of the paper's coupling-monotonicity claim and catches
    rule changes that would let a stronger dependency attenuate more than a
    weaker one.
    """
    base, ids = _random_graph(
        seed, n, edge_types=("optional", "async"), allow_cycles=False
    )
    # Find a soft edge to promote.
    soft_edges = [
        (d.source_id, d.target_id) for d in base.all_dependency_edges()
    ]
    if not soft_edges:
        return  # vacuous for this example; the strategy yields plenty with edges
    src, tgt = soft_edges[seed % len(soft_edges)]

    # Rebuild an identical graph but with that one edge hard-required.
    strong, _ = _random_graph(
        seed, n, edge_types=("optional", "async"), allow_cycles=False
    )
    strong.remove_dependency(src, tgt)
    strong.add_dependency(
        Dependency(source_id=src, target_id=tgt, dependency_type="requires", weight=1.0)
    )

    target = ids[seed % n]
    base_health = {e.component_id: e.health for e in _affected(base, target).effects}
    strong_health = {e.component_id: e.health for e in _affected(strong, target).effects}

    # Affected set only grows; shared components are equal-or-worse.
    assert set(base_health) <= set(strong_health), (
        "strengthening a dependency dropped a previously-affected component"
    )
    for cid, h in base_health.items():
        assert _HEALTH_RANK[strong_health[cid]] >= _HEALTH_RANK[h], (
            f"{cid} improved from {h} to {strong_health[cid]} after a dependency "
            "was strengthened"
        )


# ---------------------------------------------------------------------------
# Theorem 4 — Causality
# ---------------------------------------------------------------------------
@given(seed=st.integers(0, 1 << 30), n=st.integers(2, 12))
@settings(max_examples=60, deadline=None)
def test_causality_no_spontaneous_failures(seed: int, n: int) -> None:
    """Every affected component (other than the target) depends on something
    that is itself affected — failures never appear out of nowhere.
    """
    graph, ids = _random_graph(seed, n, allow_cycles=False)
    target = ids[seed % n]
    chain = _affected(graph, target)

    affected = {e.component_id for e in chain.effects}
    for cid in affected:
        if cid == target:
            continue
        deps = [d.id for d in graph.get_dependencies(cid)]
        assert any(
            d in affected for d in deps
        ), f"{cid} is affected but none of its dependencies {deps} are"


# ---------------------------------------------------------------------------
# Theorem 6 — Attenuation (bounded blast radius via soft edges)
# ---------------------------------------------------------------------------
@given(seed=st.integers(0, 1 << 30), n=st.integers(2, 14))
@settings(max_examples=60, deadline=None)
def test_attenuation_optional_async_never_hard_fail(seed: int, n: int) -> None:
    """With only optional/async edges, a single fault degrades but never hard-
    fails anything downstream: every non-target effect is exactly DEGRADED and
    no second hop occurs (DEGRADED does not propagate)."""
    graph, ids = _random_graph(
        seed, n, edge_types=("optional", "async"), allow_cycles=False
    )
    target = ids[seed % n]
    chain = _affected(graph, target)

    direct_dependents = {d.id for d in graph.get_dependents(target)}
    for e in chain.effects:
        if e.component_id == target:
            continue
        assert e.health == HealthStatus.DEGRADED, (
            f"{e.component_id} reached {e.health} via a soft edge — "
            "optional/async must only ever degrade"
        )
        assert e.component_id in direct_dependents, (
            f"{e.component_id} was affected but is not a direct dependent of the "
            "target — DEGRADED must not propagate (Attenuation)"
        )


# ---------------------------------------------------------------------------
# Determinism (reproducibility) — order independence
# ---------------------------------------------------------------------------
@given(seed=st.integers(0, 1 << 30), n=st.integers(2, 12))
@settings(max_examples=40, deadline=None)
def test_cascade_is_insertion_order_independent(seed: int, n: int) -> None:
    """The same logical topology yields identical results regardless of the
    order components were added — both the final per-component health AND the
    order of the effect list must match (the paper claims reproducibility)."""
    rng = random.Random(seed ^ 0xA5A5)
    shuffled = list(range(n))
    rng.shuffle(shuffled)

    g1, ids = _random_graph(seed, n, allow_cycles=True)
    g2, _ = _random_graph(seed, n, allow_cycles=True, insertion_order=shuffled)
    target = ids[seed % n]

    c1 = _affected(g1, target)
    c2 = _affected(g2, target)

    assert [(e.component_id, e.health) for e in c1.effects] == [
        (e.component_id, e.health) for e in c2.effects
    ]


# ---------------------------------------------------------------------------
# H9 — Availability layers are always within [0, 1]
# ---------------------------------------------------------------------------
@given(
    seed=st.integers(0, 1 << 30),
    n=st.integers(1, 10),
    incidents=st.floats(min_value=0.0, max_value=5000.0),
    response_min=st.floats(min_value=0.0, max_value=2000.0),
    coverage=st.floats(min_value=1.0, max_value=100.0),
)
@settings(max_examples=60, deadline=None)
def test_availability_layers_within_unit_interval(
    seed: int, n: int, incidents: float, response_min: float, coverage: float
) -> None:
    """Every availability layer stays in [0, 1] even for pathological inputs.

    Without clamping, Layer 4 (1 - incidents*response/8760) goes negative for
    high incident counts and low coverage; this pins the H9 fix.
    """
    graph, _ = _random_graph(seed, n, allow_cycles=False)
    result = compute_five_layer_model(
        graph,
        incidents_per_year=incidents,
        mean_response_minutes=response_min,
        oncall_coverage_percent=coverage,
    )
    for layer in (
        result.layer1_software,
        result.layer2_hardware,
        result.layer3_theoretical,
        result.layer4_operational,
        result.layer5_external,
    ):
        assert 0.0 <= layer.availability <= 1.0, (
            f"{layer.description}: availability {layer.availability} out of [0,1]"
        )
        assert layer.nines >= 0.0
        assert layer.annual_downtime_seconds >= 0.0
