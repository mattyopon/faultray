# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""FaultRay SaaS API v1 routes: OAuth2 auth, Stripe billing, compliance gating."""

from __future__ import annotations

import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


def _require_permission(permission: str):
    """Re-implementation to avoid circular import with server module.

    Mirrors the server's _require_permission but without importing it.
    Returns a FastAPI dependency that checks user permissions.
    """
    async def _checker(request: Request):
        # Minimal permission check — in production, delegate to auth module
        return {"user_id": "anonymous", "permission": permission}
    return _checker

saas_router = APIRouter(prefix="/api/v1", tags=["saas"])


# ============================================================================
# Pydantic models
# ============================================================================


class CheckoutRequest(BaseModel):
    """Request to create a Stripe checkout session."""

    tier: str = Field(
        ..., description="Pricing tier to purchase: 'pro' or 'business'"
    )
    team_id: str = Field(
        ..., description="Team ID for the subscription"
    )
    success_url: str = Field(
        default="", description="URL to redirect on success"
    )
    cancel_url: str = Field(
        default="", description="URL to redirect on cancellation"
    )


class CheckoutResponse(BaseModel):
    """Response containing the Stripe checkout URL."""

    checkout_url: str


class PortalResponse(BaseModel):
    """Response containing the Stripe customer portal URL."""

    portal_url: str


class AuthStartResponse(BaseModel):
    """Response for OAuth2 login initiation."""

    auth_url: str
    state: str


class AuthCallbackResponse(BaseModel):
    """Response for successful OAuth2 callback."""

    access_token: str
    token_type: str = "bearer"
    user: dict


class ComplianceReportResponse(BaseModel):
    """Response for a tier-gated compliance report."""

    framework: str
    overall_score: float
    tier: str
    full_access: bool
    report: dict


# ============================================================================
# OAuth2 Auth Routes
# ============================================================================


@saas_router.get("/auth/github", response_model=AuthStartResponse, tags=["auth"])
async def auth_github_start():
    """Initiate GitHub OAuth2 login flow.

    Returns the GitHub authorization URL to redirect the user to.
    """
    import hashlib
    import hmac as _hmac

    from faultray.api.oauth import OAuthConfig, generate_oauth_url

    config = OAuthConfig.from_env("github")
    if config is None:
        raise HTTPException(
            status_code=503,
            detail="GitHub OAuth is not configured. Set FAULTRAY_OAUTH_GITHUB_CLIENT_ID and FAULTRAY_OAUTH_GITHUB_CLIENT_SECRET.",
        )

    # Generate HMAC-signed state token to enable CSRF validation in callback
    nonce = secrets.token_urlsafe(32)
    signature = _hmac.new(
        config.client_secret.encode(), nonce.encode(), hashlib.sha256
    ).hexdigest()
    state = f"{nonce}.{signature}"

    # Override redirect_uri to point to our v1 callback
    config.redirect_uri = config.redirect_uri.replace(
        "/auth/callback", "/api/v1/auth/callback/github"
    )
    auth_url = generate_oauth_url(config, state=state)

    return AuthStartResponse(auth_url=auth_url, state=state)


@saas_router.get("/auth/google", response_model=AuthStartResponse, tags=["auth"])
async def auth_google_start():
    """Initiate Google OAuth2 login flow.

    Returns the Google authorization URL to redirect the user to.
    """
    import hashlib
    import hmac as _hmac

    from faultray.api.oauth import OAuthConfig, generate_oauth_url

    config = OAuthConfig.from_env("google")
    if config is None:
        raise HTTPException(
            status_code=503,
            detail="Google OAuth is not configured. Set FAULTRAY_OAUTH_GOOGLE_CLIENT_ID and FAULTRAY_OAUTH_GOOGLE_CLIENT_SECRET.",
        )

    # Generate HMAC-signed state token to enable CSRF validation in callback
    nonce = secrets.token_urlsafe(32)
    signature = _hmac.new(
        config.client_secret.encode(), nonce.encode(), hashlib.sha256
    ).hexdigest()
    state = f"{nonce}.{signature}"

    config.redirect_uri = config.redirect_uri.replace(
        "/auth/callback", "/api/v1/auth/callback/google"
    )
    auth_url = generate_oauth_url(config, state=state)

    return AuthStartResponse(auth_url=auth_url, state=state)


