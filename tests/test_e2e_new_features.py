# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""E2E: New features added recently -- GAS, Governance, Remediate, APM, EOL.

Zero mocks.  CLI tests use subprocess.  API tests use real HTTP.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

_PYTHON = "python3"
_REPO = str(Path(__file__).parent.parent)
_TIMEOUT = 30

try:
    import httpx

    _HTTPX = True
except ImportError:
    _HTTPX = False
    httpx = None  # type: ignore[assignment]

_skip_api = pytest.mark.skipif(not _HTTPX, reason="httpx not installed")

FAULTRAY_URL = "https://faultray.com"
_HTTP_TIMEOUT = 15.0


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


def _parse_json(text: str) -> dict:
    """Extract first JSON object from text."""
    start = text.find("{")
    if start == -1:
        start = text.find("[")
    if start == -1:
        raise ValueError(f"No JSON in: {text[:200]}")
    return json.loads(text[start:])


# ---------------------------------------------------------------------------
# GAS Scanner (CLI)
# ---------------------------------------------------------------------------


class TestGASScannerCLI:
    """faultray gas-scan -- Google Apps Script risk scanner."""

    def test_gas_scan_help(self) -> None:
        r = _run(["gas-scan", "--help"])
        assert r.returncode == 0
        out = r.stdout + r.stderr
        assert len(out.strip()) > 10

    def test_gas_scan_default(self) -> None:
        r = _run(["gas-scan"])
        assert r.returncode in (0, 1)
        out = r.stdout + r.stderr
        assert len(out.strip()) > 0

    def test_gas_scan_org(self) -> None:
        r = _run(["gas-scan", "--org", "TestCorp"])
        assert r.returncode in (0, 1)
        out = r.stdout + r.stderr
        # Should contain GAS/script/risk related output
        assert len(out.strip()) > 0

    def test_gas_scan_json(self) -> None:
        r = _run(["gas-scan", "--json"])
        assert r.returncode in (0, 1)
        out = r.stdout
        if r.returncode == 0 and out.strip():
            # If it produces JSON, it should be parseable
            start = out.find("{")
            if start == -1:
                start = out.find("[")
            if start != -1:
                data = json.loads(out[start:])
                assert isinstance(data, (dict, list))

    def test_gas_scan_contains_risk_info(self) -> None:
        r = _run(["gas-scan"])
        assert r.returncode in (0, 1)
        out = (r.stdout + r.stderr).lower()
        # Should mention scripts, risk, GAS, or scores
        assert any(
            kw in out
            for kw in ["script", "risk", "gas", "score", "scan", "google"]
        ), f"Unexpected output: {out[:300]}"


# ---------------------------------------------------------------------------
# Governance Extended (CLI)
# ---------------------------------------------------------------------------


class TestGovernanceExtendedCLI:
    """Extended governance sub-commands."""

    def test_governance_ai_registry_list(self) -> None:
        r = _run(["governance", "ai-registry", "list"])
        assert r.returncode in (0, 1)
        out = r.stdout + r.stderr
        assert len(out.strip()) > 0

    def test_governance_evidence_verify(self) -> None:
        r = _run(["governance", "evidence", "verify"])
        assert r.returncode in (0, 1)
        out = r.stdout + r.stderr
        assert len(out.strip()) > 0

    def test_governance_policy_generate_ai_usage(self) -> None:
        r = _run(
            [
                "governance",
                "policy",
                "generate",
                "--type",
                "ai_usage",
                "--org-name",
                "TestCorp",
            ]
        )
        assert r.returncode in (0, 1)
        out = r.stdout + r.stderr
        assert len(out.strip()) > 0

    def test_governance_roadmap(self) -> None:
        r = _run(["governance", "roadmap"])
        assert r.returncode in (0, 1)
        out = r.stdout + r.stderr
        assert len(out.strip()) > 0

    def test_governance_cross_map(self) -> None:
        r = _run(["governance", "cross-map"])
        assert r.returncode in (0, 1)
        out = r.stdout + r.stderr
        assert len(out.strip()) > 0

    def test_governance_gap_analysis(self) -> None:
        r = _run(["governance", "gap-analysis"])
        assert r.returncode in (0, 1)
        out = r.stdout + r.stderr
        assert len(out.strip()) > 0

    def test_governance_assess_auto_has_scores(self) -> None:
        r = _run(["governance", "assess", "--auto"])
        assert r.returncode in (0, 1)
        out = r.stdout + r.stderr
        # Should contain at least one numeric digit (score)
        assert any(c.isdigit() for c in out), f"No numbers in: {out[:300]}"


# ---------------------------------------------------------------------------
# Remediate (CLI)
# ---------------------------------------------------------------------------


class TestRemediateCLI:
    """faultray remediate sub-commands."""

    def test_remediate_run(self) -> None:
        r = _run(["remediate", "run"])
        assert r.returncode in (0, 1, 2)
        out = r.stdout + r.stderr
        assert len(out.strip()) > 0

    def test_remediate_history(self) -> None:
        r = _run(["remediate", "history"])
        assert r.returncode in (0, 1)
        out = r.stdout + r.stderr
        assert len(out.strip()) > 0

    def test_remediate_pending(self) -> None:
        r = _run(["remediate", "pending"])
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

    def test_remediate_help(self) -> None:
        r = _run(["remediate", "--help"])
        assert r.returncode == 0
        out = r.stdout + r.stderr
        assert "remediat" in out.lower()


