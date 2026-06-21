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
    or ""
)
if not _JWT_SECRET:
    # Fail closed: never fall back to a hard-coded, publicly-known default
    # secret (anyone could forge an admin JWT with it). In any non-explicitly
    # opted-in environment we generate a random, ephemeral per-process secret
    # instead. Tokens signed with it are unforgeable but do not survive a
    # restart — acceptable for local development, never relied on in prod.
    if os.environ.get("FAULTRAY_ENV", "development") == "production":
        raise RuntimeError(
            "FAULTRAY_JWT_SECRET (or JWT_SECRET_KEY) must be set in production"
        )
    _JWT_SECRET = secrets.token_urlsafe(64)
    logger.warning(
        "No FAULTRAY_JWT_SECRET / JWT_SECRET_KEY configured; using a random "
        "ephemeral per-process JWT secret. Sessions will not persist across "
        "restarts. Set FAULTRAY_JWT_SECRET for stable, multi-process auth."
    )
_JWT_ALGORITHM = "HS256"
_JWT_EXPIRY_SECONDS = 86400  # 24 hours


def create_jwt(payload: dict[str, Any]) -> str:
    """Create a signed JWT token.

    Requires ``python-jose``. We deliberately do NOT fall back to an unsigned
    token when the library is missing: an unsigned, attacker-forgeable blob
    accepted as a credential is an authentication bypass (see decode_jwt).
    """
    try:
        from jose import jwt as jose_jwt
    except ImportError as exc:
        raise RuntimeError(
            "JWT issuance requires 'python-jose'. Install it "
            "(pip install 'faultray[saas]') or use API-key authentication."
        ) from exc

    payload = {**payload, "exp": int(time.time()) + _JWT_EXPIRY_SECONDS,
               "iat": int(time.time())}
    return jose_jwt.encode(payload, _JWT_SECRET, algorithm=_JWT_ALGORITHM)


def decode_jwt(token: str) -> dict[str, Any] | None:
    """Decode and verify a signed JWT. Returns None if invalid/expired.

    Fails closed when ``python-jose`` is unavailable: rather than trusting an
    unsigned base64 payload (which anyone could forge), we reject all JWTs so
    the caller falls back to API-key authentication.
    """
    try:
        from jose import jwt as jose_jwt
    except ImportError:
        logger.warning(
            "python-jose not installed; rejecting JWT (no signature verification "
            "available). Install 'faultray[saas]' to enable JWT auth."
        )
        return None

    try:
        return jose_jwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALGORITHM])
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

