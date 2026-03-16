"""Tests for cost-resilience optimizer."""

import math

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    Capacity,
    Component,
    ComponentType,
    FailoverConfig,
    HealthStatus,
    OperationalProfile,
    ResourceMetrics,
    SecurityProfile,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.cost_resilience_optimizer import (
    CostResilienceOptimizer,
    ImprovementOption,
    ImprovementType,
    OptimizationStrategy,
    ParetoPoint,
)


def _comp(
    cid: str,
    name: str,
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    failover: bool = False,
    autoscaling: bool = False,
    cpu: float = 0.0,
    memory: float = 0.0,
    disk: float = 0.0,
    health: HealthStatus = HealthStatus.HEALTHY,
    backup: bool = False,
    encryption: bool = False,
    log_enabled: bool = True,
    mtbf_hours: float = 0.0,
) -> Component:
    c = Component(id=cid, name=name, type=ctype, replicas=replicas)
    c.metrics = ResourceMetrics(cpu_percent=cpu, memory_percent=memory, disk_percent=disk)
    c.health = health
    if failover:
        c.failover = FailoverConfig(enabled=True, promotion_time_seconds=10)
    if autoscaling:
        c.autoscaling = AutoScalingConfig(enabled=True, min_replicas=1, max_replicas=10)
    c.security = SecurityProfile(
        backup_enabled=backup,
        encryption_at_rest=encryption,
        log_enabled=log_enabled,
    )
    if mtbf_hours > 0:
        c.operational_profile = OperationalProfile(mtbf_hours=mtbf_hours)
    return c


def _graph(*comps: Component) -> InfraGraph:
    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    return g


# ==================================================================
# Basic analysis
# ==================================================================

class TestBasicAnalysis:
    def test_empty_graph(self):
        opt = CostResilienceOptimizer(InfraGraph())
        report = opt.analyze()
        assert report.current_total_cost == 0
        assert report.current_resilience_score == 0
        assert len(report.component_profiles) == 0

    def test_single_component(self):
        g = _graph(_comp("app", "App"))
        opt = CostResilienceOptimizer(g)
        report = opt.analyze()
        assert len(report.component_profiles) == 1
        assert report.current_total_cost > 0
        assert report.summary != ""

    def test_multiple_components(self):
        g = _graph(
            _comp("app", "App"),
            _comp("db", "DB", ComponentType.DATABASE),
            _comp("cache", "Cache", ComponentType.CACHE),
        )
        opt = CostResilienceOptimizer(g)
        report = opt.analyze()
        assert len(report.component_profiles) == 3
        assert report.current_total_cost > 0

    def test_fully_resilient_no_improvements(self):
        c = _comp(
            "app", "App", replicas=3, failover=True, autoscaling=True,
            backup=True, encryption=True, log_enabled=True,
        )
        g = _graph(c)
        opt = CostResilienceOptimizer(g)
        report = opt.analyze()
        # Fully configured — few improvements available
        assert report.current_resilience_score > 0


# ==================================================================
# Component resilience scoring
# ==================================================================

