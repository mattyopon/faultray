"""State Machine Chaos Simulator.

Models infrastructure components as state machines and injects chaos at state
transition boundaries.  Each component has a set of allowed states, transitions
between those states (triggered by operational events), and forbidden
transitions that should never happen but *might* be triggered by chaos.

The engine is fully stateless — every public method is a pure function of its
inputs.  Only the Python standard library is used (no networkx / numpy).
"""

from __future__ import annotations

import logging
from collections import deque
from enum import Enum
from typing import Sequence

from pydantic import BaseModel, Field, field_validator

from faultray.model.components import Component, ComponentType
from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ComponentState(str, Enum):
    """Operational states a component can be in."""

    INITIALIZING = "initializing"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    OVERLOADED = "overloaded"
    FAILING = "failing"
    RECOVERING = "recovering"
    MAINTENANCE = "maintenance"
    DRAINING = "draining"
    TERMINATED = "terminated"


class TransitionTrigger(str, Enum):
    """Events that can trigger a state transition."""

    LOAD_INCREASE = "load_increase"
    LOAD_DECREASE = "load_decrease"
    FAILURE_DETECTED = "failure_detected"
    HEALTH_CHECK_PASS = "health_check_pass"
    HEALTH_CHECK_FAIL = "health_check_fail"
    MANUAL_INTERVENTION = "manual_intervention"
    TIMEOUT = "timeout"
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    DEPENDENCY_FAILURE = "dependency_failure"
    DEPLOYMENT = "deployment"


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class StateTransition(BaseModel):
    """A single allowed state transition."""

    from_state: ComponentState
    to_state: ComponentState
    trigger: TransitionTrigger
    probability: float = Field(default=1.0, ge=0.0, le=1.0)
    duration_seconds: float = Field(default=0.0, ge=0.0)
    side_effects: list[str] = Field(default_factory=list)


class StateMachineConfig(BaseModel):
    """Full state-machine definition for a single component."""

    component_id: str
    states: list[ComponentState]
    transitions: list[StateTransition]
    initial_state: ComponentState
    forbidden_transitions: list[tuple[str, str]] = Field(default_factory=list)

    @field_validator("states")
    @classmethod
    def states_not_empty(cls, v: list[ComponentState]) -> list[ComponentState]:
        if not v:
            raise ValueError("states must not be empty")
        return v


class RecoveryPath(BaseModel):
    """A path from a given state back to HEALTHY."""

    path: list[ComponentState]
    total_duration_seconds: float
    transitions_used: list[StateTransition]


class ForbiddenTransitionRisk(BaseModel):
    """A forbidden transition that could still be triggered."""

    from_state: str
    to_state: str
    possible_triggers: list[TransitionTrigger]
    risk_level: str  # "high", "medium", "low"


class ChaosInjectionResult(BaseModel):
    """Result of injecting chaos into a component's state machine."""

    triggered_transition: StateTransition
    cascade_effects: list[str]
    recovery_path: list[ComponentState]
    estimated_recovery_seconds: float
    data_risk: str  # "none", "low", "medium", "high", "critical"


# ---------------------------------------------------------------------------
# Default transition table
# ---------------------------------------------------------------------------

