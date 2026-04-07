# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Comprehensive tests for InfraGraph (faultray.model.graph).

Targets ≥90% coverage of src/faultray/model/graph.py.
Covers: getters, cascade/critical paths, resilience scoring v1+v2,
summary, serialization (to_dict/save/load), and required edge cases
(empty, single, cycles, self-loop, duplicate IDs, missing edges,
large graphs, Unicode IDs).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from faultray.model import graph as graph_module
from faultray.model.components import (
    AutoScalingConfig,
    CircuitBreakerConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    ResourceMetrics,
    SCHEMA_VERSION,
)
from faultray.model.demo import create_demo_graph
from faultray.model.graph import InfraGraph


# ----------------------------- helpers --------------------------------------


def _comp(
    cid: str,
    *,
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    host: str = "",
    cpu: float = 0.0,
    mem: float = 0.0,
    disk: float = 0.0,
    failover: bool = False,
    autoscaling: bool = False,
) -> Component:
    return Component(
        id=cid,
        name=cid,
        type=ctype,
        host=host,
        port=8080,
        replicas=replicas,
        metrics=ResourceMetrics(cpu_percent=cpu, memory_percent=mem, disk_percent=disk),
        failover=FailoverConfig(enabled=failover),
        autoscaling=AutoScalingConfig(enabled=autoscaling),
    )


def _dep(
    src: str,
    tgt: str,
    *,
    dep_type: str = "requires",
    cb: bool = False,
) -> Dependency:
    return Dependency(
        source_id=src,
        target_id=tgt,
        dependency_type=dep_type,
        circuit_breaker=CircuitBreakerConfig(enabled=cb),
    )


# resilience_score_v2 returns dict[str, object]; these helpers narrow the
# embedded values for mypy --strict in tests.
def _breakdown(out: dict[str, object]) -> dict[str, float]:
    bd = out["breakdown"]
    assert isinstance(bd, dict)
    return cast("dict[str, float]", bd)


def _recs(out: dict[str, object]) -> list[str]:
    recs = out["recommendations"]
    assert isinstance(recs, list)
    return cast("list[str]", recs)


# ----------------------------- existing tests (kept) -----------------------


def test_cascade_path_direction() -> None:
    """get_cascade_path returns paths FROM failed component to dependents."""
    graph = InfraGraph()
    graph.add_component(Component(id="frontend", name="Frontend", type=ComponentType.WEB_SERVER, port=80))
    graph.add_component(Component(id="backend", name="Backend", type=ComponentType.APP_SERVER, port=8080))
    graph.add_component(Component(id="database", name="Database", type=ComponentType.DATABASE, port=5432))
    graph.add_dependency(Dependency(source_id="frontend", target_id="backend", dependency_type="requires"))
    graph.add_dependency(Dependency(source_id="backend", target_id="database", dependency_type="requires"))

    paths = graph.get_cascade_path("database")
    assert len(paths) > 0
    for path in paths:
        assert path[0] == "database", f"Path should start from failed component, got {path}"

    path_strs = [" -> ".join(p) for p in paths]
    assert "database -> backend" in path_strs
    assert "database -> backend -> frontend" in path_strs


def test_critical_paths_max_guard() -> None:
    """get_critical_paths respects max_paths limit."""
    graph = create_demo_graph()
    all_paths = graph.get_critical_paths(max_paths=1000)
    limited = graph.get_critical_paths(max_paths=2)
    assert len(limited) <= 2
    assert len(all_paths) >= len(limited)


# ----------------------------- construction & getters ----------------------


def test_empty_graph_basics() -> None:
    g = InfraGraph()
    assert g.components == {}
    assert g.all_dependency_edges() == []
    assert g.get_component("missing") is None
    assert g.get_dependency_edge("a", "b") is None
    assert g.get_critical_paths() == []
    assert g.resilience_score() == 0.0
    v2 = g.resilience_score_v2()
    assert v2["score"] == 0.0
    assert v2["recommendations"] == []


def test_components_property_returns_dict() -> None:
    g = InfraGraph()
    c = _comp("a")
    g.add_component(c)
    assert g.components == {"a": c}


def test_add_component_duplicate_id_overwrites() -> None:
    """Adding two components with the same ID keeps the latest (graph behaviour)."""
    g = InfraGraph()
    g.add_component(_comp("a", cpu=10))
    g.add_component(_comp("a", cpu=99))
    assert g.get_component("a") is not None
    assert g.components["a"].metrics.cpu_percent == 99


