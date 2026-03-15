"""Feature gating stub for FaultZero OSS vs commercial tiers.

This module defines a feature tier structure for future commercial
gating.  Currently **all features are enabled** regardless of tier --
this is just a stub that establishes the data model.
"""

from __future__ import annotations

from enum import Enum


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


def check_feature(
    feature: str,
    current_tier: FeatureTier = FeatureTier.FREE,
) -> bool:
    """Check if *feature* is available in *current_tier*.

    The tier hierarchy is ``FREE < PRO < ENTERPRISE``.  A higher tier
    always includes all features of a lower tier.

    Args:
        feature: feature key (must match a key in :data:`FEATURE_GATES`).
        current_tier: the user's active tier.

    Returns:
        ``True`` if the feature is available, ``False`` otherwise.
    """
    required = FEATURE_GATES.get(feature, FeatureTier.FREE)
    return _TIER_ORDER.index(current_tier) >= _TIER_ORDER.index(required)


def get_tier_features(tier: FeatureTier) -> list[str]:
    """Return a sorted list of features available in *tier*."""
    return sorted(f for f in FEATURE_GATES if check_feature(f, tier))


def get_required_tier(feature: str) -> FeatureTier:
    """Return the minimum tier required for *feature*."""
    return FEATURE_GATES.get(feature, FeatureTier.FREE)
