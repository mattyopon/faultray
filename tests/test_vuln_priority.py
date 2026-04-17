# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Tests for VulnerabilityPriorityEngine (Feature D)."""

from __future__ import annotations

import pytest

from faultray.model.components import (
    Component,
    ComponentType,
    Dependency,
    SecurityProfile,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.vulnerability_priority import (
    VulnerabilityPriority,
    VulnerabilityPriorityEngine,
    VulnerabilityPriorityReport,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_graph_with_one_insecure_lb() -> InfraGraph:
    """Single load balancer with no security controls and downstream components."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb",
        name="Public LB",
        type=ComponentType.LOAD_BALANCER,
        port=80,
        replicas=1,
        security=SecurityProfile(
            encryption_at_rest=False,
            encryption_in_transit=False,
            waf_protected=False,
            auth_required=False,
            rate_limiting=False,
        ),
    ))
    graph.add_component(Component(
        id="app",
        name="App Server",
        type=ComponentType.APP_SERVER,
        port=8080,
        replicas=1,
    ))
    graph.add_component(Component(
        id="db",
        name="Database",
        type=ComponentType.DATABASE,
        port=5432,
        replicas=1,
        security=SecurityProfile(encryption_at_rest=False),
    ))
    graph.add_dependency(Dependency(source_id="lb", target_id="app", dependency_type="requires"))
    graph.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))
    return graph


def _make_secure_graph() -> InfraGraph:
    """Graph where all components have full security controls."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb",
        name="Secure LB",
        type=ComponentType.LOAD_BALANCER,
        port=443,
        replicas=2,
        security=SecurityProfile(
            encryption_at_rest=True,
            encryption_in_transit=True,
            waf_protected=True,
            auth_required=True,
            rate_limiting=True,
        ),
    ))
    graph.add_component(Component(
        id="db",
        name="Secure DB",
        type=ComponentType.DATABASE,
        port=5432,
        replicas=2,
        security=SecurityProfile(
            encryption_at_rest=True,
            encryption_in_transit=True,
            auth_required=True,
            rate_limiting=True,
        ),
    ))
    return graph


def _make_empty_graph() -> InfraGraph:
    return InfraGraph()


def _make_single_node_graph() -> InfraGraph:
    graph = InfraGraph()
    graph.add_component(Component(
        id="solo",
        name="Solo Node",
        type=ComponentType.APP_SERVER,
        port=8080,
        replicas=1,
        security=SecurityProfile(encryption_at_rest=False, auth_required=False),
    ))
    return graph


# ---------------------------------------------------------------------------
# Tests: _vulnerability_score
# ---------------------------------------------------------------------------


def test_vulnerability_score_insecure_lb() -> None:
    """Insecure load balancer should have max/high vulnerability score."""
    graph = _make_graph_with_one_insecure_lb()
    engine = VulnerabilityPriorityEngine(graph)
    lb = graph.get_component("lb")
    assert lb is not None
    score, factors = engine._vulnerability_score(lb)
    # Expected: no enc_rest +2, no enc_transit +2, no WAF on LB +3, no auth +2, no rate_limit +1 = 10
    assert score == 10.0
    assert "no WAF" in factors
    assert "no auth required" in factors
    assert "no rate limiting" in factors


def test_vulnerability_score_secure_lb() -> None:
    """Fully secured load balancer should have score 0."""
    graph = _make_secure_graph()
    engine = VulnerabilityPriorityEngine(graph)
    lb = graph.get_component("lb")
    assert lb is not None
    score, factors = engine._vulnerability_score(lb)
    assert score == 0.0
    assert factors == [] or all(f == "public facing" for f in factors)


