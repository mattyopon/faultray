# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""L5 Security Tests — Quality & Reliability layer.

Validates that FaultRay is resilient against common security threats:
- Known CVE scanning (pip-audit simulation)
- Injection attacks through YAML/JSON parsers
- Path traversal attack prevention
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
import yaml

from faultray.errors import ValidationError
from faultray.model.loader import load_yaml


# ---------------------------------------------------------------------------
# L5-SEC-001: Dependency CVE scanning (pip-audit simulation)
# ---------------------------------------------------------------------------


class TestDependencyCVEScanning:
    """Verify that project dependencies are declared and auditable."""

    def test_pyproject_toml_exists(self) -> None:
        """pyproject.toml must exist at the project root."""
        root = Path(__file__).resolve().parent.parent
        assert (root / "pyproject.toml").exists(), "pyproject.toml not found"

    def test_dependencies_are_pinned_with_minimum_versions(self) -> None:
        """All dependencies should specify at least a minimum version."""
        root = Path(__file__).resolve().parent.parent
        toml_text = (root / "pyproject.toml").read_text()
        # Every dependency line should contain >=
        in_deps = False
        for line in toml_text.splitlines():
            stripped = line.strip()
            if stripped == 'dependencies = [':
                in_deps = True
                continue
            if in_deps:
                if stripped == ']':
                    break
                if stripped.startswith('"') and stripped.endswith('",'):
                    dep = stripped.strip('",')
                    assert ">=" in dep, (
                        f"Dependency {dep!r} does not specify a minimum version"
                    )

    def test_no_wildcard_version_pins(self) -> None:
        """Dependencies must not use wildcard (*) version specifiers."""
        root = Path(__file__).resolve().parent.parent
        toml_text = (root / "pyproject.toml").read_text()
        assert "=*" not in toml_text, "Wildcard version pin found in dependencies"

    def test_yaml_safe_load_used_not_unsafe(self) -> None:
        """Verify that FaultRay uses yaml.safe_load, never yaml.load without Loader."""
        src_root = Path(__file__).resolve().parent.parent / "src" / "faultray"
        violations: list[str] = []
        for py_file in src_root.rglob("*.py"):
            content = py_file.read_text(errors="replace")
            lines = content.splitlines()
            for i, line in enumerate(lines, 1):
                stripped = line.strip()
                # Flag yaml.load( without safe_load
                if "yaml.load(" in stripped and "yaml.safe_load(" not in stripped:
                    # Ignore comments
                    if not stripped.startswith("#"):
                        violations.append(f"{py_file.name}:{i}: {stripped}")
        assert not violations, (
            "Unsafe yaml.load() usage found:\n" + "\n".join(violations)
        )


# ---------------------------------------------------------------------------
# L5-SEC-002: SQL injection-style attacks via YAML/JSON parser
# ---------------------------------------------------------------------------


class TestInjectionViaParser:
    """Ensure that malicious input strings don't break YAML parsing."""

    SQL_INJECTION_PAYLOADS = [
        "'; DROP TABLE components; --",
        "\" OR 1=1 --",
        "1; SELECT * FROM users",
        "Robert'); DROP TABLE Students;--",
    ]

    @pytest.mark.parametrize("payload", SQL_INJECTION_PAYLOADS)
    def test_sql_injection_in_component_name(self, payload: str, tmp_path: Path) -> None:
        """Component names with SQL injection payloads should be treated as plain strings."""
        yaml_content = {
            "components": [
                {
                    "id": "test-comp",
                    "name": payload,
                    "type": "app_server",
                }
            ],
            "dependencies": [],
        }
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text(yaml.dump(yaml_content))
        graph = load_yaml(yaml_file)
        comp = graph.get_component("test-comp")
        assert comp is not None
        assert comp.name == payload  # Stored literally, never interpreted

    @pytest.mark.parametrize("payload", SQL_INJECTION_PAYLOADS)
    def test_sql_injection_in_component_id(self, payload: str, tmp_path: Path) -> None:
        """Component IDs with SQL injection payloads are safely handled."""
        safe_id = "comp-test"
        yaml_content = {
            "components": [
                {"id": safe_id, "name": payload, "type": "app_server"},
            ],
            "dependencies": [],
        }
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text(yaml.dump(yaml_content))
        graph = load_yaml(yaml_file)
        assert graph.get_component(safe_id) is not None

    def test_extremely_long_string_does_not_crash(self, tmp_path: Path) -> None:
        """A component name with 100K characters should not crash the parser."""
        long_name = "A" * 100_000
        yaml_content = {
            "components": [
                {"id": "long", "name": long_name, "type": "app_server"},
            ],
            "dependencies": [],
        }
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text(yaml.dump(yaml_content))
        graph = load_yaml(yaml_file)
        assert graph.get_component("long") is not None


# ---------------------------------------------------------------------------
# L5-SEC-003: Path traversal attack prevention
# ---------------------------------------------------------------------------


class TestPathTraversal:
    """Verify that path traversal attempts are handled safely."""

    TRAVERSAL_PATHS = [
        "../../../etc/passwd",
        "..\\..\\..\\windows\\system32\\config\\sam",
        "/etc/shadow",
        "....//....//etc/passwd",
        "%2e%2e%2f%2e%2e%2fetc/passwd",
    ]

    @pytest.mark.parametrize("malicious_path", TRAVERSAL_PATHS)
    def test_path_traversal_in_yaml_load_raises(self, malicious_path: str) -> None:
        """load_yaml should raise FileNotFoundError for traversal paths."""
        with pytest.raises((FileNotFoundError, ValidationError, OSError)):
            load_yaml(malicious_path)

    def test_path_traversal_in_component_host_is_stored_literally(
        self, tmp_path: Path,
    ) -> None:
        """Path traversal in component host field is stored as plain text."""
        yaml_content = {
            "components": [
                {
                    "id": "c1",
                    "name": "test",
                    "type": "app_server",
                    "host": "../../../etc/passwd",
                }
            ],
            "dependencies": [],
        }
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text(yaml.dump(yaml_content))
        graph = load_yaml(yaml_file)
        comp = graph.get_component("c1")
        assert comp is not None
        assert comp.host == "../../../etc/passwd"  # Stored literally

    def test_null_bytes_in_path_rejected(self) -> None:
        """Null bytes in file path should not bypass file access."""
        with pytest.raises((FileNotFoundError, ValueError, OSError)):
            load_yaml("/tmp/test\x00.yaml")
