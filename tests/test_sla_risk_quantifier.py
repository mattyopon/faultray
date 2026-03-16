"""Comprehensive tests for SLA Risk Quantifier (target: 99%+ coverage)."""

from __future__ import annotations

import pytest

from faultray.model.components import (
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    HealthStatus,
    ResourceMetrics,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.sla_risk_quantifier import (
    SLA_DEFINITIONS,
    ComponentSLARisk,
    SLABreachScenario,
    SLADefinition,
    SLARiskQuantifier,
    SLARiskReport,
    SLATier,
    _HEALTH_BASE_PROBABILITY,
    _MONTH_MINUTES,
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
    failover: bool = False,
) -> Component:
    c = Component(id=cid, name=name, type=ctype, replicas=replicas)
    c.health = health
    if failover:
        c.failover = FailoverConfig(enabled=True, promotion_time_seconds=10)
    return c


def _graph(*comps: Component) -> InfraGraph:
    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    return g


# ---------------------------------------------------------------------------
# 1. SLATier Enum Tests
# ---------------------------------------------------------------------------


class TestSLATierEnum:
    def test_platinum_value(self):
        assert SLATier.PLATINUM.value == "platinum"

    def test_gold_value(self):
        assert SLATier.GOLD.value == "gold"

    def test_silver_value(self):
        assert SLATier.SILVER.value == "silver"

    def test_bronze_value(self):
        assert SLATier.BRONZE.value == "bronze"

    def test_is_str_enum(self):
        assert isinstance(SLATier.PLATINUM, str)
        assert isinstance(SLATier.GOLD, str)

    def test_total_tier_count(self):
        assert len(SLATier) == 4

    def test_iteration(self):
        tiers = list(SLATier)
        assert SLATier.PLATINUM in tiers
        assert SLATier.GOLD in tiers
        assert SLATier.SILVER in tiers
        assert SLATier.BRONZE in tiers

    def test_equality_with_string(self):
        assert SLATier.GOLD == "gold"

    def test_str_representation(self):
        assert str(SLATier.PLATINUM) == "SLATier.PLATINUM"


# ---------------------------------------------------------------------------
# 2. SLADefinition Tests
# ---------------------------------------------------------------------------


class TestSLADefinition:
    def test_create_definition(self):
        d = SLADefinition(
            tier=SLATier.GOLD,
            uptime_target=0.999,
            monthly_penalty_rate=0.15,
            max_downtime_minutes_per_month=43.2,
        )
        assert d.tier == SLATier.GOLD
        assert d.uptime_target == 0.999
        assert d.monthly_penalty_rate == 0.15
        assert d.max_downtime_minutes_per_month == 43.2

    def test_platinum_definition(self):
        d = SLA_DEFINITIONS[SLATier.PLATINUM]
        assert d.uptime_target == 0.9999
        assert d.monthly_penalty_rate == 0.25
        assert d.max_downtime_minutes_per_month == 4.32

    def test_gold_definition(self):
        d = SLA_DEFINITIONS[SLATier.GOLD]
        assert d.uptime_target == 0.999
        assert d.monthly_penalty_rate == 0.15
        assert d.max_downtime_minutes_per_month == 43.2

    def test_silver_definition(self):
        d = SLA_DEFINITIONS[SLATier.SILVER]
        assert d.uptime_target == 0.995
        assert d.monthly_penalty_rate == 0.10
        assert d.max_downtime_minutes_per_month == 216.0

    def test_bronze_definition(self):
        d = SLA_DEFINITIONS[SLATier.BRONZE]
        assert d.uptime_target == 0.99
        assert d.monthly_penalty_rate == 0.05
        assert d.max_downtime_minutes_per_month == 432.0

    def test_all_tiers_in_definitions(self):
        for tier in SLATier:
            assert tier in SLA_DEFINITIONS

    def test_uptime_ordering(self):
        assert SLA_DEFINITIONS[SLATier.PLATINUM].uptime_target > SLA_DEFINITIONS[SLATier.GOLD].uptime_target
        assert SLA_DEFINITIONS[SLATier.GOLD].uptime_target > SLA_DEFINITIONS[SLATier.SILVER].uptime_target
        assert SLA_DEFINITIONS[SLATier.SILVER].uptime_target > SLA_DEFINITIONS[SLATier.BRONZE].uptime_target

    def test_penalty_rate_ordering(self):
        assert SLA_DEFINITIONS[SLATier.PLATINUM].monthly_penalty_rate > SLA_DEFINITIONS[SLATier.GOLD].monthly_penalty_rate
        assert SLA_DEFINITIONS[SLATier.GOLD].monthly_penalty_rate > SLA_DEFINITIONS[SLATier.SILVER].monthly_penalty_rate
        assert SLA_DEFINITIONS[SLATier.SILVER].monthly_penalty_rate > SLA_DEFINITIONS[SLATier.BRONZE].monthly_penalty_rate


# ---------------------------------------------------------------------------
# 3. ComponentSLARisk Tests
# ---------------------------------------------------------------------------


class TestComponentSLARisk:
    def test_create(self):
        r = ComponentSLARisk(
            component_id="app-1",
            component_name="App Server",
            breach_probability=0.05,
            estimated_downtime_minutes=100.0,
            risk_score=5.0,
            risk_factors=["Single replica"],
        )
        assert r.component_id == "app-1"
        assert r.component_name == "App Server"
        assert r.breach_probability == 0.05
        assert r.estimated_downtime_minutes == 100.0
        assert r.risk_score == 5.0
        assert r.risk_factors == ["Single replica"]

    def test_empty_risk_factors(self):
        r = ComponentSLARisk(
            component_id="x",
            component_name="X",
            breach_probability=0.0,
            estimated_downtime_minutes=0.0,
            risk_score=0.0,
            risk_factors=[],
        )
        assert r.risk_factors == []


# ---------------------------------------------------------------------------
# 4. SLABreachScenario Tests
# ---------------------------------------------------------------------------


class TestSLABreachScenario:
    def test_create(self):
        s = SLABreachScenario(
            description="SPOF failure",
            probability=0.3,
            estimated_penalty_dollars=5000.0,
            affected_components=["app-1"],
            mitigation="Add replicas",
        )
        assert s.description == "SPOF failure"
        assert s.probability == 0.3
        assert s.estimated_penalty_dollars == 5000.0
        assert s.affected_components == ["app-1"]
        assert s.mitigation == "Add replicas"

    def test_multiple_affected(self):
        s = SLABreachScenario(
            description="cascade",
            probability=0.1,
            estimated_penalty_dollars=1000.0,
            affected_components=["a", "b", "c"],
            mitigation="Fix it",
        )
        assert len(s.affected_components) == 3


# ---------------------------------------------------------------------------
# 5. SLARiskReport Tests
# ---------------------------------------------------------------------------


class TestSLARiskReport:
    def test_create(self):
        r = SLARiskReport(
            tier=SLATier.GOLD,
            overall_breach_probability=0.05,
            overall_risk_score=5.0,
            component_risks=[],
            breach_scenarios=[],
            total_estimated_penalty=750.0,
            monthly_revenue=100_000.0,
            recommendations=["Fix stuff"],
            summary="OK",
        )
        assert r.tier == SLATier.GOLD
        assert r.overall_breach_probability == 0.05
        assert r.overall_risk_score == 5.0
        assert r.total_estimated_penalty == 750.0
        assert r.monthly_revenue == 100_000.0
        assert len(r.recommendations) == 1
        assert r.summary == "OK"

    def test_empty_lists(self):
        r = SLARiskReport(
            tier=SLATier.BRONZE,
            overall_breach_probability=0.0,
            overall_risk_score=0.0,
            component_risks=[],
            breach_scenarios=[],
            total_estimated_penalty=0.0,
            monthly_revenue=0.0,
            recommendations=[],
            summary="",
        )
        assert r.component_risks == []
        assert r.breach_scenarios == []
        assert r.recommendations == []


# ---------------------------------------------------------------------------
# 6. Module-level constants
# ---------------------------------------------------------------------------


class TestModuleConstants:
    def test_health_base_probability_healthy(self):
        assert _HEALTH_BASE_PROBABILITY[HealthStatus.HEALTHY] == 0.01

    def test_health_base_probability_degraded(self):
        assert _HEALTH_BASE_PROBABILITY[HealthStatus.DEGRADED] == 0.15

    def test_health_base_probability_overloaded(self):
        assert _HEALTH_BASE_PROBABILITY[HealthStatus.OVERLOADED] == 0.35

    def test_health_base_probability_down(self):
        assert _HEALTH_BASE_PROBABILITY[HealthStatus.DOWN] == 0.95

    def test_month_minutes(self):
        assert _MONTH_MINUTES == 30.0 * 24.0 * 60.0


# ---------------------------------------------------------------------------
# 7. Empty Graph Tests
# ---------------------------------------------------------------------------


class TestEmptyGraph:
    def test_analyze_empty(self):
        g = InfraGraph()
        q = SLARiskQuantifier(g)
        report = q.analyze()
        assert report.overall_breach_probability == 0.0
        assert report.overall_risk_score == 0.0
        assert report.component_risks == []
        assert report.total_estimated_penalty == 0.0

    def test_empty_graph_default_tier(self):
        g = InfraGraph()
        q = SLARiskQuantifier(g)
        report = q.analyze()
        assert report.tier == SLATier.GOLD

    def test_empty_graph_recommendations(self):
        g = InfraGraph()
        q = SLARiskQuantifier(g)
        report = q.analyze()
        assert len(report.recommendations) == 1
        assert "No components" in report.recommendations[0]

    def test_empty_graph_no_scenarios(self):
        g = InfraGraph()
        q = SLARiskQuantifier(g)
        report = q.analyze()
        assert report.breach_scenarios == []

    def test_empty_graph_summary(self):
        g = InfraGraph()
        q = SLARiskQuantifier(g)
        report = q.analyze()
        assert "gold" in report.summary.lower()


# ---------------------------------------------------------------------------
# 8. All Tiers Tests
# ---------------------------------------------------------------------------


class TestAllTiers:
    @pytest.mark.parametrize("tier", list(SLATier))
    def test_analyze_each_tier(self, tier: SLATier):
        g = _graph(_comp("app", "App"))
        q = SLARiskQuantifier(g, tier=tier)
        report = q.analyze()
        assert report.tier == tier

    def test_platinum_highest_penalty_rate(self):
        g = _graph(_comp("app", "App"))
        q = SLARiskQuantifier(g, tier=SLATier.PLATINUM, monthly_revenue=100_000.0)
        report_p = q.analyze()
        q.set_tier(SLATier.BRONZE)
        report_b = q.analyze()
        assert report_p.total_estimated_penalty > report_b.total_estimated_penalty

    def test_set_tier_changes_output(self):
        g = _graph(_comp("app", "App"))
        q = SLARiskQuantifier(g, tier=SLATier.GOLD)
        r1 = q.analyze()
        q.set_tier(SLATier.PLATINUM)
        r2 = q.analyze()
        assert r1.tier == SLATier.GOLD
        assert r2.tier == SLATier.PLATINUM


# ---------------------------------------------------------------------------
# 9. Single Component Tests
# ---------------------------------------------------------------------------


class TestSingleComponent:
    def test_healthy_single_replica(self):
        g = _graph(_comp("app", "App"))
        q = SLARiskQuantifier(g)
        report = q.analyze()
        assert len(report.component_risks) == 1
        cr = report.component_risks[0]
        assert cr.component_id == "app"
        assert cr.component_name == "App"
        assert cr.breach_probability == pytest.approx(0.01, abs=0.001)

    def test_healthy_single_risk_factors(self):
        g = _graph(_comp("app", "App"))
        q = SLARiskQuantifier(g)
        report = q.analyze()
        cr = report.component_risks[0]
        assert "Single replica (no redundancy)" in cr.risk_factors
        assert "Failover not enabled" in cr.risk_factors

    def test_healthy_with_failover(self):
        g = _graph(_comp("app", "App", failover=True))
        q = SLARiskQuantifier(g)
        report = q.analyze()
        cr = report.component_risks[0]
        assert cr.breach_probability == pytest.approx(0.003, abs=0.001)
        assert "Failover not enabled" not in cr.risk_factors

    def test_healthy_with_replicas(self):
        g = _graph(_comp("app", "App", replicas=3))
        q = SLARiskQuantifier(g)
        report = q.analyze()
        cr = report.component_risks[0]
        assert cr.breach_probability == pytest.approx(0.01 / 3.0, abs=0.001)
        assert "Single replica (no redundancy)" not in cr.risk_factors

    def test_healthy_with_failover_and_replicas(self):
        g = _graph(_comp("app", "App", replicas=2, failover=True))
        q = SLARiskQuantifier(g)
        report = q.analyze()
        cr = report.component_risks[0]
        assert cr.breach_probability == pytest.approx(0.0015, abs=0.001)


# ---------------------------------------------------------------------------
# 10. All Health Status Tests
# ---------------------------------------------------------------------------


class TestAllHealthStates:
    def test_healthy_probability(self):
        g = _graph(_comp("x", "X", health=HealthStatus.HEALTHY))
        q = SLARiskQuantifier(g)
        prob = q._component_breach_probability(list(g.components.values())[0])
        assert prob == pytest.approx(0.01, abs=0.001)

    def test_degraded_probability(self):
        g = _graph(_comp("x", "X", health=HealthStatus.DEGRADED))
        q = SLARiskQuantifier(g)
        prob = q._component_breach_probability(list(g.components.values())[0])
        assert prob == pytest.approx(0.15, abs=0.001)

    def test_overloaded_probability(self):
        g = _graph(_comp("x", "X", health=HealthStatus.OVERLOADED))
        q = SLARiskQuantifier(g)
        prob = q._component_breach_probability(list(g.components.values())[0])
        assert prob == pytest.approx(0.35, abs=0.001)

    def test_down_probability(self):
        g = _graph(_comp("x", "X", health=HealthStatus.DOWN))
        q = SLARiskQuantifier(g)
        prob = q._component_breach_probability(list(g.components.values())[0])
        assert prob == pytest.approx(0.95, abs=0.001)

    def test_degraded_higher_than_healthy(self):
        g1 = _graph(_comp("x", "X", health=HealthStatus.HEALTHY))
        g2 = _graph(_comp("x", "X", health=HealthStatus.DEGRADED))
        q1 = SLARiskQuantifier(g1)
        q2 = SLARiskQuantifier(g2)
        p1 = q1._component_breach_probability(list(g1.components.values())[0])
        p2 = q2._component_breach_probability(list(g2.components.values())[0])
        assert p2 > p1

    def test_down_highest_probability(self):
        probs = {}
        for status in HealthStatus:
            g = _graph(_comp("x", "X", health=status))
            q = SLARiskQuantifier(g)
            probs[status] = q._component_breach_probability(list(g.components.values())[0])
        assert probs[HealthStatus.DOWN] >= max(
            probs[HealthStatus.HEALTHY],
            probs[HealthStatus.DEGRADED],
            probs[HealthStatus.OVERLOADED],
        )


# ---------------------------------------------------------------------------
# 11. Failover Reduction Tests
# ---------------------------------------------------------------------------


class TestFailoverReduction:
    def test_failover_reduces_probability(self):
        comp_no = _comp("x", "X")
        comp_fo = _comp("x", "X", failover=True)
        g1 = _graph(comp_no)
        g2 = _graph(comp_fo)
        q1 = SLARiskQuantifier(g1)
        q2 = SLARiskQuantifier(g2)
        p1 = q1._component_breach_probability(comp_no)
        p2 = q2._component_breach_probability(comp_fo)
        assert p2 < p1
        assert p2 == pytest.approx(p1 * 0.3, abs=0.001)

    def test_failover_factor_is_0_3(self):
        comp = _comp("x", "X", failover=True)
        g = _graph(comp)
        q = SLARiskQuantifier(g)
        prob = q._component_breach_probability(comp)
        assert prob == pytest.approx(0.01 * 0.3, abs=0.0001)

    def test_failover_with_degraded(self):
        comp = _comp("x", "X", health=HealthStatus.DEGRADED, failover=True)
        g = _graph(comp)
        q = SLARiskQuantifier(g)
        prob = q._component_breach_probability(comp)
        assert prob == pytest.approx(0.15 * 0.3, abs=0.001)


# ---------------------------------------------------------------------------
# 12. Replica Reduction Tests
# ---------------------------------------------------------------------------


class TestReplicaReduction:
    def test_two_replicas(self):
        comp = _comp("x", "X", replicas=2)
        g = _graph(comp)
        q = SLARiskQuantifier(g)
        prob = q._component_breach_probability(comp)
        assert prob == pytest.approx(0.01 / 2.0, abs=0.001)

    def test_three_replicas(self):
        comp = _comp("x", "X", replicas=3)
        g = _graph(comp)
        q = SLARiskQuantifier(g)
        prob = q._component_breach_probability(comp)
        assert prob == pytest.approx(0.01 / 3.0, abs=0.001)

    def test_five_replicas(self):
        comp = _comp("x", "X", replicas=5)
        g = _graph(comp)
        q = SLARiskQuantifier(g)
        prob = q._component_breach_probability(comp)
        assert prob == pytest.approx(0.01 / 5.0, abs=0.001)

    def test_replicas_and_failover(self):
        comp = _comp("x", "X", replicas=4, failover=True)
        g = _graph(comp)
        q = SLARiskQuantifier(g)
        prob = q._component_breach_probability(comp)
        assert prob == pytest.approx(0.01 * 0.3 / 4.0, abs=0.0001)

    def test_more_replicas_lower_probability(self):
        probs = []
        for r in [1, 2, 3, 5, 10]:
            comp = _comp("x", "X", replicas=r)
            g = _graph(comp)
            q = SLARiskQuantifier(g)
            probs.append(q._component_breach_probability(comp))
        for i in range(len(probs) - 1):
            assert probs[i] > probs[i + 1]


# ---------------------------------------------------------------------------
# 13. Breach Probability Math Tests
# ---------------------------------------------------------------------------


class TestBreachProbabilityMath:
    def test_single_component_overall(self):
        g = _graph(_comp("x", "X"))
        q = SLARiskQuantifier(g)
        report = q.analyze()
        assert report.overall_breach_probability == pytest.approx(0.01, abs=0.001)

    def test_two_component_parallel_reliability(self):
        g = _graph(_comp("a", "A"), _comp("b", "B"))
        q = SLARiskQuantifier(g)
        report = q.analyze()
        # 1 - (1-0.01) * (1-0.01) = 1 - 0.99*0.99 = 1 - 0.9801 = 0.0199
        assert report.overall_breach_probability == pytest.approx(0.0199, abs=0.001)

    def test_three_component_parallel_reliability(self):
        g = _graph(_comp("a", "A"), _comp("b", "B"), _comp("c", "C"))
        q = SLARiskQuantifier(g)
        report = q.analyze()
        # 1 - (0.99)^3 = 1 - 0.970299 = 0.029701
        assert report.overall_breach_probability == pytest.approx(0.029701, abs=0.001)

    def test_mixed_health_parallel_reliability(self):
        g = _graph(
            _comp("a", "A", health=HealthStatus.HEALTHY),
            _comp("b", "B", health=HealthStatus.DEGRADED),
        )
        q = SLARiskQuantifier(g)
        report = q.analyze()
        # 1 - (1-0.01) * (1-0.15) = 1 - 0.99*0.85 = 1 - 0.8415 = 0.1585
        assert report.overall_breach_probability == pytest.approx(0.1585, abs=0.001)

    def test_all_down_very_high_probability(self):
        g = _graph(
            _comp("a", "A", health=HealthStatus.DOWN),
            _comp("b", "B", health=HealthStatus.DOWN),
        )
        q = SLARiskQuantifier(g)
        report = q.analyze()
        # 1 - (1-0.95)^2 = 1 - 0.0025 = 0.9975
        assert report.overall_breach_probability == pytest.approx(0.9975, abs=0.001)

    def test_probability_bounded_0_1(self):
        g = _graph(_comp("x", "X", health=HealthStatus.DOWN))
        q = SLARiskQuantifier(g)
        report = q.analyze()
        assert 0.0 <= report.overall_breach_probability <= 1.0

    def test_many_components_probability_increases(self):
        comps1 = [_comp(f"c{i}", f"C{i}") for i in range(2)]
        comps2 = [_comp(f"c{i}", f"C{i}") for i in range(10)]
        g1 = _graph(*comps1)
        g2 = _graph(*comps2)
        q1 = SLARiskQuantifier(g1)
        q2 = SLARiskQuantifier(g2)
        r1 = q1.analyze()
        r2 = q2.analyze()
        assert r2.overall_breach_probability > r1.overall_breach_probability


# ---------------------------------------------------------------------------
# 14. Penalty Calculation Tests
# ---------------------------------------------------------------------------


class TestPenaltyCalculation:
    def test_basic_penalty(self):
        g = _graph(_comp("x", "X"))
        q = SLARiskQuantifier(g, monthly_revenue=100_000.0, tier=SLATier.GOLD)
        report = q.analyze()
        expected = 100_000.0 * 0.15 * 0.01
        assert report.total_estimated_penalty == pytest.approx(expected, abs=1.0)

    def test_zero_revenue_zero_penalty(self):
        g = _graph(_comp("x", "X"))
        q = SLARiskQuantifier(g, monthly_revenue=0.0)
        report = q.analyze()
        assert report.total_estimated_penalty == 0.0

    def test_higher_revenue_higher_penalty(self):
        g = _graph(_comp("x", "X"))
        q1 = SLARiskQuantifier(g, monthly_revenue=10_000.0)
        q2 = SLARiskQuantifier(g, monthly_revenue=100_000.0)
        r1 = q1.analyze()
        r2 = q2.analyze()
        assert r2.total_estimated_penalty > r1.total_estimated_penalty

    def test_penalty_proportional_to_revenue(self):
        g = _graph(_comp("x", "X"))
        q1 = SLARiskQuantifier(g, monthly_revenue=50_000.0)
        q2 = SLARiskQuantifier(g, monthly_revenue=100_000.0)
        r1 = q1.analyze()
        r2 = q2.analyze()
        assert r2.total_estimated_penalty == pytest.approx(
            r1.total_estimated_penalty * 2.0, abs=0.01
        )

    def test_platinum_penalty_vs_bronze(self):
        g = _graph(_comp("x", "X"))
        q_p = SLARiskQuantifier(g, tier=SLATier.PLATINUM, monthly_revenue=100_000.0)
        q_b = SLARiskQuantifier(g, tier=SLATier.BRONZE, monthly_revenue=100_000.0)
        r_p = q_p.analyze()
        r_b = q_b.analyze()
        assert r_p.total_estimated_penalty == pytest.approx(
            r_b.total_estimated_penalty * 5.0, abs=0.01
        )


# ---------------------------------------------------------------------------
# 15. Revenue Setting Tests
# ---------------------------------------------------------------------------


class TestRevenueSetting:
    def test_set_revenue(self):
        g = _graph(_comp("x", "X"))
        q = SLARiskQuantifier(g, monthly_revenue=50_000.0)
        r1 = q.analyze()
        assert r1.monthly_revenue == 50_000.0
        q.set_revenue(200_000.0)
        r2 = q.analyze()
        assert r2.monthly_revenue == 200_000.0

    def test_set_revenue_affects_penalty(self):
        g = _graph(_comp("x", "X"))
        q = SLARiskQuantifier(g, monthly_revenue=50_000.0)
        r1 = q.analyze()
        q.set_revenue(100_000.0)
        r2 = q.analyze()
        assert r2.total_estimated_penalty == pytest.approx(
            r1.total_estimated_penalty * 2.0, abs=0.01
        )


# ---------------------------------------------------------------------------
# 16. Tier Changing Tests
# ---------------------------------------------------------------------------


class TestTierChanging:
    def test_set_tier(self):
        g = _graph(_comp("x", "X"))
        q = SLARiskQuantifier(g, tier=SLATier.GOLD)
        r1 = q.analyze()
        assert r1.tier == SLATier.GOLD
        q.set_tier(SLATier.SILVER)
        r2 = q.analyze()
        assert r2.tier == SLATier.SILVER

    def test_set_tier_affects_penalty_rate(self):
        g = _graph(_comp("x", "X"))
        q = SLARiskQuantifier(g, tier=SLATier.GOLD, monthly_revenue=100_000.0)
        r_gold = q.analyze()
        q.set_tier(SLATier.PLATINUM)
        r_plat = q.analyze()
        assert r_plat.total_estimated_penalty > r_gold.total_estimated_penalty


# ---------------------------------------------------------------------------
# 17. Risk Score Tests
# ---------------------------------------------------------------------------


class TestRiskScore:
    def test_risk_score_is_probability_times_100(self):
        g = _graph(_comp("x", "X"))
        q = SLARiskQuantifier(g)
        report = q.analyze()
        cr = report.component_risks[0]
        assert cr.risk_score == pytest.approx(cr.breach_probability * 100.0, abs=0.01)

    def test_overall_risk_score(self):
        g = _graph(_comp("x", "X"))
        q = SLARiskQuantifier(g)
        report = q.analyze()
        assert report.overall_risk_score == pytest.approx(
            report.overall_breach_probability * 100.0, abs=0.01
        )

    def test_risk_score_capped_at_100(self):
        g = _graph(_comp("x", "X", health=HealthStatus.DOWN))
        q = SLARiskQuantifier(g)
        report = q.analyze()
        assert report.overall_risk_score <= 100.0
        for cr in report.component_risks:
            assert cr.risk_score <= 100.0


# ---------------------------------------------------------------------------
# 18. Risk Factors Tests
# ---------------------------------------------------------------------------


class TestRiskFactors:
    def test_down_factor(self):
        comp = _comp("x", "X", health=HealthStatus.DOWN)
        g = _graph(comp)
        q = SLARiskQuantifier(g)
        factors = q._component_risk_factors(comp)
        assert "Component is DOWN" in factors

    def test_overloaded_factor(self):
        comp = _comp("x", "X", health=HealthStatus.OVERLOADED)
        g = _graph(comp)
        q = SLARiskQuantifier(g)
        factors = q._component_risk_factors(comp)
        assert "Component is OVERLOADED" in factors

    def test_degraded_factor(self):
        comp = _comp("x", "X", health=HealthStatus.DEGRADED)
        g = _graph(comp)
        q = SLARiskQuantifier(g)
        factors = q._component_risk_factors(comp)
        assert "Component is DEGRADED" in factors

    def test_single_replica_factor(self):
        comp = _comp("x", "X", replicas=1)
        g = _graph(comp)
        q = SLARiskQuantifier(g)
        factors = q._component_risk_factors(comp)
        assert "Single replica (no redundancy)" in factors

    def test_no_single_replica_factor_with_replicas(self):
        comp = _comp("x", "X", replicas=3)
        g = _graph(comp)
        q = SLARiskQuantifier(g)
        factors = q._component_risk_factors(comp)
        assert "Single replica (no redundancy)" not in factors

    def test_no_failover_factor(self):
        comp = _comp("x", "X")
        g = _graph(comp)
        q = SLARiskQuantifier(g)
        factors = q._component_risk_factors(comp)
        assert "Failover not enabled" in factors

    def test_no_failover_factor_when_enabled(self):
        comp = _comp("x", "X", failover=True)
        g = _graph(comp)
        q = SLARiskQuantifier(g)
        factors = q._component_risk_factors(comp)
        assert "Failover not enabled" not in factors

    def test_high_cpu_factor(self):
        comp = _comp("x", "X")
        comp.metrics = ResourceMetrics(cpu_percent=95.0)
        g = _graph(comp)
        q = SLARiskQuantifier(g)
        factors = q._component_risk_factors(comp)
        assert any("High CPU" in f for f in factors)

    def test_high_memory_factor(self):
        comp = _comp("x", "X")
        comp.metrics = ResourceMetrics(memory_percent=90.0)
        g = _graph(comp)
        q = SLARiskQuantifier(g)
        factors = q._component_risk_factors(comp)
        assert any("High memory" in f for f in factors)

    def test_high_disk_factor(self):
        comp = _comp("x", "X")
        comp.metrics = ResourceMetrics(disk_percent=85.0)
        g = _graph(comp)
        q = SLARiskQuantifier(g)
        factors = q._component_risk_factors(comp)
        assert any("High disk" in f for f in factors)

    def test_no_resource_factors_when_low(self):
        comp = _comp("x", "X")
        comp.metrics = ResourceMetrics(cpu_percent=30.0, memory_percent=40.0, disk_percent=20.0)
        g = _graph(comp)
        q = SLARiskQuantifier(g)
        factors = q._component_risk_factors(comp)
        assert not any("High CPU" in f for f in factors)
        assert not any("High memory" in f for f in factors)
        assert not any("High disk" in f for f in factors)

    def test_fan_in_factor(self):
        db = _comp("db", "DB", ctype=ComponentType.DATABASE)
        apps = [_comp(f"app{i}", f"App{i}") for i in range(4)]
        g = InfraGraph()
        g.add_component(db)
        for a in apps:
            g.add_component(a)
            g.add_dependency(Dependency(source_id=a.id, target_id="db", dependency_type="requires"))
        q = SLARiskQuantifier(g)
        factors = q._component_risk_factors(db)
        assert any("High fan-in" in f for f in factors)

    def test_healthy_component_no_health_factor(self):
        comp = _comp("x", "X", health=HealthStatus.HEALTHY)
        g = _graph(comp)
        q = SLARiskQuantifier(g)
        factors = q._component_risk_factors(comp)
        assert not any("DOWN" in f or "DEGRADED" in f or "OVERLOADED" in f for f in factors)


# ---------------------------------------------------------------------------
# 19. Recommendations Tests
# ---------------------------------------------------------------------------


class TestRecommendations:
    def test_critical_recommendation(self):
        g = _graph(_comp("x", "X", health=HealthStatus.DOWN))
        q = SLARiskQuantifier(g)
        report = q.analyze()
        assert any("CRITICAL" in r for r in report.recommendations)

    def test_warning_recommendation(self):
        g = _graph(_comp("x", "X", health=HealthStatus.DEGRADED))
        q = SLARiskQuantifier(g)
        report = q.analyze()
        assert any("WARNING" in r for r in report.recommendations)

    def test_single_replica_recommendation(self):
        g = _graph(_comp("x", "X"))
        q = SLARiskQuantifier(g)
        report = q.analyze()
        assert any("single replicas" in r.lower() for r in report.recommendations)

    def test_failover_recommendation(self):
        g = _graph(_comp("x", "X"))
        q = SLARiskQuantifier(g)
        report = q.analyze()
        assert any("failover" in r.lower() for r in report.recommendations)

    def test_down_recommendation(self):
        g = _graph(_comp("x", "X", health=HealthStatus.DOWN))
        q = SLARiskQuantifier(g)
        report = q.analyze()
        assert any("DOWN" in r for r in report.recommendations)

    def test_all_healthy_redundant_no_critical(self):
        g = _graph(_comp("x", "X", replicas=3, failover=True))
        q = SLARiskQuantifier(g)
        report = q.analyze()
        assert not any("CRITICAL" in r for r in report.recommendations)

    def test_acceptable_risk_message(self):
        g = _graph(_comp("x", "X", replicas=3, failover=True))
        q = SLARiskQuantifier(g)
        report = q.analyze()
        assert any("acceptable" in r.lower() for r in report.recommendations)


# ---------------------------------------------------------------------------
# 20. Breach Scenarios Tests
# ---------------------------------------------------------------------------


class TestBreachScenarios:
    def test_no_scenarios_empty_graph(self):
        g = InfraGraph()
        q = SLARiskQuantifier(g)
        report = q.analyze()
        assert report.breach_scenarios == []

    def test_spof_scenario_for_single_healthy_component(self):
        g = _graph(_comp("app", "App"))
        q = SLARiskQuantifier(g)
        report = q.analyze()
        spof = [s for s in report.breach_scenarios if "SPOF" in s.description]
        assert len(spof) == 1

    def test_no_spof_with_failover_and_replicas(self):
        g = _graph(_comp("app", "App", replicas=2, failover=True))
        q = SLARiskQuantifier(g)
        report = q.analyze()
        spof = [s for s in report.breach_scenarios if "SPOF" in s.description]
        assert len(spof) == 0

    def test_unhealthy_component_scenario(self):
        g = _graph(_comp("app", "App", health=HealthStatus.DEGRADED))
        q = SLARiskQuantifier(g)
        report = q.analyze()
        deg = [s for s in report.breach_scenarios if "degraded" in s.description]
        assert len(deg) == 1

    def test_down_component_scenario(self):
        g = _graph(_comp("app", "App", health=HealthStatus.DOWN))
        q = SLARiskQuantifier(g)
        report = q.analyze()
        down = [s for s in report.breach_scenarios if "down" in s.description]
        assert len(down) == 1

    def test_cascade_scenario_with_dependencies(self):
        c1 = _comp("app", "App")
        c2 = _comp("db", "DB", ctype=ComponentType.DATABASE)
        g = InfraGraph()
        g.add_component(c1)
        g.add_component(c2)
        g.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))
        q = SLARiskQuantifier(g)
        report = q.analyze()
        cascade = [s for s in report.breach_scenarios if "Cascade" in s.description]
        assert len(cascade) == 1

    def test_no_cascade_without_dependencies(self):
        g = _graph(_comp("a", "A"), _comp("b", "B"))
        q = SLARiskQuantifier(g)
        report = q.analyze()
        cascade = [s for s in report.breach_scenarios if "Cascade" in s.description]
        assert len(cascade) == 0

    def test_full_outage_scenario_multiple_components(self):
        g = _graph(_comp("a", "A"), _comp("b", "B"))
        q = SLARiskQuantifier(g)
        report = q.analyze()
        outage = [s for s in report.breach_scenarios if "Full" in s.description]
        assert len(outage) == 1

    def test_no_full_outage_single_component(self):
        g = _graph(_comp("a", "A"))
        q = SLARiskQuantifier(g)
        report = q.analyze()
        outage = [s for s in report.breach_scenarios if "Full" in s.description]
        assert len(outage) == 0

    def test_scenario_probability_bounded(self):
        g = _graph(
            _comp("a", "A", health=HealthStatus.DOWN),
            _comp("b", "B", health=HealthStatus.OVERLOADED),
        )
        q = SLARiskQuantifier(g)
        report = q.analyze()
        for s in report.breach_scenarios:
            assert 0.0 <= s.probability <= 1.0

    def test_scenario_penalty_nonnegative(self):
        g = _graph(_comp("a", "A"), _comp("b", "B"))
        q = SLARiskQuantifier(g)
        report = q.analyze()
        for s in report.breach_scenarios:
            assert s.estimated_penalty_dollars >= 0.0

    def test_scenario_has_mitigation(self):
        g = _graph(_comp("a", "A"))
        q = SLARiskQuantifier(g)
        report = q.analyze()
        for s in report.breach_scenarios:
            assert len(s.mitigation) > 0

    def test_scenario_affected_components_not_empty(self):
        g = _graph(_comp("a", "A"))
        q = SLARiskQuantifier(g)
        report = q.analyze()
        for s in report.breach_scenarios:
            assert len(s.affected_components) > 0