# Explicit timeout for all outbound provider calls so a stalled provider cannot
# tie up server workers indefinitely.
_HTTP_TIMEOUT = httpx.Timeout(10.0)


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

        Returns ``None`` when the required ``CLIENT_ID`` / ``CLIENT_SECRET``
        variables are not set.
        """
        # NOTE: a previous "legacy prefix" fallback chain read three *identical*
        # prefixes, so it never actually supported any older variable name. The
        # dead chain has been removed; only the documented prefix is consulted.
        prefix = f"FAULTRAY_OAUTH_{provider.upper()}"
        client_id = os.getenv(f"{prefix}_CLIENT_ID")
        client_secret = os.getenv(f"{prefix}_CLIENT_SECRET")
        redirect_uri = os.getenv(
            f"{prefix}_REDIRECT_URI", "http://localhost:8000/auth/callback"
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

    from urllib.parse import urlencode

    # Percent-encode every parameter so a value containing reserved characters
    # ('&', '=', '#', ...) in client_id / redirect_uri / state cannot inject or
    # override other OAuth parameters. ``safe=':'`` keeps the ':' in the fixed
    # ``user:email`` scope literal (and is harmless for the other values).
    if config.provider == "github":
        params = urlencode(
            {
                "client_id": config.client_id,
                "redirect_uri": config.redirect_uri,
                "scope": "user:email",
                "state": state,
            },
            safe=":",
        )
        return f"{GITHUB_AUTHORIZE_URL}?{params}"
    elif config.provider == "google":
        params = urlencode(
            {
                "client_id": config.client_id,
                "redirect_uri": config.redirect_uri,
                "response_type": "code",
                "scope": "email profile",
                "state": state,
            },
            safe=":",
        )
        return f"{GOOGLE_AUTHORIZE_URL}?{params}"
    return ""


# ---------------------------------------------------------------------------
# Token exchange helpers
# ---------------------------------------------------------------------------

def _parse_token_response(resp: "httpx.Response", provider_label: str) -> dict:
    """Validate an OAuth token-endpoint response and return the parsed JSON.

    Checks the HTTP status first and guards against non-JSON bodies (provider
    error pages), converting any failure into a clear ``RuntimeError`` instead
    of letting an opaque ``JSONDecodeError`` escape.
    """
    import json as _json

    try:
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise RuntimeError(
            f"{provider_label} token exchange HTTP error: {exc}"
        ) from exc
    try:
        return resp.json()
    except (ValueError, _json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"{provider_label} token exchange returned a non-JSON response"
        ) from exc


async def exchange_code_for_token(config: OAuthConfig, code: str) -> str:
    """Exchange an authorization *code* for an access token.

    Returns the access token string.

    Raises ``RuntimeError`` on failure.
    """
    if config.provider == "github":
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
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
            data = _parse_token_response(resp, "GitHub")
            token = data.get("access_token")
            if not token:
                raise RuntimeError(f"GitHub token exchange failed: {data}")
            return token

    elif config.provider == "google":
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
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
            data = _parse_token_response(resp, "Google")
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
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        resp = await client.get(
            GITHUB_USER_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        return resp.json()


async def get_google_user(access_token: str) -> dict:
    """Fetch the authenticated Google user profile."""
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        resp = await client.get(
            GOOGLE_USER_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        return resp.json()


async def get_user_profile(config: OAuthConfig, access_token: str) -> dict:
    """Return a normalised user dict ``{email, name, id, avatar_url, email_verified}``.

    ``email_verified`` reflects whether the provider asserts the email is verified;
    callers must require it before linking an OAuth login to an existing account.
    """
    if config.provider == "github":
        raw = await get_github_user(access_token)
        email = raw.get("email")
        # A public GitHub profile email is verified by GitHub.
        email_verified = bool(email)
        if not email:
            # Fetch primary verified email from GitHub API
            try:
                async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                    emails_resp = await client.get(
                        "https://api.github.com/user/emails",
                        headers={"Authorization": f"Bearer {access_token}"},
                    )
                    emails = emails_resp.json()
                    for e in emails:
                        if e.get("primary") and e.get("verified"):
                            email = e["email"]
                            email_verified = True
                            break
                    if not email and emails:
                        # Fallback to the first email, carrying its verified flag.
                        email = emails[0].get("email", "")
                        email_verified = bool(emails[0].get("verified"))
            except Exception:
                email = f"{raw.get('login', 'unknown')}@github"
                email_verified = False
        return {
            "id": str(raw.get("id", "")),
            "email": email or f"{raw.get('login', 'unknown')}@github",
            "name": raw.get("name") or raw.get("login", "unknown"),
            "avatar_url": raw.get("avatar_url", ""),
            "email_verified": email_verified,
        }
    elif config.provider == "google":
        raw = await get_google_user(access_token)
        return {
            "id": str(raw.get("id", "")),
            "email": raw.get("email", "unknown@google"),
            "name": raw.get("name", "unknown"),
            "avatar_url": raw.get("picture", ""),
            # Google userinfo exposes verification under verified_email/email_verified.
            "email_verified": bool(
                raw.get("verified_email") or raw.get("email_verified")
            ),
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
    email_verified: bool = False,
) -> tuple[Any, str]:
    """Find or create a user via OAuth, then return ``(user, jwt_token)``.

    Lookup is by the stable provider identity ``(oauth_provider, oauth_id)``
    FIRST. Linking to an existing *local* account that shares the email is the
    classic pre-account-takeover (nOAuth) lever, so it is only performed when
    the provider asserts the email is verified (``email_verified is True``) and
    the existing account does not already carry a *different* provider identity.

    New-account creation likewise requires a verified email; we never mint an
    account from an unverified or empty provider email.

    Raises ``ValueError`` when the request cannot be satisfied safely (the
    callers translate this into an OAuth failure response).
    """
    from faultray.api.auth import hash_api_key, generate_api_key
    from faultray.api.database import UserRow, get_session_factory
    from sqlalchemy import select

    if not oauth_id:
        raise ValueError("Missing provider account id")

    sf = get_session_factory()
    async with sf() as session:
        # 1. Match on the stable provider identity first.
        result = await session.execute(
            select(UserRow).where(
                UserRow.oauth_provider == provider,
                UserRow.oauth_id == oauth_id,
            )
        )
        user = result.scalar_one_or_none()

        if user is not None:
            # Known identity: refresh mutable profile fields and sign in.
            if avatar_url:
                user.avatar_url = avatar_url
            await session.commit()
            await session.refresh(user)
        else:
            # 2. No identity match. Consider linking to an existing local
            #    account by email ONLY when the email is provider-verified.
            existing_by_email = None
            if email:
                result = await session.execute(
                    select(UserRow).where(UserRow.email == email)
                )
                existing_by_email = result.scalar_one_or_none()

            if existing_by_email is not None:
                if not email_verified:
                    # Unverified email matching an existing account -> refuse to
                    # auto-link (would let an attacker take over the account).
                    raise ValueError(
                        "Email is not verified by the provider; cannot link to "
                        "an existing account"
                    )
                if existing_by_email.oauth_provider and (
                    existing_by_email.oauth_provider != provider
                    or existing_by_email.oauth_id != oauth_id
                ):
                    # Account is already bound to a different provider identity;
                    # do not silently rebind it to this one.
                    raise ValueError(
                        "Account is already linked to a different OAuth identity"
                    )
                # Safe to link the verified email to this provider identity.
                user = existing_by_email
                user.oauth_provider = provider
                user.oauth_id = oauth_id
                if avatar_url:
                    user.avatar_url = avatar_url
                await session.commit()
                await session.refresh(user)
            else:
                # 3. Brand-new account. Require a verified, non-empty email.
                if not email or not email_verified:
                    raise ValueError(
                        "A verified email is required to create an account"
                    )
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

        token = create_jwt({
            "sub": str(user.id),
            "email": user.email,
            "name": user.name,
            "role": user.role,
            "tier": getattr(user, "tier", "free"),
        })

        return user, token