_DEFAULT_TRANSITIONS: list[StateTransition] = [
    # initializing -> healthy
    StateTransition(
        from_state=ComponentState.INITIALIZING,
        to_state=ComponentState.HEALTHY,
        trigger=TransitionTrigger.HEALTH_CHECK_PASS,
        probability=0.95,
        duration_seconds=5.0,
        side_effects=["component_ready"],
    ),
    # initializing -> failing
    StateTransition(
        from_state=ComponentState.INITIALIZING,
        to_state=ComponentState.FAILING,
        trigger=TransitionTrigger.TIMEOUT,
        probability=0.05,
        duration_seconds=30.0,
        side_effects=["startup_failure"],
    ),
    # healthy -> degraded (load)
    StateTransition(
        from_state=ComponentState.HEALTHY,
        to_state=ComponentState.DEGRADED,
        trigger=TransitionTrigger.LOAD_INCREASE,
        probability=0.3,
        duration_seconds=0.0,
        side_effects=["latency_increase"],
    ),
    # healthy -> failing (failure detected)
    StateTransition(
        from_state=ComponentState.HEALTHY,
        to_state=ComponentState.FAILING,
        trigger=TransitionTrigger.FAILURE_DETECTED,
        probability=0.1,
        duration_seconds=0.0,
        side_effects=["alert_triggered", "error_rate_spike"],
    ),
    # healthy -> maintenance
    StateTransition(
        from_state=ComponentState.HEALTHY,
        to_state=ComponentState.MAINTENANCE,
        trigger=TransitionTrigger.MANUAL_INTERVENTION,
        probability=1.0,
        duration_seconds=2.0,
        side_effects=["traffic_redirected"],
    ),
    # healthy -> draining
    StateTransition(
        from_state=ComponentState.HEALTHY,
        to_state=ComponentState.DRAINING,
        trigger=TransitionTrigger.DEPLOYMENT,
        probability=0.9,
        duration_seconds=1.0,
        side_effects=["new_connections_blocked"],
    ),
    # healthy -> failing (dependency failure)
    StateTransition(
        from_state=ComponentState.HEALTHY,
        to_state=ComponentState.FAILING,
        trigger=TransitionTrigger.DEPENDENCY_FAILURE,
        probability=0.2,
        duration_seconds=0.0,
        side_effects=["cascade_risk"],
    ),
    # degraded -> overloaded
    StateTransition(
        from_state=ComponentState.DEGRADED,
        to_state=ComponentState.OVERLOADED,
        trigger=TransitionTrigger.LOAD_INCREASE,
        probability=0.5,
        duration_seconds=0.0,
        side_effects=["request_queuing", "latency_spike"],
    ),
    # degraded -> healthy
    StateTransition(
        from_state=ComponentState.DEGRADED,
        to_state=ComponentState.HEALTHY,
        trigger=TransitionTrigger.LOAD_DECREASE,
        probability=0.7,
        duration_seconds=10.0,
        side_effects=["latency_normalized"],
    ),
    # degraded -> failing
    StateTransition(
        from_state=ComponentState.DEGRADED,
        to_state=ComponentState.FAILING,
        trigger=TransitionTrigger.RESOURCE_EXHAUSTION,
        probability=0.4,
        duration_seconds=0.0,
        side_effects=["oom_risk", "alert_triggered"],
    ),
    # degraded -> failing (health check fail)
    StateTransition(
        from_state=ComponentState.DEGRADED,
        to_state=ComponentState.FAILING,
        trigger=TransitionTrigger.HEALTH_CHECK_FAIL,
        probability=0.3,
        duration_seconds=0.0,
        side_effects=["alert_triggered"],
    ),
    # overloaded -> failing
    StateTransition(
        from_state=ComponentState.OVERLOADED,
        to_state=ComponentState.FAILING,
        trigger=TransitionTrigger.RESOURCE_EXHAUSTION,
        probability=0.6,
        duration_seconds=0.0,
        side_effects=["oom_killed", "connections_dropped"],
    ),
    # overloaded -> degraded
    StateTransition(
        from_state=ComponentState.OVERLOADED,
        to_state=ComponentState.DEGRADED,
        trigger=TransitionTrigger.LOAD_DECREASE,
        probability=0.5,
        duration_seconds=15.0,
        side_effects=["gradual_recovery"],
    ),
    # overloaded -> failing (timeout)
    StateTransition(
        from_state=ComponentState.OVERLOADED,
        to_state=ComponentState.FAILING,
        trigger=TransitionTrigger.TIMEOUT,
        probability=0.4,
        duration_seconds=0.0,
        side_effects=["timeout_cascade"],
    ),
    # failing -> recovering
    StateTransition(
        from_state=ComponentState.FAILING,
        to_state=ComponentState.RECOVERING,
        trigger=TransitionTrigger.MANUAL_INTERVENTION,
        probability=0.8,
        duration_seconds=5.0,
        side_effects=["restart_initiated"],
    ),
    # failing -> recovering (auto)
    StateTransition(
        from_state=ComponentState.FAILING,
        to_state=ComponentState.RECOVERING,
        trigger=TransitionTrigger.HEALTH_CHECK_PASS,
        probability=0.3,
        duration_seconds=10.0,
        side_effects=["auto_recovery"],
    ),
    # failing -> terminated
    StateTransition(
        from_state=ComponentState.FAILING,
        to_state=ComponentState.TERMINATED,
        trigger=TransitionTrigger.TIMEOUT,
        probability=0.2,
        duration_seconds=0.0,
        side_effects=["component_dead", "data_risk"],
    ),
    # recovering -> healthy
    StateTransition(
        from_state=ComponentState.RECOVERING,
        to_state=ComponentState.HEALTHY,
        trigger=TransitionTrigger.HEALTH_CHECK_PASS,
        probability=0.8,
        duration_seconds=15.0,
        side_effects=["component_ready"],
    ),
    # recovering -> failing
    StateTransition(
        from_state=ComponentState.RECOVERING,
        to_state=ComponentState.FAILING,
        trigger=TransitionTrigger.HEALTH_CHECK_FAIL,
        probability=0.2,
        duration_seconds=0.0,
        side_effects=["recovery_failed"],
    ),
    # maintenance -> healthy
    StateTransition(
        from_state=ComponentState.MAINTENANCE,
        to_state=ComponentState.HEALTHY,
        trigger=TransitionTrigger.MANUAL_INTERVENTION,
        probability=0.95,
        duration_seconds=5.0,
        side_effects=["maintenance_complete"],
    ),
    # maintenance -> failing
    StateTransition(
        from_state=ComponentState.MAINTENANCE,
        to_state=ComponentState.FAILING,
        trigger=TransitionTrigger.FAILURE_DETECTED,
        probability=0.05,
        duration_seconds=0.0,
        side_effects=["maintenance_error"],
    ),
    # draining -> terminated
    StateTransition(
        from_state=ComponentState.DRAINING,
        to_state=ComponentState.TERMINATED,
        trigger=TransitionTrigger.TIMEOUT,
        probability=0.9,
        duration_seconds=30.0,
        side_effects=["graceful_shutdown"],
    ),
    # draining -> initializing (redeployment)
    StateTransition(
        from_state=ComponentState.DRAINING,
        to_state=ComponentState.INITIALIZING,
        trigger=TransitionTrigger.DEPLOYMENT,
        probability=0.8,
        duration_seconds=10.0,
        side_effects=["new_version_starting"],
    ),
    # terminated -> initializing (restart)
    StateTransition(
        from_state=ComponentState.TERMINATED,
        to_state=ComponentState.INITIALIZING,
        trigger=TransitionTrigger.MANUAL_INTERVENTION,
        probability=0.9,
        duration_seconds=5.0,
        side_effects=["restart_requested"],
    ),
    # terminated -> initializing (auto-restart)
    StateTransition(
        from_state=ComponentState.TERMINATED,
        to_state=ComponentState.INITIALIZING,
        trigger=TransitionTrigger.DEPLOYMENT,
        probability=0.85,
        duration_seconds=8.0,
        side_effects=["auto_restart"],
    ),
]