# ---------------------------------------------------------------------------
# 21. Summary Generation Tests
# ---------------------------------------------------------------------------


class TestSummaryGeneration:
    def test_summary_contains_tier(self):
        g = _graph(_comp("x", "X"))
        q = SLARiskQuantifier(g, tier=SLATier.GOLD)
        report = q.analyze()
        assert "gold" in report.summary.lower()

    def test_summary_contains_uptime(self):
        g = _graph(_comp("x", "X"))
        q = SLARiskQuantifier(g, tier=SLATier.GOLD)
        report = q.analyze()
        assert "99.90%" in report.summary

    def test_summary_contains_revenue(self):
        g = _graph(_comp("x", "X"))
        q = SLARiskQuantifier(g, monthly_revenue=100_000.0)
        report = q.analyze()
        assert "100,000" in report.summary

    def test_summary_contains_breach_probability(self):
        g = _graph(_comp("x", "X"))
        q = SLARiskQuantifier(g)
        report = q.analyze()
        assert "breach probability" in report.summary.lower()

    def test_summary_contains_risk_score(self):
        g = _graph(_comp("x", "X"))
        q = SLARiskQuantifier(g)
        report = q.analyze()
        assert "risk score" in report.summary.lower()

    def test_summary_contains_penalty(self):
        g = _graph(_comp("x", "X"))
        q = SLARiskQuantifier(g)
        report = q.analyze()
        assert "penalty" in report.summary.lower()

    def test_summary_platinum(self):
        g = _graph(_comp("x", "X"))
        q = SLARiskQuantifier(g, tier=SLATier.PLATINUM)
        report = q.analyze()
        assert "platinum" in report.summary.lower()
        assert "99.99%" in report.summary


