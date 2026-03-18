"""Tests for API documentation page, versioning, and health endpoints."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from faultray.api.server import app, set_graph
from faultray.model.demo import create_demo_graph
from tests.conftest import TEST_API_KEY, _setup_test_user


@pytest.fixture(autouse=True)
def _reset_graph():
    """Reset the server graph state before and after each test."""
    _setup_test_user()
    set_graph(None)
    yield
    set_graph(None)


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app, raise_server_exceptions=False, headers={"Authorization": f"Bearer {TEST_API_KEY}"})


@pytest.fixture
def demo_client(client):
    """Create a test client with demo data preloaded."""
    graph = create_demo_graph()
    set_graph(graph)
    return client


# ---------------------------------------------------------------------------
# API Documentation Page
# ---------------------------------------------------------------------------

class TestAPIDocsPage:
    """Tests for the interactive API documentation page."""

    def test_api_docs_returns_200(self, client):
        resp = client.get("/api-docs")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")

    def test_api_docs_contains_title(self, client):
        resp = client.get("/api-docs")
        assert "FaultRay API" in resp.text

    def test_api_docs_contains_endpoint_groups(self, client):
        resp = client.get("/api-docs")
        body = resp.text
        assert "Infrastructure" in body
        assert "Simulation" in body
        assert "Analysis" in body
        assert "Compliance" in body
        assert "Incidents" in body
        assert "Marketplace" in body
        assert "Calendar" in body
        assert "Badges" in body
        assert "Chat" in body
        assert "Export" in body

    def test_api_docs_contains_endpoints(self, client):
        resp = client.get("/api-docs")
        body = resp.text
        assert "/api/topology" in body
        assert "/api/simulate-failure/" in body
        assert "/api/whatif/calculate" in body
        assert "/api/score-history" in body
        assert "/api/compliance/" in body
        assert "/api/chat" in body
        assert "/api/health" in body

    def test_api_docs_contains_auth_section(self, client):
        resp = client.get("/api-docs")
        assert "Authentication" in resp.text
        assert "Authorization" in resp.text

    def test_api_docs_contains_rate_limit_info(self, client):
        resp = client.get("/api-docs")
        assert "Rate Limit" in resp.text

    def test_api_docs_contains_response_codes(self, client):
        resp = client.get("/api-docs")
        body = resp.text
        assert "200" in body
        assert "429" in body
        assert "404" in body

    def test_api_docs_contains_code_examples(self, client):
        resp = client.get("/api-docs")
        body = resp.text
        assert "curl" in body.lower()
        assert "python" in body.lower() or "Python" in body
        assert "javascript" in body.lower() or "JavaScript" in body

    def test_api_docs_is_self_contained(self, client):
        """The page should not reference external CSS/JS files (except htmx which is already in base)."""
        resp = client.get("/api-docs")
        body = resp.text
        # Should contain inline styles
        assert "<style>" in body
        # Should contain inline scripts
        assert "<script>" in body

    def test_api_docs_has_copy_buttons(self, client):
        resp = client.get("/api-docs")
        assert "copyCode" in resp.text or "copy-btn" in resp.text

    def test_api_docs_has_search_input(self, client):
        resp = client.get("/api-docs")
        assert "searchInput" in resp.text or "search" in resp.text.lower()


# ---------------------------------------------------------------------------
# API Health Endpoint
# ---------------------------------------------------------------------------

class TestAPIHealth:
    """Tests for the /api/health endpoint."""

    def test_health_returns_200(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200

    def test_health_returns_json(self, client):
        resp = client.get("/api/health")
        data = resp.json()
        assert data["status"] == "healthy"

    def test_health_contains_version(self, client):
        resp = client.get("/api/health")
        data = resp.json()
        assert "version" in data
        assert isinstance(data["version"], str)

    def test_health_contains_uptime(self, client):
        resp = client.get("/api/health")
        data = resp.json()
        assert "uptime" in data
        assert "uptime_seconds" in data
        assert isinstance(data["uptime_seconds"], (int, float))

    def test_health_shows_zero_components_when_empty(self, client):
        resp = client.get("/api/health")
        data = resp.json()
        assert data["components_loaded"] == 0

    def test_health_shows_component_count_with_demo(self, demo_client):
        resp = demo_client.get("/api/health")
        data = resp.json()
        assert data["components_loaded"] > 0

    def test_health_contains_api_versions(self, client):
        resp = client.get("/api/health")
        data = resp.json()
        assert "api_versions" in data
        assert isinstance(data["api_versions"], list)
        assert len(data["api_versions"]) >= 2  # v1 and v2

    def test_health_contains_rate_limit_tiers(self, client):
        resp = client.get("/api/health")
        data = resp.json()
        assert "rate_limit_tiers" in data
        assert "free" in data["rate_limit_tiers"]
        assert "enterprise" in data["rate_limit_tiers"]

    def test_health_contains_timestamp(self, client):
        resp = client.get("/api/health")
        data = resp.json()
        assert "timestamp" in data


# ---------------------------------------------------------------------------
# API Versions Endpoint
# ---------------------------------------------------------------------------

class TestAPIVersions:
    """Tests for the /api/versions endpoint."""

    def test_versions_returns_200(self, client):
        resp = client.get("/api/versions")
        assert resp.status_code == 200

    def test_versions_lists_v1_and_v2(self, client):
        resp = client.get("/api/versions")
        data = resp.json()
        assert "versions" in data
        version_names = [v["version"] for v in data["versions"]]
        assert "v1" in version_names
        assert "v2" in version_names

    def test_versions_contain_status(self, client):
        resp = client.get("/api/versions")
        data = resp.json()
        for v in data["versions"]:
            assert "status" in v
            assert v["status"] in ("stable", "beta", "deprecated")

    def test_versions_contain_changelog(self, client):
        resp = client.get("/api/versions")
        data = resp.json()
        for v in data["versions"]:
            assert "changelog" in v
            assert isinstance(v["changelog"], list)

    def test_v1_is_stable(self, client):
        resp = client.get("/api/versions")
        data = resp.json()
        v1 = next((v for v in data["versions"] if v["version"] == "v1"), None)
        assert v1 is not None
        assert v1["status"] == "stable"


# ---------------------------------------------------------------------------
# API Versioning Module
# ---------------------------------------------------------------------------

class TestAPIVersioningModule:
    """Unit tests for the api_versioning module."""

    def test_rate_limiter_allows_requests(self):
        from faultray.api.api_versioning import RateLimiter

        rl = RateLimiter(window_seconds=60)
        assert rl.check_limit("test-key") is True

    def test_rate_limiter_blocks_excess(self):
        from faultray.api.api_versioning import RateLimiter

        rl = RateLimiter(window_seconds=60)
        rl._tiers["test-key"] = "free"  # 30 req/min
        for _ in range(30):
            assert rl.check_limit("test-key") is True
        # 31st request should be blocked
        assert rl.check_limit("test-key") is False

    def test_rate_limiter_get_remaining(self):
        from faultray.api.api_versioning import RateLimiter

        rl = RateLimiter(window_seconds=60)
        # Default free tier = 30
        assert rl.get_remaining("new-key") == 30
        rl.check_limit("new-key")
        assert rl.get_remaining("new-key") == 29

    def test_rate_limiter_set_tier(self):
        from faultray.api.api_versioning import RateLimiter

        rl = RateLimiter(window_seconds=60)
        rl.set_tier("pro-key", "pro")
        assert rl._limit_for("pro-key") == 600

    def test_rate_limiter_invalid_tier(self):
        from faultray.api.api_versioning import RateLimiter

        rl = RateLimiter(window_seconds=60)
        with pytest.raises(ValueError, match="Unknown tier"):
            rl.set_tier("key", "nonexistent")

    def test_rate_limiter_reset_time(self):
        from faultray.api.api_versioning import RateLimiter

        rl = RateLimiter(window_seconds=60)
        rl.check_limit("time-key")
        reset = rl.reset_time("time-key")
        assert reset is not None

    def test_rate_limiter_usage_tracking(self):
        from faultray.api.api_versioning import RateLimiter

        rl = RateLimiter(window_seconds=60)
        assert rl.get_usage("usage-key") == 0
        rl.check_limit("usage-key")
        rl.check_limit("usage-key")
        assert rl.get_usage("usage-key") == 2

    def test_api_version_dataclass(self):
        from faultray.api.api_versioning import APIVersion

        v = APIVersion(
            version="v3",
            status="beta",
            release_date="2026-06-01",
            changelog=["New feature"],
        )
        assert v.version == "v3"
        assert v.deprecation_date is None

    def test_health_check(self):
        from faultray.api.api_versioning import APIHealthCheck

        hc = APIHealthCheck(version="1.0.0-test")
        result = hc.check(component_count=5)
        assert result["status"] == "healthy"
        assert result["version"] == "1.0.0-test"
        assert result["components_loaded"] == 5
        assert result["uptime_seconds"] >= 0

    def test_list_versions(self):
        from faultray.api.api_versioning import list_versions

        versions = list_versions()
        assert len(versions) >= 2
        assert all("version" in v for v in versions)


# ---------------------------------------------------------------------------
# Sidebar API Docs Link
# ---------------------------------------------------------------------------

class TestSidebarAPIDocsLink:
    """Test that the API Docs link appears in the sidebar."""

    def test_dashboard_has_api_docs_link(self, client):
        resp = client.get("/")
        assert "api-docs" in resp.text.lower() or "/api-docs" in resp.text
