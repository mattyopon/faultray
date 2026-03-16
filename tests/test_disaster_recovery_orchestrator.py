"""Tests for the Disaster Recovery Orchestrator."""

from __future__ import annotations

import math

import pytest

from faultray.model.components import (
    Component,
    ComponentType,
    CostProfile,
    Dependency,
    FailoverConfig,
    OperationalProfile,
    RegionConfig,
    SecurityProfile,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.disaster_recovery_orchestrator import (
    AutomationGap,
    AutomationGapReport,
    AutomationLevel,
    CheckpointStatus,
    CheckpointValidationResult,
    CommunicationPlanResult,
    CriticalPathResult,
    CrossRegionFailoverPlan,
    DROrchestrator,
    DRTestCoverageReport,
    DataConsistencyCheck,
    DataConsistencyReport,
    DrillEvent,
    DrillOutcome,
    DrillSimulationResult,
    FailoverCoordinationPlan,
    HealthCheckEntry,
    HealthCheckResult,
    NotificationChannel,
    NotificationEntry,
    PostRecoveryHealthPlan,
    PriorityTier,
    RecoveryCheckpoint,
    RecoveryPhase,
    RecoveryPriorityEntry,
    RecoveryPriorityPlan,
    RecoveryStep,
    RegionRole,
    RegionState,
    StepDependencyGraph,
    StepExecutionMode,
    StepStatus,
    TestCoverageEntry,
)


# ---------------------------------------------------------------------------
# Helpers (per specification)
# ---------------------------------------------------------------------------


def _comp(cid: str = "c1", ctype: ComponentType = ComponentType.APP_SERVER) -> Component:
    return Component(id=cid, name=cid, type=ctype)


def _graph(*comps: Component) -> InfraGraph:
    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    return g


def _db_comp(
    cid: str = "db1",
    *,
    failover: bool = False,
    backup: bool = False,
    backup_freq: float = 24.0,
    rpo_seconds: int = 0,
    rto_seconds: int = 0,
    hourly_cost: float = 1.0,
    replicas: int = 1,
    region: str = "",
    dr_target: str = "",
    revenue_per_minute: float = 0.0,
) -> Component:
    return Component(
        id=cid,
        name=cid,
        type=ComponentType.DATABASE,
        replicas=replicas,
        failover=FailoverConfig(enabled=failover, promotion_time_seconds=30.0),
        security=SecurityProfile(
            backup_enabled=backup,
            backup_frequency_hours=backup_freq,
        ),
        region=RegionConfig(
            region=region,
            rpo_seconds=rpo_seconds,
            rto_seconds=rto_seconds,
            dr_target_region=dr_target,
        ),
        cost_profile=CostProfile(
            hourly_infra_cost=hourly_cost,
            revenue_per_minute=revenue_per_minute,
        ),
    )


def _app_comp(
    cid: str = "app1",
    *,
    failover: bool = False,
    region: str = "",
    dr_target: str = "",
    hourly_cost: float = 0.5,
    rto_seconds: int = 0,
    rpo_seconds: int = 0,
    replicas: int = 1,
    port: int = 8080,
    revenue_per_minute: float = 0.0,
) -> Component:
    return Component(
        id=cid,
        name=cid,
        type=ComponentType.APP_SERVER,
        replicas=replicas,
        port=port,
        failover=FailoverConfig(enabled=failover, promotion_time_seconds=30.0),
        region=RegionConfig(
            region=region,
            rpo_seconds=rpo_seconds,
            rto_seconds=rto_seconds,
            dr_target_region=dr_target,
        ),
        cost_profile=CostProfile(
            hourly_infra_cost=hourly_cost,
            revenue_per_minute=revenue_per_minute,
        ),
    )


def _storage_comp(
    cid: str = "store1",
    *,
    backup: bool = False,
    backup_freq: float = 24.0,
    failover: bool = False,
    region: str = "",
) -> Component:
    return Component(
        id=cid,
        name=cid,
        type=ComponentType.STORAGE,
        failover=FailoverConfig(enabled=failover, promotion_time_seconds=30.0),
        security=SecurityProfile(
            backup_enabled=backup,
            backup_frequency_hours=backup_freq,
        ),
        region=RegionConfig(region=region),
    )


def _cache_comp(
    cid: str = "cache1",
    *,
    failover: bool = False,
    region: str = "",
) -> Component:
    return Component(
        id=cid,
        name=cid,
        type=ComponentType.CACHE,
        failover=FailoverConfig(enabled=failover, promotion_time_seconds=30.0),
        region=RegionConfig(region=region),
    )


# ---------------------------------------------------------------------------
# Tests: build_recovery_steps
# ---------------------------------------------------------------------------


class TestBuildRecoverySteps:
    def test_empty_graph_returns_no_steps(self) -> None:
        g = _graph()
        orch = DROrchestrator(g)
        steps = orch.build_recovery_steps()
        assert steps == []

    def test_single_app_produces_standard_phases(self) -> None:
        g = _graph(_app_comp("a1"))
        orch = DROrchestrator(g)
        steps = orch.build_recovery_steps()
        phases = [s.phase for s in steps]
        assert RecoveryPhase.DETECTION in phases
        assert RecoveryPhase.TRIAGE in phases
        assert RecoveryPhase.SERVICE_RESTORATION in phases
        assert RecoveryPhase.HEALTH_CHECK in phases

    def test_db_produces_failover_and_data_validation_phases(self) -> None:
        g = _graph(_db_comp("db1"))
        orch = DROrchestrator(g)
        steps = orch.build_recovery_steps()
        phases = [s.phase for s in steps]
        assert RecoveryPhase.FAILOVER in phases
        assert RecoveryPhase.DATA_VALIDATION in phases

    def test_step_ids_unique(self) -> None:
        g = _graph(_app_comp("a1"), _db_comp("db1"))
        orch = DROrchestrator(g)
        steps = orch.build_recovery_steps()
        ids = [s.step_id for s in steps]
        assert len(ids) == len(set(ids))

    def test_detection_step_is_first(self) -> None:
        g = _graph(_app_comp("a1"))
        orch = DROrchestrator(g)
        steps = orch.build_recovery_steps()
        assert steps[0].phase == RecoveryPhase.DETECTION

    def test_health_check_step_is_last(self) -> None:
        g = _graph(_app_comp("a1"), _db_comp("db1"))
        orch = DROrchestrator(g)
        steps = orch.build_recovery_steps()
        assert steps[-1].phase == RecoveryPhase.HEALTH_CHECK

    def test_data_store_failover_before_service_restoration(self) -> None:
        g = _graph(_app_comp("a1"), _db_comp("db1"))
        orch = DROrchestrator(g)
        steps = orch.build_recovery_steps()
        fo_idx = next(i for i, s in enumerate(steps) if s.phase == RecoveryPhase.FAILOVER)
        sr_idx = next(i for i, s in enumerate(steps) if s.phase == RecoveryPhase.SERVICE_RESTORATION)
        assert fo_idx < sr_idx

    def test_failover_enabled_step_is_fully_automated(self) -> None:
        g = _graph(_db_comp("db1", failover=True))
        orch = DROrchestrator(g)
        steps = orch.build_recovery_steps()
        fo_step = next(s for s in steps if s.step_id == "failover_ds_db1")
        assert fo_step.automation_level == AutomationLevel.FULLY_AUTOMATED

    def test_no_failover_step_is_manual(self) -> None:
        g = _graph(_db_comp("db1", failover=False))
        orch = DROrchestrator(g)
        steps = orch.build_recovery_steps()
        fo_step = next(s for s in steps if s.step_id == "failover_ds_db1")
        assert fo_step.automation_level == AutomationLevel.MANUAL


# ---------------------------------------------------------------------------
# Tests: resolve_dependencies
# ---------------------------------------------------------------------------


class TestResolveDependencies:
    def test_produces_layers(self) -> None:
        g = _graph(_app_comp("a1"))
        orch = DROrchestrator(g)
        result = orch.resolve_dependencies()
        assert isinstance(result, StepDependencyGraph)
        assert len(result.execution_order) > 0

    def test_no_cycles_in_generated_steps(self) -> None:
        g = _graph(_app_comp("a1"), _db_comp("db1"))
        orch = DROrchestrator(g)
        result = orch.resolve_dependencies()
        assert result.has_cycles is False

    def test_unresolved_deps_empty_for_generated(self) -> None:
        g = _graph(_app_comp("a1"))
        orch = DROrchestrator(g)
        result = orch.resolve_dependencies()
        assert result.unresolved_deps == []

    def test_unresolved_deps_detected(self) -> None:
        step = RecoveryStep(
            step_id="s1",
            name="test",
            depends_on=["nonexistent"],
            estimated_duration_seconds=10.0,
        )
        g = _graph(_app_comp("a1"))
        orch = DROrchestrator(g)
        result = orch.resolve_dependencies([step])
        assert "nonexistent" in result.unresolved_deps

    def test_total_sequential_time_is_sum(self) -> None:
        g = _graph(_app_comp("a1"))
        orch = DROrchestrator(g)
        steps = orch.build_recovery_steps()
        result = orch.resolve_dependencies(steps)
        expected = sum(s.estimated_duration_seconds for s in steps)
        assert abs(result.total_sequential_time_seconds - expected) < 0.5

    def test_critical_path_lte_sequential(self) -> None:
        g = _graph(_app_comp("a1"), _app_comp("a2"), _db_comp("db1"))
        orch = DROrchestrator(g)
        result = orch.resolve_dependencies()
        assert result.critical_path_seconds <= result.total_sequential_time_seconds


# ---------------------------------------------------------------------------
# Tests: optimise_parallelism
# ---------------------------------------------------------------------------


class TestOptimiseParallelism:
    def test_marks_parallel_steps(self) -> None:
        g = _graph(_app_comp("a1"), _app_comp("a2"))
        orch = DROrchestrator(g)
        result = orch.optimise_parallelism()
        parallel = [s for s in result.steps if s.execution_mode == StepExecutionMode.PARALLEL]
        assert len(parallel) >= 2

    def test_single_component_no_parallel(self) -> None:
        g = _graph(_app_comp("a1"))
        orch = DROrchestrator(g)
        result = orch.optimise_parallelism()
        assert result.parallelisable_groups >= 0

    def test_multi_db_parallel(self) -> None:
        g = _graph(_db_comp("db1"), _db_comp("db2"))
        orch = DROrchestrator(g)
        result = orch.optimise_parallelism()
        fo_steps = [s for s in result.steps if s.phase == RecoveryPhase.FAILOVER]
        parallel_fo = [s for s in fo_steps if s.execution_mode == StepExecutionMode.PARALLEL]
        assert len(parallel_fo) == 2


# ---------------------------------------------------------------------------
# Tests: estimate_critical_path
# ---------------------------------------------------------------------------


class TestEstimateCriticalPath:
    def test_returns_critical_path_result(self) -> None:
        g = _graph(_app_comp("a1"))
        orch = DROrchestrator(g)
        result = orch.estimate_critical_path()
        assert isinstance(result, CriticalPathResult)
        assert result.total_duration_seconds > 0

    def test_bottleneck_identified(self) -> None:
        g = _graph(_app_comp("a1"), _db_comp("db1"))
        orch = DROrchestrator(g)
        result = orch.estimate_critical_path()
        assert result.bottleneck_step_id != ""
        assert result.bottleneck_duration_seconds > 0

    def test_parallel_savings_non_negative(self) -> None:
        g = _graph(_app_comp("a1"), _app_comp("a2"), _db_comp("db1"))
        orch = DROrchestrator(g)
        result = orch.estimate_critical_path()
        assert result.parallel_savings_seconds >= 0

    def test_estimated_rto_equals_total_duration(self) -> None:
        g = _graph(_app_comp("a1"))
        orch = DROrchestrator(g)
        result = orch.estimate_critical_path()
        assert result.estimated_rto_seconds == result.total_duration_seconds

    def test_path_step_ids_nonempty(self) -> None:
        g = _graph(_app_comp("a1"))
        orch = DROrchestrator(g)
        result = orch.estimate_critical_path()
        assert len(result.path_step_ids) > 0


# ---------------------------------------------------------------------------
# Tests: simulate_drill
# ---------------------------------------------------------------------------


class TestSimulateDrill:
    def test_all_success_drill(self) -> None:
        g = _graph(_app_comp("a1"))
        orch = DROrchestrator(g)
        result = orch.simulate_drill()
        assert result.outcome == DrillOutcome.SUCCESS
        assert result.steps_completed > 0
        assert result.steps_failed == 0
        assert result.steps_skipped == 0

    def test_failure_drill(self) -> None:
        g = _graph(_app_comp("a1"))
        orch = DROrchestrator(g)
        steps = orch.build_recovery_steps()
        first_id = steps[0].step_id
        result = orch.simulate_drill(steps, failure_step_ids=[first_id])
        assert result.steps_failed >= 1
        assert result.outcome != DrillOutcome.SUCCESS

    def test_skipped_steps_on_dependency_failure(self) -> None:
        g = _graph(_app_comp("a1"))
        orch = DROrchestrator(g)
        steps = orch.build_recovery_steps()
        # Fail detection -- triage depends on detection, so it should be skipped
        result = orch.simulate_drill(steps, failure_step_ids=["detect_1"])
        assert result.steps_skipped > 0

    def test_drill_events_generated(self) -> None:
        g = _graph(_app_comp("a1"))
        orch = DROrchestrator(g)
        result = orch.simulate_drill()
        assert len(result.events) > 0
        assert all(isinstance(e, DrillEvent) for e in result.events)

    def test_drill_total_duration_positive(self) -> None:
        g = _graph(_app_comp("a1"))
        orch = DROrchestrator(g)
        result = orch.simulate_drill()
        assert result.total_duration_seconds > 0

    def test_drill_rto_achieved(self) -> None:
        g = _graph(_app_comp("a1"))
        orch = DROrchestrator(g)
        result = orch.simulate_drill()
        assert result.rto_achieved_seconds > 0

    def test_drill_data_loss_seconds_for_data_store(self) -> None:
        g = _graph(_db_comp("db1", backup=True, backup_freq=1.0))
        orch = DROrchestrator(g)
        result = orch.simulate_drill()
        assert result.data_loss_seconds > 0

    def test_drill_recommendations_on_failure(self) -> None:
        g = _graph(_app_comp("a1"))
        orch = DROrchestrator(g)
        steps = orch.build_recovery_steps()
        result = orch.simulate_drill(steps, failure_step_ids=["detect_1"])
        assert len(result.recommendations) > 0

    def test_partial_success_outcome(self) -> None:
        g = _graph(_app_comp("a1"), _db_comp("db1"))
        orch = DROrchestrator(g)
        steps = orch.build_recovery_steps()
        # Fail only the health check (last step) -- most steps succeed
        result = orch.simulate_drill(steps, failure_step_ids=["health_check_1"])
        assert result.outcome == DrillOutcome.PARTIAL_SUCCESS

    def test_drill_manual_step_recommendation(self) -> None:
        g = _graph(_app_comp("a1", failover=False))
        orch = DROrchestrator(g)
        result = orch.simulate_drill()
        assert any("manual" in r.lower() or "automate" in r.lower()
                    for r in result.recommendations)


# ---------------------------------------------------------------------------
# Tests: plan_failover_failback
# ---------------------------------------------------------------------------


class TestPlanFailoverFailback:
    def test_data_stores_in_failover_order_first(self) -> None:
        g = _graph(_app_comp("a1"), _db_comp("db1"))
        orch = DROrchestrator(g)
        plan = orch.plan_failover_failback()
        assert plan.data_stores_first == ["db1"]
        assert plan.failover_order[0] == "db1"

    def test_failback_is_reverse(self) -> None:
        g = _graph(_app_comp("a1"), _db_comp("db1"))
        orch = DROrchestrator(g)
        plan = orch.plan_failover_failback()
        assert plan.failback_order == list(reversed(plan.failover_order))

    def test_failback_longer_than_failover(self) -> None:
        g = _graph(_app_comp("a1"), _db_comp("db1"))
        orch = DROrchestrator(g)
        plan = orch.plan_failover_failback()
        assert plan.total_failback_time_seconds > plan.total_failover_time_seconds

    def test_coordination_notes_populated(self) -> None:
        g = _graph(_app_comp("a1"), _db_comp("db1"))
        orch = DROrchestrator(g)
        plan = orch.plan_failover_failback()
        assert len(plan.coordination_notes) > 0

    def test_empty_graph_notes(self) -> None:
        g = _graph()
        orch = DROrchestrator(g)
        plan = orch.plan_failover_failback()
        assert any("No components" in n for n in plan.coordination_notes)

    def test_no_failover_warning(self) -> None:
        g = _graph(_app_comp("a1", failover=False))
        orch = DROrchestrator(g)
        plan = orch.plan_failover_failback()
        assert any("no failover" in n.lower() for n in plan.coordination_notes)

    def test_app_services_list(self) -> None:
        g = _graph(_app_comp("a1"), _app_comp("a2"))
        orch = DROrchestrator(g)
        plan = orch.plan_failover_failback()
        assert set(plan.app_services) == {"a1", "a2"}


# ---------------------------------------------------------------------------
# Tests: validate_data_consistency
# ---------------------------------------------------------------------------


class TestValidateDataConsistency:
    def test_failover_enabled_consistent(self) -> None:
        g = _graph(_db_comp("db1", failover=True))
        orch = DROrchestrator(g)
        report = orch.validate_data_consistency()
        assert len(report.checks) == 1
        assert report.checks[0].is_consistent is True
        assert report.checks[0].validation_method == "streaming_replication"

    def test_backup_enabled_periodic(self) -> None:
        g = _graph(_db_comp("db1", backup=True, backup_freq=1.0))
        orch = DROrchestrator(g)
        report = orch.validate_data_consistency()
        assert report.checks[0].validation_method == "periodic_backup"

    def test_backup_high_frequency_consistent(self) -> None:
        g = _graph(_db_comp("db1", backup=True, backup_freq=0.5))
        orch = DROrchestrator(g)
        report = orch.validate_data_consistency()
        # 0.5 hours * 3600 = 1800s lag, which is <= 3600 so consistent
        assert report.checks[0].is_consistent is True

    def test_backup_low_frequency_inconsistent(self) -> None:
        g = _graph(_db_comp("db1", backup=True, backup_freq=2.0))
        orch = DROrchestrator(g)
        report = orch.validate_data_consistency()
        # 2 hours * 3600 = 7200s lag > 3600 -> inconsistent
        assert report.checks[0].is_consistent is False

    def test_no_replication_inconsistent(self) -> None:
        g = _graph(_db_comp("db1"))
        orch = DROrchestrator(g)
        report = orch.validate_data_consistency()
        assert report.checks[0].is_consistent is False
        assert report.checks[0].validation_method == "none"

    def test_app_server_excluded(self) -> None:
        g = _graph(_app_comp("a1"))
        orch = DROrchestrator(g)
        report = orch.validate_data_consistency()
        assert len(report.checks) == 0
        assert report.all_consistent is True

    def test_storage_is_data_store(self) -> None:
        g = _graph(_storage_comp("store1", backup=True, backup_freq=0.5))
        orch = DROrchestrator(g)
        report = orch.validate_data_consistency()
        assert len(report.checks) == 1

    def test_cache_is_data_store(self) -> None:
        g = _graph(_cache_comp("cache1"))
        orch = DROrchestrator(g)
        report = orch.validate_data_consistency()
        assert len(report.checks) == 1

    def test_max_lag_tracked(self) -> None:
        g = _graph(_db_comp("db1", backup=True, backup_freq=2.0))
        orch = DROrchestrator(g)
        report = orch.validate_data_consistency()
        assert report.max_lag_seconds > 0

    def test_components_with_issues_count(self) -> None:
        g = _graph(_db_comp("db1"), _db_comp("db2", failover=True))
        orch = DROrchestrator(g)
        report = orch.validate_data_consistency()
        # db1 no replication -> inconsistent, db2 failover -> consistent
        assert report.components_with_issues == 1

    def test_recommendation_for_no_replication(self) -> None:
        g = _graph(_db_comp("db1"))
        orch = DROrchestrator(g)
        report = orch.validate_data_consistency()
        assert report.checks[0].recommendation != ""


# ---------------------------------------------------------------------------
# Tests: generate_communication_plan
# ---------------------------------------------------------------------------


class TestGenerateCommunicationPlan:
    def test_has_notifications(self) -> None:
        g = _graph(_comp("a1"))
        orch = DROrchestrator(g)
        plan = orch.generate_communication_plan()
        assert isinstance(plan, CommunicationPlanResult)
        assert plan.total_notifications == 8
        assert len(plan.notifications) == 8

    def test_escalation_chain_has_cto(self) -> None:
        g = _graph(_comp("a1"))
        orch = DROrchestrator(g)
        plan = orch.generate_communication_plan()
        assert "CTO" in plan.escalation_chain

    def test_escalation_chain_length(self) -> None:
        g = _graph(_comp("a1"))
        orch = DROrchestrator(g)
        plan = orch.generate_communication_plan()
        assert len(plan.escalation_chain) == 5

    def test_update_frequency_positive(self) -> None:
        g = _graph(_comp("a1"))
        orch = DROrchestrator(g)
        plan = orch.generate_communication_plan()
        assert plan.update_frequency_minutes > 0

    def test_notification_ordering(self) -> None:
        g = _graph(_comp("a1"))
        orch = DROrchestrator(g)
        plan = orch.generate_communication_plan()
        orders = [n.order for n in plan.notifications]
        assert orders == sorted(orders)

    def test_notifications_have_audience_and_template(self) -> None:
        g = _graph(_comp("a1"))
        orch = DROrchestrator(g)
        plan = orch.generate_communication_plan()
        for n in plan.notifications:
            assert len(n.audience) > 0
            assert len(n.message_template) > 0
            assert isinstance(n.channel, NotificationChannel)

    def test_phases_covered(self) -> None:
        g = _graph(_comp("a1"))
        orch = DROrchestrator(g)
        plan = orch.generate_communication_plan()
        assert len(plan.phases_covered) > 0
        assert "detection" in plan.phases_covered


# ---------------------------------------------------------------------------
# Tests: detect_automation_gaps
# ---------------------------------------------------------------------------


class TestDetectAutomationGaps:
    def test_manual_steps_detected(self) -> None:
        g = _graph(_app_comp("a1", failover=False))
        orch = DROrchestrator(g)
        report = orch.detect_automation_gaps()
        assert isinstance(report, AutomationGapReport)
        assert report.total_manual_steps > 0

    def test_fully_automated_no_gaps_for_auto_step(self) -> None:
        step = RecoveryStep(
            step_id="s1",
            name="auto step",
            automation_level=AutomationLevel.FULLY_AUTOMATED,
            estimated_duration_seconds=30.0,
        )
        g = _graph(_app_comp("a1"))
        orch = DROrchestrator(g)
        report = orch.detect_automation_gaps([step])
        assert report.total_fully_automated_steps == 1
        assert report.total_manual_steps == 0
        assert len(report.gaps) == 0

    def test_semi_automated_has_gap(self) -> None:
        step = RecoveryStep(
            step_id="s1",
            name="semi step",
            automation_level=AutomationLevel.SEMI_AUTOMATED,
            estimated_duration_seconds=100.0,
        )
        g = _graph(_app_comp("a1"))
        orch = DROrchestrator(g)
        report = orch.detect_automation_gaps([step])
        assert report.total_semi_automated_steps == 1
        assert len(report.gaps) == 1
        assert report.gaps[0].current_level == AutomationLevel.SEMI_AUTOMATED

    def test_potential_time_saving(self) -> None:
        step = RecoveryStep(
            step_id="s1",
            name="manual",
            automation_level=AutomationLevel.MANUAL,
            estimated_duration_seconds=100.0,
        )
        g = _graph(_app_comp("a1"))
        orch = DROrchestrator(g)
        report = orch.detect_automation_gaps([step])
        assert report.potential_time_saving_seconds > 0

    def test_automation_percentage(self) -> None:
        steps = [
            RecoveryStep(step_id="s1", name="auto", automation_level=AutomationLevel.FULLY_AUTOMATED,
                         estimated_duration_seconds=30.0),
            RecoveryStep(step_id="s2", name="manual", automation_level=AutomationLevel.MANUAL,
                         estimated_duration_seconds=60.0),
        ]
        g = _graph(_app_comp("a1"))
        orch = DROrchestrator(g)
        report = orch.detect_automation_gaps(steps)
        assert report.automation_percentage == 50.0

    def test_effort_high_for_long_step(self) -> None:
        step = RecoveryStep(
            step_id="s1",
            name="long manual",
            automation_level=AutomationLevel.MANUAL,
            estimated_duration_seconds=600.0,
        )
        g = _graph(_app_comp("a1"))
        orch = DROrchestrator(g)
        report = orch.detect_automation_gaps([step])
        assert report.gaps[0].effort_to_automate == "high"

    def test_effort_medium_for_short_step(self) -> None:
        step = RecoveryStep(
            step_id="s1",
            name="short manual",
            automation_level=AutomationLevel.MANUAL,
            estimated_duration_seconds=100.0,
        )
        g = _graph(_app_comp("a1"))
        orch = DROrchestrator(g)
        report = orch.detect_automation_gaps([step])
        assert report.gaps[0].effort_to_automate == "medium"


# ---------------------------------------------------------------------------
# Tests: score_recovery_priorities
# ---------------------------------------------------------------------------


class TestScoreRecoveryPriorities:
    def test_priority_plan_returned(self) -> None:
        g = _graph(_app_comp("a1"), _db_comp("db1"))
        orch = DROrchestrator(g)
        plan = orch.score_recovery_priorities()
        assert isinstance(plan, RecoveryPriorityPlan)
        assert plan.total_components == 2

    def test_data_store_higher_priority(self) -> None:
        g = _graph(_app_comp("a1"), _db_comp("db1"))
        orch = DROrchestrator(g)
        plan = orch.score_recovery_priorities()
        db_entry = next(e for e in plan.entries if e.component_id == "db1")
        app_entry = next(e for e in plan.entries if e.component_id == "a1")
        assert db_entry.priority_score > app_entry.priority_score

    def test_recovery_order_assigned(self) -> None:
        g = _graph(_app_comp("a1"), _db_comp("db1"))
        orch = DROrchestrator(g)
        plan = orch.score_recovery_priorities()
        orders = [e.recovery_order for e in plan.entries]
        assert sorted(orders) == [1, 2]

    def test_ordered_component_ids(self) -> None:
        g = _graph(_app_comp("a1"), _db_comp("db1"))
        orch = DROrchestrator(g)
        plan = orch.score_recovery_priorities()
        assert plan.ordered_component_ids[0] == "db1"

    def test_high_revenue_increases_score(self) -> None:
        g = _graph(
            _app_comp("a1", revenue_per_minute=0.0),
            _app_comp("a2", revenue_per_minute=10.0),
        )
        orch = DROrchestrator(g)
        plan = orch.score_recovery_priorities()
        a1 = next(e for e in plan.entries if e.component_id == "a1")
        a2 = next(e for e in plan.entries if e.component_id == "a2")
        assert a2.priority_score > a1.priority_score

    def test_dependent_count_increases_score(self) -> None:
        a1 = _app_comp("a1")
        a2 = _app_comp("a2")
        g = _graph(a1, a2)
        g.add_dependency(Dependency(source_id="a2", target_id="a1"))
        orch = DROrchestrator(g)
        plan = orch.score_recovery_priorities()
        entry_a1 = next(e for e in plan.entries if e.component_id == "a1")
        assert entry_a1.dependent_count == 1

    def test_no_failover_adds_urgency(self) -> None:
        g = _graph(
            _app_comp("a1", failover=False),
            _app_comp("a2", failover=True),
        )
        orch = DROrchestrator(g)
        plan = orch.score_recovery_priorities()
        a1 = next(e for e in plan.entries if e.component_id == "a1")
        a2 = next(e for e in plan.entries if e.component_id == "a2")
        assert a1.priority_score > a2.priority_score

    def test_critical_count(self) -> None:
        # Database without failover: 20 (ds) + 10 (no fo) = 30 => MEDIUM
        # Database with high revenue: 20 (ds) + 10 (no fo) + 40 (revenue) = 70 => CRITICAL
        g = _graph(_db_comp("db1", revenue_per_minute=10.0))
        orch = DROrchestrator(g)
        plan = orch.score_recovery_priorities()
        assert plan.critical_count >= 1

    def test_empty_graph(self) -> None:
        g = _graph()
        orch = DROrchestrator(g)
        plan = orch.score_recovery_priorities()
        assert plan.total_components == 0
        assert plan.entries == []


# ---------------------------------------------------------------------------
# Tests: plan_cross_region_failover
# ---------------------------------------------------------------------------


class TestPlanCrossRegionFailover:
    def test_basic_cross_region_plan(self) -> None:
        g = _graph(
            _app_comp("a1", region="us-east-1", dr_target="us-west-2"),
            _db_comp("db1", region="us-east-1", dr_target="us-west-2"),
        )
        orch = DROrchestrator(g)
        plan = orch.plan_cross_region_failover(failed_region="us-east-1")
        assert isinstance(plan, CrossRegionFailoverPlan)
        assert plan.primary_region == "us-east-1"
        assert plan.target_region == "us-west-2"

    def test_failover_sequence_ds_first(self) -> None:
        g = _graph(
            _app_comp("a1", region="us-east-1"),
            _db_comp("db1", region="us-east-1"),
        )
        orch = DROrchestrator(g)
        plan = orch.plan_cross_region_failover(failed_region="us-east-1")
        if plan.failover_sequence:
            assert plan.failover_sequence[0] == "db1"

    def test_dns_propagation_positive(self) -> None:
        g = _graph(_app_comp("a1", region="us-east-1"))
        orch = DROrchestrator(g)
        plan = orch.plan_cross_region_failover(failed_region="us-east-1")
        assert plan.dns_propagation_seconds > 0

    def test_no_dr_target_recommendation(self) -> None:
        g = _graph(_app_comp("a1", region="us-east-1"))
        orch = DROrchestrator(g)
        plan = orch.plan_cross_region_failover(failed_region="us-east-1")
        assert any("No DR target" in r or "dr-" in r for r in plan.recommendations)

    def test_no_failover_recommendation(self) -> None:
        g = _graph(_app_comp("a1", region="us-east-1", failover=False))
        orch = DROrchestrator(g)
        plan = orch.plan_cross_region_failover(failed_region="us-east-1")
        assert any("failover" in r.lower() for r in plan.recommendations)

    def test_regions_in_plan(self) -> None:
        g = _graph(
            _app_comp("a1", region="us-east-1"),
            _app_comp("a2", region="us-west-2"),
        )
        orch = DROrchestrator(g)
        plan = orch.plan_cross_region_failover(failed_region="us-east-1")
        region_names = {r.region_name for r in plan.regions}
        assert "us-east-1" in region_names
        assert "us-west-2" in region_names

    def test_failed_region_not_healthy(self) -> None:
        g = _graph(_app_comp("a1", region="us-east-1"))
        orch = DROrchestrator(g)
        plan = orch.plan_cross_region_failover(failed_region="us-east-1")
        failed_state = next(r for r in plan.regions if r.region_name == "us-east-1")
        assert failed_state.is_healthy is False

    def test_auto_detect_primary_region(self) -> None:
        g = _graph(_app_comp("a1", region="us-east-1"))
        orch = DROrchestrator(g)
        plan = orch.plan_cross_region_failover()
        assert plan.primary_region != ""

    def test_data_sync_seconds(self) -> None:
        g = _graph(_db_comp("db1", region="us-east-1", failover=True))
        orch = DROrchestrator(g)
        plan = orch.plan_cross_region_failover(failed_region="us-east-1")
        assert plan.data_sync_seconds >= 0

    def test_backup_recommendation_for_ds(self) -> None:
        g = _graph(_db_comp("db1", region="us-east-1", backup=False, failover=False))
        orch = DROrchestrator(g)
        plan = orch.plan_cross_region_failover(failed_region="us-east-1")
        assert any("backup" in r.lower() for r in plan.recommendations)


# ---------------------------------------------------------------------------
# Tests: analyse_test_coverage
# ---------------------------------------------------------------------------


class TestAnalyseTestCoverage:
    def test_no_tested_scenarios(self) -> None:
        g = _graph(_app_comp("a1"))
        orch = DROrchestrator(g)
        report = orch.analyse_test_coverage()
        assert isinstance(report, DRTestCoverageReport)
        assert report.tested_scenarios == 0
        assert report.coverage_percentage == 0.0

    def test_some_tested_scenarios(self) -> None:
        g = _graph(_app_comp("a1"), _db_comp("db1"))
        orch = DROrchestrator(g)
        report = orch.analyse_test_coverage(
            tested_scenarios={"single_component_failure": "2024-01-01T00:00:00Z"}
        )
        assert report.tested_scenarios == 1
        assert report.coverage_percentage > 0

    def test_all_tested(self) -> None:
        g = _graph(_app_comp("a1"), _db_comp("db1"))
        orch = DROrchestrator(g)
        all_names = {
            "single_component_failure": "2024-01-01",
            "database_failover": "2024-01-01",
            "full_site_failover": "2024-01-01",
            "network_partition": "2024-01-01",
            "data_corruption": "2024-01-01",
            "cascading_failure": "2024-01-01",
            "dns_failure": "2024-01-01",
            "partial_outage": "2024-01-01",
        }
        report = orch.analyse_test_coverage(tested_scenarios=all_names)
        assert report.coverage_percentage == 100.0

    def test_untested_critical_scenarios(self) -> None:
        g = _graph(_app_comp("a1"), _db_comp("db1"))
        orch = DROrchestrator(g)
        report = orch.analyse_test_coverage()
        assert len(report.untested_critical) > 0
        assert "database_failover" in report.untested_critical

    def test_scenario_has_gap_description(self) -> None:
        g = _graph(_app_comp("a1"))
        orch = DROrchestrator(g)
        report = orch.analyse_test_coverage()
        untested = [e for e in report.entries if not e.is_tested]
        assert all(len(e.gap_description) > 0 for e in untested)

    def test_tested_scenario_has_frequency(self) -> None:
        g = _graph(_app_comp("a1"))
        orch = DROrchestrator(g)
        report = orch.analyse_test_coverage(
            tested_scenarios={"dns_failure": "2024-01-01"}
        )
        tested_entry = next(e for e in report.entries if e.scenario_name == "dns_failure")
        assert tested_entry.test_frequency == "quarterly"

    def test_scenarios_with_no_ds_skip_db_scenarios(self) -> None:
        # If there are no data stores, database_failover and data_corruption have empty
        # covered_ids and should be skipped
        g = _graph(_app_comp("a1"))
        orch = DROrchestrator(g)
        report = orch.analyse_test_coverage()
        names = [e.scenario_name for e in report.entries]
        assert "database_failover" not in names
        assert "data_corruption" not in names


# ---------------------------------------------------------------------------
# Tests: build_checkpoints / validate_checkpoints
# ---------------------------------------------------------------------------


class TestCheckpoints:
    def test_build_checkpoints_nonempty(self) -> None:
        g = _graph(_app_comp("a1"))
        orch = DROrchestrator(g)
        cps = orch.build_checkpoints()
        assert len(cps) > 0
        assert all(isinstance(cp, RecoveryCheckpoint) for cp in cps)

    def test_detection_checkpoint_exists(self) -> None:
        g = _graph(_app_comp("a1"))
        orch = DROrchestrator(g)
        cps = orch.build_checkpoints()
        detection = [cp for cp in cps if cp.phase == RecoveryPhase.DETECTION]
        assert len(detection) == 1

    def test_ds_adds_failover_checkpoint(self) -> None:
        g = _graph(_db_comp("db1"))
        orch = DROrchestrator(g)
        cps = orch.build_checkpoints()
        fo_cps = [cp for cp in cps if cp.checkpoint_id == "cp_ds_failover"]
        assert len(fo_cps) == 1

    def test_app_adds_svc_restored_checkpoint(self) -> None:
        g = _graph(_app_comp("a1"))
        orch = DROrchestrator(g)
        cps = orch.build_checkpoints()
        svc_cps = [cp for cp in cps if cp.checkpoint_id == "cp_svc_restored"]
        assert len(svc_cps) == 1

    def test_health_checkpoint_non_blocking(self) -> None:
        g = _graph(_app_comp("a1"))
        orch = DROrchestrator(g)
        cps = orch.build_checkpoints()
        health = next(cp for cp in cps if cp.checkpoint_id == "cp_health")
        assert health.is_blocking is False

    def test_validate_all_pass(self) -> None:
        g = _graph(_app_comp("a1"))
        orch = DROrchestrator(g)
        result = orch.validate_checkpoints()
        assert result.can_proceed is True
        assert result.failed_checkpoints == 0

    def test_validate_blocking_failure(self) -> None:
        g = _graph(_app_comp("a1"))
        orch = DROrchestrator(g)
        result = orch.validate_checkpoints(failed_checkpoint_ids=["cp_detect"])
        assert result.can_proceed is False
        assert result.blocking_failures >= 1

    def test_validate_non_blocking_failure(self) -> None:
        g = _graph(_app_comp("a1"))
        orch = DROrchestrator(g)
        result = orch.validate_checkpoints(failed_checkpoint_ids=["cp_health"])
        # cp_health is non-blocking, so can still proceed
        assert result.can_proceed is True
        assert result.failed_checkpoints == 1

    def test_validate_bypassed(self) -> None:
        g = _graph(_app_comp("a1"))
        orch = DROrchestrator(g)
        result = orch.validate_checkpoints(bypassed_checkpoint_ids=["cp_detect"])
        assert result.can_proceed is True
        bypassed_cp = next(cp for cp in result.checkpoints if cp.checkpoint_id == "cp_detect")
        assert bypassed_cp.status == CheckpointStatus.BYPASSED

    def test_data_validation_checkpoint_for_ds(self) -> None:
        g = _graph(_db_comp("db1"))
        orch = DROrchestrator(g)
        cps = orch.build_checkpoints()
        dv_cps = [cp for cp in cps if cp.checkpoint_id == "cp_data_valid"]
        assert len(dv_cps) == 1

    def test_no_ds_checkpoints_without_ds(self) -> None:
        g = _graph(_app_comp("a1"))
        orch = DROrchestrator(g)
        cps = orch.build_checkpoints()
        ds_cps = [cp for cp in cps if cp.checkpoint_id in ("cp_ds_failover", "cp_data_valid")]
        assert len(ds_cps) == 0


# ---------------------------------------------------------------------------
# Tests: plan_post_recovery_health
# ---------------------------------------------------------------------------


class TestPostRecoveryHealth:
    def test_health_plan_has_checks(self) -> None:
        g = _graph(_app_comp("a1"))
        orch = DROrchestrator(g)
        plan = orch.plan_post_recovery_health()
        assert isinstance(plan, PostRecoveryHealthPlan)
        assert plan.total_checks > 0

    def test_connectivity_check_for_every_component(self) -> None:
        g = _graph(_app_comp("a1"), _db_comp("db1"))
        orch = DROrchestrator(g)
        plan = orch.plan_post_recovery_health()
        conn_checks = [c for c in plan.checks if "connectivity" in c.check_name]
        assert len(conn_checks) == 2

    def test_performance_check_for_every_component(self) -> None:
        g = _graph(_app_comp("a1"))
        orch = DROrchestrator(g)
        plan = orch.plan_post_recovery_health()
        perf_checks = [c for c in plan.checks if "performance" in c.check_name]
        assert len(perf_checks) == 1

    def test_data_integrity_check_for_data_store(self) -> None:
        g = _graph(_db_comp("db1"))
        orch = DROrchestrator(g)
        plan = orch.plan_post_recovery_health()
        integrity = [c for c in plan.checks if "data_integrity" in c.check_name]
        assert len(integrity) == 1
        assert integrity[0].is_critical is True

    def test_no_data_integrity_for_app(self) -> None:
        g = _graph(_app_comp("a1"))
        orch = DROrchestrator(g)
        plan = orch.plan_post_recovery_health()
        integrity = [c for c in plan.checks if "data_integrity" in c.check_name]
        assert len(integrity) == 0

    def test_replication_check_for_failover_component(self) -> None:
        g = _graph(_db_comp("db1", failover=True))
        orch = DROrchestrator(g)
        plan = orch.plan_post_recovery_health()
        repl = [c for c in plan.checks if "replication" in c.check_name]
        assert len(repl) == 1

    def test_no_replication_check_without_failover(self) -> None:
        g = _graph(_db_comp("db1", failover=False))
        orch = DROrchestrator(g)
        plan = orch.plan_post_recovery_health()
        repl = [c for c in plan.checks if "replication" in c.check_name]
        assert len(repl) == 0

    def test_critical_checks_count(self) -> None:
        g = _graph(_app_comp("a1"), _db_comp("db1"))
        orch = DROrchestrator(g)
        plan = orch.plan_post_recovery_health()
        actual_critical = sum(1 for c in plan.checks if c.is_critical)
        assert plan.critical_checks == actual_critical

    def test_estimated_verification_time(self) -> None:
        g = _graph(_app_comp("a1"))
        orch = DROrchestrator(g)
        plan = orch.plan_post_recovery_health()
        assert plan.estimated_verification_time_seconds == plan.total_checks * 15.0

    def test_phases_listed(self) -> None:
        g = _graph(_app_comp("a1"))
        orch = DROrchestrator(g)
        plan = orch.plan_post_recovery_health()
        assert "health_check" in plan.phases
        assert "post_recovery" in plan.phases

    def test_empty_graph_no_checks(self) -> None:
        g = _graph()
        orch = DROrchestrator(g)
        plan = orch.plan_post_recovery_health()
        assert plan.total_checks == 0


# ---------------------------------------------------------------------------
# Tests: run_full_orchestration
# ---------------------------------------------------------------------------


class TestRunFullOrchestration:
    def test_returns_all_keys(self) -> None:
        g = _graph(_app_comp("a1"), _db_comp("db1"))
        orch = DROrchestrator(g)
        result = orch.run_full_orchestration()
        expected_keys = {
            "steps", "dependency_graph", "optimised_graph", "critical_path",
            "drill_simulation", "failover_plan", "data_consistency",
            "communication_plan", "automation_gaps", "recovery_priorities",
            "cross_region_failover", "test_coverage", "checkpoints",
            "health_plan", "generated_at",
        }
        assert set(result.keys()) == expected_keys

    def test_generated_at_populated(self) -> None:
        g = _graph(_app_comp("a1"))
        orch = DROrchestrator(g)
        result = orch.run_full_orchestration()
        assert len(result["generated_at"]) > 0

    def test_with_failure_step_ids(self) -> None:
        g = _graph(_app_comp("a1"))
        orch = DROrchestrator(g)
        result = orch.run_full_orchestration(failure_step_ids=["detect_1"])
        drill = result["drill_simulation"]
        assert drill.steps_failed >= 1

    def test_with_failed_checkpoint(self) -> None:
        g = _graph(_app_comp("a1"))
        orch = DROrchestrator(g)
        result = orch.run_full_orchestration(failed_checkpoint_ids=["cp_detect"])
        cp_result = result["checkpoints"]
        assert cp_result.blocking_failures >= 1

    def test_with_tested_scenarios(self) -> None:
        g = _graph(_app_comp("a1"), _db_comp("db1"))
        orch = DROrchestrator(g)
        result = orch.run_full_orchestration(
            tested_scenarios={"single_component_failure": "2024-01-01"}
        )
        coverage = result["test_coverage"]
        assert coverage.tested_scenarios == 1

    def test_with_failed_region(self) -> None:
        g = _graph(_app_comp("a1", region="us-east-1"))
        orch = DROrchestrator(g)
        result = orch.run_full_orchestration(failed_region="us-east-1")
        cr = result["cross_region_failover"]
        assert cr.primary_region == "us-east-1"

    def test_empty_graph_full_orchestration(self) -> None:
        g = _graph()
        orch = DROrchestrator(g)
        result = orch.run_full_orchestration()
        assert result["steps"] == []
        assert result["data_consistency"].all_consistent is True


# ---------------------------------------------------------------------------
# Tests: Integration / Combined Scenarios
# ---------------------------------------------------------------------------


class TestIntegrationScenarios:
    def test_full_orchestration_flow(self) -> None:
        """End-to-end: run all methods on a realistic graph."""
        db = _db_comp("db1", failover=True, backup=True, hourly_cost=2.0,
                       region="us-east-1", dr_target="us-west-2")
        app = _app_comp("a1", failover=True, hourly_cost=1.0,
                        region="us-east-1", dr_target="us-west-2")
        g = _graph(db, app)
        orch = DROrchestrator(g)

        # Recovery steps
        steps = orch.build_recovery_steps()
        assert len(steps) > 0

        # Dependency resolution
        dep_graph = orch.resolve_dependencies(steps)
        assert dep_graph.has_cycles is False

        # Parallelism optimisation
        optimised = orch.optimise_parallelism(list(steps))
        assert optimised.critical_path_seconds <= optimised.total_sequential_time_seconds

        # Critical path
        cp = orch.estimate_critical_path(list(steps))
        assert cp.total_duration_seconds > 0

        # Drill simulation
        drill = orch.simulate_drill(list(steps))
        assert drill.outcome == DrillOutcome.SUCCESS

        # Failover/failback
        fo_plan = orch.plan_failover_failback()
        assert fo_plan.failover_order[0] == "db1"

        # Data consistency
        dc = orch.validate_data_consistency()
        assert len(dc.checks) == 1
        assert dc.checks[0].is_consistent is True

        # Communication plan
        comm = orch.generate_communication_plan()
        assert comm.total_notifications == 8

        # Automation gaps
        gaps = orch.detect_automation_gaps(list(steps))
        assert isinstance(gaps, AutomationGapReport)

        # Recovery priorities
        priorities = orch.score_recovery_priorities()
        assert priorities.total_components == 2

        # Cross-region failover
        cr = orch.plan_cross_region_failover(failed_region="us-east-1")
        assert cr.target_region == "us-west-2"

        # Test coverage
        tc = orch.analyse_test_coverage()
        assert tc.total_scenarios > 0

        # Checkpoints
        cps = orch.build_checkpoints()
        cp_result = orch.validate_checkpoints(cps)
        assert cp_result.can_proceed is True

        # Post-recovery health
        health = orch.plan_post_recovery_health()
        assert health.total_checks > 0

    def test_complex_multi_component_graph(self) -> None:
        """Test with a realistic multi-component graph."""
        comps = [
            _app_comp("web1", failover=True, region="us-east-1", hourly_cost=0.5),
            _app_comp("web2", failover=True, region="us-west-2", hourly_cost=0.5),
            _app_comp("api1", failover=True, region="us-east-1", hourly_cost=1.0),
            _db_comp("db1", failover=True, backup=True, hourly_cost=3.0,
                     region="us-east-1", dr_target="us-west-2"),
            _db_comp("cache1", failover=False, hourly_cost=0.5,
                     region="us-east-1"),
            Component(id="queue1", name="queue1", type=ComponentType.QUEUE,
                      region=RegionConfig(region="us-east-1"),
                      cost_profile=CostProfile(hourly_infra_cost=0.3)),
            _storage_comp("store1", backup=True, region="us-east-1"),
        ]
        g = _graph(*comps)
        g.add_dependency(Dependency(source_id="web1", target_id="api1"))
        g.add_dependency(Dependency(source_id="api1", target_id="db1"))

        orch = DROrchestrator(g)

        # Full orchestration
        result = orch.run_full_orchestration(failed_region="us-east-1")

        # Verify steps generated
        assert len(result["steps"]) > 5

        # Data consistency covers data stores
        dc = result["data_consistency"]
        data_ids = {c.component_id for c in dc.checks}
        assert "db1" in data_ids
        assert "store1" in data_ids
        assert "cache1" in data_ids  # cache is a data store type

        # Priorities
        priorities = result["recovery_priorities"]
        assert priorities.total_components == 7

        # Cross-region
        cr = result["cross_region_failover"]
        assert cr.primary_region == "us-east-1"

    def test_only_data_stores(self) -> None:
        """Graph with only data stores."""
        g = _graph(_db_comp("db1"), _storage_comp("store1"))
        orch = DROrchestrator(g)
        steps = orch.build_recovery_steps()
        # Should have detection, triage, failover(x2), data_validation, health_check
        phases = [s.phase for s in steps]
        assert RecoveryPhase.FAILOVER in phases
        assert RecoveryPhase.DATA_VALIDATION in phases
        # No service restoration since no app servers
        assert RecoveryPhase.SERVICE_RESTORATION not in phases

    def test_only_app_servers(self) -> None:
        """Graph with only app servers."""
        g = _graph(_app_comp("a1"), _app_comp("a2"))
        orch = DROrchestrator(g)
        steps = orch.build_recovery_steps()
        phases = [s.phase for s in steps]
        # No failover or data_validation since no data stores
        assert RecoveryPhase.FAILOVER not in phases
        assert RecoveryPhase.DATA_VALIDATION not in phases
        assert RecoveryPhase.SERVICE_RESTORATION in phases
