"""API key authentication for InfraSim."""

from __future__ import annotations

import hashlib
import secrets
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select

from infrasim.api.database import UserRow, get_session_factory

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_bearer_scheme = HTTPBearer(auto_error=False)


def hash_api_key(api_key: str) -> str:
    """Return the SHA-256 hex digest of an API key."""
    return hashlib.sha256(api_key.encode()).hexdigest()


def generate_api_key() -> str:
    """Generate a new random API key (48 URL-safe bytes)."""
    return secrets.token_urlsafe(48)


# ---------------------------------------------------------------------------
# Public endpoints that skip auth
# ---------------------------------------------------------------------------

PUBLIC_PATHS = frozenset({
    "/",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/demo",
    "/static",
    "/components",
    "/simulation",
    "/graph",
    "/simulation/run",
})


def _is_public(path: str) -> bool:
    """Check whether *path* is a public (no-auth) endpoint."""
    if path in PUBLIC_PATHS:
        return True
    # Allow static file sub-paths
    if path.startswith("/static/"):
        return True
    # Allow OAuth login/callback paths
    if path.startswith("/auth/"):
        return True
    return False


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------

async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> UserRow | None:
    """Resolve the current user from the Authorization header.

    Behaviour:
    * Public paths -> returns ``None`` (no auth required).
    * If **no users** exist in the DB at all -> returns ``None``
      (backward-compatible mode, acts as if auth is disabled).
    * Protected paths without valid credentials -> 401.
    """
    # Public endpoints never require auth
    if _is_public(request.url.path):
        return None

    session_factory = get_session_factory()
    async with session_factory() as session:
        # Check if any users exist at all
        count_result = await session.execute(
            select(UserRow.id).limit(1)
        )
        has_users = count_result.scalar_one_or_none() is not None

        if not has_users:
            # No users registered yet -> backward-compatible mode
            return None

        # Users exist -> auth is required for /api/* paths
        if credentials is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing API key. Provide Authorization: Bearer <api_key>",
            )

        key_hash = hash_api_key(credentials.credentials)
        result = await session.execute(
            select(UserRow).where(UserRow.api_key_hash == key_hash)
        )
        user = result.scalar_one_or_none()

        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key.",
            )

        return user