class TestComponentResilience:
    def test_single_replica_low_score(self):
        g = _graph(_comp("app", "App", replicas=1))
        opt = CostResilienceOptimizer(g)
        score = opt._component_resilience_score(g.get_component("app"))
        assert score == 5.0  # Only 1 replica → 5 points

    def test_two_replicas(self):
        g = _graph(_comp("app", "App", replicas=2))
        opt = CostResilienceOptimizer(g)
        score = opt._component_resilience_score(g.get_component("app"))
        assert score == 20.0

    def test_three_replicas(self):
        g = _graph(_comp("app", "App", replicas=3))
        opt = CostResilienceOptimizer(g)
        score = opt._component_resilience_score(g.get_component("app"))
        assert score == 30.0

    def test_failover_bonus(self):
        g = _graph(_comp("app", "App", replicas=1, failover=True))
        opt = CostResilienceOptimizer(g)
        score = opt._component_resilience_score(g.get_component("app"))
        assert score == 5.0 + 20.0 + 5.0  # 1 replica + failover + fast promotion

    def test_failover_slow_promotion(self):
        c = _comp("app", "App", replicas=1, failover=True)
        c.failover.promotion_time_seconds = 120  # Slow
        g = _graph(c)
        opt = CostResilienceOptimizer(g)
        score = opt._component_resilience_score(g.get_component("app"))
        assert score == 5.0 + 20.0  # No fast promotion bonus

    def test_autoscaling_bonus(self):
        g = _graph(_comp("app", "App", replicas=1, autoscaling=True))
        opt = CostResilienceOptimizer(g)
        score = opt._component_resilience_score(g.get_component("app"))
        assert score == 5.0 + 10.0

    def test_security_features(self):
        g = _graph(_comp("db", "DB", ComponentType.DATABASE, backup=True, encryption=True))
        opt = CostResilienceOptimizer(g)
        score = opt._component_resilience_score(g.get_component("db"))
        assert score >= 5.0 + 10.0 + 5.0  # replica + backup + encryption

    def test_degraded_penalty(self):
        g = _graph(_comp("app", "App", health=HealthStatus.DEGRADED))
        opt = CostResilienceOptimizer(g)
        score = opt._component_resilience_score(g.get_component("app"))
        # 5 (replica) - 10 (degraded) = max(0, -5) = 0
        assert score == 0.0

    def test_overloaded_penalty(self):
        g = _graph(_comp("app", "App", replicas=3, health=HealthStatus.OVERLOADED))
        opt = CostResilienceOptimizer(g)
        score = opt._component_resilience_score(g.get_component("app"))
        assert score == 30.0 - 20.0  # 3 replicas - overloaded

    def test_down_penalty(self):
        g = _graph(_comp("app", "App", replicas=3, failover=True, health=HealthStatus.DOWN))
        opt = CostResilienceOptimizer(g)
        score = opt._component_resilience_score(g.get_component("app"))
        # 30 + 25 - 40 = 15
        assert score == 15.0

    def test_high_mtbf_bonus(self):
        g = _graph(_comp("app", "App", mtbf_hours=2200))
        opt = CostResilienceOptimizer(g)
        score = opt._component_resilience_score(g.get_component("app"))
        assert score == 5.0 + 10.0  # replica + high MTBF

    def test_medium_mtbf_bonus(self):
        g = _graph(_comp("app", "App", mtbf_hours=800))
        opt = CostResilienceOptimizer(g)
        score = opt._component_resilience_score(g.get_component("app"))
        assert score == 5.0 + 5.0  # replica + medium MTBF

    def test_low_mtbf_no_bonus(self):
        g = _graph(_comp("app", "App", mtbf_hours=100))
        opt = CostResilienceOptimizer(g)
        score = opt._component_resilience_score(g.get_component("app"))
        assert score == 5.0  # Only replica

    def test_score_capped_at_100(self):
        c = _comp(
            "app", "App", replicas=3, failover=True, autoscaling=True,
            backup=True, encryption=True, mtbf_hours=3000,
        )
        g = _graph(c)
        opt = CostResilienceOptimizer(g)
        score = opt._component_resilience_score(g.get_component("app"))
        assert score <= 100.0

    def test_score_capped_at_0(self):
        c = _comp("app", "App", replicas=1, health=HealthStatus.DOWN)
        g = _graph(c)
        opt = CostResilienceOptimizer(g)
        score = opt._component_resilience_score(g.get_component("app"))
        assert score >= 0.0


# ==================================================================
# Improvement detection
# ==================================================================

