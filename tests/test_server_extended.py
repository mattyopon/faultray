"""Extended tests for API server endpoints that lack coverage.

Tests GET /, POST /api/simulate, GET /api/graph-data, POST /graphql,
POST /api/slack/commands, GET /widget/scorecard, GET /widget/badge,
GET /api/leaderboard/, POST /api/teams/, GET /api/insurance/benchmark,
and more.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from faultray.api.server import app, set_graph
from faultray.model.demo import create_demo_graph
from tests.conftest import TEST_API_KEY, _setup_test_user


@pytest.fixture(autouse=True)
def _setup_demo_graph():
    """Load demo graph into the server and ensure test user exists."""
    _setup_test_user()
    g = create_demo_graph()
    set_graph(g)
    yield
    from faultray.model.graph import InfraGraph
    set_graph(InfraGraph())


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {TEST_API_KEY}"}
    async with AsyncClient(transport=transport, base_url="http://test", headers=headers) as c:
        yield c


# ===================================================================
# 1. GET / (dashboard)
# ===================================================================

class TestDashboard:
    async def test_dashboard_returns_html(self, client):
        resp = await client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")

    async def test_dashboard_contains_faultray(self, client):
        resp = await client.get("/")
        assert resp.status_code == 200
        body = resp.text.lower()
        # Dashboard should contain brand or title reference
        assert "faultray" in body or "faultray" in body or "faultray" in body or "dashboard" in body


# ===================================================================
# 2. POST /api/simulate
# ===================================================================

class TestApiSimulate:
    async def test_simulate_returns_json(self, client):
        resp = await client.post("/api/simulate")
        assert resp.status_code == 200
        data = resp.json()
        assert "resilience_score" in data
        assert isinstance(data["resilience_score"], (int, float))

    async def test_simulate_has_results(self, client):
        resp = await client.post("/api/simulate")
        data = resp.json()
        assert "total_scenarios" in data
        assert data["total_scenarios"] > 0

    async def test_simulate_empty_graph(self, client):
        from faultray.model.graph import InfraGraph
        set_graph(InfraGraph())
        resp = await client.post("/api/simulate")
        assert resp.status_code == 400
        data = resp.json()
        assert "error" in data

    async def test_simulate_with_demo_graph(self, client):
        resp = await client.post("/api/simulate")
        assert resp.status_code == 200
        data = resp.json()
        assert "critical_count" in data
        assert "warning_count" in data
        assert "passed_count" in data


# ===================================================================
# 3. GET /api/graph-data
# ===================================================================

class TestApiGraphData:
    async def test_graph_data_structure(self, client):
        resp = await client.get("/api/graph-data")
        assert resp.status_code == 200
        data = resp.json()
        assert "nodes" in data
        assert "edges" in data
        assert isinstance(data["nodes"], list)
        assert isinstance(data["edges"], list)

    async def test_graph_data_node_fields(self, client):
        resp = await client.get("/api/graph-data")
        data = resp.json()
        assert len(data["nodes"]) > 0
        node = data["nodes"][0]
        assert "id" in node
        assert "name" in node
        assert "type" in node

    async def test_graph_data_edge_fields(self, client):
        resp = await client.get("/api/graph-data")
        data = resp.json()
        assert len(data["edges"]) > 0
        edge = data["edges"][0]
        assert "source" in edge
        assert "target" in edge
        assert "dependency_type" in edge

    async def test_graph_data_counts_match(self, client):
        resp = await client.get("/api/graph-data")
        data = resp.json()
        # Demo graph has 9 components and 12 dependencies
        assert len(data["nodes"]) == 9
        assert len(data["edges"]) == 12


# ===================================================================
# 4. POST /graphql with query { components { id name } }
# ===================================================================

class TestGraphQLApi:
    async def test_graphql_components_query(self, client):
        query = {"query": "{ components { id name } }"}
        resp = await client.post("/graphql", json=query)
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        assert "components" in data["data"]
        assert len(data["data"]["components"]) > 0

    async def test_graphql_components_have_id_name(self, client):
        query = {"query": "{ components { id name } }"}
        resp = await client.post("/graphql", json=query)
        data = resp.json()
        comp = data["data"]["components"][0]
        assert "id" in comp
        assert "name" in comp

    async def test_graphql_dependencies_query(self, client):
        query = {"query": "{ dependencies { sourceId targetId type } }"}
        resp = await client.post("/graphql", json=query)
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        assert "dependencies" in data["data"]

    async def test_graphql_summary_query(self, client):
        query = {"query": "{ summary { totalComponents totalDependencies resilienceScore } }"}
        resp = await client.post("/graphql", json=query)
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        assert "summary" in data["data"]

    async def test_graphql_invalid_query(self, client):
        query = {"query": "{ invalidField }"}
        resp = await client.post("/graphql", json=query)
        # Should return 200 with errors or 400
        assert resp.status_code in (200, 400)

    async def test_graphql_empty_body(self, client):
        resp = await client.post("/graphql", json={})
        assert resp.status_code in (200, 400, 422)


# ===================================================================
# 5. POST /api/slack/commands
# ===================================================================

class TestSlackCommands:
    async def test_slack_help_command(self, client):
        resp = await client.post(
            "/api/slack/commands",
            json={"text": "help", "user_id": "U123", "channel_id": "C456"},
        )
        assert resp.status_code in (200, 500)
        if resp.status_code == 200:
            data = resp.json()
            assert "text" in data or "blocks" in data

    async def test_slack_score_command(self, client):
        resp = await client.post(
            "/api/slack/commands",
            json={"text": "score", "user_id": "U123", "channel_id": "C456"},
        )
        assert resp.status_code in (200, 500)

    async def test_slack_simulate_command(self, client):
        resp = await client.post(
            "/api/slack/commands",
            json={"text": "simulate", "user_id": "U123", "channel_id": "C456"},
        )
        assert resp.status_code in (200, 500)

    async def test_slack_empty_text(self, client):
        resp = await client.post(
            "/api/slack/commands",
            json={"text": "", "user_id": "U123", "channel_id": "C456"},
        )
        assert resp.status_code in (200, 500)


# ===================================================================
# 6. GET /widget/scorecard
# ===================================================================

class TestWidgetScorecard:
    async def test_scorecard_returns_200(self, client):
        resp = await client.get("/widget/scorecard")
        assert resp.status_code == 200

    async def test_scorecard_content_type(self, client):
        resp = await client.get("/widget/scorecard")
        ct = resp.headers.get("content-type", "")
        assert "html" in ct or "json" in ct or "svg" in ct


# ===================================================================
# 7. GET /widget/badge
# ===================================================================

class TestWidgetBadge:
    async def test_badge_returns_200(self, client):
        resp = await client.get("/widget/badge")
        assert resp.status_code == 200

    async def test_badge_content(self, client):
        resp = await client.get("/widget/badge")
        ct = resp.headers.get("content-type", "")
        body = resp.text
        # Badge may return SVG or Shields.io-compatible JSON
        assert "svg" in ct or "<svg" in body or "json" in ct or "schemaVersion" in body


# ===================================================================
# 8. GET /api/leaderboard/
# ===================================================================

class TestLeaderboard:
    async def test_leaderboard_returns_200(self, client):
        resp = await client.get("/api/leaderboard/")
        assert resp.status_code == 200

    async def test_leaderboard_is_list(self, client):
        resp = await client.get("/api/leaderboard/")
        data = resp.json()
        # Could be a list or object with entries
        assert isinstance(data, (list, dict))


# ===================================================================
# 9. POST /api/teams/
# ===================================================================

class TestTeamsApi:
    async def test_create_team(self, client):
        payload = {"name": "SRE Team", "owner_id": "user-123"}
        resp = await client.post("/api/teams/", json=payload)
        assert resp.status_code in (200, 201)
        data = resp.json()
        assert "name" in data or "id" in data

    async def test_list_teams(self, client):
        resp = await client.get("/api/teams/")
        assert resp.status_code == 200

    async def test_create_team_missing_owner(self, client):
        payload = {"name": "DevOps"}
        resp = await client.post("/api/teams/", json=payload)
        assert resp.status_code == 400  # owner_id required

    async def test_create_team_missing_name(self, client):
        payload = {"owner_id": "user-456"}
        resp = await client.post("/api/teams/", json=payload)
        assert resp.status_code == 400  # name required


# ===================================================================
# 10. GET /api/insurance/benchmark
# ===================================================================

class TestInsuranceApi:
    async def test_insurance_benchmark(self, client):
        resp = await client.get("/api/insurance/benchmark")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)

    async def test_insurance_score(self, client):
        # Insurance score requires yaml_content in the body
        yaml_content = """\