def test_add_component_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """add_component raises when _MAX_COMPONENTS exceeded."""
    monkeypatch.setattr(graph_module, "_MAX_COMPONENTS", 2)
    g = InfraGraph()
    g.add_component(_comp("a"))
    g.add_component(_comp("b"))
    with pytest.raises(ValueError, match="Component limit reached"):
        g.add_component(_comp("c"))


def test_get_component_present_and_missing() -> None:
    g = InfraGraph()
    g.add_component(_comp("a"))
    assert g.get_component("a") is not None
    assert g.get_component("nope") is None


def test_get_dependents_and_dependencies() -> None:
    g = InfraGraph()
    g.add_component(_comp("a"))
    g.add_component(_comp("b"))
    g.add_component(_comp("c"))
    g.add_dependency(_dep("a", "b"))
    g.add_dependency(_dep("a", "c"))
    # 'a' depends on b and c → b/c are 'dependencies' of a
    deps = {d.id for d in g.get_dependencies("a")}
    assert deps == {"b", "c"}
    # b is depended on by a → a is a 'dependent' of b
    dependents = {d.id for d in g.get_dependents("b")}
    assert dependents == {"a"}
    # leaf nodes
    assert g.get_dependents("a") == []
    assert g.get_dependencies("b") == []


def test_get_dependency_edge_present_and_missing() -> None:
    g = InfraGraph()
    g.add_component(_comp("a"))
    g.add_component(_comp("b"))
    g.add_dependency(_dep("a", "b", dep_type="optional"))
    edge = g.get_dependency_edge("a", "b")
    assert edge is not None
    assert edge.dependency_type == "optional"
    assert g.get_dependency_edge("b", "a") is None
    assert g.get_dependency_edge("x", "y") is None


def test_all_dependency_edges_returns_metadata() -> None:
    g = InfraGraph()
    g.add_component(_comp("a"))
    g.add_component(_comp("b"))
    g.add_component(_comp("c"))
    g.add_dependency(_dep("a", "b"))
    g.add_dependency(_dep("b", "c", dep_type="async"))
    edges = g.all_dependency_edges()
    assert len(edges) == 2
    types = {e.dependency_type for e in edges}
    assert types == {"requires", "async"}


# ----------------------------- cascade & affected --------------------------


def test_get_all_affected_transitive() -> None:
    g = InfraGraph()
    for cid in ("a", "b", "c", "d"):
        g.add_component(_comp(cid))
    # a -> b -> c, a -> d (a depends on b, b on c, a on d)
    g.add_dependency(_dep("a", "b"))
    g.add_dependency(_dep("b", "c"))
    g.add_dependency(_dep("a", "d"))
    # When 'c' fails, only 'b' and 'a' are affected (a depends on b which depends on c)
    affected = g.get_all_affected("c")
    assert affected == {"a", "b"}
    # When 'd' fails, only 'a'
    assert g.get_all_affected("d") == {"a"}
    # When 'a' fails, nothing depends on a → empty
    assert g.get_all_affected("a") == set()


def test_get_all_affected_with_cycle() -> None:
    """Cycle must not cause infinite loop."""
    g = InfraGraph()
    for cid in ("a", "b", "c"):
        g.add_component(_comp(cid))
    g.add_dependency(_dep("a", "b"))
    g.add_dependency(_dep("b", "c"))
    g.add_dependency(_dep("c", "a"))  # cycle
    affected = g.get_all_affected("a")
    # Cycle: a→b→c→a means a is transitively its own dependent. BFS terminates
    # because the visited set prevents re-enqueueing.
    assert affected == {"a", "b", "c"}


def test_self_loop_edge() -> None:
    g = InfraGraph()
    g.add_component(_comp("a"))
    g.add_dependency(_dep("a", "a"))
    # a depends on itself, so 'a' is its own dependent and is included once.
    # The visited set prevents the BFS from re-enqueueing it forever.
    affected = g.get_all_affected("a")
    assert affected == {"a"}


def test_dependency_edge_to_missing_component() -> None:
    """Edges referencing unknown IDs must not crash getters."""
    g = InfraGraph()
    g.add_component(_comp("a"))
    # Adding a dependency referencing a non-existent target
    g.add_dependency(_dep("a", "ghost"))
    # get_dependencies filters out ids not in _components
    assert g.get_dependencies("a") == []
    # get_dependents on ghost: 'a' is in _components so it should appear
    assert {c.id for c in g.get_dependents("ghost")} == {"a"}


