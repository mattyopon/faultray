"""Formal methods for infrastructure resilience verification.

Contains three complementary formal/semi-formal analysis techniques:

1. **ReliabilityBlockDiagram (RBD)** — models system availability as a
   composition of series (all-must-work) and parallel (any-one-suffices)
   blocks.
   *Difference from FTA (fault_tree_engine.py)*: FTA uses AND/OR gates
   on *failure* events (top-down deductive); RBD uses block connectivity
   on *success* paths (bottom-up structural).

2. **EventTreeAnalysis (ETA)** — inductive forward analysis from an
   initiating event through a series of branching safety functions.
   *Difference from FTA*: FTA works backwards from a top event; ETA
   works forwards from an initiating event, enumerating all possible
   outcome sequences and their probabilities.

3. **SimpleModelChecker** — exhaustive state-space exploration with
   CTL-like property verification.
   *Difference from Petri Net (petri_net_engine.py)*: Petri nets model
   concurrency via token flow; the model checker operates on explicit
   states and supports temporal-logic property checking (AG, EF, AF)
   that go beyond simple reachability.

All implementations use **standard library only** (collections, itertools).
"""

from __future__ import annotations

import itertools
from collections import deque
from dataclasses import dataclass, field

from faultray.model.components import HealthStatus
from faultray.model.graph import InfraGraph


# =====================================================================
# Reliability Block Diagram (RBD)
# =====================================================================

@dataclass
class RBDResult:
    """Result of an RBD availability computation.

    Attributes:
        system_availability: Overall system availability (0.0–1.0).
        component_contributions: Per-component contribution to system
            availability.
        block_structure: Human-readable description of the block topology.
    """

    system_availability: float = 0.0
    component_contributions: dict[str, float] = field(default_factory=dict)
    block_structure: str = ""


class ReliabilityBlockDiagram:
    """Reliability Block Diagram analyser.

    Converts an InfraGraph into a block diagram:
      - **Series blocks**: components connected by ``requires`` dependencies
        form a series chain: ``P_system = P_1 × P_2 × ... × P_n``.
        All must work for the path to succeed (weakest-link).
      - **Parallel blocks**: a component with ``replicas > 1`` or failover
        enabled has internal redundancy:
        ``P_parallel = 1 - (1-P_single)^replicas``.

    Individual component availability is derived from MTBF and MTTR:
        ``A = MTBF / (MTBF + MTTR)``

    Args:
        graph: Infrastructure dependency graph.
        default_availability: Availability assumed when MTBF is not set.
    """

    def __init__(
        self, graph: InfraGraph, default_availability: float = 0.999
    ) -> None:
        self.graph = graph
        self.default_availability = default_availability

    def _component_availability(self, comp) -> float:
        """Compute single-instance availability from MTBF/MTTR."""
        mtbf = comp.operational_profile.mtbf_hours
        mttr_hours = comp.operational_profile.mttr_minutes / 60.0
        if mtbf > 0:
            return mtbf / (mtbf + mttr_hours)
        return self.default_availability

    def _effective_availability(self, comp) -> float:
        """Availability considering replicas (parallel redundancy)."""
        single = self._component_availability(comp)
        replicas = comp.replicas
        if comp.failover.enabled:
            replicas = max(replicas, 2)
        if replicas <= 1:
            return single
        # Parallel: 1 - (1 - A_single)^n
        return 1.0 - (1.0 - single) ** replicas

    def compute_availability(self) -> RBDResult:
        """Compute system-level availability from the block diagram.

        The algorithm identifies all root-to-leaf paths in the dependency
        graph.  Each path is a *series* chain.  Multiple independent paths
        between the same endpoints provide *parallel* redundancy.

        Returns:
            An :class:`RBDResult` with overall availability and breakdown.
        """
        components = self.graph.components
        if not components:
            return RBDResult()

        # Compute effective availability per component
        avail: dict[str, float] = {}
        for cid, comp in components.items():
            avail[cid] = self._effective_availability(comp)

        contributions = dict(avail)

        # Find critical paths (root → leaf chains)
        critical_paths = self.graph.get_critical_paths(max_paths=50)

        if not critical_paths:
            # No dependency paths — treat all components as parallel
            system_avail = 1.0 - math.prod(1.0 - a for a in avail.values())
            return RBDResult(
                system_availability=round(system_avail, 6),
                component_contributions=contributions,
                block_structure="parallel(all components)",
            )

        # Each path is a series chain; paths are parallel alternatives
        path_availabilities: list[float] = []
        path_descriptions: list[str] = []
        for path in critical_paths:
            # Series: multiply availability along path
            path_avail = 1.0
            for cid in path:
                path_avail *= avail.get(cid, self.default_availability)
            path_availabilities.append(path_avail)
            path_descriptions.append(" → ".join(path))

        # Overall: parallel combination of all paths
        # (conservative — assumes paths are independent)
        if len(path_availabilities) == 1:
            system_avail = path_availabilities[0]
        else:
            # The system is UP if *any* path is UP
            system_avail = 1.0 - 1.0
            # Actually: system availability ≈ max(path availabilities)
            # for series-parallel, use: 1 - prod(1 - p_i)
            system_fail = 1.0
            for pa in path_availabilities:
                system_fail *= (1.0 - pa)
            system_avail = 1.0 - system_fail

        structure = "; ".join(
            f"series({desc}) = {pa:.6f}"
            for desc, pa in zip(path_descriptions, path_availabilities)
        )

        return RBDResult(
            system_availability=round(max(0.0, min(1.0, system_avail)), 6),
            component_contributions=contributions,
            block_structure=structure,
        )


