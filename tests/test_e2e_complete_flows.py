# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""E2E: Complete multi-step user journey tests.

Six full user flows tested end-to-end with zero mocks.
CLI tests use subprocess.  API tests use real HTTP to https://faultray.com.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

import pytest

_PYTHON = "python3"
_REPO = str(Path(__file__).parent.parent)
_CLI_TIMEOUT = 90

try:
    import httpx

    _HTTPX = True
except ImportError:
    _HTTPX = False
    httpx = None  # type: ignore[assignment]

_skip_api = pytest.mark.skipif(not _HTTPX, reason="httpx not installed")

FAULTRAY_URL = "https://faultray.com"
_HTTP_TIMEOUT = 15.0

SAMPLE_YAML = """\
schema_version: "3.0"
components:
  - id: web
    name: Web Server
    type: app_server
    replicas: 2
  - id: api
    name: API Service
    type: app_server
    replicas: 3
  - id: db
    name: Database
    type: database
    replicas: 1
  - id: cache
    name: Redis Cache
    type: cache
    replicas: 1
dependencies:
  - source: web
    target: api
    type: requires
  - source: api
    target: db
    type: requires
  - source: api
    target: cache
    type: optional
"""


def _run(
    args: list[str], timeout: int = _CLI_TIMEOUT
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [_PYTHON, "-m", "faultray"] + args,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=_REPO,
    )


def _make_yaml() -> str:
    tmp = tempfile.NamedTemporaryFile(suffix=".yaml", delete=False, mode="w")
    tmp.write(SAMPLE_YAML)
    tmp.flush()
    tmp.close()
    return tmp.name


def _parse_json(text: str) -> dict:
    start = text.find("{")
    if start == -1:
        raise ValueError(f"No JSON object found in: {text[:200]}")
    return json.loads(text[start:])


# ---------------------------------------------------------------------------
# Flow 1: New User Onboarding -> First Simulation -> Results (API)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@_skip_api
class TestFlow1OnboardingSimulation:
    """Flow 1: Onboarding page -> simulate -> verify results -> remediation."""

    def test_step1_onboarding_page(self) -> None:
        assert httpx is not None
        r = httpx.get(
            f"{FAULTRAY_URL}/onboarding",
            timeout=_HTTP_TIMEOUT,
            follow_redirects=True,
        )
        assert r.status_code < 500

    def test_step2_simulate_returns_score(self) -> None:
        assert httpx is not None
        r = httpx.post(
            f"{FAULTRAY_URL}/api/simulate",
            json={"sample": "web-saas"},
            timeout=_HTTP_TIMEOUT,
        )
        assert r.status_code == 200
        data = r.json()
        assert "overall_score" in data

    def test_step3_score_between_0_and_100(self) -> None:
        assert httpx is not None
        r = httpx.post(
            f"{FAULTRAY_URL}/api/simulate",
            json={"sample": "web-saas"},
            timeout=_HTTP_TIMEOUT,
        )
        score = r.json()["overall_score"]
        assert 0 <= score <= 100

    def test_step4_response_has_suggestions(self) -> None:
        assert httpx is not None
        r = httpx.post(
            f"{FAULTRAY_URL}/api/simulate",
            json={"sample": "web-saas"},
            timeout=_HTTP_TIMEOUT,
        )
        data = r.json()
        suggestion_keys = {"suggestions", "improvements", "recommendations"}
        found = suggestion_keys & set(data.keys())
        assert len(found) > 0, f"No suggestion field. Keys: {list(data.keys())}"

    def test_step5_response_has_cascades(self) -> None:
        assert httpx is not None
        r = httpx.post(
            f"{FAULTRAY_URL}/api/simulate",
            json={"sample": "web-saas"},
            timeout=_HTTP_TIMEOUT,
        )
        data = r.json()
        cascade_keys = {"cascade_simulations", "cascades", "scenarios"}
        found = cascade_keys & set(data.keys())
        assert len(found) > 0, f"No cascade field. Keys: {list(data.keys())}"

    def test_step6_response_has_evidence(self) -> None:
        assert httpx is not None
        r = httpx.post(
            f"{FAULTRAY_URL}/api/simulate",
            json={"sample": "web-saas"},
            timeout=_HTTP_TIMEOUT,
        )
        data = r.json()
        evidence_keys = {
            "calculation_evidence",
            "evidence",
            "simulation_log",
            "component_scores",
            "total_scenarios",
        }
        found = evidence_keys & set(data.keys())
        assert len(found) > 0

    def test_step7_remediation_page(self) -> None:
        assert httpx is not None
        r = httpx.get(
            f"{FAULTRAY_URL}/remediation",
            timeout=_HTTP_TIMEOUT,
            follow_redirects=True,
        )
        assert r.status_code < 500


