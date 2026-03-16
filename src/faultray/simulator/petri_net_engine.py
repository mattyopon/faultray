"""Petri Net modeling for concurrent failure analysis.

Maps each infrastructure component to a set of places (healthy / degraded /
down) and each dependency to a transition that models failure propagation.
Supports reachability analysis and deadlock detection.

Uses ONLY the Python standard library.

Basic usage::

    >>> from faultray.model.graph import InfraGraph
    >>> graph = InfraGraph()
    >>> # ... populate graph ...
    >>> engine = PetriNetEngine(graph)
    >>> result = engine.simulate({"db-1_healthy": 0, "db-1_down": 1})
    >>> print(result.deadlock_detected, result.firing_sequence)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from faultray.model.graph import InfraGraph


@dataclass
class Place:
    """A place in the Petri Net, holding a non-negative token count.

    Attributes:
        id: Unique identifier (e.g. ``"web-1_healthy"``).
        tokens: Current number of tokens.
        name: Human-readable label.
    """

    id: str
    tokens: int = 0
    name: str = ""


@dataclass
class Transition:
    """A transition in the Petri Net.

    A transition is *enabled* when every input place has at least one token
    and the optional ``guard`` function returns ``True``.

    Attributes:
        id: Unique identifier.
        input_places: Place IDs that provide tokens to this transition.
        output_places: Place IDs that receive tokens when fired.
        guard: Optional callable ``(dict[str,int]) -> bool`` evaluated on
            the current marking.
        name: Human-readable label.
    """

    id: str
    input_places: list[str] = field(default_factory=list)
    output_places: list[str] = field(default_factory=list)
    guard: Callable[[dict[str, int]], bool] | None = None
    name: str = ""


@dataclass
class PetriNetResult:
    """Result of a Petri Net simulation run.

    Attributes:
        final_marking: Token counts per place at the end of simulation.
        firing_sequence: Ordered list of transition IDs that fired.
        reachable_states: Set of reachable markings (each as a frozenset
            of ``(place_id, tokens)`` pairs).
        deadlock_detected: Whether the net reached a state with no enabled
            transitions.
    """

    final_marking: dict[str, int] = field(default_factory=dict)
    firing_sequence: list[str] = field(default_factory=list)
    reachable_states: set[frozenset[tuple[str, int]]] = field(default_factory=set)
    deadlock_detected: bool = False


class PetriNetEngine:
    """Petri Net engine for concurrent failure analysis.

    The infrastructure graph is automatically converted into a Petri Net:

    * Each component yields three places: ``{id}_healthy``,
      ``{id}_degraded``, ``{id}_down``.
    * Initially, one token resides in the ``_healthy`` place of every
      component.
    * Each dependency edge yields transitions that propagate failure
      states from one component to another.

    Parameters:
        graph: The infrastructure dependency graph.
    """

    def __init__(self, graph: InfraGraph) -> None:
        self.graph = graph
        self._places: dict[str, Place] = {}
        self._transitions: list[Transition] = []
        self.build_net()

    # ------------------------------------------------------------------
    # Net construction
    # ------------------------------------------------------------------

    def build_net(self) -> None:
        """Convert the InfraGraph into a Petri Net."""
        self._places = {}
        self._transitions = []

        # Create three places per component
        for comp_id in self.graph.components:
            self._places[f"{comp_id}_healthy"] = Place(
                id=f"{comp_id}_healthy",
                tokens=1,
                name=f"{comp_id} healthy",
            )
            self._places[f"{comp_id}_degraded"] = Place(
                id=f"{comp_id}_degraded",
                tokens=0,
                name=f"{comp_id} degraded",
            )
            self._places[f"{comp_id}_down"] = Place(
                id=f"{comp_id}_down",
                tokens=0,
                name=f"{comp_id} down",
            )

        # Create transitions for each dependency
        t_counter = 0
        for comp_id in self.graph.components:
            dependencies = self.graph.get_dependencies(comp_id)
            for dep_comp in dependencies:
                edge = self.graph.get_dependency_edge(comp_id, dep_comp.id)
                dep_type = edge.dependency_type if edge else "requires"

                if dep_type == "requires":
                    # If dependency goes DOWN -> this component degrades
                    self._transitions.append(
                        Transition(
                            id=f"t{t_counter}_cascade_degrade",
                            input_places=[
                                f"{dep_comp.id}_down",
                                f"{comp_id}_healthy",
                            ],
                            output_places=[
                                f"{dep_comp.id}_down",  # dep stays down
                                f"{comp_id}_degraded",  # comp degrades
                            ],
                            name=f"Cascade {dep_comp.id}->DOWN causes {comp_id}->DEGRADED",
                        )
                    )
                    t_counter += 1

                    # If dependency DOWN and comp already degraded -> comp goes DOWN
                    self._transitions.append(
                        Transition(
                            id=f"t{t_counter}_cascade_down",
                            input_places=[
                                f"{dep_comp.id}_down",
                                f"{comp_id}_degraded",
                            ],
                            output_places=[
                                f"{dep_comp.id}_down",
                                f"{comp_id}_down",
                            ],
                            name=f"Cascade {dep_comp.id}->DOWN causes {comp_id}->DOWN",
                        )
                    )
                    t_counter += 1

                elif dep_type == "optional":
                    # Optional: dependency DOWN only degrades this component
                    self._transitions.append(
                        Transition(
                            id=f"t{t_counter}_opt_degrade",
                            input_places=[
                                f"{dep_comp.id}_down",
                                f"{comp_id}_healthy",
                            ],
                            output_places=[
                                f"{dep_comp.id}_down",
                                f"{comp_id}_degraded",
                            ],
                            name=f"Optional dep {dep_comp.id}->DOWN degrades {comp_id}",
                        )
                    )
                    t_counter += 1

                elif dep_type == "async":
                    # Async: slow degradation
                    self._transitions.append(
                        Transition(
                            id=f"t{t_counter}_async_degrade",
                            input_places=[
                                f"{dep_comp.id}_down",
                                f"{comp_id}_healthy",
                            ],
                            output_places=[
                                f"{dep_comp.id}_down",
                                f"{comp_id}_degraded",
                            ],
                            name=f"Async dep {dep_comp.id}->DOWN degrades {comp_id}",
                        )
                    )
                    t_counter += 1

        # Recovery transitions for each component
        for comp_id in self.graph.components:
            self._transitions.append(
                Transition(
                    id=f"t{t_counter}_recovery_{comp_id}",
                    input_places=[f"{comp_id}_down"],
                    output_places=[f"{comp_id}_healthy"],
                    name=f"Recovery of {comp_id}",
                )
            )
            t_counter += 1

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fire_transition(self, transition: Transition) -> bool:
        """Attempt to fire a transition.

        Returns ``True`` if the transition was enabled and fired,
        ``False`` otherwise.
        """
        marking = self._current_marking()

        # Check guard
        if transition.guard is not None and not transition.guard(marking):
            return False

        # Check all input places have tokens
        for pid in transition.input_places:
            place = self._places.get(pid)
            if place is None or place.tokens < 1:
                return False

        # Consume tokens from inputs
        for pid in transition.input_places:
            self._places[pid].tokens -= 1

        # Produce tokens in outputs
        for pid in transition.output_places:
            if pid in self._places:
                self._places[pid].tokens += 1

        return True

    def simulate(
        self,
        initial_marking: dict[str, int] | None = None,
        max_steps: int = 100,
    ) -> PetriNetResult:
        """Run the Petri Net simulation.

        Parameters:
            initial_marking: Override token counts for specific places.
                E.g. ``{"db-1_healthy": 0, "db-1_down": 1}`` to inject
                a fault on ``db-1``.
            max_steps: Maximum firing steps.

        Returns:
            A ``PetriNetResult`` with final marking, firing sequence,
            reachable states and deadlock flag.
        """
        # Reset to default marking (all healthy)
        for place in self._places.values():
            if place.id.endswith("_healthy"):
                place.tokens = 1
            else:
                place.tokens = 0

        # Apply initial marking overrides
        if initial_marking:
            for pid, tokens in initial_marking.items():
                if pid in self._places:
                    self._places[pid].tokens = tokens

        firing_sequence: list[str] = []
        reachable: set[frozenset[tuple[str, int]]] = set()
        reachable.add(self._marking_key())

        deadlock = False

        for _step in range(max_steps):
            # Find all enabled transitions
            enabled = [t for t in self._transitions if self._is_enabled(t)]

            if not enabled:
                deadlock = True
                break

            # Fire the first enabled transition (deterministic)
            fired = False
            for t in enabled:
                if self.fire_transition(t):
                    firing_sequence.append(t.id)
                    fired = True
                    break

            if not fired:
                deadlock = True
                break

            mk = self._marking_key()
            if mk in reachable:
                # Already visited this marking -- stop to avoid infinite loops
                break
            reachable.add(mk)

        return PetriNetResult(
            final_marking=self._current_marking(),
            firing_sequence=firing_sequence,
            reachable_states=reachable,
            deadlock_detected=deadlock,
        )

    def reachability_analysis(self) -> set[frozenset[tuple[str, int]]]:
        """Compute the full reachability set via BFS from current marking.

        Warning: This may be large for complex graphs.
        """
        from collections import deque

        initial = self._marking_key()
        visited: set[frozenset[tuple[str, int]]] = {initial}
        queue: deque[frozenset[tuple[str, int]]] = deque([initial])

        max_states = 10000  # safety cap

        while queue and len(visited) < max_states:
            state = queue.popleft()

            # Restore marking from frozen state
            self._restore_marking(state)

            for t in self._transitions:
                if not self._is_enabled(t):
                    continue

                # Save current, fire, capture new state, restore
                saved = self._marking_key()
                self.fire_transition(t)
                new_state = self._marking_key()
                self._restore_marking(saved)

                if new_state not in visited:
                    visited.add(new_state)
                    queue.append(new_state)

        return visited

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_enabled(self, transition: Transition) -> bool:
        """Check whether a transition is enabled."""
        for pid in transition.input_places:
            place = self._places.get(pid)
            if place is None or place.tokens < 1:
                return False
        if transition.guard is not None:
            if not transition.guard(self._current_marking()):
                return False
        return True

    def _current_marking(self) -> dict[str, int]:
        """Return the current token counts as a dict."""
        return {pid: p.tokens for pid, p in self._places.items()}

    def _marking_key(self) -> frozenset[tuple[str, int]]:
        """Return the current marking as a hashable frozenset."""
        return frozenset(
            (pid, p.tokens)
            for pid, p in self._places.items()
            if p.tokens > 0
        )

    def _restore_marking(self, state: frozenset[tuple[str, int]]) -> None:
        """Restore the net to a specific marking."""
        token_map = dict(state)
        for pid, place in self._places.items():
            place.tokens = token_map.get(pid, 0)
