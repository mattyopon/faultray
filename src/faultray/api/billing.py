"""Billing foundation -- pricing tiers and usage tracking for FaultRay SaaS."""

from __future__ import annotations

import logging
from enum import Enum
from dataclasses import dataclass

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
