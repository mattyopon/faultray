"""Tests for deployment strategy recommender."""

from __future__ import annotations

import pytest

from faultray.model.components import Component, ComponentType, Dependency, HealthStatus
from faultray.model.graph import InfraGraph
from faultray.simulator.deployment_strategy import (
    DeploymentPlan,
    DeploymentRecommendation,
    DeploymentStrategyAdvisor,
    DeploymentType,
    RiskTolerance,
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
    autoscaling: bool = False,
) -> Component:
    c = Component(id=cid, name=name, type=ctype, replicas=replicas)
    c.health = health
    if failover:
        c.failover.enabled = True
    if autoscaling:
        c.autoscaling.enabled = True
    return c


def _chain_graph() -> InfraGraph:
    """LB -> API -> DB chain (standard 3-tier)."""
    g = InfraGraph()
    g.add_component(_comp("lb", "LB", ComponentType.LOAD_BALANCER, replicas=2))
    g.add_component(_comp("api", "API", replicas=3))
    g.add_component(_comp("db", "DB", ComponentType.DATABASE, replicas=2))
    g.add_dependency(Dependency(source_id="lb", target_id="api"))
    g.add_dependency(Dependency(source_id="api", target_id="db"))
    return g


# ---------------------------------------------------------------------------
# Tests: Enums
# ---------------------------------------------------------------------------


class TestEnums:
    def test_deployment_type_values(self):
        assert DeploymentType.BLUE_GREEN.value == "blue_green"
        assert DeploymentType.CANARY.value == "canary"
        assert DeploymentType.ROLLING_UPDATE.value == "rolling_update"
        assert DeploymentType.RECREATE.value == "recreate"
        assert DeploymentType.AB_TESTING.value == "ab_testing"
        assert DeploymentType.SHADOW.value == "shadow"

    def test_deployment_type_count(self):
        assert len(DeploymentType) == 6

    def test_risk_tolerance_values(self):
        assert RiskTolerance.CONSERVATIVE.value == "conservative"
        assert RiskTolerance.MODERATE.value == "moderate"
        assert RiskTolerance.AGGRESSIVE.value == "aggressive"

    def test_risk_tolerance_count(self):
        assert len(RiskTolerance) == 3


# ---------------------------------------------------------------------------
# Tests: Single component recommendations — strategy selection
# ---------------------------------------------------------------------------


class TestSingleRecommendation:
    def test_basic_recommendation_structure(self):
        g = _chain_graph()
        advisor = DeploymentStrategyAdvisor(g)
        rec = advisor.recommend(g, "api")
        assert isinstance(rec, DeploymentRecommendation)
        assert isinstance(rec.strategy, DeploymentType)
        assert rec.risk_level >= 0
        assert rec.estimated_duration_minutes > 0
        assert rec.rollback_time_minutes > 0
        assert isinstance(rec.prerequisites, list)
        assert isinstance(rec.risks, list)
        assert isinstance(rec.steps, list)

    def test_database_gets_blue_green(self):
        g = _chain_graph()
        advisor = DeploymentStrategyAdvisor(g)
        rec = advisor.recommend(g, "db")
        assert rec.strategy == DeploymentType.BLUE_GREEN

    def test_storage_gets_blue_green(self):
        g = InfraGraph()
        g.add_component(_comp("s3", "S3", ComponentType.STORAGE, replicas=2))
        advisor = DeploymentStrategyAdvisor(g)
        rec = advisor.recommend(g, "s3")
        assert rec.strategy == DeploymentType.BLUE_GREEN

    def test_stateless_multi_replica_gets_rolling_update(self):
        g = InfraGraph()
        g.add_component(_comp("api", "API", replicas=3))
        advisor = DeploymentStrategyAdvisor(g)
        rec = advisor.recommend(g, "api", RiskTolerance.MODERATE)
        assert rec.strategy == DeploymentType.ROLLING_UPDATE

    def test_load_balancer_gets_blue_green_moderate(self):
        g = InfraGraph()
        g.add_component(_comp("lb", "LB", ComponentType.LOAD_BALANCER, replicas=2))
        advisor = DeploymentStrategyAdvisor(g)
        rec = advisor.recommend(g, "lb", RiskTolerance.MODERATE)
        assert rec.strategy == DeploymentType.BLUE_GREEN

    def test_queue_gets_canary(self):
        g = InfraGraph()
        g.add_component(_comp("q", "Queue", ComponentType.QUEUE, replicas=2))
        advisor = DeploymentStrategyAdvisor(g)
        rec = advisor.recommend(g, "q", RiskTolerance.MODERATE)
        assert rec.strategy == DeploymentType.CANARY

    def test_cache_moderate_gets_canary(self):
        g = InfraGraph()
        g.add_component(_comp("cache", "Cache", ComponentType.CACHE, replicas=3))
        advisor = DeploymentStrategyAdvisor(g)
        rec = advisor.recommend(g, "cache", RiskTolerance.MODERATE)
        assert rec.strategy == DeploymentType.CANARY

    def test_steps_generated(self):
        g = _chain_graph()
        advisor = DeploymentStrategyAdvisor(g)
        rec = advisor.recommend(g, "api")
        assert len(rec.steps) >= 3

    def test_prerequisites_include_backup(self):
        g = _chain_graph()
        advisor = DeploymentStrategyAdvisor(g)
        rec = advisor.recommend(g, "api")
        assert any("backup" in p.lower() for p in rec.prerequisites)

    def test_prerequisites_include_health_check(self):
        g = _chain_graph()
        advisor = DeploymentStrategyAdvisor(g)
        rec = advisor.recommend(g, "api")
        assert any("health" in p.lower() for p in rec.prerequisites)