# ---------------------------------------------------------------------------
# 22. Component Mitigation Tests
# ---------------------------------------------------------------------------


class TestComponentMitigation:
    def test_down_mitigation(self):
        comp = _comp("x", "X", health=HealthStatus.DOWN)
        m = SLARiskQuantifier._component_mitigation(comp)
        assert "Restore" in m

    def test_overloaded_mitigation(self):
        comp = _comp("x", "X", health=HealthStatus.OVERLOADED)
        m = SLARiskQuantifier._component_mitigation(comp)
        assert "Scale" in m or "reduce" in m.lower()

    def test_degraded_mitigation(self):
        comp = _comp("x", "X", health=HealthStatus.DEGRADED)
        m = SLARiskQuantifier._component_mitigation(comp)
        assert "Investigate" in m

    def test_single_replica_mitigation(self):
        comp = _comp("x", "X")
        m = SLARiskQuantifier._component_mitigation(comp)
        assert "replicas" in m.lower()

    def test_no_failover_mitigation(self):
        comp = _comp("x", "X")
        m = SLARiskQuantifier._component_mitigation(comp)
        assert "failover" in m.lower()

    def test_healthy_redundant_mitigation(self):
        comp = _comp("x", "X", replicas=3, failover=True)
        m = SLARiskQuantifier._component_mitigation(comp)
        assert m == "Monitor closely"


