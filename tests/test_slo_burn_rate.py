"""Tests for SLO Burn Rate Alert Simulator.

Covers all models, enum values, engine methods, default windows, various
error-rate patterns (steady, spike, gradual degradation, intermittent, zero
error, 100% error), edge cases, and report generation.
"""

from __future__ import annotations

import pytest

from faultray.simulator.slo_burn_rate import (
    AlertSeverity,
    AlertSimulationResult,
    AlertSimulationScenario,
    BurnRateAlert,
    BurnRateWindow,
    ErrorBudgetStatus,
    SLOBurnRateEngine,
    SLOBurnRateReport,
)


# =========================================================================
# Enum tests
# =========================================================================


class TestAlertSeverity:
    """AlertSeverity enum."""

    def test_page_value(self) -> None:
        assert AlertSeverity.PAGE.value == "page"

    def test_ticket_value(self) -> None:
        assert AlertSeverity.TICKET.value == "ticket"

    def test_log_value(self) -> None:
        assert AlertSeverity.LOG.value == "log"

    def test_is_str_enum(self) -> None:
        assert isinstance(AlertSeverity.PAGE, str)

    def test_all_members(self) -> None:
        assert set(AlertSeverity) == {
            AlertSeverity.PAGE,
            AlertSeverity.TICKET,
            AlertSeverity.LOG,
        }


# =========================================================================
# Pydantic model tests
# =========================================================================


class TestBurnRateWindow:
    """BurnRateWindow model."""

    def test_create(self) -> None:
        w = BurnRateWindow(
            window_minutes=60,
            burn_rate_threshold=14.4,
            long_window_minutes=60,
            short_window_minutes=5,
            severity=AlertSeverity.PAGE,
        )
        assert w.window_minutes == 60
        assert w.burn_rate_threshold == 14.4
        assert w.long_window_minutes == 60
        assert w.short_window_minutes == 5
        assert w.severity == AlertSeverity.PAGE

    def test_severity_string(self) -> None:
        w = BurnRateWindow(
            window_minutes=360,
            burn_rate_threshold=6.0,
            long_window_minutes=360,
            short_window_minutes=30,
            severity=AlertSeverity.TICKET,
        )
        assert w.severity == AlertSeverity.TICKET

    def test_model_dump(self) -> None:
        w = BurnRateWindow(
            window_minutes=60,
            burn_rate_threshold=14.4,
            long_window_minutes=60,
            short_window_minutes=5,
            severity=AlertSeverity.PAGE,
        )
        d = w.model_dump()
        assert d["window_minutes"] == 60
        assert d["severity"] == "page"


class TestErrorBudgetStatus:
    """ErrorBudgetStatus model."""

    def test_create(self) -> None:
        s = ErrorBudgetStatus(
            slo_target=99.9,
            error_budget_total=43.2,
            error_budget_consumed=10.0,
            error_budget_remaining_percent=76.85,
            burn_rate_1h=2.0,
            burn_rate_6h=1.5,
            burn_rate_24h=1.0,
            burn_rate_72h=0.8,
            projected_exhaustion_hours=100.0,
        )
        assert s.slo_target == 99.9
        assert s.projected_exhaustion_hours == 100.0

    def test_projected_none(self) -> None:
        s = ErrorBudgetStatus(
            slo_target=99.9,
            error_budget_total=43.2,
            error_budget_consumed=0.0,
            error_budget_remaining_percent=100.0,
            burn_rate_1h=0.0,
            burn_rate_6h=0.0,
            burn_rate_24h=0.0,
            burn_rate_72h=0.0,
            projected_exhaustion_hours=None,
        )
        assert s.projected_exhaustion_hours is None


class TestBurnRateAlert:
    """BurnRateAlert model."""

    def test_triggered_alert(self) -> None:
        w = BurnRateWindow(
            window_minutes=60,
            burn_rate_threshold=14.4,
            long_window_minutes=60,
            short_window_minutes=5,
            severity=AlertSeverity.PAGE,
        )
        a = BurnRateAlert(
            window=w,
            current_burn_rate=15.0,
            triggered=True,
            severity=AlertSeverity.PAGE,
            time_to_exhaustion_hours=2.5,
            message="ALERT",
        )
        assert a.triggered is True
        assert a.severity == AlertSeverity.PAGE

    def test_non_triggered_alert(self) -> None:
        w = BurnRateWindow(
            window_minutes=60,
            burn_rate_threshold=14.4,
            long_window_minutes=60,
            short_window_minutes=5,
            severity=AlertSeverity.PAGE,
        )
        a = BurnRateAlert(
            window=w,
            current_burn_rate=1.0,
            triggered=False,
            severity=AlertSeverity.PAGE,
            time_to_exhaustion_hours=None,
            message="OK",
        )
        assert a.triggered is False


class TestAlertSimulationScenario:
    """AlertSimulationScenario model."""

    def test_create(self) -> None:
        s = AlertSimulationScenario(
            scenario_name="spike",
            error_rate_pattern=[0.01, 0.01, 5.0],
            slo_target=99.9,
            window_days=30,
        )
        assert s.scenario_name == "spike"
        assert len(s.error_rate_pattern) == 3

    def test_empty_pattern(self) -> None:
        s = AlertSimulationScenario(
            scenario_name="empty",
            error_rate_pattern=[],
            slo_target=99.9,
            window_days=30,
        )
        assert s.error_rate_pattern == []


class TestAlertSimulationResult:
    """AlertSimulationResult model."""

    def test_create(self) -> None:
        bs = ErrorBudgetStatus(
            slo_target=99.9,
            error_budget_total=43.2,
            error_budget_consumed=0,
            error_budget_remaining_percent=100,
            burn_rate_1h=0,
            burn_rate_6h=0,
            burn_rate_24h=0,
            burn_rate_72h=0,
            projected_exhaustion_hours=None,
        )
        r = AlertSimulationResult(
            scenario_name="test",
            alerts_triggered=[],
            detection_time_minutes=None,
            false_positives=0,
            missed_violations=0,
            budget_status=bs,
        )
        assert r.scenario_name == "test"
        assert r.detection_time_minutes is None