# ----------------------------- cascade paths --------------------------------


def test_cascade_path_skips_self_node() -> None:
    g = InfraGraph()
    g.add_component(_comp("a"))
    g.add_component(_comp("b"))
    g.add_dependency(_dep("a", "b"))
    paths = g.get_cascade_path("b")
    # Self path (b->b) is excluded; path b->a should exist
    assert any(p == ["b", "a"] for p in paths)
    assert all(p[0] == "b" for p in paths)


# ----------------------------- critical paths -------------------------------


def test_critical_paths_single_chain() -> None:
    g = InfraGraph()
    for cid in ("a", "b", "c"):
        g.add_component(_comp(cid))
    g.add_dependency(_dep("a", "b"))
    g.add_dependency(_dep("b", "c"))
    paths = g.get_critical_paths()
    assert paths
    longest = paths[0]
    assert longest == ["a", "b", "c"]


def test_critical_paths_max_paths_truncation() -> None:
    """Many entry/leaf nodes — verify max_paths truncates and sorts."""
    g = InfraGraph()
    # 5 entry points, all leading to a single sink
    for i in range(5):
        g.add_component(_comp(f"src{i}"))
    g.add_component(_comp("sink"))
    for i in range(5):
        g.add_dependency(_dep(f"src{i}", "sink"))
    paths = g.get_critical_paths(max_paths=3)
    assert len(paths) <= 3


# ----------------------------- resilience_score (v1) -----------------------


def test_resilience_score_perfect_isolated_components() -> None:
    """No dependencies, low utilization → near-perfect score."""
    g = InfraGraph()
    g.add_component(_comp("a", cpu=10, mem=10, disk=10))
    score = g.resilience_score()
    assert 90.0 <= score <= 100.0


def test_resilience_score_spof_penalty() -> None:
    """Single replica with dependents → SPOF penalty applied."""
    g = InfraGraph()
    g.add_component(_comp("db", replicas=1))
    g.add_component(_comp("api1"))
    g.add_component(_comp("api2"))
    g.add_dependency(_dep("api1", "db", dep_type="requires"))
    g.add_dependency(_dep("api2", "db", dep_type="requires"))
    score = g.resilience_score()
    assert score < 100.0


def test_resilience_score_optional_and_async_lower_penalty() -> None:
    g = InfraGraph()
    g.add_component(_comp("svc"))
    g.add_component(_comp("client1"))
    g.add_component(_comp("client2"))
    g.add_dependency(_dep("client1", "svc", dep_type="optional"))
    g.add_dependency(_dep("client2", "svc", dep_type="async"))
    score = g.resilience_score()
    # weighted_deps = 0.3 + 0.1 = 0.4 → small penalty
    assert score > 90.0


def test_resilience_score_failover_reduces_penalty() -> None:
    g = InfraGraph()
    g.add_component(_comp("db", failover=True))
    g.add_component(_comp("api"))
    g.add_dependency(_dep("api", "db"))
    with_failover = g.resilience_score()

    g2 = InfraGraph()
    g2.add_component(_comp("db", failover=False))
    g2.add_component(_comp("api"))
    g2.add_dependency(_dep("api", "db"))
    without_failover = g2.resilience_score()

    assert with_failover >= without_failover


def test_resilience_score_autoscaling_reduces_penalty() -> None:
    g = InfraGraph()
    g.add_component(_comp("db", autoscaling=True))
    g.add_component(_comp("api"))
    g.add_dependency(_dep("api", "db"))
    with_as = g.resilience_score()

    g2 = InfraGraph()
    g2.add_component(_comp("db", autoscaling=False))
    g2.add_component(_comp("api"))
    g2.add_dependency(_dep("api", "db"))
    without_as = g2.resilience_score()

    assert with_as >= without_as


def test_resilience_score_replicas_same_host_penalty() -> None:
    g = InfraGraph()
    g.add_component(_comp("db", replicas=3, host="host1"))
    g.add_component(_comp("api"))
    g.add_dependency(_dep("api", "db"))
    score = g.resilience_score()
    assert score < 100.0


def test_resilience_score_high_utilization_buckets() -> None:
    """Check each utilization bucket triggers penalty."""
    for cpu in (75.0, 85.0, 92.0, 97.0):
        g = InfraGraph()
        g.add_component(_comp("a", cpu=cpu))
        score = g.resilience_score()
        assert score < 100.0, f"cpu={cpu} should incur penalty"


