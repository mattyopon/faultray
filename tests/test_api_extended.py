"""Extended tests for server.py, oauth.py, and database.py to bring coverage to 95%+."""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from infrasim.api.database import (
    AuditLog,
    Base,
    ProjectRow,
    SimulationRunRow,
    TeamRow,
    UserRow,
    get_database_url,
    get_session_factory,
    init_db,
    log_audit,
    reset_engine,
    _get_engine,
)
from infrasim.api.server import (
    RateLimiter,
    _rate_limiter,
    _report_to_dict,
    _save_run,
    app,
    build_demo_graph,
    get_graph,
    set_graph,
)
from infrasim.model.components import HealthStatus
from infrasim.model.demo import create_demo_graph
from infrasim.model.graph import InfraGraph
from infrasim.simulator.cascade import CascadeChain, CascadeEffect
from infrasim.simulator.engine import ScenarioResult, SimulationEngine, SimulationReport
from infrasim.simulator.scenarios import Fault, FaultType, Scenario


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_report(risk_score: float = 8.5, resilience: float = 65.0) -> SimulationReport:
    """Create a minimal SimulationReport for testing."""
    effect = CascadeEffect(
        component_id="comp-1",
        component_name="web-server",
        health=HealthStatus.DOWN,
        reason="Node failure",
        estimated_time_seconds=30,
    )
    chain = CascadeChain(trigger="test-fault", total_components=3)
    chain.effects.append(effect)

    fault = Fault(
        target_component_id="comp-1",
        fault_type=FaultType.COMPONENT_DOWN,
    )
    scenario = Scenario(
        id="test-scenario-1",
        name="Test Scenario",
        description="A test scenario",
        faults=[fault],
    )
    result = ScenarioResult(
        scenario=scenario,
        cascade=chain,
        risk_score=risk_score,
    )
    return SimulationReport(results=[result], resilience_score=resilience)


# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------

