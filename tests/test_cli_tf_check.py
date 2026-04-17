"""CLI-level regression tests for ``faultray tf-check``.

Focused on the exit-code contract of ``--fail-on-regression``. The
documentation promises: "Exit with code 1 if resilience score decreases."
Phase 0 baseline validation surfaced a case where the gate silently passed
(exit 0) on a destructive-only plan whose Recommendation was ``"high risk"``
but whose ``score_delta`` stayed ``0.0`` (the simulation has no prior-state
model to diff against).

These tests lock the expanded gate contract: ``--fail-on-regression``
triggers on EITHER a negative score_delta OR a ``recommendation == "high risk"``.
Reproducer fixture: ``tests/fixtures/sample-tf-plan.json`` (added in PR #66).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PLAN = REPO_ROOT / "tests" / "fixtures" / "sample-tf-plan.json"


def _run_tf_check(*args: str) -> subprocess.CompletedProcess[str]:
    """Invoke the faultray CLI module directly; preserves its exit code."""
    return subprocess.run(
        [sys.executable, "-m", "faultray", "tf-check", *args],
        capture_output=True,
        text=True,
        timeout=60,
    )


@pytest.fixture
def plan_file() -> Path:
    assert SAMPLE_PLAN.exists(), f"sample plan fixture missing: {SAMPLE_PLAN}"
    return SAMPLE_PLAN


# ---------------------------------------------------------------------------
# Regression coverage for the Phase 0 finding
# ---------------------------------------------------------------------------


def test_fail_on_regression_fires_for_high_risk_destructive_plan(plan_file: Path) -> None:
    """``--fail-on-regression`` must exit 1 when the plan is ``high risk``.

    The committed ``sample-tf-plan.json`` contains an ``aws_db_instance.primary``
    delete (risk_level 10 → recommendation "high risk") but the simulation
    produces ``score_delta == 0.0`` because there's no prior model to diff.
    Before the fix, this returned exit 0; after the fix, it returns exit 1
    via the new recommendation-based gate.
    """
    result = _run_tf_check(str(plan_file), "--fail-on-regression")
    assert result.returncode == 1, (
        f"expected exit 1 on high-risk plan with --fail-on-regression, "
        f"got {result.returncode}\nstdout={result.stdout!r}\nstderr={result.stderr!r}"
    )
    # The gate should explain *why* it fired.
    assert "HIGH RISK CHANGE DETECTED" in result.stdout, (
        f"exit code OK but no explanation printed.\nstdout={result.stdout!r}"
    )


def test_fail_on_regression_still_exits_1_in_json_mode(plan_file: Path) -> None:
    """--fail-on-regression + --json must still exit 1 on high-risk."""
    result = _run_tf_check(str(plan_file), "--fail-on-regression", "--json")
    assert result.returncode == 1
    # JSON payload must still parse and report recommendation="high risk".
    # Strip the "FaultRay v... [Free Tier...]" banner line that the CLI
    # prefixes to stdout before the JSON body.
    json_blob = "\n".join(
        ln for ln in result.stdout.splitlines()
        if not ln.startswith("FaultRay v") and ln.strip()
    )
    # The console.print_json output can span multiple lines; find the JSON
    # object by locating the first "{" and parsing from there.
    idx = json_blob.index("{")
    payload = json.loads(json_blob[idx:])
    assert payload["recommendation"] == "high risk"
    # score_delta = 0 must NOT alone be enough to pass — the recommendation
    # layer is now what gates.
    assert payload["score_delta"] == 0.0


def test_no_flag_returns_0_even_on_high_risk(plan_file: Path) -> None:
    """Without --fail-on-regression, the command is purely informational.

    Even a high-risk recommendation must not flip the exit code: the flag is
    opt-in, and backwards-compat requires plain ``tf-check`` to stay exit 0.
    """
    result = _run_tf_check(str(plan_file))
    assert result.returncode == 0, (
        f"expected exit 0 (no flag), got {result.returncode}\n"
        f"stdout={result.stdout[-400:]!r}"
    )


def test_min_score_threshold_still_fires(plan_file: Path, tmp_path: Path) -> None:
    """--min-score is an independent gate and must continue to work.

    Using a threshold of 101 forces ``score_after (100.0) < min_score`` and
    should exit 1 regardless of --fail-on-regression.
    """
    result = _run_tf_check(str(plan_file), "--min-score", "101")
    assert result.returncode == 1
    assert "POLICY VIOLATION" in result.stdout
