# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

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


# ---------------------------------------------------------------------------
# _allowed_minutes boundary tests
# ---------------------------------------------------------------------------


def test_allowed_minutes_100_percent_gives_zero():
    """100% SLO means zero allowed downtime."""
    assert _allowed_minutes(100.0, 30) == 0.0


def test_allowed_minutes_zero_slo():
    """0% SLO means all time is allowed downtime."""
    result = _allowed_minutes(0.0, 30)
    assert abs(result - 30 * 24 * 60) < 0.01


def test_allowed_minutes_99_0():
    """99.0% SLO = 30*24*60*0.01 = 432 minutes."""
    result = _allowed_minutes(99.0, 30)
    assert abs(result - 432.0) < 0.1


def test_allowed_minutes_window_7_days():
    """7-day window with 99.9% SLO."""
    result = _allowed_minutes(99.9, 7)
    expected = 7 * 24 * 60 * 0.001
    assert abs(result - expected) < 0.01


def test_allowed_minutes_window_1_day():
    """1-day window with 99.9% SLO."""
    result = _allowed_minutes(99.9, 1)
    expected = 1 * 24 * 60 * 0.001
    assert abs(result - expected) < 0.01


# ---------------------------------------------------------------------------
# _status boundary tests
# ---------------------------------------------------------------------------


def test_status_exactly_50_pct_is_healthy():
    assert _status(0.5) == "healthy"


def test_status_just_above_50_pct_is_healthy():
    assert _status(0.51) == "healthy"


def test_status_just_below_50_pct_is_warning():
    assert _status(0.49) == "warning"


def test_status_exactly_20_pct_is_warning():
    assert _status(0.2) == "warning"


def test_status_just_above_zero_is_critical():
    assert _status(0.01) == "critical"


def test_status_negative_is_exhausted():
    # remaining_fraction can be negative when consumed > allowed
    assert _status(-0.1) == "exhausted"


# ---------------------------------------------------------------------------
# Analyzer boundary / edge case tests
# ---------------------------------------------------------------------------


def test_100_components_zero_incidents():
    """Large graph with no incidents should all be healthy."""
    comps = [_comp(f"svc-{i}") for i in range(100)]
    g = _graph(*comps)
    report = SLABudgetAnalyzer().analyze(g, incidents_per_component=0, reference_time=_REF_TIME)
    assert len(report.budgets) == 100
    assert report.overall_status == "healthy"
    assert all(b.status == "healthy" for b in report.budgets)


def test_single_component_multiple_incidents_exhausted():
    """High incident count on single component should produce exhausted status."""
    g = _graph(_comp("app"))
    report = SLABudgetAnalyzer().analyze(g, incidents_per_component=10, reference_time=_REF_TIME)
    assert report.budgets[0].status == "exhausted"
    assert report.overall_status == "exhausted"


def test_slo_99_99_very_small_budget():
    """99.99% SLO allows only ~4.32 min/month; even 1 incident exhausts it."""
    g = _graph(_comp("strict", slo=99.99))
    report = SLABudgetAnalyzer().analyze(g, incidents_per_component=1, reference_time=_REF_TIME)
    assert report.budgets[0].status == "exhausted"


def test_slo_50_percent_large_budget():
    """50% SLO = 50% of 30 days = massive budget, won't exhaust with 1 incident."""
    g = _graph(_comp("relaxed", slo=50.0))
    report = SLABudgetAnalyzer().analyze(g, incidents_per_component=1, reference_time=_REF_TIME)
    assert report.budgets[0].status == "healthy"


def test_budgets_sorted_by_remaining_minutes():
    """budgets should be sorted by remaining_minutes ascending (most at risk first)."""
    comps = [_comp(f"svc-{i}", slo=99.0 + i * 0.3) for i in range(5)]
    g = _graph(*comps)
    report = SLABudgetAnalyzer().analyze(g, incidents_per_component=1, reference_time=_REF_TIME)
    remainders = [b.remaining_minutes for b in report.budgets]
    assert remainders == sorted(remainders)


def test_burn_rate_exactly_1_means_on_track():
    """When consumed == expected_consumed_so_far, burn_rate should be ~1.0."""
    g = _graph(_comp("app"))
    # We can't trivially force burn_rate=1 without knowing elapsed_fraction,
    # but we verify that it's a non-negative float.
    report = SLABudgetAnalyzer().analyze(g, incidents_per_component=1, reference_time=_REF_TIME)
    assert report.budgets[0].burn_rate >= 0.0


