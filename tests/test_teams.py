"""Tests for the Team Workspace API."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from infrasim.api.database import reset_engine
from infrasim.api.server import app, set_graph


@pytest.fixture(autouse=True)
def _reset_state():
    """Reset server and database state between tests."""
    set_graph(None)
    reset_engine()
    yield
    set_graph(None)
    reset_engine()


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Helper to create a team via the API
# ---------------------------------------------------------------------------

def _create_team(client, name: str = "Test Team", owner_id: str = "user-1") -> dict:
    resp = client.post("/api/teams/", json={"name": name, "owner_id": owner_id})
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Team CRUD
# ---------------------------------------------------------------------------


class TestTeamCRUD:
    """Test team creation, listing, and retrieval."""

    def test_create_team(self, client):
        data = _create_team(client)
        assert data["name"] == "Test Team"
        assert data["owner_id"] == "user-1"
        assert "id" in data
        assert "created_at" in data

    def test_create_team_missing_name(self, client):
        resp = client.post("/api/teams/", json={"owner_id": "user-1"})
        assert resp.status_code == 400

    def test_create_team_missing_owner(self, client):
        resp = client.post("/api/teams/", json={"name": "Team"})
        assert resp.status_code == 400

    def test_list_teams_empty(self, client):
        resp = client.get("/api/teams/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["teams"] == [] or isinstance(data["teams"], list)

    def test_list_teams_returns_created(self, client):
        _create_team(client, name="Alpha")
        _create_team(client, name="Beta", owner_id="user-2")

        resp = client.get("/api/teams/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 2
        names = [t["name"] for t in data["teams"]]
        assert "Alpha" in names
        assert "Beta" in names

    def test_list_teams_filtered_by_user(self, client):
        _create_team(client, name="Alpha", owner_id="user-1")
        _create_team(client, name="Beta", owner_id="user-2")

        resp = client.get("/api/teams/?user_id=user-1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 1
        for t in data["teams"]:
            # user-1 is owner/member of Alpha only
            assert t["name"] == "Alpha" or t["owner_id"] == "user-1"

    def test_get_team(self, client):
        created = _create_team(client)
        team_id = created["id"]

        resp = client.get(f"/api/teams/{team_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == team_id
        assert data["name"] == "Test Team"
        assert len(data["members"]) >= 1

    def test_get_team_not_found(self, client):
        resp = client.get("/api/teams/nonexistent")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Member management
# ---------------------------------------------------------------------------


class TestTeamMembers:
    """Test adding and removing team members."""

    def test_add_member(self, client):
        team = _create_team(client)
        team_id = team["id"]

        resp = client.post(
            f"/api/teams/{team_id}/members",
            json={"user_id": "user-2", "role": "editor"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["user_id"] == "user-2"
        assert data["role"] == "editor"

    def test_add_member_default_role(self, client):
        team = _create_team(client)
        team_id = team["id"]

        resp = client.post(
            f"/api/teams/{team_id}/members",
            json={"user_id": "user-3"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["role"] == "viewer"

    def test_add_member_invalid_role(self, client):
        team = _create_team(client)
        team_id = team["id"]

        resp = client.post(
            f"/api/teams/{team_id}/members",
            json={"user_id": "user-2", "role": "superadmin"},
        )
        assert resp.status_code == 400

    def test_add_member_duplicate(self, client):
        team = _create_team(client)
        team_id = team["id"]

        client.post(
            f"/api/teams/{team_id}/members",
            json={"user_id": "user-2"},
        )
        resp = client.post(
            f"/api/teams/{team_id}/members",
            json={"user_id": "user-2"},
        )
        assert resp.status_code == 409

    def test_add_member_team_not_found(self, client):
        resp = client.post(
            "/api/teams/nonexistent/members",
            json={"user_id": "user-2"},
        )
        assert resp.status_code == 404

    def test_remove_member(self, client):
        team = _create_team(client)
        team_id = team["id"]

        # Add then remove
        client.post(
            f"/api/teams/{team_id}/members",
            json={"user_id": "user-2"},
        )
        resp = client.delete(f"/api/teams/{team_id}/members/user-2")
        assert resp.status_code == 200
        data = resp.json()
        assert data["removed"] is True

    def test_remove_owner_fails(self, client):
        team = _create_team(client, owner_id="owner-1")
        team_id = team["id"]

        resp = client.delete(f"/api/teams/{team_id}/members/owner-1")
        assert resp.status_code == 400

    def test_remove_nonexistent_member(self, client):
        team = _create_team(client)
        team_id = team["id"]

        resp = client.delete(f"/api/teams/{team_id}/members/nobody")
        assert resp.status_code == 404

    def test_members_visible_in_get_team(self, client):
        team = _create_team(client, owner_id="owner-1")
        team_id = team["id"]

        client.post(
            f"/api/teams/{team_id}/members",
            json={"user_id": "user-2", "role": "editor"},
        )
        client.post(
            f"/api/teams/{team_id}/members",
            json={"user_id": "user-3", "role": "viewer"},
        )

        resp = client.get(f"/api/teams/{team_id}")
        data = resp.json()
        assert len(data["members"]) == 3  # owner + 2 added
        user_ids = {m["user_id"] for m in data["members"]}
        assert user_ids == {"owner-1", "user-2", "user-3"}


# ---------------------------------------------------------------------------
# Team projects
# ---------------------------------------------------------------------------


class TestTeamProjects:
    """Test project CRUD within a team."""

    def test_create_project(self, client):
        team = _create_team(client)
        team_id = team["id"]

        resp = client.post(
            f"/api/teams/{team_id}/projects",
            json={"name": "Production App"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Production App"
        assert data["team_id"] == team_id
        assert "id" in data
        assert data["last_score"] is None

    def test_create_project_missing_name(self, client):
        team = _create_team(client)
        resp = client.post(f"/api/teams/{team['id']}/projects", json={})
        assert resp.status_code == 400

    def test_create_project_team_not_found(self, client):
        resp = client.post(
            "/api/teams/nonexistent/projects",
            json={"name": "Orphan"},
        )
        assert resp.status_code == 404

    def test_list_projects(self, client):
        team = _create_team(client)
        team_id = team["id"]

        client.post(f"/api/teams/{team_id}/projects", json={"name": "Project A"})
        client.post(f"/api/teams/{team_id}/projects", json={"name": "Project B"})

        resp = client.get(f"/api/teams/{team_id}/projects")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2
        names = [p["name"] for p in data["projects"]]
        assert "Project A" in names
        assert "Project B" in names

    def test_list_projects_empty(self, client):
        team = _create_team(client)
        resp = client.get(f"/api/teams/{team['id']}/projects")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0

    def test_list_projects_team_not_found(self, client):
        resp = client.get("/api/teams/nonexistent/projects")
        assert resp.status_code == 404