# ---------------------------------------------------------------------------
# Tests: Risk tolerance influence
# ---------------------------------------------------------------------------


class TestRiskTolerance:
    def test_conservative_prefers_safer_strategy(self):
        """Conservative should prefer blue-green/canary over rolling update."""
        g = InfraGraph()
        g.add_component(_comp("api", "API", replicas=3))
        advisor = DeploymentStrategyAdvisor(g)
        rec_conservative = advisor.recommend(g, "api", RiskTolerance.CONSERVATIVE)
        rec_aggressive = advisor.recommend(g, "api", RiskTolerance.AGGRESSIVE)
        # Conservative should not pick rolling_update for a simple app server
        # while aggressive would
        assert rec_conservative.strategy in (DeploymentType.BLUE_GREEN, DeploymentType.CANARY)
        assert rec_aggressive.strategy == DeploymentType.ROLLING_UPDATE

    def test_aggressive_uses_rolling_update_for_stateless(self):
        g = InfraGraph()
        g.add_component(_comp("web", "Web", ComponentType.WEB_SERVER, replicas=4))
        advisor = DeploymentStrategyAdvisor(g)
        rec = advisor.recommend(g, "web", RiskTolerance.AGGRESSIVE)
        assert rec.strategy == DeploymentType.ROLLING_UPDATE

    def test_conservative_higher_risk_score(self):
        g = _chain_graph()
        advisor = DeploymentStrategyAdvisor(g)
        rec_con = advisor.recommend(g, "api", RiskTolerance.CONSERVATIVE)
        rec_agg = advisor.recommend(g, "api", RiskTolerance.AGGRESSIVE)
        assert rec_con.risk_level >= rec_agg.risk_level

    def test_conservative_canary_percent_lower(self):
        g = InfraGraph()
        # Use a queue so both pick CANARY
        g.add_component(_comp("q", "Queue", ComponentType.QUEUE, replicas=3))
        advisor = DeploymentStrategyAdvisor(g)
        rec_con = advisor.recommend(g, "q", RiskTolerance.CONSERVATIVE)
        rec_agg = advisor.recommend(g, "q", RiskTolerance.AGGRESSIVE)
        assert rec_con.recommended_canary_percent < rec_agg.recommended_canary_percent

    def test_moderate_canary_percent(self):
        g = InfraGraph()
        g.add_component(_comp("q", "Queue", ComponentType.QUEUE, replicas=2))
        advisor = DeploymentStrategyAdvisor(g)
        rec = advisor.recommend(g, "q", RiskTolerance.MODERATE)
        assert rec.recommended_canary_percent == 10.0

    def test_non_canary_strategy_zero_canary_percent(self):
        g = _chain_graph()
        advisor = DeploymentStrategyAdvisor(g)
        rec = advisor.recommend(g, "db")
        assert rec.recommended_canary_percent == 0.0


