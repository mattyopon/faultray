"""Blast Radius Mapper – maps the complete blast radius of failures.

Traces failure propagation through infrastructure dependency chains,
computing impact levels, categories, probabilities, and containment
scores. Produces structured BlastRadiusMap results with visualization
data and actionable containment recommendations.
"""

from __future__ import annotations

from collections import deque
from enum import Enum

from pydantic import BaseModel, Field, field_validator

from faultray.model.components import Component, ComponentType
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ImpactLevel(str, Enum):
    """Distance-based classification of how a component is affected."""

    DIRECT = "direct"
    FIRST_HOP = "first_hop"
    SECOND_HOP = "second_hop"
    TRANSITIVE = "transitive"
    POTENTIAL = "potential"


class ImpactCategory(str, Enum):
    """Category of impact a failure inflicts on a downstream component."""

    AVAILABILITY = "availability"
    LATENCY = "latency"
    DATA_INTEGRITY = "data_integrity"
    FUNCTIONALITY = "functionality"
    SECURITY = "security"
    COST = "cost"


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class BlastRadiusNode(BaseModel):
    """A single node inside a blast radius map."""

    component_id: str
    impact_level: ImpactLevel
    impact_categories: list[ImpactCategory]
    probability: float = Field(ge=0.0, le=1.0)
    estimated_impact_percent: float = Field(ge=0.0)
    mitigation: str = ""

    @field_validator("probability")
    @classmethod
    def _clamp_probability(cls, v: float) -> float:
        return max(0.0, min(1.0, v))


class BlastRadiusMap(BaseModel):
    """Complete blast radius mapping for a single failure scenario."""

    source_component: str
    failure_type: str
    affected_nodes: list[BlastRadiusNode] = Field(default_factory=list)
    total_affected: int = 0
    max_depth: int = 0
    critical_paths: list[list[str]] = Field(default_factory=list)
    containment_score: float = Field(default=100.0, ge=0.0, le=100.0)
    visualization_data: dict = Field(default_factory=dict)
    recommendations: list[str] = Field(default_factory=list)


class BlastRadiusComparison(BaseModel):
    """Comparison of blast radii across multiple components."""

    maps: list[BlastRadiusMap] = Field(default_factory=list)
    most_impactful: str = ""
    least_impactful: str = ""
    ranking: list[tuple[str, float]] = Field(default_factory=list)


class ContainmentBoundary(BaseModel):
    """A natural containment boundary in the infrastructure graph."""

    boundary_id: str
    components: list[str] = Field(default_factory=list)
    boundary_type: str = ""  # e.g. circuit_breaker, failover, network_segment
    effectiveness: float = Field(default=0.0, ge=0.0, le=1.0)


class ContainmentAction(BaseModel):
    """A recommended action to improve failure containment."""

    action: str
    target_component: str
    priority: str = "medium"  # low, medium, high, critical
    estimated_improvement: float = 0.0  # expected containment score improvement


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_BFS_DEPTH = 50

_FAILURE_TYPE_CATEGORIES: dict[str, list[ImpactCategory]] = {
    "crash": [ImpactCategory.AVAILABILITY],
    "latency": [ImpactCategory.LATENCY],
    "data_corruption": [ImpactCategory.DATA_INTEGRITY, ImpactCategory.AVAILABILITY],
    "security_breach": [ImpactCategory.SECURITY, ImpactCategory.AVAILABILITY],
    "resource_exhaustion": [ImpactCategory.AVAILABILITY, ImpactCategory.LATENCY, ImpactCategory.COST],
    "network_partition": [ImpactCategory.AVAILABILITY, ImpactCategory.LATENCY],
    "dependency_failure": [ImpactCategory.AVAILABILITY, ImpactCategory.FUNCTIONALITY],
    "configuration_error": [ImpactCategory.FUNCTIONALITY, ImpactCategory.AVAILABILITY],
}

_DEPTH_TO_IMPACT_LEVEL: list[tuple[int, ImpactLevel]] = [
    (0, ImpactLevel.DIRECT),
    (1, ImpactLevel.FIRST_HOP),
    (2, ImpactLevel.SECOND_HOP),
]