# ---------------------------------------------------------------------------
# 23. Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_all_healthy_low_risk(self):
        g = _graph(
            _comp("a", "A", replicas=3, failover=True),
            _comp("b", "B", replicas=3, failover=True),
        )
        q = SLARiskQuantifier(g)
        report = q.analyze()
        assert report.overall_risk_score < 1.0

    def test_all_down_high_risk(self):
        g = _graph(
            _comp("a", "A", health=HealthStatus.DOWN),
            _comp("b", "B", health=HealthStatus.DOWN),
        )
        q = SLARiskQuantifier(g)
        report = q.analyze()
        assert report.overall_risk_score > 90.0

    def test_mixed_health(self):
        g = _graph(
            _comp("a", "A", health=HealthStatus.HEALTHY, replicas=3, failover=True),
            _comp("b", "B", health=HealthStatus.DEGRADED),
            _comp("c", "C", health=HealthStatus.DOWN),
        )
        q = SLARiskQuantifier(g)
        report = q.analyze()
        assert 0.0 < report.overall_breach_probability < 1.0
        assert len(report.component_risks) == 3

    def test_single_component_with_large_replicas(self):
        g = _graph(_comp("x", "X", replicas=100))
        q = SLARiskQuantifier(g)
        report = q.analyze()
        assert report.overall_breach_probability < 0.001

    def test_default_constructor(self):
        g = _graph(_comp("x", "X"))
        q = SLARiskQuantifier(g)
        report = q.analyze()
        assert report.tier == SLATier.GOLD
        assert report.monthly_revenue == 100_000.0

    def test_component_types(self):
        for ctype in [ComponentType.LOAD_BALANCER, ComponentType.DATABASE, ComponentType.CACHE, ComponentType.QUEUE]:
            g = _graph(_comp("x", "X", ctype=ctype))
            q = SLARiskQuantifier(g)
            report = q.analyze()
            assert len(report.component_risks) == 1

    def test_many_components(self):
        comps = [_comp(f"c{i}", f"Comp{i}") for i in range(20)]
        g = _graph(*comps)
        q = SLARiskQuantifier(g)
        report = q.analyze()
        assert len(report.component_risks) == 20
        assert report.overall_breach_probability > 0.0

    def test_estimated_downtime_calculation(self):
        g = _graph(_comp("x", "X"))
        q = SLARiskQuantifier(g)
        sla_def = SLA_DEFINITIONS[SLATier.GOLD]
        downtime = q._component_estimated_downtime(0.5, sla_def)
        assert downtime == pytest.approx(0.5 * _MONTH_MINUTES, abs=0.01)

    def test_estimated_downtime_zero(self):
        g = _graph(_comp("x", "X"))
        q = SLARiskQuantifier(g)
        sla_def = SLA_DEFINITIONS[SLATier.GOLD]
        downtime = q._component_estimated_downtime(0.0, sla_def)
        assert downtime == 0.0