# ---------------------------------------------------------------------------
# Tests: Component type influence
# ---------------------------------------------------------------------------


class TestComponentTypeInfluence:
    def test_database_always_blue_green(self):
        """Databases should always get blue-green regardless of tolerance."""
        g = InfraGraph()
        g.add_component(_comp("db", "DB", ComponentType.DATABASE, replicas=3))
        advisor = DeploymentStrategyAdvisor(g)
        for tol in RiskTolerance:
            rec = advisor.recommend(g, "db", tol)
            assert rec.strategy == DeploymentType.BLUE_GREEN, f"Failed for {tol}"

    def test_database_longer_duration(self):
        g = InfraGraph()
        g.add_component(_comp("db", "DB", ComponentType.DATABASE, replicas=2))
        g.add_component(_comp("api", "API", replicas=2))
        advisor = DeploymentStrategyAdvisor(g)
        rec_db = advisor.recommend(g, "db")
        rec_api = advisor.recommend(g, "api")
        assert rec_db.estimated_duration_minutes > rec_api.estimated_duration_minutes

    def test_database_longer_rollback_than_same_strategy(self):
        """DB blue-green rollback should be longer than non-DB blue-green rollback."""
        g = InfraGraph()
        g.add_component(_comp("db", "DB", ComponentType.DATABASE, replicas=2))
        # DNS also gets blue-green at moderate tolerance, so compare same strategy
        g.add_component(_comp("dns", "DNS", ComponentType.DNS, replicas=2))
        advisor = DeploymentStrategyAdvisor(g)
        rec_db = advisor.recommend(g, "db")
        rec_dns = advisor.recommend(g, "dns")
        assert rec_db.strategy == DeploymentType.BLUE_GREEN
        assert rec_dns.strategy == DeploymentType.BLUE_GREEN
        assert rec_db.rollback_time_minutes > rec_dns.rollback_time_minutes

    def test_dns_gets_blue_green(self):
        g = InfraGraph()
        g.add_component(_comp("dns", "DNS", ComponentType.DNS, replicas=2))
        advisor = DeploymentStrategyAdvisor(g)
        rec = advisor.recommend(g, "dns", RiskTolerance.MODERATE)
        assert rec.strategy == DeploymentType.BLUE_GREEN

    def test_external_api_aggressive_rolling_update(self):
        g = InfraGraph()
        g.add_component(_comp("ext", "ExtAPI", ComponentType.EXTERNAL_API, replicas=2))
        advisor = DeploymentStrategyAdvisor(g)
        rec = advisor.recommend(g, "ext", RiskTolerance.AGGRESSIVE)
        assert rec.strategy == DeploymentType.ROLLING_UPDATE

    def test_stateful_risks_mention_data_migration(self):
        g = InfraGraph()
        g.add_component(_comp("db", "DB", ComponentType.DATABASE, replicas=2))
        advisor = DeploymentStrategyAdvisor(g)
        rec = advisor.recommend(g, "db")
        assert any("data migration" in r.lower() or "stateful" in r.lower() for r in rec.risks)


# ---------------------------------------------------------------------------
# Tests: Health status influence
# ---------------------------------------------------------------------------