_COMPONENT_TYPE_WEIGHTS: dict[ComponentType, float] = {
    ComponentType.LOAD_BALANCER: 1.0,
    ComponentType.WEB_SERVER: 0.9,
    ComponentType.APP_SERVER: 0.8,
    ComponentType.DATABASE: 1.0,
    ComponentType.CACHE: 0.5,
    ComponentType.QUEUE: 0.6,
    ComponentType.STORAGE: 0.7,
    ComponentType.DNS: 1.0,
    ComponentType.EXTERNAL_API: 0.4,
    ComponentType.CUSTOM: 0.5,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _depth_to_impact_level(depth: int) -> ImpactLevel:
    """Map BFS depth to an ImpactLevel."""
    for max_depth, level in _DEPTH_TO_IMPACT_LEVEL:
        if depth <= max_depth:
            return level
    return ImpactLevel.TRANSITIVE


def _categories_for_failure(failure_type: str, comp: Component, depth: int) -> list[ImpactCategory]:
    """Determine impact categories based on failure type, component, and depth."""
    base = list(_FAILURE_TYPE_CATEGORIES.get(failure_type, [ImpactCategory.AVAILABILITY]))

    # Deep propagation adds latency even for non-latency failures
    if depth >= 2 and ImpactCategory.LATENCY not in base:
        base.append(ImpactCategory.LATENCY)

    # Database failures always risk data integrity
    if comp.type == ComponentType.DATABASE and ImpactCategory.DATA_INTEGRITY not in base:
        base.append(ImpactCategory.DATA_INTEGRITY)

    # Cost impact for components with high hourly cost
    if comp.cost_profile.hourly_infra_cost > 0 and ImpactCategory.COST not in base:
        base.append(ImpactCategory.COST)

    return base


def _probability_at_depth(depth: int, has_cb: bool, has_failover: bool, dep_weight: float) -> float:
    """Estimate the probability of impact reaching a component at *depth*."""
    # Base probability decays with depth
    base = max(0.05, 1.0 - depth * 0.2)

    # Circuit breaker reduces probability significantly
    if has_cb:
        base *= 0.15

    # Failover reduces probability
    if has_failover:
        base *= 0.3

    # Dependency weight modulates probability
    base *= dep_weight

    return max(0.0, min(1.0, base))


def _impact_percent(depth: int, comp: Component, failure_type: str) -> float:
    """Estimate impact percentage on a component."""
    type_weight = _COMPONENT_TYPE_WEIGHTS.get(comp.type, 0.5)
    depth_decay = max(0.1, 1.0 - depth * 0.15)

    # Failure-type severity multiplier
    severity_mult = {
        "crash": 1.0,
        "data_corruption": 0.9,
        "security_breach": 0.85,
        "resource_exhaustion": 0.7,
        "network_partition": 0.8,
        "latency": 0.5,
        "dependency_failure": 0.6,
        "configuration_error": 0.5,
    }.get(failure_type, 0.6)

    raw = type_weight * depth_decay * severity_mult * 100.0

    # Redundancy reduces impact
    if comp.replicas >= 3:
        raw *= 0.4
    elif comp.replicas >= 2:
        raw *= 0.6

    return round(min(100.0, max(0.0, raw)), 2)


def _mitigation_description(comp: Component, has_cb: bool) -> str:
    """Build a human-readable mitigation description for a component."""
    parts: list[str] = []
    if has_cb:
        parts.append("circuit breaker")
    if comp.failover.enabled:
        parts.append("failover")
    if comp.replicas >= 2:
        parts.append(f"{comp.replicas} replicas")
    if comp.autoscaling.enabled:
        parts.append("autoscaling")
    if not parts:
        return "none"
    return ", ".join(parts)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class BlastRadiusMapperEngine:
    """Maps the complete blast radius of failures through dependency chains."""

    def __init__(self) -> None:
        pass

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def map_blast_radius(
        self,
        graph: InfraGraph,
        component_id: str,
        failure_type: str = "crash",
    ) -> BlastRadiusMap:
        """Map the blast radius of a failure in *component_id*.

        Performs BFS traversal through dependents (components that depend
        on the failed component), computing impact level, categories,
        probability, and estimated impact for every reachable node.
        """
        comp = graph.get_component(component_id)
        if comp is None:
            return BlastRadiusMap(
                source_component=component_id,
                failure_type=failure_type,
            )

        nodes, max_depth = self._bfs_blast(graph, component_id, failure_type)
        critical_paths = self._find_critical_paths(graph, component_id, nodes)
        containment = self._compute_containment_score(graph, component_id, nodes)
        recommendations = self._build_recommendations(graph, component_id, nodes)
        viz = self.generate_visualization_data(
            BlastRadiusMap(
                source_component=component_id,
                failure_type=failure_type,
                affected_nodes=nodes,
                total_affected=len(nodes),
                max_depth=max_depth,
                critical_paths=critical_paths,
                containment_score=containment,
                recommendations=recommendations,
            )
        )

        return BlastRadiusMap(
            source_component=component_id,
            failure_type=failure_type,
            affected_nodes=nodes,
            total_affected=len(nodes),
            max_depth=max_depth,
            critical_paths=critical_paths,
            containment_score=containment,
            visualization_data=viz,
            recommendations=recommendations,
        )

    def compare_blast_radii(
        self,
        graph: InfraGraph,
        component_ids: list[str],
    ) -> BlastRadiusComparison:
        """Compare blast radii for multiple components."""
        if not component_ids:
            return BlastRadiusComparison()

        maps: list[BlastRadiusMap] = []
        for cid in component_ids:
            maps.append(self.map_blast_radius(graph, cid))

        ranking: list[tuple[str, float]] = []
        for bmap in maps:
            score = self.calculate_risk_score(bmap)
            ranking.append((bmap.source_component, round(score, 2)))

        ranking.sort(key=lambda x: x[1], reverse=True)

        most = ranking[0][0] if ranking else ""
        least = ranking[-1][0] if ranking else ""

        return BlastRadiusComparison(
            maps=maps,
            most_impactful=most,
            least_impactful=least,
            ranking=ranking,
        )

    def find_containment_boundaries(
        self,
        graph: InfraGraph,
    ) -> list[ContainmentBoundary]:
        """Identify natural containment boundaries in the graph.

        Boundaries are formed by components with circuit breakers,
        failover, or high redundancy.
        """
        boundaries: list[ContainmentBoundary] = []
        seen_ids: set[str] = set()

        for comp in graph.components.values():
            if comp.id in seen_ids:
                continue

            boundary_type = self._classify_boundary(graph, comp)
            if boundary_type is None:
                continue

            # Collect components behind this boundary
            protected = self._components_behind_boundary(graph, comp)
            effectiveness = self._boundary_effectiveness(comp, boundary_type)

            boundaries.append(
                ContainmentBoundary(
                    boundary_id=f"boundary-{comp.id}",
                    components=[comp.id] + protected,
                    boundary_type=boundary_type,
                    effectiveness=effectiveness,
                )
            )
            seen_ids.add(comp.id)

        return boundaries

    def simulate_progressive_failure(
        self,
        graph: InfraGraph,
        component_id: str,
    ) -> list[BlastRadiusMap]:
        """Simulate progressive failure stages for a component.

        Returns a list of BlastRadiusMaps representing increasing
        severity stages: latency -> resource_exhaustion -> crash.
        """
        stages = ["latency", "resource_exhaustion", "crash"]
        results: list[BlastRadiusMap] = []
        for stage in stages:
            bmap = self.map_blast_radius(graph, component_id, stage)
            results.append(bmap)
        return results

    def calculate_risk_score(self, blast_map: BlastRadiusMap) -> float:
        """Calculate a single risk score (0-100) for a blast radius map.

        Factors: total affected, containment score, max depth,
        average probability, average impact percent.
        """
        if not blast_map.affected_nodes:
            return 0.0

        avg_prob = sum(n.probability for n in blast_map.affected_nodes) / len(
            blast_map.affected_nodes
        )
        avg_impact = sum(n.estimated_impact_percent for n in blast_map.affected_nodes) / len(
            blast_map.affected_nodes
        )

        # Higher affected count -> higher risk
        count_factor = min(1.0, blast_map.total_affected / 10.0)

        # Lower containment -> higher risk
        containment_factor = 1.0 - blast_map.containment_score / 100.0

        # Deeper cascade -> higher risk
        depth_factor = min(1.0, blast_map.max_depth / 5.0)

        raw = (
            count_factor * 25.0
            + containment_factor * 25.0
            + avg_prob * 20.0
            + (avg_impact / 100.0) * 20.0
            + depth_factor * 10.0
        )

        return round(max(0.0, min(100.0, raw)), 2)

    def recommend_containment(
        self,
        blast_map: BlastRadiusMap,
    ) -> list[ContainmentAction]:
        """Recommend containment actions based on a blast radius map."""
        actions: list[ContainmentAction] = []

        for node in blast_map.affected_nodes:
            if node.impact_level == ImpactLevel.DIRECT:
                if node.mitigation == "none":
                    actions.append(
                        ContainmentAction(
                            action="Add circuit breaker",
                            target_component=node.component_id,
                            priority="critical",
                            estimated_improvement=15.0,
                        )
                    )
                    actions.append(
                        ContainmentAction(
                            action="Enable failover",
                            target_component=node.component_id,
                            priority="critical",
                            estimated_improvement=12.0,
                        )
                    )
            elif node.impact_level == ImpactLevel.FIRST_HOP:
                if node.mitigation == "none":
                    actions.append(
                        ContainmentAction(
                            action="Add circuit breaker",
                            target_component=node.component_id,
                            priority="high",
                            estimated_improvement=10.0,
                        )
                    )
            elif node.impact_level in (ImpactLevel.SECOND_HOP, ImpactLevel.TRANSITIVE):
                if node.probability > 0.5 and node.mitigation == "none":
                    actions.append(
                        ContainmentAction(
                            action="Add redundancy",
                            target_component=node.component_id,
                            priority="medium",
                            estimated_improvement=5.0,
                        )
                    )

        # Deduplicate by (action, target)
        seen: set[tuple[str, str]] = set()
        unique: list[ContainmentAction] = []
        for a in actions:
            key = (a.action, a.target_component)
            if key not in seen:
                seen.add(key)
                unique.append(a)

        # Sort by priority
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        unique.sort(key=lambda a: priority_order.get(a.priority, 99))

        return unique

    def generate_visualization_data(self, blast_map: BlastRadiusMap) -> dict:
        """Generate visualization-ready data structure for a blast map."""
        nodes_viz: list[dict] = [
            {
                "id": blast_map.source_component,
                "label": blast_map.source_component,
                "type": "source",
                "depth": 0,
            }
        ]

        edges_viz: list[dict] = []

        for node in blast_map.affected_nodes:
            nodes_viz.append(
                {
                    "id": node.component_id,
                    "label": node.component_id,
                    "type": node.impact_level.value,
                    "depth": self._impact_level_depth(node.impact_level),
                    "probability": node.probability,
                    "impact_percent": node.estimated_impact_percent,
                }
            )
            edges_viz.append(
                {
                    "source": blast_map.source_component,
                    "target": node.component_id,
                    "impact_level": node.impact_level.value,
                }
            )

        return {
            "nodes": nodes_viz,
            "edges": edges_viz,
            "metadata": {
                "source": blast_map.source_component,
                "failure_type": blast_map.failure_type,
                "total_affected": blast_map.total_affected,
                "max_depth": blast_map.max_depth,
                "containment_score": blast_map.containment_score,
            },
        }

    # ------------------------------------------------------------------
    # Private: BFS blast radius
    # ------------------------------------------------------------------

    def _bfs_blast(
        self,
        graph: InfraGraph,
        source_id: str,
        failure_type: str,
    ) -> tuple[list[BlastRadiusNode], int]:
        """BFS to enumerate affected nodes from *source_id*."""
        nodes: list[BlastRadiusNode] = []
        visited: set[str] = {source_id}
        max_depth = 0

        queue: deque[tuple[str, int]] = deque()

        # Seed with direct dependents
        for dep_comp in graph.get_dependents(source_id):
            if dep_comp.id not in visited:
                queue.append((dep_comp.id, 1))
                visited.add(dep_comp.id)

        while queue:
            comp_id, depth = queue.popleft()
            if depth > _MAX_BFS_DEPTH:
                continue

            comp = graph.get_component(comp_id)
            if comp is None:
                continue

            max_depth = max(max_depth, depth)

            # Determine dependency edge properties
            has_cb = False
            dep_weight = 1.0
            edge = self._find_incoming_edge(graph, comp_id, visited)
            if edge is not None:
                has_cb = edge.circuit_breaker.enabled
                dep_weight = edge.weight

            has_failover = comp.failover.enabled

            impact_level = _depth_to_impact_level(depth)
            categories = _categories_for_failure(failure_type, comp, depth)
            prob = _probability_at_depth(depth, has_cb, has_failover, dep_weight)
            impact_pct = _impact_percent(depth, comp, failure_type)
            mitigation = _mitigation_description(comp, has_cb)

            # If mitigated (CB or failover), mark as potential
            if has_cb or (has_failover and comp.replicas >= 2):
                impact_level = ImpactLevel.POTENTIAL

            nodes.append(
                BlastRadiusNode(
                    component_id=comp_id,
                    impact_level=impact_level,
                    impact_categories=categories,
                    probability=round(prob, 4),
                    estimated_impact_percent=impact_pct,
                    mitigation=mitigation,
                )
            )

            # Continue propagation unless fully mitigated
            if not (has_cb and has_failover and comp.replicas >= 2):
                for next_dep in graph.get_dependents(comp_id):
                    if next_dep.id not in visited:
                        queue.append((next_dep.id, depth + 1))
                        visited.add(next_dep.id)

        return nodes, max_depth

    @staticmethod
    def _find_incoming_edge(graph: InfraGraph, comp_id: str, visited: set[str]):
        """Find dependency edge from comp_id to a visited predecessor."""
        deps = graph.get_dependencies(comp_id)
        for dep_comp in deps:
            if dep_comp.id in visited:
                edge = graph.get_dependency_edge(comp_id, dep_comp.id)
                if edge is not None:
                    return edge
        return None

    # ------------------------------------------------------------------
    # Private: critical paths
    # ------------------------------------------------------------------

    def _find_critical_paths(
        self,
        graph: InfraGraph,
        source_id: str,
        nodes: list[BlastRadiusNode],
    ) -> list[list[str]]:
        """Find critical propagation paths (longest unmitigated chains)."""
        if not nodes:
            return []

        affected_ids = {n.component_id for n in nodes}
        paths: list[list[str]] = []
        self._dfs_paths(graph, source_id, [source_id], set(), paths, affected_ids)

        # Sort by length descending, return top paths
        paths.sort(key=len, reverse=True)
        return paths[:10]

    def _dfs_paths(
        self,
        graph: InfraGraph,
        current_id: str,
        current_path: list[str],
        visited: set[str],
        all_paths: list[list[str]],
        affected_ids: set[str],
    ) -> None:
        """DFS to enumerate propagation paths through affected nodes."""
        visited.add(current_id)
        dependents = graph.get_dependents(current_id)
        reachable = [d for d in dependents if d.id not in visited and d.id in affected_ids]

        if not reachable:
            if len(current_path) > 1:
                all_paths.append(list(current_path))
        else:
            for dep in reachable:
                current_path.append(dep.id)
                self._dfs_paths(graph, dep.id, current_path, visited, all_paths, affected_ids)
                current_path.pop()

        visited.discard(current_id)

    # ------------------------------------------------------------------
    # Private: containment score
    # ------------------------------------------------------------------

    def _compute_containment_score(
        self,
        graph: InfraGraph,
        source_id: str,
        nodes: list[BlastRadiusNode],
    ) -> float:
        """Compute containment score (0-100, higher = better contained).

        Based on: ratio of mitigated nodes, circuit breakers present,
        failover coverage, and redundancy.
        """
        total = len(graph.components)
        if total <= 1:
            return 100.0

        if not nodes:
            return 100.0

        # Factor 1: Blast ratio (smaller blast = better containment)
        blast_ratio = len(nodes) / max(total - 1, 1)
        blast_score = (1.0 - blast_ratio) * 40.0

        # Factor 2: Mitigation coverage
        mitigated = sum(
            1 for n in nodes if n.mitigation != "none"
        )
        mitigation_ratio = mitigated / len(nodes) if nodes else 0.0
        mitigation_score = mitigation_ratio * 30.0

        # Factor 3: Average probability (lower = better containment)
        avg_prob = sum(n.probability for n in nodes) / len(nodes)
        prob_score = (1.0 - avg_prob) * 20.0

        # Factor 4: Potential nodes (mitigated) vs direct/first_hop
        potential_count = sum(1 for n in nodes if n.impact_level == ImpactLevel.POTENTIAL)
        potential_ratio = potential_count / len(nodes) if nodes else 0.0
        potential_score = potential_ratio * 10.0

        raw = blast_score + mitigation_score + prob_score + potential_score
        return round(max(0.0, min(100.0, raw)), 2)

    # ------------------------------------------------------------------
    # Private: recommendations
    # ------------------------------------------------------------------

    def _build_recommendations(
        self,
        graph: InfraGraph,
        source_id: str,
        nodes: list[BlastRadiusNode],
    ) -> list[str]:
        """Build actionable recommendations."""
        recs: list[str] = []

        unmitigated_direct = [
            n for n in nodes
            if n.impact_level == ImpactLevel.DIRECT and n.mitigation == "none"
        ]
        unmitigated_first = [
            n for n in nodes
            if n.impact_level == ImpactLevel.FIRST_HOP and n.mitigation == "none"
        ]

        if unmitigated_direct:
            ids = ", ".join(n.component_id for n in unmitigated_direct)
            recs.append(
                f"Add circuit breakers to direct dependents: {ids}"
            )

        if unmitigated_first:
            ids = ", ".join(n.component_id for n in unmitigated_first)
            recs.append(
                f"Enable failover for first-hop components: {ids}"
            )

        high_prob = [n for n in nodes if n.probability > 0.7]
        if high_prob:
            ids = ", ".join(n.component_id for n in high_prob)
            recs.append(
                f"High propagation probability detected for: {ids}. "
                "Consider adding redundancy or circuit breakers."
            )

        if len(nodes) > 5:
            recs.append(
                "Large blast radius detected. Consider introducing "
                "service mesh isolation or network segmentation."
            )

        comp = graph.get_component(source_id)
        if comp and comp.replicas < 2:
            recs.append(
                f"Source component {source_id} has no redundancy. "
                "Add replicas to reduce single-point-of-failure risk."
            )

        if not recs:
            recs.append("Blast radius is well-contained. No critical actions needed.")

        return recs

    # ------------------------------------------------------------------
    # Private: containment boundaries
    # ------------------------------------------------------------------

    @staticmethod
    def _classify_boundary(graph: InfraGraph, comp: Component) -> str | None:
        """Classify a component as a containment boundary, or None."""
        # Check incoming edges for circuit breakers
        deps = graph.get_dependencies(comp.id)
        for dep_comp in deps:
            edge = graph.get_dependency_edge(comp.id, dep_comp.id)
            if edge and edge.circuit_breaker.enabled:
                return "circuit_breaker"

        if comp.failover.enabled and comp.replicas >= 2:
            return "failover"

        if comp.replicas >= 3:
            return "redundancy"

        if comp.security.network_segmented:
            return "network_segment"

        return None

    @staticmethod
    def _components_behind_boundary(graph: InfraGraph, comp: Component) -> list[str]:
        """Return component IDs protected by a boundary component."""
        protected: list[str] = []
        for dep in graph.get_dependents(comp.id):
            protected.append(dep.id)
        return protected

    @staticmethod
    def _boundary_effectiveness(comp: Component, boundary_type: str) -> float:
        """Estimate effectiveness of a containment boundary (0-1)."""
        base = {
            "circuit_breaker": 0.85,
            "failover": 0.75,
            "redundancy": 0.6,
            "network_segment": 0.7,
        }.get(boundary_type, 0.5)

        # More replicas improve effectiveness
        if comp.replicas >= 3:
            base = min(1.0, base + 0.1)

        return round(base, 2)

    # ------------------------------------------------------------------
    # Private: visualization helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _impact_level_depth(level: ImpactLevel) -> int:
        """Convert an ImpactLevel to a numeric depth for visualization."""
        return {
            ImpactLevel.DIRECT: 1,
            ImpactLevel.FIRST_HOP: 2,
            ImpactLevel.SECOND_HOP: 3,
            ImpactLevel.TRANSITIVE: 4,
            ImpactLevel.POTENTIAL: 5,
        }.get(level, 4)
