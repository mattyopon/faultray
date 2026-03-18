"""Tests for the FastAPI web server endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from faultray.api.server import app, build_demo_graph, get_graph, set_graph
from faultray.model.demo import create_demo_graph
from faultray.model.graph import InfraGraph


@pytest.fixture(autouse=True)
def _reset_graph():
    """Reset the server graph state before and after each test."""
    set_graph(None)
    yield
    set_graph(None)


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def demo_client(client):
    """Create a test client with demo data preloaded."""
    graph = create_demo_graph()
    set_graph(graph)
    return client


# ---------------------------------------------------------------------------
# Dashboard / HTML routes
# ---------------------------------------------------------------------------

class TestDashboard:
    def test_root_returns_200(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")

    def test_root_with_demo_data(self, demo_client):
        resp = demo_client.get("/")
        assert resp.status_code == 200

    def test_docs_endpoint(self, client):
        resp = client.get("/docs")
        assert resp.status_code == 200

    def test_redoc_endpoint(self, client):
        resp = client.get("/redoc")
        assert resp.status_code == 200

    def test_openapi_json(self, client):
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        data = resp.json()
        assert "paths" in data
        assert "info" in data

    def test_components_page(self, demo_client):
        resp = demo_client.get("/components")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")

    def test_simulation_page(self, client):
        resp = client.get("/simulation")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")

    def test_graph_page(self, client):
        resp = client.get("/graph")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")

    def test_analyze_page_no_data(self, client):
        resp = client.get("/analyze")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")

    def test_analyze_page_with_demo(self, demo_client):
        resp = demo_client.get("/analyze")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")
        assert "AI Analysis" in resp.text or "analyze" in resp.text.lower()


# ---------------------------------------------------------------------------
# Analyze API endpoint
# ---------------------------------------------------------------------------

class TestAnalyzeAPI:
    def test_api_analyze_no_data(self, client):
        resp = client.get("/api/analyze")
        assert resp.status_code == 400
        data = resp.json()
        assert "error" in data

    def test_api_analyze_with_demo(self, demo_client):
        resp = demo_client.get("/api/analyze")
        assert resp.status_code == 200
        data = resp.json()
        assert "summary" in data
        assert "recommendations" in data
        assert "estimated_current_nines" in data
        assert "theoretical_max_nines" in data
        assert "top_risks" in data
        assert "availability_assessment" in data
        assert "upgrade_path" in data


# ---------------------------------------------------------------------------
# Demo endpoint
# ---------------------------------------------------------------------------

class TestDemo:
    def test_demo_redirects(self, client):
        resp = client.get("/demo", follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers.get("location") == "/"

    def test_demo_loads_data(self, client):
        # First hit /demo to load data
        client.get("/demo", follow_redirects=False)
        # Then check that graph data is populated
        resp = client.get("/api/graph-data")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["nodes"]) > 0
        assert len(data["edges"]) > 0


# ---------------------------------------------------------------------------
# Simulation endpoints
# ---------------------------------------------------------------------------

class TestSimulation:
    def test_simulation_run_no_data(self, client):
        resp = client.get("/simulation/run")
        assert resp.status_code == 400
        data = resp.json()
        assert "error" in data

    def test_simulation_run_with_demo(self, demo_client):
        resp = demo_client.get("/simulation/run")
        assert resp.status_code == 200
        data = resp.json()
        assert "resilience_score" in data
        assert "total_scenarios" in data
        assert "critical_count" in data

    def test_api_simulate_post_no_data(self, client):
        resp = client.post("/api/simulate")
        assert resp.status_code == 400
        data = resp.json()
        assert "error" in data

    def test_api_simulate_post_with_demo(self, demo_client):
        resp = demo_client.post("/api/simulate")
        assert resp.status_code == 200
        data = resp.json()
        assert "resilience_score" in data
        assert "critical" in data
        assert "warnings" in data
        assert "passed" in data


# ---------------------------------------------------------------------------
# Graph data endpoint
# ---------------------------------------------------------------------------

class TestGraphData:
    def test_graph_data_empty(self, client):
        resp = client.get("/api/graph-data")
        assert resp.status_code == 200
        data = resp.json()
        assert data["nodes"] == []
        assert data["edges"] == []

    def test_graph_data_with_demo(self, demo_client):
        resp = demo_client.get("/api/graph-data")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["nodes"]) == 9  # Demo has 9 components
        assert len(data["edges"]) > 0

        # Verify node structure
        node = data["nodes"][0]
        assert "id" in node
        assert "name" in node
        assert "type" in node
        assert "health" in node
        assert "utilization" in node

        # Verify edge structure
        edge = data["edges"][0]
        assert "source" in edge
        assert "target" in edge
        assert "dependency_type" in edge


# ---------------------------------------------------------------------------
# Runs CRUD endpoints
# ---------------------------------------------------------------------------

class TestRuns:
    def test_list_runs_empty(self, client):
        resp = client.get("/api/runs")
        assert resp.status_code == 200
        data = resp.json()
        assert "runs" in data

    def test_get_run_not_found(self, client):
        resp = client.get("/api/runs/99999")
        # Will be 404 if DB is working, or 503 if not
        assert resp.status_code in (404, 503)

    def test_delete_run_not_found(self, client):
        resp = client.delete("/api/runs/99999")
        assert resp.status_code in (404, 503)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_get_graph_returns_empty_if_none(self):
        set_graph(None)
        graph = get_graph()
        assert isinstance(graph, InfraGraph)
        assert len(graph.components) == 0

    def test_set_and_get_graph(self):
        demo = create_demo_graph()
        set_graph(demo)
        graph = get_graph()
        assert len(graph.components) == 9

    def test_build_demo_graph(self):
        graph = build_demo_graph()
        assert isinstance(graph, InfraGraph)
        assert len(graph.components) == 9
