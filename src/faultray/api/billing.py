# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Billing foundation -- pricing tiers and usage tracking for FaultRay SaaS."""

from __future__ import annotations

import logging
import os
from enum import Enum
from dataclasses import dataclass

try:
    import stripe as _stripe
except ImportError:  # pragma: no cover
    _stripe = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


class PricingTier(str, Enum):
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


@dataclass
class UsageLimits:
    """Per-tier resource limits."""

    max_components: int
    max_simulations_per_month: int
    compliance_reports: bool
    insurance_api: bool
    custom_sso: bool
    support_sla: str


TIER_LIMITS: dict[PricingTier, UsageLimits] = {
    PricingTier.FREE: UsageLimits(
        max_components=5,
        max_simulations_per_month=10,
        compliance_reports=False,
        insurance_api=False,
        custom_sso=False,
        support_sla="community",
    ),
    PricingTier.PRO: UsageLimits(
        max_components=50,
        max_simulations_per_month=-1,  # unlimited
        compliance_reports=True,
        insurance_api=False,
        custom_sso=False,
        support_sla="email_24h",
    ),
    PricingTier.ENTERPRISE: UsageLimits(
        max_components=-1,  # unlimited
        max_simulations_per_month=-1,
        compliance_reports=True,
        insurance_api=True,
        custom_sso=True,
        support_sla="dedicated_1h",
    ),
}


class UsageTracker:
    """Track and enforce per-team resource usage against tier limits."""

    def __init__(self, db_session_factory) -> None:
        self._session_factory = db_session_factory

    async def track_simulation(self, team_id: str) -> None:
        """Record a simulation run for usage accounting."""
        try:
            from faultray.api.database import get_session_factory

            sf = self._session_factory or get_session_factory()
            async with sf() as session:
                from faultray.api.database import UsageLogRow

                log = UsageLogRow(team_id=team_id, resource="simulation", quantity=1)
                session.add(log)
                await session.commit()
        except Exception:
            logger.debug("Could not track simulation usage.", exc_info=True)

    async def check_limit(self, team_id: str, resource: str) -> bool:
        """Check if team is within usage limits.

        Returns True if usage is allowed, False if limit reached.
        """
        try:
            from faultray.api.database import (
                SubscriptionRow,
                UsageLogRow,
                get_session_factory,
            )
            from sqlalchemy import select, func
            import datetime

            sf = self._session_factory or get_session_factory()
            async with sf() as session:
                # Get team's subscription tier
                stmt = select(SubscriptionRow).where(
                    SubscriptionRow.team_id == team_id
                )
                result = await session.execute(stmt)
                sub = result.scalar_one_or_none()

                tier = PricingTier(sub.tier) if sub else PricingTier.FREE
                limits = TIER_LIMITS[tier]

                if resource == "simulation":
                    limit = limits.max_simulations_per_month
                    if limit == -1:
                        return True

                    # Count this month's usage
                    now = datetime.datetime.now(datetime.timezone.utc)
                    month_start = now.replace(
                        day=1, hour=0, minute=0, second=0, microsecond=0,
                    )
                    count_stmt = (
                        select(func.count())
                        .select_from(UsageLogRow)
                        .where(
                            UsageLogRow.team_id == team_id,
                            UsageLogRow.resource == "simulation",
                            UsageLogRow.created_at >= month_start,
                        )
                    )
                    count_result = await session.execute(count_stmt)
                    count = count_result.scalar() or 0
                    return count < limit

                if resource == "components":
                    return limits.max_components == -1  # defer actual check to caller

                return True
        except Exception:
            logger.debug("Could not check usage limit.", exc_info=True)
            return True  # fail open

    async def get_usage(self, team_id: str, period: str = "") -> dict:
        """Get current usage summary for a team."""
        try:
            from faultray.api.database import (
                SubscriptionRow,
                UsageLogRow,
                get_session_factory,
            )
            from sqlalchemy import select, func
            import datetime

            sf = self._session_factory or get_session_factory()
            async with sf() as session:
                stmt = select(SubscriptionRow).where(
                    SubscriptionRow.team_id == team_id
                )
                result = await session.execute(stmt)
                sub = result.scalar_one_or_none()

                tier = PricingTier(sub.tier) if sub else PricingTier.FREE
                limits = TIER_LIMITS[tier]

                now = datetime.datetime.now(datetime.timezone.utc)
                month_start = now.replace(
                    day=1, hour=0, minute=0, second=0, microsecond=0,
                )

                count_stmt = (
                    select(func.count())
                    .select_from(UsageLogRow)
                    .where(
                        UsageLogRow.team_id == team_id,
                        UsageLogRow.resource == "simulation",
                        UsageLogRow.created_at >= month_start,
                    )
                )
                count_result = await session.execute(count_stmt)
                sim_count = count_result.scalar() or 0

                return {
                    "team_id": team_id,
                    "tier": tier.value,
                    "simulations_this_month": sim_count,
                    "simulation_limit": limits.max_simulations_per_month,
                    "component_limit": limits.max_components,
                    "features": {
                        "compliance_reports": limits.compliance_reports,
                        "insurance_api": limits.insurance_api,
                        "custom_sso": limits.custom_sso,
                        "support_sla": limits.support_sla,
                    },
                }
        except Exception:
            logger.debug("Could not get usage.", exc_info=True)
            return {"team_id": team_id, "tier": "free", "error": "unavailable"}


