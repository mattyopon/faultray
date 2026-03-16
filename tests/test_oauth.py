"""Tests for OAuth2 SSO integration."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from faultray.api.oauth import (
    GITHUB_AUTHORIZE_URL,
    GOOGLE_AUTHORIZE_URL,
    OAuthConfig,
    generate_oauth_url,
)


# ---------------------------------------------------------------------------
# OAuthConfig.from_env
# ---------------------------------------------------------------------------

class TestOAuthConfigFromEnv:
    def test_github_config_from_env(self):
        env = {
            "FAULTRAY_OAUTH_GITHUB_CLIENT_ID": "gh-client-id",
            "FAULTRAY_OAUTH_GITHUB_CLIENT_SECRET": "gh-client-secret",
            "FAULTRAY_OAUTH_GITHUB_REDIRECT_URI": "http://example.com/callback",
        }
        with patch.dict(os.environ, env, clear=False):
            config = OAuthConfig.from_env("github")
            assert config is not None
            assert config.provider == "github"
            assert config.client_id == "gh-client-id"
            assert config.client_secret == "gh-client-secret"
            assert config.redirect_uri == "http://example.com/callback"

    def test_google_config_from_env(self):
        env = {
            "FAULTRAY_OAUTH_GOOGLE_CLIENT_ID": "ggl-id",
            "FAULTRAY_OAUTH_GOOGLE_CLIENT_SECRET": "ggl-secret",
        }
        with patch.dict(os.environ, env, clear=False):
            config = OAuthConfig.from_env("google")
            assert config is not None
            assert config.provider == "google"
            assert config.client_id == "ggl-id"
            # Default redirect URI when not specified
            assert "localhost" in config.redirect_uri

    def test_missing_client_id_returns_none(self):
        env = {
            "FAULTRAY_OAUTH_GITHUB_CLIENT_SECRET": "secret-only",
        }
        with patch.dict(os.environ, env, clear=False):
            # Remove CLIENT_ID if it happens to exist
            os.environ.pop("FAULTRAY_OAUTH_GITHUB_CLIENT_ID", None)
            config = OAuthConfig.from_env("github")
            assert config is None

    def test_missing_client_secret_returns_none(self):
        env = {
            "FAULTRAY_OAUTH_GITHUB_CLIENT_ID": "id-only",
        }
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("FAULTRAY_OAUTH_GITHUB_CLIENT_SECRET", None)
            config = OAuthConfig.from_env("github")
            assert config is None

    def test_completely_missing_env_returns_none(self):
        # Ensure vars are not set
        for key in list(os.environ):
            if key.startswith("FAULTRAY_OAUTH_"):
                os.environ.pop(key, None)
        config = OAuthConfig.from_env("github")
        assert config is None

    def test_default_redirect_uri(self):
        env = {
            "FAULTRAY_OAUTH_GITHUB_CLIENT_ID": "id",
            "FAULTRAY_OAUTH_GITHUB_CLIENT_SECRET": "secret",
        }
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("FAULTRAY_OAUTH_GITHUB_REDIRECT_URI", None)
            config = OAuthConfig.from_env("github")
            assert config is not None
            assert config.redirect_uri == "http://localhost:8000/auth/callback"


# ---------------------------------------------------------------------------
# generate_oauth_url
# ---------------------------------------------------------------------------

class TestGenerateOAuthUrl:
    def test_github_url(self):
        config = OAuthConfig(
            provider="github",
            client_id="my-gh-id",
            client_secret="my-gh-secret",
            redirect_uri="http://localhost:8000/auth/callback",
        )
        url = generate_oauth_url(config, state="test-state-123")
        assert url.startswith(GITHUB_AUTHORIZE_URL)
        assert "client_id=my-gh-id" in url
        assert "state=test-state-123" in url
        assert "scope=user:email" in url
        assert "redirect_uri=" in url

    def test_google_url(self):
        config = OAuthConfig(
            provider="google",
            client_id="my-ggl-id",
            client_secret="my-ggl-secret",
            redirect_uri="http://localhost:8000/auth/callback",
        )
        url = generate_oauth_url(config, state="test-state-456")
        assert url.startswith(GOOGLE_AUTHORIZE_URL)
        assert "client_id=my-ggl-id" in url
        assert "state=test-state-456" in url
        assert "response_type=code" in url
        assert "scope=email+profile" in url

    def test_auto_generated_state(self):
        config = OAuthConfig(
            provider="github",
            client_id="id",
            client_secret="secret",
            redirect_uri="http://localhost:8000/auth/callback",
        )
        url = generate_oauth_url(config)
        assert "state=" in url

    def test_unknown_provider_returns_empty(self):
        config = OAuthConfig(
            provider="unknown",
            client_id="id",
            client_secret="secret",
            redirect_uri="http://localhost:8000/auth/callback",
        )
        url = generate_oauth_url(config)
        assert url == ""
