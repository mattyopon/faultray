"""Regression test locking in that `faultray gate terraform-plan --json`
keeps informational logs (schema migration warnings) on stderr, leaving
stdout as pure pipe-friendly JSON.

This was flagged as a bug in the 2026-04-17 Phase 0 baseline validation
report (Phase 1 candidate #11). On re-verification (Issue #74, 2026-04-20)
the warning was confirmed to already be on stderr via `logger.warning()` —
the report misattributed what the user saw in an unseparated terminal.
This test cements the current behaviour so a future change that switches
to `print()` or `console.print()` (both stdout) gets caught by CI.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PLAN = REPO_ROOT / "tests" / "fixtures" / "sample-tf-plan.json"
DEMO_MODEL = REPO_ROOT / "tests" / "fixtures" / "demo-topology.json"


@pytest.fixture
def fixtures_exist() -> None:
    for p in (SAMPLE_PLAN, DEMO_MODEL):
        assert p.exists(), f"missing committed fixture: {p}"


def test_gate_terraform_plan_json_stdout_is_pure_json(fixtures_exist: None) -> None:
    """`--json` stdout must be a single JSON payload, not prefixed by logs."""
    result = subprocess.run(
        [
            sys.executable, "-m", "faultray", "gate", "terraform-plan",
            str(SAMPLE_PLAN),
            "--model", str(DEMO_MODEL),
            "--json",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    # Exit code may be 0 or 1 depending on gate outcome — either is acceptable
    # for *this* test's purpose (verifying stream separation, not gate logic).
    assert result.returncode in (0, 1), result.stderr[-400:]

    # stdout must parse as JSON on its own — no "Model uses schema" prefix.
    # This would fail if someone changed logger.warning(...) to print(...).
    parsed = json.loads(result.stdout)
    assert "passed" in parsed
    assert "before_score" in parsed
    assert "after_score" in parsed


def test_schema_migration_warning_goes_to_stderr(fixtures_exist: None) -> None:
    """Model schema migration notice must appear on stderr, NOT stdout."""
    result = subprocess.run(
        [
            sys.executable, "-m", "faultray", "gate", "terraform-plan",
            str(SAMPLE_PLAN),
            "--model", str(DEMO_MODEL),
            "--json",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    # The schema warning should NOT appear in stdout under --json mode.
    assert "Model uses schema" not in result.stdout, (
        f"schema warning leaked into stdout:\n{result.stdout[:300]}"
    )
