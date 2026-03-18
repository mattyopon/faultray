"""Shared test fixtures for FaultRay tests."""

from __future__ import annotations

import asyncio

import pytest

from faultray.api.auth import hash_api_key
from faultray.api.database import (
    Base,
    UserRow,
    get_session_factory,
    reset_engine,
    _get_engine,
)

# A known test API key for use in tests
TEST_API_KEY = "test-api-key-for-faultray-tests"
TEST_API_KEY_HASH = hash_api_key(TEST_API_KEY)


def _run_async(coro):
    """Run an async coroutine from sync code, handling event loop reuse."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
    return loop.run_until_complete(coro)


def _setup_test_user():
    """Create test admin user in DB (sync helper).

    Safe to call multiple times — skips if user already exists.
    """
    async def _setup():
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

    _run_async(_setup())


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
