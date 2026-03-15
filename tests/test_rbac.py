"""Tests for RBAC (Role-Based Access Control) in FaultZero."""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from infrasim.api.auth import (
    Role,
    ROLE_PERMISSIONS,
    generate_api_key,
    hash_api_key,
    require_permission,
)
from infrasim.api.database import Base, UserRow, reset_engine


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def rbac_db(tmp_path: Path):
    """Create a temporary database for RBAC tests."""
    db_path = tmp_path / "rbac_test.db"
    url = f"sqlite+aiosqlite:///{db_path}"

    reset_engine()

    engine = create_async_engine(url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory, engine

    await engine.dispose()
    reset_engine()


class FakeURL:
    def __init__(self, path: str):
        self.path = path


class FakeRequest:
    def __init__(self, path: str):
        self.url = FakeURL(path)


class FakeCredentials:
    def __init__(self, token: str):
        self.credentials = token
        self.scheme = "Bearer"


async def _create_user(factory, email: str, name: str, role: str = "viewer"):
    """Helper to create a user with a given role. Returns (user, api_key)."""
    api_key = generate_api_key()
    key_hash = hash_api_key(api_key)
    async with factory() as session:
        user = UserRow(
            email=email,
            name=name,
            api_key_hash=key_hash,
            role=role,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user, api_key


# ---------------------------------------------------------------------------
# Role enum tests
# ---------------------------------------------------------------------------

class TestRoleEnum:
    def test_admin_value(self):
        assert Role.ADMIN == "admin"

    def test_editor_value(self):
        assert Role.EDITOR == "editor"

    def test_viewer_value(self):
        assert Role.VIEWER == "viewer"

    def test_role_from_string(self):
        assert Role("admin") is Role.ADMIN
        assert Role("editor") is Role.EDITOR
        assert Role("viewer") is Role.VIEWER

    def test_invalid_role(self):
        with pytest.raises(ValueError):
            Role("superuser")


# ---------------------------------------------------------------------------
# Role permissions tests
# ---------------------------------------------------------------------------

class TestRolePermissions:
    def test_admin_has_wildcard(self):
        assert "*" in ROLE_PERMISSIONS[Role.ADMIN]

    def test_editor_can_run_simulation(self):
        assert "run_simulation" in ROLE_PERMISSIONS[Role.EDITOR]

    def test_editor_can_create_project(self):
        assert "create_project" in ROLE_PERMISSIONS[Role.EDITOR]

    def test_editor_can_view_results(self):
        assert "view_results" in ROLE_PERMISSIONS[Role.EDITOR]

    def test_viewer_can_view_results(self):
        assert "view_results" in ROLE_PERMISSIONS[Role.VIEWER]

    def test_viewer_cannot_run_simulation(self):
        assert "run_simulation" not in ROLE_PERMISSIONS[Role.VIEWER]

    def test_viewer_cannot_create_project(self):
        assert "create_project" not in ROLE_PERMISSIONS[Role.VIEWER]

    def test_viewer_can_export_results(self):
        assert "export_results" in ROLE_PERMISSIONS[Role.VIEWER]

    def test_editor_can_export_results(self):
        assert "export_results" in ROLE_PERMISSIONS[Role.EDITOR]


# ---------------------------------------------------------------------------
# require_permission dependency tests
# ---------------------------------------------------------------------------

class TestRequirePermission:
    async def test_no_auth_mode_allows_all(self, rbac_db):
        """When no users exist in DB, RBAC is opt-in — allow everything."""
        factory, engine = rbac_db

        import infrasim.api.auth as auth_module
        original_factory = auth_module.get_session_factory
        auth_module.get_session_factory = lambda: factory

        try:
            checker = require_permission("run_simulation")
            request = FakeRequest("/api/simulate")
            result = await checker(request)
            # No users -> backward-compatible mode -> returns None (allowed)
            assert result is None
        finally:
            auth_module.get_session_factory = original_factory

    async def test_admin_has_all_permissions(self, rbac_db):
        """Admin user should pass any permission check."""
        factory, engine = rbac_db
        _, api_key = await _create_user(factory, "admin@test.com", "Admin", "admin")

        import infrasim.api.auth as auth_module
        original_factory = auth_module.get_session_factory
        auth_module.get_session_factory = lambda: factory

        try:
            checker = require_permission("run_simulation")
            request = FakeRequest("/api/simulate")
            # Inject credentials via the bearer scheme
            from fastapi.security import HTTPBearer
            auth_module._bearer_scheme = HTTPBearer(auto_error=False)

            # Mock the bearer scheme to return our credentials
            original_resolve = auth_module._resolve_user

            async def mock_resolve(req):
                from infrasim.api.auth import get_current_user
                creds = FakeCredentials(api_key)
                return await get_current_user(req, creds)

            auth_module._resolve_user = mock_resolve
            try:
                result = await checker(request)
                assert result is not None
                assert result.role == "admin"
            finally:
                auth_module._resolve_user = original_resolve
        finally:
            auth_module.get_session_factory = original_factory

    async def test_editor_can_run_simulation(self, rbac_db):
        """Editor should be allowed to run simulations."""
        factory, engine = rbac_db
        _, api_key = await _create_user(factory, "editor@test.com", "Editor", "editor")

        import infrasim.api.auth as auth_module
        original_factory = auth_module.get_session_factory
        auth_module.get_session_factory = lambda: factory

        try:
            checker = require_permission("run_simulation")
            request = FakeRequest("/api/simulate")

            original_resolve = auth_module._resolve_user

            async def mock_resolve(req):
                from infrasim.api.auth import get_current_user
                creds = FakeCredentials(api_key)
                return await get_current_user(req, creds)

            auth_module._resolve_user = mock_resolve
            try:
                result = await checker(request)
                assert result is not None
                assert result.role == "editor"
            finally:
                auth_module._resolve_user = original_resolve
        finally:
            auth_module.get_session_factory = original_factory

    async def test_viewer_cannot_run_simulation(self, rbac_db):
        """Viewer should be denied run_simulation permission."""
        factory, engine = rbac_db
        _, api_key = await _create_user(factory, "viewer@test.com", "Viewer", "viewer")

        import infrasim.api.auth as auth_module
        original_factory = auth_module.get_session_factory
        auth_module.get_session_factory = lambda: factory

        try:
            checker = require_permission("run_simulation")
            request = FakeRequest("/api/simulate")

            original_resolve = auth_module._resolve_user

            async def mock_resolve(req):
                from infrasim.api.auth import get_current_user
                creds = FakeCredentials(api_key)
                return await get_current_user(req, creds)

            auth_module._resolve_user = mock_resolve
            try:
                with pytest.raises(HTTPException) as exc_info:
                    await checker(request)
                assert exc_info.value.status_code == 403
                assert "run_simulation" in exc_info.value.detail
            finally:
                auth_module._resolve_user = original_resolve
        finally:
            auth_module.get_session_factory = original_factory

    async def test_viewer_can_view_results(self, rbac_db):
        """Viewer should be allowed to view results."""
        factory, engine = rbac_db
        _, api_key = await _create_user(factory, "viewer2@test.com", "Viewer2", "viewer")

        import infrasim.api.auth as auth_module
        original_factory = auth_module.get_session_factory
        auth_module.get_session_factory = lambda: factory

        try:
            checker = require_permission("view_results")
            request = FakeRequest("/api/runs")

            original_resolve = auth_module._resolve_user

            async def mock_resolve(req):
                from infrasim.api.auth import get_current_user
                creds = FakeCredentials(api_key)
                return await get_current_user(req, creds)

            auth_module._resolve_user = mock_resolve
            try:
                result = await checker(request)
                assert result is not None
                assert result.role == "viewer"
            finally:
                auth_module._resolve_user = original_resolve
        finally:
            auth_module.get_session_factory = original_factory

    async def test_viewer_cannot_create_project(self, rbac_db):
        """Viewer should be denied create_project permission."""
        factory, engine = rbac_db
        _, api_key = await _create_user(factory, "viewer3@test.com", "Viewer3", "viewer")

        import infrasim.api.auth as auth_module
        original_factory = auth_module.get_session_factory
        auth_module.get_session_factory = lambda: factory

        try:
            checker = require_permission("create_project")
            request = FakeRequest("/api/projects")

            original_resolve = auth_module._resolve_user

            async def mock_resolve(req):
                from infrasim.api.auth import get_current_user
                creds = FakeCredentials(api_key)
                return await get_current_user(req, creds)

            auth_module._resolve_user = mock_resolve
            try:
                with pytest.raises(HTTPException) as exc_info:
                    await checker(request)
                assert exc_info.value.status_code == 403
                assert "create_project" in exc_info.value.detail
            finally:
                auth_module._resolve_user = original_resolve
        finally:
            auth_module.get_session_factory = original_factory

    async def test_editor_can_create_project(self, rbac_db):
        """Editor should be allowed to create projects."""
        factory, engine = rbac_db
        _, api_key = await _create_user(factory, "editor2@test.com", "Editor2", "editor")

        import infrasim.api.auth as auth_module
        original_factory = auth_module.get_session_factory
        auth_module.get_session_factory = lambda: factory

        try:
            checker = require_permission("create_project")
            request = FakeRequest("/api/projects")

            original_resolve = auth_module._resolve_user

            async def mock_resolve(req):
                from infrasim.api.auth import get_current_user
                creds = FakeCredentials(api_key)
                return await get_current_user(req, creds)

            auth_module._resolve_user = mock_resolve
            try:
                result = await checker(request)
                assert result is not None
                assert result.role == "editor"
            finally:
                auth_module._resolve_user = original_resolve
        finally:
            auth_module.get_session_factory = original_factory

    async def test_default_role_is_viewer(self, rbac_db):
        """Users created without explicit role should default to viewer."""
        factory, engine = rbac_db
        api_key = generate_api_key()
        key_hash = hash_api_key(api_key)

        async with factory() as session:
            user = UserRow(
                email="default@test.com",
                name="Default",
                api_key_hash=key_hash,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            assert user.role == "viewer"

    async def test_admin_can_do_anything(self, rbac_db):
        """Admin wildcard should allow any permission string."""
        factory, engine = rbac_db
        _, api_key = await _create_user(factory, "admin2@test.com", "Admin2", "admin")

        import infrasim.api.auth as auth_module
        original_factory = auth_module.get_session_factory
        auth_module.get_session_factory = lambda: factory

        try:
            # Check an arbitrary permission name
            checker = require_permission("nonexistent_permission_xyz")
            request = FakeRequest("/api/some-endpoint")

            original_resolve = auth_module._resolve_user

            async def mock_resolve(req):
                from infrasim.api.auth import get_current_user
                creds = FakeCredentials(api_key)
                return await get_current_user(req, creds)

            auth_module._resolve_user = mock_resolve
            try:
                result = await checker(request)
                assert result is not None
                assert result.role == "admin"
            finally:
                auth_module._resolve_user = original_resolve
        finally:
            auth_module.get_session_factory = original_factory


# ---------------------------------------------------------------------------
# UserRow role column tests
# ---------------------------------------------------------------------------

class TestUserRowRole:
    async def test_user_with_admin_role(self, rbac_db):
        factory, _ = rbac_db
        user, _ = await _create_user(factory, "admin@role.com", "Admin", "admin")
        assert user.role == "admin"

    async def test_user_with_editor_role(self, rbac_db):
        factory, _ = rbac_db
        user, _ = await _create_user(factory, "editor@role.com", "Editor", "editor")
        assert user.role == "editor"

    async def test_user_with_viewer_role(self, rbac_db):
        factory, _ = rbac_db
        user, _ = await _create_user(factory, "viewer@role.com", "Viewer", "viewer")
        assert user.role == "viewer"
