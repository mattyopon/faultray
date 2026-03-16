"""Feature flags for graceful degradation."""
from __future__ import annotations

FEATURES: dict[str, bool] = {
    "cascade_engine": True,
    "dynamic_engine": True,
    "ops_engine": True,
    "whatif_engine": True,
    "capacity_engine": True,
    "cost_engine": True,
    "security_engine": True,
    "compliance_engine": True,
    "dr_engine": True,
    "predictive_engine": True,
    "gameday_engine": True,
    "markov_model": True,
    "bayesian_model": True,
    "advisor_engine": True,
    "feed_threat_data": True,
    "prometheus_integration": True,
    "plugin_system": True,
}


def is_enabled(feature: str) -> bool:
    """Check if a feature flag is enabled. Defaults to True for unknown features."""
    return FEATURES.get(feature, True)


def disable(feature: str) -> None:
    """Disable a feature flag."""
    FEATURES[feature] = False


def enable(feature: str) -> None:
    """Enable a feature flag."""
    FEATURES[feature] = True


def reset_all() -> None:
    """Reset all feature flags to True (useful for testing)."""
    for key in FEATURES:
        FEATURES[key] = True


def list_features() -> dict[str, bool]:
    """Return a copy of all feature flags."""
    return dict(FEATURES)
