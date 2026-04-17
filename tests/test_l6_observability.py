# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""L6 Observability Tests — Value (Acceptance) layer.

Validates that FaultRay provides adequate information for debugging:
- Error messages contain useful context
- Stack traces are captured properly
- Logging output is structured and informative
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
import yaml

from faultray.errors import (
    ComponentNotFoundError,
    ConfigurationError,
    FaultRayError,
    SimulationError,
    ValidationError,
)
from faultray.model.loader import load_yaml


# ---------------------------------------------------------------------------
# L6-OBS-001: Error messages contain useful information
# ---------------------------------------------------------------------------


class TestErrorMessageQuality:
    """Verify that errors convey actionable information."""

    def test_missing_yaml_file_shows_path(self) -> None:
        """FileNotFoundError for YAML should include the attempted path."""
        with pytest.raises(FileNotFoundError, match="nonexistent"):
            load_yaml("/tmp/nonexistent_faultray_test.yaml")

    def test_invalid_yaml_top_level_shows_type(self, tmp_path: Path) -> None:
        """ValidationError for non-dict YAML should show the actual type."""
        yaml_file = tmp_path / "bad.yaml"
        yaml_file.write_text("- just a list item\n- another item\n")
        with pytest.raises(ValidationError, match="list"):
            load_yaml(yaml_file)

    def test_unknown_component_type_lists_valid_types(
        self, tmp_path: Path,
    ) -> None:
        """Unknown component type error should list valid types."""
        yaml_content = {
            "components": [
                {"id": "c1", "name": "C1", "type": "nonexistent_type"},
            ],
            "dependencies": [],
        }
        yaml_file = tmp_path / "bad_type.yaml"
        yaml_file.write_text(yaml.dump(yaml_content))
        with pytest.raises(ValidationError, match="Valid types"):
            load_yaml(yaml_file)

    def test_missing_component_id_shows_index(self, tmp_path: Path) -> None:
        """Missing component ID error should reference the entry index."""
        yaml_content = {
            "components": [
                {"name": "No ID", "type": "app_server"},
            ],
            "dependencies": [],
        }
        yaml_file = tmp_path / "no_id.yaml"
        yaml_file.write_text(yaml.dump(yaml_content))
        with pytest.raises(ValidationError, match="0"):
            load_yaml(yaml_file)

    def test_dangling_dependency_shows_component_id(
        self, tmp_path: Path,
    ) -> None:
        """Dependency referencing nonexistent component shows the bad ID."""
        yaml_content = {
            "components": [
                {"id": "a", "name": "A", "type": "app_server"},
            ],
            "dependencies": [
                {"source": "a", "target": "nonexistent", "type": "requires"},
            ],
        }
        yaml_file = tmp_path / "dangling.yaml"
        yaml_file.write_text(yaml.dump(yaml_content))
        with pytest.raises(ValidationError, match="nonexistent"):
            load_yaml(yaml_file)

    def test_circular_dependency_shows_cycle(self, tmp_path: Path) -> None:
        """Circular dependency error should show the cycle path."""
        yaml_content = {
            "components": [
                {"id": "a", "name": "A", "type": "app_server"},
                {"id": "b", "name": "B", "type": "app_server"},
            ],
            "dependencies": [
                {"source": "a", "target": "b", "type": "requires"},
                {"source": "b", "target": "a", "type": "requires"},
            ],
        }
        yaml_file = tmp_path / "circular.yaml"
        yaml_file.write_text(yaml.dump(yaml_content))
        with pytest.raises(ValidationError, match="[Cc]ircular"):
            load_yaml(yaml_file)


# ---------------------------------------------------------------------------
# L6-OBS-002: Exception hierarchy is correct
# ---------------------------------------------------------------------------


class TestExceptionHierarchy:
    """Verify exception hierarchy for proper catch semantics."""

    def test_all_custom_exceptions_inherit_faultray_error(self) -> None:
        """All custom exceptions should be catchable via FaultRayError."""
        assert issubclass(ValidationError, FaultRayError)
        assert issubclass(ComponentNotFoundError, FaultRayError)
        assert issubclass(ConfigurationError, FaultRayError)
        assert issubclass(SimulationError, FaultRayError)

    def test_validation_error_is_value_error(self) -> None:
        """ValidationError should also be a ValueError for compatibility."""
        assert issubclass(ValidationError, ValueError)

    def test_component_not_found_is_key_error(self) -> None:
        """ComponentNotFoundError should also be a KeyError for compatibility."""
        assert issubclass(ComponentNotFoundError, KeyError)

    def test_catch_faultray_error_catches_all(self) -> None:
        """A broad `except FaultRayError` should catch all custom exceptions."""
        for exc_cls in [ValidationError, ComponentNotFoundError, ConfigurationError]:
            try:
                raise exc_cls("test")
            except FaultRayError:
                pass  # Expected
            except Exception:
                pytest.fail(f"{exc_cls.__name__} not caught by FaultRayError")


# ---------------------------------------------------------------------------
# L6-OBS-003: Logging is structured
# ---------------------------------------------------------------------------


class TestLoggingStructure:
    """Verify that logging is properly configured and structured."""

    def test_setup_logging_creates_handler(self) -> None:
        """setup_logging should add a handler to the faultray logger."""
        from faultray.log_config import setup_logging

        logger = logging.getLogger("faultray")
        # Clear existing handlers to test fresh
        logger.handlers.clear()
        setup_logging(level="DEBUG")
        assert len(logger.handlers) > 0

    def test_setup_logging_json_format(self) -> None:
        """setup_logging with json_format=True should use JSON formatter."""
        from faultray.log_config import setup_logging

        logger = logging.getLogger("faultray")
        logger.handlers.clear()
        setup_logging(level="DEBUG", json_format=True)
        handler = logger.handlers[0]
        fmt = handler.formatter
        assert fmt is not None
        # JSON format should contain 'timestamp' and 'level'
        assert "timestamp" in fmt._fmt
        assert "level" in fmt._fmt

    def test_get_logger_returns_child(self) -> None:
        """get_logger should return a logger under the faultray namespace."""
        from faultray.log_config import get_logger

        lg = get_logger("test_module")
        assert lg.name == "faultray.test_module"

    def test_setup_logging_idempotent(self) -> None:
        """Calling setup_logging twice should not add duplicate handlers."""
        from faultray.log_config import setup_logging

        logger = logging.getLogger("faultray")
        logger.handlers.clear()
        setup_logging(level="WARNING")
        count1 = len(logger.handlers)
        setup_logging(level="WARNING")
        count2 = len(logger.handlers)
        assert count1 == count2, "Duplicate handlers added"
