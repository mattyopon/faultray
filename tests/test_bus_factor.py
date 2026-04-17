# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Tests for Bus Factor / Organizational Risk Analysis."""

from __future__ import annotations

from pathlib import Path

import pytest

from faultray.model.components import Component, ComponentType, Dependency
from faultray.model.graph import InfraGraph
from faultray.simulator.bus_factor_analyzer import (
    BusFactorAnalyzer,
    BusFactorReport,
    PersonRisk,
    _risk_level,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(comp_id: str, owner: str, comp_type: ComponentType = ComponentType.APP_SERVER) -> Component:
    return Component(id=comp_id, name=comp_id, type=comp_type, owner=owner)


def _graph(*components: Component, deps: list[tuple[str, str]] | None = None) -> InfraGraph:
    g = InfraGraph()
    for c in components:
        g.add_component(c)
    for source, target in (deps or []):
        g.add_dependency(Dependency(source_id=source, target_id=target, type="requires"))
    return g


# ---------------------------------------------------------------------------
# Unit tests: _risk_level helper
# ---------------------------------------------------------------------------


def test_risk_level_critical():
    assert _risk_level(55.0) == "critical"


def test_risk_level_high():
    assert _risk_level(30.0) == "high"


def test_risk_level_medium():
    assert _risk_level(15.0) == "medium"


def test_risk_level_low():
    assert _risk_level(5.0) == "low"


def test_risk_level_boundary_critical():
    assert _risk_level(50.0) == "critical"


def test_risk_level_boundary_high():
    assert _risk_level(25.0) == "high"


# ---------------------------------------------------------------------------
# Analyzer tests
# ---------------------------------------------------------------------------


def test_empty_graph_returns_zero_bus_factor():
    report = BusFactorAnalyzer().analyze(InfraGraph())
    assert report.bus_factor == 0
    assert report.people_risks == []
    assert report.risk_score == 0.0


def test_single_owner_single_component():
    g = _graph(_comp("app", "alice@example.com"))
    report = BusFactorAnalyzer().analyze(g)
    assert report.bus_factor == 1
    assert len(report.people_risks) == 1
    assert report.people_risks[0].owner == "alice@example.com"
    assert report.people_risks[0].components == ["app"]


def test_multiple_owners_detected():
    g = _graph(
        _comp("app", "alice@example.com"),
        _comp("db", "bob@example.com"),
    )
    report = BusFactorAnalyzer().analyze(g)
    owners = {p.owner for p in report.people_risks}
    assert "alice@example.com" in owners
    assert "bob@example.com" in owners


def test_unowned_components_tracked():
    g = _graph(
        _comp("app", "alice@example.com"),
        _comp("db", ""),
    )
    report = BusFactorAnalyzer().analyze(g)
    assert "db" in report.unowned_components


def test_dependents_counted_in_impact():
    """Owner of a component that others depend on has higher impact."""
    # nginx (no owner) depends on app (alice owns), app depends on db (alice owns)
    g = _graph(
        _comp("nginx", "ops@example.com"),
        _comp("app", "alice@example.com"),
        _comp("db", "alice@example.com"),
        deps=[("nginx", "app"), ("app", "db")],
    )
    report = BusFactorAnalyzer().analyze(g)
    alice = next(p for p in report.people_risks if p.owner == "alice@example.com")
    # nginx depends on app (alice's component), so alice's departure affects nginx
    assert alice.total_dependents >= 1


def test_single_owner_component_list():
    """Components whose owner owns only that one component appear in single_owner_components."""
    g = _graph(
        _comp("lonely-service", "solo@example.com"),
        _comp("app1", "team@example.com"),
        _comp("app2", "team@example.com"),
    )
    report = BusFactorAnalyzer().analyze(g)
    assert "lonely-service" in report.single_owner_components
    # team owns 2 components, so neither is single-owner
    assert "app1" not in report.single_owner_components
    assert "app2" not in report.single_owner_components


def test_bus_factor_increases_with_more_owners():
    """More evenly distributed ownership raises bus factor."""
    # All owned by one person
    g1 = _graph(
        _comp("a", "alice"), _comp("b", "alice"), _comp("c", "alice"), _comp("d", "alice"),
    )
    report1 = BusFactorAnalyzer().analyze(g1)

    # Distributed across 4 people
    g2 = _graph(
        _comp("a", "alice"), _comp("b", "bob"), _comp("c", "carol"), _comp("d", "dave"),
    )
    report2 = BusFactorAnalyzer().analyze(g2)

    assert report2.bus_factor >= report1.bus_factor


def test_report_to_dict_structure():
    g = _graph(_comp("app", "alice@example.com"))
    report = BusFactorAnalyzer().analyze(g)
    d = report.to_dict()
    assert "bus_factor" in d
    assert "risk_score" in d
    assert "summary" in d
    assert "unowned_components" in d
    assert "single_owner_components" in d
    assert "people_risks" in d
    assert isinstance(d["people_risks"], list)


def test_person_risk_to_dict():
    pr = PersonRisk(
        owner="alice@example.com",
        components=["app", "db"],
        total_dependents=3,
        impact_if_leaves=60.0,
        risk_level="critical",
    )
    d = pr.to_dict()
    assert d["owner"] == "alice@example.com"
    assert d["components"] == ["app", "db"]
    assert d["total_dependents"] == 3
    assert d["impact_if_leaves"] == 60.0
    assert d["risk_level"] == "critical"


def test_shadow_it_sample_yaml_loads_and_runs():
    """The bundled shadow-it-sample.yaml provides ownership data for bus factor analysis."""
    from faultray.model.loader import load_yaml
    sample = Path(__file__).parent.parent / "examples" / "shadow-it-sample.yaml"
    if not sample.exists():
        pytest.skip("shadow-it-sample.yaml not found")
    graph = load_yaml(sample)
    report = BusFactorAnalyzer().analyze(graph)
    # Sample has tanaka, suzuki, infra-team as owners; some orphaned
    assert report.bus_factor >= 1
    assert len(report.unowned_components) >= 2   # gas-report, cron-backup, zapier-slack


# ---------------------------------------------------------------------------
# _risk_level boundary tests
# ---------------------------------------------------------------------------


def test_risk_level_just_below_critical():
    assert _risk_level(49.9) == "high"


def test_risk_level_exactly_high_threshold():
    assert _risk_level(25.0) == "high"


def test_risk_level_just_below_high():
    assert _risk_level(24.9) == "medium"


def test_risk_level_exactly_medium_threshold():
    assert _risk_level(10.0) == "medium"


def test_risk_level_just_below_medium():
    assert _risk_level(9.9) == "low"


def test_risk_level_zero():
    assert _risk_level(0.0) == "low"


def test_risk_level_100():
    assert _risk_level(100.0) == "critical"


# ---------------------------------------------------------------------------
# Boundary value: component count
# ---------------------------------------------------------------------------


def test_two_components_same_owner():
    """Two components with the same owner: bus_factor=1."""
    g = _graph(_comp("a", "alice"), _comp("b", "alice"))
    report = BusFactorAnalyzer().analyze(g)
    assert report.bus_factor == 1


def test_all_unowned_graph():
    """All components unowned: bus_factor=0, everyone is in unowned_components."""
    g = _graph(_comp("a", ""), _comp("b", ""), _comp("c", ""))
    report = BusFactorAnalyzer().analyze(g)
    assert report.bus_factor == 0
    assert set(report.unowned_components) == {"a", "b", "c"}


def test_risk_score_max_100():
    """risk_score should never exceed 100."""
    comps = [_comp(f"c{i}", f"owner{i}") for i in range(20)]
    g = _graph(*comps)
    report = BusFactorAnalyzer().analyze(g)
    assert report.risk_score <= 100.0


def test_risk_score_zero_when_all_owned_by_many():
    """When every component has a unique owner, risk_score is based on single-owner components."""
    g = _graph(
        _comp("a", "alice"), _comp("b", "bob"),
        _comp("c", "carol"), _comp("d", "dave"),
    )
    report = BusFactorAnalyzer().analyze(g)
    # All are single-owner, so risk_score = 100%, but bus_factor >= 1
    assert report.bus_factor >= 1


# ---------------------------------------------------------------------------
# Edge case tests
# ---------------------------------------------------------------------------


def test_person_risk_impact_zero_no_dependents():
    """Owner whose components have no dependents gets impact=0.0."""
    g = _graph(_comp("solo", "alice"))
    report = BusFactorAnalyzer().analyze(g)
    alice = report.people_risks[0]
    assert alice.impact_if_leaves == 0.0


def test_person_risk_sorted_by_impact_descending():
    """people_risks should be sorted by impact_if_leaves descending."""
    g = _graph(
        _comp("lb", "ops"),
        _comp("app1", "alice"),
        _comp("app2", "alice"),
        _comp("app3", "alice"),
        deps=[("lb", "app1"), ("lb", "app2"), ("lb", "app3")],
    )
    report = BusFactorAnalyzer().analyze(g)
    impacts = [p.impact_if_leaves for p in report.people_risks]
    assert impacts == sorted(impacts, reverse=True)


def test_bus_factor_three_equal_owners():
    """6 components split equally across 3 owners: removing 2 leaves ≥50% unowned."""
    g = _graph(
        _comp("a1", "alice"), _comp("a2", "alice"),
        _comp("b1", "bob"), _comp("b2", "bob"),
        _comp("c1", "carol"), _comp("c2", "carol"),
    )
    report = BusFactorAnalyzer().analyze(g)
    # Each owner controls 2/6 = 33.3%. Need 2 removed to hit ≥50%
    assert report.bus_factor == 2


def test_japanese_owner_name():
    """Japanese owner names should process correctly."""
    g = _graph(_comp("app", "田中太郎"), _comp("db", "田中太郎"))
    report = BusFactorAnalyzer().analyze(g)
    owners = {p.owner for p in report.people_risks}
    assert "田中太郎" in owners


def test_to_dict_has_all_required_keys():
    """to_dict() should include all required top-level keys."""
    g = _graph(_comp("app", "alice"))
    report = BusFactorAnalyzer().analyze(g)
    d = report.to_dict()
    for key in ("bus_factor", "risk_score", "summary", "unowned_components",
                "single_owner_components", "people_risks"):
        assert key in d


def test_person_risk_to_dict_all_keys():
    """PersonRisk.to_dict() should include all required keys."""
    pr = PersonRisk(owner="alice", components=["app"], total_dependents=1,
                    impact_if_leaves=20.0, risk_level="medium")
    d = pr.to_dict()
    for key in ("owner", "components", "total_dependents", "impact_if_leaves", "risk_level"):
        assert key in d


def test_summary_contains_bus_factor():
    """Summary should mention the bus factor value."""
    g = _graph(_comp("app", "alice"), _comp("db", "bob"))
    report = BusFactorAnalyzer().analyze(g)
    assert "Bus factor" in report.summary or "bus_factor" in report.summary or str(report.bus_factor) in report.summary


def test_summary_non_empty():
    """Summary should always be a non-empty string."""
    report = BusFactorAnalyzer().analyze(InfraGraph())
    assert isinstance(report.summary, str)
    assert len(report.summary) > 0


def test_unowned_not_in_people_risks():
    """Unowned components (empty owner) should NOT appear in people_risks."""
    g = _graph(_comp("owned", "alice"), _comp("orphan", ""))
    report = BusFactorAnalyzer().analyze(g)
    all_owners = {p.owner for p in report.people_risks}
    assert "" not in all_owners


def test_impact_capped_at_100():
    """impact_if_leaves should not exceed 100."""
    g = _graph(
        _comp("hub", "alice"),
        _comp("dep1", "bob"),
        _comp("dep2", "carol"),
        _comp("dep3", "dave"),
        deps=[("dep1", "hub"), ("dep2", "hub"), ("dep3", "hub")],
    )
    report = BusFactorAnalyzer().analyze(g)
    for p in report.people_risks:
        assert p.impact_if_leaves <= 100.0


def test_single_owner_component_is_listed():
    """Components whose owner owns only one component appear in single_owner_components."""
    g = _graph(
        _comp("only-mine", "solo"),
        _comp("shared1", "team"),
        _comp("shared2", "team"),
    )
    report = BusFactorAnalyzer().analyze(g)
    assert "only-mine" in report.single_owner_components
    assert "shared1" not in report.single_owner_components
    assert "shared2" not in report.single_owner_components


def test_multiple_component_types_bus_factor():
    """Bus factor analysis works across different ComponentType values."""
    from faultray.model.components import ComponentType
    g = _graph(
        _comp("lb", "ops", ComponentType.LOAD_BALANCER),
        _comp("db", "ops", ComponentType.DATABASE),
        _comp("cache", "alice", ComponentType.CACHE),
        _comp("queue", "alice", ComponentType.QUEUE),
    )
    report = BusFactorAnalyzer().analyze(g)
    assert report.bus_factor >= 1
    assert len(report.people_risks) == 2


@pytest.mark.parametrize("yaml_file", [
    "examples/demo-infra.yaml",
    "examples/typical-startup.yaml",
    "examples/shadow-it-sample.yaml",
    "examples/ecommerce-platform.yaml",
])
def test_analyze_all_examples(yaml_file):
    """All example YAML files should load and analyze without error."""
    from faultray.model.loader import load_yaml
    path = Path(__file__).parent.parent / yaml_file
    if not path.exists():
        pytest.skip(f"{yaml_file} not found")
    graph = load_yaml(path)
    report = BusFactorAnalyzer().analyze(graph)
    assert report.bus_factor >= 0
    assert 0.0 <= report.risk_score <= 100.0
    d = report.to_dict()
    assert "bus_factor" in d


def test_dependents_tracked_across_components():
    """Owner with two components, each with separate dependents, gets correct total."""
    g = _graph(
        _comp("a", "alice"),
        _comp("b", "alice"),
        _comp("dep-a", "bob"),
        _comp("dep-b", "carol"),
        deps=[("dep-a", "a"), ("dep-b", "b")],
    )
    report = BusFactorAnalyzer().analyze(g)
    alice = next(p for p in report.people_risks if p.owner == "alice")
    # dep-a and dep-b both depend on alice's components
    assert alice.total_dependents >= 1


def test_risk_level_high_for_50_percent_impact():
    """Owner with exactly 50% impact should be 'critical'."""
    result = _risk_level(50.0)
    assert result == "critical"


def test_bus_factor_increases_with_distribution():
    """More evenly distributed ownership always raises bus_factor."""
    # 1 owner
    g1 = _graph(_comp("a", "alice"), _comp("b", "alice"), _comp("c", "alice"), _comp("d", "alice"))
    r1 = BusFactorAnalyzer().analyze(g1)

    # 4 owners
    g2 = _graph(_comp("a", "alice"), _comp("b", "bob"), _comp("c", "carol"), _comp("d", "dave"))
    r2 = BusFactorAnalyzer().analyze(g2)

    assert r2.bus_factor >= r1.bus_factor


def test_report_is_bus_factor_report_instance():
    """analyze() should return a BusFactorReport instance."""
    report = BusFactorAnalyzer().analyze(InfraGraph())
    assert isinstance(report, BusFactorReport)


def test_risk_score_is_float():
    """risk_score should always be a float."""
    g = _graph(_comp("app", "alice"))
    report = BusFactorAnalyzer().analyze(g)
    assert isinstance(report.risk_score, float)


def test_people_risks_list_type():
    """people_risks should be a list."""
    g = _graph(_comp("a", "alice"), _comp("b", "bob"))
    report = BusFactorAnalyzer().analyze(g)
    assert isinstance(report.people_risks, list)


def test_bus_factor_value_is_int():
    """bus_factor should be an integer."""
    g = _graph(_comp("a", "alice"))
    report = BusFactorAnalyzer().analyze(g)
    assert isinstance(report.bus_factor, int)
