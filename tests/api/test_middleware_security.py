"""Tests for CORS and session middleware security configuration."""

import importlib
import os
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Helper: keys that must be cleaned from os.environ before each reload
# ---------------------------------------------------------------------------
_ENV_KEYS = [
    "FAULTRAY_CORS_ORIGINS",
    "FAULTRAY_ENV",
    "FAULTRAY_SESSION_SECRET",
    "JWT_SECRET_KEY",
]


def _reload_server(env: dict[str, str]):
    """Patch environment, remove unset keys, and reload the server module."""
    with patch.dict(os.environ, env, clear=False):
        for key in _ENV_KEYS:
            if key not in env:
                os.environ.pop(key, None)
        from faultray.api import server

        importlib.reload(server)
        return server


def _get_session_middleware_kwargs(server):
    """Extract SessionMiddleware kwargs from the app middleware stack."""
    from starlette.middleware.sessions import SessionMiddleware

    for mw in server.app.user_middleware:
        if mw.cls is SessionMiddleware:
            return mw.kwargs
    raise AssertionError("SessionMiddleware not found in app.user_middleware")


# ---------------------------------------------------------------------------
# CORS tests
# ---------------------------------------------------------------------------


def test_cors_origins_unset():
    """No FAULTRAY_CORS_ORIGINS env var -> _cors_origins is empty list."""
    server = _reload_server({})
    assert server._cors_origins == []


def test_cors_wildcard_origin_no_credentials():
    """FAULTRAY_CORS_ORIGINS='*' -> _allow_credentials is False."""
    server = _reload_server({"FAULTRAY_CORS_ORIGINS": "*"})
    assert server._allow_credentials is False


def test_cors_specific_origins_credentials():
    """Specific origins -> _allow_credentials is True."""
    server = _reload_server(
        {"FAULTRAY_CORS_ORIGINS": "https://a.com,https://b.com"}
    )
    assert server._allow_credentials is True


def test_cors_methods_explicit():
    """allow_methods must be an explicit list (no wildcard)."""
    server = _reload_server({})
    assert "*" not in server._cors_methods
    expected_methods = {"GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH", "HEAD"}
    assert set(server._cors_methods) == expected_methods


def test_cors_headers_include_authorization():
    """allow_headers must include Authorization explicitly (MDN spec requirement)."""
    server = _reload_server({})
    assert "Authorization" in server._cors_headers
    assert "*" not in server._cors_headers


# ---------------------------------------------------------------------------
# Session tests
# ---------------------------------------------------------------------------


def test_session_production_no_secret_raises():
    """Production without session secret raises RuntimeError."""
    with pytest.raises(RuntimeError, match="FAULTRAY_SESSION_SECRET"):
        _reload_server({"FAULTRAY_ENV": "production"})


def test_session_production_with_secret():
    """Production with FAULTRAY_SESSION_SECRET set -> no error, secret used."""
    server = _reload_server(
        {"FAULTRAY_ENV": "production", "FAULTRAY_SESSION_SECRET": "xxx"}
    )
    assert server._session_secret == "xxx"


def test_session_development_fallback(caplog):
    """Development without secret -> warning logged, uses dev key."""
    import logging

    with caplog.at_level(logging.WARNING):
        server = _reload_server({"FAULTRAY_ENV": "development"})
    assert server._session_secret == "faultray-dev-session-key"
    assert any("default session secret" in r.message for r in caplog.records)


def test_session_https_only_development():
    """Development -> https_only=False on actual SessionMiddleware."""
    server = _reload_server({"FAULTRAY_ENV": "development"})
    assert server._is_production is False
    mw_kwargs = _get_session_middleware_kwargs(server)
    assert mw_kwargs["https_only"] is False


def test_session_https_only_production():
    """Production with secret -> https_only=True on actual SessionMiddleware."""
    server = _reload_server(
        {"FAULTRAY_ENV": "production", "FAULTRAY_SESSION_SECRET": "xxx"}
    )
    assert server._is_production is True
    mw_kwargs = _get_session_middleware_kwargs(server)
    assert mw_kwargs["https_only"] is True
