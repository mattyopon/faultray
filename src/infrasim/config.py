"""FaultZero configuration management."""
from __future__ import annotations

import logging
from pathlib import Path
from dataclasses import dataclass, field

import yaml

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path.home() / ".faultzero" / "config.yaml"


@dataclass
class FaultZeroConfig:
    simulation: dict = field(default_factory=lambda: {
        "max_scenarios": 2000,
        "checkpoint_interval": 100,
    })
    cost_model: dict = field(default_factory=lambda: {
        "default_engineers": 2,
        "engineer_hourly_rate": 100,
    })
    daemon: dict = field(default_factory=lambda: {
        "default_interval_seconds": 3600,
        "log_directory": str(Path.home() / ".faultzero" / "logs"),
    })
    notifications: dict = field(default_factory=lambda: {
        "slack_webhook": "",
        "pagerduty_key": "",
        "teams_webhook": "",
        "email_smtp_host": "",
    })
    ui: dict = field(default_factory=lambda: {
        "default_port": 8080,
        "default_host": "0.0.0.0",
        "language": "en",
    })


def load_config(path: Path | None = None) -> FaultZeroConfig:
    """Load config from YAML file. Returns defaults if file doesn't exist."""
    config_path = path or DEFAULT_CONFIG_PATH
    if config_path.exists():
        with open(config_path) as f:
            data = yaml.safe_load(f) or {}
        config = FaultZeroConfig()
        for key, value in data.items():
            if hasattr(config, key) and isinstance(value, dict):
                getattr(config, key).update(value)
        return config
    return FaultZeroConfig()


def save_config(config: FaultZeroConfig, path: Path | None = None) -> None:
    """Save config to YAML file."""
    config_path = path or DEFAULT_CONFIG_PATH
    config_path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "simulation": config.simulation,
        "cost_model": config.cost_model,
        "daemon": config.daemon,
        "notifications": config.notifications,
        "ui": config.ui,
    }
    with open(config_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def set_nested_value(config: FaultZeroConfig, key_path: str, value: str) -> None:
    """Set a nested config value using dot notation (e.g. 'simulation.max_scenarios').

    Attempts to parse the value as int, then float, then keeps as string.
    """
    parts = key_path.split(".", 1)
    if len(parts) != 2:
        raise ValueError(
            f"Invalid key path '{key_path}'. Use 'section.key' format "
            f"(e.g. 'simulation.max_scenarios')."
        )
    section, key = parts
    if not hasattr(config, section):
        raise ValueError(
            f"Unknown config section '{section}'. "
            f"Valid sections: simulation, cost_model, daemon, notifications, ui"
        )
    section_dict = getattr(config, section)
    if not isinstance(section_dict, dict):
        raise ValueError(f"Config section '{section}' is not a dict.")

    # Parse value type
    parsed_value: str | int | float = value
    try:
        parsed_value = int(value)
    except ValueError:
        try:
            parsed_value = float(value)
        except ValueError:
            pass  # keep as string

    section_dict[key] = parsed_value


# Global config instance
_config: FaultZeroConfig | None = None


def get_config() -> FaultZeroConfig:
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reset_config() -> None:
    """Reset the global config instance (useful for testing)."""
    global _config
    _config = None
