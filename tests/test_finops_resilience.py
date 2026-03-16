"""Tests for the FinOps-Resilience Optimizer."""

from __future__ import annotations

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    Component,
    ComponentType,
    CostProfile,
    FailoverConfig,
    HealthStatus,
    ResourceMetrics,
    SLOTarget,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.finops_resilience import (
    CostResiliencePoint,
    CostTier,
    FinOpsRecommendation,
    FinOpsResilienceEngine,
    FinOpsResilienceReport,
    InfraOption,
    OptimizationGoal,
    SLABreachCost,
    _DEFAULT_MONTHLY_COST,
    _TIER_AVAILABILITY,
    _TIER_COST_MULTIPLIER,
    _TIER_FAILOVER_SECONDS,
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
    cost=None,
    health=HealthStatus.HEALTHY,
):
    c = Component(id=cid, name=name, type=ctype, replicas=replicas)
    c.health = health
    if failover:
        c.failover = FailoverConfig(enabled=True, promotion_time_seconds=10)
    if cost:
        c.cost_profile = cost
    return c


def _graph(*comps):
    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    return g


# ---------------------------------------------------------------------------
# CostTier enum tests
# ---------------------------------------------------------------------------


class TestCostTierEnum:
    def test_on_demand_value(self):
        assert CostTier.ON_DEMAND.value == "on_demand"

    def test_reserved_value(self):
        assert CostTier.RESERVED.value == "reserved"

    def test_spot_value(self):
        assert CostTier.SPOT.value == "spot"

    def test_serverless_value(self):
        assert CostTier.SERVERLESS.value == "serverless"

    def test_all_members(self):
        assert len(CostTier) == 4

    def test_from_string(self):
        assert CostTier("on_demand") == CostTier.ON_DEMAND

    def test_is_str(self):
        assert isinstance(CostTier.SPOT, str)


# ---------------------------------------------------------------------------
# OptimizationGoal enum tests
# ---------------------------------------------------------------------------


class TestOptimizationGoalEnum:
    def test_minimize_cost(self):
        assert OptimizationGoal.MINIMIZE_COST.value == "minimize_cost"

    def test_maximize_resilience(self):
        assert OptimizationGoal.MAXIMIZE_RESILIENCE.value == "maximize_resilience"

    def test_balanced(self):
        assert OptimizationGoal.BALANCED.value == "balanced"

    def test_all_members(self):
        assert len(OptimizationGoal) == 3


# ---------------------------------------------------------------------------
# Tier constant tests
# ---------------------------------------------------------------------------


class TestTierConstants:
    def test_cost_multiplier_on_demand(self):
        assert _TIER_COST_MULTIPLIER[CostTier.ON_DEMAND] == 1.0

    def test_cost_multiplier_reserved(self):
        assert _TIER_COST_MULTIPLIER[CostTier.RESERVED] == 0.6

    def test_cost_multiplier_spot(self):
        assert _TIER_COST_MULTIPLIER[CostTier.SPOT] == 0.3

    def test_cost_multiplier_serverless(self):
        assert _TIER_COST_MULTIPLIER[CostTier.SERVERLESS] == 0.8

    def test_availability_on_demand(self):
        assert _TIER_AVAILABILITY[CostTier.ON_DEMAND] == 99.95

    def test_availability_spot_lowest(self):
        assert _TIER_AVAILABILITY[CostTier.SPOT] == 95.0

    def test_failover_seconds_serverless_fastest(self):
        assert _TIER_FAILOVER_SECONDS[CostTier.SERVERLESS] == 5.0

    def test_failover_seconds_spot_slowest(self):
        assert _TIER_FAILOVER_SECONDS[CostTier.SPOT] == 120.0

    def test_default_monthly_cost_database(self):
        assert _DEFAULT_MONTHLY_COST[ComponentType.DATABASE] == 150.0

    def test_default_monthly_cost_external_api_zero(self):
        assert _DEFAULT_MONTHLY_COST[ComponentType.EXTERNAL_API] == 0.0


# ---------------------------------------------------------------------------
# InfraOption model tests
# ---------------------------------------------------------------------------


class TestInfraOption:
    def test_create_basic(self):
        opt = InfraOption(
            component_id="app1",
            cost_tier=CostTier.ON_DEMAND,
            monthly_cost=100.0,
        )
        assert opt.component_id == "app1"
        assert opt.monthly_cost == 100.0

    def test_default_availability(self):
        opt = InfraOption(
            component_id="x", cost_tier=CostTier.SPOT, monthly_cost=30.0
        )
        assert opt.availability_percent == 99.9

    def test_default_failover_time(self):
        opt = InfraOption(
            component_id="x", cost_tier=CostTier.SPOT, monthly_cost=30.0
        )
        assert opt.failover_time_seconds == 30.0

    def test_default_replicas(self):
        opt = InfraOption(
            component_id="x", cost_tier=CostTier.SPOT, monthly_cost=30.0
        )
        assert opt.replicas == 1

    def test_custom_values(self):
        opt = InfraOption(
            component_id="db1",
            cost_tier=CostTier.RESERVED,
            monthly_cost=500.0,
            availability_percent=99.99,
            failover_time_seconds=5.0,
            replicas=3,
        )
        assert opt.availability_percent == 99.99
        assert opt.failover_time_seconds == 5.0
        assert opt.replicas == 3


# ---------------------------------------------------------------------------
# CostResiliencePoint model tests
# ---------------------------------------------------------------------------


class TestCostResiliencePoint:
    def test_basic_creation(self):
        pt = CostResiliencePoint(monthly_cost=100.0, resilience_score=75.0)
        assert pt.monthly_cost == 100.0
        assert pt.resilience_score == 75.0

    def test_default_config(self):
        pt = CostResiliencePoint(monthly_cost=0.0, resilience_score=0.0)
        assert pt.configuration == {}

    def test_default_description(self):
        pt = CostResiliencePoint(monthly_cost=0.0, resilience_score=0.0)
        assert pt.tradeoff_description == ""

    def test_with_config(self):
        pt = CostResiliencePoint(
            monthly_cost=50.0,
            resilience_score=80.0,
            configuration={"app": CostTier.RESERVED},
            tradeoff_description="test desc",
        )
        assert pt.configuration["app"] == CostTier.RESERVED
        assert pt.tradeoff_description == "test desc"


# ---------------------------------------------------------------------------
# SLABreachCost model tests
# ---------------------------------------------------------------------------


class TestSLABreachCost:
    def test_creation(self):
        sla = SLABreachCost(
            component_id="db1",
            sla_target=99.9,
            current_availability=99.5,
            annual_breach_probability=0.1,
            annual_expected_penalty=1200.0,
            penalty_per_incident=100.0,
        )
        assert sla.component_id == "db1"
        assert sla.sla_target == 99.9
        assert sla.annual_expected_penalty == 1200.0