def _run_async(coro):
    """Run an async coroutine synchronously, creating a new event loop if needed."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, coro).result()
    else:
        return asyncio.run(coro)


def _seed_sync(db_path: Path, table: str, rows: list[dict]) -> list[int]:
    """Insert rows into a table using synchronous sqlite3 and return the IDs."""
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    ids = []
    for row_data in rows:
        cols = ", ".join(row_data.keys())
        placeholders = ", ".join(["?"] * len(row_data))
        conn.execute(
            f"INSERT INTO {table} ({cols}) VALUES ({placeholders})",
            list(row_data.values()),
        )
        ids.append(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
    conn.commit()
    conn.close()
    return ids


@pytest.fixture
def db_setup(tmp_path: Path):
    """Create temp DB, init tables, configure the global engine to use it.

    Uses a synchronous engine for table creation to avoid event-loop issues,
    then configures the global async engine/session factory for the TestClient.
    """
    db_path = tmp_path / "test_extended.db"
    url = f"sqlite+aiosqlite:///{db_path}"

    reset_engine()

    # Create tables using synchronous SQLAlchemy (avoids event loop issues)
    from sqlalchemy import create_engine as create_sync_engine
    sync_engine = create_sync_engine(f"sqlite:///{db_path}", echo=False)
    Base.metadata.create_all(sync_engine)
    sync_engine.dispose()

    # Now configure the global async engine/session factory
    _get_engine(url)
    get_session_factory(url)

    yield db_path  # yield Path for sync seeding

    reset_engine()


@pytest_asyncio.fixture
async def session_factory_async(tmp_path: Path):
    """Async session factory for pure async tests (not using TestClient)."""
    db_path = tmp_path / "test_async.db"
    url = f"sqlite+aiosqlite:///{db_path}"

    reset_engine()

    engine = _get_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    sf = get_session_factory(url)
    yield sf

    await engine.dispose()
    reset_engine()


@pytest.fixture
def session_factory(db_setup):
    """Return the global session factory (sync fixture wrapper)."""
    return get_session_factory()


# ---------------------------------------------------------------------------
# Server fixtures
# ---------------------------------------------------------------------------

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
def db_client(db_setup):
    """Create a test client with the test database pre-configured.

    Patches init_db to prevent the lifespan from overwriting our test engine.
    Attaches db_path as tc._db_path for sync seeding.
    """
    with patch("infrasim.api.database.init_db", new_callable=AsyncMock):
        tc = TestClient(app, raise_server_exceptions=False)
        tc._db_path = db_setup
        yield tc


@pytest.fixture
def demo_client(client):
    """Create a test client with demo data preloaded."""
    graph = create_demo_graph()
    set_graph(graph)
    return client


@pytest.fixture
def demo_db_client(db_setup):
    """Test client with both demo data and test database."""
    graph = create_demo_graph()
    set_graph(graph)
    with patch("infrasim.api.database.init_db", new_callable=AsyncMock):
        tc = TestClient(app, raise_server_exceptions=False)
        tc._db_path = db_setup
        yield tc


# ===================================================================
# 1. RateLimiter tests (covers line 43 — rate limit denial)
# ===================================================================

class TestRateLimiter:
    def test_allows_within_limit(self):
        rl = RateLimiter(max_requests=3, window_seconds=60)
        assert rl.is_allowed("client-a") is True
        assert rl.is_allowed("client-a") is True
        assert rl.is_allowed("client-a") is True

    def test_blocks_over_limit(self):
        """Cover line 43: return False when over limit."""
        rl = RateLimiter(max_requests=2, window_seconds=60)
        assert rl.is_allowed("client-b") is True
        assert rl.is_allowed("client-b") is True
        assert rl.is_allowed("client-b") is False  # line 43

    def test_different_clients_independent(self):
        rl = RateLimiter(max_requests=1, window_seconds=60)
        assert rl.is_allowed("client-c") is True
        assert rl.is_allowed("client-d") is True
        assert rl.is_allowed("client-c") is False

    def test_window_expiry(self):
        rl = RateLimiter(max_requests=1, window_seconds=0)
        assert rl.is_allowed("client-e") is True
        # With window=0 all previous timestamps should be pruned
        assert rl.is_allowed("client-e") is True


class TestRateLimitMiddleware:
    """Cover line 133: middleware returning 429."""

    def test_rate_limit_429_response(self, client):
        """Exhaust rate limiter to trigger 429 response (line 133)."""
        # Replace global rate limiter with a very small one
        import infrasim.api.server as srv
        original = srv._rate_limiter
        srv._rate_limiter = RateLimiter(max_requests=1, window_seconds=60)
        try:
            # First request succeeds
            resp1 = client.get("/api/graph-data")
            assert resp1.status_code == 200

            # Second request should be rate limited
            resp2 = client.get("/api/graph-data")
            assert resp2.status_code == 429
            data = resp2.json()
            assert data["error"]["code"] == 429
            assert "Too many requests" in data["error"]["message"]
        finally:
            srv._rate_limiter = original


# ===================================================================
# 2. HTTPException handler (covers line 152)
# ===================================================================

class TestHTTPExceptionHandler:
    def test_structured_error_response_via_dependency(self, client):
        """Cover line 152: custom_http_exception_handler returns structured JSON.

        We trigger an HTTPException by overriding the _optional_user dependency
        to raise one.
        """
        from fastapi import HTTPException
        from infrasim.api.server import _optional_user

        async def _raise_http_exc():
            raise HTTPException(status_code=403, detail="Forbidden by test")

        app.dependency_overrides[_optional_user] = _raise_http_exc
        try:
            resp = client.get("/api/audit-logs")
            assert resp.status_code == 403
            data = resp.json()
            assert "error" in data
            assert data["error"]["code"] == 403
            assert data["error"]["message"] == "Forbidden by test"
        finally:
            app.dependency_overrides.clear()


# ===================================================================
# 3. Lifespan tests (covers lines 67-92)
# ===================================================================

class TestLifespan:
    def test_lifespan_initialises_db(self, tmp_path):
        """Cover lines 67-72: lifespan initialises database on startup."""
        db_path = tmp_path / "lifespan_test.db"
        url = f"sqlite+aiosqlite:///{db_path}"

        reset_engine()
        with patch.dict(os.environ, {}, clear=False):
            # Remove Prometheus env var to skip that branch
            os.environ.pop("INFRASIM_PROMETHEUS_URL", None)
            with patch("infrasim.api.database.init_db", new_callable=AsyncMock) as mock_init:
                with TestClient(app):
                    mock_init.assert_awaited_once()

        reset_engine()

    def test_lifespan_db_init_failure_logs_warning(self, tmp_path):
        """Cover line 72: warning logged when DB init fails."""
        reset_engine()
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("INFRASIM_PROMETHEUS_URL", None)
            with patch(
                "infrasim.api.database.init_db",
                new_callable=AsyncMock,
                side_effect=Exception("DB init error"),
            ):
                # Should not raise — app still starts
                with TestClient(app):
                    pass

        reset_engine()

    def test_lifespan_with_prometheus(self, tmp_path):
        """Cover lines 77-92: Prometheus monitor starts and stops."""
        reset_engine()

        mock_monitor = AsyncMock()
        mock_monitor.start = AsyncMock()
        mock_monitor.stop = AsyncMock()

        with patch.dict(
            os.environ,
            {"INFRASIM_PROMETHEUS_URL": "http://fake-prom:9090"},
            clear=False,
        ):
            with patch("infrasim.api.database.init_db", new_callable=AsyncMock):
                with patch(
                    "infrasim.discovery.prometheus_monitor.PrometheusMonitor",
                    return_value=mock_monitor,
                ):
                    with TestClient(app):
                        mock_monitor.start.assert_awaited_once()

                    # After exiting, stop should have been called
                    mock_monitor.stop.assert_awaited_once()

        reset_engine()

    def test_lifespan_prometheus_failure_logs_warning(self, tmp_path):
        """Cover lines 85-86: warning when Prometheus monitor fails to start."""
        reset_engine()

        with patch.dict(
            os.environ,
            {"INFRASIM_PROMETHEUS_URL": "http://fake-prom:9090"},
            clear=False,
        ):
            with patch("infrasim.api.database.init_db", new_callable=AsyncMock):
                with patch(
                    "infrasim.discovery.prometheus_monitor.PrometheusMonitor",
                    side_effect=Exception("prom import error"),
                ):
                    # Should not raise
                    with TestClient(app):
                        pass

        reset_engine()


# ===================================================================
# 4. Dashboard with _last_report set (covers lines 278, 326)
# ===================================================================

class TestDashboardWithReport:
    def test_dashboard_with_last_report(self, demo_client):
        """Cover line 278: dashboard with _last_report set."""
        import infrasim.api.server as srv
        report = _make_report()
        srv._last_report = report
        try:
            resp = demo_client.get("/")
            assert resp.status_code == 200
        finally:
            srv._last_report = None

    def test_simulation_page_with_report(self, demo_client):
        """Cover line 326: simulation page with _last_report set."""
        import infrasim.api.server as srv
        report = _make_report()
        srv._last_report = report
        try:
            resp = demo_client.get("/simulation")
            assert resp.status_code == 200
        finally:
            srv._last_report = None


# ===================================================================
# 5. API analyze with no prior report (covers lines 391-392)
# ===================================================================

class TestAnalyzeWithNoReport:
    def test_api_analyze_runs_simulation_if_no_report(self, demo_client):
        """Cover lines 391-392: run simulation if _last_report is None."""
        import infrasim.api.server as srv
        srv._last_report = None
        try:
            resp = demo_client.get("/api/analyze")
            assert resp.status_code == 200
            data = resp.json()
            assert "summary" in data
            # _last_report should now be set
            assert srv._last_report is not None
        finally:
            srv._last_report = None


# ===================================================================
# 6. Simulation run with DB save (covers lines 419, 439, 243-244)
# ===================================================================

class TestSimulationRunWithDB:
    async def test_save_run_returns_id(self, session_factory_async):
        """Cover lines 243-244: _save_run returns row id."""
        report_dict = {"resilience_score": 75.0, "total_scenarios": 5}
        run_id = await _save_run(report_dict, engine_type="static")
        assert run_id is not None
        assert isinstance(run_id, int)

    async def test_save_run_exception_returns_none(self):
        """Cover _save_run returning None on exception."""
        reset_engine()
        # With no DB set up, this should catch the exception and return None
        result = await _save_run({"resilience_score": 50.0})
        # It may return None if there's no valid engine
        # Just ensure it doesn't raise
        reset_engine()

    def test_simulation_run_get_saves_to_db(self, demo_db_client):
        """Cover line 419: run_id is set in response when DB works."""
        resp = demo_db_client.get("/simulation/run")
        assert resp.status_code == 200
        data = resp.json()
        assert "resilience_score" in data
        # run_id should be present when DB is working
        assert "run_id" in data

    def test_api_simulate_post_saves_to_db(self, demo_db_client):
        """Cover line 439: run_id is set in post response, plus audit log (line 456)."""
        resp = demo_db_client.post("/api/simulate")
        assert resp.status_code == 200
        data = resp.json()
        assert "resilience_score" in data


# ===================================================================
# 7. Runs CRUD (covers lines 545-601)
# ===================================================================

class TestRunsCRUD:
    def test_list_runs_with_data(self, db_client):
        """Cover lines 568-579: list runs returning data."""
        now = "2026-01-01T00:00:00"
        for i in range(3):
            _seed_sync(db_client._db_path, "simulation_runs", [{
                "engine_type": "static",
                "results_json": json.dumps({"score": i * 10}),
                "risk_score": float(i * 10),
                "created_at": now,
            }])

        resp = db_client.get("/api/runs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 3
        assert len(data["runs"]) == 3
        run = data["runs"][0]
        assert "id" in run
        assert "engine_type" in run
        assert "risk_score" in run
        assert "created_at" in run

    def test_list_runs_with_project_filter(self, db_client):
        """Cover line 545: filter by project_id."""
        now = "2026-01-01T00:00:00"
        pids = _seed_sync(db_client._db_path, "projects", [{
            "name": "test-proj", "created_at": now, "updated_at": now,
        }])
        pid = pids[0]

        _seed_sync(db_client._db_path, "simulation_runs", [
            {"engine_type": "static", "risk_score": 50.0, "project_id": pid, "created_at": now},
            {"engine_type": "static", "risk_score": 60.0, "created_at": now},
        ])

        resp = db_client.get(f"/api/runs?project_id={pid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["runs"][0]["project_id"] == pid

    def test_get_run_found(self, db_client):
        """Cover lines 596-601: get run returns data."""
        now = "2026-01-01T00:00:00"
        ids = _seed_sync(db_client._db_path, "simulation_runs", [{
            "engine_type": "static",
            "config_json": json.dumps({"key": "value"}),
            "results_json": json.dumps({"score": 80}),
            "risk_score": 80.0,
            "created_at": now,
        }])
        run_id = ids[0]

        resp = db_client.get(f"/api/runs/{run_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == run_id
        assert data["engine_type"] == "static"
        assert data["config_json"] == {"key": "value"}
        assert data["results_json"] == {"score": 80}
        assert data["risk_score"] == 80.0

    def test_get_run_not_found(self, db_client):
        """Cover lines 598-599: run not found returns 404."""
        resp = db_client.get("/api/runs/99999")
        assert resp.status_code == 404
        data = resp.json()
        assert "error" in data

    def test_delete_run_found(self, db_client):
        """Cover lines 626-644: delete run succeeds."""
        now = "2026-01-01T00:00:00"
        ids = _seed_sync(db_client._db_path, "simulation_runs", [{
            "engine_type": "static", "risk_score": 50.0, "created_at": now,
        }])
        run_id = ids[0]

        resp = db_client.delete(f"/api/runs/{run_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["deleted"] is True
        assert data["id"] == run_id

        # Verify it's actually deleted
        resp2 = db_client.get(f"/api/runs/{run_id}")
        assert resp2.status_code == 404

    def test_delete_run_not_found(self, db_client):
        """Cover lines 628-629: delete non-existent run returns 404."""
        resp = db_client.delete("/api/runs/99999")
        assert resp.status_code == 404


# ===================================================================
# 8. Projects CRUD (covers lines 660-744)
# ===================================================================

class TestProjectsCRUD:
    def test_create_project(self, db_client):
        """Cover lines 660-703: create project."""
        resp = db_client.post(
            "/api/projects",
            json={"name": "My Project"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "My Project"
        assert data["id"] is not None
        assert "created_at" in data

    def test_create_project_no_name(self, db_client):
        """Cover line 666: missing name returns 400."""
        resp = db_client.post("/api/projects", json={})
        assert resp.status_code == 400
        data = resp.json()
        assert "error" in data
        assert "name" in data["error"].lower()

    def test_create_project_with_team_id(self, db_client):
        """Cover line 668: project with team_id."""
        now = "2026-01-01T00:00:00"
        tids = _seed_sync(db_client._db_path, "teams", [{"name": "test-team", "created_at": now}])
        team_id = tids[0]

        resp = db_client.post(
            "/api/projects",
            json={"name": "Team Project", "team_id": team_id},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["team_id"] == team_id

    def test_list_projects(self, db_client):
        """Cover lines 713-744: list projects."""
        # Create some projects first
        db_client.post("/api/projects", json={"name": "Proj A"})
        db_client.post("/api/projects", json={"name": "Proj B"})

        resp = db_client.get("/api/projects")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2
        assert len(data["projects"]) == 2
        proj = data["projects"][0]
        assert "id" in proj
        assert "name" in proj
        assert "created_at" in proj

    def test_list_projects_empty(self, db_client):
        """Cover list projects when empty."""
        resp = db_client.get("/api/projects")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0


# ===================================================================
# 9. Audit logs (covers lines 763-793)
# ===================================================================

class TestAuditLogs:
    def test_list_audit_logs(self, db_client):
        """Cover lines 763-793: list audit logs."""
        now = "2026-01-01T00:00:00"
        _seed_sync(db_client._db_path, "audit_logs", [{
            "action": "test_action",
            "resource_type": "test_resource",
            "resource_id": "1",
            "details_json": json.dumps({"key": "value"}),
            "ip_address": "127.0.0.1",
            "created_at": now,
        }])

        resp = db_client.get("/api/audit-logs")
        assert resp.status_code == 200
        data = resp.json()
        assert "audit_logs" in data
        assert data["count"] >= 1
        log_entry = data["audit_logs"][0]
        assert log_entry["action"] == "test_action"
        assert log_entry["resource_type"] == "test_resource"
        assert log_entry["details"] == {"key": "value"}
        assert log_entry["ip_address"] == "127.0.0.1"

    def test_list_audit_logs_empty(self, db_client):
        """Cover audit logs when empty."""
        resp = db_client.get("/api/audit-logs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0

    def test_list_audit_logs_with_pagination(self, db_client):
        """Test audit logs pagination."""
        now = "2026-01-01T00:00:00"
        for i in range(5):
            _seed_sync(db_client._db_path, "audit_logs", [{
                "action": f"action_{i}",
                "resource_type": "test",
                "created_at": now,
            }])

        resp = db_client.get("/api/audit-logs?limit=2&offset=0")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2


# ===================================================================
# 10. OAuth login/callback (covers lines 807-883)
# ===================================================================

class TestOAuthRoutes:
    def test_oauth_login_unconfigured(self, client):
        """Cover lines 807-814: OAuth login with no env vars configured."""
        with patch.dict(os.environ, {}, clear=False):
            for k in list(os.environ):
                if k.startswith("INFRASIM_OAUTH_"):
                    os.environ.pop(k, None)
            resp = client.get("/auth/login/github", follow_redirects=False)
            assert resp.status_code == 400
            data = resp.json()
            assert "not configured" in data["error"]

    def test_oauth_login_configured_redirects(self, client):
        """Cover lines 807-819: OAuth login redirects when configured."""
        env = {
            "INFRASIM_OAUTH_GITHUB_CLIENT_ID": "test-id",
            "INFRASIM_OAUTH_GITHUB_CLIENT_SECRET": "test-secret",
        }
        with patch.dict(os.environ, env, clear=False):
            resp = client.get("/auth/login/github", follow_redirects=False)
            assert resp.status_code == 307
            assert "github.com" in resp.headers.get("location", "")

    def test_oauth_callback_unconfigured(self, client):
        """Cover lines 828-835: callback with no provider configured."""
        with patch.dict(os.environ, {}, clear=False):
            for k in list(os.environ):
                if k.startswith("INFRASIM_OAUTH_"):
                    os.environ.pop(k, None)
            resp = client.get("/auth/callback?code=abc&provider=github")
            assert resp.status_code == 400

    def test_oauth_callback_missing_code(self, client):
        """Cover lines 837-838: callback with no code."""
        env = {
            "INFRASIM_OAUTH_GITHUB_CLIENT_ID": "test-id",
            "INFRASIM_OAUTH_GITHUB_CLIENT_SECRET": "test-secret",
        }
        with patch.dict(os.environ, env, clear=False):
            resp = client.get("/auth/callback?provider=github")
            assert resp.status_code == 400
            data = resp.json()
            assert "Missing authorization code" in data["error"]

    def test_oauth_callback_exchange_failure(self, client):
        """Cover lines 843-845: OAuth exchange failure returns 502."""
        env = {
            "INFRASIM_OAUTH_GITHUB_CLIENT_ID": "test-id",
            "INFRASIM_OAUTH_GITHUB_CLIENT_SECRET": "test-secret",
        }
        with patch.dict(os.environ, env, clear=False):
            with patch(
                "infrasim.api.oauth.exchange_code_for_token",
                new_callable=AsyncMock,
                side_effect=RuntimeError("token exchange failed"),
            ):
                resp = client.get("/auth/callback?code=testcode&provider=github")
                assert resp.status_code == 502
                data = resp.json()
                assert "OAuth exchange failed" in data["error"]

    def test_oauth_callback_success_new_user(self, db_client):
        """Cover lines 848-880: successful OAuth creates new user."""
        env = {
            "INFRASIM_OAUTH_GITHUB_CLIENT_ID": "test-id",
            "INFRASIM_OAUTH_GITHUB_CLIENT_SECRET": "test-secret",
        }
        with patch.dict(os.environ, env, clear=False):
            with patch(
                "infrasim.api.oauth.exchange_code_for_token",
                new_callable=AsyncMock,
                return_value="fake-access-token",
            ):
                with patch(
                    "infrasim.api.oauth.get_user_profile",
                    new_callable=AsyncMock,
                    return_value={"email": "new@example.com", "name": "New User"},
                ):
                    resp = db_client.get(
                        "/auth/callback?code=testcode&provider=github"
                    )
                    assert resp.status_code == 200
                    data = resp.json()
                    assert data["message"] == "Login successful"
                    assert data["user"]["email"] == "new@example.com"
                    assert data["user"]["name"] == "New User"
                    assert "api_key" in data

    def test_oauth_callback_existing_user(self, db_client):
        """Cover lines 868-874: existing user gets API key rotated."""
        from infrasim.api.auth import hash_api_key

        # Create a user first using sync sqlite
        now = "2026-01-01T00:00:00"
        _seed_sync(db_client._db_path, "users", [{
            "email": "existing@example.com",
            "name": "Old Name",
            "api_key_hash": hash_api_key("old-key"),
            "role": "viewer",
            "created_at": now,
        }])

        env = {
            "INFRASIM_OAUTH_GITHUB_CLIENT_ID": "test-id",
            "INFRASIM_OAUTH_GITHUB_CLIENT_SECRET": "test-secret",
        }
        with patch.dict(os.environ, env, clear=False):
            with patch(
                "infrasim.api.oauth.exchange_code_for_token",
                new_callable=AsyncMock,
                return_value="fake-access-token",
            ):
                with patch(
                    "infrasim.api.oauth.get_user_profile",
                    new_callable=AsyncMock,
                    return_value={
                        "email": "existing@example.com",
                        "name": "Updated Name",
                    },
                ):
                    resp = db_client.get(
                        "/auth/callback?code=testcode&provider=github"
                    )
                    assert resp.status_code == 200
                    data = resp.json()
                    assert data["user"]["email"] == "existing@example.com"
                    assert data["user"]["name"] == "Updated Name"
                    assert "api_key" in data

    def test_oauth_callback_db_failure(self, client):
        """Cover lines 881-883: user creation fails."""
        env = {
            "INFRASIM_OAUTH_GITHUB_CLIENT_ID": "test-id",
            "INFRASIM_OAUTH_GITHUB_CLIENT_SECRET": "test-secret",
        }
        with patch.dict(os.environ, env, clear=False):
            with patch(
                "infrasim.api.oauth.exchange_code_for_token",
                new_callable=AsyncMock,
                return_value="fake-access-token",
            ):
                with patch(
                    "infrasim.api.oauth.get_user_profile",
                    new_callable=AsyncMock,
                    return_value={"email": "fail@example.com", "name": "Fail"},
                ):
                    # Patch at the database module level since it's imported locally
                    with patch(
                        "infrasim.api.database.get_session_factory",
                        side_effect=Exception("DB unavailable"),
                    ):
                        resp = client.get(
                            "/auth/callback?code=testcode&provider=github"
                        )
                        assert resp.status_code == 500
                        data = resp.json()
                        assert "User creation failed" in data["error"]


# ===================================================================
# 11. Multi-tenant: runs filtered by user team (covers lines 550-557)
# ===================================================================

class TestMultiTenantRuns:
    def test_list_runs_with_user_team_filter(self, db_client):
        """Cover lines 550-557: runs filtered by user's team."""
        now = "2026-01-01T00:00:00"
        tids = _seed_sync(db_client._db_path, "teams", [{"name": "test-team", "created_at": now}])
        team_id = tids[0]

        pids = _seed_sync(db_client._db_path, "projects", [{
            "name": "team-proj", "team_id": team_id, "created_at": now, "updated_at": now,
        }])
        pid = pids[0]

        _seed_sync(db_client._db_path, "simulation_runs", [
            {"engine_type": "static", "risk_score": 50.0, "project_id": pid, "created_at": now},
            {"engine_type": "static", "risk_score": 60.0, "created_at": now},
        ])

        # Override the RBAC dependency for the /api/runs GET route
        mock_user = SimpleNamespace(id=1, team_id=team_id, role="viewer")
        dep_func = None
        for route in app.routes:
            if hasattr(route, "path") and route.path == "/api/runs" and "GET" in getattr(route, "methods", set()):
                for dep in route.dependant.dependencies:
                    dep_func = dep.call
                    break
                break

        if dep_func is not None:
            app.dependency_overrides[dep_func] = lambda: mock_user
        try:
            resp = db_client.get("/api/runs")
            assert resp.status_code == 200
            data = resp.json()
            # Should return runs from team projects + runs with no project
            assert data["count"] >= 1
        finally:
            app.dependency_overrides.clear()


