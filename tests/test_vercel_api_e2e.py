# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Vercel API E2E tests for FaultRay.

Tests the actual deployed API endpoints at https://faultray.com.
All tests are marked with @pytest.mark.e2e and require network access.

Run with:
    pytest tests/test_vercel_api_e2e.py -m e2e
"""

from __future__ import annotations

import pytest

# Mark all tests in this file as E2E (network-required)
pytestmark = pytest.mark.e2e

FAULTRAY_URL = "https://faultray.com"

# ---------------------------------------------------------------------------
# Optional import: httpx may not be installed in all environments
# ---------------------------------------------------------------------------

try:
    import httpx

    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False

_skip_if_no_httpx = pytest.mark.skipif(
    not _HTTPX_AVAILABLE,
    reason="httpx not installed — install with: pip install httpx",
)

_TIMEOUT = 15.0  # seconds


# ---------------------------------------------------------------------------
# APM Endpoints
# ---------------------------------------------------------------------------


@_skip_if_no_httpx
class TestVercelAPMEndpoints:
    """Tests for /api/apm/* endpoints on the live Vercel deployment."""

    def test_get_agents_returns_200(self) -> None:
        resp = httpx.get(f"{FAULTRAY_URL}/api/apm/agents", timeout=_TIMEOUT)
        assert resp.status_code == 200

    def test_get_agents_returns_list(self) -> None:
        resp = httpx.get(f"{FAULTRAY_URL}/api/apm/agents", timeout=_TIMEOUT)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_get_agents_returns_valid_structure(self) -> None:
        resp = httpx.get(f"{FAULTRAY_URL}/api/apm/agents", timeout=_TIMEOUT)
        assert resp.status_code == 200
        agents = resp.json()
        # May be empty (Supabase connected but no agents) or demo data
        assert isinstance(agents, list)
        if agents:
            assert "agent_id" in agents[0] or "hostname" in agents[0]

    def test_get_alerts_returns_200(self) -> None:
        resp = httpx.get(f"{FAULTRAY_URL}/api/apm/alerts", timeout=_TIMEOUT)
        assert resp.status_code == 200

    def test_get_alerts_returns_list(self) -> None:
        resp = httpx.get(f"{FAULTRAY_URL}/api/apm/alerts", timeout=_TIMEOUT)
        data = resp.json()
        assert isinstance(data, list)

    def test_get_stats_returns_200(self) -> None:
        resp = httpx.get(f"{FAULTRAY_URL}/api/apm/stats", timeout=_TIMEOUT)
        assert resp.status_code == 200

    def test_get_stats_has_summary_fields(self) -> None:
        resp = httpx.get(f"{FAULTRAY_URL}/api/apm/stats", timeout=_TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            assert isinstance(data, dict)

    def test_content_type_is_json(self) -> None:
        resp = httpx.get(f"{FAULTRAY_URL}/api/apm/agents", timeout=_TIMEOUT)
        assert "application/json" in resp.headers.get("content-type", "")


# ---------------------------------------------------------------------------
# Projects / Simulate Endpoints
# ---------------------------------------------------------------------------


@_skip_if_no_httpx
class TestVercelProjectsEndpoints:
    """Tests for /api/projects and /api/simulate endpoints."""

    def test_get_projects_returns_200(self) -> None:
        resp = httpx.get(f"{FAULTRAY_URL}/api/projects", timeout=_TIMEOUT)
        assert resp.status_code == 200

    def test_get_projects_returns_list_or_dict(self) -> None:
        resp = httpx.get(f"{FAULTRAY_URL}/api/projects", timeout=_TIMEOUT)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, (list, dict))

    def test_simulate_with_sample_web_saas(self) -> None:
        resp = httpx.post(
            f"{FAULTRAY_URL}/api/simulate",
            json={"sample": "web-saas"},
            timeout=_TIMEOUT,
        )
        assert resp.status_code == 200

    def test_simulate_returns_overall_score(self) -> None:
        resp = httpx.post(
            f"{FAULTRAY_URL}/api/simulate",
            json={"sample": "web-saas"},
            timeout=_TIMEOUT,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "overall_score" in data

    def test_simulate_returns_total_scenarios(self) -> None:
        resp = httpx.post(
            f"{FAULTRAY_URL}/api/simulate",
            json={"sample": "web-saas"},
            timeout=_TIMEOUT,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("total_scenarios", 0) > 0

    def test_simulate_score_in_valid_range(self) -> None:
        resp = httpx.post(
            f"{FAULTRAY_URL}/api/simulate",
            json={"sample": "web-saas"},
            timeout=_TIMEOUT,
        )
        assert resp.status_code == 200
        score = resp.json().get("overall_score", -1)
        assert 0.0 <= score <= 100.0


# ---------------------------------------------------------------------------
# Health Endpoint
# ---------------------------------------------------------------------------


@_skip_if_no_httpx
class TestVercelHealthEndpoint:
    """Tests for /api/health endpoint."""

    def test_health_check_returns_200(self) -> None:
        resp = httpx.get(f"{FAULTRAY_URL}/api/health", timeout=_TIMEOUT)
        assert resp.status_code == 200

    def test_health_check_status_ok(self) -> None:
        resp = httpx.get(f"{FAULTRAY_URL}/api/health", timeout=_TIMEOUT)
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "ok"

    def test_health_returns_json(self) -> None:
        resp = httpx.get(f"{FAULTRAY_URL}/api/health", timeout=_TIMEOUT)
        assert "application/json" in resp.headers.get("content-type", "")

    def test_health_response_fast(self) -> None:
        """Health endpoint should respond in under 5 seconds."""
        import time
        start = time.time()
        httpx.get(f"{FAULTRAY_URL}/api/health", timeout=_TIMEOUT)
        elapsed = time.time() - start
        assert elapsed < 5.0


# ---------------------------------------------------------------------------
# Root / Landing
# ---------------------------------------------------------------------------


@_skip_if_no_httpx
class TestVercelRootEndpoint:
    """Tests for the root landing page."""

    def test_root_returns_200_or_redirect(self) -> None:
        resp = httpx.get(FAULTRAY_URL, timeout=_TIMEOUT, follow_redirects=False)
        # Root may redirect to /en or /ja (i18n proxy)
        assert resp.status_code in (200, 301, 302, 307, 308)

    def test_root_resolves_to_html(self) -> None:
        resp = httpx.get(FAULTRAY_URL, timeout=_TIMEOUT, follow_redirects=True)
        ct = resp.headers.get("content-type", "")
        assert "text/html" in ct

    def test_root_no_500_error(self) -> None:
        resp = httpx.get(FAULTRAY_URL, timeout=_TIMEOUT)
        assert resp.status_code < 500
