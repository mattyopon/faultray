"""Tests for the Chaos Experiment Designer."""

import json

import pytest

from infrasim.model.components import (
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    HealthStatus,
    ResourceMetrics,
)
from infrasim.model.graph import InfraGraph
from infrasim.simulator.experiment_designer import (
    ActionType,
    AssertionType,
    ExperimentAction,
    ExperimentAssertion,
    ExperimentDesign,
    ExperimentDesigner,
    ExperimentPhase,
    ExperimentResult,
    ExperimentStep,
)


# ---------------------------------------------------------------------------
# Helper: build test graphs
# ---------------------------------------------------------------------------

def _build_simple_graph() -> InfraGraph:
    """Build a minimal test graph with a few components."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb", name="Load Balancer", type=ComponentType.LOAD_BALANCER,
        replicas=2, metrics=ResourceMetrics(cpu_percent=30.0, memory_percent=40.0),
    ))
    graph.add_component(Component(
        id="app", name="App Server", type=ComponentType.APP_SERVER,
        replicas=2, metrics=ResourceMetrics(cpu_percent=50.0, memory_percent=50.0),
    ))
    graph.add_component(Component(
        id="db", name="Database", type=ComponentType.DATABASE,
        replicas=1, failover=FailoverConfig(enabled=True, promotion_time_seconds=30.0),
        metrics=ResourceMetrics(cpu_percent=40.0, memory_percent=60.0),
    ))
    graph.add_component(Component(
        id="cache", name="Cache", type=ComponentType.CACHE,
        replicas=1, metrics=ResourceMetrics(cpu_percent=20.0, memory_percent=30.0),
    ))
    graph.add_dependency(Dependency(source_id="lb", target_id="app", dependency_type="requires"))
    graph.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))
    graph.add_dependency(Dependency(source_id="app", target_id="cache", dependency_type="optional"))
    return graph


def _build_large_graph() -> InfraGraph:
    """Build a larger graph to test blast radius limits."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb", name="LB", type=ComponentType.LOAD_BALANCER, replicas=2,
    ))
    for i in range(5):
        graph.add_component(Component(
            id=f"app-{i}", name=f"App {i}", type=ComponentType.APP_SERVER, replicas=1,
        ))
        graph.add_dependency(Dependency(source_id="lb", target_id=f"app-{i}", dependency_type="requires"))
    graph.add_component(Component(
        id="db", name="Database", type=ComponentType.DATABASE, replicas=1,
    ))
    for i in range(5):
        graph.add_dependency(Dependency(source_id=f"app-{i}", target_id="db", dependency_type="requires"))
    graph.add_component(Component(
        id="cache", name="Cache", type=ComponentType.CACHE, replicas=1,
    ))
    graph.add_component(Component(
        id="ext", name="External API", type=ComponentType.EXTERNAL_API, replicas=1,
    ))
    graph.add_component(Component(
        id="storage", name="Storage", type=ComponentType.STORAGE, replicas=1,
    ))
    return graph


# ---------------------------------------------------------------------------
# Test: Experiment creation and step addition
# ---------------------------------------------------------------------------

class TestExperimentCreation:

    def test_create_experiment_basic(self):
        designer = ExperimentDesigner()
        exp = designer.create_experiment("test-1", "A test experiment", "It should work")
        assert exp.name == "test-1"
        assert exp.description == "A test experiment"
        assert exp.hypothesis == "It should work"
        assert exp.steps == []
        assert exp.created_at != ""

    def test_create_experiment_has_timestamp(self):
        designer = ExperimentDesigner()
        exp = designer.create_experiment("ts-test", "desc", "hyp")
        assert len(exp.created_at) > 0
        # Should be valid ISO format
        assert "T" in exp.created_at

    def test_create_experiment_duplicate_name_raises(self):
        designer = ExperimentDesigner()
        designer.create_experiment("dup-test", "desc", "hyp")
        with pytest.raises(ValueError, match="Duplicate experiment name"):
            designer.create_experiment("dup-test", "desc2", "hyp2")

    def test_add_step_returns_design(self):
        designer = ExperimentDesigner()
        exp = designer.create_experiment("step-test", "desc", "hyp")
        result = designer.add_step(
            exp, ExperimentPhase.SETUP, description="Setup step"
        )
        assert result is exp
        assert len(exp.steps) == 1
        assert exp.steps[0].phase == ExperimentPhase.SETUP

    def test_add_multiple_steps(self):
        designer = ExperimentDesigner()
        exp = designer.create_experiment("multi-step", "desc", "hyp")
        designer.add_step(exp, ExperimentPhase.SETUP, description="Setup")
        designer.add_step(
            exp,
            ExperimentPhase.INJECT,
            actions=[
                ExperimentAction(
                    action_type=ActionType.KILL_COMPONENT,
                    target_component_id="app",
                    duration_seconds=60,
                )
            ],
            description="Inject failure",
        )
        designer.add_step(exp, ExperimentPhase.OBSERVE, wait_seconds=30, description="Observe")
        designer.add_step(
            exp,
            ExperimentPhase.VERIFY,
            assertions=[
                ExperimentAssertion(
                    assertion_type=AssertionType.HEALTH_CHECK,
                    description="Check health",
                )
            ],
            description="Verify",
        )
        designer.add_step(exp, ExperimentPhase.ROLLBACK, description="Rollback")
        assert len(exp.steps) == 5
        assert exp.steps[0].phase == ExperimentPhase.SETUP
        assert exp.steps[1].phase == ExperimentPhase.INJECT
        assert exp.steps[2].phase == ExperimentPhase.OBSERVE
        assert exp.steps[3].phase == ExperimentPhase.VERIFY
        assert exp.steps[4].phase == ExperimentPhase.ROLLBACK

    def test_add_step_with_no_actions_or_assertions(self):
        designer = ExperimentDesigner()
        exp = designer.create_experiment("empty-step", "desc", "hyp")
        designer.add_step(exp, ExperimentPhase.OBSERVE, wait_seconds=10)
        step = exp.steps[0]
        assert step.actions == []
        assert step.assertions == []
        assert step.wait_seconds == 10


# ---------------------------------------------------------------------------
# Test: All action types
# ---------------------------------------------------------------------------

