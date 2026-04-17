# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Chaos Experiment Scheduler — plan and schedule chaos experiments.

Plans and schedules chaos experiments with conflict detection, safety
constraints, risk estimation, and concurrent experiment simulation.
Provides intelligent scheduling with blast radius limits and prerequisite
validation.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from faultray.model.components import ComponentType, HealthStatus
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ExperimentType(str, Enum):
    """Types of chaos experiments."""

    FAILURE_INJECTION = "failure_injection"
    LATENCY_INJECTION = "latency_injection"
    RESOURCE_STRESS = "resource_stress"
    NETWORK_CHAOS = "network_chaos"
    STATE_TRANSITION = "state_transition"
    SECURITY_TEST = "security_test"
    DATA_CORRUPTION = "data_corruption"
    LOAD_TEST = "load_test"


class SafetyLevel(str, Enum):
    """Safety classification for an experiment."""

    SAFE = "safe"
    CAUTION = "caution"
    DANGEROUS = "dangerous"
    FORBIDDEN = "forbidden"


class ConflictType(str, Enum):
    """Types of scheduling conflicts."""

    TARGET_OVERLAP = "target_overlap"
    DEPENDENCY_CHAIN = "dependency_chain"
    BLAST_RADIUS_EXCEEDED = "blast_radius_exceeded"
    SAFETY_VIOLATION = "safety_violation"
    PREREQUISITE_MISSING = "prerequisite_missing"
    CONCURRENT_LIMIT = "concurrent_limit"


class WindowType(str, Enum):
    """Type of time window."""

    MAINTENANCE = "maintenance"
    SAFE_WINDOW = "safe_window"
    BLACKOUT = "blackout"
    PEAK_HOURS = "peak_hours"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class Experiment(BaseModel):
    """A chaos experiment definition."""

    id: str
    name: str
    experiment_type: ExperimentType
    target_components: list[str] = Field(default_factory=list)
    safety_level: SafetyLevel = SafetyLevel.SAFE
    duration_minutes: float = 10.0
    blast_radius_limit: int = 3
    requires_approval: bool = False
    rollback_plan: str = ""
    prerequisites: list[str] = Field(default_factory=list)


class TimeWindow(BaseModel):
    """A time window for scheduling."""

    start_offset_minutes: float = 0.0
    end_offset_minutes: float = 60.0
    window_type: WindowType = WindowType.SAFE_WINDOW
    label: str = ""
    available: bool = True


class ScheduledExperiment(BaseModel):
    """An experiment assigned to a time window."""

    experiment: Experiment
    time_window: TimeWindow
    execution_order: int = 0
    estimated_risk: float = 0.0
    approved: bool = False
    notes: str = ""


class ScheduleConflict(BaseModel):
    """A conflict detected between experiments or constraints."""

    conflict_type: ConflictType
    experiment_ids: list[str] = Field(default_factory=list)
    description: str = ""
    severity: float = 0.0
    resolution_hint: str = ""


class SafetyValidation(BaseModel):
    """Result of safety validation for an experiment."""

    is_safe: bool = True
    safety_level: SafetyLevel = SafetyLevel.SAFE
    violations: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    affected_components: list[str] = Field(default_factory=list)
    max_blast_radius: int = 0
    requires_approval: bool = False
    rollback_feasible: bool = True


class ScheduleConstraints(BaseModel):
    """Constraints for schedule creation."""

    max_concurrent_experiments: int = 2
    max_total_risk: float = 0.8
    max_blast_radius: int = 5
    allow_dangerous: bool = False
    allow_forbidden: bool = False
    required_rollback_plans: bool = True
    blackout_windows: list[TimeWindow] = Field(default_factory=list)
    max_duration_minutes: float = 480.0


class ConcurrentImpact(BaseModel):
    """Impact assessment of a single concurrent experiment."""

    experiment_id: str
    individual_risk: float = 0.0
    added_blast_radius: int = 0
    cascading_components: list[str] = Field(default_factory=list)


class ConcurrentResult(BaseModel):
    """Result of simulating concurrent experiments."""

    total_risk: float = 0.0
    combined_blast_radius: int = 0
    interaction_effects: list[str] = Field(default_factory=list)
    is_safe: bool = True
    max_concurrent_reached: int = 0
    per_experiment: list[ConcurrentImpact] = Field(default_factory=list)
    cascading_failures: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class Schedule(BaseModel):
    """A complete chaos experiment schedule."""

    experiments: list[ScheduledExperiment] = Field(default_factory=list)
    conflicts: list[ScheduleConflict] = Field(default_factory=list)
    total_duration_minutes: float = 0.0
    risk_score: float = 0.0
    safety_windows: list[TimeWindow] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