class TestSLOBurnRateReport:
    """SLOBurnRateReport model."""

    def test_create(self) -> None:
        r = SLOBurnRateReport(
            scenarios_tested=2,
            results=[],
            fastest_detection_minutes=60.0,
            slowest_detection_minutes=120.0,
            alert_effectiveness_score=100.0,
            recommendations=["ok"],
        )
        assert r.scenarios_tested == 2
        assert r.alert_effectiveness_score == 100.0


# =========================================================================
# Engine construction
# =========================================================================


class TestEngineInit:
    """SLOBurnRateEngine.__init__."""

    def test_defaults(self) -> None:
        e = SLOBurnRateEngine()
        assert e.slo_target == 99.9
        assert e.window_days == 30
        assert e.allowed_error_rate == pytest.approx(0.001)

    def test_custom_slo(self) -> None:
        e = SLOBurnRateEngine(slo_target=99.0, window_days=7)
        assert e.slo_target == 99.0
        assert e.window_days == 7
        assert e.allowed_error_rate == pytest.approx(0.01)

    def test_four_default_windows(self) -> None:
        e = SLOBurnRateEngine()
        assert len(e.windows) == 4

    def test_window_1_page_14_4x(self) -> None:
        e = SLOBurnRateEngine()
        w = e.windows[0]
        assert w.burn_rate_threshold == 14.4
        assert w.long_window_minutes == 60
        assert w.short_window_minutes == 5
        assert w.severity == AlertSeverity.PAGE

    def test_window_2_page_6x(self) -> None:
        e = SLOBurnRateEngine()
        w = e.windows[1]
        assert w.burn_rate_threshold == 6.0
        assert w.long_window_minutes == 360
        assert w.short_window_minutes == 30
        assert w.severity == AlertSeverity.PAGE

    def test_window_3_ticket_3x(self) -> None:
        e = SLOBurnRateEngine()
        w = e.windows[2]
        assert w.burn_rate_threshold == 3.0
        assert w.long_window_minutes == 1440
        assert w.short_window_minutes == 120
        assert w.severity == AlertSeverity.TICKET

    def test_window_4_log_1x(self) -> None:
        e = SLOBurnRateEngine()
        w = e.windows[3]
        assert w.burn_rate_threshold == 1.0
        assert w.long_window_minutes == 4320
        assert w.short_window_minutes == 360
        assert w.severity == AlertSeverity.LOG

    def test_100_percent_slo(self) -> None:
        e = SLOBurnRateEngine(slo_target=100.0)
        assert e.allowed_error_rate == 0.0

    def test_slo_95(self) -> None:
        e = SLOBurnRateEngine(slo_target=95.0)
        assert e.allowed_error_rate == pytest.approx(0.05)


# =========================================================================
# calculate_error_budget
# =========================================================================


class TestCalculateErrorBudget:
    """SLOBurnRateEngine.calculate_error_budget."""

    def test_default_budget(self) -> None:
        e = SLOBurnRateEngine()
        # 0.001 * 30 * 24 * 60 = 43.2
        assert e.calculate_error_budget() == pytest.approx(43.2, rel=1e-3)

    def test_99_slo_30d(self) -> None:
        e = SLOBurnRateEngine(slo_target=99.0, window_days=30)
        assert e.calculate_error_budget() == pytest.approx(432.0, rel=1e-3)

    def test_7_day_window(self) -> None:
        e = SLOBurnRateEngine(slo_target=99.9, window_days=7)
        expected = 0.001 * 7 * 24 * 60  # 10.08
        assert e.calculate_error_budget() == pytest.approx(expected, rel=1e-3)

    def test_100_percent_slo_zero_budget(self) -> None:
        e = SLOBurnRateEngine(slo_target=100.0)
        assert e.calculate_error_budget() == pytest.approx(0.0)

    def test_1_day_window(self) -> None:
        e = SLOBurnRateEngine(slo_target=99.9, window_days=1)
        expected = 0.001 * 1 * 24 * 60  # 1.44
        assert e.calculate_error_budget() == pytest.approx(expected, rel=1e-3)


# =========================================================================
# calculate_burn_rate
# =========================================================================


