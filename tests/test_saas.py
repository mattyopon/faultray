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


class TestSaasV1Unauthenticated:
    """#138: every protected v1 SaaS route must return 401 when no user
    can be resolved. Previously the local ``_require_permission`` stub
    always returned a synthetic ``anonymous`` principal, so callers
    reached the endpoint body unauthenticated.
    """

    def test_checkout_unauthenticated_returns_401(self, unauth_client):
        resp = unauth_client.post(
            "/api/v1/billing/checkout",
            json={"tier": "pro", "team_id": "team-1"},
        )
        assert resp.status_code == 401, resp.text

    def test_portal_unauthenticated_returns_401(self, unauth_client):
        resp = unauth_client.get("/api/v1/billing/portal?team_id=team-1")
        assert resp.status_code == 401, resp.text

    def test_compliance_report_unauthenticated_returns_401(self, unauth_client):
        resp = unauth_client.get("/api/v1/compliance/report?framework=dora")
        assert resp.status_code == 401, resp.text


class TestProtectedSaaSEndpointsRejectUnauthenticated:
    """Regression guard (#143): every tier-gated v1 SaaS endpoint must reject
    callers with no credentials. These would have caught the placeholder auth
    dependency that previously let anonymous requests through.
    """

    def test_billing_checkout_requires_auth(self, unauth_client):
        resp = unauth_client.post(
            "/api/v1/billing/checkout", json={"tier": "pro", "team_id": "t1"}
        )
        assert resp.status_code in (401, 403), resp.text

    def test_billing_portal_requires_auth(self, unauth_client):
        resp = unauth_client.get("/api/v1/billing/portal?team_id=t1")
        assert resp.status_code in (401, 403), resp.text

    def test_compliance_report_requires_auth(self, unauth_client):
        resp = unauth_client.get("/api/v1/compliance/report")
        assert resp.status_code in (401, 403), resp.text


# ---------------------------------------------------------------------------
# Billing enforcement: fail-closed usage + idempotent webhooks
# ---------------------------------------------------------------------------


