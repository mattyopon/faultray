"""Chaos Experiment Designer - Programmatic multi-step chaos experiment builder.

Provides a structured way to design, validate, run, and report on
custom chaos experiments with preconditions, fault-injection actions,
assertions, and rollback plans.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from infrasim.model.components import ComponentType, HealthStatus
from infrasim.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ExperimentPhase(str, Enum):
    """Lifecycle phase of an experiment step."""

    SETUP = "setup"
    INJECT = "inject"
    OBSERVE = "observe"
    VERIFY = "verify"
    ROLLBACK = "rollback"


class ActionType(str, Enum):
    """Types of chaos actions that can be injected."""

    KILL_COMPONENT = "kill_component"
    DEGRADE_COMPONENT = "degrade_component"
    SPIKE_TRAFFIC = "spike_traffic"
    PARTITION_NETWORK = "partition_network"
    CORRUPT_DATA = "corrupt_data"
    DELAY_RESPONSES = "delay_responses"
    EXHAUST_RESOURCES = "exhaust_resources"
    FAILOVER_TRIGGER = "failover_trigger"


class AssertionType(str, Enum):
    """Types of assertions that can be checked after chaos injection."""

    HEALTH_CHECK = "health_check"
    LATENCY_BELOW = "latency_below"
    ERROR_RATE_BELOW = "error_rate_below"
    AVAILABILITY_ABOVE = "availability_above"
    RECOVERY_WITHIN = "recovery_within"
    CASCADE_CONTAINED = "cascade_contained"
    NO_DATA_LOSS = "no_data_loss"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ExperimentAction:
    """A single chaos action within an experiment step."""

    action_type: ActionType
    target_component_id: str
    parameters: dict[str, Any] = field(default_factory=dict)
    duration_seconds: int = 60


@dataclass
class ExperimentAssertion:
    """An assertion to verify system behaviour during/after chaos."""

    assertion_type: AssertionType
    target_component_id: str | None = None
    threshold: float = 0.0
    description: str = ""


@dataclass
class ExperimentStep:
    """A single step within an experiment, tied to a phase."""

    phase: ExperimentPhase
    actions: list[ExperimentAction] = field(default_factory=list)
    assertions: list[ExperimentAssertion] = field(default_factory=list)
    wait_seconds: int = 0
    description: str = ""


@dataclass
class ExperimentDesign:
    """Complete design of a chaos experiment."""

    name: str
    description: str
    hypothesis: str
    steps: list[ExperimentStep] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    blast_radius_limit: int = 5
    rollback_plan: list[ExperimentAction] = field(default_factory=list)
    created_at: str = ""


@dataclass
class ExperimentResult:
    """Result of running an experiment."""

    design: ExperimentDesign
    passed_assertions: list[tuple[ExperimentAssertion, str]] = field(default_factory=list)
    failed_assertions: list[tuple[ExperimentAssertion, str]] = field(default_factory=list)
    observations: list[str] = field(default_factory=list)
    conclusion: str = ""
    risk_score: float = 0.0


# ---------------------------------------------------------------------------
# Built-in templates
# ---------------------------------------------------------------------------

_TEMPLATES: dict[str, dict[str, Any]] = {
    "zone-failure": {
        "name": "Zone Failure",
        "description": "Simulate an availability zone outage by killing all components in a zone.",
        "hypothesis": "The system should survive the loss of a single availability zone with minimal degradation.",
        "tags": ["availability", "zone", "dr"],
        "blast_radius_limit": 10,
        "steps": [
            {
                "phase": "setup",
                "description": "Verify all components are healthy before injection.",
                "actions": [],
                "assertions": [
                    {"assertion_type": "health_check", "target_component_id": None, "threshold": 1.0, "description": "All components healthy"},
                ],
                "wait_seconds": 0,
            },
            {
                "phase": "inject",
                "description": "Kill components to simulate zone outage.",
                "actions": [
                    {"action_type": "kill_component", "target_component_id": "__FIRST_SERVER__", "parameters": {"reason": "zone_outage"}, "duration_seconds": 300},
                ],
                "assertions": [],
                "wait_seconds": 5,
            },
            {
                "phase": "observe",
                "description": "Wait for system to react to zone failure.",
                "actions": [],
                "assertions": [],
                "wait_seconds": 30,
            },
            {
                "phase": "verify",
                "description": "Verify system availability remains above threshold.",
                "actions": [],
                "assertions": [
                    {"assertion_type": "availability_above", "target_component_id": None, "threshold": 50.0, "description": "System availability above 50%"},
                    {"assertion_type": "cascade_contained", "target_component_id": None, "threshold": 5.0, "description": "Cascade contained within 5 components"},
                ],
                "wait_seconds": 0,
            },
            {
                "phase": "rollback",
                "description": "Restore zone components.",
                "actions": [],
                "assertions": [],
                "wait_seconds": 0,
            },
        ],
        "rollback_plan": [
            {"action_type": "failover_trigger", "target_component_id": "__FIRST_SERVER__", "parameters": {"restore": True}, "duration_seconds": 0},
        ],
    },
    "database-failover": {
        "name": "Database Failover",
        "description": "Kill primary database and verify automatic failover to replica.",
        "hypothesis": "Database failover should complete within recovery time and maintain data integrity.",
        "tags": ["database", "failover", "ha"],
        "blast_radius_limit": 5,
        "steps": [
            {
                "phase": "setup",
                "description": "Verify database is healthy and replication is active.",
                "actions": [],
                "assertions": [
                    {"assertion_type": "health_check", "target_component_id": "__FIRST_DB__", "threshold": 1.0, "description": "Primary DB healthy"},
                ],
                "wait_seconds": 0,
            },
            {
                "phase": "inject",
                "description": "Kill the primary database.",
                "actions": [
                    {"action_type": "kill_component", "target_component_id": "__FIRST_DB__", "parameters": {"reason": "failover_test"}, "duration_seconds": 120},
                ],
                "assertions": [],
                "wait_seconds": 5,
            },
            {
                "phase": "observe",
                "description": "Wait for failover to occur.",
                "actions": [],
                "assertions": [],
                "wait_seconds": 60,
            },
            {
                "phase": "verify",
                "description": "Verify failover completed and data is intact.",
                "actions": [],
                "assertions": [
                    {"assertion_type": "recovery_within", "target_component_id": "__FIRST_DB__", "threshold": 120.0, "description": "Recovery within 120 seconds"},
                    {"assertion_type": "no_data_loss", "target_component_id": "__FIRST_DB__", "threshold": 0.0, "description": "No data loss during failover"},
                ],
                "wait_seconds": 0,
            },
            {
                "phase": "rollback",
                "description": "Restore primary database.",
                "actions": [],
                "assertions": [],
                "wait_seconds": 0,
            },
        ],
        "rollback_plan": [
            {"action_type": "failover_trigger", "target_component_id": "__FIRST_DB__", "parameters": {"restore": True}, "duration_seconds": 0},
        ],
    },
    "cache-stampede": {
        "name": "Cache Stampede",
        "description": "Kill cache layer and verify the database handles the thundering herd.",
        "hypothesis": "When cache is lost, the database should handle increased load without going down.",
        "tags": ["cache", "stampede", "thundering-herd"],
        "blast_radius_limit": 5,
        "steps": [
            {
                "phase": "setup",
                "description": "Verify cache and database are healthy.",
                "actions": [],
                "assertions": [
                    {"assertion_type": "health_check", "target_component_id": None, "threshold": 1.0, "description": "All components healthy"},
                ],
                "wait_seconds": 0,
            },
            {
                "phase": "inject",
                "description": "Kill the cache layer.",
                "actions": [
                    {"action_type": "kill_component", "target_component_id": "__FIRST_CACHE__", "parameters": {"reason": "cache_stampede_test"}, "duration_seconds": 180},
                ],
                "assertions": [],
                "wait_seconds": 5,
            },
            {
                "phase": "observe",
                "description": "Observe database behaviour under increased load.",
                "actions": [],
                "assertions": [],
                "wait_seconds": 30,
            },
            {
                "phase": "verify",
                "description": "Verify database survived the thundering herd.",
                "actions": [],
                "assertions": [
                    {"assertion_type": "health_check", "target_component_id": "__FIRST_DB__", "threshold": 1.0, "description": "Database survived"},
                    {"assertion_type": "error_rate_below", "target_component_id": None, "threshold": 10.0, "description": "Error rate below 10%"},
                ],
                "wait_seconds": 0,
            },
            {
                "phase": "rollback",
                "description": "Restore cache.",
                "actions": [],
                "assertions": [],
                "wait_seconds": 0,
            },
        ],
        "rollback_plan": [
            {"action_type": "failover_trigger", "target_component_id": "__FIRST_CACHE__", "parameters": {"restore": True}, "duration_seconds": 0},
        ],
    },
    "network-partition": {
        "name": "Network Partition",
        "description": "Create a network partition and verify graceful degradation.",
        "hypothesis": "The system should degrade gracefully during a network partition without data corruption.",
        "tags": ["network", "partition", "split-brain"],
        "blast_radius_limit": 8,
        "steps": [
            {
                "phase": "setup",
                "description": "Verify network connectivity.",
                "actions": [],
                "assertions": [
                    {"assertion_type": "health_check", "target_component_id": None, "threshold": 1.0, "description": "All components healthy"},
                ],
                "wait_seconds": 0,
            },
            {
                "phase": "inject",
                "description": "Partition the network.",
                "actions": [
                    {"action_type": "partition_network", "target_component_id": "__FIRST_SERVER__", "parameters": {"partition_type": "full"}, "duration_seconds": 120},
                ],
                "assertions": [],
                "wait_seconds": 5,
            },
            {
                "phase": "observe",
                "description": "Observe system behaviour during partition.",
                "actions": [],
                "assertions": [],
                "wait_seconds": 30,
            },
            {
                "phase": "verify",
                "description": "Verify graceful degradation.",
                "actions": [],
                "assertions": [
                    {"assertion_type": "availability_above", "target_component_id": None, "threshold": 30.0, "description": "Partial availability maintained"},
                    {"assertion_type": "no_data_loss", "target_component_id": None, "threshold": 0.0, "description": "No data loss during partition"},
                ],
                "wait_seconds": 0,
            },
            {
                "phase": "rollback",
                "description": "Restore network connectivity.",
                "actions": [],
                "assertions": [],
                "wait_seconds": 0,
            },
        ],
        "rollback_plan": [
            {"action_type": "failover_trigger", "target_component_id": "__FIRST_SERVER__", "parameters": {"restore": True}, "duration_seconds": 0},
        ],
    },
    "cascading-failure": {
        "name": "Cascading Failure",
        "description": "Kill a critical component and verify the blast radius is contained.",
        "hypothesis": "Failure of a critical component should not cascade beyond the blast radius limit.",
        "tags": ["cascade", "blast-radius", "critical"],
        "blast_radius_limit": 5,
        "steps": [
            {
                "phase": "setup",
                "description": "Identify critical component and verify baseline.",
                "actions": [],
                "assertions": [
                    {"assertion_type": "health_check", "target_component_id": None, "threshold": 1.0, "description": "All components healthy"},
                ],
                "wait_seconds": 0,
            },
            {
                "phase": "inject",
                "description": "Kill the most critical component.",
                "actions": [
                    {"action_type": "kill_component", "target_component_id": "__FIRST_SERVER__", "parameters": {"reason": "cascade_test"}, "duration_seconds": 120},
                ],
                "assertions": [],
                "wait_seconds": 5,
            },
            {
                "phase": "observe",
                "description": "Observe cascade propagation.",
                "actions": [],
                "assertions": [],
                "wait_seconds": 30,
            },
            {
                "phase": "verify",
                "description": "Verify blast radius is contained.",
                "actions": [],
                "assertions": [
                    {"assertion_type": "cascade_contained", "target_component_id": None, "threshold": 5.0, "description": "Cascade contained within blast radius"},
                    {"assertion_type": "availability_above", "target_component_id": None, "threshold": 50.0, "description": "System still partially available"},
                ],
                "wait_seconds": 0,
            },
            {
                "phase": "rollback",
                "description": "Restore the failed component.",
                "actions": [],
                "assertions": [],
                "wait_seconds": 0,
            },
        ],
        "rollback_plan": [
            {"action_type": "failover_trigger", "target_component_id": "__FIRST_SERVER__", "parameters": {"restore": True}, "duration_seconds": 0},
        ],
    },
    "traffic-spike": {
        "name": "Traffic Spike",
        "description": "Simulate a 10x traffic increase and verify autoscaling handles it.",
        "hypothesis": "Autoscaling should engage and maintain acceptable latency during a 10x traffic spike.",
        "tags": ["traffic", "autoscaling", "capacity"],
        "blast_radius_limit": 3,
        "steps": [
            {
                "phase": "setup",
                "description": "Verify autoscaling is configured and baseline latency.",
                "actions": [],
                "assertions": [
                    {"assertion_type": "health_check", "target_component_id": None, "threshold": 1.0, "description": "All components healthy"},
                ],
                "wait_seconds": 0,
            },
            {
                "phase": "inject",
                "description": "Spike traffic to 10x normal.",
                "actions": [
                    {"action_type": "spike_traffic", "target_component_id": "__FIRST_LB__", "parameters": {"multiplier": 10}, "duration_seconds": 300},
                ],
                "assertions": [],
                "wait_seconds": 5,
            },
            {
                "phase": "observe",
                "description": "Observe autoscaling behaviour.",
                "actions": [],
                "assertions": [],
                "wait_seconds": 60,
            },
            {
                "phase": "verify",
                "description": "Verify system handled the traffic spike.",
                "actions": [],
                "assertions": [
                    {"assertion_type": "latency_below", "target_component_id": None, "threshold": 1000.0, "description": "Latency below 1000ms"},
                    {"assertion_type": "error_rate_below", "target_component_id": None, "threshold": 5.0, "description": "Error rate below 5%"},
                ],
                "wait_seconds": 0,
            },
            {
                "phase": "rollback",
                "description": "Return traffic to normal levels.",
                "actions": [],
                "assertions": [],
                "wait_seconds": 0,
            },
        ],
        "rollback_plan": [
            {"action_type": "spike_traffic", "target_component_id": "__FIRST_LB__", "parameters": {"multiplier": 1}, "duration_seconds": 0},
        ],
    },
    "dependency-timeout": {
        "name": "Dependency Timeout",
        "description": "Simulate external API timeout and verify circuit breaker activation.",
        "hypothesis": "Circuit breaker should open within the configured threshold, protecting upstream services.",
        "tags": ["dependency", "timeout", "circuit-breaker"],
        "blast_radius_limit": 4,
        "steps": [
            {
                "phase": "setup",
                "description": "Verify external dependency is reachable.",
                "actions": [],
                "assertions": [
                    {"assertion_type": "health_check", "target_component_id": None, "threshold": 1.0, "description": "All components healthy"},
                ],
                "wait_seconds": 0,
            },
            {
                "phase": "inject",
                "description": "Inject response delay on external API.",
                "actions": [
                    {"action_type": "delay_responses", "target_component_id": "__FIRST_EXT__", "parameters": {"delay_ms": 30000}, "duration_seconds": 120},
                ],
                "assertions": [],
                "wait_seconds": 5,
            },
            {
                "phase": "observe",
                "description": "Observe circuit breaker behaviour.",
                "actions": [],
                "assertions": [],
                "wait_seconds": 30,
            },
            {
                "phase": "verify",
                "description": "Verify circuit breaker activated.",
                "actions": [],
                "assertions": [
                    {"assertion_type": "latency_below", "target_component_id": None, "threshold": 5000.0, "description": "Upstream latency stays below 5s"},
                    {"assertion_type": "error_rate_below", "target_component_id": None, "threshold": 20.0, "description": "Error rate below 20%"},
                ],
                "wait_seconds": 0,
            },
            {
                "phase": "rollback",
                "description": "Remove response delay.",
                "actions": [],
                "assertions": [],
                "wait_seconds": 0,
            },
        ],
        "rollback_plan": [
            {"action_type": "delay_responses", "target_component_id": "__FIRST_EXT__", "parameters": {"delay_ms": 0}, "duration_seconds": 0},
        ],
    },
    "data-corruption": {
        "name": "Data Corruption",
        "description": "Corrupt data source and verify data integrity checks detect it.",
        "hypothesis": "Data integrity checks should detect corruption and prevent propagation to downstream services.",
        "tags": ["data", "corruption", "integrity"],
        "blast_radius_limit": 3,
        "steps": [
            {
                "phase": "setup",
                "description": "Verify data integrity baseline.",
                "actions": [],
                "assertions": [
                    {"assertion_type": "health_check", "target_component_id": None, "threshold": 1.0, "description": "All components healthy"},
                    {"assertion_type": "no_data_loss", "target_component_id": None, "threshold": 0.0, "description": "Data integrity baseline"},
                ],
                "wait_seconds": 0,
            },
            {
                "phase": "inject",
                "description": "Corrupt data source.",
                "actions": [
                    {"action_type": "corrupt_data", "target_component_id": "__FIRST_DB__", "parameters": {"corruption_type": "random_bytes"}, "duration_seconds": 60},
                ],
                "assertions": [],
                "wait_seconds": 5,
            },
            {
                "phase": "observe",
                "description": "Observe system reaction to corrupted data.",
                "actions": [],
                "assertions": [],
                "wait_seconds": 30,
            },
            {
                "phase": "verify",
                "description": "Verify corruption was detected and contained.",
                "actions": [],
                "assertions": [
                    {"assertion_type": "no_data_loss", "target_component_id": None, "threshold": 0.0, "description": "Data integrity maintained downstream"},
                    {"assertion_type": "cascade_contained", "target_component_id": None, "threshold": 3.0, "description": "Corruption impact contained"},
                ],
                "wait_seconds": 0,
            },
            {
                "phase": "rollback",
                "description": "Restore clean data.",
                "actions": [],
                "assertions": [],
                "wait_seconds": 0,
            },
        ],
        "rollback_plan": [
            {"action_type": "failover_trigger", "target_component_id": "__FIRST_DB__", "parameters": {"restore": True}, "duration_seconds": 0},
        ],
    },
}

# Mapping of placeholder targets to ComponentType for template resolution
_PLACEHOLDER_TYPE_MAP: dict[str, ComponentType] = {
    "__FIRST_SERVER__": ComponentType.APP_SERVER,
    "__FIRST_DB__": ComponentType.DATABASE,
    "__FIRST_CACHE__": ComponentType.CACHE,
    "__FIRST_LB__": ComponentType.LOAD_BALANCER,
    "__FIRST_EXT__": ComponentType.EXTERNAL_API,
}


# ---------------------------------------------------------------------------
# ExperimentDesigner
# ---------------------------------------------------------------------------

class ExperimentDesigner:
    """Designs, validates, runs, and reports on chaos experiments."""

    def __init__(self) -> None:
        self._experiment_names: set[str] = set()

    # ------------------------------------------------------------------
    # Creation helpers
    # ------------------------------------------------------------------

    def create_experiment(
        self,
        name: str,
        description: str,
        hypothesis: str,
    ) -> ExperimentDesign:
        """Create a new empty experiment design."""
        if name in self._experiment_names:
            raise ValueError(f"Duplicate experiment name: '{name}'")
        self._experiment_names.add(name)
        return ExperimentDesign(
            name=name,
            description=description,
            hypothesis=hypothesis,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def add_step(
        self,
        design: ExperimentDesign,
        phase: ExperimentPhase,
        actions: list[ExperimentAction] | None = None,
        assertions: list[ExperimentAssertion] | None = None,
        wait_seconds: int = 0,
        description: str = "",
    ) -> ExperimentDesign:
        """Add a step to an existing experiment design and return it."""
        step = ExperimentStep(
            phase=phase,
            actions=actions or [],
            assertions=assertions or [],
            wait_seconds=wait_seconds,
            description=description,
        )
        design.steps.append(step)
        return design

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_experiment(
        self,
        design: ExperimentDesign,
        graph: InfraGraph,
    ) -> list[str]:
        """Validate an experiment design against a graph.

        Returns a list of validation error messages.  An empty list means
        the experiment is valid.
        """
        errors: list[str] = []

        # 1. Must have at least one VERIFY step
        has_verify = any(
            step.phase == ExperimentPhase.VERIFY for step in design.steps
        )
        if not has_verify:
            errors.append("Experiment must have at least one VERIFY step.")

        # 2. All target component IDs must exist in the graph
        component_ids = set(graph.components.keys())
        for step in design.steps:
            for action in step.actions:
                if action.target_component_id not in component_ids:
                    errors.append(
                        f"Action target '{action.target_component_id}' "
                        f"does not exist in the graph."
                    )
            for assertion in step.assertions:
                if (
                    assertion.target_component_id is not None
                    and assertion.target_component_id not in component_ids
                ):
                    errors.append(
                        f"Assertion target '{assertion.target_component_id}' "
                        f"does not exist in the graph."
                    )

        # Validate rollback plan targets
        for action in design.rollback_plan:
            if action.target_component_id not in component_ids:
                errors.append(
                    f"Rollback action target '{action.target_component_id}' "
                    f"does not exist in the graph."
                )

        # 3. Blast radius limit check
        injected_targets: set[str] = set()
        for step in design.steps:
            if step.phase == ExperimentPhase.INJECT:
                for action in step.actions:
                    injected_targets.add(action.target_component_id)

        estimated_blast_radius = 0
        for target_id in injected_targets:
            if target_id in component_ids:
                affected = graph.get_all_affected(target_id)
                estimated_blast_radius += len(affected) + 1  # +1 for the target itself

        if estimated_blast_radius > design.blast_radius_limit:
            errors.append(
                f"Estimated blast radius ({estimated_blast_radius}) exceeds "
                f"limit ({design.blast_radius_limit})."
            )

        # 4. Rollback plan must cover all injected actions
        injected_action_targets: set[str] = set()
        for step in design.steps:
            if step.phase == ExperimentPhase.INJECT:
                for action in step.actions:
                    injected_action_targets.add(action.target_component_id)

        rollback_targets: set[str] = set()
        for action in design.rollback_plan:
            rollback_targets.add(action.target_component_id)

        # Also count ROLLBACK phase actions
        for step in design.steps:
            if step.phase == ExperimentPhase.ROLLBACK:
                for action in step.actions:
                    rollback_targets.add(action.target_component_id)

        uncovered = injected_action_targets - rollback_targets
        if uncovered:
            errors.append(
                f"Rollback plan does not cover injected targets: "
                f"{', '.join(sorted(uncovered))}."
            )

        return errors

    # ------------------------------------------------------------------
    # Experiment execution (simulation)
    # ------------------------------------------------------------------

    def run_experiment(
        self,
        design: ExperimentDesign,
        graph: InfraGraph,
    ) -> ExperimentResult:
        """Simulate running the experiment against the graph.

        The graph is deep-copied so the original is not modified.
        """
        sim_graph = self._copy_graph(graph)
        original_graph = self._copy_graph(graph)

        passed: list[tuple[ExperimentAssertion, str]] = []
        failed: list[tuple[ExperimentAssertion, str]] = []
        observations: list[str] = []

        for step in design.steps:
            if step.phase == ExperimentPhase.SETUP:
                obs = self._run_setup(step, sim_graph)
                observations.extend(obs)
                # Check SETUP assertions
                for assertion in step.assertions:
                    ok, msg = self._check_assertion(assertion, sim_graph, original_graph)
                    if ok:
                        passed.append((assertion, msg))
                    else:
                        failed.append((assertion, msg))

            elif step.phase == ExperimentPhase.INJECT:
                obs = self._run_inject(step, sim_graph)
                observations.extend(obs)

            elif step.phase == ExperimentPhase.OBSERVE:
                obs = self._run_observe(step, sim_graph)
                observations.extend(obs)

            elif step.phase == ExperimentPhase.VERIFY:
                for assertion in step.assertions:
                    ok, msg = self._check_assertion(assertion, sim_graph, original_graph)
                    if ok:
                        passed.append((assertion, msg))
                    else:
                        failed.append((assertion, msg))
                observations.append(
                    f"VERIFY: {len([a for a in step.assertions])} assertions checked."
                )

            elif step.phase == ExperimentPhase.ROLLBACK:
                obs = self._run_rollback(step, sim_graph, original_graph)
                observations.extend(obs)

        # Also run the top-level rollback plan
        if design.rollback_plan:
            for action in design.rollback_plan:
                comp = sim_graph.get_component(action.target_component_id)
                if comp:
                    orig_comp = original_graph.get_component(action.target_component_id)
                    if orig_comp:
                        comp.health = orig_comp.health
            observations.append("Rollback plan executed.")

        # Compute risk score and conclusion
        total_assertions = len(passed) + len(failed)
        if total_assertions > 0:
            pass_rate = len(passed) / total_assertions
            risk_score = round((1.0 - pass_rate) * 10.0, 1)
        else:
            risk_score = 5.0  # Unknown risk

        if len(failed) == 0:
            conclusion = "PASSED: All assertions passed. The hypothesis is supported."
        elif len(failed) <= len(passed):
            conclusion = (
                f"PARTIAL: {len(failed)} of {total_assertions} assertions failed. "
                f"The hypothesis is partially supported."
            )
        else:
            conclusion = (
                f"FAILED: {len(failed)} of {total_assertions} assertions failed. "
                f"The hypothesis is not supported."
            )

        return ExperimentResult(
            design=design,
            passed_assertions=passed,
            failed_assertions=failed,
            observations=observations,
            conclusion=conclusion,
            risk_score=risk_score,
        )

    # ------------------------------------------------------------------
    # Templates
    # ------------------------------------------------------------------

    def from_template(self, template_name: str) -> ExperimentDesign:
        """Create an experiment design from a built-in template."""
        if template_name not in _TEMPLATES:
            available = ", ".join(sorted(_TEMPLATES.keys()))
            raise ValueError(
                f"Unknown template '{template_name}'. "
                f"Available templates: {available}"
            )

        tpl = _TEMPLATES[template_name]
        design = ExperimentDesign(
            name=tpl["name"],
            description=tpl["description"],
            hypothesis=tpl["hypothesis"],
            tags=list(tpl.get("tags", [])),
            blast_radius_limit=tpl.get("blast_radius_limit", 5),
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        for step_data in tpl.get("steps", []):
            actions = [
                ExperimentAction(
                    action_type=ActionType(a["action_type"]),
                    target_component_id=a["target_component_id"],
                    parameters=dict(a.get("parameters", {})),
                    duration_seconds=a.get("duration_seconds", 60),
                )
                for a in step_data.get("actions", [])
            ]
            assertions = [
                ExperimentAssertion(
                    assertion_type=AssertionType(a["assertion_type"]),
                    target_component_id=a.get("target_component_id"),
                    threshold=a.get("threshold", 0.0),
                    description=a.get("description", ""),
                )
                for a in step_data.get("assertions", [])
            ]
            design.steps.append(
                ExperimentStep(
                    phase=ExperimentPhase(step_data["phase"]),
                    actions=actions,
                    assertions=assertions,
                    wait_seconds=step_data.get("wait_seconds", 0),
                    description=step_data.get("description", ""),
                )
            )

        design.rollback_plan = [
            ExperimentAction(
                action_type=ActionType(a["action_type"]),
                target_component_id=a["target_component_id"],
                parameters=dict(a.get("parameters", {})),
                duration_seconds=a.get("duration_seconds", 0),
            )
            for a in tpl.get("rollback_plan", [])
        ]

        # Track the template name to prevent duplicates
        self._experiment_names.add(design.name)

        return design

    def list_templates(self) -> list[dict[str, str]]:
        """List available built-in experiment templates."""
        result: list[dict[str, str]] = []
        for key, tpl in _TEMPLATES.items():
            result.append({
                "key": key,
                "name": tpl["name"],
                "description": tpl["description"],
                "hypothesis": tpl["hypothesis"],
            })
        return result

    # ------------------------------------------------------------------
    # Export / Import
    # ------------------------------------------------------------------

    def export_experiment(self, design: ExperimentDesign) -> dict:
        """Export an experiment design as a JSON-serializable dict."""
        return {
            "name": design.name,
            "description": design.description,
            "hypothesis": design.hypothesis,
            "tags": list(design.tags),
            "blast_radius_limit": design.blast_radius_limit,
            "created_at": design.created_at,
            "steps": [
                {
                    "phase": step.phase.value,
                    "description": step.description,
                    "wait_seconds": step.wait_seconds,
                    "actions": [
                        {
                            "action_type": action.action_type.value,
                            "target_component_id": action.target_component_id,
                            "parameters": dict(action.parameters),
                            "duration_seconds": action.duration_seconds,
                        }
                        for action in step.actions
                    ],
                    "assertions": [
                        {
                            "assertion_type": assertion.assertion_type.value,
                            "target_component_id": assertion.target_component_id,
                            "threshold": assertion.threshold,
                            "description": assertion.description,
                        }
                        for assertion in step.assertions
                    ],
                }
                for step in design.steps
            ],
            "rollback_plan": [
                {
                    "action_type": action.action_type.value,
                    "target_component_id": action.target_component_id,
                    "parameters": dict(action.parameters),
                    "duration_seconds": action.duration_seconds,
                }
                for action in design.rollback_plan
            ],
        }

    def import_experiment(self, data: dict) -> ExperimentDesign:
        """Import an experiment design from a dict."""
        name = data["name"]
        if name in self._experiment_names:
            raise ValueError(f"Duplicate experiment name: '{name}'")
        design = ExperimentDesign(
            name=data["name"],
            description=data["description"],
            hypothesis=data["hypothesis"],
            tags=list(data.get("tags", [])),
            blast_radius_limit=data.get("blast_radius_limit", 5),
            created_at=data.get("created_at", ""),
        )

        for step_data in data.get("steps", []):
            actions = [
                ExperimentAction(
                    action_type=ActionType(a["action_type"]),
                    target_component_id=a["target_component_id"],
                    parameters=dict(a.get("parameters", {})),
                    duration_seconds=a.get("duration_seconds", 60),
                )
                for a in step_data.get("actions", [])
            ]
            assertions = [
                ExperimentAssertion(
                    assertion_type=AssertionType(a["assertion_type"]),
                    target_component_id=a.get("target_component_id"),
                    threshold=a.get("threshold", 0.0),
                    description=a.get("description", ""),
                )
                for a in step_data.get("assertions", [])
            ]
            design.steps.append(
                ExperimentStep(
                    phase=ExperimentPhase(step_data["phase"]),
                    actions=actions,
                    assertions=assertions,
                    wait_seconds=step_data.get("wait_seconds", 0),
                    description=step_data.get("description", ""),
                )
            )

        design.rollback_plan = [
            ExperimentAction(
                action_type=ActionType(a["action_type"]),
                target_component_id=a["target_component_id"],
                parameters=dict(a.get("parameters", {})),
                duration_seconds=a.get("duration_seconds", 0),
            )
            for a in data.get("rollback_plan", [])
        ]

        self._experiment_names.add(design.name)
        return design

    # ------------------------------------------------------------------
    # Report generation
    # ------------------------------------------------------------------

    def generate_report(self, result: ExperimentResult) -> str:
        """Generate a markdown report from an experiment result."""
        lines: list[str] = []
        d = result.design

        lines.append(f"# Chaos Experiment Report: {d.name}")
        lines.append("")
        lines.append(f"**Description:** {d.description}")
        lines.append(f"**Hypothesis:** {d.hypothesis}")
        lines.append(f"**Created:** {d.created_at}")
        if d.tags:
            lines.append(f"**Tags:** {', '.join(d.tags)}")
        lines.append(f"**Blast Radius Limit:** {d.blast_radius_limit}")
        lines.append("")

        # Conclusion
        lines.append("## Conclusion")
        lines.append("")
        lines.append(result.conclusion)
        lines.append(f"**Risk Score:** {result.risk_score}/10.0")
        lines.append("")

        # Assertions
        lines.append("## Assertions")
        lines.append("")
        if result.passed_assertions:
            lines.append("### Passed")
            lines.append("")
            for assertion, msg in result.passed_assertions:
                lines.append(f"- [PASS] {assertion.description}: {msg}")
            lines.append("")

        if result.failed_assertions:
            lines.append("### Failed")
            lines.append("")
            for assertion, msg in result.failed_assertions:
                lines.append(f"- [FAIL] {assertion.description}: {msg}")
            lines.append("")

        # Steps
        lines.append("## Experiment Steps")
        lines.append("")
        for i, step in enumerate(d.steps, 1):
            lines.append(f"### Step {i}: {step.phase.value.upper()} - {step.description}")
            if step.actions:
                lines.append(f"  Actions: {len(step.actions)}")
            if step.assertions:
                lines.append(f"  Assertions: {len(step.assertions)}")
            if step.wait_seconds > 0:
                lines.append(f"  Wait: {step.wait_seconds}s")
            lines.append("")

        # Observations
        if result.observations:
            lines.append("## Observations")
            lines.append("")
            for obs in result.observations:
                lines.append(f"- {obs}")
            lines.append("")

        # Rollback
        if d.rollback_plan:
            lines.append("## Rollback Plan")
            lines.append("")
            for action in d.rollback_plan:
                lines.append(
                    f"- {action.action_type.value} on {action.target_component_id}"
                )
            lines.append("")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Template resolution helpers
    # ------------------------------------------------------------------

    def resolve_template_targets(
        self,
        design: ExperimentDesign,
        graph: InfraGraph,
    ) -> ExperimentDesign:
        """Resolve placeholder target IDs in a template to real component IDs.

        Placeholders like ``__FIRST_DB__`` are replaced with the first
        component of the matching type found in the graph.
        """
        component_by_type: dict[ComponentType, str] = {}
        for comp_id, comp in graph.components.items():
            if comp.type not in component_by_type:
                component_by_type[comp.type] = comp_id

        def _resolve(target: str) -> str:
            if target in _PLACEHOLDER_TYPE_MAP:
                ctype = _PLACEHOLDER_TYPE_MAP[target]
                return component_by_type.get(ctype, target)
            return target

        for step in design.steps:
            for action in step.actions:
                action.target_component_id = _resolve(action.target_component_id)
            for assertion in step.assertions:
                if assertion.target_component_id is not None:
                    assertion.target_component_id = _resolve(assertion.target_component_id)

        for action in design.rollback_plan:
            action.target_component_id = _resolve(action.target_component_id)

        return design

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _copy_graph(graph: InfraGraph) -> InfraGraph:
        """Create a deep copy of an InfraGraph."""
        return copy.deepcopy(graph)

    @staticmethod
    def _run_setup(step: ExperimentStep, sim_graph: InfraGraph) -> list[str]:
        """Run SETUP phase: verify preconditions."""
        observations: list[str] = []
        healthy_count = sum(
            1 for c in sim_graph.components.values()
            if c.health == HealthStatus.HEALTHY
        )
        total = len(sim_graph.components)
        observations.append(
            f"SETUP: {healthy_count}/{total} components healthy."
        )
        return observations

    @staticmethod
    def _run_inject(step: ExperimentStep, sim_graph: InfraGraph) -> list[str]:
        """Run INJECT phase: apply chaos actions to the simulated graph."""
        observations: list[str] = []
        for action in step.actions:
            comp = sim_graph.get_component(action.target_component_id)
            if comp is None:
                observations.append(
                    f"INJECT: Target '{action.target_component_id}' not found, skipped."
                )
                continue

            if action.action_type == ActionType.KILL_COMPONENT:
                comp.health = HealthStatus.DOWN
                observations.append(
                    f"INJECT: Killed component '{action.target_component_id}'."
                )
                # Propagate to dependents
                affected = sim_graph.get_all_affected(action.target_component_id)
                for dep_id in affected:
                    dep_comp = sim_graph.get_component(dep_id)
                    if dep_comp and dep_comp.health == HealthStatus.HEALTHY:
                        dep_comp.health = HealthStatus.DEGRADED
                        observations.append(
                            f"INJECT: Component '{dep_id}' degraded due to cascade."
                        )

            elif action.action_type == ActionType.DEGRADE_COMPONENT:
                comp.health = HealthStatus.DEGRADED
                observations.append(
                    f"INJECT: Degraded component '{action.target_component_id}'."
                )

            elif action.action_type == ActionType.SPIKE_TRAFFIC:
                multiplier = action.parameters.get("multiplier", 10)
                comp.metrics.cpu_percent = min(100.0, comp.metrics.cpu_percent * float(multiplier))
                comp.metrics.memory_percent = min(100.0, comp.metrics.memory_percent * float(multiplier) * 0.5)
                if comp.metrics.cpu_percent > 90:
                    comp.health = HealthStatus.OVERLOADED
                observations.append(
                    f"INJECT: Traffic spike ({multiplier}x) on '{action.target_component_id}'."
                )

            elif action.action_type == ActionType.PARTITION_NETWORK:
                comp.health = HealthStatus.DOWN
                observations.append(
                    f"INJECT: Network partition on '{action.target_component_id}'."
                )
                affected = sim_graph.get_all_affected(action.target_component_id)
                for dep_id in affected:
                    dep_comp = sim_graph.get_component(dep_id)
                    if dep_comp and dep_comp.health == HealthStatus.HEALTHY:
                        dep_comp.health = HealthStatus.DEGRADED

            elif action.action_type == ActionType.CORRUPT_DATA:
                comp.health = HealthStatus.DEGRADED
                observations.append(
                    f"INJECT: Data corruption on '{action.target_component_id}'."
                )

            elif action.action_type == ActionType.DELAY_RESPONSES:
                delay_ms = action.parameters.get("delay_ms", 5000)
                comp.network.rtt_ms += float(delay_ms)
                if float(delay_ms) > 10000:
                    comp.health = HealthStatus.DEGRADED
                observations.append(
                    f"INJECT: Added {delay_ms}ms delay to '{action.target_component_id}'."
                )

            elif action.action_type == ActionType.EXHAUST_RESOURCES:
                comp.metrics.cpu_percent = 99.0
                comp.metrics.memory_percent = 98.0
                comp.health = HealthStatus.OVERLOADED
                observations.append(
                    f"INJECT: Resource exhaustion on '{action.target_component_id}'."
                )

            elif action.action_type == ActionType.FAILOVER_TRIGGER:
                if comp.failover.enabled:
                    comp.health = HealthStatus.HEALTHY
                    observations.append(
                        f"INJECT: Failover triggered for '{action.target_component_id}'."
                    )
                else:
                    observations.append(
                        f"INJECT: Failover not enabled for '{action.target_component_id}'."
                    )

        return observations

    @staticmethod
    def _run_observe(step: ExperimentStep, sim_graph: InfraGraph) -> list[str]:
        """Run OBSERVE phase: collect observations from current state."""
        observations: list[str] = []
        status_counts: dict[str, int] = {}
        for comp in sim_graph.components.values():
            status_counts[comp.health.value] = status_counts.get(comp.health.value, 0) + 1

        status_str = ", ".join(f"{k}: {v}" for k, v in sorted(status_counts.items()))
        observations.append(f"OBSERVE: Component health status - {status_str}")
        return observations

    @staticmethod
    def _run_rollback(
        step: ExperimentStep,
        sim_graph: InfraGraph,
        original_graph: InfraGraph,
    ) -> list[str]:
        """Run ROLLBACK phase: restore components to original state."""
        observations: list[str] = []
        restored = 0

        # Restore via step actions
        for action in step.actions:
            comp = sim_graph.get_component(action.target_component_id)
            orig_comp = original_graph.get_component(action.target_component_id)
            if comp and orig_comp:
                comp.health = orig_comp.health
                comp.metrics = copy.deepcopy(orig_comp.metrics)
                comp.network = copy.deepcopy(orig_comp.network)
                restored += 1

        # If no explicit actions, restore all
        if not step.actions:
            for comp_id in sim_graph.components:
                comp = sim_graph.get_component(comp_id)
                orig_comp = original_graph.get_component(comp_id)
                if comp and orig_comp:
                    comp.health = orig_comp.health
                    comp.metrics = copy.deepcopy(orig_comp.metrics)
                    comp.network = copy.deepcopy(orig_comp.network)
                    restored += 1

        observations.append(f"ROLLBACK: Restored {restored} components.")
        return observations

    def _check_assertion(
        self,
        assertion: ExperimentAssertion,
        sim_graph: InfraGraph,
        original_graph: InfraGraph,
    ) -> tuple[bool, str]:
        """Check a single assertion against the current simulated graph state.

        Returns (passed: bool, message: str).
        """
        if assertion.assertion_type == AssertionType.HEALTH_CHECK:
            if assertion.target_component_id:
                comp = sim_graph.get_component(assertion.target_component_id)
                if comp is None:
                    return False, f"Component '{assertion.target_component_id}' not found."
                ok = comp.health == HealthStatus.HEALTHY
                return ok, f"Health: {comp.health.value}"
            else:
                # Check all components
                total = len(sim_graph.components)
                healthy = sum(
                    1 for c in sim_graph.components.values()
                    if c.health == HealthStatus.HEALTHY
                )
                ok = healthy == total
                return ok, f"{healthy}/{total} healthy"

        elif assertion.assertion_type == AssertionType.LATENCY_BELOW:
            if assertion.target_component_id:
                comp = sim_graph.get_component(assertion.target_component_id)
                if comp is None:
                    return False, f"Component '{assertion.target_component_id}' not found."
                ok = comp.network.rtt_ms < assertion.threshold
                return ok, f"Latency: {comp.network.rtt_ms:.1f}ms (threshold: {assertion.threshold}ms)"
            else:
                max_latency = max(
                    (c.network.rtt_ms for c in sim_graph.components.values()),
                    default=0.0,
                )
                ok = max_latency < assertion.threshold
                return ok, f"Max latency: {max_latency:.1f}ms (threshold: {assertion.threshold}ms)"

        elif assertion.assertion_type == AssertionType.ERROR_RATE_BELOW:
            total = len(sim_graph.components)
            unhealthy = sum(
                1 for c in sim_graph.components.values()
                if c.health != HealthStatus.HEALTHY
            )
            error_rate = (unhealthy / total * 100) if total > 0 else 0.0
            ok = error_rate < assertion.threshold
            return ok, f"Error rate: {error_rate:.1f}% (threshold: {assertion.threshold}%)"

        elif assertion.assertion_type == AssertionType.AVAILABILITY_ABOVE:
            total = len(sim_graph.components)
            healthy = sum(
                1 for c in sim_graph.components.values()
                if c.health in (HealthStatus.HEALTHY, HealthStatus.DEGRADED)
            )
            availability = (healthy / total * 100) if total > 0 else 0.0
            ok = availability > assertion.threshold
            return ok, f"Availability: {availability:.1f}% (threshold: {assertion.threshold}%)"

        elif assertion.assertion_type == AssertionType.RECOVERY_WITHIN:
            # In simulation, recovery time is estimated from failover config
            if assertion.target_component_id:
                comp = sim_graph.get_component(assertion.target_component_id)
                if comp is None:
                    return False, f"Component '{assertion.target_component_id}' not found."
                recovery_time = comp.failover.promotion_time_seconds if comp.failover.enabled else 600.0
                ok = recovery_time <= assertion.threshold
                return ok, f"Recovery time: {recovery_time}s (threshold: {assertion.threshold}s)"
            else:
                return True, "No specific target for recovery check."

        elif assertion.assertion_type == AssertionType.CASCADE_CONTAINED:
            # Count total affected (non-healthy) components
            unhealthy = sum(
                1 for c in sim_graph.components.values()
                if c.health != HealthStatus.HEALTHY
            )
            ok = unhealthy <= assertion.threshold
            return ok, f"Affected components: {unhealthy} (threshold: {assertion.threshold})"

        elif assertion.assertion_type == AssertionType.NO_DATA_LOSS:
            # In simulation, check if any database/storage components are DOWN
            data_components = [
                c for c in sim_graph.components.values()
                if c.type in (ComponentType.DATABASE, ComponentType.STORAGE)
            ]
            data_loss = any(c.health == HealthStatus.DOWN for c in data_components)
            if not data_components:
                return True, "No data components to check."
            ok = not data_loss
            return ok, "No data loss detected" if ok else "Data component(s) DOWN - potential data loss"

        return False, f"Unknown assertion type: {assertion.assertion_type}"