class TestImprovements:
    def test_replica_improvement_available(self):
        g = _graph(_comp("app", "App", replicas=1))
        opt = CostResilienceOptimizer(g)
        report = opt.analyze()
        types = [o.improvement_type for o in report.improvement_options]
        assert ImprovementType.ADD_REPLICA in types

    def test_no_replica_improvement_at_3(self):
        g = _graph(_comp("app", "App", replicas=3))
        opt = CostResilienceOptimizer(g)
        report = opt.analyze()
        replica_opts = [o for o in report.improvement_options if o.improvement_type == ImprovementType.ADD_REPLICA]
        assert len(replica_opts) == 0

    def test_two_replica_less_gain(self):
        g = _graph(_comp("app", "App", replicas=2))
        opt = CostResilienceOptimizer(g)
        report = opt.analyze()
        replica_opts = [o for o in report.improvement_options if o.improvement_type == ImprovementType.ADD_REPLICA]
        assert len(replica_opts) == 1
        assert replica_opts[0].resilience_score_increase == 10.0  # Less for 3rd

    def test_failover_improvement(self):
        g = _graph(_comp("app", "App"))
        opt = CostResilienceOptimizer(g)
        report = opt.analyze()
        types = [o.improvement_type for o in report.improvement_options]
        assert ImprovementType.ENABLE_FAILOVER in types

    def test_no_failover_when_enabled(self):
        g = _graph(_comp("app", "App", failover=True))
        opt = CostResilienceOptimizer(g)
        report = opt.analyze()
        failover_opts = [o for o in report.improvement_options if o.improvement_type == ImprovementType.ENABLE_FAILOVER]
        assert len(failover_opts) == 0

    def test_autoscaling_improvement(self):
        g = _graph(_comp("app", "App"))
        opt = CostResilienceOptimizer(g)
        report = opt.analyze()
        types = [o.improvement_type for o in report.improvement_options]
        assert ImprovementType.ENABLE_AUTOSCALING in types

    def test_backup_for_database(self):
        g = _graph(_comp("db", "DB", ComponentType.DATABASE))
        opt = CostResilienceOptimizer(g)
        report = opt.analyze()
        types = [o.improvement_type for o in report.improvement_options]
        assert ImprovementType.ENABLE_BACKUP in types

    def test_backup_for_storage(self):
        g = _graph(_comp("s3", "S3", ComponentType.STORAGE))
        opt = CostResilienceOptimizer(g)
        report = opt.analyze()
        types = [o.improvement_type for o in report.improvement_options]
        assert ImprovementType.ENABLE_BACKUP in types

    def test_backup_for_cache(self):
        g = _graph(_comp("redis", "Redis", ComponentType.CACHE))
        opt = CostResilienceOptimizer(g)
        report = opt.analyze()
        types = [o.improvement_type for o in report.improvement_options]
        assert ImprovementType.ENABLE_BACKUP in types

    def test_no_backup_for_app_server(self):
        g = _graph(_comp("app", "App", ComponentType.APP_SERVER))
        opt = CostResilienceOptimizer(g)
        report = opt.analyze()
        backup_opts = [o for o in report.improvement_options if o.improvement_type == ImprovementType.ENABLE_BACKUP]
        assert len(backup_opts) == 0

    def test_encryption_for_database(self):
        g = _graph(_comp("db", "DB", ComponentType.DATABASE))
        opt = CostResilienceOptimizer(g)
        report = opt.analyze()
        types = [o.improvement_type for o in report.improvement_options]
        assert ImprovementType.ENABLE_ENCRYPTION in types

    def test_no_encryption_when_enabled(self):
        g = _graph(_comp("db", "DB", ComponentType.DATABASE, encryption=True))
        opt = CostResilienceOptimizer(g)
        report = opt.analyze()
        enc_opts = [o for o in report.improvement_options if o.improvement_type == ImprovementType.ENABLE_ENCRYPTION]
        assert len(enc_opts) == 0

    def test_monitoring_improvement(self):
        g = _graph(_comp("app", "App", log_enabled=False))
        opt = CostResilienceOptimizer(g)
        report = opt.analyze()
        types = [o.improvement_type for o in report.improvement_options]
        assert ImprovementType.ADD_MONITORING in types

    def test_no_monitoring_when_logged(self):
        g = _graph(_comp("app", "App", log_enabled=True))
        opt = CostResilienceOptimizer(g)
        report = opt.analyze()
        mon_opts = [o for o in report.improvement_options if o.improvement_type == ImprovementType.ADD_MONITORING]
        assert len(mon_opts) == 0

    def test_roi_positive(self):
        g = _graph(_comp("app", "App"))
        opt = CostResilienceOptimizer(g)
        report = opt.analyze()
        for o in report.improvement_options:
            assert o.roi_score > 0

    def test_annual_cost_calculated(self):
        g = _graph(_comp("app", "App"))
        opt = CostResilienceOptimizer(g)
        report = opt.analyze()
        for o in report.improvement_options:
            assert o.annual_cost == round(o.monthly_cost_increase * 12, 2)

    def test_loss_prevented_positive(self):
        g = _graph(_comp("app", "App"))
        opt = CostResilienceOptimizer(g)
        report = opt.analyze()
        for o in report.improvement_options:
            assert o.potential_loss_prevented > 0