def test_resilience_score_deep_chain_penalty() -> None:
    g = InfraGraph()
    ids = [f"n{i}" for i in range(8)]
    for cid in ids:
        g.add_component(_comp(cid))
    for a, b in zip(ids, ids[1:]):
        g.add_dependency(_dep(a, b))
    score = g.resilience_score()
    assert 0.0 <= score <= 100.0


def test_resilience_score_missing_edge_metadata_fallback() -> None:
    """resilience_score should still compute when an edge has no metadata."""
    g = InfraGraph()
    g.add_component(_comp("a"))
    g.add_component(_comp("b"))
    # Intentional private access: add a raw edge without dependency metadata
    # to exercise the fallback branch in resilience_score() where
    # get_dependency_edge() returns None.
    g._graph.add_edge("a", "b")
    score = g.resilience_score()
    assert 0.0 <= score <= 100.0


def test_resilience_score_clamped_zero_minimum() -> None:
    """Heavily-stressed graph must clamp to exactly 0, not go negative.

    Drive every penalty bucket in resilience_score() to its cap:
        SPOF (30) + same-host-replica (20) + failover-missing (15)
        + utilization (25) + depth (10) = 100
    which exceeds the 100-point base, so the clamp must produce 0.0.
    """
    g = InfraGraph()
    # 20 SPOF DBs (replicas=1, no failover) each with a dedicated dependent.
    # Drives both the SPOF cap (30) and failover-missing cap (15).
    for i in range(20):
        g.add_component(_comp(f"db{i}", cpu=99, mem=99, disk=99))
        g.add_component(_comp(f"api{i}", cpu=99, mem=99, disk=99))
        g.add_dependency(_dep(f"api{i}", f"db{i}", dep_type="requires"))
    # 10 components with replicas>=2 on a single host → false-redundancy
    # penalty (capped at 20). Each needs a dependent to be counted.
    for i in range(10):
        g.add_component(
            _comp(f"hr{i}", cpu=99, mem=99, disk=99, replicas=3, host="host1")
        )
        g.add_component(_comp(f"hrclient{i}", cpu=99, mem=99, disk=99))
        g.add_dependency(
            _dep(f"hrclient{i}", f"hr{i}", dep_type="requires")
        )
    # A long chain → max_depth > 5 → depth penalty caps at 10
    chain_ids = [f"chain{i}" for i in range(10)]
    for cid in chain_ids:
        g.add_component(_comp(cid, cpu=99, mem=99, disk=99))
    for a, b in zip(chain_ids, chain_ids[1:]):
        g.add_dependency(_dep(a, b, dep_type="requires"))
    score = g.resilience_score()
    assert score == 0.0


# ----------------------------- resilience_score_v2 -------------------------


def test_resilience_score_v2_structure() -> None:
    g = create_demo_graph()
    out = g.resilience_score_v2()
    assert "score" in out
    assert "breakdown" in out
    assert "recommendations" in out
    breakdown = _breakdown(out)
    assert isinstance(breakdown, dict)
    for key in (
        "redundancy",
        "circuit_breaker_coverage",
        "auto_recovery",
        "dependency_risk",
        "capacity_headroom",
    ):
        assert key in breakdown


def test_resilience_score_v2_active_active_redundancy() -> None:
    g = InfraGraph()
    g.add_component(_comp("db", replicas=3, failover=True))
    out = g.resilience_score_v2()
    assert _breakdown(out)["redundancy"] == 20.0


def test_resilience_score_v2_active_standby_redundancy() -> None:
    g = InfraGraph()
    g.add_component(_comp("db", replicas=2, failover=False))
    out = g.resilience_score_v2()
    assert _breakdown(out)["redundancy"] == 15.0


def test_resilience_score_v2_no_redundancy_recommendation() -> None:
    g = InfraGraph()
    g.add_component(_comp("db", replicas=1, failover=False))
    out = g.resilience_score_v2()
    assert _breakdown(out)["redundancy"] == 5.0
    assert any("no redundancy" in r for r in _recs(out))


def test_resilience_score_v2_circuit_breaker_full_coverage() -> None:
    g = InfraGraph()
    g.add_component(_comp("a"))
    g.add_component(_comp("b"))
    g.add_dependency(_dep("a", "b", cb=True))
    out = g.resilience_score_v2()
    assert _breakdown(out)["circuit_breaker_coverage"] == 20.0