class TestCalculateBurnRate:
    """SLOBurnRateEngine.calculate_burn_rate."""

    def test_zero_error(self) -> None:
        e = SLOBurnRateEngine()
        assert e.calculate_burn_rate([0.0, 0.0, 0.0], 1) == 0.0

    def test_at_allowed_rate(self) -> None:
        # 0.1% error = allowed rate for 99.9% SLO → burn rate 1.0
        e = SLOBurnRateEngine()
        assert e.calculate_burn_rate([0.1], 1) == pytest.approx(1.0)

    def test_14_4x_burn_rate(self) -> None:
        # 1.44% error rate / 0.1% allowed = 14.4x
        e = SLOBurnRateEngine()
        assert e.calculate_burn_rate([1.44], 1) == pytest.approx(14.4)

    def test_empty_list(self) -> None:
        e = SLOBurnRateEngine()
        assert e.calculate_burn_rate([], 1) == 0.0

    def test_zero_window(self) -> None:
        e = SLOBurnRateEngine()
        assert e.calculate_burn_rate([1.0], 0) == 0.0

    def test_negative_window(self) -> None:
        e = SLOBurnRateEngine()
        assert e.calculate_burn_rate([1.0], -1) == 0.0

    def test_window_larger_than_data(self) -> None:
        # Only 2 data points, window is 6 hours
        e = SLOBurnRateEngine()
        br = e.calculate_burn_rate([0.2, 0.2], 6)
        # avg = 0.2% / 100 = 0.002. br = 0.002 / 0.001 = 2.0
        assert br == pytest.approx(2.0)

    def test_uses_most_recent_data(self) -> None:
        e = SLOBurnRateEngine()
        # 10 hours of data, 1h window → should use only the last hour
        data = [0.0] * 9 + [1.0]
        br = e.calculate_burn_rate(data, 1)
        assert br == pytest.approx(10.0)

    def test_6h_window(self) -> None:
        e = SLOBurnRateEngine()
        data = [0.6] * 6  # avg 0.6%
        br = e.calculate_burn_rate(data, 6)
        assert br == pytest.approx(6.0)

    def test_100_percent_slo_zero_allowed(self) -> None:
        e = SLOBurnRateEngine(slo_target=100.0)
        assert e.calculate_burn_rate([1.0], 1) == 0.0

    def test_high_error_rate(self) -> None:
        e = SLOBurnRateEngine()
        br = e.calculate_burn_rate([10.0], 1)  # 10% error
        assert br == pytest.approx(100.0)

    def test_mixed_rates_6h(self) -> None:
        e = SLOBurnRateEngine()
        data = [0.0, 0.0, 0.0, 0.3, 0.3, 0.3]
        br = e.calculate_burn_rate(data, 6)
        avg = 0.15  # 0.15% avg
        assert br == pytest.approx(avg / 0.1)


# =========================================================================
# evaluate_budget_status
# =========================================================================


class TestEvaluateBudgetStatus:
    """SLOBurnRateEngine.evaluate_budget_status."""

    def test_zero_errors(self) -> None:
        e = SLOBurnRateEngine()
        s = e.evaluate_budget_status([0.0] * 24)
        assert s.error_budget_consumed == 0.0
        assert s.error_budget_remaining_percent == 100.0
        assert s.burn_rate_1h == 0.0
        assert s.projected_exhaustion_hours is None

    def test_full_consumption(self) -> None:
        e = SLOBurnRateEngine(slo_target=99.9, window_days=30)
        # Budget = 43.2 min. To consume it all in 24h at constant rate:
        # each hour consumes rate/100 * 60 min
        # 43.2 = 24 * rate/100 * 60 → rate = 43.2 / (24*0.6) = 3.0%
        data = [3.0] * 24
        s = e.evaluate_budget_status(data)
        assert s.error_budget_consumed == pytest.approx(43.2, rel=1e-2)
        assert s.error_budget_remaining_percent == pytest.approx(0.0, abs=0.1)

    def test_partial_consumption(self) -> None:
        e = SLOBurnRateEngine()
        # 1 hour at 0.1% → consumed = 0.001 * 60 = 0.06 min
        s = e.evaluate_budget_status([0.1])
        assert s.error_budget_consumed == pytest.approx(0.06, rel=1e-2)
        assert s.error_budget_remaining_percent > 99.0

    def test_burn_rates_populated(self) -> None:
        e = SLOBurnRateEngine()
        data = [0.6] * 72
        s = e.evaluate_budget_status(data)
        assert s.burn_rate_1h == pytest.approx(6.0)
        assert s.burn_rate_6h == pytest.approx(6.0)
        assert s.burn_rate_24h == pytest.approx(6.0)
        assert s.burn_rate_72h == pytest.approx(6.0)

    def test_projected_exhaustion(self) -> None:
        e = SLOBurnRateEngine()
        data = [1.44]  # 14.4x burn rate
        s = e.evaluate_budget_status(data)
        assert s.projected_exhaustion_hours is not None
        assert s.projected_exhaustion_hours > 0

    def test_slo_target_in_status(self) -> None:
        e = SLOBurnRateEngine(slo_target=99.5)
        s = e.evaluate_budget_status([0.0])
        assert s.slo_target == 99.5

    def test_budget_total_in_status(self) -> None:
        e = SLOBurnRateEngine()
        s = e.evaluate_budget_status([0.0])
        assert s.error_budget_total == pytest.approx(43.2, rel=1e-3)

    def test_consumed_capped_at_total(self) -> None:
        e = SLOBurnRateEngine()
        # Massive error for many hours → consumed should not exceed total
        data = [100.0] * 100
        s = e.evaluate_budget_status(data)
        assert s.error_budget_consumed <= s.error_budget_total

    def test_remaining_never_negative(self) -> None:
        e = SLOBurnRateEngine()
        data = [100.0] * 100
        s = e.evaluate_budget_status(data)
        assert s.error_budget_remaining_percent >= 0.0


# =========================================================================
# check_alerts
# =========================================================================