# ---------------------------------------------------------------------------
# Flow 2: GAS Scan -> People Risk (CLI + Web)
# ---------------------------------------------------------------------------


class TestFlow2GASScanPeopleRisk:
    """Flow 2: GAS scan -> people risk page."""

    def test_step1_gas_scan_runs(self) -> None:
        r = _run(["gas-scan"])
        assert r.returncode in (0, 1)
        out = (r.stdout + r.stderr).lower()
        assert any(kw in out for kw in ["script", "risk", "gas", "scan", "google"])

    def test_step2_gas_scan_has_output(self) -> None:
        r = _run(["gas-scan"])
        out = r.stdout + r.stderr
        assert len(out.strip()) > 0

    @pytest.mark.e2e
    @_skip_api
    def test_step3_people_risk_page(self) -> None:
        assert httpx is not None
        r = httpx.get(
            f"{FAULTRAY_URL}/people-risk",
            timeout=_HTTP_TIMEOUT,
            follow_redirects=True,
        )
        assert r.status_code < 500


# ---------------------------------------------------------------------------
# Flow 3: Governance -> DORA -> Audit Report (CLI + API + Web)
# ---------------------------------------------------------------------------


class TestFlow3GovernanceDORAAudit:
    """Flow 3: Governance assess -> DORA API -> audit report page."""

    def test_step1_governance_assess(self) -> None:
        r = _run(["governance", "assess", "--auto"])
        assert r.returncode in (0, 1)
        out = r.stdout + r.stderr
        assert any(c.isdigit() for c in out), "Expected numeric score"

    @pytest.mark.e2e
    @_skip_api
    def test_step2_governance_dora_api(self) -> None:
        assert httpx is not None
        r = httpx.get(
            f"{FAULTRAY_URL}/api/governance?action=dora",
            timeout=_HTTP_TIMEOUT,
        )
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict)
        assert len(data) > 0

    @pytest.mark.e2e
    @_skip_api
    def test_step3_ai_governance_api(self) -> None:
        assert httpx is not None
        r = httpx.get(
            f"{FAULTRAY_URL}/api/governance?action=ai-governance",
            timeout=_HTTP_TIMEOUT,
        )
        assert r.status_code == 200
        data = r.json()
        assert "maturity_level" in data

    @pytest.mark.e2e
    @_skip_api
    def test_step4_dora_page(self) -> None:
        assert httpx is not None
        r = httpx.get(
            f"{FAULTRAY_URL}/dora",
            timeout=_HTTP_TIMEOUT,
            follow_redirects=True,
        )
        assert r.status_code < 500

    @pytest.mark.e2e
    @_skip_api
    def test_step5_governance_page(self) -> None:
        assert httpx is not None
        r = httpx.get(
            f"{FAULTRAY_URL}/governance",
            timeout=_HTTP_TIMEOUT,
            follow_redirects=True,
        )
        assert r.status_code < 500

    @pytest.mark.e2e
    @_skip_api
    def test_step6_audit_report_page(self) -> None:
        assert httpx is not None
        r = httpx.get(
            f"{FAULTRAY_URL}/audit-report",
            timeout=_HTTP_TIMEOUT,
            follow_redirects=True,
        )
        assert r.status_code < 500