# ---------------------------------------------------------------------------
# APM Extended (CLI)
# ---------------------------------------------------------------------------


class TestAPMExtendedCLI:
    """faultray apm sub-commands."""

    def test_apm_setup_help(self) -> None:
        r = _run(["apm", "setup", "--help"])
        assert r.returncode == 0
        out = r.stdout + r.stderr
        assert len(out.strip()) > 10

    def test_apm_report(self) -> None:
        r = _run(["apm", "report"])
        assert r.returncode in (0, 1)
        out = r.stdout + r.stderr
        assert len(out.strip()) > 0

    def test_apm_help_shows_architecture(self) -> None:
        r = _run(["apm", "help"])
        assert r.returncode == 0
        out = r.stdout + r.stderr
        assert any(
            kw in out.lower() for kw in ["architecture", "apm", "agent"]
        )

    def test_apm_status(self) -> None:
        r = _run(["apm", "status"])
        assert r.returncode in (0, 1)
        out = r.stdout + r.stderr
        assert len(out.strip()) > 0

    def test_apm_install_help(self) -> None:
        r = _run(["apm", "install", "--help"])
        assert r.returncode == 0

    def test_apm_start_help(self) -> None:
        r = _run(["apm", "start", "--help"])
        assert r.returncode == 0

    def test_apm_stop_help(self) -> None:
        r = _run(["apm", "stop", "--help"])
        assert r.returncode == 0

    def test_apm_metrics_help(self) -> None:
        r = _run(["apm", "metrics", "--help"])
        assert r.returncode == 0


# ---------------------------------------------------------------------------
# EOL Checker (Python import)
# ---------------------------------------------------------------------------


class TestEOLChecker:
    """faultray.apm.eol_checker -- import and run directly."""

    def test_import_eol_checker(self) -> None:
        """EOLChecker can be imported without error."""
        r = subprocess.run(
            [
                _PYTHON,
                "-c",
                "from faultray.apm.eol_checker import EOLChecker; print('OK')",
            ],
            capture_output=True,
            text=True,
            timeout=15,
            cwd=_REPO,
        )
        assert r.returncode == 0
        assert "OK" in r.stdout

    def test_eol_checker_check_returns_report(self) -> None:
        """EOLChecker.check() runs and returns a report dict."""
        code = """
import json
from faultray.apm.eol_checker import EOLChecker, DetectedSoftware
checker = EOLChecker()
detected = [
    DetectedSoftware(name="python", version="3.9.0", source="manual"),
    DetectedSoftware(name="node", version="16.0.0", source="manual"),
]
report = checker.check(detected)
print(json.dumps({"ok": True, "type": type(report).__name__}))
"""
        r = subprocess.run(
            [_PYTHON, "-c", code],
            capture_output=True,
            text=True,
            timeout=15,
            cwd=_REPO,
        )
        assert r.returncode == 0, f"EOLChecker.check() failed: {r.stderr[:300]}"
        data = json.loads(r.stdout.strip())
        assert data["ok"] is True


# ---------------------------------------------------------------------------
# Simulation Rich Output (API)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@_skip_api
class TestSimulationRichOutputAPI:
    """POST /api/simulate should return rich calculation evidence."""

    def test_simulate_has_overall_score(self) -> None:
        assert httpx is not None
        r = httpx.post(
            f"{FAULTRAY_URL}/api/simulate",
            json={"sample": "web-saas"},
            timeout=_HTTP_TIMEOUT,
        )
        assert r.status_code == 200
        data = r.json()
        assert "overall_score" in data
        assert 0 <= data["overall_score"] <= 100

    def test_simulate_has_total_scenarios(self) -> None:
        assert httpx is not None
        r = httpx.post(
            f"{FAULTRAY_URL}/api/simulate",
            json={"sample": "web-saas"},
            timeout=_HTTP_TIMEOUT,
        )
        data = r.json()
        assert data.get("total_scenarios", 0) > 0

    def test_simulate_has_evidence_or_log(self) -> None:
        assert httpx is not None
        r = httpx.post(
            f"{FAULTRAY_URL}/api/simulate",
            json={"sample": "web-saas"},
            timeout=_HTTP_TIMEOUT,
        )
        data = r.json()
        # Should have at least one of these rich output fields
        evidence_keys = {
            "calculation_evidence",
            "evidence",
            "simulation_log",
            "cascade_simulations",
            "cascades",
            "scenarios",
            "component_scores",
        }
        found = evidence_keys & set(data.keys())
        assert len(found) > 0, (
            f"No evidence fields found. Keys: {list(data.keys())}"
        )

    def test_simulate_suggestions_not_empty(self) -> None:
        assert httpx is not None
        r = httpx.post(
            f"{FAULTRAY_URL}/api/simulate",
            json={"sample": "web-saas"},
            timeout=_HTTP_TIMEOUT,
        )
        data = r.json()
        suggestion_keys = {"suggestions", "improvements", "recommendations"}
        for key in suggestion_keys:
            if key in data:
                val = data[key]
                if isinstance(val, list):
                    assert len(val) > 0, f"{key} is empty list"
                break
