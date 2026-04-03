"""Shared test fixtures for FaultRay tests."""

from __future__ import annotations

import asyncio

import pytest

from faultray.api.auth import hash_api_key
from faultray.api.database import (
    Base,
    UserRow,
    get_session_factory,
    _get_engine,
)


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Reset the global rate limiter state before each test.

    The rate limiter uses a sliding-window counter keyed by client IP.
    TestClient always uses the same IP ("testclient"), so after 60 requests
    within the 60-second window, every subsequent request returns 429.
    This fixture clears accumulated request timestamps so each test starts
    with a clean slate regardless of how many other tests have run.
    """
    import faultray.api.server as _srv
    _srv._rate_limiter.requests.clear()
    yield
    # Leave state clean for the next test as well
    _srv._rate_limiter.requests.clear()

# A known test API key for use in tests
TEST_API_KEY = "test-api-key-for-faultray-tests"
TEST_API_KEY_HASH = hash_api_key(TEST_API_KEY)


def _run_async(coro):
    """Run an async coroutine from sync code (no running event loop)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _setup_test_user_async():
    """Create test admin user in DB (async helper).

    Safe to call multiple times — skips if user already exists.
    """
    engine = _get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sf = get_session_factory()
    async with sf() as session:
        from sqlalchemy import select
        result = await session.execute(
            select(UserRow).where(UserRow.api_key_hash == TEST_API_KEY_HASH)
        )
        if result.scalar_one_or_none() is None:
            user = UserRow(
                email="test@faultray.local",
                name="Test Admin",
                api_key_hash=TEST_API_KEY_HASH,
                role="admin",
            )
            session.add(user)
            await session.commit()


def _setup_test_user():
    """Create test admin user in DB (sync helper).

    Safe to call multiple times — skips if user already exists.
    """
    _run_async(_setup_test_user_async())


def _teardown_test_user():
    """Remove test admin user from DB (sync helper)."""
    async def _teardown():
        sf = get_session_factory()
        async with sf() as session:
            from sqlalchemy import delete
            await session.execute(
                delete(UserRow).where(UserRow.api_key_hash == TEST_API_KEY_HASH)
            )
            await session.commit()

    try:
        _run_async(_teardown())
    except Exception:
        pass


@pytest.fixture
def auth_client():
    """Create authenticated FastAPI test client with test admin user."""
    from fastapi.testclient import TestClient
    from faultray.api.server import app

    _setup_test_user()
    client = TestClient(app, raise_server_exceptions=False)
    client.headers["Authorization"] = f"Bearer {TEST_API_KEY}"
    yield client
    _teardown_test_user()


# ---------------------------------------------------------------------------
# E2E redirect: route httpx calls to faultray.com through local ASGI app
# ---------------------------------------------------------------------------

def _install_e2e_httpx_redirect():
    """Monkey-patch httpx.get/post to redirect faultray.com /api/* to local app.

    All /api/* requests are served locally to eliminate network dependency,
    rate-limiting issues, and auth mismatches in CI.  Non-API paths (HTML
    pages like /onboarding) still go to production if reachable.
    """
    try:
        import httpx
    except ImportError:
        return

    from fastapi.testclient import TestClient
    from faultray.api.server import app

    _setup_test_user()

    _local_client = TestClient(app, raise_server_exceptions=False)
    _local_client.headers["Authorization"] = f"Bearer {TEST_API_KEY}"

    _orig_get = httpx.get
    _orig_post = httpx.post

    def _should_redirect(url_str: str) -> str | None:
        """Return local path if the URL should be redirected, else None."""
        if "faultray.com" in url_str:
            path = url_str.split("faultray.com", 1)[1]
            if path.startswith("/api/"):
                return path
        return None

    def _redirected_get(url, **kwargs):
        path = _should_redirect(str(url))
        if path is not None:
            kwargs.pop("timeout", None)
            return _local_client.get(path, **kwargs)
        return _orig_get(url, **kwargs)

    def _redirected_post(url, **kwargs):
        path = _should_redirect(str(url))
        if path is not None:
            kwargs.pop("timeout", None)
            return _local_client.post(path, **kwargs)
        return _orig_post(url, **kwargs)

    httpx.get = _redirected_get  # type: ignore[assignment]
    httpx.post = _redirected_post  # type: ignore[assignment]


try:
    _install_e2e_httpx_redirect()
except Exception:
    # CI environments without a database will fail here — that's OK,
    # the redirect is only needed for E2E tests that hit the local API.
    pass
