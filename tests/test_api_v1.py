"""Tests for FaultRay API v1 routes and OpenAPI documentation."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from faultray.api.server import app
from tests.conftest import TEST_API_KEY, _setup_test_user


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    _setup_test_user()
    return TestClient(app, raise_server_exceptions=False, headers={"Authorization": f"Bearer {TEST_API_KEY}"})


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------

class TestHealthEndpoint:
    """Tests for GET /api/v1/health."""

    def test_health_returns_200(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200

    def test_health_status_healthy(self, client):
        resp = client.get("/api/v1/health")
        data = resp.json()
        assert data["status"] == "healthy"

    def test_health_version_matches(self, client):
        import faultray
        resp = client.get("/api/v1/health")
        data = resp.json()
        assert data["version"] == faultray.__version__

    def test_health_engines_count(self, client):
        resp = client.get("/api/v1/health")
        data = resp.json()
        assert data["engines"] == 5

    def test_health_response_schema(self, client):
        resp = client.get("/api/v1/health")
        data = resp.json()
        assert "status" in data
        assert "version" in data
        assert "engines" in data


# ---------------------------------------------------------------------------
# Simulation endpoint
# ---------------------------------------------------------------------------

class TestSimulationEndpoint:
    """Tests for POST /api/v1/simulate."""

    def test_simulate_returns_200(self, client):
        payload = {
            "topology_yaml": "services:\n  - name: api\n    replicas: 3",
            "scenarios": "all",
            "engines": ["cascade"],
        }
        resp = client.post("/api/v1/simulate", json=payload)
        assert resp.status_code == 200

    def test_simulate_response_schema(self, client):
        payload = {
            "topology_yaml": "services:\n  - name: api\n    replicas: 3",
        }
        resp = client.post("/api/v1/simulate", json=payload)
        data = resp.json()
        assert "resilience_score" in data
        assert "scenarios_tested" in data
        assert "critical_count" in data
        assert "warning_count" in data
        assert "passed_count" in data
        assert "availability_nines" in data

    def test_simulate_resilience_score_range(self, client):
        payload = {"topology_yaml": "services:\n  - name: api"}
        resp = client.post("/api/v1/simulate", json=payload)
        data = resp.json()
        assert 0 <= data["resilience_score"] <= 100

    def test_simulate_default_engines(self, client):
        payload = {"topology_yaml": "services:\n  - name: api"}
        resp = client.post("/api/v1/simulate", json=payload)
        assert resp.status_code == 200

    def test_simulate_multiple_engines(self, client):
        payload = {
            "topology_yaml": "services:\n  - name: api",
            "engines": ["cascade", "dynamic", "ops"],
        }
        resp = client.post("/api/v1/simulate", json=payload)
        assert resp.status_code == 200

    def test_simulate_critical_filter(self, client):
        payload = {
            "topology_yaml": "services:\n  - name: api",
            "scenarios": "critical",
        }
        resp = client.post("/api/v1/simulate", json=payload)
        assert resp.status_code == 200

    def test_simulate_missing_topology_returns_422(self, client):
        resp = client.post("/api/v1/simulate", json={})
        assert resp.status_code == 422

    def test_simulate_counts_are_non_negative(self, client):
        payload = {"topology_yaml": "services:\n  - name: api"}
        resp = client.post("/api/v1/simulate", json=payload)
        data = resp.json()
        assert data["scenarios_tested"] >= 0
        assert data["critical_count"] >= 0
        assert data["warning_count"] >= 0
        assert data["passed_count"] >= 0


# ---------------------------------------------------------------------------
# Compliance endpoint
# ---------------------------------------------------------------------------

class TestComplianceEndpoint:
    """Tests for POST /api/v1/compliance/assess."""

    def test_assess_soc2_returns_200(self, client):
        payload = {"framework": "soc2", "evidence": {}}
        resp = client.post("/api/v1/compliance/assess", json=payload)
        assert resp.status_code == 200

    def test_assess_dora_returns_200(self, client):
        payload = {"framework": "dora", "evidence": {}}
        resp = client.post("/api/v1/compliance/assess", json=payload)
        assert resp.status_code == 200

    def test_assess_iso27001_returns_200(self, client):
        payload = {"framework": "iso27001"}
        resp = client.post("/api/v1/compliance/assess", json=payload)
        assert resp.status_code == 200

    def test_assess_pci_dss_returns_200(self, client):
        payload = {"framework": "pci_dss"}
        resp = client.post("/api/v1/compliance/assess", json=payload)
        assert resp.status_code == 200

    def test_assess_hipaa_returns_200(self, client):
        payload = {"framework": "hipaa"}
        resp = client.post("/api/v1/compliance/assess", json=payload)
        assert resp.status_code == 200

    def test_assess_gdpr_returns_200(self, client):
        payload = {"framework": "gdpr"}
        resp = client.post("/api/v1/compliance/assess", json=payload)
        assert resp.status_code == 200

    def test_assess_unknown_framework_returns_400(self, client):
        payload = {"framework": "unknown_framework"}
        resp = client.post("/api/v1/compliance/assess", json=payload)
        assert resp.status_code == 400

    def test_assess_response_schema(self, client):
        payload = {"framework": "soc2"}
        resp = client.post("/api/v1/compliance/assess", json=payload)
        data = resp.json()
        assert "framework" in data
        assert "overall_score" in data
        assert "compliant_count" in data
        assert "non_compliant_count" in data
        assert "critical_gaps" in data
        assert "recommendations" in data

    def test_assess_with_evidence(self, client):
        payload = {
            "framework": "soc2",
            "evidence": {
                "encryption_at_rest": True,
                "encryption_in_transit": True,
                "mfa_enabled": True,
            },
        }
        resp = client.post("/api/v1/compliance/assess", json=payload)
        data = resp.json()
        assert data["overall_score"] > 0

    def test_assess_score_range(self, client):
        payload = {"framework": "dora"}
        resp = client.post("/api/v1/compliance/assess", json=payload)
        data = resp.json()
        assert 0 <= data["overall_score"] <= 100

    def test_assess_framework_value_matches(self, client):
        payload = {"framework": "soc2"}
        resp = client.post("/api/v1/compliance/assess", json=payload)
        data = resp.json()
        assert data["framework"] == "soc2"

    def test_assess_missing_framework_returns_422(self, client):
        resp = client.post("/api/v1/compliance/assess", json={})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Cost endpoint
# ---------------------------------------------------------------------------

class TestCostEndpoint:
    """Tests for POST /api/v1/cost/analyze."""

    def test_cost_returns_200(self, client):
        payload = {"topology_yaml": "services:\n  - name: api"}
        resp = client.post("/api/v1/cost/analyze", json=payload)
        assert resp.status_code == 200

    def test_cost_response_schema(self, client):
        payload = {"topology_yaml": "services:\n  - name: api"}
        resp = client.post("/api/v1/cost/analyze", json=payload)
        data = resp.json()
        assert "expected_annual_cost" in data
        assert "worst_case_annual_cost" in data
        assert "top_scenarios" in data

    def test_cost_values_positive(self, client):
        payload = {"topology_yaml": "services:\n  - name: api"}
        resp = client.post("/api/v1/cost/analyze", json=payload)
        data = resp.json()
        assert data["expected_annual_cost"] > 0
        assert data["worst_case_annual_cost"] > 0

    def test_cost_worst_case_gte_expected(self, client):
        payload = {"topology_yaml": "services:\n  - name: api"}
        resp = client.post("/api/v1/cost/analyze", json=payload)
        data = resp.json()
        assert data["worst_case_annual_cost"] >= data["expected_annual_cost"]

    def test_cost_top_scenarios_not_empty(self, client):
        payload = {"topology_yaml": "services:\n  - name: api"}
        resp = client.post("/api/v1/cost/analyze", json=payload)
        data = resp.json()
        assert len(data["top_scenarios"]) > 0

    def test_cost_missing_topology_returns_422(self, client):
        resp = client.post("/api/v1/cost/analyze", json={})
        assert resp.status_code == 422

    def test_cost_custom_revenue(self, client):
        payload = {
            "topology_yaml": "services:\n  - name: api",
            "revenue_per_hour": 50000,
            "incidents_per_year": 6,
        }
        resp = client.post("/api/v1/cost/analyze", json=payload)
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# OpenAPI / Documentation endpoints
# ---------------------------------------------------------------------------

class TestOpenAPIDocs:
    """Tests for OpenAPI schema and documentation endpoints."""

    def test_openapi_json_accessible(self, client):
        resp = client.get("/openapi.json")
        assert resp.status_code == 200

    def test_openapi_json_valid_schema(self, client):
        resp = client.get("/openapi.json")
        data = resp.json()
        assert "openapi" in data
        assert "info" in data
        assert "paths" in data

    def test_openapi_title(self, client):
        resp = client.get("/openapi.json")
        data = resp.json()
        assert data["info"]["title"] == "FaultRay API"

    def test_openapi_version(self, client):
        resp = client.get("/openapi.json")
        data = resp.json()
        assert data["info"]["version"] == "10.3.0"

    def test_openapi_contact_info(self, client):
        resp = client.get("/openapi.json")
        data = resp.json()
        contact = data["info"]["contact"]
        assert contact["name"] == "FaultRay Support"
        assert contact["url"].rstrip("/") == "https://faultray.com"
        assert contact["email"] == "support@faultray.com"

    def test_openapi_license_info(self, client):
        resp = client.get("/openapi.json")
        data = resp.json()
        lic = data["info"]["license"]
        assert lic["name"] == "MIT"

    def test_openapi_tags_present(self, client):
        resp = client.get("/openapi.json")
        data = resp.json()
        assert "tags" in data
        tag_names = [t["name"] for t in data["tags"]]
        assert "simulation" in tag_names
        assert "health" in tag_names
        assert "compliance" in tag_names
        assert "cost" in tag_names

    def test_openapi_paths_include_v1(self, client):
        resp = client.get("/openapi.json")
        data = resp.json()
        paths = list(data["paths"].keys())
        assert "/api/v1/health" in paths
        assert "/api/v1/simulate" in paths
        assert "/api/v1/compliance/assess" in paths
        assert "/api/v1/cost/analyze" in paths

    def test_openapi_description_contains_features(self, client):
        resp = client.get("/openapi.json")
        data = resp.json()
        desc = data["info"]["description"]
        assert "chaos" in desc.lower()
        assert "simulation" in desc.lower() or "simulate" in desc.lower()

    def test_swagger_ui_accessible(self, client):
        resp = client.get("/docs")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")

    def test_redoc_accessible(self, client):
        resp = client.get("/redoc")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")

    def test_openapi_compliance_schema_has_request_body(self, client):
        resp = client.get("/openapi.json")
        data = resp.json()
        compliance_path = data["paths"]["/api/v1/compliance/assess"]["post"]
        assert "requestBody" in compliance_path

    def test_openapi_health_is_get(self, client):
        resp = client.get("/openapi.json")
        data = resp.json()
        assert "get" in data["paths"]["/api/v1/health"]