class TestActionTypes:

    def test_all_action_types_exist(self):
        expected = {
            "kill_component", "degrade_component", "spike_traffic",
            "partition_network", "corrupt_data", "delay_responses",
            "exhaust_resources", "failover_trigger",
        }
        actual = {at.value for at in ActionType}
        assert actual == expected

    def test_kill_component_action(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("kill-test", "desc", "hyp")
        designer.add_step(
            exp, ExperimentPhase.INJECT,
            actions=[ExperimentAction(ActionType.KILL_COMPONENT, "app", duration_seconds=60)],
        )
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(AssertionType.HEALTH_CHECK, "app")],
        )
        exp.rollback_plan = [ExperimentAction(ActionType.FAILOVER_TRIGGER, "app")]
        result = designer.run_experiment(exp, graph)
        # After killing app, health check on app should fail
        assert len(result.failed_assertions) > 0

    def test_degrade_component_action(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("degrade-test", "desc", "hyp")
        designer.add_step(
            exp, ExperimentPhase.INJECT,
            actions=[ExperimentAction(ActionType.DEGRADE_COMPONENT, "app")],
        )
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(AssertionType.HEALTH_CHECK, "app")],
        )
        exp.rollback_plan = [ExperimentAction(ActionType.FAILOVER_TRIGGER, "app")]
        result = designer.run_experiment(exp, graph)
        assert len(result.failed_assertions) >= 1

    def test_spike_traffic_action(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("spike-test", "desc", "hyp")
        designer.add_step(
            exp, ExperimentPhase.INJECT,
            actions=[ExperimentAction(
                ActionType.SPIKE_TRAFFIC, "lb",
                parameters={"multiplier": 10}, duration_seconds=60,
            )],
        )
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(AssertionType.LATENCY_BELOW, threshold=5000.0)],
        )
        exp.rollback_plan = [ExperimentAction(ActionType.SPIKE_TRAFFIC, "lb", parameters={"multiplier": 1})]
        result = designer.run_experiment(exp, graph)
        assert len(result.observations) > 0

    def test_partition_network_action(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("partition-test", "desc", "hyp")
        designer.add_step(
            exp, ExperimentPhase.INJECT,
            actions=[ExperimentAction(ActionType.PARTITION_NETWORK, "app")],
        )
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(
                AssertionType.AVAILABILITY_ABOVE, threshold=20.0,
                description="Partial availability",
            )],
        )
        exp.rollback_plan = [ExperimentAction(ActionType.FAILOVER_TRIGGER, "app")]
        result = designer.run_experiment(exp, graph)
        assert any("partition" in o.lower() for o in result.observations)

    def test_corrupt_data_action(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("corrupt-test", "desc", "hyp")
        designer.add_step(
            exp, ExperimentPhase.INJECT,
            actions=[ExperimentAction(ActionType.CORRUPT_DATA, "db")],
        )
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(AssertionType.NO_DATA_LOSS)],
        )
        exp.rollback_plan = [ExperimentAction(ActionType.FAILOVER_TRIGGER, "db")]
        result = designer.run_experiment(exp, graph)
        assert any("corruption" in o.lower() for o in result.observations)

    def test_delay_responses_action(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("delay-test", "desc", "hyp")
        designer.add_step(
            exp, ExperimentPhase.INJECT,
            actions=[ExperimentAction(
                ActionType.DELAY_RESPONSES, "db",
                parameters={"delay_ms": 30000},
            )],
        )
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(
                AssertionType.LATENCY_BELOW, "db", threshold=100.0,
            )],
        )
        exp.rollback_plan = [ExperimentAction(ActionType.DELAY_RESPONSES, "db", parameters={"delay_ms": 0})]
        result = designer.run_experiment(exp, graph)
        # Delay should make latency assertion fail
        assert len(result.failed_assertions) >= 1

    def test_delay_responses_small_delay_no_degrade(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("small-delay-test", "desc", "hyp")
        designer.add_step(
            exp, ExperimentPhase.INJECT,
            actions=[ExperimentAction(
                ActionType.DELAY_RESPONSES, "db",
                parameters={"delay_ms": 100},
            )],
        )
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(AssertionType.HEALTH_CHECK, "db")],
        )
        exp.rollback_plan = [ExperimentAction(ActionType.DELAY_RESPONSES, "db", parameters={"delay_ms": 0})]
        result = designer.run_experiment(exp, graph)
        # Small delay should not degrade the component
        assert len(result.passed_assertions) >= 1

    def test_exhaust_resources_action(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("exhaust-test", "desc", "hyp")
        designer.add_step(
            exp, ExperimentPhase.INJECT,
            actions=[ExperimentAction(ActionType.EXHAUST_RESOURCES, "app")],
        )
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(AssertionType.HEALTH_CHECK, "app")],
        )
        exp.rollback_plan = [ExperimentAction(ActionType.FAILOVER_TRIGGER, "app")]
        result = designer.run_experiment(exp, graph)
        # Resource exhaustion should make the component unhealthy
        assert len(result.failed_assertions) >= 1

    def test_failover_trigger_action_with_failover_enabled(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("failover-test", "desc", "hyp")
        # First kill, then trigger failover on the DB (which has failover enabled)
        designer.add_step(
            exp, ExperimentPhase.INJECT,
            actions=[ExperimentAction(ActionType.KILL_COMPONENT, "db")],
        )
        designer.add_step(
            exp, ExperimentPhase.INJECT,
            actions=[ExperimentAction(ActionType.FAILOVER_TRIGGER, "db")],
        )
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(AssertionType.HEALTH_CHECK, "db")],
        )
        exp.rollback_plan = [ExperimentAction(ActionType.FAILOVER_TRIGGER, "db")]
        result = designer.run_experiment(exp, graph)
        # After failover trigger on db with failover enabled, it should be healthy
        assert any(a.assertion_type == AssertionType.HEALTH_CHECK for a, _ in result.passed_assertions)

    def test_failover_trigger_action_without_failover(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("no-failover-test", "desc", "hyp")
        # Cache doesn't have failover enabled
        designer.add_step(
            exp, ExperimentPhase.INJECT,
            actions=[ExperimentAction(ActionType.KILL_COMPONENT, "cache")],
        )
        designer.add_step(
            exp, ExperimentPhase.INJECT,
            actions=[ExperimentAction(ActionType.FAILOVER_TRIGGER, "cache")],
        )
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(AssertionType.HEALTH_CHECK, "cache")],
        )
        exp.rollback_plan = [ExperimentAction(ActionType.FAILOVER_TRIGGER, "cache")]
        result = designer.run_experiment(exp, graph)
        # Without failover, the cache should remain DOWN
        assert any(a.assertion_type == AssertionType.HEALTH_CHECK for a, _ in result.failed_assertions)


# ---------------------------------------------------------------------------
# Test: All assertion types
# ---------------------------------------------------------------------------

