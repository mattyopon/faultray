# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""E2E: Every API endpoint returns valid responses.

Tests ALL API endpoints with real HTTP requests to https://faultray.com.
Zero mocks.  Marked with @pytest.mark.e2e.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.e2e

try:
    import httpx

    _HTTPX = True
except ImportError:
    _HTTPX = False
    httpx = None  # type: ignore[assignment]

_skip = pytest.mark.skipif(not _HTTPX, reason="httpx not installed")

FAULTRAY_URL = "https://faultray.com"
_TIMEOUT = 15.0


# ---------------------------------------------------------------------------
# Health & Chat
# ---------------------------------------------------------------------------


@_skip
class TestHealthAPI:
    """GET /api/health."""

    def test_health_200(self) -> None:
        assert httpx is not None
        r = httpx.get(f"{FAULTRAY_URL}/api/health", timeout=_TIMEOUT)
        assert r.status_code == 200

    def test_health_status_ok(self) -> None:
        assert httpx is not None
        r = httpx.get(f"{FAULTRAY_URL}/api/health", timeout=_TIMEOUT)
        data = r.json()
        assert data.get("status") == "ok"

    def test_health_json_content_type(self) -> None:
        assert httpx is not None
        r = httpx.get(f"{FAULTRAY_URL}/api/health", timeout=_TIMEOUT)
        assert "application/json" in r.headers.get("content-type", "")


@_skip
class TestChatAPI:
    """POST /api/chat."""

    def test_chat_200(self) -> None:
        assert httpx is not None
        r = httpx.post(
            f"{FAULTRAY_URL}/api/chat",
            json={"message": "how to improve resilience"},
            timeout=_TIMEOUT,
        )
        assert r.status_code == 200

    def test_chat_has_response_string(self) -> None:
        assert httpx is not None
        r = httpx.post(
            f"{FAULTRAY_URL}/api/chat",
            json={"message": "what is DORA"},
            timeout=_TIMEOUT,
        )
        data = r.json()
        assert "response" in data
        assert isinstance(data["response"], str)
        assert len(data["response"]) > 0

    def test_chat_empty_message_handled(self) -> None:
        assert httpx is not None
        r = httpx.post(
            f"{FAULTRAY_URL}/api/chat",
            json={"message": ""},
            timeout=_TIMEOUT,
        )
        # Should not crash -- 200 or 400 are both valid
        assert r.status_code in (200, 400)


# ---------------------------------------------------------------------------
# Simulate API
# ---------------------------------------------------------------------------


