"""Regression tests for the Component Financial Impact Rich Table layout.

See Issue #73: before this fix the table used fixed column widths summing
to >80 cols, so Rich auto-shrank each cell to 4-5 chars and rendered
``$/Hour`` as ``$/…``, ``$10,140`` as ``$10,1…``, etc. After the fix,
letting Rich size to content + ``overflow="fold"`` on free-form cells
restores full data at normal terminal widths.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
# Committed fixture with 3 components + 2 deps + a DB SPOF so the
# financial report renders the full Component Table in CI — not just
# an empty panel when ``faultray-model.json`` is minimal/absent. The
# fixture file ships in PR #76 (``tests/fixtures/demo-topology.json``);
# this PR depends on that file being on main.
DEMO_MODEL = REPO_ROOT / "tests" / "fixtures" / "demo-topology.json"


@pytest.fixture
def demo_model() -> Path:
    assert DEMO_MODEL.exists(), (
        f"committed fixture missing: {DEMO_MODEL}"
    )
    return DEMO_MODEL


def _run_financial_at_width(
    model: Path, cols: str
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["COLUMNS"] = cols
    env.setdefault("TERM", "xterm-256color")
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "faultray",
            "financial",
            str(model),
            "--cost-per-hour",
            "10000",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )


def test_headers_render_in_full_at_wide_terminal(demo_model: Path) -> None:
    """At 120 cols, the full header labels must be visible (no ellipsis)."""
    result = _run_financial_at_width(demo_model, "120")
    assert result.returncode == 0, result.stderr[-400:]
    for label in ("Avail %", "Downtime/yr", "$/Hour", "Loss/yr"):
        assert label in result.stdout, (
            f"header {label!r} truncated at 120 cols.\n"
            f"Tail: {result.stdout[-800:]}"
        )


def test_no_values_truncated_mid_digit_at_wide_terminal(demo_model: Path) -> None:
    """At 120 cols, numeric values must not end in ellipsis mid-number."""
    result = _run_financial_at_width(demo_model, "120")
    assert result.returncode == 0
    # The old bug produced lines like "$10,1…", "$1…" for the Loss column
    # (money truncated mid-digit after the thousand separator). Assert no
    # such pattern appears in the body.
    import re

    bad = re.findall(r"\$[\d,]+…", result.stdout)
    assert not bad, (
        f"money values truncated mid-digit: {bad!r}\n"
        f"Tail: {result.stdout[-800:]}"
    )


def test_table_renders_cleanly_at_narrow_terminal(demo_model: Path) -> None:
    """At 80 cols the table wraps instead of truncating; no traceback."""
    result = _run_financial_at_width(demo_model, "80")
    assert result.returncode == 0, result.stderr[-400:]
    # Table bottom-border char present.
    assert "└" in result.stdout
    # No stack traces.
    assert "Traceback" not in result.stdout
    assert "Traceback" not in result.stderr
