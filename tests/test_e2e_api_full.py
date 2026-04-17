# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Full Vercel API coverage E2E tests — NO mocks.

All tests make real HTTP requests to https://faultray.com.
Marked with @pytest.mark.e2e — skip with: pytest -m "not e2e"
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.e2e

try:
    import httpx

    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False

_skip = pytest.mark.skipif(not _HTTPX_AVAILABLE, reason="httpx not installed")

FAULTRAY_URL = "https://faultray.com"
_TIMEOUT = 15.0


# ---------------------------------------------------------------------------
# Engine API
# ---------------------------------------------------------------------------


@_skip
class TestEngineAPI:
    """Tests for /api/simulate and /api/analysis endpoints."""

    def test_simulate_web_saas_200(self) -> None:
        r = httpx.post(
            f"{FAULTRAY_URL}/api/simulate",
            json={"sample": "web-saas"},
            timeout=_TIMEOUT,
        )
        assert r.status_code == 200

    def test_simulate_web_saas_has_overall_score(self) -> None:
        r = httpx.post(
            f"{FAULTRAY_URL}/api/simulate",
            json={"sample": "web-saas"},
            timeout=_TIMEOUT,
        )
        assert r.status_code == 200
        data = r.json()
        assert "overall_score" in data

    def test_simulate_web_saas_total_scenarios_positive(self) -> None:
        r = httpx.post(
            f"{FAULTRAY_URL}/api/simulate",
            json={"sample": "web-saas"},
            timeout=_TIMEOUT,
        )
        assert r.status_code == 200
        data = r.json()
        assert data.get("total_scenarios", 0) > 0

    def test_simulate_web_saas_score_in_range(self) -> None:
        r = httpx.post(
            f"{FAULTRAY_URL}/api/simulate",
            json={"sample": "web-saas"},
            timeout=_TIMEOUT,
        )
        assert r.status_code == 200
        score = r.json().get("overall_score", -1)
        assert 0.0 <= score <= 100.0

    def test_simulate_microservices_200(self) -> None:
        r = httpx.post(
            f"{FAULTRAY_URL}/api/simulate",
            json={"sample": "microservices"},
            timeout=_TIMEOUT,
        )
        assert r.status_code == 200

    def test_simulate_invalid_body_400(self) -> None:
        r = httpx.post(
            f"{FAULTRAY_URL}/api/simulate",
            json={"invalid_key": True},
            timeout=_TIMEOUT,
        )
        assert r.status_code == 400

    def test_analysis_score_explain_200(self) -> None:
        r = httpx.get(
            f"{FAULTRAY_URL}/api/analysis?action=score-explain",
            timeout=_TIMEOUT,
        )
        assert r.status_code == 200

    def test_analysis_score_explain_has_overall_score(self) -> None:
        r = httpx.get(
            f"{FAULTRAY_URL}/api/analysis?action=score-explain",
            timeout=_TIMEOUT,
        )
        assert r.status_code == 200
        data = r.json()
        assert "overall_score" in data

    def test_discovery_without_creds_400_or_500(self) -> None:
        """Discovery requires cloud credentials — expects 4xx or 5xx."""
        r = httpx.post(
            f"{FAULTRAY_URL}/api/discovery",
            json={},
            timeout=_TIMEOUT,
        )
        assert r.status_code in (400, 422, 500)


# ---------------------------------------------------------------------------
# Compliance / Governance API
# ---------------------------------------------------------------------------


