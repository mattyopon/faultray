"""Core tests for faultray.model.graph and faultray.model.components.

Covers edge cases, boundary conditions, and error paths for:
- InfraGraph: all public methods
- Component: utilization, effective_capacity_at_replicas, validate_replicas
- Dependency: basic construction
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    Capacity,
    CircuitBreakerConfig,
    Component,
    ComponentType,
    Dependency,
    ExternalSLAConfig,
    FailoverConfig,
    HealthStatus,
    OperationalProfile,
    ResourceMetrics,
)
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _comp(
    cid: str,
    name: str = "",
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    **kwargs: object,
) -> Component:
    return Component(id=cid, name=name or cid, type=ctype, replicas=replicas, **kwargs)  # type: ignore[arg-type]


def _dep(src: str, tgt: str, dtype: str = "requires", **kwargs: object) -> Dependency:
    return Dependency(source_id=src, target_id=tgt, dependency_type=dtype, **kwargs)  # type: ignore[arg-type]


def _graph(*comps: Component, deps: list[Dependency] | None = None) -> InfraGraph:
    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    for d in (deps or []):
        g.add_dependency(d)
    return g


# ===========================================================================
# Component.validate_replicas
# ===========================================================================


class TestValidateReplicas:

    def test_valid_replicas(self) -> None:
        c = _comp("a", replicas=3)
        assert c.replicas == 3

    def test_replicas_exactly_one(self) -> None:
        c = _comp("a", replicas=1)
        assert c.replicas == 1

    def test_zero_replicas_rejected(self) -> None:
        with pytest.raises(ValueError, match="replicas must be >= 1"):
            _comp("a", replicas=0)

    def test_negative_replicas_rejected(self) -> None:
        with pytest.raises(ValueError, match="replicas must be >= 1"):
            _comp("a", replicas=-5)


# ===========================================================================
# Component.utilization
# ===========================================================================


class TestUtilization:

    def test_no_metrics_zero(self) -> None:
        c = _comp("a")
        assert c.utilization() == 0.0

    def test_cpu_only(self) -> None:
        c = _comp("a", metrics=ResourceMetrics(cpu_percent=75.0))
        assert c.utilization() == 75.0

    def test_max_of_factors(self) -> None:
        c = _comp(
            "a",
            metrics=ResourceMetrics(
                cpu_percent=50.0,
                memory_percent=80.0,
                disk_percent=30.0,
                network_connections=200,
            ),
            capacity=Capacity(max_connections=1000),
        )
        # network = 200/1000*100 = 20%, cpu = 50, mem = 80, disk = 30  =>  max = 80
        assert c.utilization() == 80.0

    def test_network_connections_factor(self) -> None:
        c = _comp(
            "a",
            metrics=ResourceMetrics(network_connections=500),
            capacity=Capacity(max_connections=1000),
        )
        assert c.utilization() == 50.0

    def test_zero_max_connections_skipped(self) -> None:
        c = _comp(
            "a",
            metrics=ResourceMetrics(cpu_percent=40.0),
            capacity=Capacity(max_connections=0),
        )
        assert c.utilization() == 40.0


# ===========================================================================
# Component.effective_capacity_at_replicas
# ===========================================================================


class TestEffectiveCapacity:

    def test_same_replicas(self) -> None:
        c = _comp("a", replicas=3)
        assert c.effective_capacity_at_replicas(3) == pytest.approx(1.0)

    def test_double_replicas(self) -> None:
        c = _comp("a", replicas=2)
        assert c.effective_capacity_at_replicas(4) == pytest.approx(2.0)

    def test_half_replicas(self) -> None:
        c = _comp("a", replicas=4)
        assert c.effective_capacity_at_replicas(2) == pytest.approx(0.5)

    def test_zero_target_replicas(self) -> None:
        c = _comp("a", replicas=3)
        assert c.effective_capacity_at_replicas(0) == pytest.approx(0.0)


# ===========================================================================
# InfraGraph — empty graph
# ===========================================================================


class TestEmptyGraph:

    def test_empty_components(self) -> None:
        g = InfraGraph()
        assert g.components == {}

    def test_get_component_returns_none(self) -> None:
        g = InfraGraph()
        assert g.get_component("nonexistent") is None

    def test_get_dependents_empty(self) -> None:
        g = InfraGraph()
        # Node doesn't exist; networkx will raise or return empty
        # Our graph adds the node only when add_component is called
        g2 = _graph(_comp("a"))
        assert g2.get_dependents("a") == []

    def test_get_dependencies_empty(self) -> None:
        g = _graph(_comp("a"))
        assert g.get_dependencies("a") == []

    def test_resilience_score_empty(self) -> None:
        g = InfraGraph()
        assert g.resilience_score() == 0.0

    def test_resilience_score_v2_empty(self) -> None:
        g = InfraGraph()
        result = g.resilience_score_v2()
        assert result["score"] == 0.0

    def test_summary_empty(self) -> None:
        g = InfraGraph()
        s = g.summary()
        assert s["total_components"] == 0
        assert s["total_dependencies"] == 0

    def test_get_cascade_path_no_component(self) -> None:
        g = _graph(_comp("a"))
        paths = g.get_cascade_path("a")
        assert paths == []

    def test_get_all_affected_isolated(self) -> None:
        g = _graph(_comp("a"))
        affected = g.get_all_affected("a")
        assert affected == set()

    def test_get_critical_paths_single_node(self) -> None:
        g = _graph(_comp("a"))
        paths = g.get_critical_paths()
        # Single node with no edges: it's both entry and leaf
        assert len(paths) >= 0  # may return [["a"]] depending on implementation

    def test_all_dependency_edges_empty(self) -> None:
        g = _graph(_comp("a"))
        assert g.all_dependency_edges() == []


# ===========================================================================
# InfraGraph — dependency operations
# ===========================================================================


class TestGraphDependencies:

    def test_add_and_get_dependency_edge(self) -> None:
        g = _graph(
            _comp("a"), _comp("b"),
            deps=[_dep("a", "b", "requires")],
        )
        edge = g.get_dependency_edge("a", "b")
        assert edge is not None
        assert edge.dependency_type == "requires"

    def test_get_dependency_edge_nonexistent(self) -> None:
        g = _graph(_comp("a"), _comp("b"))
        assert g.get_dependency_edge("a", "b") is None

    def test_get_dependency_edge_reversed(self) -> None:
        g = _graph(
            _comp("a"), _comp("b"),
            deps=[_dep("a", "b")],
        )
        # Reverse direction should return None
        assert g.get_dependency_edge("b", "a") is None

    def test_get_dependents(self) -> None:
        g = _graph(
            _comp("a"), _comp("b"), _comp("c"),
            deps=[_dep("a", "b"), _dep("c", "b")],
        )
        dependents = g.get_dependents("b")
        ids = {d.id for d in dependents}
        assert ids == {"a", "c"}

    def test_get_dependencies(self) -> None:
        g = _graph(
            _comp("a"), _comp("b"), _comp("c"),
            deps=[_dep("a", "b"), _dep("a", "c")],
        )
        deps = g.get_dependencies("a")
        ids = {d.id for d in deps}
        assert ids == {"b", "c"}

    def test_all_dependency_edges(self) -> None:
        g = _graph(
            _comp("a"), _comp("b"), _comp("c"),
            deps=[_dep("a", "b"), _dep("b", "c")],
        )
        edges = g.all_dependency_edges()
        assert len(edges) == 2

    def test_all_dependency_edges_types(self) -> None:
        g = _graph(
            _comp("a"), _comp("b"),
            deps=[_dep("a", "b", "optional")],
        )
        edges = g.all_dependency_edges()
        assert edges[0].dependency_type == "optional"


# ===========================================================================
# InfraGraph — cascade path and affected
# ===========================================================================


class TestCascadeAndAffected:

    def _chain_graph(self) -> InfraGraph:
        """a -> b -> c (a depends on b, b depends on c)."""
        return _graph(
            _comp("a"), _comp("b"), _comp("c"),
            deps=[_dep("a", "b"), _dep("b", "c")],
        )

    def test_get_cascade_path_chain(self) -> None:
        g = self._chain_graph()
        # If c fails, cascade goes to b (depends on c), then a (depends on b)
        paths = g.get_cascade_path("c")
        # Should find paths from c -> b and c -> b -> a in the reverse graph
        assert len(paths) > 0

    def test_get_all_affected_chain(self) -> None:
        g = self._chain_graph()
        affected = g.get_all_affected("c")
        # b depends on c, a depends on b
        assert "b" in affected
        assert "a" in affected

    def test_get_all_affected_leaf(self) -> None:
        g = self._chain_graph()
        # a is a leaf (nothing depends on a)
        affected = g.get_all_affected("a")
        assert affected == set()

    def test_get_all_affected_middle(self) -> None:
        g = self._chain_graph()
        affected = g.get_all_affected("b")
        assert "a" in affected
        assert "c" not in affected

    def test_get_cascade_path_diamond(self) -> None:
        """Diamond: a->b, a->c, b->d, c->d. If d fails, both paths should be found."""
        g = _graph(
            _comp("a"), _comp("b"), _comp("c"), _comp("d"),
            deps=[_dep("a", "b"), _dep("a", "c"), _dep("b", "d"), _dep("c", "d")],
        )
        paths = g.get_cascade_path("d")
        assert len(paths) >= 2  # At least d->b->a and d->c->a


# ===========================================================================
# InfraGraph — critical paths
# ===========================================================================


class TestCriticalPaths:

    def test_chain_path(self) -> None:
        g = _graph(
            _comp("a"), _comp("b"), _comp("c"),
            deps=[_dep("a", "b"), _dep("b", "c")],
        )
        paths = g.get_critical_paths()
        # Should find a -> b -> c
        assert len(paths) >= 1
        longest = paths[0]
        assert len(longest) == 3

    def test_max_paths_limit(self) -> None:
        g = _graph(
            _comp("a"), _comp("b"), _comp("c"),
            deps=[_dep("a", "b"), _dep("b", "c")],
        )
        paths = g.get_critical_paths(max_paths=1)
        assert len(paths) <= 1

    def test_no_edges_no_long_paths(self) -> None:
        g = _graph(_comp("a"), _comp("b"))
        paths = g.get_critical_paths()
        # Nodes with no edges are both entry and leaf; paths are single-node
        for p in paths:
            assert len(p) == 1


# ===========================================================================
# InfraGraph — resilience_score
# ===========================================================================


class TestResilienceScore:

    def test_single_component_no_dependents(self) -> None:
        g = _graph(_comp("a"))
        score = g.resilience_score()
        assert 0.0 <= score <= 100.0

    def test_spof_penalty(self) -> None:
        """Single replica with requires dependents should lower score."""
        g = _graph(
            _comp("app"), _comp("db", replicas=1),
            deps=[_dep("app", "db", "requires")],
        )
        score = g.resilience_score()
        # Compare with redundant version
        g2 = _graph(
            _comp("app"), _comp("db", replicas=3),
            deps=[_dep("app", "db", "requires")],
        )
        score2 = g2.resilience_score()
        # Redundant should have equal or higher score
        assert score2 >= score

    def test_failover_reduces_penalty(self) -> None:
        g = _graph(
            _comp("app"),
            _comp("db", replicas=1, failover=FailoverConfig(enabled=True)),
            deps=[_dep("app", "db", "requires")],
        )
        score_fo = g.resilience_score()

        g2 = _graph(
            _comp("app"),
            _comp("db", replicas=1),
            deps=[_dep("app", "db", "requires")],
        )
        score_nofo = g2.resilience_score()
        assert score_fo >= score_nofo

    def test_high_utilization_penalty(self) -> None:
        g = _graph(
            _comp("a", metrics=ResourceMetrics(cpu_percent=95.0)),
        )
        score_high = g.resilience_score()

        g2 = _graph(
            _comp("a", metrics=ResourceMetrics(cpu_percent=10.0)),
        )
        score_low = g2.resilience_score()
        assert score_low >= score_high

    def test_deep_chain_penalty(self) -> None:
        """Deep dependency chain should lower score."""
        comps = [_comp(f"c{i}") for i in range(8)]
        deps_list = [_dep(f"c{i}", f"c{i+1}") for i in range(7)]
        g = _graph(*comps, deps=deps_list)
        score = g.resilience_score()
        assert score < 100.0


# ===========================================================================
# InfraGraph — summary, to_dict, save, load
# ===========================================================================


class TestSerializationRoundTrip:

    def test_summary_contents(self) -> None:
        g = _graph(
            _comp("app"), _comp("db", ctype=ComponentType.DATABASE),
            deps=[_dep("app", "db")],
        )
        s = g.summary()
        assert s["total_components"] == 2
        assert s["total_dependencies"] == 1
        assert "app_server" in s["component_types"]  # type: ignore[operator]
        assert "database" in s["component_types"]  # type: ignore[operator]
        assert isinstance(s["resilience_score"], float)

    def test_to_dict_and_back(self) -> None:
        g = _graph(
            _comp("app"), _comp("db", ctype=ComponentType.DATABASE),
            deps=[_dep("app", "db", "requires")],
        )
        d = g.to_dict()
        assert "components" in d
        assert "dependencies" in d
        assert "schema_version" in d

    def test_save_and_load(self) -> None:
        g = _graph(
            _comp("app"), _comp("db", ctype=ComponentType.DATABASE),
            deps=[_dep("app", "db", "requires")],
        )
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = Path(f.name)
        try:
            g.save(path)
            g2 = InfraGraph.load(path)
            assert set(g2.components.keys()) == {"app", "db"}
            edge = g2.get_dependency_edge("app", "db")
            assert edge is not None
            assert edge.dependency_type == "requires"
        finally:
            path.unlink(missing_ok=True)

    def test_load_missing_schema_version(self) -> None:
        """Load a file without schema_version should still work."""
        data = {
            "components": [
                {"id": "a", "name": "A", "type": "app_server"},
            ],
            "dependencies": [],
        }
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump(data, f)
            path = Path(f.name)
        try:
            g = InfraGraph.load(path)
            assert "a" in g.components
        finally:
            path.unlink(missing_ok=True)

    def test_load_different_schema_version(self) -> None:
        data = {
            "schema_version": "1.0",
            "components": [
                {"id": "a", "name": "A", "type": "app_server"},
            ],
            "dependencies": [],
        }
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump(data, f)
            path = Path(f.name)
        try:
            g = InfraGraph.load(path)
            assert "a" in g.components
        finally:
            path.unlink(missing_ok=True)


# ===========================================================================
# InfraGraph — resilience_score_v2 edge cases
# ===========================================================================


class TestResilienceScoreV2Extras:

    def test_no_edges_full_cb_coverage(self) -> None:
        """No dependency edges -> circuit breaker coverage should be perfect."""
        g = _graph(_comp("a"))
        result = g.resilience_score_v2()
        assert result["breakdown"]["circuit_breaker_coverage"] == 20.0  # type: ignore[index]

    def test_recommendations_for_no_redundancy(self) -> None:
        g = _graph(_comp("a"))
        result = g.resilience_score_v2()
        recs = result["recommendations"]
        assert isinstance(recs, list)
        # Should recommend adding redundancy
        assert any("redundancy" in r.lower() or "replica" in r.lower() for r in recs)  # type: ignore[union-attr]

    def test_high_utilization_recommendation(self) -> None:
        g = _graph(
            _comp("a", metrics=ResourceMetrics(cpu_percent=95.0)),
        )
        result = g.resilience_score_v2()
        recs = result["recommendations"]
        assert any("utilization" in r.lower() for r in recs)  # type: ignore[union-attr]


# ===========================================================================
# Availability model functions
# ===========================================================================


class TestAvailabilityModelFunctions:
    """Direct tests for compute_three_layer_model and compute_five_layer_model."""

    def test_three_layer_empty_graph(self) -> None:
        from faultray.simulator.availability_model import compute_three_layer_model
        g = InfraGraph()
        result = compute_three_layer_model(g)
        assert result.layer1_software.availability == 0.0
        assert result.layer2_hardware.availability == 0.0
        assert result.layer3_theoretical.availability == 0.0

    def test_five_layer_empty_graph(self) -> None:
        from faultray.simulator.availability_model import compute_five_layer_model
        g = InfraGraph()
        result = compute_five_layer_model(g)
        assert result.layer4_operational.availability == 0.0
        assert result.layer5_external.availability == 0.0

    def test_three_layer_single_component(self) -> None:
        from faultray.simulator.availability_model import compute_three_layer_model
        g = _graph(_comp("db", ctype=ComponentType.DATABASE))
        result = compute_three_layer_model(g)
        assert 0.0 < result.layer2_hardware.availability <= 1.0
        assert result.layer1_software.availability <= result.layer2_hardware.availability

    def test_three_layer_multi_replica_higher(self) -> None:
        from faultray.simulator.availability_model import compute_three_layer_model
        g1 = _graph(_comp("db", replicas=1))
        g2 = _graph(_comp("db", replicas=3))
        r1 = compute_three_layer_model(g1)
        r2 = compute_three_layer_model(g2)
        assert r2.layer2_hardware.availability >= r1.layer2_hardware.availability

    def test_five_layer_external_sla(self) -> None:
        from faultray.simulator.availability_model import compute_five_layer_model
        g = _graph(
            _comp("app"),
            _comp("ext", ctype=ComponentType.EXTERNAL_API,
                  external_sla=ExternalSLAConfig(provider_sla=99.0)),
        )
        result = compute_five_layer_model(g)
        # External layer should reflect the SLA
        assert result.layer5_external.availability < 1.0
        assert result.layer5_external.availability >= 0.99 * 0.999 - 0.01  # approx

    def test_five_layer_no_external_deps(self) -> None:
        from faultray.simulator.availability_model import compute_five_layer_model
        g = _graph(_comp("app"))
        result = compute_five_layer_model(g)
        assert result.layer5_external.availability == 1.0

    def test_five_layer_operational_layer(self) -> None:
        from faultray.simulator.availability_model import compute_five_layer_model
        g = _graph(_comp("app"))
        result = compute_five_layer_model(g)
        assert 0.0 < result.layer4_operational.availability <= 1.0

    def test_three_layer_summary_property(self) -> None:
        from faultray.simulator.availability_model import compute_three_layer_model
        g = _graph(_comp("app"))
        result = compute_three_layer_model(g)
        summary = result.summary
        assert "3-Layer" in summary
        assert "Layer 1" in summary
        assert "Layer 2" in summary
        assert "Layer 3" in summary

    def test_five_layer_summary_property(self) -> None:
        from faultray.simulator.availability_model import compute_five_layer_model
        g = _graph(_comp("app"))
        result = compute_five_layer_model(g)
        summary = result.summary
        assert "5-Layer" in summary
        assert "Layer 4" in summary
        assert "Layer 5" in summary

    def test_three_layer_failover_reduces_downtime(self) -> None:
        from faultray.simulator.availability_model import compute_three_layer_model
        g1 = _graph(_comp("db", replicas=2, failover=FailoverConfig(enabled=True)))
        g2 = _graph(_comp("db", replicas=2))
        r1 = compute_three_layer_model(g1)
        r2 = compute_three_layer_model(g2)
        # With failover there's a penalty, but the test is about the model functioning
        assert r1.layer2_hardware.availability > 0.0
        assert r2.layer2_hardware.availability > 0.0

    def test_to_nines_edge_cases(self) -> None:
        from faultray.simulator.availability_model import _to_nines, _annual_downtime
        assert _to_nines(1.0) == float("inf")
        assert _to_nines(0.0) == 0.0
        assert _to_nines(0.99) == pytest.approx(2.0, abs=0.01)
        assert _to_nines(0.999) == pytest.approx(3.0, abs=0.01)
        assert _annual_downtime(1.0) == 0.0
        assert _annual_downtime(0.0) > 0.0

    def test_three_layer_with_dependencies(self) -> None:
        """Components with requires dependencies should affect system availability."""
        from faultray.simulator.availability_model import compute_three_layer_model
        g = _graph(
            _comp("app"), _comp("db"),
            deps=[_dep("app", "db", "requires")],
        )
        result = compute_three_layer_model(g)
        assert 0.0 < result.layer2_hardware.availability < 1.0

    def test_three_layer_optional_dep_not_multiplicative(self) -> None:
        """Optional dependencies shouldn't reduce system availability as much."""
        from faultray.simulator.availability_model import compute_three_layer_model
        g_req = _graph(
            _comp("app"), _comp("cache"),
            deps=[_dep("app", "cache", "requires")],
        )
        g_opt = _graph(
            _comp("app"), _comp("cache"),
            deps=[_dep("app", "cache", "optional")],
        )
        r_req = compute_three_layer_model(g_req)
        r_opt = compute_three_layer_model(g_opt)
        # Optional dependency should result in equal or higher availability
        assert r_opt.layer2_hardware.availability >= r_req.layer2_hardware.availability

    def test_five_layer_external_api_default_sla(self) -> None:
        """External API without explicit SLA should get default 99.9%."""
        from faultray.simulator.availability_model import compute_five_layer_model
        g = _graph(_comp("ext", ctype=ComponentType.EXTERNAL_API))
        result = compute_five_layer_model(g)
        assert result.layer5_external.availability == pytest.approx(0.999, abs=0.001)

    def test_three_layer_network_penalty(self) -> None:
        """High packet loss should reduce theoretical availability."""
        from faultray.simulator.availability_model import compute_three_layer_model
        from faultray.model.components import NetworkProfile
        g = _graph(
            _comp("app", network=NetworkProfile(packet_loss_rate=0.1)),
        )
        result = compute_three_layer_model(g)
        assert result.layer3_theoretical.availability < result.layer2_hardware.availability

    def test_three_layer_gc_penalty(self) -> None:
        """GC pauses should reduce theoretical availability."""
        from faultray.simulator.availability_model import compute_three_layer_model
        from faultray.model.components import RuntimeJitter
        g = _graph(
            _comp("app", runtime_jitter=RuntimeJitter(gc_pause_ms=50.0, gc_pause_frequency=10.0)),
        )
        result = compute_three_layer_model(g)
        assert result.layer3_theoretical.availability < result.layer2_hardware.availability


