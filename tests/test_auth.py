"""Tests for API key authentication dependency."""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from faultray.api.auth import (
    PUBLIC_PATHS,
    _is_public,
    generate_api_key,
    get_current_user,
    hash_api_key,
)
from faultray.api.database import Base, UserRow, reset_engine


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def auth_db(tmp_path: Path):
    """Create a temporary database for auth tests."""
    db_path = tmp_path / "auth_test.db"
    url = f"sqlite+aiosqlite:///{db_path}"

    reset_engine()

    engine = create_async_engine(url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory, engine

    await engine.dispose()
    reset_engine()


# ---------------------------------------------------------------------------
# Fake request for testing
# ---------------------------------------------------------------------------

class FakeURL:
    def __init__(self, path: str):
        self.path = path


class FakeRequest:
    def __init__(self, path: str):
        self.url = FakeURL(path)


class FakeCredentials:
    def __init__(self, token: str):
        self.credentials = token


# ---------------------------------------------------------------------------
# Public path tests
# ---------------------------------------------------------------------------

class TestPublicPaths:
    def test_root_is_public(self):
        assert _is_public("/") is True

    def test_docs_is_public(self):
        assert _is_public("/docs") is True

    def test_redoc_is_public(self):
        assert _is_public("/redoc") is True

    def test_openapi_is_public(self):
        assert _is_public("/openapi.json") is True

    def test_demo_is_public(self):
        assert _is_public("/demo") is True

    def test_static_is_public(self):
        assert _is_public("/static") is True

    def test_static_subpath_is_public(self):
        assert _is_public("/static/css/style.css") is True

    def test_components_is_public(self):
        assert _is_public("/components") is True

    def test_simulation_is_public(self):
        assert _is_public("/simulation") is True

    def test_simulation_run_is_public(self):
        assert _is_public("/simulation/run") is True

    def test_api_simulate_is_not_public(self):
        assert _is_public("/api/simulate") is False

    def test_api_runs_is_not_public(self):
        assert _is_public("/api/runs") is False

    def test_api_graph_data_is_not_public(self):
        assert _is_public("/api/graph-data") is False

    def test_random_path_is_not_public(self):
        assert _is_public("/admin/settings") is False


# ---------------------------------------------------------------------------
# get_current_user tests
# ---------------------------------------------------------------------------

class TestGetCurrentUser:
    async def test_public_path_returns_none(self, auth_db):
        """Public paths should always return None, no auth needed."""
        request = FakeRequest("/")
        result = await get_current_user(request, credentials=None)
        assert result is None

    async def test_public_docs_returns_none(self, auth_db):
        request = FakeRequest("/docs")
        result = await get_current_user(request, credentials=None)
        assert result is None

    async def test_protected_path_no_users_returns_none(self, auth_db):
        """When no users exist in DB, auth is disabled (backward-compat)."""
        factory, engine = auth_db

        # Monkey-patch get_session_factory to use our test DB
        import faultray.api.auth as auth_module
        original_factory = auth_module.get_session_factory
        auth_module.get_session_factory = lambda: factory

        try:
            request = FakeRequest("/api/simulate")
            result = await get_current_user(request, credentials=None)
            assert result is None
        finally:
            auth_module.get_session_factory = original_factory

    async def test_protected_path_with_users_no_creds_raises(self, auth_db):
        """When users exist but no credentials provided, should raise 401."""
        factory, engine = auth_db

        # Create a user in the DB
        api_key = generate_api_key()
        key_hash = hash_api_key(api_key)
        async with factory() as session:
            user = UserRow(
                email="test@example.com",
                name="Test",
                api_key_hash=key_hash,
            )
            session.add(user)
            await session.commit()

        import faultray.api.auth as auth_module
        original_factory = auth_module.get_session_factory
        auth_module.get_session_factory = lambda: factory

        try:
            request = FakeRequest("/api/simulate")
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(request, credentials=None)
            assert exc_info.value.status_code == 401
        finally:
            auth_module.get_session_factory = original_factory

    async def test_protected_path_valid_key_returns_user(self, auth_db):
        """Valid API key should return the user."""
        factory, engine = auth_db

        api_key = generate_api_key()
        key_hash = hash_api_key(api_key)
        async with factory() as session:
            user = UserRow(
                email="valid@example.com",
                name="Valid User",
                api_key_hash=key_hash,
            )
            session.add(user)
            await session.commit()

        import faultray.api.auth as auth_module
        original_factory = auth_module.get_session_factory
        auth_module.get_session_factory = lambda: factory

        try:
            request = FakeRequest("/api/simulate")
            creds = FakeCredentials(api_key)
            result = await get_current_user(request, creds)
            assert result is not None
            assert result.email == "valid@example.com"
        finally:
            auth_module.get_session_factory = original_factory

    async def test_protected_path_invalid_key_raises(self, auth_db):
        """Invalid API key should raise 401."""
        factory, engine = auth_db

        api_key = generate_api_key()
        key_hash = hash_api_key(api_key)
        async with factory() as session:
            user = UserRow(
                email="user@example.com",
                name="User",
                api_key_hash=key_hash,
            )
            session.add(user)
            await session.commit()

        import faultray.api.auth as auth_module
        original_factory = auth_module.get_session_factory
        auth_module.get_session_factory = lambda: factory

        try:
            request = FakeRequest("/api/runs")
            creds = FakeCredentials("wrong-api-key-totally-invalid")
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(request, creds)
            assert exc_info.value.status_code == 401
            assert "Invalid" in exc_info.value.detail
        finally:
            auth_module.get_session_factory = original_factory