class TestHealthInfluence:
    def test_down_component_gets_recreate(self):
        g = InfraGraph()
        g.add_component(_comp("api", "API", replicas=3, health=HealthStatus.DOWN))
        advisor = DeploymentStrategyAdvisor(g)
        rec = advisor.recommend(g, "api")
        assert rec.strategy == DeploymentType.RECREATE

    def test_overloaded_component_gets_recreate(self):
        g = InfraGraph()
        g.add_component(_comp("api", "API", replicas=3, health=HealthStatus.OVERLOADED))
        advisor = DeploymentStrategyAdvisor(g)
        rec = advisor.recommend(g, "api")
        assert rec.strategy == DeploymentType.RECREATE

    def test_unhealthy_higher_risk_than_healthy(self):
        g = InfraGraph()
        g.add_component(_comp("a1", "A1", replicas=3, health=HealthStatus.HEALTHY))
        g.add_component(_comp("a2", "A2", replicas=3, health=HealthStatus.DEGRADED))
        advisor = DeploymentStrategyAdvisor(g)
        rec_healthy = advisor.recommend(g, "a1")
        rec_degraded = advisor.recommend(g, "a2")
        assert rec_degraded.risk_level > rec_healthy.risk_level

    def test_down_highest_risk(self):
        g = InfraGraph()
        g.add_component(_comp("a1", "A1", replicas=3, health=HealthStatus.DEGRADED))
        g.add_component(_comp("a2", "A2", replicas=3, health=HealthStatus.DOWN))
        advisor = DeploymentStrategyAdvisor(g)
        rec_degraded = advisor.recommend(g, "a1")
        rec_down = advisor.recommend(g, "a2")
        assert rec_down.risk_level > rec_degraded.risk_level

    def test_unhealthy_risks_mention_status(self):
        g = InfraGraph()
        g.add_component(_comp("api", "API", replicas=3, health=HealthStatus.DEGRADED))
        advisor = DeploymentStrategyAdvisor(g)
        rec = advisor.recommend(g, "api")
        assert any("degraded" in r.lower() for r in rec.risks)

    def test_recreate_has_downtime_risk(self):
        g = InfraGraph()
        g.add_component(_comp("api", "API", replicas=3, health=HealthStatus.DOWN))
        advisor = DeploymentStrategyAdvisor(g)
        rec = advisor.recommend(g, "api")
        assert any("downtime" in r.lower() for r in rec.risks)


# ---------------------------------------------------------------------------
# Tests: Failover and autoscaling influence
# ---------------------------------------------------------------------------


class TestFailoverAutoscaling:
    def test_failover_reduces_risk(self):
        g = InfraGraph()
        g.add_component(_comp("a1", "A1", replicas=2))
        g.add_component(_comp("a2", "A2", replicas=2, failover=True))
        advisor = DeploymentStrategyAdvisor(g)
        rec_no_fo = advisor.recommend(g, "a1")
        rec_fo = advisor.recommend(g, "a2")
        assert rec_fo.risk_level < rec_no_fo.risk_level

    def test_autoscaling_reduces_risk(self):
        g = InfraGraph()
        g.add_component(_comp("a1", "A1", replicas=2))
        g.add_component(_comp("a2", "A2", replicas=2, autoscaling=True))
        advisor = DeploymentStrategyAdvisor(g)
        rec_no_as = advisor.recommend(g, "a1")
        rec_as = advisor.recommend(g, "a2")
        assert rec_as.risk_level < rec_no_as.risk_level


# ---------------------------------------------------------------------------
# Tests: Multi-component deployment plans
# ---------------------------------------------------------------------------