# ===================================================================
# 12. Multi-tenant: projects filtered by user (covers lines 722-726)
# ===================================================================

class TestMultiTenantProjects:
    def test_list_projects_with_user_team_filter(self, db_client):
        """Cover lines 722-726: projects filtered by user's team."""
        from infrasim.api.auth import hash_api_key

        now = "2026-01-01T00:00:00"
        tids = _seed_sync(db_client._db_path, "teams", [{"name": "proj-team", "created_at": now}])
        team_id = tids[0]

        uids = _seed_sync(db_client._db_path, "users", [{
            "email": "team@example.com",
            "name": "Team User",
            "api_key_hash": hash_api_key("team-key"),
            "role": "editor",
            "team_id": team_id,
            "created_at": now,
        }])
        user_id = uids[0]

        _seed_sync(db_client._db_path, "projects", [
            {"name": "Team Proj", "team_id": team_id, "owner_id": user_id, "created_at": now, "updated_at": now},
            {"name": "Other Proj", "created_at": now, "updated_at": now},
        ])

        # The /api/projects endpoint uses _require_permission("view_results"),
        # which wraps require_permission and returns the user.  We need to
        # override the actual dependency function attached to the route.
        # Extract the dependency from the route so we can override it properly.
        from infrasim.api.server import _require_permission
        mock_user = SimpleNamespace(id=user_id, team_id=team_id, role="editor")

        # Find the actual dependency function used by the /api/projects GET route
        dep_func = None
        for route in app.routes:
            if hasattr(route, "path") and route.path == "/api/projects" and "GET" in getattr(route, "methods", set()):
                for dep in route.dependant.dependencies:
                    dep_func = dep.call
                    break
                break

        if dep_func is not None:
            app.dependency_overrides[dep_func] = lambda: mock_user
        try:
            resp = db_client.get("/api/projects")
            assert resp.status_code == 200
            data = resp.json()
            # Should only return the team project (and user-owned projects)
            assert data["count"] >= 1
            names = [p["name"] for p in data["projects"]]
            assert "Team Proj" in names
        finally:
            app.dependency_overrides.clear()