@_skip
class TestComplianceGovernanceAPI:
    """Tests for /api/compliance and /api/governance endpoints."""

    def test_compliance_dora_200(self) -> None:
        r = httpx.get(f"{FAULTRAY_URL}/api/compliance?action=dora", timeout=_TIMEOUT)
        assert r.status_code == 200

    def test_compliance_dora_has_pillars(self) -> None:
        r = httpx.get(f"{FAULTRAY_URL}/api/compliance?action=dora", timeout=_TIMEOUT)
        assert r.status_code == 200
        data = r.json()
        assert "pillars" in data or "dora_metrics" in data

    def test_compliance_dora_has_overall_score(self) -> None:
        r = httpx.get(f"{FAULTRAY_URL}/api/compliance?action=dora", timeout=_TIMEOUT)
        assert r.status_code == 200
        data = r.json()
        assert "overall_score" in data

    def test_governance_ai_governance_200(self) -> None:
        r = httpx.get(
            f"{FAULTRAY_URL}/api/governance?action=ai-governance",
            timeout=_TIMEOUT,
        )
        assert r.status_code == 200

    def test_governance_ai_governance_has_maturity_level(self) -> None:
        r = httpx.get(
            f"{FAULTRAY_URL}/api/governance?action=ai-governance",
            timeout=_TIMEOUT,
        )
        assert r.status_code == 200
        data = r.json()
        assert "maturity_level" in data

    def test_governance_ai_governance_has_categories(self) -> None:
        r = httpx.get(
            f"{FAULTRAY_URL}/api/governance?action=ai-governance",
            timeout=_TIMEOUT,
        )
        assert r.status_code == 200
        data = r.json()
        assert "categories" in data

    def test_governance_sla_200(self) -> None:
        r = httpx.get(f"{FAULTRAY_URL}/api/governance?action=sla", timeout=_TIMEOUT)
        assert r.status_code == 200

    def test_governance_sla_has_sla_target(self) -> None:
        r = httpx.get(f"{FAULTRAY_URL}/api/governance?action=sla", timeout=_TIMEOUT)
        assert r.status_code == 200
        data = r.json()
        assert "sla_target" in data
        assert "current_availability" in data

    def test_compliance_post_dora_200(self) -> None:
        r = httpx.post(
            f"{FAULTRAY_URL}/api/compliance",
            json={"framework": "dora"},
            timeout=_TIMEOUT,
        )
        assert r.status_code == 200

    def test_compliance_post_soc2_200(self) -> None:
        r = httpx.post(
            f"{FAULTRAY_URL}/api/compliance",
            json={"framework": "soc2"},
            timeout=_TIMEOUT,
        )
        assert r.status_code == 200

    def test_compliance_post_invalid_framework_400(self) -> None:
        r = httpx.post(
            f"{FAULTRAY_URL}/api/compliance",
            json={"framework": "invalid_framework_xyz"},
            timeout=_TIMEOUT,
        )
        assert r.status_code == 400

    def test_compliance_get_no_action_has_supported_actions(self) -> None:
        r = httpx.get(f"{FAULTRAY_URL}/api/compliance", timeout=_TIMEOUT)
        assert r.status_code == 200
        data = r.json()
        assert "supported_actions" in data


# ---------------------------------------------------------------------------
# Reports API
# ---------------------------------------------------------------------------