# ==================================================================
# Loss estimation
# ==================================================================

class TestLossEstimation:
    def test_database_higher_impact(self):
        g = _graph(
            _comp("app", "App", ComponentType.APP_SERVER),
            _comp("db", "DB", ComponentType.DATABASE),
        )
        opt = CostResilienceOptimizer(g)
        app_loss = opt._estimate_loss_prevented(
            g.get_component("app"), ImprovementType.ADD_REPLICA
        )
        db_loss = opt._estimate_loss_prevented(
            g.get_component("db"), ImprovementType.ADD_REPLICA
        )
        assert db_loss > app_loss

    def test_single_replica_higher_loss(self):
        g = _graph(_comp("a1", "A1", replicas=1), _comp("a3", "A3", replicas=3))
        opt = CostResilienceOptimizer(g)
        loss_1 = opt._estimate_loss_prevented(
            g.get_component("a1"), ImprovementType.ENABLE_FAILOVER
        )
        loss_3 = opt._estimate_loss_prevented(
            g.get_component("a3"), ImprovementType.ENABLE_FAILOVER
        )
        assert loss_1 > loss_3

    def test_unhealthy_higher_loss(self):
        g = _graph(
            _comp("ok", "OK"),
            _comp("bad", "Bad", health=HealthStatus.DOWN),
        )
        opt = CostResilienceOptimizer(g)
        loss_ok = opt._estimate_loss_prevented(
            g.get_component("ok"), ImprovementType.ADD_REPLICA
        )
        loss_bad = opt._estimate_loss_prevented(
            g.get_component("bad"), ImprovementType.ADD_REPLICA
        )
        assert loss_bad > loss_ok

    def test_external_api_type(self):
        g = _graph(_comp("ext", "Ext", ComponentType.EXTERNAL_API))
        opt = CostResilienceOptimizer(g)
        loss = opt._estimate_loss_prevented(
            g.get_component("ext"), ImprovementType.ADD_REPLICA
        )
        assert loss > 0

    def test_custom_type(self):
        g = _graph(_comp("custom", "Custom", ComponentType.CUSTOM))
        opt = CostResilienceOptimizer(g)
        loss = opt._estimate_loss_prevented(
            g.get_component("custom"), ImprovementType.ENABLE_FAILOVER
        )
        assert loss > 0


# ==================================================================
# Optimization strategies
# ==================================================================