class TestCheckAlerts:
    """SLOBurnRateEngine.check_alerts."""

    def test_returns_four_alerts(self) -> None:
        e = SLOBurnRateEngine()
        alerts = e.check_alerts([0.0])
        assert len(alerts) == 4

    def test_no_triggers_on_zero_error(self) -> None:
        e = SLOBurnRateEngine()
        alerts = e.check_alerts([0.0] * 24)
        assert all(not a.triggered for a in alerts)

    def test_all_ok_messages_on_zero(self) -> None:
        e = SLOBurnRateEngine()
        alerts = e.check_alerts([0.0])
        assert all("OK" in a.message for a in alerts)

    def test_14_4x_triggers_page(self) -> None:
        e = SLOBurnRateEngine()
        # 1.44% for 1 hour → 14.4x burn rate
        alerts = e.check_alerts([1.44])
        page_alert = alerts[0]
        assert page_alert.triggered is True
        assert page_alert.severity == AlertSeverity.PAGE
        assert "ALERT" in page_alert.message

    def test_6x_triggers_second_page(self) -> None:
        e = SLOBurnRateEngine()
        # 0.6% for 6 hours → 6x burn rate (sustained)
        data = [0.6] * 6
        alerts = e.check_alerts(data)
        second = alerts[1]
        assert second.triggered is True
        assert second.severity == AlertSeverity.PAGE

    def test_3x_triggers_ticket(self) -> None:
        e = SLOBurnRateEngine()
        # 0.3% for 24 hours → 3x burn rate
        data = [0.3] * 24
        alerts = e.check_alerts(data)
        ticket = alerts[2]
        assert ticket.triggered is True
        assert ticket.severity == AlertSeverity.TICKET

    def test_1x_triggers_log(self) -> None:
        e = SLOBurnRateEngine()
        # 0.1% for 72 hours → 1x burn rate
        data = [0.1] * 72
        alerts = e.check_alerts(data)
        log_alert = alerts[3]
        assert log_alert.triggered is True
        assert log_alert.severity == AlertSeverity.LOG

    def test_below_threshold_no_trigger(self) -> None:
        e = SLOBurnRateEngine()
        # 0.05% → 0.5x burn rate — below all thresholds
        data = [0.05] * 72
        alerts = e.check_alerts(data)
        assert all(not a.triggered for a in alerts)

    def test_time_to_exhaustion_populated(self) -> None:
        e = SLOBurnRateEngine()
        alerts = e.check_alerts([1.44])
        assert alerts[0].time_to_exhaustion_hours is not None
        assert alerts[0].time_to_exhaustion_hours > 0

    def test_time_to_exhaustion_none_on_zero(self) -> None:
        e = SLOBurnRateEngine()
        alerts = e.check_alerts([0.0])
        assert alerts[0].time_to_exhaustion_hours is None

    def test_alert_message_contains_threshold(self) -> None:
        e = SLOBurnRateEngine()
        alerts = e.check_alerts([1.44])
        assert "14.4x" in alerts[0].message

    def test_alert_window_attached(self) -> None:
        e = SLOBurnRateEngine()
        alerts = e.check_alerts([0.0])
        assert alerts[0].window.window_minutes == 60
        assert alerts[1].window.window_minutes == 360

    def test_massive_error_triggers_all(self) -> None:
        e = SLOBurnRateEngine()
        data = [50.0] * 72  # 50% error rate → 500x burn rate
        alerts = e.check_alerts(data)
        assert all(a.triggered for a in alerts)

    def test_current_burn_rate_value(self) -> None:
        e = SLOBurnRateEngine()
        alerts = e.check_alerts([1.44])
        assert alerts[0].current_burn_rate == pytest.approx(14.4)


# =========================================================================
# simulate_scenario
# =========================================================================


class TestSimulateScenario:
    """SLOBurnRateEngine.simulate_scenario."""

    def test_no_errors_no_detection(self) -> None:
        e = SLOBurnRateEngine()
        scenario = AlertSimulationScenario(
            scenario_name="healthy",
            error_rate_pattern=[0.0] * 24,
            slo_target=99.9,
            window_days=30,
        )
        r = e.simulate_scenario(scenario)
        assert r.detection_time_minutes is None
        assert r.alerts_triggered == []
        assert r.missed_violations == 0

    def test_spike_detected(self) -> None:
        e = SLOBurnRateEngine()
        scenario = AlertSimulationScenario(
            scenario_name="spike",
            error_rate_pattern=[0.0] * 3 + [5.0] * 3,
            slo_target=99.9,
            window_days=30,
        )
        r = e.simulate_scenario(scenario)
        assert r.detection_time_minutes is not None
        assert len(r.alerts_triggered) > 0
        assert r.scenario_name == "spike"

    def test_gradual_degradation(self) -> None:
        e = SLOBurnRateEngine()
        # Gradually increase error rate from 0 to 2%
        pattern = [i * 0.1 for i in range(21)]
        scenario = AlertSimulationScenario(
            scenario_name="gradual",
            error_rate_pattern=pattern,
            slo_target=99.9,
            window_days=30,
        )
        r = e.simulate_scenario(scenario)
        assert r.scenario_name == "gradual"
        # High error rates at the end should trigger something
        assert r.detection_time_minutes is not None

    def test_intermittent_errors(self) -> None:
        e = SLOBurnRateEngine()
        # Alternating 0% and 2%
        pattern = [0.0, 2.0] * 12
        scenario = AlertSimulationScenario(
            scenario_name="intermittent",
            error_rate_pattern=pattern,
            slo_target=99.9,
            window_days=30,
        )
        r = e.simulate_scenario(scenario)
        assert r.scenario_name == "intermittent"

    def test_steady_high_error(self) -> None:
        e = SLOBurnRateEngine()
        scenario = AlertSimulationScenario(
            scenario_name="steady_high",
            error_rate_pattern=[1.44] * 6,
            slo_target=99.9,
            window_days=30,
        )
        r = e.simulate_scenario(scenario)
        assert r.detection_time_minutes is not None
        assert r.detection_time_minutes == 60.0  # detected at hour 1

    def test_budget_status_populated(self) -> None:
        e = SLOBurnRateEngine()
        scenario = AlertSimulationScenario(
            scenario_name="test",
            error_rate_pattern=[0.5] * 6,
            slo_target=99.9,
            window_days=30,
        )
        r = e.simulate_scenario(scenario)
        assert r.budget_status.slo_target == 99.9
        assert r.budget_status.error_budget_total > 0

    def test_engine_state_restored(self) -> None:
        e = SLOBurnRateEngine(slo_target=99.9, window_days=30)
        scenario = AlertSimulationScenario(
            scenario_name="different",
            error_rate_pattern=[0.1],
            slo_target=99.0,
            window_days=7,
        )
        e.simulate_scenario(scenario)
        assert e.slo_target == 99.9
        assert e.window_days == 30
        assert e.allowed_error_rate == pytest.approx(0.001)

    def test_empty_pattern(self) -> None:
        e = SLOBurnRateEngine()
        scenario = AlertSimulationScenario(
            scenario_name="empty",
            error_rate_pattern=[],
            slo_target=99.9,
            window_days=30,
        )
        r = e.simulate_scenario(scenario)
        assert r.detection_time_minutes is None
        assert r.missed_violations == 0

    def test_false_positives_counted(self) -> None:
        e = SLOBurnRateEngine()
        # Put a few hours of very high error followed by low error
        # The first detection at hour 1 is a real violation, so fp depends
        # on whether any triggered alert has the current rate below allowed.
        scenario = AlertSimulationScenario(
            scenario_name="mixed",
            error_rate_pattern=[5.0, 5.0, 0.0, 0.0],
            slo_target=99.9,
            window_days=30,
        )
        r = e.simulate_scenario(scenario)
        # At hours 3/4 (0.0% error), if the window still triggers, it's fp
        assert isinstance(r.false_positives, int)

    def test_missed_violations_when_not_detected(self) -> None:
        e = SLOBurnRateEngine()
        # Very subtle violation (barely above allowed) for short time
        # 0.11% error rate for 1 hour — above 0.1% allowed but burn rate < 14.4x
        scenario = AlertSimulationScenario(
            scenario_name="subtle",
            error_rate_pattern=[0.11],
            slo_target=99.9,
            window_days=30,
        )
        r = e.simulate_scenario(scenario)
        if r.detection_time_minutes is None:
            assert r.missed_violations > 0

    def test_custom_slo_in_scenario(self) -> None:
        e = SLOBurnRateEngine()
        scenario = AlertSimulationScenario(
            scenario_name="custom_slo",
            error_rate_pattern=[1.0] * 6,
            slo_target=99.0,
            window_days=7,
        )
        r = e.simulate_scenario(scenario)
        assert r.budget_status.slo_target == 99.0

    def test_100_percent_error(self) -> None:
        e = SLOBurnRateEngine()
        scenario = AlertSimulationScenario(
            scenario_name="total_failure",
            error_rate_pattern=[100.0] * 3,
            slo_target=99.9,
            window_days=30,
        )
        r = e.simulate_scenario(scenario)
        assert r.detection_time_minutes is not None
        assert r.detection_time_minutes == 60.0

    def test_scenario_name_propagated(self) -> None:
        e = SLOBurnRateEngine()
        scenario = AlertSimulationScenario(
            scenario_name="my_scenario",
            error_rate_pattern=[0.0],
            slo_target=99.9,
            window_days=30,
        )
        r = e.simulate_scenario(scenario)
        assert r.scenario_name == "my_scenario"


