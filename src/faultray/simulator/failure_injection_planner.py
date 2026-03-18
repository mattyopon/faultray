"""Intelligent Failure Injection Planner -- plans optimal chaos injection sequences.

Plans which failures to inject and in what order to maximise learning
while minimising risk.  Uses graph topology, component criticality,
and past experiment coverage to produce a prioritised, safety-validated
injection plan.
"""

from __future__ import annotations

import logging
import uuid
from collections import deque
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from faultray.model.components import Component, ComponentType
from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class InjectionType(str, Enum):
    """Concrete failure-injection technique."""

    PROCESS_KILL = "process_kill"
    NETWORK_DELAY = "network_delay"
    NETWORK_PARTITION = "network_partition"
    CPU_STRESS = "cpu_stress"
    MEMORY_PRESSURE = "memory_pressure"
    DISK_FILL = "disk_fill"
    DNS_FAILURE = "dns_failure"
    DEPENDENCY_TIMEOUT = "dependency_timeout"
    CLOCK_SKEW = "clock_skew"
    CERTIFICATE_EXPIRY = "certificate_expiry"


class InjectionPriority(str, Enum):
    """Priority ranking for an injection experiment."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFORMATIONAL = "informational"


class SafetyLevel(str, Enum):
    """Safety classification for an injection experiment."""

    SAFE = "safe"
    CAUTION = "caution"
    RISKY = "risky"
    DANGEROUS = "dangerous"
    PROHIBITED = "prohibited"


class CoverageGap(str, Enum):
    """How well a component has been tested by past experiments."""

    NEVER_TESTED = "never_tested"
    STALE_TEST = "stale_test"
    PARTIAL_COVERAGE = "partial_coverage"
    WELL_COVERED = "well_covered"


class InjectionScope(str, Enum):
    """Scope of an injection experiment."""

    SINGLE_COMPONENT = "single_component"
    MULTI_COMPONENT = "multi_component"
    ZONE = "zone"
    REGION = "region"
    GLOBAL = "global"


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


class InjectionTarget(BaseModel):
    """A component targeted for failure injection."""

    component_id: str
    component_type: ComponentType
    coverage_gap: CoverageGap = CoverageGap.NEVER_TESTED
    last_tested_days_ago: Optional[int] = None


class SafetyConstraint(BaseModel):
    """Safety constraints governing injection experiments."""

    max_blast_radius_components: int = Field(default=10, ge=0)
    excluded_components: list[str] = Field(default_factory=list)
    required_redundancy_level: int = Field(default=1, ge=0)
    business_hours_only: bool = False
    max_duration_seconds: int = Field(default=300, ge=0)


class InjectionExperiment(BaseModel):
    """A single planned injection experiment."""

    experiment_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    injection_type: InjectionType
    targets: list[InjectionTarget] = Field(default_factory=list)
    scope: InjectionScope = InjectionScope.SINGLE_COMPONENT
    priority: InjectionPriority = InjectionPriority.MEDIUM
    safety_level: SafetyLevel = SafetyLevel.CAUTION
    estimated_blast_radius: int = Field(default=0, ge=0)
    hypothesis: str = ""
    expected_outcome: str = ""
    rollback_procedure: str = ""


class CoverageReport(BaseModel):
    """Coverage analysis of past injection experiments."""

    total_components: int = Field(default=0, ge=0)
    tested_components: int = Field(default=0, ge=0)
    coverage_percentage: float = Field(default=0.0, ge=0.0, le=100.0)
    gaps: list[InjectionTarget] = Field(default_factory=list)


class InjectionPlan(BaseModel):
    """A complete, ordered injection plan."""

    experiments: list[InjectionExperiment] = Field(default_factory=list)
    total_experiments: int = Field(default=0, ge=0)
    estimated_duration_minutes: float = Field(default=0.0, ge=0.0)
    coverage_improvement: float = Field(default=0.0, ge=0.0, le=100.0)
    risk_summary: str = ""
    execution_order: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Constants for scoring and method suitability
# ---------------------------------------------------------------------------

_CRITICALITY_WEIGHTS: dict[ComponentType, float] = {
    ComponentType.LOAD_BALANCER: 0.95,
    ComponentType.DNS: 0.90,
    ComponentType.DATABASE: 0.85,
    ComponentType.APP_SERVER: 0.70,
    ComponentType.WEB_SERVER: 0.65,
    ComponentType.QUEUE: 0.60,
    ComponentType.STORAGE: 0.55,
    ComponentType.CACHE: 0.50,
    ComponentType.EXTERNAL_API: 0.40,
    ComponentType.CUSTOM: 0.35,
    ComponentType.AI_AGENT: 0.65,
    ComponentType.LLM_ENDPOINT: 0.60,
    ComponentType.TOOL_SERVICE: 0.50,
    ComponentType.AGENT_ORCHESTRATOR: 0.80,
}

_SAFETY_CONCERN: dict[ComponentType, float] = {
    ComponentType.DATABASE: 0.95,
    ComponentType.QUEUE: 0.85,
    ComponentType.STORAGE: 0.80,
    ComponentType.LOAD_BALANCER: 0.75,
    ComponentType.DNS: 0.70,
    ComponentType.APP_SERVER: 0.50,
    ComponentType.WEB_SERVER: 0.45,
    ComponentType.CACHE: 0.30,
    ComponentType.EXTERNAL_API: 0.25,
    ComponentType.CUSTOM: 0.40,
    ComponentType.AI_AGENT: 0.55,
    ComponentType.LLM_ENDPOINT: 0.45,
    ComponentType.TOOL_SERVICE: 0.35,
    ComponentType.AGENT_ORCHESTRATOR: 0.70,
}

_METHOD_SUITABILITY: dict[ComponentType, list[InjectionType]] = {
    ComponentType.LOAD_BALANCER: [
        InjectionType.PROCESS_KILL,
        InjectionType.NETWORK_DELAY,
        InjectionType.NETWORK_PARTITION,
        InjectionType.CERTIFICATE_EXPIRY,
        InjectionType.CPU_STRESS,
    ],
    ComponentType.WEB_SERVER: [
        InjectionType.PROCESS_KILL,
        InjectionType.CPU_STRESS,
        InjectionType.MEMORY_PRESSURE,
        InjectionType.NETWORK_DELAY,
        InjectionType.CERTIFICATE_EXPIRY,
    ],
    ComponentType.APP_SERVER: [
        InjectionType.PROCESS_KILL,
        InjectionType.CPU_STRESS,
        InjectionType.MEMORY_PRESSURE,
        InjectionType.NETWORK_DELAY,
        InjectionType.DEPENDENCY_TIMEOUT,
        InjectionType.CLOCK_SKEW,
    ],
    ComponentType.DATABASE: [
        InjectionType.PROCESS_KILL,
        InjectionType.DISK_FILL,
        InjectionType.NETWORK_PARTITION,
        InjectionType.CPU_STRESS,
        InjectionType.MEMORY_PRESSURE,
        InjectionType.CLOCK_SKEW,
    ],
    ComponentType.CACHE: [
        InjectionType.PROCESS_KILL,
        InjectionType.MEMORY_PRESSURE,
        InjectionType.NETWORK_DELAY,
        InjectionType.CPU_STRESS,
    ],
    ComponentType.QUEUE: [
        InjectionType.PROCESS_KILL,
        InjectionType.DISK_FILL,
        InjectionType.MEMORY_PRESSURE,
        InjectionType.CPU_STRESS,
        InjectionType.NETWORK_PARTITION,
    ],
    ComponentType.STORAGE: [
        InjectionType.DISK_FILL,
        InjectionType.NETWORK_PARTITION,
        InjectionType.PROCESS_KILL,
        InjectionType.CPU_STRESS,
    ],
    ComponentType.DNS: [
        InjectionType.DNS_FAILURE,
        InjectionType.NETWORK_DELAY,
        InjectionType.PROCESS_KILL,
    ],
    ComponentType.EXTERNAL_API: [
        InjectionType.NETWORK_DELAY,
        InjectionType.NETWORK_PARTITION,
        InjectionType.DNS_FAILURE,
        InjectionType.DEPENDENCY_TIMEOUT,
        InjectionType.CERTIFICATE_EXPIRY,
    ],
    ComponentType.CUSTOM: [
        InjectionType.PROCESS_KILL,
        InjectionType.CPU_STRESS,
        InjectionType.MEMORY_PRESSURE,
        InjectionType.NETWORK_DELAY,
    ],
    ComponentType.AI_AGENT: [
        InjectionType.PROCESS_KILL,
        InjectionType.CPU_STRESS,
        InjectionType.MEMORY_PRESSURE,
        InjectionType.NETWORK_DELAY,
        InjectionType.DEPENDENCY_TIMEOUT,
    ],
    ComponentType.LLM_ENDPOINT: [
        InjectionType.NETWORK_DELAY,
        InjectionType.NETWORK_PARTITION,
        InjectionType.DEPENDENCY_TIMEOUT,
        InjectionType.DNS_FAILURE,
    ],
    ComponentType.TOOL_SERVICE: [
        InjectionType.PROCESS_KILL,
        InjectionType.CPU_STRESS,
        InjectionType.MEMORY_PRESSURE,
        InjectionType.NETWORK_DELAY,
    ],
    ComponentType.AGENT_ORCHESTRATOR: [
        InjectionType.PROCESS_KILL,
        InjectionType.CPU_STRESS,
        InjectionType.MEMORY_PRESSURE,
        InjectionType.NETWORK_DELAY,
        InjectionType.DEPENDENCY_TIMEOUT,
        InjectionType.CLOCK_SKEW,
    ],
}

# Base duration estimates per injection type (minutes).
_INJECTION_DURATION: dict[InjectionType, float] = {
    InjectionType.PROCESS_KILL: 3.0,
    InjectionType.NETWORK_DELAY: 5.0,
    InjectionType.NETWORK_PARTITION: 8.0,
    InjectionType.CPU_STRESS: 7.0,
    InjectionType.MEMORY_PRESSURE: 7.0,
    InjectionType.DISK_FILL: 6.0,
    InjectionType.DNS_FAILURE: 4.0,
    InjectionType.DEPENDENCY_TIMEOUT: 5.0,
    InjectionType.CLOCK_SKEW: 5.0,
    InjectionType.CERTIFICATE_EXPIRY: 6.0,
}

# Risk factor per injection type (0-1).
_INJECTION_RISK: dict[InjectionType, float] = {
    InjectionType.PROCESS_KILL: 0.7,
    InjectionType.NETWORK_DELAY: 0.3,
    InjectionType.NETWORK_PARTITION: 0.8,
    InjectionType.CPU_STRESS: 0.5,
    InjectionType.MEMORY_PRESSURE: 0.6,
    InjectionType.DISK_FILL: 0.6,
    InjectionType.DNS_FAILURE: 0.7,
    InjectionType.DEPENDENCY_TIMEOUT: 0.4,
    InjectionType.CLOCK_SKEW: 0.4,
    InjectionType.CERTIFICATE_EXPIRY: 0.5,
}

# Stale threshold (days) -- components tested longer ago than this are stale.
_STALE_THRESHOLD_DAYS = 30


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class FailureInjectionPlanner:
    """Stateless engine that plans intelligent failure-injection sequences."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_plan(
        self,
        graph: InfraGraph,
        safety_constraints: SafetyConstraint | None = None,
        max_experiments: int = 10,
    ) -> InjectionPlan:
        """Generate an optimal injection plan for *graph*.

        Analyses the graph to identify high-value injection targets,
        generates experiments, validates them against *safety_constraints*,
        and returns a prioritised, ordered plan.
        """
        if max_experiments < 0:
            max_experiments = 0

        if not graph.components:
            return InjectionPlan(
                risk_summary="No components in graph -- nothing to plan.",
            )

        if safety_constraints is None:
            safety_constraints = SafetyConstraint()

        targets = self.prioritize_targets(graph)
        experiments: list[InjectionExperiment] = []

        for target in targets:
            if len(experiments) >= max_experiments:
                break

            if target.component_id in safety_constraints.excluded_components:
                continue

            comp = graph.get_component(target.component_id)
            if comp is None:
                continue

            if comp.replicas < safety_constraints.required_redundancy_level:
                continue

            component_experiments = self.suggest_experiments_for_component(
                graph, target.component_id
            )

            for exp in component_experiments:
                if len(experiments) >= max_experiments:
                    break

                safety = self.assess_safety(graph, exp)
                exp.safety_level = safety

                if safety == SafetyLevel.PROHIBITED:
                    continue

                if exp.estimated_blast_radius > safety_constraints.max_blast_radius_components:
                    continue

                experiments.append(exp)

        ordered = self.optimize_execution_order(experiments)

        total_duration = sum(
            _INJECTION_DURATION.get(e.injection_type, 5.0) for e in ordered
        )

        coverage_before = self._count_covered(graph, [])
        coverage_after = self._count_covered(graph, ordered)
        total = len(graph.components)
        improvement = 0.0
        if total > 0:
            improvement = min(
                100.0,
                max(0.0, (coverage_after - coverage_before) / total * 100),
            )

        risk_summary = self._build_risk_summary(graph, ordered)

        return InjectionPlan(
            experiments=ordered,
            total_experiments=len(ordered),
            estimated_duration_minutes=round(total_duration, 1),
            coverage_improvement=round(improvement, 2),
            risk_summary=risk_summary,
            execution_order=[e.experiment_id for e in ordered],
        )

    def analyze_coverage(
        self,
        graph: InfraGraph,
        past_experiments: list[InjectionExperiment] | None = None,
    ) -> CoverageReport:
        """Analyse how well past experiments cover the current graph."""
        if past_experiments is None:
            past_experiments = []

        total = len(graph.components)
        if total == 0:
            return CoverageReport()

        tested_ids: set[str] = set()
        tested_types: dict[str, set[InjectionType]] = {}

        for exp in past_experiments:
            for t in exp.targets:
                tested_ids.add(t.component_id)
                tested_types.setdefault(t.component_id, set()).add(
                    exp.injection_type
                )

        gaps: list[InjectionTarget] = []
        for comp in graph.components.values():
            if comp.id not in tested_ids:
                gaps.append(
                    InjectionTarget(
                        component_id=comp.id,
                        component_type=comp.type,
                        coverage_gap=CoverageGap.NEVER_TESTED,
                        last_tested_days_ago=None,
                    )
                )
            else:
                methods_tested = tested_types.get(comp.id, set())
                suitable = _METHOD_SUITABILITY.get(comp.type, list(InjectionType))
                coverage_ratio = len(methods_tested) / max(len(suitable), 1)
                if coverage_ratio < 0.5:
                    gaps.append(
                        InjectionTarget(
                            component_id=comp.id,
                            component_type=comp.type,
                            coverage_gap=CoverageGap.PARTIAL_COVERAGE,
                            last_tested_days_ago=0,
                        )
                    )

        tested = len(tested_ids & set(graph.components.keys()))
        pct = (tested / total * 100) if total > 0 else 0.0

        return CoverageReport(
            total_components=total,
            tested_components=tested,
            coverage_percentage=round(min(100.0, pct), 2),
            gaps=gaps,
        )

    def prioritize_targets(
        self,
        graph: InfraGraph,
    ) -> list[InjectionTarget]:
        """Return components sorted by injection value (highest first).

        Components with higher in-degree (more dependents), higher
        criticality weight, and lower coverage get higher priority.
        """
        if not graph.components:
            return []

        scored: list[tuple[float, InjectionTarget]] = []

        for comp in graph.components.values():
            dependents = graph.get_dependents(comp.id)
            in_degree = len(dependents)

            criticality = _CRITICALITY_WEIGHTS.get(comp.type, 0.35)
            total = max(len(graph.components), 1)
            in_degree_score = min(1.0, in_degree / total)

            blast = self.calculate_blast_radius(graph, comp.id)
            blast_score = min(1.0, blast / total)

            redundancy_penalty = 0.0
            if comp.replicas > 1:
                redundancy_penalty = 0.1

            value = (
                criticality * 0.35
                + in_degree_score * 0.30
                + blast_score * 0.25
                - redundancy_penalty
            )
            value = max(0.0, min(1.0, value))

            target = InjectionTarget(
                component_id=comp.id,
                component_type=comp.type,
                coverage_gap=CoverageGap.NEVER_TESTED,
            )
            scored.append((value, target))

        scored.sort(key=lambda t: t[0], reverse=True)
        return [t for _, t in scored]

    def assess_safety(
        self,
        graph: InfraGraph,
        experiment: InjectionExperiment,
    ) -> SafetyLevel:
        """Assess the safety level of a proposed experiment.

        Safety level is determined by:
        - blast_radius / total_components ratio
        - Component type safety concern (DATABASE/QUEUE > CACHE)
        - Whether targeting all instances of a redundant component simultaneously
        """
        total = len(graph.components)
        if total == 0:
            return SafetyLevel.SAFE

        # Compute blast radius across all targets
        blast = experiment.estimated_blast_radius
        for target in experiment.targets:
            b = self.calculate_blast_radius(graph, target.component_id)
            blast = max(blast, b)
        experiment.estimated_blast_radius = blast

        blast_ratio = blast / max(total, 1)

        # Max safety concern across targets
        max_safety_concern = 0.0
        for target in experiment.targets:
            concern = _SAFETY_CONCERN.get(target.component_type, 0.40)
            max_safety_concern = max(max_safety_concern, concern)

        # PROHIBITED if targeting all instances of a redundant component
        if self._targets_all_instances(graph, experiment):
            return SafetyLevel.PROHIBITED

        injection_risk = _INJECTION_RISK.get(experiment.injection_type, 0.5)
        combined = blast_ratio * 0.5 + max_safety_concern * 0.3 + injection_risk * 0.2

        if combined >= 0.75:
            return SafetyLevel.DANGEROUS
        elif combined >= 0.55:
            return SafetyLevel.RISKY
        elif combined >= 0.30:
            return SafetyLevel.CAUTION
        else:
            return SafetyLevel.SAFE

    def suggest_experiments_for_component(
        self,
        graph: InfraGraph,
        component_id: str,
    ) -> list[InjectionExperiment]:
        """Suggest injection experiments for a specific component."""
        comp = graph.get_component(component_id)
        if comp is None:
            return []

        suitable_types = _METHOD_SUITABILITY.get(comp.type, list(InjectionType))
        blast = self.calculate_blast_radius(graph, component_id)
        dependents = graph.get_dependents(component_id)
        in_degree = len(dependents)

        experiments: list[InjectionExperiment] = []

        for inj_type in suitable_types:
            target = InjectionTarget(
                component_id=component_id,
                component_type=comp.type,
                coverage_gap=CoverageGap.NEVER_TESTED,
            )

            priority = self._compute_priority(comp, in_degree, inj_type)

            scope = InjectionScope.SINGLE_COMPONENT
            total = max(len(graph.components), 1)
            if blast > total * 0.5:
                scope = InjectionScope.ZONE

            hypothesis = (
                f"Injecting {inj_type.value} into {comp.name} "
                f"(type={comp.type.value}) will reveal failure handling "
                f"behaviour for {blast} downstream component(s)."
            )
            expected = (
                f"System should degrade gracefully when {comp.name} "
                f"experiences {inj_type.value}."
            )
            rollback = f"Restart {comp.name} and verify health checks pass."

            exp = InjectionExperiment(
                injection_type=inj_type,
                targets=[target],
                scope=scope,
                priority=priority,
                estimated_blast_radius=blast,
                hypothesis=hypothesis,
                expected_outcome=expected,
                rollback_procedure=rollback,
            )
            experiments.append(exp)

        return experiments

    def calculate_blast_radius(
        self,
        graph: InfraGraph,
        component_id: str,
    ) -> int:
        """Calculate the number of components affected by a failure via BFS.

        Uses the reverse dependency graph: if A depends on B and B fails,
        A is affected.  The failed component itself is **not** counted.
        """
        if component_id not in graph.components:
            return 0

        affected: set[str] = set()
        queue: deque[str] = deque([component_id])

        while queue:
            current = queue.popleft()
            for dep in graph.get_dependents(current):
                if dep.id not in affected:
                    affected.add(dep.id)
                    queue.append(dep.id)

        return len(affected)

    def optimize_execution_order(
        self,
        experiments: list[InjectionExperiment],
    ) -> list[InjectionExperiment]:
        """Order experiments for optimal execution.

        Strategy: low blast radius first, then increasing.  This builds
        confidence before escalating to riskier experiments.
        """
        if len(experiments) <= 1:
            return list(experiments)

        return sorted(
            experiments,
            key=lambda e: (
                e.estimated_blast_radius,
                _INJECTION_RISK.get(e.injection_type, 0.5),
            ),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _compute_priority(
        self,
        comp: Component,
        in_degree: int,
        inj_type: InjectionType,
    ) -> InjectionPriority:
        """Compute priority for an experiment based on component characteristics."""
        criticality = _CRITICALITY_WEIGHTS.get(comp.type, 0.35)
        risk = _INJECTION_RISK.get(inj_type, 0.5)

        score = criticality * 0.4 + min(1.0, in_degree * 0.15) * 0.3 + risk * 0.3

        if score >= 0.70:
            return InjectionPriority.CRITICAL
        elif score >= 0.55:
            return InjectionPriority.HIGH
        elif score >= 0.35:
            return InjectionPriority.MEDIUM
        elif score >= 0.20:
            return InjectionPriority.LOW
        else:
            return InjectionPriority.INFORMATIONAL

    def _targets_all_instances(
        self,
        graph: InfraGraph,
        experiment: InjectionExperiment,
    ) -> bool:
        """Check if the experiment targets all instances of a redundant component.

        If multiple components share the same name and type (representing
        replicas modelled as separate graph nodes) and **all** of them are
        targeted, the experiment is PROHIBITED.
        """
        for target in experiment.targets:
            comp = graph.get_component(target.component_id)
            if comp is None:
                continue
            if comp.replicas <= 1:
                continue

            same_type_ids = [
                c.id
                for c in graph.components.values()
                if c.type == comp.type and c.name == comp.name
            ]
            targeted_ids = {t.component_id for t in experiment.targets}
            if len(same_type_ids) > 1 and all(
                sid in targeted_ids for sid in same_type_ids
            ):
                return True

        return False

    def _count_covered(
        self,
        graph: InfraGraph,
        experiments: list[InjectionExperiment],
    ) -> int:
        """Count unique graph components covered by *experiments*."""
        covered: set[str] = set()
        for exp in experiments:
            for t in exp.targets:
                if t.component_id in graph.components:
                    covered.add(t.component_id)
        return len(covered)

    def _build_risk_summary(
        self,
        graph: InfraGraph,
        experiments: list[InjectionExperiment],
    ) -> str:
        """Build a human-readable risk summary for the plan."""
        if not experiments:
            return "No experiments planned."

        total = len(graph.components)
        max_blast = max(e.estimated_blast_radius for e in experiments)
        avg_blast = sum(e.estimated_blast_radius for e in experiments) / len(
            experiments
        )

        dangerous_count = sum(
            1 for e in experiments if e.safety_level == SafetyLevel.DANGEROUS
        )
        risky_count = sum(
            1 for e in experiments if e.safety_level == SafetyLevel.RISKY
        )

        parts: list[str] = [
            f"{len(experiments)} experiment(s) planned across "
            f"{total} component(s).",
            f"Max blast radius: {max_blast}, avg: {avg_blast:.1f}.",
        ]

        if dangerous_count > 0:
            parts.append(
                f"WARNING: {dangerous_count} experiment(s) classified as DANGEROUS."
            )
        if risky_count > 0:
            parts.append(f"{risky_count} experiment(s) classified as RISKY.")

        return " ".join(parts)
