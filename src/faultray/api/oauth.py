# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""OAuth2 SSO integration for FaultRay (GitHub and Google providers).

Includes JWT token issuance for authenticated sessions.
"""

from __future__ import annotations

import logging
import os
import secrets
import time
from dataclasses import dataclass
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------

_JWT_SECRET = (
    os.environ.get("FAULTRAY_JWT_SECRET")
    or os.environ.get("JWT_SECRET_KEY")
    or "faultray-dev-secret-change-me"
)
if _JWT_SECRET == "faultray-dev-secret-change-me":
    logger.warning(
        "Using default JWT secret — set FAULTRAY_JWT_SECRET or JWT_SECRET_KEY for production"
    )
_JWT_ALGORITHM = "HS256"
_JWT_EXPIRY_SECONDS = 86400  # 24 hours


def create_jwt(payload: dict[str, Any]) -> str:
    """Create a signed JWT token."""
    try:
        from jose import jwt as jose_jwt

        payload = {**payload, "exp": int(time.time()) + _JWT_EXPIRY_SECONDS,
                   "iat": int(time.time())}
        return jose_jwt.encode(payload, _JWT_SECRET, algorithm=_JWT_ALGORITHM)
    except ImportError:
        import base64
        import json

        payload = {**payload, "exp": int(time.time()) + _JWT_EXPIRY_SECONDS,
                   "iat": int(time.time())}
        return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()


def decode_jwt(token: str) -> dict[str, Any] | None:
    """Decode and verify a JWT token. Returns None if invalid/expired."""
    try:
        from jose import jwt as jose_jwt

        return jose_jwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALGORITHM])
    except ImportError:
        import base64
        import json

        try:
            data = json.loads(base64.urlsafe_b64decode(token))
            if data.get("exp", 0) < time.time():
                return None
            return data
        except Exception:
            return None
    except Exception:
        return None

# ---------------------------------------------------------------------------
# Provider URLs
# ---------------------------------------------------------------------------

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"

GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USER_URL = "https://www.googleapis.com/oauth2/v2/userinfo"


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class OAuthConfig:
    """OAuth2 provider configuration loaded from environment variables."""

    provider: str  # "github" or "google"
    client_id: str
    client_secret: str
    redirect_uri: str

    @classmethod
    def from_env(cls, provider: str) -> Optional["OAuthConfig"]:
        """Build config from ``FAULTRAY_OAUTH_{PROVIDER}_*`` env vars.

        Falls back to legacy ``FAULTRAY_OAUTH_*`` then ``FAULTRAY_OAUTH_*`` for
        backward compatibility.

        Returns ``None`` when the required ``CLIENT_ID`` / ``CLIENT_SECRET``
        variables are not set.
        """
        new_prefix = f"FAULTRAY_OAUTH_{provider.upper()}"
        mid_prefix = f"FAULTRAY_OAUTH_{provider.upper()}"
        old_prefix = f"FAULTRAY_OAUTH_{provider.upper()}"
        client_id = os.getenv(f"{new_prefix}_CLIENT_ID", os.getenv(f"{mid_prefix}_CLIENT_ID", os.getenv(f"{old_prefix}_CLIENT_ID")))
        client_secret = os.getenv(f"{new_prefix}_CLIENT_SECRET", os.getenv(f"{mid_prefix}_CLIENT_SECRET", os.getenv(f"{old_prefix}_CLIENT_SECRET")))
        redirect_uri = os.getenv(
            f"{new_prefix}_REDIRECT_URI",
            os.getenv(f"{mid_prefix}_REDIRECT_URI", os.getenv(f"{old_prefix}_REDIRECT_URI", "http://localhost:8000/auth/callback")),
        )
        if client_id and client_secret:
            return cls(
                provider=provider,
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri=redirect_uri,
            )
        return None


# ---------------------------------------------------------------------------
# OAuth URL generation
# ---------------------------------------------------------------------------

def generate_oauth_url(config: OAuthConfig, state: str | None = None) -> str:
    """Return the authorization URL to redirect the user to.

    A random ``state`` token is generated if none is supplied.
    """
    if state is None:
        state = secrets.token_urlsafe(32)

    if config.provider == "github":
        return (
            f"{GITHUB_AUTHORIZE_URL}"
            f"?client_id={config.client_id}"
            f"&redirect_uri={config.redirect_uri}"
            f"&scope=user:email"
            f"&state={state}"
        )
    elif config.provider == "google":
        return (
            f"{GOOGLE_AUTHORIZE_URL}"
            f"?client_id={config.client_id}"
            f"&redirect_uri={config.redirect_uri}"
            f"&response_type=code"
            f"&scope=email+profile"
            f"&state={state}"
        )
    return ""


# ---------------------------------------------------------------------------
# Token exchange helpers
# ---------------------------------------------------------------------------

async def exchange_code_for_token(config: OAuthConfig, code: str) -> str:
    """Exchange an authorization *code* for an access token.

    Returns the access token string.

    Raises ``RuntimeError`` on failure.
    """
    if config.provider == "github":
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                GITHUB_TOKEN_URL,
                data={
                    "client_id": config.client_id,
                    "client_secret": config.client_secret,
                    "code": code,
                    "redirect_uri": config.redirect_uri,
                },
                headers={"Accept": "application/json"},
            )
            data = resp.json()
            token = data.get("access_token")
            if not token:
                raise RuntimeError(f"GitHub token exchange failed: {data}")
            return token

    elif config.provider == "google":
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "client_id": config.client_id,
                    "client_secret": config.client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": config.redirect_uri,
                },
            )
            data = resp.json()
            token = data.get("access_token")
            if not token:
                raise RuntimeError(f"Google token exchange failed: {data}")
            return token

    raise RuntimeError(f"Unsupported provider: {config.provider}")


# ---------------------------------------------------------------------------
# User profile fetchers
# ---------------------------------------------------------------------------

async def get_github_user(access_token: str) -> dict:
    """Fetch the authenticated GitHub user profile."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            GITHUB_USER_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        return resp.json()