# ---------------------------------------------------------------------------
# FinOpsRecommendation model tests
# ---------------------------------------------------------------------------


class TestFinOpsRecommendation:
    def test_creation(self):
        rec = FinOpsRecommendation(
            action="Switch to spot",
            monthly_savings=50.0,
            resilience_impact=-10.0,
            risk_description="Interruption risk",
            priority=1,
        )
        assert rec.action == "Switch to spot"
        assert rec.monthly_savings == 50.0
        assert rec.priority == 1

    def test_negative_resilience_impact(self):
        rec = FinOpsRecommendation(
            action="test", monthly_savings=0.0,
            resilience_impact=-5.0, risk_description="", priority=1,
        )
        assert rec.resilience_impact < 0


# ---------------------------------------------------------------------------
# FinOpsResilienceReport model tests
# ---------------------------------------------------------------------------


class TestFinOpsResilienceReport:
    def test_creation(self):
        report = FinOpsResilienceReport(
            current_monthly_cost=500.0,
            current_resilience_score=75.0,
        )
        assert report.current_monthly_cost == 500.0
        assert report.optimal_configurations == []
        assert report.sla_breach_costs == []
        assert report.recommendations == []
        assert report.total_potential_savings == 0.0
        assert report.total_annual_risk_cost == 0.0


# ---------------------------------------------------------------------------
# FinOpsResilienceEngine — calculate_current_cost
# ---------------------------------------------------------------------------


class TestCalculateCurrentCost:
    def test_empty_graph(self):
        g = _graph()
        engine = FinOpsResilienceEngine(g)
        assert engine.calculate_current_cost() == 0.0

    def test_single_component_default_cost(self):
        c = _comp("app1", "App", ctype=ComponentType.APP_SERVER)
        g = _graph(c)
        engine = FinOpsResilienceEngine(g)
        # default APP_SERVER = 80 * 1 replica
        assert engine.calculate_current_cost() == 80.0

    def test_single_component_with_cost_profile(self):
        c = _comp("app1", "App", cost=CostProfile(hourly_infra_cost=1.0))
        g = _graph(c)
        engine = FinOpsResilienceEngine(g)
        # 1.0 * 730 * 1 replica = 730
        assert engine.calculate_current_cost() == 730.0

    def test_multiple_components(self):
        c1 = _comp("db", "DB", ctype=ComponentType.DATABASE)
        c2 = _comp("cache", "Cache", ctype=ComponentType.CACHE)
        g = _graph(c1, c2)
        engine = FinOpsResilienceEngine(g)
        # 150 + 60 = 210
        assert engine.calculate_current_cost() == 210.0

    def test_replicas_multiply_default_cost(self):
        c = _comp("app1", "App", ctype=ComponentType.APP_SERVER, replicas=3)
        g = _graph(c)
        engine = FinOpsResilienceEngine(g)
        # 80 * 3 = 240
        assert engine.calculate_current_cost() == 240.0

    def test_replicas_multiply_hourly_cost(self):
        c = _comp("app1", "App", replicas=2, cost=CostProfile(hourly_infra_cost=2.0))
        g = _graph(c)
        engine = FinOpsResilienceEngine(g)
        # 2.0 * 730 * 2 = 2920
        assert engine.calculate_current_cost() == 2920.0

    def test_external_api_zero_cost(self):
        c = _comp("ext", "External", ctype=ComponentType.EXTERNAL_API)
        g = _graph(c)
        engine = FinOpsResilienceEngine(g)
        assert engine.calculate_current_cost() == 0.0

    def test_dns_cost(self):
        c = _comp("dns1", "DNS", ctype=ComponentType.DNS)
        g = _graph(c)
        engine = FinOpsResilienceEngine(g)
        assert engine.calculate_current_cost() == 10.0

    def test_custom_type_cost(self):
        c = _comp("custom1", "Custom", ctype=ComponentType.CUSTOM)
        g = _graph(c)
        engine = FinOpsResilienceEngine(g)
        assert engine.calculate_current_cost() == 50.0

    def test_queue_cost(self):
        c = _comp("q1", "Queue", ctype=ComponentType.QUEUE)
        g = _graph(c)
        engine = FinOpsResilienceEngine(g)
        assert engine.calculate_current_cost() == 40.0

    def test_storage_cost(self):
        c = _comp("s1", "Storage", ctype=ComponentType.STORAGE)
        g = _graph(c)
        engine = FinOpsResilienceEngine(g)
        assert engine.calculate_current_cost() == 30.0


# ---------------------------------------------------------------------------
# FinOpsResilienceEngine — evaluate_option
# ---------------------------------------------------------------------------