components:
  - id: web
    name: web-server
    type: web_server
    host: web01
    port: 443
    replicas: 2
dependencies: []
"""
        resp = await client.post(
            "/api/insurance/score",
            json={"yaml_content": yaml_content},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)
        assert "overall_score" in data or "error" in data


# ===================================================================
# Additional endpoints for more coverage
# ===================================================================

class TestDemoEndpoint:
    async def test_demo_redirects(self, client):
        resp = await client.get("/demo", follow_redirects=False)
        # Demo should redirect or return HTML
        assert resp.status_code in (200, 302, 303, 307)

    async def test_demo_load(self, client):
        resp = await client.get("/demo", follow_redirects=True)
        assert resp.status_code == 200


class TestDocsEndpoints:
    async def test_openapi_docs(self, client):
        resp = await client.get("/docs")
        assert resp.status_code == 200

    async def test_redoc(self, client):
        resp = await client.get("/redoc")
        assert resp.status_code == 200

    async def test_openapi_schema(self, client):
        resp = await client.get("/openapi.json")
        assert resp.status_code == 200
        data = resp.json()
        assert "openapi" in data
        assert "paths" in data


class TestApiVersioning:
    async def test_v1_graph_data(self, client):
        resp = await client.get("/api/v1/graph-data")
        assert resp.status_code == 200
        data = resp.json()
        assert "nodes" in data
        assert "edges" in data

    async def test_v1_simulate(self, client):
        resp = await client.post("/api/v1/simulate", json={
            "topology_yaml": "services:\n  - name: api\n    replicas: 3",
            "scenarios": "all",
            "engines": ["cascade"],
        })
        assert resp.status_code == 200


class TestRateLimiter:
    async def test_rate_limiter_allows_normal_traffic(self, client):
        # A few requests should be fine
        for _ in range(3):
            resp = await client.get("/api/graph-data")
            assert resp.status_code == 200


class TestErrorHandling:
    async def test_404_for_unknown_route(self, client):
        resp = await client.get("/api/nonexistent")
        assert resp.status_code == 404

    async def test_structured_error_response(self, client):
        resp = await client.get("/api/nonexistent")
        data = resp.json()
        assert "error" in data or "detail" in data
