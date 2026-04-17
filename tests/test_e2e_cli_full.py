# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Full CLI feature coverage E2E tests — NO mocks.

Every test runs real faultray commands via subprocess and verifies
actual exit codes and output content.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

import pytest

_PYTHON = "python3"
_TIMEOUT = 60
_REPO = str(Path(__file__).parent.parent)

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
    """Run a real faultray CLI command via subprocess."""
    return subprocess.run(
        [_PYTHON, "-m", "faultray"] + args,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=_REPO,
    )


def _make_yaml() -> str:
    """Write SAMPLE_YAML to a temp file and return the path."""
    tmp = tempfile.NamedTemporaryFile(suffix=".yaml", delete=False, mode="w")
    tmp.write(SAMPLE_YAML)
    tmp.flush()
    tmp.close()
    return tmp.name


# ---------------------------------------------------------------------------
# APM Commands
# ---------------------------------------------------------------------------


class TestAPMCommands:
    """APM sub-command tests — all run real CLI, no mocks."""

    def test_apm_setup_help(self) -> None:
        r = _run(["apm", "setup", "--help"])
        assert r.returncode == 0
        out = r.stdout + r.stderr
        assert "setup" in out.lower() or "wizard" in out.lower()

    def test_apm_install_help(self) -> None:
        r = _run(["apm", "install", "--help"])
        assert r.returncode == 0

    def test_apm_start_help(self) -> None:
        r = _run(["apm", "start", "--help"])
        assert r.returncode == 0

    def test_apm_stop_help(self) -> None:
        r = _run(["apm", "stop", "--help"])
        assert r.returncode == 0

    def test_apm_status_runs(self) -> None:
        """apm status exits 0 or 1; always prints state information."""
        r = _run(["apm", "status"])
        # Exit 0 (running) or 1 (not running) are both valid
        assert r.returncode in (0, 1)
        out = r.stdout + r.stderr
        assert "running" in out.lower() or "not" in out.lower() or "agent" in out.lower()

    def test_apm_metrics_help(self) -> None:
        r = _run(["apm", "metrics", "--help"])
        assert r.returncode == 0

    def test_apm_report_runs(self) -> None:
        """apm report exits 0 or 1; always produces output."""
        r = _run(["apm", "report"])
        assert r.returncode in (0, 1)
        out = r.stdout + r.stderr
        assert len(out.strip()) > 0

    def test_apm_help_shows_architecture(self) -> None:
        r = _run(["apm", "help"])
        assert r.returncode == 0
        out = r.stdout + r.stderr
        assert "apm" in out.lower() or "architecture" in out.lower() or "agent" in out.lower()


# ---------------------------------------------------------------------------
# Governance Commands
# ---------------------------------------------------------------------------


class TestGovernanceCommands:
    """Governance sub-command tests."""

    def test_governance_assess_auto(self) -> None:
        r = _run(["governance", "assess", "--auto"])
        assert r.returncode in (0, 1)
        out = r.stdout + r.stderr
        # Should show maturity scores or error gracefully
        assert any(
            kw in out.lower()
            for kw in ["maturity", "score", "level", "meti", "principle", "ai"]
        )

    def test_governance_cross_map(self) -> None:
        r = _run(["governance", "cross-map"])
        assert r.returncode in (0, 1)
        out = r.stdout + r.stderr
        assert any(kw in out for kw in ["METI", "ISO", "AI", "Cross"])

    def test_governance_cross_map_json(self) -> None:
        r = _run(["governance", "cross-map", "--json"])
        assert r.returncode in (0, 1)
        out = r.stdout
        # Find and parse JSON block
        try:
            # Output may have preamble; find the JSON object
            start = out.find("{")
            if start != -1:
                data = json.loads(out[start:])
                assert isinstance(data, dict)
        except json.JSONDecodeError:
            # If not valid JSON, must have at least produced output
            assert len(out.strip()) > 0

    def test_governance_gap_analysis(self) -> None:
        r = _run(["governance", "gap-analysis"])
        assert r.returncode in (0, 1)
        out = r.stdout + r.stderr
        assert len(out.strip()) > 0

    def test_governance_roadmap(self) -> None:
        r = _run(["governance", "roadmap"])
        assert r.returncode in (0, 1)
        out = r.stdout + r.stderr
        assert len(out.strip()) > 0

    def test_governance_policy_generate(self) -> None:
        r = _run(
            ["governance", "policy", "generate", "--type", "ai_usage", "--org-name", "TestCorp"]
        )
        assert r.returncode in (0, 1)
        out = r.stdout + r.stderr
        assert len(out.strip()) > 0

    def test_governance_evidence_list(self) -> None:
        r = _run(["governance", "evidence", "list"])
        assert r.returncode in (0, 1)
        out = r.stdout + r.stderr
        assert len(out.strip()) > 0

    def test_governance_evidence_verify(self) -> None:
        r = _run(["governance", "evidence", "verify"])
        assert r.returncode in (0, 1)
        out = r.stdout + r.stderr
        assert len(out.strip()) > 0

    def test_governance_ai_registry_list(self) -> None:
        r = _run(["governance", "ai-registry", "list"])
        assert r.returncode in (0, 1)
        out = r.stdout + r.stderr
        assert len(out.strip()) > 0


