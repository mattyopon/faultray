# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Sensitivity Ratchet Simulation Engine.

Simulates the effectiveness of the *sensitivity ratchet* — a security
mechanism where an AI agent's outbound permissions narrow irreversibly
once it accesses data above a certain sensitivity threshold.

The simulator runs each scenario twice (WITH and WITHOUT the ratchet) and
quantifies the difference, producing a *ratchet effectiveness score* that
shows how much data-leak damage the ratchet prevents.

Integration with FaultRay:
    This module uses the existing ``CascadeEngine`` for infrastructure-level
    cascade analysis and extends the agent simulation layer with permission-
    aware behaviour modeling.

Concept origin: agent-iam ``PermissionEngine`` (sensitivity ratchet +
``narrow_scopes``).  This implementation is fully self-contained and does
NOT depend on the agent-iam package.
"""

from __future__ import annotations

import logging
from copy import deepcopy

from faultray.simulator.ratchet_models import (
    AgentAction,
    AgentSimProfile,
    LeakEvent,
    RatchetSimulationResult,
    RatchetState,
    SensitivityLevel,
)

logger = logging.getLogger(__name__)

# Damage weight per sensitivity level (used for weighted damage scoring)
_DAMAGE_WEIGHTS: dict[SensitivityLevel, float] = {
    SensitivityLevel.PUBLIC: 0.0,
    SensitivityLevel.INTERNAL: 1.0,
    SensitivityLevel.CONFIDENTIAL: 3.0,
    SensitivityLevel.RESTRICTED: 7.0,
    SensitivityLevel.TOP_SECRET: 15.0,
}

# Actions that can cause external data leaks
_EXTERNAL_ACTIONS: frozenset[str] = frozenset({
    "send_external",
    "write_external",
})

# Mapping from action_type to the permission required
_ACTION_PERMISSION_MAP: dict[str, str] = {
    "access_data": "",            # reading data is always allowed (but ratchets up)
    "send_external": "send:external_api",
    "write_external": "write:external",
    "write_internal": "write:internal",
    "execute_tool": "execute:tool",
    "read_external": "read:external",
    "read_internal": "read:internal",
}


def _resolve_required_permission(action: AgentAction) -> str:
    """Determine the permission required for an action."""
    if action.required_permission:
        return action.required_permission
    return _ACTION_PERMISSION_MAP.get(action.action_type, "")


def _is_leak_action(action: AgentAction) -> bool:
    """Return True if this action could exfiltrate data externally."""
    return action.action_type in _EXTERNAL_ACTIONS


def _damage_for(sensitivity: SensitivityLevel) -> float:
    """Return the damage weight for a given sensitivity level."""
    return _DAMAGE_WEIGHTS.get(sensitivity, 0.0)


# ──────────────────────────────────────────────────────────────────────
# Core simulation functions
# ──────────────────────────────────────────────────────────────────────


def simulate_agent_with_ratchet(
    profile: AgentSimProfile,
    ratchet_enabled: bool = True,
) -> tuple[list[LeakEvent], RatchetState]:
    """Simulate a single agent's action sequence.

    Args:
        profile: The agent's behaviour profile (actions to attempt).
        ratchet_enabled: When True, permissions narrow after sensitive
            data access.  When False, all initial permissions remain
            throughout (baseline / no-ratchet mode).

    Returns:
        A tuple of (leak_events, final_ratchet_state).
    """
    state = RatchetState(remaining_permissions=set(profile.initial_permissions))
    events: list[LeakEvent] = []
    # Track highest sensitivity data the agent has seen (for leak scoring)
    max_accessed_sensitivity = SensitivityLevel.PUBLIC

    for step, action in enumerate(profile.actions):
        # 1. If the action reads/accesses data, update ratchet
        if action.action_type == "access_data":
            if action.sensitivity > max_accessed_sensitivity:
                max_accessed_sensitivity = action.sensitivity
            if ratchet_enabled:
                state.apply_ratchet(action.sensitivity)
            else:
                state.access_history.append(f"accessed:{action.sensitivity.name}")
                if action.sensitivity > state.high_water_mark:
                    state.high_water_mark = action.sensitivity
            continue

        # 2. Check whether this action can leak data externally
        if not _is_leak_action(action):
            continue

        # 3. Check permission
        required = _resolve_required_permission(action)
        has_permission = (not required) or (required in state.remaining_permissions)

        if has_permission and max_accessed_sensitivity > SensitivityLevel.PUBLIC:
            # The agent CAN send data externally and it has seen sensitive data
            events.append(LeakEvent(
                step=step,
                agent_id=profile.agent_id,
                action=action,
                data_sensitivity=max_accessed_sensitivity,
                leaked=True,
                prevented_by_ratchet=False,
                detail=(
                    f"Agent '{profile.agent_id}' sent data externally after accessing "
                    f"{max_accessed_sensitivity.name} data. Permission '{required}' was available."
                ),
            ))
        elif not has_permission and max_accessed_sensitivity > SensitivityLevel.PUBLIC:
            # Ratchet blocked the leak
            events.append(LeakEvent(
                step=step,
                agent_id=profile.agent_id,
                action=action,
                data_sensitivity=max_accessed_sensitivity,
                leaked=False,
                prevented_by_ratchet=True,
                detail=(
                    f"Agent '{profile.agent_id}' attempted external send after accessing "
                    f"{max_accessed_sensitivity.name} data, but permission '{required}' was "
                    f"revoked by the ratchet."
                ),
            ))

    return events, state


def simulate_multi_agent_with_ratchet(
    profiles: list[AgentSimProfile],
    ratchet_enabled: bool = True,
) -> tuple[list[LeakEvent], dict[str, RatchetState]]:
    """Simulate multiple agents, including cross-agent data passing.

    When agent A accesses classified data and passes it to agent B, agent B
    inherits the sensitivity level.  With the ratchet, agent B's permissions
    also narrow upon receiving that data.

    Args:
        profiles: List of agent profiles.  Actions with action_type
            ``"pass_to_agent"`` transfer the current max sensitivity to the
            target agent (identified by ``action.target``).
        ratchet_enabled: Whether the ratchet mechanism is active.

    Returns:
        Tuple of (all_leak_events, agent_id -> final_ratchet_state).
    """
    states: dict[str, RatchetState] = {}
    max_sensitivities: dict[str, SensitivityLevel] = {}
    all_events: list[LeakEvent] = []
    {p.agent_id: p for p in profiles}

    # Initialize states
    for p in profiles:
        states[p.agent_id] = RatchetState(remaining_permissions=set(p.initial_permissions))
        max_sensitivities[p.agent_id] = SensitivityLevel.PUBLIC

    # Execute actions sequentially: process each profile's actions in
    # order, with the profiles themselves ordered by their position in
    # the input list.  This ensures that agent A's actions complete
    # (including pass_to_agent) before agent B's actions execute.
    global_actions: list[tuple[int, str, AgentAction]] = []
    step_counter = 0
    for p in profiles:
        for action in p.actions:
            global_actions.append((step_counter, p.agent_id, action))
            step_counter += 1

    for step, agent_id, action in global_actions:
        state = states[agent_id]
        max_sens = max_sensitivities[agent_id]

        if action.action_type == "access_data":
            if action.sensitivity > max_sens:
                max_sensitivities[agent_id] = action.sensitivity
            if ratchet_enabled:
                state.apply_ratchet(action.sensitivity)
            else:
                state.access_history.append(f"accessed:{action.sensitivity.name}")
                if action.sensitivity > state.high_water_mark:
                    state.high_water_mark = action.sensitivity
            continue

        if action.action_type == "pass_to_agent":
            # Transfer sensitivity to target agent
            target_id = action.target
            if target_id in states:
                inherited = max_sensitivities[agent_id]
                if inherited > max_sensitivities[target_id]:
                    max_sensitivities[target_id] = inherited
                if ratchet_enabled:
                    states[target_id].apply_ratchet(inherited)
                else:
                    states[target_id].access_history.append(
                        f"inherited:{inherited.name}:from:{agent_id}"
                    )
                    if inherited > states[target_id].high_water_mark:
                        states[target_id].high_water_mark = inherited
            continue

        if not _is_leak_action(action):
            continue

        required = _resolve_required_permission(action)
        has_permission = (not required) or (required in state.remaining_permissions)
        current_max = max_sensitivities[agent_id]

        if has_permission and current_max > SensitivityLevel.PUBLIC:
            all_events.append(LeakEvent(
                step=step,
                agent_id=agent_id,
                action=action,
                data_sensitivity=current_max,
                leaked=True,
                prevented_by_ratchet=False,
                detail=(
                    f"Agent '{agent_id}' sent data externally after accessing "
                    f"{current_max.name} data. Permission '{required}' was available."
                ),
            ))
        elif not has_permission and current_max > SensitivityLevel.PUBLIC:
            all_events.append(LeakEvent(
                step=step,
                agent_id=agent_id,
                action=action,
                data_sensitivity=current_max,
                leaked=False,
                prevented_by_ratchet=True,
                detail=(
                    f"Agent '{agent_id}' attempted external send after accessing "
                    f"{current_max.name} data, but permission '{required}' was "
                    f"revoked by the ratchet."
                ),
            ))

    return all_events, states


# ──────────────────────────────────────────────────────────────────────
# High-level simulation runner
# ──────────────────────────────────────────────────────────────────────


def run_ratchet_simulation(
    scenario_name: str,
    profiles: list[AgentSimProfile],
) -> RatchetSimulationResult:
    """Run a full ratchet effectiveness simulation.

    Executes the scenario twice — once with and once without the ratchet —
    then computes the effectiveness score.

    Args:
        scenario_name: Human-readable label for this scenario.
        profiles: Agent behaviour profiles.

    Returns:
        ``RatchetSimulationResult`` with comparative damage metrics.
    """
    # Deep-copy profiles so the two runs don't interfere
    profiles_with = deepcopy(profiles)
    profiles_without = deepcopy(profiles)

    multi = len(profiles) > 1

    if multi:
        events_with, states_with = simulate_multi_agent_with_ratchet(
            profiles_with, ratchet_enabled=True,
        )
        events_without, states_without = simulate_multi_agent_with_ratchet(
            profiles_without, ratchet_enabled=False,
        )
    else:
        events_with, state_with = simulate_agent_with_ratchet(
            profiles_with[0], ratchet_enabled=True,
        )
        events_without, state_without = simulate_agent_with_ratchet(
            profiles_without[0], ratchet_enabled=False,
        )
        states_with = {profiles_with[0].agent_id: state_with}
        {profiles_without[0].agent_id: state_without}

    # Compute damage
    damage_with = sum(
        _damage_for(e.data_sensitivity) for e in events_with if e.leaked
    )
    damage_without = sum(
        _damage_for(e.data_sensitivity) for e in events_without if e.leaked
    )
    prevented = damage_without - damage_with
    effectiveness = prevented / damage_without if damage_without > 0 else 1.0

    total_actions = sum(len(p.actions) for p in profiles)

    # Combine all events (mark which came from which run)
    events_with + events_without

    ratchet_final = {
        aid: {
            "high_water_mark": s.high_water_mark.name,
            "remaining_permissions": sorted(s.remaining_permissions),
            "access_history": s.access_history,
        }
        for aid, s in states_with.items()
    }

    return RatchetSimulationResult(
        scenario_name=scenario_name,
        agents=[p.agent_id for p in profiles],
        total_actions=total_actions,
        with_ratchet_leaks=sum(1 for e in events_with if e.leaked),
        without_ratchet_leaks=sum(1 for e in events_without if e.leaked),
        prevented_leaks=sum(1 for e in events_with if e.prevented_by_ratchet),
        with_ratchet_damage=damage_with,
        without_ratchet_damage=damage_without,
        prevented_damage=max(0.0, prevented),
        effectiveness_score=round(max(0.0, min(1.0, effectiveness)), 4),
        leak_events=events_with,  # Only report the ratchet-enabled run's events
        ratchet_final_states=ratchet_final,
    )


# ──────────────────────────────────────────────────────────────────────
# Built-in scenarios (convenience)
# ──────────────────────────────────────────────────────────────────────


def build_data_exfiltration_scenario() -> tuple[str, list[AgentSimProfile]]:
    """Classic scenario: agent reads classified data then tries to send externally.

    Without ratchet: agent reads RESTRICTED data -> sends to external API -> LEAK.
    With ratchet:    agent reads RESTRICTED data -> send permission revoked -> BLOCKED.
    """
    profile = AgentSimProfile(
        agent_id="data-agent",
        actions=[
            AgentAction(
                action_type="access_data",
                target="classified-db",
                sensitivity=SensitivityLevel.RESTRICTED,
            ),
            AgentAction(
                action_type="send_external",
                target="external-api",
                required_permission="send:external_api",
            ),
        ],
    )
    return "Data Exfiltration via External API", [profile]


def build_cross_agent_leak_scenario() -> tuple[str, list[AgentSimProfile]]:
    """Multi-agent scenario: Agent A reads classified data, passes to Agent B,
    Agent B tries to send externally.

    Without ratchet: Agent B has full permissions -> data leaks.
    With ratchet:    Agent B inherits sensitivity -> send blocked.
    """
    agent_a = AgentSimProfile(
        agent_id="agent-a",
        actions=[
            AgentAction(
                action_type="access_data",
                target="top-secret-store",
                sensitivity=SensitivityLevel.TOP_SECRET,
            ),
            AgentAction(
                action_type="pass_to_agent",
                target="agent-b",
                sensitivity=SensitivityLevel.TOP_SECRET,
            ),
        ],
    )
    agent_b = AgentSimProfile(
        agent_id="agent-b",
        actions=[
            # Step 2 (after receiving data from agent-a)
            AgentAction(
                action_type="send_external",
                target="external-endpoint",
                required_permission="send:external_api",
            ),
        ],
    )
    return "Cross-Agent Data Leak (A -> B -> External)", [agent_a, agent_b]


def build_gradual_escalation_scenario() -> tuple[str, list[AgentSimProfile]]:
    """Agent gradually accesses higher-sensitivity data, attempting external
    sends at each level.

    Demonstrates the ratchet tightening progressively.
    """
    profile = AgentSimProfile(
        agent_id="escalating-agent",
        actions=[
            # Start with public data
            AgentAction(
                action_type="access_data",
                target="public-docs",
                sensitivity=SensitivityLevel.PUBLIC,
            ),
            AgentAction(
                action_type="send_external",
                target="analytics-api",
                required_permission="send:external_api",
            ),
            # Escalate to INTERNAL
            AgentAction(
                action_type="access_data",
                target="internal-wiki",
                sensitivity=SensitivityLevel.INTERNAL,
            ),
            AgentAction(
                action_type="send_external",
                target="analytics-api",
                required_permission="send:external_api",
            ),
            # Escalate to CONFIDENTIAL (ratchet kicks in here)
            AgentAction(
                action_type="access_data",
                target="customer-pii",
                sensitivity=SensitivityLevel.CONFIDENTIAL,
            ),
            AgentAction(
                action_type="send_external",
                target="analytics-api",
                required_permission="send:external_api",
            ),
            # Escalate to RESTRICTED
            AgentAction(
                action_type="access_data",
                target="trade-secrets",
                sensitivity=SensitivityLevel.RESTRICTED,
            ),
            AgentAction(
                action_type="send_external",
                target="analytics-api",
                required_permission="send:external_api",
            ),
        ],
    )
    return "Gradual Sensitivity Escalation", [profile]
