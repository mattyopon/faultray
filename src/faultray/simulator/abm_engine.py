"""Agent-Based Model (ABM) Engine for infrastructure resilience simulation.

Models each infrastructure component as an independent agent that makes
autonomous decisions about its health state based on local observations
of neighboring agents. Discovers emergent failure patterns that graph
traversal (BFS) cannot detect.

Uses ONLY the Python standard library.

Basic usage::

    >>> from faultray.model.graph import InfraGraph
    >>> from faultray.simulator.scenarios import Fault, FaultType
    >>> graph = InfraGraph()
    >>> # ... populate graph with components and dependencies ...
    >>> engine = ABMEngine(graph)
    >>> fault = Fault(target_component_id="db-1", fault_type=FaultType.COMPONENT_DOWN)
    >>> result = engine.simulate(fault)
    >>> print(result.severity)
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from faultray.model.graph import InfraGraph
    from faultray.simulator.cascade import CascadeChain
    from faultray.simulator.scenarios import Fault, Scenario


class AgentState(str, Enum):
    """Possible health states for an ABM agent."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    OVERLOADED = "overloaded"
    DOWN = "down"


@dataclass
class _AgentRule:
    """A single decision rule for an agent.

    Attributes:
        condition: Human-readable description of the trigger condition.
        target_state: The state the agent transitions to when triggered.
        priority: Higher priority rules are evaluated first.
    """

    condition: str
    target_state: AgentState
    priority: int = 0


@dataclass
class Agent:
    """An autonomous agent representing one infrastructure component.

    Attributes:
        component_id: ID of the underlying ``Component``.
        state: Current health state of the agent.
        rules: Ordered list of decision rules (highest priority first).
        neighbors: Mapping of neighbour component IDs to dependency metadata.
            Each value is a dict with at least ``"type"`` (``"requires"`` /
            ``"optional"`` / ``"async"``) and ``"weight"`` (``float``).
        metrics: Simulated resource metrics (cpu, memory, disk, connections).
        timeout_steps: Number of steps a *requires* dependency must be DOWN
            before this agent also transitions to DOWN.
        _down_counter: Internal counter tracking consecutive steps with a
            required dependency DOWN.
    """

    component_id: str
    state: AgentState = AgentState.HEALTHY
    rules: list[_AgentRule] = field(default_factory=list)
    neighbors: dict[str, dict] = field(default_factory=dict)
    metrics: dict[str, float] = field(default_factory=dict)
    timeout_steps: int = 2
    _down_counter: int = 0


@dataclass
class ABMStep:
    """Snapshot of one simulation step.

    Attributes:
        step_number: Zero-based step index.
        agent_states: Mapping of component_id -> ``AgentState`` at this step.
        events: Human-readable descriptions of state transitions that
            occurred during this step.
    """

    step_number: int
    agent_states: dict[str, AgentState] = field(default_factory=dict)
    events: list[str] = field(default_factory=list)


@dataclass
class ABMResult:
    """Complete result of an ABM simulation run.

    Attributes:
        steps: Ordered list of ``ABMStep`` snapshots.
        emergent_patterns: Descriptions of emergent behaviours discovered
            (i.e. outcomes that differ from BFS prediction).
        affected_agents: IDs of agents that ended in a non-HEALTHY state.
        severity: Overall severity score in ``[0.0, 10.0]``.
    """

    steps: list[ABMStep] = field(default_factory=list)
    emergent_patterns: list[str] = field(default_factory=list)
    affected_agents: list[str] = field(default_factory=list)
    severity: float = 0.0