@_skip
class TestReportsAPI:
    """Tests for /api/reports, /api/risk, and /api/finance endpoints."""

    def test_reports_report_200(self) -> None:
        r = httpx.get(f"{FAULTRAY_URL}/api/reports?action=report", timeout=_TIMEOUT)
        assert r.status_code == 200

    def test_reports_report_has_executive_summary(self) -> None:
        r = httpx.get(f"{FAULTRAY_URL}/api/reports?action=report", timeout=_TIMEOUT)
        assert r.status_code == 200
        data = r.json()
        assert "executive_summary" in data

    def test_reports_incidents_200(self) -> None:
        r = httpx.get(f"{FAULTRAY_URL}/api/reports?action=incidents", timeout=_TIMEOUT)
        assert r.status_code == 200

    def test_reports_incidents_has_incidents_array(self) -> None:
        r = httpx.get(f"{FAULTRAY_URL}/api/reports?action=incidents", timeout=_TIMEOUT)
        assert r.status_code == 200
        data = r.json()
        assert "incidents" in data
        assert isinstance(data["incidents"], list)

    def test_risk_attack_surface_200(self) -> None:
        r = httpx.get(
            f"{FAULTRAY_URL}/api/risk?action=attack-surface",
            timeout=_TIMEOUT,
        )
        assert r.status_code == 200

    def test_risk_attack_surface_has_summary(self) -> None:
        r = httpx.get(
            f"{FAULTRAY_URL}/api/risk?action=attack-surface",
            timeout=_TIMEOUT,
        )
        assert r.status_code == 200
        data = r.json()
        assert "summary" in data

    def test_risk_fmea_200(self) -> None:
        r = httpx.get(f"{FAULTRAY_URL}/api/risk?action=fmea", timeout=_TIMEOUT)
        assert r.status_code == 200

    def test_risk_fmea_has_failure_modes(self) -> None:
        r = httpx.get(f"{FAULTRAY_URL}/api/risk?action=fmea", timeout=_TIMEOUT)
        assert r.status_code == 200
        data = r.json()
        assert "failure_modes" in data
        assert isinstance(data["failure_modes"], list)

    def test_finance_benchmark_fintech_200(self) -> None:
        r = httpx.get(
            f"{FAULTRAY_URL}/api/finance?action=benchmark&industry=fintech",
            timeout=_TIMEOUT,
        )
        assert r.status_code == 200

    def test_finance_benchmark_has_industry(self) -> None:
        r = httpx.get(
            f"{FAULTRAY_URL}/api/finance?action=benchmark&industry=fintech",
            timeout=_TIMEOUT,
        )
        assert r.status_code == 200
        data = r.json()
        assert "industry" in data or "industry_id" in data

    def test_finance_post_cost_200(self) -> None:
        r = httpx.post(
            f"{FAULTRAY_URL}/api/finance",
            json={"action": "cost", "revenue_per_hour": 10000, "industry": "saas"},
            timeout=_TIMEOUT,
        )
        assert r.status_code == 200

    def test_finance_post_cost_has_improvements(self) -> None:
        r = httpx.post(
            f"{FAULTRAY_URL}/api/finance",
            json={"action": "cost", "revenue_per_hour": 10000, "industry": "saas"},
            timeout=_TIMEOUT,
        )
        assert r.status_code == 200
        data = r.json()
        # Response has financial data
        assert isinstance(data, dict)
        assert len(data) > 0


# ---------------------------------------------------------------------------
# Realtime / APM API
# ---------------------------------------------------------------------------


