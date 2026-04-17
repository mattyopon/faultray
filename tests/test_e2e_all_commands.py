# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""E2E: Every CLI command --help exits 0 and produces output.

Tests ALL CLI commands with ``--help`` to ensure nothing is broken at
import level.  Zero mocks -- every invocation is a real subprocess call.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

_PYTHON = "python3"
_REPO = str(Path(__file__).parent.parent)
_TIMEOUT = 15

# ---------------------------------------------------------------------------
# Complete command list extracted from ``faultray --help``
# ---------------------------------------------------------------------------

ALL_COMMANDS: list[str] = [
    # Getting Started
    "demo",
    "start",
    "quickstart",
    "init",
    # Discovery & Import
    "scan",
    "load",
    "show",
    "tf-check",
    "tf-import",
    "tf-plan",
    "import-metrics",
    "calibrate",
    # GAS Scanner
    "gas-scan",
    # Simulation
    "simulate",
    "dynamic",
    "monte-carlo",
    "ops-sim",
    "whatif",
    "capacity",
    "chaos-monkey",
    "fuzz",
    "gameday",
    "dr",
    "bayesian",
    "markov",
    # Compliance & Governance
    "dora",
    "compliance",
    "compliance-monitor",
    "governance",
    "evidence",
    "contract-validate",
    "contract-generate",
    "contract-diff",
    "sre-maturity",
    # Analysis & Reports
    "analyze",
    "report",
    "cost",
    "cost-report",
    "cost-optimize",
    "cost-attribution",
    "financial",
    "risk",
    "heatmap",
    "benchmark",
    "anomaly",
    "antipatterns",
    "fmea",
    "predict",
    "evaluate",
    "executive",
    "score-explain",
    # IaC
    "iac-export",
    "iac-gen",
    "export",
    "fix",
    "auto-fix",
    # Security
    "security",
    "attack-surface",
    "supply-chain",
    "feed-update",
    "feed-list",
    "feed-sources",
    "feed-clear",
    # Monitoring & History
    "apm",
    "daemon",
    "history",
    "timeline",
    "drift",
    "diff",
    "topo-diff",
    "compare-envs",
    "env-compare",
    "canary-compare",
    "ab-test",
    "velocity",
    "leaderboard",
    "dora-report",
    # AI Agent
    "agent",
    "nl",
    "ask",
    "advise",
    "twin",
    # SLA
    "sla-validate",
    "sla-prove",
    "sla-improve",
    "slo-budget",
    "budget",
    # Web & Config
    "serve",
    "config",
    "plugin",
    "template",
    "team",
    "gate",
    # Utilities
    "graph-export",
    "deps",
    "dna",
    "genome",
    "carbon",
    "marketplace",
    "replay",
    "replay-timeline",
    "calendar",
    "runbook",
    "postmortem-generate",
    "postmortem-list",
    "postmortem-summary",
    "git-track",
    "war-room",
    "badge",
    "score-custom",
    "correlate",
    "autoscale",
    "backtest",
    "plan",
    "overmind",
    "resilience-hub",
    "optimize",
    "remediate",
]


def _run(
    args: list[str], timeout: int = _TIMEOUT
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [_PYTHON, "-m", "faultray"] + args,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=_REPO,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAllCommandsHelp:
    """Every CLI command must accept --help, exit 0, and produce output."""

    @pytest.mark.parametrize("cmd", ALL_COMMANDS)
    def test_help_does_not_crash(self, cmd: str) -> None:
        r = _run([cmd, "--help"], timeout=_TIMEOUT)
        assert r.returncode == 0, (
            f"{cmd} --help failed (rc={r.returncode}): "
            f"{r.stderr[:300]}"
        )
        combined = r.stdout + r.stderr
        assert len(combined.strip()) > 10, (
            f"{cmd} --help produced no meaningful output"
        )

    @pytest.mark.parametrize("cmd", ALL_COMMANDS)
    def test_help_no_traceback(self, cmd: str) -> None:
        """--help must never produce a Python traceback."""
        r = _run([cmd, "--help"], timeout=_TIMEOUT)
        for stream in (r.stdout, r.stderr):
            assert "Traceback (most recent call last)" not in stream, (
                f"{cmd} --help produced a traceback:\n{stream[:500]}"
            )


class TestTopLevelHelp:
    """Top-level CLI entry points."""

    def test_main_help(self) -> None:
        r = _run(["--help"])
        assert r.returncode == 0
        assert "Usage" in r.stdout

    def test_version(self) -> None:
        r = _run(["--version"])
        assert r.returncode == 0
        assert "FaultRay" in r.stdout

    def test_unknown_command_fails(self) -> None:
        r = _run(["this-command-does-not-exist"])
        assert r.returncode != 0
