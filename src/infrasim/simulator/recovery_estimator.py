"""Recovery Time Estimator engine for InfraSim / ChaosProof.

Estimates Mean Time To Recovery (MTTR) for each component based on:
1. Component type (databases take longer to recover than stateless services)
2. Redundancy level (replicas, failover configuration)
3. Dependency chain depth (components deeper in the chain take longer)
4. Historical incident patterns (estimated from component characteristics)

The engine builds a recovery DAG from the dependency graph, identifies
parallel recovery groups, calculates the critical path, and generates
prioritised improvement recommendations.
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from infrasim.model.components import ComponentType, HealthStatus
from infrasim.model.graph import InfraGraph

if TYPE_CHECKING:
    from infrasim.model.components import Component
    from infrasim.simulator.engine import ScenarioResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Base MTTR lookup tables (minutes)
# ---------------------------------------------------------------------------

# (best_case, worst_case) for each component type.
# Best case assumes automation / redundancy; worst case is manual recovery.
_BASE_MTTR: dict[str, tuple[float, float]] = {
    ComponentType.WEB_SERVER.value: (5.0, 30.0),
    ComponentType.APP_SERVER.value: (5.0, 30.0),
    ComponentType.DATABASE.value: (15.0, 120.0),
    ComponentType.CACHE.value: (2.0, 10.0),
    ComponentType.QUEUE.value: (5.0, 30.0),
    ComponentType.LOAD_BALANCER.value: (1.0, 15.0),
    ComponentType.DNS.value: (5.0, 60.0),
    ComponentType.STORAGE.value: (10.0, 180.0),
    ComponentType.EXTERNAL_API.value: (0.0, 0.0),
    ComponentType.CUSTOM.value: (10.0, 60.0),
}

# Cascade delay added per dependency-chain level (minutes).
_CASCADE_DELAY_PER_LEVEL = 2.0


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class RecoveryStep:
    """A single step in a recovery sequence."""

    component_name: str
    action: str
    estimated_minutes: float
    can_parallelize: bool
    dependencies: list[str] = field(default_factory=list)


@dataclass
class ComponentRecovery:
    """Recovery estimate for a single component."""

    component_id: str
    component_name: str
    component_type: str
    estimated_mttr_minutes: float
    recovery_steps: list[RecoveryStep] = field(default_factory=list)
    bottlenecks: list[str] = field(default_factory=list)
    improvement_suggestions: list[str] = field(default_factory=list)


@dataclass
class RecoveryReport:
    """Full recovery report for an infrastructure graph."""

    components: list[ComponentRecovery]
    overall_mttr_minutes: float
    worst_case_mttr_minutes: float
    recovery_tiers: dict[str, list[str]]
    bottleneck_components: list[str]


@dataclass
class ScenarioRecovery:
    """Recovery estimate for a specific failure scenario."""

    scenario_name: str
    total_recovery_minutes: float
    recovery_sequence: list[RecoveryStep]
    parallel_recovery_groups: list[list[str]]
    critical_path_minutes: float


@dataclass
class RecoveryImprovement:
    """A prioritised recovery improvement recommendation."""

    component_name: str
    current_mttr: float
    improved_mttr: float
    improvement_action: str
    effort: str  # "low", "medium", "high"
    impact_score: float  # 0-100


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class RecoveryEstimator:
    """Estimates MTTR and builds recovery plans for infrastructure components.

    The estimator analyses each component's type, redundancy configuration,
    position in the dependency graph, and utilisation to produce realistic
    MTTR estimates.  It can also analyse a specific failure scenario to
    determine the optimal recovery sequence and critical path.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def estimate(self, graph: InfraGraph) -> RecoveryReport:
        """Produce a full recovery report for every component in *graph*.

        Parameters
        ----------
        graph:
            The infrastructure graph to analyse.

        Returns
        -------
        RecoveryReport
            Aggregated recovery analysis with per-component estimates,
            recovery tiers, and bottleneck identification.
        """
        if not graph.components:
            return RecoveryReport(
                components=[],
                overall_mttr_minutes=0.0,
                worst_case_mttr_minutes=0.0,
                recovery_tiers={"fast": [], "moderate": [], "slow": [], "critical": []},
                bottleneck_components=[],
            )

        component_recoveries: list[ComponentRecovery] = []
        for comp in graph.components.values():
            cr = self.estimate_component(comp, graph)
            component_recoveries.append(cr)

        mttr_values = [cr.estimated_mttr_minutes for cr in component_recoveries]
        overall = sum(mttr_values) / len(mttr_values) if mttr_values else 0.0
        worst_case = max(mttr_values) if mttr_values else 0.0

        tiers = self._classify_tiers(component_recoveries)
        bottlenecks = self._identify_bottlenecks(component_recoveries, graph)

        return RecoveryReport(
            components=component_recoveries,
            overall_mttr_minutes=round(overall, 2),
            worst_case_mttr_minutes=round(worst_case, 2),
            recovery_tiers=tiers,
            bottleneck_components=bottlenecks,
        )

    def estimate_component(
        self, component: Component, graph: InfraGraph
    ) -> ComponentRecovery:
        """Estimate MTTR for a single *component* within *graph*.

        Parameters
        ----------
        component:
            The component to analyse.
        graph:
            The infrastructure graph (needed for dependency depth).

        Returns
        -------
        ComponentRecovery
            Detailed recovery estimate with steps and suggestions.
        """
        base_mttr = self._base_mttr(component)
        modified_mttr = self._apply_modifiers(component, base_mttr, graph)
        steps = self._build_recovery_steps(component, graph)
        bottlenecks = self._identify_component_bottlenecks(component, graph)
        suggestions = self._generate_suggestions(component, modified_mttr, graph)

        return ComponentRecovery(
            component_id=component.id,
            component_name=component.name,
            component_type=component.type.value,
            estimated_mttr_minutes=round(modified_mttr, 2),
            recovery_steps=steps,
            bottlenecks=bottlenecks,
            improvement_suggestions=suggestions,
        )

    def estimate_scenario_recovery(
        self,
        graph: InfraGraph,
        scenario_result: ScenarioResult,
    ) -> ScenarioRecovery:
        """Estimate recovery time and sequence for a specific failure scenario.

        Analyses which components were affected by the scenario, builds a
        recovery DAG, identifies parallel groups, and computes the critical
        path.

        Parameters
        ----------
        graph:
            The infrastructure graph.
        scenario_result:
            The result of running a chaos scenario (from the simulation engine).

        Returns
        -------
        ScenarioRecovery
            Recovery sequence with parallelism analysis and critical path.
        """
        affected_ids = self._extract_affected_ids(scenario_result, graph)

        if not affected_ids:
            return ScenarioRecovery(
                scenario_name=scenario_result.scenario.name,
                total_recovery_minutes=0.0,
                recovery_sequence=[],
                parallel_recovery_groups=[],
                critical_path_minutes=0.0,
            )

        # Build per-component MTTR map.
        mttr_map: dict[str, float] = {}
        for cid in affected_ids:
            comp = graph.get_component(cid)
            if comp is not None:
                cr = self.estimate_component(comp, graph)
                mttr_map[cid] = cr.estimated_mttr_minutes

        # Build recovery DAG and identify parallel groups.
        parallel_groups = self._build_parallel_groups(affected_ids, graph)
        recovery_sequence = self._build_scenario_recovery_steps(
            parallel_groups, mttr_map, graph,
        )
        critical_path = self._calculate_critical_path(parallel_groups, mttr_map)
        total_recovery = critical_path  # critical path is the real constraint

        return ScenarioRecovery(
            scenario_name=scenario_result.scenario.name,
            total_recovery_minutes=round(total_recovery, 2),
            recovery_sequence=recovery_sequence,
            parallel_recovery_groups=[
                [cid for cid in grp] for grp in parallel_groups
            ],
            critical_path_minutes=round(critical_path, 2),
        )

    def get_recovery_roadmap(
        self, graph: InfraGraph
    ) -> list[RecoveryImprovement]:
        """Generate a prioritised list of improvements to reduce MTTR.

        Parameters
        ----------
        graph:
            The infrastructure graph to analyse.

        Returns
        -------
        list[RecoveryImprovement]
            Improvements sorted by descending ``impact_score``.
        """
        improvements: list[RecoveryImprovement] = []

        for comp in graph.components.values():
            cr = self.estimate_component(comp, graph)
            improvements.extend(
                self._generate_improvements(comp, cr, graph)
            )

        # Sort by impact (highest first).
        improvements.sort(key=lambda imp: imp.impact_score, reverse=True)
        return improvements

    # ------------------------------------------------------------------
    # MTTR calculation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _base_mttr(component: Component) -> float:
        """Look up the base MTTR for *component* based on its type.

        If the component has redundancy features (replicas, failover,
        autoscaling), the best-case estimate is used as the starting point;
        otherwise the worst-case estimate is used.
        """
        best, worst = _BASE_MTTR.get(
            component.type.value, (10.0, 60.0),
        )

        # External APIs: we cannot control their recovery.
        if component.type == ComponentType.EXTERNAL_API:
            return 0.0

        has_redundancy = (
            component.replicas > 1
            or component.failover.enabled
            or component.autoscaling.enabled
        )
        return best if has_redundancy else worst

    @staticmethod
    def _apply_modifiers(
        component: Component, base_mttr: float, graph: InfraGraph
    ) -> float:
        """Apply multiplier modifiers to the base MTTR.

        Modifiers
        ---------
        - Replicas > 1: reduce by 60-80%  (factor 0.2-0.4)
        - Failover enabled: reduce by 50-70%  (factor 0.3-0.5)
        - Autoscaling enabled: reduce by 40-60%  (factor 0.4-0.6)
        - High utilisation (>80%): increase by 30-50%  (factor 1.3-1.5)
        - Deep dependency chain: add cascade delay per level
        - SPOF status: increase by 100%  (factor 2.0)
        """
        mttr = base_mttr

        # --- Reductions ---
        if component.replicas > 1:
            # More replicas -> more reduction (up to 80% reduction at 5+ replicas).
            replica_factor = max(0.2, 0.4 - 0.05 * (component.replicas - 2))
            mttr *= replica_factor

        if component.failover.enabled:
            # Failover reduces MTTR by 50-70%.
            mttr *= 0.3

        if component.autoscaling.enabled:
            # Autoscaling reduces MTTR by 40-60%.
            mttr *= 0.4

        # --- Increases ---
        utilisation = component.utilization()
        if utilisation > 80.0:
            # Recovery under load is harder.
            load_penalty = 1.3 + 0.2 * min(1.0, (utilisation - 80.0) / 20.0)
            mttr *= load_penalty

        # Dependency chain depth adds cascade delay.
        depth = _dependency_depth(component.id, graph)
        if depth > 0:
            mttr += depth * _CASCADE_DELAY_PER_LEVEL

        # SPOF: single replica with dependents but no failover.
        if component.replicas <= 1 and not component.failover.enabled:
            dependents = graph.get_dependents(component.id)
            if dependents:
                mttr *= 2.0

        # Never return negative.
        return max(0.0, mttr)

    # ------------------------------------------------------------------
    # Recovery steps & bottlenecks
    # ------------------------------------------------------------------

    @staticmethod
    def _build_recovery_steps(
        component: Component, graph: InfraGraph
    ) -> list[RecoveryStep]:
        """Build the concrete recovery steps for *component*."""
        steps: list[RecoveryStep] = []
        comp_name = component.name

        # Step 1: Detection / alerting.
        steps.append(RecoveryStep(
            component_name=comp_name,
            action="Detect failure via health-check / monitoring",
            estimated_minutes=1.0,
            can_parallelize=True,
        ))

        # Step 2: Automated or manual failover / restart.
        if component.failover.enabled:
            steps.append(RecoveryStep(
                component_name=comp_name,
                action="Automatic failover to standby replica",
                estimated_minutes=component.failover.promotion_time_seconds / 60.0,
                can_parallelize=False,
                dependencies=["Detect failure via health-check / monitoring"],
            ))
        elif component.autoscaling.enabled:
            steps.append(RecoveryStep(
                component_name=comp_name,
                action="Autoscaler provisions replacement instance",
                estimated_minutes=component.autoscaling.scale_up_delay_seconds / 60.0,
                can_parallelize=False,
                dependencies=["Detect failure via health-check / monitoring"],
            ))
        else:
            steps.append(RecoveryStep(
                component_name=comp_name,
                action="Manual restart / reprovisioning",
                estimated_minutes=15.0,
                can_parallelize=False,
                dependencies=["Detect failure via health-check / monitoring"],
            ))

        # Step 3: Type-specific warm-up.
        if component.type == ComponentType.DATABASE:
            steps.append(RecoveryStep(
                component_name=comp_name,
                action="Database consistency check and WAL replay",
                estimated_minutes=10.0,
                can_parallelize=False,
                dependencies=[steps[-1].action],
            ))
        elif component.type == ComponentType.CACHE:
            warm_duration = component.cache_warming.warm_duration_seconds / 60.0
            if warm_duration <= 0:
                warm_duration = 5.0
            steps.append(RecoveryStep(
                component_name=comp_name,
                action="Cache warm-up (rebuild hot keys)",
                estimated_minutes=warm_duration,
                can_parallelize=True,
            ))

        # Step 4: Verify health.
        steps.append(RecoveryStep(
            component_name=comp_name,
            action="Verify component health and reconnect dependents",
            estimated_minutes=2.0,
            can_parallelize=True,
            dependencies=[steps[-1].action],
        ))

        return steps

    @staticmethod
    def _identify_component_bottlenecks(
        component: Component, graph: InfraGraph
    ) -> list[str]:
        """Identify factors that make recovery slow for *component*."""
        bottlenecks: list[str] = []

        if component.replicas <= 1 and not component.failover.enabled:
            bottlenecks.append("Single point of failure with no failover")

        if component.utilization() > 80.0:
            bottlenecks.append(
                f"High utilisation ({component.utilization():.0f}%) slows recovery"
            )

        depth = _dependency_depth(component.id, graph)
        if depth >= 3:
            bottlenecks.append(
                f"Deep dependency chain (depth={depth}) adds cascade delay"
            )

        if component.type == ComponentType.DATABASE and component.replicas <= 1:
            bottlenecks.append(
                "Database without replica requires full manual recovery"
            )

        if component.type == ComponentType.STORAGE:
            bottlenecks.append("Storage recovery may require data restore from backup")

        return bottlenecks

    @staticmethod
    def _generate_suggestions(
        component: Component, current_mttr: float, graph: InfraGraph
    ) -> list[str]:
        """Generate improvement suggestions for *component*."""
        suggestions: list[str] = []

        if component.replicas <= 1:
            suggestions.append(
                "Add replicas to enable automatic failover and reduce MTTR by 60-80%"
            )

        if not component.failover.enabled and component.replicas > 1:
            suggestions.append(
                "Enable failover configuration to reduce MTTR by 50-70%"
            )

        if not component.autoscaling.enabled:
            suggestions.append(
                "Enable autoscaling for faster recovery under load"
            )

        if component.type == ComponentType.CACHE and not component.cache_warming.enabled:
            suggestions.append(
                "Enable cache warming to reduce post-recovery performance degradation"
            )

        if component.type == ComponentType.DATABASE and not component.security.backup_enabled:
            suggestions.append(
                "Enable database backups to reduce worst-case recovery time"
            )

        return suggestions

    # ------------------------------------------------------------------
    # Tier classification
    # ------------------------------------------------------------------

    @staticmethod
    def _classify_tiers(
        recoveries: list[ComponentRecovery],
    ) -> dict[str, list[str]]:
        """Classify components into recovery tiers based on their MTTR.

        Tiers
        -----
        - fast: < 5 minutes
        - moderate: 5-30 minutes
        - slow: 30-120 minutes
        - critical: > 120 minutes
        """
        tiers: dict[str, list[str]] = {
            "fast": [],
            "moderate": [],
            "slow": [],
            "critical": [],
        }
        for cr in recoveries:
            if cr.estimated_mttr_minutes < 5.0:
                tiers["fast"].append(cr.component_id)
            elif cr.estimated_mttr_minutes < 30.0:
                tiers["moderate"].append(cr.component_id)
            elif cr.estimated_mttr_minutes < 120.0:
                tiers["slow"].append(cr.component_id)
            else:
                tiers["critical"].append(cr.component_id)
        return tiers

    # ------------------------------------------------------------------
    # Bottleneck identification (report-level)
    # ------------------------------------------------------------------

    @staticmethod
    def _identify_bottlenecks(
        recoveries: list[ComponentRecovery], graph: InfraGraph
    ) -> list[str]:
        """Identify components whose recovery time is disproportionately high.

        A component is considered a bottleneck if:
        - Its MTTR is in the top quartile **and**
        - It has at least one dependent component.
        """
        if not recoveries:
            return []

        sorted_by_mttr = sorted(
            recoveries, key=lambda cr: cr.estimated_mttr_minutes, reverse=True,
        )
        # Top-quartile threshold.
        q75_idx = max(1, len(sorted_by_mttr) // 4)
        bottlenecks: list[str] = []
        for cr in sorted_by_mttr[:q75_idx]:
            dependents = graph.get_dependents(cr.component_id)
            if dependents:
                bottlenecks.append(cr.component_id)
        # Also include any component with MTTR > 60 min regardless.
        for cr in sorted_by_mttr:
            if cr.estimated_mttr_minutes > 60.0 and cr.component_id not in bottlenecks:
                bottlenecks.append(cr.component_id)
        return bottlenecks

    # ------------------------------------------------------------------
    # Scenario recovery helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_affected_ids(
        scenario_result: ScenarioResult, graph: InfraGraph
    ) -> list[str]:
        """Extract the set of affected component IDs from a scenario result."""
        affected: set[str] = set()

        # Faults directly target components.
        for fault in scenario_result.scenario.faults:
            target_id = fault.target_component_id
            # Only include targets that exist in the graph.
            if graph.get_component(target_id) is None:
                continue
            affected.add(target_id)
            # Transitively affected via dependency graph.
            affected |= graph.get_all_affected(target_id)

        return sorted(affected)

    @staticmethod
    def _build_parallel_groups(
        affected_ids: list[str], graph: InfraGraph
    ) -> list[list[str]]:
        """Build parallel recovery groups from affected components.

        Components that share no dependency relationship can be recovered
        simultaneously.  The groups are ordered so that leaf-level
        dependencies (e.g. databases) are recovered first, then their
        dependents.

        The algorithm performs a topological sort on the sub-graph of
        affected components to produce recovery layers.
        """
        if not affected_ids:
            return []

        affected_set = set(affected_ids)

        # Build an adjacency structure restricted to affected components.
        # "depends on" edges within the affected set.
        in_degree: dict[str, int] = {cid: 0 for cid in affected_ids}
        dependents_map: dict[str, list[str]] = {cid: [] for cid in affected_ids}

        for cid in affected_ids:
            deps = graph.get_dependencies(cid)
            for dep_comp in deps:
                if dep_comp.id in affected_set:
                    in_degree[cid] += 1
                    dependents_map[dep_comp.id].append(cid)

        # Kahn's algorithm for topological layers.
        groups: list[list[str]] = []
        queue = deque(
            cid for cid, deg in in_degree.items() if deg == 0
        )
        while queue:
            layer: list[str] = []
            next_queue: deque[str] = deque()
            while queue:
                node = queue.popleft()
                layer.append(node)
                for dependent in dependents_map.get(node, []):
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0:
                        next_queue.append(dependent)
            if layer:
                groups.append(sorted(layer))
            queue = next_queue

        # Handle cycles: any remaining nodes form their own group.
        remaining = [
            cid for cid, deg in in_degree.items()
            if deg > 0 and cid not in {c for g in groups for c in g}
        ]
        if remaining:
            groups.append(sorted(remaining))

        return groups

    @staticmethod
    def _build_scenario_recovery_steps(
        parallel_groups: list[list[str]],
        mttr_map: dict[str, float],
        graph: InfraGraph,
    ) -> list[RecoveryStep]:
        """Build a flat recovery step sequence from parallel groups."""
        steps: list[RecoveryStep] = []
        prev_group_names: list[str] = []

        for group in parallel_groups:
            group_names: list[str] = []
            for cid in group:
                comp = graph.get_component(cid)
                comp_name = comp.name if comp else cid
                group_names.append(comp_name)
                can_parallel = len(group) > 1
                steps.append(RecoveryStep(
                    component_name=comp_name,
                    action=f"Recover {comp_name}",
                    estimated_minutes=mttr_map.get(cid, 30.0),
                    can_parallelize=can_parallel,
                    dependencies=list(prev_group_names),
                ))
            prev_group_names = group_names

        return steps

    @staticmethod
    def _calculate_critical_path(
        parallel_groups: list[list[str]],
        mttr_map: dict[str, float],
    ) -> float:
        """Calculate the critical path length through the recovery groups.

        Within each group, components recover in parallel so only the
        slowest component counts.  Groups are sequential, so their maxima
        are summed.
        """
        total = 0.0
        for group in parallel_groups:
            group_max = max(
                (mttr_map.get(cid, 30.0) for cid in group),
                default=0.0,
            )
            total += group_max
        return total

    # ------------------------------------------------------------------
    # Roadmap improvements
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_improvements(
        component: Component,
        recovery: ComponentRecovery,
        graph: InfraGraph,
    ) -> list[RecoveryImprovement]:
        """Generate concrete improvement recommendations for *component*."""
        improvements: list[RecoveryImprovement] = []
        current = recovery.estimated_mttr_minutes

        if current <= 0.0:
            return improvements

        # 1. Add replicas.
        if component.replicas <= 1:
            improved = current * 0.3  # ~70% reduction
            improvements.append(RecoveryImprovement(
                component_name=component.name,
                current_mttr=current,
                improved_mttr=round(improved, 2),
                improvement_action="Add replica (replicas >= 2)",
                effort="medium",
                impact_score=round(min(100.0, (current - improved) / current * 100), 2),
            ))

        # 2. Enable failover.
        if not component.failover.enabled:
            factor = 0.3  # 70% reduction
            improved = current * factor
            improvements.append(RecoveryImprovement(
                component_name=component.name,
                current_mttr=current,
                improved_mttr=round(improved, 2),
                improvement_action="Enable failover configuration",
                effort="medium",
                impact_score=round(min(100.0, (current - improved) / current * 100), 2),
            ))

        # 3. Enable autoscaling.
        if not component.autoscaling.enabled:
            factor = 0.4  # 60% reduction
            improved = current * factor
            improvements.append(RecoveryImprovement(
                component_name=component.name,
                current_mttr=current,
                improved_mttr=round(improved, 2),
                improvement_action="Enable autoscaling",
                effort="low",
                impact_score=round(min(100.0, (current - improved) / current * 100), 2),
            ))

        # 4. Reduce utilisation headroom.
        if component.utilization() > 80.0:
            # Removing the high-utilisation penalty.
            improved = current / 1.4  # approximate
            improvements.append(RecoveryImprovement(
                component_name=component.name,
                current_mttr=current,
                improved_mttr=round(improved, 2),
                improvement_action="Reduce utilisation below 80% (scale up or optimise)",
                effort="medium",
                impact_score=round(min(100.0, (current - improved) / current * 100), 2),
            ))

        # 5. Database-specific: add backup.
        if (
            component.type == ComponentType.DATABASE
            and not component.security.backup_enabled
        ):
            improved = current * 0.6
            improvements.append(RecoveryImprovement(
                component_name=component.name,
                current_mttr=current,
                improved_mttr=round(improved, 2),
                improvement_action="Enable automated database backups",
                effort="low",
                impact_score=round(min(100.0, (current - improved) / current * 100), 2),
            ))

        return improvements


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _dependency_depth(component_id: str, graph: InfraGraph) -> int:
    """Calculate the longest dependency chain depth from *component_id*.

    The depth counts how many levels of downstream dependencies exist.
    A leaf component has depth 0.
    """
    visited: set[str] = set()
    return _dfs_depth(component_id, graph, visited)


def _dfs_depth(
    component_id: str, graph: InfraGraph, visited: set[str]
) -> int:
    """Depth-first search to find the longest path from *component_id*."""
    if component_id in visited:
        return 0  # Cycle guard.

    # Component must exist in the graph for dependency lookup.
    if graph.get_component(component_id) is None:
        return 0

    visited.add(component_id)

    dependencies = graph.get_dependencies(component_id)
    if not dependencies:
        visited.discard(component_id)
        return 0

    max_depth = 0
    for dep in dependencies:
        d = 1 + _dfs_depth(dep.id, graph, visited)
        max_depth = max(max_depth, d)

    visited.discard(component_id)
    return max_depth