@_skip
class TestSimulateAPI:
    """POST /api/simulate."""

    def test_simulate_web_saas_200(self) -> None:
        assert httpx is not None
        r = httpx.post(
            f"{FAULTRAY_URL}/api/simulate",
            json={"sample": "web-saas"},
            timeout=_TIMEOUT,
        )
        assert r.status_code == 200

    def test_simulate_has_overall_score(self) -> None:
        assert httpx is not None
        r = httpx.post(
            f"{FAULTRAY_URL}/api/simulate",
            json={"sample": "web-saas"},
            timeout=_TIMEOUT,
        )
        data = r.json()
        assert "overall_score" in data

    def test_simulate_score_in_range(self) -> None:
        assert httpx is not None
        r = httpx.post(
            f"{FAULTRAY_URL}/api/simulate",
            json={"sample": "web-saas"},
            timeout=_TIMEOUT,
        )
        score = r.json().get("overall_score", -1)
        assert 0.0 <= score <= 100.0

    def test_simulate_has_total_scenarios(self) -> None:
        assert httpx is not None
        r = httpx.post(
            f"{FAULTRAY_URL}/api/simulate",
            json={"sample": "web-saas"},
            timeout=_TIMEOUT,
        )
        data = r.json()
        assert data.get("total_scenarios", 0) > 0

    def test_simulate_microservices_200(self) -> None:
        assert httpx is not None
        r = httpx.post(
            f"{FAULTRAY_URL}/api/simulate",
            json={"sample": "microservices"},
            timeout=_TIMEOUT,
        )
        assert r.status_code == 200

    def test_simulate_invalid_body_400(self) -> None:
        assert httpx is not None
        r = httpx.post(
            f"{FAULTRAY_URL}/api/simulate",
            json={"invalid_key": True},
            timeout=_TIMEOUT,
        )
        assert r.status_code == 400

    def test_simulate_json_content_type(self) -> None:
        assert httpx is not None
        r = httpx.post(
            f"{FAULTRAY_URL}/api/simulate",
            json={"sample": "web-saas"},
            timeout=_TIMEOUT,
        )
        assert "application/json" in r.headers.get("content-type", "")

    def test_simulate_has_suggestions(self) -> None:
        assert httpx is not None
        r = httpx.post(
            f"{FAULTRAY_URL}/api/simulate",
            json={"sample": "web-saas"},
            timeout=_TIMEOUT,
        )
        data = r.json()
        assert "suggestions" in data or "improvements" in data or "recommendations" in data

    def test_simulate_has_cascade_simulations(self) -> None:
        assert httpx is not None
        r = httpx.post(
            f"{FAULTRAY_URL}/api/simulate",
            json={"sample": "web-saas"},
            timeout=_TIMEOUT,
        )
        data = r.json()
        assert "cascade_simulations" in data or "cascades" in data or "scenarios" in data

    def test_simulate_has_calculation_evidence(self) -> None:
        assert httpx is not None
        r = httpx.post(
            f"{FAULTRAY_URL}/api/simulate",
            json={"sample": "web-saas"},
            timeout=_TIMEOUT,
        )
        data = r.json()
        # Rich simulation output should have evidence
        assert (
            "calculation_evidence" in data
            or "evidence" in data
            or "simulation_log" in data
            or "total_scenarios" in data
        )

    def test_simulate_save_run_action(self) -> None:
        """POST /api/simulate with action=save-run."""
        assert httpx is not None
        r = httpx.post(
            f"{FAULTRAY_URL}/api/simulate",
            json={"sample": "web-saas", "action": "save-run"},
            timeout=_TIMEOUT,
        )
        # 200 or 400 (if save-run needs auth) are both acceptable
        assert r.status_code in (200, 400, 401, 403)


# ---------------------------------------------------------------------------
# Analysis API
# ---------------------------------------------------------------------------


@_skip
class TestAnalysisAPI:
    """GET /api/analysis."""

    def test_score_explain_200(self) -> None:
        assert httpx is not None
        r = httpx.get(
            f"{FAULTRAY_URL}/api/analysis?action=score-explain",
            timeout=_TIMEOUT,
        )
        assert r.status_code == 200

    def test_score_explain_has_overall_score(self) -> None:
        assert httpx is not None
        r = httpx.get(
            f"{FAULTRAY_URL}/api/analysis?action=score-explain",
            timeout=_TIMEOUT,
        )
        data = r.json()
        assert "overall_score" in data

    def test_heatmap_200(self) -> None:
        assert httpx is not None
        # Heatmap is POST /api/analysis with action in body
        r = httpx.post(
            f"{FAULTRAY_URL}/api/analysis",
            json={"action": "heatmap"},
            timeout=_TIMEOUT,
        )
        assert r.status_code == 200

    def test_heatmap_has_components(self) -> None:
        assert httpx is not None
        r = httpx.post(
            f"{FAULTRAY_URL}/api/analysis",
            json={"action": "heatmap"},
            timeout=_TIMEOUT,
        )
        data = r.json()
        assert "components" in data
        assert isinstance(data["components"], list)


# ---------------------------------------------------------------------------
# Discovery API
# ---------------------------------------------------------------------------


@_skip
class TestDiscoveryAPI:
    """POST /api/discovery."""

    def test_discovery_without_creds_returns_error(self) -> None:
        assert httpx is not None
        r = httpx.post(
            f"{FAULTRAY_URL}/api/discovery",
            json={},
            timeout=_TIMEOUT,
        )
        # No credentials -> 400/422/500
        assert r.status_code in (400, 422, 500)


# ---------------------------------------------------------------------------
# Compliance / Governance API
# ---------------------------------------------------------------------------