# =========================================================================
# generate_report
# =========================================================================


class TestGenerateReport:
    """SLOBurnRateEngine.generate_report."""

    def _make_scenario(
        self,
        name: str,
        pattern: list[float],
        slo: float = 99.9,
        days: int = 30,
    ) -> AlertSimulationScenario:
        return AlertSimulationScenario(
            scenario_name=name,
            error_rate_pattern=pattern,
            slo_target=slo,
            window_days=days,
        )

    def test_empty_scenarios(self) -> None:
        e = SLOBurnRateEngine()
        report = e.generate_report([])
        assert report.scenarios_tested == 0
        assert report.results == []
        assert report.fastest_detection_minutes == 0.0
        assert report.slowest_detection_minutes is None

    def test_single_healthy_scenario(self) -> None:
        e = SLOBurnRateEngine()
        report = e.generate_report(
            [self._make_scenario("healthy", [0.0] * 24)]
        )
        assert report.scenarios_tested == 1
        assert len(report.results) == 1

    def test_multiple_scenarios(self) -> None:
        e = SLOBurnRateEngine()
        scenarios = [
            self._make_scenario("healthy", [0.0] * 24),
            self._make_scenario("spike", [0.0] * 3 + [5.0] * 3),
            self._make_scenario("steady", [1.44] * 6),
        ]
        report = e.generate_report(scenarios)
        assert report.scenarios_tested == 3
        assert len(report.results) == 3

    def test_fastest_detection(self) -> None:
        e = SLOBurnRateEngine()
        scenarios = [
            self._make_scenario("fast", [10.0] * 6),
            self._make_scenario("slow", [0.0] * 10 + [10.0] * 6),
        ]
        report = e.generate_report(scenarios)
        assert report.fastest_detection_minutes == 60.0

    def test_slowest_detection(self) -> None:
        e = SLOBurnRateEngine()
        scenarios = [
            self._make_scenario("fast", [10.0] * 6),
            self._make_scenario("slow", [0.0] * 10 + [10.0] * 6),
        ]
        report = e.generate_report(scenarios)
        assert report.slowest_detection_minutes is not None
        assert report.slowest_detection_minutes >= report.fastest_detection_minutes

    def test_effectiveness_all_detected(self) -> None:
        e = SLOBurnRateEngine()
        scenarios = [
            self._make_scenario("s1", [5.0] * 6),
            self._make_scenario("s2", [10.0] * 6),
        ]
        report = e.generate_report(scenarios)
        assert report.alert_effectiveness_score == 100.0

    def test_effectiveness_no_violations(self) -> None:
        e = SLOBurnRateEngine()
        scenarios = [
            self._make_scenario("healthy", [0.0] * 24),
        ]
        report = e.generate_report(scenarios)
        # No violations → 100% effectiveness by definition
        assert report.alert_effectiveness_score == 100.0

    def test_recommendations_present(self) -> None:
        e = SLOBurnRateEngine()
        scenarios = [
            self._make_scenario("s1", [5.0] * 6),
        ]
        report = e.generate_report(scenarios)
        assert isinstance(report.recommendations, list)
        assert len(report.recommendations) > 0

    def test_recommendations_false_positives(self) -> None:
        e = SLOBurnRateEngine()
        # High error then zero → alerts lingering would be false positives
        scenarios = [
            self._make_scenario("fp", [10.0, 10.0, 0.0, 0.0, 0.0, 0.0]),
        ]
        report = e.generate_report(scenarios)
        # If false positives detected, recommendation about tightening
        if any(r.false_positives > 0 for r in report.results):
            assert any("false positive" in rec.lower() for rec in report.recommendations)

    def test_recommendations_slow_detection(self) -> None:
        e = SLOBurnRateEngine()
        # Error starts late, so detection_time > 360 minutes
        scenarios = [
            self._make_scenario("late", [0.0] * 8 + [5.0] * 3),
        ]
        report = e.generate_report(scenarios)
        if report.slowest_detection_minutes and report.slowest_detection_minutes > 360:
            assert any("faster" in rec.lower() for rec in report.recommendations)

    def test_recommendations_healthy(self) -> None:
        e = SLOBurnRateEngine()
        scenarios = [
            self._make_scenario("ok", [0.0] * 24),
        ]
        report = e.generate_report(scenarios)
        assert any("healthy" in rec.lower() for rec in report.recommendations)

    def test_report_model_type(self) -> None:
        e = SLOBurnRateEngine()
        report = e.generate_report([])
        assert isinstance(report, SLOBurnRateReport)

    def test_results_contain_correct_names(self) -> None:
        e = SLOBurnRateEngine()
        scenarios = [
            self._make_scenario("alpha", [0.0] * 3),
            self._make_scenario("beta", [1.0] * 3),
        ]
        report = e.generate_report(scenarios)
        names = [r.scenario_name for r in report.results]
        assert names == ["alpha", "beta"]


