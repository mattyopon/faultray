# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Chaos blast radius predictor.

Predicts the cascading impact of component failures before they occur,
using graph topology analysis, dependency criticality scoring, and
historical incident correlation to estimate blast radius with confidence intervals.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum

from faultray.model.components import ComponentType
from faultray.model.graph import InfraGraph


class ImpactSeverity(str, Enum):
    """Severity of impact on a component from a failure."""

    TOTAL_OUTAGE = "total_outage"  # Service completely unavailable
    MAJOR_DEGRADATION = "major_degradation"  # >50% capacity loss
    MINOR_DEGRADATION = "minor_degradation"  # <50% capacity loss
    NEGLIGIBLE = "negligible"  # No user-visible impact


@dataclass
class AffectedComponent:
    """A component affected by a predicted failure."""

    component_id: str
    component_name: str
    impact_severity: ImpactSeverity
    propagation_depth: int  # How many hops from failed component
    time_to_impact_seconds: float  # Estimated time before impact hits
    has_circuit_breaker: bool
    has_failover: bool
    mitigated: bool  # True if circuit breaker/failover would prevent impact


@dataclass
class BlastRadiusPrediction:
    """Complete prediction of a component failure's blast radius."""

    failed_component_id: str
    failed_component_name: str
    total_affected: int
    mitigated_count: int  # Components protected by circuit breakers/failover
    unmitigated_count: int
    affected_components: list[AffectedComponent] = field(default_factory=list)
    severity_distribution: dict[str, int] = field(default_factory=dict)
    estimated_user_impact_percent: float = 0.0  # 0-100
    estimated_revenue_impact_percent: float = 0.0  # 0-100 based on component criticality
    confidence: float = 0.0  # 0-1.0
    propagation_paths: list[list[str]] = field(default_factory=list)
    critical_path: list[str] = field(default_factory=list)
    mttr_estimate_minutes: float = 0.0  # Mean time to recovery estimate