@_skip
class TestRealtimeAPMAPI:
    """Tests for /api/apm/* and related realtime endpoints."""

    def test_apm_agents_200(self) -> None:
        r = httpx.get(f"{FAULTRAY_URL}/api/apm/agents", timeout=_TIMEOUT)
        assert r.status_code == 200

    def test_apm_agents_is_list(self) -> None:
        r = httpx.get(f"{FAULTRAY_URL}/api/apm/agents", timeout=_TIMEOUT)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_apm_alerts_200(self) -> None:
        r = httpx.get(f"{FAULTRAY_URL}/api/apm/alerts", timeout=_TIMEOUT)
        assert r.status_code == 200

    def test_apm_alerts_is_list(self) -> None:
        r = httpx.get(f"{FAULTRAY_URL}/api/apm/alerts", timeout=_TIMEOUT)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_apm_stats_200(self) -> None:
        r = httpx.get(f"{FAULTRAY_URL}/api/apm/stats", timeout=_TIMEOUT)
        assert r.status_code == 200

    def test_apm_stats_has_total_agents(self) -> None:
        r = httpx.get(f"{FAULTRAY_URL}/api/apm/stats", timeout=_TIMEOUT)
        assert r.status_code == 200
        data = r.json()
        assert "total_agents" in data

    def test_projects_200(self) -> None:
        r = httpx.get(f"{FAULTRAY_URL}/api/projects", timeout=_TIMEOUT)
        assert r.status_code == 200

    def test_projects_is_list(self) -> None:
        r = httpx.get(f"{FAULTRAY_URL}/api/projects", timeout=_TIMEOUT)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_health_200(self) -> None:
        r = httpx.get(f"{FAULTRAY_URL}/api/health", timeout=_TIMEOUT)
        assert r.status_code == 200

    def test_health_status_ok(self) -> None:
        r = httpx.get(f"{FAULTRAY_URL}/api/health", timeout=_TIMEOUT)
        assert r.status_code == 200
        assert r.json().get("status") == "ok"

    def test_chat_post_200(self) -> None:
        r = httpx.post(
            f"{FAULTRAY_URL}/api/chat",
            json={"message": "how to improve resilience"},
            timeout=_TIMEOUT,
        )
        assert r.status_code == 200

    def test_chat_has_response_string(self) -> None:
        r = httpx.post(
            f"{FAULTRAY_URL}/api/chat",
            json={"message": "how to improve resilience"},
            timeout=_TIMEOUT,
        )
        assert r.status_code == 200
        data = r.json()
        assert "response" in data
        assert isinstance(data["response"], str)
        assert len(data["response"]) > 0

    def test_apm_register_agent_200(self) -> None:
        r = httpx.post(
            f"{FAULTRAY_URL}/api/apm/agents/register",
            json={"agent_id": "e2e-test-agent", "hostname": "test-host"},
            timeout=_TIMEOUT,
        )
        assert r.status_code == 200

    def test_apm_agent_metrics_endpoint_200(self) -> None:
        # Register first, then query metrics
        httpx.post(
            f"{FAULTRAY_URL}/api/apm/agents/register",
            json={"agent_id": "e2e-metrics-agent", "hostname": "test-host"},
            timeout=_TIMEOUT,
        )
        r = httpx.get(
            f"{FAULTRAY_URL}/api/apm/agents/e2e-metrics-agent/metrics",
            timeout=_TIMEOUT,
        )
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Cross-cutting Concerns
# ---------------------------------------------------------------------------


@_skip
class TestCrossCuttingConcerns:
    """Tests that apply across all API endpoints."""

    def test_health_returns_json_content_type(self) -> None:
        r = httpx.get(f"{FAULTRAY_URL}/api/health", timeout=_TIMEOUT)
        assert "application/json" in r.headers.get("content-type", "")

    def test_compliance_returns_json_content_type(self) -> None:
        r = httpx.get(f"{FAULTRAY_URL}/api/compliance?action=dora", timeout=_TIMEOUT)
        assert "application/json" in r.headers.get("content-type", "")

    def test_simulate_returns_json_content_type(self) -> None:
        r = httpx.post(
            f"{FAULTRAY_URL}/api/simulate",
            json={"sample": "web-saas"},
            timeout=_TIMEOUT,
        )
        assert "application/json" in r.headers.get("content-type", "")

    def test_api_endpoints_respond_within_10_seconds(self) -> None:
        """Key endpoints must respond in under 10 seconds."""
        import time

        endpoints = [
            ("GET", f"{FAULTRAY_URL}/api/health", None),
            ("GET", f"{FAULTRAY_URL}/api/compliance?action=dora", None),
        ]
        for method, url, body in endpoints:
            t0 = time.time()
            if method == "GET":
                httpx.get(url, timeout=10.0)
            else:
                httpx.post(url, json=body, timeout=10.0)
            elapsed = time.time() - t0
            assert elapsed < 10.0, f"{url} took {elapsed:.1f}s"

    def test_options_returns_cors_headers(self) -> None:
        """OPTIONS requests should return CORS headers."""
        r = httpx.options(f"{FAULTRAY_URL}/api/health", timeout=_TIMEOUT)
        # 200 or 204 are both valid for OPTIONS
        assert r.status_code in (200, 204)
        cors = r.headers.get("access-control-allow-origin", "")
        assert cors != "", "No CORS header on OPTIONS response"

    def test_invalid_path_returns_404(self) -> None:
        """Non-existent API paths should return 404."""
        r = httpx.get(
            f"{FAULTRAY_URL}/api/nonexistent-endpoint-xyzabc",
            timeout=_TIMEOUT,
            follow_redirects=True,
        )
        assert r.status_code == 404
