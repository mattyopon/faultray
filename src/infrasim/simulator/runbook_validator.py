"""Runbook Validator for ChaosProof.

Validate that runbooks actually work by simulating each step against the
infrastructure graph. Inject an initial fault, then execute runbook steps
and verify that each step produces the expected outcome.

Usage:
    from infrasim.simulator.runbook_validator import RunbookValidator
    validator = RunbookValidator(graph)
    report = validator.validate(steps, initial_fault)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from infrasim.model.components import HealthStatus
from infrasim.model.graph import InfraGraph
from infrasim.simulator.cascade import CascadeEngine
from infrasim.simulator.scenarios import Fault, FaultType


@dataclass
class RunbookStep:
    """A single step in a runbook."""

    step_number: int
    action: str  # "restart_component", "scale_up", "failover", "check_health", "wait"
    target: str  # component_id or "all"
    expected_result: str  # "healthy", "down", "degraded", "overloaded", "scaled"
    timeout_seconds: int = 300
    parameters: dict[str, str | int | float] = field(default_factory=dict)


@dataclass
class RunbookValidationResult:
    """Result of validating a single runbook step."""

    step_number: int
    action: str
    target: str
    result: str  # "PASS", "FAIL", "TIMEOUT", "SKIP"
    actual_state: str
    expected_state: str
    time_elapsed_seconds: float = 0.0
    details: str = ""


@dataclass
class RunbookReport:
    """Complete report from validating a runbook."""

    runbook_name: str
    total_steps: int
    passed: int
    failed: int
    skipped: int
    overall: str  # "VALID", "INVALID", "PARTIAL"
    estimated_recovery_minutes: float
    step_results: list[RunbookValidationResult] = field(default_factory=list)
    improvements: list[str] = field(default_factory=list)
    initial_fault: str = ""


class RunbookValidator:
    """Validate runbooks by simulating each step against the infrastructure.

    Supported actions:
        - check_health: Check if a component is in the expected state.
        - restart_component: Simulate restarting a component.
        - failover: Simulate failover to a standby.
        - scale_up: Simulate scaling up replicas.
        - scale_down: Simulate scaling down replicas.
        - wait: Simulate waiting for a recovery period.
        - notify: Simulate sending a notification (always passes).
        - rollback: Simulate rolling back a change.
    """

    VALID_ACTIONS = {
        "check_health",
        "restart_component",
        "failover",
        "scale_up",
        "scale_down",
        "wait",
        "notify",
        "rollback",
    }

    def __init__(self, graph: InfraGraph) -> None:
        self.graph = graph
        self._cascade_engine = CascadeEngine(graph)
        # Track simulated component states during validation
        self._component_states: dict[str, HealthStatus] = {}

    def validate(
        self,
        runbook_steps: list[RunbookStep],
        initial_fault: Fault,
        runbook_name: str = "unnamed",
    ) -> RunbookReport:
        """Inject a fault, then execute runbook steps to verify recovery.

        Args:
            runbook_steps: The ordered list of steps to validate.
            initial_fault: The initial fault to inject before running steps.
            runbook_name: Name of the runbook for reporting.

        Returns:
            A RunbookReport with step-by-step results and suggestions.
        """
        # Initialize all components as healthy
        self._component_states = {
            comp_id: HealthStatus.HEALTHY
            for comp_id in self.graph.components
        }

        # Inject the initial fault
        chain = self._cascade_engine.simulate_fault(initial_fault)
        for effect in chain.effects:
            if effect.component_id in self._component_states:
                self._component_states[effect.component_id] = effect.health

        step_results: list[RunbookValidationResult] = []
        total_time = 0.0

        for step in runbook_steps:
            result = self._execute_step(step)
            step_results.append(result)
            total_time += result.time_elapsed_seconds

        passed = sum(1 for r in step_results if r.result == "PASS")
        failed = sum(1 for r in step_results if r.result in ("FAIL", "TIMEOUT"))
        skipped = sum(1 for r in step_results if r.result == "SKIP")

        if failed == 0 and passed > 0:
            overall = "VALID"
        elif passed > 0 and failed > 0:
            overall = "PARTIAL"
        else:
            overall = "INVALID"

        improvements = self.suggest_improvements_from_results(
            step_results, initial_fault
        )

        return RunbookReport(
            runbook_name=runbook_name,
            total_steps=len(runbook_steps),
            passed=passed,
            failed=failed,
            skipped=skipped,
            overall=overall,
            estimated_recovery_minutes=total_time / 60.0,
            step_results=step_results,
            improvements=improvements,
            initial_fault=f"{initial_fault.fault_type.value} on {initial_fault.target_component_id}",
        )

    def _execute_step(self, step: RunbookStep) -> RunbookValidationResult:
        """Execute a single runbook step in simulation."""
        action = step.action.lower().strip()

        if action not in self.VALID_ACTIONS:
            return RunbookValidationResult(
                step_number=step.step_number,
                action=step.action,
                target=step.target,
                result="SKIP",
                actual_state="unknown",
                expected_state=step.expected_result,
                details=f"Unknown action: {step.action}",
            )

        handler = getattr(self, f"_action_{action}", None)
        if handler is None:
            return RunbookValidationResult(
                step_number=step.step_number,
                action=step.action,
                target=step.target,
                result="SKIP",
                actual_state="unknown",
                expected_state=step.expected_result,
                details=f"No handler for action: {step.action}",
            )

        return handler(step)

    def _action_check_health(self, step: RunbookStep) -> RunbookValidationResult:
        """Check if a component is in the expected health state."""
        target = step.target
        expected = step.expected_result.lower().strip()

        if target == "all":
            # Check all components
            states = list(self._component_states.values())
            if expected == "healthy":
                all_healthy = all(s == HealthStatus.HEALTHY for s in states)
                actual = "healthy" if all_healthy else "mixed"
            elif expected == "down":
                all_down = all(s == HealthStatus.DOWN for s in states)
                actual = "down" if all_down else "mixed"
            else:
                actual = "mixed"
        else:
            current = self._component_states.get(target)
            if current is None:
                return RunbookValidationResult(
                    step_number=step.step_number,
                    action=step.action,
                    target=target,
                    result="FAIL",
                    actual_state="not_found",
                    expected_state=expected,
                    details=f"Component '{target}' not found in infrastructure.",
                )
            actual = current.value

        passed = actual == expected
        return RunbookValidationResult(
            step_number=step.step_number,
            action=step.action,
            target=target,
            result="PASS" if passed else "FAIL",
            actual_state=actual,
            expected_state=expected,
            time_elapsed_seconds=5.0,  # health check takes ~5s
            details=f"Health check: expected={expected}, actual={actual}",
        )

    def _action_restart_component(self, step: RunbookStep) -> RunbookValidationResult:
        """Simulate restarting a component."""
        target = step.target
        expected = step.expected_result.lower().strip()

        comp = self.graph.get_component(target)
        if comp is None:
            return RunbookValidationResult(
                step_number=step.step_number,
                action=step.action,
                target=target,
                result="FAIL",
                actual_state="not_found",
                expected_state=expected,
                details=f"Component '{target}' not found.",
            )

        # Simulate restart: component goes down briefly then comes back healthy
        restart_time = comp.operational_profile.deploy_downtime_seconds
        self._component_states[target] = HealthStatus.HEALTHY
        actual = "healthy"

        passed = actual == expected
        return RunbookValidationResult(
            step_number=step.step_number,
            action=step.action,
            target=target,
            result="PASS" if passed else "FAIL",
            actual_state=actual,
            expected_state=expected,
            time_elapsed_seconds=restart_time,
            details=f"Component restarted in {restart_time}s.",
        )

    def _action_failover(self, step: RunbookStep) -> RunbookValidationResult:
        """Simulate failover to a standby."""
        target = step.target
        expected = step.expected_result.lower().strip()

        comp = self.graph.get_component(target)
        if comp is None:
            return RunbookValidationResult(
                step_number=step.step_number,
                action=step.action,
                target=target,
                result="FAIL",
                actual_state="not_found",
                expected_state=expected,
                details=f"Component '{target}' not found.",
            )

        if not comp.failover.enabled:
            # Failover not configured -- step fails
            self._component_states[target] = HealthStatus.DOWN
            return RunbookValidationResult(
                step_number=step.step_number,
                action=step.action,
                target=target,
                result="FAIL",
                actual_state="down",
                expected_state=expected,
                time_elapsed_seconds=step.timeout_seconds,
                details=(
                    f"Failover is not enabled for '{target}'. "
                    "Cannot promote standby."
                ),
            )

        # Failover succeeds -- promotion takes some time
        promotion_time = comp.failover.promotion_time_seconds
        if promotion_time > step.timeout_seconds:
            self._component_states[target] = HealthStatus.DOWN
            return RunbookValidationResult(
                step_number=step.step_number,
                action=step.action,
                target=target,
                result="TIMEOUT",
                actual_state="down",
                expected_state=expected,
                time_elapsed_seconds=step.timeout_seconds,
                details=(
                    f"Failover promotion time ({promotion_time}s) exceeds "
                    f"timeout ({step.timeout_seconds}s)."
                ),
            )

        self._component_states[target] = HealthStatus.HEALTHY
        actual = "healthy"
        passed = actual == expected
        return RunbookValidationResult(
            step_number=step.step_number,
            action=step.action,
            target=target,
            result="PASS" if passed else "FAIL",
            actual_state=actual,
            expected_state=expected,
            time_elapsed_seconds=promotion_time,
            details=f"Failover completed in {promotion_time}s.",
        )

    def _action_scale_up(self, step: RunbookStep) -> RunbookValidationResult:
        """Simulate scaling up a component."""
        target = step.target
        expected = step.expected_result.lower().strip()

        comp = self.graph.get_component(target)
        if comp is None:
            return RunbookValidationResult(
                step_number=step.step_number,
                action=step.action,
                target=target,
                result="FAIL",
                actual_state="not_found",
                expected_state=expected,
                details=f"Component '{target}' not found.",
            )

        if not comp.autoscaling.enabled:
            return RunbookValidationResult(
                step_number=step.step_number,
                action=step.action,
                target=target,
                result="FAIL",
                actual_state="not_scalable",
                expected_state=expected,
                time_elapsed_seconds=0.0,
                details=f"Autoscaling is not enabled for '{target}'.",
            )

        # Simulate scale up
        scale_time = comp.autoscaling.scale_up_delay_seconds
        self._component_states[target] = HealthStatus.HEALTHY
        actual = expected if expected in ("healthy", "scaled") else "healthy"

        return RunbookValidationResult(
            step_number=step.step_number,
            action=step.action,
            target=target,
            result="PASS",
            actual_state=actual,
            expected_state=expected,
            time_elapsed_seconds=scale_time,
            details=(
                f"Scaled up by {comp.autoscaling.scale_up_step} replicas "
                f"in {scale_time}s."
            ),
        )

    def _action_scale_down(self, step: RunbookStep) -> RunbookValidationResult:
        """Simulate scaling down a component."""
        target = step.target
        expected = step.expected_result.lower().strip()

        comp = self.graph.get_component(target)
        if comp is None:
            return RunbookValidationResult(
                step_number=step.step_number,
                action=step.action,
                target=target,
                result="FAIL",
                actual_state="not_found",
                expected_state=expected,
                details=f"Component '{target}' not found.",
            )

        scale_time = comp.autoscaling.scale_down_delay_seconds if comp.autoscaling.enabled else 60
        actual = "healthy"
        passed = actual == expected

        return RunbookValidationResult(
            step_number=step.step_number,
            action=step.action,
            target=target,
            result="PASS" if passed else "FAIL",
            actual_state=actual,
            expected_state=expected,
            time_elapsed_seconds=scale_time,
            details=f"Scale down completed in {scale_time}s.",
        )

    def _action_wait(self, step: RunbookStep) -> RunbookValidationResult:
        """Simulate waiting for a recovery period."""
        wait_seconds = step.parameters.get("seconds", step.timeout_seconds)
        if isinstance(wait_seconds, str):
            try:
                wait_seconds = int(wait_seconds)
            except ValueError:
                wait_seconds = step.timeout_seconds

        return RunbookValidationResult(
            step_number=step.step_number,
            action=step.action,
            target=step.target,
            result="PASS",
            actual_state="waited",
            expected_state=step.expected_result,
            time_elapsed_seconds=float(wait_seconds),
            details=f"Waited {wait_seconds}s for recovery.",
        )

    def _action_notify(self, step: RunbookStep) -> RunbookValidationResult:
        """Simulate sending a notification (always passes)."""
        return RunbookValidationResult(
            step_number=step.step_number,
            action=step.action,
            target=step.target,
            result="PASS",
            actual_state="notified",
            expected_state=step.expected_result,
            time_elapsed_seconds=1.0,
            details="Notification sent (simulated).",
        )

    def _action_rollback(self, step: RunbookStep) -> RunbookValidationResult:
        """Simulate rolling back a change."""
        target = step.target
        expected = step.expected_result.lower().strip()

        comp = self.graph.get_component(target)
        if comp is None and target != "all":
            return RunbookValidationResult(
                step_number=step.step_number,
                action=step.action,
                target=target,
                result="FAIL",
                actual_state="not_found",
                expected_state=expected,
                details=f"Component '{target}' not found.",
            )

        # Rollback restores component to healthy
        rollback_time = 60.0  # default rollback time
        if comp:
            rollback_time = comp.operational_profile.deploy_downtime_seconds * 2
            self._component_states[target] = HealthStatus.HEALTHY

        actual = "healthy"
        passed = actual == expected

        return RunbookValidationResult(
            step_number=step.step_number,
            action=step.action,
            target=target,
            result="PASS" if passed else "FAIL",
            actual_state=actual,
            expected_state=expected,
            time_elapsed_seconds=rollback_time,
            details=f"Rollback completed in {rollback_time}s.",
        )

    def parse_runbook_yaml(self, path: Path) -> tuple[list[RunbookStep], Fault, str]:
        """Parse a runbook from a YAML file.

        Expected YAML format:
            name: "Database failover runbook"
            trigger_fault:
              component: postgres
              type: component_down
            steps:
              - action: check_health
                target: postgres
                expected: down
              - action: failover
                target: postgres
                expected: healthy

        Args:
            path: Path to the YAML file.

        Returns:
            Tuple of (steps, initial_fault, runbook_name).

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If the YAML is malformed.
        """
        if not path.exists():
            raise FileNotFoundError(f"Runbook file not found: {path}")

        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("Runbook YAML must be a mapping at the top level.")

        runbook_name = raw.get("name", path.stem)

        # Parse trigger fault
        trigger = raw.get("trigger_fault", {})
        if not isinstance(trigger, dict):
            raise ValueError("'trigger_fault' must be a mapping.")

        target_component = trigger.get("component", "")
        fault_type_str = trigger.get("type", "component_down")
        try:
            fault_type = FaultType(fault_type_str)
        except ValueError:
            raise ValueError(
                f"Unknown fault type '{fault_type_str}'. "
                f"Valid types: {[t.value for t in FaultType]}"
            )

        initial_fault = Fault(
            target_component_id=target_component,
            fault_type=fault_type,
            severity=trigger.get("severity", 1.0),
        )

        # Parse steps
        raw_steps = raw.get("steps", [])
        if not isinstance(raw_steps, list):
            raise ValueError("'steps' must be a list.")

        steps = []
        for idx, entry in enumerate(raw_steps):
            if not isinstance(entry, dict):
                raise ValueError(f"Step {idx} must be a mapping.")

            step = RunbookStep(
                step_number=idx + 1,
                action=entry.get("action", ""),
                target=entry.get("target", ""),
                expected_result=entry.get("expected", ""),
                timeout_seconds=entry.get("timeout", 300),
                parameters=entry.get("parameters", {}),
            )
            steps.append(step)

        return steps, initial_fault, runbook_name

    def suggest_improvements_from_results(
        self,
        step_results: list[RunbookValidationResult],
        initial_fault: Fault,
    ) -> list[str]:
        """Suggest runbook improvements based on validation results."""
        improvements: list[str] = []

        failed_steps = [r for r in step_results if r.result in ("FAIL", "TIMEOUT")]
        has_health_check = any(r.action == "check_health" for r in step_results)
        has_notify = any(r.action == "notify" for r in step_results)
        has_rollback = any(r.action == "rollback" for r in step_results)

        # Check for failed failover steps
        for r in failed_steps:
            if r.action == "failover" and "not enabled" in r.details:
                improvements.append(
                    f"Enable failover for component '{r.target}' to make the "
                    f"failover step work."
                )
            elif r.action == "failover" and r.result == "TIMEOUT":
                improvements.append(
                    f"Failover promotion time for '{r.target}' exceeds the "
                    f"runbook timeout. Increase the timeout or optimize failover."
                )
            elif r.action == "scale_up" and "not enabled" in r.details:
                improvements.append(
                    f"Enable autoscaling for component '{r.target}' to make "
                    f"the scale_up step work."
                )
            elif r.action == "check_health" and r.result == "FAIL":
                improvements.append(
                    f"Step {r.step_number}: Health check expected '{r.expected_state}' "
                    f"but got '{r.actual_state}'. Review previous recovery steps."
                )

        # Suggest missing steps
        if not has_health_check:
            improvements.append(
                "Add health check steps to verify component state before and after recovery."
            )

        if not has_notify:
            improvements.append(
                "Add notification steps to alert the team about the incident and recovery."
            )

        if not has_rollback:
            improvements.append(
                "Consider adding a rollback step as a fallback if recovery fails."
            )

        # Check if initial fault target has failover
        target_comp = self.graph.get_component(initial_fault.target_component_id)
        if target_comp and not target_comp.failover.enabled:
            improvements.append(
                f"Component '{initial_fault.target_component_id}' has no failover configured. "
                f"Consider enabling failover for automated recovery."
            )

        if target_comp and target_comp.replicas <= 1:
            improvements.append(
                f"Component '{initial_fault.target_component_id}' has only 1 replica. "
                f"Consider adding replicas for redundancy."
            )

        return improvements