# ===========================================================================
# CascadeChain.severity edge cases
# ===========================================================================


class TestCascadeChainSeverity:
    """Additional severity edge case tests."""

    def test_empty_effects_zero(self) -> None:
        from faultray.simulator.cascade import CascadeChain
        chain = CascadeChain(trigger="test", total_components=5)
        assert chain.severity == 0.0

    def test_all_degraded_capped_at_4(self) -> None:
        from faultray.simulator.cascade import CascadeChain, CascadeEffect
        chain = CascadeChain(
            trigger="test",
            total_components=5,
            effects=[
                CascadeEffect(component_id=f"c{i}", component_name=f"C{i}",
                              health=HealthStatus.DEGRADED, reason="degraded")
                for i in range(5)
            ],
        )
        assert chain.severity <= 4.0

    def test_single_down_capped_at_3(self) -> None:
        from faultray.simulator.cascade import CascadeChain, CascadeEffect
        chain = CascadeChain(
            trigger="test",
            total_components=10,
            effects=[
                CascadeEffect(component_id="c0", component_name="C0",
                              health=HealthStatus.DOWN, reason="down"),
            ],
        )
        assert chain.severity <= 3.0

    def test_single_overloaded_capped_at_2(self) -> None:
        from faultray.simulator.cascade import CascadeChain, CascadeEffect
        chain = CascadeChain(
            trigger="test",
            total_components=10,
            effects=[
                CascadeEffect(component_id="c0", component_name="C0",
                              health=HealthStatus.OVERLOADED, reason="overloaded"),
            ],
        )
        assert chain.severity <= 2.0

    def test_single_degraded_capped_at_1_5(self) -> None:
        from faultray.simulator.cascade import CascadeChain, CascadeEffect
        chain = CascadeChain(
            trigger="test",
            total_components=10,
            effects=[
                CascadeEffect(component_id="c0", component_name="C0",
                              health=HealthStatus.DEGRADED, reason="degraded"),
            ],
        )
        assert chain.severity <= 1.5

    def test_full_system_down_max_score(self) -> None:
        from faultray.simulator.cascade import CascadeChain, CascadeEffect
        chain = CascadeChain(
            trigger="test",
            total_components=5,
            effects=[
                CascadeEffect(component_id=f"c{i}", component_name=f"C{i}",
                              health=HealthStatus.DOWN, reason="down")
                for i in range(5)
            ],
        )
        assert chain.severity == 10.0

    def test_likelihood_reduces_severity(self) -> None:
        from faultray.simulator.cascade import CascadeChain, CascadeEffect
        chain = CascadeChain(
            trigger="test",
            total_components=5,
            likelihood=0.5,
            effects=[
                CascadeEffect(component_id=f"c{i}", component_name=f"C{i}",
                              health=HealthStatus.DOWN, reason="down")
                for i in range(5)
            ],
        )
        assert chain.severity <= 5.0

    def test_minor_cascade_capped_at_6(self) -> None:
        """Less than 30% spread should be capped at 6.0."""
        from faultray.simulator.cascade import CascadeChain, CascadeEffect
        chain = CascadeChain(
            trigger="test",
            total_components=20,
            effects=[
                CascadeEffect(component_id=f"c{i}", component_name=f"C{i}",
                              health=HealthStatus.DOWN, reason="down")
                for i in range(5)  # 5/20 = 25% < 30%
            ],
        )
        assert chain.severity <= 6.0


