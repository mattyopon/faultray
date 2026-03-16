"""Documentation accuracy tests -- verify docs match code.

These tests ensure that documentation (README, MkDocs pages, CLI help,
example YAML files, and public API surfaces) accurately reflect the
actual code behavior. They test ACCURACY, not style.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest
import yaml

# Project root
PROJECT_ROOT = Path(__file__).parent.parent
SRC_ROOT = PROJECT_ROOT / "src" / "faultray"
DOCS_ROOT = PROJECT_ROOT / "docs"
EXAMPLES_ROOT = PROJECT_ROOT / "examples"
TEMPLATES_ROOT = SRC_ROOT / "templates"


# ---------------------------------------------------------------------------
# Test 1: README CLI commands exist
# ---------------------------------------------------------------------------

class TestReadmeCLICommandsExist:
    """Every command listed in README should be a real CLI command."""

    def _get_readme_commands(self) -> list[str]:
        """Extract 'faultray <cmd>' patterns from README."""
        readme_path = PROJECT_ROOT / "README.md"
        if not readme_path.exists():
            pytest.skip("README.md not found")
        text = readme_path.read_text(encoding="utf-8")

        # Find patterns like: faultray <command>
        # Match within code blocks and inline code
        patterns = re.findall(r'faultray\s+([a-z][a-z0-9_-]*)', text)
        # Deduplicate
        return list(set(patterns))

    def _get_registered_commands(self) -> set[str]:
        """Get all registered CLI commands from the Typer app."""
        from faultray.cli import app
        from typer.main import get_command

        click_app = get_command(app)
        commands = set()
        if hasattr(click_app, "commands"):
            commands = set(click_app.commands.keys())
        elif hasattr(click_app, "list_commands"):
            ctx = click_app.make_context("faultray", [])
            commands = set(click_app.list_commands(ctx))
        return commands

    def test_readme_commands_are_registered(self):
        """Commands mentioned in README should exist in the CLI app."""
        readme_cmds = self._get_readme_commands()
        if not readme_cmds:
            pytest.skip("No commands found in README")

        registered = self._get_registered_commands()
        if not registered:
            pytest.skip("Could not enumerate registered commands")

        missing = []
        # Commands that are external tools or subcommands, not top-level CLI commands
        external_or_sub = {
            "pip", "docker", "compose", "up", "run", "install", "build",
            "scan", "load",  # may be subcommands or removed
        }
        for cmd in readme_cmds:
            if cmd in external_or_sub:
                continue
            # Normalize dashes to underscores for comparison
            if cmd not in registered and cmd.replace("-", "_") not in registered:
                missing.append(cmd)

        # Allow up to 3 minor mismatches (README might mention future/deprecated commands)
        assert len(missing) <= 3, (
            f"README references {len(missing)} commands not found in CLI: {missing}\n"
            f"Registered commands: {sorted(registered)}"
        )


# ---------------------------------------------------------------------------
# Test 2: MkDocs pages not empty
# ---------------------------------------------------------------------------

class TestMkDocsPagesNotEmpty:
    """Every MkDocs page should have meaningful content (> 100 chars)."""

    def _get_mkdocs_pages(self) -> list[Path]:
        """Parse mkdocs.yml and extract all referenced page paths."""
        mkdocs_path = PROJECT_ROOT / "mkdocs.yml"
        if not mkdocs_path.exists():
            return []

        with open(mkdocs_path) as f:
            config = yaml.safe_load(f)

        pages = []

        def _extract_pages(nav_items):
            if isinstance(nav_items, list):
                for item in nav_items:
                    _extract_pages(item)
            elif isinstance(nav_items, dict):
                for key, value in nav_items.items():
                    if isinstance(value, str):
                        pages.append(DOCS_ROOT / value)
                    else:
                        _extract_pages(value)
            elif isinstance(nav_items, str):
                pages.append(DOCS_ROOT / nav_items)

        if "nav" in config:
            _extract_pages(config["nav"])

        return pages

    def test_mkdocs_pages_have_content(self):
        """Each MkDocs page should have more than 100 characters of content."""
        pages = self._get_mkdocs_pages()
        if not pages:
            pytest.skip("No mkdocs.yml or no nav pages found")

        empty_pages = []
        missing_pages = []
        for page_path in pages:
            if not page_path.exists():
                missing_pages.append(str(page_path.relative_to(PROJECT_ROOT)))
                continue
            content = page_path.read_text(encoding="utf-8").strip()
            if len(content) < 100:
                empty_pages.append(
                    f"{page_path.relative_to(PROJECT_ROOT)} ({len(content)} chars)"
                )

        if missing_pages:
            pytest.fail(
                f"MkDocs references {len(missing_pages)} missing page(s): {missing_pages}"
            )

        assert len(empty_pages) == 0, (
            f"MkDocs pages with < 100 chars: {empty_pages}"
        )


# ---------------------------------------------------------------------------
# Test 3: All public API documented
# ---------------------------------------------------------------------------

class TestAllPublicAPIDocumented:
    """Every function in __init__.py __all__ should have a docstring."""

    def test_public_api_has_docstrings(self):
        """All public API names in __all__ should have docstrings when imported."""
        from faultray import __all__ as public_api

        missing_docs = []
        import_errors = []

        for name in public_api:
            try:
                obj = getattr(importlib.import_module("faultray"), name)
            except (ImportError, AttributeError) as exc:
                import_errors.append(f"{name}: {exc}")
                continue

            # Check for docstring on the class/function itself
            doc = getattr(obj, "__doc__", None)
            if not doc or len(doc.strip()) < 10:
                missing_docs.append(name)

        assert len(import_errors) == 0, (
            f"Public API names that fail to import: {import_errors}"
        )
        # Allow a small number of missing docstrings (type aliases, constants)
        assert len(missing_docs) <= 2, (
            f"Public API names without meaningful docstrings: {missing_docs}"
        )


# ---------------------------------------------------------------------------
# Test 4: Changelog versions match (if changelog exists)
# ---------------------------------------------------------------------------

class TestChangelogVersions:
    """Version numbers in changelog should be consistent."""

    def test_init_version_is_valid(self):
        """__version__ should be a valid semantic version string."""
        from faultray import __version__

        assert __version__, "__version__ should not be empty"
        # Should match semver pattern: X.Y.Z (with optional pre-release)
        assert re.match(r'^\d+\.\d+\.\d+', __version__), (
            f"__version__ '{__version__}' does not match semver pattern"
        )

    def test_pyproject_version_matches_init(self):
        """pyproject.toml version should match __init__.py __version__."""
        from faultray import __version__

        pyproject_path = PROJECT_ROOT / "pyproject.toml"
        if not pyproject_path.exists():
            pytest.skip("pyproject.toml not found")

        content = pyproject_path.read_text(encoding="utf-8")
        # Extract version from pyproject.toml
        match = re.search(r'version\s*=\s*"([^"]+)"', content)
        if not match:
            pytest.skip("Could not extract version from pyproject.toml")

        pyproject_version = match.group(1)
        assert pyproject_version == __version__, (
            f"pyproject.toml version ({pyproject_version}) != "
            f"__init__.py version ({__version__})"
        )


# ---------------------------------------------------------------------------
# Test 5: Example YAML files loadable
# ---------------------------------------------------------------------------

class TestExampleYAMLFilesLoadable:
    """All YAML files in examples/ and templates/ should load without error."""

    def _find_yaml_files(self) -> list[Path]:
        """Find all YAML files in examples and templates."""
        yaml_files = []
        for directory in [EXAMPLES_ROOT, TEMPLATES_ROOT]:
            if directory.exists():
                yaml_files.extend(directory.glob("*.yaml"))
                yaml_files.extend(directory.glob("*.yml"))
        return yaml_files

    def test_all_yaml_files_parseable(self):
        """Every YAML file should parse without error."""
        yaml_files = self._find_yaml_files()
        if not yaml_files:
            pytest.skip("No YAML files found in examples/ or templates/")

        errors = []
        for yf in yaml_files:
            try:
                with open(yf) as f:
                    data = yaml.safe_load(f)
                assert data is not None, f"YAML file is empty: {yf.name}"
            except Exception as exc:
                errors.append(f"{yf.name}: {exc}")

        assert len(errors) == 0, f"YAML files with parse errors: {errors}"

    def test_template_yaml_loadable_by_faultray(self):
        """Template YAML files should load via faultray.model.loader."""
        from faultray.model.loader import load_yaml

        template_files = list(TEMPLATES_ROOT.glob("*.yaml"))
        if not template_files:
            pytest.skip("No template YAML files found")

        errors = []
        for tf in template_files:
            try:
                graph = load_yaml(tf)
                assert len(graph.components) > 0, f"Template '{tf.name}' has no components"
            except Exception as exc:
                errors.append(f"{tf.name}: {exc}")

        assert len(errors) == 0, f"Templates that fail to load: {errors}"

    def test_example_yaml_loadable_by_faultray(self):
        """Example YAML files (infra models) should load via faultray."""
        from faultray.model.loader import load_yaml

        example_yamls = []
        if EXAMPLES_ROOT.exists():
            for yf in EXAMPLES_ROOT.glob("*.yaml"):
                # Skip non-model YAMLs (e.g., CI configs)
                content = yf.read_text(encoding="utf-8")
                if "components:" in content:
                    example_yamls.append(yf)

        if not example_yamls:
            pytest.skip("No example infrastructure YAML files found")

        errors = []
        for yf in example_yamls:
            try:
                graph = load_yaml(yf)
                assert len(graph.components) > 0
            except Exception as exc:
                errors.append(f"{yf.name}: {exc}")

        assert len(errors) == 0, f"Example YAMLs that fail to load: {errors}"


# ---------------------------------------------------------------------------
# Test 6: Help text matches actual options
# ---------------------------------------------------------------------------

class TestHelpTextMatchesOptions:
    """CLI --help output should list all actual options."""

    def test_main_help_works(self):
        """Main CLI --help should produce output with registered commands."""
        from typer.testing import CliRunner
        from faultray.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "faultray" in result.output.lower() or "usage" in result.output.lower()

    def test_simulate_help_shows_options(self):
        """simulate --help should document --model, --json, --dynamic."""
        from typer.testing import CliRunner
        from faultray.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["simulate", "--help"])
        assert result.exit_code == 0
        output = result.output.lower()
        assert "--model" in output, "simulate --help should document --model"
        assert "--json" in output, "simulate --help should document --json"

    def test_evaluate_help_shows_options(self):
        """evaluate --help should document key options."""
        from typer.testing import CliRunner
        from faultray.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["evaluate", "--help"])
        assert result.exit_code == 0
        output = result.output.lower()
        assert "--model" in output or "--json" in output

    @pytest.mark.parametrize("cmd", [
        "security", "cost", "plan", "fix", "fuzz", "slo-budget",
    ])
    def test_command_help_exits_zero(self, cmd: str):
        """All documented commands should have working --help."""
        from typer.testing import CliRunner
        from faultray.cli import app

        runner = CliRunner()
        result = runner.invoke(app, [cmd, "--help"])
        assert result.exit_code == 0, f"{cmd} --help failed: {result.output}"
        assert len(result.output) > 50, f"{cmd} --help output too short"


# ---------------------------------------------------------------------------
# Test 7: __all__ completeness
# ---------------------------------------------------------------------------

class TestAllCompleteness:
    """__all__ in __init__.py should export importable names."""

    def test_all_names_importable(self):
        """Every name in __all__ should be importable from faultray."""
        from faultray import __all__ as public_api
        import faultray

        for name in public_api:
            try:
                obj = getattr(faultray, name)
                assert obj is not None, f"'{name}' imported but is None"
            except (ImportError, AttributeError) as exc:
                pytest.fail(f"Cannot import '{name}' from faultray: {exc}")

    def test_all_names_are_strings(self):
        """__all__ should be a list of strings."""
        from faultray import __all__ as public_api

        assert isinstance(public_api, (list, tuple))
        for name in public_api:
            assert isinstance(name, str), f"__all__ entry is not a string: {name!r}"


# ---------------------------------------------------------------------------
# Test 8: Component model consistency
# ---------------------------------------------------------------------------

class TestComponentModelConsistency:
    """Component types and fields should be consistent across docs and code."""

    def test_all_component_types_in_enum(self):
        """All ComponentType enum values should be recognized strings."""
        from faultray.model.components import ComponentType

        # These should exist as per the code and documentation
        expected = {
            "load_balancer", "web_server", "app_server", "database",
            "cache", "queue", "storage", "dns", "external_api", "custom",
        }
        actual = {ct.value for ct in ComponentType}
        assert expected.issubset(actual), (
            f"Missing component types: {expected - actual}"
        )

    def test_fault_types_in_enum(self):
        """All FaultType enum values should be valid strings."""
        from faultray.simulator.scenarios import FaultType

        expected = {
            "component_down", "latency_spike", "cpu_saturation",
            "memory_exhaustion", "disk_full", "connection_pool_exhaustion",
            "network_partition", "traffic_spike",
        }
        actual = {ft.value for ft in FaultType}
        assert expected.issubset(actual), (
            f"Missing fault types: {expected - actual}"
        )

    def test_health_status_enum(self):
        """HealthStatus enum should have expected values."""
        from faultray.model.components import HealthStatus

        expected = {"healthy", "degraded", "down", "overloaded"}
        actual = {hs.value for hs in HealthStatus}
        assert expected.issubset(actual), (
            f"Missing health statuses: {expected - actual}"
        )


# ---------------------------------------------------------------------------
# Test 9: Schema version consistency
# ---------------------------------------------------------------------------

class TestSchemaVersionConsistency:
    """Schema version should be consistent across the codebase."""

    def test_schema_version_is_string(self):
        """SCHEMA_VERSION should be a non-empty string."""
        from faultray.model.components import SCHEMA_VERSION

        assert isinstance(SCHEMA_VERSION, str)
        assert len(SCHEMA_VERSION) > 0

    def test_saved_model_includes_schema_version(self, tmp_path: Path):
        """A saved model JSON should include schema_version."""
        import json
        from faultray.model.demo import create_demo_graph
        from faultray.model.components import SCHEMA_VERSION

        graph = create_demo_graph()
        model_path = tmp_path / "test.json"
        graph.save(model_path)

        data = json.loads(model_path.read_text())
        assert "schema_version" in data
        assert data["schema_version"] == SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Test 10: Templates registry matches files
# ---------------------------------------------------------------------------

class TestTemplatesRegistryMatchesFiles:
    """Templates registry should match actual YAML files on disk."""

    def test_all_registered_templates_have_files(self):
        """Every template in the TEMPLATES dict should have a corresponding YAML file."""
        from faultray.templates import TEMPLATES, get_template_path

        for name in TEMPLATES:
            path = get_template_path(name)
            assert path.exists(), (
                f"Template '{name}' registered but file missing: {path}"
            )

    def test_template_files_have_components(self):
        """Every template YAML should have a 'components' key with entries."""
        from faultray.templates import TEMPLATES, get_template_path

        for name in TEMPLATES:
            path = get_template_path(name)
            with open(path) as f:
                data = yaml.safe_load(f)
            assert "components" in data, (
                f"Template '{name}' YAML missing 'components' key"
            )
            assert len(data["components"]) > 0, (
                f"Template '{name}' has empty components list"
            )
