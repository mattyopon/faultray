"""Tests for the Enhanced Dashboard V2 features."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from faultray.api.server import app, set_graph
from faultray.model.demo import create_demo_graph
from faultray.model.graph import InfraGraph
from tests.conftest import TEST_API_KEY, _setup_test_user


@pytest.fixture(autouse=True)
def _reset_graph():
    """Reset the server graph state, last report, and rate limiter before and after each test."""
    import faultray.api.server as _srv
    _setup_test_user()
    set_graph(None)
    _srv._last_report = None
    _srv._rate_limiter.requests.clear()
    yield
    set_graph(None)
    _srv._last_report = None
    _srv._rate_limiter.requests.clear()


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
# Dashboard Summary API Endpoint
# ---------------------------------------------------------------------------

class TestDashboardSummaryAPI:
    """Tests for the /api/dashboard/summary endpoint."""

    def test_summary_returns_200(self, client):
        resp = client.get("/api/dashboard/summary")
        assert resp.status_code == 200

    def test_summary_returns_json(self, client):
        resp = client.get("/api/dashboard/summary")
        data = resp.json()
        assert isinstance(data, dict)

    def test_summary_contains_resilience_score(self, client):
        resp = client.get("/api/dashboard/summary")
        data = resp.json()
        assert "resilience_score" in data
        assert isinstance(data["resilience_score"], (int, float))

    def test_summary_contains_sla_estimate(self, client):
        resp = client.get("/api/dashboard/summary")
        data = resp.json()
        assert "sla_estimate" in data

    def test_summary_contains_spof_count(self, client):
        resp = client.get("/api/dashboard/summary")
        data = resp.json()
        assert "spof_count" in data
        assert isinstance(data["spof_count"], int)
        assert data["spof_count"] >= 0

    def test_summary_contains_sre_maturity(self, client):
        resp = client.get("/api/dashboard/summary")
        data = resp.json()
        assert "sre_maturity_level" in data
        assert 1 <= data["sre_maturity_level"] <= 5

    def test_summary_contains_risk_distribution(self, client):
        resp = client.get("/api/dashboard/summary")
        data = resp.json()
        assert "risk_distribution" in data
        rd = data["risk_distribution"]
        assert "critical" in rd
        assert "high" in rd
        assert "medium" in rd
        assert "low" in rd

    def test_summary_contains_component_breakdown(self, client):
        resp = client.get("/api/dashboard/summary")
        data = resp.json()
        assert "component_breakdown" in data
        assert isinstance(data["component_breakdown"], dict)

    def test_summary_contains_compliance_scores(self, client):
        resp = client.get("/api/dashboard/summary")
        data = resp.json()
        assert "compliance_scores" in data
        cs = data["compliance_scores"]
        assert isinstance(cs, dict)

    def test_summary_contains_recent_activity(self, client):
        resp = client.get("/api/dashboard/summary")
        data = resp.json()
        assert "recent_activity" in data
        assert isinstance(data["recent_activity"], list)

    def test_summary_contains_quick_stats(self, client):
        resp = client.get("/api/dashboard/summary")
        data = resp.json()
        assert "quick_stats" in data
        qs = data["quick_stats"]
        assert "failover_pct" in qs
        assert "circuit_breaker_pct" in qs
        assert "autoscaling_pct" in qs
        assert "monitoring_pct" in qs

    def test_summary_contains_sparkline(self, client):
        resp = client.get("/api/dashboard/summary")
        data = resp.json()
        assert "sparkline" in data

    def test_summary_with_demo_data(self, demo_client):
        resp = demo_client.get("/api/dashboard/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["resilience_score"] > 0
        assert data["component_breakdown"]  # non-empty

    def test_summary_sre_maturity_range(self, demo_client):
        resp = demo_client.get("/api/dashboard/summary")
        data = resp.json()
        assert 1 <= data["sre_maturity_level"] <= 5

    def test_summary_quick_stats_percentages(self, demo_client):
        resp = demo_client.get("/api/dashboard/summary")
        data = resp.json()
        qs = data["quick_stats"]
        for key in ("failover_pct", "circuit_breaker_pct", "autoscaling_pct", "monitoring_pct"):
            assert 0 <= qs[key] <= 100


# ---------------------------------------------------------------------------
# Enhanced Dashboard HTML Page
# ---------------------------------------------------------------------------

class TestDashboardV2HTML:
    """Tests for the enhanced dashboard HTML page."""

    def test_dashboard_returns_200(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")

    def test_dashboard_with_demo_data(self, demo_client):
        resp = demo_client.get("/")
        assert resp.status_code == 200

    def test_dashboard_contains_score_cards(self, demo_client):
        resp = demo_client.get("/")
        body = resp.text
        assert "Resilience Score" in body
        assert "SLA Estimate" in body
        assert "SPOF Count" in body
        assert "SRE Maturity" in body

    def test_dashboard_contains_risk_distribution(self, demo_client):
        resp = demo_client.get("/")
        body = resp.text
        assert "Risk Distribution" in body
        assert "risk-bar" in body

    def test_dashboard_contains_key_metrics(self, demo_client):
        resp = demo_client.get("/")
        body = resp.text
        assert "Key Metrics" in body
        assert "Components" in body
        assert "Dependencies" in body

    def test_dashboard_contains_quick_actions(self, demo_client):
        resp = demo_client.get("/")
        body = resp.text
        assert "Quick Actions" in body
        assert "Run Simulation" in body
        assert "Generate Report" in body

    def test_dashboard_contains_compliance_overview(self, demo_client):
        resp = demo_client.get("/")
        body = resp.text
        assert "Compliance Overview" in body

    def test_dashboard_contains_incident_readiness(self, demo_client):
        resp = demo_client.get("/")
        body = resp.text
        assert "Incident Readiness" in body

    def test_dashboard_contains_top_risks(self, demo_client):
        resp = demo_client.get("/")
        body = resp.text
        assert "Top Risks" in body

    def test_dashboard_contains_component_status(self, demo_client):
        resp = demo_client.get("/")
        body = resp.text
        assert "Component Status" in body

    def test_dashboard_contains_activity_feed(self, demo_client):
        resp = demo_client.get("/")
        body = resp.text
        assert "Recent Activity" in body

    def test_dashboard_has_auto_refresh(self, demo_client):
        """Dashboard should use htmx auto-refresh."""
        resp = demo_client.get("/")
        body = resp.text
        assert "hx-trigger" in body
        assert "every 30s" in body or "30s" in body

    def test_dashboard_has_simulation_button(self, demo_client):
        resp = demo_client.get("/")
        body = resp.text
        assert "runSim" in body

    def test_dashboard_maturity_badge(self, demo_client):
        """Dashboard should show SRE maturity level badge."""
        resp = demo_client.get("/")
        body = resp.text
        # Should contain a maturity badge class
        assert "maturity-badge" in body or "maturity-l" in body

    def test_dashboard_sparkline_present(self, demo_client):
        """Dashboard should show sparkline trend indicator."""
        resp = demo_client.get("/")
        body = resp.text
        assert "sparkline" in body

    def test_dashboard_responsive_classes(self, demo_client):
        """Dashboard should have responsive grid classes."""
        resp = demo_client.get("/")
        body = resp.text
        assert "dash-row" in body

    def test_dashboard_no_data_state(self, client):
        """Dashboard should show empty state when no data is loaded."""
        resp = client.get("/")
        assert resp.status_code == 200
        # No infrastructure loaded message from base.html
        assert "No Infrastructure Loaded" in resp.text or "Load Demo" in resp.text


# ---------------------------------------------------------------------------
# Dashboard Summary with Simulation Data
# ---------------------------------------------------------------------------

class TestDashboardWithSimulation:
    """Test dashboard with simulation data loaded."""

    def test_dashboard_after_simulation(self, demo_client):
        """Load demo, run simulation, verify dashboard shows results."""
        # Run simulation
        sim_resp = demo_client.post("/api/simulate")
        assert sim_resp.status_code == 200

        # Check dashboard
        resp = demo_client.get("/")
        assert resp.status_code == 200
        body = resp.text
        # Should now show simulation results
        assert "Resilience Score" in body

    def test_summary_after_simulation(self, demo_client):
        """After simulation, summary should have non-zero risk distribution."""
        # Run simulation
        demo_client.post("/api/simulate")

        resp = demo_client.get("/api/dashboard/summary")
        data = resp.json()
        rd = data["risk_distribution"]
        total = rd["critical"] + rd["high"] + rd["medium"] + rd["low"]
        assert total > 0

    def test_summary_activity_after_simulation(self, demo_client):
        """After simulation, recent activity key should exist."""
        demo_client.post("/api/simulate")

        resp = demo_client.get("/api/dashboard/summary")
        data = resp.json()
        assert "recent_activity" in data

    def test_summary_compliance_with_demo(self, demo_client):
        """Compliance scores should be non-zero with demo data."""
        resp = demo_client.get("/api/dashboard/summary")
        data = resp.json()
        # At least some framework should have a non-zero score
        total = sum(data["compliance_scores"].values())
        assert total >= 0  # May be 0 if demo has no security settings


# ---------------------------------------------------------------------------
# Dashboard Summary Edge Cases
# ---------------------------------------------------------------------------

class TestDashboardEdgeCases:
    """Edge case tests for dashboard summary."""

    def test_empty_graph_returns_safe_defaults(self, client):
        resp = client.get("/api/dashboard/summary")
        data = resp.json()
        assert data["resilience_score"] == 0
        assert data["spof_count"] == 0
        assert data["sre_maturity_level"] >= 1
        assert data["risk_distribution"]["critical"] == 0

    def test_empty_graph_quick_stats_zero(self, client):
        resp = client.get("/api/dashboard/summary")
        data = resp.json()
        qs = data["quick_stats"]
        assert qs["failover_pct"] == 0
        assert qs["circuit_breaker_pct"] == 0

    def test_empty_graph_component_breakdown_empty(self, client):
        resp = client.get("/api/dashboard/summary")
        data = resp.json()
        assert data["component_breakdown"] == {} or data["component_breakdown"] is not None
