"""Regression tests for /api/projects tenant isolation (realtime.py).

Loads the serverless module directly (it is not a package) and exercises the
project access-control helpers, which previously returned every tenant's
projects from a service-role query with no auth or team filter.
"""
import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "faultray_realtime", ROOT / "api" / "realtime.py"
)
realtime = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(realtime)


def test_bearer_token_parsing():
    assert realtime._bearer_token({"Authorization": "Bearer abc"}) == "abc"
    assert realtime._bearer_token({"authorization": "Bearer xyz"}) == "xyz"
    assert realtime._bearer_token({"Authorization": "Basic abc"}) is None
    assert realtime._bearer_token({"Authorization": "Bearer "}) is None
    assert realtime._bearer_token({}) is None


def test_proj_list_demo_vs_authenticated():
    # Demo mode (team_ids is None) keeps returning sample projects.
    status, data = realtime._proj_list(None)
    assert status == 200 and isinstance(data, list) and data

    # Authenticated with no teams returns an empty list — never demo, never
    # another tenant's data.
    status, data = realtime._proj_list([])
    assert status == 200 and data == []


def test_proj_get_tenant_guard(monkeypatch):
    uuid = "11111111-1111-1111-1111-111111111111"

    def fake_request(method, table, params="", body=None):
        if table == "projects":
            return [{"id": uuid, "team_id": "team-A"}]
        return []

    monkeypatch.setattr(realtime, "_proj_supabase_request", fake_request)

    # Caller outside team-A must not be able to tell the project exists.
    status, _ = realtime._proj_get(uuid, ["team-B"])
    assert status == 404

    # Caller in team-A gets it.
    status, _ = realtime._proj_get(uuid, ["team-A"])
    assert status == 200


def test_proj_create_requires_team():
    # Demo mode still works.
    status, _ = realtime._proj_create({"name": "x"}, None)
    assert status == 201

    # Authenticated but with no resolvable team is refused rather than
    # creating an orphan (team_id NULL) row.
    status, _ = realtime._proj_create({"name": "x"}, [])
    assert status == 403


def test_proj_create_stamps_owner_team(monkeypatch):
    captured = {}

    def fake_request(method, table, params="", body=None):
        captured["body"] = body
        return [{"id": "p1", **(body or {})}]

    monkeypatch.setattr(realtime, "_proj_supabase_request", fake_request)
    status, _ = realtime._proj_create({"name": "x"}, ["team-A"])
    assert status == 201
    assert captured["body"]["team_id"] == "team-A"


def test_proj_owned_by(monkeypatch):
    monkeypatch.setattr(
        realtime, "_proj_supabase_request",
        lambda *a, **k: [{"team_id": "team-A"}],
    )
    assert realtime._proj_owned_by("id", ["team-A"]) is True
    assert realtime._proj_owned_by("id", ["team-B"]) is False


def test_proj_update_and_delete_reject_cross_tenant(monkeypatch):
    uuid = "11111111-1111-1111-1111-111111111111"
    monkeypatch.setattr(
        realtime, "_proj_supabase_request",
        lambda *a, **k: [{"team_id": "team-A"}],
    )
    # Not a member of team-A → 404 for both mutations.
    assert realtime._proj_update(uuid, {"name": "y"}, ["team-B"])[0] == 404
    assert realtime._proj_delete(uuid, ["team-B"])[0] == 404