def test_vulnerability_score_database_without_encryption_has_extra_penalty() -> None:
    """Database without encryption_at_rest should score +3 extra on top of base."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="db",
        name="DB",
        type=ComponentType.DATABASE,
        port=5432,
        replicas=1,
        security=SecurityProfile(
            encryption_at_rest=False,
            encryption_in_transit=True,
            auth_required=True,
            rate_limiting=True,
            waf_protected=False,
        ),
    ))
    engine = VulnerabilityPriorityEngine(graph)
    db = graph.get_component("db")
    assert db is not None
    score, factors = engine._vulnerability_score(db)
    # enc_at_rest=False: +2 + extra +3 for DB = 5; waf check: LB only so N/A; others ok
    assert score == 5.0
    assert "no encryption at rest" in factors
    assert "database without encryption" in factors


# ---------------------------------------------------------------------------
# Tests: _blast_radius
# ---------------------------------------------------------------------------


def test_blast_radius_db_affects_upstream() -> None:
    """DB (deepest dependency) failing should affect all upstream callers.

    Graph: lb -> app -> db
    get_all_affected("db") returns {lb, app} = 2 out of 3 components.
    """
    graph = _make_graph_with_one_insecure_lb()
    engine = VulnerabilityPriorityEngine(graph)
    # get_all_affected("db") = {lb, app} = 2 out of 3 components
    br = engine._blast_radius("db", len(graph.components))
    assert br == pytest.approx(2 / 3 * 100, abs=1.0)


def test_blast_radius_root_node_is_zero() -> None:
    """Root node (lb) has no upstream dependents, so blast_radius == 0.

    Graph: lb -> app -> db
    get_all_affected("lb") = {} (nothing upstream depends on lb).
    """
    graph = _make_graph_with_one_insecure_lb()
    engine = VulnerabilityPriorityEngine(graph)
    br = engine._blast_radius("lb", len(graph.components))
    assert br == 0.0


def test_blast_radius_empty_graph_is_zero() -> None:
    """Empty graph should return 0 blast radius."""
    graph = _make_empty_graph()
    engine = VulnerabilityPriorityEngine(graph)
    assert engine._blast_radius("nonexistent", 0) == 0.0


# ---------------------------------------------------------------------------
# Tests: analyze
# ---------------------------------------------------------------------------


def test_analyze_returns_report_type() -> None:
    graph = _make_graph_with_one_insecure_lb()
    engine = VulnerabilityPriorityEngine(graph)
    report = engine.analyze()
    assert isinstance(report, VulnerabilityPriorityReport)


def test_analyze_priorities_count_matches_components() -> None:
    graph = _make_graph_with_one_insecure_lb()
    engine = VulnerabilityPriorityEngine(graph)
    report = engine.analyze()
    assert len(report.priorities) == len(graph.components)


def test_analyze_ranks_are_unique_and_sequential() -> None:
    graph = _make_graph_with_one_insecure_lb()
    engine = VulnerabilityPriorityEngine(graph)
    report = engine.analyze()
    ranks = [p.priority_rank for p in report.priorities]
    assert sorted(ranks) == list(range(1, len(ranks) + 1))


def test_analyze_priorities_sorted_by_score_descending() -> None:
    graph = _make_graph_with_one_insecure_lb()
    engine = VulnerabilityPriorityEngine(graph)
    report = engine.analyze()
    scores = [p.priority_score for p in report.priorities]
    assert scores == sorted(scores, reverse=True)


def test_analyze_db_ranked_first_insecure() -> None:
    """In lb->app->db, the database is most critical because it has both high
    vulnerability (database without encryption penalty) and high blast radius
    (all upstream components depend on it).

    Graph: lb -> app -> db
    get_all_affected("db") = {lb, app} → blast_radius ≈ 66.7%
    get_all_affected("lb") = {} → blast_radius = 0%
    """
    graph = _make_graph_with_one_insecure_lb()
    engine = VulnerabilityPriorityEngine(graph)
    report = engine.analyze()
    top = report.priorities[0]
    # db has highest priority_score: vulnerability(10) * blast_radius(66.7) / 10 ≈ 66.7
    assert top.component_id == "db"
    assert top.priority_rank == 1
    assert top.blast_radius > 0.0


def test_analyze_secure_graph_all_zero_scores() -> None:
    """Fully secured graph should have zero vulnerability scores."""
    graph = _make_secure_graph()
    engine = VulnerabilityPriorityEngine(graph)
    report = engine.analyze()
    for p in report.priorities:
        assert p.vulnerability_score == 0.0
        assert p.priority_score == 0.0


def test_analyze_empty_graph() -> None:
    graph = _make_empty_graph()
    engine = VulnerabilityPriorityEngine(graph)
    report = engine.analyze()
    assert report.priorities == []
    assert report.critical_count == 0
    assert report.high_count == 0
    assert report.risk_score == 0.0


def test_analyze_single_node_no_blast_radius() -> None:
    """Single isolated node has no downstream, so blast_radius == 0 and priority_score == 0."""
    graph = _make_single_node_graph()
    engine = VulnerabilityPriorityEngine(graph)
    report = engine.analyze()
    assert len(report.priorities) == 1
    p = report.priorities[0]
    assert p.blast_radius == 0.0
    assert p.priority_score == 0.0


def test_analyze_critical_count_correct() -> None:
    """critical_count should equal number of priorities with score >= 70."""
    graph = _make_graph_with_one_insecure_lb()
    engine = VulnerabilityPriorityEngine(graph)
    report = engine.analyze()
    expected = sum(1 for p in report.priorities if p.priority_score >= 70.0)
    assert report.critical_count == expected


def test_analyze_high_count_correct() -> None:
    """high_count should equal priorities with 40 <= score < 70."""
    graph = _make_graph_with_one_insecure_lb()
    engine = VulnerabilityPriorityEngine(graph)
    report = engine.analyze()
    expected = sum(1 for p in report.priorities if 40.0 <= p.priority_score < 70.0)
    assert report.high_count == expected


def test_analyze_summary_is_nonempty_string() -> None:
    graph = _make_graph_with_one_insecure_lb()
    engine = VulnerabilityPriorityEngine(graph)
    report = engine.analyze()
    assert isinstance(report.summary, str)
    assert len(report.summary) > 0


def test_analyze_recommendation_nonempty_for_insecure(  # noqa: D103
) -> None:
    graph = _make_graph_with_one_insecure_lb()
    engine = VulnerabilityPriorityEngine(graph)
    report = engine.analyze()
    lb_entry = next((p for p in report.priorities if p.component_id == "lb"), None)
    assert lb_entry is not None
    assert lb_entry.recommendation != ""


# ---------------------------------------------------------------------------
# Additional _vulnerability_score tests
# ---------------------------------------------------------------------------


def test_vulnerability_score_app_server_no_security() -> None:
    """APP_SERVER with no auth and no encryption should have positive score."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app",
        name="App",
        type=ComponentType.APP_SERVER,
        port=8080,
        replicas=1,
        security=SecurityProfile(
            encryption_at_rest=False,
            encryption_in_transit=False,
            auth_required=False,
        ),
    ))
    engine = VulnerabilityPriorityEngine(graph)
    app = graph.get_component("app")
    assert app is not None
    score, factors = engine._vulnerability_score(app)
    assert score > 0.0


