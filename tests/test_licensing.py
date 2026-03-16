"""Tests for the licensing / feature gating stub."""

from __future__ import annotations

import pytest

from faultray.licensing import (
    FEATURE_GATES,
    FeatureTier,
    check_feature,
    get_required_tier,
    get_tier_features,
)


# ---------------------------------------------------------------------------
# Tests: check_feature
# ---------------------------------------------------------------------------


class TestCheckFeature:
    def test_free_features_available_in_free_tier(self):
        for feature in ("simulate", "dynamic", "demo", "evaluate"):
            assert check_feature(feature, FeatureTier.FREE) is True

    def test_pro_features_blocked_in_free_tier(self):
        for feature in ("scan_aws", "fix", "plan", "security", "cost", "monte_carlo"):
            assert check_feature(feature, FeatureTier.FREE) is False

    def test_pro_features_available_in_pro_tier(self):
        for feature in ("scan_aws", "fix", "plan", "security", "cost", "monte_carlo"):
            assert check_feature(feature, FeatureTier.PRO) is True

    def test_enterprise_features_blocked_in_pro_tier(self):
        for feature in ("compliance", "insurance_api", "executive_report", "dr"):
            assert check_feature(feature, FeatureTier.PRO) is False

    def test_enterprise_features_available_in_enterprise_tier(self):
        for feature in ("compliance", "insurance_api", "executive_report", "dr"):
            assert check_feature(feature, FeatureTier.ENTERPRISE) is True

    def test_enterprise_includes_all_lower_tiers(self):
        for feature in FEATURE_GATES:
            assert check_feature(feature, FeatureTier.ENTERPRISE) is True

    def test_unknown_feature_defaults_to_free(self):
        # Unknown features should be accessible in FREE tier
        assert check_feature("unknown_feature", FeatureTier.FREE) is True
        assert check_feature("another_missing", FeatureTier.PRO) is True

    def test_pro_includes_free_features(self):
        for feature in ("simulate", "dynamic", "demo", "evaluate"):
            assert check_feature(feature, FeatureTier.PRO) is True


# ---------------------------------------------------------------------------
# Tests: get_tier_features
# ---------------------------------------------------------------------------


class TestGetTierFeatures:
    def test_free_tier_features(self):
        features = get_tier_features(FeatureTier.FREE)
        assert "simulate" in features
        assert "dynamic" in features
        assert "scan_aws" not in features
        assert "compliance" not in features

    def test_pro_tier_includes_free(self):
        free_features = set(get_tier_features(FeatureTier.FREE))
        pro_features = set(get_tier_features(FeatureTier.PRO))
        assert free_features.issubset(pro_features)

    def test_enterprise_includes_all(self):
        enterprise_features = get_tier_features(FeatureTier.ENTERPRISE)
        assert len(enterprise_features) == len(FEATURE_GATES)

    def test_features_are_sorted(self):
        for tier in FeatureTier:
            features = get_tier_features(tier)
            assert features == sorted(features)


# ---------------------------------------------------------------------------
# Tests: get_required_tier
# ---------------------------------------------------------------------------


class TestGetRequiredTier:
    def test_free_feature_returns_free(self):
        assert get_required_tier("simulate") == FeatureTier.FREE

    def test_pro_feature_returns_pro(self):
        assert get_required_tier("scan_aws") == FeatureTier.PRO

    def test_enterprise_feature_returns_enterprise(self):
        assert get_required_tier("compliance") == FeatureTier.ENTERPRISE

    def test_unknown_feature_returns_free(self):
        assert get_required_tier("not_a_real_feature") == FeatureTier.FREE


# ---------------------------------------------------------------------------
# Tests: FeatureTier enum
# ---------------------------------------------------------------------------


class TestFeatureTier:
    def test_enum_values(self):
        assert FeatureTier.FREE.value == "free"
        assert FeatureTier.PRO.value == "pro"
        assert FeatureTier.ENTERPRISE.value == "enterprise"

    def test_enum_is_string(self):
        assert isinstance(FeatureTier.FREE, str)
        assert FeatureTier.PRO == "pro"

    def test_all_gates_have_valid_tiers(self):
        valid_tiers = set(FeatureTier)
        for feature, tier in FEATURE_GATES.items():
            assert tier in valid_tiers, f"Feature '{feature}' has invalid tier: {tier}"
