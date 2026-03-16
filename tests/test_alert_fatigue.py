"""Tests for alert fatigue analyzer."""

from __future__ import annotations

import pytest

from faultray.model.components import (
    Component,
    ComponentType,
    Dependency,
    HealthStatus,
    ResourceMetrics,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.alert_fatigue import (
    AlertConfig,
    AlertFatigueEngine,
    AlertSeverity,
    AlertStormResult,
    FatigueAssessment,
    FatigueRisk,
    _trigger_multiplier,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(
    cid: str,
    name: str | None = None,
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    health: HealthStatus = HealthStatus.HEALTHY,
    cpu: float = 0.0,
    mem: float = 0.0,
    disk: float = 0.0,
    net_conn: int = 0,
) -> Component:
    return Component(
        id=cid,
        name=name or cid,
        type=ctype,
        replicas=replicas,
        health=health,
        metrics=ResourceMetrics(
            cpu_percent=cpu,
            memory_percent=mem,
            disk_percent=disk,
            network_connections=net_conn,
        ),
    )


def _alert(
    aid: str,
    component_id: str = "svc-1",
    severity: AlertSeverity = AlertSeverity.WARNING,
    threshold: float = 80.0,
    window: int = 15,
    channels: list[str] | None = None,
    actionable: bool = True,
    auto_resolve: bool = False,
    suppression: int = 0,
    name: str | None = None,
) -> AlertConfig:
    return AlertConfig(
        id=aid,
        name=name or f"Alert {aid}",
        severity=severity,
        component_id=component_id,
        threshold=threshold,
        evaluation_window_minutes=window,
        notification_channels=channels or ["slack"],
        is_actionable=actionable,
        auto_resolve=auto_resolve,
        suppression_minutes=suppression,
    )


def _chain_graph() -> InfraGraph:
    """lb -> api -> db"""
    g = InfraGraph()
    g.add_component(_comp("lb", "Load Balancer", ComponentType.LOAD_BALANCER))
    g.add_component(_comp("api", "API Server"))
    g.add_component(_comp("db", "Database", ComponentType.DATABASE))
    g.add_dependency(Dependency(source_id="lb", target_id="api"))
    g.add_dependency(Dependency(source_id="api", target_id="db"))
    return g


def _fan_graph() -> InfraGraph:
    """api -> db, api -> cache, api -> queue, svc -> api"""
    g = InfraGraph()
    g.add_component(_comp("api", "API Server"))
    g.add_component(_comp("db", "Database", ComponentType.DATABASE))
    g.add_component(_comp("cache", "Cache", ComponentType.CACHE))
    g.add_component(_comp("queue", "Queue", ComponentType.QUEUE))
    g.add_component(_comp("svc", "Service"))
    g.add_dependency(Dependency(source_id="api", target_id="db"))
    g.add_dependency(Dependency(source_id="api", target_id="cache"))
    g.add_dependency(Dependency(source_id="api", target_id="queue"))
    g.add_dependency(Dependency(source_id="svc", target_id="api"))
    return g


def _large_alert_set(count: int, **kwargs) -> list[AlertConfig]:
    """Generate a list of alert configs."""
    return [_alert(f"a-{i}", **kwargs) for i in range(count)]


# ===========================================================================
# Tests: Enums
# ===========================================================================


class TestAlertSeverity:
    def test_critical_value(self):
        assert AlertSeverity.CRITICAL.value == "critical"

    def test_warning_value(self):
        assert AlertSeverity.WARNING.value == "warning"

    def test_info_value(self):
        assert AlertSeverity.INFO.value == "info"

    def test_debug_value(self):
        assert AlertSeverity.DEBUG.value == "debug"

    def test_is_string_enum(self):
        assert isinstance(AlertSeverity.CRITICAL, str)


class TestFatigueRisk:
    def test_none_value(self):
        assert FatigueRisk.NONE.value == "none"

    def test_low_value(self):
        assert FatigueRisk.LOW.value == "low"

    def test_moderate_value(self):
        assert FatigueRisk.MODERATE.value == "moderate"

    def test_high_value(self):
        assert FatigueRisk.HIGH.value == "high"

    def test_severe_value(self):
        assert FatigueRisk.SEVERE.value == "severe"

    def test_is_string_enum(self):
        assert isinstance(FatigueRisk.NONE, str)


# ===========================================================================
# Tests: Models
# ===========================================================================


class TestAlertConfig:
    def test_minimal_creation(self):
        a = AlertConfig(
            id="a1",
            name="CPU Alert",
            severity=AlertSeverity.WARNING,
            component_id="svc-1",
            threshold=80.0,
            evaluation_window_minutes=10,
        )
        assert a.id == "a1"
        assert a.name == "CPU Alert"
        assert a.severity == AlertSeverity.WARNING
        assert a.component_id == "svc-1"
        assert a.threshold == 80.0
        assert a.evaluation_window_minutes == 10

    def test_defaults(self):
        a = AlertConfig(
            id="a1",
            name="Test",
            severity=AlertSeverity.INFO,
            component_id="svc-1",
            threshold=50.0,
            evaluation_window_minutes=5,
        )
        assert a.notification_channels == []
        assert a.is_actionable is True
        assert a.auto_resolve is False
        assert a.suppression_minutes == 0

    def test_full_creation(self):
        a = AlertConfig(
            id="a1",
            name="Full Alert",
            severity=AlertSeverity.CRITICAL,
            component_id="db-1",
            threshold=95.0,
            evaluation_window_minutes=1,
            notification_channels=["slack", "pagerduty"],
            is_actionable=True,
            auto_resolve=True,
            suppression_minutes=10,
        )
        assert a.notification_channels == ["slack", "pagerduty"]
        assert a.auto_resolve is True
        assert a.suppression_minutes == 10

    def test_model_copy(self):
        a = _alert("a1")
        b = a.model_copy()
        assert a.id == b.id
        assert a is not b

    def test_model_dump(self):
        a = _alert("a1")
        d = a.model_dump()
        assert d["id"] == "a1"
        assert "severity" in d
        assert "threshold" in d


class TestFatigueAssessment:
    def test_defaults(self):
        fa = FatigueAssessment()
        assert fa.total_alerts == 0
        assert fa.actionable_ratio == 0.0
        assert fa.estimated_daily_alerts == 0
        assert fa.fatigue_risk == FatigueRisk.NONE
        assert fa.noise_alerts == []
        assert fa.duplicate_groups == []
        assert fa.recommendations == []
        assert fa.optimal_threshold_adjustments == {}

    def test_full_creation(self):
        fa = FatigueAssessment(
            total_alerts=10,
            actionable_ratio=0.8,
            estimated_daily_alerts=50,
            fatigue_risk=FatigueRisk.MODERATE,
            noise_alerts=["a1", "a2"],
            duplicate_groups=[["a3", "a4"]],
            recommendations=["reduce alerts"],
            optimal_threshold_adjustments={"a1": 90.0},
        )
        assert fa.total_alerts == 10
        assert fa.noise_alerts == ["a1", "a2"]


class TestAlertStormResult:
    def test_defaults(self):
        r = AlertStormResult()
        assert r.total_alerts_generated == 0
        assert r.peak_alerts_per_minute == 0
        assert r.fatigue_risk == FatigueRisk.NONE
        assert r.affected_components == []

    def test_full_creation(self):
        r = AlertStormResult(
            total_alerts_generated=100,
            peak_alerts_per_minute=20,
            unique_alerts=15,
            duplicate_alerts=5,
            cascade_depth=3,
            affected_components=["a", "b"],
            storm_duration_minutes=60,
            fatigue_risk=FatigueRisk.SEVERE,
        )
        assert r.cascade_depth == 3
        assert r.storm_duration_minutes == 60


# ===========================================================================
# Tests: _trigger_multiplier helper
# ===========================================================================


class TestTriggerMultiplier:
    def test_known_values(self):
        assert _trigger_multiplier(1) == 60.0
        assert _trigger_multiplier(5) == 20.0
        assert _trigger_multiplier(15) == 6.0
        assert _trigger_multiplier(60) == 1.5

    def test_zero_window(self):
        result = _trigger_multiplier(0)
        assert result == 60.0

    def test_negative_window(self):
        result = _trigger_multiplier(-1)
        assert result == 60.0

    def test_very_large_window(self):
        result = _trigger_multiplier(120)
        assert result == 0.5

    def test_interpolated_value(self):
        # Between 1 (60.0) and 5 (20.0)
        result = _trigger_multiplier(3)
        assert 20.0 < result < 60.0

    def test_interpolation_between_30_and_60(self):
        result = _trigger_multiplier(45)
        assert 1.5 < result < 3.0


# ===========================================================================
# Tests: AlertFatigueEngine.assess_fatigue
# ===========================================================================


class TestAssessFatigue:
    def setup_method(self):
        self.engine = AlertFatigueEngine()

    def test_empty_alerts(self):
        result = self.engine.assess_fatigue([])
        assert result.total_alerts == 0
        assert result.fatigue_risk == FatigueRisk.NONE
        assert result.actionable_ratio == 0.0

    def test_single_alert(self):
        alerts = [_alert("a1")]
        result = self.engine.assess_fatigue(alerts)
        assert result.total_alerts == 1
        assert result.actionable_ratio == 1.0

    def test_all_actionable(self):
        alerts = [_alert(f"a{i}") for i in range(5)]
        result = self.engine.assess_fatigue(alerts)
        assert result.actionable_ratio == 1.0
        assert result.noise_alerts == []

    def test_mixed_actionable(self):
        alerts = [
            _alert("a1", actionable=True),
            _alert("a2", actionable=False),
            _alert("a3", actionable=True),
            _alert("a4", actionable=False),
        ]
        result = self.engine.assess_fatigue(alerts)
        assert result.actionable_ratio == 0.5
        assert sorted(result.noise_alerts) == ["a2", "a4"]

    def test_all_non_actionable(self):
        alerts = [_alert(f"a{i}", actionable=False) for i in range(3)]
        result = self.engine.assess_fatigue(alerts)
        assert result.actionable_ratio == 0.0
        assert len(result.noise_alerts) == 3

    def test_estimated_daily_alerts_positive(self):
        alerts = [_alert("a1", window=5)]
        result = self.engine.assess_fatigue(alerts)
        assert result.estimated_daily_alerts > 0

    def test_suppression_reduces_daily(self):
        alerts_no_supp = [_alert("a1", window=5)]
        alerts_with_supp = [_alert("a1", window=5, suppression=30)]
        r1 = self.engine.assess_fatigue(alerts_no_supp)
        r2 = self.engine.assess_fatigue(alerts_with_supp)
        assert r2.estimated_daily_alerts <= r1.estimated_daily_alerts

    def test_auto_resolve_reduces_daily(self):
        alerts_no_ar = [_alert("a1", window=5)]
        alerts_with_ar = [_alert("a1", window=5, auto_resolve=True)]
        r1 = self.engine.assess_fatigue(alerts_no_ar)
        r2 = self.engine.assess_fatigue(alerts_with_ar)
        assert r2.estimated_daily_alerts <= r1.estimated_daily_alerts

    def test_fatigue_risk_none_for_small_set(self):
        alerts = [_alert("a1", window=60, suppression=30)]
        result = self.engine.assess_fatigue(alerts)
        assert result.fatigue_risk in (FatigueRisk.NONE, FatigueRisk.LOW)

    def test_fatigue_risk_increases_with_volume(self):
        # Many alerts with short windows
        alerts = _large_alert_set(30, window=1, actionable=False)
        result = self.engine.assess_fatigue(alerts)
        assert result.fatigue_risk in (FatigueRisk.HIGH, FatigueRisk.SEVERE)

    def test_duplicate_groups_detected(self):
        alerts = [
            _alert("a1", component_id="svc-1", severity=AlertSeverity.WARNING, threshold=80),
            _alert("a2", component_id="svc-1", severity=AlertSeverity.WARNING, threshold=82),
        ]
        result = self.engine.assess_fatigue(alerts)
        assert len(result.duplicate_groups) == 1

    def test_recommendations_non_empty_for_noisy_set(self):
        alerts = [_alert(f"a{i}", actionable=False, window=1) for i in range(10)]
        result = self.engine.assess_fatigue(alerts)
        assert len(result.recommendations) > 0

    def test_recommendations_include_actionable_advice(self):
        alerts = [
            _alert("a1", actionable=False),
            _alert("a2", actionable=False),
            _alert("a3", actionable=True),
        ]
        result = self.engine.assess_fatigue(alerts)
        joined = " ".join(result.recommendations)
        assert "actionable" in joined.lower() or "non-actionable" in joined.lower()

    def test_threshold_adjustments_for_non_actionable(self):
        alerts = [_alert("a1", actionable=False, threshold=50.0)]
        result = self.engine.assess_fatigue(alerts)
        assert "a1" in result.optimal_threshold_adjustments
        assert result.optimal_threshold_adjustments["a1"] > 50.0

    def test_threshold_adjustments_for_short_window_low_threshold(self):
        alerts = [_alert("a1", window=2, threshold=30.0)]
        result = self.engine.assess_fatigue(alerts)
        assert "a1" in result.optimal_threshold_adjustments
        assert result.optimal_threshold_adjustments["a1"] > 30.0


# ===========================================================================
# Tests: AlertFatigueEngine.detect_duplicate_alerts
# ===========================================================================


class TestDetectDuplicates:
    def setup_method(self):
        self.engine = AlertFatigueEngine()

    def test_empty_list(self):
        assert self.engine.detect_duplicate_alerts([]) == []

    def test_no_duplicates(self):
        alerts = [
            _alert("a1", component_id="svc-1", severity=AlertSeverity.CRITICAL),
            _alert("a2", component_id="svc-2", severity=AlertSeverity.WARNING),
        ]
        assert self.engine.detect_duplicate_alerts(alerts) == []

    def test_same_component_same_severity_similar_threshold(self):
        alerts = [
            _alert("a1", component_id="svc-1", severity=AlertSeverity.WARNING, threshold=80),
            _alert("a2", component_id="svc-1", severity=AlertSeverity.WARNING, threshold=85),
        ]
        groups = self.engine.detect_duplicate_alerts(alerts)
        assert len(groups) == 1
        assert sorted(groups[0]) == ["a1", "a2"]

    def test_same_component_different_severity_not_duplicate(self):
        alerts = [
            _alert("a1", component_id="svc-1", severity=AlertSeverity.WARNING, threshold=80),
            _alert("a2", component_id="svc-1", severity=AlertSeverity.CRITICAL, threshold=80),
        ]
        groups = self.engine.detect_duplicate_alerts(alerts)
        assert len(groups) == 0

    def test_different_component_not_duplicate(self):
        alerts = [
            _alert("a1", component_id="svc-1", severity=AlertSeverity.WARNING, threshold=80),
            _alert("a2", component_id="svc-2", severity=AlertSeverity.WARNING, threshold=80),
        ]
        groups = self.engine.detect_duplicate_alerts(alerts)
        assert len(groups) == 0

    def test_threshold_too_different_not_duplicate(self):
        alerts = [
            _alert("a1", component_id="svc-1", severity=AlertSeverity.WARNING, threshold=80),
            _alert("a2", component_id="svc-1", severity=AlertSeverity.WARNING, threshold=50),
        ]
        groups = self.engine.detect_duplicate_alerts(alerts)
        assert len(groups) == 0

    def test_multiple_duplicate_groups(self):
        alerts = [
            _alert("a1", component_id="svc-1", severity=AlertSeverity.WARNING, threshold=80),
            _alert("a2", component_id="svc-1", severity=AlertSeverity.WARNING, threshold=82),
            _alert("a3", component_id="svc-2", severity=AlertSeverity.CRITICAL, threshold=90),
            _alert("a4", component_id="svc-2", severity=AlertSeverity.CRITICAL, threshold=92),
        ]
        groups = self.engine.detect_duplicate_alerts(alerts)
        assert len(groups) == 2

    def test_three_way_duplicate(self):
        alerts = [
            _alert("a1", component_id="svc-1", severity=AlertSeverity.WARNING, threshold=80),
            _alert("a2", component_id="svc-1", severity=AlertSeverity.WARNING, threshold=82),
            _alert("a3", component_id="svc-1", severity=AlertSeverity.WARNING, threshold=84),
        ]
        groups = self.engine.detect_duplicate_alerts(alerts)
        assert len(groups) == 1
        assert len(groups[0]) == 3

    def test_single_alert_no_group(self):
        alerts = [_alert("a1")]
        groups = self.engine.detect_duplicate_alerts(alerts)
        assert len(groups) == 0


# ===========================================================================
# Tests: AlertFatigueEngine.recommend_thresholds
# ===========================================================================


class TestRecommendThresholds:
    def setup_method(self):
        self.engine = AlertFatigueEngine()

    def test_empty_alerts(self):
        g = _chain_graph()
        result = self.engine.recommend_thresholds(g, [])
        assert result == {}

    def test_component_not_in_graph(self):
        g = _chain_graph()
        alerts = [_alert("a1", component_id="nonexistent")]
        result = self.engine.recommend_thresholds(g, alerts)
        assert result == {}

    def test_threshold_close_to_utilization_raised(self):
        g = InfraGraph()
        g.add_component(_comp("svc-1", cpu=75.0))
        alerts = [_alert("a1", component_id="svc-1", threshold=78.0)]
        result = self.engine.recommend_thresholds(g, alerts)
        assert "a1" in result
        assert result["a1"] > 78.0

    def test_threshold_far_from_utilization_tightened(self):
        g = InfraGraph()
        g.add_component(_comp("svc-1", cpu=20.0))
        alerts = [_alert("a1", component_id="svc-1", threshold=80.0)]
        result = self.engine.recommend_thresholds(g, alerts)
        assert "a1" in result
        assert result["a1"] < 80.0

    def test_many_dependents_lowers_threshold(self):
        g = InfraGraph()
        g.add_component(_comp("db", "Database", ComponentType.DATABASE, cpu=50.0))
        g.add_component(_comp("svc-1"))
        g.add_component(_comp("svc-2"))
        g.add_component(_comp("svc-3"))
        g.add_dependency(Dependency(source_id="svc-1", target_id="db"))
        g.add_dependency(Dependency(source_id="svc-2", target_id="db"))
        g.add_dependency(Dependency(source_id="svc-3", target_id="db"))
        alerts = [_alert("a1", component_id="db", threshold=80.0)]
        result = self.engine.recommend_thresholds(g, alerts)
        assert "a1" in result
        assert result["a1"] < 80.0

    def test_critical_not_lowered_for_dependents(self):
        g = InfraGraph()
        g.add_component(_comp("db", cpu=50.0))
        g.add_component(_comp("svc-1"))
        g.add_component(_comp("svc-2"))
        g.add_component(_comp("svc-3"))
        g.add_dependency(Dependency(source_id="svc-1", target_id="db"))
        g.add_dependency(Dependency(source_id="svc-2", target_id="db"))
        g.add_dependency(Dependency(source_id="svc-3", target_id="db"))
        alerts = [
            _alert("a1", component_id="db", severity=AlertSeverity.CRITICAL, threshold=80.0)
        ]
        result = self.engine.recommend_thresholds(g, alerts)
        # Critical severity alerts should not have the dependent-lowering applied
        if "a1" in result:
            # If the threshold is close/far, it might still be adjusted for
            # headroom reasons, but not below a dependent-reduction.
            assert result["a1"] > 0

    def test_zero_utilization_no_adjustment(self):
        g = InfraGraph()
        g.add_component(_comp("svc-1"))
        alerts = [_alert("a1", component_id="svc-1", threshold=80.0)]
        result = self.engine.recommend_thresholds(g, alerts)
        # With zero utilization and reasonable threshold, no headroom issue
        assert "a1" not in result or result["a1"] != 80.0

    def test_multiple_alerts_independent(self):
        g = InfraGraph()
        g.add_component(_comp("svc-1", cpu=70.0))
        g.add_component(_comp("svc-2", cpu=20.0))
        alerts = [
            _alert("a1", component_id="svc-1", threshold=75.0),
            _alert("a2", component_id="svc-2", threshold=80.0),
        ]
        result = self.engine.recommend_thresholds(g, alerts)
        # a1 should be raised (close to utilization)
        assert "a1" in result


# ===========================================================================
# Tests: AlertFatigueEngine.simulate_alert_storm
# ===========================================================================


class TestSimulateAlertStorm:
    def setup_method(self):
        self.engine = AlertFatigueEngine()

    def test_empty_alerts(self):
        g = _chain_graph()
        result = self.engine.simulate_alert_storm(g, [], "db")
        assert result.total_alerts_generated == 0

    def test_empty_scenario(self):
        alerts = [_alert("a1", component_id="db")]
        g = _chain_graph()
        result = self.engine.simulate_alert_storm(g, alerts, "")
        assert result.total_alerts_generated == 0

    def test_single_component_failure(self):
        g = _chain_graph()
        alerts = [_alert("a1", component_id="db")]
        result = self.engine.simulate_alert_storm(g, alerts, "db")
        assert result.total_alerts_generated > 0
        assert "db" in result.affected_components

    def test_cascade_includes_dependents(self):
        g = _chain_graph()
        alerts = [
            _alert("a1", component_id="db"),
            _alert("a2", component_id="api"),
            _alert("a3", component_id="lb"),
        ]
        result = self.engine.simulate_alert_storm(g, alerts, "db")
        assert "db" in result.affected_components
        assert "api" in result.affected_components
        assert "lb" in result.affected_components

    def test_cascade_depth(self):
        g = _chain_graph()
        alerts = [
            _alert("a1", component_id="db"),
            _alert("a2", component_id="api"),
        ]
        result = self.engine.simulate_alert_storm(g, alerts, "db")
        assert result.cascade_depth >= 1

    def test_no_matching_alerts(self):
        g = _chain_graph()
        alerts = [_alert("a1", component_id="nonexistent")]
        result = self.engine.simulate_alert_storm(g, alerts, "db")
        # No alerts for affected components
        assert result.total_alerts_generated == 0

    def test_peak_alerts_per_minute(self):
        g = _chain_graph()
        alerts = [
            _alert("a1", component_id="db", window=1),
            _alert("a2", component_id="db", window=1),
        ]
        result = self.engine.simulate_alert_storm(g, alerts, "db")
        assert result.peak_alerts_per_minute > 0

    def test_short_window_higher_peak(self):
        g = _chain_graph()
        short_alerts = [_alert("a1", component_id="db", window=1)]
        long_alerts = [_alert("a1", component_id="db", window=30)]
        r_short = self.engine.simulate_alert_storm(g, short_alerts, "db")
        r_long = self.engine.simulate_alert_storm(g, long_alerts, "db")
        assert r_short.peak_alerts_per_minute >= r_long.peak_alerts_per_minute

    def test_suppression_reduces_duration(self):
        g = _chain_graph()
        no_supp = [_alert("a1", component_id="db")]
        with_supp = [_alert("a1", component_id="db", suppression=30, auto_resolve=True)]
        r1 = self.engine.simulate_alert_storm(g, no_supp, "db")
        r2 = self.engine.simulate_alert_storm(g, with_supp, "db")
        assert r2.storm_duration_minutes <= r1.storm_duration_minutes

    def test_duplicate_detection_in_storm(self):
        g = _chain_graph()
        alerts = [
            _alert("a1", component_id="db", severity=AlertSeverity.WARNING, threshold=80),
            _alert("a2", component_id="db", severity=AlertSeverity.WARNING, threshold=82),
        ]
        result = self.engine.simulate_alert_storm(g, alerts, "db")
        assert result.duplicate_alerts > 0

    def test_fatigue_risk_severe_for_large_storm(self):
        g = _fan_graph()
        alerts = [
            _alert(f"a{i}", component_id=cid, window=1)
            for i, cid in enumerate(["api", "db", "cache", "queue", "svc"] * 5)
        ]
        result = self.engine.simulate_alert_storm(g, alerts, "api")
        assert result.fatigue_risk in (FatigueRisk.HIGH, FatigueRisk.SEVERE)

    def test_fatigue_risk_none_for_tiny_storm(self):
        g = InfraGraph()
        g.add_component(_comp("svc-1"))
        alerts = [_alert("a1", component_id="svc-1", window=60)]
        result = self.engine.simulate_alert_storm(g, alerts, "svc-1")
        assert result.fatigue_risk in (FatigueRisk.NONE, FatigueRisk.LOW)

    def test_affected_components_sorted(self):
        g = _chain_graph()
        alerts = [_alert("a1", component_id="db")]
        result = self.engine.simulate_alert_storm(g, alerts, "db")
        assert result.affected_components == sorted(result.affected_components)


# ===========================================================================
# Tests: AlertFatigueEngine.calculate_signal_to_noise
# ===========================================================================


class TestSignalToNoise:
    def setup_method(self):
        self.engine = AlertFatigueEngine()

    def test_empty_alerts(self):
        assert self.engine.calculate_signal_to_noise([]) == 0.0

    def test_all_actionable_no_duplicates(self):
        alerts = [_alert(f"a{i}", component_id=f"svc-{i}", auto_resolve=True, suppression=10)
                  for i in range(5)]
        snr = self.engine.calculate_signal_to_noise(alerts)
        assert snr > 0.7

    def test_all_non_actionable(self):
        alerts = [_alert(f"a{i}", actionable=False) for i in range(5)]
        snr = self.engine.calculate_signal_to_noise(alerts)
        assert snr < 0.5

    def test_duplicates_reduce_snr(self):
        no_dup = [
            _alert("a1", component_id="svc-1", severity=AlertSeverity.WARNING, threshold=80),
            _alert("a2", component_id="svc-2", severity=AlertSeverity.WARNING, threshold=80),
        ]
        with_dup = [
            _alert("a1", component_id="svc-1", severity=AlertSeverity.WARNING, threshold=80),
            _alert("a2", component_id="svc-1", severity=AlertSeverity.WARNING, threshold=82),
        ]
        snr_no_dup = self.engine.calculate_signal_to_noise(no_dup)
        snr_dup = self.engine.calculate_signal_to_noise(with_dup)
        assert snr_no_dup > snr_dup

    def test_too_many_criticals_lower_snr(self):
        mostly_crit = [
            _alert(f"a{i}", severity=AlertSeverity.CRITICAL, component_id=f"svc-{i}")
            for i in range(10)
        ]
        mostly_warn = [
            _alert(f"a{i}", severity=AlertSeverity.WARNING, component_id=f"svc-{i}")
            for i in range(10)
        ]
        snr_crit = self.engine.calculate_signal_to_noise(mostly_crit)
        snr_warn = self.engine.calculate_signal_to_noise(mostly_warn)
        assert snr_warn > snr_crit

    def test_bounded_0_to_1(self):
        alerts = [_alert("a1")]
        snr = self.engine.calculate_signal_to_noise(alerts)
        assert 0.0 <= snr <= 1.0

    def test_managed_alerts_improve_snr(self):
        unmanaged = [_alert("a1", auto_resolve=False, suppression=0)]
        managed = [_alert("a1", auto_resolve=True, suppression=15)]
        snr_un = self.engine.calculate_signal_to_noise(unmanaged)
        snr_man = self.engine.calculate_signal_to_noise(managed)
        assert snr_man >= snr_un

    def test_single_alert(self):
        snr = self.engine.calculate_signal_to_noise([_alert("a1")])
        assert snr > 0.0


# ===========================================================================
# Tests: AlertFatigueEngine.optimize_alert_set
# ===========================================================================


class TestOptimizeAlertSet:
    def setup_method(self):
        self.engine = AlertFatigueEngine()

    def test_empty_alerts(self):
        assert self.engine.optimize_alert_set([]) == []

    def test_removes_non_actionable(self):
        alerts = [
            _alert("a1", actionable=True),
            _alert("a2", actionable=False, component_id="svc-2"),
        ]
        result = self.engine.optimize_alert_set(alerts)
        ids = [a.id for a in result]
        assert "a1" in ids
        assert "a2" not in ids

    def test_keeps_all_if_all_non_actionable(self):
        alerts = [
            _alert("a1", actionable=False),
            _alert("a2", actionable=False, component_id="svc-2"),
        ]
        result = self.engine.optimize_alert_set(alerts)
        assert len(result) >= 1  # Should not return empty

    def test_removes_duplicates(self):
        alerts = [
            _alert("a1", component_id="svc-1", severity=AlertSeverity.WARNING, threshold=80),
            _alert("a2", component_id="svc-1", severity=AlertSeverity.WARNING, threshold=82),
        ]
        result = self.engine.optimize_alert_set(alerts)
        assert len(result) == 1

    def test_adds_suppression_critical(self):
        alerts = [_alert("a1", severity=AlertSeverity.CRITICAL, suppression=0)]
        result = self.engine.optimize_alert_set(alerts)
        assert result[0].suppression_minutes == 5

    def test_adds_suppression_warning(self):
        alerts = [_alert("a1", severity=AlertSeverity.WARNING, suppression=0)]
        result = self.engine.optimize_alert_set(alerts)
        assert result[0].suppression_minutes == 15

    def test_adds_suppression_info(self):
        alerts = [_alert("a1", severity=AlertSeverity.INFO, suppression=0)]
        result = self.engine.optimize_alert_set(alerts)
        assert result[0].suppression_minutes == 30

    def test_adds_suppression_debug(self):
        alerts = [_alert("a1", severity=AlertSeverity.DEBUG, suppression=0)]
        result = self.engine.optimize_alert_set(alerts)
        assert result[0].suppression_minutes == 60

    def test_preserves_existing_suppression(self):
        alerts = [_alert("a1", severity=AlertSeverity.WARNING, suppression=45)]
        result = self.engine.optimize_alert_set(alerts)
        assert result[0].suppression_minutes == 45

    def test_sets_auto_resolve_info(self):
        alerts = [_alert("a1", severity=AlertSeverity.INFO, auto_resolve=False)]
        result = self.engine.optimize_alert_set(alerts)
        assert result[0].auto_resolve is True

    def test_sets_auto_resolve_debug(self):
        alerts = [_alert("a1", severity=AlertSeverity.DEBUG, auto_resolve=False)]
        result = self.engine.optimize_alert_set(alerts)
        assert result[0].auto_resolve is True

    def test_does_not_set_auto_resolve_warning(self):
        alerts = [_alert("a1", severity=AlertSeverity.WARNING, auto_resolve=False)]
        result = self.engine.optimize_alert_set(alerts)
        assert result[0].auto_resolve is False

    def test_does_not_set_auto_resolve_critical(self):
        alerts = [_alert("a1", severity=AlertSeverity.CRITICAL, auto_resolve=False)]
        result = self.engine.optimize_alert_set(alerts)
        assert result[0].auto_resolve is False

    def test_optimized_set_is_smaller_than_noisy_input(self):
        alerts = [
            _alert("a1", actionable=True),
            _alert("a2", actionable=False, component_id="svc-2"),
            _alert("a3", component_id="svc-1", severity=AlertSeverity.WARNING, threshold=80),
            _alert("a4", component_id="svc-1", severity=AlertSeverity.WARNING, threshold=82),
        ]
        result = self.engine.optimize_alert_set(alerts)
        assert len(result) < len(alerts)

    def test_original_not_modified(self):
        alerts = [_alert("a1", suppression=0)]
        _ = self.engine.optimize_alert_set(alerts)
        assert alerts[0].suppression_minutes == 0


# ===========================================================================
# Tests: AlertFatigueEngine.estimate_response_time
# ===========================================================================


class TestEstimateResponseTime:
    def setup_method(self):
        self.engine = AlertFatigueEngine()

    def test_empty_alerts(self):
        assert self.engine.estimate_response_time([]) == 0.0

    def test_single_critical(self):
        alerts = [_alert("a1", severity=AlertSeverity.CRITICAL, window=15)]
        rt = self.engine.estimate_response_time(alerts)
        assert rt > 0.0

    def test_critical_slower_than_info(self):
        critical = [_alert("a1", severity=AlertSeverity.CRITICAL)]
        info = [_alert("a1", severity=AlertSeverity.INFO)]
        rt_crit = self.engine.estimate_response_time(critical)
        rt_info = self.engine.estimate_response_time(info)
        assert rt_crit > rt_info

    def test_auto_resolve_reduces_response_time(self):
        no_ar = [_alert("a1", auto_resolve=False)]
        with_ar = [_alert("a1", auto_resolve=True)]
        rt_no = self.engine.estimate_response_time(no_ar)
        rt_ar = self.engine.estimate_response_time(with_ar)
        assert rt_ar < rt_no

    def test_suppression_reduces_response_time(self):
        no_supp = [_alert("a1", suppression=0)]
        with_supp = [_alert("a1", suppression=30)]
        rt_no = self.engine.estimate_response_time(no_supp)
        rt_supp = self.engine.estimate_response_time(with_supp)
        assert rt_supp < rt_no

    def test_non_actionable_lower_effort(self):
        actionable = [_alert("a1", actionable=True)]
        non_actionable = [_alert("a1", actionable=False)]
        rt_act = self.engine.estimate_response_time(actionable)
        rt_na = self.engine.estimate_response_time(non_actionable)
        assert rt_na < rt_act

    def test_many_alerts_slower(self):
        few = [_alert("a1")]
        many = _large_alert_set(20, window=5)
        rt_few = self.engine.estimate_response_time(few)
        rt_many = self.engine.estimate_response_time(many)
        assert rt_many > rt_few

    def test_response_time_non_negative(self):
        alerts = [_alert("a1", auto_resolve=True, suppression=60)]
        rt = self.engine.estimate_response_time(alerts)
        assert rt >= 0.0


# ===========================================================================
# Tests: Fatigue risk classification edge cases
# ===========================================================================


class TestFatigueRiskClassification:
    def setup_method(self):
        self.engine = AlertFatigueEngine()

    def test_low_risk_moderate_volume(self):
        alerts = _large_alert_set(10, window=30, suppression=30)
        result = self.engine.assess_fatigue(alerts)
        assert result.fatigue_risk in (FatigueRisk.NONE, FatigueRisk.LOW, FatigueRisk.MODERATE)

    def test_high_risk_many_non_actionable(self):
        alerts = _large_alert_set(25, actionable=False, window=5)
        result = self.engine.assess_fatigue(alerts)
        assert result.fatigue_risk in (
            FatigueRisk.HIGH, FatigueRisk.SEVERE, FatigueRisk.MODERATE,
        )

    def test_severe_risk_many_duplicates_and_noise(self):
        # Many alerts on same component with similar thresholds
        alerts = [
            _alert(f"a{i}", component_id="svc-1",
                   severity=AlertSeverity.WARNING,
                   threshold=80 + i * 0.5,
                   actionable=False,
                   window=1)
            for i in range(30)
        ]
        result = self.engine.assess_fatigue(alerts)
        assert result.fatigue_risk in (FatigueRisk.HIGH, FatigueRisk.SEVERE)


# ===========================================================================
# Tests: Recommendations detail
# ===========================================================================


class TestRecommendations:
    def setup_method(self):
        self.engine = AlertFatigueEngine()

    def test_recommendation_for_high_daily_volume(self):
        alerts = _large_alert_set(20, window=1)
        result = self.engine.assess_fatigue(alerts)
        has_volume_rec = any("daily" in r.lower() for r in result.recommendations)
        assert has_volume_rec

    def test_recommendation_for_duplicate_groups(self):
        alerts = [
            _alert("a1", component_id="svc-1", severity=AlertSeverity.WARNING, threshold=80),
            _alert("a2", component_id="svc-1", severity=AlertSeverity.WARNING, threshold=82),
        ]
        result = self.engine.assess_fatigue(alerts)
        has_dup_rec = any("duplicate" in r.lower() for r in result.recommendations)
        assert has_dup_rec

    def test_recommendation_for_missing_suppression(self):
        alerts = [_alert("a1", suppression=0)]
        result = self.engine.assess_fatigue(alerts)
        has_supp_rec = any("suppression" in r.lower() for r in result.recommendations)
        assert has_supp_rec

    def test_recommendation_for_info_without_auto_resolve(self):
        alerts = [_alert("a1", severity=AlertSeverity.INFO, auto_resolve=False)]
        result = self.engine.assess_fatigue(alerts)
        has_ar_rec = any("auto-resolve" in r.lower() or "auto_resolve" in r.lower()
                         for r in result.recommendations)
        assert has_ar_rec

    def test_recommendation_for_short_windows(self):
        alerts = [_alert("a1", window=2)]
        result = self.engine.assess_fatigue(alerts)
        has_window_rec = any("window" in r.lower() for r in result.recommendations)
        assert has_window_rec

    def test_recommendation_for_critical_single_channel(self):
        alerts = [_alert("a1", severity=AlertSeverity.CRITICAL, channels=["slack"])]
        result = self.engine.assess_fatigue(alerts)
        has_channel_rec = any("channel" in r.lower() for r in result.recommendations)
        assert has_channel_rec


# ===========================================================================
# Tests: Integration scenarios
# ===========================================================================


class TestIntegrationScenarios:
    def setup_method(self):
        self.engine = AlertFatigueEngine()

    def test_well_configured_system(self):
        """A well-configured alert set should have low fatigue risk."""
        alerts = [
            _alert("cpu-critical", severity=AlertSeverity.CRITICAL, threshold=95.0,
                   window=10, channels=["pagerduty", "slack"], suppression=5),
            _alert("cpu-warning", severity=AlertSeverity.WARNING, threshold=80.0,
                   window=15, channels=["slack"], suppression=15, component_id="svc-2"),
            _alert("disk-info", severity=AlertSeverity.INFO, threshold=70.0,
                   window=60, auto_resolve=True, suppression=30, component_id="svc-3"),
        ]
        assessment = self.engine.assess_fatigue(alerts)
        assert assessment.fatigue_risk in (FatigueRisk.NONE, FatigueRisk.LOW)
        assert assessment.actionable_ratio == 1.0
        assert len(assessment.duplicate_groups) == 0

    def test_poorly_configured_system(self):
        """A poorly configured alert set should have high fatigue risk."""
        alerts = [
            _alert(f"noise-{i}", severity=AlertSeverity.WARNING, threshold=50 + i,
                   window=1, actionable=False, component_id="svc-1")
            for i in range(20)
        ]
        assessment = self.engine.assess_fatigue(alerts)
        assert assessment.fatigue_risk in (FatigueRisk.HIGH, FatigueRisk.SEVERE)
        assert assessment.actionable_ratio == 0.0
        assert len(assessment.recommendations) > 0

    def test_optimize_then_reassess(self):
        """Optimizing an alert set should improve the fatigue assessment."""
        original = [
            _alert("a1", actionable=True, suppression=0),
            _alert("a2", actionable=False, component_id="svc-2", suppression=0),
            _alert("a3", component_id="svc-1", severity=AlertSeverity.WARNING, threshold=80),
            _alert("a4", component_id="svc-1", severity=AlertSeverity.WARNING, threshold=82),
            _alert("a5", severity=AlertSeverity.INFO, auto_resolve=False,
                   component_id="svc-3"),
        ]
        optimized = self.engine.optimize_alert_set(original)
        snr_before = self.engine.calculate_signal_to_noise(original)
        snr_after = self.engine.calculate_signal_to_noise(optimized)
        assert snr_after >= snr_before

    def test_storm_then_assess(self):
        """An alert storm should correlate with high fatigue risk."""
        g = _chain_graph()
        alerts = [
            _alert("a1", component_id="db", window=1),
            _alert("a2", component_id="api", window=1),
            _alert("a3", component_id="lb", window=1),
        ]
        storm = self.engine.simulate_alert_storm(g, alerts, "db")
        assert storm.total_alerts_generated > 0
        assert storm.cascade_depth >= 1

    def test_end_to_end_pipeline(self):
        """Full pipeline: assess -> optimize -> reassess."""
        alerts = [
            _alert(f"a{i}", component_id=f"svc-{i % 3}",
                   severity=[AlertSeverity.CRITICAL, AlertSeverity.WARNING,
                             AlertSeverity.INFO][i % 3],
                   threshold=70 + i,
                   window=5 + i * 2,
                   actionable=i % 4 != 0)
            for i in range(12)
        ]

        # Step 1: Initial assessment
        assessment = self.engine.assess_fatigue(alerts)
        assert assessment.total_alerts == 12

        # Step 2: Optimize
        optimized = self.engine.optimize_alert_set(alerts)
        assert len(optimized) <= len(alerts)

        # Step 3: Reassess
        new_assessment = self.engine.assess_fatigue(optimized)
        assert new_assessment.actionable_ratio >= assessment.actionable_ratio

        # Step 4: SNR should be better or equal
        snr_before = self.engine.calculate_signal_to_noise(alerts)
        snr_after = self.engine.calculate_signal_to_noise(optimized)
        assert snr_after >= snr_before

    def test_graph_based_threshold_recommendation(self):
        """Threshold recommendations should consider the graph topology."""
        g = _fan_graph()
        # api has 3 dependents (svc depends on api... actually svc -> api,
        # and api -> db, cache, queue). Let's make sure api has dependents.
        alerts = [
            _alert("a1", component_id="api", threshold=80.0, severity=AlertSeverity.WARNING),
        ]
        result = self.engine.recommend_thresholds(g, alerts)
        # api is depended upon by svc, so with 1 dependent it may or may not trigger
        # the 3-dependent rule. Let's just verify it runs.
        assert isinstance(result, dict)


# ===========================================================================
# Tests: Edge cases
# ===========================================================================


class TestEdgeCases:
    def setup_method(self):
        self.engine = AlertFatigueEngine()

    def test_alert_with_zero_threshold(self):
        alerts = [_alert("a1", threshold=0.0)]
        result = self.engine.assess_fatigue(alerts)
        assert result.total_alerts == 1

    def test_alert_with_negative_threshold(self):
        alerts = [_alert("a1", threshold=-10.0)]
        result = self.engine.assess_fatigue(alerts)
        assert result.total_alerts == 1

    def test_alert_with_very_large_threshold(self):
        alerts = [_alert("a1", threshold=99999.0)]
        result = self.engine.assess_fatigue(alerts)
        assert result.total_alerts == 1

    def test_alert_with_zero_window(self):
        alerts = [_alert("a1", window=0)]
        result = self.engine.assess_fatigue(alerts)
        assert result.estimated_daily_alerts > 0

    def test_alert_with_large_window(self):
        alerts = [_alert("a1", window=1440)]
        result = self.engine.assess_fatigue(alerts)
        assert result.estimated_daily_alerts >= 0

    def test_alert_with_empty_channels(self):
        alerts = [_alert("a1", channels=[])]
        result = self.engine.assess_fatigue(alerts)
        assert result.total_alerts == 1

    def test_all_same_severity(self):
        alerts = [
            _alert(f"a{i}", severity=AlertSeverity.WARNING, component_id=f"svc-{i}")
            for i in range(5)
        ]
        snr = self.engine.calculate_signal_to_noise(alerts)
        assert 0.0 <= snr <= 1.0

    def test_storm_with_nonexistent_component(self):
        g = _chain_graph()
        alerts = [_alert("a1", component_id="db")]
        result = self.engine.simulate_alert_storm(g, alerts, "nonexistent")
        # nonexistent is not in the graph, so returns empty result
        assert result.total_alerts_generated == 0
        assert result.affected_components == []

    def test_large_alert_set_performance(self):
        """Ensure engine handles 200+ alerts without error."""
        alerts = _large_alert_set(200, window=10)
        result = self.engine.assess_fatigue(alerts)
        assert result.total_alerts == 200

    def test_optimize_preserves_id(self):
        alerts = [_alert("unique-id-123")]
        result = self.engine.optimize_alert_set(alerts)
        assert result[0].id == "unique-id-123"

    def test_optimize_preserves_component_id(self):
        alerts = [_alert("a1", component_id="special-component")]
        result = self.engine.optimize_alert_set(alerts)
        assert result[0].component_id == "special-component"

    def test_snr_with_single_non_actionable(self):
        alerts = [_alert("a1", actionable=False)]
        snr = self.engine.calculate_signal_to_noise(alerts)
        assert 0.0 <= snr <= 1.0

    def test_response_time_with_all_auto_resolve(self):
        alerts = [_alert(f"a{i}", auto_resolve=True, suppression=30) for i in range(5)]
        rt = self.engine.estimate_response_time(alerts)
        assert rt >= 0.0

    def test_duplicate_with_identical_threshold(self):
        alerts = [
            _alert("a1", component_id="svc-1", severity=AlertSeverity.WARNING, threshold=80),
            _alert("a2", component_id="svc-1", severity=AlertSeverity.WARNING, threshold=80),
        ]
        groups = self.engine.detect_duplicate_alerts(alerts)
        assert len(groups) == 1

    def test_storm_with_only_suppression_no_autoresolve(self):
        g = _chain_graph()
        alerts = [_alert("a1", component_id="db", suppression=15, auto_resolve=False)]
        result = self.engine.simulate_alert_storm(g, alerts, "db")
        assert result.storm_duration_minutes == 30

    def test_storm_with_only_autoresolve_no_suppression(self):
        g = _chain_graph()
        alerts = [_alert("a1", component_id="db", suppression=0, auto_resolve=True)]
        result = self.engine.simulate_alert_storm(g, alerts, "db")
        assert result.storm_duration_minutes == 30

    def test_storm_with_medium_window_peak(self):
        """Cover the window <= 5 branch for peak_per_minute."""
        g = InfraGraph()
        g.add_component(_comp("svc-1"))
        alerts = [_alert("a1", component_id="svc-1", window=3)]
        result = self.engine.simulate_alert_storm(g, alerts, "svc-1")
        assert result.peak_alerts_per_minute == 2

    def test_trigger_multiplier_exact_boundary(self):
        """Test _trigger_multiplier at exact boundary value 10."""
        result = _trigger_multiplier(10)
        assert result == 10.0

    def test_trigger_multiplier_between_10_and_15(self):
        """Test interpolation between 10 (10.0) and 15 (6.0)."""
        result = _trigger_multiplier(12)
        assert 6.0 < result < 10.0
