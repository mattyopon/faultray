"""Fault Tree Analysis (FTA) -- top-down deductive failure analysis.

Builds a Fault Tree from the infrastructure dependency graph and computes:
- Top-event probability (system failure probability)
- Minimal cut sets (smallest combinations that cause system failure)
- Critical component ranking

Uses ONLY the Python standard library.

Basic usage::

    >>> from faultray.model.graph import InfraGraph
    >>> graph = InfraGraph()
    >>> # ... populate graph ...
    >>> engine = FaultTreeEngine(graph)
    >>> result = engine.analyze()
    >>> print(result.top_event_probability, result.minimal_cut_sets)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from itertools import combinations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from faultray.model.graph import InfraGraph


class FTGate(str, Enum):
    """Gate types in a Fault Tree."""

    AND = "AND"
    OR = "OR"
    VOTING = "VOTING"  # k-of-n gate


@dataclass
class FTNode:
    """A node in the Fault Tree.

    Leaf nodes have no children and carry a base ``probability``.
    Intermediate nodes carry a ``gate_type`` and child references.

    Attributes:
        id: Unique node identifier.
        gate_type: Logic gate (AND / OR / VOTING) or ``None`` for leaves.
        children: Child nodes (empty for basic events / leaves).
        probability: Base failure probability for leaf nodes.
        k: Threshold for VOTING gates (k-of-n must fail).
        component_id: For leaf nodes, the corresponding component ID.
    """

    id: str
    gate_type: FTGate | None = None
    children: list[FTNode] = field(default_factory=list)
    probability: float = 0.0
    k: int = 1
    component_id: str | None = None


@dataclass
class FTAResult:
    """Result of a Fault Tree Analysis.

    Attributes:
        top_event_probability: Probability of the top-level system failure.
        minimal_cut_sets: Minimal combinations of basic events that cause
            the top event.
        critical_components: Component IDs ranked by contribution to the
            top-event probability (highest first).
        tree: The root ``FTNode`` of the constructed Fault Tree.
    """

    top_event_probability: float = 0.0
    minimal_cut_sets: list[set[str]] = field(default_factory=list)
    critical_components: list[str] = field(default_factory=list)
    tree: FTNode | None = None


class FaultTreeEngine:
    """Fault Tree Analysis engine for infrastructure graphs.

    Constructs a Fault Tree by walking the dependency graph in reverse:

    * **requires** dependencies become **OR** gates in the tree (any one
      failing causes impact).
    * **optional** dependencies are excluded (non-critical).
    * Components with ``replicas > 1`` use a **VOTING** gate
      (``n - replicas + 1`` of ``n`` must fail).

    Base failure probabilities are derived from component MTBF values.

    Parameters:
        graph: The infrastructure dependency graph.
    """

    # Default base failure probability when MTBF is not set
    _DEFAULT_FAILURE_PROB = 0.01

    def __init__(self, graph: InfraGraph) -> None:
        self.graph = graph

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_tree(self, top_event: str = "system_failure") -> FTNode:
        """Build the Fault Tree from the infrastructure graph.

        The root represents *system failure*.  For each component that has
        no dependents (i.e. entry points / user-facing), if **any** fails
        the system is considered failed (OR gate at root).

        Parameters:
            top_event: Label for the root node.

        Returns:
            The root ``FTNode``.
        """
        # Find entry-point components (those that nothing depends on, i.e.
        # they have no "predecessors" in the reversed view, which means
        # nothing lists them as a dependency target).
        entry_points: list[str] = []
        for cid in self.graph.components:
            dependents = self.graph.get_dependents(cid)
            if not dependents:
                entry_points.append(cid)

        # If every component has dependents, fall back to all components
        if not entry_points:
            entry_points = list(self.graph.components.keys())

        # Build sub-trees for each entry point
        visited: set[str] = set()
        children: list[FTNode] = []
        for cid in entry_points:
            subtree = self._build_subtree(cid, visited)
            if subtree is not None:
                children.append(subtree)

        root = FTNode(
            id=top_event,
            gate_type=FTGate.OR,
            children=children,
        )
        return root

    def compute_probability(self, node: FTNode) -> float:
        """Compute the failure probability of *node* bottom-up.

        Leaf nodes return their base probability.  Gate nodes combine
        children's probabilities according to the gate type.
        """
        if not node.children:
            return node.probability

        child_probs = [self.compute_probability(c) for c in node.children]

        if node.gate_type == FTGate.OR:
            # P(OR) = 1 - product(1 - p_i)
            product = 1.0
            for p in child_probs:
                product *= (1.0 - p)
            return 1.0 - product

        if node.gate_type == FTGate.AND:
            # P(AND) = product(p_i)
            product = 1.0
            for p in child_probs:
                product *= p
            return product

        if node.gate_type == FTGate.VOTING:
            # P(k-of-n) = sum over all combos of k+ failures
            n = len(child_probs)
            k = node.k
            total = 0.0
            for r in range(k, n + 1):
                for combo in combinations(range(n), r):
                    prob = 1.0
                    for i in range(n):
                        if i in combo:
                            prob *= child_probs[i]
                        else:
                            prob *= (1.0 - child_probs[i])
                    total += prob
            return min(1.0, total)

        return 0.0

    def minimal_cut_sets(self, node: FTNode) -> list[set[str]]:
        """Compute the minimal cut sets of the Fault Tree rooted at *node*.

        A *cut set* is a set of basic events (leaf component IDs) whose
        simultaneous occurrence causes the top event.  A *minimal* cut set
        has no proper subset that is also a cut set.

        Returns:
            List of sets, each set containing component IDs.
        """
        raw = self._cut_sets(node)
        return self._minimise(raw)

    def analyze(self) -> FTAResult:
        """Run a complete Fault Tree Analysis.

        Builds the tree, computes probability, extracts cut sets, and
        ranks critical components.
        """
        tree = self.build_tree()
        probability = self.compute_probability(tree)
        cut_sets = self.minimal_cut_sets(tree)

        # Rank components by how many minimal cut sets they appear in
        component_count: dict[str, int] = {}
        for cs in cut_sets:
            for cid in cs:
                component_count[cid] = component_count.get(cid, 0) + 1
        critical = sorted(component_count, key=lambda c: component_count[c], reverse=True)

        return FTAResult(
            top_event_probability=round(probability, 6),
            minimal_cut_sets=cut_sets,
            critical_components=critical,
            tree=tree,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_subtree(self, comp_id: str, visited: set[str]) -> FTNode | None:
        """Recursively build the FT subtree for *comp_id*."""
        if comp_id in visited:
            # Avoid cycles; return a leaf referencing the component
            return self._make_leaf(comp_id)
        visited.add(comp_id)

        comp = self.graph.get_component(comp_id)
        if comp is None:
            return None

        # Get required dependencies (children in the FT)
        dependencies = self.graph.get_dependencies(comp_id)
        required_deps: list[str] = []
        for dep_comp in dependencies:
            edge = self.graph.get_dependency_edge(comp_id, dep_comp.id)
            if edge and edge.dependency_type == "optional":
                continue  # skip optional
            required_deps.append(dep_comp.id)

        if not required_deps:
            # Leaf node -- base event
            return self._make_leaf(comp_id)

        # Build children subtrees
        children: list[FTNode] = []
        for dep_id in required_deps:
            child = self._build_subtree(dep_id, visited)
            if child is not None:
                children.append(child)

        if not children:
            return self._make_leaf(comp_id)

        # Determine gate type
        if comp.replicas > 1:
            # VOTING gate: need (n - replicas + 1) failures out of n deps
            # to cause this component to fail
            k = max(1, len(children) - comp.replicas + 2)
            k = min(k, len(children))
            node = FTNode(
                id=f"vote_{comp_id}",
                gate_type=FTGate.VOTING,
                children=children,
                k=k,
            )
        else:
            # OR gate: any single dependency failing impacts this component
            node = FTNode(
                id=f"or_{comp_id}",
                gate_type=FTGate.OR,
                children=children,
            )

        return node

    def _make_leaf(self, comp_id: str) -> FTNode:
        """Create a leaf node for a component with its base failure probability."""
        comp = self.graph.get_component(comp_id)
        prob = self._DEFAULT_FAILURE_PROB
        if comp is not None:
            mtbf_hours = comp.operational_profile.mtbf_hours
            if mtbf_hours > 0:
                # Probability of failure in a 1-hour window
                prob = 1.0 - math.exp(-1.0 / mtbf_hours)
        return FTNode(
            id=f"leaf_{comp_id}",
            probability=prob,
            component_id=comp_id,
        )

    def _cut_sets(self, node: FTNode) -> list[set[str]]:
        """Recursively compute cut sets (not yet minimised)."""
        if not node.children:
            # Leaf
            if node.component_id:
                return [{node.component_id}]
            return [set()]

        child_cut_sets = [self._cut_sets(c) for c in node.children]

        if node.gate_type == FTGate.OR:
            # OR: union of all children's cut sets
            result: list[set[str]] = []
            for ccs in child_cut_sets:
                result.extend(ccs)
            return result

        if node.gate_type == FTGate.AND:
            # AND: Cartesian product (cross-product) of children's cut sets
            result = [set()]
            for ccs in child_cut_sets:
                new_result: list[set[str]] = []
                for existing in result:
                    for cs in ccs:
                        new_result.append(existing | cs)
                result = new_result
            return result

        if node.gate_type == FTGate.VOTING:
            # VOTING(k-of-n): combine cut sets from any k children
            n = len(child_cut_sets)
            k = node.k
            result = []
            for combo in combinations(range(n), k):
                # Cartesian product of selected children
                partial: list[set[str]] = [set()]
                for idx in combo:
                    new_partial: list[set[str]] = []
                    for existing in partial:
                        for cs in child_cut_sets[idx]:
                            new_partial.append(existing | cs)
                    partial = new_partial
                result.extend(partial)
            return result

        return [set()]

    @staticmethod
    def _minimise(cut_sets: list[set[str]]) -> list[set[str]]:
        """Remove non-minimal cut sets (supersets of other cut sets)."""
        # Sort by size so we process smaller sets first
        sorted_sets = sorted(cut_sets, key=len)
        minimal: list[set[str]] = []
        for cs in sorted_sets:
            if not cs:
                continue
            # Check if any existing minimal set is a subset of cs
            is_superset = any(m.issubset(cs) for m in minimal)
            if not is_superset:
                minimal.append(cs)
        return minimal
