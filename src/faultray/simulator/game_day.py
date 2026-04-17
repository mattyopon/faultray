# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Game Day Simulator -- automated chaos engineering game day exercise runner.

Generates, executes, and evaluates structured game day exercises against an
infrastructure graph to assess operational readiness and resilience posture.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum

from faultray.model.components import Component, ComponentType
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ExerciseType(str, Enum):
    COMPONENT_FAILURE = "component_failure"
    CASCADING_FAILURE = "cascading_failure"
    REGION_OUTAGE = "region_outage"
    DEPENDENCY_TIMEOUT = "dependency_timeout"
    LOAD_SPIKE = "load_spike"
    DATA_CORRUPTION = "data_corruption"
    SECURITY_BREACH = "security_breach"
    NETWORK_PARTITION = "network_partition"


class ExerciseDifficulty(str, Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"


class ExerciseStatus(str, Enum):
    PLANNED = "planned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED = "aborted"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ExerciseObjective:
    description: str
    success_criteria: str
    met: bool = False


@dataclass
class ExerciseStep:
    order: int
    action: str
    description: str
    expected_outcome: str
    actual_outcome: str = ""
    passed: bool = False


@dataclass
class GameDayExercise:
    id: str
    name: str
    exercise_type: ExerciseType
    difficulty: ExerciseDifficulty
    description: str
    objectives: list[ExerciseObjective]
    steps: list[ExerciseStep]
    target_components: list[str]
    status: ExerciseStatus = ExerciseStatus.PLANNED
    score: float = 0.0
    duration_minutes: int = 60
    findings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


@dataclass
class GameDayReport:
    exercises: list[GameDayExercise]
    overall_score: float
    total_exercises: int
    passed_count: int
    failed_count: int
    critical_findings: list[str]
    improvement_areas: list[str]
    readiness_level: str  # "not_ready", "partially_ready", "ready", "well_prepared"


# ---------------------------------------------------------------------------
# Difficulty parameters
# ---------------------------------------------------------------------------

_DIFFICULTY_PARAMS: dict[ExerciseDifficulty, dict] = {
    ExerciseDifficulty.BEGINNER: {
        "min_steps": 2,
        "max_steps": 3,
        "replica_threshold": 1,
        "pass_ratio": 0.5,
    },
    ExerciseDifficulty.INTERMEDIATE: {
        "min_steps": 3,
        "max_steps": 5,
        "replica_threshold": 2,
        "pass_ratio": 0.6,
    },
    ExerciseDifficulty.ADVANCED: {
        "min_steps": 4,
        "max_steps": 6,
        "replica_threshold": 3,
        "pass_ratio": 0.75,
    },
    ExerciseDifficulty.EXPERT: {
        "min_steps": 5,
        "max_steps": 8,
        "replica_threshold": 4,
        "pass_ratio": 0.9,
    },
}


# ---------------------------------------------------------------------------
# Helpers (internal)
# ---------------------------------------------------------------------------


def _uid() -> str:
    return uuid.uuid4().hex[:8]


def _is_spof(comp: Component, graph: InfraGraph) -> bool:
    """Return True if *comp* is a single point of failure."""
    if comp.replicas > 1:
        return False
    if comp.failover.enabled:
        return False
    dependents = graph.get_dependents(comp.id)
    return len(dependents) > 0


def _dependency_chain_depth(comp_id: str, graph: InfraGraph) -> int:
    """Return the longest downstream dependency chain length starting from *comp_id*."""
    visited: set[str] = set()

    def _dfs(cid: str) -> int:
        if cid in visited:
            return 0
        visited.add(cid)
        deps = graph.get_dependencies(cid)
        if not deps:
            return 1
        return 1 + max(_dfs(d.id) for d in deps)

    return _dfs(comp_id)


def _has_circuit_breaker(comp_id: str, graph: InfraGraph) -> bool:
    """Return True if any edge *from* comp_id has a circuit breaker enabled."""
    deps = graph.get_dependencies(comp_id)
    for dep in deps:
        edge = graph.get_dependency_edge(comp_id, dep.id)
        if edge and edge.circuit_breaker.enabled:
            return True
    return False


def _has_security_controls(comp: Component) -> bool:
    sec = comp.security
    controls = [
        sec.encryption_at_rest,
        sec.encryption_in_transit,
        sec.waf_protected,
        sec.rate_limiting,
        sec.auth_required,
        sec.network_segmented,
        sec.backup_enabled,
    ]
    return sum(controls) >= 3


# ---------------------------------------------------------------------------
# Exercise generation helpers
# ---------------------------------------------------------------------------


def _make_component_failure_exercise(
    comp: Component,
    difficulty: ExerciseDifficulty,
) -> GameDayExercise:
    _DIFFICULTY_PARAMS[difficulty]
    objectives = [
        ExerciseObjective(
            description=f"System survives failure of {comp.name}",
            success_criteria="Redundancy or failover handles component loss",
        ),
        ExerciseObjective(
            description="No data loss during failure",
            success_criteria="Backup or replication protects data",
        ),
    ]
    steps = [
        ExerciseStep(
            order=1,
            action="identify_target",
            description=f"Identify component {comp.name} as failure target",
            expected_outcome="Target confirmed",
        ),
        ExerciseStep(
            order=2,
            action="simulate_failure",
            description=f"Simulate complete failure of {comp.name}",
            expected_outcome="Component marked as DOWN",
        ),
        ExerciseStep(
            order=3,
            action="verify_redundancy",
            description="Verify redundancy handles the failure",
            expected_outcome="Service remains available via replicas or failover",
        ),
    ]
    if difficulty in (ExerciseDifficulty.ADVANCED, ExerciseDifficulty.EXPERT):
        steps.append(
            ExerciseStep(
                order=4,
                action="verify_monitoring",
                description="Verify monitoring detects the failure",
                expected_outcome="Alerting systems triggered",
            )
        )
    if difficulty == ExerciseDifficulty.EXPERT:
        steps.append(
            ExerciseStep(
                order=5,
                action="verify_auto_recovery",
                description="Verify automatic recovery mechanisms",
                expected_outcome="Component auto-recovers within SLA",
            )
        )
    return GameDayExercise(
        id=f"ex-cf-{_uid()}",
        name=f"Component Failure: {comp.name}",
        exercise_type=ExerciseType.COMPONENT_FAILURE,
        difficulty=difficulty,
        description=f"Simulate failure of {comp.name} and verify resilience",
        objectives=objectives,
        steps=steps,
        target_components=[comp.id],
        duration_minutes=30 if difficulty == ExerciseDifficulty.BEGINNER else 60,
    )


def _make_cascading_failure_exercise(
    comp: Component,
    affected_count: int,
    difficulty: ExerciseDifficulty,
) -> GameDayExercise:
    objectives = [
        ExerciseObjective(
            description=f"Cascading failure from {comp.name} is contained",
            success_criteria="Circuit breakers or isolation prevents full cascade",
        ),
        ExerciseObjective(
            description="Blast radius is minimised",
            success_criteria=f"Fewer than {affected_count} components affected",
        ),
    ]
    steps = [
        ExerciseStep(
            order=1,
            action="identify_chain",
            description=f"Map dependency chain from {comp.name}",
            expected_outcome="Dependency chain documented",
        ),
        ExerciseStep(
            order=2,
            action="inject_failure",
            description=f"Inject failure at {comp.name}",
            expected_outcome="Failure propagates through dependencies",
        ),
        ExerciseStep(
            order=3,
            action="verify_containment",
            description="Verify cascade containment mechanisms",
            expected_outcome="Circuit breakers or bulkheads limit blast radius",
        ),
    ]
    if difficulty in (ExerciseDifficulty.ADVANCED, ExerciseDifficulty.EXPERT):
        steps.append(
            ExerciseStep(
                order=4,
                action="verify_graceful_degradation",
                description="Verify graceful degradation",
                expected_outcome="Non-critical features degrade gracefully",
            )
        )
    return GameDayExercise(
        id=f"ex-cas-{_uid()}",
        name=f"Cascading Failure: {comp.name}",
        exercise_type=ExerciseType.CASCADING_FAILURE,
        difficulty=difficulty,
        description=f"Simulate cascading failure starting from {comp.name}",
        objectives=objectives,
        steps=steps,
        target_components=[comp.id],
        duration_minutes=60 if difficulty != ExerciseDifficulty.EXPERT else 90,
    )


def _make_load_spike_exercise(
    comp: Component,
    difficulty: ExerciseDifficulty,
) -> GameDayExercise:
    objectives = [
        ExerciseObjective(
            description=f"{comp.name} handles load spike",
            success_criteria="Autoscaling or sufficient replicas absorb load",
        ),
    ]
    steps = [
        ExerciseStep(
            order=1,
            action="baseline_metrics",
            description=f"Record baseline metrics for {comp.name}",
            expected_outcome="Baseline utilization recorded",
        ),
        ExerciseStep(
            order=2,
            action="inject_load",
            description=f"Inject 3x load spike on {comp.name}",
            expected_outcome="Load increases significantly",
        ),
        ExerciseStep(
            order=3,
            action="verify_scaling",
            description="Verify autoscaling or capacity handles load",
            expected_outcome="System scales or absorbs load without degradation",
        ),
    ]
    return GameDayExercise(
        id=f"ex-ls-{_uid()}",
        name=f"Load Spike: {comp.name}",
        exercise_type=ExerciseType.LOAD_SPIKE,
        difficulty=difficulty,
        description=f"Simulate load spike on {comp.name}",
        objectives=objectives,
        steps=steps,
        target_components=[comp.id],
        duration_minutes=45,
    )


def _make_security_breach_exercise(
    comp: Component,
    difficulty: ExerciseDifficulty,
) -> GameDayExercise:
    objectives = [
        ExerciseObjective(
            description=f"Security controls protect {comp.name}",
            success_criteria="Encryption, auth, and segmentation are in place",
        ),
        ExerciseObjective(
            description="Breach detection is operational",
            success_criteria="Monitoring and alerting detect the breach",
        ),
    ]
    steps = [
        ExerciseStep(
            order=1,
            action="assess_security",
            description=f"Assess security posture of {comp.name}",
            expected_outcome="Security controls documented",
        ),
        ExerciseStep(
            order=2,
            action="simulate_breach",
            description=f"Simulate security breach on {comp.name}",
            expected_outcome="Breach attempt logged and detected",
        ),
        ExerciseStep(
            order=3,
            action="verify_controls",
            description="Verify security controls effectiveness",
            expected_outcome="Controls prevent or mitigate breach",
        ),
    ]
    return GameDayExercise(
        id=f"ex-sb-{_uid()}",
        name=f"Security Breach: {comp.name}",
        exercise_type=ExerciseType.SECURITY_BREACH,
        difficulty=difficulty,
        description=f"Simulate security breach targeting {comp.name}",
        objectives=objectives,
        steps=steps,
        target_components=[comp.id],
        duration_minutes=60,
    )


def _make_network_partition_exercise(
    comp: Component,
    difficulty: ExerciseDifficulty,
) -> GameDayExercise:
    objectives = [
        ExerciseObjective(
            description=f"{comp.name} survives network partition",
            success_criteria="Component handles partition gracefully",
        ),
    ]
    steps = [
        ExerciseStep(
            order=1,
            action="identify_network_deps",
            description=f"Identify network dependencies for {comp.name}",
            expected_outcome="Network topology documented",
        ),
        ExerciseStep(
            order=2,
            action="simulate_partition",
            description=f"Simulate network partition isolating {comp.name}",
            expected_outcome="Component loses connectivity to dependents",
        ),
        ExerciseStep(
            order=3,
            action="verify_handling",
            description="Verify partition handling (timeouts, retries, fallbacks)",
            expected_outcome="System handles partition without data loss",
        ),
    ]
    return GameDayExercise(
        id=f"ex-np-{_uid()}",
        name=f"Network Partition: {comp.name}",
        exercise_type=ExerciseType.NETWORK_PARTITION,
        difficulty=difficulty,
        description=f"Simulate network partition around {comp.name}",
        objectives=objectives,
        steps=steps,
        target_components=[comp.id],
        duration_minutes=45,
    )


def _make_dependency_timeout_exercise(
    comp: Component,
    difficulty: ExerciseDifficulty,
) -> GameDayExercise:
    objectives = [
        ExerciseObjective(
            description=f"{comp.name} handles dependency timeouts",
            success_criteria="Retry and circuit breaker strategies manage timeouts",
        ),
    ]
    steps = [
        ExerciseStep(
            order=1,
            action="identify_dependencies",
            description=f"Identify dependencies of {comp.name}",
            expected_outcome="Dependencies documented",
        ),
        ExerciseStep(
            order=2,
            action="inject_timeout",
            description=f"Inject dependency timeouts for {comp.name}",
            expected_outcome="Downstream dependencies become unresponsive",
        ),
        ExerciseStep(
            order=3,
            action="verify_timeout_handling",
            description="Verify timeout handling and fallback behaviour",
            expected_outcome="Retries, circuit breakers, or fallbacks engage",
        ),
    ]
    return GameDayExercise(
        id=f"ex-dt-{_uid()}",
        name=f"Dependency Timeout: {comp.name}",
        exercise_type=ExerciseType.DEPENDENCY_TIMEOUT,
        difficulty=difficulty,
        description=f"Simulate dependency timeouts affecting {comp.name}",
        objectives=objectives,
        steps=steps,
        target_components=[comp.id],
        duration_minutes=45,
    )


def _make_data_corruption_exercise(
    comp: Component,
    difficulty: ExerciseDifficulty,
) -> GameDayExercise:
    objectives = [
        ExerciseObjective(
            description=f"Data integrity of {comp.name} is recoverable",
            success_criteria="Backup and restore procedures work",
        ),
    ]
    steps = [
        ExerciseStep(
            order=1,
            action="assess_backup",
            description=f"Assess backup strategy for {comp.name}",
            expected_outcome="Backup configuration documented",
        ),
        ExerciseStep(
            order=2,
            action="simulate_corruption",
            description=f"Simulate data corruption on {comp.name}",
            expected_outcome="Data integrity compromised",
        ),
        ExerciseStep(
            order=3,
            action="verify_recovery",
            description="Verify data recovery from backup",
            expected_outcome="Data restored from backup without loss",
        ),
    ]
    return GameDayExercise(
        id=f"ex-dc-{_uid()}",
        name=f"Data Corruption: {comp.name}",
        exercise_type=ExerciseType.DATA_CORRUPTION,
        difficulty=difficulty,
        description=f"Simulate data corruption on {comp.name}",
        objectives=objectives,
        steps=steps,
        target_components=[comp.id],
        duration_minutes=60,
    )


def _make_region_outage_exercise(
    region: str,
    comp_ids: list[str],
    difficulty: ExerciseDifficulty,
) -> GameDayExercise:
    objectives = [
        ExerciseObjective(
            description=f"System survives region outage ({region})",
            success_criteria="Multi-region failover activates",
        ),
        ExerciseObjective(
            description="RTO/RPO targets met during region failover",
            success_criteria="Recovery within defined RTO/RPO",
        ),
    ]
    steps = [
        ExerciseStep(
            order=1,
            action="identify_region_components",
            description=f"Identify all components in region {region}",
            expected_outcome="Region component list documented",
        ),
        ExerciseStep(
            order=2,
            action="simulate_outage",
            description=f"Simulate complete outage of region {region}",
            expected_outcome="All components in region become unavailable",
        ),
        ExerciseStep(
            order=3,
            action="verify_failover",
            description="Verify cross-region failover",
            expected_outcome="Traffic fails over to DR region",
        ),
    ]
    if difficulty in (ExerciseDifficulty.ADVANCED, ExerciseDifficulty.EXPERT):
        steps.append(
            ExerciseStep(
                order=4,
                action="verify_rto_rpo",
                description="Verify RTO/RPO compliance",
                expected_outcome="Recovery meets defined targets",
            )
        )
    return GameDayExercise(
        id=f"ex-ro-{_uid()}",
        name=f"Region Outage: {region}",
        exercise_type=ExerciseType.REGION_OUTAGE,
        difficulty=difficulty,
        description=f"Simulate complete outage of region {region}",
        objectives=objectives,
        steps=steps,
        target_components=comp_ids,
        duration_minutes=90,
    )


# ---------------------------------------------------------------------------
# Exercise evaluation helpers
# ---------------------------------------------------------------------------


def _evaluate_component_failure(
    exercise: GameDayExercise,
    graph: InfraGraph,
    difficulty: ExerciseDifficulty,
) -> None:
    """Evaluate a component failure exercise against the graph."""
    params = _DIFFICULTY_PARAMS[difficulty]
    for comp_id in exercise.target_components:
        comp = graph.get_component(comp_id)
        if comp is None:
            exercise.findings.append(f"Component {comp_id} not found in graph")
            continue

        # Step 1: identify (always passes)
        if len(exercise.steps) > 0:
            exercise.steps[0].passed = True
            exercise.steps[0].actual_outcome = f"Target {comp.name} identified"

        # Step 2: simulate failure
        if len(exercise.steps) > 1:
            exercise.steps[1].passed = True
            exercise.steps[1].actual_outcome = f"{comp.name} marked as DOWN"

        # Step 3: verify redundancy
        if len(exercise.steps) > 2:
            has_redundancy = (
                comp.replicas >= params["replica_threshold"]
                or comp.failover.enabled
            )
            exercise.steps[2].passed = has_redundancy
            if has_redundancy:
                exercise.steps[2].actual_outcome = (
                    f"Redundancy OK: replicas={comp.replicas}, "
                    f"failover={comp.failover.enabled}"
                )
            else:
                exercise.steps[2].actual_outcome = (
                    f"No redundancy: replicas={comp.replicas}, "
                    f"failover={comp.failover.enabled}"
                )
                exercise.findings.append(
                    f"{comp.name} is a single point of failure"
                )
                exercise.recommendations.append(
                    f"Add replicas or enable failover for {comp.name}"
                )

        # Step 4: verify monitoring (advanced+)
        if len(exercise.steps) > 3:
            has_monitoring = comp.security.log_enabled or comp.security.ids_monitored
            exercise.steps[3].passed = has_monitoring
            exercise.steps[3].actual_outcome = (
                f"Monitoring: log_enabled={comp.security.log_enabled}, "
                f"ids_monitored={comp.security.ids_monitored}"
            )
            if not has_monitoring:
                exercise.findings.append(f"No monitoring for {comp.name}")
                exercise.recommendations.append(
                    f"Enable logging and monitoring for {comp.name}"
                )

        # Step 5: verify auto-recovery (expert)
        if len(exercise.steps) > 4:
            has_auto_recovery = comp.autoscaling.enabled or comp.failover.enabled
            exercise.steps[4].passed = has_auto_recovery
            exercise.steps[4].actual_outcome = (
                f"Auto-recovery: autoscaling={comp.autoscaling.enabled}, "
                f"failover={comp.failover.enabled}"
            )
            if not has_auto_recovery:
                exercise.findings.append(f"No auto-recovery for {comp.name}")
                exercise.recommendations.append(
                    f"Enable autoscaling or failover for {comp.name}"
                )

    # Objectives
    if exercise.objectives:
        passed_steps = sum(1 for s in exercise.steps if s.passed)
        total_steps = len(exercise.steps)
        # Objective 0: system survives
        exercise.objectives[0].met = (
            passed_steps >= total_steps * params["pass_ratio"]
        )
    if len(exercise.objectives) > 1:
        # Objective 1: no data loss
        for comp_id in exercise.target_components:
            comp = graph.get_component(comp_id)
            if comp and comp.security.backup_enabled:
                exercise.objectives[1].met = True
            else:
                exercise.objectives[1].met = False
                exercise.findings.append(
                    f"No backup enabled for {comp_id}"
                )
                exercise.recommendations.append(
                    f"Enable backup for {comp_id}"
                )


def _evaluate_cascading_failure(
    exercise: GameDayExercise,
    graph: InfraGraph,
    difficulty: ExerciseDifficulty,
) -> None:
    params = _DIFFICULTY_PARAMS[difficulty]
    for comp_id in exercise.target_components:
        comp = graph.get_component(comp_id)
        if comp is None:
            continue

        affected = graph.get_all_affected(comp_id)

        # Step 1: identify chain
        if len(exercise.steps) > 0:
            exercise.steps[0].passed = True
            exercise.steps[0].actual_outcome = (
                f"Chain mapped: {len(affected)} components affected"
            )

        # Step 2: inject failure
        if len(exercise.steps) > 1:
            exercise.steps[1].passed = True
            exercise.steps[1].actual_outcome = f"Failure injected at {comp.name}"

        # Step 3: verify containment
        if len(exercise.steps) > 2:
            has_cb = _has_circuit_breaker(comp_id, graph)
            # Also check if affected components have circuit breakers
            affected_with_cb = sum(
                1 for aid in affected if _has_circuit_breaker(aid, graph)
            )
            contained = has_cb or (len(affected) > 0 and affected_with_cb > 0)
            exercise.steps[2].passed = contained
            if contained:
                exercise.steps[2].actual_outcome = "Circuit breakers contain cascade"
            else:
                exercise.steps[2].actual_outcome = (
                    f"No containment: {len(affected)} components affected"
                )
                exercise.findings.append(
                    f"Cascading failure from {comp.name} affects "
                    f"{len(affected)} components without containment"
                )
                exercise.recommendations.append(
                    f"Add circuit breakers to dependencies of {comp.name}"
                )

        # Step 4: graceful degradation (advanced+)
        if len(exercise.steps) > 3:
            # Check for optional/async dependencies that would allow degradation
            deps = graph.get_dependencies(comp_id)
            has_optional = any(
                (edge := graph.get_dependency_edge(comp_id, d.id))
                and edge.dependency_type in ("optional", "async")
                for d in deps
            )
            exercise.steps[3].passed = has_optional
            exercise.steps[3].actual_outcome = (
                "Graceful degradation possible" if has_optional
                else "All dependencies are 'requires' type -- no graceful degradation"
            )

    # Objectives
    if exercise.objectives:
        passed_steps = sum(1 for s in exercise.steps if s.passed)
        total_steps = len(exercise.steps)
        exercise.objectives[0].met = (
            passed_steps >= total_steps * params["pass_ratio"]
        )
    if len(exercise.objectives) > 1:
        for comp_id in exercise.target_components:
            affected = graph.get_all_affected(comp_id)
            blast_small = len(affected) <= 2
            exercise.objectives[1].met = blast_small
            if not blast_small:
                exercise.findings.append(
                    f"Blast radius too large: {len(affected)} components affected"
                )


def _evaluate_load_spike(
    exercise: GameDayExercise,
    graph: InfraGraph,
    difficulty: ExerciseDifficulty,
) -> None:
    params = _DIFFICULTY_PARAMS[difficulty]
    for comp_id in exercise.target_components:
        comp = graph.get_component(comp_id)
        if comp is None:
            continue

        # Step 1: baseline
        if len(exercise.steps) > 0:
            exercise.steps[0].passed = True
            exercise.steps[0].actual_outcome = (
                f"Baseline: utilization={comp.utilization():.1f}%"
            )

        # Step 2: inject load
        if len(exercise.steps) > 1:
            exercise.steps[1].passed = True
            exercise.steps[1].actual_outcome = "Load spike injected"

        # Step 3: verify scaling
        if len(exercise.steps) > 2:
            can_scale = (
                comp.autoscaling.enabled
                or comp.replicas >= params["replica_threshold"]
            )
            exercise.steps[2].passed = can_scale
            if can_scale:
                exercise.steps[2].actual_outcome = (
                    f"Scaling OK: autoscaling={comp.autoscaling.enabled}, "
                    f"replicas={comp.replicas}"
                )
            else:
                exercise.steps[2].actual_outcome = (
                    f"Cannot scale: autoscaling={comp.autoscaling.enabled}, "
                    f"replicas={comp.replicas}"
                )
                exercise.findings.append(
                    f"{comp.name} cannot handle load spikes"
                )
                exercise.recommendations.append(
                    f"Enable autoscaling for {comp.name}"
                )

    if exercise.objectives:
        passed_steps = sum(1 for s in exercise.steps if s.passed)
        total_steps = len(exercise.steps)
        exercise.objectives[0].met = (
            passed_steps >= total_steps * params["pass_ratio"]
        )


def _evaluate_security_breach(
    exercise: GameDayExercise,
    graph: InfraGraph,
    difficulty: ExerciseDifficulty,
) -> None:
    params = _DIFFICULTY_PARAMS[difficulty]
    for comp_id in exercise.target_components:
        comp = graph.get_component(comp_id)
        if comp is None:
            continue

        # Step 1: assess security
        if len(exercise.steps) > 0:
            exercise.steps[0].passed = True
            exercise.steps[0].actual_outcome = "Security posture assessed"

        # Step 2: simulate breach
        if len(exercise.steps) > 1:
            exercise.steps[1].passed = True
            exercise.steps[1].actual_outcome = "Breach simulated"

        # Step 3: verify controls
        if len(exercise.steps) > 2:
            secure = _has_security_controls(comp)
            exercise.steps[2].passed = secure
            if secure:
                exercise.steps[2].actual_outcome = "Security controls effective"
            else:
                exercise.steps[2].actual_outcome = "Insufficient security controls"
                exercise.findings.append(
                    f"{comp.name} has insufficient security controls"
                )
                exercise.recommendations.append(
                    f"Enable encryption, auth, and network segmentation for {comp.name}"
                )

    if exercise.objectives:
        passed_steps = sum(1 for s in exercise.steps if s.passed)
        total_steps = len(exercise.steps)
        exercise.objectives[0].met = (
            passed_steps >= total_steps * params["pass_ratio"]
        )
    if len(exercise.objectives) > 1:
        for comp_id in exercise.target_components:
            comp = graph.get_component(comp_id)
            if comp:
                has_detection = comp.security.log_enabled or comp.security.ids_monitored
                exercise.objectives[1].met = has_detection
                if not has_detection:
                    exercise.findings.append(
                        f"No breach detection for {comp.name}"
                    )


def _evaluate_network_partition(
    exercise: GameDayExercise,
    graph: InfraGraph,
    difficulty: ExerciseDifficulty,
) -> None:
    params = _DIFFICULTY_PARAMS[difficulty]
    for comp_id in exercise.target_components:
        comp = graph.get_component(comp_id)
        if comp is None:
            continue

        # Step 1: identify network deps
        if len(exercise.steps) > 0:
            exercise.steps[0].passed = True
            exercise.steps[0].actual_outcome = "Network dependencies identified"

        # Step 2: simulate partition
        if len(exercise.steps) > 1:
            exercise.steps[1].passed = True
            exercise.steps[1].actual_outcome = f"{comp.name} isolated"

        # Step 3: verify handling
        if len(exercise.steps) > 2:
            has_cb = _has_circuit_breaker(comp_id, graph)
            deps = graph.get_dependencies(comp_id)
            has_retry = any(
                (edge := graph.get_dependency_edge(comp_id, d.id))
                and edge.retry_strategy.enabled
                for d in deps
            )
            handles_partition = has_cb or has_retry or comp.failover.enabled
            exercise.steps[2].passed = handles_partition
            if handles_partition:
                exercise.steps[2].actual_outcome = "Partition handling in place"
            else:
                exercise.steps[2].actual_outcome = "No partition handling"
                exercise.findings.append(
                    f"{comp.name} has no partition handling"
                )
                exercise.recommendations.append(
                    f"Add circuit breakers or retries for {comp.name}"
                )

    if exercise.objectives:
        passed_steps = sum(1 for s in exercise.steps if s.passed)
        total_steps = len(exercise.steps)
        exercise.objectives[0].met = (
            passed_steps >= total_steps * params["pass_ratio"]
        )


def _evaluate_dependency_timeout(
    exercise: GameDayExercise,
    graph: InfraGraph,
    difficulty: ExerciseDifficulty,
) -> None:
    params = _DIFFICULTY_PARAMS[difficulty]
    for comp_id in exercise.target_components:
        comp = graph.get_component(comp_id)
        if comp is None:
            continue

        if len(exercise.steps) > 0:
            exercise.steps[0].passed = True
            exercise.steps[0].actual_outcome = "Dependencies identified"

        if len(exercise.steps) > 1:
            exercise.steps[1].passed = True
            exercise.steps[1].actual_outcome = "Timeouts injected"

        if len(exercise.steps) > 2:
            has_cb = _has_circuit_breaker(comp_id, graph)
            deps = graph.get_dependencies(comp_id)
            has_retry = any(
                (edge := graph.get_dependency_edge(comp_id, d.id))
                and edge.retry_strategy.enabled
                for d in deps
            )
            handles = has_cb or has_retry
            exercise.steps[2].passed = handles
            if handles:
                exercise.steps[2].actual_outcome = "Timeout handling in place"
            else:
                exercise.steps[2].actual_outcome = "No timeout handling"
                exercise.findings.append(
                    f"{comp.name} has no timeout handling"
                )
                exercise.recommendations.append(
                    f"Add circuit breakers or retries for {comp.name}"
                )

    if exercise.objectives:
        passed_steps = sum(1 for s in exercise.steps if s.passed)
        total_steps = len(exercise.steps)
        exercise.objectives[0].met = (
            passed_steps >= total_steps * params["pass_ratio"]
        )


def _evaluate_data_corruption(
    exercise: GameDayExercise,
    graph: InfraGraph,
    difficulty: ExerciseDifficulty,
) -> None:
    params = _DIFFICULTY_PARAMS[difficulty]
    for comp_id in exercise.target_components:
        comp = graph.get_component(comp_id)
        if comp is None:
            continue

        if len(exercise.steps) > 0:
            exercise.steps[0].passed = True
            exercise.steps[0].actual_outcome = "Backup strategy assessed"

        if len(exercise.steps) > 1:
            exercise.steps[1].passed = True
            exercise.steps[1].actual_outcome = "Data corruption simulated"

        if len(exercise.steps) > 2:
            has_backup = comp.security.backup_enabled
            exercise.steps[2].passed = has_backup
            if has_backup:
                exercise.steps[2].actual_outcome = "Data recovered from backup"
            else:
                exercise.steps[2].actual_outcome = "No backup available"
                exercise.findings.append(
                    f"{comp.name} has no backup for data recovery"
                )
                exercise.recommendations.append(
                    f"Enable backup for {comp.name}"
                )

    if exercise.objectives:
        passed_steps = sum(1 for s in exercise.steps if s.passed)
        total_steps = len(exercise.steps)
        exercise.objectives[0].met = (
            passed_steps >= total_steps * params["pass_ratio"]
        )


def _evaluate_region_outage(
    exercise: GameDayExercise,
    graph: InfraGraph,
    difficulty: ExerciseDifficulty,
) -> None:
    params = _DIFFICULTY_PARAMS[difficulty]

    has_dr = False
    for comp_id in exercise.target_components:
        comp = graph.get_component(comp_id)
        if comp is None:
            continue
        if comp.region.dr_target_region:
            has_dr = True

    # Step 1: identify components
    if len(exercise.steps) > 0:
        exercise.steps[0].passed = True
        exercise.steps[0].actual_outcome = (
            f"Identified {len(exercise.target_components)} components in region"
        )

    # Step 2: simulate outage
    if len(exercise.steps) > 1:
        exercise.steps[1].passed = True
        exercise.steps[1].actual_outcome = "Region outage simulated"

    # Step 3: verify failover
    if len(exercise.steps) > 2:
        exercise.steps[2].passed = has_dr
        if has_dr:
            exercise.steps[2].actual_outcome = "Cross-region failover available"
        else:
            exercise.steps[2].actual_outcome = "No cross-region failover"
            exercise.findings.append("No DR target region configured")
            exercise.recommendations.append(
                "Configure multi-region DR with failover"
            )

    # Step 4: RTO/RPO (advanced+)
    if len(exercise.steps) > 3:
        rto_ok = all(
            (c := graph.get_component(cid)) is not None and c.region.rto_seconds > 0
            for cid in exercise.target_components
            if graph.get_component(cid) is not None
        )
        exercise.steps[3].passed = rto_ok and has_dr
        exercise.steps[3].actual_outcome = (
            "RTO/RPO defined" if rto_ok else "RTO/RPO not configured"
        )

    # Objectives
    if exercise.objectives:
        passed_steps = sum(1 for s in exercise.steps if s.passed)
        total_steps = len(exercise.steps)
        exercise.objectives[0].met = (
            passed_steps >= total_steps * params["pass_ratio"]
        )
    if len(exercise.objectives) > 1:
        exercise.objectives[1].met = has_dr


_EVALUATORS = {
    ExerciseType.COMPONENT_FAILURE: _evaluate_component_failure,
    ExerciseType.CASCADING_FAILURE: _evaluate_cascading_failure,
    ExerciseType.LOAD_SPIKE: _evaluate_load_spike,
    ExerciseType.SECURITY_BREACH: _evaluate_security_breach,
    ExerciseType.NETWORK_PARTITION: _evaluate_network_partition,
    ExerciseType.DEPENDENCY_TIMEOUT: _evaluate_dependency_timeout,
    ExerciseType.DATA_CORRUPTION: _evaluate_data_corruption,
    ExerciseType.REGION_OUTAGE: _evaluate_region_outage,
}


# ---------------------------------------------------------------------------
# Main simulator
# ---------------------------------------------------------------------------


class GameDaySimulator:
    """Automated game day exercise runner.

    Analyses an :class:`InfraGraph` to generate targeted chaos engineering
    exercises, runs them by evaluating infrastructure properties, and
    produces a comprehensive readiness report.
    """

    def __init__(self, graph: InfraGraph) -> None:
        self._graph = graph
        self._exercises: list[GameDayExercise] = []

    # -- public API ----------------------------------------------------------

    def generate_exercises(
        self,
        difficulty: ExerciseDifficulty = ExerciseDifficulty.INTERMEDIATE,
        count: int = 5,
    ) -> list[GameDayExercise]:
        """Auto-generate game day exercises based on infrastructure analysis.

        Analyses the graph topology to find weak points and generates
        relevant exercises.  SPOF components get ``COMPONENT_FAILURE``,
        deep dependency chains get ``CASCADING_FAILURE``, components without
        autoscaling get ``LOAD_SPIKE``, etc.
        """
        candidates: list[GameDayExercise] = []
        components = list(self._graph.components.values())

        if not components:
            return []

        # 1. SPOF -> COMPONENT_FAILURE
        for comp in components:
            if _is_spof(comp, self._graph):
                candidates.append(
                    _make_component_failure_exercise(comp, difficulty)
                )

        # 2. Deep dependency chains -> CASCADING_FAILURE
        for comp in components:
            depth = _dependency_chain_depth(comp.id, self._graph)
            affected = self._graph.get_all_affected(comp.id)
            if depth >= 2 or len(affected) >= 2:
                candidates.append(
                    _make_cascading_failure_exercise(comp, len(affected), difficulty)
                )

        # 3. No autoscaling -> LOAD_SPIKE
        for comp in components:
            if not comp.autoscaling.enabled and comp.replicas < 3:
                candidates.append(
                    _make_load_spike_exercise(comp, difficulty)
                )

        # 4. Weak security -> SECURITY_BREACH
        for comp in components:
            if not _has_security_controls(comp):
                candidates.append(
                    _make_security_breach_exercise(comp, difficulty)
                )

        # 5. Components with dependencies -> DEPENDENCY_TIMEOUT
        for comp in components:
            deps = self._graph.get_dependencies(comp.id)
            if deps and not _has_circuit_breaker(comp.id, self._graph):
                candidates.append(
                    _make_dependency_timeout_exercise(comp, difficulty)
                )

        # 6. Components with dependencies -> NETWORK_PARTITION
        for comp in components:
            deps = self._graph.get_dependencies(comp.id)
            dependents = self._graph.get_dependents(comp.id)
            if deps or dependents:
                candidates.append(
                    _make_network_partition_exercise(comp, difficulty)
                )

        # 7. Database/Storage -> DATA_CORRUPTION
        for comp in components:
            if comp.type in (ComponentType.DATABASE, ComponentType.STORAGE):
                candidates.append(
                    _make_data_corruption_exercise(comp, difficulty)
                )

        # 8. Region-based grouping -> REGION_OUTAGE
        regions: dict[str, list[str]] = {}
        for comp in components:
            r = comp.region.region
            if r:
                regions.setdefault(r, []).append(comp.id)
        for region, comp_ids in regions.items():
            candidates.append(
                _make_region_outage_exercise(region, comp_ids, difficulty)
            )

        # Deduplicate by exercise type + target components combo
        seen: set[tuple[str, tuple[str, ...]]] = set()
        unique: list[GameDayExercise] = []
        for ex in candidates:
            key = (ex.exercise_type.value, tuple(sorted(ex.target_components)))
            if key not in seen:
                seen.add(key)
                unique.append(ex)
        candidates = unique

        # Limit to requested count
        result = candidates[:count]
        self._exercises.extend(result)
        return result

    def add_exercise(self, exercise: GameDayExercise) -> None:
        """Add a custom exercise."""
        self._exercises.append(exercise)

    def run_exercise(self, exercise_id: str) -> GameDayExercise | None:
        """Simulate running a single exercise and evaluate results.

        Returns the exercise with updated status, score, findings and
        recommendations, or ``None`` if the exercise ID is not found.
        """
        exercise = self.get_exercise(exercise_id)
        if exercise is None:
            return None

        exercise.status = ExerciseStatus.RUNNING

        evaluator = _EVALUATORS.get(exercise.exercise_type)
        if evaluator:
            evaluator(exercise, self._graph, exercise.difficulty)

        # Calculate score
        exercise.score = self._calculate_score(exercise)

        # Update status based on score
        params = _DIFFICULTY_PARAMS[exercise.difficulty]
        if exercise.score >= params["pass_ratio"] * 100:
            exercise.status = ExerciseStatus.COMPLETED
        else:
            exercise.status = ExerciseStatus.FAILED

        return exercise

    def run_all(self) -> GameDayReport:
        """Run all planned exercises and generate report."""
        for exercise in self._exercises:
            if exercise.status == ExerciseStatus.PLANNED:
                self.run_exercise(exercise.id)
        return self.generate_report()

    def evaluate_readiness(self) -> str:
        """Evaluate overall infrastructure readiness based on exercises.

        Returns one of ``"not_ready"``, ``"partially_ready"``, ``"ready"``,
        or ``"well_prepared"`` based on the average exercise score.
        """
        if not self._exercises:
            return "not_ready"

        completed = [
            e for e in self._exercises
            if e.status in (ExerciseStatus.COMPLETED, ExerciseStatus.FAILED)
        ]
        if not completed:
            return "not_ready"

        avg_score = sum(e.score for e in completed) / len(completed)
        return self._readiness_from_score(avg_score)

    def get_exercise(self, exercise_id: str) -> GameDayExercise | None:
        """Get an exercise by ID."""
        for exercise in self._exercises:
            if exercise.id == exercise_id:
                return exercise
        return None

    def generate_report(self) -> GameDayReport:
        """Generate comprehensive game day report."""
        completed = [
            e for e in self._exercises
            if e.status in (ExerciseStatus.COMPLETED, ExerciseStatus.FAILED)
        ]
        passed = [e for e in completed if e.status == ExerciseStatus.COMPLETED]
        failed = [e for e in completed if e.status == ExerciseStatus.FAILED]

        if completed:
            overall_score = sum(e.score for e in completed) / len(completed)
        else:
            overall_score = 0.0

        # Collect critical findings (from failed exercises)
        critical_findings: list[str] = []
        for e in failed:
            critical_findings.extend(e.findings)

        # Collect improvement areas (from all exercises)
        improvement_areas: list[str] = []
        for e in self._exercises:
            improvement_areas.extend(e.recommendations)

        # Deduplicate
        critical_findings = list(dict.fromkeys(critical_findings))
        improvement_areas = list(dict.fromkeys(improvement_areas))

        return GameDayReport(
            exercises=list(self._exercises),
            overall_score=round(overall_score, 1),
            total_exercises=len(self._exercises),
            passed_count=len(passed),
            failed_count=len(failed),
            critical_findings=critical_findings,
            improvement_areas=improvement_areas,
            readiness_level=self._readiness_from_score(overall_score),
        )

    # -- internal helpers ----------------------------------------------------

    @staticmethod
    def _calculate_score(exercise: GameDayExercise) -> float:
        """Calculate exercise score (0-100) based on steps and objectives."""
        if not exercise.steps and not exercise.objectives:
            return 0.0

        step_score = 0.0
        obj_score = 0.0

        if exercise.steps:
            passed = sum(1 for s in exercise.steps if s.passed)
            step_score = (passed / len(exercise.steps)) * 100

        if exercise.objectives:
            met = sum(1 for o in exercise.objectives if o.met)
            obj_score = (met / len(exercise.objectives)) * 100

        # Weighted: 60% steps, 40% objectives
        if exercise.steps and exercise.objectives:
            return round(step_score * 0.6 + obj_score * 0.4, 1)
        if exercise.steps:
            return round(step_score, 1)
        return round(obj_score, 1)

    @staticmethod
    def _readiness_from_score(score: float) -> str:
        if score >= 80:
            return "well_prepared"
        if score >= 60:
            return "ready"
        if score >= 40:
            return "partially_ready"
        return "not_ready"
