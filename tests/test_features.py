"""Tests for FaultRay feature flags."""

import pytest

from faultray.features import (
    FEATURES,
    disable,
    enable,
    is_enabled,
    list_features,
    reset_all,
)


@pytest.fixture(autouse=True)
def _reset_features():
    """Reset all feature flags before each test."""
    reset_all()
    yield
    reset_all()


def test_all_features_enabled_by_default():
    """All known feature flags should default to True."""
    for name, value in FEATURES.items():
        assert value is True, f"Feature '{name}' should default to True"


def test_is_enabled_known_feature():
    """is_enabled should return True for known enabled features."""
    assert is_enabled("cascade_engine") is True
    assert is_enabled("dynamic_engine") is True


def test_is_enabled_unknown_feature():
    """is_enabled should return True for unknown features (default)."""
    assert is_enabled("totally_unknown_feature") is True


def test_disable_feature():
    """disable() should set a feature to False."""
    assert is_enabled("cascade_engine") is True
    disable("cascade_engine")
    assert is_enabled("cascade_engine") is False


def test_enable_feature():
    """enable() should set a feature back to True."""
    disable("dynamic_engine")
    assert is_enabled("dynamic_engine") is False
    enable("dynamic_engine")
    assert is_enabled("dynamic_engine") is True


def test_reset_all():
    """reset_all() should restore all features to True."""
    disable("cascade_engine")
    disable("dynamic_engine")
    disable("ops_engine")
    assert is_enabled("cascade_engine") is False
    assert is_enabled("dynamic_engine") is False
    reset_all()
    assert is_enabled("cascade_engine") is True
    assert is_enabled("dynamic_engine") is True
    assert is_enabled("ops_engine") is True


def test_list_features_returns_copy():
    """list_features() should return a copy, not the global dict."""
    features = list_features()
    assert features == FEATURES
    # Modifying the copy should not affect the global
    features["cascade_engine"] = False
    assert FEATURES["cascade_engine"] is True


def test_disable_unknown_feature():
    """disable() should create a new entry for unknown features."""
    disable("new_experimental_feature")
    assert is_enabled("new_experimental_feature") is False


def test_feature_flag_count():
    """There should be at least 17 feature flags defined."""
    assert len(FEATURES) >= 17
