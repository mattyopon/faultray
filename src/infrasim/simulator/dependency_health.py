"""Dependency-aware health scoring and propagation engine.

Computes component health scores that account for dependency chain health,
enabling a real-time dependency health dashboard where upstream failures
propagate health degradation to downstream consumers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from infrasim.model.components import ComponentType, HealthStatus
from infrasim.model.graph import InfraGraph


class HealthTier(str, Enum):
    """Health tier classification."""

    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"
    CRITICAL = "critical"


@dataclass
class DependencyHealthScore:
    """Health score for a single component including dependency impact."""

    component_id: str
    component_name: str
    component_type: str
    own_health_score: float  # 0-100, based on component's own metrics
    dependency_health_score: float  # 0-100, based on upstream deps
    effective_health_score: float  # 0-100, combined
    tier: HealthTier
    health_status: HealthStatus
    degradation_sources: list[str]  # component names causing degradation
    dependency_depth: int  # max depth in dependency chain
    critical_dependency_count: int  # number of unhealthy dependencies
    is_leaf: bool  # no downstream dependencies


@dataclass
class HealthPropagation:
    """How health degrades through a dependency path."""

    path: list[str]  # component IDs from source to target
    path_names: list[str]  # component names
    source_health: float
    propagated_health: float
    attenuation_factor: float  # how much health is lost per hop


@dataclass
class HealthCluster:
    """Group of components with correlated health."""

    cluster_id: str
    component_ids: list[str]
    component_names: list[str]
    average_health: float
    min_health: float
    correlation_reason: str  # why these are clustered


@dataclass
class DependencyHealthReport:
    """Full dependency health analysis report."""

    scores: dict[str, DependencyHealthScore]
    overall_health: float  # 0-100
    tier: HealthTier
    critical_components: list[str]  # IDs of components in CRITICAL tier
    degraded_paths: list[HealthPropagation]
    health_clusters: list[HealthCluster]
    improvement_suggestions: list[str]
    component_count: int
    healthy_count: int
    degraded_count: int
    critical_count: int


# Health score weights for different component states
_OWN_HEALTH_WEIGHTS: dict[HealthStatus, float] = {
    HealthStatus.HEALTHY: 100.0,
    HealthStatus.DEGRADED: 60.0,
    HealthStatus.OVERLOADED: 35.0,
    HealthStatus.DOWN: 0.0,
}

# How much dependency health affects effective score (vs own health)
_DEPENDENCY_WEIGHT = 0.35
_OWN_WEIGHT = 0.65

# Health decay per dependency hop
_HOP_DECAY = 0.7  # each hop retains 70% of the degradation signal

# Utilization thresholds that reduce health score
_UTILIZATION_THRESHOLDS = [
    (90, -30),  # >90% util: -30 health
    (80, -20),  # >80% util: -20 health
    (70, -10),  # >70% util: -10 health
    (60, -5),   # >60% util: -5 health
]


def _classify_tier(score: float) -> HealthTier:
    """Classify a health score into a tier."""
    if score >= 90:
        return HealthTier.EXCELLENT
    if score >= 75:
        return HealthTier.GOOD
    if score >= 50:
        return HealthTier.FAIR
    if score >= 25:
        return HealthTier.POOR
    return HealthTier.CRITICAL


def _own_health_score(component) -> float:
    """Calculate a component's own health score (0-100)."""
    base = _OWN_HEALTH_WEIGHTS.get(component.health, 50.0)

    # Adjust for utilization
    util = component.utilization()
    for threshold, penalty in _UTILIZATION_THRESHOLDS:
        if util > threshold:
            base = max(0, base + penalty)
            break

    # Bonus for redundancy
    if component.replicas > 1:
        redundancy_bonus = min(15, (component.replicas - 1) * 5)
        base = min(100, base + redundancy_bonus)

    # Bonus for failover
    if component.failover.enabled:
        base = min(100, base + 5)

    # Penalty for SPOF with dependents (handled later with dependency info)
    return base


