"""Reinforcement Learning-based Chaos Scenario Generator.

Uses Q-learning to discover the most impactful failure scenarios by
treating the FaultRay simulation engine as an RL environment. The agent
learns which components to fail and in what order to maximize cascade
damage, thereby identifying critical vulnerabilities.

Uses ONLY the Python standard library + random.

Basic usage::

    >>> from faultray.model.graph import InfraGraph
    >>> from faultray.simulator.engine import SimulationEngine
    >>> graph = InfraGraph()
    >>> # ... populate graph ...
    >>> engine = SimulationEngine(graph)
    >>> generator = RLScenarioGenerator(graph, engine)
    >>> generator.train(episodes=200)
    >>> top = generator.generate_top_scenarios(k=5)
    >>> for discovery in top:
    ...     print(discovery.severity, discovery.scenario.name)
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from faultray.model.graph import InfraGraph
    from faultray.simulator.engine import SimulationEngine

from faultray.simulator.scenarios import Fault, FaultType, Scenario


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RLState:
    """Immutable representation of the environment state.

    Encoded as a frozenset of ``(component_id, health_status)`` pairs so it
    can be used as a dictionary key.
    """

    components: frozenset[tuple[str, str]]

    def to_key(self) -> str:
        """Return a compact string representation for Q-table indexing."""
        # Sort for deterministic key generation
        parts = sorted(self.components)
        return "|".join(f"{cid}:{hs}" for cid, hs in parts)


@dataclass(frozen=True)
class RLAction:
    """An action the RL agent can take: inject a fault on a component.

    Attributes:
        target_component_id: Which component to fault.
        fault_type: What kind of fault to inject.
    """

    target_component_id: str
    fault_type: FaultType

    def to_key(self) -> str:
        return f"{self.target_component_id}:{self.fault_type.value}"


@dataclass
class RLEpisode:
    """Record of a single training episode.

    Attributes:
        states: Sequence of state keys visited.
        actions: Sequence of action keys taken.
        rewards: Reward received at each step.
        total_reward: Cumulative reward for the episode.
    """

    states: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    rewards: list[float] = field(default_factory=list)
    total_reward: float = 0.0


@dataclass
class RLDiscovery:
    """A high-impact scenario discovered by the RL agent.

    Attributes:
        scenario: The ``Scenario`` object that can be fed back into the
            simulation engine.
        severity: The cascade severity score (0.0 - 10.0).
        discovery_method: Description of how this scenario was found.
    """

    scenario: Scenario
    severity: float
    discovery_method: str


# ---------------------------------------------------------------------------
# RL Scenario Generator
# ---------------------------------------------------------------------------

class RLScenarioGenerator:
    """Q-learning agent that discovers high-impact failure scenarios.

    The generator treats the FaultRay ``SimulationEngine`` as an RL
    *environment*.  At each step the agent selects a component and fault
    type to inject; the resulting cascade severity is the *reward*.
    After training, the learned Q-table encodes a policy that maps
    infrastructure states to the most damaging actions, effectively
    identifying critical vulnerabilities.

    Parameters:
        graph: The infrastructure dependency graph.
        engine: A ``SimulationEngine`` wired to the same graph.
        seed: Optional RNG seed for reproducibility.
        max_steps_per_episode: Maximum faults injected per episode.
    """

    def __init__(
        self,
        graph: InfraGraph,
        engine: SimulationEngine,
        seed: int | None = None,
        max_steps_per_episode: int = 5,
    ) -> None:
        self.graph = graph
        self.engine = engine
        self._rng = random.Random(seed)
        self._max_steps = max_steps_per_episode

        # Q-table: state_key -> {action_key -> Q-value}
        self._q_table: dict[str, dict[str, float]] = {}

        # Pre-compute action space
        self._actions: list[RLAction] = self._get_actions()

        # Training history
        self._episodes: list[RLEpisode] = []

    # ------------------------------------------------------------------
    # Action space
    # ------------------------------------------------------------------

    def _get_actions(self) -> list[RLAction]:
        """Build the full action space: every (component, fault_type) pair."""
        actions: list[RLAction] = []
        fault_types = [
            FaultType.COMPONENT_DOWN,
            FaultType.LATENCY_SPIKE,
            FaultType.CPU_SATURATION,
            FaultType.MEMORY_EXHAUSTION,
            FaultType.DISK_FULL,
            FaultType.CONNECTION_POOL_EXHAUSTION,
            FaultType.NETWORK_PARTITION,
        ]
        for comp_id in self.graph.components:
            for ft in fault_types:
                actions.append(RLAction(target_component_id=comp_id, fault_type=ft))
        return actions

    # ------------------------------------------------------------------
    # Environment interaction
    # ------------------------------------------------------------------

    def _get_initial_state(self) -> RLState:
        """Return the initial (all-healthy) state."""
        pairs = frozenset(
            (cid, "healthy") for cid in self.graph.components
        )
        return RLState(components=pairs)

    def _step(
        self, state: RLState, action: RLAction
    ) -> tuple[RLState, float]:
        """Execute *action* in *state* and return ``(next_state, reward)``.

        The reward is the cascade severity produced by injecting the fault.
        """
        fault = Fault(
            target_component_id=action.target_component_id,
            fault_type=action.fault_type,
        )
        chain = self.engine.cascade_engine.simulate_fault(fault)
        reward = chain.severity

        # Build next state from cascade effects
        state_dict: dict[str, str] = {cid: hs for cid, hs in state.components}
        for effect in chain.effects:
            state_dict[effect.component_id] = effect.health.value

        next_state = RLState(
            components=frozenset(state_dict.items())
        )
        return next_state, reward

    # ------------------------------------------------------------------
    # Q-learning helpers
    # ------------------------------------------------------------------

    def _q_value(self, state_key: str, action_key: str) -> float:
        return self._q_table.get(state_key, {}).get(action_key, 0.0)

    def _set_q_value(self, state_key: str, action_key: str, value: float) -> None:
        if state_key not in self._q_table:
            self._q_table[state_key] = {}
        self._q_table[state_key][action_key] = value

    def _max_q(self, state_key: str) -> float:
        """Return the maximum Q-value achievable from *state_key*."""
        q_row = self._q_table.get(state_key)
        if not q_row:
            return 0.0
        return max(q_row.values())

    def _select_action(self, state_key: str, epsilon: float) -> RLAction:
        """Epsilon-greedy action selection."""
        if self._rng.random() < epsilon:
            return self._rng.choice(self._actions)

        # Greedy: pick the action with the highest Q-value
        q_row = self._q_table.get(state_key, {})
        if not q_row:
            return self._rng.choice(self._actions)

        best_key = max(q_row, key=q_row.get)  # type: ignore[arg-type]
        # Resolve the key back to an RLAction
        for a in self._actions:
            if a.to_key() == best_key:
                return a
        # Fallback (should not happen)
        return self._rng.choice(self._actions)

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def train(
        self,
        episodes: int = 500,
        epsilon: float = 0.3,
        alpha: float = 0.1,
        gamma: float = 0.9,
    ) -> list[RLEpisode]:
        """Train the Q-learning agent.

        Parameters:
            episodes: Number of training episodes to run.
            epsilon: Exploration probability (epsilon-greedy).
            alpha: Learning rate.
            gamma: Discount factor.

        Returns:
            List of ``RLEpisode`` records for the training run.
        """
        if not self._actions:
            return []

        for ep_idx in range(episodes):
            episode = RLEpisode()
            state = self._get_initial_state()
            state_key = state.to_key()

            for _step in range(self._max_steps):
                action = self._select_action(state_key, epsilon)
                action_key = action.to_key()

                next_state, reward = self._step(state, action)
                next_key = next_state.to_key()

                episode.states.append(state_key)
                episode.actions.append(action_key)
                episode.rewards.append(reward)
                episode.total_reward += reward

                # Q-learning update:
                # Q(s,a) <- Q(s,a) + alpha * (reward + gamma * max Q(s') - Q(s,a))
                old_q = self._q_value(state_key, action_key)
                td_target = reward + gamma * self._max_q(next_key)
                new_q = old_q + alpha * (td_target - old_q)
                self._set_q_value(state_key, action_key, new_q)

                state = next_state
                state_key = next_key

            self._episodes.append(episode)

            # Decay epsilon over time (exploration -> exploitation)
            epsilon = max(0.05, epsilon * 0.995)

        return self._episodes

    # ------------------------------------------------------------------
    # Scenario generation
    # ------------------------------------------------------------------

    def generate_top_scenarios(self, k: int = 10) -> list[RLDiscovery]:
        """Generate the top-K most impactful scenarios from the learned policy.

        After training, this method replays the policy greedily (epsilon=0)
        from the initial state to build multi-fault scenarios, then ranks
        them by severity.

        Parameters:
            k: Number of top scenarios to return.

        Returns:
            Sorted list of ``RLDiscovery`` objects (highest severity first).
        """
        if not self._q_table:
            return []

        discoveries: dict[str, RLDiscovery] = {}

        # 1. Generate scenarios from greedy policy replay
        state = self._get_initial_state()
        state_key = state.to_key()
        faults: list[Fault] = []
        cumulative_severity = 0.0

        for step_idx in range(self._max_steps):
            action = self._select_action(state_key, epsilon=0.0)
            fault = Fault(
                target_component_id=action.target_component_id,
                fault_type=action.fault_type,
            )
            faults.append(fault)

            next_state, reward = self._step(state, action)
            cumulative_severity += reward
            state = next_state
            state_key = next_state.to_key()

            # Record partial scenario at each step
            scenario = Scenario(
                id=f"rl-greedy-{step_idx + 1}",
                name=f"RL Discovery: {step_idx + 1}-fault greedy scenario",
                description=(
                    f"Multi-fault scenario discovered by RL Q-learning "
                    f"(greedy policy, {step_idx + 1} faults)"
                ),
                faults=list(faults),  # copy
            )

            # Evaluate the full scenario through the engine
            result = self.engine.run_scenario(scenario)
            severity = result.risk_score

            disc = RLDiscovery(
                scenario=scenario,
                severity=severity,
                discovery_method="q-learning greedy policy replay",
            )
            discoveries[scenario.id] = disc

        # 2. Also generate single-fault scenarios from the Q-table's
        #    highest-valued actions in the initial state.
        initial_key = self._get_initial_state().to_key()
        q_row = self._q_table.get(initial_key, {})
        if q_row:
            ranked_actions = sorted(q_row.items(), key=lambda x: x[1], reverse=True)
            for rank, (action_key, q_val) in enumerate(ranked_actions[:k]):
                # Parse action key back
                parts = action_key.split(":", 1)
                if len(parts) != 2:
                    continue
                comp_id, ft_value = parts
                try:
                    ft = FaultType(ft_value)
                except ValueError:
                    continue

                scenario = Scenario(
                    id=f"rl-single-{rank}",
                    name=f"RL Discovery: {comp_id} {ft.value}",
                    description=(
                        f"Single-fault scenario with highest Q-value "
                        f"(Q={q_val:.3f}) for {comp_id} {ft.value}"
                    ),
                    faults=[
                        Fault(target_component_id=comp_id, fault_type=ft)
                    ],
                )

                result = self.engine.run_scenario(scenario)
                disc = RLDiscovery(
                    scenario=scenario,
                    severity=result.risk_score,
                    discovery_method=f"q-learning top Q-value (Q={q_val:.3f})",
                )
                discoveries[scenario.id] = disc

        # Sort by severity descending and return top-k
        ranked = sorted(discoveries.values(), key=lambda d: d.severity, reverse=True)
        return ranked[:k]

    def get_policy(self) -> dict[str, dict[str, float]]:
        """Return the learned policy (Q-table).

        Returns:
            A dict mapping state keys to dicts of action keys -> Q-values.
            Callers can inspect this to understand which actions the agent
            considers most damaging in each state.
        """
        return dict(self._q_table)
