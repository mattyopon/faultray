# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Dependency Health Propagation Simulator.

Simulates how health issues propagate through dependency chains:
- **Forward propagation**: When component X fails, what downstream
  components (dependents) are affected?
- **Backward propagation**: When component X's dependency degrades,
  how does X's own health change?
- **What-if analysis**: ``what_if_fail`` / ``what_if_recover`` scenarios.

Each hop reduces the health impact by a configurable *decay factor*
(default 0.7), so distant components are less affected than immediate
neighbours.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum

from faultray.model.components import Component, HealthStatus
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Constants & helpers
# ---------------------------------------------------------------------------

_HEALTH_SCORE: dict[HealthStatus, float] = {
    HealthStatus.HEALTHY: 100.0,
    HealthStatus.DEGRADED: 60.0,
    HealthStatus.OVERLOADED: 35.0,
    HealthStatus.DOWN: 0.0,
}


def _health_to_score(status: HealthStatus) -> float:
    """Map a ``HealthStatus`` to a numeric score (0-100)."""
    return _HEALTH_SCORE.get(status, 50.0)


def _score_to_status(score: float) -> HealthStatus:
    """Map a numeric score back to the closest ``HealthStatus``."""
    if score >= 80.0:
        return HealthStatus.HEALTHY
    if score >= 50.0:
        return HealthStatus.DEGRADED
    if score >= 15.0:
        return HealthStatus.OVERLOADED
    return HealthStatus.DOWN


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class PropagationMode(str, Enum):
    """Direction(s) in which health propagation is analysed."""

    FORWARD = "forward"
    BACKWARD = "backward"
    BOTH = "both"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class HealthImpact:
    """Describes how a single component's health is projected to change."""

    component_id: str
    component_name: str
    original_health: float
    projected_health: float
    impact_severity: float  # 0-1 (1 = maximally severe)
    hop_distance: int
    propagation_path: list[str] = field(default_factory=list)


@dataclass
class PropagationReport:
    """Result of a health-propagation analysis."""

    source_component: str
    mode: PropagationMode
    impacts: list[HealthImpact] = field(default_factory=list)
    cascade_depth: int = 0
    total_affected: int = 0
    critical_paths: list[list[str]] = field(default_factory=list)
    summary: str = ""