# ---------------------------------------------------------------------------
# 24. Multiple Component Scenarios
# ---------------------------------------------------------------------------


class TestMultipleComponents:
    def test_two_healthy_components(self):
        g = _graph(_comp("a", "A"), _comp("b", "B"))
        q = SLARiskQuantifier(g)
        report = q.analyze()
        assert len(report.component_risks) == 2
        assert report.overall_breach_probability > 0.01

    def test_mixed_failover_components(self):
        g = _graph(
            _comp("a", "A", failover=True),
            _comp("b", "B", failover=False),
        )
        q = SLARiskQuantifier(g)
        report = q.analyze()
        probs = {cr.component_id: cr.breach_probability for cr in report.component_risks}
        assert probs["a"] < probs["b"]

    def test_mixed_replicas_components(self):
        g = _graph(
            _comp("a", "A", replicas=5),
            _comp("b", "B", replicas=1),
        )
        q = SLARiskQuantifier(g)
        report = q.analyze()
        probs = {cr.component_id: cr.breach_probability for cr in report.component_risks}
        assert probs["a"] < probs["b"]

    def test_all_same_probability(self):
        g = _graph(
            _comp("a", "A", replicas=2),
            _comp("b", "B", replicas=2),
        )
        q = SLARiskQuantifier(g)
        report = q.analyze()
        probs = [cr.breach_probability for cr in report.component_risks]
        assert probs[0] == pytest.approx(probs[1], abs=0.0001)

    def test_component_with_dependencies(self):
        c1 = _comp("lb", "LB", ctype=ComponentType.LOAD_BALANCER)
        c2 = _comp("app", "App")
        c3 = _comp("db", "DB", ctype=ComponentType.DATABASE)
        g = InfraGraph()
        g.add_component(c1)
        g.add_component(c2)
        g.add_component(c3)
        g.add_dependency(Dependency(source_id="lb", target_id="app", dependency_type="requires"))
        g.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))
        q = SLARiskQuantifier(g)
        report = q.analyze()
        assert len(report.component_risks) == 3
        cascade = [s for s in report.breach_scenarios if "Cascade" in s.description]
        assert len(cascade) >= 1


