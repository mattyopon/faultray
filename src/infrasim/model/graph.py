"""Dependency graph for infrastructure components."""

from __future__ import annotations

import json
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

    def get_cascade_path(self, failed_component_id: str) -> list[list[str]]:
        """Find all paths that could be affected by a component failure.

        Returns paths from the failed component back to all entry points.
        """
        paths = []
        for node in self._graph.nodes:
            if node == failed_component_id:
                continue
            for path in nx.all_simple_paths(
                self._graph, node, failed_component_id
            ):
                paths.append(path)
        return paths

    def get_all_affected(self, component_id: str) -> set[str]:
        """Get all components transitively affected by a failure."""
        affected = set()
        queue = [component_id]
        while queue:
            current = queue.pop(0)
            for dep in self.get_dependents(current):
                if dep.id not in affected:
                    affected.add(dep.id)
                    queue.append(dep.id)
        return affected

    def get_critical_paths(self) -> list[list[str]]:
        """Find the longest dependency chains (most vulnerable to cascade)."""
        paths = []
        for node in self._graph.nodes:
            if self._graph.in_degree(node) == 0:  # entry points
                for target in self._graph.nodes:
                    if self._graph.out_degree(target) == 0:  # leaf nodes
                        for path in nx.all_simple_paths(self._graph, node, target):
                            paths.append(path)
        paths.sort(key=len, reverse=True)
        return paths

    def resilience_score(self) -> float:
        """Calculate overall resilience score (0-100).

        Factors:
        - Single points of failure (components with no replicas and dependents)
        - Average utilization headroom
        - Dependency chain depth
        """
        if not self._components:
            return 0.0

        score = 100.0
        total_components = len(self._components)

        # Penalize single points of failure
        for comp in self._components.values():
            dependents = self.get_dependents(comp.id)
            if comp.replicas <= 1 and len(dependents) > 0:
                penalty = min(20, len(dependents) * 5)
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