class TestEvaluateOption:
    def test_high_availability_option(self):
        g = _graph(_comp("app1", "App"))
        engine = FinOpsResilienceEngine(g)
        opt = InfraOption(
            component_id="app1",
            cost_tier=CostTier.RESERVED,
            monthly_cost=200.0,
            availability_percent=99.99,
            failover_time_seconds=5.0,
            replicas=3,
        )
        pt = engine.evaluate_option(opt)
        assert pt.resilience_score == 100.0
        assert pt.monthly_cost == 200.0

    def test_low_availability_option(self):
        g = _graph(_comp("app1", "App"))
        engine = FinOpsResilienceEngine(g)
        opt = InfraOption(
            component_id="app1",
            cost_tier=CostTier.SPOT,
            monthly_cost=30.0,
            availability_percent=90.0,
            failover_time_seconds=300.0,
            replicas=1,
        )
        pt = engine.evaluate_option(opt)
        assert pt.resilience_score < 20

    def test_config_maps_component_to_tier(self):
        g = _graph(_comp("db1", "DB"))
        engine = FinOpsResilienceEngine(g)
        opt = InfraOption(
            component_id="db1",
            cost_tier=CostTier.SERVERLESS,
            monthly_cost=120.0,
        )
        pt = engine.evaluate_option(opt)
        assert pt.configuration["db1"] == CostTier.SERVERLESS

    def test_description_contains_tier(self):
        g = _graph(_comp("x", "X"))
        engine = FinOpsResilienceEngine(g)
        opt = InfraOption(
            component_id="x", cost_tier=CostTier.ON_DEMAND, monthly_cost=50.0
        )
        pt = engine.evaluate_option(opt)
        assert "on_demand" in pt.tradeoff_description

    def test_description_contains_cost(self):
        g = _graph(_comp("x", "X"))
        engine = FinOpsResilienceEngine(g)
        opt = InfraOption(
            component_id="x", cost_tier=CostTier.SPOT, monthly_cost=75.0
        )
        pt = engine.evaluate_option(opt)
        assert "$75" in pt.tradeoff_description

    def test_score_availability_99(self):
        g = _graph(_comp("x", "X"))
        engine = FinOpsResilienceEngine(g)
        opt = InfraOption(
            component_id="x", cost_tier=CostTier.SPOT,
            monthly_cost=10.0, availability_percent=99.0,
            failover_time_seconds=30.0, replicas=1,
        )
        pt = engine.evaluate_option(opt)
        # 30(avail99) + 5(1rep) + 10(30s failover) = 45
        assert pt.resilience_score == 45.0

    def test_score_availability_95(self):
        g = _graph(_comp("x", "X"))
        engine = FinOpsResilienceEngine(g)
        opt = InfraOption(
            component_id="x", cost_tier=CostTier.SPOT,
            monthly_cost=10.0, availability_percent=95.0,
            failover_time_seconds=60.0, replicas=1,
        )
        pt = engine.evaluate_option(opt)
        # 15(avail95) + 5(1rep) + 5(60s failover) = 25
        assert pt.resilience_score == 25.0

    def test_score_2_replicas(self):
        g = _graph(_comp("x", "X"))
        engine = FinOpsResilienceEngine(g)
        opt = InfraOption(
            component_id="x", cost_tier=CostTier.ON_DEMAND,
            monthly_cost=100.0, availability_percent=99.9,
            failover_time_seconds=15.0, replicas=2,
        )
        pt = engine.evaluate_option(opt)
        # 40(avail99.9) + 20(2rep) + 15(15s) = 75
        assert pt.resilience_score == 75.0

    def test_score_failover_over_60(self):
        g = _graph(_comp("x", "X"))
        engine = FinOpsResilienceEngine(g)
        opt = InfraOption(
            component_id="x", cost_tier=CostTier.SPOT,
            monthly_cost=10.0, availability_percent=99.9,
            failover_time_seconds=120.0, replicas=1,
        )
        pt = engine.evaluate_option(opt)
        # 40 + 5 + 2 = 47
        assert pt.resilience_score == 47.0

    def test_score_capped_at_100(self):
        g = _graph(_comp("x", "X"))
        engine = FinOpsResilienceEngine(g)
        opt = InfraOption(
            component_id="x", cost_tier=CostTier.RESERVED,
            monthly_cost=500.0, availability_percent=99.999,
            failover_time_seconds=1.0, replicas=5,
        )
        pt = engine.evaluate_option(opt)
        assert pt.resilience_score == 100.0

    def test_availability_below_95(self):
        g = _graph(_comp("x", "X"))
        engine = FinOpsResilienceEngine(g)
        opt = InfraOption(
            component_id="x", cost_tier=CostTier.SPOT,
            monthly_cost=5.0, availability_percent=80.0,
            failover_time_seconds=300.0, replicas=1,
        )
        pt = engine.evaluate_option(opt)
        # 5(avail<95) + 5(1rep) + 2(>60s) = 12
        assert pt.resilience_score == 12.0


# ---------------------------------------------------------------------------
# FinOpsResilienceEngine — generate_pareto_frontier
# ---------------------------------------------------------------------------


class TestGenerateParetoFrontier:
    def test_empty_options(self):
        g = _graph(_comp("app1", "App"))
        engine = FinOpsResilienceEngine(g)
        result = engine.generate_pareto_frontier({})
        assert result == []

    def test_single_component_single_option(self):
        g = _graph(_comp("app1", "App"))
        engine = FinOpsResilienceEngine(g)
        opts = {
            "app1": [
                InfraOption(
                    component_id="app1",
                    cost_tier=CostTier.ON_DEMAND,
                    monthly_cost=100.0,
                )
            ]
        }
        result = engine.generate_pareto_frontier(opts)
        assert len(result) == 1
        assert result[0].monthly_cost == 100.0

    def test_single_component_two_options(self):
        g = _graph(_comp("app1", "App"))
        engine = FinOpsResilienceEngine(g)
        opts = {
            "app1": [
                InfraOption(
                    component_id="app1",
                    cost_tier=CostTier.SPOT,
                    monthly_cost=30.0,
                    availability_percent=95.0,
                ),
                InfraOption(
                    component_id="app1",
                    cost_tier=CostTier.RESERVED,
                    monthly_cost=200.0,
                    availability_percent=99.99,
                    replicas=3,
                    failover_time_seconds=5.0,
                ),
            ]
        }
        result = engine.generate_pareto_frontier(opts)
        # Both should be Pareto-optimal (one cheaper, one more resilient)
        assert len(result) == 2
        assert result[0].monthly_cost < result[1].monthly_cost
        assert result[0].resilience_score < result[1].resilience_score

    def test_dominated_option_removed(self):
        g = _graph(_comp("a", "A"))
        engine = FinOpsResilienceEngine(g)
        opts = {
            "a": [
                InfraOption(
                    component_id="a", cost_tier=CostTier.ON_DEMAND,
                    monthly_cost=100.0, availability_percent=99.9,
                    replicas=2, failover_time_seconds=15.0,
                ),
                InfraOption(
                    component_id="a", cost_tier=CostTier.RESERVED,
                    monthly_cost=80.0, availability_percent=99.99,
                    replicas=3, failover_time_seconds=5.0,
                ),
                InfraOption(
                    component_id="a", cost_tier=CostTier.SPOT,
                    monthly_cost=120.0, availability_percent=99.0,
                    replicas=1, failover_time_seconds=60.0,
                ),
            ]
        }
        result = engine.generate_pareto_frontier(opts)
        # The RESERVED option dominates ON_DEMAND (cheaper AND better resilience)
        # SPOT is dominated by RESERVED too (more expensive AND worse)
        # So only RESERVED should survive
        assert len(result) == 1
        assert result[0].configuration["a"] == CostTier.RESERVED

    def test_two_components_cross_product(self):
        g = _graph(_comp("a", "A"), _comp("b", "B"))
        engine = FinOpsResilienceEngine(g)
        opts = {
            "a": [
                InfraOption(component_id="a", cost_tier=CostTier.SPOT, monthly_cost=30.0, availability_percent=95.0),
                InfraOption(component_id="a", cost_tier=CostTier.ON_DEMAND, monthly_cost=100.0, availability_percent=99.9),
            ],
            "b": [
                InfraOption(component_id="b", cost_tier=CostTier.SPOT, monthly_cost=20.0, availability_percent=95.0),
                InfraOption(component_id="b", cost_tier=CostTier.ON_DEMAND, monthly_cost=80.0, availability_percent=99.9),
            ],
        }
        result = engine.generate_pareto_frontier(opts)
        # 4 combos; frontier should be at least 2 (cheapest + most resilient)
        assert len(result) >= 2
        costs = [p.monthly_cost for p in result]
        assert costs == sorted(costs)

    def test_pareto_sorted_by_cost(self):
        g = _graph(_comp("a", "A"))
        engine = FinOpsResilienceEngine(g)
        opts = {
            "a": [
                InfraOption(component_id="a", cost_tier=CostTier.SPOT, monthly_cost=10.0, availability_percent=90.0),
                InfraOption(component_id="a", cost_tier=CostTier.ON_DEMAND, monthly_cost=50.0, availability_percent=99.0),
                InfraOption(component_id="a", cost_tier=CostTier.RESERVED, monthly_cost=100.0, availability_percent=99.99, replicas=3, failover_time_seconds=5.0),
            ]
        }
        result = engine.generate_pareto_frontier(opts)
        for i in range(len(result) - 1):
            assert result[i].monthly_cost <= result[i + 1].monthly_cost

    def test_empty_option_list_for_component(self):
        g = _graph(_comp("a", "A"))
        engine = FinOpsResilienceEngine(g)
        opts = {"a": []}
        result = engine.generate_pareto_frontier(opts)
        assert result == []

    def test_config_has_all_component_ids(self):
        g = _graph(_comp("a", "A"), _comp("b", "B"))
        engine = FinOpsResilienceEngine(g)
        opts = {
            "a": [InfraOption(component_id="a", cost_tier=CostTier.SPOT, monthly_cost=10.0)],
            "b": [InfraOption(component_id="b", cost_tier=CostTier.ON_DEMAND, monthly_cost=50.0)],
        }
        result = engine.generate_pareto_frontier(opts)
        assert len(result) == 1
        assert "a" in result[0].configuration
        assert "b" in result[0].configuration

    def test_description_format(self):
        g = _graph(_comp("x", "X"))
        engine = FinOpsResilienceEngine(g)
        opts = {
            "x": [InfraOption(component_id="x", cost_tier=CostTier.SPOT, monthly_cost=10.0)]
        }
        result = engine.generate_pareto_frontier(opts)
        assert "Config:" in result[0].tradeoff_description


