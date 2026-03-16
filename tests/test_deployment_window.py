"""Tests for deployment window risk analyzer."""

from __future__ import annotations

import pytest

from faultray.model.components import Component, ComponentType, Dependency, HealthStatus
from faultray.model.graph import InfraGraph
from faultray.simulator.deployment_window import (
    DeploymentType,
    DeploymentWindowEngine,
    PeakDeployResult,
    ScheduledDeploy,
    TimeWindow,
    WindowAssessment,
    WindowRisk,
    _DAY_MULTIPLIER,
    _DEPLOY_DURATION,
    _DEPLOY_TYPE_WEIGHT,
    _HOURLY_TRAFFIC,
    _TEAM_AVAILABILITY,
    _WEEKEND_AVAIL_MULTIPLIER,
    _graph_complexity,
    _graph_health_penalty,
    _incident_penalty,
    _risk_from_score,
    _spof_count,
    _team_avail,
    _traffic_label,
    _traffic_level_for,
    _window_span_hours,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(
    cid: str = "c1",
    name: str = "comp",
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 2,
    health: HealthStatus = HealthStatus.HEALTHY,
    failover: bool = False,
    autoscaling: bool = False,
    cpu: float = 0.0,
) -> Component:
    c = Component(id=cid, name=name, type=ctype, replicas=replicas)
    c.health = health
    if failover:
        c.failover.enabled = True
    if autoscaling:
        c.autoscaling.enabled = True
    if cpu > 0:
        c.metrics.cpu_percent = cpu
    return c


def _graph(*comps: Component, deps: list[tuple[str, str]] | None = None) -> InfraGraph:
    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    for src, tgt in (deps or []):
        g.add_dependency(Dependency(source_id=src, target_id=tgt))
    return g


# ---------------------------------------------------------------------------
# Tests: Enums
# ---------------------------------------------------------------------------


class TestWindowRisk:
    def test_values(self):
        assert WindowRisk.LOW.value == "low"
        assert WindowRisk.MODERATE.value == "moderate"
        assert WindowRisk.ELEVATED.value == "elevated"
        assert WindowRisk.HIGH.value == "high"
        assert WindowRisk.CRITICAL.value == "critical"

    def test_count(self):
        assert len(WindowRisk) == 5

    def test_str_enum(self):
        assert isinstance(WindowRisk.LOW, str)
        assert WindowRisk.LOW == "low"

    def test_from_value(self):
        assert WindowRisk("low") is WindowRisk.LOW


class TestDeploymentType:
    def test_values(self):
        assert DeploymentType.FEATURE_RELEASE.value == "feature_release"
        assert DeploymentType.HOTFIX.value == "hotfix"
        assert DeploymentType.INFRASTRUCTURE_CHANGE.value == "infrastructure_change"
        assert DeploymentType.CONFIG_UPDATE.value == "config_update"
        assert DeploymentType.DATABASE_MIGRATION.value == "database_migration"
        assert DeploymentType.DEPENDENCY_UPGRADE.value == "dependency_upgrade"
        assert DeploymentType.ROLLBACK.value == "rollback"

    def test_count(self):
        assert len(DeploymentType) == 7

    def test_str_enum(self):
        assert isinstance(DeploymentType.HOTFIX, str)

    def test_from_value(self):
        assert DeploymentType("rollback") is DeploymentType.ROLLBACK


# ---------------------------------------------------------------------------
# Tests: TimeWindow model
# ---------------------------------------------------------------------------


class TestTimeWindow:
    def test_basic_creation(self):
        tw = TimeWindow(start_hour=10, end_hour=11, day_of_week=1)
        assert tw.start_hour == 10
        assert tw.end_hour == 11
        assert tw.day_of_week == 1
        assert tw.timezone == "UTC"

    def test_custom_timezone(self):
        tw = TimeWindow(start_hour=0, end_hour=23, day_of_week=6, timezone="Asia/Tokyo")
        assert tw.timezone == "Asia/Tokyo"

    def test_boundary_hours(self):
        tw = TimeWindow(start_hour=0, end_hour=0, day_of_week=0)
        assert tw.start_hour == 0
        assert tw.end_hour == 0

    def test_max_hour(self):
        tw = TimeWindow(start_hour=23, end_hour=23, day_of_week=6)
        assert tw.start_hour == 23

    def test_invalid_start_hour_high(self):
        with pytest.raises(Exception):
            TimeWindow(start_hour=24, end_hour=10, day_of_week=0)

    def test_invalid_start_hour_low(self):
        with pytest.raises(Exception):
            TimeWindow(start_hour=-1, end_hour=10, day_of_week=0)

    def test_invalid_end_hour(self):
        with pytest.raises(Exception):
            TimeWindow(start_hour=10, end_hour=25, day_of_week=0)

    def test_invalid_day_of_week_high(self):
        with pytest.raises(Exception):
            TimeWindow(start_hour=10, end_hour=11, day_of_week=7)

    def test_invalid_day_of_week_low(self):
        with pytest.raises(Exception):
            TimeWindow(start_hour=10, end_hour=11, day_of_week=-1)

    def test_serialisation_roundtrip(self):
        tw = TimeWindow(start_hour=14, end_hour=16, day_of_week=3, timezone="US/Pacific")
        data = tw.model_dump()
        tw2 = TimeWindow(**data)
        assert tw2 == tw


# ---------------------------------------------------------------------------
# Tests: WindowAssessment model
# ---------------------------------------------------------------------------


class TestWindowAssessment:
    def test_basic(self):
        tw = TimeWindow(start_hour=10, end_hour=11, day_of_week=1)
        wa = WindowAssessment(
            window=tw,
            risk=WindowRisk.LOW,
            risk_score=15.0,
            traffic_level="moderate",
            team_availability=0.9,
            recent_incidents_24h=0,
            change_freeze_active=False,
        )
        assert wa.risk == WindowRisk.LOW
        assert wa.optimal_alternative is None
        assert wa.recommendations == []

    def test_with_recommendations(self):
        tw = TimeWindow(start_hour=16, end_hour=17, day_of_week=0)
        wa = WindowAssessment(
            window=tw,
            risk=WindowRisk.HIGH,
            risk_score=75.0,
            traffic_level="peak",
            team_availability=0.5,
            recent_incidents_24h=3,
            change_freeze_active=True,
            recommendations=["Postpone", "Review"],
            optimal_alternative=TimeWindow(start_hour=3, end_hour=4, day_of_week=1),
        )
        assert len(wa.recommendations) == 2
        assert wa.optimal_alternative is not None
        assert wa.change_freeze_active is True

    def test_score_bounds(self):
        tw = TimeWindow(start_hour=10, end_hour=11, day_of_week=0)
        with pytest.raises(Exception):
            WindowAssessment(
                window=tw, risk=WindowRisk.LOW, risk_score=-1,
                traffic_level="low", team_availability=0.5,
                recent_incidents_24h=0, change_freeze_active=False,
            )

    def test_score_upper_bound(self):
        tw = TimeWindow(start_hour=10, end_hour=11, day_of_week=0)
        with pytest.raises(Exception):
            WindowAssessment(
                window=tw, risk=WindowRisk.LOW, risk_score=101,
                traffic_level="low", team_availability=0.5,
                recent_incidents_24h=0, change_freeze_active=False,
            )

    def test_team_availability_bounds(self):
        tw = TimeWindow(start_hour=10, end_hour=11, day_of_week=0)
        with pytest.raises(Exception):
            WindowAssessment(
                window=tw, risk=WindowRisk.LOW, risk_score=10,
                traffic_level="low", team_availability=1.5,
                recent_incidents_24h=0, change_freeze_active=False,
            )


# ---------------------------------------------------------------------------
# Tests: PeakDeployResult model
# ---------------------------------------------------------------------------


class TestPeakDeployResult:
    def test_basic(self):
        r = PeakDeployResult(
            estimated_error_rate_increase=0.5,
            estimated_latency_increase_ms=10.0,
            affected_users_percent=5.0,
            rollback_risk=20.0,
            capacity_headroom_percent=60.0,
            safe_to_deploy=True,
        )
        assert r.safe_to_deploy is True
        assert r.warnings == []

    def test_with_warnings(self):
        r = PeakDeployResult(
            estimated_error_rate_increase=2.0,
            estimated_latency_increase_ms=100.0,
            affected_users_percent=50.0,
            rollback_risk=80.0,
            capacity_headroom_percent=5.0,
            safe_to_deploy=False,
            warnings=["High impact", "Low headroom"],
        )
        assert len(r.warnings) == 2
        assert not r.safe_to_deploy


# ---------------------------------------------------------------------------
# Tests: ScheduledDeploy model
# ---------------------------------------------------------------------------


class TestScheduledDeploy:
    def test_basic(self):
        tw = TimeWindow(start_hour=10, end_hour=11, day_of_week=2)
        sd = ScheduledDeploy(
            deploy_type=DeploymentType.HOTFIX,
            recommended_window=tw,
            risk_score=25.0,
            priority=1,
            estimated_duration_minutes=15.0,
        )
        assert sd.deploy_type == DeploymentType.HOTFIX
        assert sd.priority == 1
        assert sd.notes == []

    def test_with_notes(self):
        tw = TimeWindow(start_hour=3, end_hour=4, day_of_week=0)
        sd = ScheduledDeploy(
            deploy_type=DeploymentType.DATABASE_MIGRATION,
            recommended_window=tw,
            risk_score=70.0,
            priority=2,
            estimated_duration_minutes=60.0,
            notes=["Backup first"],
        )
        assert len(sd.notes) == 1


# ---------------------------------------------------------------------------
# Tests: internal helpers — _traffic_level_for
# ---------------------------------------------------------------------------


class TestTrafficLevelFor:
    def test_midnight_weekday(self):
        v = _traffic_level_for(0, 0)  # Mon midnight
        assert v == pytest.approx(0.10 * 1.0)

    def test_peak_weekday(self):
        v = _traffic_level_for(16, 0)  # Mon 16:00 (peak)
        assert v == pytest.approx(1.0 * 1.0)

    def test_sunday(self):
        v = _traffic_level_for(16, 6)  # Sun 16:00
        assert v == pytest.approx(1.0 * 0.50)

    def test_saturday(self):
        v = _traffic_level_for(12, 5)  # Sat noon
        assert v == pytest.approx(0.80 * 0.55)

    def test_early_morning(self):
        v = _traffic_level_for(3, 2)  # Wed 03:00
        assert v == pytest.approx(0.05 * 1.0)


class TestTrafficLabel:
    def test_very_low(self):
        assert _traffic_label(0.05) == "very_low"

    def test_low(self):
        assert _traffic_label(0.20) == "low"

    def test_moderate(self):
        assert _traffic_label(0.50) == "moderate"

    def test_high(self):
        assert _traffic_label(0.70) == "high"

    def test_peak(self):
        assert _traffic_label(0.90) == "peak"

    def test_boundary_very_low(self):
        assert _traffic_label(0.14) == "very_low"

    def test_boundary_low(self):
        assert _traffic_label(0.15) == "low"

    def test_boundary_moderate(self):
        assert _traffic_label(0.35) == "moderate"

    def test_boundary_high(self):
        assert _traffic_label(0.60) == "high"

    def test_boundary_peak(self):
        assert _traffic_label(0.80) == "peak"


# ---------------------------------------------------------------------------
# Tests: _team_avail
# ---------------------------------------------------------------------------


class TestTeamAvail:
    def test_core_hours(self):
        v = _team_avail(10, 1)  # Tue 10:00
        assert v == 0.95

    def test_night(self):
        v = _team_avail(2, 0)  # Mon 02:00
        assert v == 0.05

    def test_weekend_core(self):
        v = _team_avail(10, 5)  # Sat 10:00
        assert v == pytest.approx(0.95 * _WEEKEND_AVAIL_MULTIPLIER)

    def test_weekend_night(self):
        v = _team_avail(2, 6)  # Sun 02:00
        assert v == pytest.approx(0.05 * _WEEKEND_AVAIL_MULTIPLIER)

    def test_capped_at_one(self):
        # Even if base * multiplier > 1, should be capped.
        for h in range(24):
            for d in range(7):
                assert _team_avail(h, d) <= 1.0


# ---------------------------------------------------------------------------
# Tests: _risk_from_score
# ---------------------------------------------------------------------------


class TestRiskFromScore:
    def test_low(self):
        assert _risk_from_score(0) == WindowRisk.LOW
        assert _risk_from_score(19.9) == WindowRisk.LOW

    def test_moderate(self):
        assert _risk_from_score(20) == WindowRisk.MODERATE
        assert _risk_from_score(39.9) == WindowRisk.MODERATE

    def test_elevated(self):
        assert _risk_from_score(40) == WindowRisk.ELEVATED
        assert _risk_from_score(59.9) == WindowRisk.ELEVATED

    def test_high(self):
        assert _risk_from_score(60) == WindowRisk.HIGH
        assert _risk_from_score(79.9) == WindowRisk.HIGH

    def test_critical(self):
        assert _risk_from_score(80) == WindowRisk.CRITICAL
        assert _risk_from_score(100) == WindowRisk.CRITICAL


# ---------------------------------------------------------------------------
# Tests: _graph_health_penalty
# ---------------------------------------------------------------------------


class TestGraphHealthPenalty:
    def test_all_healthy(self):
        g = _graph(_comp("a", "A"), _comp("b", "B"))
        assert _graph_health_penalty(g) == 0.0

    def test_one_degraded(self):
        g = _graph(_comp("a", "A", health=HealthStatus.DEGRADED))
        assert _graph_health_penalty(g) == 3.0

    def test_one_overloaded(self):
        g = _graph(_comp("a", "A", health=HealthStatus.OVERLOADED))
        assert _graph_health_penalty(g) == 6.0

    def test_one_down(self):
        g = _graph(_comp("a", "A", health=HealthStatus.DOWN))
        assert _graph_health_penalty(g) == 10.0

    def test_mixed(self):
        g = _graph(
            _comp("a", "A", health=HealthStatus.DOWN),
            _comp("b", "B", health=HealthStatus.DEGRADED),
        )
        assert _graph_health_penalty(g) == 13.0

    def test_capped_at_30(self):
        comps = [_comp(f"c{i}", f"C{i}", health=HealthStatus.DOWN) for i in range(10)]
        g = _graph(*comps)
        assert _graph_health_penalty(g) == 30.0

    def test_empty_graph(self):
        g = _graph()
        assert _graph_health_penalty(g) == 0.0


# ---------------------------------------------------------------------------
# Tests: _spof_count
# ---------------------------------------------------------------------------


class TestSpofCount:
    def test_no_spofs(self):
        g = _graph(_comp("a", "A", replicas=2), _comp("b", "B", replicas=3))
        assert _spof_count(g) == 0

    def test_one_spof(self):
        g = _graph(_comp("a", "A", replicas=1), _comp("b", "B", replicas=2))
        assert _spof_count(g) == 1

    def test_dns_excluded(self):
        g = _graph(_comp("d", "DNS", ctype=ComponentType.DNS, replicas=1))
        assert _spof_count(g) == 0

    def test_multiple_spofs(self):
        g = _graph(
            _comp("a", "A", replicas=1),
            _comp("b", "B", replicas=1),
            _comp("c", "C", replicas=2),
        )
        assert _spof_count(g) == 2

    def test_empty(self):
        g = _graph()
        assert _spof_count(g) == 0


# ---------------------------------------------------------------------------
# Tests: _graph_complexity
# ---------------------------------------------------------------------------


class TestGraphComplexity:
    def test_small(self):
        g = _graph(_comp("a", "A"))
        assert _graph_complexity(g) == 1.0

    def test_three(self):
        g = _graph(*[_comp(f"c{i}", f"C{i}") for i in range(3)])
        assert _graph_complexity(g) == 1.0

    def test_medium(self):
        g = _graph(*[_comp(f"c{i}", f"C{i}") for i in range(5)])
        assert _graph_complexity(g) == 3.0

    def test_ten(self):
        g = _graph(*[_comp(f"c{i}", f"C{i}") for i in range(10)])
        assert _graph_complexity(g) == 3.0

    def test_large(self):
        g = _graph(*[_comp(f"c{i}", f"C{i}") for i in range(15)])
        assert _graph_complexity(g) == 5.0

    def test_very_large(self):
        g = _graph(*[_comp(f"c{i}", f"C{i}") for i in range(30)])
        assert _graph_complexity(g) == pytest.approx(5.5)


# ---------------------------------------------------------------------------
# Tests: _incident_penalty
# ---------------------------------------------------------------------------


class TestIncidentPenalty:
    def test_zero(self):
        assert _incident_penalty(0) == 0.0

    def test_one(self):
        assert _incident_penalty(1) == 8.0

    def test_two(self):
        assert _incident_penalty(2) == 8.0

    def test_three(self):
        assert _incident_penalty(3) == 15.0

    def test_five(self):
        assert _incident_penalty(5) == 15.0

    def test_many(self):
        assert _incident_penalty(10) == 25.0


# ---------------------------------------------------------------------------
# Tests: _window_span_hours
# ---------------------------------------------------------------------------


class TestWindowSpanHours:
    def test_normal(self):
        tw = TimeWindow(start_hour=10, end_hour=14, day_of_week=0)
        assert _window_span_hours(tw) == 4

    def test_single_hour(self):
        tw = TimeWindow(start_hour=10, end_hour=10, day_of_week=0)
        assert _window_span_hours(tw) == 1

    def test_wrap_around(self):
        tw = TimeWindow(start_hour=22, end_hour=2, day_of_week=0)
        assert _window_span_hours(tw) == 4

    def test_full_range(self):
        tw = TimeWindow(start_hour=0, end_hour=23, day_of_week=0)
        assert _window_span_hours(tw) == 23


# ---------------------------------------------------------------------------
# Tests: constants sanity
# ---------------------------------------------------------------------------


class TestConstants:
    def test_hourly_traffic_length(self):
        assert len(_HOURLY_TRAFFIC) == 24

    def test_day_multiplier_length(self):
        assert len(_DAY_MULTIPLIER) == 7

    def test_team_availability_length(self):
        assert len(_TEAM_AVAILABILITY) == 24

    def test_deploy_type_weight_completeness(self):
        for dt in DeploymentType:
            assert dt in _DEPLOY_TYPE_WEIGHT

    def test_deploy_duration_completeness(self):
        for dt in DeploymentType:
            assert dt in _DEPLOY_DURATION

    def test_traffic_values_non_negative(self):
        for v in _HOURLY_TRAFFIC:
            assert v >= 0

    def test_day_multiplier_non_negative(self):
        for v in _DAY_MULTIPLIER:
            assert v >= 0


# ---------------------------------------------------------------------------
# Tests: DeploymentWindowEngine.calculate_risk_score
# ---------------------------------------------------------------------------


class TestCalculateRiskScore:
    def setup_method(self):
        self.engine = DeploymentWindowEngine()
        self.g = _graph(
            _comp("lb", "LB", ctype=ComponentType.LOAD_BALANCER, replicas=2),
            _comp("api", "API", replicas=3),
            _comp("db", "DB", ctype=ComponentType.DATABASE, replicas=2),
            deps=[("lb", "api"), ("api", "db")],
        )

    def test_returns_float(self):
        tw = TimeWindow(start_hour=10, end_hour=11, day_of_week=1)
        score = self.engine.calculate_risk_score(self.g, tw, DeploymentType.CONFIG_UPDATE)
        assert isinstance(score, float)

    def test_score_bounded(self):
        for h in range(24):
            for d in range(7):
                tw = TimeWindow(start_hour=h, end_hour=(h + 1) % 24, day_of_week=d)
                score = self.engine.calculate_risk_score(self.g, tw, DeploymentType.FEATURE_RELEASE)
                assert 0 <= score <= 100

    def test_off_peak_lower_than_peak(self):
        off = TimeWindow(start_hour=3, end_hour=4, day_of_week=1)
        peak = TimeWindow(start_hour=16, end_hour=17, day_of_week=1)
        s_off = self.engine.calculate_risk_score(self.g, off, DeploymentType.FEATURE_RELEASE)
        s_peak = self.engine.calculate_risk_score(self.g, peak, DeploymentType.FEATURE_RELEASE)
        assert s_off < s_peak

    def test_config_update_lower_than_db_migration(self):
        tw = TimeWindow(start_hour=10, end_hour=11, day_of_week=1)
        s_cfg = self.engine.calculate_risk_score(self.g, tw, DeploymentType.CONFIG_UPDATE)
        s_db = self.engine.calculate_risk_score(self.g, tw, DeploymentType.DATABASE_MIGRATION)
        assert s_cfg < s_db

    def test_weekend_different_from_weekday(self):
        wd = TimeWindow(start_hour=14, end_hour=15, day_of_week=2)
        we = TimeWindow(start_hour=14, end_hour=15, day_of_week=6)
        s_wd = self.engine.calculate_risk_score(self.g, wd, DeploymentType.FEATURE_RELEASE)
        s_we = self.engine.calculate_risk_score(self.g, we, DeploymentType.FEATURE_RELEASE)
        assert s_wd != s_we

    def test_unhealthy_graph_higher_score(self):
        healthy = _graph(_comp("a", "A", replicas=2))
        unhealthy = _graph(_comp("a", "A", replicas=2, health=HealthStatus.DOWN))
        tw = TimeWindow(start_hour=10, end_hour=11, day_of_week=1)
        s_h = self.engine.calculate_risk_score(healthy, tw, DeploymentType.FEATURE_RELEASE)
        s_u = self.engine.calculate_risk_score(unhealthy, tw, DeploymentType.FEATURE_RELEASE)
        assert s_u > s_h

    def test_spof_increases_score(self):
        no_spof = _graph(_comp("a", "A", replicas=2))
        with_spof = _graph(_comp("a", "A", replicas=1))
        tw = TimeWindow(start_hour=10, end_hour=11, day_of_week=1)
        s_ns = self.engine.calculate_risk_score(no_spof, tw, DeploymentType.FEATURE_RELEASE)
        s_ws = self.engine.calculate_risk_score(with_spof, tw, DeploymentType.FEATURE_RELEASE)
        assert s_ws > s_ns

    def test_empty_graph(self):
        g = _graph()
        tw = TimeWindow(start_hour=10, end_hour=11, day_of_week=1)
        score = self.engine.calculate_risk_score(g, tw, DeploymentType.CONFIG_UPDATE)
        assert 0 <= score <= 100

    def test_hotfix_lower_weight_than_infra_change(self):
        tw = TimeWindow(start_hour=10, end_hour=11, day_of_week=1)
        s_hf = self.engine.calculate_risk_score(self.g, tw, DeploymentType.HOTFIX)
        s_ic = self.engine.calculate_risk_score(self.g, tw, DeploymentType.INFRASTRUCTURE_CHANGE)
        assert s_hf < s_ic

    def test_rollback_lower_weight(self):
        tw = TimeWindow(start_hour=10, end_hour=11, day_of_week=1)
        s_rb = self.engine.calculate_risk_score(self.g, tw, DeploymentType.ROLLBACK)
        s_fr = self.engine.calculate_risk_score(self.g, tw, DeploymentType.FEATURE_RELEASE)
        assert s_rb < s_fr


# ---------------------------------------------------------------------------
# Tests: check_change_freeze
# ---------------------------------------------------------------------------


class TestCheckChangeFreeze:
    def setup_method(self):
        self.engine = DeploymentWindowEngine()

    def test_no_freeze(self):
        tw = TimeWindow(start_hour=10, end_hour=11, day_of_week=1)
        assert self.engine.check_change_freeze(tw, []) is False

    def test_overlapping_freeze(self):
        tw = TimeWindow(start_hour=10, end_hour=12, day_of_week=1)
        freeze = TimeWindow(start_hour=11, end_hour=13, day_of_week=1)
        assert self.engine.check_change_freeze(tw, [freeze]) is True

    def test_non_overlapping_freeze(self):
        tw = TimeWindow(start_hour=10, end_hour=12, day_of_week=1)
        freeze = TimeWindow(start_hour=14, end_hour=16, day_of_week=1)
        assert self.engine.check_change_freeze(tw, [freeze]) is False

    def test_different_day(self):
        tw = TimeWindow(start_hour=10, end_hour=12, day_of_week=1)
        freeze = TimeWindow(start_hour=10, end_hour=12, day_of_week=2)
        assert self.engine.check_change_freeze(tw, [freeze]) is False

    def test_exact_overlap(self):
        tw = TimeWindow(start_hour=10, end_hour=12, day_of_week=3)
        freeze = TimeWindow(start_hour=10, end_hour=12, day_of_week=3)
        assert self.engine.check_change_freeze(tw, [freeze]) is True

    def test_multiple_freezes_one_matches(self):
        tw = TimeWindow(start_hour=10, end_hour=12, day_of_week=1)
        f1 = TimeWindow(start_hour=14, end_hour=16, day_of_week=1)
        f2 = TimeWindow(start_hour=11, end_hour=13, day_of_week=1)
        assert self.engine.check_change_freeze(tw, [f1, f2]) is True

    def test_wrap_around_freeze(self):
        tw = TimeWindow(start_hour=23, end_hour=1, day_of_week=4)
        freeze = TimeWindow(start_hour=22, end_hour=2, day_of_week=4)
        assert self.engine.check_change_freeze(tw, [freeze]) is True

    def test_single_hour_window(self):
        tw = TimeWindow(start_hour=10, end_hour=10, day_of_week=0)
        freeze = TimeWindow(start_hour=9, end_hour=11, day_of_week=0)
        assert self.engine.check_change_freeze(tw, [freeze]) is True

    def test_single_hour_no_overlap(self):
        tw = TimeWindow(start_hour=10, end_hour=10, day_of_week=0)
        freeze = TimeWindow(start_hour=11, end_hour=13, day_of_week=0)
        assert self.engine.check_change_freeze(tw, [freeze]) is False


# ---------------------------------------------------------------------------
# Tests: assess_window
# ---------------------------------------------------------------------------


class TestAssessWindow:
    def setup_method(self):
        self.engine = DeploymentWindowEngine()
        self.g = _graph(
            _comp("api", "API", replicas=3),
            _comp("db", "DB", ctype=ComponentType.DATABASE, replicas=2),
            deps=[("api", "db")],
        )

    def test_returns_assessment(self):
        tw = TimeWindow(start_hour=10, end_hour=11, day_of_week=1)
        a = self.engine.assess_window(self.g, tw, DeploymentType.CONFIG_UPDATE)
        assert isinstance(a, WindowAssessment)

    def test_low_risk_window(self):
        tw = TimeWindow(start_hour=3, end_hour=4, day_of_week=1)
        g = _graph(_comp("a", "A", replicas=2))
        a = self.engine.assess_window(g, tw, DeploymentType.CONFIG_UPDATE)
        assert a.risk in (WindowRisk.LOW, WindowRisk.MODERATE)
        assert a.risk_score < 40

    def test_high_risk_provides_alternative(self):
        # Create a high-risk scenario: peak traffic, many SPOFs, unhealthy.
        g = _graph(
            _comp("a", "A", replicas=1, health=HealthStatus.DOWN),
            _comp("b", "B", replicas=1, health=HealthStatus.DOWN),
            _comp("c", "C", replicas=1, health=HealthStatus.OVERLOADED),
        )
        tw = TimeWindow(start_hour=16, end_hour=17, day_of_week=0)
        a = self.engine.assess_window(
            g, tw, DeploymentType.DATABASE_MIGRATION, recent_incidents_24h=5,
        )
        assert a.risk in (WindowRisk.HIGH, WindowRisk.CRITICAL)
        assert a.optimal_alternative is not None

    def test_freeze_boosts_score(self):
        tw = TimeWindow(start_hour=10, end_hour=11, day_of_week=1)
        freeze = TimeWindow(start_hour=9, end_hour=12, day_of_week=1)
        no_freeze = self.engine.assess_window(self.g, tw, DeploymentType.FEATURE_RELEASE)
        with_freeze = self.engine.assess_window(
            self.g, tw, DeploymentType.FEATURE_RELEASE, freeze_windows=[freeze],
        )
        assert with_freeze.risk_score > no_freeze.risk_score

    def test_incidents_boost_score(self):
        tw = TimeWindow(start_hour=10, end_hour=11, day_of_week=1)
        no_inc = self.engine.assess_window(self.g, tw, DeploymentType.FEATURE_RELEASE)
        with_inc = self.engine.assess_window(
            self.g, tw, DeploymentType.FEATURE_RELEASE, recent_incidents_24h=3,
        )
        assert with_inc.risk_score > no_inc.risk_score

    def test_traffic_level_populated(self):
        tw = TimeWindow(start_hour=16, end_hour=17, day_of_week=0)
        a = self.engine.assess_window(self.g, tw, DeploymentType.FEATURE_RELEASE)
        assert a.traffic_level in ("very_low", "low", "moderate", "high", "peak")

    def test_team_availability_populated(self):
        tw = TimeWindow(start_hour=10, end_hour=11, day_of_week=1)
        a = self.engine.assess_window(self.g, tw, DeploymentType.FEATURE_RELEASE)
        assert 0 <= a.team_availability <= 1

    def test_change_freeze_flag(self):
        tw = TimeWindow(start_hour=10, end_hour=11, day_of_week=1)
        a = self.engine.assess_window(self.g, tw, DeploymentType.FEATURE_RELEASE)
        assert a.change_freeze_active is False

    def test_recommendations_non_empty_for_risky(self):
        g = _graph(
            _comp("a", "A", replicas=1, health=HealthStatus.DOWN),
        )
        tw = TimeWindow(start_hour=16, end_hour=17, day_of_week=0)
        a = self.engine.assess_window(
            g, tw, DeploymentType.DATABASE_MIGRATION, recent_incidents_24h=2,
        )
        assert len(a.recommendations) > 0

    def test_favorable_recommendation(self):
        g = _graph(_comp("a", "A", replicas=2))
        tw = TimeWindow(start_hour=3, end_hour=4, day_of_week=1)
        a = self.engine.assess_window(g, tw, DeploymentType.CONFIG_UPDATE)
        if a.risk == WindowRisk.LOW:
            assert any("favorable" in r for r in a.recommendations)

    def test_score_capped_at_100(self):
        g = _graph(
            *[_comp(f"c{i}", f"C{i}", replicas=1, health=HealthStatus.DOWN) for i in range(5)],
        )
        tw = TimeWindow(start_hour=16, end_hour=17, day_of_week=0)
        a = self.engine.assess_window(
            g, tw, DeploymentType.DATABASE_MIGRATION,
            recent_incidents_24h=10,
            freeze_windows=[TimeWindow(start_hour=15, end_hour=18, day_of_week=0)],
        )
        assert a.risk_score <= 100.0


# ---------------------------------------------------------------------------
# Tests: find_optimal_window
# ---------------------------------------------------------------------------


class TestFindOptimalWindow:
    def setup_method(self):
        self.engine = DeploymentWindowEngine()
        self.g = _graph(
            _comp("api", "API", replicas=3),
            _comp("db", "DB", ctype=ComponentType.DATABASE, replicas=2),
        )

    def test_returns_time_window(self):
        tw = self.engine.find_optimal_window(self.g, DeploymentType.FEATURE_RELEASE)
        assert isinstance(tw, TimeWindow)

    def test_optimal_is_weekday(self):
        tw = self.engine.find_optimal_window(self.g, DeploymentType.FEATURE_RELEASE)
        assert tw.day_of_week <= 4

    def test_optimal_risk_is_low(self):
        tw = self.engine.find_optimal_window(self.g, DeploymentType.CONFIG_UPDATE)
        score = self.engine.calculate_risk_score(self.g, tw, DeploymentType.CONFIG_UPDATE)
        assert score < 40

    def test_custom_allowed_days(self):
        tw = self.engine.find_optimal_window(
            self.g, DeploymentType.FEATURE_RELEASE,
            constraints={"allowed_days": [5, 6]},
        )
        assert tw.day_of_week in (5, 6)

    def test_min_availability_constraint(self):
        tw = self.engine.find_optimal_window(
            self.g, DeploymentType.FEATURE_RELEASE,
            constraints={"min_availability": 0.8},
        )
        avail = _team_avail(tw.start_hour, tw.day_of_week)
        assert avail >= 0.8

    def test_max_traffic_constraint(self):
        tw = self.engine.find_optimal_window(
            self.g, DeploymentType.FEATURE_RELEASE,
            constraints={"max_traffic": 0.2},
        )
        traffic = _traffic_level_for(tw.start_hour, tw.day_of_week)
        assert traffic <= 0.2

    def test_default_constraints(self):
        tw = self.engine.find_optimal_window(self.g, DeploymentType.FEATURE_RELEASE)
        avail = _team_avail(tw.start_hour, tw.day_of_week)
        traffic = _traffic_level_for(tw.start_hour, tw.day_of_week)
        assert avail >= 0.3
        assert traffic <= 0.8

    def test_empty_graph(self):
        g = _graph()
        tw = self.engine.find_optimal_window(g, DeploymentType.CONFIG_UPDATE)
        assert isinstance(tw, TimeWindow)

    def test_no_constraints(self):
        tw = self.engine.find_optimal_window(self.g, DeploymentType.FEATURE_RELEASE, constraints={})
        assert isinstance(tw, TimeWindow)

    def test_empty_allowed_days_fallback(self):
        """When allowed_days is empty, the absolute fallback is returned."""
        tw = self.engine.find_optimal_window(
            self.g, DeploymentType.FEATURE_RELEASE,
            constraints={"allowed_days": []},
        )
        assert isinstance(tw, TimeWindow)
        # Falls through to absolute fallback with day_of_week=1.
        assert tw.day_of_week == 1
        assert tw.start_hour == 10


# ---------------------------------------------------------------------------
# Tests: estimate_rollback_window
# ---------------------------------------------------------------------------


class TestEstimateRollbackWindow:
    def setup_method(self):
        self.engine = DeploymentWindowEngine()

    def test_returns_float(self):
        g = _graph(_comp("a", "A"))
        result = self.engine.estimate_rollback_window(g, DeploymentType.FEATURE_RELEASE)
        assert isinstance(result, float)

    def test_positive_duration(self):
        g = _graph(_comp("a", "A"))
        result = self.engine.estimate_rollback_window(g, DeploymentType.FEATURE_RELEASE)
        assert result > 0

    def test_failover_increases_window(self):
        no_fo = _graph(_comp("a", "A", failover=False))
        with_fo = _graph(_comp("a", "A", failover=True))
        r_no = self.engine.estimate_rollback_window(no_fo, DeploymentType.FEATURE_RELEASE)
        r_fo = self.engine.estimate_rollback_window(with_fo, DeploymentType.FEATURE_RELEASE)
        assert r_fo > r_no

    def test_empty_graph(self):
        g = _graph()
        result = self.engine.estimate_rollback_window(g, DeploymentType.FEATURE_RELEASE)
        assert result == _DEPLOY_DURATION[DeploymentType.FEATURE_RELEASE]

    def test_db_migration_longer(self):
        g = _graph(_comp("a", "A"))
        r_cfg = self.engine.estimate_rollback_window(g, DeploymentType.CONFIG_UPDATE)
        r_db = self.engine.estimate_rollback_window(g, DeploymentType.DATABASE_MIGRATION)
        assert r_db > r_cfg

    def test_hotfix_shorter_than_feature(self):
        g = _graph(_comp("a", "A"))
        r_hf = self.engine.estimate_rollback_window(g, DeploymentType.HOTFIX)
        r_fr = self.engine.estimate_rollback_window(g, DeploymentType.FEATURE_RELEASE)
        assert r_hf < r_fr

    def test_complex_graph_shorter_window(self):
        simple = _graph(_comp("a", "A"))
        complex_g = _graph(*[_comp(f"c{i}", f"C{i}") for i in range(15)])
        r_s = self.engine.estimate_rollback_window(simple, DeploymentType.FEATURE_RELEASE)
        r_c = self.engine.estimate_rollback_window(complex_g, DeploymentType.FEATURE_RELEASE)
        assert r_c < r_s  # complexity penalty reduces rollback window

    def test_all_failover_benefit(self):
        g = _graph(_comp("a", "A", failover=True), _comp("b", "B", failover=True))
        result = self.engine.estimate_rollback_window(g, DeploymentType.FEATURE_RELEASE)
        base = _DEPLOY_DURATION[DeploymentType.FEATURE_RELEASE]
        assert result > base  # failover benefit should increase


# ---------------------------------------------------------------------------
# Tests: simulate_deploy_during_peak
# ---------------------------------------------------------------------------


class TestSimulateDeployDuringPeak:
    def setup_method(self):
        self.engine = DeploymentWindowEngine()

    def test_returns_result(self):
        g = _graph(_comp("a", "A", replicas=2))
        r = self.engine.simulate_deploy_during_peak(g, DeploymentType.FEATURE_RELEASE)
        assert isinstance(r, PeakDeployResult)

    def test_empty_graph_safe(self):
        g = _graph()
        r = self.engine.simulate_deploy_during_peak(g, DeploymentType.CONFIG_UPDATE)
        assert r.safe_to_deploy is True
        assert r.estimated_error_rate_increase == 0.0
        assert r.capacity_headroom_percent == 100.0
        assert r.warnings == []

    def test_healthy_graph_metrics(self):
        g = _graph(_comp("a", "A", replicas=3), _comp("b", "B", replicas=2))
        r = self.engine.simulate_deploy_during_peak(g, DeploymentType.CONFIG_UPDATE)
        assert r.estimated_error_rate_increase >= 0
        assert r.estimated_latency_increase_ms >= 0
        assert 0 <= r.affected_users_percent <= 100
        assert 0 <= r.rollback_risk <= 100

    def test_unhealthy_graph_warnings(self):
        g = _graph(
            _comp("a", "A", replicas=1, health=HealthStatus.DOWN),
            _comp("b", "B", replicas=1, health=HealthStatus.DOWN),
        )
        r = self.engine.simulate_deploy_during_peak(g, DeploymentType.FEATURE_RELEASE)
        assert len(r.warnings) > 0
        assert any("Unhealthy" in w for w in r.warnings)

    def test_db_migration_warning(self):
        g = _graph(_comp("db", "DB", ctype=ComponentType.DATABASE, replicas=2))
        r = self.engine.simulate_deploy_during_peak(g, DeploymentType.DATABASE_MIGRATION)
        assert any("Database" in w for w in r.warnings)

    def test_spof_warning(self):
        g = _graph(_comp("a", "A", replicas=1))
        r = self.engine.simulate_deploy_during_peak(g, DeploymentType.FEATURE_RELEASE)
        assert any("Single" in w or "single" in w.lower() for w in r.warnings)

    def test_high_utilization_reduces_headroom(self):
        g = _graph(_comp("a", "A", replicas=2, cpu=90.0))
        r = self.engine.simulate_deploy_during_peak(g, DeploymentType.FEATURE_RELEASE)
        assert r.capacity_headroom_percent < 50

    def test_safe_false_for_risky(self):
        g = _graph(
            _comp("a", "A", replicas=1, health=HealthStatus.DOWN),
            _comp("b", "B", replicas=1, health=HealthStatus.DOWN),
            _comp("c", "C", replicas=1, health=HealthStatus.DOWN),
        )
        r = self.engine.simulate_deploy_during_peak(g, DeploymentType.DATABASE_MIGRATION)
        assert r.safe_to_deploy is False

    def test_rollback_risk_bounded(self):
        g = _graph(
            *[_comp(f"c{i}", f"C{i}", replicas=1, health=HealthStatus.DOWN) for i in range(5)],
        )
        r = self.engine.simulate_deploy_during_peak(g, DeploymentType.DATABASE_MIGRATION)
        assert r.rollback_risk <= 100


# ---------------------------------------------------------------------------
# Tests: recommend_deployment_schedule
# ---------------------------------------------------------------------------


class TestRecommendDeploymentSchedule:
    def setup_method(self):
        self.engine = DeploymentWindowEngine()
        self.g = _graph(
            _comp("api", "API", replicas=3),
            _comp("db", "DB", ctype=ComponentType.DATABASE, replicas=2),
            deps=[("api", "db")],
        )

    def test_empty_list(self):
        result = self.engine.recommend_deployment_schedule(self.g, [])
        assert result == []

    def test_single_deploy(self):
        result = self.engine.recommend_deployment_schedule(
            self.g, [DeploymentType.CONFIG_UPDATE],
        )
        assert len(result) == 1
        assert result[0].deploy_type == DeploymentType.CONFIG_UPDATE
        assert result[0].priority == 1

    def test_multiple_deploys_sorted_by_risk(self):
        result = self.engine.recommend_deployment_schedule(
            self.g,
            [DeploymentType.DATABASE_MIGRATION, DeploymentType.CONFIG_UPDATE, DeploymentType.HOTFIX],
        )
        assert len(result) == 3
        # Lower risk should come first (lower priority number).
        scores = [s.risk_score for s in result]
        assert scores == sorted(scores)

    def test_priorities_sequential(self):
        result = self.engine.recommend_deployment_schedule(
            self.g,
            [DeploymentType.FEATURE_RELEASE, DeploymentType.HOTFIX],
        )
        priorities = [s.priority for s in result]
        assert priorities == [1, 2]

    def test_no_slot_collision(self):
        result = self.engine.recommend_deployment_schedule(
            self.g,
            [DeploymentType.FEATURE_RELEASE, DeploymentType.HOTFIX, DeploymentType.CONFIG_UPDATE],
        )
        slots = [(s.recommended_window.day_of_week, s.recommended_window.start_hour) for s in result]
        assert len(set(slots)) == len(slots)

    def test_db_migration_note(self):
        result = self.engine.recommend_deployment_schedule(
            self.g, [DeploymentType.DATABASE_MIGRATION],
        )
        assert any("backup" in n.lower() or "Backup" in n for n in result[0].notes)

    def test_spof_note(self):
        g = _graph(_comp("a", "A", replicas=1))
        result = self.engine.recommend_deployment_schedule(
            g, [DeploymentType.FEATURE_RELEASE],
        )
        assert any("SPOF" in n or "spof" in n.lower() for n in result[0].notes)

    def test_duration_matches_type(self):
        result = self.engine.recommend_deployment_schedule(
            self.g, [DeploymentType.HOTFIX],
        )
        assert result[0].estimated_duration_minutes == _DEPLOY_DURATION[DeploymentType.HOTFIX]

    def test_returns_scheduled_deploy_type(self):
        result = self.engine.recommend_deployment_schedule(
            self.g, [DeploymentType.ROLLBACK],
        )
        assert isinstance(result[0], ScheduledDeploy)

    def test_high_risk_gets_note(self):
        g = _graph(
            *[_comp(f"c{i}", f"C{i}", replicas=1, health=HealthStatus.DOWN) for i in range(5)],
        )
        result = self.engine.recommend_deployment_schedule(
            g, [DeploymentType.DATABASE_MIGRATION],
        )
        assert any("additional review" in n.lower() or "postpone" in n.lower() for n in result[0].notes)


# ---------------------------------------------------------------------------
# Tests: _hour_set (via engine static method)
# ---------------------------------------------------------------------------


class TestHourSet:
    def setup_method(self):
        self.engine = DeploymentWindowEngine()

    def test_normal_range(self):
        tw = TimeWindow(start_hour=10, end_hour=14, day_of_week=0)
        assert self.engine._hour_set(tw) == {10, 11, 12, 13}

    def test_single_hour(self):
        tw = TimeWindow(start_hour=10, end_hour=10, day_of_week=0)
        assert self.engine._hour_set(tw) == {10}

    def test_wrap_around(self):
        tw = TimeWindow(start_hour=22, end_hour=2, day_of_week=0)
        assert self.engine._hour_set(tw) == {22, 23, 0, 1}

    def test_full_day_minus_one(self):
        tw = TimeWindow(start_hour=0, end_hour=23, day_of_week=0)
        assert len(self.engine._hour_set(tw)) == 23


# ---------------------------------------------------------------------------
# Tests: _find_free_slot
# ---------------------------------------------------------------------------


class TestFindFreeSlot:
    def setup_method(self):
        self.engine = DeploymentWindowEngine()
        self.g = _graph(_comp("a", "A"))

    def test_preferred_free(self):
        tw = TimeWindow(start_hour=10, end_hour=11, day_of_week=1)
        result = self.engine._find_free_slot(tw, set(), self.g, DeploymentType.FEATURE_RELEASE)
        assert result.start_hour == 10
        assert result.day_of_week == 1

    def test_preferred_taken(self):
        tw = TimeWindow(start_hour=10, end_hour=11, day_of_week=1)
        used = {(1, 10)}
        result = self.engine._find_free_slot(tw, used, self.g, DeploymentType.FEATURE_RELEASE)
        assert result.start_hour == 11
        assert result.day_of_week == 1

    def test_multiple_taken(self):
        tw = TimeWindow(start_hour=10, end_hour=11, day_of_week=1)
        used = {(1, 10), (1, 11), (1, 12)}
        result = self.engine._find_free_slot(tw, used, self.g, DeploymentType.FEATURE_RELEASE)
        assert result.start_hour == 13

    def test_all_hours_taken_wraps_day(self):
        tw = TimeWindow(start_hour=10, end_hour=11, day_of_week=1)
        used = {(1, h) for h in range(24)}
        result = self.engine._find_free_slot(tw, used, self.g, DeploymentType.FEATURE_RELEASE)
        assert result.day_of_week == 2


# ---------------------------------------------------------------------------
# Tests: _build_recommendations
# ---------------------------------------------------------------------------


class TestBuildRecommendations:
    def test_freeze_active(self):
        g = _graph(_comp("a", "A", replicas=2))
        recs = DeploymentWindowEngine._build_recommendations(
            WindowRisk.ELEVATED, 0.5, 0.9, True, 0, DeploymentType.FEATURE_RELEASE, g,
        )
        assert any("freeze" in r.lower() for r in recs)

    def test_peak_traffic(self):
        g = _graph(_comp("a", "A", replicas=2))
        recs = DeploymentWindowEngine._build_recommendations(
            WindowRisk.ELEVATED, 0.85, 0.9, False, 0, DeploymentType.FEATURE_RELEASE, g,
        )
        assert any("peak" in r.lower() for r in recs)

    def test_low_availability(self):
        g = _graph(_comp("a", "A", replicas=2))
        recs = DeploymentWindowEngine._build_recommendations(
            WindowRisk.ELEVATED, 0.5, 0.2, False, 0, DeploymentType.FEATURE_RELEASE, g,
        )
        assert any("availability" in r.lower() for r in recs)

    def test_incidents(self):
        g = _graph(_comp("a", "A", replicas=2))
        recs = DeploymentWindowEngine._build_recommendations(
            WindowRisk.ELEVATED, 0.5, 0.9, False, 3, DeploymentType.FEATURE_RELEASE, g,
        )
        assert any("incident" in r.lower() for r in recs)

    def test_high_risk(self):
        g = _graph(_comp("a", "A", replicas=2))
        recs = DeploymentWindowEngine._build_recommendations(
            WindowRisk.HIGH, 0.5, 0.9, False, 0, DeploymentType.FEATURE_RELEASE, g,
        )
        assert any("approval" in r.lower() for r in recs)

    def test_critical_risk(self):
        g = _graph(_comp("a", "A", replicas=2))
        recs = DeploymentWindowEngine._build_recommendations(
            WindowRisk.CRITICAL, 0.5, 0.9, False, 0, DeploymentType.FEATURE_RELEASE, g,
        )
        assert any("approval" in r.lower() for r in recs)

    def test_db_migration(self):
        g = _graph(_comp("a", "A", replicas=2))
        recs = DeploymentWindowEngine._build_recommendations(
            WindowRisk.MODERATE, 0.5, 0.9, False, 0, DeploymentType.DATABASE_MIGRATION, g,
        )
        assert any("backup" in r.lower() for r in recs)

    def test_infra_change(self):
        g = _graph(_comp("a", "A", replicas=2))
        recs = DeploymentWindowEngine._build_recommendations(
            WindowRisk.MODERATE, 0.5, 0.9, False, 0, DeploymentType.INFRASTRUCTURE_CHANGE, g,
        )
        assert any("rollback" in r.lower() for r in recs)

    def test_spof(self):
        g = _graph(_comp("a", "A", replicas=1))
        recs = DeploymentWindowEngine._build_recommendations(
            WindowRisk.MODERATE, 0.5, 0.9, False, 0, DeploymentType.FEATURE_RELEASE, g,
        )
        assert any("single" in r.lower() or "spof" in r.lower() for r in recs)

    def test_unhealthy(self):
        g = _graph(
            _comp("a", "A", replicas=2, health=HealthStatus.DOWN),
            _comp("b", "B", replicas=2, health=HealthStatus.DOWN),
        )
        recs = DeploymentWindowEngine._build_recommendations(
            WindowRisk.HIGH, 0.5, 0.9, False, 0, DeploymentType.FEATURE_RELEASE, g,
        )
        assert any("unhealthy" in r.lower() for r in recs)

    def test_favorable(self):
        g = _graph(_comp("a", "A", replicas=2))
        recs = DeploymentWindowEngine._build_recommendations(
            WindowRisk.LOW, 0.3, 0.9, False, 0, DeploymentType.CONFIG_UPDATE, g,
        )
        assert any("favorable" in r.lower() for r in recs)

    def test_not_favorable_with_freeze(self):
        g = _graph(_comp("a", "A", replicas=2))
        recs = DeploymentWindowEngine._build_recommendations(
            WindowRisk.LOW, 0.3, 0.9, True, 0, DeploymentType.CONFIG_UPDATE, g,
        )
        # Should not say favorable when freeze is active.
        assert not any("favorable" in r.lower() and "freeze" not in r.lower() for r in recs) or \
               any("freeze" in r.lower() for r in recs)

    def test_not_favorable_with_incidents(self):
        g = _graph(_comp("a", "A", replicas=2))
        recs = DeploymentWindowEngine._build_recommendations(
            WindowRisk.LOW, 0.3, 0.9, False, 2, DeploymentType.CONFIG_UPDATE, g,
        )
        # Should not say favorable when incidents > 0.
        assert not any(r == "Conditions are favorable for deployment" for r in recs)


# ---------------------------------------------------------------------------
# Tests: integration / end-to-end
# ---------------------------------------------------------------------------


class TestIntegration:
    def setup_method(self):
        self.engine = DeploymentWindowEngine()

    def test_full_workflow(self):
        g = _graph(
            _comp("lb", "LB", ctype=ComponentType.LOAD_BALANCER, replicas=2),
            _comp("api", "API", replicas=3),
            _comp("db", "DB", ctype=ComponentType.DATABASE, replicas=2),
            deps=[("lb", "api"), ("api", "db")],
        )
        tw = TimeWindow(start_hour=10, end_hour=11, day_of_week=2)
        assessment = self.engine.assess_window(g, tw, DeploymentType.FEATURE_RELEASE)
        assert isinstance(assessment, WindowAssessment)

        optimal = self.engine.find_optimal_window(g, DeploymentType.FEATURE_RELEASE)
        assert isinstance(optimal, TimeWindow)

        rollback = self.engine.estimate_rollback_window(g, DeploymentType.FEATURE_RELEASE)
        assert rollback > 0

        peak = self.engine.simulate_deploy_during_peak(g, DeploymentType.FEATURE_RELEASE)
        assert isinstance(peak, PeakDeployResult)

        schedule = self.engine.recommend_deployment_schedule(
            g, [DeploymentType.CONFIG_UPDATE, DeploymentType.FEATURE_RELEASE],
        )
        assert len(schedule) == 2

    def test_all_deploy_types(self):
        g = _graph(_comp("a", "A", replicas=2))
        tw = TimeWindow(start_hour=10, end_hour=11, day_of_week=1)
        for dt in DeploymentType:
            score = self.engine.calculate_risk_score(g, tw, dt)
            assert 0 <= score <= 100
            a = self.engine.assess_window(g, tw, dt)
            assert isinstance(a, WindowAssessment)

    def test_all_hours_all_days(self):
        g = _graph(_comp("a", "A", replicas=2))
        for d in range(7):
            for h in range(24):
                tw = TimeWindow(start_hour=h, end_hour=(h + 1) % 24, day_of_week=d)
                score = self.engine.calculate_risk_score(g, tw, DeploymentType.FEATURE_RELEASE)
                assert 0 <= score <= 100

    def test_stateless_engine(self):
        g = _graph(_comp("a", "A", replicas=2))
        tw = TimeWindow(start_hour=10, end_hour=11, day_of_week=1)
        e1 = DeploymentWindowEngine()
        e2 = DeploymentWindowEngine()
        s1 = e1.calculate_risk_score(g, tw, DeploymentType.FEATURE_RELEASE)
        s2 = e2.calculate_risk_score(g, tw, DeploymentType.FEATURE_RELEASE)
        assert s1 == s2

    def test_large_graph(self):
        comps = [_comp(f"c{i}", f"C{i}") for i in range(50)]
        g = _graph(*comps)
        tw = TimeWindow(start_hour=10, end_hour=11, day_of_week=1)
        score = self.engine.calculate_risk_score(g, tw, DeploymentType.FEATURE_RELEASE)
        assert 0 <= score <= 100

    def test_graph_with_all_health_states(self):
        g = _graph(
            _comp("h", "Healthy", replicas=2, health=HealthStatus.HEALTHY),
            _comp("d", "Degraded", replicas=2, health=HealthStatus.DEGRADED),
            _comp("o", "Overloaded", replicas=2, health=HealthStatus.OVERLOADED),
            _comp("x", "Down", replicas=2, health=HealthStatus.DOWN),
        )
        tw = TimeWindow(start_hour=10, end_hour=11, day_of_week=1)
        a = self.engine.assess_window(g, tw, DeploymentType.FEATURE_RELEASE)
        assert a.risk_score > 0

    def test_schedule_all_types(self):
        g = _graph(_comp("a", "A", replicas=2))
        schedule = self.engine.recommend_deployment_schedule(g, list(DeploymentType))
        assert len(schedule) == len(DeploymentType)
        # All priorities should be unique.
        priorities = [s.priority for s in schedule]
        assert len(set(priorities)) == len(priorities)

    def test_peak_simulation_consistency(self):
        g = _graph(_comp("a", "A", replicas=2))
        r1 = self.engine.simulate_deploy_during_peak(g, DeploymentType.FEATURE_RELEASE)
        r2 = self.engine.simulate_deploy_during_peak(g, DeploymentType.FEATURE_RELEASE)
        assert r1.estimated_error_rate_increase == r2.estimated_error_rate_increase
        assert r1.safe_to_deploy == r2.safe_to_deploy
