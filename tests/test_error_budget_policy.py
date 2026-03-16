"""Comprehensive tests for Error Budget Policy Engine (target: 100% coverage)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from faultray.simulator.error_budget_policy import (
    BudgetForecast,
    BudgetState,
    BudgetThreshold,
    ErrorBudgetPolicyEngine,
    ErrorBudgetPolicyReport,
    ErrorBudgetSnapshot,
    EscalationLevel,
    PolicyAction,
    PolicyDecision,
    _DEFAULT_THRESHOLDS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime.now(timezone.utc)


def _snap(
    name: str = "api-availability",
    target: float = 99.9,
    window: int = 30,
    total: float = 43.2,
    consumed: float = 0.0,
    remaining: float = 100.0,
    state: BudgetState = BudgetState.HEALTHY,
    ts: datetime | None = None,
) -> ErrorBudgetSnapshot:
    return ErrorBudgetSnapshot(
        slo_name=name,
        slo_target=target,
        window_days=window,
        budget_total_minutes=total,
        budget_consumed_minutes=consumed,
        budget_remaining_percent=remaining,
        state=state,
        timestamp=ts or _NOW,
    )


# ---------------------------------------------------------------------------
# 1. BudgetState enum
# ---------------------------------------------------------------------------


class TestBudgetStateEnum:
    def test_healthy_value(self):
        assert BudgetState.HEALTHY.value == "healthy"

    def test_warning_value(self):
        assert BudgetState.WARNING.value == "warning"

    def test_critical_value(self):
        assert BudgetState.CRITICAL.value == "critical"

    def test_exhausted_value(self):
        assert BudgetState.EXHAUSTED.value == "exhausted"

    def test_is_str_enum(self):
        assert isinstance(BudgetState.HEALTHY, str)

    def test_member_count(self):
        assert len(BudgetState) == 4


# ---------------------------------------------------------------------------
# 2. PolicyAction enum
# ---------------------------------------------------------------------------


class TestPolicyActionEnum:
    def test_allow_releases(self):
        assert PolicyAction.ALLOW_RELEASES.value == "allow_releases"

    def test_slow_releases(self):
        assert PolicyAction.SLOW_RELEASES.value == "slow_releases"

    def test_freeze_releases(self):
        assert PolicyAction.FREEZE_RELEASES.value == "freeze_releases"

    def test_emergency_only(self):
        assert PolicyAction.EMERGENCY_ONLY.value == "emergency_only"

    def test_is_str_enum(self):
        assert isinstance(PolicyAction.ALLOW_RELEASES, str)

    def test_member_count(self):
        assert len(PolicyAction) == 4


# ---------------------------------------------------------------------------
# 3. EscalationLevel enum
# ---------------------------------------------------------------------------


class TestEscalationLevelEnum:
    def test_team(self):
        assert EscalationLevel.TEAM.value == "team"

    def test_management(self):
        assert EscalationLevel.MANAGEMENT.value == "management"

    def test_vp(self):
        assert EscalationLevel.VP.value == "vp"

    def test_executive(self):
        assert EscalationLevel.EXECUTIVE.value == "executive"

    def test_is_str_enum(self):
        assert isinstance(EscalationLevel.TEAM, str)

    def test_member_count(self):
        assert len(EscalationLevel) == 4


# ---------------------------------------------------------------------------
# 4. BudgetThreshold model
# ---------------------------------------------------------------------------


class TestBudgetThreshold:
    def test_create(self):
        t = BudgetThreshold(
            state=BudgetState.HEALTHY,
            min_remaining_percent=50.0,
            max_remaining_percent=100.0,
            action=PolicyAction.ALLOW_RELEASES,
            escalation=EscalationLevel.TEAM,
            description="healthy",
        )
        assert t.state == BudgetState.HEALTHY
        assert t.min_remaining_percent == 50.0
        assert t.max_remaining_percent == 100.0

    def test_all_fields(self):
        t = _DEFAULT_THRESHOLDS[0]
        assert t.action == PolicyAction.ALLOW_RELEASES
        assert t.escalation == EscalationLevel.TEAM
        assert len(t.description) > 0


# ---------------------------------------------------------------------------
# 5. ErrorBudgetSnapshot model
# ---------------------------------------------------------------------------


class TestErrorBudgetSnapshot:
    def test_create_snapshot(self):
        s = _snap()
        assert s.slo_name == "api-availability"
        assert s.slo_target == 99.9
        assert s.window_days == 30

    def test_snapshot_fields(self):
        s = _snap(consumed=10.0, remaining=76.85)
        assert s.budget_consumed_minutes == 10.0
        assert s.budget_remaining_percent == 76.85

    def test_snapshot_timestamp(self):
        s = _snap()
        assert s.timestamp == _NOW

    def test_snapshot_state(self):
        s = _snap(state=BudgetState.CRITICAL)
        assert s.state == BudgetState.CRITICAL


# ---------------------------------------------------------------------------
# 6. PolicyDecision model
# ---------------------------------------------------------------------------


class TestPolicyDecision:
    def test_create(self):
        s = _snap()
        d = PolicyDecision(
            snapshot=s,
            action=PolicyAction.ALLOW_RELEASES,
            escalation=EscalationLevel.TEAM,
            reason="test",
            conditions_for_release=["ok"],
        )
        assert d.action == PolicyAction.ALLOW_RELEASES
        assert d.conditions_for_release == ["ok"]


# ---------------------------------------------------------------------------
# 7. BudgetForecast model
# ---------------------------------------------------------------------------


class TestBudgetForecast:
    def test_create_with_exhaustion(self):
        f = BudgetForecast(
            days_until_exhaustion=10.0,
            current_burn_rate=0.5,
            projected_end_of_window_remaining=50.0,
            on_track=True,
        )
        assert f.days_until_exhaustion == 10.0
        assert f.on_track is True

    def test_create_without_exhaustion(self):
        f = BudgetForecast(
            days_until_exhaustion=None,
            current_burn_rate=0.0,
            projected_end_of_window_remaining=100.0,
            on_track=True,
        )
        assert f.days_until_exhaustion is None


# ---------------------------------------------------------------------------
# 8. ErrorBudgetPolicyReport model
# ---------------------------------------------------------------------------


class TestErrorBudgetPolicyReport:
    def test_create(self):
        r = ErrorBudgetPolicyReport(
            snapshots=[],
            decisions=[],
            forecasts=[],
            overall_action=PolicyAction.ALLOW_RELEASES,
            recommendations=["ok"],
        )
        assert r.overall_action == PolicyAction.ALLOW_RELEASES
        assert r.recommendations == ["ok"]


# ---------------------------------------------------------------------------
# 9. Default thresholds
# ---------------------------------------------------------------------------


class TestDefaultThresholds:
    def test_count(self):
        assert len(_DEFAULT_THRESHOLDS) == 4

    def test_healthy_threshold(self):
        t = _DEFAULT_THRESHOLDS[0]
        assert t.state == BudgetState.HEALTHY
        assert t.min_remaining_percent == 50.0
        assert t.max_remaining_percent == 100.0
        assert t.action == PolicyAction.ALLOW_RELEASES
        assert t.escalation == EscalationLevel.TEAM

    def test_warning_threshold(self):
        t = _DEFAULT_THRESHOLDS[1]
        assert t.state == BudgetState.WARNING
        assert t.min_remaining_percent == 20.0
        assert t.max_remaining_percent == 50.0
        assert t.action == PolicyAction.SLOW_RELEASES
        assert t.escalation == EscalationLevel.MANAGEMENT

    def test_critical_threshold(self):
        t = _DEFAULT_THRESHOLDS[2]
        assert t.state == BudgetState.CRITICAL
        assert t.min_remaining_percent == 1.0
        assert t.max_remaining_percent == 20.0
        assert t.action == PolicyAction.FREEZE_RELEASES
        assert t.escalation == EscalationLevel.VP

    def test_exhausted_threshold(self):
        t = _DEFAULT_THRESHOLDS[3]
        assert t.state == BudgetState.EXHAUSTED
        assert t.min_remaining_percent == 0.0
        assert t.max_remaining_percent == 1.0
        assert t.action == PolicyAction.EMERGENCY_ONLY
        assert t.escalation == EscalationLevel.EXECUTIVE


# ---------------------------------------------------------------------------
# 10. Engine init
# ---------------------------------------------------------------------------


class TestEngineInit:
    def test_default_thresholds_copied(self):
        engine = ErrorBudgetPolicyEngine()
        assert len(engine.thresholds) == 4
        # Ensure it is a copy, not the original list
        engine.thresholds.pop()
        assert len(_DEFAULT_THRESHOLDS) == 4

    def test_thresholds_are_default(self):
        engine = ErrorBudgetPolicyEngine()
        for i, t in enumerate(engine.thresholds):
            assert t.state == _DEFAULT_THRESHOLDS[i].state


# ---------------------------------------------------------------------------
# 11. create_snapshot
# ---------------------------------------------------------------------------


class TestCreateSnapshot:
    def test_zero_errors(self):
        engine = ErrorBudgetPolicyEngine()
        snap = engine.create_snapshot("svc", 99.9, 0.0, 30)
        assert snap.budget_remaining_percent == 100.0
        assert snap.state == BudgetState.HEALTHY

    def test_full_budget_consumed(self):
        engine = ErrorBudgetPolicyEngine()
        # 99.9% SLO, 30-day window => budget = 0.001 * 30 * 24 * 60 = 43.2 min
        snap = engine.create_snapshot("svc", 99.9, 43.2, 30)
        assert snap.budget_remaining_percent == pytest.approx(0.0)
        assert snap.state == BudgetState.EXHAUSTED

    def test_half_consumed(self):
        engine = ErrorBudgetPolicyEngine()
        snap = engine.create_snapshot("svc", 99.9, 21.6, 30)
        assert snap.budget_remaining_percent == pytest.approx(50.0, abs=1e-4)
        # Floating point: remaining is just under 50%, so classified WARNING
        assert snap.state in (BudgetState.HEALTHY, BudgetState.WARNING)

    def test_warning_state(self):
        engine = ErrorBudgetPolicyEngine()
        # remaining ~30%
        consumed = 43.2 * 0.70
        snap = engine.create_snapshot("svc", 99.9, consumed, 30)
        assert snap.state == BudgetState.WARNING

    def test_critical_state(self):
        engine = ErrorBudgetPolicyEngine()
        # remaining ~10%
        consumed = 43.2 * 0.90
        snap = engine.create_snapshot("svc", 99.9, consumed, 30)
        assert snap.state == BudgetState.CRITICAL

    def test_over_consumed_clamped(self):
        engine = ErrorBudgetPolicyEngine()
        snap = engine.create_snapshot("svc", 99.9, 999.0, 30)
        assert snap.budget_consumed_minutes == pytest.approx(43.2, rel=1e-6)
        assert snap.budget_remaining_percent == 0.0
        assert snap.state == BudgetState.EXHAUSTED

    def test_slo_name_preserved(self):
        engine = ErrorBudgetPolicyEngine()
        snap = engine.create_snapshot("my-slo", 99.9, 0.0, 30)
        assert snap.slo_name == "my-slo"

    def test_slo_target_preserved(self):
        engine = ErrorBudgetPolicyEngine()
        snap = engine.create_snapshot("svc", 99.5, 0.0, 30)
        assert snap.slo_target == 99.5

    def test_window_days_preserved(self):
        engine = ErrorBudgetPolicyEngine()
        snap = engine.create_snapshot("svc", 99.9, 0.0, 7)
        assert snap.window_days == 7

    def test_budget_total_calculation(self):
        engine = ErrorBudgetPolicyEngine()
        snap = engine.create_snapshot("svc", 99.0, 0.0, 30)
        # 1% * 30 * 1440 = 432 minutes
        assert snap.budget_total_minutes == pytest.approx(432.0)

    def test_timestamp_is_utc(self):
        engine = ErrorBudgetPolicyEngine()
        snap = engine.create_snapshot("svc", 99.9, 0.0, 30)
        assert snap.timestamp.tzinfo == timezone.utc

    def test_100_percent_slo(self):
        engine = ErrorBudgetPolicyEngine()
        snap = engine.create_snapshot("svc", 100.0, 0.0, 30)
        # budget total = 0, remaining = 0%
        assert snap.budget_total_minutes == 0.0
        assert snap.budget_remaining_percent == 0.0


# ---------------------------------------------------------------------------
# 12. _classify_state
# ---------------------------------------------------------------------------


class TestClassifyState:
    def test_healthy_at_100(self):
        engine = ErrorBudgetPolicyEngine()
        assert engine._classify_state(100.0) == BudgetState.HEALTHY

    def test_healthy_at_50(self):
        engine = ErrorBudgetPolicyEngine()
        assert engine._classify_state(50.0) == BudgetState.HEALTHY

    def test_warning_at_49(self):
        engine = ErrorBudgetPolicyEngine()
        assert engine._classify_state(49.9) == BudgetState.WARNING

    def test_warning_at_20(self):
        engine = ErrorBudgetPolicyEngine()
        assert engine._classify_state(20.0) == BudgetState.WARNING

    def test_critical_at_19(self):
        engine = ErrorBudgetPolicyEngine()
        assert engine._classify_state(19.9) == BudgetState.CRITICAL

    def test_critical_at_1(self):
        engine = ErrorBudgetPolicyEngine()
        assert engine._classify_state(1.0) == BudgetState.CRITICAL

    def test_exhausted_at_0_9(self):
        engine = ErrorBudgetPolicyEngine()
        assert engine._classify_state(0.9) == BudgetState.EXHAUSTED

    def test_exhausted_at_0(self):
        engine = ErrorBudgetPolicyEngine()
        assert engine._classify_state(0.0) == BudgetState.EXHAUSTED


# ---------------------------------------------------------------------------
# 13. _find_threshold
# ---------------------------------------------------------------------------


class TestFindThreshold:
    def test_find_healthy(self):
        engine = ErrorBudgetPolicyEngine()
        t = engine._find_threshold(BudgetState.HEALTHY)
        assert t.state == BudgetState.HEALTHY

    def test_find_warning(self):
        engine = ErrorBudgetPolicyEngine()
        t = engine._find_threshold(BudgetState.WARNING)
        assert t.state == BudgetState.WARNING

    def test_find_critical(self):
        engine = ErrorBudgetPolicyEngine()
        t = engine._find_threshold(BudgetState.CRITICAL)
        assert t.state == BudgetState.CRITICAL

    def test_find_exhausted(self):
        engine = ErrorBudgetPolicyEngine()
        t = engine._find_threshold(BudgetState.EXHAUSTED)
        assert t.state == BudgetState.EXHAUSTED

    def test_fallback_when_state_missing(self):
        engine = ErrorBudgetPolicyEngine()
        # Remove all except exhausted
        engine.thresholds = [
            t for t in engine.thresholds if t.state == BudgetState.EXHAUSTED
        ]
        # Requesting HEALTHY should fall back to last (EXHAUSTED)
        t = engine._find_threshold(BudgetState.HEALTHY)
        assert t.state == BudgetState.EXHAUSTED


# ---------------------------------------------------------------------------
# 14. evaluate_policy
# ---------------------------------------------------------------------------


class TestEvaluatePolicy:
    def test_healthy_allows_releases(self):
        engine = ErrorBudgetPolicyEngine()
        snap = _snap(state=BudgetState.HEALTHY, remaining=80.0)
        d = engine.evaluate_policy(snap)
        assert d.action == PolicyAction.ALLOW_RELEASES
        assert d.escalation == EscalationLevel.TEAM

    def test_warning_slows_releases(self):
        engine = ErrorBudgetPolicyEngine()
        snap = _snap(state=BudgetState.WARNING, remaining=35.0)
        d = engine.evaluate_policy(snap)
        assert d.action == PolicyAction.SLOW_RELEASES
        assert d.escalation == EscalationLevel.MANAGEMENT

    def test_critical_freezes_releases(self):
        engine = ErrorBudgetPolicyEngine()
        snap = _snap(state=BudgetState.CRITICAL, remaining=10.0)
        d = engine.evaluate_policy(snap)
        assert d.action == PolicyAction.FREEZE_RELEASES
        assert d.escalation == EscalationLevel.VP

    def test_exhausted_emergency_only(self):
        engine = ErrorBudgetPolicyEngine()
        snap = _snap(state=BudgetState.EXHAUSTED, remaining=0.0)
        d = engine.evaluate_policy(snap)
        assert d.action == PolicyAction.EMERGENCY_ONLY
        assert d.escalation == EscalationLevel.EXECUTIVE

    def test_reason_is_set(self):
        engine = ErrorBudgetPolicyEngine()
        snap = _snap(state=BudgetState.HEALTHY)
        d = engine.evaluate_policy(snap)
        assert len(d.reason) > 0

    def test_snapshot_preserved(self):
        engine = ErrorBudgetPolicyEngine()
        snap = _snap(name="my-slo")
        d = engine.evaluate_policy(snap)
        assert d.snapshot.slo_name == "my-slo"


# ---------------------------------------------------------------------------
# 15. _conditions_for_release
# ---------------------------------------------------------------------------


class TestConditionsForRelease:
    def test_allow_conditions(self):
        engine = ErrorBudgetPolicyEngine()
        snap = _snap(state=BudgetState.HEALTHY)
        d = engine.evaluate_policy(snap)
        assert "Standard release process applies." in d.conditions_for_release

    def test_slow_conditions(self):
        engine = ErrorBudgetPolicyEngine()
        snap = _snap(state=BudgetState.WARNING)
        d = engine.evaluate_policy(snap)
        assert any("50%" in c for c in d.conditions_for_release)
        assert any("rollback" in c for c in d.conditions_for_release)

    def test_freeze_conditions(self):
        engine = ErrorBudgetPolicyEngine()
        snap = _snap(state=BudgetState.CRITICAL)
        d = engine.evaluate_policy(snap)
        assert any("VP" in c for c in d.conditions_for_release)

    def test_emergency_conditions(self):
        engine = ErrorBudgetPolicyEngine()
        snap = _snap(state=BudgetState.EXHAUSTED)
        d = engine.evaluate_policy(snap)
        assert any("P0/P1" in c for c in d.conditions_for_release)
        assert any("Executive" in c for c in d.conditions_for_release)
        assert any("4 hours" in c for c in d.conditions_for_release)

    def test_emergency_has_three_conditions(self):
        engine = ErrorBudgetPolicyEngine()
        snap = _snap(state=BudgetState.EXHAUSTED)
        d = engine.evaluate_policy(snap)
        assert len(d.conditions_for_release) == 3

    def test_allow_has_one_condition(self):
        engine = ErrorBudgetPolicyEngine()
        snap = _snap(state=BudgetState.HEALTHY)
        d = engine.evaluate_policy(snap)
        assert len(d.conditions_for_release) == 1

    def test_slow_has_two_conditions(self):
        engine = ErrorBudgetPolicyEngine()
        snap = _snap(state=BudgetState.WARNING)
        d = engine.evaluate_policy(snap)
        assert len(d.conditions_for_release) == 2

    def test_freeze_has_two_conditions(self):
        engine = ErrorBudgetPolicyEngine()
        snap = _snap(state=BudgetState.CRITICAL)
        d = engine.evaluate_policy(snap)
        assert len(d.conditions_for_release) == 2


# ---------------------------------------------------------------------------
# 16. forecast_budget
# ---------------------------------------------------------------------------


class TestForecastBudget:
    def test_zero_error_rate(self):
        engine = ErrorBudgetPolicyEngine()
        snap = _snap(total=43.2, consumed=0.0, remaining=100.0)
        f = engine.forecast_budget(snap, 0.0)
        assert f.days_until_exhaustion is None
        assert f.current_burn_rate == 0.0
        assert f.on_track is True

    def test_moderate_error_rate(self):
        engine = ErrorBudgetPolicyEngine()
        # 43.2 total, 30 day window => 1.44 min/day budget
        snap = _snap(total=43.2, consumed=0.0, remaining=100.0, window=30)
        f = engine.forecast_budget(snap, 1.44)
        assert f.current_burn_rate == pytest.approx(1.0)
        assert f.on_track is True

    def test_high_burn_rate(self):
        engine = ErrorBudgetPolicyEngine()
        snap = _snap(total=43.2, consumed=0.0, remaining=100.0, window=30)
        # 2x the daily budget
        f = engine.forecast_budget(snap, 2.88)
        assert f.current_burn_rate == pytest.approx(2.0)
        assert f.on_track is False

    def test_days_until_exhaustion(self):
        engine = ErrorBudgetPolicyEngine()
        snap = _snap(total=43.2, consumed=0.0, remaining=100.0, window=30)
        # consuming 4.32 min/day => exhaustion in 10 days
        f = engine.forecast_budget(snap, 4.32)
        assert f.days_until_exhaustion == pytest.approx(10.0)

    def test_partially_consumed_budget(self):
        engine = ErrorBudgetPolicyEngine()
        snap = _snap(total=43.2, consumed=21.6, remaining=50.0, window=30)
        # 4.32 min/day => remaining 21.6 / 4.32 = 5 days
        f = engine.forecast_budget(snap, 4.32)
        assert f.days_until_exhaustion == pytest.approx(5.0)

    def test_projected_remaining_healthy(self):
        engine = ErrorBudgetPolicyEngine()
        snap = _snap(total=43.2, consumed=0.0, remaining=100.0, window=30)
        # 0.5 min/day => 15 min consumed => 28.2 remaining => ~65.3%
        f = engine.forecast_budget(snap, 0.5)
        assert f.projected_end_of_window_remaining > 0.0

    def test_projected_remaining_overconsumed(self):
        engine = ErrorBudgetPolicyEngine()
        snap = _snap(total=43.2, consumed=0.0, remaining=100.0, window=30)
        # 10 min/day => way over budget
        f = engine.forecast_budget(snap, 10.0)
        assert f.projected_end_of_window_remaining == 0.0

    def test_on_track_true(self):
        engine = ErrorBudgetPolicyEngine()
        snap = _snap(total=43.2, consumed=0.0, remaining=100.0, window=30)
        f = engine.forecast_budget(snap, 0.5)
        assert f.on_track is True

    def test_on_track_false(self):
        engine = ErrorBudgetPolicyEngine()
        snap = _snap(total=43.2, consumed=0.0, remaining=100.0, window=30)
        f = engine.forecast_budget(snap, 5.0)
        assert f.on_track is False

    def test_zero_budget_total(self):
        engine = ErrorBudgetPolicyEngine()
        snap = _snap(total=0.0, consumed=0.0, remaining=0.0, window=30)
        f = engine.forecast_budget(snap, 1.0)
        assert f.current_burn_rate == 0.0
        assert f.projected_end_of_window_remaining == 0.0

    def test_zero_window_days(self):
        engine = ErrorBudgetPolicyEngine()
        snap = _snap(total=43.2, consumed=0.0, remaining=100.0, window=0)
        f = engine.forecast_budget(snap, 1.0)
        assert f.current_burn_rate == 0.0

    def test_no_remaining_budget(self):
        engine = ErrorBudgetPolicyEngine()
        snap = _snap(total=43.2, consumed=43.2, remaining=0.0, window=30)
        f = engine.forecast_budget(snap, 1.0)
        assert f.days_until_exhaustion is None


# ---------------------------------------------------------------------------
# 17. should_allow_release
# ---------------------------------------------------------------------------


class TestShouldAllowRelease:
    def test_empty_list(self):
        engine = ErrorBudgetPolicyEngine()
        assert engine.should_allow_release([]) is True

    def test_all_healthy(self):
        engine = ErrorBudgetPolicyEngine()
        snaps = [
            _snap(name="a", state=BudgetState.HEALTHY),
            _snap(name="b", state=BudgetState.HEALTHY),
        ]
        assert engine.should_allow_release(snaps) is True

    def test_one_warning_still_allowed(self):
        engine = ErrorBudgetPolicyEngine()
        snaps = [
            _snap(name="a", state=BudgetState.HEALTHY),
            _snap(name="b", state=BudgetState.WARNING),
        ]
        assert engine.should_allow_release(snaps) is True

    def test_one_critical_blocks(self):
        engine = ErrorBudgetPolicyEngine()
        snaps = [
            _snap(name="a", state=BudgetState.HEALTHY),
            _snap(name="b", state=BudgetState.CRITICAL),
        ]
        assert engine.should_allow_release(snaps) is False

    def test_one_exhausted_blocks(self):
        engine = ErrorBudgetPolicyEngine()
        snaps = [
            _snap(name="a", state=BudgetState.HEALTHY),
            _snap(name="b", state=BudgetState.EXHAUSTED),
        ]
        assert engine.should_allow_release(snaps) is False

    def test_single_healthy(self):
        engine = ErrorBudgetPolicyEngine()
        assert engine.should_allow_release([_snap(state=BudgetState.HEALTHY)]) is True

    def test_single_exhausted(self):
        engine = ErrorBudgetPolicyEngine()
        assert engine.should_allow_release([_snap(state=BudgetState.EXHAUSTED)]) is False

    def test_all_warning(self):
        engine = ErrorBudgetPolicyEngine()
        snaps = [
            _snap(name="a", state=BudgetState.WARNING),
            _snap(name="b", state=BudgetState.WARNING),
        ]
        assert engine.should_allow_release(snaps) is True

    def test_all_critical(self):
        engine = ErrorBudgetPolicyEngine()
        snaps = [
            _snap(name="a", state=BudgetState.CRITICAL),
            _snap(name="b", state=BudgetState.CRITICAL),
        ]
        assert engine.should_allow_release(snaps) is False


# ---------------------------------------------------------------------------
# 18. get_recovery_actions
# ---------------------------------------------------------------------------


class TestGetRecoveryActions:
    def test_healthy_no_action(self):
        engine = ErrorBudgetPolicyEngine()
        snap = _snap(state=BudgetState.HEALTHY)
        actions = engine.get_recovery_actions(snap)
        assert len(actions) == 1
        assert "healthy" in actions[0].lower()

    def test_warning_actions(self):
        engine = ErrorBudgetPolicyEngine()
        snap = _snap(state=BudgetState.WARNING)
        actions = engine.get_recovery_actions(snap)
        assert len(actions) == 3
        assert any("cadence" in a.lower() for a in actions)
        assert any("incident" in a.lower() for a in actions)
        assert any("redundancy" in a.lower() for a in actions)

    def test_critical_actions(self):
        engine = ErrorBudgetPolicyEngine()
        snap = _snap(state=BudgetState.CRITICAL)
        actions = engine.get_recovery_actions(snap)
        assert len(actions) == 3
        assert any("freeze" in a.lower() for a in actions)
        assert any("reliability" in a.lower() for a in actions)
        assert any("monitoring" in a.lower() for a in actions)

    def test_exhausted_actions(self):
        engine = ErrorBudgetPolicyEngine()
        snap = _snap(state=BudgetState.EXHAUSTED)
        actions = engine.get_recovery_actions(snap)
        assert len(actions) == 4
        assert any("halt" in a.lower() for a in actions)
        assert any("incident review" in a.lower() for a in actions)
        assert any("on-call" in a.lower() for a in actions)
        assert any("executive" in a.lower() for a in actions)


# ---------------------------------------------------------------------------
# 19. _worst_action
# ---------------------------------------------------------------------------


class TestWorstAction:
    def test_emergency_is_worst(self):
        engine = ErrorBudgetPolicyEngine()
        snap_h = _snap(state=BudgetState.HEALTHY)
        snap_e = _snap(state=BudgetState.EXHAUSTED)
        d1 = engine.evaluate_policy(snap_h)
        d2 = engine.evaluate_policy(snap_e)
        assert ErrorBudgetPolicyEngine._worst_action([d1, d2]) == PolicyAction.EMERGENCY_ONLY

    def test_freeze_over_slow(self):
        engine = ErrorBudgetPolicyEngine()
        snap_w = _snap(state=BudgetState.WARNING)
        snap_c = _snap(state=BudgetState.CRITICAL)
        d1 = engine.evaluate_policy(snap_w)
        d2 = engine.evaluate_policy(snap_c)
        assert ErrorBudgetPolicyEngine._worst_action([d1, d2]) == PolicyAction.FREEZE_RELEASES

    def test_slow_over_allow(self):
        engine = ErrorBudgetPolicyEngine()
        snap_h = _snap(state=BudgetState.HEALTHY)
        snap_w = _snap(state=BudgetState.WARNING)
        d1 = engine.evaluate_policy(snap_h)
        d2 = engine.evaluate_policy(snap_w)
        assert ErrorBudgetPolicyEngine._worst_action([d1, d2]) == PolicyAction.SLOW_RELEASES

    def test_all_allow(self):
        engine = ErrorBudgetPolicyEngine()
        snap = _snap(state=BudgetState.HEALTHY)
        d = engine.evaluate_policy(snap)
        assert ErrorBudgetPolicyEngine._worst_action([d]) == PolicyAction.ALLOW_RELEASES

    def test_empty_decisions(self):
        assert ErrorBudgetPolicyEngine._worst_action([]) == PolicyAction.ALLOW_RELEASES


# ---------------------------------------------------------------------------
# 20. generate_report
# ---------------------------------------------------------------------------


class TestGenerateReport:
    def test_empty_snapshots(self):
        engine = ErrorBudgetPolicyEngine()
        report = engine.generate_report([])
        assert report.overall_action == PolicyAction.ALLOW_RELEASES
        assert len(report.snapshots) == 0
        assert len(report.decisions) == 0
        assert len(report.forecasts) == 0

    def test_single_healthy_snapshot(self):
        engine = ErrorBudgetPolicyEngine()
        snap = _snap(state=BudgetState.HEALTHY, remaining=80.0)
        report = engine.generate_report([snap])
        assert report.overall_action == PolicyAction.ALLOW_RELEASES
        assert len(report.decisions) == 1

    def test_mixed_snapshots_overall_action(self):
        engine = ErrorBudgetPolicyEngine()
        snap_h = _snap(name="a", state=BudgetState.HEALTHY)
        snap_c = _snap(name="b", state=BudgetState.CRITICAL)
        report = engine.generate_report([snap_h, snap_c])
        assert report.overall_action == PolicyAction.FREEZE_RELEASES

    def test_report_with_error_rates(self):
        engine = ErrorBudgetPolicyEngine()
        snap = _snap(
            name="api",
            state=BudgetState.HEALTHY,
            total=43.2,
            consumed=0.0,
            remaining=100.0,
            window=30,
        )
        report = engine.generate_report([snap], error_rates={"api": 1.0})
        assert len(report.forecasts) == 1
        assert report.forecasts[0].current_burn_rate > 0.0

    def test_report_without_error_rates(self):
        engine = ErrorBudgetPolicyEngine()
        snap = _snap(state=BudgetState.HEALTHY)
        report = engine.generate_report([snap])
        assert len(report.forecasts) == 1
        assert report.forecasts[0].current_burn_rate == 0.0

    def test_report_recommendations_healthy(self):
        engine = ErrorBudgetPolicyEngine()
        snap = _snap(state=BudgetState.HEALTHY, remaining=80.0)
        report = engine.generate_report([snap])
        assert any("No action required" in r for r in report.recommendations)

    def test_report_recommendations_critical(self):
        engine = ErrorBudgetPolicyEngine()
        snap = _snap(
            name="svc",
            state=BudgetState.CRITICAL,
            remaining=5.0,
            total=43.2,
            consumed=41.04,
            window=30,
        )
        report = engine.generate_report([snap])
        assert any("critical" in r.lower() for r in report.recommendations)

    def test_report_recommendations_exhausted(self):
        engine = ErrorBudgetPolicyEngine()
        snap = _snap(
            name="svc",
            state=BudgetState.EXHAUSTED,
            remaining=0.0,
            total=43.2,
            consumed=43.2,
            window=30,
        )
        report = engine.generate_report([snap])
        assert any("exhausted" in r.lower() for r in report.recommendations)

    def test_report_forecast_near_exhaustion_recommendation(self):
        engine = ErrorBudgetPolicyEngine()
        snap = _snap(
            name="svc",
            state=BudgetState.WARNING,
            remaining=30.0,
            total=43.2,
            consumed=30.24,
            window=30,
        )
        # 5 min/day => exhaustion in ~2.6 days
        report = engine.generate_report([snap], error_rates={"svc": 5.0})
        assert any("take action" in r.lower() for r in report.recommendations)

    def test_report_burn_rate_recommendation(self):
        engine = ErrorBudgetPolicyEngine()
        snap = _snap(
            name="svc",
            state=BudgetState.WARNING,
            remaining=40.0,
            total=43.2,
            consumed=25.92,
            window=30,
        )
        # High burn rate but enough remaining that exhaustion is > 7 days
        # 43.2 / 30 = 1.44/day budget, 3.0 > 1.44 => burn_rate > 1
        report = engine.generate_report([snap], error_rates={"svc": 3.0})
        assert any("burn rate" in r.lower() for r in report.recommendations)

    def test_report_multiple_snapshots(self):
        engine = ErrorBudgetPolicyEngine()
        snaps = [
            _snap(name="a", state=BudgetState.HEALTHY, remaining=80.0),
            _snap(name="b", state=BudgetState.WARNING, remaining=35.0),
            _snap(name="c", state=BudgetState.CRITICAL, remaining=5.0),
        ]
        report = engine.generate_report(snaps)
        assert len(report.snapshots) == 3
        assert len(report.decisions) == 3
        assert len(report.forecasts) == 3
        assert report.overall_action == PolicyAction.FREEZE_RELEASES

    def test_report_error_rates_missing_key(self):
        engine = ErrorBudgetPolicyEngine()
        snap = _snap(name="svc", state=BudgetState.HEALTHY, total=43.2, window=30)
        report = engine.generate_report([snap], error_rates={"other": 1.0})
        # Missing key => 0.0 error rate used
        assert report.forecasts[0].current_burn_rate == 0.0


# ---------------------------------------------------------------------------
# 21. _build_recommendations
# ---------------------------------------------------------------------------


class TestBuildRecommendations:
    def test_no_issues_returns_default(self):
        recs = ErrorBudgetPolicyEngine._build_recommendations(
            [_snap(state=BudgetState.HEALTHY, remaining=80.0)],
            [],
            [
                BudgetForecast(
                    days_until_exhaustion=None,
                    current_burn_rate=0.0,
                    projected_end_of_window_remaining=100.0,
                    on_track=True,
                )
            ],
        )
        assert len(recs) == 1
        assert "No action required" in recs[0]

    def test_exhausted_recommendation(self):
        recs = ErrorBudgetPolicyEngine._build_recommendations(
            [_snap(name="x", state=BudgetState.EXHAUSTED, remaining=0.0)],
            [],
            [
                BudgetForecast(
                    days_until_exhaustion=None,
                    current_burn_rate=0.0,
                    projected_end_of_window_remaining=0.0,
                    on_track=False,
                )
            ],
        )
        assert any("exhausted" in r.lower() for r in recs)

    def test_critical_recommendation(self):
        recs = ErrorBudgetPolicyEngine._build_recommendations(
            [_snap(name="x", state=BudgetState.CRITICAL, remaining=5.0)],
            [],
            [
                BudgetForecast(
                    days_until_exhaustion=30.0,
                    current_burn_rate=0.5,
                    projected_end_of_window_remaining=50.0,
                    on_track=True,
                )
            ],
        )
        assert any("critical" in r.lower() for r in recs)

    def test_near_exhaustion_recommendation(self):
        recs = ErrorBudgetPolicyEngine._build_recommendations(
            [_snap(name="x", state=BudgetState.WARNING, remaining=30.0)],
            [],
            [
                BudgetForecast(
                    days_until_exhaustion=3.0,
                    current_burn_rate=2.0,
                    projected_end_of_window_remaining=0.0,
                    on_track=False,
                )
            ],
        )
        assert any("take action" in r.lower() for r in recs)

    def test_high_burn_rate_recommendation(self):
        recs = ErrorBudgetPolicyEngine._build_recommendations(
            [_snap(name="x", state=BudgetState.HEALTHY, remaining=80.0)],
            [],
            [
                BudgetForecast(
                    days_until_exhaustion=20.0,
                    current_burn_rate=2.0,
                    projected_end_of_window_remaining=0.0,
                    on_track=False,
                )
            ],
        )
        assert any("burn rate" in r.lower() for r in recs)


# ---------------------------------------------------------------------------
# 22. End-to-end / integration scenarios
# ---------------------------------------------------------------------------


class TestEndToEnd:
    def test_full_lifecycle_healthy(self):
        engine = ErrorBudgetPolicyEngine()
        snap = engine.create_snapshot("api", 99.9, 0.0, 30)
        decision = engine.evaluate_policy(snap)
        assert decision.action == PolicyAction.ALLOW_RELEASES
        assert engine.should_allow_release([snap]) is True
        actions = engine.get_recovery_actions(snap)
        assert "healthy" in actions[0].lower()

    def test_full_lifecycle_exhausted(self):
        engine = ErrorBudgetPolicyEngine()
        snap = engine.create_snapshot("api", 99.9, 43.2, 30)
        decision = engine.evaluate_policy(snap)
        assert decision.action == PolicyAction.EMERGENCY_ONLY
        assert engine.should_allow_release([snap]) is False
        actions = engine.get_recovery_actions(snap)
        assert len(actions) == 4

    def test_report_end_to_end(self):
        engine = ErrorBudgetPolicyEngine()
        snaps = [
            engine.create_snapshot("api", 99.9, 5.0, 30),
            engine.create_snapshot("web", 99.5, 100.0, 30),
        ]
        rates = {"api": 0.5, "web": 10.0}
        report = engine.generate_report(snaps, error_rates=rates)
        assert isinstance(report, ErrorBudgetPolicyReport)
        assert len(report.snapshots) == 2
        assert len(report.recommendations) > 0

    def test_forecast_end_to_end(self):
        engine = ErrorBudgetPolicyEngine()
        snap = engine.create_snapshot("api", 99.9, 10.0, 30)
        forecast = engine.forecast_budget(snap, 1.0)
        assert isinstance(forecast, BudgetForecast)
        assert forecast.days_until_exhaustion is not None

    def test_multiple_slos_gate(self):
        engine = ErrorBudgetPolicyEngine()
        s1 = engine.create_snapshot("api", 99.9, 0.0, 30)
        s2 = engine.create_snapshot("web", 99.9, 21.0, 30)
        s3 = engine.create_snapshot("db", 99.9, 40.0, 30)
        # s3 is critical/exhausted => should block
        assert engine.should_allow_release([s1, s2, s3]) is False

    def test_99_percent_slo(self):
        engine = ErrorBudgetPolicyEngine()
        # 1% * 30 * 1440 = 432 min total budget
        snap = engine.create_snapshot("svc", 99.0, 216.0, 30)
        assert snap.budget_remaining_percent == pytest.approx(50.0, abs=1e-4)
        assert snap.state in (BudgetState.HEALTHY, BudgetState.WARNING)

    def test_7_day_window(self):
        engine = ErrorBudgetPolicyEngine()
        # 0.1% * 7 * 1440 = 10.08 min
        snap = engine.create_snapshot("svc", 99.9, 5.04, 7)
        assert snap.budget_remaining_percent == pytest.approx(50.0)

    def test_custom_thresholds(self):
        engine = ErrorBudgetPolicyEngine()
        engine.thresholds = [
            BudgetThreshold(
                state=BudgetState.HEALTHY,
                min_remaining_percent=80.0,
                max_remaining_percent=100.0,
                action=PolicyAction.ALLOW_RELEASES,
                escalation=EscalationLevel.TEAM,
                description="custom healthy",
            ),
            BudgetThreshold(
                state=BudgetState.WARNING,
                min_remaining_percent=0.0,
                max_remaining_percent=80.0,
                action=PolicyAction.FREEZE_RELEASES,
                escalation=EscalationLevel.VP,
                description="custom warning",
            ),
        ]
        snap = _snap(state=BudgetState.WARNING, remaining=50.0)
        d = engine.evaluate_policy(snap)
        assert d.action == PolicyAction.FREEZE_RELEASES

    def test_snapshot_with_exact_boundary_20(self):
        engine = ErrorBudgetPolicyEngine()
        # 99.0 SLO, 30-day => budget 432 min, consume 80% => remaining 20%
        snap = engine.create_snapshot("svc", 99.0, 432.0 * 0.80, 30)
        assert snap.state in (BudgetState.WARNING, BudgetState.CRITICAL)

    def test_snapshot_with_exact_boundary_1(self):
        engine = ErrorBudgetPolicyEngine()
        snap = engine.create_snapshot("svc", 99.0, 432.0 * 0.99, 30)
        assert snap.state in (BudgetState.CRITICAL, BudgetState.EXHAUSTED)

    def test_forecast_with_very_low_error_rate(self):
        engine = ErrorBudgetPolicyEngine()
        snap = _snap(total=43.2, consumed=0.0, remaining=100.0, window=30)
        f = engine.forecast_budget(snap, 0.001)
        assert f.days_until_exhaustion is not None
        assert f.days_until_exhaustion > 1000

    def test_report_with_all_states(self):
        engine = ErrorBudgetPolicyEngine()
        snaps = [
            _snap(name="a", state=BudgetState.HEALTHY, remaining=80.0),
            _snap(name="b", state=BudgetState.WARNING, remaining=35.0),
            _snap(name="c", state=BudgetState.CRITICAL, remaining=5.0),
            _snap(name="d", state=BudgetState.EXHAUSTED, remaining=0.0),
        ]
        report = engine.generate_report(snaps)
        assert report.overall_action == PolicyAction.EMERGENCY_ONLY
        assert len(report.decisions) == 4