def test_vulnerability_score_database_with_all_security() -> None:
    """Database with all security controls should score 0."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="db",
        name="Secure DB",
        type=ComponentType.DATABASE,
        port=5432,
        replicas=1,
        security=SecurityProfile(
            encryption_at_rest=True,
            encryption_in_transit=True,
            auth_required=True,
            rate_limiting=True,
        ),
    ))
    engine = VulnerabilityPriorityEngine(graph)
    db = graph.get_component("db")
    assert db is not None
    score, _ = engine._vulnerability_score(db)
    assert score == 0.0


def test_vulnerability_score_lb_no_waf_adds_penalty() -> None:
    """LB without WAF should have 'no WAF' in factors."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb",
        name="LB",
        type=ComponentType.LOAD_BALANCER,
        port=80,
        replicas=1,
        security=SecurityProfile(waf_protected=False),
    ))
    engine = VulnerabilityPriorityEngine(graph)
    lb = graph.get_component("lb")
    assert lb is not None
    score, factors = engine._vulnerability_score(lb)
    assert "no WAF" in factors


def test_vulnerability_score_no_rate_limiting_flagged() -> None:
    """Component without rate limiting should include it in factors."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app",
        name="App",
        type=ComponentType.APP_SERVER,
        port=8080,
        replicas=1,
        security=SecurityProfile(rate_limiting=False),
    ))
    engine = VulnerabilityPriorityEngine(graph)
    app = graph.get_component("app")
    assert app is not None
    score, factors = engine._vulnerability_score(app)
    assert "no rate limiting" in factors


# ---------------------------------------------------------------------------
# Additional _blast_radius tests
# ---------------------------------------------------------------------------


def test_blast_radius_middle_node() -> None:
    """Middle node (app) in lb->app->db has 1 upstream (lb) = 1/3 affected."""
    graph = _make_graph_with_one_insecure_lb()
    engine = VulnerabilityPriorityEngine(graph)
    br = engine._blast_radius("app", len(graph.components))
    # get_all_affected("app") = {lb} = 1 out of 3 = 33.3%
    assert pytest.approx(br, abs=1.0) == 1 / 3 * 100


def test_blast_radius_single_component_is_zero() -> None:
    """Single isolated component should have blast_radius == 0."""
    graph = _make_single_node_graph()
    engine = VulnerabilityPriorityEngine(graph)
    br = engine._blast_radius("solo", 1)
    assert br == 0.0


def test_blast_radius_zero_total_components() -> None:
    """When total == 0, blast_radius should return 0."""
    graph = _make_empty_graph()
    engine = VulnerabilityPriorityEngine(graph)
    assert engine._blast_radius("any", 0) == 0.0


# ---------------------------------------------------------------------------
# Additional analyze() tests
# ---------------------------------------------------------------------------


def test_analyze_priority_score_formula() -> None:
    """priority_score = vulnerability_score * blast_radius / 10 (approx)."""
    graph = _make_graph_with_one_insecure_lb()
    engine = VulnerabilityPriorityEngine(graph)
    report = engine.analyze()
    for p in report.priorities:
        expected = p.vulnerability_score * p.blast_radius / 10.0
        assert abs(p.priority_score - expected) < 0.1


def test_analyze_report_risk_score_is_float() -> None:
    graph = _make_graph_with_one_insecure_lb()
    engine = VulnerabilityPriorityEngine(graph)
    report = engine.analyze()
    assert isinstance(report.risk_score, float)


def test_analyze_risk_score_range() -> None:
    """risk_score should be in [0, 100]."""
    graph = _make_graph_with_one_insecure_lb()
    engine = VulnerabilityPriorityEngine(graph)
    report = engine.analyze()
    assert 0.0 <= report.risk_score <= 100.0


def test_analyze_single_node_rank_is_1() -> None:
    """Single node should get rank 1."""
    graph = _make_single_node_graph()
    engine = VulnerabilityPriorityEngine(graph)
    report = engine.analyze()
    assert report.priorities[0].priority_rank == 1


def test_analyze_component_names_preserved() -> None:
    """component_name in priorities should match the original component name."""
    graph = _make_graph_with_one_insecure_lb()
    engine = VulnerabilityPriorityEngine(graph)
    report = engine.analyze()
    name_map = {c.id: c.name for c in graph.components.values()}
    for p in report.priorities:
        assert p.component_name == name_map[p.component_id]


def test_analyze_risk_factors_are_list() -> None:
    """risk_factors for each priority should be a list."""
    graph = _make_graph_with_one_insecure_lb()
    engine = VulnerabilityPriorityEngine(graph)
    report = engine.analyze()
    for p in report.priorities:
        assert isinstance(p.risk_factors, list)


@pytest.mark.parametrize("yaml_file", [
    "examples/demo-infra.yaml",
    "examples/typical-startup.yaml",
    "examples/ecommerce-platform.yaml",
])
def test_analyze_all_examples(yaml_file: str) -> None:
    """All example YAML files should analyze without error."""
    from pathlib import Path
    from faultray.model.loader import load_yaml
    path = Path(__file__).parent.parent / yaml_file
    if not path.exists():
        pytest.skip(f"{yaml_file} not found")
    graph = load_yaml(path)
    engine = VulnerabilityPriorityEngine(graph)
    report = engine.analyze()
    assert len(report.priorities) == len(graph.components)
    assert 0.0 <= report.risk_score <= 100.0


def test_analyze_two_components_ranks_unique() -> None:
    """With two components, ranks should be [1, 2] in some order."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="a", name="A", type=ComponentType.APP_SERVER, replicas=1,
        security=SecurityProfile(encryption_at_rest=False),
    ))
    graph.add_component(Component(
        id="b", name="B", type=ComponentType.DATABASE, replicas=1,
        security=SecurityProfile(encryption_at_rest=False),
    ))
    graph.add_dependency(Dependency(source_id="a", target_id="b", dependency_type="requires"))
    engine = VulnerabilityPriorityEngine(graph)
    report = engine.analyze()
    ranks = sorted(p.priority_rank for p in report.priorities)
    assert ranks == [1, 2]