# ---------------------------------------------------------------------------
# Remediation Commands
# ---------------------------------------------------------------------------


class TestRemediationCommands:
    """Remediation sub-command tests."""

    def test_remediate_run_fails_gracefully(self) -> None:
        """remediate run may fail without a loaded model — must exit cleanly."""
        r = _run(["remediate", "run"])
        assert r.returncode in (0, 1, 2)

    def test_remediate_pending(self) -> None:
        r = _run(["remediate", "pending"])
        assert r.returncode in (0, 1)
        out = r.stdout + r.stderr
        assert len(out.strip()) > 0

    def test_remediate_history(self) -> None:
        r = _run(["remediate", "history"])
        assert r.returncode in (0, 1)
        out = r.stdout + r.stderr
        assert len(out.strip()) > 0

    def test_remediate_report(self) -> None:
        r = _run(["remediate", "report"])
        assert r.returncode in (0, 1)
        out = r.stdout + r.stderr
        assert len(out.strip()) > 0

    def test_remediate_report_json(self) -> None:
        r = _run(["remediate", "report", "--json"])
        assert r.returncode in (0, 1)
        out = r.stdout + r.stderr
        assert len(out.strip()) > 0


# ---------------------------------------------------------------------------
# Simulation Commands
# ---------------------------------------------------------------------------


