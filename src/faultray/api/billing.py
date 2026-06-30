# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

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


def _saas_quota_enabled() -> bool:
    """Whether hosted-SaaS usage quotas are actively ENFORCED on API requests.

    Defaults to OFF. The Apache-2.0 CLI and any self-hosted deployment must
    never be gated -- monetization applies only to the managed SaaS. The hosted
    service opts in by setting ``FAULTRAY_ENFORCE_QUOTA=1`` once per-team
    subscription tiers are synced into ``SubscriptionRow`` (otherwise every team
    resolves to the FREE tier and would be throttled). Usage *accounting*
    (``track_simulation``) is gated by the same flag so self-host runs never
    write per-team usage rows.
    """
    return os.environ.get("FAULTRAY_ENFORCE_QUOTA", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


class PricingTier(str, Enum):
    FREE = "free"
    PRO = "pro"
    BUSINESS = "business"
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
        max_simulations_per_month=5,
        compliance_reports=False,
        insurance_api=False,
        custom_sso=False,
        support_sla="community",
    ),
    PricingTier.PRO: UsageLimits(
        max_components=50,
        max_simulations_per_month=100,
        compliance_reports=True,
        insurance_api=False,
        custom_sso=False,
        support_sla="email_24h",
    ),
    PricingTier.BUSINESS: UsageLimits(
        max_components=-1,  # unlimited
        max_simulations_per_month=-1,  # unlimited
        compliance_reports=True,
        insurance_api=True,
        custom_sso=True,
        support_sla="dedicated_1h",
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


# Ordering used to pick the BEST tier available to a caller (their own
# UserRow.tier vs any paid team subscription).
_TIER_RANK: dict[PricingTier, int] = {
    PricingTier.FREE: 0,
    PricingTier.PRO: 1,
    PricingTier.BUSINESS: 2,
    PricingTier.ENTERPRISE: 3,
}


async def resolve_billing_context(
    user, session_factory=None,
) -> tuple[PricingTier, str]:
    """Resolve ``(effective_tier, usage_key)`` for *user*.

    *effective_tier* is the best of the user's own ``UserRow.tier`` and the tier
    of any billing team (``team_workspaces``) they own or belong to -- paid plans
    live in ``SubscriptionRow`` keyed by the billing-workspace id and
    ``UserRow.tier`` is never synced from it, so a Pro/Business team member would
    otherwise be treated as FREE.

    *usage_key* is the billing workspace id of the paying team ONLY when a single
    team's subscription unambiguously raises the caller above their personal tier
    (so the team's monthly quota is SHARED across members); otherwise it is
    ``"user:<id>"`` (free / solo, a personal tier >= the team tier, or several
    equal-tier teams), which also sidesteps the team-id vs billing-workspace-id
    namespace mismatch and never charges an ambiguous team.

    Resolution failures (e.g. team tables absent on a self-host) fall back to the
    user's own tier and a per-user key.
    """
    own = getattr(user, "tier", None)
    try:
        best = PricingTier(own) if own else PricingTier.FREE
    except ValueError:
        best = PricingTier.FREE

    uid = str(getattr(user, "id", "") or "")
    usage_key = f"user:{uid or 'anon'}"
    if not uid:
        return best, usage_key
    try:
        from faultray.api.database import SubscriptionRow, get_session_factory
        from sqlalchemy import select, text

        sf = session_factory or get_session_factory()
        async with sf() as session:
            # Workspaces the user owns OR is a member of.
            rows = (
                await session.execute(
                    text(
                        "SELECT id FROM team_workspaces WHERE owner_id = :uid "
                        "UNION "
                        "SELECT team_id FROM team_members WHERE user_id = :uid"
                    ),
                    {"uid": uid},
                )
            ).fetchall()
            workspace_ids = [r[0] for r in rows]
            if workspace_ids:
                subs = (
                    await session.execute(
                        select(
                            SubscriptionRow.team_id, SubscriptionRow.tier
                        ).where(SubscriptionRow.team_id.in_(workspace_ids))
                    )
                ).all()
                own_tier = best  # the caller's personal tier, before team raise
                # Highest team-subscription tier, and the workspaces holding it.
                team_tier = PricingTier.FREE
                top_workspaces: list[str] = []
                for ws_id, t in subs:
                    try:
                        cand = PricingTier(t)
                    except ValueError:
                        continue
                    if _TIER_RANK[cand] > _TIER_RANK[team_tier]:
                        team_tier = cand
                        top_workspaces = [ws_id]
                    elif cand == team_tier:
                        top_workspaces.append(ws_id)
                if _TIER_RANK[team_tier] > _TIER_RANK[best]:
                    best = team_tier
                # Charge usage to the paying team ONLY when it is unambiguous:
                # the team tier STRICTLY exceeds the caller's personal tier (so
                # the team is what grants the paid tier) AND exactly one workspace
                # holds that top tier. Otherwise -- a personal tier >= the team
                # tier, or several equal-tier teams -- fall back to per-user
                # accounting so we never charge (or 402) the wrong team.
                if (
                    _TIER_RANK[team_tier] > _TIER_RANK[own_tier]
                    and len(top_workspaces) == 1
                ):
                    usage_key = top_workspaces[0]
    except Exception:
        logger.debug("Could not resolve billing context.", exc_info=True)
    return best, usage_key


async def resolve_effective_tier(user, session_factory=None) -> PricingTier:
    """Best pricing tier available to *user* (see :func:`resolve_billing_context`)."""
    tier, _ = await resolve_billing_context(user, session_factory)
    return tier


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

    async def check_limit(
        self, team_id: str, resource: str, current_count: int | None = None,
    ) -> bool:
        """Check if team is within usage limits.

        Returns True if usage is allowed, False if limit reached.

        For ``resource == "components"`` the live component count is not stored
        per-team in the database (components live in the in-memory infra graph),
        so the caller passes it via *current_count*; an unlimited tier always
        allows, otherwise creation is allowed only while strictly under the
        configured maximum.
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
                    if limits.max_components == -1:
                        return True
                    # Compare the caller-supplied live count against the limit.
                    # If no count was provided we cannot prove the team is under
                    # limit, so fail closed (deny) rather than silently allow.
                    if current_count is None:
                        return False
                    return current_count < limits.max_components

                return True
        except Exception:
            # Fail CLOSED: if we cannot determine usage (DB error, unknown
            # tier, etc.) deny rather than silently grant unlimited paid usage.
            logger.warning("Could not check usage limit; denying.", exc_info=True)
            return False

    async def simulations_this_month(self, usage_key: str) -> int:
        """Count simulations recorded for *usage_key* in the current calendar
        month.

        On any error this returns 0 (fail OPEN) so a transient DB issue never
        throttles a possibly-paying user -- for a monetization gate a wrong
        ALLOW is far cheaper than wrongly blocking a paid customer.
        """
        try:
            from faultray.api.database import UsageLogRow, get_session_factory
            from sqlalchemy import select, func
            import datetime

            sf = self._session_factory or get_session_factory()
            async with sf() as session:
                now = datetime.datetime.now(datetime.timezone.utc)
                month_start = now.replace(
                    day=1, hour=0, minute=0, second=0, microsecond=0,
                )
                stmt = (
                    select(func.count())
                    .select_from(UsageLogRow)
                    .where(
                        UsageLogRow.team_id == usage_key,
                        UsageLogRow.resource == "simulation",
                        UsageLogRow.created_at >= month_start,
                    )
                )
                return int((await session.execute(stmt)).scalar() or 0)
        except Exception:
            logger.debug("Could not count monthly simulations.", exc_info=True)
            return 0

    async def simulation_quota_exceeded(
        self, usage_key: str, tier: PricingTier,
    ) -> bool:
        """Return True if *usage_key* has reached the monthly simulation cap for
        *tier*.

        Unlimited tiers (limit ``-1``) are never exceeded, so a paid plan
        genuinely unlocks more capacity. Counting failures fail OPEN.
        """
        limit = TIER_LIMITS[tier].max_simulations_per_month
        if limit == -1:
            return False
        return (await self.simulations_this_month(usage_key)) >= limit

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
    PricingTier.BUSINESS: os.environ.get("STRIPE_PRICE_BUSINESS", ""),
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
            # Propagate the team id onto the created Subscription too, so later
            # customer.subscription.updated/deleted webhooks (which read team_id
            # from the *subscription* metadata, not the session) can identify
            # the team and apply the downgrade on cancellation.
            subscription_data={"metadata": {"team_id": team_id, "tier": tier.value}},
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
            # Fail closed: derive the tier from the trusted price→tier mapping
            # first, and only fall back to validated checkout metadata. An
            # absent/unknown value yields the lowest tier (free) so a malformed
            # or attacker-influenced event can never silently grant a paid tier.
            result["tier"] = self._resolve_tier_from_event(session_obj)

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

    @staticmethod
    def _resolve_tier_from_event(session_obj: dict) -> str:
        """Derive a validated pricing tier from a checkout session event.

        Resolution order (fails closed at every step):
        1. The Stripe price id, mapped back through ``STRIPE_PRICE_MAP`` (the
           server-controlled, trusted source of truth) when present on the
           event's line items.
        2. The checkout ``metadata.tier`` value, but only if it parses to a
           known :class:`PricingTier`.
        Anything else -> ``free`` (never a paid tier from untrusted/absent data).
        """
        # 1. Prefer the trusted price→tier mapping if a price id is available.
        price_id = ""
        try:
            line_items = (session_obj.get("line_items") or {}).get("data") or []
            if line_items:
                price = line_items[0].get("price") or {}
                price_id = price.get("id", "") if isinstance(price, dict) else ""
        except Exception:  # pragma: no cover - defensive
            price_id = ""
        if price_id:
            for tier, mapped in STRIPE_PRICE_MAP.items():
                if mapped and mapped == price_id:
                    return tier.value

        # 2. Fall back to checkout metadata, validated against PricingTier.
        meta_tier = (session_obj.get("metadata") or {}).get("tier", "")
        try:
            return PricingTier(meta_tier).value
        except ValueError:
            return PricingTier.FREE.value

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
        """Persist subscription state changes from a processed webhook event.

        Idempotent *and* atomic: the idempotency-ledger insert and the
        subscription state mutation happen inside a single transaction that is
        committed exactly once at the end. The event is therefore marked
        "processed" only when its state change has also been applied -- if the
        mutation (or the process) fails, nothing is committed, so Stripe's retry
        is reprocessed normally rather than short-circuited as a duplicate.
        Concurrent duplicates are deduped by the ledger's unique constraint
        (IntegrityError -> skip).
        """
        event_type = event_data.get("event_type", "")
        event_id = event_data.get("event_id", "")

        from faultray.api.database import (
            ProcessedWebhookEventRow,
            get_session_factory,
        )
        from sqlalchemy import select
        from sqlalchemy.exc import IntegrityError

        sf = get_session_factory()
        try:
            async with sf() as session:
                # Replay / idempotency guard keyed by Stripe event id, applied
                # in the SAME transaction as the state change below.
                if event_id:
                    already = (
                        await session.execute(
                            select(ProcessedWebhookEventRow.id).where(
                                ProcessedWebhookEventRow.event_id == event_id
                            )
                        )
                    ).scalar_one_or_none()
                    if already is not None:
                        logger.info(
                            "Skipping already-processed webhook event %s", event_id
                        )
                        return
                    session.add(
                        ProcessedWebhookEventRow(
                            event_id=event_id, event_type=event_type
                        )
                    )
                    # Flush so a concurrent duplicate trips the unique
                    # constraint here (before we apply the state change), rather
                    # than at final commit.
                    await session.flush()

                # ---- apply the state change within the same transaction ----
                if event_type == "checkout.session.completed":
                    await self._activate_subscription(
                        session,
                        team_id=event_data.get("team_id", ""),
                        tier=event_data.get("tier", PricingTier.FREE.value),
                        customer_id=event_data.get("customer_id", ""),
                    )
                elif event_type == "customer.subscription.deleted":
                    team_id = event_data.get("team_id", "")
                    if team_id:
                        await self._downgrade_to_free(session, team_id)
                elif event_type == "invoice.payment_failed":
                    customer_id = event_data.get("customer_id", "")
                    if customer_id:
                        logger.warning(
                            "Payment failed for customer %s — subscription may be at risk",
                            customer_id,
                        )

                # Single commit: idempotency record + state change are atomic.
                await session.commit()
        except IntegrityError:
            # A concurrent delivery already recorded this event id; the unique
            # constraint rolled us back. The other transaction owns the state
            # change, so skipping here is correct (no double-apply).
            logger.info(
                "Webhook event %s already being processed concurrently; skipping.",
                event_id,
            )

    async def _activate_subscription(
        self, session, team_id: str, tier: str, customer_id: str,
    ) -> None:
        """Create or update a subscription row after successful checkout.

        Operates on the caller-provided *session* (does NOT commit) so the
        change is atomic with the webhook idempotency record.
        """
        if not team_id:
            return
        from faultray.api.database import SubscriptionRow
        from sqlalchemy import select

        result = await session.execute(
            select(SubscriptionRow).where(SubscriptionRow.team_id == team_id)
        )
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

        logger.info("Activated %s subscription for team %s", tier, team_id)

    async def _downgrade_to_free(self, session, team_id: str) -> None:
        """Downgrade a team to the free tier.

        Operates on the caller-provided *session* (does NOT commit) so the
        change is atomic with the webhook idempotency record.
        """
        from faultray.api.database import SubscriptionRow
        from sqlalchemy import select

        result = await session.execute(
            select(SubscriptionRow).where(SubscriptionRow.team_id == team_id)
        )
        sub = result.scalar_one_or_none()
        if sub is not None:
            sub.tier = PricingTier.FREE.value
            logger.info("Downgraded team %s to free tier", team_id)
