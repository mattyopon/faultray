"""Tests for the GraphQL-like API endpoint."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from faultray.api.server import app, set_graph
from faultray.model.demo import create_demo_graph


@pytest.fixture(autouse=True)
def _reset_graph():
    """Reset the server graph state before and after each test."""
    set_graph(None)
    yield
    set_graph(None)


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def demo_client(client):
    graph = create_demo_graph()
    set_graph(graph)
    return client


# ---------------------------------------------------------------------------
# Query parsing / basic endpoint
# ---------------------------------------------------------------------------


class TestGraphQLEndpoint:
    """Test the /graphql POST endpoint."""

    def test_missing_query_returns_error(self, client):
        resp = client.post("/graphql", json={})
        assert resp.status_code == 400
        data = resp.json()
        assert "errors" in data

    def test_invalid_json_returns_error(self, client):
        resp = client.post(
            "/graphql",
            content="not json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 400

    def test_empty_query_returns_error(self, client):
        resp = client.post("/graphql", json={"query": ""})
        assert resp.status_code == 400

    def test_components_query_empty_graph(self, client):
        resp = client.post("/graphql", json={"query": "{ components { id name type } }"})
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        assert data["data"]["components"] == []


# ---------------------------------------------------------------------------
# Component queries with demo data
# ---------------------------------------------------------------------------


class TestGraphQLComponents:
    """Test component queries with demo infrastructure loaded."""

    def test_components_returns_list(self, demo_client):
        resp = demo_client.post(
            "/graphql",
            json={"query": "{ components { id name type } }"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert isinstance(data["components"], list)
        assert len(data["components"]) > 0

    def test_components_fields_filtered(self, demo_client):
        resp = demo_client.post(
            "/graphql",
            json={"query": "{ components { id name } }"},
        )
        data = resp.json()["data"]
        comp = data["components"][0]
        assert "id" in comp
        assert "name" in comp
        # 'type' should not be present since we did not request it
        assert "type" not in comp

    def test_components_all_fields(self, demo_client):
        resp = demo_client.post(
            "/graphql",
            json={
                "query": "{ components { id name type replicas utilization health host port } }"
            },
        )
        data = resp.json()["data"]
        comp = data["components"][0]
        assert "id" in comp
        assert "name" in comp
        assert "type" in comp
        assert "replicas" in comp
        assert isinstance(comp["replicas"], int)
        assert "utilization" in comp
        assert isinstance(comp["utilization"], (int, float))
        assert "health" in comp


# ---------------------------------------------------------------------------
# Simulation summary
# ---------------------------------------------------------------------------


class TestGraphQLSimulation:
    """Test simulation-related queries."""

    def test_simulation_summary_null_without_run(self, demo_client):
        """simulationSummary should be None before any simulation has run."""
        import faultray.api.server as srv
        srv._last_report = None

        resp = demo_client.post(
            "/graphql",
            json={"query": "{ simulationSummary { resilienceScore totalScenarios } }"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["simulationSummary"] is None

    def test_simulation_summary_after_mutation(self, demo_client):
        """Running the mutation should populate simulationSummary."""
        resp = demo_client.post(
            "/graphql",
            json={
                "query": "mutation { runSimulation { resilienceScore totalScenarios critical warning passed } }"
            },
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        sim = data["runSimulation"]
        assert isinstance(sim["resilienceScore"], (int, float))
        assert isinstance(sim["totalScenarios"], int)
        assert sim["totalScenarios"] > 0

    def test_resilience_score_scalar(self, demo_client):
        """Test the scalar resilienceScore field."""
        # First run the simulation
        demo_client.post(
            "/graphql",
            json={"query": "mutation { runSimulation { resilienceScore } }"},
        )
        resp = demo_client.post(
            "/graphql",
            json={"query": "{ resilienceScore }"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert isinstance(data["resilienceScore"], (int, float))

    def test_resilience_score_v2(self, demo_client):
        """Test the v2 resilience score with breakdown."""
        # Run simulation first
        demo_client.post(
            "/graphql",
            json={"query": "mutation { runSimulation { resilienceScore } }"},
        )
        resp = demo_client.post(
            "/graphql",
            json={"query": "{ resilienceScoreV2 { score breakdown { totalScenarios critical passedRatio } } }"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        v2 = data["resilienceScoreV2"]
        assert "score" in v2
        assert "breakdown" in v2
        assert "totalScenarios" in v2["breakdown"]


# ---------------------------------------------------------------------------
# Availability layers
# ---------------------------------------------------------------------------


class TestGraphQLAvailability:
    """Test availability layer queries."""

    def test_availability_layers(self, demo_client):
        resp = demo_client.post(
            "/graphql",
            json={"query": "{ availabilityLayers { name nines availabilityPercent annualDowntimeSeconds } }"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        layers = data["availabilityLayers"]
        assert isinstance(layers, list)
        assert len(layers) > 0

        layer = layers[0]
        assert "name" in layer
        assert "nines" in layer
        assert isinstance(layer["nines"], (int, float))

    def test_availability_layers_filtered(self, demo_client):
        resp = demo_client.post(
            "/graphql",
            json={"query": "{ availabilityLayers { name nines } }"},
        )
        data = resp.json()["data"]
        layer = data["availabilityLayers"][0]
        assert "name" in layer
        assert "nines" in layer
        # These should not be returned
        assert "availabilityPercent" not in layer
        assert "annualDowntimeSeconds" not in layer


# ---------------------------------------------------------------------------
# Unknown fields
# ---------------------------------------------------------------------------


class TestGraphQLEdgeCases:
    """Test edge cases and unknown fields."""

    def test_unknown_field_returns_null(self, client):
        resp = client.post(
            "/graphql",
            json={"query": "{ unknownField }"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["unknownField"] is None

    def test_multiple_root_fields(self, demo_client):
        """Query multiple root fields at once."""
        # Run simulation first
        demo_client.post(
            "/graphql",
            json={"query": "mutation { runSimulation { resilienceScore } }"},
        )
        resp = demo_client.post(
            "/graphql",
            json={"query": "{ components { id } resilienceScore }"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "components" in data
        assert "resilienceScore" in data