# ---------------------------------------------------------------------------
# FinOpsResilienceEngine — assess_sla_breach_cost
# ---------------------------------------------------------------------------


class TestAssessSLABreachCost:
    def test_component_not_found(self):
        g = _graph()
        engine = FinOpsResilienceEngine(g)
        sla = engine.assess_sla_breach_cost("nonexistent", 99.9)
        assert sla.component_id == "nonexistent"
        assert sla.current_availability == 0.0
        assert sla.annual_breach_probability == 1.0

    def test_healthy_single_replica(self):
        c = _comp("app1", "App")
        g = _graph(c)
        engine = FinOpsResilienceEngine(g)
        sla = engine.assess_sla_breach_cost("app1", 99.9)
        assert sla.sla_target == 99.9
        assert sla.current_availability > 0

    def test_zero_gap_no_breach(self):
        c = _comp("app1", "App", replicas=3, failover=True)
        c.autoscaling = AutoScalingConfig(enabled=True)
        g = _graph(c)
        engine = FinOpsResilienceEngine(g)
        sla = engine.assess_sla_breach_cost("app1", 99.0)
        assert sla.annual_breach_probability == 0.0
        assert sla.annual_expected_penalty == 0.0

    def test_large_gap_high_breach(self):
        c = _comp("app1", "App", health=HealthStatus.DOWN)
        g = _graph(c)
        engine = FinOpsResilienceEngine(g)
        sla = engine.assess_sla_breach_cost("app1", 99.99)
        assert sla.annual_breach_probability > 0.5

    def test_penalty_proportional_to_sla_credit(self):
        c = _comp("app1", "App", cost=CostProfile(hourly_infra_cost=1.0, sla_credit_percent=10.0))
        g = _graph(c)
        engine = FinOpsResilienceEngine(g)
        sla = engine.assess_sla_breach_cost("app1", 99.99)
        assert sla.penalty_per_incident > 0

    def test_penalty_zero_when_no_credit(self):
        c = _comp("app1", "App", cost=CostProfile(hourly_infra_cost=1.0, sla_credit_percent=0.0))
        g = _graph(c)
        engine = FinOpsResilienceEngine(g)
        sla = engine.assess_sla_breach_cost("app1", 99.99)
        assert sla.penalty_per_incident == 0.0
        assert sla.annual_expected_penalty == 0.0

    def test_degraded_lowers_availability(self):
        c_healthy = _comp("a", "A")
        c_degraded = _comp("b", "B", health=HealthStatus.DEGRADED)
        g1 = _graph(c_healthy)
        g2 = _graph(c_degraded)
        e1 = FinOpsResilienceEngine(g1)
        e2 = FinOpsResilienceEngine(g2)
        s1 = e1.assess_sla_breach_cost("a", 99.9)
        s2 = e2.assess_sla_breach_cost("b", 99.9)
        assert s2.current_availability < s1.current_availability

    def test_overloaded_lowers_availability(self):
        c = _comp("x", "X", health=HealthStatus.OVERLOADED)
        g = _graph(c)
        engine = FinOpsResilienceEngine(g)
        sla = engine.assess_sla_breach_cost("x", 99.9)
        assert sla.current_availability < 99.0

    def test_replicas_improve_availability(self):
        c1 = _comp("a", "A", replicas=1)
        c3 = _comp("b", "B", replicas=3)
        g1 = _graph(c1)
        g3 = _graph(c3)
        e1 = FinOpsResilienceEngine(g1)
        e3 = FinOpsResilienceEngine(g3)
        s1 = e1.assess_sla_breach_cost("a", 99.9)
        s3 = e3.assess_sla_breach_cost("b", 99.9)
        assert s3.current_availability > s1.current_availability

    def test_failover_improves_availability(self):
        c_no = _comp("a", "A")
        c_fo = _comp("b", "B", failover=True)
        g1 = _graph(c_no)
        g2 = _graph(c_fo)
        e1 = FinOpsResilienceEngine(g1)
        e2 = FinOpsResilienceEngine(g2)
        s1 = e1.assess_sla_breach_cost("a", 99.9)
        s2 = e2.assess_sla_breach_cost("b", 99.9)
        assert s2.current_availability > s1.current_availability

    def test_breach_probability_capped_at_1(self):
        c = _comp("x", "X", health=HealthStatus.DOWN)
        g = _graph(c)
        engine = FinOpsResilienceEngine(g)
        sla = engine.assess_sla_breach_cost("x", 99.999)
        assert sla.annual_breach_probability <= 1.0

    def test_sla_target_rounded(self):
        c = _comp("x", "X")
        g = _graph(c)
        engine = FinOpsResilienceEngine(g)
        sla = engine.assess_sla_breach_cost("x", 99.12345)
        assert sla.sla_target == 99.1235  # rounded to 4 decimal places


