"""Chaos Advisor Engine - auto-recommends chaos tests based on graph topology.

Analyzes the infrastructure graph to detect SPOFs, bottleneck components,
missing test patterns, and combination failure risks. Produces a prioritized
list of recommended chaos scenarios.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from itertools import combinations
from typing import Any

import networkx as nx

from faultray.model.components import ComponentType
from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ChaosRecommendation:
    """A single recommended chaos test."""

    priority: str  # "critical", "high", "medium", "low"
    scenario_name: str
    scenario_id: str
    reasoning: str
    risk_if_untested: str
    estimated_blast_radius: int
    target_components: list[str] = field(default_factory=list)


@dataclass
class AdvisorReport:
    """Full advisor analysis report."""

    recommendations: list[ChaosRecommendation] = field(default_factory=list)
    total_recommendations: int = 0
    critical_count: int = 0
    coverage_score: float = 0.0  # 0-100, how well current tests cover risks
    topology_insights: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Fault-type mapping per component type (expected coverage)
# ---------------------------------------------------------------------------

_EXPECTED_FAULT_TYPES: dict[str, list[str]] = {
    ComponentType.DATABASE.value: [
        "connection_pool_exhaustion",
        "disk_full",
        "latency_spike",
        "component_down",
    ],
    ComponentType.CACHE.value: [
        "component_down",
        "memory_exhaustion",
        "connection_pool_exhaustion",
    ],
    ComponentType.APP_SERVER.value: [
        "cpu_saturation",
        "memory_exhaustion",
        "component_down",
    ],
    ComponentType.WEB_SERVER.value: [
        "cpu_saturation",
        "component_down",
        "latency_spike",
    ],
    ComponentType.LOAD_BALANCER.value: [
        "component_down",
        "latency_spike",
    ],
    ComponentType.QUEUE.value: [
        "disk_full",
        "component_down",
        "latency_spike",
    ],
    ComponentType.STORAGE.value: [
        "disk_full",
        "component_down",
    ],
    ComponentType.DNS.value: [
        "component_down",
        "latency_spike",
    ],
    ComponentType.EXTERNAL_API.value: [
        "component_down",
        "latency_spike",
    ],
}


# ---------------------------------------------------------------------------
# Priority ordering for sorting
# ---------------------------------------------------------------------------

_PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class ChaosAdvisorEngine:
    """Analyzes an InfraGraph and recommends chaos test scenarios.

    Uses networkx graph algorithms to identify:
    - Single points of failure (SPOF)
    - Betweenness centrality bottlenecks
    - Combination failure scenarios for critical components
    - Missing fault-type test coverage per component type
    - Topology insights (density, longest path, most connected)
    """

    def __init__(self, graph: InfraGraph) -> None:
        self.graph = graph

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(self) -> AdvisorReport:
        """Run full topology analysis and return an AdvisorReport."""
        recommendations: list[ChaosRecommendation] = []

        # 1. SPOF detection
        recommendations.extend(self._detect_spofs())

        # 2. Betweenness centrality bottleneck detection
        recommendations.extend(self._detect_bottlenecks())

        # 3. Combination failures for top-3 critical components
        recommendations.extend(self._suggest_combination_failures())

        # 4. Missing fault-type patterns
        recommendations.extend(self._detect_missing_patterns())

        # Sort by priority
        recommendations.sort(
            key=lambda r: (_PRIORITY_ORDER.get(r.priority, 99), -r.estimated_blast_radius)
        )

        # Compute topology insights
        insights = self._compute_topology_insights()

        # Compute coverage score
        coverage = self._compute_coverage_score(recommendations)

        critical_count = sum(1 for r in recommendations if r.priority == "critical")

        return AdvisorReport(
            recommendations=recommendations,
            total_recommendations=len(recommendations),
            critical_count=critical_count,
            coverage_score=coverage,
            topology_insights=insights,
        )

    # ------------------------------------------------------------------
    # Analysis 1: SPOF detection
    # ------------------------------------------------------------------

    def _detect_spofs(self) -> list[ChaosRecommendation]:
        """Detect single points of failure: replicas <= 1 AND dependents > 0."""
        recs: list[ChaosRecommendation] = []
        for comp in self.graph.components.values():
            dependents = self.graph.get_dependents(comp.id)
            if comp.replicas <= 1 and len(dependents) > 0:
                blast_radius = len(self.graph.get_all_affected(comp.id))
                recs.append(ChaosRecommendation(
                    priority="critical",
                    scenario_name=f"SPOF failure: {comp.id}",
                    scenario_id=f"spof-{comp.id}-{uuid.uuid4().hex[:8]}",
                    reasoning=(
                        f"Component '{comp.id}' ({comp.type.value}) has {comp.replicas} replica(s) "
                        f"but {len(dependents)} component(s) depend on it. "
                        f"A single failure would cascade to {blast_radius} downstream component(s)."
                    ),
                    risk_if_untested=(
                        f"Complete outage of {blast_radius + 1} component(s) with no redundancy. "
                        "Service interruption is highly likely."
                    ),
                    estimated_blast_radius=blast_radius,
                    target_components=[comp.id],
                ))
        return recs

    # ------------------------------------------------------------------
    # Analysis 2: Betweenness centrality bottlenecks
    # ------------------------------------------------------------------

    def _detect_bottlenecks(self) -> list[ChaosRecommendation]:
        """Identify bottleneck components via betweenness centrality."""
        recs: list[ChaosRecommendation] = []
        g = self.graph._graph

        if len(g.nodes) < 2:
            return recs

        centrality = nx.betweenness_centrality(g)
        if not centrality:
            return recs

        # Threshold: components with centrality > 0.1 or in top-3
        sorted_nodes = sorted(centrality.items(), key=lambda x: x[1], reverse=True)
        threshold = 0.1

        for node_id, score in sorted_nodes:
            if score < threshold:
                break
            comp = self.graph.get_component(node_id)
            if comp is None:
                continue

            blast_radius = len(self.graph.get_all_affected(node_id))
            # Skip if already covered by SPOF (avoid exact duplicates)
            recs.append(ChaosRecommendation(
                priority="high",
                scenario_name=f"Bottleneck failure: {node_id}",
                scenario_id=f"bottleneck-{node_id}-{uuid.uuid4().hex[:8]}",
                reasoning=(
                    f"Component '{node_id}' has high betweenness centrality "
                    f"({score:.3f}), making it a critical routing point in the "
                    f"dependency graph. Failure would disrupt communication "
                    f"between many components."
                ),
                risk_if_untested=(
                    f"Cascading failures through the dependency graph. "
                    f"Estimated blast radius: {blast_radius} component(s)."
                ),
                estimated_blast_radius=blast_radius,
                target_components=[node_id],
            ))
        return recs

    # ------------------------------------------------------------------
    # Analysis 3: Combination failures for top-3 critical components
    # ------------------------------------------------------------------

    def _suggest_combination_failures(self) -> list[ChaosRecommendation]:
        """Suggest pairwise failure tests for the top-3 most critical components."""
        recs: list[ChaosRecommendation] = []
        g = self.graph._graph

        if len(g.nodes) < 2:
            return recs

        # Rank components by: (number of dependents, blast radius) descending
        ranked: list[tuple[str, int, int]] = []
        for comp_id in self.graph.components:
            dependents = self.graph.get_dependents(comp_id)
            blast = len(self.graph.get_all_affected(comp_id))
            ranked.append((comp_id, len(dependents), blast))
        ranked.sort(key=lambda x: (x[1], x[2]), reverse=True)

        top_n = min(3, len(ranked))
        top_ids = [r[0] for r in ranked[:top_n]]

        for a, b in combinations(top_ids, 2):
            # Compute combined blast radius (union of affected sets)
            affected_a = self.graph.get_all_affected(a)
            affected_b = self.graph.get_all_affected(b)
            combined = affected_a | affected_b | {a, b}
            blast = len(combined) - 2  # exclude the failed components themselves

            recs.append(ChaosRecommendation(
                priority="high",
                scenario_name=f"Combination failure: {a} + {b}",
                scenario_id=f"combo-{a}-{b}-{uuid.uuid4().hex[:8]}",
                reasoning=(
                    f"Both '{a}' and '{b}' are among the most critical components. "
                    f"Testing their simultaneous failure reveals hidden dependencies "
                    f"and verifies that the system can survive compound outages."
                ),
                risk_if_untested=(
                    f"Untested compound failure could take down {blast} additional "
                    f"component(s), potentially causing a full system outage."
                ),
                estimated_blast_radius=blast,
                target_components=[a, b],
            ))
        return recs

    # ------------------------------------------------------------------
    # Analysis 4: Missing fault-type patterns
    # ------------------------------------------------------------------

    def _detect_missing_patterns(self) -> list[ChaosRecommendation]:
        """Check if each component type has appropriate fault types tested."""
        recs: list[ChaosRecommendation] = []

        for comp in self.graph.components.values():
            comp_type = comp.type.value
            expected_faults = _EXPECTED_FAULT_TYPES.get(comp_type, [])

            for fault_type in expected_faults:
                recs.append(ChaosRecommendation(
                    priority="medium",
                    scenario_name=f"Missing test: {fault_type} on {comp.id}",
                    scenario_id=f"missing-{fault_type}-{comp.id}-{uuid.uuid4().hex[:8]}",
                    reasoning=(
                        f"Component '{comp.id}' is of type '{comp_type}', which should "
                        f"be tested for '{fault_type}' failures. This fault type is "
                        f"common for this component category."
                    ),
                    risk_if_untested=(
                        f"A '{fault_type}' event on '{comp.id}' could go undetected "
                        f"during chaos testing, leaving a blind spot in resilience coverage."
                    ),
                    estimated_blast_radius=len(self.graph.get_all_affected(comp.id)),
                    target_components=[comp.id],
                ))
        return recs

    # ------------------------------------------------------------------
    # Topology insights
    # ------------------------------------------------------------------

    def _compute_topology_insights(self) -> dict[str, Any]:
        """Report graph density, longest path, most connected component."""
        g = self.graph._graph
        insights: dict[str, Any] = {}

        num_nodes = g.number_of_nodes()
        num_edges = g.number_of_edges()
        insights["num_nodes"] = num_nodes
        insights["num_edges"] = num_edges

        # Graph density
        if num_nodes > 1:
            insights["density"] = round(nx.density(g), 4)
        else:
            insights["density"] = 0.0

        # Longest path (only meaningful for DAGs)
        try:
            if nx.is_directed_acyclic_graph(g) and num_nodes > 0:
                longest = nx.dag_longest_path(g)
                insights["longest_path"] = longest
                insights["longest_path_length"] = len(longest)
            else:
                insights["longest_path"] = []
                insights["longest_path_length"] = 0
        except Exception:
            insights["longest_path"] = []
            insights["longest_path_length"] = 0

        # Most connected component (by total degree)
        if num_nodes > 0:
            degrees = dict(g.degree())
            most_connected = max(degrees, key=degrees.get)
            insights["most_connected_component"] = most_connected
            insights["most_connected_degree"] = degrees[most_connected]
        else:
            insights["most_connected_component"] = None
            insights["most_connected_degree"] = 0

        # Average degree
        if num_nodes > 0:
            avg_degree = sum(dict(g.degree()).values()) / num_nodes
            insights["average_degree"] = round(avg_degree, 2)
        else:
            insights["average_degree"] = 0.0

        return insights

    # ------------------------------------------------------------------
    # Coverage score
    # ------------------------------------------------------------------

    def _compute_coverage_score(
        self, recommendations: list[ChaosRecommendation]
    ) -> float:
        """Estimate coverage score (0-100).

        Higher score means fewer critical gaps. Penalised by:
        - Critical recommendations: -15 each
        - High recommendations: -8 each
        - Medium recommendations: -3 each
        - Low recommendations: -1 each
        """
        if not recommendations:
            return 100.0

        score = 100.0
        for rec in recommendations:
            if rec.priority == "critical":
                score -= 15
            elif rec.priority == "high":
                score -= 8
            elif rec.priority == "medium":
                score -= 3
            else:
                score -= 1

        return max(0.0, min(100.0, round(score, 1)))