class TestDeploymentPlan:
    def test_plan_structure(self):
        g = _chain_graph()
        advisor = DeploymentStrategyAdvisor(g)
        plan = advisor.plan(g, ["lb", "api", "db"])
        assert isinstance(plan, DeploymentPlan)
        assert len(plan.recommendations) == 3
        assert plan.total_duration > 0
        assert plan.total_risk_score >= 0

    def test_plan_total_duration_is_sum(self):
        g = _chain_graph()
        advisor = DeploymentStrategyAdvisor(g)
        plan = advisor.plan(g, ["api", "db"])
        expected = sum(r.estimated_duration_minutes for r in plan.recommendations.values())
        assert plan.total_duration == expected

    def test_plan_risk_is_max(self):
        g = _chain_graph()
        advisor = DeploymentStrategyAdvisor(g)
        plan = advisor.plan(g, ["api", "db"])
        max_risk = max(r.risk_level for r in plan.recommendations.values())
        assert plan.total_risk_score == max_risk

    def test_plan_overall_strategy_most_conservative(self):
        g = _chain_graph()
        advisor = DeploymentStrategyAdvisor(g)
        plan = advisor.plan(g, ["api", "db"])
        # DB should get blue_green, which is more conservative than rolling_update
        assert plan.overall_strategy == DeploymentType.BLUE_GREEN

    def test_plan_ordering_lowest_risk_first(self):
        g = InfraGraph()
        g.add_component(_comp("api", "API", replicas=3))
        g.add_component(_comp("db", "DB", ComponentType.DATABASE, replicas=2))
        advisor = DeploymentStrategyAdvisor(g)
        plan = advisor.plan(g, ["db", "api"])
        keys = list(plan.recommendations.keys())
        risks = [plan.recommendations[k].risk_level for k in keys]
        # Should be sorted: lowest risk first
        assert risks == sorted(risks)

    def test_single_component_plan(self):
        g = _chain_graph()
        advisor = DeploymentStrategyAdvisor(g)
        plan = advisor.plan(g, ["api"])
        assert len(plan.recommendations) == 1
        assert "api" in plan.recommendations


# ---------------------------------------------------------------------------
# Tests: Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_graph(self):
        g = InfraGraph()
        advisor = DeploymentStrategyAdvisor(g)
        rec = advisor.recommend(g, "nonexistent")
        assert rec.strategy == DeploymentType.RECREATE
        assert rec.risk_level > 0

    def test_unknown_component(self):
        g = _chain_graph()
        advisor = DeploymentStrategyAdvisor(g)
        rec = advisor.recommend(g, "does_not_exist")
        assert rec.strategy == DeploymentType.RECREATE
        assert "not found" in rec.risks[0].lower() or "not found" in rec.prerequisites[0].lower()

    def test_single_replica_gets_blue_green_or_recreate(self):
        g = InfraGraph()
        g.add_component(_comp("api", "API", replicas=1))
        advisor = DeploymentStrategyAdvisor(g)
        rec = advisor.recommend(g, "api", RiskTolerance.MODERATE)
        assert rec.strategy in (DeploymentType.BLUE_GREEN, DeploymentType.RECREATE)

    def test_single_replica_has_redundancy_risk(self):
        g = InfraGraph()
        g.add_component(_comp("api", "API", replicas=1))
        advisor = DeploymentStrategyAdvisor(g)
        rec = advisor.recommend(g, "api")
        assert any("single replica" in r.lower() or "redundancy" in r.lower() for r in rec.risks)

    def test_empty_plan(self):
        g = _chain_graph()
        advisor = DeploymentStrategyAdvisor(g)
        plan = advisor.plan(g, [])
        assert len(plan.recommendations) == 0
        assert plan.total_duration == 0
        assert plan.total_risk_score == 0.0

    def test_single_replica_aggressive_gets_recreate(self):
        g = InfraGraph()
        g.add_component(_comp("api", "API", replicas=1))
        advisor = DeploymentStrategyAdvisor(g)
        rec = advisor.recommend(g, "api", RiskTolerance.AGGRESSIVE)
        assert rec.strategy == DeploymentType.RECREATE

    def test_many_dependents_conservative_gets_blue_green(self):
        """Component with many dependents under conservative tolerance -> blue-green."""
        g = InfraGraph()
        g.add_component(_comp("core", "Core", replicas=3))
        for i in range(5):
            cid = f"svc{i}"
            g.add_component(_comp(cid, f"Service {i}", replicas=2))
            g.add_dependency(Dependency(source_id=cid, target_id="core"))
        advisor = DeploymentStrategyAdvisor(g)
        rec = advisor.recommend(g, "core", RiskTolerance.CONSERVATIVE)
        assert rec.strategy == DeploymentType.BLUE_GREEN

    def test_dependent_count_increases_risk(self):
        g1 = InfraGraph()
        g1.add_component(_comp("api", "API", replicas=3))
        advisor1 = DeploymentStrategyAdvisor(g1)
        rec1 = advisor1.recommend(g1, "api")

        g2 = InfraGraph()
        g2.add_component(_comp("api", "API", replicas=3))
        for i in range(4):
            cid = f"dep{i}"
            g2.add_component(_comp(cid, f"Dep {i}", replicas=2))
            g2.add_dependency(Dependency(source_id=cid, target_id="api"))
        advisor2 = DeploymentStrategyAdvisor(g2)
        rec2 = advisor2.recommend(g2, "api")

        assert rec2.risk_level > rec1.risk_level

    def test_risk_level_bounded(self):
        """Risk level should always be 0-100."""
        g = InfraGraph()
        g.add_component(_comp("api", "API", replicas=1, health=HealthStatus.DOWN))
        for i in range(10):
            cid = f"dep{i}"
            g.add_component(_comp(cid, f"Dep {i}"))
            g.add_dependency(Dependency(source_id=cid, target_id="api"))
        advisor = DeploymentStrategyAdvisor(g)
        rec = advisor.recommend(g, "api")
        assert 0 <= rec.risk_level <= 100

    def test_recreate_steps_mention_stop_and_start(self):
        g = InfraGraph()
        g.add_component(_comp("api", "API", replicas=2, health=HealthStatus.DOWN))
        advisor = DeploymentStrategyAdvisor(g)
        rec = advisor.recommend(g, "api")
        steps_text = " ".join(rec.steps).lower()
        assert "stop" in steps_text or "deploy" in steps_text
        assert "start" in steps_text or "verify" in steps_text

    def test_blue_green_steps_mention_switch(self):
        g = InfraGraph()
        g.add_component(_comp("db", "DB", ComponentType.DATABASE, replicas=2))
        advisor = DeploymentStrategyAdvisor(g)
        rec = advisor.recommend(g, "db")
        steps_text = " ".join(rec.steps).lower()
        assert "green" in steps_text
        assert "switch" in steps_text or "traffic" in steps_text