def test_resilience_score_v2_circuit_breaker_partial_coverage_recommendation() -> None:
    g = InfraGraph()
    g.add_component(_comp("a"))
    g.add_component(_comp("b"))
    g.add_component(_comp("c"))
    g.add_dependency(_dep("a", "b", cb=True))
    g.add_dependency(_dep("a", "c", cb=False))
    out = g.resilience_score_v2()
    assert _breakdown(out)["circuit_breaker_coverage"] == 10.0
    assert any("circuit breaker" in r for r in _recs(out))


def test_resilience_score_v2_no_edges_full_cb_score() -> None:
    g = InfraGraph()
    g.add_component(_comp("solo"))
    out = g.resilience_score_v2()
    assert _breakdown(out)["circuit_breaker_coverage"] == 20.0


def test_resilience_score_v2_auto_recovery() -> None:
    g = InfraGraph()
    g.add_component(_comp("a", autoscaling=True))
    g.add_component(_comp("b", failover=True))
    out = g.resilience_score_v2()
    assert _breakdown(out)["auto_recovery"] == 20.0


def test_resilience_score_v2_no_auto_recovery_recommendation() -> None:
    g = InfraGraph()
    g.add_component(_comp("a"))
    out = g.resilience_score_v2()
    assert _breakdown(out)["auto_recovery"] == 0.0
    assert any("auto-recovery" in r for r in _recs(out))


def test_resilience_score_v2_dependency_risk_shallow() -> None:
    g = InfraGraph()
    g.add_component(_comp("solo", failover=True, replicas=2))
    out = g.resilience_score_v2()
    assert _breakdown(out)["dependency_risk"] == 20.0


def test_resilience_score_v2_dependency_risk_deep_chain() -> None:
    g = InfraGraph()
    ids = [f"n{i}" for i in range(12)]
    for cid in ids:
        g.add_component(_comp(cid, failover=True, replicas=2))
    for a, b in zip(ids, ids[1:]):
        g.add_dependency(_dep(a, b))
    out = g.resilience_score_v2()
    # depth ≥ 10 → 0
    assert _breakdown(out)["dependency_risk"] == 0.0


def test_resilience_score_v2_requires_without_alternative_penalty() -> None:
    g = InfraGraph()
    g.add_component(_comp("api"))
    g.add_component(_comp("db", replicas=1, failover=False))
    g.add_dependency(_dep("api", "db", dep_type="requires"))
    out = g.resilience_score_v2()
    assert any("'requires'" in r for r in _recs(out))


def test_resilience_score_v2_high_utilization_recommendation() -> None:
    g = InfraGraph()
    g.add_component(_comp("a", cpu=85))
    out = g.resilience_score_v2()
    assert any("high utilization" in r for r in _recs(out))


def test_resilience_score_v2_capacity_headroom_low_util() -> None:
    g = InfraGraph()
    g.add_component(_comp("a", cpu=10))
    out = g.resilience_score_v2()
    assert _breakdown(out)["capacity_headroom"] == 20.0


def test_resilience_score_v2_capacity_headroom_high_util() -> None:
    g = InfraGraph()
    g.add_component(_comp("a", cpu=95))
    out = g.resilience_score_v2()
    assert _breakdown(out)["capacity_headroom"] == 0.0


def test_resilience_score_v2_capacity_headroom_mid_util() -> None:
    g = InfraGraph()
    g.add_component(_comp("a", cpu=70))
    out = g.resilience_score_v2()
    headroom = _breakdown(out)["capacity_headroom"]
    assert isinstance(headroom, float)
    assert 0.0 < headroom < 20.0


def test_resilience_score_v2_recommendations_deduplicated() -> None:
    g = InfraGraph()
    g.add_component(_comp("a"))
    g.add_component(_comp("b"))
    out = g.resilience_score_v2()
    # both 'a' and 'b' lack redundancy → exactly 2 distinct recs (one per ID)
    redundancy_recs = [r for r in _recs(out) if "no redundancy" in r]
    assert len(redundancy_recs) == 2
    assert len(redundancy_recs) == len(set(redundancy_recs))


# ----------------------------- summary -------------------------------------


def test_summary_includes_counts_and_types() -> None:
    g = InfraGraph()
    g.add_component(_comp("api", ctype=ComponentType.APP_SERVER))
    g.add_component(_comp("db", ctype=ComponentType.DATABASE))
    g.add_dependency(_dep("api", "db"))
    s = g.summary()
    assert s["total_components"] == 2
    assert s["total_dependencies"] == 1
    types = s["component_types"]
    assert isinstance(types, dict)
    assert types.get("app_server") == 1
    assert types.get("database") == 1
    assert "resilience_score" in s


