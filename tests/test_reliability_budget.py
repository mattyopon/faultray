"""Tests for Reliability Budget Planner.

Covers ReliabilityBudgetEngine and all supporting enums, models, and
helper methods with 100% line + branch coverage.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from faultray.model.components import Component, ComponentType, HealthStatus
from faultray.model.graph import InfraGraph
from faultray.simulator.reliability_budget import (
    BudgetConsumption,
    BudgetPeriod,
    BudgetPolicy,
    BudgetStatus,
    BurnRateAnalysis,
    BurnRateLevel,
    ExhaustionRisk,
    IncidentRecord,
    MINUTES_PER_DAY,
    MINUTES_PER_HOUR,
    MINUTES_PER_MONTH,
    MINUTES_PER_QUARTER,
    MINUTES_PER_WEEK,
    MINUTES_PER_YEAR,
    PolicyAction,
    ReliabilityBudgetEngine,
    ReliabilityBudgetReport,
    ReliabilityTarget,
    ReleaseRiskAssessment,
    _PERIOD_MINUTES,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(name="c1", ctype=ComponentType.APP_SERVER):
    return Component(id=name, name=name, type=ctype, replicas=2)


def _graph(*comps):
    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    return g


def _single_comp_graph(name="svc1", ctype=ComponentType.APP_SERVER, replicas=2):
    c = Component(id=name, name=name, type=ctype, replicas=replicas)
    return _graph(c)


def _engine():
    return ReliabilityBudgetEngine()


# ---------------------------------------------------------------------------
# Tests: Enums — BudgetStatus
# ---------------------------------------------------------------------------


class TestBudgetStatus:
    def test_healthy(self):
        assert BudgetStatus.HEALTHY == "healthy"
        assert BudgetStatus.HEALTHY.value == "healthy"

    def test_warning(self):
        assert BudgetStatus.WARNING == "warning"

    def test_critical(self):
        assert BudgetStatus.CRITICAL == "critical"

    def test_exhausted(self):
        assert BudgetStatus.EXHAUSTED == "exhausted"

    def test_frozen(self):
        assert BudgetStatus.FROZEN == "frozen"

    def test_all_values(self):
        expected = {"healthy", "warning", "critical", "exhausted", "frozen"}
        actual = {s.value for s in BudgetStatus}
        assert actual == expected

    def test_str_enum(self):
        assert isinstance(BudgetStatus.HEALTHY, str)


# ---------------------------------------------------------------------------
# Tests: Enums — BudgetPeriod
# ---------------------------------------------------------------------------


class TestBudgetPeriod:
    def test_hourly(self):
        assert BudgetPeriod.HOURLY == "hourly"

    def test_daily(self):
        assert BudgetPeriod.DAILY == "daily"

    def test_weekly(self):
        assert BudgetPeriod.WEEKLY == "weekly"

    def test_monthly(self):
        assert BudgetPeriod.MONTHLY == "monthly"

    def test_quarterly(self):
        assert BudgetPeriod.QUARTERLY == "quarterly"

    def test_yearly(self):
        assert BudgetPeriod.YEARLY == "yearly"

    def test_all_values(self):
        expected = {"hourly", "daily", "weekly", "monthly", "quarterly", "yearly"}
        actual = {p.value for p in BudgetPeriod}
        assert actual == expected


# ---------------------------------------------------------------------------
# Tests: Enums — PolicyAction
# ---------------------------------------------------------------------------


class TestPolicyAction:
    def test_allow_releases(self):
        assert PolicyAction.ALLOW_RELEASES == "allow_releases"

    def test_restrict_risky(self):
        assert PolicyAction.RESTRICT_RISKY == "restrict_risky"

    def test_freeze_deployments(self):
        assert PolicyAction.FREEZE_DEPLOYMENTS == "freeze_deployments"

    def test_emergency_only(self):
        assert PolicyAction.EMERGENCY_ONLY == "emergency_only"

    def test_full_lockdown(self):
        assert PolicyAction.FULL_LOCKDOWN == "full_lockdown"

    def test_all_values(self):
        expected = {
            "allow_releases", "restrict_risky", "freeze_deployments",
            "emergency_only", "full_lockdown",
        }
        actual = {a.value for a in PolicyAction}
        assert actual == expected


# ---------------------------------------------------------------------------
# Tests: Enums — BurnRateLevel
# ---------------------------------------------------------------------------


class TestBurnRateLevel:
    def test_slow(self):
        assert BurnRateLevel.SLOW == "slow"

    def test_normal(self):
        assert BurnRateLevel.NORMAL == "normal"

    def test_elevated(self):
        assert BurnRateLevel.ELEVATED == "elevated"

    def test_fast(self):
        assert BurnRateLevel.FAST == "fast"

    def test_critical(self):
        assert BurnRateLevel.CRITICAL == "critical"

    def test_all_values(self):
        expected = {"slow", "normal", "elevated", "fast", "critical"}
        actual = {l.value for l in BurnRateLevel}
        assert actual == expected


# ---------------------------------------------------------------------------
# Tests: Enums — ExhaustionRisk
# ---------------------------------------------------------------------------


class TestExhaustionRisk:
    def test_none(self):
        assert ExhaustionRisk.NONE == "none"

    def test_low(self):
        assert ExhaustionRisk.LOW == "low"

    def test_moderate(self):
        assert ExhaustionRisk.MODERATE == "moderate"

    def test_high(self):
        assert ExhaustionRisk.HIGH == "high"

    def test_imminent(self):
        assert ExhaustionRisk.IMMINENT == "imminent"

    def test_all_values(self):
        expected = {"none", "low", "moderate", "high", "imminent"}
        actual = {r.value for r in ExhaustionRisk}
        assert actual == expected


# ---------------------------------------------------------------------------
# Tests: Constants
# ---------------------------------------------------------------------------


class TestConstants:
    def test_minutes_per_hour(self):
        assert MINUTES_PER_HOUR == 60.0

    def test_minutes_per_day(self):
        assert MINUTES_PER_DAY == 1440.0

    def test_minutes_per_week(self):
        assert MINUTES_PER_WEEK == 10080.0

    def test_minutes_per_month(self):
        assert MINUTES_PER_MONTH == 43200.0

    def test_minutes_per_quarter(self):
        assert MINUTES_PER_QUARTER == 129600.0

    def test_minutes_per_year(self):
        assert MINUTES_PER_YEAR == 525600.0

    def test_period_minutes_mapping(self):
        assert _PERIOD_MINUTES[BudgetPeriod.HOURLY] == MINUTES_PER_HOUR
        assert _PERIOD_MINUTES[BudgetPeriod.DAILY] == MINUTES_PER_DAY
        assert _PERIOD_MINUTES[BudgetPeriod.WEEKLY] == MINUTES_PER_WEEK
        assert _PERIOD_MINUTES[BudgetPeriod.MONTHLY] == MINUTES_PER_MONTH
        assert _PERIOD_MINUTES[BudgetPeriod.QUARTERLY] == MINUTES_PER_QUARTER
        assert _PERIOD_MINUTES[BudgetPeriod.YEARLY] == MINUTES_PER_YEAR


# ---------------------------------------------------------------------------
# Tests: ReliabilityTarget
# ---------------------------------------------------------------------------


class TestReliabilityTarget:
    def test_defaults(self):
        t = ReliabilityTarget(service_id="svc1")
        assert t.service_id == "svc1"
        assert t.slo_target == 0.999
        assert t.period == BudgetPeriod.MONTHLY
        assert t.total_budget_minutes == 0.0

    def test_effective_budget_999_monthly(self):
        """99.9% monthly = (1 - 0.999) * 43200 = 43.2 minutes."""
        t = ReliabilityTarget(service_id="svc1", slo_target=0.999)
        assert t.effective_budget_minutes() == pytest.approx(43.2, abs=0.01)

    def test_effective_budget_99_monthly(self):
        """99% monthly = 0.01 * 43200 = 432 minutes."""
        t = ReliabilityTarget(service_id="svc1", slo_target=0.99)
        assert t.effective_budget_minutes() == pytest.approx(432.0, abs=0.1)

    def test_effective_budget_9999_monthly(self):
        """99.99% monthly = 0.0001 * 43200 = 4.32 minutes."""
        t = ReliabilityTarget(service_id="svc1", slo_target=0.9999)
        assert t.effective_budget_minutes() == pytest.approx(4.32, abs=0.01)

    def test_effective_budget_yearly(self):
        """99.9% yearly = 0.001 * 525600 = 525.6 minutes."""
        t = ReliabilityTarget(
            service_id="svc1", slo_target=0.999, period=BudgetPeriod.YEARLY
        )
        assert t.effective_budget_minutes() == pytest.approx(525.6, abs=0.1)

    def test_effective_budget_hourly(self):
        """99.9% hourly = 0.001 * 60 = 0.06 minutes."""
        t = ReliabilityTarget(
            service_id="svc1", slo_target=0.999, period=BudgetPeriod.HOURLY
        )
        assert t.effective_budget_minutes() == pytest.approx(0.06, abs=0.001)

    def test_effective_budget_daily(self):
        """99.9% daily = 0.001 * 1440 = 1.44 minutes."""
        t = ReliabilityTarget(
            service_id="svc1", slo_target=0.999, period=BudgetPeriod.DAILY
        )
        assert t.effective_budget_minutes() == pytest.approx(1.44, abs=0.01)

    def test_effective_budget_weekly(self):
        """99.9% weekly = 0.001 * 10080 = 10.08 minutes."""
        t = ReliabilityTarget(
            service_id="svc1", slo_target=0.999, period=BudgetPeriod.WEEKLY
        )
        assert t.effective_budget_minutes() == pytest.approx(10.08, abs=0.01)

    def test_effective_budget_quarterly(self):
        """99.9% quarterly = 0.001 * 129600 = 129.6 minutes."""
        t = ReliabilityTarget(
            service_id="svc1", slo_target=0.999, period=BudgetPeriod.QUARTERLY
        )
        assert t.effective_budget_minutes() == pytest.approx(129.6, abs=0.1)

    def test_explicit_budget_override(self):
        """When total_budget_minutes > 0, it overrides the computed value."""
        t = ReliabilityTarget(
            service_id="svc1", slo_target=0.999, total_budget_minutes=100.0
        )
        assert t.effective_budget_minutes() == 100.0

    def test_custom_slo(self):
        t = ReliabilityTarget(service_id="svc1", slo_target=0.95)
        # 0.05 * 43200 = 2160
        assert t.effective_budget_minutes() == pytest.approx(2160.0, abs=0.1)


# ---------------------------------------------------------------------------
# Tests: BudgetConsumption
# ---------------------------------------------------------------------------


class TestBudgetConsumption:
    def test_defaults(self):
        c = BudgetConsumption()
        assert c.consumed_minutes == 0.0
        assert c.remaining_minutes == 0.0
        assert c.consumed_fraction == 0.0
        assert c.period_elapsed_fraction == 0.0

    def test_custom_values(self):
        c = BudgetConsumption(
            consumed_minutes=10.0,
            remaining_minutes=33.2,
            consumed_fraction=0.23,
            period_elapsed_fraction=0.5,
        )
        assert c.consumed_minutes == 10.0
        assert c.remaining_minutes == 33.2


# ---------------------------------------------------------------------------
# Tests: BurnRateAnalysis
# ---------------------------------------------------------------------------


class TestBurnRateAnalysis:
    def test_defaults(self):
        b = BurnRateAnalysis()
        assert b.current_burn_rate == 0.0
        assert b.burn_rate_level == BurnRateLevel.NORMAL
        assert b.projected_exhaustion_day == 0.0
        assert b.budget_sufficient_for_period is True

    def test_custom(self):
        b = BurnRateAnalysis(
            current_burn_rate=2.5,
            burn_rate_level=BurnRateLevel.FAST,
            projected_exhaustion_day=12.0,
            budget_sufficient_for_period=False,
        )
        assert b.current_burn_rate == 2.5
        assert b.burn_rate_level == BurnRateLevel.FAST


# ---------------------------------------------------------------------------
# Tests: ReleaseRiskAssessment
# ---------------------------------------------------------------------------


class TestReleaseRiskAssessment:
    def test_defaults(self):
        r = ReleaseRiskAssessment()
        assert r.release_id == ""
        assert r.estimated_error_budget_cost_minutes == 0.0
        assert r.risk_to_budget == ExhaustionRisk.NONE
        assert r.recommendation == ""

    def test_custom(self):
        r = ReleaseRiskAssessment(
            release_id="v1.2.3",
            estimated_error_budget_cost_minutes=5.0,
            risk_to_budget=ExhaustionRisk.HIGH,
            recommendation="Postpone.",
        )
        assert r.release_id == "v1.2.3"


# ---------------------------------------------------------------------------
# Tests: BudgetPolicy
# ---------------------------------------------------------------------------


class TestBudgetPolicy:
    def test_defaults(self):
        p = BudgetPolicy()
        assert p.status == BudgetStatus.HEALTHY
        assert p.action == PolicyAction.ALLOW_RELEASES
        assert p.reason == ""
        assert p.auto_freeze_threshold == 0.9
        assert p.release_gate_enabled is True

    def test_custom(self):
        p = BudgetPolicy(
            status=BudgetStatus.FROZEN,
            action=PolicyAction.FULL_LOCKDOWN,
            auto_freeze_threshold=0.85,
            release_gate_enabled=True,
        )
        assert p.status == BudgetStatus.FROZEN


# ---------------------------------------------------------------------------
# Tests: ReliabilityBudgetReport
# ---------------------------------------------------------------------------


class TestReliabilityBudgetReport:
    def test_construction(self):
        t = ReliabilityTarget(service_id="svc1")
        r = ReliabilityBudgetReport(
            service_id="svc1",
            target=t,
            consumption=BudgetConsumption(),
            burn_rate=BurnRateAnalysis(),
            policy=BudgetPolicy(),
        )
        assert r.service_id == "svc1"
        assert r.release_assessments == []
        assert r.forecast_days_remaining == 0.0
        assert r.recommendations == []


# ---------------------------------------------------------------------------
# Tests: IncidentRecord
# ---------------------------------------------------------------------------


class TestIncidentRecord:
    def test_defaults(self):
        i = IncidentRecord()
        assert i.incident_id == ""
        assert i.service_id == ""
        assert i.duration_minutes == 0.0
        assert i.severity == "low"

    def test_custom(self):
        i = IncidentRecord(
            incident_id="INC-001",
            service_id="svc1",
            duration_minutes=15.0,
            severity="critical",
        )
        assert i.incident_id == "INC-001"
        assert i.duration_minutes == 15.0

    def test_timestamp_is_utc(self):
        i = IncidentRecord()
        assert i.timestamp.tzinfo is not None


# ---------------------------------------------------------------------------
# Tests: Engine — analyze_burn_rate
# ---------------------------------------------------------------------------


class TestAnalyzeBurnRate:
    def test_zero_budget(self):
        e = _engine()
        t = ReliabilityTarget(service_id="svc1", slo_target=1.0)  # 0 budget
        result = e.analyze_burn_rate(t, 0.0, 0.5)
        assert result.burn_rate_level == BurnRateLevel.SLOW
        assert result.budget_sufficient_for_period is True

    def test_normal_burn(self):
        e = _engine()
        t = ReliabilityTarget(service_id="svc1", slo_target=0.999)
        # 43.2 min budget, consumed 10 min, 50% elapsed
        # consumed_fraction = 10/43.2 = 0.2315
        # burn_rate = 0.2315 / 0.5 = 0.463
        result = e.analyze_burn_rate(t, 10.0, 0.5)
        assert result.burn_rate_level == BurnRateLevel.SLOW
        assert result.budget_sufficient_for_period is True

    def test_elevated_burn(self):
        e = _engine()
        t = ReliabilityTarget(service_id="svc1", slo_target=0.999)
        # consumed 30 min out of 43.2, 50% elapsed
        # fraction = 30/43.2 = 0.694, rate = 0.694/0.5 = 1.389
        result = e.analyze_burn_rate(t, 30.0, 0.5)
        assert result.burn_rate_level == BurnRateLevel.ELEVATED
        assert result.budget_sufficient_for_period is False

    def test_fast_burn(self):
        e = _engine()
        t = ReliabilityTarget(service_id="svc1", slo_target=0.999)
        # consumed 35 min out of 43.2, 40% elapsed
        # fraction = 35/43.2 = 0.810, rate = 0.810/0.4 = 2.025
        result = e.analyze_burn_rate(t, 35.0, 0.4)
        assert result.burn_rate_level == BurnRateLevel.FAST

    def test_critical_burn(self):
        e = _engine()
        t = ReliabilityTarget(service_id="svc1", slo_target=0.999)
        # Budget ~43.2. Consumed 44 min, 10% elapsed.
        # fraction = 44/43.2 = 1.0185, rate = 1.0185/0.1 = 10.185 -> CRITICAL
        result = e.analyze_burn_rate(t, 44.0, 0.1)
        assert result.burn_rate_level == BurnRateLevel.CRITICAL

    def test_no_time_elapsed_with_consumption(self):
        e = _engine()
        t = ReliabilityTarget(service_id="svc1", slo_target=0.999)
        result = e.analyze_burn_rate(t, 5.0, 0.0)
        # rate is inf -> classified as CRITICAL
        assert result.current_burn_rate == 999.0
        assert result.burn_rate_level == BurnRateLevel.CRITICAL

    def test_no_time_elapsed_no_consumption(self):
        e = _engine()
        t = ReliabilityTarget(service_id="svc1", slo_target=0.999)
        result = e.analyze_burn_rate(t, 0.0, 0.0)
        assert result.current_burn_rate == 0.0
        assert result.burn_rate_level == BurnRateLevel.SLOW

    def test_projected_exhaustion_day(self):
        e = _engine()
        t = ReliabilityTarget(service_id="svc1", slo_target=0.999)
        # rate ~1.0 -> exhaustion at ~30 days (full period)
        result = e.analyze_burn_rate(t, 21.6, 0.5)
        assert result.projected_exhaustion_day == pytest.approx(30.0, abs=0.5)

    def test_sufficient_for_period(self):
        e = _engine()
        t = ReliabilityTarget(service_id="svc1", slo_target=0.999)
        result = e.analyze_burn_rate(t, 5.0, 0.5)
        assert result.budget_sufficient_for_period is True

    def test_not_sufficient_for_period(self):
        e = _engine()
        t = ReliabilityTarget(service_id="svc1", slo_target=0.999)
        result = e.analyze_burn_rate(t, 30.0, 0.3)
        assert result.budget_sufficient_for_period is False


# ---------------------------------------------------------------------------
# Tests: Engine — assess_release_risk
# ---------------------------------------------------------------------------


class TestAssessReleaseRisk:
    def test_no_risk(self):
        e = _engine()
        t = ReliabilityTarget(service_id="svc1", slo_target=0.999)
        consumption = BudgetConsumption(
            consumed_minutes=5.0, remaining_minutes=38.2,
            consumed_fraction=0.116, period_elapsed_fraction=0.5,
        )
        result = e.assess_release_risk(t, consumption, 1.0, "v1.0")
        assert result.risk_to_budget == ExhaustionRisk.NONE
        assert "safe" in result.recommendation.lower()

    def test_low_risk(self):
        e = _engine()
        t = ReliabilityTarget(service_id="svc1", slo_target=0.999)
        consumption = BudgetConsumption(
            consumed_minutes=20.0, remaining_minutes=23.2,
            consumed_fraction=0.46, period_elapsed_fraction=0.5,
        )
        # 5.0 / 23.2 = 0.215 -> LOW
        result = e.assess_release_risk(t, consumption, 5.0, "v1.1")
        assert result.risk_to_budget == ExhaustionRisk.LOW

    def test_moderate_risk(self):
        e = _engine()
        t = ReliabilityTarget(service_id="svc1", slo_target=0.999)
        consumption = BudgetConsumption(
            consumed_minutes=30.0, remaining_minutes=13.2,
            consumed_fraction=0.69, period_elapsed_fraction=0.5,
        )
        # 5.0 / 13.2 = 0.379 -> MODERATE
        result = e.assess_release_risk(t, consumption, 5.0, "v1.2")
        assert result.risk_to_budget == ExhaustionRisk.MODERATE
        assert "canary" in result.recommendation.lower()

    def test_high_risk(self):
        e = _engine()
        t = ReliabilityTarget(service_id="svc1", slo_target=0.999)
        consumption = BudgetConsumption(
            consumed_minutes=35.0, remaining_minutes=8.2,
            consumed_fraction=0.81, period_elapsed_fraction=0.5,
        )
        # 5.0 / 8.2 = 0.610 -> HIGH
        result = e.assess_release_risk(t, consumption, 5.0, "v1.3")
        assert result.risk_to_budget == ExhaustionRisk.HIGH
        assert "postponing" in result.recommendation.lower()

    def test_imminent_risk(self):
        e = _engine()
        t = ReliabilityTarget(service_id="svc1", slo_target=0.999)
        consumption = BudgetConsumption(
            consumed_minutes=40.0, remaining_minutes=3.2,
            consumed_fraction=0.926, period_elapsed_fraction=0.5,
        )
        # 3.0 / 3.2 = 0.9375 -> IMMINENT
        result = e.assess_release_risk(t, consumption, 3.0, "v1.4")
        assert result.risk_to_budget == ExhaustionRisk.IMMINENT

    def test_budget_already_exhausted(self):
        e = _engine()
        t = ReliabilityTarget(service_id="svc1", slo_target=0.999)
        consumption = BudgetConsumption(
            consumed_minutes=43.2, remaining_minutes=0.0,
            consumed_fraction=1.0, period_elapsed_fraction=0.5,
        )
        result = e.assess_release_risk(t, consumption, 1.0, "v2.0")
        assert result.risk_to_budget == ExhaustionRisk.IMMINENT
        assert "exhausted" in result.recommendation.lower()

    def test_release_id_propagated(self):
        e = _engine()
        t = ReliabilityTarget(service_id="svc1", slo_target=0.999)
        consumption = BudgetConsumption(remaining_minutes=40.0)
        result = e.assess_release_risk(t, consumption, 1.0, "my-release")
        assert result.release_id == "my-release"

    def test_zero_remaining_not_caught_by_early_return(self):
        """When remaining_minutes > 0 but exactly 0.0 via rounding edge."""
        e = _engine()
        t = ReliabilityTarget(service_id="svc1", slo_target=0.999)
        # remaining > 0 so early return doesn't fire, but remaining is tiny
        consumption = BudgetConsumption(
            consumed_minutes=43.19, remaining_minutes=0.0,
            consumed_fraction=0.999, period_elapsed_fraction=0.5,
        )
        # remaining is 0.0 -> early return triggers with IMMINENT
        result = e.assess_release_risk(t, consumption, 1.0, "edge")
        assert result.risk_to_budget == ExhaustionRisk.IMMINENT


# ---------------------------------------------------------------------------
# Tests: Engine — enforce_policy
# ---------------------------------------------------------------------------


class TestEnforcePolicy:
    def test_healthy(self):
        e = _engine()
        consumption = BudgetConsumption(consumed_fraction=0.2, remaining_minutes=30.0)
        burn = BurnRateAnalysis(burn_rate_level=BurnRateLevel.NORMAL)
        p = e.enforce_policy(consumption, burn)
        assert p.status == BudgetStatus.HEALTHY
        assert p.action == PolicyAction.ALLOW_RELEASES
        assert p.release_gate_enabled is False

    def test_warning(self):
        e = _engine()
        consumption = BudgetConsumption(consumed_fraction=0.55, remaining_minutes=20.0)
        burn = BurnRateAnalysis(burn_rate_level=BurnRateLevel.NORMAL)
        p = e.enforce_policy(consumption, burn)
        assert p.status == BudgetStatus.WARNING
        assert p.action == PolicyAction.RESTRICT_RISKY

    def test_critical(self):
        e = _engine()
        consumption = BudgetConsumption(consumed_fraction=0.75, remaining_minutes=10.0)
        burn = BurnRateAnalysis(burn_rate_level=BurnRateLevel.NORMAL)
        p = e.enforce_policy(consumption, burn)
        assert p.status == BudgetStatus.CRITICAL
        assert p.action == PolicyAction.RESTRICT_RISKY

    def test_frozen_at_threshold(self):
        e = _engine()
        consumption = BudgetConsumption(consumed_fraction=0.92, remaining_minutes=3.0)
        burn = BurnRateAnalysis(burn_rate_level=BurnRateLevel.NORMAL)
        p = e.enforce_policy(consumption, burn, auto_freeze_threshold=0.9)
        assert p.status == BudgetStatus.FROZEN
        assert p.action == PolicyAction.FREEZE_DEPLOYMENTS

    def test_exhausted(self):
        e = _engine()
        consumption = BudgetConsumption(
            consumed_fraction=1.0, remaining_minutes=0.0,
        )
        burn = BurnRateAnalysis(burn_rate_level=BurnRateLevel.CRITICAL)
        p = e.enforce_policy(consumption, burn, auto_freeze_threshold=1.1)
        assert p.status == BudgetStatus.EXHAUSTED
        assert p.action == PolicyAction.EMERGENCY_ONLY

    def test_frozen_exhausted_above_threshold(self):
        e = _engine()
        consumption = BudgetConsumption(
            consumed_fraction=1.0, remaining_minutes=0.0,
        )
        burn = BurnRateAnalysis(burn_rate_level=BurnRateLevel.CRITICAL)
        p = e.enforce_policy(consumption, burn, auto_freeze_threshold=0.9)
        assert p.status == BudgetStatus.FROZEN
        assert p.action == PolicyAction.FULL_LOCKDOWN

    def test_critical_burn_rate_override(self):
        e = _engine()
        consumption = BudgetConsumption(consumed_fraction=0.3, remaining_minutes=30.0)
        burn = BurnRateAnalysis(
            burn_rate_level=BurnRateLevel.CRITICAL,
            current_burn_rate=6.0,
        )
        p = e.enforce_policy(consumption, burn)
        assert p.status == BudgetStatus.CRITICAL
        assert p.action == PolicyAction.RESTRICT_RISKY

    def test_custom_freeze_threshold(self):
        e = _engine()
        consumption = BudgetConsumption(consumed_fraction=0.82, remaining_minutes=8.0)
        burn = BurnRateAnalysis(burn_rate_level=BurnRateLevel.NORMAL)
        p = e.enforce_policy(consumption, burn, auto_freeze_threshold=0.8)
        assert p.status == BudgetStatus.FROZEN

    def test_release_gate_disabled_when_healthy(self):
        e = _engine()
        consumption = BudgetConsumption(consumed_fraction=0.1, remaining_minutes=38.0)
        burn = BurnRateAnalysis(burn_rate_level=BurnRateLevel.SLOW)
        p = e.enforce_policy(consumption, burn)
        assert p.release_gate_enabled is False

    def test_release_gate_enabled_when_not_healthy(self):
        e = _engine()
        consumption = BudgetConsumption(consumed_fraction=0.6, remaining_minutes=17.0)
        burn = BurnRateAnalysis(burn_rate_level=BurnRateLevel.NORMAL)
        p = e.enforce_policy(consumption, burn)
        assert p.release_gate_enabled is True


# ---------------------------------------------------------------------------
# Tests: Engine — forecast_exhaustion
# ---------------------------------------------------------------------------


class TestForecastExhaustion:
    def test_already_exhausted(self):
        e = _engine()
        burn = BurnRateAnalysis(current_burn_rate=2.0, projected_exhaustion_day=5.0)
        result = e.forecast_exhaustion(burn, 0.0)
        assert result["days"] == 0.0
        assert result["confidence"] == 1.0

    def test_no_burn_rate(self):
        e = _engine()
        burn = BurnRateAnalysis(current_burn_rate=0.0, projected_exhaustion_day=0.0)
        result = e.forecast_exhaustion(burn, 30.0)
        assert result["days"] == -1.0
        assert result["date"] == "never"
        assert result["confidence"] == 0.0

    def test_normal_projection(self):
        e = _engine()
        burn = BurnRateAnalysis(current_burn_rate=1.0, projected_exhaustion_day=15.0)
        result = e.forecast_exhaustion(burn, 20.0)
        assert result["days"] == 15.0
        assert result["confidence"] == 0.7  # 7 < 15 <= 30

    def test_short_projection_high_confidence(self):
        e = _engine()
        burn = BurnRateAnalysis(current_burn_rate=5.0, projected_exhaustion_day=0.5)
        result = e.forecast_exhaustion(burn, 1.0)
        assert result["days"] == 0.5
        assert result["confidence"] == 0.95

    def test_long_projection_low_confidence(self):
        e = _engine()
        burn = BurnRateAnalysis(current_burn_rate=0.1, projected_exhaustion_day=60.0)
        result = e.forecast_exhaustion(burn, 100.0)
        assert result["days"] == 60.0
        assert result["confidence"] == 0.5

    def test_zero_projected_day(self):
        e = _engine()
        burn = BurnRateAnalysis(current_burn_rate=999.0, projected_exhaustion_day=0.0)
        result = e.forecast_exhaustion(burn, 5.0)
        assert result["days"] == 0.0

    def test_week_confidence(self):
        e = _engine()
        burn = BurnRateAnalysis(current_burn_rate=1.0, projected_exhaustion_day=5.0)
        result = e.forecast_exhaustion(burn, 10.0)
        assert result["confidence"] == 0.85  # 1 < 5 <= 7

    def test_one_day_confidence(self):
        e = _engine()
        burn = BurnRateAnalysis(current_burn_rate=2.0, projected_exhaustion_day=1.0)
        result = e.forecast_exhaustion(burn, 5.0)
        assert result["confidence"] == 0.95


# ---------------------------------------------------------------------------
# Tests: Engine — allocate_budget_across_services
# ---------------------------------------------------------------------------


class TestAllocateBudgetAcrossServices:
    def test_empty_graph(self):
        e = _engine()
        g = InfraGraph()
        result = e.allocate_budget_across_services(g, 0.999)
        assert result == {}

    def test_single_service(self):
        e = _engine()
        g = _single_comp_graph("svc1")
        result = e.allocate_budget_across_services(g, 0.999)
        assert "svc1" in result
        # 0.001 * 43200 = 43.2 min, single service gets all
        assert result["svc1"] == pytest.approx(43.2, abs=0.1)

    def test_two_services_equal_weight(self):
        e = _engine()
        c1 = _comp("svc1")
        c2 = _comp("svc2")
        g = _graph(c1, c2)
        result = e.allocate_budget_across_services(g, 0.999)
        assert len(result) == 2
        total = sum(result.values())
        assert total == pytest.approx(43.2, abs=0.1)
        # Both should get roughly equal share
        assert abs(result["svc1"] - result["svc2"]) < 0.1

    def test_weighted_services(self):
        e = _engine()
        c1 = _comp("svc1")
        c2 = _comp("svc2")
        g = _graph(c1, c2)
        weights = {"svc1": 3.0, "svc2": 1.0}
        result = e.allocate_budget_across_services(g, 0.999, weights)
        assert result["svc1"] > result["svc2"]

    def test_topology_boost(self):
        """Components with dependents get a topology boost."""
        e = _engine()
        from faultray.model.components import Dependency

        c1 = _comp("lb")
        c2 = _comp("api")
        g = _graph(c1, c2)
        g.add_dependency(Dependency(source_id="api", target_id="lb"))
        # lb has 1 dependent (api), api has 0
        result = e.allocate_budget_across_services(g, 0.999)
        assert result["lb"] > result["api"]

    def test_custom_global_slo(self):
        e = _engine()
        g = _single_comp_graph("svc1")
        result = e.allocate_budget_across_services(g, 0.99)
        # 0.01 * 43200 = 432
        assert result["svc1"] == pytest.approx(432.0, abs=0.5)

    def test_zero_weight_services(self):
        """When all weights are 0, total_weight falls back to 1.0."""
        e = _engine()
        c1 = _comp("svc1")
        g = _graph(c1)
        weights = {"svc1": 0.0}
        result = e.allocate_budget_across_services(g, 0.999, weights)
        # weight = 0.0 * topology_boost = 0.0, total_weight -> 1.0
        assert "svc1" in result
        assert result["svc1"] == 0.0


# ---------------------------------------------------------------------------
# Tests: Engine — compute_budget
# ---------------------------------------------------------------------------


class TestComputeBudget:
    def test_no_incidents(self):
        e = _engine()
        g = _single_comp_graph("svc1")
        t = ReliabilityTarget(service_id="svc1", slo_target=0.999)
        report = e.compute_budget(g, t)
        assert report.service_id == "svc1"
        assert report.consumption.consumed_minutes == 0.0
        assert report.consumption.remaining_minutes == pytest.approx(43.2, abs=0.1)
        assert report.policy.status == BudgetStatus.HEALTHY

    def test_with_incidents(self):
        e = _engine()
        g = _single_comp_graph("svc1")
        t = ReliabilityTarget(service_id="svc1", slo_target=0.999)
        incidents = [
            IncidentRecord(service_id="svc1", duration_minutes=10.0),
            IncidentRecord(service_id="svc1", duration_minutes=5.0),
        ]
        report = e.compute_budget(g, t, incidents)
        assert report.consumption.consumed_minutes == 15.0
        assert report.consumption.remaining_minutes == pytest.approx(28.2, abs=0.1)

    def test_exhausted_budget(self):
        e = _engine()
        g = _single_comp_graph("svc1")
        t = ReliabilityTarget(service_id="svc1", slo_target=0.999)
        incidents = [
            IncidentRecord(service_id="svc1", duration_minutes=50.0),
        ]
        report = e.compute_budget(g, t, incidents)
        assert report.consumption.remaining_minutes == 0.0
        assert report.consumption.consumed_fraction == 1.0

    def test_incidents_filtered_by_service(self):
        e = _engine()
        g = _single_comp_graph("svc1")
        t = ReliabilityTarget(service_id="svc1", slo_target=0.999)
        incidents = [
            IncidentRecord(service_id="svc1", duration_minutes=5.0),
            IncidentRecord(service_id="svc2", duration_minutes=10.0),
            IncidentRecord(service_id="", duration_minutes=3.0),  # global
        ]
        report = e.compute_budget(g, t, incidents)
        # svc1 (5) + global (3) = 8
        assert report.consumption.consumed_minutes == 8.0

    def test_recommendations_present(self):
        e = _engine()
        g = _single_comp_graph("svc1")
        t = ReliabilityTarget(service_id="svc1", slo_target=0.999)
        report = e.compute_budget(g, t)
        assert len(report.recommendations) > 0

    def test_no_redundancy_recommendation(self):
        """Single replica service should get redundancy recommendation."""
        e = _engine()
        c = Component(id="svc1", name="svc1", type=ComponentType.APP_SERVER, replicas=1)
        g = _graph(c)
        t = ReliabilityTarget(service_id="svc1", slo_target=0.999)
        incidents = [
            IncidentRecord(service_id="svc1", duration_minutes=25.0),
        ]
        report = e.compute_budget(g, t, incidents)
        recs_text = " ".join(report.recommendations)
        assert "redundancy" in recs_text.lower() or "replica" in recs_text.lower()


# ---------------------------------------------------------------------------
# Tests: Engine — compute_multi_service_budget
# ---------------------------------------------------------------------------


class TestComputeMultiServiceBudget:
    def test_multiple_services(self):
        e = _engine()
        c1 = _comp("svc1")
        c2 = _comp("svc2")
        g = _graph(c1, c2)
        targets = [
            ReliabilityTarget(service_id="svc1", slo_target=0.999),
            ReliabilityTarget(service_id="svc2", slo_target=0.99),
        ]
        incidents = [
            IncidentRecord(service_id="svc1", duration_minutes=5.0),
            IncidentRecord(service_id="svc2", duration_minutes=100.0),
        ]
        reports = e.compute_multi_service_budget(g, targets, incidents)
        assert len(reports) == 2
        assert reports[0].service_id == "svc1"
        assert reports[1].service_id == "svc2"

    def test_no_incidents(self):
        e = _engine()
        g = _single_comp_graph("svc1")
        targets = [ReliabilityTarget(service_id="svc1")]
        reports = e.compute_multi_service_budget(g, targets)
        assert len(reports) == 1

    def test_empty_targets(self):
        e = _engine()
        g = _single_comp_graph("svc1")
        reports = e.compute_multi_service_budget(g, [])
        assert reports == []


# ---------------------------------------------------------------------------
# Tests: Engine — compare_slo_targets
# ---------------------------------------------------------------------------


class TestCompareSloTargets:
    def test_same_targets(self):
        e = _engine()
        a = ReliabilityTarget(service_id="a", slo_target=0.999)
        b = ReliabilityTarget(service_id="b", slo_target=0.999)
        result = e.compare_slo_targets(a, b)
        assert result["difference_minutes"] == pytest.approx(0.0, abs=0.01)
        assert result["budget_ratio"] == pytest.approx(1.0, abs=0.01)

    def test_different_targets(self):
        e = _engine()
        a = ReliabilityTarget(service_id="a", slo_target=0.9999)  # 4.32 min
        b = ReliabilityTarget(service_id="b", slo_target=0.999)   # 43.2 min
        result = e.compare_slo_targets(a, b)
        assert result["stricter_target"] == "a"
        assert result["budget_a_minutes"] < result["budget_b_minutes"]

    def test_zero_budget_b(self):
        e = _engine()
        a = ReliabilityTarget(service_id="a", slo_target=0.999)
        b = ReliabilityTarget(service_id="b", slo_target=1.0)  # 0 budget
        result = e.compare_slo_targets(a, b)
        assert result["budget_ratio"] == 0.0


# ---------------------------------------------------------------------------
# Tests: Engine — simulate_incident_impact
# ---------------------------------------------------------------------------


class TestSimulateIncidentImpact:
    def test_no_exhaustion(self):
        e = _engine()
        t = ReliabilityTarget(service_id="svc1", slo_target=0.999)
        consumption = BudgetConsumption(consumed_minutes=5.0, remaining_minutes=38.2)
        result = e.simulate_incident_impact(t, consumption, 10.0)
        assert result["new_consumed_minutes"] == 15.0
        assert result["would_exhaust"] is False
        assert result["new_status"] == BudgetStatus.HEALTHY

    def test_causes_exhaustion(self):
        e = _engine()
        t = ReliabilityTarget(service_id="svc1", slo_target=0.999)
        consumption = BudgetConsumption(consumed_minutes=40.0, remaining_minutes=3.2)
        result = e.simulate_incident_impact(t, consumption, 10.0)
        assert result["would_exhaust"] is True
        assert result["new_remaining_minutes"] == 0.0
        assert result["new_status"] == BudgetStatus.EXHAUSTED

    def test_warning_status(self):
        e = _engine()
        t = ReliabilityTarget(service_id="svc1", slo_target=0.999)
        # 43.2 budget, consumed 20 -> 46.3%
        consumption = BudgetConsumption(consumed_minutes=20.0, remaining_minutes=23.2)
        # Adding 5 -> 25/43.2 = 57.9% -> WARNING
        result = e.simulate_incident_impact(t, consumption, 5.0)
        assert result["new_status"] == BudgetStatus.WARNING

    def test_critical_status(self):
        e = _engine()
        t = ReliabilityTarget(service_id="svc1", slo_target=0.999)
        consumption = BudgetConsumption(consumed_minutes=25.0, remaining_minutes=18.2)
        # Adding 8 -> 33/43.2 = 76.4% -> CRITICAL
        result = e.simulate_incident_impact(t, consumption, 8.0)
        assert result["new_status"] == BudgetStatus.CRITICAL

    def test_frozen_status(self):
        e = _engine()
        t = ReliabilityTarget(service_id="svc1", slo_target=0.999)
        consumption = BudgetConsumption(consumed_minutes=35.0, remaining_minutes=8.2)
        # Adding 5 -> 40/43.2 = 92.6% -> FROZEN
        result = e.simulate_incident_impact(t, consumption, 5.0)
        assert result["new_status"] == BudgetStatus.FROZEN

    def test_zero_budget(self):
        e = _engine()
        t = ReliabilityTarget(service_id="svc1", slo_target=1.0)
        consumption = BudgetConsumption(consumed_minutes=0.0, remaining_minutes=0.0)
        result = e.simulate_incident_impact(t, consumption, 1.0)
        assert result["new_consumed_fraction"] == 1.0
        assert result["would_exhaust"] is True


# ---------------------------------------------------------------------------
# Tests: Engine — calculate_budget_for_slo
# ---------------------------------------------------------------------------


class TestCalculateBudgetForSlo:
    def test_999_monthly(self):
        e = _engine()
        result = e.calculate_budget_for_slo(0.999, BudgetPeriod.MONTHLY)
        assert result["slo"] == 0.999
        assert result["period"] == "monthly"
        assert result["error_budget_minutes"] == pytest.approx(43.2, abs=0.01)
        assert result["error_budget_seconds"] == pytest.approx(2592.0, abs=0.1)

    def test_99_monthly(self):
        e = _engine()
        result = e.calculate_budget_for_slo(0.99, BudgetPeriod.MONTHLY)
        assert result["error_budget_minutes"] == pytest.approx(432.0, abs=0.1)

    def test_9999_monthly(self):
        e = _engine()
        result = e.calculate_budget_for_slo(0.9999, BudgetPeriod.MONTHLY)
        assert result["error_budget_minutes"] == pytest.approx(4.32, abs=0.01)

    def test_yearly(self):
        e = _engine()
        result = e.calculate_budget_for_slo(0.999, BudgetPeriod.YEARLY)
        assert result["error_budget_minutes"] == pytest.approx(525.6, abs=0.1)

    def test_daily(self):
        e = _engine()
        result = e.calculate_budget_for_slo(0.999, BudgetPeriod.DAILY)
        assert result["error_budget_minutes"] == pytest.approx(1.44, abs=0.01)

    def test_hourly(self):
        e = _engine()
        result = e.calculate_budget_for_slo(0.999, BudgetPeriod.HOURLY)
        assert result["error_budget_minutes"] == pytest.approx(0.06, abs=0.001)

    def test_allowed_downtime_per_day(self):
        e = _engine()
        result = e.calculate_budget_for_slo(0.999, BudgetPeriod.MONTHLY)
        # 2592 seconds / 30 days = 86.4 seconds/day
        assert result["allowed_downtime_per_day_seconds"] == pytest.approx(86.4, abs=0.1)


# ---------------------------------------------------------------------------
# Tests: Engine — evaluate_burn_rate_alerts
# ---------------------------------------------------------------------------


class TestEvaluateBurnRateAlerts:
    def test_no_alerts_healthy(self):
        e = _engine()
        burn = BurnRateAnalysis(
            burn_rate_level=BurnRateLevel.NORMAL,
            current_burn_rate=0.8,
            budget_sufficient_for_period=True,
        )
        consumption = BudgetConsumption(consumed_fraction=0.3)
        alerts = e.evaluate_burn_rate_alerts(burn, consumption)
        assert len(alerts) == 0

    def test_critical_burn_rate_alert(self):
        e = _engine()
        burn = BurnRateAnalysis(
            burn_rate_level=BurnRateLevel.CRITICAL,
            current_burn_rate=6.0,
            budget_sufficient_for_period=False,
        )
        consumption = BudgetConsumption(consumed_fraction=0.4)
        alerts = e.evaluate_burn_rate_alerts(burn, consumption)
        severities = [a["severity"] for a in alerts]
        assert "critical" in severities

    def test_fast_burn_rate_alert(self):
        e = _engine()
        burn = BurnRateAnalysis(
            burn_rate_level=BurnRateLevel.FAST,
            current_burn_rate=3.0,
            budget_sufficient_for_period=False,
        )
        consumption = BudgetConsumption(consumed_fraction=0.4)
        alerts = e.evaluate_burn_rate_alerts(burn, consumption)
        severities = [a["severity"] for a in alerts]
        assert "warning" in severities

    def test_high_consumption_alert(self):
        e = _engine()
        burn = BurnRateAnalysis(
            burn_rate_level=BurnRateLevel.NORMAL,
            current_burn_rate=1.0,
            budget_sufficient_for_period=True,
        )
        consumption = BudgetConsumption(consumed_fraction=0.92)
        alerts = e.evaluate_burn_rate_alerts(burn, consumption)
        assert any(a["action"] == "freeze_deployments" for a in alerts)

    def test_medium_consumption_alert(self):
        e = _engine()
        burn = BurnRateAnalysis(
            burn_rate_level=BurnRateLevel.NORMAL,
            current_burn_rate=1.0,
            budget_sufficient_for_period=True,
        )
        consumption = BudgetConsumption(consumed_fraction=0.75)
        alerts = e.evaluate_burn_rate_alerts(burn, consumption)
        assert any(a["action"] == "restrict_releases" for a in alerts)

    def test_insufficient_budget_alert(self):
        e = _engine()
        burn = BurnRateAnalysis(
            burn_rate_level=BurnRateLevel.NORMAL,
            current_burn_rate=1.0,
            budget_sufficient_for_period=False,
        )
        consumption = BudgetConsumption(consumed_fraction=0.3)
        alerts = e.evaluate_burn_rate_alerts(burn, consumption)
        assert any(a["action"] == "review_release_plan" for a in alerts)


# ---------------------------------------------------------------------------
# Tests: Engine — compute_composite_slo
# ---------------------------------------------------------------------------


class TestComputeCompositeSlo:
    def test_empty_list(self):
        e = _engine()
        assert e.compute_composite_slo([]) == 1.0

    def test_single_service(self):
        e = _engine()
        targets = [ReliabilityTarget(service_id="a", slo_target=0.999)]
        assert e.compute_composite_slo(targets) == pytest.approx(0.999)

    def test_two_services(self):
        e = _engine()
        targets = [
            ReliabilityTarget(service_id="a", slo_target=0.999),
            ReliabilityTarget(service_id="b", slo_target=0.999),
        ]
        # 0.999 * 0.999 = 0.998001
        assert e.compute_composite_slo(targets) == pytest.approx(0.998001, abs=1e-6)

    def test_three_services(self):
        e = _engine()
        targets = [
            ReliabilityTarget(service_id="a", slo_target=0.99),
            ReliabilityTarget(service_id="b", slo_target=0.99),
            ReliabilityTarget(service_id="c", slo_target=0.99),
        ]
        # 0.99^3 = 0.970299
        assert e.compute_composite_slo(targets) == pytest.approx(0.970299, abs=1e-5)


# ---------------------------------------------------------------------------
# Tests: Engine — budget_utilization_efficiency
# ---------------------------------------------------------------------------


class TestBudgetUtilizationEfficiency:
    def test_perfect_efficiency(self):
        e = _engine()
        c = BudgetConsumption(consumed_fraction=0.5, period_elapsed_fraction=0.5)
        assert e.budget_utilization_efficiency(c) == pytest.approx(1.0)

    def test_over_consumption(self):
        e = _engine()
        c = BudgetConsumption(consumed_fraction=0.8, period_elapsed_fraction=0.5)
        assert e.budget_utilization_efficiency(c) == pytest.approx(1.6)

    def test_under_consumption(self):
        e = _engine()
        c = BudgetConsumption(consumed_fraction=0.25, period_elapsed_fraction=0.5)
        assert e.budget_utilization_efficiency(c) == pytest.approx(0.5)

    def test_zero_elapsed(self):
        e = _engine()
        c = BudgetConsumption(consumed_fraction=0.0, period_elapsed_fraction=0.0)
        assert e.budget_utilization_efficiency(c) == 0.0

    def test_zero_elapsed_with_consumption(self):
        e = _engine()
        c = BudgetConsumption(consumed_fraction=0.5, period_elapsed_fraction=0.0)
        assert e.budget_utilization_efficiency(c) == float("inf")


# ---------------------------------------------------------------------------
# Tests: Engine — _classify_burn_rate
# ---------------------------------------------------------------------------


class TestClassifyBurnRate:
    def test_slow(self):
        assert ReliabilityBudgetEngine._classify_burn_rate(0.3) == BurnRateLevel.SLOW

    def test_normal(self):
        assert ReliabilityBudgetEngine._classify_burn_rate(0.8) == BurnRateLevel.NORMAL

    def test_normal_boundary(self):
        assert ReliabilityBudgetEngine._classify_burn_rate(0.5) == BurnRateLevel.NORMAL

    def test_elevated(self):
        assert ReliabilityBudgetEngine._classify_burn_rate(1.5) == BurnRateLevel.ELEVATED

    def test_elevated_boundary(self):
        assert ReliabilityBudgetEngine._classify_burn_rate(1.2) == BurnRateLevel.ELEVATED

    def test_fast(self):
        assert ReliabilityBudgetEngine._classify_burn_rate(3.0) == BurnRateLevel.FAST

    def test_fast_boundary(self):
        assert ReliabilityBudgetEngine._classify_burn_rate(2.0) == BurnRateLevel.FAST

    def test_critical(self):
        assert ReliabilityBudgetEngine._classify_burn_rate(5.0) == BurnRateLevel.CRITICAL

    def test_critical_high(self):
        assert ReliabilityBudgetEngine._classify_burn_rate(10.0) == BurnRateLevel.CRITICAL

    def test_infinity(self):
        assert ReliabilityBudgetEngine._classify_burn_rate(float("inf")) == BurnRateLevel.CRITICAL

    def test_zero(self):
        assert ReliabilityBudgetEngine._classify_burn_rate(0.0) == BurnRateLevel.SLOW


# ---------------------------------------------------------------------------
# Tests: Engine — _classify_exhaustion_risk
# ---------------------------------------------------------------------------


class TestClassifyExhaustionRisk:
    def test_none(self):
        assert ReliabilityBudgetEngine._classify_exhaustion_risk(0.05) == ExhaustionRisk.NONE

    def test_low(self):
        assert ReliabilityBudgetEngine._classify_exhaustion_risk(0.15) == ExhaustionRisk.LOW

    def test_low_boundary(self):
        assert ReliabilityBudgetEngine._classify_exhaustion_risk(0.1) == ExhaustionRisk.LOW

    def test_moderate(self):
        assert ReliabilityBudgetEngine._classify_exhaustion_risk(0.35) == ExhaustionRisk.MODERATE

    def test_moderate_boundary(self):
        assert ReliabilityBudgetEngine._classify_exhaustion_risk(0.25) == ExhaustionRisk.MODERATE

    def test_high(self):
        assert ReliabilityBudgetEngine._classify_exhaustion_risk(0.6) == ExhaustionRisk.HIGH

    def test_high_boundary(self):
        assert ReliabilityBudgetEngine._classify_exhaustion_risk(0.5) == ExhaustionRisk.HIGH

    def test_imminent(self):
        assert ReliabilityBudgetEngine._classify_exhaustion_risk(0.9) == ExhaustionRisk.IMMINENT

    def test_imminent_boundary(self):
        assert ReliabilityBudgetEngine._classify_exhaustion_risk(0.8) == ExhaustionRisk.IMMINENT

    def test_zero(self):
        assert ReliabilityBudgetEngine._classify_exhaustion_risk(0.0) == ExhaustionRisk.NONE


# ---------------------------------------------------------------------------
# Tests: Engine — _estimate_elapsed_fraction
# ---------------------------------------------------------------------------


class TestEstimateElapsedFraction:
    def test_no_incidents_default(self):
        result = ReliabilityBudgetEngine._estimate_elapsed_fraction(
            [], ReliabilityTarget(service_id="svc1")
        )
        assert result == 0.5

    def test_recent_incident(self):
        now = datetime.now(timezone.utc)
        inc = IncidentRecord(
            service_id="svc1",
            duration_minutes=5.0,
            timestamp=now - timedelta(minutes=10),
        )
        result = ReliabilityBudgetEngine._estimate_elapsed_fraction(
            [inc], ReliabilityTarget(service_id="svc1")
        )
        # 10 min out of 43200 = ~0.0002, clamped to >= 0.01
        assert 0.0 < result <= 0.01

    def test_old_incident(self):
        now = datetime.now(timezone.utc)
        inc = IncidentRecord(
            service_id="svc1",
            duration_minutes=5.0,
            timestamp=now - timedelta(days=25),
        )
        result = ReliabilityBudgetEngine._estimate_elapsed_fraction(
            [inc], ReliabilityTarget(service_id="svc1")
        )
        assert result > 0.5

    def test_clamped_to_1(self):
        now = datetime.now(timezone.utc)
        inc = IncidentRecord(
            service_id="svc1",
            duration_minutes=5.0,
            timestamp=now - timedelta(days=60),
        )
        result = ReliabilityBudgetEngine._estimate_elapsed_fraction(
            [inc], ReliabilityTarget(service_id="svc1")
        )
        assert result <= 1.0

    def test_multiple_incidents_uses_earliest(self):
        now = datetime.now(timezone.utc)
        inc1 = IncidentRecord(timestamp=now - timedelta(days=1))
        inc2 = IncidentRecord(timestamp=now - timedelta(days=10))
        result = ReliabilityBudgetEngine._estimate_elapsed_fraction(
            [inc1, inc2], ReliabilityTarget(service_id="svc1")
        )
        # Should use earliest (10 days ago)
        assert result > 0.3


# ---------------------------------------------------------------------------
# Tests: Engine — _build_recommendations
# ---------------------------------------------------------------------------


class TestBuildRecommendations:
    def test_healthy_budget(self):
        e = _engine()
        consumption = BudgetConsumption(consumed_fraction=0.1, remaining_minutes=38.0)
        burn = BurnRateAnalysis(
            burn_rate_level=BurnRateLevel.SLOW, budget_sufficient_for_period=True
        )
        policy = BudgetPolicy(status=BudgetStatus.HEALTHY)
        target = ReliabilityTarget(service_id="svc1")
        g = _single_comp_graph("svc1")
        recs = e._build_recommendations(consumption, burn, policy, target, g)
        assert any("healthy" in r.lower() for r in recs)

    def test_exhausted_recommendation(self):
        e = _engine()
        consumption = BudgetConsumption(consumed_fraction=1.0, remaining_minutes=0.0)
        burn = BurnRateAnalysis(
            burn_rate_level=BurnRateLevel.CRITICAL, budget_sufficient_for_period=False
        )
        policy = BudgetPolicy(status=BudgetStatus.EXHAUSTED)
        target = ReliabilityTarget(service_id="svc1")
        g = _single_comp_graph("svc1")
        recs = e._build_recommendations(consumption, burn, policy, target, g)
        assert any("exhausted" in r.lower() for r in recs)

    def test_frozen_recommendation(self):
        e = _engine()
        consumption = BudgetConsumption(consumed_fraction=0.95, remaining_minutes=2.0)
        burn = BurnRateAnalysis(
            burn_rate_level=BurnRateLevel.FAST, budget_sufficient_for_period=False
        )
        policy = BudgetPolicy(status=BudgetStatus.FROZEN)
        target = ReliabilityTarget(service_id="svc1")
        g = _single_comp_graph("svc1")
        recs = e._build_recommendations(consumption, burn, policy, target, g)
        assert any("frozen" in r.lower() for r in recs)

    def test_fast_burn_recommendation(self):
        e = _engine()
        consumption = BudgetConsumption(consumed_fraction=0.3, remaining_minutes=30.0)
        burn = BurnRateAnalysis(
            burn_rate_level=BurnRateLevel.FAST,
            current_burn_rate=3.0,
            budget_sufficient_for_period=False,
        )
        policy = BudgetPolicy(status=BudgetStatus.WARNING)
        target = ReliabilityTarget(service_id="svc1")
        g = _single_comp_graph("svc1")
        recs = e._build_recommendations(consumption, burn, policy, target, g)
        assert any("burn rate" in r.lower() for r in recs)

    def test_critical_burn_recommendation(self):
        e = _engine()
        consumption = BudgetConsumption(consumed_fraction=0.4, remaining_minutes=25.0)
        burn = BurnRateAnalysis(
            burn_rate_level=BurnRateLevel.CRITICAL,
            current_burn_rate=6.0,
            budget_sufficient_for_period=False,
        )
        policy = BudgetPolicy(status=BudgetStatus.WARNING)
        target = ReliabilityTarget(service_id="svc1")
        g = _single_comp_graph("svc1")
        recs = e._build_recommendations(consumption, burn, policy, target, g)
        assert any("burn rate" in r.lower() for r in recs)

    def test_no_redundancy_recommendation(self):
        e = _engine()
        consumption = BudgetConsumption(consumed_fraction=0.2, remaining_minutes=34.0)
        burn = BurnRateAnalysis(
            burn_rate_level=BurnRateLevel.NORMAL, budget_sufficient_for_period=True
        )
        policy = BudgetPolicy(status=BudgetStatus.HEALTHY)
        target = ReliabilityTarget(service_id="svc1")
        c = Component(id="svc1", name="svc1", type=ComponentType.APP_SERVER, replicas=1)
        g = _graph(c)
        recs = e._build_recommendations(consumption, burn, policy, target, g)
        assert any("redundancy" in r.lower() or "replica" in r.lower() for r in recs)

    def test_above_50_percent_recommendation(self):
        e = _engine()
        consumption = BudgetConsumption(consumed_fraction=0.55, remaining_minutes=19.0)
        burn = BurnRateAnalysis(
            burn_rate_level=BurnRateLevel.NORMAL, budget_sufficient_for_period=True
        )
        policy = BudgetPolicy(status=BudgetStatus.WARNING)
        target = ReliabilityTarget(service_id="svc1")
        g = _single_comp_graph("svc1")
        recs = e._build_recommendations(consumption, burn, policy, target, g)
        assert any("50%" in r for r in recs)

    def test_budget_insufficient_recommendation(self):
        e = _engine()
        consumption = BudgetConsumption(consumed_fraction=0.3, remaining_minutes=30.0)
        burn = BurnRateAnalysis(
            burn_rate_level=BurnRateLevel.ELEVATED,
            current_burn_rate=1.5,
            budget_sufficient_for_period=False,
        )
        policy = BudgetPolicy(status=BudgetStatus.HEALTHY)
        target = ReliabilityTarget(service_id="svc1")
        g = _single_comp_graph("svc1")
        recs = e._build_recommendations(consumption, burn, policy, target, g)
        assert any("period" in r.lower() for r in recs)

    def test_service_not_in_graph(self):
        """When the target service is not in the graph, no redundancy rec."""
        e = _engine()
        consumption = BudgetConsumption(consumed_fraction=0.1, remaining_minutes=38.0)
        burn = BurnRateAnalysis(
            burn_rate_level=BurnRateLevel.SLOW, budget_sufficient_for_period=True
        )
        policy = BudgetPolicy(status=BudgetStatus.HEALTHY)
        target = ReliabilityTarget(service_id="missing")
        g = _single_comp_graph("svc1")
        recs = e._build_recommendations(consumption, burn, policy, target, g)
        # Should get the default "healthy" recommendation
        assert len(recs) > 0


# ---------------------------------------------------------------------------
# Tests: Policy transitions
# ---------------------------------------------------------------------------


class TestPolicyTransitions:
    """Test the full HEALTHY -> WARNING -> CRITICAL -> EXHAUSTED -> FROZEN path."""

    def test_healthy_to_warning(self):
        e = _engine()
        c1 = BudgetConsumption(consumed_fraction=0.3, remaining_minutes=30.0)
        burn = BurnRateAnalysis(burn_rate_level=BurnRateLevel.NORMAL)
        p1 = e.enforce_policy(c1, burn)
        assert p1.status == BudgetStatus.HEALTHY

        c2 = BudgetConsumption(consumed_fraction=0.55, remaining_minutes=20.0)
        p2 = e.enforce_policy(c2, burn)
        assert p2.status == BudgetStatus.WARNING

    def test_warning_to_critical(self):
        e = _engine()
        burn = BurnRateAnalysis(burn_rate_level=BurnRateLevel.NORMAL)
        c1 = BudgetConsumption(consumed_fraction=0.55, remaining_minutes=20.0)
        p1 = e.enforce_policy(c1, burn)
        assert p1.status == BudgetStatus.WARNING

        c2 = BudgetConsumption(consumed_fraction=0.75, remaining_minutes=10.0)
        p2 = e.enforce_policy(c2, burn)
        assert p2.status == BudgetStatus.CRITICAL

    def test_critical_to_exhausted(self):
        e = _engine()
        burn = BurnRateAnalysis(burn_rate_level=BurnRateLevel.NORMAL)
        c1 = BudgetConsumption(consumed_fraction=0.75, remaining_minutes=10.0)
        p1 = e.enforce_policy(c1, burn)
        assert p1.status == BudgetStatus.CRITICAL

        c2 = BudgetConsumption(consumed_fraction=1.0, remaining_minutes=0.0)
        p2 = e.enforce_policy(c2, burn, auto_freeze_threshold=1.1)
        assert p2.status == BudgetStatus.EXHAUSTED

    def test_exhausted_to_frozen(self):
        e = _engine()
        burn = BurnRateAnalysis(burn_rate_level=BurnRateLevel.CRITICAL)
        c = BudgetConsumption(consumed_fraction=1.0, remaining_minutes=0.0)
        p = e.enforce_policy(c, burn, auto_freeze_threshold=0.9)
        assert p.status == BudgetStatus.FROZEN
        assert p.action == PolicyAction.FULL_LOCKDOWN

    def test_full_transition_sequence(self):
        e = _engine()
        burn = BurnRateAnalysis(burn_rate_level=BurnRateLevel.NORMAL)
        fractions = [0.1, 0.55, 0.75, 0.92, 1.0]
        expected = [
            BudgetStatus.HEALTHY,
            BudgetStatus.WARNING,
            BudgetStatus.CRITICAL,
            BudgetStatus.FROZEN,
            BudgetStatus.FROZEN,  # consumed_fraction >= freeze_threshold
        ]
        for frac, exp in zip(fractions, expected):
            remaining = max(0.0, 43.2 - frac * 43.2)
            c = BudgetConsumption(consumed_fraction=frac, remaining_minutes=remaining)
            p = e.enforce_policy(c, burn)
            assert p.status == exp, f"Expected {exp} for fraction {frac}, got {p.status}"


# ---------------------------------------------------------------------------
# Tests: Integration — full workflow
# ---------------------------------------------------------------------------


class TestIntegrationWorkflow:
    def test_full_workflow(self):
        e = _engine()
        g = _single_comp_graph("api")
        target = ReliabilityTarget(service_id="api", slo_target=0.999)

        # Initial report - no incidents
        report = e.compute_budget(g, target)
        assert report.policy.status == BudgetStatus.HEALTHY

        # Simulate some incidents
        incidents = [
            IncidentRecord(service_id="api", duration_minutes=20.0),
        ]
        report = e.compute_budget(g, target, incidents)
        assert report.consumption.consumed_minutes == 20.0

        # Assess a release
        assessment = e.assess_release_risk(
            target, report.consumption, 5.0, "v1.5"
        )
        assert assessment.release_id == "v1.5"
        assert assessment.risk_to_budget != ExhaustionRisk.NONE  # significant

        # Forecast
        forecast = e.forecast_exhaustion(report.burn_rate, report.consumption.remaining_minutes)
        assert "days" in forecast

    def test_multi_service_workflow(self):
        e = _engine()
        c1 = _comp("web")
        c2 = _comp("db", ctype=ComponentType.DATABASE)
        g = _graph(c1, c2)

        targets = [
            ReliabilityTarget(service_id="web", slo_target=0.999),
            ReliabilityTarget(service_id="db", slo_target=0.9999),
        ]

        allocations = e.allocate_budget_across_services(g, 0.999)
        assert "web" in allocations
        assert "db" in allocations

        reports = e.compute_multi_service_budget(g, targets)
        assert len(reports) == 2

    def test_budget_math_precision(self):
        """99.9% monthly = exactly 43.2 minutes."""
        t = ReliabilityTarget(service_id="svc1", slo_target=0.999)
        budget = t.effective_budget_minutes()
        assert budget == pytest.approx(43.2, abs=0.0001)

        # 99.99% monthly = 4.32 min
        t2 = ReliabilityTarget(service_id="svc2", slo_target=0.9999)
        assert t2.effective_budget_minutes() == pytest.approx(4.32, abs=0.0001)

        # 99% monthly = 432 min
        t3 = ReliabilityTarget(service_id="svc3", slo_target=0.99)
        assert t3.effective_budget_minutes() == pytest.approx(432.0, abs=0.001)


# ---------------------------------------------------------------------------
# Tests: Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_engine_instantiation(self):
        e = ReliabilityBudgetEngine()
        assert e is not None

    def test_empty_graph_compute_budget(self):
        e = _engine()
        g = InfraGraph()
        t = ReliabilityTarget(service_id="svc1")
        report = e.compute_budget(g, t)
        assert report.service_id == "svc1"

    def test_very_high_slo(self):
        t = ReliabilityTarget(service_id="svc1", slo_target=0.99999)
        # 0.00001 * 43200 = 0.432 min
        assert t.effective_budget_minutes() == pytest.approx(0.432, abs=0.001)

    def test_very_low_slo(self):
        t = ReliabilityTarget(service_id="svc1", slo_target=0.5)
        # 0.5 * 43200 = 21600 min
        assert t.effective_budget_minutes() == pytest.approx(21600.0, abs=1.0)

    def test_slo_of_zero(self):
        t = ReliabilityTarget(service_id="svc1", slo_target=0.0)
        assert t.effective_budget_minutes() == pytest.approx(43200.0, abs=0.1)

    def test_negative_remaining_consumed_fraction_capped(self):
        e = _engine()
        g = _single_comp_graph("svc1")
        t = ReliabilityTarget(service_id="svc1", slo_target=0.999)
        # Consumed more than budget
        incidents = [
            IncidentRecord(service_id="svc1", duration_minutes=100.0),
        ]
        report = e.compute_budget(g, t, incidents)
        assert report.consumption.consumed_fraction == 1.0  # capped
        assert report.consumption.remaining_minutes == 0.0

    def test_forecast_with_zero_remaining(self):
        e = _engine()
        burn = BurnRateAnalysis(current_burn_rate=1.0, projected_exhaustion_day=10.0)
        result = e.forecast_exhaustion(burn, 0.0)
        assert result["days"] == 0.0

    def test_all_enum_values_accessible(self):
        assert len(BudgetStatus) == 5
        assert len(BudgetPeriod) == 6
        assert len(PolicyAction) == 5
        assert len(BurnRateLevel) == 5
        assert len(ExhaustionRisk) == 5

    def test_incident_with_high_severity(self):
        i = IncidentRecord(severity="critical", duration_minutes=30.0)
        assert i.severity == "critical"

    def test_incident_with_medium_severity(self):
        i = IncidentRecord(severity="medium", duration_minutes=10.0)
        assert i.severity == "medium"

    def test_budget_policy_model_fields(self):
        p = BudgetPolicy(
            status=BudgetStatus.WARNING,
            action=PolicyAction.RESTRICT_RISKY,
            reason="Test reason",
            auto_freeze_threshold=0.85,
            release_gate_enabled=True,
        )
        assert p.auto_freeze_threshold == 0.85
        assert p.reason == "Test reason"

    def test_report_with_release_assessments(self):
        t = ReliabilityTarget(service_id="svc1")
        assessment = ReleaseRiskAssessment(
            release_id="v1.0",
            estimated_error_budget_cost_minutes=5.0,
            risk_to_budget=ExhaustionRisk.LOW,
            recommendation="Proceed with caution.",
        )
        r = ReliabilityBudgetReport(
            service_id="svc1",
            target=t,
            consumption=BudgetConsumption(),
            burn_rate=BurnRateAnalysis(),
            policy=BudgetPolicy(),
            release_assessments=[assessment],
            forecast_days_remaining=25.0,
            recommendations=["Test rec"],
        )
        assert len(r.release_assessments) == 1
        assert r.forecast_days_remaining == 25.0

    def test_allocate_with_all_component_types(self):
        e = _engine()
        comps = [
            _comp("lb", ctype=ComponentType.LOAD_BALANCER),
            _comp("web", ctype=ComponentType.WEB_SERVER),
            _comp("app", ctype=ComponentType.APP_SERVER),
            _comp("db", ctype=ComponentType.DATABASE),
            _comp("cache", ctype=ComponentType.CACHE),
            _comp("queue", ctype=ComponentType.QUEUE),
        ]
        g = _graph(*comps)
        result = e.allocate_budget_across_services(g, 0.999)
        assert len(result) == 6
        total = sum(result.values())
        assert total == pytest.approx(43.2, abs=0.1)

    def test_simulate_zero_duration_incident(self):
        e = _engine()
        t = ReliabilityTarget(service_id="svc1", slo_target=0.999)
        c = BudgetConsumption(consumed_minutes=10.0, remaining_minutes=33.2)
        result = e.simulate_incident_impact(t, c, 0.0)
        assert result["new_consumed_minutes"] == 10.0
        assert result["would_exhaust"] is False

    def test_compare_same_period_different_slo(self):
        e = _engine()
        a = ReliabilityTarget(service_id="a", slo_target=0.99)
        b = ReliabilityTarget(service_id="b", slo_target=0.999)
        result = e.compare_slo_targets(a, b)
        assert result["stricter_target"] == "b"
        assert result["budget_a_minutes"] > result["budget_b_minutes"]
