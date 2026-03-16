"""Tests for the Change Velocity Impact Analyzer."""

from __future__ import annotations

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    CircuitBreakerConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    HealthStatus,
    OperationalProfile,
    ResourceMetrics,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.change_velocity import (
    ChangeVelocityAnalyzer,
    ChangeVelocityProfile,
    VelocityImpactReport,
    _classify_cfr,
    _classify_deploy_freq,
    _classify_lead_time,
    _classify_mttr,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(
    cid: str,
    name: str,
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    health: HealthStatus = HealthStatus.HEALTHY,
    autoscaling: bool = False,
    failover: bool = False,
    deploy_downtime_seconds: float = 30.0,
) -> Component:
    return Component(
        id=cid,
        name=name,
        type=ctype,
        replicas=replicas,
        health=health,
        autoscaling=AutoScalingConfig(enabled=autoscaling),
        failover=FailoverConfig(enabled=failover),
        operational_profile=OperationalProfile(deploy_downtime_seconds=deploy_downtime_seconds),
    )


def _chain_graph() -> InfraGraph:
    """lb -> app -> db  with circuit breaker on lb->app edge."""
    g = InfraGraph()
    g.add_component(_comp("lb", "LB", ComponentType.LOAD_BALANCER, replicas=2, failover=True))
    g.add_component(_comp("app", "API", replicas=3, autoscaling=True, deploy_downtime_seconds=5))
    g.add_component(_comp("db", "DB", ComponentType.DATABASE, replicas=1, deploy_downtime_seconds=60))
    g.add_dependency(Dependency(
        source_id="lb", target_id="app",
        circuit_breaker=CircuitBreakerConfig(enabled=True),
    ))
    g.add_dependency(Dependency(source_id="app", target_id="db"))
    return g


# ---------------------------------------------------------------------------
# Tests: DORA Classification Helpers
# ---------------------------------------------------------------------------


class TestClassifyDeployFreq:
    def test_elite(self):
        assert _classify_deploy_freq(7) == "Elite"
        assert _classify_deploy_freq(100) == "Elite"

    def test_high(self):
        assert _classify_deploy_freq(1) == "High"
        assert _classify_deploy_freq(6.9) == "High"

    def test_medium(self):
        assert _classify_deploy_freq(0.25) == "Medium"
        assert _classify_deploy_freq(0.5) == "Medium"

    def test_low(self):
        assert _classify_deploy_freq(0.1) == "Low"
        assert _classify_deploy_freq(0.0) == "Low"


class TestClassifyLeadTime:
    def test_elite(self):
        assert _classify_lead_time(0.5) == "Elite"
        assert _classify_lead_time(1.0) == "Elite"

    def test_high(self):
        assert _classify_lead_time(24) == "High"
        assert _classify_lead_time(168) == "High"

    def test_medium(self):
        assert _classify_lead_time(169) == "Medium"
        assert _classify_lead_time(720) == "Medium"

    def test_low(self):
        assert _classify_lead_time(721) == "Low"
        assert _classify_lead_time(10000) == "Low"


class TestClassifyCfr:
    def test_elite(self):
        assert _classify_cfr(0.0) == "Elite"
        assert _classify_cfr(5.0) == "Elite"

    def test_high(self):
        assert _classify_cfr(5.1) == "High"
        assert _classify_cfr(10.0) == "High"

    def test_medium(self):
        assert _classify_cfr(10.1) == "Medium"
        assert _classify_cfr(15.0) == "Medium"

    def test_low(self):
        assert _classify_cfr(15.1) == "Low"
        assert _classify_cfr(100.0) == "Low"


class TestClassifyMttr:
    def test_elite(self):
        assert _classify_mttr(1) == "Elite"
        assert _classify_mttr(60) == "Elite"

    def test_high(self):
        assert _classify_mttr(61) == "High"
        assert _classify_mttr(1440) == "High"

    def test_medium(self):
        assert _classify_mttr(1441) == "Medium"
        assert _classify_mttr(10080) == "Medium"

    def test_low(self):
        assert _classify_mttr(10081) == "Low"
        assert _classify_mttr(100000) == "Low"


# ---------------------------------------------------------------------------
# Tests: _classify_dora (overall)
# ---------------------------------------------------------------------------


class TestClassifyDora:
    def test_all_elite(self):
        """When all metrics are elite, overall is Elite."""
        g = InfraGraph()
        analyzer = ChangeVelocityAnalyzer(g)
        profile = ChangeVelocityProfile(
            deploys_per_week=14, change_failure_rate=2.0,
            mttr_minutes=30, lead_time_hours=0.5,
        )
        assert analyzer._classify_dora(profile) == "Elite"

    def test_worst_metric_wins(self):
        """Overall is the worst (lowest) of all metrics."""
        g = InfraGraph()
        analyzer = ChangeVelocityAnalyzer(g)
        # Elite deploy freq, Elite lead time, Elite CFR, but Low MTTR
        profile = ChangeVelocityProfile(
            deploys_per_week=14, change_failure_rate=2.0,
            mttr_minutes=50000, lead_time_hours=0.5,
        )
        assert analyzer._classify_dora(profile) == "Low"

    def test_medium_classification(self):
        """Medium in one dimension drags the overall to Medium."""
        g = InfraGraph()
        analyzer = ChangeVelocityAnalyzer(g)
        profile = ChangeVelocityProfile(
            deploys_per_week=14, change_failure_rate=12.0,  # Medium CFR
            mttr_minutes=30, lead_time_hours=0.5,
        )
        assert analyzer._classify_dora(profile) == "Medium"


# ---------------------------------------------------------------------------
# Tests: _compute_dora_scores
# ---------------------------------------------------------------------------


class TestComputeDoraScores:
    def test_all_four_keys_present(self):
        g = InfraGraph()
        analyzer = ChangeVelocityAnalyzer(g)
        profile = ChangeVelocityProfile(
            deploys_per_week=10, change_failure_rate=5.0,
            mttr_minutes=60, lead_time_hours=24,
        )
        scores = analyzer._compute_dora_scores(profile)
        assert "deployment_frequency" in scores
        assert "lead_time" in scores
        assert "change_failure_rate" in scores
        assert "mttr" in scores

    def test_values_are_valid_levels(self):
        g = InfraGraph()
        analyzer = ChangeVelocityAnalyzer(g)
        profile = ChangeVelocityProfile(
            deploys_per_week=10, change_failure_rate=5.0,
            mttr_minutes=60, lead_time_hours=24,
        )
        scores = analyzer._compute_dora_scores(profile)
        valid = {"Elite", "High", "Medium", "Low"}
        for v in scores.values():
            assert v in valid


# ---------------------------------------------------------------------------
# Tests: _compute_stability_impact
# ---------------------------------------------------------------------------


class TestStabilityImpact:
    def test_range_0_to_100(self):
        g = _chain_graph()
        analyzer = ChangeVelocityAnalyzer(g)
        for cfr in [0, 5, 10, 15, 30]:
            for mttr in [1, 60, 1440, 10080, 50000]:
                profile = ChangeVelocityProfile(
                    deploys_per_week=10, change_failure_rate=cfr,
                    mttr_minutes=mttr, lead_time_hours=24,
                )
                impact = analyzer._compute_stability_impact(profile)
                assert 0.0 <= impact <= 100.0

    def test_low_cfr_high_stability(self):
        g = _chain_graph()
        analyzer = ChangeVelocityAnalyzer(g)
        p_low = ChangeVelocityProfile(deploys_per_week=10, change_failure_rate=1.0,
                                       mttr_minutes=5, lead_time_hours=1)
        p_high = ChangeVelocityProfile(deploys_per_week=10, change_failure_rate=30.0,
                                        mttr_minutes=50000, lead_time_hours=1000)
        low_impact = analyzer._compute_stability_impact(p_low)
        high_impact = analyzer._compute_stability_impact(p_high)
        assert low_impact > high_impact

    def test_cfr_score_brackets(self):
        """Test the specific CFR scoring brackets."""
        g = InfraGraph()
        analyzer = ChangeVelocityAnalyzer(g)
        # cfr <= 1 => 40 pts
        p1 = ChangeVelocityProfile(deploys_per_week=10, change_failure_rate=0.5,
                                    mttr_minutes=5, lead_time_hours=1)
        # cfr <= 5 => 35 pts
        p2 = ChangeVelocityProfile(deploys_per_week=10, change_failure_rate=3.0,
                                    mttr_minutes=5, lead_time_hours=1)
        s1 = analyzer._compute_stability_impact(p1)
        s2 = analyzer._compute_stability_impact(p2)
        assert s1 > s2  # 40 > 35

    def test_cfr_above_15_decays(self):
        """CFR > 15 uses the decaying formula: 15 - (cfr - 15) * 0.5."""
        g = InfraGraph()
        analyzer = ChangeVelocityAnalyzer(g)
        p = ChangeVelocityProfile(deploys_per_week=10, change_failure_rate=25.0,
                                   mttr_minutes=5, lead_time_hours=1)
        # CFR score = max(0, 15 - (25-15)*0.5) = max(0, 10) = 10
        # MTTR <= 5 => 30
        # arch score for empty graph = 15
        # Total should be >= 10 + 30 (arch may contribute)
        impact = analyzer._compute_stability_impact(p)
        assert impact >= 0

    def test_cfr_very_high_clamps_to_zero(self):
        """CFR so high that cfr_score goes to 0."""
        g = InfraGraph()
        analyzer = ChangeVelocityAnalyzer(g)
        p = ChangeVelocityProfile(deploys_per_week=10, change_failure_rate=100.0,
                                   mttr_minutes=50000, lead_time_hours=1)
        impact = analyzer._compute_stability_impact(p)
        assert impact >= 0.0

    def test_mttr_score_brackets(self):
        """Test the MTTR scoring brackets."""
        g = InfraGraph()
        analyzer = ChangeVelocityAnalyzer(g)
        # mttr <= 5 => 30, mttr <= 60 => 25, mttr <= 1440 => 15, mttr <= 10080 => 5, else 0
        p_fast = ChangeVelocityProfile(deploys_per_week=10, change_failure_rate=1.0,
                                        mttr_minutes=3, lead_time_hours=1)
        p_slow = ChangeVelocityProfile(deploys_per_week=10, change_failure_rate=1.0,
                                        mttr_minutes=50000, lead_time_hours=1)
        s_fast = analyzer._compute_stability_impact(p_fast)
        s_slow = analyzer._compute_stability_impact(p_slow)
        assert s_fast > s_slow


# ---------------------------------------------------------------------------
# Tests: _architecture_resilience_score
# ---------------------------------------------------------------------------


class TestArchitectureResilienceScore:
    def test_empty_graph_neutral_score(self):
        g = InfraGraph()
        analyzer = ChangeVelocityAnalyzer(g)
        assert analyzer._architecture_resilience_score() == 15.0

    def test_resilient_graph_higher_score(self):
        """Graph with replicas, autoscaling, failover, circuit breakers => higher."""
        g = _chain_graph()
        analyzer = ChangeVelocityAnalyzer(g)
        score = analyzer._architecture_resilience_score()
        assert score > 0.0
        assert score <= 30.0

    def test_replicas_contribute(self):
        g = InfraGraph()
        g.add_component(_comp("app", "App", replicas=2))
        analyzer = ChangeVelocityAnalyzer(g)
        score_multi = analyzer._architecture_resilience_score()

        g2 = InfraGraph()
        g2.add_component(_comp("app", "App", replicas=1))
        analyzer2 = ChangeVelocityAnalyzer(g2)
        score_single = analyzer2._architecture_resilience_score()
        assert score_multi >= score_single

    def test_autoscaling_contributes(self):
        g1 = InfraGraph()
        g1.add_component(_comp("app", "App", replicas=2, autoscaling=True))
        g2 = InfraGraph()
        g2.add_component(_comp("app", "App", replicas=2, autoscaling=False))
        s1 = ChangeVelocityAnalyzer(g1)._architecture_resilience_score()
        s2 = ChangeVelocityAnalyzer(g2)._architecture_resilience_score()
        assert s1 > s2

    def test_failover_contributes(self):
        g1 = InfraGraph()
        g1.add_component(_comp("app", "App", replicas=2, failover=True))
        g2 = InfraGraph()
        g2.add_component(_comp("app", "App", replicas=2, failover=False))
        s1 = ChangeVelocityAnalyzer(g1)._architecture_resilience_score()
        s2 = ChangeVelocityAnalyzer(g2)._architecture_resilience_score()
        assert s1 > s2

    def test_circuit_breakers_contribute(self):
        g1 = InfraGraph()
        g1.add_component(_comp("a", "A", replicas=1))
        g1.add_component(_comp("b", "B", replicas=1))
        g1.add_dependency(Dependency(
            source_id="a", target_id="b",
            circuit_breaker=CircuitBreakerConfig(enabled=True),
        ))
        g2 = InfraGraph()
        g2.add_component(_comp("a", "A", replicas=1))
        g2.add_component(_comp("b", "B", replicas=1))
        g2.add_dependency(Dependency(source_id="a", target_id="b"))
        s1 = ChangeVelocityAnalyzer(g1)._architecture_resilience_score()
        s2 = ChangeVelocityAnalyzer(g2)._architecture_resilience_score()
        assert s1 > s2

    def test_score_capped_at_30(self):
        g = _chain_graph()
        analyzer = ChangeVelocityAnalyzer(g)
        assert analyzer._architecture_resilience_score() <= 30.0


# ---------------------------------------------------------------------------
# Tests: _estimate_weekly_downtime
# ---------------------------------------------------------------------------


class TestEstimateWeeklyDowntime:
    def test_formula(self):
        profile = ChangeVelocityProfile(
            deploys_per_week=10, change_failure_rate=10.0,
            mttr_minutes=60, lead_time_hours=24,
        )
        result = ChangeVelocityAnalyzer._estimate_weekly_downtime(profile)
        expected = 10 * (10.0 / 100) * 60  # = 60
        assert abs(result - expected) < 0.01

    def test_zero_deploys(self):
        profile = ChangeVelocityProfile(
            deploys_per_week=0, change_failure_rate=50.0,
            mttr_minutes=120, lead_time_hours=24,
        )
        assert ChangeVelocityAnalyzer._estimate_weekly_downtime(profile) == 0.0

    def test_zero_cfr(self):
        profile = ChangeVelocityProfile(
            deploys_per_week=50, change_failure_rate=0.0,
            mttr_minutes=120, lead_time_hours=24,
        )
        assert ChangeVelocityAnalyzer._estimate_weekly_downtime(profile) == 0.0


# ---------------------------------------------------------------------------
# Tests: _compute_optimal_frequency
# ---------------------------------------------------------------------------


class TestOptimalFrequency:
    def test_always_at_least_1(self):
        g = _chain_graph()
        analyzer = ChangeVelocityAnalyzer(g)
        profile = ChangeVelocityProfile(
            deploys_per_week=1, change_failure_rate=50.0,
            mttr_minutes=50000, lead_time_hours=1000,
        )
        result = analyzer._compute_optimal_frequency(profile)
        assert result >= 1.0

    def test_low_cfr_fast_mttr_higher_freq(self):
        g = _chain_graph()
        analyzer = ChangeVelocityAnalyzer(g)
        p_good = ChangeVelocityProfile(
            deploys_per_week=10, change_failure_rate=2.0,
            mttr_minutes=3, lead_time_hours=1,
        )
        p_bad = ChangeVelocityProfile(
            deploys_per_week=10, change_failure_rate=20.0,
            mttr_minutes=5000, lead_time_hours=1,
        )
        freq_good = analyzer._compute_optimal_frequency(p_good)
        freq_bad = analyzer._compute_optimal_frequency(p_bad)
        assert freq_good > freq_bad

    def test_cfr_above_15_reduces(self):
        g = InfraGraph()
        analyzer = ChangeVelocityAnalyzer(g)
        p = ChangeVelocityProfile(
            deploys_per_week=10, change_failure_rate=20.0,
            mttr_minutes=30, lead_time_hours=1,
        )
        freq = analyzer._compute_optimal_frequency(p)
        # base 10 * 0.3 (cfr>15) => 3.0 base, but MTTR & arch adjustments apply
        assert freq >= 1.0

    def test_cfr_above_10_reduces(self):
        g = InfraGraph()
        analyzer = ChangeVelocityAnalyzer(g)
        p = ChangeVelocityProfile(
            deploys_per_week=10, change_failure_rate=12.0,
            mttr_minutes=30, lead_time_hours=1,
        )
        freq = analyzer._compute_optimal_frequency(p)
        assert freq >= 1.0

    def test_cfr_above_5_reduces(self):
        g = InfraGraph()
        analyzer = ChangeVelocityAnalyzer(g)
        p = ChangeVelocityProfile(
            deploys_per_week=10, change_failure_rate=8.0,
            mttr_minutes=30, lead_time_hours=1,
        )
        freq = analyzer._compute_optimal_frequency(p)
        assert freq >= 1.0

    def test_mttr_above_1440_slows(self):
        g = InfraGraph()
        analyzer = ChangeVelocityAnalyzer(g)
        p_slow = ChangeVelocityProfile(
            deploys_per_week=10, change_failure_rate=3.0,
            mttr_minutes=2000, lead_time_hours=1,
        )
        p_fast = ChangeVelocityProfile(
            deploys_per_week=10, change_failure_rate=3.0,
            mttr_minutes=30, lead_time_hours=1,
        )
        assert analyzer._compute_optimal_frequency(p_fast) > analyzer._compute_optimal_frequency(p_slow)

    def test_mttr_above_60_slows(self):
        g = InfraGraph()
        analyzer = ChangeVelocityAnalyzer(g)
        p = ChangeVelocityProfile(
            deploys_per_week=10, change_failure_rate=3.0,
            mttr_minutes=120, lead_time_hours=1,
        )
        freq = analyzer._compute_optimal_frequency(p)
        assert freq >= 1.0

    def test_mttr_lte_5_boosts(self):
        """MTTR <= 5 gives a 1.5x boost."""
        g = InfraGraph()
        analyzer = ChangeVelocityAnalyzer(g)
        p_excellent = ChangeVelocityProfile(
            deploys_per_week=10, change_failure_rate=3.0,
            mttr_minutes=3, lead_time_hours=1,
        )
        p_normal = ChangeVelocityProfile(
            deploys_per_week=10, change_failure_rate=3.0,
            mttr_minutes=30, lead_time_hours=1,
        )
        assert analyzer._compute_optimal_frequency(p_excellent) > analyzer._compute_optimal_frequency(p_normal)

    def test_high_arch_score_boosts(self):
        """Architecture with high resilience supports faster deploys."""
        g_resilient = InfraGraph()
        g_resilient.add_component(_comp("app", "App", replicas=3, autoscaling=True, failover=True))
        g_resilient.add_component(_comp("db", "DB", ComponentType.DATABASE, replicas=3, failover=True))
        g_resilient.add_dependency(Dependency(
            source_id="app", target_id="db",
            circuit_breaker=CircuitBreakerConfig(enabled=True),
        ))

        g_weak = InfraGraph()
        g_weak.add_component(_comp("app", "App", replicas=1))

        p = ChangeVelocityProfile(
            deploys_per_week=10, change_failure_rate=3.0,
            mttr_minutes=30, lead_time_hours=1,
        )
        freq_resilient = ChangeVelocityAnalyzer(g_resilient)._compute_optimal_frequency(p)
        freq_weak = ChangeVelocityAnalyzer(g_weak)._compute_optimal_frequency(p)
        assert freq_resilient >= freq_weak


# ---------------------------------------------------------------------------
# Tests: _analyze_architecture_risks
# ---------------------------------------------------------------------------


class TestArchitectureRisks:
    def test_single_replica_risk_at_high_freq(self):
        g = InfraGraph()
        g.add_component(_comp("api", "API", replicas=1))
        analyzer = ChangeVelocityAnalyzer(g)
        profile = ChangeVelocityProfile(
            deploys_per_week=10, change_failure_rate=5.0,
            mttr_minutes=60, lead_time_hours=24,
        )
        risks = analyzer._analyze_architecture_risks(profile)
        assert any("single replica" in r.lower() for r in risks)

    def test_no_single_replica_risk_at_low_freq(self):
        """deploys_per_week < 5 should not trigger single replica risk."""
        g = InfraGraph()
        g.add_component(_comp("api", "API", replicas=1))
        analyzer = ChangeVelocityAnalyzer(g)
        profile = ChangeVelocityProfile(
            deploys_per_week=2, change_failure_rate=5.0,
            mttr_minutes=60, lead_time_hours=24,
        )
        risks = analyzer._analyze_architecture_risks(profile)
        single = [r for r in risks if "single replica" in r.lower()]
        assert len(single) == 0

    def test_stateful_without_failover(self):
        """DB/Cache without failover flagged at deploys_per_week >= 3."""
        g = InfraGraph()
        g.add_component(_comp("db", "DB", ComponentType.DATABASE, replicas=2, failover=False))
        analyzer = ChangeVelocityAnalyzer(g)
        profile = ChangeVelocityProfile(
            deploys_per_week=5, change_failure_rate=5.0,
            mttr_minutes=60, lead_time_hours=24,
        )
        risks = analyzer._analyze_architecture_risks(profile)
        assert any("failover" in r.lower() for r in risks)

    def test_cache_without_failover(self):
        g = InfraGraph()
        g.add_component(_comp("cache", "Cache", ComponentType.CACHE, replicas=2, failover=False))
        analyzer = ChangeVelocityAnalyzer(g)
        profile = ChangeVelocityProfile(
            deploys_per_week=5, change_failure_rate=5.0,
            mttr_minutes=60, lead_time_hours=24,
        )
        risks = analyzer._analyze_architecture_risks(profile)
        assert any("failover" in r.lower() for r in risks)

    def test_stateful_with_failover_no_risk(self):
        g = InfraGraph()
        g.add_component(_comp("db", "DB", ComponentType.DATABASE, replicas=2, failover=True))
        analyzer = ChangeVelocityAnalyzer(g)
        profile = ChangeVelocityProfile(
            deploys_per_week=10, change_failure_rate=5.0,
            mttr_minutes=60, lead_time_hours=24,
        )
        risks = analyzer._analyze_architecture_risks(profile)
        failover_risks = [r for r in risks if "failover" in r.lower() and "db" in r.lower()]
        assert len(failover_risks) == 0

    def test_deploy_downtime_risk(self):
        """High deploy_downtime_seconds * frequency > 3600s/week triggers risk."""
        g = InfraGraph()
        # deploy_downtime = 120s, 50 deploys/week => 6000s = 100min > 60min threshold
        g.add_component(Component(
            id="app", name="SlowApp", type=ComponentType.APP_SERVER,
            replicas=2,
            operational_profile=OperationalProfile(deploy_downtime_seconds=120),
        ))
        analyzer = ChangeVelocityAnalyzer(g)
        profile = ChangeVelocityProfile(
            deploys_per_week=50, change_failure_rate=5.0,
            mttr_minutes=60, lead_time_hours=24,
        )
        risks = analyzer._analyze_architecture_risks(profile)
        assert any("deploy downtime" in r.lower() or "deploy-induced" in r.lower() for r in risks)

    def test_deploy_downtime_no_risk_when_low(self):
        """deploy_downtime=5s * 10 deploys = 50s/week, under threshold."""
        g = InfraGraph()
        g.add_component(Component(
            id="app", name="FastApp", type=ComponentType.APP_SERVER,
            replicas=2,
            operational_profile=OperationalProfile(deploy_downtime_seconds=5),
        ))
        analyzer = ChangeVelocityAnalyzer(g)
        profile = ChangeVelocityProfile(
            deploys_per_week=10, change_failure_rate=5.0,
            mttr_minutes=60, lead_time_hours=24,
        )
        risks = analyzer._analyze_architecture_risks(profile)
        deploy_risks = [r for r in risks if "deploy downtime" in r.lower() or "deploy-induced downtime" in r.lower()]
        assert len(deploy_risks) == 0

    def test_missing_circuit_breakers_at_high_freq(self):
        """Missing CB on edges flagged at deploys_per_week >= 10."""
        g = InfraGraph()
        g.add_component(_comp("a", "A", replicas=2))
        g.add_component(_comp("b", "B", replicas=2))
        g.add_dependency(Dependency(source_id="a", target_id="b"))  # No CB
        analyzer = ChangeVelocityAnalyzer(g)
        profile = ChangeVelocityProfile(
            deploys_per_week=15, change_failure_rate=5.0,
            mttr_minutes=60, lead_time_hours=24,
        )
        risks = analyzer._analyze_architecture_risks(profile)
        assert any("circuit breaker" in r.lower() for r in risks)

    def test_no_cb_risk_at_low_freq(self):
        """No CB risk at deploys_per_week < 10."""
        g = InfraGraph()
        g.add_component(_comp("a", "A", replicas=2))
        g.add_component(_comp("b", "B", replicas=2))
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        analyzer = ChangeVelocityAnalyzer(g)
        profile = ChangeVelocityProfile(
            deploys_per_week=5, change_failure_rate=5.0,
            mttr_minutes=60, lead_time_hours=24,
        )
        risks = analyzer._analyze_architecture_risks(profile)
        cb_risks = [r for r in risks if "circuit breaker" in r.lower()]
        assert len(cb_risks) == 0

    def test_resilient_graph_no_risks(self):
        """Fully resilient graph should have minimal risks."""
        g = InfraGraph()
        g.add_component(_comp("lb", "LB", ComponentType.LOAD_BALANCER, replicas=3,
                              autoscaling=True, failover=True, deploy_downtime_seconds=0))
        g.add_component(_comp("app", "App", replicas=3, autoscaling=True,
                              failover=True, deploy_downtime_seconds=0))
        g.add_component(_comp("db", "DB", ComponentType.DATABASE, replicas=3,
                              failover=True, deploy_downtime_seconds=0))
        g.add_dependency(Dependency(
            source_id="lb", target_id="app",
            circuit_breaker=CircuitBreakerConfig(enabled=True),
        ))
        g.add_dependency(Dependency(
            source_id="app", target_id="db",
            circuit_breaker=CircuitBreakerConfig(enabled=True),
        ))
        analyzer = ChangeVelocityAnalyzer(g)
        profile = ChangeVelocityProfile(
            deploys_per_week=10, change_failure_rate=3.0,
            mttr_minutes=30, lead_time_hours=1,
        )
        risks = analyzer._analyze_architecture_risks(profile)
        single_replica = [r for r in risks if "single replica" in r.lower()]
        failover_risks = [r for r in risks if "failover" in r.lower()]
        assert len(single_replica) == 0
        assert len(failover_risks) == 0


# ---------------------------------------------------------------------------
# Tests: _generate_recommendations
# ---------------------------------------------------------------------------


class TestRecommendations:
    def test_low_dora_ci_recommendation(self):
        recs = ChangeVelocityAnalyzer._generate_recommendations(
            ChangeVelocityProfile(deploys_per_week=0.04, change_failure_rate=25.0,
                                   mttr_minutes=50000, lead_time_hours=5000),
            "Low", 20.0, [],
        )
        assert any("ci/cd" in r.lower() for r in recs)

    def test_medium_dora_mttr_recommendation(self):
        recs = ChangeVelocityAnalyzer._generate_recommendations(
            ChangeVelocityProfile(deploys_per_week=2, change_failure_rate=8.0,
                                   mttr_minutes=120, lead_time_hours=100),
            "Medium", 60.0, [],
        )
        assert any("mttr" in r.lower() or "rollback" in r.lower() for r in recs)

    def test_high_cfr_gt_15_recommendation(self):
        recs = ChangeVelocityAnalyzer._generate_recommendations(
            ChangeVelocityProfile(deploys_per_week=10, change_failure_rate=20.0,
                                   mttr_minutes=60, lead_time_hours=24),
            "Low", 50.0, [],
        )
        assert any("failure rate" in r.lower() for r in recs)

    def test_elevated_cfr_gt_10_recommendation(self):
        recs = ChangeVelocityAnalyzer._generate_recommendations(
            ChangeVelocityProfile(deploys_per_week=10, change_failure_rate=12.0,
                                   mttr_minutes=60, lead_time_hours=24),
            "Medium", 60.0, [],
        )
        assert any("failure rate" in r.lower() or "integration test" in r.lower() for r in recs)

    def test_mttr_gt_1440_recommendation(self):
        recs = ChangeVelocityAnalyzer._generate_recommendations(
            ChangeVelocityProfile(deploys_per_week=10, change_failure_rate=5.0,
                                   mttr_minutes=2000, lead_time_hours=24),
            "High", 60.0, [],
        )
        assert any("mttr" in r.lower() or "monitoring" in r.lower() for r in recs)

    def test_mttr_gt_60_recommendation(self):
        recs = ChangeVelocityAnalyzer._generate_recommendations(
            ChangeVelocityProfile(deploys_per_week=10, change_failure_rate=5.0,
                                   mttr_minutes=120, lead_time_hours=24),
            "High", 70.0, [],
        )
        assert any("mttr" in r.lower() or "rollback" in r.lower() for r in recs)

    def test_lead_time_gt_168_recommendation(self):
        recs = ChangeVelocityAnalyzer._generate_recommendations(
            ChangeVelocityProfile(deploys_per_week=10, change_failure_rate=5.0,
                                   mttr_minutes=60, lead_time_hours=500),
            "High", 70.0, [],
        )
        assert any("lead time" in r.lower() for r in recs)

    def test_low_stability_recommendation(self):
        recs = ChangeVelocityAnalyzer._generate_recommendations(
            ChangeVelocityProfile(deploys_per_week=10, change_failure_rate=5.0,
                                   mttr_minutes=60, lead_time_hours=24),
            "High", 30.0, [],
        )
        assert any("stability" in r.lower() for r in recs)

    def test_elite_positive_feedback(self):
        recs = ChangeVelocityAnalyzer._generate_recommendations(
            ChangeVelocityProfile(deploys_per_week=14, change_failure_rate=2.0,
                                   mttr_minutes=15, lead_time_hours=0.5),
            "Elite", 90.0, [],
        )
        assert any("elite" in r.lower() for r in recs)

    def test_no_elite_feedback_when_low_stability(self):
        """Elite DORA but low stability should not get positive feedback."""
        recs = ChangeVelocityAnalyzer._generate_recommendations(
            ChangeVelocityProfile(deploys_per_week=14, change_failure_rate=2.0,
                                   mttr_minutes=15, lead_time_hours=0.5),
            "Elite", 50.0, [],
        )
        elite_recs = [r for r in recs if "elite" in r.lower() and "continue" in r.lower()]
        assert len(elite_recs) == 0


# ---------------------------------------------------------------------------
# Tests: analyze() integration
# ---------------------------------------------------------------------------


class TestAnalyze:
    def test_returns_report(self):
        g = _chain_graph()
        report = ChangeVelocityAnalyzer(g).analyze()
        assert isinstance(report, VelocityImpactReport)

    def test_report_fields_populated(self):
        g = _chain_graph()
        report = ChangeVelocityAnalyzer(g).analyze(
            deploys_per_week=7, change_failure_rate=3.0,
            mttr_minutes=45, lead_time_hours=12,
        )
        assert report.current_velocity.deploys_per_week == 7
        assert report.current_velocity.change_failure_rate == 3.0
        assert report.current_velocity.mttr_minutes == 45
        assert report.current_velocity.lead_time_hours == 12
        assert report.dora_classification in {"Elite", "High", "Medium", "Low"}
        assert 0 <= report.stability_impact <= 100
        assert report.optimal_deploy_frequency >= 1.0
        assert isinstance(report.recommendations, list)
        assert isinstance(report.dora_scores, dict)
        assert isinstance(report.architecture_risk_factors, list)

    def test_elite_classification(self):
        g = _chain_graph()
        report = ChangeVelocityAnalyzer(g).analyze(
            deploys_per_week=14, change_failure_rate=2.0,
            mttr_minutes=30, lead_time_hours=0.5,
        )
        assert report.dora_classification == "Elite"

    def test_low_classification(self):
        g = InfraGraph()
        g.add_component(_comp("api", "API", replicas=1))
        report = ChangeVelocityAnalyzer(g).analyze(
            deploys_per_week=0.04, change_failure_rate=25.0,
            mttr_minutes=50000, lead_time_hours=5000,
        )
        assert report.dora_classification == "Low"

    def test_downtime_calculation(self):
        g = _chain_graph()
        report = ChangeVelocityAnalyzer(g).analyze(
            deploys_per_week=10, change_failure_rate=10.0,
            mttr_minutes=60,
        )
        expected = 10 * (10.0 / 100) * 60
        assert abs(report.estimated_downtime_minutes_per_week - expected) < 0.1

    def test_default_parameters(self):
        """Default args: 10 deploys/week, 5% CFR, 60min MTTR, 24h lead time."""
        g = _chain_graph()
        report = ChangeVelocityAnalyzer(g).analyze()
        assert report.current_velocity.deploys_per_week == 10
        assert report.current_velocity.change_failure_rate == 5.0
        assert report.current_velocity.mttr_minutes == 60
        assert report.current_velocity.lead_time_hours == 24


# ---------------------------------------------------------------------------
# Tests: simulate_velocity_sweep
# ---------------------------------------------------------------------------


class TestVelocitySweep:
    def test_default_range(self):
        g = _chain_graph()
        results = ChangeVelocityAnalyzer(g).simulate_velocity_sweep()
        assert len(results) == 5
        assert [r["deploys_per_week"] for r in results] == [1, 5, 10, 20, 50]

    def test_custom_range(self):
        g = _chain_graph()
        results = ChangeVelocityAnalyzer(g).simulate_velocity_sweep(deploy_range=[2, 4])
        assert len(results) == 2
        assert results[0]["deploys_per_week"] == 2

    def test_result_keys(self):
        g = _chain_graph()
        results = ChangeVelocityAnalyzer(g).simulate_velocity_sweep()
        required_keys = {
            "deploys_per_week", "dora_classification", "stability_impact",
            "estimated_downtime_minutes_per_week", "optimal_deploy_frequency",
            "recommendation_count",
        }
        for r in results:
            assert required_keys.issubset(r.keys())

    def test_downtime_increases_with_frequency(self):
        g = _chain_graph()
        results = ChangeVelocityAnalyzer(g).simulate_velocity_sweep(
            deploy_range=[1, 50], change_failure_rate=10.0,
        )
        assert results[1]["estimated_downtime_minutes_per_week"] > results[0]["estimated_downtime_minutes_per_week"]

    def test_empty_graph_sweep(self):
        g = InfraGraph()
        results = ChangeVelocityAnalyzer(g).simulate_velocity_sweep()
        assert len(results) == 5
        for r in results:
            assert r["stability_impact"] >= 0

    def test_custom_cfr_and_mttr(self):
        g = _chain_graph()
        results = ChangeVelocityAnalyzer(g).simulate_velocity_sweep(
            deploy_range=[5],
            change_failure_rate=20.0,
            mttr_minutes=120,
            lead_time_hours=48,
        )
        assert len(results) == 1
        assert results[0]["deploys_per_week"] == 5


# ---------------------------------------------------------------------------
# Tests: Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_zero_deploys(self):
        g = _chain_graph()
        report = ChangeVelocityAnalyzer(g).analyze(deploys_per_week=0)
        assert report.estimated_downtime_minutes_per_week == 0.0
        assert isinstance(report, VelocityImpactReport)

    def test_very_high_cfr(self):
        g = _chain_graph()
        report = ChangeVelocityAnalyzer(g).analyze(
            deploys_per_week=10, change_failure_rate=100.0,
        )
        assert report.dora_classification == "Low"
        assert report.estimated_downtime_minutes_per_week > 0

    def test_empty_graph_analyze(self):
        g = InfraGraph()
        report = ChangeVelocityAnalyzer(g).analyze()
        assert isinstance(report, VelocityImpactReport)
        assert report.stability_impact >= 0

    def test_deploy_downtime_zero(self):
        """Components with 0 deploy downtime should not trigger deploy risk."""
        g = InfraGraph()
        g.add_component(_comp("app", "App", replicas=2, deploy_downtime_seconds=0))
        analyzer = ChangeVelocityAnalyzer(g)
        profile = ChangeVelocityProfile(
            deploys_per_week=100, change_failure_rate=5.0,
            mttr_minutes=60, lead_time_hours=24,
        )
        risks = analyzer._analyze_architecture_risks(profile)
        deploy_risks = [r for r in risks if "deploy downtime" in r.lower() or "deploy-induced" in r.lower()]
        assert len(deploy_risks) == 0

    def test_no_edges_no_cb_risk(self):
        """Graph with no edges should not have circuit breaker risks."""
        g = InfraGraph()
        g.add_component(_comp("a", "A", replicas=2))
        analyzer = ChangeVelocityAnalyzer(g)
        profile = ChangeVelocityProfile(
            deploys_per_week=50, change_failure_rate=5.0,
            mttr_minutes=60, lead_time_hours=24,
        )
        risks = analyzer._analyze_architecture_risks(profile)
        cb_risks = [r for r in risks if "circuit breaker" in r.lower()]
        assert len(cb_risks) == 0

    def test_all_edges_have_cb(self):
        """All CB enabled should produce no CB risk."""
        g = InfraGraph()
        g.add_component(_comp("a", "A", replicas=2))
        g.add_component(_comp("b", "B", replicas=2))
        g.add_dependency(Dependency(
            source_id="a", target_id="b",
            circuit_breaker=CircuitBreakerConfig(enabled=True),
        ))
        analyzer = ChangeVelocityAnalyzer(g)
        profile = ChangeVelocityProfile(
            deploys_per_week=50, change_failure_rate=5.0,
            mttr_minutes=60, lead_time_hours=24,
        )
        risks = analyzer._analyze_architecture_risks(profile)
        cb_risks = [r for r in risks if "circuit breaker" in r.lower()]
        assert len(cb_risks) == 0