# ---------------------------------------------------------------------------
# FinOpsResilienceEngine — recommend_optimizations
# ---------------------------------------------------------------------------


class TestRecommendOptimizations:
    def test_empty_graph_no_recommendations(self):
        g = _graph()
        engine = FinOpsResilienceEngine(g)
        recs = engine.recommend_optimizations()
        assert recs == []

    def test_over_provisioned_replicas_recommendation(self):
        c = _comp("app1", "App", replicas=3, failover=True)
        g = _graph(c)
        engine = FinOpsResilienceEngine(g)
        recs = engine.recommend_optimizations()
        actions = [r.action for r in recs]
        assert any("Reduce replicas" in a for a in actions)

    def test_no_dependent_gets_spot_recommendation(self):
        c = _comp("app1", "App")
        g = _graph(c)
        engine = FinOpsResilienceEngine(g)
        recs = engine.recommend_optimizations()
        actions = [r.action for r in recs]
        assert any("spot/reserved" in a for a in actions)

    def test_autoscaling_recommendation(self):
        c = _comp("app1", "App", replicas=2)
        g = _graph(c)
        engine = FinOpsResilienceEngine(g)
        recs = engine.recommend_optimizations()
        actions = [r.action for r in recs]
        assert any("autoscaling" in a for a in actions)

    def test_no_autoscaling_rec_when_already_enabled(self):
        c = _comp("app1", "App", replicas=2)
        c.autoscaling = AutoScalingConfig(enabled=True)
        g = _graph(c)
        engine = FinOpsResilienceEngine(g)
        recs = engine.recommend_optimizations()
        actions = [r.action for r in recs]
        assert not any("autoscaling" in a for a in actions)

    def test_right_size_recommendation_low_util(self):
        c = _comp("app1", "App", cost=CostProfile(hourly_infra_cost=1.0))
        c.metrics = ResourceMetrics(cpu_percent=10.0)
        g = _graph(c)
        engine = FinOpsResilienceEngine(g)
        recs = engine.recommend_optimizations()
        actions = [r.action for r in recs]
        assert any("Right-size" in a for a in actions)

    def test_no_right_size_when_high_util(self):
        c = _comp("app1", "App")
        c.metrics = ResourceMetrics(cpu_percent=80.0)
        g = _graph(c)
        engine = FinOpsResilienceEngine(g)
        recs = engine.recommend_optimizations()
        actions = [r.action for r in recs]
        assert not any("Right-size" in a for a in actions)

    def test_recommendations_sorted_by_savings_descending(self):
        c1 = _comp("a", "A", replicas=3, failover=True, cost=CostProfile(hourly_infra_cost=10.0))
        c2 = _comp("b", "B", replicas=3, failover=True, cost=CostProfile(hourly_infra_cost=1.0))
        g = _graph(c1, c2)
        engine = FinOpsResilienceEngine(g)
        recs = engine.recommend_optimizations()
        if len(recs) >= 2:
            for i in range(len(recs) - 1):
                assert recs[i].monthly_savings >= recs[i + 1].monthly_savings

    def test_priority_starts_at_1(self):
        c = _comp("app1", "App", replicas=3, failover=True)
        g = _graph(c)
        engine = FinOpsResilienceEngine(g)
        recs = engine.recommend_optimizations()
        if recs:
            assert recs[0].priority == 1

    def test_priority_sequential(self):
        c = _comp("app1", "App", replicas=3, failover=True)
        g = _graph(c)
        engine = FinOpsResilienceEngine(g)
        recs = engine.recommend_optimizations()
        for i, rec in enumerate(recs):
            assert rec.priority == i + 1

    def test_savings_positive(self):
        c = _comp("app1", "App", replicas=3, failover=True)
        g = _graph(c)
        engine = FinOpsResilienceEngine(g)
        recs = engine.recommend_optimizations()
        for rec in recs:
            assert rec.monthly_savings >= 0

    def test_resilience_impact_present(self):
        c = _comp("app1", "App", replicas=3, failover=True)
        g = _graph(c)
        engine = FinOpsResilienceEngine(g)
        recs = engine.recommend_optimizations()
        for rec in recs:
            assert rec.resilience_impact != 0.0 or rec.monthly_savings == 0.0

    def test_risk_description_not_empty(self):
        c = _comp("app1", "App", replicas=3, failover=True)
        g = _graph(c)
        engine = FinOpsResilienceEngine(g)
        recs = engine.recommend_optimizations()
        for rec in recs:
            assert len(rec.risk_description) > 0

    def test_external_api_zero_cost_no_spot_rec(self):
        c = _comp("ext", "Ext", ctype=ComponentType.EXTERNAL_API)
        g = _graph(c)
        engine = FinOpsResilienceEngine(g)
        recs = engine.recommend_optimizations()
        # External API cost is 0, so spot/reserved rec should not appear
        actions = [r.action for r in recs]
        assert not any("spot/reserved" in a for a in actions)

    def test_single_replica_no_autoscaling_rec(self):
        c = _comp("app1", "App", replicas=1)
        g = _graph(c)
        engine = FinOpsResilienceEngine(g)
        recs = engine.recommend_optimizations()
        actions = [r.action for r in recs]
        assert not any("autoscaling" in a for a in actions)


# ---------------------------------------------------------------------------
# FinOpsResilienceEngine — generate_report
# ---------------------------------------------------------------------------


