"""Tests for Deployment Strategy Analyzer."""

from __future__ import annotations

import pytest
from datetime import datetime, timezone

from faultray.model.components import Component, ComponentType, Dependency, HealthStatus
from faultray.model.graph import InfraGraph
from faultray.simulator.deployment_strategy_analyzer import (
    CanaryProgression,
    CanaryStageConfig,
    DbMigrationAssessment,
    DbMigrationCompat,
    DeploymentRisk,
    DeploymentStrategyAnalyzer,
    DeploymentWindowRecommendation,
    FeatureFlagAssessment,
    HealthCheckAdequacy,
    HealthCheckEvaluation,
    PipelineAnalysis,
    PipelineStage,
    PipelineStageAnalysis,
    RegionDeploymentPlan,
    ResourceCostModel,
    RollbackAnalysis,
    RollbackSafety,
    StrategyAnalysisReport,
    StrategyType,
    VelocityRiskScore,
    ZeroDowntimeVerification,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(cid: str = "c1", ctype: ComponentType = ComponentType.APP_SERVER) -> Component:
    return Component(id=cid, name=cid, type=ctype)


def _graph(*comps: Component) -> InfraGraph:
    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    return g


def _three_tier_graph() -> InfraGraph:
    """LB -> API (3 replicas) -> DB (2 replicas) standard 3-tier."""
    lb = Component(id="lb", name="lb", type=ComponentType.LOAD_BALANCER, replicas=2)
    api = Component(id="api", name="api", type=ComponentType.APP_SERVER, replicas=3)
    db = Component(id="db", name="db", type=ComponentType.DATABASE, replicas=2)
    g = InfraGraph()
    g.add_component(lb)
    g.add_component(api)
    g.add_component(db)
    g.add_dependency(Dependency(source_id="lb", target_id="api"))
    g.add_dependency(Dependency(source_id="api", target_id="db"))
    return g


def _single_component_graph(
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    failover: bool = False,
    autoscaling: bool = False,
) -> tuple[InfraGraph, Component]:
    """Return a graph with a single component and the component itself."""
    c = Component(id="svc", name="svc", type=ctype, replicas=replicas)
    if failover:
        c.failover.enabled = True
    if autoscaling:
        c.autoscaling.enabled = True
    g = _graph(c)
    return g, c


def _large_graph(n: int = 12) -> InfraGraph:
    """Build a graph with *n* chained app-server components."""
    g = InfraGraph()
    comps = []
    for i in range(n):
        c = Component(
            id=f"svc{i}",
            name=f"svc{i}",
            type=ComponentType.APP_SERVER,
            replicas=2,
        )
        g.add_component(c)
        comps.append(c)
    for i in range(n - 1):
        g.add_dependency(Dependency(source_id=comps[i].id, target_id=comps[i + 1].id))
    return g


# ---------------------------------------------------------------------------
# Tests: Enums
# ---------------------------------------------------------------------------


class TestEnums:
    def test_strategy_type_values(self):
        assert StrategyType.ROLLING_UPDATE.value == "rolling_update"
        assert StrategyType.BLUE_GREEN.value == "blue_green"
        assert StrategyType.CANARY.value == "canary"
        assert StrategyType.AB_TESTING.value == "ab_testing"
        assert StrategyType.RECREATE.value == "recreate"
        assert StrategyType.SHADOW.value == "shadow"

    def test_strategy_type_count(self):
        assert len(StrategyType) == 6

    def test_rollback_safety_values(self):
        assert RollbackSafety.INSTANT.value == "instant"
        assert RollbackSafety.FAST.value == "fast"
        assert RollbackSafety.MODERATE.value == "moderate"
        assert RollbackSafety.SLOW.value == "slow"
        assert RollbackSafety.DANGEROUS.value == "dangerous"

    def test_deployment_risk_values(self):
        assert DeploymentRisk.LOW.value == "low"
        assert DeploymentRisk.MODERATE.value == "moderate"
        assert DeploymentRisk.HIGH.value == "high"
        assert DeploymentRisk.CRITICAL.value == "critical"

    def test_pipeline_stage_values(self):
        assert PipelineStage.BUILD.value == "build"
        assert PipelineStage.TEST.value == "test"
        assert PipelineStage.STAGE.value == "stage"
        assert PipelineStage.PROD.value == "prod"

    def test_health_check_adequacy(self):
        assert HealthCheckAdequacy.EXCELLENT.value == "excellent"
        assert HealthCheckAdequacy.MISSING.value == "missing"

    def test_db_migration_compat(self):
        assert DbMigrationCompat.FULLY_COMPATIBLE.value == "fully_compatible"
        assert DbMigrationCompat.INCOMPATIBLE.value == "incompatible"


# ---------------------------------------------------------------------------
# Tests: Rollback Analysis
# ---------------------------------------------------------------------------


class TestRollbackAnalysis:
    def test_blue_green_rollback_instant(self):
        g = _graph(_comp("a1"))
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.analyze_rollback(StrategyType.BLUE_GREEN)
        assert result.safety == RollbackSafety.INSTANT
        assert result.rollback_time_seconds == 10.0
        assert result.data_compatible is True
        assert len(result.steps) > 0

    def test_canary_rollback_fast(self):
        g = _graph(_comp("a1"))
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.analyze_rollback(StrategyType.CANARY)
        assert result.safety == RollbackSafety.FAST
        assert result.rollback_time_seconds == 30.0

    def test_rolling_update_rollback_scales_with_components(self):
        g = _large_graph(8)
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.analyze_rollback(StrategyType.ROLLING_UPDATE)
        assert result.safety == RollbackSafety.MODERATE
        assert result.rollback_time_seconds >= 8 * 15.0

    def test_recreate_rollback_dangerous(self):
        g = _graph(_comp("a1"))
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.analyze_rollback(StrategyType.RECREATE)
        assert result.safety == RollbackSafety.DANGEROUS
        assert result.data_compatible is False
        assert result.requires_data_migration is True
        assert result.estimated_data_loss_risk > 0
        assert len(result.warnings) > 0

    def test_shadow_rollback_instant(self):
        g = _graph(_comp("a1"))
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.analyze_rollback(StrategyType.SHADOW)
        assert result.safety == RollbackSafety.INSTANT
        assert result.rollback_time_seconds == 5.0

    def test_ab_testing_rollback_fast(self):
        g = _graph(_comp("a1"))
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.analyze_rollback(StrategyType.AB_TESTING)
        assert result.safety == RollbackSafety.FAST
        assert result.rollback_time_seconds == 20.0

    def test_stateful_components_increase_rollback_time(self):
        db = _comp("db1", ComponentType.DATABASE)
        g = _graph(db)
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.analyze_rollback(StrategyType.ROLLING_UPDATE)
        # Should be multiplied by 1.5 for stateful
        assert result.rollback_time_seconds > 60.0
        assert any("Stateful" in w for w in result.warnings)

    def test_stateful_does_not_affect_blue_green(self):
        db = _comp("db1", ComponentType.DATABASE)
        g = _graph(db)
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.analyze_rollback(StrategyType.BLUE_GREEN)
        assert result.rollback_time_seconds == 10.0  # no multiplier


# ---------------------------------------------------------------------------
# Tests: Canary Analysis
# ---------------------------------------------------------------------------


class TestCanaryAnalysis:
    def test_canary_stages_default(self):
        g = _graph(_comp("a1"))
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.analyze_canary(StrategyType.CANARY)
        assert len(result.stages) == 7  # _CANARY_DEFAULT_STAGES has 7 entries
        assert result.stages[0].traffic_percent == 1.0
        assert result.stages[-1].traffic_percent == 100.0

    def test_canary_not_applicable_for_other_strategies(self):
        g = _graph(_comp("a1"))
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.analyze_canary(StrategyType.BLUE_GREEN)
        assert len(result.stages) == 0
        assert any("not applicable" in r for r in result.recommendations)

    def test_canary_custom_stages(self):
        g = _graph(_comp("a1"))
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.analyze_canary(
            StrategyType.CANARY, custom_stages=[5.0, 50.0, 100.0]
        )
        assert len(result.stages) == 3
        assert result.stages[0].traffic_percent == 5.0

    def test_canary_with_database_increases_duration(self):
        db = _comp("db1", ComponentType.DATABASE)
        g = _graph(db)
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.analyze_canary(StrategyType.CANARY)
        assert any("Database" in r for r in result.recommendations)
        # All durations should be multiplied by 1.5
        for stage in result.stages:
            assert stage.duration_minutes >= 4  # smallest base 3 * 1.5 = 4.5 -> 4

    def test_canary_large_topology_recommendation(self):
        g = _large_graph(12)
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.analyze_canary(StrategyType.CANARY)
        assert any("Large topology" in r for r in result.recommendations)

    def test_canary_auto_promote_small_graph(self):
        g = _graph(_comp("a1"), _comp("a2", ComponentType.WEB_SERVER))
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.analyze_canary(StrategyType.CANARY)
        assert result.auto_promote is True

    def test_canary_auto_rollback_always_true(self):
        g = _graph(_comp("a1"))
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.analyze_canary(StrategyType.CANARY)
        assert result.auto_rollback is True

    def test_canary_total_duration(self):
        g = _graph(_comp("a1"))
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.analyze_canary(StrategyType.CANARY)
        expected = sum(s.duration_minutes for s in result.stages)
        assert result.total_duration_minutes == expected

    def test_canary_abort_thresholds_vary_by_stage(self):
        g = _graph(_comp("a1"))
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.analyze_canary(StrategyType.CANARY)
        # Early stages (< 50%) should have 5.0 abort threshold
        early = [s for s in result.stages if s.traffic_percent < 50]
        late = [s for s in result.stages if s.traffic_percent >= 50]
        for s in early:
            assert s.error_rate_abort_threshold == 5.0
        for s in late:
            assert s.error_rate_abort_threshold == 3.0


# ---------------------------------------------------------------------------
# Tests: Resource Cost Model
# ---------------------------------------------------------------------------


class TestResourceCostModel:
    def test_blue_green_2x_cost(self):
        g = _graph(_comp("a1"))
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.analyze_cost(StrategyType.BLUE_GREEN)
        assert result.cost_multiplier == 2.0
        assert result.peak_extra_instances == 1  # single instance duplicated
        assert any("2x cost" in n for n in result.notes)

    def test_shadow_cost(self):
        g = _graph(_comp("a1"))
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.analyze_cost(StrategyType.SHADOW)
        assert result.cost_multiplier == 1.8
        assert any("Shadow" in n for n in result.notes)

    def test_recreate_lowest_cost(self):
        g = _graph(_comp("a1"))
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.analyze_cost(StrategyType.RECREATE)
        assert result.cost_multiplier == 1.0
        assert result.peak_extra_instances == 0

    def test_cost_with_hourly_rates(self):
        c = _comp("a1")
        c.cost_profile.hourly_infra_cost = 10.0
        g = _graph(c)
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.analyze_cost(StrategyType.BLUE_GREEN)
        assert result.total_deployment_cost == 20.0
        assert result.peak_extra_cost_hourly == 10.0
        assert result.steady_state_cost_hourly == 10.0

    def test_canary_extra_instances(self):
        comps = [_comp(f"a{i}") for i in range(10)]
        g = _graph(*comps)
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.analyze_cost(StrategyType.CANARY)
        assert result.peak_extra_instances >= 1  # 15% of 10 = ~2

    def test_rolling_update_cost_multiplier(self):
        g = _graph(_comp("a1"))
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.analyze_cost(StrategyType.ROLLING_UPDATE)
        assert result.cost_multiplier == 1.1

    def test_ab_testing_extra_instances(self):
        comps = [_comp(f"a{i}") for i in range(5)]
        g = _graph(*comps)
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.analyze_cost(StrategyType.AB_TESTING)
        assert result.peak_extra_instances >= 1  # 30% of 5 = ~2


# ---------------------------------------------------------------------------
# Tests: Velocity vs Risk Tradeoff
# ---------------------------------------------------------------------------


class TestVelocityRiskScore:
    def test_recreate_high_velocity_high_risk(self):
        g = _graph(_comp("a1"))
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.analyze_velocity_risk(StrategyType.RECREATE)
        assert result.velocity_score >= 80.0
        assert result.risk_score >= 80.0

    def test_shadow_low_velocity_low_risk(self):
        g = _graph(_comp("a1"))
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.analyze_velocity_risk(StrategyType.SHADOW)
        assert result.velocity_score <= 40.0
        assert result.risk_score <= 20.0

    def test_composite_score_in_bounds(self):
        g = _graph(_comp("a1"))
        analyzer = DeploymentStrategyAnalyzer(g)
        for st in StrategyType:
            result = analyzer.analyze_velocity_risk(st)
            assert 0.0 <= result.composite_score <= 100.0

    def test_large_graph_increases_risk(self):
        g = _large_graph(15)
        analyzer = DeploymentStrategyAnalyzer(g)
        result_large = analyzer.analyze_velocity_risk(StrategyType.ROLLING_UPDATE)

        g_small = _graph(_comp("a1"))
        analyzer_small = DeploymentStrategyAnalyzer(g_small)
        result_small = analyzer_small.analyze_velocity_risk(StrategyType.ROLLING_UPDATE)

        assert result_large.risk_score > result_small.risk_score

    def test_recommendation_text_present(self):
        g = _graph(_comp("a1"))
        analyzer = DeploymentStrategyAnalyzer(g)
        for st in StrategyType:
            result = analyzer.analyze_velocity_risk(st)
            assert result.recommendation != ""


# ---------------------------------------------------------------------------
# Tests: Health Check Evaluation
# ---------------------------------------------------------------------------


class TestHealthCheckEvaluation:
    def test_missing_health_checks(self):
        c = _comp("a1")
        g = _graph(c)
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.evaluate_health_check(c, StrategyType.ROLLING_UPDATE)
        assert result.adequacy == HealthCheckAdequacy.MISSING
        assert any("No health checks" in r for r in result.recommendations)

    def test_failover_enables_probes(self):
        c = _comp("a1")
        c.failover.enabled = True
        g = _graph(c)
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.evaluate_health_check(c, StrategyType.CANARY)
        assert result.has_liveness_probe is True
        assert result.has_readiness_probe is True

    def test_excellent_health_checks(self):
        c = Component(
            id="svc", name="svc", type=ComponentType.APP_SERVER, replicas=3
        )
        c.failover.enabled = True
        c.autoscaling.enabled = True
        g = _graph(c)
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.evaluate_health_check(c, StrategyType.CANARY)
        assert result.adequacy == HealthCheckAdequacy.EXCELLENT

    def test_rolling_update_readiness_recommendation(self):
        c = _comp("a1")
        g = _graph(c)
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.evaluate_health_check(c, StrategyType.ROLLING_UPDATE)
        assert any("Readiness probe" in r for r in result.recommendations)

    def test_canary_liveness_recommendation(self):
        c = _comp("a1")
        g = _graph(c)
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.evaluate_health_check(c, StrategyType.CANARY)
        assert any("Liveness probe" in r for r in result.recommendations)

    def test_blue_green_readiness_recommendation(self):
        c = _comp("a1")
        g = _graph(c)
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.evaluate_health_check(c, StrategyType.BLUE_GREEN)
        assert any("Readiness probe" in r for r in result.recommendations)

    def test_long_probe_interval_warning(self):
        c = _comp("a1")
        c.failover.enabled = True
        c.failover.health_check_interval_seconds = 60.0
        g = _graph(c)
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.evaluate_health_check(c, StrategyType.ROLLING_UPDATE)
        assert any("too long" in r for r in result.recommendations)


# ---------------------------------------------------------------------------
# Tests: Database Migration Compatibility
# ---------------------------------------------------------------------------


class TestDbMigrationCompatibility:
    def test_non_db_component_fully_compatible(self):
        c = _comp("a1", ComponentType.APP_SERVER)
        g = _graph(c)
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.assess_db_migration(c, StrategyType.BLUE_GREEN)
        assert result.compatibility == DbMigrationCompat.FULLY_COMPATIBLE

    def test_recreate_db_incompatible(self):
        c = _comp("db1", ComponentType.DATABASE)
        g = _graph(c)
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.assess_db_migration(c, StrategyType.RECREATE)
        assert result.compatibility == DbMigrationCompat.INCOMPATIBLE
        assert result.rollback_migration_possible is False

    def test_blue_green_db_dual_write(self):
        c = _comp("db1", ComponentType.DATABASE)
        g = _graph(c)
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.assess_db_migration(c, StrategyType.BLUE_GREEN)
        assert result.compatibility == DbMigrationCompat.REQUIRES_DUAL_WRITE
        assert result.requires_backward_compat_schema is True

    def test_canary_db_compatible_with_caution(self):
        c = _comp("db1", ComponentType.DATABASE)
        g = _graph(c)
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.assess_db_migration(c, StrategyType.CANARY)
        assert result.compatibility == DbMigrationCompat.COMPATIBLE_WITH_CAUTION

    def test_rolling_update_db(self):
        c = _comp("db1", ComponentType.DATABASE)
        g = _graph(c)
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.assess_db_migration(c, StrategyType.ROLLING_UPDATE)
        assert result.compatibility == DbMigrationCompat.COMPATIBLE_WITH_CAUTION
        assert result.requires_backward_compat_schema is True

    def test_shadow_db_fully_compatible(self):
        c = _comp("db1", ComponentType.DATABASE)
        g = _graph(c)
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.assess_db_migration(c, StrategyType.SHADOW)
        assert result.compatibility == DbMigrationCompat.FULLY_COMPATIBLE

    def test_ab_testing_db_dual_write(self):
        c = _comp("db1", ComponentType.DATABASE)
        g = _graph(c)
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.assess_db_migration(c, StrategyType.AB_TESTING)
        assert result.compatibility == DbMigrationCompat.REQUIRES_DUAL_WRITE

    def test_replicas_increase_migration_time(self):
        c = Component(
            id="db1", name="db1", type=ComponentType.DATABASE, replicas=3
        )
        g = _graph(c)
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.assess_db_migration(c, StrategyType.CANARY)
        # Base 20 * 1.2 = 24
        assert result.estimated_migration_time_minutes >= 24

    def test_storage_component_treated_as_db(self):
        c = _comp("store1", ComponentType.STORAGE)
        g = _graph(c)
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.assess_db_migration(c, StrategyType.RECREATE)
        assert result.compatibility == DbMigrationCompat.INCOMPATIBLE


# ---------------------------------------------------------------------------
# Tests: Multi-Region Coordination
# ---------------------------------------------------------------------------


class TestMultiRegionPlan:
    def test_no_regions(self):
        g = _graph(_comp("a1"))
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.plan_multi_region(StrategyType.BLUE_GREEN, [])
        assert len(result.regions) == 0
        assert any("single-region" in r for r in result.recommendations)

    def test_single_region(self):
        g = _graph(_comp("a1"))
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.plan_multi_region(StrategyType.CANARY, ["us-east-1"])
        assert result.canary_region == "us-east-1"
        assert result.sequence == ["us-east-1"]
        assert result.rollback_order == ["us-east-1"]

    def test_three_regions_canary_first(self):
        g = _graph(_comp("a1"))
        analyzer = DeploymentStrategyAnalyzer(g)
        regions = ["us-east-1", "eu-west-1", "ap-northeast-1"]
        result = analyzer.plan_multi_region(StrategyType.BLUE_GREEN, regions)
        assert result.canary_region == "us-east-1"
        assert result.rollback_order == list(reversed(regions))
        assert result.total_deployment_time_seconds > 0
        assert any("canary region" in r for r in result.recommendations)

    def test_five_regions_wave_recommendation(self):
        g = _graph(_comp("a1"))
        analyzer = DeploymentStrategyAnalyzer(g)
        regions = [f"region-{i}" for i in range(5)]
        result = analyzer.plan_multi_region(StrategyType.ROLLING_UPDATE, regions)
        assert any("wave-based" in r for r in result.recommendations)

    def test_recreate_multi_region_warning(self):
        g = _graph(_comp("a1"))
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.plan_multi_region(
            StrategyType.RECREATE, ["us-east-1", "eu-west-1"]
        )
        assert any("rolling outages" in r for r in result.recommendations)

    def test_coordination_overhead_scales(self):
        g = _graph(_comp("a1"))
        analyzer = DeploymentStrategyAnalyzer(g)
        result2 = analyzer.plan_multi_region(
            StrategyType.CANARY, ["r1", "r2"]
        )
        result4 = analyzer.plan_multi_region(
            StrategyType.CANARY, ["r1", "r2", "r3", "r4"]
        )
        assert result4.coordination_overhead_seconds > result2.coordination_overhead_seconds


# ---------------------------------------------------------------------------
# Tests: Deployment Window Optimization
# ---------------------------------------------------------------------------


class TestDeploymentWindow:
    def test_safe_hour(self):
        g = _graph(_comp("a1"))
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.recommend_window(3)
        assert result.is_safe_hour is True
        assert result.is_peak_hour is False
        assert result.risk_level == DeploymentRisk.LOW

    def test_peak_hour(self):
        g = _graph(_comp("a1"))
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.recommend_window(10)
        assert result.is_peak_hour is True
        assert result.risk_level == DeploymentRisk.HIGH
        # Should suggest safe alternative
        assert result.recommended_hour_utc == 3

    def test_moderate_hour(self):
        g = _graph(_comp("a1"))
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.recommend_window(20)
        assert result.is_peak_hour is False
        assert result.is_safe_hour is False
        assert result.risk_level == DeploymentRisk.MODERATE

    def test_high_utilization_warning(self):
        c = _comp("a1")
        c.metrics.cpu_percent = 85.0
        g = _graph(c)
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.recommend_window(3)
        assert any("high utilization" in n for n in result.notes)

    def test_recommended_day_is_wednesday(self):
        g = _graph(_comp("a1"))
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.recommend_window(3)
        assert result.recommended_day_of_week == 2  # Wednesday


# ---------------------------------------------------------------------------
# Tests: Feature Flag Assessment
# ---------------------------------------------------------------------------


class TestFeatureFlagAssessment:
    def test_no_flags(self):
        g = _graph(_comp("a1"))
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.assess_feature_flags([])
        assert result.has_feature_flags is False
        assert result.flag_count == 0
        assert any("tightly coupled" in r for r in result.recommendations)

    def test_flags_present(self):
        g = _graph(_comp("a1"))
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.assess_feature_flags(["new-checkout-ui"])
        assert result.has_feature_flags is True
        assert result.flag_count == 1
        assert result.decoupled_deploy_and_release is True

    def test_kill_switch_detected(self):
        g = _graph(_comp("a1"))
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.assess_feature_flags(["kill-switch-checkout"])
        assert result.kill_switch_available is True
        assert result.risk_reduction_percent >= 25.0

    def test_gradual_rollout_detected(self):
        g = _graph(_comp("a1"))
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.assess_feature_flags(["gradual-rollout-v2"])
        assert result.gradual_rollout_possible is True

    def test_many_flags_bonus(self):
        g = _graph(_comp("a1"))
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.assess_feature_flags(
            ["f1", "f2", "f3", "kill-switch", "gradual-rollout"]
        )
        assert result.risk_reduction_percent >= 40.0

    def test_missing_kill_switch_recommendation(self):
        g = _graph(_comp("a1"))
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.assess_feature_flags(["feature-a"])
        assert any("kill switch" in r for r in result.recommendations)

    def test_missing_gradual_recommendation(self):
        g = _graph(_comp("a1"))
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.assess_feature_flags(["feature-a"])
        assert any("gradual" in r.lower() for r in result.recommendations)


# ---------------------------------------------------------------------------
# Tests: Zero-Downtime Verification
# ---------------------------------------------------------------------------


class TestZeroDowntimeVerification:
    def test_recreate_not_zero_downtime(self):
        g = _graph(_comp("a1"))
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.verify_zero_downtime(StrategyType.RECREATE)
        assert result.is_zero_downtime is False
        assert result.estimated_downtime_seconds > 0
        assert result.confidence == 0.0
        assert len(result.blockers) > 0

    def test_blue_green_zero_downtime(self):
        g = _graph(_comp("a1"))
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.verify_zero_downtime(StrategyType.BLUE_GREEN)
        assert result.is_zero_downtime is True
        assert result.confidence >= 0.75

    def test_blue_green_spof_reduces_confidence(self):
        c = _comp("a1")
        svc = _comp("b1")
        g = _graph(c, svc)
        g.add_dependency(Dependency(source_id="a1", target_id="b1"))
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.verify_zero_downtime(StrategyType.BLUE_GREEN)
        # b1 is SPOF (1 replica, no failover, has dependent a1)
        # Wait - a1 depends on b1, so b1 has dependents
        assert result.confidence <= 0.95

    def test_canary_zero_downtime(self):
        g = _graph(_comp("a1"))
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.verify_zero_downtime(StrategyType.CANARY)
        assert result.is_zero_downtime is True
        assert result.confidence == 0.9

    def test_rolling_update_multi_replica_zero_downtime(self):
        c = Component(
            id="svc", name="svc", type=ComponentType.APP_SERVER, replicas=3
        )
        g = _graph(c)
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.verify_zero_downtime(StrategyType.ROLLING_UPDATE)
        assert result.is_zero_downtime is True

    def test_rolling_update_single_replica_not_zero_downtime(self):
        c = _comp("svc")
        g = _graph(c)
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.verify_zero_downtime(StrategyType.ROLLING_UPDATE)
        assert result.is_zero_downtime is False
        assert "svc" in result.blockers[0]
        assert len(result.mitigations) > 0

    def test_shadow_highest_confidence(self):
        g = _graph(_comp("a1"))
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.verify_zero_downtime(StrategyType.SHADOW)
        assert result.is_zero_downtime is True
        assert result.confidence == 0.98

    def test_ab_testing_zero_downtime(self):
        g = _graph(_comp("a1"))
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.verify_zero_downtime(StrategyType.AB_TESTING)
        assert result.is_zero_downtime is True
        assert result.confidence == 0.88

    def test_rolling_empty_graph(self):
        g = InfraGraph()
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.verify_zero_downtime(StrategyType.ROLLING_UPDATE)
        assert result.is_zero_downtime is True


# ---------------------------------------------------------------------------
# Tests: Pipeline Analysis
# ---------------------------------------------------------------------------


class TestPipelineAnalysis:
    def test_default_pipeline(self):
        g = _graph(_comp("a1"))
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.analyze_pipeline()
        assert len(result.stages) == 4
        assert result.total_duration_minutes > 0

    def test_missing_stages_detected(self):
        g = _graph(_comp("a1"))
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.analyze_pipeline(["build", "prod"])
        assert "test" in result.missing_stages or "stage" in result.missing_stages
        assert result.overall_risk == DeploymentRisk.HIGH

    def test_invalid_stage_ignored(self):
        g = _graph(_comp("a1"))
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.analyze_pipeline(["build", "test", "nonexistent", "prod"])
        stage_names = [s.stage.value for s in result.stages]
        assert "nonexistent" not in stage_names
        assert "build" in stage_names

    def test_build_stage_properties(self):
        g = _graph(_comp("a1"))
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.analyze_pipeline(["build"])
        build = result.stages[0]
        assert build.stage == PipelineStage.BUILD
        assert build.has_automated_tests is False
        assert build.risk_score == 10.0

    def test_prod_stage_has_gates(self):
        g = _graph(_comp("a1"))
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.analyze_pipeline(["prod"])
        prod = result.stages[0]
        assert prod.has_approval_gate is True
        assert prod.has_rollback_mechanism is True
        assert prod.risk_score == 60.0

    def test_no_approval_gate_recommendation(self):
        g = _graph(_comp("a1"))
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.analyze_pipeline(["build", "test"])
        assert any("approval gate" in r.lower() for r in result.recommendations)

    def test_full_automation_check(self):
        g = _graph(_comp("a1"))
        analyzer = DeploymentStrategyAnalyzer(g)
        # build has no tests, so full automation should be false
        result = analyzer.analyze_pipeline(["build", "test", "stage", "prod"])
        assert result.has_full_automation is False

    def test_only_auto_test_stages(self):
        g = _graph(_comp("a1"))
        analyzer = DeploymentStrategyAnalyzer(g)
        # test, stage, prod all have automated_tests = True
        result = analyzer.analyze_pipeline(["test", "stage", "prod"])
        assert result.has_full_automation is True


# ---------------------------------------------------------------------------
# Tests: Full Analysis (analyze method)
# ---------------------------------------------------------------------------


class TestFullAnalysis:
    def test_analyze_returns_report(self):
        g = _three_tier_graph()
        analyzer = DeploymentStrategyAnalyzer(g)
        report = analyzer.analyze(StrategyType.BLUE_GREEN)
        assert isinstance(report, StrategyAnalysisReport)
        assert report.strategy == StrategyType.BLUE_GREEN
        assert report.graph_component_count == 3

    def test_analyze_populates_all_fields(self):
        g = _three_tier_graph()
        analyzer = DeploymentStrategyAnalyzer(g)
        report = analyzer.analyze(StrategyType.CANARY, regions=["us-east-1"])
        assert report.rollback is not None
        assert report.canary is not None
        assert report.cost is not None
        assert report.velocity_risk is not None
        assert len(report.health_checks) == 3
        assert report.region_plan is not None
        assert report.window is not None
        assert report.feature_flags is not None
        assert report.zero_downtime is not None
        assert report.pipeline is not None

    def test_analyze_db_migrations_only_for_stateful(self):
        g = _three_tier_graph()
        analyzer = DeploymentStrategyAnalyzer(g)
        report = analyzer.analyze(StrategyType.BLUE_GREEN)
        # Only DB component should appear in db_migrations
        assert len(report.db_migrations) == 1
        assert report.db_migrations[0].component_id == "db"

    def test_overall_score_in_bounds(self):
        g = _three_tier_graph()
        analyzer = DeploymentStrategyAnalyzer(g)
        for st in StrategyType:
            report = analyzer.analyze(st)
            assert 0.0 <= report.overall_score <= 100.0

    def test_overall_risk_classification(self):
        g = _graph(_comp("a1"))
        analyzer = DeploymentStrategyAnalyzer(g)
        report = analyzer.analyze(StrategyType.SHADOW)
        # Shadow should score well (high confidence, instant rollback)
        assert report.overall_risk in (DeploymentRisk.LOW, DeploymentRisk.MODERATE)

    def test_recreate_higher_risk_than_blue_green(self):
        g = _three_tier_graph()
        analyzer = DeploymentStrategyAnalyzer(g)
        recreate = analyzer.analyze(StrategyType.RECREATE)
        blue_green = analyzer.analyze(StrategyType.BLUE_GREEN)
        assert recreate.overall_score < blue_green.overall_score

    def test_analyze_with_feature_flags(self):
        g = _graph(_comp("a1"))
        analyzer = DeploymentStrategyAnalyzer(g)
        report = analyzer.analyze(
            StrategyType.CANARY,
            feature_flags=["kill-switch", "gradual-rollout"],
        )
        assert report.feature_flags is not None
        assert report.feature_flags.has_feature_flags is True
        assert report.feature_flags.kill_switch_available is True

    def test_analyze_with_custom_pipeline(self):
        g = _graph(_comp("a1"))
        analyzer = DeploymentStrategyAnalyzer(g)
        report = analyzer.analyze(
            StrategyType.ROLLING_UPDATE,
            pipeline_stages=["build", "test"],
        )
        assert report.pipeline is not None
        assert len(report.pipeline.stages) == 2

    def test_analyze_peak_hour_affects_window(self):
        g = _graph(_comp("a1"))
        analyzer = DeploymentStrategyAnalyzer(g)
        report = analyzer.analyze(StrategyType.CANARY, deploy_hour_utc=12)
        assert report.window is not None
        assert report.window.is_peak_hour is True

    def test_report_to_dict(self):
        g = _graph(_comp("a1"))
        analyzer = DeploymentStrategyAnalyzer(g)
        report = analyzer.analyze(StrategyType.BLUE_GREEN)
        d = report.to_dict()
        assert d["strategy"] == "blue_green"
        assert "overall_score" in d
        assert "timestamp" in d

    def test_recommendations_are_deduplicated(self):
        g = _three_tier_graph()
        analyzer = DeploymentStrategyAnalyzer(g)
        report = analyzer.analyze(StrategyType.CANARY)
        # All recommendations should be unique
        assert len(report.recommendations) == len(set(report.recommendations))

    def test_timestamp_is_utc(self):
        g = _graph(_comp("a1"))
        analyzer = DeploymentStrategyAnalyzer(g)
        report = analyzer.analyze(StrategyType.BLUE_GREEN)
        assert report.timestamp.tzinfo is not None


# ---------------------------------------------------------------------------
# Tests: Compare Strategies & Best Strategy
# ---------------------------------------------------------------------------


class TestCompareStrategies:
    def test_compare_all_strategies(self):
        g = _three_tier_graph()
        analyzer = DeploymentStrategyAnalyzer(g)
        reports = analyzer.compare_strategies()
        assert len(reports) == len(StrategyType)
        # Should be sorted by score descending
        scores = [r.overall_score for r in reports]
        assert scores == sorted(scores, reverse=True)

    def test_compare_subset(self):
        g = _graph(_comp("a1"))
        analyzer = DeploymentStrategyAnalyzer(g)
        reports = analyzer.compare_strategies(
            strategies=[StrategyType.BLUE_GREEN, StrategyType.CANARY]
        )
        assert len(reports) == 2

    def test_best_strategy_returns_highest_score(self):
        g = _three_tier_graph()
        analyzer = DeploymentStrategyAnalyzer(g)
        best = analyzer.best_strategy()
        all_reports = analyzer.compare_strategies()
        assert best.overall_score == all_reports[0].overall_score

    def test_best_strategy_with_regions(self):
        g = _graph(_comp("a1"))
        analyzer = DeploymentStrategyAnalyzer(g)
        best = analyzer.best_strategy(regions=["us-east-1", "eu-west-1"])
        assert best.region_plan is not None
        assert len(best.region_plan.regions) == 2


# ---------------------------------------------------------------------------
# Tests: Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_graph(self):
        g = InfraGraph()
        analyzer = DeploymentStrategyAnalyzer(g)
        report = analyzer.analyze(StrategyType.BLUE_GREEN)
        assert report.graph_component_count == 0
        assert len(report.health_checks) == 0
        assert len(report.db_migrations) == 0

    def test_single_db_graph(self):
        db = _comp("db1", ComponentType.DATABASE)
        g = _graph(db)
        analyzer = DeploymentStrategyAnalyzer(g)
        report = analyzer.analyze(StrategyType.BLUE_GREEN)
        assert len(report.db_migrations) == 1

    def test_graph_with_no_edges(self):
        g = _graph(_comp("a1"), _comp("a2"), _comp("a3"))
        analyzer = DeploymentStrategyAnalyzer(g)
        report = analyzer.analyze(StrategyType.ROLLING_UPDATE)
        assert report.graph_component_count == 3

    def test_all_strategies_for_three_tier(self):
        """Smoke test: every strategy on a realistic graph without error."""
        g = _three_tier_graph()
        analyzer = DeploymentStrategyAnalyzer(g)
        for st in StrategyType:
            report = analyzer.analyze(st)
            assert report.strategy == st
            assert isinstance(report.overall_score, float)

    def test_high_replica_recreate_downtime(self):
        comps = [
            Component(
                id=f"svc{i}", name=f"svc{i}",
                type=ComponentType.APP_SERVER, replicas=5,
            )
            for i in range(4)
        ]
        g = _graph(*comps)
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.verify_zero_downtime(StrategyType.RECREATE)
        # 4 components * 5 replicas = 20 total replicas * 10s = 200s
        assert result.estimated_downtime_seconds >= 200.0

    def test_cost_zero_hourly(self):
        """Components with zero hourly cost should not produce negative costs."""
        g = _graph(_comp("a1"))
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.analyze_cost(StrategyType.BLUE_GREEN)
        assert result.peak_extra_cost_hourly == 0.0
        assert result.total_deployment_cost == 0.0

    def test_pipeline_empty_list(self):
        g = _graph(_comp("a1"))
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.analyze_pipeline([])
        assert len(result.stages) == 0
        # All default stages should be missing
        assert len(result.missing_stages) == 4

    def test_canary_empty_custom_stages(self):
        g = _graph(_comp("a1"))
        analyzer = DeploymentStrategyAnalyzer(g)
        result = analyzer.analyze_canary(
            StrategyType.CANARY, custom_stages=[]
        )
        assert len(result.stages) == 0
        assert result.total_duration_minutes == 0

    def test_risk_classification_boundaries(self):
        g = _graph(_comp("a1"))
        analyzer = DeploymentStrategyAnalyzer(g)
        assert analyzer._classify_risk(100.0) == DeploymentRisk.LOW
        assert analyzer._classify_risk(75.0) == DeploymentRisk.LOW
        assert analyzer._classify_risk(74.9) == DeploymentRisk.MODERATE
        assert analyzer._classify_risk(50.0) == DeploymentRisk.MODERATE
        assert analyzer._classify_risk(49.9) == DeploymentRisk.HIGH
        assert analyzer._classify_risk(25.0) == DeploymentRisk.HIGH
        assert analyzer._classify_risk(24.9) == DeploymentRisk.CRITICAL
        assert analyzer._classify_risk(0.0) == DeploymentRisk.CRITICAL
