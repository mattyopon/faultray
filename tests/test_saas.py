"""Tests for FaultRay SaaS features: OAuth2, Stripe billing, compliance gating."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from faultray.api.server import app, set_graph
from tests.conftest import TEST_API_KEY, _setup_test_user


@pytest.fixture(autouse=True)
def _reset_db():
    """Reset DB engine so schema changes take effect."""
    from faultray.api.database import reset_engine
    reset_engine()
    yield
    reset_engine()


@pytest.fixture
def client():
    """Create authenticated test client."""
    _setup_test_user()
    return TestClient(
        app,
        raise_server_exceptions=False,
        headers={"Authorization": f"Bearer {TEST_API_KEY}"},
    )


@pytest.fixture
def unauth_client():
    """Create unauthenticated test client."""
    _setup_test_user()
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def demo_graph():
    """Load demo graph for compliance tests."""
    _setup_test_user()
    from faultray.model.demo import create_demo_graph
    g = create_demo_graph()
    set_graph(g)
    yield g
    from faultray.model.graph import InfraGraph
    set_graph(InfraGraph())


# ============================================================================
# OAuth2 Auth Tests
# ============================================================================


class TestOAuthGitHub:
    """Tests for GET /api/v1/auth/github."""

    def test_github_auth_returns_503_when_not_configured(self, unauth_client):
        """Without env vars, GitHub OAuth should return 503."""
        with patch.dict("os.environ", {}, clear=False):
            resp = unauth_client.get("/api/v1/auth/github")
            assert resp.status_code == 503

    def test_github_auth_returns_url_when_configured(self, unauth_client):
        """With env vars set, should return auth_url."""
        env = {
            "FAULTRAY_OAUTH_GITHUB_CLIENT_ID": "test-client-id",
            "FAULTRAY_OAUTH_GITHUB_CLIENT_SECRET": "test-secret",
        }
        with patch.dict("os.environ", env, clear=False):
            resp = unauth_client.get("/api/v1/auth/github")
            assert resp.status_code == 200
            data = resp.json()
            assert "auth_url" in data
            assert "state" in data
            assert "github.com" in data["auth_url"]
            assert "test-client-id" in data["auth_url"]


class TestOAuthGoogle:
    """Tests for GET /api/v1/auth/google."""

    def test_google_auth_returns_503_when_not_configured(self, unauth_client):
        """Without env vars, Google OAuth should return 503."""
        with patch.dict("os.environ", {}, clear=False):
            resp = unauth_client.get("/api/v1/auth/google")
            assert resp.status_code == 503

    def test_google_auth_returns_url_when_configured(self, unauth_client):
        """With env vars set, should return auth_url."""
        env = {
            "FAULTRAY_OAUTH_GOOGLE_CLIENT_ID": "test-client-id",
            "FAULTRAY_OAUTH_GOOGLE_CLIENT_SECRET": "test-secret",
        }
        with patch.dict("os.environ", env, clear=False):
            resp = unauth_client.get("/api/v1/auth/google")
            assert resp.status_code == 200
            data = resp.json()
            assert "auth_url" in data
            assert "state" in data
            assert "accounts.google.com" in data["auth_url"]


class TestOAuthCallback:
    """Tests for GET /api/v1/auth/callback/{provider}."""

    def test_callback_unsupported_provider(self, unauth_client):
        resp = unauth_client.get("/api/v1/auth/callback/twitter?code=abc&state=xyz")
        assert resp.status_code == 400

    def test_callback_missing_code(self, unauth_client):
        resp = unauth_client.get("/api/v1/auth/callback/github")
        assert resp.status_code == 400

    def test_callback_github_not_configured(self, unauth_client):
        with patch.dict("os.environ", {}, clear=False):
            resp = unauth_client.get("/api/v1/auth/callback/github?code=abc&state=xyz")
            assert resp.status_code == 503


# ============================================================================
# JWT Token Tests
# ============================================================================


class TestJWT:
    """Tests for JWT creation and decoding."""

    def test_create_and_decode_jwt(self):
        from faultray.api.oauth import create_jwt, decode_jwt

        payload = {"sub": "123", "email": "test@example.com", "role": "editor"}
        token = create_jwt(payload)
        assert isinstance(token, str)
        assert len(token) > 0

        decoded = decode_jwt(token)
        assert decoded is not None
        assert decoded["sub"] == "123"
        assert decoded["email"] == "test@example.com"

    def test_decode_invalid_jwt(self):
        from faultray.api.oauth import decode_jwt

        result = decode_jwt("invalid-token")
        assert result is None

    def test_jwt_auth_in_api(self, client):
        """JWT token should be accepted for API authentication."""
        from faultray.api.oauth import create_jwt

        # Create a JWT for the test user
        token = create_jwt({"sub": "1", "email": "test@faultray.local", "role": "admin"})
        jwt_client = TestClient(
            app,
            raise_server_exceptions=False,
            headers={"Authorization": f"Bearer {token}"},
        )
        resp = jwt_client.get("/api/v1/health")
        assert resp.status_code == 200


# ============================================================================
# Stripe Billing v1 Tests
# ============================================================================


class TestBillingCheckout:
    """Tests for POST /api/v1/billing/checkout."""

    def test_checkout_disabled_returns_503(self, client):
        """Without Stripe config, should return 503."""
        resp = client.post(
            "/api/v1/billing/checkout",
            json={"tier": "pro", "team_id": "team-1"},
        )
        assert resp.status_code == 503

    def test_checkout_invalid_tier(self, client):
        """Invalid tier should return 400."""
        with patch.dict("os.environ", {"STRIPE_SECRET_KEY": "sk_test_fake"}, clear=False):
            resp = client.post(
                "/api/v1/billing/checkout",
                json={"tier": "invalid", "team_id": "team-1"},
            )
            assert resp.status_code == 400

    def test_checkout_free_tier_rejected(self, client):
        """Cannot purchase free tier."""
        with patch.dict("os.environ", {"STRIPE_SECRET_KEY": "sk_test_fake"}, clear=False):
            resp = client.post(
                "/api/v1/billing/checkout",
                json={"tier": "free", "team_id": "team-1"},
            )
            assert resp.status_code == 400


class TestBillingWebhook:
    """Tests for POST /api/v1/billing/webhook."""

    def test_webhook_disabled_returns_503(self, unauth_client):
        """Without Stripe config, should return 503."""
        resp = unauth_client.post("/api/v1/billing/webhook")
        assert resp.status_code == 503


class TestBillingPortal:
    """Tests for GET /api/v1/billing/portal."""

    def test_portal_missing_team_id(self, client):
        resp = client.get("/api/v1/billing/portal")
        assert resp.status_code == 400

    def test_portal_disabled_returns_503(self, client):
        resp = client.get("/api/v1/billing/portal?team_id=team-1")
        assert resp.status_code == 503


# ============================================================================
# Pricing Tier Tests
# ============================================================================


class TestPricingTiers:
    """Tests for pricing tier configuration."""

    def test_business_tier_exists(self):
        from faultray.api.billing import PricingTier

        assert PricingTier.BUSINESS == "business"

    def test_tier_limits_free(self):
        from faultray.api.billing import PricingTier, TIER_LIMITS

        limits = TIER_LIMITS[PricingTier.FREE]
        assert limits.max_simulations_per_month == 5
        assert limits.compliance_reports is False

    def test_tier_limits_pro(self):
        from faultray.api.billing import PricingTier, TIER_LIMITS

        limits = TIER_LIMITS[PricingTier.PRO]
        assert limits.max_simulations_per_month == 100
        assert limits.compliance_reports is True

    def test_tier_limits_business(self):
        from faultray.api.billing import PricingTier, TIER_LIMITS

        limits = TIER_LIMITS[PricingTier.BUSINESS]
        assert limits.max_simulations_per_month == -1  # unlimited
        assert limits.compliance_reports is True
        assert limits.insurance_api is True
        assert limits.custom_sso is True


# ============================================================================
# Compliance Report Gating Tests
# ============================================================================


class TestComplianceGating:
    """Tests for GET /api/v1/compliance/report tier gating."""

    def test_compliance_report_no_graph(self, client):
        """Without loaded graph, should return 400."""
        resp = client.get("/api/v1/compliance/report?framework=dora")
        assert resp.status_code == 400

    def test_compliance_report_unsupported_framework(self, client, demo_graph):
        resp = client.get("/api/v1/compliance/report?framework=unknown")
        assert resp.status_code == 400

    def test_compliance_report_free_tier_redacted(self, client, demo_graph):
        """Free tier should get redacted report."""
        resp = client.get("/api/v1/compliance/report?framework=dora")
        assert resp.status_code == 200
        data = resp.json()
        assert data["tier"] == "free"
        assert data["full_access"] is False
        assert "overall_score" in data
        assert "upgrade_message" in data
        # Components should be redacted
        for comp in data["report"]["components"]:
            assert "REDACTED" in comp.get("status", "")

    def test_compliance_report_soc2(self, client, demo_graph):
        resp = client.get("/api/v1/compliance/report?framework=soc2")
        assert resp.status_code == 200
        data = resp.json()
        assert data["framework"] == "soc2"
        assert "overall_score" in data

    def test_compliance_report_score_range(self, client, demo_graph):
        resp = client.get("/api/v1/compliance/report?framework=dora")
        data = resp.json()
        assert 0 <= data["overall_score"] <= 100


# ============================================================================
# Database Model Tests
# ============================================================================


class TestUserRowOAuthFields:
    """Tests for UserRow OAuth extensions."""

    def test_user_row_has_oauth_fields(self):
        from faultray.api.database import UserRow

        # Check that the columns exist in the mapped class
        mapper = UserRow.__mapper__
        column_names = [c.key for c in mapper.columns]
        assert "oauth_provider" in column_names
        assert "oauth_id" in column_names
        assert "avatar_url" in column_names
        assert "tier" in column_names


# ============================================================================
# Auth Integration Tests
# ============================================================================


class TestAuthIntegration:
    """Tests for auth system supporting both API key and JWT."""

    def test_api_key_auth_still_works(self, client):
        """Existing API key authentication should still work."""
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200

    def test_auth_public_paths(self):
        """OAuth callback paths should be public."""
        from faultray.api.auth import _is_public

        assert _is_public("/api/v1/auth/github") is True
        assert _is_public("/api/v1/auth/callback/github") is True
        assert _is_public("/api/v1/billing/webhook") is True

    def test_auth_protected_paths(self):
        """Billing and compliance paths should be protected."""
        from faultray.api.auth import _is_public

        assert _is_public("/api/v1/billing/checkout") is False
        assert _is_public("/api/v1/billing/portal") is False