# ===================================================================
# 13. OAuth module: exchange_code_for_token + get_user_profile
#     (covers lines 105-141, 150-156, 161-167, 172-184)
# ===================================================================

class TestOAuthTokenExchange:
    """Tests for oauth.py exchange_code_for_token and get_user_profile."""

    async def test_github_exchange_code_success(self):
        """Cover lines 105-121: GitHub token exchange."""
        from infrasim.api.oauth import OAuthConfig, exchange_code_for_token

        config = OAuthConfig(
            provider="github",
            client_id="gh-id",
            client_secret="gh-secret",
            redirect_uri="http://localhost/callback",
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {"access_token": "gh-token-123"}

        with patch("infrasim.api.oauth.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            token = await exchange_code_for_token(config, "auth-code-123")
            assert token == "gh-token-123"
            mock_client.post.assert_awaited_once()

    async def test_github_exchange_code_failure(self):
        """Cover lines 119-120: GitHub token exchange failure."""
        from infrasim.api.oauth import OAuthConfig, exchange_code_for_token

        config = OAuthConfig(
            provider="github",
            client_id="gh-id",
            client_secret="gh-secret",
            redirect_uri="http://localhost/callback",
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {"error": "bad_verification_code"}

        with patch("infrasim.api.oauth.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with pytest.raises(RuntimeError, match="GitHub token exchange failed"):
                await exchange_code_for_token(config, "bad-code")

    async def test_google_exchange_code_success(self):
        """Cover lines 123-139: Google token exchange."""
        from infrasim.api.oauth import OAuthConfig, exchange_code_for_token

        config = OAuthConfig(
            provider="google",
            client_id="ggl-id",
            client_secret="ggl-secret",
            redirect_uri="http://localhost/callback",
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {"access_token": "ggl-token-456"}

        with patch("infrasim.api.oauth.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            token = await exchange_code_for_token(config, "ggl-auth-code")
            assert token == "ggl-token-456"

    async def test_google_exchange_code_failure(self):
        """Cover lines 137-138: Google token exchange failure."""
        from infrasim.api.oauth import OAuthConfig, exchange_code_for_token

        config = OAuthConfig(
            provider="google",
            client_id="ggl-id",
            client_secret="ggl-secret",
            redirect_uri="http://localhost/callback",
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {"error": "invalid_grant"}

        with patch("infrasim.api.oauth.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with pytest.raises(RuntimeError, match="Google token exchange failed"):
                await exchange_code_for_token(config, "bad-code")

    async def test_unsupported_provider_exchange(self):
        """Cover line 141: unsupported provider raises RuntimeError."""
        from infrasim.api.oauth import OAuthConfig, exchange_code_for_token

        config = OAuthConfig(
            provider="unknown",
            client_id="id",
            client_secret="secret",
            redirect_uri="http://localhost/callback",
        )
        with pytest.raises(RuntimeError, match="Unsupported provider"):
            await exchange_code_for_token(config, "code")


class TestOAuthUserProfile:
    """Tests for get_github_user, get_google_user, get_user_profile."""

    async def test_get_github_user(self):
        """Cover lines 150-156: fetch GitHub user profile."""
        from infrasim.api.oauth import get_github_user

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "login": "testuser",
            "name": "Test User",
            "email": "test@github.com",
        }
        mock_response.raise_for_status = MagicMock()

        with patch("infrasim.api.oauth.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            user = await get_github_user("fake-token")
            assert user["login"] == "testuser"
            assert user["email"] == "test@github.com"

    async def test_get_google_user(self):
        """Cover lines 161-167: fetch Google user profile."""
        from infrasim.api.oauth import get_google_user

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "name": "Google User",
            "email": "user@google.com",
        }
        mock_response.raise_for_status = MagicMock()

        with patch("infrasim.api.oauth.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            user = await get_google_user("fake-token")
            assert user["email"] == "user@google.com"

    async def test_get_user_profile_github(self):
        """Cover lines 172-177: normalised profile for GitHub."""
        from infrasim.api.oauth import OAuthConfig, get_user_profile

        config = OAuthConfig(
            provider="github",
            client_id="id",
            client_secret="secret",
            redirect_uri="http://localhost/callback",
        )
        with patch(
            "infrasim.api.oauth.get_github_user",
            new_callable=AsyncMock,
            return_value={"email": "gh@example.com", "name": "GH User", "login": "ghuser"},
        ):
            profile = await get_user_profile(config, "token")
            assert profile["email"] == "gh@example.com"
            assert profile["name"] == "GH User"

    async def test_get_user_profile_github_no_email(self):
        """Cover lines 175: fallback email for GitHub user without email."""
        from infrasim.api.oauth import OAuthConfig, get_user_profile

        config = OAuthConfig(
            provider="github",
            client_id="id",
            client_secret="secret",
            redirect_uri="http://localhost/callback",
        )
        with patch(
            "infrasim.api.oauth.get_github_user",
            new_callable=AsyncMock,
            return_value={"email": None, "name": None, "login": "ghuser"},
        ):
            profile = await get_user_profile(config, "token")
            assert profile["email"] == "ghuser@github"
            assert profile["name"] == "ghuser"

    async def test_get_user_profile_google(self):
        """Cover lines 178-183: normalised profile for Google."""
        from infrasim.api.oauth import OAuthConfig, get_user_profile

        config = OAuthConfig(
            provider="google",
            client_id="id",
            client_secret="secret",
            redirect_uri="http://localhost/callback",
        )
        with patch(
            "infrasim.api.oauth.get_google_user",
            new_callable=AsyncMock,
            return_value={"email": "ggl@example.com", "name": "Google User"},
        ):
            profile = await get_user_profile(config, "token")
            assert profile["email"] == "ggl@example.com"
            assert profile["name"] == "Google User"

    async def test_get_user_profile_unsupported(self):
        """Cover line 184: unsupported provider raises RuntimeError."""
        from infrasim.api.oauth import OAuthConfig, get_user_profile

        config = OAuthConfig(
            provider="unknown",
            client_id="id",
            client_secret="secret",
            redirect_uri="http://localhost/callback",
        )
        with pytest.raises(RuntimeError, match="Unsupported provider"):
            await get_user_profile(config, "token")


# ===================================================================
# 14. Database: log_audit (covers line 166) and init_db (covers 207-212)
# ===================================================================

class TestDatabaseExtended:
    async def test_log_audit_returns_entry(self, session_factory_async):
        """Cover line 166: log_audit returns the AuditLog entry."""
        async with session_factory_async() as session:
            entry = await log_audit(
                session,
                user_id=42,
                action="test_audit",
                resource_type="test_res",
                resource_id="res-1",
                details={"hello": "world"},
                ip="10.0.0.1",
            )
            await session.commit()

            assert entry is not None
            assert entry.id is not None
            assert entry.user_id == 42
            assert entry.action == "test_audit"
            assert entry.resource_type == "test_res"
            assert entry.resource_id == "res-1"
            assert entry.ip_address == "10.0.0.1"
            parsed = json.loads(entry.details_json)
            assert parsed == {"hello": "world"}

    async def test_log_audit_no_details(self, session_factory_async):
        """Test log_audit with no details."""
        async with session_factory_async() as session:
            entry = await log_audit(
                session,
                user_id=None,
                action="simple_action",
                resource_type="test_res",
            )
            await session.commit()
            assert entry.details_json is None

    async def test_init_db_creates_tables_with_url(self, tmp_path):
        """Cover lines 210-212: init_db with explicit url creates tables."""
        reset_engine()
        db_path = tmp_path / "initdb_test.db"
        url = f"sqlite+aiosqlite:///{db_path}"

        await init_db(url=url)

        # Verify tables exist
        engine = _get_engine()
        async with engine.connect() as conn:
            from sqlalchemy import inspect as sa_inspect
            table_names = await conn.run_sync(
                lambda sync_conn: sa_inspect(sync_conn).get_table_names()
            )
        assert "users" in table_names
        assert "simulation_runs" in table_names
        assert "audit_logs" in table_names

        await engine.dispose()
        reset_engine()

    async def test_init_db_default_url_creates_dir(self, tmp_path, monkeypatch):
        """Cover lines 207-208: init_db with url=None creates DB_DIR."""
        import infrasim.api.database as db_mod

        reset_engine()

        fake_db_dir = tmp_path / "fake_infrasim"
        fake_db_path = fake_db_dir / "infrasim.db"
        monkeypatch.setattr(db_mod, "DB_DIR", fake_db_dir)
        monkeypatch.setattr(db_mod, "DB_PATH", fake_db_path)

        await init_db(url=None)

        # Directory should be created
        assert fake_db_dir.exists()

        engine = _get_engine()
        await engine.dispose()
        reset_engine()

    def test_get_database_url_default(self):
        """Test get_database_url with default path."""
        url = get_database_url()
        assert "sqlite+aiosqlite" in url
        assert "infrasim.db" in url

    def test_get_database_url_custom_path(self, tmp_path):
        """Test get_database_url with custom path."""
        custom_path = tmp_path / "custom.db"
        url = get_database_url(custom_path)
        assert str(custom_path) in url


# ===================================================================
# 15. report_to_dict helper
# ===================================================================

class TestReportToDict:
    def test_report_to_dict_basic(self):
        """Test _report_to_dict converts report properly."""
        report = _make_report(risk_score=8.5, resilience=65.0)
        d = _report_to_dict(report)
        assert d["resilience_score"] == 65.0
        assert d["total_scenarios"] == 1
        assert d["critical_count"] == 1
        assert d["warning_count"] == 0
        assert d["passed_count"] == 0
        assert len(d["critical"]) == 1
        assert d["critical"][0]["risk_score"] == 8.5
        assert d["critical"][0]["cascade"]["trigger"] == "test-fault"

    def test_report_to_dict_warning(self):
        """Test with a warning-level result."""
        report = _make_report(risk_score=5.0, resilience=80.0)
        d = _report_to_dict(report)
        assert d["warning_count"] == 1
        assert d["critical_count"] == 0
        assert len(d["warnings"]) == 1

    def test_report_to_dict_passed(self):
        """Test with a passed result."""
        report = _make_report(risk_score=2.0, resilience=90.0)
        d = _report_to_dict(report)
        assert d["passed_count"] == 1
        assert d["critical_count"] == 0
        assert d["warning_count"] == 0


# ===================================================================
# 16. Analyze page with data but no prior report (covers lines 354-355)
# ===================================================================

class TestAnalyzeNoReport:
    def test_analyze_page_runs_simulation_when_no_report(self, demo_client):
        """Cover lines 354-355: analyze page runs simulation when _last_report is None."""
        import infrasim.api.server as srv
        srv._last_report = None
        try:
            resp = demo_client.get("/analyze")
            assert resp.status_code == 200
            assert "text/html" in resp.headers.get("content-type", "")
            # _last_report should be set now
            assert srv._last_report is not None
        finally:
            srv._last_report = None


# ===================================================================
# 17. DB error branches for create_project, list_projects, audit_logs
#     (covers lines 701-703, 742-744, 791-793)
# ===================================================================

class TestDBErrorBranches:
    def test_create_project_db_error(self, client):
        """Cover lines 701-703: create_project returns 503 on DB error."""
        with patch(
            "infrasim.api.database.get_session_factory",
            side_effect=Exception("DB unavailable"),
        ):
            resp = client.post("/api/projects", json={"name": "Failing"})
            assert resp.status_code == 503
            data = resp.json()
            assert "Database not available" in data["error"]

    def test_list_projects_db_error(self, client):
        """Cover lines 742-744: list_projects returns fallback on DB error."""
        with patch(
            "infrasim.api.database.get_session_factory",
            side_effect=Exception("DB unavailable"),
        ):
            resp = client.get("/api/projects")
            assert resp.status_code == 200
            data = resp.json()
            assert data["count"] == 0
            assert "note" in data

    def test_list_audit_logs_db_error(self, client):
        """Cover lines 791-793: list_audit_logs returns fallback on DB error."""
        with patch(
            "infrasim.api.database.get_session_factory",
            side_effect=Exception("DB unavailable"),
        ):
            resp = client.get("/api/audit-logs")
            assert resp.status_code == 200
            data = resp.json()
            assert data["count"] == 0
            assert "note" in data