# ---------------------------------------------------------------------------
# Flow 4: Full Compliance Pipeline (API)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@_skip_api
class TestFlow4CompliancePipeline:
    """Flow 4: simulate -> DORA -> SLA -> report -> FMEA."""

    def test_step1_simulate(self) -> None:
        assert httpx is not None
        r = httpx.post(
            f"{FAULTRAY_URL}/api/simulate",
            json={"sample": "web-saas"},
            timeout=_HTTP_TIMEOUT,
        )
        assert r.status_code == 200
        data = r.json()
        assert "overall_score" in data

    def test_step2_dora_compliance(self) -> None:
        assert httpx is not None
        r = httpx.get(
            f"{FAULTRAY_URL}/api/compliance?action=dora",
            timeout=_HTTP_TIMEOUT,
        )
        assert r.status_code == 200
        data = r.json()
        assert "overall_score" in data

    def test_step3_sla_governance(self) -> None:
        assert httpx is not None
        r = httpx.get(
            f"{FAULTRAY_URL}/api/governance?action=sla",
            timeout=_HTTP_TIMEOUT,
        )
        assert r.status_code == 200
        data = r.json()
        assert "sla_target" in data

    def test_step4_executive_report(self) -> None:
        assert httpx is not None
        r = httpx.get(
            f"{FAULTRAY_URL}/api/reports?action=report",
            timeout=_HTTP_TIMEOUT,
        )
        assert r.status_code == 200
        data = r.json()
        assert "executive_summary" in data

    def test_step5_fmea(self) -> None:
        assert httpx is not None
        r = httpx.get(
            f"{FAULTRAY_URL}/api/risk?action=fmea",
            timeout=_HTTP_TIMEOUT,
        )
        assert r.status_code == 200
        data = r.json()
        assert "failure_modes" in data

    def test_step6_all_responses_are_json(self) -> None:
        assert httpx is not None
        urls = [
            f"{FAULTRAY_URL}/api/compliance?action=dora",
            f"{FAULTRAY_URL}/api/governance?action=sla",
            f"{FAULTRAY_URL}/api/reports?action=report",
            f"{FAULTRAY_URL}/api/risk?action=fmea",
        ]
        for url in urls:
            r = httpx.get(url, timeout=_HTTP_TIMEOUT)
            assert r.status_code == 200, f"{url} returned {r.status_code}"
            ct = r.headers.get("content-type", "")
            assert "application/json" in ct, f"{url} content-type: {ct}"


# ---------------------------------------------------------------------------
# Flow 5: APM -> Monitor -> Alerts (API + Web)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@_skip_api
class TestFlow5APMMonitorAlerts:
    """Flow 5: APM agents -> stats -> alerts -> pages."""

    def test_step1_apm_agents(self) -> None:
        assert httpx is not None
        r = httpx.get(f"{FAULTRAY_URL}/api/apm/agents", timeout=_HTTP_TIMEOUT)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_step2_apm_stats(self) -> None:
        assert httpx is not None
        r = httpx.get(f"{FAULTRAY_URL}/api/apm/stats", timeout=_HTTP_TIMEOUT)
        assert r.status_code == 200
        data = r.json()
        assert "total_agents" in data

    def test_step3_apm_alerts(self) -> None:
        assert httpx is not None
        r = httpx.get(f"{FAULTRAY_URL}/api/apm/alerts", timeout=_HTTP_TIMEOUT)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_step4_apm_page(self) -> None:
        assert httpx is not None
        r = httpx.get(
            f"{FAULTRAY_URL}/apm",
            timeout=_HTTP_TIMEOUT,
            follow_redirects=True,
        )
        assert r.status_code < 500

    def test_step5_traffic_light_page(self) -> None:
        assert httpx is not None
        r = httpx.get(
            f"{FAULTRAY_URL}/traffic-light",
            timeout=_HTTP_TIMEOUT,
            follow_redirects=True,
        )
        assert r.status_code < 500


# ---------------------------------------------------------------------------
# Flow 6: IaC -> Remediation -> Optimization (Web)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@_skip_api
class TestFlow6IaCRemediationOptimization:
    """Flow 6: IaC page -> remediation -> optimize -> IPO readiness."""

    def test_step1_iac_page(self) -> None:
        assert httpx is not None
        r = httpx.get(
            f"{FAULTRAY_URL}/iac",
            timeout=_HTTP_TIMEOUT,
            follow_redirects=True,
        )
        assert r.status_code < 500

    def test_step2_remediation_page(self) -> None:
        assert httpx is not None
        r = httpx.get(
            f"{FAULTRAY_URL}/remediation",
            timeout=_HTTP_TIMEOUT,
            follow_redirects=True,
        )
        assert r.status_code < 500

    def test_step3_optimize_page(self) -> None:
        assert httpx is not None
        r = httpx.get(
            f"{FAULTRAY_URL}/optimize",
            timeout=_HTTP_TIMEOUT,
            follow_redirects=True,
        )
        assert r.status_code < 500

    def test_step4_ipo_readiness_page(self) -> None:
        assert httpx is not None
        r = httpx.get(
            f"{FAULTRAY_URL}/ipo-readiness",
            timeout=_HTTP_TIMEOUT,
            follow_redirects=True,
        )
        assert r.status_code < 500


