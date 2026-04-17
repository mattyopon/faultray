# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""L13 Escrow / Build Reproducibility Tests — Business Continuity layer.

Validates that FaultRay can be built and installed reproducibly:
- pyproject.toml is valid and complete for pip install
- Entry points are declared and functional
- Package metadata is complete
"""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# L13-ESCROW-001: pyproject.toml build reproducibility
# ---------------------------------------------------------------------------


class TestBuildReproducibility:
    """Verify that the project can be built from pyproject.toml."""

    PROJECT_ROOT = Path(__file__).resolve().parent.parent

    def test_pyproject_toml_valid(self) -> None:
        """pyproject.toml should be parseable."""
        toml_path = self.PROJECT_ROOT / "pyproject.toml"
        assert toml_path.exists()
        content = toml_path.read_text()
        assert "[project]" in content
        assert "[build-system]" in content

    def test_build_system_requires_hatchling(self) -> None:
        """Build system should specify hatchling."""
        toml_path = self.PROJECT_ROOT / "pyproject.toml"
        content = toml_path.read_text()
        assert "hatchling" in content

    def test_project_name_declared(self) -> None:
        """Project name should be 'faultray'."""
        toml_path = self.PROJECT_ROOT / "pyproject.toml"
        content = toml_path.read_text()
        assert 'name = "faultray"' in content

    def test_version_declared(self) -> None:
        """Version should be declared in pyproject.toml."""
        toml_path = self.PROJECT_ROOT / "pyproject.toml"
        content = toml_path.read_text()
        assert 'version = "' in content

    def test_requires_python_declared(self) -> None:
        """Python version requirement should be declared."""
        toml_path = self.PROJECT_ROOT / "pyproject.toml"
        content = toml_path.read_text()
        assert "requires-python" in content

    def test_src_layout_correct(self) -> None:
        """Source should be in src/faultray/ directory."""
        src_dir = self.PROJECT_ROOT / "src" / "faultray"
        assert src_dir.is_dir(), "src/faultray/ directory not found"
        assert (src_dir / "__init__.py").exists(), "__init__.py missing"

    def test_py_typed_marker_exists(self) -> None:
        """py.typed marker should exist for PEP 561 compliance."""
        marker = self.PROJECT_ROOT / "src" / "faultray" / "py.typed"
        assert marker.exists(), "py.typed marker missing for PEP 561"


# ---------------------------------------------------------------------------
# L13-ESCROW-002: Entry points are functional
# ---------------------------------------------------------------------------


class TestEntryPoints:
    """Verify that declared entry points are functional."""

    def test_faultray_cli_entry_point_declared(self) -> None:
        """The 'faultray' CLI entry point should be declared."""
        toml_path = Path(__file__).resolve().parent.parent / "pyproject.toml"
        content = toml_path.read_text()
        assert 'faultray = "faultray.cli:app"' in content

    def test_faultray_mcp_entry_point_declared(self) -> None:
        """The 'faultray-mcp' entry point should be declared."""
        toml_path = Path(__file__).resolve().parent.parent / "pyproject.toml"
        content = toml_path.read_text()
        assert 'faultray-mcp = "faultray.mcp_server:main"' in content

    def test_cli_module_importable(self) -> None:
        """The CLI module should be importable."""
        mod = importlib.import_module("faultray.cli")
        assert hasattr(mod, "app")

    def test_mcp_server_module_importable(self) -> None:
        """The MCP server module should be importable (skipped if mcp extra not installed)."""
        try:
            mod = importlib.import_module("faultray.mcp_server")
        except ImportError as exc:
            pytest.skip(f"faultray.mcp_server requires optional mcp extra: {exc}")
        assert hasattr(mod, "main")

    def test_faultray_help_runs(self) -> None:
        """'python -m faultray --help' should exit with code 0."""
        result = subprocess.run(
            [sys.executable, "-m", "faultray", "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, f"Help failed: {result.stderr}"
        assert "faultray" in result.stdout.lower() or "usage" in result.stdout.lower()


# ---------------------------------------------------------------------------
# L13-ESCROW-003: Package metadata completeness
# ---------------------------------------------------------------------------


class TestPackageMetadata:
    """Verify package metadata for distribution."""

    def test_license_declared(self) -> None:
        """License should be declared in pyproject.toml."""
        toml_path = Path(__file__).resolve().parent.parent / "pyproject.toml"
        content = toml_path.read_text()
        assert "license" in content

    def test_authors_declared(self) -> None:
        """Authors should be declared."""
        toml_path = Path(__file__).resolve().parent.parent / "pyproject.toml"
        content = toml_path.read_text()
        assert "authors" in content

    def test_description_declared(self) -> None:
        """Description should be declared."""
        toml_path = Path(__file__).resolve().parent.parent / "pyproject.toml"
        content = toml_path.read_text()
        assert "description" in content

    def test_classifiers_declared(self) -> None:
        """Classifiers should be declared for PyPI."""
        toml_path = Path(__file__).resolve().parent.parent / "pyproject.toml"
        content = toml_path.read_text()
        assert "classifiers" in content

    def test_urls_declared(self) -> None:
        """Project URLs (homepage, repo) should be declared."""
        toml_path = Path(__file__).resolve().parent.parent / "pyproject.toml"
        content = toml_path.read_text()
        assert "[project.urls]" in content
        assert "Homepage" in content
        assert "Repository" in content

    def test_version_matches_init(self) -> None:
        """Version in pyproject.toml should match __version__."""
        import faultray

        toml_path = Path(__file__).resolve().parent.parent / "pyproject.toml"
        content = toml_path.read_text()
        expected = f'version = "{faultray.__version__}"'
        assert expected in content, (
            f"pyproject.toml version doesn't match __version__ {faultray.__version__}"
        )
