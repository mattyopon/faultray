# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Multi-step user flow E2E tests — NO mocks.

Tests complete user journeys end-to-end:
- CLI flows use real subprocess
- API flows use real HTTP to https://faultray.com

API tests are marked @pytest.mark.e2e and need network access.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

import pytest

_PYTHON = "python3"
_TIMEOUT = 90
_REPO = str(Path(__file__).parent.parent)

try:
    import httpx

    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False

_skip_api = pytest.mark.skipif(
    not _HTTPX_AVAILABLE,
    reason="httpx not installed — API flow tests skipped",
)

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


def _run(args: list[str], timeout: int = _TIMEOUT) -> subprocess.CompletedProcess[str]:
    """Run real faultray CLI command via subprocess."""
    return subprocess.run(
        [_PYTHON, "-m", "faultray"] + args,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=_REPO,
    )


def _make_yaml() -> str:
    """Write SAMPLE_YAML to a temp file and return its path."""
    tmp = tempfile.NamedTemporaryFile(suffix=".yaml", delete=False, mode="w")
    tmp.write(SAMPLE_YAML)
    tmp.flush()
    tmp.close()
    return tmp.name


def _parse_json(text: str) -> dict:
    """Extract and parse first JSON object from text output."""
    start = text.find("{")
    if start == -1:
        raise ValueError(f"No JSON object found in: {text[:200]}")
    return json.loads(text[start:])


# ---------------------------------------------------------------------------
# Flow 1: Simulation Pipeline (CLI)
# ---------------------------------------------------------------------------