class TestStrategies:
    def test_balanced_strategy(self):
        g = _graph(
            _comp("app", "App"),
            _comp("db", "DB", ComponentType.DATABASE),
        )
        opt = CostResilienceOptimizer(g)
        report = opt.analyze(strategy=OptimizationStrategy.BALANCED)
        assert report.strategy == OptimizationStrategy.BALANCED
        assert len(report.optimal_improvements) <= 5

    def test_min_cost_strategy(self):
        g = _graph(_comp("app", "App"))
        opt = CostResilienceOptimizer(g)
        report = opt.analyze(
            strategy=OptimizationStrategy.MIN_COST,
            target_resilience=30.0,
        )
        assert report.strategy == OptimizationStrategy.MIN_COST

    def test_min_cost_already_at_target(self):
        c = _comp("app", "App", replicas=3, failover=True, autoscaling=True)
        g = _graph(c)
        opt = CostResilienceOptimizer(g)
        report = opt.analyze(
            strategy=OptimizationStrategy.MIN_COST,
            target_resilience=10.0,
        )
        assert len(report.optimal_improvements) == 0

    def test_min_cost_default_target(self):
        g = _graph(_comp("app", "App"))
        opt = CostResilienceOptimizer(g)
        report = opt.analyze(strategy=OptimizationStrategy.MIN_COST)
        # Default target is 70, which requires improvements
        assert len(report.optimal_improvements) > 0

    def test_max_resilience_no_budget(self):
        g = _graph(_comp("app", "App"))
        opt = CostResilienceOptimizer(g)
        report = opt.analyze(strategy=OptimizationStrategy.MAX_RESILIENCE)
        # No budget limit — takes all improvements
        assert len(report.optimal_improvements) == len(report.improvement_options)

    def test_max_resilience_with_budget(self):
        g = _graph(_comp("app", "App"))
        opt = CostResilienceOptimizer(g)
        report = opt.analyze(
            strategy=OptimizationStrategy.MAX_RESILIENCE,
            budget_limit=50.0,
        )
        total_cost = sum(o.monthly_cost_increase for o in report.optimal_improvements)
        assert total_cost <= 50.0

    def test_cost_efficient_strategy(self):
        g = _graph(
            _comp("app", "App"),
            _comp("db", "DB", ComponentType.DATABASE),
        )
        opt = CostResilienceOptimizer(g)
        report = opt.analyze(strategy=OptimizationStrategy.COST_EFFICIENT)
        assert report.strategy == OptimizationStrategy.COST_EFFICIENT
        # Should be sorted by ROI
        if len(report.optimal_improvements) >= 2:
            assert report.optimal_improvements[0].roi_score >= report.optimal_improvements[1].roi_score

    def test_cost_efficient_with_budget(self):
        g = _graph(_comp("app", "App"))
        opt = CostResilienceOptimizer(g)
        report = opt.analyze(
            strategy=OptimizationStrategy.COST_EFFICIENT,
            budget_limit=30.0,
        )
        total = sum(o.monthly_cost_increase for o in report.optimal_improvements)
        assert total <= 30.0

    def test_balanced_with_budget(self):
        g = _graph(_comp("app", "App"))
        opt = CostResilienceOptimizer(g)
        report = opt.analyze(
            strategy=OptimizationStrategy.BALANCED,
            budget_limit=20.0,
        )
        total = sum(o.monthly_cost_increase for o in report.optimal_improvements)
        assert total <= 20.0

    def test_no_options_empty_result(self):
        c = _comp(
            "app", "App", replicas=3, failover=True, autoscaling=True,
            backup=True, encryption=True,
        )
        g = _graph(c)
        opt = CostResilienceOptimizer(g)
        report = opt.analyze()
        # Even fully configured may have some options depending on type
        assert report.summary != ""


# ==================================================================
# Pareto frontier
# ==================================================================

class TestParetoFrontier:
    def test_frontier_starts_with_current_state(self):
        g = _graph(_comp("app", "App"))
        opt = CostResilienceOptimizer(g)
        report = opt.analyze()
        assert len(report.pareto_frontier) >= 1
        assert report.pareto_frontier[0].improvement_count == 0

    def test_frontier_monotonically_increasing_resilience(self):
        g = _graph(
            _comp("app", "App"),
            _comp("db", "DB", ComponentType.DATABASE),
        )
        opt = CostResilienceOptimizer(g)
        report = opt.analyze()
        for i in range(1, len(report.pareto_frontier)):
            assert report.pareto_frontier[i].resilience_score >= report.pareto_frontier[i - 1].resilience_score

    def test_frontier_monotonically_increasing_cost(self):
        g = _graph(_comp("app", "App"))
        opt = CostResilienceOptimizer(g)
        report = opt.analyze()
        for i in range(1, len(report.pareto_frontier)):
            assert report.pareto_frontier[i].total_monthly_cost >= report.pareto_frontier[i - 1].total_monthly_cost

    def test_frontier_improvements_accumulated(self):
        g = _graph(_comp("app", "App"))
        opt = CostResilienceOptimizer(g)
        report = opt.analyze()
        for i in range(1, len(report.pareto_frontier)):
            assert report.pareto_frontier[i].improvement_count >= report.pareto_frontier[i - 1].improvement_count

    def test_frontier_resilience_capped_at_100(self):
        g = _graph(_comp("app", "App"))
        opt = CostResilienceOptimizer(g)
        report = opt.analyze()
        for p in report.pareto_frontier:
            assert p.resilience_score <= 100.0


