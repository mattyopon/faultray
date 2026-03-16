"""Tests for the Disaster Recovery Simulator."""

from __future__ import annotations

import math

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    CircuitBreakerConfig,
    Component,
    ComponentType,
    CostProfile,
    Dependency,
    FailoverConfig,
    OperationalProfile,
    RegionConfig,
    ResourceMetrics,
    SecurityProfile,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.disaster_recovery import (
    DRCostEstimate,
    DRGap,
    DRPlan,
    DRPlanValidation,
    DRSimulationResult,
    DRStrategy,
    DisasterRecoveryEngine,
    DisasterType,
    FailbackResult,
    RPORTOEstimate,
    StrategyComparison,
    _DISASTER_SEVERITY,
    _STRATEGY_COST_MULTIPLIER,
    _STRATEGY_RPO_MULTIPLIER,
    _STRATEGY_RTO_MULTIPLIER,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_component(
    cid: str,
    ctype: ComponentType = ComponentType.APP_SERVER,
    region: str = "",
    az: str = "",
    replicas: int = 1,
    failover: bool = False,
    promotion_time: float = 30.0,
    backup_enabled: bool = False,
    backup_freq: float = 24.0,
    encryption_at_rest: bool = False,
    autoscaling: bool = False,
    rpo_seconds: int = 0,
    rto_seconds: int = 0,
    mttr_minutes: float = 30.0,
    hourly_cost: float = 0.0,
    disk_used_gb: float = 0.0,
    network_segmented: bool = False,
) -> Component:
    return Component(
        id=cid,
        name=cid,
        type=ctype,
        replicas=replicas,
        failover=FailoverConfig(
            enabled=failover, promotion_time_seconds=promotion_time,
        ),
        autoscaling=AutoScalingConfig(enabled=autoscaling),
        region=RegionConfig(
            region=region,
            availability_zone=az,
            rpo_seconds=rpo_seconds,
            rto_seconds=rto_seconds,
        ),
        security=SecurityProfile(
            backup_enabled=backup_enabled,
            backup_frequency_hours=backup_freq,
            encryption_at_rest=encryption_at_rest,
            network_segmented=network_segmented,
        ),
        operational_profile=OperationalProfile(mttr_minutes=mttr_minutes),
        cost_profile=CostProfile(hourly_infra_cost=hourly_cost),
        metrics=ResourceMetrics(disk_used_gb=disk_used_gb),
    )


def _build_graph(
    components: list[Component],
    deps: list[tuple[str, str]] | None = None,
    cb_edges: set[tuple[str, str]] | None = None,
) -> InfraGraph:
    g = InfraGraph()
    for c in components:
        g.add_component(c)
    cb_edges = cb_edges or set()
    for src, tgt in deps or []:
        cb = CircuitBreakerConfig(enabled=((src, tgt) in cb_edges))
        g.add_dependency(
            Dependency(source_id=src, target_id=tgt, circuit_breaker=cb)
        )
    return g


def _default_plan(**overrides) -> DRPlan:
    defaults = dict(
        strategy=DRStrategy.WARM_STANDBY,
        primary_region="us-east-1",
        dr_region="us-west-2",
        rpo_target_seconds=300,
        rto_target_seconds=600,
        data_replication="async",
        failover_automated=True,
        last_tested="2025-01-01",
        runbook_id="RB-001",
    )
    defaults.update(overrides)
    return DRPlan(**defaults)


def _basic_graph() -> InfraGraph:
    """Two-region graph with common components."""
    return _build_graph(
        [
            _make_component("lb", ComponentType.LOAD_BALANCER, region="us-east-1", failover=True),
            _make_component("web", ComponentType.WEB_SERVER, region="us-east-1", replicas=3),
            _make_component("api", ComponentType.APP_SERVER, region="us-east-1", failover=True),
            _make_component("db", ComponentType.DATABASE, region="us-east-1", failover=True, backup_enabled=True),
            _make_component("cache", ComponentType.CACHE, region="us-east-1"),
            _make_component("lb-dr", ComponentType.LOAD_BALANCER, region="us-west-2", failover=True),
            _make_component("web-dr", ComponentType.WEB_SERVER, region="us-west-2", replicas=2),
            _make_component("api-dr", ComponentType.APP_SERVER, region="us-west-2", failover=True),
            _make_component("db-dr", ComponentType.DATABASE, region="us-west-2", failover=True, backup_enabled=True),
        ],
        deps=[
            ("lb", "web"),
            ("web", "api"),
            ("api", "db"),
            ("api", "cache"),
        ],
        cb_edges={("api", "cache")},
    )


# ===========================================================================
# DisasterType enum
# ===========================================================================


class TestDisasterType:
    def test_all_values(self):
        expected = {
            "region_outage", "data_center_failure", "cloud_provider_outage",
            "ransomware", "natural_disaster", "power_outage",
            "network_backbone_failure", "dns_hijack",
        }
        assert {dt.value for dt in DisasterType} == expected

    def test_string_enum(self):
        assert DisasterType.REGION_OUTAGE == "region_outage"

    def test_iteration(self):
        assert len(list(DisasterType)) == 8


# ===========================================================================
# DRStrategy enum
# ===========================================================================


class TestDRStrategy:
    def test_all_values(self):
        expected = {
            "pilot_light", "warm_standby", "multi_site_active",
            "backup_restore", "cold_standby",
        }
        assert {s.value for s in DRStrategy} == expected

    def test_string_enum(self):
        assert DRStrategy.PILOT_LIGHT == "pilot_light"

    def test_iteration(self):
        assert len(list(DRStrategy)) == 5


# ===========================================================================
# DRPlan model
# ===========================================================================


class TestDRPlan:
    def test_creation(self):
        plan = _default_plan()
        assert plan.strategy == DRStrategy.WARM_STANDBY
        assert plan.primary_region == "us-east-1"
        assert plan.dr_region == "us-west-2"
        assert plan.rpo_target_seconds == 300
        assert plan.rto_target_seconds == 600

    def test_defaults(self):
        plan = DRPlan(
            strategy=DRStrategy.COLD_STANDBY,
            primary_region="eu-west-1",
            dr_region="eu-central-1",
            rpo_target_seconds=3600,
            rto_target_seconds=7200,
        )
        assert plan.data_replication == "async"
        assert plan.failover_automated is False
        assert plan.last_tested == ""
        assert plan.runbook_id == ""

    def test_all_strategies_accepted(self):
        for strategy in DRStrategy:
            plan = DRPlan(
                strategy=strategy,
                primary_region="a",
                dr_region="b",
                rpo_target_seconds=60,
                rto_target_seconds=120,
            )
            assert plan.strategy == strategy


# ===========================================================================
# DRSimulationResult model
# ===========================================================================


class TestDRSimulationResult:
    def test_creation(self):
        result = DRSimulationResult(
            disaster_type=DisasterType.REGION_OUTAGE,
            actual_rpo_seconds=120,
            actual_rto_seconds=300,
            rpo_met=True,
            rto_met=False,
            data_loss_estimate_gb=0.5,
            affected_services=["web", "api"],
            recovery_steps=["step1"],
            cost_estimate=1000.0,
            recommendations=["rec1"],
        )
        assert result.disaster_type == DisasterType.REGION_OUTAGE
        assert result.rpo_met is True
        assert result.rto_met is False
        assert len(result.affected_services) == 2

    def test_defaults(self):
        result = DRSimulationResult(
            disaster_type=DisasterType.DNS_HIJACK,
            actual_rpo_seconds=0,
            actual_rto_seconds=0,
            rpo_met=True,
            rto_met=True,
        )
        assert result.data_loss_estimate_gb == 0.0
        assert result.affected_services == []
        assert result.recovery_steps == []
        assert result.cost_estimate == 0.0
        assert result.recommendations == []


# ===========================================================================
# DRPlanValidation model
# ===========================================================================


class TestDRPlanValidation:
    def test_valid(self):
        v = DRPlanValidation(is_valid=True, coverage_percent=80.0)
        assert v.is_valid is True
        assert v.issues == []

    def test_invalid(self):
        v = DRPlanValidation(
            is_valid=False,
            issues=["Primary region not found"],
            unprotected_components=["web"],
        )
        assert v.is_valid is False
        assert len(v.issues) == 1
        assert "web" in v.unprotected_components


# ===========================================================================
# RPORTOEstimate model
# ===========================================================================


class TestRPORTOEstimate:
    def test_defaults(self):
        e = RPORTOEstimate()
        assert e.estimated_rpo_seconds == 0
        assert e.estimated_rto_seconds == 0
        assert e.bottleneck_component == ""

    def test_with_breakdown(self):
        e = RPORTOEstimate(
            estimated_rpo_seconds=60,
            estimated_rto_seconds=120,
            rpo_breakdown={"db": 60, "web": 10},
            rto_breakdown={"db": 120, "web": 30},
            bottleneck_component="db",
        )
        assert e.rpo_breakdown["db"] == 60
        assert e.bottleneck_component == "db"


# ===========================================================================
# DRGap model
# ===========================================================================


class TestDRGap:
    def test_creation(self):
        gap = DRGap(
            component_id="db",
            gap_type="no_backup",
            severity="critical",
            description="No backup configured",
            recommendation="Enable backups",
        )
        assert gap.severity == "critical"
        assert gap.component_id == "db"


# ===========================================================================
# StrategyComparison model
# ===========================================================================


class TestStrategyComparison:
    def test_creation(self):
        sc = StrategyComparison(
            strategy=DRStrategy.WARM_STANDBY,
            estimated_rpo_seconds=60,
            estimated_rto_seconds=120,
            estimated_monthly_cost=500.0,
            pros=["Low RTO"],
            cons=["Some data loss"],
            score=75.0,
        )
        assert sc.strategy == DRStrategy.WARM_STANDBY
        assert sc.score == 75.0
        assert len(sc.pros) == 1


# ===========================================================================
# DRCostEstimate model
# ===========================================================================


class TestDRCostEstimate:
    def test_defaults(self):
        ce = DRCostEstimate()
        assert ce.total_monthly_cost == 0.0
        assert ce.cost_per_component == {}

    def test_with_values(self):
        ce = DRCostEstimate(
            monthly_infrastructure_cost=1000.0,
            monthly_replication_cost=300.0,
            monthly_storage_cost=50.0,
            annual_testing_cost=1200.0,
            total_monthly_cost=1450.0,
            cost_per_component={"db": 800.0, "web": 200.0},
        )
        assert ce.monthly_infrastructure_cost == 1000.0
        assert "db" in ce.cost_per_component


# ===========================================================================
# FailbackResult model
# ===========================================================================


class TestFailbackResult:
    def test_defaults(self):
        fb = FailbackResult()
        assert fb.estimated_failback_time_seconds == 0
        assert fb.can_failback_safely is True
        assert fb.steps == []
        assert fb.risks == []

    def test_with_values(self):
        fb = FailbackResult(
            estimated_failback_time_seconds=600,
            data_sync_required_gb=10.0,
            steps=["step1"],
            risks=["risk1"],
            can_failback_safely=False,
        )
        assert fb.estimated_failback_time_seconds == 600
        assert fb.can_failback_safely is False


# ===========================================================================
# Constants
# ===========================================================================


class TestConstants:
    def test_strategy_rto_multipliers_all_present(self):
        for s in DRStrategy:
            assert s in _STRATEGY_RTO_MULTIPLIER

    def test_strategy_rpo_multipliers_all_present(self):
        for s in DRStrategy:
            assert s in _STRATEGY_RPO_MULTIPLIER

    def test_strategy_cost_multipliers_all_present(self):
        for s in DRStrategy:
            assert s in _STRATEGY_COST_MULTIPLIER

    def test_disaster_severity_all_present(self):
        for dt in DisasterType:
            assert dt in _DISASTER_SEVERITY

    def test_multi_site_active_has_lowest_rto_multiplier(self):
        assert _STRATEGY_RTO_MULTIPLIER[DRStrategy.MULTI_SITE_ACTIVE] < _STRATEGY_RTO_MULTIPLIER[DRStrategy.BACKUP_RESTORE]

    def test_backup_restore_has_lowest_cost_multiplier(self):
        assert _STRATEGY_COST_MULTIPLIER[DRStrategy.BACKUP_RESTORE] < _STRATEGY_COST_MULTIPLIER[DRStrategy.MULTI_SITE_ACTIVE]


# ===========================================================================
# DisasterRecoveryEngine - initialization
# ===========================================================================


class TestEngineInit:
    def test_default_graph(self):
        engine = DisasterRecoveryEngine()
        assert len(engine.graph.components) == 0

    def test_with_graph(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine(graph)
        assert len(engine.graph.components) == 9


# ===========================================================================
# DisasterRecoveryEngine.simulate_disaster
# ===========================================================================


class TestSimulateDisaster:
    def test_region_outage(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine()
        plan = _default_plan()
        result = engine.simulate_disaster(graph, DisasterType.REGION_OUTAGE, plan)

        assert isinstance(result, DRSimulationResult)
        assert result.disaster_type == DisasterType.REGION_OUTAGE
        assert result.actual_rpo_seconds >= 0
        assert result.actual_rto_seconds >= 0
        assert isinstance(result.rpo_met, bool)
        assert isinstance(result.rto_met, bool)
        assert len(result.affected_services) > 0
        assert len(result.recovery_steps) > 0

    def test_data_center_failure(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine()
        plan = _default_plan()
        result = engine.simulate_disaster(graph, DisasterType.DATA_CENTER_FAILURE, plan)

        assert result.disaster_type == DisasterType.DATA_CENTER_FAILURE
        assert len(result.affected_services) > 0

    def test_ransomware_has_specific_steps(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine()
        plan = _default_plan()
        result = engine.simulate_disaster(graph, DisasterType.RANSOMWARE, plan)

        assert result.disaster_type == DisasterType.RANSOMWARE
        steps_text = " ".join(result.recovery_steps).lower()
        assert "isolate" in steps_text
        assert "ransomware" in steps_text

    def test_dns_hijack_has_specific_steps(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine()
        plan = _default_plan()
        result = engine.simulate_disaster(graph, DisasterType.DNS_HIJACK, plan)

        assert result.disaster_type == DisasterType.DNS_HIJACK
        steps_text = " ".join(result.recovery_steps).lower()
        assert "dns" in steps_text

    def test_rpo_met_with_generous_target(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine()
        plan = _default_plan(rpo_target_seconds=999999, rto_target_seconds=999999)
        result = engine.simulate_disaster(graph, DisasterType.REGION_OUTAGE, plan)

        assert result.rpo_met is True
        assert result.rto_met is True

    def test_rpo_not_met_with_tight_target(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine()
        plan = _default_plan(rpo_target_seconds=1, rto_target_seconds=1)
        result = engine.simulate_disaster(graph, DisasterType.REGION_OUTAGE, plan)

        assert result.rpo_met is False
        assert result.rto_met is False

    def test_recommendations_when_targets_not_met(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine()
        plan = _default_plan(
            rpo_target_seconds=1,
            rto_target_seconds=1,
            last_tested="",
            runbook_id="",
        )
        result = engine.simulate_disaster(graph, DisasterType.REGION_OUTAGE, plan)

        assert len(result.recommendations) > 0

    def test_cost_estimate_positive(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine()
        plan = _default_plan()
        result = engine.simulate_disaster(graph, DisasterType.REGION_OUTAGE, plan)

        assert result.cost_estimate >= 0

    def test_data_loss_estimate_non_negative(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine()
        plan = _default_plan()
        result = engine.simulate_disaster(graph, DisasterType.REGION_OUTAGE, plan)

        assert result.data_loss_estimate_gb >= 0

    def test_empty_graph(self):
        graph = InfraGraph()
        engine = DisasterRecoveryEngine()
        plan = _default_plan()
        result = engine.simulate_disaster(graph, DisasterType.REGION_OUTAGE, plan)

        assert result.actual_rpo_seconds == 0
        assert result.actual_rto_seconds == 0
        assert result.rpo_met is True
        assert result.rto_met is True
        assert result.affected_services == []

    def test_manual_failover_increases_rto(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine()
        plan_auto = _default_plan(failover_automated=True, rpo_target_seconds=999999, rto_target_seconds=999999)
        plan_manual = _default_plan(failover_automated=False, rpo_target_seconds=999999, rto_target_seconds=999999)

        result_auto = engine.simulate_disaster(graph, DisasterType.REGION_OUTAGE, plan_auto)
        result_manual = engine.simulate_disaster(graph, DisasterType.REGION_OUTAGE, plan_manual)

        assert result_manual.actual_rto_seconds > result_auto.actual_rto_seconds

    def test_sync_replication_reduces_rpo(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine()
        plan_async = _default_plan(data_replication="async", rpo_target_seconds=999999, rto_target_seconds=999999)
        plan_sync = _default_plan(data_replication="sync", rpo_target_seconds=999999, rto_target_seconds=999999)

        result_async = engine.simulate_disaster(graph, DisasterType.REGION_OUTAGE, plan_async)
        result_sync = engine.simulate_disaster(graph, DisasterType.REGION_OUTAGE, plan_sync)

        assert result_sync.actual_rpo_seconds < result_async.actual_rpo_seconds

    def test_multi_site_active_better_rto(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine()
        plan_multi = _default_plan(strategy=DRStrategy.MULTI_SITE_ACTIVE)
        plan_backup = _default_plan(strategy=DRStrategy.BACKUP_RESTORE)

        result_multi = engine.simulate_disaster(graph, DisasterType.REGION_OUTAGE, plan_multi)
        result_backup = engine.simulate_disaster(graph, DisasterType.REGION_OUTAGE, plan_backup)

        assert result_multi.actual_rto_seconds < result_backup.actual_rto_seconds

    def test_all_disaster_types(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine()
        plan = _default_plan()

        for dt in DisasterType:
            result = engine.simulate_disaster(graph, dt, plan)
            assert result.disaster_type == dt
            assert len(result.recovery_steps) > 0

    def test_all_strategies(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine()

        for strategy in DRStrategy:
            plan = _default_plan(strategy=strategy, rpo_target_seconds=999999, rto_target_seconds=999999)
            result = engine.simulate_disaster(graph, DisasterType.REGION_OUTAGE, plan)
            assert result.actual_rto_seconds >= 0

    def test_recovery_steps_include_monitoring(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine()
        plan = _default_plan()
        result = engine.simulate_disaster(graph, DisasterType.REGION_OUTAGE, plan)

        steps_text = " ".join(result.recovery_steps).lower()
        assert "monitor" in steps_text

    def test_recovery_steps_include_stakeholders(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine()
        plan = _default_plan()
        result = engine.simulate_disaster(graph, DisasterType.REGION_OUTAGE, plan)

        steps_text = " ".join(result.recovery_steps).lower()
        assert "stakeholder" in steps_text

    def test_cloud_provider_outage_recommendation(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine()
        plan = _default_plan(rpo_target_seconds=1, rto_target_seconds=1)
        result = engine.simulate_disaster(graph, DisasterType.CLOUD_PROVIDER_OUTAGE, plan)

        recs_text = " ".join(result.recommendations).lower()
        assert "multi-cloud" in recs_text

    def test_ransomware_recommendation(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine()
        plan = _default_plan()
        result = engine.simulate_disaster(graph, DisasterType.RANSOMWARE, plan)

        recs_text = " ".join(result.recommendations).lower()
        assert "immutable" in recs_text or "backup" in recs_text

    def test_untested_plan_recommendation(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine()
        plan = _default_plan(last_tested="")
        result = engine.simulate_disaster(graph, DisasterType.REGION_OUTAGE, plan)

        recs_text = " ".join(result.recommendations).lower()
        assert "test" in recs_text

    def test_no_runbook_recommendation(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine()
        plan = _default_plan(runbook_id="")
        result = engine.simulate_disaster(graph, DisasterType.REGION_OUTAGE, plan)

        recs_text = " ".join(result.recommendations).lower()
        assert "runbook" in recs_text

    def test_automated_failover_step(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine()
        plan = _default_plan(failover_automated=True)
        result = engine.simulate_disaster(graph, DisasterType.REGION_OUTAGE, plan)

        steps_text = " ".join(result.recovery_steps).lower()
        assert "automat" in steps_text

    def test_manual_failover_step(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine()
        plan = _default_plan(failover_automated=False)
        result = engine.simulate_disaster(graph, DisasterType.REGION_OUTAGE, plan)

        steps_text = " ".join(result.recovery_steps).lower()
        assert "manual" in steps_text

    def test_backup_restore_strategy_recommendation_when_rto_not_met(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine()
        plan = _default_plan(
            strategy=DRStrategy.BACKUP_RESTORE,
            rto_target_seconds=1,
            failover_automated=False,
        )
        result = engine.simulate_disaster(graph, DisasterType.REGION_OUTAGE, plan)

        recs_text = " ".join(result.recommendations).lower()
        assert "warm standby" in recs_text or "multi-site" in recs_text


# ===========================================================================
# DisasterRecoveryEngine.validate_dr_plan
# ===========================================================================


class TestValidateDRPlan:
    def test_valid_plan(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine()
        plan = _default_plan()
        result = engine.validate_dr_plan(graph, plan)

        assert isinstance(result, DRPlanValidation)
        assert result.is_valid is True
        assert len(result.issues) == 0

    def test_primary_region_not_found(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine()
        plan = _default_plan(primary_region="nonexistent")
        result = engine.validate_dr_plan(graph, plan)

        assert result.is_valid is False
        assert any("nonexistent" in i for i in result.issues)

    def test_dr_region_not_found(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine()
        plan = _default_plan(dr_region="nonexistent")
        result = engine.validate_dr_plan(graph, plan)

        assert result.is_valid is False
        assert any("nonexistent" in i for i in result.issues)

    def test_same_primary_and_dr_region(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine()
        plan = _default_plan(primary_region="us-east-1", dr_region="us-east-1")
        result = engine.validate_dr_plan(graph, plan)

        assert result.is_valid is False
        assert any("same" in i.lower() for i in result.issues)

    def test_unprotected_components_detected(self):
        graph = _build_graph([
            _make_component("web", ComponentType.WEB_SERVER, region="us-east-1", failover=False),
            _make_component("db", ComponentType.DATABASE, region="us-east-1", failover=True),
            _make_component("web-dr", ComponentType.WEB_SERVER, region="us-west-2"),
        ])
        engine = DisasterRecoveryEngine()
        plan = _default_plan()
        result = engine.validate_dr_plan(graph, plan)

        assert "web" in result.unprotected_components

    def test_coverage_percent(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine()
        plan = _default_plan()
        result = engine.validate_dr_plan(graph, plan)

        assert 0.0 <= result.coverage_percent <= 100.0

    def test_multi_site_active_no_dr_components(self):
        graph = _build_graph([
            _make_component("web", ComponentType.WEB_SERVER, region="us-east-1"),
        ])
        engine = DisasterRecoveryEngine()
        plan = _default_plan(strategy=DRStrategy.MULTI_SITE_ACTIVE)
        result = engine.validate_dr_plan(graph, plan)

        assert result.is_valid is False
        assert any("multi-site" in i.lower() for i in result.issues)

    def test_backup_restore_no_backups(self):
        graph = _build_graph([
            _make_component("web", ComponentType.WEB_SERVER, region="us-east-1"),
            _make_component("web-dr", ComponentType.WEB_SERVER, region="us-west-2"),
        ])
        engine = DisasterRecoveryEngine()
        plan = _default_plan(strategy=DRStrategy.BACKUP_RESTORE)
        result = engine.validate_dr_plan(graph, plan)

        assert result.is_valid is False
        assert any("backup" in i.lower() for i in result.issues)

    def test_warning_tight_rpo_with_async(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine()
        plan = _default_plan(rpo_target_seconds=10, data_replication="async")
        result = engine.validate_dr_plan(graph, plan)

        assert any("async" in w.lower() for w in result.warnings)

    def test_warning_untested_plan(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine()
        plan = _default_plan(last_tested="")
        result = engine.validate_dr_plan(graph, plan)

        assert any("tested" in w.lower() for w in result.warnings)

    def test_warning_no_runbook(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine()
        plan = _default_plan(runbook_id="")
        result = engine.validate_dr_plan(graph, plan)

        assert any("runbook" in w.lower() for w in result.warnings)

    def test_warning_manual_failover(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine()
        plan = _default_plan(failover_automated=False)
        result = engine.validate_dr_plan(graph, plan)

        assert any("manual" in w.lower() for w in result.warnings)

    def test_empty_graph(self):
        graph = InfraGraph()
        engine = DisasterRecoveryEngine()
        plan = _default_plan()
        result = engine.validate_dr_plan(graph, plan)

        assert result.coverage_percent == 0.0


# ===========================================================================
# DisasterRecoveryEngine.estimate_rpo_rto
# ===========================================================================


class TestEstimateRPORTO:
    def test_basic_estimate(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine()
        plan = _default_plan()
        result = engine.estimate_rpo_rto(graph, plan)

        assert isinstance(result, RPORTOEstimate)
        assert result.estimated_rpo_seconds > 0
        assert result.estimated_rto_seconds > 0

    def test_breakdown_per_component(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine()
        plan = _default_plan()
        result = engine.estimate_rpo_rto(graph, plan)

        assert len(result.rpo_breakdown) == len(graph.components)
        assert len(result.rto_breakdown) == len(graph.components)

    def test_bottleneck_identified(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine()
        plan = _default_plan()
        result = engine.estimate_rpo_rto(graph, plan)

        assert result.bottleneck_component != ""
        assert result.bottleneck_component in graph.components

    def test_empty_graph(self):
        graph = InfraGraph()
        engine = DisasterRecoveryEngine()
        plan = _default_plan()
        result = engine.estimate_rpo_rto(graph, plan)

        assert result.estimated_rpo_seconds == 0
        assert result.estimated_rto_seconds == 0
        assert result.bottleneck_component == ""

    def test_sync_replication_lowers_rpo(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine()
        plan_async = _default_plan(data_replication="async")
        plan_sync = _default_plan(data_replication="sync")

        est_async = engine.estimate_rpo_rto(graph, plan_async)
        est_sync = engine.estimate_rpo_rto(graph, plan_sync)

        assert est_sync.estimated_rpo_seconds < est_async.estimated_rpo_seconds

    def test_manual_failover_increases_rto(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine()
        plan_auto = _default_plan(failover_automated=True)
        plan_manual = _default_plan(failover_automated=False)

        est_auto = engine.estimate_rpo_rto(graph, plan_auto)
        est_manual = engine.estimate_rpo_rto(graph, plan_manual)

        assert est_manual.estimated_rto_seconds > est_auto.estimated_rto_seconds

    def test_all_strategies_produce_different_estimates(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine()

        rtos: set[int] = set()
        for strategy in DRStrategy:
            plan = _default_plan(strategy=strategy)
            est = engine.estimate_rpo_rto(graph, plan)
            rtos.add(est.estimated_rto_seconds)

        # At least 3 different RTO values for 5 strategies
        assert len(rtos) >= 3

    def test_component_with_failover_has_lower_rto(self):
        comp_fo = _make_component("with_fo", failover=True, promotion_time=15.0, region="us-east-1")
        comp_no = _make_component("no_fo", failover=False, mttr_minutes=60.0, region="us-east-1")
        graph = _build_graph([comp_fo, comp_no])
        engine = DisasterRecoveryEngine()
        plan = _default_plan()
        result = engine.estimate_rpo_rto(graph, plan)

        assert result.rto_breakdown["with_fo"] < result.rto_breakdown["no_fo"]

    def test_component_with_explicit_rpo(self):
        comp = _make_component("db", ComponentType.DATABASE, region="us-east-1", rpo_seconds=120)
        graph = _build_graph([comp])
        engine = DisasterRecoveryEngine()
        plan = _default_plan()
        result = engine.estimate_rpo_rto(graph, plan)

        assert result.rpo_breakdown["db"] > 0

    def test_component_with_backup_rpo(self):
        comp = _make_component("db", ComponentType.DATABASE, region="us-east-1", backup_enabled=True, backup_freq=1.0)
        graph = _build_graph([comp])
        engine = DisasterRecoveryEngine()
        plan = _default_plan()
        result = engine.estimate_rpo_rto(graph, plan)

        assert result.rpo_breakdown["db"] > 0


# ===========================================================================
# DisasterRecoveryEngine.find_dr_gaps
# ===========================================================================


class TestFindDRGaps:
    def test_finds_gaps(self):
        graph = _build_graph([
            _make_component("web", ComponentType.WEB_SERVER, region="us-east-1"),
            _make_component("db", ComponentType.DATABASE, region="us-east-1"),
        ])
        engine = DisasterRecoveryEngine()
        plan = _default_plan()
        gaps = engine.find_dr_gaps(graph, plan)

        assert isinstance(gaps, list)
        assert len(gaps) > 0
        assert all(isinstance(g, DRGap) for g in gaps)

    def test_no_failover_gap(self):
        graph = _build_graph([
            _make_component("web", ComponentType.WEB_SERVER, region="us-east-1", failover=False),
        ])
        engine = DisasterRecoveryEngine()
        plan = _default_plan()
        gaps = engine.find_dr_gaps(graph, plan)

        gap_types = [g.gap_type for g in gaps]
        assert "no_failover" in gap_types

    def test_no_backup_gap_for_database(self):
        graph = _build_graph([
            _make_component("db", ComponentType.DATABASE, region="us-east-1", backup_enabled=False),
        ])
        engine = DisasterRecoveryEngine()
        plan = _default_plan()
        gaps = engine.find_dr_gaps(graph, plan)

        backup_gaps = [g for g in gaps if g.gap_type == "no_backup"]
        assert len(backup_gaps) >= 1
        assert backup_gaps[0].severity == "critical"

    def test_no_encryption_gap(self):
        graph = _build_graph([
            _make_component("web", ComponentType.WEB_SERVER, region="us-east-1", encryption_at_rest=False),
        ])
        engine = DisasterRecoveryEngine()
        plan = _default_plan()
        gaps = engine.find_dr_gaps(graph, plan)

        enc_gaps = [g for g in gaps if g.gap_type == "no_encryption"]
        assert len(enc_gaps) >= 1

    def test_single_replica_gap(self):
        graph = _build_graph([
            _make_component("web", ComponentType.WEB_SERVER, region="us-east-1", replicas=1, autoscaling=False),
        ])
        engine = DisasterRecoveryEngine()
        plan = _default_plan()
        gaps = engine.find_dr_gaps(graph, plan)

        single_gaps = [g for g in gaps if g.gap_type == "single_replica"]
        assert len(single_gaps) >= 1

    def test_no_single_replica_gap_with_autoscaling(self):
        graph = _build_graph([
            _make_component("web", ComponentType.WEB_SERVER, region="us-east-1", replicas=1, autoscaling=True, failover=True, encryption_at_rest=True),
        ])
        engine = DisasterRecoveryEngine()
        plan = _default_plan()
        gaps = engine.find_dr_gaps(graph, plan)

        single_gaps = [g for g in gaps if g.gap_type == "single_replica"]
        assert len(single_gaps) == 0

    def test_no_dr_counterpart_gap(self):
        graph = _build_graph([
            _make_component("web", ComponentType.WEB_SERVER, region="us-east-1"),
        ])
        engine = DisasterRecoveryEngine()
        plan = _default_plan()
        gaps = engine.find_dr_gaps(graph, plan)

        dr_gaps = [g for g in gaps if g.gap_type == "no_dr_counterpart"]
        assert len(dr_gaps) >= 1
        assert dr_gaps[0].severity == "critical"

    def test_no_circuit_breaker_gap(self):
        graph = _build_graph(
            [
                _make_component("web", ComponentType.WEB_SERVER, region="us-east-1"),
                _make_component("db", ComponentType.DATABASE, region="us-east-1"),
            ],
            deps=[("web", "db")],
            cb_edges=set(),
        )
        engine = DisasterRecoveryEngine()
        plan = _default_plan()
        gaps = engine.find_dr_gaps(graph, plan)

        cb_gaps = [g for g in gaps if g.gap_type == "no_circuit_breaker"]
        assert len(cb_gaps) >= 1

    def test_no_circuit_breaker_gap_when_enabled(self):
        graph = _build_graph(
            [
                _make_component("web", ComponentType.WEB_SERVER, region="us-east-1"),
                _make_component("db", ComponentType.DATABASE, region="us-east-1"),
            ],
            deps=[("web", "db")],
            cb_edges={("web", "db")},
        )
        engine = DisasterRecoveryEngine()
        plan = _default_plan()
        gaps = engine.find_dr_gaps(graph, plan)

        cb_gaps = [g for g in gaps if g.gap_type == "no_circuit_breaker"]
        assert len(cb_gaps) == 0

    def test_gaps_sorted_by_severity(self):
        graph = _build_graph([
            _make_component("web", ComponentType.WEB_SERVER, region="us-east-1"),
            _make_component("db", ComponentType.DATABASE, region="us-east-1", backup_enabled=False),
        ])
        engine = DisasterRecoveryEngine()
        plan = _default_plan()
        gaps = engine.find_dr_gaps(graph, plan)

        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        for i in range(len(gaps) - 1):
            assert severity_order[gaps[i].severity] <= severity_order[gaps[i + 1].severity]

    def test_well_protected_graph_has_fewer_gaps(self):
        protected = _build_graph([
            _make_component("web", ComponentType.WEB_SERVER, region="us-east-1", failover=True, replicas=3, encryption_at_rest=True),
            _make_component("db", ComponentType.DATABASE, region="us-east-1", failover=True, backup_enabled=True, encryption_at_rest=True, replicas=2),
            _make_component("web-dr", ComponentType.WEB_SERVER, region="us-west-2", failover=True, replicas=2, encryption_at_rest=True),
            _make_component("db-dr", ComponentType.DATABASE, region="us-west-2", failover=True, backup_enabled=True, encryption_at_rest=True, replicas=2),
        ])
        unprotected = _build_graph([
            _make_component("web", ComponentType.WEB_SERVER, region="us-east-1"),
            _make_component("db", ComponentType.DATABASE, region="us-east-1"),
        ])
        engine = DisasterRecoveryEngine()
        plan = _default_plan()

        gaps_protected = engine.find_dr_gaps(protected, plan)
        gaps_unprotected = engine.find_dr_gaps(unprotected, plan)

        assert len(gaps_protected) < len(gaps_unprotected)

    def test_database_encryption_gap_is_high(self):
        graph = _build_graph([
            _make_component("db", ComponentType.DATABASE, region="us-east-1", encryption_at_rest=False, failover=True, backup_enabled=True),
        ])
        engine = DisasterRecoveryEngine()
        plan = _default_plan()
        gaps = engine.find_dr_gaps(graph, plan)

        enc_gaps = [g for g in gaps if g.gap_type == "no_encryption" and g.component_id == "db"]
        assert len(enc_gaps) >= 1
        assert enc_gaps[0].severity == "high"

    def test_app_server_encryption_gap_is_medium(self):
        graph = _build_graph([
            _make_component("api", ComponentType.APP_SERVER, region="us-east-1", encryption_at_rest=False, failover=True, replicas=2),
        ])
        engine = DisasterRecoveryEngine()
        plan = _default_plan()
        gaps = engine.find_dr_gaps(graph, plan)

        enc_gaps = [g for g in gaps if g.gap_type == "no_encryption" and g.component_id == "api"]
        assert len(enc_gaps) >= 1
        assert enc_gaps[0].severity == "medium"

    def test_empty_graph_no_gaps(self):
        graph = InfraGraph()
        engine = DisasterRecoveryEngine()
        plan = _default_plan()
        gaps = engine.find_dr_gaps(graph, plan)

        assert gaps == []

    def test_storage_no_backup_is_critical(self):
        graph = _build_graph([
            _make_component("s3", ComponentType.STORAGE, region="us-east-1", backup_enabled=False),
        ])
        engine = DisasterRecoveryEngine()
        plan = _default_plan()
        gaps = engine.find_dr_gaps(graph, plan)

        backup_gaps = [g for g in gaps if g.gap_type == "no_backup"]
        assert len(backup_gaps) >= 1
        assert backup_gaps[0].severity == "critical"

    def test_cache_no_backup_is_critical(self):
        graph = _build_graph([
            _make_component("redis", ComponentType.CACHE, region="us-east-1", backup_enabled=False),
        ])
        engine = DisasterRecoveryEngine()
        plan = _default_plan()
        gaps = engine.find_dr_gaps(graph, plan)

        backup_gaps = [g for g in gaps if g.gap_type == "no_backup"]
        assert len(backup_gaps) >= 1


# ===========================================================================
# DisasterRecoveryEngine.compare_strategies
# ===========================================================================


class TestCompareStrategies:
    def test_returns_all_strategies(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine()
        results = engine.compare_strategies(graph)

        assert isinstance(results, list)
        assert len(results) == len(DRStrategy)
        strategies = {r.strategy for r in results}
        assert strategies == set(DRStrategy)

    def test_sorted_by_score_descending(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine()
        results = engine.compare_strategies(graph)

        for i in range(len(results) - 1):
            assert results[i].score >= results[i + 1].score

    def test_each_has_pros_and_cons(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine()
        results = engine.compare_strategies(graph)

        for r in results:
            assert len(r.pros) > 0
            assert len(r.cons) > 0

    def test_multi_site_has_lowest_rto(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine()
        results = engine.compare_strategies(graph)

        by_strategy = {r.strategy: r for r in results}
        assert by_strategy[DRStrategy.MULTI_SITE_ACTIVE].estimated_rto_seconds <= by_strategy[DRStrategy.BACKUP_RESTORE].estimated_rto_seconds

    def test_backup_restore_cheapest(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine()
        results = engine.compare_strategies(graph)

        by_strategy = {r.strategy: r for r in results}
        assert by_strategy[DRStrategy.BACKUP_RESTORE].estimated_monthly_cost < by_strategy[DRStrategy.MULTI_SITE_ACTIVE].estimated_monthly_cost

    def test_empty_graph(self):
        graph = InfraGraph()
        engine = DisasterRecoveryEngine()
        results = engine.compare_strategies(graph)

        assert len(results) == len(DRStrategy)
        for r in results:
            assert r.estimated_rpo_seconds == 0
            assert r.estimated_rto_seconds == 0
            assert r.estimated_monthly_cost == 0.0

    def test_cost_scales_with_components(self):
        small_graph = _build_graph([
            _make_component("web", ComponentType.WEB_SERVER, region="us-east-1"),
        ])
        large_graph = _build_graph([
            _make_component(f"web{i}", ComponentType.WEB_SERVER, region="us-east-1")
            for i in range(10)
        ])
        engine = DisasterRecoveryEngine()

        small_results = engine.compare_strategies(small_graph)
        large_results = engine.compare_strategies(large_graph)

        small_by_strat = {r.strategy: r for r in small_results}
        large_by_strat = {r.strategy: r for r in large_results}

        for s in DRStrategy:
            assert large_by_strat[s].estimated_monthly_cost > small_by_strat[s].estimated_monthly_cost

    def test_scores_non_negative(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine()
        results = engine.compare_strategies(graph)

        for r in results:
            assert r.score >= 0


# ===========================================================================
# DisasterRecoveryEngine.calculate_dr_cost
# ===========================================================================


class TestCalculateDRCost:
    def test_basic_cost(self):
        graph = _build_graph([
            _make_component("web", ComponentType.WEB_SERVER, region="us-east-1", hourly_cost=1.0),
            _make_component("db", ComponentType.DATABASE, region="us-east-1", hourly_cost=2.0),
        ])
        engine = DisasterRecoveryEngine()
        plan = _default_plan()
        cost = engine.calculate_dr_cost(graph, plan)

        assert isinstance(cost, DRCostEstimate)
        assert cost.monthly_infrastructure_cost > 0
        assert cost.total_monthly_cost > 0

    def test_per_component_costs(self):
        graph = _build_graph([
            _make_component("web", ComponentType.WEB_SERVER, region="us-east-1", hourly_cost=1.0),
            _make_component("db", ComponentType.DATABASE, region="us-east-1", hourly_cost=2.0),
        ])
        engine = DisasterRecoveryEngine()
        plan = _default_plan()
        cost = engine.calculate_dr_cost(graph, plan)

        assert "web" in cost.cost_per_component
        assert "db" in cost.cost_per_component

    def test_database_has_replication_cost(self):
        graph = _build_graph([
            _make_component("db", ComponentType.DATABASE, region="us-east-1", hourly_cost=2.0),
        ])
        engine = DisasterRecoveryEngine()
        plan = _default_plan()
        cost = engine.calculate_dr_cost(graph, plan)

        assert cost.monthly_replication_cost > 0

    def test_sync_replication_more_expensive(self):
        graph = _build_graph([
            _make_component("db", ComponentType.DATABASE, region="us-east-1", hourly_cost=2.0),
        ])
        engine = DisasterRecoveryEngine()
        plan_async = _default_plan(data_replication="async")
        plan_sync = _default_plan(data_replication="sync")

        cost_async = engine.calculate_dr_cost(graph, plan_async)
        cost_sync = engine.calculate_dr_cost(graph, plan_sync)

        assert cost_sync.monthly_replication_cost > cost_async.monthly_replication_cost

    def test_storage_cost_with_disk(self):
        graph = _build_graph([
            _make_component("web", ComponentType.WEB_SERVER, region="us-east-1", disk_used_gb=100.0),
        ])
        engine = DisasterRecoveryEngine()
        plan = _default_plan()
        cost = engine.calculate_dr_cost(graph, plan)

        assert cost.monthly_storage_cost > 0

    def test_storage_cost_zero_without_disk(self):
        graph = _build_graph([
            _make_component("web", ComponentType.WEB_SERVER, region="us-east-1", disk_used_gb=0.0),
        ])
        engine = DisasterRecoveryEngine()
        plan = _default_plan()
        cost = engine.calculate_dr_cost(graph, plan)

        assert cost.monthly_storage_cost == 0.0

    def test_annual_testing_cost(self):
        graph = _build_graph([
            _make_component("web", ComponentType.WEB_SERVER, region="us-east-1"),
        ])
        engine = DisasterRecoveryEngine()
        plan = _default_plan()
        cost = engine.calculate_dr_cost(graph, plan)

        assert cost.annual_testing_cost > 0

    def test_multi_site_active_most_expensive(self):
        graph = _build_graph([
            _make_component("web", ComponentType.WEB_SERVER, region="us-east-1", hourly_cost=1.0),
        ])
        engine = DisasterRecoveryEngine()
        plan_multi = _default_plan(strategy=DRStrategy.MULTI_SITE_ACTIVE)
        plan_backup = _default_plan(strategy=DRStrategy.BACKUP_RESTORE)

        cost_multi = engine.calculate_dr_cost(graph, plan_multi)
        cost_backup = engine.calculate_dr_cost(graph, plan_backup)

        assert cost_multi.monthly_infrastructure_cost > cost_backup.monthly_infrastructure_cost

    def test_empty_graph(self):
        graph = InfraGraph()
        engine = DisasterRecoveryEngine()
        plan = _default_plan()
        cost = engine.calculate_dr_cost(graph, plan)

        assert cost.monthly_infrastructure_cost == 0.0
        assert cost.monthly_replication_cost == 0.0
        assert cost.monthly_storage_cost == 0.0
        assert cost.cost_per_component == {}

    def test_zero_hourly_cost_components(self):
        graph = _build_graph([
            _make_component("web", ComponentType.WEB_SERVER, region="us-east-1", hourly_cost=0.0),
        ])
        engine = DisasterRecoveryEngine()
        plan = _default_plan()
        cost = engine.calculate_dr_cost(graph, plan)

        assert cost.monthly_infrastructure_cost == 0.0

    def test_cache_has_replication_cost(self):
        graph = _build_graph([
            _make_component("redis", ComponentType.CACHE, region="us-east-1", hourly_cost=1.0),
        ])
        engine = DisasterRecoveryEngine()
        plan = _default_plan()
        cost = engine.calculate_dr_cost(graph, plan)

        assert cost.monthly_replication_cost > 0

    def test_storage_type_has_replication_cost(self):
        graph = _build_graph([
            _make_component("s3", ComponentType.STORAGE, region="us-east-1", hourly_cost=0.5),
        ])
        engine = DisasterRecoveryEngine()
        plan = _default_plan()
        cost = engine.calculate_dr_cost(graph, plan)

        assert cost.monthly_replication_cost > 0


# ===========================================================================
# DisasterRecoveryEngine.simulate_failback
# ===========================================================================


class TestSimulateFailback:
    def test_basic_failback(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine()
        plan = _default_plan()
        result = engine.simulate_failback(graph, plan)

        assert isinstance(result, FailbackResult)
        assert result.estimated_failback_time_seconds > 0
        assert len(result.steps) > 0
        assert len(result.risks) > 0

    def test_failback_steps_content(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine()
        plan = _default_plan()
        result = engine.simulate_failback(graph, plan)

        steps_text = " ".join(result.steps).lower()
        assert "primary" in steps_text
        assert "traffic" in steps_text or "dns" in steps_text

    def test_failback_has_data_sync(self):
        graph = _build_graph([
            _make_component("db", ComponentType.DATABASE, region="us-east-1", disk_used_gb=100.0),
            _make_component("db-dr", ComponentType.DATABASE, region="us-west-2", disk_used_gb=100.0),
        ])
        engine = DisasterRecoveryEngine()
        plan = _default_plan()
        result = engine.simulate_failback(graph, plan)

        assert result.data_sync_required_gb > 0

    def test_failback_no_data_stores(self):
        graph = _build_graph([
            _make_component("web", ComponentType.WEB_SERVER, region="us-east-1"),
            _make_component("web-dr", ComponentType.WEB_SERVER, region="us-west-2"),
        ])
        engine = DisasterRecoveryEngine()
        plan = _default_plan()
        result = engine.simulate_failback(graph, plan)

        assert result.data_sync_required_gb == 0.0

    def test_failback_backup_restore_has_risk(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine()
        plan = _default_plan(strategy=DRStrategy.BACKUP_RESTORE)
        result = engine.simulate_failback(graph, plan)

        risks_text = " ".join(result.risks).lower()
        assert "data loss" in risks_text or "backup" in risks_text

    def test_failback_no_dr_components_unsafe(self):
        graph = _build_graph([
            _make_component("web", ComponentType.WEB_SERVER, region="us-east-1"),
        ])
        engine = DisasterRecoveryEngine()
        plan = _default_plan()
        result = engine.simulate_failback(graph, plan)

        assert result.can_failback_safely is False

    def test_failback_with_dr_components_safe(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine()
        plan = _default_plan()
        result = engine.simulate_failback(graph, plan)

        assert result.can_failback_safely is True

    def test_failback_manual_increases_time(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine()
        plan_auto = _default_plan(failover_automated=True)
        plan_manual = _default_plan(failover_automated=False)

        result_auto = engine.simulate_failback(graph, plan_auto)
        result_manual = engine.simulate_failback(graph, plan_manual)

        assert result_manual.estimated_failback_time_seconds >= result_auto.estimated_failback_time_seconds

    def test_failback_manual_has_risk(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine()
        plan = _default_plan(failover_automated=False)
        result = engine.simulate_failback(graph, plan)

        risks_text = " ".join(result.risks).lower()
        assert "manual" in risks_text

    def test_failback_empty_graph(self):
        graph = InfraGraph()
        engine = DisasterRecoveryEngine()
        plan = _default_plan()
        result = engine.simulate_failback(graph, plan)

        assert result.estimated_failback_time_seconds == 0
        assert result.data_sync_required_gb == 0.0

    def test_failback_multi_site_active_faster(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine()
        plan_multi = _default_plan(strategy=DRStrategy.MULTI_SITE_ACTIVE)
        plan_cold = _default_plan(strategy=DRStrategy.COLD_STANDBY)

        result_multi = engine.simulate_failback(graph, plan_multi)
        result_cold = engine.simulate_failback(graph, plan_cold)

        assert result_multi.estimated_failback_time_seconds < result_cold.estimated_failback_time_seconds


# ===========================================================================
# Internal helpers
# ===========================================================================


class TestInternalHelpers:
    def test_components_in_region(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine(graph)

        us_east = engine._components_in_region("us-east-1")
        us_west = engine._components_in_region("us-west-2")

        assert len(us_east) == 5
        assert len(us_west) == 4

    def test_components_in_nonexistent_region(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine(graph)

        result = engine._components_in_region("ap-southeast-1")
        assert result == []

    def test_all_regions(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine(graph)

        regions = engine._all_regions()
        assert regions == {"us-east-1", "us-west-2"}

    def test_all_regions_empty_graph(self):
        engine = DisasterRecoveryEngine(InfraGraph())
        assert engine._all_regions() == set()

    def test_component_base_rto_with_failover(self):
        comp = _make_component("web", failover=True, promotion_time=15.0)
        engine = DisasterRecoveryEngine()
        assert engine._component_base_rto(comp) == 15.0

    def test_component_base_rto_without_failover(self):
        comp = _make_component("web", failover=False, mttr_minutes=10.0)
        engine = DisasterRecoveryEngine()
        assert engine._component_base_rto(comp) == 600.0  # 10 min * 60

    def test_component_base_rto_default(self):
        comp = _make_component("web", failover=False, mttr_minutes=0.0)
        engine = DisasterRecoveryEngine()
        assert engine._component_base_rto(comp) == 300.0

    def test_component_base_rpo_explicit(self):
        comp = _make_component("db", rpo_seconds=120)
        engine = DisasterRecoveryEngine()
        assert engine._component_base_rpo(comp) == 120.0

    def test_component_base_rpo_with_failover(self):
        comp = _make_component("db", failover=True, rpo_seconds=0)
        engine = DisasterRecoveryEngine()
        assert engine._component_base_rpo(comp) == 5.0

    def test_component_base_rpo_with_backup(self):
        comp = _make_component("db", backup_enabled=True, backup_freq=6.0, rpo_seconds=0)
        engine = DisasterRecoveryEngine()
        assert engine._component_base_rpo(comp) == 6.0 * 3600.0

    def test_component_base_rpo_default(self):
        comp = _make_component("web", rpo_seconds=0, failover=False, backup_enabled=False)
        engine = DisasterRecoveryEngine()
        assert engine._component_base_rpo(comp) == 3600.0

    def test_affected_services_high_severity(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine(graph)
        plan = _default_plan()

        affected = engine._affected_services_for_disaster(DisasterType.REGION_OUTAGE, plan)
        primary_comps = engine._components_in_region("us-east-1")
        assert set(affected) == set(primary_comps)

    def test_affected_services_low_severity(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine(graph)
        plan = _default_plan()

        affected = engine._affected_services_for_disaster(DisasterType.DNS_HIJACK, plan)
        primary_comps = engine._components_in_region("us-east-1")
        assert len(affected) <= len(primary_comps)
        assert len(affected) >= 1

    def test_recovery_steps_vary_by_strategy(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine(graph)
        plan_multi = _default_plan(strategy=DRStrategy.MULTI_SITE_ACTIVE)
        plan_backup = _default_plan(strategy=DRStrategy.BACKUP_RESTORE)

        steps_multi = engine._recovery_steps_for_disaster(DisasterType.REGION_OUTAGE, plan_multi)
        steps_backup = engine._recovery_steps_for_disaster(DisasterType.REGION_OUTAGE, plan_backup)

        assert steps_multi != steps_backup

    def test_recommendations_with_all_met(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine(graph)
        plan = _default_plan()

        recs = engine._recommendations_for_disaster(DisasterType.REGION_OUTAGE, plan, rpo_met=True, rto_met=True)
        # Should still have general recommendations if any defaults are empty
        assert isinstance(recs, list)

    def test_recommendations_rpo_not_met(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine(graph)
        plan = _default_plan()

        recs = engine._recommendations_for_disaster(DisasterType.REGION_OUTAGE, plan, rpo_met=False, rto_met=True)
        recs_text = " ".join(recs).lower()
        assert "replication" in recs_text

    def test_recommendations_rto_not_met_manual(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine(graph)
        plan = _default_plan(failover_automated=False)

        recs = engine._recommendations_for_disaster(DisasterType.REGION_OUTAGE, plan, rpo_met=True, rto_met=False)
        recs_text = " ".join(recs).lower()
        assert "automated" in recs_text or "failover" in recs_text


# ===========================================================================
# Integration / edge cases
# ===========================================================================


class TestIntegration:
    def test_full_workflow(self):
        """Run all engine methods on the same graph and plan."""
        graph = _basic_graph()
        engine = DisasterRecoveryEngine()
        plan = _default_plan()

        # Simulate
        sim_result = engine.simulate_disaster(graph, DisasterType.REGION_OUTAGE, plan)
        assert isinstance(sim_result, DRSimulationResult)

        # Validate
        val_result = engine.validate_dr_plan(graph, plan)
        assert isinstance(val_result, DRPlanValidation)

        # Estimate
        est_result = engine.estimate_rpo_rto(graph, plan)
        assert isinstance(est_result, RPORTOEstimate)

        # Find gaps
        gaps = engine.find_dr_gaps(graph, plan)
        assert isinstance(gaps, list)

        # Compare
        comparisons = engine.compare_strategies(graph)
        assert isinstance(comparisons, list)

        # Cost
        cost = engine.calculate_dr_cost(graph, plan)
        assert isinstance(cost, DRCostEstimate)

        # Failback
        failback = engine.simulate_failback(graph, plan)
        assert isinstance(failback, FailbackResult)

    def test_single_component_graph(self):
        graph = _build_graph([
            _make_component("lonely", ComponentType.APP_SERVER, region="us-east-1"),
        ])
        engine = DisasterRecoveryEngine()
        plan = _default_plan()

        sim = engine.simulate_disaster(graph, DisasterType.POWER_OUTAGE, plan)
        assert sim.actual_rto_seconds > 0

        val = engine.validate_dr_plan(graph, plan)
        assert isinstance(val, DRPlanValidation)

        est = engine.estimate_rpo_rto(graph, plan)
        assert est.estimated_rto_seconds > 0

        gaps = engine.find_dr_gaps(graph, plan)
        assert len(gaps) > 0

        comparisons = engine.compare_strategies(graph)
        assert len(comparisons) == 5

        cost = engine.calculate_dr_cost(graph, plan)
        assert isinstance(cost, DRCostEstimate)

        failback = engine.simulate_failback(graph, plan)
        assert isinstance(failback, FailbackResult)

    def test_large_graph(self):
        components = []
        for i in range(50):
            region = "us-east-1" if i < 25 else "us-west-2"
            ctype = ComponentType.APP_SERVER if i % 3 != 0 else ComponentType.DATABASE
            components.append(
                _make_component(
                    f"comp{i}", ctype, region=region,
                    failover=(i % 2 == 0),
                    backup_enabled=(ctype == ComponentType.DATABASE),
                    hourly_cost=float(i),
                )
            )
        graph = _build_graph(components)
        engine = DisasterRecoveryEngine()
        plan = _default_plan()

        sim = engine.simulate_disaster(graph, DisasterType.NATURAL_DISASTER, plan)
        assert len(sim.affected_services) > 0

        comparisons = engine.compare_strategies(graph)
        assert len(comparisons) == 5

        cost = engine.calculate_dr_cost(graph, plan)
        assert cost.total_monthly_cost > 0

    def test_graph_with_no_primary_region_components(self):
        graph = _build_graph([
            _make_component("web", ComponentType.WEB_SERVER, region="eu-west-1"),
        ])
        engine = DisasterRecoveryEngine()
        plan = _default_plan()

        sim = engine.simulate_disaster(graph, DisasterType.REGION_OUTAGE, plan)
        assert sim.affected_services == []

    def test_all_disaster_strategy_combinations(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine()

        for dt in DisasterType:
            for strategy in DRStrategy:
                plan = _default_plan(strategy=strategy, rpo_target_seconds=999999, rto_target_seconds=999999)
                result = engine.simulate_disaster(graph, dt, plan)
                assert result.disaster_type == dt
                assert result.actual_rto_seconds >= 0
                assert result.actual_rpo_seconds >= 0

    def test_network_backbone_failure(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine()
        plan = _default_plan()
        result = engine.simulate_disaster(graph, DisasterType.NETWORK_BACKBONE_FAILURE, plan)

        assert result.disaster_type == DisasterType.NETWORK_BACKBONE_FAILURE
        assert len(result.recovery_steps) > 0

    def test_power_outage(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine()
        plan = _default_plan()
        result = engine.simulate_disaster(graph, DisasterType.POWER_OUTAGE, plan)

        assert result.disaster_type == DisasterType.POWER_OUTAGE
        # Power outage has lower severity so may affect fewer services
        assert isinstance(result.affected_services, list)

    def test_natural_disaster(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine()
        plan = _default_plan()
        result = engine.simulate_disaster(graph, DisasterType.NATURAL_DISASTER, plan)

        assert result.disaster_type == DisasterType.NATURAL_DISASTER

    def test_dns_hijack_recommendation(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine()
        plan = _default_plan(rpo_target_seconds=1, rto_target_seconds=1)
        result = engine.simulate_disaster(graph, DisasterType.DNS_HIJACK, plan)

        recs_text = " ".join(result.recommendations).lower()
        assert "dnssec" in recs_text or "registry" in recs_text

    def test_cold_standby_strategy(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine()
        plan = _default_plan(strategy=DRStrategy.COLD_STANDBY)
        result = engine.simulate_disaster(graph, DisasterType.REGION_OUTAGE, plan)

        assert result.actual_rto_seconds > 0
        steps_text = " ".join(result.recovery_steps).lower()
        assert "provision" in steps_text

    def test_pilot_light_strategy(self):
        graph = _basic_graph()
        engine = DisasterRecoveryEngine()
        plan = _default_plan(strategy=DRStrategy.PILOT_LIGHT)
        result = engine.simulate_disaster(graph, DisasterType.REGION_OUTAGE, plan)

        assert result.actual_rto_seconds > 0
        steps_text = " ".join(result.recovery_steps).lower()
        assert "pilot" in steps_text or "scale" in steps_text