def test_summary_empty_graph() -> None:
    s = InfraGraph().summary()
    assert s["total_components"] == 0
    assert s["total_dependencies"] == 0
    assert s["component_types"] == {}
    assert s["resilience_score"] == 0.0


# ----------------------------- to_dict / save / load -----------------------


def test_to_dict_round_trip(tmp_path: Path) -> None:
    g = InfraGraph()
    g.add_component(_comp("api"))
    g.add_component(_comp("db"))
    g.add_dependency(_dep("api", "db"))
    d = g.to_dict()
    assert d["schema_version"] == SCHEMA_VERSION
    components = d["components"]
    dependencies = d["dependencies"]
    assert isinstance(components, list)
    assert isinstance(dependencies, list)
    assert len(components) == 2
    assert len(dependencies) == 1


def test_save_and_load_json(tmp_path: Path) -> None:
    g = InfraGraph()
    g.add_component(_comp("api"))
    g.add_component(_comp("db"))
    g.add_dependency(_dep("api", "db"))
    path = tmp_path / "graph.json"
    g.save(path)
    assert path.exists()

    loaded = InfraGraph.load(path)
    assert set(loaded.components.keys()) == {"api", "db"}
    assert len(loaded.all_dependency_edges()) == 1


def test_load_missing_schema_version_warning(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    payload = {
        "components": [_comp("a").model_dump()],
        "dependencies": [],
    }
    path = tmp_path / "noschema.json"
    path.write_text(json.dumps(payload, default=str))
    import logging
    with caplog.at_level(logging.WARNING, logger="faultray.model.graph"):
        loaded = InfraGraph.load(path)
    assert "a" in loaded.components
    assert any("schema v1.0" in rec.message for rec in caplog.records)


def test_load_old_schema_version_warning(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    payload = {
        "schema_version": "0.1",
        "components": [_comp("a").model_dump()],
        "dependencies": [],
    }
    path = tmp_path / "oldschema.json"
    path.write_text(json.dumps(payload, default=str))
    import logging
    with caplog.at_level(logging.WARNING, logger="faultray.model.graph"):
        loaded = InfraGraph.load(path)
    assert "a" in loaded.components
    assert any("v0.1" in rec.message for rec in caplog.records)


def test_load_yaml_delegates_to_loader(tmp_path: Path) -> None:
    """load() with .yaml extension delegates to faultray.model.loader.load_yaml."""
    yaml_text = """\
schema_version: "4.0"
components:
  - id: api
    name: api
    type: app_server
    port: 8080
dependencies: []
"""
    path = tmp_path / "graph.yaml"
    path.write_text(yaml_text)
    loaded = InfraGraph.load(path)
    assert "api" in loaded.components


# ----------------------------- edge cases ----------------------------------


def test_unicode_component_id() -> None:
    g = InfraGraph()
    g.add_component(_comp("サービス-🚀"))
    g.add_component(_comp("データベース-🗄️"))
    g.add_dependency(_dep("サービス-🚀", "データベース-🗄️"))
    assert g.get_component("サービス-🚀") is not None
    deps = g.get_dependencies("サービス-🚀")
    assert deps[0].id == "データベース-🗄️"
    s = g.summary()
    assert s["total_components"] == 2


def test_unknown_component_type_via_custom() -> None:
    """ComponentType.CUSTOM acts as the catch-all for unknown types."""
    g = InfraGraph()
    g.add_component(_comp("weird", ctype=ComponentType.CUSTOM))
    s = g.summary()
    types = s["component_types"]
    assert isinstance(types, dict)
    assert types.get("custom") == 1


def test_large_graph_under_limit() -> None:
    """1,000 nodes (10x smaller than the 10,000 cap to keep test fast)."""
    g = InfraGraph()
    for i in range(1000):
        g.add_component(_comp(f"n{i}"))
    assert len(g.components) == 1000
    s = g.summary()
    assert s["total_components"] == 1000


def test_dependency_to_unknown_target_does_not_crash_resilience_v2() -> None:
    g = InfraGraph()
    g.add_component(_comp("a"))
    g.add_dependency(_dep("a", "ghost"))  # dangling target
    out = g.resilience_score_v2()
    assert isinstance(out["score"], float)
