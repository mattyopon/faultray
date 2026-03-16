"""Tests for SLA budget tracker."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from faultray.model.components import Component, ComponentType, Dependency, HealthStatus
from faultray.model.graph import InfraGraph
from faultray.simulator.sla_budget import (
    BudgetReport,
    BudgetSnapshot,
    BudgetStatus,
    BurnRateInfo,
    BurnRateTrend,
    Incident,
    SLABudgetTracker,
    SLATarget,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REF = datetime(2026, 3, 1, 12, 0, 0)


def _comp(
    cid: str,
    name: str,
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    health: HealthStatus = HealthStatus.HEALTHY,
) -> Component:
    c = Component(id=cid, name=name, type=ctype, replicas=replicas)
    c.health = health
    return c


def _target(
    name: str = "API SLA",
    pct: float = 99.9,
    window: int = 30,
    component_ids: list[str] | None = None,
) -> SLATarget:
    return SLATarget(
        name=name,
        target_percent=pct,
        window_days=window,
        component_ids=component_ids or [],
    )


# ---------------------------------------------------------------------------
# Tests: Enums
# ---------------------------------------------------------------------------


class TestEnums:
    def test_budget_status_values(self):
        assert BudgetStatus.HEALTHY.value == "healthy"
        assert BudgetStatus.EXCEEDED.value == "exceeded"

    def test_burn_rate_trend_values(self):
        assert BurnRateTrend.IMPROVING.value == "improving"
        assert BurnRateTrend.CRITICAL.value == "critical"


# ---------------------------------------------------------------------------
# Tests: SLA Target
# ---------------------------------------------------------------------------


class TestSLATarget:
    def test_default_window(self):
        t = SLATarget(name="Test", target_percent=99.9)
        assert t.window_days == 30

    def test_custom_window(self):
        t = SLATarget(name="Test", target_percent=99.95, window_days=7)
        assert t.window_days == 7

    def test_component_filter(self):
        t = _target(component_ids=["api", "db"])
        assert t.component_ids == ["api", "db"]


# ---------------------------------------------------------------------------
# Tests: calculate_budget
# ---------------------------------------------------------------------------


class TestCalculateBudget:
    def test_three_nines(self):
        tracker = SLABudgetTracker()
        t = _target(pct=99.9, window=30)
        budget = tracker.calculate_budget(t)
        # 30 days * 24 hours * 60 min = 43200 min
        # 0.1% of 43200 = 43.2 min
        assert abs(budget - 43.2) < 0.01

    def test_two_nines(self):
        tracker = SLABudgetTracker()
        t = _target(pct=99.0, window=30)
        budget = tracker.calculate_budget(t)
        assert abs(budget - 432.0) < 0.01

    def test_four_nines(self):
        tracker = SLABudgetTracker()
        t = _target(pct=99.99, window=30)
        budget = tracker.calculate_budget(t)
        assert abs(budget - 4.32) < 0.01

    def test_seven_day_window(self):
        tracker = SLABudgetTracker()
        t = _target(pct=99.9, window=7)
        budget = tracker.calculate_budget(t)
        # 7 * 24 * 60 = 10080, 0.1% = 10.08
        assert abs(budget - 10.08) < 0.01


# ---------------------------------------------------------------------------
# Tests: consumed_budget / remaining_budget
# ---------------------------------------------------------------------------


class TestConsumedBudget:
    def test_no_incidents(self):
        tracker = SLABudgetTracker()
        t = _target()
        assert tracker.consumed_budget(t, _REF) == 0.0

    def test_single_incident(self):
        tracker = SLABudgetTracker()
        t = _target()
        tracker.add_incident(Incident(
            component_id="api",
            start_time=_REF - timedelta(hours=5),
            duration_minutes=10.0,
        ))
        assert tracker.consumed_budget(t, _REF) == 10.0

    def test_multiple_incidents(self):
        tracker = SLABudgetTracker()
        t = _target()
        tracker.add_incident(Incident("api", _REF - timedelta(hours=5), 10.0))
        tracker.add_incident(Incident("db", _REF - timedelta(hours=3), 20.0))
        assert tracker.consumed_budget(t, _REF) == 30.0

    def test_incident_outside_window(self):
        tracker = SLABudgetTracker()
        t = _target(window=7)
        tracker.add_incident(Incident(
            "api", _REF - timedelta(days=10), 60.0,
        ))
        assert tracker.consumed_budget(t, _REF) == 0.0

    def test_incident_filtered_by_component(self):
        tracker = SLABudgetTracker()
        t = _target(component_ids=["api"])
        tracker.add_incident(Incident("api", _REF - timedelta(hours=1), 10.0))
        tracker.add_incident(Incident("db", _REF - timedelta(hours=1), 20.0))
        assert tracker.consumed_budget(t, _REF) == 10.0

    def test_remaining_budget(self):
        tracker = SLABudgetTracker()
        t = _target(pct=99.9, window=30)
        tracker.add_incident(Incident("api", _REF - timedelta(hours=1), 10.0))
        remaining = tracker.remaining_budget(t, _REF)
        assert abs(remaining - 33.2) < 0.01  # 43.2 - 10 = 33.2


# ---------------------------------------------------------------------------
# Tests: budget_status
# ---------------------------------------------------------------------------


class TestBudgetStatus:
    def test_healthy(self):
        tracker = SLABudgetTracker()
        t = _target(pct=99.9)
        # No incidents → 100% remaining → HEALTHY
        assert tracker.budget_status(t, _REF) == BudgetStatus.HEALTHY

    def test_warning(self):
        tracker = SLABudgetTracker()
        t = _target(pct=99.9, window=30)
        # Budget = 43.2 min. Consume ~60% → 40% remaining → WARNING
        tracker.add_incident(Incident("api", _REF - timedelta(hours=1), 25.92))
        assert tracker.budget_status(t, _REF) == BudgetStatus.WARNING

    def test_critical(self):
        tracker = SLABudgetTracker()
        t = _target(pct=99.9, window=30)
        # Budget = 43.2 min. Consume 85% → 15% remaining → CRITICAL
        tracker.add_incident(Incident("api", _REF - timedelta(hours=1), 36.72))
        assert tracker.budget_status(t, _REF) == BudgetStatus.CRITICAL

    def test_exhausted(self):
        tracker = SLABudgetTracker()
        t = _target(pct=99.9, window=30)
        # Budget = 43.2. Consume 97% → 3% remaining → EXHAUSTED
        tracker.add_incident(Incident("api", _REF - timedelta(hours=1), 41.9))
        assert tracker.budget_status(t, _REF) == BudgetStatus.EXHAUSTED

    def test_exceeded(self):
        tracker = SLABudgetTracker()
        t = _target(pct=99.9, window=30)
        # Budget = 43.2. Consume 50 min → negative → EXCEEDED
        tracker.add_incident(Incident("api", _REF - timedelta(hours=1), 50.0))
        assert tracker.budget_status(t, _REF) == BudgetStatus.EXCEEDED


# ---------------------------------------------------------------------------
# Tests: burn_rate
# ---------------------------------------------------------------------------


class TestBurnRate:
    def test_no_incidents_improving(self):
        tracker = SLABudgetTracker()
        t = _target()
        br = tracker.burn_rate(t, _REF, lookback_days=7)
        assert br.current_burn_rate == 0.0
        assert br.trend == BurnRateTrend.IMPROVING
        assert br.is_sustainable

    def test_sustainable_rate(self):
        tracker = SLABudgetTracker()
        t = _target(pct=99.9, window=30)
        # Budget=43.2 min over 30 days = 1.44 min/day expected
        # Consume 7 min over 7 days = 1.0 min/day → rate ≈ 0.69
        tracker.add_incident(Incident("api", _REF - timedelta(days=3), 7.0))
        br = tracker.burn_rate(t, _REF, lookback_days=7)
        assert br.is_sustainable
        assert br.trend in (BurnRateTrend.IMPROVING, BurnRateTrend.STABLE)

    def test_high_burn_rate(self):
        tracker = SLABudgetTracker()
        t = _target(pct=99.9, window=30)
        # 20 min in 7 days = 2.86 min/day vs expected 1.44 → rate ~1.98
        tracker.add_incident(Incident("api", _REF - timedelta(days=3), 20.0))
        br = tracker.burn_rate(t, _REF, lookback_days=7)
        assert not br.is_sustainable
        assert br.trend in (BurnRateTrend.DEGRADING, BurnRateTrend.CRITICAL)

    def test_critical_burn_rate(self):
        tracker = SLABudgetTracker()
        t = _target(pct=99.9, window=30)
        # 40 min in 7 days = 5.71 min/day vs 1.44 → rate ~3.97
        tracker.add_incident(Incident("api", _REF - timedelta(days=2), 40.0))
        br = tracker.burn_rate(t, _REF, lookback_days=7)
        assert br.trend == BurnRateTrend.CRITICAL

    def test_projected_exhaustion(self):
        tracker = SLABudgetTracker()
        t = _target(pct=99.9, window=30)
        # Budget=43.2, consumed 20 in last 7 days → 2.86/day
        # Remaining 23.2 → exhaustion in ~8.1 days
        tracker.add_incident(Incident("api", _REF - timedelta(days=3), 20.0))
        br = tracker.burn_rate(t, _REF, lookback_days=7)
        assert br.projected_exhaustion_days is not None
        assert br.projected_exhaustion_days > 0

    def test_no_exhaustion_when_no_consumption(self):
        tracker = SLABudgetTracker()
        t = _target()
        br = tracker.burn_rate(t, _REF)
        assert br.projected_exhaustion_days is None


# ---------------------------------------------------------------------------
# Tests: snapshot
# ---------------------------------------------------------------------------


class TestSnapshot:
    def test_snapshot_fields(self):
        tracker = SLABudgetTracker()
        t = _target()
        snap = tracker.snapshot(t, _REF)
        assert snap.total_budget_minutes > 0
        assert snap.remaining_minutes > 0
        assert snap.remaining_percent == 100.0
        assert snap.status == BudgetStatus.HEALTHY
        assert snap.incident_count == 0

    def test_snapshot_with_incidents(self):
        tracker = SLABudgetTracker()
        t = _target()
        tracker.add_incident(Incident("api", _REF - timedelta(hours=1), 10.0))
        snap = tracker.snapshot(t, _REF)
        assert snap.consumed_minutes == 10.0
        assert snap.incident_count == 1


# ---------------------------------------------------------------------------
# Tests: can_release / release_risk
# ---------------------------------------------------------------------------


class TestReleaseDecisions:
    def test_can_release_healthy(self):
        tracker = SLABudgetTracker()
        t = _target()
        assert tracker.can_release(t, _REF) is True

    def test_can_release_warning(self):
        tracker = SLABudgetTracker()
        t = _target(pct=99.9, window=30)
        tracker.add_incident(Incident("api", _REF - timedelta(hours=1), 25.0))
        assert tracker.can_release(t, _REF) is True

    def test_cannot_release_critical(self):
        tracker = SLABudgetTracker()
        t = _target(pct=99.9, window=30)
        tracker.add_incident(Incident("api", _REF - timedelta(hours=1), 37.0))
        assert tracker.can_release(t, _REF) is False

    def test_cannot_release_exceeded(self):
        tracker = SLABudgetTracker()
        t = _target(pct=99.9, window=30)
        tracker.add_incident(Incident("api", _REF - timedelta(hours=1), 50.0))
        assert tracker.can_release(t, _REF) is False

    def test_release_risk_low(self):
        tracker = SLABudgetTracker()
        t = _target()
        assert tracker.release_risk(t, _REF) == "low"

    def test_release_risk_blocked(self):
        tracker = SLABudgetTracker()
        t = _target(pct=99.9, window=30)
        tracker.add_incident(Incident("api", _REF - timedelta(hours=1), 50.0))
        assert tracker.release_risk(t, _REF) == "blocked"


# ---------------------------------------------------------------------------
# Tests: generate_report
# ---------------------------------------------------------------------------


class TestReport:
    def test_report_basic(self):
        tracker = SLABudgetTracker()
        t = _target()
        report = tracker.generate_report(t, _REF)
        assert report.sla_name == "API SLA"
        assert report.target_percent == 99.9
        assert report.can_release is True
        assert report.release_risk == "low"

    def test_report_with_incidents(self):
        tracker = SLABudgetTracker()
        t = _target(pct=99.9, window=30)
        tracker.add_incident(Incident("api", _REF - timedelta(hours=1), 50.0))
        report = tracker.generate_report(t, _REF)
        assert report.status == BudgetStatus.EXCEEDED
        assert report.can_release is False
        assert len(report.recommendations) > 0

    def test_report_recommendations_freeze(self):
        tracker = SLABudgetTracker()
        t = _target(pct=99.9, window=30)
        tracker.add_incident(Incident("api", _REF - timedelta(hours=1), 50.0))
        report = tracker.generate_report(t, _REF)
        freeze_recs = [r for r in report.recommendations if "freeze" in r.lower()]
        assert len(freeze_recs) >= 1

    def test_report_recommendations_critical_burn(self):
        tracker = SLABudgetTracker()
        t = _target(pct=99.9, window=30)
        tracker.add_incident(Incident("api", _REF - timedelta(days=2), 40.0))
        report = tracker.generate_report(t, _REF)
        burn_recs = [r for r in report.recommendations if "burn" in r.lower() or "root cause" in r.lower()]
        assert len(burn_recs) >= 1

    def test_report_many_incidents_recommendation(self):
        tracker = SLABudgetTracker()
        t = _target(pct=99.0, window=30)  # 99% = 432 min budget
        for i in range(8):
            tracker.add_incident(Incident("api", _REF - timedelta(hours=i + 1), 5.0))
        report = tracker.generate_report(t, _REF)
        sprint_recs = [r for r in report.recommendations if "incident" in r.lower()]
        assert len(sprint_recs) >= 1


# ---------------------------------------------------------------------------
# Tests: report_from_graph
# ---------------------------------------------------------------------------


class TestReportFromGraph:
    def test_healthy_graph(self):
        tracker = SLABudgetTracker()
        g = InfraGraph()
        g.add_component(_comp("api", "API"))
        g.add_component(_comp("db", "DB", ComponentType.DATABASE))
        report = tracker.report_from_graph(g, reference_time=_REF)
        assert report.status == BudgetStatus.HEALTHY

    def test_degraded_graph(self):
        tracker = SLABudgetTracker()
        g = InfraGraph()
        g.add_component(_comp("api", "API", health=HealthStatus.DEGRADED))
        report = tracker.report_from_graph(g, reference_time=_REF)
        assert report.consumed_minutes > 0

    def test_down_graph(self):
        tracker = SLABudgetTracker()
        g = InfraGraph()
        g.add_component(_comp("api", "API", health=HealthStatus.DOWN))
        report = tracker.report_from_graph(g, reference_time=_REF)
        assert report.consumed_minutes >= 60

    def test_default_target(self):
        tracker = SLABudgetTracker()
        g = InfraGraph()
        g.add_component(_comp("api", "API"))
        report = tracker.report_from_graph(g, reference_time=_REF)
        assert report.sla_name == "Default SLA"
        assert report.target_percent == 99.9

    def test_custom_target(self):
        tracker = SLABudgetTracker()
        g = InfraGraph()
        g.add_component(_comp("api", "API"))
        t = _target(name="Custom", pct=99.95)
        report = tracker.report_from_graph(g, target=t, reference_time=_REF)
        assert report.sla_name == "Custom"


# ---------------------------------------------------------------------------
# Tests: Target and Incident management
# ---------------------------------------------------------------------------


class TestManagement:
    def test_add_target(self):
        tracker = SLABudgetTracker()
        tracker.add_target(_target())
        assert len(tracker.get_targets()) == 1

    def test_add_incident(self):
        tracker = SLABudgetTracker()
        tracker.add_incident(Incident("api", _REF, 10.0))
        assert len(tracker.get_incidents()) == 1

    def test_incident_description(self):
        inc = Incident("api", _REF, 10.0, description="Network outage")
        assert inc.description == "Network outage"


# ---------------------------------------------------------------------------
# Tests: Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_100_percent_sla(self):
        tracker = SLABudgetTracker()
        t = _target(pct=100.0)
        budget = tracker.calculate_budget(t)
        assert budget == 0.0

    def test_future_incident_ignored(self):
        tracker = SLABudgetTracker()
        t = _target()
        tracker.add_incident(Incident("api", _REF + timedelta(days=1), 60.0))
        assert tracker.consumed_budget(t, _REF) == 0.0

    def test_budget_status_zero_budget(self):
        """Test line 168: budget_status returns EXHAUSTED when total budget is 0."""
        tracker = SLABudgetTracker()
        t = _target(pct=100.0, window=30)  # 100% SLA = 0 budget
        status = tracker.budget_status(t, _REF)
        assert status == BudgetStatus.EXHAUSTED

    def test_burn_rate_before_lookback(self):
        """Test line 196: incidents before lookback period are ignored."""
        tracker = SLABudgetTracker()
        t = _target(pct=99.9, window=30)
        # Incident 10 days ago, lookback is 7 days
        tracker.add_incident(Incident("api", _REF - timedelta(days=10), 20.0))
        br = tracker.burn_rate(t, _REF, lookback_days=7)
        assert br.current_burn_rate == 0.0

    def test_burn_rate_after_ref(self):
        """Test line 198: incidents after reference time are ignored."""
        tracker = SLABudgetTracker()
        t = _target(pct=99.9, window=30)
        tracker.add_incident(Incident("api", _REF + timedelta(days=1), 20.0))
        br = tracker.burn_rate(t, _REF, lookback_days=7)
        assert br.current_burn_rate == 0.0

    def test_burn_rate_component_filter(self):
        """Test line 200: component filter in burn rate calculation."""
        tracker = SLABudgetTracker()
        t = _target(pct=99.9, window=30, component_ids=["api"])
        tracker.add_incident(Incident("db", _REF - timedelta(hours=1), 20.0))
        br = tracker.burn_rate(t, _REF, lookback_days=7)
        assert br.current_burn_rate == 0.0

    def test_burn_rate_zero_expected(self):
        """Test line 210: current_rate = 0 when expected_per_day is 0."""
        tracker = SLABudgetTracker()
        t = _target(pct=100.0, window=0)  # zero budget and zero window
        br = tracker.burn_rate(t, _REF, lookback_days=7)
        assert br.current_burn_rate == 0.0

    def test_report_exhaustion_warning(self):
        """Test line 323: recommendations for exhausted budget."""
        tracker = SLABudgetTracker()
        t = _target(pct=99.9, window=30)
        # Nearly exhaust the budget
        tracker.add_incident(Incident("api", _REF - timedelta(hours=1), 42.0))
        report = tracker.generate_report(t, _REF)
        # Should have recommendation about exhaustion or critical
        assert len(report.recommendations) >= 1

    def test_report_degrading_burn_rate_recommendation(self):
        """Test line 330: recommendation when burn rate trend is DEGRADING.

        Budget = 43.2 min over 30 days = 1.44 min/day expected.
        Need rate between 1.5 and 3.0 to trigger DEGRADING trend.
        25 min in 7 days = 3.57 min/day -> rate = 3.57 / 1.44 = 2.48 -> DEGRADING.
        """
        tracker = SLABudgetTracker()
        t = _target(pct=99.9, window=30)
        tracker.add_incident(Incident("api", _REF - timedelta(days=3), 25.0))
        report = tracker.generate_report(t, _REF)
        burn_recs = [r for r in report.recommendations if "monitor" in r.lower() or "increasing" in r.lower()]
        assert len(burn_recs) >= 1

    def test_zero_window(self):
        tracker = SLABudgetTracker()
        t = _target(window=0)
        budget = tracker.calculate_budget(t)
        assert budget == 0.0