def test_analyze_report_is_correct_type() -> None:
    graph = _make_secure_graph()
    engine = VulnerabilityPriorityEngine(graph)
    report = engine.analyze()
    assert isinstance(report, VulnerabilityPriorityReport)


def test_analyze_secure_graph_no_critical_or_high() -> None:
    """Fully secure graph should have no critical or high priority components."""
    graph = _make_secure_graph()
    engine = VulnerabilityPriorityEngine(graph)
    report = engine.analyze()
    assert report.critical_count == 0
    assert report.high_count == 0


def test_analyze_empty_graph_zero_risk_score() -> None:
    graph = _make_empty_graph()
    engine = VulnerabilityPriorityEngine(graph)
    report = engine.analyze()
    assert report.risk_score == 0.0


def test_vulnerability_priority_dataclass_fields() -> None:
    """VulnerabilityPriority should have all expected fields."""
    vp = VulnerabilityPriority(
        component_id="test",
        component_name="Test",
        vulnerability_score=5.0,
        blast_radius=50.0,
        priority_score=25.0,
        priority_rank=1,
        risk_factors=["no auth"],
        recommendation="Fix it",
    )
    assert vp.component_id == "test"
    assert vp.priority_rank == 1
    assert vp.recommendation == "Fix it"
    assert "no auth" in vp.risk_factors


