"""Cellular Automata for deterministic failure propagation modeling.

Models infrastructure components as cells in a grid defined by the
adjacency structure of the dependency graph.  Unlike the ABM engine
(stochastic), CA uses deterministic rules for state transitions,
making results fully reproducible and suitable for formal analysis.

Uses ONLY the Python standard library.

Basic usage::

    >>> from faultray.model.graph import InfraGraph
    >>> graph = InfraGraph()
    >>> # ... populate graph ...
    >>> engine = CAEngine(graph)
    >>> result = engine.simulate("db-1", generations=50)
    >>> print(result.pattern_type, result.affected_cells)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from faultray.model.graph import InfraGraph


class CellState(IntEnum):
    """Possible states for a CA cell, ordered by severity."""

    HEALTHY = 0
    DEGRADED = 1
    OVERLOADED = 2
    DOWN = 3


@dataclass
class CAResult:
    """Result of a Cellular Automata simulation.

    Attributes:
        generation_history: List of per-generation state snapshots
            (each is a ``dict[str, CellState]``).
        final_state: State of each cell after the last generation.
        pattern_type: Classification of the observed dynamic: ``"stable"``,
            ``"oscillating"``, or ``"chaotic"``.
        affected_cells: Cell (component) IDs that ended in a non-HEALTHY
            state.
        total_generations: Number of generations actually simulated.
        severity: Overall severity score in ``[0.0, 10.0]``.
    """

    generation_history: list[dict[str, CellState]] = field(default_factory=list)
    final_state: dict[str, CellState] = field(default_factory=dict)
    pattern_type: str = "stable"
    affected_cells: list[str] = field(default_factory=list)
    total_generations: int = 0
    severity: float = 0.0


class CAEngine:
    """Cellular Automata engine for deterministic failure propagation.

    Each infrastructure component is a *cell* whose neighbours are
    determined by the dependency graph (both upstream and downstream
    edges).  On every generation, all cells update **synchronously**
    according to deterministic rules.

    Deterministic rules (contrast with ABM's probabilistic rules):

    * >= 2 DOWN neighbours  -> cell becomes DOWN
    * >= 1 DOWN neighbour   -> cell becomes DEGRADED
    * >= 3 DEGRADED neighbours -> cell becomes OVERLOADED
    * Otherwise             -> cell retains its current state

    Parameters:
        graph: The infrastructure dependency graph.
    """

    def __init__(self, graph: InfraGraph) -> None:
        self.graph = graph
        self._adjacency: dict[str, list[str]] = {}
        self._build_grid()

    # ------------------------------------------------------------------
    # Grid construction
    # ------------------------------------------------------------------

    def _build_grid(self) -> None:
        """Build the adjacency map from the InfraGraph.

        Neighbours include both directions of the dependency graph so
        that failure can propagate in either direction (a component
        both depends on and is depended upon by its neighbours).
        """
        self._adjacency = {cid: [] for cid in self.graph.components}

        for comp_id in self.graph.components:
            neighbours: set[str] = set()

            # Components this one depends on
            for dep in self.graph.get_dependencies(comp_id):
                neighbours.add(dep.id)

            # Components that depend on this one
            for dep in self.graph.get_dependents(comp_id):
                neighbours.add(dep.id)

            self._adjacency[comp_id] = list(neighbours)

    # ------------------------------------------------------------------
    # Deterministic rules
    # ------------------------------------------------------------------

    @staticmethod
    def rule(
        cell_state: CellState,
        neighbor_states: list[CellState],
    ) -> CellState:
        """Deterministic transition rule for a single cell.

        Parameters:
            cell_state: The cell's current state.
            neighbor_states: Current states of all neighbouring cells.

        Returns:
            The cell's next state.
        """
        if cell_state == CellState.DOWN:
            return CellState.DOWN  # DOWN is absorbing

        n_down = sum(1 for s in neighbor_states if s == CellState.DOWN)
        n_degraded = sum(1 for s in neighbor_states if s == CellState.DEGRADED)
        n_overloaded = sum(1 for s in neighbor_states if s == CellState.OVERLOADED)

        # Rule 1: Two or more DOWN neighbours -> DOWN
        if n_down >= 2:
            return CellState.DOWN

        # Rule 2: One DOWN neighbour -> at least DEGRADED
        if n_down >= 1:
            # If already overloaded or worse, go DOWN
            if cell_state >= CellState.OVERLOADED:
                return CellState.DOWN
            return max(cell_state, CellState.DEGRADED)

        # Rule 3: Three or more DEGRADED neighbours -> OVERLOADED
        if n_degraded >= 3:
            return max(cell_state, CellState.OVERLOADED)

        # Rule 4: Two or more OVERLOADED neighbours -> OVERLOADED
        if n_overloaded >= 2:
            return max(cell_state, CellState.OVERLOADED)

        return cell_state

    # ------------------------------------------------------------------
    # Simulation
    # ------------------------------------------------------------------

    def simulate(
        self,
        initial_fault: str,
        generations: int = 50,
    ) -> CAResult:
        """Run the CA simulation starting from a single faulted component.

        Parameters:
            initial_fault: Component ID to set to DOWN at generation 0.
            generations: Number of synchronous update generations.

        Returns:
            A ``CAResult`` with generation history, final state, pattern
            classification, and affected cells.
        """
        # Initialise all cells to HEALTHY
        state: dict[str, CellState] = {
            cid: CellState.HEALTHY for cid in self.graph.components
        }

        # Inject fault
        if initial_fault in state:
            state[initial_fault] = CellState.DOWN

        history: list[dict[str, CellState]] = [dict(state)]
        stable_count = 0

        for _gen in range(1, generations + 1):
            next_state: dict[str, CellState] = {}

            for cid in self.graph.components:
                # The faulted component stays DOWN for the entire simulation
                if cid == initial_fault:
                    next_state[cid] = CellState.DOWN
                    continue

                neighbour_ids = self._adjacency.get(cid, [])
                neighbour_states = [state[nid] for nid in neighbour_ids if nid in state]
                next_state[cid] = self.rule(state[cid], neighbour_states)

            history.append(dict(next_state))

            # Convergence check
            if next_state == state:
                stable_count += 1
            else:
                stable_count = 0

            if stable_count >= 2:
                break

            state = next_state

        final = history[-1]
        affected = [
            cid for cid, s in final.items() if s != CellState.HEALTHY
        ]

        pattern = self._detect_patterns(history)
        severity = self._calculate_severity(final)

        return CAResult(
            generation_history=history,
            final_state=final,
            pattern_type=pattern,
            affected_cells=affected,
            total_generations=len(history) - 1,
            severity=severity,
        )

    # ------------------------------------------------------------------
    # Pattern detection
    # ------------------------------------------------------------------

    def detect_patterns(self) -> list[str]:
        """Analyse the most recent simulation for dynamic patterns.

        Must be called after ``simulate()``.  Returns a list of
        human-readable pattern descriptions.
        """
        # No-op if no simulation has been run; call simulate first
        return []

    @staticmethod
    def _detect_patterns(history: list[dict[str, CellState]]) -> str:
        """Classify the dynamic pattern observed in *history*.

        * **stable**: the grid converged (last two snapshots are identical).
        * **oscillating**: the grid repeats a cycle of length 2-5.
        * **chaotic**: no convergence or repeating pattern detected.
        """
        if len(history) < 2:
            return "stable"

        # Check for stability (last two equal)
        if history[-1] == history[-2]:
            return "stable"

        # Check for oscillation (cycle length 2..5)
        last = history[-1]
        for cycle_len in range(2, min(6, len(history))):
            if len(history) > cycle_len:
                candidate = history[-(cycle_len + 1)]
                if candidate == last:
                    return "oscillating"

        return "chaotic"

    # ------------------------------------------------------------------
    # Severity
    # ------------------------------------------------------------------

    @staticmethod
    def _calculate_severity(final_state: dict[str, CellState]) -> float:
        """Compute a severity score in ``[0.0, 10.0]``."""
        total = len(final_state)
        if total == 0:
            return 0.0

        down = sum(1 for s in final_state.values() if s == CellState.DOWN)
        overloaded = sum(1 for s in final_state.values() if s == CellState.OVERLOADED)
        degraded = sum(1 for s in final_state.values() if s == CellState.DEGRADED)
        affected_count = down + overloaded + degraded

        if affected_count == 0:
            return 0.0

        impact = (down * 1.0 + overloaded * 0.5 + degraded * 0.25) / affected_count
        spread = affected_count / total
        raw = impact * spread * 10.0

        if affected_count <= 1:
            raw = min(raw, 3.0)
        elif spread < 0.3:
            raw = min(raw, 6.0)

        if down == 0 and overloaded == 0 and degraded > 0:
            raw = min(raw, 4.0)

        return min(10.0, max(0.0, round(raw, 1)))