class TestAssertionTypes:

    def test_all_assertion_types_exist(self):
        expected = {
            "health_check", "latency_below", "error_rate_below",
            "availability_above", "recovery_within", "cascade_contained",
            "no_data_loss",
        }
        actual = {at.value for at in AssertionType}
        assert actual == expected

    def test_health_check_specific_component_healthy(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("hc-healthy", "desc", "hyp")
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(AssertionType.HEALTH_CHECK, "app")],
        )
        result = designer.run_experiment(exp, graph)
        assert len(result.passed_assertions) == 1

    def test_health_check_all_components(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("hc-all", "desc", "hyp")
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(AssertionType.HEALTH_CHECK, None)],
        )
        result = designer.run_experiment(exp, graph)
        assert len(result.passed_assertions) == 1

    def test_health_check_missing_component(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("hc-missing", "desc", "hyp")
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(AssertionType.HEALTH_CHECK, "nonexistent")],
        )
        result = designer.run_experiment(exp, graph)
        assert len(result.failed_assertions) == 1

    def test_latency_below_passes(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("lat-pass", "desc", "hyp")
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(AssertionType.LATENCY_BELOW, "app", threshold=100.0)],
        )
        result = designer.run_experiment(exp, graph)
        assert len(result.passed_assertions) == 1

    def test_latency_below_all_components(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("lat-all", "desc", "hyp")
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(AssertionType.LATENCY_BELOW, None, threshold=100.0)],
        )
        result = designer.run_experiment(exp, graph)
        assert len(result.passed_assertions) == 1

    def test_latency_below_fails(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("lat-fail", "desc", "hyp")
        # Set a very low threshold that the default rtt_ms (1.0) won't meet
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(AssertionType.LATENCY_BELOW, "app", threshold=0.5)],
        )
        result = designer.run_experiment(exp, graph)
        assert len(result.failed_assertions) == 1

    def test_latency_below_missing_component(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("lat-missing", "desc", "hyp")
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(AssertionType.LATENCY_BELOW, "nonexistent", threshold=100.0)],
        )
        result = designer.run_experiment(exp, graph)
        assert len(result.failed_assertions) == 1

    def test_error_rate_below_passes(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("err-pass", "desc", "hyp")
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(AssertionType.ERROR_RATE_BELOW, threshold=50.0)],
        )
        result = designer.run_experiment(exp, graph)
        assert len(result.passed_assertions) == 1

    def test_error_rate_below_fails(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("err-fail", "desc", "hyp")
        # Kill components first, then check error rate
        designer.add_step(
            exp, ExperimentPhase.INJECT,
            actions=[
                ExperimentAction(ActionType.KILL_COMPONENT, "app"),
                ExperimentAction(ActionType.KILL_COMPONENT, "db"),
                ExperimentAction(ActionType.KILL_COMPONENT, "cache"),
            ],
        )
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(AssertionType.ERROR_RATE_BELOW, threshold=1.0)],
        )
        exp.rollback_plan = [
            ExperimentAction(ActionType.FAILOVER_TRIGGER, "app"),
            ExperimentAction(ActionType.FAILOVER_TRIGGER, "db"),
            ExperimentAction(ActionType.FAILOVER_TRIGGER, "cache"),
        ]
        result = designer.run_experiment(exp, graph)
        assert len(result.failed_assertions) >= 1

    def test_availability_above_passes(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("avail-pass", "desc", "hyp")
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(AssertionType.AVAILABILITY_ABOVE, threshold=50.0)],
        )
        result = designer.run_experiment(exp, graph)
        assert len(result.passed_assertions) == 1

    def test_availability_above_fails(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("avail-fail", "desc", "hyp")
        designer.add_step(
            exp, ExperimentPhase.INJECT,
            actions=[
                ExperimentAction(ActionType.KILL_COMPONENT, "app"),
                ExperimentAction(ActionType.KILL_COMPONENT, "db"),
                ExperimentAction(ActionType.KILL_COMPONENT, "cache"),
                ExperimentAction(ActionType.KILL_COMPONENT, "lb"),
            ],
        )
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(AssertionType.AVAILABILITY_ABOVE, threshold=99.0)],
        )
        exp.rollback_plan = [
            ExperimentAction(ActionType.FAILOVER_TRIGGER, "app"),
            ExperimentAction(ActionType.FAILOVER_TRIGGER, "db"),
            ExperimentAction(ActionType.FAILOVER_TRIGGER, "cache"),
            ExperimentAction(ActionType.FAILOVER_TRIGGER, "lb"),
        ]
        result = designer.run_experiment(exp, graph)
        assert len(result.failed_assertions) >= 1

    def test_recovery_within_passes(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("recovery-pass", "desc", "hyp")
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(
                AssertionType.RECOVERY_WITHIN, "db", threshold=60.0,
            )],
        )
        result = designer.run_experiment(exp, graph)
        # DB has failover enabled with 30s promotion time, threshold is 60s
        assert len(result.passed_assertions) == 1

    def test_recovery_within_fails(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("recovery-fail", "desc", "hyp")
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(
                AssertionType.RECOVERY_WITHIN, "db", threshold=10.0,
                description="Recovery within 10s",
            )],
        )
        result = designer.run_experiment(exp, graph)
        # DB has 30s promotion time, threshold is 10s
        assert len(result.failed_assertions) == 1

    def test_recovery_within_no_failover(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("recovery-no-fo", "desc", "hyp")
        # Cache has no failover, so recovery time defaults to 600s
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(
                AssertionType.RECOVERY_WITHIN, "cache", threshold=100.0,
            )],
        )
        result = designer.run_experiment(exp, graph)
        assert len(result.failed_assertions) == 1

    def test_recovery_within_no_target(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("recovery-no-tgt", "desc", "hyp")
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(
                AssertionType.RECOVERY_WITHIN, None, threshold=100.0,
            )],
        )
        result = designer.run_experiment(exp, graph)
        assert len(result.passed_assertions) == 1

    def test_recovery_within_missing_component(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("recovery-missing", "desc", "hyp")
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(
                AssertionType.RECOVERY_WITHIN, "nonexistent", threshold=100.0,
            )],
        )
        result = designer.run_experiment(exp, graph)
        assert len(result.failed_assertions) == 1

    def test_cascade_contained_passes(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("cascade-pass", "desc", "hyp")
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(AssertionType.CASCADE_CONTAINED, threshold=5.0)],
        )
        result = designer.run_experiment(exp, graph)
        assert len(result.passed_assertions) == 1

    def test_cascade_contained_fails(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("cascade-fail", "desc", "hyp")
        designer.add_step(
            exp, ExperimentPhase.INJECT,
            actions=[
                ExperimentAction(ActionType.KILL_COMPONENT, "app"),
                ExperimentAction(ActionType.KILL_COMPONENT, "db"),
                ExperimentAction(ActionType.KILL_COMPONENT, "cache"),
            ],
        )
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(AssertionType.CASCADE_CONTAINED, threshold=0.0)],
        )
        exp.rollback_plan = [
            ExperimentAction(ActionType.FAILOVER_TRIGGER, "app"),
            ExperimentAction(ActionType.FAILOVER_TRIGGER, "db"),
            ExperimentAction(ActionType.FAILOVER_TRIGGER, "cache"),
        ]
        result = designer.run_experiment(exp, graph)
        assert len(result.failed_assertions) >= 1

    def test_no_data_loss_passes(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("ndl-pass", "desc", "hyp")
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(AssertionType.NO_DATA_LOSS)],
        )
        result = designer.run_experiment(exp, graph)
        assert len(result.passed_assertions) == 1

    def test_no_data_loss_fails_when_db_down(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("ndl-fail", "desc", "hyp")
        designer.add_step(
            exp, ExperimentPhase.INJECT,
            actions=[ExperimentAction(ActionType.KILL_COMPONENT, "db")],
        )
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(AssertionType.NO_DATA_LOSS)],
        )
        exp.rollback_plan = [ExperimentAction(ActionType.FAILOVER_TRIGGER, "db")]
        result = designer.run_experiment(exp, graph)
        assert len(result.failed_assertions) >= 1

    def test_no_data_loss_no_data_components(self):
        """When there are no data components, NO_DATA_LOSS should pass."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER, replicas=1,
        ))
        designer = ExperimentDesigner()
        exp = designer.create_experiment("ndl-no-data", "desc", "hyp")
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(AssertionType.NO_DATA_LOSS)],
        )
        result = designer.run_experiment(exp, graph)
        assert len(result.passed_assertions) == 1


# ---------------------------------------------------------------------------
# Test: Validation
# ---------------------------------------------------------------------------

class TestValidation:

    def test_valid_experiment(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("valid-exp", "desc", "hyp")
        designer.add_step(
            exp, ExperimentPhase.INJECT,
            actions=[ExperimentAction(ActionType.KILL_COMPONENT, "app")],
        )
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(AssertionType.HEALTH_CHECK)],
        )
        exp.rollback_plan = [ExperimentAction(ActionType.FAILOVER_TRIGGER, "app")]
        exp.blast_radius_limit = 10
        errors = designer.validate_experiment(exp, graph)
        assert errors == []

    def test_missing_verify_step(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("no-verify", "desc", "hyp")
        designer.add_step(exp, ExperimentPhase.SETUP)
        designer.add_step(
            exp, ExperimentPhase.INJECT,
            actions=[ExperimentAction(ActionType.KILL_COMPONENT, "app")],
        )
        exp.rollback_plan = [ExperimentAction(ActionType.FAILOVER_TRIGGER, "app")]
        errors = designer.validate_experiment(exp, graph)
        assert any("VERIFY" in e for e in errors)

    def test_nonexistent_action_target(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("bad-target", "desc", "hyp")
        designer.add_step(
            exp, ExperimentPhase.INJECT,
            actions=[ExperimentAction(ActionType.KILL_COMPONENT, "nonexistent")],
        )
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(AssertionType.HEALTH_CHECK)],
        )
        exp.rollback_plan = [ExperimentAction(ActionType.FAILOVER_TRIGGER, "nonexistent")]
        errors = designer.validate_experiment(exp, graph)
        assert any("nonexistent" in e for e in errors)

    def test_nonexistent_assertion_target(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("bad-assert-target", "desc", "hyp")
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(AssertionType.HEALTH_CHECK, "nonexistent")],
        )
        errors = designer.validate_experiment(exp, graph)
        assert any("nonexistent" in e for e in errors)

    def test_assertion_target_none_is_valid(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("none-target", "desc", "hyp")
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(AssertionType.HEALTH_CHECK, None)],
        )
        errors = designer.validate_experiment(exp, graph)
        assert errors == []

    def test_blast_radius_exceeded(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("blast-exceed", "desc", "hyp")
        # db is depended on by app, which is depended on by lb
        designer.add_step(
            exp, ExperimentPhase.INJECT,
            actions=[ExperimentAction(ActionType.KILL_COMPONENT, "db")],
        )
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(AssertionType.HEALTH_CHECK)],
        )
        exp.blast_radius_limit = 1  # Very restrictive
        exp.rollback_plan = [ExperimentAction(ActionType.FAILOVER_TRIGGER, "db")]
        errors = designer.validate_experiment(exp, graph)
        assert any("blast radius" in e.lower() for e in errors)

    def test_blast_radius_within_limit(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("blast-ok", "desc", "hyp")
        designer.add_step(
            exp, ExperimentPhase.INJECT,
            actions=[ExperimentAction(ActionType.KILL_COMPONENT, "cache")],
        )
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(AssertionType.HEALTH_CHECK)],
        )
        exp.blast_radius_limit = 10
        exp.rollback_plan = [ExperimentAction(ActionType.FAILOVER_TRIGGER, "cache")]
        errors = designer.validate_experiment(exp, graph)
        assert not any("blast radius" in e.lower() for e in errors)

    def test_uncovered_rollback(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("no-rollback", "desc", "hyp")
        designer.add_step(
            exp, ExperimentPhase.INJECT,
            actions=[
                ExperimentAction(ActionType.KILL_COMPONENT, "app"),
                ExperimentAction(ActionType.KILL_COMPONENT, "db"),
            ],
        )
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(AssertionType.HEALTH_CHECK)],
        )
        # Only rollback for app, not db
        exp.rollback_plan = [ExperimentAction(ActionType.FAILOVER_TRIGGER, "app")]
        exp.blast_radius_limit = 20
        errors = designer.validate_experiment(exp, graph)
        assert any("rollback" in e.lower() for e in errors)
        assert any("db" in e for e in errors)

    def test_rollback_via_rollback_step(self):
        """Rollback covered via a ROLLBACK phase step should be valid."""
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("rollback-step", "desc", "hyp")
        designer.add_step(
            exp, ExperimentPhase.INJECT,
            actions=[ExperimentAction(ActionType.KILL_COMPONENT, "app")],
        )
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(AssertionType.HEALTH_CHECK)],
        )
        designer.add_step(
            exp, ExperimentPhase.ROLLBACK,
            actions=[ExperimentAction(ActionType.FAILOVER_TRIGGER, "app")],
        )
        exp.blast_radius_limit = 20
        errors = designer.validate_experiment(exp, graph)
        assert not any("rollback" in e.lower() for e in errors)

    def test_nonexistent_rollback_target(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("bad-rollback-target", "desc", "hyp")
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(AssertionType.HEALTH_CHECK)],
        )
        exp.rollback_plan = [ExperimentAction(ActionType.FAILOVER_TRIGGER, "nonexistent")]
        errors = designer.validate_experiment(exp, graph)
        assert any("nonexistent" in e for e in errors)

    def test_multiple_validation_errors(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("multi-error", "desc", "hyp")
        # No verify step, nonexistent target, no rollback
        designer.add_step(
            exp, ExperimentPhase.INJECT,
            actions=[ExperimentAction(ActionType.KILL_COMPONENT, "nonexistent")],
        )
        errors = designer.validate_experiment(exp, graph)
        assert len(errors) >= 2  # At least: no VERIFY + nonexistent target


# ---------------------------------------------------------------------------
# Test: Running experiments (passing and failing)
# ---------------------------------------------------------------------------

class TestRunExperiment:

    def test_run_passing_experiment(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("pass-exp", "desc", "hyp")
        designer.add_step(
            exp, ExperimentPhase.SETUP,
            assertions=[ExperimentAssertion(AssertionType.HEALTH_CHECK, None)],
            description="Verify all healthy",
        )
        designer.add_step(exp, ExperimentPhase.VERIFY,
            assertions=[
                ExperimentAssertion(AssertionType.HEALTH_CHECK, None),
                ExperimentAssertion(AssertionType.AVAILABILITY_ABOVE, threshold=50.0),
            ],
        )
        result = designer.run_experiment(exp, graph)
        assert result.conclusion.startswith("PASSED")
        assert result.risk_score == 0.0
        assert len(result.failed_assertions) == 0

    def test_run_failing_experiment(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("fail-exp", "desc", "hyp")
        designer.add_step(
            exp, ExperimentPhase.INJECT,
            actions=[
                ExperimentAction(ActionType.KILL_COMPONENT, "app"),
                ExperimentAction(ActionType.KILL_COMPONENT, "db"),
            ],
        )
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[
                ExperimentAssertion(AssertionType.HEALTH_CHECK, None),
                ExperimentAssertion(AssertionType.ERROR_RATE_BELOW, threshold=1.0),
            ],
        )
        exp.rollback_plan = [
            ExperimentAction(ActionType.FAILOVER_TRIGGER, "app"),
            ExperimentAction(ActionType.FAILOVER_TRIGGER, "db"),
        ]
        result = designer.run_experiment(exp, graph)
        assert "FAILED" in result.conclusion
        assert result.risk_score > 0.0
        assert len(result.failed_assertions) > 0

    def test_run_partial_experiment(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("partial-exp", "desc", "hyp")
        designer.add_step(
            exp, ExperimentPhase.INJECT,
            actions=[ExperimentAction(ActionType.KILL_COMPONENT, "cache")],
        )
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[
                ExperimentAssertion(AssertionType.HEALTH_CHECK, "cache"),  # Will fail
                ExperimentAssertion(AssertionType.HEALTH_CHECK, "db"),    # Will pass
                ExperimentAssertion(AssertionType.AVAILABILITY_ABOVE, threshold=50.0),  # Will pass
            ],
        )
        exp.rollback_plan = [ExperimentAction(ActionType.FAILOVER_TRIGGER, "cache")]
        result = designer.run_experiment(exp, graph)
        assert "PARTIAL" in result.conclusion
        assert len(result.passed_assertions) > 0
        assert len(result.failed_assertions) > 0

    def test_run_experiment_with_observe_step(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("observe-exp", "desc", "hyp")
        designer.add_step(exp, ExperimentPhase.OBSERVE, wait_seconds=10, description="Observe")
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(AssertionType.HEALTH_CHECK)],
        )
        result = designer.run_experiment(exp, graph)
        assert any("OBSERVE" in o for o in result.observations)

    def test_run_experiment_with_rollback_step(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("rollback-exp", "desc", "hyp")
        designer.add_step(
            exp, ExperimentPhase.INJECT,
            actions=[ExperimentAction(ActionType.KILL_COMPONENT, "app")],
        )
        designer.add_step(
            exp, ExperimentPhase.ROLLBACK,
            actions=[ExperimentAction(ActionType.FAILOVER_TRIGGER, "app")],
            description="Restore app",
        )
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(AssertionType.HEALTH_CHECK, "app")],
        )
        exp.rollback_plan = [ExperimentAction(ActionType.FAILOVER_TRIGGER, "app")]
        result = designer.run_experiment(exp, graph)
        assert any("ROLLBACK" in o for o in result.observations)

    def test_run_experiment_empty_rollback_restores_all(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("empty-rollback", "desc", "hyp")
        designer.add_step(
            exp, ExperimentPhase.INJECT,
            actions=[ExperimentAction(ActionType.KILL_COMPONENT, "app")],
        )
        designer.add_step(exp, ExperimentPhase.ROLLBACK, description="Restore all")
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(AssertionType.HEALTH_CHECK, "app")],
        )
        exp.rollback_plan = [ExperimentAction(ActionType.FAILOVER_TRIGGER, "app")]
        result = designer.run_experiment(exp, graph)
        # After rollback with no actions, all components should be restored
        assert len(result.passed_assertions) == 1

    def test_run_does_not_modify_original_graph(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("no-mutate", "desc", "hyp")
        designer.add_step(
            exp, ExperimentPhase.INJECT,
            actions=[ExperimentAction(ActionType.KILL_COMPONENT, "app")],
        )
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(AssertionType.HEALTH_CHECK)],
        )
        exp.rollback_plan = [ExperimentAction(ActionType.FAILOVER_TRIGGER, "app")]
        designer.run_experiment(exp, graph)
        # Original graph should be untouched
        assert graph.get_component("app").health == HealthStatus.HEALTHY

    def test_run_experiment_no_assertions(self):
        """Experiment with no assertions should have unknown risk."""
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("no-assert", "desc", "hyp")
        designer.add_step(exp, ExperimentPhase.OBSERVE)
        # No VERIFY step, but still runnable
        result = designer.run_experiment(exp, graph)
        assert result.risk_score == 5.0

    def test_inject_on_nonexistent_target_skips(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("inject-missing", "desc", "hyp")
        designer.add_step(
            exp, ExperimentPhase.INJECT,
            actions=[ExperimentAction(ActionType.KILL_COMPONENT, "nonexistent")],
        )
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(AssertionType.HEALTH_CHECK)],
        )
        result = designer.run_experiment(exp, graph)
        assert any("not found" in o.lower() for o in result.observations)

    def test_run_experiment_with_top_level_rollback_plan(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("top-rollback", "desc", "hyp")
        designer.add_step(
            exp, ExperimentPhase.INJECT,
            actions=[ExperimentAction(ActionType.KILL_COMPONENT, "app")],
        )
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(AssertionType.HEALTH_CHECK, "app")],
        )
        exp.rollback_plan = [ExperimentAction(ActionType.FAILOVER_TRIGGER, "app")]
        result = designer.run_experiment(exp, graph)
        assert any("Rollback plan executed" in o for o in result.observations)

    def test_setup_phase_records_observations(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("setup-obs", "desc", "hyp")
        designer.add_step(exp, ExperimentPhase.SETUP, description="Initial setup")
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(AssertionType.HEALTH_CHECK)],
        )
        result = designer.run_experiment(exp, graph)
        assert any("SETUP" in o for o in result.observations)

    def test_setup_with_assertion(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("setup-assert", "desc", "hyp")
        designer.add_step(
            exp, ExperimentPhase.SETUP,
            assertions=[ExperimentAssertion(AssertionType.HEALTH_CHECK, None, description="Precondition")],
        )
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(AssertionType.HEALTH_CHECK)],
        )
        result = designer.run_experiment(exp, graph)
        # Both setup and verify assertions should pass
        assert len(result.passed_assertions) == 2


# ---------------------------------------------------------------------------
# Test: Built-in templates
# ---------------------------------------------------------------------------

class TestTemplates:

    def test_list_templates(self):
        designer = ExperimentDesigner()
        templates = designer.list_templates()
        assert len(templates) >= 8
        keys = [t["key"] for t in templates]
        assert "zone-failure" in keys
        assert "database-failover" in keys
        assert "cache-stampede" in keys
        assert "network-partition" in keys
        assert "cascading-failure" in keys
        assert "traffic-spike" in keys
        assert "dependency-timeout" in keys
        assert "data-corruption" in keys

    def test_list_templates_structure(self):
        designer = ExperimentDesigner()
        templates = designer.list_templates()
        for t in templates:
            assert "key" in t
            assert "name" in t
            assert "description" in t
            assert "hypothesis" in t
            assert t["name"] != ""
            assert t["description"] != ""

    def test_from_template_zone_failure(self):
        designer = ExperimentDesigner()
        exp = designer.from_template("zone-failure")
        assert exp.name == "Zone Failure"
        assert len(exp.steps) > 0
        assert any(s.phase == ExperimentPhase.VERIFY for s in exp.steps)
        assert len(exp.rollback_plan) > 0

    def test_from_template_database_failover(self):
        designer = ExperimentDesigner()
        exp = designer.from_template("database-failover")
        assert exp.name == "Database Failover"
        assert len(exp.steps) >= 4

    def test_from_template_cache_stampede(self):
        designer = ExperimentDesigner()
        exp = designer.from_template("cache-stampede")
        assert exp.name == "Cache Stampede"
        assert any(
            any(a.action_type == ActionType.KILL_COMPONENT for a in s.actions)
            for s in exp.steps
        )

    def test_from_template_network_partition(self):
        designer = ExperimentDesigner()
        exp = designer.from_template("network-partition")
        assert exp.name == "Network Partition"
        assert any(
            any(a.action_type == ActionType.PARTITION_NETWORK for a in s.actions)
            for s in exp.steps
        )

    def test_from_template_cascading_failure(self):
        designer = ExperimentDesigner()
        exp = designer.from_template("cascading-failure")
        assert exp.name == "Cascading Failure"
        assert any(
            any(a.assertion_type == AssertionType.CASCADE_CONTAINED for a in s.assertions)
            for s in exp.steps
        )

    def test_from_template_traffic_spike(self):
        designer = ExperimentDesigner()
        exp = designer.from_template("traffic-spike")
        assert exp.name == "Traffic Spike"
        assert any(
            any(a.action_type == ActionType.SPIKE_TRAFFIC for a in s.actions)
            for s in exp.steps
        )

    def test_from_template_dependency_timeout(self):
        designer = ExperimentDesigner()
        exp = designer.from_template("dependency-timeout")
        assert exp.name == "Dependency Timeout"
        assert any(
            any(a.action_type == ActionType.DELAY_RESPONSES for a in s.actions)
            for s in exp.steps
        )

    def test_from_template_data_corruption(self):
        designer = ExperimentDesigner()
        exp = designer.from_template("data-corruption")
        assert exp.name == "Data Corruption"
        assert any(
            any(a.action_type == ActionType.CORRUPT_DATA for a in s.actions)
            for s in exp.steps
        )

    def test_from_template_unknown_raises(self):
        designer = ExperimentDesigner()
        with pytest.raises(ValueError, match="Unknown template"):
            designer.from_template("nonexistent-template")

    def test_template_has_created_at(self):
        designer = ExperimentDesigner()
        exp = designer.from_template("zone-failure")
        assert exp.created_at != ""

    def test_template_prevents_duplicate_names(self):
        designer = ExperimentDesigner()
        designer.from_template("zone-failure")
        # Creating again with the same template name should clash
        with pytest.raises(ValueError, match="Duplicate"):
            designer.create_experiment("Zone Failure", "desc", "hyp")

    def test_resolve_template_targets(self):
        designer = ExperimentDesigner()
        graph = _build_large_graph()
        exp = designer.from_template("database-failover")
        exp = designer.resolve_template_targets(exp, graph)
        # All placeholders should be resolved
        for step in exp.steps:
            for action in step.actions:
                assert not action.target_component_id.startswith("__")
            for assertion in step.assertions:
                if assertion.target_component_id is not None:
                    assert not assertion.target_component_id.startswith("__")

    def test_resolve_template_targets_rollback(self):
        designer = ExperimentDesigner()
        graph = _build_large_graph()
        exp = designer.from_template("zone-failure")
        exp = designer.resolve_template_targets(exp, graph)
        for action in exp.rollback_plan:
            assert not action.target_component_id.startswith("__")

    def test_resolve_unresolvable_placeholder(self):
        """If graph has no matching component type, placeholder stays."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER, replicas=1,
        ))
        designer = ExperimentDesigner()
        exp = designer.from_template("database-failover")
        exp = designer.resolve_template_targets(exp, graph)
        # DB placeholder should remain since there's no DB in the graph
        has_placeholder = False
        for step in exp.steps:
            for action in step.actions:
                if action.target_component_id.startswith("__"):
                    has_placeholder = True
        assert has_placeholder


