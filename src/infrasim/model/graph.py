"""Dependency graph for infrastructure components."""

from __future__ import annotations

import json
from collections import deque
from pathlib import Path

import networkx as nx

from .components import Component, ComponentType, Dependency


class InfraGraph:
    """Directed graph of infrastructure components and their dependencies."""

    def __init__(self) -> None:
        self._graph = nx.DiGraph()
        self._components: dict[str, Component] = {}

    @property
    def components(self) -> dict[str, Component]:
        return self._components

    def add_component(self, component: Component) -> None:
        self._components[component.id] = component
        self._graph.add_node(component.id, component=component)

    def add_dependency(self, dep: Dependency) -> None:
        self._graph.add_edge(
            dep.source_id,
            dep.target_id,
            dependency=dep,
        )

    def get_component(self, component_id: str) -> Component | None:
        return self._components.get(component_id)

    def get_dependents(self, component_id: str) -> list[Component]:
        """Get components that depend ON this component (upstream impact)."""
        predecessors = self._graph.predecessors(component_id)
        return [self._components[pid] for pid in predecessors if pid in self._components]

    def get_dependencies(self, component_id: str) -> list[Component]:
        """Get components that this component depends on."""
        successors = self._graph.successors(component_id)
        return [self._components[sid] for sid in successors if sid in self._components]

    def get_dependency_edge(self, source_id: str, target_id: str) -> Dependency | None:
        edge = self._graph.edges.get((source_id, target_id))
        if edge:
            return edge.get("dependency")
        return None

    def all_dependency_edges(self) -> list:
        """Return all dependency edge metadata."""
        edges = []
        for u, v, data in self._graph.edges(data=True):
            if "dependency" in data:
                edges.append(data["dependency"])
        return edges

    def get_cascade_path(self, failed_component_id: str) -> list[list[str]]:
        """Find all downstream paths showing how a failure cascades from the component.

        Returns paths from the failed component to all transitively affected components.
        """
        paths = []
        reverse = self._graph.reverse()
        for node in reverse.nodes:
            if node == failed_component_id:
                continue
            for path in nx.all_simple_paths(
                reverse, failed_component_id, node
            ):
                paths.append(path)
        return paths

    def get_all_affected(self, component_id: str) -> set[str]:
        """Get all components transitively affected by a failure."""
        affected: set[str] = set()
        bfs_queue: deque[str] = deque([component_id])
        while bfs_queue:
            current = bfs_queue.popleft()
            for dep in self.get_dependents(current):
                if dep.id not in affected:
                    affected.add(dep.id)
                    bfs_queue.append(dep.id)
        return affected

    def get_critical_paths(self, max_paths: int = 100) -> list[list[str]]:
        """Find the longest dependency chains (most vulnerable to cascade)."""
        paths = []
        for node in self._graph.nodes:
            if self._graph.in_degree(node) == 0:  # entry points
                for target in self._graph.nodes:
                    if self._graph.out_degree(target) == 0:  # leaf nodes
                        for path in nx.all_simple_paths(self._graph, node, target):
                            paths.append(path)
                            if len(paths) >= max_paths:
                                paths.sort(key=len, reverse=True)
                                return paths
        paths.sort(key=len, reverse=True)
        return paths

    def resilience_score(self) -> float:
        """Calculate overall resilience score (0-100).

        Factors:
        - Single points of failure (weighted by dependency type)
        - Failover and autoscaling reduce SPOF penalty
        - Average utilization headroom
        - Dependency chain depth
        """
        if not self._components:
            return 0.0

        score = 100.0

        # Penalize single points of failure, weighted by dependency type
        for comp in self._components.values():
            dependents = self.get_dependents(comp.id)
            if comp.replicas <= 1 and len(dependents) > 0:
                # Weight by dependency type: requires=1.0, optional=0.3, async=0.1
                weighted_deps = 0.0
                for dep_comp in dependents:
                    edge = self.get_dependency_edge(dep_comp.id, comp.id)
                    if edge:
                        dep_type = edge.dependency_type
                        if dep_type == "requires":
                            weighted_deps += 1.0
                        elif dep_type == "optional":
                            weighted_deps += 0.3
                        else:  # async
                            weighted_deps += 0.1
                    else:
                        weighted_deps += 1.0

                penalty = min(20, weighted_deps * 5)

                # Reduce penalty for components with failover or autoscaling
                if comp.failover.enabled:
                    penalty *= 0.3  # failover greatly reduces SPOF risk
                if comp.autoscaling.enabled:
                    penalty *= 0.5  # autoscaling reduces capacity risk

                score -= penalty

        # Penalize high utilization
        for comp in self._components.values():
            util = comp.utilization()
            if util > 90:
                score -= 15
            elif util > 80:
                score -= 8
            elif util > 70:
                score -= 3

        # Penalize deep dependency chains
        critical_paths = self.get_critical_paths()
        if critical_paths:
            max_depth = len(critical_paths[0])
            if max_depth > 5:
                score -= (max_depth - 5) * 5

        return max(0.0, min(100.0, score))

    def resilience_score_v2(self) -> dict:
        """Enhanced resilience score with detailed breakdown.

        Returns dict with:
        - score: float (0-100)
        - breakdown: dict with per-category scores
        - recommendations: list of improvement suggestions
        """
        if not self._components:
            return {
                "score": 0.0,
                "breakdown": {
                    "redundancy": 0.0,
                    "circuit_breaker_coverage": 0.0,
                    "auto_recovery": 0.0,
                    "dependency_risk": 0.0,
                    "capacity_headroom": 0.0,
                },
                "recommendations": [],
            }

        recommendations: list[str] = []

        # --- 1. Redundancy Score (0-20) ---
        redundancy_scores: list[float] = []
        for comp in self._components.values():
            if comp.replicas >= 2 and comp.failover.enabled:
                # Active-Active: multiple replicas with failover
                redundancy_scores.append(20.0)
            elif comp.replicas >= 2 or comp.failover.enabled:
                # Active-Standby: either replicas or failover but not both
                redundancy_scores.append(15.0)
            else:
                # Single instance, no failover
                redundancy_scores.append(5.0)
                recommendations.append(
                    f"Component '{comp.id}' has no redundancy (replicas=1, no failover). "
                    "Consider adding replicas or enabling failover."
                )
        redundancy = sum(redundancy_scores) / len(redundancy_scores) if redundancy_scores else 0.0

        # --- 2. Circuit Breaker Coverage (0-20) ---
        all_edges = self.all_dependency_edges()
        if all_edges:
            cb_enabled_count = sum(
                1 for edge in all_edges if edge.circuit_breaker.enabled
            )
            cb_ratio = cb_enabled_count / len(all_edges)
            circuit_breaker_coverage = cb_ratio * 20.0
            if cb_ratio < 1.0:
                uncovered = len(all_edges) - cb_enabled_count
                recommendations.append(
                    f"{uncovered} of {len(all_edges)} dependency edges lack circuit breakers. "
                    "Enable circuit breakers to prevent cascade failures."
                )
        else:
            # No dependencies means no risk from missing circuit breakers
            circuit_breaker_coverage = 20.0

        # --- 3. Auto-Recovery Score (0-20) ---
        recovery_scores: list[float] = []
        for comp in self._components.values():
            has_recovery = comp.autoscaling.enabled or comp.failover.enabled
            recovery_scores.append(1.0 if has_recovery else 0.0)
            if not has_recovery:
                recommendations.append(
                    f"Component '{comp.id}' has no auto-recovery (no autoscaling or failover). "
                    "Enable autoscaling or failover for automatic recovery."
                )
        if recovery_scores:
            recovery_ratio = sum(recovery_scores) / len(recovery_scores)
            auto_recovery = recovery_ratio * 20.0
        else:
            auto_recovery = 0.0

        # --- 4. Dependency Risk Score (0-20) ---
        critical_paths = self.get_critical_paths()
        if critical_paths:
            max_depth = len(critical_paths[0])
        else:
            max_depth = 0

        # Score based on inverse of max depth: depth 1 = 20, depth 10+ = 0
        if max_depth <= 1:
            depth_score = 20.0
        elif max_depth >= 10:
            depth_score = 0.0
        else:
            # Linear interpolation: depth 2 -> ~17.8, depth 5 -> ~11.1, depth 9 -> ~2.2
            depth_score = max(0.0, 20.0 * (1.0 - (max_depth - 1) / 9.0))

        # Penalize 'requires' dependencies without alternatives
        requires_without_alt = 0
        for comp in self._components.values():
            deps = self.get_dependencies(comp.id)
            for dep_comp in deps:
                edge = self.get_dependency_edge(comp.id, dep_comp.id)
                if edge and edge.dependency_type == "requires":
                    # Check if the target has replicas or failover
                    if dep_comp.replicas <= 1 and not dep_comp.failover.enabled:
                        requires_without_alt += 1

        if requires_without_alt > 0 and self._components:
            alt_penalty = min(10.0, requires_without_alt * 2.0)
            depth_score = max(0.0, depth_score - alt_penalty)
            recommendations.append(
                f"{requires_without_alt} 'requires' dependencies target components "
                "without redundancy. Add replicas or failover to critical dependencies."
            )

        dependency_risk = depth_score

        # --- 5. Capacity Headroom Score (0-20) ---
        utilizations: list[float] = []
        for comp in self._components.values():
            utilizations.append(comp.utilization())

        if utilizations:
            avg_util = sum(utilizations) / len(utilizations)
            # All < 50% = 20, all > 90% = 0, linear interpolation between
            if avg_util <= 50.0:
                capacity_headroom = 20.0
            elif avg_util >= 90.0:
                capacity_headroom = 0.0
            else:
                capacity_headroom = 20.0 * (1.0 - (avg_util - 50.0) / 40.0)

            for comp in self._components.values():
                util = comp.utilization()
                if util > 80.0:
                    recommendations.append(
                        f"Component '{comp.id}' has high utilization ({util:.0f}%). "
                        "Consider scaling up or enabling autoscaling."
                    )
        else:
            capacity_headroom = 20.0

        # --- Total Score ---
        total_score = redundancy + circuit_breaker_coverage + auto_recovery + dependency_risk + capacity_headroom
        total_score = max(0.0, min(100.0, total_score))

        # Deduplicate recommendations
        seen: set[str] = set()
        unique_recommendations: list[str] = []
        for rec in recommendations:
            if rec not in seen:
                seen.add(rec)
                unique_recommendations.append(rec)

        return {
            "score": round(total_score, 1),
            "breakdown": {
                "redundancy": round(redundancy, 1),
                "circuit_breaker_coverage": round(circuit_breaker_coverage, 1),
                "auto_recovery": round(auto_recovery, 1),
                "dependency_risk": round(dependency_risk, 1),
                "capacity_headroom": round(capacity_headroom, 1),
            },
            "recommendations": unique_recommendations,
        }

    def summary(self) -> dict:
        return {
            "total_components": len(self._components),
            "total_dependencies": self._graph.number_of_edges(),
            "component_types": {
                t.value: sum(
                    1 for c in self._components.values() if c.type == t
                )
                for t in ComponentType
                if any(c.type == t for c in self._components.values())
            },
            "resilience_score": round(self.resilience_score(), 1),
        }

    def to_dict(self) -> dict:
        return {
            "components": [c.model_dump() for c in self._components.values()],
            "dependencies": [
                self._graph.edges[e]["dependency"].model_dump()
                for e in self._graph.edges
                if "dependency" in self._graph.edges[e]
            ],
        }

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_dict(), indent=2, default=str))

    @classmethod
    def load(cls, path: Path) -> InfraGraph:
        data = json.loads(path.read_text())
        graph = cls()
        for c in data["components"]:
            graph.add_component(Component(**c))
        for d in data["dependencies"]:
            graph.add_dependency(Dependency(**d))
        return graph