# Need math for the RBD — import at module level is fine since math is stdlib
import math  # noqa: E402


# =====================================================================
# Event Tree Analysis (ETA)
# =====================================================================

@dataclass
class ETABranch:
    """A branching point in an event tree.

    Attributes:
        event_name: Name of the safety function or barrier.
        success_prob: Probability that the safety function succeeds.
        failure_prob: Probability that the safety function fails.
    """

    event_name: str = ""
    success_prob: float = 0.9
    failure_prob: float = 0.1

    def __post_init__(self) -> None:
        # Ensure consistency
        if self.failure_prob <= 0:
            self.failure_prob = 1.0 - self.success_prob
        if self.success_prob <= 0:
            self.success_prob = 1.0 - self.failure_prob


@dataclass
class ETAOutcome:
    """A single outcome path through the event tree.

    Attributes:
        sequence: Ordered list of (event_name, "success"|"failure") pairs.
        probability: Combined probability of this outcome path.
        severity: Estimated severity label.
    """

    sequence: list[tuple[str, str]] = field(default_factory=list)
    probability: float = 0.0
    severity: str = "low"


@dataclass
class ETAResult:
    """Complete result of an Event Tree Analysis.

    Attributes:
        initiating_event: Description of the triggering event.
        outcomes: All possible outcome paths with probabilities.
        total_risk: Sum of probability × severity_weight across outcomes.
    """

    initiating_event: str = ""
    outcomes: list[ETAOutcome] = field(default_factory=list)
    total_risk: float = 0.0


