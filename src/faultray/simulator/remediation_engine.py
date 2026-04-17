# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Autonomous remediation engine — detect, plan, and execute fixes.

Automatically identifies infrastructure issues and generates executable
remediation plans. Supports dry-run mode for safety, approval gates,
and rollback planning.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from faultray.model.components import Component, ComponentType, HealthStatus
from faultray.model.graph import InfraGraph


class RemediationAction(str, Enum):
    """Types of remediation actions."""

    SCALE_UP = "scale_up"
    SCALE_DOWN = "scale_down"
    ENABLE_FAILOVER = "enable_failover"
    ENABLE_CIRCUIT_BREAKER = "enable_circuit_breaker"
    INCREASE_TIMEOUT = "increase_timeout"
    ADD_REPLICA = "add_replica"
    REMOVE_REPLICA = "remove_replica"
    ENABLE_AUTOSCALING = "enable_autoscaling"
    ENABLE_RATE_LIMITING = "enable_rate_limiting"
    ENABLE_BACKUP = "enable_backup"
    ENABLE_ENCRYPTION = "enable_encryption"
    RESTART_COMPONENT = "restart_component"
    DRAIN_AND_REPLACE = "drain_and_replace"
    REBALANCE_LOAD = "rebalance_load"
    QUARANTINE = "quarantine"


class RemediationPriority(str, Enum):
    IMMEDIATE = "immediate"  # Execute now (P0)
    URGENT = "urgent"  # Within 1 hour (P1)
    PLANNED = "planned"  # Next maintenance window (P2)
    ADVISORY = "advisory"  # Recommendation only (P3)


class ExecutionStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    SKIPPED = "skipped"


@dataclass
class RemediationStep:
    """A single step in a remediation plan."""

    step_number: int
    action: RemediationAction
    component_id: str
    component_name: str
    description: str
    parameters: dict  # Action-specific params (e.g., {"target_replicas": 3})
    estimated_impact: str
    rollback_action: str
    risk_level: str  # "low", "medium", "high"
    execution_status: ExecutionStatus = ExecutionStatus.PENDING
    execution_result: str = ""


@dataclass
class RemediationPlan:
    """A complete remediation plan for an issue."""

    plan_id: str
    issue_description: str
    priority: RemediationPriority
    steps: list[RemediationStep]
    estimated_duration_minutes: int
    requires_approval: bool
    rollback_plan: list[str]
    affected_components: list[str]
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class RemediationReport:
    """Full remediation analysis report."""

    plans: list[RemediationPlan]
    total_issues_found: int
    auto_remediable_count: int
    manual_required_count: int
    estimated_total_duration_minutes: int
    risk_summary: str
    execution_log: list[str]