# Risk weights per experiment type
_TYPE_RISK_WEIGHTS: dict[ExperimentType, float] = {
    ExperimentType.FAILURE_INJECTION: 0.8,
    ExperimentType.LATENCY_INJECTION: 0.3,
    ExperimentType.RESOURCE_STRESS: 0.5,
    ExperimentType.NETWORK_CHAOS: 0.7,
    ExperimentType.STATE_TRANSITION: 0.6,
    ExperimentType.SECURITY_TEST: 0.4,
    ExperimentType.DATA_CORRUPTION: 0.9,
    ExperimentType.LOAD_TEST: 0.4,
}

# Safety level risk multipliers
_SAFETY_MULTIPLIERS: dict[SafetyLevel, float] = {
    SafetyLevel.SAFE: 0.2,
    SafetyLevel.CAUTION: 0.5,
    SafetyLevel.DANGEROUS: 0.8,
    SafetyLevel.FORBIDDEN: 1.0,
}

# Experiment types considered incompatible when targeting same components
_INCOMPATIBLE_TYPES: set[tuple[ExperimentType, ExperimentType]] = {
    (ExperimentType.FAILURE_INJECTION, ExperimentType.DATA_CORRUPTION),
    (ExperimentType.FAILURE_INJECTION, ExperimentType.NETWORK_CHAOS),
    (ExperimentType.RESOURCE_STRESS, ExperimentType.LOAD_TEST),
    (ExperimentType.DATA_CORRUPTION, ExperimentType.STATE_TRANSITION),
}


def _types_incompatible(a: ExperimentType, b: ExperimentType) -> bool:
    return (a, b) in _INCOMPATIBLE_TYPES or (b, a) in _INCOMPATIBLE_TYPES


