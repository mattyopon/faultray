"""Dependency Impact Matrix - shows how failure of each component impacts every other.

Builds a complete N x N matrix of impact relationships across all components
in the infrastructure graph, enabling identification of critical components,
vulnerability hotspots, and cascade risk paths.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum

from faultray.model.graph import InfraGraph


class ImpactLevel(str, Enum):
    """Severity classification derived from impact score."""

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ImpactCell:
    """Single cell in the impact matrix: effect of source failure on target."""

    source_id: str
    target_id: str
    impact_level: ImpactLevel
    impact_score: float  # 0-100
    path_length: int  # hops between components
    is_direct: bool  # direct dependency?
    description: str


@dataclass
class ComponentImpactProfile:
    """Aggregated impact profile for a single component."""

    component_id: str
    component_name: str
    blast_radius: int  # number of affected components
    max_impact_score: float
    avg_impact_score: float
    criticality_rank: int  # 1 = most critical
    direct_dependents: int
    transitive_dependents: int


@dataclass
class ImpactMatrix:
    """Complete impact matrix result."""

    cells: list[ImpactCell] = field(default_factory=list)
    component_profiles: list[ComponentImpactProfile] = field(default_factory=list)
    matrix_size: int = 0
    most_critical_component: str = ""
    most_vulnerable_component: str = ""
    avg_blast_radius: float = 0.0
    max_blast_radius: int = 0


def _score_to_level(score: float) -> ImpactLevel:
    """Convert a numeric impact score to an ImpactLevel classification."""
    if score >= 80:
        return ImpactLevel.CRITICAL
    if score >= 60:
        return ImpactLevel.HIGH
    if score >= 40:
        return ImpactLevel.MEDIUM
    if score >= 20:
        return ImpactLevel.LOW
    return ImpactLevel.NONE


class ImpactAnalyzer:
    """Analyzes dependency impact across all components in an InfraGraph."""

    def __init__(self, graph: InfraGraph) -> None:
        self._graph = graph

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_matrix(self) -> ImpactMatrix:
        """Build complete impact matrix for all components."""
        components = self._graph.components
        if not components:
            return ImpactMatrix()

        comp_ids = sorted(components.keys())
        matrix_size = len(comp_ids)

        # --- Build all cells ---------------------------------------------------
        cells: list[ImpactCell] = []
        # Per-source aggregation helpers
        blast_radii: dict[str, list[str]] = {}  # source_id -> affected ids
        source_scores: dict[str, list[float]] = {}
        source_direct: dict[str, int] = {}
        source_transitive: dict[str, int] = {}

        for src in comp_ids:
            affected = self.get_blast_radius(src)
            blast_radii[src] = affected
            scores: list[float] = []
            direct_count = 0
            transitive_count = 0

            for tgt in comp_ids:
                if src == tgt:
                    continue
                cell = self.get_impact(src, tgt)
                if cell is not None:
                    cells.append(cell)
                    scores.append(cell.impact_score)
                    if cell.is_direct:
                        direct_count += 1
                    else:
                        transitive_count += 1

            source_scores[src] = scores
            source_direct[src] = direct_count
            source_transitive[src] = transitive_count

        # --- Build component profiles -----------------------------------------
        profiles: list[ComponentImpactProfile] = []
        for src in comp_ids:
            sc = source_scores[src]
            profiles.append(
                ComponentImpactProfile(
                    component_id=src,
                    component_name=components[src].name,
                    blast_radius=len(blast_radii[src]),
                    max_impact_score=max(sc) if sc else 0.0,
                    avg_impact_score=sum(sc) / len(sc) if sc else 0.0,
                    criticality_rank=0,  # filled below
                    direct_dependents=source_direct[src],
                    transitive_dependents=source_transitive[src],
                )
            )

        # Sort for criticality ranking: descending blast_radius, then max_impact_score
        profiles.sort(
            key=lambda p: (p.blast_radius, p.max_impact_score), reverse=True
        )
        for idx, prof in enumerate(profiles, start=1):
            prof.criticality_rank = idx

        # --- Aggregate stats ---------------------------------------------------
        radii = [len(blast_radii[s]) for s in comp_ids]
        avg_blast = sum(radii) / len(radii) if radii else 0.0
        max_blast = max(radii) if radii else 0

        most_critical = profiles[0].component_id if profiles else ""
        most_vulnerable = self.find_most_vulnerable() if comp_ids else ""

        return ImpactMatrix(
            cells=cells,
            component_profiles=profiles,
            matrix_size=matrix_size,
            most_critical_component=most_critical,
            most_vulnerable_component=most_vulnerable,
            avg_blast_radius=avg_blast,
            max_blast_radius=max_blast,
        )

    def get_impact(self, source_id: str, target_id: str) -> ImpactCell | None:
        """Get impact of *source* failure on *target*.

        Returns ``None`` when there is no dependency path from source to target
        (i.e. the target is not affected by the source failure), or when either
        component does not exist in the graph.
        """
        if source_id == target_id:
            return None

        # Guard against components that are not in the graph
        if (
            self._graph.get_component(source_id) is None
            or self._graph.get_component(target_id) is None
        ):
            return None

        path = self.get_critical_path(source_id, target_id)
        if not path:
            return None

        path_length = len(path) - 1  # hops
        is_direct = path_length == 1
        score = 100.0 / path_length
        level = _score_to_level(score)

        src_comp = self._graph.get_component(source_id)
        tgt_comp = self._graph.get_component(target_id)
        src_name = src_comp.name if src_comp else source_id
        tgt_name = tgt_comp.name if tgt_comp else target_id

        if is_direct:
            desc = f"Direct dependency: {src_name} failure directly impacts {tgt_name}"
        else:
            desc = (
                f"Transitive impact ({path_length} hops): "
                f"{src_name} failure reaches {tgt_name} via {' -> '.join(path)}"
            )

        return ImpactCell(
            source_id=source_id,
            target_id=target_id,
            impact_level=level,
            impact_score=score,
            path_length=path_length,
            is_direct=is_direct,
            description=desc,
        )

    def get_blast_radius(self, component_id: str) -> list[str]:
        """Get all components affected by failure of *component_id*."""
        if self._graph.get_component(component_id) is None:
            return []
        affected = self._graph.get_all_affected(component_id)
        return sorted(affected)

    def get_critical_path(self, source_id: str, target_id: str) -> list[str]:
        """BFS shortest path from *source* to *target* through dependents.

        The path traverses **upstream** (from the failing component towards its
        dependents) so the direction matches the cascade propagation.
        Returns an empty list if either node does not exist in the graph.
        """
        if self._graph.get_component(source_id) is None:
            return []
        if source_id == target_id:
            return [source_id]
        if self._graph.get_component(target_id) is None:
            return []

        visited: set[str] = set()
        queue: deque[list[str]] = deque([[source_id]])
        visited.add(source_id)

        while queue:
            path = queue.popleft()
            current = path[-1]
            for dep in self._graph.get_dependents(current):
                if dep.id == target_id:
                    return path + [dep.id]
                if dep.id not in visited:
                    visited.add(dep.id)
                    queue.append(path + [dep.id])

        return []  # no path found

    def rank_by_criticality(self) -> list[ComponentImpactProfile]:
        """Rank components by criticality (blast radius desc, then max score)."""
        matrix = self.build_matrix()
        return matrix.component_profiles

    def find_most_vulnerable(self) -> str:
        """Find the component most affected by other failures.

        The most vulnerable component is the one that appears in the largest
        number of other components' blast radii.
        """
        components = self._graph.components
        if not components:
            return ""

        comp_ids = sorted(components.keys())
        vulnerability_count: dict[str, int] = {cid: 0 for cid in comp_ids}

        for src in comp_ids:
            affected = self._graph.get_all_affected(src)
            for a in affected:
                if a in vulnerability_count:
                    vulnerability_count[a] += 1

        if not vulnerability_count:
            return ""

        # Most vulnerable = highest count; tie-break by id for determinism
        return max(
            vulnerability_count,
            key=lambda cid: (vulnerability_count[cid], cid),
        )

    def format_matrix(self, matrix: ImpactMatrix) -> str:
        """Format *matrix* as a human-readable ASCII table."""
        if matrix.matrix_size == 0:
            return "Empty matrix (no components)"

        components = self._graph.components
        comp_ids = sorted(components.keys())

        # Build lookup: (source, target) -> ImpactCell
        cell_map: dict[tuple[str, str], ImpactCell] = {}
        for cell in matrix.cells:
            cell_map[(cell.source_id, cell.target_id)] = cell

        # Column width: accommodate longest id + padding
        col_w = max(len(cid) for cid in comp_ids)
        col_w = max(col_w, 6)  # minimum width for level labels
        header_w = col_w  # row header width

        # Header row
        header = " " * (header_w + 3)
        header += "  ".join(cid.center(col_w) for cid in comp_ids)
        lines: list[str] = [header]
        lines.append("-" * len(header))

        for src in comp_ids:
            row_parts: list[str] = []
            for tgt in comp_ids:
                if src == tgt:
                    row_parts.append("---".center(col_w))
                else:
                    cell = cell_map.get((src, tgt))
                    if cell:
                        label = cell.impact_level.value.upper()
                    else:
                        label = ImpactLevel.NONE.value.upper()
                    row_parts.append(label.center(col_w))
            lines.append(f"{src:<{header_w}} | {'  '.join(row_parts)}")

        lines.append("")
        lines.append(f"Most Critical:   {matrix.most_critical_component}")
        lines.append(f"Most Vulnerable: {matrix.most_vulnerable_component}")
        lines.append(f"Avg Blast Radius: {matrix.avg_blast_radius:.1f}")
        lines.append(f"Max Blast Radius: {matrix.max_blast_radius}")

        return "\n".join(lines)
