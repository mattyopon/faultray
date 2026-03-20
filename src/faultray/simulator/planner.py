# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Remediation Planner - generates phased improvement plans with timeline, team, and ROI.

Analyzes the current infrastructure state using resilience_score_v2(), security
resilience scoring, and compliance checks to produce actionable PlanTask items
grouped into prioritized phases.  Each task includes team requirements, cost
estimates, and projected resilience score improvement.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from faultray.model.components import ComponentType
from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Estimation table: maps remediation action to role, hours, and monthly cost
# ---------------------------------------------------------------------------

TASK_ESTIMATES: dict[str, dict] = {
    "add_replica": {"role": "DBA", "hours": 8, "monthly_cost": 800, "one_time": 0},
    "enable_autoscaling": {"role": "SRE", "hours": 4, "monthly_cost": 0, "one_time": 0},
    "add_waf": {"role": "Security", "hours": 16, "monthly_cost": 500, "one_time": 0},
    "enable_encryption": {"role": "SRE", "hours": 8, "monthly_cost": 0, "one_time": 0},
    "setup_dr": {"role": "SRE", "hours": 40, "monthly_cost": 3000, "one_time": 0},
    "add_monitoring": {"role": "SRE", "hours": 8, "monthly_cost": 200, "one_time": 0},
    "network_segmentation": {"role": "Infrastructure", "hours": 16, "monthly_cost": 0, "one_time": 0},
    "add_backup": {"role": "DBA", "hours": 8, "monthly_cost": 200, "one_time": 0},
    "add_circuit_breaker": {"role": "SRE", "hours": 4, "monthly_cost": 0, "one_time": 0},
    "add_failover": {"role": "DBA", "hours": 12, "monthly_cost": 400, "one_time": 0},
}

# Default labor cost per hour for one-time cost estimation
_LABOR_COST_PER_HOUR = 150.0

# Category mapping for remediation actions
_ACTION_CATEGORY: dict[str, str] = {
    "add_replica": "redundancy",
    "enable_autoscaling": "redundancy",
    "add_waf": "security",
    "enable_encryption": "security",
    "setup_dr": "dr",
    "add_monitoring": "monitoring",
    "network_segmentation": "security",
    "add_backup": "dr",
    "add_circuit_breaker": "redundancy",
    "add_failover": "redundancy",
}

# Phase assignment: phase 1 = critical reliability, phase 2 = security, phase 3 = DR/compliance
_ACTION_PHASE: dict[str, int] = {
    "add_replica": 1,
    "enable_autoscaling": 1,
    "add_circuit_breaker": 1,
    "add_failover": 1,
    "add_waf": 2,
    "enable_encryption": 2,
    "network_segmentation": 2,
    "add_monitoring": 2,
    "setup_dr": 3,
    "add_backup": 3,
}

# Priority mapping based on action type
_ACTION_PRIORITY: dict[str, str] = {
    "add_replica": "critical",
    "add_failover": "critical",
    "add_circuit_breaker": "high",
    "enable_autoscaling": "high",
    "add_waf": "high",
    "enable_encryption": "medium",
    "network_segmentation": "medium",
    "add_monitoring": "medium",
    "setup_dr": "medium",
    "add_backup": "medium",
}

# Estimated annual risk reduction per action type (in $)
_ACTION_RISK_REDUCTION: dict[str, float] = {
    "add_replica": 50000.0,
    "add_failover": 40000.0,
    "add_circuit_breaker": 15000.0,
    "enable_autoscaling": 20000.0,
    "add_waf": 30000.0,
    "enable_encryption": 25000.0,
    "network_segmentation": 20000.0,
    "add_monitoring": 10000.0,
    "setup_dr": 60000.0,
    "add_backup": 35000.0,
}

