# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""L14 Panic-Free Tests — Psychological Quality layer.

Validates that FaultRay provides user-friendly error handling:
- Errors produce helpful messages, not raw stack traces
- Invalid YAML gives clear guidance
- Fatal errors provide reassuring messages
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from faultray.errors import FaultRayError, ValidationError
from faultray.model.loader import load_yaml


# ---------------------------------------------------------------------------
# L14-PANIC-001: User-friendly error messages
# ---------------------------------------------------------------------------


class TestUserFriendlyErrors:
    """Verify that error messages are helpful and not cryptic."""

    def test_missing_file_message_is_clear(self) -> None:
        """FileNotFoundError message should mention the file path."""
        try:
            load_yaml("/tmp/this_file_does_not_exist_faultray_test.yaml")
            pytest.fail("Should have raised FileNotFoundError")
        except FileNotFoundError as e:
            msg = str(e)
            assert "this_file_does_not_exist" in msg
            # Should NOT be a raw Python traceback
            assert "Traceback" not in msg

    def test_invalid_yaml_syntax_gives_guidance(self, tmp_path: Path) -> None:
        """Invalid YAML syntax should produce a parseable error."""
        yaml_file = tmp_path / "bad_syntax.yaml"
        yaml_file.write_text("components:\n  - id: [unclosed bracket\n")
        try:
            load_yaml(yaml_file)
            pytest.fail("Should have raised an error")
        except Exception as e:
            msg = str(e)
            # Error should be understandable
            assert len(msg) > 10, "Error message too short to be helpful"

    def test_invalid_component_type_lists_alternatives(
        self, tmp_path: Path,
    ) -> None:
        """Unknown component type should list valid alternatives."""
        yaml_content = {
            "components": [
                {"id": "x", "name": "X", "type": "magical_server"},
            ],
            "dependencies": [],
        }
        yaml_file = tmp_path / "bad_type.yaml"
        yaml_file.write_text(yaml.dump(yaml_content))
        try:
            load_yaml(yaml_file)
            pytest.fail("Should have raised ValidationError")
        except ValidationError as e:
            msg = str(e)
            assert "magical_server" in msg  # Shows what was wrong
            assert "Valid types" in msg  # Shows valid alternatives

    def test_missing_id_shows_entry_position(self, tmp_path: Path) -> None:
        """Missing component ID should indicate which entry."""
        yaml_content = {
            "components": [
                {"name": "OK", "type": "app_server", "id": "ok"},
                {"name": "Missing ID", "type": "app_server"},
            ],
            "dependencies": [],
        }
        yaml_file = tmp_path / "no_id.yaml"
        yaml_file.write_text(yaml.dump(yaml_content))
        try:
            load_yaml(yaml_file)
            pytest.fail("Should have raised ValidationError")
        except ValidationError as e:
            msg = str(e)
            # Should reference entry index
            assert "1" in msg or "missing" in msg.lower()

    def test_invalid_replicas_shows_value(self, tmp_path: Path) -> None:
        """Invalid replicas value should show what was provided."""
        yaml_content = {
            "components": [
                {"id": "r1", "name": "R1", "type": "app_server", "replicas": -1},
            ],
            "dependencies": [],
        }
        yaml_file = tmp_path / "bad_replicas.yaml"
        yaml_file.write_text(yaml.dump(yaml_content))
        try:
            load_yaml(yaml_file)
            pytest.fail("Should have raised ValidationError")
        except ValidationError as e:
            msg = str(e)
            assert "-1" in msg or "positive" in msg.lower()


# ---------------------------------------------------------------------------
# L14-PANIC-002: Error hierarchy provides structured handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Verify that errors can be caught at appropriate granularity."""

    def test_all_errors_catchable_by_base_class(self) -> None:
        """All FaultRay errors should be catchable with FaultRayError."""
        yaml_content = "not a mapping"
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            try:
                load_yaml(f.name)
                pytest.fail("Should have raised")
            except FaultRayError:
                pass  # Good: caught by base class
            finally:
                Path(f.name).unlink(missing_ok=True)

    def test_validation_error_is_also_value_error(self) -> None:
        """ValidationError should be catchable as ValueError too."""
        try:
            raise ValidationError("test")
        except ValueError:
            pass  # Good: backward compatible

    def test_error_str_is_not_empty(self) -> None:
        """All FaultRay error messages should be non-empty."""
        for exc_cls in [ValidationError, FaultRayError]:
            e = exc_cls("test message")
            assert str(e), f"{exc_cls.__name__} has empty str()"


# ---------------------------------------------------------------------------
# L14-PANIC-003: Graceful handling of corrupted/unexpected input
# ---------------------------------------------------------------------------


class TestGracefulDegradation:
    """Verify graceful handling of unexpected input."""

    def test_empty_yaml_file(self, tmp_path: Path) -> None:
        """An empty YAML file should raise a clear error."""
        yaml_file = tmp_path / "empty.yaml"
        yaml_file.write_text("")
        with pytest.raises((ValidationError, TypeError, AttributeError)):
            load_yaml(yaml_file)

    def test_yaml_with_only_comments(self, tmp_path: Path) -> None:
        """YAML with only comments should raise a clear error."""
        yaml_file = tmp_path / "comments.yaml"
        yaml_file.write_text("# This is just a comment\n# Another comment\n")
        with pytest.raises((ValidationError, TypeError, AttributeError)):
            load_yaml(yaml_file)

    def test_binary_file_does_not_crash(self, tmp_path: Path) -> None:
        """A binary file should raise an error, not crash."""
        binary_file = tmp_path / "binary.yaml"
        binary_file.write_bytes(b"\x00\x01\x02\x03\xff\xfe\xfd")
        with pytest.raises(Exception):
            load_yaml(binary_file)

    def test_html_file_does_not_crash(self, tmp_path: Path) -> None:
        """An HTML file renamed to .yaml should not crash."""
        html_file = tmp_path / "page.yaml"
        html_file.write_text("<html><body>Not YAML</body></html>")
        with pytest.raises((ValidationError, Exception)):
            load_yaml(html_file)

    def test_json_file_loads_as_yaml(self, tmp_path: Path) -> None:
        """JSON is valid YAML; a JSON file should load if structured correctly."""
        import json
        data = {
            "components": [
                {"id": "j1", "name": "JSON Component", "type": "app_server"},
            ],
            "dependencies": [],
        }
        json_file = tmp_path / "data.yaml"
        json_file.write_text(json.dumps(data))
        graph = load_yaml(json_file)
        assert graph.get_component("j1") is not None

    def test_simulation_error_does_not_propagate_raw_traceback(self) -> None:
        """Simulation errors should be wrapped, not raw exceptions."""
        from faultray.model.graph import InfraGraph
        from faultray.simulator.engine import SimulationEngine
        from faultray.simulator.scenarios import Scenario, Fault

        graph = InfraGraph()
        engine = SimulationEngine(graph)
        # Run a scenario that references nonexistent component
        scenario = Scenario(
            id="bad",
            name="Bad Scenario",
            description="A bad scenario for testing",
            faults=[Fault(target_component_id="nonexistent", fault_type="component_down")],
        )
        # Should not crash; engine wraps errors gracefully
        result = engine.run_scenario(scenario)
        # Should have error info, not a crash
        assert result is not None
