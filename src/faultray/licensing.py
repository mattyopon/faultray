# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""HMAC-based license key generation, verification, and feature gating for FaultRay.

License key format: ``FR-{TIER}-{TEAM_ID_HASH}-{SIGNATURE}``

Environment variables:
    ``FAULTRAY_LICENSE_KEY``    — set by the user to activate Pro/Enterprise.
    ``FAULTRAY_LICENSE_SECRET`` — server-side only, used to generate keys.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
from enum import Enum

from faultray.api.billing import PricingTier, TIER_LIMITS, UsageLimits

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Environment variable names
# ---------------------------------------------------------------------------
_ENV_LICENSE_KEY = "FAULTRAY_LICENSE_KEY"
_ENV_LICENSE_SECRET = "FAULTRAY_LICENSE_SECRET"  # noqa: S105 - env var name, not a secret value

# ---------------------------------------------------------------------------
# Key format constants
# ---------------------------------------------------------------------------
_KEY_PREFIX = "FR"
_VALID_TIERS: dict[str, PricingTier] = {
    t.value.upper(): t for t in PricingTier if t != PricingTier.FREE
}

# ---------------------------------------------------------------------------
# Feature gating (carried over from the original stub)
# ---------------------------------------------------------------------------


class FeatureTier(str, Enum):
    """Tier levels for feature gating."""

    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


# Mapping of CLI command / feature name -> minimum required tier.
FEATURE_GATES: dict[str, FeatureTier] = {
    # --- Free tier (open-source core) ---
    "simulate": FeatureTier.FREE,
    "dynamic": FeatureTier.FREE,
    "demo": FeatureTier.FREE,
    "evaluate": FeatureTier.FREE,
    # --- Pro tier ---
    "scan_aws": FeatureTier.PRO,
    "fix": FeatureTier.PRO,
    "plan": FeatureTier.PRO,
    "security": FeatureTier.PRO,
    "cost": FeatureTier.PRO,
    "monte_carlo": FeatureTier.PRO,
    # --- Enterprise tier ---
    "compliance": FeatureTier.ENTERPRISE,
    "insurance_api": FeatureTier.ENTERPRISE,
    "executive_report": FeatureTier.ENTERPRISE,
    "dr": FeatureTier.ENTERPRISE,
}

_TIER_ORDER: list[FeatureTier] = [
    FeatureTier.FREE,
    FeatureTier.PRO,
    FeatureTier.ENTERPRISE,
]

# Map between PricingTier and FeatureTier.
# PricingTier.BUSINESS maps to FeatureTier.ENTERPRISE (same feature set).
_PRICING_TO_FEATURE: dict[PricingTier, FeatureTier] = {
    PricingTier.FREE: FeatureTier.FREE,
    PricingTier.PRO: FeatureTier.PRO,
    PricingTier.BUSINESS: FeatureTier.ENTERPRISE,
    PricingTier.ENTERPRISE: FeatureTier.ENTERPRISE,
}

# ---------------------------------------------------------------------------
# License key generation (admin / server-side)
# ---------------------------------------------------------------------------


def generate_license_key(
    tier: PricingTier,
    team_id: str,
    secret: str | None = None,
) -> str:
    """Generate a signed license key for the given tier and team.

    Parameters
    ----------
    tier:
        The pricing tier to encode (PRO or ENTERPRISE).
    team_id:
        An opaque team identifier (e.g. UUID or slug).
    secret:
        The HMAC signing secret.  Falls back to ``FAULTRAY_LICENSE_SECRET``.

    Returns
    -------
    str
        A license key in the format ``FR-{TIER}-{TEAM_ID_HASH}-{SIGNATURE}``.

    Raises
    ------
    ValueError
        If the tier is FREE or the secret is missing.
    """
    if tier == PricingTier.FREE:
        raise ValueError("Cannot generate a license key for the FREE tier")

    secret = secret or os.environ.get(_ENV_LICENSE_SECRET, "")
    if not secret:
        raise ValueError(
            f"Signing secret is required. Set {_ENV_LICENSE_SECRET} or pass explicitly."
        )

    tier_tag = tier.value.upper()
    team_hash = hashlib.sha256(team_id.encode()).hexdigest()[:8]

    message = f"{_KEY_PREFIX}-{tier_tag}-{team_hash}"
    signature = hmac.new(
        secret.encode(), message.encode(), hashlib.sha256,
    ).hexdigest()[:8]

    return f"{message}-{signature}"