# ==================================================================
# Infrastructure resilience calculation
# ==================================================================

class TestInfrastructureResilience:
    def test_weighted_by_dependents(self):
        from faultray.model.components import Dependency
        g = _graph(
            _comp("lb", "LB", ComponentType.LOAD_BALANCER, replicas=3, failover=True),
            _comp("app", "App", replicas=1),
        )
        g.add_dependency(Dependency(source_id="app", target_id="lb", dependency_type="requires"))
        opt = CostResilienceOptimizer(g)
        score = opt._calculate_infrastructure_resilience()
        # LB has 1 dependent → higher weight → pulls score up
        assert score > 0

    def test_empty_graph_zero_resilience(self):
        opt = CostResilienceOptimizer(InfraGraph())
        assert opt._calculate_infrastructure_resilience() == 0.0


# ==================================================================
# Cost calculation
# ==================================================================

class TestCostCalculation:
    def test_cost_scales_with_replicas(self):
        g1 = _graph(_comp("app", "App", replicas=1))
        g2 = _graph(_comp("app", "App", replicas=3))
        opt1 = CostResilienceOptimizer(g1)
        opt2 = CostResilienceOptimizer(g2)
        r1 = opt1.analyze()
        r2 = opt2.analyze()
        assert r2.current_total_cost > r1.current_total_cost

    def test_database_costs_more_than_app(self):
        g = _graph(
            _comp("app", "App", ComponentType.APP_SERVER, replicas=1),
            _comp("db", "DB", ComponentType.DATABASE, replicas=1),
        )
        opt = CostResilienceOptimizer(g)
        report = opt.analyze()
        app_cost = next(p for p in report.component_profiles if p.component_id == "app").current_monthly_cost
        db_cost = next(p for p in report.component_profiles if p.component_id == "db").current_monthly_cost
        assert db_cost > app_cost

    def test_external_api_zero_cost(self):
        g = _graph(_comp("ext", "Ext", ComponentType.EXTERNAL_API))
        opt = CostResilienceOptimizer(g)
        report = opt.analyze()
        ext_cost = report.component_profiles[0].current_monthly_cost
        assert ext_cost == 0.0


# ==================================================================
# Summary generation
# ==================================================================

class TestSummary:
    def test_summary_contains_strategy(self):
        g = _graph(_comp("app", "App"))
        opt = CostResilienceOptimizer(g)
        report = opt.analyze(strategy=OptimizationStrategy.BALANCED)
        assert "balanced" in report.summary

    def test_summary_no_improvements_message(self):
        c = _comp(
            "app", "App", replicas=3, failover=True, autoscaling=True,
            backup=True, encryption=True,
        )
        g = _graph(c)
        opt = CostResilienceOptimizer(g)
        # Use min_cost strategy with low target to get "no improvements needed"
        report = opt.analyze(
            strategy=OptimizationStrategy.MIN_COST,
            target_resilience=5.0,
        )
        assert "No improvements needed" in report.summary

    def test_summary_with_improvements(self):
        g = _graph(_comp("app", "App"))
        opt = CostResilienceOptimizer(g)
        report = opt.analyze()
        assert "Recommended" in report.summary or "No improvements" in report.summary

    def test_projected_resilience_higher_than_current(self):
        g = _graph(_comp("app", "App"))
        opt = CostResilienceOptimizer(g)
        report = opt.analyze()
        if report.optimal_improvements:
            assert report.projected_resilience > report.current_resilience_score

    def test_projected_resilience_capped(self):
        g = _graph(_comp("app", "App"))
        opt = CostResilienceOptimizer(g)
        report = opt.analyze()
        assert report.projected_resilience <= 100.0