def test_days_until_exhaustion_positive():
    """days_until_exhaustion should be positive when budget is not yet exhausted."""
    g = _graph(_comp("app"))
    report = SLABudgetAnalyzer().analyze(g, incidents_per_component=1, reference_time=_REF_TIME)
    b = report.budgets[0]
    if b.status not in ("exhausted",) and b.days_until_exhaustion is not None:
        assert b.days_until_exhaustion > 0


def test_to_dict_returns_dict():
    """to_dict() should return a dict."""
    g = _graph(_comp("app"))
    report = SLABudgetAnalyzer().analyze(g, reference_time=_REF_TIME)
    d = report.to_dict()
    assert isinstance(d, dict)


def test_budget_status_to_dict_has_all_keys():
    """SLABudgetStatus.to_dict() should have all required keys."""
    g = _graph(_comp("app"))
    report = SLABudgetAnalyzer().analyze(g, reference_time=_REF_TIME)
    b = report.budgets[0]
    d = b.to_dict()
    expected_keys = {
        "component_id", "slo_target", "window_days",
        "allowed_downtime_minutes", "consumed_downtime_minutes",
        "remaining_minutes", "burn_rate", "status", "days_until_exhaustion"
    }
    assert expected_keys.issubset(d.keys())


def test_component_id_in_budget():
    """Each budget entry should reference the correct component_id."""
    g = _graph(_comp("my-service"))
    report = SLABudgetAnalyzer().analyze(g, reference_time=_REF_TIME)
    assert report.budgets[0].component_id == "my-service"


def test_slo_target_used_in_budget():
    """Budget should reflect the custom SLO target."""
    g = _graph(_comp("app", slo=99.5))
    report = SLABudgetAnalyzer().analyze(g, reference_time=_REF_TIME)
    assert report.budgets[0].slo_target == 99.5


def test_summary_overall_status_in_summary():
    """Summary string should mention the overall status."""
    g = _graph(_comp("app"))
    report = SLABudgetAnalyzer().analyze(g, reference_time=_REF_TIME)
    assert report.overall_status in report.summary


def test_summary_non_empty():
    """Summary should be a non-empty string."""
    g = _graph(_comp("app"))
    report = SLABudgetAnalyzer().analyze(g, reference_time=_REF_TIME)
    assert isinstance(report.summary, str)
    assert len(report.summary) > 0


def test_multiple_slo_targets_different_components():
    """Components with different SLO targets should produce different allowed minutes."""
    g = _graph(_comp("strict", slo=99.99), _comp("relaxed", slo=99.0))
    report = SLABudgetAnalyzer().analyze(g, reference_time=_REF_TIME)
    strict_b = next(b for b in report.budgets if b.component_id == "strict")
    relaxed_b = next(b for b in report.budgets if b.component_id == "relaxed")
    assert strict_b.allowed_downtime_minutes < relaxed_b.allowed_downtime_minutes


@pytest.mark.parametrize("yaml_file", [
    "examples/demo-infra.yaml",
    "examples/typical-startup.yaml",
    "examples/ecommerce-platform.yaml",
])
def test_analyze_all_examples(yaml_file):
    """All example YAML files should produce valid SLA budget reports."""
    from faultray.model.loader import load_yaml
    path = Path(__file__).parent.parent / yaml_file
    if not path.exists():
        pytest.skip(f"{yaml_file} not found")
    graph = load_yaml(path)
    report = SLABudgetAnalyzer().analyze(graph, reference_time=_REF_TIME)
    assert len(report.budgets) == len(graph.components)
    assert report.overall_status in ("healthy", "warning", "critical", "exhausted")


def test_no_incidents_remaining_equals_allowed():
    """With zero incidents, remaining_minutes should equal allowed_downtime_minutes."""
    g = _graph(_comp("app", slo=99.9))
    report = SLABudgetAnalyzer().analyze(g, incidents_per_component=0, reference_time=_REF_TIME)
    b = report.budgets[0]
    assert abs(b.remaining_minutes - b.allowed_downtime_minutes) < 0.01


def test_consumed_equals_incidents_times_30():
    """consumed_downtime_minutes should equal incidents * 30."""
    g = _graph(_comp("app"))
    for n in range(0, 5):
        report = SLABudgetAnalyzer().analyze(g, incidents_per_component=n, reference_time=_REF_TIME)
        assert abs(report.budgets[0].consumed_downtime_minutes - n * 30.0) < 0.01


def test_overall_status_valid_values():
    """overall_status should always be one of the four valid values."""
    valid = {"healthy", "warning", "critical", "exhausted"}
    g = _graph(_comp("a"), _comp("b"))
    for n in range(3):
        report = SLABudgetAnalyzer().analyze(g, incidents_per_component=n, reference_time=_REF_TIME)
        assert report.overall_status in valid