class TestGenerateReport:
    def test_empty_graph(self):
        g = _graph()
        engine = FinOpsResilienceEngine(g)
        report = engine.generate_report()
        assert report.current_monthly_cost == 0.0
        assert report.current_resilience_score == 0.0
        assert report.optimal_configurations == []
        assert report.sla_breach_costs == []
        assert report.recommendations == []

    def test_report_type(self):
        g = _graph(_comp("a", "A"))
        engine = FinOpsResilienceEngine(g)
        report = engine.generate_report()
        assert isinstance(report, FinOpsResilienceReport)

    def test_report_has_current_cost(self):
        c = _comp("app1", "App", ctype=ComponentType.APP_SERVER)
        g = _graph(c)
        engine = FinOpsResilienceEngine(g)
        report = engine.generate_report()
        assert report.current_monthly_cost == 80.0

    def test_report_has_resilience_score(self):
        c = _comp("app1", "App")
        g = _graph(c)
        engine = FinOpsResilienceEngine(g)
        report = engine.generate_report()
        assert report.current_resilience_score >= 0
        assert report.current_resilience_score <= 100

    def test_report_with_options(self):
        c = _comp("app1", "App")
        g = _graph(c)
        engine = FinOpsResilienceEngine(g)
        opts = {
            "app1": [
                InfraOption(component_id="app1", cost_tier=CostTier.SPOT, monthly_cost=30.0),
                InfraOption(component_id="app1", cost_tier=CostTier.ON_DEMAND, monthly_cost=100.0),
            ]
        }
        report = engine.generate_report(options=opts)
        assert len(report.optimal_configurations) >= 1

    def test_report_without_options(self):
        c = _comp("app1", "App")
        g = _graph(c)
        engine = FinOpsResilienceEngine(g)
        report = engine.generate_report()
        assert report.optimal_configurations == []

    def test_sla_breach_for_each_component(self):
        c1 = _comp("a", "A")
        c2 = _comp("b", "B")
        g = _graph(c1, c2)
        engine = FinOpsResilienceEngine(g)
        report = engine.generate_report()
        assert len(report.sla_breach_costs) == 2

    def test_sla_uses_slo_target_if_available(self):
        c = _comp("a", "A")
        c.slo_targets = [SLOTarget(name="avail", metric="availability", target=99.95)]
        g = _graph(c)
        engine = FinOpsResilienceEngine(g)
        report = engine.generate_report()
        assert report.sla_breach_costs[0].sla_target == 99.95

    def test_sla_default_target(self):
        c = _comp("a", "A")
        g = _graph(c)
        engine = FinOpsResilienceEngine(g)
        report = engine.generate_report()
        assert report.sla_breach_costs[0].sla_target == 99.9

    def test_total_potential_savings(self):
        c = _comp("app1", "App", replicas=3, failover=True)
        g = _graph(c)
        engine = FinOpsResilienceEngine(g)
        report = engine.generate_report()
        assert report.total_potential_savings >= 0

    def test_total_annual_risk_cost(self):
        c = _comp("app1", "App")
        g = _graph(c)
        engine = FinOpsResilienceEngine(g)
        report = engine.generate_report()
        assert report.total_annual_risk_cost >= 0

    def test_report_recommendations_present(self):
        c = _comp("app1", "App", replicas=3, failover=True)
        g = _graph(c)
        engine = FinOpsResilienceEngine(g)
        report = engine.generate_report()
        assert len(report.recommendations) >= 1


# ---------------------------------------------------------------------------
# FinOpsResilienceEngine — _estimate_availability
# ---------------------------------------------------------------------------


class TestEstimateAvailability:
    def test_base_availability(self):
        c = _comp("a", "A")
        g = _graph(c)
        engine = FinOpsResilienceEngine(g)
        avail = engine._estimate_availability(c)
        assert 98.0 < avail < 100.0

    def test_3_replicas_boost(self):
        c = _comp("a", "A", replicas=3)
        g = _graph(c)
        engine = FinOpsResilienceEngine(g)
        avail = engine._estimate_availability(c)
        assert avail >= 99.9

    def test_2_replicas_boost(self):
        c = _comp("a", "A", replicas=2)
        g = _graph(c)
        engine = FinOpsResilienceEngine(g)
        avail = engine._estimate_availability(c)
        assert avail >= 99.5

    def test_failover_boost(self):
        c = _comp("a", "A", failover=True)
        g = _graph(c)
        engine = FinOpsResilienceEngine(g)
        avail = engine._estimate_availability(c)
        assert avail >= 99.09

    def test_autoscaling_boost(self):
        c = _comp("a", "A")
        c.autoscaling = AutoScalingConfig(enabled=True)
        g = _graph(c)
        engine = FinOpsResilienceEngine(g)
        avail = engine._estimate_availability(c)
        assert avail >= 99.05

    def test_down_reduces_availability(self):
        c = _comp("a", "A", health=HealthStatus.DOWN)
        g = _graph(c)
        engine = FinOpsResilienceEngine(g)
        avail = engine._estimate_availability(c)
        assert avail < 90.0

    def test_overloaded_reduces_availability(self):
        c = _comp("a", "A", health=HealthStatus.OVERLOADED)
        g = _graph(c)
        engine = FinOpsResilienceEngine(g)
        avail = engine._estimate_availability(c)
        assert avail < 97.0

    def test_availability_capped_at_100(self):
        c = _comp("a", "A", replicas=5, failover=True)
        c.autoscaling = AutoScalingConfig(enabled=True)
        g = _graph(c)
        engine = FinOpsResilienceEngine(g)
        avail = engine._estimate_availability(c)
        assert avail <= 100.0

    def test_availability_min_zero(self):
        c = _comp("a", "A", health=HealthStatus.DOWN)
        g = _graph(c)
        engine = FinOpsResilienceEngine(g)
        avail = engine._estimate_availability(c)
        assert avail >= 0.0


# ---------------------------------------------------------------------------
# FinOpsResilienceEngine — _filter_dominated
# ---------------------------------------------------------------------------