# =========================================================================
# Edge cases
# =========================================================================


class TestEdgeCases:
    """Various edge cases and boundary conditions."""

    def test_single_data_point(self) -> None:
        e = SLOBurnRateEngine()
        alerts = e.check_alerts([0.5])
        assert len(alerts) == 4

    def test_very_small_error_rate(self) -> None:
        e = SLOBurnRateEngine()
        br = e.calculate_burn_rate([0.001], 1)
        assert br == pytest.approx(0.01)

    def test_very_large_pattern(self) -> None:
        e = SLOBurnRateEngine()
        data = [0.05] * 720  # 30 days of hourly data
        alerts = e.check_alerts(data)
        assert len(alerts) == 4

    def test_windows_are_copies(self) -> None:
        # Modifying engine windows should not affect other engines
        e1 = SLOBurnRateEngine()
        e2 = SLOBurnRateEngine()
        e1.windows.append(
            BurnRateWindow(
                window_minutes=120,
                burn_rate_threshold=10.0,
                long_window_minutes=120,
                short_window_minutes=10,
                severity=AlertSeverity.PAGE,
            )
        )
        assert len(e1.windows) == 5
        assert len(e2.windows) == 4

    def test_budget_status_with_single_point(self) -> None:
        e = SLOBurnRateEngine()
        s = e.evaluate_budget_status([0.5])
        assert s.burn_rate_1h > 0

    def test_scenario_restores_after_exception_free(self) -> None:
        # Ensure engine state is restored even if scenario has weird data
        e = SLOBurnRateEngine(slo_target=99.99, window_days=14)
        scenario = AlertSimulationScenario(
            scenario_name="weird",
            error_rate_pattern=[100.0],
            slo_target=99.0,
            window_days=1,
        )
        e.simulate_scenario(scenario)
        assert e.slo_target == 99.99
        assert e.window_days == 14

    def test_alert_severity_matches_window(self) -> None:
        e = SLOBurnRateEngine()
        alerts = e.check_alerts([50.0] * 72)
        for alert in alerts:
            assert alert.severity == alert.window.severity

    def test_multiple_simulations_independent(self) -> None:
        e = SLOBurnRateEngine()
        s1 = AlertSimulationScenario(
            scenario_name="s1",
            error_rate_pattern=[5.0] * 6,
            slo_target=99.9,
            window_days=30,
        )
        s2 = AlertSimulationScenario(
            scenario_name="s2",
            error_rate_pattern=[0.0] * 6,
            slo_target=99.9,
            window_days=30,
        )
        r1 = e.simulate_scenario(s1)
        r2 = e.simulate_scenario(s2)
        assert r1.detection_time_minutes is not None
        assert r2.detection_time_minutes is None

    def test_custom_window_detection(self) -> None:
        e = SLOBurnRateEngine()
        # Add a very sensitive custom window
        e.windows.append(
            BurnRateWindow(
                window_minutes=30,
                burn_rate_threshold=0.5,
                long_window_minutes=30,
                short_window_minutes=5,
                severity=AlertSeverity.LOG,
            )
        )
        alerts = e.check_alerts([0.08] * 6)
        assert len(alerts) == 5

    def test_burn_rate_with_99_slo(self) -> None:
        e = SLOBurnRateEngine(slo_target=99.0)
        # allowed error rate = 1%. 1% actual = 1x burn rate
        br = e.calculate_burn_rate([1.0], 1)
        assert br == pytest.approx(1.0)

    def test_burn_rate_with_95_slo(self) -> None:
        e = SLOBurnRateEngine(slo_target=95.0)
        # allowed = 5%. 10% actual = 2x
        br = e.calculate_burn_rate([10.0], 1)
        assert br == pytest.approx(2.0)

    def test_report_budget_nearly_exhausted_recommendation(self) -> None:
        e = SLOBurnRateEngine()
        # Scenario that consumes most of the budget
        # Budget = 43.2 min. Consume ~38 min → ~12% remaining
        # 38 min / (hours * 0.6) → use high rate for enough hours
        # 10 hours at 0.633% = 10 * 0.00633 * 60 = 3.8 min consumed (too low)
        # 10 hours at 6.0% = 10 * 0.06 * 60 = 36 min consumed → ~16.7% remaining
        scenario = AlertSimulationScenario(
            scenario_name="nearly_exhausted",
            error_rate_pattern=[6.0] * 11,
            slo_target=99.9,
            window_days=30,
        )
        report = e.generate_report([scenario])
        status = report.results[0].budget_status
        if 0 < status.error_budget_remaining_percent < 20:
            assert any(
                "freeze" in rec.lower() for rec in report.recommendations
            )