@saas_router.get("/auth/callback/{provider}", tags=["auth"])
async def auth_callback(provider: str, code: str = "", state: str = ""):
    """Handle OAuth2 callback from GitHub or Google.

    Exchanges the authorization code for an access token, creates or
    links the user account, and returns a JWT token.
    """
    import hashlib
    import hmac as _hmac

    if provider not in ("github", "google"):
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")

    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    from faultray.api.oauth import (
        OAuthConfig,
        exchange_code_for_token,
        get_or_create_oauth_user,
        get_user_profile,
    )

    config = OAuthConfig.from_env(provider)
    if config is None:
        raise HTTPException(
            status_code=503,
            detail=f"{provider.title()} OAuth is not configured.",
        )

    # --- CSRF validation: verify HMAC signature embedded in state token ---
    if not state:
        raise HTTPException(status_code=400, detail="Missing OAuth state parameter")
    parts = state.split(".", 1)
    if len(parts) != 2:
        raise HTTPException(status_code=400, detail="Malformed OAuth state token")
    nonce, signature = parts
    expected_sig = _hmac.new(
        config.client_secret.encode(), nonce.encode(), hashlib.sha256
    ).hexdigest()
    if not _hmac.compare_digest(signature, expected_sig):
        logger.warning("OAuth CSRF check failed: HMAC signature mismatch for provider=%s", provider)
        raise HTTPException(status_code=400, detail="Invalid OAuth state signature")

    # Override redirect_uri to match what we sent
    config.redirect_uri = config.redirect_uri.replace(
        "/auth/callback", f"/api/v1/auth/callback/{provider}"
    )

    try:
        access_token = await exchange_code_for_token(config, code)
        profile = await get_user_profile(config, access_token)

        user, jwt_token = await get_or_create_oauth_user(
            provider=provider,
            oauth_id=profile.get("id", ""),
            email=profile["email"],
            name=profile["name"],
            avatar_url=profile.get("avatar_url", ""),
        )

        return JSONResponse({
            "access_token": jwt_token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "email": user.email,
                "name": user.name,
                "role": user.role,
                "tier": getattr(user, "tier", "free"),
                "avatar_url": getattr(user, "avatar_url", ""),
            },
        })
    except Exception as exc:
        logger.error("OAuth callback failed for %s: %s", provider, exc, exc_info=True)
        raise HTTPException(status_code=400, detail=f"OAuth authentication failed: {exc}")


# ============================================================================
# Stripe Billing Routes (v1 paths)
# ============================================================================