# ---------------------------------------------------------------------------
# Stripe price ID mapping (env-var driven)
# ---------------------------------------------------------------------------

STRIPE_PRICE_MAP: dict[PricingTier, str] = {
    PricingTier.PRO: os.environ.get("STRIPE_PRICE_PRO", ""),
    PricingTier.ENTERPRISE: os.environ.get("STRIPE_PRICE_ENTERPRISE", ""),
}


def _stripe_available() -> bool:
    """Return True if the stripe package is installed and a secret key is configured."""
    return _stripe is not None and bool(os.environ.get("STRIPE_SECRET_KEY"))


class StripeManager:
    """Thin wrapper around Stripe APIs for FaultRay billing.

    All methods are safe to call even when the ``stripe`` package is not
    installed or the environment variables are unset -- they will raise
    :class:`RuntimeError` so the caller can fall back gracefully.
    """

    def __init__(self, secret_key: str | None = None) -> None:
        key = secret_key or os.environ.get("STRIPE_SECRET_KEY", "")
        if _stripe is None:
            logger.warning("stripe package not installed -- billing features disabled")
            self._enabled = False
            return
        if not key:
            logger.info("STRIPE_SECRET_KEY not set -- billing features disabled")
            self._enabled = False
            return
        _stripe.api_key = key
        self._enabled = True

    @property
    def enabled(self) -> bool:
        return self._enabled

    # -- Checkout ----------------------------------------------------------

    async def create_checkout_session(
        self,
        tier: PricingTier,
        team_id: str,
        success_url: str,
        cancel_url: str,
    ) -> str:
        """Create a Stripe Checkout Session and return the session URL."""
        if not self._enabled:
            raise RuntimeError("Stripe is not configured")

        price_id = STRIPE_PRICE_MAP.get(tier, "")
        if not price_id:
            raise ValueError(f"No Stripe price configured for tier {tier.value}")

        session = _stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=success_url,
            cancel_url=cancel_url,
            client_reference_id=team_id,
            metadata={"team_id": team_id, "tier": tier.value},
        )
        return session.url  # type: ignore[return-value]

    # -- Customer Portal ---------------------------------------------------

    async def create_customer_portal_session(
        self,
        customer_id: str,
        return_url: str,
    ) -> str:
        """Create a Stripe Customer Portal session and return the URL."""
        if not self._enabled:
            raise RuntimeError("Stripe is not configured")

        session = _stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=return_url,
        )
        return session.url  # type: ignore[return-value]

    # -- Webhooks ----------------------------------------------------------

    async def handle_webhook_event(
        self,
        payload: bytes,
        sig_header: str,
        webhook_secret: str | None = None,
    ) -> dict:
        """Verify and process a Stripe webhook event.

        Returns a dict with ``event_type`` and any relevant data extracted
        from the event.  The caller (route handler) is responsible for
        persisting subscription state changes.
        """
        if not self._enabled:
            raise RuntimeError("Stripe is not configured")

        secret = webhook_secret or os.environ.get("STRIPE_WEBHOOK_SECRET", "")
        if not secret:
            raise RuntimeError("STRIPE_WEBHOOK_SECRET is not configured")

        event = _stripe.Webhook.construct_event(payload, sig_header, secret)

        result: dict = {"event_type": event["type"], "event_id": event["id"]}

        # ---- subscription lifecycle events ----
        if event["type"] == "checkout.session.completed":
            session_obj = event["data"]["object"]
            result["team_id"] = session_obj.get("client_reference_id", "")
            result["customer_id"] = session_obj.get("customer", "")
            result["subscription_id"] = session_obj.get("subscription", "")
            result["tier"] = session_obj.get("metadata", {}).get("tier", "pro")

        elif event["type"] in (
            "customer.subscription.updated",
            "customer.subscription.deleted",
        ):
            sub_obj = event["data"]["object"]
            result["subscription_id"] = sub_obj.get("id", "")
            result["customer_id"] = sub_obj.get("customer", "")
            result["status"] = sub_obj.get("status", "")
            result["team_id"] = sub_obj.get("metadata", {}).get("team_id", "")

        elif event["type"] == "invoice.payment_failed":
            invoice_obj = event["data"]["object"]
            result["customer_id"] = invoice_obj.get("customer", "")
            result["subscription_id"] = invoice_obj.get("subscription", "")

        return result

    # -- Subscription queries ----------------------------------------------

    async def get_subscription(self, team_id: str) -> dict | None:
        """Look up the team's active subscription from the local database."""
        try:
            from faultray.api.database import SubscriptionRow, get_session_factory
            from sqlalchemy import select

            sf = get_session_factory()
            async with sf() as session:
                stmt = select(SubscriptionRow).where(
                    SubscriptionRow.team_id == team_id
                )
                result = await session.execute(stmt)
                sub = result.scalar_one_or_none()
                if sub is None:
                    return None
                return {
                    "team_id": sub.team_id,
                    "tier": sub.tier,
                    "stripe_customer_id": sub.stripe_customer_id,
                    "started_at": sub.started_at.isoformat() if sub.started_at else None,
                    "expires_at": sub.expires_at.isoformat() if sub.expires_at else None,
                }
        except Exception:
            logger.debug("Could not fetch subscription for team %s", team_id, exc_info=True)
            return None

    async def cancel_subscription(self, team_id: str) -> bool:
        """Cancel the team's Stripe subscription and downgrade to Free."""
        if not self._enabled:
            raise RuntimeError("Stripe is not configured")

        try:
            from faultray.api.database import SubscriptionRow, get_session_factory
            from sqlalchemy import select

            sf = get_session_factory()
            async with sf() as session:
                stmt = select(SubscriptionRow).where(
                    SubscriptionRow.team_id == team_id
                )
                result = await session.execute(stmt)
                sub = result.scalar_one_or_none()
                if sub is None:
                    return False

                # Cancel on Stripe if we have a customer
                if sub.stripe_customer_id:
                    subscriptions = _stripe.Subscription.list(
                        customer=sub.stripe_customer_id, status="active", limit=1,
                    )
                    for s in subscriptions.data:
                        _stripe.Subscription.cancel(s.id)

                # Downgrade locally
                sub.tier = PricingTier.FREE.value
                await session.commit()
                return True
        except Exception:
            logger.error("Failed to cancel subscription for team %s", team_id, exc_info=True)
            return False

    # -- Webhook → DB persistence helper -----------------------------------

    async def persist_webhook_event(self, event_data: dict) -> None:
        """Persist subscription state changes from a processed webhook event."""
        event_type = event_data.get("event_type", "")

        if event_type == "checkout.session.completed":
            await self._activate_subscription(
                team_id=event_data.get("team_id", ""),
                tier=event_data.get("tier", "pro"),
                customer_id=event_data.get("customer_id", ""),
            )

        elif event_type == "customer.subscription.deleted":
            team_id = event_data.get("team_id", "")
            if team_id:
                await self._downgrade_to_free(team_id)

        elif event_type == "invoice.payment_failed":
            customer_id = event_data.get("customer_id", "")
            if customer_id:
                logger.warning(
                    "Payment failed for customer %s — subscription may be at risk",
                    customer_id,
                )

    async def _activate_subscription(
        self, team_id: str, tier: str, customer_id: str,
    ) -> None:
        """Create or update a subscription row after successful checkout."""
        if not team_id:
            return
        try:
            from faultray.api.database import SubscriptionRow, get_session_factory
            from sqlalchemy import select

            sf = get_session_factory()
            async with sf() as session:
                stmt = select(SubscriptionRow).where(
                    SubscriptionRow.team_id == team_id
                )
                result = await session.execute(stmt)
                sub = result.scalar_one_or_none()

                if sub is None:
                    sub = SubscriptionRow(
                        team_id=team_id,
                        tier=tier,
                        stripe_customer_id=customer_id,
                    )
                    session.add(sub)
                else:
                    sub.tier = tier
                    sub.stripe_customer_id = customer_id

                await session.commit()
                logger.info("Activated %s subscription for team %s", tier, team_id)
        except Exception:
            logger.error(
                "Failed to activate subscription for team %s", team_id, exc_info=True,
            )

    async def _downgrade_to_free(self, team_id: str) -> None:
        """Downgrade a team to the free tier."""
        try:
            from faultray.api.database import SubscriptionRow, get_session_factory
            from sqlalchemy import select

            sf = get_session_factory()
            async with sf() as session:
                stmt = select(SubscriptionRow).where(
                    SubscriptionRow.team_id == team_id
                )
                result = await session.execute(stmt)
                sub = result.scalar_one_or_none()
                if sub is not None:
                    sub.tier = PricingTier.FREE.value
                    await session.commit()
                    logger.info("Downgraded team %s to free tier", team_id)
        except Exception:
            logger.error(
                "Failed to downgrade team %s", team_id, exc_info=True,
            )