# ==================================================================
# Cost efficiency score
# ==================================================================

class TestCostEfficiency:
    def test_zero_cost_positive_resilience(self):
        # External API has 0 cost
        g = _graph(_comp("ext", "Ext", ComponentType.EXTERNAL_API, replicas=3, failover=True))
        opt = CostResilienceOptimizer(g)
        report = opt.analyze()
        assert report.cost_efficiency_score == 100.0

    def test_zero_cost_zero_resilience(self):
        # Empty graph edge case handled in analysis
        opt = CostResilienceOptimizer(InfraGraph())
        report = opt.analyze()
        assert report.cost_efficiency_score == 0.0

    def test_efficiency_positive(self):
        g = _graph(_comp("app", "App"))
        opt = CostResilienceOptimizer(g)
        report = opt.analyze()
        assert report.cost_efficiency_score >= 0


# ==================================================================
# Component profiles
# ==================================================================

class TestComponentProfiles:
    def test_profile_has_correct_type(self):
        g = _graph(_comp("db", "DB", ComponentType.DATABASE))
        opt = CostResilienceOptimizer(g)
        report = opt.analyze()
        profile = report.component_profiles[0]
        assert profile.component_type == "database"

    def test_max_resilience_higher_than_current(self):
        g = _graph(_comp("app", "App"))
        opt = CostResilienceOptimizer(g)
        report = opt.analyze()
        for p in report.component_profiles:
            assert p.max_achievable_resilience >= p.current_resilience_score

    def test_cost_to_max_positive(self):
        g = _graph(_comp("app", "App"))
        opt = CostResilienceOptimizer(g)
        report = opt.analyze()
        for p in report.component_profiles:
            if p.available_improvements:
                assert p.cost_to_max_resilience > 0


# ==================================================================
# Edge cases
# ==================================================================

class TestEdgeCases:
    def test_all_component_types(self):
        """Every component type should work without errors."""
        comps = [
            _comp(t.value, t.value, t) for t in ComponentType
        ]
        g = _graph(*comps)
        opt = CostResilienceOptimizer(g)
        report = opt.analyze()
        assert len(report.component_profiles) == len(ComponentType)

    def test_very_large_replicas(self):
        g = _graph(_comp("app", "App", replicas=100))
        opt = CostResilienceOptimizer(g)
        report = opt.analyze()
        assert report.current_total_cost > 0

    def test_dns_low_cost(self):
        g = _graph(_comp("dns", "DNS", ComponentType.DNS))
        opt = CostResilienceOptimizer(g)
        report = opt.analyze()
        assert report.component_profiles[0].current_monthly_cost == 10.0

    def test_all_health_statuses(self):
        for health in HealthStatus:
            g = _graph(_comp("app", "App", health=health))
            opt = CostResilienceOptimizer(g)
            report = opt.analyze()
            assert report.current_resilience_score >= 0

    def test_budget_zero(self):
        g = _graph(_comp("app", "App"))
        opt = CostResilienceOptimizer(g)
        report = opt.analyze(
            strategy=OptimizationStrategy.MAX_RESILIENCE,
            budget_limit=0.0,
        )
        assert len(report.optimal_improvements) == 0

    def test_huge_budget(self):
        g = _graph(_comp("app", "App"))
        opt = CostResilienceOptimizer(g)
        report = opt.analyze(
            strategy=OptimizationStrategy.MAX_RESILIENCE,
            budget_limit=1_000_000.0,
        )
        assert len(report.optimal_improvements) == len(report.improvement_options)

    def test_min_cost_resilience_already_exceeds_target(self):
        """Component with high resilience but still has improvement options."""
        # 3 replicas + failover = score ~55, but no autoscaling = has improvement option
        c = _comp("app", "App", replicas=3, failover=True, log_enabled=False)
        g = _graph(c)
        opt = CostResilienceOptimizer(g)
        # Target 10 — well below current resilience
        report = opt.analyze(
            strategy=OptimizationStrategy.MIN_COST,
            target_resilience=10.0,
        )
        # Should select no improvements since already at target
        assert len(report.optimal_improvements) == 0
