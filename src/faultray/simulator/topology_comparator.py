# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Topology comparator — structural comparison of infrastructure graphs.

Compares two InfraGraph instances and reports structural differences:
added/removed components, changed dependencies, topology metrics shifts,
and architectural pattern changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from faultray.model.components import HealthStatus
from faultray.model.graph import InfraGraph


class ChangeType(str, Enum):
    """Type of topology change."""

    COMPONENT_ADDED = "component_added"
    COMPONENT_REMOVED = "component_removed"
    COMPONENT_MODIFIED = "component_modified"
    DEPENDENCY_ADDED = "dependency_added"
    DEPENDENCY_REMOVED = "dependency_removed"
    TOPOLOGY_SHIFT = "topology_shift"


class ChangeImpact(str, Enum):
    """Impact level of a change."""

    BREAKING = "breaking"
    SIGNIFICANT = "significant"
    MINOR = "minor"
    COSMETIC = "cosmetic"


@dataclass
class TopologyChange:
    """A single topology change between two graphs."""

    change_type: ChangeType
    impact: ChangeImpact
    component_id: str
    description: str
    before: str
    after: str


@dataclass
class TopologyMetrics:
    """Structural metrics for a topology."""

    component_count: int
    dependency_count: int
    max_depth: int
    avg_fan_out: float
    isolated_count: int  # no deps and no dependents
    spof_count: int
    resilience_score: float


@dataclass
class TopologyDiff:
    """Full comparison result between two topologies."""

    changes: list[TopologyChange]
    added_components: list[str]
    removed_components: list[str]
    modified_components: list[str]
    added_dependencies: list[tuple[str, str]]
    removed_dependencies: list[tuple[str, str]]
    before_metrics: TopologyMetrics
    after_metrics: TopologyMetrics
    breaking_changes: int
    significant_changes: int
    total_changes: int
    similarity_score: float  # 0-100 (100 = identical)
    summary: str


