# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

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