# ---------------------------------------------------------------------------
# Test: Export / Import round-trip
# ---------------------------------------------------------------------------

class TestExportImport:

    def test_export_basic(self):
        designer = ExperimentDesigner()
        exp = designer.create_experiment("export-test", "A test", "Should work")
        data = designer.export_experiment(exp)
        assert data["name"] == "export-test"
        assert data["description"] == "A test"
        assert data["hypothesis"] == "Should work"
        assert isinstance(data["steps"], list)
        assert isinstance(data["rollback_plan"], list)

    def test_export_is_json_serializable(self):
        designer = ExperimentDesigner()
        exp = designer.create_experiment("json-test", "desc", "hyp")
        designer.add_step(
            exp, ExperimentPhase.INJECT,
            actions=[ExperimentAction(
                ActionType.KILL_COMPONENT, "app",
                parameters={"reason": "test"}, duration_seconds=60,
            )],
        )
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(
                AssertionType.HEALTH_CHECK, "app",
                threshold=1.0, description="Check app",
            )],
        )
        exp.rollback_plan = [ExperimentAction(ActionType.FAILOVER_TRIGGER, "app")]
        data = designer.export_experiment(exp)
        # Should not raise
        json_str = json.dumps(data)
        assert len(json_str) > 0

    def test_import_basic(self):
        designer = ExperimentDesigner()
        data = {
            "name": "imported-exp",
            "description": "An imported experiment",
            "hypothesis": "Hypothesis",
            "tags": ["test", "import"],
            "blast_radius_limit": 7,
            "created_at": "2025-01-01T00:00:00Z",
            "steps": [
                {
                    "phase": "verify",
                    "description": "Verify step",
                    "wait_seconds": 0,
                    "actions": [],
                    "assertions": [
                        {
                            "assertion_type": "health_check",
                            "target_component_id": None,
                            "threshold": 1.0,
                            "description": "All healthy",
                        }
                    ],
                }
            ],
            "rollback_plan": [],
        }
        exp = designer.import_experiment(data)
        assert exp.name == "imported-exp"
        assert exp.tags == ["test", "import"]
        assert exp.blast_radius_limit == 7
        assert len(exp.steps) == 1
        assert exp.steps[0].phase == ExperimentPhase.VERIFY

    def test_round_trip(self):
        designer = ExperimentDesigner()
        exp = designer.create_experiment("roundtrip", "A round-trip test", "Should survive")
        exp.tags = ["test", "roundtrip"]
        exp.blast_radius_limit = 8
        designer.add_step(
            exp, ExperimentPhase.SETUP,
            assertions=[ExperimentAssertion(AssertionType.HEALTH_CHECK, None, 1.0, "Healthy")],
            description="Setup step",
        )
        designer.add_step(
            exp, ExperimentPhase.INJECT,
            actions=[ExperimentAction(
                ActionType.KILL_COMPONENT, "app",
                parameters={"reason": "test"}, duration_seconds=120,
            )],
            wait_seconds=5,
            description="Kill app",
        )
        designer.add_step(
            exp, ExperimentPhase.OBSERVE,
            wait_seconds=30,
            description="Observe",
        )
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[
                ExperimentAssertion(AssertionType.AVAILABILITY_ABOVE, None, 50.0, "Availability"),
                ExperimentAssertion(AssertionType.ERROR_RATE_BELOW, None, 10.0, "Error rate"),
            ],
            description="Verify",
        )
        exp.rollback_plan = [
            ExperimentAction(ActionType.FAILOVER_TRIGGER, "app", {"restore": True}, 0),
        ]

        exported = designer.export_experiment(exp)

        # Use a new designer for import to avoid name clash
        designer2 = ExperimentDesigner()
        imported = designer2.import_experiment(exported)

        assert imported.name == exp.name
        assert imported.description == exp.description
        assert imported.hypothesis == exp.hypothesis
        assert imported.tags == exp.tags
        assert imported.blast_radius_limit == exp.blast_radius_limit
        assert len(imported.steps) == len(exp.steps)
        for orig_step, imp_step in zip(exp.steps, imported.steps):
            assert orig_step.phase == imp_step.phase
            assert orig_step.description == imp_step.description
            assert orig_step.wait_seconds == imp_step.wait_seconds
            assert len(orig_step.actions) == len(imp_step.actions)
            assert len(orig_step.assertions) == len(imp_step.assertions)
        assert len(imported.rollback_plan) == len(exp.rollback_plan)

    def test_round_trip_all_templates(self):
        """All templates should survive export/import round-trip."""
        for template_key in [
            "zone-failure", "database-failover", "cache-stampede",
            "network-partition", "cascading-failure", "traffic-spike",
            "dependency-timeout", "data-corruption",
        ]:
            designer1 = ExperimentDesigner()
            exp = designer1.from_template(template_key)
            exported = designer1.export_experiment(exp)
            json_str = json.dumps(exported)
            data = json.loads(json_str)
            designer2 = ExperimentDesigner()
            imported = designer2.import_experiment(data)
            assert imported.name == exp.name
            assert len(imported.steps) == len(exp.steps)

    def test_import_prevents_duplicate_names(self):
        designer = ExperimentDesigner()
        designer.create_experiment("dup-import", "desc", "hyp")
        data = {
            "name": "dup-import",
            "description": "duplicate",
            "hypothesis": "hyp",
            "steps": [{"phase": "verify", "description": "", "wait_seconds": 0, "actions": [], "assertions": []}],
            "rollback_plan": [],
        }
        with pytest.raises(ValueError, match="Duplicate"):
            designer.import_experiment(data)

    def test_export_with_empty_steps(self):
        designer = ExperimentDesigner()
        exp = designer.create_experiment("empty-export", "desc", "hyp")
        data = designer.export_experiment(exp)
        assert data["steps"] == []
        assert data["rollback_plan"] == []