# ---------------------------------------------------------------------------
# Tests: Coverage gaps — lines 209, 222, 244, 464-473
# ---------------------------------------------------------------------------


class TestCoverageGaps:
    def test_conservative_cache_gets_blue_green(self):
        """Conservative tolerance + CACHE -> BLUE_GREEN. [line 209]"""
        g = InfraGraph()
        g.add_component(_comp("cache", "Cache", ComponentType.CACHE, replicas=3))
        advisor = DeploymentStrategyAdvisor(g)
        rec = advisor.recommend(g, "cache", RiskTolerance.CONSERVATIVE)
        assert rec.strategy == DeploymentType.BLUE_GREEN

    def test_aggressive_cache_gets_rolling_update(self):
        """Aggressive tolerance + CACHE -> ROLLING_UPDATE. [line 222]"""
        g = InfraGraph()
        g.add_component(_comp("cache", "Cache", ComponentType.CACHE, replicas=3))
        advisor = DeploymentStrategyAdvisor(g)
        rec = advisor.recommend(g, "cache", RiskTolerance.AGGRESSIVE)
        assert rec.strategy == DeploymentType.ROLLING_UPDATE

    def test_ab_testing_steps(self):
        """AB_TESTING strategy should generate specific steps. [lines 464-471]"""
        g = InfraGraph()
        g.add_component(_comp("api", "API", replicas=3))
        advisor = DeploymentStrategyAdvisor(g)
        steps = advisor._generate_steps(
            DeploymentType.AB_TESTING, g.get_component("api")
        )
        steps_text = " ".join(steps).lower()
        assert "variant" in steps_text or "traffic" in steps_text
        assert "metrics" in steps_text or "analyze" in steps_text

    def test_shadow_steps(self):
        """SHADOW strategy should generate specific steps. [lines 472-479]"""
        g = InfraGraph()
        g.add_component(_comp("api", "API", replicas=3))
        advisor = DeploymentStrategyAdvisor(g)
        steps = advisor._generate_steps(
            DeploymentType.SHADOW, g.get_component("api")
        )
        steps_text = " ".join(steps).lower()
        assert "shadow" in steps_text
        assert "mirror" in steps_text or "compare" in steps_text
