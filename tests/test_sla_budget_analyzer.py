# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Tests for SLA Budget Analyzer (Error Budget / Burn Rate)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from faultray.model.components import Component, ComponentType, SLOTarget
from faultray.model.graph import InfraGraph
from faultray.simulator.sla_budget_analyzer import (
    SLABudgetAnalyzer,
    SLABudgetReport,
    SLABudgetStatus,
    _allowed_minutes,
    _status,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REF_TIME = datetime(2026, 4, 15, 12, 0, 0, tzinfo=timezone.utc)  # day 15 of month


def _comp(comp_id: str, slo: float | None = None) -> Component:
    c = Component(id=comp_id, name=comp_id, type=ComponentType.APP_SERVER)
    if slo is not None:
        c.slo_targets = [SLOTarget(name="availability", metric="availability", target=slo)]
    return c


def _graph(*components: Component) -> InfraGraph:
    g = InfraGraph()
    for c in components:
        g.add_component(c)
    return g


# ---------------------------------------------------------------------------
# Unit tests: helpers
# ---------------------------------------------------------------------------


def test_allowed_minutes_99_9():
    # 30 days * 24h * 60min * 0.001 = 43.2 minutes
    result = _allowed_minutes(99.9, 30)
    assert abs(result - 43.2) < 0.01


def test_allowed_minutes_99_99():
    result = _allowed_minutes(99.99, 30)
    assert abs(result - 4.32) < 0.01


def test_allowed_minutes_100_percent_zero():
    assert _allowed_minutes(100.0, 30) == 0.0


def test_status_healthy():
    assert _status(0.8) == "healthy"


def test_status_warning():
    assert _status(0.3) == "warning"


def test_status_critical():
    assert _status(0.1) == "critical"


def test_status_exhausted():
    assert _status(0.0) == "exhausted"


# ---------------------------------------------------------------------------
# Analyzer tests
# ---------------------------------------------------------------------------


def test_empty_graph_returns_empty_report():
    report = SLABudgetAnalyzer().analyze(InfraGraph(), reference_time=_REF_TIME)
    assert report.budgets == []
    assert report.overall_status == "healthy"


def test_zero_incidents_healthy():
    g = _graph(_comp("app"))
    report = SLABudgetAnalyzer().analyze(g, incidents_per_component=0, reference_time=_REF_TIME)
    assert len(report.budgets) == 1
    assert report.budgets[0].consumed_downtime_minutes == 0.0
    assert report.budgets[0].status == "healthy"


def test_incidents_consumed_budget():
    g = _graph(_comp("app"))
    report = SLABudgetAnalyzer().analyze(g, incidents_per_component=1, reference_time=_REF_TIME)
    # 1 incident = 30 minutes consumed
    assert report.budgets[0].consumed_downtime_minutes == 30.0


def test_budget_decreases_with_incidents():
    g = _graph(_comp("app"))
    r0 = SLABudgetAnalyzer().analyze(g, incidents_per_component=0, reference_time=_REF_TIME)
    r1 = SLABudgetAnalyzer().analyze(g, incidents_per_component=1, reference_time=_REF_TIME)
    assert r1.budgets[0].remaining_minutes < r0.budgets[0].remaining_minutes


def test_many_incidents_exhausted():
    g = _graph(_comp("app"))
    # 99.9% SLO = 43.2 min/month. 2 incidents = 60 min → exhausted
    report = SLABudgetAnalyzer().analyze(g, incidents_per_component=2, reference_time=_REF_TIME)
    assert report.budgets[0].status == "exhausted"


def test_custom_slo_respected():
    g = _graph(_comp("app", slo=99.0))
    # 99.0% SLO = 30*24*60*0.01 = 432 minutes
    report = SLABudgetAnalyzer().analyze(g, incidents_per_component=0, reference_time=_REF_TIME)
    assert abs(report.budgets[0].allowed_downtime_minutes - 432.0) < 0.5


def test_burn_rate_zero_for_no_incidents():
    g = _graph(_comp("app"))
    report = SLABudgetAnalyzer().analyze(g, incidents_per_component=0, reference_time=_REF_TIME)
    assert report.budgets[0].burn_rate == 0.0


def test_burn_rate_high_for_many_incidents():
    g = _graph(_comp("app"))
    report = SLABudgetAnalyzer().analyze(g, incidents_per_component=3, reference_time=_REF_TIME)
    # Should be burning much faster than 1x
    assert report.budgets[0].burn_rate > 1.0


def test_days_until_exhaustion_none_for_zero_incidents():
    g = _graph(_comp("app"))
    report = SLABudgetAnalyzer().analyze(g, incidents_per_component=0, reference_time=_REF_TIME)
    assert report.budgets[0].days_until_exhaustion is None


def test_days_until_exhaustion_set_for_incidents():
    g = _graph(_comp("app"))
    report = SLABudgetAnalyzer().analyze(g, incidents_per_component=1, reference_time=_REF_TIME)
    b = report.budgets[0]
    if b.remaining_minutes > 0:
        assert b.days_until_exhaustion is not None


def test_overall_status_worst():
    """overall_status should reflect the worst component status."""
    g = _graph(_comp("app1"), _comp("app2"))
    report = SLABudgetAnalyzer().analyze(g, incidents_per_component=2, reference_time=_REF_TIME)
    assert report.overall_status == "exhausted"


def test_to_dict_structure():
    g = _graph(_comp("app"))
    report = SLABudgetAnalyzer().analyze(g, reference_time=_REF_TIME)
    d = report.to_dict()
    assert "overall_status" in d
    assert "summary" in d
    assert "budgets" in d
    assert isinstance(d["budgets"], list)
    budget_dict = d["budgets"][0]
    assert "component_id" in budget_dict
    assert "slo_target" in budget_dict
    assert "allowed_downtime_minutes" in budget_dict
    assert "consumed_downtime_minutes" in budget_dict
    assert "remaining_minutes" in budget_dict
    assert "burn_rate" in budget_dict
    assert "status" in budget_dict
    assert "days_until_exhaustion" in budget_dict


def test_demo_infra_yaml_loads():
    """The bundled demo-infra.yaml should load and produce a budget report."""
    from faultray.model.loader import load_yaml
    sample = Path(__file__).parent.parent / "examples" / "demo-infra.yaml"
    if not sample.exists():
        pytest.skip("demo-infra.yaml not found")
    graph = load_yaml(sample)
    report = SLABudgetAnalyzer().analyze(graph, reference_time=_REF_TIME)
    assert len(report.budgets) == len(graph.components)
    assert report.overall_status in ("healthy", "warning", "critical", "exhausted")
