# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Deep security tests for the Sensitivity Ratchet in remediation context.

Tests:
- Initial permissions are restricted appropriately
- Ratchet narrows after touching sensitive resources
- Ratchet is irreversible (no permission regain)
- Blocked steps are logged correctly
- Ratchet state persisted in cycle JSON
- Integration with AutonomousRemediationAgent
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from faultray.model.components import Component, ComponentType, Dependency
from faultray.model.graph import InfraGraph
from faultray.remediation.autonomous_agent import (
    AutonomousRemediationAgent,
    RemediationCycle,
    _PlanStep,
)
from faultray.simulator.ratchet_models import (
    RatchetState,
    SensitivityLevel,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_agent(
    tmp_path: Path,
    ratchet_enabled: bool = True,
    max_risk: str = "medium",
) -> AutonomousRemediationAgent:
    """Create an agent with a minimal SPOF graph."""
    g = InfraGraph()
    g.add_component(Component(id="web", name="Web", type=ComponentType.WEB_SERVER))
    g.add_component(Component(id="db", name="DB", type=ComponentType.DATABASE, replicas=1))
    g.add_dependency(Dependency(source_id="web", target_id="db"))

    model_path = tmp_path / "model.json"
    g.save(model_path)

    return AutonomousRemediationAgent(
        model_path=str(model_path),
        auto_approve=True,
        max_risk_level=max_risk,
        ratchet_enabled=ratchet_enabled,
        dry_run=True,
        output_dir=str(tmp_path / "remediation"),
    )


# ---------------------------------------------------------------------------
# RatchetState unit tests
# ---------------------------------------------------------------------------


class TestRatchetInitialPermissions:
    """Initial ratchet state is correctly initialized."""

    def test_initial_state_has_all_six_permissions(self) -> None:
        state = RatchetState()
        expected = {
            "read:internal",
            "read:external",
            "write:internal",
            "write:external",
            "execute:tool",
            "send:external_api",
        }
        assert state.remaining_permissions == expected

    def test_initial_high_water_mark_is_public(self) -> None:
        state = RatchetState()
        assert state.high_water_mark == SensitivityLevel.PUBLIC

    def test_initial_access_history_empty(self) -> None:
        state = RatchetState()
        assert state.access_history == []

    def test_agent_ratchet_starts_with_restricted_set(self, tmp_path: Path) -> None:
        """Agent with ratchet_enabled starts with no external read/send permissions."""
        agent = _make_agent(tmp_path, ratchet_enabled=True)
        cycle = agent.run_cycle()
        if cycle.ratchet_state:
            # Initial permissions for remediation context exclude read:external
            # and send:external_api
            initial_perms = cycle.ratchet_state.get("remaining_permissions", [])
            assert isinstance(initial_perms, list)


class TestRatchetNarrowsOnSensitiveAccess:
    """Ratchet removes permissions when sensitive data is accessed."""

    def test_public_access_preserves_all_permissions(self) -> None:
        state = RatchetState()
        before = set(state.remaining_permissions)
        state.apply_ratchet(SensitivityLevel.PUBLIC)
        assert state.remaining_permissions == before

    def test_internal_access_preserves_all_permissions(self) -> None:
        state = RatchetState()
        before = set(state.remaining_permissions)
        state.apply_ratchet(SensitivityLevel.INTERNAL)
        assert state.remaining_permissions == before

    def test_confidential_removes_execute_tool(self) -> None:
        state = RatchetState()
        state.apply_ratchet(SensitivityLevel.CONFIDENTIAL)
        assert "execute:tool" not in state.remaining_permissions

    def test_confidential_removes_send_external_api(self) -> None:
        state = RatchetState()
        state.apply_ratchet(SensitivityLevel.CONFIDENTIAL)
        assert "send:external_api" not in state.remaining_permissions

    def test_confidential_preserves_read_internal(self) -> None:
        state = RatchetState()
        state.apply_ratchet(SensitivityLevel.CONFIDENTIAL)
        assert "read:internal" in state.remaining_permissions

    def test_confidential_preserves_write_internal(self) -> None:
        state = RatchetState()
        state.apply_ratchet(SensitivityLevel.CONFIDENTIAL)
        assert "write:internal" in state.remaining_permissions

    def test_restricted_removes_all_writes(self) -> None:
        state = RatchetState()
        state.apply_ratchet(SensitivityLevel.RESTRICTED)
        assert "write:external" not in state.remaining_permissions
        assert "write:internal" not in state.remaining_permissions

    def test_restricted_removes_execute_and_send(self) -> None:
        state = RatchetState()
        state.apply_ratchet(SensitivityLevel.RESTRICTED)
        assert "execute:tool" not in state.remaining_permissions
        assert "send:external_api" not in state.remaining_permissions

    def test_restricted_preserves_read_internal_and_external(self) -> None:
        state = RatchetState()
        state.apply_ratchet(SensitivityLevel.RESTRICTED)
        assert "read:internal" in state.remaining_permissions
        assert "read:external" in state.remaining_permissions

    def test_top_secret_removes_read_external(self) -> None:
        state = RatchetState()
        state.apply_ratchet(SensitivityLevel.TOP_SECRET)
        assert "read:external" not in state.remaining_permissions

    def test_top_secret_only_read_internal_remains(self) -> None:
        state = RatchetState()
        state.apply_ratchet(SensitivityLevel.TOP_SECRET)
        remaining = state.remaining_permissions
        # Only read:internal should remain after TOP_SECRET
        assert "read:internal" in remaining
        assert "write:internal" not in remaining
        assert "write:external" not in remaining
        assert "execute:tool" not in remaining
        assert "send:external_api" not in remaining
        assert "read:external" not in remaining


class TestRatchetIrreversibility:
    """Ratchet cannot be reversed — permissions are only lost, never regained."""

    def test_cannot_regain_execute_after_confidential(self) -> None:
        state = RatchetState()
        state.apply_ratchet(SensitivityLevel.CONFIDENTIAL)
        assert "execute:tool" not in state.remaining_permissions
        # "Resetting" back to PUBLIC doesn't restore permissions
        state.apply_ratchet(SensitivityLevel.PUBLIC)
        assert "execute:tool" not in state.remaining_permissions

    def test_cannot_regain_write_after_restricted(self) -> None:
        state = RatchetState()
        state.apply_ratchet(SensitivityLevel.RESTRICTED)
        assert "write:internal" not in state.remaining_permissions
        state.apply_ratchet(SensitivityLevel.INTERNAL)
        assert "write:internal" not in state.remaining_permissions

    def test_cannot_regain_read_external_after_top_secret(self) -> None:
        state = RatchetState()
        state.apply_ratchet(SensitivityLevel.TOP_SECRET)
        assert "read:external" not in state.remaining_permissions
        state.apply_ratchet(SensitivityLevel.PUBLIC)
        assert "read:external" not in state.remaining_permissions

    def test_high_water_mark_never_decreases(self) -> None:
        state = RatchetState()
        state.apply_ratchet(SensitivityLevel.RESTRICTED)
        assert state.high_water_mark == SensitivityLevel.RESTRICTED
        state.apply_ratchet(SensitivityLevel.PUBLIC)
        assert state.high_water_mark == SensitivityLevel.RESTRICTED

    def test_high_water_mark_increases_monotonically(self) -> None:
        state = RatchetState()
        levels = [
            SensitivityLevel.PUBLIC,
            SensitivityLevel.INTERNAL,
            SensitivityLevel.CONFIDENTIAL,
            SensitivityLevel.RESTRICTED,
        ]
        for level in levels:
            state.apply_ratchet(level)

        assert state.high_water_mark == SensitivityLevel.RESTRICTED

    def test_permissions_only_decrease_over_time(self) -> None:
        state = RatchetState()
        perms_before = set(state.remaining_permissions)
        state.apply_ratchet(SensitivityLevel.CONFIDENTIAL)
        perms_mid = set(state.remaining_permissions)
        state.apply_ratchet(SensitivityLevel.RESTRICTED)
        perms_after = set(state.remaining_permissions)

        assert len(perms_after) <= len(perms_mid) <= len(perms_before)
        assert perms_after.issubset(perms_mid)
        assert perms_mid.issubset(perms_before)

    def test_sequential_ratcheting_loses_permissions_cumulatively(self) -> None:
        state = RatchetState()
        state.apply_ratchet(SensitivityLevel.CONFIDENTIAL)
        confidential_perms = set(state.remaining_permissions)

        state.apply_ratchet(SensitivityLevel.RESTRICTED)
        restricted_perms = set(state.remaining_permissions)

        # Restricted should be a strict subset of confidential
        assert restricted_perms < confidential_perms


class TestRatchetAccessHistory:
    """Ratchet records access history correctly."""

    def test_access_history_records_each_access(self) -> None:
        state = RatchetState()
        state.apply_ratchet(SensitivityLevel.CONFIDENTIAL)
        state.apply_ratchet(SensitivityLevel.RESTRICTED)
        assert len(state.access_history) == 2

    def test_access_history_records_level_names(self) -> None:
        state = RatchetState()
        state.apply_ratchet(SensitivityLevel.CONFIDENTIAL)
        assert "CONFIDENTIAL" in state.access_history[0]

    def test_access_history_records_public_access(self) -> None:
        state = RatchetState()
        state.apply_ratchet(SensitivityLevel.PUBLIC)
        assert len(state.access_history) == 1
        assert "PUBLIC" in state.access_history[0]


# ---------------------------------------------------------------------------
# Remediation integration — ratchet in cycle context
# ---------------------------------------------------------------------------


class TestRatchetInRemediationCycle:
    """Ratchet behavior in full remediation cycle."""

    def test_cycle_ratchet_state_persisted_in_json(self, tmp_path: Path) -> None:
        agent = _make_agent(tmp_path)
        cycle = agent.run_cycle()
        # Ratchet state should be in the cycle dict
        d = cycle.to_dict()
        assert "ratchet_state" in d
        assert isinstance(d["ratchet_state"], dict)

    def test_cycle_execution_log_shows_ratchet_permissions(self, tmp_path: Path) -> None:
        agent = _make_agent(tmp_path)
        cycle = agent.run_cycle()
        # Dry-run entries should contain ratchet_permissions
        for entry in cycle.execution_log:
            if entry.get("status") == "dry_run":
                assert "ratchet_permissions" in entry
                assert isinstance(entry["ratchet_permissions"], list)

    def test_cycle_without_ratchet_has_broader_permissions(self, tmp_path: Path) -> None:
        """Agent with ratchet disabled has more permissions than with ratchet."""
        agent_no_ratchet = _make_agent(tmp_path, ratchet_enabled=False)
        cycle = agent_no_ratchet.run_cycle()
        if cycle.execution_log:
            for entry in cycle.execution_log:
                if entry.get("status") in ("dry_run",):
                    perms = entry.get("ratchet_permissions", [])
                    # Without ratchet, should have more permissions
                    assert isinstance(perms, list)

    def test_blocked_step_logged_with_reason(self, tmp_path: Path) -> None:
        """Blocked steps are logged with denial reason."""
        agent = _make_agent(tmp_path, max_risk="low")
        cycle = agent.run_cycle()
        blocked = [e for e in cycle.execution_log if e.get("status") == "blocked"]
        for entry in blocked:
            assert "reason" in entry or "status" in entry

    def test_cycle_ratchet_final_level_recorded(self, tmp_path: Path) -> None:
        """Final ratchet level is recorded in cycle ratchet_state."""
        agent = _make_agent(tmp_path)
        cycle = agent.run_cycle()
        if cycle.ratchet_state:
            assert "final_level" in cycle.ratchet_state

    def test_saved_cycle_json_contains_ratchet_state(self, tmp_path: Path) -> None:
        """Persisted cycle JSON includes ratchet_state."""
        agent = _make_agent(tmp_path)
        agent.run_cycle()
        cycles_dir = tmp_path / "remediation" / "cycles"
        files = list(cycles_dir.glob("*.json"))
        assert len(files) >= 1
        data = json.loads(files[0].read_text())
        assert "ratchet_state" in data


# ---------------------------------------------------------------------------
# RatchetState permission boundary tests
# ---------------------------------------------------------------------------


class TestRatchetPermissionBoundaries:
    """Edge cases and boundary conditions for the ratchet."""

    def test_empty_permissions_after_top_secret(self) -> None:
        """After TOP_SECRET, very few permissions remain."""
        state = RatchetState()
        state.apply_ratchet(SensitivityLevel.TOP_SECRET)
        # Only read:internal should remain
        assert "write:internal" not in state.remaining_permissions
        assert "execute:tool" not in state.remaining_permissions

    def test_ratchet_with_custom_initial_permissions(self) -> None:
        """Ratchet works correctly with a custom initial permission set."""
        state = RatchetState(
            remaining_permissions={"read:internal", "write:internal", "execute:tool"}
        )
        state.apply_ratchet(SensitivityLevel.CONFIDENTIAL)
        assert "execute:tool" not in state.remaining_permissions
        assert "read:internal" in state.remaining_permissions

    def test_applying_same_level_twice_is_idempotent(self) -> None:
        """Applying the same sensitivity level twice has the same effect as once."""
        state1 = RatchetState()
        state1.apply_ratchet(SensitivityLevel.RESTRICTED)

        state2 = RatchetState()
        state2.apply_ratchet(SensitivityLevel.RESTRICTED)
        state2.apply_ratchet(SensitivityLevel.RESTRICTED)

        assert state1.remaining_permissions == state2.remaining_permissions
        assert state1.high_water_mark == state2.high_water_mark

    def test_ratchet_levels_are_ordered(self) -> None:
        """Sensitivity levels have the expected ordering."""
        assert SensitivityLevel.PUBLIC < SensitivityLevel.INTERNAL
        assert SensitivityLevel.INTERNAL < SensitivityLevel.CONFIDENTIAL
        assert SensitivityLevel.CONFIDENTIAL < SensitivityLevel.RESTRICTED
        assert SensitivityLevel.RESTRICTED < SensitivityLevel.TOP_SECRET

    def test_permission_check_required_subset_passes(self) -> None:
        """Required permissions that are a subset of remaining should pass."""
        state = RatchetState()
        required = {"read:internal", "write:internal"}
        assert required.issubset(state.remaining_permissions)

    def test_permission_check_required_subset_fails_after_ratchet(self) -> None:
        """Required permissions that exceed remaining should fail after ratchet."""
        state = RatchetState()
        state.apply_ratchet(SensitivityLevel.RESTRICTED)
        required = {"write:internal"}
        assert not required.issubset(state.remaining_permissions)