class TestFilterDominated:
    def test_empty_list(self):
        result = FinOpsResilienceEngine._filter_dominated([])
        assert result == []

    def test_single_point(self):
        pt = CostResiliencePoint(monthly_cost=100.0, resilience_score=50.0)
        result = FinOpsResilienceEngine._filter_dominated([pt])
        assert len(result) == 1

    def test_two_non_dominated(self):
        p1 = CostResiliencePoint(monthly_cost=50.0, resilience_score=30.0)
        p2 = CostResiliencePoint(monthly_cost=100.0, resilience_score=70.0)
        result = FinOpsResilienceEngine._filter_dominated([p1, p2])
        assert len(result) == 2

    def test_dominated_removed(self):
        p1 = CostResiliencePoint(monthly_cost=50.0, resilience_score=70.0)
        p2 = CostResiliencePoint(monthly_cost=100.0, resilience_score=50.0)
        result = FinOpsResilienceEngine._filter_dominated([p1, p2])
        # p1 dominates p2 (cheaper AND better resilience)
        assert len(result) == 1
        assert result[0].monthly_cost == 50.0

    def test_three_points_one_dominated(self):
        p1 = CostResiliencePoint(monthly_cost=30.0, resilience_score=30.0)
        p2 = CostResiliencePoint(monthly_cost=60.0, resilience_score=50.0)
        p3 = CostResiliencePoint(monthly_cost=70.0, resilience_score=40.0)
        result = FinOpsResilienceEngine._filter_dominated([p1, p2, p3])
        # p2 dominates p3 (cheaper AND better resilience)
        assert len(result) == 2
        costs = [p.monthly_cost for p in result]
        assert 70.0 not in costs

    def test_equal_cost_different_resilience(self):
        p1 = CostResiliencePoint(monthly_cost=50.0, resilience_score=30.0)
        p2 = CostResiliencePoint(monthly_cost=50.0, resilience_score=70.0)
        result = FinOpsResilienceEngine._filter_dominated([p1, p2])
        # p2 dominates p1 (same cost, better resilience)
        assert len(result) == 1
        assert result[0].resilience_score == 70.0

    def test_equal_resilience_different_cost(self):
        p1 = CostResiliencePoint(monthly_cost=50.0, resilience_score=50.0)
        p2 = CostResiliencePoint(monthly_cost=100.0, resilience_score=50.0)
        result = FinOpsResilienceEngine._filter_dominated([p1, p2])
        # p1 dominates p2 (same resilience, cheaper)
        assert len(result) == 1
        assert result[0].monthly_cost == 50.0

    def test_identical_points(self):
        p1 = CostResiliencePoint(monthly_cost=50.0, resilience_score=50.0)
        p2 = CostResiliencePoint(monthly_cost=50.0, resilience_score=50.0)
        result = FinOpsResilienceEngine._filter_dominated([p1, p2])
        # Neither dominates the other (both equal), so both survive
        assert len(result) == 2

    def test_output_sorted_by_cost(self):
        p1 = CostResiliencePoint(monthly_cost=100.0, resilience_score=80.0)
        p2 = CostResiliencePoint(monthly_cost=50.0, resilience_score=40.0)
        p3 = CostResiliencePoint(monthly_cost=150.0, resilience_score=90.0)
        result = FinOpsResilienceEngine._filter_dominated([p1, p2, p3])
        for i in range(len(result) - 1):
            assert result[i].monthly_cost <= result[i + 1].monthly_cost


# ---------------------------------------------------------------------------
# FinOpsResilienceEngine — _component_monthly_cost
# ---------------------------------------------------------------------------


class TestComponentMonthlyCost:
    def test_default_app_server(self):
        c = _comp("a", "A", ctype=ComponentType.APP_SERVER)
        g = _graph(c)
        engine = FinOpsResilienceEngine(g)
        assert engine._component_monthly_cost(c) == 80.0

    def test_default_database(self):
        c = _comp("a", "A", ctype=ComponentType.DATABASE)
        g = _graph(c)
        engine = FinOpsResilienceEngine(g)
        assert engine._component_monthly_cost(c) == 150.0

    def test_with_hourly_cost(self):
        c = _comp("a", "A", cost=CostProfile(hourly_infra_cost=0.5))
        g = _graph(c)
        engine = FinOpsResilienceEngine(g)
        assert engine._component_monthly_cost(c) == 0.5 * 730.0

    def test_replicas_factor(self):
        c = _comp("a", "A", ctype=ComponentType.CACHE, replicas=4)
        g = _graph(c)
        engine = FinOpsResilienceEngine(g)
        assert engine._component_monthly_cost(c) == 60.0 * 4

    def test_hourly_with_replicas(self):
        c = _comp("a", "A", replicas=3, cost=CostProfile(hourly_infra_cost=2.0))
        g = _graph(c)
        engine = FinOpsResilienceEngine(g)
        assert engine._component_monthly_cost(c) == 2.0 * 730.0 * 3

    def test_load_balancer_cost(self):
        c = _comp("lb", "LB", ctype=ComponentType.LOAD_BALANCER)
        g = _graph(c)
        engine = FinOpsResilienceEngine(g)
        assert engine._component_monthly_cost(c) == 25.0

    def test_web_server_cost(self):
        c = _comp("ws", "WS", ctype=ComponentType.WEB_SERVER)
        g = _graph(c)
        engine = FinOpsResilienceEngine(g)
        assert engine._component_monthly_cost(c) == 50.0


# ---------------------------------------------------------------------------
# _option_resilience_score tests
# ---------------------------------------------------------------------------


class TestOptionResilienceScore:
    def test_max_score(self):
        g = _graph(_comp("x", "X"))
        engine = FinOpsResilienceEngine(g)
        opt = InfraOption(
            component_id="x", cost_tier=CostTier.RESERVED,
            monthly_cost=500.0, availability_percent=99.99,
            failover_time_seconds=3.0, replicas=3,
        )
        assert engine._option_resilience_score(opt) == 100.0

    def test_min_score(self):
        g = _graph(_comp("x", "X"))
        engine = FinOpsResilienceEngine(g)
        opt = InfraOption(
            component_id="x", cost_tier=CostTier.SPOT,
            monthly_cost=5.0, availability_percent=80.0,
            failover_time_seconds=999.0, replicas=1,
        )
        score = engine._option_resilience_score(opt)
        assert score == 12.0  # 5+5+2

    def test_availability_99_9(self):
        g = _graph(_comp("x", "X"))
        engine = FinOpsResilienceEngine(g)
        opt = InfraOption(
            component_id="x", cost_tier=CostTier.ON_DEMAND,
            monthly_cost=100.0, availability_percent=99.9,
            failover_time_seconds=30.0, replicas=1,
        )
        # 40+5+10 = 55
        assert engine._option_resilience_score(opt) == 55.0

    def test_failover_5s(self):
        g = _graph(_comp("x", "X"))
        engine = FinOpsResilienceEngine(g)
        opt = InfraOption(
            component_id="x", cost_tier=CostTier.ON_DEMAND,
            monthly_cost=100.0, availability_percent=99.0,
            failover_time_seconds=5.0, replicas=1,
        )
        # 30+5+20=55
        assert engine._option_resilience_score(opt) == 55.0


# ---------------------------------------------------------------------------
# Integration tests — multi-component scenarios
# ---------------------------------------------------------------------------


