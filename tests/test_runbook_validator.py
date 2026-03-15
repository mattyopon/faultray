"""Tests for Runbook Validator."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import yaml

from infrasim.model.components import (
    AutoScalingConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
)
from infrasim.model.graph import InfraGraph
from infrasim.simulator.runbook_validator import (
    RunbookReport,
    RunbookStep,
    RunbookValidationResult,
    RunbookValidator,
)
from infrasim.simulator.scenarios import Fault, FaultType


def _build_test_graph() -> InfraGraph:
    """Build a test infrastructure graph."""
    graph = InfraGraph()

    graph.add_component(Component(
        id="app",
        name="App Server",
        type=ComponentType.APP_SERVER,
        replicas=2,
        autoscaling=AutoScalingConfig(
            enabled=True, min_replicas=2, max_replicas=10,
            scale_up_delay_seconds=15,
        ),
    ))

    graph.add_component(Component(
        id="postgres",
        name="PostgreSQL",
        type=ComponentType.DATABASE,
        replicas=1,
        failover=FailoverConfig(
            enabled=True,
            promotion_time_seconds=30.0,
            health_check_interval_seconds=10.0,
        ),
    ))

    graph.add_component(Component(
        id="redis",
        name="Redis",
        type=ComponentType.CACHE,
        replicas=1,
        # No failover or autoscaling
    ))

    graph.add_dependency(Dependency(
        source_id="app", target_id="postgres", dependency_type="requires",
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="redis", dependency_type="optional",
    ))

    return graph


class TestRunbookValidator:
    """Test suite for RunbookValidator."""

    def test_simple_valid_runbook(self):
        """Test a simple runbook that should fully validate."""
        graph = _build_test_graph()
        validator = RunbookValidator(graph)

        fault = Fault(
            target_component_id="postgres",
            fault_type=FaultType.COMPONENT_DOWN,
        )

        steps = [
            RunbookStep(1, "check_health", "postgres", "down"),
            RunbookStep(2, "failover", "postgres", "healthy"),
            RunbookStep(3, "check_health", "postgres", "healthy"),
            RunbookStep(4, "notify", "oncall", "notified"),
        ]

        report = validator.validate(steps, fault, runbook_name="DB failover")

        assert report.overall == "VALID"
        assert report.passed == 4
        assert report.failed == 0
        assert report.runbook_name == "DB failover"
        assert report.estimated_recovery_minutes > 0

    def test_failover_without_config(self):
        """Test that failover fails when not configured."""
        graph = _build_test_graph()
        validator = RunbookValidator(graph)

        fault = Fault(
            target_component_id="redis",
            fault_type=FaultType.COMPONENT_DOWN,
        )

        steps = [
            RunbookStep(1, "check_health", "redis", "down"),
            RunbookStep(2, "failover", "redis", "healthy"),
        ]

        report = validator.validate(steps, fault, runbook_name="Redis failover")

        assert report.overall == "PARTIAL"
        assert report.failed >= 1
        # The failover step should fail since redis has no failover
        failover_result = report.step_results[1]
        assert failover_result.result == "FAIL"
        assert "not enabled" in failover_result.details

    def test_restart_component_step(self):
        """Test the restart_component action."""
        graph = _build_test_graph()
        validator = RunbookValidator(graph)

        fault = Fault(
            target_component_id="app",
            fault_type=FaultType.COMPONENT_DOWN,
        )

        steps = [
            RunbookStep(1, "restart_component", "app", "healthy"),
        ]

        report = validator.validate(steps, fault)
        assert report.passed == 1
        assert report.step_results[0].result == "PASS"

    def test_scale_up_step(self):
        """Test the scale_up action."""
        graph = _build_test_graph()
        validator = RunbookValidator(graph)

        fault = Fault(
            target_component_id="app",
            fault_type=FaultType.CPU_SATURATION,
        )

        steps = [
            RunbookStep(1, "scale_up", "app", "healthy"),
        ]

        report = validator.validate(steps, fault)
        assert report.step_results[0].result == "PASS"
        assert "Scaled up" in report.step_results[0].details

    def test_scale_up_without_autoscaling(self):
        """Test scale_up fails when autoscaling is not enabled."""
        graph = _build_test_graph()
        validator = RunbookValidator(graph)

        fault = Fault(
            target_component_id="redis",
            fault_type=FaultType.CPU_SATURATION,
        )

        steps = [
            RunbookStep(1, "scale_up", "redis", "healthy"),
        ]

        report = validator.validate(steps, fault)
        assert report.step_results[0].result == "FAIL"
        assert "not enabled" in report.step_results[0].details

    def test_wait_step(self):
        """Test the wait action."""
        graph = _build_test_graph()
        validator = RunbookValidator(graph)

        fault = Fault(
            target_component_id="app",
            fault_type=FaultType.COMPONENT_DOWN,
        )

        steps = [
            RunbookStep(1, "wait", "app", "waited", parameters={"seconds": 60}),
        ]

        report = validator.validate(steps, fault)
        assert report.step_results[0].result == "PASS"
        assert report.step_results[0].time_elapsed_seconds == 60.0

    def test_notify_step(self):
        """Test the notify action (always passes)."""
        graph = _build_test_graph()
        validator = RunbookValidator(graph)

        fault = Fault(
            target_component_id="app",
            fault_type=FaultType.COMPONENT_DOWN,
        )

        steps = [
            RunbookStep(1, "notify", "oncall-team", "notified"),
        ]

        report = validator.validate(steps, fault)
        assert report.step_results[0].result == "PASS"

    def test_unknown_action(self):
        """Test that unknown actions are skipped."""
        graph = _build_test_graph()
        validator = RunbookValidator(graph)

        fault = Fault(
            target_component_id="app",
            fault_type=FaultType.COMPONENT_DOWN,
        )

        steps = [
            RunbookStep(1, "magic_fix", "app", "healthy"),
        ]

        report = validator.validate(steps, fault)
        assert report.step_results[0].result == "SKIP"

    def test_nonexistent_component(self):
        """Test handling of a component that doesn't exist."""
        graph = _build_test_graph()
        validator = RunbookValidator(graph)

        fault = Fault(
            target_component_id="app",
            fault_type=FaultType.COMPONENT_DOWN,
        )

        steps = [
            RunbookStep(1, "check_health", "nonexistent", "healthy"),
        ]

        report = validator.validate(steps, fault)
        assert report.step_results[0].result == "FAIL"
        assert "not found" in report.step_results[0].details.lower()

    def test_parse_runbook_yaml(self):
        """Test parsing a runbook from YAML."""
        graph = _build_test_graph()
        validator = RunbookValidator(graph)

        runbook_data = {
            "name": "Database failover runbook",
            "trigger_fault": {
                "component": "postgres",
                "type": "component_down",
            },
            "steps": [
                {"action": "check_health", "target": "postgres", "expected": "down"},
                {"action": "failover", "target": "postgres", "expected": "healthy"},
                {"action": "check_health", "target": "app", "expected": "healthy"},
            ],
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            yaml.dump(runbook_data, f)
            tmp_path = Path(f.name)

        try:
            steps, fault, name = validator.parse_runbook_yaml(tmp_path)

            assert name == "Database failover runbook"
            assert fault.target_component_id == "postgres"
            assert fault.fault_type == FaultType.COMPONENT_DOWN
            assert len(steps) == 3
            assert steps[0].action == "check_health"
            assert steps[1].action == "failover"
            assert steps[2].target == "app"
        finally:
            tmp_path.unlink()

    def test_parse_runbook_yaml_file_not_found(self):
        """Test parsing a nonexistent runbook file."""
        graph = _build_test_graph()
        validator = RunbookValidator(graph)

        with pytest.raises(FileNotFoundError):
            validator.parse_runbook_yaml(Path("/nonexistent/runbook.yaml"))

    def test_improvements_suggest_health_checks(self):
        """Test that improvements suggest missing health checks."""
        graph = _build_test_graph()
        validator = RunbookValidator(graph)

        fault = Fault(
            target_component_id="redis",
            fault_type=FaultType.COMPONENT_DOWN,
        )

        # Runbook without health checks
        steps = [
            RunbookStep(1, "restart_component", "redis", "healthy"),
        ]

        report = validator.validate(steps, fault)
        # Should suggest adding health checks and notification
        has_health_suggestion = any(
            "health check" in imp.lower() for imp in report.improvements
        )
        assert has_health_suggestion

    def test_improvements_suggest_failover(self):
        """Test that improvements suggest enabling failover."""
        graph = _build_test_graph()
        validator = RunbookValidator(graph)

        fault = Fault(
            target_component_id="redis",
            fault_type=FaultType.COMPONENT_DOWN,
        )

        steps = [
            RunbookStep(1, "check_health", "redis", "down"),
            RunbookStep(2, "restart_component", "redis", "healthy"),
        ]

        report = validator.validate(steps, fault)
        # Redis has no failover, should suggest enabling it
        has_failover_suggestion = any(
            "failover" in imp.lower() for imp in report.improvements
        )
        assert has_failover_suggestion

    def test_report_structure(self):
        """Test RunbookReport has correct structure."""
        graph = _build_test_graph()
        validator = RunbookValidator(graph)

        fault = Fault(
            target_component_id="app",
            fault_type=FaultType.COMPONENT_DOWN,
        )

        steps = [
            RunbookStep(1, "check_health", "app", "down"),
        ]

        report = validator.validate(steps, fault)

        assert isinstance(report, RunbookReport)
        assert isinstance(report.step_results, list)
        assert isinstance(report.improvements, list)
        assert report.total_steps == 1
        assert report.overall in ("VALID", "INVALID", "PARTIAL")
        assert report.initial_fault != ""

    def test_check_health_all(self):
        """Test check_health with target='all'."""
        graph = _build_test_graph()
        validator = RunbookValidator(graph)

        fault = Fault(
            target_component_id="app",
            fault_type=FaultType.COMPONENT_DOWN,
        )

        steps = [
            RunbookStep(1, "restart_component", "app", "healthy"),
            RunbookStep(2, "check_health", "all", "healthy"),
        ]

        report = validator.validate(steps, fault)
        # After restarting app, not all components might be healthy
        # (depending on cascade from initial fault)
        assert report.step_results[1].target == "all"

    def test_rollback_step(self):
        """Test the rollback action."""
        graph = _build_test_graph()
        validator = RunbookValidator(graph)

        fault = Fault(
            target_component_id="app",
            fault_type=FaultType.COMPONENT_DOWN,
        )

        steps = [
            RunbookStep(1, "rollback", "app", "healthy"),
        ]

        report = validator.validate(steps, fault)
        assert report.step_results[0].result == "PASS"
        assert "Rollback" in report.step_results[0].details

    def test_failover_timeout(self):
        """Test failover that exceeds step timeout."""
        graph = _build_test_graph()
        validator = RunbookValidator(graph)

        fault = Fault(
            target_component_id="postgres",
            fault_type=FaultType.COMPONENT_DOWN,
        )

        # Set a very short timeout (shorter than promotion time of 30s)
        steps = [
            RunbookStep(1, "failover", "postgres", "healthy", timeout_seconds=5),
        ]

        report = validator.validate(steps, fault)
        assert report.step_results[0].result == "TIMEOUT"