# Default forbidden transitions — these should never happen.
_DEFAULT_FORBIDDEN: list[tuple[str, str]] = [
    (ComponentState.TERMINATED.value, ComponentState.HEALTHY.value),
    (ComponentState.INITIALIZING.value, ComponentState.OVERLOADED.value),
    (ComponentState.MAINTENANCE.value, ComponentState.OVERLOADED.value),
    (ComponentState.DRAINING.value, ComponentState.HEALTHY.value),
]


# ---------------------------------------------------------------------------
# Helpers for data-risk assessment
# ---------------------------------------------------------------------------

_DATA_RISK_BY_TYPE: dict[ComponentType, str] = {
    ComponentType.DATABASE: "critical",
    ComponentType.STORAGE: "high",
    ComponentType.CACHE: "medium",
    ComponentType.QUEUE: "medium",
    ComponentType.APP_SERVER: "low",
    ComponentType.WEB_SERVER: "low",
    ComponentType.LOAD_BALANCER: "none",
    ComponentType.DNS: "none",
    ComponentType.EXTERNAL_API: "low",
    ComponentType.CUSTOM: "low",
    ComponentType.AI_AGENT: "low",
    ComponentType.LLM_ENDPOINT: "low",
    ComponentType.TOOL_SERVICE: "low",
    ComponentType.AGENT_ORCHESTRATOR: "medium",
}