class RemediationEngine:
    """Autonomous remediation engine for infrastructure issues."""

    # Thresholds for triggering remediation
    CPU_CRITICAL = 90.0
    CPU_HIGH = 75.0
    MEMORY_CRITICAL = 90.0
    MEMORY_HIGH = 80.0
    DISK_CRITICAL = 90.0
    DISK_HIGH = 75.0
    CONNECTION_CRITICAL = 0.9  # 90% of max
    CONNECTION_HIGH = 0.7

    def __init__(self, graph: InfraGraph, dry_run: bool = True) -> None:
        self._graph = graph
        self._dry_run = dry_run
        self._execution_log: list[str] = []
        self._plan_counter = 0

    def analyze_and_plan(self) -> RemediationReport:
        """Analyze infrastructure and generate remediation plans."""
        plans: list[RemediationPlan] = []

        for comp in self._graph.components.values():
            comp_plans = self._analyze_component(comp)
            plans.extend(comp_plans)

        # Add topology-level plans
        plans.extend(self._analyze_topology())

        # Sort by priority
        priority_order = {
            RemediationPriority.IMMEDIATE: 0,
            RemediationPriority.URGENT: 1,
            RemediationPriority.PLANNED: 2,
            RemediationPriority.ADVISORY: 3,
        }
        plans.sort(key=lambda p: priority_order.get(p.priority, 99))

        auto_count = sum(1 for p in plans if not p.requires_approval)
        manual_count = sum(1 for p in plans if p.requires_approval)
        total_duration = sum(p.estimated_duration_minutes for p in plans)

        risk_summary = self._build_risk_summary(plans)

        return RemediationReport(
            plans=plans,
            total_issues_found=len(plans),
            auto_remediable_count=auto_count,
            manual_required_count=manual_count,
            estimated_total_duration_minutes=total_duration,
            risk_summary=risk_summary,
            execution_log=list(self._execution_log),
        )

    def execute_plan(self, plan: RemediationPlan) -> RemediationPlan:
        """Execute a remediation plan (dry-run or actual).

        Returns the plan with updated execution statuses.
        """
        if plan.requires_approval:
            # In dry_run, mark as skipped
            for step in plan.steps:
                if step.execution_status == ExecutionStatus.PENDING:
                    step.execution_status = ExecutionStatus.SKIPPED
                    step.execution_result = "Requires manual approval"
            self._execution_log.append(
                f"Plan {plan.plan_id}: Skipped (requires approval)"
            )
            return plan

        for step in plan.steps:
            step.execution_status = ExecutionStatus.IN_PROGRESS
            try:
                result = self._execute_step(step)
                step.execution_status = ExecutionStatus.COMPLETED
                step.execution_result = result
                self._execution_log.append(
                    f"Plan {plan.plan_id} Step {step.step_number}: "
                    f"{step.action.value} → {result}"
                )
            except Exception as e:
                step.execution_status = ExecutionStatus.FAILED
                step.execution_result = str(e)
                self._execution_log.append(
                    f"Plan {plan.plan_id} Step {step.step_number}: "
                    f"FAILED → {e}"
                )
                # Rollback remaining
                self._rollback_plan(plan, step.step_number)
                break

        return plan

    def execute_all(self, report: RemediationReport) -> RemediationReport:
        """Execute all plans in the report."""
        for plan in report.plans:
            self.execute_plan(plan)
        report.execution_log = list(self._execution_log)
        return report

    # ------------------------------------------------------------------
    # Component-level analysis
    # ------------------------------------------------------------------

    def _analyze_component(self, comp: Component) -> list[RemediationPlan]:
        """Analyze a single component and generate plans."""
        plans: list[RemediationPlan] = []

        # Check health status
        if comp.health == HealthStatus.DOWN:
            plans.append(self._plan_restart_or_replace(comp))
        elif comp.health == HealthStatus.OVERLOADED:
            plans.append(self._plan_scale_up(comp))

        # Check CPU
        if comp.metrics.cpu_percent >= self.CPU_CRITICAL:
            plans.append(self._plan_cpu_remediation(comp, "critical"))
        elif comp.metrics.cpu_percent >= self.CPU_HIGH:
            plans.append(self._plan_cpu_remediation(comp, "high"))

        # Check Memory
        if comp.metrics.memory_percent >= self.MEMORY_CRITICAL:
            plans.append(self._plan_memory_remediation(comp, "critical"))
        elif comp.metrics.memory_percent >= self.MEMORY_HIGH:
            plans.append(self._plan_memory_remediation(comp, "high"))

        # Check Disk
        if comp.metrics.disk_percent >= self.DISK_CRITICAL:
            plans.append(self._plan_disk_remediation(comp, "critical"))
        elif comp.metrics.disk_percent >= self.DISK_HIGH:
            plans.append(self._plan_disk_remediation(comp, "high"))

        # Check connections
        if comp.capacity.max_connections > 0:
            ratio = (
                comp.metrics.network_connections
                / comp.capacity.max_connections
            )
            if ratio >= self.CONNECTION_CRITICAL:
                plans.append(
                    self._plan_connection_remediation(comp, "critical")
                )
            elif ratio >= self.CONNECTION_HIGH:
                plans.append(
                    self._plan_connection_remediation(comp, "high")
                )

        # Security checks
        if not comp.security.encryption_at_rest and comp.type in (
            ComponentType.DATABASE,
            ComponentType.STORAGE,
        ):
            plans.append(
                self._plan_security_remediation(comp, "encryption")
            )

        if not comp.security.backup_enabled and comp.type in (
            ComponentType.DATABASE,
            ComponentType.STORAGE,
        ):
            plans.append(self._plan_security_remediation(comp, "backup"))

        # HA checks
        if comp.replicas <= 1 and not comp.failover.enabled:
            dependents = self._graph.get_dependents(comp.id)
            if dependents:
                plans.append(
                    self._plan_ha_remediation(comp, len(dependents))
                )

        return plans

    # ------------------------------------------------------------------
    # Topology-level analysis
    # ------------------------------------------------------------------

    def _analyze_topology(self) -> list[RemediationPlan]:
        """Analyze infrastructure topology for systemic issues."""
        plans: list[RemediationPlan] = []

        # Check for SPOF chains
        for comp in self._graph.components.values():
            deps = self._graph.get_dependencies(comp.id)
            single_deps = [
                d
                for d in deps
                if d.replicas <= 1 and not d.failover.enabled
            ]
            if len(single_deps) >= 2:
                self._plan_counter += 1
                steps = []
                for i, dep in enumerate(single_deps, 1):
                    steps.append(
                        RemediationStep(
                            step_number=i,
                            action=RemediationAction.ADD_REPLICA,
                            component_id=dep.id,
                            component_name=dep.name,
                            description=(
                                f"Add replica to {dep.name} to eliminate "
                                f"SPOF chain"
                            ),
                            parameters={"target_replicas": 2},
                            estimated_impact=(
                                "Eliminates single point of failure"
                            ),
                            rollback_action=(
                                f"Remove added replica from {dep.name}"
                            ),
                            risk_level="low",
                        )
                    )
                plans.append(
                    RemediationPlan(
                        plan_id=f"TOPO-{self._plan_counter:03d}",
                        issue_description=(
                            f"{comp.name} depends on "
                            f"{len(single_deps)} SPOFs: "
                            f"{', '.join(d.name for d in single_deps)}"
                        ),
                        priority=RemediationPriority.URGENT,
                        steps=steps,
                        estimated_duration_minutes=15 * len(single_deps),
                        requires_approval=True,
                        rollback_plan=[
                            f"Remove replica from {d.name}"
                            for d in single_deps
                        ],
                        affected_components=[comp.id]
                        + [d.id for d in single_deps],
                    )
                )

        # Check for autoscaling gaps
        overloaded_no_autoscale = [
            c
            for c in self._graph.components.values()
            if c.metrics.cpu_percent > 60 and not c.autoscaling.enabled
        ]
        if overloaded_no_autoscale:
            self._plan_counter += 1
            steps = []
            for i, c in enumerate(overloaded_no_autoscale, 1):
                steps.append(
                    RemediationStep(
                        step_number=i,
                        action=RemediationAction.ENABLE_AUTOSCALING,
                        component_id=c.id,
                        component_name=c.name,
                        description=(
                            f"Enable autoscaling for {c.name} "
                            f"(CPU: {c.metrics.cpu_percent}%)"
                        ),
                        parameters={
                            "min_replicas": c.replicas,
                            "max_replicas": c.replicas * 3,
                            "target_cpu": 70,
                        },
                        estimated_impact=(
                            "Automatic scaling based on CPU utilization"
                        ),
                        rollback_action=(
                            f"Disable autoscaling for {c.name}"
                        ),
                        risk_level="low",
                    )
                )
            plans.append(
                RemediationPlan(
                    plan_id=f"TOPO-{self._plan_counter:03d}",
                    issue_description=(
                        f"{len(overloaded_no_autoscale)} components "
                        f"under load without autoscaling"
                    ),
                    priority=RemediationPriority.PLANNED,
                    steps=steps,
                    estimated_duration_minutes=(
                        10 * len(overloaded_no_autoscale)
                    ),
                    requires_approval=False,
                    rollback_plan=[
                        f"Disable autoscaling for {c.name}"
                        for c in overloaded_no_autoscale
                    ],
                    affected_components=[
                        c.id for c in overloaded_no_autoscale
                    ],
                )
            )

        return plans

    # ------------------------------------------------------------------
    # Plan builders
    # ------------------------------------------------------------------

    def _plan_restart_or_replace(
        self, comp: Component
    ) -> RemediationPlan:
        self._plan_counter += 1
        return RemediationPlan(
            plan_id=f"REM-{self._plan_counter:03d}",
            issue_description=(
                f"{comp.name} is DOWN — requires restart or replacement"
            ),
            priority=RemediationPriority.IMMEDIATE,
            steps=[
                RemediationStep(
                    step_number=1,
                    action=RemediationAction.RESTART_COMPONENT,
                    component_id=comp.id,
                    component_name=comp.name,
                    description=(
                        f"Attempt graceful restart of {comp.name}"
                    ),
                    parameters={"grace_period_seconds": 30},
                    estimated_impact=(
                        "Brief additional downtime during restart"
                    ),
                    rollback_action="Escalate to drain and replace",
                    risk_level="medium",
                ),
                RemediationStep(
                    step_number=2,
                    action=RemediationAction.DRAIN_AND_REPLACE,
                    component_id=comp.id,
                    component_name=comp.name,
                    description=(
                        f"If restart fails, drain and replace "
                        f"{comp.name}"
                    ),
                    parameters={"drain_timeout_seconds": 60},
                    estimated_impact="New instance provisioned",
                    rollback_action="Restore from backup",
                    risk_level="high",
                ),
            ],
            estimated_duration_minutes=15,
            requires_approval=False,
            rollback_plan=[
                "Restore from latest backup",
                "Failover to standby",
            ],
            affected_components=[comp.id],
        )

    def _plan_scale_up(self, comp: Component) -> RemediationPlan:
        self._plan_counter += 1
        target = max(comp.replicas + 1, comp.replicas * 2)
        return RemediationPlan(
            plan_id=f"REM-{self._plan_counter:03d}",
            issue_description=(
                f"{comp.name} is OVERLOADED — scale up required"
            ),
            priority=RemediationPriority.IMMEDIATE,
            steps=[
                RemediationStep(
                    step_number=1,
                    action=RemediationAction.SCALE_UP,
                    component_id=comp.id,
                    component_name=comp.name,
                    description=(
                        f"Scale {comp.name} from {comp.replicas} "
                        f"to {target} replicas"
                    ),
                    parameters={
                        "current_replicas": comp.replicas,
                        "target_replicas": target,
                    },
                    estimated_impact="Reduced load per instance",
                    rollback_action=(
                        f"Scale back to {comp.replicas} replicas"
                    ),
                    risk_level="low",
                ),
            ],
            estimated_duration_minutes=5,
            requires_approval=False,
            rollback_plan=[
                f"Scale back to {comp.replicas} replicas"
            ],
            affected_components=[comp.id],
        )

    def _plan_cpu_remediation(
        self, comp: Component, severity: str
    ) -> RemediationPlan:
        self._plan_counter += 1
        priority = (
            RemediationPriority.IMMEDIATE
            if severity == "critical"
            else RemediationPriority.URGENT
        )
        target = comp.replicas + (2 if severity == "critical" else 1)
        steps = [
            RemediationStep(
                step_number=1,
                action=RemediationAction.ADD_REPLICA,
                component_id=comp.id,
                component_name=comp.name,
                description=(
                    f"Add replicas to distribute CPU load "
                    f"(current: {comp.metrics.cpu_percent}%)"
                ),
                parameters={
                    "current_replicas": comp.replicas,
                    "target_replicas": target,
                },
                estimated_impact=(
                    f"CPU per instance reduced to "
                    f"~{comp.metrics.cpu_percent * comp.replicas / target:.0f}%"
                ),
                rollback_action="Remove added replicas",
                risk_level="low",
            ),
        ]
        if not comp.autoscaling.enabled:
            steps.append(
                RemediationStep(
                    step_number=2,
                    action=RemediationAction.ENABLE_AUTOSCALING,
                    component_id=comp.id,
                    component_name=comp.name,
                    description=(
                        "Enable autoscaling to prevent future CPU issues"
                    ),
                    parameters={
                        "min_replicas": comp.replicas,
                        "max_replicas": target * 2,
                        "target_cpu": 70,
                    },
                    estimated_impact="Automatic future scaling",
                    rollback_action="Disable autoscaling",
                    risk_level="low",
                )
            )
        return RemediationPlan(
            plan_id=f"REM-{self._plan_counter:03d}",
            issue_description=(
                f"{comp.name} CPU at {comp.metrics.cpu_percent}% "
                f"({severity})"
            ),
            priority=priority,
            steps=steps,
            estimated_duration_minutes=10,
            requires_approval=severity != "critical",
            rollback_plan=[
                f"Scale back to {comp.replicas} replicas"
            ],
            affected_components=[comp.id],
        )

    def _plan_memory_remediation(
        self, comp: Component, severity: str
    ) -> RemediationPlan:
        self._plan_counter += 1
        priority = (
            RemediationPriority.IMMEDIATE
            if severity == "critical"
            else RemediationPriority.URGENT
        )
        return RemediationPlan(
            plan_id=f"REM-{self._plan_counter:03d}",
            issue_description=(
                f"{comp.name} memory at "
                f"{comp.metrics.memory_percent}% ({severity})"
            ),
            priority=priority,
            steps=[
                RemediationStep(
                    step_number=1,
                    action=RemediationAction.RESTART_COMPONENT,
                    component_id=comp.id,
                    component_name=comp.name,
                    description=(
                        f"Restart {comp.name} to free leaked memory"
                    ),
                    parameters={"grace_period_seconds": 30},
                    estimated_impact=(
                        "Temporary service interruption, memory freed"
                    ),
                    rollback_action="No rollback needed for restart",
                    risk_level=(
                        "medium" if severity == "critical" else "low"
                    ),
                ),
                RemediationStep(
                    step_number=2,
                    action=RemediationAction.ADD_REPLICA,
                    component_id=comp.id,
                    component_name=comp.name,
                    description=(
                        "Add replica to handle load during memory "
                        "investigation"
                    ),
                    parameters={"target_replicas": comp.replicas + 1},
                    estimated_impact=(
                        "Load distributed across more instances"
                    ),
                    rollback_action="Remove added replica",
                    risk_level="low",
                ),
            ],
            estimated_duration_minutes=15,
            requires_approval=severity != "critical",
            rollback_plan=[
                "Remove added replicas",
                "Revert memory settings",
            ],
            affected_components=[comp.id],
        )

    def _plan_disk_remediation(
        self, comp: Component, severity: str
    ) -> RemediationPlan:
        self._plan_counter += 1
        priority = (
            RemediationPriority.IMMEDIATE
            if severity == "critical"
            else RemediationPriority.PLANNED
        )
        return RemediationPlan(
            plan_id=f"REM-{self._plan_counter:03d}",
            issue_description=(
                f"{comp.name} disk at {comp.metrics.disk_percent}% "
                f"({severity})"
            ),
            priority=priority,
            steps=[
                RemediationStep(
                    step_number=1,
                    action=RemediationAction.SCALE_UP,
                    component_id=comp.id,
                    component_name=comp.name,
                    description=(
                        f"Expand disk storage for {comp.name}"
                    ),
                    parameters={
                        "current_disk_percent": comp.metrics.disk_percent,
                        "action": "expand_volume",
                    },
                    estimated_impact="More storage available",
                    rollback_action=(
                        "Shrink volume (data migration required)"
                    ),
                    risk_level="medium",
                ),
            ],
            estimated_duration_minutes=(
                30 if severity == "critical" else 60
            ),
            requires_approval=True,
            rollback_plan=[
                "Shrink volume after data migration"
            ],
            affected_components=[comp.id],
        )

    def _plan_connection_remediation(
        self, comp: Component, severity: str
    ) -> RemediationPlan:
        self._plan_counter += 1
        ratio = (
            comp.metrics.network_connections
            / comp.capacity.max_connections
            if comp.capacity.max_connections > 0
            else 0
        )
        priority = (
            RemediationPriority.URGENT
            if severity == "critical"
            else RemediationPriority.PLANNED
        )
        steps = [
            RemediationStep(
                step_number=1,
                action=RemediationAction.ENABLE_RATE_LIMITING,
                component_id=comp.id,
                component_name=comp.name,
                description=(
                    f"Enable rate limiting to control connection "
                    f"growth ({ratio * 100:.0f}% capacity)"
                ),
                parameters={
                    "max_connections": comp.capacity.max_connections,
                    "rate_limit_rps": 100,
                },
                estimated_impact="New connections throttled",
                rollback_action="Disable rate limiting",
                risk_level="low",
            ),
        ]
        if severity == "critical":
            steps.append(
                RemediationStep(
                    step_number=2,
                    action=RemediationAction.ADD_REPLICA,
                    component_id=comp.id,
                    component_name=comp.name,
                    description=(
                        "Add replica to distribute connections"
                    ),
                    parameters={
                        "target_replicas": comp.replicas + 1,
                    },
                    estimated_impact=(
                        "Connections distributed across instances"
                    ),
                    rollback_action="Remove added replica",
                    risk_level="low",
                )
            )
        return RemediationPlan(
            plan_id=f"REM-{self._plan_counter:03d}",
            issue_description=(
                f"{comp.name} connections at {ratio * 100:.0f}% "
                f"of max ({severity})"
            ),
            priority=priority,
            steps=steps,
            estimated_duration_minutes=10,
            requires_approval=False,
            rollback_plan=[
                "Disable rate limiting",
                "Remove added replicas",
            ],
            affected_components=[comp.id],
        )

    def _plan_security_remediation(
        self, comp: Component, issue_type: str
    ) -> RemediationPlan:
        self._plan_counter += 1
        if issue_type == "encryption":
            return RemediationPlan(
                plan_id=f"SEC-{self._plan_counter:03d}",
                issue_description=(
                    f"{comp.name}: encryption at rest not enabled"
                ),
                priority=RemediationPriority.PLANNED,
                steps=[
                    RemediationStep(
                        step_number=1,
                        action=RemediationAction.ENABLE_ENCRYPTION,
                        component_id=comp.id,
                        component_name=comp.name,
                        description=(
                            f"Enable encryption at rest for {comp.name}"
                        ),
                        parameters={
                            "algorithm": "AES-256",
                            "key_management": "AWS_KMS",
                        },
                        estimated_impact=(
                            "Data encrypted at rest — slight I/O overhead"
                        ),
                        rollback_action=(
                            "Disable encryption (not recommended)"
                        ),
                        risk_level="low",
                    )
                ],
                estimated_duration_minutes=30,
                requires_approval=True,
                rollback_plan=[
                    "Disable encryption (data migration may be required)"
                ],
                affected_components=[comp.id],
            )
        else:  # backup
            return RemediationPlan(
                plan_id=f"SEC-{self._plan_counter:03d}",
                issue_description=(
                    f"{comp.name}: automated backup not configured"
                ),
                priority=RemediationPriority.PLANNED,
                steps=[
                    RemediationStep(
                        step_number=1,
                        action=RemediationAction.ENABLE_BACKUP,
                        component_id=comp.id,
                        component_name=comp.name,
                        description=(
                            f"Enable automated daily backups for "
                            f"{comp.name}"
                        ),
                        parameters={
                            "frequency": "daily",
                            "retention_days": 30,
                            "type": "incremental",
                        },
                        estimated_impact=(
                            "Automated backup with 30-day retention"
                        ),
                        rollback_action="Disable automated backups",
                        risk_level="low",
                    )
                ],
                estimated_duration_minutes=15,
                requires_approval=False,
                rollback_plan=["Disable automated backups"],
                affected_components=[comp.id],
            )

    def _plan_ha_remediation(
        self, comp: Component, dependent_count: int
    ) -> RemediationPlan:
        self._plan_counter += 1
        priority = (
            RemediationPriority.URGENT
            if dependent_count > 2
            else RemediationPriority.PLANNED
        )
        return RemediationPlan(
            plan_id=f"HA-{self._plan_counter:03d}",
            issue_description=(
                f"{comp.name}: single replica, no failover, "
                f"{dependent_count} dependents"
            ),
            priority=priority,
            steps=[
                RemediationStep(
                    step_number=1,
                    action=RemediationAction.ADD_REPLICA,
                    component_id=comp.id,
                    component_name=comp.name,
                    description=f"Add replica to {comp.name}",
                    parameters={"target_replicas": 2},
                    estimated_impact=(
                        "High availability — no single point of failure"
                    ),
                    rollback_action="Remove added replica",
                    risk_level="low",
                ),
                RemediationStep(
                    step_number=2,
                    action=RemediationAction.ENABLE_FAILOVER,
                    component_id=comp.id,
                    component_name=comp.name,
                    description=(
                        f"Enable automatic failover for {comp.name}"
                    ),
                    parameters={"promotion_time_seconds": 30},
                    estimated_impact="Automatic recovery on failure",
                    rollback_action="Disable failover",
                    risk_level="low",
                ),
            ],
            estimated_duration_minutes=20,
            requires_approval=dependent_count <= 2,
            rollback_plan=["Remove replica", "Disable failover"],
            affected_components=[comp.id],
        )

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def _execute_step(self, step: RemediationStep) -> str:
        """Execute a single remediation step."""
        comp = self._graph.get_component(step.component_id)
        if not comp:
            raise ValueError(
                f"Component {step.component_id} not found"
            )

        if self._dry_run:
            return (
                f"DRY-RUN: Would {step.action.value} on "
                f"{step.component_name}"
            )

        # Actual execution (modifies the graph in-place)
        action = step.action

        if action in (
            RemediationAction.ADD_REPLICA,
            RemediationAction.SCALE_UP,
        ):
            target = step.parameters.get(
                "target_replicas", comp.replicas + 1
            )
            comp.replicas = target
            return f"Scaled {comp.name} to {target} replicas"

        if action in (
            RemediationAction.REMOVE_REPLICA,
            RemediationAction.SCALE_DOWN,
        ):
            target = step.parameters.get(
                "target_replicas", max(1, comp.replicas - 1)
            )
            comp.replicas = target
            return f"Scaled {comp.name} down to {target} replicas"

        if action == RemediationAction.ENABLE_FAILOVER:
            comp.failover.enabled = True
            promo = step.parameters.get("promotion_time_seconds", 30)
            comp.failover.promotion_time_seconds = promo
            return (
                f"Enabled failover for {comp.name} "
                f"(promotion: {promo}s)"
            )

        if action == RemediationAction.ENABLE_AUTOSCALING:
            comp.autoscaling.enabled = True
            comp.autoscaling.min_replicas = step.parameters.get(
                "min_replicas", 1
            )
            comp.autoscaling.max_replicas = step.parameters.get(
                "max_replicas", 10
            )
            return f"Enabled autoscaling for {comp.name}"

        if action == RemediationAction.ENABLE_BACKUP:
            comp.security.backup_enabled = True
            return f"Enabled automated backup for {comp.name}"

        if action == RemediationAction.ENABLE_ENCRYPTION:
            comp.security.encryption_at_rest = True
            return f"Enabled encryption at rest for {comp.name}"

        if action == RemediationAction.RESTART_COMPONENT:
            # Simulate restart — health resets to HEALTHY
            comp.health = HealthStatus.HEALTHY
            return (
                f"Restarted {comp.name} — health reset to HEALTHY"
            )

        if action == RemediationAction.ENABLE_RATE_LIMITING:
            return f"Rate limiting configured for {comp.name}"

        if action == RemediationAction.ENABLE_CIRCUIT_BREAKER:
            return f"Circuit breaker enabled for {comp.name}"

        if action == RemediationAction.DRAIN_AND_REPLACE:
            comp.health = HealthStatus.HEALTHY
            return f"Drained and replaced {comp.name}"

        if action == RemediationAction.REBALANCE_LOAD:
            return (
                f"Rebalanced load across {comp.name} instances"
            )

        if action == RemediationAction.QUARANTINE:
            comp.health = HealthStatus.DOWN
            return f"Quarantined {comp.name}"

        if action == RemediationAction.INCREASE_TIMEOUT:
            current = comp.capacity.timeout_seconds
            new_timeout = step.parameters.get(
                "timeout_seconds", current * 2
            )
            comp.capacity.timeout_seconds = new_timeout
            return (
                f"Increased timeout for {comp.name} "
                f"to {new_timeout}s"
            )

        return f"Unknown action: {step.action.value}"

    def _rollback_plan(
        self, plan: RemediationPlan, failed_step: int
    ) -> None:
        """Rollback completed steps when a later step fails."""
        for step in reversed(plan.steps):
            if (
                step.step_number < failed_step
                and step.execution_status == ExecutionStatus.COMPLETED
            ):
                step.execution_status = ExecutionStatus.ROLLED_BACK
                step.execution_result += " [ROLLED BACK]"
                self._execution_log.append(
                    f"Plan {plan.plan_id} Step {step.step_number}: "
                    f"Rolled back"
                )

    @staticmethod
    def _build_risk_summary(plans: list[RemediationPlan]) -> str:
        """Build a human-readable risk summary."""
        if not plans:
            return (
                "No remediation needed — infrastructure is healthy."
            )

        immediate = sum(
            1
            for p in plans
            if p.priority == RemediationPriority.IMMEDIATE
        )
        urgent = sum(
            1
            for p in plans
            if p.priority == RemediationPriority.URGENT
        )
        planned = sum(
            1
            for p in plans
            if p.priority == RemediationPriority.PLANNED
        )
        advisory = sum(
            1
            for p in plans
            if p.priority == RemediationPriority.ADVISORY
        )

        parts: list[str] = []
        if immediate:
            parts.append(f"{immediate} IMMEDIATE (P0)")
        if urgent:
            parts.append(f"{urgent} URGENT (P1)")
        if planned:
            parts.append(f"{planned} PLANNED (P2)")
        if advisory:
            parts.append(f"{advisory} ADVISORY (P3)")

        return f"{len(plans)} issues found: {', '.join(parts)}."