class ABMEngine:
    """Agent-Based Model engine for infrastructure resilience simulation.

    Each infrastructure component is modelled as an independent *agent* that
    observes the states of its neighbours and decides its own next state
    according to a set of rules.  Because every agent acts simultaneously
    (synchronous update), the engine can discover *emergent* failure patterns
    that a deterministic BFS cascade walk would miss -- for example cascading
    overloads triggered by probabilistic retry storms.

    Parameters:
        graph: The infrastructure dependency graph.
        seed: Optional RNG seed for reproducibility.
    """

    def __init__(self, graph: InfraGraph, seed: int | None = None) -> None:
        self.graph = graph
        self._rng = random.Random(seed)
        self._agents: dict[str, Agent] = {}
        self._build_agents()

    # ------------------------------------------------------------------
    # Agent construction
    # ------------------------------------------------------------------

    def _build_agents(self) -> None:
        """Convert every component in the graph into an autonomous Agent."""
        for comp_id, comp in self.graph.components.items():
            # Gather neighbour metadata (dependencies this component has)
            neighbors: dict[str, dict] = {}
            for dep_comp in self.graph.get_dependencies(comp_id):
                edge = self.graph.get_dependency_edge(comp_id, dep_comp.id)
                dep_type = edge.dependency_type if edge else "requires"
                weight = edge.weight if edge else 1.0
                neighbors[dep_comp.id] = {"type": dep_type, "weight": weight}

            # Also include components that depend *on* this component so the
            # agent is aware of upstream pressure (used for overload rules).
            for dep_comp in self.graph.get_dependents(comp_id):
                if dep_comp.id not in neighbors:
                    neighbors[dep_comp.id] = {"type": "dependent", "weight": 0.5}

            # Derive timeout_steps from the component's timeout_seconds.
            # Each simulation step represents ~5 seconds of real time.
            timeout_steps = max(1, int(comp.capacity.timeout_seconds / 5))

            metrics = {
                "cpu": comp.metrics.cpu_percent,
                "memory": comp.metrics.memory_percent,
                "disk": comp.metrics.disk_percent,
                "connections": float(comp.metrics.network_connections),
                "max_connections": float(comp.capacity.max_connections),
            }

            rules = self._default_rules()

            self._agents[comp_id] = Agent(
                component_id=comp_id,
                state=AgentState.HEALTHY,
                rules=rules,
                neighbors=neighbors,
                metrics=metrics,
                timeout_steps=timeout_steps,
            )

    @staticmethod
    def _default_rules() -> list[_AgentRule]:
        """Return the standard rule-set applied to every agent."""
        return sorted(
            [
                _AgentRule(
                    condition="required_dependency_down",
                    target_state=AgentState.DOWN,
                    priority=100,
                ),
                _AgentRule(
                    condition="optional_dependency_down",
                    target_state=AgentState.DEGRADED,
                    priority=50,
                ),
                _AgentRule(
                    condition="cpu_saturation",
                    target_state=AgentState.OVERLOADED,
                    priority=70,
                ),
                _AgentRule(
                    condition="probabilistic_cascade",
                    target_state=AgentState.DEGRADED,
                    priority=30,
                ),
            ],
            key=lambda r: r.priority,
            reverse=True,
        )

    # ------------------------------------------------------------------
    # Simulation
    # ------------------------------------------------------------------

    def simulate(self, fault: Fault, max_steps: int = 50) -> ABMResult:
        """Run an ABM simulation for a single fault injection.

        1. Set the target agent to DOWN.
        2. On each step every agent *simultaneously* evaluates its rules
           based on the previous step's state snapshot.
        3. Simulation ends when the global state converges (no changes for
           two consecutive steps) or *max_steps* is reached.
        4. Emergent patterns are detected by comparing the final affected
           set against what a simple BFS would predict.

        Parameters:
            fault: The fault to inject.
            max_steps: Upper bound on simulation steps.

        Returns:
            An ``ABMResult`` with the full step history, emergent patterns,
            affected agents and an overall severity score.
        """
        # Reset all agents to HEALTHY
        for agent in self._agents.values():
            agent.state = AgentState.HEALTHY
            agent._down_counter = 0

        # Inject the fault
        target_id = fault.target_component_id
        if target_id in self._agents:
            self._agents[target_id].state = AgentState.DOWN

        steps: list[ABMStep] = []
        prev_snapshot: dict[str, AgentState] = {}
        stable_count = 0

        for step_num in range(max_steps):
            # Take a snapshot *before* updates (agents read from this)
            snapshot = {aid: a.state for aid, a in self._agents.items()}

            events: list[str] = []

            # Synchronous update: compute next state for every agent, then
            # apply all at once.
            next_states: dict[str, AgentState] = {}
            for aid, agent in self._agents.items():
                # The fault target stays DOWN for the entire simulation.
                if aid == target_id:
                    next_states[aid] = AgentState.DOWN
                    continue
                new_state = self._evaluate_agent(agent, snapshot)
                if new_state != agent.state:
                    events.append(
                        f"Step {step_num}: {aid} {agent.state.value} -> {new_state.value}"
                    )
                next_states[aid] = new_state

            # Apply next states
            for aid, ns in next_states.items():
                self._agents[aid].state = ns

            step = ABMStep(
                step_number=step_num,
                agent_states=dict(snapshot),
                events=events,
            )
            steps.append(step)

            # Convergence check
            if snapshot == prev_snapshot:
                stable_count += 1
            else:
                stable_count = 0
            if stable_count >= 2:
                break
            prev_snapshot = snapshot

        # Collect affected agents (non-HEALTHY at end)
        affected = [
            aid
            for aid, a in self._agents.items()
            if a.state != AgentState.HEALTHY
        ]

        # Detect emergent patterns (difference from BFS prediction)
        emergent = self._detect_emergent_patterns(target_id, affected)

        # Calculate severity
        severity = self._calculate_severity(affected)

        return ABMResult(
            steps=steps,
            emergent_patterns=emergent,
            affected_agents=affected,
            severity=severity,
        )

    def simulate_scenario(self, scenario: Scenario) -> ABMResult:
        """Run ABM simulation for a full scenario (multiple faults).

        Each fault is injected sequentially; the combined result is returned.
        """
        # Reset all agents
        for agent in self._agents.values():
            agent.state = AgentState.HEALTHY
            agent._down_counter = 0

        all_target_ids: list[str] = []
        for fault in scenario.faults:
            tid = fault.target_component_id
            if tid in self._agents:
                self._agents[tid].state = AgentState.DOWN
                all_target_ids.append(tid)

        # Run the simulation loop (same as simulate but with multiple pinned targets)
        steps: list[ABMStep] = []
        prev_snapshot: dict[str, AgentState] = {}
        stable_count = 0
        max_steps = 50

        for step_num in range(max_steps):
            snapshot = {aid: a.state for aid, a in self._agents.items()}
            events: list[str] = []

            next_states: dict[str, AgentState] = {}
            for aid, agent in self._agents.items():
                if aid in all_target_ids:
                    next_states[aid] = AgentState.DOWN
                    continue
                new_state = self._evaluate_agent(agent, snapshot)
                if new_state != agent.state:
                    events.append(
                        f"Step {step_num}: {aid} {agent.state.value} -> {new_state.value}"
                    )
                next_states[aid] = new_state

            for aid, ns in next_states.items():
                self._agents[aid].state = ns

            steps.append(
                ABMStep(step_number=step_num, agent_states=dict(snapshot), events=events)
            )

            if snapshot == prev_snapshot:
                stable_count += 1
            else:
                stable_count = 0
            if stable_count >= 2:
                break
            prev_snapshot = snapshot

        affected = [
            aid for aid, a in self._agents.items() if a.state != AgentState.HEALTHY
        ]

        emergent: list[str] = []
        for tid in all_target_ids:
            emergent.extend(self._detect_emergent_patterns(tid, affected))
        # Deduplicate
        emergent = list(dict.fromkeys(emergent))

        severity = self._calculate_severity(affected)

        return ABMResult(
            steps=steps,
            emergent_patterns=emergent,
            affected_agents=affected,
            severity=severity,
        )

    def compare_with_cascade(self, cascade_chain: CascadeChain) -> dict:
        """Compare ABM results with BFS-based CascadeChain predictions.

        Returns a dict with:
        - ``bfs_only``: component IDs affected by BFS but not ABM.
        - ``abm_only``: component IDs affected by ABM but not BFS.
        - ``both``: component IDs affected by both.
        - ``agreement_ratio``: float in ``[0, 1]`` indicating overlap.
        """
        bfs_affected = {e.component_id for e in cascade_chain.effects}

        # We need the *last* step's snapshot for the ABM side.
        abm_affected = {
            aid for aid, a in self._agents.items() if a.state != AgentState.HEALTHY
        }

        both = bfs_affected & abm_affected
        bfs_only = bfs_affected - abm_affected
        abm_only = abm_affected - bfs_affected

        union = bfs_affected | abm_affected
        agreement_ratio = len(both) / len(union) if union else 1.0

        return {
            "bfs_only": sorted(bfs_only),
            "abm_only": sorted(abm_only),
            "both": sorted(both),
            "agreement_ratio": round(agreement_ratio, 3),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _evaluate_agent(
        self, agent: Agent, snapshot: dict[str, AgentState]
    ) -> AgentState:
        """Evaluate an agent's rules against the current global snapshot.

        Rules are checked in priority order.  The first matching rule
        determines the next state.  If no rule matches the agent stays
        HEALTHY.
        """
        worst_state = AgentState.HEALTHY

        for rule in agent.rules:
            matched_state = self._check_rule(agent, rule, snapshot)
            if matched_state is not None:
                if self._state_severity(matched_state) > self._state_severity(worst_state):
                    worst_state = matched_state

        return worst_state

    def _check_rule(
        self,
        agent: Agent,
        rule: _AgentRule,
        snapshot: dict[str, AgentState],
    ) -> AgentState | None:
        """Check whether *rule* triggers for *agent* given *snapshot*.

        Returns the target state if triggered, else ``None``.
        """
        if rule.condition == "required_dependency_down":
            # If any *requires* dependency is DOWN for timeout_steps steps
            for nid, meta in agent.neighbors.items():
                if meta["type"] != "requires":
                    continue
                if snapshot.get(nid) == AgentState.DOWN:
                    agent._down_counter += 1
                    if agent._down_counter >= agent.timeout_steps:
                        return AgentState.DOWN
            # Reset counter if no required dep is down
            if not any(
                snapshot.get(nid) == AgentState.DOWN
                for nid, meta in agent.neighbors.items()
                if meta["type"] == "requires"
            ):
                agent._down_counter = 0
            return None

        if rule.condition == "optional_dependency_down":
            for nid, meta in agent.neighbors.items():
                if meta["type"] != "optional":
                    continue
                if snapshot.get(nid) == AgentState.DOWN:
                    return AgentState.DEGRADED
            return None

        if rule.condition == "cpu_saturation":
            cpu = agent.metrics.get("cpu", 0.0)
            if cpu > 90:
                return AgentState.OVERLOADED
            return None

        if rule.condition == "probabilistic_cascade":
            # Stochastic propagation: if many neighbours are unhealthy,
            # there is a chance this agent degrades even without a direct
            # dependency link.  This models retry storms, back-pressure,
            # and other emergent effects that BFS cannot capture.
            unhealthy_neighbours = sum(
                1
                for nid in agent.neighbors
                if snapshot.get(nid) in (AgentState.DOWN, AgentState.OVERLOADED)
            )
            total_neighbours = len(agent.neighbors)
            if total_neighbours == 0:
                return None

            # Probability proportional to fraction of unhealthy neighbours
            prob = (unhealthy_neighbours / total_neighbours) * 0.4
            # Use a deterministic-ish seed per agent per step for
            # reproducibility while still allowing stochasticity.
            if self._rng.random() < prob:
                return AgentState.DEGRADED
            return None

        return None

    @staticmethod
    def _state_severity(state: AgentState) -> int:
        """Return a numeric severity for ordering states."""
        return {
            AgentState.HEALTHY: 0,
            AgentState.DEGRADED: 1,
            AgentState.OVERLOADED: 2,
            AgentState.DOWN: 3,
        }.get(state, 0)

    def _detect_emergent_patterns(
        self, target_id: str, abm_affected: list[str]
    ) -> list[str]:
        """Identify outcomes that differ from a naive BFS prediction."""
        # BFS prediction: all components transitively dependent on target
        bfs_predicted = self.graph.get_all_affected(target_id)

        abm_set = set(abm_affected)
        patterns: list[str] = []

        # Components affected by ABM but *not* in the BFS transitive closure
        abm_only = abm_set - bfs_predicted - {target_id}
        if abm_only:
            patterns.append(
                f"Emergent cascade: {len(abm_only)} component(s) affected "
                f"outside BFS prediction ({', '.join(sorted(abm_only))}). "
                "Likely caused by probabilistic back-pressure / retry storms."
            )

        # Components predicted by BFS but *not* affected by ABM
        bfs_only = bfs_predicted - abm_set
        if bfs_only:
            patterns.append(
                f"Resilience discovered: {len(bfs_only)} component(s) predicted "
                f"to fail by BFS remained healthy in ABM simulation "
                f"({', '.join(sorted(bfs_only))}). "
                "Timeout buffers or low propagation probability may explain this."
            )

        return patterns

    def _calculate_severity(self, affected: list[str]) -> float:
        """Compute a severity score in [0.0, 10.0] analogous to CascadeChain."""
        total = len(self._agents)
        if total == 0:
            return 0.0

        down = sum(
            1 for aid in affected if self._agents[aid].state == AgentState.DOWN
        )
        overloaded = sum(
            1 for aid in affected if self._agents[aid].state == AgentState.OVERLOADED
        )
        degraded = sum(
            1 for aid in affected if self._agents[aid].state == AgentState.DEGRADED
        )

        affected_count = len(affected)
        if affected_count == 0:
            return 0.0

        impact_score = (down * 1.0 + overloaded * 0.5 + degraded * 0.25) / affected_count
        spread_score = affected_count / total
        raw = impact_score * spread_score * 10.0

        # Apply caps consistent with CascadeChain.severity
        if affected_count <= 1:
            raw = min(raw, 3.0)
        elif spread_score < 0.3:
            raw = min(raw, 6.0)

        if down == 0 and overloaded == 0 and degraded > 0:
            raw = min(raw, 4.0)

        return min(10.0, max(0.0, round(raw, 1)))