@dataclass
class WhatIfResult:
    """Result of a what-if scenario analysis."""

    scenario: str
    impacts: list[HealthImpact] = field(default_factory=list)
    components_affected: int = 0
    severity_change: float = 0.0
    recommendations: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class DependencyHealthEngine:
    """Analyse health propagation through an ``InfraGraph``.

    Parameters
    ----------
    graph:
        The infrastructure dependency graph.
    decay_factor:
        Multiplier applied at each hop (``0 < decay <= 1``).
        Default ``0.7``.
    """

    def __init__(self, graph: InfraGraph, decay_factor: float = 0.7) -> None:
        self.graph = graph
        self.decay_factor = max(0.01, min(decay_factor, 1.0))

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def propagate(
        self,
        source_id: str,
        mode: PropagationMode = PropagationMode.BOTH,
    ) -> PropagationReport:
        """Propagate health from *source_id* in the given *mode*.

        Returns a :class:`PropagationReport` with all affected
        components, cascade depth, and critical paths.
        """
        comp = self.graph.get_component(source_id)
        if comp is None:
            return PropagationReport(
                source_component=source_id,
                mode=mode,
                summary=f"Component '{source_id}' not found.",
            )

        source_score = _health_to_score(comp.health)
        impacts: list[HealthImpact] = []
        max_depth = 0

        if mode in (PropagationMode.FORWARD, PropagationMode.BOTH):
            fwd_impacts, fwd_depth = self._propagate_forward(source_id, source_score)
            impacts.extend(fwd_impacts)
            max_depth = max(max_depth, fwd_depth)

        if mode in (PropagationMode.BACKWARD, PropagationMode.BOTH):
            bwd_impacts, bwd_depth = self._propagate_backward(source_id, source_score)
            # Avoid duplicates when mode is BOTH
            existing_ids = {i.component_id for i in impacts}
            for imp in bwd_impacts:
                if imp.component_id not in existing_ids:
                    impacts.append(imp)
                    existing_ids.add(imp.component_id)
            max_depth = max(max_depth, bwd_depth)

        # Deduplicate and sort by severity descending
        impacts.sort(key=lambda i: i.impact_severity, reverse=True)

        affected_count = sum(1 for i in impacts if i.impact_severity > 0.0)

        critical = self._find_critical_paths(source_id, impacts)

        parts: list[str] = [
            f"Propagation from '{comp.name}' (mode={mode.value}).",
            f"Cascade depth: {max_depth}.",
            f"Affected components: {affected_count}.",
        ]
        if critical:
            parts.append(f"Critical paths: {len(critical)}.")

        return PropagationReport(
            source_component=source_id,
            mode=mode,
            impacts=impacts,
            cascade_depth=max_depth,
            total_affected=affected_count,
            critical_paths=critical,
            summary=" ".join(parts),
        )

    def what_if_fail(self, component_id: str) -> WhatIfResult:
        """Simulate the impact of *component_id* going DOWN."""
        comp = self.graph.get_component(component_id)
        if comp is None:
            return WhatIfResult(
                scenario=f"fail({component_id})",
                recommendations=[f"Component '{component_id}' not found."],
            )

        original_health = comp.health
        original_score = _health_to_score(original_health)

        # Temporarily set to DOWN and propagate
        comp.health = HealthStatus.DOWN
        try:
            report = self.propagate(component_id, PropagationMode.FORWARD)
        finally:
            comp.health = original_health

        severity_delta = original_score - _health_to_score(HealthStatus.DOWN)
        recommendations = self._generate_fail_recommendations(
            comp, report.impacts, report.cascade_depth
        )

        return WhatIfResult(
            scenario=f"Component '{comp.name}' fails (goes DOWN)",
            impacts=report.impacts,
            components_affected=report.total_affected,
            severity_change=round(severity_delta / 100.0, 4),
            recommendations=recommendations,
        )

    def what_if_recover(self, component_id: str) -> WhatIfResult:
        """Simulate the impact of *component_id* recovering to HEALTHY."""
        comp = self.graph.get_component(component_id)
        if comp is None:
            return WhatIfResult(
                scenario=f"recover({component_id})",
                recommendations=[f"Component '{component_id}' not found."],
            )

        original_health = comp.health
        original_score = _health_to_score(original_health)

        comp.health = HealthStatus.HEALTHY
        try:
            report = self.propagate(component_id, PropagationMode.FORWARD)
        finally:
            comp.health = original_health

        recovery_delta = _health_to_score(HealthStatus.HEALTHY) - original_score
        recommendations = self._generate_recover_recommendations(
            comp, report.impacts, original_health
        )

        return WhatIfResult(
            scenario=f"Component '{comp.name}' recovers to HEALTHY",
            impacts=report.impacts,
            components_affected=report.total_affected,
            severity_change=round(recovery_delta / 100.0, 4),
            recommendations=recommendations,
        )

    def full_analysis(self) -> PropagationReport:
        """Analyse all currently unhealthy components.

        Combines the forward propagation from every non-HEALTHY component
        into a single :class:`PropagationReport`.
        """
        all_impacts: list[HealthImpact] = []
        max_depth = 0
        unhealthy_sources: list[str] = []

        for cid, comp in self.graph.components.items():
            if comp.health != HealthStatus.HEALTHY:
                unhealthy_sources.append(cid)
                source_score = _health_to_score(comp.health)
                fwd, depth = self._propagate_forward(cid, source_score)
                bwd, bdepth = self._propagate_backward(cid, source_score)
                for imp in fwd + bwd:
                    # Keep the worst impact per component
                    existing = next(
                        (i for i in all_impacts if i.component_id == imp.component_id),
                        None,
                    )
                    if existing is None:
                        all_impacts.append(imp)
                    elif imp.impact_severity > existing.impact_severity:
                        all_impacts.remove(existing)
                        all_impacts.append(imp)
                max_depth = max(max_depth, depth, bdepth)

        all_impacts.sort(key=lambda i: i.impact_severity, reverse=True)
        affected = sum(1 for i in all_impacts if i.impact_severity > 0.0)

        # Gather critical paths across all sources
        critical: list[list[str]] = []
        for src in unhealthy_sources:
            critical.extend(self._find_critical_paths(src, all_impacts))

        source_label = ", ".join(unhealthy_sources) if unhealthy_sources else "(none)"
        parts = [
            f"Full analysis: {len(unhealthy_sources)} unhealthy source(s): {source_label}.",
            f"Cascade depth: {max_depth}.",
            f"Affected components: {affected}.",
        ]

        return PropagationReport(
            source_component=source_label,
            mode=PropagationMode.BOTH,
            impacts=all_impacts,
            cascade_depth=max_depth,
            total_affected=affected,
            critical_paths=critical,
            summary=" ".join(parts),
        )

    # -----------------------------------------------------------------
    # Private: forward / backward propagation
    # -----------------------------------------------------------------

    def _propagate_forward(
        self, source_id: str, source_score: float
    ) -> tuple[list[HealthImpact], int]:
        """BFS from *source_id* to its **dependents** (components that
        depend *on* it).  This models downstream impact when a
        component degrades or fails.

        Returns ``(impacts, max_depth)``.
        """
        impacts: list[HealthImpact] = []
        visited: set[str] = {source_id}
        # queue items: (component_id, current_impact_factor, hop, path)
        queue: deque[tuple[str, float, int, list[str]]] = deque()

        for dep in self.graph.get_dependents(source_id):
            if dep.id not in visited:
                queue.append((dep.id, 1.0, 1, [source_id, dep.id]))

        max_depth = 0

        while queue:
            cid, factor, hop, path = queue.popleft()
            if cid in visited:
                continue
            visited.add(cid)
            max_depth = max(max_depth, hop)

            comp = self.graph.get_component(cid)
            if comp is None:
                continue

            decayed_factor = factor * (self.decay_factor ** hop)
            original_score = _health_to_score(comp.health)
            health_loss = (100.0 - source_score) * decayed_factor
            projected = max(0.0, original_score - health_loss)
            severity = min(1.0, health_loss / 100.0)

            impacts.append(
                HealthImpact(
                    component_id=cid,
                    component_name=comp.name,
                    original_health=original_score,
                    projected_health=round(projected, 2),
                    impact_severity=round(severity, 4),
                    hop_distance=hop,
                    propagation_path=list(path),
                )
            )

            for dep in self.graph.get_dependents(cid):
                if dep.id not in visited:
                    queue.append((dep.id, decayed_factor, hop + 1, path + [dep.id]))

        return impacts, max_depth

    def _propagate_backward(
        self, source_id: str, source_score: float
    ) -> tuple[list[HealthImpact], int]:
        """BFS from *source_id* to its **dependencies** (components
        that it depends *on*).  This models backward/upstream pressure:
        when a component degrades, it may increase load on its
        dependencies.

        Returns ``(impacts, max_depth)``.
        """
        impacts: list[HealthImpact] = []
        visited: set[str] = {source_id}
        queue: deque[tuple[str, float, int, list[str]]] = deque()

        for dep in self.graph.get_dependencies(source_id):
            if dep.id not in visited:
                queue.append((dep.id, 1.0, 1, [source_id, dep.id]))

        max_depth = 0

        while queue:
            cid, factor, hop, path = queue.popleft()
            if cid in visited:
                continue
            visited.add(cid)
            max_depth = max(max_depth, hop)

            comp = self.graph.get_component(cid)
            if comp is None:
                continue

            decayed_factor = factor * (self.decay_factor ** hop)
            original_score = _health_to_score(comp.health)
            # Backward pressure is gentler: half the intensity
            health_loss = (100.0 - source_score) * decayed_factor * 0.5
            projected = max(0.0, original_score - health_loss)
            severity = min(1.0, health_loss / 100.0)

            impacts.append(
                HealthImpact(
                    component_id=cid,
                    component_name=comp.name,
                    original_health=original_score,
                    projected_health=round(projected, 2),
                    impact_severity=round(severity, 4),
                    hop_distance=hop,
                    propagation_path=list(path),
                )
            )

            for dep in self.graph.get_dependencies(cid):
                if dep.id not in visited:
                    queue.append((dep.id, decayed_factor, hop + 1, path + [dep.id]))

        return impacts, max_depth

    # -----------------------------------------------------------------
    # Private: critical-path detection
    # -----------------------------------------------------------------

    def _find_critical_paths(
        self, source_id: str, impacts: list[HealthImpact]
    ) -> list[list[str]]:
        """Return propagation paths that lead to a component going DOWN.

        A path is *critical* if the projected health of the terminal
        component is below the DOWN threshold (< 15).
        """
        critical: list[list[str]] = []
        for imp in impacts:
            if imp.projected_health < 15.0 and imp.propagation_path:
                critical.append(list(imp.propagation_path))
        return critical

    # -----------------------------------------------------------------
    # Private: recommendation generation
    # -----------------------------------------------------------------

    def _generate_fail_recommendations(
        self,
        comp: Component,
        impacts: list[HealthImpact],
        cascade_depth: int,
    ) -> list[str]:
        recs: list[str] = []
        if comp.replicas <= 1:
            recs.append(
                f"Add replicas to '{comp.name}' to reduce single-point-of-failure risk."
            )
        if not comp.failover.enabled:
            recs.append(
                f"Enable failover for '{comp.name}' to allow automatic recovery."
            )
        if cascade_depth > 2:
            recs.append(
                "Deep cascade detected. Consider adding circuit breakers "
                "on intermediate dependencies."
            )
        critical_count = sum(1 for i in impacts if i.projected_health < 15.0)
        if critical_count > 0:
            recs.append(
                f"{critical_count} component(s) projected to go DOWN. "
                "Review dependency design and add redundancy."
            )
        if not impacts:
            recs.append("No downstream dependents detected; failure is isolated.")
        return recs

    def _generate_recover_recommendations(
        self,
        comp: Component,
        impacts: list[HealthImpact],
        original_health: HealthStatus,
    ) -> list[str]:
        recs: list[str] = []
        if original_health == HealthStatus.DOWN:
            recs.append(
                f"Recovering '{comp.name}' from DOWN to HEALTHY resolves "
                "a critical failure."
            )
        elif original_health == HealthStatus.DEGRADED:
            recs.append(
                f"Recovering '{comp.name}' from DEGRADED to HEALTHY "
                "improves system stability."
            )
        elif original_health == HealthStatus.OVERLOADED:
            recs.append(
                f"Recovering '{comp.name}' from OVERLOADED to HEALTHY "
                "relieves upstream pressure."
            )
        else:
            recs.append(f"'{comp.name}' is already HEALTHY; no recovery needed.")
        affected_count = sum(1 for i in impacts if i.impact_severity > 0.0)
        if affected_count > 0:
            recs.append(
                f"Recovery would positively affect {affected_count} dependent component(s)."
            )
        return recs