# ---------------------------------------------------------------------------
# Test: Report generation
# ---------------------------------------------------------------------------

class TestReportGeneration:

    def test_generate_report_basic(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("report-test", "desc", "hyp")
        exp.tags = ["test"]
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(AssertionType.HEALTH_CHECK, description="All healthy")],
        )
        result = designer.run_experiment(exp, graph)
        report = designer.generate_report(result)
        assert "# Chaos Experiment Report: report-test" in report
        assert "hyp" in report
        assert "desc" in report

    def test_report_contains_conclusion(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("report-conclusion", "desc", "hyp")
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(AssertionType.HEALTH_CHECK)],
        )
        result = designer.run_experiment(exp, graph)
        report = designer.generate_report(result)
        assert "## Conclusion" in report
        assert "Risk Score" in report

    def test_report_contains_passed_assertions(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("report-passed", "desc", "hyp")
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(AssertionType.HEALTH_CHECK, description="All healthy")],
        )
        result = designer.run_experiment(exp, graph)
        report = designer.generate_report(result)
        assert "### Passed" in report
        assert "[PASS]" in report

    def test_report_contains_failed_assertions(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("report-failed", "desc", "hyp")
        designer.add_step(
            exp, ExperimentPhase.INJECT,
            actions=[ExperimentAction(ActionType.KILL_COMPONENT, "app")],
        )
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(
                AssertionType.HEALTH_CHECK, "app", description="App healthy",
            )],
        )
        exp.rollback_plan = [ExperimentAction(ActionType.FAILOVER_TRIGGER, "app")]
        result = designer.run_experiment(exp, graph)
        report = designer.generate_report(result)
        assert "### Failed" in report
        assert "[FAIL]" in report

    def test_report_contains_steps(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("report-steps", "desc", "hyp")
        designer.add_step(exp, ExperimentPhase.SETUP, description="Setup phase")
        designer.add_step(exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(AssertionType.HEALTH_CHECK)],
            description="Verify phase",
        )
        result = designer.run_experiment(exp, graph)
        report = designer.generate_report(result)
        assert "## Experiment Steps" in report
        assert "SETUP" in report
        assert "VERIFY" in report

    def test_report_contains_observations(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("report-obs", "desc", "hyp")
        designer.add_step(exp, ExperimentPhase.SETUP, description="Setup")
        designer.add_step(exp, ExperimentPhase.OBSERVE, wait_seconds=10, description="Observe")
        designer.add_step(exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(AssertionType.HEALTH_CHECK)],
        )
        result = designer.run_experiment(exp, graph)
        report = designer.generate_report(result)
        assert "## Observations" in report

    def test_report_contains_rollback_plan(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("report-rollback", "desc", "hyp")
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(AssertionType.HEALTH_CHECK)],
        )
        exp.rollback_plan = [ExperimentAction(ActionType.FAILOVER_TRIGGER, "app")]
        result = designer.run_experiment(exp, graph)
        report = designer.generate_report(result)
        assert "## Rollback Plan" in report

    def test_report_contains_tags(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("report-tags", "desc", "hyp")
        exp.tags = ["ha", "resilience"]
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(AssertionType.HEALTH_CHECK)],
        )
        result = designer.run_experiment(exp, graph)
        report = designer.generate_report(result)
        assert "ha" in report
        assert "resilience" in report

    def test_report_no_tags(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("report-no-tags", "desc", "hyp")
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(AssertionType.HEALTH_CHECK)],
        )
        result = designer.run_experiment(exp, graph)
        report = designer.generate_report(result)
        assert "**Tags:**" not in report

    def test_report_with_wait_seconds(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("report-wait", "desc", "hyp")
        designer.add_step(exp, ExperimentPhase.OBSERVE, wait_seconds=30, description="Wait")
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(AssertionType.HEALTH_CHECK)],
        )
        result = designer.run_experiment(exp, graph)
        report = designer.generate_report(result)
        assert "30s" in report