# ---------------------------------------------------------------------------
# 25. Downtime Estimation Tests
# ---------------------------------------------------------------------------


class TestDowntimeEstimation:
    def test_healthy_low_downtime(self):
        g = _graph(_comp("x", "X", replicas=3, failover=True))
        q = SLARiskQuantifier(g)
        report = q.analyze()
        cr = report.component_risks[0]
        assert cr.estimated_downtime_minutes < 100.0

    def test_down_high_downtime(self):
        g = _graph(_comp("x", "X", health=HealthStatus.DOWN))
        q = SLARiskQuantifier(g)
        report = q.analyze()
        cr = report.component_risks[0]
        assert cr.estimated_downtime_minutes > 10_000.0

    def test_downtime_proportional_to_probability(self):
        g = _graph(
            _comp("a", "A", health=HealthStatus.HEALTHY),
            _comp("b", "B", health=HealthStatus.DOWN),
        )
        q = SLARiskQuantifier(g)
        report = q.analyze()
        risks = {cr.component_id: cr for cr in report.component_risks}
        assert risks["b"].estimated_downtime_minutes > risks["a"].estimated_downtime_minutes


# ---------------------------------------------------------------------------
# 26. Report Completeness Tests
# ---------------------------------------------------------------------------


class TestReportCompleteness:
    def test_report_has_all_fields(self):
        g = _graph(_comp("x", "X"))
        q = SLARiskQuantifier(g)
        report = q.analyze()
        assert isinstance(report.tier, SLATier)
        assert isinstance(report.overall_breach_probability, float)
        assert isinstance(report.overall_risk_score, float)
        assert isinstance(report.component_risks, list)
        assert isinstance(report.breach_scenarios, list)
        assert isinstance(report.total_estimated_penalty, float)
        assert isinstance(report.monthly_revenue, float)
        assert isinstance(report.recommendations, list)
        assert isinstance(report.summary, str)

    def test_component_risk_has_all_fields(self):
        g = _graph(_comp("x", "X"))
        q = SLARiskQuantifier(g)
        report = q.analyze()
        cr = report.component_risks[0]
        assert isinstance(cr.component_id, str)
        assert isinstance(cr.component_name, str)
        assert isinstance(cr.breach_probability, float)
        assert isinstance(cr.estimated_downtime_minutes, float)
        assert isinstance(cr.risk_score, float)
        assert isinstance(cr.risk_factors, list)

    def test_scenario_has_all_fields(self):
        g = _graph(_comp("x", "X"))
        q = SLARiskQuantifier(g)
        report = q.analyze()
        for s in report.breach_scenarios:
            assert isinstance(s.description, str)
            assert isinstance(s.probability, float)
            assert isinstance(s.estimated_penalty_dollars, float)
            assert isinstance(s.affected_components, list)
            assert isinstance(s.mitigation, str)

    def test_report_consistency(self):
        g = _graph(_comp("x", "X"))
        q = SLARiskQuantifier(g)
        report = q.analyze()
        assert report.overall_risk_score == pytest.approx(
            report.overall_breach_probability * 100.0, abs=0.01
        )


