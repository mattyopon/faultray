"""Tests for the Game Day simulation engine."""

from __future__ import annotations

import pytest

from infrasim.model.components import (
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    HealthStatus,
    OperationalProfile,
)
from infrasim.model.graph import InfraGraph
from infrasim.simulator.gameday_engine import (
    GameDayEngine,
    GameDayPlan,
    GameDayReport,
    GameDayStep,
    GameDayStepResult,
)
from infrasim.simulator.scenarios import Fault, FaultType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _simple_graph() -> InfraGraph:
    """Build a simple LB -> App -> DB graph."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb", name="LB", type=ComponentType.LOAD_BALANCER, replicas=2,
        failover=FailoverConfig(enabled=True, promotion_time_seconds=5),
        operational_profile=OperationalProfile(mtbf_hours=8760, mttr_minutes=2),
    ))
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=3,
        operational_profile=OperationalProfile(mtbf_hours=2160, mttr_minutes=10),
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE, replicas=1,
        operational_profile=OperationalProfile(mtbf_hours=4320, mttr_minutes=30),
    ))
    graph.add_dependency(Dependency(
        source_id="lb", target_id="app", dependency_type="requires",
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
    ))
    return graph


def _basic_plan() -> GameDayPlan:
    """A basic Game Day plan: inject fault then verify health."""
    return GameDayPlan(
        name="Basic Game Day",
        description="Test basic fault injection and recovery",
        steps=[
            GameDayStep(
                time_offset_seconds=0,
                action="inject_fault",
                fault=Fault(
                    target_component_id="db",
                    fault_type=FaultType.COMPONENT_DOWN,
                    severity=1.0,
                    duration_seconds=60,
                ),
                expected_outcome="",
            ),
            GameDayStep(
                time_offset_seconds=30,
                action="verify_health",
                expected_outcome="db:down",
            ),
            GameDayStep(
                time_offset_seconds=60,
                action="manual_check",
                runbook_step="Check monitoring dashboards",
            ),
        ],
        success_criteria=["DB failover completes within 60s"],
        rollback_plan="Restart DB from backup",
    )


# ---------------------------------------------------------------------------
# Tests for basic execution
# ---------------------------------------------------------------------------


class TestGameDayBasic:
    """Basic Game Day engine tests."""

    def test_report_structure(self) -> None:
        graph = _simple_graph()
        engine = GameDayEngine(graph)
        plan = _basic_plan()
        report = engine.execute(plan)

        assert isinstance(report, GameDayReport)
        assert report.plan_name == "Basic Game Day"
        assert len(report.steps) == 3
        assert report.passed >= 0
        assert report.failed >= 0
        assert report.overall in ("PASS", "FAIL")
        assert len(report.timeline_summary) > 0

    def test_step_result_structure(self) -> None:
        graph = _simple_graph()
        engine = GameDayEngine(graph)
        plan = _basic_plan()
        report = engine.execute(plan)

        for step in report.steps:
            assert isinstance(step, GameDayStepResult)
            assert isinstance(step.step_index, int)
            assert step.action in ("inject_fault", "verify_health", "manual_check")
            assert step.outcome in ("PASS", "FAIL", "SKIP")
            assert isinstance(step.details, str)
            assert isinstance(step.health_snapshot, dict)

    def test_empty_plan(self) -> None:
        graph = _simple_graph()
        engine = GameDayEngine(graph)
        plan = GameDayPlan(name="Empty Plan")
        report = engine.execute(plan)

        assert report.plan_name == "Empty Plan"
        assert len(report.steps) == 0
        assert report.passed == 0
        assert report.failed == 0
        assert report.overall == "PASS"


# ---------------------------------------------------------------------------
# Tests for fault injection
# ---------------------------------------------------------------------------


class TestFaultInjection:
    """Tests for inject_fault steps."""

    def test_component_down_injection(self) -> None:
        graph = _simple_graph()
        engine = GameDayEngine(graph)
        plan = GameDayPlan(
            name="DB Down",
            steps=[
                GameDayStep(
                    time_offset_seconds=0,
                    action="inject_fault",
                    fault=Fault(
                        target_component_id="db",
                        fault_type=FaultType.COMPONENT_DOWN,
                    ),
                ),
            ],
        )
        report = engine.execute(plan)

        assert report.steps[0].outcome == "PASS"
        assert "DOWN" in report.steps[0].details
        assert report.steps[0].health_snapshot["db"] == "down"

    def test_latency_spike_injection(self) -> None:
        graph = _simple_graph()
        engine = GameDayEngine(graph)
        plan = GameDayPlan(
            name="Latency Spike",
            steps=[
                GameDayStep(
                    time_offset_seconds=0,
                    action="inject_fault",
                    fault=Fault(
                        target_component_id="app",
                        fault_type=FaultType.LATENCY_SPIKE,
                        severity=0.5,
                    ),
                ),
            ],
        )
        report = engine.execute(plan)

        assert report.steps[0].outcome == "PASS"
        assert report.steps[0].health_snapshot["app"] == "degraded"

    def test_cpu_saturation_high_severity(self) -> None:
        graph = _simple_graph()
        engine = GameDayEngine(graph)
        plan = GameDayPlan(
            name="CPU Saturation",
            steps=[
                GameDayStep(
                    time_offset_seconds=0,
                    action="inject_fault",
                    fault=Fault(
                        target_component_id="app",
                        fault_type=FaultType.CPU_SATURATION,
                        severity=0.9,
                    ),
                ),
            ],
        )
        report = engine.execute(plan)

        assert report.steps[0].health_snapshot["app"] == "overloaded"

    def test_missing_fault_skipped(self) -> None:
        graph = _simple_graph()
        engine = GameDayEngine(graph)
        plan = GameDayPlan(
            name="No Fault",
            steps=[
                GameDayStep(
                    time_offset_seconds=0,
                    action="inject_fault",
                    fault=None,
                ),
            ],
        )
        report = engine.execute(plan)

        assert report.steps[0].outcome == "SKIP"

    def test_unknown_target_fails(self) -> None:
        graph = _simple_graph()
        engine = GameDayEngine(graph)
        plan = GameDayPlan(
            name="Missing Target",
            steps=[
                GameDayStep(
                    time_offset_seconds=0,
                    action="inject_fault",
                    fault=Fault(
                        target_component_id="nonexistent",
                        fault_type=FaultType.COMPONENT_DOWN,
                    ),
                ),
            ],
        )
        report = engine.execute(plan)

        assert report.steps[0].outcome == "FAIL"
        assert "not found" in report.steps[0].details

    def test_failover_mentioned_when_available(self) -> None:
        graph = _simple_graph()
        engine = GameDayEngine(graph)
        plan = GameDayPlan(
            name="LB Fault",
            steps=[
                GameDayStep(
                    time_offset_seconds=0,
                    action="inject_fault",
                    fault=Fault(
                        target_component_id="lb",
                        fault_type=FaultType.COMPONENT_DOWN,
                    ),
                ),
            ],
        )
        report = engine.execute(plan)

        assert "failover" in report.steps[0].details.lower()

    def test_cascade_detected(self) -> None:
        graph = _simple_graph()
        engine = GameDayEngine(graph)
        plan = GameDayPlan(
            name="DB Down Cascade",
            steps=[
                GameDayStep(
                    time_offset_seconds=0,
                    action="inject_fault",
                    fault=Fault(
                        target_component_id="db",
                        fault_type=FaultType.COMPONENT_DOWN,
                    ),
                ),
            ],
        )
        report = engine.execute(plan)

        # DB is a dependency, so cascade should affect app and lb
        assert "cascade" in report.steps[0].details.lower() or \
               "affect" in report.steps[0].details.lower()


# ---------------------------------------------------------------------------
# Tests for health verification
# ---------------------------------------------------------------------------


class TestHealthVerification:
    """Tests for verify_health steps."""

    def test_expected_status_matches(self) -> None:
        graph = _simple_graph()
        engine = GameDayEngine(graph)
        plan = GameDayPlan(
            name="Verify Healthy",
            steps=[
                GameDayStep(
                    time_offset_seconds=0,
                    action="verify_health",
                    expected_outcome="all_healthy",
                ),
            ],
        )
        report = engine.execute(plan)

        # All components should be healthy initially
        assert report.steps[0].outcome == "PASS"

    def test_expected_status_mismatch(self) -> None:
        graph = _simple_graph()
        engine = GameDayEngine(graph)
        plan = GameDayPlan(
            name="Inject then verify healthy",
            steps=[
                GameDayStep(
                    time_offset_seconds=0,
                    action="inject_fault",
                    fault=Fault(
                        target_component_id="db",
                        fault_type=FaultType.COMPONENT_DOWN,
                    ),
                ),
                GameDayStep(
                    time_offset_seconds=10,
                    action="verify_health",
                    expected_outcome="all_healthy",
                ),
            ],
        )
        report = engine.execute(plan)

        # After injecting db down, all_healthy should fail
        assert report.steps[1].outcome == "FAIL"

    def test_component_specific_verification(self) -> None:
        graph = _simple_graph()
        engine = GameDayEngine(graph)
        plan = GameDayPlan(
            name="Verify specific",
            steps=[
                GameDayStep(
                    time_offset_seconds=0,
                    action="inject_fault",
                    fault=Fault(
                        target_component_id="db",
                        fault_type=FaultType.COMPONENT_DOWN,
                    ),
                ),
                GameDayStep(
                    time_offset_seconds=10,
                    action="verify_health",
                    expected_outcome="db:down",
                ),
            ],
        )
        report = engine.execute(plan)

        # Verifying db:down should pass
        assert report.steps[1].outcome == "PASS"

    def test_no_expected_outcome_with_down(self) -> None:
        graph = _simple_graph()
        engine = GameDayEngine(graph)
        plan = GameDayPlan(
            name="No Expected",
            steps=[
                GameDayStep(
                    time_offset_seconds=0,
                    action="inject_fault",
                    fault=Fault(
                        target_component_id="db",
                        fault_type=FaultType.COMPONENT_DOWN,
                    ),
                ),
                GameDayStep(
                    time_offset_seconds=10,
                    action="verify_health",
                ),
            ],
        )
        report = engine.execute(plan)

        # With no expected outcome but down components, should FAIL
        assert report.steps[1].outcome == "FAIL"


# ---------------------------------------------------------------------------
# Tests for manual checks
# ---------------------------------------------------------------------------


class TestManualCheck:
    """Tests for manual_check steps."""

    def test_manual_check_always_passes(self) -> None:
        graph = _simple_graph()
        engine = GameDayEngine(graph)
        plan = GameDayPlan(
            name="Manual",
            steps=[
                GameDayStep(
                    time_offset_seconds=0,
                    action="manual_check",
                    runbook_step="Verify monitoring dashboard",
                ),
            ],
        )
        report = engine.execute(plan)

        assert report.steps[0].outcome == "PASS"
        assert "monitoring" in report.steps[0].details.lower()


# ---------------------------------------------------------------------------
# Tests for overall report
# ---------------------------------------------------------------------------


class TestOverallReport:
    """Tests for the overall Game Day report."""

    def test_all_pass_overall_pass(self) -> None:
        graph = _simple_graph()
        engine = GameDayEngine(graph)
        plan = GameDayPlan(
            name="All Pass",
            steps=[
                GameDayStep(
                    time_offset_seconds=0,
                    action="verify_health",
                    expected_outcome="all_healthy",
                ),
                GameDayStep(
                    time_offset_seconds=10,
                    action="manual_check",
                ),
            ],
        )
        report = engine.execute(plan)

        assert report.overall == "PASS"
        assert report.failed == 0
        assert report.passed == 2

    def test_any_fail_overall_fail(self) -> None:
        graph = _simple_graph()
        engine = GameDayEngine(graph)
        plan = GameDayPlan(
            name="With Failure",
            steps=[
                GameDayStep(
                    time_offset_seconds=0,
                    action="inject_fault",
                    fault=Fault(
                        target_component_id="db",
                        fault_type=FaultType.COMPONENT_DOWN,
                    ),
                ),
                GameDayStep(
                    time_offset_seconds=10,
                    action="verify_health",
                    expected_outcome="all_healthy",
                ),
            ],
        )
        report = engine.execute(plan)

        assert report.overall == "FAIL"
        assert report.failed >= 1

    def test_timeline_summary_contains_steps(self) -> None:
        graph = _simple_graph()
        engine = GameDayEngine(graph)
        plan = _basic_plan()
        report = engine.execute(plan)

        assert "3 steps" in report.timeline_summary
        assert "inject_fault" in report.timeline_summary
        assert "verify_health" in report.timeline_summary

    def test_unknown_action_skipped(self) -> None:
        graph = _simple_graph()
        engine = GameDayEngine(graph)
        plan = GameDayPlan(
            name="Unknown Action",
            steps=[
                GameDayStep(
                    time_offset_seconds=0,
                    action="unknown_action",
                ),
            ],
        )
        report = engine.execute(plan)

        assert report.steps[0].outcome == "SKIP"
        assert report.overall == "PASS"  # skipped steps don't fail


# ---------------------------------------------------------------------------
# Tests for multi-fault scenarios
# ---------------------------------------------------------------------------


class TestMultiFault:
    """Tests for plans with multiple fault injections."""

    def test_multiple_faults_accumulate(self) -> None:
        graph = _simple_graph()
        engine = GameDayEngine(graph)
        plan = GameDayPlan(
            name="Multi Fault",
            steps=[
                GameDayStep(
                    time_offset_seconds=0,
                    action="inject_fault",
                    fault=Fault(
                        target_component_id="db",
                        fault_type=FaultType.COMPONENT_DOWN,
                    ),
                ),
                GameDayStep(
                    time_offset_seconds=30,
                    action="inject_fault",
                    fault=Fault(
                        target_component_id="app",
                        fault_type=FaultType.LATENCY_SPIKE,
                        severity=0.5,
                    ),
                ),
                GameDayStep(
                    time_offset_seconds=60,
                    action="verify_health",
                    expected_outcome="db:down",
                ),
            ],
        )
        report = engine.execute(plan)

        # Both faults should have been applied
        assert report.steps[2].health_snapshot["db"] == "down"
        assert report.steps[2].health_snapshot["app"] == "degraded"
        assert report.steps[2].outcome == "PASS"  # expected db:down

    def test_all_fault_types(self) -> None:
        """Test that all fault types are handled."""
        graph = _simple_graph()
        engine = GameDayEngine(graph)

        fault_types = [
            FaultType.COMPONENT_DOWN,
            FaultType.LATENCY_SPIKE,
            FaultType.CPU_SATURATION,
            FaultType.MEMORY_EXHAUSTION,
            FaultType.DISK_FULL,
            FaultType.CONNECTION_POOL_EXHAUSTION,
            FaultType.NETWORK_PARTITION,
            FaultType.TRAFFIC_SPIKE,
        ]

        steps = [
            GameDayStep(
                time_offset_seconds=i * 10,
                action="inject_fault",
                fault=Fault(
                    target_component_id="app",
                    fault_type=ft,
                    severity=0.9,
                ),
            )
            for i, ft in enumerate(fault_types)
        ]

        plan = GameDayPlan(name="All Faults", steps=steps)
        report = engine.execute(plan)

        # All injections should succeed (PASS or at worst produce details)
        for step in report.steps:
            assert step.outcome in ("PASS", "SKIP")