@_skip
class TestComplianceAPI:
    """GET/POST /api/compliance."""

    def test_compliance_dora_get_200(self) -> None:
        assert httpx is not None
        r = httpx.get(
            f"{FAULTRAY_URL}/api/compliance?action=dora", timeout=_TIMEOUT
        )
        assert r.status_code == 200

    def test_compliance_dora_has_pillars(self) -> None:
        assert httpx is not None
        r = httpx.get(
            f"{FAULTRAY_URL}/api/compliance?action=dora", timeout=_TIMEOUT
        )
        data = r.json()
        assert "pillars" in data or "dora_metrics" in data

    def test_compliance_dora_has_overall_score(self) -> None:
        assert httpx is not None
        r = httpx.get(
            f"{FAULTRAY_URL}/api/compliance?action=dora", timeout=_TIMEOUT
        )
        data = r.json()
        assert "overall_score" in data

    def test_compliance_post_dora_200(self) -> None:
        assert httpx is not None
        r = httpx.post(
            f"{FAULTRAY_URL}/api/compliance",
            json={"framework": "dora"},
            timeout=_TIMEOUT,
        )
        assert r.status_code == 200

    def test_compliance_post_soc2_200(self) -> None:
        assert httpx is not None
        r = httpx.post(
            f"{FAULTRAY_URL}/api/compliance",
            json={"framework": "soc2"},
            timeout=_TIMEOUT,
        )
        assert r.status_code == 200

    def test_compliance_post_iso27001_200(self) -> None:
        assert httpx is not None
        r = httpx.post(
            f"{FAULTRAY_URL}/api/compliance",
            json={"framework": "iso27001"},
            timeout=_TIMEOUT,
        )
        assert r.status_code == 200

    def test_compliance_post_invalid_framework_400(self) -> None:
        assert httpx is not None
        r = httpx.post(
            f"{FAULTRAY_URL}/api/compliance",
            json={"framework": "nonexistent_xyz"},
            timeout=_TIMEOUT,
        )
        assert r.status_code == 400

    def test_compliance_no_action_has_supported_actions(self) -> None:
        assert httpx is not None
        r = httpx.get(f"{FAULTRAY_URL}/api/compliance", timeout=_TIMEOUT)
        assert r.status_code == 200
        data = r.json()
        assert "supported_actions" in data

    def test_compliance_json_content_type(self) -> None:
        assert httpx is not None
        r = httpx.get(
            f"{FAULTRAY_URL}/api/compliance?action=dora", timeout=_TIMEOUT
        )
        assert "application/json" in r.headers.get("content-type", "")


@_skip
class TestGovernanceAPI:
    """GET /api/governance."""

    def test_governance_dora_200(self) -> None:
        assert httpx is not None
        r = httpx.get(
            f"{FAULTRAY_URL}/api/governance?action=dora", timeout=_TIMEOUT
        )
        assert r.status_code == 200

    def test_governance_ai_governance_200(self) -> None:
        assert httpx is not None
        r = httpx.get(
            f"{FAULTRAY_URL}/api/governance?action=ai-governance",
            timeout=_TIMEOUT,
        )
        assert r.status_code == 200

    def test_governance_ai_governance_has_maturity_level(self) -> None:
        assert httpx is not None
        r = httpx.get(
            f"{FAULTRAY_URL}/api/governance?action=ai-governance",
            timeout=_TIMEOUT,
        )
        data = r.json()
        assert "maturity_level" in data

    def test_governance_ai_governance_has_categories(self) -> None:
        assert httpx is not None
        r = httpx.get(
            f"{FAULTRAY_URL}/api/governance?action=ai-governance",
            timeout=_TIMEOUT,
        )
        data = r.json()
        assert "categories" in data

    def test_governance_sla_200(self) -> None:
        assert httpx is not None
        r = httpx.get(
            f"{FAULTRAY_URL}/api/governance?action=sla", timeout=_TIMEOUT
        )
        assert r.status_code == 200

    def test_governance_sla_has_targets(self) -> None:
        assert httpx is not None
        r = httpx.get(
            f"{FAULTRAY_URL}/api/governance?action=sla", timeout=_TIMEOUT
        )
        data = r.json()
        assert "sla_target" in data
        assert "current_availability" in data


# ---------------------------------------------------------------------------
# Reports API
# ---------------------------------------------------------------------------