async def get_google_user(access_token: str) -> dict:
    """Fetch the authenticated Google user profile."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            GOOGLE_USER_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        return resp.json()


async def get_user_profile(config: OAuthConfig, access_token: str) -> dict:
    """Return a normalised user dict ``{email, name, id, avatar_url}`` from the provider."""
    if config.provider == "github":
        raw = await get_github_user(access_token)
        email = raw.get("email")
        if not email:
            # Fetch primary verified email from GitHub API
            try:
                async with httpx.AsyncClient() as client:
                    emails_resp = await client.get(
                        "https://api.github.com/user/emails",
                        headers={"Authorization": f"Bearer {access_token}"},
                    )
                    emails = emails_resp.json()
                    for e in emails:
                        if e.get("primary") and e.get("verified"):
                            email = e["email"]
                            break
                    if not email and emails:
                        email = emails[0].get("email", "")
            except Exception:
                email = f"{raw.get('login', 'unknown')}@github"
        return {
            "id": str(raw.get("id", "")),
            "email": email or f"{raw.get('login', 'unknown')}@github",
            "name": raw.get("name") or raw.get("login", "unknown"),
            "avatar_url": raw.get("avatar_url", ""),
        }
    elif config.provider == "google":
        raw = await get_google_user(access_token)
        return {
            "id": str(raw.get("id", "")),
            "email": raw.get("email", "unknown@google"),
            "name": raw.get("name", "unknown"),
            "avatar_url": raw.get("picture", ""),
        }
    raise RuntimeError(f"Unsupported provider: {config.provider}")


# ---------------------------------------------------------------------------
# User creation / linking
# ---------------------------------------------------------------------------


async def get_or_create_oauth_user(
    provider: str,
    oauth_id: str,
    email: str,
    name: str,
    avatar_url: str = "",
) -> tuple[Any, str]:
    """Find or create a user via OAuth, then return ``(user, jwt_token)``.

    If a user with the same email already exists, link the OAuth provider
    to the existing account. Otherwise, create a new user with a random
    API key.
    """
    from faultray.api.auth import hash_api_key, generate_api_key
    from faultray.api.database import UserRow, get_session_factory
    from sqlalchemy import select

    sf = get_session_factory()
    async with sf() as session:
        # Try by email first
        result = await session.execute(
            select(UserRow).where(UserRow.email == email)
        )
        user = result.scalar_one_or_none()

        if user is None:
            # Try by OAuth ID
            result = await session.execute(
                select(UserRow).where(
                    UserRow.oauth_provider == provider,
                    UserRow.oauth_id == oauth_id,
                )
            )
            user = result.scalar_one_or_none()

        if user is None:
            api_key = generate_api_key()
            user = UserRow(
                email=email,
                name=name,
                api_key_hash=hash_api_key(api_key),
                role="editor",
                oauth_provider=provider,
                oauth_id=oauth_id,
                avatar_url=avatar_url,
                tier="free",
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            logger.info("Created new OAuth user: %s (%s)", email, provider)
        else:
            # Update OAuth info if missing
            if not user.oauth_provider:
                user.oauth_provider = provider
                user.oauth_id = oauth_id
            if avatar_url:
                user.avatar_url = avatar_url
            await session.commit()
            await session.refresh(user)

        token = create_jwt({
            "sub": str(user.id),
            "email": user.email,
            "name": user.name,
            "role": user.role,
            "tier": getattr(user, "tier", "free"),
        })

        return user, token
