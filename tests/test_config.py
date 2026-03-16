"""Tests for FaultRay configuration management."""

import tempfile
from pathlib import Path

import pytest
import yaml

from faultray.config import (
    FaultRayConfig,
    load_config,
    save_config,
    set_nested_value,
    get_config,
    reset_config,
)


@pytest.fixture(autouse=True)
def _reset_global_config():
    """Reset the global config singleton before each test."""
    reset_config()
    yield
    reset_config()


def test_default_config_values():
    """FaultRayConfig should have sensible defaults."""
    config = FaultRayConfig()
    assert config.simulation["max_scenarios"] == 2000
    assert config.simulation["checkpoint_interval"] == 100
    assert config.cost_model["default_engineers"] == 2
    assert config.cost_model["engineer_hourly_rate"] == 100
    assert config.daemon["default_interval_seconds"] == 3600
    assert config.ui["default_port"] == 8080
    assert config.ui["default_host"] == "0.0.0.0"
    assert config.notifications["slack_webhook"] == ""


def test_load_config_returns_defaults_when_file_missing():
    """load_config should return defaults when the config file doesn't exist."""
    config = load_config(Path("/tmp/nonexistent-faultray-config.yaml"))
    assert config.simulation["max_scenarios"] == 2000
    assert config.ui["language"] == "en"


def test_save_and_load_config():
    """Config should round-trip through save and load."""
    with tempfile.TemporaryDirectory() as tmp:
        config_path = Path(tmp) / "config.yaml"
        config = FaultRayConfig()
        config.simulation["max_scenarios"] = 5000
        config.ui["language"] = "ja"

        save_config(config, config_path)
        assert config_path.exists()

        loaded = load_config(config_path)
        assert loaded.simulation["max_scenarios"] == 5000
        assert loaded.ui["language"] == "ja"
        # Defaults should be preserved
        assert loaded.simulation["checkpoint_interval"] == 100


def test_save_config_creates_parent_dirs():
    """save_config should create parent directories if they don't exist."""
    with tempfile.TemporaryDirectory() as tmp:
        config_path = Path(tmp) / "subdir" / "deep" / "config.yaml"
        config = FaultRayConfig()
        save_config(config, config_path)
        assert config_path.exists()


def test_load_config_partial_yaml():
    """load_config should merge partial YAML with defaults."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump({"simulation": {"max_scenarios": 999}}, f)
        f.flush()
        config = load_config(Path(f.name))

    assert config.simulation["max_scenarios"] == 999
    # checkpoint_interval should still have the default
    assert config.simulation["checkpoint_interval"] == 100
    # Other sections should have all defaults
    assert config.ui["default_port"] == 8080


def test_set_nested_value_int():
    """set_nested_value should parse integers correctly."""
    config = FaultRayConfig()
    set_nested_value(config, "simulation.max_scenarios", "5000")
    assert config.simulation["max_scenarios"] == 5000
    assert isinstance(config.simulation["max_scenarios"], int)


def test_set_nested_value_float():
    """set_nested_value should parse floats correctly."""
    config = FaultRayConfig()
    set_nested_value(config, "cost_model.engineer_hourly_rate", "150.5")
    assert config.cost_model["engineer_hourly_rate"] == 150.5
    assert isinstance(config.cost_model["engineer_hourly_rate"], float)


def test_set_nested_value_string():
    """set_nested_value should keep string values as strings."""
    config = FaultRayConfig()
    set_nested_value(config, "notifications.slack_webhook", "https://hooks.example.com/xyz")
    assert config.notifications["slack_webhook"] == "https://hooks.example.com/xyz"


def test_set_nested_value_invalid_section():
    """set_nested_value should raise ValueError for unknown section."""
    config = FaultRayConfig()
    with pytest.raises(ValueError, match="Unknown config section"):
        set_nested_value(config, "nonexistent.key", "value")


def test_set_nested_value_invalid_key_path():
    """set_nested_value should raise ValueError for invalid key path format."""
    config = FaultRayConfig()
    with pytest.raises(ValueError, match="Invalid key path"):
        set_nested_value(config, "noperiod", "value")


def test_get_config_singleton():
    """get_config should return the same instance on repeated calls."""
    c1 = get_config()
    c2 = get_config()
    assert c1 is c2


def test_load_config_empty_file():
    """load_config should handle an empty YAML file gracefully."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("")
        f.flush()
        config = load_config(Path(f.name))

    assert config.simulation["max_scenarios"] == 2000


def test_set_nested_value_new_key():
    """set_nested_value should allow setting keys that don't exist in defaults."""
    config = FaultRayConfig()
    set_nested_value(config, "simulation.custom_key", "hello")
    assert config.simulation["custom_key"] == "hello"