@_skip
class TestReportsAPI:
    """GET /api/reports."""

    def test_reports_report_200(self) -> None:
        assert httpx is not None
        r = httpx.get(
            f"{FAULTRAY_URL}/api/reports?action=report", timeout=_TIMEOUT
        )
        assert r.status_code == 200

    def test_reports_report_has_executive_summary(self) -> None:
        assert httpx is not None
        r = httpx.get(
            f"{FAULTRAY_URL}/api/reports?action=report", timeout=_TIMEOUT
        )
        data = r.json()
        assert "executive_summary" in data

    def test_reports_incidents_200(self) -> None:
        assert httpx is not None
        r = httpx.get(
            f"{FAULTRAY_URL}/api/reports?action=incidents", timeout=_TIMEOUT
        )
        assert r.status_code == 200

    def test_reports_incidents_has_list(self) -> None:
        assert httpx is not None
        r = httpx.get(
            f"{FAULTRAY_URL}/api/reports?action=incidents", timeout=_TIMEOUT
        )
        data = r.json()
        assert "incidents" in data
        assert isinstance(data["incidents"], list)

    def test_reports_json_content_type(self) -> None:
        assert httpx is not None
        r = httpx.get(
            f"{FAULTRAY_URL}/api/reports?action=report", timeout=_TIMEOUT
        )
        assert "application/json" in r.headers.get("content-type", "")


# ---------------------------------------------------------------------------
# Risk API
# ---------------------------------------------------------------------------


@_skip
class TestRiskAPI:
    """GET /api/risk."""

    def test_risk_attack_surface_200(self) -> None:
        assert httpx is not None
        r = httpx.get(
            f"{FAULTRAY_URL}/api/risk?action=attack-surface", timeout=_TIMEOUT
        )
        assert r.status_code == 200

    def test_risk_attack_surface_has_summary(self) -> None:
        assert httpx is not None
        r = httpx.get(
            f"{FAULTRAY_URL}/api/risk?action=attack-surface", timeout=_TIMEOUT
        )
        data = r.json()
        assert "summary" in data

    def test_risk_fmea_200(self) -> None:
        assert httpx is not None
        r = httpx.get(
            f"{FAULTRAY_URL}/api/risk?action=fmea", timeout=_TIMEOUT
        )
        assert r.status_code == 200

    def test_risk_fmea_has_failure_modes(self) -> None:
        assert httpx is not None
        r = httpx.get(
            f"{FAULTRAY_URL}/api/risk?action=fmea", timeout=_TIMEOUT
        )
        data = r.json()
        assert "failure_modes" in data
        assert isinstance(data["failure_modes"], list)


# ---------------------------------------------------------------------------
# Finance API
# ---------------------------------------------------------------------------


@_skip
class TestFinanceAPI:
    """GET/POST /api/finance."""

    def test_finance_benchmark_fintech_200(self) -> None:
        assert httpx is not None
        r = httpx.get(
            f"{FAULTRAY_URL}/api/finance?action=benchmark&industry=fintech",
            timeout=_TIMEOUT,
        )
        assert r.status_code == 200

    def test_finance_benchmark_has_industry(self) -> None:
        assert httpx is not None
        r = httpx.get(
            f"{FAULTRAY_URL}/api/finance?action=benchmark&industry=fintech",
            timeout=_TIMEOUT,
        )
        data = r.json()
        assert "industry" in data or "industry_id" in data

    def test_finance_post_cost_200(self) -> None:
        assert httpx is not None
        r = httpx.post(
            f"{FAULTRAY_URL}/api/finance",
            json={"action": "cost", "revenue_per_hour": 10000, "industry": "saas"},
            timeout=_TIMEOUT,
        )
        assert r.status_code == 200

    def test_finance_post_cost_has_data(self) -> None:
        assert httpx is not None
        r = httpx.post(
            f"{FAULTRAY_URL}/api/finance",
            json={"action": "cost", "revenue_per_hour": 10000, "industry": "saas"},
            timeout=_TIMEOUT,
        )
        data = r.json()
        assert isinstance(data, dict)
        assert len(data) > 0

    def test_finance_benchmark_healthcare_200(self) -> None:
        assert httpx is not None
        r = httpx.get(
            f"{FAULTRAY_URL}/api/finance?action=benchmark&industry=healthcare",
            timeout=_TIMEOUT,
        )
        assert r.status_code == 200

    def test_finance_benchmark_ecommerce_200(self) -> None:
        assert httpx is not None
        r = httpx.get(
            f"{FAULTRAY_URL}/api/finance?action=benchmark&industry=ecommerce",
            timeout=_TIMEOUT,
        )
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# APM API
# ---------------------------------------------------------------------------