# Phase names and estimated durations
_PHASE_META: dict[int, dict] = {
    1: {"name": "Critical Fixes", "estimated_weeks": 2, "team_size": 3},
    2: {"name": "Security Hardening", "estimated_weeks": 3, "team_size": 3},
    3: {"name": "DR & Compliance", "estimated_weeks": 4, "team_size": 4},
}


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class PlanTask:
    """A single remediation task within a plan."""

    id: str  # "1.1", "1.2", etc.
    title: str  # "Add Aurora Multi-AZ replica"
    description: str
    phase: int  # 1, 2, or 3
    category: str  # "redundancy", "security", "dr", "monitoring", "compliance"
    priority: str  # "critical", "high", "medium", "low"

    # Team requirements
    required_role: str  # "SRE", "DBA", "Security", "Infrastructure"
    estimated_hours: float  # person-hours to implement

    # Cost
    monthly_cost_increase: float  # additional monthly infra cost
    one_time_cost: float  # implementation cost (labor)

    # Impact
    resilience_score_delta: float  # expected score improvement
    risk_reduction_annual: float  # annual risk reduction in $

    # Dependencies
    depends_on: list[str] = field(default_factory=list)  # task IDs

    @property
    def roi_percent(self) -> float:
        """Calculate ROI as (annual benefit - annual cost) / annual cost * 100."""
        annual_cost = self.monthly_cost_increase * 12 + self.one_time_cost
        if annual_cost <= 0:
            return float("inf") if self.risk_reduction_annual > 0 else 0.0
        return (self.risk_reduction_annual - annual_cost) / annual_cost * 100


@dataclass
class RemediationPhase:
    """A group of tasks in a single implementation phase."""

    phase_number: int
    name: str  # "Critical Fixes", "Security Hardening", "DR & Compliance"
    tasks: list[PlanTask]
    estimated_weeks: int
    team_size: int
    phase_cost: float
    score_before: float
    score_after: float


@dataclass
class RemediationPlan:
    """Complete remediation plan with all phases."""

    current_score: float
    target_score: float
    phases: list[RemediationPhase]
    total_weeks: int
    total_budget: float
    total_risk_reduction: float
    overall_roi: float

    @property
    def summary(self) -> str:
        """Build a human-readable summary of the remediation plan."""
        lines: list[str] = []
        lines.append(f"Remediation Plan: {self.current_score:.1f} -> {self.target_score:.1f}")
        lines.append(f"Timeline: {self.total_weeks} weeks | Budget: ${self.total_budget:,.0f}")
        lines.append(f"Annual Risk Reduction: ${self.total_risk_reduction:,.0f}")
        lines.append(f"Overall ROI: {self.overall_roi:.0f}%")
        lines.append("")

        for phase in self.phases:
            lines.append(
                f"Phase {phase.phase_number}: {phase.name} "
                f"({phase.estimated_weeks} weeks, team of {phase.team_size})"
            )
            lines.append(
                f"  Score: {phase.score_before:.1f} -> {phase.score_after:.1f} "
                f"| Cost: ${phase.phase_cost:,.0f}"
            )
            for task in phase.tasks:
                lines.append(
                    f"  [{task.id}] {task.title} "
                    f"({task.priority}, {task.required_role}, {task.estimated_hours}h)"
                )
            lines.append("")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Planner engine
# ---------------------------------------------------------------------------