class ChaosScheduleEngine:
    """Plans, validates, and schedules chaos experiments."""

    # -- public API ---------------------------------------------------------

    def create_schedule(
        self,
        graph: InfraGraph,
        experiments: list[Experiment],
        constraints: ScheduleConstraints | None = None,
    ) -> Schedule:
        """Build a schedule for the given experiments.

        Steps:
        1. Validate safety of each experiment.
        2. Detect conflicts.
        3. Assign time windows, skipping forbidden / invalid experiments.
        4. Compute aggregate risk.
        """
        if constraints is None:
            constraints = ScheduleConstraints()

        conflicts = self.detect_conflicts(experiments)

        # Validate each experiment and filter
        scheduled: list[ScheduledExperiment] = []
        safety_windows: list[TimeWindow] = []
        offset = 0.0

        for idx, exp in enumerate(experiments):
            validation = self.validate_safety(graph, exp)

            # Skip forbidden unless explicitly allowed
            if exp.safety_level == SafetyLevel.FORBIDDEN and not constraints.allow_forbidden:
                conflicts.append(ScheduleConflict(
                    conflict_type=ConflictType.SAFETY_VIOLATION,
                    experiment_ids=[exp.id],
                    description=f"Experiment '{exp.name}' has forbidden safety level",
                    severity=1.0,
                    resolution_hint="Set allow_forbidden=True in constraints or change safety level",
                ))
                continue

            if exp.safety_level == SafetyLevel.DANGEROUS and not constraints.allow_dangerous:
                conflicts.append(ScheduleConflict(
                    conflict_type=ConflictType.SAFETY_VIOLATION,
                    experiment_ids=[exp.id],
                    description=f"Experiment '{exp.name}' has dangerous safety level",
                    severity=0.8,
                    resolution_hint="Set allow_dangerous=True in constraints or change safety level",
                ))
                continue

            # Check blast radius
            actual_blast = self._compute_blast_radius(graph, exp)
            if actual_blast > constraints.max_blast_radius:
                conflicts.append(ScheduleConflict(
                    conflict_type=ConflictType.BLAST_RADIUS_EXCEEDED,
                    experiment_ids=[exp.id],
                    description=(
                        f"Blast radius {actual_blast} exceeds limit "
                        f"{constraints.max_blast_radius}"
                    ),
                    severity=0.7,
                    resolution_hint="Reduce target components or increase max_blast_radius",
                ))
                continue

            # Check rollback plan requirement
            if constraints.required_rollback_plans and not exp.rollback_plan:
                conflicts.append(ScheduleConflict(
                    conflict_type=ConflictType.SAFETY_VIOLATION,
                    experiment_ids=[exp.id],
                    description=f"Experiment '{exp.name}' missing rollback plan",
                    severity=0.5,
                    resolution_hint="Add a rollback_plan to the experiment",
                ))
                continue

            # Check unresolved prerequisites
            scheduled_ids = {s.experiment.id for s in scheduled}
            missing = [p for p in exp.prerequisites if p not in scheduled_ids]
            if missing:
                conflicts.append(ScheduleConflict(
                    conflict_type=ConflictType.PREREQUISITE_MISSING,
                    experiment_ids=[exp.id] + missing,
                    description=f"Missing prerequisites: {', '.join(missing)}",
                    severity=0.6,
                    resolution_hint="Schedule prerequisite experiments first",
                ))
                continue

            # Check if adding would exceed total duration
            if offset + exp.duration_minutes > constraints.max_duration_minutes:
                continue

            risk = self.estimate_risk(graph, exp)
            window = TimeWindow(
                start_offset_minutes=offset,
                end_offset_minutes=offset + exp.duration_minutes,
                window_type=WindowType.SAFE_WINDOW,
                label=f"Window for {exp.name}",
                available=True,
            )
            safety_windows.append(window)

            scheduled.append(ScheduledExperiment(
                experiment=exp,
                time_window=window,
                execution_order=len(scheduled),
                estimated_risk=risk,
                approved=not exp.requires_approval,
                notes="; ".join(validation.warnings) if validation.warnings else "",
            ))
            offset += exp.duration_minutes

        total_risk = sum(s.estimated_risk for s in scheduled) / max(len(scheduled), 1)

        return Schedule(
            experiments=scheduled,
            conflicts=conflicts,
            total_duration_minutes=offset,
            risk_score=min(1.0, total_risk),
            safety_windows=safety_windows,
        )

    def detect_conflicts(
        self, experiments: list[Experiment]
    ) -> list[ScheduleConflict]:
        """Detect scheduling conflicts among experiments."""
        conflicts: list[ScheduleConflict] = []

        for i, a in enumerate(experiments):
            for j, b in enumerate(experiments):
                if j <= i:
                    continue

                # Target overlap
                overlap = set(a.target_components) & set(b.target_components)
                if overlap:
                    severity = len(overlap) / max(
                        len(set(a.target_components) | set(b.target_components)), 1
                    )
                    conflicts.append(ScheduleConflict(
                        conflict_type=ConflictType.TARGET_OVERLAP,
                        experiment_ids=[a.id, b.id],
                        description=(
                            f"Experiments target overlapping components: "
                            f"{', '.join(sorted(overlap))}"
                        ),
                        severity=severity,
                        resolution_hint="Stagger experiments or remove overlapping targets",
                    ))

                # Incompatible types on same targets
                if overlap and _types_incompatible(a.experiment_type, b.experiment_type):
                    conflicts.append(ScheduleConflict(
                        conflict_type=ConflictType.SAFETY_VIOLATION,
                        experiment_ids=[a.id, b.id],
                        description=(
                            f"Incompatible experiment types "
                            f"({a.experiment_type.value}, {b.experiment_type.value}) "
                            f"on shared targets"
                        ),
                        severity=0.9,
                        resolution_hint="Do not run these experiment types concurrently on the same targets",
                    ))

                # Combined blast radius
                combined_blast = len(
                    set(a.target_components) | set(b.target_components)
                )
                limit = min(a.blast_radius_limit, b.blast_radius_limit)
                if combined_blast > limit:
                    conflicts.append(ScheduleConflict(
                        conflict_type=ConflictType.BLAST_RADIUS_EXCEEDED,
                        experiment_ids=[a.id, b.id],
                        description=(
                            f"Combined blast radius {combined_blast} exceeds "
                            f"limit {limit}"
                        ),
                        severity=0.7,
                        resolution_hint="Reduce the number of target components",
                    ))

        return conflicts

    def validate_safety(
        self, graph: InfraGraph, experiment: Experiment
    ) -> SafetyValidation:
        """Validate the safety of an experiment against the graph."""
        violations: list[str] = []
        warnings: list[str] = []
        affected: list[str] = list(experiment.target_components)
        requires_approval = experiment.requires_approval

        # Gather all affected components (including cascade)
        for cid in experiment.target_components:
            comp = graph.get_component(cid)
            if comp is None:
                continue  # skip non-existent; violation added below
            cascade = graph.get_all_affected(cid)
            for c in cascade:
                if c not in affected:
                    affected.append(c)

        max_blast = len(affected)

        # Check blast radius limit
        if max_blast > experiment.blast_radius_limit:
            violations.append(
                f"Blast radius {max_blast} exceeds limit "
                f"{experiment.blast_radius_limit}"
            )

        # Check target components exist
        for cid in experiment.target_components:
            comp = graph.get_component(cid)
            if comp is None:
                violations.append(f"Target component '{cid}' not found in graph")
                continue

            # Warn if component is already degraded or down
            if comp.health in (HealthStatus.DEGRADED, HealthStatus.OVERLOADED):
                warnings.append(
                    f"Component '{cid}' is already {comp.health.value}"
                )
            elif comp.health == HealthStatus.DOWN:
                violations.append(
                    f"Component '{cid}' is already DOWN — experiment is pointless"
                )

            # Warn if targeting a single-replica component with no failover
            if comp.replicas == 1 and not comp.failover.enabled:
                warnings.append(
                    f"Component '{cid}' is a SPOF (1 replica, no failover)"
                )

        # Safety-level based checks
        if experiment.safety_level == SafetyLevel.FORBIDDEN:
            violations.append("Experiment safety level is FORBIDDEN")
            requires_approval = True
        elif experiment.safety_level == SafetyLevel.DANGEROUS:
            warnings.append("Experiment safety level is DANGEROUS — proceed with caution")
            requires_approval = True

        # Check rollback plan for non-safe experiments
        if experiment.safety_level != SafetyLevel.SAFE and not experiment.rollback_plan:
            warnings.append("No rollback plan provided for non-safe experiment")

        # Check data corruption targets databases
        if experiment.experiment_type == ExperimentType.DATA_CORRUPTION:
            for cid in experiment.target_components:
                comp = graph.get_component(cid)
                if comp and comp.type == ComponentType.DATABASE:
                    if not comp.security.backup_enabled:
                        violations.append(
                            f"Data corruption on database '{cid}' without backups"
                        )
                    else:
                        warnings.append(
                            f"Data corruption on database '{cid}' — ensure recent backup"
                        )

        rollback_feasible = bool(experiment.rollback_plan) or experiment.safety_level == SafetyLevel.SAFE
        is_safe = len(violations) == 0

        return SafetyValidation(
            is_safe=is_safe,
            safety_level=experiment.safety_level,
            violations=violations,
            warnings=warnings,
            affected_components=affected,
            max_blast_radius=max_blast,
            requires_approval=requires_approval,
            rollback_feasible=rollback_feasible,
        )

    def find_safe_window(
        self, graph: InfraGraph, experiment: Experiment
    ) -> TimeWindow:
        """Find a safe time window for the experiment.

        Logic:
        - Use component utilisation to estimate off-peak offset.
        - Return a window type based on experiment safety level.
        """
        avg_util = 0.0
        count = 0
        for cid in experiment.target_components:
            comp = graph.get_component(cid)
            if comp:
                avg_util += comp.utilization()
                count += 1

        if count > 0:
            avg_util /= count

        # High utilisation → push to later maintenance window
        if avg_util > 70.0:
            start = 360.0  # 6 hours from now
            wtype = WindowType.MAINTENANCE
        elif avg_util > 40.0:
            start = 120.0  # 2 hours
            wtype = WindowType.SAFE_WINDOW
        else:
            start = 0.0
            wtype = WindowType.SAFE_WINDOW

        # Dangerous experiments only in maintenance windows
        if experiment.safety_level in (SafetyLevel.DANGEROUS, SafetyLevel.FORBIDDEN):
            wtype = WindowType.MAINTENANCE
            start = max(start, 360.0)

        return TimeWindow(
            start_offset_minutes=start,
            end_offset_minutes=start + experiment.duration_minutes,
            window_type=wtype,
            label=f"Safe window for {experiment.name}",
            available=True,
        )

    def estimate_risk(self, graph: InfraGraph, experiment: Experiment) -> float:
        """Estimate the risk score (0.0–1.0) for an experiment.

        Factors:
        - Experiment type weight
        - Safety level multiplier
        - Blast radius relative to total graph size
        - Target component criticality (dependents count)
        - Duration factor
        """
        type_weight = _TYPE_RISK_WEIGHTS.get(experiment.experiment_type, 0.5)
        safety_mult = _SAFETY_MULTIPLIERS.get(experiment.safety_level, 0.5)

        # Blast radius factor
        total_components = len(graph.components) if graph.components else 1
        blast = self._compute_blast_radius(graph, experiment)
        blast_factor = min(1.0, blast / total_components)

        # Criticality — how many dependents do the targets have
        criticality = 0.0
        for cid in experiment.target_components:
            dependents = graph.get_dependents(cid)
            criticality += len(dependents)
        if experiment.target_components:
            criticality /= len(experiment.target_components)
        criticality_factor = min(1.0, criticality / max(total_components, 1))

        # Duration factor — longer experiments are riskier
        duration_factor = min(1.0, experiment.duration_minutes / 60.0)

        raw_risk = (
            type_weight * 0.30
            + safety_mult * 0.25
            + blast_factor * 0.20
            + criticality_factor * 0.15
            + duration_factor * 0.10
        )
        return round(min(1.0, max(0.0, raw_risk)), 4)

    def generate_experiment_plan(self, graph: InfraGraph) -> list[Experiment]:
        """Auto-generate a set of chaos experiments based on graph topology.

        Heuristics:
        - Failure injection for SPOFs
        - Latency injection for high-latency edges
        - Resource stress for highly utilised components
        - Network chaos for multi-dependency components
        - Load test for entry points (no dependents targeting them as source)
        """
        experiments: list[Experiment] = []
        counter = 0

        for comp in graph.components.values():
            dependents = graph.get_dependents(comp.id)
            deps = graph.get_dependencies(comp.id)

            # SPOF detection — single replica with dependents
            if comp.replicas == 1 and len(dependents) > 0 and not comp.failover.enabled:
                counter += 1
                experiments.append(Experiment(
                    id=f"auto-{counter:03d}",
                    name=f"SPOF failure: {comp.name}",
                    experiment_type=ExperimentType.FAILURE_INJECTION,
                    target_components=[comp.id],
                    safety_level=SafetyLevel.CAUTION,
                    duration_minutes=15.0,
                    blast_radius_limit=max(3, len(dependents) + 1),
                    requires_approval=True,
                    rollback_plan=f"Restart {comp.name} and verify health",
                ))

            # High utilisation — resource stress
            util = comp.utilization()
            if util > 60.0:
                counter += 1
                experiments.append(Experiment(
                    id=f"auto-{counter:03d}",
                    name=f"Resource stress: {comp.name}",
                    experiment_type=ExperimentType.RESOURCE_STRESS,
                    target_components=[comp.id],
                    safety_level=SafetyLevel.CAUTION if util < 80 else SafetyLevel.DANGEROUS,
                    duration_minutes=10.0,
                    blast_radius_limit=3,
                    requires_approval=util > 80,
                    rollback_plan=f"Release resources on {comp.name}",
                ))

            # Multi-dependency — network chaos
            if len(deps) >= 2:
                counter += 1
                experiments.append(Experiment(
                    id=f"auto-{counter:03d}",
                    name=f"Network chaos: {comp.name}",
                    experiment_type=ExperimentType.NETWORK_CHAOS,
                    target_components=[comp.id],
                    safety_level=SafetyLevel.CAUTION,
                    duration_minutes=10.0,
                    blast_radius_limit=4,
                    requires_approval=False,
                    rollback_plan=f"Restore network for {comp.name}",
                ))

            # Entry point — load test (no predecessors in the dependency graph)
            if len(dependents) == 0 and len(deps) > 0:
                counter += 1
                experiments.append(Experiment(
                    id=f"auto-{counter:03d}",
                    name=f"Load test: {comp.name}",
                    experiment_type=ExperimentType.LOAD_TEST,
                    target_components=[comp.id],
                    safety_level=SafetyLevel.SAFE,
                    duration_minutes=20.0,
                    blast_radius_limit=5,
                    requires_approval=False,
                    rollback_plan=f"Stop load generator for {comp.name}",
                ))

            # Database — data corruption test (only if backup enabled)
            if comp.type == ComponentType.DATABASE and comp.security.backup_enabled:
                counter += 1
                experiments.append(Experiment(
                    id=f"auto-{counter:03d}",
                    name=f"Data integrity: {comp.name}",
                    experiment_type=ExperimentType.DATA_CORRUPTION,
                    target_components=[comp.id],
                    safety_level=SafetyLevel.DANGEROUS,
                    duration_minutes=5.0,
                    blast_radius_limit=2,
                    requires_approval=True,
                    rollback_plan=f"Restore {comp.name} from latest backup",
                ))

            # Latency injection for edges with high latency
            for dep_comp in deps:
                edge = graph.get_dependency_edge(comp.id, dep_comp.id)
                if edge and edge.latency_ms > 50.0:
                    counter += 1
                    experiments.append(Experiment(
                        id=f"auto-{counter:03d}",
                        name=f"Latency spike: {comp.name} -> {dep_comp.name}",
                        experiment_type=ExperimentType.LATENCY_INJECTION,
                        target_components=[comp.id, dep_comp.id],
                        safety_level=SafetyLevel.SAFE,
                        duration_minutes=10.0,
                        blast_radius_limit=4,
                        requires_approval=False,
                        rollback_plan=f"Remove latency injection on {comp.id}->{dep_comp.id}",
                    ))

        return experiments

    def simulate_concurrent_experiments(
        self, graph: InfraGraph, experiments: list[Experiment]
    ) -> ConcurrentResult:
        """Simulate running multiple experiments concurrently.

        Evaluates interaction effects, combined blast radius, and cascading
        failures across all experiments running at the same time.
        """
        if not experiments:
            return ConcurrentResult(is_safe=True)

        per_experiment: list[ConcurrentImpact] = []
        all_affected: set[str] = set()
        all_targets: set[str] = set()
        interaction_effects: list[str] = []
        cascading_failures: list[str] = []
        recommendations: list[str] = []

        for exp in experiments:
            targets = set(exp.target_components)
            all_targets |= targets

            cascade: set[str] = set()
            for cid in exp.target_components:
                cascade |= graph.get_all_affected(cid)

            risk = self.estimate_risk(graph, exp)
            per_experiment.append(ConcurrentImpact(
                experiment_id=exp.id,
                individual_risk=risk,
                added_blast_radius=len(targets | cascade),
                cascading_components=sorted(cascade - targets),
            ))

            for c in cascade:
                if c not in all_affected:
                    all_affected.add(c)
                else:
                    cascading_failures.append(c)

            all_affected |= targets

        # Detect interaction effects between experiments
        for i, a in enumerate(experiments):
            for j, b in enumerate(experiments):
                if j <= i:
                    continue
                overlap = set(a.target_components) & set(b.target_components)
                if overlap:
                    interaction_effects.append(
                        f"{a.name} and {b.name} share targets: "
                        f"{', '.join(sorted(overlap))}"
                    )

                # Check if one experiment's cascade hits another's targets
                for cid in a.target_components:
                    a_cascade = graph.get_all_affected(cid)
                    b_hit = a_cascade & set(b.target_components)
                    if b_hit:
                        interaction_effects.append(
                            f"Cascade from {a.name} affects {b.name}'s targets: "
                            f"{', '.join(sorted(b_hit))}"
                        )

        combined_blast = len(all_affected)
        total_risk_raw = sum(p.individual_risk for p in per_experiment)
        # Apply interaction penalty
        interaction_penalty = len(interaction_effects) * 0.05
        total_risk = min(1.0, total_risk_raw / max(len(experiments), 1) + interaction_penalty)

        is_safe = total_risk < 0.7 and not cascading_failures

        if cascading_failures:
            recommendations.append(
                "Multiple experiments cause cascading to the same components — "
                "stagger execution"
            )
        if combined_blast > 5:
            recommendations.append(
                f"Combined blast radius ({combined_blast}) is high — "
                "consider reducing concurrent experiments"
            )
        if interaction_effects:
            recommendations.append(
                "Interaction effects detected — review experiment ordering"
            )

        return ConcurrentResult(
            total_risk=round(total_risk, 4),
            combined_blast_radius=combined_blast,
            interaction_effects=interaction_effects,
            is_safe=is_safe,
            max_concurrent_reached=len(experiments),
            per_experiment=per_experiment,
            cascading_failures=sorted(set(cascading_failures)),
            recommendations=recommendations,
        )

    # -- private helpers ----------------------------------------------------

    def _compute_blast_radius(
        self, graph: InfraGraph, experiment: Experiment
    ) -> int:
        """Compute total blast radius including cascade."""
        affected: set[str] = set(experiment.target_components)
        for cid in experiment.target_components:
            if graph.get_component(cid) is not None:
                affected |= graph.get_all_affected(cid)
        return len(affected)
