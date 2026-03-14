"""Game Day simulation engine for ChaosProof.

Simulates structured Game Day exercises by executing a sequence of planned
steps — fault injections, health verifications, and manual checks — against
the infrastructure graph using the dynamic simulation engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from infrasim.model.components import HealthStatus
from infrasim.model.graph import InfraGraph
from infrasim.simulator.scenarios import Fault, FaultType


# ---------------------------------------------------------------------------
# Plan models
# ---------------------------------------------------------------------------


class GameDayStep(BaseModel):
    """A single step in a Game Day exercise."""

    time_offset_seconds: int
    action: str  # "inject_fault", "verify_health", "manual_check"
    fault: Fault | None = None
    expected_outcome: str = ""
    runbook_step: str = ""


class GameDayPlan(BaseModel):
    """A complete Game Day exercise plan."""

    name: str
    description: str = ""
    steps: list[GameDayStep] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    rollback_plan: str = ""


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class GameDayStepResult:
    """Result of a single Game Day step execution."""

    step_index: int
    action: str
    time_seconds: int
    outcome: str  # "PASS", "FAIL", "SKIP"
    details: str
    health_snapshot: dict[str, str] = field(default_factory=dict)


@dataclass
class GameDayReport:
    """Full Game Day exercise report."""

    plan_name: str
    steps: list[GameDayStepResult] = field(default_factory=list)
    passed: int = 0
    failed: int = 0
    overall: str = "PASS"  # "PASS" or "FAIL"
    timeline_summary: str = ""


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class GameDayEngine:
    """Execute Game Day exercises against an infrastructure graph.

    Each step is simulated using the dynamic simulation engine (fault
    injection) or direct health inspection (verification steps).
    """

    def __init__(self, graph: InfraGraph) -> None:
        self._graph = graph
        # Track component health overrides during the exercise
        self._health_overrides: dict[str, HealthStatus] = {}

    def execute(self, plan: GameDayPlan) -> GameDayReport:
        """Execute a Game Day plan and return the report.

        Parameters
        ----------
        plan:
            The Game Day plan to execute.

        Returns
        -------
        GameDayReport
            Results of every step, pass/fail counts, and a timeline summary.
        """
        step_results: list[GameDayStepResult] = []
        self._health_overrides.clear()

        for idx, step in enumerate(plan.steps):
            if step.action == "inject_fault":
                result = self._execute_fault_injection(idx, step)
            elif step.action == "verify_health":
                result = self._execute_health_verification(idx, step)
            elif step.action == "manual_check":
                result = self._execute_manual_check(idx, step)
            else:
                result = GameDayStepResult(
                    step_index=idx,
                    action=step.action,
                    time_seconds=step.time_offset_seconds,
                    outcome="SKIP",
                    details=f"Unknown action: {step.action}",
                    health_snapshot=self._current_health_snapshot(),
                )
            step_results.append(result)

        passed = sum(1 for r in step_results if r.outcome == "PASS")
        failed = sum(1 for r in step_results if r.outcome == "FAIL")
        overall = "FAIL" if failed > 0 else "PASS"

        timeline = self._build_timeline(step_results)

        return GameDayReport(
            plan_name=plan.name,
            steps=step_results,
            passed=passed,
            failed=failed,
            overall=overall,
            timeline_summary=timeline,
        )

    # -- step executors ----------------------------------------------------

    def _execute_fault_injection(
        self,
        idx: int,
        step: GameDayStep,
    ) -> GameDayStepResult:
        """Simulate a fault injection step."""
        if step.fault is None:
            return GameDayStepResult(
                step_index=idx,
                action=step.action,
                time_seconds=step.time_offset_seconds,
                outcome="SKIP",
                details="No fault specified in inject_fault step.",
                health_snapshot=self._current_health_snapshot(),
            )

        fault = step.fault
        target = self._graph.get_component(fault.target_component_id)

        if target is None:
            return GameDayStepResult(
                step_index=idx,
                action=step.action,
                time_seconds=step.time_offset_seconds,
                outcome="FAIL",
                details=f"Target component '{fault.target_component_id}' not found.",
                health_snapshot=self._current_health_snapshot(),
            )

        # Simulate fault effects
        details_parts: list[str] = []

        if fault.fault_type == FaultType.COMPONENT_DOWN:
            self._health_overrides[target.id] = HealthStatus.DOWN
            details_parts.append(f"Component '{target.id}' set to DOWN.")
            # Check cascade: affected components via dependencies
            affected = self._graph.get_all_affected(target.id)
            if affected:
                details_parts.append(
                    f"Cascade affects: {', '.join(sorted(affected))}."
                )

        elif fault.fault_type == FaultType.LATENCY_SPIKE:
            self._health_overrides[target.id] = HealthStatus.DEGRADED
            details_parts.append(
                f"Latency spike injected on '{target.id}' "
                f"(severity={fault.severity:.1f})."
            )

        elif fault.fault_type == FaultType.CPU_SATURATION:
            if fault.severity > 0.8:
                self._health_overrides[target.id] = HealthStatus.OVERLOADED
            else:
                self._health_overrides[target.id] = HealthStatus.DEGRADED
            details_parts.append(
                f"CPU saturation on '{target.id}' "
                f"(severity={fault.severity:.1f})."
            )

        elif fault.fault_type == FaultType.MEMORY_EXHAUSTION:
            self._health_overrides[target.id] = HealthStatus.DOWN
            details_parts.append(
                f"Memory exhaustion on '{target.id}' — component DOWN."
            )

        elif fault.fault_type == FaultType.DISK_FULL:
            self._health_overrides[target.id] = HealthStatus.DOWN
            details_parts.append(
                f"Disk full on '{target.id}' — component DOWN."
            )

        elif fault.fault_type == FaultType.CONNECTION_POOL_EXHAUSTION:
            self._health_overrides[target.id] = HealthStatus.DEGRADED
            details_parts.append(
                f"Connection pool exhausted on '{target.id}'."
            )

        elif fault.fault_type == FaultType.NETWORK_PARTITION:
            self._health_overrides[target.id] = HealthStatus.DOWN
            details_parts.append(
                f"Network partition isolating '{target.id}'."
            )

        elif fault.fault_type == FaultType.TRAFFIC_SPIKE:
            self._health_overrides[target.id] = HealthStatus.OVERLOADED
            details_parts.append(
                f"Traffic spike on '{target.id}' "
                f"(severity={fault.severity:.1f})."
            )

        else:
            self._health_overrides[target.id] = HealthStatus.DEGRADED
            details_parts.append(
                f"Fault '{fault.fault_type.value}' injected on '{target.id}'."
            )

        # Check if resilience mechanisms mitigate the fault
        if target.failover.enabled and target.replicas > 1:
            details_parts.append(
                f"Failover available (promotion time: "
                f"{target.failover.promotion_time_seconds}s)."
            )

        details = " ".join(details_parts)
        outcome = "PASS"  # Injection itself always succeeds

        return GameDayStepResult(
            step_index=idx,
            action=step.action,
            time_seconds=step.time_offset_seconds,
            outcome=outcome,
            details=details,
            health_snapshot=self._current_health_snapshot(),
        )

    def _execute_health_verification(
        self,
        idx: int,
        step: GameDayStep,
    ) -> GameDayStepResult:
        """Verify component health against expected outcome."""
        snapshot = self._current_health_snapshot()
        details_parts: list[str] = []
        outcome = "PASS"

        if step.expected_outcome:
            # Parse expected outcome format: "component_id:status" or just "all_healthy"
            expected = step.expected_outcome.strip()

            if expected == "all_healthy":
                unhealthy = {
                    cid: status for cid, status in snapshot.items()
                    if status != "healthy"
                }
                if unhealthy:
                    outcome = "FAIL"
                    details_parts.append(
                        f"Expected all healthy, but found: "
                        f"{', '.join(f'{k}={v}' for k, v in unhealthy.items())}."
                    )
                else:
                    details_parts.append("All components healthy as expected.")

            elif ":" in expected:
                comp_id, expected_status = expected.split(":", 1)
                actual = snapshot.get(comp_id, "unknown")
                if actual == expected_status:
                    details_parts.append(
                        f"Component '{comp_id}' is '{actual}' as expected."
                    )
                else:
                    outcome = "FAIL"
                    details_parts.append(
                        f"Expected '{comp_id}' to be '{expected_status}', "
                        f"got '{actual}'."
                    )
            else:
                # Generic check: see if expected_outcome component is healthy
                comp_id = expected
                actual = snapshot.get(comp_id, "unknown")
                if actual in ("healthy", "degraded"):
                    details_parts.append(
                        f"Component '{comp_id}' is '{actual}'."
                    )
                else:
                    outcome = "FAIL"
                    details_parts.append(
                        f"Component '{comp_id}' is '{actual}' (not healthy/degraded)."
                    )
        else:
            # No expected outcome - just report current state
            down_count = sum(1 for s in snapshot.values() if s == "down")
            details_parts.append(
                f"Health check: {len(snapshot)} components, "
                f"{down_count} down."
            )
            if down_count > 0:
                outcome = "FAIL"

        return GameDayStepResult(
            step_index=idx,
            action=step.action,
            time_seconds=step.time_offset_seconds,
            outcome=outcome,
            details=" ".join(details_parts),
            health_snapshot=snapshot,
        )

    def _execute_manual_check(
        self,
        idx: int,
        step: GameDayStep,
    ) -> GameDayStepResult:
        """Execute a manual check step (simulated).

        Manual checks always pass in simulation mode.  In a real exercise,
        these would be paused for a human operator.
        """
        details = f"Manual check: {step.runbook_step}" if step.runbook_step else "Manual check completed (simulated)."
        if step.expected_outcome:
            details += f" Expected: {step.expected_outcome}."

        return GameDayStepResult(
            step_index=idx,
            action=step.action,
            time_seconds=step.time_offset_seconds,
            outcome="PASS",
            details=details,
            health_snapshot=self._current_health_snapshot(),
        )

    # -- helpers -----------------------------------------------------------

    def _current_health_snapshot(self) -> dict[str, str]:
        """Get current health status of all components."""
        snapshot: dict[str, str] = {}
        for comp in self._graph.components.values():
            if comp.id in self._health_overrides:
                snapshot[comp.id] = self._health_overrides[comp.id].value
            else:
                snapshot[comp.id] = comp.health.value
        return snapshot

    def _build_timeline(self, results: list[GameDayStepResult]) -> str:
        """Build a human-readable timeline summary."""
        if not results:
            return "No steps executed."

        lines: list[str] = []
        for r in results:
            status_marker = "OK" if r.outcome == "PASS" else (
                "FAIL" if r.outcome == "FAIL" else "SKIP"
            )
            lines.append(
                f"  T+{r.time_seconds:>5d}s [{status_marker:4s}] "
                f"{r.action}: {r.details[:80]}"
            )

        passed = sum(1 for r in results if r.outcome == "PASS")
        failed = sum(1 for r in results if r.outcome == "FAIL")
        skipped = sum(1 for r in results if r.outcome == "SKIP")

        header = (
            f"Game Day Timeline ({len(results)} steps: "
            f"{passed} passed, {failed} failed, {skipped} skipped)"
        )
        return header + "\n" + "\n".join(lines)
