"""Auth/authorization tests for admin.py routes (#100).

Verifies the wiring added by security/admin-require-permission:
- Public endpoints (health, versions, api-docs, setup, auth/*) stay open
- Protected HTML pages + read-only APIs require view_dashboard (viewer+)
- Write endpoints (marketplace install, calendar CRUD, chat) require
  run_simulation (editor+); viewer gets 403
- Slack webhook uses Slack signature HMAC instead of bearer auth
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time

import pytest
from fastapi.testclient import TestClient

from faultray.api.auth import hash_api_key
from faultray.api.database import Base, UserRow, _get_engine, get_session_factory
from faultray.api.server import _rate_limiter, app
from tests.conftest import TEST_API_KEY, _run_async


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_VIEWER_KEY = "test-viewer-key-for-#100"
_VIEWER_HASH = hash_api_key(_VIEWER_KEY)


async def _ensure_user(email: str, key_hash: str, role: str) -> None:
    engine = _get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sf = get_session_factory()
    async with sf() as session:
        from sqlalchemy import select

        result = await session.execute(
            select(UserRow).where(UserRow.api_key_hash == key_hash)
        )
        if result.scalar_one_or_none() is None:
            session.add(
                UserRow(email=email, name=email, api_key_hash=key_hash, role=role)
            )
            await session.commit()


@pytest.fixture(autouse=True)
def _reset_state():
    """Ensure admin test user + viewer exist; reset rate limiter each test."""
    from tests.conftest import _setup_test_user

    _setup_test_user()
    _run_async(_ensure_user("viewer@test.local", _VIEWER_HASH, "viewer"))
    _rate_limiter.requests.clear()
    yield
    _rate_limiter.requests.clear()


@pytest.fixture
def anon_client():
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def admin_client():
    c = TestClient(app, raise_server_exceptions=False)
    c.headers["Authorization"] = f"Bearer {TEST_API_KEY}"
    return c


@pytest.fixture
def viewer_client():
    c = TestClient(app, raise_server_exceptions=False)
    c.headers["Authorization"] = f"Bearer {_VIEWER_KEY}"
    return c


# ---------------------------------------------------------------------------
# Public endpoints stay open
# ---------------------------------------------------------------------------


class TestPublicEndpoints:
    @pytest.mark.parametrize(
        "path",
        [
            "/api/health",
            "/api/versions",
            "/api-docs",
        ],
    )
    def test_public_paths_no_auth(self, anon_client, path):
        resp = anon_client.get(path)
        # 200 expected for all three (api-docs returns HTML; health/versions return JSON)
        assert resp.status_code == 200, f"{path} returned {resp.status_code}"


# ---------------------------------------------------------------------------
# Protected read endpoints require view_dashboard
# ---------------------------------------------------------------------------


class TestReadProtection:
    READ_PATHS = [
        "/settings",
        "/marketplace",
        "/api/marketplace/packages",
        "/api/marketplace/featured",
        "/api/marketplace/categories",
        "/api/marketplace/popular",
        "/api/marketplace/search",
        "/calendar",
        "/api/calendar",
        "/api/calendar/ical",
        "/chat",
        "/templates",
        "/api/templates",
        "/agents",
        "/supply-chain",
    ]

    @pytest.mark.parametrize("path", READ_PATHS)
    def test_anon_gets_401_or_403(self, anon_client, path):
        resp = anon_client.get(path)
        assert resp.status_code in (401, 403), (
            f"{path}: expected 401/403 without auth, got {resp.status_code}"
        )

    @pytest.mark.parametrize("path", READ_PATHS)
    def test_viewer_allowed(self, viewer_client, path):
        resp = viewer_client.get(path)
        # 200 / 404 are fine — 401/403 are not
        assert resp.status_code not in (401, 403), (
            f"{path}: viewer should have view_dashboard, got {resp.status_code}"
        )

    @pytest.mark.parametrize("path", READ_PATHS)
    def test_admin_allowed(self, admin_client, path):
        resp = admin_client.get(path)
        assert resp.status_code not in (401, 403), (
            f"{path}: admin should always work, got {resp.status_code}"
        )


# ---------------------------------------------------------------------------
# Write endpoints require run_simulation (editor+)
# ---------------------------------------------------------------------------


class TestWriteProtection:
    @pytest.mark.parametrize(
        "method,path,body",
        [
            ("POST", "/api/marketplace/install/nonexistent-pkg", None),
            ("POST", "/api/calendar/schedule", {"name": "x", "scenario_ids": []}),
            ("DELETE", "/api/calendar/nonexistent-exp", None),
            ("POST", "/api/calendar/auto-schedule", None),
            ("POST", "/api/chat", {"question": "hello"}),
        ],
    )
    def test_anon_rejected(self, anon_client, method, path, body):
        resp = anon_client.request(method, path, json=body)
        assert resp.status_code in (401, 403), (
            f"{method} {path}: expected 401/403 anon, got {resp.status_code}"
        )

    @pytest.mark.parametrize(
        "method,path,body",
        [
            ("POST", "/api/marketplace/install/nonexistent-pkg", None),
            ("POST", "/api/calendar/schedule", {"name": "x", "scenario_ids": []}),
            ("DELETE", "/api/calendar/nonexistent-exp", None),
            ("POST", "/api/calendar/auto-schedule", None),
            ("POST", "/api/chat", {"question": "hello"}),
        ],
    )
    def test_viewer_forbidden(self, viewer_client, method, path, body):
        resp = viewer_client.request(method, path, json=body)
        # Viewer has view_dashboard but NOT run_simulation → 403
        assert resp.status_code == 403, (
            f"{method} {path}: expected 403 for viewer, got {resp.status_code}"
        )

    @pytest.mark.parametrize(
        "method,path,body",
        [
            ("POST", "/api/marketplace/install/nonexistent-pkg", None),
            ("DELETE", "/api/calendar/nonexistent-exp", None),
            ("POST", "/api/chat", {"question": "hello"}),
        ],
    )
    def test_admin_passes_auth(self, admin_client, method, path, body):
        resp = admin_client.request(method, path, json=body)
        # Auth passes; status depends on route logic (404, 400, 200 are all fine)
        assert resp.status_code not in (401, 403), (
            f"{method} {path}: admin rejected with {resp.status_code}"
        )


# ---------------------------------------------------------------------------
# Slack webhook signature verification
# ---------------------------------------------------------------------------


class TestSlackSignature:
    _SECRET = "test-slack-signing-secret-#100"  # pragma: allowlist secret

    def _sign(self, body: str, ts: str) -> str:
        basestring = f"v0:{ts}:{body}".encode()
        return "v0=" + hmac.new(
            self._SECRET.encode(), basestring, hashlib.sha256
        ).hexdigest()

    def test_rejects_without_signing_secret_by_default(self, anon_client):
        # SLACK_SIGNING_SECRET not set, FAULTRAY_ALLOW_UNSIGNED_SLACK not set → reject
        os.environ.pop("SLACK_SIGNING_SECRET", None)
        os.environ.pop("FAULTRAY_ALLOW_UNSIGNED_SLACK", None)
        resp = anon_client.post("/api/slack/commands", data="text=help")
        assert resp.status_code == 401

    def test_rejects_invalid_signature(self, anon_client):
        os.environ["SLACK_SIGNING_SECRET"] = self._SECRET
        try:
            ts = str(int(time.time()))
            resp = anon_client.post(
                "/api/slack/commands",
                data="text=help",
                headers={
                    "x-slack-request-timestamp": ts,
                    "x-slack-signature": "v0=deadbeef",
                },
            )
            assert resp.status_code == 401
        finally:
            os.environ.pop("SLACK_SIGNING_SECRET", None)

    def test_rejects_stale_timestamp(self, anon_client):
        os.environ["SLACK_SIGNING_SECRET"] = self._SECRET
        try:
            ts = str(int(time.time()) - 60 * 10)  # 10 min old
            body = "text=help"
            resp = anon_client.post(
                "/api/slack/commands",
                data=body,
                headers={
                    "x-slack-request-timestamp": ts,
                    "x-slack-signature": self._sign(body, ts),
                },
            )
            assert resp.status_code == 401
        finally:
            os.environ.pop("SLACK_SIGNING_SECRET", None)

    def test_accepts_valid_signature(self, anon_client):
        os.environ["SLACK_SIGNING_SECRET"] = self._SECRET
        try:
            ts = str(int(time.time()))
            body = "text=help&user_id=U123&channel_id=C123"
            resp = anon_client.post(
                "/api/slack/commands",
                data=body,
                headers={
                    "x-slack-request-timestamp": ts,
                    "x-slack-signature": self._sign(body, ts),
                    "content-type": "application/x-www-form-urlencoded",
                },
            )
            # Signature valid — downstream may 200 or 500 depending on slack bot
            # deps, but must not be 401 (signature fail).
            assert resp.status_code != 401, (
                f"Valid signature rejected with {resp.status_code}"
            )
        finally:
            os.environ.pop("SLACK_SIGNING_SECRET", None)

    def test_unsigned_allowed_with_explicit_opt_in(self, anon_client):
        os.environ.pop("SLACK_SIGNING_SECRET", None)
        os.environ["FAULTRAY_ALLOW_UNSIGNED_SLACK"] = "1"
        try:
            resp = anon_client.post("/api/slack/commands", data="text=help")
            # Not rejected by signature check (may still 200/500 from bot logic)
            assert resp.status_code != 401
        finally:
            os.environ.pop("FAULTRAY_ALLOW_UNSIGNED_SLACK", None)