# ---------------------------------------------------------------------------
# Test: Blast radius limit enforcement
# ---------------------------------------------------------------------------

class TestBlastRadiusLimit:

    def test_blast_radius_default(self):
        exp = ExperimentDesign(name="default", description="", hypothesis="")
        assert exp.blast_radius_limit == 5

    def test_blast_radius_custom(self):
        exp = ExperimentDesign(name="custom", description="", hypothesis="", blast_radius_limit=20)
        assert exp.blast_radius_limit == 20

    def test_blast_radius_validation_with_large_graph(self):
        designer = ExperimentDesigner()
        graph = _build_large_graph()
        exp = designer.create_experiment("blast-large", "desc", "hyp")
        # Killing db affects all 5 app servers and lb (6 affected + db = 7)
        designer.add_step(
            exp, ExperimentPhase.INJECT,
            actions=[ExperimentAction(ActionType.KILL_COMPONENT, "db")],
        )
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(AssertionType.HEALTH_CHECK)],
        )
        exp.blast_radius_limit = 2  # Very small limit
        exp.rollback_plan = [ExperimentAction(ActionType.FAILOVER_TRIGGER, "db")]
        errors = designer.validate_experiment(exp, graph)
        assert any("blast radius" in e.lower() for e in errors)

    def test_blast_radius_validation_passes_with_high_limit(self):
        designer = ExperimentDesigner()
        graph = _build_large_graph()
        exp = designer.create_experiment("blast-high", "desc", "hyp")
        designer.add_step(
            exp, ExperimentPhase.INJECT,
            actions=[ExperimentAction(ActionType.KILL_COMPONENT, "db")],
        )
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(AssertionType.HEALTH_CHECK)],
        )
        exp.blast_radius_limit = 50
        exp.rollback_plan = [ExperimentAction(ActionType.FAILOVER_TRIGGER, "db")]
        errors = designer.validate_experiment(exp, graph)
        assert not any("blast radius" in e.lower() for e in errors)

    def test_blast_radius_multiple_inject_targets(self):
        designer = ExperimentDesigner()
        graph = _build_large_graph()
        exp = designer.create_experiment("blast-multi", "desc", "hyp")
        designer.add_step(
            exp, ExperimentPhase.INJECT,
            actions=[
                ExperimentAction(ActionType.KILL_COMPONENT, "db"),
                ExperimentAction(ActionType.KILL_COMPONENT, "cache"),
            ],
        )
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(AssertionType.HEALTH_CHECK)],
        )
        exp.blast_radius_limit = 3  # Very small
        exp.rollback_plan = [
            ExperimentAction(ActionType.FAILOVER_TRIGGER, "db"),
            ExperimentAction(ActionType.FAILOVER_TRIGGER, "cache"),
        ]
        errors = designer.validate_experiment(exp, graph)
        assert any("blast radius" in e.lower() for e in errors)


