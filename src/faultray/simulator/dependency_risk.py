# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Dependency risk analyzer for infrastructure graphs.

Evaluates the risk of each dependency edge in an infrastructure graph,
identifies critical paths, single points of failure, circular dependencies,
and provides risk mitigation recommendations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import networkx as nx

from faultray.model.components import Dependency, HealthStatus
from faultray.model.graph import InfraGraph


class DependencyRiskLevel(str, Enum):
    """Risk level for a dependency."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    MINIMAL = "minimal"


class CouplingType(str, Enum):
    """Type of coupling between components."""

    TIGHT = "tight"
    LOOSE = "loose"
    ASYNC = "async"
    SYNC = "sync"


@dataclass
class DependencyRisk:
    """Risk assessment for a single dependency edge."""

    source_id: str
    target_id: str
    risk_level: DependencyRiskLevel
    coupling_type: CouplingType
    risk_score: float  # 0-100
    factors: list[str] = field(default_factory=list)
    mitigation: list[str] = field(default_factory=list)


@dataclass
class DependencyRiskReport:
    """Full risk report for the entire dependency graph."""

    risks: list[DependencyRisk]
    overall_risk_score: float
    critical_paths: list[list[str]]
    circular_dependencies: list[list[str]]
    single_point_of_failures: list[str]
    recommendations: list[str]


class DependencyRiskAnalyzer:
    """Analyze dependency risks in an infrastructure graph."""

    def __init__(self) -> None:
        pass

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(self, graph: InfraGraph) -> DependencyRiskReport:
        """Produce a full dependency risk report for *graph*."""

        # Analyze each dependency edge
        risks: list[DependencyRisk] = []
        for dep in graph.all_dependency_edges():
            risk = self.analyze_dependency(graph, dep.source_id, dep.target_id)
            risks.append(risk)

        # Critical paths (longest dependency chains)
        critical_paths = self.find_critical_paths(graph)

        # Circular dependencies
        circular = self._find_circular_dependencies(graph)

        # Single points of failure
        spofs = self.find_spofs(graph)

        # Overall risk score
        if risks:
            overall_risk_score = max(r.risk_score for r in risks)
        else:
            overall_risk_score = 0.0

        # Recommendations
        recommendations = self._build_recommendations(
            risks, critical_paths, circular, spofs, graph,
        )

        return DependencyRiskReport(
            risks=risks,
            overall_risk_score=round(overall_risk_score, 1),
            critical_paths=critical_paths,
            circular_dependencies=circular,
            single_point_of_failures=spofs,
            recommendations=recommendations,
        )

    def analyze_dependency(
        self, graph: InfraGraph, source_id: str, target_id: str,
    ) -> DependencyRisk:
        """Analyze risk of a single dependency edge."""

        dep = graph.get_dependency_edge(source_id, target_id)
        source = graph.get_component(source_id)
        target = graph.get_component(target_id)

        factors: list[str] = []
        mitigation: list[str] = []
        score = 0.0

        # --- Factor: circuit breaker ---
        has_cb = dep is not None and dep.circuit_breaker.enabled
        if not has_cb:
            factors.append("No circuit breaker configured")
            mitigation.append("Enable circuit breaker on this dependency")
            score += 20

        # --- Factor: retry strategy ---
        has_retry = dep is not None and dep.retry_strategy.enabled
        if not has_retry:
            factors.append("No retry strategy configured")
            mitigation.append("Add retry strategy with exponential backoff")
            score += 10

        # --- Factor: target has no replicas ---
        if target is not None and target.replicas <= 1:
            factors.append("Target has no replicas (single instance)")
            mitigation.append("Add replicas to target component")
            score += 15

        # --- Factor: target has no failover ---
        if target is not None and not target.failover.enabled:
            factors.append("Target has no failover configured")
            mitigation.append("Enable failover for target component")
            score += 10

        # --- Factor: tight coupling (sync without timeout) ---
        coupling = self._determine_coupling(dep)
        if coupling == CouplingType.TIGHT:
            factors.append("Tight coupling (synchronous without adequate timeout)")
            mitigation.append(
                "Consider async communication or add timeout/deadline"
            )
            score += 15

        # --- Factor: fan-out ---
        if source is not None:
            source_deps = graph.get_dependencies(source_id)
            if len(source_deps) >= 4:
                factors.append(
                    f"High fan-out: source depends on {len(source_deps)} components"
                )
                mitigation.append(
                    "Reduce fan-out or add bulkhead isolation pattern"
                )
                score += 10

        # --- Factor: dependency type weight ---
        if dep is not None and dep.dependency_type == "requires":
            factors.append("Hard 'requires' dependency")
            score += 10
        elif dep is not None and dep.dependency_type == "optional":
            score += 0  # no extra risk for optional
        # async dep type handled via coupling above

        # --- Factor: target health ---
        if target is not None and target.health != HealthStatus.HEALTHY:
            factors.append(f"Target health is {target.health.value}")
            mitigation.append("Investigate and resolve target health issues")
            score += 10

        score = min(100.0, max(0.0, score))
        risk_level = self._score_to_level(score)

        return DependencyRisk(
            source_id=source_id,
            target_id=target_id,
            risk_level=risk_level,
            coupling_type=coupling,
            risk_score=round(score, 1),
            factors=factors,
            mitigation=mitigation,
        )

    def find_critical_paths(self, graph: InfraGraph) -> list[list[str]]:
        """Find the longest dependency chains in the graph.

        Returns paths sorted by length descending (longest first).
        """
        g = graph._graph  # networkx DiGraph
        if g.number_of_nodes() == 0:
            return []

        # Only look in DAG portions -- if cycles exist we skip them for path
        # finding (cycles are reported separately).
        paths: list[list[str]] = []
        try:
            if nx.is_directed_acyclic_graph(g):
                longest = nx.dag_longest_path(g)
                if len(longest) >= 2:
                    paths.append(longest)
                # Also collect all entry->leaf simple paths
                entries = [n for n in g.nodes if g.in_degree(n) == 0]
                leaves = [n for n in g.nodes if g.out_degree(n) == 0]
                for entry in entries:
                    for leaf in leaves:
                        for p in nx.all_simple_paths(g, entry, leaf):
                            if p not in paths:
                                paths.append(p)
            else:
                # Graph has cycles -- still try to find long simple paths
                entries = [n for n in g.nodes if g.in_degree(n) == 0]
                if not entries:
                    entries = list(g.nodes)
                leaves = [n for n in g.nodes if g.out_degree(n) == 0]
                if not leaves:
                    leaves = list(g.nodes)
                for entry in entries:
                    for leaf in leaves:
                        if entry == leaf:
                            continue
                        try:
                            for p in nx.all_simple_paths(g, entry, leaf):
                                if p not in paths:
                                    paths.append(p)
                        except nx.NetworkXError:
                            continue
        except nx.NetworkXError:
            pass

        # Deduplicate, filter out trivial single-node paths, sort by length
        seen: set[tuple[str, ...]] = set()
        unique: list[list[str]] = []
        for p in paths:
            if len(p) < 2:
                continue
            key = tuple(p)
            if key not in seen:
                seen.add(key)
                unique.append(p)
        unique.sort(key=len, reverse=True)
        return unique

    def find_spofs(self, graph: InfraGraph) -> list[str]:
        """Find single points of failure.

        A SPOF is a component that:
        - Has at least one dependent (something depends on it)
        - Has replicas <= 1
        - Has failover disabled
        """
        spofs: list[str] = []
        for comp_id, comp in graph.components.items():
            dependents = graph.get_dependents(comp_id)
            if not dependents:
                continue
            if comp.replicas <= 1 and not comp.failover.enabled:
                spofs.append(comp_id)
        return sorted(spofs)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _determine_coupling(self, dep: Dependency | None) -> CouplingType:
        """Determine coupling type from dependency metadata."""
        if dep is None:
            return CouplingType.SYNC

        if dep.dependency_type == "async":
            return CouplingType.ASYNC

        # Synchronous dependency -- check if there are timeouts / circuit
        # breakers that loosen the coupling.
        if dep.circuit_breaker.enabled and dep.retry_strategy.enabled:
            return CouplingType.LOOSE

        # Sync with no protection is tight coupling
        if dep.dependency_type == "requires":
            return CouplingType.TIGHT

        return CouplingType.SYNC

    def _find_circular_dependencies(
        self, graph: InfraGraph,
    ) -> list[list[str]]:
        """Detect circular dependencies using networkx cycle detection."""
        g = graph._graph
        try:
            cycles = list(nx.simple_cycles(g))
            return [list(c) for c in cycles]
        except nx.NetworkXError:
            return []

    @staticmethod
    def _score_to_level(score: float) -> DependencyRiskLevel:
        """Map a numeric risk score to a risk level."""
        if score >= 70:
            return DependencyRiskLevel.CRITICAL
        if score >= 50:
            return DependencyRiskLevel.HIGH
        if score >= 30:
            return DependencyRiskLevel.MEDIUM
        if score >= 15:
            return DependencyRiskLevel.LOW
        return DependencyRiskLevel.MINIMAL

    def _build_recommendations(
        self,
        risks: list[DependencyRisk],
        critical_paths: list[list[str]],
        circular: list[list[str]],
        spofs: list[str],
        graph: InfraGraph,
    ) -> list[str]:
        """Generate actionable recommendations based on analysis results."""
        recs: list[str] = []

        # SPOFs
        if spofs:
            recs.append(
                f"Resolve {len(spofs)} single point(s) of failure: "
                + ", ".join(spofs)
                + ". Add replicas or enable failover."
            )

        # Critical paths
        if critical_paths:
            longest = critical_paths[0]
            if len(longest) >= 4:
                recs.append(
                    f"Longest dependency chain has {len(longest)} components "
                    f"({' -> '.join(longest)}). Consider reducing chain depth."
                )

        # Circular dependencies
        if circular:
            recs.append(
                f"Found {len(circular)} circular dependency cycle(s). "
                "Refactor to break circular dependencies."
            )

        # Missing circuit breakers
        no_cb = [r for r in risks if "No circuit breaker configured" in r.factors]
        if no_cb:
            recs.append(
                f"{len(no_cb)} dependency edge(s) lack circuit breakers. "
                "Enable circuit breakers to prevent cascade failures."
            )

        # Missing retry strategies
        no_retry = [
            r for r in risks if "No retry strategy configured" in r.factors
        ]
        if no_retry:
            recs.append(
                f"{len(no_retry)} dependency edge(s) lack retry strategies. "
                "Add retry with exponential backoff."
            )

        # Fan-out
        fan_out_risks = [r for r in risks if any("fan-out" in f.lower() for f in r.factors)]
        if fan_out_risks:
            sources = {r.source_id for r in fan_out_risks}
            recs.append(
                f"{len(sources)} component(s) have high fan-out. "
                "Add bulkhead isolation or reduce dependencies."
            )

        return recs