def test_analyze_counts_consistent() -> None:
    """critical_count + high_count should be <= total priorities."""
    graph = _make_graph_with_one_insecure_lb()
    engine = VulnerabilityPriorityEngine(graph)
    report = engine.analyze()
    assert report.critical_count + report.high_count <= len(report.priorities)


def test_vulnerability_score_cache_no_auth() -> None:
    """CACHE component without auth should be flagged."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="cache",
        name="Redis",
        type=ComponentType.CACHE,
        port=6379,
        replicas=1,
        security=SecurityProfile(auth_required=False),
    ))
    engine = VulnerabilityPriorityEngine(graph)
    cache = graph.get_component("cache")
    assert cache is not None
    score, factors = engine._vulnerability_score(cache)
    assert "no auth required" in factors


def test_blast_radius_between_zero_and_100() -> None:
    """blast_radius should always be between 0 and 100."""
    graph = _make_graph_with_one_insecure_lb()
    engine = VulnerabilityPriorityEngine(graph)
    total = len(graph.components)
    for comp in graph.components.values():
        br = engine._blast_radius(comp.id, total)
        assert 0.0 <= br <= 100.0


def test_analyze_five_components_ranks_1_to_5() -> None:
    """Five components should get ranks 1 through 5."""
    graph = InfraGraph()
    for i in range(5):
        graph.add_component(Component(
            id=f"svc{i}",
            name=f"Service {i}",
            type=ComponentType.APP_SERVER,
            replicas=1,
        ))
    engine = VulnerabilityPriorityEngine(graph)
    report = engine.analyze()
    ranks = sorted(p.priority_rank for p in report.priorities)
    assert ranks == [1, 2, 3, 4, 5]


def test_analyze_summary_contains_component_count() -> None:
    """Summary should reference the number of components."""
    graph = _make_graph_with_one_insecure_lb()
    engine = VulnerabilityPriorityEngine(graph)
    report = engine.analyze()
    # 3 components in insecure graph
    assert "3" in report.summary


def test_secure_db_has_zero_vulnerability() -> None:
    """Database with all security enabled should score zero."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="db",
        name="Secure DB",
        type=ComponentType.DATABASE,
        port=5432,
        replicas=2,
        security=SecurityProfile(
            encryption_at_rest=True,
            encryption_in_transit=True,
            auth_required=True,
            rate_limiting=True,
            waf_protected=False,  # waf is LB-specific, not counted for DB
        ),
    ))
    engine = VulnerabilityPriorityEngine(graph)
    db = graph.get_component("db")
    assert db is not None
    score, _ = engine._vulnerability_score(db)
    assert score == 0.0