@_skip
class TestAPMAPI:
    """GET/POST /api/apm/*."""

    def test_apm_agents_200(self) -> None:
        assert httpx is not None
        r = httpx.get(f"{FAULTRAY_URL}/api/apm/agents", timeout=_TIMEOUT)
        assert r.status_code == 200

    def test_apm_agents_is_list(self) -> None:
        assert httpx is not None
        r = httpx.get(f"{FAULTRAY_URL}/api/apm/agents", timeout=_TIMEOUT)
        assert isinstance(r.json(), list)

    def test_apm_alerts_200(self) -> None:
        assert httpx is not None
        r = httpx.get(f"{FAULTRAY_URL}/api/apm/alerts", timeout=_TIMEOUT)
        assert r.status_code == 200

    def test_apm_alerts_is_list(self) -> None:
        assert httpx is not None
        r = httpx.get(f"{FAULTRAY_URL}/api/apm/alerts", timeout=_TIMEOUT)
        assert isinstance(r.json(), list)

    def test_apm_stats_200(self) -> None:
        assert httpx is not None
        r = httpx.get(f"{FAULTRAY_URL}/api/apm/stats", timeout=_TIMEOUT)
        assert r.status_code == 200

    def test_apm_stats_has_total_agents(self) -> None:
        assert httpx is not None
        r = httpx.get(f"{FAULTRAY_URL}/api/apm/stats", timeout=_TIMEOUT)
        data = r.json()
        assert "total_agents" in data

    def test_apm_register_agent_200(self) -> None:
        assert httpx is not None
        r = httpx.post(
            f"{FAULTRAY_URL}/api/apm/agents/register",
            json={"agent_id": "e2e-allapi-agent", "hostname": "test-host"},
            timeout=_TIMEOUT,
        )
        assert r.status_code == 200

    def test_apm_agent_metrics_200(self) -> None:
        assert httpx is not None
        # Register first
        httpx.post(
            f"{FAULTRAY_URL}/api/apm/agents/register",
            json={"agent_id": "e2e-allapi-metrics", "hostname": "test-host"},
            timeout=_TIMEOUT,
        )
        r = httpx.get(
            f"{FAULTRAY_URL}/api/apm/agents/e2e-allapi-metrics/metrics",
            timeout=_TIMEOUT,
        )
        assert r.status_code == 200

    def test_apm_agents_json_content_type(self) -> None:
        assert httpx is not None
        r = httpx.get(f"{FAULTRAY_URL}/api/apm/agents", timeout=_TIMEOUT)
        assert "application/json" in r.headers.get("content-type", "")


# ---------------------------------------------------------------------------
# Projects API
# ---------------------------------------------------------------------------


@_skip
class TestProjectsAPI:
    """GET /api/projects."""

    def test_projects_200(self) -> None:
        assert httpx is not None
        r = httpx.get(f"{FAULTRAY_URL}/api/projects", timeout=_TIMEOUT)
        assert r.status_code == 200

    def test_projects_is_list(self) -> None:
        assert httpx is not None
        r = httpx.get(f"{FAULTRAY_URL}/api/projects", timeout=_TIMEOUT)
        assert isinstance(r.json(), list)


# ---------------------------------------------------------------------------
# Cross-cutting: CORS, 404, response times
# ---------------------------------------------------------------------------


@_skip
class TestAPICrossCutting:
    """Cross-cutting API concerns."""

    def test_options_returns_cors(self) -> None:
        assert httpx is not None
        r = httpx.options(f"{FAULTRAY_URL}/api/health", timeout=_TIMEOUT)
        assert r.status_code in (200, 204)
        cors = r.headers.get("access-control-allow-origin", "")
        assert cors != "", "No CORS header"

    def test_nonexistent_api_404(self) -> None:
        assert httpx is not None
        r = httpx.get(
            f"{FAULTRAY_URL}/api/nonexistent-endpoint-xyzabc",
            timeout=_TIMEOUT,
            follow_redirects=True,
        )
        assert r.status_code == 404

    def test_api_response_time_under_10s(self) -> None:
        import time

        assert httpx is not None
        endpoints = [
            f"{FAULTRAY_URL}/api/health",
            f"{FAULTRAY_URL}/api/compliance?action=dora",
            f"{FAULTRAY_URL}/api/apm/agents",
        ]
        for url in endpoints:
            t0 = time.time()
            httpx.get(url, timeout=10.0)
            elapsed = time.time() - t0
            assert elapsed < 10.0, f"{url} took {elapsed:.1f}s"