class EventTreeAnalysis:
    """Event Tree Analysis (ETA) for inductive forward risk assessment.

    Starting from an *initiating event* (e.g., a component failure), the
    analysis traces forward through a sequence of safety barriers or
    mitigation functions, each of which can succeed or fail.  The result
    is a tree of all possible outcome sequences with their probabilities.

    This is the *inductive* complement to Fault Tree Analysis (FTA) which
    works *deductively* backward from a top event.

    Args:
        graph: Infrastructure dependency graph (used to auto-generate
            branches from component resilience features).
    """

    def __init__(self, graph: InfraGraph) -> None:
        self.graph = graph

    def build_tree(self, initiating_event: str) -> list[ETABranch]:
        """Auto-generate ETA branches from component resilience features.

        For each safety barrier that could mitigate the initiating event,
        a branch is created with success/failure probabilities derived from
        the component configuration.

        Args:
            initiating_event: Component ID of the initially failing component.

        Returns:
            A list of :class:`ETABranch` representing the safety barriers.
        """
        comp = self.graph.get_component(initiating_event)
        branches: list[ETABranch] = []

        if not comp:
            return branches

        # Branch 1: Circuit breaker on incoming edges
        dependents = self.graph.get_dependents(initiating_event)
        cb_count = 0
        for dep in dependents:
            edge = self.graph.get_dependency_edge(dep.id, initiating_event)
            if edge and edge.circuit_breaker.enabled:
                cb_count += 1
        if dependents:
            cb_ratio = cb_count / len(dependents)
            branches.append(ETABranch(
                event_name="Circuit Breaker Activation",
                success_prob=min(0.99, 0.5 + cb_ratio * 0.45),
            ))

        # Branch 2: Failover
        if comp.failover.enabled:
            branches.append(ETABranch(
                event_name="Failover to Standby",
                success_prob=0.95,
            ))
        else:
            branches.append(ETABranch(
                event_name="Failover to Standby",
                success_prob=0.1,
            ))

        # Branch 3: Autoscaling
        if comp.autoscaling.enabled:
            branches.append(ETABranch(
                event_name="Autoscaling Response",
                success_prob=0.85,
            ))

        # Branch 4: Replica redundancy
        if comp.replicas > 1:
            p_all_fail = (0.01) ** comp.replicas  # rough estimate
            branches.append(ETABranch(
                event_name="Replica Redundancy",
                success_prob=1.0 - p_all_fail,
            ))

        # Ensure at least one branch
        if not branches:
            branches.append(ETABranch(
                event_name="Manual Recovery",
                success_prob=0.7,
            ))

        return branches

    def compute_outcomes(
        self,
        initiating_event: str,
        branches: list[ETABranch] | None = None,
    ) -> ETAResult:
        """Enumerate all outcome paths and compute probabilities.

        Args:
            initiating_event: Description or ID of the initiating event.
            branches: Safety function branches. If None, auto-generated.

        Returns:
            An :class:`ETAResult` with all outcome paths.
        """
        if branches is None:
            branches = self.build_tree(initiating_event)

        outcomes: list[ETAOutcome] = []
        severity_weights = {"low": 1, "medium": 3, "high": 7, "critical": 10}

        # Enumerate all 2^n combinations of success/failure
        for bits in itertools.product([True, False], repeat=len(branches)):
            sequence: list[tuple[str, str]] = []
            prob = 1.0
            failures = 0

            for branch, success in zip(branches, bits):
                if success:
                    sequence.append((branch.event_name, "success"))
                    prob *= branch.success_prob
                else:
                    sequence.append((branch.event_name, "failure"))
                    prob *= branch.failure_prob
                    failures += 1

            # Classify severity based on number of barrier failures
            if failures == 0:
                sev = "low"
            elif failures <= len(branches) // 2:
                sev = "medium"
            elif failures < len(branches):
                sev = "high"
            else:
                sev = "critical"

            outcomes.append(ETAOutcome(
                sequence=sequence,
                probability=prob,
                severity=sev,
            ))

        total_risk = sum(
            o.probability * severity_weights.get(o.severity, 1)
            for o in outcomes
        )

        return ETAResult(
            initiating_event=initiating_event,
            outcomes=outcomes,
            total_risk=round(total_risk, 4),
        )


# =====================================================================
# Simple Model Checker (CTL-like)
# =====================================================================

# A state is represented as a frozenset of (component_id, status_str) pairs
State = frozenset[tuple[str, str]]


@dataclass
class ModelCheckResult:
    """Result of a model-checking property verification.

    Attributes:
        property_name: The CTL-like property that was checked.
        satisfied: Whether the property holds.
        states_explored: Number of states visited during exploration.
        counterexample: A path of states that violates the property
            (if the property is not satisfied); otherwise None.
    """

    property_name: str = ""
    satisfied: bool = False
    states_explored: int = 0
    counterexample: list[State] | None = None