# =========================================================================
# Pattern-specific tests
# =========================================================================


class TestErrorPatterns:
    """Specific error rate patterns."""

    def test_spike_and_recovery(self) -> None:
        e = SLOBurnRateEngine()
        # Normal → spike → recovery
        pattern = [0.01] * 5 + [10.0] * 2 + [0.01] * 5
        alerts = e.check_alerts(pattern)
        # At least one should be triggered from the recent high rates
        # (last 5 hours are 0.01, but 6h window includes the spike)
        triggered = [a for a in alerts if a.triggered]
        # The 1h window should NOT trigger (last hour is 0.01)
        page_1h = alerts[0]
        assert page_1h.triggered is False

    def test_slow_burn(self) -> None:
        e = SLOBurnRateEngine()
        # Slightly above allowed rate for a long time
        pattern = [0.12] * 72  # 1.2x burn rate
        alerts = e.check_alerts(pattern)
        # Should trigger the LOG window (1x threshold)
        log_alert = alerts[3]
        assert log_alert.triggered is True
        # Should NOT trigger PAGE windows (14.4x and 6x)
        assert alerts[0].triggered is False
        assert alerts[1].triggered is False

    def test_ramp_up(self) -> None:
        e = SLOBurnRateEngine()
        # Error rate increasing linearly
        pattern = [i * 0.5 for i in range(25)]  # 0 to 12%
        status = e.evaluate_budget_status(pattern)
        assert status.burn_rate_1h > status.burn_rate_24h

    def test_all_zero(self) -> None:
        e = SLOBurnRateEngine()
        pattern = [0.0] * 100
        status = e.evaluate_budget_status(pattern)
        assert status.error_budget_consumed == 0.0
        assert status.burn_rate_1h == 0.0
        assert status.projected_exhaustion_hours is None

    def test_constant_at_threshold(self) -> None:
        e = SLOBurnRateEngine()
        # Exactly at allowed error rate → 1x burn rate
        pattern = [0.1] * 72
        alerts = e.check_alerts(pattern)
        log_alert = alerts[3]
        assert log_alert.triggered is True  # 1.0 >= 1.0

    def test_very_short_spike(self) -> None:
        e = SLOBurnRateEngine()
        # Single hour of 50% error in a sea of zeros
        pattern = [0.0] * 23 + [50.0]
        alerts = e.check_alerts(pattern)
        # 1h window should trigger (burn rate on last hour is 500x)
        assert alerts[0].triggered is True

    def test_oscillating_pattern(self) -> None:
        e = SLOBurnRateEngine()
        # High-low oscillation
        pattern = [2.0, 0.0] * 36
        status = e.evaluate_budget_status(pattern)
        # Average should be ~1%, burn rate ~10x
        assert status.burn_rate_72h == pytest.approx(10.0, rel=0.1)


# =========================================================================
# Alert message content tests
# =========================================================================


class TestAlertMessages:
    """Alert message formatting."""

    def test_triggered_message_format(self) -> None:
        e = SLOBurnRateEngine()
        alerts = e.check_alerts([1.44])
        msg = alerts[0].message
        assert "ALERT" in msg
        assert "PAGE" in msg
        assert "60min" in msg

    def test_ok_message_format(self) -> None:
        e = SLOBurnRateEngine()
        alerts = e.check_alerts([0.0])
        msg = alerts[0].message
        assert "OK" in msg
        assert "60min" in msg

    def test_ticket_message(self) -> None:
        e = SLOBurnRateEngine()
        data = [0.3] * 24
        alerts = e.check_alerts(data)
        ticket = alerts[2]
        if ticket.triggered:
            assert "TICKET" in ticket.message

    def test_log_message(self) -> None:
        e = SLOBurnRateEngine()
        data = [0.1] * 72
        alerts = e.check_alerts(data)
        log = alerts[3]
        if log.triggered:
            assert "LOG" in log.message


# =========================================================================
# Multi-window interaction tests
# =========================================================================


class TestMultiWindowInteraction:
    """Test interactions between multiple burn rate windows."""

    def test_high_error_triggers_multiple_windows(self) -> None:
        e = SLOBurnRateEngine()
        # Very high sustained error → all windows trigger
        data = [10.0] * 72
        alerts = e.check_alerts(data)
        triggered = [a for a in alerts if a.triggered]
        assert len(triggered) == 4

    def test_moderate_error_selective_trigger(self) -> None:
        e = SLOBurnRateEngine()
        # 0.3% → 3x burn rate → should trigger ticket/log but not page
        data = [0.3] * 72
        alerts = e.check_alerts(data)
        assert alerts[0].triggered is False  # 14.4x threshold
        assert alerts[1].triggered is False  # 6x threshold
        assert alerts[2].triggered is True   # 3x threshold
        assert alerts[3].triggered is True   # 1x threshold

    def test_page_requires_both_windows(self) -> None:
        # Short window check must also exceed threshold
        e = SLOBurnRateEngine()
        # Long window (1h) sees 14.4x but short window (5min=1h here) also must
        # With our implementation both use the same hourly data
        alerts = e.check_alerts([1.44])
        assert alerts[0].triggered is True

    def test_report_detection_order(self) -> None:
        e = SLOBurnRateEngine()
        s1 = AlertSimulationScenario(
            scenario_name="fast_detect",
            error_rate_pattern=[50.0] * 2,
            slo_target=99.9,
            window_days=30,
        )
        s2 = AlertSimulationScenario(
            scenario_name="slow_detect",
            error_rate_pattern=[0.0] * 5 + [50.0] * 2,
            slo_target=99.9,
            window_days=30,
        )
        report = e.generate_report([s1, s2])
        assert report.fastest_detection_minutes <= (
            report.slowest_detection_minutes or float("inf")
        )