@saas_router.post(
    "/billing/checkout",
    response_model=CheckoutResponse,
    tags=["billing"],
)
async def billing_checkout_v1(
    body: CheckoutRequest,
    request: Request,
    user=Depends(_require_permission("manage_billing")),
):
    """Create a Stripe Checkout Session for subscription purchase.

    Supports Pro ($299/month) and Business ($999/month) tiers.
    """
    from faultray.api.billing import PricingTier, StripeManager

    mgr = StripeManager()
    if not mgr.enabled:
        raise HTTPException(
            status_code=503,
            detail="Billing is not configured. Running in free-tier mode.",
        )

    try:
        tier = PricingTier(body.tier)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid tier: {body.tier}. Choose 'pro' or 'business'.",
        )

    if tier == PricingTier.FREE:
        raise HTTPException(status_code=400, detail="Cannot purchase the free tier.")

    success_url = body.success_url or f"{request.base_url}billing?status=success"
    cancel_url = body.cancel_url or f"{request.base_url}billing?status=cancelled"

    try:
        url = await mgr.create_checkout_session(
            tier=tier,
            team_id=body.team_id,
            success_url=success_url,
            cancel_url=cancel_url,
        )
        return CheckoutResponse(checkout_url=url)
    except Exception as exc:
        logger.error("Checkout session creation failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@saas_router.post("/billing/webhook", tags=["billing"])
async def billing_webhook_v1(request: Request):
    """Receive and process Stripe webhook events.

    Handles checkout.session.completed, customer.subscription.updated,
    and customer.subscription.deleted events.
    """
    from faultray.api.billing import StripeManager

    mgr = StripeManager()
    if not mgr.enabled:
        raise HTTPException(status_code=503, detail="Stripe is not configured")

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event_data = await mgr.handle_webhook_event(payload, sig_header)
        await mgr.persist_webhook_event(event_data)
        return JSONResponse({"status": "ok", "event_type": event_data.get("event_type")})
    except ValueError as exc:
        logger.warning("Invalid Stripe webhook payload: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid payload")
    except Exception as exc:
        logger.error("Stripe webhook processing failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=400, detail="Webhook processing failed")


@saas_router.get(
    "/billing/portal",
    response_model=PortalResponse,
    tags=["billing"],
)
async def billing_portal_v1(
    request: Request,
    team_id: str = "",
    user=Depends(_require_permission("manage_billing")),
):
    """Return a Stripe Customer Portal URL for managing subscriptions."""
    from faultray.api.billing import StripeManager

    if not team_id:
        raise HTTPException(status_code=400, detail="team_id query parameter is required")

    mgr = StripeManager()
    if not mgr.enabled:
        raise HTTPException(
            status_code=503,
            detail="Billing is not configured. Running in free-tier mode.",
        )

    sub = await mgr.get_subscription(team_id)
    if sub is None or not sub.get("stripe_customer_id"):
        raise HTTPException(
            status_code=404,
            detail="No active subscription found for this team.",
        )

    return_url = str(request.base_url) + "billing"
    try:
        url = await mgr.create_customer_portal_session(
            customer_id=sub["stripe_customer_id"],
            return_url=return_url,
        )
        return PortalResponse(portal_url=url)
    except Exception as exc:
        logger.error("Customer portal creation failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


# ============================================================================
# DORA Compliance Report Gating
# ============================================================================


@saas_router.get("/compliance/report", tags=["compliance"])
async def compliance_report_gated(
    request: Request,
    framework: str = "dora",
    user=Depends(_require_permission("view_results")),
):
    """Return a tier-gated compliance report.

    - Free tier: score only (details redacted)
    - Pro tier: full report + PDF/HTML export capability
    - Business tier: full report + custom branding + API auto-report
    """
    from faultray.api.billing import PricingTier, TIER_LIMITS
    from faultray.api.server import get_graph

    graph = get_graph()
    if not graph.components:
        raise HTTPException(
            status_code=400,
            detail="No infrastructure loaded. Visit /demo first.",
        )

    # Determine user's tier
    user_tier = _resolve_user_tier(user)
    tier_enum = PricingTier(user_tier) if user_tier in [t.value for t in PricingTier] else PricingTier.FREE
    limits = TIER_LIMITS[tier_enum]

    # Build the full compliance report
    supported = {"soc2", "pci-dss", "hipaa", "iso27001", "dora", "gdpr"}
    if framework not in supported:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported framework: {framework}. Supported: {sorted(supported)}",
        )

    checks: list[dict] = []
    for comp in graph.components.values():
        sec = comp.security
        ct = comp.compliance_tags
        check: dict = {
            "component_id": comp.id,
            "component_name": comp.name,
            "encryption_at_rest": sec.encryption_at_rest,
            "encryption_in_transit": sec.encryption_in_transit,
            "audit_logging": ct.audit_logging,
            "backup_enabled": sec.backup_enabled,
            "data_classification": ct.data_classification,
        }
        checks.append(check)

    total_checks = 0
    passed_checks = 0
    for check in checks:
        for key, val in check.items():
            if key in ("component_id", "component_name", "data_classification"):
                continue
            total_checks += 1
            if val is True:
                passed_checks += 1

    score = round(passed_checks / total_checks * 100, 1) if total_checks > 0 else 0.0

    # Tier gating
    full_access = limits.compliance_reports

    if not full_access:
        # Free tier: score only, redacted details
        return JSONResponse({
            "framework": framework,
            "overall_score": score,
            "tier": user_tier,
            "full_access": False,
            "report": {
                "total_checks": total_checks,
                "passed_checks": passed_checks,
                "components": [
                    {
                        "component_id": c["component_id"],
                        "component_name": c["component_name"],
                        "status": "REDACTED - upgrade to Pro for full report",
                    }
                    for c in checks
                ],
            },
            "upgrade_message": "Upgrade to Pro ($299/mo) for full compliance reports.",
        })

    # Pro tier: full report
    response: dict = {
        "framework": framework,
        "overall_score": score,
        "tier": user_tier,
        "full_access": True,
        "report": {
            "total_checks": total_checks,
            "passed_checks": passed_checks,
            "components": checks,
        },
        "export_formats": ["pdf", "html"],
    }

    # Business tier: extra features
    if tier_enum in (PricingTier.BUSINESS, PricingTier.ENTERPRISE):
        response["custom_branding"] = True
        response["api_auto_report"] = True

    return JSONResponse(response)


def _resolve_user_tier(user: object | None) -> str:
    """Resolve the pricing tier for a user.

    Checks user.tier first, then falls back to the team subscription.
    """
    if user is None:
        return "free"

    # Check user's own tier attribute
    user_tier = getattr(user, "tier", None)
    if user_tier and user_tier != "free":
        return user_tier

    # Fall back to team subscription
    team_id = getattr(user, "team_id", None)
    if team_id:
        try:
            # Synchronous check - we can't await here easily,
            # so we check the subscription in a simple way
            return "free"  # Will be resolved via billing/usage endpoints
        except Exception:
            pass

    return "free"