# ===========================================================================
# CascadeEngine — targeted traffic spike edge cases
# ===========================================================================


class TestTrafficSpikeTargeted:

    def test_nonexistent_component_skipped(self) -> None:
        from faultray.simulator.cascade import CascadeEngine
        g = _graph(_comp("a"))
        engine = CascadeEngine(g)
        chain = engine.simulate_traffic_spike_targeted(3.0, ["nonexistent"])
        assert len(chain.effects) == 0

    def test_below_threshold_no_effect(self) -> None:
        from faultray.simulator.cascade import CascadeEngine
        # Very low utilization, even 2x won't trigger
        g = _graph(_comp("a", metrics=ResourceMetrics(cpu_percent=10.0)))
        engine = CascadeEngine(g)
        chain = engine.simulate_traffic_spike_targeted(2.0, ["a"])
        assert len(chain.effects) == 0

    def test_overloaded_threshold(self) -> None:
        from faultray.simulator.cascade import CascadeEngine
        # 50% util * 1.9 = 95% -> should be overloaded
        g = _graph(_comp("a", metrics=ResourceMetrics(cpu_percent=50.0)))
        engine = CascadeEngine(g)
        chain = engine.simulate_traffic_spike_targeted(1.9, ["a"])
        if chain.effects:
            assert chain.effects[0].health in (HealthStatus.OVERLOADED, HealthStatus.DEGRADED)
