# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Disaster Recovery Orchestrator -- step-by-step coordination of recovery procedures.

Orchestrates and validates disaster recovery procedures with:
- DR runbook step sequencing and dependency resolution
- Parallel vs sequential recovery step optimisation
- Recovery time estimation with critical path analysis
- DR drill simulation -- execute a full DR drill virtually
- Failover/failback coordination across multiple services
- Data consistency validation during recovery
- Communication plan generation (who to notify, when, what)
- DR automation gap detection (manual vs automated steps)
- Recovery priority scoring based on business impact
- Cross-region failover orchestration
- DR test coverage analysis -- which scenarios have been tested
- Recovery checkpoint validation
- Post-recovery health verification planning

NOTE: This is DIFFERENT from disaster_recovery.py (basic DR), dr_engine.py
(DR simulation engine), dr_readiness.py (readiness assessment).  This module
focuses on ORCHESTRATION -- the actual step-by-step coordination of recovery
procedures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from faultray.model.components import Component
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class StepStatus(str, Enum):
    """Execution status of a recovery step."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class StepExecutionMode(str, Enum):
    """Whether a step runs sequentially or can be parallelised."""

    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"


class AutomationLevel(str, Enum):
    """How automated a recovery step is."""

    MANUAL = "manual"
    SEMI_AUTOMATED = "semi_automated"
    FULLY_AUTOMATED = "fully_automated"


class RecoveryPhase(str, Enum):
    """High-level phases of a disaster recovery procedure."""

    DETECTION = "detection"
    TRIAGE = "triage"
    FAILOVER = "failover"
    DATA_VALIDATION = "data_validation"
    SERVICE_RESTORATION = "service_restoration"
    HEALTH_CHECK = "health_check"
    FAILBACK = "failback"
    POST_RECOVERY = "post_recovery"


class DrillOutcome(str, Enum):
    """Outcome of a DR drill simulation."""

    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILURE = "failure"


class PriorityTier(str, Enum):
    """Recovery priority tiers based on business impact."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class NotificationChannel(str, Enum):
    """Communication channels for notifications."""

    PAGER = "pager"
    SLACK = "slack"
    EMAIL = "email"
    SMS = "sms"
    STATUS_PAGE = "status_page"
    PHONE = "phone"


class CheckpointStatus(str, Enum):
    """Validation status of a recovery checkpoint."""

    NOT_REACHED = "not_reached"
    PASSED = "passed"
    FAILED = "failed"
    BYPASSED = "bypassed"


