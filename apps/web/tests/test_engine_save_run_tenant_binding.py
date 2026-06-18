"""Regression tests for /api/engine save-run tenant binding (engine.py).

`_save_run_to_supabase` inserts with the service role (RLS bypassed) and used to
trust an attacker-controllable `project_id` from the body with no ownership
check, so any authenticated caller could write simulation_runs rows against
another tenant's project (landing with a NULL team_id, escaping tenant scoping).
It now resolves the project's owning team, requires a JWT caller to be a member,
and stamps team_id. These tests pin that authorization branching.
"""
import importlib.util
import pathlib
import urllib.request

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("faultray_engine", ROOT / "api" / "engine.py")
engine = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(engine)


@pytest.fixture
def configured(monkeypatch):
    """Make Supabase look configured so save does not short-circuit to demo."""
    monkeypatch.setenv("NEXT_PUBLIC_SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-key")  # noqa: S105


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        import json
        return json.dumps(self._payload).encode()


def _capture_insert(monkeypatch):
    """Patch the insert HTTP call; return a list that receives the posted record."""
    import json
    captured = []

    def fake_urlopen(req, timeout=10):
        captured.append(json.loads(req.data.decode()))
        return _FakeResp([{"id": "run-123"}])

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return captured


def test_demo_when_supabase_unconfigured(monkeypatch):
    monkeypatch.delenv("NEXT_PUBLIC_SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    # 1-arg call still works (backward compatible signature).
    out = engine._save_run_to_supabase({"overall_score": 99})
    assert out["ok"] is True and out.get("demo") is True


def test_unknown_project_is_refused(configured, monkeypatch):
    monkeypatch.setattr(engine, "_project_team_id", lambda *a, **k: None)
    captured = _capture_insert(monkeypatch)
    out = engine._save_run_to_supabase({"project_id": "ghost"}, "user-1")
    assert out["ok"] is False
    assert "project not found" in out["error"]
    assert captured == []  # no row inserted


def test_non_member_is_forbidden(configured, monkeypatch):
    monkeypatch.setattr(engine, "_project_team_id", lambda *a, **k: "team-victim")
    monkeypatch.setattr(engine, "_user_in_team", lambda *a, **k: False)
    captured = _capture_insert(monkeypatch)
    out = engine._save_run_to_supabase({"project_id": "p-victim"}, "attacker")
    assert out["ok"] is False
    assert "forbidden" in out["error"]
    assert captured == []  # cross-tenant write blocked


def test_member_insert_stamps_team_id(configured, monkeypatch):
    monkeypatch.setattr(engine, "_project_team_id", lambda *a, **k: "team-mine")
    monkeypatch.setattr(engine, "_user_in_team", lambda *a, **k: True)
    captured = _capture_insert(monkeypatch)
    out = engine._save_run_to_supabase(
        {"project_id": "p-mine", "overall_score": 88}, "member-user"
    )
    assert out["ok"] is True and out["id"] == "run-123"
    assert len(captured) == 1
    assert captured[0]["project_id"] == "p-mine"
    assert captured[0]["team_id"] == "team-mine"  # tenant-scoped, not NULL


def test_internal_key_caller_skips_membership_check(configured, monkeypatch):
    # caller_user_id=None ⇒ internal/agent API-key path (already trusted by
    # _authenticate). It must still bind team_id but not require membership.
    monkeypatch.setattr(engine, "_project_team_id", lambda *a, **k: "team-x")

    def _must_not_call(*a, **k):  # pragma: no cover - asserted via raise
        raise AssertionError("membership check must be skipped for internal callers")

    monkeypatch.setattr(engine, "_user_in_team", _must_not_call)
    captured = _capture_insert(monkeypatch)
    out = engine._save_run_to_supabase({"project_id": "p-x"}, None)
    assert out["ok"] is True
    assert captured[0]["team_id"] == "team-x"


def test_no_project_id_inserts_without_team(configured, monkeypatch):
    # An anonymous/demo save with no project_id keeps prior behavior (no team_id,
    # no ownership lookup).
    called = {"team": False}
    monkeypatch.setattr(
        engine, "_project_team_id",
        lambda *a, **k: called.__setitem__("team", True) or "x",
    )
    captured = _capture_insert(monkeypatch)
    out = engine._save_run_to_supabase({"overall_score": 5}, "user-1")
    assert out["ok"] is True
    assert called["team"] is False
    assert "team_id" not in captured[0]