@dataclass
class BlastRadiusComparison:
    """Comparison of blast radius predictions across multiple components."""

    predictions: list[BlastRadiusPrediction] = field(default_factory=list)
    most_dangerous_component: str = ""
    safest_component: str = ""
    risk_ranking: list[tuple[str, float]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Seconds of propagation delay per hop
_PROPAGATION_DELAY_PER_HOP = 15.0

# Maximum BFS depth to prevent infinite loops
_MAX_BFS_DEPTH = 50

# User-facing component types (failures here directly affect users)
_USER_FACING_TYPES = frozenset(
    {
        ComponentType.LOAD_BALANCER,
        ComponentType.DNS,
        ComponentType.WEB_SERVER,
    }
)

# Component types with high revenue criticality
_REVENUE_CRITICAL_TYPES = frozenset(
    {
        ComponentType.DATABASE,
        ComponentType.APP_SERVER,
        ComponentType.LOAD_BALANCER,
        ComponentType.WEB_SERVER,
    }
)


class BlastRadiusPredictor:
    """Predicts the blast radius of component failures before they occur.

    Uses BFS/DFS traversal on the dependency graph to trace failure
    propagation paths, estimate severity, and compute confidence intervals
    for the predicted blast radius.
    """

    def __init__(self, graph: InfraGraph) -> None:
        self.graph = graph

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def predict(self, component_id: str) -> BlastRadiusPrediction:
        """Predict the blast radius for a single component failure.

        Args:
            component_id: ID of the component whose failure to predict.

        Returns:
            A BlastRadiusPrediction with full impact analysis.
        """
        comp = self.graph.get_component(component_id)
        if comp is None:
            return BlastRadiusPrediction(
                failed_component_id=component_id,
                failed_component_name="unknown",
                total_affected=0,
                mitigated_count=0,
                unmitigated_count=0,
            )

        # Trace propagation via BFS
        affected = self._trace_propagation(component_id)

        # Find propagation paths
        propagation_paths = self._find_propagation_paths(component_id)

        # Determine critical path (longest unmitigated path)
        critical_path = self._find_critical_path(propagation_paths, affected)

        # Calculate counts
        mitigated_count = sum(1 for a in affected if a.mitigated)
        unmitigated_count = len(affected) - mitigated_count

        # Build severity distribution
        severity_dist: dict[str, int] = {s.value: 0 for s in ImpactSeverity}
        for a in affected:
            severity_dist[a.impact_severity.value] += 1

        # Estimate user and revenue impact
        user_impact = self._estimate_user_impact(affected)
        revenue_impact = self._estimate_revenue_impact(affected)

        # Calculate confidence
        confidence = self._calculate_confidence()

        # Estimate MTTR
        mttr = self._estimate_mttr(affected)

        return BlastRadiusPrediction(
            failed_component_id=component_id,
            failed_component_name=comp.name,
            total_affected=len(affected),
            mitigated_count=mitigated_count,
            unmitigated_count=unmitigated_count,
            affected_components=affected,
            severity_distribution=severity_dist,
            estimated_user_impact_percent=round(user_impact, 2),
            estimated_revenue_impact_percent=round(revenue_impact, 2),
            confidence=round(confidence, 4),
            propagation_paths=propagation_paths,
            critical_path=critical_path,
            mttr_estimate_minutes=round(mttr, 1),
        )

    def predict_all(self) -> BlastRadiusComparison:
        """Predict blast radius for every component and rank them.

        Returns:
            A BlastRadiusComparison with all predictions and risk ranking.
        """
        component_ids = list(self.graph.components.keys())
        return self.compare(component_ids)

    def compare(self, component_ids: list[str]) -> BlastRadiusComparison:
        """Compare blast radius predictions for a subset of components.

        Args:
            component_ids: List of component IDs to compare.

        Returns:
            A BlastRadiusComparison with predictions sorted by risk.
        """
        if not component_ids:
            return BlastRadiusComparison()

        predictions: list[BlastRadiusPrediction] = []
        for cid in component_ids:
            predictions.append(self.predict(cid))

        # Calculate risk score for each prediction
        risk_ranking: list[tuple[str, float]] = []
        for pred in predictions:
            risk_score = self._compute_risk_score(pred)
            risk_ranking.append((pred.failed_component_id, round(risk_score, 2)))

        # Sort by risk score descending
        risk_ranking.sort(key=lambda x: x[1], reverse=True)

        most_dangerous = risk_ranking[0][0] if risk_ranking else ""
        safest = risk_ranking[-1][0] if risk_ranking else ""

        return BlastRadiusComparison(
            predictions=predictions,
            most_dangerous_component=most_dangerous,
            safest_component=safest,
            risk_ranking=risk_ranking,
        )

    # ------------------------------------------------------------------
    # Private: propagation tracing
    # ------------------------------------------------------------------

    def _trace_propagation(self, component_id: str) -> list[AffectedComponent]:
        """BFS traversal to find all components affected by a failure.

        Traverses upstream through dependents (components that depend ON
        the failed component), computing severity based on depth, dependency
        type, and mitigation status.
        """
        affected: list[AffectedComponent] = []
        visited: set[str] = {component_id}

        # Queue entries: (component_id, depth)
        queue: deque[tuple[str, int]] = deque()

        # Seed with direct dependents
        for dep_comp in self.graph.get_dependents(component_id):
            if dep_comp.id not in visited:
                queue.append((dep_comp.id, 1))
                visited.add(dep_comp.id)

        while queue:
            comp_id, depth = queue.popleft()
            if depth > _MAX_BFS_DEPTH:
                continue

            comp = self.graph.get_component(comp_id)
            if comp is None:
                continue

            # Check if there's a dependency edge from comp to the source
            # (or to any of the components already known to be affected)
            # For the first level, the source is the failed component.
            # For deeper levels, we need to find which edge brought us here.
            # We look at which visited predecessor this component depends on.
            dependency_edge = self._find_incoming_edge(comp_id, visited)

            has_cb = False
            has_failover = comp.failover.enabled

            if dependency_edge is not None:
                has_cb = dependency_edge.circuit_breaker.enabled

            mitigated = self._is_mitigated(comp, dependency_edge)

            severity = self._estimate_severity(comp, depth)

            time_to_impact = depth * _PROPAGATION_DELAY_PER_HOP

            affected.append(
                AffectedComponent(
                    component_id=comp_id,
                    component_name=comp.name,
                    impact_severity=severity,
                    propagation_depth=depth,
                    time_to_impact_seconds=time_to_impact,
                    has_circuit_breaker=has_cb,
                    has_failover=has_failover,
                    mitigated=mitigated,
                )
            )

            # Continue propagation unless mitigated
            if not mitigated:
                for next_dep in self.graph.get_dependents(comp_id):
                    if next_dep.id not in visited:
                        queue.append((next_dep.id, depth + 1))
                        visited.add(next_dep.id)

        return affected

    def _find_incoming_edge(self, comp_id: str, visited: set[str]):
        """Find the dependency edge from comp_id to any visited predecessor.

        Returns the Dependency object or None.
        """
        # The component depends on some target in visited.
        # In the graph, an edge from comp_id -> target means comp_id depends on target.
        deps = self.graph.get_dependencies(comp_id)
        for dep_comp in deps:
            if dep_comp.id in visited:
                edge = self.graph.get_dependency_edge(comp_id, dep_comp.id)
                if edge is not None:
                    return edge
        return None

    def _find_propagation_paths(self, source_id: str) -> list[list[str]]:
        """Find all failure propagation paths from the source component.

        Uses DFS to enumerate paths through the dependency graph
        (traversing upstream through dependents).
        """
        paths: list[list[str]] = []
        self._dfs_paths(source_id, [source_id], set(), paths)
        return paths

    def _dfs_paths(
        self,
        current_id: str,
        current_path: list[str],
        visited: set[str],
        all_paths: list[list[str]],
    ) -> None:
        """DFS helper to enumerate all propagation paths."""
        visited.add(current_id)
        dependents = self.graph.get_dependents(current_id)

        if not dependents or all(d.id in visited for d in dependents):
            # Leaf of propagation -- record path if it has more than just source
            if len(current_path) > 1:
                all_paths.append(list(current_path))
        else:
            for dep in dependents:
                if dep.id not in visited:
                    current_path.append(dep.id)
                    self._dfs_paths(dep.id, current_path, visited, all_paths)
                    current_path.pop()

            # Also record the current path if it's non-trivial
            # (handles fan-out where some branches are visited)
            if len(current_path) > 1 and current_path not in all_paths:
                all_paths.append(list(current_path))

        visited.discard(current_id)

    def _find_critical_path(
        self,
        paths: list[list[str]],
        affected: list[AffectedComponent],
    ) -> list[str]:
        """Find the most damaging propagation path.

        The critical path is the longest path where the most components
        are unmitigated, weighted by severity.
        """
        if not paths:
            return []

        mitigated_ids = {a.component_id for a in affected if a.mitigated}

        best_path: list[str] = []
        best_score = -1.0

        for path in paths:
            # Score = number of unmitigated components * path length
            unmitigated_in_path = sum(
                1 for cid in path if cid not in mitigated_ids
            )
            score = unmitigated_in_path * len(path)
            if score > best_score:
                best_score = score
                best_path = path

        return best_path

    # ------------------------------------------------------------------
    # Private: severity estimation
    # ------------------------------------------------------------------

    def _estimate_severity(self, comp, depth: int) -> ImpactSeverity:
        """Estimate the impact severity on a component based on depth and type.

        Deeper components get less severe impact (propagation weakens).
        Components with higher redundancy get less severe impact.
        """
        # Base severity from depth
        if depth <= 1:
            base = ImpactSeverity.TOTAL_OUTAGE
        elif depth <= 2:
            base = ImpactSeverity.MAJOR_DEGRADATION
        elif depth <= 4:
            base = ImpactSeverity.MINOR_DEGRADATION
        else:
            base = ImpactSeverity.NEGLIGIBLE

        # Reduce severity if component has redundancy
        if comp.replicas >= 3:
            base = self._reduce_severity(base, 2)
        elif comp.replicas >= 2:
            base = self._reduce_severity(base, 1)

        # Reduce severity if failover is enabled
        if comp.failover.enabled:
            base = self._reduce_severity(base, 1)

        return base

    @staticmethod
    def _reduce_severity(severity: ImpactSeverity, levels: int) -> ImpactSeverity:
        """Reduce severity by the given number of levels."""
        order = [
            ImpactSeverity.TOTAL_OUTAGE,
            ImpactSeverity.MAJOR_DEGRADATION,
            ImpactSeverity.MINOR_DEGRADATION,
            ImpactSeverity.NEGLIGIBLE,
        ]
        idx = order.index(severity)
        new_idx = min(idx + levels, len(order) - 1)
        return order[new_idx]

    # ------------------------------------------------------------------
    # Private: user / revenue impact estimation
    # ------------------------------------------------------------------

    def _estimate_user_impact(self, affected: list[AffectedComponent]) -> float:
        """Estimate the percentage of users affected by the failure.

        Based on whether user-facing components (LB, DNS, WEB) are in the
        blast radius and whether they are mitigated.
        """
        if not affected:
            return 0.0

        total_components = len(self.graph.components)
        if total_components == 0:
            return 0.0

        user_facing_affected = 0
        user_facing_unmitigated = 0

        for ac in affected:
            comp = self.graph.get_component(ac.component_id)
            if comp is None:
                continue
            if comp.type in _USER_FACING_TYPES:
                user_facing_affected += 1
                if not ac.mitigated:
                    user_facing_unmitigated += 1

        if user_facing_unmitigated > 0:
            # Direct user-facing impact: high percentage
            return min(100.0, user_facing_unmitigated * 40.0)

        if user_facing_affected > 0:
            # Mitigated user-facing impact: moderate percentage
            return min(100.0, user_facing_affected * 10.0)

        # No user-facing components affected, but backend degradation
        # still causes some user impact proportional to blast spread
        unmitigated_count = sum(1 for a in affected if not a.mitigated)
        spread_ratio = unmitigated_count / total_components
        return min(100.0, spread_ratio * 30.0)

    def _estimate_revenue_impact(self, affected: list[AffectedComponent]) -> float:
        """Estimate revenue impact as a percentage based on component criticality.

        Revenue-critical components (DB, app server, LB, web server) contribute
        more to revenue impact.
        """
        if not affected:
            return 0.0

        total_components = len(self.graph.components)
        if total_components == 0:
            return 0.0

        revenue_score = 0.0
        for ac in affected:
            comp = self.graph.get_component(ac.component_id)
            if comp is None:
                continue

            if ac.mitigated:
                weight = 0.1  # Mitigated components contribute minimally
            else:
                weight = 1.0

            if comp.type in _REVENUE_CRITICAL_TYPES:
                revenue_score += 20.0 * weight
            else:
                revenue_score += 5.0 * weight

        return min(100.0, revenue_score)

    # ------------------------------------------------------------------
    # Private: mitigation check
    # ------------------------------------------------------------------

    def _is_mitigated(self, comp, dependency) -> bool:
        """Determine if the impact on a component is mitigated.

        A component is considered mitigated if:
        - The dependency edge has a circuit breaker enabled, OR
        - The component has failover enabled with sufficient replicas
        """
        if dependency is not None and dependency.circuit_breaker.enabled:
            return True

        if comp.failover.enabled and comp.replicas >= 2:
            return True

        return False

    # ------------------------------------------------------------------
    # Private: confidence calculation
    # ------------------------------------------------------------------

    def _calculate_confidence(self) -> float:
        """Calculate prediction confidence based on graph properties.

        Higher confidence when:
        - The graph is well-connected (clear dependency structure)
        - Components have well-defined configurations
        - More edges have explicit weights and types
        """
        components = self.graph.components
        if not components:
            return 0.0

        total_components = len(components)
        if total_components == 1:
            return 1.0

        edges = self.graph.all_dependency_edges()
        total_edges = len(edges)

        # Factor 1: Edge-to-component ratio (well-connected graph)
        # total_components is guaranteed > 1 here (single component returns early above)
        connectivity = min(1.0, total_edges / (total_components - 1))

        # Factor 2: Proportion of edges with explicit weights
        if total_edges > 0:
            explicit_weights = sum(
                1 for e in edges if e.weight != 1.0 or e.dependency_type != "requires"
            )
            # Even default weights provide some info, so base is 0.5
            weight_quality = 0.5 + 0.5 * (explicit_weights / total_edges)
        else:
            weight_quality = 0.5

        # Factor 3: Component configuration completeness
        configured_count = 0
        for comp in components.values():
            has_config = (
                comp.replicas > 1
                or comp.failover.enabled
                or comp.autoscaling.enabled
            )
            if has_config:
                configured_count += 1
        config_ratio = configured_count / total_components

        # Combine factors
        confidence = (connectivity * 0.4 + weight_quality * 0.3 + config_ratio * 0.3)
        return max(0.0, min(1.0, confidence))

    # ------------------------------------------------------------------
    # Private: MTTR estimation
    # ------------------------------------------------------------------

    def _estimate_mttr(self, affected: list[AffectedComponent]) -> float:
        """Estimate Mean Time To Recovery in minutes.

        Based on:
        - Number of affected components (more = longer recovery)
        - Whether components have automation (failover, autoscaling)
        - Depth of cascade (deeper = harder to diagnose)
        """
        if not affected:
            return 0.0

        base_mttr = 15.0  # Base MTTR in minutes for a single component

        # Additional time per affected component
        component_factor = len(affected) * 5.0

        # Reduce MTTR for automated recovery
        automated = sum(
            1 for a in affected
            if a.has_failover or a.has_circuit_breaker
        )
        # len(affected) is guaranteed > 0 here (empty case returns early above)
        automation_ratio = automated / len(affected)

        # Automation reduces recovery time
        automation_discount = automation_ratio * 0.5  # Up to 50% reduction

        # Depth factor: deeper cascades are harder to diagnose
        max_depth = max((a.propagation_depth for a in affected), default=0)
        depth_penalty = max_depth * 3.0  # 3 minutes per depth level

        raw_mttr = base_mttr + component_factor + depth_penalty
        mttr = raw_mttr * (1.0 - automation_discount)

        return max(5.0, mttr)  # Minimum 5 minutes

    # ------------------------------------------------------------------
    # Private: risk score for comparison
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_risk_score(prediction: BlastRadiusPrediction) -> float:
        """Compute a single risk score for ranking predictions.

        Combines:
        - Number of unmitigated affected components
        - Severity distribution
        - User and revenue impact
        """
        severity_weights = {
            ImpactSeverity.TOTAL_OUTAGE.value: 10.0,
            ImpactSeverity.MAJOR_DEGRADATION.value: 5.0,
            ImpactSeverity.MINOR_DEGRADATION.value: 2.0,
            ImpactSeverity.NEGLIGIBLE.value: 0.5,
        }

        severity_score = 0.0
        for sev, count in prediction.severity_distribution.items():
            severity_score += severity_weights.get(sev, 0.0) * count

        impact_score = (
            prediction.estimated_user_impact_percent * 0.5
            + prediction.estimated_revenue_impact_percent * 0.5
        )

        return severity_score + impact_score + prediction.unmitigated_count * 2.0