class RemediationPlanner:
    """Generates phased remediation plans from infrastructure analysis.

    Analyzes the graph using resilience_score_v2(), security scoring, and
    compliance checks.  Converts recommendations into concrete tasks with
    time, cost, and ROI estimates.

    Parameters
    ----------
    graph:
        The infrastructure graph to analyze and plan improvements for.
    """

    def __init__(self, graph: InfraGraph) -> None:
        self.graph = graph

    def plan(
        self,
        target_score: float = 90.0,
        budget_limit: float | None = None,
    ) -> RemediationPlan:
        """Generate a phased remediation plan.

        Parameters
        ----------
        target_score:
            Target resilience score to achieve (0-100).
        budget_limit:
            Maximum total budget.  If set, tasks are pruned when the
            cumulative cost would exceed this limit.

        Returns
        -------
        RemediationPlan
            A complete plan with phases, tasks, timeline, and ROI.
        """
        # 1. Analyze current state
        v2_result = self.graph.resilience_score_v2()
        current_score = v2_result["score"]
        recommendations = v2_result.get("recommendations", [])

        # Also gather security recommendations
        security_tasks = self._generate_security_tasks()
        # DR/backup tasks
        dr_tasks = self._generate_dr_tasks()

        # 2. Generate tasks from recommendations
        all_tasks = self._generate_tasks_from_recommendations(recommendations)
        all_tasks.extend(security_tasks)
        all_tasks.extend(dr_tasks)

        # Deduplicate by title
        seen_titles: set[str] = set()
        unique_tasks: list[PlanTask] = []
        for task in all_tasks:
            if task.title not in seen_titles:
                seen_titles.add(task.title)
                unique_tasks.append(task)
        all_tasks = unique_tasks

        # 3. Prioritize by ROI (risk_reduction / cost ratio)
        all_tasks.sort(key=lambda t: t.roi_percent, reverse=True)

        # 4. Apply budget constraints
        if budget_limit is not None:
            budget_tasks: list[PlanTask] = []
            cumulative = 0.0
            for task in all_tasks:
                task_total = task.monthly_cost_increase * 12 + task.one_time_cost
                if cumulative + task_total <= budget_limit:
                    budget_tasks.append(task)
                    cumulative += task_total
            all_tasks = budget_tasks

        # 5. Group into phases
        phase_groups: dict[int, list[PlanTask]] = {1: [], 2: [], 3: []}
        for task in all_tasks:
            phase_num = task.phase
            if phase_num not in phase_groups:
                phase_num = 3
            phase_groups[phase_num].append(task)

        # 6. Assign task IDs and set up dependency ordering
        for phase_num, tasks in phase_groups.items():
            for idx, task in enumerate(tasks, 1):
                task.id = f"{phase_num}.{idx}"

        # DB redundancy tasks must come before DR tasks
        replica_task_ids = [
            t.id for t in phase_groups.get(1, [])
            if "replica" in t.title.lower() or "failover" in t.title.lower()
        ]
        for task in phase_groups.get(3, []):
            if "dr" in task.category or "backup" in task.category:
                task.depends_on = replica_task_ids[:]

        # 7. Simulate impact - estimate score improvement per phase
        phases: list[RemediationPhase] = []
        running_score = current_score

        for phase_num in [1, 2, 3]:
            tasks = phase_groups.get(phase_num, [])
            if not tasks:
                continue

            meta = _PHASE_META.get(phase_num, {"name": f"Phase {phase_num}", "estimated_weeks": 2, "team_size": 3})
            phase_cost = sum(
                t.monthly_cost_increase * 12 + t.one_time_cost for t in tasks
            )
            score_delta = sum(t.resilience_score_delta for t in tasks)
            score_after = min(100.0, running_score + score_delta)

            phases.append(RemediationPhase(
                phase_number=phase_num,
                name=meta["name"],
                tasks=tasks,
                estimated_weeks=meta["estimated_weeks"],
                team_size=meta["team_size"],
                phase_cost=phase_cost,
                score_before=running_score,
                score_after=score_after,
            ))

            running_score = score_after

        # 8. Build the overall plan
        total_weeks = sum(p.estimated_weeks for p in phases)
        total_budget = sum(p.phase_cost for p in phases)
        total_risk_reduction = sum(t.risk_reduction_annual for p in phases for t in p.tasks)

        if total_budget > 0:
            overall_roi = (total_risk_reduction - total_budget) / total_budget * 100
        else:
            overall_roi = float("inf") if total_risk_reduction > 0 else 0.0

        return RemediationPlan(
            current_score=current_score,
            target_score=target_score,
            phases=phases,
            total_weeks=total_weeks,
            total_budget=total_budget,
            total_risk_reduction=total_risk_reduction,
            overall_roi=overall_roi,
        )

    # ------------------------------------------------------------------
    # Task generation from v2 recommendations
    # ------------------------------------------------------------------

    def _generate_tasks_from_recommendations(
        self, recommendations: list[str]
    ) -> list[PlanTask]:
        """Convert resilience_score_v2 recommendations into PlanTask items."""
        tasks: list[PlanTask] = []

        for rec in recommendations:
            rec_lower = rec.lower()

            if "no redundancy" in rec_lower and "replicas" in rec_lower:
                # Extract component ID from recommendation
                comp_id = self._extract_component_id(rec)
                est = TASK_ESTIMATES["add_replica"]
                tasks.append(PlanTask(
                    id="",
                    title=f"Add replica for '{comp_id}'" if comp_id else "Add replicas for SPOF components",
                    description=rec,
                    phase=_ACTION_PHASE["add_replica"],
                    category=_ACTION_CATEGORY["add_replica"],
                    priority=_ACTION_PRIORITY["add_replica"],
                    required_role=est["role"],
                    estimated_hours=est["hours"],
                    monthly_cost_increase=est["monthly_cost"],
                    one_time_cost=est["hours"] * _LABOR_COST_PER_HOUR,
                    resilience_score_delta=self._estimate_score_delta("add_replica"),
                    risk_reduction_annual=_ACTION_RISK_REDUCTION["add_replica"],
                ))

            elif "circuit breaker" in rec_lower:
                est = TASK_ESTIMATES["add_circuit_breaker"]
                tasks.append(PlanTask(
                    id="",
                    title="Enable circuit breakers on dependency edges",
                    description=rec,
                    phase=_ACTION_PHASE["add_circuit_breaker"],
                    category=_ACTION_CATEGORY["add_circuit_breaker"],
                    priority=_ACTION_PRIORITY["add_circuit_breaker"],
                    required_role=est["role"],
                    estimated_hours=est["hours"],
                    monthly_cost_increase=est["monthly_cost"],
                    one_time_cost=est["hours"] * _LABOR_COST_PER_HOUR,
                    resilience_score_delta=self._estimate_score_delta("add_circuit_breaker"),
                    risk_reduction_annual=_ACTION_RISK_REDUCTION["add_circuit_breaker"],
                ))

            elif "no auto-recovery" in rec_lower or "autoscaling" in rec_lower:
                comp_id = self._extract_component_id(rec)
                est = TASK_ESTIMATES["enable_autoscaling"]
                tasks.append(PlanTask(
                    id="",
                    title=f"Enable autoscaling for '{comp_id}'" if comp_id else "Enable autoscaling",
                    description=rec,
                    phase=_ACTION_PHASE["enable_autoscaling"],
                    category=_ACTION_CATEGORY["enable_autoscaling"],
                    priority=_ACTION_PRIORITY["enable_autoscaling"],
                    required_role=est["role"],
                    estimated_hours=est["hours"],
                    monthly_cost_increase=est["monthly_cost"],
                    one_time_cost=est["hours"] * _LABOR_COST_PER_HOUR,
                    resilience_score_delta=self._estimate_score_delta("enable_autoscaling"),
                    risk_reduction_annual=_ACTION_RISK_REDUCTION["enable_autoscaling"],
                ))

            elif "high utilization" in rec_lower:
                comp_id = self._extract_component_id(rec)
                est = TASK_ESTIMATES["enable_autoscaling"]
                tasks.append(PlanTask(
                    id="",
                    title=f"Scale up or enable autoscaling for '{comp_id}'" if comp_id else "Address high utilization",
                    description=rec,
                    phase=_ACTION_PHASE["enable_autoscaling"],
                    category=_ACTION_CATEGORY["enable_autoscaling"],
                    priority="high",
                    required_role=est["role"],
                    estimated_hours=est["hours"],
                    monthly_cost_increase=est["monthly_cost"],
                    one_time_cost=est["hours"] * _LABOR_COST_PER_HOUR,
                    resilience_score_delta=self._estimate_score_delta("enable_autoscaling"),
                    risk_reduction_annual=_ACTION_RISK_REDUCTION["enable_autoscaling"],
                ))

            elif "'requires' dependencies" in rec_lower and "redundancy" in rec_lower:
                est = TASK_ESTIMATES["add_failover"]
                tasks.append(PlanTask(
                    id="",
                    title="Add failover for critical dependencies",
                    description=rec,
                    phase=_ACTION_PHASE["add_failover"],
                    category=_ACTION_CATEGORY["add_failover"],
                    priority=_ACTION_PRIORITY["add_failover"],
                    required_role=est["role"],
                    estimated_hours=est["hours"],
                    monthly_cost_increase=est["monthly_cost"],
                    one_time_cost=est["hours"] * _LABOR_COST_PER_HOUR,
                    resilience_score_delta=self._estimate_score_delta("add_failover"),
                    risk_reduction_annual=_ACTION_RISK_REDUCTION["add_failover"],
                ))

        return tasks

    def _generate_security_tasks(self) -> list[PlanTask]:
        """Generate tasks from security profile analysis."""
        tasks: list[PlanTask] = []

        for comp in self.graph.components.values():
            sec = comp.security

            if not sec.encryption_at_rest or not sec.encryption_in_transit:
                est = TASK_ESTIMATES["enable_encryption"]
                tasks.append(PlanTask(
                    id="",
                    title=f"Enable encryption for '{comp.id}'",
                    description=(
                        f"Component '{comp.id}' is missing encryption "
                        f"(at_rest={sec.encryption_at_rest}, in_transit={sec.encryption_in_transit}). "
                        "Enable both encryption at rest and in transit."
                    ),
                    phase=_ACTION_PHASE["enable_encryption"],
                    category=_ACTION_CATEGORY["enable_encryption"],
                    priority=_ACTION_PRIORITY["enable_encryption"],
                    required_role=est["role"],
                    estimated_hours=est["hours"],
                    monthly_cost_increase=est["monthly_cost"],
                    one_time_cost=est["hours"] * _LABOR_COST_PER_HOUR,
                    resilience_score_delta=self._estimate_score_delta("enable_encryption"),
                    risk_reduction_annual=_ACTION_RISK_REDUCTION["enable_encryption"],
                ))

            if not sec.waf_protected and comp.type in (
                ComponentType.LOAD_BALANCER,
                ComponentType.WEB_SERVER,
                ComponentType.APP_SERVER,
            ):
                est = TASK_ESTIMATES["add_waf"]
                tasks.append(PlanTask(
                    id="",
                    title=f"Add WAF protection for '{comp.id}'",
                    description=(
                        f"Component '{comp.id}' (type={comp.type.value}) is not protected by a WAF. "
                        "Deploy WAF to protect against application-layer attacks."
                    ),
                    phase=_ACTION_PHASE["add_waf"],
                    category=_ACTION_CATEGORY["add_waf"],
                    priority=_ACTION_PRIORITY["add_waf"],
                    required_role=est["role"],
                    estimated_hours=est["hours"],
                    monthly_cost_increase=est["monthly_cost"],
                    one_time_cost=est["hours"] * _LABOR_COST_PER_HOUR,
                    resilience_score_delta=self._estimate_score_delta("add_waf"),
                    risk_reduction_annual=_ACTION_RISK_REDUCTION["add_waf"],
                ))

            if not sec.network_segmented:
                est = TASK_ESTIMATES["network_segmentation"]
                tasks.append(PlanTask(
                    id="",
                    title=f"Enable network segmentation for '{comp.id}'",
                    description=(
                        f"Component '{comp.id}' is not network segmented. "
                        "Segment network to limit lateral movement."
                    ),
                    phase=_ACTION_PHASE["network_segmentation"],
                    category=_ACTION_CATEGORY["network_segmentation"],
                    priority=_ACTION_PRIORITY["network_segmentation"],
                    required_role=est["role"],
                    estimated_hours=est["hours"],
                    monthly_cost_increase=est["monthly_cost"],
                    one_time_cost=est["hours"] * _LABOR_COST_PER_HOUR,
                    resilience_score_delta=self._estimate_score_delta("network_segmentation"),
                    risk_reduction_annual=_ACTION_RISK_REDUCTION["network_segmentation"],
                ))

        return tasks

    def _generate_dr_tasks(self) -> list[PlanTask]:
        """Generate DR and backup tasks."""
        tasks: list[PlanTask] = []

        # Check for DR region
        has_dr = False
        for comp in self.graph.components.values():
            region_cfg = getattr(comp, "region", None)
            if region_cfg is not None:
                if region_cfg.dr_target_region or not region_cfg.is_primary:
                    has_dr = True
                    break

        if not has_dr and len(self.graph.components) > 0:
            est = TASK_ESTIMATES["setup_dr"]
            tasks.append(PlanTask(
                id="",
                title="Set up cross-region disaster recovery",
                description=(
                    "No DR region detected. Set up cross-region replication "
                    "for business continuity."
                ),
                phase=_ACTION_PHASE["setup_dr"],
                category="dr",
                priority=_ACTION_PRIORITY["setup_dr"],
                required_role=est["role"],
                estimated_hours=est["hours"],
                monthly_cost_increase=est["monthly_cost"],
                one_time_cost=est["hours"] * _LABOR_COST_PER_HOUR,
                resilience_score_delta=self._estimate_score_delta("setup_dr"),
                risk_reduction_annual=_ACTION_RISK_REDUCTION["setup_dr"],
            ))

        # Check for backup on DB/storage components
        for comp in self.graph.components.values():
            if comp.type in (ComponentType.DATABASE, ComponentType.STORAGE):
                if not comp.security.backup_enabled:
                    est = TASK_ESTIMATES["add_backup"]
                    tasks.append(PlanTask(
                        id="",
                        title=f"Enable backups for '{comp.id}'",
                        description=(
                            f"Component '{comp.id}' (type={comp.type.value}) "
                            "has no backup enabled. Enable automated backups."
                        ),
                        phase=_ACTION_PHASE["add_backup"],
                        category="dr",
                        priority=_ACTION_PRIORITY["add_backup"],
                        required_role=est["role"],
                        estimated_hours=est["hours"],
                        monthly_cost_increase=est["monthly_cost"],
                        one_time_cost=est["hours"] * _LABOR_COST_PER_HOUR,
                        resilience_score_delta=self._estimate_score_delta("add_backup"),
                        risk_reduction_annual=_ACTION_RISK_REDUCTION["add_backup"],
                    ))

        return tasks

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_component_id(recommendation: str) -> str:
        """Extract a component ID from a recommendation string like "Component 'xyz' has..."."""
        import re

        match = re.search(r"[Cc]omponent '([^']+)'", recommendation)
        if match:
            return match.group(1)
        return ""

    def _estimate_score_delta(self, action: str) -> float:
        """Estimate the resilience score improvement for an action.

        Uses a heuristic based on the number of components and the
        category of the action.
        """
        n = max(len(self.graph.components), 1)

        # Base delta per action type (for a single component)
        base_deltas: dict[str, float] = {
            "add_replica": 5.0,
            "enable_autoscaling": 3.0,
            "add_waf": 2.0,
            "enable_encryption": 1.5,
            "setup_dr": 4.0,
            "add_monitoring": 2.0,
            "network_segmentation": 1.0,
            "add_backup": 2.0,
            "add_circuit_breaker": 3.0,
            "add_failover": 4.0,
        }

        delta = base_deltas.get(action, 2.0)
        # Scale down slightly for larger graphs (diminishing returns)
        if n > 5:
            delta *= 5 / n
        return round(delta, 1)

    def plan_to_dict(self, plan: RemediationPlan) -> dict:
        """Convert a RemediationPlan to a JSON-serializable dict."""
        return {
            "current_score": plan.current_score,
            "target_score": plan.target_score,
            "total_weeks": plan.total_weeks,
            "total_budget": plan.total_budget,
            "total_risk_reduction": plan.total_risk_reduction,
            "overall_roi": plan.overall_roi,
            "phases": [
                {
                    "phase_number": phase.phase_number,
                    "name": phase.name,
                    "estimated_weeks": phase.estimated_weeks,
                    "team_size": phase.team_size,
                    "phase_cost": phase.phase_cost,
                    "score_before": phase.score_before,
                    "score_after": phase.score_after,
                    "tasks": [
                        {
                            "id": task.id,
                            "title": task.title,
                            "description": task.description,
                            "phase": task.phase,
                            "category": task.category,
                            "priority": task.priority,
                            "required_role": task.required_role,
                            "estimated_hours": task.estimated_hours,
                            "monthly_cost_increase": task.monthly_cost_increase,
                            "one_time_cost": task.one_time_cost,
                            "resilience_score_delta": task.resilience_score_delta,
                            "risk_reduction_annual": task.risk_reduction_annual,
                            "roi_percent": task.roi_percent
                            if task.roi_percent != float("inf")
                            else "infinite",
                            "depends_on": task.depends_on,
                        }
                        for task in phase.tasks
                    ],
                }
                for phase in plan.phases
            ],
            "summary": plan.summary,
        }