class SimpleModelChecker:
    """Exhaustive state-space model checker with CTL-like properties.

    The checker enumerates the reachable state space of the infrastructure
    graph by BFS, where each state assigns a :class:`HealthStatus` to
    every component.  Transitions model failure propagation: when a
    component is DOWN, its ``requires`` dependents may also go DOWN.

    Supports three CTL-like property forms:
      - **AG(p)**: *p* holds in **all** states on **all** paths from the
        initial state ("always globally").
      - **EF(p)**: there **exists** a path where *p* **eventually** holds
        ("exists finally").
      - **AF(p)**: on **all** paths, *p* **eventually** holds ("always
        finally").

    *Difference from Petri Net (petri_net_engine.py)*: Petri nets model
    concurrency via token-based state transitions; this checker works on
    explicit state tuples and supports temporal-logic queries.

    Args:
        graph: Infrastructure dependency graph.
        max_states: Limit on number of states to explore (prevents
            combinatorial explosion).
    """

    def __init__(self, graph: InfraGraph, max_states: int = 10000) -> None:
        self.graph = graph
        self.max_states = max_states
        self._component_ids = list(graph.components.keys())
        self._transitions: dict[State, list[State]] = {}

    def _initial_state(self) -> State:
        """All components healthy."""
        return frozenset(
            (cid, HealthStatus.HEALTHY.value) for cid in self._component_ids
        )

    def _state_to_dict(self, state: State) -> dict[str, str]:
        return dict(state)

    def _generate_successors(self, state: State) -> list[State]:
        """Generate successor states by propagating failures.

        From any state, the possible transitions are:
        1. One healthy component spontaneously fails (→ DOWN).
        2. Cascade propagation from existing failures.
        """
        successors: list[State] = []
        state_dict = self._state_to_dict(state)

        # Transition type 1: spontaneous failure of one healthy component
        for cid in self._component_ids:
            if state_dict.get(cid) == HealthStatus.HEALTHY.value:
                new_dict = dict(state_dict)
                new_dict[cid] = HealthStatus.DOWN.value

                # Cascade propagation
                self._propagate_cascade(new_dict)
                new_state = frozenset(new_dict.items())
                if new_state != state:
                    successors.append(new_state)

        return successors

    def _propagate_cascade(self, state_dict: dict[str, str]) -> None:
        """Propagate failure cascade through requires-dependencies."""
        changed = True
        iterations = 0
        while changed and iterations < 50:
            changed = False
            iterations += 1
            for cid in self._component_ids:
                if state_dict[cid] != HealthStatus.HEALTHY.value:
                    continue
                # Check if all required dependencies are down
                deps = self.graph.get_dependencies(cid)
                for dep in deps:
                    edge = self.graph.get_dependency_edge(cid, dep.id)
                    if (
                        edge
                        and edge.dependency_type == "requires"
                        and state_dict.get(dep.id) == HealthStatus.DOWN.value
                    ):
                        comp = self.graph.get_component(cid)
                        if comp and comp.replicas <= 1:
                            state_dict[cid] = HealthStatus.DOWN.value
                            changed = True
                            break

    def _build_state_space(self) -> None:
        """Build the reachable state space via BFS."""
        initial = self._initial_state()
        visited: set[State] = {initial}
        queue: deque[State] = deque([initial])
        self._transitions = {initial: []}

        while queue and len(visited) < self.max_states:
            current = queue.popleft()
            successors = self._generate_successors(current)
            self._transitions[current] = successors

            for succ in successors:
                if succ not in visited:
                    visited.add(succ)
                    self._transitions[succ] = []
                    queue.append(succ)

    @staticmethod
    def _check_predicate(state: State, predicate: dict[str, str]) -> bool:
        """Check if a state satisfies a predicate.

        The predicate is a dict like ``{"db": "healthy", "web": "down"}``.
        """
        state_dict = dict(state)
        return all(state_dict.get(k) == v for k, v in predicate.items())

    # ------------------------------------------------------------------
    # CTL operators
    # ------------------------------------------------------------------

    def check_ag(self, predicate: dict[str, str]) -> ModelCheckResult:
        """AG(p): *p* holds in all reachable states.

        "On all paths, *p* is always true."
        """
        self._build_state_space()
        for state in self._transitions:
            if not self._check_predicate(state, predicate):
                # Find path from initial to violating state
                path = self._find_path(self._initial_state(), state)
                return ModelCheckResult(
                    property_name=f"AG({predicate})",
                    satisfied=False,
                    states_explored=len(self._transitions),
                    counterexample=path,
                )
        return ModelCheckResult(
            property_name=f"AG({predicate})",
            satisfied=True,
            states_explored=len(self._transitions),
        )

    def check_ef(self, predicate: dict[str, str]) -> ModelCheckResult:
        """EF(p): there exists a reachable state where *p* holds.

        "There exists a path where *p* eventually becomes true."
        """
        self._build_state_space()
        for state in self._transitions:
            if self._check_predicate(state, predicate):
                path = self._find_path(self._initial_state(), state)
                return ModelCheckResult(
                    property_name=f"EF({predicate})",
                    satisfied=True,
                    states_explored=len(self._transitions),
                    counterexample=path,  # witness path, not counter
                )
        return ModelCheckResult(
            property_name=f"EF({predicate})",
            satisfied=False,
            states_explored=len(self._transitions),
        )

    def check_af(self, predicate: dict[str, str]) -> ModelCheckResult:
        """AF(p): on all paths, *p* eventually holds.

        "On every possible execution, *p* will become true at some point."
        Approximated by checking that all terminal states (no successors)
        satisfy *p*, and all cycles pass through a state satisfying *p*.
        """
        self._build_state_space()

        # Simple approximation: check all leaf states
        for state, successors in self._transitions.items():
            if not successors:  # terminal state
                if not self._check_predicate(state, predicate):
                    path = self._find_path(self._initial_state(), state)
                    return ModelCheckResult(
                        property_name=f"AF({predicate})",
                        satisfied=False,
                        states_explored=len(self._transitions),
                        counterexample=path,
                    )

        return ModelCheckResult(
            property_name=f"AF({predicate})",
            satisfied=True,
            states_explored=len(self._transitions),
        )

    def check_property(
        self,
        initial_state: State | None,
        property_type: str,
        predicate: dict[str, str],
    ) -> bool:
        """Convenience method to check a named property.

        Args:
            initial_state: Ignored (initial state is always all-healthy).
            property_type: One of ``"AG"``, ``"EF"``, ``"AF"``.
            predicate: State predicate as a dict.

        Returns:
            True if the property is satisfied.
        """
        if property_type.upper() == "AG":
            return self.check_ag(predicate).satisfied
        elif property_type.upper() == "EF":
            return self.check_ef(predicate).satisfied
        elif property_type.upper() == "AF":
            return self.check_af(predicate).satisfied
        return False

    def find_counterexample(
        self, property_type: str, predicate: dict[str, str]
    ) -> list[State] | None:
        """Find a counterexample (or witness) path for a property.

        Returns:
            A list of states forming the counter/witness path, or None.
        """
        if property_type.upper() == "AG":
            result = self.check_ag(predicate)
        elif property_type.upper() == "EF":
            result = self.check_ef(predicate)
        elif property_type.upper() == "AF":
            result = self.check_af(predicate)
        else:
            return None
        return result.counterexample

    def _find_path(self, start: State, target: State) -> list[State]:
        """BFS to find a path from start to target in the state graph."""
        if start == target:
            return [start]
        visited: set[State] = {start}
        queue: deque[list[State]] = deque([[start]])
        while queue:
            path = queue.popleft()
            current = path[-1]
            for succ in self._transitions.get(current, []):
                if succ == target:
                    return path + [succ]
                if succ not in visited:
                    visited.add(succ)
                    queue.append(path + [succ])
        return [start, target]  # fallback