class DependencyHealthEngine:
    """Compute dependency-aware health scores for all components."""

    def __init__(
        self,
        dependency_weight: float = _DEPENDENCY_WEIGHT,
        hop_decay: float = _HOP_DECAY,
    ):
        self._dep_weight = dependency_weight
        self._own_weight = 1.0 - dependency_weight
        self._hop_decay = hop_decay

    def analyze(self, graph: InfraGraph) -> DependencyHealthReport:
        """Run full dependency health analysis on the graph."""
        if not graph.components:
            return DependencyHealthReport(
                scores={},
                overall_health=100.0,
                tier=HealthTier.EXCELLENT,
                critical_components=[],
                degraded_paths=[],
                health_clusters=[],
                improvement_suggestions=[],
                component_count=0,
                healthy_count=0,
                degraded_count=0,
                critical_count=0,
            )

        # Phase 1: Calculate own health scores
        own_scores: dict[str, float] = {}
        for cid, comp in graph.components.items():
            own_scores[cid] = _own_health_score(comp)

        # Phase 2: Calculate dependency health scores via BFS propagation
        dep_scores: dict[str, float] = {}
        dep_sources: dict[str, list[str]] = {}
        dep_depths: dict[str, int] = {}

        for cid in graph.components:
            dep_health, sources, depth = self._propagate_dependency_health(
                graph, cid, own_scores
            )
            dep_scores[cid] = dep_health
            dep_sources[cid] = sources
            dep_depths[cid] = depth

        # Phase 3: Calculate effective health scores
        scores: dict[str, DependencyHealthScore] = {}
        for cid, comp in graph.components.items():
            own = own_scores[cid]
            dep = dep_scores[cid]
            effective = self._own_weight * own + self._dep_weight * dep

            deps = graph.get_dependencies(cid)
            is_leaf = len(deps) == 0
            critical_dep_count = sum(
                1 for d in deps
                if own_scores.get(d.id, 100) < 50
            )

            scores[cid] = DependencyHealthScore(
                component_id=cid,
                component_name=comp.name,
                component_type=comp.type.value,
                own_health_score=round(own, 1),
                dependency_health_score=round(dep, 1),
                effective_health_score=round(effective, 1),
                tier=_classify_tier(effective),
                health_status=comp.health,
                degradation_sources=dep_sources.get(cid, []),
                dependency_depth=dep_depths.get(cid, 0),
                critical_dependency_count=critical_dep_count,
                is_leaf=is_leaf,
            )

        # Phase 4: Find degraded paths
        degraded_paths = self._find_degraded_paths(graph, own_scores)

        # Phase 5: Cluster components by health correlation
        clusters = self._find_health_clusters(graph, scores)

        # Phase 6: Generate improvement suggestions
        suggestions = self._generate_suggestions(graph, scores)

        # Phase 7: Aggregate statistics
        health_values = [s.effective_health_score for s in scores.values()]
        overall = sum(health_values) / len(health_values) if health_values else 100.0

        critical_ids = [
            s.component_id for s in scores.values()
            if s.tier == HealthTier.CRITICAL
        ]
        healthy_count = sum(
            1 for s in scores.values() if s.tier in (HealthTier.EXCELLENT, HealthTier.GOOD)
        )
        degraded_count = sum(
            1 for s in scores.values() if s.tier == HealthTier.FAIR
        )
        critical_count = sum(
            1 for s in scores.values()
            if s.tier in (HealthTier.POOR, HealthTier.CRITICAL)
        )

        return DependencyHealthReport(
            scores=scores,
            overall_health=round(overall, 1),
            tier=_classify_tier(overall),
            critical_components=critical_ids,
            degraded_paths=degraded_paths,
            health_clusters=clusters,
            improvement_suggestions=suggestions,
            component_count=len(scores),
            healthy_count=healthy_count,
            degraded_count=degraded_count,
            critical_count=critical_count,
        )

    def score_component(
        self, graph: InfraGraph, component_id: str
    ) -> DependencyHealthScore | None:
        """Score a single component with dependency awareness."""
        comp = graph.get_component(component_id)
        if comp is None:
            return None

        own_scores: dict[str, float] = {}
        for cid, c in graph.components.items():
            own_scores[cid] = _own_health_score(c)

        own = own_scores[component_id]
        dep_health, sources, depth = self._propagate_dependency_health(
            graph, component_id, own_scores
        )
        effective = self._own_weight * own + self._dep_weight * dep_health

        deps = graph.get_dependencies(component_id)
        is_leaf = len(deps) == 0
        critical_dep_count = sum(
            1 for d in deps if own_scores.get(d.id, 100) < 50
        )

        return DependencyHealthScore(
            component_id=component_id,
            component_name=comp.name,
            component_type=comp.type.value,
            own_health_score=round(own, 1),
            dependency_health_score=round(dep_health, 1),
            effective_health_score=round(effective, 1),
            tier=_classify_tier(effective),
            health_status=comp.health,
            degradation_sources=sources,
            dependency_depth=depth,
            critical_dependency_count=critical_dep_count,
            is_leaf=is_leaf,
        )

    def get_health_summary(self, graph: InfraGraph) -> dict:
        """Return a compact health summary suitable for dashboard display."""
        report = self.analyze(graph)
        return {
            "overall_health": report.overall_health,
            "tier": report.tier.value,
            "component_count": report.component_count,
            "healthy": report.healthy_count,
            "degraded": report.degraded_count,
            "critical": report.critical_count,
            "critical_components": [
                {
                    "id": report.scores[cid].component_id,
                    "name": report.scores[cid].component_name,
                    "score": report.scores[cid].effective_health_score,
                }
                for cid in report.critical_components
            ],
            "top_degradation_sources": self._top_degradation_sources(report),
        }

    def _propagate_dependency_health(
        self,
        graph: InfraGraph,
        component_id: str,
        own_scores: dict[str, float],
    ) -> tuple[float, list[str], int]:
        """Calculate dependency health score via BFS through dependencies.

        Returns (dep_health_score, degradation_sources, max_depth).
        """
        deps = graph.get_dependencies(component_id)
        if not deps:
            return 100.0, [], 0

        visited: set[str] = {component_id}
        queue: list[tuple[str, int]] = [(d.id, 1) for d in deps]
        degradation_sources: list[str] = []
        health_contributions: list[tuple[float, float]] = []  # (score, weight)
        max_depth = 0

        while queue:
            cid, depth = queue.pop(0)
            if cid in visited:
                continue
            visited.add(cid)
            max_depth = max(max_depth, depth)

            score = own_scores.get(cid, 100.0)
            weight = self._hop_decay ** (depth - 1)
            health_contributions.append((score, weight))

            if score < 50:
                comp = graph.get_component(cid)
                if comp:
                    degradation_sources.append(comp.name)

            # Continue BFS through this component's dependencies
            next_deps = graph.get_dependencies(cid)
            for nd in next_deps:
                if nd.id not in visited:
                    queue.append((nd.id, depth + 1))

        if not health_contributions:
            return 100.0, degradation_sources, max_depth

        total_weight = sum(w for _, w in health_contributions)
        weighted_sum = sum(s * w for s, w in health_contributions)
        dep_health = weighted_sum / total_weight if total_weight > 0 else 100.0

        return dep_health, degradation_sources, max_depth

    def _find_degraded_paths(
        self, graph: InfraGraph, own_scores: dict[str, float]
    ) -> list[HealthPropagation]:
        """Find paths where health degradation propagates."""
        degraded_paths: list[HealthPropagation] = []

        # Find components with low health as sources
        sources = [
            cid for cid, score in own_scores.items() if score < 50
        ]

        for source_id in sources:
            dependents = graph.get_dependents(source_id)
            for dep in dependents:
                source_comp = graph.get_component(source_id)
                dep_comp = graph.get_component(dep.id)
                if not source_comp or not dep_comp:
                    continue

                source_health = own_scores[source_id]
                propagated = source_health * self._hop_decay

                degraded_paths.append(HealthPropagation(
                    path=[source_id, dep.id],
                    path_names=[source_comp.name, dep_comp.name],
                    source_health=round(source_health, 1),
                    propagated_health=round(propagated, 1),
                    attenuation_factor=self._hop_decay,
                ))

        return degraded_paths

    def _find_health_clusters(
        self, graph: InfraGraph, scores: dict[str, DependencyHealthScore]
    ) -> list[HealthCluster]:
        """Group components that share health correlation."""
        clusters: list[HealthCluster] = []

        # Cluster by shared dependencies
        dep_groups: dict[str, list[str]] = {}
        for cid in graph.components:
            deps = graph.get_dependencies(cid)
            dep_key = ",".join(sorted(d.id for d in deps)) if deps else ""
            if dep_key:
                dep_groups.setdefault(dep_key, []).append(cid)

        cluster_idx = 0
        for dep_key, members in dep_groups.items():
            if len(members) < 2:
                continue
            member_scores = [
                scores[m].effective_health_score for m in members if m in scores
            ]
            if not member_scores:
                continue

            names = [
                scores[m].component_name for m in members if m in scores
            ]
            clusters.append(HealthCluster(
                cluster_id=f"cluster-{cluster_idx}",
                component_ids=members,
                component_names=names,
                average_health=round(
                    sum(member_scores) / len(member_scores), 1
                ),
                min_health=round(min(member_scores), 1),
                correlation_reason="Shared dependency chain",
            ))
            cluster_idx += 1

        return clusters

    def _generate_suggestions(
        self,
        graph: InfraGraph,
        scores: dict[str, DependencyHealthScore],
    ) -> list[str]:
        """Generate improvement suggestions based on health analysis."""
        suggestions: list[str] = []

        for cid, score in scores.items():
            comp = graph.get_component(cid)
            if not comp:
                continue

            if score.tier in (HealthTier.CRITICAL, HealthTier.POOR):
                if comp.health == HealthStatus.DOWN:
                    suggestions.append(
                        f"CRITICAL: {comp.name} is DOWN. Immediate recovery required."
                    )
                elif comp.replicas <= 1:
                    suggestions.append(
                        f"Add replicas to {comp.name} (currently single instance, "
                        f"health score: {score.effective_health_score})."
                    )

            if score.critical_dependency_count > 0:
                suggestions.append(
                    f"{comp.name} has {score.critical_dependency_count} unhealthy "
                    f"dependency(ies). Address upstream issues first."
                )

            if (
                score.own_health_score > 80
                and score.dependency_health_score < 50
            ):
                suggestions.append(
                    f"{comp.name} is healthy but degraded by dependencies: "
                    f"{', '.join(score.degradation_sources)}."
                )

        # Deduplicate
        seen: set[str] = set()
        unique: list[str] = []
        for s in suggestions:
            if s not in seen:
                seen.add(s)
                unique.append(s)

        return unique[:20]  # Limit to top 20

    def _top_degradation_sources(
        self, report: DependencyHealthReport
    ) -> list[dict]:
        """Find the top degradation sources across all components."""
        source_counts: dict[str, int] = {}
        for score in report.scores.values():
            for src in score.degradation_sources:
                source_counts[src] = source_counts.get(src, 0) + 1

        sorted_sources = sorted(
            source_counts.items(), key=lambda x: x[1], reverse=True
        )
        return [
            {"name": name, "affected_count": count}
            for name, count in sorted_sources[:5]
        ]
