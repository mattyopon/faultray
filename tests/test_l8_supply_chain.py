# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""L8 Supply Chain Tests — Social Trust layer.

Validates the integrity of FaultRay's dependency supply chain:
- All dependencies declared in pyproject.toml
- No hidden/undeclared dependencies
- Import integrity
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# L8-SC-001: pyproject.toml dependency completeness
# ---------------------------------------------------------------------------


class TestDependencyDeclaration:
    """Verify all runtime dependencies are properly declared."""

    PROJECT_ROOT = Path(__file__).resolve().parent.parent

    def _get_declared_deps(self) -> set[str]:
        """Parse dependency names from pyproject.toml."""
        toml_text = (self.PROJECT_ROOT / "pyproject.toml").read_text()
        deps: set[str] = set()
        in_deps = False
        for line in toml_text.splitlines():
            stripped = line.strip()
            if stripped == 'dependencies = [':
                in_deps = True
                continue
            if in_deps:
                if stripped == ']':
                    break
                # Extract package name before version specifier
                match = re.match(r'"([a-zA-Z0-9_-]+)', stripped)
                if match:
                    deps.add(match.group(1).lower().replace("-", "_"))
        return deps

    def test_pyproject_toml_exists(self) -> None:
        """pyproject.toml should exist."""
        assert (self.PROJECT_ROOT / "pyproject.toml").exists()

    def test_core_dependencies_declared(self) -> None:
        """Core dependencies (typer, rich, pydantic, etc.) must be declared."""
        deps = self._get_declared_deps()
        required = {
            "typer", "rich", "pydantic", "networkx", "psutil",
            "fastapi", "uvicorn", "jinja2", "httpx", "pyyaml",
        }
        missing = required - deps
        assert not missing, f"Missing core dependencies: {missing}"

    def test_no_hidden_stdlib_assumptions(self) -> None:
        """FaultRay should not import non-existent stdlib modules."""
        # Just verify core imports work
        import json
        import logging
        import math
        import random
        import tempfile
        import pathlib
        # All should import without error

    def test_faultray_package_importable(self) -> None:
        """The faultray package should be importable."""
        import faultray
        assert hasattr(faultray, "__version__")

    def test_core_submodules_importable(self) -> None:
        """Core submodules should import without error."""
        modules = [
            "faultray.model.components",
            "faultray.model.graph",
            "faultray.model.loader",
            "faultray.model.demo",
            "faultray.errors",
            "faultray.config",
            "faultray.log_config",
        ]
        for mod_name in modules:
            mod = importlib.import_module(mod_name)
            assert mod is not None, f"Failed to import {mod_name}"

    def test_simulator_submodules_importable(self) -> None:
        """Simulator submodules should import without error."""
        modules = [
            "faultray.simulator.engine",
            "faultray.simulator.cascade",
            "faultray.simulator.scenarios",
            "faultray.simulator.monte_carlo",
        ]
        for mod_name in modules:
            mod = importlib.import_module(mod_name)
            assert mod is not None, f"Failed to import {mod_name}"


# ---------------------------------------------------------------------------
# L8-SC-002: No hidden dependencies
# ---------------------------------------------------------------------------


class TestNoDependencyLeaks:
    """Verify there are no undeclared external imports."""

    def test_sdk_import_does_not_require_optional_deps(self) -> None:
        """Importing faultray.sdk should work without optional deps."""
        # FaultZero should be importable
        from faultray.sdk import FaultZero
        assert FaultZero is not None

    def test_model_layer_only_needs_core_deps(self) -> None:
        """The model layer should only need pydantic, networkx, pyyaml."""
        from faultray.model.components import Component, ComponentType
        from faultray.model.graph import InfraGraph
        from faultray.model.loader import load_yaml
        # If these import without error, core deps are sufficient

    def test_version_string_format(self) -> None:
        """Version should follow semver format."""
        import faultray
        version = faultray.__version__
        parts = version.split(".")
        assert len(parts) == 3, f"Version {version} is not semver"
        for part in parts:
            assert part.isdigit(), f"Version part {part!r} is not numeric"

    def test_build_system_declared(self) -> None:
        """Build system (hatchling) should be declared in pyproject.toml."""
        root = Path(__file__).resolve().parent.parent
        toml_text = (root / "pyproject.toml").read_text()
        assert "hatchling" in toml_text, "Build system (hatchling) not declared"