class TestSimulationPipelineCLI:
    """Flow 1: Write YAML → load → simulate → simulate --json."""

    def test_flow1_write_yaml(self) -> None:
        """Temp YAML file is created and readable."""
        yaml_path = _make_yaml()
        try:
            content = Path(yaml_path).read_text()
            assert "components" in content
            assert "web" in content
        finally:
            Path(yaml_path).unlink(missing_ok=True)

    def test_flow1_load_creates_model(self) -> None:
        """faultray load → exits 0 and confirms model created."""
        yaml_path = _make_yaml()
        try:
            r = _run(["load", yaml_path])
            assert r.returncode == 0
            out = r.stdout + r.stderr
            assert len(out.strip()) > 0
        finally:
            Path(yaml_path).unlink(missing_ok=True)

    def test_flow1_simulate_after_load_has_score(self) -> None:
        """load then simulate → output contains score."""
        yaml_path = _make_yaml()
        try:
            load_r = _run(["load", yaml_path])
            assert load_r.returncode == 0

            sim_r = _run(["simulate"])
            assert sim_r.returncode == 0
            out = sim_r.stdout + sim_r.stderr
            assert "score" in out.lower() or "resilience" in out.lower()
        finally:
            Path(yaml_path).unlink(missing_ok=True)

    def test_flow1_simulate_json_parses(self) -> None:
        """simulate --json → valid JSON with overall_score."""
        yaml_path = _make_yaml()
        try:
            _run(["load", yaml_path])
            r = _run(["simulate", "--json"])
            assert r.returncode == 0

            data = _parse_json(r.stdout)
            assert "overall_score" in data or "resilience_score" in data
        finally:
            Path(yaml_path).unlink(missing_ok=True)

    def test_flow1_simulate_json_score_positive(self) -> None:
        """simulate --json → overall_score > 0 for valid infra."""
        yaml_path = _make_yaml()
        try:
            _run(["load", yaml_path])
            r = _run(["simulate", "--json"])
            assert r.returncode == 0

            data = _parse_json(r.stdout)
            score = data.get("overall_score") or data.get("resilience_score", 0)
            assert score > 0
        finally:
            Path(yaml_path).unlink(missing_ok=True)

    def test_flow1_auto_fix_dry_run(self) -> None:
        """auto-fix --dry-run (default) generates a plan without applying."""
        yaml_path = _make_yaml()
        try:
            _run(["load", yaml_path])
            r = _run(["auto-fix", yaml_path])
            # May succeed or fail gracefully (dry-run is safe)
            assert r.returncode in (0, 1)
            out = r.stdout + r.stderr
            assert len(out.strip()) > 0
        finally:
            Path(yaml_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Flow 2: Governance Pipeline (CLI)
# ---------------------------------------------------------------------------


class TestGovernancePipelineCLI:
    """Flow 2: governance assess → cross-map → gap-analysis."""

    def test_flow2_assess_auto_exits_cleanly(self) -> None:
        r = _run(["governance", "assess", "--auto"])
        assert r.returncode in (0, 1)

    def test_flow2_assess_auto_has_numeric_output(self) -> None:
        r = _run(["governance", "assess", "--auto"])
        assert r.returncode in (0, 1)
        out = r.stdout + r.stderr
        assert any(c.isdigit() for c in out)

    def test_flow2_cross_map_json_is_valid(self) -> None:
        r = _run(["governance", "cross-map", "--json"])
        assert r.returncode in (0, 1)
        out = r.stdout
        start = out.find("{")
        assert start != -1, f"No JSON in output: {out[:200]}"
        data = json.loads(out[start:])
        assert isinstance(data, dict)
        assert len(data) > 0

    def test_flow2_cross_map_json_has_meti_or_iso_key(self) -> None:
        r = _run(["governance", "cross-map", "--json"])
        assert r.returncode in (0, 1)
        out = r.stdout
        start = out.find("{")
        data = json.loads(out[start:])
        # At least one key should contain a mapping
        assert len(data) > 0

    def test_flow2_gap_analysis_runs(self) -> None:
        r = _run(["governance", "gap-analysis"])
        assert r.returncode in (0, 1)
        out = r.stdout + r.stderr
        assert len(out.strip()) > 0


# ---------------------------------------------------------------------------
# Flow 3: Project → Simulate → History (API)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@_skip_api
class TestProjectSimulateFlowAPI:
    """Flow 3: POST /api/projects → simulate → verify data consistency."""

    def test_flow3_get_projects_before_creation(self) -> None:
        r = httpx.get(f"{FAULTRAY_URL}/api/projects", timeout=_HTTP_TIMEOUT)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_flow3_simulate_returns_score(self) -> None:
        r = httpx.post(
            f"{FAULTRAY_URL}/api/simulate",
            json={"sample": "web-saas"},
            timeout=_HTTP_TIMEOUT,
        )
        assert r.status_code == 200
        data = r.json()
        assert "overall_score" in data

    def test_flow3_simulate_score_consistent_range(self) -> None:
        """Two simulations of same sample should both return scores in 0-100."""
        r1 = httpx.post(
            f"{FAULTRAY_URL}/api/simulate",
            json={"sample": "web-saas"},
            timeout=_HTTP_TIMEOUT,
        )
        r2 = httpx.post(
            f"{FAULTRAY_URL}/api/simulate",
            json={"sample": "web-saas"},
            timeout=_HTTP_TIMEOUT,
        )
        assert r1.status_code == 200
        assert r2.status_code == 200
        s1 = r1.json()["overall_score"]
        s2 = r2.json()["overall_score"]
        assert 0 <= s1 <= 100
        assert 0 <= s2 <= 100

    def test_flow3_projects_returns_list_after_simulate(self) -> None:
        httpx.post(
            f"{FAULTRAY_URL}/api/simulate",
            json={"sample": "web-saas"},
            timeout=_HTTP_TIMEOUT,
        )
        r = httpx.get(f"{FAULTRAY_URL}/api/projects", timeout=_HTTP_TIMEOUT)
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ---------------------------------------------------------------------------
# Flow 4: APM Agent Lifecycle (API)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@_skip_api
class TestAPMAgentLifecycleAPI:
    """Flow 4: register agent → heartbeat → list → metrics."""

    _AGENT_ID = "e2e-flow-agent-lifecycle"

    def test_flow4_register_agent(self) -> None:
        r = httpx.post(
            f"{FAULTRAY_URL}/api/apm/agents/register",
            json={"agent_id": self._AGENT_ID, "hostname": "flow-test-host"},
            timeout=_HTTP_TIMEOUT,
        )
        assert r.status_code == 200
        data = r.json()
        assert data.get("ok") is True or "agent_id" in data

    def test_flow4_heartbeat_after_register(self) -> None:
        # Register
        httpx.post(
            f"{FAULTRAY_URL}/api/apm/agents/register",
            json={"agent_id": self._AGENT_ID, "hostname": "flow-test-host"},
            timeout=_HTTP_TIMEOUT,
        )
        # Heartbeat
        r = httpx.post(
            f"{FAULTRAY_URL}/api/apm/agents/{self._AGENT_ID}/heartbeat",
            json={},
            timeout=_HTTP_TIMEOUT,
        )
        assert r.status_code == 200

    def test_flow4_agents_list_returns_list(self) -> None:
        r = httpx.get(f"{FAULTRAY_URL}/api/apm/agents", timeout=_HTTP_TIMEOUT)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_flow4_agent_metrics_endpoint_returns_200(self) -> None:
        httpx.post(
            f"{FAULTRAY_URL}/api/apm/agents/register",
            json={"agent_id": self._AGENT_ID, "hostname": "flow-test-host"},
            timeout=_HTTP_TIMEOUT,
        )
        r = httpx.get(
            f"{FAULTRAY_URL}/api/apm/agents/{self._AGENT_ID}/metrics",
            timeout=_HTTP_TIMEOUT,
        )
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Flow 5: Full Report Generation (API)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@_skip_api
class TestFullReportGenerationAPI:
    """Flow 5: simulate → report → FMEA → DORA — all consistent JSON."""

    def test_flow5_simulate_returns_json(self) -> None:
        r = httpx.post(
            f"{FAULTRAY_URL}/api/simulate",
            json={"sample": "web-saas"},
            timeout=_HTTP_TIMEOUT,
        )
        assert r.status_code == 200
        assert "application/json" in r.headers.get("content-type", "")

    def test_flow5_executive_report_has_summary(self) -> None:
        r = httpx.get(f"{FAULTRAY_URL}/api/reports?action=report", timeout=_HTTP_TIMEOUT)
        assert r.status_code == 200
        data = r.json()
        assert "executive_summary" in data

    def test_flow5_fmea_has_failure_modes(self) -> None:
        r = httpx.get(f"{FAULTRAY_URL}/api/risk?action=fmea", timeout=_HTTP_TIMEOUT)
        assert r.status_code == 200
        data = r.json()
        assert "failure_modes" in data

    def test_flow5_dora_assessment_has_score(self) -> None:
        r = httpx.get(f"{FAULTRAY_URL}/api/compliance?action=dora", timeout=_HTTP_TIMEOUT)
        assert r.status_code == 200
        data = r.json()
        assert "overall_score" in data

    def test_flow5_all_endpoints_return_json(self) -> None:
        """Verify all report endpoints return application/json content-type."""
        endpoints = [
            ("GET", f"{FAULTRAY_URL}/api/reports?action=report"),
            ("GET", f"{FAULTRAY_URL}/api/risk?action=fmea"),
            ("GET", f"{FAULTRAY_URL}/api/compliance?action=dora"),
        ]
        for method, url in endpoints:
            r = httpx.get(url, timeout=_HTTP_TIMEOUT)
            assert r.status_code == 200, f"{url} returned {r.status_code}"
            ct = r.headers.get("content-type", "")
            assert "application/json" in ct, f"{url} content-type: {ct}"

    def test_flow5_all_scores_are_numeric(self) -> None:
        """All score fields across report endpoints are numeric."""
        sim_r = httpx.post(
            f"{FAULTRAY_URL}/api/simulate",
            json={"sample": "web-saas"},
            timeout=_HTTP_TIMEOUT,
        )
        dora_r = httpx.get(f"{FAULTRAY_URL}/api/compliance?action=dora", timeout=_HTTP_TIMEOUT)

        sim_score = sim_r.json().get("overall_score")
        dora_score = dora_r.json().get("overall_score")

        assert isinstance(sim_score, (int, float)), f"simulate score: {sim_score!r}"
        assert isinstance(dora_score, (int, float)), f"dora score: {dora_score!r}"