class TestMultiComponentScenarios:
    def test_three_tier_architecture(self):
        lb = _comp("lb", "LB", ctype=ComponentType.LOAD_BALANCER, replicas=2)
        app = _comp("app", "App", ctype=ComponentType.APP_SERVER, replicas=3, failover=True)
        db = _comp("db", "DB", ctype=ComponentType.DATABASE, replicas=2, failover=True)
        g = _graph(lb, app, db)
        engine = FinOpsResilienceEngine(g)

        cost = engine.calculate_current_cost()
        assert cost == 25.0 * 2 + 80.0 * 3 + 150.0 * 2

        report = engine.generate_report()
        assert report.current_monthly_cost == cost
        assert len(report.sla_breach_costs) == 3

    def test_mixed_cost_profiles(self):
        c1 = _comp("a", "A", cost=CostProfile(hourly_infra_cost=0.1))
        c2 = _comp("b", "B", ctype=ComponentType.CACHE)
        g = _graph(c1, c2)
        engine = FinOpsResilienceEngine(g)
        cost = engine.calculate_current_cost()
        assert cost == 0.1 * 730.0 + 60.0

    def test_all_down_components(self):
        c1 = _comp("a", "A", health=HealthStatus.DOWN)
        c2 = _comp("b", "B", health=HealthStatus.DOWN)
        g = _graph(c1, c2)
        engine = FinOpsResilienceEngine(g)
        report = engine.generate_report()
        for sla in report.sla_breach_costs:
            assert sla.annual_breach_probability > 0

    def test_all_highly_available(self):
        c1 = _comp("a", "A", replicas=3, failover=True)
        c1.autoscaling = AutoScalingConfig(enabled=True)
        c2 = _comp("b", "B", replicas=3, failover=True)
        c2.autoscaling = AutoScalingConfig(enabled=True)
        g = _graph(c1, c2)
        engine = FinOpsResilienceEngine(g)
        report = engine.generate_report()
        for sla in report.sla_breach_costs:
            if sla.sla_target <= 99.0:
                assert sla.annual_breach_probability == 0.0

    def test_pareto_with_multiple_components(self):
        c1 = _comp("a", "A")
        c2 = _comp("b", "B")
        g = _graph(c1, c2)
        engine = FinOpsResilienceEngine(g)
        opts = {
            "a": [
                InfraOption(component_id="a", cost_tier=CostTier.SPOT, monthly_cost=20.0, availability_percent=95.0),
                InfraOption(component_id="a", cost_tier=CostTier.ON_DEMAND, monthly_cost=80.0, availability_percent=99.9, replicas=2),
            ],
            "b": [
                InfraOption(component_id="b", cost_tier=CostTier.SPOT, monthly_cost=15.0, availability_percent=95.0),
                InfraOption(component_id="b", cost_tier=CostTier.RESERVED, monthly_cost=60.0, availability_percent=99.99, replicas=3, failover_time_seconds=5.0),
            ],
        }
        report = engine.generate_report(options=opts)
        assert len(report.optimal_configurations) >= 2


# ---------------------------------------------------------------------------
# Edge cases and boundary tests
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_zero_monthly_cost_option(self):
        g = _graph(_comp("x", "X"))
        engine = FinOpsResilienceEngine(g)
        opt = InfraOption(
            component_id="x", cost_tier=CostTier.SERVERLESS,
            monthly_cost=0.0, availability_percent=99.9,
        )
        pt = engine.evaluate_option(opt)
        assert pt.monthly_cost == 0.0
        assert pt.resilience_score > 0

    def test_very_high_monthly_cost(self):
        g = _graph(_comp("x", "X"))
        engine = FinOpsResilienceEngine(g)
        opt = InfraOption(
            component_id="x", cost_tier=CostTier.RESERVED,
            monthly_cost=1_000_000.0, availability_percent=99.99,
            replicas=10, failover_time_seconds=1.0,
        )
        pt = engine.evaluate_option(opt)
        assert pt.monthly_cost == 1_000_000.0
        assert pt.resilience_score == 100.0

    def test_single_external_api(self):
        c = _comp("ext", "Ext", ctype=ComponentType.EXTERNAL_API)
        g = _graph(c)
        engine = FinOpsResilienceEngine(g)
        report = engine.generate_report()
        assert report.current_monthly_cost == 0.0

    def test_report_with_slo_non_availability_metric(self):
        c = _comp("a", "A")
        c.slo_targets = [SLOTarget(name="latency", metric="latency_p99", target=500.0)]
        g = _graph(c)
        engine = FinOpsResilienceEngine(g)
        report = engine.generate_report()
        # No availability SLO → default 99.9
        assert report.sla_breach_costs[0].sla_target == 99.9

    def test_large_number_of_components(self):
        comps = [_comp(f"c{i}", f"C{i}") for i in range(20)]
        g = _graph(*comps)
        engine = FinOpsResilienceEngine(g)
        report = engine.generate_report()
        assert report.current_monthly_cost == 80.0 * 20
        assert len(report.sla_breach_costs) == 20

    def test_component_with_zero_hourly_uses_default(self):
        c = _comp("a", "A", ctype=ComponentType.DATABASE, cost=CostProfile(hourly_infra_cost=0.0))
        g = _graph(c)
        engine = FinOpsResilienceEngine(g)
        assert engine._component_monthly_cost(c) == 150.0

    def test_pareto_three_options_all_pareto_optimal(self):
        g = _graph(_comp("x", "X"))
        engine = FinOpsResilienceEngine(g)
        # Each option is strictly better in one dimension and worse in the other
        opts = {
            "x": [
                InfraOption(component_id="x", cost_tier=CostTier.SPOT, monthly_cost=10.0, availability_percent=90.0, failover_time_seconds=300.0),
                InfraOption(component_id="x", cost_tier=CostTier.ON_DEMAND, monthly_cost=50.0, availability_percent=99.0),
                InfraOption(component_id="x", cost_tier=CostTier.RESERVED, monthly_cost=100.0, availability_percent=99.99, replicas=3, failover_time_seconds=5.0),
            ]
        }
        result = engine.generate_pareto_frontier(opts)
        assert len(result) == 3

    def test_evaluate_option_description_has_replicas(self):
        g = _graph(_comp("x", "X"))
        engine = FinOpsResilienceEngine(g)
        opt = InfraOption(
            component_id="x", cost_tier=CostTier.ON_DEMAND,
            monthly_cost=100.0, replicas=5,
        )
        pt = engine.evaluate_option(opt)
        assert "5 replica(s)" in pt.tradeoff_description

    def test_utilization_zero_no_rightsize_rec(self):
        c = _comp("a", "A")
        # utilization is 0 by default — condition is util > 0 && util < 30
        g = _graph(c)
        engine = FinOpsResilienceEngine(g)
        recs = engine.recommend_optimizations()
        actions = [r.action for r in recs]
        assert not any("Right-size" in a for a in actions)

    def test_autoscaling_improves_availability(self):
        c1 = _comp("a", "A")
        c2 = _comp("b", "B")
        c2.autoscaling = AutoScalingConfig(enabled=True)
        g1 = _graph(c1)
        g2 = _graph(c2)
        e1 = FinOpsResilienceEngine(g1)
        e2 = FinOpsResilienceEngine(g2)
        a1 = e1._estimate_availability(c1)
        a2 = e2._estimate_availability(c2)
        assert a2 > a1