# ---------------------------------------------------------------------------
# Test: Rollback plan validation
# ---------------------------------------------------------------------------

class TestRollbackPlanValidation:

    def test_complete_rollback_plan(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("rollback-complete", "desc", "hyp")
        designer.add_step(
            exp, ExperimentPhase.INJECT,
            actions=[
                ExperimentAction(ActionType.KILL_COMPONENT, "app"),
                ExperimentAction(ActionType.KILL_COMPONENT, "db"),
            ],
        )
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(AssertionType.HEALTH_CHECK)],
        )
        exp.rollback_plan = [
            ExperimentAction(ActionType.FAILOVER_TRIGGER, "app"),
            ExperimentAction(ActionType.FAILOVER_TRIGGER, "db"),
        ]
        exp.blast_radius_limit = 20
        errors = designer.validate_experiment(exp, graph)
        assert not any("rollback" in e.lower() for e in errors)

    def test_partial_rollback_plan(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("rollback-partial", "desc", "hyp")
        designer.add_step(
            exp, ExperimentPhase.INJECT,
            actions=[
                ExperimentAction(ActionType.KILL_COMPONENT, "app"),
                ExperimentAction(ActionType.KILL_COMPONENT, "db"),
            ],
        )
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(AssertionType.HEALTH_CHECK)],
        )
        # Only covers app, not db
        exp.rollback_plan = [ExperimentAction(ActionType.FAILOVER_TRIGGER, "app")]
        exp.blast_radius_limit = 20
        errors = designer.validate_experiment(exp, graph)
        assert any("rollback" in e.lower() and "db" in e for e in errors)

    def test_empty_rollback_when_no_inject(self):
        """No inject actions means no rollback needed."""
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("no-inject-rollback", "desc", "hyp")
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(AssertionType.HEALTH_CHECK)],
        )
        errors = designer.validate_experiment(exp, graph)
        assert not any("rollback" in e.lower() for e in errors)


# ---------------------------------------------------------------------------
# Test: Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:

    def test_empty_graph(self):
        """Experiment on empty graph should handle gracefully."""
        designer = ExperimentDesigner()
        graph = InfraGraph()
        exp = designer.create_experiment("empty-graph", "desc", "hyp")
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(AssertionType.HEALTH_CHECK)],
        )
        result = designer.run_experiment(exp, graph)
        # With zero components, all-component health check should pass (vacuously)
        assert isinstance(result, ExperimentResult)

    def test_empty_steps(self):
        """Experiment with no steps should run without error."""
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("empty-steps", "desc", "hyp")
        result = designer.run_experiment(exp, graph)
        assert result.risk_score == 5.0  # Unknown risk when no assertions
        assert result.conclusion.startswith("PASSED")

    def test_experiment_with_only_observe(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("only-observe", "desc", "hyp")
        designer.add_step(exp, ExperimentPhase.OBSERVE, wait_seconds=5)
        result = designer.run_experiment(exp, graph)
        assert len(result.observations) > 0

    def test_experiment_design_defaults(self):
        exp = ExperimentDesign(name="defaults", description="", hypothesis="")
        assert exp.steps == []
        assert exp.tags == []
        assert exp.blast_radius_limit == 5
        assert exp.rollback_plan == []
        assert exp.created_at == ""

    def test_experiment_result_defaults(self):
        exp = ExperimentDesign(name="result-defaults", description="", hypothesis="")
        result = ExperimentResult(design=exp)
        assert result.passed_assertions == []
        assert result.failed_assertions == []
        assert result.observations == []
        assert result.conclusion == ""
        assert result.risk_score == 0.0

    def test_experiment_step_defaults(self):
        step = ExperimentStep(phase=ExperimentPhase.OBSERVE)
        assert step.actions == []
        assert step.assertions == []
        assert step.wait_seconds == 0
        assert step.description == ""

    def test_experiment_action_defaults(self):
        action = ExperimentAction(
            action_type=ActionType.KILL_COMPONENT,
            target_component_id="test",
        )
        assert action.parameters == {}
        assert action.duration_seconds == 60

    def test_experiment_assertion_defaults(self):
        assertion = ExperimentAssertion(assertion_type=AssertionType.HEALTH_CHECK)
        assert assertion.target_component_id is None
        assert assertion.threshold == 0.0
        assert assertion.description == ""

    def test_multiple_designers_independent(self):
        """Different designer instances should have independent name tracking."""
        d1 = ExperimentDesigner()
        d2 = ExperimentDesigner()
        d1.create_experiment("shared-name", "desc", "hyp")
        # d2 should be able to create the same name
        exp2 = d2.create_experiment("shared-name", "desc", "hyp")
        assert exp2.name == "shared-name"

    def test_single_component_graph(self):
        graph = InfraGraph()
        graph.add_component(Component(
            id="solo", name="Solo App", type=ComponentType.APP_SERVER, replicas=1,
        ))
        designer = ExperimentDesigner()
        exp = designer.create_experiment("single-comp", "desc", "hyp")
        designer.add_step(
            exp, ExperimentPhase.INJECT,
            actions=[ExperimentAction(ActionType.KILL_COMPONENT, "solo")],
        )
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(AssertionType.AVAILABILITY_ABOVE, threshold=0.0)],
        )
        exp.rollback_plan = [ExperimentAction(ActionType.FAILOVER_TRIGGER, "solo")]
        exp.blast_radius_limit = 10
        errors = designer.validate_experiment(exp, graph)
        assert errors == []
        result = designer.run_experiment(exp, graph)
        assert isinstance(result, ExperimentResult)

    def test_inject_multiple_actions_same_step(self):
        designer = ExperimentDesigner()
        graph = _build_simple_graph()
        exp = designer.create_experiment("multi-inject", "desc", "hyp")
        designer.add_step(
            exp, ExperimentPhase.INJECT,
            actions=[
                ExperimentAction(ActionType.KILL_COMPONENT, "app"),
                ExperimentAction(ActionType.DEGRADE_COMPONENT, "db"),
                ExperimentAction(ActionType.EXHAUST_RESOURCES, "cache"),
            ],
        )
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[ExperimentAssertion(AssertionType.HEALTH_CHECK)],
        )
        exp.rollback_plan = [
            ExperimentAction(ActionType.FAILOVER_TRIGGER, "app"),
            ExperimentAction(ActionType.FAILOVER_TRIGGER, "db"),
            ExperimentAction(ActionType.FAILOVER_TRIGGER, "cache"),
        ]
        result = designer.run_experiment(exp, graph)
        assert len(result.observations) > 3  # multiple inject observations


