"""Regression tests for ``faultray financial`` text/HTML render formatting.

Specifically locks in the 1-decimal ROI format. See Issue #72: before
the fix, the Rich text panel showed ``Overall ROI: 0x`` while the same
run with ``--json`` emitted ``"roi": 0.4``. The integer-floored text
hid the real ROI from users skimming stdout.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
# Committed fixture known to produce a non-zero ROI path (1 DB SPOF +
# 2 app_servers dependent on it → "Add replica" fix with 0.4x ROI at
# $10K/hour default pricing). This is the k8s topology captured during
# Phase 0 scan validation, redistributed as a committed fixture so CI
# doesn't depend on scratch files under /tmp or on
# ``faultray-model.json`` (which is gitignored and may be absent or
# minimal in CI).
DEMO_MODEL = REPO_ROOT / "tests" / "fixtures" / "demo-topology.json"


def _run_financial(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "faultray", "financial", *args],
        capture_output=True,
        text=True,
        timeout=60,
    )


@pytest.fixture
def demo_model() -> Path:
    assert DEMO_MODEL.exists(), (
        f"committed fixture missing: {DEMO_MODEL} — this should ship with the repo"
    )
    return DEMO_MODEL


def test_roi_rendered_with_one_decimal_in_text_output(demo_model: Path) -> None:
    """Text output must NOT floor ROI to integer (regression for Issue #72)."""
    result = _run_financial(str(demo_model), "--cost-per-hour", "10000")
    assert result.returncode == 0, (
        f"financial command failed: {result.stdout[-400:]!r} / {result.stderr[-400:]!r}"
    )
    # The panel must contain an "Overall ROI: <N>.<d>x" line — explicit decimal.
    import re
    match = re.search(r"Overall ROI:\s*([\d.]+)x", result.stdout)
    assert match is not None, (
        f"'Overall ROI: <n>x' line not found.\n{result.stdout[-600:]}"
    )
    roi_str = match.group(1)
    assert "." in roi_str, (
        f"ROI rendered without decimal point: {roi_str!r}. "
        f"Expected 1-decimal format like '0.4x', got '{roi_str}x'."
    )


def test_per_fix_roi_also_has_one_decimal(demo_model: Path) -> None:
    """Each recommended fix's ROI must also show the decimal, not just the total."""
    result = _run_financial(str(demo_model), "--cost-per-hour", "10000")
    if "Recommended Fixes" not in result.stdout:
        pytest.skip("sample model has no recommended fixes to check")
    import re
    # Per-fix ROI pattern: "(<N>.<d>x ROI)"
    roi_tokens = re.findall(r"\(([\d.]+)x ROI\)", result.stdout)
    assert roi_tokens, f"no per-fix ROI tokens found.\n{result.stdout[-600:]}"
    for t in roi_tokens:
        assert "." in t, (
            f"per-fix ROI rendered without decimal: {t!r}. All tokens: {roi_tokens}"
        )


def test_json_roi_unchanged(demo_model: Path) -> None:
    """The --json payload's `roi` field is the canonical source; must keep float."""
    result = _run_financial(str(demo_model), "--cost-per-hour", "10000", "--json")
    assert result.returncode == 0
    # Strip the "FaultRay v... [Free Tier...]" banner; console.print_json emits the
    # JSON body after it.
    idx = result.stdout.index("{")
    payload = json.loads(result.stdout[idx:])
    assert "roi" in payload
    assert isinstance(payload["roi"], (int, float))
    # Matches the rich text format: both should agree.
    assert payload["roi"] >= 0.0
