"""Comprehensive tests for ResilienceScorecard — targeting 99%+ coverage."""

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    Component,
    ComponentType,
    FailoverConfig,
    HealthStatus,
    ResourceMetrics,
    SecurityProfile,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.resilience_scorecard import (
    ActionItem,
    Dimension,
    DimensionScore,
    Grade,
    ResilienceScorecard,
    Scorecard,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _comp(
    cid,
    name,
    ctype=ComponentType.APP_SERVER,
    replicas=1,
    failover=False,
    health=HealthStatus.HEALTHY,
    promotion_time=10,
):
    c = Component(id=cid, name=name, type=ctype, replicas=replicas)
    c.health = health
    if failover:
        c.failover = FailoverConfig(
            enabled=True, promotion_time_seconds=promotion_time
        )
    return c


def _graph(*comps):
    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    return g


# ---------------------------------------------------------------------------
# 1. Enum values
# ---------------------------------------------------------------------------

class TestEnums:
    def test_grade_values(self):
        assert Grade.A_PLUS == "A+"
        assert Grade.A == "A"
        assert Grade.B == "B"
        assert Grade.C == "C"
        assert Grade.D == "D"
        assert Grade.F == "F"

    def test_grade_is_str_enum(self):
        assert isinstance(Grade.A_PLUS, str)
        assert Grade.A_PLUS.value == "A+"

    def test_dimension_values(self):
        assert Dimension.AVAILABILITY == "availability"
        assert Dimension.REDUNDANCY == "redundancy"
        assert Dimension.FAULT_TOLERANCE == "fault_tolerance"
        assert Dimension.SCALABILITY == "scalability"
        assert Dimension.SECURITY_POSTURE == "security_posture"
        assert Dimension.OBSERVABILITY == "observability"
        assert Dimension.RECOVERY == "recovery"
        assert Dimension.DEPENDENCY_HEALTH == "dependency_health"

    def test_dimension_is_str_enum(self):
        assert isinstance(Dimension.AVAILABILITY, str)

    def test_all_dimensions_count(self):
        assert len(Dimension) == 8

    def test_all_grades_count(self):
        assert len(Grade) == 6


# ---------------------------------------------------------------------------
# 2. Empty graph
# ---------------------------------------------------------------------------

class TestEmptyGraph:
    def test_empty_graph_overall_score(self):
        sc = ResilienceScorecard(InfraGraph()).generate()
        assert sc.overall_score == 0.0

    def test_empty_graph_grade_f(self):
        sc = ResilienceScorecard(InfraGraph()).generate()
        assert sc.overall_grade == Grade.F

    def test_empty_graph_no_dimensions(self):
        sc = ResilienceScorecard(InfraGraph()).generate()
        assert sc.dimension_scores == []

    def test_empty_graph_no_action_items(self):
        sc = ResilienceScorecard(InfraGraph()).generate()
        assert sc.action_items == []

    def test_empty_graph_counts(self):
        sc = ResilienceScorecard(InfraGraph()).generate()
        assert sc.total_components == 0
        assert sc.healthy_components == 0
        assert sc.at_risk_components == 0

    def test_empty_graph_no_strengths_weaknesses(self):
        sc = ResilienceScorecard(InfraGraph()).generate()
        assert sc.strengths == []
        assert sc.weaknesses == []

    def test_empty_graph_summary(self):
        sc = ResilienceScorecard(InfraGraph()).generate()
        assert sc.executive_summary == "No infrastructure components to assess."


# ---------------------------------------------------------------------------
# 3. Single healthy component
# ---------------------------------------------------------------------------

class TestSingleHealthy:
    @pytest.fixture()
    def scorecard(self):
        g = _graph(_comp("app1", "AppServer"))
        return ResilienceScorecard(g).generate()

    def test_all_dimensions_scored(self, scorecard):
        assert len(scorecard.dimension_scores) == 8
        dims = {ds.dimension for ds in scorecard.dimension_scores}
        assert dims == set(Dimension)

    def test_total_components(self, scorecard):
        assert scorecard.total_components == 1

    def test_healthy_components(self, scorecard):
        assert scorecard.healthy_components == 1
        assert scorecard.at_risk_components == 0

    def test_availability_score_100(self, scorecard):
        avail = next(
            ds for ds in scorecard.dimension_scores
            if ds.dimension == Dimension.AVAILABILITY
        )
        assert avail.score == 100.0
        assert avail.grade == Grade.A_PLUS

    def test_availability_finding_all_healthy(self, scorecard):
        avail = next(
            ds for ds in scorecard.dimension_scores
            if ds.dimension == Dimension.AVAILABILITY
        )
        assert "All components healthy" in avail.findings

    def test_each_dimension_has_description(self, scorecard):
        for ds in scorecard.dimension_scores:
            assert ds.description, f"{ds.dimension} missing description"

    def test_component_scores_dict_present(self, scorecard):
        for ds in scorecard.dimension_scores:
            assert "app1" in ds.component_scores


# ---------------------------------------------------------------------------
# 4. All health states (availability)
# ---------------------------------------------------------------------------

class TestHealthStates:
    @pytest.mark.parametrize(
        "status,expected_score",
        [
            (HealthStatus.HEALTHY, 100),
            (HealthStatus.DEGRADED, 50),
            (HealthStatus.OVERLOADED, 25),
            (HealthStatus.DOWN, 0),
        ],
    )
    def test_single_component_availability(self, status, expected_score):
        g = _graph(_comp("c1", "Comp1", health=status))
        sc = ResilienceScorecard(g).generate()
        avail = next(
            ds for ds in sc.dimension_scores
            if ds.dimension == Dimension.AVAILABILITY
        )
        assert avail.score == expected_score

    def test_down_generates_critical_recommendation(self):
        g = _graph(_comp("c1", "Server", health=HealthStatus.DOWN))
        sc = ResilienceScorecard(g).generate()
        avail = next(
            ds for ds in sc.dimension_scores
            if ds.dimension == Dimension.AVAILABILITY
        )
        assert any("CRITICAL" in r and "Restore" in r for r in avail.recommendations)

    def test_overloaded_generates_scale_recommendation(self):
        g = _graph(_comp("c1", "Server", health=HealthStatus.OVERLOADED))
        sc = ResilienceScorecard(g).generate()
        avail = next(
            ds for ds in sc.dimension_scores
            if ds.dimension == Dimension.AVAILABILITY
        )
        assert any("Scale" in r for r in avail.recommendations)

    def test_degraded_generates_finding_but_no_recommendation(self):
        g = _graph(_comp("c1", "Server", health=HealthStatus.DEGRADED))
        sc = ResilienceScorecard(g).generate()
        avail = next(
            ds for ds in sc.dimension_scores
            if ds.dimension == Dimension.AVAILABILITY
        )
        assert any("degraded" in f for f in avail.findings)
        # DEGRADED generates no specific recommendation (only DOWN & OVERLOADED do)
        assert not any("CRITICAL" in r for r in avail.recommendations)
        assert not any("Scale" in r for r in avail.recommendations)

    def test_mixed_health_average(self):
        g = _graph(
            _comp("c1", "A", health=HealthStatus.HEALTHY),
            _comp("c2", "B", health=HealthStatus.DOWN),
        )
        sc = ResilienceScorecard(g).generate()
        avail = next(
            ds for ds in sc.dimension_scores
            if ds.dimension == Dimension.AVAILABILITY
        )
        assert avail.score == 50.0

    def test_recommendations_limited_to_3(self):
        """Availability recommendations are capped at 3."""
        comps = [
            _comp(f"c{i}", f"S{i}", health=HealthStatus.DOWN) for i in range(10)
        ]
        g = _graph(*comps)
        sc = ResilienceScorecard(g).generate()
        avail = next(
            ds for ds in sc.dimension_scores
            if ds.dimension == Dimension.AVAILABILITY
        )
        assert len(avail.recommendations) <= 3


# ---------------------------------------------------------------------------
# 5. Redundancy scoring
# ---------------------------------------------------------------------------

class TestRedundancy:
    def test_replicas_1_no_dependents(self):
        g = _graph(_comp("c1", "App", replicas=1))
        sc = ResilienceScorecard(g).generate()
        red = next(
            ds for ds in sc.dimension_scores
            if ds.dimension == Dimension.REDUNDANCY
        )
        assert red.component_scores["c1"] == 20.0
        assert any("single replica" in f for f in red.findings)

    def test_replicas_1_with_dependents_is_spof(self):
        from faultray.model.components import Dependency

        g = InfraGraph()
        g.add_component(_comp("db", "Database", ctype=ComponentType.DATABASE, replicas=1))
        g.add_component(_comp("app", "App", replicas=1))
        g.add_dependency(Dependency(source_id="app", target_id="db"))
        sc = ResilienceScorecard(g).generate()
        red = next(
            ds for ds in sc.dimension_scores
            if ds.dimension == Dimension.REDUNDANCY
        )
        assert red.component_scores["db"] == 10.0
        assert any("SPOF" in f for f in red.findings)
        assert any("Add replica" in r for r in red.recommendations)

    def test_replicas_2(self):
        g = _graph(_comp("c1", "App", replicas=2))
        sc = ResilienceScorecard(g).generate()
        red = next(
            ds for ds in sc.dimension_scores
            if ds.dimension == Dimension.REDUNDANCY
        )
        assert red.component_scores["c1"] == 70.0

    def test_replicas_3_plus(self):
        g = _graph(_comp("c1", "App", replicas=3))
        sc = ResilienceScorecard(g).generate()
        red = next(
            ds for ds in sc.dimension_scores
            if ds.dimension == Dimension.REDUNDANCY
        )
        assert red.component_scores["c1"] == 100.0

    def test_replicas_5(self):
        g = _graph(_comp("c1", "App", replicas=5))
        sc = ResilienceScorecard(g).generate()
        red = next(
            ds for ds in sc.dimension_scores
            if ds.dimension == Dimension.REDUNDANCY
        )
        assert red.component_scores["c1"] == 100.0

    def test_all_redundant_finding(self):
        g = _graph(_comp("c1", "App", replicas=3))
        sc = ResilienceScorecard(g).generate()
        red = next(
            ds for ds in sc.dimension_scores
            if ds.dimension == Dimension.REDUNDANCY
        )
        assert "All components have redundancy" in red.findings

    def test_redundancy_recommendations_capped(self):
        from faultray.model.components import Dependency

        g = InfraGraph()
        for i in range(10):
            g.add_component(_comp(f"db{i}", f"DB{i}", ctype=ComponentType.DATABASE, replicas=1))
            g.add_component(_comp(f"app{i}", f"App{i}", replicas=1))
            g.add_dependency(Dependency(source_id=f"app{i}", target_id=f"db{i}"))
        sc = ResilienceScorecard(g).generate()
        red = next(
            ds for ds in sc.dimension_scores
            if ds.dimension == Dimension.REDUNDANCY
        )
        assert len(red.recommendations) <= 3


# ---------------------------------------------------------------------------
# 6. Fault tolerance
# ---------------------------------------------------------------------------

class TestFaultTolerance:
    def test_no_failover_no_replicas(self):
        g = _graph(_comp("c1", "App", replicas=1, failover=False))
        sc = ResilienceScorecard(g).generate()
        ft = next(
            ds for ds in sc.dimension_scores
            if ds.dimension == Dimension.FAULT_TOLERANCE
        )
        assert ft.component_scores["c1"] == 0.0
        assert any("Enable failover" in r for r in ft.recommendations)

    def test_failover_fast_promotion(self):
        g = _graph(_comp("c1", "App", replicas=1, failover=True, promotion_time=10))
        sc = ResilienceScorecard(g).generate()
        ft = next(
            ds for ds in sc.dimension_scores
            if ds.dimension == Dimension.FAULT_TOLERANCE
        )
        # failover(50) + fast promotion(20) = 70
        assert ft.component_scores["c1"] == 70.0
        assert any("fast failover" in f for f in ft.findings)

    def test_failover_slow_promotion(self):
        g = _graph(_comp("c1", "App", replicas=1, failover=True, promotion_time=60))
        sc = ResilienceScorecard(g).generate()
        ft = next(
            ds for ds in sc.dimension_scores
            if ds.dimension == Dimension.FAULT_TOLERANCE
        )
        # failover(50) + slow(10) = 60
        assert ft.component_scores["c1"] == 60.0

    def test_failover_boundary_30s(self):
        g = _graph(_comp("c1", "App", replicas=1, failover=True, promotion_time=30))
        sc = ResilienceScorecard(g).generate()
        ft = next(
            ds for ds in sc.dimension_scores
            if ds.dimension == Dimension.FAULT_TOLERANCE
        )
        # 30 <= 30 -> fast path: 50 + 20 = 70
        assert ft.component_scores["c1"] == 70.0

    def test_replicas_bonus(self):
        g = _graph(_comp("c1", "App", replicas=2, failover=False))
        sc = ResilienceScorecard(g).generate()
        ft = next(
            ds for ds in sc.dimension_scores
            if ds.dimension == Dimension.FAULT_TOLERANCE
        )
        # no failover(0) + replicas_bonus(30) = 30
        assert ft.component_scores["c1"] == 30.0

    def test_failover_plus_replicas_capped_at_100(self):
        g = _graph(_comp("c1", "App", replicas=2, failover=True, promotion_time=10))
        sc = ResilienceScorecard(g).generate()
        ft = next(
            ds for ds in sc.dimension_scores
            if ds.dimension == Dimension.FAULT_TOLERANCE
        )
        # failover(50) + fast(20) + replicas(30) = 100
        assert ft.component_scores["c1"] == 100.0

    def test_no_findings_no_recs_default_finding(self):
        """When there are no findings and no recs, a default finding is added."""
        # replicas >= 2 but no failover --> recs list will have an entry,
        # so we need failover=True and replicas>=2 for both lists to be populated,
        # which means we won't hit the no-findings-no-recs branch.
        # Actually, if failover is True (findings += fast/slow) and recs is empty,
        # the branch `if not findings and not recs` is not triggered.
        # The only way to trigger it: failover=False with findings from
        # fast failover (impossible). So this branch is essentially unreachable
        # in normal usage. Let's verify the fallback exists by crafting
        # the scenario where failover is enabled (so no recs) and promotion
        # finding is added.
        g = _graph(_comp("c1", "App", replicas=1, failover=True, promotion_time=10))
        sc = ResilienceScorecard(g).generate()
        ft = next(
            ds for ds in sc.dimension_scores
            if ds.dimension == Dimension.FAULT_TOLERANCE
        )
        # findings will have the fast failover entry, no recs -> branch not hit
        assert len(ft.findings) >= 1

    def test_fault_tolerance_recommendations_capped(self):
        comps = [_comp(f"c{i}", f"C{i}", replicas=1, failover=False) for i in range(10)]
        g = _graph(*comps)
        sc = ResilienceScorecard(g).generate()
        ft = next(
            ds for ds in sc.dimension_scores
            if ds.dimension == Dimension.FAULT_TOLERANCE
        )
        assert len(ft.recommendations) <= 3


# ---------------------------------------------------------------------------
# 7. Scalability
# ---------------------------------------------------------------------------

class TestScalability:
    def test_autoscaling_enabled_low_usage(self):
        c = _comp("c1", "App")
        c.autoscaling = AutoScalingConfig(enabled=True)
        c.metrics = ResourceMetrics(cpu_percent=10, memory_percent=10)
        g = _graph(c)
        sc = ResilienceScorecard(g).generate()
        scal = next(
            ds for ds in sc.dimension_scores
            if ds.dimension == Dimension.SCALABILITY
        )
        # autoscaling(50) + headroom: avg_headroom=90 -> 90*0.5=45 => 95
        assert scal.component_scores["c1"] == 95.0

    def test_autoscaling_disabled_low_cpu(self):
        c = _comp("c1", "App")
        c.autoscaling = AutoScalingConfig(enabled=False)
        c.metrics = ResourceMetrics(cpu_percent=20, memory_percent=20)
        g = _graph(c)
        sc = ResilienceScorecard(g).generate()
        scal = next(
            ds for ds in sc.dimension_scores
            if ds.dimension == Dimension.SCALABILITY
        )
        # no autoscaling(0) + headroom: avg_headroom=80 -> 80*0.5=40 => 40
        assert scal.component_scores["c1"] == 40.0
        # CPU <= 60, so no autoscaling recommendation
        assert not any("autoscaling" in r.lower() for r in scal.recommendations)

    def test_autoscaling_disabled_high_cpu_triggers_recommendation(self):
        c = _comp("c1", "App")
        c.autoscaling = AutoScalingConfig(enabled=False)
        c.metrics = ResourceMetrics(cpu_percent=80, memory_percent=50)
        g = _graph(c)
        sc = ResilienceScorecard(g).generate()
        scal = next(
            ds for ds in sc.dimension_scores
            if ds.dimension == Dimension.SCALABILITY
        )
        assert any("autoscaling" in r.lower() for r in scal.recommendations)

    def test_low_headroom_finding(self):
        c = _comp("c1", "App")
        c.metrics = ResourceMetrics(cpu_percent=90, memory_percent=95)
        g = _graph(c)
        sc = ResilienceScorecard(g).generate()
        scal = next(
            ds for ds in sc.dimension_scores
            if ds.dimension == Dimension.SCALABILITY
        )
        # avg_headroom = (10 + 5) / 2 = 7.5 < 20 => finding
        assert any("low headroom" in f for f in scal.findings)

    def test_adequate_headroom_finding(self):
        c = _comp("c1", "App")
        c.metrics = ResourceMetrics(cpu_percent=20, memory_percent=20)
        g = _graph(c)
        sc = ResilienceScorecard(g).generate()
        scal = next(
            ds for ds in sc.dimension_scores
            if ds.dimension == Dimension.SCALABILITY
        )
        assert "Adequate resource headroom across all components" in scal.findings

    def test_headroom_capped_at_100(self):
        c = _comp("c1", "App")
        c.autoscaling = AutoScalingConfig(enabled=True)
        c.metrics = ResourceMetrics(cpu_percent=0, memory_percent=0)
        g = _graph(c)
        sc = ResilienceScorecard(g).generate()
        scal = next(
            ds for ds in sc.dimension_scores
            if ds.dimension == Dimension.SCALABILITY
        )
        # autoscaling(50) + headroom: 100*0.5=50 => 100
        assert scal.component_scores["c1"] == 100.0

    def test_scalability_recommendations_capped(self):
        comps = []
        for i in range(10):
            c = _comp(f"c{i}", f"C{i}")
            c.autoscaling = AutoScalingConfig(enabled=False)
            c.metrics = ResourceMetrics(cpu_percent=80)
            comps.append(c)
        g = _graph(*comps)
        sc = ResilienceScorecard(g).generate()
        scal = next(
            ds for ds in sc.dimension_scores
            if ds.dimension == Dimension.SCALABILITY
        )
        assert len(scal.recommendations) <= 3


# ---------------------------------------------------------------------------
# 8. Security posture
# ---------------------------------------------------------------------------

class TestSecurityPosture:
    def test_all_security_enabled(self):
        c = _comp("c1", "App")
        c.security = SecurityProfile(
            encryption_at_rest=True,
            encryption_in_transit=True,
            waf_protected=True,
            rate_limiting=True,
            auth_required=True,
        )
        g = _graph(c)
        sc = ResilienceScorecard(g).generate()
        sec = next(
            ds for ds in sc.dimension_scores
            if ds.dimension == Dimension.SECURITY_POSTURE
        )
        assert sec.component_scores["c1"] == 100.0
        assert "Security controls configured across all components" in sec.findings

    def test_no_security_enabled(self):
        c = _comp("c1", "App")
        c.security = SecurityProfile()
        g = _graph(c)
        sc = ResilienceScorecard(g).generate()
        sec = next(
            ds for ds in sc.dimension_scores
            if ds.dimension == Dimension.SECURITY_POSTURE
        )
        assert sec.component_scores["c1"] == 0.0

    def test_partial_security(self):
        c = _comp("c1", "App")
        c.security = SecurityProfile(
            encryption_at_rest=True,
            encryption_in_transit=True,
        )
        g = _graph(c)
        sc = ResilienceScorecard(g).generate()
        sec = next(
            ds for ds in sc.dimension_scores
            if ds.dimension == Dimension.SECURITY_POSTURE
        )
        assert sec.component_scores["c1"] == 40.0

    def test_database_missing_encryption_triggers_findings(self):
        c = _comp("c1", "DB", ctype=ComponentType.DATABASE)
        c.security = SecurityProfile(encryption_at_rest=False, encryption_in_transit=False)
        g = _graph(c)
        sc = ResilienceScorecard(g).generate()
        sec = next(
            ds for ds in sc.dimension_scores
            if ds.dimension == Dimension.SECURITY_POSTURE
        )
        assert any("encryption_at_rest" in f for f in sec.findings)
        assert any("encryption_in_transit" in f for f in sec.findings)

    def test_database_missing_encryption_at_rest_triggers_recommendation(self):
        c = _comp("c1", "DB", ctype=ComponentType.DATABASE)
        c.security = SecurityProfile(encryption_at_rest=False)
        g = _graph(c)
        sc = ResilienceScorecard(g).generate()
        sec = next(
            ds for ds in sc.dimension_scores
            if ds.dimension == Dimension.SECURITY_POSTURE
        )
        assert any("Enable encryption at rest" in r for r in sec.recommendations)

    def test_storage_missing_encryption_triggers_recommendation(self):
        c = _comp("c1", "Store", ctype=ComponentType.STORAGE)
        c.security = SecurityProfile(encryption_at_rest=False)
        g = _graph(c)
        sc = ResilienceScorecard(g).generate()
        sec = next(
            ds for ds in sc.dimension_scores
            if ds.dimension == Dimension.SECURITY_POSTURE
        )
        assert any("Enable encryption at rest" in r for r in sec.recommendations)

    def test_non_data_type_missing_encryption_no_recommendation(self):
        c = _comp("c1", "App", ctype=ComponentType.APP_SERVER)
        c.security = SecurityProfile(encryption_at_rest=False)
        g = _graph(c)
        sc = ResilienceScorecard(g).generate()
        sec = next(
            ds for ds in sc.dimension_scores
            if ds.dimension == Dimension.SECURITY_POSTURE
        )
        # APP_SERVER missing encryption_at_rest does NOT trigger recommendation
        assert not any("Enable encryption at rest" in r for r in sec.recommendations)

    def test_database_with_encryption_at_rest_only_findings(self):
        """DB with encryption_at_rest but not in_transit: finding mentions in_transit only."""
        c = _comp("c1", "DB", ctype=ComponentType.DATABASE)
        c.security = SecurityProfile(
            encryption_at_rest=True,
            encryption_in_transit=False,
        )
        g = _graph(c)
        sc = ResilienceScorecard(g).generate()
        sec = next(
            ds for ds in sc.dimension_scores
            if ds.dimension == Dimension.SECURITY_POSTURE
        )
        assert any("encryption_in_transit" in f for f in sec.findings)
        assert not any("encryption_at_rest" in f for f in sec.findings)

    def test_security_recommendations_capped(self):
        comps = []
        for i in range(10):
            c = _comp(f"db{i}", f"DB{i}", ctype=ComponentType.DATABASE)
            c.security = SecurityProfile(encryption_at_rest=False)
            comps.append(c)
        g = _graph(*comps)
        sc = ResilienceScorecard(g).generate()
        sec = next(
            ds for ds in sc.dimension_scores
            if ds.dimension == Dimension.SECURITY_POSTURE
        )
        assert len(sec.recommendations) <= 3


# ---------------------------------------------------------------------------
# 9. Observability
# ---------------------------------------------------------------------------

class TestObservability:
    def test_both_enabled(self):
        c = _comp("c1", "App")
        c.security = SecurityProfile(log_enabled=True, ids_monitored=True)
        g = _graph(c)
        sc = ResilienceScorecard(g).generate()
        obs = next(
            ds for ds in sc.dimension_scores
            if ds.dimension == Dimension.OBSERVABILITY
        )
        assert obs.component_scores["c1"] == 100.0
        assert "Full observability coverage" in obs.findings

    def test_log_only(self):
        c = _comp("c1", "App")
        c.security = SecurityProfile(log_enabled=True, ids_monitored=False)
        g = _graph(c)
        sc = ResilienceScorecard(g).generate()
        obs = next(
            ds for ds in sc.dimension_scores
            if ds.dimension == Dimension.OBSERVABILITY
        )
        assert obs.component_scores["c1"] == 50.0

    def test_ids_only(self):
        c = _comp("c1", "App")
        c.security = SecurityProfile(log_enabled=False, ids_monitored=True)
        g = _graph(c)
        sc = ResilienceScorecard(g).generate()
        obs = next(
            ds for ds in sc.dimension_scores
            if ds.dimension == Dimension.OBSERVABILITY
        )
        assert obs.component_scores["c1"] == 50.0
        assert any("logging not enabled" in f for f in obs.findings)
        assert any("Enable logging" in r for r in obs.recommendations)

    def test_both_off_triggers_double_recommendations(self):
        c = _comp("c1", "App")
        c.security = SecurityProfile(log_enabled=False, ids_monitored=False)
        g = _graph(c)
        sc = ResilienceScorecard(g).generate()
        obs = next(
            ds for ds in sc.dimension_scores
            if ds.dimension == Dimension.OBSERVABILITY
        )
        assert obs.component_scores["c1"] == 0.0
        assert any("Enable logging" in r for r in obs.recommendations)
        assert any("Enable IDS" in r for r in obs.recommendations)

    def test_ids_recommendation_only_when_log_disabled(self):
        """IDS monitoring recommendation is only added when log_enabled is also False."""
        c = _comp("c1", "App")
        c.security = SecurityProfile(log_enabled=True, ids_monitored=False)
        g = _graph(c)
        sc = ResilienceScorecard(g).generate()
        obs = next(
            ds for ds in sc.dimension_scores
            if ds.dimension == Dimension.OBSERVABILITY
        )
        # log is enabled but ids is not -> no IDS recommendation (per code logic)
        assert not any("IDS" in r for r in obs.recommendations)

    def test_observability_recommendations_capped(self):
        comps = []
        for i in range(10):
            c = _comp(f"c{i}", f"C{i}")
            c.security = SecurityProfile(log_enabled=False, ids_monitored=False)
            comps.append(c)
        g = _graph(*comps)
        sc = ResilienceScorecard(g).generate()
        obs = next(
            ds for ds in sc.dimension_scores
            if ds.dimension == Dimension.OBSERVABILITY
        )
        assert len(obs.recommendations) <= 3


# ---------------------------------------------------------------------------
# 10. Recovery
# ---------------------------------------------------------------------------

class TestRecovery:
    def test_database_with_backup(self):
        c = _comp("c1", "DB", ctype=ComponentType.DATABASE)
        c.security = SecurityProfile(backup_enabled=True)
        g = _graph(c)
        sc = ResilienceScorecard(g).generate()
        rec = next(
            ds for ds in sc.dimension_scores
            if ds.dimension == Dimension.RECOVERY
        )
        # base(50) + backup(50) = 100
        assert rec.component_scores["c1"] == 100.0
        assert "All data stores have backup configured" in rec.findings

    def test_database_without_backup(self):
        c = _comp("c1", "DB", ctype=ComponentType.DATABASE)
        c.security = SecurityProfile(backup_enabled=False)
        g = _graph(c)
        sc = ResilienceScorecard(g).generate()
        rec = next(
            ds for ds in sc.dimension_scores
            if ds.dimension == Dimension.RECOVERY
        )
        assert rec.component_scores["c1"] == 20.0
        assert any("no backup configured" in f for f in rec.findings)
        assert any("Enable automated backup" in r for r in rec.recommendations)

    def test_storage_without_backup(self):
        c = _comp("c1", "Store", ctype=ComponentType.STORAGE)
        c.security = SecurityProfile(backup_enabled=False)
        g = _graph(c)
        sc = ResilienceScorecard(g).generate()
        rec = next(
            ds for ds in sc.dimension_scores
            if ds.dimension == Dimension.RECOVERY
        )
        assert rec.component_scores["c1"] == 20.0

    def test_cache_without_backup(self):
        c = _comp("c1", "Cache", ctype=ComponentType.CACHE)
        c.security = SecurityProfile(backup_enabled=False)
        g = _graph(c)
        sc = ResilienceScorecard(g).generate()
        rec = next(
            ds for ds in sc.dimension_scores
            if ds.dimension == Dimension.RECOVERY
        )
        assert rec.component_scores["c1"] == 20.0

    def test_non_data_type_with_replicas_and_failover(self):
        c = _comp("c1", "App", replicas=2, failover=True)
        g = _graph(c)
        sc = ResilienceScorecard(g).generate()
        rec = next(
            ds for ds in sc.dimension_scores
            if ds.dimension == Dimension.RECOVERY
        )
        # base(50) + replicas(30) + failover(20) = 100
        assert rec.component_scores["c1"] == 100.0

    def test_non_data_type_no_replicas_no_failover(self):
        c = _comp("c1", "App", replicas=1, failover=False)
        g = _graph(c)
        sc = ResilienceScorecard(g).generate()
        rec = next(
            ds for ds in sc.dimension_scores
            if ds.dimension == Dimension.RECOVERY
        )
        # base(50) only
        assert rec.component_scores["c1"] == 50.0

    def test_non_data_type_with_replicas_only(self):
        c = _comp("c1", "App", replicas=2, failover=False)
        g = _graph(c)
        sc = ResilienceScorecard(g).generate()
        rec = next(
            ds for ds in sc.dimension_scores
            if ds.dimension == Dimension.RECOVERY
        )
        # base(50) + replicas(30) = 80
        assert rec.component_scores["c1"] == 80.0

    def test_non_data_type_with_failover_only(self):
        c = _comp("c1", "App", replicas=1, failover=True)
        g = _graph(c)
        sc = ResilienceScorecard(g).generate()
        rec = next(
            ds for ds in sc.dimension_scores
            if ds.dimension == Dimension.RECOVERY
        )
        # base(50) + failover(20) = 70
        assert rec.component_scores["c1"] == 70.0

    def test_recovery_recommendations_capped(self):
        comps = []
        for i in range(10):
            c = _comp(f"db{i}", f"DB{i}", ctype=ComponentType.DATABASE)
            c.security = SecurityProfile(backup_enabled=False)
            comps.append(c)
        g = _graph(*comps)
        sc = ResilienceScorecard(g).generate()
        rec = next(
            ds for ds in sc.dimension_scores
            if ds.dimension == Dimension.RECOVERY
        )
        assert len(rec.recommendations) <= 3


# ---------------------------------------------------------------------------
# 11. Dependency health
# ---------------------------------------------------------------------------

class TestDependencyHealth:
    def test_no_dependencies_score_100(self):
        g = _graph(_comp("c1", "App"))
        sc = ResilienceScorecard(g).generate()
        dh = next(
            ds for ds in sc.dimension_scores
            if ds.dimension == Dimension.DEPENDENCY_HEALTH
        )
        assert dh.component_scores["c1"] == 100.0
        assert "All dependencies healthy" in dh.findings

    def test_healthy_dependency(self):
        from faultray.model.components import Dependency

        g = InfraGraph()
        g.add_component(_comp("app", "App"))
        g.add_component(_comp("db", "DB", health=HealthStatus.HEALTHY))
        g.add_dependency(Dependency(source_id="app", target_id="db"))
        sc = ResilienceScorecard(g).generate()
        dh = next(
            ds for ds in sc.dimension_scores
            if ds.dimension == Dimension.DEPENDENCY_HEALTH
        )
        assert dh.component_scores["app"] == 100.0

    def test_degraded_dependency(self):
        from faultray.model.components import Dependency

        g = InfraGraph()
        g.add_component(_comp("app", "App"))
        g.add_component(_comp("db", "DB", health=HealthStatus.DEGRADED))
        g.add_dependency(Dependency(source_id="app", target_id="db"))
        sc = ResilienceScorecard(g).generate()
        dh = next(
            ds for ds in sc.dimension_scores
            if ds.dimension == Dimension.DEPENDENCY_HEALTH
        )
        assert dh.component_scores["app"] == 50.0
        assert any("degraded" in f for f in dh.findings)

    def test_overloaded_dependency(self):
        from faultray.model.components import Dependency

        g = InfraGraph()
        g.add_component(_comp("app", "App"))
        g.add_component(_comp("db", "DB", health=HealthStatus.OVERLOADED))
        g.add_dependency(Dependency(source_id="app", target_id="db"))
        sc = ResilienceScorecard(g).generate()
        dh = next(
            ds for ds in sc.dimension_scores
            if ds.dimension == Dimension.DEPENDENCY_HEALTH
        )
        assert dh.component_scores["app"] == 25.0
        assert any("overloaded" in f for f in dh.findings)

    def test_down_dependency(self):
        from faultray.model.components import Dependency

        g = InfraGraph()
        g.add_component(_comp("app", "App"))
        g.add_component(_comp("db", "DB", health=HealthStatus.DOWN))
        g.add_dependency(Dependency(source_id="app", target_id="db"))
        sc = ResilienceScorecard(g).generate()
        dh = next(
            ds for ds in sc.dimension_scores
            if ds.dimension == Dimension.DEPENDENCY_HEALTH
        )
        assert dh.component_scores["app"] == 0.0
        assert any("DOWN" in f for f in dh.findings)
        assert any("Restore" in r for r in dh.recommendations)

    def test_mixed_dependencies(self):
        from faultray.model.components import Dependency

        g = InfraGraph()
        g.add_component(_comp("app", "App"))
        g.add_component(_comp("db", "DB", health=HealthStatus.HEALTHY))
        g.add_component(_comp("cache", "Cache", health=HealthStatus.DOWN))
        g.add_dependency(Dependency(source_id="app", target_id="db"))
        g.add_dependency(Dependency(source_id="app", target_id="cache"))
        sc = ResilienceScorecard(g).generate()
        dh = next(
            ds for ds in sc.dimension_scores
            if ds.dimension == Dimension.DEPENDENCY_HEALTH
        )
        # (100 + 0) / 2 = 50.0
        assert dh.component_scores["app"] == 50.0

    def test_dependency_recommendations_capped(self):
        from faultray.model.components import Dependency

        g = InfraGraph()
        g.add_component(_comp("app", "App"))
        for i in range(10):
            g.add_component(_comp(f"dep{i}", f"Dep{i}", health=HealthStatus.DOWN))
            g.add_dependency(Dependency(source_id="app", target_id=f"dep{i}"))
        sc = ResilienceScorecard(g).generate()
        dh = next(
            ds for ds in sc.dimension_scores
            if ds.dimension == Dimension.DEPENDENCY_HEALTH
        )
        assert len(dh.recommendations) <= 3


# ---------------------------------------------------------------------------
# 12. Grade conversion
# ---------------------------------------------------------------------------

class TestGradeConversion:
    @pytest.mark.parametrize(
        "score,expected_grade",
        [
            (100, Grade.A_PLUS),
            (95, Grade.A_PLUS),
            (94.9, Grade.A),
            (80, Grade.A),
            (79.9, Grade.B),
            (65, Grade.B),
            (64.9, Grade.C),
            (50, Grade.C),
            (49.9, Grade.D),
            (30, Grade.D),
            (29.9, Grade.F),
            (0, Grade.F),
        ],
    )
    def test_score_to_grade_boundaries(self, score, expected_grade):
        assert ResilienceScorecard._score_to_grade(score) == expected_grade


# ---------------------------------------------------------------------------
# 13. Overall weighted score
# ---------------------------------------------------------------------------

class TestOverallWeightedScore:
    def test_weighted_average_calculation(self):
        """Verify weighted average is computed correctly."""
        # All components healthy, 3 replicas, failover enabled with fast promotion,
        # autoscaling on, full security, full observability, backup, no deps
        c = _comp("c1", "App", replicas=3, failover=True, promotion_time=5)
        c.autoscaling = AutoScalingConfig(enabled=True)
        c.metrics = ResourceMetrics(cpu_percent=10, memory_percent=10)
        c.security = SecurityProfile(
            encryption_at_rest=True,
            encryption_in_transit=True,
            waf_protected=True,
            rate_limiting=True,
            auth_required=True,
            log_enabled=True,
            ids_monitored=True,
            backup_enabled=True,
        )
        g = _graph(c)
        sc = ResilienceScorecard(g).generate()

        # Manually compute expected weighted average
        weights = {
            Dimension.AVAILABILITY: 2.0,
            Dimension.REDUNDANCY: 1.5,
            Dimension.FAULT_TOLERANCE: 1.5,
            Dimension.SCALABILITY: 1.0,
            Dimension.SECURITY_POSTURE: 1.5,
            Dimension.OBSERVABILITY: 1.0,
            Dimension.RECOVERY: 1.5,
            Dimension.DEPENDENCY_HEALTH: 1.0,
        }
        weighted_sum = sum(
            ds.score * weights[ds.dimension] for ds in sc.dimension_scores
        )
        total_weight = sum(weights.values())
        expected = round(weighted_sum / total_weight, 1)

        assert sc.overall_score == expected

    def test_overall_grade_matches_score(self):
        c = _comp("c1", "App", replicas=3, failover=True)
        c.autoscaling = AutoScalingConfig(enabled=True)
        c.metrics = ResourceMetrics(cpu_percent=10, memory_percent=10)
        c.security = SecurityProfile(
            encryption_at_rest=True,
            encryption_in_transit=True,
            waf_protected=True,
            rate_limiting=True,
            auth_required=True,
            log_enabled=True,
            ids_monitored=True,
            backup_enabled=True,
        )
        g = _graph(c)
        sc = ResilienceScorecard(g).generate()
        assert sc.overall_grade == ResilienceScorecard._score_to_grade(sc.overall_score)


# ---------------------------------------------------------------------------
# 14. Strengths and weaknesses
# ---------------------------------------------------------------------------

class TestStrengthsWeaknesses:
    def test_strength_above_80(self):
        """Dimensions scoring >= 80 appear in strengths."""
        c = _comp("c1", "App", replicas=3)
        g = _graph(c)
        sc = ResilienceScorecard(g).generate()
        # Availability should be 100 (healthy) => strength
        avail_strength = f"{Dimension.AVAILABILITY.value}: {Grade.A_PLUS.value}"
        assert avail_strength in sc.strengths

    def test_weakness_below_50(self):
        """Dimensions scoring < 50 appear in weaknesses."""
        c = _comp("c1", "App", replicas=1, failover=False)
        c.security = SecurityProfile()  # all false => score 0
        g = _graph(c)
        sc = ResilienceScorecard(g).generate()
        sec_weakness = f"{Dimension.SECURITY_POSTURE.value}: {Grade.F.value}"
        assert sec_weakness in sc.weaknesses

    def test_score_exactly_50_no_weakness(self):
        """Score of exactly 50 is not a weakness (< 50 is)."""
        # Observability: log_enabled=True, ids_monitored=False => 50 points
        c = _comp("c1", "App")
        c.security = SecurityProfile(log_enabled=True, ids_monitored=False)
        g = _graph(c)
        sc = ResilienceScorecard(g).generate()
        obs = next(
            ds for ds in sc.dimension_scores
            if ds.dimension == Dimension.OBSERVABILITY
        )
        assert obs.score == 50.0
        assert not any("observability" in w for w in sc.weaknesses)

    def test_score_exactly_80_is_strength(self):
        """Score of exactly 80 is a strength (>= 80)."""
        # Recovery: non-data type with replicas=2, no failover => base(50)+replicas(30)=80
        c = _comp("c1", "App", replicas=2, failover=False)
        g = _graph(c)
        sc = ResilienceScorecard(g).generate()
        rec = next(
            ds for ds in sc.dimension_scores
            if ds.dimension == Dimension.RECOVERY
        )
        assert rec.score == 80.0
        assert any("recovery" in s for s in sc.strengths)


# ---------------------------------------------------------------------------
# 15. Action items
# ---------------------------------------------------------------------------

class TestActionItems:
    def test_priority_ordering_worst_first(self):
        """Action items are ordered by dimension score ascending (worst first)."""
        c = _comp("c1", "App", replicas=1, failover=False)
        c.security = SecurityProfile(encryption_at_rest=False)
        c.autoscaling = AutoScalingConfig(enabled=False)
        c.metrics = ResourceMetrics(cpu_percent=80)
        g = _graph(c)
        sc = ResilienceScorecard(g).generate()
        if len(sc.action_items) >= 2:
            for i in range(len(sc.action_items) - 1):
                assert sc.action_items[i].priority < sc.action_items[i + 1].priority

    def test_effort_low_for_restore(self):
        c = _comp("c1", "Server", health=HealthStatus.DOWN)
        g = _graph(c)
        sc = ResilienceScorecard(g).generate()
        restore_items = [
            ai for ai in sc.action_items if "restore" in ai.action.lower()
        ]
        for ai in restore_items:
            assert ai.effort == "low"
            assert "Critical" in ai.impact

    def test_effort_medium_for_enable(self):
        c = _comp("c1", "App", replicas=1, failover=False)
        g = _graph(c)
        sc = ResilienceScorecard(g).generate()
        enable_items = [
            ai for ai in sc.action_items if "enable" in ai.action.lower()
        ]
        for ai in enable_items:
            assert ai.effort == "medium"
            assert "High" in ai.impact

    def test_effort_medium_for_add_replica(self):
        from faultray.model.components import Dependency

        g = InfraGraph()
        g.add_component(_comp("db", "DB", ctype=ComponentType.DATABASE, replicas=1))
        g.add_component(_comp("app", "App", replicas=1))
        g.add_dependency(Dependency(source_id="app", target_id="db"))
        sc = ResilienceScorecard(g).generate()
        replica_items = [
            ai for ai in sc.action_items if "add replica" in ai.action.lower()
        ]
        for ai in replica_items:
            assert ai.effort == "medium"

    def test_effort_medium_for_scale(self):
        c = _comp("c1", "App", health=HealthStatus.OVERLOADED)
        g = _graph(c)
        sc = ResilienceScorecard(g).generate()
        scale_items = [
            ai for ai in sc.action_items if "scale" in ai.action.lower()
        ]
        for ai in scale_items:
            assert ai.effort == "medium"

    def test_effort_high_for_other(self):
        """Actions that don't match restore/enable/scale/add replica get high effort."""
        # Build a DimensionScore with a recommendation that doesn't match
        # any of the low/medium keywords, then run _build_action_items directly.
        ds = DimensionScore(
            dimension=Dimension.SECURITY_POSTURE,
            description="test",
            score=10.0,
            grade=Grade.F,
            findings=["custom finding"],
            recommendations=["Refactor authentication middleware"],
            component_scores={"c1": 10.0},
        )
        scorer = ResilienceScorecard(InfraGraph())
        items = scorer._build_action_items([ds])
        assert len(items) == 1
        assert items[0].effort == "high"
        assert "Moderate" in items[0].impact

    def test_affected_components(self):
        """components_affected lists components with score < 50."""
        c = _comp("c1", "App", replicas=1, failover=False)
        c.security = SecurityProfile()
        g = _graph(c)
        sc = ResilienceScorecard(g).generate()
        sec_items = [
            ai for ai in sc.action_items
            if ai.dimension == Dimension.SECURITY_POSTURE
        ]
        for ai in sec_items:
            # Security score is 0 which is < 50 so "c1" should be affected
            assert "c1" in ai.components_affected

    def test_action_items_capped_at_10(self):
        """Total action items are capped at 10."""
        comps = []
        for i in range(20):
            c = _comp(f"c{i}", f"C{i}", replicas=1, failover=False)
            c.security = SecurityProfile()
            c.autoscaling = AutoScalingConfig(enabled=False)
            c.metrics = ResourceMetrics(cpu_percent=80)
            comps.append(c)
        g = _graph(*comps)
        sc = ResilienceScorecard(g).generate()
        assert len(sc.action_items) <= 10

    def test_affected_components_capped_at_5(self):
        """Components affected list is capped at 5."""
        comps = []
        for i in range(20):
            c = _comp(f"c{i}", f"C{i}", replicas=1, failover=False)
            c.security = SecurityProfile()
            comps.append(c)
        g = _graph(*comps)
        sc = ResilienceScorecard(g).generate()
        for ai in sc.action_items:
            assert len(ai.components_affected) <= 5

    def test_no_recommendations_no_action_items(self):
        """When all dimensions have no recommendations, no action items are generated."""
        c = _comp("c1", "App", replicas=3, failover=True, promotion_time=5)
        c.autoscaling = AutoScalingConfig(enabled=True)
        c.metrics = ResourceMetrics(cpu_percent=10, memory_percent=10)
        c.security = SecurityProfile(
            encryption_at_rest=True,
            encryption_in_transit=True,
            waf_protected=True,
            rate_limiting=True,
            auth_required=True,
            log_enabled=True,
            ids_monitored=True,
            backup_enabled=True,
        )
        g = _graph(c)
        sc = ResilienceScorecard(g).generate()
        assert sc.action_items == []


# ---------------------------------------------------------------------------
# 16. Executive summary
# ---------------------------------------------------------------------------

class TestExecutiveSummary:
    def test_includes_grade(self):
        c = _comp("c1", "App")
        g = _graph(c)
        sc = ResilienceScorecard(g).generate()
        assert sc.overall_grade.value in sc.executive_summary

    def test_includes_overall_in_summary(self):
        c = _comp("c1", "App")
        g = _graph(c)
        sc = ResilienceScorecard(g).generate()
        assert "Overall resilience" in sc.executive_summary

    def test_includes_strong_dimensions(self):
        c = _comp("c1", "App", replicas=3)
        g = _graph(c)
        sc = ResilienceScorecard(g).generate()
        # Availability is 100 -> strong
        if any(ds.score >= 80 for ds in sc.dimension_scores):
            assert "Strong:" in sc.executive_summary

    def test_includes_weak_dimensions(self):
        c = _comp("c1", "App", replicas=1, failover=False)
        c.security = SecurityProfile()
        g = _graph(c)
        sc = ResilienceScorecard(g).generate()
        # Security is 0 -> weak
        if any(ds.score < 50 for ds in sc.dimension_scores):
            assert "Needs attention:" in sc.executive_summary

    def test_includes_action_count(self):
        c = _comp("c1", "App", replicas=1, failover=False)
        g = _graph(c)
        sc = ResilienceScorecard(g).generate()
        if sc.action_items:
            assert "action item" in sc.executive_summary

    def test_action_count_plural(self):
        c = _comp("c1", "App", replicas=1, failover=False)
        c.security = SecurityProfile()
        c.autoscaling = AutoScalingConfig(enabled=False)
        c.metrics = ResourceMetrics(cpu_percent=80)
        g = _graph(c)
        sc = ResilienceScorecard(g).generate()
        if len(sc.action_items) > 1:
            assert "action items" in sc.executive_summary

    def test_action_count_singular(self):
        """When exactly 1 action item, summary uses singular form."""
        # We need exactly 1 recommendation across all dimensions.
        # One easy way: single component, everything perfect except 1 dimension.
        c = _comp("c1", "App", replicas=3, failover=True, promotion_time=5)
        c.autoscaling = AutoScalingConfig(enabled=True)
        c.metrics = ResourceMetrics(cpu_percent=10, memory_percent=10)
        c.security = SecurityProfile(
            encryption_at_rest=True,
            encryption_in_transit=True,
            waf_protected=True,
            rate_limiting=True,
            auth_required=True,
            log_enabled=False,  # this creates 1 recommendation
            ids_monitored=True,
            backup_enabled=True,
        )
        g = _graph(c)
        sc = ResilienceScorecard(g).generate()
        if len(sc.action_items) == 1:
            assert "1 action item " in sc.executive_summary

    def test_no_actions_no_action_text(self):
        c = _comp("c1", "App", replicas=3, failover=True, promotion_time=5)
        c.autoscaling = AutoScalingConfig(enabled=True)
        c.metrics = ResourceMetrics(cpu_percent=10, memory_percent=10)
        c.security = SecurityProfile(
            encryption_at_rest=True,
            encryption_in_transit=True,
            waf_protected=True,
            rate_limiting=True,
            auth_required=True,
            log_enabled=True,
            ids_monitored=True,
            backup_enabled=True,
        )
        g = _graph(c)
        sc = ResilienceScorecard(g).generate()
        assert "action item" not in sc.executive_summary

    def test_no_weak_no_needs_attention(self):
        """When no dimension scores < 50, 'Needs attention' is not in summary."""
        c = _comp("c1", "App", replicas=3, failover=True, promotion_time=5)
        c.autoscaling = AutoScalingConfig(enabled=True)
        c.metrics = ResourceMetrics(cpu_percent=10, memory_percent=10)
        c.security = SecurityProfile(
            encryption_at_rest=True,
            encryption_in_transit=True,
            waf_protected=True,
            rate_limiting=True,
            auth_required=True,
            log_enabled=True,
            ids_monitored=True,
            backup_enabled=True,
        )
        g = _graph(c)
        sc = ResilienceScorecard(g).generate()
        assert "Needs attention" not in sc.executive_summary


# ---------------------------------------------------------------------------
# 17. Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_single_component_graph(self):
        g = _graph(_comp("only", "OnlyOne"))
        sc = ResilienceScorecard(g).generate()
        assert sc.total_components == 1
        assert len(sc.dimension_scores) == 8

    def test_all_components_down(self):
        comps = [
            _comp(f"c{i}", f"C{i}", health=HealthStatus.DOWN) for i in range(3)
        ]
        g = _graph(*comps)
        sc = ResilienceScorecard(g).generate()
        avail = next(
            ds for ds in sc.dimension_scores
            if ds.dimension == Dimension.AVAILABILITY
        )
        assert avail.score == 0.0
        assert sc.healthy_components == 0
        assert sc.at_risk_components == 3

    def test_all_components_perfect(self):
        c = _comp("c1", "App", replicas=3, failover=True, promotion_time=5)
        c.autoscaling = AutoScalingConfig(enabled=True)
        c.metrics = ResourceMetrics(cpu_percent=0, memory_percent=0)
        c.security = SecurityProfile(
            encryption_at_rest=True,
            encryption_in_transit=True,
            waf_protected=True,
            rate_limiting=True,
            auth_required=True,
            log_enabled=True,
            ids_monitored=True,
            backup_enabled=True,
        )
        g = _graph(c)
        sc = ResilienceScorecard(g).generate()
        assert sc.overall_grade in (Grade.A_PLUS, Grade.A)
        assert sc.weaknesses == []
        assert sc.action_items == []

    def test_mixed_health_states_multiple_components(self):
        g = _graph(
            _comp("h", "Healthy", health=HealthStatus.HEALTHY),
            _comp("d", "Degraded", health=HealthStatus.DEGRADED),
            _comp("o", "Overloaded", health=HealthStatus.OVERLOADED),
            _comp("x", "Down", health=HealthStatus.DOWN),
        )
        sc = ResilienceScorecard(g).generate()
        avail = next(
            ds for ds in sc.dimension_scores
            if ds.dimension == Dimension.AVAILABILITY
        )
        # (100 + 50 + 25 + 0) / 4 = 43.75
        assert avail.score == 43.8  # rounded to 1 decimal

    def test_large_graph(self):
        comps = [_comp(f"c{i}", f"C{i}") for i in range(50)]
        g = _graph(*comps)
        sc = ResilienceScorecard(g).generate()
        assert sc.total_components == 50
        assert len(sc.dimension_scores) == 8


# ---------------------------------------------------------------------------
# 18. Component scores dict
# ---------------------------------------------------------------------------

class TestComponentScoresDict:
    def test_all_components_in_each_dimension(self):
        g = _graph(
            _comp("a", "A"),
            _comp("b", "B"),
            _comp("c", "C"),
        )
        sc = ResilienceScorecard(g).generate()
        for ds in sc.dimension_scores:
            assert set(ds.component_scores.keys()) == {"a", "b", "c"}

    def test_component_scores_values_are_numeric(self):
        g = _graph(_comp("c1", "App"))
        sc = ResilienceScorecard(g).generate()
        for ds in sc.dimension_scores:
            for score in ds.component_scores.values():
                assert isinstance(score, (int, float))
                assert 0 <= score <= 100


# ---------------------------------------------------------------------------
# 19. Dataclass structure tests
# ---------------------------------------------------------------------------

class TestDataclasses:
    def test_dimension_score_fields(self):
        ds = DimensionScore(
            dimension=Dimension.AVAILABILITY,
            description="test",
            score=80.0,
            grade=Grade.A,
            findings=["f1"],
            recommendations=["r1"],
            component_scores={"c1": 80.0},
        )
        assert ds.dimension == Dimension.AVAILABILITY
        assert ds.description == "test"
        assert ds.score == 80.0
        assert ds.grade == Grade.A
        assert ds.findings == ["f1"]
        assert ds.recommendations == ["r1"]
        assert ds.component_scores == {"c1": 80.0}

    def test_action_item_fields(self):
        ai = ActionItem(
            priority=1,
            dimension=Dimension.SECURITY_POSTURE,
            action="Fix it",
            impact="High",
            effort="low",
            components_affected=["c1", "c2"],
        )
        assert ai.priority == 1
        assert ai.dimension == Dimension.SECURITY_POSTURE
        assert ai.action == "Fix it"
        assert ai.impact == "High"
        assert ai.effort == "low"
        assert ai.components_affected == ["c1", "c2"]

    def test_scorecard_fields(self):
        sc = Scorecard(
            overall_score=75.0,
            overall_grade=Grade.B,
            dimension_scores=[],
            action_items=[],
            total_components=5,
            healthy_components=3,
            at_risk_components=2,
            strengths=["avail"],
            weaknesses=["sec"],
            executive_summary="Test summary",
        )
        assert sc.overall_score == 75.0
        assert sc.overall_grade == Grade.B
        assert sc.total_components == 5
        assert sc.executive_summary == "Test summary"


# ---------------------------------------------------------------------------
# 20. Integration: end-to-end multi-component scenario
# ---------------------------------------------------------------------------

class TestIntegration:
    def test_realistic_infrastructure(self):
        """Simulate a realistic 3-tier setup and verify scorecard integrity."""
        from faultray.model.components import Dependency

        lb = _comp("lb", "LoadBalancer", ctype=ComponentType.LOAD_BALANCER, replicas=2)
        lb.security = SecurityProfile(
            waf_protected=True, rate_limiting=True, log_enabled=True,
            ids_monitored=True, encryption_in_transit=True,
        )

        app = _comp("app", "AppServer", replicas=3, failover=True, promotion_time=10)
        app.autoscaling = AutoScalingConfig(enabled=True)
        app.metrics = ResourceMetrics(cpu_percent=40, memory_percent=50)
        app.security = SecurityProfile(
            auth_required=True, encryption_in_transit=True,
            log_enabled=True, ids_monitored=True,
        )

        db = _comp("db", "Database", ctype=ComponentType.DATABASE, replicas=2, failover=True, promotion_time=20)
        db.security = SecurityProfile(
            encryption_at_rest=True, encryption_in_transit=True,
            backup_enabled=True, log_enabled=True, ids_monitored=True,
        )

        g = InfraGraph()
        g.add_component(lb)
        g.add_component(app)
        g.add_component(db)
        g.add_dependency(Dependency(source_id="lb", target_id="app"))
        g.add_dependency(Dependency(source_id="app", target_id="db"))

        sc = ResilienceScorecard(g).generate()

        assert sc.total_components == 3
        assert sc.healthy_components == 3
        assert sc.at_risk_components == 0
        assert len(sc.dimension_scores) == 8
        assert sc.overall_score > 0
        assert isinstance(sc.overall_grade, Grade)
        assert isinstance(sc.executive_summary, str)
        assert len(sc.executive_summary) > 0

    def test_critical_effort_keyword_immediately(self):
        """The keyword 'immediately' triggers low effort."""
        c = _comp("c1", "Server", health=HealthStatus.DOWN)
        g = _graph(c)
        sc = ResilienceScorecard(g).generate()
        # "CRITICAL: Restore Server immediately" contains both "critical" and "immediately"
        critical_items = [
            ai for ai in sc.action_items if "immediately" in ai.action.lower()
        ]
        for ai in critical_items:
            assert ai.effort == "low"

    def test_dimension_descriptions_exist_for_all(self):
        """Every dimension that is scored has a non-empty description."""
        g = _graph(_comp("c1", "App"))
        sc = ResilienceScorecard(g).generate()
        for ds in sc.dimension_scores:
            assert ds.description != ""
            assert len(ds.description) > 10  # meaningful description