class TopologyComparator:
    """Compare two infrastructure topologies."""

    def compare(self, before: InfraGraph, after: InfraGraph) -> TopologyDiff:
        """Compare two infrastructure graphs and return differences."""
        changes: list[TopologyChange] = []

        before_ids = set(before.components.keys())
        after_ids = set(after.components.keys())

        added_ids = list(after_ids - before_ids)
        removed_ids = list(before_ids - after_ids)
        common_ids = before_ids & after_ids

        # Component additions
        for cid in added_ids:
            comp = after.get_component(cid)
            if comp:
                impact = self._assess_add_impact(comp, after)
                changes.append(TopologyChange(
                    change_type=ChangeType.COMPONENT_ADDED,
                    impact=impact,
                    component_id=cid,
                    description=f"New component: {comp.name} ({comp.type.value})",
                    before="(absent)",
                    after=f"{comp.name} [{comp.type.value}, replicas={comp.replicas}]",
                ))

        # Component removals
        for cid in removed_ids:
            comp = before.get_component(cid)
            if comp:
                dependents = before.get_dependents(cid)
                impact = ChangeImpact.BREAKING if dependents else ChangeImpact.SIGNIFICANT
                changes.append(TopologyChange(
                    change_type=ChangeType.COMPONENT_REMOVED,
                    impact=impact,
                    component_id=cid,
                    description=f"Removed component: {comp.name} ({comp.type.value})",
                    before=f"{comp.name} [{comp.type.value}, replicas={comp.replicas}]",
                    after="(absent)",
                ))

        # Component modifications
        modified_ids: list[str] = []
        for cid in common_ids:
            b_comp = before.get_component(cid)
            a_comp = after.get_component(cid)
            if b_comp and a_comp:
                mods = self._detect_modifications(cid, b_comp, a_comp)
                if mods:
                    modified_ids.append(cid)
                    changes.extend(mods)

        # Dependency changes
        before_deps = self._get_dep_set(before)
        after_deps = self._get_dep_set(after)
        added_deps = list(after_deps - before_deps)
        removed_deps = list(before_deps - after_deps)

        for src, tgt in added_deps:
            changes.append(TopologyChange(
                change_type=ChangeType.DEPENDENCY_ADDED,
                impact=ChangeImpact.MINOR,
                component_id=src,
                description=f"New dependency: {src} → {tgt}",
                before="(none)",
                after=f"{src} → {tgt}",
            ))

        for src, tgt in removed_deps:
            # Removing a dependency from an existing component is significant
            impact = ChangeImpact.SIGNIFICANT if src in after_ids else ChangeImpact.MINOR
            changes.append(TopologyChange(
                change_type=ChangeType.DEPENDENCY_REMOVED,
                impact=impact,
                component_id=src,
                description=f"Removed dependency: {src} → {tgt}",
                before=f"{src} → {tgt}",
                after="(none)",
            ))

        # Metrics
        before_metrics = self._compute_metrics(before)
        after_metrics = self._compute_metrics(after)

        # Topology-level shifts
        shifts = self._detect_topology_shifts(before_metrics, after_metrics)
        changes.extend(shifts)

        # Counts
        breaking = sum(1 for c in changes if c.impact == ChangeImpact.BREAKING)
        significant = sum(1 for c in changes if c.impact == ChangeImpact.SIGNIFICANT)

        # Similarity score
        similarity = self._calculate_similarity(
            before_ids, after_ids, before_deps, after_deps, len(changes),
        )

        # Summary
        summary = self._build_summary(
            added_ids, removed_ids, modified_ids,
            added_deps, removed_deps, breaking, similarity,
        )

        return TopologyDiff(
            changes=changes,
            added_components=added_ids,
            removed_components=removed_ids,
            modified_components=modified_ids,
            added_dependencies=added_deps,
            removed_dependencies=removed_deps,
            before_metrics=before_metrics,
            after_metrics=after_metrics,
            breaking_changes=breaking,
            significant_changes=significant,
            total_changes=len(changes),
            similarity_score=round(similarity, 1),
            summary=summary,
        )

    def is_compatible(self, before: InfraGraph, after: InfraGraph) -> bool:
        """Check if the topology change is backward compatible (no breaking changes)."""
        diff = self.compare(before, after)
        return diff.breaking_changes == 0

    def _get_dep_set(self, graph: InfraGraph) -> set[tuple[str, str]]:
        """Get all dependency edges as (source, target) tuples."""
        deps: set[tuple[str, str]] = set()
        for comp in graph.components.values():
            for dep in graph.get_dependencies(comp.id):
                deps.add((comp.id, dep.id))
        return deps

    def _detect_modifications(self, cid, b_comp, a_comp) -> list[TopologyChange]:
        """Detect modifications to a component."""
        mods: list[TopologyChange] = []

        # Replica change
        if b_comp.replicas != a_comp.replicas:
            impact = ChangeImpact.SIGNIFICANT if a_comp.replicas < b_comp.replicas else ChangeImpact.MINOR
            mods.append(TopologyChange(
                change_type=ChangeType.COMPONENT_MODIFIED,
                impact=impact,
                component_id=cid,
                description=f"Replicas changed: {b_comp.replicas} → {a_comp.replicas}",
                before=str(b_comp.replicas),
                after=str(a_comp.replicas),
            ))

        # Type change
        if b_comp.type != a_comp.type:
            mods.append(TopologyChange(
                change_type=ChangeType.COMPONENT_MODIFIED,
                impact=ChangeImpact.BREAKING,
                component_id=cid,
                description=f"Type changed: {b_comp.type.value} → {a_comp.type.value}",
                before=b_comp.type.value,
                after=a_comp.type.value,
            ))

        # Failover change
        if b_comp.failover.enabled != a_comp.failover.enabled:
            impact = ChangeImpact.SIGNIFICANT if not a_comp.failover.enabled else ChangeImpact.MINOR
            mods.append(TopologyChange(
                change_type=ChangeType.COMPONENT_MODIFIED,
                impact=impact,
                component_id=cid,
                description=f"Failover {'disabled' if not a_comp.failover.enabled else 'enabled'}",
                before=str(b_comp.failover.enabled),
                after=str(a_comp.failover.enabled),
            ))

        # Health change
        if b_comp.health != a_comp.health:
            impact = ChangeImpact.SIGNIFICANT if a_comp.health in (HealthStatus.DOWN, HealthStatus.OVERLOADED) else ChangeImpact.MINOR
            mods.append(TopologyChange(
                change_type=ChangeType.COMPONENT_MODIFIED,
                impact=impact,
                component_id=cid,
                description=f"Health changed: {b_comp.health.value} → {a_comp.health.value}",
                before=b_comp.health.value,
                after=a_comp.health.value,
            ))

        return mods

    def _compute_metrics(self, graph: InfraGraph) -> TopologyMetrics:
        """Compute topology metrics."""
        components = list(graph.components.values())
        if not components:
            return TopologyMetrics(
                component_count=0, dependency_count=0, max_depth=0,
                avg_fan_out=0.0, isolated_count=0, spof_count=0,
                resilience_score=100.0,
            )

        dep_count = 0
        fan_outs: list[int] = []
        isolated = 0
        spofs = 0
        max_depth = 0

        for comp in components:
            deps = graph.get_dependencies(comp.id)
            dependents = graph.get_dependents(comp.id)
            fan_outs.append(len(deps))
            dep_count += len(deps)

            if not deps and not dependents:
                isolated += 1

            if comp.replicas <= 1 and dependents:
                spofs += 1

            depth = self._calc_depth(graph, comp.id)
            max_depth = max(max_depth, depth)

        return TopologyMetrics(
            component_count=len(components),
            dependency_count=dep_count,
            max_depth=max_depth,
            avg_fan_out=round(sum(fan_outs) / len(fan_outs), 2) if fan_outs else 0.0,
            isolated_count=isolated,
            spof_count=spofs,
            resilience_score=round(graph.resilience_score(), 1),
        )

    def _calc_depth(self, graph: InfraGraph, cid: str) -> int:
        """Calculate max dependency depth from a component (DFS)."""
        visited: set[str] = set()
        max_d = 0

        def _dfs(c: str, d: int) -> None:
            nonlocal max_d
            if c in visited:
                return
            visited.add(c)
            max_d = max(max_d, d)
            for dep in graph.get_dependencies(c):
                _dfs(dep.id, d + 1)

        _dfs(cid, 0)
        return max_d

    def _assess_add_impact(self, comp, graph: InfraGraph) -> ChangeImpact:
        """Assess impact of adding a component."""
        dependents = graph.get_dependents(comp.id)
        if dependents:
            return ChangeImpact.SIGNIFICANT
        return ChangeImpact.MINOR

    def _detect_topology_shifts(
        self, before: TopologyMetrics, after: TopologyMetrics
    ) -> list[TopologyChange]:
        """Detect significant topology-level shifts."""
        shifts: list[TopologyChange] = []

        # SPOF count increase
        if after.spof_count > before.spof_count:
            shifts.append(TopologyChange(
                change_type=ChangeType.TOPOLOGY_SHIFT,
                impact=ChangeImpact.SIGNIFICANT,
                component_id="__topology__",
                description=f"SPOF count increased: {before.spof_count} → {after.spof_count}",
                before=str(before.spof_count),
                after=str(after.spof_count),
            ))

        # Max depth increase
        if after.max_depth > before.max_depth + 1:
            shifts.append(TopologyChange(
                change_type=ChangeType.TOPOLOGY_SHIFT,
                impact=ChangeImpact.MINOR,
                component_id="__topology__",
                description=f"Max depth increased: {before.max_depth} → {after.max_depth}",
                before=str(before.max_depth),
                after=str(after.max_depth),
            ))

        # Resilience score drop
        score_delta = after.resilience_score - before.resilience_score
        if score_delta < -10:
            shifts.append(TopologyChange(
                change_type=ChangeType.TOPOLOGY_SHIFT,
                impact=ChangeImpact.BREAKING,
                component_id="__topology__",
                description=f"Resilience score dropped: {before.resilience_score} → {after.resilience_score}",
                before=str(before.resilience_score),
                after=str(after.resilience_score),
            ))
        elif score_delta < -5:
            shifts.append(TopologyChange(
                change_type=ChangeType.TOPOLOGY_SHIFT,
                impact=ChangeImpact.SIGNIFICANT,
                component_id="__topology__",
                description=f"Resilience score decreased: {before.resilience_score} → {after.resilience_score}",
                before=str(before.resilience_score),
                after=str(after.resilience_score),
            ))

        return shifts

    def _calculate_similarity(
        self,
        before_ids: set[str],
        after_ids: set[str],
        before_deps: set[tuple[str, str]],
        after_deps: set[tuple[str, str]],
        total_changes: int,
    ) -> float:
        """Calculate similarity score between topologies."""
        if not before_ids and not after_ids:
            return 100.0

        # Jaccard similarity for components
        union_c = before_ids | after_ids
        intersect_c = before_ids & after_ids
        comp_similarity = len(intersect_c) / len(union_c) if union_c else 1.0

        # Jaccard similarity for dependencies
        union_d = before_deps | after_deps
        intersect_d = before_deps & after_deps
        dep_similarity = len(intersect_d) / len(union_d) if union_d else 1.0

        # Weighted average (components are more important)
        similarity = comp_similarity * 0.6 + dep_similarity * 0.4
        return similarity * 100

    def _build_summary(
        self,
        added: list[str],
        removed: list[str],
        modified: list[str],
        added_deps: list[tuple[str, str]],
        removed_deps: list[tuple[str, str]],
        breaking: int,
        similarity: float,
    ) -> str:
        """Build human-readable summary."""
        if not added and not removed and not modified and not added_deps and not removed_deps:
            return "Topologies are identical."

        parts: list[str] = []
        if added:
            parts.append(f"+{len(added)} component(s)")
        if removed:
            parts.append(f"-{len(removed)} component(s)")
        if modified:
            parts.append(f"~{len(modified)} modified")
        if added_deps:
            parts.append(f"+{len(added_deps)} dep(s)")
        if removed_deps:
            parts.append(f"-{len(removed_deps)} dep(s)")

        summary = ", ".join(parts)
        if breaking > 0:
            summary += f" | {breaking} BREAKING"
        summary += f" | Similarity: {similarity:.0f}%"
        return summary