# ---------------------------------------------------------------------------
# 27. Constructor and Initialization Tests
# ---------------------------------------------------------------------------


class TestConstructor:
    def test_default_tier_gold(self):
        g = InfraGraph()
        q = SLARiskQuantifier(g)
        r = q.analyze()
        assert r.tier == SLATier.GOLD

    def test_default_revenue(self):
        g = InfraGraph()
        q = SLARiskQuantifier(g)
        r = q.analyze()
        assert r.monthly_revenue == 100_000.0

    def test_custom_tier(self):
        g = InfraGraph()
        q = SLARiskQuantifier(g, tier=SLATier.PLATINUM)
        r = q.analyze()
        assert r.tier == SLATier.PLATINUM

    def test_custom_revenue(self):
        g = InfraGraph()
        q = SLARiskQuantifier(g, monthly_revenue=500_000.0)
        r = q.analyze()
        assert r.monthly_revenue == 500_000.0

    def test_all_params(self):
        g = InfraGraph()
        q = SLARiskQuantifier(g, tier=SLATier.BRONZE, monthly_revenue=250_000.0)
        r = q.analyze()
        assert r.tier == SLATier.BRONZE
        assert r.monthly_revenue == 250_000.0


# ---------------------------------------------------------------------------
# 28. Deterministic Behavior Tests
# ---------------------------------------------------------------------------