# ---------------------------------------------------------------------------
# License key verification
# ---------------------------------------------------------------------------


def verify_license_key(key: str, secret: str | None = None) -> PricingTier | None:
    """Verify a license key and return the encoded tier if valid.

    Returns ``None`` when the key is malformed, the secret is missing, or
    the signature does not match.
    """
    secret = secret or os.environ.get(_ENV_LICENSE_SECRET, "")
    if not secret:
        logger.debug("No license secret configured; cannot verify key")
        return None

    parts = key.split("-")
    if len(parts) != 4:
        logger.debug("License key has wrong number of segments: %d", len(parts))
        return None

    prefix, tier_tag, team_hash, provided_sig = parts

    if prefix != _KEY_PREFIX:
        logger.debug("License key prefix mismatch: %s", prefix)
        return None

    if tier_tag not in _VALID_TIERS:
        logger.debug("License key tier unknown: %s", tier_tag)
        return None

    # Recompute expected signature
    message = f"{prefix}-{tier_tag}-{team_hash}"
    expected_sig = hmac.new(
        secret.encode(), message.encode(), hashlib.sha256,
    ).hexdigest()[:8]

    if not hmac.compare_digest(provided_sig, expected_sig):
        logger.debug("License key signature mismatch")
        return None

    return _VALID_TIERS[tier_tag]


# ---------------------------------------------------------------------------
# Active tier resolution
# ---------------------------------------------------------------------------


def get_active_tier() -> PricingTier:
    """Return the active pricing tier.

    Resolution order:

    1. ``FAULTRAY_LICENSE_KEY`` environment variable (HMAC-signed key).
    2. Active redeemed coupon in ``~/.faultray/license.json``.
    3. :attr:`PricingTier.FREE` (default).
    """
    key = os.environ.get(_ENV_LICENSE_KEY, "")
    if key:
        tier = verify_license_key(key)
        if tier is None:
            logger.warning(
                "Invalid license key in %s; falling back to coupon / FREE tier",
                _ENV_LICENSE_KEY,
            )
        else:
            return tier

    # Fall through to coupon-based tier
    try:
        from faultray.coupon import get_active_coupon_tier

        coupon_tier_str = get_active_coupon_tier()
        if coupon_tier_str is not None:
            try:
                return PricingTier(coupon_tier_str)
            except ValueError:
                logger.warning(
                    "Unknown tier value in license.json: %r; ignoring coupon",
                    coupon_tier_str,
                )
    except Exception:
        logger.debug("Could not read coupon tier", exc_info=True)

    return PricingTier.FREE


def get_active_limits() -> UsageLimits:
    """Return the usage limits for the currently active tier."""
    return TIER_LIMITS[get_active_tier()]


# ---------------------------------------------------------------------------
# Feature checks
# ---------------------------------------------------------------------------


def check_feature(
    feature: str,
    current_tier: FeatureTier | None = None,
) -> bool:
    """Check if *feature* is available in *current_tier*.

    When *current_tier* is ``None`` the tier is resolved automatically from
    the ``FAULTRAY_LICENSE_KEY`` environment variable via :func:`get_active_tier`.

    The tier hierarchy is ``FREE < PRO < ENTERPRISE``.  A higher tier
    always includes all features of a lower tier.
    """
    if current_tier is None:
        current_tier = _PRICING_TO_FEATURE[get_active_tier()]

    required = FEATURE_GATES.get(feature, FeatureTier.FREE)
    return _TIER_ORDER.index(current_tier) >= _TIER_ORDER.index(required)


def get_tier_features(tier: FeatureTier) -> list[str]:
    """Return a sorted list of features available in *tier*."""
    return sorted(f for f in FEATURE_GATES if check_feature(f, tier))


def get_required_tier(feature: str) -> FeatureTier:
    """Return the minimum tier required for *feature*."""
    return FEATURE_GATES.get(feature, FeatureTier.FREE)
