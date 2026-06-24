# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Autonomous remediation agent with sensitivity ratchet safety.

Detects infrastructure issues, generates fixes, verifies safety via
simulation, executes with ratchet-controlled permissions, and verifies
improvement. Humans only need to approve (or set auto-approve mode).
"""

from __future__ import annotations

import copy
import json
import logging
import os
import re
import subprocess
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

_VALID_STATUSES = frozenset({
    "detecting",
    "planning",
    "simulating",
    "awaiting_approval",
    "executing",
    "verifying",
    "completed",
    "failed",
    "rolled_back",
    "rollback_failed",
    "regressed",
})


@dataclass
class StepResult:
    """Result of executing a single remediation step."""

    status: str  # "success", "failed", "dry_run", "timeout"
    output: str = ""


@dataclass
class RemediationCycle:
    """Record of one detect -> fix -> verify cycle."""

    id: str
    started_at: str
    completed_at: str | None = None
    status: str = "detecting"

    # Detection
    initial_score: float = 0.0
    issues_found: list[dict[str, Any]] = field(default_factory=list)

    # Planning
    remediation_plan: dict[str, Any] | None = None
    estimated_improvement: float = 0.0
    estimated_cost: str = "$0.00"

    # Simulation
    simulation_passed: bool = False
    simulated_score: float = 0.0
    side_effects: list[str] = field(default_factory=list)

    # Execution
    ratchet_state: dict[str, Any] = field(default_factory=dict)
    execution_log: list[dict[str, Any]] = field(default_factory=list)

    # Verification
    final_score: float | None = None
    improvement_achieved: float | None = None

    # Report
    report_summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize the cycle to a JSON-friendly dict."""
        return {
            "id": self.id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "status": self.status,
            "initial_score": self.initial_score,
            "issues_found": self.issues_found,
            "remediation_plan": self.remediation_plan,
            "estimated_improvement": self.estimated_improvement,
            "estimated_cost": self.estimated_cost,
            "simulation_passed": self.simulation_passed,
            "simulated_score": self.simulated_score,
            "side_effects": self.side_effects,
            "ratchet_state": self.ratchet_state,
            "execution_log": self.execution_log,
            "final_score": self.final_score,
            "improvement_achieved": self.improvement_achieved,
            "report_summary": self.report_summary,
        }


# ---------------------------------------------------------------------------
# Simulation result (lightweight, avoids coupling to external types)
# ---------------------------------------------------------------------------


@dataclass
class _SimResult:
    """Internal simulation result for plan pre-validation."""

    passed: bool
    new_score: float
    side_effects: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Plan step (lightweight wrapper)
# ---------------------------------------------------------------------------


@dataclass
class _PlanStep:
    """A single step extracted from the remediation plan."""

    description: str
    risk_level: str  # "low", "medium", "high", "critical"
    file_path: str
    content: str
    execution_type: str  # "terraform", "kubernetes", "aws_cli", "script"


# ---------------------------------------------------------------------------
# Independent simulation: apply remediation intent to a graph and re-measure
# ---------------------------------------------------------------------------

# A measured patched score may decrease by at most this (float noise) before it
# counts as a regression.
_SIM_REGRESSION_TOLERANCE = 0.5
# If the generator's projected score exceeds the independently measured score by
# more than this, we log the divergence (the measured value stays authoritative).
_SIM_DIVERGENCE_THRESHOLD = 5.0


def _mut_add_replicas(comp: Any) -> None:
    comp.replicas = max(comp.replicas, 2)


def _mut_enable_autoscaling(comp: Any) -> None:
    comp.autoscaling.enabled = True
    comp.autoscaling.min_replicas = max(2, comp.autoscaling.min_replicas)
    comp.autoscaling.max_replicas = max(
        comp.autoscaling.max_replicas, comp.autoscaling.min_replicas, 4
    )


def _mut_encryption_at_rest(comp: Any) -> None:
    comp.security.encryption_at_rest = True


def _mut_waf(comp: Any) -> None:
    comp.security.waf_protected = True


def _mut_network_segmented(comp: Any) -> None:
    comp.security.network_segmented = True


def _mut_tls(comp: Any) -> None:
    comp.security.encryption_in_transit = True


def _mut_dr_region(comp: Any) -> None:
    comp.region.dr_target_region = comp.region.dr_target_region or "dr-region"


def _mut_backup(comp: Any) -> None:
    comp.security.backup_enabled = True


def _mut_failover(comp: Any) -> None:
    comp.failover.enabled = True


# Maps each IaC remediation rule key to the structural change it represents.
# Kept 1:1 with REMEDIATION_RULES so the independent simulation applies exactly
# what the generator would fix (a test asserts every rule key is mapped).
_RULE_MUTATIONS = {
    "database_no_replica": _mut_add_replicas,
    "cache_no_replica": _mut_add_replicas,
    "no_autoscaling": _mut_enable_autoscaling,
    "no_encryption": _mut_encryption_at_rest,
    "no_waf": _mut_waf,
    "no_network_segmentation": _mut_network_segmented,
    "no_tls": _mut_tls,
    "no_cross_region": _mut_dr_region,
    "no_backup": _mut_backup,
    "no_dns_failover": _mut_failover,
}