# ---------------------------------------------------------------------------
# Test: Experiment phases enum
# ---------------------------------------------------------------------------

class TestEnums:

    def test_experiment_phase_values(self):
        assert ExperimentPhase.SETUP.value == "setup"
        assert ExperimentPhase.INJECT.value == "inject"
        assert ExperimentPhase.OBSERVE.value == "observe"
        assert ExperimentPhase.VERIFY.value == "verify"
        assert ExperimentPhase.ROLLBACK.value == "rollback"

    def test_action_type_values(self):
        assert ActionType.KILL_COMPONENT.value == "kill_component"
        assert ActionType.DEGRADE_COMPONENT.value == "degrade_component"
        assert ActionType.SPIKE_TRAFFIC.value == "spike_traffic"
        assert ActionType.PARTITION_NETWORK.value == "partition_network"
        assert ActionType.CORRUPT_DATA.value == "corrupt_data"
        assert ActionType.DELAY_RESPONSES.value == "delay_responses"
        assert ActionType.EXHAUST_RESOURCES.value == "exhaust_resources"
        assert ActionType.FAILOVER_TRIGGER.value == "failover_trigger"

    def test_assertion_type_values(self):
        assert AssertionType.HEALTH_CHECK.value == "health_check"
        assert AssertionType.LATENCY_BELOW.value == "latency_below"
        assert AssertionType.ERROR_RATE_BELOW.value == "error_rate_below"
        assert AssertionType.AVAILABILITY_ABOVE.value == "availability_above"
        assert AssertionType.RECOVERY_WITHIN.value == "recovery_within"
        assert AssertionType.CASCADE_CONTAINED.value == "cascade_contained"
        assert AssertionType.NO_DATA_LOSS.value == "no_data_loss"


# ---------------------------------------------------------------------------
# Test: Full end-to-end scenarios
# ---------------------------------------------------------------------------

class TestEndToEnd:

    def test_full_workflow_create_validate_run_report(self):
        """Complete workflow: create, add steps, validate, run, report."""
        designer = ExperimentDesigner()
        graph = _build_simple_graph()

        # Create
        exp = designer.create_experiment(
            "e2e-test",
            "End to end test",
            "System should survive cache loss",
        )
        exp.tags = ["e2e", "cache"]
        exp.blast_radius_limit = 10

        # Add steps
        designer.add_step(
            exp, ExperimentPhase.SETUP,
            assertions=[ExperimentAssertion(AssertionType.HEALTH_CHECK, None, description="Precondition check")],
            description="Verify preconditions",
        )
        designer.add_step(
            exp, ExperimentPhase.INJECT,
            actions=[ExperimentAction(ActionType.KILL_COMPONENT, "cache", duration_seconds=120)],
            wait_seconds=5,
            description="Kill cache",
        )
        designer.add_step(
            exp, ExperimentPhase.OBSERVE,
            wait_seconds=30,
            description="Observe system behaviour",
        )
        designer.add_step(
            exp, ExperimentPhase.VERIFY,
            assertions=[
                ExperimentAssertion(AssertionType.HEALTH_CHECK, "db", description="DB still alive"),
                ExperimentAssertion(AssertionType.AVAILABILITY_ABOVE, threshold=50.0, description="System available"),
                ExperimentAssertion(AssertionType.ERROR_RATE_BELOW, threshold=50.0, description="Acceptable error rate"),
            ],
            description="Verify resilience",
        )
        designer.add_step(
            exp, ExperimentPhase.ROLLBACK,
            description="Restore cache",
        )
        exp.rollback_plan = [ExperimentAction(ActionType.FAILOVER_TRIGGER, "cache")]

        # Validate
        errors = designer.validate_experiment(exp, graph)
        assert errors == [], f"Validation errors: {errors}"

        # Run
        result = designer.run_experiment(exp, graph)
        assert isinstance(result, ExperimentResult)
        assert len(result.observations) > 0

        # Report
        report = designer.generate_report(result)
        assert "e2e-test" in report
        assert "cache" in report.lower()
        assert len(report) > 100

        # Export
        data = designer.export_experiment(exp)
        json_str = json.dumps(data)
        assert len(json_str) > 0

    def test_template_resolve_validate_run(self):
        """Use template, resolve targets, validate, run."""
        designer = ExperimentDesigner()
        graph = _build_large_graph()

        exp = designer.from_template("cache-stampede")
        exp = designer.resolve_template_targets(exp, graph)

        errors = designer.validate_experiment(exp, graph)
        # May have blast radius issues with a simple template, but should validate structurally
        # (rollback targets may not match exactly after resolution)

        result = designer.run_experiment(exp, graph)
        assert isinstance(result, ExperimentResult)
        report = designer.generate_report(result)
        assert "Cache Stampede" in report

    def test_database_failover_template_on_large_graph(self):
        """Database failover template on a graph with a database."""
        designer = ExperimentDesigner()
        graph = _build_large_graph()
        exp = designer.from_template("database-failover")
        exp = designer.resolve_template_targets(exp, graph)
        result = designer.run_experiment(exp, graph)
        assert isinstance(result, ExperimentResult)
        assert len(result.observations) > 0

    def test_traffic_spike_template_on_large_graph(self):
        designer = ExperimentDesigner()
        graph = _build_large_graph()
        exp = designer.from_template("traffic-spike")
        exp = designer.resolve_template_targets(exp, graph)
        result = designer.run_experiment(exp, graph)
        assert isinstance(result, ExperimentResult)
        assert any("spike" in o.lower() or "traffic" in o.lower() for o in result.observations)

    def test_data_corruption_template_end_to_end(self):
        designer = ExperimentDesigner()
        graph = _build_large_graph()
        exp = designer.from_template("data-corruption")
        exp = designer.resolve_template_targets(exp, graph)
        result = designer.run_experiment(exp, graph)
        report = designer.generate_report(result)
        assert "Data Corruption" in report

    def test_network_partition_template_end_to_end(self):
        designer = ExperimentDesigner()
        graph = _build_large_graph()
        exp = designer.from_template("network-partition")
        exp = designer.resolve_template_targets(exp, graph)
        result = designer.run_experiment(exp, graph)
        assert isinstance(result, ExperimentResult)

    def test_dependency_timeout_template_end_to_end(self):
        designer = ExperimentDesigner()
        graph = _build_large_graph()
        exp = designer.from_template("dependency-timeout")
        exp = designer.resolve_template_targets(exp, graph)
        result = designer.run_experiment(exp, graph)
        assert isinstance(result, ExperimentResult)

    def test_cascading_failure_template_end_to_end(self):
        designer = ExperimentDesigner()
        graph = _build_large_graph()
        exp = designer.from_template("cascading-failure")
        exp = designer.resolve_template_targets(exp, graph)
        result = designer.run_experiment(exp, graph)
        assert isinstance(result, ExperimentResult)

    def test_zone_failure_template_end_to_end(self):
        designer = ExperimentDesigner()
        graph = _build_large_graph()
        exp = designer.from_template("zone-failure")
        exp = designer.resolve_template_targets(exp, graph)
        result = designer.run_experiment(exp, graph)
        assert isinstance(result, ExperimentResult)
