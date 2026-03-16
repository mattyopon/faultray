"""Dependency Graph Diff Engine — computes structural diffs between infrastructure graphs.

Identifies architectural changes including added/removed/modified components and
dependencies, calculates change risk, detects breaking changes, generates migration
plans, and validates backward compatibility.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from faultray.model.components import ComponentType, HealthStatus
from faultray.model.graph import InfraGraph


class DiffType(str, Enum):
    """Type of structural diff between two graphs."""

    COMPONENT_ADDED = "component_added"
    COMPONENT_REMOVED = "component_removed"
    COMPONENT_MODIFIED = "component_modified"
    DEPENDENCY_ADDED = "dependency_added"
    DEPENDENCY_REMOVED = "dependency_removed"
    DEPENDENCY_MODIFIED = "dependency_modified"
    TYPE_CHANGED = "type_changed"
    REPLICAS_CHANGED = "replicas_changed"
    HEALTH_CHANGED = "health_changed"


# Risk level weights for score calculation.
_RISK_WEIGHTS: dict[str, float] = {
    "critical": 1.0,
    "high": 0.7,
    "medium": 0.4,
    "low": 0.1,
}

# Component types that are considered critical infrastructure.
_CRITICAL_TYPES: set[ComponentType] = {
    ComponentType.DATABASE,
    ComponentType.LOAD_BALANCER,
    ComponentType.DNS,
}


class DiffEntry(BaseModel):
    """A single diff entry describing one change between two graphs."""

    diff_type: DiffType
    entity_id: str
    old_value: str = ""
    new_value: str = ""
    risk_level: str = "low"  # critical / high / medium / low
    description: str = ""


class GraphDiff(BaseModel):
    """Full structural diff result between two infrastructure graphs."""

    added_components: list[str] = Field(default_factory=list)
    removed_components: list[str] = Field(default_factory=list)
    modified_components: list[str] = Field(default_factory=list)
    added_dependencies: list[tuple[str, str]] = Field(default_factory=list)
    removed_dependencies: list[tuple[str, str]] = Field(default_factory=list)
    entries: list[DiffEntry] = Field(default_factory=list)
    total_changes: int = 0
    risk_score: float = 0.0
    breaking_changes: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class MigrationStep(BaseModel):
    """A single step in a migration plan."""

    order: int
    action: str
    component_id: str
    description: str
    risk_level: str = "low"
    rollback_action: str = ""


class MigrationPlan(BaseModel):
    """Ordered migration plan generated from a graph diff."""

    steps: list[MigrationStep] = Field(default_factory=list)
    estimated_steps: int = 0
    requires_downtime: bool = False
    rollback_steps: list[MigrationStep] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class CompatibilityIssue(BaseModel):
    """A single backward-compatibility issue."""

    severity: str  # critical / high / medium / low
    entity_id: str
    description: str


class CompatibilityReport(BaseModel):
    """Result of backward-compatibility validation."""

    is_compatible: bool = True
    issues: list[CompatibilityIssue] = Field(default_factory=list)
    score: float = 100.0  # 0-100, 100 = fully compatible
    summary: str = ""


class DependencyGraphDiffEngine:
    """Engine for computing and analysing structural diffs between InfraGraphs."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compute_diff(self, graph_a: InfraGraph, graph_b: InfraGraph) -> GraphDiff:
        """Compute a structural diff between *graph_a* (before) and *graph_b* (after)."""

        entries: list[DiffEntry] = []
        added_components: list[str] = []
        removed_components: list[str] = []
        modified_components: list[str] = []
        added_dependencies: list[tuple[str, str]] = []
        removed_dependencies: list[tuple[str, str]] = []

        ids_a = set(graph_a.components.keys())
        ids_b = set(graph_b.components.keys())

        # --- Component additions ---
        for cid in sorted(ids_b - ids_a):
            added_components.append(cid)
            comp = graph_b.get_component(cid)
            risk = self._component_add_risk(comp, graph_b)
            entries.append(DiffEntry(
                diff_type=DiffType.COMPONENT_ADDED,
                entity_id=cid,
                old_value="",
                new_value=f"{comp.name} ({comp.type.value})" if comp else cid,
                risk_level=risk,
                description=f"Component '{cid}' added",
            ))

        # --- Component removals ---
        for cid in sorted(ids_a - ids_b):
            removed_components.append(cid)
            comp = graph_a.get_component(cid)
            risk = self._component_remove_risk(comp, graph_a)
            entries.append(DiffEntry(
                diff_type=DiffType.COMPONENT_REMOVED,
                entity_id=cid,
                old_value=f"{comp.name} ({comp.type.value})" if comp else cid,
                new_value="",
                risk_level=risk,
                description=f"Component '{cid}' removed",
            ))

        # --- Component modifications ---
        for cid in sorted(ids_a & ids_b):
            comp_a = graph_a.get_component(cid)
            comp_b = graph_b.get_component(cid)
            if comp_a is None or comp_b is None:
                continue
            mods = self._diff_component(cid, comp_a, comp_b, graph_a)
            if mods:
                modified_components.append(cid)
                entries.extend(mods)

        # --- Dependency changes ---
        deps_a = self._dep_set(graph_a)
        deps_b = self._dep_set(graph_b)

        for src, tgt in sorted(deps_b - deps_a):
            added_dependencies.append((src, tgt))
            entries.append(DiffEntry(
                diff_type=DiffType.DEPENDENCY_ADDED,
                entity_id=f"{src}->{tgt}",
                old_value="",
                new_value=f"{src} -> {tgt}",
                risk_level="low",
                description=f"Dependency added: {src} -> {tgt}",
            ))

        for src, tgt in sorted(deps_a - deps_b):
            removed_dependencies.append((src, tgt))
            risk = self._dep_remove_risk(src, tgt, graph_a, graph_b)
            entries.append(DiffEntry(
                diff_type=DiffType.DEPENDENCY_REMOVED,
                entity_id=f"{src}->{tgt}",
                old_value=f"{src} -> {tgt}",
                new_value="",
                risk_level=risk,
                description=f"Dependency removed: {src} -> {tgt}",
            ))

        # --- Dependency modifications (type / weight changes on common edges) ---
        for src, tgt in sorted(deps_a & deps_b):
            edge_a = graph_a.get_dependency_edge(src, tgt)
            edge_b = graph_b.get_dependency_edge(src, tgt)
            if edge_a and edge_b:
                dep_mods = self._diff_dependency(src, tgt, edge_a, edge_b)
                entries.extend(dep_mods)

        # --- Build result ---
        diff = GraphDiff(
            added_components=added_components,
            removed_components=removed_components,
            modified_components=modified_components,
            added_dependencies=added_dependencies,
            removed_dependencies=removed_dependencies,
            entries=entries,
            total_changes=len(entries),
        )
        diff.risk_score = self.calculate_change_risk(diff)
        diff.breaking_changes = self.detect_breaking_changes(diff)
        diff.recommendations = self._generate_recommendations(diff, graph_a, graph_b)
        return diff

    def detect_breaking_changes(self, diff: GraphDiff) -> list[str]:
        """Return human-readable descriptions of breaking changes found in *diff*."""
        breaking: list[str] = []
        for entry in diff.entries:
            if entry.risk_level == "critical":
                breaking.append(entry.description)
            elif entry.diff_type == DiffType.COMPONENT_REMOVED:
                breaking.append(entry.description)
            elif entry.diff_type == DiffType.TYPE_CHANGED:
                breaking.append(entry.description)
            elif (
                entry.diff_type == DiffType.DEPENDENCY_REMOVED
                and entry.risk_level in ("critical", "high")
            ):
                breaking.append(entry.description)
        # Deduplicate while preserving order.
        seen: set[str] = set()
        unique: list[str] = []
        for b in breaking:
            if b not in seen:
                seen.add(b)
                unique.append(b)
        return unique

    def calculate_change_risk(self, diff: GraphDiff) -> float:
        """Calculate an aggregate risk score (0.0 -- 100.0) for the diff."""
        if not diff.entries:
            return 0.0

        total_weight = 0.0
        for entry in diff.entries:
            total_weight += _RISK_WEIGHTS.get(entry.risk_level, 0.1)

        # Normalise so that 10 critical entries = 100.
        raw = (total_weight / max(len(diff.entries), 1)) * min(len(diff.entries), 10) * 10
        return round(min(100.0, max(0.0, raw)), 2)

    def generate_migration_plan(self, diff: GraphDiff) -> MigrationPlan:
        """Generate an ordered migration plan from a diff."""
        steps: list[MigrationStep] = []
        rollback_steps: list[MigrationStep] = []
        warnings: list[str] = []
        order = 0
        requires_downtime = False

        # 1. Add new components first (safe — nothing depends on them yet).
        for cid in diff.added_components:
            order += 1
            entry = self._find_entry(diff, cid, DiffType.COMPONENT_ADDED)
            steps.append(MigrationStep(
                order=order,
                action="add",
                component_id=cid,
                description=f"Deploy new component '{cid}'",
                risk_level=entry.risk_level if entry else "low",
                rollback_action=f"Remove component '{cid}'",
            ))
            rollback_steps.append(MigrationStep(
                order=order,
                action="remove",
                component_id=cid,
                description=f"Remove component '{cid}' (rollback)",
                risk_level="low",
                rollback_action="",
            ))

        # 2. Add new dependencies.
        for src, tgt in diff.added_dependencies:
            order += 1
            steps.append(MigrationStep(
                order=order,
                action="add_dependency",
                component_id=f"{src}->{tgt}",
                description=f"Add dependency {src} -> {tgt}",
                risk_level="low",
                rollback_action=f"Remove dependency {src} -> {tgt}",
            ))
            rollback_steps.append(MigrationStep(
                order=order,
                action="remove_dependency",
                component_id=f"{src}->{tgt}",
                description=f"Remove dependency {src} -> {tgt} (rollback)",
                risk_level="low",
                rollback_action="",
            ))

        # 3. Modify components.
        for cid in diff.modified_components:
            order += 1
            mod_entries = [e for e in diff.entries if e.entity_id == cid]
            max_risk = max(
                (e.risk_level for e in mod_entries),
                key=lambda r: _RISK_WEIGHTS.get(r, 0),
                default="low",
            )
            has_type_change = any(e.diff_type == DiffType.TYPE_CHANGED for e in mod_entries)
            if has_type_change:
                requires_downtime = True
                warnings.append(
                    f"Component '{cid}' type changed — may require downtime"
                )
            steps.append(MigrationStep(
                order=order,
                action="modify",
                component_id=cid,
                description=f"Modify component '{cid}'",
                risk_level=max_risk,
                rollback_action=f"Revert component '{cid}' to previous state",
            ))
            rollback_steps.append(MigrationStep(
                order=order,
                action="revert",
                component_id=cid,
                description=f"Revert component '{cid}' (rollback)",
                risk_level="low",
                rollback_action="",
            ))

        # 4. Remove dependencies (before removing components that may own them).
        for src, tgt in diff.removed_dependencies:
            order += 1
            risk = "medium"
            for e in diff.entries:
                if e.entity_id == f"{src}->{tgt}" and e.diff_type == DiffType.DEPENDENCY_REMOVED:
                    risk = e.risk_level
                    break
            steps.append(MigrationStep(
                order=order,
                action="remove_dependency",
                component_id=f"{src}->{tgt}",
                description=f"Remove dependency {src} -> {tgt}",
                risk_level=risk,
                rollback_action=f"Re-add dependency {src} -> {tgt}",
            ))
            rollback_steps.append(MigrationStep(
                order=order,
                action="add_dependency",
                component_id=f"{src}->{tgt}",
                description=f"Re-add dependency {src} -> {tgt} (rollback)",
                risk_level="low",
                rollback_action="",
            ))

        # 5. Remove components last (most dangerous).
        for cid in diff.removed_components:
            order += 1
            requires_downtime = True
            entry = self._find_entry(diff, cid, DiffType.COMPONENT_REMOVED)
            steps.append(MigrationStep(
                order=order,
                action="remove",
                component_id=cid,
                description=f"Remove component '{cid}'",
                risk_level=entry.risk_level if entry else "high",
                rollback_action=f"Re-deploy component '{cid}'",
            ))
            rollback_steps.append(MigrationStep(
                order=order,
                action="add",
                component_id=cid,
                description=f"Re-deploy component '{cid}' (rollback)",
                risk_level="low",
                rollback_action="",
            ))
            warnings.append(f"Removing component '{cid}' is irreversible without backup")

        # Reverse rollback order so undo is done in reverse.
        rollback_steps = list(reversed(rollback_steps))
        for i, step in enumerate(rollback_steps, 1):
            step.order = i

        return MigrationPlan(
            steps=steps,
            estimated_steps=len(steps),
            requires_downtime=requires_downtime,
            rollback_steps=rollback_steps,
            warnings=warnings,
        )

    def find_safe_rollback_point(self, diffs: list[GraphDiff]) -> int:
        """Given a chronological list of diffs, return the 0-based index of the
        last diff that can be safely rolled back to (lowest cumulative risk).

        Returns 0 if only one diff is provided, or -1 if the list is empty.
        """
        if not diffs:
            return -1
        if len(diffs) == 1:
            return 0

        # Walk backwards; the first diff whose cumulative risk is still low is safe.
        cumulative_risk = 0.0
        best_index = 0
        best_risk = float("inf")
        for i, d in enumerate(diffs):
            cumulative_risk += d.risk_score
            has_critical = any(e.risk_level == "critical" for e in d.entries)
            effective = cumulative_risk * (2.0 if has_critical else 1.0)
            if effective <= best_risk:
                best_risk = effective
                best_index = i
        return best_index

    def summarize_diff(self, diff: GraphDiff) -> str:
        """Return a human-readable one-paragraph summary of the diff."""
        if diff.total_changes == 0:
            return "No changes detected between the two graphs."

        parts: list[str] = []
        if diff.added_components:
            parts.append(f"{len(diff.added_components)} component(s) added")
        if diff.removed_components:
            parts.append(f"{len(diff.removed_components)} component(s) removed")
        if diff.modified_components:
            parts.append(f"{len(diff.modified_components)} component(s) modified")
        if diff.added_dependencies:
            parts.append(f"{len(diff.added_dependencies)} dependency(ies) added")
        if diff.removed_dependencies:
            parts.append(f"{len(diff.removed_dependencies)} dependency(ies) removed")

        summary = "Changes: " + ", ".join(parts) + "."
        summary += f" Total entries: {diff.total_changes}."
        summary += f" Risk score: {diff.risk_score}."

        if diff.breaking_changes:
            summary += f" Breaking changes ({len(diff.breaking_changes)}): "
            summary += "; ".join(diff.breaking_changes[:3])
            if len(diff.breaking_changes) > 3:
                summary += f" (and {len(diff.breaking_changes) - 3} more)"
            summary += "."

        if diff.recommendations:
            summary += f" Recommendations: {diff.recommendations[0]}"
            if len(diff.recommendations) > 1:
                summary += f" (+{len(diff.recommendations) - 1} more)"
            summary += "."

        return summary

    def validate_backward_compatibility(
        self, diff: GraphDiff
    ) -> CompatibilityReport:
        """Validate whether the diff is backward-compatible."""
        issues: list[CompatibilityIssue] = []

        # Removed components are inherently incompatible.
        for cid in diff.removed_components:
            issues.append(CompatibilityIssue(
                severity="critical",
                entity_id=cid,
                description=f"Component '{cid}' was removed",
            ))

        # Type changes are breaking.
        for entry in diff.entries:
            if entry.diff_type == DiffType.TYPE_CHANGED:
                issues.append(CompatibilityIssue(
                    severity="critical",
                    entity_id=entry.entity_id,
                    description=entry.description,
                ))

        # Removed dependencies where the source still exists.
        for entry in diff.entries:
            if entry.diff_type == DiffType.DEPENDENCY_REMOVED:
                src = entry.entity_id.split("->")[0] if "->" in entry.entity_id else ""
                if src and src not in diff.removed_components:
                    issues.append(CompatibilityIssue(
                        severity="high",
                        entity_id=entry.entity_id,
                        description=entry.description,
                    ))

        # Replica reduction.
        for entry in diff.entries:
            if entry.diff_type == DiffType.REPLICAS_CHANGED:
                try:
                    old_val = int(entry.old_value)
                    new_val = int(entry.new_value)
                except (ValueError, TypeError):
                    continue
                if new_val < old_val:
                    issues.append(CompatibilityIssue(
                        severity="medium",
                        entity_id=entry.entity_id,
                        description=f"Replica count reduced from {old_val} to {new_val}",
                    ))

        # Health degradation.
        for entry in diff.entries:
            if entry.diff_type == DiffType.HEALTH_CHANGED:
                if entry.new_value in (HealthStatus.DOWN.value, HealthStatus.OVERLOADED.value):
                    issues.append(CompatibilityIssue(
                        severity="high",
                        entity_id=entry.entity_id,
                        description=f"Health degraded to {entry.new_value}",
                    ))

        # Score: deduct per-severity.
        severity_deductions = {"critical": 25.0, "high": 15.0, "medium": 5.0, "low": 1.0}
        deduction = sum(severity_deductions.get(i.severity, 0.0) for i in issues)
        score = round(max(0.0, 100.0 - deduction), 2)
        is_compatible = all(i.severity not in ("critical",) for i in issues)

        # Summary.
        if not issues:
            summary_text = "Fully backward compatible — no issues detected."
        elif is_compatible:
            summary_text = (
                f"{len(issues)} compatibility concern(s) found, "
                "but none are critical. Backward compatibility is maintained."
            )
        else:
            critical_count = sum(1 for i in issues if i.severity == "critical")
            summary_text = (
                f"NOT backward compatible — {critical_count} critical issue(s) detected."
            )

        return CompatibilityReport(
            is_compatible=is_compatible,
            issues=issues,
            score=score,
            summary=summary_text,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _dep_set(self, graph: InfraGraph) -> set[tuple[str, str]]:
        """Return all dependency edges as ``(source, target)`` pairs."""
        result: set[tuple[str, str]] = set()
        for comp in graph.components.values():
            for dep in graph.get_dependencies(comp.id):
                result.add((comp.id, dep.id))
        return result

    def _diff_component(self, cid, comp_a, comp_b, graph_a) -> list[DiffEntry]:
        """Detect per-field modifications between two versions of a component."""
        mods: list[DiffEntry] = []

        # Type change
        if comp_a.type != comp_b.type:
            dependents = graph_a.get_dependents(cid)
            risk = "critical" if dependents else "high"
            mods.append(DiffEntry(
                diff_type=DiffType.TYPE_CHANGED,
                entity_id=cid,
                old_value=comp_a.type.value,
                new_value=comp_b.type.value,
                risk_level=risk,
                description=(
                    f"Component '{cid}' type changed from "
                    f"{comp_a.type.value} to {comp_b.type.value}"
                ),
            ))

        # Replica change
        if comp_a.replicas != comp_b.replicas:
            if comp_b.replicas < comp_a.replicas:
                risk = "high" if comp_a.type in _CRITICAL_TYPES else "medium"
            else:
                risk = "low"
            mods.append(DiffEntry(
                diff_type=DiffType.REPLICAS_CHANGED,
                entity_id=cid,
                old_value=str(comp_a.replicas),
                new_value=str(comp_b.replicas),
                risk_level=risk,
                description=(
                    f"Component '{cid}' replicas changed from "
                    f"{comp_a.replicas} to {comp_b.replicas}"
                ),
            ))

        # Health change
        if comp_a.health != comp_b.health:
            if comp_b.health in (HealthStatus.DOWN, HealthStatus.OVERLOADED):
                risk = "critical"
            elif comp_b.health == HealthStatus.DEGRADED:
                risk = "medium"
            else:
                risk = "low"
            mods.append(DiffEntry(
                diff_type=DiffType.HEALTH_CHANGED,
                entity_id=cid,
                old_value=comp_a.health.value,
                new_value=comp_b.health.value,
                risk_level=risk,
                description=(
                    f"Component '{cid}' health changed from "
                    f"{comp_a.health.value} to {comp_b.health.value}"
                ),
            ))

        # Name change (tracked as component_modified)
        if comp_a.name != comp_b.name:
            mods.append(DiffEntry(
                diff_type=DiffType.COMPONENT_MODIFIED,
                entity_id=cid,
                old_value=comp_a.name,
                new_value=comp_b.name,
                risk_level="low",
                description=f"Component '{cid}' name changed from '{comp_a.name}' to '{comp_b.name}'",
            ))

        # Host/port change
        if comp_a.host != comp_b.host or comp_a.port != comp_b.port:
            mods.append(DiffEntry(
                diff_type=DiffType.COMPONENT_MODIFIED,
                entity_id=cid,
                old_value=f"{comp_a.host}:{comp_a.port}",
                new_value=f"{comp_b.host}:{comp_b.port}",
                risk_level="medium",
                description=f"Component '{cid}' endpoint changed",
            ))

        # Failover change
        if comp_a.failover.enabled != comp_b.failover.enabled:
            risk = "high" if not comp_b.failover.enabled else "low"
            mods.append(DiffEntry(
                diff_type=DiffType.COMPONENT_MODIFIED,
                entity_id=cid,
                old_value=f"failover={comp_a.failover.enabled}",
                new_value=f"failover={comp_b.failover.enabled}",
                risk_level=risk,
                description=(
                    f"Component '{cid}' failover "
                    f"{'disabled' if not comp_b.failover.enabled else 'enabled'}"
                ),
            ))

        # Autoscaling change
        if comp_a.autoscaling.enabled != comp_b.autoscaling.enabled:
            risk = "medium" if not comp_b.autoscaling.enabled else "low"
            mods.append(DiffEntry(
                diff_type=DiffType.COMPONENT_MODIFIED,
                entity_id=cid,
                old_value=f"autoscaling={comp_a.autoscaling.enabled}",
                new_value=f"autoscaling={comp_b.autoscaling.enabled}",
                risk_level=risk,
                description=(
                    f"Component '{cid}' autoscaling "
                    f"{'disabled' if not comp_b.autoscaling.enabled else 'enabled'}"
                ),
            ))

        return mods

    def _diff_dependency(self, src, tgt, edge_a, edge_b) -> list[DiffEntry]:
        """Detect modifications on a shared dependency edge."""
        mods: list[DiffEntry] = []
        eid = f"{src}->{tgt}"

        if edge_a.dependency_type != edge_b.dependency_type:
            risk = "high" if edge_b.dependency_type == "requires" else "medium"
            mods.append(DiffEntry(
                diff_type=DiffType.DEPENDENCY_MODIFIED,
                entity_id=eid,
                old_value=edge_a.dependency_type,
                new_value=edge_b.dependency_type,
                risk_level=risk,
                description=(
                    f"Dependency {src}->{tgt} type changed from "
                    f"'{edge_a.dependency_type}' to '{edge_b.dependency_type}'"
                ),
            ))

        if edge_a.weight != edge_b.weight:
            risk = "medium" if edge_b.weight > edge_a.weight else "low"
            mods.append(DiffEntry(
                diff_type=DiffType.DEPENDENCY_MODIFIED,
                entity_id=eid,
                old_value=str(edge_a.weight),
                new_value=str(edge_b.weight),
                risk_level=risk,
                description=(
                    f"Dependency {src}->{tgt} weight changed from "
                    f"{edge_a.weight} to {edge_b.weight}"
                ),
            ))

        # Circuit breaker toggled
        if edge_a.circuit_breaker.enabled != edge_b.circuit_breaker.enabled:
            risk = "medium" if not edge_b.circuit_breaker.enabled else "low"
            mods.append(DiffEntry(
                diff_type=DiffType.DEPENDENCY_MODIFIED,
                entity_id=eid,
                old_value=f"cb={edge_a.circuit_breaker.enabled}",
                new_value=f"cb={edge_b.circuit_breaker.enabled}",
                risk_level=risk,
                description=(
                    f"Dependency {src}->{tgt} circuit breaker "
                    f"{'disabled' if not edge_b.circuit_breaker.enabled else 'enabled'}"
                ),
            ))

        return mods

    def _component_add_risk(self, comp, graph: InfraGraph) -> str:
        """Assess risk level for adding a component."""
        if comp is None:
            return "low"
        if comp.type in _CRITICAL_TYPES:
            return "medium"
        dependents = graph.get_dependents(comp.id)
        if dependents:
            return "medium"
        return "low"

    def _component_remove_risk(self, comp, graph: InfraGraph) -> str:
        """Assess risk level for removing a component."""
        if comp is None:
            return "medium"
        dependents = graph.get_dependents(comp.id)
        if dependents:
            return "critical"
        if comp.type in _CRITICAL_TYPES:
            return "high"
        return "medium"

    def _dep_remove_risk(
        self, src: str, tgt: str, graph_a: InfraGraph, graph_b: InfraGraph
    ) -> str:
        """Assess risk level for removing a dependency edge."""
        # If the source component was also removed, the dep removal is expected.
        if src not in graph_b.components:
            return "low"
        edge = graph_a.get_dependency_edge(src, tgt)
        if edge and edge.dependency_type == "requires":
            return "critical"
        if edge and edge.dependency_type == "optional":
            return "medium"
        return "low"

    def _find_entry(
        self, diff: GraphDiff, entity_id: str, diff_type: DiffType
    ) -> DiffEntry | None:
        for e in diff.entries:
            if e.entity_id == entity_id and e.diff_type == diff_type:
                return e
        return None

    def _generate_recommendations(
        self, diff: GraphDiff, graph_a: InfraGraph, graph_b: InfraGraph
    ) -> list[str]:
        """Generate actionable recommendations based on the diff."""
        recs: list[str] = []

        # Removed components with dependents.
        for cid in diff.removed_components:
            comp = graph_a.get_component(cid)
            if comp:
                dependents = graph_a.get_dependents(cid)
                if dependents:
                    dep_names = ", ".join(d.id for d in dependents[:3])
                    recs.append(
                        f"Component '{cid}' is depended on by [{dep_names}]. "
                        "Ensure dependents are updated or rerouted before removal."
                    )

        # Replica reductions.
        for entry in diff.entries:
            if entry.diff_type == DiffType.REPLICAS_CHANGED:
                try:
                    old_val = int(entry.old_value)
                    new_val = int(entry.new_value)
                except (ValueError, TypeError):
                    continue
                if new_val < old_val:
                    recs.append(
                        f"Component '{entry.entity_id}' replicas reduced "
                        f"from {old_val} to {new_val}. "
                        "Verify capacity can handle current load."
                    )

        # Critical type changes.
        for entry in diff.entries:
            if entry.diff_type == DiffType.TYPE_CHANGED:
                recs.append(
                    f"Component '{entry.entity_id}' type changed "
                    f"({entry.old_value} -> {entry.new_value}). "
                    "Review all consumers for compatibility."
                )

        # Failover disabled.
        for entry in diff.entries:
            if (
                entry.diff_type == DiffType.COMPONENT_MODIFIED
                and "failover disabled" in entry.description.lower()
            ):
                recs.append(
                    f"Failover disabled on '{entry.entity_id}'. "
                    "Ensure alternative HA mechanism is in place."
                )

        # Health degradation.
        for entry in diff.entries:
            if entry.diff_type == DiffType.HEALTH_CHANGED:
                if entry.new_value in (HealthStatus.DOWN.value, HealthStatus.OVERLOADED.value):
                    recs.append(
                        f"Component '{entry.entity_id}' health degraded to "
                        f"{entry.new_value}. Investigate root cause."
                    )

        # Dependency type escalation to 'requires'.
        for entry in diff.entries:
            if (
                entry.diff_type == DiffType.DEPENDENCY_MODIFIED
                and entry.new_value == "requires"
                and entry.old_value != "requires"
            ):
                recs.append(
                    f"Dependency '{entry.entity_id}' escalated to 'requires'. "
                    "Ensure target component has adequate redundancy."
                )

        # Circuit breaker disabled.
        for entry in diff.entries:
            if (
                entry.diff_type == DiffType.DEPENDENCY_MODIFIED
                and "circuit breaker disabled" in entry.description.lower()
            ):
                recs.append(
                    f"Circuit breaker disabled on '{entry.entity_id}'. "
                    "This increases cascade failure risk."
                )

        # Deduplicate.
        seen: set[str] = set()
        unique: list[str] = []
        for r in recs:
            if r not in seen:
                seen.add(r)
                unique.append(r)
        return unique
