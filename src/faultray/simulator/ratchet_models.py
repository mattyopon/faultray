# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Pydantic models for Sensitivity Ratchet simulation.

The Sensitivity Ratchet is a security mechanism where, once an AI agent
accesses data at sensitivity level S, its outbound permissions narrow
irreversibly.  This module defines the data structures used to simulate
and quantify the ratchet's effectiveness at preventing data leaks.

Concept origin: agent-iam PermissionEngine (sensitivity ratchet + scope
narrowing).  This module is self-contained and does NOT depend on agent-iam.
"""

from __future__ import annotations

from enum import IntEnum

from pydantic import BaseModel, Field


class SensitivityLevel(IntEnum):
    """Data sensitivity classification.  Higher = more restricted."""

    PUBLIC = 0
    INTERNAL = 1
    CONFIDENTIAL = 2
    RESTRICTED = 3
    TOP_SECRET = 4


class RatchetState(BaseModel):
    """Tracks the ratchet high-water mark and remaining permissions.

    Once the agent touches data at a given sensitivity, the high-water mark
    ratchets up and permissions narrow irreversibly.
    """

    high_water_mark: SensitivityLevel = SensitivityLevel.PUBLIC
    remaining_permissions: set[str] = Field(
        default_factory=lambda: {
            "read:internal",
            "read:external",
            "write:internal",
            "write:external",
            "execute:tool",
            "send:external_api",
        }
    )
    access_history: list[str] = Field(default_factory=list)

    model_config = {"arbitrary_types_allowed": True}

    def apply_ratchet(self, accessed_sensitivity: SensitivityLevel) -> None:
        """Narrow permissions after accessing data at the given sensitivity.

        Rules (mirroring agent-iam PermissionEngine.narrow_scopes):
        - CONFIDENTIAL+: remove execute and send:external_api
        - RESTRICTED+: remove all write and send scopes
        - TOP_SECRET: read-only on internal resources only
        """
        if accessed_sensitivity > self.high_water_mark:
            self.high_water_mark = accessed_sensitivity

        self.access_history.append(
            f"accessed:{accessed_sensitivity.name}"
        )

        if accessed_sensitivity >= SensitivityLevel.CONFIDENTIAL:
            self.remaining_permissions.discard("execute:tool")
            self.remaining_permissions.discard("send:external_api")

        if accessed_sensitivity >= SensitivityLevel.RESTRICTED:
            self.remaining_permissions.discard("write:external")
            self.remaining_permissions.discard("write:internal")

        if accessed_sensitivity >= SensitivityLevel.TOP_SECRET:
            self.remaining_permissions.discard("read:external")


class AgentAction(BaseModel):
    """A single action an agent attempts during simulation."""

    action_type: str  # "access_data", "send_external", "write_internal", etc.
    target: str  # resource identifier
    sensitivity: SensitivityLevel = SensitivityLevel.PUBLIC
    required_permission: str = ""  # e.g. "send:external_api"


class LeakEvent(BaseModel):
    """Records a data leak that occurred (or was prevented) during simulation."""

    step: int
    agent_id: str
    action: AgentAction
    data_sensitivity: SensitivityLevel
    leaked: bool
    prevented_by_ratchet: bool
    detail: str = ""


class AgentSimProfile(BaseModel):
    """Defines an agent's behaviour sequence for simulation."""

    agent_id: str
    initial_permissions: set[str] = Field(
        default_factory=lambda: {
            "read:internal",
            "read:external",
            "write:internal",
            "write:external",
            "execute:tool",
            "send:external_api",
        }
    )
    actions: list[AgentAction] = Field(default_factory=list)

    model_config = {"arbitrary_types_allowed": True}


class RatchetSimulationResult(BaseModel):
    """Outcome of a ratchet effectiveness simulation.

    Compares damage with and without the ratchet mechanism.
    """

    scenario_name: str
    agents: list[str] = Field(default_factory=list)
    total_actions: int = 0

    # Damage metrics
    with_ratchet_leaks: int = 0
    without_ratchet_leaks: int = 0
    prevented_leaks: int = 0

    # Weighted damage (higher sensitivity = higher damage)
    with_ratchet_damage: float = 0.0
    without_ratchet_damage: float = 0.0
    prevented_damage: float = 0.0

    # 0.0 = ratchet prevents nothing, 1.0 = ratchet prevents all damage
    effectiveness_score: float = 0.0

    leak_events: list[LeakEvent] = Field(default_factory=list)
    ratchet_final_states: dict[str, dict] = Field(default_factory=dict)

    model_config = {"arbitrary_types_allowed": True}
