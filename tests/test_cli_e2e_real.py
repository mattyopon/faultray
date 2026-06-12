# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Real CLI E2E tests — no mocks, runs actual faultray commands.

These tests execute the real CLI binary and verify output.
They test what a user would actually experience.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

_PYTHON = sys.executable  # the interpreter running the tests, not whatever "python3" resolves to
_TIMEOUT = 60

SAMPLE_YAML = """\
schema_version: "3.0"
components:
  - id: web
    name: Web Server
    type: app_server
    replicas: 2
  - id: db
    name: Database
    type: database
    replicas: 1
dependencies:
  - source: web
    target: db
    type: requires
"""


def _run(args: list[str], timeout: int = _TIMEOUT) -> subprocess.CompletedProcess[str]:
    """Run a faultray CLI command and return the result."""
    return subprocess.run(
        [_PYTHON, "-m", "faultray"] + args,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(Path(__file__).parent.parent),
    )


class TestCLIVersion:
    """faultray --version."""

    def test_version_prints(self) -> None:
        import faultray

        r = _run(["--version"])
        assert r.returncode == 0
        assert faultray.__version__ in r.stdout

    def test_version_format(self) -> None:
        r = _run(["--version"])
        assert "FaultRay" in r.stdout


class TestCLIDemo:
    """faultray demo — runs a full demo simulation without any input."""

    def test_demo_runs_without_error(self) -> None:
        r = _run(["demo"])
        assert r.returncode == 0

    def test_demo_shows_score(self) -> None:
        r = _run(["demo"])
        assert "Resilience Score" in r.stdout or "score" in r.stdout.lower()

    def test_demo_shows_scenarios(self) -> None:
        r = _run(["demo"])
        assert "Scenarios" in r.stdout or "scenarios" in r.stdout.lower()

    def test_demo_shows_components(self) -> None:
        r = _run(["demo"])
        assert "Components" in r.stdout or "components" in r.stdout.lower()


class TestCLILoadAndSimulate:
    """faultray load + faultray simulate — the core user flow."""

    def test_load_yaml(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
            f.write(SAMPLE_YAML)
            f.flush()
            try:
                r = _run(["load", f.name])
                assert r.returncode == 0
                assert "Loading" in r.stdout or "Infrastructure" in r.stdout
            finally:
                os.unlink(f.name)

    def test_load_creates_model_json(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
            f.write(SAMPLE_YAML)
            f.flush()
            try:
                _run(["load", f.name])
                model_path = Path(__file__).parent.parent / "faultray-model.json"
                assert model_path.exists()
            finally:
                os.unlink(f.name)

    def test_simulate_after_load(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
            f.write(SAMPLE_YAML)
            f.flush()
            try:
                _run(["load", f.name])
                r = _run(["simulate"])
                assert r.returncode == 0
                assert "Resilience Score" in r.stdout or "Simulation" in r.stdout
            finally:
                os.unlink(f.name)

    def test_simulate_shows_scenario_count(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
            f.write(SAMPLE_YAML)
            f.flush()
            try:
                _run(["load", f.name])
                r = _run(["simulate"])
                assert "Scenarios" in r.stdout or "tested" in r.stdout
            finally:
                os.unlink(f.name)


class TestCLIGovernance:
    """faultray governance commands."""

    def test_governance_assess_auto(self) -> None:
        r = _run(["governance", "assess", "--auto"])
        assert r.returncode == 0
        out = r.stdout.lower()
        assert "maturity" in out or "score" in out or "level" in out

    def test_governance_cross_map(self) -> None:
        r = _run(["governance", "cross-map"])
        assert r.returncode == 0
        assert "METI" in r.stdout or "ISO" in r.stdout

    def test_governance_gap_analysis(self) -> None:
        r = _run(["governance", "gap-analysis"])
        # May need assessment first, but should not crash
        assert r.returncode in (0, 1)

    def test_governance_policy_generate(self) -> None:
        r = _run(["governance", "policy", "generate", "--type", "ai_usage", "--org-name", "TestCorp"])
        assert r.returncode in (0, 1)  # May fail gracefully if no assessment


class TestCLIAPM:
    """faultray apm commands."""

    def test_apm_status(self) -> None:
        r = _run(["apm", "status"])
        assert r.returncode in (0, 1)
        assert "running" in r.stdout.lower() or "not running" in r.stdout.lower() or "PID" in r.stdout

    def test_apm_help_shows_architecture(self) -> None:
        r = _run(["apm", "help"])
        assert r.returncode == 0
        assert "Architecture" in r.stdout or "APM" in r.stdout

    def test_apm_help_shows_commands(self) -> None:
        r = _run(["apm", "help"])
        assert "install" in r.stdout or "start" in r.stdout


class TestCLIRemediate:
    """faultray remediate commands."""

    def test_remediate_report_no_crash(self) -> None:
        r = _run(["remediate", "report"])
        assert r.returncode in (0, 1)

    def test_remediate_history_no_crash(self) -> None:
        r = _run(["remediate", "history"])
        assert r.returncode in (0, 1)

    def test_remediate_pending_no_crash(self) -> None:
        r = _run(["remediate", "pending"])
        assert r.returncode in (0, 1)

    def test_remediate_dry_run(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
            f.write(SAMPLE_YAML)
            f.flush()
            try:
                _run(["load", f.name])
                r = _run(["remediate", "run"])
                # Dry-run by default, should not crash
                assert r.returncode in (0, 1)
            finally:
                os.unlink(f.name)


class TestCLIHelp:
    """All major commands have --help and don't crash."""

    @pytest.mark.parametrize("cmd", [
        [],
        ["demo"],
        ["simulate"],
        ["governance"],
        ["apm"],
        ["remediate"],
        ["scan"],
        ["serve"],
    ])
    def test_help_does_not_crash(self, cmd: list[str]) -> None:
        r = _run(cmd + ["--help"], timeout=15)
        assert r.returncode == 0
        assert "Usage" in r.stdout or "usage" in r.stdout or "Options" in r.stdout