# ---------------------------------------------------------------------------
# Flow 7: Full CLI Pipeline (load -> simulate -> financial -> badge -> gov)
# ---------------------------------------------------------------------------


class TestFlow7FullCLIPipeline:
    """Flow 7: Complete CLI pipeline with real subprocess calls."""

    def test_step1_load(self) -> None:
        yaml_path = _make_yaml()
        try:
            r = _run(["load", yaml_path])
            assert r.returncode == 0
            out = r.stdout + r.stderr
            assert "Resilience Score" in out or "score" in out.lower()
        finally:
            Path(yaml_path).unlink(missing_ok=True)

    def test_step2_simulate(self) -> None:
        yaml_path = _make_yaml()
        try:
            _run(["load", yaml_path])
            r = _run(["simulate"])
            assert r.returncode == 0
            out = r.stdout + r.stderr
            assert "score" in out.lower() or "resilience" in out.lower()
        finally:
            Path(yaml_path).unlink(missing_ok=True)

    def test_step3_simulate_json_score_positive(self) -> None:
        yaml_path = _make_yaml()
        try:
            _run(["load", yaml_path])
            r = _run(["simulate", "--json"])
            assert r.returncode == 0
            data = _parse_json(r.stdout)
            score = data.get("overall_score") or data.get("resilience_score", 0)
            assert isinstance(score, (int, float))
            assert score > 0
        finally:
            Path(yaml_path).unlink(missing_ok=True)

    def test_step4_financial(self) -> None:
        yaml_path = _make_yaml()
        try:
            r = _run(["financial", yaml_path])
            assert r.returncode == 0
            out = r.stdout + r.stderr
            assert "Financial" in out or "Annual" in out or "Impact" in out
        finally:
            Path(yaml_path).unlink(missing_ok=True)

    def test_step5_badge(self) -> None:
        yaml_path = _make_yaml()
        try:
            r = _run(["badge", yaml_path])
            assert r.returncode == 0
            assert "shields.io" in r.stdout or "img.shields.io" in r.stdout
        finally:
            Path(yaml_path).unlink(missing_ok=True)

    def test_step6_governance(self) -> None:
        yaml_path = _make_yaml()
        try:
            r = _run(["governance", "assess", "--auto", "--yaml", yaml_path])
            assert r.returncode in (0, 1)
            out = r.stdout + r.stderr
            assert len(out.strip()) > 0
        finally:
            Path(yaml_path).unlink(missing_ok=True)

    def test_step7_compliance_monitor(self) -> None:
        yaml_path = _make_yaml()
        try:
            r = _run(["compliance-monitor", yaml_path, "--framework", "dora"])
            assert r.returncode == 0
            out = r.stdout + r.stderr
            assert "DORA" in out or "Compliance" in out
        finally:
            Path(yaml_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Flow 8: Cross-sample comparison (API)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@_skip_api
class TestFlow8CrossSampleComparison:
    """Flow 8: Compare simulation results across different samples."""

    def test_web_saas_and_microservices_both_score(self) -> None:
        assert httpx is not None
        r1 = httpx.post(
            f"{FAULTRAY_URL}/api/simulate",
            json={"sample": "web-saas"},
            timeout=_HTTP_TIMEOUT,
        )
        r2 = httpx.post(
            f"{FAULTRAY_URL}/api/simulate",
            json={"sample": "microservices"},
            timeout=_HTTP_TIMEOUT,
        )
        assert r1.status_code == 200
        assert r2.status_code == 200
        s1 = r1.json()["overall_score"]
        s2 = r2.json()["overall_score"]
        assert 0 <= s1 <= 100
        assert 0 <= s2 <= 100

    def test_same_sample_consistent_range(self) -> None:
        """Two runs of the same sample should produce scores in the same range."""
        assert httpx is not None
        scores = []
        for _ in range(2):
            r = httpx.post(
                f"{FAULTRAY_URL}/api/simulate",
                json={"sample": "web-saas"},
                timeout=_HTTP_TIMEOUT,
            )
            assert r.status_code == 200
            scores.append(r.json()["overall_score"])
        # Both should be in the same ballpark (within 20 points)
        assert abs(scores[0] - scores[1]) < 20, (
            f"Score variance too high: {scores}"
        )