class TestBillingEnforcement:
    """UsageTracker fail-closed behaviour and webhook replay protection."""

    def _temp_sf(self, tmp_path):
        from faultray.api.database import (
            Base,
            get_session_factory,
            reset_engine,
            _get_engine,
        )
        from tests.conftest import _run_async

        db_path = tmp_path / "billing.db"
        url = f"sqlite+aiosqlite:///{db_path}"
        reset_engine()
        engine = _get_engine(url)

        async def _create():
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

        _run_async(_create())
        return get_session_factory(url)

    def test_check_limit_fails_closed_on_db_error(self, tmp_path):
        from faultray.api.billing import UsageTracker
        from tests.conftest import _run_async

        # A session factory that raises -> usage cannot be determined.
        def _broken_sf():
            raise RuntimeError("DB down")

        tracker = UsageTracker(_broken_sf)
        allowed = _run_async(tracker.check_limit("team-x", "simulation"))
        assert allowed is False  # deny, never fail open

    def test_webhook_event_is_idempotent(self, tmp_path):
        from faultray.api.billing import StripeManager
        from faultray.api.database import SubscriptionRow, get_session_factory
        from tests.conftest import _run_async
        from sqlalchemy import select

        _sf = self._temp_sf(tmp_path)
        mgr = StripeManager.__new__(StripeManager)  # bypass Stripe key setup
        mgr._enabled = True

        event = {
            "event_type": "checkout.session.completed",
            "event_id": "evt_123",
            "team_id": "team-idem",
            "tier": "pro",
            "customer_id": "cus_1",
        }

        async def _run():
            await mgr.persist_webhook_event(event)
            # Simulate a later downgrade arriving as a REPLAY of the SAME id.
            replay = {
                "event_type": "customer.subscription.deleted",
                "event_id": "evt_123",
                "team_id": "team-idem",
            }
            await mgr.persist_webhook_event(replay)
            async with get_session_factory()() as session:
                row = (
                    await session.execute(
                        select(SubscriptionRow).where(
                            SubscriptionRow.team_id == "team-idem"
                        )
                    )
                ).scalar_one_or_none()
                return row

        row = _run_async(_run())
        # The replayed event id was ignored, so the pro tier is retained
        # (the duplicate delete did NOT downgrade).
        assert row is not None
        assert row.tier == "pro"

    def test_saas_quota_flag_defaults_off_and_parses(self, monkeypatch):
        """The hosted-SaaS quota gate is OFF unless explicitly enabled, so the
        OSS CLI / self-host is never throttled."""
        from faultray.api.billing import _saas_quota_enabled

        monkeypatch.delenv("FAULTRAY_ENFORCE_QUOTA", raising=False)
        assert _saas_quota_enabled() is False
        for val in ("1", "true", "TRUE", "yes", "on"):
            monkeypatch.setenv("FAULTRAY_ENFORCE_QUOTA", val)
            assert _saas_quota_enabled() is True
        for val in ("0", "false", "", "no", "off"):
            monkeypatch.setenv("FAULTRAY_ENFORCE_QUOTA", val)
            assert _saas_quota_enabled() is False

    def test_free_tier_simulation_quota_enforced(self, tmp_path):
        """A team with no paid subscription is held to the FREE monthly cap."""
        from faultray.api.billing import UsageTracker
        from faultray.api.database import UsageLogRow
        from tests.conftest import _run_async

        sf = self._temp_sf(tmp_path)
        tracker = UsageTracker(sf)

        async def _seed(n):
            async with sf() as session:
                for _ in range(n):
                    session.add(
                        UsageLogRow(
                            team_id="team-free", resource="simulation", quantity=1
                        )
                    )
                await session.commit()

        # FREE tier = 5 simulations / month (no SubscriptionRow -> FREE default).
        _run_async(_seed(4))
        assert _run_async(tracker.check_limit("team-free", "simulation")) is True
        _run_async(_seed(1))  # now AT the limit (5 used)
        assert _run_async(tracker.check_limit("team-free", "simulation")) is False

    def test_track_simulation_records_usage(self, tmp_path):
        """Usage accounting writes one row per recorded simulation."""
        from faultray.api.billing import UsageTracker
        from faultray.api.database import UsageLogRow
        from tests.conftest import _run_async
        from sqlalchemy import select, func

        sf = self._temp_sf(tmp_path)
        tracker = UsageTracker(sf)

        async def _run():
            await tracker.track_simulation("team-track")
            await tracker.track_simulation("team-track")
            async with sf() as session:
                return (
                    await session.execute(
                        select(func.count())
                        .select_from(UsageLogRow)
                        .where(
                            UsageLogRow.team_id == "team-track",
                            UsageLogRow.resource == "simulation",
                        )
                    )
                ).scalar()

        assert _run_async(_run()) == 2

    def test_business_tier_simulations_unlimited(self, tmp_path):
        """A paid Business subscription lifts the monthly simulation cap."""
        from faultray.api.billing import UsageTracker
        from faultray.api.database import SubscriptionRow, UsageLogRow
        from tests.conftest import _run_async

        sf = self._temp_sf(tmp_path)
        tracker = UsageTracker(sf)

        async def _seed():
            async with sf() as session:
                session.add(SubscriptionRow(team_id="team-biz", tier="business"))
                for _ in range(50):
                    session.add(
                        UsageLogRow(
                            team_id="team-biz", resource="simulation", quantity=1
                        )
                    )
                await session.commit()

        _run_async(_seed())
        # Business tier has unlimited (-1) monthly simulations.
        assert _run_async(tracker.check_limit("team-biz", "simulation")) is True

    def test_simulations_this_month_counts_per_key(self, tmp_path):
        """Per-user usage keys are counted independently (no cross-key leak)."""
        from faultray.api.billing import UsageTracker
        from tests.conftest import _run_async

        sf = self._temp_sf(tmp_path)
        tracker = UsageTracker(sf)

        async def _run():
            await tracker.track_simulation("user:1")
            await tracker.track_simulation("user:1")
            await tracker.track_simulation("user:2")
            return (
                await tracker.simulations_this_month("user:1"),
                await tracker.simulations_this_month("user:2"),
                await tracker.simulations_this_month("user:3"),
            )

        assert _run_async(_run()) == (2, 1, 0)

    def test_simulation_quota_exceeded_by_tier(self, tmp_path):
        """The quota gate the /api/simulate route uses: FREE caps, paid unlocks.

        This is the regression guard for the team-id vs billing-workspace-id
        namespace bug -- a Business (paid) user is NEVER throttled regardless of
        usage, while a FREE user is capped.
        """
        from faultray.api.billing import UsageTracker, PricingTier
        from tests.conftest import _run_async

        sf = self._temp_sf(tmp_path)
        tracker = UsageTracker(sf)

        async def _seed(key, n):
            for _ in range(n):
                await tracker.track_simulation(key)

        # FREE = 5/month -> exceeded at 5.
        _run_async(_seed("user:free", 5))
        assert (
            _run_async(
                tracker.simulation_quota_exceeded("user:free", PricingTier.FREE)
            )
            is True
        )
        # PRO = 100/month -> 5 used is well under.
        _run_async(_seed("user:pro", 5))
        assert (
            _run_async(
                tracker.simulation_quota_exceeded("user:pro", PricingTier.PRO)
            )
            is False
        )
        # BUSINESS = unlimited -> never throttled, even past the FREE cap.
        _run_async(_seed("user:biz", 50))
        assert (
            _run_async(
                tracker.simulation_quota_exceeded("user:biz", PricingTier.BUSINESS)
            )
            is False
        )

    def test_resolve_effective_tier_honors_team_subscription(self, tmp_path):
        """A FREE user who belongs to a paid team resolves to the team's tier.

        Regression for the Codex P1: paid plans live in SubscriptionRow (keyed by
        the billing workspace), not UserRow.tier, so the gate must look through
        the team membership or it would 402 a paying Pro/Business member.
        """
        from faultray.api.billing import resolve_billing_context, PricingTier
        from faultray.api.database import SubscriptionRow
        from tests.conftest import _run_async
        from sqlalchemy import text

        sf = self._temp_sf(tmp_path)

        class _U:
            id = 42
            tier = "free"

        async def _seed_and_resolve():
            async with sf() as session:
                # team_workspaces / team_members are created at runtime by
                # teams.py (raw SQL), not Base.metadata -- create them here.
                await session.execute(text(
                    "CREATE TABLE IF NOT EXISTS team_workspaces "
                    "(id TEXT PRIMARY KEY, name TEXT, owner_id TEXT, created_at TEXT)"
                ))
                await session.execute(text(
                    "CREATE TABLE IF NOT EXISTS team_members "
                    "(team_id TEXT, user_id TEXT, role TEXT, joined_at TEXT)"
                ))
                await session.execute(text(
                    "INSERT INTO team_members (team_id, user_id, role) "
                    "VALUES ('ws-hex', '42', 'editor')"
                ))
                session.add(SubscriptionRow(team_id="ws-hex", tier="business"))
                await session.commit()
            return await resolve_billing_context(_U(), session_factory=sf)

        tier, key = _run_async(_seed_and_resolve())
        assert tier == PricingTier.BUSINESS
        # Usage is charged to the paying team's workspace (shared quota).
        assert key == "ws-hex"

    def test_resolve_billing_context_defaults_free_per_user(self, tmp_path):
        """No paid team and tier='free' -> FREE tier keyed per-user."""
        from faultray.api.billing import resolve_billing_context, PricingTier
        from tests.conftest import _run_async

        sf = self._temp_sf(tmp_path)

        class _U:
            id = 7
            tier = "free"

        tier, key = _run_async(resolve_billing_context(_U(), session_factory=sf))
        assert tier == PricingTier.FREE
        assert key == "user:7"

    def test_resolve_billing_context_ambiguous_or_personal_stays_per_user(
        self, tmp_path
    ):
        """Per-team keying only applies for a SINGLE team that STRICTLY raises the
        tier. Multiple equal-tier teams, or a personal tier >= the team tier,
        fall back to per-user so the wrong team is never charged (Codex P2s)."""
        from faultray.api.billing import resolve_billing_context, PricingTier
        from faultray.api.database import SubscriptionRow
        from tests.conftest import _run_async
        from sqlalchemy import text

        sf = self._temp_sf(tmp_path)

        async def _seed_two_pro_teams():
            async with sf() as session:
                await session.execute(text(
                    "CREATE TABLE IF NOT EXISTS team_workspaces "
                    "(id TEXT PRIMARY KEY, name TEXT, owner_id TEXT, created_at TEXT)"
                ))
                await session.execute(text(
                    "CREATE TABLE IF NOT EXISTS team_members "
                    "(team_id TEXT, user_id TEXT, role TEXT, joined_at TEXT)"
                ))
                for ws in ("ws-a", "ws-b"):
                    await session.execute(
                        text(
                            "INSERT INTO team_members (team_id, user_id, role) "
                            "VALUES (:ws, '50', 'editor')"
                        ),
                        {"ws": ws},
                    )
                    session.add(SubscriptionRow(team_id=ws, tier="pro"))
                await session.commit()

        _run_async(_seed_two_pro_teams())

        # (a) Free user in TWO Pro teams: two upgrade workspaces -> ambiguous,
        # so per-user accounting at the caller's OWN (free) tier. We do NOT adopt
        # the team tier when we cannot attribute usage to a single workspace.
        class _Free:
            id = 50
            tier = "free"

        tier, key = _run_async(
            resolve_billing_context(_Free(), session_factory=sf)
        )
        assert tier == PricingTier.FREE
        assert key == "user:50"

        # (b) Personal tier already == team tier: the team did not raise the
        # caller's tier, so charge per-user, not the team.
        class _Pro:
            id = 50
            tier = "pro"

        tier2, key2 = _run_async(
            resolve_billing_context(_Pro(), session_factory=sf)
        )
        assert tier2 == PricingTier.PRO
        assert key2 == "user:50"

    def test_resolve_billing_context_single_converging_rule(self, tmp_path):
        """The one converging rule: charge a team ONLY when EXACTLY ONE workspace
        STRICTLY upgrades the caller; otherwise per-user at the caller's own tier.
        Covers the multi-workspace attribution P2.
        """
        from faultray.api.billing import resolve_billing_context, PricingTier
        from faultray.api.database import SubscriptionRow
        from tests.conftest import _run_async
        from sqlalchemy import text

        sf = self._temp_sf(tmp_path)

        async def _seed(memberships):
            async with sf() as session:
                await session.execute(text(
                    "CREATE TABLE IF NOT EXISTS team_workspaces "
                    "(id TEXT PRIMARY KEY, name TEXT, owner_id TEXT, created_at TEXT)"
                ))
                await session.execute(text(
                    "CREATE TABLE IF NOT EXISTS team_members "
                    "(team_id TEXT, user_id TEXT, role TEXT, joined_at TEXT)"
                ))
                for ws, tier, uid in memberships:
                    await session.execute(
                        text(
                            "INSERT INTO team_members (team_id, user_id, role) "
                            "VALUES (:ws, :uid, 'editor')"
                        ),
                        {"ws": ws, "uid": uid},
                    )
                    session.add(SubscriptionRow(team_id=ws, tier=tier))
                await session.commit()

        # Case 1: own=pro + one pro team -> team does NOT strictly upgrade ->
        # per-user, pro tier.
        _run_async(_seed([("ws-pro1", "pro", "1")]))

        class _U1:
            id = 1
            tier = "pro"

        t, k = _run_async(resolve_billing_context(_U1(), session_factory=sf))
        assert t == PricingTier.PRO
        assert k == "user:1"

        # Case 2: free user in BOTH a Pro and a Business workspace -> two upgrade
        # workspaces (mixed tier) -> per-user, FREE tier (no Business subsidy).
        c2 = tmp_path / "c2"
        c2.mkdir()
        sf2 = self._temp_sf(c2)

        async def _seed2():
            async with sf2() as session:
                await session.execute(text(
                    "CREATE TABLE IF NOT EXISTS team_workspaces "
                    "(id TEXT PRIMARY KEY, name TEXT, owner_id TEXT, created_at TEXT)"
                ))
                await session.execute(text(
                    "CREATE TABLE IF NOT EXISTS team_members "
                    "(team_id TEXT, user_id TEXT, role TEXT, joined_at TEXT)"
                ))
                for ws, tier in (("ws-pro", "pro"), ("ws-biz", "business")):
                    await session.execute(
                        text(
                            "INSERT INTO team_members (team_id, user_id, role) "
                            "VALUES (:ws, '2', 'editor')"
                        ),
                        {"ws": ws},
                    )
                    session.add(SubscriptionRow(team_id=ws, tier=tier))
                await session.commit()

        _run_async(_seed2())

        class _U2:
            id = 2
            tier = "free"

        t, k = _run_async(resolve_billing_context(_U2(), session_factory=sf2))
        assert t == PricingTier.FREE, "mixed-tier ambiguity must not adopt Business"
        assert k == "user:2"

        # Case 4: free + EXACTLY one pro workspace -> intended team path works.
        c4 = tmp_path / "c4"
        c4.mkdir()
        sf4 = self._temp_sf(c4)

        async def _seed4():
            async with sf4() as session:
                await session.execute(text(
                    "CREATE TABLE IF NOT EXISTS team_workspaces "
                    "(id TEXT PRIMARY KEY, name TEXT, owner_id TEXT, created_at TEXT)"
                ))
                await session.execute(text(
                    "CREATE TABLE IF NOT EXISTS team_members "
                    "(team_id TEXT, user_id TEXT, role TEXT, joined_at TEXT)"
                ))
                await session.execute(text(
                    "INSERT INTO team_members (team_id, user_id, role) "
                    "VALUES ('ws-solo-pro', '4', 'editor')"
                ))
                session.add(SubscriptionRow(team_id="ws-solo-pro", tier="pro"))
                await session.commit()

        _run_async(_seed4())

        class _U4:
            id = 4
            tier = "free"

        t, k = _run_async(resolve_billing_context(_U4(), session_factory=sf4))
        assert t == PricingTier.PRO
        assert k == "ws-solo-pro"