def _data_risk_for_component(comp: Component, target_state: ComponentState) -> str:
    """Determine data-risk level for a state transition on *comp*."""
    base_risk = _DATA_RISK_BY_TYPE.get(comp.type, "low")
    if target_state in (ComponentState.FAILING, ComponentState.TERMINATED):
        return base_risk
    # Non-terminal states have lower risk.
    risk_levels = ["none", "low", "medium", "high", "critical"]
    idx = risk_levels.index(base_risk)
    return risk_levels[max(0, idx - 1)]


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class StateMachineChaosEngine:
    """Stateless engine that models components as state machines and injects chaos."""

    # -- public API ----------------------------------------------------------

    def build_state_machine(
        self,
        graph: InfraGraph,
        component_id: str,
    ) -> StateMachineConfig:
        """Auto-generate a state-machine from a component in *graph*.

        Uses the default transition table and adjusts probabilities /
        side-effects based on component type, replicas and health.
        """
        comp = graph.get_component(component_id)
        if comp is None:
            raise ValueError(f"component {component_id!r} not found in graph")

        all_states = list(ComponentState)
        transitions = self._adapt_transitions(comp, _DEFAULT_TRANSITIONS)
        forbidden = list(_DEFAULT_FORBIDDEN)

        # Components with replicas > 1 are less likely to terminate.
        if comp.replicas > 1:
            for t in transitions:
                if t.to_state == ComponentState.TERMINATED:
                    t = t.model_copy(update={"probability": t.probability * 0.5})

        return StateMachineConfig(
            component_id=component_id,
            states=all_states,
            transitions=transitions,
            initial_state=self._initial_state_for(comp),
            forbidden_transitions=forbidden,
        )

    def inject_state_chaos(
        self,
        graph: InfraGraph,
        component_id: str,
        trigger: TransitionTrigger,
    ) -> ChaosInjectionResult:
        """Force a state transition on *component_id* using *trigger*.

        Returns the result of the chaos injection including cascade effects
        and a recovery path back to HEALTHY.
        """
        config = self.build_state_machine(graph, component_id)
        current_state = config.initial_state

        # Find matching transition from current state with this trigger.
        transition = self._find_transition(config, current_state, trigger)
        if transition is None:
            # Synthesize a forced transition.
            transition = StateTransition(
                from_state=current_state,
                to_state=self._forced_target(trigger),
                trigger=trigger,
                probability=1.0,
                duration_seconds=0.0,
                side_effects=["chaos_injected"],
            )

        cascade = self._compute_cascade_effects(graph, component_id, transition)
        recovery = self._shortest_recovery(config, transition.to_state)
        recovery_seconds = self._recovery_duration(config, recovery)
        comp = graph.get_component(component_id)
        assert comp is not None
        data_risk = _data_risk_for_component(comp, transition.to_state)

        return ChaosInjectionResult(
            triggered_transition=transition,
            cascade_effects=cascade,
            recovery_path=recovery,
            estimated_recovery_seconds=recovery_seconds,
            data_risk=data_risk,
        )

    def find_deadlock_states(
        self,
        config: StateMachineConfig,
    ) -> list[ComponentState]:
        """Return states that have no outgoing transitions (dead ends)."""
        outgoing: set[ComponentState] = set()
        for t in config.transitions:
            outgoing.add(t.from_state)
        return [s for s in config.states if s not in outgoing]

    def find_unreachable_states(
        self,
        config: StateMachineConfig,
    ) -> list[ComponentState]:
        """Return states that can never be reached from *initial_state*."""
        reachable = self._reachable_from(config, config.initial_state)
        return [s for s in config.states if s not in reachable]

    def simulate_state_sequence(
        self,
        config: StateMachineConfig,
        triggers: Sequence[TransitionTrigger],
    ) -> list[ComponentState]:
        """Walk the state machine applying *triggers* in order.

        Returns a list of states with length ``len(triggers) + 1`` — the
        initial state followed by the state after each trigger.  When a
        trigger has no matching transition the state stays unchanged.
        """
        current = config.initial_state
        path: list[ComponentState] = [current]
        for trigger in triggers:
            t = self._find_transition(config, current, trigger)
            if t is not None:
                current = t.to_state
            path.append(current)
        return path

    def analyze_recovery_paths(
        self,
        config: StateMachineConfig,
        from_state: ComponentState,
    ) -> list[RecoveryPath]:
        """Find all simple paths from *from_state* to HEALTHY.

        Returns an empty list when *from_state* is already HEALTHY or when
        no path exists.
        """
        if from_state == ComponentState.HEALTHY:
            return []

        all_paths: list[RecoveryPath] = []
        self._dfs_recovery(
            config,
            current=from_state,
            target=ComponentState.HEALTHY,
            visited=set(),
            path_states=[from_state],
            path_transitions=[],
            results=all_paths,
        )
        return all_paths

    def detect_forbidden_transitions(
        self,
        config: StateMachineConfig,
    ) -> list[ForbiddenTransitionRisk]:
        """Identify forbidden transitions that could still be triggered.

        For each forbidden (from, to) pair, check whether any trigger could
        chain through intermediate states to create the forbidden transition
        in practice.
        """
        risks: list[ForbiddenTransitionRisk] = []
        transition_lookup = self._build_transition_lookup(config)

        for from_s, to_s in config.forbidden_transitions:
            possible_triggers: list[TransitionTrigger] = []
            # Direct trigger check: is there actually a transition defined?
            for t in config.transitions:
                if t.from_state.value == from_s and t.to_state.value == to_s:
                    possible_triggers.append(t.trigger)

            # Indirect check: can we reach to_s from from_s in exactly 2 steps?
            from_state_enum = ComponentState(from_s)
            to_state_enum = ComponentState(to_s)
            for t1 in transition_lookup.get(from_state_enum, []):
                for t2 in transition_lookup.get(t1.to_state, []):
                    if t2.to_state == to_state_enum:
                        if t1.trigger not in possible_triggers:
                            possible_triggers.append(t1.trigger)

            risk_level = self._assess_forbidden_risk(possible_triggers)
            risks.append(
                ForbiddenTransitionRisk(
                    from_state=from_s,
                    to_state=to_s,
                    possible_triggers=possible_triggers,
                    risk_level=risk_level,
                )
            )
        return risks

    # -- private helpers -----------------------------------------------------

    @staticmethod
    def _adapt_transitions(
        comp: Component,
        defaults: list[StateTransition],
    ) -> list[StateTransition]:
        """Clone default transitions, adjusting for component properties."""
        adapted: list[StateTransition] = []
        for t in defaults:
            updates: dict = {}
            side_effects = list(t.side_effects)

            # Databases get longer recovery durations.
            if comp.type == ComponentType.DATABASE:
                if t.to_state == ComponentState.RECOVERING:
                    updates["duration_seconds"] = t.duration_seconds * 2.0
                if t.to_state == ComponentState.FAILING:
                    side_effects = side_effects + ["data_integrity_risk"]

            # Caches recover fast but lose data.
            if comp.type == ComponentType.CACHE:
                if t.to_state == ComponentState.RECOVERING:
                    updates["duration_seconds"] = max(1.0, t.duration_seconds * 0.5)
                if t.to_state in (ComponentState.FAILING, ComponentState.TERMINATED):
                    side_effects = side_effects + ["cache_invalidated"]

            # Load balancers affect traffic.
            if comp.type == ComponentType.LOAD_BALANCER:
                if t.to_state == ComponentState.FAILING:
                    side_effects = side_effects + ["traffic_blackhole"]

            if updates or side_effects != t.side_effects:
                updates["side_effects"] = side_effects
                adapted.append(t.model_copy(update=updates))
            else:
                adapted.append(t.model_copy())
        return adapted

    @staticmethod
    def _initial_state_for(comp: Component) -> ComponentState:
        """Map component health to its current state."""
        from faultray.model.components import HealthStatus

        mapping = {
            HealthStatus.HEALTHY: ComponentState.HEALTHY,
            HealthStatus.DEGRADED: ComponentState.DEGRADED,
            HealthStatus.OVERLOADED: ComponentState.OVERLOADED,
            HealthStatus.DOWN: ComponentState.FAILING,
        }
        return mapping.get(comp.health, ComponentState.HEALTHY)

    @staticmethod
    def _find_transition(
        config: StateMachineConfig,
        current: ComponentState,
        trigger: TransitionTrigger,
    ) -> StateTransition | None:
        """Find the first transition from *current* with *trigger*."""
        best: StateTransition | None = None
        for t in config.transitions:
            if t.from_state == current and t.trigger == trigger:
                if best is None or t.probability > best.probability:
                    best = t
        return best

    @staticmethod
    def _forced_target(trigger: TransitionTrigger) -> ComponentState:
        """Determine target state for a chaos-injected trigger with no transition."""
        mapping: dict[TransitionTrigger, ComponentState] = {
            TransitionTrigger.LOAD_INCREASE: ComponentState.OVERLOADED,
            TransitionTrigger.LOAD_DECREASE: ComponentState.HEALTHY,
            TransitionTrigger.FAILURE_DETECTED: ComponentState.FAILING,
            TransitionTrigger.HEALTH_CHECK_PASS: ComponentState.HEALTHY,
            TransitionTrigger.HEALTH_CHECK_FAIL: ComponentState.FAILING,
            TransitionTrigger.MANUAL_INTERVENTION: ComponentState.MAINTENANCE,
            TransitionTrigger.TIMEOUT: ComponentState.FAILING,
            TransitionTrigger.RESOURCE_EXHAUSTION: ComponentState.FAILING,
            TransitionTrigger.DEPENDENCY_FAILURE: ComponentState.DEGRADED,
            TransitionTrigger.DEPLOYMENT: ComponentState.DRAINING,
        }
        return mapping.get(trigger, ComponentState.FAILING)

    @staticmethod
    def _compute_cascade_effects(
        graph: InfraGraph,
        component_id: str,
        transition: StateTransition,
    ) -> list[str]:
        """Compute cascade effects on dependent components."""
        effects: list[str] = list(transition.side_effects)

        bad_states = {
            ComponentState.FAILING,
            ComponentState.TERMINATED,
            ComponentState.OVERLOADED,
        }
        if transition.to_state not in bad_states:
            return effects

        dependents = graph.get_dependents(component_id)
        for dep in dependents:
            effects.append(f"{dep.id}:degraded_by_{component_id}")

        dependencies = graph.get_dependencies(component_id)
        for d in dependencies:
            if transition.to_state == ComponentState.TERMINATED:
                effects.append(f"{d.id}:orphaned_dependency")

        return effects

    def _shortest_recovery(
        self,
        config: StateMachineConfig,
        from_state: ComponentState,
    ) -> list[ComponentState]:
        """BFS shortest path from *from_state* to HEALTHY."""
        if from_state == ComponentState.HEALTHY:
            return [ComponentState.HEALTHY]

        visited: set[ComponentState] = {from_state}
        queue: deque[list[ComponentState]] = deque([[from_state]])
        lookup = self._build_transition_lookup(config)

        while queue:
            path = queue.popleft()
            current = path[-1]
            for t in lookup.get(current, []):
                if t.to_state in visited:
                    continue
                new_path = path + [t.to_state]
                if t.to_state == ComponentState.HEALTHY:
                    return new_path
                visited.add(t.to_state)
                queue.append(new_path)

        # No path to healthy — return best effort.
        return [from_state]

    @staticmethod
    def _recovery_duration(
        config: StateMachineConfig,
        recovery_path: list[ComponentState],
    ) -> float:
        """Sum durations along a recovery path."""
        if len(recovery_path) <= 1:
            return 0.0
        total = 0.0
        for i in range(len(recovery_path) - 1):
            from_s = recovery_path[i]
            to_s = recovery_path[i + 1]
            # Find the fastest transition for this hop.
            best_dur = float("inf")
            for t in config.transitions:
                if t.from_state == from_s and t.to_state == to_s:
                    best_dur = min(best_dur, t.duration_seconds)
            if best_dur == float("inf"):
                best_dur = 30.0  # fallback
            total += best_dur
        return total

    @staticmethod
    def _build_transition_lookup(
        config: StateMachineConfig,
    ) -> dict[ComponentState, list[StateTransition]]:
        """Group transitions by from_state for quick lookup."""
        lookup: dict[ComponentState, list[StateTransition]] = {}
        for t in config.transitions:
            lookup.setdefault(t.from_state, []).append(t)
        return lookup

    def _reachable_from(
        self,
        config: StateMachineConfig,
        start: ComponentState,
    ) -> set[ComponentState]:
        """BFS to find all states reachable from *start*."""
        visited: set[ComponentState] = {start}
        queue: deque[ComponentState] = deque([start])
        lookup = self._build_transition_lookup(config)
        while queue:
            current = queue.popleft()
            for t in lookup.get(current, []):
                if t.to_state not in visited:
                    visited.add(t.to_state)
                    queue.append(t.to_state)
        return visited

    def _dfs_recovery(
        self,
        config: StateMachineConfig,
        current: ComponentState,
        target: ComponentState,
        visited: set[ComponentState],
        path_states: list[ComponentState],
        path_transitions: list[StateTransition],
        results: list[RecoveryPath],
        max_results: int = 50,
    ) -> None:
        """DFS to enumerate all simple paths from *current* to *target*."""
        if len(results) >= max_results:
            return

        lookup = self._build_transition_lookup(config)
        for t in lookup.get(current, []):
            if t.to_state in visited:
                continue
            new_states = path_states + [t.to_state]
            new_transitions = path_transitions + [t]
            if t.to_state == target:
                total_dur = sum(tr.duration_seconds for tr in new_transitions)
                results.append(
                    RecoveryPath(
                        path=new_states,
                        total_duration_seconds=total_dur,
                        transitions_used=new_transitions,
                    )
                )
            else:
                visited.add(t.to_state)
                self._dfs_recovery(
                    config,
                    current=t.to_state,
                    target=target,
                    visited=visited,
                    path_states=new_states,
                    path_transitions=new_transitions,
                    results=results,
                    max_results=max_results,
                )
                visited.discard(t.to_state)

    @staticmethod
    def _assess_forbidden_risk(triggers: list[TransitionTrigger]) -> str:
        """Classify risk level based on how many triggers could cause it."""
        if not triggers:
            return "low"
        high_risk_triggers = {
            TransitionTrigger.RESOURCE_EXHAUSTION,
            TransitionTrigger.FAILURE_DETECTED,
            TransitionTrigger.TIMEOUT,
        }
        if any(t in high_risk_triggers for t in triggers):
            return "high"
        if len(triggers) >= 2:
            return "medium"
        return "medium"