# =========================================================================
# Regression / specific value checks
# =========================================================================


class TestSpecificValues:
    """Verify specific calculated values."""

    def test_budget_99_9_30d(self) -> None:
        e = SLOBurnRateEngine(slo_target=99.9, window_days=30)
        assert e.calculate_error_budget() == pytest.approx(43.2, rel=1e-3)

    def test_budget_99_99_30d(self) -> None:
        e = SLOBurnRateEngine(slo_target=99.99, window_days=30)
        assert e.calculate_error_budget() == pytest.approx(4.32, rel=1e-2)

    def test_budget_99_0_30d(self) -> None:
        e = SLOBurnRateEngine(slo_target=99.0, window_days=30)
        assert e.calculate_error_budget() == pytest.approx(432.0, rel=1e-3)

    def test_burn_rate_exact_6x(self) -> None:
        e = SLOBurnRateEngine()
        br = e.calculate_burn_rate([0.6], 1)
        assert br == pytest.approx(6.0)

    def test_burn_rate_exact_3x(self) -> None:
        e = SLOBurnRateEngine()
        br = e.calculate_burn_rate([0.3], 1)
        assert br == pytest.approx(3.0)

    def test_burn_rate_exact_1x(self) -> None:
        e = SLOBurnRateEngine()
        br = e.calculate_burn_rate([0.1], 1)
        assert br == pytest.approx(1.0)

    def test_time_to_exhaustion_at_14_4x(self) -> None:
        e = SLOBurnRateEngine()
        alerts = e.check_alerts([1.44])
        tte = alerts[0].time_to_exhaustion_hours
        assert tte is not None
        # budget=43.2min, consumed_per_hour=14.4*0.001*60=0.864min/h
        # tte = 43.2/0.864 = 50h
        assert tte == pytest.approx(50.0, rel=1e-2)

    def test_allowed_error_rate_999(self) -> None:
        e = SLOBurnRateEngine(slo_target=99.9)
        assert e.allowed_error_rate == pytest.approx(0.001)

    def test_allowed_error_rate_990(self) -> None:
        e = SLOBurnRateEngine(slo_target=99.0)
        assert e.allowed_error_rate == pytest.approx(0.01)


# =========================================================================
# Missed-violation and recommendation coverage
# =========================================================================


class TestMissedViolations:
    """Ensure missed-violation counting and recommendations are covered."""

    def test_missed_violations_with_high_thresholds(self) -> None:
        """A real violation exists but no window threshold is crossed."""
        e = SLOBurnRateEngine()
        # Replace all windows with very high thresholds so nothing triggers
        e.windows = [
            BurnRateWindow(
                window_minutes=60,
                burn_rate_threshold=1000.0,
                long_window_minutes=60,
                short_window_minutes=5,
                severity=AlertSeverity.PAGE,
            ),
        ]
        # 0.2% error rate at 99.9% SLO → burn rate = 2x, but threshold is 1000x
        scenario = AlertSimulationScenario(
            scenario_name="missed",
            error_rate_pattern=[0.2] * 3,
            slo_target=99.9,
            window_days=30,
        )
        r = e.simulate_scenario(scenario)
        assert r.detection_time_minutes is None
        assert r.missed_violations == 3

    def test_missed_violations_recommendation_in_report(self) -> None:
        """Report should recommend adding lower burn-rate windows."""
        e = SLOBurnRateEngine()
        e.windows = [
            BurnRateWindow(
                window_minutes=60,
                burn_rate_threshold=1000.0,
                long_window_minutes=60,
                short_window_minutes=5,
                severity=AlertSeverity.PAGE,
            ),
        ]
        scenario = AlertSimulationScenario(
            scenario_name="missed_rec",
            error_rate_pattern=[0.5] * 3,
            slo_target=99.9,
            window_days=30,
        )
        report = e.generate_report([scenario])
        assert any(r.missed_violations > 0 for r in report.results)
        assert any(
            "lower burn-rate" in rec.lower()
            for rec in report.recommendations
        )

    def test_missed_violations_zero_when_no_violation(self) -> None:
        """No real violations means missed count should stay zero."""
        e = SLOBurnRateEngine()
        scenario = AlertSimulationScenario(
            scenario_name="clean",
            error_rate_pattern=[0.0] * 10,
            slo_target=99.9,
            window_days=30,
        )
        r = e.simulate_scenario(scenario)
        assert r.missed_violations == 0

    def test_effectiveness_with_missed(self) -> None:
        """Effectiveness score drops when violations are missed."""
        e = SLOBurnRateEngine()
        e.windows = [
            BurnRateWindow(
                window_minutes=60,
                burn_rate_threshold=1000.0,
                long_window_minutes=60,
                short_window_minutes=5,
                severity=AlertSeverity.PAGE,
            ),
        ]
        scenario = AlertSimulationScenario(
            scenario_name="eff_miss",
            error_rate_pattern=[1.0] * 3,
            slo_target=99.9,
            window_days=30,
        )
        report = e.generate_report([scenario])
        assert report.alert_effectiveness_score == 0.0