def _apply_remediation_intent(
    graph: InfraGraph, selected: set[tuple[str, str]] | None = None
) -> int:
    """Apply the remediation rules' intended structural changes to *graph* in
    place; return the number of fixes applied.

    Reuses the exact condition predicates from REMEDIATION_RULES so detection
    never drifts from the IaC generator, then applies the corresponding graph
    mutation. This lets SIMULATE MEASURE a fix's real effect on the resilience
    score instead of trusting the generator's self-reported projected delta.

    When *selected* (a set of ``(component_id, rule_key)`` pairs) is given, only
    those pairs are applied — so the measurement reflects exactly the selected
    plan, not every rule that happens to match the graph (the IaC generator
    trims its plan once the target score is reached).
    """
    from faultray.remediation.iac_generator import REMEDIATION_RULES

    applied = 0
    for comp in graph.components.values():
        for rule in REMEDIATION_RULES:
            mutate = _RULE_MUTATIONS.get(rule.key)
            if mutate is None or not rule.condition(comp):
                continue
            if selected is not None and (comp.id, rule.key) not in selected:
                continue
            mutate(comp)
            applied += 1
    return applied


class _ApplyBlocked(Exception):
    """Raised when a live-apply subprocess is attempted without full opt-in."""


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class AutonomousRemediationAgent:
    """Self-healing infrastructure agent with safety guardrails.

    Runs the full autonomous loop::

        Detect -> Plan -> Simulate -> [Approve] -> Execute -> Verify -> Report
    """

    _STEP_TIMEOUT = 300  # seconds per execution step

    # Live execution (`terraform apply -auto-approve`, `kubectl apply`) against
    # real infrastructure is DEFAULT-OFF. It only runs when ALL of the
    # following hold: dry_run is False, auto_approve is True, AND the operator
    # has explicitly opted in via the FAULTRAY_ALLOW_AUTO_APPLY environment
    # variable. Any other combination falls back to dry-run (preview only).
    _AUTO_APPLY_ENV = "FAULTRAY_ALLOW_AUTO_APPLY"

    def __init__(
        self,
        model_path: str = "faultray-model.json",
        auto_approve: bool = False,
        max_risk_level: str = "medium",
        ratchet_enabled: bool = True,
        dry_run: bool = True,
        output_dir: str = "~/.faultray/remediation/",
        cloud_provider: str | None = None,
        terraform_dir: str | None = None,
        max_monthly_cost: float = 100_000.0,
        max_steps: int = 50,
    ) -> None:
        self.model_path = model_path
        self.auto_approve = auto_approve
        self.max_risk_level = max_risk_level
        self.ratchet_enabled = ratchet_enabled
        self.dry_run = dry_run
        self.output_dir = Path(output_dir).expanduser()
        self.cloud_provider = cloud_provider
        self.terraform_dir = terraform_dir
        # Hard fail-safe ceilings: a plan whose projected monthly cost or step
        # count exceeds these is rejected outright (never executed), instead of
        # passing simulation with an advisory warning string.
        self.max_monthly_cost = max_monthly_cost
        self.max_steps = max_steps

        # Ensure storage directories exist
        self._cycles_dir = self.output_dir / "cycles"
        self._reports_dir = self.output_dir / "reports"
        self._cycles_dir.mkdir(parents=True, exist_ok=True)
        self._reports_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def _auto_apply_allowed(self) -> bool:
        """Return True only when live IaC apply is fully opted into.

        Requires dry_run=False AND auto_approve=True AND the explicit
        ``FAULTRAY_ALLOW_AUTO_APPLY`` env opt-in. Defaults to False so the
        agent never modifies live infrastructure unless an operator has taken
        all three deliberate steps.
        """
        env_optin = os.environ.get(self._AUTO_APPLY_ENV, "").strip().lower()
        env_allowed = env_optin in ("1", "true", "yes", "on")
        return (not self.dry_run) and self.auto_approve and env_allowed

    def run_cycle(self) -> RemediationCycle:
        """Run one full detect -> fix -> verify cycle (synchronous)."""
        cycle = RemediationCycle(
            id=str(uuid.uuid4())[:12],
            started_at=datetime.now(timezone.utc).isoformat(),
        )

        # Phase 1: DETECT
        cycle.status = "detecting"
        graph = self._load_or_discover()
        report = self._simulate(graph)
        cycle.initial_score = report.score_before
        cycle.issues_found = self._extract_issues(report)

        if not cycle.issues_found:
            cycle.status = "completed"
            cycle.completed_at = datetime.now(timezone.utc).isoformat()
            cycle.report_summary = (
                f"No issues found. Score: {cycle.initial_score:.1f}/100"
            )
            self._save_cycle(cycle)
            return cycle

        # Phase 2: PLAN
        cycle.status = "planning"
        plan, iac_plan = self._generate_plan(graph)
        cycle.remediation_plan = iac_plan.to_dict()
        cycle.estimated_improvement = (
            iac_plan.expected_score_after - iac_plan.expected_score_before
        )
        cycle.estimated_cost = f"${iac_plan.total_monthly_cost:,.2f}/mo"

        # Phase 3: SIMULATE (independently measure the fix's effect before applying)
        cycle.status = "simulating"
        sim_result = self._simulate_with_fix(graph, iac_plan)
        cycle.simulation_passed = sim_result.passed
        cycle.simulated_score = sim_result.new_score
        cycle.side_effects = sim_result.side_effects

        if not sim_result.passed:
            cycle.status = "failed"
            cycle.completed_at = datetime.now(timezone.utc).isoformat()
            cycle.report_summary = (
                "Simulation failed: fix would cause side effects: "
                + "; ".join(sim_result.side_effects)
            )
            self._save_cycle(cycle)
            return cycle

        # Phase 4: APPROVE
        if not self.auto_approve:
            cycle.status = "awaiting_approval"
            self._save_cycle(cycle)
            return cycle

        # Phase 5: EXECUTE (with ratchet)
        cycle = self._execute_with_ratchet(cycle, iac_plan)

        # Phase 6: VERIFY
        cycle = self._verify(cycle, graph)

        # Phase 7: REPORT
        cycle = self._generate_report(cycle)

        return cycle

    def approve_and_execute(self, cycle_id: str) -> RemediationCycle:
        """Human approves a pending cycle, then execute + verify."""
        cycle = self._load_cycle(cycle_id)
        if cycle.status != "awaiting_approval":
            raise ValueError(
                f"Cycle {cycle_id} is not awaiting approval "
                f"(status: {cycle.status})"
            )

        graph = self._load_or_discover()

        # Reconstruct IaC plan from saved data
        from faultray.remediation.iac_generator import IaCGenerator

        generator = IaCGenerator(graph)
        iac_plan = generator.generate()

        cycle = self._execute_with_ratchet(cycle, iac_plan)
        cycle = self._verify(cycle, graph)
        cycle = self._generate_report(cycle)

        return cycle

    def list_pending(self) -> list[RemediationCycle]:
        """Return all cycles awaiting approval."""
        pending: list[RemediationCycle] = []
        for f in sorted(self._cycles_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if data.get("status") == "awaiting_approval":
                    pending.append(self._dict_to_cycle(data))
            except Exception:
                logger.warning("Failed to load cycle %s", f)
        return pending

    def list_history(self) -> list[RemediationCycle]:
        """Return all completed/failed cycles, newest first."""
        cycles: list[RemediationCycle] = []
        for f in sorted(self._cycles_dir.glob("*.json"), reverse=True):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                cycles.append(self._dict_to_cycle(data))
            except Exception:
                logger.warning("Failed to load cycle %s", f)
        return cycles

    def get_latest_report(self) -> str | None:
        """Return the latest markdown report, or None."""
        reports = sorted(self._reports_dir.glob("*.md"), reverse=True)
        if reports:
            return reports[0].read_text(encoding="utf-8")
        return None

    def get_latest_report_json(self) -> dict[str, Any] | None:
        """Return the latest JSON report, or None."""
        reports = sorted(self._reports_dir.glob("*.json"), reverse=True)
        if reports:
            return json.loads(reports[0].read_text(encoding="utf-8"))  # type: ignore[no-any-return]
        return None

    # ------------------------------------------------------------------
    # Phase implementations
    # ------------------------------------------------------------------

    def _load_or_discover(self) -> InfraGraph:
        """Load existing model or run auto-discovery."""
        path = Path(self.model_path)

        if path.exists():
            if str(path).endswith((".yaml", ".yml")):
                from faultray.model.loader import load_yaml

                return load_yaml(path)
            return InfraGraph.load(path)

        # Attempt auto-discovery if cloud provider is set
        if self.cloud_provider:
            try:
                from faultray.apm.auto_discover import auto_discover

                graph = auto_discover(provider=self.cloud_provider)
                if graph is not None:
                    return graph
            except ImportError:
                logger.warning("Auto-discovery not available")

        raise FileNotFoundError(
            f"Model file not found: {self.model_path}. "
            "Run 'faultray scan' first or specify --cloud."
        )

    def _simulate(self, graph: InfraGraph) -> Any:
        """Run FaultRay auto-pipeline evaluation step.

        Returns a pipeline result with ``score_before`` attribute.
        """
        from faultray.remediation.auto_pipeline import (
            AutoRemediationPipeline,
        )

        pipeline = AutoRemediationPipeline(graph)
        result = pipeline.run(dry_run=True)
        return result

    def _extract_issues(self, report: Any) -> list[dict[str, Any]]:
        """Extract SPOFs, critical risks, warnings from simulation."""
        from faultray.simulator.remediation_engine import RemediationEngine

        # Use the full remediation engine for detailed issue analysis
        graph = self._load_or_discover()
        engine = RemediationEngine(graph, dry_run=True)
        full_report = engine.analyze_and_plan()

        issues: list[dict[str, Any]] = []
        for plan in full_report.plans:
            issues.append({
                "plan_id": plan.plan_id,
                "description": plan.issue_description,
                "priority": plan.priority.value,
                "affected_components": plan.affected_components,
                "steps_count": len(plan.steps),
                "requires_approval": plan.requires_approval,
                "estimated_minutes": plan.estimated_duration_minutes,
            })

        return issues

    def _generate_plan(
        self, graph: InfraGraph
    ) -> tuple[Any, Any]:
        """Use IaCGenerator to create fix plan.

        Returns (engine_report, iac_plan).
        """
        from faultray.remediation.iac_generator import IaCGenerator

        generator = IaCGenerator(graph)
        iac_plan = generator.generate()

        return generator, iac_plan

    def _measure_fix_effect(
        self, graph: InfraGraph, plan: Any = None
    ) -> tuple[float | None, float | None]:
        """Independently MEASURE the fix's effect on the resilience score.

        Deep-copies the graph, applies ONLY the selected plan's structural
        intent to the copy, and re-scores both — returning ``(before, after)``
        measured with the real scoring engine. Returns ``(None, None)`` if
        measurement is not possible, so the caller can fall back without
        claiming verification.
        """
        try:
            before = graph.resilience_score()
            patched = copy.deepcopy(graph)
            # Restrict the measurement to exactly the files in the selected plan
            # (the generator trims its plan once the target score is reached);
            # fall back to all matching rules when the linkage is unavailable.
            selected: set[tuple[str, str]] | None = None
            files = getattr(plan, "files", None) if plan is not None else None
            if files:
                pairs = {
                    (f.component_id, f.rule_key)
                    for f in files
                    if getattr(f, "component_id", "") and getattr(f, "rule_key", "")
                }
                if pairs:
                    selected = pairs
            applied = _apply_remediation_intent(patched, selected)
            if applied == 0:
                return before, before
            after = patched.resilience_score()
            return before, after
        except Exception:
            logger.warning(
                "Independent fix simulation failed; falling back to projection",
                exc_info=True,
            )
            return None, None

    def _simulate_with_fix(self, graph: InfraGraph, plan: Any) -> _SimResult:
        """Verify a fix is safe by INDEPENDENTLY MEASURING its effect.

        Applies the remediation rules' structural intent to a graph copy and
        re-scores with the real engine, using the measured patched score as the
        authoritative result rather than the generator's self-reported
        ``expected_score_after`` (which is just the sum of its own optimistic
        per-file deltas). Fails on a measured regression or risk-level / budget
        violation. If independent measurement is unavailable it falls back to
        the projection but does NOT present it as verified.
        """
        # The IaC plan's own projection — used only as a fallback / divergence
        # reference, never as the authoritative verified score.
        predicted_after = plan.expected_score_after
        predicted_before = plan.expected_score_before

        if not plan.files:
            return _SimResult(passed=True, new_score=graph.resilience_score())

        side_effects: list[str] = []
        new_score = predicted_after

        # HARD STOP: a plan whose projected monthly cost exceeds the configured
        # ceiling is rejected outright. Previously this was an advisory string
        # that still let the plan pass (the cost carve-out below), so a
        # $1M/mo plan would sail through simulation.
        if plan.total_monthly_cost > self.max_monthly_cost:
            return _SimResult(
                passed=False,
                new_score=predicted_after,
                side_effects=[
                    f"Estimated cost ${plan.total_monthly_cost:,.2f}/mo exceeds the "
                    f"${self.max_monthly_cost:,.2f}/mo safety cap"
                ],
            )

        # HARD STOP: an unbounded number of steps is rejected outright rather
        # than executed step-by-step.
        if len(plan.files) > self.max_steps:
            return _SimResult(
                passed=False,
                new_score=predicted_after,
                side_effects=[
                    f"Plan has {len(plan.files)} steps, exceeding the safety cap "
                    f"of {self.max_steps}"
                ],
            )

        # Independently MEASURE the fix's effect by applying the remediation
        # rules' structural intent to a graph copy and re-scoring with the real
        # engine — never trust the generator's projected expected_score_after.
        measured_before, measured_after = self._measure_fix_effect(graph, plan)
        if measured_before is not None and measured_after is not None:
            new_score = measured_after
            if measured_after < measured_before - _SIM_REGRESSION_TOLERANCE:
                side_effects.append(
                    f"Measured score would decrease: {measured_before:.1f} -> "
                    f"{measured_after:.1f}"
                )
            elif predicted_after - measured_after > _SIM_DIVERGENCE_THRESHOLD:
                # The generator over-promised relative to the measured effect;
                # surface it but do not fail — the measured value is authoritative.
                logger.warning(
                    "Remediation projection (%.1f) exceeds measured score "
                    "(%.1f) by more than %.1f",
                    predicted_after, measured_after, _SIM_DIVERGENCE_THRESHOLD,
                )
        else:
            # Could not measure independently: fall back to the projection but
            # do NOT present it as an independently verified result.
            new_score = predicted_after
            logger.warning(
                "SIMULATE could not independently measure the fix; using the "
                "generator projection (UNVERIFIED)"
            )
            if predicted_after < predicted_before:
                side_effects.append(
                    f"Score would decrease: {predicted_before:.1f} -> "
                    f"{predicted_after:.1f}"
                )

        # Check risk levels against max_risk_level
        risk_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        max_allowed = risk_order.get(self.max_risk_level, 1)

        for f in plan.files:
            # Phase 1 = critical SPOF (high risk), Phase 2 = security (medium),
            # Phase 3 = DR (low-medium)
            file_risk = "low" if f.phase == 3 else ("medium" if f.phase == 2 else "high")
            if risk_order.get(file_risk, 0) > max_allowed:
                side_effects.append(
                    f"File {f.path} risk level ({file_risk}) exceeds "
                    f"max allowed ({self.max_risk_level})"
                )

        # Any remaining side effect (measured regression or a risk-level
        # violation) fails the simulation. There is no cost carve-out: cost is
        # enforced by the hard ceiling above, not by an advisory string.
        passed = len(side_effects) == 0

        return _SimResult(
            passed=passed,
            new_score=new_score,
            side_effects=side_effects,
        )

    def _execute_with_ratchet(
        self, cycle: RemediationCycle, plan: Any
    ) -> RemediationCycle:
        """Execute remediation with sensitivity ratchet controlling permissions.

        The ratchet ensures:
        - Agent can only modify infrastructure config (not read data)
        - After touching production resources, external API access is revoked
        - Scope narrows irreversibly as execution proceeds
        - If the agent tries to exceed permissions, execution is halted
        """
        from faultray.simulator.ratchet_models import (
            RatchetState,
            SensitivityLevel,
        )

        cycle.status = "executing"

        # Initialize ratchet with infrastructure-appropriate permissions
        if self.ratchet_enabled:
            ratchet = RatchetState(
                high_water_mark=SensitivityLevel.PUBLIC,
                remaining_permissions={
                    "read:internal",
                    "write:internal",
                    "execute:tool",
                },
            )
        else:
            ratchet = RatchetState(
                high_water_mark=SensitivityLevel.PUBLIC,
                remaining_permissions={
                    "read:internal",
                    "read:external",
                    "write:internal",
                    "write:external",
                    "execute:tool",
                    "send:external_api",
                },
            )

        steps = self._plan_to_steps(plan)

        # Fail-safe guard at the execution boundary: even when a caller reaches
        # execution without going through _simulate_with_fix (e.g.
        # approve_and_execute), never run an over-budget or over-long plan.
        plan_cost = getattr(plan, "total_monthly_cost", 0.0) or 0.0
        if len(steps) > self.max_steps:
            reason = (
                f"Plan has {len(steps)} steps, exceeding the safety cap "
                f"of {self.max_steps}"
            )
            cycle.status = "blocked"
            cycle.report_summary = f"BLOCKED (pre-flight): {reason}"
            cycle.execution_log.append({
                "step": "(pre-flight)", "status": "blocked", "reason": reason,
            })
            return cycle
        if plan_cost > self.max_monthly_cost:
            reason = (
                f"Estimated cost ${plan_cost:,.2f}/mo exceeds the "
                f"${self.max_monthly_cost:,.2f}/mo safety cap"
            )
            cycle.status = "blocked"
            cycle.report_summary = f"BLOCKED (pre-flight): {reason}"
            cycle.execution_log.append({
                "step": "(pre-flight)", "status": "blocked", "reason": reason,
            })
            return cycle

        live_apply = self._auto_apply_allowed()
        if (not self.dry_run) and not live_apply:
            # Live apply was requested but is not fully opted-in. Fail safe to
            # preview-only rather than touching real infrastructure.
            logger.warning(
                "Live IaC apply requested but not permitted; falling back to "
                "dry-run. To enable, set %s=1 AND auto_approve=True AND "
                "dry_run=False.",
                self._AUTO_APPLY_ENV,
            )

        for step in steps:
            required = self._step_permissions(step)
            if not required.issubset(ratchet.remaining_permissions):
                blocked = required - ratchet.remaining_permissions
                cycle.execution_log.append({
                    "step": step.description,
                    "status": "blocked",
                    "reason": f"Permission denied by ratchet: needs {sorted(blocked)}",
                })
                continue

            # Ratchet up if touching production
            if step.risk_level in ("high", "critical"):
                ratchet.apply_ratchet(SensitivityLevel.RESTRICTED)
            elif step.risk_level == "medium":
                ratchet.apply_ratchet(SensitivityLevel.CONFIDENTIAL)

            # Execute — only when live apply is fully opted-in (see
            # _auto_apply_allowed); otherwise record a dry-run preview.
            if live_apply:
                result = self._execute_step(step)
                cycle.execution_log.append({
                    "step": step.description,
                    "status": result.status,
                    "output": result.output,
                    "ratchet_permissions": sorted(ratchet.remaining_permissions),
                    # Record what was actually applied so _verify can perform a
                    # real rollback (terraform destroy / kubectl delete) on a
                    # regression — not merely relabel the cycle "rolled_back".
                    "execution_type": step.execution_type,
                    "file_path": step.file_path,
                })
                if result.status == "failed":
                    cycle.status = "failed"
                    break
            else:
                cycle.execution_log.append({
                    "step": step.description,
                    "status": "dry_run",
                    "ratchet_permissions": sorted(ratchet.remaining_permissions),
                })

        cycle.ratchet_state = {
            "final_level": ratchet.high_water_mark.name,
            "remaining_permissions": sorted(ratchet.remaining_permissions),
        }

        if cycle.status != "failed":
            cycle.status = "verifying"

        return cycle

    def _execute_step(self, step: _PlanStep) -> StepResult:
        """Execute a single remediation step.

        Supported execution types:
        - terraform: Run terraform plan + apply
        - kubernetes: kubectl apply
        - aws_cli: aws CLI command
        - script: Custom shell script
        """
        if step.execution_type == "terraform":
            return self._execute_terraform(step)
        if step.execution_type == "kubernetes":
            return self._execute_kubernetes(step)
        # Default: log and succeed for unsupported types
        return StepResult(
            status="success",
            output=f"Executed {step.execution_type}: {step.description}",
        )

    def _apply_guarded(
        self, cmd: list[str], *, cwd: str | None = None
    ) -> subprocess.CompletedProcess:
        """Single chokepoint for every side-effecting subprocess.

        Re-checks _auto_apply_allowed() AT THE BOUNDARY (so a direct caller of
        _execute_terraform/_execute_kubernetes cannot bypass the orchestration-
        layer gate), enforces a mandatory timeout, and logs the resolved
        (dry_run, auto_approve, env opt-in) tuple for auditability. Raises
        :class:`_ApplyBlocked` when live apply is not fully opted into.
        """
        env_optin = os.environ.get(self._AUTO_APPLY_ENV, "")
        if not self._auto_apply_allowed():
            logger.warning(
                "Blocked live apply at boundary: %s (dry_run=%s auto_approve=%s %s=%r)",
                cmd, self.dry_run, self.auto_approve, self._AUTO_APPLY_ENV, env_optin,
            )
            raise _ApplyBlocked(cmd[0] if cmd else "apply")
        logger.info(
            "Live apply at boundary: %s (dry_run=%s auto_approve=%s %s=%r)",
            cmd, self.dry_run, self.auto_approve, self._AUTO_APPLY_ENV, env_optin,
        )
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=self._STEP_TIMEOUT, cwd=cwd
        )

    def _execute_terraform(self, step: _PlanStep) -> StepResult:
        """Run terraform plan + apply for a step (gated by _apply_guarded)."""
        tf_dir = self.terraform_dir or str(self.output_dir / "terraform")
        Path(tf_dir).mkdir(parents=True, exist_ok=True)

        # Write the terraform file
        tf_path = Path(tf_dir) / Path(step.file_path).name
        tf_path.write_text(step.content, encoding="utf-8")

        try:
            plan_result = self._apply_guarded(
                ["terraform", "plan", "-no-color"], cwd=tf_dir
            )
            if plan_result.returncode != 0:
                return StepResult(
                    status="failed",
                    output=f"terraform plan failed: {plan_result.stderr}",
                )

            apply_result = self._apply_guarded(
                ["terraform", "apply", "-auto-approve", "-no-color"], cwd=tf_dir
            )
            if apply_result.returncode != 0:
                return StepResult(
                    status="failed",
                    output=f"terraform apply failed: {apply_result.stderr}",
                )

            return StepResult(
                status="success",
                output=apply_result.stdout[:500],
            )
        except _ApplyBlocked:
            return StepResult(
                status="dry_run",
                output=f"live apply not opted-in ({self._AUTO_APPLY_ENV}); skipped",
            )
        except subprocess.TimeoutExpired:
            return StepResult(status="timeout", output="Step timed out")
        except (FileNotFoundError, OSError) as exc:
            return StepResult(
                status="failed",
                output=f"terraform CLI not available: {exc}",
            )

    def _execute_kubernetes(self, step: _PlanStep) -> StepResult:
        """Run kubectl apply for a step (gated by _apply_guarded)."""
        k8s_dir = self.output_dir / "kubernetes"
        k8s_dir.mkdir(parents=True, exist_ok=True)

        k8s_path = k8s_dir / Path(step.file_path).name
        k8s_path.write_text(step.content, encoding="utf-8")

        try:
            result = self._apply_guarded(
                ["kubectl", "apply", "-f", str(k8s_path)]
            )
            if result.returncode != 0:
                return StepResult(
                    status="failed",
                    output=f"kubectl apply failed: {result.stderr}",
                )
            return StepResult(status="success", output=result.stdout[:500])
        except _ApplyBlocked:
            return StepResult(
                status="dry_run",
                output=f"live apply not opted-in ({self._AUTO_APPLY_ENV}); skipped",
            )
        except subprocess.TimeoutExpired:
            return StepResult(status="timeout", output="Step timed out")
        except (FileNotFoundError, OSError) as exc:
            return StepResult(
                status="failed",
                output=f"kubectl CLI not available: {exc}",
            )

    @staticmethod
    def _terraform_targets(tf_path: Path) -> list[str]:
        """Extract ``TYPE.NAME`` resource addresses from a terraform file.

        Used so rollback can ``-target`` ONLY the resources this remediation
        added, never the whole workspace.
        """
        try:
            content = tf_path.read_text(encoding="utf-8")
        except OSError:
            return []
        return [
            f"{m.group(1)}.{m.group(2)}"
            for m in re.finditer(r'resource\s+"([^"]+)"\s+"([^"]+)"', content)
        ]

    def _rollback_step(self, execution_type: str, file_path: str) -> bool:
        """Undo a previously-applied step. Returns True if the undo succeeded.

        terraform -> targeted ``terraform destroy -target=...`` (NEVER an
        untargeted destroy, which would deprovision the operator's entire
        Terraform-managed stack); kubernetes -> ``kubectl delete -f`` (already
        scoped to the applied file). Routed through _apply_guarded so the undo
        is itself gated/timed/audited. Non-infra steps have nothing to undo.
        """
        try:
            if execution_type == "terraform":
                tf_dir = self.terraform_dir or str(self.output_dir / "terraform")
                tf_path = Path(tf_dir) / Path(file_path).name
                targets = self._terraform_targets(tf_path)
                if not targets:
                    # Refuse to run an untargeted destroy: we cannot determine
                    # exactly what this step added, so undoing it automatically
                    # could tear down unrelated infrastructure.
                    logger.error(
                        "Cannot safely roll back %s: no resource targets found; "
                        "refusing untargeted `terraform destroy`. Manual rollback "
                        "required.",
                        file_path,
                    )
                    return False
                cmd = ["terraform", "destroy", "-auto-approve", "-no-color"]
                for target in targets:
                    cmd.extend(["-target", target])
                r = self._apply_guarded(cmd, cwd=tf_dir)
                ok = r.returncode == 0
                if ok:
                    # Remove the file so a later apply does not recreate it.
                    tf_path.unlink(missing_ok=True)
                return ok
            if execution_type == "kubernetes":
                k8s_path = self.output_dir / "kubernetes" / Path(file_path).name
                r = self._apply_guarded(["kubectl", "delete", "-f", str(k8s_path)])
                return r.returncode == 0
            return True
        except (_ApplyBlocked, subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return False

    def _applied_infra_steps(self, cycle: RemediationCycle) -> list[dict[str, Any]]:
        """Steps that were actually applied live to real infra (for rollback)."""
        return [
            e for e in cycle.execution_log
            if e.get("status") == "success"
            and e.get("execution_type") in ("terraform", "kubernetes")
        ]

    def _verify(
        self, cycle: RemediationCycle, graph: InfraGraph
    ) -> RemediationCycle:
        """Re-scan and re-simulate to verify improvement."""
        # A pre-flight hard-stop already blocked execution; do NOT reset the
        # status (which would let the cycle reach "completed") or re-scan.
        if cycle.status == "blocked":
            cycle.completed_at = datetime.now(timezone.utc).isoformat()
            self._save_cycle(cycle)
            return cycle

        cycle.status = "verifying"

        try:
            fresh_graph = self._load_or_discover()
            final_score = fresh_graph.resilience_score()
        except Exception:
            # If we can't re-discover, use the predicted score
            final_score = cycle.simulated_score

        cycle.final_score = final_score
        cycle.improvement_achieved = final_score - cycle.initial_score

        if cycle.improvement_achieved < 0:
            applied = self._applied_infra_steps(cycle)
            if not applied:
                # Nothing was applied to real infra (dry-run / preview), so there
                # is nothing to roll back. Do NOT claim "rolled_back" — the score
                # moved for reasons outside this cycle's changes.
                cycle.status = "regressed"
                cycle.report_summary = (
                    f"Score decreased from {cycle.initial_score:.1f} to "
                    f"{final_score:.1f}, but no changes were applied (preview only); "
                    "nothing to roll back."
                )
            else:
                # Real changes were applied: actually undo them and report whether
                # every undo succeeded.
                results = [
                    self._rollback_step(e["execution_type"], e.get("file_path", ""))
                    for e in applied
                ]
                if all(results):
                    cycle.status = "rolled_back"
                    cycle.report_summary = (
                        f"Rolled back {len(applied)} applied step(s): score "
                        f"decreased from {cycle.initial_score:.1f} to {final_score:.1f}."
                    )
                else:
                    failed = sum(1 for ok in results if not ok)
                    cycle.status = "rollback_failed"
                    cycle.report_summary = (
                        f"REGRESSION with FAILED ROLLBACK: score decreased from "
                        f"{cycle.initial_score:.1f} to {final_score:.1f}; "
                        f"{failed} of {len(applied)} applied step(s) could not be "
                        "undone — changes REMAIN APPLIED, manual intervention required."
                    )
                    logger.error(cycle.report_summary)
        else:
            cycle.status = "completed"

        cycle.completed_at = datetime.now(timezone.utc).isoformat()
        self._save_cycle(cycle)
        return cycle

    def _generate_report(self, cycle: RemediationCycle) -> RemediationCycle:
        """Generate human-readable and machine-readable reports."""
        # Build summary
        improvement = cycle.improvement_achieved or 0.0
        final = cycle.final_score or cycle.simulated_score
        executed = sum(
            1
            for e in cycle.execution_log
            if e.get("status") in ("success", "dry_run")
        )
        blocked = sum(
            1 for e in cycle.execution_log if e.get("status") == "blocked"
        )
        failed = sum(
            1 for e in cycle.execution_log if e.get("status") == "failed"
        )

        mode = "LIVE" if self._auto_apply_allowed() else "DRY-RUN"

        generic = (
            f"[{mode}] Remediation cycle {cycle.id}: "
            f"Score {cycle.initial_score:.1f} -> {final:.1f} "
            f"(+{improvement:.1f}). "
            f"Steps: {executed} executed, {blocked} blocked, {failed} failed. "
            f"Issues found: {len(cycle.issues_found)}. "
            f"Cost: {cycle.estimated_cost}"
        )
        # Preserve critical warnings (failed rollback / regression / hard-stop
        # block) rather than overwriting them with the generic summary.
        if cycle.status in ("rollback_failed", "regressed", "blocked") and cycle.report_summary:
            cycle.report_summary = f"{cycle.report_summary} | {generic}"
        else:
            cycle.report_summary = generic

        # Save markdown report
        md = self._render_markdown_report(cycle)
        md_path = (
            self._reports_dir / f"cycle-{cycle.id}.md"
        )
        md_path.write_text(md, encoding="utf-8")

        # Save JSON report
        json_path = self._reports_dir / f"cycle-{cycle.id}.json"
        json_path.write_text(
            json.dumps(cycle.to_dict(), indent=2), encoding="utf-8"
        )

        return cycle

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save_cycle(self, cycle: RemediationCycle) -> None:
        """Persist cycle state for later approval."""
        path = self._cycles_dir / f"{cycle.id}.json"
        path.write_text(
            json.dumps(cycle.to_dict(), indent=2), encoding="utf-8"
        )

    def _load_cycle(self, cycle_id: str) -> RemediationCycle:
        """Load persisted cycle state."""
        path = self._cycles_dir / f"{cycle_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"Cycle not found: {cycle_id}")
        data = json.loads(path.read_text(encoding="utf-8"))
        return self._dict_to_cycle(data)

    @staticmethod
    def _dict_to_cycle(data: dict[str, Any]) -> RemediationCycle:
        """Reconstruct a RemediationCycle from a dict."""
        return RemediationCycle(
            id=data["id"],
            started_at=data["started_at"],
            completed_at=data.get("completed_at"),
            status=data.get("status", "unknown"),
            initial_score=data.get("initial_score", 0.0),
            issues_found=data.get("issues_found", []),
            remediation_plan=data.get("remediation_plan"),
            estimated_improvement=data.get("estimated_improvement", 0.0),
            estimated_cost=data.get("estimated_cost", "$0.00"),
            simulation_passed=data.get("simulation_passed", False),
            simulated_score=data.get("simulated_score", 0.0),
            side_effects=data.get("side_effects", []),
            ratchet_state=data.get("ratchet_state", {}),
            execution_log=data.get("execution_log", []),
            final_score=data.get("final_score"),
            improvement_achieved=data.get("improvement_achieved"),
            report_summary=data.get("report_summary", ""),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _plan_to_steps(plan: Any) -> list[_PlanStep]:
        """Convert an IaC RemediationPlan to a list of execution steps."""
        steps: list[_PlanStep] = []
        for f in plan.files:
            # Determine execution type from file extension
            if f.path.endswith(".tf"):
                exec_type = "terraform"
            elif f.path.endswith((".yaml", ".yml")):
                exec_type = "kubernetes"
            else:
                exec_type = "script"

            # Map phase to risk level
            if f.phase == 1:
                risk = "high"
            elif f.phase == 2:
                risk = "medium"
            else:
                risk = "low"

            steps.append(
                _PlanStep(
                    description=f.description,
                    risk_level=risk,
                    file_path=f.path,
                    content=f.content,
                    execution_type=exec_type,
                )
            )
        return steps

    @staticmethod
    def _step_permissions(step: _PlanStep) -> set[str]:
        """Determine the permissions required for a step."""
        required: set[str] = {"write:internal"}

        if step.execution_type in ("terraform", "aws_cli"):
            required.add("execute:tool")

        if step.risk_level in ("high", "critical"):
            required.add("read:internal")

        return required

    def _render_markdown_report(self, cycle: RemediationCycle) -> str:
        """Render a markdown report for a remediation cycle."""
        mode = "LIVE" if self._auto_apply_allowed() else "DRY-RUN"
        improvement = cycle.improvement_achieved or 0.0
        final = cycle.final_score or cycle.simulated_score

        lines: list[str] = []
        lines.append(f"# FaultRay Remediation Report — Cycle {cycle.id}")
        lines.append("")
        lines.append(f"**Mode:** {mode}")
        lines.append(f"**Started:** {cycle.started_at}")
        lines.append(f"**Completed:** {cycle.completed_at or 'N/A'}")
        lines.append(f"**Status:** {cycle.status}")
        lines.append("")
        lines.append("## Score")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Initial Score | {cycle.initial_score:.1f}/100 |")
        lines.append(f"| Simulated Score | {cycle.simulated_score:.1f}/100 |")
        lines.append(f"| Final Score | {final:.1f}/100 |")
        lines.append(f"| Improvement | +{improvement:.1f} |")
        lines.append(f"| Estimated Cost | {cycle.estimated_cost} |")
        lines.append("")

        if cycle.issues_found:
            lines.append("## Issues Found")
            lines.append("")
            lines.append("| # | Description | Priority | Components |")
            lines.append("|---|-------------|----------|------------|")
            for i, issue in enumerate(cycle.issues_found, 1):
                desc = issue.get("description", "")
                pri = issue.get("priority", "")
                comps = ", ".join(issue.get("affected_components", []))
                lines.append(f"| {i} | {desc} | {pri} | {comps} |")
            lines.append("")

        if cycle.execution_log:
            lines.append("## Execution Log")
            lines.append("")
            lines.append("| Step | Status | Details |")
            lines.append("|------|--------|---------|")
            for entry in cycle.execution_log:
                step_desc = entry.get("step", "")
                status = entry.get("status", "")
                detail = entry.get("output", entry.get("reason", ""))
                lines.append(f"| {step_desc} | {status} | {detail} |")
            lines.append("")

        if cycle.ratchet_state:
            lines.append("## Ratchet State")
            lines.append("")
            level = cycle.ratchet_state.get("final_level", "N/A")
            perms = cycle.ratchet_state.get("remaining_permissions", [])
            lines.append(f"- **Final sensitivity level:** {level}")
            lines.append(f"- **Remaining permissions:** {', '.join(perms)}")
            lines.append("")

        lines.append("---")
        lines.append("*Generated by FaultRay Autonomous Remediation Agent*")

        return "\n".join(lines)