class TestDeterministic:
    def test_same_input_same_output(self):
        g = _graph(_comp("x", "X"))
        q = SLARiskQuantifier(g)
        r1 = q.analyze()
        r2 = q.analyze()
        assert r1.overall_breach_probability == r2.overall_breach_probability
        assert r1.overall_risk_score == r2.overall_risk_score
        assert r1.total_estimated_penalty == r2.total_estimated_penalty

    def test_component_order_independent(self):
        g1 = _graph(_comp("a", "A"), _comp("b", "B"))
        g2 = _graph(_comp("b", "B"), _comp("a", "A"))
        q1 = SLARiskQuantifier(g1)
        q2 = SLARiskQuantifier(g2)
        r1 = q1.analyze()
        r2 = q2.analyze()
        assert r1.overall_breach_probability == pytest.approx(
            r2.overall_breach_probability, abs=0.0001
        )


# ---------------------------------------------------------------------------
# 29. Overloaded Component Tests
# ---------------------------------------------------------------------------


class TestOverloadedComponent:
    def test_overloaded_breach_probability(self):
        g = _graph(_comp("x", "X", health=HealthStatus.OVERLOADED))
        q = SLARiskQuantifier(g)
        report = q.analyze()
        cr = report.component_risks[0]
        assert cr.breach_probability == pytest.approx(0.35, abs=0.001)

    def test_overloaded_risk_score(self):
        g = _graph(_comp("x", "X", health=HealthStatus.OVERLOADED))
        q = SLARiskQuantifier(g)
        report = q.analyze()
        assert report.overall_risk_score == pytest.approx(35.0, abs=0.1)


# ---------------------------------------------------------------------------
# 30. Integration-like Tests
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_full_stack_analysis(self):
        lb = _comp("lb", "LB", ctype=ComponentType.LOAD_BALANCER, replicas=2, failover=True)
        app = _comp("app", "App", replicas=3, failover=True)
        db = _comp("db", "DB", ctype=ComponentType.DATABASE, replicas=2, failover=True)
        cache = _comp("cache", "Cache", ctype=ComponentType.CACHE)

        g = InfraGraph()
        for c in [lb, app, db, cache]:
            g.add_component(c)
        g.add_dependency(Dependency(source_id="lb", target_id="app", dependency_type="requires"))
        g.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))
        g.add_dependency(Dependency(source_id="app", target_id="cache", dependency_type="optional"))

        q = SLARiskQuantifier(g, tier=SLATier.PLATINUM, monthly_revenue=500_000.0)
        report = q.analyze()

        assert report.tier == SLATier.PLATINUM
        assert report.monthly_revenue == 500_000.0
        assert len(report.component_risks) == 4
        assert len(report.breach_scenarios) > 0
        assert len(report.recommendations) > 0
        assert report.total_estimated_penalty > 0.0

    def test_degraded_infrastructure_analysis(self):
        g = _graph(
            _comp("app", "App", health=HealthStatus.DEGRADED),
            _comp("db", "DB", ctype=ComponentType.DATABASE, health=HealthStatus.OVERLOADED),
        )
        q = SLARiskQuantifier(g, tier=SLATier.GOLD, monthly_revenue=200_000.0)
        report = q.analyze()

        assert report.overall_breach_probability > 0.3
        assert report.total_estimated_penalty > 0.0
        assert any("CRITICAL" in r or "WARNING" in r for r in report.recommendations)

    def test_tier_comparison(self):
        g = _graph(_comp("app", "App"))
        penalties = {}
        for tier in SLATier:
            q = SLARiskQuantifier(g, tier=tier, monthly_revenue=100_000.0)
            r = q.analyze()
            penalties[tier] = r.total_estimated_penalty
        assert penalties[SLATier.PLATINUM] > penalties[SLATier.BRONZE]

    def test_set_tier_and_revenue_together(self):
        g = _graph(_comp("x", "X"))
        q = SLARiskQuantifier(g, tier=SLATier.BRONZE, monthly_revenue=10_000.0)
        r1 = q.analyze()
        q.set_tier(SLATier.PLATINUM)
        q.set_revenue(500_000.0)
        r2 = q.analyze()
        assert r2.tier == SLATier.PLATINUM
        assert r2.monthly_revenue == 500_000.0
        assert r2.total_estimated_penalty > r1.total_estimated_penalty