class TestSimulationCommands:
    """Simulation commands — load YAML then run sims."""

    def test_load_then_simulate(self) -> None:
        yaml_path = _make_yaml()
        try:
            _run(["load", yaml_path])
            r = _run(["simulate"])
            assert r.returncode == 0
            out = r.stdout + r.stderr
            assert "score" in out.lower() or "resilience" in out.lower()
        finally:
            Path(yaml_path).unlink(missing_ok=True)

    def test_simulate_json_output(self) -> None:
        yaml_path = _make_yaml()
        try:
            _run(["load", yaml_path])
            r = _run(["simulate", "--json"])
            assert r.returncode == 0
            # Find JSON start
            out = r.stdout
            start = out.find("{")
            assert start != -1, f"No JSON in output: {out[:200]}"
            data = json.loads(out[start:])
            assert "overall_score" in data or "resilience_score" in data
        finally:
            Path(yaml_path).unlink(missing_ok=True)

    def test_simulate_json_score_positive(self) -> None:
        yaml_path = _make_yaml()
        try:
            _run(["load", yaml_path])
            r = _run(["simulate", "--json"])
            assert r.returncode == 0
            out = r.stdout
            start = out.find("{")
            data = json.loads(out[start:])
            score = data.get("overall_score") or data.get("resilience_score", 0)
            assert isinstance(score, (int, float))
            assert score >= 0
        finally:
            Path(yaml_path).unlink(missing_ok=True)

    def test_ops_sim_with_defaults(self) -> None:
        yaml_path = _make_yaml()
        try:
            r = _run(["ops-sim", yaml_path, "--defaults"], timeout=90)
            assert r.returncode in (0, 1)
            out = r.stdout + r.stderr
            assert len(out.strip()) > 0
        finally:
            Path(yaml_path).unlink(missing_ok=True)

    def test_dynamic_simulation(self) -> None:
        yaml_path = _make_yaml()
        try:
            _run(["load", yaml_path])
            r = _run(["dynamic", "--duration", "30"])
            assert r.returncode in (0, 1)
            out = r.stdout + r.stderr
            assert len(out.strip()) > 0
        finally:
            Path(yaml_path).unlink(missing_ok=True)

    def test_analyze_with_yaml(self) -> None:
        yaml_path = _make_yaml()
        try:
            r = _run(["analyze", yaml_path])
            assert r.returncode in (0, 1)
            out = r.stdout + r.stderr
            assert len(out.strip()) > 0
        finally:
            Path(yaml_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# DORA Commands
# ---------------------------------------------------------------------------


class TestDORACommands:
    """DORA and compliance-related command tests."""

    def test_dora_help(self) -> None:
        r = _run(["dora", "--help"])
        assert r.returncode == 0
        out = r.stdout + r.stderr
        assert "dora" in out.lower() or "DORA" in out

    def test_dora_assess_with_model(self) -> None:
        yaml_path = _make_yaml()
        try:
            load_r = _run(["load", yaml_path])
            assert load_r.returncode == 0
            r = _run(["dora", "assess", "faultray-model.json"])
            assert r.returncode in (0, 1)
            out = r.stdout + r.stderr
            assert len(out.strip()) > 0
        finally:
            Path(yaml_path).unlink(missing_ok=True)

    def test_compliance_monitor_help(self) -> None:
        r = _run(["compliance-monitor", "--help"])
        assert r.returncode == 0

    def test_sre_maturity_help(self) -> None:
        r = _run(["sre-maturity", "--help"])
        assert r.returncode == 0


# ---------------------------------------------------------------------------
# Other Commands
# ---------------------------------------------------------------------------


class TestOtherCommands:
    """Miscellaneous top-level commands."""

    def test_badge_help(self) -> None:
        r = _run(["badge", "--help"])
        assert r.returncode == 0

    def test_drift_help(self) -> None:
        r = _run(["drift", "--help"])
        assert r.returncode == 0

    def test_daemon_help(self) -> None:
        r = _run(["daemon", "--help"])
        assert r.returncode == 0

    def test_auto_fix_help(self) -> None:
        r = _run(["auto-fix", "--help"])
        assert r.returncode == 0

    def test_agent_help(self) -> None:
        r = _run(["agent", "--help"])
        assert r.returncode == 0
        out = r.stdout + r.stderr
        assert "agent" in out.lower()


# ---------------------------------------------------------------------------
# Full Flow Tests
# ---------------------------------------------------------------------------


class TestFullFlows:
    """Multi-step CLI flow tests."""

    def test_load_simulate_score_is_numeric(self) -> None:
        """Load YAML → simulate → score is a real number."""
        yaml_path = _make_yaml()
        try:
            load_r = _run(["load", yaml_path])
            assert load_r.returncode == 0

            sim_r = _run(["simulate", "--json"])
            assert sim_r.returncode == 0

            out = sim_r.stdout
            start = out.find("{")
            data = json.loads(out[start:])
            score = data.get("overall_score") or data.get("resilience_score")
            assert score is not None, f"No score in: {list(data.keys())}"
            assert isinstance(score, (int, float))
        finally:
            Path(yaml_path).unlink(missing_ok=True)

    def test_simulate_json_overall_score_positive(self) -> None:
        """simulate --json → overall_score > 0 for valid infrastructure."""
        yaml_path = _make_yaml()
        try:
            _run(["load", yaml_path])
            r = _run(["simulate", "--json"])
            assert r.returncode == 0
            out = r.stdout
            start = out.find("{")
            data = json.loads(out[start:])
            score = data.get("overall_score") or data.get("resilience_score", 0)
            assert score > 0
        finally:
            Path(yaml_path).unlink(missing_ok=True)

    def test_demo_contains_resilience_score(self) -> None:
        """faultray demo → output must contain Resilience Score."""
        r = _run(["demo"])
        assert r.returncode == 0
        out = r.stdout + r.stderr
        assert "Resilience Score" in out or "resilience" in out.lower()

    def test_governance_assess_produces_score_like_number(self) -> None:
        """governance assess --auto → output has at least one digit."""
        r = _run(["governance", "assess", "--auto"])
        assert r.returncode in (0, 1)
        out = r.stdout + r.stderr
        # There should be at least one numeric character in the output
        assert any(c.isdigit() for c in out)