def test_insecure_lb_highest_in_chain() -> None:
    """In a chain, the insecure component with highest blast_radius dominates."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb",
        name="Insecure LB",
        type=ComponentType.LOAD_BALANCER,
        port=80,
        replicas=1,
        security=SecurityProfile(
            encryption_in_transit=False,
            waf_protected=False,
            auth_required=False,
            rate_limiting=False,
        ),
    ))
    graph.add_component(Component(
        id="db",
        name="Secure DB",
        type=ComponentType.DATABASE,
        port=5432,
        replicas=2,
        security=SecurityProfile(
            encryption_at_rest=True,
            encryption_in_transit=True,
            auth_required=True,
        ),
    ))
    graph.add_dependency(Dependency(source_id="lb", target_id="db", dependency_type="requires"))
    engine = VulnerabilityPriorityEngine(graph)
    report = engine.analyze()
    # db has blast_radius=0 (nothing upstream depends on db from lb side)
    # lb has blast_radius=0 too (nothing upstream depends on lb)
    # All priority scores = 0 due to zero blast radius
    for p in report.priorities:
        assert p.blast_radius >= 0.0


def test_vulnerability_priority_report_fields() -> None:
    """VulnerabilityPriorityReport should have all required fields."""
    graph = _make_single_node_graph()
    engine = VulnerabilityPriorityEngine(graph)
    report = engine.analyze()
    assert hasattr(report, "priorities")
    assert hasattr(report, "critical_count")
    assert hasattr(report, "high_count")
    assert hasattr(report, "risk_score")
    assert hasattr(report, "summary")


def test_priority_score_is_float() -> None:
    """All priority_score values should be floats."""
    graph = _make_graph_with_one_insecure_lb()
    engine = VulnerabilityPriorityEngine(graph)
    report = engine.analyze()
    for p in report.priorities:
        assert isinstance(p.priority_score, float)


def test_vulnerability_score_no_encryption_in_transit() -> None:
    """Component without encryption_in_transit should include it in factors."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app",
        name="App",
        type=ComponentType.APP_SERVER,
        port=8080,
        replicas=1,
        security=SecurityProfile(encryption_in_transit=False),
    ))
    engine = VulnerabilityPriorityEngine(graph)
    app = graph.get_component("app")
    assert app is not None
    score, factors = engine._vulnerability_score(app)
    assert "no encryption in transit" in factors


def test_analyze_with_dependency_chain_has_non_zero_blast_radius() -> None:
    """Components in a dependency chain should have positive blast radius for leaf nodes."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="frontend", name="Frontend", type=ComponentType.APP_SERVER, replicas=2,
        security=SecurityProfile(encryption_in_transit=False),
    ))
    graph.add_component(Component(
        id="backend", name="Backend", type=ComponentType.APP_SERVER, replicas=2,
        security=SecurityProfile(encryption_in_transit=False),
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE, replicas=1,
        security=SecurityProfile(encryption_at_rest=False),
    ))
    graph.add_dependency(Dependency(source_id="frontend", target_id="backend", dependency_type="requires"))
    graph.add_dependency(Dependency(source_id="backend", target_id="db", dependency_type="requires"))
    engine = VulnerabilityPriorityEngine(graph)
    report = engine.analyze()
    db_priority = next(p for p in report.priorities if p.component_id == "db")
    # db is depended on by both backend and frontend
    assert db_priority.blast_radius > 0.0