class HealthCheckResult(str, Enum):
    """Result of a post-recovery health check."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class RegionRole(str, Enum):
    """Role of a region in cross-region failover."""

    PRIMARY = "primary"
    SECONDARY = "secondary"
    STANDBY = "standby"


# ---------------------------------------------------------------------------
# Dataclasses -- result models
# ---------------------------------------------------------------------------


@dataclass
class RecoveryStep:
    """A single step in a disaster recovery procedure."""

    step_id: str
    name: str
    description: str = ""
    phase: RecoveryPhase = RecoveryPhase.FAILOVER
    component_ids: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    execution_mode: StepExecutionMode = StepExecutionMode.SEQUENTIAL
    automation_level: AutomationLevel = AutomationLevel.MANUAL
    estimated_duration_seconds: float = 60.0
    status: StepStatus = StepStatus.PENDING
    responsible_team: str = "operations"
    rollback_step_id: str = ""
    verification_command: str = ""
    timeout_seconds: float = 300.0


@dataclass
class StepDependencyGraph:
    """Resolved dependency graph for recovery steps."""

    steps: list[RecoveryStep] = field(default_factory=list)
    execution_order: list[list[str]] = field(default_factory=list)
    total_sequential_time_seconds: float = 0.0
    critical_path_seconds: float = 0.0
    parallelisable_groups: int = 0
    has_cycles: bool = False
    unresolved_deps: list[str] = field(default_factory=list)


@dataclass
class CriticalPathResult:
    """Critical path analysis for recovery time estimation."""

    path_step_ids: list[str] = field(default_factory=list)
    total_duration_seconds: float = 0.0
    bottleneck_step_id: str = ""
    bottleneck_duration_seconds: float = 0.0
    parallel_savings_seconds: float = 0.0
    estimated_rto_seconds: float = 0.0


@dataclass
class DrillEvent:
    """A single event during a DR drill simulation."""

    timestamp_offset_seconds: float = 0.0
    step_id: str = ""
    event_type: str = ""
    message: str = ""
    success: bool = True


@dataclass
class DrillSimulationResult:
    """Full result of a virtual DR drill."""

    outcome: DrillOutcome = DrillOutcome.SUCCESS
    total_duration_seconds: float = 0.0
    steps_completed: int = 0
    steps_failed: int = 0
    steps_skipped: int = 0
    events: list[DrillEvent] = field(default_factory=list)
    data_loss_seconds: float = 0.0
    rto_achieved_seconds: float = 0.0
    rpo_achieved_seconds: float = 0.0
    recommendations: list[str] = field(default_factory=list)


@dataclass
class FailoverCoordinationPlan:
    """Failover/failback coordination across multiple services."""

    failover_order: list[str] = field(default_factory=list)
    failback_order: list[str] = field(default_factory=list)
    data_stores_first: list[str] = field(default_factory=list)
    app_services: list[str] = field(default_factory=list)
    total_failover_time_seconds: float = 0.0
    total_failback_time_seconds: float = 0.0
    coordination_notes: list[str] = field(default_factory=list)


@dataclass
class DataConsistencyCheck:
    """Data consistency validation result for a component."""

    component_id: str = ""
    is_consistent: bool = True
    replication_lag_seconds: float = 0.0
    checksum_match: bool = True
    records_behind: int = 0
    validation_method: str = "checksum"
    recommendation: str = ""


@dataclass
class DataConsistencyReport:
    """Aggregated data consistency report across all data stores."""

    checks: list[DataConsistencyCheck] = field(default_factory=list)
    all_consistent: bool = True
    max_lag_seconds: float = 0.0
    components_with_issues: int = 0


@dataclass
class NotificationEntry:
    """A single notification in the communication plan."""

    order: int = 0
    audience: str = ""
    channel: NotificationChannel = NotificationChannel.EMAIL
    message_template: str = ""
    timing_description: str = ""
    responsible: str = "incident_commander"
    phase: RecoveryPhase = RecoveryPhase.DETECTION


@dataclass
class CommunicationPlanResult:
    """Generated communication plan for DR events."""

    notifications: list[NotificationEntry] = field(default_factory=list)
    escalation_chain: list[str] = field(default_factory=list)
    update_frequency_minutes: int = 30
    total_notifications: int = 0
    phases_covered: list[str] = field(default_factory=list)


@dataclass
class AutomationGap:
    """A detected gap in DR automation."""

    step_id: str = ""
    step_name: str = ""
    current_level: AutomationLevel = AutomationLevel.MANUAL
    recommended_level: AutomationLevel = AutomationLevel.FULLY_AUTOMATED
    estimated_time_saving_seconds: float = 0.0
    effort_to_automate: str = "medium"
    recommendation: str = ""


@dataclass
class AutomationGapReport:
    """Aggregated automation gap analysis."""

    gaps: list[AutomationGap] = field(default_factory=list)
    total_manual_steps: int = 0
    total_semi_automated_steps: int = 0
    total_fully_automated_steps: int = 0
    automation_percentage: float = 0.0
    potential_time_saving_seconds: float = 0.0


@dataclass
class RecoveryPriorityEntry:
    """Recovery priority scoring for a single component."""

    component_id: str = ""
    priority_tier: PriorityTier = PriorityTier.MEDIUM
    priority_score: float = 0.0
    revenue_impact_per_minute: float = 0.0
    dependent_count: int = 0
    is_data_store: bool = False
    has_failover: bool = False
    recovery_order: int = 0


@dataclass
class RecoveryPriorityPlan:
    """Recovery priority plan for all components."""

    entries: list[RecoveryPriorityEntry] = field(default_factory=list)
    ordered_component_ids: list[str] = field(default_factory=list)
    total_components: int = 0
    critical_count: int = 0
    high_count: int = 0


@dataclass
class RegionState:
    """State of a single region in cross-region failover."""

    region_name: str = ""
    role: RegionRole = RegionRole.PRIMARY
    component_ids: list[str] = field(default_factory=list)
    is_healthy: bool = True
    failover_time_seconds: float = 0.0


@dataclass
class CrossRegionFailoverPlan:
    """Cross-region failover orchestration plan."""

    regions: list[RegionState] = field(default_factory=list)
    primary_region: str = ""
    target_region: str = ""
    failover_sequence: list[str] = field(default_factory=list)
    total_failover_time_seconds: float = 0.0
    dns_propagation_seconds: float = 0.0
    data_sync_seconds: float = 0.0
    recommendations: list[str] = field(default_factory=list)


@dataclass
class TestCoverageEntry:
    """DR test coverage for a single scenario."""

    scenario_name: str = ""
    is_tested: bool = False
    last_tested_iso: str = ""
    test_frequency: str = "never"
    components_covered: list[str] = field(default_factory=list)
    gap_description: str = ""


@dataclass
class DRTestCoverageReport:
    """Aggregated DR test coverage analysis."""

    entries: list[TestCoverageEntry] = field(default_factory=list)
    total_scenarios: int = 0
    tested_scenarios: int = 0
    coverage_percentage: float = 0.0
    untested_critical: list[str] = field(default_factory=list)


@dataclass
class RecoveryCheckpoint:
    """A checkpoint to validate during recovery."""

    checkpoint_id: str = ""
    name: str = ""
    phase: RecoveryPhase = RecoveryPhase.FAILOVER
    validation_command: str = ""
    expected_result: str = ""
    status: CheckpointStatus = CheckpointStatus.NOT_REACHED
    component_ids: list[str] = field(default_factory=list)
    is_blocking: bool = True


@dataclass
class CheckpointValidationResult:
    """Checkpoint validation results across all checkpoints."""

    checkpoints: list[RecoveryCheckpoint] = field(default_factory=list)
    total_checkpoints: int = 0
    passed_checkpoints: int = 0
    failed_checkpoints: int = 0
    blocking_failures: int = 0
    can_proceed: bool = True


@dataclass
class HealthCheckEntry:
    """Post-recovery health check for a component."""

    component_id: str = ""
    check_name: str = ""
    result: HealthCheckResult = HealthCheckResult.UNKNOWN
    details: str = ""
    is_critical: bool = False
    verification_command: str = ""


@dataclass
class PostRecoveryHealthPlan:
    """Post-recovery health verification plan."""

    checks: list[HealthCheckEntry] = field(default_factory=list)
    total_checks: int = 0
    critical_checks: int = 0
    estimated_verification_time_seconds: float = 0.0
    phases: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PHASE_ORDER: dict[RecoveryPhase, int] = {
    RecoveryPhase.DETECTION: 0,
    RecoveryPhase.TRIAGE: 1,
    RecoveryPhase.FAILOVER: 2,
    RecoveryPhase.DATA_VALIDATION: 3,
    RecoveryPhase.SERVICE_RESTORATION: 4,
    RecoveryPhase.HEALTH_CHECK: 5,
    RecoveryPhase.FAILBACK: 6,
    RecoveryPhase.POST_RECOVERY: 7,
}

_DATA_STORE_TYPES: set[str] = {"database", "storage", "cache"}

_AUTOMATION_TIME_FACTOR: dict[AutomationLevel, float] = {
    AutomationLevel.MANUAL: 1.0,
    AutomationLevel.SEMI_AUTOMATED: 0.5,
    AutomationLevel.FULLY_AUTOMATED: 0.1,
}


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class DROrchestrator:
    """Orchestrates disaster recovery procedures on an InfraGraph.

    Provides step sequencing, dependency resolution, parallel optimisation,
    critical path analysis, drill simulation, failover/failback coordination,
    data consistency validation, communication planning, automation gap
    detection, priority scoring, cross-region orchestration, test coverage
    analysis, checkpoint validation, and post-recovery health verification.
    """

    def __init__(self, graph: InfraGraph) -> None:
        self.graph = graph

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _components(self) -> dict[str, Component]:
        return self.graph.components

    def _is_data_store(self, comp: Component) -> bool:
        return comp.type.value in _DATA_STORE_TYPES

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _component_rto(self, comp: Component) -> float:
        if comp.failover.enabled:
            return comp.failover.promotion_time_seconds
        mttr = comp.operational_profile.mttr_minutes
        if mttr > 0:
            return mttr * 60.0
        return 300.0

    def _component_rpo(self, comp: Component) -> float:
        rpo = comp.region.rpo_seconds
        if rpo > 0:
            return float(rpo)
        if comp.failover.enabled:
            return 5.0
        if comp.security.backup_enabled:
            return comp.security.backup_frequency_hours * 3600.0
        return 3600.0

    def _revenue_per_minute(self, comp: Component) -> float:
        return comp.cost_profile.revenue_per_minute

    def _dependent_count(self, comp: Component) -> int:
        return len(self.graph.get_dependents(comp.id))

    def _sorted_components_by_type(self) -> tuple[list[str], list[str]]:
        """Return (data_store_ids, other_ids) sorted by id."""
        ds: list[str] = []
        other: list[str] = []
        for cid in sorted(self._components()):
            comp = self._components()[cid]
            if self._is_data_store(comp):
                ds.append(cid)
            else:
                other.append(cid)
        return ds, other

    # ------------------------------------------------------------------
    # 1. Runbook step sequencing & dependency resolution
    # ------------------------------------------------------------------

    def build_recovery_steps(self) -> list[RecoveryStep]:
        """Build the full list of recovery steps from the infrastructure graph.

        Steps are generated per-component and grouped by phase.  Data stores
        get failover steps before application services.  Each step is assigned
        dependencies so that the graph is self-consistent.
        """
        steps: list[RecoveryStep] = []
        comps = self._components()
        if not comps:
            return steps

        ds_ids, app_ids = self._sorted_components_by_type()

        # Phase: Detection
        detect_step = RecoveryStep(
            step_id="detect_1",
            name="Detect disaster event",
            description="Monitor alerts and confirm disaster",
            phase=RecoveryPhase.DETECTION,
            component_ids=sorted(comps.keys()),
            automation_level=AutomationLevel.FULLY_AUTOMATED,
            estimated_duration_seconds=30.0,
            responsible_team="monitoring",
            verification_command="check_alerts",
        )
        steps.append(detect_step)

        # Phase: Triage
        triage_step = RecoveryStep(
            step_id="triage_1",
            name="Triage and assess blast radius",
            description="Determine affected components and severity",
            phase=RecoveryPhase.TRIAGE,
            component_ids=sorted(comps.keys()),
            depends_on=["detect_1"],
            automation_level=AutomationLevel.SEMI_AUTOMATED,
            estimated_duration_seconds=120.0,
            responsible_team="incident_commander",
            verification_command="list_affected_components",
        )
        steps.append(triage_step)

        # Phase: Failover -- data stores first
        failover_deps = ["triage_1"]
        for cid in ds_ids:
            comp = comps[cid]
            auto = AutomationLevel.FULLY_AUTOMATED if comp.failover.enabled else AutomationLevel.MANUAL
            dur = self._component_rto(comp)
            step = RecoveryStep(
                step_id=f"failover_ds_{cid}",
                name=f"Failover data store {cid}",
                description=f"Failover {cid} to DR site",
                phase=RecoveryPhase.FAILOVER,
                component_ids=[cid],
                depends_on=list(failover_deps),
                execution_mode=StepExecutionMode.PARALLEL,
                automation_level=auto,
                estimated_duration_seconds=dur,
                responsible_team="dba",
                rollback_step_id=f"failback_ds_{cid}",
                verification_command=f"verify_failover {cid}",
            )
            steps.append(step)

        # Data validation after data store failover
        ds_failover_ids = [f"failover_ds_{cid}" for cid in ds_ids]
        if ds_ids:
            validate_data_step = RecoveryStep(
                step_id="validate_data_1",
                name="Validate data consistency",
                description="Verify data integrity post failover",
                phase=RecoveryPhase.DATA_VALIDATION,
                component_ids=list(ds_ids),
                depends_on=ds_failover_ids if ds_failover_ids else ["triage_1"],
                automation_level=AutomationLevel.SEMI_AUTOMATED,
                estimated_duration_seconds=60.0,
                responsible_team="dba",
                verification_command="check_data_integrity",
            )
            steps.append(validate_data_step)
            service_deps = ["validate_data_1"]
        else:
            service_deps = ["triage_1"]

        # Phase: Service restoration -- app services
        for cid in app_ids:
            comp = comps[cid]
            auto = AutomationLevel.FULLY_AUTOMATED if comp.failover.enabled else AutomationLevel.MANUAL
            dur = self._component_rto(comp)
            step = RecoveryStep(
                step_id=f"restore_svc_{cid}",
                name=f"Restore service {cid}",
                description=f"Bring {cid} online in DR",
                phase=RecoveryPhase.SERVICE_RESTORATION,
                component_ids=[cid],
                depends_on=list(service_deps),
                execution_mode=StepExecutionMode.PARALLEL,
                automation_level=auto,
                estimated_duration_seconds=dur,
                responsible_team="sre",
                rollback_step_id=f"failback_svc_{cid}",
                verification_command=f"health_check {cid}",
            )
            steps.append(step)

        # Phase: Health check
        svc_step_ids = [f"restore_svc_{cid}" for cid in app_ids]
        all_prior = svc_step_ids if svc_step_ids else service_deps
        health_step = RecoveryStep(
            step_id="health_check_1",
            name="Post-recovery health check",
            description="Verify all services healthy",
            phase=RecoveryPhase.HEALTH_CHECK,
            component_ids=sorted(comps.keys()),
            depends_on=list(all_prior),
            automation_level=AutomationLevel.FULLY_AUTOMATED,
            estimated_duration_seconds=90.0,
            responsible_team="sre",
            verification_command="run_smoke_tests",
        )
        steps.append(health_step)

        return steps

    def resolve_dependencies(
        self, steps: list[RecoveryStep] | None = None,
    ) -> StepDependencyGraph:
        """Resolve step dependencies and compute execution order.

        Uses topological-sort style layering.  Each layer contains steps
        whose dependencies are fully satisfied by previous layers.  Steps
        within a layer can execute in parallel.
        """
        if steps is None:
            steps = self.build_recovery_steps()

        step_map: dict[str, RecoveryStep] = {s.step_id: s for s in steps}
        all_ids = set(step_map.keys())

        # Check for unresolved dependencies
        unresolved: list[str] = []
        for s in steps:
            for dep in s.depends_on:
                if dep not in all_ids:
                    unresolved.append(dep)

        # Topological layering (Kahn's algorithm variant)
        in_degree: dict[str, int] = {sid: 0 for sid in all_ids}
        for s in steps:
            for dep in s.depends_on:
                if dep in all_ids:
                    in_degree[s.step_id] += 1

        remaining = set(all_ids)
        layers: list[list[str]] = []
        has_cycles = False

        while remaining:
            layer = [sid for sid in sorted(remaining) if in_degree[sid] == 0]
            if not layer:
                has_cycles = True
                # Break cycle by picking one remaining step
                layer = [sorted(remaining)[0]]
            layers.append(layer)
            for sid in layer:
                remaining.discard(sid)
                for s in steps:
                    if sid in s.depends_on and s.step_id in remaining:
                        in_degree[s.step_id] -= 1

        # Compute timing
        total_sequential = sum(s.estimated_duration_seconds for s in steps)

        # Critical path: sum of max per-layer durations
        critical = 0.0
        for layer in layers:
            max_dur = max(
                (step_map[sid].estimated_duration_seconds for sid in layer),
                default=0.0,
            )
            critical += max_dur

        parallel_groups = sum(1 for layer in layers if len(layer) > 1)

        return StepDependencyGraph(
            steps=steps,
            execution_order=layers,
            total_sequential_time_seconds=round(total_sequential, 2),
            critical_path_seconds=round(critical, 2),
            parallelisable_groups=parallel_groups,
            has_cycles=has_cycles,
            unresolved_deps=unresolved,
        )

    # ------------------------------------------------------------------
    # 2. Parallel vs sequential optimisation
    # ------------------------------------------------------------------

    def optimise_parallelism(
        self, steps: list[RecoveryStep] | None = None,
    ) -> StepDependencyGraph:
        """Mark steps that can safely run in parallel and return optimised graph.

        Steps targeting different components in the same phase with no
        cross-dependencies can be parallelised.
        """
        if steps is None:
            steps = self.build_recovery_steps()

        # Identify steps that share no component_ids and have compatible deps
        step_map: dict[str, RecoveryStep] = {s.step_id: s for s in steps}

        # Group by phase
        phase_groups: dict[RecoveryPhase, list[str]] = {}
        for s in steps:
            phase_groups.setdefault(s.phase, []).append(s.step_id)

        for phase, sids in phase_groups.items():
            if len(sids) < 2:
                continue
            # Mark all steps in this phase as parallel if they share no components
            for i, sid_a in enumerate(sids):
                for sid_b in sids[i + 1:]:
                    s_a = step_map[sid_a]
                    s_b = step_map[sid_b]
                    shared = set(s_a.component_ids) & set(s_b.component_ids)
                    if not shared:
                        s_a.execution_mode = StepExecutionMode.PARALLEL
                        s_b.execution_mode = StepExecutionMode.PARALLEL

        return self.resolve_dependencies(steps)

    # ------------------------------------------------------------------
    # 3. Recovery time estimation with critical path analysis
    # ------------------------------------------------------------------

    def estimate_critical_path(
        self, steps: list[RecoveryStep] | None = None,
    ) -> CriticalPathResult:
        """Compute the critical path -- longest chain determining total RTO.

        Returns the path through the dependency graph that has the highest
        cumulative duration.
        """
        if steps is None:
            steps = self.build_recovery_steps()

        step_map: dict[str, RecoveryStep] = {s.step_id: s for s in steps}
        all_ids = set(step_map.keys())

        # Compute longest path using dynamic programming
        memo: dict[str, float] = {}
        path_map: dict[str, list[str]] = {}

        def _longest(sid: str) -> float:
            if sid in memo:
                return memo[sid]
            s = step_map[sid]
            dur = s.estimated_duration_seconds
            if not s.depends_on:
                memo[sid] = dur
                path_map[sid] = [sid]
                return dur
            best = 0.0
            best_dep = ""
            for dep in s.depends_on:
                if dep in all_ids:
                    val = _longest(dep)
                    if val > best:
                        best = val
                        best_dep = dep
            memo[sid] = dur + best
            if best_dep:
                path_map[sid] = path_map.get(best_dep, []) + [sid]
            else:
                path_map[sid] = [sid]
            return memo[sid]

        # Find the step with longest total path
        max_total = 0.0
        max_sid = ""
        for sid in all_ids:
            val = _longest(sid)
            if val > max_total:
                max_total = val
                max_sid = sid

        path_ids = path_map.get(max_sid, [])

        # Find bottleneck
        bottleneck_id = ""
        bottleneck_dur = 0.0
        for sid in path_ids:
            dur = step_map[sid].estimated_duration_seconds
            if dur > bottleneck_dur:
                bottleneck_dur = dur
                bottleneck_id = sid

        total_sequential = sum(s.estimated_duration_seconds for s in steps)
        parallel_savings = total_sequential - max_total

        return CriticalPathResult(
            path_step_ids=path_ids,
            total_duration_seconds=round(max_total, 2),
            bottleneck_step_id=bottleneck_id,
            bottleneck_duration_seconds=round(bottleneck_dur, 2),
            parallel_savings_seconds=round(max(0.0, parallel_savings), 2),
            estimated_rto_seconds=round(max_total, 2),
        )

    # ------------------------------------------------------------------
    # 4. DR drill simulation
    # ------------------------------------------------------------------

    def simulate_drill(
        self,
        steps: list[RecoveryStep] | None = None,
        *,
        failure_step_ids: list[str] | None = None,
    ) -> DrillSimulationResult:
        """Simulate a full DR drill virtually.

        Parameters
        ----------
        steps:
            Recovery steps to simulate.  Defaults to ``build_recovery_steps()``.
        failure_step_ids:
            Step IDs that should be simulated as failing.  If *None*, all
            steps succeed.
        """
        if steps is None:
            steps = self.build_recovery_steps()
        if failure_step_ids is None:
            failure_step_ids = []

        dep_graph = self.resolve_dependencies(steps)
        step_map: dict[str, RecoveryStep] = {s.step_id: s for s in steps}

        events: list[DrillEvent] = []
        completed_ids: set[str] = set()
        failed_ids: set[str] = set()
        skipped_ids: set[str] = set()

        clock = 0.0
        completed_count = 0
        failed_count = 0
        skipped_count = 0

        for layer in dep_graph.execution_order:
            layer_max_dur = 0.0
            for sid in layer:
                s = step_map[sid]
                # Check if deps are satisfied
                unsatisfied = [d for d in s.depends_on if d in failed_ids or d in skipped_ids]
                if unsatisfied:
                    skipped_ids.add(sid)
                    skipped_count += 1
                    s.status = StepStatus.SKIPPED
                    events.append(DrillEvent(
                        timestamp_offset_seconds=clock,
                        step_id=sid,
                        event_type="skipped",
                        message=f"Skipped {s.name}: dependency failed",
                        success=False,
                    ))
                    continue

                events.append(DrillEvent(
                    timestamp_offset_seconds=clock,
                    step_id=sid,
                    event_type="start",
                    message=f"Starting {s.name}",
                    success=True,
                ))

                dur = s.estimated_duration_seconds
                time_factor = _AUTOMATION_TIME_FACTOR.get(s.automation_level, 1.0)
                effective_dur = dur * time_factor

                if sid in failure_step_ids:
                    failed_ids.add(sid)
                    failed_count += 1
                    s.status = StepStatus.FAILED
                    events.append(DrillEvent(
                        timestamp_offset_seconds=clock + effective_dur,
                        step_id=sid,
                        event_type="failed",
                        message=f"Failed: {s.name}",
                        success=False,
                    ))
                else:
                    completed_ids.add(sid)
                    completed_count += 1
                    s.status = StepStatus.COMPLETED
                    events.append(DrillEvent(
                        timestamp_offset_seconds=clock + effective_dur,
                        step_id=sid,
                        event_type="completed",
                        message=f"Completed {s.name}",
                        success=True,
                    ))

                if effective_dur > layer_max_dur:
                    layer_max_dur = effective_dur

            clock += layer_max_dur

        # Determine outcome
        if failed_count == 0 and skipped_count == 0:
            outcome = DrillOutcome.SUCCESS
        elif completed_count > 0 and failed_count > 0:
            outcome = DrillOutcome.PARTIAL_SUCCESS
        else:
            outcome = DrillOutcome.FAILURE

        # Estimate data loss
        max_rpo = 0.0
        for cid, comp in self._components().items():
            if self._is_data_store(comp):
                rpo = self._component_rpo(comp)
                if rpo > max_rpo:
                    max_rpo = rpo

        recommendations: list[str] = []
        if failed_count > 0:
            recommendations.append(
                f"{failed_count} step(s) failed -- review and fix automation"
            )
        if skipped_count > 0:
            recommendations.append(
                f"{skipped_count} step(s) skipped due to dependency failures"
            )
        manual_steps = [s for s in steps if s.automation_level == AutomationLevel.MANUAL]
        if manual_steps:
            recommendations.append(
                f"Automate {len(manual_steps)} manual step(s) to reduce RTO"
            )

        return DrillSimulationResult(
            outcome=outcome,
            total_duration_seconds=round(clock, 2),
            steps_completed=completed_count,
            steps_failed=failed_count,
            steps_skipped=skipped_count,
            events=events,
            data_loss_seconds=round(max_rpo, 2),
            rto_achieved_seconds=round(clock, 2),
            rpo_achieved_seconds=round(max_rpo, 2),
            recommendations=recommendations,
        )

    # ------------------------------------------------------------------
    # 5. Failover/failback coordination
    # ------------------------------------------------------------------

    def plan_failover_failback(self) -> FailoverCoordinationPlan:
        """Plan failover and failback order across all services.

        Data stores fail over first, then application services.
        Failback is the reverse order.
        """
        comps = self._components()
        ds_ids, app_ids = self._sorted_components_by_type()

        failover_order = list(ds_ids) + list(app_ids)
        failback_order = list(reversed(failover_order))

        total_fo = 0.0
        for cid in failover_order:
            total_fo += self._component_rto(comps[cid])

        # Failback generally takes longer (1.5x)
        total_fb = total_fo * 1.5

        notes: list[str] = []
        if ds_ids:
            notes.append(
                f"Failover data stores first: {', '.join(ds_ids)}"
            )
        if app_ids:
            notes.append(
                f"Then restore app services: {', '.join(app_ids)}"
            )
        if not ds_ids and not app_ids:
            notes.append("No components to coordinate")

        for cid in failover_order:
            comp = comps[cid]
            if not comp.failover.enabled:
                notes.append(f"Warning: {cid} has no failover configured")

        return FailoverCoordinationPlan(
            failover_order=failover_order,
            failback_order=failback_order,
            data_stores_first=ds_ids,
            app_services=app_ids,
            total_failover_time_seconds=round(total_fo, 2),
            total_failback_time_seconds=round(total_fb, 2),
            coordination_notes=notes,
        )

    # ------------------------------------------------------------------
    # 6. Data consistency validation
    # ------------------------------------------------------------------

    def validate_data_consistency(self) -> DataConsistencyReport:
        """Validate data consistency across all data store components.

        Estimates replication lag and consistency based on component
        configuration.
        """
        checks: list[DataConsistencyCheck] = []
        comps = self._components()

        for cid in sorted(comps.keys()):
            comp = comps[cid]
            if not self._is_data_store(comp):
                continue

            rpo = self._component_rpo(comp)

            if comp.failover.enabled:
                lag = min(rpo, 5.0)
                consistent = True
                method = "streaming_replication"
                records = 0
                rec = ""
            elif comp.security.backup_enabled:
                lag = comp.security.backup_frequency_hours * 3600.0
                consistent = lag <= 3600.0
                method = "periodic_backup"
                records = int(lag * 10)  # rough estimate
                rec = f"Reduce backup interval for {cid}" if not consistent else ""
            else:
                lag = rpo
                consistent = False
                method = "none"
                records = int(lag * 100)
                rec = f"Enable replication or backups for {cid}"

            checks.append(DataConsistencyCheck(
                component_id=cid,
                is_consistent=consistent,
                replication_lag_seconds=round(lag, 2),
                checksum_match=consistent,
                records_behind=records,
                validation_method=method,
                recommendation=rec,
            ))

        all_ok = all(c.is_consistent for c in checks) if checks else True
        max_lag = max((c.replication_lag_seconds for c in checks), default=0.0)
        issues = sum(1 for c in checks if not c.is_consistent)

        return DataConsistencyReport(
            checks=checks,
            all_consistent=all_ok,
            max_lag_seconds=round(max_lag, 2),
            components_with_issues=issues,
        )

    # ------------------------------------------------------------------
    # 7. Communication plan generation
    # ------------------------------------------------------------------

    def generate_communication_plan(self) -> CommunicationPlanResult:
        """Generate a communication plan for DR events.

        Produces a sequence of notifications covering each recovery phase
        with appropriate audiences, channels, and timing.
        """
        notifications: list[NotificationEntry] = [
            NotificationEntry(
                order=1,
                audience="On-Call Engineer",
                channel=NotificationChannel.PAGER,
                message_template="DR event detected: {event}. Acknowledge immediately.",
                timing_description="T+0 min",
                responsible="monitoring_system",
                phase=RecoveryPhase.DETECTION,
            ),
            NotificationEntry(
                order=2,
                audience="Incident Response Team",
                channel=NotificationChannel.SLACK,
                message_template="DR activated. Triage in progress. Join #incident channel.",
                timing_description="T+2 min",
                responsible="incident_commander",
                phase=RecoveryPhase.TRIAGE,
            ),
            NotificationEntry(
                order=3,
                audience="Engineering Leadership",
                channel=NotificationChannel.SLACK,
                message_template="Failover in progress. Affected: {components}. ETA: {eta}.",
                timing_description="T+5 min",
                responsible="incident_commander",
                phase=RecoveryPhase.FAILOVER,
            ),
            NotificationEntry(
                order=4,
                audience="Customer Support",
                channel=NotificationChannel.EMAIL,
                message_template="Service disruption. DR activated. Updates every {interval} min.",
                timing_description="T+10 min",
                responsible="communications_team",
                phase=RecoveryPhase.FAILOVER,
            ),
            NotificationEntry(
                order=5,
                audience="Affected Customers",
                channel=NotificationChannel.STATUS_PAGE,
                message_template="We are experiencing a disruption. Recovery in progress.",
                timing_description="T+15 min",
                responsible="communications_team",
                phase=RecoveryPhase.SERVICE_RESTORATION,
            ),
            NotificationEntry(
                order=6,
                audience="Executive Leadership",
                channel=NotificationChannel.EMAIL,
                message_template="DR summary: {summary}. Impact: {impact}. Status: {status}.",
                timing_description="T+30 min",
                responsible="incident_commander",
                phase=RecoveryPhase.SERVICE_RESTORATION,
            ),
            NotificationEntry(
                order=7,
                audience="All Stakeholders",
                channel=NotificationChannel.STATUS_PAGE,
                message_template="Recovery complete. Services restored. Post-incident review scheduled.",
                timing_description="T+recovery",
                responsible="communications_team",
                phase=RecoveryPhase.POST_RECOVERY,
            ),
            NotificationEntry(
                order=8,
                audience="Engineering Team",
                channel=NotificationChannel.EMAIL,
                message_template="Post-recovery: review action items. Blameless postmortem at {time}.",
                timing_description="T+recovery+24h",
                responsible="incident_commander",
                phase=RecoveryPhase.POST_RECOVERY,
            ),
        ]

        escalation = [
            "On-Call Engineer",
            "Incident Commander",
            "Engineering Manager",
            "VP Engineering",
            "CTO",
        ]

        phases_covered = sorted(
            {n.phase.value for n in notifications}
        )

        return CommunicationPlanResult(
            notifications=notifications,
            escalation_chain=escalation,
            update_frequency_minutes=30,
            total_notifications=len(notifications),
            phases_covered=phases_covered,
        )

    # ------------------------------------------------------------------
    # 8. DR automation gap detection
    # ------------------------------------------------------------------

    def detect_automation_gaps(
        self, steps: list[RecoveryStep] | None = None,
    ) -> AutomationGapReport:
        """Detect manual vs automated steps and recommend automation.

        Analyses each step's automation level and estimates time savings
        if the step were fully automated.
        """
        if steps is None:
            steps = self.build_recovery_steps()

        gaps: list[AutomationGap] = []
        total_manual = 0
        total_semi = 0
        total_auto = 0
        total_savings = 0.0

        for s in steps:
            if s.automation_level == AutomationLevel.MANUAL:
                total_manual += 1
                saving = s.estimated_duration_seconds * (1.0 - _AUTOMATION_TIME_FACTOR[AutomationLevel.FULLY_AUTOMATED])
                effort = "high" if s.estimated_duration_seconds > 300 else "medium"
                gaps.append(AutomationGap(
                    step_id=s.step_id,
                    step_name=s.name,
                    current_level=AutomationLevel.MANUAL,
                    recommended_level=AutomationLevel.FULLY_AUTOMATED,
                    estimated_time_saving_seconds=round(saving, 2),
                    effort_to_automate=effort,
                    recommendation=f"Automate '{s.name}' to reduce recovery time by {saving:.0f}s",
                ))
                total_savings += saving
            elif s.automation_level == AutomationLevel.SEMI_AUTOMATED:
                total_semi += 1
                saving = s.estimated_duration_seconds * (
                    _AUTOMATION_TIME_FACTOR[AutomationLevel.SEMI_AUTOMATED]
                    - _AUTOMATION_TIME_FACTOR[AutomationLevel.FULLY_AUTOMATED]
                )
                gaps.append(AutomationGap(
                    step_id=s.step_id,
                    step_name=s.name,
                    current_level=AutomationLevel.SEMI_AUTOMATED,
                    recommended_level=AutomationLevel.FULLY_AUTOMATED,
                    estimated_time_saving_seconds=round(saving, 2),
                    effort_to_automate="low",
                    recommendation=f"Fully automate '{s.name}' to save {saving:.0f}s",
                ))
                total_savings += saving
            else:
                total_auto += 1

        total_steps = len(steps)
        auto_pct = (total_auto / total_steps * 100.0) if total_steps > 0 else 0.0

        return AutomationGapReport(
            gaps=gaps,
            total_manual_steps=total_manual,
            total_semi_automated_steps=total_semi,
            total_fully_automated_steps=total_auto,
            automation_percentage=round(auto_pct, 1),
            potential_time_saving_seconds=round(total_savings, 2),
        )

    # ------------------------------------------------------------------
    # 9. Recovery priority scoring
    # ------------------------------------------------------------------

    def score_recovery_priorities(self) -> RecoveryPriorityPlan:
        """Score and rank components by recovery priority.

        Priority is determined by revenue impact, number of dependents,
        whether the component is a data store, and failover capability.
        """
        comps = self._components()
        entries: list[RecoveryPriorityEntry] = []

        for cid in sorted(comps.keys()):
            comp = comps[cid]
            rev = self._revenue_per_minute(comp)
            deps = self._dependent_count(comp)
            is_ds = self._is_data_store(comp)
            has_fo = comp.failover.enabled

            # Score: higher = more urgent to recover
            score = 0.0
            score += min(rev * 10.0, 40.0)  # revenue impact (max 40)
            score += min(deps * 5.0, 30.0)  # dependency weight (max 30)
            if is_ds:
                score += 20.0  # data stores are critical
            if not has_fo:
                score += 10.0  # no failover = more urgency

            if score >= 70.0:
                tier = PriorityTier.CRITICAL
            elif score >= 45.0:
                tier = PriorityTier.HIGH
            elif score >= 20.0:
                tier = PriorityTier.MEDIUM
            else:
                tier = PriorityTier.LOW

            entries.append(RecoveryPriorityEntry(
                component_id=cid,
                priority_tier=tier,
                priority_score=round(score, 2),
                revenue_impact_per_minute=rev,
                dependent_count=deps,
                is_data_store=is_ds,
                has_failover=has_fo,
            ))

        # Sort by score descending
        entries.sort(key=lambda e: e.priority_score, reverse=True)
        for i, entry in enumerate(entries):
            entry.recovery_order = i + 1

        ordered_ids = [e.component_id for e in entries]
        critical_count = sum(1 for e in entries if e.priority_tier == PriorityTier.CRITICAL)
        high_count = sum(1 for e in entries if e.priority_tier == PriorityTier.HIGH)

        return RecoveryPriorityPlan(
            entries=entries,
            ordered_component_ids=ordered_ids,
            total_components=len(entries),
            critical_count=critical_count,
            high_count=high_count,
        )

    # ------------------------------------------------------------------
    # 10. Cross-region failover orchestration
    # ------------------------------------------------------------------

    def plan_cross_region_failover(
        self,
        failed_region: str = "",
    ) -> CrossRegionFailoverPlan:
        """Plan cross-region failover orchestration.

        Groups components by region, identifies the target region, and
        builds a failover sequence.

        Parameters
        ----------
        failed_region:
            The region that has failed.  If empty, uses the primary region.
        """
        comps = self._components()
        region_map: dict[str, list[str]] = {}

        for cid in sorted(comps.keys()):
            comp = comps[cid]
            region = comp.region.region or "default"
            region_map.setdefault(region, []).append(cid)

        # Determine primary and target
        if not failed_region:
            # Find the region with the most primary components
            primary_candidates: dict[str, int] = {}
            for cid, comp in comps.items():
                r = comp.region.region or "default"
                if comp.region.is_primary:
                    primary_candidates[r] = primary_candidates.get(r, 0) + 1
            if primary_candidates:
                failed_region = max(primary_candidates, key=primary_candidates.get)  # type: ignore[arg-type]
            elif region_map:
                failed_region = sorted(region_map.keys())[0]
            else:
                failed_region = "default"

        # Determine target region
        target_region = ""
        for cid, comp in comps.items():
            if comp.region.dr_target_region:
                target_region = comp.region.dr_target_region
                break

        if not target_region:
            other_regions = [r for r in sorted(region_map.keys()) if r != failed_region]
            target_region = other_regions[0] if other_regions else "dr-" + failed_region

        # Build region states
        regions: list[RegionState] = []
        for region_name in sorted(region_map.keys()):
            cids = region_map[region_name]
            role = RegionRole.PRIMARY if region_name == failed_region else RegionRole.SECONDARY
            is_healthy = region_name != failed_region
            fo_time = sum(self._component_rto(comps[c]) for c in cids)
            regions.append(RegionState(
                region_name=region_name,
                role=role,
                component_ids=cids,
                is_healthy=is_healthy,
                failover_time_seconds=round(fo_time, 2),
            ))

        # Build failover sequence
        ds_ids, app_ids = self._sorted_components_by_type()
        failed_ds = [c for c in ds_ids if comps[c].region.region == failed_region or not comps[c].region.region]
        failed_apps = [c for c in app_ids if comps[c].region.region == failed_region or not comps[c].region.region]
        failover_seq = failed_ds + failed_apps

        # Timing estimates
        data_sync = sum(self._component_rpo(comps[c]) for c in failed_ds) if failed_ds else 0.0
        total_fo = sum(self._component_rto(comps[c]) for c in failover_seq) if failover_seq else 0.0
        dns_prop = 60.0  # default DNS propagation

        recs: list[str] = []
        if not target_region.startswith("dr-"):
            pass  # real target region
        else:
            recs.append(f"No DR target region configured; assumed '{target_region}'")

        for cid in failover_seq:
            comp = comps[cid]
            if not comp.failover.enabled:
                recs.append(f"Enable failover for {cid} to reduce cross-region RTO")
            if self._is_data_store(comp) and not comp.security.backup_enabled:
                recs.append(f"Enable backups for data store {cid}")

        return CrossRegionFailoverPlan(
            regions=regions,
            primary_region=failed_region,
            target_region=target_region,
            failover_sequence=failover_seq,
            total_failover_time_seconds=round(total_fo, 2),
            dns_propagation_seconds=dns_prop,
            data_sync_seconds=round(data_sync, 2),
            recommendations=recs,
        )

    # ------------------------------------------------------------------
    # 11. DR test coverage analysis
    # ------------------------------------------------------------------

    def analyse_test_coverage(
        self,
        tested_scenarios: dict[str, str] | None = None,
    ) -> DRTestCoverageReport:
        """Analyse which DR scenarios have been tested.

        Parameters
        ----------
        tested_scenarios:
            Mapping of scenario name to ISO timestamp of last test.
            If *None*, assumes no scenarios have been tested.
        """
        if tested_scenarios is None:
            tested_scenarios = {}

        comps = self._components()
        ds_ids, app_ids = self._sorted_components_by_type()
        all_ids = sorted(comps.keys())

        # Define standard scenarios
        scenarios: list[TestCoverageEntry] = []

        scenario_defs: list[tuple[str, list[str], str]] = [
            ("single_component_failure", all_ids, "Single component failure and recovery"),
            ("database_failover", ds_ids, "Database failover to DR"),
            ("full_site_failover", all_ids, "Complete site failover"),
            ("network_partition", all_ids, "Network partition between regions"),
            ("data_corruption", ds_ids, "Data corruption and restore"),
            ("cascading_failure", all_ids, "Cascading failure across services"),
            ("dns_failure", all_ids, "DNS resolution failure"),
            ("partial_outage", app_ids, "Partial outage of app services"),
        ]

        untested_critical: list[str] = []
        tested_count = 0

        for name, covered_ids, description in scenario_defs:
            is_tested = name in tested_scenarios
            last_tested = tested_scenarios.get(name, "")
            freq = "quarterly" if is_tested else "never"

            if not covered_ids:
                # Skip scenarios with no applicable components
                continue

            entry = TestCoverageEntry(
                scenario_name=name,
                is_tested=is_tested,
                last_tested_iso=last_tested,
                test_frequency=freq,
                components_covered=list(covered_ids),
                gap_description="" if is_tested else f"Scenario '{name}' has never been tested",
            )
            scenarios.append(entry)
            if is_tested:
                tested_count += 1
            else:
                if name in ("database_failover", "full_site_failover", "data_corruption"):
                    untested_critical.append(name)

        total = len(scenarios)
        coverage = (tested_count / total * 100.0) if total > 0 else 0.0

        return DRTestCoverageReport(
            entries=scenarios,
            total_scenarios=total,
            tested_scenarios=tested_count,
            coverage_percentage=round(coverage, 1),
            untested_critical=untested_critical,
        )

    # ------------------------------------------------------------------
    # 12. Recovery checkpoint validation
    # ------------------------------------------------------------------

    def build_checkpoints(self) -> list[RecoveryCheckpoint]:
        """Build recovery checkpoints for validation during recovery."""
        comps = self._components()
        checkpoints: list[RecoveryCheckpoint] = []
        ds_ids, app_ids = self._sorted_components_by_type()

        # Checkpoint: Disaster confirmed
        checkpoints.append(RecoveryCheckpoint(
            checkpoint_id="cp_detect",
            name="Disaster event confirmed",
            phase=RecoveryPhase.DETECTION,
            validation_command="check_alert_acknowledged",
            expected_result="Alert acknowledged within SLA",
            component_ids=sorted(comps.keys()),
            is_blocking=True,
        ))

        # Checkpoint: Triage complete
        checkpoints.append(RecoveryCheckpoint(
            checkpoint_id="cp_triage",
            name="Triage and blast radius assessed",
            phase=RecoveryPhase.TRIAGE,
            validation_command="verify_triage_report",
            expected_result="Triage report generated",
            component_ids=sorted(comps.keys()),
            is_blocking=True,
        ))

        # Checkpoint: Data stores failed over
        if ds_ids:
            checkpoints.append(RecoveryCheckpoint(
                checkpoint_id="cp_ds_failover",
                name="Data stores failed over",
                phase=RecoveryPhase.FAILOVER,
                validation_command="verify_ds_failover",
                expected_result="All data stores responding in DR",
                component_ids=list(ds_ids),
                is_blocking=True,
            ))

        # Checkpoint: Data validated
        if ds_ids:
            checkpoints.append(RecoveryCheckpoint(
                checkpoint_id="cp_data_valid",
                name="Data consistency validated",
                phase=RecoveryPhase.DATA_VALIDATION,
                validation_command="verify_data_checksums",
                expected_result="Checksums match",
                component_ids=list(ds_ids),
                is_blocking=True,
            ))

        # Checkpoint: Services restored
        if app_ids:
            checkpoints.append(RecoveryCheckpoint(
                checkpoint_id="cp_svc_restored",
                name="Application services restored",
                phase=RecoveryPhase.SERVICE_RESTORATION,
                validation_command="verify_service_health",
                expected_result="All services healthy",
                component_ids=list(app_ids),
                is_blocking=True,
            ))

        # Checkpoint: Health verified (non-blocking)
        checkpoints.append(RecoveryCheckpoint(
            checkpoint_id="cp_health",
            name="Post-recovery health verified",
            phase=RecoveryPhase.HEALTH_CHECK,
            validation_command="run_smoke_tests",
            expected_result="All smoke tests pass",
            component_ids=sorted(comps.keys()),
            is_blocking=False,
        ))

        return checkpoints

    def validate_checkpoints(
        self,
        checkpoints: list[RecoveryCheckpoint] | None = None,
        *,
        failed_checkpoint_ids: list[str] | None = None,
        bypassed_checkpoint_ids: list[str] | None = None,
    ) -> CheckpointValidationResult:
        """Validate recovery checkpoints.

        Parameters
        ----------
        checkpoints:
            Checkpoints to validate.  Defaults to ``build_checkpoints()``.
        failed_checkpoint_ids:
            IDs of checkpoints that failed.
        bypassed_checkpoint_ids:
            IDs of checkpoints that were bypassed.
        """
        if checkpoints is None:
            checkpoints = self.build_checkpoints()
        if failed_checkpoint_ids is None:
            failed_checkpoint_ids = []
        if bypassed_checkpoint_ids is None:
            bypassed_checkpoint_ids = []

        passed = 0
        failed = 0
        blocking_failures = 0

        for cp in checkpoints:
            if cp.checkpoint_id in failed_checkpoint_ids:
                cp.status = CheckpointStatus.FAILED
                failed += 1
                if cp.is_blocking:
                    blocking_failures += 1
            elif cp.checkpoint_id in bypassed_checkpoint_ids:
                cp.status = CheckpointStatus.BYPASSED
                passed += 1  # bypassed counts as passed for proceed check
            else:
                cp.status = CheckpointStatus.PASSED
                passed += 1

        can_proceed = blocking_failures == 0

        return CheckpointValidationResult(
            checkpoints=checkpoints,
            total_checkpoints=len(checkpoints),
            passed_checkpoints=passed,
            failed_checkpoints=failed,
            blocking_failures=blocking_failures,
            can_proceed=can_proceed,
        )

    # ------------------------------------------------------------------
    # 13. Post-recovery health verification planning
    # ------------------------------------------------------------------

    def plan_post_recovery_health(self) -> PostRecoveryHealthPlan:
        """Generate a post-recovery health verification plan.

        Creates health checks for every component covering connectivity,
        performance, and data integrity.
        """
        comps = self._components()
        checks: list[HealthCheckEntry] = []

        for cid in sorted(comps.keys()):
            comp = comps[cid]

            # Connectivity check
            checks.append(HealthCheckEntry(
                component_id=cid,
                check_name=f"{cid}_connectivity",
                result=HealthCheckResult.UNKNOWN,
                details=f"Verify {cid} is reachable",
                is_critical=True,
                verification_command=f"curl -sf http://{cid}:8080/health",
            ))

            # Performance check
            checks.append(HealthCheckEntry(
                component_id=cid,
                check_name=f"{cid}_performance",
                result=HealthCheckResult.UNKNOWN,
                details=f"Verify {cid} response time within SLA",
                is_critical=False,
                verification_command=f"check_latency {cid} --threshold 500ms",
            ))

            # Data integrity check for data stores
            if self._is_data_store(comp):
                checks.append(HealthCheckEntry(
                    component_id=cid,
                    check_name=f"{cid}_data_integrity",
                    result=HealthCheckResult.UNKNOWN,
                    details=f"Verify data integrity for {cid}",
                    is_critical=True,
                    verification_command=f"verify_checksums {cid}",
                ))

            # Replication check if failover is enabled
            if comp.failover.enabled:
                checks.append(HealthCheckEntry(
                    component_id=cid,
                    check_name=f"{cid}_replication",
                    result=HealthCheckResult.UNKNOWN,
                    details=f"Verify replication lag for {cid}",
                    is_critical=self._is_data_store(comp),
                    verification_command=f"check_replication_lag {cid}",
                ))

        total = len(checks)
        critical = sum(1 for c in checks if c.is_critical)
        # Estimate 15s per check
        est_time = total * 15.0

        phases = sorted({RecoveryPhase.HEALTH_CHECK.value, RecoveryPhase.POST_RECOVERY.value})

        return PostRecoveryHealthPlan(
            checks=checks,
            total_checks=total,
            critical_checks=critical,
            estimated_verification_time_seconds=est_time,
            phases=phases,
        )

    # ------------------------------------------------------------------
    # Full orchestration run
    # ------------------------------------------------------------------

    def run_full_orchestration(
        self,
        *,
        failure_step_ids: list[str] | None = None,
        failed_checkpoint_ids: list[str] | None = None,
        tested_scenarios: dict[str, str] | None = None,
        failed_region: str = "",
    ) -> dict:
        """Run the full DR orchestration pipeline and return all results.

        This is a convenience method that calls all analysis methods and
        returns a dict with all outputs.
        """
        steps = self.build_recovery_steps()
        dep_graph = self.resolve_dependencies(steps)
        optimised = self.optimise_parallelism(list(steps))
        critical_path = self.estimate_critical_path(list(steps))
        drill = self.simulate_drill(
            list(steps), failure_step_ids=failure_step_ids,
        )
        failover_plan = self.plan_failover_failback()
        data_consistency = self.validate_data_consistency()
        comm_plan = self.generate_communication_plan()
        automation_gaps = self.detect_automation_gaps(list(steps))
        priorities = self.score_recovery_priorities()
        cross_region = self.plan_cross_region_failover(failed_region=failed_region)
        test_coverage = self.analyse_test_coverage(tested_scenarios=tested_scenarios)
        checkpoints = self.build_checkpoints()
        checkpoint_result = self.validate_checkpoints(
            checkpoints, failed_checkpoint_ids=failed_checkpoint_ids,
        )
        health_plan = self.plan_post_recovery_health()

        return {
            "steps": steps,
            "dependency_graph": dep_graph,
            "optimised_graph": optimised,
            "critical_path": critical_path,
            "drill_simulation": drill,
            "failover_plan": failover_plan,
            "data_consistency": data_consistency,
            "communication_plan": comm_plan,
            "automation_gaps": automation_gaps,
            "recovery_priorities": priorities,
            "cross_region_failover": cross_region,
            "test_coverage": test_coverage,
            "checkpoints": checkpoint_result,
            "health_plan": health_plan,
            "generated_at": self._now_iso(),
        }
