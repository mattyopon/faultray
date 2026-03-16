"""OAuth2 SSO integration for FaultRay (GitHub and Google providers)."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from typing import Optional

import httpx

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
    """Return a normalised user dict ``{email, name}`` from the provider."""
    if config.provider == "github":
        raw = await get_github_user(access_token)
        return {
            "email": raw.get("email") or f"{raw.get('login', 'unknown')}@github",
            "name": raw.get("name") or raw.get("login", "unknown"),
        }
    elif config.provider == "google":
        raw = await get_google_user(access_token)
        return {
            "email": raw.get("email", "unknown@google"),
            "name": raw.get("name", "unknown"),
        }
    raise RuntimeError(f"Unsupported provider: {config.provider}")
